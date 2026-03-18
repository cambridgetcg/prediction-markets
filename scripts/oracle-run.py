#!/usr/bin/env python3
"""
Oracle Run — Automated signal generation engine for the Kingdom.

Runs spike-detector (and whale-activity-scanner if available) on schedule,
writes discovered signals to data/pending-signals.json, logs all runs.

Usage:
    python3 scripts/oracle-run.py          # Single run
    python3 scripts/oracle-run.py --loop   # Continuous (spike every 30m, whale every 15m)
"""

import json
import subprocess
import sys
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SCRIPTS_DIR = BASE_DIR / "scripts"
SIGNALS_FILE = DATA_DIR / "pending-signals.json"
STATUS_FILE = DATA_DIR / "oracle-status.json"
LOG_FILE = DATA_DIR / "oracle-run.log"
WHALE_SCANNER = SCRIPTS_DIR / "whale-activity-scanner.py"
GEO_BRIDGE = BASE_DIR / "pipeline" / "geo_intelligence.py"


def log(msg):
    """Log a timestamped message to stdout (captured by cron redirect)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def load_signals():
    """Load existing signals from pending-signals.json."""
    if SIGNALS_FILE.exists():
        try:
            with open(SIGNALS_FILE) as f:
                data = json.load(f)
            return data.get("signals", [])
        except (json.JSONDecodeError, KeyError):
            return []
    return []


def save_signals(signals):
    """Save signals to pending-signals.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SIGNALS_FILE, "w") as f:
        json.dump({"signals": signals}, f, indent=2)


def make_signal_id(market_question, trade, ts_date):
    """Generate a deterministic signal ID to avoid duplicates."""
    raw = f"{market_question}|{trade}|{ts_date}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def run_spike_detector():
    """Run spike-detector.py --json and parse output into signals."""
    log("Running spike-detector...")
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "spike-detector.py"), "--json"],
            capture_output=True, text=True, timeout=120,
            cwd=str(BASE_DIR)
        )
        if result.returncode != 0:
            log(f"  spike-detector failed (rc={result.returncode}): {result.stderr[:200]}")
            return []

        if not result.stdout.strip():
            log("  spike-detector returned empty output")
            return []

        spikes = json.loads(result.stdout)
        log(f"  spike-detector found {len(spikes)} spikes")
        return spikes

    except subprocess.TimeoutExpired:
        log("  spike-detector timed out (120s)")
        return []
    except json.JSONDecodeError as e:
        log(f"  spike-detector JSON parse error: {e}")
        return []
    except Exception as e:
        log(f"  spike-detector unexpected error: {e}")
        return []


def run_whale_scanner():
    """Run whale-activity-scanner.py --json if it exists."""
    if not WHALE_SCANNER.exists():
        log("Whale scanner not found — skipping")
        return []

    log("Running whale-activity-scanner...")
    try:
        result = subprocess.run(
            [sys.executable, str(WHALE_SCANNER), "--json", "--min-score", "4"],
            capture_output=True, text=True, timeout=120,
            cwd=str(BASE_DIR)
        )
        if result.returncode != 0:
            log(f"  whale-scanner failed (rc={result.returncode}): {result.stderr[:200]}")
            return []

        if not result.stdout.strip():
            log("  whale-scanner returned empty output")
            return []

        alerts = json.loads(result.stdout)
        log(f"  whale-scanner found {len(alerts)} alerts")
        return alerts

    except subprocess.TimeoutExpired:
        log("  whale-scanner timed out (120s)")
        return []
    except json.JSONDecodeError as e:
        log(f"  whale-scanner JSON parse error: {e}")
        return []
    except Exception as e:
        log(f"  whale-scanner unexpected error: {e}")
        return []


def spikes_to_signals(spikes):
    """Convert spike-detector output to signal format."""
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    signals = []

    for spike in spikes:
        # Only FADE and HALF-SIZE are actionable
        if spike.get("s004_signal") == "SKIP":
            continue

        question = spike.get("question", "")
        domain = spike.get("domain", "OTHER")
        yes_price = spike.get("yes_price", 0.5)
        magnitude = spike.get("max_magnitude", 0)
        classification = spike.get("classification", "UNKNOWN")
        s004_signal = spike.get("s004_signal", "SKIP")
        e_score = spike.get("emotional_score", 0)
        s_score = spike.get("structural_score", 0)

        # Determine trade direction
        spike_types = spike.get("spike_types", [])
        has_positive = any(v > 0 for _, v in spike_types)

        if s004_signal == "FADE":
            if has_positive:
                trade = f"BUY NO at {1 - yes_price:.1%}"
                target = f"YES drops to {max(yes_price - magnitude * 0.40, 0.01):.1%}"
                stop = f"YES rises to {min(yes_price + 0.08, 0.99):.1%}"
            else:
                trade = f"BUY YES at {yes_price:.1%}"
                target = f"YES rises to {min(yes_price + magnitude * 0.40, 0.99):.1%}"
                stop = f"YES drops to {max(yes_price - 0.08, 0.01):.1%}"
        else:  # HALF-SIZE
            if has_positive:
                trade = f"HALF-SIZE NO at {1 - yes_price:.1%}"
                target = f"YES drops to {max(yes_price - magnitude * 0.30, 0.01):.1%}"
                stop = f"YES rises to {min(yes_price + 0.06, 0.99):.1%}"
            else:
                trade = f"HALF-SIZE YES at {yes_price:.1%}"
                target = f"YES rises to {min(yes_price + magnitude * 0.30, 0.99):.1%}"
                stop = f"YES drops to {max(yes_price - 0.06, 0.01):.1%}"

        # Composite score: emotional advantage (0-10 scale)
        score = min(e_score + max(e_score - s_score, 0) + int(magnitude >= 0.20) * 2, 10)
        # Minimum score of 3 for FADE, 2 for HALF-SIZE
        if s004_signal == "FADE":
            score = max(score, 3)
        else:
            score = max(score, 2)

        signal_id = make_signal_id(question, trade, today)

        signals.append({
            "id": signal_id,
            "type": "FADE" if s004_signal == "FADE" else "HALF",
            "source": "spike-detector",
            "market": question,
            "domain": domain,
            "trade": trade,
            "target": target,
            "stop": stop,
            "score": score,
            "magnitude": round(magnitude, 4),
            "classification": classification,
            "notes": spike.get("notes", []),
            "ts": now,
            "delivered": False,
        })

    return signals


def whale_alerts_to_signals(alerts):
    """Convert whale-scanner output to signal format."""
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    signals = []

    for alert in alerts:
        question = alert.get("market", alert.get("question", ""))
        domain = alert.get("domain", "OTHER")
        score = alert.get("score", 0)
        direction = alert.get("direction", "UNKNOWN")

        if direction == "UNKNOWN":
            trade = f"MONITOR — whale active"
        else:
            trade = f"BACK {direction}"

        signal_id = make_signal_id(question, f"whale-{direction}", today)

        signals.append({
            "id": signal_id,
            "type": "BACK" if direction != "UNKNOWN" else "MONITOR",
            "source": "whale-scanner",
            "market": question,
            "domain": domain,
            "trade": trade,
            "target": "",
            "stop": "",
            "score": score,
            "magnitude": 0,
            "classification": "WHALE",
            "notes": [alert.get("reason", "")],
            "ts": now,
            "delivered": False,
        })

    return signals


def merge_signals(existing, new_signals):
    """Merge new signals into existing, avoiding duplicates by ID."""
    existing_ids = {s["id"] for s in existing}
    added = 0
    for sig in new_signals:
        if sig["id"] not in existing_ids:
            existing.append(sig)
            existing_ids.add(sig["id"])
            added += 1
    return existing, added


def update_status(signals):
    """Update oracle-status.json."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat()

    # Load existing status for uptime_since
    uptime_since = now
    if STATUS_FILE.exists():
        try:
            with open(STATUS_FILE) as f:
                old = json.load(f)
            uptime_since = old.get("uptime_since", now)
        except (json.JSONDecodeError, KeyError):
            pass

    today_signals = [s for s in signals if s["ts"].startswith(today)]
    delivered = [s for s in signals if s.get("delivered")]

    status = {
        "last_run": now,
        "signals_today": len(today_signals),
        "signals_delivered": len(delivered),
        "signals_total": len(signals),
        "status": "live",
        "uptime_since": uptime_since,
    }

    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)


def run_geo_inject():
    """Run geo intelligence bridge inject if available."""
    if not GEO_BRIDGE.exists():
        log("Geo bridge not found — skipping Layer 6")
        return

    log("Running geo intelligence inject...")
    try:
        result = subprocess.run(
            [sys.executable, str(GEO_BRIDGE), "inject"],
            capture_output=True, text=True, timeout=60,
            cwd=str(BASE_DIR)
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "not found" in stderr or "No events" in result.stdout:
                log("  WW3 bridge inactive — no DB")
            else:
                log(f"  Geo inject failed (rc={result.returncode}): {stderr[:200]}")
        else:
            out = result.stdout.strip()
            if out:
                log(f"  Geo inject: {out[:120]}")
            else:
                log("  Geo inject: done (no output)")
    except subprocess.TimeoutExpired:
        log("  Geo inject timed out (60s)")
    except Exception as e:
        log(f"  Geo inject error: {e}")


def run_once():
    """Execute one full Oracle cycle."""
    log("=== Oracle run starting ===")

    # Layer 6: Geo intelligence inject (before detectors)
    run_geo_inject()

    # Load existing signals
    signals = load_signals()
    log(f"Loaded {len(signals)} existing signals")

    # Run detectors
    spikes = run_spike_detector()
    new_spike_signals = spikes_to_signals(spikes)
    signals, spike_added = merge_signals(signals, new_spike_signals)
    log(f"  Spike signals: {len(new_spike_signals)} found, {spike_added} new")

    whale_alerts = run_whale_scanner()
    new_whale_signals = whale_alerts_to_signals(whale_alerts)
    signals, whale_added = merge_signals(signals, new_whale_signals)
    log(f"  Whale signals: {len(new_whale_signals)} found, {whale_added} new")

    # Save
    save_signals(signals)
    update_status(signals)

    total_new = spike_added + whale_added
    log(f"=== Oracle run complete: {total_new} new signals, {len(signals)} total ===")
    return total_new


def run_loop():
    """Run continuously — spike every 30m, whale every 15m."""
    import time
    log("=== Oracle entering continuous mode ===")
    cycle = 0
    while True:
        try:
            cycle += 1
            # Whale runs every cycle (15m), spike every 2nd cycle (30m)
            signals = load_signals()

            if cycle % 2 == 0:
                spikes = run_spike_detector()
                new_spike_signals = spikes_to_signals(spikes)
                signals, added = merge_signals(signals, new_spike_signals)
                log(f"  [cycle {cycle}] Spike: {added} new signals")

            whale_alerts = run_whale_scanner()
            new_whale_signals = whale_alerts_to_signals(whale_alerts)
            signals, added = merge_signals(signals, new_whale_signals)
            log(f"  [cycle {cycle}] Whale: {added} new signals")

            save_signals(signals)
            update_status(signals)

            log(f"  Sleeping 15 minutes...")
            time.sleep(900)

        except KeyboardInterrupt:
            log("=== Oracle stopped by user ===")
            break
        except Exception as e:
            log(f"  ERROR in cycle {cycle}: {e}")
            time.sleep(60)  # Wait 1 min on error, then continue


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Oracle Run — Signal generation engine")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    args = parser.parse_args()

    if args.loop:
        run_loop()
    else:
        run_once()


if __name__ == "__main__":
    main()
