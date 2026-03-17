#!/usr/bin/env python3
"""S012 Module 5: Signal Generator — converts actionable assessments into trading signals.

Applies portfolio-level risk checks (C1-C4 concentration, anti-pattern verification),
formats signals for human review, and manages signal lifecycle (pending/approved/rejected/expired).

Usage:
    python3 scripts/s012/signal_generator.py --demo              # Demo with synthetic assessment
    python3 scripts/s012/signal_generator.py --pending           # Show pending signals
    python3 scripts/s012/signal_generator.py --history           # Show all signals with outcomes
    python3 scripts/s012/signal_generator.py --approve <id>      # Mark signal as approved
    python3 scripts/s012/signal_generator.py --reject <id>       # Mark signal as rejected
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reaction_comparator import ReactionAssessment, AssessmentStore

logger = logging.getLogger(__name__)

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
JSONL_PATH = PROJECT_ROOT / "data" / "s012" / "signals.jsonl"
POSITIONS_PATH = PROJECT_ROOT / "strategies" / "paper-trades" / "positions.json"

# --- Constants ---
DEFAULT_BANKROLL = 10_000.0
SIGNAL_EXPIRY_HOURS = 2

# --- Concentration Caps (from research/position-sizing-rules.md) ---
C1_EVENT_CAP = 0.03          # 3% bankroll per underlying event
C2_DOMAIN_CAP = 0.10         # 10% bankroll per domain
C3_CORRELATION_THRESHOLD = 0.80  # Block if ρ > 0.80
C4_S012_CAP = 0.10           # 10% total S012 exposure

# --- Anti-Pattern Constants ---
AP2_REVENGE_WINDOW_SECONDS = 14_400  # 4 hours


# --- Dataclass ---

@dataclass
class TradingSignal:
    signal_id: str
    assessment_id: str
    event_id: str
    market_id: str
    market_question: str

    # Signal
    signal_type: str                # S012-OVER | S012-UNDER
    direction: str                  # YES | NO
    entry_price: float
    target_price: float
    stop_price: float
    time_horizon_hours: int
    size_usdc: float                # Actual $ amount
    size_pct: float                 # Bankroll percentage

    # Context
    reaction_delta: float
    estimated_shift: float
    actual_move: float
    confidence: float
    reasoning: str
    domain: str

    # Risk checks
    passed_concentration: bool
    passed_anti_patterns: bool
    risk_notes: list[str]

    # Status
    status: str                     # PENDING | APPROVED | REJECTED | EXPIRED
    created_at: datetime
    expires_at: datetime


# --- Portfolio Loading ---

def load_positions() -> tuple[float, list[dict]]:
    """Load bankroll and open positions from positions.json.

    Returns (bankroll, positions_list).
    """
    if not POSITIONS_PATH.exists():
        logger.warning("positions.json not found at %s — using defaults", POSITIONS_PATH)
        return DEFAULT_BANKROLL, []

    with open(POSITIONS_PATH) as f:
        data = json.load(f)

    bankroll = data.get("bankroll", DEFAULT_BANKROLL)
    positions = [p for p in data.get("positions", []) if p.get("status") == "open"]
    return bankroll, positions


# --- Keyword Extraction ---

_STOP_WORDS = frozenset({
    "will", "the", "a", "an", "be", "by", "in", "on", "of", "to", "for",
    "and", "or", "is", "at", "from", "with", "before", "after", "than",
    "has", "have", "had", "are", "was", "were", "not", "no", "yes",
    "that", "this", "it", "its", "there", "their", "they", "any", "some",
    "above", "below", "between", "more", "most", "next", "new",
})


def _market_keywords(question: str) -> set[str]:
    """Extract meaningful lowercase keywords from a market question."""
    words = set()
    for w in question.lower().split():
        cleaned = w.strip("?.,!\"'()[]{}$%")
        if cleaned and cleaned not in _STOP_WORDS and len(cleaned) > 2:
            words.add(cleaned)
    return words


# --- Correlation Heuristics ---

def overlaps_event(position: dict, signal: TradingSignal) -> bool:
    """Heuristic: does this position overlap the signal's underlying event?

    Uses domain match + keyword similarity as a proxy.
    """
    if position.get("domain") != signal.domain:
        return False

    pos_kw = _market_keywords(position.get("market", ""))
    sig_kw = _market_keywords(signal.market_question)

    if not pos_kw or not sig_kw:
        return False

    overlap = len(pos_kw & sig_kw)
    union = len(pos_kw | sig_kw)

    # Jaccard > 0.30 = likely same event
    return (overlap / union) > 0.30 if union > 0 else False


def estimate_correlation(position: dict, signal: TradingSignal) -> float:
    """Heuristic correlation estimate between an existing position and a signal.

    Returns estimated ρ in [0.0, 1.0].
    """
    if position.get("domain") != signal.domain:
        return 0.0

    pos_kw = _market_keywords(position.get("market", ""))
    sig_kw = _market_keywords(signal.market_question)

    if not pos_kw or not sig_kw:
        return 0.0

    overlap = len(pos_kw & sig_kw)
    union = len(pos_kw | sig_kw)

    jaccard = overlap / union if union > 0 else 0.0

    # Scale jaccard to correlation range: 0.0-1.0
    # Same domain + high keyword overlap → high correlation
    return min(jaccard * 1.2, 1.0)


# --- Concentration Checks (C1-C4) ---

def check_concentration(
    signal: TradingSignal,
    positions: list[dict],
    bankroll: float,
) -> tuple[bool, list[str]]:
    """Apply C1-C4 concentration rules. Returns (passed, warnings)."""
    warnings: list[str] = []
    passed = True

    # C1: Max 3% bankroll on any single event/thesis
    same_event = [p for p in positions if overlaps_event(p, signal)]
    existing_event_pct = sum(p.get("size_usd", 0) for p in same_event) / bankroll
    total_event_exposure = existing_event_pct + signal.size_pct
    if total_event_exposure > C1_EVENT_CAP:
        warnings.append(
            f"C1 FAIL: {total_event_exposure:.1%} on same event (max {C1_EVENT_CAP:.0%})"
        )
        passed = False

    # C2: Max 10% bankroll per domain
    same_domain = [p for p in positions if p.get("domain") == signal.domain]
    existing_domain_pct = sum(p.get("size_usd", 0) for p in same_domain) / bankroll
    total_domain = existing_domain_pct + signal.size_pct
    if total_domain > C2_DOMAIN_CAP:
        warnings.append(
            f"C2 FAIL: {total_domain:.1%} in {signal.domain} (max {C2_DOMAIN_CAP:.0%})"
        )
        passed = False

    # C3: Correlation check — don't add to highly correlated existing position
    for p in positions:
        rho = estimate_correlation(p, signal)
        if rho > C3_CORRELATION_THRESHOLD:
            warnings.append(
                f"C3 FAIL: rho>{C3_CORRELATION_THRESHOLD} with {p.get('market', '?')[:40]}"
            )
            passed = False
            break

    # C4: Max total S012 exposure 10%
    s012_positions = [p for p in positions if p.get("strategy", "").startswith("S012")]
    existing_s012_pct = sum(p.get("size_usd", 0) for p in s012_positions) / bankroll
    total_s012 = existing_s012_pct + signal.size_pct
    if total_s012 > C4_S012_CAP:
        warnings.append(
            f"C4 FAIL: {total_s012:.1%} total S012 (max {C4_S012_CAP:.0%})"
        )
        passed = False

    return passed, warnings


# --- Anti-Pattern Checks ---

def check_anti_patterns(
    signal: TradingSignal,
    recent_signals: list[dict],
) -> tuple[bool, list[str]]:
    """Verify this signal doesn't fall into known failure patterns."""
    warnings: list[str] = []
    passed = True

    # AP1: Not trading outside our domain expertise
    if signal.domain in ("ECO", "FIN") and signal.signal_type == "S012-UNDER":
        warnings.append("AP1: Underreaction trades in ECO/FIN are low-edge (too efficient)")
        passed = False

    # AP2: Not revenge trading (signal within 4h of a stopped-out S012 trade on same market)
    for s in recent_signals:
        if (s.get("market_id") == signal.market_id
                and s.get("status") == "STOPPED"
                and s.get("created_at")):
            try:
                s_time = datetime.fromisoformat(s["created_at"])
                diff = (signal.created_at - s_time).total_seconds()
                if 0 < diff < AP2_REVENGE_WINDOW_SECONDS:
                    warnings.append(
                        "AP2: Possible revenge trade — same market stopped out <4h ago"
                    )
                    passed = False
                    break
            except (ValueError, TypeError):
                pass

    # AP3: Entry price in Zone 4-5 (>$0.70) needs extra justification
    if signal.entry_price > 0.70:
        warnings.append(
            f"AP3: Entry at {signal.entry_price:.2f} is Zone 4+ — high asymmetric risk"
        )
        # Warning only, don't fail

    # AP5: Resolution rules read? (Flag for human verification)
    warnings.append("AP5: Verify resolution rules before executing")

    return passed, warnings


# --- Signal Generation ---

def generate_signal(
    assessment: ReactionAssessment,
    bankroll: float,
    positions: list[dict],
    recent_signals: list[dict],
    domain: str,
    reasoning: str = "",
) -> TradingSignal:
    """Convert an actionable ReactionAssessment into a TradingSignal with risk checks."""

    if not assessment.is_actionable:
        raise ValueError("Assessment is not actionable — cannot generate signal")

    now = datetime.now(timezone.utc)

    signal_type = (
        "S012-OVER" if assessment.reaction_type == "OVERREACTION" else "S012-UNDER"
    )

    size_usdc = round(assessment.size_pct * bankroll, 2)

    signal = TradingSignal(
        signal_id=str(uuid.uuid4()),
        assessment_id=assessment.assessment_id,
        event_id=assessment.event_id,
        market_id=assessment.market_id,
        market_question=assessment.market_question,
        signal_type=signal_type,
        direction=assessment.suggested_direction,
        entry_price=assessment.suggested_entry,
        target_price=assessment.suggested_target,
        stop_price=assessment.suggested_stop,
        time_horizon_hours=assessment.time_horizon_hours,
        size_usdc=size_usdc,
        size_pct=assessment.size_pct,
        reaction_delta=assessment.reaction_delta,
        estimated_shift=assessment.estimated_shift,
        actual_move=assessment.actual_move,
        confidence=assessment.adjusted_confidence,
        reasoning=reasoning,
        domain=domain,
        passed_concentration=True,   # Provisional — updated below
        passed_anti_patterns=True,   # Provisional — updated below
        risk_notes=[],
        status="PENDING",
        created_at=now,
        expires_at=now + timedelta(hours=SIGNAL_EXPIRY_HOURS),
    )

    # Run risk checks
    conc_passed, conc_warnings = check_concentration(signal, positions, bankroll)
    ap_passed, ap_warnings = check_anti_patterns(signal, recent_signals)

    signal.passed_concentration = conc_passed
    signal.passed_anti_patterns = ap_passed
    signal.risk_notes = conc_warnings + ap_warnings

    # Auto-reject if hard risk checks fail
    if not conc_passed or not ap_passed:
        signal.status = "REJECTED"

    return signal


# --- Signal Formatting ---

def format_signal(signal: TradingSignal) -> str:
    """Format a signal for human review."""
    lines: list[str] = []

    label = "OVERREACTION" if signal.signal_type == "S012-OVER" else "UNDERREACTION"
    lines.append("")
    lines.append("=" * 55)
    lines.append(f"  S012 SIGNAL: {label} DETECTED")
    lines.append("=" * 55)

    lines.append("")
    lines.append(f"Market: {signal.market_question}")

    pre_news = signal.entry_price - signal.actual_move if signal.direction == "YES" else None
    if signal.direction == "NO":
        yes_price = 1.0 - signal.entry_price
        pre_news_yes = yes_price - signal.actual_move
        lines.append(
            f"Current YES: {yes_price:.1%} | Pre-news: {pre_news_yes:.1%} | "
            f"Move: {signal.actual_move:+.1%}"
        )
    else:
        lines.append(
            f"Current YES: {signal.entry_price:.1%} | "
            f"Move: {signal.actual_move:+.1%}"
        )

    lines.append(f"Domain: {signal.domain}")

    lines.append("")
    lines.append(f"LLM Estimate: {signal.estimated_shift:+.1%} rational shift")
    lines.append(f"Actual Move:  {signal.actual_move:+.1%}")
    delta_label = "OVERREACTION" if signal.reaction_delta > 0 else "UNDERREACTION"
    mag_label = "STRONG" if abs(signal.reaction_delta) >= 0.08 else "MODERATE"
    lines.append(
        f"Delta:        {signal.reaction_delta:+.1%} {delta_label} ({mag_label})"
    )
    lines.append(f"Confidence:   {signal.confidence:.2f}")

    lines.append("")
    dir_label = "Buy" if signal.direction == "YES" else "Buy"
    token = "YES" if signal.direction == "YES" else "NO"
    entry_cents = signal.entry_price * 100
    lines.append(f"TRADE: Buy {token} at {entry_cents:.1f}c")
    target_cents = signal.target_price * 100
    lines.append(f"  Target: {target_cents:.1f}c")
    stop_cents = signal.stop_price * 100
    lines.append(f"  Stop:   {stop_cents:.1f}c")
    lines.append(f"  Size:   ${signal.size_usdc:.0f} ({signal.size_pct:.1%} bankroll)")
    lines.append(f"  Horizon: {signal.time_horizon_hours}h ({signal.time_horizon_hours // 24}d)")

    lines.append("")
    conc_icon = "PASS" if signal.passed_concentration else "FAIL"
    ap_icon = "PASS" if signal.passed_anti_patterns else "FAIL"
    lines.append(f"Risk: C1-C4 {conc_icon} | Anti-patterns {ap_icon}")
    for note in signal.risk_notes:
        lines.append(f"  - {note}")

    lines.append("")
    lines.append(f"Status: {signal.status}")
    lines.append(f"Signal ID: {signal.signal_id[:12]}...")
    lines.append(f"Expires: {signal.expires_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 55)

    return "\n".join(lines)


# --- SQLite Store ---

class SignalStore:
    """SQLite-backed signal storage."""

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS s012_signals (
                signal_id TEXT PRIMARY KEY,
                assessment_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                market_id TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL,
                target_price REAL,
                stop_price REAL,
                time_horizon_hours INTEGER,
                size_usdc REAL,
                size_pct REAL,
                reaction_delta REAL,
                confidence REAL,
                domain TEXT,
                passed_concentration INTEGER,
                passed_anti_patterns INTEGER,
                risk_notes TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_signal_status ON s012_signals(status);
            CREATE INDEX IF NOT EXISTS idx_signal_market ON s012_signals(market_id);
        """)
        self.conn.commit()

    def save(self, s: TradingSignal):
        """Persist a signal to SQLite."""
        self.conn.execute("""
            INSERT OR REPLACE INTO s012_signals
                (signal_id, assessment_id, event_id, market_id,
                 signal_type, direction, entry_price, target_price,
                 stop_price, time_horizon_hours, size_usdc, size_pct,
                 reaction_delta, confidence, domain,
                 passed_concentration, passed_anti_patterns,
                 risk_notes, status, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s.signal_id, s.assessment_id, s.event_id, s.market_id,
            s.signal_type, s.direction, s.entry_price, s.target_price,
            s.stop_price, s.time_horizon_hours, s.size_usdc, s.size_pct,
            s.reaction_delta, s.confidence, s.domain,
            int(s.passed_concentration), int(s.passed_anti_patterns),
            json.dumps(s.risk_notes), s.status,
            s.created_at.isoformat(), s.expires_at.isoformat(),
        ))
        self.conn.commit()

    def load_pending(self) -> list[dict]:
        """Load pending signals (auto-expire stale ones first)."""
        self._expire_stale()
        return self._load_by_status("PENDING")

    def load_all(self, limit: int = 50) -> list[dict]:
        """Load all signals ordered by creation time."""
        self._expire_stale()
        rows = self.conn.execute("""
            SELECT signal_id, assessment_id, event_id, market_id,
                   signal_type, direction, entry_price, target_price,
                   stop_price, time_horizon_hours, size_usdc, size_pct,
                   reaction_delta, confidence, domain,
                   passed_concentration, passed_anti_patterns,
                   risk_notes, status, created_at, expires_at
            FROM s012_signals
            ORDER BY created_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def load_recent_for_market(self, market_id: str, limit: int = 10) -> list[dict]:
        """Load recent signals for a specific market (for anti-pattern checks)."""
        rows = self.conn.execute("""
            SELECT signal_id, assessment_id, event_id, market_id,
                   signal_type, direction, entry_price, target_price,
                   stop_price, time_horizon_hours, size_usdc, size_pct,
                   reaction_delta, confidence, domain,
                   passed_concentration, passed_anti_patterns,
                   risk_notes, status, created_at, expires_at
            FROM s012_signals
            WHERE market_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (market_id, limit)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_status(self, signal_id: str, new_status: str) -> bool:
        """Update signal status. Returns True if found and updated."""
        cursor = self.conn.execute(
            "UPDATE s012_signals SET status = ? WHERE signal_id = ?",
            (new_status, signal_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def find_by_prefix(self, prefix: str) -> str | None:
        """Find a signal_id matching a prefix (for CLI convenience)."""
        row = self.conn.execute(
            "SELECT signal_id FROM s012_signals WHERE signal_id LIKE ?",
            (prefix + "%",),
        ).fetchone()
        return row[0] if row else None

    def _expire_stale(self):
        """Auto-expire PENDING signals past their expires_at."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE s012_signals SET status = 'EXPIRED' "
            "WHERE status = 'PENDING' AND expires_at < ?",
            (now,),
        )
        self.conn.commit()

    def _load_by_status(self, status: str) -> list[dict]:
        rows = self.conn.execute("""
            SELECT signal_id, assessment_id, event_id, market_id,
                   signal_type, direction, entry_price, target_price,
                   stop_price, time_horizon_hours, size_usdc, size_pct,
                   reaction_delta, confidence, domain,
                   passed_concentration, passed_anti_patterns,
                   risk_notes, status, created_at, expires_at
            FROM s012_signals
            WHERE status = ?
            ORDER BY created_at DESC
        """, (status,)).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(r: tuple) -> dict:
        return {
            "signal_id": r[0], "assessment_id": r[1],
            "event_id": r[2], "market_id": r[3],
            "signal_type": r[4], "direction": r[5],
            "entry_price": r[6], "target_price": r[7],
            "stop_price": r[8], "time_horizon_hours": r[9],
            "size_usdc": r[10], "size_pct": r[11],
            "reaction_delta": r[12], "confidence": r[13],
            "domain": r[14],
            "passed_concentration": bool(r[15]),
            "passed_anti_patterns": bool(r[16]),
            "risk_notes": json.loads(r[17]) if r[17] else [],
            "status": r[18],
            "created_at": r[19], "expires_at": r[20],
        }

    def close(self):
        self.conn.close()


# --- JSONL Logger ---

def log_to_jsonl(s: TradingSignal):
    """Append signal to JSONL file."""
    JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "signal_id": s.signal_id,
        "assessment_id": s.assessment_id,
        "event_id": s.event_id,
        "market_id": s.market_id,
        "market_question": s.market_question,
        "signal_type": s.signal_type,
        "direction": s.direction,
        "entry_price": s.entry_price,
        "target_price": s.target_price,
        "stop_price": s.stop_price,
        "time_horizon_hours": s.time_horizon_hours,
        "size_usdc": s.size_usdc,
        "size_pct": s.size_pct,
        "reaction_delta": s.reaction_delta,
        "estimated_shift": s.estimated_shift,
        "actual_move": s.actual_move,
        "confidence": s.confidence,
        "reasoning": s.reasoning,
        "domain": s.domain,
        "passed_concentration": s.passed_concentration,
        "passed_anti_patterns": s.passed_anti_patterns,
        "risk_notes": s.risk_notes,
        "status": s.status,
        "created_at": s.created_at.isoformat(),
        "expires_at": s.expires_at.isoformat(),
    }

    with open(JSONL_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


# --- Synthetic Demo Data ---

def _make_demo_assessment() -> ReactionAssessment:
    """Build a synthetic ACTIONABLE ReactionAssessment for demo mode.

    Scenario: Iran nuclear talks resume. Market spiked YES +17.5pp,
    but LLM estimates only +8pp rational shift → OVERREACTION (STRONG).
    """
    now = datetime.now(timezone.utc)
    return ReactionAssessment(
        assessment_id="demo-assess-sig-001",
        interpretation_id="demo-interp-sig-001",
        event_id="demo-evt-sig-001",
        market_id="demo-mkt-sig-001",
        market_question="Will Iran reach a nuclear deal before July 2026?",
        estimated_shift=0.08,
        actual_move=0.175,
        reaction_delta=0.095,       # 17.5pp - 8pp = +9.5pp OVERREACTION
        reaction_type="OVERREACTION",
        delta_magnitude="STRONG",
        raw_confidence=0.70,
        adjusted_confidence=0.68,
        is_actionable=True,
        suggested_direction="NO",
        suggested_entry=0.275,      # NO price = 1 - 0.725 YES
        suggested_target=0.345,     # YES drops to 65.5% → NO = 34.5%
        suggested_stop=0.195,       # YES rises to 80.5% → NO = 19.5%
        time_horizon_hours=168,     # 7 days
        size_pct=0.03,              # 3% for STRONG overreaction
        current_yes_price=0.725,
        price_before_news=0.55,
        assessed_at=now - timedelta(minutes=2),
    )


# --- CLI Commands ---

def cmd_demo():
    """Run a synthetic demo without any API calls."""
    assessment = _make_demo_assessment()
    bankroll, positions = load_positions()

    print("=" * 55)
    print("SIGNAL GENERATOR — Demo Mode")
    print("=" * 55)
    print(f"\nBankroll: ${bankroll:,.0f} | Open positions: {len(positions)}")

    # Generate signal
    signal = generate_signal(
        assessment=assessment,
        bankroll=bankroll,
        positions=positions,
        recent_signals=[],
        domain="GEO",
        reasoning="IAEA inspections represent a modest increase in deal probability, "
                  "but market has overreacted to unconfirmed reports.",
    )

    # Display
    print(format_signal(signal))

    # Persist
    store = SignalStore()
    store.save(signal)
    store.close()
    log_to_jsonl(signal)

    print(f"\nSaved to DB and signals.jsonl")


def cmd_pending():
    """Show pending signals."""
    store = SignalStore()
    pending = store.load_pending()
    store.close()

    if not pending:
        print("No pending signals.")
        return

    now = datetime.now(timezone.utc)
    print(f"\n{'=' * 60}")
    print(f"PENDING SIGNALS — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 60}")
    print(f"  {len(pending)} signal(s)\n")

    for s in pending:
        _print_signal_row(s)


def cmd_history():
    """Show all signals with outcomes."""
    store = SignalStore()
    signals = store.load_all(limit=50)
    store.close()

    if not signals:
        print("No signals yet. Run --demo first.")
        return

    now = datetime.now(timezone.utc)
    print(f"\n{'=' * 60}")
    print(f"SIGNAL HISTORY — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 60}")
    print(f"  {len(signals)} signal(s)\n")

    for s in signals:
        _print_signal_row(s)


def cmd_approve(signal_id_prefix: str):
    """Mark a signal as approved."""
    store = SignalStore()
    full_id = store.find_by_prefix(signal_id_prefix)

    if not full_id:
        print(f"No signal found matching '{signal_id_prefix}'")
        store.close()
        return

    updated = store.update_status(full_id, "APPROVED")
    store.close()

    if updated:
        print(f"APPROVED: {full_id[:12]}...")
    else:
        print(f"Failed to update {full_id[:12]}...")


def cmd_reject(signal_id_prefix: str):
    """Mark a signal as rejected."""
    store = SignalStore()
    full_id = store.find_by_prefix(signal_id_prefix)

    if not full_id:
        print(f"No signal found matching '{signal_id_prefix}'")
        store.close()
        return

    updated = store.update_status(full_id, "REJECTED")
    store.close()

    if updated:
        print(f"REJECTED: {full_id[:12]}...")
    else:
        print(f"Failed to update {full_id[:12]}...")


def _print_signal_row(s: dict):
    """Print a single signal row for CLI output."""
    delta_str = f"{s['reaction_delta']:+.1%}" if s['reaction_delta'] is not None else "N/A"
    conf_str = f"{s['confidence']:.0%}" if s['confidence'] is not None else "N/A"
    conc_str = "PASS" if s["passed_concentration"] else "FAIL"
    ap_str = "PASS" if s["passed_anti_patterns"] else "FAIL"

    print(f"  [{s['signal_type']:10s}] {s['status']:8s} | "
          f"Delta: {delta_str:>6s} | Conf: {conf_str} | "
          f"C1-4: {conc_str} | AP: {ap_str}")
    print(f"    {s['direction']} @ {s['entry_price']:.1%} "
          f"target {s['target_price']:.1%} stop {s['stop_price']:.1%} "
          f"| ${s['size_usdc']:.0f} ({s['size_pct']:.1%})")
    print(f"    Market: {s['market_id'][:20]}... | Domain: {s.get('domain', '?')}")
    print(f"    Created: {s['created_at']} | Expires: {s['expires_at']}")

    risk = s.get("risk_notes", [])
    if risk:
        for note in risk:
            print(f"    - {note}")
    print()


# --- Main ---

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    args = sys.argv[1:]
    if "--demo" in args:
        cmd_demo()
    elif "--pending" in args:
        cmd_pending()
    elif "--history" in args:
        cmd_history()
    elif "--approve" in args:
        idx = args.index("--approve")
        sid = args[idx + 1] if idx + 1 < len(args) else ""
        if not sid:
            print("Usage: --approve <signal_id_prefix>")
            sys.exit(1)
        cmd_approve(sid)
    elif "--reject" in args:
        idx = args.index("--reject")
        sid = args[idx + 1] if idx + 1 < len(args) else ""
        if not sid:
            print("Usage: --reject <signal_id_prefix>")
            sys.exit(1)
        cmd_reject(sid)
    else:
        print(__doc__)
        sys.exit(0)


if __name__ == "__main__":
    main()
