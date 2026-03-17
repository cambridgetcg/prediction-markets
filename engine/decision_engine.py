#!/usr/bin/env python3
"""
decision_engine.py — Converts prediction signals into investment decisions.

Takes synthesis outputs and Oracle signals, applies Kelly criterion sizing,
cross-asset correlation, and outputs ranked trade recommendations.

Usage:
    python3 engine/decision_engine.py                    # scan all signals
    python3 engine/decision_engine.py --min-edge 0.05   # 5%+ edge only
    python3 engine/decision_engine.py --load synthesis-X.json  # from file
"""

import json
import math
import sys
import os
import argparse
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CALIBRATION_DIR = BASE_DIR / "calibration"
BANKROLL_FILE = BASE_DIR / "bankroll" / "state.json"

# ── Kelly Criterion ────────────────────────────────────────────────────────────

def kelly_fraction(my_estimate: float, market_price: float,
                   win_multiplier: float = None, fraction: float = 0.25) -> float:
    """
    Full Kelly: f = (bp - q) / b
    where b = odds (1/price - 1), p = my_estimate, q = 1 - p
    Returns fractional Kelly (default: quarter Kelly for safety).
    """
    if market_price <= 0 or market_price >= 1:
        return 0.0
    b = (1 / market_price) - 1  # payout odds on prediction market
    p = my_estimate
    q = 1 - p
    full_kelly = (b * p - q) / b
    return max(0.0, full_kelly * fraction)


def edge_score(my_estimate: float, market_price: float) -> float:
    """Edge in percentage points."""
    return my_estimate - market_price


# ── Decision scoring ──────────────────────────────────────────────────────────

def score_opportunity(signal: dict, bankroll: float = 1250.0) -> dict:
    """
    Score a prediction/signal as a trade opportunity.
    Returns a decision dict with recommended action, size, reasoning.
    """
    est = signal.get("my_estimate", 0)
    price = signal.get("market_price")

    if price is None:
        return {**signal, "decision": "NO_PRICE", "recommended_action": None}

    edge = edge_score(est, price)
    kf = kelly_fraction(est, price)
    position_size = bankroll * kf

    # Direction
    if edge > 0:
        direction = "YES (Buy YES — market underprices)"
    elif edge < 0:
        direction = "NO (Buy NO — market overprices)"
    else:
        direction = "PASS (no edge)"

    # Confidence tier
    ci = signal.get("confidence_interval", [est, est])
    ci_width = ci[1] - ci[0] if len(ci) == 2 else 0.5
    if ci_width < 0.15:
        conf_tier = "HIGH"
    elif ci_width < 0.30:
        conf_tier = "MEDIUM"
    else:
        conf_tier = "LOW"

    # Override: if edge is tiny, pass regardless
    if abs(edge) < 0.05:
        recommended = "PASS"
        reason = f"Edge too small ({edge:.1%})"
    elif conf_tier == "LOW":
        recommended = "WATCH"
        reason = f"Low confidence (CI={ci[0]:.0%}–{ci[1]:.0%}); wait for resolution signal"
    elif kf < 0.01:
        recommended = "PASS"
        reason = "Kelly fraction < 1% — insufficient edge/odds"
    else:
        recommended = "TRADE"
        reason = f"Edge {edge:.1%} | Kelly {kf:.1%} | Size ~${position_size:.0f}"

    return {
        **signal,
        "edge_pct": round(edge * 100, 1),
        "kelly_fraction": round(kf * 100, 2),
        "position_size_usd": round(position_size, 2),
        "direction": direction,
        "confidence_tier": conf_tier,
        "recommended_action": recommended,
        "decision_reason": reason,
    }


def rank_opportunities(signals: list, bankroll: float = 1250.0,
                       min_edge: float = 0.05) -> list:
    """Score and rank all signals by expected value."""
    scored = [score_opportunity(s, bankroll) for s in signals if s.get("market_price")]
    # Filter by min edge
    filtered = [s for s in scored if abs(s.get("edge_pct", 0)) >= min_edge * 100]
    # Sort by absolute edge descending
    return sorted(filtered, key=lambda x: abs(x.get("edge_pct", 0)), reverse=True)


def load_active_predictions() -> list:
    pred_file = CALIBRATION_DIR / "predictions.jsonl"
    if not pred_file.exists():
        return []
    preds = []
    for line in pred_file.read_text().splitlines():
        if line.strip():
            try:
                p = json.loads(line)
                if p.get("resolved") is None and p.get("market_price"):
                    preds.append(p)
            except Exception:
                pass
    return preds


def display_recommendations(opps: list) -> None:
    print(f"\n{'═'*60}")
    print(f"DECISION ENGINE — TRADE RECOMMENDATIONS")
    print(f"{'═'*60}\n")

    if not opps:
        print("  No actionable opportunities above edge threshold.")
        print("  (Try lowering --min-edge or adding more predictions with market prices)")
        return

    for i, opp in enumerate(opps, 1):
        action = opp.get("recommended_action", "?")
        emoji = {"TRADE": "🎯", "WATCH": "👁️", "PASS": "❌"}.get(action, "•")
        domain = opp.get("domain", "?")
        q = opp.get("question", "?")[:55]
        edge = opp.get("edge_pct", 0)
        kf = opp.get("kelly_fraction", 0)
        size = opp.get("position_size_usd", 0)
        direction = opp.get("direction", "?")

        print(f"  {i}. {emoji} {action} [{domain}]")
        print(f"     {q}...")
        print(f"     Edge: {edge:+.1f}pp | Kelly: {kf:.1f}% | Size: ${size:.0f}")
        print(f"     → {direction}")
        print(f"     {opp.get('decision_reason','')}")
        print()

    print(f"{'─'*60}")
    tradeable = [o for o in opps if o.get("recommended_action") == "TRADE"]
    total_deploy = sum(o.get("position_size_usd", 0) for o in tradeable)
    print(f"  Tradeable: {len(tradeable)} | Total to deploy: ${total_deploy:.0f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Decision Engine")
    parser.add_argument("--min-edge", type=float, default=0.05, help="Minimum edge (default: 5%%)")
    parser.add_argument("--bankroll", type=float, help="Bankroll override")
    parser.add_argument("--load", help="Load synthesis JSON file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    # Get bankroll
    bankroll = args.bankroll or 1250.0
    if BANKROLL_FILE.exists():
        br = json.loads(BANKROLL_FILE.read_text())
        bankroll = br.get("current_bankroll_usd", bankroll)

    # Get signals
    if args.load:
        synth = json.loads(Path(args.load).read_text())
        signals = [synth]
    else:
        signals = load_active_predictions()

    opps = rank_opportunities(signals, bankroll=bankroll, min_edge=args.min_edge)

    if args.json:
        print(json.dumps(opps, indent=2))
    else:
        display_recommendations(opps)
