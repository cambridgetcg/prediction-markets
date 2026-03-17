#!/usr/bin/env python3
"""
Resolved Events Collector (I02)

Collects historical resolved Polymarket events for backtesting.
Paginates the Gamma API, classifies by domain, filters sports/small markets,
and produces a structured dataset.

Usage:
    python3 collect-resolved.py                  # Collect all resolved events
    python3 collect-resolved.py --min-volume 50000  # Higher volume threshold
    python3 collect-resolved.py --stats          # Stats only (skip fetch, read existing)
    python3 collect-resolved.py --json           # Print raw JSON to stdout
"""

import argparse
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

# ============================================================
# CONFIGURATION
# ============================================================

DATA_DIR = "/Users/yu/Desktop/prediction-markets/data/polymarket"
OUTPUT_FILE = f"{DATA_DIR}/resolved-events.json"
BACKTEST_FILE = f"{DATA_DIR}/backtest-ready.json"
SUMMARY_FILE = f"{DATA_DIR}/dataset-summary.md"

# Paginate up to offset 2000 (known Gamma API max)
MAX_OFFSET = 2000
PAGE_SIZE = 100

MIN_VOLUME_DEFAULT = 10000  # $10K

# ============================================================
# DOMAIN CLASSIFICATION
# ============================================================

DOMAIN_KEYWORDS = {
    "GEO": ["strike", "war", "military", "ceasefire", "troops", "invasion",
            "iran", "russia", "ukraine", "israel", "nato", "nuclear",
            "houthi", "hezbollah", "taiwan", "china ", "north korea",
            "sanctions", "troops", "missile", "bomb", "annex", "occupy"],
    "POL": ["trump", "biden", "election", "president", "congress", "senate",
            "democrat", "republican", "impeach", "nomination", "appointed",
            "governor", "mayor", "speaker", "veto", "executive order",
            "cabinet", "resign", "pardon", "musk", "doge"],
    "ECO": ["fed ", "interest rate", "gdp", "inflation", "recession",
            "unemployment", "tariff", "treasury", "cpi", "bps",
            "revenue", "deficit", "trade war", "s&p", "dow jones"],
    "FIN": ["stock", "ipo", "market cap", "earnings", "shares",
            "bankruptcy", "acquisition", "merger", "nasdaq"],
    "CRY": ["bitcoin", "ethereum", "crypto", "btc", "eth", "token",
            "airdrop", "solana", "dogecoin", "xrp", "fdv",
            "defi", "nft", "stablecoin", "memecoin"],
    "TEC": ["ai ", "artificial intelligence", "gpt", "openai", "google",
            "apple", "tesla", "spacex", "nvidia", "anthropic", "chatgpt",
            "claude", "tiktok", "meta ", "microsoft", "amazon"],
    "LAW": ["court", "judge", "lawsuit", "indictment", "trial",
            "verdict", "epstein", "ruling", "extradite", "plea",
            "convicted", "sentenced", "supreme court"],
    "ENV": ["climate", "hurricane", "earthquake", "temperature",
            "emissions", "sea level", "wildfire", "tornado", "flood",
            "measles", "bird flu", "drought"],
    "SCI": ["pandemic", "vaccine", "virus", "outbreak", "fda approved",
            "clinical trial", "mars", "moon landing", "nasa"],
    "SOC": ["oscar", "grammy", "super bowl", "world cup", "olympics",
            "tiktok ban", "social media", "netflix"],
}

SPORTS_KEYWORDS = [
    'nba', 'nfl', 'nhl', 'mlb', 'ipl', 'premier league', 'serie a',
    'la liga', 'bundesliga', 'champions league', 'ufc', 'atp', 'wta',
    'formula 1', 'nascar', 'pga', 'cricket', 'rugby', 'wnba', 'mma',
    'copa', 'super bowl', 'march madness', 'world series',
    'stanley cup', 'ncaa', 'epl', 'eredivisie', 'ligue 1',
    'counter-strike', 'dota', 'valorant', 'league of legends', 'cs2',
    'blast', 'iem', 'esl', 'cct', 'up or down', 'bo3', 'bo2', 'bo1',
    'map 1', 'map 2', 'map 3', 'o/u', 'total rounds', 'handicap',
    'efl', 'super lig', 'jupiler', 'eliteserien', 'allsvenskan',
    'veikkausliiga',
    # Team names
    'pacers', 'grizzlies', 'lakers', 'celtics', 'warriors', 'nuggets',
    'thunder', 'bucks', 'cavaliers', 'rockets', 'knicks', 'wolves',
    'pistons', 'spurs', 'suns', 'kings', 'mavericks', 'nets', 'heat',
    'magic', 'hawks', 'raptors', 'hornets', 'bulls', 'clippers',
    '76ers', 'pelicans', 'wizards', 'jazz', 'blazers',
    'yankees', 'red sox', 'dodgers', 'mets', 'cubs', 'braves',
    'astros', 'phillies', 'cardinals', 'padres', 'giants', 'orioles',
    'chiefs', 'eagles', 'bills', 'lions', 'ravens', 'commanders',
    'steelers', 'texans', 'chargers', '49ers', 'seahawks', 'packers',
]


def classify_domain(question):
    """Classify a market question into a domain."""
    q = question.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                return domain
    return "OTHER"


def is_sports(question):
    """Check if a market is sports-related."""
    q = question.lower()
    return any(kw in q for kw in SPORTS_KEYWORDS)


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
        print(f"  curl error: {result.stderr}", file=sys.stderr)
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error: {e}", file=sys.stderr)
        return None


def fetch_resolved_events():
    """Fetch all resolved events from Gamma API, paginating through offsets."""
    all_events = []
    seen_ids = set()

    for offset in range(0, MAX_OFFSET + 1, PAGE_SIZE):
        url = (
            f"https://gamma-api.polymarket.com/events?"
            f"closed=true&order=volume&ascending=false"
            f"&limit={PAGE_SIZE}&offset={offset}"
        )
        print(f"  Fetching offset={offset}...", end="", flush=True)
        data = curl_json(url)
        if not data:
            print(" ERROR")
            break
        if not isinstance(data, list) or len(data) == 0:
            print(" empty — done")
            break

        new = 0
        for event in data:
            eid = event.get("id", "")
            if eid and eid not in seen_ids:
                seen_ids.add(eid)
                all_events.append(event)
                new += 1

        print(f" {new} new events (total: {len(all_events)})")

        if len(data) < PAGE_SIZE:
            print("  Reached last page")
            break
        time.sleep(0.25)

    return all_events


def parse_event(event, min_volume):
    """Parse a Gamma API event into structured market records."""
    records = []
    event_title = event.get("title", "")
    event_slug = event.get("slug", "")
    event_id = event.get("id", "")

    for mkt in event.get("markets", []):
        question = mkt.get("question", "")

        # Skip sports
        if is_sports(question) or is_sports(event_title):
            continue

        # Parse outcome prices to determine resolution
        try:
            prices = json.loads(mkt.get("outcomePrices", "[]"))
            yes_final = float(prices[0])
            no_final = float(prices[1]) if len(prices) > 1 else 1 - yes_final
        except (json.JSONDecodeError, IndexError, ValueError, TypeError):
            continue

        # Determine resolution
        if yes_final >= 0.99:
            outcome = "YES"
        elif no_final >= 0.99:
            outcome = "NO"
        else:
            outcome = f"AMBIGUOUS({yes_final:.2f})"

        # Volume filter
        vol = float(mkt.get("volume", 0) or mkt.get("volumeNum", 0) or 0)
        if vol < min_volume:
            continue

        # Parse dates
        created = mkt.get("createdAt", mkt.get("startDate", ""))
        end_date = mkt.get("endDate", "")
        closed_at = mkt.get("closedTime", mkt.get("updatedAt", ""))

        # Compute duration in days
        duration_days = None
        if created and end_date:
            try:
                t0 = datetime.fromisoformat(created.replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                duration_days = max(1, (t1 - t0).days)
            except (ValueError, TypeError):
                pass

        # Parse CLOB token IDs (for future price history)
        try:
            tokens = json.loads(mkt.get("clobTokenIds", "[]"))
        except (json.JSONDecodeError, TypeError):
            tokens = []

        domain = classify_domain(question)

        # Check if "by date" pattern
        is_by_date = bool(re.search(
            r"\b(by|before)\b.*\b(20\d{2}|january|february|march|april|may|june|"
            r"july|august|september|october|november|december|"
            r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
            question, re.I
        ))

        records.append({
            "market_id": mkt.get("id", ""),
            "condition_id": mkt.get("conditionId", ""),
            "event_id": event_id,
            "event_title": event_title,
            "event_slug": event_slug,
            "question": question,
            "slug": mkt.get("slug", ""),
            "domain": domain,
            "outcome": outcome,
            "yes_final_price": yes_final,
            "no_final_price": no_final,
            "volume": vol,
            "liquidity": float(mkt.get("liquidityNum", 0) or 0),
            "created": created[:10] if created else "",
            "end_date": end_date[:10] if end_date else "",
            "closed_at": closed_at[:10] if closed_at else "",
            "duration_days": duration_days,
            "is_by_date": is_by_date,
            "clob_token_ids": tokens,
        })

    return records


# ============================================================
# STATISTICS
# ============================================================

def compute_stats(records):
    """Compute dataset statistics."""
    total = len(records)
    if total == 0:
        return {}

    yes_count = sum(1 for r in records if r["outcome"] == "YES")
    no_count = sum(1 for r in records if r["outcome"] == "NO")
    ambiguous = total - yes_count - no_count

    # By domain
    by_domain = defaultdict(lambda: {"total": 0, "yes": 0, "no": 0, "volume": 0})
    for r in records:
        d = r["domain"]
        by_domain[d]["total"] += 1
        by_domain[d]["volume"] += r["volume"]
        if r["outcome"] == "YES":
            by_domain[d]["yes"] += 1
        elif r["outcome"] == "NO":
            by_domain[d]["no"] += 1

    # Volume buckets
    vol_buckets = {"<$50K": 0, "$50K-$250K": 0, "$250K-$1M": 0, "$1M+": 0}
    vol_outcome = {"<$50K": [0, 0], "$50K-$250K": [0, 0], "$250K-$1M": [0, 0], "$1M+": [0, 0]}
    for r in records:
        v = r["volume"]
        if v < 50000:
            bucket = "<$50K"
        elif v < 250000:
            bucket = "$50K-$250K"
        elif v < 1000000:
            bucket = "$250K-$1M"
        else:
            bucket = "$1M+"
        vol_buckets[bucket] += 1
        if r["outcome"] == "YES":
            vol_outcome[bucket][0] += 1
        elif r["outcome"] == "NO":
            vol_outcome[bucket][1] += 1

    # Duration
    durations = [r["duration_days"] for r in records if r["duration_days"]]
    avg_duration = sum(durations) / len(durations) if durations else 0
    median_duration = sorted(durations)[len(durations) // 2] if durations else 0

    # By-date markets
    by_date_markets = [r for r in records if r["is_by_date"]]
    by_date_yes = sum(1 for r in by_date_markets if r["outcome"] == "YES")
    by_date_no = sum(1 for r in by_date_markets if r["outcome"] == "NO")

    return {
        "total": total,
        "yes_count": yes_count,
        "no_count": no_count,
        "ambiguous": ambiguous,
        "yes_rate": yes_count / total,
        "no_rate": no_count / total,
        "by_domain": dict(by_domain),
        "vol_buckets": vol_buckets,
        "vol_outcome": vol_outcome,
        "avg_duration_days": avg_duration,
        "median_duration_days": median_duration,
        "by_date_total": len(by_date_markets),
        "by_date_yes": by_date_yes,
        "by_date_no": by_date_no,
        "by_date_no_rate": by_date_no / len(by_date_markets) if by_date_markets else 0,
    }


def write_summary(stats, records):
    """Write dataset-summary.md."""
    lines = []
    lines.append("# Polymarket Resolved Markets Dataset")
    lines.append(f"\nGenerated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"\n## Overview")
    lines.append(f"- **Total resolved markets**: {stats['total']}")
    lines.append(f"- **Resolved YES**: {stats['yes_count']} ({stats['yes_rate']:.1%})")
    lines.append(f"- **Resolved NO**: {stats['no_count']} ({stats['no_rate']:.1%})")
    lines.append(f"- **Ambiguous**: {stats['ambiguous']}")
    lines.append(f"- **Avg duration**: {stats['avg_duration_days']:.0f} days")
    lines.append(f"- **Median duration**: {stats['median_duration_days']:.0f} days")

    # YES overpricing finding
    if stats["no_rate"] > 0.5:
        lines.append(f"\n> **Finding**: YES is systematically overpriced. "
                     f"{stats['no_rate']:.1%} of markets resolve NO.")

    # By-date subset
    lines.append(f"\n## \"By Date\" Markets (Time Decay Subset)")
    lines.append(f"- Total: {stats['by_date_total']}")
    lines.append(f"- Resolved YES: {stats['by_date_yes']}")
    lines.append(f"- Resolved NO: {stats['by_date_no']} "
                 f"({stats['by_date_no_rate']:.1%} NO rate)")

    # Domain breakdown
    lines.append(f"\n## Distribution by Domain")
    lines.append(f"\n| Domain | Markets | YES | NO | NO Rate | Total Volume |")
    lines.append(f"|--------|---------|-----|-----|---------|-------------|")
    for d in sorted(stats["by_domain"].keys(),
                    key=lambda x: stats["by_domain"][x]["total"], reverse=True):
        info = stats["by_domain"][d]
        t = info["total"]
        y = info["yes"]
        n = info["no"]
        no_rate = n / t if t > 0 else 0
        vol = info["volume"]
        lines.append(f"| {d:<6} | {t:>7} | {y:>3} | {n:>3} | {no_rate:>6.1%} | ${vol:>12,.0f} |")

    # Volume distribution
    lines.append(f"\n## Distribution by Volume")
    lines.append(f"\n| Bucket | Markets | YES | NO | NO Rate |")
    lines.append(f"|--------|---------|-----|-----|---------|")
    for bucket in ["<$50K", "$50K-$250K", "$250K-$1M", "$1M+"]:
        count = stats["vol_buckets"][bucket]
        y, n = stats["vol_outcome"][bucket]
        no_rate = n / count if count > 0 else 0
        lines.append(f"| {bucket:<11} | {count:>7} | {y:>3} | {n:>3} | {no_rate:>6.1%} |")

    # Quick analysis
    lines.append(f"\n## Quick Analysis")
    lines.append(f"\n### 1. Is YES systematically overpriced?")
    if stats["no_rate"] > 0.60:
        lines.append(f"**YES.** {stats['no_rate']:.1%} of all resolved markets resolve NO. "
                     f"This confirms systematic overpricing of YES outcomes.")
    elif stats["no_rate"] > 0.50:
        lines.append(f"Mild overpricing. {stats['no_rate']:.1%} resolve NO — slight edge for NO sellers.")
    else:
        lines.append(f"No clear overpricing. {stats['no_rate']:.1%} resolve NO.")

    lines.append(f"\n### 2. Do high-volume markets resolve differently?")
    big = stats["vol_outcome"]["$1M+"]
    small = stats["vol_outcome"]["<$50K"]
    big_no = big[1] / (big[0] + big[1]) if (big[0] + big[1]) > 0 else 0
    small_no = small[1] / (small[0] + small[1]) if (small[0] + small[1]) > 0 else 0
    lines.append(f"- $1M+ markets NO rate: {big_no:.1%}")
    lines.append(f"- <$50K markets NO rate: {small_no:.1%}")
    if abs(big_no - small_no) > 0.05:
        if big_no < small_no:
            lines.append(f"- High-volume markets are **more efficient** (lower NO rate = less overpricing)")
        else:
            lines.append(f"- High-volume markets are **more overpriced** (surprising)")
    else:
        lines.append(f"- No significant difference by volume")

    lines.append(f"\n### 3. Domain-level differences")
    lines.append(f"Domains with enough data for statistical significance (n>20):")
    for d in sorted(stats["by_domain"].keys(),
                    key=lambda x: stats["by_domain"][x]["total"], reverse=True):
        info = stats["by_domain"][d]
        if info["total"] >= 20:
            no_rate = info["no"] / info["total"]
            lines.append(f"- **{d}**: {info['total']} markets, {no_rate:.1%} NO rate")

    with open(SUMMARY_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n  Summary written to {SUMMARY_FILE}")


def write_backtest_ready(records):
    """Write standardized backtest-ready.json."""
    bt = []
    for r in records:
        if r["outcome"] in ("YES", "NO"):
            bt.append({
                "market_id": r["market_id"],
                "title": r["question"],
                "event_title": r["event_title"],
                "domain": r["domain"],
                "created": r["created"],
                "end_date": r["end_date"],
                "resolved": r["closed_at"],
                "outcome": r["outcome"],
                "volume": r["volume"],
                "liquidity": r["liquidity"],
                "final_price": r["yes_final_price"],
                "duration_days": r["duration_days"],
                "is_by_date": r["is_by_date"],
                "clob_token_ids": r["clob_token_ids"],
                "price_history": [],  # Populated by collect-price-history.py
            })
    bt.sort(key=lambda x: x["volume"], reverse=True)

    with open(BACKTEST_FILE, "w") as f:
        json.dump(bt, f, indent=2)
    print(f"  Backtest-ready file written: {len(bt)} markets -> {BACKTEST_FILE}")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Collect resolved Polymarket events")
    parser.add_argument("--min-volume", type=float, default=MIN_VOLUME_DEFAULT,
                        help=f"Min market volume in USD (default: {MIN_VOLUME_DEFAULT})")
    parser.add_argument("--stats", action="store_true",
                        help="Stats only — read existing data, skip fetch")
    parser.add_argument("--json", action="store_true",
                        help="Print raw JSON to stdout")
    args = parser.parse_args()

    print("=" * 80)
    print("POLYMARKET RESOLVED EVENTS COLLECTOR (I02)")
    print("=" * 80)

    if args.stats:
        # Read existing data
        print(f"\n[1] Reading existing data from {OUTPUT_FILE}")
        try:
            with open(OUTPUT_FILE) as f:
                records = json.load(f)
            print(f"    Loaded {len(records)} records")
        except FileNotFoundError:
            print("    ERROR: No existing data. Run without --stats first.")
            sys.exit(1)
    else:
        # Fetch from API
        print(f"\n[1] Fetching resolved events from Gamma API...")
        events = fetch_resolved_events()
        print(f"    Total events fetched: {len(events)}")

        # Parse into market records
        print(f"\n[2] Parsing markets (min volume: ${args.min_volume:,.0f})...")
        records = []
        for event in events:
            records.extend(parse_event(event, args.min_volume))
        print(f"    Total qualifying markets: {len(records)}")

        # Deduplicate by market_id
        seen = set()
        unique = []
        for r in records:
            mid = r["market_id"]
            if mid and mid not in seen:
                seen.add(mid)
                unique.append(r)
        records = unique
        print(f"    After dedup: {len(records)}")

        # Save raw data
        with open(OUTPUT_FILE, "w") as f:
            json.dump(records, f, indent=2)
        print(f"    Saved to {OUTPUT_FILE}")

    if args.json:
        print(json.dumps(records, indent=2))
        return

    # Compute and display stats
    print(f"\n[3] Computing statistics...")
    stats = compute_stats(records)

    print(f"\n{'=' * 80}")
    print("DATASET OVERVIEW")
    print(f"{'=' * 80}")
    print(f"  Total markets:    {stats['total']}")
    print(f"  Resolved YES:     {stats['yes_count']} ({stats['yes_rate']:.1%})")
    print(f"  Resolved NO:      {stats['no_count']} ({stats['no_rate']:.1%})")
    print(f"  Ambiguous:        {stats['ambiguous']}")
    print(f"  Avg duration:     {stats['avg_duration_days']:.0f} days")
    print(f"  Median duration:  {stats['median_duration_days']:.0f} days")

    print(f"\n  'By date' markets: {stats['by_date_total']} "
          f"(NO rate: {stats['by_date_no_rate']:.1%})")

    print(f"\n  Domain breakdown:")
    for d in sorted(stats["by_domain"].keys(),
                    key=lambda x: stats["by_domain"][x]["total"], reverse=True):
        info = stats["by_domain"][d]
        no_rate = info["no"] / info["total"] if info["total"] > 0 else 0
        print(f"    {d:<6}: {info['total']:>4} markets, "
              f"NO rate {no_rate:>5.1%}, vol ${info['volume']:>12,.0f}")

    print(f"\n  Volume distribution:")
    for bucket in ["<$50K", "$50K-$250K", "$250K-$1M", "$1M+"]:
        count = stats["vol_buckets"][bucket]
        y, n = stats["vol_outcome"][bucket]
        no_rate = n / count if count > 0 else 0
        print(f"    {bucket:<11}: {count:>4} markets, NO rate {no_rate:.1%}")

    # Write summary and backtest files
    print(f"\n[4] Writing output files...")
    write_summary(stats, records)
    write_backtest_ready(records)

    print(f"\n{'=' * 80}")
    print("DONE")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
