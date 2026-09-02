#!/usr/bin/env python3
"""
decision_engine.py — Converts forecast differences into paper opportunities.

Takes synthesis outputs and Oracle signals, applies direction-correct Kelly
math, and outputs research candidates. It does not authorize or place trades.

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
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CALIBRATION_DIR = BASE_DIR / "calibration"
BANKROLL_FILE = BASE_DIR / "bankroll" / "state.json"
NO_LIVE_TRADING_FILE = BASE_DIR / "NO-LIVE-TRADING"

# ── Kelly Criterion ────────────────────────────────────────────────────────────

def kelly_fraction(my_estimate: float, market_price: float,
                   win_multiplier: float = None, fraction: float = 0.25) -> float:
    """
    Full Kelly: f = (bp - q) / b
    where b = odds (1/price - 1), p = probability the selected token wins,
    and q = 1 - p. Despite their legacy names, ``my_estimate`` and
    ``market_price`` must both describe that same selected token.

    All parameter names, including unused ``win_multiplier``, are retained for
    compatibility; binary contract odds continue to derive from market price.
    Returns fractional Kelly (default: quarter Kelly for safety).
    """
    try:
        win_probability = float(my_estimate)
        token_price = float(market_price)
        kelly_scale = float(fraction)
    except (TypeError, ValueError):
        return 0.0
    if (
        not math.isfinite(win_probability)
        or not 0.0 <= win_probability <= 1.0
        or not math.isfinite(token_price)
        or token_price <= 0
        or token_price >= 1
        or not math.isfinite(kelly_scale)
        or kelly_scale < 0
    ):
        return 0.0
    b = (1 / token_price) - 1  # payout odds on prediction market
    p = win_probability
    q = 1 - p
    full_kelly = (b * p - q) / b
    return max(0.0, full_kelly * kelly_scale)


def edge_score(my_estimate: float, market_price: float) -> float:
    """Edge in percentage points."""
    return my_estimate - market_price


def _as_probability(value) -> Optional[float]:
    """Return a finite probability, or None for absent/invalid input."""
    if isinstance(value, bool):
        return None
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        return None
    return probability


def _confidence_interval(value, estimate):
    """Return a valid two-point probability interval, or None if malformed."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    low = _as_probability(value[0])
    high = _as_probability(value[1])
    if low is None or high is None or low > high:
        return None
    return (low, high)


# ── Decision scoring ──────────────────────────────────────────────────────────

def score_opportunity(signal: dict, bankroll: float = 1250.0) -> dict:
    """
    Score a forecast difference as a paper opportunity.

    ``market_price`` is retained as a historical YES reference. A paper
    candidate additionally requires the selected side's executable ask and an
    explicit non-negative ``cost_per_contract``. Missing execution inputs can
    be watched, but never promoted by plausible defaults.
    """
    raw_estimate = signal.get("my_estimate")
    raw_price = signal.get("market_price")

    if raw_price is None:
        return {**signal, "decision": "NO_PRICE", "recommended_action": None}

    est = _as_probability(raw_estimate)
    price = _as_probability(raw_price)
    if est is None or price is None or price in (0.0, 1.0):
        return {
            **signal,
            "decision": "INVALID_PROBABILITY",
            "recommended_action": None,
            "decision_reason": "Estimate and market price must be finite probabilities; price must be strictly between 0 and 1",
        }

    reference_edge = edge_score(est, price)

    # The historical YES reference gives a watch direction when executable
    # inputs are absent. Complete side-specific asks can choose either side.
    if reference_edge > 0:
        side = "YES"
        selected_probability = est
        derived_price = price
    elif reference_edge < 0:
        side = "NO"
        selected_probability = 1.0 - est
        derived_price = 1.0 - price
    else:
        side = "NONE"
        selected_probability = est
        derived_price = price

    # Missing or malformed uncertainty fails closed.
    ci = _confidence_interval(signal.get("confidence_interval"), est)
    if ci is None:
        return {
            **signal,
            "decision": "INVALID_CONFIDENCE_INTERVAL",
            "recommended_action": None,
            "decision_reason": "A confidence interval must contain two ordered finite probabilities",
        }
    ci_width = ci[1] - ci[0]
    if ci_width < 0.15:
        conf_tier = "HIGH"
    elif ci_width < 0.30:
        conf_tier = "MEDIUM"
    else:
        conf_tier = "LOW"

    asks = {}
    for candidate_side, field in (("YES", "yes_ask"), ("NO", "no_ask")):
        raw_ask = signal.get(field)
        if raw_ask is None:
            continue
        executable_ask = _as_probability(raw_ask)
        if executable_ask in (None, 0.0, 1.0):
            return {
                **signal,
                "decision": "INVALID_EXECUTABLE_QUOTE",
                "recommended_action": None,
                "decision_reason": f"{field} must be a finite probability strictly between 0 and 1",
            }
        asks[candidate_side] = executable_ask

    raw_cost = signal.get("cost_per_contract")
    try:
        cost = float(raw_cost) if raw_cost is not None and not isinstance(raw_cost, bool) else None
    except (TypeError, ValueError):
        cost = None
    if cost is not None and (not math.isfinite(cost) or cost < 0):
        return {
            **signal,
            "decision": "INVALID_COST",
            "recommended_action": None,
            "decision_reason": "cost_per_contract must be a finite non-negative amount",
        }

    candidates = []
    if cost is not None:
        for candidate_side, executable_ask in asks.items():
            candidate_all_in = executable_ask + cost
            if not 0.0 < candidate_all_in < 1.0:
                return {
                    **signal,
                    "decision": "INVALID_ALL_IN_PRICE",
                    "recommended_action": None,
                    "decision_reason": "Executable ask plus per-contract costs must be strictly between 0 and 1",
                }
            probability = est if candidate_side == "YES" else 1.0 - est
            candidates.append(
                (probability - candidate_all_in, candidate_side, probability, executable_ask, candidate_all_in)
            )

    execution_inputs_complete = bool(candidates)
    if candidates:
        paper_edge, side, selected_probability, selected_price, all_in_price = max(candidates)
    else:
        paper_edge = None
        selected_price = asks.get(side, derived_price)
        all_in_price = None

    if side == "YES":
        direction = "YES (paper comparison)"
    elif side == "NO":
        direction = "NO (paper comparison)"
    else:
        direction = "PASS (no reference gap)"

    kf = kelly_fraction(selected_probability, all_in_price) if all_in_price is not None else 0.0
    try:
        paper_bankroll = float(bankroll)
    except (TypeError, ValueError):
        paper_bankroll = 0.0
    if not math.isfinite(paper_bankroll) or paper_bankroll < 0:
        paper_bankroll = 0.0
    position_size = paper_bankroll * kf

    # This engine ranks research candidates only. Live authority is always false.
    if conf_tier == "LOW":
        recommended = "WATCH"
        reason = f"Low confidence (CI={ci[0]:.0%}–{ci[1]:.0%}); wait for resolution signal"
    elif not execution_inputs_complete:
        if abs(reference_edge) < 0.05:
            recommended = "PASS"
            reason = f"Reference probability gap too small ({reference_edge:.1%})"
        else:
            recommended = "WATCH"
            reason = "Missing a side-specific executable ask or explicit per-contract costs"
    elif paper_edge < 0.05:
        recommended = "PASS"
        reason = f"All-in paper edge too small ({paper_edge:.1%})"
    elif kf < 0.01:
        recommended = "PASS"
        reason = "Kelly fraction < 1% — insufficient edge/odds"
    else:
        recommended = "PAPER_CANDIDATE"
        reason = f"All-in paper edge {paper_edge:.1%} | Kelly {kf:.1%} | Paper size ~${position_size:.0f}"

    return {
        **signal,
        "decision": "PAPER_ONLY",
        "side": side,
        "edge_pct": round(reference_edge * 100, 1),
        "reference_gap_pct": round(reference_edge * 100, 1),
        "paper_edge_pct": round(paper_edge * 100, 1) if paper_edge is not None else None,
        "quote_basis": "executable_ask" if execution_inputs_complete else "derived_reference",
        "selected_token_price": round(selected_price, 4),
        "selected_token_probability": round(selected_probability, 4),
        "all_in_token_price": round(all_in_price, 4) if all_in_price is not None else None,
        "kelly_fraction": round(kf * 100, 2),
        "position_size_usd": round(position_size, 2),
        "paper_position_size_usd": round(position_size, 2),
        "execution_authorized": False,
        "no_live_trading_brake_present": NO_LIVE_TRADING_FILE.exists(),
        "direction": direction,
        "confidence_tier": conf_tier,
        "recommended_action": recommended,
        "decision_reason": reason,
    }


def rank_opportunities(signals: list, bankroll: float = 1250.0,
                       min_edge: float = 0.05) -> list:
    """Score and rank paper candidates by all-in edge when available."""
    scored = [
        score_opportunity(s, bankroll)
        for s in signals
        if s.get("market_price") is not None
    ]
    def comparable_edge(result):
        paper_edge = result.get("paper_edge_pct")
        return paper_edge if paper_edge is not None else abs(result.get("reference_gap_pct", 0))

    filtered = [s for s in scored if comparable_edge(s) >= min_edge * 100]
    return sorted(filtered, key=comparable_edge, reverse=True)


def load_active_predictions() -> list:
    pred_file = CALIBRATION_DIR / "predictions.jsonl"
    if not pred_file.exists():
        return []
    preds = []
    for line in pred_file.read_text().splitlines():
        if line.strip():
            try:
                p = json.loads(line)
                price = _as_probability(p.get("market_price"))
                if p.get("resolved") in (None, False) and price not in (None, 0.0, 1.0):
                    preds.append(p)
            except Exception:
                pass
    return preds


def display_recommendations(opps: list) -> None:
    print(f"\n{'═'*60}")
    print(f"DECISION ENGINE — PAPER OPPORTUNITIES")
    print(f"{'═'*60}\n")

    if not opps:
        print("  No actionable opportunities above edge threshold.")
        print("  (Try lowering --min-edge or adding more predictions with market prices)")
        return

    for i, opp in enumerate(opps, 1):
        action = opp.get("recommended_action", "?")
        emoji = {"PAPER_CANDIDATE": "🎯", "WATCH": "👁️", "PASS": "❌"}.get(action, "•")
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
    candidates = [o for o in opps if o.get("recommended_action") == "PAPER_CANDIDATE"]
    total_paper = sum(o.get("position_size_usd", 0) for o in candidates)
    print(f"  Paper candidates: {len(candidates)} | Paper allocation: ${total_paper:.0f}")


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
