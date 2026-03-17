You are a strategy performance analyst conducting the first formal review of all active strategies. The question is not just P&L — it's whether each strategy is structurally sound and whether underperformance is a signal to improve, pause, or abandon.

## Read First

1. ~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md
2. ~/Desktop/prediction-markets/strategies/playbooks/ — all strategy playbooks
3. ~/Desktop/prediction-markets/strategies/backtests/ — backtest results
4. ~/Desktop/prediction-markets/calibration/lessons.md
5. ~/Desktop/prediction-markets/trades/live-trades.md — live account

## Context

Paper account deployed since Feb 23 (2 days). One closed position (S003, -17.5%). Seven open with most in early state. This review is a PROCESS audit, not a P&L audit — too early for P&L to be meaningful except as a directional signal.

---

## Task 1: The Strategy Scorecard

For each strategy, evaluate on four dimensions:
- **Thesis Quality** (1-5): Is the underlying edge hypothesis sound? Is there evidence it works?
- **Execution Quality** (1-5): Did we follow the playbook? Were entry/exit rules respected?
- **Sample Size** (1-5): How much evidence do we have? (1=zero trades, 5=many resolved)
- **System Fit** (1-5): Does this strategy fit our current capital level, domain expertise, and infrastructure?

### S003 — Catalyst (CME-Polymarket Divergence)

**Trade**: T004 — Fed 25bp cut March, YES at 2.85%, closed at 2.4%, -$35.09 (-17.5%)

**Thesis**: When CME FedWatch and Polymarket diverge significantly on Fed rate decisions, Polymarket is inefficiently priced. The divergence should close toward the CME price.

**Post-mortem**:
- Entry: Feb 23, CME at 5.9% vs Polymarket 2.85% — 3.05pp divergence
- Exit: Feb 25, divergence closed but in WRONG DIRECTION — CME fell to meet Polymarket, not vice versa
- What actually happened: Hot PCE print + hawkish FOMC minutes drove CME lower. Polymarket was RIGHT. CME was more wrong than Polymarket on this tail probability.
- Lesson: The assumption "CME is correct, Polymarket is wrong" is not always valid. On low-probability tails, Polymarket retail may be MORE efficient than CME (which is driven by institutional rate hedgers, not pure probability assessors)

**Critical evaluation**:
- Is the thesis still valid in general? When CME diverges from Poly, which direction is "right"?
- Under what conditions is CME divergence reliable vs. misleading?
- Should S003 be paused until we understand the directionality better?

**Execution error**: Entered 23 days before FOMC (too early). S003 playbook says 3-7 days. This was a clear execution error that amplified the thesis risk by creating more time for thesis-killing data.

**Verdict**: Thesis conditionally valid, execution was wrong. Refine: (a) only enter 3-7 days before FOMC, (b) verify the direction of expected convergence more carefully before entry.

---

### S004 — Contrarian Overreaction

**Trade**: T003 — Iran Mar 31 NO, entry 57.5%, current 60.5%, -$21.18 (-7.1%)

**Thesis**: When a market spikes ≥10% due to emotional overreaction, it partially reverts. The Iran market spiked on Trump's ultimatum deadline. We bet on reversion.

**Status**: Open. 34 days to resolution. Thesis partially validated in near-term (Feb 28 market fell from 18% to 10.5%) but invalidated in medium-term (Mar 31 ROSE from 57.5% to 60.5%).

**Critical evaluation**:
- The near-term and medium-term markets DIVERGED. This is not overreaction — it's market repricing of the timeline. The Feb 28 probability correctly fell (talks happening). The Mar 31 probability rose (medium-term tension persists).
- S004 applies best to markets that FULLY REVERT within the same timeframe. "By March 31" is not a mean-reverting situation if the underlying risk is structural.
- S004 in GEO may be the wrong domain: geopolitical risk doesn't fully revert. Wars don't follow mean reversion.

**Key question**: Is S004 appropriate for GEO, or should it be restricted to domains where price moves ARE more likely noise (POL short-term, ECO post-data-release)?

**Execution**: Met entry criteria (spike ≥10%, volume OK). Exit rules are clear. No execution errors — just thesis application in wrong domain context.

**Verdict**: Strategy valid; domain application questionable for GEO. Should test S004 primarily in POL and ECO where reversion dynamics are stronger. Add domain restriction to playbook.

---

### S006 — Time Decay

**Trades**: 
- T001 — Iran Jun 30 NO, entry 66.5%, current 69.5%, -$26.87 (-9.0%)
- T008 — BTC $150K NO, entry 91.5%, current 91.5%, flat

**Thesis**: Near-impossible events are overpriced due to availability bias. As time passes without the event, price decays toward 0. NO positions profit from this decay.

**Critical evaluation for T001**:
- Entry: Iran Jun 30 NO when YES = 66.5%. This is NOT "near-impossible." 66.5% YES means the market thinks a strike is MORE LIKELY than not by June 30.
- The CORRECT S006 application is for events at <20% probability. Buying NO on a 33.5% NO position is S004 (contrarian) territory, not S006 (time decay).
- T001 was mislabeled: it's a directional contrarian bet disguised as time decay.

**Critical evaluation for T008**:
- BTC $150K NO at 91.5% YES. This IS correct S006 territory — needs +130% move in 10 months. Near-impossible, high NO probability, time decay works in our favour.
- The CRY domain is the right home for S006 (price target markets).
- T008 is the correct S006 trade. T001 was misclassified.

**Domain insight**: S006 works best when:
- Event probability is <20-25% (genuine tail event)
- There is NO structural reason for the tail to grow over time
- CRY price target markets (BTC $200K, $300K, etc.) fit perfectly
- GEO "will X happen by Y date" markets at 60-70% YES do NOT fit

**Verdict**: Strategy valid. T008 is properly classified S006. T001 is mislabelled — it's actually S004. Correct the classification and add a probability gate: S006 requires YES probability < 25% at entry. Above 25%, it's S004.

---

### S007 — Structural Arbitrage (Overround)

**Trade**: T002 — Trump 2028 GOP nom NO, entry 2.8%, current 2.5%, +$1.54 (+0.3%)

**Thesis**: Exploiting overround in multi-outcome POL markets. T002 specifically exploits a legally impossible candidate being priced at 2.8%.

**Status**: Working as expected. Very long-dated. Small positive.

**Critical evaluation**:
- T002 is properly classified S007 (arb on impossible candidate's residual price)
- But: the returns are tiny (0.3%) because the price was already low
- The real overround arb opportunity is in candidates with 20-50% combined overround — but those require NegRisk (P01 research)
- T002 is more S001 (hold to resolution) than true S007 arb

**The broader S007 opportunity**:
- Scanner ran on Feb 23: found Republican 2028 nominee at 49.7% overround (mostly stale RFK Jr. price)
- No actual arb trades were placed beyond T002
- Why? Because the only clean overround was from stale pricing artifacts, not exploitable imbalances
- The REAL S007 opportunity requires NegRisk (P01) — multi-outcome arbitrage via convert()

**Verdict**: T002 is working but is mis-strategy-labeled (it's S001 not S007). Real S007 needs NegRisk infrastructure (P01 playbook). Reclassify T002 as S001.

---

### S001 — Hold to Resolution

**Trade**: T006 — Vance 2028 YES, entry 41.6%, current 41.6%, flat

**Thesis**: JD Vance at 41.6% is significantly below VP base rate of ~80% for nomination. Long-duration value hold.

**Status**: Just opened (Feb 25). No movement yet. Longest-dated position (resolution ~2028).

**Critical evaluation**:
- The thesis is sound (VP base rate research, incumbent advantage)
- The risk is that Vance underperforms politically in 2026-2028, creating headwinds
- This is a 2-year hold. In prediction market terms, that's essentially an illiquid asset — Polymarket may not even be running in 2028 in its current form
- The capital opportunity cost is significant: $125 locked for 2 years that could cycle through 50+ fast-resolution trades

**Verdict**: Thesis sound but capital efficiency is very poor. S001 long-duration holds may not be the best use of prediction market capital. Consider reducing size or limiting S001 to < 1-year duration markets.

---

### S008 — Information Edge

**Trades**:
- T005 — US/Israel Iran Mar 31 NO, entry 59%, current 62%, -$10.98 (-7.3%)
- T007 — Maduro Venezuela NO, entry 87.3%, current 87.3%, flat

**Thesis**: We have superior information (Maduro in federal custody, operational reality of strikes) that the market hasn't fully priced.

**Status**: T005 is correlated with T003 (overlapping Iran thesis). T007 is flat.

**Critical evaluation for T005**:
- T005 is effectively the same position as T003 (both Iran Mar 31 NO)
- The information edge claimed is the same for both
- This was a concentration error — T005 should not have been opened alongside T003 on the same thesis

**Critical evaluation for T007**:
- Maduro in Brooklyn MDC is genuine information edge
- BUT: resolution criteria ambiguity is significant. Does "leader" mean actual power, or official recognition?
- S009 (oracle trader) framework retroactively flags T007 as having high ambiguity risk (Score 4/5)
- Should have been sized at 50% of standard given oracle ambiguity

**Verdict**: S008 is the highest-quality strategy in the system — genuine information edges exist. Execution error on T005 (correlated with existing T003). T007 is correct but needs S009 ambiguity discount applied. Fix: before opening any S008 trade, run S009 ambiguity check and reduce size by 25-50% if Ambiguity Score ≥ 3.

---

### S011 — Bond Rotation (Live Account Only)

**Live Trade**: T008 (live) — US revenue < $100b YES at 96.5%, $4.98, resolves Feb 28

**Thesis**: Near-certain outcomes at > 95% probability with short resolution windows (< 7 days) are yield instruments. Buy and hold to collect the spread.

**Status**: Not yet formally in paper account. Live account executed this by instinct.

**Performance to date**: Not yet resolved. If YES (96.5% probability): +$0.18 (+3.6% in 5 days = ~262% annualised).

**Critical evaluation**:
- This strategy is UNDERREPRESENTED in paper
- The live account found it by instinct on the first real-money trade
- 262% annualised is exceptional even after accounting for capital-at-risk
- The risk (oracle manipulation, resolution surprise) is manageable at small sizes

**Verdict**: S011 is actively working in live before the playbook was written. Formalise immediately (P02 prompt). Add S011 trades to paper account as a systematic screen, not just opportunistic.

---

## Task 2: Formal Scorecard

Complete this table with ratings (1-5) and verdicts:

| Strategy | Thesis Quality | Execution Quality | Evidence | System Fit | Overall | Verdict |
|----------|---------------|-------------------|----------|------------|---------|---------|
| S001 (Hold) | | | | | | |
| S003 (Catalyst) | | | | | | |
| S004 (Contrarian) | | | | | | |
| S006 (Time Decay) | | | | | | |
| S007 (Arb) | | | | | | |
| S008 (Info Edge) | | | | | | |
| S011 (Bond Rotation) | | | | | | |

**Verdict options**: CONTINUE / REFINE / PAUSE / RETIRE

---

## Task 3: Priority Reordering

Based on the scorecard, reorder strategy deployment priority for the next 30 days:

**Tier A — Deploy capital first**:
These strategies have the strongest evidence, system fit, and current opportunity:
- (List 2-3 strategies)

**Tier B — Deploy capital selectively**:
Valid but with conditions:
- (List 2-3 strategies with the specific conditions)

**Tier C — Pause or restrict**:
Need refinement before more capital:
- (List any strategies that need work)

---

## Task 4: Classification Corrections

Based on the analysis, several trades were mis-strategy-labeled. Correct them:

1. T001 (paper): Relabel from S006 → S004 (it's contrarian, not time decay — YES probability too high for S006)
2. T002 (paper): Relabel from S007 → S001 (it's a long hold, not an arb)
3. Live T008: Add as an S011 paper trade equivalent (currently only in live, not paper)

Update positions.json and pnl-summary.md with corrected strategy labels.

---

## Output

1. `~/Desktop/prediction-markets/strategies/strategy-scorecard-2026-02-25.md` — full scorecard
2. Updated strategy playbooks for any strategies requiring rule changes (S003 timing correction, S004 domain restriction, S006 probability gate)
3. Corrected positions.json and pnl-summary.md labels
4. Tier A/B/C priority list for next 30 days added to strategies/README.md
5. 3+ new lessons to calibration/lessons.md
