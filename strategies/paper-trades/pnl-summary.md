# P&L Dashboard (Paper Account)

*Last updated: 2026-02-28T00:10:00Z (E01 Sprint 1 — 10 fast-resolution positions added)*
*Naming: Paper trades use PT prefix. Sprint trades use FT prefix.*

## Portfolio

| Metric | Value |
|--------|-------|
| Starting bankroll | $10,000.00 |
| Allocated | $2,193.26 (21.9%) |
| Available | $7,806.74 (78.1%) |
| Current value | $9,757.16 |
| Realized P&L | **-$168.26** |
| Unrealized P&L | **-$74.58** |
| Total P&L | **-$242.84 (-2.43%)** |
| Return on deployed | -11.1% |
| Open positions | 15 (5 core + 10 sprint) |
| Closed trades | 3 |
| Win rate | 0/3 (0%) |

## Open Positions (Mark-to-Market)

| ID | Strategy | Market | Dir | Entry | Curr | Unrealized P&L | Resolves |
|----|----------|--------|-----|-------|------|----------------|----------|
| PT001 | S004 | US strikes Iran by Jun 30 | NO | $0.335 / 66.5% | ~75% | **-$76.12** | 2026-06-30 |
| PT002 | S001 | Trump wins 2028 GOP nom | NO | $0.972 / 2.8% | 2.5% | **+$1.54** | ~2028-08 |
| PT006 | S001 | Vance wins 2028 GOP nom | YES | $0.416 / 41.6% | 41.6% | **$0.00** | ~2028-08 |
| PT007 | S008 | Maduro leads Venezuela EOY | NO | $0.873 / 12.8% | 12.8% | **$0.00** | 2026-12-31 |
| PT008 | S006 | BTC reaches $150K by EOY | NO | $0.915 / 8.5% | 8.5% | **$0.00** | 2026-12-31 |

## Closed Trades

| ID | Strategy | Market | Dir | Entry | Exit | P&L | Return | Reason |
|----|----------|--------|-----|-------|------|-----|--------|--------|
| PT004 | S003 | Fed 25bp cut March | YES | $0.029 | $0.024 | **-$35.09** | -17.5% | Thesis invalidated — CME-Poly divergence closed, hot PCE |
| PT003 | S004 | US strikes Iran Mar 31 | NO | $0.425 | $0.34 | **-$60.00** | -20.0% | Stop triggered: YES 66% > 65% stop. Geneva inconclusive |
| PT005 | S008 | US/Israel strikes Iran Mar 31 | NO | $0.41 | $0.31 | **-$73.17** | -24.4% | R01 correlation exit: most redundant position (ρ=0.95) |

## E01 Sprint 1 Positions (Fast Resolution)

| ID | Domain | Market | Dir | My Est | Market | Edge | Size | Resolves |
|----|--------|--------|-----|--------|--------|------|------|----------|
| FT001 | POL | Paxton wins TX GOP | NO | 75% | 78% | 3pp | $50 | Mar 3 |
| FT002 | POL | Crockett TX Dem nominee | YES | 65% | 36% | **29pp** | $150 | Mar 3 |
| FT003 | POL | CDU most seats BW | YES | 72% | 68% | 4pp | $50 | Mar 8 |
| FT004 | POL | Greens most seats BW | NO | 27% | 31% | 4pp | $50 | Mar 8 |
| FT005 | GEO | Somalia 10-13 strikes | NO | 65% | 84% | **19pp** | $200 | Mar 4 |
| FT006 | SOC | Scream 7 >$65M OW | NO | 25% | 50% | **25pp** | $200 | Mar 2 |
| FT007 | CRY | BTC >$66K Mar 1 | NO | 47% | 48% | 1pp | $50 | Mar 1 |
| FT008 | GEO | Balen Shah PM Nepal | NO | 52% | 54% | 2pp | $50 | Mar 5+ |
| FT009 | GEO | Israel strike Gaza Feb 28 | YES | 45% | 34% | **11pp** | $100 | Feb 28 |
| FT010 | POL | Talarico TX Dem nominee | NO | 33% | 62% | **29pp** | $75 | Mar 3 |
| | | | | | **Sprint total** | | **$975** | |

**Sprint thesis**: 4 high-edge bets (FT002, FT005, FT006, FT010), 3 YES-direction trades (FT002, FT003, FT009), 5 domains represented.
**Correlation note**: FT002+FT010 are same event ($225 combined). FT003+FT004 are inverse ($100 combined).

## Position Alerts

| ID | Alert | Status |
|----|-------|--------|
| PT001 | Iran YES at ~75% (+5pp from Feb 26). Only Iran position. Stop: 78% YES. Next review: Mar 7 post-IAEA Board. Geneva inconclusive (Scenario B). | **WATCH** |
| PT002 | Working. Very long-dated. | HOLD |
| PT006 | Monitor Trump endorsement signals. Long-dated. | HOLD |
| PT007 | Resolution criteria ambiguity — monitor market definition. Next hearing Mar 26. | WATCH |
| PT008 | First CRY position. Monitor BTC vs $90K recovery level. | HOLD |

## By Strategy

| Strategy | Open | Closed | Win Rate | Realized P&L | Unrealized P&L | Status |
|----------|------|--------|----------|-------------|----------------|--------|
| S001 Hold | **2** | 0 | — | — | +$1.54 | PT002 + PT006 |
| S003 Catalyst | 0 | 1 | 0% | -$35.09 | — | **CLOSED** — paused |
| S004 Contrarian | **1** | 1 | 0% | -$60.00 | -$49.25 | PT001 only; PT003 stopped out |
| S006 Time Decay | **1** | 0 | — | — | $0.00 | PT008 only |
| S008 Info Edge | **1** | 1 | 0% | -$73.17 | $0.00 | PT007 only; PT005 R01 exit |

## By Domain

| Domain | Allocated | % Bankroll | Realized P&L | Unrealized P&L | Positions |
|--------|-----------|------------|-------------|----------------|-----------|
| GEO | $700 | 7.0% | -$133.17 | -$49.25 | 5 (PT001, PT007, FT005, FT008, FT009) |
| POL | $1,000 | **10.0%** | — | +$1.54 | 7 (PT002, PT006, FT001-FT004, FT010) |
| ECO | $0 | 0.0% | -$35.09 | — | 0 (PT004 closed) |
| CRY | $125 | 1.25% | — | $0.00 | 2 (PT008, FT007) |
| SOC | $200 | 2.0% | — | $0.00 | 1 (FT006) |

## Key Upcoming Catalysts

| Date | Event | Affects |
|------|-------|---------|
| **Feb 28** | Israel Gaza daily resolution | FT009 |
| **Mar 1** | BTC $66K resolution | FT007 |
| **Mar 2** | Scream 7 OW final number | FT006 |
| **Mar 3** | TX primary day (GOP + Dem) | FT001, FT002, FT010 |
| **Mar 4** | AFRICOM Feb strikes count deadline | FT005 |
| **Mar 5** | Nepal election | FT008 |
| **~Mar 1-5** | Trump deadline window expires | PT001 (indirectly) |
| **~Mar 3-7** | Vienna technical talks (IAEA HQ) | PT001 |
| **Mar 8** | Baden-Württemberg election | FT003, FT004 |
| Mar 7 | February jobs report | April FOMC consideration |
| Mar 11 | February CPI | April FOMC consideration |
| Mar 13 | January PCE + GDP 2nd estimate | April FOMC consideration |
| **Mar 17-18** | FOMC meeting + dot plot | **April FOMC entry signal** |
| **Mar 26** | Maduro next court hearing | PT007 |
| Jun 30 | Iran Jun 30 market resolves | PT001 |
| Dec 31 | BTC $150K + Venezuela EOY resolve | PT007, PT008 |

## Lessons Learned (Updated Feb 27)

1. **GEO is not an easy S006 domain**: GEO has the weakest NO rate (64.3%) and the Iran market is well-calibrated.
2. **Overround arb returns are tiny**: 48.8% overround yields only 1-3% return on long-duration capital.
3. **CME FedWatch vs Polymarket divergence can close wrong way** (T13): CME dropped to meet Polymarket, not vice versa.
4. **Asymmetric lottery tickets need constant probability re-eval** (T14): 35:1 payoff means nothing if probability drops below 2.86%.
5. **S003 early entry increases exposure to thesis-killing data** (T15): 23 days before catalyst vs 3-7 day ideal window.
6. **Not all elevated pricing is overreaction** (T11): Sustained crisis pricing != event-driven spikes.
7. **Near-term and medium-term markets can diverge** (T12): Feb 28 probability fell while Mar 31 rose.
8. **Prediction markets can be more efficient than traditional derivatives on tails** (T13).
9. **Phase 1 batch limits enforce discipline** (NEW): $250 cap eliminated the no-edge April FOMC trade and forced proper sizing on Maduro/BTC positions.
10. **Pre-committed stops save money** (NEW): T003's 65% stop triggered at 66%, saving ~$40 vs holding to 70%+. The stop was set when thinking was clear (Feb 26 memo), not in the heat of the adverse move.
11. **Delayed execution on risk reduction costs real money** (NEW): R01 recommended T005 exit at -$10.97. One day later: -$73.17. The $62.20 cost of delay was the single most expensive lesson in the portfolio.
12. **Geneva "progress" is diplomatic protocol, not substance** (L16): WSJ "rejected all demands" > Araghchi's "significant progress." Weight substance over tone when classifying talk outcomes.
13. **Inconclusive is worst for short-dated NO, neutral for long-dated NO** (L17): T003/T005 (Mar 31) were killed by uncertainty persisting. PT001 (Jun 30) survives because time remains an ally.
14. **Execute exits within the hour, not the next day** (L18): T005 delay cost $62.20. T003 stop saved $40. The difference: T003 stop was automated-in-mind; T005 was "let me think about it."

## Correlation Risk

*Updated 2026-02-27 — post R01 remediation. Full analysis: risk-report-2026-02-25.md*

| Cluster | Positions | Deployed | % BK | Avg ρ | Cap (C1) | Status |
|---------|-----------|----------|------|-------|----------|--------|
| **Iran NO** | T001 only | $300 | 3.0% | — | 3% | **AT CAP** |
| POL 2028 | T002+T006 | $625 | 6.25% | 0.50 | 3%+3%* | Within caps |
| GEO other | T007 | $50 | 0.5% | — | 3% | OK |
| CRY | T008 | $75 | 0.75% | — | 3% | OK |
| **TX Dem primary** | FT002+FT010 | $225 | 2.25% | ~1.0 | 3% | OK (same event) |
| **BW election** | FT003+FT004 | $100 | 1.0% | ~-0.95 | 3% | OK (hedged pair) |
| Sprint singles | FT001,FT005-FT009 | $650 | 6.5% | <0.3 | 3% each | OK |

*POL positions are on different events (Trump nom vs Vance nom), so each gets its own C1 cap. However, they are positively correlated (ρ=0.50) — both benefit from Trump not running.*

**Effective N**: ~10.5 independent bets from 15 nominal positions (70% diversification efficiency — up from 84% pre-sprint due to correlated pairs)

**E01 Sprint adds**: 10 positions, 5 domains, resolution Feb 28–Mar 8. Sprint-specific correlation: FT002/FT010 same event, FT003/FT004 inverse. All other FT positions uncorrelated with each other and with core portfolio.

**POL domain at 10% cap**: $1,000 = $625 (core) + $375 (sprint). No more POL positions until sprint resolves.

**Rules adopted**: C1 (3% event cap), C2 (10% domain cap), C3 (ρ<0.30 for same-event additions), C4 (pre-entry delta check). See research/position-sizing-rules.md.

---

## Resolution Speed Distribution

*Added by R04 (Fast-Resolution Pipeline) — 2026-02-25. Updated 2026-02-27.*

### Current Allocation by Resolution Speed

| Speed Category | Positions | Capital | % of Deployed | Target % | Gap |
|---------------|-----------|---------|---------------|----------|-----|
| **Overnight/Weekly** (<7d) | 10 | $975 | 45% | 50% | **-5pp** |
| **Monthly** (7-30d) | 0 | $0 | 0% | 30% | **-30pp** |
| **Quarterly** (30-90d) | 0 | $0 | 0% | 15% | **-15pp** |
| **Annual/Multi-year** (>90d) | 5 | $1,050.00 | 55% | 5% | **+50pp** |
| **Total** | **15** | **$2,025.00** | **100%** | 100% | |

### Position Detail by Resolution Speed

| Speed | ID | Market | Resolves | Capital |
|-------|-----|--------|----------|---------|
| Annual | T001 | US strikes Iran by Jun 30 | 2026-06-30 | $300.00 |
| Multi-year | T002 | Trump 2028 GOP nom | ~2028-08 | $500.00 |
| Multi-year | T006 | Vance 2028 GOP nom | ~2028-08 | $125.00 |
| Annual | T007 | Maduro leads Venezuela EOY | 2026-12-31 | $50.00 |
| Annual | T008 | BTC $150K by EOY | 2026-12-31 | $75.00 |

### Calibration Velocity

| Metric | Current | Target |
|--------|---------|--------|
| Resolved predictions (total) | 12 (SOTU retro only) | 50 by month 6 |
| Sprint 1 pending resolutions | 10 (FT001-FT010) | — |
| Expected resolutions by Mar 8 | +10 = **22 total** | — |
| Resolutions per day (sprint) | ~1.3/day (10 in 8 days) | 1.0/day ✓ |
| Sprints needed for 50 total | ~4 more | — |

### Rebalancing Directive

**Next $500 deployment**: 70%+ into Weekly/Monthly resolution.

| Bucket | Amount | Candidates |
|--------|--------|------------|
| **S011 rotation fund** | $500 | FOMC overnight, data releases, near-certain "by date" markets |
| **Weekly calibration** | $125 | Trump say/talk/meet monthly batches (tiny size, $1-5 each) |
| **Monthly** | $75 | Oscars favorites, Bank of England, FOMC rate path |
| **Quarterly** | $0 | T003/T005 exited — no quarterly positions remain |

---

*Next review: Mar 3 — post-TX primary (FT001/FT002/FT010) + Scream 7 final (FT006). Also: Mar 7 — post-IAEA Board (Mar 2-6) + Vienna technical talks (Mar 2-3). PT001 stop: 78% YES.*
