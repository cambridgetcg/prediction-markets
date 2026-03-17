#!/usr/bin/env python3
"""
Market Maker Yield Calculator for Polymarket

Models the three income streams for a Polymarket market maker:
1. Spread capture revenue
2. LP rewards (quadratic scoring)
3. Maker rebates (fee-enabled markets only)

Minus:
- Inventory risk (directional exposure from imbalanced fills)
- Opportunity cost vs. T-bills

Usage:
    python3 scripts/mm-yield-calculator.py [--capital AMOUNT] [--markets N] [--pilot]
"""

import json
import math
import sys

# ============================================================
# Constants
# ============================================================

LP_REWARDS_ANNUAL = 12_000_000       # $12M/year total LP rewards pool
LP_REWARDS_DAILY = LP_REWARDS_ANNUAL / 365  # ~$32,877/day
QUALIFYING_SPREAD_V = 0.03           # Typical qualifying spread parameter (3 cents)
TBILL_ANNUAL_YIELD = 0.053           # 3-month T-bill rate (~5.3% as of Feb 2026)
WINNER_FEE = 0.02                    # 2% fee on winning shares at resolution
CRYPTO_FEE_RATE = 0.25               # Fee rate for crypto markets
CRYPTO_FEE_EXPONENT = 2              # Exponent for crypto fee formula
SPORTS_FEE_RATE = 0.0175             # Fee rate for sports markets
SPORTS_FEE_EXPONENT = 1              # Exponent for sports fee formula
CRYPTO_MAKER_REBATE_PCT = 0.20       # 20% of taker fees
SPORTS_MAKER_REBATE_PCT = 0.25       # 25% of taker fees

# Estimated total maker score across all markets (for LP reward share calc)
# Based on ~$250M total maker liquidity across ~50 active reward markets
# This is a rough estimate — actual value fluctuates
EST_TOTAL_MAKER_SCORE = 500_000_000  # Normalized score units


# ============================================================
# Market Data (from Gamma API, Feb 25 2026)
# ============================================================

CANDIDATE_MARKETS = [
    {
        "name": "Jesus Christ Return (NO)",
        "slug": "jesus-christ-return",
        "mid": 0.0375,                # YES at 3.75%, making on NO side
        "daily_volume": 559_000,
        "liquidity": 5_167_000,
        "spread_observed": 0.001,      # 0.1 cent (extremely tight)
        "daily_price_stdev": 0.002,    # Near-zero movement
        "resolution_date": "2026-12-31",
        "days_to_resolution": 309,
        "fee_enabled": False,
        "domain": "SOC",
        "making_side": "NO",           # We'd be making around 96.25c
        "notes": "Near-certain NO. Ultra-stable. Bot-dominated spreads."
    },
    {
        "name": "Fed Chair - Warsh (YES)",
        "slug": "fed-chair-warsh",
        "mid": 0.939,
        "daily_volume": 446_000,
        "liquidity": 252_000,
        "spread_observed": 0.002,      # 0.2 cent
        "daily_price_stdev": 0.005,
        "resolution_date": "2026-06-30",  # Estimated
        "days_to_resolution": 125,
        "fee_enabled": False,
        "domain": "ECO",
        "making_side": "YES",
        "notes": "Heavy favorite at 93.9%. Tight spreads, high bot competition."
    },
    {
        "name": "Greenland Acquisition (NO)",
        "slug": "greenland-acquisition",
        "mid": 0.1095,
        "daily_volume": 75_000,
        "liquidity": 584_000,
        "spread_observed": 0.01,       # 1 cent
        "daily_price_stdev": 0.008,
        "resolution_date": "2027-01-01",
        "days_to_resolution": 309,
        "fee_enabled": False,
        "domain": "GEO",
        "making_side": "NO",
        "notes": "Slow-moving, 1c spread, moderate volume. Lower bot competition."
    },
    {
        "name": "Iran Strikes Mar 31 (both sides)",
        "slug": "iran-strikes-mar31",
        "mid": 0.605,
        "daily_volume": 1_307_000,
        "liquidity": 788_000,
        "spread_observed": 0.01,       # 1 cent
        "daily_price_stdev": 0.035,    # HIGH — news-driven
        "resolution_date": "2026-03-31",
        "days_to_resolution": 34,
        "fee_enabled": False,
        "domain": "GEO",
        "making_side": "BOTH",
        "notes": "HIGH delta risk. 60.5% YES. Very volatile. NOT ideal for making."
    },
    {
        "name": "Fed Chair - Shelton (YES/NO)",
        "slug": "fed-chair-shelton",
        "mid": 0.0365,
        "daily_volume": 1_000_000,
        "liquidity": 1_716_000,
        "spread_observed": 0.001,      # 0.1 cent
        "daily_price_stdev": 0.005,
        "resolution_date": "2026-06-30",
        "days_to_resolution": 125,
        "fee_enabled": False,
        "domain": "ECO",
        "making_side": "NO",
        "notes": "Alt candidate at 3.65%. Tight spread. $1M daily volume."
    },
]


# ============================================================
# Model Functions
# ============================================================

def spread_capture_revenue(capital_per_market, half_spread, daily_volume, fill_rate,
                           manual_checks_per_day=2):
    """
    Calculate daily spread capture revenue.

    The BINDING constraint for a manual maker is capital turnover:
    - You post capital/2 on each side of the book
    - When one side fills, you rebalance at next check
    - Manual checks = 2x/day → max 2 rebalances/day
    - Each rebalance can process at most capital_per_side in flow
    - Automated bot: could do 100+ rebalances/day

    The volume-based formula (half_spread × 2 × volume × fill_rate) is the
    theoretical maximum for an INFINITELY-CAPITALIZED maker. For small manual
    operations, capital turnover is always the binding constraint.
    """
    if capital_per_market <= 0:
        return 0.0

    capital_per_side = capital_per_market / 2

    # Maximum daily throughput = capital_per_side × rebalances_per_day
    # Each rebalance: one side fills, you cancel+repost the other side
    # Realistic: not every check results in a full fill
    fill_probability_per_check = min(1.0, daily_volume * fill_rate / capital_per_side / 24)
    fills_per_day = manual_checks_per_day * fill_probability_per_check

    # Revenue per fill = spread × shares filled
    # Shares per fill ≈ capital_per_side / avg_price (but capped by what's available)
    revenue_per_fill = half_spread * 2 * capital_per_side

    # But not every fill completes a round-trip (buy→sell).
    # You earn spread only when BOTH sides fill (a round-trip).
    # Approximate: half of fills complete a round-trip.
    round_trip_fraction = 0.5

    daily_revenue = revenue_per_fill * fills_per_day * round_trip_fraction

    return daily_revenue


def lp_reward_score(spread_from_mid, order_size_shares, v=QUALIFYING_SPREAD_V):
    """
    Calculate LP reward score using Polymarket's quadratic formula.

    S(v, s) = ((v - s) / v)^2 * b

    Two-sided: score = min(bid_score, ask_score)
    One-sided at 0.10-0.90: score / 3.0
    """
    if spread_from_mid >= v:
        return 0.0
    score = ((v - spread_from_mid) / v) ** 2 * order_size_shares
    return score


def lp_rewards_daily(my_total_score, est_total_pool_score=EST_TOTAL_MAKER_SCORE):
    """
    Estimate daily LP rewards based on your share of total score.
    """
    if est_total_pool_score <= 0:
        return 0.0
    my_share = my_total_score / est_total_pool_score
    return LP_REWARDS_DAILY * my_share


def taker_fee(price, fee_rate, exponent):
    """
    Calculate taker fee per share.
    fee = fee_rate * (p * (1-p))^exponent
    """
    return fee_rate * (price * (1 - price)) ** exponent


def maker_rebate_daily(capital_per_market, mid_price, daily_volume, fill_rate,
                       fee_rate, exponent, rebate_pct, num_makers=10):
    """
    Estimate daily maker rebate from fee-enabled markets.
    """
    fee_per_share = taker_fee(mid_price, fee_rate, exponent)
    total_taker_fees_daily = fee_per_share * daily_volume
    total_rebate_pool = total_taker_fees_daily * rebate_pct

    # Your share based on your fill fraction
    your_share = fill_rate / num_makers if num_makers > 0 else fill_rate
    return total_rebate_pool * your_share


def inventory_risk_daily(capital_per_market, daily_price_stdev, imbalance_fraction=0.5):
    """
    Estimate daily inventory risk (cost of holding unbalanced inventory).

    If the market moves against you while holding imbalanced inventory:
    loss = price_move × imbalanced_capital

    imbalance_fraction: what fraction of capital is typically imbalanced (0-1)
    """
    imbalanced_capital = capital_per_market * imbalance_fraction
    # Expected daily loss from inventory = stdev × imbalanced capital
    # Using 1 stdev as expected adverse move (conservative)
    return daily_price_stdev * imbalanced_capital


def opportunity_cost_daily(total_capital):
    """Daily opportunity cost vs. T-bills."""
    return total_capital * TBILL_ANNUAL_YIELD / 365


# ============================================================
# Scenario Modeling
# ============================================================

def model_market(market, capital_per_market, half_spread=None, fill_rate=0.25,
                 manual_checks_per_day=2):
    """
    Model the full P&L for making a single market.

    Returns dict with all revenue/cost components.
    """
    mid = market["mid"]
    daily_vol = market["daily_volume"]
    observed_spread = market["spread_observed"]
    price_stdev = market["daily_price_stdev"]

    # If no spread specified, use observed + 0.5c (we quote slightly wider than bots)
    if half_spread is None:
        half_spread = max(observed_spread, 0.005)  # At least 0.5c each side

    effective_fill_rate = fill_rate

    # 1. Spread capture (capital-constrained for manual makers)
    spread_rev = spread_capture_revenue(
        capital_per_market, half_spread, daily_vol, effective_fill_rate,
        manual_checks_per_day=manual_checks_per_day
    )

    # 2. LP rewards
    # Shares on each side: capital / 2 / price_per_share
    shares_per_side = capital_per_market / 2 / max(mid, 1 - mid)
    score = lp_reward_score(half_spread, shares_per_side)
    # Two-sided bonus
    if mid >= 0.10 and mid <= 0.90:
        lp_score = score  # Two-sided gets full score
    else:
        lp_score = score / 3.0  # One-sided at extremes
    lp_rev = lp_rewards_daily(lp_score)

    # 3. Maker rebates (only fee-enabled markets)
    if market.get("fee_enabled"):
        rebate = maker_rebate_daily(
            capital_per_market, mid, daily_vol, effective_fill_rate,
            CRYPTO_FEE_RATE, CRYPTO_FEE_EXPONENT, CRYPTO_MAKER_REBATE_PCT
        )
    else:
        rebate = 0.0

    # 4. Inventory risk
    # Manual makers have HIGHER inventory risk due to stale quotes
    # Adverse selection: fills happen when market moves against your quote
    adverse_selection_multiplier = 1.5 if manual_checks_per_day <= 2 else 1.0
    inv_risk = inventory_risk_daily(
        capital_per_market, price_stdev, imbalance_fraction=0.5
    ) * adverse_selection_multiplier

    # Net daily P&L
    gross_daily = spread_rev + lp_rev + rebate
    net_daily = gross_daily - inv_risk

    return {
        "market": market["name"],
        "capital": capital_per_market,
        "half_spread": half_spread,
        "fill_rate": effective_fill_rate,
        "spread_revenue": spread_rev,
        "lp_rewards": lp_rev,
        "maker_rebate": rebate,
        "gross_daily": gross_daily,
        "inventory_risk": inv_risk,
        "net_daily": net_daily,
        "net_annual": net_daily * 365,
        "annual_yield_pct": (net_daily * 365 / capital_per_market * 100) if capital_per_market > 0 else 0,
        "price_stdev": price_stdev,
        "observed_spread": observed_spread,
    }


def model_portfolio(total_capital, markets, half_spread=None, fill_rate=0.25):
    """
    Model the full portfolio P&L across multiple markets.
    """
    n_markets = len(markets)
    capital_per_market = total_capital / n_markets if n_markets > 0 else 0

    results = []
    for m in markets:
        r = model_market(m, capital_per_market, half_spread, fill_rate)
        results.append(r)

    total_gross = sum(r["gross_daily"] for r in results)
    total_inv_risk = sum(r["inventory_risk"] for r in results)
    total_net = sum(r["net_daily"] for r in results)
    opp_cost = opportunity_cost_daily(total_capital)

    return {
        "total_capital": total_capital,
        "n_markets": n_markets,
        "capital_per_market": capital_per_market,
        "market_results": results,
        "total_gross_daily": total_gross,
        "total_inventory_risk": total_inv_risk,
        "total_net_daily": total_net,
        "opportunity_cost_daily": opp_cost,
        "net_after_opp_cost_daily": total_net - opp_cost,
        "total_net_annual": total_net * 365,
        "net_after_opp_cost_annual": (total_net - opp_cost) * 365,
        "annual_yield_pct": (total_net * 365 / total_capital * 100) if total_capital > 0 else 0,
        "yield_vs_tbills_pct": ((total_net * 365 / total_capital * 100) - TBILL_ANNUAL_YIELD * 100) if total_capital > 0 else 0,
    }


# ============================================================
# Display Functions
# ============================================================

def print_header(text):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}")


def print_market_result(r):
    print(f"\n  {r['market']}")
    print(f"    Capital deployed:   ${r['capital']:>10,.2f}")
    print(f"    Half-spread quoted: {r['half_spread']*100:>10.1f}c")
    print(f"    Observed spread:    {r['observed_spread']*100:>10.1f}c")
    print(f"    Effective fill rate:{r['fill_rate']:>10.1%}")
    print(f"    Daily price stdev:  {r['price_stdev']*100:>10.1f}%")
    print(f"    ─── Daily P&L ───")
    print(f"    Spread capture:     ${r['spread_revenue']:>10.2f}")
    print(f"    LP rewards:         ${r['lp_rewards']:>10.2f}")
    print(f"    Maker rebates:      ${r['maker_rebate']:>10.2f}")
    print(f"    Gross revenue:      ${r['gross_daily']:>10.2f}")
    print(f"    Inventory risk:     ${r['inventory_risk']:>10.2f}")
    print(f"    Net daily:          ${r['net_daily']:>10.2f}")
    print(f"    ─── Annualized ───")
    print(f"    Net annual:         ${r['net_annual']:>10,.2f}")
    print(f"    Annual yield:       {r['annual_yield_pct']:>10.1f}%")


def print_portfolio_summary(p):
    print(f"\n  PORTFOLIO SUMMARY")
    print(f"  {'─'*50}")
    print(f"  Total capital:           ${p['total_capital']:>12,.2f}")
    print(f"  Markets:                  {p['n_markets']:>12}")
    print(f"  Capital per market:      ${p['capital_per_market']:>12,.2f}")
    print(f"  {'─'*50}")
    print(f"  Gross daily revenue:     ${p['total_gross_daily']:>12.2f}")
    print(f"  Inventory risk daily:    ${p['total_inventory_risk']:>12.2f}")
    print(f"  Net daily:               ${p['total_net_daily']:>12.2f}")
    print(f"  T-bill opp. cost daily:  ${p['opportunity_cost_daily']:>12.2f}")
    print(f"  Net after opp. cost:     ${p['net_after_opp_cost_daily']:>12.2f}")
    print(f"  {'─'*50}")
    print(f"  Net annual:              ${p['total_net_annual']:>12,.2f}")
    print(f"  Net after opp. cost/yr:  ${p['net_after_opp_cost_annual']:>12,.2f}")
    print(f"  Annual yield:            {p['annual_yield_pct']:>12.1f}%")
    print(f"  Yield vs T-bills:        {p['yield_vs_tbills_pct']:>+12.1f}pp")


def print_combined_table(scenarios):
    """Print the combined yield table from Task 1d."""
    print(f"\n  {'Capital':>8} | {'Mkts':>4} | {'Spread':>7} | {'Fill':>5} | "
          f"{'Daily Spread':>12} | {'Daily LP':>10} | {'Inv Risk':>10} | "
          f"{'Net Daily':>10} | {'Annual':>10} | {'Yield':>7} | {'vs T-bill':>9}")
    print(f"  {'─'*8}─┼─{'─'*4}─┼─{'─'*7}─┼─{'─'*5}─┼─"
          f"{'─'*12}─┼─{'─'*10}─┼─{'─'*10}─┼─"
          f"{'─'*10}─┼─{'─'*10}─┼─{'─'*7}─┼─{'─'*9}")
    for s in scenarios:
        p = s["portfolio"]
        total_spread = sum(r["spread_revenue"] for r in p["market_results"])
        total_lp = sum(r["lp_rewards"] for r in p["market_results"])
        print(f"  ${p['total_capital']:>7,.0f} | {p['n_markets']:>4} | "
              f"{s['spread_label']:>7} | {s['fill_label']:>5} | "
              f"${total_spread:>11.2f} | ${total_lp:>9.2f} | "
              f"${p['total_inventory_risk']:>9.2f} | "
              f"${p['total_net_daily']:>9.2f} | "
              f"${p['total_net_annual']:>9,.0f} | "
              f"{p['annual_yield_pct']:>6.1f}% | "
              f"{p['yield_vs_tbills_pct']:>+8.1f}pp")


def print_lp_reward_sensitivity():
    """Show how LP rewards change with spread distance."""
    print_header("LP REWARD SENSITIVITY (v = 3 cents)")
    print(f"\n  {'Spread (s)':>12} | {'Score Multiplier':>18} | {'% of Max':>10} | {'Risk Level':>12}")
    print(f"  {'─'*12}─┼─{'─'*18}─┼─{'─'*10}─┼─{'─'*12}")
    for s_cents in [0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]:
        s = s_cents / 100
        if s >= QUALIFYING_SPREAD_V:
            mult = 0
        else:
            mult = ((QUALIFYING_SPREAD_V - s) / QUALIFYING_SPREAD_V) ** 2
        risk = "MAXIMUM" if s_cents == 0 else "Very High" if s_cents <= 0.5 else \
               "High" if s_cents <= 1.0 else "Medium" if s_cents <= 1.5 else \
               "Low" if s_cents <= 2.0 else "Very Low" if s_cents < 3.0 else "Zero"
        print(f"  {s_cents:>10.2f}c | {mult:>18.3f} | {mult*100:>9.1f}% | {risk:>12}")


def print_harvest_mode_analysis():
    """Model the Harvest Mode strategy for near-resolution positions."""
    print_header("HARVEST MODE ANALYSIS")
    print("\n  When a position reaches >90% probability, switch from holding to making.\n")

    scenarios = [
        {"name": "Position at 90% (10c spread)", "prob": 0.90, "spread_room": 0.05, "daily_vol": 200_000},
        {"name": "Position at 95% (5c spread)", "prob": 0.95, "spread_room": 0.025, "daily_vol": 100_000},
        {"name": "Position at 98% (2c spread)", "prob": 0.98, "spread_room": 0.01, "daily_vol": 50_000},
    ]

    print(f"  {'Scenario':>30} | {'Half Spread':>11} | {'Daily Vol':>10} | {'Inv Risk':>10} | "
          f"{'Net $/day':>10} | {'Yield/mo':>9}")
    print(f"  {'─'*30}─┼─{'─'*11}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*10}─┼─{'─'*9}")

    for s in scenarios:
        hs = min(s["spread_room"] / 2, 0.01)  # Half-spread, max 1c
        capital = 500  # $500 position
        fill_rate = 0.15  # Conservative for near-resolution

        spread_rev = hs * 2 * s["daily_vol"] * fill_rate
        # Capital-constrained
        max_turnover = s["daily_vol"] * fill_rate / capital
        turnover = min(max_turnover, 3.0)
        cap_rev = hs * 2 * capital * turnover
        actual_rev = min(spread_rev, cap_rev)

        inv_risk = 0.005 * capital * 0.3  # Very low at high probability
        net = actual_rev - inv_risk
        yield_mo = net * 30 / capital * 100 if capital > 0 else 0

        print(f"  {s['name']:>30} | {hs*100:>9.1f}c | ${s['daily_vol']:>9,} | "
              f"${inv_risk:>9.2f} | ${net:>9.2f} | {yield_mo:>8.1f}%")

    print(f"\n  Note: Harvest mode is INCREMENTAL yield on capital already committed.")
    print(f"  The main benefit is earning while waiting, not a standalone income stream.")
    print(f"  Exit the maker position the day before resolution to avoid MOOV2 process.")


def print_pilot_plan():
    """Print the specific 3-market pilot plan."""
    print_header("PILOT PLAN: $300 / 3 MARKETS / 2 WEEKS")

    pilots = [
        {
            "market": "Jesus Christ Return (NO side)",
            "capital": 100,
            "reason": "Near-certain NO (96.25%). Ultra-low inventory risk. $559K daily volume.",
            "spread": "Quote at 0.961/0.965 (0.2c each side of 0.963 mid)",
            "risk": "Spread is already 0.1c — we'll quote wider to ensure fills but earn less than bots.",
            "check": "Monitor 2x/day. Rebalance if inventory > $60 one-sided.",
            "target": "Earn ~$0.10-0.30/day from spread + LP. Test whether any fills occur.",
            "kill": "Stop if zero fills after 3 days (bots dominate completely)."
        },
        {
            "market": "Greenland Acquisition (NO side)",
            "capital": 100,
            "reason": "Slow-moving (11% YES), $75K daily volume, 1c observed spread.",
            "spread": "Quote at 0.885/0.895 (0.5c each side)",
            "risk": "Low delta risk (Trump-Greenland unlikely to move fast). Lower bot competition.",
            "check": "Monitor 2x/day. Adjust quotes if price moves >1c.",
            "target": "Earn ~$0.05-0.20/day. Test fill rates on niche political market.",
            "kill": "Stop if cumulative inventory exceeds $70 on one side."
        },
        {
            "market": "BTC $150K by Dec 2026 (NO side — EXISTING POSITION T008)",
            "capital": 100,
            "reason": "We already hold NO shares (T008). This is Harvest Mode lite.",
            "spread": "Quote at 0.910/0.920 (0.5c each side of 0.915 mid)",
            "risk": "BTC volatility could move price. Fee-enabled market = maker rebates possible.",
            "check": "Monitor 2x/day. Tighten quotes if BTC stable; widen if volatile.",
            "target": "Test harvest mode on existing position. Earn spread + rebates.",
            "kill": "Stop if BTC moves >5% in a day (inventory risk too high)."
        }
    ]

    for i, p in enumerate(pilots, 1):
        print(f"\n  Market {i}: {p['market']}")
        print(f"  Capital:    ${p['capital']}")
        print(f"  Reason:     {p['reason']}")
        print(f"  Spread:     {p['spread']}")
        print(f"  Risk:       {p['risk']}")
        print(f"  Monitoring: {p['check']}")
        print(f"  Target:     {p['target']}")
        print(f"  Kill switch:{p['kill']}")

    print(f"\n  ─── Expected Pilot Results ───")
    print(f"  Best case:  $5-10 total over 2 weeks (1.7-3.3% return on $300)")
    print(f"  Base case:  $0-3 total (breakeven to slightly positive)")
    print(f"  Worst case: -$15 to -$30 (inventory loss from adverse moves)")
    print(f"")
    print(f"  Decision criteria after pilot:")
    print(f"  - If net positive: consider scaling to $1K across 5 markets")
    print(f"  - If breakeven: making not worth the effort at manual frequency")
    print(f"  - If negative: abandon making, keep capital for directional trades")


# ============================================================
# Main
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Market Maker Yield Calculator")
    parser.add_argument("--capital", type=float, default=None,
                        help="Total capital to model (default: run $1K/$5K/$10K)")
    parser.add_argument("--markets", type=int, default=5,
                        help="Number of markets to make (default: 5)")
    parser.add_argument("--pilot", action="store_true",
                        help="Show pilot plan only")
    args = parser.parse_args()

    print("=" * 70)
    print("  POLYMARKET MARKET MAKER YIELD MODEL")
    print("  Based on live market data — February 25, 2026")
    print("=" * 70)

    # ── LP Reward Sensitivity ──
    print_lp_reward_sensitivity()

    # ── Scenario Table (Task 1d) ──
    print_header("COMBINED YIELD MODEL (Task 1d)")

    # Select markets by capital tier
    safe_markets = [m for m in CANDIDATE_MARKETS if m["daily_price_stdev"] <= 0.01]
    all_markets = CANDIDATE_MARKETS

    scenarios = [
        {
            "spread_label": "2.0c",
            "fill_label": "30%",
            "portfolio": model_portfolio(1_000, safe_markets[:3], half_spread=0.01, fill_rate=0.30),
        },
        {
            "spread_label": "1.5c",
            "fill_label": "25%",
            "portfolio": model_portfolio(5_000, safe_markets[:4], half_spread=0.0075, fill_rate=0.25),
        },
        {
            "spread_label": "1.0c",
            "fill_label": "25%",
            "portfolio": model_portfolio(10_000, all_markets, half_spread=0.005, fill_rate=0.25),
        },
    ]

    print_combined_table(scenarios)

    # ── Detailed Per-Market Analysis ──
    if args.capital:
        capitals = [args.capital]
    else:
        capitals = [1_000, 5_000, 10_000]

    for cap in capitals:
        n = min(args.markets, len(CANDIDATE_MARKETS))
        markets_to_use = CANDIDATE_MARKETS[:n]

        print_header(f"DETAILED MODEL: ${cap:,.0f} across {n} markets")

        portfolio = model_portfolio(cap, markets_to_use, fill_rate=0.25)

        for r in portfolio["market_results"]:
            print_market_result(r)

        print_portfolio_summary(portfolio)

    # ── Harvest Mode ──
    print_harvest_mode_analysis()

    # ── Pilot Plan ──
    print_pilot_plan()

    # ── THE VERDICT ──
    print_header("THE VERDICT: Is Market Making Worth It at $8K?")

    # Model our specific situation: $8,315 available
    our_portfolio = model_portfolio(8_315, safe_markets[:4], half_spread=0.0075, fill_rate=0.25)
    tbill_annual = 8_315 * TBILL_ANNUAL_YIELD

    print(f"""
  Our situation: $8,315 available capital

  ┌─────────────────────────────────────────────────────────────────┐
  │ Option A: Market Making (4 safe markets, 1.5c spread)          │
  │   Estimated net annual:  ${our_portfolio['total_net_annual']:>10,.2f}                        │
  │   Annual yield:          {our_portfolio['annual_yield_pct']:>10.1f}%                        │
  │   Effort: 2 checks/day, quote management, inventory monitoring │
  │                                                                 │
  │ Option B: T-Bills (3-month, risk-free)                          │
  │   Annual return:         ${tbill_annual:>10,.2f}                        │
  │   Annual yield:              5.3%                        │
  │   Effort: Zero                                                  │
  │                                                                 │
  │ Option C: Hold for Directional Trades (S004/S006/S008)          │
  │   Expected annual:       $1,247 - $2,494 (15-30% on deployed)  │
  │   Annual yield:          15-30% on deployed capital             │
  │   Effort: Research-heavy but higher-conviction returns          │
  └─────────────────────────────────────────────────────────────────┘

  RECOMMENDATION: NO — Do NOT allocate to market making as primary strategy.

  Reasons:
  1. Spreads on liquid markets are 0.1-1c, already competed by bots
  2. Manual checking (2x/day) creates adverse selection — you get filled
     when the market moves against you, not with you
  3. The poly-maker bot creator explicitly says it's "not profitable"
  4. LP rewards are distributed across $250M+ in maker capital; our $8K
     captures an immaterial fraction
  5. Inventory risk on a manual operation exceeds spread capture
  6. Opportunity cost: directional S006/S004/S008 returns 15-30% vs
     estimated {our_portfolio['annual_yield_pct']:.1f}% from making (before adverse selection)

  EXCEPTION: Harvest Mode on existing positions reaching 90%+ probability.
  When T001-T008 approach near-certain resolution, making around the
  position earns incremental yield while waiting. This is worth doing
  because the capital is ALREADY committed.

  PILOT: Run the $300 / 3-market / 2-week pilot for LEARNING VALUE only.
  The pilot's purpose is to validate these estimates with real data, not
  to generate returns. If the pilot surprises to the upside, reassess.""")


if __name__ == "__main__":
    main()
