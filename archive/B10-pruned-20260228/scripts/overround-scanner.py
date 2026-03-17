#!/usr/bin/env python3
"""
Overround Scanner (S007 Type 1)

Scans active Polymarket multi-outcome events for overround/underround pricing.
When the sum of YES prices across mutually exclusive outcomes deviates from 1.0,
an arbitrage opportunity exists.

Usage:
    python3 overround-scanner.py                  # Full scan
    python3 overround-scanner.py --min-edge 0.03  # Only show >=3% mispricing
    python3 overround-scanner.py --domain POL     # Filter by domain
    python3 overround-scanner.py --json           # JSON output
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone

# ============================================================
# CONFIGURATION
# ============================================================

# Minimum edge to flag (covers spread + execution friction)
MIN_EDGE_DEFAULT = 0.03  # 3%

# Events where sub-markets are NOT mutually exclusive (false positives)
# These are "by date" series or independent sub-markets that shouldn't sum to 1
NON_EXCLUSIVE_PATTERNS = [
    'by ',          # "by date" series — handled by temporal-checker instead
    'on ',          # "on date" daily markets
    'dip to',       # Multiple price levels, not mutually exclusive
    'reach $',      # Same
    'hit ',         # Price target series
    'above $',      # Price level series
    'between',      # Price range buckets (could be exclusive — check carefully)
    'less than',    # Threshold markets
    'more than',
    'Total Rounds', # Sports props
    'O/U',          # Over/under
    'Handicap',
]

DOMAIN_KEYWORDS = {
    'GEO': ['iran', 'strike', 'war', 'invasion', 'ceasefire', 'nato', 'ukraine',
             'russia', 'china', 'taiwan', 'israel', 'lebanon', 'khamenei',
             'regime', 'leader out', 'prime minister', 'grenell', 'venezuela',
             'greenland', 'annex', 'invade'],
    'CRY': ['bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol', 'xrp',
             'crypto', 'token', 'fdv', 'launch'],
    'POL': ['president', 'nomination', 'democrat', 'republican', 'trump',
             'election', 'nominate', 'congress', 'senate', 'governor',
             'fed chair', 'speaker', 'house', 'primary'],
    'ECO': ['fed ', 'interest rate', 'bps', 'gdp', 'inflation', 'cpi',
             'unemployment', 'revenue', 'treasury', 'bank of'],
    'TECH': ['ai model', 'anthropic', 'openai', 'google ai', 'chatgpt',
             'claude', 'gemini', 'gpt'],
    'ENV': ['earthquake', 'hurricane', 'snow', 'temperature', 'wildfire',
             'climate', 'storm'],
}

SPORTS_KEYWORDS = [
    'nba', 'nfl', 'nhl', 'mlb', 'ipl', 'premier league', 'serie a',
    'la liga', 'bundesliga', 'champions league', 'ufc', 'atp', 'wta',
    'formula 1', 'nascar', 'pga', 'cricket', 'rugby', 'wnba', 'mma',
    'copa', 'super bowl', 'ncaa', 'world cup', 'fifa', 'bo3', 'bo2',
    'bo1', 'bo5', 'map 1', 'map 2', 'o/u', 'total rounds', 'handicap',
    'counter-strike', 'dota', 'valorant', 'league of legends', 'cs2',
    'blast', 'iem', 'esl', 'cct', 'lck', 'lpl', 'lec',
    # Esports
    'lol:', 'cdl ', 'arabian league', 'challengers', 'kickoff',
    'esports', 'fnatic', 'g2 ', 'optic', 'faze',
    # Tennis
    'open:', 'open akron', 'antalya:', 'vs ', ' vs.',
    'set 1', 'set 2', 'game 1', 'game 2',
    # General sports patterns
    'first blood', 'total kills', 'game winner',
    'regular season', 'playoffs', 'championship',
    # More team/league names
    'eredivisie', 'ligue 1', 'super lig', 'eliteserien', 'allsvenskan',
    'jupiler', 'efl', 'shl', 'khl',
]


def curl_json(url):
    """Fetch JSON from a URL via curl."""
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '15',
             '-H', 'User-Agent: Mozilla/5.0', url],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def classify_domain(title):
    """Classify an event title into a domain."""
    t = title.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in t:
                return domain
    return 'OTHER'


def is_sports(title):
    """Check if an event is sports-related."""
    t = title.lower()
    return any(kw in t for kw in SPORTS_KEYWORDS)


def looks_non_exclusive(markets):
    """Check if sub-markets look like they're NOT mutually exclusive."""
    questions = [m.get('question', '').lower() for m in markets]

    # If many questions contain date/price patterns, likely not exclusive
    for pattern in NON_EXCLUSIVE_PATTERNS:
        matches = sum(1 for q in questions if pattern in q)
        if matches > len(questions) * 0.3:  # Lower threshold — catch more false positives
            return True

    # Props/handicaps are never mutually exclusive
    prop_patterns = ['o/u', 'over/under', 'handicap', 'total kills',
                     'first blood', 'game winner', 'set winner',
                     'total rounds', 'games o/u']
    for pattern in prop_patterns:
        if any(pattern in q for q in questions):
            return True

    return False


def fetch_events(include_sports=False):
    """Fetch active multi-outcome events from Gamma API."""
    all_events = []
    for offset in range(0, 1000, 100):
        url = (f"https://gamma-api.polymarket.com/events"
               f"?limit=100&closed=false&order=volume&offset={offset}")
        data = curl_json(url)
        if not data:
            break
        all_events.extend(data)
        if len(data) < 100:
            break
        time.sleep(0.25)

    # Filter to multi-outcome events
    multi = []
    for e in all_events:
        markets = e.get('markets', [])
        if len(markets) < 3:
            continue
        title = e.get('title', '')
        if not include_sports and is_sports(title):
            continue
        multi.append(e)

    return multi


def analyze_event(event):
    """Analyze an event for overround/underround."""
    title = event.get('title', '')
    markets = event.get('markets', [])
    domain = classify_domain(title)
    volume = float(event.get('volume', 0) or 0)

    # Parse each sub-market
    outcomes = []
    total_yes = 0
    active_count = 0

    for m in markets:
        q = m.get('question', '')
        closed = m.get('closed', False)

        try:
            prices = json.loads(m.get('outcomePrices', '[]'))
            yes_p = float(prices[0])
        except (json.JSONDecodeError, IndexError, ValueError):
            continue

        try:
            tokens = json.loads(m.get('clobTokenIds', '[]'))
            yes_token = tokens[0] if tokens else ''
        except json.JSONDecodeError:
            yes_token = ''

        vol = float(m.get('volumeNum', 0) or 0)

        if not closed and yes_p > 0.001:
            active_count += 1

        total_yes += yes_p
        outcomes.append({
            'question': q,
            'yes_price': yes_p,
            'volume': vol,
            'closed': closed,
            'yes_token': yes_token,
        })

    if active_count < 3:
        return None

    overround = total_yes - 1.0

    # Check if these are actually mutually exclusive
    non_exclusive = looks_non_exclusive(markets)

    # Sort by price descending
    outcomes.sort(key=lambda x: x['yes_price'], reverse=True)

    # Find most overpriced (highest price relative to others) and underpriced
    # In an overround scenario, selling the most overpriced outcome is the play
    # In an underround scenario, buying all outcomes is the play
    most_overpriced = outcomes[0] if outcomes else None
    most_underpriced = outcomes[-1] if outcomes else None

    # Calculate edge per dollar
    if overround > 0:
        # Overround: selling all YES costs $total_yes, pays $1 guaranteed
        # Profit = total_yes - 1.0
        edge_type = 'OVERROUND'
        edge_pct = overround
    elif overround < 0:
        # Underround: buying all YES costs $total_yes, pays $1 guaranteed
        # Profit = 1.0 - total_yes
        edge_type = 'UNDERROUND'
        edge_pct = -overround
    else:
        edge_type = 'FAIR'
        edge_pct = 0

    return {
        'title': title,
        'domain': domain,
        'volume': volume,
        'num_markets': len(outcomes),
        'active_count': active_count,
        'total_yes': total_yes,
        'overround': overround,
        'edge_type': edge_type,
        'edge_pct': edge_pct,
        'non_exclusive': non_exclusive,
        'outcomes': outcomes,
        'most_overpriced': most_overpriced,
        'most_underpriced': most_underpriced,
    }


def print_report(results, min_edge):
    """Print formatted overround report."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f"\n{'=' * 80}")
    print(f"S007 OVERROUND SCANNER — {now}")
    print(f"{'=' * 80}")
    print(f"Minimum edge threshold: {min_edge:.1%}")

    # Split into actionable vs informational
    actionable = [r for r in results
                  if abs(r['overround']) >= min_edge and not r['non_exclusive']]
    informational = [r for r in results
                     if abs(r['overround']) >= min_edge and r['non_exclusive']]
    fair = [r for r in results if abs(r['overround']) < min_edge]

    if actionable:
        print(f"\n--- ACTIONABLE ({len(actionable)}) --- mutually exclusive, edge >= {min_edge:.0%} ---")
        for i, r in enumerate(actionable):
            direction = 'SELL ALL YES' if r['edge_type'] == 'OVERROUND' else 'BUY ALL YES'
            print(f"\n  {i+1}. [{r['domain']:5s}] {r['title'][:70]}")
            print(f"     Markets: {r['active_count']} active / {r['num_markets']} total")
            print(f"     Volume: ${r['volume']:,.0f}")
            print(f"     Sum YES: {r['total_yes']:.4f} | {r['edge_type']}: {r['overround']:+.4f} ({r['edge_pct']:.1%} edge)")
            print(f"     Action: {direction}")

            # Show top outcomes
            print(f"     Top outcomes:")
            for o in r['outcomes'][:7]:
                flag = ''
                if o == r['most_overpriced'] and r['edge_type'] == 'OVERROUND':
                    flag = ' <-- most overpriced'
                print(f"       {o['yes_price']:6.1%} | ${o['volume']:>12,.0f} | {o['question'][:55]}{flag}")
            remaining = len(r['outcomes']) - 7
            if remaining > 0:
                tail_sum = sum(o['yes_price'] for o in r['outcomes'][7:])
                print(f"       ... {remaining} more outcomes (sum: {tail_sum:.1%})")

    if informational:
        print(f"\n--- INFORMATIONAL ({len(informational)}) --- likely non-exclusive (by-date/price series) ---")
        for i, r in enumerate(informational[:10]):
            print(f"  {i+1}. [{r['domain']:5s}] {r['title'][:60]} | sum={r['total_yes']:.2f} | {r['overround']:+.2f}")

    if fair:
        print(f"\n--- FAIR PRICING ({len(fair)}) --- edge < {min_edge:.0%} ---")
        for i, r in enumerate(fair[:10]):
            print(f"  {i+1}. [{r['domain']:5s}] {r['title'][:60]} | sum={r['total_yes']:.4f} | {r['overround']:+.4f}")

    # Summary stats
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    all_exclusive = [r for r in results if not r['non_exclusive']]
    if all_exclusive:
        avg_or = sum(r['overround'] for r in all_exclusive) / len(all_exclusive)
        overrounds = [r for r in all_exclusive if r['overround'] > min_edge]
        underrounds = [r for r in all_exclusive if r['overround'] < -min_edge]
        print(f"  Exclusive events analyzed: {len(all_exclusive)}")
        print(f"  Average overround: {avg_or:+.4f} ({avg_or*100:+.2f}%)")
        print(f"  Events with overround > {min_edge:.0%}: {len(overrounds)}")
        print(f"  Events with underround > {min_edge:.0%}: {len(underrounds)}")
    print(f"  Non-exclusive events skipped: {len(informational)}")
    print(f"{'=' * 80}")


def output_json(results, min_edge):
    """Output results as JSON."""
    output = []
    for r in results:
        if abs(r['overround']) < min_edge:
            continue
        output.append({
            'title': r['title'],
            'domain': r['domain'],
            'volume': r['volume'],
            'num_markets': r['num_markets'],
            'total_yes': r['total_yes'],
            'overround': r['overround'],
            'edge_type': r['edge_type'],
            'edge_pct': r['edge_pct'],
            'non_exclusive': r['non_exclusive'],
            'outcomes': [{
                'question': o['question'],
                'yes_price': o['yes_price'],
                'volume': o['volume'],
                'yes_token': o['yes_token'],
            } for o in r['outcomes']],
        })
    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(description='S007 Overround Scanner')
    parser.add_argument('--min-edge', type=float, default=MIN_EDGE_DEFAULT,
                        help=f'Minimum edge to flag (default: {MIN_EDGE_DEFAULT})')
    parser.add_argument('--domain', type=str, default=None,
                        help='Filter by domain (GEO, CRY, POL, ECO, TECH, ENV, OTHER)')
    parser.add_argument('--include-sports', action='store_true',
                        help='Include sports events')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    args = parser.parse_args()

    if not args.json:
        print("Fetching multi-outcome events from Polymarket...")

    events = fetch_events(include_sports=args.include_sports)
    if not args.json:
        print(f"  Found {len(events)} multi-outcome events")

    # Analyze each event
    results = []
    for e in events:
        analysis = analyze_event(e)
        if analysis is None:
            continue
        if args.domain and analysis['domain'] != args.domain:
            continue
        results.append(analysis)

    # Sort by edge magnitude
    results.sort(key=lambda x: abs(x['overround']), reverse=True)

    if args.json:
        output_json(results, args.min_edge)
    else:
        print_report(results, args.min_edge)


if __name__ == '__main__':
    main()
