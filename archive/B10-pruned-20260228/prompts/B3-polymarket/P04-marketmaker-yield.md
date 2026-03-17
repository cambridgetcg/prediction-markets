You are a market microstructure engineer building a yield strategy from Polymarket's liquidity rewards programme, maker rebates, and spread capture — treating prediction markets as a yield instrument rather than a directional betting platform.

## Read First

1. ~/Desktop/prediction-markets/research/polymarket-structural-mechanics.md — section 2 (Market Making / Liquidity Rewards) — the quadratic scoring formula is critical
2. ~/Desktop/prediction-markets/strategies/evolution/new-strategy-research.md — S011 identification
3. ~/Desktop/prediction-markets/research/what-doesnt-work.md — section on "High-Probability Bond Trading"

## The Three Income Streams

A Polymarket market maker can earn from three sources simultaneously:

1. **Spread capture**: Buy at bid, sell at ask. Profit = spread × volume × fill rate
2. **LP rewards**: Polymarket pays $12M/year to makers providing tight spreads. Quadratic scoring rewards proximity to midpoint.
3. **Maker rebates**: On fee-enabled markets (crypto, sports), takers pay a fee; makers receive 20-25% of those fees as rebate.

**The total return** can be modelled. Your task is to build the model and find the optimal markets to make.

---

## Task 1: The Full P&L Model

### 1a. Spread Capture Revenue

For a market maker quoting a market:

```
Variables:
- mid = midpoint price (e.g., 0.60)
- half_spread = half of your quoted spread (e.g., 0.01 = 1 cent half-spread)
- bid = mid - half_spread (you buy here)
- ask = mid + half_spread (you sell here)
- daily_volume = $ of contracts traded daily in this market
- fill_rate = fraction of volume that hits YOUR quotes (typically 20-50% for a single maker)
- inventory_drift = cost of holding unbalanced YES/NO inventory

Revenue per day:
spread_revenue = half_spread × 2 × daily_volume × fill_rate

Inventory risk:
If market moves 5pp against you while you're holding $500 of imbalanced inventory:
inventory_loss = 0.05 × 500 = $25

Net spread capture = spread_revenue - inventory_loss
```

**Build this model for the top 5 most liquid non-sports Polymarket markets.**

What is the realistically achievable daily spread revenue at $10K capital deployed?

### 1b. LP Rewards Revenue

From the structural mechanics doc, the quadratic scoring formula:

```
S(v, s) = ((v - s) / v)^2 × b

Where:
v = qualifying spread parameter (Polymarket sets this per market, typically 3 cents)
s = your spread from adjusted midpoint (distance of your order from mid)
b = your order size in shares

Key insight: The reward is QUADRATIC in spread distance.
- At s=0 (quoting exactly at mid): S = b (maximum reward, maximum adverse selection risk)
- At s=1 cent: S = ((3-1)/3)^2 × b = 0.444 × b
- At s=2 cents: S = ((3-2)/3)^2 × b = 0.111 × b
- At s=3 cents (max): S = 0 (no reward)
```

**Calculate**: Given a total LP rewards pool of $12M/year distributed proportionally:

1. What fraction of the total reward pool can a $10K maker capture by quoting tightly on 5 markets?
2. What is the optimal spread to maximise (spread_revenue + LP_rewards - inventory_risk)?
3. Is there a sweet spot between "tight enough to earn rewards" and "not so tight that adverse selection destroys you"?

### 1c. Maker Rebates (Fee-Enabled Markets)

Fee-enabled markets (crypto price targets, some sports): takers pay a fee, makers earn a rebate.

**Fee structure** (from research):
```
fee = C × feeRate × (p × (1-p))^exponent
```

At p=0.50 on a crypto market, the effective taker fee ≈ 1.56%.
Makers receive 20-25% of taker fees.

For T008 (BTC $150K NO) and any future CRY positions:
- What is the maker rebate on this market if we quote on both sides?
- At $75 capital with realistic volume, what's the annual rebate yield?

### 1d. The Combined Yield Model

Build a table:

| Capital | Markets | Avg Spread Quoted | Fill Rate | Daily Spread Rev | Daily LP Rev | Annual Yield | Directional Risk |
|---------|---------|-------------------|-----------|------------------|--------------|--------------|------------------|
| $1,000 | 5 active | 2 cents | 30% | $? | $? | ?% | Low |
| $5,000 | 10 active | 1.5 cents | 30% | $? | $? | ?% | Medium |
| $10,000 | 20 active | 1 cent | 25% | $? | $? | ?% | Higher |

**The core question**: At what capital level does market making on Polymarket become worth doing as a standalone yield strategy vs. simply deploying into 3-month T-bills at ~5.3% annualised?

---

## Task 2: Market Selection for Making

Not all markets are worth making. Criteria:

### 2a. Good Markets for Making

- **High daily volume** (>$100K/day): more fill opportunities, more LP rewards
- **Slow-moving underlying** (probability changes slowly): low inventory risk
- **Clear resolution criteria**: no oracle risk
- **Time to resolution**: long enough that delta doesn't move much daily
- **Not bot-dominated**: if bots are making the market at 0.1 cent spreads, your 2 cent quotes get no fills

**Best candidates** (from our domain research):
- Fed rate decision markets: clear resolution, slow-moving, high volume
- 2028 presidential markets: very long duration, stable probabilities
- Iran multi-window markets: high volume, but HIGH delta risk (not ideal for making)

**Worst candidates** for making:
- Short-term crypto price targets: extreme volatility = severe inventory risk
- Markets with imminent catalyst events (election day, FOMC day): spreads widen, bots dominate
- Low-volume niche markets: can't earn LP rewards, no fills

### 2b. The Two-Sided Quoting Requirement

From the quadratic formula: two-sided quoting earns 3× more than one-sided quoting at probabilities 0.10-0.90.

**The risk**: If you quote both sides on a directional market (one you have a view on), you might "double dip" — your making loses on the directional move even as it earns from spreads.

**Solution**: Only make markets where you have NO directional view. Or: make on markets where your directional edge (S004, S006, S008) is LESS THAN the spread yield expected.

**Practical rule**: If expected LP yield on a market > 3× the directional edge, consider making rather than taking.

---

## Task 3: Inventory Risk Management

The key operational risk for market makers: **inventory accumulation** when the market trends against you.

### 3a. The Inventory Problem

Example: You quote BID at $0.58, ASK at $0.62 on a market at $0.60.
- Market rallies to $0.70 over 3 days.
- You accumulated 2,000 NO shares (someone kept selling to your $0.58 bid) = $1,160 inventory.
- Now those NO shares are worth $0.30 each = $600 = $560 loss.
- This wipes out weeks of spread revenue.

**Inventory management techniques:**
1. **Delta hedging**: Buy the opposite side as you accumulate (flattens inventory at cost of spreads)
2. **Skewing quotes**: If you're long NO (too much inventory), widen the NO bid and tighten the YES bid
3. **Hard limit**: Stop quoting when inventory exceeds $X
4. **Correlation hedging**: If you're making Iran markets, hedge with Venezuela/GEO exposure on the other side

**Research**: What inventory management techniques work in practice on thin prediction markets?

### 3b. The Safe Markets

Identify markets where inventory risk is LOWEST:
- Very high-probability markets (>95% YES): prices barely move, inventory risk minimal
- Short-duration markets with no pending catalyst: no sudden moves expected
- Markets where you're correlated to other existing positions (natural hedge)

**Practical screen**: For market making candidates, run:
- Average daily price move (standard deviation of daily price changes)
- If daily move < 0.5%, inventory risk is low → good making candidate
- If daily move > 2%, inventory risk is high → making is risky without hedging

---

## Task 4: The "Harvest Mode" Strategy

When one of our directional positions (T001-T008) gets close to resolution (>90% YES/NO), switch from holding to **market making around the near-certain price**.

**Mechanics**:
1. T001 (Iran Jun 30 NO) currently at 70.5% YES (29.5% NO)
2. If talks succeed and NO reaches 90%, switch: become a maker at 89.5/90.5 bid/ask
3. Earn spread income while waiting for the final 10% to resolve
4. Exit the maker position the day before resolution to avoid the MOOV2 process

**Why this works near resolution**:
- At 90%+ probability, price barely moves → minimal inventory risk
- LP rewards are available even on one-sided markets (<0.10 or >0.90) though at 1/3 efficiency
- Small spread × high certainty = reliable yield while waiting

**This is S011 (Bond Rotation) combined with making**. Formalize it.

---

## Task 5: Practical Implementation

### 5a. The Making Stack

What do you need to execute this strategy?

**Minimum viable:**
- Polymarket API key (for order placement)
- Python script to monitor inventory and adjust quotes
- Manual monitoring 2× per day

**Full automation:**
- Bot that quotes continuously, adjusts for inventory, skews for delta
- WebSocket connection to CLOB for real-time order book updates
- Alert system when inventory exceeds limits

### 5b. Capital Allocation Decision

Given our current portfolio ($1,685 deployed, $8,315 available):

- Is market making a better use of the $8,315 reserve than keeping it idle?
- Tradeoff: making earns ~15-30% annualised in ideal conditions, vs. 5.3% in T-bills, vs. holding for opportunistic directional entries
- Recommendation: how much capital (if any) should we allocate to making?

**Specific proposal**: Run a small pilot.
- Select 3 markets with characteristics from Task 2a
- Allocate $300 total (3× $100)
- Quote at 1.5 cent spread on each side
- Run for 2 weeks, measure actual yield
- Scale or abandon based on results

Create this pilot plan with specific markets identified.

---

## Output

1. `~/Desktop/prediction-markets/strategies/playbooks/P04-marketmaker-yield.md` — strategy playbook
2. `~/Desktop/prediction-markets/scripts/mm-yield-calculator.py` — the P&L model script
3. Terminal output of yield model at $1K, $5K, $10K capital
4. Pilot plan: 3 specific markets to make in the next 2 weeks
5. Add to `~/Desktop/prediction-markets/strategies/evolution/strategy-domain-matrix.md`: a "Making Suitability" column for each domain

**The core question to answer explicitly**: Is market making on Polymarket worth doing at our capital level ($8K available), or should we only use the reserve for directional opportunities? Give a direct recommendation with numbers.
