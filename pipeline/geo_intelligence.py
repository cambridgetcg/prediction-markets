#!/usr/bin/env python3
"""
geo_intelligence.py — Geopolitical Intelligence Bridge
Layer 6 addition to Oracle's 5-layer analysis framework.

"Layer 6" here is the geo layer. engine/DATA-SOURCES.md numbers its data
sources differently and calls betting markets "Layer 6"; see the naming note
there.

Reads the ww3-intelligence ledger named by WW3_DB_PATH (read-only) and turns
its recent events into Oracle geo signals.

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

What it reads: ww3's `event` rows, each with its newest `escalationstate` and
`impactassessment`. ww3 writes Event rows only when its model layer analyses an
observation (which may add both assessments), or when someone adds an event
by hand (with neither, so it is counted but moves nothing). Its scheduled
collection writes observations only, and the bridge does not turn observations
into signals, so a current ledger may hold no Event rows at all.
engine/DATA-SOURCES.md has the current status.

The Kingdom maps this to Wall 2 (TREASURY) + Wall 4 (ACADEMY):
  - TRUTH: honest geopolitical risk factored into market predictions
  - JUSTICE: no double-counting, no phantom precision

Usage:
    python3 pipeline/geo_intelligence.py status         # show feed health
    python3 pipeline/geo_intelligence.py events         # recent geo events
    python3 pipeline/geo_intelligence.py signals        # current geo signals for Oracle
    python3 pipeline/geo_intelligence.py inject         # inject into Oracle's news stream
    python3 pipeline/geo_intelligence.py watch          # continuous bridge mode

    WW3_DB_PATH=/path/to/ww3.db python3 pipeline/geo_intelligence.py status
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

ORACLE_ROOT = Path(__file__).resolve().parent.parent
ORACLE_NEWS_JSONL = ORACLE_ROOT / "data" / "stream" / "news.jsonl"
ORACLE_GEO_JSONL = ORACLE_ROOT / "data" / "stream" / "geo_intelligence.jsonl"

# The ww3 ledger to read. WW3_DB_PATH wins; unset, the bridge looks where the
# March 2026 copy of ww3 lived, which is the old default.
WW3_DB_ENV = "WW3_DB_PATH"
WW3_ROOT = Path.home() / "Desktop" / "ww3-intelligence"
DEFAULT_WW3_DB = WW3_ROOT / "core" / "db" / "ww3.db"

ORACLE_GEO_JSONL.parent.mkdir(parents=True, exist_ok=True)


def ww3_db_path() -> Path:
    """The ww3 ledger this bridge reads: $WW3_DB_PATH, else the old default."""
    value = os.environ.get(WW3_DB_ENV, "").strip()
    return Path(value).expanduser() if value else DEFAULT_WW3_DB


def ww3_db_source() -> str:
    return f"from {WW3_DB_ENV}" if os.environ.get(WW3_DB_ENV, "").strip() else f"default; {WW3_DB_ENV} is unset"


# ─── ww3 schema contract ──────────────────────────────────────────────────────
# The columns this bridge reads, as ww3-intelligence's core/db defines them
# (schema v2). They are checked before every read, so a ledger that has drifted
# fails with the missing names instead of quietly answering with fewer columns.

WW3_EVENT_COLUMNS = {
    "event": ("id", "title", "date", "category", "classification", "significance",
              "location_name", "lat", "lon"),
    "escalationstate": ("id", "event_id", "region", "current_level", "assessed_at"),
    "impactassessment": ("id", "event_id", "economic_global", "economic_regional",
                         "assessed_at"),
}
WW3_OBSERVATION_COLUMNS = {
    "observation": ("id", "fetched_at"),
}
WW3_PREDICTION_COLUMNS = {
    "event": ("id", "title", "category"),
    "prediction": ("id", "event_id", "probability", "confidence", "brier_score",
                   "reasoning", "resolved_at"),
}

# ww3's EscalationState.current_level runs 1-10. An event is "active" from the
# level at which engine/geo_layer starts to adjust a probability.
ESCALATION_SCALE = 10
ACTIVE_ESCALATION_MIN = 4

# Weight for an event with no ImpactAssessment row: the bridge's existing
# neutral factor. It is a weighting choice, not an assessment.
UNASSESSED_IMPACT_FACTOR = 0.5


class WW3LedgerError(RuntimeError):
    """The ww3 ledger is missing, unreadable, or lacks a column this bridge reads."""


def missing_db_message(db_path: Path) -> str:
    return (f"ww3 ledger not found at {db_path}. Set {WW3_DB_ENV} to a ww3 database "
            f"file, for example a restored copy of ww3's weekly export.")


def _connect_ww3(db_path: Path | None = None) -> sqlite3.Connection:
    db_path = db_path or ww3_db_path()
    if not db_path.is_file():
        raise WW3LedgerError(missing_db_message(db_path))
    # Read-only: the bridge never writes the ledger, and a restored copy stays as restored.
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            conn.execute("PRAGMA schema_version").fetchone()
        except sqlite3.OperationalError as first_error:
            conn.close()
            # ww3 keeps its database in WAL mode, and reading one needs a -shm file
            # beside it. In a directory this process cannot write, a copy without
            # one cannot get one. Nothing of ours can write such a copy (an
            # archived export), so it is read as immutable.
            if os.access(db_path, os.W_OK) and os.access(db_path.parent, os.W_OK):
                raise
            # An immutable read skips the -wal file. Committed rows still in one
            # would be missing with no error, so such a copy is refused instead.
            wal = Path(f"{db_path.resolve()}-wal")
            if wal.is_file() and wal.stat().st_size > 0:
                raise WW3LedgerError(
                    f"ww3 ledger at {db_path} has a non-empty {wal.name} beside it in a "
                    f"directory this process cannot write, and reading it from here would "
                    f"skip those rows. Copy the ledger and its -wal to a writable directory, "
                    f"or checkpoint it before archiving."
                ) from first_error
            conn = sqlite3.connect(f"{uri}&immutable=1", uri=True)
            conn.execute("PRAGMA schema_version").fetchone()
    except sqlite3.Error as exc:
        raise WW3LedgerError(f"ww3 ledger at {db_path} cannot be read: {exc}") from exc
    conn.row_factory = sqlite3.Row
    return conn


def missing_columns(conn: sqlite3.Connection, required: dict) -> list:
    """Return the required columns this ledger lacks, as "table.column"."""
    missing = []
    for table, columns in required.items():
        present = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
        if not present:
            missing.append(f"{table} (whole table)")
            continue
        missing.extend(f"{table}.{column}" for column in columns if column not in present)
    return missing


def missing_ledger_columns(conn: sqlite3.Connection) -> list:
    """Every column any read in this bridge needs, checked at once for `status`."""
    found = []
    for required in (WW3_EVENT_COLUMNS, WW3_OBSERVATION_COLUMNS, WW3_PREDICTION_COLUMNS):
        found.extend(missing_columns(conn, required))
    return list(dict.fromkeys(found))


def _require_columns(conn: sqlite3.Connection, required: dict, db_path: Path) -> None:
    missing = missing_columns(conn, required)
    if missing:
        raise WW3LedgerError(
            f"ww3 ledger at {db_path} does not match the schema this bridge reads; "
            f"missing {', '.join(missing)}"
        )


def _read(sql: str, params: tuple, required: dict, db_path: Path | None) -> list:
    db_path = db_path or ww3_db_path()
    conn = _connect_ww3(db_path)
    try:
        _require_columns(conn, required, db_path)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.Error as exc:
        raise WW3LedgerError(f"ww3 ledger read failed at {db_path}: {exc}") from exc
    finally:
        conn.close()


def _naive_utc(moment: datetime) -> datetime:
    """ww3 stores datetimes as naive UTC text; compare against the same."""
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


# ─── Instrument Geo Sensitivity ──────────────────────────────────────────────
# How geopolitical escalation affects each Oracle instrument
# Scores: -2 (strong negative) to +2 (strong positive), 0 = neutral
# These are the bridge author's priors, not fitted estimates. Only the profiles
# named in CATEGORY_TO_TYPE can be reached from ww3's current categories; the
# rest are kept for a finer event type that ww3 does not record today.

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
# Maps ww3-intelligence event categories to geo sensitivity profiles.
# ww3 records exactly these six (analysis/schema.py EVENT_CATEGORIES), lowercase.
# "political" spans elections, diplomacy and coups, and "seismic" and "other"
# name no market profile, so all three take the generic default rather than a
# sharper profile the category cannot support.

CATEGORY_TO_TYPE = {
    "military": "war",
    "cyber": "cyber_attack",
    "economic": "sanctions",
    "political": "default",
    "seismic": "default",
    "other": "default",
}


# ─── WW3 DB Reader ────────────────────────────────────────────────────────────

def read_ww3_events(days: int = 7, min_significance: int = 5, db_path: Path | None = None,
                    now: datetime | None = None) -> list:
    """Read recent significant events from the ww3-intelligence ledger.

    An event qualifies when its date falls on or after the cutoff day and its
    significance (ww3's 1-10) is at least min_significance. ww3 stores
    Event.date as a calendar date ('YYYY-MM-DD'), so the cutoff is a date too:
    an event dated on the cutoff day is included. Each event carries its newest
    EscalationState and ImpactAssessment, or None where ww3 recorded none.

    Raises WW3LedgerError when the ledger is missing or lacks a column read here.
    """
    now = now or datetime.now(timezone.utc)
    cutoff_date = (now - timedelta(days=days)).date().isoformat()
    return _read("""
        SELECT e.id, e.title, e.date, e.category, e.classification, e.significance,
               e.location_name, e.lat, e.lon,
               es.current_level AS escalation_level,
               es.region AS escalation_region,
               ia.economic_global, ia.economic_regional
        FROM event e
        LEFT JOIN escalationstate es ON es.id = (
            SELECT s.id FROM escalationstate s WHERE s.event_id = e.id
            ORDER BY s.assessed_at DESC, s.id DESC LIMIT 1)
        LEFT JOIN impactassessment ia ON ia.id = (
            SELECT a.id FROM impactassessment a WHERE a.event_id = e.id
            ORDER BY a.assessed_at DESC, a.id DESC LIMIT 1)
        WHERE e.date >= ? AND e.significance >= ?
        ORDER BY e.date DESC, e.id DESC
        LIMIT 100
    """, (cutoff_date, min_significance), WW3_EVENT_COLUMNS, db_path)


def read_ledger_as_of(db_path: Path | None = None) -> str | None:
    """The newest observation's fetched_at in the ledger, as UTC ISO text.

    This bounds how current anything derived from the ledger can be. None when
    the ledger holds no observations.
    """
    rows = _read("SELECT MAX(fetched_at) AS newest FROM observation", (),
                 WW3_OBSERVATION_COLUMNS, db_path)
    newest = rows[0]["newest"] if rows else None
    if not newest:
        return None
    try:
        parsed = datetime.fromisoformat(str(newest))
    except ValueError:
        raise WW3LedgerError(f"ww3 observation.fetched_at is not a timestamp: {newest!r}") from None
    # ww3 writes fetched_at as naive UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def count_ww3_rows(db_path: Path | None = None) -> dict:
    """Row counts for the tables that decide whether the bridge has anything to read."""
    counts = {}
    for table in ("event", "observation"):
        rows = _read(f'SELECT COUNT(*) AS n FROM "{table}"', (), {table: ("id",)}, db_path)
        counts[table] = rows[0]["n"]
    return counts


def read_ww3_predictions(days: int = 30, db_path: Path | None = None,
                         now: datetime | None = None) -> list:
    """Read recent scored predictions from ww3-intelligence."""
    now = now or datetime.now(timezone.utc)
    # ww3 stores resolved_at as naive UTC text ('YYYY-MM-DD HH:MM:SS[.ffffff]').
    cutoff = _naive_utc(now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    return _read("""
        SELECT p.id, p.probability, p.confidence, p.brier_score,
               p.reasoning, p.resolved_at,
               e.title as event_title, e.category
        FROM prediction p
        JOIN event e ON e.id = p.event_id
        WHERE p.brier_score IS NOT NULL
        AND p.resolved_at >= ?
        ORDER BY p.resolved_at DESC
        LIMIT 50
    """, (cutoff,), WW3_PREDICTION_COLUMNS, db_path)


# ─── Signal Generation ────────────────────────────────────────────────────────

def generate_geo_signals(events: list, ledger_as_of: str | None = None) -> dict:
    """
    Aggregate geopolitical events into Oracle instrument signals.
    Returns per-instrument adjustment scores + dominant events.

    Only events with an escalation assessment are weighted. One without is
    counted in event_count but moves nothing, since its level is unknown, not 1.
    global_escalation_level is the highest assessed level on ww3's 1-10 scale,
    or 0 when no event was assessed.
    """
    instrument_scores = {inst: 0.0 for inst in ["SPY", "QQQ", "IWM", "TLT", "HYG", "DXY", "GLD", "USO", "BTC", "ETH"]}
    active_events = []
    escalation_level = 0
    assessed = 0

    for event in events:
        category = (event.get("category") or "").lower()
        esc_level = event.get("escalation_level")
        # economic_global (1-10) is the nearest ww3 field to a market impact score.
        market_impact = event.get("economic_global")

        # Map category to sensitivity type
        sens_type = CATEGORY_TO_TYPE.get(category, "default")
        sensitivity = GEO_SENSITIVITY[sens_type]

        if esc_level is None:
            continue
        assessed += 1

        # Weight by escalation level and market impact
        if market_impact is not None:
            impact_factor = max(0.1, market_impact / 10.0)
        else:
            impact_factor = UNASSESSED_IMPACT_FACTOR
        weight = (esc_level / ESCALATION_SCALE) * impact_factor

        for inst, score in sensitivity.items():
            instrument_scores[inst] += score * weight

        if esc_level >= ACTIVE_ESCALATION_MIN:
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

    active_events.sort(key=lambda e: e["escalation_level"], reverse=True)

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ledger_as_of": ledger_as_of,
        "instrument_adjustments": instrument_scores,
        "risk_posture": risk_posture,
        "global_escalation_level": escalation_level,
        "active_events": active_events[:5],  # Top 5 most significant
        "event_count": len(events),
        "escalation_assessed": assessed,
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
        "ledger_as_of": signals.get("ledger_as_of"),
        "risk_posture": signals["risk_posture"],
        "global_escalation": signals["global_escalation_level"],
        "instrument_adjustments": signals["instrument_adjustments"],
        "active_events": signals["active_events"],
        "event_count": signals["event_count"],
        "escalation_assessed": signals.get("escalation_assessed"),
    }

    with open(ORACLE_GEO_JSONL, "a") as f:
        f.write(json.dumps(record) + "\n")

    # Also write a tagged news item. The event_processor it was meant for does not
    # exist in this repository, so nothing reads news.jsonl today.
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


def _escalation_bar(esc) -> str:
    if esc is None:
        return "·····"
    filled = min(5, (esc + 1) // 2)  # five cells, two levels each
    return "🔴" * filled + "○" * (5 - filled)


def display_status():
    """Show health of the geo intelligence bridge."""
    db_path = ww3_db_path()
    print(f"\n  {GOLD}{BOLD}🌍 GEO INTELLIGENCE BRIDGE — Status{RESET}")
    print(f"  {'─' * 45}")
    print(f"  WW3 DB:      {db_path} ({ww3_db_source()})")
    print(f"  Oracle geo:  {ORACLE_GEO_JSONL}")
    print(f"  Oracle news: {ORACLE_NEWS_JSONL}")
    print()

    if not db_path.is_file():
        print("  WW3 database: ❌ not found")
        print(f"  {missing_db_message(db_path)}")
    else:
        print("  WW3 database: ✅ found")
        try:
            conn = _connect_ww3(db_path)
            try:
                missing = missing_ledger_columns(conn)
            finally:
                conn.close()
            if missing:
                print(f"  Schema:       ❌ missing {', '.join(missing)}")
            else:
                print("  Schema:       ✅ has every column this bridge reads")
                counts = count_ww3_rows(db_path)
                print(f"  Ledger as of: {read_ledger_as_of(db_path) or 'no observations'}")
                print(f"  Observations: {counts['observation']} (not read as signals)")
                print(f"  Event rows:   {counts['event']}")
                if counts["event"] == 0:
                    print(f"  {DIM}ww3 writes Event rows only when its model layer runs or someone adds one by hand.{RESET}")
                events = read_ww3_events(days=7)
                predictions = read_ww3_predictions(days=30)
                print(f"  Events (7d, significance ≥5): {len(events)}")
                print(f"  Predictions scored (30d): {len(predictions)}")
                if predictions:
                    ctx = generate_brier_context(predictions)
                    print(f"  Brier score:  {ctx.get('avg_brier_score', 'N/A')} — {ctx.get('interpretation', '')}")
        except WW3LedgerError as exc:
            print(f"  ❌ {exc}")
        except sqlite3.Error as exc:
            print(f"  ❌ ww3 ledger at {db_path} cannot be read: {exc}")

    geo_lines = 0
    newest = None
    if ORACLE_GEO_JSONL.exists():
        with open(ORACLE_GEO_JSONL) as f:
            for line in f:
                if line.strip():
                    geo_lines += 1
                    newest = line
    print(f"  Injected signals: {geo_lines}")
    if newest:
        try:
            print(f"  Newest injected:  {json.loads(newest).get('ts', '?')} "
                  f"{DIM}(age check: python3 engine/geo_layer.py status){RESET}")
        except json.JSONDecodeError:
            print("  Newest injected:  unreadable line")
    print()


def display_events():
    """Show recent geopolitical events."""
    try:
        events = read_ww3_events(days=7, min_significance=3)
    except WW3LedgerError as exc:
        print(f"\n  {exc}\n")
        return
    if not events:
        print(f"\n  {DIM}No events with significance ≥3 dated in the last 7 days in {ww3_db_path()}.{RESET}")
        print(f"  {DIM}ww3 writes Event rows only when its model layer runs or someone adds one by hand.{RESET}\n")
        return

    print(f"\n  {GOLD}{BOLD}🌍 GEOPOLITICAL EVENTS — Last 7 Days{RESET}")
    print(f"  {'─' * 55}")
    for e in events[:20]:
        cat = e.get("category", "?")
        title = e.get("title", "?")[:60]
        esc = e.get("escalation_level")
        region = e.get("location_name") or e.get("escalation_region", "?")
        esc_str = f"{esc}/10" if esc is not None else "not assessed"
        print(f"  {_escalation_bar(esc)} [{cat:9s}] {title}  {DIM}esc {esc_str}{RESET}")
        if region:
            print(f"  {DIM}           📍 {region}{RESET}")
    print()


def display_signals():
    """Show current geo intelligence signals for Oracle instruments."""
    try:
        events = read_ww3_events(days=14)
        ledger_as_of = read_ledger_as_of()
    except WW3LedgerError as exc:
        print(f"\n  {exc}\n")
        return
    if not events:
        print(f"\n  {DIM}No events to generate signals from.{RESET}\n")
        return

    signals = generate_geo_signals(events, ledger_as_of=ledger_as_of)

    print(f"\n  {GOLD}{BOLD}📊 GEO INTELLIGENCE SIGNALS → Oracle Layer 6{RESET}")
    print(f"  {'─' * 50}")
    print(f"  Risk posture: {BOLD}{signals['risk_posture']}{RESET}")
    print(f"  Global escalation: {signals['global_escalation_level']}/10")
    print(f"  Events analysed: {signals['event_count']} ({signals['escalation_assessed']} with an escalation assessment)")
    print(f"  Ledger as of: {ledger_as_of or 'no observations'}")
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
            print(f"  🔴 [{e['category']:9s}] {e['title'][:55]}")
            print(f"       {DIM}Escalation {e['escalation_level']}/10 | Region: {e['region']} | Type: {e['sensitivity_type']}{RESET}")
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
        try:
            events = read_ww3_events(days=14)
            ledger_as_of = read_ledger_as_of()
        except WW3LedgerError as exc:
            print(f"  {exc}", file=sys.stderr)
            sys.exit(1)
        if not events:
            print("No events to inject.")
            return
        signals = generate_geo_signals(events, ledger_as_of=ledger_as_of)
        record = inject_geo_signals(signals)
        print(f"  ✅ Injected: {signals['risk_posture']} | Escalation {signals['global_escalation_level']}/10 | {signals['event_count']} events")
        print(f"  📊 Top adjustments:")
        for inst, adj in sorted(record["instrument_adjustments"].items(), key=lambda x: abs(x[1]), reverse=True)[:5]:
            if abs(adj) > 0.1:
                print(f"     {inst}: {adj:+.2f}")

    elif cmd == "watch":
        print(f"  {GOLD}🌍 GEO INTELLIGENCE — Watch Mode (30min intervals){RESET}")
        print(f"  {DIM}Press Ctrl+C to stop{RESET}\n")
        while True:
            try:
                now = datetime.now(timezone.utc).strftime("%H:%M UTC")
                try:
                    events = read_ww3_events(days=14)
                    ledger_as_of = read_ledger_as_of()
                except WW3LedgerError as exc:
                    print(f"  [{now}] {exc}")
                    events = None
                if events:
                    signals = generate_geo_signals(events, ledger_as_of=ledger_as_of)
                    inject_geo_signals(signals)
                    print(f"  [{now}] {signals['risk_posture']} | Esc:{signals['global_escalation_level']}/10 | {signals['event_count']} events")
                elif events is not None:
                    # A fresh record with nothing behind it would make a dead feed look live.
                    print(f"  [{now}] no events in the last 14 days; nothing injected")
                time.sleep(1800)  # 30 min
            except KeyboardInterrupt:
                print("\n  Stopped.")
                break

    else:
        print(f"  Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
