#!/usr/bin/env python3
"""
L05 Decay Monitor — Signal Freshness and Edge Degradation

Monitors insider edge degradation over time, manages registry lifecycle,
and tracks L04 follow-signal performance attribution. Closes the loop:
L01 populates -> L02 scores -> L03 classifies -> L04 follows -> L05 monitors & culls.

Usage:
    python3 scripts/l05-decay-monitor.py                    # Full decay check (live mode)
    python3 scripts/l05-decay-monitor.py --bootstrap        # Run with synthesized sample data
    python3 scripts/l05-decay-monitor.py --wallet 0xabc...  # Single wallet deep-dive
    python3 scripts/l05-decay-monitor.py --json             # Machine-readable output
    python3 scripts/l05-decay-monitor.py --dry-run          # Analysis only, don't update files

Schedule: Weekly (Sundays), after R02/R04 calibration review.

Dependencies: stdlib only (json, datetime, math, statistics, pathlib, argparse).
"""

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, stdev

# --- Paths ---

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

CLASSIFIED_INSIDERS_PATH = DATA_DIR / "classified-insiders.json"
FOLLOW_SIGNALS_PATH = DATA_DIR / "follow-signals.jsonl"
EDGE_PROFILES_PATH = DATA_DIR / "edge-profiles.json"
REGISTRY_EVENTS_PATH = DATA_DIR / "registry-events.jsonl"
TRADES_PATH = PROJECT_DIR / "strategies" / "paper-trades" / "trades.jsonl"

# --- Thresholds ---

DECAY_THRESHOLDS = {
    "soft_flag": 0.30,   # Edge < 30% of historical max -> flag for review
    "hard_flag": 0.10,   # Edge < 10% of historical max -> lower confidence
    "archive": 0.00,     # Edge <= 0 over 3+ consecutive windows -> archive
    "inactive": 90,      # No new bets in N days -> flag as possibly inactive
}

REGISTRY_STATES = {
    "ACTIVE": "Following. Confidence 3-5. Edge holding.",
    "WATCHING": "Monitoring. Confidence 1-2. Edge weakening or inactive.",
    "ARCHIVED": "Not following. Edge gone or account abandoned.",
}

ROLLING_WINDOWS_DAYS = [90, 180, 270, 360]  # windows ending at: now, 3mo, 6mo, 9mo, 12mo ago

# --- Data loading ---


def load_json(path, default=None):
    """Load a JSON file, returning default if missing."""
    if not path.exists():
        return default
    with open(path) as f:
        return json.load(f)


def load_jsonl(path):
    """Load a JSONL file, returning list of dicts."""
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def save_json(path, data):
    """Save data as pretty-printed JSON."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Written: {path}")


def append_jsonl(path, entry):
    """Append a single entry to a JSONL file."""
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


# --- Bootstrap data ---


def generate_bootstrap_data():
    """
    Generate synthetic insider data for initial testing.
    Three insiders with different decay profiles:
      1. Stable edge (POL specialist)
      2. Decaying edge (TEC specialist)
      3. Collapsed edge (GEO specialist - exposed)
    """
    now = datetime.now(timezone.utc)

    # Synthetic edge profiles (L01 output format)
    edge_profiles = [
        {
            "wallet": "0x1111111111111111111111111111111111111111",
            "alias": "POL-Insider-01",
            "trades": _generate_trades_series(
                now, n=60, categories={"POL": 40, "ECO": 20},
                edge_profile="stable", base_edge=0.22
            ),
        },
        {
            "wallet": "0x2222222222222222222222222222222222222222",
            "alias": "TEC-Insider-01",
            "trades": _generate_trades_series(
                now, n=45, categories={"TEC": 35, "CRY": 10},
                edge_profile="decaying", base_edge=0.28
            ),
        },
        {
            "wallet": "0x3333333333333333333333333333333333333333",
            "alias": "GEO-Exposed-01",
            "trades": _generate_trades_series(
                now, n=30, categories={"GEO": 25, "POL": 5},
                edge_profile="collapsed", base_edge=0.30
            ),
        },
    ]

    # Synthetic classified insiders (L03 output format)
    classified = [
        {
            "wallet": "0x1111111111111111111111111111111111111111",
            "alias": "POL-Insider-01",
            "insider_score": 8.2,
            "dominant_category": "POL",
            "edge_categories": {"POL": 0.22, "ECO": 0.12},
            "follow_confidence": 4,
            "n_bets": 60,
            "p_value": 0.0003,
            "last_active": (now - timedelta(days=5)).isoformat(),
            "notes": "Consistent political market edge. Possible campaign staffer.",
        },
        {
            "wallet": "0x2222222222222222222222222222222222222222",
            "alias": "TEC-Insider-01",
            "insider_score": 7.5,
            "dominant_category": "TEC",
            "edge_categories": {"TEC": 0.18, "CRY": 0.08},
            "follow_confidence": 3,
            "n_bets": 45,
            "p_value": 0.004,
            "last_active": (now - timedelta(days=12)).isoformat(),
            "notes": "Tech insider. Edge declining over last two quarters.",
        },
        {
            "wallet": "0x3333333333333333333333333333333333333333",
            "alias": "GEO-Exposed-01",
            "insider_score": 6.8,
            "dominant_category": "GEO",
            "edge_categories": {"GEO": 0.01, "POL": -0.05},
            "follow_confidence": 2,
            "n_bets": 30,
            "p_value": 0.04,
            "last_active": (now - timedelta(days=95)).isoformat(),
            "notes": "Publicly identified on Twitter. Edge collapsed post-exposure.",
        },
    ]

    # Synthetic follow signals (L04 output format)
    follow_signals = [
        {
            "ts": (now - timedelta(days=30)).isoformat(),
            "wallet": "0x1111111111111111111111111111111111111111",
            "alias": "POL-Insider-01",
            "market": "Will X happen by March 2026?",
            "action": "FOLLOW",
            "direction": "YES",
            "confidence": 4,
            "insider_edge_at_signal": 0.21,
            "outcome": "pending",
        },
        {
            "ts": (now - timedelta(days=20)).isoformat(),
            "wallet": "0x2222222222222222222222222222222222222222",
            "alias": "TEC-Insider-01",
            "market": "Google launches product Y in Q1?",
            "action": "FOLLOW",
            "direction": "YES",
            "confidence": 3,
            "insider_edge_at_signal": 0.15,
            "outcome": "NO",
            "pnl_usd": -45.00,
        },
        {
            "ts": (now - timedelta(days=60)).isoformat(),
            "wallet": "0x1111111111111111111111111111111111111111",
            "alias": "POL-Insider-01",
            "market": "Senate confirms nominee Z?",
            "action": "FOLLOW",
            "direction": "YES",
            "confidence": 4,
            "insider_edge_at_signal": 0.23,
            "outcome": "YES",
            "pnl_usd": 120.00,
        },
    ]

    return edge_profiles, classified, follow_signals


def _generate_trades_series(now, n, categories, edge_profile, base_edge):
    """Generate a series of synthetic trades with a specified edge profile."""
    trades = []
    total_days = 360
    for i in range(n):
        days_ago = int(total_days * (i / n))
        ts = (now - timedelta(days=days_ago)).isoformat()
        # Pick category proportionally
        cat = _pick_category(categories, i)
        # Compute edge based on profile and time
        # time_frac: 0 = oldest trade, 1 = most recent trade
        time_frac = 1 - (i / n)  # i=0 is most recent (days_ago=0), so invert
        if edge_profile == "stable":
            edge = base_edge + (0.02 * (time_frac - 0.5))  # slight variation
        elif edge_profile == "decaying":
            edge = base_edge * (1.0 - 0.6 * time_frac)  # high historically, low now
        elif edge_profile == "collapsed":
            if time_frac > 0.6:  # recent trades, post-exposure
                edge = -0.02 + 0.01 * (time_frac - 0.6)  # near-zero/negative
            else:
                edge = base_edge * (0.7 + 0.3 * time_frac)  # historical edge
        else:
            edge = base_edge
        trades.append({
            "ts": ts,
            "category": cat,
            "edge": round(edge, 4),
            "resolved": True,
        })
    return trades


def _pick_category(categories, index):
    """Deterministically pick category from distribution."""
    total = sum(categories.values())
    cumulative = 0
    target = index % total
    for cat, count in categories.items():
        cumulative += count
        if target < cumulative:
            return cat
    return list(categories.keys())[-1]


# --- Core analysis ---


def rolling_edge(trades, category, window_days=90, reference_date=None):
    """
    Compute edge for trades in a category over rolling windows.
    Returns list of window results sorted oldest-first.
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)

    results = []
    for offset_months in [0, 3, 6, 9]:
        window_end = reference_date - timedelta(days=offset_months * 30)
        window_start = window_end - timedelta(days=window_days)

        window_trades = []
        for t in trades:
            ts = _parse_ts(t["ts"])
            if ts and window_start <= ts <= window_end and t.get("category") == category:
                window_trades.append(t)

        if not window_trades:
            results.append({
                "period_end": window_end.strftime("%Y-%m-%d"),
                "mean_edge": None,
                "n": 0,
                "p": None,
            })
            continue

        edges = [t["edge"] for t in window_trades if "edge" in t]
        if not edges:
            results.append({
                "period_end": window_end.strftime("%Y-%m-%d"),
                "mean_edge": None,
                "n": 0,
                "p": None,
            })
            continue

        m = mean(edges)
        n = len(edges)
        # One-sample t-test: is mean edge > 0?
        if n >= 2:
            se = stdev(edges) / math.sqrt(n)
            if se > 0:
                t_stat = m / se
                # Approximate p-value using normal distribution (good enough for n >= 10)
                p = _normal_cdf(-t_stat)
            else:
                p = 0.0 if m > 0 else 1.0
        else:
            p = None

        results.append({
            "period_end": window_end.strftime("%Y-%m-%d"),
            "mean_edge": round(m, 4),
            "n": n,
            "p": round(p, 6) if p is not None else None,
        })

    # Return oldest-first
    results.reverse()
    return results


def _normal_cdf(x):
    """Approximate standard normal CDF using error function approximation."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _parse_ts(ts_str):
    """Parse ISO timestamp string to datetime."""
    try:
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def classify_decay(rolling_results, historical_max_edge):
    """
    Classify the decay pattern from rolling window results.
    Returns (pattern_name, description).
    """
    valid = [r for r in rolling_results if r["mean_edge"] is not None]
    if len(valid) < 2:
        return "INSUFFICIENT_DATA", "Not enough windows with data for trend analysis."

    latest = valid[-1]
    edges = [r["mean_edge"] for r in valid]

    if historical_max_edge <= 0:
        return "NO_EDGE", "No historical edge detected."

    ratio = latest["mean_edge"] / historical_max_edge if historical_max_edge > 0 else 0

    # Check for monotone decline
    declining = all(edges[i] >= edges[i + 1] for i in range(len(edges) - 1))
    # Check for collapse
    collapsed = latest["mean_edge"] <= 0 and latest["n"] >= 3

    if collapsed:
        return "COLLAPSED", f"Edge reversed/zero. Latest: {latest['mean_edge']:.3f}. Archive candidate."
    if ratio <= DECAY_THRESHOLDS["hard_flag"]:
        return "HARD_DECAY", f"Edge at {ratio:.0%} of historical max ({historical_max_edge:.3f}). Hard flag."
    if ratio <= DECAY_THRESHOLDS["soft_flag"]:
        return "SOFT_DECAY", f"Edge at {ratio:.0%} of historical max ({historical_max_edge:.3f}). Soft flag."
    if declining and len(valid) >= 3:
        return "DECLINING", f"Monotone decline across {len(valid)} windows. Watch closely."
    if latest["mean_edge"] > historical_max_edge * 0.9:
        return "STRONG", f"Edge at {ratio:.0%} of max. Holding strong."
    return "STABLE", f"Edge at {ratio:.0%} of max. Within normal range."


def check_inactivity(insider, now=None):
    """Check if an insider has gone inactive."""
    if now is None:
        now = datetime.now(timezone.utc)
    last_active = _parse_ts(insider.get("last_active", ""))
    if not last_active:
        return True, "No last_active timestamp."
    days_inactive = (now - last_active).days
    if days_inactive >= DECAY_THRESHOLDS["inactive"]:
        return True, f"Inactive for {days_inactive} days (threshold: {DECAY_THRESHOLDS['inactive']}d)."
    if days_inactive >= 60:
        return False, f"Quiet for {days_inactive} days. Pre-inactive warning."
    return False, f"Active {days_inactive} days ago."


# --- Confidence updates ---


def compute_confidence_delta(insider, decay_pattern, rolling_results, follow_signals, now=None):
    """
    Compute how follow_confidence should change.
    Returns (delta, reasons) where delta is -2 to +1.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    delta = 0
    reasons = []
    wallet = insider.get("wallet", "")
    valid_windows = [r for r in rolling_results if r["mean_edge"] is not None]

    # --- INCREASE checks ---
    if len(valid_windows) >= 2:
        historical_avg = mean([r["mean_edge"] for r in valid_windows])
        latest = valid_windows[-1]["mean_edge"]
        if latest > historical_avg and latest > 0:
            delta += 1
            reasons.append(f"Latest edge ({latest:.3f}) > historical avg ({historical_avg:.3f})")

    # N bets increasing check
    if len(valid_windows) >= 2:
        n_trend = [r["n"] for r in valid_windows]
        if len(n_trend) >= 2 and n_trend[-1] > n_trend[-2]:
            # Don't double-count if already increased
            if delta == 0:
                delta += 1
                reasons.append(f"Bet volume increasing: {n_trend[-2]} -> {n_trend[-1]}")

    # --- DECREASE checks ---
    if decay_pattern in ("HARD_DECAY", "COLLAPSED"):
        delta -= 1
        reasons.append(f"Decay pattern: {decay_pattern}")

    if decay_pattern == "COLLAPSED":
        delta -= 1  # extra penalty for collapse
        reasons.append("Edge collapsed — additional penalty")

    # Inactivity check
    inactive, inactive_msg = check_inactivity(insider, now)
    if inactive:
        delta -= 1
        reasons.append(f"Inactive: {inactive_msg}")

    # Follow signal performance
    wallet_signals = [s for s in follow_signals if s.get("wallet") == wallet]
    resolved_signals = [s for s in wallet_signals if s.get("outcome") not in (None, "pending")]
    if len(resolved_signals) >= 2:
        losing = [s for s in resolved_signals if s.get("pnl_usd", 0) < 0]
        if len(losing) >= 2:
            delta -= 1
            reasons.append(f"{len(losing)}/{len(resolved_signals)} follow signals lost money")

    # Exposure check (from notes)
    notes = insider.get("notes", "").lower()
    if any(kw in notes for kw in ["exposed", "identified", "public", "charged"]):
        if "exposure_penalty_applied" not in insider.get("flags", []):
            delta -= 1
            reasons.append("Account publicly exposed (from notes)")

    return delta, reasons


def apply_confidence(insider, delta, reasons):
    """Apply confidence delta and determine new state. Returns (new_confidence, new_state, event_or_none)."""
    old_conf = insider.get("follow_confidence", 3)
    new_conf = max(1, min(5, old_conf + delta))

    old_state = insider.get("registry_state", "ACTIVE")

    # Determine new state
    if new_conf >= 3:
        new_state = "ACTIVE"
    elif new_conf >= 1:
        new_state = "WATCHING"
    else:
        new_state = "ARCHIVED"

    # Check archive rule: confidence at 1 for 2+ cycles with no activity
    cycles_at_min = insider.get("_cycles_at_min", 0)
    inactive, _ = check_inactivity(insider)
    if new_conf == 1 and inactive:
        cycles_at_min += 1
        if cycles_at_min >= 2:
            new_state = "ARCHIVED"
    else:
        cycles_at_min = 0

    # Build event if anything changed
    event = None
    now_iso = datetime.now(timezone.utc).isoformat()
    if new_conf != old_conf or new_state != old_state:
        event = {
            "ts": now_iso,
            "wallet": insider.get("wallet", ""),
            "alias": insider.get("alias", ""),
        }
        if new_conf != old_conf:
            event["event"] = "confidence_change"
            event["from"] = old_conf
            event["to"] = new_conf
            event["reason"] = "; ".join(reasons)
        if new_state != old_state:
            event["event"] = "state_change"
            event["from_state"] = old_state
            event["to_state"] = new_state
            event["reason"] = "; ".join(reasons)

    return new_conf, new_state, cycles_at_min, event


# --- Performance attribution ---


def l04_attribution(follow_signals, trades):
    """Compute P&L attribution for L04 follow signals."""
    resolved = [s for s in follow_signals if s.get("outcome") not in (None, "pending")]
    if not resolved:
        return {
            "total_signals": len(follow_signals),
            "resolved": 0,
            "pending": len(follow_signals),
            "win_rate": None,
            "total_pnl": 0.0,
            "avg_pnl": None,
        }

    wins = [s for s in resolved if s.get("pnl_usd", 0) > 0]
    total_pnl = sum(s.get("pnl_usd", 0) for s in resolved)

    return {
        "total_signals": len(follow_signals),
        "resolved": len(resolved),
        "pending": len([s for s in follow_signals if s.get("outcome") in (None, "pending")]),
        "win_rate": round(len(wins) / len(resolved), 3) if resolved else None,
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / len(resolved), 2) if resolved else None,
    }


# --- New insider discovery ---


def check_emerging(edge_profiles, current_registry):
    """
    Identify accounts in edge_profiles not yet in registry that now qualify.
    Conservative: insider_score >= 6.0, n >= 20, p < 0.01, active in last 60d.
    """
    registry_wallets = {i.get("wallet") for i in current_registry}
    now = datetime.now(timezone.utc)
    emerging = []

    for profile in edge_profiles:
        wallet = profile.get("wallet", "")
        if wallet in registry_wallets:
            continue
        # Check if any category has enough data
        trades = profile.get("trades", [])
        if len(trades) < 20:
            continue
        # Check recency
        latest_ts = max((_parse_ts(t["ts"]) for t in trades if _parse_ts(t["ts"])), default=None)
        if not latest_ts or (now - latest_ts).days > 60:
            continue
        # Check edge significance
        cat_edges = {}
        for t in trades:
            cat = t.get("category", "UNK")
            cat_edges.setdefault(cat, []).append(t.get("edge", 0))
        best_cat = max(cat_edges, key=lambda c: mean(cat_edges[c]) if len(cat_edges[c]) >= 5 else -1)
        if len(cat_edges[best_cat]) < 20:
            continue
        cat_mean = mean(cat_edges[best_cat])
        if cat_mean <= 0:
            continue
        # Approximate p-value
        if len(cat_edges[best_cat]) >= 2:
            se = stdev(cat_edges[best_cat]) / math.sqrt(len(cat_edges[best_cat]))
            p = _normal_cdf(-cat_mean / se) if se > 0 else 0.0
        else:
            p = 1.0
        if p >= 0.01:
            continue

        emerging.append({
            "wallet": wallet,
            "alias": profile.get("alias", f"NEW-{wallet[:8]}"),
            "dominant_category": best_cat,
            "mean_edge": round(cat_mean, 4),
            "n_bets": len(cat_edges[best_cat]),
            "p_value": round(p, 6),
        })

    return emerging


# --- Report generation ---


def generate_report(insiders, edge_profiles, follow_signals, analysis_results, attribution, emerging):
    """Generate human-readable decay report."""
    lines = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"# L05 Decay Monitor Report — {now_str}")
    lines.append("")

    # Summary
    states = {"ACTIVE": 0, "WATCHING": 0, "ARCHIVED": 0}
    for r in analysis_results:
        states[r.get("new_state", "ACTIVE")] = states.get(r.get("new_state", "ACTIVE"), 0) + 1
    lines.append(f"## Registry Summary")
    lines.append(f"  Active: {states.get('ACTIVE', 0)}  |  Watching: {states.get('WATCHING', 0)}  |  Archived: {states.get('ARCHIVED', 0)}")
    lines.append("")

    # Per-insider analysis
    lines.append("## Insider Decay Analysis")
    lines.append("")
    for r in analysis_results:
        alias = r["alias"]
        wallet_short = r["wallet"][:10] + "..."
        lines.append(f"### {alias} ({wallet_short})")
        lines.append(f"  State: {r.get('old_state', '?')} -> {r['new_state']}")
        lines.append(f"  Confidence: {r.get('old_confidence', '?')} -> {r['new_confidence']}")
        lines.append(f"  Decay pattern: {r['decay_pattern']} — {r['decay_description']}")

        # Rolling windows
        if r.get("rolling_windows"):
            lines.append("  Rolling windows (oldest -> newest):")
            for w in r["rolling_windows"]:
                edge_str = f"{w['mean_edge']:.4f}" if w["mean_edge"] is not None else "N/A"
                p_str = f"{w['p']:.6f}" if w["p"] is not None else "N/A"
                lines.append(f"    {w['period_end']}: edge={edge_str}  n={w['n']}  p={p_str}")

        # Inactivity
        lines.append(f"  Inactivity: {r.get('inactivity_msg', 'N/A')}")

        # Confidence reasons
        if r.get("confidence_reasons"):
            lines.append("  Confidence change reasons:")
            for reason in r["confidence_reasons"]:
                lines.append(f"    - {reason}")
        lines.append("")

    # L04 attribution
    lines.append("## L04 Signal Performance Attribution")
    if attribution["resolved"] > 0:
        lines.append(f"  Total signals: {attribution['total_signals']}")
        lines.append(f"  Resolved: {attribution['resolved']}  |  Pending: {attribution['pending']}")
        lines.append(f"  Win rate: {attribution['win_rate']:.1%}" if attribution["win_rate"] is not None else "  Win rate: N/A")
        lines.append(f"  Total P&L: ${attribution['total_pnl']:+.2f}")
        lines.append(f"  Avg P&L per signal: ${attribution['avg_pnl']:+.2f}" if attribution["avg_pnl"] is not None else "  Avg P&L: N/A")
    else:
        lines.append(f"  Total signals: {attribution['total_signals']}  |  None resolved yet.")
    lines.append("")

    # Emerging insiders
    if emerging:
        lines.append("## Emerging Insiders (Promotion Candidates)")
        for e in emerging:
            lines.append(f"  {e['alias']} — {e['dominant_category']}: edge={e['mean_edge']:.4f}, n={e['n_bets']}, p={e['p_value']:.6f}")
    else:
        lines.append("## Emerging Insiders")
        lines.append("  No new accounts qualify for promotion.")
    lines.append("")

    return "\n".join(lines)


# --- Main pipeline ---


def run_decay_analysis(insiders, edge_profiles, follow_signals, dry_run=False, bootstrap=False):
    """
    Run full decay analysis on all insiders.
    Returns (analysis_results, events, updated_insiders, attribution, emerging).
    """
    now = datetime.now(timezone.utc)
    analysis_results = []
    events = []
    trades = load_jsonl(TRADES_PATH)

    for insider in insiders:
        wallet = insider.get("wallet", "")
        alias = insider.get("alias", "")
        dominant_cat = insider.get("dominant_category", "UNK")
        old_state = insider.get("registry_state", "ACTIVE")
        old_conf = insider.get("follow_confidence", 3)

        # Find this wallet's trades in edge profiles
        wallet_profile = None
        for ep in edge_profiles:
            if ep.get("wallet") == wallet:
                wallet_profile = ep
                break

        wallet_trades = wallet_profile.get("trades", []) if wallet_profile else []

        # Rolling edge analysis
        rolling = rolling_edge(wallet_trades, dominant_cat, window_days=90, reference_date=now)

        # Historical max edge
        valid_edges = [r["mean_edge"] for r in rolling if r["mean_edge"] is not None]
        hist_max = max(valid_edges) if valid_edges else 0

        # Classify decay
        pattern, description = classify_decay(rolling, hist_max)

        # Inactivity check
        inactive, inact_msg = check_inactivity(insider, now)

        # Confidence update
        delta, reasons = compute_confidence_delta(insider, pattern, rolling, follow_signals, now)
        new_conf, new_state, cycles_at_min, event = apply_confidence(insider, delta, reasons)

        # Update insider record
        insider["follow_confidence"] = new_conf
        insider["registry_state"] = new_state
        insider["confidence_trend"] = valid_edges
        insider["last_decay_check"] = now.isoformat()
        insider["_cycles_at_min"] = cycles_at_min

        result = {
            "wallet": wallet,
            "alias": alias,
            "old_state": old_state,
            "new_state": new_state,
            "old_confidence": old_conf,
            "new_confidence": new_conf,
            "decay_pattern": pattern,
            "decay_description": description,
            "rolling_windows": rolling,
            "inactivity_msg": inact_msg,
            "confidence_reasons": reasons,
        }
        analysis_results.append(result)

        if event:
            events.append(event)

    # L04 attribution
    attribution = l04_attribution(follow_signals, trades)

    # Emerging insider check
    registry_wallets = {i.get("wallet") for i in insiders}
    emerging = check_emerging(edge_profiles, insiders)

    return analysis_results, events, insiders, attribution, emerging


def main():
    parser = argparse.ArgumentParser(
        description="L05 Decay Monitor — Signal Freshness and Edge Degradation"
    )
    parser.add_argument("--bootstrap", action="store_true",
                        help="Run with synthesized sample data (no L01-L04 files needed)")
    parser.add_argument("--wallet", type=str, default=None,
                        help="Deep-dive a single wallet address")
    parser.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="Analysis only — don't update any files")
    args = parser.parse_args()

    # Route status messages to stderr when --json so stdout is clean JSON
    log = (lambda msg: print(msg, file=sys.stderr)) if args.json else print

    # --- Load data ---

    if args.bootstrap:
        log("=== BOOTSTRAP MODE — using synthesized data ===\n")
        edge_profiles, insiders, follow_signals = generate_bootstrap_data()
    else:
        insiders = load_json(CLASSIFIED_INSIDERS_PATH, default=None)
        if insiders is None:
            log(f"ERROR: {CLASSIFIED_INSIDERS_PATH} not found.")
            log("Run L01-L03 first, or use --bootstrap for testing.")
            sys.exit(1)
        edge_profiles = load_json(EDGE_PROFILES_PATH, default=[])
        follow_signals = load_jsonl(FOLLOW_SIGNALS_PATH)

    # --- Filter to single wallet if requested ---

    if args.wallet:
        insiders = [i for i in insiders if i.get("wallet", "").lower() == args.wallet.lower()]
        if not insiders:
            print(f"ERROR: Wallet {args.wallet} not found in registry.")
            sys.exit(1)

    # --- Run analysis ---

    analysis_results, events, updated_insiders, attribution, emerging = run_decay_analysis(
        insiders, edge_profiles, follow_signals, dry_run=args.dry_run, bootstrap=args.bootstrap
    )

    # --- Output ---

    if args.json:
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "bootstrap" if args.bootstrap else "live",
            "analysis": analysis_results,
            "events": events,
            "attribution": attribution,
            "emerging": emerging,
        }
        print(json.dumps(output, indent=2))
    else:
        report = generate_report(
            updated_insiders, edge_profiles, follow_signals,
            analysis_results, attribution, emerging
        )
        print(report)

    # --- Persist changes ---

    if not args.dry_run and not args.wallet:
        if args.bootstrap:
            # In bootstrap mode, write sample files to demonstrate format
            log("\n--- Writing bootstrap data files ---")
            save_json(CLASSIFIED_INSIDERS_PATH, updated_insiders)
            # Write edge profiles
            save_json(EDGE_PROFILES_PATH, edge_profiles)
            # Write follow signals
            with open(FOLLOW_SIGNALS_PATH, "w") as f:
                for s in follow_signals:
                    f.write(json.dumps(s) + "\n")
            log(f"  Written: {FOLLOW_SIGNALS_PATH}")
        else:
            # Live mode: update classified insiders in place
            save_json(CLASSIFIED_INSIDERS_PATH, updated_insiders)

        # Append events to registry log
        for event in events:
            append_jsonl(REGISTRY_EVENTS_PATH, event)
        if events:
            log(f"  Appended {len(events)} events to: {REGISTRY_EVENTS_PATH}")
        else:
            log("  No registry events to log (no state changes).")
    elif args.dry_run:
        log("\n--- DRY RUN: no files updated ---")

    # --- Summary stats ---

    if not args.json:
        active = sum(1 for r in analysis_results if r["new_state"] == "ACTIVE")
        watching = sum(1 for r in analysis_results if r["new_state"] == "WATCHING")
        archived = sum(1 for r in analysis_results if r["new_state"] == "ARCHIVED")
        changed = sum(1 for r in analysis_results if r["old_state"] != r["new_state"])
        log(f"\nDone. {len(analysis_results)} insiders analyzed. "
            f"Active={active} Watching={watching} Archived={archived} "
            f"State changes={changed}.")


if __name__ == "__main__":
    main()
