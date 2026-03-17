# Module 2: Market Snapshot Cache

## Task

Build `scripts/s012/market_snapshot.py` — a module that captures Polymarket price snapshots, matches news events to relevant markets, and tracks price movements over time.

## Context

When a news event breaks, we need to know:
1. Which Polymarket markets are relevant to this event?
2. What are their current prices?
3. What were their prices BEFORE the news (to measure the market's reaction)?

The existing `spike-detector.py` fetches market data from Gamma API but doesn't store historical snapshots. We need a lightweight price history to compute reaction deltas.

## Requirements

### Input
- `NewsEvent` from Module 1 (key_entities, domain, summary)
- Gamma API market data

### Output
```python
@dataclass
class MarketSnapshot:
    market_id: str
    question: str
    slug: str
    yes_price: float
    no_price: float
    volume_24h: float
    volume_total: float
    liquidity: float
    end_date: str
    domain: str
    snapshot_time: datetime
    # Token IDs for trading
    yes_token: str
    no_token: str

@dataclass
class MarketMatch:
    event: NewsEvent              # The news event
    market: MarketSnapshot        # The matched market
    relevance_score: float        # 0.0-1.0, how relevant is this market to the event
    price_before: float | None    # YES price before news (from cache, if available)
    price_after: float            # YES price now (current snapshot)
    actual_move: float | None     # price_after - price_before (None if no prior snapshot)
```

### Behavior

1. **Market fetching**: Use Gamma API to fetch active markets (reuse `fetch_markets()` and `parse_market()` from `spike-detector.py`)
   - Filter out sports markets (reuse `SPORTS_KEYWORDS` from spike-detector)
   - Cache full market list (refresh every 5 minutes max, not per-event)

2. **Market matching**: Given a `NewsEvent`, find relevant Polymarket markets
   - Match by entity overlap: event entities vs market question keywords
   - Match by domain: GEO events → GEO markets, etc.
   - Scoring: each shared entity = +0.3 relevance, same domain = +0.2, keyword in question = +0.2
   - Minimum relevance threshold: 0.3 (below this, skip)
   - Return top 5 matches per event

3. **Price history**: Store snapshots in SQLite
   - New table `market_snapshots` in `data/news-pipeline.db`:
     ```sql
     CREATE TABLE IF NOT EXISTS market_snapshots (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         market_id TEXT NOT NULL,
         yes_price REAL NOT NULL,
         volume_24h REAL,
         liquidity REAL,
         snapshot_time TEXT NOT NULL,
         trigger_event_id TEXT  -- NULL for periodic snapshots, event_id for news-triggered
     );
     CREATE INDEX IF NOT EXISTS idx_snapshots_market ON market_snapshots(market_id);
     CREATE INDEX IF NOT EXISTS idx_snapshots_time ON market_snapshots(snapshot_time);
     ```
   - Take periodic snapshots of watched markets (every 15 min for high-interest, hourly for others)
   - "Price before" = most recent snapshot BEFORE the news event's first_seen timestamp

4. **Watched markets**: Maintain a "watchlist" of markets we're actively monitoring
   - Initially: all markets matching any configured query domain
   - Pruned: only markets with volume > $100K and resolution > 24h away
   - Updated when market list refreshes

### Gamma API Details

```
GET https://gamma-api.polymarket.com/markets?limit=100&closed=false&order=volume&ascending=false&offset={offset}
```

Response fields we need:
- `id` → market_id
- `question` → question
- `slug` → slug
- `outcomePrices` → JSON string, parse to get [yes_price, no_price]
- `clobTokenIds` → JSON string, parse to get [yes_token, no_token]
- `volumeNum` → volume_total
- `volume24hr` → volume_24h
- `liquidityNum` → liquidity
- `endDate` → end_date
- `oneDayPriceChange`, `oneWeekPriceChange` → for S004 compatibility

### What to Reuse

From `scripts/spike-detector.py`:
- `curl_json()` or equivalent (switch to `httpx` for consistency)
- `fetch_markets()` pagination logic
- `parse_market()` field extraction
- `classify_domain()` and `DOMAIN_KEYWORDS`
- `is_sports()` and `SPORTS_KEYWORDS`

### CLI Interface

```bash
python3 scripts/s012/market_snapshot.py --scan              # Fetch and display all active markets
python3 scripts/s012/market_snapshot.py --match "Iran nuclear talks"  # Find markets matching text
python3 scripts/s012/market_snapshot.py --snapshot           # Take snapshot of watched markets
python3 scripts/s012/market_snapshot.py --history <market_id> # Show price history for a market
python3 scripts/s012/market_snapshot.py --watchlist          # Show current watchlist
```

### Tests

Append to `scripts/s012/test_s012.py`:
- `test_market_matching()` — "Iran nuclear" event matches Iran strike markets
- `test_relevance_scoring()` — more entity overlap = higher score
- `test_snapshot_storage()` — snapshot round-trips through SQLite
- `test_price_before_lookup()` — finds correct pre-event price
- `test_sports_filtering()` — NBA/NFL markets excluded

### Conventions

- Same as Module 1 (Python 3.12+, type hints, dataclasses, httpx, sqlite3, pathlib, logging)
- Market cache in memory (dict), snapshots in SQLite
- No Gamma API calls in tests — use fixtures/mock data
