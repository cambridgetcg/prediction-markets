#!/usr/bin/env python3
"""
Temporal Consistency Checker (S007 Type 2)

Finds "by date" market series on Polymarket (same event, different deadlines)
and checks that P(by earlier date) <= P(by later date). Violations indicate
a pure arbitrage opportunity.

Usage:
    python3 temporal-checker.py                  # Full scan
    python3 temporal-checker.py --json           # JSON output
    python3 temporal-checker.py --tolerance 0.02 # Allow 2% noise before flagging
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

# ============================================================
# CONFIGURATION
# ============================================================

# Minimum price difference to flag as a violation (covers spread noise)
TOLERANCE_DEFAULT = 0.01  # 1%

# Minimum volume for a series to be worth analyzing
MIN_SERIES_VOLUME = 100000  # $100K total across the series

# Patterns that indicate "by date" markets
BY_DATE_PATTERNS = [
    r'by (January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+',
    r'by (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+',
    r'by \d{4}',
    r'by end of',
    r'before (January|February|March|April|May|June|July|August|September|October|November|December)',
    r'in (January|February|March|April|May|June|July|August|September|October|November|December)',
    r'by Q[1-4]',
]

# Month name to number mapping
MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9,
    'oct': 10, 'nov': 11, 'dec': 12,
}


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


def extract_base_question(question):
    """Strip date information to find the base question for series matching."""
    q = question.strip()

    # Remove date suffixes
    patterns = [
        r'\s+by\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+,?\s*\d*\??$',
        r'\s+by\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+,?\s*\d*\??$',
        r'\s+by\s+(March|June|September|December)\s+\d+,?\s*\d*\??$',
        r'\s+on\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+,?\s*\d*.*$',
        r'\s+on\s+\d{4}-\d{2}-\d{2}.*$',
        r'\s+by\s+end\s+of\s+\d{4}\??$',
        r'\s+in\s+\d{4}\??$',
        r'\s*\(ET\)\??$',
        r'\s*2026\??$',
        r'\s*2025\??$',
        r',?\s*2026\??$',
    ]

    for pattern in patterns:
        q = re.sub(pattern, '', q, flags=re.IGNORECASE).strip()

    # Remove trailing punctuation
    q = q.rstrip('?,. ')
    return q


def extract_date_key(question, end_date):
    """Extract a sortable date key from a market question or end_date.

    Prefers parsing the question text because end_date is often the event-level
    resolution deadline, not the specific "by" date in each sub-market.
    """
    q = question.lower()
    parsed_from_question = None

    # Match "by Month Day, Year" or "by Month Day"
    m = re.search(
        r'by\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d+),?\s*(\d{4})?',
        q
    )
    if m:
        month = MONTH_MAP[m.group(1)]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else 2026
        parsed_from_question = f'{year:04d}-{month:02d}-{day:02d}'

    # Match "on February 23, 2026 (ET)"
    if not parsed_from_question:
        m = re.search(
            r'on\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d+),?\s*(\d{4})?',
            q
        )
        if m:
            month = MONTH_MAP[m.group(1)]
            day = int(m.group(2))
            year = int(m.group(3)) if m.group(3) else 2026
            parsed_from_question = f'{year:04d}-{month:02d}-{day:02d}'

    # Match "by end of 2026"
    if not parsed_from_question:
        m = re.search(r'by\s+end\s+of\s+(\d{4})', q)
        if m:
            parsed_from_question = f'{m.group(1)}-12-31'

    # Match "in February" style (month-level granularity)
    if not parsed_from_question:
        m = re.search(r'in\s+(january|february|march|april|may|june|july|august|september|october|november|december)\??$', q)
        if m:
            month = MONTH_MAP[m.group(1)]
            parsed_from_question = f'2026-{month:02d}-28'

    # Return question-parsed date if found (more specific than event end_date)
    if parsed_from_question:
        return parsed_from_question

    # Fall back to end_date (event-level resolution date)
    if end_date:
        try:
            dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass

    return '9999-12-31'  # Unknown dates sort last


def fetch_all_events():
    """Fetch active events from Gamma API (events group related markets)."""
    all_events = []
    for offset in range(0, 1000, 100):
        url = (f"https://gamma-api.polymarket.com/events"
               f"?limit=100&closed=false&order=volume&ascending=false&offset={offset}")
        data = curl_json(url)
        if not data:
            break
        all_events.extend(data)
        if len(data) < 100:
            break
        time.sleep(0.25)
    return all_events


def build_series(events):
    """Extract temporal series from events with multiple "by date" markets."""
    series = {}

    for event in events:
        markets = event.get('markets', [])
        if len(markets) < 2:
            continue

        # Try to group markets within each event by base question
        event_series = {}
        for m in markets:
            q = m.get('question', '')
            if m.get('closed', False):
                continue

            base = extract_base_question(q)
            if len(base) < 10:
                continue

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
            end_date = m.get('endDate', '')
            date_key = extract_date_key(q, end_date)

            if base not in event_series:
                event_series[base] = []

            event_series[base].append({
                'question': q,
                'yes_price': yes_p,
                'volume': vol,
                'end_date': end_date,
                'date_key': date_key,
                'yes_token': yes_token,
                'market_id': m.get('id', ''),
            })

        # Add event-level series to global series
        for base, mkts in event_series.items():
            if base not in series:
                series[base] = []
            series[base].extend(mkts)

    # Also try to match across events (same base question in different events)
    # Deduplicate by market_id
    for base in series:
        seen = set()
        unique = []
        for m in series[base]:
            mid = m['market_id'] or m['question']
            if mid not in seen:
                seen.add(mid)
                unique.append(m)
        series[base] = unique

    # Filter to series with 2+ markets with distinct dates, sort by date
    valid_series = {}
    for base, mkts in series.items():
        if len(mkts) < 2:
            continue
        # Sort by date_key
        mkts.sort(key=lambda x: x['date_key'])
        # Check that dates are actually different (not all the same)
        unique_dates = set(m['date_key'] for m in mkts)
        if len(unique_dates) < 2:
            continue
        total_vol = sum(m['volume'] for m in mkts)
        if total_vol < MIN_SERIES_VOLUME:
            continue
        valid_series[base] = {
            'markets': mkts,
            'total_volume': total_vol,
        }

    return valid_series


def check_consistency(series, tolerance):
    """Check temporal consistency across all series."""
    results = []

    for base, data in series.items():
        mkts = data['markets']
        total_vol = data['total_volume']
        violations = []

        prev_price = -1
        prev_question = ''
        for i, m in enumerate(mkts):
            if m['yes_price'] < prev_price - tolerance:
                violations.append({
                    'earlier': prev_question,
                    'earlier_price': prev_price,
                    'later': m['question'],
                    'later_price': m['yes_price'],
                    'gap': prev_price - m['yes_price'],
                })
            prev_price = m['yes_price']
            prev_question = m['question']

        results.append({
            'base_question': base,
            'num_markets': len(mkts),
            'total_volume': total_vol,
            'markets': mkts,
            'violations': violations,
            'has_violations': len(violations) > 0,
        })

    # Sort: violations first, then by volume
    results.sort(key=lambda x: (-len(x['violations']), -x['total_volume']))
    return results


def print_report(results, tolerance):
    """Print formatted temporal consistency report."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print(f"\n{'=' * 80}")
    print(f"S007 TEMPORAL CONSISTENCY CHECKER — {now}")
    print(f"{'=' * 80}")
    print(f"Tolerance: {tolerance:.1%} (violations below this ignored as spread noise)")

    violations = [r for r in results if r['has_violations']]
    consistent = [r for r in results if not r['has_violations']]

    if violations:
        print(f"\n--- TEMPORAL VIOLATIONS ({len(violations)}) --- arbitrage opportunities ---")
        for i, r in enumerate(violations):
            print(f"\n  {i+1}. {r['base_question'][:70]}")
            print(f"     Markets: {r['num_markets']} | Total volume: ${r['total_volume']:,.0f}")
            print(f"     Timeline:")
            for m in r['markets']:
                flag = ''
                for v in r['violations']:
                    if m['question'] == v['later']:
                        flag = f'  ** VIOLATION: should be >= {v["earlier_price"]:.1%} (gap: {v["gap"]:.1%}) **'
                print(f"       {m['yes_price']:6.1%} | {m['date_key']:10s} | {m['question'][:55]}{flag}")
            print(f"     Violations:")
            for v in r['violations']:
                print(f"       BUY YES on \"{v['later'][:50]}\" at {v['later_price']:.1%}")
                print(f"       SELL YES on \"{v['earlier'][:50]}\" at {v['earlier_price']:.1%}")
                print(f"       Edge: {v['gap']:.1%} guaranteed")
    else:
        print(f"\n  No temporal violations detected (all {len(consistent)} series are consistent)")

    if consistent:
        print(f"\n--- CONSISTENT SERIES ({len(consistent)}) ---")
        for i, r in enumerate(consistent[:15]):
            prices = [f"{m['yes_price']:.0%}" for m in r['markets']]
            print(f"  {i+1}. {r['base_question'][:55]} | {r['num_markets']} mkts | {' -> '.join(prices)}")

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"  Series analyzed: {len(results)}")
    print(f"  With violations: {len(violations)}")
    print(f"  Consistent: {len(consistent)}")
    if violations:
        total_edge = sum(v['gap'] for r in violations for v in r['violations'])
        print(f"  Total arbitrage edge found: {total_edge:.1%}")
    print(f"{'=' * 80}")


def output_json(results, tolerance):
    """Output results as JSON."""
    output = []
    for r in results:
        output.append({
            'base_question': r['base_question'],
            'num_markets': r['num_markets'],
            'total_volume': r['total_volume'],
            'has_violations': r['has_violations'],
            'violations': r['violations'],
            'markets': [{
                'question': m['question'],
                'yes_price': m['yes_price'],
                'date_key': m['date_key'],
                'volume': m['volume'],
                'yes_token': m['yes_token'],
            } for m in r['markets']],
        })
    print(json.dumps(output, indent=2))


def main():
    parser = argparse.ArgumentParser(description='S007 Temporal Consistency Checker')
    parser.add_argument('--tolerance', type=float, default=TOLERANCE_DEFAULT,
                        help=f'Minimum violation size to flag (default: {TOLERANCE_DEFAULT})')
    parser.add_argument('--json', action='store_true',
                        help='Output as JSON')
    args = parser.parse_args()

    if not args.json:
        print("Fetching active markets from Polymarket...")

    events = fetch_all_events()
    if not args.json:
        print(f"  Fetched {len(events)} events")

    # Build temporal series from events
    series = build_series(events)
    if not args.json:
        print(f"  Found {len(series)} temporal series (2+ markets, >$100K volume)")

    # Check consistency
    results = check_consistency(series, args.tolerance)

    if args.json:
        output_json(results, args.tolerance)
    else:
        print_report(results, args.tolerance)


if __name__ == '__main__':
    main()
