You are a quantitative analyst building and testing a time decay strategy for prediction markets.

## Objective

Strategy S006 hypothesizes that "Will X happen by [date]?" markets systematically overprice the YES outcome because humans overweight dramatic/scary events. Your job is to build the mathematical foundation, test it against historical data, and produce a tool for screening opportunities.

## Research Tasks

1. **Build the math**:
   - For a "by date" market at price P with N days remaining:
     - Constant hazard model: implied daily p = 1 - (1-P)^(1/N)
     - Increasing hazard model: if probability is front-loaded or back-loaded
     - Decreasing hazard model (most events: risk decreases as deadline approaches without occurrence)
   - How to compare implied daily probability to a base rate
   - At what divergence (implied vs base rate) does the edge become significant?

2. **Historical backtest**:
   - Use the Polymarket Gamma API to find resolved "by date" markets:
     `curl -s "https://gamma-api.polymarket.com/events?limit=100&closed=true&order=volume&ascending=false"`
   - Filter for "by [date]" structure
   - For each: what was the price at various points before resolution? Did they resolve YES or NO?
   - Calculate: what fraction resolved NO? (If >50%, systematic overpricing exists)
   - Calculate: what would a mechanical "buy NO at market price" strategy have returned?

3. **Screening tool**:
   - Write a Python script that:
     - Fetches active "by date" markets from Polymarket
     - Calculates implied daily probability for each
     - Compares to domain-specific base rates (from a configurable table)
     - Flags markets where implied daily p > 2x base rate
     - Outputs ranked opportunities
   - Save as `~/Desktop/prediction-markets/scripts/time-decay-screener.py`

4. **Risk analysis**:
   - What's the expected loss profile? (Many small wins, occasional large loss)
   - Kelly criterion: optimal position sizing given win rate and payoff ratio
   - Portfolio correlation: if you hold multiple NO positions, how correlated are the risks?
   - Black swan protection: when a "by date" market resolves YES, how fast does the price move? Can you exit?

5. **Domain-specific calibration**:
   - Do certain domains overprice more than others?
   - Hypothesis: GEO (war/conflict) markets overprice most (fear bias). ECO (Fed decisions) overprice least (sophisticated participants).
   - Test if historical data supports this.

## Output

Write main findings to: `~/Desktop/prediction-markets/strategies/backtests/S006-time-decay-backtest.md`
Write the screening tool to: `~/Desktop/prediction-markets/scripts/time-decay-screener.py`
Update: `~/Desktop/prediction-markets/strategies/playbooks/S006-time-decay.md` with any refinements

End with:
- Does the time decay edge exist in historical Polymarket data?
- What's the estimated annual return of a mechanical NO strategy?
- Which domain/market types show the strongest overpricing?
- Recommended parameters for live paper trading
