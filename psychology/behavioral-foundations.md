# B01: Behavioral Foundations

*Research date: 2026-02-25*
*Purpose: Comprehensive map of how human psychology distorts prediction market prices*
*Status: Complete — theoretical infrastructure for all behavioral strategies*

---

## Table of Contents

1. [The Bias Inventory](#1-the-bias-inventory)
2. [The Five Compound Patterns](#2-the-five-compound-patterns)
3. [Tetlock's Framework](#3-tetlocks-framework)
4. [The Emotional Charge Index](#4-the-emotional-charge-index-eci)
5. [The Reality Check Protocol](#5-the-reality-check-protocol)
6. [Integration with Existing Strategies](#6-integration-with-existing-strategies)

---

## 1. The Bias Inventory

### Summary Table

| # | Bias | Group | Direction | Key Citation | Exploited By |
|---|------|-------|-----------|-------------|-------------|
| 1 | Availability Heuristic | Availability | UP (media-covered) | Tversky & Kahneman 1973 | S004, S006 |
| 2 | Salience Bias | Availability | UP (dramatic) | Bordalo, Gennaioli & Shleifer 2012 | S004, S006 |
| 3 | Scope Insensitivity | Availability | Compressed | Desvousges et al. 1992 | S002, S007 |
| 4 | Narrative Fallacy | Narrative | UP (story-driven) | Taleb 2007; Tetlock 2005 | S004, S008 |
| 5 | Representativeness | Narrative | UP (prototypical) | Kahneman & Tversky 1972 | S004, S001 |
| 6 | Cluster Illusion | Narrative | Context-dependent | Gilovich, Vallone & Tversky 1985 | S004 |
| 7 | Motivated Reasoning | Social | UP (aligned) | Kunda 1990; Clinton & Huang 2025 | S004, S001 |
| 8 | Identity-Protective Cognition | Social | UP (group-congruent) | Kahan 2017 | S004, S008 |
| 9 | Social Proof / Herding | Social | Amplifies trend | Banerjee 1992; Park & Sgroi 2022 | S004 |
| 10 | FOMO | Social | UP (exclusively) | Przybylski et al. 2013 | S004 |
| 11 | Loss Aversion | Loss & Risk | UP (feared events) | Kahneman & Tversky 1979 | S006 |
| 12 | Fear Premium | Loss & Risk | UP (tail risks) | Bollerslev & Todorov 2011 | S006, S004 |
| 13 | Hope Premium | Loss & Risk | UP (longshots) | Snowberg & Wolfers 2010 | S006 |
| 14 | Probability Weighting | Loss & Risk | UP (both tails) | Tversky & Kahneman 1992 | S006, S007 |
| 15 | Pseudocertainty | Loss & Risk | UP (conditional) | Kahneman & Tversky 1984 | S007 |
| 16 | Recency Bias | Temporal | Amplifies recent | Campbell & Sharpe 2009 | S004 |
| 17 | Present Bias | Temporal | Toward 50% | Laibson 1997; Page & Clemen 2013 | S001 |
| 18 | Deadline Panic | Temporal | Context-dependent | Choi & Hui 2014 | S006 |
| 19 | Conservatism | Updating | Toward prior | Edwards 1968; Angelini et al. 2022 | S005 |
| 20 | Confirmation Bias | Updating | Toward consensus | Merkle & Weber 2014 | S008 |
| 21 | Anchoring | Updating | Toward anchor | Tversky & Kahneman 1974 | S008, S001 |
| 22 | Belief Perseverance | Updating | Toward initial belief | Ross, Lepper & Hubbard 1975 | S004, S008 |
| 23 | YES Bias | Market-Specific | UP (affirmative) | Becker 2024; Reichenbach & Walther 2025 | S006 |
| 24 | Favorite-Longshot Bias | Market-Specific | UP longshots, DOWN favorites | Snowberg & Wolfers 2010; Whelan 2024 | S006, S007 |
| 25 | Action Bias | Market-Specific | UP (net) | Patt & Zeckhauser 2000 | S006 |
| 26 | Compound Probability Neglect | Market-Specific | UP (joint outcomes) | Tversky & Kahneman 1983; Lee et al. 2020 | S006, S007 |

---

### Group 1: Availability & Vividness

#### 1. Availability Heuristic

**Definition**: People estimate the probability of an event by how easily examples come to mind — vivid, recent, or heavily covered events feel more likely than they are.

**Mechanism in prediction markets**: Media coverage cycles inflate probability estimates for covered events. When "Iran strike" dominates cable news, traders overestimate strike probability regardless of base rates. In Google's internal prediction markets, a 2% stock increase pushed optimistic contract prices 3-4pp higher through availability of positive sentiment, not updated fundamentals (Cowgill & Zitzewitz 2015).

**Directional effect**: UP — pushes prices above true probability for vivid/media-covered outcomes. DOWN for outcomes lacking media coverage.

**Academic evidence**: Tversky, A. & Kahneman, D. (1973). "Availability: A heuristic for judging frequency and probability." *Cognitive Psychology*, 5(2), 207-232. Prediction market evidence: Cowgill, B. & Zitzewitz, E. (2015). "Corporate Prediction Markets." *Review of Economic Studies*, 82(4), 1309-1341.

**Detection signal**: Price spikes coinciding with media coverage cycles without new fundamental information. Markets on well-publicized risks (pandemics, terrorism) persistently trading above base rates.

**Exploitation**: S004 (fade media-driven spikes that lack structural basis), S006 (time decay on media-inflated "by date" markets).

**Our track record**: T001/T003/T005 (Iran markets) — all entered during peak media coverage of Iran rhetoric. The availability of "strike" imagery in news drove prices above our base-rate estimates. T003 explicitly identified rhetoric-driven spike.

---

#### 2. Salience Bias

**Definition**: Attention is drawn disproportionately to payoffs that "stand out" relative to context, distorting probability assessment toward salient outcomes.

**Mechanism in prediction markets**: Extreme upside scenarios (longshot candidate winning, military strike occurring) receive disproportionate attention because the payoff if correct is dramatic, while the high probability of loss fades to background. Bordalo, Gennaioli & Shleifer (2013) showed that assets with salient recent upsides become overpriced and earn lower future returns.

**Directional effect**: UP for contracts with vivid/extreme upside scenarios. DOWN for mundane high-probability outcomes.

**Academic evidence**: Bordalo, P., Gennaioli, N. & Shleifer, A. (2012). "Salience Theory of Choice Under Risk." *Quarterly Journal of Economics*, 127(3), 1243-1285. Asset pricing: Bordalo et al. (2013). "Salience and Asset Prices." *American Economic Review*, 103(3), 623-628.

**Detection signal**: "Headline" markets trading above actuarial fair value versus nearly identical but less salient alternatives. Contracts involving dramatic regime change persistently overpriced.

**Exploitation**: S004 (fade salience-driven overpricing), S006 (the less salient "nothing happens" outcome is systematically underpriced).

**Our track record**: SOTU China market (res-sotu-003) — 93% market price vs. 75% estimate. China was the most salient geopolitical topic but was strategically omitted. The salience of China tensions made "mention" seem near-certain.

---

#### 3. Scope Insensitivity

**Definition**: People's emotional and probabilistic responses are insensitive to the magnitude of the outcome — "100 deaths" and "10,000 deaths" produce similar emotional reactions.

**Mechanism in prediction markets**: Similar pricing for qualitatively similar but quantitatively different outcomes. Desvousges et al. (1992) found respondents paid $80 to save 2,000 birds vs. $88 for 200,000 birds — near-identical valuations across 100x scope. In prediction markets, "GDP falls 1%" and "GDP falls 5%" may trade at similar prices because traders respond to the category "recession" rather than scaling with magnitude.

**Directional effect**: Compresses prices toward a single "category response." Moderate outcomes overpriced relative to extreme outcomes within the same event class.

**Academic evidence**: Desvousges, W.H. et al. (1992). "Measuring Nonuse Damages Using Contingent Valuation." Kahneman, D., Ritov, I. & Schkade, D. (1999). "Economic Preferences or Attitude Expressions?" *Journal of Risk and Uncertainty*, 19, 203-235.

**Detection signal**: Within a single event series (e.g., "BTC above $X" at different thresholds), prices that don't decrease proportionally with increasing threshold. Price curves that are too flat across magnitude brackets.

**Exploitation**: S002 (threshold markets may be mispriced within a series), S007 (scope insensitivity across linked markets creates arb surface).

**Our track record**: T008 (BTC $150K) — the market was originally pricing $200K NO at 93.5% and $150K NO at 91.5%, a suspiciously small gap for a $50K difference in threshold. Scope insensitivity compressed the two price levels.

---

### Group 2: Narrative & Pattern

#### 4. Narrative Fallacy

**Definition**: People construct coherent stories that make past events seem predictable and project those narratives forward, generating overconfidence in scenario-based predictions.

**Mechanism in prediction markets**: Tetlock (2005) found "hedgehog" forecasters — those with one big narrative — performed dramatically worse than "fox" forecasters who maintained uncertainty across scenarios. Narrative-driven forecasters generated excessively confident predictions. In markets, "invasion is coming because of escalation logic" or "this candidate will surge because of debate performance" are narratives that override base-rate reasoning.

**Directional effect**: UP — prices pushed up for outcomes fitting compelling narratives. DOWN for "nothing happens" status quo outcomes that lack narrative structure.

**Academic evidence**: Taleb, N.N. (2007). *The Black Swan*. Tetlock, P.E. (2005). *Expert Political Judgment*. Tetlock, P.E. & Gardner, D. (2015). *Superforecasting*.

**Detection signal**: Markets on dramatic scenarios (regime change, war escalation) trading above base rates while "status quo" contracts are underpriced. Price movements tracking narrative arcs rather than probability-relevant data.

**Exploitation**: S004 (fade narrative-driven spikes), S008 (use information research to counter narrative with data).

**Our track record**: T003 (Iran March 31) — the "Trump's 10-15 day deadline" narrative drove prices from ~40% to ~58%. The narrative ("deadline → strike") was compelling but Geneva talks were simultaneously producing positive signals that the narrative crowd ignored.

---

#### 5. Representativeness Heuristic

**Definition**: People judge probability by how "representative" a situation is of a category, ignoring base rates and sample sizes.

**Mechanism in prediction markets**: Simmons et al. (2011) found NFL bettors wagering $20,000+ systematically predicted favorites against point spreads because "good team wins" is more representative than "underdog covers." The crowd was systematically wrong due to representativeness. In prediction markets, "strong incumbent wins" or "rising candidate continues rising" feel more probable because they match prototypical patterns.

**Directional effect**: UP for outcomes matching prototypical patterns (favorites, incumbents, market leaders). DOWN for atypical outcomes.

**Academic evidence**: Kahneman, D. & Tversky, A. (1972). "Subjective probability: A judgment of representativeness." *Cognitive Psychology*, 3(3), 430-454. Simmons, J.P. et al. (2011). "Intuitive Biases in Choice versus Estimation." *Journal of Consumer Research*, 38(1), 1-15.

**Detection signal**: Prices on "representative" outcomes (favorites, incumbents) persistently higher than base rates warrant. Contracts on atypical outcomes priced below actuarial value.

**Exploitation**: S004 (when representativeness drives overpricing), S001 (calibrate against representativeness by starting from base rates).

**Our track record**: T006 (Vance 2028 GOP nom) — this trade *uses* representativeness correctly: 100% of modern sitting VPs from two-term presidents won the nomination (N=4). But the market at 41.6% was ignoring this base rate, possibly because "contested primary" is a more representative narrative than "VP coasts to nomination."

---

#### 6. Cluster Illusion

**Definition**: People perceive meaningful patterns in random sequences, seeing streaks and trends where only statistical noise exists.

**Mechanism in prediction markets**: Gilovich et al. (1985) showed the "hot hand" belief in basketball was a statistical illusion. Croson & Sundali (2005) found casino gamblers bet against streaks with short runs (gambler's fallacy) but with longer streaks (hot hand), both irrational. In prediction markets, a series of YES resolutions on similar markets makes traders expect the next one to also resolve YES, even when events are independent.

**Directional effect**: Context-dependent. After "winning streaks," prices pushed UP (hot hand) or DOWN (gambler's fallacy) depending on streak length and framing.

**Academic evidence**: Gilovich, T., Vallone, R. & Tversky, A. (1985). "The hot hand in basketball." *Cognitive Psychology*, 17(3), 295-314. Croson, R. & Sundali, J. (2005). "The Gambler's Fallacy and the Hot Hand." *Journal of Risk and Uncertainty*, 30(3), 195-209.

**Detection signal**: Prices on independent-but-similar markets moving in lockstep after resolutions. Overreaction to sequences of 3+ similar outcomes that are statistically independent.

**Exploitation**: S004 (when cluster illusion drives mispricing in either direction).

**Our track record**: Limited direct evidence. Potentially relevant to SOTU batch — after multiple mention markets resolved YES, later mention markets may have been inflated by the "hot hand" of earlier YES resolutions.

---

### Group 3: Social & Identity

#### 7. Motivated Reasoning / Partisan Bias

**Definition**: People assess probability through an ideological lens, overestimating the likelihood of outcomes they desire and underestimating those they fear or oppose.

**Mechanism in prediction markets**: Republicans overestimate Republican candidates' chances; Democrats do the same for theirs. Tetlock showed ideologically committed "hedgehog" experts were the worst forecasters because motivated reasoning prevented belief updating. Clinton & Huang (2025) found partisan-motivated buying on Polymarket created spikes that reversed within days — 58% of national presidential markets showed negative serial correlation.

**Directional effect**: UP on politically aligned outcomes (your candidate, your party's preferred policy). Net effect depends on which partisan group dominates platform capital.

**Academic evidence**: Kunda, Z. (1990). "The case for motivated reasoning." *Psychological Bulletin*, 108(3), 480-498. Clinton, J. & Huang, T.F. (2025). Vanderbilt prediction market study. Mellers, B., Tetlock, P.E. et al. (2014). "Forecasting Tournaments." *Current Directions in Psychological Science*, 23(4), 290-295.

**Detection signal**: Divergence between prediction market prices and polling averages on political markets. Price movements tracking partisan media cycles rather than new data.

**Exploitation**: S004 (fade partisan overreaction after debates, primaries, gaffe moments), S001 (calibrate probability estimates independent of partisan framing).

**Our track record**: T006 (Vance 2028) — the market may underweight Vance at 41.6% partly because GOP base partisans don't yet identify Vance as "their" candidate (no Trump endorsement). Once partisan identity activates behind Vance (endorsement moment), expect rapid repricing.

---

#### 8. Identity-Protective Cognition

**Definition**: Beliefs that threaten group identity are resisted regardless of evidence — and critically, this effect is *amplified*, not reduced, among the more informed and numerate.

**Mechanism in prediction markets**: Kahan (2017) showed that higher scientific literacy *increases* polarization on identity-relevant topics because skilled reasoners use their abilities to defend group-congruent beliefs. In prediction markets, sophisticated traders on identity-charged topics (climate policy, gun control, immigration) may produce *worse* prices than naive traders because their analytical skills serve identity protection.

**Directional effect**: UP for identity-congruent outcomes among the dominant trading population. Amplified (not reduced) among more informed traders.

**Academic evidence**: Kahan, D.M. (2017). "Misconceptions, Misinformation, and the Logic of Identity-Protective Cognition." SSRN 2973067. Kahan, D.M. et al. (2012). "The polarizing impact of science literacy." *Nature Climate Change*, 2, 732-735.

**Detection signal**: Markets on culturally polarized topics where price diverges from expert consensus. Prices correlating with platform user-base demographics rather than objective indicators.

**Exploitation**: S004 (identity-charged markets are most prone to emotional overreaction), S008 (research that cuts against identity-protective reasoning provides genuine edge).

**Our track record**: SOTU markets broadly — the "MAGA" mention market at 87% was partly driven by identity-protective cognition among Trump supporters who couldn't imagine a Trump SOTU without "MAGA." The word is identity-defining for the base, which inflated the estimate.

---

#### 9. Social Proof / Herding

**Definition**: After observing others choose the same action, people discard their private information and follow, creating fragile informational cascades.

**Mechanism in prediction markets**: Banerjee (1992) and Bikhchandani et al. (1992) modeled how rational cascades emerge from sequential observation. Park & Sgroi (2022) found herding "far more prevalent than previous studies suggest, particularly amongst less informed traders" in UK financial spread markets. Cascades are brittle — any public information shock can reverse direction — explaining the combination of trending moves followed by sharp reversals.

**Directional effect**: Amplifies existing price direction. Creates momentum that overshoots in both directions.

**Academic evidence**: Banerjee, A.V. (1992). "A Simple Model of Herd Behavior." *Quarterly Journal of Economics*, 107(3), 797-817. Bikhchandani, S., Hirshleifer, D. & Welch, I. (1992). "A Theory of Fads, Fashion, Custom, and Cultural Change as Informational Cascades." *Journal of Political Economy*, 100(5), 992-1026. Park, A. & Sgroi, D. (2022). "Herding behavior in prediction markets."

**Detection signal**: Volume spikes with one-directional price movement. Prices moving in steps (cascade) rather than smooth updating. Sharp reversals after seemingly strong trends.

**Exploitation**: S004 (herding creates the overshooting that mean reversion corrects).

**Our track record**: T003 (Iran March 31) — the +25% spike to 57.5% had herd characteristics: volume surged as the Trump deadline rhetoric amplified, creating a cascade of YES buying that overshot fundamentals.

---

#### 10. FOMO (Fear of Missing Out)

**Definition**: Sharp price increases trigger urgency-driven buying that further inflates prices beyond informational value.

**Mechanism in prediction markets**: Ante (2023) identified FOMO as "one of the strongest psychological factors that appears to influence crypto-trading." FOMO is "particularly intensified in crypto-trading" relative to traditional betting. The mechanism is asymmetric: FOMO triggers buying, not selling, creating a ratchet effect during rallies.

**Directional effect**: UP — exclusively pushes prices higher during momentum phases.

**Academic evidence**: Przybylski, A.K. et al. (2013). "Motivational, emotional, and behavioral correlates of fear of missing out." *Computers in Human Behavior*, 29(4), 1841-1848. Ante, L. (2023). "The psychology of cryptocurrency trading." *PLOS ONE*.

**Detection signal**: Accelerating price increase with accelerating volume (parabolic shape). Social media mention volume correlating with or lagging price movements.

**Exploitation**: S004 (FOMO-driven spikes are prime fade candidates — the urgency fades, the reversion follows).

**Our track record**: T003 — the Iran rhetoric spike likely included FOMO dynamics: as prices rose through 50%, traders who had been watching bought in fear of missing the move, pushing prices to the 57.5% level where we entered NO.

---

### Group 4: Loss & Risk

#### 11. Loss Aversion

**Definition**: Losses feel approximately 2x more painful than equivalent gains feel good, creating asymmetric reactions to positive and negative information.

**Mechanism in prediction markets**: Negative developments (war escalation, recession signals) produce outsized price swings compared to equivalently informative positive developments. Traders are also reluctant to sell losing positions (disposition effect), leading to stale prices on contracts moving against holders. Replicated in 19 countries with ~90% success rate (Ruggeri et al. 2020).

**Directional effect**: UP for feared-event contracts (overpricing of bad outcomes). Creates sluggish downward adjustment on losing positions.

**Academic evidence**: Kahneman, D. & Tversky, A. (1979). "Prospect Theory." *Econometrica*, 47(2), 263-291. Ruggeri, K. et al. (2020). "Replicating patterns of Prospect Theory." *Nature Human Behaviour*, 4, 622-633.

**Detection signal**: Asymmetric price response: bad news moves prices more than equivalently significant good news. Low volume on losing contracts (holders won't sell).

**Exploitation**: S006 (feared "by date" events systematically overpriced due to loss aversion premium), S004 (the asymmetry in reaction creates larger spikes on negative news → larger fade opportunities).

**Our track record**: T001/T003/T005 (all Iran NO) — the loss aversion premium is visible in the asymmetric response: hawkish rhetoric pushed prices up faster than dovish signals (Geneva talks) pushed them down.

---

#### 12. Fear Premium

**Definition**: Negative/threatening outcomes carry a persistent price premium above actuarial fair value because traders pay for the emotional relief of hedging against dread scenarios.

**Mechanism in prediction markets**: Bollerslev & Todorov (2011) found a 1 standard deviation increase in tail risk forecasts 4.5% excess annual market returns — fear is systematically overpriced. Becker (2025) found "World Events" contracts (war, disaster, geopolitical) show the largest maker-taker gap at 7.32pp on Kalshi — the least efficient category. Finance contracts show only 0.17pp gap.

**Directional effect**: UP — feared negative outcomes are systematically overpriced. Premium increases during market stress.

**Academic evidence**: Bollerslev, T. & Todorov, V. (2011). "Tails, Fears, and Risk Premia." *Journal of Finance*, 66(6), 2165-2211. Kelly, B. & Jiang, H. (2014). "Tail Risk and Asset Prices." *Review of Financial Studies*, 27(10), 2841-2871. Becker, J. (2025). Kalshi microstructure analysis.

**Detection signal**: "Insurance" contracts (recession, war, default) persistently trading above historical base rates. Price premium widening during volatility spikes.

**Exploitation**: S006 (the core edge — time decay on fear-premium markets), S004 (fade fear-driven spikes).

**Our track record**: T001 (Iran June 30 NO at 33.5%) — this is a direct fear premium play. The market prices strike probability at 66.5% over 127 days, implying a daily hazard rate of ~0.85%, while historical base rates suggest ~0.3-0.5%. The ~35pp gap is partly fear premium.

---

#### 13. Hope Premium

**Definition**: Traders overpay for low-probability high-payoff outcomes because the "hope" of a big win provides utility independent of expected value.

**Mechanism in prediction markets**: Snowberg & Wolfers (2010) analyzed 5.6 million horse race starts and found longshots systematically overbet — driven by probability misperceptions consistent with prospect theory, not risk-love. Becker (2024) documented that Kalshi takers disproportionately favor YES bets at longshot prices, losing 1.12% on average through an "Optimism Tax."

**Directional effect**: UP — low-probability outcomes are systematically overpriced.

**Academic evidence**: Snowberg, E. & Wolfers, J. (2010). "Explaining the Favorite-Longshot Bias." *Journal of Political Economy*, 118(4), 723-746. Becker, J. (2024). "The Microstructure of Wealth Transfer in Prediction Markets."

**Detection signal**: Contracts priced under 20 cents consistently resolving YES less often than price implies. Systematic negative returns for buyers of cheap contracts (Kalshi: <10 cent contracts lose >60% of invested money).

**Exploitation**: S006 (sell overpriced longshot YES), S007 (overround arbs partly driven by cumulative hope premiums across multi-outcome fields).

**Our track record**: T004 (Fed 25bp cut at 2.85%) — this was a hope premium play in reverse. We *bought* the longshot, hoping for asymmetric payoff. The trade lost 17.5% precisely because the hope premium made the entry price elevated relative to true probability (~1.5-2%). Lesson T14: "Lottery tickets need constant probability re-evaluation."

---

#### 14. Probability Weighting

**Definition**: People systematically overweight small probabilities and underweight large probabilities, with an S-shaped weighting function crossing the diagonal at approximately p=0.30-0.33.

**Mechanism in prediction markets**: Tversky & Kahneman (1992) estimated weighting parameters: gamma=0.61 for gains (more distortion), 0.69 for losses. Prelec (1998) provided the axiomatic function w(p) = exp(-(-ln(p))^alpha) with alpha ≈ 0.6. Quantified distortions:

| True Probability | Decision Weight | Distortion |
|-----------------|----------------|-----------|
| p = 0.01 | w ≈ 0.05-0.06 | **5-6x overweighting** |
| p = 0.05 | w ≈ 0.15 | **3x overweighting** |
| p = 0.10 | w ≈ 0.20 | **2x overweighting** |
| p = 0.30 | w ≈ 0.30 | **Crossover (neutral)** |
| p = 0.50 | w ≈ 0.45-0.48 | Slight underweighting |
| p = 0.80 | w ≈ 0.70-0.75 | ~10% underweighting |
| p = 0.95 | w ≈ 0.80 | ~16% underweighting |

This maps directly to Kalshi empirical data (Becker 2025): contracts priced 1-10 cents resolve YES far less than price implies; contracts priced 90-99 cents resolve YES more than implied.

**Directional effect**: UP for both tails (p < 0.20 overpriced, p > 0.80 underpriced). Crossover at approximately 30-33%.

**Academic evidence**: Tversky, A. & Kahneman, D. (1992). "Advances in Prospect Theory." *Journal of Risk and Uncertainty*, 5(4), 297-323. Prelec, D. (1998). "The Probability Weighting Function." *Econometrica*, 66(3), 497-528.

**Detection signal**: S-shaped calibration curve across a large portfolio. Contracts under 20 cents resolving YES less than implied; contracts above 80 cents resolving YES more than implied.

**Exploitation**: S006 (sell overpriced tail events), S007 (probability weighting inflates each alternative in multi-outcome fields, creating overround).

**Our track record**: T002 (Trump 2028 GOP nom NO at 97.2%) — at the high-probability end, probability weighting suggests 97.2% is slightly underpriced (true value closer to 99%+ given constitutional prohibition). The 2.8% YES price is ~2x overpriced relative to true probability via weighting distortion. T008 (BTC $150K NO at 91.5%) — similar pattern.

---

#### 15. Pseudocertainty Effect

**Definition**: In multi-stage decisions, people treat outcomes in later stages as certain while ignoring uncertainty introduced by earlier stages.

**Mechanism in prediction markets**: When traders price a conditional outcome ("if X wins the primary, X wins the general") at 90%, they often price the general election contract as if nomination is already resolved. A 90% conditional × 60% nomination = 54% joint, but traders anchor on 90% and price the general too high.

**Directional effect**: UP — conditional probabilities treated as unconditional, inflating prices of outcomes depending on uncertain preconditions.

**Academic evidence**: Kahneman, D. & Tversky, A. (1984). "Choices, values, and frames." *American Psychologist*, 39(4), 341-350.

**Detection signal**: In multi-leg event trees, the product of conditional market prices exceeding the joint outcome price. "If...then" scenarios where conditional price doesn't discount antecedent uncertainty.

**Exploitation**: S007 (detect pseudocertainty-driven overround in multi-outcome markets).

**Our track record**: Not directly observed yet, but relevant to T006 (Vance) — the market may partially exhibit pseudocertainty by pricing "Vance wins general" conditional on nomination as if the nomination is more certain than our 58% estimate.

---

### Group 5: Temporal

#### 16. Recency Bias

**Definition**: Recent events receive disproportionate weight when estimating probabilities, with the recent past treated as more predictive than base rates warrant.

**Mechanism in prediction markets**: A recent YES resolution for a similar market makes the next similar market trade higher, even when events are independent. Campbell & Sharpe (2009) found professional forecasters placed excessive weight on recent realized values, making up to 25% of macroeconomic "surprises" predictable from anchoring to recent data.

**Directional effect**: Amplifies direction of recent outcomes. Recent YES → prices pushed UP; recent NO → pushed DOWN.

**Academic evidence**: Tversky & Kahneman (1973). Campbell, S.D. & Sharpe, S.A. (2009). "Anchoring Bias in Consensus Forecasts." *Journal of Financial and Quantitative Analysis*, 44(2), 369-390.

**Detection signal**: Prices on independent-but-similar markets moving in lockstep after resolution. Price-to-base-rate gap widening after streak of similar outcomes.

**Exploitation**: S004 (recency-driven spikes on news events are prime fade targets).

**Our track record**: T003/T005 (Iran) — the most recent Iran-related events at time of entry (Trump deadline rhetoric, military buildup headlines) dominated estimates despite the longer base-rate history of threats ≫ action.

---

#### 17. Present Bias / Hyperbolic Discounting

**Definition**: Traders disproportionately discount future payoffs, creating bias toward 50% on long-dated contracts because locking capital at extreme prices is unattractive.

**Mechanism in prediction markets**: Page & Clemen (2013) found prediction markets are "reasonably well calibrated when time to expiration is relatively short but significantly biased for events farther in the future" with prices biased toward 50% for distant events. Othman (2025) confirmed the "long-horizon problem" — traders' time preferences make them unwilling to lock capital at extreme prices for months.

**Directional effect**: Toward 50% — high-probability long-dated contracts are underpriced (pushed DOWN), low-probability long-dated contracts are overpriced (pushed UP toward 50%).

**Academic evidence**: Laibson, D. (1997). "Golden Eggs and Hyperbolic Discounting." *Quarterly Journal of Economics*, 112(2), 443-477. Page, L. & Clemen, R. (2013). "Do Prediction Markets Produce Well-Calibrated Probability Forecasts?" *Economic Journal*, 123(568), 491-513.

**Detection signal**: Long-dated contracts clustered more tightly around 50% than short-dated contracts on similar events. Prices reaching extreme values only in final days regardless of when information was available.

**Exploitation**: S001 (long-dated positions with correct probability estimates capture the present-bias discount as time passes and prices converge).

**Our track record**: T006 (Vance at 41.6%, Aug 2028 resolution) — present bias likely suppresses this price. Traders see a 2.5-year horizon and are unwilling to lock capital even at an apparently mispriced 41.6%. Our 58% estimate implies the present-bias discount is ~16pp.

---

#### 18. Deadline Panic

**Definition**: As contract expiration approaches, two opposing forces intensify: rational capital deployment and irrational panic trading from existing position holders.

**Mechanism in prediction markets**: Choi & Hui (2014) found biased reactions in in-play markets attenuate ~5 minutes after surprise events, but the initial overreaction window creates exploitable mispricing. Near expiration, volume spikes and bid-ask spreads first widen then collapse, with brief panicked overshoots.

**Directional effect**: Context-dependent. Losing positions get panic-sold (overshooting in correct direction). Last-minute information rush can create brief mispricings both ways.

**Academic evidence**: Page & Clemen (2013). Choi, D. & Hui, S.K. (2014). "The Role of Surprise." *Journal of Economic Behavior & Organization*, 107(B), 614-629.

**Detection signal**: Volume spikes in final 24-48 hours. Bid-ask spreads widening then collapsing near expiration. Sharp corrections in final hours that reverse within minutes.

**Exploitation**: S006 (deadline panic on "by date" markets creates last-minute mispricing opportunities; also confirms the time-decay thesis as quiet days erode YES value).

**Our track record**: T003 (Iran March 31) — as the March 31 deadline approaches with no strike, each quiet day is evidence that should push YES down, but deadline panic can create contrary spikes from YES holders cutting positions or NO holders taking profits early.

---

### Group 6: Updating

#### 19. Conservatism Bias

**Definition**: People update beliefs in the correct direction but insufficiently — approximately 50-75% of the Bayesian-optimal update (Edwards 1968).

**Mechanism in prediction markets**: Choi & Hui (2014) confirmed directly in betting markets: when reacting to expected or moderately surprising events, "market participants tend to be conservative, i.e., they rely too much on their prior beliefs and hence underreact." Overreaction occurs *only* for highly surprising events. Angelini et al. (2022) found the same in football betting exchanges: mispricing increased for longshot-team goals (surprise events).

**Directional effect**: Toward the prior/anchor price. After expected news, prices move correctly but not enough — creating persistent underreaction.

**Academic evidence**: Edwards, W. (1968). "Conservatism in human information processing." Choi & Hui (2014). Angelini, G., De Angelis, L. & Singleton, C. (2022). "Informational efficiency within in-play prediction markets." *International Journal of Forecasting*, 38(1), 282-299.

**Detection signal**: Prices that drift slowly toward where they "should" have jumped immediately. Post-announcement drift — the prediction market equivalent of post-earnings drift.

**Exploitation**: S005 (trade in the direction of news on expected-but-underreacted events — the slow drift is exploitable momentum).

**Our track record**: T001 (Iran June 30) — the Geneva talks progress has been gradual and expected, so the market may be conservatively updating. If talks continue positively, the market should drift down from 69.5% but will likely do so slowly, creating a window for additional NO entry.

---

#### 20. Confirmation Bias

**Definition**: Traders selectively attend to information consistent with existing positions and discount contradictory evidence.

**Mechanism in prediction markets**: Merkle & Weber (2014) demonstrated in real-money movie prediction markets that when traders wrote explanations of their forecasts (inducing the "explanation effect"), they subsequently ignored value-relevant new information. "When all traders are subject to confirmation bias, market prices do not accurately reflect new, value-relevant information." However, even a minority of unbiased traders restored efficiency.

**Directional effect**: Toward existing consensus price. Once a market establishes a view, it becomes sticky and slow to incorporate contradictory evidence.

**Academic evidence**: Merkle, C. & Weber, M. (2014). "The power of priors: How confirmation bias impacts market prices." *Journal of Prediction Markets*, 8(3), 34-56. Tetlock & Gardner (2015). *Superforecasting*.

**Detection signal**: Asymmetric response to confirmatory vs. disconfirmatory news. Low volume following contradictory news releases.

**Exploitation**: S008 (research that finds disconfirming evidence the market is ignoring provides genuine edge).

**Our track record**: T004 (Fed March) — the thesis was partly invalidated by hot core PCE data, but the CME-Poly divergence persisted for days because traders on both sides were selectively attending to supporting evidence. Our exit decision correctly identified the confirmation bias and cut the position.

---

#### 21. Anchoring

**Definition**: Initial values — whether meaningful or arbitrary — anchor subsequent estimates, with insufficient adjustment away from the anchor.

**Mechanism in prediction markets**: The current price is the most powerful anchor. New traders see "60 cents" and adjust from that number rather than forming independent estimates. Campbell & Sharpe (2009) found professional forecasters were significantly anchored to recent values, making 25% of macroeconomic forecast "surprises" predictable from anchoring patterns.

**Directional effect**: Toward the anchor value. Markets starting at 50 cents stay closer to 50 than markets starting at 20 or 80 with identical information. Creates inertia slowing price discovery.

**Academic evidence**: Tversky, A. & Kahneman, D. (1974). "Judgment under Uncertainty: Heuristics and Biases." *Science*, 185(4157), 1124-1131. Campbell & Sharpe (2009).

**Detection signal**: Markets on similar events with different starting prices converging slowly. Price changes proportional to distance from anchor rather than magnitude of new information.

**Exploitation**: S008 (form independent estimates before looking at market price — anchor immunity), S001 (base-rate anchoring as counter-strategy).

**Our track record**: All trades — we form independent probability estimates *before* checking market price, specifically to avoid anchoring. This is documented in each trade's reasoning field. The discipline of independent estimation is our primary anchoring defense.

---

#### 22. Belief Perseverance

**Definition**: Initial beliefs persist even after the evidence that created them is thoroughly discredited.

**Mechanism in prediction markets**: Lord, Ross & Lepper (1979) found that presenting mixed evidence to people with strong prior beliefs actually *increased* polarization. In prediction markets, once a price level is established by early news — even if later retracted or debunked — prices fail to fully return to pre-news levels. The "scar" of debunked information persists in prices.

**Directional effect**: Toward initial belief-driven price. After a false rumor pushes a contract to 70 cents and is debunked, price may settle at 55 rather than returning to the original 45.

**Academic evidence**: Ross, L., Lepper, M.R. & Hubbard, M. (1975). *Journal of Personality and Social Psychology*, 32(5), 880-892. Lord, C.G., Ross, L. & Lepper, M.R. (1979). *Journal of Personality and Social Psychology*, 37(11), 2098-2109.

**Detection signal**: Prices that fail to return to pre-news levels after retractions. Slow mean reversion after information corrections, with permanent price footprint.

**Exploitation**: S004 (belief perseverance means initial overreaction doesn't fully correct — the ~40% retracement target accounts for this), S008 (research that identifies belief perseverance creates edge by knowing the "true" pre-news level).

**Our track record**: T003 (Iran March 31) — the Trump deadline rhetoric pushed prices up, and even after Geneva talks showed progress, prices didn't return to pre-rhetoric levels. The belief that "Trump has a deadline" persisted in the price even after diplomatic developments contradicted it.

---

### Group 7: Market-Specific

#### 23. YES Bias

**Definition**: Traders systematically favor buying YES contracts over NO contracts at identical expected values, creating a structural "Optimism Tax."

**Mechanism in prediction markets**: Becker (2024) found Kalshi takers lose 1.12% on average by "overpaying for affirmative longshot outcomes." Reichenbach & Walther (2025) confirmed "tendency to overtrade the default and YES option" across 124M Polymarket trades. On Kalshi, YES at 1 cent has -41% expected value while NO at 1 cent has +23% — a 64pp divergence. NO contracts outperform YES at 69 of 99 price levels.

**Directional effect**: UP — YES prices are systematically inflated above true probability. "Things happening" is overpriced relative to "things not happening."

**Academic evidence**: Becker, J. (2024). "The Microstructure of Wealth Transfer in Prediction Markets." Kalshi analysis. Reichenbach, F. & Walther, M. (2025). "Exploring Decentralized Prediction Markets." SSRN 5910522.

**Detection signal**: Across a large portfolio, YES contracts resolve at rates below their average price. The structural edge is to systematically sell YES / buy NO at prices below ~35 cents.

**Exploitation**: S006 (the core structural edge — buy NO on overpriced YES "by date" markets).

**Our track record**: This is the foundational bias behind our S006 strategy. The 73.5% NO resolution rate on "by date" markets exists because YES is systematically overtraded. Every S006 position (T001, T008) exploits this bias.

---

#### 24. Favorite-Longshot Bias

**Definition**: Longshots are consistently overbet and favorites are consistently underbet across nearly all betting and prediction markets.

**Mechanism in prediction markets**: Snowberg & Wolfers (2010) used 5.6M horse race starts to show this is driven by probability misperceptions (consistent with probability weighting), not risk-love. Kalshi data (Burgi, Deng & Whelan 2025): contracts under 10 cents lose >60% of invested money; contracts above 50 cents earn small positive returns. Average pre-fee return on all Kalshi contracts: **-20%**.

Quantified from Becker (2025):

| Price Level | Actual Win Rate | Implied | Taker Return |
|------------|----------------|---------|-------------|
| 5 cents | 4.18% | 5% | -16.4% |
| 10 cents | 8.91% | 10% | -10.9% |
| 50 cents | ~50% | 50% | -2.65% |
| 95 cents | 95.83% | 95% | +0.87% |

**Directional effect**: UP longshots, DOWN favorites. Low-probability contracts systematically too expensive; high-probability contracts systematically too cheap.

**Academic evidence**: Griffith (1949). *American Journal of Psychology*. Snowberg & Wolfers (2010). *Journal of Political Economy*, 118(4). Whelan (2024). *Economica*, 91(361). Burgi, Deng & Whelan (2025). CEPR Discussion Paper.

Note: Reichenbach & Walther (2025) found **no general longshot bias on Polymarket** specifically, though YES bias was present. Platform structure matters.

**Detection signal**: Calibration analysis showing cheap contracts resolve YES less than implied. Systematic negative returns for longshot buyers, positive for favorite buyers.

**Exploitation**: S006 (buy high-probability NO contracts — the "favorite" that is underpriced), S007 (cumulative longshot bias across multi-outcome fields creates overround).

**Our track record**: T002 (Trump 2028 NO at 97.2%) and T007 (Maduro NO at 87.25%) — both buy the "favorite" (NO) at high-probability levels where the longshot bias suggests YES is overpriced.

---

#### 25. Action Bias

**Definition**: People have a penchant for action even when inaction would produce better outcomes, especially when acting as agents for others.

**Mechanism in prediction markets**: Bar-Eli et al. (2007) showed goalkeepers jump left/right 94% of penalty kicks despite staying center yielding the highest save probability — because the psychological cost of inaction exceeds the cost of wrong action. In prediction markets, this translates to overtrading: traders who have done research feel compelled to take a position even when the market is correctly priced.

**Directional effect**: UP (net) because action bias primarily manifests as buying (taking position = action; not trading = inaction), and the default action is buying YES.

**Academic evidence**: Patt, A. & Zeckhauser, R. (2000). "Action Bias and Environmental Decisions." *Journal of Risk and Uncertainty*, 21(1), 45-72. Bar-Eli, M. et al. (2007). *Journal of Economic Psychology*, 28(5), 606-621.

**Detection signal**: High volume with minimal price impact. Position-taking shortly after account funding. High turnover relative to information arrival rate.

**Exploitation**: S006 (action bias provides constant counterparty flow for NO positions — the YES buyers who "need to do something").

**Our track record**: T004 (Fed March) was arguably an action bias entry. With only 2.85% implied probability and no exceptional edge, we entered because the asymmetric payoff felt like action worth taking. The 17.5% loss validated that inaction (no trade) was the correct response.

---

#### 26. Compound Probability Neglect

**Definition**: People fail to properly compute joint probabilities of independent events, treating compound probabilities as approximately equal to their components rather than their product.

**Mechanism in prediction markets**: Nilsson & Andersson (2010) showed that when a low-probability football outcome was combined with high-probability outcomes, the compound was judged *more* likely than the low-probability component alone — a conjunction fallacy. Lee, Stallaert & Fan (2020) provided direct prediction market evidence: "Even when there are large numbers of transactions and high volumes of trades, probabilistic fallacies still occur" and "they tend to be persistent."

**Directional effect**: UP for compound/conditional outcomes. Multi-step scenarios overpriced because traders fail to multiply probabilities.

**Academic evidence**: Tversky, A. & Kahneman, D. (1983). "Extensional versus intuitive reasoning: The conjunction fallacy." *Psychological Review*, 90(4), 293-315. Nilsson, H. & Andersson, P. (2010). *Journal of Economic Psychology*, 31(2), 172-180. Lee, Stallaert & Fan (2020). "Anomalies in Probability Estimates for Event Forecasting on Prediction Markets." *Production and Operations Management*.

**Detection signal**: In event series with sub-markets, implied joint probability (product of individual prices) exceeding the explicit joint outcome price. Parlay-equivalent positions showing systematically negative returns.

**Exploitation**: S006 ("by date" markets often require a conjunction of conditions — compound neglect inflates their prices), S007 (detect when sub-market prices imply impossible joint probabilities).

**Our track record**: T001/T003/T005 (Iran) — "US strikes Iran by [date]" requires: (1) political will, (2) military readiness, (3) opportunity/trigger, (4) failure of diplomatic off-ramp. Each component may be 60-80% likely, but the conjunction is 60%^4 ≈ 13%, far below the ~60% market price. Compound probability neglect is a major contributor to the overpricing.

---

## 2. The Five Compound Patterns

Five named patterns where multiple biases compound to create predictable, large-magnitude mispricings.

---

### Pattern 1: The War Panic Premium

**Biases compounding**: Availability heuristic + Salience bias + Fear premium + YES bias + Narrative fallacy + Loss aversion

**Mechanism**: Vivid military/conflict news dominates media (availability). Strike imagery is dramatic (salience). Threatening outcomes carry a natural risk premium (fear premium). Traders prefer to bet on "something happening" (YES bias). A coherent escalation narrative ("first rhetoric, then deployment, then strike") makes the sequence feel inevitable (narrative fallacy). The potential consequence is so severe that traders overweight it even at low probability (loss aversion).

**Compound effect**: Each bias reinforces the others. The narrative provides the framework for availability to fill with vivid details. Fear premium makes the YES side emotionally compelling. Loss aversion makes NOT hedging against the worst case feel irresponsible. The result: war-related YES contracts trade 15-30pp above actuarial fair value.

**Domain**: GEO (strongest), SOC (terrorism), LAW (enforcement actions)

**Empirical evidence from our trades**: T001 (Iran June 30 at 66.5% vs. our 63% estimate), T003 (Iran March 31 at 57.5% vs. our 52% estimate), T005 (US/Israel Iran at 59% vs. our 55% estimate). Across all three Iran NO positions, the average war panic premium is ~6pp. Becker (2025): World Events contracts show 7.32pp maker-taker gap — largest of any Kalshi category.

**Exploitation**: S006 + S004 stack. S006 identifies the structural overpricing (time decay math). S004 fades the specific spikes within the premium (rhetoric events). Combined: fade the spike AND collect the structural premium.

---

### Pattern 2: The Narrative Cascade

**Biases compounding**: Narrative fallacy + Social proof/herding + FOMO + Representativeness + Cluster illusion

**Mechanism**: A compelling story emerges ("this candidate is surging," "Bitcoin is entering a new bull cycle"). The narrative provides a framework (narrative fallacy) that makes each new price movement look like confirmation of the trend (representativeness). Early buyers create visible momentum that draws herding (social proof). Accelerating prices trigger FOMO in observers. A few consecutive positive data points are read as a pattern (cluster illusion) even if statistically insignificant.

**Compound effect**: The cascade is self-reinforcing until an external shock breaks it. Each price increase confirms the narrative, attracts more herd participants, triggers more FOMO, and creates more "streak" data points. The cascade is fragile — any contradictory shock reverses it sharply (Bikhchandani et al. 1992). The reversal is where the exploitation opportunity lies.

**Domain**: CRY (strongest — narrative-driven, emotional, herd-prone), POL (primary momentum), GEO (escalation narratives)

**Empirical evidence**: Clinton & Huang (2025): 58% of Polymarket national markets showed negative serial correlation — consistent with narrative cascades followed by reversals. The SOTU "MAGA" market at 87% had cascade characteristics: the narrative "Trump always says MAGA" + herding + FOMO drove the price far above the true probability.

**Exploitation**: S004 (wait for cascade to exhaust, enter when it breaks). Key timing: enter 24-72h after the cascade peak, when the reversal is underway but before the full retracement. Target: 40% retracement.

---

### Pattern 3: The Deadline Decay Funnel

**Biases compounding**: Compound probability neglect + Deadline panic + YES bias + Present bias + Probability weighting

**Mechanism**: A "by date" market opens with YES overpriced (YES bias + probability weighting at the low-to-mid probability range). As time passes without the event occurring, the probability should decrease (each quiet day is evidence against). But present bias makes traders reluctant to buy NO on long-dated markets. Compound probability neglect prevents traders from correctly computing the cumulative probability of non-occurrence. As the deadline approaches, the declining probability finally forces panic selling by YES holders (deadline panic), creating accelerating price decay in the final days.

**Compound effect**: The funnel shape: slowly declining YES prices for most of the contract's life (present bias + compound neglect resist correct pricing), followed by sharp decline in the final 7-14 days (reality forces the adjustment). The early period has the most mispricing but lowest velocity; the late period has fast price movement but less remaining mispricing.

**Domain**: GEO ("strike by date"), CRY ("BTC above X by date"), LAW ("regulation by date"), TEC ("product launch by date")

**Empirical evidence**: Our S006 backtest: 73.5% of "by date" markets resolve NO. Page & Clemen (2013): prices biased toward 50% for distant events but well-calibrated near expiration. The pattern is: overpriced early, correctly priced late — the edge is captured by entering early and holding through the decay.

**Exploitation**: S006 (the entire strategy is built on this compound pattern). Enter when the decay funnel is widest (14-90 days from deadline). Exit at resolution or when price reaches estimated fair value.

---

### Pattern 4: The Partisan Echo Chamber

**Biases compounding**: Motivated reasoning + Identity-protective cognition + Confirmation bias + Anchoring + Belief perseverance

**Mechanism**: A politically charged market activates partisan identity (motivated reasoning). Sophisticated partisans use their analytical skills to defend group-congruent positions (identity-protective cognition). They selectively consume supporting evidence (confirmation bias). The established price becomes an anchor that resists updating (anchoring). Even when contradictory evidence arrives — polls shifting, events contradicting the narrative — the initial belief persists (belief perseverance).

**Compound effect**: This pattern is uniquely dangerous because it gets *worse* with trader sophistication. Kahan (2017) showed that more numerate/literate individuals are MORE polarized on identity topics, not less. The prediction market price becomes a consensus anchor that is defended by sophisticated partisans on both sides, creating a "sticky" price that responds asymmetrically: confirmatory news moves price, disconfirmatory news is absorbed without movement.

**Domain**: POL (strongest), GEO (when geopolitics becomes partisan — e.g., "who's tough on China?"), LAW (when legal outcomes have partisan valence)

**Empirical evidence**: SOTU markets — "Fake News" at 52% despite NEVER appearing in any Trump SOTU. The market was anchored to the belief that "Trump always says Fake News" (which is true at rallies), defended by partisan echo chambers that couldn't distinguish rally Trump from SOTU Trump. Our 15% estimate captured a 37pp edge precisely because we broke through the echo chamber with historical data.

**Exploitation**: S008 (research that cuts through partisan framing provides massive edge on politically charged markets), S004 (fade partisan overreaction after debates, primaries), S001 (forming independent estimates using base rates, not partisan narratives).

---

### Pattern 5: The Lottery Ticket Illusion

**Biases compounding**: Hope premium + Probability weighting + Action bias + Compound probability neglect + Scope insensitivity

**Mechanism**: A low-probability contract trades cheaply in absolute dollar terms ($0.05 per share), triggering the "lottery ticket" frame. Hope premium makes the potential 20x payoff emotionally compelling. Probability weighting overweights the small probability by 3-6x. Action bias makes buying feel better than not buying. Compound probability neglect means the multiple conditions required are not properly multiplied. Scope insensitivity means the difference between 5% and 1% true probability doesn't register — both feel like "unlikely but possible."

**Compound effect**: The biases stack multiplicatively. If probability weighting makes a 5% event feel like 15%, and hope premium adds another 3pp, and compound neglect inflates by another 5pp, the net effect is that a 5-cent contract trading at fair value feels like it should be worth 20-25 cents. The result: systematic, massive overpricing of longshot YES contracts. Kalshi data confirms: <10 cent contracts lose >60% of invested money; 1 cent YES contracts have -41% expected value.

**Domain**: CRY (lottery tickets everywhere — "BTC to $1M"), POL (longshot candidates), GEO (unlikely-but-dramatic scenarios)

**Empirical evidence**: T004 (Fed 25bp cut at 2.85%) was a lottery ticket that cost us 17.5%. Becker (2025): "takers disproportionately favor affirmative bets at longshot prices, losing 1.12% on average through an Optimism Tax." Snowberg & Wolfers (2010): driven by probability misperceptions, not risk-love.

**Exploitation**: S006 (sell the lottery tickets — be the counterparty to hope premium buyers), S007 (cumulative longshot bias across multi-outcome fields creates exploitable overround).

---

## 3. Tetlock's Framework

### 3.1 What Separates Superforecasters from Experts

The IARPA ACE tournament (2011-2015) produced hard numbers. The Good Judgment Project (Tetlock & Mellers, UPenn):

| Comparison | Improvement |
|-----------|------------|
| vs. control group (Year 1) | **60%** better |
| vs. control group (Year 2) | **~80%** better |
| vs. competing research teams | **35-72%** better |
| vs. intelligence analysts WITH CLASSIFIED INFORMATION | **30%** better |

**Brier score benchmarks:**

| Forecaster Type | Brier Score |
|----------------|------------|
| Random guessing | 0.50 |
| Regular forecasters | ~0.35 |
| Intelligence analysts (classified) | ~0.25-0.30 |
| Superforecasters (aggregate) | **~0.15-0.16** |
| Best individual superforecaster | **~0.14** |

Beyond foxes vs. hedgehogs, the specific cognitive habits:

1. **Active Open-Mindedness**: Beliefs are hypotheses to test, not treasures to protect.
2. **Need for Cognition**: Enjoy intellectual puzzles and complexity.
3. **Perpetual Beta**: The **single strongest predictor** — approximately **3x more powerful than intelligence** as a predictor of superforecaster status. Always self-correcting, never "done."
4. **Granular probability discrimination**: Use 10-15 degrees of uncertainty vs. experts' 3-5 buckets.
5. **Dragonfly eye perspective**: Synthesize multiple viewpoints into a single integrated assessment.
6. **Growth mindset**: Improve over time by tracking accuracy and learning from errors.

Critical finding: A single **1-hour training module** (base rates, Bayesian updating, cognitive biases) produced accuracy improvements that **persisted for at least one year**.

---

### 3.2 The Ten Commandments of Superforecasting

From Tetlock & Gardner (2015), *Superforecasting: The Art and Science of Prediction*:

| # | Commandment | Which PM Traders Violate | Severity |
|---|------------|-------------------------|----------|
| 1 | **Triage** — Focus on questions where effort can improve accuracy | Traders trade everything regardless of edge | Moderate |
| 2 | **Break problems into sub-components** (Fermi estimation) | Most traders use holistic gut feeling | **SEVERE** |
| 3 | **Strike the right balance between inside and outside views** — start with base rates | S006 data: 73.5% resolve NO, but traders consistently overprice YES | **SEVERE** |
| 4 | **Strike the right balance between under- and overreacting to evidence** | Two failure modes: anchoring or overreaction | **SEVERE** |
| 5 | **Look for clashing causal forces** in each problem | Traders pick a narrative and stick with it | Moderate |
| 6 | **Distinguish degrees of uncertainty** — use granular probabilities | Retail traders think in "likely/unlikely/coin-flip" | Moderate |
| 7 | **Strike the right balance between prudence and decisiveness** | Premature commitment + disposition effect | **SEVERE** |
| 8 | **Look for mistakes in your forecasting** — do postmortems | 70% of Polymarket traders lose money, suggesting near-zero learning | **SEVERE** |
| 9 | **Bring out the best in others** — use teams and diverse perspectives | Solo traders dominate prediction markets | Low |
| 10 | **Master the error-balancing cycle** — never stop practicing | Most traders trade for entertainment, not accuracy improvement | Moderate |

**The commandments we should self-audit against**: 3 (base rates), 4 (belief updating), 8 (postmortems). Our calibration/lessons.md system addresses Commandment 8. Our Reality Check Protocol (Section 5) addresses Commandment 3. Our Emotional Charge Index (Section 4) addresses Commandment 4.

---

### 3.3 Calibration Framework

Tetlock's calibration system:

**Brier Score**: The primary metric. Lower = better.
- 0.00 = perfect foresight
- 0.25 = random guessing on binary (equivalent to always saying 50%)
- 0.50 = maximally wrong (always 100% confident, always wrong)
- Superforecasters: ~0.15-0.16
- Our SOTU retrospective: Brier mine = 0.20 average, Brier market = 0.34 average

**Brier Decomposition**:
1. **Calibration (Reliability)**: How close are your probabilities to observed frequencies? Perfect = 0.
2. **Resolution (Discrimination)**: How much do your forecasts vary from the overall base rate? Higher = better.
3. **Uncertainty**: The inherent unpredictability of the events.

**Calibration curve**: Plot predicted probability (x-axis) vs. observed frequency (y-axis). Perfect calibration = 45-degree diagonal. Typical prediction markets show S-curve = favorite-longshot bias. Superforecaster calibration: ~0.01 deviation (their probabilities deviate from outcomes by just ~1 percentage point).

---

### 3.4 Base Rate Anchoring

**Reference Class Forecasting** (Kahneman & Tversky theory, Flyvbjerg operationalization):

1. **Identify the reference class** of similar past events
2. **Establish the probability distribution** from the class
3. **Position the specific case** within the distribution, adjusting modestly

Kahneman called Flyvbjerg's work "the single most important piece of advice regarding how to increase accuracy in forecasting."

**How base rates protect against biases:**

| Bias | How Base Rates Counter It |
|------|--------------------------|
| Availability | Base rate says X happens 5% of the time, regardless of how vivid it feels |
| Narrative | The story is compelling, but historically similar stories led to action only 15% of the time |
| Representativeness | This case "looks like" war, but the base rate for rhetoric → action is ~5% |
| Anchoring | Start from the base rate, not from the current market price |
| Optimism/Hope | The base rate for this class of event is 3%, not the 15% you'd like |
| Confirmation | The base rate includes all cases, not just the ones that confirm your view |

**Applied to our strategies**: S006 is fundamentally a base-rate strategy — 73.5% of "by date" markets resolve NO (count-weighted), 60% (volume-weighted). Every S006 trade starts from this base rate and adjusts modestly for domain-specific factors.

---

### 3.5 The Updating Problem

**The Bayesian ideal**: P(H|E) = P(E|H) × P(H) / P(E). Update beliefs proportionally to the diagnosticity of the evidence.

**The human reality** (two opposing errors):

| Error | When It Dominates | Magnitude |
|-------|------------------|-----------|
| **Conservatism** (underreaction) | Expected or mildly surprising events; statistical/abstract evidence | Update at 50-75% of Bayesian optimal (Edwards 1968) |
| **Overreaction** | Highly surprising, vivid, narrative-consistent events | Update exceeds Bayesian optimal, often dramatically |

**The superforecaster pattern** (Atanasov et al. 2020): **Incremental updaters are ~30% more accurate than large-jump updaters** (515 forecasters, 80,000+ forecasts).

The superforecaster updating style:
- Many small updates (1-3pp) on routine evidence
- Occasional larger updates on genuinely diagnostic evidence
- Updates in both directions (willing to revise upward AND downward)
- Triggered by evidence, not emotion
- Never updates to 0% or 100% — always maintains "perpetual beta"

**The "dragonfly eye" technique**: Aggregate multiple weak signals from diverse sources into a single estimate, rather than relying on one strong signal. Each source may be biased, but the biases partially cancel when synthesized.

---

### 3.6 Tetlock Framework Applied to T001-T008

| Trade | Base Rate First? | Disconfirming Evidence Sought? | Inside/Outside View? | Grade |
|-------|-----------------|-------------------------------|---------------------|-------|
| T001 (S006 Iran Jun 30) | YES — GEO NO rate 64.3% | Partial — noted weak NO rate for GEO | Mixed — used base rate but acknowledged "edge is marginal" | B+ |
| T002 (S007 Trump 2028 GOP) | YES — constitutional prohibition = ~0% base | YES — considered political uncertainty | Correct — outside view (22nd Amendment) dominates | A |
| T003 (S004 Iran Mar 31) | Partial — cited base rates but lead with spike analysis | YES — listed structural factors | Inside view slightly dominant — specific rhetoric analysis | B |
| T004 (S003 Fed March) | Weak — focused on CME divergence, not on base rate of March cuts historically | Moderate — noted PCE against thesis | Inside view heavy — saw "this time" signals | C+ |
| T005 (S008 Iran Mar 31) | YES — "55% YES" from first principles | YES — explicit "what would change my mind" | Good balance — base rate + specific synthesis | A- |
| T006 (S001 Vance 2028) | YES — "100% nomination for modern sitting VPs" | YES — "no Trump endorsement yet," "Rubio risk" | Excellent — outside view (VP base rate) as primary anchor | A |
| T007 (S008 Maduro) | Moderate — not explicit historical base rate | YES — listed resolution ambiguity, drift risk | Inside view dominant — specific legal situation | B |
| T008 (S006 BTC 150K) | YES — year-2 post-halving returns (-58%, -73%, -64%) | YES — noted "massive BTC rally" risk | Good balance — historical cycle as base rate, specific conditions as adjustment | A- |

**Pattern**: Our strongest trades (T002, T006, T008) start from clear base rates. Our weakest (T004) started from a specific case comparison (CME-Poly divergence) without a base-rate anchor. **The lesson: always anchor on outside view first, adjust with inside view second.**

---

## 4. The Emotional Charge Index (ECI)

### 4.1 Design

The ECI scores how much "emotional charge" a piece of news carries. **Higher ECI → bigger deviation from true probability → bigger exploitable gap.**

**Six dimensions, each scored 1-10:**

| Dimension | What It Measures | Score 1 (Low) | Score 10 (High) |
|-----------|-----------------|---------------|-----------------|
| **Fear Factor** | Threat/danger response activation | Routine policy announcement | Active military engagement, imminent threat |
| **Vividness** | Concrete, specific, dramatic imagery | Abstract statistics, diplomatic communiqué | Video footage, named casualties, specific weapons |
| **Narrative Coherence** | Fits a compelling escalation story | Contradicts existing narratives | Confirms and extends the dominant narrative |
| **Identity Activation** | Triggers partisan/in-group identity | Bipartisan/apolitical topic | Deep partisan divide (us vs. them framing) |
| **Recency Shock** | Sudden departure from prior expectations | Expected, gradual, priced in | Completely unexpected, discontinuous from trend |
| **Media Amplification** | Dominance of news coverage | Below-the-fold, niche coverage | Leading all networks, trending globally |

### 4.2 Composite Score

**ECI = (Fear + Vividness + Narrative + Identity + Recency + Media) / 6**

| ECI Range | Classification | Expected Market Response | Action |
|-----------|---------------|------------------------|--------|
| 1-3 | **LOW** | Minimal mispricing | No S004 opportunity |
| 4-5 | **MODERATE** | 3-8pp overreaction | S004 at half-size (1.5% bankroll) |
| 6-7 | **HIGH** | 8-15pp overreaction | S004 at full-size (3% bankroll) |
| 8-10 | **EXTREME** | 15-30pp overreaction | S004 at full-size; monitor for continued spike |

### 4.3 Trigger Rule for S004

**When ECI ≥ 7 AND market moves ≥10% in 24h (or ≥20% in 7d), classify as emotional overreaction.** Proceed to S004 entry analysis.

**When ECI < 4 AND market moves ≥10%, classify as likely structural.** Do NOT fade — the move is probably information-driven.

**When ECI 4-6 AND market moves ≥10%, ambiguous.** Run S004 classification checklist for tiebreak.

### 4.4 Calibration: Scoring Known Events

| Event | Fear | Vivid | Narr | Identity | Recency | Media | **ECI** | Market Move | Actual Overreaction |
|-------|------|-------|------|----------|---------|-------|---------|-------------|---------------------|
| Trump 10-15 day Iran deadline (Feb 19) | 8 | 6 | 9 | 5 | 7 | 8 | **7.2** | +25% on Iran markets | ~5-8pp (markets retraced partially after Geneva talks) |
| Hot core PCE 3.0% (Feb 20) | 3 | 2 | 4 | 2 | 4 | 5 | **3.3** | -1.5% on Fed cut odds | Minimal — structural move, correctly priced |
| SOTU 2026 (Feb 24) | 2 | 4 | 3 | 7 | 5 | 8 | **4.8** | N/A (resolved same day) | Moderate — partisan identity drove mispricing on mention markets |
| Geneva talks progress (Feb 23-26) | 2 | 2 | 3 | 3 | 4 | 4 | **3.0** | -3% on Iran markets (slow drift) | Correctly conservative — gradual evidence, not emotional |

**Preliminary calibration**: The ECI correctly distinguishes the Iran rhetoric spike (7.2 → emotional, correctly faded by T003) from the PCE data release (3.3 → structural, correctly recognized as thesis-killing for T004). The scoring system works directionally on our known events.

### 4.5 Hypothesis to Test

**H1**: High ECI news events (≥7) produce S004 opportunities within 24-72h in >60% of cases.
**H2**: ECI correlates with magnitude of overreaction (higher ECI → more pp of mispricing).
**H3**: Fear Factor is the most predictive single dimension for GEO markets; Identity Activation is most predictive for POL markets.

Track these across the next 20+ events that produce market moves ≥10%.

---

## 5. The Reality Check Protocol

*A 1-page template to strip psychological noise and return to fundamental probability. Complete before every trade entry.*

---

### REALITY CHECK — Trade Pre-Entry Template

**Market**: _______________________________________________
**Current price**: ______ **My independent estimate**: ______

---

**Step 1: BASE RATE**
- Reference class: What type of event is this? _______________________
- Historical frequency: How often has this happened in similar circumstances? ______%
- Source for base rate: ____________________________________
- **My base rate anchor**: ______%

**Step 2: SCOPE CHECK**
- Time window: _____ days remaining
- Am I distinguishing near-term vs. long-term correctly? [ ] Yes [ ] No
- Implied daily hazard rate: _____% (compare to base rate)

**Step 3: INDEPENDENCE CHECK**
- Current market price: ______
- Did I form my estimate BEFORE checking the market price? [ ] Yes [ ] No
- If no: re-estimate from base rate + evidence, ignoring market price

**Step 4: INSIDE/OUTSIDE VIEW**
- Outside view (base rate): ______%
- Inside view (case-specific adjustment): +/- _____pp
- Justification for adjustment: ________________________________
- **Combined estimate**: ______%
- Is my adjustment >15pp from base rate? If yes, what exceptional evidence justifies this?

**Step 5: COMPOUND PROBABILITY CHECK**
- Does this event require multiple things to happen? [ ] Yes [ ] No
- If yes, list components and their individual probabilities:
  - P(A) = ____%  P(B) = ____%  P(C) = ____%
  - Joint: P(A×B×C) = ____%
- Is my estimate close to the joint probability? [ ] Yes [ ] No

**Step 6: EMOTIONAL AUDIT**
- My emotional reaction to this outcome: _____________________________
- ECI score (if news-driven): _____
- Am I correcting for: [ ] Fear [ ] Hope [ ] Excitement [ ] Partisan identity [ ] None needed
- Bias most likely affecting me right now: _____________________________

**Step 7: DEVIL'S ADVOCATE**
- The strongest argument that the market is RIGHT and I'm wrong:
  _______________________________________________________________
  _______________________________________________________________
- How strong is this argument? [ ] Weak [ ] Moderate [ ] Strong
- If strong: reduce confidence or skip trade

**Step 8: THE EMPTY WALLET TEST**
- If this were my last $100: would I change my probability estimate? [ ] No (confident) [ ] Yes → revised: _____%
- If I had to defend this estimate to a superforecaster, what would they challenge?
  _______________________________________________________________

---

**FINAL DECISION**
- Base rate: ______%
- My estimate: ______%
- Market price: ______%
- Edge: ______pp
- Minimum required edge for this strategy: ______pp
- **ENTER** [ ] / **SKIP** [ ] / **REVISIT LATER** [ ]

---

## 6. Integration with Existing Strategies

### 6.1 How B01 Upgrades S004 (Contrarian Overreaction)

**Before B01**: S004 used a classification checklist (structural vs. emotional) with subjective scoring.

**After B01**:
1. **ECI trigger**: When ECI ≥ 7 AND market moves ≥10%, classify as emotional overreaction automatically. When ECI < 4, classify as structural automatically. This replaces the subjective "emotional score ≥ 4" with a more rigorous, multi-dimensional assessment.
2. **Compound pattern recognition**: Check which of the Five Compound Patterns applies. War Panic Premium → GEO fade. Narrative Cascade → wait for cascade break. Partisan Echo Chamber → POL fade after debate/gaffe. Lottery Ticket Illusion → avoid fading (structural overpricing, not spike).
3. **Reality Check Protocol**: Run before every S004 entry. Step 7 (Devil's Advocate) is critical — the strongest argument the market is right must be explicitly articulated and addressed.
4. **Bias interaction awareness**: Check if multiple biases are compounding. The more biases stacking in one direction, the more likely the move is emotional (and fadeable) rather than structural.

### 6.2 How B01 Upgrades S006 (Time Decay)

**Before B01**: S006 relied on the statistical finding that 73.5% of "by date" markets resolve NO.

**After B01**:
1. **Mechanistic understanding of WHY 73.5% resolve NO**: It's not just a statistical regularity — it's the compound effect of YES bias + probability weighting + compound probability neglect + fear premium + hope premium + action bias. These biases are structural (rooted in human psychology), not circumstantial, so the pattern should persist.
2. **Domain-specific bias weighting**: GEO overpricing is primarily fear premium + availability. CRY overpricing is primarily hope premium + FOMO. POL overpricing is primarily motivated reasoning + YES bias. Different bias compositions suggest different optimal entry conditions.
3. **Probability weighting sweet spot**: The probability weighting function crossover at ~30-33% means contracts priced below 33% are in the strongest overweighting zone. S006 should prioritize markets where YES is priced 10-33% (maximum probability weighting distortion). Above 33%, the overpricing decreases.
4. **Present bias discount**: Long-dated S006 positions capture the present-bias discount — traders are unwilling to lock capital at extreme NO prices for months, so NO is structurally underpriced on long-duration markets.

### 6.3 How B01 Upgrades S008 (Information Edge)

**Before B01**: S008 focused on finding information the market doesn't have.

**After B01**:
1. **Confirmation bias exploitation**: The market has confirmation bias — it responds asymmetrically to confirming vs. disconfirming evidence. S008's edge is greatest when our research finds *disconfirming* evidence that the market is structurally biased against incorporating. (Example: SOTU "Fake News" — our research disconfirmed the market's belief, and the market couldn't incorporate it because of identity-protective cognition.)
2. **Anchoring immunity**: S008 must form estimates BEFORE checking market prices. The Reality Check Protocol Step 3 enforces this.
3. **Narrative fallacy defense**: S008 research should explicitly test "what if the narrative is wrong?" before entering. The strongest S008 edges come from situations where the dominant narrative is both compelling AND wrong.
4. **Tetlock integration**: Apply superforecaster habits — granular probability (not "likely/unlikely"), dragonfly eye (synthesize multiple sources), perpetual beta (update as evidence arrives), and postmortems (track every S008 estimate vs. outcome for calibration).

### 6.4 Bias-to-Strategy Mapping

| Primary Bias | Best Counter-Strategy | Why |
|-------------|----------------------|-----|
| Availability + Salience | S004 (fade spike) | Media-driven overreaction creates fade opportunity |
| Fear premium | S006 (time decay) | Structural overpricing of feared "by date" events |
| Hope premium | S006 (sell longshots) | Systematic overpricing of exciting YES outcomes |
| Motivated reasoning | S008 (research edge) | Non-partisan research cuts through partisan pricing |
| YES bias + Action bias | S006 (buy NO) | Be the counterparty to structural YES overbuying |
| Probability weighting | S006 + S007 | Both tails overpriced → sell tails, buy midrange |
| Compound prob. neglect | S006 + S007 | Multi-step events overpriced → sell conjunctions |
| Conservatism | S005 (momentum) | Market underreacts to expected news → ride the drift |
| Anchoring | S008 (independent est.) | Form estimate before checking price → avoid anchor |
| Herding + FOMO | S004 (fade cascade) | Wait for cascade to break, then fade the overshoot |
| Narrative fallacy | S004 + S008 | Counter-narrative research + fade when narrative breaks |
| Present bias | S001 (long-dated hold) | Capture the discount on long-duration correct estimates |
| Belief perseverance | S004 (incomplete revert) | Target 40% retracement, not full reversion — perseverance prevents full correction |

---

## Sources

### Foundational Papers

1. Tversky, A. & Kahneman, D. (1973). "Availability: A heuristic for judging frequency and probability." *Cognitive Psychology*, 5(2), 207-232.
2. Tversky, A. & Kahneman, D. (1974). "Judgment under Uncertainty: Heuristics and Biases." *Science*, 185(4157), 1124-1131.
3. Kahneman, D. & Tversky, A. (1979). "Prospect Theory: An Analysis of Decision under Risk." *Econometrica*, 47(2), 263-291.
4. Tversky, A. & Kahneman, D. (1983). "Extensional versus intuitive reasoning: The conjunction fallacy." *Psychological Review*, 90(4), 293-315.
5. Kahneman, D. & Tversky, A. (1984). "Choices, values, and frames." *American Psychologist*, 39(4), 341-350.
6. Tversky, A. & Kahneman, D. (1992). "Advances in Prospect Theory: Cumulative Representation of Uncertainty." *Journal of Risk and Uncertainty*, 5(4), 297-323.
7. Prelec, D. (1998). "The Probability Weighting Function." *Econometrica*, 66(3), 497-528.

### Cognitive Bias Research

8. Edwards, W. (1968). "Conservatism in human information processing." In *Formal Representation of Human Judgment*.
9. Kunda, Z. (1990). "The case for motivated reasoning." *Psychological Bulletin*, 108(3), 480-498.
10. Ross, L., Lepper, M.R. & Hubbard, M. (1975). *Journal of Personality and Social Psychology*, 32(5), 880-892.
11. Lord, C.G., Ross, L. & Lepper, M.R. (1979). *Journal of Personality and Social Psychology*, 37(11), 2098-2109.
12. Kahan, D.M. (2017). "Misconceptions, Misinformation, and the Logic of Identity-Protective Cognition." SSRN 2973067.
13. Kahan, D.M. et al. (2012). "The polarizing impact of science literacy." *Nature Climate Change*, 2, 732-735.
14. Gilovich, T., Vallone, R. & Tversky, A. (1985). "The hot hand in basketball." *Cognitive Psychology*, 17(3), 295-314.
15. Desvousges, W.H. et al. (1992). "Measuring Nonuse Damages Using Contingent Valuation."
16. Patt, A. & Zeckhauser, R. (2000). "Action Bias and Environmental Decisions." *Journal of Risk and Uncertainty*, 21(1), 45-72.
17. Bar-Eli, M. et al. (2007). "Action bias among elite soccer goalkeepers." *Journal of Economic Psychology*, 28(5), 606-621.
18. Ruggeri, K. et al. (2020). "Replicating patterns of Prospect Theory." *Nature Human Behaviour*, 4, 622-633.

### Prediction Market & Betting Research

19. Snowberg, E. & Wolfers, J. (2010). "Explaining the Favorite-Longshot Bias." *Journal of Political Economy*, 118(4), 723-746.
20. Reichenbach, F. & Walther, M. (2025). "Exploring Decentralized Prediction Markets." SSRN 5910522.
21. Becker, J. (2024/2025). "The Microstructure of Wealth Transfer in Prediction Markets."
22. Burgi, Deng & Whelan (2025). "Makers and Takers: The Economics of the Kalshi Prediction Market." CEPR.
23. Clinton, J. & Huang, T.F. (2025). Vanderbilt prediction market study.
24. Page, L. & Clemen, R. (2013). "Do Prediction Markets Produce Well-Calibrated Probability Forecasts?" *Economic Journal*, 123(568), 491-513.
25. Manski, C.F. (2006). "Interpreting the Predictions of Prediction Markets." *Economics Letters*.
26. Wolfers, J. & Zitzewitz, E. (2006). "Interpreting Prediction Market Prices as Probabilities." NBER WP 12200.
27. Cowgill, B. & Zitzewitz, E. (2015). "Corporate Prediction Markets." *Review of Economic Studies*, 82(4), 1309-1341.
28. Whelan, K. (2024). "Risk aversion and favourite-longshot bias." *Economica*, 91(361).
29. Lee, Stallaert & Fan (2020). "Anomalies in Probability Estimates for Event Forecasting on Prediction Markets." *Production and Operations Management*.
30. Nilsson, H. & Andersson, P. (2010). *Journal of Economic Psychology*, 31(2), 172-180.

### Market Microstructure & Herding

31. Banerjee, A.V. (1992). "A Simple Model of Herd Behavior." *Quarterly Journal of Economics*, 107(3), 797-817.
32. Bikhchandani, S., Hirshleifer, D. & Welch, I. (1992). *Journal of Political Economy*, 100(5), 992-1026.
33. Park, A. & Sgroi, D. (2022). "Herding behavior in prediction markets."
34. Merkle, C. & Weber, M. (2014). "The power of priors." *Journal of Prediction Markets*, 8(3), 34-56.
35. Angelini, G., De Angelis, L. & Singleton, C. (2022). *International Journal of Forecasting*, 38(1), 282-299.
36. Choi, D. & Hui, S.K. (2014). *Journal of Economic Behavior & Organization*, 107(B), 614-629.
37. Sonnemann, Camerer, Fox & Langer (2013). *PNAS*.
38. Bordalo, P., Gennaioli, N. & Shleifer, A. (2012/2013). *QJE* / *AER*.

### Superforecasting & Calibration

39. Tetlock, P.E. (2005). *Expert Political Judgment*. Princeton University Press.
40. Tetlock, P.E. & Gardner, D. (2015). *Superforecasting*. Crown.
41. Mellers, B., Tetlock, P.E. et al. (2014). "Forecasting Tournaments." *Current Directions in Psychological Science*, 23(4), 290-295.
42. Campbell, S.D. & Sharpe, S.A. (2009). "Anchoring Bias in Consensus Forecasts." *Journal of Financial and Quantitative Analysis*, 44(2), 369-390.
43. Atanasov, P. et al. (2020). Belief updating study (515 forecasters, 80,000+ forecasts).
44. Bollerslev, T. & Todorov, V. (2011). "Tails, Fears, and Risk Premia." *Journal of Finance*, 66(6), 2165-2211.
45. Kelly, B. & Jiang, H. (2014). "Tail Risk and Asset Prices." *Review of Financial Studies*, 27(10).

### Other

46. Taleb, N.N. (2007). *The Black Swan*. Random House.
47. Laibson, D. (1997). *Quarterly Journal of Economics*, 112(2), 443-477.
48. Przybylski, A.K. et al. (2013). *Computers in Human Behavior*, 29(4), 1841-1848.
49. Ante, L. (2023). *PLOS ONE*.
50. Croson, R. & Sundali, J. (2005). *Journal of Risk and Uncertainty*, 30(3), 195-209.
51. Simmons, J.P. et al. (2011). *Journal of Consumer Research*, 38(1), 1-15.
52. Griffith (1949). *American Journal of Psychology*, 62, 290-294.
53. Bar-Hillel, M. (1973). *Organizational Behavior and Human Performance*.
54. Kahneman, D., Ritov, I. & Schkade, D. (1999). *Journal of Risk and Uncertainty*, 19, 203-235.
