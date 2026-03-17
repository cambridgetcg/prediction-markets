# Exit Decision Memo — 2026-02-27

*Execution date: Feb 27, 2026*
*Trigger: Geneva talks inconclusive (Feb 26) + R01 correlation remediation*

---

## T003 Decision: **EXIT** — Stop Triggered

### Trigger Chain

1. **Feb 26 Geneva talks**: Inconclusive. No deal. Progress claimed, technical teams to Vienna next week. Iran rejected uranium transfer, insists on enrichment. US demands dismantling of Fordow/Natanz/Isfahan.
2. **Exit-decision-2026-02-26.md** specified: "If talks inconclusive → Tighten stop to 65% YES"
3. **Exit-decision-2026-02-26.md** specified: "If YES hits 65% at any point → EXIT"
4. **Feb 27 price**: YES 66% — stop breached by 1pp
5. **Pre-committed rule. Not a judgment call.**

### Execution

| Field | Value |
|-------|-------|
| Entry | NO $0.425 (YES 57.5%) |
| Exit | NO $0.34 (YES 66%) |
| Shares | 705.88 |
| Exit value | $240.00 |
| Realized P&L | **-$60.00 (-20.0%)** |
| Hold period | 4 days |
| Capital recovered | $240.00 |

### What the Stop Saved

If held to Feb 27 at 68% (original stop): loss would have been ~$75. The tightened 65% stop saved ~$15 on paper. More importantly, if held through the danger window (Mar 1-15 when "forces fully in place"), losses could reach -$120 to -$180.

### Thesis Post-Mortem

| Leg | Entry Thesis | Outcome |
|-----|-------------|---------|
| 1. Feb 26 talks = off-ramp | Talks happened, no collapse — **PARTIAL** (inconclusive, not breakthrough) |
| 2. Near-term panic overblown | Feb 28 dropped 18% → 10.5% — **VALIDATED** |
| 3. Price reverts toward 50% | Mar 31 rose from 57.5% → 66% — **FAILED** |

The contrarian thesis was directionally correct on the near-term (panic subsided) but wrong on the medium-term (market correctly repriced risk into mid-March military readiness window). S004 logic assumes mean reversion. Geopolitical risk escalation is path-dependent, not mean-reverting (L07).

---

## T005 Decision: **EXIT** — R01 Correlation Remediation

### Rationale

1. **R01 audit** (Feb 26) identified T005 as the most redundant position: ρ=0.95 with T003, same date, near-identical thesis
2. Recommended exit at -$10.97
3. **One day delay** → price moved +8.5pp against → exit at -$73.17
4. **Cost of delay: $62.20** — most expensive lesson in portfolio

### Execution

| Field | Value |
|-------|-------|
| Entry | NO $0.41 (YES 59.0%) |
| Exit | NO $0.31 (YES 69%) |
| Shares | 731.71 |
| Exit value | $226.83 |
| Realized P&L | **-$73.17 (-24.4%)** |
| Hold period | 4 days |
| Capital recovered | $226.83 |

### Why T005 Moved Harder Than T003

T005 (US/Israel strikes) moved +8.5pp vs T003 (US strikes) +5.5pp. The "Israel" component adds ~3pp of additional risk that the US-only market doesn't capture. Israel has independent strike capability and less diplomatic constraint. When talks are inconclusive, the wider scope market (US OR Israel) reprices more aggressively.

---

## Combined Impact

### Capital Flow

| Item | Amount |
|------|--------|
| T003 recovered | +$240.00 |
| T005 recovered | +$226.83 |
| **Total cash recovered** | **+$466.83** |
| T003 realized loss | -$60.00 |
| T005 realized loss | -$73.17 |
| **Total realized loss (today)** | **-$133.17** |

### Iran Cluster Before/After

| Metric | Before | After |
|--------|--------|-------|
| Positions | 3 (T001+T003+T005) | **1 (T001 only)** |
| Deployed | $900 (9.0%) | **$300 (3.0%)** |
| C1 compliance | 3× OVER | **AT CAP** |
| Effective N | 2.4 (34% efficiency) | **~4.2 (84% efficiency)** |
| Tail risk (strike occurs) | -$841 (8.4%) | **-$300 (3.0%)** |

### Portfolio After Exits

| Metric | Feb 26 | Feb 27 (post-exit) | Change |
|--------|--------|-------------------|--------|
| Open positions | 7 | **5** | -2 |
| Allocated | $1,685.09 | **$1,218.26** | -$466.83 |
| Available | $8,314.91 | **$8,781.74** | +$466.83 |
| Realized P&L | -$35.09 | **-$168.26** | -$133.17 |
| Unrealized P&L | -$57.48 | **-$47.71** | +$9.77 |
| Total P&L | -$92.57 (-0.93%) | **-$215.97 (-2.16%)** | -$123.40 |

---

## T001 Status: **HOLD** (at C1 cap, monitor closely)

| Field | Value |
|-------|-------|
| Current | NO $0.28 (YES 72%) |
| Unrealized | -$49.25 (-16.4%) |
| Resolution | 2026-06-30 |
| Iran cluster exposure | $300 (3.0%) — exactly at C1 cap |

### Why Hold

1. Longest duration — 4 months of time value remaining
2. Reducing to zero Iran exposure would mean taking -$49.25 with no remaining upside
3. If Vienna technical talks next week produce progress, Jun 30 NO benefits most
4. At exactly C1 cap — no concentration violation
5. The S006 base rate (73.5% NO for "by date" markets) still provides structural edge, though the Iran-specific probability is lower

### Escalation Triggers

- **EXIT if YES exceeds 80%** — would imply strike is near-certain, time value gone
- **EXIT if Trump cancels all diplomatic engagement** — removes the off-ramp thesis
- **REDUCE if any new GEO position is being considered** — cannot add GEO without first reducing T001

---

## Lessons From This Exit

### L14: Execute Risk Reductions Immediately

The R01 audit identified T005 for exit on Feb 26. Execution happened Feb 27. In that 24 hours, T005 moved from -$10.97 to -$73.17 — a $62.20 cost of delay. Risk reductions have negative expected value the longer they're delayed, because the scenarios that trigger the reduction (adverse moves) also increase the loss.

**Rule**: When a risk audit recommends an exit, execute within the same session. Do not wait for "more data" or "the catalyst." The catalyst is the audit finding itself.

### L15: Pre-Committed Stops Are the Only Stops That Work

T003's stop at 65% was set on Feb 26 when thinking was clear and unemotional. On Feb 27 at 66%, the temptation was to "wait for Vienna talks" or "give it one more day." The pre-committed stop removed that option. Stops written in exit memos during calm periods are more reliable than real-time judgment during drawdowns.

### L16: Wider-Scope Markets Move Faster in Crises

T005 (US/Israel) moved +8.5pp while T003 (US-only) moved +5.5pp. Markets with broader trigger conditions (OR-type resolution) reprice more aggressively because any catalyst component can move them. This makes wider-scope markets systematically riskier for NO positions during escalation.

---

*T003 exit executed: 2026-02-27*
*T005 exit executed: 2026-02-27*
*T001 status: HOLDING with escalation triggers*
*Next review: After Vienna technical talks (~Mar 3-7)*
