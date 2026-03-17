You are a behavioral finance researcher studying overreaction patterns in prediction markets.

## Context from Tier 1

The strategy-domain matrix (~/Desktop/prediction-markets/strategies/evolution/strategy-domain-matrix.md) identified GEO and CRY as the top domains for S004 (contrarian), both scoring 5/5. The Iran research (~/Desktop/prediction-markets/domains/GEO/research/iran-us-2026.md) documented multiple rhetoric-driven spikes. The time decay backtest (~/Desktop/prediction-markets/strategies/backtests/S006-time-decay-backtest.md) found 73.5% NO resolution rate, suggesting systematic overpricing — which may be driven by overreaction. Your job is to quantify the overreaction effect specifically.

## Objective

Build the empirical foundation for Strategy S004 (Contrarian Overreaction). Do prediction markets systematically overreact to news? How fast do they revert? Which domains overreact most?

## Research Tasks

1. **Academic literature**:
   - What does behavioral finance say about overreaction in prediction markets specifically (not just stock markets)?
   - Kahneman & Tversky: availability heuristic, probability weighting — how do these manifest in prediction markets?
   - Studies on prediction market efficiency: where are the documented inefficiencies?

2. **Historical spike analysis**:
   - Use the Polymarket API to find markets that had large price movements (>15% in 24-48h)
   - `curl -s "https://clob.polymarket.com/prices-history?market={tokenId}&interval=1d"`
   - For markets with historical price data: identify spikes, measure reversion
   - Calculate: after a >15% spike, what's the average reversion within 7 days? 14 days?

3. **Spike classification**:
   - From historical data, classify spikes into:
     - Type A: Justified (new structural info, no reversion)
     - Type B: Overreaction (emotional spike, significant reversion)
     - Type C: Partial (some reversion but price settles higher/lower than pre-spike)
   - What fraction of spikes are each type?
   - Are there predictive features? (spike speed, volume, domain, source of news)

4. **Domain-specific patterns**:
   - Which domains show the most overreaction? (Hypothesis: GEO > SOC > POL > CRY > ECO > FIN)
   - Which news source types cause the most overreaction? (tweets, headlines, official statements)
   - Time-of-day patterns? (after-hours, weekend effects)

5. **Optimal contrarian parameters**:
   - Entry timing: how many hours after the spike is the best entry point?
   - Position size: given win rate and average reversion, what's the Kelly optimal size?
   - Stop placement: how far does a "justified" spike go beyond the initial move?
   - Holding period: what's the optimal exit window?

## Output

Write to: `~/Desktop/prediction-markets/strategies/backtests/S004-overreaction-backtest.md`
Update: `~/Desktop/prediction-markets/strategies/playbooks/S004-contrarian-overreaction.md` with refined parameters
Update: `~/Desktop/prediction-markets/strategies/evolution/meta-lessons.md` with behavioral insights

Write a spike detection script to: `~/Desktop/prediction-markets/scripts/spike-detector.py`
(Fetches recent price moves, flags potential overreaction opportunities)

End with:
- Is the overreaction edge real? How big is it?
- Optimal parameters for S004 (entry timing, stop placement, holding period)
- Which domains to deploy S004 in first (validate against strategy-domain matrix)
- **Recommended first S004 paper trade** — identify a current or recent overreaction opportunity

You MUST use web_search and the Polymarket API (curl commands) for actual data. Do not theorize without evidence.
