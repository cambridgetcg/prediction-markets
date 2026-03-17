# New Strategy Research

*Generated: 2026-02-23*

This document explores strategies beyond S001-S008, focusing on structural features unique to prediction markets that are impossible in traditional finance.

---

## Part 1: Polymarket Structural Mechanics

Understanding the platform's architecture reveals where structural edges live.

### Order Book (CLOB)

Polymarket uses a **hybrid-decentralized CLOB** — off-chain matching for speed, on-chain settlement on Polygon. Critical structural feature: **unified order book** — every BUY YES at price X appears as SELL NO at (1.00 - X), doubling effective liquidity. Matching is price-time priority. Standard tick: $0.01. Market orders use Fill-or-Kill with 5-cent slippage tolerance.

### Fee Structure

**Most markets are fee-free** — this is Polymarket's biggest structural advantage over traditional betting. Fee-enabled markets (crypto short-term, some sports) use: `fee = C * feeRate * (p*(1-p))^exponent`. Maximum effective rate: 1.56% at p=0.50 for crypto, 0.44% for sports. **The 2% winner fee on resolution is the primary cost.** Gas on Polygon is negligible ($0.01-0.10/trade).

**Minimum viable edge**: At p=0.50, you need >2% edge to profit after the winner fee. At p=0.90, breakeven edge is 5.63% despite only 0.20% fee — because profit per share is only $0.10. **Implication: high-probability bond trading requires more edge than it appears.**

### Neg-Risk Markets

The standout structural mechanic. In multi-outcome markets, a NO share in any outcome can be converted into 1 YES share in every other outcome via the NegRiskAdapter. This creates massive capital efficiency:

- During Apr 2024 - Apr 2025, **$40M in arbitrage profit** was extracted
- Neg-risk rebalancing generated **73% of profits from only 8.6% of opportunities** — a 29x capital efficiency advantage
- The arbitrage comes from probability sums drifting from $1.00, which the convert mechanism makes cheap to exploit
- **Need 2.5-3% overround to profit after fees**

### Resolution Mechanics (UMA Oracle)

- Undisputed resolution: ~2 hours (proposal + liveness period)
- Disputed resolution: 3-6 days (escalates to DVM token holder vote)
- Bond: $750 USDC.e for both proposers and disputers
- **Critical vulnerability**: Only ~5M UMA tokens needed to control a vote (25% of voting power)
- Post-Ukraine-mineral-deal attack (March 2025), Polymarket moved to MOOV2 (whitelisted proposers only)

### Liquidity Rewards

$12M allocated for 2025 LP rewards. Scoring: `S(v,s) = ((v-s)/v)^2 * b` — quadratic, heavily penalizing wide spreads. Sampled every minute, paid daily at midnight UTC. New maker rebates program (Jan-Feb 2026) pays 20-25% of taker fees back on crypto/sports markets.

---

## Part 2: Novel Strategy Candidates

### S009 — Resolution Arbitrage ("The Oracle Trader")

**Edge hypothesis**: Markets with ambiguous resolution criteria have mispriced resolution risk. Bet on how the UMA oracle will *interpret* whether an event happened, not on the event itself.

**Mechanism**: UMA's voting principles state "the title reflects the spirit of the market" and "public understanding is more important than nuanced interpretation of the rules." This creates systematic ambiguity. When resolution criteria are unclear, the price should reflect resolution uncertainty — but retail traders price only event probability.

**Evidence**:
- Ukraine mineral deal: whale with 5M UMA tokens forced $7M market to wrong resolution. Polymarket refused refunds: "not a market failure."
- Venezuela presidential election: resolved for Gonzalez based on "credible reporting" despite official government source saying otherwise
- "Israel invade Lebanon before September": UMA voted "No" despite active military operations
- "Gold missing from Fort Knox": whether a monthly report counts as an "audit" is ambiguous
- TIME Person of the Year 2022: required UMA to handle edge case

**Entry rules**:
1. Scan new markets for ambiguous resolution criteria (what counts as "agree"? "strike"? "invade"?)
2. When event outcome is uncertain AND resolution criteria are ambiguous, price in the resolution risk
3. Buy NO when the resolution criteria make NO the safer interpretation (UMA defaults to status quo)
4. Size small — oracle manipulation is a tail risk

**Exit rules**: Hold to resolution. If resolution is disputed, the 3-6 day window creates opportunity to buy/sell based on UMA voting dynamics.

**Data requirements**: UMA voting history, resolution criteria text, historical resolution disputes database

**Feasibility**: 3/5 — Requires deep UMA knowledge, small addressable market, but genuine structural edge when applicable.

**Should we add?**: YES — as an overlay on existing strategies, not standalone. When entering any trade, assess resolution ambiguity as a risk factor. Promote markets with clear resolution criteria.

---

### S010 — Whale Signal Following ("Smart Money Tracker")

**Edge hypothesis**: Large wallets on Polygon are publicly visible. Historically profitable wallets (identifiable via on-chain P&L) have informational edge. Following their directional bets with a delay captures a portion of their alpha.

**Mechanism**: All Polymarket trades settle on Polygon. Tools like Polywhaler (tracks $10K+ trades), PolyTrack (cluster detection for related wallets), and HashDive Smart Scores (-100 to +100 trader ratings) make whale identification accessible.

**Evidence**:
- Theo: $85M profit from 11 accounts, commissioning private polling. His on-chain flow was visible before his identity was known.
- The "Unravelling the Probabilistic Forest" paper found $40M in realized arbitrage by sophisticated traders — all traceable on-chain.
- Documented: top 0.04% captured >70% of all profits. These wallets are identifiable.
- One platform reports "average user profit increase of 127%" from copy trading (self-reported, treat skeptically).

**Entry rules**:
1. Identify 10-20 historically profitable wallets via Dune Analytics / PolyTrack
2. Monitor their new positions via on-chain alerts
3. When a tracked whale takes a new position >$10K in a market you've researched (S008 overlap), enter same direction
4. Require convergence: whale signal + your own estimate must agree on direction
5. Don't blind-copy — use whale as confirmation signal, not primary signal

**Exit rules**: Exit when whale exits, OR when your own thesis changes, OR at threshold (S002).

**Data requirements**: Dune Analytics dashboard, Polygon RPC node or API, wallet tracking alerts (Polywhaler/PolyTrack free tiers), historical P&L data for wallet scoring.

**Feasibility**: 4/5 — Tools exist, data is public, Theo case proves concept. Challenge: distinguishing genuine signal from noise traders and wash trading. Speed is NOT the constraint (we're following over days/weeks, not milliseconds).

**Should we add?**: YES — as a signal overlay. Integrate whale tracking into the S008 research process. When your research says "BUY" and a historically profitable whale just entered the same direction, that's convergence worth sizing up for.

---

### S011 — High-Probability Bond Rotation ("The Yield Farmer")

**Edge hypothesis**: Buying >95% probability contracts for near-certain resolution turns prediction markets into a yield instrument. Systematically rotating through short-duration, high-probability contracts generates annualized returns exceeding Treasury bills.

**Mechanism**: Buy at $0.95-0.99, receive $1.00 at resolution. The return is (1 - price) / price. If resolution occurs quickly, annualized returns are enormous.

**Evidence**:
- BrewMarkets documents traders replacing bonds with prediction market contracts, achieving 5.5%+ annualized
- Documented example: "No" on "Will Fed cut rates at this meeting?" at $0.95, 3 days to resolution = ~5.2% in 72 hours
- The "high-probability bonds" profit model is one of 6 documented profitable approaches on Polymarket (from ChainCatcher analysis)
- Annualized returns of 80-200% documented in optimal conditions

**Entry rules**:
1. Screen for markets at >95% with resolution within 7 days
2. Verify the 95% is genuine (not just illiquid / stale) — read the market, check recent news
3. Require clear resolution criteria (avoid oracle risk)
4. Buy the dominant side (YES or NO, whichever is >95%)
5. Maximum 5% of bankroll per position (tail risk management)

**Exit rules**: Hold to resolution only. No early exit. This is a "clip the coupon" strategy.

**Rough math**:
- Buy at 96c, resolve in 5 days = 4.17% return = 304% annualized
- Buy at 98c, resolve in 3 days = 2.04% return = 248% annualized
- BUT: 2% winner fee reduces 96c buy to ~2.17% net return
- AND: one 95c position failing wipes ~19 successful 95c positions

**Risk**: This is NOT risk-free. Oracle manipulation (Ukraine deal), genuinely uncertain events priced as certain, platform risk. The favorite-longshot bias research confirms that high-probability contracts are underpriced (they win more often than implied), but the tail risk is catastrophic when it hits.

**Data requirements**: Market screener for >95% contracts with near-term resolution. Historical resolution data to estimate true failure rate at each probability level.

**Feasibility**: 4/5 — Simple to execute, well-documented profit model. The key risk management challenge: the Kelly criterion says you should bet your entire bankroll on a 95% contract, but the fat-tailed failure distribution (oracle attacks, etc.) means you need to cap position size severely.

**Should we add?**: YES — as a capital deployment strategy for idle bankroll. When bankroll is sitting in cash between S006/S004/S008 trades, rotate into high-probability bonds. This is the "risk-free rate" of the prediction market world (with the caveat that it's not actually risk-free).

---

### S012 — LLM Ensemble Screener ("The Silicon Forecaster")

**Edge hypothesis**: An ensemble of 3-5 LLMs, calibrated via Platt scaling and combined with market prices and base rates, can identify mispriced markets faster and at greater scale than manual research (S008).

**Mechanism**: Feed market questions to multiple LLMs → aggregate predictions → calibrate → compare to market price → flag mispricings for human review.

**Evidence**:
- Halawi et al. (NeurIPS 2024): LLM system matches crowd-level accuracy on uncertain questions with good retrieval
- "Wisdom of the Silicon Crowd" (Science Advances 2024): 12-LLM ensemble matches human crowd accuracy
- ForecastBench: GPT-4.5 Brier score 0.101 vs superforecasters 0.081 — gap closing, parity projected late 2026
- AIA Forecaster (Bridgewater): **ensemble of AI + market consensus outperforms market consensus alone** — proof that AI adds information
- Schoenegger/Tetlock: LLM assistants improve human forecasting by 24-41%
- ilovecircle bot: $2.2M profit in 60 days, 74% accuracy using neural net + news feeds + social sentiment
- OLAS/Gnosis: 300+ autonomous agents at 79% prediction accuracy

**Entry rules**:
1. Query 3+ LLMs (GPT-4, Claude, one open-source) on each active market with structured prompt
2. Take median of LLM estimates (more robust to outlier overconfidence)
3. Combine: `P_final = extremize(w1 * P_market + w2 * median(P_llm) + w3 * P_base_rate)`
4. Apply Platt scaling trained on historical LLM predictions vs outcomes
5. Flag markets where |P_final - P_market| > 5pp for human review
6. Human makes final entry decision (AI screens, human decides)

**Exit rules**: Per the underlying strategy (S001-S008) that the LLM identified the edge for.

**Key calibration findings**:
- LLMs are overconfident at 90%+ (wrong 15-32% of the time) — never trust raw high-confidence outputs
- Prompt format dramatically affects calibration — structured queries outperform narrative prompts
- Political questions: LLMs perform notably better than on economic questions
- Uncertain questions (30-70% range): LLMs match or edge out the crowd

**Data requirements**: LLM API access (OpenAI, Anthropic, open-source), Polymarket Gamma API for market list, historical resolved market data for calibration training, vector DB (ChromaDB) for RAG.

**Open source starting points**:
- [Polymarket/agents](https://github.com/Polymarket/agents) — official framework with Gamma API + ChromaDB + LLM integration
- [gnosis/prediction-market-agent](https://github.com/gnosis/prediction-market-agent) — 300+ agents, 79% accuracy
- [AutoCast++](https://arxiv.org/abs/2310.01880) — zero-shot ranking-based context retrieval, 48% accuracy boost

**Feasibility**: 4/5 — The tools exist, the evidence is strong, open-source frameworks are available. The bottleneck is calibration: you need ~100+ resolved predictions to train Platt scaling. Building the calibration dataset takes time. Start by logging LLM estimates alongside market prices on every market you research — this builds the training data passively.

**Should we add?**: YES — this is the highest-leverage new strategy. It doesn't replace S008 (human research); it scales S008 by screening hundreds of markets to find the ones worth researching deeply. The ilovecircle case ($2.2M in 60 days) and Bridgewater AIA Forecaster (AI + market consensus beats consensus alone) provide the strongest evidence.

---

### S013 — Temporal Spread Trading ("The Calendar Trader")

**Edge hypothesis**: Related markets with different resolution dates create a term structure of probability. When the term structure is inconsistent (e.g., "by March" is priced higher than "by June"), the spread is exploitable.

**Mechanism**: In nested deadline markets (common in GEO), "by March" ≤ "by June" ≤ "by December" must hold mathematically. When they don't (or when the implied conditional probability between dates is unreasonable), trade the spread.

**Evidence**:
- "Unravelling the Probabilistic Forest" (IMDEA 2025): 41% of all conditions had single-market arbitrage; >7,000 markets had measurable combinatorial mispricings; $40M USD in realized profit
- GEO nested deadlines are the primary terrain: Iran strike by March/June/December, ceasefire by Q1/Q2/Q4
- Your S007 already identifies this in theory — S013 makes it systematic for temporal structures specifically

**Entry rules**:
1. Identify all markets on the same event with different deadlines
2. Calculate implied conditional probabilities: P(by June | not by March) = (P_June - P_March) / (1 - P_March)
3. If conditional is negative (P_March > P_June): pure arbitrage — buy June YES, sell March YES
4. If conditional is unreasonably high/low compared to base rate: directional spread trade
5. Use neg-risk mechanics for capital-efficient spread construction

**Exit rules**: Hold both legs to resolution. The spread converges as the first deadline approaches.

**Data requirements**: Gamma API for identifying related markets, price history for term structure analysis, base rate data for conditional probability benchmarking.

**Feasibility**: 3/5 — The math is clean and the edge is well-documented ($40M extracted). However: average arbitrage opportunity lasts only 2.7 seconds, and 73% of profits go to sub-100ms bots. The *fast* arb is dead for humans. The *slow* arb (mispriced conditionals that persist for days because they require domain reasoning to identify) remains accessible.

**Should we add?**: YES — but explicitly as the "slow" version. Don't compete with bots on pure price discrepancies. Instead, use domain knowledge to identify when the implied conditional probability between dates is wrong (e.g., "if Iran hasn't struck by March, the probability of striking by June should drop, not stay the same"). This is S007 Type 2 (temporal consistency) made systematic.

---

### S014 — Geo-Restriction Edge ("The Local Informer")

**Edge hypothesis**: With 33+ countries blocked from Polymarket (France, Belgium, Poland, Italy, Netherlands, UK, etc.), markets on events in those countries are priced by non-local traders who lack local knowledge.

**Mechanism**: European political markets, for example, are priced primarily by US/crypto-native traders. Local context — polling nuances, coalition dynamics, legal system mechanics, cultural factors — is systematically underrepresented in the price.

**Evidence**:
- Portugal scandal (Jan 2026): $5M surged into presidential election market hours before results. Odds jumped from 60% to 95% as exit polls circulated locally — proving local information was dramatically more valuable.
- Theo ($85M): French trader with private polling methodology crushed US election markets — demonstrating cross-cultural information edge.
- Academic support: geographic information asymmetry in equity markets is well-documented (Baik, Kang & Kim) — local investors have measurable edge, especially on high-asymmetry securities.
- Your European politics research (europe-2026.md) already identified this: "European political markets are priced primarily by non-European traders, creating informational asymmetry."

**Entry rules**:
1. Identify markets about events in geo-restricted countries
2. Develop local knowledge through primary sources (not just English-language media)
3. Compare your locally-informed estimate to the market price
4. Enter when edge > 5pp and your information has a specific, articulable source
5. Prioritize: French 2027 election, UK PM market, Hungarian election, Dutch politics

**Exit rules**: Per the underlying strategy. The information edge persists until the market catches up (typically 1-14 days after information becomes widely available in English).

**Data requirements**: Foreign-language news sources, local polling data, understanding of local political systems. This is S008 (information edge) applied to a specific structural blind spot.

**Feasibility**: 4/5 — The pattern is well-documented and the edge is structural (it persists as long as geo-restrictions exist). The constraint is that these markets tend to be lower-volume, limiting position size. But the Europe research already shows $9.1M on French presidential, $21.6M on Hungarian PM — decent liquidity.

**Should we add?**: YES — this is effectively S008 specialized for European/non-US markets. It's already being practiced informally (your Europe research is exactly this). Formalizing it as a strategy with entry/exit rules makes it repeatable.

---

### S015 — Calendar/Temporal Pattern Exploitation ("The Rhythm Trader")

**Edge hypothesis**: Prediction markets exhibit temporal patterns (time-of-day, day-of-week, weekend effects) analogous to those documented in equity and crypto markets, creating exploitable liquidity rhythm.

**Mechanism**: Polymarket's user base skews US/crypto-native. Volume likely follows US waking hours. Weekend political markets may be thinner. Placing limit orders during low-activity periods (late US night, weekends) may capture wider spreads.

**Evidence**:
- **This is the LEAST researched strategy area.** No academic paper or blog post specifically documents temporal trading patterns on Polymarket.
- Adjacent evidence: Amberdata research on crypto markets shows 87% variation in available liquidity from temporal patterns.
- Polymarket data: 67.7% of markets have cycles under 7 days, 63% of short-term markets have zero 24-hour volume — significant activity clustering.
- Equity markets: robust Monday effects, U-shaped intraday volume, holiday effects all well-documented.
- Raw data is available via Dune Analytics dashboards for analysis.

**Entry rules**: TBD — requires data analysis first. Hypothesized approach:
1. Analyze volume by hour-of-day and day-of-week via Dune Analytics
2. Identify periods of systematically thinner liquidity
3. Place wider limit orders during thin periods, tighter during peak
4. If weekend/overnight drift is detected, fade it during Monday US-hours convergence

**Data requirements**: Dune Analytics queries on Polymarket hourly/daily volume patterns. Historical order book depth data.

**Feasibility**: 2/5 currently (needs primary research). Could become 4/5 if patterns are confirmed. **The absence of published research is itself the opportunity** — if we run the analysis and find patterns, we have first-mover advantage.

**Should we add?**: NOT YET — add to research queue. Run the Dune Analytics analysis first. If patterns emerge, formalize as a strategy. If not, discard. This is a NIGREDO-stage hypothesis that needs data before it deserves a playbook.

---

## Part 3: AI-Native Strategies

### The State of AI Forecasting (February 2026)

| Model/System | Brier Score | Notes |
|---|---|---|
| Human superforecasters | 0.081 | Gold standard |
| GPT-4.5 | 0.101 | Best individual LLM |
| Claude 3.5 Sonnet | 0.119 | |
| AIA Forecaster (Bridgewater) | ~superforecaster | Ensemble + Platt scaling |
| Human crowd (non-expert) | 0.149 | LLMs now beat this |
| 12-LLM ensemble | ~0.149 | Matches crowd (Science Advances) |
| Prediction market prices | ~0.09 | Better than any single LLM |

**Key finding**: No single LLM beats well-calibrated prediction market prices. But **LLM ensemble + market prices beats market prices alone** (Bridgewater AIA Forecaster proof). The AI provides *additive* information.

**LLM-superforecaster parity projected**: Late 2026 (95% CI: Dec 2025 — Jan 2028).

### Calibration is the Bottleneck

LLMs are systematically overconfident at 90%+ probability (wrong 15-32% of the time). This means:
- **Never use raw LLM outputs for trading**
- Platt scaling or isotonic regression is essential (needs ~100+ calibration samples)
- Prompt format matters enormously — structured queries outperform narrative prompts
- The same model given the same question can produce different probabilities across runs

### Practical Architecture

```
S012 Pipeline (recommended)

News/Data ──> Retrieval (RAG) ──> Multi-LLM Analysis ──> Calibration ──> vs Market ──> Human Review
     │              │                    │                     │               │
     ├─ NewsAPI      ├─ ChromaDB          ├─ GPT-4              ├─ Platt        ├─ Flag if |edge| > 5pp
     ├─ On-chain     ├─ Summarize         ├─ Claude             ├─ Historical   ├─ Human decides entry
     └─ Dune         └─ Top-k retrieval   ├─ Open-source        │  calibration  └─ Strategy assignment
                                          └─ Take median        └─ Extremize
```

**The "ilovecircle" case study**: $2.2M profit in 60 days, 74% accuracy. Used neural network + news feeds + social sentiment + on-chain data + Polymarket API. Built with Claude as coding partner. This validates the architecture.

### What AI Can vs Can't Do for Us

**AI advantages**:
- Screen hundreds of markets simultaneously (humans: 5-10)
- Process news in seconds (humans: hours)
- Consistent — no fatigue, emotion, availability bias
- Political questions: LLMs perform notably better than economic
- Uncertain questions (30-70%): LLMs match/beat crowd

**AI limitations**:
- Can't beat well-calibrated markets on its own
- Overconfident at extremes (90%+)
- No genuine causal reasoning
- Knowledge cutoff requires RAG (which introduces retrieval quality as bottleneck)
- Adversarial: if many bots use similar models, they herd toward similar predictions
- Novel/unprecedented events: LLMs extrapolate from training, fail on true black swans

---

## Part 4: Anti-Strategies (What Doesn't Work)

### The Sobering Numbers

- **70% of Polymarket's 1.7M traders lose money** (Reichenbach & Walther 2025, 124M+ trades)
- **Only 0.51% of wallets profit >$1,000** (ChainCatcher, 95M transactions)
- **Top 0.04% captured >70% of all profits** ($3.7B) — extreme power law
- **Average pre-fee return on Kalshi contracts is negative 20%** (Burgi, Deng & Whelan 2026)
- This matches CFD/forex loss rates (62-82% per European regulators)

### The #1 Killer: Win-Rate Trap

At $0.77 entry, you risk $0.77 to win $0.23 — a 3.35:1 ratio against you. One loss wipes out three wins. Trader "beachboy4" lost $2.36M in 35 days with ~51% win rate because of this asymmetry. A trader right 30% on cheap contracts outperforms a trader right 70% on expensive ones.

**Implication for us**: Always calculate expected value, not just directional probability. Position at prices where the risk:reward ratio is favorable, not just where the probability estimate has edge.

### Strategies That Fail in Practice

| Strategy | Why It Fails | Evidence |
|---|---|---|
| **Simple momentum** | 58% of markets show negative serial correlation | Clinton & Huang 2025 |
| **Blind contrarianism** | Buying cheap (<$0.10) contracts loses 60%+ of capital | Kalshi data (Burgi et al.) |
| **Cross-platform arb** (for humans) | Opportunity window compressed to 2.7 seconds; 73% of profits to sub-100ms bots | IMDEA Networks |
| **Technical analysis** | No published evidence of profitability; price is probability converging to binary | No supporting research exists |
| **"Buy the dip"** on declining markets | 73.5% of "by date" markets resolve NO; the decline is correct repricing | Our S006 backtest |
| **Market making** (current era) | Post-election rewards down 10x+, bot competition intense; poly-maker author: "not profitable" | Direct statement from bot creator |

### Structural Risks to Monitor

| Risk | Severity | Documented Case |
|---|---|---|
| **Oracle manipulation** | Catastrophic | $7M Ukraine deal forced to wrong resolution by UMA whale |
| **Wash trading** | High | 25% of Polymarket volume may be fake (Columbia 2025), peaking at 60% |
| **No insider trading rules** | Medium | Politicians can legally bet on their own elections |
| **Zero regulatory enforcement** | Medium | No CFTC actions for prediction market manipulation |
| **Bot frontrunning** | Medium | One bot: $313 → $414,000 in a month exploiting latency |
| **Platform risk** | Low-Medium | Regulatory bans expanding (Netherlands, Portugal, France) |

### What Separates the 0.51% from the Rest

Based on documented evidence, profitable traders:
1. **Specialize deeply** in 1-2 domains (Axios: 96% win rate on Trump markets)
2. **Size correctly** — Kelly criterion or fraction thereof
3. **Invest in information** — Theo: $100K on private polling → $85M profit
4. **Trade infrequently** — 10-30 high-conviction trades/year, not hundreds
5. **Buy structural edge** — time decay, overround arbs, not directional guesses
6. **Understand the asymmetry** — risk:reward matters more than win rate

---

## Part 5: Strategy Evaluation Summary

### For each candidate:

| ID | Name | Edge Hypothesis | Feasibility | Should Add? | Priority |
|---|---|---|---|---|---|
| S009 | Resolution Arbitrage | Ambiguous criteria = mispriced oracle risk | 3/5 | YES (overlay) | Low — niche, small addressable market |
| S010 | Whale Signal | On-chain smart money predicts outcomes | 4/5 | YES (signal) | Medium — good confirmation signal |
| S011 | High-Prob Bond | >95% contracts as yield instrument | 4/5 | YES (capital mgmt) | Medium — idle bankroll deployment |
| **S012** | **LLM Ensemble** | **AI + market > market alone** | **4/5** | **YES (core)** | **HIGH — highest leverage new strategy** |
| S013 | Temporal Spread | Nested deadline mispricing | 3/5 | YES (S007 extension) | Medium — extends existing S007 |
| **S014** | **Geo-Restriction Edge** | **Blocked users = blind market** | **4/5** | **YES (core)** | **HIGH — already practicing informally** |
| S015 | Calendar Patterns | Temporal liquidity exploitation | 2/5 | NOT YET | Research first — run Dune analysis |

---

## Part 6: Conclusions

### Top 3 New Strategies Worth Pursuing

1. **S012 — LLM Ensemble Screener** (highest leverage)
   - Evidence: AIA Forecaster proves AI + market beats market alone. ilovecircle: $2.2M in 60 days.
   - Action: Build ensemble with 3 LLMs, log estimates against market prices, build calibration dataset. Start with S006 screening — use AI to scan hundreds of "by date" markets.
   - This multiplies our S008 research capacity by 10-100x.

2. **S014 — Geo-Restriction Edge** (already practicing)
   - Evidence: Portugal scandal (35pp price move when local info arrived), academic literature on geographic information asymmetry.
   - Action: Formalize the European politics research (europe-2026.md) as S014. Add entry/exit rules. Prioritize French 2027, UK PM, Hungary.
   - We already have the edge — formalizing it makes it repeatable.

3. **S011 — High-Probability Bond Rotation** (capital efficiency)
   - Evidence: documented 5.5%+ annualized beating T-bills, high-probability contracts underpriced per favorite-longshot bias.
   - Action: Screen for >95% contracts with <7 day resolution. Deploy idle bankroll between directional trades.
   - Turns dead capital into working capital.

### Top 3 Strategies That Sound Good But Probably Don't Work

1. **Cross-platform arbitrage** (for humans)
   - Average opportunity window: 2.7 seconds. 73% of profits to sub-100ms bots. The $40M/year was real, but it's an arms race we can't win without infrastructure investment. Dead for manual traders.

2. **Market making / liquidity provision** (current era)
   - Was profitable in 2024 ($200-800/day). Now: rewards down 10x, bot competition intense, the poly-maker author explicitly says it loses money. The edge was the liquidity rewards subsidy, not the spread — and the subsidy shrank.

3. **Calendar/temporal pattern trading** (unproven)
   - No published evidence that prediction markets have exploitable temporal patterns. It MIGHT exist (crypto markets show 87% liquidity variation by time), but nobody has confirmed it for Polymarket. Needs primary research before deploying capital.

### The Biggest Structural Edge Unique to Prediction Markets

**The neg-risk conversion mechanism in multi-outcome markets.**

This is the single most important structural feature that has no analogue in traditional finance. It enables:
- Capital-efficient spread trading (S013)
- Overround arbitrage where you can cheaply short every longshot simultaneously (S007)
- 29x capital efficiency vs. trading each outcome independently
- $40M in documented extraction (73% from neg-risk mechanics)

The neg-risk mechanism is what makes prediction market arbitrage fundamentally different from — and potentially more accessible than — traditional financial arbitrage. In equities, you need a borrow locate, margin, and counterparty risk to short. On Polymarket, shorting a candidate costs the same as going long on all others, and the collateral requirement is minimal.

**Our S007 (Cross-Market Arb) is already positioned to exploit this, but we should make neg-risk conversion the FIRST thing we check on every multi-outcome market entry.** The overround check (sum of YES prices > 100%) should be automated — this is where S012 (LLM screener) feeds directly into S007.

---

### S016 — Insider Follow ("The Intelligence Trader")

**Edge hypothesis**: Mathematically-identified insiders — accounts with statistically significant, localised edge in specific sub-domains (detected by L01→L02→L03 pipeline) — provide the highest-confidence follow signal when trading in their dominant field.

**Parent**: S010 (Whale Signal) + L04 intelligence pipeline
**Mechanism**: 4-gate decision framework (field match → direction check → timing quality → price impact). Insider Conviction Multiplier (ICM) adjusts sizing from 0.5x to 2.0x standard.

**Key distinction from S010**: S010 tracks manually-curated whales by P&L. S016 uses the localisation test (L02) to distinguish between genuine insiders (extreme edge in 1-2 categories) and superforecasters (broad positive edge). Only follows insiders in their dominant sub-domain.

**Entry rules**: All 4 gates pass + ICM >= 0.8 + independent estimate exists + bankroll caps respected.
**Exit rules**: Per underlying strategy. S016 is a modifier, not standalone.

**Tools**: `scripts/l04-follow-monitor.py`, `data/follow-signals.jsonl`
**Playbook**: `strategies/playbooks/S016-insider-follow.md`

**Feasibility**: 4/5 — Framework built, whale-registry operational as fallback. Full activation requires L01-L03 pipeline to produce classified-insiders.json with real data.

**Should we add?**: YES — already added. This formalises the "when to follow a whale" decision that S010 left informal. The 4-gate framework prevents the cardinal sin (following outside field match) and the ICM provides evidence-based sizing.
