#!/usr/bin/env python3
"""S012 Module 6: Paper Trade Logger — tracks paper trades and measures LLM calibration.

Opens paper trades from approved signals, monitors prices against targets/stops,
closes trades on hit/expiry, and produces calibration reports.

Usage:
    python3 scripts/s012/paper_logger.py --open <signal_id>      # Open paper trade from signal
    python3 scripts/s012/paper_logger.py --check                  # Check all open trades vs targets
    python3 scripts/s012/paper_logger.py --close <trade_id> --reason manual  # Manual close
    python3 scripts/s012/paper_logger.py --status                 # Show all trades
    python3 scripts/s012/paper_logger.py --calibration            # Show calibration report
    python3 scripts/s012/paper_logger.py --pnl                    # Show P&L summary
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from signal_generator import SignalStore, TradingSignal

logger = logging.getLogger(__name__)

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
JSONL_PATH = PROJECT_ROOT / "data" / "s012" / "paper-trades.jsonl"

# --- Constants ---
GAMMA_BASE = "https://gamma-api.polymarket.com"
DEFAULT_BANKROLL = 10_000.0


# --- Dataclass ---

@dataclass
class PaperTrade:
    trade_id: str                   # PT-S012-001, PT-S012-002, etc.
    signal_id: str
    market_id: str
    market_question: str

    # Entry
    direction: str                  # YES | NO
    entry_price: float
    entry_time: datetime
    size_usdc: float
    shares: float                   # size_usdc / entry_price

    # Targets
    target_price: float
    stop_price: float
    expiry_time: datetime           # entry_time + time_horizon

    # Exit (filled when closed)
    exit_price: float | None
    exit_time: datetime | None
    exit_reason: str | None         # TARGET_HIT | STOP_HIT | TIME_EXPIRED | MANUAL

    # P&L
    pnl_usdc: float | None
    pnl_pct: float | None          # pnl_usdc / size_usdc

    # Classification
    signal_type: str                # S012-OVER | S012-UNDER
    domain: str
    reaction_delta: float
    estimated_shift: float
    actual_move: float

    # Calibration (filled at resolution)
    market_resolved: bool | None
    llm_direction_correct: bool | None
    reaction_call_correct: bool | None

    status: str                     # OPEN | CLOSED | EXPIRED


@dataclass
class CalibrationReport:
    total_trades: int
    open_trades: int
    closed_trades: int

    # P&L
    total_pnl_usdc: float
    avg_pnl_per_trade: float
    win_rate: float

    # By type
    overreaction_count: int
    overreaction_win_rate: float
    underreaction_count: int
    underreaction_win_rate: float

    # LLM calibration
    llm_direction_accuracy: float
    avg_estimated_shift: float
    avg_actual_shift: float

    # Classification accuracy
    reaction_call_accuracy: float

    # By domain
    domain_breakdown: dict[str, dict]


# --- P&L ---

def calculate_pnl(direction: str, entry_price: float, exit_price: float,
                  shares: float) -> float:
    """Calculate P&L for a paper trade.

    For YES: bought at entry, value at exit → (exit - entry) * shares
    For NO:  bought at (1 - entry_yes), value at (1 - exit_yes)
             → simplifies to (entry_yes - exit_yes) * shares
    All prices are YES prices.
    """
    if direction == "YES":
        return (exit_price - entry_price) * shares
    else:
        return (entry_price - exit_price) * shares


# --- Trade ID ---

def next_trade_id(conn: sqlite3.Connection) -> str:
    """Generate next sequential trade ID: PT-S012-001, PT-S012-002, etc."""
    row = conn.execute(
        "SELECT trade_id FROM s012_paper_trades ORDER BY trade_id DESC LIMIT 1"
    ).fetchone()

    if row is None:
        return "PT-S012-001"

    last_id = row[0]
    try:
        num = int(last_id.split("-")[-1])
    except (ValueError, IndexError):
        num = 0

    return f"PT-S012-{num + 1:03d}"


# --- Price Fetching ---

def fetch_current_yes_price(market_id: str) -> float | None:
    """Fetch current YES price from Gamma API."""
    url = f"{GAMMA_BASE}/markets/{market_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "s012-paper-logger/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        prices = json.loads(data.get("outcomePrices", "[]"))
        if prices:
            return float(prices[0])
    except Exception as e:
        logger.warning("Failed to fetch price for %s: %s", market_id, e)
    return None


# --- SQLite Store ---

class TradeStore:
    """SQLite-backed paper trade storage."""

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS s012_paper_trades (
                trade_id TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                market_id TEXT NOT NULL,
                market_question TEXT,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                entry_time TEXT NOT NULL,
                size_usdc REAL NOT NULL,
                shares REAL NOT NULL,
                target_price REAL,
                stop_price REAL,
                expiry_time TEXT,
                exit_price REAL,
                exit_time TEXT,
                exit_reason TEXT,
                pnl_usdc REAL,
                pnl_pct REAL,
                signal_type TEXT,
                domain TEXT,
                reaction_delta REAL,
                estimated_shift REAL,
                actual_move REAL,
                market_resolved INTEGER,
                llm_direction_correct INTEGER,
                reaction_call_correct INTEGER,
                status TEXT DEFAULT 'OPEN'
            );
            CREATE INDEX IF NOT EXISTS idx_trade_status ON s012_paper_trades(status);
        """)
        self.conn.commit()

    def save(self, t: PaperTrade):
        """Persist a paper trade to SQLite."""
        self.conn.execute("""
            INSERT OR REPLACE INTO s012_paper_trades
                (trade_id, signal_id, market_id, market_question,
                 direction, entry_price, entry_time, size_usdc, shares,
                 target_price, stop_price, expiry_time,
                 exit_price, exit_time, exit_reason,
                 pnl_usdc, pnl_pct,
                 signal_type, domain, reaction_delta, estimated_shift, actual_move,
                 market_resolved, llm_direction_correct, reaction_call_correct,
                 status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t.trade_id, t.signal_id, t.market_id, t.market_question,
            t.direction, t.entry_price, t.entry_time.isoformat(),
            t.size_usdc, t.shares,
            t.target_price, t.stop_price, t.expiry_time.isoformat(),
            t.exit_price,
            t.exit_time.isoformat() if t.exit_time else None,
            t.exit_reason,
            t.pnl_usdc, t.pnl_pct,
            t.signal_type, t.domain, t.reaction_delta,
            t.estimated_shift, t.actual_move,
            _bool_to_int(t.market_resolved),
            _bool_to_int(t.llm_direction_correct),
            _bool_to_int(t.reaction_call_correct),
            t.status,
        ))
        self.conn.commit()

    def load_open(self) -> list[dict]:
        """Load all open trades."""
        return self._load_by_status("OPEN")

    def load_all(self, limit: int = 100) -> list[dict]:
        """Load all trades ordered by entry time."""
        rows = self.conn.execute("""
            SELECT trade_id, signal_id, market_id, market_question,
                   direction, entry_price, entry_time, size_usdc, shares,
                   target_price, stop_price, expiry_time,
                   exit_price, exit_time, exit_reason,
                   pnl_usdc, pnl_pct,
                   signal_type, domain, reaction_delta, estimated_shift, actual_move,
                   market_resolved, llm_direction_correct, reaction_call_correct,
                   status
            FROM s012_paper_trades
            ORDER BY entry_time DESC LIMIT ?
        """, (limit,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def load_closed(self) -> list[dict]:
        """Load closed and expired trades."""
        rows = self.conn.execute("""
            SELECT trade_id, signal_id, market_id, market_question,
                   direction, entry_price, entry_time, size_usdc, shares,
                   target_price, stop_price, expiry_time,
                   exit_price, exit_time, exit_reason,
                   pnl_usdc, pnl_pct,
                   signal_type, domain, reaction_delta, estimated_shift, actual_move,
                   market_resolved, llm_direction_correct, reaction_call_correct,
                   status
            FROM s012_paper_trades
            WHERE status IN ('CLOSED', 'EXPIRED')
            ORDER BY exit_time DESC
        """).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_exit(self, trade_id: str, exit_price: float, exit_time: datetime,
                    exit_reason: str, pnl_usdc: float, pnl_pct: float,
                    status: str) -> bool:
        """Close a trade with exit details."""
        cursor = self.conn.execute("""
            UPDATE s012_paper_trades
            SET exit_price = ?, exit_time = ?, exit_reason = ?,
                pnl_usdc = ?, pnl_pct = ?, status = ?
            WHERE trade_id = ?
        """, (
            exit_price, exit_time.isoformat(), exit_reason,
            pnl_usdc, pnl_pct, status, trade_id,
        ))
        self.conn.commit()
        return cursor.rowcount > 0

    def update_calibration(self, trade_id: str, market_resolved: bool,
                           llm_direction_correct: bool,
                           reaction_call_correct: bool) -> bool:
        """Record calibration data after market resolution."""
        cursor = self.conn.execute("""
            UPDATE s012_paper_trades
            SET market_resolved = ?, llm_direction_correct = ?,
                reaction_call_correct = ?
            WHERE trade_id = ?
        """, (
            int(market_resolved), int(llm_direction_correct),
            int(reaction_call_correct), trade_id,
        ))
        self.conn.commit()
        return cursor.rowcount > 0

    def find_by_prefix(self, prefix: str) -> str | None:
        """Find a trade_id matching a prefix."""
        row = self.conn.execute(
            "SELECT trade_id FROM s012_paper_trades WHERE trade_id LIKE ?",
            (prefix + "%",),
        ).fetchone()
        return row[0] if row else None

    def _load_by_status(self, status: str) -> list[dict]:
        rows = self.conn.execute("""
            SELECT trade_id, signal_id, market_id, market_question,
                   direction, entry_price, entry_time, size_usdc, shares,
                   target_price, stop_price, expiry_time,
                   exit_price, exit_time, exit_reason,
                   pnl_usdc, pnl_pct,
                   signal_type, domain, reaction_delta, estimated_shift, actual_move,
                   market_resolved, llm_direction_correct, reaction_call_correct,
                   status
            FROM s012_paper_trades
            WHERE status = ?
            ORDER BY entry_time DESC
        """, (status,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "trade_id": r[0], "signal_id": r[1],
            "market_id": r[2], "market_question": r[3],
            "direction": r[4], "entry_price": r[5],
            "entry_time": r[6], "size_usdc": r[7], "shares": r[8],
            "target_price": r[9], "stop_price": r[10],
            "expiry_time": r[11],
            "exit_price": r[12], "exit_time": r[13],
            "exit_reason": r[14],
            "pnl_usdc": r[15], "pnl_pct": r[16],
            "signal_type": r[17], "domain": r[18],
            "reaction_delta": r[19], "estimated_shift": r[20],
            "actual_move": r[21],
            "market_resolved": _int_to_bool(r[22]),
            "llm_direction_correct": _int_to_bool(r[23]),
            "reaction_call_correct": _int_to_bool(r[24]),
            "status": r[25],
        }

    def close(self):
        self.conn.close()


def _bool_to_int(v: bool | None) -> int | None:
    if v is None:
        return None
    return int(v)


def _int_to_bool(v: int | None) -> bool | None:
    if v is None:
        return None
    return bool(v)


# --- JSONL Logger ---

def log_to_jsonl(t: PaperTrade):
    """Append paper trade to JSONL file."""
    JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "trade_id": t.trade_id,
        "signal_id": t.signal_id,
        "market_id": t.market_id,
        "market_question": t.market_question,
        "direction": t.direction,
        "entry_price": t.entry_price,
        "entry_time": t.entry_time.isoformat(),
        "size_usdc": t.size_usdc,
        "shares": t.shares,
        "target_price": t.target_price,
        "stop_price": t.stop_price,
        "expiry_time": t.expiry_time.isoformat(),
        "exit_price": t.exit_price,
        "exit_time": t.exit_time.isoformat() if t.exit_time else None,
        "exit_reason": t.exit_reason,
        "pnl_usdc": t.pnl_usdc,
        "pnl_pct": t.pnl_pct,
        "signal_type": t.signal_type,
        "domain": t.domain,
        "reaction_delta": t.reaction_delta,
        "estimated_shift": t.estimated_shift,
        "actual_move": t.actual_move,
        "status": t.status,
    }

    with open(JSONL_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


# --- Open Trade ---

def open_trade_from_signal(signal: dict, store: TradeStore) -> PaperTrade:
    """Create a PaperTrade from an approved signal dict."""
    now = datetime.now(timezone.utc)
    trade_id = next_trade_id(store.conn)

    entry_price = signal["entry_price"]
    size_usdc = signal["size_usdc"]
    shares = size_usdc / entry_price if entry_price > 0 else 0.0

    time_horizon_hours = signal.get("time_horizon_hours", 168)

    trade = PaperTrade(
        trade_id=trade_id,
        signal_id=signal["signal_id"],
        market_id=signal["market_id"],
        market_question=signal.get("market_question", signal["market_id"]),
        direction=signal["direction"],
        entry_price=entry_price,
        entry_time=now,
        size_usdc=size_usdc,
        shares=round(shares, 4),
        target_price=signal["target_price"],
        stop_price=signal["stop_price"],
        expiry_time=now + timedelta(hours=time_horizon_hours),
        exit_price=None,
        exit_time=None,
        exit_reason=None,
        pnl_usdc=None,
        pnl_pct=None,
        signal_type=signal["signal_type"],
        domain=signal.get("domain", "OTHER"),
        reaction_delta=signal.get("reaction_delta", 0.0),
        estimated_shift=signal.get("estimated_shift", 0.0),
        actual_move=signal.get("actual_move", 0.0),
        market_resolved=None,
        llm_direction_correct=None,
        reaction_call_correct=None,
        status="OPEN",
    )

    store.save(trade)
    log_to_jsonl(trade)
    return trade


# --- Check Trades ---

def check_trade(trade: dict, current_yes_price: float, now: datetime) -> dict | None:
    """Check if a trade should be closed. Returns close info dict or None."""
    direction = trade["direction"]
    target = trade["target_price"]
    stop = trade["stop_price"]
    expiry = datetime.fromisoformat(trade["expiry_time"])

    if direction == "YES":
        if current_yes_price >= target:
            return {"reason": "TARGET_HIT", "exit_price": current_yes_price}
        if current_yes_price <= stop:
            return {"reason": "STOP_HIT", "exit_price": current_yes_price}
    else:  # NO
        # For NO trades: target/stop are in NO-price terms
        # target_price is the NO target; current NO = 1 - current_yes
        current_no = 1.0 - current_yes_price
        if current_no >= target:
            return {"reason": "TARGET_HIT", "exit_price": current_yes_price}
        if current_no <= stop:
            return {"reason": "STOP_HIT", "exit_price": current_yes_price}

    if now >= expiry:
        return {"reason": "TIME_EXPIRED", "exit_price": current_yes_price}

    return None


def close_trade(store: TradeStore, trade: dict, exit_price: float,
                exit_reason: str) -> tuple[float, float]:
    """Close a trade and record P&L. Returns (pnl_usdc, pnl_pct)."""
    now = datetime.now(timezone.utc)
    pnl = calculate_pnl(
        trade["direction"], trade["entry_price"], exit_price, trade["shares"]
    )
    pnl_pct = pnl / trade["size_usdc"] if trade["size_usdc"] > 0 else 0.0

    status = "EXPIRED" if exit_reason == "TIME_EXPIRED" else "CLOSED"

    store.update_exit(
        trade_id=trade["trade_id"],
        exit_price=exit_price,
        exit_time=now,
        exit_reason=exit_reason,
        pnl_usdc=round(pnl, 2),
        pnl_pct=round(pnl_pct, 4),
        status=status,
    )
    return round(pnl, 2), round(pnl_pct, 4)


# --- Calibration ---

def build_calibration_report(trades: list[dict]) -> CalibrationReport:
    """Build a calibration report from a list of trade dicts."""
    open_trades = [t for t in trades if t["status"] == "OPEN"]
    closed = [t for t in trades if t["status"] in ("CLOSED", "EXPIRED")]

    total_pnl = sum(t["pnl_usdc"] or 0.0 for t in closed)
    wins = [t for t in closed if (t["pnl_usdc"] or 0.0) > 0]
    win_rate = len(wins) / len(closed) if closed else 0.0
    avg_pnl = total_pnl / len(closed) if closed else 0.0

    # By type
    over = [t for t in closed if t["signal_type"] == "S012-OVER"]
    under = [t for t in closed if t["signal_type"] == "S012-UNDER"]
    over_wins = [t for t in over if (t["pnl_usdc"] or 0.0) > 0]
    under_wins = [t for t in under if (t["pnl_usdc"] or 0.0) > 0]

    # LLM calibration (only where calibration data exists)
    calibrated = [t for t in trades if t["llm_direction_correct"] is not None]
    llm_correct = [t for t in calibrated if t["llm_direction_correct"]]
    llm_accuracy = len(llm_correct) / len(calibrated) if calibrated else 0.0

    all_shifts = [t for t in trades if t["estimated_shift"] is not None]
    avg_est = (sum(abs(t["estimated_shift"]) for t in all_shifts) / len(all_shifts)
               if all_shifts else 0.0)
    avg_act = (sum(abs(t["actual_move"]) for t in all_shifts) / len(all_shifts)
               if all_shifts else 0.0)

    # Reaction call accuracy
    reaction_checked = [t for t in trades if t["reaction_call_correct"] is not None]
    reaction_correct = [t for t in reaction_checked if t["reaction_call_correct"]]
    reaction_accuracy = (len(reaction_correct) / len(reaction_checked)
                         if reaction_checked else 0.0)

    # By domain
    domain_breakdown: dict[str, dict] = {}
    for t in closed:
        d = t.get("domain", "OTHER")
        if d not in domain_breakdown:
            domain_breakdown[d] = {"count": 0, "wins": 0, "pnl": 0.0}
        domain_breakdown[d]["count"] += 1
        domain_breakdown[d]["pnl"] += t["pnl_usdc"] or 0.0
        if (t["pnl_usdc"] or 0.0) > 0:
            domain_breakdown[d]["wins"] += 1

    for d in domain_breakdown:
        c = domain_breakdown[d]["count"]
        domain_breakdown[d]["win_rate"] = domain_breakdown[d]["wins"] / c if c else 0.0
        domain_breakdown[d]["avg_pnl"] = domain_breakdown[d]["pnl"] / c if c else 0.0

    return CalibrationReport(
        total_trades=len(trades),
        open_trades=len(open_trades),
        closed_trades=len(closed),
        total_pnl_usdc=round(total_pnl, 2),
        avg_pnl_per_trade=round(avg_pnl, 2),
        win_rate=round(win_rate, 4),
        overreaction_count=len(over),
        overreaction_win_rate=round(len(over_wins) / len(over), 4) if over else 0.0,
        underreaction_count=len(under),
        underreaction_win_rate=round(len(under_wins) / len(under), 4) if under else 0.0,
        llm_direction_accuracy=round(llm_accuracy, 4),
        avg_estimated_shift=round(avg_est, 4),
        avg_actual_shift=round(avg_act, 4),
        reaction_call_accuracy=round(reaction_accuracy, 4),
        domain_breakdown=domain_breakdown,
    )


# --- CLI Commands ---

def cmd_open(signal_id_prefix: str):
    """Open a paper trade from an approved signal."""
    sig_store = SignalStore()
    full_id = sig_store.find_by_prefix(signal_id_prefix)

    if not full_id:
        print(f"No signal found matching '{signal_id_prefix}'")
        sig_store.close()
        return

    # Load the signal
    all_sigs = sig_store.load_all(limit=200)
    sig_store.close()

    signal = None
    for s in all_sigs:
        if s["signal_id"] == full_id:
            signal = s
            break

    if signal is None:
        print(f"Signal {full_id[:12]}... not found in store")
        return

    if signal["status"] != "APPROVED":
        print(f"Signal {full_id[:12]}... is {signal['status']}, not APPROVED")
        return

    trade_store = TradeStore()
    trade = open_trade_from_signal(signal, trade_store)
    trade_store.close()

    print(f"OPENED: {trade.trade_id}")
    print(f"  Market: {trade.market_question}")
    print(f"  {trade.direction} @ {trade.entry_price:.1%} "
          f"| Target: {trade.target_price:.1%} | Stop: {trade.stop_price:.1%}")
    print(f"  Size: ${trade.size_usdc:.0f} ({trade.shares:.1f} shares)")
    print(f"  Expires: {trade.expiry_time.strftime('%Y-%m-%d %H:%M UTC')}")


def cmd_check():
    """Check all open trades against current prices."""
    store = TradeStore()
    open_trades = store.load_open()

    if not open_trades:
        print("No open trades.")
        store.close()
        return

    now = datetime.now(timezone.utc)
    print(f"\nChecking {len(open_trades)} open trade(s)...\n")

    for trade in open_trades:
        price = fetch_current_yes_price(trade["market_id"])
        if price is None:
            print(f"  {trade['trade_id']}: SKIP — could not fetch price")
            continue

        result = check_trade(trade, price, now)
        if result:
            pnl, pnl_pct = close_trade(store, trade, result["exit_price"],
                                        result["reason"])
            icon = "+" if pnl >= 0 else ""
            print(f"  {trade['trade_id']}: CLOSED — {result['reason']}")
            print(f"    P&L: {icon}${pnl:.2f} ({pnl_pct:+.1%})")
        else:
            # Show current status
            unrealized = calculate_pnl(
                trade["direction"], trade["entry_price"], price, trade["shares"]
            )
            icon = "+" if unrealized >= 0 else ""
            expiry = datetime.fromisoformat(trade["expiry_time"])
            remaining = expiry - now
            days_left = remaining.total_seconds() / 86400

            if trade["direction"] == "NO":
                current_no = 1.0 - price
                print(f"  {trade['trade_id']}: OPEN — NO @ {current_no:.1%} "
                      f"(entry {trade['entry_price']:.1%})")
            else:
                print(f"  {trade['trade_id']}: OPEN — YES @ {price:.1%} "
                      f"(entry {trade['entry_price']:.1%})")
            print(f"    Unrealized: {icon}${unrealized:.2f} | {days_left:.1f}d remaining")

    store.close()


def cmd_close(trade_id_prefix: str, reason: str):
    """Manually close a trade."""
    store = TradeStore()
    full_id = store.find_by_prefix(trade_id_prefix)

    if not full_id:
        print(f"No trade found matching '{trade_id_prefix}'")
        store.close()
        return

    # Find the trade
    all_trades = store.load_open()
    trade = None
    for t in all_trades:
        if t["trade_id"] == full_id:
            trade = t
            break

    if trade is None:
        print(f"Trade {full_id} is not open")
        store.close()
        return

    # Fetch current price
    price = fetch_current_yes_price(trade["market_id"])
    if price is None:
        print(f"Could not fetch current price for {trade['market_id']}")
        store.close()
        return

    pnl, pnl_pct = close_trade(store, trade, price, reason.upper())
    store.close()

    icon = "+" if pnl >= 0 else ""
    print(f"CLOSED: {full_id}")
    print(f"  Reason: {reason.upper()}")
    print(f"  Exit price (YES): {price:.1%}")
    print(f"  P&L: {icon}${pnl:.2f} ({pnl_pct:+.1%})")


def cmd_status():
    """Show all trades."""
    store = TradeStore()
    trades = store.load_all()
    store.close()

    if not trades:
        print("No paper trades yet.")
        return

    print(f"\n{'=' * 65}")
    print(f"S012 PAPER TRADES — {len(trades)} total")
    print(f"{'=' * 65}")

    for t in trades:
        _print_trade_row(t)


def cmd_calibration():
    """Show calibration report."""
    store = TradeStore()
    trades = store.load_all()
    store.close()

    if not trades:
        print("No trades for calibration.")
        return

    report = build_calibration_report(trades)

    print(f"\n{'=' * 55}")
    print("S012 CALIBRATION REPORT")
    print(f"{'=' * 55}")
    print(f"  Total trades: {report.total_trades}")
    print(f"  Open: {report.open_trades} | Closed: {report.closed_trades}")

    print(f"\n  P&L")
    icon = "+" if report.total_pnl_usdc >= 0 else ""
    print(f"    Total: {icon}${report.total_pnl_usdc:.2f}")
    print(f"    Avg/trade: ${report.avg_pnl_per_trade:.2f}")
    print(f"    Win rate: {report.win_rate:.1%}")

    print(f"\n  By Type")
    print(f"    Overreaction:  {report.overreaction_count} trades, "
          f"{report.overreaction_win_rate:.1%} win rate")
    print(f"    Underreaction: {report.underreaction_count} trades, "
          f"{report.underreaction_win_rate:.1%} win rate")

    print(f"\n  LLM Calibration")
    print(f"    Direction accuracy: {report.llm_direction_accuracy:.1%}")
    print(f"    Avg |estimated shift|: {report.avg_estimated_shift:.1%}")
    print(f"    Avg |actual shift|:    {report.avg_actual_shift:.1%}")
    print(f"    Reaction call accuracy: {report.reaction_call_accuracy:.1%}")

    if report.domain_breakdown:
        print(f"\n  By Domain")
        for domain, stats in sorted(report.domain_breakdown.items()):
            print(f"    {domain}: {stats['count']} trades, "
                  f"{stats['win_rate']:.0%} win, "
                  f"avg ${stats['avg_pnl']:.2f}")

    print(f"\n{'=' * 55}")


def cmd_pnl():
    """Show P&L summary."""
    store = TradeStore()
    trades = store.load_all()
    store.close()

    closed = [t for t in trades if t["status"] in ("CLOSED", "EXPIRED")]
    open_trades = [t for t in trades if t["status"] == "OPEN"]

    total_realized = sum(t["pnl_usdc"] or 0.0 for t in closed)
    wins = [t for t in closed if (t["pnl_usdc"] or 0.0) > 0]
    losses = [t for t in closed if (t["pnl_usdc"] or 0.0) < 0]

    print(f"\n{'=' * 55}")
    print("S012 P&L SUMMARY")
    print(f"{'=' * 55}")
    print(f"  Closed trades: {len(closed)}")
    print(f"  Open trades: {len(open_trades)}")

    icon = "+" if total_realized >= 0 else ""
    print(f"\n  Realized P&L: {icon}${total_realized:.2f}")

    if closed:
        print(f"  Win rate: {len(wins)}/{len(closed)} ({len(wins)/len(closed):.0%})")
        if wins:
            avg_win = sum(t["pnl_usdc"] for t in wins) / len(wins)
            print(f"  Avg win: +${avg_win:.2f}")
        if losses:
            avg_loss = sum(t["pnl_usdc"] for t in losses) / len(losses)
            print(f"  Avg loss: ${avg_loss:.2f}")

    if closed:
        print(f"\n  Trade History:")
        for t in closed:
            pnl = t["pnl_usdc"] or 0.0
            icon = "+" if pnl >= 0 else ""
            print(f"    {t['trade_id']} | {t['direction']:3s} | "
                  f"{t['exit_reason']:13s} | {icon}${pnl:.2f} ({t['pnl_pct']:+.1%})")

    print(f"\n{'=' * 55}")


def _print_trade_row(t: dict):
    """Print a single trade row."""
    status_icon = {"OPEN": "~", "CLOSED": "+", "EXPIRED": "x"}.get(t["status"], "?")

    print(f"\n  [{status_icon}] {t['trade_id']} — {t['status']}")
    print(f"    {t['direction']} @ {t['entry_price']:.1%} "
          f"| Target: {t['target_price']:.1%} | Stop: {t['stop_price']:.1%}")
    print(f"    Size: ${t['size_usdc']:.0f} ({t['shares']:.1f} shares) "
          f"| Type: {t['signal_type']} | Domain: {t.get('domain', '?')}")
    print(f"    Market: {t['market_question'][:60]}...")

    if t["exit_price"] is not None:
        pnl = t["pnl_usdc"] or 0.0
        icon = "+" if pnl >= 0 else ""
        print(f"    Exit: {t['exit_price']:.1%} ({t['exit_reason']}) "
              f"| P&L: {icon}${pnl:.2f} ({t['pnl_pct']:+.1%})")
    else:
        print(f"    Opened: {t['entry_time']}")
        print(f"    Expires: {t['expiry_time']}")


# --- Demo Data ---

def _make_demo_signal() -> dict:
    """Build a synthetic approved signal for testing."""
    now = datetime.now(timezone.utc)
    return {
        "signal_id": "demo-sig-pt-001",
        "market_id": "demo-mkt-pt-001",
        "market_question": "Will Iran reach a nuclear deal before July 2026?",
        "signal_type": "S012-OVER",
        "direction": "NO",
        "entry_price": 0.275,
        "target_price": 0.345,
        "stop_price": 0.195,
        "time_horizon_hours": 168,
        "size_usdc": 300.0,
        "size_pct": 0.03,
        "reaction_delta": 0.095,
        "estimated_shift": 0.08,
        "actual_move": 0.175,
        "confidence": 0.68,
        "domain": "GEO",
        "status": "APPROVED",
        "created_at": now.isoformat(),
    }


# --- Main ---

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    args = sys.argv[1:]

    if "--open" in args:
        idx = args.index("--open")
        sid = args[idx + 1] if idx + 1 < len(args) else ""
        if not sid:
            print("Usage: --open <signal_id_prefix>")
            sys.exit(1)
        cmd_open(sid)

    elif "--check" in args:
        cmd_check()

    elif "--close" in args:
        idx = args.index("--close")
        tid = args[idx + 1] if idx + 1 < len(args) else ""
        reason = "MANUAL"
        if "--reason" in args:
            r_idx = args.index("--reason")
            reason = args[r_idx + 1] if r_idx + 1 < len(args) else "MANUAL"
        if not tid:
            print("Usage: --close <trade_id> [--reason manual]")
            sys.exit(1)
        cmd_close(tid, reason)

    elif "--status" in args:
        cmd_status()

    elif "--calibration" in args:
        cmd_calibration()

    elif "--pnl" in args:
        cmd_pnl()

    else:
        print(__doc__)
        sys.exit(0)


if __name__ == "__main__":
    main()
