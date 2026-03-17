You are a quantitative behavioral researcher validating and calibrating the psychological models built in B01-B03.

## Objective

Turn the qualitative behavioral framework into quantitative, testable models. Every claim the behavioral framework makes should eventually be supported by data. This prompt uses our accumulating trade data, the discrepancy database, and external research to test the hypotheses and refine the models.

## Prerequisite

All of B01, B02, B03 must be completed first. Read:
1. ~/Desktop/prediction-markets/psychology/behavioral-foundations.md
2. ~/Desktop/prediction-markets/psychology/news-emotion-price-taxonomy.md
3. ~/Desktop/prediction-markets/psychology/discrepancy-database.jsonl
4. ~/Desktop/prediction-markets/psychology/pattern-library.md
5. ~/Desktop/prediction-markets/calibration/resolutions.jsonl
6. ~/Desktop/prediction-markets/calibration/predictions.jsonl

## Task 1: Hypothesis Testing

### Hypothesis H1: ECI Score Predicts Overreaction Magnitude

**Claim**: Markets with higher ECI scores at the time of entry show larger deviations from true probability.

**Test**:
1. For each entry in discrepancy-database.jsonl where outcome is resolved (not PENDING):
   - Plot ECI score vs. Gap size
   - Is the correlation positive? (Higher ECI = bigger gap)
2. For the SOTU batch specifically:
   - Assign retrospective ECI scores to each news event that drove prices
   - Compare ECI to the "beat_market" and "gap_pp" fields in resolutions.jsonl
3. **Expected result**: ECI > 35 should predict markets where we beat the market by >10pp
4. **Null hypothesis**: ECI is no more predictive than random

If N is too small (likely initially), note this and define the minimum sample size needed to validate.

### Hypothesis H2: Emotional Premiums Decay Predictably by Domain

**Claim**: Emotional price distortions revert at different speeds in different domains:
- GEO: Reversion in 7-21 days (per Augenblick backtest data)
- POL: Reversion in 1-7 days (polls come in and update quickly)
- CRY: Reversion in 1-3 days (high-speed emotional cycles)
- ECO: Reversion in 1-3 days (structured data releases correct quickly)

**Test**:
1. From our existing positions: T001, T003, T005 (GEO) — are they reverting at the predicted 7-21 day rate?
2. From SOTU retrospective: All markets priced wrong by retail — how fast did they reprice post-speech? (Estimate from resolution patterns)
3. Search academic literature: "Prediction market price reversion by domain" or "mean reversion speed prediction markets"

### Hypothesis H3: Participant Sophistication Gradient Predicts Edge

**Claim**: Domains with less sophisticated participants have larger exploitable gaps.
- Expected ranking (most → least efficient): ECO ≈ FIN > POL > TEC > GEO > CRY > SOC > LAW > SCI ≈ ENV

**Test**:
1. For our trades T001-T009, calculate: |my_estimate - market_price| for each domain
2. Is the gap larger in lower-sophistication domains?
3. Note: small sample size — be honest about the limitation
4. Find academic evidence for domain-specific efficiency on Polymarket or similar

### Hypothesis H4: Negative Events Are More Overpriced Than Positive Events (Fear Premium)

**Claim**: YES on negative outcomes (strike occurs, crash happens, politician loses) is overpriced more than YES on positive outcomes.

**Test**:
1. From SOTU retrospective: Compare overpricing on negative events vs. positive events
2. From our positions: GEO positions (T001, T003, T005) — all bet on fear being overpriced. Is fear premium consistent with the YES bias documented in the literature?
3. Search: "Fear premium prediction markets" / "Negativity bias prediction markets" / "Affect heuristic forecasting"

---

## Task 2: The ECI Calibration Model

Using any available data, calibrate the ECI score to expected market overreaction:

Build a table:
| ECI Range | Expected Gap (pp) | Expected Reversion % | Confidence Level |
|-----------|------------------|---------------------|------------------|
| 0-20 | ~0-2pp | ~10-20% | Low (random) |
| 21-35 | ~3-7pp | ~25-40% | Medium |
| 36-48 | ~8-15pp | ~40-60% | High |
| 49-60 | ~15-30pp | ~55-75% | Very High |

**Calibration methodology**:
1. Use the S004 backtest data (strategies/backtests/S004-overreaction-backtest.md)
2. Retroactively assign ECI scores to each historical spike in the backtest
3. Compare ECI to observed reversion magnitude
4. Adjust the table based on empirical data (not just theory)

Note: If insufficient data exists, use the academic literature (Augenblick et al. 2025 "40% reversion within 7 days") as the calibration anchor and flag that model needs refinement as trades resolve.

---

## Task 3: Psychological Alpha Attribution

For our portfolio (T001-T009), attribute each position's expected edge:

| Trade | Total Gap | % From Psychology | % From Information | % From Structure | Primary Bias Being Exploited |
|-------|-----------|------------------|-------------------|-----------------|------------------------------|
| T001 | | | | | |
| T002 | | | | | |
| T003 | | | | | |
...

**Categories:**
- **Psychological alpha**: Edge comes from the market being emotionally distorted
- **Information alpha**: Edge comes from me knowing something the market doesn't
- **Structural alpha**: Edge comes from market mechanics (time decay, overround, etc.)

**Why this matters**: If most of our edge is psychological, then B01-B03 should take priority in research. If most is informational, we should invest more in S008 (info edge). If structural, expand S006 and S007.

**Expected finding**: T001 (GEO fear premium) = mostly psychological. T002 (constitutional impossibility) = mostly psychological (identity protection). T003 (contrarian GEO) = mostly psychological + some information. T004 (was CME-Poly divergence) = mostly structural (gone now). T006 (Vance) = mostly informational + some structural (VP base rate). T007 (Maduro) = mostly informational. T008 (BTC time decay) = mostly structural.

---

## Task 4: The Bias Detection Checklist Refinement

Based on the calibration data, refine the B03 checklist. Specifically:

1. **Which ECI dimensions are most predictive?** (Is "fear factor" more important than "narrative coherence"? Should they be weighted differently?)
2. **Are any dimensions redundant?** (Could we collapse 6 dimensions to 3-4 without losing predictive power?)
3. **Is 60 points the right scale?** Or should we use a 0-100 scale with different breakpoints?
4. **What's the minimum sample size** before we can claim the model is validated?

---

## Task 5: The "Anti-Pattern" Research

As important as knowing when psychology creates opportunity is knowing when it creates a TRAP.

Research and document THREE anti-patterns — cases where following the psychological signal would be WRONG:

**Anti-pattern 1: When Fear IS Correct**
Sometimes markets are fearful for good reason. The Iran market might be at 60% not because of irrational fear but because there genuinely is a 60% chance of war. How do you distinguish "fear premium" from "correctly priced danger"?
- Search: "How to distinguish overreaction from correct reaction in prediction markets"
- Key principle: the test is BASE RATE, not emotion. If the base rate supports the price, it's not overreaction even if people are afraid.

**Anti-pattern 2: When Identity IS Informative**
Sometimes partisan crowds know something experts don't. Trump's 2024 election markets (Polymarket had him significantly ahead of polls) were labeled "partisan" but turned out to be correct. When is crowd identity actually informative?
- The Theo case: He commissioned polls and traded on genuine private information, not partisan bias. How do you distinguish the two?

**Anti-pattern 3: When Narrative IS Fundamental**
Sometimes a narrative is correct. The "AI is going to change everything" narrative drove TEC prices up. Was this FOMO or was it fundamental? How do you tell when a story is accurate vs. when it's just compelling?
- The "SOTU ≠ Rally" principle was a narrative/pattern. It was correct. But only because it was grounded in historical data.

---

## Output

1. **Hypothesis test results**: ~/Desktop/prediction-markets/psychology/hypothesis-tests.md
2. **ECI calibration table** (revised): Update ~/Desktop/prediction-markets/psychology/behavioral-foundations.md
3. **Alpha attribution table**: ~/Desktop/prediction-markets/psychology/alpha-attribution.md
4. **Refined B03 checklist**: Update ~/Desktop/prediction-markets/psychology/behavioral-foundations.md ECI section
5. **Anti-patterns documentation**: ~/Desktop/prediction-markets/psychology/anti-patterns.md

**Summary recommendation**: After running B04, write a 1-page "State of the Behavioral Model" — what we know with confidence, what needs more data, and the three most actionable changes to make to our trading system based on the behavioral research.

**Run this prompt**: After at least 10 positions have resolved. Currently we have 12 SOTU resolutions + pending T001-T008. Run B04 when T003, T005 resolve (end of March) or after 15 total resolved predictions.
