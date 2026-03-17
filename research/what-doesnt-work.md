# What Doesn't Work in Prediction Market Trading

*Research date: 2026-02-23*
*Purpose: Document failures, common mistakes, and strategies that fail in practice*
*Status: Comprehensive literature review + empirical evidence synthesis*

---

## Table of Contents

1. [The Base Rate of Failure](#1-the-base-rate-of-failure)
2. [Common Retail Mistakes](#2-common-retail-mistakes)
3. [Why Most "Systems" Fail](#3-why-most-systems-fail)
4. [Strategies That Sound Good But Don't Work](#4-strategies-that-sound-good-but-dont-work)
5. [Structural Risks Unique to Prediction Markets](#5-structural-risks-unique-to-prediction-markets)
6. [What Separates Winners from Losers](#6-what-separates-winners-from-losers)
7. [Implications for Our System](#7-implications-for-our-system)

---

## 1. The Base Rate of Failure

### 1.1 The Numbers Are Brutal

From Reichenbach & Walther (2025), analyzing 124M+ trades across ~1M Polymarket traders:

| Metric | Value | Source |
|--------|-------|--------|
| Traders with realized losses | **70%** | Reichenbach & Walther 2025 |
| Traders with profit > $0 | 30% | Same |
| Traders with profit > $1,000 | **0.51%** | ChainCatcher on-chain analysis |
| Top 0.04% share of total profits | **>70%** ($3.7B) | ChainCatcher / defioasis.eth |
| Addresses with losses < $1,000 | 63.5% (1.1M addresses) | Same |
| Addresses with losses > $1M | 149 | Same |
| Average pre-fee return on Kalshi contracts | **-20%** | Burgi, Deng & Whelan 2026 |

**The distribution is a power law, not a bell curve:**
- Most losers lose small amounts ($0-$1,000) -- 63.5% of all participants
- A small number lose catastrophically (149 addresses lost >$1M each)
- Most winners win modest amounts ($0-$1,000) -- 24.56% of addresses, capturing 0.86% of profits
- A tiny elite (<0.04%) captures the vast majority of all profits

**This mirrors CFD/forex trading exactly.** European regulators report 62-82% loss rates among retail CFD traders. Prediction markets are not a new frontier -- they reproduce the same wealth transfer dynamics from unsophisticated to sophisticated participants.

### 1.2 Skill vs. Luck

The evidence says **skill exists but is rare**:

- Reichenbach & Walther (2025): "The proportion of traders with positive gains per bet exceeds expectations under randomness." Profitable traders show **persistent** profits over time -- not just lucky streaks.
- Forecasting tournament research (Tetlock): "Superforecasters" improved over time, confirming skill is learnable. They share traits: reasonable intelligence, information-seeking, willingness to update, probabilistic thinking.
- **But**: Only ~30% achieve positive P&L, and this share **decreases over time** as more casual participants enter. The skill ceiling is high and the skill floor is much lower than people think.

**Key insight**: Skill in prediction markets is real but is primarily the skill of **not making mistakes** rather than the skill of being brilliantly right. The 0.51% who profit >$1,000 are mostly people who avoid the errors documented below.

---

## 2. Common Retail Mistakes

### 2.1 The Win-Rate Trap (The #1 Killer)

**The single most documented cause of prediction market losses: confusing win rate with profitability.**

On Polymarket, every contract trades $0.00 to $1.00. The price you pay defines your risk-reward ratio:

| Entry Price | Risk | Reward | Ratio Against You | Break-Even Win Rate |
|-------------|------|--------|-------------------|---------------------|
| $0.10 | $0.10 | $0.90 | 0.11:1 | 10% |
| $0.30 | $0.30 | $0.70 | 0.43:1 | 30% |
| $0.50 | $0.50 | $0.50 | 1:1 | 50% |
| $0.70 | $0.70 | $0.30 | 2.33:1 | 70% |
| $0.77 | $0.77 | $0.23 | **3.35:1** | 77% |
| $0.90 | $0.90 | $0.10 | **9:1** | 90% |
| $0.95 | $0.95 | $0.05 | **19:1** | 95% |

**Case study: beachboy4** -- Lost $2.36M in 35 days with a ~51% win rate across 53 predictions. Entry prices clustered at $0.51-$0.67 (limited upside, full downside). Average bet size: ~$400K. Single largest loss: $1.58M on one Liverpool bet. No stop losses, no exit strategy, no position sizing.

**Case study: BTC $86K bet** -- Trader wagered $308,000 at $0.77 on "Will BTC stay above $86k?" Potential gain: +$92K. Potential loss: -$308K. The 3.35:1 ratio against means even at 77% implied probability, **any miscalibration destroys you**.

**The paradox**: A trader right 30% of the time on $0.10 contracts will outperform a trader right 70% of the time on $0.70 contracts. Most retail traders instinctively gravitate to "safe" high-probability bets without understanding the payoff asymmetry.

### 2.2 The "Yes" Bias

Reichenbach & Walther (2025) document systematic overtrading of the YES side:

> "Almost every bucket in available data resolves to 'yes' at a lower rate than expected, suggesting market participants seem to overestimate the likelihood of most events, especially the lower probability buckets."

**Why this happens:**
- People bet on things **happening**, not things **not happening**
- "Will X happen?" frames the question as a positive event -- psychologically easier to imagine
- Narrative bias: dramatic outcomes are more vivid and available than status quo
- Action bias: "buying YES" feels like doing something; "buying NO" feels passive

**What it means**: The structural counterparty to the 70% who lose is someone systematically selling YES (buying NO) at overpriced levels. This is the foundation of S006's time decay edge.

### 2.3 Trading Outside Your Domain

**Documented case: zxgngl** -- Earned $29M on Trump 2024 election markets (deep domain expertise). Then lost $3.6M on Mike Tyson vs. Jake Paul betting (zero domain expertise). The edge in political forecasting had absolutely no transfer value to sports.

**Documented case: SSryjh** -- Lost $4.5M blindly trusting sports favorites across multiple markets. Domain-general "this team is better" reasoning fails against specialized sports bettors with injury data, lineup analysis, and historical matchup statistics.

**Meta-lesson from T05**: "Across all documented Polymarket success stories, domain specialists dramatically outperform generalists." The top traders execute 10-30 trades/year with extremely high conviction in narrow domains. The worst performers trade everything.

### 2.4 Ignoring Resolution Rules

Markets resolve on **exact written definitions**, not common sense:

- **Zelenskyy suit market**: Resolved "No" despite video evidence of him wearing what most would call a suit, because the market's specific definition of "formal suit" excluded what he wore.
- **Trump/China crypto summit**: Trump mentioned China during his crypto summit. Market resolved "No" after Polymarket issued a retroactive rule clarification that the mention "didn't count."
- **Government shutdown cross-platform**: Polymarket resolved "YES" (shutdown occurred) while Kalshi resolved "NO" (no shutdown). Arbitrageurs who hedged across platforms **lost on both sides**.

**Implication**: Every dollar placed without reading the full resolution criteria is a dollar at risk of resolution surprise.

### 2.5 Emotional Trading Patterns

**Revenge trading**: After a loss, traders attempt to immediately "win back" money. Research shows this reduces decision quality by >70%. The emotional pain of loss (loss aversion: losses feel ~2x stronger than equivalent gains) drives impulsive entries, ignored risk management, and chains of compounding mistakes.

**Overtrading**: Trading for the sake of trading, without a validated thesis. FOMO drives premature entries. The urge to "do something" replaces probability-based decision-making. Each additional trade incurs spread costs that compound.

**Loss chasing**: Increasing position size after losses to accelerate recovery. This is the exact opposite of Kelly criterion logic (reduce size after losses, increase after wins).

**Anchoring**: Traders anchor on their entry price, round numbers ($0.50), or recent highs/lows instead of updating beliefs based on new information. This prevents cutting losses and taking profits at appropriate levels.

### 2.6 Market Orders in Thin Markets

Using market orders on illiquid Polymarket markets can mean paying $0.50/share when fair value is $0.10. Thin order books have wide bid-ask spreads, and market orders fill at whatever is available.

**Rule**: Always use limit orders. If the spread is >5%, the market is too thin to trade.

### 2.7 Ignoring Time Value of Money

Capital locked in a 6-month position earning 10% has an opportunity cost. The same capital could potentially earn 5% in one week and be redeployed 24+ times. Polymarket's 4% annualized holding rewards partially compensate, but most traders don't factor opportunity cost into position sizing.

### 2.8 Holding Until Resolution

Many traders hold positions to resolution when they could exit profitably at 90%+ probability. Risks of holding include:

- Resolution disputes (UMA oracle manipulation)
- Last-minute price reversals
- Capital locked during dispute periods (can be weeks)
- Ambiguous outcome interpretation

---

## 3. Why Most "Systems" Fail

### 3.1 Edge Decay

**The fundamental problem**: Any discovered edge attracts competition, compressing returns toward zero.

Evidence of edge compression in prediction markets:

| Edge Type | 2024 Window | 2026 Window | Compression |
|-----------|------------|------------|-------------|
| Cross-platform arbitrage | Minutes | **2.7 seconds** average | ~100x faster |
| Sub-100ms bot captures | N/A | 73% of arb profits | Bots dominate |
| Arb opportunity duration | 12.3 seconds | 2.7 seconds | 78% decline |
| Manual arb viability | Possible | "Essentially impossible" | Dead |

**Cross-platform arbitrage** yielded $40M from April 2024-April 2025. By 2026, open-source bots exist, average opportunity duration is 2.7 seconds, and 73% of all arb profits are captured by sub-100ms execution bots. Manual cross-platform arbitrage is dead for retail.

**But**: Slower edges (time decay, domain expertise, behavioral exploitation) decay much more slowly because they require domain knowledge, not just speed. Our S006 and S004 edges exploit human psychology, which doesn't evolve on bot timescales.

### 3.2 Fees and Spread Eating Theoretical Edge

Polymarket's cost structure:

| Cost | Approximate Impact |
|------|-------------------|
| Bid-ask spread | 1-3% per roundtrip (varies by liquidity) |
| Polygon gas | <$0.01 (negligible) |
| Price impact (slippage) | 0.5-5% on larger orders in thin markets |
| Opportunity cost | Varies (capital locked until resolution) |

**The math**: If your theoretical edge is 5% per trade and the spread eats 2%, your realized edge is 3%. If you also face 1% slippage, your edge is 2%. If your position is locked for 3 months, your annualized edge is ~8% -- barely better than treasury yields.

**Kalshi evidence**: Burgi, Deng & Whelan (2026) found the average pre-fee return on Kalshi contracts is **negative 20%**. Fees and the favorite-longshot bias combine to make the average contract a losing proposition.

**Implication**: Edges below ~3% are likely fee-negative in practice. Only strategies with structural edges of 5%+ survive transaction costs.

### 3.3 Illiquidity and the Exit Problem

Unlike equity markets, prediction markets have **no natural hedgers**. Nobody "needs" to hold these contracts the way fund managers need equities. This creates:

- **Thin order books**: Especially outside top markets. Many markets have <$10K in total liquidity.
- **Wide spreads**: 5-20% spreads on niche markets are common.
- **No exit when you need one**: When a YES event is confirmed (e.g., military strike occurs), liquidity on the NO side evaporates instantly. You cannot exit at any price.
- **Adverse selection**: Market makers widen spreads or exit when they detect informed flow, further degrading liquidity when you most need it.

**Academic basis**: Tetlock (2008) showed that liquidity directly impacts prediction market efficiency. Low-liquidity markets are less accurate AND harder to trade profitably.

### 3.4 Resolution Risk

This is the risk unique to prediction markets with no equivalent in traditional finance:

**Major documented resolution failures (2025):**

1. **Ukraine mineral deal** ($7M): Resolved "YES" despite no deal existing. A UMA whale cast 5M tokens (25% of total votes) across 3 accounts to force the outcome. Traders on the correct side lost everything.

2. **UFO declassification** ($16M): Resolved "YES" despite no documents being released. Late-session buying at 99-99.9 cents preceded a disputed UMA resolution.

3. **Fort Knox gold** ($3.5M): Manipulators resolved "No" on the "Gold missing from Fort Knox" market, stealing $3.5M from traders who held the correct position.

4. **Government shutdown cross-platform**: Different platforms resolved the same event differently, causing losses for hedged arbitrageurs.

**Systemic oracle issues**: UMA's Optimistic Oracle allows anyone to propose an outcome by staking collateral. UMA token holders vote to settle disputes. The problems:
- Large UMA holders can sway outcomes to protect their own positions
- Smaller voters are incentivized to follow majority signals, not independently verify
- Rewards are paid in UMA regardless of accuracy
- The system prioritizes coordination over correctness

**Partial fix**: In response, UMA migrated to Managed OOV2 (MOOV2), limiting proposals to 37 pre-approved addresses. This reduces attack surface but centralizes resolution authority.

**Implication**: Resolution risk is non-diversifiable. A single oracle manipulation can wipe out an otherwise profitable position. Position sizing must account for this as a real (not theoretical) risk.

### 3.5 Selection Bias in Backtests

Why our backtests look better than live performance will be:

| Bias | How It Affects Prediction Market Backtests |
|------|-------------------------------------------|
| **Survivorship bias** | We only analyze markets that resolved. Markets that were cancelled, delisted, or stuck in dispute limbo are invisible. |
| **Selection bias** | We backtest on the markets we *chose* to look at, which are the ones with clear resolution and good data -- not the messy ones. |
| **Look-ahead bias** | Historical domain NO rates (73.5% for S006) use all resolved data. We wouldn't have known this rate when entering individual trades. |
| **Execution assumption** | Backtests assume we enter at the observed price. In practice, our order moves the price, spreads widen, and execution is imperfect. |
| **Data quality** | Polymarket CLOB API purges price history for resolved markets. Our return estimates are modeled, not measured. We don't actually know what entry prices were achievable. |
| **Regime change** | Historical patterns come from 2024-2026 -- a period of elevated geopolitical tension and crypto speculation. The next 2 years may be structurally different. |

**The S006 backtest acknowledges this**: "The volume-weighted NO rate (60%) is lower than the count-based rate (73.5%). This means higher-volume markets are better calibrated." If we mostly trade high-volume markets (as we should for liquidity), our effective edge is closer to the 60% rate than 73.5%.

### 3.6 Survivorship Bias

**What we see**: Theo made $85M. "Axios" has a 96% win rate. HyperLiquid0xb made $1.4M from sports.

**What we don't see**: The thousands of traders who attempted the same strategies and failed. The wallet that tried commissioned polling (like Theo) and got it wrong. The domain specialist who specialized in the wrong domain. The arb bot that got stuck in a liquidity trap.

**Academic confirmation**: Brown, Goetzmann, Ibbotson & Ross: "When there is no truncation by survivorship, there is no apparent persistence of performance." Published "winning strategies" appear more robust than they are because the losers aren't published.

---

## 4. Strategies That Sound Good But Don't Work

### 4.1 Simple Momentum Following

**The claim**: "Markets that move in one direction tend to keep moving."

**The evidence in prediction markets**: **Mixed to negative.**

- Clinton & Huang (2025): **58% of Polymarket presidential markets show negative serial correlation** -- the opposite of momentum. Day-over-day, markets **reverse**, they don't continue.
- Restocchi et al. (2019): Confirmed mean-reverting behavior at short horizons across 3,385 PredictIt markets.
- Sung et al. (2019): Found systematic overreaction to price trends across 6,058 markets. A **correction** model improved accuracy, not a momentum model.

**Why momentum fails in prediction markets**:
- Unlike equities (where new information flows in gradually), prediction markets reprice discretely on news events
- The participant pool is dominated by retail emotional traders who overshoot
- Mean reversion is the dominant short-term pattern, not momentum
- The few cases where momentum works (primary momentum in political races) are well-known and competed away

**Where S005 might still work**: Slow, multi-event trend shifts (e.g., a candidate gaining across multiple polls over weeks). But our own S004 backtest found that **weekly drift is more exploitable than daily spikes** -- and the exploitable pattern is mean reversion, not momentum continuation.

### 4.2 Contrarian Trading Without Understanding "Why"

**The claim**: "The market is wrong, so I'll bet the other way."

**The failure mode**: Being contrarian without a specific thesis for *why* the market is wrong is just uninformed trading with extra confidence.

**The Kalshi evidence** (Burgi, Deng & Whelan 2026): Traders who buy cheap contracts (<$0.10) -- the classic "contrarian" bet on longshots -- lose over 60% of their money. The contracts are cheap for a reason: they almost never win.

**Aswath Damodaran's framework**: "The biggest danger in knee-jerk contrarian investing... is that buying the dip is akin to catching a falling knife, since that initial market drop can be a prelude to a much larger sell off." With individual stocks, "investors buy stocks being sold off for legitimate reasons (a broken business model, dysfunctional management, financial distress) and wait for a market correction that never comes."

**Applied to prediction markets**: Buying YES at $0.05 on "Will candidate X win?" because "everyone says they'll lose" requires knowing something the market doesn't. If your contrarian thesis is "I disagree" without supporting evidence, you're the liquidity the smart money is extracting from.

**When contrarianism works**: S004 works because it has a quantified mechanism (overreaction to emotional news, with documented 40% reversion within 7 days) and a classification checklist to distinguish structural moves from emotional spikes. **Undisciplined contrarianism is just another way to lose.**

### 4.3 "Buy the Dip" on Markets Headed to Zero

**The pattern**: A "by date" market declines from $0.60 to $0.40 to $0.20. Each decline looks like "the market is undervaluing this." Traders buy the dip. The market resolves NO, and they lose everything.

**Why this fails in prediction markets specifically**:
- As the deadline approaches with no event occurring, the probability **should** decline. This isn't a dip -- it's correct repricing.
- Each quiet day is evidence against the event happening (decreasing hazard model)
- The S006 backtest shows 73.5% of "by date" markets resolve NO. The dip buyers are usually wrong.

**When "buy the dip" works**: Only when there's a specific, articulable catalyst that the market hasn't priced. "Iran strike dropped from 60% to 40% but troops just deployed" is information. "Iran strike dropped from 60% to 40% so it's cheaper now" is the favorite-longshot bias in action.

### 4.4 Technical Analysis Applied to Prediction Markets

**The claim**: RSI, MACD, support/resistance, chart patterns work for predicting future price movements.

**Why it categorically fails in prediction markets**:

1. **Prediction markets converge to binary outcomes.** A stock can go up forever. A prediction market resolves at $1.00 or $0.00. Technical "support at $0.65" is meaningless when the market is about to resolve.

2. **Price is a probability, not a valuation.** "BTC is oversold" can have meaning because BTC has intrinsic cash flows (debatable) or network effects. "The probability that Trump wins is oversold" has no analogous meaning -- the probability is whatever the evidence says.

3. **No continuous price discovery.** Prediction market prices jump discretely on news events, not through the continuous order flow that generates chart patterns. RSI overbought/oversold signals are noise on a probability curve.

4. **Sample sizes are tiny.** Most markets exist for weeks to months with irregular trading. There isn't enough data to calibrate any technical indicator.

5. **Mean reversion is fundamental, not technical.** The documented negative autocorrelation (Clinton & Huang 2025) is driven by behavioral overreaction, not by any chart pattern. You don't need RSI to detect it -- you need a spike classification checklist.

**Evidence**: No published study documents profitable technical analysis in prediction markets. The entire academic literature on prediction market inefficiencies focuses on behavioral biases, not chart patterns.

### 4.5 Cross-Platform Arbitrage (Increasingly Dead)

**Historical profit**: $40M extracted April 2024 - April 2025 across platforms.

**Current state (2026)**:
- Average arb opportunity duration: **2.7 seconds** (down from 12.3 seconds in 2024)
- 73% of arb profits captured by sub-100ms execution bots
- Open-source arb bots freely available
- "Manual arbitrage identification is essentially impossible in 2026"
- A 2025 study found 78% of arb opportunities in low-volume markets failed due to execution inefficiencies

**Additional risks**:
- Settlement definition differences across platforms (the government shutdown problem)
- Different resolution rules mean "the same event" isn't actually the same market
- Capital locked on multiple platforms simultaneously reduces capital efficiency
- Regulatory risk: platforms may be blocked in your jurisdiction

**Our S007 strategy correctly identifies this**: "S007 Type 4 (cross-platform) is declining in viability. Focus S007 on Type 1 (overround) and Type 2 (temporal consistency) arbs within Polymarket."

### 4.6 "High-Probability Bond" Trading Without Edge

**The strategy**: Buy contracts at $0.95+ and collect the $0.05 spread when they resolve correctly.

**Why it sounds appealing**: Annualized returns of >500% if turnover is fast. "Free money."

**Why it often fails**:
- At $0.95, you need >95% accuracy to break even. **One loss wipes out 19 wins.**
- The remaining 5% probability is real. Over enough trades, the tail event *will* happen.
- Resolution risk: oracle manipulation on a $0.95 contract creates a 19:1 loss
- Liquidity dries up at extreme prices (few sellers at $0.95+)
- Capital locked for the full resolution period, limiting throughput
- This is literally "picking up pennies in front of a steamroller"

---

## 5. Structural Risks Unique to Prediction Markets

### 5.1 Platform Risk

**Documented incidents:**
- **Polymarket enforcement action (2022)**: CFTC shut down US access for years. Traders with capital on the platform were unable to trade or withdraw easily.
- **December 2025 authentication attack**: Exploited Magic Labs flaw in Polymarket's email login, bypassing 2FA and compromising user accounts.
- **State-level bans**: At least 20 federal lawsuits challenge prediction market legality. Nevada obtained temporary restraining orders against both Kalshi and Polymarket. Massachusetts courts banned Kalshi's sports contracts.

**Current regulatory landscape (Feb 2026)**:
- Polymarket received CFTC approval for regulated US return (Nov 2025)
- CFTC defending federal authority against state challenges
- But: state-level resistance is strong, legal experts expect Supreme Court fight
- Industry trajectory is uncertain despite current favorable federal posture

**CertiK warning**: "Liquidity consolidated around just three platforms -- Kalshi, Polymarket, and Opinion -- creating fragility if regulation disrupts market access."

### 5.2 Oracle / Resolution Risk

Detailed in Section 3.4 above. Summary of documented losses:

| Incident | Amount at Stake | Outcome |
|----------|----------------|---------|
| Ukraine mineral deal manipulation | $7M | Wrong resolution forced by whale |
| UFO declassification dispute | $16M | Resolved YES without evidence |
| Fort Knox gold manipulation | $3.5M | Manipulators stole from correct position holders |
| Trump/China retroactive rule change | Unknown | Polymarket retroactively changed rules |
| Government shutdown cross-platform | Unknown | Different platforms, different outcomes |

**Systemic change**: UMA migrated to Managed OOV2 (37 whitelisted proposers). Reduces whale attacks but introduces centralization risk -- now 37 people can determine outcomes.

### 5.3 Wash Trading and Fake Volume

**Columbia University study (2025)**: Nearly 25% of Polymarket's total trading volume may be artificial.

| Period | Estimated Wash Trading % |
|--------|------------------------|
| Peak weeks (Dec 2024) | Up to **60%** of weekly volume |
| Election markets peak | Up to **95%** in one week |
| Sports markets (historical avg) | **45%** |
| Election markets (overall avg) | **17%** |
| Flagged wallets | 14% of 1.26M total wallets |

**Implications for traders**:
- Volume-based signals are unreliable (a market showing $10M volume may have $2.5M of real activity)
- Liquidity appears deeper than it actually is -- market impact on real orders is worse than order book suggests
- Price discovery may be distorted during high wash-trading periods
- Some wash traders hold losing positions deliberately to appear legitimate

**Motivations**: Primarily airdrop farming and platform ranking manipulation, not direct profit. CertiK notes wash trading hasn't distorted prices at scale **yet** -- but it could if the share grows.

### 5.4 Market Manipulation

**Insider trading**: No SEC-equivalent insider trading rules apply to prediction markets. Politicians can bet on their own elections. Campaign insiders can trade on unreleased polling. Corporate executives can trade on their own company's decisions.

**CFTC enforcement**: Zero enforcement actions for market manipulation on event contracts to date.

**Spoofing and manipulation**:
- Thin order books make price manipulation cheap
- A single large order can move prices 10-20% on niche markets
- Bots monitor and front-run large retail orders

**The Polymarket social media incident**: The platform publicly mocked a trader who lost $42,000 in 48 hours, calling it a "historic meltdown." This reveals the platform's incentive alignment -- it profits from trading volume, not from trader profitability.

### 5.5 Automated Adversaries

**Bot dominance statistics (2026)**:
- Bots achieve ~85% win rate with $206K profit on specific strategies
- Humans using similar strategies capture ~$100K (roughly half)
- One bot turned $313 into $414,000 in a single month trading 15-minute BTC/ETH/SOL markets
- Average arb opportunity duration: 2.7 seconds
- Wall Street quants are moving into prediction markets specifically to hunt for arbitrage

**Implication**: In any strategy that requires speed (arbitrage, news reaction, spike detection), you are competing against bots that react in milliseconds. Only strategies requiring **judgment, domain knowledge, and patience** remain viable for human traders.

### 5.6 Liquidity Traps and Stuck Markets

**The trap**: Enter a position in a market with apparent liquidity. Conditions change (regulatory event, disputed resolution, platform issue). Liquidity evaporates. You cannot exit at any reasonable price.

**Why prediction markets are uniquely vulnerable**:
- No natural hedgers (nobody *needs* these contracts)
- Markets can be delisted, paused, or disputed
- When an event confirms (military strike occurs, election is called), the losing side sees instant liquidity evaporation
- No circuit breakers or market halts
- No regulatory requirement for market makers to maintain continuous quotes

### 5.7 Consumer Protection Gaps

Unlike broker-dealers (SEC-regulated), prediction market platforms:
- Have no mandatory suitability analysis for customers
- No automated cooling-off periods after large losses
- Minimal self-exclusion options for problem gambling
- No addiction warning systems
- Age verification through self-certification only (Polymarket)
- No mandatory balance segregation requirements (for some platforms)

---

## 6. What Separates Winners from Losers

### 6.1 The Documented Profit Models

From ChainCatcher analysis of 95M on-chain transactions:

| Model | Representative | Profit | Key Trait |
|-------|---------------|--------|-----------|
| Information arbitrage | Theo | $85M | Commissioned custom poll. Months of domain expertise. |
| Cross-platform arb | Aggregate | $40M | Speed + infrastructure. Declining viability. |
| High-probability bonds | Various | Unknown | Capital efficiency + resolution risk tolerance |
| Market making | Various | 80-200% annualized | Infrastructure, algorithms, spread management |
| Domain specialization | "Axios" (96% win rate) | Millions | 10-30 trades/year, extreme conviction in narrow domain |
| Speed trading | Various | $4.2M aggregate | Within 8 seconds of Powell speaking, 13% contract jump |

### 6.2 What the Winners Do Differently

Based on all documented evidence:

1. **Extreme domain specialization**: Not generalists. They know one domain deeply.
2. **Few, high-conviction trades**: 10-30/year, not 10-30/day. Quality over quantity.
3. **Asymmetric payoff structure**: They seek bets where the upside dramatically exceeds the downside, not "safe" bets with capped upside.
4. **Position sizing discipline**: Max 3-5% of capital per position. Quarter-Kelly or less.
5. **Exit discipline**: They exit when the thesis changes, not when they hit a round-number target.
6. **They sell what others want to buy**: Contrarian on emotional markets, not contrarian on principle.
7. **They understand resolution rules before entering**: No resolution surprises.
8. **They use limit orders**: Never market orders on thin books.
9. **Infrastructure investment**: Monitoring bots, news feeds, automated alerts. They don't check prices manually.
10. **They account for all costs**: Spread, opportunity cost, resolution risk, time value of money.

### 6.3 What the Losers Do Consistently

1. **Trade on vibes**: No thesis, no edge, no probability estimate. Just "I think YES."
2. **Chase high-probability bets**: Buy at $0.80+ for "safe" returns, get destroyed by the asymmetry.
3. **Overtrade**: Frequency substitutes for quality. Each trade incurs costs.
4. **Trade outside their domain**: Success in politics doesn't transfer to sports or crypto.
5. **Ignore resolution rules**: Get surprised by technicalities.
6. **Use market orders on thin markets**: Give away 5-20% on entry.
7. **Hold until resolution**: Miss profitable exits, get trapped in disputes.
8. **Revenge trade**: Try to win back losses with bigger, less disciplined bets.
9. **Copy trades without understanding**: Follow whales without knowing their thesis, timing, or exit plan.
10. **Treat it as gambling**: Binary outcomes, no probability framework, no risk management.

---

## 7. Implications for Our System

### 7.1 What This Research Validates

Our existing system **already accounts for many of these failure modes**:

- **Quarter-Kelly sizing** (BANKROLL.md) -- prevents the beachboy4 blowup
- **S006 time decay exploits the YES bias** -- we're on the winning side of the structural mispricing
- **S004 has a classification checklist** -- prevents blind contrarianism
- **Domain specialization** (strategy-domain matrix) -- we're not trading everything
- **Drawdown limits** (BANKROLL.md -15%, -25%, -40% stops) -- prevents catastrophic loss spirals
- **Paper trading first** -- catches selection bias before real capital
- **S007 correctly deprioritizes cross-platform arb** -- acknowledges edge decay

### 7.2 Where We're Still Vulnerable

| Risk | Current Mitigation | Gap |
|------|-------------------|-----|
| **Resolution risk** | Not explicitly addressed | Need: maximum position size factoring in oracle manipulation risk. Consider exiting at 90%+ rather than holding to resolution. |
| **Wash trading distortion** | S004 has $200K liquidity minimum | Need: cross-reference volume signals against Columbia wash trading estimates. Apply discount to apparent liquidity. |
| **Win-rate trap** | Kelly sizing helps | Need: explicit rule against entering at >$0.70 without exceptional justification. Track payoff asymmetry per trade. |
| **Backtest-live gap** | Acknowledged in S006 report | Need: use volume-weighted NO rate (60%) not count-weighted (73.5%) for sizing. Apply 30-50% haircut to theoretical returns. |
| **Edge decay on S006** | Monitoring recommended | Need: quarterly recalibration of domain NO rates. Watch for the pattern being arbitraged away. |
| **Platform risk** | $250 permanent reserve | Need: explicit plan for regulatory shutdown scenario. Know how to withdraw in an emergency. |
| **Bot competition** | Not explicitly addressed | Need: ensure all strategies require judgment/domain knowledge, not speed. We cannot compete on execution speed. |
| **Time value of money** | Not tracked | Need: track annualized return per position, not just absolute P&L. A 10% return over 6 months is ~20% annualized; same return in 2 weeks is ~260% annualized. |

### 7.3 Concrete Action Items

1. **Add resolution risk protocol**: For positions >3% of bankroll, exit at 90-95% probability rather than holding to resolution. The 5-10% left on the table is insurance against oracle manipulation.

2. **Implement the "Zone" framework**: Classify every trade entry by price zone (1-5). Track P&L by zone. Flag any trade entering Zone 4-5 ($0.60-$0.98) for extra scrutiny.

3. **Apply backtest haircut**: Use 60% (volume-weighted) not 73.5% (count-weighted) NO rate for S006 sizing. Apply additional 20% haircut for execution reality.

4. **Track annualized returns**: Every position should have an annualized return calculation. If annualized return is <15%, the capital is better deployed elsewhere.

5. **Quarterly edge decay check**: Recalculate domain-specific NO rates each quarter using new resolution data. If the edge compresses >10%, reduce allocation.

6. **Platform emergency protocol**: Document exact steps to withdraw all capital within 24 hours if regulatory action occurs.

7. **Anti-patterns checklist**: Before every trade, verify:
   - [ ] Am I trading in a domain I understand? (Not outside swim lane)
   - [ ] Have I read the full resolution rules?
   - [ ] Is this a limit order? (Not market order)
   - [ ] Is the entry price in Zone 1-3? (If Zone 4-5, what's my exceptional justification?)
   - [ ] Is the market liquid enough? (>$200K real volume, after wash trading discount)
   - [ ] Am I revenge trading or FOMO-ing?
   - [ ] Does this position have a defined exit plan?

---

## Sources

### Academic Papers
1. Reichenbach & Walther (2025). "Exploring Decentralized Prediction Markets: Accuracy, Skill, and Bias on Polymarket." [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5910522)
2. Clinton & Huang (2025). "Prediction Markets? The Accuracy and Efficiency of $2.4 Billion in the 2024 Presidential Election." Vanderbilt University.
3. Augenblick et al. (2025). "How Manipulable Are Prediction Markets?" arXiv:2503.03312.
4. Sung et al. (2019). "Improving prediction market forecasts by detecting and correcting possible over-reaction to price movements." European Journal of Operational Research.
5. Restocchi et al. (2019). "The Stylized Facts of Prediction Markets." Physica A.
6. Burgi, Deng & Whelan (2026). "Makers and Takers: The Economics of the Kalshi Prediction Market." [CEPR](https://cepr.org/voxeu/columns/economics-kalshi-prediction-market)
7. Tetlock (2008). "Liquidity and Prediction Market Efficiency." Columbia Business School.
8. Manski (2006). "Interpreting the Predictions of Prediction Markets." Economics Letters.

### Industry Reports & Analysis
9. ChainCatcher (2025). "Polymarket 2025 Six Major Profit Models In-Depth Report." [Link](https://www.chaincatcher.com/en/article/2233047)
10. CertiK (2026). "Skynet Prediction Markets Report." [Link](https://www.certik.com/resources/blog/2026-skynet-prediction-markets-report)
11. Columbia University (2025). Wash trading study. [CoinDesk](https://www.coindesk.com/markets/2025/11/07/polymarket-s-trading-volume-may-be-25-fake-columbia-study-finds)

### News & Analysis
12. [70% of Polymarket Traders Lost Money](https://finance.yahoo.com/news/70-polymarket-traders-lost-money-192327162.html) - Yahoo Finance
13. [Polymarket Faces Major Credibility Crisis](https://cryptoslate.com/polymarket-faces-major-credibility-crisis-after-whales-forced-a-yes-ufo-vote-without-evidence/) - CryptoSlate
14. [Polymarket Faces Backlash as $7M Market Manipulation](https://finance.yahoo.com/news/polymarket-faces-backlash-7m-ukraine-010306627.html) - Yahoo Finance
15. [Trader Lost $2 Million on Polymarket](https://finance.yahoo.com/news/trader-lost-2-million-polymarket-133015895.html) - Yahoo Finance
16. [Why 77% Win-Rate Traders Go Broke](https://quantjourney.substack.com/p/why-77-win-rate-traders-go-broke) - QuantJourney
17. [Common Mistakes on Prediction Markets](https://whales.market/blog/common-mistakes-on-prediction-market/) - Whales.market
18. [7 Mistakes New Prediction Market Traders Make](https://news.stand.trade/p/7-mistakes-new-predictive-market) - Stand Trade
19. [70% of Prediction Market Traders Are Capital Donors](https://www.financemagnates.com/forex/70-of-prediction-market-traders-are-capital-donors-matching-cfd-losses/) - Finance Magnates
20. [Arbitrage Bots Dominate Polymarket](https://finance.yahoo.com/news/arbitrage-bots-dominate-polymarket-millions-100000888.html) - Yahoo Finance
21. [Prediction Markets Oversight](https://www.citationneeded.news/prediction-markets-oversight/) - Citation Needed
22. [The Problem with Prediction Markets](https://theoryvc.com/blog-posts/the-problem-with-prediction-markets-spencer-farrar) - Theory VC
23. [Prediction Markets Grew 4X But Risk Structural Strain](https://decrypt.co/357583/prediction-markets-grew-4x-to-63-5b-in-2025-but-risk-structural-strain-certik) - Decrypt
24. [Polymarket Users Lost Millions to Bot-Like Bettors](https://www.dlnews.com/articles/markets/polymarket-users-lost-millions-of-dollars-to-bot-like-bettors-over-the-past-year/) - DL News
25. [Buy the Dip: The Draw and Dangers of Contrarian Investing](https://aswathdamodaran.substack.com/p/buy-the-dip-the-appeal-and-dangers) - Aswath Damodaran
