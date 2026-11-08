#!/usr/bin/env python3
"""
geo_layer.py — Oracle Layer 6 Geo Receiver.

Reads geopolitical intelligence from the WW3 bridge (pipeline/geo_intelligence.py)
and integrates it into Oracle's synthesis engine.

The bridge writes to data/stream/geo_intelligence.jsonl.
This module reads it, builds context strings for LLM injection,
and applies conservative regime adjustments.

"Layer 6" here is the geo layer. engine/DATA-SOURCES.md uses "Layer 6" for
betting markets; see the naming note there.

A record is only used while it is fresh. Its age is measured from the older of
two times: when the bridge wrote it (`ts`) and, when the record carries one,
the newest observation in the ww3 ledger the bridge read (`ledger_as_of`).
Past GEO_MAX_AGE_HOURS (default 24) the record is STALE: the status says so,
the context block says so, and it adjusts no probability. A record whose time
cannot be read has no knowable age and counts as stale.

For whether the bridge is connected at all, see engine/DATA-SOURCES.md.

Usage:
    python3 engine/geo_layer.py status    # Show current geo layer status
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GEO_JSONL = BASE_DIR / "data" / "stream" / "geo_intelligence.jsonl"

MAX_AGE_ENV = "GEO_MAX_AGE_HOURS"
DEFAULT_MAX_AGE_HOURS = 24.0


# ── Field normalization ───────────────────────────────────────────────────────
# The bridge may use different field names than the spec. Handle both.

def _norm(geo: dict) -> dict:
    """Normalize field names from bridge output to canonical form."""
    return {
        "escalation_level": geo.get("escalation_level") or geo.get("global_escalation", 0),
        "regime_bias": geo.get("regime_bias") or _posture_to_bias(geo.get("risk_posture", "NEUTRAL")),
        "instrument_impacts": geo.get("instrument_impacts") or geo.get("instrument_adjustments", {}),
        "top_events": geo.get("top_events") or geo.get("active_events", []),
        "brier_context": geo.get("brier_context", {}),
        "ts": geo.get("ts", ""),
        "ledger_as_of": geo.get("ledger_as_of"),
        "event_count": geo.get("event_count", 0),
    }


def _posture_to_bias(posture: str) -> str:
    return {"RISK_OFF": "risk-off", "RISK_ON": "risk-on"}.get(posture, "neutral")


# ── Freshness ─────────────────────────────────────────────────────────────────

def configured_max_age_hours() -> float:
    """Return GEO_MAX_AGE_HOURS, or 24 when it is unset.

    A value that is set but is not a positive number raises, rather than
    quietly falling back to the default.
    """
    raw = os.environ.get(MAX_AGE_ENV, "").strip()
    if not raw:
        return DEFAULT_MAX_AGE_HOURS
    try:
        hours = float(raw)
    except ValueError:
        hours = float("nan")
    if not (math.isfinite(hours) and hours > 0):
        raise ValueError(f"{MAX_AGE_ENV} must be a positive number of hours, got {raw!r}")
    return hours


def _parse_utc(value) -> datetime | None:
    """Parse an ISO timestamp that states its zone. None when missing, unreadable or zoneless."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # A time without a zone could be any of ~26 hours; it has no knowable age.
        return None
    return parsed


def _format_age(age: timedelta) -> str:
    mins = int(age.total_seconds() // 60)
    if mins < 60:
        return f"{mins}m"
    if mins < 1440:
        return f"{mins // 60}h {mins % 60}m"
    return f"{mins // 1440}d {(mins % 1440) // 60}h"


def _format_hours(hours: float) -> str:
    return f"{hours:g}h"


def geo_freshness(geo: dict | None, *, max_age_hours: float | None = None,
                  now: datetime | None = None) -> dict:
    """Say how old a geo record's data is and whether it is fresh enough to use.

    Returns a dict with:
      state         "ACTIVE" (fresh), "STALE", or "MISSING" (no record)
      age           timedelta, or None when the age cannot be known
      age_str       the age in words ("3h 12m", "232d 1h", "unknown")
      basis         which time the age was measured from
      max_age_hours the limit that was applied
      reason        one line on why the state is what it is
    """
    limit = configured_max_age_hours() if max_age_hours is None else max_age_hours
    now = now or datetime.now(timezone.utc)
    result = {"state": "MISSING", "age": None, "age_str": "unknown", "basis": None,
              "max_age_hours": limit, "reason": "no geo record"}
    if geo is None:
        return result

    written = _parse_utc(geo.get("ts"))
    if written is None:
        result.update(state="STALE", reason="the record has no readable, zoned timestamp (ts)")
        return result

    as_of, basis = written, "the record's write time (ts)"
    raw_ledger = geo.get("ledger_as_of")
    if raw_ledger is not None:
        ledger = _parse_utc(raw_ledger)
        if ledger is None:
            result.update(state="STALE", reason="the record's ledger_as_of cannot be read")
            return result
        if ledger < as_of:
            as_of, basis = ledger, "the newest ww3 observation read (ledger_as_of)"

    age = now - as_of
    if age < timedelta(0):
        result.update(state="STALE", reason="the record's time is in the future")
        return result

    result.update(age=age, age_str=_format_age(age), basis=basis)
    if age <= timedelta(hours=limit):
        result.update(state="ACTIVE", reason=f"data is within the {_format_hours(limit)} limit")
    else:
        result.update(state="STALE",
                      reason=f"data is {result['age_str']} old, past the {_format_hours(limit)} limit")
    return result


def is_fresh(geo: dict | None, *, max_age_hours: float | None = None,
             now: datetime | None = None) -> bool:
    return geo_freshness(geo, max_age_hours=max_age_hours, now=now)["state"] == "ACTIVE"


# ── Core functions ────────────────────────────────────────────────────────────

def load_geo_context() -> dict | None:
    """Read the latest entry from data/stream/geo_intelligence.jsonl.

    Returns the newest record whatever its age. Check geo_freshness() before
    treating it as current.
    """
    try:
        if not GEO_JSONL.exists():
            return None
        text = GEO_JSONL.read_text().strip()
        if not text:
            return None
        last_line = text.splitlines()[-1].strip()
        if not last_line:
            return None
        return json.loads(last_line)
    except (json.JSONDecodeError, OSError):
        return None


def build_geo_context_string(geo: dict, *, max_age_hours: float | None = None,
                             now: datetime | None = None) -> str:
    """Convert a geo signal dict into a concise text block for LLM injection.
    Kept under 400 chars for context window efficiency.

    The header states the data's age. A stale record is labelled STALE, so a
    caller that injects it anyway cannot pass it off as current."""
    g = _norm(geo)
    esc = g["escalation_level"]
    bias = g["regime_bias"]
    fresh = geo_freshness(geo, max_age_hours=max_age_hours, now=now)

    # Top 3 events — one line each
    events = g["top_events"][:3]
    event_lines = []
    for e in events:
        if isinstance(e, dict):
            event_lines.append(e.get("title", "?")[:60])
        else:
            event_lines.append(str(e)[:60])
    events_str = "; ".join(event_lines) if event_lines else "none"

    # Instrument signals — top 3 by magnitude
    impacts = g["instrument_impacts"]
    if impacts:
        sorted_inst = sorted(impacts.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        inst_str = ", ".join(f"{k} {v:+.1f}" for k, v in sorted_inst)
    else:
        inst_str = "none"

    # Brier context
    brier = g["brier_context"]
    if brier and brier.get("calibrated"):
        cal_str = f"Brier {brier.get('avg_brier_score', '?')} — {brier.get('interpretation', '?')}"
    else:
        cal_str = "no calibration data"

    age_words = f"data {fresh['age_str']} old" if fresh["age"] is not None else "data age unknown"
    if fresh["state"] == "ACTIVE":
        label = age_words
    else:
        label = f"STALE, {age_words}, limit {_format_hours(fresh['max_age_hours'])}; not current"

    return (
        f"## Geopolitical Context (Layer 6 geo bridge — {label})\n"
        f"Escalation: {esc}/10 | Regime: {bias}\n"
        f"Events: {events_str}\n"
        f"Instruments: {inst_str}\n"
        f"Calibration: {cal_str}"
    )


def get_regime_adjustment(geo: dict | None, domain: str, *,
                          max_age_hours: float | None = None,
                          now: datetime | None = None) -> float:
    """Return a probability adjustment (-0.05 to +0.05) based on escalation and domain.

    For GEO domain: escalation 7+ → ±0.05 (sign depends on question direction,
    but since we can't know direction here, we nudge toward escalation = YES more likely).
    Other domains: max ±0.02.
    Returns 0.0 if geo is None, stale (see geo_freshness), or escalation < 4.
    Escalation is ww3's 1-10 scale.
    """
    if geo is None:
        return 0.0
    if not is_fresh(geo, max_age_hours=max_age_hours, now=now):
        return 0.0

    g = _norm(geo)
    esc = g["escalation_level"] or 0
    bias = g["regime_bias"]

    if esc < 4:
        return 0.0

    # Scale: esc 4→small, 7→medium, 10→max
    raw = (esc - 3) / 7.0  # 0.14 at esc=4, 1.0 at esc=10

    if domain == "GEO":
        # GEO questions: escalation makes conflict/escalation YES more likely
        if bias == "risk-off":
            adjustment = raw * 0.05   # up to +0.05
        elif bias == "risk-on":
            adjustment = raw * -0.03  # de-escalation signal
        else:
            adjustment = raw * 0.02
    else:
        # Other domains: smaller, risk-off dampens YES on positive outcomes
        if bias == "risk-off":
            adjustment = raw * -0.02  # risk-off hurts positive outcomes
        elif bias == "risk-on":
            adjustment = raw * 0.01
        else:
            adjustment = 0.0

    return round(max(-0.05, min(0.05, adjustment)), 4)


def enrich_synthesise_call(question: str, domain: str, market_price: float) -> dict:
    """Call synthesise() with geo context injected. Returns synthesis result + geo metadata.

    Only a fresh record enters the prompt or moves the estimate. Nothing in the
    repository calls this today."""
    # Import here to avoid circular imports
    from engine.synthesise import synthesise, load_domain_context

    geo = load_geo_context()
    fresh = geo_freshness(geo)
    geo_active = fresh["state"] == "ACTIVE"

    # Build context: domain context + geo context appended
    domain_ctx = load_domain_context(domain)
    if geo_active:
        geo_str = build_geo_context_string(geo, max_age_hours=fresh["max_age_hours"])
        context = f"{domain_ctx}\n\n{geo_str}"
    else:
        context = domain_ctx

    result = synthesise(question, domain=domain, market_price=market_price,
                        context_override=context)

    # Apply regime adjustment
    adjustment = get_regime_adjustment(geo, domain, max_age_hours=fresh["max_age_hours"])
    if adjustment != 0.0 and "my_estimate" in result:
        result["my_estimate"] = round(
            max(0.01, min(0.99, result["my_estimate"] + adjustment)), 4
        )

    # Attach geo layer metadata
    g = _norm(geo) if geo else {}
    age = fresh["age"]
    result["geo_layer"] = {
        "active": geo_active,
        "state": fresh["state"],
        "data_age_hours": round(age.total_seconds() / 3600, 2) if age is not None else None,
        "escalation_level": g.get("escalation_level", 0),
        "regime_bias": g.get("regime_bias", "neutral"),
        "adjustment": adjustment,
    }

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def cli_status():
    """Show current geo layer status."""
    geo = load_geo_context()
    if geo is None:
        print("GEO LAYER INACTIVE — no readable record in data/stream/geo_intelligence.jsonl")
        return

    try:
        fresh = geo_freshness(geo)
    except ValueError as exc:
        print(f"GEO LAYER STATUS UNKNOWN — {exc}")
        return

    g = _norm(geo)
    esc = g["escalation_level"]
    bias = g["regime_bias"]
    limit = _format_hours(fresh["max_age_hours"])

    if fresh["state"] == "ACTIVE":
        print(f"GEO LAYER ACTIVE — data {fresh['age_str']} old (limit {limit})")
    else:
        print(f"GEO LAYER STALE — {fresh['reason']}")
        print("  Not used for context or probability adjustments.")
    print(f"  Data age:   {fresh['age_str']}"
          + (f", from {fresh['basis']}" if fresh["basis"] else ""))
    print(f"  Record ts:  {g['ts'] or 'missing'}")
    if g["ledger_as_of"]:
        print(f"  Ledger as of: {g['ledger_as_of']}")
    print(f"  Escalation: {esc}/10")
    print(f"  Regime:     {bias}")
    print(f"  Events:     {g['event_count']}")

    events = g["top_events"][:3]
    if events:
        print(f"  Top events:")
        for e in events:
            if isinstance(e, dict):
                print(f"    - {e.get('title', '?')[:70]}")
            else:
                print(f"    - {str(e)[:70]}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        cli_status()
    else:
        print(f"Usage: python3 engine/geo_layer.py status")


if __name__ == "__main__":
    main()
