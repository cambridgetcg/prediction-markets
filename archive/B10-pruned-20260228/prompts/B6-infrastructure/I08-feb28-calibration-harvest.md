# I08 — Feb 28 Calibration Harvest

**Run date**: February 28, 2026 (or immediately after market resolutions are confirmed)
**Depends on**: I07 (which runs the S011 sweep simultaneously)

This prompt is the calibration-only companion to I07. I07 focuses on operational tasks (S011 sweep, portfolio updates). I08 focuses exclusively on the calibration data quality and what it tells us about where to improve.

## Read First

1. `~/Desktop/prediction-markets/calibration/resolutions.jsonl` — all logged resolutions
2. `~/Desktop/prediction-markets/calibration/calibration.md` — current Brier dashboard
3. `~/Desktop/prediction-markets/calibration/lessons.md` — running lessons log
4. `~/Desktop/prediction-markets/calibration/predictions.jsonl` — all predictions made before outcome was known

---

## Task 1: Log All Feb 28 Resolutions

I07 may have already done this partially. Complete the full resolution sweep if not done:

Resolved market clusters to check:
1. SOTU Feb 25 sub-markets (all Trump nicknames, references, mentions, attendance)
2. "US strikes Iran by Feb 28" — should resolve NO
3. "Fed rate change by Feb 28" — should resolve NO
4. Any "by February" date markets in crypto, political
5. Our paper trade PT003/PT005 monitoring (they resolve Mar 31, not today — confirm)

For every resolution:
- Record outcome (1 = YES, 0 = NO)
- Record our prediction at time of making it
- Record market price at time of our prediction
- Compute: `my_brier = (outcome - my_estimate)²` and `market_brier = (outcome - market_price)²`
- Record beat-market (1 if my_brier < market_brier, else 0)

---

## Task 2: Deep Calibration Analysis

After logging, run analysis on cumulative dataset.

### 2a. YES vs NO Calibration Problem

We know: 7/7 on NO, 2/5 on YES (as of I05). Does Feb 28 data shift this pattern?

Build the following table from all resolved predictions:

| Category | N | My Avg Estimate | Avg Outcome | Calibration Gap | Bias Direction |
|----------|---|----------------|-------------|-----------------|----------------|
| YES bets (my_estimate > 0.5) | N_y | X% | Y% | Z% | Overconfident/Underconfident |
| NO bets (my_estimate < 0.5) | N_n | X% | Y% | Z% | |
| Near-certain YES (>80%) | N | | | | |
| Near-certain NO (<20%) | N | | | | |
| Close calls (40-60%) | N | | | | |

**The diagnostic question**: Are we overconfident on YES (predicting 70% and winning only 50% of the time), or are we just picking wrong YES bets? These have different solutions:
- Overconfidence → calibrate down all YES estimates by X%
- Wrong selection → improve market selection, not the calibration method

### 2b. Domain Performance

| Domain | N | My Brier | Market Brier | Beat Rate | Edge vs Market |
|--------|---|----------|-------------|-----------|----------------|
| POL | | | | | |
| GEO | | | | | |
| ECO | | | | | |
| TEC | | | | | |
| SOC (SOTU) | | | | | |

Where is our genuine edge? Where are we losing to the market?

### 2c. The SOTU Anomaly

We went 9/12 (75%) on SOTU predictions. But SOTU markets are different from most Polymarket markets:
- High volume, lots of entertainment-motivated traders
- Resolution criteria are sometimes ambiguous (did Trump "say" X? Depends on interpretation)
- Short time horizon (resolved same day)

**Is the SOTU performance genuine edge or one-day anomaly?**
- If we beat the market on SOTU: is it because we understood Trump's patterns better, or because the market was irrationally priced on entertainment markets?
- Implication: Should we actively seek more short-duration cultural/political event markets (S007 territory)?

---

## Task 3: Brier Score Rolling Window

Build a rolling Brier score chart to see if we're improving over time:

```python
# Rolling 10-prediction Brier
# For each prediction i from 10 to N:
#   window_brier_mine = mean of (outcome_j - my_estimate_j)^2 for j in [i-10, i]
#   window_brier_market = mean of (outcome_j - market_price_j)^2 for j in [i-10, i]
```

This will show:
- Are we getting better over time? (rolling Brier declining)
- Are we tracking the market or diverging?
- Any specific periods where we outperformed/underperformed?

---

## Task 4: Derive Calibration Rules

From the analysis, derive 2-3 actionable calibration rules:

**Format**:
```markdown
## Calibration Rule C01 (derived Feb 28, 2026)
**Pattern**: [observed pattern in data]
**Rule**: [concrete adjustment to make]
**Strength**: [weak/moderate/strong — based on N]
**Review date**: [when to re-evaluate after more data]

Example:
Pattern: YES bets with 60-70% estimates resolved at 50% actual rate
Rule: When estimating YES probability in 60-70% range, reduce estimate by 8% (multiply by 0.87)
Strength: weak (N=5)
Review: After 20 YES predictions in this range
```

Write rules only for patterns with N >= 5. Don't over-fit on tiny samples.

---

## Task 5: Update the Calibration Dashboard

Final calibration.md update:

```markdown
## Calibration Dashboard — Updated Feb 28, 2026

### Summary Stats
| Metric | Value | Trend |
|--------|-------|-------|
| Total predictions logged | N | ↑ |
| Resolved predictions | N_r | |
| Brier score (mine) | X.XXX | |
| Brier score (market) | X.XXX | |
| Beat-market rate | XX% | |
| YES calibration | XX% actual vs XX% estimated | |
| NO calibration | XX% actual vs XX% estimated | |
| Best domain | | |
| Worst domain | | |

### Calibration Rules Active
- C01: [rule]
- C02: [rule]

### Next Calibration Review
- Date: March 31 (B04 is scheduled after 15+ resolutions)
- Target: 50 total predictions resolved
- At current rate (without S011): 1,900 days
- At rate with S011 fast-resolution: ~60 days
```

---

## Output

1. Fully updated `calibration/resolutions.jsonl` — all Feb 28 resolutions
2. Updated `calibration/calibration.md` — new Brier stats, domain breakdown, rolling window
3. New section in `calibration/lessons.md` — calibration rules derived from Feb 28 analysis
4. Terminal output: summary Brier score, beat-market rate, YES vs NO breakdown, 2-3 derived rules

**Done when**: The calibration dashboard has a complete post-Feb 28 update, at least 1 calibration rule is derived from the data, and the YES bias is either explained (sampling error) or formalized into an adjustment rule.

**Time to run**: 30-60 minutes after I07 completes the resolution logging.
