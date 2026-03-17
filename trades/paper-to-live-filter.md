# Paper-to-Live Selection Filter

*Created: 2026-02-25 | Applies at: Level 0-2 (review at Level 3)*

Not every paper trade should go live. This filter determines which paper positions qualify for parallel live execution and which should remain paper-only.

---

## Tier 1: Automatic Live Qualification

These strategies run BOTH paper AND live at the current level's max size.

### S011 Bond Rotation
- **Criteria**: Probability > 95%, resolution < 7 days, binary resolution, clear outcome
- **Why live**: Lowest execution risk, fastest resolution cycle, best calibration data generator
- **Size**: Full current-level max ($12 at Level 0, $25 at Level 1, etc.)
- **Examples**: FOMC rate hold at 98%, earnings beat at 96%, primary winner at 97%

### S007 Structural Arbitrage (Type 1: Overround)
- **Criteria**: Scanner confirms genuine overround > 3%, not stale pricing, sufficient liquidity
- **Why live**: Mathematical edge, no directional exposure, self-hedging
- **Size**: Full current-level max, split across legs
- **Gate**: Must verify overround is real-time (not stale/resolved sub-markets inflating sum)

### Primary/Election Markets (S003 variant)
- **Criteria**: Domain expertise + clear winner-loser resolution + catalyst within 7 days
- **Why live**: High-information, fast resolution, well-defined outcomes
- **Size**: Full current-level max
- **Examples**: LT003 Ken Paxton primary (clear polling lead + Mar 3 resolution)

---

## Tier 2: Paper Only (Until Specified Level)

These stay in paper until the system proves itself.

### GEO Directional (Iran, Venezuela, conflict markets)
- **Why paper only**: High oracle ambiguity (S009 Score 4-5), long duration, correlated positions, emotional pricing
- **Graduate to live at**: Level 2, AND S009 oracle framework proven on 3+ resolutions, AND no more than 1 GEO live position at a time
- **Current exposure**: LT001 (Iran Mar 31) is the ONE allowed GEO live position

### Very Long Duration (> 6 months)
- **Why paper only**: Capital locked up, prevents cycling through trades for calibration data, opportunity cost
- **Graduate to live at**: Level 3 (when bankroll is large enough that one locked position doesn't constrain)
- **Examples**: PT002 (Trump 2028 nom), PT006 (Vance 2028), PT007 (Maduro EOY), PT008 (BTC $150K EOY)

### New/Untested Strategies (S009, S010, P01, any new)
- **Why paper only**: No resolution data yet, unknown failure modes
- **Graduate to live at**: After 3 paper resolutions with documented results per strategy
- **Gate**: Must have a formal playbook (strategies/playbooks/S0XX.md) before any live deployment

---

## Tier 3: Case-by-Case

These require individual assessment before going live.

### S008 Information Edge
| Condition | Decision |
|-----------|----------|
| Duration < 30 days + high-quality info synthesis | Live at 50% of paper size |
| Duration > 30 days | Paper only |
| Domain = GEO | Paper only (see GEO rules above) |
| Domain = POL/ECO/TEC | Live candidate at reduced size |

### S004 Contrarian Overreaction
| Condition | Decision |
|-----------|----------|
| Domain = POL or ECO | Live candidate at full size |
| Domain = GEO | Paper only until GEO restriction lifts |
| Spike source = emotional (>45% emotional fraction) | Requires 48h wait before live entry |
| Spike source = structural | Paper only (structural ≠ overreaction) |

### S006 Time Decay
| Condition | Decision |
|-----------|----------|
| Domain = ENV or POL (highest NO rates: 82%, 78%) | Live candidate |
| Duration < 30 days + YES price 40-65% | Live candidate |
| Domain = ECO (most efficient pricing) | Paper only |
| Duration > 90 days | Paper only |

### S001 Long Hold
- **Decision**: No live positions until Level 3+
- **Reason**: Opportunity cost too high at small bankroll. Every $12 locked for 12+ months is $12 not cycling through 3-5 bond rotations generating calibration data.

---

## Decision Checklist (Before Any Live Entry)

Before placing a live trade, verify:

- [ ] Strategy has a formal playbook? (If no → paper only)
- [ ] Meets Tier 1 auto-qualify OR Tier 3 case-by-case approval?
- [ ] Not in Tier 2 exclusion zone?
- [ ] Correlation check: no >2 positions in same domain in live? (R01)
- [ ] Size within current level's max?
- [ ] Resolution date within appropriate window for current level?
- [ ] Prediction logged in calibration/predictions.jsonl?
- [ ] Added to trades/trade-index.md?

---

## Review Schedule

- **Monthly**: Review filter criteria against actual results
- **At each level promotion**: Reassess which Tier 2 items can graduate
- **After any live loss > 25%**: Review whether the filter should have caught it
