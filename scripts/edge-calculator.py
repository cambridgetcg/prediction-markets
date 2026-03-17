#!/usr/bin/env python3
"""Edge Calculator — L01

Computes per-account, per-category edge profiles for Polymarket traders.
Edge = outcome - entry_price (positive = beats the market consistently).

A bettor who buys YES at 70c and wins 70% of the time has zero edge.
An insider who buys YES at 20c and wins 90% of the time has massive edge.
That delta is the signal.

Usage:
    python3 scripts/edge-calculator.py                          # Profile whale registry wallets
    python3 scripts/edge-calculator.py --wallet 0x5668...       # Profile specific wallet
    python3 scripts/edge-calculator.py --wallet 0xee50... --wallet 0x5668...  # Multiple wallets
    python3 scripts/edge-calculator.py --min-trades-cat 5       # Lower per-category threshold
    python3 scripts/edge-calculator.py --json                   # JSON to stdout
    python3 scripts/edge-calculator.py --refresh                # Force refresh cached data
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

# ── Configuration ──────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(DATA_DIR, "edge-cache")
WHALE_REGISTRY = os.path.join(DATA_DIR, "whale-registry.json")

GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

MIN_TRADES_PER_CATEGORY = 10
MIN_TOTAL_TRADES = 20

# ── Domain Classification ──────────────────────────────────────────────────────

SPORTS_KEYWORDS = [
    'nba', 'nfl', 'nhl', 'mlb', 'mls', 'ufc', 'wwe', 'pga', 'atp', 'wta',
    'premier league', 'champions league', 'la liga', 'serie a', 'bundesliga',
    'ligue 1', 'eredivisie', 'copa america',
    'super bowl', 'world series', 'stanley cup', 'march madness',
    'formula 1', 'f1 grand', 'nascar', 'indycar',
    'wimbledon', 'us open tennis', 'french open', 'australian open tennis',
    ' vs ', ' vs.', 'moneyline', 'spread', 'o/u ', 'over/under',
    'handicap', 'total points', 'total goals', 'total runs',
    'counter-strike', 'valorant', 'league of legends', 'dota',
    'warriors', 'lakers', 'celtics', 'knicks', 'nets', '76ers', 'bulls',
    'cowboys', 'eagles', 'chiefs', 'bills', 'ravens', '49ers',
    'yankees', 'dodgers', 'mets', 'red sox', 'braves', 'astros',
    'hockey', 'soccer', 'baseball game', 'basketball game', 'football game',
    'tennis match', 'boxing match', 'mma fight',
]

DOMAIN_KEYWORDS = {
    'GEO': ['iran', 'strike on', 'war ', 'invasion', 'ceasefire', 'nato',
            'ukraine', 'russia', 'china', 'taiwan', 'north korea', 'gaza',
            'israel', 'hezbollah', 'hamas', 'conflict', 'troops', 'military op',
            'sanctions', 'annex', 'invade', 'airstrike', 'missile',
            'nuclear weapon', 'yemen', 'houthi', 'south china sea', 'syria',
            'maduro', 'venezuela', 'coup', 'regime change', 'martial law'],
    'POL': ['trump', 'biden', 'president', 'election', 'congress', 'senate',
            'governor', 'mayor', 'democrat', 'republican', 'gop ', 'dnc', 'rnc',
            'impeach', 'nomination', 'primary', 'electoral', 'cabinet',
            'speaker of the house', 'vance', 'desantis', 'newsom', 'haley',
            'executive order', 'pardon', 'state of the union', 'sotu',
            'approval rating', 'midterm', 'ballot', 'swing state',
            'running mate', 'vice president', 'white house'],
    'ECO': ['fed ', 'federal reserve', 'interest rate', 'rate cut', 'rate hike',
            'inflation', 'cpi ', 'gdp ', 'recession', 'unemployment',
            'treasury', 'yield curve', 'fomc', 'powell', 'ecb ', 'lagarde',
            'tariff', 'trade war', 'debt ceiling', 'government shutdown',
            'quantitative', 'jobs report', 'nonfarm', 'consumer spending'],
    'FIN': ['s&p 500', 'dow jones', 'nasdaq', 'stock market',
            'ipo ', 'earnings', 'market cap', 'nyse',
            'commodity', 'gold price', 'oil price', 'silver price',
            'hedge fund', 'berkshire', 'tesla stock', 'apple stock'],
    'CRY': ['bitcoin', 'btc ', 'ethereum', 'eth ', 'solana', 'sol ',
            'crypto', 'blockchain', 'defi', 'nft ', 'token launch',
            'binance', 'coinbase', 'altcoin', 'memecoin', 'doge',
            'stablecoin', 'layer 2'],
    'TEC': ['ai ', 'artificial intelligence', 'openai', 'chatgpt', 'google',
            'apple', 'microsoft', 'meta ', 'nvidia', 'semiconductor', 'chip',
            'quantum comput', 'robot', 'spacex', 'launch', 'mars ',
            'starship', 'neuralink', 'agi', 'gpt-', 'gemini ai', 'llm',
            'machine learning', 'autonomous', 'self-driving', 'tiktok ban',
            'year in search'],
    'SCI': ['vaccine', 'pandemic', 'virus', 'covid', 'bird flu', 'h5n1',
            'disease', 'fda approv', 'drug trial', 'climate change',
            'earthquake', 'hurricane', 'wildfire', 'species', 'extinction',
            'nobel prize', 'scientific'],
    'LAW': ['supreme court', 'lawsuit', 'indictment', 'trial', 'verdict',
            'guilty', 'conviction', 'sentenced', 'regulation',
            'sec ', 'cftc', 'doj ', 'fbi ', 'arrest', 'extradite',
            'constitutional', 'amendment', 'gun law', 'antitrust',
            'class action', 'settlement'],
    'ENV': ['carbon', 'emission', 'renewable', 'solar energy',
            'wind energy', 'ev ', 'electric vehicle', 'paris agreement',
            'epa ', 'pollution', 'deforestation', 'glacier',
            'temperature record', 'sea level'],
}


def is_sports(text):
    """Check if market question is sports-related."""
    t = text.lower()
    return any(kw in t for kw in SPORTS_KEYWORDS)


def classify_domain(text):
    """Classify market question into domain category."""
    if not text:
        return 'OTHER'
    if is_sports(text):
        return 'SOC'
    t = text.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in t:
                return domain
    return 'OTHER'


# ── API Helpers ────────────────────────────────────────────────────────────────

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
    except (subprocess.TimeoutExpired, json.JSONDecodeError, TypeError):
        return None


def fetch_resolved_markets(max_events=2000, cache_file=None):
    """
    Build conditionId → resolution lookup from closed events.

    Returns dict keyed by conditionId (lowercase) and "token:<clobTokenId>".
    Each value: {question, outcome_prices, outcomes, domain, volume, closed_time, clob_tokens}
    """
    if cache_file and os.path.exists(cache_file):
        cache_age = time.time() - os.path.getmtime(cache_file)
        if cache_age < 86400:
            print(f"  Loading cached resolved markets ({int(cache_age / 3600)}h old)",
                  file=sys.stderr)
            with open(cache_file) as f:
                return json.load(f)

    print("  Fetching resolved markets from Gamma API...", file=sys.stderr)
    resolved = {}
    n_condition = 0

    for offset in range(0, max_events, 100):
        url = (f"{GAMMA_BASE}/events?limit=100&closed=true"
               f"&order=volume&ascending=false&offset={offset}")
        data = curl_json(url)
        if not data:
            break

        for event in data:
            for m in event.get('markets', []):
                cid = m.get('conditionId', '')
                if not cid:
                    continue

                # Parse outcome prices
                try:
                    prices_raw = json.loads(m.get('outcomePrices', '[]'))
                    prices = [float(p) for p in prices_raw]
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

                # Only include fully resolved markets
                if not prices or max(prices) < 0.99:
                    continue

                try:
                    outcomes = json.loads(m.get('outcomes', '[]'))
                except json.JSONDecodeError:
                    outcomes = ['Yes', 'No']

                try:
                    tokens = json.loads(m.get('clobTokenIds', '[]'))
                except json.JSONDecodeError:
                    tokens = []

                question = m.get('question', '') or event.get('title', '')
                entry = {
                    "question": question,
                    "outcome_prices": prices,
                    "outcomes": outcomes,
                    "domain": classify_domain(question),
                    "volume": float(m.get('volumeNum', 0) or 0),
                    "closed_time": m.get('closedTime', ''),
                    "clob_tokens": tokens,
                }

                resolved[cid.lower()] = entry
                n_condition += 1

                # Also index by CLOB token IDs for fallback matching
                for tok in tokens:
                    if tok:
                        resolved[f"token:{tok}"] = entry

        print(f"  ... {n_condition} resolved markets (offset {offset})",
              file=sys.stderr)

        if len(data) < 100:
            break
        time.sleep(0.25)

    print(f"  Total: {n_condition} resolved markets indexed", file=sys.stderr)

    if cache_file:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump(resolved, f)

    return resolved


def fetch_wallet_trades(address, max_pages=20):
    """
    Fetch all trades for a wallet from data-api.
    Returns list of trade dicts.
    """
    trades = []
    seen_hashes = set()

    for page in range(max_pages):
        offset = page * 1000
        url = f"{DATA_API}/trades?user={address}&limit=1000&offset={offset}"
        data = curl_json(url)
        if not data or not isinstance(data, list):
            break  # API returns dict with error at max offset (3000)

        for t in data:
            if not isinstance(t, dict):
                continue
            tx_hash = t.get('transactionHash', '')
            if tx_hash in seen_hashes:
                continue
            seen_hashes.add(tx_hash)

            trades.append({
                'side': t.get('side', ''),
                'price': float(t.get('price', 0) or 0),
                'size': float(t.get('size', 0) or 0),
                'condition_id': (t.get('conditionId', '') or '').lower(),
                'asset': t.get('asset', ''),
                'outcome_index': int(t.get('outcomeIndex', -1) if t.get('outcomeIndex') is not None else -1),
                'outcome': t.get('outcome', ''),
                'title': t.get('title', ''),
                'timestamp': int(t.get('timestamp', 0) or 0),
                'tx_hash': tx_hash,
            })

        if len(data) < 1000:
            break
        time.sleep(0.25)

    return trades


# ── Statistics ─────────────────────────────────────────────────────────────────

def compute_t_stat(values):
    """One-sample t-statistic testing H0: mean = 0."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else 1e-8
    return mean / (std / math.sqrt(n))


def approx_p_value(t_val, n):
    """
    Approximate two-tailed p-value using normal CDF approximation.
    Accurate for n >= 20; slightly conservative for smaller n.
    Uses Abramowitz & Stegun 26.2.17.
    """
    z = abs(t_val)
    if z > 8:
        return 1e-10
    if z < 0.001:
        return 1.0
    t = 1.0 / (1.0 + 0.2316419 * z)
    d = 0.3989422804014327  # 1/sqrt(2*pi)
    p_one_tail = d * math.exp(-z * z / 2.0) * (
        0.319381530 * t
        - 0.356563782 * t ** 2
        + 1.781477937 * t ** 3
        - 1.821255978 * t ** 4
        + 1.330274429 * t ** 5
    )
    return max(2.0 * p_one_tail, 1e-10)


# ── Edge Computation ───────────────────────────────────────────────────────────

def compute_edge_profile(wallet_addr, alias, trades, resolved, min_cat, min_total):
    """
    Compute per-category edge profile for a wallet.
    Only considers BUY trades on resolved markets.
    Edge_i = resolved_value (1 if won, 0 if lost) - entry_price
    """
    cat_edges = defaultdict(list)
    matched = 0
    unmatched = 0

    for t in trades:
        if t['side'] != 'BUY':
            continue
        if t['price'] <= 0.001 or t['price'] >= 0.999:
            continue
        if t['outcome_index'] < 0:
            continue

        # Match to resolved market: try conditionId, then CLOB token
        market = None
        cid = t['condition_id']
        if cid and cid in resolved:
            market = resolved[cid]
        elif t['asset'] and f"token:{t['asset']}" in resolved:
            market = resolved[f"token:{t['asset']}"]

        if not market:
            unmatched += 1
            continue

        prices = market['outcome_prices']
        if t['outcome_index'] >= len(prices):
            unmatched += 1
            continue

        resolved_value = prices[t['outcome_index']]
        edge = resolved_value - t['price']
        domain = market['domain']

        cat_edges[domain].append({
            'edge': edge,
            'size': t['size'],
            'price': t['price'],
            'won': resolved_value > 0.5,
            'title': t['title'],
            'timestamp': t['timestamp'],
        })
        matched += 1

    if matched < min_total:
        return None

    # Aggregate by category
    categories = {}
    all_edges = []

    for domain, edges in cat_edges.items():
        if domain == 'OTHER':
            continue

        edge_values = [e['edge'] for e in edges]
        all_edges.extend(edge_values)
        n = len(edge_values)

        if n < min_cat:
            continue

        mean_edge = sum(edge_values) / n
        variance = sum((x - mean_edge) ** 2 for x in edge_values) / (n - 1) if n > 1 else 0
        std_dev = math.sqrt(variance)

        total_wagered = sum(e['size'] * e['price'] for e in edges)
        net_profit = sum(e['size'] * e['edge'] for e in edges)
        roi = net_profit / total_wagered if total_wagered > 0 else 0

        t_stat = compute_t_stat(edge_values)
        p_val = approx_p_value(t_stat, n)

        categories[domain] = {
            "n": n,
            "mean_edge": round(mean_edge, 4),
            "roi": round(roi, 4),
            "std_dev": round(std_dev, 4),
            "t_stat": round(t_stat, 3),
            "p_value": round(p_val, 4),
            "significant": p_val < 0.05,
            "total_wagered_usd": round(total_wagered, 2),
            "net_profit_usd": round(net_profit, 2),
            "win_rate": round(sum(1 for e in edges if e['won']) / n, 3),
        }

    if not categories:
        return None

    # Overall stats
    overall_mean = sum(all_edges) / len(all_edges) if all_edges else 0
    total_profit = sum(c['net_profit_usd'] for c in categories.values())
    total_wagered = sum(c['total_wagered_usd'] for c in categories.values())

    # Dominant category: prefer significant, then highest |mean_edge|
    sig_cats = {k: v for k, v in categories.items() if v['significant']}
    if sig_cats:
        dominant = max(sig_cats, key=lambda k: abs(sig_cats[k]['mean_edge']))
    else:
        dominant = max(categories, key=lambda k: abs(categories[k]['mean_edge']))

    # Last active
    timestamps = [t['timestamp'] for t in trades if t['timestamp'] > 0]
    last_active = max(timestamps) if timestamps else 0
    last_active_str = (datetime.fromtimestamp(last_active, tz=timezone.utc).isoformat()
                       if last_active else None)

    sig_count = sum(1 for c in categories.values() if c['significant'])

    return {
        "wallet": wallet_addr,
        "alias": alias,
        "total_trades": len(trades),
        "buy_trades": sum(1 for t in trades if t['side'] == 'BUY'),
        "resolved_trades": matched,
        "unmatched_trades": unmatched,
        "total_profit_usd": round(total_profit, 2),
        "total_wagered_usd": round(total_wagered, 2),
        "overall_mean_edge": round(overall_mean, 4),
        "overall_roi": round(total_profit / total_wagered, 4) if total_wagered > 0 else 0,
        "categories": categories,
        "dominant_category": dominant,
        "significant_categories": sig_count,
        "edge_type": ("localized" if 0 < sig_count <= 2
                      else ("broad" if sig_count >= 3 else "none")),
        "insider_score": None,  # Computed in L02
        "last_active": last_active_str,
    }


# ── Output ─────────────────────────────────────────────────────────────────────

def print_profile_summary(profiles):
    """Print human-readable summary table."""
    print()
    print("=" * 135)
    print("L01 EDGE CALCULATOR — Per-Account, Per-Category Edge Profiles")
    print("=" * 135)

    if not profiles:
        print("\nNo qualifying profiles found (try --min-trades-cat 3 or --min-total 5).")
        return

    # Sort by overall mean edge descending
    ranked = sorted(profiles, key=lambda p: p['overall_mean_edge'], reverse=True)

    print(f"\n{'#':>3} {'Alias':<20} {'Wallet':<14} {'Buys':>5} {'Resolved':>8} "
          f"{'Edge':>7} {'ROI':>8} {'Profit':>12} {'Dom':>5} {'Sig':>4} {'Type':<10}")
    print("-" * 135)

    for i, p in enumerate(ranked, 1):
        alias = (p['alias'] or p['wallet'][:10])[:19]
        wallet_short = p['wallet'][:12] + '..'
        profit_str = f"${p['total_profit_usd']:>10,.0f}"
        print(f"{i:>3} {alias:<20} {wallet_short:<14} {p['buy_trades']:>5} "
              f"{p['resolved_trades']:>8} "
              f"{p['overall_mean_edge']:>+7.3f} {p['overall_roi']:>+8.1%} "
              f"{profit_str:>12} {p['dominant_category']:>5} "
              f"{p['significant_categories']:>4} {p['edge_type']:<10}")

    # Category breakdown for profiles with significant edges
    print(f"\n{'─' * 135}")
    print("CATEGORY BREAKDOWN (significant edges marked with *)")
    print(f"{'─' * 135}")

    for p in ranked:
        if not p['categories']:
            continue

        alias = p['alias'] or p['wallet'][:12]
        print(f"\n  {alias}:")
        print(f"    {'Cat':<6} {'N':>5} {'Edge':>8} {'ROI':>8} {'Win%':>6} "
              f"{'t-stat':>7} {'p-val':>7} {'Wagered':>12} {'Profit':>12}")

        for cat in sorted(p['categories'],
                          key=lambda k: p['categories'][k]['mean_edge'],
                          reverse=True):
            c = p['categories'][cat]
            sig = "*" if c['significant'] else " "
            print(f"  {sig} {cat:<5} {c['n']:>5} {c['mean_edge']:>+8.4f} "
                  f"{c['roi']:>+8.1%} {c['win_rate']:>5.0%} "
                  f"{c['t_stat']:>7.2f} {c['p_value']:>7.4f} "
                  f"${c['total_wagered_usd']:>10,.0f} "
                  f"${c['net_profit_usd']:>10,.0f}")

    # Population summary
    print(f"\n{'=' * 135}")
    print("POPULATION SUMMARY")
    print(f"{'=' * 135}")

    n_total = len(profiles)
    n_sig = sum(1 for p in profiles if p['significant_categories'] > 0)
    n_local = sum(1 for p in profiles if p['edge_type'] == 'localized')
    n_broad = sum(1 for p in profiles if p['edge_type'] == 'broad')

    print(f"  Accounts profiled:               {n_total}")
    print(f"  With significant edge:           {n_sig} ({n_sig/n_total*100:.0f}%)")
    print(f"  Localized edge (1-2 categories): {n_local} — possible domain specialists/insiders")
    print(f"  Broad edge (3+ categories):      {n_broad} — possible superforecasters")

    all_cats = set()
    for p in profiles:
        all_cats.update(p['categories'].keys())

    print(f"\n  Top edge by category:")
    for cat in sorted(all_cats):
        cat_entries = [(p, p['categories'][cat])
                       for p in profiles
                       if cat in p['categories'] and p['categories'][cat]['significant']]
        if not cat_entries:
            continue
        cat_entries.sort(key=lambda x: x[1]['mean_edge'], reverse=True)
        top_p, top_c = cat_entries[0]
        alias = top_p['alias'] or top_p['wallet'][:12]
        print(f"    {cat}: {alias} "
              f"(edge {top_c['mean_edge']:+.3f}, n={top_c['n']}, "
              f"ROI {top_c['roi']:+.1%})")


def write_outputs(profiles):
    """Write JSON and CSV output files."""
    all_cats = set()
    for p in profiles:
        all_cats.update(p['categories'].keys())
    cats = sorted(all_cats)

    # edge-profiles.json
    profiles_path = os.path.join(DATA_DIR, "edge-profiles.json")
    with open(profiles_path, 'w') as f:
        json.dump(profiles, f, indent=2)
    print(f"\n  Wrote: {profiles_path}", file=sys.stderr)

    # edge-summary.json
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_accounts_analysed": len(profiles),
        "accounts_above_significance": sum(
            1 for p in profiles if p['significant_categories'] > 0),
        "accounts_with_localised_edge": sum(
            1 for p in profiles if p['edge_type'] == 'localized'),
        "accounts_with_broad_edge": sum(
            1 for p in profiles if p['edge_type'] == 'broad'),
        "top_10_by_overall_edge": [
            {"wallet": p['wallet'], "alias": p['alias'],
             "overall_mean_edge": p['overall_mean_edge'],
             "dominant_category": p['dominant_category']}
            for p in sorted(profiles,
                            key=lambda x: x['overall_mean_edge'],
                            reverse=True)[:10]
        ],
        "top_by_category": {},
    }
    for cat in cats:
        cat_profiles = [p for p in profiles if cat in p['categories']]
        cat_profiles.sort(
            key=lambda p: p['categories'][cat]['mean_edge'], reverse=True)
        summary["top_by_category"][cat] = [
            {"wallet": p['wallet'], "alias": p['alias'],
             "mean_edge": p['categories'][cat]['mean_edge'],
             "n": p['categories'][cat]['n'],
             "significant": p['categories'][cat]['significant']}
            for p in cat_profiles[:10]
        ]

    summary_path = os.path.join(DATA_DIR, "edge-summary.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  Wrote: {summary_path}", file=sys.stderr)

    # edge-profiles.csv
    csv_path = os.path.join(DATA_DIR, "edge-profiles.csv")
    with open(csv_path, 'w') as f:
        header = ("wallet,alias,total_trades,buy_trades,resolved_trades,"
                  "overall_mean_edge,overall_roi,total_profit_usd,"
                  "dominant_category,significant_categories,edge_type,last_active")
        for cat in cats:
            header += f",{cat}_n,{cat}_edge,{cat}_roi,{cat}_pvalue,{cat}_sig"
        f.write(header + "\n")

        for p in sorted(profiles,
                        key=lambda x: x['overall_mean_edge'], reverse=True):
            alias_safe = (p['alias'] or '').replace(',', ';')
            row = (f"{p['wallet']},{alias_safe},{p['total_trades']},"
                   f"{p['buy_trades']},{p['resolved_trades']},"
                   f"{p['overall_mean_edge']},{p['overall_roi']},"
                   f"{p['total_profit_usd']},"
                   f"{p['dominant_category']},{p['significant_categories']},"
                   f"{p['edge_type']},{p['last_active'] or ''}")
            for cat in cats:
                if cat in p['categories']:
                    c = p['categories'][cat]
                    row += (f",{c['n']},{c['mean_edge']},{c['roi']},"
                            f"{c['p_value']},{c['significant']}")
                else:
                    row += ",,,,,"
            f.write(row + "\n")

    print(f"  Wrote: {csv_path}", file=sys.stderr)


def run_validation(profiles):
    """Check known wallets surface correctly."""
    print(f"\n{'=' * 135}", file=sys.stderr)
    print("VALIDATION CHECKS", file=sys.stderr)
    print(f"{'=' * 135}", file=sys.stderr)

    checks = 0
    passes = 0

    for p in profiles:
        # AlphaRaccoon: should show TEC edge
        if p['alias'] == 'AlphaRaccoon':
            checks += 1
            tec = p['categories'].get('TEC', {})
            if tec and tec.get('significant'):
                print(f"  PASS  AlphaRaccoon: TEC edge detected "
                      f"(edge={tec['mean_edge']:+.3f}, p={tec['p_value']:.4f}, "
                      f"n={tec['n']})", file=sys.stderr)
                passes += 1
            elif tec:
                print(f"  WEAK  AlphaRaccoon: TEC found but not significant "
                      f"(edge={tec['mean_edge']:+.3f}, p={tec['p_value']:.4f}, "
                      f"n={tec['n']})", file=sys.stderr)
            else:
                print(f"  FAIL  AlphaRaccoon: no TEC trades in data window",
                      file=sys.stderr)

        # Theo4: should show POL edge
        if p['alias'] == 'Theo4':
            checks += 1
            pol = p['categories'].get('POL', {})
            if pol and pol.get('significant'):
                print(f"  PASS  Theo4: POL edge detected "
                      f"(edge={pol['mean_edge']:+.3f}, p={pol['p_value']:.4f}, "
                      f"n={pol['n']})", file=sys.stderr)
                passes += 1
            elif pol:
                print(f"  WEAK  Theo4: POL found but not significant "
                      f"(edge={pol['mean_edge']:+.3f}, n={pol['n']})",
                      file=sys.stderr)
            else:
                print(f"  FAIL  Theo4: no POL trades in data window",
                      file=sys.stderr)

        # Domer: should show broad edge
        if p['alias'] == 'Domer / ImJustKen':
            checks += 1
            print(f"  INFO  Domer: dominant={p['dominant_category']}, "
                  f"type={p['edge_type']}, "
                  f"sig categories={p['significant_categories']}, "
                  f"categories={list(p['categories'].keys())}",
                  file=sys.stderr)
            if p['edge_type'] in ('broad', 'localized'):
                passes += 1

        # scottilicious: should show POL edge with high win rate
        if p['alias'] == 'scottilicious':
            checks += 1
            pol = p['categories'].get('POL', {})
            if pol:
                print(f"  INFO  scottilicious: POL win_rate={pol['win_rate']:.0%}, "
                      f"edge={pol['mean_edge']:+.3f}, n={pol['n']}",
                      file=sys.stderr)
                if pol.get('win_rate', 0) > 0.7:
                    passes += 1
            else:
                print(f"  FAIL  scottilicious: no POL data", file=sys.stderr)

        # ricosuave666: should show GEO edge
        if p['alias'] == 'ricosuave666':
            checks += 1
            geo = p['categories'].get('GEO', {})
            if geo:
                print(f"  INFO  ricosuave666: GEO win_rate={geo['win_rate']:.0%}, "
                      f"edge={geo['mean_edge']:+.3f}, n={geo['n']}",
                      file=sys.stderr)
                if geo.get('win_rate', 0) > 0.8:
                    passes += 1
            else:
                print(f"  FAIL  ricosuave666: no GEO data", file=sys.stderr)

    if checks > 0:
        print(f"\n  Validation: {passes}/{checks} checks passed", file=sys.stderr)
    else:
        print(f"\n  No validation targets found in profiles", file=sys.stderr)

    # Note about single-trade insiders
    print(f"\n  Note: Single-trade insiders (Venezuela/Maduro pattern) are correctly",
          file=sys.stderr)
    print(f"  excluded by the min-trades filter. L01 catches systematic insiders;",
          file=sys.stderr)
    print(f"  P07 covers one-time front-runners.\n", file=sys.stderr)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='L01 Edge Calculator — per-account, per-category edge profiling')
    parser.add_argument('--wallet', '-w', action='append',
                        help='Wallet address to profile (repeatable)')
    parser.add_argument('--min-trades-cat', type=int,
                        default=MIN_TRADES_PER_CATEGORY,
                        help=f'Min trades per category (default: {MIN_TRADES_PER_CATEGORY})')
    parser.add_argument('--min-total', type=int, default=MIN_TOTAL_TRADES,
                        help=f'Min total resolved trades (default: {MIN_TOTAL_TRADES})')
    parser.add_argument('--max-events', type=int, default=2000,
                        help='Max resolved events to fetch (default: 2000)')
    parser.add_argument('--json', action='store_true',
                        help='Output JSON to stdout')
    parser.add_argument('--refresh', action='store_true',
                        help='Force refresh cached data')
    args = parser.parse_args()

    os.makedirs(CACHE_DIR, exist_ok=True)

    # Step 1: Build resolved market index
    print("\n[1/3] Building resolved market index...", file=sys.stderr)
    cache_file = os.path.join(CACHE_DIR, "resolved-markets.json")
    if args.refresh and os.path.exists(cache_file):
        os.remove(cache_file)
    resolved = fetch_resolved_markets(args.max_events, cache_file)

    n_resolved = len([k for k in resolved if not k.startswith('token:')])
    if n_resolved == 0:
        print("  ERROR: No resolved markets found. Check network.", file=sys.stderr)
        sys.exit(1)

    # Step 2: Determine wallets to profile
    wallets = []
    if args.wallet:
        for addr in args.wallet:
            wallets.append((addr.lower(), None))
    else:
        if os.path.exists(WHALE_REGISTRY):
            with open(WHALE_REGISTRY) as f:
                registry = json.load(f)
            for entry in registry:
                wallets.append((entry['wallet'].lower(), entry.get('alias')))
            print(f"  Loaded {len(wallets)} wallets from whale registry",
                  file=sys.stderr)
        else:
            print(f"  ERROR: {WHALE_REGISTRY} not found. "
                  f"Use --wallet to specify addresses.", file=sys.stderr)
            sys.exit(1)

    # Step 3: Profile each wallet
    print(f"\n[2/3] Profiling {len(wallets)} wallets...", file=sys.stderr)
    profiles = []

    for i, (addr, alias) in enumerate(wallets, 1):
        label = alias or addr[:12]
        print(f"  [{i}/{len(wallets)}] {label}... ", file=sys.stderr, end='',
              flush=True)

        # Check trade cache
        trade_cache = os.path.join(CACHE_DIR, f"trades-{addr[:16]}.json")
        if not args.refresh and os.path.exists(trade_cache):
            cache_age = time.time() - os.path.getmtime(trade_cache)
            if cache_age < 86400:
                with open(trade_cache) as f:
                    trades = json.load(f)
                print(f"cached ({len(trades)} trades)", file=sys.stderr)
            else:
                trades = fetch_wallet_trades(addr)
                with open(trade_cache, 'w') as f:
                    json.dump(trades, f)
                print(f"{len(trades)} trades fetched", file=sys.stderr)
        else:
            trades = fetch_wallet_trades(addr)
            with open(trade_cache, 'w') as f:
                json.dump(trades, f)
            print(f"{len(trades)} trades fetched", file=sys.stderr)

        if not trades:
            continue

        profile = compute_edge_profile(
            addr, alias, trades, resolved,
            args.min_trades_cat, args.min_total
        )

        if profile:
            profiles.append(profile)

    # Step 4: Output
    print(f"\n[3/3] Generating output ({len(profiles)} qualifying profiles)...",
          file=sys.stderr)

    if args.json:
        print(json.dumps(profiles, indent=2))
    else:
        print_profile_summary(profiles)

    write_outputs(profiles)
    run_validation(profiles)


if __name__ == '__main__':
    main()
