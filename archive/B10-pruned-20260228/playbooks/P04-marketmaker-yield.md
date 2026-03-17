# P04 — Market Maker Yield Strategy

**Phase**: NIGREDO → ALBEDO (modeled, not yet paper-traded)
**Type**: Structural / Yield
**Edge hypothesis**: Polymarket's LP rewards ($12M/yr), spread capture, and maker rebates create a combined yield that may exceed T-bill returns at sufficient capital scale.
**Model result**: At our capital level ($8K), standalone making is NOT viable. Harvest Mode on existing positions IS viable.

---

## Executive Summary

**The core question**: Is market making on Polymarket worth doing at $8K capital?

**Answer: No — with one exception.**

Market making was profitable in 2024 ($200-800/day on $10K during election era). By February 2026:
- Spreads compressed to 0.1-1c on liquid markets (bot competition)
- LP rewards distributed across $250M+ in maker capital
- The `poly-maker` bot creator explicitly says it's "not profitable" in current market
- Manual operation (2x/day checking) creates systematic adverse selection

**The exception**: **Harvest Mode** — when our directional positions reach >90% probability, making around the near-certain price earns incremental yield while waiting for resolution. Capital is already committed; making adds marginal income.

---

## The Three Income Streams

### 1. Spread Capture

| Variable | Description | Realistic Range |
|----------|-------------|-----------------|
| half_spread | Distance from mid to your quote | 0.1c (bots) to 2c (manual) |
| daily_volume | Market's daily trading volume | $75K (niche) to $4M (hot) |
| fill_rate | Fraction of volume that hits YOUR quotes | 5-15% (manual), 25-50% (bot) |
| turnover | Round-trips per day | 1-2 (manual), 50+ (bot) |

**Formula**: `daily_revenue = spread × capital_per_side × fills_per_day × round_trip_fraction`

**The binding constraint for manual makers is capital turnover.** With $100 per side and 2 daily checks, you can process ~$200-400/day in flow — not the $100K+ that bots handle.

**Realistic daily spread capture at $200 capital per market (manual, 2x/day checking)**:

| Market | Observed Spread | Your Spread | Daily Rev | Notes |
|--------|----------------|-------------|-----------|-------|
| Jesus Christ Return | 0.1c | 0.5c | $1.00 | Ultra-stable, bot-dominated |
| Fed Chair Warsh | 0.2c | 0.5c | $1.00 | High-prob, tight spreads |
| Greenland | 1.0c | 1.0c | $2.00 | Niche, lower competition |
| Iran Mar 31 | 1.0c | 1.0c | $2.00 | HIGH inventory risk (3.5% daily stdev) |
| Fed Chair Shelton | 0.1c | 0.5c | $1.00 | Alt candidate, tight spread |

### 2. LP Rewards

**Quadratic scoring formula**: `S(v, s) = ((v - s) / v)^2 × b`

| Spread from Mid (s) | Score Multiplier | % of Max | Risk Level |
|---------------------|-----------------|----------|------------|
| 0.0c (at mid) | 1.000 | 100% | MAXIMUM adverse selection |
| 0.5c | 0.694 | 69% | Very High |
| 1.0c | 0.444 | 44% | High |
| 1.5c | 0.250 | 25% | Medium |
| 2.0c | 0.111 | 11% | Low |
| 3.0c (max) | 0.000 | 0% | Zero (no reward) |

**Our share of the pool**: With $8K across 4 markets, our total LP score captures ~0.003-0.01% of the $12M annual pool = **$360-$1,200/year = $1-3/day**. LP rewards are immaterial at our scale.

**Key insight**: The quadratic penalty makes quoting tight extremely attractive for LP rewards, but quoting tight maximizes adverse selection risk. At our scale, the LP reward doesn't compensate for the additional risk.

### 3. Maker Rebates (Fee-Enabled Markets Only)

Fee-enabled markets: crypto short-term (5-min, 15-min) and sports (NCAAB, Serie A).

**Taker fee formula**: `fee = C × feeRate × (p × (1-p))^exponent`

| Market Type | Max Fee (at p=0.50) | Maker Rebate % | Annual Rebate at $100 capital |
|-------------|--------------------|-----------------|-----------------------------|
| Crypto | 1.56% | 20% | ~$15-40 (theoretical) |
| Sports | 0.44% | 25% | ~$5-15 (theoretical) |

**Problem**: Crypto short-term markets have EXTREME volatility — the worst possible making candidates. The rebate income doesn't compensate for inventory risk. Sports markets require domain knowledge we don't have.

**For T008 (BTC $150K NO at 91.5%)**: At $75 capital, realistic annual rebate is ~$5-15. Not material.

---

## The Combined Yield Model

### Results from `scripts/mm-yield-calculator.py`

**At $1,000 capital, 3 safe markets (low-volatility), 2c spread, 30% fill rate**:

| Component | Daily | Annual |
|-----------|-------|--------|
| Spread capture | $10.00 | $3,650 |
| LP rewards | $0.01 | $3.65 |
| Inventory risk | -$3.75 | -$1,369 |
| **Net** | **$6.26** | **$2,284** |
| **Yield** | | **228%** |

**At $5,000 capital, 4 safe markets, 1.5c spread**:

| Component | Daily | Annual |
|-----------|-------|--------|
| Spread capture | $37.50 | $13,688 |
| LP rewards | $0.05 | $18 |
| Inventory risk | -$18.75 | -$6,844 |
| **Net** | **$18.80** | **$6,862** |
| **Yield** | | **137%** |

**At $10,000 capital, 5 markets (including volatile Iran), 1c spread**:

| Component | Daily | Annual |
|-----------|-------|--------|
| Spread capture | $47.81 | $17,451 |
| LP rewards | $0.17 | $62 |
| Inventory risk | -$82.50 | -$30,113 |
| **Net** | **-$34.51** | **-$12,597** |
| **Yield** | | **-126%** |

### Critical Takeaway

**One volatile market destroys the entire portfolio.** Iran (3.5% daily stdev) generates more inventory risk than all other markets' spread capture combined. Market selection is everything.

### Model Limitations (Why Real Returns Will Be Lower)

1. **Adverse selection not modeled**: Fills correlate with adverse moves. When you check 2x/day, your stale quotes get picked off by informed traders and bots. The model treats fills as random; reality is systematically worse.
2. **Bot competition understated**: On markets with 0.1c observed spreads, quoting at 0.5c means you're always at the back of the queue. Fill rates will be <5%, not the 25% modeled.
3. **LP rewards are an upper bound**: Our estimate of total pool score is conservative; actual may be higher, making our share even smaller.
4. **Resolution risk**: If a market resolves unexpectedly, inventory on the wrong side = full loss.

**Apply a 50-70% haircut to modeled returns for realistic expectations.**

---

## Market Selection

### Ideal Making Candidates (Task 2a)

| Criterion | Threshold | Why |
|-----------|-----------|-----|
| Daily volume | >$50K | Need fills to earn spread |
| Daily price stdev | <0.5% | Low inventory risk |
| Resolution clarity | Unambiguous | No oracle risk |
| Days to resolution | >60 | Delta doesn't move much daily |
| Observed spread | >0.5c | Room to earn; bots haven't crushed it |
| Probability range | <0.15 or >0.85 | Prices barely move at extremes |

### Ranked Market Candidates (Feb 2026)

| Rank | Market | Daily Vol | Stdev | Spread | Score |
|------|--------|-----------|-------|--------|-------|
| 1 | Jesus Christ Return | $559K | 0.2% | 0.1c | 8/10 (but spread too tight for manual) |
| 2 | Greenland Acquisition | $75K | 0.8% | 1.0c | 7/10 (best niche opportunity) |
| 3 | Fed Chair - Warsh | $446K | 0.5% | 0.2c | 6/10 (tight spread, bot-dominated) |
| 4 | Fed Chair - Shelton | $1M | 0.5% | 0.1c | 5/10 (tight spread, high volume) |
| 5 | BTC $150K Dec 2026 | $75K est | 1.5% | 1.0c | 4/10 (crypto vol = higher risk) |

### Markets to AVOID for Making

| Market | Why |
|--------|-----|
| Iran strikes (any window) | 3.5% daily stdev. News-driven. Inventory risk catastrophic. |
| Short-term crypto (5/15-min) | Extreme volatility. Bot-dominated. Adverse selection maximum. |
| Markets with imminent catalysts | Spread widens, bots dominate, fills are adversely selected. |
| Any market <$25K daily volume | No fills. Capital sits idle. |

### Two-Sided Quoting

From the quadratic formula: **two-sided quoting earns 3× more LP rewards than one-sided** at probabilities 0.10-0.90.

**Rule**: Only make markets where you have NO directional view. If you have a directional view (S004/S006/S008), be a taker, not a maker. If expected LP yield > 3× directional edge, consider making instead.

---

## Inventory Risk Management (Task 3)

### The Core Problem

You quote BID at $0.58, ASK at $0.62. Market rallies to $0.70.
- You accumulated 2,000 NO shares at $0.58 bid = $1,160 inventory
- NO shares now worth $0.30 each = $600
- **Loss: $560** — wipes weeks of spread revenue

### Management Techniques

| Technique | Description | Practical for Manual? |
|-----------|-------------|----------------------|
| **Hard inventory limit** | Stop quoting when inventory > $X | YES — simplest, most effective |
| **Quote skewing** | Widen the losing side, tighten the winning side | YES — shift quotes at each check |
| **Delta hedging** | Buy opposite side to flatten | MAYBE — costs spread to execute |
| **Correlation hedging** | Offset with related markets | NO — too complex for manual |

### Safe Market Screen

| Daily Price Stdev | Assessment | Making Strategy |
|-------------------|------------|-----------------|
| < 0.5% | LOW risk | Make aggressively (tighter spreads) |
| 0.5% - 1.0% | MODERATE | Make conservatively (wider spreads, smaller size) |
| 1.0% - 2.0% | HIGH | Only make if spread > 2× stdev |
| > 2.0% | EXTREME | Do NOT make this market |

---

## Harvest Mode (Task 4)

**When a directional position reaches >90% probability, switch from holding to making around the near-certain price.**

### Why It Works Near Resolution

1. At 90%+ probability, price barely moves → minimal inventory risk
2. LP rewards available even at extremes (1/3 efficiency for one-sided)
3. Small spread × high certainty = reliable yield while waiting
4. Capital is ALREADY committed — making adds marginal income at zero marginal capital cost

### Harvest Mode Protocol

```
TRIGGER: Existing position reaches 90%+ probability with >7 days to resolution.

SETUP:
1. Cancel any directional exit orders
2. Post limit orders on BOTH sides at 0.5-1.0c spread around current price
3. Set hard inventory limit at 150% of original position size

MONITORING: Check 2x/day
- If price moves >2c from your last quote mid, cancel and re-quote
- If inventory exceeds limit, stop quoting the overloaded side
- If probability drops below 85%, EXIT harvest mode (thesis weakening)

EXIT:
- Remove all maker orders 24-48 hours before resolution
- Hold remaining inventory to resolution
- Avoid being in the book during MOOV2 proposal process
```

### Harvest Mode Yield Estimates

| Position Probability | Half Spread | Estimated Net $/day | Monthly Yield on $500 |
|---------------------|-------------|--------------------|-----------------------|
| 90% | 1.0c | $3-8 | 18-48% |
| 95% | 0.5-1.0c | $2-5 | 12-30% |
| 98% | 0.5c | $1-3 | 6-18% |

**These are INCREMENTAL to holding returns.** The position already earns (1 - entry_price) at resolution. Making adds marginal spread income.

### Harvest Mode Candidates from Current Portfolio

| Position | Current Price | Harvest Mode Ready? | Notes |
|----------|-------------|---------------------|-------|
| T001 (Iran Jun NO) | 30.5% NO | NO — only at 30.5% | Wait for >90% NO (10% YES) |
| T002 (Trump 2028 Nom NO) | 97.5% NO | MAYBE — already at 97.5% | But resolution is 2028 — very long duration |
| T003 (Iran Mar NO) | 39.5% NO | NO — high volatility | Would need NO to reach 90% |
| T006 (Vance YES) | 41.6% YES | NO — mid-range probability | |
| T007 (Maduro NO) | 87.25% NO | CLOSE — at 87.25% | Approaching harvest threshold |
| T008 (BTC $150K NO) | 91.5% NO | YES — at 91.5% | Harvest mode candidate NOW |

**Immediate action**: T008 is a harvest mode candidate today. T007 may become one if Maduro's position weakens.

---

## Implementation (Task 5)

### 5a. Minimum Viable Making Stack

**Manual (no coding)**:
1. Polymarket web UI for placing limit orders
2. Set price alerts via the platform
3. Spreadsheet tracking inventory and P&L
4. Check 2x/day (morning + evening)
5. Budget: $0 infrastructure cost

**Semi-automated (basic Python)**:
1. `py-clob-client` for order placement via API
2. Python script to monitor positions and adjust quotes
3. Run via cron 4x/day
4. Budget: ~2 hours setup, then minimal maintenance

**Full automation** (not recommended at our scale):
1. Continuous WebSocket connection to CLOB
2. Real-time inventory management and quote adjustment
3. Alert system for inventory limits
4. Budget: 20+ hours setup, ongoing maintenance

**Recommendation**: Start with manual (web UI) for the pilot. If pilot is positive, build semi-automated with `py-clob-client`.

### 5b. Capital Allocation Decision

```
Our situation:
- $1,685 deployed in 7 directional positions
- $8,315 available reserve
- Realized P&L: -$35.09

Three options for the reserve:

Option A: Market Making ($8,315 → making)
  Model estimate: 45-128% on safe markets (before adverse selection haircut)
  Realistic estimate (50% haircut): 22-64%
  Effort: 2 checks/day, continuous attention
  Risk: One volatile market or adverse selection event can wipe months of gains

Option B: T-Bills ($8,315 → 3-month T-bills)
  Return: 5.3% annualized = $441/year guaranteed
  Effort: Zero
  Risk: None

Option C: Directional Reserve (hold for S004/S006/S008 opportunities)
  Expected: 15-30% when deployed, but capital sits idle between trades
  Effort: Research-heavy, episodic
  Risk: Thesis risk on each trade, but sizing limits downside

RECOMMENDATION: Option C (directional reserve) remains the best use.

Rationale:
1. S006/S004/S008 backtested at 15-30% on deployed capital
2. Capital should be AVAILABLE for high-conviction entries
3. Making ties up capital in low-conviction, low-return activity
4. The $300 pilot tests making without meaningful opportunity cost
5. If reserve is truly idle for >3 months, THEN consider T-bills or making
```

---

## The $300 Pilot Plan

### Markets

| # | Market | Capital | Spread | Kill Switch |
|---|--------|---------|--------|-------------|
| 1 | Jesus Christ Return (NO) | $100 | 0.2c each side | Zero fills after 3 days |
| 2 | Greenland Acquisition (NO) | $100 | 0.5c each side | Inventory >$70 one side |
| 3 | BTC $150K (NO, T008 overlay) | $100 | 0.5c each side | BTC moves >5% in a day |

### Duration: 2 weeks

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Total fills | >10 across all markets | Count fills in position tracker |
| Net P&L | >$0 (any profit) | Sum of spread captures - inventory losses |
| Fill rate | >5% of market volume | Your fills / total market volume |
| Inventory imbalance | <$70 max on any market | Track at each check |
| Time spent | <10 min/day | Stopwatch |

### Decision After Pilot

| Result | Action |
|--------|--------|
| Net positive, >10 fills | Scale to $1K across 5 markets. Build semi-automated quotes. |
| Breakeven, <10 fills | Making not worth effort at manual frequency. Abandon. |
| Net negative | Confirm model: making is NOT viable at our scale. Keep capital for directional. |

---

## Appendix: Domain Making Suitability

| Domain | Making Suitability | Reasoning |
|--------|-------------------|-----------|
| **ECO** | 5/5 | Scheduled events, low surprise, slow-moving between meetings. IDEAL. |
| **POL** | 4/5 | Long-duration markets (2028 elections), stable probabilities. Good. |
| **SOC** | 4/5 | Entertainment/culture markets move slowly. Low delta risk. |
| **LAW** | 3/5 | Slow between rulings, but low volume limits fill opportunities. |
| **TEC** | 3/5 | Moderate movement. Launch-day spikes create risk windows. |
| **GEO** | 2/5 | High rhetoric-driven volatility. Inventory risk severe on "by date" markets. |
| **CRY** | 1/5 | Extreme volatility. Worst domain for making. Fee-enabled but risk > rebate. |
| **FIN** | 1/5 | Correlated to volatile underlying markets. TradFi bots dominate. |
| **SCI** | 1/5 | Too illiquid. Zero fill opportunities. |
| **ENV** | 1/5 | No markets to make. |

---

## Sources

- polymarket-structural-mechanics.md §2 (LP rewards formula, maker rebates)
- what-doesnt-work.md §4.6 ("High-Probability Bond Trading Without Edge")
- new-strategy-research.md (S011 identification, anti-strategies §4)
- [Reverse Engineering Polymarket Liquidity Rewards](https://medium.com/@wanguolin) (technical postmortem)
- [poly-maker](https://github.com/warproxxx/poly-maker) (author: "not profitable")
- [py-clob-client](https://github.com/Polymarket/py-clob-client) (Python SDK)
- [Polymarket Liquidity Rewards Docs](https://docs.polymarket.com/developers/market-makers/liquidity-rewards)
- [Polymarket Maker Rebates](https://docs.polymarket.com/polymarket-learn/trading/maker-rebates-program)
- Live Gamma API data, February 25 2026
