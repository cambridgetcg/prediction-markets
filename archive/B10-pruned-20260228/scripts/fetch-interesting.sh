#!/bin/bash
# Fetch non-sports Polymarket events with real liquidity
# Filters out sports/esports, focuses on politics, geopolitics, tech, crypto, culture

DATE=$(date +%Y-%m-%d)
DIR="$(dirname "$0")/../data/polymarket"
mkdir -p "$DIR"

OUTFILE="$DIR/interesting-${DATE}.json"

echo "Fetching active Polymarket events by liquidity..."

curl -s "https://gamma-api.polymarket.com/events?limit=200&active=true&closed=false&order=liquidity&ascending=false" | python3 -c "
import json, sys

events = json.load(sys.stdin)

# Filter out sports/esports
sports = ['vs.', ' fc ', 'nba ', 'nfl ', 'nhl ', 'mlb ', 'ufc ', 'serie a', 'la liga',
          'bo3', 'bo5', 'champion', 'premier league', 'champions league', 'stanley cup',
          'big game', 'super bowl', 'copa', 'heads-up poker', 'lol:', 'counter-strike',
          'dota', 'valorant', 'league of legends', 'world cup', 'australian open',
          'grand slam', 'f1 ', 'formula 1', 'eurovision']

interesting = []
for e in events:
    title = e.get('title','').lower()
    if any(s in title for s in sports):
        continue
    liq = e.get('liquidity', 0)
    if liq < 500:
        continue
    
    # Slim down the data
    active_markets = []
    for m in e.get('markets', []):
        if m.get('closed'):
            continue
        active_markets.append({
            'question': m.get('question'),
            'groupItemTitle': m.get('groupItemTitle'),
            'outcomePrices': m.get('outcomePrices'),
            'volume24hr': m.get('volume1wk', 0),
        })
    
    interesting.append({
        'id': e.get('id'),
        'title': e.get('title'),
        'liquidity': liq,
        'volume': e.get('volume', 0),
        'volume24hr': e.get('volume24hr', 0),
        'endDate': e.get('endDate'),
        'markets': active_markets[:10],
    })

# Save
json.dump(interesting, sys.stdout, indent=2)
" > "$OUTFILE"

COUNT=$(python3 -c "import json; print(len(json.load(open('$OUTFILE'))))")
echo "Saved $COUNT interesting events to $OUTFILE"

# Print summary
python3 -c "
import json
with open('$OUTFILE') as f:
    events = json.load(f)

print(f'\n=== Interesting Markets — $DATE ===\n')

for e in events[:25]:
    title = e['title']
    liq = e['liquidity']
    v24 = e['volume24hr']
    markets = e.get('markets', [])
    probs = []
    for m in markets[:3]:
        q = m.get('groupItemTitle') or (m.get('question','')[:60])
        prices = json.loads(m.get('outcomePrices','[]'))
        if prices:
            probs.append(f'{q}: {float(prices[0]):.0%}')
    
    print(f'• {title}')
    print(f'  Liq: \${liq:,.0f} | 24h Vol: \${v24:,.0f}')
    for p in probs:
        print(f'  → {p}')
    print()
"
