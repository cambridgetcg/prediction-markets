You are a prediction market trader opening the next round of paper positions.

## Context

Read these files first:
1. ~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md — current portfolio state
2. ~/Desktop/prediction-markets/strategies/evolution/strategy-domain-matrix.md — strategy-domain fit
3. ~/Desktop/prediction-markets/calibration/predictions.jsonl — existing predictions
4. ~/Desktop/prediction-markets/strategies/paper-trades/trade-schema.md — trade format

## Current Portfolio Situation

Portfolio is -$110 (-6.9% on deployed). 5 open positions — all Iran-heavy in GEO, one POL arb, one ECO catalyst.

**Gaps identified from Batch 1 analysis:**
- NO Vance 2028 deep research has been done — he's the biggest alpha in POL
- NO Maduro Venezuela trade opened despite identified 14% edge
- NO April FOMC trade despite 11% being more interesting than March's 2.85%
- NO CRY domain positions despite identified time-decay edge
- ECO domain has only the March FOMC (weakening)

## Task 1: Vance 2028 Nomination Research + Trade

**The opportunity**: J.D. Vance at 41.6% YES on the 2028 Republican nomination.
- From T002 analysis: my estimate is 55-65% (a 13-24pp edge)
- He's the sitting VP — VP base rate for nomination is ~80% after 2 terms
- Market is heavily discounting him for reasons worth investigating

**Research tasks:**
1. Fetch current Polymarket price: `curl -s "https://gamma-api.polymarket.com/events?q=republican+2028&limit=5"`
2. Fetch current Vance polling, favorability, and 2028 prediction data from web search
3. Research reasons for market discount: any scandals, challengers, primary dynamics?
4. Form independent estimate with historical VP base rate reasoning
5. Confirm edge is real, not a gap in my knowledge

**Trade (if edge confirmed ≥10pp):**
- Strategy: S001 (Hold to Resolution) — directional, long-dated
- Size: $250 (per Phase 1 rules — max $125/trade, but this is the highest-conviction opportunity; use $125 if strict, up to $250 if overriding with documented rationale)
- Log prediction to calibration/predictions.jsonl
- Log trade to strategies/paper-trades/trades.jsonl
- Update positions.json

## Task 2: Venezuela Maduro NO Trade

**The opportunity**: From D07 research — Maduro is in Brooklyn MDC on federal charges with 20yr mandatory minimum. Market has him at ~12.4% to lead Venezuela by end of 2026.

1. Fetch current Polymarket price for Venezuela leader EOY market
2. Confirm Maduro is still in federal custody (verify with web search — check for any legal developments since Feb 23)
3. If unchanged: execute paper trade
   - Strategy: S008 (Info Edge Type A)
   - Direction: Maduro NO
   - Size: $125 (conservative, long duration)
   - Log prediction + trade

## Task 3: April FOMC Catalyst

**The opportunity**: April FOMC 25bp cut is at 11% on Polymarket. Much better asymmetry than March (which we're already in at 2.85%).

1. Fetch current April FOMC markets
2. Research: what's the market consensus for April vs March? Goldman/CME FedWatch data?
3. Key question: if March is "no change" (96% likely), does that make April MORE or LESS likely to cut?
4. Key economic data between Mar 18 (FOMC) and Apr 29-30 (April FOMC): Feb PCE (Mar 28), Mar jobs (Apr 4), Mar CPI (Apr 10)
5. If edge confirmed:
   - Strategy: S003 (Catalyst) — April meeting is the catalyst
   - Direction: YES on 25bp cut
   - Size: $150 (slightly larger than T004 March, since April is better priced)
   - Timing: Better to enter after March FOMC (Mar 18) when we have the dot plot. Log the **intent** now but flag as "pending March 18 entry signal"

## Task 4: CRY Domain — Bitcoin Time Decay

**The opportunity**: Bitcoin price-by-date markets. BTC at ~$64K. All 2026 high-price targets ($200K, $180K, $160K) are NO candidates via S006.

1. Fetch current CRY price target markets from Polymarket
2. Run: `python3 ~/Desktop/prediction-markets/scripts/time-decay-screener.py` and filter to CRY domain
3. From the D04 research: "Best risk/reward: $200K NO" — confirm current price
4. Is $160K still the "dangerous NO"? At what price does the edge disappear?
5. If $200K NO is still at ≤6%, execute:
   - Strategy: S006 (Time Decay)
   - Direction: BTC $200K NO
   - Size: $100 (small — CRY has higher tail risk than GEO for time decay)
   - Log prediction + trade

## Output Requirements

For each trade executed:
- Entry in calibration/predictions.jsonl (form estimate BEFORE checking market price where possible)
- Entry in strategies/paper-trades/trades.jsonl
- Updated strategies/paper-trades/positions.json
- Updated strategies/paper-trades/pnl-summary.md

Write a trade report to: `~/Desktop/prediction-markets/strategies/paper-trades/trade-report-2026-02-25.md`

The report should include: what was traded, current thesis, edge calculation, risks, portfolio correlation analysis.

## Risk Constraints
- Phase 1: $250 max new deployment (don't exceed $250 total across this batch)
- Max 10% single position ($100 given $1,000 Phase 1 = wait, total bankroll is $10K so max is $1,000 per position — use $125 as the practical limit)
- Total GEO exposure after this batch should not exceed $1,000 ($900 already deployed)
- If all 4 trades are taken, total new: ~$600 — document the Phase 1 limit tension
