#!/usr/bin/env python3
"""
Price History Collector (I02)

Fetches price history from the Polymarket CLOB API for resolved markets
and enriches the backtest-ready dataset.

IMPORTANT: The CLOB API purges price history for most resolved/closed markets.
This script attempts to collect what's available and reports the hit rate.

Usage:
    python3 collect-price-history.py                 # Fetch for top 200 markets
    python3 collect-price-history.py --limit 50      # Fetch for top 50 only
    python3 collect-price-history.py --active         # Also fetch active market history
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

# ============================================================
# CONFIGURATION
# ============================================================

DATA_DIR = "/Users/yu/Desktop/prediction-markets/data/polymarket"
BACKTEST_FILE = f"{DATA_DIR}/backtest-ready.json"
HISTORY_DIR = f"{DATA_DIR}/price-history"

# ============================================================
# DATA FETCHING
# ============================================================

def curl_json(url):
    """Fetch JSON from URL via curl."""
    result = subprocess.run(
        ['curl', '-s', '--max-time', '15',
         '-H', 'User-Agent: Mozilla/5.0',
         url],
        capture_output=True, text=True, timeout=20
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def fetch_price_history(token_id, interval='1d'):
    """Fetch price history from CLOB API. Returns list of {t, p} dicts."""
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval={interval}&fidelity=1"
    data = curl_json(url)
    if not data or not isinstance(data, dict):
        return []
    return data.get('history', [])


def process_history(history):
    """Convert raw history to standardized format."""
    points = []
    for h in history:
        ts = h.get('t', 0)
        price = float(h.get('p', 0))
        # Convert timestamp to date string
        if isinstance(ts, (int, float)) and ts > 0:
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
        else:
            date_str = str(ts)
        points.append({"date": date_str, "price": price})
    return points


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Collect price history for resolved markets")
    parser.add_argument("--limit", type=int, default=200,
                        help="Max markets to fetch history for (default: 200)")
    parser.add_argument("--active", action="store_true",
                        help="Also fetch active market history for comparison")
    args = parser.parse_args()

    print("=" * 80)
    print("POLYMARKET PRICE HISTORY COLLECTOR (I02)")
    print("=" * 80)

    # Ensure output directory exists
    os.makedirs(HISTORY_DIR, exist_ok=True)

    # Load backtest-ready data
    print(f"\n[1] Loading backtest data from {BACKTEST_FILE}...")
    try:
        with open(BACKTEST_FILE) as f:
            markets = json.load(f)
    except FileNotFoundError:
        print("    ERROR: Run collect-resolved.py first.")
        sys.exit(1)

    print(f"    Loaded {len(markets)} markets")

    # Filter to markets with CLOB token IDs
    with_tokens = [m for m in markets if m.get("clob_token_ids")]
    print(f"    Markets with CLOB tokens: {len(with_tokens)}")

    # Take top N by volume
    candidates = sorted(with_tokens, key=lambda x: x["volume"], reverse=True)[:args.limit]
    print(f"    Fetching history for top {len(candidates)} by volume")

    # Fetch price histories
    print(f"\n[2] Fetching price histories from CLOB API...")
    print(f"    NOTE: CLOB often purges history for resolved markets.\n")

    found = 0
    empty = 0
    errors = 0
    enriched = 0

    for i, mkt in enumerate(candidates):
        tokens = mkt["clob_token_ids"]
        if not tokens:
            continue

        yes_token = tokens[0]
        slug = mkt.get("title", "")[:60].replace(" ", "-").lower()
        slug = ''.join(c for c in slug if c.isalnum() or c == '-')[:50]

        print(f"  [{i+1:>3}/{len(candidates)}] {mkt['title'][:70]}...", end="", flush=True)

        history = fetch_price_history(yes_token)
        time.sleep(0.3)  # Rate limiting

        if history and len(history) > 1:
            found += 1
            points = process_history(history)
            print(f" OK ({len(points)} points)")

            # Save individual file
            fname = f"{mkt['market_id']}.json"
            with open(os.path.join(HISTORY_DIR, fname), "w") as f:
                json.dump({
                    "market_id": mkt["market_id"],
                    "title": mkt["title"],
                    "domain": mkt["domain"],
                    "outcome": mkt["outcome"],
                    "volume": mkt["volume"],
                    "history": points,
                }, f, indent=2)

            # Enrich backtest data
            mkt["price_history"] = points
            enriched += 1
        elif history is not None:
            empty += 1
            print(" EMPTY (purged)")
        else:
            errors += 1
            print(" ERROR")

    # Save enriched backtest file
    print(f"\n[3] Saving enriched backtest data...")
    with open(BACKTEST_FILE, "w") as f:
        json.dump(markets, f, indent=2)

    # Summary
    print(f"\n{'=' * 80}")
    print("PRICE HISTORY COLLECTION SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Attempted:      {len(candidates)}")
    print(f"  With history:   {found} ({found/len(candidates):.1%})")
    print(f"  Empty (purged): {empty} ({empty/len(candidates):.1%})")
    print(f"  Errors:         {errors}")
    print(f"  Enriched in backtest-ready.json: {enriched}")
    print(f"  Individual files saved to: {HISTORY_DIR}/")

    if found == 0:
        print(f"\n  WARNING: No price history available for resolved markets.")
        print(f"  This confirms the known CLOB API limitation: price history")
        print(f"  is purged after market resolution.")
        print(f"\n  RECOMMENDATION: Collect price history for ACTIVE markets")
        print(f"  before they resolve. Use --active flag or run spike-collector.py")
        print(f"  on a cron schedule to build a forward-looking dataset.")

    # Optionally fetch active market history
    if args.active:
        print(f"\n[4] Fetching active market history for comparison...")
        active_url = ("https://gamma-api.polymarket.com/markets?"
                      "limit=50&closed=false&order=volume&ascending=false")
        active_data = curl_json(active_url)
        if active_data:
            active_found = 0
            for m in active_data[:30]:
                try:
                    tokens = json.loads(m.get("clobTokenIds", "[]"))
                except (json.JSONDecodeError, TypeError):
                    continue
                if not tokens:
                    continue

                q = m.get("question", "")[:60]
                history = fetch_price_history(tokens[0])
                time.sleep(0.3)
                if history and len(history) > 1:
                    active_found += 1
                    print(f"    ACTIVE: {q}... ({len(history)} points)")

            print(f"\n  Active markets with history: {active_found}/30")
            print(f"  (Active markets retain price history — use for forward testing)")

    print(f"\n{'=' * 80}")
    print("DONE")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
