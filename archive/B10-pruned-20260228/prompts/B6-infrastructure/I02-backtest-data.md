You are a data engineer building a historical dataset of resolved prediction markets for backtesting.

## Context from Prior Research
The S006 backtest already found 73.5% NO resolution rate across "by date" markets. The S004 backtest documented negative serial correlation. But both used limited data. We need a comprehensive historical dataset for:
1. Validating the time decay edge across more markets
2. Testing the overreaction reversion rates with actual price history
3. Building domain-specific base rates (GEO vs CRY vs POL resolution patterns)
4. Training position sizing models (Kelly criterion needs win rate + payoff data)
Existing scripts in `~/Desktop/prediction-markets/scripts/` — extend, don't duplicate.

## Objective

Collect and structure historical Polymarket data for strategy backtesting. The `strategies/backtests/` directory needs actual data to test against.

## Build Tasks

1. **Resolved events collector** (`scripts/collect-resolved.py`):
   Write a script that:
   - Fetches resolved events from Polymarket Gamma API:
     `https://gamma-api.polymarket.com/events?closed=true&order=volume&ascending=false&limit=100`
   - Iterates through pages to collect a large dataset
   - For each event: title, markets, resolution outcome, dates, volume, liquidity
   - Filters out trivially small markets (< $10K volume)
   - Classifies each by domain (GEO/POL/ECO/FIN/CRY/TEC/SCI/SOC/LAW/ENV) using keyword matching
   - Saves to `data/polymarket/resolved-events.json`

2. **Price history collector** (`scripts/collect-price-history.py`):
   For the top resolved markets by volume:
   - Fetch price history from CLOB API:
     `https://clob.polymarket.com/prices-history?market={tokenId}&interval=1d&fidelity=1`
   - Store as `data/polymarket/price-history/{market-slug}.json`
   - Include: timestamps, prices, for both YES and NO tokens

3. **Dataset statistics**:
   Generate a summary report:
   - Total resolved markets collected
   - Distribution by domain
   - Distribution by outcome (YES/NO resolution rates)
   - Distribution by market size (volume buckets)
   - Average market duration (creation to resolution)
   - Save to `data/polymarket/dataset-summary.md`

4. **Backtesting data format**:
   Create a standardized format for backtesting:
   ```json
   {
     "market_id": "...",
     "title": "...",
     "domain": "GEO",
     "created": "2025-01-01",
     "resolved": "2025-06-01",
     "outcome": "NO",
     "price_history": [{"date": "2025-01-01", "price": 0.30}, ...],
     "volume": 1000000,
     "final_price": 0.02
   }
   ```
   Save cleaned dataset to `data/polymarket/backtest-ready.json`

5. **Quick analysis**:
   From the collected data, answer:
   - What fraction of prediction markets resolve YES vs NO? (If NO > 60%, systematic overpricing of YES)
   - Do high-volume markets resolve differently than low-volume?
   - Is there a domain-level difference in YES/NO rates?

## Output

Scripts in `~/Desktop/prediction-markets/scripts/`
Data in `~/Desktop/prediction-markets/data/polymarket/`
Summary in `data/polymarket/dataset-summary.md`

End with:
- Dataset size and quality assessment
- Preliminary finding: is YES systematically overpriced?
- Which domains have enough data for statistically meaningful backtests?
- Recommended next steps for backtesting
