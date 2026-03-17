# Trade Index — Unified Cross-Reference

*Created: 2026-02-25 | Convention: LT = Live Trade, PT = Paper Trade*

---

## Naming Convention

| Prefix | Account | Tracking File |
|--------|---------|---------------|
| **LT** | Live (real money) | `trades/live-trades.md` |
| **PT** | Paper ($10K virtual) | `strategies/paper-trades/pnl-summary.md` |

Old convention used `T00X` for both accounts. Remapped Feb 25, 2026.

---

## Live Trades (LT)

| New ID | Old ID | Market | Side | Strategy | Domain | Opened | Resolves | Status |
|--------|--------|--------|------|----------|--------|--------|----------|--------|
| LT001 | T006 (live) | Will US/Israel strike Iran by Mar 31? | NO | S008 | GEO | 2026-02-23 | 2026-03-31 | OPEN |
| LT002 | T008 (live) | US collect <$100b revenue in 2025? | YES | S011 | ECO | 2026-02-23 | 2026-02-28 | OPEN |
| LT003 | T009 (live) | Ken Paxton wins TX Republican Primary? | YES | S003 | POL | 2026-02-23 | 2026-03-03 | OPEN |

**Next live ID**: LT004

---

## Paper Trades (PT)

| New ID | Old ID | Market | Side | Strategy | Domain | Opened | Resolves | Status |
|--------|--------|--------|------|----------|--------|--------|----------|--------|
| PT001 | T001 | US strikes Iran by Jun 30 | NO | S004 | GEO | 2026-02-23 | 2026-06-30 | OPEN |
| PT002 | T002 | Trump wins 2028 GOP nom | NO | S001 | POL | 2026-02-23 | ~2028-08 | OPEN |
| PT003 | T003 | US strikes Iran by Mar 31 | NO | S004 | GEO | 2026-02-23 | 2026-03-31 | OPEN |
| PT004 | T004 | Fed 25bp cut March | YES | S003 | ECO | 2026-02-23 | 2026-03-18 | **CLOSED** (-17.5%) |
| PT005 | T005 | US/Israel strikes Iran by Mar 31 | NO | S008 | GEO | 2026-02-23 | 2026-03-31 | OPEN |
| PT006 | T006 (paper) | Vance wins 2028 GOP nom | YES | S001 | POL | 2026-02-25 | ~2028-08 | OPEN |
| PT007 | T007 | Maduro leads Venezuela EOY | NO | S008 | GEO | 2026-02-25 | 2026-12-31 | OPEN |
| PT008 | T008 (paper) | BTC reaches $150K by EOY | NO | S006 | CRY | 2026-02-25 | 2026-12-31 | OPEN |

**Next paper ID**: PT009

---

## Prediction Cross-Reference

Maps prediction IDs (calibration/predictions.jsonl) to new trade IDs.

| Prediction ID | Old Trade ID(s) | New Trade ID(s) | Notes |
|---------------|-----------------|-----------------|-------|
| pred-0001 | T001 | PT001 | Paper only |
| pred-0002 | T002 | PT002 | Paper only |
| pred-0003 | T003 | PT003 | Paper only |
| pred-0004 | T004 | PT004 | Paper — CLOSED |
| pred-0005 | T005 | PT005, LT001 | Paper + Live (same market, different framing) |
| pred-0006 | T006 (paper) | PT006 | Paper only |
| pred-0007 | T007 | PT007 | Paper only |
| pred-0008 | T008 (paper) | PT008 | Paper only |
| pred-0009 | — | — | Pending (April FOMC, no trade yet) |

**Note**: pred-0005 covers both PT005 and LT001 — same underlying market (US/Israel Iran Mar 31). LT001 is the live execution of the same thesis.

---

## Overlap: Same Market in Both Accounts

| Market | Paper ID | Live ID | Notes |
|--------|----------|---------|-------|
| US/Israel strike Iran by Mar 31 | PT005 | LT001 | Same thesis, different sizing ($410 paper vs $12 live) |

No other overlaps currently. Paper and live are deliberately running different playbooks (paper = long-duration directional; live = fast-resolution diverse).

---

## Files Containing Old T00X References (Not Yet Updated)

The following files still reference old T001-T009 naming. These are historical records and research docs — updating them is optional but the cross-reference above is authoritative.

- `calibration/predictions.jsonl` — trade_ids field uses old T00X
- `strategies/paper-trades/trades.jsonl` — historical trade log
- `strategies/paper-trades/positions.json` — position snapshots
- `strategies/paper-trades/trade-report-2026-02-23.md` — Batch 1 report
- `strategies/paper-trades/trade-report-2026-02-25.md` — Batch 2 report
- `strategies/paper-trades/exit-decision-2026-02-26.md` — PT004 exit analysis
- `domains/GEO/active.md`, `domains/POL/active.md`, `domains/ECO/active.md`
- Various prompt and research files

**Rule**: All NEW entries from this point forward use LT/PT convention. Historical files are grandfathered with old naming — use this index to translate.

---

## Statistics

| Account | Open | Closed | Total | Strategies Used |
|---------|------|--------|-------|----------------|
| Live | 3 | 0 | 3 | S003, S008, S011 |
| Paper | 7 | 1 | 8 | S001, S003, S004, S006, S008 |
| **Combined** | **10** | **1** | **11** | **5 unique** (S001, S003, S004, S006, S008, S011) |
