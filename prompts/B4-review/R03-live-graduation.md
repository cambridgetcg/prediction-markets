You are a trading system architect defining the graduation criteria for the live account — when to scale from $12 test trades to meaningful live exposure, and how to reconcile the paper and live systems as they mature in parallel.

## Context

Live account (0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3) is in testing phase:
- Bankroll: ~$1,354 (USDC.e + POL)
- 5% max rule = ~$12 per trade
- Only 3 trades opened (Feb 23), all at or below $12
- 2 of 3 positions resolve within 6 days (T008, T009 live)

Paper account: $10,000 virtual, 7 open positions, -0.93% bankroll

The two accounts are running different playbooks by instinct:
- Paper: long-duration directional bets
- Live: fast-resolution, diverse, S011 bond rotation by instinct

**The key question**: What must be TRUE before risking meaningfully more in live?

## Read First

1. ~/Desktop/prediction-markets/trades/live-trades.md
2. ~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md
3. ~/Desktop/prediction-markets/calibration/predictions.jsonl
4. ~/Desktop/prediction-markets/calibration/resolutions.jsonl
5. ~/Desktop/prediction-markets/calibration/calibration.md (if I05 has been run)
6. ~/Desktop/prediction-markets/strategies/strategy-scorecard-2026-02-25.md (if R02 has been run)

---

## Task 1: Graduation Criteria Framework

Define explicit, measurable criteria for each level:

### Level 0 → Level 1: $12 per trade (CURRENT)
**Status**: Active
**Purpose**: Platform testing, UX verification, position management practice
**Exit criteria for this level**: 5 positions opened and tracked successfully without errors (wrong market, wrong side, execution failures). T006/T008/T009 live counts as 3 — need 2 more.

### Level 1 → Level 2: $25 per trade
**Purpose**: Meaningful test of strategy execution with some skin in the game
**Required before moving:**
- [ ] 5+ positions closed (not just opened) in live account with accurate record-keeping
- [ ] Live account win rate ≥ 40% (on resolved positions)
- [ ] No execution errors (wrong direction, wrong market, size error) in last 5 trades
- [ ] Paper account Brier score <0.20 on resolved predictions (beats random)
- [ ] S011 (bond rotation) formally implemented in both paper and live

### Level 2 → Level 3: $50 per trade
**Purpose**: Partial-live trading alongside paper
**Required:**
- [ ] 10+ positions closed in live with P&L tracking
- [ ] Live + paper combined beat market on >50% of resolved predictions (Brier score comparison)
- [ ] At least one full resolution cycle of a long-duration position (wait for T006 Mar 31 or similar)
- [ ] Correlation rules (R01) implemented and followed for last 5 entries
- [ ] No single strategy has been used without a formal playbook review first

### Level 3 → Level 4: $100 per trade (meaningful live exposure)
**Purpose**: Live account as primary system alongside paper
**Required:**
- [ ] 20+ closed positions across both accounts
- [ ] Sharpe ratio > 0.5 on closed trades (annualised)
- [ ] Beat market on calibration (Brier score < market average) across minimum 30 predictions
- [ ] No open correlation violations (R01 rules maintained for 60+ days)
- [ ] Live bankroll has grown (not just protected) — required growth of at least 5% from initial
- [ ] Full strategy playbooks for all deployed strategies (S001-S012 where used)

### Level 4 → Level 5: $250+ per trade (full deployment)
**Purpose**: Live account as the primary system
**Required:**
- [ ] 50+ closed positions
- [ ] 12 consecutive months of records
- [ ] Bankroll growth consistently > 20% annualised
- [ ] Whale signal infrastructure working (P05) to confirm entries
- [ ] NegRisk scanner (P01) running automatically
- [ ] Full automation of bond rotation screening (S011)

---

## Task 2: Paper-to-Live Selection Criteria

Not every paper trade should go live. Define the filter:

### Automatic Live Qualification (run both paper AND live):
- **S011 Bond Rotation**: High probability (>95%), short duration (<7 days), clear criteria → always run live at current level. Low execution risk, fast resolution, safe to practice.
- **S007 Structural Arb**: If scanner confirms genuine overround (not stale) → live at current level. Mathematical edge, no directional exposure.
- **POL primary markets** (Ken Paxton type): Domain expertise + clear winner/loser resolution + catalyst event → good live candidate at current level.

### Paper Only (for now):
- **GEO directional (Iran, Venezuela)**: High oracle ambiguity (S009 Score 4-5), long duration, high correlation risk → paper only until oracle risk framework is proven
- **Very long duration (>6 months)**: Capital tied up in live account detracts from cycling through more trades for calibration data
- **New, untested strategies** (S009, S010, P01): Paper test first, minimum 3 resolutions before live

### Case-by-Case:
- **S008 Information Edge**: High quality information edges that are SHORT duration (<30 days) can go live at reduced size (50% of paper size)
- **S004 Contrarian**: Depends on domain. POL/ECO contrarian: consider live. GEO contrarian: paper only until S004 GEO domain restriction is resolved.
- **S001 Long Hold**: No more S001 positions in live until Level 3+ (opportunity cost is too high)

---

## Task 3: The Tracking & Naming Convention Fix

Current problem: Both accounts use T00X numbering but with DIFFERENT trades:
- Paper T006 = Vance 2028 YES
- Live T006 = Iran/Israel Mar 31 NO

This will cause confusion and accounting errors. Fix it now while positions are small.

**Proposed new convention:**
- Paper: `PT001`, `PT002`, etc. (prefix P)
- Live: `LT001`, `LT002`, etc. (prefix L)

**Remapping:**
```
Live current:
  LT001 = US/Israel strike Iran Mar 31 NO (was T006 live)
  LT002 = US collect <$100b revenue YES (was T008 live)
  LT003 = Ken Paxton TX primary YES (was T009 live)

Paper:
  PT001 = US strikes Iran Jun 30 NO (was T001)
  PT002 = Trump 2028 GOP nom NO (was T002)
  PT003 = US strikes Iran Mar 31 NO (was T003)
  [PT004 = Fed 25bp March — CLOSED]
  PT005 = US/Israel Iran Mar 31 NO (was T005)
  PT006 = Vance 2028 YES (was T006)
  PT007 = Maduro Venezuela NO (was T007)
  PT008 = BTC $150K NO (was T008)
```

Update both tracking files with the new convention. Create a cross-reference: `~/Desktop/prediction-markets/trades/trade-index.md`

---

## Task 4: Live Account Strategy for Next 30 Days

Given the graduation criteria and the live account's current state (Level 0 → Level 1 transition), design the next 30 days of live trades:

**Priority order for live at Level 1 ($12-25 per trade):**

1. **Bond rotation (S011)**: Every market that meets criteria (>95%, <7 days, clear resolution). These are the fastest path to resolved trades and calibration data. Target 5-10 such trades in 30 days.

2. **Primary/election markets (S003 variant)**: Events like Paxton (Texas primary Mar 3), any other state primaries, FOMC result (overnight before meeting when at 97%+ probability). 1-2 trades per week.

3. **One GEO directional (maximum)**: Continue LT001 (Iran Mar 31) — already open. DO NOT add more Iran positions in live while LT001 is open (correlation cap).

4. **No long-duration holds in live for now**: T006 paper (Vance) should stay paper-only.

**30-day target for Level 1:**
- 8-12 positions opened
- 6-10 positions resolved (closed)
- No execution errors
- Track actual vs. expected (estimate calibration)

**Exit criteria for Level 1 → Level 2:**
- By March 25, have 5 resolved live positions with clean records → graduate to $25/trade

---

## Task 5: The Paper-Live Reconciliation Report

Once T008 (live, Feb 28) and T009 (live, Mar 3) resolve, write a reconciliation report comparing:
- Paper estimates vs. live outcomes
- Whether paper would have called the same trades
- Whether live sizing was appropriate
- First real Brier score from LIVE predictions (not paper/SOTU retrospective)

**Create template**: `~/Desktop/prediction-markets/trades/live-resolution-report-template.md`

---

## Output

1. `~/Desktop/prediction-markets/trades/graduation-criteria.md` — the level system
2. `~/Desktop/prediction-markets/trades/paper-to-live-filter.md` — selection criteria
3. `~/Desktop/prediction-markets/trades/trade-index.md` — unified cross-reference with new PT/LT naming
4. Updated `~/Desktop/prediction-markets/trades/live-trades.md` — fix naming convention to LT
5. Updated `~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md` — fix naming convention to PT
6. `~/Desktop/prediction-markets/trades/live-30day-plan.md` — next 30 days strategy for live account
7. `~/Desktop/prediction-markets/trades/live-resolution-report-template.md` — post-resolution template

**Critical output**: Make a clear statement in the graduation criteria file about what the current level IS and what the next trigger event is. E.g., "Currently Level 0.7. Next milestone: T008/T009 live resolve cleanly → advance to Level 1. Earliest Level 2 date: March 25."
