# L01 — Edge Calculator: Per-Account, Per-Category Profit Profiling

You are a quantitative analyst building a systematic edge-profiling system for Polymarket. The goal is to compute every resolvable account's **true edge** across all categories — not raw win rate, but performance relative to the market-implied probability at the time of each bet.

## Why Win Rate Alone Is Misleading

A bettor who buys YES at 70¢ and wins 70% of the time has zero edge. The market was right. An insider who buys YES at 20¢ and wins 90% of the time has massive edge — the market said 80% NO, they knew it was ~95% YES. That delta is the signal.

**The only useful metric:**

```
Edge_i = outcome_i − entry_price_i

Where:
  outcome_i = 1 if bet won, 0 if lost
  entry_price_i = price paid per share (= market-implied probability at time of entry)

Per-account, per-category edge:
  mean_edge(account, category) = Σ Edge_i / N
  ROI(account, category) = Σ (outcome_i × 1.0 - entry_price_i) / Σ entry_price_i
```

Positive mean edge = account consistently beats the market. Zero edge = calibrated but no alpha. Negative edge = the market was smarter.

## Read First

1. `~/Desktop/prediction-markets/research/whale-signal-research.md` — existing whale analysis
2. `~/Desktop/prediction-markets/strategies/playbooks/S010-whale-signal.md` — current whale signal strategy
3. `~/Desktop/prediction-markets/prompts/polymarket/P07-insider-detection-pipeline.md` — single-trade detection (this is the complement: population-level profiling)
4. `~/Desktop/prediction-markets/data/whale-registry.json` — known whale wallets (these should already score highly; use as validation set)

---

## Task 1: Data Collection

### 1a. Polymarket Data Sources

The full trade history is available via:

**Gamma API (REST, no auth required):**
```
https://gamma-api.polymarket.com/trades?limit=500&offset=0
https://gamma-api.polymarket.com/trades?maker_address=0x...
```

**CLOB API:**
```
https://clob.polymarket.com/trades?maker_address=0x...&limit=500
```

**Dune Analytics:**
- Search: "Polymarket all trades resolved" — several public dashboards exist
- Target datasets with: wallet, market_id, entry_price, outcome, category, timestamp

**On-chain (Polygon):**
- All CTF (Conditional Token Framework) transfers are on-chain
- TheGraph subgraph for Polymarket: `https://api.thegraph.com/subgraphs/name/polymarket/polymarket-matic`

### 1b. Build the Trade Scraper

Write: `~/Desktop/prediction-markets/scripts/edge-calculator.py`

```python
"""
Edge Calculator — L01

Scrapes all resolved Polymarket trades from Gamma API, computes per-account
per-category edge, and outputs a ranked edge profile table.

Data schema (per trade):
  {
    "wallet": "0x...",
    "market_id": "...",
    "category": "GEO" | "POL" | "ECO" | "FIN" | "CRY" | "TEC" | "SCI" | "SOC" | "LAW" | "ENV",
    "entry_price": 0.35,      # price paid per YES share (= market probability at entry)
    "shares": 1000,            # number of shares purchased
    "direction": "YES" | "NO",
    "outcome": 1 | 0,          # 1 = won, 0 = lost
    "resolved_at": "2026-01-15T12:00:00Z",
    "trade_value_usd": 350.0   # entry_price × shares
  }

Output:
  ~/Desktop/prediction-markets/data/edge-profiles.json
  ~/Desktop/prediction-markets/data/edge-profiles.csv
"""

import requests
import json
from collections import defaultdict
from scipy import stats
import numpy as np

GAMMA_API = "https://gamma-api.polymarket.com"
CATEGORIES = ["GEO", "POL", "ECO", "FIN", "CRY", "TEC", "SCI", "SOC", "LAW", "ENV"]

# Step 1: Fetch resolved markets with category tags
# Step 2: For each market, fetch all trades
# Step 3: For each trade, compute edge = outcome - entry_price
# Step 4: Aggregate by (wallet, category): N trades, mean_edge, ROI, std_dev
# Step 5: Filter to wallets with >= MIN_TRADES per category (default: 10)
# Step 6: Compute statistical significance: t-test against H0: mean_edge = 0
# Step 7: Output ranked table

MIN_TRADES_PER_CATEGORY = 10
MIN_TOTAL_TRADES = 20
SIGNIFICANCE_THRESHOLD = 0.05  # p < 0.05 to be considered a signal
```

### 1c. Category Mapping

Polymarket markets have tags. Map their tags to our 10-domain system:

```python
CATEGORY_MAP = {
    # Polymarket tag → our domain
    "politics": "POL",
    "elections": "POL",
    "trump": "POL",
    "us-politics": "POL",
    "world": "GEO",
    "middle-east": "GEO",
    "russia-ukraine": "GEO",
    "china": "GEO",
    "economics": "ECO",
    "fed": "ECO",
    "inflation": "ECO",
    "stocks": "FIN",
    "commodities": "FIN",
    "crypto": "CRY",
    "bitcoin": "CRY",
    "ethereum": "CRY",
    "ai": "TEC",
    "tech": "TEC",
    "science": "SCI",
    "health": "SCI",
    "culture": "SOC",
    "sports": "SOC",  # note: sports = SOC in our system
    "legal": "LAW",
    "climate": "ENV",
}
```

If a market has no matching tag, classify as "OTHER" and exclude from edge analysis (too noisy).

---

## Task 2: Edge Profile Schema

### 2a. Per-Account Output

For each account with >= MIN_TOTAL_TRADES resolved bets:

```json
{
  "wallet": "0x4576...",
  "alias": "Theo" | null,
  "total_trades": 147,
  "total_profit_usd": 1240.50,
  "overall_mean_edge": 0.043,
  "categories": {
    "POL": {
      "n": 89,
      "mean_edge": 0.112,
      "roi": 0.234,
      "std_dev": 0.421,
      "t_stat": 2.51,
      "p_value": 0.007,
      "significant": true,
      "total_wagered_usd": 45200,
      "net_profit_usd": 1890
    },
    "GEO": {
      "n": 41,
      "mean_edge": 0.012,
      "roi": 0.021,
      "std_dev": 0.489,
      "t_stat": 0.16,
      "p_value": 0.87,
      "significant": false
    },
    "CRY": {
      "n": 17,
      "mean_edge": -0.034,
      "significant": false
    }
  },
  "dominant_category": "POL",
  "insider_score": 7.2,  # computed in L02
  "last_active": "2026-02-20T09:14:00Z"
}
```

### 2b. Population Summary

```json
{
  "generated_at": "2026-02-26T10:00:00Z",
  "total_accounts_analysed": 15420,
  "accounts_above_significance": 234,
  "accounts_with_localised_edge": 67,  # edge in 1-2 categories only (insider signal)
  "accounts_with_broad_edge": 31,      # edge across 3+ categories (superforecaster signal)
  "top_10_by_overall_edge": [...],
  "top_10_by_category": {
    "POL": [...],
    "GEO": [...],
    "CRY": [...]
  }
}
```

---

## Task 3: Validation Against Known Cases

### 3a. AlphaRaccoon Test

AlphaRaccoon was identified as a probable Google insider (22/23 Google predictions correct):
- Find their wallet address (documented in P07 research)
- Run their trades through the edge calculator
- Expected result: massive positive edge in TEC/SOC, near-zero edge elsewhere
- If the calculator correctly surfaces them as a TEC-category outlier → algorithm validated

### 3b. Venezuela/Maduro Test

The $32K → $400K+ Maduro trade came from a single fresh wallet (one-time insider):
- Single-trade insiders WON'T appear in longitudinal profiling (they disappear after)
- Confirm: the edge calculator should NOT surface these wallets (they have N=1, excluded)
- This is correct behaviour — L01 is for systematic insiders, not one-time front-runners
- P07 covers one-time insiders. L01 covers repeat insiders. Together they cover the full space.

### 3c. Known Whale Wallets

From `whale-registry.json`:
- Theo (POL specialist) → should show highest edge in POL category
- zxgngl ($29M POL) → should show localised POL edge
- HyperLiquid0xb (sports) → should show SOC edge

If our known whales surface correctly → calculator is working.

---

## Task 4: Performance Benchmarks

The calculator needs efficiency constraints — Polymarket has millions of trades.

**Recommended approach:**
1. Start with resolved markets only (complete signal, no partial outcomes)
2. Filter to wallets with >= 20 total resolved trades (eliminates noise accounts)
3. Batch API calls: fetch markets by category, then fetch trades per market
4. Cache locally: `data/raw-trades/YYYY-MM-DD.jsonl` (daily incremental updates)
5. Use pandas for aggregation, scipy.stats.ttest_1samp for significance tests

**Expected dataset size:**
- ~500K wallets have ever traded on Polymarket
- ~50K have >= 5 resolved trades
- ~5K-15K have >= 20 resolved trades
- ~200-400 will show statistically significant edge in at least one category

---

## Output

1. `scripts/edge-calculator.py` — complete script with data fetching, edge computation, statistical tests
2. `data/edge-profiles.json` — full edge profile for all qualifying accounts
3. `data/edge-profiles.csv` — spreadsheet-friendly version
4. `data/edge-summary.json` — population-level stats
5. Terminal output: top 20 accounts by edge in each category (validation table)
6. Validation report: did AlphaRaccoon and known whales surface correctly?

**Done when**: The script runs end-to-end on at least 6 months of resolved market data and produces a ranked edge profile table. The top entries in the POL category should match or include known whale wallets from `whale-registry.json`.
