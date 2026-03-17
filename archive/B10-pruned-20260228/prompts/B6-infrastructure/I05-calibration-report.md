You are a prediction market calibration analyst generating the first formal calibration report.

## Context

Read these files:
1. ~/Desktop/prediction-markets/calibration/predictions.jsonl — all 9 active predictions
2. ~/Desktop/prediction-markets/calibration/resolutions.jsonl — 12 SOTU resolutions + any others
3. ~/Desktop/prediction-markets/calibration/lessons.md — documented lessons
4. ~/Desktop/prediction-markets/calibration/calibration.md — current dashboard (may be sparse)
5. ~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md — trade performance

## Tasks

### 1. Brier Score Dashboard

For every **resolved** prediction in resolutions.jsonl:
- Calculate Brier score: `(outcome - prediction)^2` where outcome=1 (YES) or 0 (NO)
- Calculate the market's Brier score for comparison
- Note whether we beat the market (`brier_mine < brier_market`)

For **active** (unresolved) predictions: note the current market-vs-my-estimate gap.

Report format:

| ID | Domain | Question (short) | My Est | Mkt | Outcome | My Brier | Mkt Brier | Beat? |
|----|--------|-----------------|--------|-----|---------|----------|-----------|-------|

### 2. Aggregate Metrics

Calculate and report:
- **Overall Brier score** (average across all resolved predictions)
- **Market Brier score** (average)
- **Beat-market rate** (% of predictions where my Brier < market Brier)
- **Mean edge captured** (average pp gap between my estimate and market, weighted by edge size)
- **Calibration by domain**: GEO vs POL vs ECO vs CRY
- **Calibration by strategy**: S001 vs S003 vs S004 vs S006 vs S007 vs S008
- **Calibration by confidence**: bucket into high (>80%), medium (50-80%), low (<50%)

### 3. Edge Analysis

From the SOTU batch (12 resolutions) and active predictions:
- Are we systematically biased in any direction? (Over-confident? Under-confident?)
- Is the "SOTU ≠ Rally" edge real and replicable? (Hint: 17/20 beating the market suggests yes)
- Is GEO currently performing above or below expectation?

### 4. Calibration Curves

Produce a text-based calibration curve for the SOTU batch:

For each 10% bucket (0-10%, 10-20%, ..., 90-100%):
- Average predicted probability
- Actual resolution rate
- Number of predictions in bucket

A well-calibrated forecaster should have actual ≈ predicted in each bucket.

### 5. Where Is the Edge Coming From?

Categorize each prediction:
- **Type A** (Synthesis): My estimate better because I assembled more information
- **Type B** (Pattern): My estimate better because of a known bias/pattern (e.g., SOTU ≠ Rally)
- **Type C** (Market gap**: My estimate better because of a cross-market signal (e.g., CME vs Polymarket)
- **Type D** (Miss): Market was more accurate than me

Count and analyse. What type of edge is working best so far?

### 6. Lessons Integration

For each lesson in lessons.md, evaluate:
- Has this lesson been tested yet? (Yes/No + which predictions tested it)
- How many predictions does this lesson affect going forward?
- Rank lessons by expected future impact

### 7. Updated Dashboard

Overwrite ~/Desktop/prediction-markets/calibration/calibration.md with the full report.

Include:
- Summary table
- Calibration curve
- Edge type analysis
- Lessons ranking
- 3-5 priority recommendations for improving calibration over the next 30 days

### 8. Prediction Log Hygiene

Review the 9 active predictions in predictions.jsonl:
- Are the confidence intervals realistic?
- Are the reasoning summaries adequate?
- Flag any predictions where the reasoning is too thin to be useful for calibration learning

Write the report to: ~/Desktop/prediction-markets/calibration/calibration.md
Print a 1-page executive summary to the terminal.
