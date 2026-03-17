# Polymarket Structural Mechanics: Technical Research

**Date**: 2026-02-23
**Purpose**: Detailed technical analysis of Polymarket infrastructure mechanics that create trading strategy opportunities.

---

## 1. Order Book Mechanics (CLOB)

### Architecture: Hybrid-Decentralized

Polymarket's CLOB (Central Limit Order Book) is **hybrid-decentralized**:
- **Off-chain**: An operator matches and orders trades for speed
- **On-chain**: Settlement executes on Polygon via audited Exchange smart contract
- **Signing**: All orders use EIP-712 typed data signing
- **Settlement**: Atomic swaps of outcome tokens for USDC collateral, non-custodial

The operator's privileges are **strictly limited** to:
- Order matching
- Non-censorship guarantee
- Correct ordering
- **Cannot** set prices or execute unauthorized trades

### Matching Engine

**Price-time priority** with a **unified order book**:
- Every BUY order for Outcome YES at price X is simultaneously visible as a SELL order for Outcome NO at price (1.00 - X)
- This mirroring creates deeper liquidity and tighter spreads than separate order books
- Three settlement types:
  - **Direct Match**: User-to-user trade (no minting/burning)
  - **Minting**: New shares created when orders for opposite outcomes match (1 USDC -> 1 YES + 1 NO)
  - **Merging**: Shares burned when opposite sell orders match (1 YES + 1 NO -> 1 USDC)

### Order Types

| Type | Behavior |
|------|----------|
| **Limit Order (GTC)** | Rests on book until filled or cancelled |
| **Market Order (FOK)** | Fill-or-Kill: execute immediately at specified price or better; auto-cancels if full amount cannot be filled |

- **Slippage protection**: 5-cent tolerance on market orders vs. execution price
- **Minimum order size**: $1.00 USD for BUY orders (enforced before creation and after sizing)

### Tick Sizes

The CLOB supports multiple tick sizes per market:
- **0.1** (10 cents)
- **0.01** (1 cent) -- standard for most markets
- **0.001** (0.1 cent)
- **0.0001** (0.01 cent)

Tick sizes can change dynamically when markets become one-sided. Market orders have stricter precision (sell orders limited to 2 decimal places). The tick size for a specific market can be queried via `GET /tick-size`.

### Slippage Characteristics

Slippage on Polymarket is a function of:
1. **Order book depth** at the price level
2. **Order size** relative to available liquidity
3. **Unified book effect** -- mirrored orders increase effective depth
4. **Fill-or-Kill default** -- market orders won't partial-fill at worse prices

**Strategic implication**: Thin markets (low volume, niche topics) have significantly wider spreads and more slippage. The unified book structure means liquidity is better than it appears if you count both YES and NO sides.

### Key API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /price` | Best bid/ask for a token |
| `GET /book` | Full order book |
| `GET /midpoint` | Midpoint price |
| `GET /spread` | Current spread |
| `GET /tick-size` | Minimum price increment |
| `POST /order` | Place order (requires API key) |
| `DELETE /order` | Cancel order |

---

## 2. Market Making / Liquidity Provision

### Liquidity Rewards Program

Polymarket runs a **formal liquidity rewards program** that pays market makers for providing depth.

**2025 budget**: $12 million in total LP rewards allocated.

**Recent development (2026)**: Permissionless liquidity reward sponsorship -- anyone can now attach rewards to any market, paying traders to provide tight limit orders. Previously, only Polymarket chose which markets received incentives.

### Scoring Formula (Quadratic)

Rewards use the formula:

```
S(v, s) = ((v - s) / v)^2 * b
```

Where:
- **v** = qualifying spread parameter (max spread, e.g., 3 cents)
- **s** = your order's spread from the adjusted midpoint
- **b** = order size (number of shares)

**Key properties**:
- **Quadratic penalty** for wider spreads -- sitting far from midpoint is heavily penalized
- **Linear reward** for size -- larger orders get proportionally more
- **Two-sided bonus**: Score = min(bid_side_score, ask_side_score), so single-sided quoting scores much less
- Between 0.10-0.90 midpoint: single-sided orders permitted but score divided by 3.0
- Below 0.10 or above 0.90: only two-sided liquidity qualifies

### Reward Calculation Process

1. Orders scored every **1 minute** (10,080 samples per weekly epoch)
2. Q_min = min(bid_side_score, ask_side_score) per sample
3. Normalized across all participants per sample
4. Accumulated over epoch
5. Final distribution proportional to accumulated normalized score
6. Paid **daily at midnight UTC** in USDC
7. Minimum payout: $1

### Maker Rebates Program (New, 2026)

On fee-enabled markets, taker fees fund direct rebates to makers:

| Market Type | Launch Date | Rebate % of Taker Fees |
|-------------|------------|------------------------|
| 15-min crypto | Jan 19, 2026 | 20% |
| 5-min crypto | Feb 12, 2026 | 20% |
| NCAAB | Feb 18, 2026 | 25% |
| Serie A | Feb 18, 2026 | 25% |

Rebate formula: `your_rebate = (your_fee_equivalent / total_fee_equivalent) * rebate_pool`

### Typical Spreads and Returns

**Spreads** vary enormously by market:
- High-volume markets (elections, major events): 1-3 cent spreads
- Medium markets: 3-8 cent spreads
- Low-volume/niche markets: 10-30+ cent spreads

**Realistic returns** (as of late 2025 / early 2026):
- **Conservative**: ~10% annualized
- **Active market maker**: 5-15% monthly (60-180% annualized)
- **Rule of thumb**: ~0.2% of trading volume in profit ($1M monthly volume ~ $2,000 profit)
- **Peak historical**: $700-800/day on $10,000 capital (2024 election era) -- no longer achievable
- **Current**: Rewards declining, competition intensifying, treat rewards as bonus not primary income

### Open Source Market Making Bots

| Bot | Source | Status |
|-----|--------|--------|
| **poly-maker** (warproxxx) | [github.com/warproxxx/poly-maker](https://github.com/warproxxx/poly-maker) | Reference only -- author says "not profitable" in current market |
| **poly-market-maker** (Official) | [github.com/Polymarket/poly-market-maker](https://github.com/Polymarket/poly-market-maker) | Official Polymarket market maker keeper |
| **py-clob-client** | [github.com/Polymarket/py-clob-client](https://github.com/Polymarket/py-clob-client) | Python SDK for building custom bots |
| **rs-clob-client** | [github.com/Polymarket/rs-clob-client](https://github.com/Polymarket/rs-clob-client) | Rust SDK (lower latency) |

### Capital Requirements

- **Minimum viable**: $1,000-5,000 (small markets, limited diversification)
- **Recommended**: $10,000+ (multiple markets, risk diversification)
- **Professional**: $50,000-100,000+ (full-time MM across many markets)

---

## 3. Neg-Risk / Negative Risk Markets

### What Are Neg-Risk Markets?

Neg-risk markets are **multi-outcome prediction markets** where a set of mutually exclusive binary markets are unified into a single event structure. Exactly **one and only one** outcome will resolve YES.

**Examples**: "Who will win the 2028 Presidential Election?", "Which team will win the Super Bowl?"

Each outcome is still a binary YES/NO market, but the NegRiskAdapter contract relates them so that:
- Only one outcome resolves YES
- All others resolve NO
- Total probability across all YES shares should sum to ~$1.00

### Collateral System

**Standard markets**: Each market uses raw USDC as collateral independently.

**Neg-risk markets**: Use **WrappedCollateral** -- a specialized token that holds underlying USDC:
1. USDC is wrapped into WrappedCollateral
2. WrappedCollateral collateralizes all underlying binary markets
3. NegRiskAdapter manages the USDC separately from the ConditionalTokens (CTF) contract
4. Settlement still ultimately pays in USDC

### The Convert Mechanism

The core innovation: **A NO share in any market can be converted into 1 YES share in every other market** (and potentially some USDC back).

**Example -- 5-outcome market (A, B, C, D, E)**:
1. Buy 100 NO shares in markets A, B, C, D (cost: ~$400)
2. Call `convert()` on the NegRiskAdapter
3. Receive: 100 YES shares of market E + $300 USDC back
4. Net cost: $100 (equivalent to buying YES in E directly)

**Cash extraction rules**:
- Converting k NO positions where k >= 2 releases USDC equal to the "guaranteed floor" value
- Converting a single NO position swaps it for YES positions but releases no cash
- The adapter burns input NO tokens, calculates the guaranteed floor, and instructs WrappedCollateral to release corresponding USDC

### Capital Efficiency

| Scenario | Standard Markets | Neg-Risk Markets |
|----------|-----------------|-----------------|
| Buy all outcomes (9-outcome market) | Sum of all prices (~$1.018 if overpriced) | $1.00 maximum |
| Bet against one outcome | Buy YES in all others (expensive) | Buy single NO (cheap) |
| Collateral needed for portfolio | Sum of all positions | Shared collateral pool |

**The economic equivalence**: Betting against one outcome = betting for all other outcomes. This eliminates redundant collateral.

### Arbitrage and Structural Opportunities

#### Overround Arbitrage (Sum > $1.00)
If the sum of all YES prices exceeds $1.00:
- Buy NO in all outcomes (costs less than $1.00 total due to neg-risk)
- Guaranteed to receive $1.00 when one resolves YES
- Profit = $1.00 - total cost

**However**: After the 2% winner fee (on applicable markets) and gas, spreads need to exceed **2.5-3%** to be profitable.

#### Underround Arbitrage (Sum < $1.00)
If the sum of all YES prices is less than $1.00:
- Buy YES in every outcome
- One must resolve YES, paying $1.00
- Profit = $1.00 - total cost

#### NegRisk Market Rebalancing (The Big One)

**Research finding**: During April 2024 - April 2025, an estimated **$40 million in profit** was extracted through arbitrage on Polymarket. NegRisk market rebalancing generated **73% of total profits** despite representing only 8.6% of opportunities -- a **29x capital efficiency advantage** over binary arbitrage.

Two forms:
1. **Market Rebalancing Arbitrage** (intra-market): Within a single multi-outcome event, when probabilities drift from $1.00 sum
2. **Combinatorial Arbitrage** (inter-market): Across related but separate markets

**Important caveat**: NegRisk itself is a capital efficiency tool, not inherently an arbitrage mechanism. The arbitrage comes from market mispricing that neg-risk structure makes cheaper to exploit. The convert mechanism reduces the capital needed to capture these mispricings.

#### Conversion-Based Strategies

The convert mechanism enables strategies impossible in standard markets:
- **NO-to-YES rotation**: If you believe the field is mispriced, buy NO on the overpriced outcome, convert to YES on all others
- **Portfolio rebalancing**: Shift exposure across outcomes without round-tripping through USDC
- **Capital recycling**: Extract USDC from guaranteed-value portfolios to deploy elsewhere

### Overround Calculations in Neg-Risk

In a standard bookmaker model, overround = sum of all implied probabilities - 100%.

In neg-risk markets:
- The theoretical sum should be exactly $1.00
- In practice, sums often range $0.97-$1.03
- Overround above $1.00 means the market is "overpriced" overall (opportunity to sell)
- Underround below $1.00 means it's "underpriced" (opportunity to buy all)
- The neg-risk structure makes monitoring and exploiting these deviations **cheaper** because you don't need separate collateral for each position

---

## 4. Resolution Mechanics

### UMA Optimistic Oracle (OO)

Polymarket uses UMA's Optimistic Oracle for resolution. The system assumes proposals are correct unless challenged.

### Resolution Flow

```
Request (market creation)
    |
    v
Propose (anyone posts answer + $750 bond)
    |
    v
Liveness Period (2 hours, no dispute)
    |
    v
Resolution accepted --> Market settles
```

### Dispute Flow

```
Proposal submitted ($750 USDC.e bond)
    |
    v
Dispute filed ($750 counter-bond)
    |
    v
FIRST DISPUTE: Adapter ignores it, creates new Request
    |
    v
Second proposal submitted ($750 bond)
    |
    v
No dispute? --> Resolves (2 hours)
    |
    v
SECOND DISPUTE: Escalates to DVM (UMA token holder vote)
    |
    v
DVM voting period (~48 hours)
    |
    v
Resolution based on vote
```

### Key Timing Parameters

| Phase | Duration |
|-------|----------|
| Liveness (no dispute) | **2 hours** |
| Debate period (single dispute) | 24-48 hours |
| DVM vote (double dispute) | ~48 hours |
| **Total undisputed** | **~2 hours** |
| **Total single dispute** | **~3-4 days** |
| **Total double dispute (DVM)** | **4-6 days** |

### Bond Economics

- **Proposal bond**: $750 USDC.e (typical)
- **Dispute bond**: $750 USDC.e (must match proposer)
- **Winner receives**: Own bond back + half of opponent's bond
- **Unknown/50-50 resolution**: Each token redeems for $0.50

### Managed Optimistic Oracle V2 (MOOV2)

After multiple resolution controversies, Polymarket transitioned from OOV2 to **MOOV2**:
- Proposals restricted to **whitelisted, experienced proposers**
- Reduces premature/incorrect proposals that caused delays (up to 4 days per bad proposal)
- Better due diligence before proposal submission

### Historical Controversial Resolutions

#### Ukraine Mineral Deal (March 2025) -- $7M Market
- Market: "Ukraine agrees to Trump mineral deal before April?"
- Odds spiked from 9% to 100% overnight with no official confirmation
- A whale cast **5 million UMA tokens** across 3 accounts (25% of total votes)
- Market resolved YES despite no binding agreement
- Polymarket acknowledged "unprecedented situation" but **refused refunds**
- Exposed: UMA voting is highly concentrated; ~2 whales control >50% of staked tokens

#### TikTok Ban (January 2025)
- Market: "TikTok banned in the US before May 2025?"
- Resolved YES after Supreme Court upheld the ban
- DVM process was bypassed; market resolved directly to YES
- Bettors accused platform of manipulation due to ambiguous resolution criteria

**Key insight**: UMA votes almost always reach near-unanimous resolution (95%+), but when large financial interests are at stake, whale concentration creates vulnerability.

### Exploitable Patterns and Delays

**Resolution delay opportunities**:
- Between event occurrence and resolution proposal: typically hours, sometimes days for ambiguous events
- During dispute periods: 3-6 days of uncertainty where shares trade at discount to intrinsic value
- Markets trading at 98-99 cents after event but before formal resolution: low-risk profit if you're confident in the outcome

**Resolution ambiguity patterns**:
- Markets with vague criteria (e.g., "agrees to" vs. "signs") are dispute-prone
- Political/diplomatic markets have the most ambiguous resolution criteria
- Technical markets (crypto prices, sports scores) resolve cleanly

**Strategy**: Buy shares at 98-99 cents on markets where the outcome is known but resolution hasn't been proposed yet. Risk is limited to UMA dispute/manipulation edge cases.

---

## 5. Fee Structure

### Overview: Most Markets Are Fee-Free

As of February 2026, Polymarket charges **zero trading fees on most markets**. Fees are selectively applied to specific high-frequency market types.

### Taker Fee Formula

For fee-enabled markets:

```
fee = C * feeRate * (p * (1 - p))^exponent
```

Where:
- **C** = number of shares traded
- **p** = share price (probability)
- **feeRate** = market-specific rate
- **exponent** = market-specific (1 or 2)

### Fee Parameters by Market Type

| Parameter | Sports (NCAAB/Serie A) | 5-min & 15-min Crypto |
|-----------|----------------------|----------------------|
| Fee Rate | 0.0175 | 0.25 |
| Exponent | 1 | 2 |
| Max effective fee (at p=0.50) | **0.44%** | **1.56%** |
| Maker Rebate % | 25% | 20% |

### Fee Curve at Different Price Points (Crypto Markets, feeRate=0.25, exponent=2)

| Price (p) | Effective Fee % | Breakeven Edge Needed |
|-----------|----------------|----------------------|
| 0.05 | 0.06% | 0.31% |
| 0.10 | 0.20% | 0.63% |
| 0.20 | 0.64% | 1.25% |
| 0.30 | 1.10% | 2.10% |
| 0.50 | **1.56%** | **3.13%** |
| 0.70 | 1.10% | 4.20% |
| 0.80 | 0.64% | 5.00% |
| 0.90 | 0.20% | 5.63% |
| 0.95 | 0.06% | 5.94% |

**Critical insight**: The breakeven edge is NOT symmetric with the fee curve. At p=0.90, the fee is only 0.20%, but you need 5.63% edge because your potential gain is only $0.10/share. Trading near extremes requires proportionally more edge relative to potential profit.

### Total Cost Formula

```
c_total = fee_per_share(p) + (ask - bid) / 2 + slippage(size, depth)
```

### Minimum Viable Edge by Market Type

| Market Type | At p=0.50 | At p=0.20 | At p=0.80 |
|-------------|-----------|-----------|-----------|
| Fee-free markets | Spread + slippage only | Spread + slippage only | Spread + slippage only |
| Sports | ~0.44% + spread | ~0.28% + spread | ~0.28% + spread |
| Crypto (5/15 min) | ~1.56% + spread | ~0.64% + spread | ~0.64% + spread |

### Maker vs. Taker

| | Maker (Passive) | Taker (Aggressive) |
|---|---|---|
| Fee | **Zero** | Formula above (fee-enabled markets) |
| Rebate | Receives rebate from taker fees | Pays fees |
| Strategy implication | Always prefer limit orders | Market orders cost more |

### Deposit/Withdrawal Fees

| Action | Cost |
|--------|------|
| Deposit (USDC on Polygon) | $0.01-0.10 (gas only) |
| Deposit (via relayer) | $3 + network fee OR 0.3% (whichever higher) |
| Deposit (credit card) | 3.5-4.5% |
| Withdrawal (to exchange) | $0.10-0.50 (blockchain fee) |
| Bridge (ETH -> Polygon) | ~$10-20 |
| Polymarket platform fee | **None** |

### Gas Costs on Polygon

Polygon gas is **negligible** for most strategies:
- Basic transfer: $0.0005-$0.002
- Smart contract interaction: $0.01-$0.10
- 0.1-1 MATIC is enough for **thousands** of trades
- Not a meaningful factor in strategy economics

### US Exchange (Polymarket US) Fees

For the CFTC-regulated US platform:
- **Taker fee**: 0.01% of total contract premium
- Significantly lower than international platform's fee-enabled markets

### Fee Impact on Strategy Selection

| Strategy | Fee Impact | Recommendation |
|----------|-----------|----------------|
| Long-term directional | Negligible (one trade) | Use any market |
| Time decay (S006) | Negligible | Use fee-free markets |
| Market making | Positive (rebates) | Target fee-enabled markets for rebate income |
| High-frequency arbitrage | Significant | Must exceed fee + spread + slippage |
| Neg-risk rebalancing | Moderate | Need 2.5-3% overround to profit after fees |
| Resolution delay trades | Negligible | Single trade, fee-free markets |

---

## Strategic Synthesis

### Highest-Opportunity Structural Edges

1. **Neg-Risk Rebalancing** (proven $29M+ extracted): Monitor multi-outcome markets for probability sum deviations from $1.00. Capital-efficient via convert mechanism. Requires automation and speed.

2. **Liquidity Provision + Rewards** (declining but viable): Earn from spread capture + Polymarket rewards + maker rebates (on fee-enabled markets). Best with $10K+ capital across multiple markets.

3. **Resolution Delay Arbitrage** (episodic): Buy at 98-99 cents when outcome is known but resolution not yet proposed. Low risk except for UMA oracle manipulation edge cases.

4. **Fee-Free Advantage** (structural): Most markets have zero fees, giving Polymarket a structural advantage over Kalshi (which charges fees). This means lower minimum viable edge for strategies.

5. **Market Making on Fee-Enabled Markets** (new opportunity): Sports and crypto markets now have taker fees with 20-25% maker rebates. This is a new income stream layered on top of spread capture and liquidity rewards.

### Key Risks

- **UMA oracle manipulation**: Whale concentration in UMA voting creates tail risk on resolution
- **Operator centralization**: Off-chain matching depends on Polymarket operator honesty
- **Regulatory**: US users face restrictions; regulatory landscape shifting
- **Liquidity withdrawal**: Rewards declining as platform matures; spreads may widen or tighten unpredictably
- **Smart contract risk**: NegRiskAdapter and Exchange contracts, while audited, carry residual risk

---

## Sources

- [CLOB Introduction - Polymarket Docs](https://docs.polymarket.com/developers/CLOB/introduction)
- [Neg-Risk Overview - Polymarket Docs](https://docs.polymarket.com/developers/neg-risk/overview)
- [Resolution/UMA - Polymarket Docs](https://docs.polymarket.com/developers/resolution/UMA)
- [Trading Fees - Polymarket Docs](https://docs.polymarket.com/polymarket-learn/trading/fees)
- [Maker Rebates Program - Polymarket Docs](https://docs.polymarket.com/polymarket-learn/trading/maker-rebates-program)
- [Liquidity Rewards - Polymarket Docs](https://docs.polymarket.com/developers/market-makers/liquidity-rewards)
- [NegRisk Market Rebalancing: How $29M Was Extracted](https://medium.com/@navnoorbawa/negrisk-market-rebalancing-how-29m-was-extracted-from-multi-condition-prediction-markets-2f1f91644c5b)
- [Reverse Engineering Polymarket Liquidity Rewards](https://medium.com/@wanguolin/my-two-week-deep-dive-into-polymarket-liquidity-rewards-a-technical-postmortem-88d3a954a058)
- [Understanding the Polymarket Fee Curve](https://quantjourney.substack.com/p/understanding-the-polymarket-fee)
- [Polymarket HFT: AI Arbitrage and Mispricing](https://www.quantvps.com/blog/polymarket-hft-traders-use-ai-arbitrage-mispricing)
- [Oracle Manipulation in Polymarket 2025](https://orochi.network/blog/oracle-manipulation-in-polymarket-2025)
- [How a $7 Million Market Was Manipulated on Polymarket](https://beincrypto.com/polymarket-manipulation-attack-ukraine-trump-deal/)
- [Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets](https://arxiv.org/abs/2508.03474)
- [poly-maker (warproxxx)](https://github.com/warproxxx/poly-maker)
- [Polymarket py-clob-client](https://github.com/Polymarket/py-clob-client)
- [NegRisk CTF Adapter Source](https://github.com/Polymarket/neg-risk-ctf-adapter)
- [Polymarket US Fee Schedule](https://www.polymarketexchange.com/fees-hours.html)
- [How Polymarket Works - RockNBlock](https://rocknblock.io/blog/how-polymarket-works-the-tech-behind-prediction-markets)
- [UMA Oracle Controversy - Webopedia](https://www.webopedia.com/crypto/learn/polymarkets-uma-oracle-controversy/)
