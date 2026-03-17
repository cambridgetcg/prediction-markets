# Backtesting

## Purpose

Test strategies against historical data before committing paper capital. Polymarket has historical price data via the CLOB API.

## Methodology

### Data Sources
- **Polymarket CLOB API**: Historical price series for resolved markets
  - `GET /prices-history?market={tokenId}&interval={1m|1h|1d}&fidelity={1-60}`
- **Polymarket Gamma API**: Resolved events with outcome data
  - `GET /events?closed=true&order=volume&ascending=false`

### Backtest Process

1. **Collect**: Gather resolved markets with historical prices
2. **Classify**: Tag each market by domain
3. **Simulate**: Apply strategy rules to historical prices
4. **Score**: Calculate P&L, win rate, Sharpe, max drawdown
5. **Compare**: Strategy vs buy-and-hold (S001 baseline)
6. **Validate**: Out-of-sample test (train on first half, test on second)

### Backtesting Pitfalls to Avoid

| Pitfall | Description | Mitigation |
|---------|-------------|------------|
| **Lookahead bias** | Using future info in past decisions | Strict time-ordering of signals |
| **Survivorship bias** | Only testing on markets that got big | Include low-volume resolved markets |
| **Overfitting** | Tuning to history too precisely | Out-of-sample validation |
| **Transaction costs** | Ignoring spread and slippage | Add 1-2% friction per trade |
| **Selection bias** | Cherry-picking favorable backtests | Test ALL strategies on SAME dataset |

### Data Collection Script

TODO: Build a script that:
1. Fetches resolved Polymarket events (last 6-12 months)
2. Gets price history for each market
3. Stores in `backtests/data/` as JSON
4. Tags with domain classification

### Priority Backtests

1. **S006 Time Decay** — Most testable. Historical "by date" markets with known resolution.
2. **S004 Contrarian** — Look for historical spikes and measure reversion.
3. **S005 Momentum** — Check if persistent trends existed.
4. **S007 Arb** — Historical overround in multi-outcome markets.

### Future: Automated Backtesting

When we have enough historical data, build:
- `backtest.py` — applies strategy rules to historical data
- Configurable parameters per strategy
- Generates standard report (P&L, Sharpe, calibration, domain breakdown)
- Comparison table: all strategies on same dataset
