# Strategy-Domain Fit Matrix

*Which strategies work in which domains — and why.*

---

## 1. Domain Characteristics

| Domain | Info Density | Participant Sophistication | Liquidity | Volatility | Resolution Clarity | Time Horizons | Structural Features |
|--------|-------------|---------------------------|-----------|-----------|-------------------|---------------|-------------------|
| **GEO** | Med-High (OSINT, diplomatic signals; hard to interpret) | Low-Med (crypto-native retail, few experts; govt insiders create extreme asymmetry) | Growing fast ($155M single market); historically thin | Very High (rhetoric → spikes) | Mixed (what counts as "strike"?) | Med-Long ("by date" common) | Nested deadlines, conditional chains |
| **POL** | Very High (polls, ratings, debates, historical analogues) | High (political junkies, data scientists, former operatives) | Highest ($2.4B on 2024 election) | Low-Mod (spiky around primaries/debates) | Very Clear (elections are definitive) | Long (years for presidential) | Multi-outcome fields, binary generals, clear calendars |
| **ECO** | Very High (scheduled releases, professional analysis industry) | Very High (Fed watchers, rates traders, economists) | Deep for FOMC; moderate for secondary | Low (well-telegraphed); higher for surprise data | Extremely Clear (numbers are numbers) | Short-Med (FOMC every 6 weeks) | Scheduled events, "by date" structure, rate path conditionals |
| **FIN** | Highest (real-time prices, filings, earnings, analyst coverage) | Highest (TradFi pros, quants, algo traders) | Moderate on Polymarket specifically | Moderate (driven by underlying markets) | Very Clear (stock prices, market cap) | Short-Med | Binary price targets, multi-outcome, live price feeds |
| **CRY** | High but noisy (on-chain, social media, exchange flows) | Low-Med (retail-heavy, narrative-driven, high risk tolerance) | Moderate ($167M+ active; ~25% may be wash trading) | Very High (crypto-native participants swing hard) | Clear for price targets; murky for regulatory Qs | Short-Med (monthly targets common) | "By date" price targets, multiple correlated markets |
| **TEC** | High for product launches; moderate for milestones | Med-High (tech enthusiasts, some industry insiders) | Moderate (AI markets growing) | Low-Mod (gradual except launch days) | Mixed (what counts as "GPT-5 launch"?) | Med-Long | Binary, some multi-outcome ("best model"), few "by date" |
| **SCI** | High but specialized (papers, trials, committee decisions) | Low (very few domain experts trading) | Very Low (Metaculus better for this) | Low (occasional breakthrough spikes) | Usually Clear (Nobel, trial pass/fail) | Long (months-years) | Multi-outcome (Nobel candidates), binary milestones |
| **SOC** | Medium (pop culture, social media, entertainment) | Low (casual bettors, entertainment fans) | Moderate for entertainment; low for niche | Moderate (rumors, announcements) | Usually Clear (release dates, award winners) | Short-Med | Binary and multi-outcome, event calendars known |
| **LAW** | High but arcane (filings, calendars, legal analysis) | Low-Med (legal experts rarely trade; some informed hobbyists) | Low-Mod (niche) | Low normally; spiky on ruling days | Very Clear (court rules or doesn't) | Med-Long (known schedules, frequent delays) | Binary rulings, "by date" regulatory deadlines |
| **ENV** | Low for prediction markets (climate data exists but rarely marketized) | Low (few participants) | Very Low (minimal Polymarket coverage) | Low (climate/energy changes slowly) | Mixed ("hottest year" clear; policy less so) | Long | Binary, very few markets, better on Metaculus |

---

## 2. Strategy-Domain Compatibility Matrix

**Scale**: 1 = Avoid, 2 = Poor fit, 3 = Moderate, 4 = Good fit, 5 = Ideal terrain

| Strategy | GEO | POL | ECO | FIN | CRY | TEC | SCI | SOC | LAW | ENV |
|----------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| **S001 Hold** | 4 ★ | 3 | 2 | 2 | 3 | 4 ★ | 4 ★ | 2 | 4 ★ | 2 |
| **S002 Threshold** | 5 ★★ | 3 | 2 | 3 | 5 ★★ | 2 | 1 | 3 | 2 | 1 |
| **S003 Catalyst** | 4 | 5 ★★ | 5 ★★ | 4 | 3 | 4 | 3 | 4 | 5 ★★ | 2 |
| **S004 Contrarian** | 5 ★★ | 4 ★ | 2 | 2 | 5 ★★ | 3 | 2 | 3 | 3 | 1 |
| **S005 Momentum** | 3 | 4 ★ | 2 | 3 | 4 ★ | 3 | 1 | 3 | 2 | 1 |
| **S006 Time Decay** | 5 ★★ | 3 | 3 | 2 | 4 ★ | 3 | 3 | 2 | 3 | 2 |
| **S007 Arb** | 4 ★ | 5 ★★ | 3 | 3 | 3 | 3 | 2 | 2 | 2 | 1 |
| **S008 Info Edge** | 5 ★★ | 4 ★ | 3 | 2 | 3 | 4 ★ | 5 ★★ | 2 | 4 ★ | 3 |

*★★ = Ideal pairing (5/5). ★ = Strong pairing (4/5).*

### Making Suitability by Domain (P04)

How suitable is each domain for market making? Based on volatility, liquidity depth, bot competition, and spread characteristics. See `strategies/playbooks/P04-marketmaker-yield.md` for full analysis.

| Domain | Making Suitability | Key Factor | Best Candidate Markets |
|--------|-------------------|-----------|----------------------|
| **ECO** | 5 ★★ | Scheduled events, slow between meetings, clear resolution | Fed rate decisions, economic indicators |
| **POL** | 4 ★ | Long-duration (2028), stable probabilities, deep liquidity | Presidential/nomination markets |
| **SOC** | 4 ★ | Entertainment moves slowly, low delta risk | Celebrity/cultural event markets |
| **LAW** | 3 | Slow between rulings, but very low volume limits fills | Court ruling "by date" markets |
| **TEC** | 3 | Moderate, but launch-day spikes create risk windows | AI model/product timeline markets |
| **GEO** | 2 | High rhetoric-driven volatility, inventory risk severe | Avoid "by date" strike markets |
| **CRY** | 1 | Extreme volatility, worst domain for making | Fee-enabled but risk > rebate |
| **FIN** | 1 | Correlated to volatile underlying, TradFi bots dominate | Avoid entirely |
| **SCI** | 1 | Too illiquid, zero fill opportunities | No viable markets |
| **ENV** | 1 | No markets exist | N/A |

**Rule**: Only consider making in domains scoring 3+. In domains scoring 1-2, the inventory risk exceeds spread capture for a manual maker.

### Psychological Edge Score (B02)

How susceptible is each domain to emotional mispricings? Higher = more exploitable via behavioral strategies (S004, S006, S008).

| Domain | Psych Edge Score | Primary Bias Exploited | Avg Gap (pp) | ECI Threshold for S004 | Practical Score |
|--------|-----------------|----------------------|-------------|----------------------|----------------|
| **GEO** | **9/10** | Fear Premium + Availability + YES bias | 5-15 | ≥6 | **9** (high liquidity) |
| **CRY** | **8/10** | FOMO + Hope Premium + Narrative | 5-15 | ≥6 | **7** (~25% wash trading) |
| **SCI** | **7/10** | Hope Premium + Base Rate Neglect | 5-10 | ≥7 | **2** (no liquidity) |
| **ENV** | **7/10** | Hope Premium + Narrative | Unknown | N/A | **1** (no markets) |
| **LAW** | **6/10** | Deadline Panic + Narrative | 3-8 | ≥6 | **5** (moderate liquidity) |
| **POL** | **6/10** | Motivated Reasoning + Identity-Protective | 3-10 | ≥5 (identity markets) | **6** (highest liquidity) |
| **TEC** | **5/10** | Hype Cycle + Representativeness | 3-8 | ≥7 | **5** (moderate liquidity) |
| **SOC** | **3/10** | Social Proof + Recency | 2-5 | ≥7 | **3** (moderate liquidity) |
| **ECO** | **1/10** | Recency (minimal) | 0-2 | N/A (skip S004) | **1** (pros dominate) |
| **FIN** | **1/10** | None reliable | 0-2 | N/A (skip S004) | **1** (TradFi mirror) |

*Source: `psychology/participant-profiles.md` and `psychology/news-emotion-price-taxonomy.md` (B02)*

**Reading this table**: Deploy behavioral strategies (S004 fade, S006 time decay, S008 disconfirming research) in domains with Practical Score ≥ 5. In domains scoring 1-2, only use catalyst (S003) or structural (S007) strategies. The Psych Edge Score measures theoretical susceptibility; the Practical Score adjusts for liquidity constraints.

---

## 3. Cell-by-Cell Rationale

### GEO (Geopolitics) — The Overpriced Fear Factory

| Strategy | Score | Rationale |
|----------|-------|-----------|
| S001 Hold | 4 | Rich OSINT, base rate reasoning gives edge over fear-driven retail. Insiders are the risk. |
| S002 Threshold | 5 | Extreme volatility: rhetoric spikes 15-20% in 24h, then reverts. Thresholds trigger frequently. |
| S003 Catalyst | 4 | Summit meetings, treaty deadlines, UN sessions. But many catalysts are unpredictable (escalation is emergent). |
| S004 Contrarian | 5 | War rhetoric → panic spikes → mean reversion. Textbook contrarian terrain. Emotional > structural moves. |
| S005 Momentum | 3 | Escalation ladders create real trends, but regime changes are sudden. Hard to distinguish from spikes. |
| S006 Time Decay | 5 | "Strike by [date]" markets everywhere. Fear systematically overprices. Base rate: threats ≫ action historically. |
| S007 Arb | 4 | Nested deadlines (by March/June/Dec) create temporal consistency arbs. Type 2 arb terrain. |
| S008 Info Edge | 5 | Highest info asymmetry. OSINT, satellite imagery, diplomatic analysis. Research effort pays off enormously. |

### POL (Politics) — The Efficient Calendar

| Strategy | Score | Rationale |
|----------|-------|-----------|
| S001 Hold | 3 | Sophisticated participants compete. Edge exists but is harder to find. Good calibration test domain. |
| S002 Threshold | 3 | Debate/poll swings create moderate volatility. Less extreme than GEO/CRY. |
| S003 Catalyst | 5 | Richest scheduled event calendar: elections, primaries, debates, conventions, appointment announcements. |
| S004 Contrarian | 4 | Partisan motivated reasoning causes emotional overreaction. Debate gaffe panic. Strong but less dramatic than GEO. |
| S005 Momentum | 4 | Primary momentum ("Big Mo"), polling trends, narrative shifts. Classic momentum domain. Tetlock-documented. |
| S006 Time Decay | 3 | Some "by date" structure but less common than GEO. "Will X happen before midterms" type markets. |
| S007 Arb | 5 | Multi-outcome nomination markets (candidates should sum to ~100%). Overround arbs. Richest arb surface. |
| S008 Info Edge | 4 | High info density. Polling internals, historical analogues, demographic modeling. Competition exists but so does edge. |

### ECO (Economics) — The Efficient Machine

| Strategy | Score | Rationale |
|----------|-------|-----------|
| S001 Hold | 2 | Kalshi maintained perfect forecast record on Fed decisions. Extremely hard to out-calibrate professionals. |
| S002 Threshold | 2 | Low volatility. Markets converge efficiently post-data. Thresholds rarely hit. |
| S003 Catalyst | 5 | Most predictable catalyst calendar in all domains: FOMC meetings, CPI, jobs, GDP. All scheduled. |
| S004 Contrarian | 2 | Professionals rarely overreact. Markets efficient within seconds of data releases. |
| S005 Momentum | 2 | Fed decisions are discrete events, not trends. Rate paths known. No slow information digestion. |
| S006 Time Decay | 3 | "Fed cuts by [date]" markets exist. Pros trade these efficiently, but retail overprices occasionally. |
| S007 Arb | 3 | Linked Fed outcomes (rate path conditionals). Some structural arbs between related decisions. |
| S008 Info Edge | 3 | High info density but low effort barrier. Bloomberg, Fed Funds futures already price efficiently. Edge only at margins. |

### FIN (Financial Markets) — TradFi Spillover

| Strategy | Score | Rationale |
|----------|-------|-----------|
| S001 Hold | 2 | TradFi pros trade these. Correlated with highly efficient financial markets. Little calibration edge. |
| S002 Threshold | 3 | Moderate volatility from underlying market swings. Thresholds can hit on earnings surprises. |
| S003 Catalyst | 4 | Earnings reports, product launches, market events. Good catalyst density. Clear calendar. |
| S004 Contrarian | 2 | Efficient markets with sophisticated participants. Overreaction rare or quickly arbitraged. |
| S005 Momentum | 3 | Correlated with equity trends. Moderate opportunity, but prediction markets lag underlying. |
| S006 Time Decay | 2 | Less "by date" structure. More about "will stock reach X?" which tracks underlying, not time premium. |
| S007 Arb | 3 | Multi-outcome ("largest company"), connected to live prices. Arb against underlying market possible. |
| S008 Info Edge | 2 | Extremely competitive info environment. Any research edge is already priced in traditional markets first. |

### CRY (Crypto) — The Emotional Rollercoaster

| Strategy | Score | Rationale |
|----------|-------|-----------|
| S001 Hold | 3 | Can out-calibrate crypto retail on fundamentals. But noise level is extreme. Market may not converge to truth. |
| S002 Threshold | 5 | Highest volatility domain. BTC swings 10-20%+ weekly. Thresholds hit constantly. Perfect terrain. |
| S003 Catalyst | 3 | Halving cycles, ETF decisions, regulatory rulings scheduled. But many catalysts are surprise (Elon tweets, hacks). |
| S004 Contrarian | 5 | Most emotional participants. FUD/hype cycles create textbook overreactions. Reliable mean reversion on panic. |
| S005 Momentum | 4 | Crypto narratives persist for weeks (bull/bear cycles). Strong momentum effects documented. |
| S006 Time Decay | 4 | "BTC above X by [date]" common. Fear/greed overprices. Monthly targets tractable. |
| S007 Arb | 3 | Multiple BTC price targets. Cross-platform possible. Wash trading complicates volume signals. |
| S008 Info Edge | 3 | On-chain data, exchange flows give some edge. But market is noisy — edge may not be priced even when correct. |

### TEC (Technology & AI) — The Insider's Domain

| Strategy | Score | Rationale |
|----------|-------|-----------|
| S001 Hold | 4 | Following AI research closely (arxiv, benchmarks) gives real calibration edge. Moderate competition. |
| S002 Threshold | 2 | Low volatility. Gradual price discovery. Thresholds rarely triggered. |
| S003 Catalyst | 4 | Product launches (WWDC, GTC, I/O), benchmark releases, conference dates. Good catalyst density. |
| S004 Contrarian | 3 | Some AI hype overreaction. Less dramatic than GEO/CRY. Moderate opportunity. |
| S005 Momentum | 3 | AI model leapfrogging creates narratives. But timescale is long and resolution fuzzy. |
| S006 Time Decay | 3 | "GPT-5 by [date]" type markets. Moderate time decay opportunity. Resolution clarity is the risk. |
| S007 Arb | 3 | "Best AI model" multi-outcome markets. Some overround. Moderate surface area. |
| S008 Info Edge | 4 | Following arxiv papers, understanding benchmarks, industry insider knowledge. Genuine effort barrier. |

### SCI (Science & Health) — The Expert's Paradise (Liquidity Desert)

| Strategy | Score | Rationale |
|----------|-------|-----------|
| S001 Hold | 4 | Scientific literacy is extremely rare among market participants. Huge calibration edge. Liquidity is the constraint. |
| S002 Threshold | 1 | No volatility. Markets barely move. Thresholds will never trigger. |
| S003 Catalyst | 3 | Nobel dates, clinical trial readouts, conference presentations. Known but sparse. |
| S004 Contrarian | 2 | No spikes to fade. Market too thin for overreaction patterns. |
| S005 Momentum | 1 | No trends in prediction market sense. Scientific progress too gradual for trading timescales. |
| S006 Time Decay | 3 | "Space mission by [date]" type markets. Base rates knowable. But liquidity limits position size. |
| S007 Arb | 2 | Few connected markets. Very limited arb surface area. |
| S008 Info Edge | 5 | Highest potential edge. Scientific domain expertise vs. uninformed participants. Documented in replication market studies. |

### SOC (Society & Culture) — The Fun Money Zone

| Strategy | Score | Rationale |
|----------|-------|-----------|
| S001 Hold | 2 | Hard to have systematic calibration edge on pop culture. Whimsical outcomes. |
| S002 Threshold | 3 | Moderate swings on rumors/announcements (game delays, award favorites shifting). |
| S003 Catalyst | 4 | Release dates, award ceremonies, sporting events. Clear calendars, fun to trade. |
| S004 Contrarian | 3 | Pop culture overreaction (celebrity drama, leaks, trailer releases). Moderate. |
| S005 Momentum | 3 | Cultural hype cycles, entertainment buzz. Some momentum, but outcomes are discrete events not trends. |
| S006 Time Decay | 2 | Some "by date" but outcomes rarely fear-driven. No systematic time premium overpricing. |
| S007 Arb | 2 | Mostly standalone markets. Limited connected outcomes. |
| S008 Info Edge | 2 | Pop culture edge is fleeting and low-value. Hard to systematize research. |

### LAW (Legal & Regulatory) — The Arcane Edge

| Strategy | Score | Rationale |
|----------|-------|-----------|
| S001 Hold | 4 | Legal reasoning ability is rare. Reading filings, understanding precedent — few participants can do this. |
| S002 Threshold | 2 | Low volatility except on ruling days (then it's resolution, not a swing to trade). |
| S003 Catalyst | 5 | Court calendars, oral argument dates, regulatory deadlines. Most predictable catalyst structure. |
| S004 Contrarian | 3 | Media dramatizes legal outcomes. Some overreaction to legal news. Moderate. |
| S005 Momentum | 2 | Legal outcomes are discrete. Regulatory shifts happen at specific moments, not as trends. |
| S006 Time Decay | 3 | "Regulation by [date]" markets. Deadlines frequently slip, making NO the base case. |
| S007 Arb | 2 | Mostly standalone binary markets. Limited connected outcomes. |
| S008 Info Edge | 4 | Legal domain expertise = massive edge. Court filing analysis, precedent research, regulatory history. Few do this. |

### ENV (Environment & Energy) — The Ghost Town

| Strategy | Score | Rationale |
|----------|-------|-----------|
| S001 Hold | 2 | Edge may exist (climate literacy) but markets too thin to exploit. |
| S002 Threshold | 1 | No volatility. No liquidity. Dead terrain. |
| S003 Catalyst | 2 | COP conferences, but markets are thin. Very few prediction market catalysts. |
| S004 Contrarian | 1 | No dramatic events producing spikes. No emotional participants to fade. |
| S005 Momentum | 1 | No markets, no liquidity, no trends to ride. |
| S006 Time Decay | 2 | Few "by date" markets. Better served by Metaculus than Polymarket. |
| S007 Arb | 1 | Too few markets. Zero arb surface. |
| S008 Info Edge | 3 | Climate science literacy is an edge. But can't exploit it — no liquid markets. Metaculus only. |

---

## 4. Historical Evidence

### Academic Foundation

**Markets are roughly efficient, but imperfectly so — and the imperfections are patterned.**

- **Manski (2006)**: Market prices only partially identify the central tendency of trader beliefs. When price > 0.50, most traders have beliefs above the price; when < 0.50, most have beliefs below. Naive reading of prices as probabilities is flawed. *Implication: systematic miscalibration is exploitable.*
- **Wolfers & Zitzewitz (2004, 2006)**: Prices approximate wealth-weighted mean belief. Markets follow a random walk with "little evidence of arbitrage opportunities." But key caveat: this was on IEM and TradeSports — smaller, pre-Polymarket era. *Implication: S007 arb may be more viable on newer, less mature platforms.*
- **Arrow et al. (2008)**: 22 economists endorsed prediction markets as decision tools. "Markets for contracts that yield payments based on the outcome of an uncertain future event." Called for reduced regulation. *Implication: market efficiency will increase over time as regulation loosens and participation grows.*
- **Prediction market Brier scores**: Average ~0.09 (below 0.125 = good, below 0.1 = great). Sports betting lines average 0.18-0.22. *Implication: prediction markets are well-calibrated on average but not perfectly so.*

### Domain-Specific Efficiency Evidence

- **Political**: PredictIt correctly predicted 93% of 2024 markets; Kalshi 78%; Polymarket 67%. Cross-platform divergences persisted. Negative autocorrelation in daily changes suggests overreaction-correction cycles. *Supports S004 and S007 in POL.*
- **Economic/Fed**: Kalshi maintained **perfect** forecast record on Fed rate decisions (2022-June 2024), matching or exceeding Bloomberg consensus. *ECO is the hardest domain to beat. Avoid calibration strategies here.*
- **Scientific**: Replication market study showed prediction markets effectively predicted which psychology studies would replicate. *SCI has genuine edge for domain experts, confirmed by literature.*
- **Geopolitical**: Markets assigned 58% to Iran strikes that experts dismissed but which materialized. Growing rapidly (191 new events in Jan 2026, +260% YoY). CFR recommends "hefty margin of error." *GEO is high-edge but high-uncertainty territory.*

### Practical Evidence from Polymarket

**Only 0.51% of wallets profit >$1,000. 85-90% of retail accounts end with net losses.**

Documented profit models (from analysis of 95M on-chain transactions):
1. **Information Arbitrage**: "Theo" commissioned a custom poll, invested $100K research → $85M profit. *Extreme outlier, but validates S008 thesis.*
2. **Cross-Platform Arb**: $40M extracted Apr 2024 - Apr 2025. 7.5% returns within hours. Open-source bots exist. *Validates S007, but windows compressing.*
3. **High-Probability Bonds**: Buying >95% contracts. ~5.2% in ~72 days. Annualized >500%. *Not captured by our strategies — closest to S001 with extreme confidence.*
4. **Market Making**: 80-200% annualized. $200-800/day on $10K capital. *Not our strategy set.*
5. **Domain Specialization**: "Axios" 96% win rate on Trump-mention markets. HyperLiquid0xb $1.4M from sports. *Validates S008 + domain focus.*
6. **Speed Trading**: $4.2M aggregate. Within 8 seconds of Powell speaking, contracts jumped 13%. *Validates S008-Type-D, but requires infrastructure we don't have.*

### Key Biases (Exploitable Inefficiencies)

| Bias | Where Strongest | Strategy Exploiting It |
|------|----------------|----------------------|
| **Favorite-longshot** | POL (multi-outcome), CRY | S001 (buy mispriced NO on longshots), S007 (overround arb) |
| **Availability/salience** | GEO (war fears), CRY (FUD) | S004, S006 (fear overprices "by date" events) |
| **Base rate neglect** | GEO (threats ≫ action), LAW | S006 (time decay math), S008-Type-B |
| **Partisan motivated reasoning** | POL | S004 (fade partisan overreaction), S001 (calibration against bias) |
| **Recency bias** | CRY, SOC | S004 (fade spike on latest news) |
| **Slow Bayesian updating** | TEC, POL (primaries) | S005 (ride the trend as market catches up) |

---

## 5. Recommended Playbooks by Domain

### Tier 1: Primary Hunting Grounds

**GEO — Deploy: S006, S004, S008, S002, S007**

GEO is the single richest domain for strategy deployment. Fear-driven retail participants, nested "by date" markets, massive info asymmetry, and growing liquidity create multiple simultaneous edges. Lead with S006 (time decay math is most defensible), support with S004 (fade rhetoric spikes), and layer S008 (OSINT research) for conviction sizing.

**POL — Deploy: S007, S003, S005, S004, S008**

POL is the deepest liquidity domain and the best for structural arb (multi-outcome fields). Lead with S007 (overround scanning on nomination markets), time entries around S003 catalysts (debates, primaries), and ride S005 momentum when polling trends confirm. S004 for debate gaffe panic.

**CRY — Deploy: S002, S004, S006, S005**

CRY has the most emotional participants and highest volatility. Lead with S002 (thresholds trigger constantly) and S004 (fade FUD/hype cycles). S006 on "BTC by [date]" markets. S005 when crypto narrative momentum is confirmed multi-event. Beware wash trading inflating volume signals.

### Tier 2: Selective Opportunities

**ECO — Deploy: S003 only (selective S006, S007)**

ECO is the most efficient domain. Don't try to out-calibrate Fed watchers. Instead, use S003 to position around FOMC meetings. Selective S006 if retail misunderstands rate path probabilities. S007 for structural inconsistencies between related rate path markets.

**LAW — Deploy: S003, S008, S001**

LAW's edge is domain expertise. Lead with S003 (court calendars are the most predictable catalysts in existence). Layer S008 (legal reasoning is a genuine research barrier). S001 baseline for calibration testing.

**TEC — Deploy: S001, S008, S003**

TEC rewards AI/tech domain knowledge. Lead with S001 (calibration testing on model/product timelines) and S008 (arxiv/benchmark analysis as research edge). S003 around known product launch dates.

**FIN — Deploy: S003, S002**

FIN is tough — TradFi pros dominate. Use S003 around earnings catalysts. S002 if underlying market volatility creates threshold opportunities. Avoid trying to out-calibrate.

### Tier 3: Niche / Low Priority

**SCI — Deploy: S008, S001 (only if liquidity permits)**

The edge-to-liquidity ratio is inverted: massive potential edge, no way to size into it on Polymarket. Use S008 for high-confidence small positions. Consider Metaculus for non-monetary calibration practice.

**SOC — Deploy: S003, S002**

Fun money. S003 around known events (game releases, award shows). S002 if announcements create tradable swings. Don't allocate serious capital.

**ENV — Skip entirely on Polymarket**

Too few markets, too little liquidity. Use Metaculus for calibration practice only. Revisit if ENV market coverage expands.

---

## 6. Anti-Patterns: Combinations to Avoid

| Strategy | Domain | Score | Why It Fails |
|----------|--------|-------|-------------|
| S005 Momentum | SCI | 1 | No trends. Scientific progress is too gradual. No liquidity for position building. |
| S005 Momentum | ENV | 1 | No markets, no liquidity, no trends. Zero signal. |
| S002 Threshold | SCI | 1 | No volatility. Markets barely move. Thresholds never trigger — degrades to trapped capital. |
| S002 Threshold | ENV | 1 | Same as SCI. Dead terrain. |
| S004 Contrarian | ENV | 1 | No dramatic events, no emotional participants, no spikes to fade. |
| S007 Arb | ENV | 1 | Zero arb surface. Too few markets to create logical inconsistencies. |
| S001 Hold | ECO | 2 | Kalshi has a perfect forecast record. You are not smarter than the Fed watchers. |
| S004 Contrarian | ECO | 2 | Professional participants process data within seconds. No emotional overreaction to fade. |
| S005 Momentum | ECO | 2 | Fed decisions are discrete events. Rate paths are known. No slow-digestion momentum. |
| S008 Info Edge | FIN | 2 | Any financial research edge is already priced in traditional markets. Prediction markets are a lagging mirror. |
| S001 Hold | FIN | 2 | TradFi pros. Efficient markets. Your calibration edge is near-zero against this competition. |

**Meta-lesson**: The worst anti-pattern is deploying **any strategy in a domain where you face expert competition without expert-level knowledge**. ECO and FIN are expert-dominated. Avoid unless you have a specific, articulable edge.

---

## 7. Prioritization

### Top 5 Strategy-Domain Pairs for First Paper Trades

| Rank | Pair | Why First | Immediate Test |
|------|------|-----------|----------------|
| 1 | **S006-GEO** (Time Decay + Geopolitics) | Most defensible edge: pure math. "Iran strikes by March" at 18% with 5 days left — calculate implied daily hazard rate vs base rate. High liquidity ($17M+). | Iran strike markets: compare implied daily probability to historical base rate of US military strikes. |
| 2 | **S007-POL** (Arb + Politics) | Lowest risk: structural mispricings don't require directional conviction. Check if 2028 Republican nomination candidates sum to >103%. | Sum all candidate YES prices on Republican 2028 nomination market. If >103%, the overround is exploitable. |
| 3 | **S004-GEO** (Contrarian + Geopolitics) | Runs alongside S006-GEO on same markets. When rhetoric spikes Iran strike 15%+ in 24h, track whether mean reversion occurs. | Next major Iran rhetoric spike: track price path for 14 days. Did it revert 50%? |
| 4 | **S003-ECO** (Catalyst + Economics) | Clearest catalyst calendar. Next FOMC meeting is scheduled. Research Fed dot plot consensus, position 3-7 days before. | Next FOMC: is the market pricing consistent with Fed guidance and futures? Enter if divergence. |
| 5 | **S008-GEO** (Info Edge + Geopolitics) | Tests whether OSINT research creates genuine calibration edge. Iran strike probability: synthesize military logistics, diplomatic timeline, historical base rates. | Build an Iran strike probability estimate from first principles. Compare to market. Document edge type (A-E). |

### Top 5 Strategy-Domain Pairs to Avoid

| Rank | Pair | Why Avoid |
|------|------|-----------|
| 1 | **S005-SCI** (Momentum + Science) | No trends, no liquidity, no signal. Capital would sit idle indefinitely. |
| 2 | **S005-ENV** (Momentum + Environment) | Ghost town. Zero markets worth monitoring. |
| 3 | **S002-SCI** (Threshold + Science) | No volatility to trigger thresholds. Trapped capital with no exit signal. |
| 4 | **S004-ENV** (Contrarian + Environment) | No spikes, no emotion, nothing to fade. |
| 5 | **S001-ECO** (Hold + Economics) | Trying to out-calibrate Kalshi's perfect track record and Bloomberg consensus. Hubris bet. |

### Where the Biggest Edge Probably Lives

**GEO + S006/S008 combination — Geopolitical "by date" markets with information edge**

The reasoning:

1. **Participant quality is lowest where stakes feel highest.** War fears attract scared retail bettors, not calibrated analysts. Availability bias runs the show — vivid scenarios (nuclear strikes, invasions) feel more likely than base rates justify.

2. **The math is most exploitable here.** Time decay on "by date" markets is pure arithmetic. If "US strikes Iran by March 31" is at 57% with 37 days remaining, the implied daily hazard rate is ~2.3%. Historical base rate for US military strikes on sovereign nations since 1990: roughly 0.3% per day (when tensions are elevated). That's a 7x overprice — even with a large error bar, the edge is massive.

3. **Information asymmetry is structural, not transient.** OSINT analysis (troop movements, carrier deployments, diplomatic signals, budget allocation) is publicly available but requires synthesis effort. This is S008-Type-A edge: connecting public dots nobody else bothers to connect.

4. **Liquidity has finally caught up.** GEO markets were historically too thin. In 2026, individual events are reaching $155M+ volume. You can now size into the edge.

5. **The compound effect.** Every GEO research investment builds cumulative domain knowledge. context.md, sources.md, and research/ files create a moat that deepens over time. This is how "Theo" built his $85M position — months of accumulated domain expertise compressed into high-conviction trades.

**The playbook**: Start with S006 (time decay math) as the quantitative backbone. Layer S008 (OSINT research) to refine probability estimates beyond base rates. Use S004 (contrarian) as the tactical entry signal — wait for a rhetoric spike, calculate whether the implied probability is structurally overpriced, and fade the fear. The three strategies reinforce each other in GEO specifically.
