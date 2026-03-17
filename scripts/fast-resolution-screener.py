#!/usr/bin/env python3
"""
Fast-Resolution Market Screener (R04)

Finds high-probability markets resolving soon — the "bond rotation" pipeline.
Designed to feed S011 (bond rotation) and accelerate calibration.

Usage:
    python3 scripts/fast-resolution-screener.py                  # defaults: 7d, >95%
    python3 scripts/fast-resolution-screener.py --days 30 --min-prob 0.90
    python3 scripts/fast-resolution-screener.py --days 7 --min-prob 0.95 --min-liq 20000
"""

import argparse
import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

GAMMA_BASE = "https://gamma-api.polymarket.com"
HEADERS = {"User-Agent": "prediction-markets-screener/1.0"}


def fetch_json(url, params=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def fetch_events_paginated(end_date_max, max_pages=10):
    """Fetch all active events resolving before end_date_max."""
    all_events = []
    for page in range(max_pages):
        offset = page * 100
        params = {
            "limit": 100,
            "active": "true",
            "closed": "false",
            "end_date_max": end_date_max,
            "offset": offset,
        }
        events = fetch_json(f"{GAMMA_BASE}/events", params)
        if not events:
            break
        all_events.extend(events)
        if len(events) < 100:
            break
    return all_events


def parse_prices(raw):
    """Parse outcomePrices which can be a JSON string or list."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    return raw if isinstance(raw, list) else []


def parse_date(date_str):
    """Parse ISO date string to datetime."""
    if not date_str:
        return None
    # Handle various formats
    for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def days_until(date_str):
    """Days from now until the given date."""
    dt = parse_date(date_str)
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    return (dt - now).total_seconds() / 86400


def screen_fast_resolution(max_days=7, min_prob=0.95, min_liq=20000, verbose=False):
    """
    Find markets that:
    1. Resolve within max_days
    2. Have one side priced at min_prob or higher
    3. Have >= min_liq liquidity
    4. Entry price <= 0.97 (fee-adjusted S011 breakeven)
    """
    now = datetime.now(timezone.utc)
    end_date_max = (now + timedelta(days=max_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    if verbose:
        print(f"Fetching events resolving before {end_date_max}...")

    events = fetch_events_paginated(end_date_max)

    if verbose:
        print(f"Found {len(events)} events, scanning markets...")

    opportunities = []
    skipped = {"no_prices": 0, "low_prob": 0, "low_liq": 0, "no_date": 0}

    for event in events:
        markets = event.get("markets", [])
        for market in markets:
            prices = parse_prices(market.get("outcomePrices", "[]"))
            if not prices or len(prices) < 2:
                skipped["no_prices"] += 1
                continue

            yes_price = float(prices[0])
            no_price = float(prices[1])
            max_price = max(yes_price, no_price)
            dominant_side = "YES" if yes_price >= no_price else "NO"

            if max_price < min_prob:
                skipped["low_prob"] += 1
                continue

            # Liquidity check
            liquidity = float(market.get("liquidity", 0) or 0)
            volume = float(market.get("volumeNum", 0) or 0)
            if liquidity < min_liq:
                skipped["low_liq"] += 1
                continue

            # End date
            end_date = market.get("endDate") or event.get("endDate")
            d = days_until(end_date)
            if d is None or d < 0 or d > max_days:
                skipped["no_date"] += 1
                continue

            # Fee-adjusted return
            entry_price = max_price
            gross_return = (1.0 - entry_price) / entry_price if entry_price > 0 else 0
            # 2% winner fee
            net_return = (1.0 - entry_price - 0.02) / entry_price if entry_price > 0 else 0

            # S011 viability flag
            s011_viable = entry_price <= 0.97 and net_return > 0.005

            opportunities.append({
                "event": event.get("title", "?")[:65],
                "market": market.get("question", "?")[:70],
                "slug": event.get("slug", ""),
                "side": dominant_side,
                "price": max_price,
                "gross_return_pct": gross_return * 100,
                "net_return_pct": net_return * 100,
                "liquidity": liquidity,
                "volume": volume,
                "end_date": end_date,
                "days_left": round(d, 1),
                "s011_viable": s011_viable,
                "condition_id": market.get("conditionId", ""),
            })

    # Sort by net return (highest first), then by days (shortest first)
    opportunities.sort(key=lambda x: (-x["net_return_pct"], x["days_left"]))

    return opportunities, skipped


def print_results(opportunities, skipped, max_days, min_prob, min_liq):
    """Pretty-print screening results."""
    print()
    print(f"{'='*85}")
    print(f"  FAST-RESOLUTION SCREENER  |  Next {max_days}d  |  >{min_prob*100:.0f}%  |  >${min_liq/1000:.0f}K liq")
    print(f"{'='*85}")

    if not opportunities:
        print(f"\n  No opportunities found.")
        print(f"  Skipped: {skipped}")
        return

    # Separate S011-viable from other
    s011 = [o for o in opportunities if o["s011_viable"]]
    others = [o for o in opportunities if not o["s011_viable"]]

    if s011:
        print(f"\n  S011-VIABLE (entry <=97c, net return >0.5%):")
        print(f"  {'Side':>4} {'Price':>6} {'Net%':>6} {'Days':>5} {'Liq':>7} {'Market'}")
        print(f"  {'----':>4} {'-----':>6} {'----':>6} {'----':>5} {'---':>7} {'------'}")
        for o in s011[:15]:
            print(f"  {o['side']:>4} {o['price']:.3f}  {o['net_return_pct']:>5.1f}% {o['days_left']:>5.1f} ${o['liquidity']/1000:>5.0f}K {o['market'][:55]}")

    if others:
        print(f"\n  HIGH-PROB (not S011-viable — entry >97c or thin net return):")
        print(f"  {'Side':>4} {'Price':>6} {'Grs%':>6} {'Days':>5} {'Liq':>7} {'Market'}")
        print(f"  {'----':>4} {'-----':>6} {'----':>6} {'----':>5} {'---':>7} {'------'}")
        for o in others[:10]:
            print(f"  {o['side']:>4} {o['price']:.3f}  {o['gross_return_pct']:>5.1f}% {o['days_left']:>5.1f} ${o['liquidity']/1000:>5.0f}K {o['market'][:55]}")

    print(f"\n  Total: {len(opportunities)} opportunities ({len(s011)} S011-viable)")
    print(f"  Skipped: prob<{min_prob*100:.0f}%={skipped['low_prob']}, liq<${min_liq/1000:.0f}K={skipped['low_liq']}, no_date={skipped['no_date']}, no_prices={skipped['no_prices']}")
    print()


def print_deployment_recommendation(opps_7d, opps_30d):
    """Print specific $250 deployment recommendation."""
    print()
    print(f"{'='*85}")
    print(f"  $250 PAPER DEPLOYMENT RECOMMENDATION")
    print(f"  Target: 50% weekly / 30% monthly / 20% quarterly")
    print(f"{'='*85}")

    weekly = [o for o in opps_7d if o["s011_viable"]]
    monthly = [o for o in opps_30d if o["days_left"] > 7 and o["days_left"] <= 30]

    print(f"\n  WEEKLY ($125 = 50%):")
    if weekly:
        for o in weekly[:3]:
            size = min(125, 50)  # $50 per position max (5% of $1000 rotation fund)
            print(f"    -> {o['side']} {o['market'][:55]}")
            print(f"       Entry: {o['price']:.3f} | Net: {o['net_return_pct']:.1f}% | Size: ${size}")
    else:
        print(f"    -> No S011-viable weekly opportunities right now")
        print(f"    -> Alternative: Enter S011 positions as they appear in next 3 days")

    print(f"\n  MONTHLY ($75 = 30%):")
    if monthly:
        for o in monthly[:2]:
            print(f"    -> {o['side']} {o['market'][:55]}")
            print(f"       Entry: {o['price']:.3f} | Days: {o['days_left']:.0f} | Size: $37.50")
    else:
        print(f"    -> No qualifying monthly opportunities found")
        print(f"    -> Watch: FOMC Mar 17-18, Feb jobs report Mar 7, CPI Mar 11")

    print(f"\n  QUARTERLY ($50 = 20%):")
    print(f"    -> Already deployed: T003/T005 (Iran Mar 31)")
    print(f"    -> No new quarterly capital needed — current positions cover this bucket")

    print(f"\n  If the next $250 paper deployment is split 50% weekly / 30% monthly / 20% quarterly,")
    print(f"  what specific trades are available today?")
    print(f"  -> See S011-VIABLE section above for weekly candidates")
    print(f"  -> Monthly: FOMC/data release markets when they appear 7-30d before event")
    print(f"  -> Quarterly: already covered by existing T003/T005 positions")
    print()


def main():
    parser = argparse.ArgumentParser(description="Fast-resolution market screener")
    parser.add_argument("--days", type=int, default=7, help="Max days to resolution (default: 7)")
    parser.add_argument("--min-prob", type=float, default=0.95, help="Min probability threshold (default: 0.95)")
    parser.add_argument("--min-liq", type=float, default=20000, help="Min liquidity in USD (default: 20000)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--deploy", action="store_true", help="Include $250 deployment recommendation")
    args = parser.parse_args()

    # 7-day screen
    print(f"\n[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}]")
    opps_7d, skipped_7d = screen_fast_resolution(
        max_days=7, min_prob=args.min_prob, min_liq=args.min_liq, verbose=args.verbose
    )
    print_results(opps_7d, skipped_7d, 7, args.min_prob, args.min_liq)

    # 30-day screen (broader)
    opps_30d, skipped_30d = screen_fast_resolution(
        max_days=30, min_prob=0.90, min_liq=args.min_liq, verbose=args.verbose
    )
    print_results(opps_30d, skipped_30d, 30, 0.90, args.min_liq)

    if args.deploy:
        print_deployment_recommendation(opps_7d, opps_30d)


if __name__ == "__main__":
    main()
