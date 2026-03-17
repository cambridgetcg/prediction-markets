#!/usr/bin/env python3
"""
Time Decay Screener (S006)

Screens active Polymarket "by date" markets for time-decay overpricing.
Identifies markets where the implied daily hazard rate exceeds base rate
by a configurable multiplier (default 2x), flagging them as NO opportunities.

Usage:
    python3 time-decay-screener.py                    # Default run
    python3 time-decay-screener.py --min-days 14      # At least 14 days remaining
    python3 time-decay-screener.py --multiplier 3     # 3x base rate threshold
    python3 time-decay-screener.py --domain GEO       # Filter by domain
    python3 time-decay-screener.py --json              # JSON output
"""

import argparse
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone

# ============================================================
# DOMAIN-SPECIFIC BASE RATES
# ============================================================
# Estimated daily probability that a "by date" event occurs on any given day.
# Derived from historical Polymarket resolution data (804 resolved markets)
# and domain-specific adjustment.
#
# Key insight: 73.5% of "by date" markets resolve NO historically.
# These base rates represent calibrated daily hazard rates by domain.

BASE_RATES = {
    # Domain: daily_base_rate (probability event happens on any given day)
    #
    # GEO: Military strikes, ceasefires, regime changes. High drama, lower resolution.
    # Historical NO rate: 64.3% — the least overpriced domain, but still overpriced.
    "GEO": 0.005,   # 0.5% daily — wars/strikes are rare-per-day events

    # POL: Elections, appointments, legislation.
    # Historical NO rate: 78.3% — strong overpricing due to media cycles.
    "POL": 0.003,   # 0.3% daily — political actions have long lead times

    # ECO: Fed decisions, GDP, employment.
    # Historical NO rate: 60.0% — most efficient (sophisticated participants).
    "ECO": 0.008,   # 0.8% daily — higher base rate, less overpricing

    # CRY: Bitcoin milestones, ETH prices, token events.
    # Historical NO rate: 69.5% — aspirational price targets rarely hit.
    "CRY": 0.003,   # 0.3% daily — round-number crypto targets are aspirational

    # TEC: AI launches, product releases, tech regulation.
    # Historical NO rate: 63.6%
    "TEC": 0.005,   # 0.5% daily — tech launches have specific timelines

    # LAW: Court rulings, indictments, verdicts.
    # Historical NO rate: 0.0% (only 1 market, resolved YES — insufficient data)
    "LAW": 0.005,   # 0.5% daily — courts have structured timelines

    # ENV: Climate, natural disasters, emissions.
    # Historical NO rate: 82.4% — strong overpricing.
    "ENV": 0.002,   # 0.2% daily — climate targets almost never hit early

    # SCI: Pandemics, vaccines, space.
    # Historical NO rate: 100% (only 1 market — insufficient data)
    "SCI": 0.003,   # 0.3% daily

    # OTHER / default
    "OTHER": 0.004,  # 0.4% daily — moderate default
}


def classify_domain(question: str) -> str:
    """Classify a market question into a domain."""
    q = question.lower()
    if any(w in q for w in ["strike", "war", "military", "ceasefire", "troops",
                            "invasion", "iran", "russia", "ukraine", "israel",
                            "nato", "nuclear", "houthi", "hezbollah"]):
        return "GEO"
    if any(w in q for w in ["trump", "biden", "election", "president", "congress",
                            "senate", "democrat", "republican", "impeach",
                            "nomination", "appointed"]):
        return "POL"
    if any(w in q for w in ["fed ", "interest rate", "gdp", "inflation",
                            "recession", "unemployment", "tariff"]):
        return "ECO"
    if any(w in q for w in ["bitcoin", "ethereum", "crypto", "btc", "eth",
                            "token", "airdrop", "solana", "dogecoin"]):
        return "CRY"
    if any(w in q for w in ["ai ", "artificial intelligence", "gpt", "openai",
                            "google", "apple", "tesla", "spacex", "nvidia"]):
        return "TEC"
    if any(w in q for w in ["court", "judge", "lawsuit", "indictment", "trial",
                            "verdict", "epstein"]):
        return "LAW"
    if any(w in q for w in ["climate", "hurricane", "earthquake", "temperature",
                            "emissions", "sea level"]):
        return "ENV"
    if any(w in q for w in ["pandemic", "vaccine", "virus", "outbreak", "measles"]):
        return "SCI"
    return "OTHER"


# ============================================================
# HAZARD RATE MODELS
# ============================================================

def constant_hazard_implied_daily_p(market_price: float, days_remaining: int) -> float:
    """
    Constant hazard model: assumes equal daily probability throughout.
    P(event by day N) = 1 - (1-p)^N
    Solving for p: p = 1 - (1 - P)^(1/N)
    """
    if market_price <= 0 or market_price >= 1 or days_remaining <= 0:
        return 0.0
    return 1 - (1 - market_price) ** (1.0 / days_remaining)


def decreasing_hazard_implied_daily_p(market_price: float, days_remaining: int,
                                       decay_factor: float = 0.98) -> float:
    """
    Decreasing hazard model: risk decreases over time (most realistic for
    "will X happen by date" markets where no news = less likely).

    Each day's probability is decay_factor * previous day's probability.
    p_day_k = p_0 * decay_factor^k

    P(event by N) = 1 - prod(1 - p_0 * decay^k, k=0..N-1)

    Solved numerically via bisection.
    """
    if market_price <= 0 or market_price >= 1 or days_remaining <= 0:
        return 0.0

    def cumulative_prob(p0):
        survival = 1.0
        for k in range(days_remaining):
            daily = p0 * (decay_factor ** k)
            daily = min(daily, 0.999)
            survival *= (1 - daily)
        return 1 - survival

    # Bisection search for p0
    lo, hi = 0.0, 0.999
    for _ in range(100):
        mid = (lo + hi) / 2
        if cumulative_prob(mid) < market_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def increasing_hazard_implied_daily_p(market_price: float, days_remaining: int,
                                       growth_factor: float = 1.02) -> float:
    """
    Increasing hazard model: risk grows over time (e.g., escalation scenarios).
    p_day_k = p_0 * growth_factor^k
    """
    if market_price <= 0 or market_price >= 1 or days_remaining <= 0:
        return 0.0

    def cumulative_prob(p0):
        survival = 1.0
        for k in range(days_remaining):
            daily = p0 * (growth_factor ** k)
            daily = min(daily, 0.999)
            survival *= (1 - daily)
        return 1 - survival

    lo, hi = 0.0, 0.999
    for _ in range(100):
        mid = (lo + hi) / 2
        if cumulative_prob(mid) < market_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ============================================================
# KELLY CRITERION
# ============================================================

def kelly_fraction(win_prob: float, win_payout: float, loss_payout: float) -> float:
    """
    Kelly criterion for optimal position sizing.
    f* = (p * b - q) / b
    where p = win probability, q = 1-p, b = net odds (win_payout / loss_payout)
    """
    if win_payout <= 0 or loss_payout <= 0:
        return 0.0
    b = win_payout / loss_payout
    q = 1 - win_prob
    f = (win_prob * b - q) / b
    return max(0.0, f)


def expected_value(win_prob: float, win_amount: float, loss_amount: float) -> float:
    """Expected value per dollar risked."""
    return win_prob * win_amount - (1 - win_prob) * loss_amount


# ============================================================
# DATA FETCHING
# ============================================================

def fetch_active_by_date_markets() -> list:
    """Fetch active markets from Polymarket Gamma API, filter for by-date structure."""
    markets = []
    now = datetime.now(timezone.utc)

    for offset in range(0, 1000, 100):
        cmd = (
            f'curl -s "https://gamma-api.polymarket.com/events?'
            f'limit=100&closed=false&active=true&order=volume&ascending=false&offset={offset}"'
        )
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        try:
            events = json.loads(result.stdout)
            if not events:
                break
        except (json.JSONDecodeError, TypeError):
            break

        for event in events:
            for mkt in event.get("markets", []):
                if mkt.get("closed"):
                    continue

                q = mkt.get("question", "")

                # Filter for "by [date]" or "before [date]" pattern
                is_by_date = bool(re.search(
                    r"\b(by|before)\b.*\b(20\d{2}|january|february|march|april|may|june|"
                    r"july|august|september|october|november|december|"
                    r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
                    q, re.I
                ))
                is_fed_meeting = bool(re.search(
                    r"after\s+\w+\s+\d{4}\s+meeting", q, re.I
                ))

                if not is_by_date or is_fed_meeting:
                    continue

                # Parse YES price
                outcomes = mkt.get("outcomes", [])
                prices_raw = mkt.get("outcomePrices", "")
                if isinstance(prices_raw, str):
                    try:
                        prices = json.loads(prices_raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                else:
                    prices = prices_raw

                if len(prices) < 2 or len(outcomes) < 2:
                    continue

                yes_idx = 0
                for i, o in enumerate(outcomes):
                    if str(o).lower() == "yes":
                        yes_idx = i
                        break

                try:
                    yes_price = float(prices[yes_idx])
                except (ValueError, IndexError):
                    continue

                if yes_price <= 0.01 or yes_price >= 0.99:
                    continue

                # Parse end date
                end_date_str = mkt.get("endDate", "")
                if not end_date_str:
                    continue
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                    days_remaining = max(1, (end_date - now).days)
                except (ValueError, TypeError):
                    continue

                domain = classify_domain(q)
                base_rate = BASE_RATES.get(domain, BASE_RATES["OTHER"])

                implied_daily = constant_hazard_implied_daily_p(yes_price, days_remaining)
                implied_daily_dec = decreasing_hazard_implied_daily_p(yes_price, days_remaining)

                multiplier = implied_daily / base_rate if base_rate > 0 else float("inf")

                # NO strategy expected value using historical domain-specific NO rates
                domain_no_rates = {
                    "GEO": 0.643, "POL": 0.783, "ECO": 0.600, "CRY": 0.695,
                    "TEC": 0.636, "LAW": 0.500, "ENV": 0.824, "SCI": 0.750,
                    "OTHER": 0.800,
                }
                no_rate = domain_no_rates.get(domain, 0.735)

                # If you buy NO at (1 - yes_price):
                no_entry = 1 - yes_price
                win_amount = yes_price      # You gain yes_price per share on NO resolution
                loss_amount = no_entry       # You lose no_entry per share on YES resolution
                ev = expected_value(no_rate, win_amount, loss_amount)

                # Kelly sizing
                kelly = kelly_fraction(no_rate, win_amount, loss_amount)

                markets.append({
                    "question": q,
                    "domain": domain,
                    "yes_price": yes_price,
                    "no_price": no_entry,
                    "days_remaining": days_remaining,
                    "end_date": end_date_str[:10],
                    "implied_daily_p": implied_daily,
                    "implied_daily_p_decreasing": implied_daily_dec,
                    "base_rate": base_rate,
                    "multiplier": multiplier,
                    "historical_no_rate": no_rate,
                    "ev_per_dollar": ev / no_entry if no_entry > 0 else 0,
                    "kelly_fraction": kelly,
                    "volume": float(mkt.get("volume", 0) or 0),
                    "market_id": mkt.get("id", ""),
                    "slug": mkt.get("slug", ""),
                })

    return markets


# ============================================================
# OUTPUT
# ============================================================

def print_table(markets: list, limit: int = 40):
    """Print ranked opportunities table."""
    print()
    print("=" * 120)
    print("S006 TIME DECAY SCREENER — Ranked Opportunities (Buy NO)")
    print("=" * 120)
    print(f"{'#':>3} {'Question':<55} {'YES':>5} {'NO':>5} {'Days':>4} "
          f"{'Impl/d':>7} {'Base':>6} {'Mult':>5} {'EV/$':>6} {'Kelly':>6} {'Dom':>5}")
    print("-" * 120)

    for i, m in enumerate(markets[:limit], 1):
        q = m["question"][:54]
        print(f"{i:>3} {q:<55} {m['yes_price']:>5.1%} {m['no_price']:>5.1%} "
              f"{m['days_remaining']:>4} {m['implied_daily_p']:>7.3%} "
              f"{m['base_rate']:>6.3%} {m['multiplier']:>5.1f}x "
              f"{m['ev_per_dollar']:>+6.1%} {m['kelly_fraction']:>6.1%} {m['domain']:>5}")

    print()
    print("Legend:")
    print("  YES/NO    = current market price")
    print("  Days      = days until market end date")
    print("  Impl/d    = implied daily probability (constant hazard)")
    print("  Base      = domain base rate (daily)")
    print("  Mult      = implied/base ratio (>2x = overpriced signal)")
    print("  EV/$      = expected value per dollar risked (using historical NO rates)")
    print("  Kelly     = Kelly criterion recommended allocation")


def main():
    parser = argparse.ArgumentParser(description="S006 Time Decay Screener")
    parser.add_argument("--min-days", type=int, default=7,
                        help="Minimum days remaining (default: 7)")
    parser.add_argument("--max-days", type=int, default=365,
                        help="Maximum days remaining (default: 365)")
    parser.add_argument("--multiplier", type=float, default=2.0,
                        help="Min implied/base rate multiplier to flag (default: 2.0)")
    parser.add_argument("--min-volume", type=float, default=0,
                        help="Minimum volume in USD (default: 0)")
    parser.add_argument("--domain", type=str, default=None,
                        help="Filter by domain (GEO, POL, ECO, CRY, TEC, LAW, ENV, SCI)")
    parser.add_argument("--limit", type=int, default=40,
                        help="Max results to show (default: 40)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON instead of table")
    parser.add_argument("--sort", type=str, default="ev",
                        choices=["ev", "multiplier", "kelly", "volume", "days"],
                        help="Sort by field (default: ev)")
    args = parser.parse_args()

    print("Fetching active markets from Polymarket...", file=sys.stderr)
    markets = fetch_active_by_date_markets()
    print(f"Found {len(markets)} active by-date markets", file=sys.stderr)

    # Apply filters
    filtered = [
        m for m in markets
        if m["days_remaining"] >= args.min_days
        and m["days_remaining"] <= args.max_days
        and m["multiplier"] >= args.multiplier
        and m["volume"] >= args.min_volume
        and (args.domain is None or m["domain"] == args.domain.upper())
    ]
    print(f"After filters: {len(filtered)} opportunities", file=sys.stderr)

    # Sort
    sort_keys = {
        "ev": lambda m: m["ev_per_dollar"],
        "multiplier": lambda m: m["multiplier"],
        "kelly": lambda m: m["kelly_fraction"],
        "volume": lambda m: m["volume"],
        "days": lambda m: -m["days_remaining"],
    }
    filtered.sort(key=sort_keys[args.sort], reverse=True)

    if args.json:
        print(json.dumps(filtered[:args.limit], indent=2))
    else:
        print_table(filtered, args.limit)

        # Summary stats
        if filtered:
            avg_ev = sum(m["ev_per_dollar"] for m in filtered) / len(filtered)
            avg_mult = sum(m["multiplier"] for m in filtered) / len(filtered)
            avg_kelly = sum(m["kelly_fraction"] for m in filtered) / len(filtered)
            print(f"\nSummary ({len(filtered)} opportunities):")
            print(f"  Avg EV per dollar: {avg_ev:+.1%}")
            print(f"  Avg multiplier:    {avg_mult:.1f}x")
            print(f"  Avg Kelly:         {avg_kelly:.1%}")
            print(f"\n  Domain distribution:")
            domains = {}
            for m in filtered:
                domains[m["domain"]] = domains.get(m["domain"], 0) + 1
            for d, c in sorted(domains.items(), key=lambda x: -x[1]):
                print(f"    {d}: {c}")


if __name__ == "__main__":
    main()
