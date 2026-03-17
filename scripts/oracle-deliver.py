#!/usr/bin/env python3
"""
Oracle Deliver — Reads pending signals, writes formatted alerts for high-score signals.

Reads data/pending-signals.json, writes alerts to data/oracle-alerts.md,
marks delivered signals as delivered.

Usage:
    python3 scripts/oracle-deliver.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SIGNALS_FILE = DATA_DIR / "pending-signals.json"
ALERTS_FILE = DATA_DIR / "oracle-alerts.md"

MIN_SCORE = 4  # Minimum score to deliver


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def load_signals():
    if SIGNALS_FILE.exists():
        try:
            with open(SIGNALS_FILE) as f:
                data = json.load(f)
            return data.get("signals", [])
        except (json.JSONDecodeError, KeyError):
            return []
    return []


def save_signals(signals):
    with open(SIGNALS_FILE, "w") as f:
        json.dump({"signals": signals}, f, indent=2)


def format_alert(signal):
    """Format a signal as a markdown alert block."""
    domain = signal.get("domain", "OTHER")
    market = signal.get("market", "Unknown")
    trade = signal.get("trade", "")
    target = signal.get("target", "")
    stop = signal.get("stop", "")
    score = signal.get("score", 0)
    sig_type = signal.get("type", "UNKNOWN")
    source = signal.get("source", "unknown")
    magnitude = signal.get("magnitude", 0)
    notes = signal.get("notes", [])
    ts = signal.get("ts", "")

    lines = [
        f"## [{domain}] {market}",
        f"**Signal**: {sig_type} | **Source**: {source} | **Score**: {score}/10",
        f"**Trade**: {trade}",
    ]
    if target:
        lines.append(f"**Target**: {target}")
    if stop:
        lines.append(f"**Stop**: {stop}")
    if magnitude:
        lines.append(f"**Magnitude**: {magnitude:.1%}")
    if notes:
        notes_str = "; ".join(n for n in notes if n)
        if notes_str:
            lines.append(f"**Notes**: {notes_str}")
    lines.append(f"*Generated: {ts}*")
    lines.append("")

    return "\n".join(lines)


def deliver():
    signals = load_signals()
    if not signals:
        log("No signals to deliver")
        return

    # Find undelivered signals with score >= MIN_SCORE
    to_deliver = [
        s for s in signals
        if not s.get("delivered") and s.get("score", 0) >= MIN_SCORE
    ]

    if not to_deliver:
        log(f"No undelivered signals with score >= {MIN_SCORE}")
        return

    log(f"Delivering {len(to_deliver)} signals (score >= {MIN_SCORE})")

    # Read existing alerts file
    existing = ""
    if ALERTS_FILE.exists():
        existing = ALERTS_FILE.read_text()

    # Build new alerts
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    new_section = f"\n---\n\n# Oracle Alerts — {now}\n\n"
    for sig in to_deliver:
        new_section += format_alert(sig) + "\n"

    # Prepend header if file is new
    if not existing:
        existing = "# Oracle Alerts\n\n> Automated signals from the Oracle pipeline.\n> Score >= 4 delivered here. Review before acting.\n\n"

    # Append new alerts
    with open(ALERTS_FILE, "w") as f:
        f.write(existing + new_section)

    # Mark as delivered
    delivered_ids = {s["id"] for s in to_deliver}
    for sig in signals:
        if sig["id"] in delivered_ids:
            sig["delivered"] = True
            sig["delivered_ts"] = datetime.now(timezone.utc).isoformat()

    save_signals(signals)
    log(f"Delivered {len(to_deliver)} alerts to {ALERTS_FILE}")


if __name__ == "__main__":
    deliver()
