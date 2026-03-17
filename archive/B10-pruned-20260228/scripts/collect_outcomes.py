#!/usr/bin/env python3
"""NB11: Polymarket Outcome Collector — Auto-resolves signal outcomes.

Polls the Gamma API for resolution status of markets tracked in the
calibration engine. Auto-labels signal outcomes when a market resolves.
Supports manual labeling for paper trades or when auto-collection fails.

Usage:
    python3 scripts/collect_outcomes.py                    # Check all pending signals
    python3 scripts/collect_outcomes.py --days 7           # Only signals from last 7 days
    python3 scripts/collect_outcomes.py --signal SIG-abc   # Check specific signal
    python3 scripts/collect_outcomes.py --manual SIG-abc yes   # Manual label YES
    python3 scripts/collect_outcomes.py --manual SIG-abc no    # Manual label NO
    python3 scripts/collect_outcomes.py --dry-run          # Show what would be resolved
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from calibration_engine import CalibrationEngine  # noqa: E402

PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
SIGNALS_PATH = PROJECT_ROOT / "data" / "signals.jsonl"
GAMMA_BASE = "https://gamma-api.polymarket.com"


def curl_json(url: str) -> dict | list | None:
    """Fetch JSON from URL via curl."""
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '15',
             '-H', 'User-Agent: Mozilla/5.0', url],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, TypeError):
        return None


def fetch_market_resolution(condition_id: str) -> dict | None:
    """Check if a market has resolved via Gamma API.

    Returns dict with 'resolved', 'outcome' (YES/NO), 'outcome_prices' if resolved.
    Returns None on API failure.
    """
    url = f"{GAMMA_BASE}/markets/{condition_id}"
    data = curl_json(url)
    if not data or not isinstance(data, dict):
        return None

    closed = data.get('closed', False)
    if not closed:
        return {'resolved': False}

    # Parse outcome prices: ["1","0"] = YES resolved, ["0","1"] = NO resolved
    try:
        prices = json.loads(data.get('outcomePrices', '[]'))
        yes_price = float(prices[0]) if prices else None
    except (json.JSONDecodeError, ValueError, IndexError):
        yes_price = None

    if yes_price is None:
        return {'resolved': False}

    resolved_yes = yes_price > 0.5

    return {
        'resolved': True,
        'resolved_yes': resolved_yes,
        'resolution_price': yes_price,
        'question': data.get('question', ''),
    }


def load_pending_signals(days: int | None = None) -> list[dict]:
    """Load signals that haven't been resolved yet.

    Checks both the calibration DB and signals.jsonl for unresolved signals.
    """
    pending = []

    # From signals.jsonl (primary source)
    if SIGNALS_PATH.exists():
        cutoff = None
        if days:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        with open(SIGNALS_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    signal = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Skip already resolved (status != pending/approved/executed)
                status = signal.get('status', 'pending')
                if status in ('resolved', 'expired'):
                    continue

                if cutoff and signal.get('generated_at', '') < cutoff:
                    continue

                if signal.get('market_id'):
                    pending.append(signal)

    return pending


def manual_label(engine: CalibrationEngine, signal_id: str, resolved_yes: bool):
    """Manually label a signal's outcome."""
    # Ensure the signal exists in calibration DB
    row = engine.conn.execute(
        "SELECT market_question, direction FROM signal_outcomes WHERE signal_id = ?",
        (signal_id,)
    ).fetchone()

    if not row:
        # Try importing from signals.jsonl first
        engine.import_signals()
        row = engine.conn.execute(
            "SELECT market_question, direction FROM signal_outcomes WHERE signal_id = ?",
            (signal_id,)
        ).fetchone()

    if not row:
        print(f"Signal {signal_id} not found in calibration DB or signals.jsonl")
        return

    question, direction = row
    engine.record_outcome(signal_id, resolved_yes=resolved_yes)
    outcome = "YES" if resolved_yes else "NO"
    won = (direction == "YES" and resolved_yes) or (direction == "NO" and not resolved_yes)
    status = "WIN" if won else "LOSS"
    print(f"Labeled {signal_id}: resolved {outcome}, direction was {direction} -> {status}")
    print(f"  Market: {question}")


def check_single_signal(engine: CalibrationEngine, signal_id: str, dry_run: bool = False):
    """Check resolution status of a single signal."""
    # Find the signal in signals.jsonl or DB
    signal = None
    if SIGNALS_PATH.exists():
        with open(SIGNALS_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    s = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if s.get('signal_id') == signal_id:
                    signal = s
                    break

    if not signal or not signal.get('market_id'):
        print(f"Signal {signal_id} not found or has no market_id")
        return

    market_id = signal['market_id']
    question = signal.get('market_question', '?')[:60]

    result = fetch_market_resolution(market_id)
    if result is None:
        print(f"API failed for market {market_id}")
        return

    if not result['resolved']:
        print(f"[OPEN] {signal_id} — {question}")
        return

    outcome = "YES" if result['resolved_yes'] else "NO"
    direction = signal.get('direction', '?')
    won = (direction == "YES" and result['resolved_yes']) or \
          (direction == "NO" and not result['resolved_yes'])
    status = "WIN" if won else "LOSS"

    print(f"[{status}] {signal_id} — {question}")
    print(f"  Resolved: {outcome} | Our direction: {direction}")

    if not dry_run:
        engine.import_signals()
        engine.record_outcome(
            signal_id=signal_id,
            resolved_yes=result['resolved_yes'],
            resolution_price=result.get('resolution_price', 1.0 if result['resolved_yes'] else 0.0),
        )
        print("  Outcome recorded.")


def main():
    args = sys.argv[1:]
    dry_run = '--dry-run' in args

    engine = CalibrationEngine(db_path=DB_PATH)

    # --manual SIG-abc yes/no
    if '--manual' in args:
        idx = args.index('--manual')
        if idx + 2 >= len(args):
            print("Usage: --manual <signal_id> <yes|no>")
            engine.close()
            return
        sig_id = args[idx + 1]
        outcome_str = args[idx + 2].lower()
        if outcome_str not in ('yes', 'no'):
            print(f"Invalid outcome '{outcome_str}'. Use 'yes' or 'no'.")
            engine.close()
            return
        manual_label(engine, sig_id, resolved_yes=(outcome_str == 'yes'))
        engine.close()
        return

    # --signal SIG-abc
    if '--signal' in args:
        idx = args.index('--signal')
        if idx + 1 >= len(args):
            print("Usage: --signal <signal_id>")
            engine.close()
            return
        check_single_signal(engine, args[idx + 1], dry_run=dry_run)
        engine.close()
        return

    # Default: check all pending
    days = None
    for i, a in enumerate(args):
        if a == '--days' and i + 1 < len(args):
            days = int(args[i + 1])

    # Import any signals not yet in calibration DB
    imported = engine.import_signals()
    if imported:
        print(f"Imported {imported} new signal(s) into calibration DB")

    # Load pending signals
    pending = load_pending_signals(days)
    if not pending:
        print("No pending signals to check.")
        engine.close()
        return

    print(f"Checking {len(pending)} pending signal(s)...")
    print()

    resolved_count = 0
    for signal in pending:
        market_id = signal.get('market_id', '')
        question = signal.get('market_question', '?')[:60]
        signal_id = signal.get('signal_id', '')

        result = fetch_market_resolution(market_id)
        if result is None:
            print(f"  [ERROR] {signal_id[:8]} — API failed for {market_id[:20]}")
            continue

        if not result['resolved']:
            print(f"  [OPEN]  {signal_id[:8]} — {question}")
            continue

        outcome = "YES" if result['resolved_yes'] else "NO"
        direction = signal.get('direction', '?')
        won = (direction == "YES" and result['resolved_yes']) or \
              (direction == "NO" and not result['resolved_yes'])
        status = "WIN" if won else "LOSS"

        print(f"  [{status:>4}]  {signal_id[:8]} — {question}")
        print(f"          Resolved: {outcome} | Our direction: {direction} | "
              f"Est: {signal.get('suggested_probability', 0):.0%}")

        if not dry_run:
            engine.record_outcome(
                signal_id=signal_id,
                resolved_yes=result['resolved_yes'],
                resolution_price=result.get('resolution_price', 1.0 if result['resolved_yes'] else 0.0),
            )
            resolved_count += 1

    print()
    if dry_run:
        print("(dry run — no outcomes recorded)")
    else:
        print(f"Resolved {resolved_count} signal(s).")

        # Quick summary
        brier = engine.compute_brier(30)
        if brier is not None:
            print(f"Rolling 30d Brier: {brier:.4f} (market baseline: 0.349)")

    engine.close()


if __name__ == "__main__":
    main()
