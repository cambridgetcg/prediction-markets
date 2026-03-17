# Strategy Scorecard — First Formal Review

**Date**: 2026-02-25 (evaluated over Feb 23-26)
**Review type**: Process audit (too early for P&L audit — 2 days of paper trading, 1 closed trade)
**Reviewer**: Strategy performance analyst

---

## Context

Paper trading began Feb 23, 2026. One closed position (T004/S003, -17.5%). Seven open positions, most in early state. Live account has 3 positions ($28.98 deployed). This review evaluates structural soundness, not returns.

**Portfolio snapshot**:
- Starting bankroll: $10,000
- Total P&L: -$92.57 (-0.93%)
- Realized: -$35.09 (1 closed trade)
- Unrealized: -$57.48 (7 open)
- Allocated: $1,685.09 (16.9%)
- Domain exposure: GEO 56.4%, POL 37.1%, CRY 4.5%, ECO 0%

---

## Task 1: Strategy-by-Strategy Analysis

### S001 — Hold to Resolution

**Trade**: T006 — Vance 2028 GOP nom YES at 41.6%, $125 size. Flat.

**Thesis assessment**: VP base rate of ~80% for nomination is well-researched. At 41.6%, the market is pricing significant doubt. The divergence (+16.4pp estimated edge) meets S001's ≥10% threshold. Direction is supported by historical precedent and polling data.

**Execution assessment**: Entry followed the playbook — independent estimate formed, divergence calculated, sizing at ~1.25% of bankroll (conservative relative to the 3-8% rules for 10-30%+ divergence). No exit planned (correct for S001).

**Structural concern**: This is a ~2.5 year hold. Capital opportunity cost is severe — $125 locked while we could cycle through 50+ fast-resolution trades. Polymarket may not exist in current form by 2028. S001 as a control strategy makes sense for 30-90 day markets, but multi-year holds are a different asset class.

**Verdict**: Thesis sound, execution correct, capital efficiency poor for our bankroll size.

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Thesis Quality | 4/5 | VP base rate is solid evidence; price divergence is real |
| Execution Quality | 4/5 | Followed playbook; conservative sizing |
| Evidence | 1/5 | Zero resolved trades; no performance data |
| System Fit | 2/5 | 2-year hold is terrible capital efficiency at $10K bankroll |

---

### S003 — News Catalyst (CME-Poly Divergence)

**Trade**: T004 — Fed 25bp cut March YES at 2.85%. Closed at 2.35%. **-$35.09 (-17.5%).**

**Thesis assessment**: The core thesis — that CME and Polymarket divergences on Fed decisions represent mispricing — is conditionally valid. But the **direction assumption** was wrong. We assumed Polymarket was too pessimistic (CME at 5.9% was "right"). In reality, CME was the wrong one — it dropped to meet Polymarket, not vice versa.

**Critical insight (T13)**: On tail probabilities (<10%), prediction markets can be MORE efficient than traditional derivatives. CME FedWatch is driven by institutional hedgers, not pure probability assessors. Their interest rate derivatives pricing reflects hedging demand, not clean probability estimation.

**Execution error**: Entered 23 days before FOMC. S003 playbook explicitly says 3-7 days. This created 16+ extra days of exposure to thesis-killing data (hot PCE on Feb 20, hawkish minutes). Had we entered Mar 11, the PCE data would have prevented entry entirely.

**What would fix this**:
1. **Timing discipline**: 3-7 days only. No exceptions.
2. **Direction verification**: Before assuming "CME is right, Poly is wrong," evaluate which market has better-calibrated participants for this specific probability range.
3. **Probability regime**: Below 10%, prediction market retail may price tails more accurately than institutional derivatives markets. Above 30%, CME is likely more accurate.

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Thesis Quality | 3/5 | Conditionally valid, but direction assumption was wrong |
| Execution Quality | 2/5 | Clear timing violation (23d vs 3-7d playbook) |
| Evidence | 2/5 | 1 trade, 1 loss. Small sample but informative loss. |
| System Fit | 3/5 | Concept fits (scheduled catalysts exist); needs refinement |

---

### S004 — Contrarian Overreaction

**Trade**: T003 — Iran Mar 31 NO at $0.425 (57.5% YES). Current 60.5% YES. **-$21.18 (-7.1%).**

**Thesis assessment**: Academic evidence is strong (58% negative autocorrelation, 40% reversion within 7 days). The specific application to Iran was partially validated — near-term markets (Feb 28) fell from 18% to 10.5%, confirming the overreaction in the immediate window. But the medium-term market (Mar 31) ROSE, suggesting the market isn't overreacting — it's repricing the timeline.

**Domain problem**: S004 in GEO faces a structural issue. Geopolitical risk doesn't fully mean-revert. Wars, military buildups, and diplomatic crises have persistent risk profiles. The rhetoric-driven spike was real overreaction, but the underlying probability distribution shifted structurally (forces deploying, IAEA deadline approaching). This is not the same as a tweet-driven crypto spike that fully reverts.

**Where S004 DOES work**: POL (debate gaffes, partisan panic — documented to revert in 2-4 weeks), CRY (FUD/hype cycles with documented negative autocorrelation), and single-event markets where the spike is clearly emotional (ECI ≥ 7).

**Execution**: Entry criteria were approximately met (weekly +25% move on rhetoric). The classification checklist was applied. No execution errors per se — the issue is thesis application to a domain where the model is weakest.

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Thesis Quality | 4/5 | Strong academic backing; specific application questionable in GEO |
| Execution Quality | 3/5 | Entry criteria met; applied to difficult domain |
| Evidence | 2/5 | 1 open trade, partial validation, not yet resolved |
| System Fit | 4/5 | Short-duration, clear triggers, good capital efficiency |

---

### S006 — Time Decay

**Trades**:
- T001 — Iran Jun 30 NO at $0.335 (66.5% YES). Current 69.5% YES. **-$26.87 (-9.0%).**
- T008 — BTC $150K NO at $0.915 (8.5% YES). Flat.

**Thesis assessment**: The strongest evidence base of any strategy — 73.5% NO rate across 804 resolved markets. The mathematical framework (constant/decreasing hazard models) is sound and the screener tool is built.

**T001 misclassification**: This is the key finding. T001 was labeled S006 but does NOT meet S006 criteria:
- YES price: 66.5% → This is NOT a tail event. S006's edge comes from overpriced low-probability events.
- The market is saying "more likely than not" that Iran gets struck by June 30.
- S006 works when YES < 25% (genuine tail event where time decay mechanically works in your favor).
- At 66.5% YES, buying NO is a **directional contrarian bet** (S004 territory), not a time decay play.

**T008 is correctly classified S006**:
- YES price: 8.5% → BTC needs +130% move in 10 months. Genuinely near-impossible.
- CRY domain (69.5% historical NO rate) is appropriate.
- Time decay works: each day without reaching $150K makes it incrementally less likely.

**Probability gate needed**: S006 entry should require YES probability < 25%. Above 25%, it's S004 (contrarian) or S001 (directional hold), not S006.

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Thesis Quality | 5/5 | 73.5% NO rate across 804 markets; strongest evidence |
| Execution Quality | 3/5 | T001 misclassified (should be S004); T008 correct |
| Evidence | 3/5 | Backtest excellent; 2 open positions, neither resolved |
| System Fit | 4/5 | Systematic screening works; needs probability gate |

---

### S007 — Cross-Market Arb

**Trade**: T002 — Trump 2028 GOP nom NO at $0.972 (2.8% YES). Current 2.5% YES. **+$1.54 (+0.3%).**

**Thesis assessment**: Overround exists and is documented (49.7% on GOP nom, 10.3% on Fed Chair, -3% presidential underround). The scanner tools work. But T002 is not truly an arb trade — it's buying NO on a legally impossible candidate (Trump can't run for a third term if he served two). This is S001 (hold to resolution on a near-certain outcome), not S007 (structural arbitrage exploiting price relationships).

**Real S007 opportunity**: Requires NegRisk infrastructure (P01 research). Multi-outcome arbitrage via convert() is the true S007 play. Without NegRisk, S007 is limited to:
- Type 1 overround: need ≥3% after 2% winner fee → only works on significantly overpriced baskets
- Type 2 temporal: zero violations found across all series
- Types 3-4: too rare / too competed

**The honest assessment**: S007 as executed is not really S007. T002 is an S001 trade with extra steps. Real arbitrage requires infrastructure we don't have yet.

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Thesis Quality | 4/5 | Overround exists; but actionable pure arb is rare without NegRisk |
| Execution Quality | 3/5 | T002 works but is mislabeled (really S001) |
| Evidence | 2/5 | 1 open trade with tiny return; no resolved arb trades |
| System Fit | 3/5 | Scanners built; real arb needs P01 NegRisk infrastructure |

---

### S008 — Information Edge

**Trades**:
- T005 — US/Israel strikes Iran Mar 31 NO at $0.41 (59% YES). Current 62% YES. **-$10.98 (-7.3%).**
- T007 — Maduro leads Venezuela EOY NO at $0.8725 (12.8% YES). Flat.

**Thesis assessment**: S008 is the highest-quality strategy conceptually — it's the entire reason the domain knowledge system exists. Genuine information edges exist. T007 (Maduro in federal custody, no mechanism to lead from Brooklyn MDC) is a real Type A synthesis edge. T005's information edge is questionable because it overlaps entirely with T003's thesis.

**T005 concentration error**: T005 and T003 are the same trade on the same thesis (Iran Mar 31 NO). The "information edge" claimed for T005 (operational reality of strikes) is the same reasoning used for T003. Opening both created $600 exposure to a single geopolitical outcome — 6% of bankroll on one event when the risk management rules suggest max 2 positions per conflict at 5% each.

**T007 S009 overlay needed**: Maduro's "leader of Venezuela" has resolution criteria ambiguity (does "leader" mean actual power holder, or internationally recognized president?). S009 rates this at RAI 4/5. The position should have been sized at 50% of standard given oracle ambiguity risk.

**What makes S008 the best strategy**: It's the only strategy that generates genuine alpha from knowledge asymmetry. Every other strategy is structural/systematic. S008 is where domain expertise pays off. But it requires discipline: no correlated positions, always run S009 check, and the information edge must be articulable and distinct from other strategies' theses.

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Thesis Quality | 5/5 | Genuine information edges exist; highest-quality strategy |
| Execution Quality | 3/5 | T007 good; T005 correlated with T003 (concentration error) |
| Evidence | 2/5 | 2 open trades, neither resolved |
| System Fit | 5/5 | Core strategy; leverages entire domain knowledge system |

---

### S011 — Bond Rotation (Live Account)

**Trade**: Live T008 — US revenue <$100B YES at $0.965, $4.98 size. Resolves Feb 28.

**Thesis assessment**: The math works at the 95-97c sweet spot. After 2% winner fee, net return is 1-3% per 3-7 day cycle. The favorite-longshot bias provides ~2pp calibration edge at these probability levels. This is not risk-free — one failure wipes 32-48 successes — but RAI filtering (only RAI 1-2 markets) mitigates the worst failure modes.

**Status**: Discovered by instinct on the live account before the playbook was written. The fact that the first real-money trade gravitated to this pattern suggests it's a natural fit for the system — deploying idle capital in high-confidence, short-duration positions.

**Underrepresentation**: S011 has zero paper trades. The live account found it first. This should be formalized immediately — add S011 to daily screening and paper account.

**Expected performance**: If the trade resolves YES (96.5% probability), return is +$0.18 (+3.6% in 5 days). Annualized: ~262%. Even after accounting for the ~3% failure rate, the expected value is positive as long as entry ≤ $0.97.

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Thesis Quality | 4/5 | Favorite-longshot bias documented; math works at 95-97c |
| Execution Quality | 4/5 | Live trade executed well; correct screening criteria met |
| Evidence | 1/5 | No resolved paper trades; 1 live trade pending |
| System Fit | 5/5 | Perfect for idle capital; short duration; systematic |

---

## Task 2: Formal Scorecard

| Strategy | Thesis (1-5) | Execution (1-5) | Evidence (1-5) | System Fit (1-5) | Overall | Verdict |
|----------|:---:|:---:|:---:|:---:|:---:|---------|
| **S001** Hold to Resolution | 4 | 4 | 1 | 2 | 2.75 | **REFINE** |
| **S003** Catalyst | 3 | 2 | 2 | 3 | 2.50 | **REFINE** |
| **S004** Contrarian | 4 | 3 | 2 | 4 | 3.25 | **REFINE** |
| **S006** Time Decay | 5 | 3 | 3 | 4 | 3.75 | **REFINE** |
| **S007** Cross-Market Arb | 4 | 3 | 2 | 3 | 3.00 | **REFINE** |
| **S008** Info Edge | 5 | 3 | 2 | 5 | 3.75 | **CONTINUE** |
| **S011** Bond Rotation | 4 | 4 | 1 | 5 | 3.50 | **CONTINUE** |

**Summary**: No strategy earns PAUSE or RETIRE — all have valid theses. But every strategy except S008 and S011 needs refinement before deploying more capital. The system's biggest issues are classification errors and domain misapplication, not thesis quality.

---

## Task 3: Priority Reordering (Next 30 Days)

### Tier A — Deploy Capital First

These strategies have the strongest thesis-to-system-fit ratio and should receive priority capital allocation:

1. **S011 — Bond Rotation**: Highest system fit (5/5), deploys idle capital, short duration. Formalize the screener, add to daily workflow, begin paper tracking. Target: 2-4 concurrent S011 positions rotating through 3-7 day near-certainties.

2. **S008 — Information Edge**: Highest thesis quality (5/5), leverages the entire domain knowledge system. Focus on domains where we have genuine expertise (GEO operational analysis, POL speech/behavior patterns). Add mandatory S009 overlay before every trade. Fix: no new positions correlated with existing positions.

3. **S006 — Time Decay**: Strongest backtest evidence (73.5% NO rate, 804 markets). After adding the probability gate (YES < 25%), this becomes a clean systematic strategy. Target: CRY price targets and OTHER/POL milestone markets.

### Tier B — Deploy Capital Selectively

Valid strategies with specific conditions that must be met:

1. **S004 — Contrarian Overreaction**: Valid in POL and CRY. **Condition**: Add domain restriction — S004 in GEO only when ECI ≥ 7 AND classification score is clear emotional. For POL and CRY, standard ECI ≥ 5-6 is sufficient. Prefer weekly drift over daily spikes.

2. **S007 — Cross-Market Arb**: Scanner tools are built and working. **Condition**: Only deploy on ≥3% edge after fees. Real S007 (multi-outcome NegRisk arb) awaits P01 infrastructure. Until then, limit to obvious overround opportunities (presidential underround, stale pricing artifacts).

### Tier C — Pause or Restrict

Need refinement before more capital:

1. **S003 — Catalyst**: **Paused for new entries until timing discipline is proven.** The thesis is conditionally valid but we haven't demonstrated we can follow the 3-7 day entry window. Next S003 opportunity: June FOMC, with entry no earlier than Apr 23 (7 days before Apr 30). If that trade follows the playbook, S003 re-enters Tier B.

2. **S001 — Hold to Resolution**: **Restricted to < 1 year duration markets.** T006 (Vance 2028) remains open but no new multi-year holds. S001 is the control strategy and should focus on 30-180 day markets where capital efficiency is reasonable.

---

## Task 4: Classification Corrections

### Correction 1: T001 — S006 → S004

**Reason**: Iran Jun 30 NO at 66.5% YES. S006 requires tail events (YES < 25%). At 66.5%, this is a directional contrarian bet on geopolitical overpricing, not a time decay play on a near-impossible event.

**Impact**: S006 now has 1 trade (T008, correctly classified). S004 now has 2 trades (T001, T003).

### Correction 2: T002 — S007 → S001

**Reason**: Trump 2028 GOP nom NO at 2.8% is a hold-to-resolution bet on a legally impossible outcome (22nd Amendment). It's not exploiting a structural price relationship between markets — it's a calibration bet that 2.8% is too high for an impossible event.

**Impact**: S007 now has 0 active trades. S001 now has 2 trades (T002, T006).

### Correction 3: Live T008 — Add S011 paper equivalent

**Reason**: The live account's US revenue <$100B YES at 96.5% is the first S011 trade. It should be tracked as a paper equivalent for strategy performance comparison.

**Impact**: S011 gains its first tracked position.

---

## New Lessons

### L06: Strategy Misclassification Distorts Performance Tracking

T001 was labeled S006 but was really S004. T002 was labeled S007 but was really S001. When strategies are mislabeled, performance attribution becomes meaningless — you can't evaluate whether a strategy works if the trades assigned to it don't actually follow its rules. **Rule: Before assigning a strategy label, verify that ALL entry criteria from the playbook are met. If even one criterion fails, the trade belongs to a different strategy.**

### L07: Domain Context Determines Strategy Viability

S004 (contrarian) works differently in different domains. In POL and CRY, overreactions revert because the underlying probability hasn't structurally changed. In GEO, "overreaction" to military rhetoric may actually be correct repricing because geopolitical risk is persistent and path-dependent. **Rule: Each strategy should have explicit domain restrictions. Not every strategy works in every domain.**

### L08: Capital Efficiency Is a Strategy Dimension

S001's Vance 2028 trade locks $125 for ~2.5 years. In that time, S011 could cycle through 100+ short-duration trades. At a $10K bankroll, capital efficiency matters more than at $100K+. **Rule: Score every trade on capital efficiency (edge per unit of capital-time) before entering. For S001, restrict to < 1 year duration until bankroll exceeds $50K.**

### L09: Correlation Exposure Hides in Strategy Labels

T003 (S004) and T005 (S008) are the same trade on the same outcome (Iran Mar 31 NO). Combined exposure: $600 (6% of bankroll) to a single geopolitical event. The strategy labels made them look diversified, but the risk is concentrated. **Rule: Before opening any position, check portfolio correlation — if a new trade has >80% outcome correlation with an existing position, either skip it or treat the combined position as one unit for sizing purposes.**

---

## Appendix: Updated Strategy Phase Tracking

| Strategy | Previous Phase | New Phase | Reason |
|----------|---------------|-----------|--------|
| S001 | NIGREDO | **ALBEDO** | T006 entered; control strategy now live |
| S003 | NIGREDO | NIGREDO | 1 trade closed at loss; paused for refinement |
| S004 | ALBEDO | ALBEDO | T003 open; backtest validated; domain refinement needed |
| S006 | ALBEDO | ALBEDO | T008 correctly classified; T001 reclassified out |
| S007 | NIGREDO | NIGREDO | T002 reclassified to S001; no true S007 trades yet |
| S008 | NIGREDO | **ALBEDO** | T005 + T007 entered; real information edges deployed |
| S011 | NIGREDO | **ALBEDO** | Live trade executed; playbook written; paper tracking begins |

---

*Next scorecard review: After Mar 31 Iran market resolution (T001, T003, T005) + first S011 paper trade cycle*
