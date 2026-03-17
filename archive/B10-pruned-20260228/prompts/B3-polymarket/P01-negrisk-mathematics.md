You are a quantitative researcher building a systematic strategy around Polymarket's NegRisk multi-outcome market structure — the mechanism that generated $40M in arbitrage profit in 2024-2025 and still offers structural edges that retail participants cannot exploit.

## Read First

1. ~/Desktop/prediction-markets/research/polymarket-structural-mechanics.md — sections 3-4 (NegRisk mechanics, current state)
2. ~/Desktop/prediction-markets/strategies/backtests/S007-arb-analysis.md — current Type 1 overround work
3. ~/Desktop/prediction-markets/strategies/evolution/new-strategy-research.md — S009 identification

## Background

The NegRiskAdapter is Polymarket's key structural innovation for multi-outcome markets. In a standard Polymarket binary market, YES + NO = $1.00 (trivially). In a NegRisk market with N outcomes:

```
Each outcome: YES_i + NO_i = $1.00 (binary constraint per outcome)

But also:
Exactly one outcome will be YES → sum(YES_i) should equal $1.00

This creates: sum(NO_i) should equal (N - 1) dollars

The convert() function: 1 NO share in any outcome = 1 YES share in EVERY OTHER outcome
```

When `sum(YES_i) ≠ $1.00`, the NegRiskAdapter makes exploitation cheap.

---

## Task 1: The Mathematics

Work through the NegRisk mathematics from scratch. Document in full:

### 1a. The Convert Operation

Given a market with N outcomes (candidates in a race):
- NO share in outcome i costs: (1 - price_i)
- After convert(), it becomes YES shares in outcomes j≠i

**When is convert() profitable?**
- You hold 1 NO share in outcome i (cost: 1 - p_i)
- After convert: you hold YES shares in all other outcomes (N-1 shares)
- These are worth: sum(p_j for j ≠ i) = sum(p_j for all j) - p_i

**Profit condition**: sum(all YES prices) - p_i > (1 - p_i)
Simplifies to: **sum(all YES prices) > 1.00**

When total YES prices exceed $1.00 (overround), buying NO in the lowest-priced outcome and converting is profitable.

**Calculate the breakeven**: What total YES price sum is needed to profit after the 2% winner fee?

### 1b. The Reverse Convert

When total YES prices < $1.00 (underround):
- Buy YES in multiple outcomes for < $1.00 total
- At resolution, exactly one pays $1.00
- If underround > 2% winner fee, this is a "buy everything" guaranteed profit

**From S007 analysis**: The 2028 Presidential race has a 3.0% underround. Calculate the exact trade structure and profit, accounting for the winner fee.

### 1c. NegRisk Rebalancing (The $40M Mechanism)

The biggest opportunity is not the initial convert but the **ongoing imbalance**. When new participants trade a multi-outcome market:
- A large YES purchase on candidate X pushes X's price up
- This creates an imbalance: sum(YES) > $1.00
- The convert mechanism makes it cheap to rebalance

**Research questions**:
1. How does a NegRisk rebalancing trade actually work? Walk through a concrete example.
2. Why was this profitable at scale in 2024-2025 when bots now capture it in 2.7 seconds?
3. Are there any NegRisk markets where manual rebalancing is still viable?
   - Answer: Yes — markets with LONGER REBALANCING WINDOWS than average. Which market types rebalance slowly?

### 1d. The Size-Speed Tradeoff

The $40M was dominated by bots. But bots optimise for SIZE × SPEED on the most liquid markets. This creates an opportunity at the OTHER end:

- Low-volume, niche multi-outcome markets
- Where imbalances persist longer (no bot monitoring)
- Where the dollar amounts are small enough that bots don't bother

**Research**: What is the minimum dollar imbalance that activates arbitrage bots? (If it's $5K, then markets with <$5K total YES imbalance may still be manually exploitable.)

---

## Task 2: Scanning for Current NegRisk Opportunities

### 2a. Build the Scanner

Write a Python script to:
```python
# ~/Desktop/prediction-markets/scripts/negrisk-scanner.py

# 1. Fetch all multi-outcome events from Gamma API
import requests

events = requests.get("https://gamma-api.polymarket.com/events?limit=100&multi_outcome=true").json()

# 2. For each event, calculate:
#    - sum(YES prices) across all active outcomes
#    - Overround = sum(YES) - 1.00
#    - Underround = 1.00 - sum(YES) [when negative overround]
#    - Total liquidity
#    - 24h volume

# 3. Flag:
#    - Any market with overround > 2.5% (convert() is profitable after fees)
#    - Any market with underround > 2.5% (buy-all-YES is profitable after fees)
#    - Sort by: |overround| × liquidity (highest dollar opportunity first)

# 4. For top 10 opportunities, fetch full order book:
#    - Available shares at each price level
#    - Maximum exploitable position before price impact exceeds edge

# 5. Output: formatted table with opportunity size in dollars
```

Run it. Report the findings.

### 2b. Analyse the Results

For each opportunity found:
- Is this a genuine edge or a stale pricing artifact (illiquid outcome, no recent trades)?
- What is the ACTUAL exploitable dollar amount after considering order book depth?
- Is this a bot-detectable opportunity (would it be captured in <3 seconds)?
- Does it require blockchain operations (convert()) or just trading?

---

## Task 3: The Residual Edge Framework

Given that high-frequency NegRisk arb is dominated by bots, where does residual edge live?

### 3a. Slow Markets

Some multi-outcome markets are structurally slow to reprice:
- **Very long duration** (>6 months) with low daily volume — bots have less incentive to monitor
- **Low absolute dollar value** (<$50K total) — below bot attention thresholds
- **Newly created** — bots haven't indexed them yet (window: minutes to hours)
- **Niche domains** — SCI, ENV, SOC — less bot coverage than GEO, POL, CRY

**Task**: From the scanner output, identify which category most opportunities fall into.

### 3b. Structural Convert Plays

Even without imbalance, there are NegRisk plays available to patient traders:

**The "Cheap NO bundle"**: Buy NO in multiple outcomes for less than the per-share cost of buying YES in each. Hold; if any outcome you're NOT holding wins, your combined NOs profit.

**The "Reverse field"**: In a race with 20+ candidates, buying NO on the top 3 candidates is equivalent to buying YES on the field (all others). If "field" is underpriced vs the top-3 combined, this is the trade.

**Research**: Are there any current Polymarket markets where the "field" (NO on top candidates combined) is cheaper than its probability suggests?

---

## Task 4: Strategy P01 Formalisation

Write a formal strategy playbook:

**P01 — NegRisk Structural Arbitrage**

Document:
- Entry criteria (overround threshold, minimum liquidity, maximum bot speed)
- The two trade types: (a) convert() play, (b) buy-all-YES underround play
- Position sizing (no Kelly needed — risk-free, but capped by order book depth)
- Execution: limit orders only, which order to fill first (maximize fill probability)
- The "slow market" screen: how to find opportunities bots don't see
- Risk factors: stale pricing artifacts, oracle resolution for multi-outcome markets
- Expected return range: X% per opportunity, Y opportunities per week/month

---

## Output

1. `~/Desktop/prediction-markets/strategies/playbooks/P01-negrisk-arb.md` — the full strategy playbook
2. `~/Desktop/prediction-markets/scripts/negrisk-scanner.py` — working scanner script
3. Terminal output of scanner results (what did you find today?)
4. Mathematical derivation document: `~/Desktop/prediction-markets/research/negrisk-mathematics.md`

**Key sources to research:**
- https://docs.polymarket.com/developers/neg-risk/overview
- https://github.com/Polymarket/neg-risk-ctf-adapter (source code)
- "NegRisk Market Rebalancing: How $29M Was Extracted" (Medium, Navnoor Bawa)
- Any academic papers on multi-outcome binary prediction markets

**Expected finding**: The $40M-per-year opportunity is largely gone for manual traders. But in niche/slow markets with overround >2.5% and <$5K daily volume, manual plays still exist. Document the realistic annual return available from this strategy at our capital scale.
