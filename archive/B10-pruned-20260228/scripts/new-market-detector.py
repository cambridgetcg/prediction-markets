#!/usr/bin/env python3
"""
New Market Detector — Screens Polymarket for recently created markets.

Identifies new markets in our research domains during the "discovery window"
(low volume, initial pricing) where first-mover edge exists.

Usage:
    python3 scripts/new-market-detector.py                    # Last 12 hours
    python3 scripts/new-market-detector.py --hours 4          # Last 4 hours
    python3 scripts/new-market-detector.py --hours 720        # Last 30 days
    python3 scripts/new-market-detector.py --domain GEO       # Filter by domain
    python3 scripts/new-market-detector.py --all              # Include all domains
    python3 scripts/new-market-detector.py --json             # JSON output
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

# --- Configuration ---

LOOKBACK_HOURS = 12  # Default: last 12 hours

# Volume thresholds for discovery window assessment
VOLUME_TIERS = {
    'discovery': 5000,       # <$5K = deep discovery (highest mispricing probability)
    'early': 10000,          # $5-10K = early price formation
    'forming': 50000,        # $10-50K = price forming (moderate edge)
    'mature': float('inf'),  # >$50K = mature (edge likely gone)
}

# Sizing rules per volume tier
SIZING_RULES = {
    'discovery': '$50 max',
    'early': '$75 max',
    'forming': '$125 max',
    'mature': 'Standard sizing',
}

# Domain classification keywords (consistent with spike-detector.py)
# Sports detection — applied BEFORE domain classification
SPORTS_KEYWORDS = [
    # Team sports
    ' vs ', ' vs.', 'nba', 'nfl', 'nhl', 'mlb', 'ncaab', 'ncaaf',
    'premier league', 'la liga', 'serie a', 'bundesliga', 'ligue 1',
    'champions league', 'europa league', 'ufc', 'pga tour', 'atp', 'wta',
    'ahl:', 'echl:', 'ushl:', 'ohl:', 'whl:',
    # Specific sports patterns
    'moneyline', 'spread', 'over/under', 'o/u ', 'handicap',
    'top 5', 'top 10', 'top 20', 'match winner', 'set winner',
    'bachelorette', 'bachelor', 'season winner',
    # Sports-specific team words that cause false positives
    'warriors vs', 'senators vs', 'raiders vs', 'eagles vs', 'bulls vs',
    'magic vs', 'pistons vs', 'lakers vs', 'clippers vs', 'celtics vs',
    'rangers vs', 'maple leafs', 'blue jays', 'wildcats vs', 'bulldogs vs',
    'hornets vs', 'bison vs', 'bears vs', 'tigers vs', 'hawks vs',
    'comets vs', 'purple eagles', 'blue raiders', 'blue hens',
    'rugby', 'cricket', 't20 series', 'super rugby', 'top 14:',
    'copa ', 'chile open', 'antalya:', 'roland garros', 'wimbledon',
    'australian open', 'us open:', 'conference winner:',
    'hot 100', 'billboard', 'all-in podcast',
]

DOMAIN_KEYWORDS = {
    'GEO': ['iran', 'strike', 'war', 'invasion', 'ceasefire', 'nato', 'ukraine',
             'russia', 'china', 'taiwan', 'israel', 'lebanon', 'khamenei',
             'regime', 'leader', 'venezuela', 'greenland', 'annex', 'invade',
             'north korea', 'military', 'troops', 'airstrike', 'missile',
             'nuclear', 'maduro', 'sanctions', 'embassy', 'territory',
             'cartel', 'rubio visit'],
    'POL': ['president', 'nomination', 'democrat', 'republican', 'trump',
             'election', 'nominate', 'congress', 'senate primary',
             'governor', 'speaker', 'vance', 'desantis', 'newsom',
             'shapiro', 'haley', 'primary', 'electoral', 'impeach',
             'cabinet', 'sotu', 'approval rating', 'pardon',
             'executive order', 'lagarde', 'ecb president',
             'testimony', 'epstein', 'become law', 'bill pass',
             'by-election'],
    'ECO': ['fed ', 'interest rate', 'bps', 'gdp', 'inflation', 'cpi',
             'unemployment', 'revenue', 'treasury', 'tariff', 'recession',
             'fomc', 'rate cut', 'rate hike', 'jobs report', 'nonfarm',
             'stablecoin', 'debt ceiling', 'meta launch', 'earnings'],
    'TEC': ['ai model', 'anthropic', 'openai', 'chatgpt', 'claude',
             'gemini', 'gpt', 'deepseek', 'llama', 'benchmark', 'agi',
             'chatbot arena', 'lmsys', 'best model', 'ai safety', 'compute',
             'google stock', 'googl', 'nvidia', 'tsla stock'],
    'LAW': ['supreme court', 'scotus', 'ruling', 'lawsuit', 'legal',
             'regulation', 'doj', 'fbi', 'indictment', 'conviction',
             'appeal', 'attorney general', 'cftc', 'sec ', 'war powers'],
    'CRY': ['bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol', 'xrp',
             'crypto', 'token', 'fdv', 'launch', 'dip to', 'reach $',
             'memecoin', 'altcoin', 'defi', 'nft', 'halving'],
    'ENV': ['earthquake', 'hurricane', 'snow', 'temperature', 'wildfire',
             'climate', 'storm', 'tornado', 'flood', 'volcano'],
    'SCI': ['space', 'nasa', 'spacex', 'moon', 'mars', 'vaccine', 'pandemic',
             'virus', 'research', 'nobel'],
    'POP': ['oscar', 'grammy', 'super bowl', 'celebrity', 'tiktok',
             'youtube', 'twitter', 'elon musk'],
}

# Domains we have deep research for (first-mover advantage)
STRONG_DOMAINS = {'GEO', 'POL', 'ECO', 'TEC', 'LAW'}
MODERATE_DOMAINS = {'CRY'}

# --- Helpers ---

def is_sports_market(text):
    """Detect sports/entertainment markets that pollute domain classification."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in SPORTS_KEYWORDS)

def classify_domain(text):
    """Classify market text into domain. Returns 'SPORTS' for sports markets."""
    text_lower = text.lower()
    if is_sports_market(text_lower):
        return 'SPORTS'
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[domain] = score
    if not scores:
        return 'OTHER'
    return max(scores, key=scores.get)

def classify_volume_tier(volume):
    """Classify market volume into discovery tier."""
    if volume < VOLUME_TIERS['discovery']:
        return 'discovery'
    elif volume < VOLUME_TIERS['early']:
        return 'early'
    elif volume < VOLUME_TIERS['forming']:
        return 'forming'
    else:
        return 'mature'

def parse_iso_date(date_str):
    """Parse ISO date string to datetime."""
    if not date_str:
        return None
    # Handle various formats
    date_str = date_str.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None

def hours_ago(dt):
    """How many hours ago was this datetime."""
    if not dt:
        return float('inf')
    now = datetime.now(timezone.utc)
    delta = now - dt
    return delta.total_seconds() / 3600

def format_price(price_str):
    """Parse and format outcome prices."""
    try:
        prices = json.loads(price_str)
        if len(prices) >= 2:
            yes_pct = float(prices[0]) * 100
            return f"{yes_pct:.0f}%"
    except (json.JSONDecodeError, TypeError, IndexError, ValueError):
        pass
    return "?"

def format_volume(vol):
    """Format volume as human-readable."""
    try:
        v = float(vol)
    except (TypeError, ValueError):
        return "$0"
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    elif v >= 1_000:
        return f"${v/1_000:.0f}K"
    else:
        return f"${v:.0f}"

def format_hours(h):
    """Format hours as human-readable duration."""
    if h < 1:
        return f"{h*60:.0f}m ago"
    elif h < 24:
        return f"{h:.1f}h ago"
    elif h < 168:
        return f"{h/24:.1f}d ago"
    else:
        return f"{h/168:.1f}w ago"

def fetch_events(offset=0, limit=100):
    """Fetch events from Gamma API sorted by creation date."""
    url = (
        f"https://gamma-api.polymarket.com/events"
        f"?limit={limit}&offset={offset}"
        f"&order=createdAt&ascending=false"
        f"&active=true&closed=false"
    )
    result = subprocess.run(
        ['curl', '-s', '-H', 'User-Agent: prediction-markets-detector/1.0', url],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

def is_automated_series(event):
    """Detect automated series markets (crypto up/down, sports spreads)."""
    slug = (event.get('slug') or '').lower()
    title = (event.get('title') or '').lower()
    # Common automated patterns
    auto_patterns = [
        'updown', 'up-down', 'price-up', 'price-down',
        '(bo3)', '(bo5)', 'spread', 'over-under', 'total-points',
        'winner-of', 'moneyline',
    ]
    for p in auto_patterns:
        if p in slug or p in title:
            return True
    # High-frequency crypto price markets
    if any(kw in title for kw in ['dip to', 'drop below', 'rise above', 'close above', 'close below']):
        markets = event.get('markets', [])
        if markets and len(markets) == 1:
            return True
    return False

# --- Main ---

def detect_new_markets(lookback_hours, domain_filter=None, include_all=False):
    """Detect new markets within lookback window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    all_new = []
    offset = 0
    pages = 0
    max_pages = 30  # Up to 3000 events for 30-day lookback

    while pages < max_pages:
        events = fetch_events(offset=offset, limit=100)
        if not events:
            break

        found_old = False
        for event in events:
            created = parse_iso_date(event.get('createdAt'))
            if not created or created < cutoff:
                found_old = True
                continue

            # Skip automated series unless --all
            if not include_all and is_automated_series(event):
                continue

            title = event.get('title', '')
            markets = event.get('markets', [])

            # Aggregate volume across sub-markets
            total_volume = 0
            total_liquidity = 0
            sub_market_info = []

            for m in markets:
                vol = float(m.get('volumeNum', 0) or 0)
                liq = float(m.get('liquidityNum', 0) or 0)
                total_volume += vol
                total_liquidity += liq

                sub_market_info.append({
                    'question': m.get('question', ''),
                    'price': format_price(m.get('outcomePrices', '')),
                    'volume': vol,
                    'liquidity': liq,
                    'volume_24h': float(m.get('volume24hr', 0) or 0),
                    'token_id': (json.loads(m.get('clobTokenIds', '[]')) or [None])[0],
                })

            domain = classify_domain(title + ' ' + ' '.join(m.get('question', '') for m in markets))
            vol_tier = classify_volume_tier(total_volume)
            age_hours = hours_ago(created)

            # Apply domain filter
            if domain_filter and domain != domain_filter:
                continue

            entry = {
                'title': title,
                'domain': domain,
                'created': event.get('createdAt'),
                'age': age_hours,
                'age_str': format_hours(age_hours),
                'volume': total_volume,
                'volume_str': format_volume(total_volume),
                'liquidity': total_liquidity,
                'liquidity_str': format_volume(total_liquidity),
                'vol_tier': vol_tier,
                'sizing': SIZING_RULES[vol_tier],
                'num_markets': len(markets),
                'sub_markets': sub_market_info[:5],  # Top 5 sub-markets
                'strong_domain': domain in STRONG_DOMAINS,
                'slug': event.get('slug', ''),
                'event_id': event.get('id', ''),
            }
            all_new.append(entry)

        # If we found events older than cutoff, we're done
        if found_old:
            break

        offset += 100
        pages += 1
        time.sleep(0.1)  # Rate limit respect

    # Sort: strong domains first, then by volume tier (discovery first), then age
    tier_order = {'discovery': 0, 'early': 1, 'forming': 2, 'mature': 3}
    all_new.sort(key=lambda x: (
        not x['strong_domain'],
        tier_order.get(x['vol_tier'], 4),
        x['age'],
    ))

    return all_new

def print_results(markets, json_output=False):
    """Print detected markets."""
    if json_output:
        print(json.dumps(markets, indent=2, default=str))
        return

    if not markets:
        print("No new markets found in the lookback window.")
        return

    # Summary stats
    strong = [m for m in markets if m['strong_domain']]
    discovery = [m for m in markets if m['vol_tier'] in ('discovery', 'early')]

    print(f"\n{'='*80}")
    print(f"NEW MARKET DETECTOR — {len(markets)} markets found")
    print(f"  Strong domains (GEO/POL/ECO/TEC/LAW): {len(strong)}")
    print(f"  In discovery window (<$10K volume): {len(discovery)}")
    print(f"  Strong + discovery (HIGHEST PRIORITY): {len([m for m in strong if m['vol_tier'] in ('discovery', 'early')])}")
    print(f"{'='*80}\n")

    # Group by priority
    priority_groups = {
        'FIRST-MOVER TARGETS (strong domain + discovery window)': [],
        'STRONG DOMAIN (price forming)': [],
        'OTHER DOMAINS': [],
    }

    for m in markets:
        if m['strong_domain'] and m['vol_tier'] in ('discovery', 'early'):
            priority_groups['FIRST-MOVER TARGETS (strong domain + discovery window)'].append(m)
        elif m['strong_domain']:
            priority_groups['STRONG DOMAIN (price forming)'].append(m)
        else:
            priority_groups['OTHER DOMAINS'].append(m)

    for group_name, group_markets in priority_groups.items():
        if not group_markets:
            continue

        print(f"--- {group_name} ({len(group_markets)}) ---\n")

        for m in group_markets:
            domain_tag = f"[{m['domain']}]"
            tier_tag = f"[{m['vol_tier'].upper()}]"
            star = " ***" if m['strong_domain'] and m['vol_tier'] in ('discovery', 'early') else ""

            print(f"  {domain_tag:6} {tier_tag:12} {m['title'][:65]}{star}")
            print(f"         Created: {m['age_str']:10} | Vol: {m['volume_str']:8} | Liq: {m['liquidity_str']:8} | Sizing: {m['sizing']}")

            for sub in m['sub_markets'][:3]:
                q = sub['question'][:55]
                print(f"         - {q:55} YES: {sub['price']:5} Vol: {format_volume(sub['volume'])}")

            print()

    # Actionable summary
    targets = priority_groups['FIRST-MOVER TARGETS (strong domain + discovery window)']
    if targets:
        print(f"{'='*80}")
        print(f"ACTION: {len(targets)} first-mover targets detected.")
        print(f"Next step: Evaluate each against existing domain research.")
        print(f"If edge > 8pp and your estimate is confident (±10pp): ENTER.")
        print(f"{'='*80}")

def main():
    lookback = LOOKBACK_HOURS
    domain_filter = None
    json_output = False
    include_all = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--hours' and i + 1 < len(args):
            lookback = float(args[i+1])
            i += 2
        elif args[i] == '--domain' and i + 1 < len(args):
            domain_filter = args[i+1].upper()
            i += 2
        elif args[i] == '--json':
            json_output = True
            i += 1
        elif args[i] == '--all':
            include_all = True
            i += 1
        else:
            i += 1

    print(f"Scanning for new markets (lookback: {lookback}h, domain: {domain_filter or 'ALL'})...")
    markets = detect_new_markets(lookback, domain_filter=domain_filter, include_all=include_all)
    print_results(markets, json_output=json_output)

if __name__ == '__main__':
    main()
