You are a prediction market portfolio manager evaluating whether to exit two weakening positions.

## Context

Read these files first:
1. ~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md — current P&L
2. ~/Desktop/prediction-markets/strategies/paper-trades/trade-report-2026-02-23.md — original thesis for each trade
3. ~/Desktop/prediction-markets/domains/GEO/research/iran-us-2026.md — Iran research base
4. ~/Desktop/prediction-markets/domains/GEO/active.md — current GEO positions and estimates
5. ~/Desktop/prediction-markets/strategies/playbooks/ — S003 and S004 exit rules

## Position Review: T003 — Iran Mar 31 NO (S004 Contrarian)

**Current state:**
- Entry: YES 57.5% ($0.425 NO)
- Current: YES 60.5% ($0.395 NO)
- Loss: -$21.18 (-7.1%)
- Original exit rules: Target ~45-50% YES, 14-day limit (exit by **Mar 9**), stop if YES > 68%

**Questions to evaluate:**

1. **Is the thesis still valid?**
   - The thesis was: Feb 26 Geneva talks = active diplomatic off-ramp → prices should REVERT
   - What happened at the Feb 26 talks? Search for "Iran Geneva talks February 26 2026"
   - Has the "token enrichment" compromise gained or lost traction since Feb 23?
   - Is Trump's "10-15 day deadline" (from Feb 19) being treated as real by markets?

2. **What does the new market structure tell us?**
   - A new "Iran by March 15" market appeared at 50% — this prices the deadline window directly
   - Why is Mar 31 at 60.5% when Mar 15 is at 50%? The gap should be ~5-8pp, not 10.5pp — this suggests some temporal inconsistency (possible S007 arb)
   - The "US next strikes Iran on Feb 26" was at 1.75% — did it resolve? What actually happened?

3. **Decision framework** (from S004 playbook):
   - Exit rule says: exit by Mar 9 if "no reversion"
   - "No reversion" = price has not moved toward 50% (our target)
   - Currently at 60.5% — that's moved AWAY from 50%, not toward
   - Should we exit early to preserve capital? Or is the Feb 26 talks outcome the key data?

4. **Post-Feb-26 update**:
   - If talks produced a framework/framework-adjacent outcome → hold or ADD (thesis validated)
   - If talks collapsed → exit immediately (thesis invalidated)
   - If talks inconclusive / extending → hold, but revise price target

## Position Review: T004 — Fed 25bp Cut March (S003 Catalyst)

**Current state:**
- Entry: YES 2.85%
- Current: YES 2.3%
- Loss: -$42.11 (-20.6%)
- Original reasoning: CME FedWatch at 5.9% vs Poly 2.85%. Asymmetric 35:1 payoff.

**Questions to evaluate:**

1. **Has the CME-Polymarket divergence persisted or closed?**
   - Fetch current CME FedWatch probability for March 25bp cut
   - If CME is still significantly above Polymarket → thesis intact (divergence persists)
   - If CME has dropped to match Polymarket (~2.3%) → thesis gone (divergence closed)

2. **What economic data has come in since Feb 23?**
   - Search for: February jobs report (if released), CPI data, PCE data
   - Any FOMC member speeches or minutes since Feb 23?
   - Has any data shifted the Fed's stated patience stance?

3. **Decision framework** (from S003 playbook):
   - S003 entries are speculative asymmetric plays — expected to lose 80-90% of the time
   - The 35:1 payoff means we only need 3% probability to break even
   - Key question: has the probability dropped BELOW our breakeven (3%)?
   - If current probability is ~2.3% on Polymarket and CME has converged → edge is gone → exit
   - If CME still at 4-5% → gap persists → hold through March 18

4. **Hold/exit calculus:**
   - If we exit now: lock in -$42.11 loss, save $161.89 for redeployment
   - If we hold: 97.7% chance we lose the remaining $161.89; 2.3% chance of 35x payout
   - Exit if: CME probability dropped to < 3.5% (convergence) OR Fed has explicitly guided against any March action

## Task: Fetch Current Data

```bash
# Current Iran market prices
curl -s "https://gamma-api.polymarket.com/events?q=iran+strikes&limit=5"

# Current Fed markets  
curl -s "https://gamma-api.polymarket.com/events?q=fed+march&limit=5"

# CME FedWatch (alternative: search web for current probabilities)
```

Also web search:
- "Iran Geneva talks outcome February 26"
- "CME FedWatch March 2026 rate cut probability"
- Any Trump deadline statements on Iran since Feb 23

## Output

A structured decision memo:

**T003 Decision**: [HOLD / EXIT / ADD]
- Rationale
- Updated price target and stop-loss if holding
- Exit instructions if exiting

**T004 Decision**: [HOLD / EXIT]
- Rationale
- Whether to re-enter April FOMC instead (if March is a bust)

Update `strategies/paper-trades/pnl-summary.md` and `positions.json` based on the decision.
If any positions are closed, log to `strategies/paper-trades/trades.jsonl` with outcome notes.
Log any resolved predictions to `calibration/resolutions.jsonl`.

Write the decision memo to: `~/Desktop/prediction-markets/strategies/paper-trades/exit-decision-2026-02-26.md`
