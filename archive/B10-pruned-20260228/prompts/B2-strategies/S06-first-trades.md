You are a prediction market trader executing the first paper trades based on completed research.

## Context

Read these files first (in order):
1. ~/Desktop/prediction-markets/strategies/evolution/strategy-domain-matrix.md — top 5 recommended pairs
2. ~/Desktop/prediction-markets/strategies/backtests/S006-time-decay-backtest.md — time decay edge confirmation
3. ~/Desktop/prediction-markets/domains/GEO/research/iran-us-2026.md — Iran deep dive
4. ~/Desktop/prediction-markets/domains/ECO/research/fed-policy-2026.md — Fed analysis
5. ~/Desktop/prediction-markets/domains/POL/research/2028-presidential.md — presidential race analysis
6. ~/Desktop/prediction-markets/strategies/paper-trades/trade-schema.md — trade format

The strategy-domain matrix recommends these first trades:
1. S006-GEO: Time decay on Iran "by date" markets
2. S007-POL: Overround arb on 2028 nomination markets
3. S004-GEO: Contrarian fade on Iran rhetoric spikes
4. S003-ECO: Catalyst play on March FOMC
5. S008-GEO: Info edge on Iran probability

## Tasks

1. **Fetch current market prices** for all relevant markets using the Polymarket API
2. **For each of the 5 recommended trades**, execute the paper trade:
   - Calculate position size per strategy rules (from playbooks)
   - Form independent estimate with reasoning
   - Log the prediction to `calibration/predictions.jsonl` using the schema
   - Log the trade to `strategies/paper-trades/trades.jsonl` using the schema
   - Update `strategies/paper-trades/positions.json` with new positions
3. **For the POL arb trade**: sum all candidate YES prices on the Republican 2028 nomination market. If overround > 3%, identify which NO position to buy.
4. **For the Iran time decay trade**: use the time-decay-screener.py output to identify the best entry. Run `python3 scripts/time-decay-screener.py` and use its output.
5. **Update the P&L dashboard**: `strategies/paper-trades/pnl-summary.md`
6. **Update domain active.md files** with the positions taken

## Rules (from BANKROLL.md)
- **Phase 1**: $250 deployed (of $1,250 total bankroll)
- Max 10% of total bankroll ($125) per trade
- Max 30% of total bankroll per domain
- Use quarter-Kelly sizing
- Phase 1 focus: 2-3 S006 time decay positions + 1 S004 if spike available
- Log EVERYTHING — reasoning, entry price, strategy, prediction link
- Form your estimate BEFORE checking market price where possible

## Output

All trade logs in their respective JSONL files.
Updated positions.json and pnl-summary.md.
A brief trade report summarizing: what was traded, why, expected edge, key risks.

Write the trade report to: `~/Desktop/prediction-markets/strategies/paper-trades/trade-report-2026-02-23.md`
