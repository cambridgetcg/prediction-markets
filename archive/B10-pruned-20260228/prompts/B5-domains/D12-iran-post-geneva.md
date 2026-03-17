# D12 — Iran Post-Geneva: Outcome Assessment + Portfolio Action

You are a geopolitical analyst and portfolio manager. The Feb 26 Geneva talks (US-Iran round 3) have either concluded or are concluding. This is the catalyst that gates ALL three Iran positions (PT001, PT003, PT005). Act immediately.

## Read First (in order)

1. `~/Desktop/prediction-markets/domains/GEO/active.md` — all Iran market prices and thesis details
2. `~/Desktop/prediction-markets/strategies/paper-trades/exit-decision-2026-02-26.md` — the full exit decision memo including R01 directive
3. `~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md` — current portfolio state
4. `~/Desktop/prediction-markets/domains/GEO/research/iran-us-2026.md` — full Iran research

## Context (what you're deciding on entering)

Three open Iran positions, all directional NO (we bet strike DOESN'T happen):

| ID | Market | Dir | Entry | Current Estimate | Unrealized P&L |
|----|--------|-----|-------|-----------------|----------------|
| PT001 | US strikes Iran by Jun 30 | NO | $0.335 | -$26.87 | Largest loss |
| PT003 | US strikes Iran by Mar 31 | NO | $0.425 | -$21.18 | Tightened: stop 65%, exit Mar 5 if inconclusive |
| PT005 | US/Israel strikes Iran by Mar 31 | NO | $0.410 | -$10.97 | **EXIT per R01 directive** |

**R01 directive (already decided)**: Exit PT005 regardless of outcome. It is the most redundant position (ρ=0.95 with PT003, same date, same thesis). The exit is not contingent on the talks outcome.

**The only open question is what to do with PT001 and PT003.**

---

## Task 1: Assess the Geneva Talks Outcome

### 1a. Research What Happened

```
web_search("US Iran Geneva talks February 26 2026 outcome")
web_search("US Iran nuclear negotiations result February 26")
web_search("Steve Witkoff Iran talks February 26")
web_search("Iran nuclear deal framework February 2026")
```

Classify the outcome into one of three scenarios:

**SCENARIO A — FRAMEWORK ANNOUNCED** (talks produced a deal structure or roadmap):
- Indicators: Both sides announce "progress," "framework," "roadmap," "agreement in principle," or next round scheduled
- Iran signals: Enrichment caps discussed/accepted, HEU export agreed
- US signals: Sanctions relief offered, recognition of civilian program

**SCENARIO B — INCONCLUSIVE / ONGOING** (talks ended without breakthrough or collapse):
- Indicators: Talks "continue," next round set for March, no major announcements either way
- Both sides neutral language: "constructive," "serious," "gaps remain"
- No framework, no collapse

**SCENARIO C — COLLAPSE / BREAKDOWN** (talks failed or Iran/US walked out):
- Indicators: Walkout, expulsion, ultimatum issued, "unacceptable," sanctions escalated
- One side blames the other publicly
- Trump announces military timeline or escalation

---

## Task 2: Execute R01 Directive — Exit PT005

**This is unconditional.** Execute before assessing the talks outcome.

PT005 exit:
- Sell PT005 (US/Israel strikes Iran by Mar 31 — NO position)
- Current NO price: ~$0.395 (check live price)
- Expected recovery: ~$289
- Realized loss: ~-$10.97
- Log to `strategies/paper-trades/trades.jsonl` with reason: "R01 correlation risk — redundant with PT003"
- Update `strategies/paper-trades/pnl-summary.md`

---

## Task 3: Execute Position Decision Based on Scenario

### IF SCENARIO A (Framework):

**PT003**: HOLD through Mar 9 (extended deadline).
- Thesis validated — talks produced framework → war risk reduced → Mar 31 YES should fall
- Update stop-loss to 63% YES (tighten further as thesis confirms)
- Update target to 50% YES (from 55%)
- Log to exit-decision memo

**PT001**: HOLD. Jun 30 has more time; framework reduces the probability.
- If Mar 31 market drops below 55% → add insight to Jun 30 thesis
- No position changes, just monitor

**New opportunities to evaluate**:
- "Iran nuclear deal by Jun 30" (currently 41.5%) — if framework confirmed, BUY YES at 41.5%? Research the resolution criteria first.
- "Iran ends enrichment by Mar 31" (18.5%) — BUY YES if framework includes enrichment cap?
- Run edge calculations before entering any new positions.

### IF SCENARIO B (Inconclusive):

**PT003**: HOLD but tightened parameters as per exit-decision memo.
- Stop: 65% YES (already set)
- Exit deadline: **Mar 5** (not Mar 9 — inconclusive = thesis not confirming)
- Target: 52-55% YES (reduced ambition)
- If Mar 31 price moves above 65%: EXIT IMMEDIATELY

**PT001**: HOLD. Jun 30 gives more time. Inconclusive talks ≠ breakdown.
- Set informal monitor: if Apr 1 price rises above 73% after T003/T005 expire → reassess

**No new Iran positions.**

### IF SCENARIO C (Collapse):

**PT003**: **EXIT IMMEDIATELY.**
- Thesis explicitly invalidated in exit-decision memo
- If YES is now above 65% → exit at loss
- Log reason: "Thesis invalidated — talks collapsed"

**PT001**: **ASSESS STOP-LOSS.**
- Jun 30 has more time, but collapse means war risk is now very real
- Current stop: if YES spikes above 75% → exit
- If YES is currently between 68-75% → reduce position by 50% (don't exit fully — Jun 30 has 4 months for diplomacy to restart)
- If YES is above 75% → EXIT FULLY

**Update thesis**: Full pivot. War risk is now the base case.

---

## Task 4: Update Iran Markets Research

Update `~/Desktop/prediction-markets/domains/GEO/active.md` with:

1. Geneva talks outcome (Scenario A/B/C classification)
2. Updated market prices for all Iran markets (pull from Polymarket)
3. Updated PT001/PT003 positions after executing R01 directive and scenario-based decisions
4. Next catalyst: IAEA Board meeting (~Mar 2-3), Trump deadline expiry (~Mar 5), IAEA censure vote

Update `~/Desktop/prediction-markets/domains/GEO/research/iran-us-2026.md` with the talks narrative.

---

## Task 5: New Opportunities Post-Geneva

Depending on scenario, evaluate these FRESH:

### If Scenario A or B:
- **Khamenei out by Mar 31 at 18.5%**: Does a framework make this MORE or LESS likely? Diplomatic resolution = regime survival signal → SELL (NO)
- **Iran regime fall before 2027 at 35.5%**: Framework = regime more stable → potential SELL
- **"Israel-Iran ceasefire broken by Mar 31" at 56.5%**: If talks progressing, this should FALL → potential BUY for NO

### If Scenario C:
- **US strikes Iran by Mar 31 at 60.5%**: Is this NOW underpriced? What's your revised estimate?
- **US strikes Iran by Jun 30 at 69.5%**: Collapse changes fundamental risk
- **Don't revenge-trade**: Think carefully. Scenario C means the thesis was wrong. Don't double down immediately.

---

## Output

1. Updated `strategies/paper-trades/trades.jsonl` — PT005 exit logged
2. Updated `strategies/paper-trades/pnl-summary.md` — reflection of PT005 exit and any other changes
3. Updated `domains/GEO/active.md` — current prices, positions, scenario classification
4. Updated `domains/GEO/research/iran-us-2026.md` — Geneva outcome narrative
5. Exit-decision addendum: add Geneva outcome + action taken to `exit-decision-2026-02-26.md`
6. Terminal output: What scenario (A/B/C)? What actions were taken? What is current Iran cluster exposure after actions?

**Done when**: PT005 is exited, scenario is classified, position decisions are executed and logged, and GEO domain files are updated with current intelligence.

**Time pressure**: This should run immediately. If Geneva outcome is still developing (talks in progress), assess what's known so far and set monitoring parameters. Don't wait for perfect information.
