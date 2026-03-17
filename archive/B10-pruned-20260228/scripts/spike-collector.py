#!/usr/bin/env python3
"""Collect active markets from Polymarket and detect price spikes."""

import json
import subprocess
import sys
import time

def curl_json(url):
    """Fetch JSON from URL via curl."""
    result = subprocess.run(
        ['curl', '-s', url],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"  curl error: {result.stderr}", file=sys.stderr)
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"  JSON parse error for {url[:80]}: {e}", file=sys.stderr)
        return None

def fetch_active_markets():
    """Fetch active high-volume markets from Gamma API."""
    all_markets = []
    # Paginate to get more markets
    for offset in [0, 100, 200, 300]:
        url = f"https://gamma-api.polymarket.com/markets?limit=100&closed=false&order=volume&ascending=false&offset={offset}"
        data = curl_json(url)
        if not data:
            break
        all_markets.extend(data)
        if len(data) < 100:
            break
        time.sleep(0.2)

    return all_markets

def is_sports(question):
    """Check if a market is sports-related."""
    sports_kw = [
        'NBA', 'NFL', 'NHL', 'MLB', 'IPL', 'Premier League', 'Serie A',
        'La Liga', 'Bundesliga', 'Champions League', 'UFC', 'ATP', 'WTA',
        'Formula 1', 'NASCAR', 'PGA', 'Cricket', 'Rugby', 'WNBA', 'MMA',
        'Copa', 'Leeds', 'Super Bowl', 'March Madness', 'World Series',
        'Stanley Cup', 'NCAA', 'EPL', 'Eredivisie', 'Ligue 1', 'AHL',
        'SHL', 'KHL', 'SNHL', 'CPL', 'Counter-Strike', 'Dota', 'Valorant',
        'League of Legends', 'CS2', 'BLAST', 'IEM', 'ESL', 'CCT',
        'Up or Down', 'BO3', 'BO2', 'BO1', 'Map 1', 'Map 2', 'Map 3',
        'O/U', 'Total Rounds', 'Handicap', 'EFL', 'Super Lig', 'Jupiler',
        'Eliteserien', 'Allsvenskan', 'Veikkausliiga', 'Turkish',
        # Team names that leak through
        'Pacers', 'Grizzlies', 'Lakers', 'Celtics', 'Warriors', 'Nuggets',
        'Thunder', 'Bucks', 'Cavaliers', 'Rockets', 'Knicks', 'Wolves',
        'Pistons', 'Spurs', 'Suns', 'Kings', 'Mavericks', 'Nets', 'Heat',
        'Magic', 'Hawks', 'Raptors', 'Hornets', 'Bulls', 'Clippers',
        '76ers', 'Pelicans', 'Wizards', 'Jazz', 'Blazers',
        'Yankees', 'Red Sox', 'Dodgers', 'Mets', 'Cubs', 'Braves',
        'Astros', 'Phillies', 'Cardinals', 'Padres', 'Giants', 'Orioles',
        'Tigers', 'Twins', 'Mariners', 'Rangers', 'Rays', 'Guardians',
        'Diamondbacks', 'Pirates', 'Brewers', 'Reds', 'Nationals',
        'Rockies', 'Royals', 'White Sox', 'Angels', 'Athletics',
        'Chiefs', 'Eagles', 'Bills', 'Lions', 'Ravens', 'Commanders',
        'Steelers', 'Texans', 'Chargers', '49ers', 'Seahawks', 'Packers',
        'Dolphins', 'Bengals', 'Vikings', 'Broncos', 'Raiders', 'Colts',
        'Jaguars', 'Falcons', 'Saints', 'Bears', 'Buccaneers', 'Panthers',
        'Patriots', 'Titans', 'Jets', 'Browns', 'Rams', 'Cardinals',
    ]
    q_lower = question.lower()
    for kw in sports_kw:
        if kw.lower() in q_lower:
            return True
    return False

def filter_interesting_markets(markets):
    """Filter to interesting non-sports markets with real activity."""
    interesting = []
    for m in markets:
        q = m.get('question', '')

        # Skip sports and 5-min crypto markets
        if is_sports(q):
            continue

        # Parse prices
        try:
            prices = json.loads(m.get('outcomePrices', '[]'))
            yes_price = float(prices[0])
        except:
            continue

        # Parse tokens
        try:
            tokens = json.loads(m.get('clobTokenIds', '[]'))
        except:
            continue
        if not tokens:
            continue

        vol = float(m.get('volumeNum', 0) or 0)
        v24 = float(m.get('volume24hr', 0) or 0)
        one_day = float(m.get('oneDayPriceChange', 0) or 0)
        one_week = float(m.get('oneWeekPriceChange', 0) or 0)
        one_month = float(m.get('oneMonthPriceChange', 0) or 0)

        interesting.append({
            'question': q,
            'market_id': m.get('id', ''),
            'yes_price': yes_price,
            'volume': vol,
            'volume24hr': v24,
            'yes_token': tokens[0],
            'no_token': tokens[1] if len(tokens) > 1 else '',
            'one_day_change': one_day,
            'one_week_change': one_week,
            'one_month_change': one_month,
            'end_date': m.get('endDate', ''),
        })

    return interesting

def fetch_price_history(token_id, interval='1d'):
    """Fetch price history from CLOB API."""
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval={interval}"
    data = curl_json(url)
    if not data or not isinstance(data, dict):
        return []
    return data.get('history', [])

def detect_spikes(history, threshold=0.15):
    """Detect price spikes >= threshold in daily history."""
    if len(history) < 2:
        return []

    spikes = []
    for i in range(1, len(history)):
        prev_price = float(history[i-1].get('p', 0))
        curr_price = float(history[i].get('p', 0))
        change = curr_price - prev_price

        if abs(change) >= threshold:
            spikes.append({
                'date': history[i].get('t', '?'),
                'prev_price': prev_price,
                'curr_price': curr_price,
                'change': change,
                'pct_change': change / max(prev_price, 0.01),
            })

    return spikes

def main():
    print("=" * 80)
    print("POLYMARKET SPIKE COLLECTOR")
    print("=" * 80)

    # Step 1: Fetch active markets
    print("\n[1] Fetching active markets from Gamma API...")
    all_markets = fetch_active_markets()
    print(f"    Total markets fetched: {len(all_markets)}")

    # Step 2: Filter to interesting markets
    interesting = filter_interesting_markets(all_markets)
    print(f"    Non-sports interesting markets: {len(interesting)}")

    # Sort by 24h volume
    interesting.sort(key=lambda x: x['volume24hr'], reverse=True)

    # Print top markets
    print("\n" + "=" * 80)
    print("ACTIVE MARKETS BY 24H VOLUME (non-sports)")
    print("=" * 80)

    for i, m in enumerate(interesting[:50]):
        spike_flag = " ** 1D SPIKE **" if abs(m['one_day_change']) >= 0.10 else ""
        week_flag = " ** 1W SPIKE **" if abs(m['one_week_change']) >= 0.15 else ""
        month_flag = " ** 1M SPIKE **" if abs(m['one_month_change']) >= 0.20 else ""
        flags = spike_flag + week_flag + month_flag
        print(f"\n{i+1:3d}. {m['question'][:100]}")
        print(f"     YES={m['yes_price']:.4f} | vol=${m['volume']:,.0f} | 24h=${m['volume24hr']:,.0f}")
        print(f"     1d_chg={m['one_day_change']:+.4f} | 1w_chg={m['one_week_change']:+.4f} | 1m_chg={m['one_month_change']:+.4f}{flags}")
        print(f"     end={m['end_date'][:10] if m['end_date'] else '?'} | token={m['yes_token'][:30]}...")

    # Step 3: Fetch price histories for top markets
    # Focus on markets with notable price changes or high 24h volume
    candidates = []
    for m in interesting[:50]:
        if abs(m['one_day_change']) >= 0.05 or abs(m['one_week_change']) >= 0.10 or m['volume24hr'] >= 100000:
            candidates.append(m)

    # Also add any with big month changes
    for m in interesting:
        if abs(m['one_month_change']) >= 0.15 and m not in candidates:
            candidates.append(m)

    print(f"\n\n{'=' * 80}")
    print(f"PRICE HISTORY ANALYSIS ({len(candidates)} markets)")
    print("=" * 80)

    all_spikes = []
    for i, m in enumerate(candidates[:30]):  # Limit to 30 to avoid rate limiting
        print(f"\n--- [{i+1}/{min(len(candidates),30)}] {m['question'][:80]} ---")
        print(f"    Current YES={m['yes_price']:.4f}")

        # Fetch daily price history
        history = fetch_price_history(m['yes_token'], '1d')
        time.sleep(0.3)  # Rate limiting

        if not history:
            print("    No price history available")
            continue

        print(f"    History: {len(history)} data points")

        # Show last 10 days of prices
        if len(history) > 0:
            recent = history[-10:]
            prices_str = " -> ".join([f"{float(h['p']):.3f}" for h in recent])
            print(f"    Recent prices: {prices_str}")

        # Detect spikes
        spikes = detect_spikes(history, threshold=0.10)  # 10% threshold for daily
        if spikes:
            print(f"    SPIKES DETECTED ({len(spikes)}):")
            for s in spikes[-5:]:  # Show last 5 spikes
                ts = s['date']
                # Convert timestamp if numeric
                if isinstance(ts, (int, float)):
                    from datetime import datetime
                    ts = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                print(f"      {ts}: {s['prev_price']:.3f} -> {s['curr_price']:.3f} ({s['change']:+.3f})")
                all_spikes.append({
                    'market': m['question'],
                    'date': ts,
                    'prev_price': s['prev_price'],
                    'curr_price': s['curr_price'],
                    'change': s['change'],
                    'current_price': m['yes_price'],
                    'token': m['yes_token'],
                })
        else:
            print("    No spikes >= 10% detected")

        # Also check hourly for the most active markets
        if m['volume24hr'] >= 500000:
            history_h = fetch_price_history(m['yes_token'], '1h')
            time.sleep(0.3)
            if history_h:
                hourly_spikes = detect_spikes(history_h, threshold=0.08)
                if hourly_spikes:
                    print(f"    HOURLY SPIKES ({len(hourly_spikes)} >= 8%):")
                    for s in hourly_spikes[-5:]:
                        ts = s['date']
                        if isinstance(ts, (int, float)):
                            from datetime import datetime
                            ts = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
                        print(f"      {ts}: {s['prev_price']:.3f} -> {s['curr_price']:.3f} ({s['change']:+.3f})")

    # Summary
    print(f"\n\n{'=' * 80}")
    print("SPIKE SUMMARY")
    print("=" * 80)
    print(f"\nTotal spikes detected (>=10% daily): {len(all_spikes)}")

    if all_spikes:
        # Sort by magnitude
        all_spikes.sort(key=lambda x: abs(x['change']), reverse=True)
        print("\nTop spikes by magnitude:")
        for i, s in enumerate(all_spikes[:20]):
            reverted = s['current_price'] - s['curr_price']
            print(f"  {i+1:3d}. {s['market'][:70]}")
            print(f"       {s['date']}: {s['prev_price']:.3f} -> {s['curr_price']:.3f} ({s['change']:+.3f}) | Now: {s['current_price']:.3f} (reversion: {reverted:+.3f})")

    # Step 4: Closed markets resolution patterns
    print(f"\n\n{'=' * 80}")
    print("CLOSED MARKET RESOLUTION PATTERNS")
    print("=" * 80)

    # Fetch recently closed high-volume markets
    closed_url = "https://gamma-api.polymarket.com/markets?limit=100&closed=true&order=volume&ascending=false"
    closed_data = curl_json(closed_url)

    if closed_data:
        yes_resolved = 0
        no_resolved = 0
        total_closed = 0

        closed_interesting = []
        for m in closed_data:
            q = m.get('question', '')
            if is_sports(q):
                continue

            try:
                prices = json.loads(m.get('outcomePrices', '[]'))
                yes_p = float(prices[0])
                no_p = float(prices[1])
            except:
                continue

            vol = float(m.get('volumeNum', 0) or 0)

            total_closed += 1
            if yes_p >= 0.99:
                yes_resolved += 1
                resolution = "YES"
            elif no_p >= 0.99:
                no_resolved += 1
                resolution = "NO"
            else:
                resolution = f"UNCLEAR (YES={yes_p:.3f})"

            closed_interesting.append({
                'question': q,
                'resolution': resolution,
                'volume': vol,
            })

        print(f"\nClosed non-sports markets: {total_closed}")
        print(f"  Resolved YES: {yes_resolved} ({100*yes_resolved/max(total_closed,1):.1f}%)")
        print(f"  Resolved NO:  {no_resolved} ({100*no_resolved/max(total_closed,1):.1f}%)")

        # Show top closed markets
        closed_interesting.sort(key=lambda x: x['volume'], reverse=True)
        print(f"\nTop closed markets by volume:")
        for i, m in enumerate(closed_interesting[:20]):
            print(f"  {i+1:3d}. [{m['resolution']:4s}] vol=${m['volume']:,.0f} | {m['question'][:70]}")

    # Save raw data for further analysis
    output = {
        'active_markets': interesting[:50],
        'spikes': all_spikes,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ'),
    }

    with open('/Users/yu/Desktop/prediction-markets/data/spike-data.json', 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\n\nRaw data saved to data/spike-data.json")

if __name__ == '__main__':
    main()
