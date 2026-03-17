You are a system designer formalising the single biggest insight from comparing paper vs. live performance: fast-resolving markets are the system's highest-value asset class for calibration, compounding, and risk management.

## The Core Finding

```
Paper account (7 positions): 0 resolved predictions in 2 days
Live account (3 positions): 2 positions resolve within 6 days

SOTU retrospective (1 prompt): 12 calibration resolutions in 24 hours
Long-duration paper positions: 0 calibration resolutions in 2+ months (expected)

Calibration data per day:
  SOTU batch: 12 / 1 day = 12.0/day
  Bond rotation (S011): 1 / 5 days = 0.2/day
  Long-duration directional (GEO): 1 / 60+ days = 0.016/day
  
SOTU generates 750× more calibration data per day than GEO positions.
```

**The implication**: The portfolio is optimised for capital efficiency (deploying $1,685 in interesting long-duration bets) when it should be optimised for **learning efficiency** (getting as many resolution events per day as possible during the calibration phase).

This doesn't mean abandoning long positions. It means deliberately seeding the portfolio with short-resolution trades to accelerate the calibration loop.

---

## Read First

1. ~/Desktop/prediction-markets/calibration/resolutions.jsonl — all resolved predictions
2. ~/Desktop/prediction-markets/calibration/calibration.md (if I05 has run)
3. ~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md
4. ~/Desktop/prediction-markets/trades/live-trades.md
5. ~/Desktop/prediction-markets/strategies/playbooks/S011-bond-rotation.md (if P02 has run)
6. ~/Desktop/prediction-markets/research/polymarket-structural-mechanics.md

---

## Task 1: The Fast-Resolution Market Taxonomy

Define "fast-resolving" and classify all market types we trade:

### Resolution Speed Categories

| Category | Resolution Window | Examples | Calibration Value |
|----------|------------------|----------|-------------------|
| **Instant** | Same day | In-game markets (not our focus) | Very high, but ephemeral |
| **Overnight** | <24h | Fed meeting result, election night, primary night | ★★★★★ |
| **Weekly** | 1-7 days | Weekly catalyst events, SOTU-type speeches, data releases | ★★★★☆ |
| **Monthly** | 7-30 days | FOMC meetings, primary elections, economic data | ★★★☆☆ |
| **Quarterly** | 30-90 days | Iran Mar 31, seasonal price targets, quarterly reports | ★★☆☆☆ |
| **Annual** | 90-365 days | EOY price targets, annual election cycles | ★☆☆☆☆ |
| **Multi-year** | 1-3 years | 2028 election, long-term policy | ○ (negligible) |

**Strategic implication**: During Phase 1 (calibration phase, first 6 months), the target allocation should be:
- 40%+ of new capital into Overnight/Weekly markets
- 30% into Monthly markets
- 20% into Quarterly markets
- ≤10% into Annual/Multi-year

Current paper allocation: ~90% Quarterly-to-Multi-year. This is inverted.

---

## Task 2: The Fast-Resolution Opportunity Screen

### 2a. Systematic Calendar

Build a forward calendar of fast-resolving opportunities for the next 60 days:

```
Weekly: 
  Feb 28   — US revenue <$100b (LT002 live) — FRIDAY
  Feb 28   — Iran by Feb 28 resolution window
  Feb 28   — [Other Feb 28 expiring markets?]
  
  Mar 3    — Texas Republican primary (LT003 live) — MONDAY
  Mar 4    — State of the Union (S003 catalyst, multiple fast-resolving markets)
  Mar 7    — February jobs report (S011 Fed market overnight)
  
Monthly:
  Mar 11   — February CPI
  Mar 13   — January PCE + GDP
  Mar 17-18 — FOMC meeting (S011 result + S003 entry for April)
  Mar 25   — [Any primaries?]
  Mar 26   — Maduro court hearing (LT007 paper)
  Mar 31   — Iran Mar 31 (PT003, PT005, LT001)

  Apr 3    — March NFP
  Apr 9    — February PCE
  Apr 10   — March CPI
  Apr 29-30 — FOMC April meeting
```

Fetch this calendar data:
```bash
curl -s "https://gamma-api.polymarket.com/events?limit=100&end_date_min=2026-02-25&end_date_max=2026-03-07&active=true" 
```

For each event in the next 7 days:
- What markets resolve on that date?
- Are any in our strong domains (GEO, POL, ECO, TEC)?
- What's the current price? Is there edge?

### 2b. The Bond Rotation Screen

S011 specifically targets >95% probability, <7 days to resolution. Build the automated screen:

```python
# ~/Desktop/prediction-markets/scripts/fast-resolution-screener.py

import requests, json
from datetime import datetime, timedelta

def screen_fast_resolution(max_days=7, min_prob=0.95):
    """
    Find markets that:
    1. Resolve within max_days
    2. Have one side priced at min_prob or higher
    3. Have >$20K liquidity (enough to enter without slippage)
    4. Are NOT in domains with high oracle risk (crypto speculation, very niche events)
    """
    # Calculate date range
    today = datetime.utcnow()
    end_date_max = (today + timedelta(days=max_days)).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # Fetch events
    resp = requests.get(
        "https://gamma-api.polymarket.com/events",
        params={"limit": 200, "active": "true", "end_date_max": end_date_max}
    )
    events = resp.json()
    
    opportunities = []
    for event in events:
        for market in event.get("markets", []):
            prices_raw = market.get("outcomePrices", "[]")
            if isinstance(prices_raw, str):
                prices = json.loads(prices_raw)
            else:
                prices = prices_raw
            
            if not prices:
                continue
            
            yes_price = float(prices[0]) if prices else 0
            no_price = float(prices[1]) if len(prices) > 1 else 1 - yes_price
            
            max_price = max(yes_price, no_price)
            dominant_side = "YES" if yes_price >= no_price else "NO"
            
            if max_price >= min_prob:
                liquidity = float(market.get("liquidity", 0))
                if liquidity >= 20000:
                    end_date = market.get("endDate") or event.get("endDate")
                    opportunities.append({
                        "event": event.get("title", "?")[:60],
                        "market": market.get("question", "?")[:60],
                        "side": dominant_side,
                        "price": max_price,
                        "return": (1 - max_price) / max_price,
                        "liquidity": liquidity,
                        "end_date": end_date,
                    })
    
    # Sort by return × probability (EV weighted)
    opportunities.sort(key=lambda x: x["return"] * x["price"], reverse=True)
    
    print(f"Fast-resolution opportunities (next {max_days} days, >{min_prob*100:.0f}% confidence):")
    print()
    for opp in opportunities[:20]:
        ann_return = opp["return"] / 7 * 365  # rough annualisation
        print(f"  {opp['side']}:{opp['price']:.3f} | ret:{opp['return']*100:.1f}% | liq:${opp['liquidity']/1000:.0f}K | {opp['event'][:40]}")
        print(f"    {opp['market'][:60]}")
    
    return opportunities

if __name__ == "__main__":
    screen_fast_resolution(max_days=7, min_prob=0.95)
    print()
    screen_fast_resolution(max_days=30, min_prob=0.90)
```

Write and run this script. What does it find?

---

## Task 3: The SOTU Pattern — Replicable Catalyst Events

The SOTU batch proved that formal speeches and structured events (where word/topic markets exist) are gold mines for fast calibration. Find the next similar events:

**Replicable SOTU-type events (Trump speeches with prediction markets):**
1. **Weekly addresses/briefings**: Does Trump do weekly radio addresses or press conferences with associated markets?
2. **Cabinet meetings**: Any prediction markets on what gets announced?
3. **State visits**: When foreign leaders visit the White House, are there markets on outcomes?
4. **Congressional testimony**: Fed Chair Yellen/Powell-type hearings where market language markets exist?
5. **Summit communiqués**: G7, NATO summits — outcome markets that resolve within 24h of statement

**Research**: Search Polymarket for any of these market types active in the next 30 days. Note: the SOTU itself won't repeat for ~11 months, but the PATTERN (formal event + word/topic markets) might repeat on smaller events.

Web search approach (if available): "Polymarket Trump speech markets 2026" / "Polymarket press conference word markets"

Alternatively, search Gamma API:
```bash
curl -s "https://gamma-api.polymarket.com/events?q=trump+say&limit=20"
curl -s "https://gamma-api.polymarket.com/events?q=speech+word&limit=20"
```

---

## Task 4: Calibration-First Portfolio Rebalancing

Given the finding that calibration is the bottleneck (not capital), propose a portfolio rebalancing:

### 4a. The Target Allocation

**Phase 1 (calibration phase, now until 50 resolved predictions):**

| Speed Category | Target % of New Deployments | Reason |
|---------------|---------------------------|--------|
| Overnight/Weekly | 50% | Maximum calibration data per dollar |
| Monthly | 30% | Good calibration, manageable risk |
| Quarterly | 15% | Maintains domain expertise, acceptable |
| Annual/Multi-year | 5% | Only for highest-conviction structural plays |

**Current paper allocation deviation:**
- Weekly: 0% (should be 50%)
- Monthly: 14% (T004 closed, April FOMC pending)
- Quarterly: 26% (T003, T005 Mar 31)
- Annual/Multi-year: 60%+ (T001 Jun 30, T002/T006 2028, T007/T008 Dec 31)

**Correction**: Next $500 of new paper capital should go 70% into Weekly/Monthly.

### 4b. Don't Close Long-Duration Positions

The fix is NOT to close T001, T006, T007, T008. They're open, let them run per their rules.

The fix is to WEIGHT NEW CAPITAL differently. Use the $8,315 available in paper account deliberately:
- Next 5 entries: at least 3 must be Weekly/Monthly resolution
- Set up an "S011 rotation fund": $500 of paper capital dedicated purely to bond rotation trades, recycling every 5-7 days

### 4c. The Compounding Math

**Bond rotation compounding example (conservative):**
- $500 in bond rotation
- Average return per trade: 3% (position at 97% resolves YES)
- Average duration: 5 days per trade
- Cycle rate: ~6 trades per month
- Monthly return: approximately 3% × 6 = 18% (gross, before any losses)
- Even with 10% failure rate: 0.9 × 3% × 6 = 16.2% monthly
- Annual compounded: (1.162)^12 = 5.5× return

This is not realistic at scale (liquidity limits, rate pressure), but demonstrates the STRUCTURAL advantage of fast-resolving high-probability trades over long-duration directional ones.

---

## Task 5: The Pipeline Design

Design the fast-resolution workflow as a system:

```
DAILY MORNING CHECK (8am UTC):
  1. Run fast-resolution-screener.py (next 7 days, >95%)
  2. Scan for any catalyst events today (from calendar)
  3. Check: did anything resolve overnight? Update tracking.
  
EVENT-TRIGGERED (any time):
  1. News breaks on an active market
  2. Run B03 (live sentiment signal) if ECI > 35
  3. Check: does the event resolve any fast-resolution position?
  
WEEKLY REVIEW (Sundays):
  1. What resolved this week? (Brier score update)
  2. What S011 opportunities are available next week?
  3. Rebalance: is the fast/slow ratio in target range?
  4. Are any overnight FOMC/data releases coming? Set alerts.
```

**Infrastructure needed** (from P prompts):
- `fast-resolution-screener.py` (this prompt builds it)
- `new-market-detector.py` (from P03) — for first-mover on new fast-resolving markets
- Resolution registry (from P02) — to detect when outcomes occur before oracle resolves

---

## Output

1. `~/Desktop/prediction-markets/scripts/fast-resolution-screener.py` — working script
2. Run it: terminal output of current opportunities
3. `~/Desktop/prediction-markets/strategies/playbooks/S011-bond-rotation.md` — complete playbook (or update if P02 already ran)
4. `~/Desktop/prediction-markets/strategies/fast-resolution-calendar.md` — next 60 days of events
5. Portfolio rebalancing recommendation: for the next $250 of paper capital, what 3-4 fast-resolution trades to enter?
6. Updated `~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md` — add "Resolution Speed Distribution" section showing current vs. target allocation

**Terminal output must include**: "If the next $250 paper deployment is split 50% weekly / 30% monthly / 20% quarterly, what specific trades are available today?"
