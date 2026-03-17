You are a portfolio risk manager auditing the prediction markets system for hidden concentration risk and designing position sizing rules that prevent it recurring.

## The Problem Discovered

The paper account shows 7 open positions but contains a structural deception:

```
T001 (Iran Jun 30 NO)   — $300 deployed — GEO / Iran / NO direction
T003 (Iran Mar 31 NO)   — $300 deployed — GEO / Iran / NO direction  
T005 (Iran Mar 31 NO)   — $150 deployed — GEO / Iran / NO direction
```

This is not three positions. It is ONE directional thesis — "Iran will not strike" — expressed three times with different expirations. Their daily P&L correlation is ~0.95+. When Iran YES rises, all three lose simultaneously. The system treated them as independent for sizing purposes and deployed $750 (44.5% of all deployed capital) into a single correlated bet.

**Total Iran unrealized loss: -$59.02 (63.8% of total portfolio loss from 9% of bankroll)**

## Read First

1. ~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md
2. ~/Desktop/prediction-markets/strategies/paper-trades/positions.json
3. ~/Desktop/prediction-markets/strategies/playbooks/ — all strategy playbooks (check existing sizing rules)
4. ~/Desktop/prediction-markets/calibration/lessons.md — existing lessons

---

## Task 1: The True Correlation Matrix

### 1a. Calculate Empirical Correlations

For each pair of open positions, estimate the correlation between their price movements:

Use available data:
- Same underlying event (Iran) → correlation ~0.90-0.95
- Same domain, different event → correlation ~0.30-0.50
- Different domains → correlation ~0.05-0.20
- Opposite direction in same market → correlation ~-0.85 to -0.95

Build the correlation matrix:

| | T001 | T002 | T003 | T005 | T006 | T007 | T008 |
|-|------|------|------|------|------|------|------|
| T001 (GEO Iran NO) | 1.00 | ? | ? | ? | ? | ? | ? |
| T002 (POL GOP NO) | | 1.00 | | | | | |
| T003 (GEO Iran NO) | | | 1.00 | | | | |
| T005 (GEO Iran NO) | | | | 1.00 | | | |
| T006 (POL Vance YES) | | | | | 1.00 | | |
| T007 (GEO Venezuela NO) | | | | | | 1.00 | |
| T008 (CRY BTC NO) | | | | | | | 1.00 |

Note the T002/T006 relationship: both are POL 2028, but T002 (Trump NO) and T006 (Vance YES) are actually POSITIVELY correlated — if Trump runs, Vance doesn't get the nom. They hedge each other. This is the one natural hedge in the portfolio.

### 1b. The "Effective N" Calculation

Given the correlation matrix, calculate the effective number of independent positions:

```
Effective N = (sum of all correlations)^(-1) ... approximately

Or use: If cluster A correlates at 0.90, cluster A counts as 1 position regardless of how many trades express it.
```

**Expected finding**: The 7 paper positions have an effective N of approximately 4-5 independent bets, not 7.

### 1c. True Risk Exposure by Cluster

Group correlated positions into "risk clusters":

| Cluster | Positions | True Deployed | % Bankroll | Max Loss | Correlation |
|---------|-----------|---------------|------------|----------|-------------|
| Iran NO | T001, T003, T005 | $750 | 7.5% | -$750 | ~0.92 |
| POL 2028 | T002 (hedge), T006 | $625 | 6.25% | -$500 (hedged) | ~-0.30 |
| GEO other | T007 | $50 | 0.5% | -$50 | ~0.0 |
| CRY | T008 | $75 | 0.75% | -$75 | ~0.0 |

**The shocking number**: 7.5% of the entire bankroll ($750) is in a single correlated directional bet.

Phase 1 rules said max 5% per position (implied). The Iran cluster is 150% of that limit just on correlation grounds alone.

---

## Task 2: The Correlation Rules (Retroactive + Forward)

### 2a. Position Sizing Under Correlation

Design a new rule set that prevents this recurrence. Research Kelly Criterion extensions for correlated bets if relevant.

**Proposed Rule Set — document and evaluate each:**

**Rule C1 — Single Event Cap**: No more than 3% bankroll exposure to any single underlying event or thesis, regardless of how many markets/tranches express it.
- Current violation: Iran NO = 7.5% vs 3% cap
- Implication: We should have opened one Iran NO position at $300 max, not three at $750

**Rule C2 — Domain Concentration Cap**: No more than 5% bankroll in any single domain after correlation adjustment.
- Current: GEO = $950 deployed = 9.5% (with high internal correlation)
- Correlation-adjusted: ~7.5% effective single-thesis exposure
- Still above 5% cap

**Rule C3 — Mandatory Hedge**: When opening a second position in the same domain, the second must have negative correlation with the first OR reduce the overall delta.
- Application: Before opening T005, should have asked "what's my existing GEO Iran exposure?" and required T005 to hedge (e.g., buy some Iran YES to offset)

**Rule C4 — Portfolio Delta Check**: Before any new entry, calculate the net portfolio delta on the underlying thesis. If adding a new position would push the thesis exposure above X%, require override rationale.

**Evaluate each rule**: Is it enforceable? Does it create false negatives (blocking good trades)?

### 2b. The Kelly Adjustment

Standard Kelly for a single bet: f = (bp - q) / b where b = payoff, p = win probability, q = 1-p.

**For correlated positions**, Kelly shrinks. The adjustment: multiply Kelly fraction by (1 - average correlation with existing positions).

Example: First Iran NO position at Kelly says 15% of bankroll. Second Iran NO position: adjust by (1 - 0.92) = 0.08. Adjusted Kelly = 15% × 0.08 = 1.2% → very small second position.

Apply this framework retroactively to T001, T003, T005 and show what size they SHOULD have been.

---

## Task 3: Current Portfolio Remediation

### 3a. The Immediate Decision

Given the current exposure:
- Iran cluster is $750 deployed, -$59.02 unrealized
- Feb 26 Geneva talks happening today — outcome unknown
- T003 has exit deadline March 5 (conditional on talks outcome)

**Should we reduce the Iran cluster now?**

Evaluate three options:

**Option A — Hold all**: Wait for talks outcome, exits per existing rules
- Rationale: Feb 26 talks are the thesis-defining catalyst. Exit AFTER seeing the outcome.
- Risk: If talks collapse, all three positions lose more simultaneously

**Option B — Reduce T001 (longest duration) now**:
- T001 (Jun 30) is the longest-dated. If talks collapse → this is the last to resolve.
- Selling T001 now at -$26.87 loss reduces single-event exposure from $750 → $450
- Frees $273 for non-correlated opportunities
- Rationale: Sacrificing the weakest temporal thesis to reduce concentration risk

**Option C — Exit T003 and T005 (near-term), hold T001 (long-term)**:
- Near-term positions (Mar 31) are at highest risk if talks collapse
- Long-term (Jun 30) has more time for thesis to play out
- Reduces the 2-position concentration on March 31

**Recommendation**: Choose one option and provide rationale using the concentration rules from Task 2.

### 3b. Forward Portfolio Construction Rules

Write a Position Planning Checklist that must be completed before any new position:

```markdown
## Pre-Position Concentration Check

1. What is the underlying event/thesis this bet depends on? ___
2. What existing positions depend on the SAME underlying event? ___
3. What is my current deployed exposure to this thesis? $___ / ___% bankroll
4. After this trade, what would my thesis exposure be? $___ / ___% bankroll
5. Does this exceed Rule C1 (3% single-event cap)? YES / NO
   If YES: Reduce size, or override with documented rationale
6. What is the correlation of this position with my top 3 existing positions? ___
7. Kelly-adjusted position size: $___
8. Final position size (min of Kelly-adjusted and cap-constrained): $___
```

Add this checklist to: `~/Desktop/prediction-markets/strategies/paper-trades/position-plan-template.md`

---

## Task 4: Risk Dashboard Update

Update `~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md` to include a "Correlation Risk" section:

```markdown
## Correlation Risk

| Cluster | Positions | Deployed | % BK | Corr | Cap (C1) | Over? |
|---------|-----------|---------|------|------|----------|-------|
| Iran NO | T001+T003+T005 | $750 | 7.5% | ~0.92 | 3% | ⚠️ YES — 2.5× over cap |
| POL 2028 | T002+T006 | $625 | 6.25% | ~-0.30 | 5%* | ✅ (hedge reduces effective) |
| GEO other | T007 | $50 | 0.5% | — | 3% | ✅ |
| CRY | T008 | $75 | 0.75% | — | 3% | ✅ |

*Hedged cluster: T002 (short GOP nom) and T006 (long Vance) reduce each other's risk

⚠️ ACTION REQUIRED: Iran cluster exceeds single-event cap by 2.5×
```

---

## Output

1. **Correlation matrix** (Task 1a): Add to `~/Desktop/prediction-markets/strategies/paper-trades/risk-report-2026-02-25.md`
2. **True risk exposure by cluster** (Task 1c): Same file
3. **Correlation rules C1-C4** (Task 2a): Add to `~/Desktop/prediction-markets/research/position-sizing-rules.md`
4. **Kelly adjustment formula** (Task 2b): Same sizing rules file
5. **Remediation recommendation** (Task 3a): `exit-decision-2026-02-26.md` — append to existing or create new section
6. **Pre-Position Concentration Check template** (Task 3b): `strategies/paper-trades/position-plan-template.md`
7. **Updated pnl-summary.md** with Correlation Risk section
8. **Lessons**: Add to `calibration/lessons.md` — minimum 3 new lessons from this analysis (e.g., L16: "Correlation-adjusted exposure is the true risk measure, not position count")
