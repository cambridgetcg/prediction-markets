#!/usr/bin/env python3
"""
geo_layer.py — Oracle Layer 6 Geo Receiver.

Reads geopolitical intelligence from the WW3 bridge (pipeline/geo_intelligence.py)
and integrates it into Oracle's synthesis engine.

The bridge writes to data/stream/geo_intelligence.jsonl.
This module reads it, builds context strings for LLM injection,
and applies conservative regime adjustments.

Usage:
    python3 engine/geo_layer.py status    # Show current geo layer status
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GEO_JSONL = BASE_DIR / "data" / "stream" / "geo_intelligence.jsonl"


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
        "event_count": geo.get("event_count", 0),
    }


def _posture_to_bias(posture: str) -> str:
    return {"RISK_OFF": "risk-off", "RISK_ON": "risk-on"}.get(posture, "neutral")


# ── Core functions ────────────────────────────────────────────────────────────

def load_geo_context() -> dict | None:
    """Read the latest entry from data/stream/geo_intelligence.jsonl."""
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


def build_geo_context_string(geo: dict) -> str:
    """Convert a geo signal dict into a concise text block for LLM injection.
    Kept under 400 chars for context window efficiency."""
    g = _norm(geo)
    esc = g["escalation_level"]
    bias = g["regime_bias"]

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

    return (
        f"## Geopolitical Context (Layer 6 — Live Feed)\n"
        f"Escalation: {esc}/10 | Regime: {bias}\n"
        f"Events: {events_str}\n"
        f"Instruments: {inst_str}\n"
        f"Calibration: {cal_str}"
    )


def get_regime_adjustment(geo: dict | None, domain: str) -> float:
    """Return a probability adjustment (-0.05 to +0.05) based on escalation and domain.

    For GEO domain: escalation 7+ → ±0.05 (sign depends on question direction,
    but since we can't know direction here, we nudge toward escalation = YES more likely).
    Other domains: max ±0.02.
    Returns 0.0 if geo is None or escalation < 4.
    """
    if geo is None:
        return 0.0

    g = _norm(geo)
    esc = g["escalation_level"]
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
    """Call synthesise() with geo context injected. Returns synthesis result + geo metadata."""
    # Import here to avoid circular imports
    from engine.synthesise import synthesise, load_domain_context

    geo = load_geo_context()
    geo_active = geo is not None

    # Build context: domain context + geo context appended
    domain_ctx = load_domain_context(domain)
    if geo_active:
        geo_str = build_geo_context_string(geo)
        context = f"{domain_ctx}\n\n{geo_str}"
    else:
        context = domain_ctx

    result = synthesise(question, domain=domain, market_price=market_price,
                        context_override=context)

    # Apply regime adjustment
    adjustment = get_regime_adjustment(geo, domain)
    if adjustment != 0.0 and "my_estimate" in result:
        result["my_estimate"] = round(
            max(0.01, min(0.99, result["my_estimate"] + adjustment)), 4
        )

    # Attach geo layer metadata
    g = _norm(geo) if geo else {}
    result["geo_layer"] = {
        "active": geo_active,
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
        print("GEO LAYER INACTIVE — no data/stream/geo_intelligence.jsonl")
        return

    g = _norm(geo)
    ts = g["ts"]
    esc = g["escalation_level"]
    bias = g["regime_bias"]

    # Age
    age_str = "unknown"
    if ts:
        try:
            then = datetime.fromisoformat(ts)
            now = datetime.now(timezone.utc)
            delta = now - then
            mins = int(delta.total_seconds() / 60)
            if mins < 60:
                age_str = f"{mins}m ago"
            elif mins < 1440:
                age_str = f"{mins // 60}h {mins % 60}m ago"
            else:
                age_str = f"{mins // 1440}d ago"
        except (ValueError, TypeError):
            pass

    print(f"GEO LAYER ACTIVE")
    print(f"  Escalation: {esc}/10")
    print(f"  Regime:     {bias}")
    print(f"  Data age:   {age_str}")
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
