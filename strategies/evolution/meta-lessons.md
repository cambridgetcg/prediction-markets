# Meta-Lessons

*Cross-strategy patterns. What works, what doesn't, and why.*

## Structure

Each lesson has:
- **Pattern**: What was observed
- **Source**: Which strategies/trades revealed it
- **Evidence**: Specific data points
- **Implication**: What to do differently
- **Applied**: Whether this was fed into strategy evolution

---

*Pre-trade theoretical lessons from research. To be validated/invalidated by live trades.*

---

### Lesson T01: Domain Efficiency Is Not Uniform

**Pattern**: Prediction market efficiency varies dramatically by domain. ECO (Fed decisions) is near-perfect (Kalshi perfect forecast record 2022-2024). GEO and CRY are the least efficient (emotional participants, fear/greed overpricing, retail-dominated).

**Source**: S02 strategy-domain fit analysis; Kalshi/NBER Fed study; 2024 election market analysis (cross-platform divergences, negative daily autocorrelation)

**Evidence**: Kalshi perfect on Fed. PredictIt 93% but Polymarket only 67% on same 2024 elections. GEO markets assigned 58% to events experts dismissed. Overall prediction market Brier score ~0.09 (good), but variance across domains is high.

**Implication**: Concentrate strategy deployment in inefficient domains (GEO, CRY, POL multi-outcome) rather than spreading evenly. Don't try to beat efficient domains (ECO, FIN) on calibration — trade structure instead.

**Applied**: Yes — strategy-domain-matrix.md (2026-02-23)

---

### Lesson T02: Only 0.51% Win

**Pattern**: Only 0.51% of Polymarket wallets profit >$1,000. 85-90% of retail accounts end with net losses. The base rate for prediction market trading profitability is extremely low.

**Source**: ChainCatcher analysis of 95M on-chain Polymarket transactions

**Evidence**: $85M single trader (Theo, information arbitrage outlier), $40M cross-platform arb aggregate, $4.2M speed trading aggregate. But vast majority lose.

**Implication**: Humility as default stance. Every strategy needs proof of edge before scaling. Paper trading first. The null hypothesis is that we lose money. Calibration system is not optional — it's the survival mechanism.

**Applied**: Yes — reinforces NIGREDO phase for all strategies

---

### Lesson T03: Fear Overprices Time Premium in Geopolitical Markets

**Pattern**: "Will X happen by [date]?" geopolitical markets are systematically overpriced because availability bias + salience + base rate neglect creates an exploitable wedge between implied daily hazard rate and historical base rate.

**Source**: S006 analysis applied to GEO domain; Iran strike market data; base rate reasoning from GEO/context.md

**Evidence**: "Iran strikes by March 31" at 57% with 37 days → implied daily p = ~2.3%. Historical base rate for US military action (elevated tensions): ~0.3%/day. 7x overprice. The math survives even with large error bars on base rate.

**Implication**: S006-GEO is the most defensible first trade. The edge is mathematical, not directional. Even if the base rate estimate is wrong by 3x, the implied probability is still overpriced.

**Applied**: Yes — strategy-domain-matrix.md ranks S006-GEO #1 for first paper trades

---

### Lesson T04: Structural Strategies Beat Directional Strategies in Efficient Domains

**Pattern**: In domains with sophisticated participants (ECO, FIN), directional strategies (S001, S004, S005, S008) underperform structural strategies (S003, S006, S007). In inefficient domains (GEO, CRY), directional strategies have more room.

**Source**: S02 strategy-domain compatibility analysis; Kalshi perfect record evidence; TradFi spillover reasoning

**Evidence**: ECO pros process data in seconds (no S004 overreaction to fade). FIN research edge is priced in underlying markets first (no S008 edge). But S003 catalyst timing and S007 structural arbs work regardless of participant sophistication — they exploit market structure, not human error.

**Implication**: Classify domains as "structural only" (ECO, FIN) vs "directional + structural" (GEO, CRY, POL). Match strategy type to domain type.

**Applied**: Yes — ECO/FIN recommended strategies emphasize S003/S006/S007 only

---

### Lesson T05: Domain Specialization Is the Documented Winner

**Pattern**: Across all documented Polymarket success stories, domain specialists dramatically outperform generalists. Concentrated expertise in a narrow field produces the highest risk-adjusted returns.

**Source**: Polymarket leaderboard analysis; "Axios" 96% win rate on Trump statements; HyperLiquid0xb $1.4M from sports; Theo's $85M from political polling methodology

**Evidence**: Top traders execute only 10-30 trades/year with extremely high conviction. Generalist approaches produce mediocre returns diluted across domains.

**Implication**: After initial paper trading across domains, specialize. Pick 2-3 domains where calibration proves strongest and go deep. The strategy-domain matrix identifies candidates: GEO, POL, and LAW/TEC as secondary.

**Applied**: Yes — strategy-domain-matrix.md includes domain prioritization tiers

---

### Lesson T06: Favorite-Longshot Bias Is Real and Exploitable

**Pattern**: Longshots are systematically overbet; favorites are underbet. Betting on favorites yields avg -3.64% loss; betting on underdogs yields avg -26.08% loss. The gap is the exploitable inefficiency.

**Source**: NBER working paper on prospect theory in betting markets; Journal of Political Economy; Management Science studies

**Evidence**: Context-dependent: few-outcome markets show favorite bias; many-outcome markets show longshot bias. Multi-outcome political markets (nomination fields) likely exhibit longshot bias — too much money on fringe candidates.

**Implication**: In multi-outcome POL markets (S007), buying NO on overpriced longshots is the highest-probability edge. In binary markets, slight favorite bias means buying slightly underpriced favorites (high-probability bonds).

**Applied**: Yes — POL recommended strategies emphasize S007 overround scanning

---

### Lesson T07: Cross-Platform Arbitrage Windows Are Compressing

**Pattern**: Cross-platform arb (Polymarket vs Kalshi vs PredictIt) yielded $40M in 2024-2025 but institutional competition is compressing windows from minutes to seconds. Open-source bots exist.

**Source**: ChainCatcher analysis; cross-platform arb studies; 2024 election arb data

**Evidence**: Top 3 arb wallets earned $4.2M at 7.5% returns within hours. But "settlement definition differences" create risk (e.g., "government shutdown" defined differently across platforms).

**Implication**: S007 Type 4 (cross-platform) is declining in viability. Focus S007 on Type 1 (overround) and Type 2 (temporal consistency) arbs within Polymarket. These are less competed because they require domain understanding, not just speed.

**Applied**: Yes — S007 recommendations focus on intra-platform structural arbs

### Lesson T08: Overreaction Is the Dominant Short-Term Price Pattern

**Pattern**: 58% of high-profile Polymarket markets show negative serial correlation — prices that spike one day systematically reverse the next. This is the single strongest documented inefficiency in prediction markets.

**Source**: S004 backtest; Clinton & Huang (2025) — 2,500+ markets, $2.4B volume; Augenblick et al. (2025) — experimental manipulation study

**Evidence**: Clinton & Huang found negative daily autocorrelation in 58% of Polymarket's 2024 presidential markets. Augenblick et al. found ~40% reversion within 7 days after a 5pp shock. Reversion is front-loaded (fast in days 1-7, then slows dramatically). Sung et al. (2019) confirmed systematic overreaction across 6,058 markets.

**Implication**: S004 has a quantified edge. Entry should be 24-72h post-spike, holding 3-7 days (not 14 as originally hypothesized). Target 40% retracement (not 50%). GEO and CRY are the primary domains.

**Applied**: Yes — S004 playbook refined with evidence-based parameters (2026-02-23)

---

### Lesson T09: 70% of Polymarket Traders Lose — This Is the Edge Source

**Pattern**: Only 30% of Polymarket traders earn positive profits, and this share decreases over time. The majority of participants are unsophisticated retail traders who systematically overpay for dramatic outcomes and overtrade the YES side.

**Source**: S004 backtest; Reichenbach & Walther (2025) — 124M+ trades, ~1M traders

**Evidence**: 70% negative P&L. Documented "Yes" bias (systematic overtrading of YES/default option). Inaccuracies concentrate early in contract lifecycle and near resolution. Profitable traders are persistent — skill exists and is learnable. PredictIt ($850 limit, fees, KYC) achieved 93% accuracy vs. Polymarket's 67% on the same 2024 elections — suggesting more money ≠ more wisdom when participant sophistication is low.

**Implication**: The counterparty pool IS the edge. Contrarian strategies (S004) and structural strategies (S006, S007) work because they trade against the 70% who lose. The Yes bias specifically means fading YES spikes has a structural tailwind. Focus on high-volume markets where the retail pool is largest.

**Applied**: Yes — S004 playbook updated to prefer fading YES spikes

---

### Lesson T10: Weekly Drift Is More Exploitable Than Daily Spikes

**Pattern**: Daily price spikes (>10% in 24h) are often driven by actual information (resolution events, confirmed data). Weekly movements (>15% in 7 days) more reliably represent emotional drift that reverts — this is the sweet spot for S004.

**Source**: S004 backtest — spike classification of 40 active market movers (2026-02-23)

**Evidence**: Of 20 daily movers, only ~25% were classified as emotional (Type B). Of 20 weekly movers, ~35% were emotional. Daily spikes include many resolution events (date passed, data released). Weekly drift accumulates sentiment-driven mispricing without a single structural catalyst.

**Implication**: S004's trigger should weight weekly movements (≥20% in 7 days) at least equally with daily spikes (≥10% in 24h). The weekly timeframe also gives more time to classify and enter (24-72h window vs. rushed daily reaction).

**Applied**: Yes — S004 trigger expanded to include weekly threshold (2026-02-23)

---

### Lesson T11: Neg-Risk Is the Core Structural Advantage

**Pattern**: The neg-risk conversion mechanism in multi-outcome markets is the single most important structural feature unique to prediction markets. It enables 29x capital efficiency and generated 73% of documented arbitrage profits from only 8.6% of opportunities.

**Source**: "Unravelling the Probabilistic Forest" (IMDEA 2025) — 86M bids/transactions on Polymarket, Apr 2024 - Apr 2025

**Evidence**: $40M in realized arbitrage profit. Neg-risk rebalancing: 73% of profits from 8.6% of opportunities. Need 2.5-3% overround to profit after 2% winner fee.

**Implication**: Every multi-outcome market entry should first check the neg-risk math. S007 overround scanning should be the FIRST filter on all multi-outcome markets. Automating this check (via S012 LLM screener or a simple script) would multiply coverage.

**Applied**: Yes — S013 (Temporal Spread) formalized for nested deadlines; S007 emphasis on neg-risk mechanics (2026-02-23)

---

### Lesson T12: AI + Market > Market Alone

**Pattern**: No single LLM beats well-calibrated prediction market prices. But an LLM ensemble combined with market consensus beats market consensus alone. The AI provides additive information.

**Source**: AIA Forecaster (Bridgewater AIA Labs, 2025); "Wisdom of the Silicon Crowd" (Science Advances 2024); ForecastBench (ICLR 2025); Schoenegger/Tetlock (2024)

**Evidence**: GPT-4.5 Brier 0.101 vs superforecasters 0.081 vs market prices ~0.09. AIA Forecaster + market consensus outperforms consensus alone. 12-LLM ensemble matches human crowd. LLM assistants improve human forecasting 24-41%. ilovecircle bot: $2.2M in 60 days at 74% accuracy.

**Implication**: The optimal architecture is AI screens + human decides. Don't replace S008 human research with AI — augment it. Log every LLM probability estimate alongside market price and outcome to build calibration dataset. Platt scaling is essential (LLMs are overconfident at 90%+).

**Applied**: Yes — S012 (LLM Ensemble Screener) designed (2026-02-23)

---

### Lesson T13: The Win-Rate Trap Is the #1 Retail Killer

**Pattern**: Confusing win rate with profitability is the most common failure mode. At $0.77 entry: risk $0.77 to win $0.23 (3.35:1 against). One loss wipes three wins. Trader "beachboy4" lost $2.36M in 35 days with ~51% win rate.

**Source**: Reichenbach & Walther 2025 (124M+ trades); QuantJourney analysis; Kalshi economics (Burgi, Deng & Whelan 2026)

**Evidence**: 70% of traders lose money. Average pre-fee Kalshi return: -20%. Top 0.04% captured >70% of profits ($3.7B). Power law distribution matches CFD/forex.

**Implication**: Always calculate expected value (edge * payoff), not just directional probability. Quarter-Kelly sizing (already our policy) is correct. Track EV per trade, not win rate. A 30% win-rate strategy on cheap contracts can dominate a 70% win-rate strategy on expensive contracts.

**Applied**: Yes — reinforces position sizing discipline; S011 (High-Prob Bond) explicitly addresses the risk:reward math at 95%+ levels (2026-02-23)

---

### Lesson T14: Geo-Restriction Creates Structural Information Asymmetry

**Pattern**: With 33+ countries blocked from Polymarket, markets on local events in those countries are systematically mispriced because the most informed participants cannot trade.

**Source**: Portugal gambling authority (Jan 2026); Theo case study ($85M); geographic information asymmetry literature (Baik, Kang & Kim)

**Evidence**: Portugal presidential election market moved 35pp in 2 hours when local exit polls circulated. Theo (French trader) used private polling methodology to exploit US election markets. Academic literature confirms local institutional investors have measurable information advantage.

**Implication**: European, Latin American, and other geo-restricted political markets are our best non-US hunting ground. Develop local-language news sources. The edge is structural and persists as long as the geo-restrictions exist (and they're expanding, not contracting). Our europe-2026.md research is already S014 in practice.

**Applied**: Yes — S014 (Geo-Restriction Edge) designed (2026-02-23)

---

## Questions to Answer Over Time

1. **Does domain expertise translate to prediction edge?** (S008 test)
2. **Is mean reversion or momentum more common?** (S004 vs S005)
3. **Do "by date" markets systematically overprice?** (S006 test)
4. **Which information edge type (A-E) is most reliable?** (S008 subtypes)
5. **Does position sizing matter more than entry quality?** (S002 variants)
6. **Are there domains where markets are consistently inefficient?** (cross-domain comparison)
7. **How fast do mispricings correct?** (S007 + S008 timing data)
8. **Does research time correlate with edge quality?** (S008 effort tracking)
9. **Can LLM ensemble screening identify tradeable mispricings at scale?** (S012 test)
10. **Do on-chain whale signals predict outcomes better than market prices?** (S010 test)
11. **Do temporal patterns exist in Polymarket volume/spreads?** (R01 data analysis)
12. **What is the true failure rate of 95%+ contracts?** (S011 bond risk quantification)
13. **Does the geo-restriction edge persist across resolution?** (S014 — does local info eventually reach the market before resolution, or does it remain mispriced?)
