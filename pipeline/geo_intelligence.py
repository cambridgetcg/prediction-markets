#!/usr/bin/env python3
"""
geo_intelligence.py — Geopolitical Intelligence Bridge
Layer 6 addition to Oracle's 5-layer analysis framework.

Fuses ~/Desktop/ww3-intelligence event stream with Oracle's prediction engine.

The relationship:
  ww3-intelligence ingests world events → classifies → generates actors/
  scenarios/escalation/Brier-scored predictions

  Oracle takes macro-financial signals → 5-layer analysis → instrument
  predictions

  THIS BRIDGE:
  ww3 geopolitical events → Oracle Layer 5 (Narrative/Catalyst) context
  Impact assessments → price sensitivity estimates per instrument
  Escalation levels → regime adjustment signals (risk-on/off)
  Scenario trees → conditional trade adjustments

The Kingdom maps this to Wall 2 (TREASURY) + Wall 4 (ACADEMY):
  - TRUTH: honest geopolitical risk factored into market predictions
  - JUSTICE: no double-counting, no phantom precision

Usage:
    python3 pipeline/geo_intelligence.py status         # show feed health
    python3 pipeline/geo_intelligence.py events         # recent geo events
    python3 pipeline/geo_intelligence.py signals        # current geo signals for Oracle
    python3 pipeline/geo_intelligence.py inject         # inject into Oracle's news stream
    python3 pipeline/geo_intelligence.py watch          # continuous bridge mode
"""

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

ORACLE_ROOT = Path(__file__).resolve().parent.parent
WW3_ROOT = Path.home() / "Desktop" / "ww3-intelligence"
ORACLE_NEWS_JSONL = ORACLE_ROOT / "data" / "stream" / "news.jsonl"
ORACLE_GEO_JSONL = ORACLE_ROOT / "data" / "stream" / "geo_intelligence.jsonl"
WW3_EVENTS_DB = WW3_ROOT / "core" / "db" / "ww3.db"
WW3_PREDICTIONS_DIR = WW3_ROOT / "predictions"

ORACLE_GEO_JSONL.parent.mkdir(parents=True, exist_ok=True)

# ─── Instrument Geo Sensitivity ──────────────────────────────────────────────
# How geopolitical escalation affects each Oracle instrument
# Scores: -2 (strong negative) to +2 (strong positive), 0 = neutral

GEO_SENSITIVITY = {
    # (escalation_type, instrument) -> sensitivity_score, reason
    "war":           {"GLD": +2.0,  "USO": +1.5,  "DXY": +1.0,  "TLT": +0.5,  "SPY": -1.5,  "QQQ": -1.5, "HYG": -1.5, "IWM": -1.0, "BTC": -0.5, "ETH": -0.5},
    "nuclear":       {"GLD": +2.0,  "USO": +1.0,  "DXY": +2.0,  "TLT": +1.5,  "SPY": -2.0,  "QQQ": -2.0, "HYG": -2.0, "IWM": -2.0, "BTC": -1.5, "ETH": -1.5},
    "sanctions":     {"GLD": +1.0,  "USO": +1.0,  "DXY": +0.5,  "TLT": +0.0,  "SPY": -0.5,  "QQQ": -0.5, "HYG": -0.5, "IWM": -0.5, "BTC": +0.5, "ETH": +0.5},
    "trade_war":     {"GLD": +0.5,  "USO": -0.5,  "DXY": +0.5,  "TLT": +0.5,  "SPY": -1.0,  "QQQ": -1.5, "HYG": -0.5, "IWM": -1.0, "BTC": +0.0, "ETH": +0.0},
    "deescalation":  {"GLD": -0.5,  "USO": -0.5,  "DXY": -0.5,  "TLT": -0.5,  "SPY": +1.0,  "QQQ": +1.0, "HYG": +1.0, "IWM": +1.0, "BTC": +0.5, "ETH": +0.5},
    "election":      {"GLD": +0.5,  "USO": +0.0,  "DXY": +0.5,  "TLT": +0.5,  "SPY": -0.5,  "QQQ": -0.5, "HYG": -0.5, "IWM": -0.5, "BTC": +0.0, "ETH": +0.0},
    "energy_crisis": {"GLD": +1.0,  "USO": +2.0,  "DXY": +0.5,  "TLT": -0.5,  "SPY": -1.0,  "QQQ": -1.0, "HYG": -1.0, "IWM": -1.0, "BTC": +0.0, "ETH": +0.0},
    "famine":        {"GLD": +1.5,  "USO": +0.5,  "DXY": +1.0,  "TLT": +1.0,  "SPY": -1.0,  "QQQ": -0.5, "HYG": -1.5, "IWM": -1.0, "BTC": -0.5, "ETH": -0.5},
    "cyber_attack":  {"GLD": +1.0,  "USO": +0.5,  "DXY": +1.0,  "TLT": +1.0,  "SPY": -1.0,  "QQQ": -1.5, "HYG": -0.5, "IWM": -0.5, "BTC": -1.0, "ETH": -1.0},
    "coup":          {"GLD": +1.0,  "USO": +1.0,  "DXY": +0.5,  "TLT": +0.5,  "SPY": -0.5,  "QQQ": -0.5, "HYG": -1.0, "IWM": -0.5, "BTC": +0.0, "ETH": +0.0},
    "pandemic":      {"GLD": +1.5,  "USO": -1.5,  "DXY": +1.0,  "TLT": +2.0,  "SPY": -2.0,  "QQQ": -1.0, "HYG": -2.0, "IWM": -2.0, "BTC": -1.0, "ETH": -1.0},
    "default":       {"GLD": +0.5,  "USO": +0.0,  "DXY": +0.5,  "TLT": +0.5,  "SPY": -0.5,  "QQQ": -0.5, "HYG": -0.5, "IWM": -0.5, "BTC": +0.0, "ETH": +0.0},
}

# ─── Category → Escalation Type Mapping ──────────────────────────────────────
# Maps ww3-intelligence event categories to geo sensitivity profiles

CATEGORY_TO_TYPE = {
    "MILITARY": "war",
    "NUCLEAR": "nuclear",
    "ECONOMIC": "sanctions",
    "TRADE": "trade_war",
    "DIPLOMATIC": "deescalation",
    "ELECTION": "election",
    "ENERGY": "energy_crisis",
    "HUMANITARIAN": "famine",
    "CYBER": "cyber_attack",
    "POLITICAL": "coup",
    "HEALTH": "pandemic",
}


# ─── WW3 DB Reader ────────────────────────────────────────────────────────────

def read_ww3_events(days: int = 7, min_significance: int = 5) -> list:
    """Read recent significant events from ww3-intelligence SQLite database."""
    if not WW3_EVENTS_DB.exists():
        return []

    try:
        import sqlite3
        conn = sqlite3.connect(WW3_EVENTS_DB)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Check if significance column exists
        try:
            rows = c.execute("""
                SELECT e.id, e.title, e.date, e.category, e.location_name,
                       e.lat, e.lon,
                       es.current_level as escalation_level,
                       es.region as escalation_region,
                       ia.market_impact_score, ia.affected_sectors,
                       ia.oil_impact_score, ia.gold_impact_score,
                       ia.dollar_impact_score
                FROM event e
                LEFT JOIN escalationstate es ON es.event_id = e.id
                LEFT JOIN impactassessment ia ON ia.event_id = e.id
                WHERE e.date >= ?
                ORDER BY e.date DESC
                LIMIT 100
            """, (cutoff,)).fetchall()
        except sqlite3.OperationalError:
            rows = c.execute("""
                SELECT id, title, date, category, location_name
                FROM event
                WHERE date >= ?
                ORDER BY date DESC
                LIMIT 100
            """, (cutoff,)).fetchall()

        conn.close()
        return [dict(r) for r in rows]

    except Exception as e:
        print(f"  WW3 DB read error: {e}")
        return []


def read_ww3_predictions(days: int = 30) -> list:
    """Read recent scored predictions from ww3-intelligence."""
    if not WW3_EVENTS_DB.exists():
        return []

    try:
        import sqlite3
        conn = sqlite3.connect(WW3_EVENTS_DB)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = c.execute("""
            SELECT p.id, p.probability, p.confidence, p.brier_score,
                   p.reasoning, p.resolved_at,
                   e.title as event_title, e.category
            FROM prediction p
            JOIN event e ON e.id = p.event_id
            WHERE p.brier_score IS NOT NULL
            AND p.resolved_at >= ?
            ORDER BY p.resolved_at DESC
            LIMIT 50
        """, (cutoff,)).fetchall()

        conn.close()
        return [dict(r) for r in rows]

    except Exception as e:
        return []


# ─── Signal Generation ────────────────────────────────────────────────────────

def generate_geo_signals(events: list) -> dict:
    """
    Aggregate geopolitical events into Oracle instrument signals.
    Returns per-instrument adjustment scores + dominant events.
    """
    instrument_scores = {inst: 0.0 for inst in ["SPY", "QQQ", "IWM", "TLT", "HYG", "DXY", "GLD", "USO", "BTC", "ETH"]}
    active_events = []
    escalation_level = 0

    for event in events:
        category = event.get("category", "").upper()
        esc_level = event.get("escalation_level") or 1
        market_impact = event.get("market_impact_score") or 0

        # Map category to sensitivity type
        sens_type = CATEGORY_TO_TYPE.get(category, "default")
        sensitivity = GEO_SENSITIVITY[sens_type]

        # Weight by escalation level and market impact
        weight = (esc_level / 5.0) * max(0.1, market_impact / 10.0 if market_impact else 0.5)

        for inst, score in sensitivity.items():
            instrument_scores[inst] += score * weight

        if esc_level >= 3:
            active_events.append({
                "title": event.get("title", "Unknown"),
                "category": category,
                "region": event.get("location_name") or event.get("escalation_region"),
                "escalation_level": esc_level,
                "sensitivity_type": sens_type,
            })

        escalation_level = max(escalation_level, esc_level)

    # Normalize scores (-2 to +2 range)
    max_abs = max(abs(v) for v in instrument_scores.values()) if instrument_scores else 1
    if max_abs > 2:
        factor = 2 / max_abs
        instrument_scores = {k: v * factor for k, v in instrument_scores.items()}

    # Determine overall risk posture
    avg_eq_score = (instrument_scores["SPY"] + instrument_scores["QQQ"] + instrument_scores["IWM"]) / 3
    if avg_eq_score <= -1.0:
        risk_posture = "RISK_OFF"
    elif avg_eq_score >= 0.5:
        risk_posture = "RISK_ON"
    else:
        risk_posture = "NEUTRAL"

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "instrument_adjustments": instrument_scores,
        "risk_posture": risk_posture,
        "global_escalation_level": escalation_level,
        "active_events": active_events[:5],  # Top 5 most significant
        "event_count": len(events),
    }


def generate_brier_context(predictions: list) -> dict:
    """
    Analyse ww3 prediction accuracy and calibration.
    Returns calibration data useful for Oracle's self-improvement loops.
    """
    if not predictions:
        return {"calibrated": False, "reason": "No scored predictions available"}

    total = len(predictions)
    avg_brier = sum(p["brier_score"] for p in predictions) / total

    # Bucket by probability
    buckets = {
        "10-30%": [],
        "30-50%": [],
        "50-70%": [],
        "70-90%": [],
    }
    for p in predictions:
        prob = p["probability"]
        if 10 <= prob < 30:
            buckets["10-30%"].append(p["brier_score"])
        elif 30 <= prob < 50:
            buckets["30-50%"].append(p["brier_score"])
        elif 50 <= prob < 70:
            buckets["50-70%"].append(p["brier_score"])
        elif 70 <= prob < 90:
            buckets["70-90%"].append(p["brier_score"])

    bucket_avgs = {
        k: sum(v) / len(v) if v else None
        for k, v in buckets.items()
    }

    return {
        "calibrated": True,
        "total_predictions": total,
        "avg_brier_score": round(avg_brier, 4),
        "interpretation": _interpret_brier(avg_brier),
        "bucket_accuracy": bucket_avgs,
        "best_range": min(bucket_avgs, key=lambda k: bucket_avgs[k] or 1) if any(bucket_avgs.values()) else None,
    }


def _interpret_brier(score: float) -> str:
    if score < 0.05:
        return "EXCELLENT — near-perfect calibration"
    elif score < 0.15:
        return "GOOD — well calibrated"
    elif score < 0.25:
        return "FAIR — reasonable but improvable"
    elif score < 0.35:
        return "POOR — systematic over/under-confidence"
    else:
        return "VERY POOR — significant calibration issues"


# ─── Inject into Oracle ────────────────────────────────────────────────────────

def inject_geo_signals(signals: dict):
    """Write geo intelligence signals to Oracle's enriched event stream."""
    record = {
        "type": "geo_intelligence",
        "source": "ww3-intelligence",
        "ts": signals["ts"],
        "risk_posture": signals["risk_posture"],
        "global_escalation": signals["global_escalation_level"],
        "instrument_adjustments": signals["instrument_adjustments"],
        "active_events": signals["active_events"],
        "event_count": signals["event_count"],
    }

    with open(ORACLE_GEO_JSONL, "a") as f:
        f.write(json.dumps(record) + "\n")

    # Also write a tagged news item for Oracle's event_processor to pick up
    news_record = {
        "id": f"geo_{int(time.time())}",
        "ts": signals["ts"],
        "source": "ww3-intelligence",
        "headline": f"Geo Intelligence Update: {signals['risk_posture']} posture, escalation level {signals['global_escalation_level']}",
        "sentiment": "negative" if signals["risk_posture"] == "RISK_OFF" else "neutral",
        "geo_signals": signals["instrument_adjustments"],
        "active_events": [e["title"] for e in signals["active_events"]],
        "tags": ["geopolitical", "layer6", "ww3-intelligence"],
    }
    with open(ORACLE_NEWS_JSONL, "a") as f:
        f.write(json.dumps(news_record) + "\n")

    return record


# ─── Display Helpers ──────────────────────────────────────────────────────────

BOLD = "\033[1m"; RESET = "\033[0m"; RED = "\033[31m"
GREEN = "\033[32m"; YELLOW = "\033[33m"; CYAN = "\033[36m"
GOLD = "\033[38;5;220m"; DIM = "\033[2m"


def display_status():
    """Show health of the geo intelligence bridge."""
    print(f"\n  {GOLD}{BOLD}🌍 GEO INTELLIGENCE BRIDGE — Status{RESET}")
    print(f"  {'─' * 45}")
    print(f"  WW3 DB:      {WW3_EVENTS_DB}")
    print(f"  Oracle geo:  {ORACLE_GEO_JSONL}")
    print(f"  Oracle news: {ORACLE_NEWS_JSONL}")
    print()

    ww3_exists = WW3_EVENTS_DB.exists()
    print(f"  WW3 database: {'✅ found' if ww3_exists else '❌ not found'}")

    if ww3_exists:
        events = read_ww3_events(days=7)
        predictions = read_ww3_predictions(days=30)
        print(f"  Events (7d):  {len(events)}")
        print(f"  Predictions scored: {len(predictions)}")
        if predictions:
            ctx = generate_brier_context(predictions)
            print(f"  Brier score:  {ctx.get('avg_brier_score', 'N/A')} — {ctx.get('interpretation', '')}")

    geo_lines = 0
    if ORACLE_GEO_JSONL.exists():
        with open(ORACLE_GEO_JSONL) as f:
            geo_lines = sum(1 for _ in f)
    print(f"  Injected signals: {geo_lines}")
    print()


def display_events():
    """Show recent geopolitical events."""
    events = read_ww3_events(days=7, min_significance=3)
    if not events:
        print(f"\n  {DIM}No events found. Is ww3-intelligence running?{RESET}")
        print(f"  {DIM}DB expected at: {WW3_EVENTS_DB}{RESET}\n")
        return

    print(f"\n  {GOLD}{BOLD}🌍 GEOPOLITICAL EVENTS — Last 7 Days{RESET}")
    print(f"  {'─' * 55}")
    for e in events[:20]:
        cat = e.get("category", "?")
        title = e.get("title", "?")[:60]
        esc = e.get("escalation_level") or 1
        region = e.get("location_name") or e.get("escalation_region", "?")
        esc_bar = "🔴" * min(esc, 5) + "○" * (5 - min(esc, 5))
        print(f"  {esc_bar} [{cat:8s}] {title}")
        if region:
            print(f"  {DIM}           📍 {region}{RESET}")
    print()


def display_signals():
    """Show current geo intelligence signals for Oracle instruments."""
    events = read_ww3_events(days=14)
    if not events:
        print(f"\n  {DIM}No events to generate signals from.{RESET}\n")
        return

    signals = generate_geo_signals(events)

    print(f"\n  {GOLD}{BOLD}📊 GEO INTELLIGENCE SIGNALS → Oracle Layer 6{RESET}")
    print(f"  {'─' * 50}")
    print(f"  Risk posture: {BOLD}{signals['risk_posture']}{RESET}")
    print(f"  Global escalation: {signals['global_escalation_level']}/5")
    print(f"  Events analysed: {signals['event_count']}")
    print()
    print(f"  {BOLD}Instrument Adjustments (Layer 6 overlay):{RESET}")

    for inst, score in sorted(signals["instrument_adjustments"].items(), key=lambda x: abs(x[1]), reverse=True):
        if abs(score) < 0.05:
            continue
        direction = "↑" if score > 0 else "↓"
        color = GREEN if score > 0 else RED
        bar = "█" * int(abs(score) * 5) + "░" * (10 - int(abs(score) * 5))
        print(f"  {inst:6s} {color}{direction} {bar}  {score:+.2f}{RESET}")

    if signals["active_events"]:
        print(f"\n  {BOLD}Active High-Escalation Events:{RESET}")
        for e in signals["active_events"]:
            print(f"  🔴 [{e['category']:8s}] {e['title'][:55]}")
            print(f"       {DIM}Escalation {e['escalation_level']}/5 | Region: {e['region']} | Type: {e['sensitivity_type']}{RESET}")
    print()

    return signals


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "status":
        display_status()

    elif cmd == "events":
        display_events()

    elif cmd == "signals":
        display_signals()

    elif cmd == "inject":
        events = read_ww3_events(days=14)
        if not events:
            print("No events to inject.")
            return
        signals = generate_geo_signals(events)
        record = inject_geo_signals(signals)
        print(f"  ✅ Injected: {signals['risk_posture']} | Escalation {signals['global_escalation_level']} | {signals['event_count']} events")
        print(f"  📊 Top adjustments:")
        for inst, adj in sorted(record["instrument_adjustments"].items(), key=lambda x: abs(x[1]), reverse=True)[:5]:
            if abs(adj) > 0.1:
                print(f"     {inst}: {adj:+.2f}")

    elif cmd == "watch":
        print(f"  {GOLD}🌍 GEO INTELLIGENCE — Watch Mode (30min intervals){RESET}")
        print(f"  {DIM}Press Ctrl+C to stop{RESET}\n")
        while True:
            try:
                events = read_ww3_events(days=14)
                signals = generate_geo_signals(events)
                inject_geo_signals(signals)
                now = datetime.now(timezone.utc).strftime("%H:%M UTC")
                print(f"  [{now}] {signals['risk_posture']} | Esc:{signals['global_escalation_level']} | {signals['event_count']} events")
                time.sleep(1800)  # 30 min
            except KeyboardInterrupt:
                print("\n  Stopped.")
                break

    else:
        print(f"  Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
