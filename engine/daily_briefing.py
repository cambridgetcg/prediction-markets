#!/usr/bin/env python3
"""
daily_briefing.py — Morning intelligence briefing for the prediction engine.

Pulls together:
- Active predictions (unresolved)
- Oracle signals (pending)
- Top Polymarket opportunities (spike detector output)
- Key events to watch today
- Portfolio state

Usage:
    python3 engine/daily_briefing.py
    python3 engine/daily_briefing.py --full  # include scenario trees
"""

import json
import sys
import subprocess
import os
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CALIBRATION_DIR = BASE_DIR / "calibration"
SCRIPTS_DIR = BASE_DIR / "scripts"
BANKROLL_DIR = BASE_DIR / "bankroll"

PYTHON = "/opt/homebrew/bin/python3"

def load_active_predictions() -> list:
    pred_file = CALIBRATION_DIR / "predictions.jsonl"
    if not pred_file.exists():
        return []
    preds = []
    for line in pred_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            p = json.loads(line)
            if p.get("resolved") is None:
                preds.append(p)
        except Exception:
            pass
    return preds

def load_oracle_signals() -> dict:
    status_file = DATA_DIR / "oracle-status.json"
    signals_file = DATA_DIR / "pending-signals.json"
    status = {}
    signals = []
    if status_file.exists():
        status = json.loads(status_file.read_text())
    if signals_file.exists():
        signals = json.loads(signals_file.read_text()).get("signals", [])
    return {"status": status, "signals": signals}

def run_spike_detector() -> str:
    """Run spike detector and return top signals."""
    try:
        result = subprocess.run(
            [PYTHON, str(SCRIPTS_DIR / "spike-detector.py")],
            capture_output=True, text=True, timeout=60,
            cwd=str(BASE_DIR)
        )
        lines = result.stdout.splitlines()
        # Extract just the signal summaries (compact)
        signals = []
        for i, line in enumerate(lines):
            if "TRADE:" in line or ("YES=" in line and "Score:" in line):
                signals.append(line.strip())
        return "\n".join(signals[:6]) if signals else "No spikes detected"
    except Exception as e:
        return f"Spike detector error: {e}"

def load_bankroll() -> dict:
    state_file = BANKROLL_DIR / "state.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {}

def generate_briefing(full: bool = False) -> str:
    now = datetime.now(timezone.utc)
    lines = []
    lines.append(f"\n{'═'*60}")
    lines.append(f"📊 FUTURE PREDICTION ENGINE — DAILY BRIEFING")
    lines.append(f"   {now.strftime('%A, %B %d, %Y — %H:%M UTC')}")
    lines.append(f"{'═'*60}\n")

    # Oracle status
    oracle = load_oracle_signals()
    ost = oracle["status"]
    last_run = ost.get("last_run", "?")[:16].replace("T", " ")
    lines.append(f"── Oracle Status ──")
    lines.append(f"  Last run: {last_run} UTC | Signals total: {ost.get('signals_total', 0)}")
    undelivered = [s for s in oracle["signals"] if not s.get("delivered", False)]
    if undelivered:
        lines.append(f"  ⚡ {len(undelivered)} undelivered signal(s):")
        for s in undelivered[:3]:
            lines.append(f"    [{s.get('domain','?')}] {s.get('market','?')[:50]} | {s.get('trade','?')} | score={s.get('score','?')}")
    lines.append("")

    # Active predictions
    preds = load_active_predictions()
    lines.append(f"── Active Predictions ({len(preds)}) ──")
    if preds:
        for p in sorted(preds, key=lambda x: x.get("resolution_date") or "9999", reverse=False)[:5]:
            domain = p.get("domain", "?")
            q = p.get("question", "?")[:55]
            est = p.get("my_estimate", 0)
            rd = (p.get("resolution_date") or "?")[:10]
            lines.append(f"  [{domain}] {q}...")
            lines.append(f"    My estimate: {est:.0%} | Resolves: {rd}")
    else:
        lines.append("  No active predictions.")
    lines.append("")

    # Spike detector
    lines.append(f"── Market Opportunities (S004 Spike Detector) ──")
    spikes = run_spike_detector()
    for line in spikes.splitlines():
        lines.append(f"  {line}")
    lines.append("")

    # Bankroll
    br = load_bankroll()
    if br:
        lines.append(f"── Bankroll ──")
        lines.append(f"  Current: ${br.get('current_bankroll_usd',0):.2f} | P&L: ${br.get('total_pnl_usd',0):.2f} ({br.get('total_pnl_pct',0):.1f}%)")
        lines.append(f"  Status: {br.get('status','?')} | Trades: {br.get('trades_total',0)}")
        lines.append("")

    lines.append(f"── To Synthesise ──")
    lines.append(f"  python3 engine/synthesise.py \"your question here\"")
    lines.append(f"  python3 engine/scenario_tree.py \"triggering event\"")
    lines.append(f"  python3 engine/decision_engine.py  # trade recommendations")
    lines.append(f"\n{'─'*60}\n")

    return "\n".join(lines)


if __name__ == "__main__":
    full = "--full" in sys.argv
    print(generate_briefing(full=full))
