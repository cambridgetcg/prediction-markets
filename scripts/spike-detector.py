#!/usr/bin/env python3
"""
S004 Spike Detector — Screens active Polymarket markets for overreaction opportunities.

Fetches current market data, identifies price spikes meeting S004 trigger criteria,
and scores each spike using the structural vs. emotional classification checklist.

Usage:
    python3 scripts/spike-detector.py                  # Full scan
    python3 scripts/spike-detector.py --domain GEO     # Filter by domain
    python3 scripts/spike-detector.py --threshold 0.10  # Custom spike threshold
    python3 scripts/spike-detector.py --json            # Output as JSON
"""

import json
import subprocess
import sys
import time
import math
from datetime import datetime, timezone

# --- Configuration ---

SPIKE_THRESHOLDS = {
    'daily': 0.10,     # 10% in 24h
    'weekly': 0.15,    # 15% in 7 days
    'monthly': 0.25,   # 25% in 30 days
}

MIN_LIQUIDITY_24H = 50000  # $50K minimum 24h volume for relevance
MIN_VOLUME_TOTAL = 200000  # $200K total volume for S004 consideration

DOMAIN_KEYWORDS = {
    'GEO': ['iran', 'strike', 'war', 'invasion', 'ceasefire', 'nato', 'ukraine',
             'russia', 'china', 'taiwan', 'israel', 'lebanon', 'khamenei',
             'regime', 'leader out', 'prime minister', 'grenell', 'venezuela',
             'greenland', 'annex', 'invade'],
    'CRY': ['bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol', 'xrp',
             'crypto', 'token', 'fdv', 'launch', 'dip to', 'reach $'],
    'POL': ['president', 'nomination', 'democrat', 'republican', 'trump',
             'election', 'nominate', 'congress', 'senate', 'governor',
             'fed chair', 'speaker'],
    'ECO': ['fed ', 'interest rate', 'bps', 'gdp', 'inflation', 'cpi',
             'unemployment', 'revenue', 'treasury'],
    'TECH': ['ai model', 'anthropic', 'openai', 'google', 'chatgpt', 'claude',
             'gemini', 'gpt'],
    'ENV': ['earthquake', 'hurricane', 'snow', 'temperature', 'wildfire',
             'climate', 'storm'],
    'OTHER': [],  # Fallback
}

SPORTS_KEYWORDS = [
    'nba', 'nfl', 'nhl', 'mlb', 'ipl', 'premier league', 'serie a',
    'la liga', 'bundesliga', 'champions league', 'ufc', 'atp', 'wta',
    'formula 1', 'nascar', 'pga', 'cricket', 'rugby', 'wnba', 'mma',
    'copa', 'super bowl', 'ncaa', 'world cup', 'fifa', 'bo3', 'bo2',
    'bo1', 'map 1', 'map 2', 'o/u', 'total rounds', 'handicap',
    'masters tournament', 'counter-strike', 'dota', 'valorant',
    'league of legends', 'cs2', 'blast', 'iem', 'esl', 'cct',
    'lck', 'lpl', 'lec', 'up or down',
]


def curl_json(url):
    """Fetch JSON from a URL via curl."""
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '15', url],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def classify_domain(question):
    """Classify a market question into a domain."""
    q = question.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if domain == 'OTHER':
            continue
        for kw in keywords:
            if kw in q:
                return domain
    return 'OTHER'


def is_sports(question):
    """Check if a market is sports-related."""
    q = question.lower()
    return any(kw in q for kw in SPORTS_KEYWORDS)


def score_spike(market, spike_type, magnitude):
    """Score a spike for structural vs. emotional content.

    Returns (structural_score, emotional_score, notes).
    Higher emotional = more likely overreaction = better S004 candidate.
    """
    structural = 0
    emotional = 0
    notes = []
    q = market['question'].lower()
    domain = market.get('domain', 'OTHER')

    # Factor 1: Is the move on a "by date" market with date approaching?
    end_date = market.get('end_date', '')
    if end_date:
        try:
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            days_left = (end - now).days
            if 0 < days_left < 7:
                emotional += 1
                notes.append(f"Expiring soon ({days_left}d)")
            elif days_left < 0:
                structural += 3
                notes.append("Already expired/resolved")
        except (ValueError, TypeError):
            pass

    # Factor 2: Domain-based prior
    if domain in ('GEO', 'CRY'):
        emotional += 1
        notes.append(f"Emotional domain ({domain})")
    elif domain in ('ECO', 'FIN'):
        structural += 2
        notes.append(f"Efficient domain ({domain})")

    # Factor 3: Spike magnitude — extreme moves more likely emotional
    if abs(magnitude) >= 0.30:
        emotional += 2
        notes.append(f"Extreme move ({magnitude:+.1%})")
    elif abs(magnitude) >= 0.15:
        emotional += 1
        notes.append(f"Large move ({magnitude:+.1%})")

    # Factor 4: Keywords suggesting structural vs. emotional
    structural_kw = ['passed', 'signed', 'confirmed', 'elected', 'resigned',
                     'occurred', 'declared', 'announced']
    emotional_kw = ['rhetoric', 'rumor', 'threat', 'ultimatum', 'tweet',
                    'may', 'could', 'might', 'sources say']

    for kw in structural_kw:
        if kw in q:
            structural += 1
            notes.append(f"Structural keyword: {kw}")
            break

    for kw in emotional_kw:
        if kw in q:
            emotional += 1
            notes.append(f"Emotional keyword: {kw}")
            break

    # Factor 5: Price level — extreme prices (>90% or <10%) more likely to be structural
    price = market.get('yes_price', 0.5)
    if price > 0.90 or price < 0.10:
        structural += 1
        notes.append(f"Extreme price ({price:.1%})")
    elif 0.30 <= price <= 0.70:
        emotional += 1
        notes.append("Mid-range price (reversion space)")

    # Factor 6: Volume relative to norm
    v24 = market.get('volume24hr', 0)
    vol_total = market.get('volume', 0)
    if vol_total > 0:
        daily_pct = v24 / vol_total
        if daily_pct > 0.10:  # >10% of total volume in one day
            notes.append(f"High relative volume ({daily_pct:.1%} of total)")
            # High volume spikes can be either — doesn't clearly favor one side

    return structural, emotional, notes


def fetch_markets():
    """Fetch active markets from Gamma API."""
    all_markets = []
    for offset in [0, 100, 200, 300]:
        url = (f"https://gamma-api.polymarket.com/markets"
               f"?limit=100&closed=false&order=volume&ascending=false&offset={offset}")
        data = curl_json(url)
        if not data:
            break
        all_markets.extend(data)
        if len(data) < 100:
            break
        time.sleep(0.2)
    return all_markets


def parse_market(m):
    """Parse a raw Gamma API market into our format."""
    q = m.get('question', '')
    if is_sports(q):
        return None

    try:
        prices = json.loads(m.get('outcomePrices', '[]'))
        yes_price = float(prices[0])
    except (json.JSONDecodeError, IndexError, ValueError):
        return None

    try:
        tokens = json.loads(m.get('clobTokenIds', '[]'))
    except json.JSONDecodeError:
        return None

    if not tokens:
        return None

    return {
        'question': q,
        'market_id': m.get('id', ''),
        'yes_price': yes_price,
        'volume': float(m.get('volumeNum', 0) or 0),
        'volume24hr': float(m.get('volume24hr', 0) or 0),
        'liquidity': float(m.get('liquidityNum', 0) or 0),
        'one_day_change': float(m.get('oneDayPriceChange', 0) or 0),
        'one_week_change': float(m.get('oneWeekPriceChange', 0) or 0),
        'one_month_change': float(m.get('oneMonthPriceChange', 0) or 0),
        'yes_token': tokens[0],
        'no_token': tokens[1] if len(tokens) > 1 else '',
        'end_date': m.get('endDate', ''),
        'domain': classify_domain(q),
    }


def find_spikes(markets, thresholds=None, domain_filter=None):
    """Find markets with price spikes exceeding thresholds."""
    if thresholds is None:
        thresholds = SPIKE_THRESHOLDS

    spikes = []
    for m in markets:
        if domain_filter and m['domain'] != domain_filter:
            continue
        if m['volume'] < MIN_VOLUME_TOTAL:
            continue

        spike_info = {
            'market': m,
            'spike_types': [],
            'max_magnitude': 0,
        }

        # Check daily
        if abs(m['one_day_change']) >= thresholds['daily']:
            spike_info['spike_types'].append(('daily', m['one_day_change']))
            spike_info['max_magnitude'] = max(spike_info['max_magnitude'],
                                              abs(m['one_day_change']))

        # Check weekly
        if abs(m['one_week_change']) >= thresholds['weekly']:
            spike_info['spike_types'].append(('weekly', m['one_week_change']))
            spike_info['max_magnitude'] = max(spike_info['max_magnitude'],
                                              abs(m['one_week_change']))

        # Check monthly
        if abs(m['one_month_change']) >= thresholds['monthly']:
            spike_info['spike_types'].append(('monthly', m['one_month_change']))
            spike_info['max_magnitude'] = max(spike_info['max_magnitude'],
                                              abs(m['one_month_change']))

        if spike_info['spike_types']:
            # Score the spike
            primary_type, primary_mag = max(spike_info['spike_types'],
                                           key=lambda x: abs(x[1]))
            s_score, e_score, notes = score_spike(m, primary_type, primary_mag)
            spike_info['structural_score'] = s_score
            spike_info['emotional_score'] = e_score
            spike_info['notes'] = notes

            if e_score > s_score:
                spike_info['classification'] = 'EMOTIONAL'
                spike_info['s004_signal'] = 'FADE'
            elif s_score > e_score:
                spike_info['classification'] = 'STRUCTURAL'
                spike_info['s004_signal'] = 'SKIP'
            else:
                spike_info['classification'] = 'MIXED'
                spike_info['s004_signal'] = 'HALF-SIZE'

            spikes.append(spike_info)

    # Sort by emotional score (descending), then by magnitude
    spikes.sort(key=lambda x: (x['emotional_score'], x['max_magnitude']),
                reverse=True)
    return spikes


def print_spike_report(spikes):
    """Print a formatted spike report."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f"\n{'=' * 80}")
    print(f"S004 SPIKE DETECTOR — {now}")
    print(f"{'=' * 80}")

    if not spikes:
        print("\nNo spikes detected meeting S004 criteria.")
        return

    # Separate by signal type
    fade_signals = [s for s in spikes if s['s004_signal'] == 'FADE']
    half_signals = [s for s in spikes if s['s004_signal'] == 'HALF-SIZE']
    skip_signals = [s for s in spikes if s['s004_signal'] == 'SKIP']

    if fade_signals:
        print(f"\n--- FADE SIGNALS ({len(fade_signals)}) --- S004 candidates ---")
        for i, s in enumerate(fade_signals):
            m = s['market']
            types_str = ', '.join([f"{t}:{v:+.1%}" for t, v in s['spike_types']])
            print(f"\n  {i+1}. [{m['domain']:5s}] {m['question'][:75]}")
            print(f"     YES={m['yes_price']:.1%} | Vol=${m['volume']:,.0f} | 24h=${m['volume24hr']:,.0f}")
            print(f"     Spikes: {types_str}")
            print(f"     Score: structural={s['structural_score']} emotional={s['emotional_score']}")
            print(f"     Notes: {'; '.join(s['notes'])}")
            # Calculate suggested entry/target/stop
            primary_mag = max(abs(v) for _, v in s['spike_types'])
            direction = 1 if any(v > 0 for _, v in s['spike_types']) else -1
            # Fading means buying the opposite side
            if direction > 0:  # Price spiked UP → buy NO (bet price goes down)
                target = m['yes_price'] - primary_mag * 0.40
                stop = m['yes_price'] + 0.08
                print(f"     TRADE: Buy NO at {1-m['yes_price']:.1%}")
                print(f"       Target: YES drops to {max(target, 0.01):.1%} (40% retracement)")
                print(f"       Stop: YES rises to {min(stop, 0.99):.1%}")
            else:  # Price spiked DOWN → buy YES (bet price goes up)
                target = m['yes_price'] + primary_mag * 0.40
                stop = m['yes_price'] - 0.08
                print(f"     TRADE: Buy YES at {m['yes_price']:.1%}")
                print(f"       Target: YES rises to {min(target, 0.99):.1%} (40% retracement)")
                print(f"       Stop: YES drops to {max(stop, 0.01):.1%}")

    if half_signals:
        print(f"\n--- HALF-SIZE SIGNALS ({len(half_signals)}) --- mixed classification ---")
        for i, s in enumerate(half_signals):
            m = s['market']
            types_str = ', '.join([f"{t}:{v:+.1%}" for t, v in s['spike_types']])
            print(f"\n  {i+1}. [{m['domain']:5s}] {m['question'][:75]}")
            print(f"     YES={m['yes_price']:.1%} | Spikes: {types_str}")
            print(f"     Score: structural={s['structural_score']} emotional={s['emotional_score']}")
            print(f"     Notes: {'; '.join(s['notes'])}")

    if skip_signals:
        print(f"\n--- SKIP ({len(skip_signals)}) --- structural moves, don't fade ---")
        for i, s in enumerate(skip_signals[:10]):  # Show top 10 only
            m = s['market']
            types_str = ', '.join([f"{t}:{v:+.1%}" for t, v in s['spike_types']])
            print(f"  {i+1}. [{m['domain']:5s}] {m['question'][:65]} | {types_str}")

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"  Total spikes: {len(spikes)}")
    print(f"  FADE signals: {len(fade_signals)}")
    print(f"  HALF-SIZE:    {len(half_signals)}")
    print(f"  SKIP:         {len(skip_signals)}")
    print(f"{'=' * 80}")


def output_json(spikes):
    """Output spikes as JSON for programmatic use."""
    output = []
    for s in spikes:
        m = s['market']
        output.append({
            'question': m['question'],
            'domain': m['domain'],
            'yes_price': m['yes_price'],
            'volume': m['volume'],
            'volume24hr': m['volume24hr'],
            'spike_types': s['spike_types'],
            'max_magnitude': s['max_magnitude'],
            'classification': s['classification'],
            's004_signal': s['s004_signal'],
            'structural_score': s['structural_score'],
            'emotional_score': s['emotional_score'],
            'notes': s['notes'],
            'yes_token': m['yes_token'],
            'end_date': m['end_date'],
        })
    print(json.dumps(output, indent=2))


def main():
    import argparse
    parser = argparse.ArgumentParser(description='S004 Spike Detector')
    parser.add_argument('--domain', type=str, default=None,
                        help='Filter by domain (GEO, CRY, POL, ECO, TECH, ENV, OTHER)')
    parser.add_argument('--threshold', type=float, default=None,
                        help='Custom daily spike threshold (default: 0.10)')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    args = parser.parse_args()

    thresholds = SPIKE_THRESHOLDS.copy()
    if args.threshold:
        thresholds['daily'] = args.threshold
        thresholds['weekly'] = args.threshold * 1.5
        thresholds['monthly'] = args.threshold * 2.5

    if not args.json:
        print("Fetching active markets from Polymarket...")

    raw_markets = fetch_markets()
    if not args.json:
        print(f"  Fetched {len(raw_markets)} markets")

    # Parse and filter
    markets = []
    for m in raw_markets:
        parsed = parse_market(m)
        if parsed:
            markets.append(parsed)

    if not args.json:
        print(f"  {len(markets)} non-sports markets")

    # Find spikes
    spikes = find_spikes(markets, thresholds, args.domain)

    if args.json:
        output_json(spikes)
    else:
        print_spike_report(spikes)


if __name__ == '__main__':
    main()
