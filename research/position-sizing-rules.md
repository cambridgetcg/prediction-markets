# Position Sizing Rules Under Correlation

*Created: 2026-02-26*
*Triggered by: R01 correlation risk audit*
*Evidence base: risk-report-2026-02-25.md, S006/S004/S008 playbook sizing rules*

---

## The Problem

The existing strategy playbooks size positions independently. Each strategy has its own sizing rules (S006: 3-5%, S004: 1-3%, S008: 3-8%, S001: 3-8%), but **no rule checks what other strategies have already deployed on the same underlying thesis**.

Result: Three strategies (S006, S004, S008) each independently took a 3% position on "Iran will not strike" and deployed 9.0% of bankroll into a single correlated bet (ρ ≈ 0.92).

The system needs **cross-strategy concentration rules** that sit above individual playbook sizing.

---

## Rule C1 — Single Event Cap

> **No more than 3% of bankroll deployed on any single underlying event or thesis, regardless of how many strategies, markets, or tranches express it.**

### Evaluation

| Criterion | Assessment |
|-----------|------------|
| Enforceable? | **Yes.** Requires identifying the underlying thesis before entry (part of the position planning checklist). |
| False negatives? | **Low.** Could block legitimate conviction-sizing on a strong thesis. Mitigated by the override mechanism (documented rationale required). |
| Current violation | Iran NO cluster: $900 = 9.0% → **3× over cap** |
| If applied retroactively | T001 ($300) fills the entire event cap. T003 and T005 would not have been opened. |

### Implementation

"Underlying event" = the binary outcome that all related markets depend on. Examples:
- "US strikes Iran" is ONE event whether expressed as "by Mar 31," "by Jun 30," or "US/Israel strikes"
- "Trump wins 2028 GOP nom" is ONE event whether expressed as Trump YES, Vance YES, DeSantis YES
- "Fed cuts in March" is ONE event whether expressed as 25bp cut, any cut, or hold rate

**Test**: If outcome X would cause positions A and B to move in the same direction by more than 50% of their range, they share an underlying event.

### Override Mechanism

If a trader wants to exceed 3% on a single event:
1. Must document the rationale in the trade entry
2. Must show that the additional exposure is from a *differentiated* thesis (e.g., different time horizon with meaningfully different probability)
3. Hard cap at **5%** even with override — no exceptions
4. Must reduce other correlated exposure to compensate

**Verdict: ADOPT.**

---

## Rule C2 — Domain Concentration Cap

> **No more than 10% of bankroll in any single domain after correlation adjustment.**

### Evaluation

| Criterion | Assessment |
|-----------|------------|
| Enforceable? | **Yes.** Sum all positions tagged with the domain. |
| False negatives? | **Moderate at 5%.** A 5% domain cap with 3% event caps means max 1-2 events per domain. Too restrictive for domains with genuinely independent events. |
| Why 10% not 5%? | A domain like GEO may have 3 truly independent events (Iran, Venezuela, Taiwan). At 3% each = 9%, a 5% domain cap blocks legitimate diversification within a domain. 10% allows ~3 independent events per domain. |
| Current violation | GEO: $950 = 9.5% (borderline at 10% cap). But correlation-adjusted effective exposure is dominated by the Iran cluster at 9.0% — violating C1 anyway. |
| Correlation adjustment | If events within a domain have ρ < 0.20, count each at face value. If ρ > 0.50, count as single event for C1 purposes. |

### Alternative Considered: 5% Cap

The prompt proposed 5%. This would mean:
- 3% event cap + 5% domain cap → max 1 event per domain with room for a small second
- Too restrictive for GEO (Iran + Venezuela + Taiwan are genuinely independent)
- Would require a waiver for almost any two-position domain exposure

**Verdict: ADOPT at 10%.** The real protection comes from C1 (event cap), not C2. C2 is a backstop against domain-level macro risk (e.g., "US becomes isolationist" → all GEO trades lose).

---

## Rule C3 — Correlation Check on Additional Positions

> **Before opening a second position on the same underlying event, the new position must either (a) have ρ < 0.30 with existing positions, or (b) explicitly hedge (negative delta) the existing exposure.**

### Evaluation

| Criterion | Assessment |
|-----------|------------|
| Enforceable? | **Partially.** Requires estimating correlation, which is judgment-based. |
| False negatives? | **Low.** The rule allows same-event positions IF they provide diversification (e.g., different time horizons with ρ < 0.30). In practice, same-event prediction market positions almost never have ρ < 0.30. |
| Current violation | T005 opened with ρ ≈ 0.95 to T003 — would have been blocked. T003 opened with ρ ≈ 0.92 to T001 — would have been blocked. |
| Practical effect | Forces the trader to ask: "Am I really adding information, or just adding exposure?" If the answer is "same thesis, same direction, same date" → blocked. |

### When Same-Event Positions Are Acceptable

1. **Opposite direction** (hedging): Buy some Iran YES to offset Iran NO exposure
2. **Meaningfully different time horizon**: "By Mar 31" vs "By Dec 31" might qualify IF the 9-month gap creates ρ < 0.30 (unlikely for Iran — probably still ρ > 0.60)
3. **Conditional on different catalysts**: One position on "talks succeed" and another on "military posture" — but in prediction markets, these resolve to the same binary outcome

**Verdict: ADOPT.** Reformulated from the original "mandatory hedge" to a "correlation check" — less prescriptive, same protective effect.

---

## Rule C4 — Pre-Entry Portfolio Delta Check

> **Before any new position, calculate the net portfolio delta on the underlying thesis. If the new position would push thesis exposure above the C1 cap, it requires documented override rationale.**

### Evaluation

| Criterion | Assessment |
|-----------|------------|
| Enforceable? | **Yes.** This is a process rule, implemented via the Position Planning Checklist (position-plan-template.md). |
| False negatives? | **None.** It's a check, not a block. You can still proceed with override. |
| Current violation | No delta check was performed before T003 or T005. Both would have revealed the Iran cluster was already at 3% (T001) and 6% (T001+T003). |

### Delta Calculation Method

```
Thesis delta = Σ (position_size × direction_sign)

Where direction_sign:
  +1 if position profits when thesis is TRUE (e.g., Iran strike NO profits when "no strike" is true)
  -1 if position profits when thesis is FALSE

Example — Iran thesis "no military strike":
  T001: $300 × (+1) = +$300
  T003: $300 × (+1) = +$300
  T005: $300 × (+1) = +$300
  Net delta: +$900 on "no strike"
```

**Verdict: ADOPT.** This is the enforcement mechanism for C1-C3.

---

## Rule Summary

| Rule | Cap | Scope | Override? |
|------|-----|-------|-----------|
| **C1** | 3% bankroll per event | Cross-strategy, cross-market | Yes, documented + hard cap 5% |
| **C2** | 10% bankroll per domain | Cross-strategy | No override |
| **C3** | ρ < 0.30 for same-event additions | Per new position | Hedge positions exempt |
| **C4** | Delta check before entry | Process rule | Always required |

---

## Kelly Adjustment for Correlated Positions

### Standard Kelly (Single Bet)

```
f* = (bp - q) / b

Where:
  b = net odds (payout per dollar risked) = (1 / entry_price) - 1
  p = estimated probability of winning
  q = 1 - p
```

### Correlated Kelly Adjustment

When a new position correlates with existing positions on the same thesis:

```
f*_adj = f* × (1 - ρ_avg)

Where:
  ρ_avg = average correlation of new position with all existing same-thesis positions
```

**Intuition**: If you already have a position that's 0.92 correlated with the new one, the new position provides only 8% incremental information. Your sizing should reflect this — the new position should be 8% of what a standalone Kelly would suggest.

### Quarter Kelly in Practice

We use quarter-Kelly as the practical cap (per S006 playbook). So:

```
Practical size = min(quarter_Kelly_adjusted, C1_cap)

Where:
  quarter_Kelly_adjusted = 0.25 × f*_adj
  C1_cap = 3% of bankroll (or 5% with documented override)
```

### Retroactive Application to Iran Cluster

**T001 (first position — S006 Time Decay)**

| Parameter | Value |
|-----------|-------|
| Entry NO price | $0.335 (YES at 33.5%) |
| Net odds (b) | (1/0.335) - 1 = 1.985 |
| Estimated NO probability (p) | 73.5% (S006 base rate for "by date" NO) |
| q | 26.5% |
| Full Kelly (f*) | (1.985 × 0.735 - 0.265) / 1.985 = **60.2%** |
| Quarter Kelly | 15.0% |
| Correlation adjustment | None (first position) → 1.0 |
| Adjusted quarter Kelly | **15.0%** |
| Practical size | min(15.0%, 3.0% C1 cap) = **3.0%** |
| Actual size | $300 = 3.0% |
| **Assessment** | **Correctly sized** |

**T003 (second position — S004 Contrarian)**

| Parameter | Value |
|-----------|-------|
| Entry NO price | $0.425 (YES at 57.5%) |
| Net odds (b) | (1/0.425) - 1 = 1.353 |
| Estimated NO probability (p) | ~65% (contrarian thesis: overreaction, reversion expected) |
| Full Kelly (f*) | (1.353 × 0.65 - 0.35) / 1.353 = **39.1%** |
| Quarter Kelly | 9.8% |
| ρ with T001 | 0.92 |
| Correlation adjustment | 1 - 0.92 = **0.08** |
| Adjusted quarter Kelly | 9.8% × 0.08 = **0.78%** |
| Practical size (Kelly) | **$78** |
| Practical size (C1 cap) | $300 - $300 (T001) = **$0** (cap already filled) |
| Actual size | $300 = 3.0% |
| **Assessment** | **3.8× oversized by Kelly; blocked by C1 cap** |

**T005 (third position — S008 Info Edge)**

| Parameter | Value |
|-----------|-------|
| Entry NO price | $0.41 (YES at 59.0%) |
| Net odds (b) | (1/0.41) - 1 = 1.439 |
| Estimated NO probability (p) | ~65% |
| Full Kelly (f*) | (1.439 × 0.65 - 0.35) / 1.439 = **40.7%** |
| Quarter Kelly | 10.2% |
| ρ with existing cluster | avg(0.88, 0.95) = 0.915 |
| Correlation adjustment | 1 - 0.915 = **0.085** |
| Adjusted quarter Kelly | 10.2% × 0.085 = **0.87%** |
| Practical size (Kelly) | **$87** |
| Practical size (C1 cap) | $300 - $600 (T001+T003) = **$0** (cap exceeded) |
| Actual size | $300 = 3.0% |
| **Assessment** | **3.4× oversized by Kelly; blocked by C1 cap** |

### What Should Have Happened

| Position | Actual Size | Kelly-Adjusted | C1-Capped | Correct Size |
|----------|-------------|----------------|-----------|--------------|
| T001 | $300 (3.0%) | $300 (15.0%→3%) | $300 (fills cap) | **$300** |
| T003 | $300 (3.0%) | $78 (0.78%) | $0 (cap full) | **$0** |
| T005 | $300 (3.0%) | $87 (0.87%) | $0 (cap full) | **$0** |
| **Total Iran** | **$900 (9.0%)** | **$465 (4.65%)** | **$300 (3.0%)** | **$300** |

The C1 cap is more restrictive than the Kelly adjustment. Under C1 alone, the Iran cluster should be $300, not $900. The extra $600 was pure uncompensated concentration risk.

---

## Integration with Existing Playbook Sizing

These rules sit ABOVE individual strategy sizing:

```
Position size = min(
  strategy_specific_size,     # S006: 3-5%, S004: 1-3%, etc.
  kelly_adjusted_size,        # Full Kelly × 0.25 × (1 - ρ_avg)
  C1_remaining_cap,           # 3% - existing_thesis_exposure
  C2_remaining_cap            # 10% - existing_domain_exposure
)
```

The smallest of these four numbers wins. In the Iran case, C1 would have been the binding constraint at $300 total ($0 for T003 and T005).

### Strategy-Level Rule Gaps to Fix

| Strategy | Has Sizing Rules? | Has Concentration Rules? | Action Needed |
|----------|------------------|--------------------------|---------------|
| S006 | Yes (3-5%, quarter Kelly) | Yes (2 per conflict, 30% domain, 6-8 total) | Add C1-C4 reference |
| S004 | Yes (1-3% by confidence) | **No** | Add C1-C4 reference |
| S008 | Yes (3-8% by edge type) | **No** | Add C1-C4 reference |
| S001 | Yes (3-8% by divergence) | **No** | Add C1-C4 reference |
| S007 | Yes (3% unhedged) | **No** | Add C1-C4 reference |

Every playbook should include: *"Before sizing, complete the Pre-Position Concentration Check (position-plan-template.md). The concentration rules (C1-C4) override strategy-specific sizing when they produce a smaller number."*

---

*See also: strategies/paper-trades/position-plan-template.md for the enforcement checklist.*
*See also: strategies/paper-trades/risk-report-2026-02-25.md for the correlation matrix and cluster analysis.*
