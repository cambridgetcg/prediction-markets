# Live Account Graduation Criteria

*Created: 2026-02-25 | Wallet: 0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3*

---

## Current Status

**Level: 0 (System Testing)**
**Progress: 0.6 / 1.0** — 3 of 5 required positions opened, 0 resolved.
**Next milestone**: LT002 (Feb 28) and LT003 (Mar 3) resolve cleanly with accurate record-keeping → 3 opens confirmed + 2 resolved. Need 2 more clean opens to complete Level 0.
**Earliest Level 1 date**: ~Mar 7 (if 2 more positions opened by then)
**Earliest Level 2 date**: ~Mar 25 (if 5 positions closed by then with clean records)

---

## Level 0: System Testing ($12/trade) — CURRENT

**Purpose**: Platform mechanics, UX, position management, record-keeping practice
**Max position size**: $12 (5% of ~$242 USDC.e)

**Entry criteria**: Account funded, first trade executed.
**Status**: Active since Feb 23, 2026. Three positions open (LT001, LT002, LT003).

**Exit criteria (all must be true)**:
- [x] Wallet connected and USDC.e deposited
- [x] First trade executed without errors
- [x] Position tracking file (live-trades.md) operational
- [ ] 5 positions opened and tracked without execution errors (3/5 done)
- [ ] At least 1 position resolved with accurate P&L recording (0/1 done)
- [ ] No execution errors: wrong market, wrong side, wrong size, failed tx (0 errors so far — PASS)

**What counts as an execution error**:
- Buying YES when thesis says NO (or vice versa)
- Wrong market (similar title but different resolution date)
- Size exceeds 5% rule
- Failed transaction not caught and re-executed
- P&L recorded incorrectly vs. on-chain reality

---

## Level 1: Skin in the Game ($12-25/trade)

**Purpose**: Meaningful strategy execution testing with real downside
**Max position size**: $25 (or 5% of bankroll, whichever is smaller)

**Entry criteria**: Level 0 complete.

**Exit criteria (all must be true)**:
- [ ] 5+ positions CLOSED in live account with accurate P&L
- [ ] Live win rate >= 40% on resolved positions (minimum 5 resolutions)
- [ ] Zero execution errors in last 5 consecutive trades
- [ ] Paper account Brier score < 0.25 on resolved predictions (12 SOTU resolutions: 0.230 — PASSING if counted)
- [ ] Bond rotation (S011) formally documented with playbook and used in at least 1 live trade
- [ ] Live trades tracked in trade-index.md with complete cross-reference

**Notes**:
- SOTU Brier (0.230) is retrospective, not live. Need at least 3 live prediction resolutions to validate.
- Paper T004 (Fed March) resolved at -17.5% — first real test of exit discipline.
- Level 1 is where we prove the tracking system works under resolution pressure.

---

## Level 2: Partial Live ($50/trade)

**Purpose**: Live account operates alongside paper with increasing weight
**Max position size**: $50 (or 5% of bankroll)

**Entry criteria**: Level 1 complete.

**Exit criteria (all must be true)**:
- [ ] 10+ positions closed in live with full P&L history
- [ ] Combined live + paper beat market on >50% of resolved predictions (Brier comparison)
- [ ] At least 1 long-duration position (>30 day hold) fully resolved in live or paper
- [ ] Correlation rules (R01) implemented and followed for last 5 entries
- [ ] No strategy deployed without a reviewed playbook (all active strategies have S0XX or P0X docs)
- [ ] Live bankroll stable or growing (not losing >10% from starting)

**Key gate**: The first long-duration resolution (LT001 Iran Mar 31, or equivalent) provides crucial data on whether directional thesis quality holds over time, not just fast-resolution bond rotation.

---

## Level 3: Meaningful Exposure ($100/trade)

**Purpose**: Live account as primary alongside paper for validation
**Max position size**: $100 (or 5% of bankroll)

**Entry criteria**: Level 2 complete.

**Exit criteria (all must be true)**:
- [ ] 20+ closed positions across both accounts
- [ ] Sharpe ratio > 0.5 on closed live trades (annualized)
- [ ] Beat market on calibration (Brier < market Brier) across minimum 30 predictions
- [ ] No open correlation violations for 60+ consecutive days
- [ ] Live bankroll has grown >= 5% from initial deposit ($242.15 → $254.26+)
- [ ] Full playbooks exist for all deployed strategies
- [ ] At least 3 different strategies tested in live (not just S011 bond rotation)

**Key gate**: This is where we prove the SYSTEM works, not just individual trades. Need strategy diversity and sustained performance.

---

## Level 4: Full Deployment ($250+/trade)

**Purpose**: Live account as the primary trading system
**Max position size**: $250 (or 5% of bankroll)

**Entry criteria**: Level 3 complete.

**Exit criteria (all must be true)**:
- [ ] 50+ closed positions in live
- [ ] 12 consecutive months of records (earliest: Feb 2027)
- [ ] Annualized bankroll growth consistently > 20%
- [ ] Whale signal infrastructure (P05) operational and confirming entries
- [ ] NegRisk scanner (P01) running automatically
- [ ] Bond rotation screening (S011) automated
- [ ] Cross-platform arbitrage (S007 Type 4) tested

**Timeline**: This is a 12+ month goal. Cannot rush here. The data must speak.

---

## Promotion Protocol

When exit criteria for current level are met:

1. Write a level-promotion memo in `trades/level-promotion-[date].md`
2. Verify ALL criteria with evidence (links to trades, Brier scores, screenshots)
3. Update this file's "Current Status" section
4. Increase max position size in live-trades.md header
5. Do NOT skip levels. Each level exists for a reason.

**Demotion triggers** (drop one level):
- 3 consecutive losing trades at new level
- Execution error at new level
- Bankroll drawdown > 15% in any 30-day window
- Correlation violation discovered

---

## Key Dates

| Date | Event | Impact |
|------|-------|--------|
| Feb 28 | LT002 resolves | First live resolution — Level 0 progress |
| Mar 3 | LT003 resolves | Second live resolution — Level 0 progress |
| ~Mar 7 | Level 0 → 1 possible | If 2 more clean opens placed |
| Mar 25 | Level 1 → 2 possible | If 5 clean resolutions by then |
| Mar 31 | LT001 resolves | First long-duration live resolution |
| Jun 2026+ | Level 2 → 3 possible | Need 20+ closed, 30+ predictions |
| Feb 2027 | Level 3 → 4 earliest | Need 12 months of records |
