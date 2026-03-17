#!/bin/bash
# Fetch top Polymarket events by 24h volume
# Usage: ./fetch-polymarket.sh [limit]

LIMIT=${1:-20}
DATE=$(date +%Y-%m-%d)
DIR="$(dirname "$0")/../data/polymarket"
mkdir -p "$DIR"

OUTFILE="$DIR/snapshot-${DATE}.json"

echo "Fetching top ${LIMIT} active Polymarket events..."

curl -s "https://gamma-api.polymarket.com/events?limit=${LIMIT}&active=true&order=volume24hr&ascending=false" \
  | python3 -m json.tool > "$OUTFILE"

echo "Saved to $OUTFILE"

# Generate human-readable summary
python3 -c "
import json, sys
with open('$OUTFILE') as f:
    events = json.load(f)

print(f'\\n=== Polymarket Snapshot {\"$DATE\"} ===')
print(f'Top {len(events)} events by 24h volume:\\n')

for i, e in enumerate(events, 1):
    title = e.get('title', 'Unknown')
    vol24 = e.get('volume24hr', 0)
    liquidity = e.get('liquidity', 0)
    
    # Get market probabilities
    markets = e.get('markets', [])
    probs = []
    for m in markets[:3]:  # Show up to 3 sub-markets
        q = m.get('groupItemTitle') or m.get('question', '')[:50]
        prices = json.loads(m.get('outcomePrices', '[]'))
        if prices:
            yes_price = float(prices[0])
            probs.append(f'{q}: {yes_price:.0%}')
    
    print(f'{i}. {title}')
    print(f'   24h Vol: \${vol24:,.0f} | Liquidity: \${liquidity:,.0f}')
    if probs:
        for p in probs:
            print(f'   → {p}')
    print()
" 2>/dev/null

echo "Summary complete."
