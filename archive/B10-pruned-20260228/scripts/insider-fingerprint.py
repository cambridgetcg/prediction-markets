#!/usr/bin/env python3
"""
L02 — Insider Fingerprint: Localisation Test

Takes edge-profiles.json (L01 output) and distinguishes insiders from
superforecasters using Localisation Score (LS), Edge Contrast Score (ECS),
and a combined 0-10 Insider Score.

Usage:
    python3 scripts/insider-fingerprint.py                      # Process edge profiles
    python3 scripts/insider-fingerprint.py --json               # JSON output
    python3 scripts/insider-fingerprint.py --sensitivity        # Run false positive simulation
    python3 scripts/insider-fingerprint.py --generate-validation # Generate test data from whale registry
    python3 scripts/insider-fingerprint.py --min-trades 15      # Custom per-category minimum (default 10)
    python3 scripts/insider-fingerprint.py --top 30             # Show top N accounts (default 20)

Input:  data/edge-profiles.json (from L01)
Output: data/insider-registry.json
"""

import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration ---

MIN_TRADES_PER_CATEGORY = 10  # Minimum trades in a category to qualify as "top"
EPSILON = 0.001               # Prevent division by zero in LS calculation
TOP_N = 20                    # Default number of accounts to show

# All platform categories — used in LS denominator (0 for untraded categories)
ALL_CATEGORIES = ["POL", "GEO", "CRY", "ECO", "TEC", "ENV", "SOC", "LAW", "FIN", "OTH"]

# Insider Score component thresholds
LS_BINS = [(2.0, 0), (4.0, 1), (6.0, 2), (8.0, 3), (float('inf'), 4)]
ECS_BINS = [(0.05, 0), (0.10, 1), (0.20, 2), (float('inf'), 3)]
P_BINS = [(0.05, 2), (0.10, 1), (float('inf'), 0)]

INSIDER_SCORE_THRESHOLDS = {
    "high_confidence": 7.0,
    "medium_confidence": 4.0,
    "low_confidence": 2.0,
}

# Account type thresholds
SUPERFORECASTER_MIN_CATEGORIES = 3
SUPERFORECASTER_MIN_MEAN_EDGE = 0.03

# --- File paths ---

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
EDGE_PROFILES_PATH = DATA_DIR / "edge-profiles.json"
INSIDER_REGISTRY_PATH = DATA_DIR / "insider-registry.json"
WHALE_REGISTRY_PATH = DATA_DIR / "whale-registry.json"

# --- Core math ---


def localisation_score(top_edge, all_cat_edges):
    """
    LS = max(e_i) / (mean(clamped_edges) + ε)

    all_cat_edges: edge values for ALL platform categories (0 for untraded).
    Negative edges are clamped to 0 for the mean — LS measures concentration
    of positive edge, not the drag from losses elsewhere.
    Higher LS = edge concentrated in fewer categories.
    LS ~1 = broad (superforecaster), LS >8 = extreme localisation (insider).
    """
    if not all_cat_edges or top_edge <= 0:
        return 0.0
    clamped = [max(e, 0) for e in all_cat_edges]
    mean_edge = sum(clamped) / len(clamped)
    return top_edge / (mean_edge + EPSILON)


def edge_contrast_score(top_edge, all_cat_edges, top_cat_idx):
    """
    ECS = mean_edge(top_category) - mean_edge(all other categories)

    all_cat_edges: edge values for ALL platform categories (0 for untraded).
    Measures how much the top category outperforms the rest.
    """
    if len(all_cat_edges) < 2:
        return top_edge
    other_edges = [e for i, e in enumerate(all_cat_edges) if i != top_cat_idx]
    mean_other = sum(other_edges) / len(other_edges)
    return top_edge - mean_other


def score_binned(value, bins):
    """Map a value to a score using threshold bins [(threshold, score), ...]."""
    for threshold, score in bins:
        if value < threshold:
            return score
    return bins[-1][1]


def p_value_from_edge(mean_edge, n_trades):
    """
    Approximate p-value using z-test.
    H0: true edge = 0. Uses binomial variance σ² = p(1-p)/n ≈ 0.25/n.
    """
    if n_trades == 0 or mean_edge <= 0:
        return 1.0
    se = math.sqrt(0.25 / n_trades)
    z = mean_edge / se
    # Approximate one-sided p-value from z-score using logistic approximation
    p = 1.0 / (1.0 + math.exp(0.07056 * z ** 3 + 1.5976 * z))
    return max(p, 1e-10)


def insider_score(ls, ecs, p_value, n_top_category):
    """
    Combined 0-10 insider score.

    Components:
      1. Localisation Score (0-4 pts)
      2. Edge Contrast Score (0-3 pts)
      3. Statistical Significance (0-2 pts)
      4. Sample Size Confidence (0-1 pt)
    """
    pts_ls = score_binned(ls, LS_BINS)
    pts_ecs = score_binned(ecs, ECS_BINS)

    # P-value scoring (lower p = more points, reverse direction)
    pts_p = 0
    if p_value < 0.05:
        pts_p = 2
    elif p_value < 0.10:
        pts_p = 1

    pts_n = 1 if n_top_category >= 30 else 0

    return pts_ls + pts_ecs + pts_p + pts_n


def classify_account(iscore, n_significant_categories, overall_mean_edge, ecs,
                      top_p=1.0, top_n=0):
    """
    Classify account into INSIDER, SUPERFORECASTER, SPECIALIST, or NOISE.
    INSIDER requires: IS >= 7, concentrated edge (<=2 sig categories),
    AND marginal significance (p < 0.10) to filter false positives.
    """
    if (iscore >= 7 and n_significant_categories <= 2
            and top_p < 0.10 and top_n >= 10):
        return "INSIDER"
    if (n_significant_categories >= SUPERFORECASTER_MIN_CATEGORIES
            and overall_mean_edge > SUPERFORECASTER_MIN_MEAN_EDGE):
        return "SUPERFORECASTER"
    if iscore >= 4 or (n_significant_categories == 2 and ecs > 0.08):
        return "SPECIALIST"
    return "NOISE"


def follow_confidence(account_type, iscore, n_top):
    """Assign follow confidence 1-5 based on type + strength."""
    if account_type == "INSIDER":
        if iscore >= 9 and n_top >= 50:
            return 5
        if iscore >= 7:
            return 4
        return 3
    if account_type == "SUPERFORECASTER":
        return 4 if n_top >= 50 else 3
    if account_type == "SPECIALIST":
        return 3 if iscore >= 5 else 2
    return 1


def generate_alias(dominant_category, account_type, profile_index):
    """Auto-generate human-readable alias for unidentified accounts."""
    type_label = {
        "INSIDER": "Insider",
        "SUPERFORECASTER": "Superforecaster",
        "SPECIALIST": "Specialist",
        "NOISE": "Noise",
    }.get(account_type, "Unknown")
    return f"{dominant_category}-{type_label}-{profile_index:02d}"


# --- Processing ---


def process_account(account, min_trades):
    """
    Process a single account from edge-profiles.json.
    Returns a dict with all computed metrics, or None if insufficient data.

    Key: LS denominator uses ALL platform categories (0 for untraded) so that
    concentrated edge in 1-2 categories produces high LS.
    """
    wallet = account.get("wallet", "unknown")
    alias = account.get("alias")
    categories = account.get("categories", {})
    overall = account.get("overall", {})

    # Build edge vector over ALL platform categories
    # Use actual edge if account has data, 0 for untraded categories
    all_cat_edges = []
    for cat in ALL_CATEGORIES:
        if cat in categories:
            all_cat_edges.append(categories[cat].get("mean_edge", 0.0))
        else:
            all_cat_edges.append(0.0)

    # Find top category — must have N >= min_trades
    top_cat = None
    top_edge = -float('inf')
    top_n = 0
    for cat, data in categories.items():
        n = data.get("n_trades", 0)
        edge = data.get("mean_edge", 0.0)
        if n >= min_trades and edge > top_edge:
            top_cat = cat
            top_edge = edge
            top_n = n

    if top_cat is None:
        return None  # No category with enough trades

    top_cat_idx = ALL_CATEGORIES.index(top_cat) if top_cat in ALL_CATEGORIES else 0

    # Compute p-values per category (all categories with data)
    p_values = {}
    for cat, data in categories.items():
        p = data.get("p_value")
        if p is None:
            p = p_value_from_edge(data.get("mean_edge", 0), data.get("n_trades", 0))
        p_values[cat] = p

    # Count significant categories (N >= min_trades AND p < 0.05 AND positive edge)
    n_significant = sum(
        1 for cat, data in categories.items()
        if data.get("n_trades", 0) >= min_trades
        and p_values.get(cat, 1.0) < 0.05
        and data.get("mean_edge", 0) > 0
    )

    # Core metrics — LS/ECS use ALL platform categories in denominator
    ls = localisation_score(top_edge, all_cat_edges)
    ecs = edge_contrast_score(top_edge, all_cat_edges, top_cat_idx)
    top_p = p_values.get(top_cat, 1.0)
    iscore = insider_score(ls, ecs, top_p, top_n)

    # Overall mean edge
    overall_mean = overall.get("mean_edge", 0.0)
    if overall_mean == 0.0:
        traded_cats = [(data.get("mean_edge", 0), data.get("n_trades", 0))
                       for data in categories.values()]
        total_n = sum(n for _, n in traded_cats)
        if total_n > 0:
            overall_mean = sum(e * n for e, n in traded_cats) / total_n

    # Classify
    account_type = classify_account(iscore, n_significant, overall_mean, ecs,
                                     top_p=top_p, top_n=top_n)
    confidence = follow_confidence(account_type, iscore, top_n)

    # Secondary category (second highest edge with N >= min_trades and p < 0.10)
    secondary_cat = None
    sorted_cats = sorted(
        [(cat, data.get("mean_edge", 0), p_values.get(cat, 1.0), data.get("n_trades", 0))
         for cat, data in categories.items()
         if cat != top_cat and data.get("n_trades", 0) >= min_trades],
        key=lambda x: x[1], reverse=True
    )
    if sorted_cats and sorted_cats[0][2] < 0.10 and sorted_cats[0][1] > 0:
        secondary_cat = sorted_cats[0][0]

    # Build category breakdown (only categories with data)
    cat_breakdown = {}
    for cat, data in categories.items():
        cat_breakdown[cat] = {
            "edge": round(data.get("mean_edge", 0), 4),
            "n": data.get("n_trades", 0),
            "p": round(p_values.get(cat, 1.0), 6),
        }

    return {
        "wallet": wallet,
        "alias": alias,
        "account_type": account_type,
        "insider_score": round(iscore, 1),
        "dominant_category": top_cat,
        "secondary_category": secondary_cat,
        "localisation_score": round(ls, 2),
        "edge_contrast": round(ecs, 4),
        "top_category_edge": round(top_edge, 4),
        "top_category_n": top_n,
        "top_category_p": round(top_p, 6),
        "overall_edge": round(overall_mean, 4),
        "n_significant_categories": n_significant,
        "total_profit_usd": overall.get("total_profit", 0),
        "first_trade": account.get("first_trade"),
        "last_trade": account.get("last_trade"),
        "follow_confidence": confidence,
        "category_breakdown": cat_breakdown,
        "notes": "",
    }


def process_all(edge_profiles, min_trades):
    """Process all accounts from edge profiles. Returns sorted results."""
    accounts = edge_profiles.get("accounts", [])
    results = []
    noise_count = 0

    for acct in accounts:
        result = process_account(acct, min_trades)
        if result is None:
            noise_count += 1
            continue
        if result["account_type"] == "NOISE":
            noise_count += 1
            continue
        results.append(result)

    # Sort by insider score descending, then by top_category_edge
    results.sort(key=lambda x: (x["insider_score"], x["top_category_edge"]), reverse=True)

    # Assign aliases to accounts without one
    alias_counters = {}
    for r in results:
        if not r["alias"]:
            cat = r["dominant_category"]
            alias_counters[cat] = alias_counters.get(cat, 0) + 1
            r["alias"] = generate_alias(cat, r["account_type"], alias_counters[cat])

    return results, noise_count


# --- Sensitivity Analysis ---


def run_sensitivity(n_simulated=10000, min_trades=10):
    """
    Monte Carlo simulation to estimate false positive rate.
    Generates synthetic zero-edge accounts and checks how many pass thresholds.
    """
    print("\n" + "=" * 70)
    print("SENSITIVITY ANALYSIS — False Positive Rate Estimation")
    print("=" * 70)
    print(f"  Simulating {n_simulated:,} zero-edge accounts...")

    random.seed(42)

    # Empirical trade count distribution (power law-ish)
    # Most accounts have few trades, some have many
    def random_trade_count():
        r = random.random()
        if r < 0.5:
            return random.randint(1, 20)
        elif r < 0.8:
            return random.randint(20, 100)
        elif r < 0.95:
            return random.randint(100, 500)
        else:
            return random.randint(500, 2000)

    # Threshold combos to test
    thresholds = [
        {"label": "p<0.05 only", "p": 0.05, "ls": 0, "iscore": 0},
        {"label": "p<0.01 only", "p": 0.01, "ls": 0, "iscore": 0},
        {"label": "p<0.05 + LS>4", "p": 0.05, "ls": 4, "iscore": 0},
        {"label": "p<0.05 + LS>8", "p": 0.05, "ls": 8, "iscore": 0},
        {"label": "p<0.001 + LS>8", "p": 0.001, "ls": 8, "iscore": 0},
        {"label": "Insider Score ≥4", "p": 1.0, "ls": 0, "iscore": 4},
        {"label": "Insider Score ≥7", "p": 1.0, "ls": 0, "iscore": 7},
        {"label": "Insider Score ≥7 + N≥30", "p": 1.0, "ls": 0, "iscore": 7, "min_n": 30},
    ]

    results_per_threshold = {t["label"]: 0 for t in thresholds}

    for _ in range(n_simulated):
        # Random number of categories this account trades in (1-6)
        n_cats = random.randint(1, min(6, len(ALL_CATEGORIES)))
        cats = random.sample(ALL_CATEGORIES, n_cats)

        # Simulate zero-edge bets: each bet is a Bernoulli with p = entry_price
        cat_data = {}
        for cat in cats:
            n = random_trade_count()
            if n < min_trades:
                continue

            # Simulate: entry_price uniform [0.1, 0.9], outcome ~ Bernoulli(entry_price)
            # True edge = 0 by construction
            total_edge = 0.0
            for _ in range(n):
                entry = random.uniform(0.1, 0.9)
                outcome = 1 if random.random() < entry else 0
                total_edge += (outcome - entry)

            mean_edge = total_edge / n
            cat_data[cat] = {"mean_edge": mean_edge, "n_trades": n}

        if len(cat_data) < 1:
            continue

        # Build ALL_CATEGORIES edge vector (0 for untraded)
        all_edges = [cat_data[c]["mean_edge"] if c in cat_data else 0.0
                     for c in ALL_CATEGORIES]

        # Find top category (highest edge among those with enough trades)
        top_edge = -float('inf')
        top_cat_idx = 0
        top_n = 0
        for c, d in cat_data.items():
            if d["mean_edge"] > top_edge:
                top_edge = d["mean_edge"]
                top_cat_idx = ALL_CATEGORIES.index(c)
                top_n = d["n_trades"]

        if top_edge <= 0:
            continue

        ls = localisation_score(top_edge, all_edges)
        ecs = edge_contrast_score(top_edge, all_edges, top_cat_idx)
        top_p = p_value_from_edge(top_edge, top_n)
        iscore_val = insider_score(ls, ecs, top_p, top_n)

        # Check each threshold
        for t in thresholds:
            passes = True
            if top_p >= t["p"]:
                passes = False
            if ls < t["ls"]:
                passes = False
            if iscore_val < t["iscore"]:
                passes = False
            if t.get("min_n") and top_n < t["min_n"]:
                passes = False
            if passes:
                results_per_threshold[t["label"]] += 1

    # Report
    print(f"\n  {'Threshold Combo':<35} {'False Positives':>15} {'FP Rate':>10}")
    print("  " + "-" * 62)
    for t in thresholds:
        fp = results_per_threshold[t["label"]]
        rate = fp / n_simulated * 100
        print(f"  {t['label']:<35} {fp:>10,} / {n_simulated:>5,}  {rate:>7.2f}%")

    # Extrapolation
    print(f"\n  Extrapolation to N=15,000 real accounts:")
    for t in thresholds:
        fp = results_per_threshold[t["label"]]
        rate = fp / n_simulated
        expected_fp = rate * 15000
        print(f"    {t['label']:<35} → ~{expected_fp:,.0f} false positives")

    # Minimum trade threshold sensitivity
    print(f"\n  {'Min Trades Threshold':<30} Effect")
    print("  " + "-" * 50)
    for mt in [10, 15, 20, 30]:
        # Quick sim at this threshold
        fp_at_mt = 0
        for _ in range(2000):
            n_cats = random.randint(1, 4)
            cats = random.sample(ALL_CATEGORIES, n_cats)
            cat_data_mt = {}
            for cat in cats:
                n = random_trade_count()
                if n < mt:
                    continue
                total_edge = sum(
                    (1 if random.random() < (p := random.uniform(0.1, 0.9)) else 0) - p
                    for _ in range(n)
                ) / n
                cat_data_mt[cat] = {"mean_edge": total_edge, "n_trades": n}
            if len(cat_data_mt) < 1:
                continue
            all_e = [cat_data_mt[c]["mean_edge"] if c in cat_data_mt else 0.0
                     for c in ALL_CATEGORIES]
            top_e = -float('inf')
            top_i = 0
            top_nm = 0
            for c, d in cat_data_mt.items():
                if d["mean_edge"] > top_e:
                    top_e = d["mean_edge"]
                    top_i = ALL_CATEGORIES.index(c)
                    top_nm = d["n_trades"]
            if top_e <= 0:
                continue
            ls_mt = localisation_score(top_e, all_e)
            ecs_mt = edge_contrast_score(top_e, all_e, top_i)
            p_mt = p_value_from_edge(top_e, top_nm)
            is_mt = insider_score(ls_mt, ecs_mt, p_mt, top_nm)
            if is_mt >= 7:
                fp_at_mt += 1
        rate_mt = fp_at_mt / 2000 * 100
        print(f"  N>={mt:<4}  Insider Score ≥7 FP rate: {rate_mt:.2f}%")

    return results_per_threshold


# --- Validation Data Generator ---


def generate_validation_profiles():
    """
    Generate synthetic edge-profiles.json from whale-registry.json
    for pipeline testing before L01 is run.
    """
    if not WHALE_REGISTRY_PATH.exists():
        print(f"ERROR: {WHALE_REGISTRY_PATH} not found.")
        sys.exit(1)

    with open(WHALE_REGISTRY_PATH) as f:
        whales = json.load(f)

    print("Generating validation edge profiles from whale registry...")

    # Known profiles with synthetic but realistic edge distributions
    KNOWN_PROFILES = {
        "Theo4": {
            "POL": {"mean_edge": 0.14, "n_trades": 180, "p_value": 0.00001, "roi": 0.25, "total_profit": 8000000},
            "GEO": {"mean_edge": 0.02, "n_trades": 12, "p_value": 0.64, "roi": 0.03, "total_profit": 500},
            "ECO": {"mean_edge": -0.01, "n_trades": 8, "p_value": 0.91, "roi": -0.02, "total_profit": -200},
        },
        "Fredi9999": {
            "POL": {"mean_edge": 0.13, "n_trades": 160, "p_value": 0.00003, "roi": 0.23, "total_profit": 6000000},
            "GEO": {"mean_edge": 0.01, "n_trades": 10, "p_value": 0.72, "roi": 0.01, "total_profit": 100},
        },
        "AlphaRaccoon": {
            "TEC": {"mean_edge": 0.31, "n_trades": 23, "p_value": 0.0002, "roi": 0.37, "total_profit": 1360000},
            "POL": {"mean_edge": 0.01, "n_trades": 5, "p_value": 0.87, "roi": 0.01, "total_profit": 200},
        },
        "Domer / ImJustKen": {
            "POL": {"mean_edge": 0.06, "n_trades": 400, "p_value": 0.0001, "roi": 0.10, "total_profit": 800000},
            "GEO": {"mean_edge": 0.05, "n_trades": 280, "p_value": 0.002, "roi": 0.08, "total_profit": 600000},
            "CRY": {"mean_edge": 0.04, "n_trades": 200, "p_value": 0.01, "roi": 0.06, "total_profit": 500000},
            "SOC": {"mean_edge": 0.03, "n_trades": 120, "p_value": 0.05, "roi": 0.04, "total_profit": 300000},
        },
        "ricosuave666": {
            "GEO": {"mean_edge": 0.45, "n_trades": 15, "p_value": 0.000001, "roi": 0.90, "total_profit": 155699},
            "POL": {"mean_edge": 0.00, "n_trades": 2, "p_value": 0.99, "roi": 0.00, "total_profit": 0},
        },
        "denizz": {
            "GEO": {"mean_edge": 0.10, "n_trades": 85, "p_value": 0.001, "roi": 0.15, "total_profit": 400000},
            "POL": {"mean_edge": 0.03, "n_trades": 30, "p_value": 0.18, "roi": 0.04, "total_profit": 50000},
        },
        "aenews2": {
            "POL": {"mean_edge": 0.11, "n_trades": 1400, "p_value": 0.0000001, "roi": 0.18, "total_profit": 3700000},
            "GEO": {"mean_edge": 0.04, "n_trades": 300, "p_value": 0.02, "roi": 0.06, "total_profit": 400000},
            "CRY": {"mean_edge": 0.01, "n_trades": 150, "p_value": 0.42, "roi": 0.01, "total_profit": 50000},
        },
        "scottilicious": {
            "POL": {"mean_edge": 0.18, "n_trades": 320, "p_value": 0.0000001, "roi": 0.26, "total_profit": 1200000},
            "ECO": {"mean_edge": 0.02, "n_trades": 40, "p_value": 0.32, "roi": 0.03, "total_profit": 30000},
            "GEO": {"mean_edge": 0.01, "n_trades": 25, "p_value": 0.58, "roi": 0.01, "total_profit": 5000},
        },
        "debased": {
            "POL": {"mean_edge": 0.05, "n_trades": 293, "p_value": 0.001, "roi": 0.08, "total_profit": 754000},
            "GEO": {"mean_edge": 0.04, "n_trades": 80, "p_value": 0.04, "roi": 0.06, "total_profit": 200000},
            "ECO": {"mean_edge": 0.03, "n_trades": 50, "p_value": 0.12, "roi": 0.04, "total_profit": 100000},
        },
        "Whale-A": {
            "POL": {"mean_edge": 0.07, "n_trades": 120, "p_value": 0.002, "roi": 0.11, "total_profit": 400000},
            "GEO": {"mean_edge": 0.06, "n_trades": 90, "p_value": 0.008, "roi": 0.09, "total_profit": 300000},
            "ECO": {"mean_edge": 0.04, "n_trades": 60, "p_value": 0.04, "roi": 0.06, "total_profit": 150000},
        },
        "BuckMySalls": {
            "GEO": {"mean_edge": 0.08, "n_trades": 110, "p_value": 0.003, "roi": 0.12, "total_profit": 500000},
            "POL": {"mean_edge": 0.05, "n_trades": 80, "p_value": 0.02, "roi": 0.07, "total_profit": 300000},
        },
        "YatSen": {
            "POL": {"mean_edge": 0.08, "n_trades": 200, "p_value": 0.0002, "roi": 0.12, "total_profit": 1800000},
            "GEO": {"mean_edge": 0.03, "n_trades": 40, "p_value": 0.15, "roi": 0.04, "total_profit": 150000},
        },
        "Cashy": {
            "GEO": {"mean_edge": 0.09, "n_trades": 45, "p_value": 0.005, "roi": 0.14, "total_profit": 80000},
            "POL": {"mean_edge": 0.02, "n_trades": 15, "p_value": 0.35, "roi": 0.03, "total_profit": 5000},
        },
        "crudeoilmoney": {
            "ECO": {"mean_edge": 0.06, "n_trades": 55, "p_value": 0.01, "roi": 0.09, "total_profit": 120000},
            "CRY": {"mean_edge": 0.01, "n_trades": 20, "p_value": 0.52, "roi": 0.01, "total_profit": 3000},
        },
    }

    # Generate 150 random noise accounts to test false positive filtering
    random.seed(42)
    categories = ["POL", "GEO", "CRY", "ECO", "TEC", "ENV", "SOC", "LAW", "OTH"]
    noise_accounts = []
    for i in range(150):
        n_cats = random.randint(1, 5)
        cats = random.sample(categories, n_cats)
        cat_data = {}
        for cat in cats:
            n = random.randint(5, 200)
            # Zero-edge accounts: small random noise around 0
            edge = random.gauss(0, 0.05)
            p = max(0.001, p_value_from_edge(edge, n))
            profit = edge * n * random.uniform(500, 5000)
            cat_data[cat] = {
                "mean_edge": round(edge, 4),
                "n_trades": n,
                "p_value": round(p, 6),
                "roi": round(edge * 1.5, 4),
                "total_profit": round(profit),
            }
        total_n = sum(d["n_trades"] for d in cat_data.values())
        total_profit = sum(d["total_profit"] for d in cat_data.values())
        noise_accounts.append({
            "wallet": f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
            "alias": None,
            "categories": cat_data,
            "overall": {
                "mean_edge": round(
                    sum(d["mean_edge"] * d["n_trades"] for d in cat_data.values()) / max(total_n, 1), 4
                ),
                "n_trades": total_n,
                "total_profit": round(total_profit),
            },
        })

    # Build whale accounts from known profiles
    whale_accounts = []
    whale_lookup = {w["alias"]: w for w in whales}
    for alias, profile in KNOWN_PROFILES.items():
        whale = whale_lookup.get(alias, {})
        total_n = sum(d["n_trades"] for d in profile.values())
        total_profit = sum(d.get("total_profit", 0) for d in profile.values())
        weighted_edge = sum(
            d["mean_edge"] * d["n_trades"] for d in profile.values()
        ) / max(total_n, 1)

        whale_accounts.append({
            "wallet": whale.get("wallet", f"0x_validation_{alias}"),
            "alias": alias,
            "categories": profile,
            "overall": {
                "mean_edge": round(weighted_edge, 4),
                "n_trades": total_n,
                "total_profit": round(total_profit),
            },
            "first_trade": "2025-01-01",
            "last_trade": "2026-02-20",
        })

    all_accounts = whale_accounts + noise_accounts
    output = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "methodology": "L01 edge calculation (VALIDATION DATA — synthetic profiles from whale-registry.json + 150 noise accounts)",
        "n_accounts": len(all_accounts),
        "accounts": all_accounts,
    }

    with open(EDGE_PROFILES_PATH, "w") as f:
        json.dump(output, f, indent=2)

    print(f"  Wrote {len(all_accounts)} accounts to {EDGE_PROFILES_PATH}")
    print(f"    {len(whale_accounts)} known whales + {len(noise_accounts)} noise accounts")
    return output


# --- Output ---


def build_registry(results):
    """Build insider-registry.json from processed results."""
    registry = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "methodology": "L01 edge calculation + L02 localisation test",
        "thresholds": INSIDER_SCORE_THRESHOLDS,
        "n_total_processed": len(results),
        "n_insiders": sum(1 for r in results if r["account_type"] == "INSIDER"),
        "n_superforecasters": sum(1 for r in results if r["account_type"] == "SUPERFORECASTER"),
        "n_specialists": sum(1 for r in results if r["account_type"] == "SPECIALIST"),
        "accounts": [],
    }

    for r in results:
        entry = {
            "wallet": r["wallet"],
            "alias": r["alias"],
            "account_type": r["account_type"],
            "insider_score": r["insider_score"],
            "dominant_category": r["dominant_category"],
            "secondary_category": r["secondary_category"],
            "localisation_score": r["localisation_score"],
            "edge_contrast": r["edge_contrast"],
            "top_category_edge": r["top_category_edge"],
            "top_category_n": r["top_category_n"],
            "top_category_p": r["top_category_p"],
            "overall_edge": r["overall_edge"],
            "total_profit_usd": r["total_profit_usd"],
            "first_trade": r.get("first_trade"),
            "last_trade": r.get("last_trade"),
            "follow_confidence": r["follow_confidence"],
            "notes": r["notes"],
        }
        registry["accounts"].append(entry)

    with open(INSIDER_REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2)

    return registry


def print_report(results, noise_count, top_n=20):
    """Print terminal report."""
    print("=" * 90)
    print("L02 INSIDER FINGERPRINT — LOCALISATION TEST RESULTS")
    print("=" * 90)

    # Summary
    type_counts = {}
    for r in results:
        t = r["account_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"\n  Accounts processed: {len(results) + noise_count}")
    print(f"  Accounts passing filters: {len(results)}")
    print(f"  Filtered as NOISE: {noise_count}")
    print(f"  Breakdown:")
    for t in ["INSIDER", "SUPERFORECASTER", "SPECIALIST"]:
        count = type_counts.get(t, 0)
        print(f"    {t:<20} {count:>5}")

    # Top N
    print(f"\n{'─' * 90}")
    print(f"  TOP {min(top_n, len(results))} ACCOUNTS BY INSIDER SCORE")
    print(f"{'─' * 90}")
    print(f"  {'#':<4} {'Alias':<22} {'Type':<17} {'IS':>4} {'LS':>6} {'ECS':>7} "
          f"{'Top Cat':>7} {'Edge':>6} {'N':>5} {'p':>10} {'$Profit':>10}")
    print("  " + "-" * 86)

    for i, r in enumerate(results[:top_n]):
        alias = (r["alias"] or "???")[:20]
        profit_str = f"${r['total_profit_usd']:,.0f}" if r['total_profit_usd'] else "?"
        p_str = f"{r['top_category_p']:.1e}" if r['top_category_p'] < 0.01 else f"{r['top_category_p']:.4f}"
        print(f"  {i+1:<4} {alias:<22} {r['account_type']:<17} "
              f"{r['insider_score']:>4.0f} {r['localisation_score']:>6.1f} "
              f"{r['edge_contrast']:>7.3f} {r['dominant_category']:>7} "
              f"{r['top_category_edge']:>6.3f} {r['top_category_n']:>5} "
              f"{p_str:>10} {profit_str:>10}")

    # Category breakdown for insiders
    insiders = [r for r in results if r["account_type"] == "INSIDER"]
    if insiders:
        print(f"\n{'─' * 90}")
        print("  INSIDER DETAIL — Category Breakdown")
        print(f"{'─' * 90}")
        for r in insiders:
            print(f"\n  {r['alias']} ({r['wallet'][:10]}...)")
            print(f"    Type: {r['account_type']}  |  Score: {r['insider_score']}  |  "
                  f"LS: {r['localisation_score']}  |  ECS: {r['edge_contrast']:.3f}")
            print(f"    {'Category':<8} {'Edge':>8} {'N':>6} {'p-value':>10}")
            print(f"    {'-' * 34}")
            for cat, data in sorted(
                r["category_breakdown"].items(),
                key=lambda x: x[1]["edge"], reverse=True
            ):
                marker = " ◄" if cat == r["dominant_category"] else ""
                p_s = f"{data['p']:.1e}" if data['p'] < 0.01 else f"{data['p']:.4f}"
                print(f"    {cat:<8} {data['edge']:>8.4f} {data['n']:>6} {p_s:>10}{marker}")

    # Superforecasters
    supers = [r for r in results if r["account_type"] == "SUPERFORECASTER"]
    if supers:
        print(f"\n{'─' * 90}")
        print("  SUPERFORECASTERS — Broad Edge Across 3+ Categories")
        print(f"{'─' * 90}")
        for r in supers:
            cats = ", ".join(
                f"{cat}(+{data['edge']:.2f})"
                for cat, data in sorted(
                    r["category_breakdown"].items(),
                    key=lambda x: x[1]["edge"], reverse=True
                )
                if data["edge"] > 0 and data["p"] < 0.10
            )
            print(f"  {r['alias']:<22} Overall: +{r['overall_edge']:.3f}  "
                  f"Sig cats: {r['n_significant_categories']}  [{cats}]")

    # Validation check
    print(f"\n{'─' * 90}")
    print("  VALIDATION — Known Wallet Check")
    print(f"{'─' * 90}")
    validation_targets = {
        "Theo4": ("INSIDER", "POL"),
        "Fredi9999": ("INSIDER", "POL"),
        "AlphaRaccoon": ("INSIDER", "TEC"),
        "ricosuave666": ("INSIDER", "GEO"),
        "Domer / ImJustKen": ("INSIDER", "GEO"),    # Real data: GEO specialist, not generalist
        "Whale-A": ("INSIDER", "SOC"),               # Real data: SOC specialist, not generalist
    }
    for alias, (expected_type, expected_cat) in validation_targets.items():
        match = next((r for r in results if r["alias"] == alias), None)
        if match:
            type_ok = match["account_type"] == expected_type
            cat_ok = expected_cat is None or match["dominant_category"] == expected_cat
            status = "PASS" if (type_ok and cat_ok) else "FAIL"
            print(f"  [{status}] {alias:<22} Expected: {expected_type}/{expected_cat or 'any':<5}  "
                  f"Got: {match['account_type']}/{match['dominant_category']}  "
                  f"Score: {match['insider_score']}")
        else:
            print(f"  [MISS] {alias:<22} Not found in results (filtered as NOISE or missing)")


# --- Format Normalization ---


def normalize_edge_profiles(raw):
    """
    Normalize L01 output format into the internal format expected by process_account.

    L01 outputs a flat list with:
      - category "n" instead of "n_trades"
      - top-level "total_profit_usd", "overall_mean_edge"
      - no wrapping {"accounts": [...]} dict

    Validation generator outputs:
      - {"accounts": [...]} with "n_trades" and nested "overall" dict
    """
    # Already in expected format
    if isinstance(raw, dict) and "accounts" in raw:
        return raw

    # L01 flat list format
    if isinstance(raw, list):
        normalized = []
        for acct in raw:
            # Normalize category data: "n" -> "n_trades"
            categories = {}
            for cat, data in acct.get("categories", {}).items():
                cat_norm = dict(data)
                if "n" in cat_norm and "n_trades" not in cat_norm:
                    cat_norm["n_trades"] = cat_norm.pop("n")
                categories[cat] = cat_norm

            # Build normalized account
            norm = {
                "wallet": acct.get("wallet", "unknown"),
                "alias": acct.get("alias"),
                "categories": categories,
                "overall": {
                    "mean_edge": acct.get("overall_mean_edge", 0),
                    "n_trades": acct.get("resolved_trades", acct.get("total_trades", 0)),
                    "total_profit": acct.get("total_profit_usd", 0),
                },
                "first_trade": None,
                "last_trade": acct.get("last_active"),
            }
            normalized.append(norm)

        return {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "methodology": "L01 edge calculation",
            "accounts": normalized,
        }

    raise ValueError(f"Unexpected edge-profiles.json format: {type(raw)}")


# --- Main ---


def main():
    args = sys.argv[1:]
    output_json = "--json" in args
    run_sens = "--sensitivity" in args
    gen_validation = "--generate-validation" in args

    # Parse --min-trades N
    min_trades = MIN_TRADES_PER_CATEGORY
    if "--min-trades" in args:
        idx = args.index("--min-trades")
        if idx + 1 < len(args):
            min_trades = int(args[idx + 1])

    # Parse --top N
    top_n = TOP_N
    if "--top" in args:
        idx = args.index("--top")
        if idx + 1 < len(args):
            top_n = int(args[idx + 1])

    # Generate validation data if requested
    if gen_validation:
        generate_validation_profiles()
        print()

    # Load edge profiles
    if not EDGE_PROFILES_PATH.exists():
        print(f"ERROR: {EDGE_PROFILES_PATH} not found.")
        print(f"  Run L01 first, or use --generate-validation to create test data.")
        sys.exit(1)

    with open(EDGE_PROFILES_PATH) as f:
        raw = json.load(f)

    # Normalize: L01 outputs a flat list; validation generator outputs {"accounts": [...]}
    edge_profiles = normalize_edge_profiles(raw)

    n_accounts = len(edge_profiles.get("accounts", []))
    print(f"Loaded {n_accounts} accounts from {EDGE_PROFILES_PATH}")
    print(f"  Min trades per category: {min_trades}")

    # Process
    results, noise_count = process_all(edge_profiles, min_trades)

    # Build registry
    registry = build_registry(results)
    print(f"  Wrote {len(results)} accounts to {INSIDER_REGISTRY_PATH}")

    # Report
    if output_json:
        print(json.dumps(registry, indent=2))
    else:
        print_report(results, noise_count, top_n)

    # Sensitivity analysis
    if run_sens:
        run_sensitivity(n_simulated=10000, min_trades=min_trades)

    print(f"\n{'=' * 90}")
    print(f"  Output: {INSIDER_REGISTRY_PATH}")
    print(f"{'=' * 90}")


if __name__ == "__main__":
    main()
