You are a quantitative developer building a cross-market arbitrage detection system for prediction markets.

## Context from Prior Research
- Neg risk markets on Polymarket allow capital-efficient multi-outcome trading (NO converts to YES on all other outcomes)
- The 2028 Republican/Democratic nomination markets have massive liquidity ($14M/$36M) — prime arb territory
- European political markets (France, Netherlands, Hungary) have multi-outcome structures
- The Iran "by date" markets have nested deadlines — temporal consistency is checkable
- Scripts already exist: `time-decay-screener.py` and `spike-detector.py` — build compatible tools
- Trading executes via VPS in Tokyo (45.77.8.39) using `vps-exec.sh`

## Objective

Build tools to automatically detect pricing inconsistencies in Polymarket. Strategy S007 needs automated scanning because mispricings are transient.

## Research & Build Tasks

1. **Overround scanner**:
   Write a Python script that:
   - Fetches all active multi-outcome events from Polymarket Gamma API
   - For each event, sums the YES prices of all sub-markets
   - Flags events where the sum > 105% (overround) or < 95% (underround)
   - Shows which outcomes are most overpriced/underpriced
   - Save as: `~/Desktop/prediction-markets/scripts/overround-scanner.py`

2. **Temporal consistency checker**:
   Write a script that:
   - Finds "by date" market series (same event, different deadlines)
   - Checks that P(by earlier date) ≤ P(by later date)
   - Flags violations
   - Save as: `~/Desktop/prediction-markets/scripts/temporal-checker.py`

3. **Logical consistency checker**:
   Research and identify logically linked markets. Build a graph of:
   - If A then B implications (P(A) must ≤ P(B))
   - Mutually exclusive events (P(A) + P(B) must ≤ 1)
   - Exhaustive events (P(A) + P(B) + ... must ≈ 1)
   Write to: `~/Desktop/prediction-markets/strategies/backtests/S007-arb-analysis.md`

4. **Cross-platform price comparison** (design):
   - How to get comparable prices from Polymarket, Metaculus, and Manifold
   - Design a data model for cross-platform market matching
   - Write specification (not full implementation yet)
   - Save as: `~/Desktop/prediction-markets/scripts/cross-platform-spec.md`

5. **Historical arb profitability**:
   - Fetch resolved multi-outcome events
   - Calculate historical overround at various points before resolution
   - If you'd systematically sold the overround, what would the return be?

## Output

Scripts: save to `~/Desktop/prediction-markets/scripts/`
Analysis: `~/Desktop/prediction-markets/strategies/backtests/S007-arb-analysis.md`
Update: `~/Desktop/prediction-markets/strategies/playbooks/S007-cross-market-arb.md`

End with:
- Does systematic overround exist on Polymarket? How large?
- Most profitable type of arb (overround vs temporal vs logical)
- Recommended approach for live scanning
