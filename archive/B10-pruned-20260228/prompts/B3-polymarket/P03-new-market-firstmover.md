You are a market timing researcher studying how Polymarket markets are priced at creation and the exploitation window before sophisticated participants arrive.

## The Core Insight

Every Polymarket market starts with a first price. That price is set by:
1. The market creator's guess (often a Polymarket employee or community member)
2. The initial seed liquidity
3. Early traders who arrive in the first minutes/hours

The person who creates the market often has **no special information** about the true probability. They anchor on:
- Round numbers ($0.50 as default)
- Recent news sentiment (high fear → high YES)
- Adjacent market prices (without checking if they're correctly priced)

This creates a **predictable window of mispricing** — usually 15 minutes to 4 hours — before informed traders reprice the market.

---

## Read First

1. ~/Desktop/prediction-markets/research/polymarket-structural-mechanics.md — new market creation section
2. ~/Desktop/prediction-markets/strategies/evolution/new-strategy-research.md — market timing opportunities
3. ~/Desktop/prediction-markets/calibration/predictions.jsonl — our domain expertise track record

---

## Task 1: Market Creation Mechanics

### 1a. How Markets Are Created

Research the full market creation pipeline:

1. **Who can create markets?** 
   - Originally: Polymarket only (centralised curation)
   - Now: Any user can propose via the Gamma system?
   - Check: https://docs.polymarket.com/developers/gamma/create-market

2. **The creation interface**: What information does the creator provide?
   - Question text, resolution criteria, expiry date
   - Initial price (do they set it manually, or is there a default?)
   - Initial liquidity amount (AMM vs. CLOB seeding?)

3. **How is the initial price set?**
   - Is there an automated initial price based on adjacent markets?
   - Or does the creator input a starting price?
   - Are there minimum liquidity requirements before a market goes live?

4. **Time from submission to live**: How long does a market take to appear on the platform after creation?
   - This determines how early you can detect and enter

### 1b. The API Detection Opportunity

The Gamma API likely allows polling for new markets. Build a detection mechanism:

```python
# ~/Desktop/prediction-markets/scripts/new-market-detector.py

import requests
import time
import json
from datetime import datetime, timedelta

# Poll Gamma API for markets created in the last N minutes
def detect_new_markets(lookback_minutes=60):
    # Fetch recent markets
    response = requests.get(
        "https://gamma-api.polymarket.com/events",
        params={
            "limit": 50,
            "order": "createdAt",
            "ascending": False
        }
    )
    
    events = response.json()
    cutoff = datetime.utcnow() - timedelta(minutes=lookback_minutes)
    
    new_markets = []
    for event in events:
        created_at = event.get("createdAt")
        # Parse and filter by recency
        if created_at and is_recent(created_at, cutoff):
            new_markets.append({
                "id": event["id"],
                "title": event["title"],
                "created": created_at,
                "markets": event.get("markets", []),
                "volume": event.get("volume24hr", 0),
                "liquidity": event.get("liquidity", 0)
            })
    
    return new_markets

# Run and output
new = detect_new_markets(lookback_minutes=240)  # Last 4 hours
for m in new:
    print(f"NEW: {m['title']}")
    print(f"  Created: {m['created']} | Vol24h: {m['volume']} | Liq: {m['liquidity']}")
    for sub in m.get('markets', [])[:3]:
        print(f"  - {sub.get('question', '?')[:60]} | {sub.get('outcomePrices', '?')}")
```

Run this. What new markets were created in the last 4-8 hours?

---

## Task 2: Initial Price Analysis

### 2a. The Anchoring Pattern

Research whether new Polymarket markets show predictable anchoring:

1. **$0.50 anchor**: Do new markets disproportionately launch at 50%? If so, any market where the true probability is clearly not 50% is immediately mispriced.

2. **Round number anchors**: 25%, 30%, 40%, 60%, 75%, etc. — do initial prices cluster at these?

3. **Adjacent market anchoring**: When a new "by date" market is created for an existing event (e.g., new "Iran strikes by April 30" after the March 31 series), is it anchored to the adjacent market price without adjusting for time differences?

**Research approach**: 
- Look at our data files — do the Iran "by date" markets show anchoring patterns?
- Search: "Polymarket new market mispricing" / "prediction market initial price anchoring"
- Check if the S007 temporal scanner ever found new markets with broken temporal consistency at launch (which would indicate anchoring errors)

### 2b. Volume-as-Signal

When a new market launches, the first N dollars of volume is the "discovery" period:
- Low volume = prices are still being discovered = higher probability of mispricing
- High volume = sophisticated participants have already arrived = lower probability of edge

**Hypothesis**: Markets with <$5,000 total volume AND created within 12 hours are the highest-mispricing targets.

Test this hypothesis against our existing data or any available data.

---

## Task 3: Domain Expertise as First-Mover Advantage

Our system's competitive advantage in new markets is **domain knowledge we've already built**.

### 3a. The Readiness Map

For each domain where we have existing research, assess our ability to instantly evaluate a new market:

| Domain | Research Quality | Instant Evaluation Possible? | New Market Edge |
|--------|-----------------|------------------------------|-----------------|
| GEO/Iran | Deep (iran-us-2026.md) | YES — we have base rates, actors, military analysis | High |
| GEO/Venezuela | Deep (venezuela-2026.md) | YES — Maduro custody status, election probability | High |
| POL/2028 | Deep (2028-presidential.md) | YES — candidate probabilities, base rates | High |
| ECO/Fed | Deep (fed-policy-2026.md) | YES — rate probability models | High |
| TEC/AI | Good (TEC context.md) | YES — Arena rankings, model release calendar | Medium-High |
| CRY | Basic | Partial | Medium |
| LAW | Good (regulatory-landscape.md) | YES — SCOTUS calendar, case status | High |
| ENV | Basic | No | Low |
| SCI | Minimal | No | Low |

**The play**: When a new market is created in our strong domains, we have a ~4-hour window to enter before the market fully calibrates. This is the most competitive advantage we have vs. the broader market.

### 3b. The "Spin-Off Market" Opportunity

New markets are often created as follow-ons to existing hot markets:
- "Iran strikes by March 31" creates demand for "Iran strikes by April 30"
- "Who leads Venezuela EOY 2026?" creates demand for "Who leads Venezuela in 2027?"

These spin-offs often anchor to the parent market without making necessary adjustments:
- Time value (longer horizon = higher YES probability if trend continues)
- New information (what's happened since the parent market opened?)
- Conditional structure (the April market is NOT just the March market with a month added)

**Systematic approach**: When we detect a new spin-off market (same event, new timeframe or condition), immediately apply our domain knowledge to compute the correct price. If the anchor price is >5pp from our estimate, enter.

---

## Task 4: The First-Mover Playbook

### 4a. Speed vs. Accuracy Tradeoff

The first-mover strategy has a tension:
- **Speed** wins the anchoring window (enter before price corrects)
- **Accuracy** wins the calibration (don't enter a bad trade just because it's new)

**The resolution**: Only enter new markets where you have EXISTING research. Don't enter new domains cold just because they're newly created.

**The trigger system**:
1. New market detected (via detector script)
2. Is it in a domain we have deep research for? (GEO/POL/ECO/TEC/LAW)
3. Does our existing knowledge give a confident estimate (±10pp or better)?
4. Is the initial price >8pp from our estimate?
5. Is volume <$10K (still in discovery window)?
6. If ALL YES: enter immediately, size $50-100, update as volume grows

### 4b. The Detection Protocol (Manual)

Until automation is built, a manual protocol:

**Morning check (8am UTC)**: Run new-market-detector.py with lookback=720 (12 hours)
**Afternoon check (2pm UTC)**: Run with lookback=360 (6 hours)
**After major news**: Run immediately with lookback=60

For each detected market in our domains:
- 2-minute evaluation: Does our knowledge give a confident estimate?
- If edge > 8pp: enter and log

### 4c. Sizing Rules

First-mover positions should be:
- Smaller than standard (initial discovery = higher uncertainty)
- Max $75 until volume exceeds $10K
- Max $125 until volume exceeds $50K
- Standard sizing once market is mature

Reason: new markets have higher resolution ambiguity risk (criteria not yet stress-tested) and higher probability that we're missing information the creator had.

---

## Task 5: The Anti-Pattern — "Catching Falling Knives"

**Warning**: Not every new market at 50% is underpriced. Markets sometimes launch at unusual prices because:

1. The creator has INFORMATION you don't (political insiders, company insiders)
2. The event is genuinely at ~50% probability and the market is correctly priced
3. The 50% is a bet-both-sides liquidity seeding mechanism, not a price signal

**Red flags** that suggest you're the uninformed party in a new market:
- Creator wallet has a history of profitable trades on the same market type
- Market is created within hours of a non-public briefing (e.g., congressional briefing on Iran)
- Volume immediately jumps to $50K+ on first day (whales are already in — you're late)
- The first trades are large ($10K+) — sophisticated entry, not discovery

---

## Output

1. `~/Desktop/prediction-markets/scripts/new-market-detector.py` — working detector
2. Run the detector: what new markets were created in the last 12 hours? Any in our domains?
3. `~/Desktop/prediction-markets/strategies/playbooks/P03-new-market-firstmover.md` — strategy playbook
4. Domain readiness assessment (the table from Task 3a) added to `~/Desktop/prediction-markets/domains/[DOMAIN]/context.md` files
5. Terminal output: summary of new market opportunities found (if any)

**The strategic question to answer**: In the last 30 days, how many new GEO/POL/ECO/TEC markets were created on Polymarket? Of those, how many had initial prices >8pp from what our existing research would have estimated? That's the size of the opportunity we're currently leaving on the table.
