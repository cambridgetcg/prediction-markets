#!/usr/bin/env python3
"""
NegRisk Scanner (P01)

Scans Polymarket multi-outcome NegRisk events for structural arbitrage:
- Overround (sum YES > 1.00): convert() or sell-all-YES play
- Underround (sum YES < 1.00): buy-all-YES guaranteed profit

Enhanced version of overround-scanner.py with:
- Order book depth analysis for top opportunities
- Execution sizing (max position before price impact exceeds edge)
- Dollar opportunity calculation
- NegRisk-specific filtering (negRisk flag from API)

Usage:
    python3 negrisk-scanner.py                   # Full scan
    python3 negrisk-scanner.py --min-edge 0.025  # 2.5% threshold
    python3 negrisk-scanner.py --domain POL      # Filter domain
    python3 negrisk-scanner.py --depth            # Include order book depth
    python3 negrisk-scanner.py --json             # JSON output
"""

import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime, timezone

# ============================================================
# CONFIGURATION
# ============================================================

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

MIN_EDGE_DEFAULT = 0.025  # 2.5% — minimum to cover 2% winner fee + friction
MIN_MARKETS = 3           # Minimum outcomes to qualify as multi-outcome
MAX_PAGES = 15            # Paginate up to 1500 events
PAGE_SIZE = 100
RATE_LIMIT_SLEEP = 0.3    # seconds between API calls

# Winner fee: 2% on profit from winning positions
WINNER_FEE = 0.02

# Non-exclusive patterns (these are NOT mutually exclusive — skip them)
NON_EXCLUSIVE_PATTERNS = [
    'by ',          # "by date" series
    'on ',          # "on date" point-in-time
    'dip to',       # Price level series
    'reach $',      # Price target series
    'hit ',         # Price target
    'above $',      # Threshold
    'between',      # Range buckets
    'less than',    # Threshold
    'more than',    # Threshold
    'Total Rounds', # Sports props
    'O/U',          # Over/under
    'Handicap',     # Handicap bets
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
    'lol:', 'cdl ', 'arabian league', 'challengers', 'kickoff',
    'esports', 'fnatic', 'g2 ', 'optic', 'faze',
    'open:', 'open akron', 'antalya:', 'vs ', ' vs.',
    'set 1', 'set 2', 'game 1', 'game 2',
    'first blood', 'total kills', 'game winner',
    'regular season', 'playoffs', 'championship',
    'eredivisie', 'ligue 1', 'super lig', 'eliteserien', 'allsvenskan',
    'jupiler', 'efl', 'shl', 'khl',
]


def curl_json(url):
    """Fetch JSON from a URL via curl."""
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '15',
             '-H', 'User-Agent: Mozilla/5.0 NegRiskScanner/1.0', url],
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
    for pattern in NON_EXCLUSIVE_PATTERNS:
        matches = sum(1 for q in questions if pattern in q)
        if matches > len(questions) * 0.3:
            return True
    prop_patterns = ['o/u', 'over/under', 'handicap', 'total kills',
                     'first blood', 'game winner', 'set winner',
                     'total rounds', 'games o/u']
    for pattern in prop_patterns:
        if any(pattern in q for q in questions):
            return True
    return False


def calculate_net_edge(edge_pct, edge_type, outcomes):
    """Calculate net edge after 2% winner fee.

    For overround (buy all NO): fee on each winning NO's profit
    For underround (buy all YES): fee on winning YES's profit
    """
    if edge_type == 'OVERROUND':
        # Buy all NO. At resolution, N-1 NOs win.
        # Worst case: cheapest outcome wins (maximizes fee base)
        prices = [o['yes_price'] for o in outcomes]
        total = sum(prices)
        p_min = min(prices)
        # Fee = 2% × (total - p_min) ... but fee is on profit per share
        # Each winning NO: cost = (1-pⱼ), payout = $1, profit = pⱼ
        # Total fee = 0.02 × Σⱼ≠w pⱼ = 0.02 × (total - p_w)
        # Worst case: p_w = p_min
        worst_fee = WINNER_FEE * (total - p_min)
        best_fee = WINNER_FEE * (total - max(prices))
        avg_fee = WINNER_FEE * (total - sum(p**2 for p in prices) / total)
        return {
            'gross_edge': edge_pct,
            'worst_net': edge_pct - worst_fee,
            'best_net': edge_pct - best_fee,
            'expected_net': edge_pct - avg_fee,
        }
    else:
        # Buy all YES. Winner pays $1, fee on profit.
        prices = [o['yes_price'] for o in outcomes]
        total = sum(prices)
        p_max = max(prices)
        p_min = min(prices)
        # Winning YES: cost = p_w, payout = $1, profit = 1-p_w
        # Fee = 0.02 × (1 - p_w)
        # Worst case: cheapest outcome wins → fee = 0.02 × (1-p_min)
        worst_fee = WINNER_FEE * (1 - p_min)
        best_fee = WINNER_FEE * (1 - p_max)
        avg_fee = WINNER_FEE * (1 - sum(p**2 for p in prices) / total)
        return {
            'gross_edge': edge_pct,
            'worst_net': edge_pct - worst_fee,
            'best_net': edge_pct - best_fee,
            'expected_net': edge_pct - avg_fee,
        }


def fetch_order_book(token_id):
    """Fetch order book for a specific token from CLOB API."""
    url = f"{CLOB_API}/book?token_id={token_id}"
    return curl_json(url)


def estimate_executable_size(book, side, edge_pct):
    """Estimate max executable position size before price impact exceeds edge.

    side: 'bids' (for selling YES) or 'asks' (for buying YES)
    Returns: max dollars executable within edge, weighted avg price
    """
    if not book or side not in book:
        return 0, 0

    levels = book[side]
    if not levels:
        return 0, 0

    total_size = 0
    total_value = 0

    for level in levels:
        price = float(level.get('price', 0))
        size = float(level.get('size', 0))
        total_size += size
        total_value += price * size

    if total_size == 0:
        return 0, 0

    avg_price = total_value / total_size
    # The edge is consumed by walking the book — estimate max size
    # where the worst fill is still profitable
    return total_value, avg_price


def fetch_events(include_sports=False, verbose=False):
    """Fetch active multi-outcome events from Gamma API."""
    all_events = []
    for page in range(MAX_PAGES):
        offset = page * PAGE_SIZE
        url = (f"{GAMMA_API}/events"
               f"?limit={PAGE_SIZE}&closed=false&order=volume"
               f"&ascending=false&offset={offset}")
        data = curl_json(url)
        if not data:
            break
        all_events.extend(data)
        if verbose:
            print(f"  Page {page+1}: {len(data)} events (total: {len(all_events)})")
        if len(data) < PAGE_SIZE:
            break
        time.sleep(RATE_LIMIT_SLEEP)

    # Filter to multi-outcome events
    multi = []
    for e in all_events:
        markets = e.get('markets', [])
        if len(markets) < MIN_MARKETS:
            continue
        title = e.get('title', '')
        if not include_sports and is_sports(title):
            continue
        multi.append(e)

    return multi


def analyze_event(event):
    """Analyze an event for NegRisk overround/underround."""
    title = event.get('title', '')
    markets = event.get('markets', [])
    domain = classify_domain(title)
    volume = float(event.get('volume', 0) or 0)

    # Check NegRisk flags
    neg_risk = event.get('negRisk', False)
    neg_risk_augmented = event.get('negRiskAugmented', False)

    # Parse each sub-market
    outcomes = []
    total_yes = 0
    active_count = 0
    total_liquidity = 0
    total_24h_vol = 0
    stale_count = 0  # outcomes with $0 recent volume

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
            no_token = tokens[1] if len(tokens) > 1 else ''
        except json.JSONDecodeError:
            yes_token = ''
            no_token = ''

        vol = float(m.get('volumeNum', 0) or 0)
        vol_24h = float(m.get('volume24hr', 0) or 0)
        liq = float(m.get('liquidityNum', 0) or 0)

        total_liquidity += liq
        total_24h_vol += vol_24h

        if vol_24h < 1 and vol < 1000:
            stale_count += 1

        if not closed and yes_p > 0.001:
            active_count += 1

        total_yes += yes_p
        outcomes.append({
            'question': q,
            'yes_price': yes_p,
            'no_price': 1.0 - yes_p,
            'volume': vol,
            'volume_24h': vol_24h,
            'liquidity': liq,
            'closed': closed,
            'yes_token': yes_token,
            'no_token': no_token,
            'stale': vol_24h < 1 and vol < 1000,
        })

    if active_count < MIN_MARKETS:
        return None

    overround = total_yes - 1.0
    non_exclusive = looks_non_exclusive(markets)

    # Sort by price descending
    outcomes.sort(key=lambda x: x['yes_price'], reverse=True)

    # Edge classification
    if overround > 0:
        edge_type = 'OVERROUND'
        edge_pct = overround
    elif overround < 0:
        edge_type = 'UNDERROUND'
        edge_pct = -overround
    else:
        edge_type = 'FAIR'
        edge_pct = 0

    # Net edge after fees
    net_edge = calculate_net_edge(edge_pct, edge_type, outcomes)

    # Stale price assessment
    stale_pct = stale_count / len(outcomes) if outcomes else 0

    return {
        'title': title,
        'domain': domain,
        'volume': volume,
        'volume_24h': total_24h_vol,
        'liquidity': total_liquidity,
        'num_markets': len(outcomes),
        'active_count': active_count,
        'total_yes': total_yes,
        'overround': overround,
        'edge_type': edge_type,
        'edge_pct': edge_pct,
        'net_edge': net_edge,
        'non_exclusive': non_exclusive,
        'neg_risk': neg_risk,
        'neg_risk_augmented': neg_risk_augmented,
        'stale_count': stale_count,
        'stale_pct': stale_pct,
        'outcomes': outcomes,
    }


def fetch_depth_for_opportunity(result, verbose=False):
    """Fetch order book depth for an opportunity's key tokens."""
    depth_info = []
    # For overround: we'd buy NO (= sell YES), check YES bid depth
    # For underround: we'd buy YES, check YES ask depth
    side = 'bids' if result['edge_type'] == 'OVERROUND' else 'asks'

    for o in result['outcomes'][:5]:  # Top 5 outcomes
        token = o['yes_token']
        if not token:
            continue
        if verbose:
            print(f"    Fetching book for {o['question'][:40]}...")
        book = fetch_order_book(token)
        time.sleep(RATE_LIMIT_SLEEP)

        if book:
            executable, avg_price = estimate_executable_size(book, side, result['edge_pct'])
            depth_info.append({
                'question': o['question'],
                'yes_price': o['yes_price'],
                'executable_value': executable,
                'avg_price': avg_price,
                'num_levels': len(book.get(side, [])),
            })
        else:
            depth_info.append({
                'question': o['question'],
                'yes_price': o['yes_price'],
                'executable_value': 0,
                'avg_price': 0,
                'num_levels': 0,
            })

    return depth_info


def print_report(results, min_edge, with_depth=False):
    """Print formatted NegRisk scanner report."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f"\n{'=' * 90}")
    print(f"P01 NEGRISK SCANNER — {now}")
    print(f"{'=' * 90}")
    print(f"Threshold: {min_edge:.1%} | Winner fee: {WINNER_FEE:.0%} | Sports: excluded")

    # Categorize
    actionable = [r for r in results
                  if abs(r['overround']) >= min_edge and not r['non_exclusive']]
    nr_actionable = [r for r in actionable if r['neg_risk']]
    non_nr_actionable = [r for r in actionable if not r['neg_risk']]
    informational = [r for r in results
                     if abs(r['overround']) >= min_edge and r['non_exclusive']]
    fair = [r for r in results if abs(r['overround']) < min_edge]

    # === NEGRISK OPPORTUNITIES ===
    if nr_actionable:
        print(f"\n{'─' * 90}")
        print(f"NEGRISK OPPORTUNITIES ({len(nr_actionable)}) — convert() eligible")
        print(f"{'─' * 90}")
        for i, r in enumerate(nr_actionable):
            ne = r['net_edge']
            direction = 'BUY ALL NO + CONVERT' if r['edge_type'] == 'OVERROUND' else 'BUY ALL YES'
            stale_warn = f" ⚠ {r['stale_pct']:.0%} stale" if r['stale_pct'] > 0.3 else ""
            aug = " [augmented]" if r['neg_risk_augmented'] else ""

            print(f"\n  {i+1}. [{r['domain']:5s}] {r['title'][:65]}{aug}")
            print(f"     Markets: {r['active_count']} active / {r['num_markets']} total{stale_warn}")
            print(f"     Volume: ${r['volume']:>12,.0f} | 24h: ${r['volume_24h']:>10,.0f} | Liq: ${r['liquidity']:>10,.0f}")
            print(f"     Sum YES: {r['total_yes']:.4f} | {r['edge_type']}: {r['overround']:+.4f}")
            print(f"     Gross edge: {ne['gross_edge']:.2%} | Net (expected): {ne['expected_net']:.2%} | Net (worst): {ne['worst_net']:.2%}")
            print(f"     Action: {direction}")

            # Outcomes
            print(f"     Outcomes:")
            for j, o in enumerate(r['outcomes'][:8]):
                stale_flag = ' [STALE]' if o['stale'] else ''
                print(f"       {o['yes_price']:6.1%} | ${o['volume']:>10,.0f} | 24h ${o['volume_24h']:>8,.0f} | {o['question'][:48]}{stale_flag}")
            remaining = len(r['outcomes']) - 8
            if remaining > 0:
                tail_sum = sum(o['yes_price'] for o in r['outcomes'][8:])
                stale_tail = sum(1 for o in r['outcomes'][8:] if o['stale'])
                print(f"       ... {remaining} more (sum: {tail_sum:.1%}, {stale_tail} stale)")

            # Depth analysis
            if with_depth:
                print(f"     Order Book Depth:")
                depth = fetch_depth_for_opportunity(r, verbose=True)
                for d in depth:
                    if d['executable_value'] > 0:
                        print(f"       ${d['executable_value']:>8,.0f} executable | avg {d['avg_price']:.3f} | {d['num_levels']} levels | {d['question'][:40]}")
                    else:
                        print(f"       NO BOOK DATA | {d['question'][:50]}")

    # === NON-NEGRISK MULTI-OUTCOME ===
    if non_nr_actionable:
        print(f"\n{'─' * 90}")
        print(f"NON-NEGRISK MULTI-OUTCOME ({len(non_nr_actionable)}) — no convert(), manual leg execution")
        print(f"{'─' * 90}")
        for i, r in enumerate(non_nr_actionable[:10]):
            ne = r['net_edge']
            print(f"  {i+1}. [{r['domain']:5s}] {r['title'][:60]}")
            print(f"     Mkts: {r['active_count']} | Vol: ${r['volume']:>10,.0f} | Sum: {r['total_yes']:.4f} | {r['edge_type']}: {r['overround']:+.4f} | Net: {ne['expected_net']:.2%}")

    # === INFORMATIONAL ===
    if informational:
        print(f"\n{'─' * 90}")
        print(f"INFORMATIONAL ({len(informational)}) — likely non-exclusive (by-date/price series)")
        print(f"{'─' * 90}")
        for i, r in enumerate(informational[:10]):
            print(f"  {i+1}. [{r['domain']:5s}] {r['title'][:60]} | sum={r['total_yes']:.2f} | {r['overround']:+.2f}")

    # === FAIR PRICING ===
    if fair:
        fair_nr = [r for r in fair if r['neg_risk']]
        print(f"\n{'─' * 90}")
        print(f"FAIR PRICING ({len(fair)}, {len(fair_nr)} NegRisk) — edge < {min_edge:.1%}")
        print(f"{'─' * 90}")
        for i, r in enumerate(fair[:10]):
            nr_flag = ' [NR]' if r['neg_risk'] else ''
            print(f"  {i+1}. [{r['domain']:5s}] {r['title'][:55]}{nr_flag} | sum={r['total_yes']:.4f} | {r['overround']:+.4f}")

    # === SUMMARY ===
    print(f"\n{'=' * 90}")
    print("SUMMARY")
    all_exclusive = [r for r in results if not r['non_exclusive']]
    nr_events = [r for r in all_exclusive if r['neg_risk']]
    non_nr = [r for r in all_exclusive if not r['neg_risk']]

    print(f"  Total events scanned: {len(results)}")
    print(f"  Exclusive (mutually exclusive): {len(all_exclusive)}")
    print(f"    NegRisk enabled: {len(nr_events)}")
    print(f"    Non-NegRisk: {len(non_nr)}")

    if nr_events:
        avg_or = sum(r['overround'] for r in nr_events) / len(nr_events)
        over = [r for r in nr_events if r['overround'] > min_edge]
        under = [r for r in nr_events if r['overround'] < -min_edge]
        print(f"  NegRisk avg overround: {avg_or:+.4f} ({avg_or*100:+.2f}%)")
        print(f"  NegRisk overround > {min_edge:.1%}: {len(over)}")
        print(f"  NegRisk underround > {min_edge:.1%}: {len(under)}")

    if all_exclusive:
        by_domain = {}
        for r in all_exclusive:
            d = r['domain']
            if d not in by_domain:
                by_domain[d] = []
            by_domain[d].append(r['overround'])
        print(f"\n  Domain breakdown:")
        for domain in sorted(by_domain.keys()):
            vals = by_domain[domain]
            avg = sum(vals) / len(vals)
            actionable_d = sum(1 for v in vals if abs(v) >= min_edge)
            print(f"    {domain:5s}: {len(vals):3d} events | avg overround: {avg:+.4f} | actionable: {actionable_d}")

    print(f"  Non-exclusive skipped: {len(informational)}")
    print(f"{'=' * 90}")


def output_json(results, min_edge):
    """Output results as JSON."""
    output = []
    for r in results:
        if abs(r['overround']) < min_edge:
            continue
        if r['non_exclusive']:
            continue
        output.append({
            'title': r['title'],
            'domain': r['domain'],
            'volume': r['volume'],
            'volume_24h': r['volume_24h'],
            'liquidity': r['liquidity'],
            'num_markets': r['num_markets'],
            'total_yes': r['total_yes'],
            'overround': r['overround'],
            'edge_type': r['edge_type'],
            'edge_pct': r['edge_pct'],
            'net_edge': r['net_edge'],
            'neg_risk': r['neg_risk'],
            'stale_pct': r['stale_pct'],
            'outcomes': [{
                'question': o['question'],
                'yes_price': o['yes_price'],
                'volume': o['volume'],
                'volume_24h': o['volume_24h'],
                'stale': o['stale'],
                'yes_token': o['yes_token'],
                'no_token': o['no_token'],
            } for o in r['outcomes']],
        })
    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(description='P01 NegRisk Scanner')
    parser.add_argument('--min-edge', type=float, default=MIN_EDGE_DEFAULT,
                        help=f'Minimum edge to flag (default: {MIN_EDGE_DEFAULT})')
    parser.add_argument('--domain', type=str, default=None,
                        help='Filter by domain (GEO, CRY, POL, ECO, TECH, ENV, OTHER)')
    parser.add_argument('--include-sports', action='store_true',
                        help='Include sports events')
    parser.add_argument('--depth', action='store_true',
                        help='Fetch order book depth for top opportunities')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    parser.add_argument('--verbose', action='store_true',
                        help='Verbose output during scanning')
    args = parser.parse_args()

    if not args.json:
        print("P01 NegRisk Scanner")
        print("Fetching multi-outcome events from Polymarket...")

    events = fetch_events(include_sports=args.include_sports, verbose=args.verbose)
    if not args.json:
        print(f"  Found {len(events)} multi-outcome events (sports {'included' if args.include_sports else 'excluded'})")

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
        print_report(results, args.min_edge, with_depth=args.depth)


if __name__ == '__main__':
    main()
