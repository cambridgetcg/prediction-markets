# NegRisk Mathematics: Complete Derivation

**Date**: 2026-02-25
**Purpose**: Mathematical foundation for P01 (NegRisk Structural Arbitrage) strategy
**Sources**: Polymarket docs, neg-risk-ctf-adapter source, Bawa (2025), IMDEA (2025)

---

## 1. Setup and Definitions

A **NegRisk market** consists of N mutually exclusive outcomes {O₁, O₂, ..., Oₙ} where exactly one outcome resolves YES. Each outcome is a binary market with:

- YES share price: pᵢ (market's implied probability of Oᵢ)
- NO share price: (1 - pᵢ)
- Constraint per market: YES_i + NO_i = $1.00

**The fundamental constraint**: Since exactly one outcome wins:

```
Theoretical: Σ pᵢ = 1.00  (all YES prices sum to $1.00)
Actual:      Σ pᵢ = 1.00 + ε  (where ε is the overround/underround)
```

When ε > 0: **overround** (market overpriced overall)
When ε < 0: **underround** (market underpriced overall)

**Contract addresses** (Polygon mainnet):
- NegRiskAdapter: `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296`
- NegRisk CTF Exchange: `0xC5d563A36AE78145C45a50134d48A1215220f80a`
- WrappedCollateral: deployed per-market by adapter

---

## 2. The Convert Operation (1a)

### 2.1 Mechanism

The `convertPositions(marketId, indexSet, amount)` function:

**Inputs:**
- `marketId`: identifies the multi-outcome event
- `indexSet`: bitmask of which outcomes' NO tokens to convert
- `amount`: quantity per position

**Outputs:**
- YES tokens in all complementary outcomes (those NOT in indexSet)
- Released USDC collateral: `(m - 1) × amountOut` where m = number of set bits in indexSet

**Fee deduction:**
```
feeAmount = amount × feeBips / 10,000
amountOut = amount - feeAmount
```

### 2.2 Single NO → All Other YES

The simplest case. You hold 1 NO share in outcome i.

**Cost of 1 NO_i**: `(1 - pᵢ)` dollars

**After convert()**: You receive 1 YES share in every outcome j ≠ i.

**Value of received YES shares**: `Σⱼ≠ᵢ pⱼ = (Σ pⱼ for all j) - pᵢ`

**Profit condition** (ignoring fees):
```
Value received > Cost paid
Σ pⱼ - pᵢ > 1 - pᵢ
Σ pⱼ > 1.00
```

**The convert is profitable if and only if the total YES price sum exceeds $1.00 (overround exists).**

The profit per unit is exactly equal to the overround:
```
Profit = (Σ pⱼ - pᵢ) - (1 - pᵢ) = Σ pⱼ - 1 = ε
```

### 2.3 Multiple NO → Complementary YES + Collateral

Converting m NO positions (m ≥ 2) via indexSet:

**Cost**: `Σᵢ∈S (1 - pᵢ)` where S is the set of outcomes whose NO you bought

**Receive**:
- `amountOut` YES tokens per complementary outcome
- `(m - 1) × amountOut` USDC collateral

**Why (m-1)?** Consider holding NO in m outcomes. If any of those m outcomes wins, you lose that NO (worth $0) but keep the other (m-1) NOs (each worth $1). So the guaranteed floor is (m-1) × $1 = (m-1) collateral. The convert() atomically extracts this guaranteed value.

**Concrete example — 5-outcome market (A, B, C, D, E):**

Buy 100 NO shares in A, B, C (m=3):
```
Cost: 100×(1-pₐ) + 100×(1-p_b) + 100×(1-p_c)

If pₐ=0.40, p_b=0.25, p_c=0.20, p_d=0.10, p_e=0.08:
Cost = 100×0.60 + 100×0.75 + 100×0.80 = $215.00
Σ pᵢ = 1.03 (3% overround)

convert(indexSet=0b00111, amount=100):
  feeAmount = 100 × 200 / 10000 = 2  (assume 2% = 200 bips)
  amountOut = 98
  Collateral released: (3-1) × 98 = $196
  YES-D tokens: 98 (worth 98 × $0.10 = $9.80)
  YES-E tokens: 98 (worth 98 × $0.08 = $7.84)

Total value received: $196 + $9.80 + $7.84 = $213.64

Profit: $213.64 - $215.00 = -$1.36 (LOSS in this case)
```

Wait — why negative? Because the 2% conversion fee ate the 3% edge. Let's recalculate the breakeven.

### 2.4 Breakeven After Fees

**The 2% winner fee** applies at resolution (on winning YES tokens), not on the convert itself. The conversion fee (feeBips) is separate and per-market.

For the **buy-NO-and-convert** play:

```
Cost:           Σᵢ∈S (1 - pᵢ) per unit
Receive:        (m-1) × amountOut collateral + amountOut × Σⱼ∉S pⱼ in YES tokens
Fee on convert: amount × feeBips / 10000 (applied to both collateral and YES)
Fee at resolution: 2% of winning YES payout (the $1.00 per winning share)
```

**For the simplest overround play** (sell all YES = buy all NO):

Buy 1 NO in every outcome. Cost: `Σ(1 - pᵢ) = N - Σ pᵢ = N - 1 - ε`

At resolution, exactly one outcome resolves YES. Your NO on that outcome is worth $0. Your (N-1) NOs on losing outcomes are each worth $1.00.

**Payout**: `(N-1) × $1.00 = N - 1`

But wait — NO shares pay $1.00 when their outcome loses. **There is no winner fee on NO shares** (the fee is on YES winners only). So:

```
Profit = (N-1) - (N - 1 - ε) = ε
```

**Breakeven for NO-based overround play: ε > 0 (any overround is profitable, ignoring spread/slippage).**

This is crucial: the overround play using NO shares avoids the 2% winner fee entirely, because NO shares that resolve to $1.00 are the "losing" side of the market (the outcome didn't happen). The fee applies to YES winners.

**Correction**: Actually, on Polymarket, the 2% fee may apply differently. Let me re-derive.

### 2.5 Fee Structure Clarification

Polymarket's fee model (as of Feb 2026):

1. **Trading fee**: Zero on most markets (only fee-enabled on crypto/sports)
2. **Winner fee**: 2% on profits from winning positions at resolution
   - Applied to: `(payout - cost_basis)` on the winning side
   - NO shares that pay $1.00 ARE subject to fee on the profit portion
3. **Convert fee**: Per-market feeBips in the NegRiskAdapter contract

**For the overround play**:

Buying all NO shares. Cost per NO_i = (1 - pᵢ). At resolution, losing NOs = $0, winning NOs = $1.00.

Your winning NOs (on the N-1 outcomes that resolved NO): each paid $(1-pᵢ)$, receives $1.00.
Profit per winning NO: $1.00 - (1 - pᵢ) = pᵢ$
Fee per winning NO: 2% × pᵢ

Wait — but you can't know in advance which outcome wins. The point is you hold ALL NOs, so (N-1) of them win.

```
Total cost:   Σᵢ (1 - pᵢ) = N - Σ pᵢ
Total payout: (N-1) × $1.00  (the N-1 losing outcomes)
Total profit before fee: (N-1) - (N - Σ pᵢ) = Σ pᵢ - 1 = ε
Fee: 2% × total profit = 0.02 × ε  (NO — this isn't right either)
```

The 2% fee is on the PROFIT of each winning share:

```
Winning NO_j (for j ≠ winner): cost = (1 - pⱼ), payout = $1.00
  Profit per share: pⱼ
  Fee per share: 0.02 × pⱼ

Total fee: 0.02 × Σⱼ≠w pⱼ  (where w is the winning outcome)
         = 0.02 × (Σ pⱼ - p_w)

Net profit: ε - 0.02 × (Σ pⱼ - p_w)
          = ε - 0.02 × (1 + ε - p_w)
```

This depends on WHICH outcome wins. **Worst case** (the cheapest outcome wins, maximizing the fee base):

```
p_w = min(pᵢ)  →  fee base = Σ pⱼ - min(pᵢ) is maximized
Net profit (worst case) = ε - 0.02 × (1 + ε - p_min)
```

For ε = 0.03 (3% overround) and p_min = 0.01 (longshot wins):
```
Net profit = 0.03 - 0.02 × (1.03 - 0.01) = 0.03 - 0.0204 = 0.0096 (0.96%)
```

For ε = 0.03 and p_min = 0.40 (favorite wins):
```
Net profit = 0.03 - 0.02 × (1.03 - 0.40) = 0.03 - 0.0126 = 0.0174 (1.74%)
```

**Breakeven overround** (worst case, longshot wins):
```
ε - 0.02 × (1 + ε - p_min) > 0
ε - 0.02 - 0.02ε + 0.02×p_min > 0
0.98ε > 0.02 - 0.02×p_min
ε > (0.02 - 0.02×p_min) / 0.98
```

With p_min ≈ 0: ε > 0.02/0.98 = **2.04%**
With p_min = 0.05: ε > 0.019/0.98 = **1.94%**
With p_min = 0.10: ε > 0.018/0.98 = **1.84%**

**Summary**: Breakeven overround for the buy-all-NO play is approximately **2.0%** in the worst case (longshot wins), declining slightly when the winning outcome has higher probability.

### 2.6 Practical Breakeven Including Spread

Each NO purchase incurs half the bid-ask spread. With N outcomes:

```
Spread cost = N × (spread / 2)
```

For N=10 outcomes with 2-cent average spread:
```
Spread cost = 10 × $0.01 = $0.10 per $1.00 of position = 10%
```

This is enormous. It means **overround plays on wide-spread markets are unprofitable** unless:
1. You use limit orders (zero spread cost, but execution risk)
2. The overround exceeds spread cost + fee cost
3. Some outcomes have tight spreads (high volume favorites)

**Effective breakeven**:
```
ε > 2.0% + (N × avg_spread / 2)
```

For liquid markets (1-cent spread, 10 outcomes): ε > 2.0% + 5% = **7.0%**
For tight markets (0.5-cent spread, 5 outcomes): ε > 2.0% + 1.25% = **3.25%**

This explains why the S007 analysis found 3% thresholds practical only for relatively concentrated markets.

---

## 3. The Reverse Convert / Buy-All-YES (1b)

### 3.1 Mechanism

When Σ pᵢ < 1.00 (underround), buy YES in every outcome:

```
Cost:    Σ pᵢ = 1 - |ε| < $1.00
Payout:  $1.00 (exactly one outcome wins)
Profit:  1 - Σ pᵢ = |ε|
```

### 3.2 Presidential 2028 Example (from S007 data)

S007 analysis found: Presidential Election Winner 2028 has 3.0% underround.

```
35 candidates, total YES prices = $0.970
  JD Vance:      25.55%
  Josh Shapiro:   2.45%
  Gavin Newsom:   2.30%
  ... 32 more candidates

Cost to buy 1 YES in all 35: $0.970
Guaranteed payout: $1.000 (one must win)
Gross edge: $0.030 (3.1%)
```

**Fee calculation**:

Winner fee applies to the profit on the ONE winning YES share:
- Winning share paid pᵢ, receives $1.00
- Profit: $1.00 - pᵢ
- Fee: 0.02 × ($1.00 - pᵢ)

But you also have 34 losing YES shares (each worth $0):
- Net loss on losing shares: Σⱼ≠w pⱼ = 0.970 - p_w

**Total P&L**:
```
Revenue:  $1.00 (winning share)
Cost:     $0.970 (all shares)
Gross:    $0.030
Fee:      0.02 × (1.00 - p_w)

If Vance wins (p_w = 0.2555):
  Fee = 0.02 × 0.7445 = $0.01489
  Net = 0.030 - 0.01489 = $0.01511 (1.56%)

If a longshot wins (p_w = 0.005):
  Fee = 0.02 × 0.995 = $0.01990
  Net = 0.030 - 0.01990 = $0.01010 (1.04%)
```

**Expected net** (probability-weighted):
```
E[net] = 0.030 - 0.02 × E[1 - p_w]
       = 0.030 - 0.02 × (1 - E[p_w])
```

Where E[p_w] = Σ pᵢ² / Σ pᵢ (the probability-weighted average winning price):
```
E[p_w] = (0.2555² + 0.0245² + ... ) / 0.970

Dominated by Vance: ≈ 0.2555²/0.970 ≈ 0.0673
Plus smaller terms: ≈ 0.08 total

E[net] ≈ 0.030 - 0.02 × (1 - 0.08) = 0.030 - 0.0184 = 0.0116 (1.2%)
```

**Annualized**: Market resolves November 2028 (~33 months). Annual return = 1.2% / 2.75 years = **0.44% per year**. This is terrible — worse than Treasury bills.

**The Presidential 2028 underround is NOT worth trading.** Capital is locked for 2.75 years for 1.2% total return. The 3% gross edge is illusory after fees and time value.

### 3.3 Breakeven for Buy-All-YES

```
|ε| - 0.02 × (1 - E[p_w]) > 0
|ε| > 0.02 × (1 - E[p_w])
```

For concentrated markets (one strong favorite, E[p_w] ≈ 0.30): |ε| > 1.4%
For diffuse markets (many candidates, E[p_w] ≈ 0.08): |ε| > 1.84%

**Practical breakeven: ~2% underround minimum**, same ballpark as overround plays.

### 3.4 When Buy-All-YES Works

Short-duration markets with significant underround:
```
Required: |ε| > 2% AND resolution within 30 days
Annualized: 1% net × (365/30) = 12.2% — now worth it
```

The S007 data shows sports events often have 1-2% underround with weekly resolution. At scale, this could compound meaningfully.

---

## 4. NegRisk Rebalancing: The $40M Mechanism (1c)

### 4.1 How Rebalancing Works

**Starting state**: 5-outcome market at equilibrium. Prices: [0.40, 0.25, 0.20, 0.10, 0.05]. Sum = 1.00.

**Event**: A news article favors Candidate A. Traders buy YES-A aggressively.

**New prices**: [0.52, 0.25, 0.20, 0.10, 0.05]. Sum = 1.12 (+12% overround).

**The rebalancing trade**:

Step 1: Buy NO in ALL outcomes (total cost = N - Σ pᵢ = 5 - 1.12 = $3.88 per unit)
Step 2: Convert all NOs → releases collateral + residual YES tokens
Step 3: Sell residual YES tokens (or hold for resolution)

OR (more practically):

Step 1: Buy NO-A specifically (cheapest at 1 - 0.52 = $0.48)
Step 2: Convert NO-A → get YES in B, C, D, E
Step 3: Sell YES-B at 0.25, YES-C at 0.20, YES-D at 0.10, YES-E at 0.05
Step 4: Revenue from sales: 0.25 + 0.20 + 0.10 + 0.05 = $0.60
Step 5: Profit: $0.60 - $0.48 = $0.12 (minus fees)

**This is the core loop.** When YES-A spikes, NO-A gets cheap, and converting NO-A into YES tokens for all other outcomes captures the overround.

### 4.2 Why It Was Profitable at Scale in 2024-2025

**Three factors converged:**

1. **Massive retail flow during US election** ($3.7B+ total volume). Retail overwhelmingly buys YES on their favored candidate, creating persistent overrounds. The 2024 presidential race had Σ pᵢ regularly at 1.05-1.15 during volatile periods.

2. **Fragmented counterparty base**. In traditional markets, the market maker adjusts all related prices simultaneously. On Polymarket, each outcome's order book is independent. When someone buys $100K of YES-Trump, no automated mechanism instantly adjusts YES-Harris downward. This creates lag.

3. **Capital efficiency of NegRisk**. Converting NO → YES across all outcomes costs only the NO price, not the sum of all YES prices. A $10K rebalancing trade captures the same edge that would require $50K+ in separate binary markets.

**Why bots capture it now**: The rebalancing window compressed from 12.3 seconds (2024) to 2.7 seconds (2025) as more bots monitored the sum of YES prices and executed convert trades within milliseconds. The most sophisticated bots execute in under 100ms, capturing 73% of all profits.

### 4.3 Slow Rebalancing Markets

**Markets where manual rebalancing may still be viable:**

| Market Type | Why Slow | Evidence |
|---|---|---|
| **Low-volume niche** (<$50K total) | Below bot monitoring thresholds | 78% failed execution in low-vol (IMDEA) |
| **Newly listed** (first hours) | Bots haven't indexed the conditionIds yet | Window: minutes to hours |
| **Many outcomes** (>15 candidates) | More legs = more execution complexity for bots | Tail outcomes often stale-priced |
| **Non-US politics** | Fewer bots monitoring, lower total interest | GEO-restricted regions especially |
| **Event-driven spikes** | Sudden news creates multi-minute windows | Polling releases, debate moments |
| **SCI/ENV/SOC domains** | Low bot coverage — crypto/POL/sports are primary bot targets | No documented bot activity |

**The key heuristic**: If a market has <$5K daily volume and >15 outcomes, the rebalancing window is likely minutes to hours, not seconds.

---

## 5. The Size-Speed Tradeoff (1d)

### 5.1 Bot Economics

Bots optimize for: `Profit = Σ (edge × size) / time`

This means bots preferentially target:
- **High-volume markets** (more available liquidity to capture per trade)
- **Liquid order books** (less slippage on larger positions)
- **Popular events** (more frequent imbalances from retail flow)

Bots have **minimum viable position size** due to:
- Gas costs on Polygon: ~$0.01-0.10 per transaction
- Monitoring costs: VPS, RPC nodes, API queries
- Convert() gas: ~200K-500K gas units ($0.10-0.50)

### 5.2 The Bot Threshold

Based on the IMDEA data:

```
Minimum profitable bot trade ≈ $50-100 (covers gas + monitoring amortization)
Minimum market size for bot monitoring ≈ $10K-50K total volume
```

Markets below these thresholds are in the **"bot dead zone"** — too small for infrastructure investment.

**However**: 78% of executions in low-volume markets fail. The order books are so thin that:
- Limit orders don't get filled (no counterparty)
- Market orders face 5-20% slippage
- The edge disappears before execution completes

### 5.3 The Manual Trader Sweet Spot

```
Market characteristics for manual NegRisk plays:

Volume:    $10K - $100K (above trivial, below bot-heavy)
Outcomes:  5-20 (enough for meaningful overround, not so many as to have all-stale tails)
Overround: >5% (covers fee + spread + execution friction)
Domain:    POL, GEO (most overround), NOT ECO (perfectly priced)
Age:       First 24-48 hours after listing (indexing lag)
Event:     Post-news-catalyst (multi-minute window)
```

### 5.4 Annual Opportunity Estimation

From IMDEA data:
- ~8.6% of arbitrage opportunities were NegRisk (vs binary)
- $29M extracted from NegRisk in 12 months by ALL traders
- Top 10 accounts captured $8.18M (28%)
- Manual-accessible fraction (slow markets): ~5% of total opportunities

```
Estimated manual-accessible annual NegRisk arb:
$29M × 5% manual-accessible = $1.45M total addressable
At 1-5% capture rate (one manual trader among many): $14.5K - $72.5K/year

Reality check: 5-10 opportunities per month × $250-$1,000 per = $15K-$120K/year
```

This aligns with the "semi-automated" return estimate from research sources.

---

## 6. Summary of Mathematical Results

| Metric | Formula | Value |
|---|---|---|
| **Overround edge** | ε = Σ pᵢ - 1 | Raw edge per $1 position |
| **Breakeven overround** (buy all NO) | ε > 0.02 / 0.98 | ~2.04% minimum |
| **Breakeven underround** (buy all YES) | \|ε\| > 0.02 × (1 - E[p_w]) | ~1.4-1.8% minimum |
| **Practical minimum** (incl. spread) | ε > 2% + N × spread / 2 | ~3-7% for typical markets |
| **Convert fee** | amount × feeBips / 10000 | Per-market, typically 2% |
| **Collateral release** (m NOs) | (m-1) × amountOut | Guaranteed floor extraction |
| **Rebalancing profit** (single NO convert) | Σⱼ≠ᵢ pⱼ - (1-pᵢ) = ε | Equals the overround |
| **Opportunity window** | | 2.7s avg (bots), minutes-hours (niche) |
| **Annual addressable (manual)** | | $15K-$120K estimated |

---

## References

- Polymarket NegRisk Docs: docs.polymarket.com/developers/neg-risk/overview
- NegRisk CTF Adapter Source: github.com/Polymarket/neg-risk-ctf-adapter
- Bawa, N. (2025). "NegRisk Market Rebalancing: How $29M Was Extracted." Medium.
- Saguillo et al. (2025). "Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets." IMDEA/arXiv.
- S007 analysis: strategies/backtests/S007-arb-analysis.md
- Polymarket structural mechanics: research/polymarket-structural-mechanics.md
