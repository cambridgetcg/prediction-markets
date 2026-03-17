# Data Sources — Future Prediction Engine

_Research date: 2026-03-17. All sources verified available._

---

## The Engine's Data Needs (by layer)

```
PREDICTION MARKETS  →  market prices, orderbooks, real-time odds
MACRO/ECONOMIC      →  CPI, GDP, rates, employment, treasury yields
FINANCIAL MARKETS   →  equities, commodities (oil, gold), forex, crypto
NEWS & INTELLIGENCE →  breaking events, government releases, geopolitical
CROSS-MARKET SIGNAL →  arbitrage between prediction markets
```

---

## Layer 1: Prediction Markets (the core)

### Polymarket ⭐ PRIMARY
**What:** ~$2B+ total volume, the dominant real-money prediction market.
**API:** Free, no key required for read-only market data.
```
Base URL: https://gamma-api.polymarket.com
Markets:  GET /markets?limit=100&closed=false
Prices:   GET /markets/{conditionId}
History:  GET /prices-history?market={id}&startTs=...&endTs=...&fidelity=60
Orders:   GET https://clob.polymarket.com/books?token_id={id}
WebSocket: wss://ws-subscriptions-clob.polymarket.com/ws/ (real-time)
SDK:      pip install py-clob-client
```
**Cost:** Free for market data. Trading requires USDC wallet on Polygon.
**What we already use:** Gamma API (markets list, prices). Need to add WebSocket for real-time.

### Kalshi ⭐ SECONDARY
**What:** US-regulated CFTC-licensed exchange. Different market set from Polymarket.
**Strength:** US elections, economic indicators (Fed rates, CPI, NFP) — these are Kalshi's strongest markets. AP-licensed election data as of March 2026.
```
Base URL: https://api.elections.kalshi.com/trade-api/v2
Markets:  GET /markets?limit=100&status=open
Tickers:  GET /markets/{ticker}/orderbook
History:  GET /series/{series_ticker}/markets
WebSocket: wss://api.elections.kalshi.com/trade-api/ws/v2
SDK:      pip install kalshi-python
Demo:     https://demo-api.kalshi.co/trade-api/v2
```
**Cost:** Free for market data. Auth needed for trading.
**Key value:** Fed rate decisions, CPI, NFP, elections — better regulated market than Polymarket for these.

### Manifold Markets 📊 SIGNAL SUPPLEMENT
**What:** Play-money market. Larger question set, longer timeframes, academic/tech AI questions.
**Value:** Good for long-horizon signals (AGI by 2030, AI capabilities) and cross-validating Polymarket prices.
```
Base URL: https://api.manifold.markets/v0
Markets:  GET /markets?limit=500
Search:   GET /search-markets?term=iran+nuclear
Single:   GET /market/{marketId}
```
**Cost:** Completely free, no API key.

### FinFeedAPI / pmxt 🔧 AGGREGATOR (optional)
**What:** Normalised data from Polymarket + Kalshi + Manifold + Myriad in one API.
**Value:** Single integration for cross-platform price comparison and arbitrage detection.
```
pmxt:     pip install pmxt  (open-source, launched Jan 2026)
FinFeed:  https://finfeed.io (CoinAPI-built, REST API)
```
**Cost:** pmxt is free/open-source. FinFeedAPI has paid tiers.
**Caution:** pmxt is new (Jan 2026) — upstream API changes may break it.

---

## Layer 2: Macro/Economic Data (the context)

### FRED API ⭐ PRIMARY (free, authoritative)
**What:** Federal Reserve Bank of St. Louis. 816,000+ economic time series.
**Coverage:** CPI, PCE, GDP, unemployment, Fed funds rate, treasury yields, money supply, trade balance — everything the Oracle needs for ECO domain predictions.
```
Base URL: https://api.stlouisfed.org/fred
Series:   GET /fred/series/observations?series_id=CPIAUCSL&api_key=KEY
          Common series: CPIAUCSL (CPI), PCEPI (PCE), UNRATE (unemployment)
                         GDP, FEDFUNDS (fed rate), DGS10 (10yr treasury yield)
                         WEI (Weekly Economic Index — leading indicator)
API Key:  Free at https://fred.stlouisfed.org/docs/api/api_key.html
```
**Cost:** Completely free. Requires API key (email registration, instant).
**What to get first:** FRED API key. Takes 60 seconds.

### World Bank API 🌍 GLOBAL MACRO (free)
**What:** Global GDP, inflation, trade, development indicators. 200+ countries.
**Value:** GEO domain — understanding economic pressure on regimes, sanctions impact.
```
Base URL: https://api.worldbank.org/v2
Example:  GET /country/IR/indicator/NY.GDP.MKTP.CD?format=json  (Iran GDP)
```
**Cost:** Completely free, no key required.

---

## Layer 3: Financial Markets (cross-asset signals)

### Polygon.io ⭐ PRIMARY for equities/forex/crypto
**What:** Real-time and historical data. Stocks, options, forex, crypto, indices, commodities futures.
**Strength:** WebSocket streaming, tick-level data, lowest latency for algo use.
```
Base URL: https://api.polygon.io
Stocks:   GET /v2/aggs/ticker/SPY/range/1/minute/2026-03-17/2026-03-17
Forex:    GET /v1/conversion/GBP/USD
Crypto:   GET /v2/aggs/ticker/X:BTCUSD/range/1/hour/...
WebSocket: wss://socket.polygon.io (real-time ticks)
```
**Cost:** Free tier = 15-min delayed + limited endpoints. Paid from $29/mo (real-time).
**Verdict:** Start with free tier for signal generation (15-min delay fine for our use). Upgrade when paper trading profitable.

### Alpha Vantage 📊 FALLBACK (free tier sufficient)
**What:** Stocks, forex, crypto, macro indicators.
**Strength:** Generous free tier (500 req/day), simple Python integration.
```
pip install alpha_vantage
Base URL: https://www.alphavantage.co/query
API key:  Free at alphavantage.co
```
**Cost:** Free 500 req/day; $50/mo for 75 req/min unlimited.
**Use case:** Historical data pull, less time-sensitive signals.

### CoinGecko API 🪙 CRYPTO (free)
**What:** Crypto prices, market cap, volume, DeFi data. 10,000+ coins.
**Strength:** Best free crypto data. No API key needed for basic endpoints.
```
Base URL: https://api.coingecko.com/api/v3
Price:    GET /simple/price?ids=bitcoin&vs_currencies=usd
History:  GET /coins/bitcoin/market_chart?vs_currency=usd&days=30
```
**Cost:** Free (50 calls/min). CoinGecko Pro from $129/mo for 500 calls/min.

### Yahoo Finance (yfinance) 📈 QUICK PROTOTYPING (free)
**What:** Free, unofficial, sufficient for EOD prices and macro signals.
```
pip install yfinance
import yfinance as yf
oil = yf.download("CL=F", period="1mo")  # WTI crude futures
gold = yf.download("GC=F", period="1mo")  # Gold futures
```
**Cost:** Free. Unofficial — not for production but excellent for rapid signal testing.

---

## Layer 4: News & Intelligence (the signal)

### NewsAPI ⭐ PRIMARY (affordable)
**What:** Real-time news from 150,000+ sources. Headlines, full text, metadata.
```
Base URL: https://newsapi.org/v2
Headlines: GET /top-headlines?category=general&apiKey=KEY
Search:    GET /everything?q=iran+nuclear&sortBy=publishedAt&apiKey=KEY
```
**Cost:** Free 100 req/day (dev). $449/mo business (unlimited). **We should get the dev key first.**

### The Guardian API (free)
**What:** Full-text access to The Guardian's archive. Strong on geopolitics, economics.
```
Base URL: https://content.guardianapis.com
Search:   GET /search?q=iran+nuclear&api-key=KEY
```
**Cost:** Free with API key registration (https://bonobo.capi.gutools.co.uk/register/developer).

### GNews API (affordable)
**What:** Google News aggregation API.
```
pip install gnews
```
**Cost:** Free 100 req/day. $25/mo for 1,000 req/day.

### BrightData (we already have this) ✅
**What:** Residential proxy + web scraping for sources that block direct access.
**Account:** brd-customer-hl_2d97e1e0-zone-seer / zmyccg3vcund
**Balance:** $960.45 remaining
**Use:** Scraping government sites, paywalled news when APIs don't cover them.

---

## Layer 5: Alternative Intelligence

### CME FedWatch (free)
**What:** Fed rate probability from futures market. The market S003 strategy uses.
```
URL: https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html
```
No official API but scrapable. SerpAPI (which we have) can pull the data.

### GDELT Project (free, massive)
**What:** Real-time global event database. Every news mention of every government, organization, person. Updated every 15 minutes.
```
BigQuery: bigquery-public-data.gdelt_v2.*  (Google BigQuery free tier)
Direct:   http://data.gdelt.org/events/YYYYMMDD.export.CSV.zip
```
**Cost:** Free. The data is enormous — use BigQuery for filtered queries.
**Value for engine:** Conflict escalation signals, diplomatic event tracking, sentiment across 100+ languages. This directly feeds GEO domain predictions.

---

## Recommended Acquisition Order

### Week 1 (free, high impact, 2 hours setup)
```
[ ] FRED API key          → fred.stlouisfed.org (free, 60 seconds)
[ ] Kalshi account        → kalshi.com (free market data immediately)
[ ] Guardian API key      → bonobo.capi.gutools.co.uk (free, instant)
[ ] Manifold Markets API  → no key needed, just use it
[ ] CoinGecko basic       → no key needed
[ ] yfinance              → pip install yfinance (free, now)
```

### Week 2 (low cost, high value)
```
[ ] NewsAPI dev key       → newsapi.org ($0, 100 req/day free tier)
[ ] Polygon.io free tier  → polygon.io ($0, 15-min delay)
[ ] Alpha Vantage key     → alphavantage.co ($0, 500 req/day)
[ ] GNews API             → gnews.io ($0 free tier)
```

### Month 2 (paid, when paper trading profitable)
```
[ ] Polygon.io Starter    → $29/mo (real-time data, needed before live trading)
[ ] NewsAPI Business      → $449/mo OR find cheaper aggregator
[ ] GDELT BigQuery        → Set up free BigQuery project
```

---

## Integration Priority for the Engine

| Data Source | Domain | Feeds Into | Priority |
|-------------|--------|-----------|----------|
| Polymarket API | ALL | Spike detector, synthesis | ✅ Already using |
| Kalshi API | POL/ECO | Signal validation, Fed/election markets | 🔥 Next |
| FRED API | ECO | Synthesis context, macro base rates | 🔥 Next |
| yfinance | FIN/CRY/COM | Scenario tree asset prices | 🔥 This week |
| CoinGecko | CRY | Crypto price context | 🔥 This week |
| Guardian API | GEO/POL | News signal for synthesis | Week 2 |
| Manifold | TEC/LONG | Long-horizon cross-validation | Week 2 |
| GDELT | GEO | Conflict escalation signals | Month 2 |
| Polygon.io paid | FIN | Live trading signals | When profitable |

---

## Polymarket WebSocket — What We're Missing Right Now

The current spike detector polls every 30 minutes via REST. With WebSocket, we get:
- Price changes in real-time (sub-second)
- Orderbook depth updates
- Trade execution feed

This is the single highest-impact upgrade for the engine:
```python
# Real-time price stream — what we should add
import websocket, json

def on_message(ws, message):
    data = json.loads(message)
    if data.get("type") == "price_change":
        # Feed into spike detector threshold check
        check_spike(data["market_id"], data["price"], data["old_price"])

ws = websocket.WebSocketApp(
    "wss://ws-subscriptions-clob.polymarket.com/ws/market",
    on_message=on_message
)
ws.run_forever()
```

---

_This document is the data foundation. Every prediction synthesised, every scenario built, every trade decision made — all flow from these sources. Keep it current as new sources emerge._

---

## Layer 6: Betting Markets (sharp money signals)

### The Odds API ⭐ PRIMARY betting data
**What:** Real-time odds from 40+ bookmakers. Betfair, Bet365, DraftKings, FanDuel, William Hill.
**Key value:** Line movement tracking, multi-book divergence detection, political markets.
```
Base URL: https://api.the-odds-api.com/v4
Sports:   GET /v4/sports/?apiKey=KEY                    (free, unlimited)
Odds:     GET /v4/sports/{sport}/odds/?apiKey=KEY&regions=uk,eu&markets=h2h
Political: sport key = "politics" or "us_politics"
```
**Cost:** Free 500 req/month → $30/mo (20K) → $59/mo (100K)
**Register:** https://the-odds-api.com/#get-access
**Store:** `python3 tools/credentials.py store odds-api-key <key>`

### OddsPapi ⭐ PINNACLE DATA (free tier)
**What:** 348 bookmakers including **Pinnacle** (the sharpest book, closed direct API).
Historical line movement (opening → closing). Free for pre-match.
```
Base URL: https://api.oddspapi.io/v1
Free:     Pre-match odds, all 348 books, historical data
Paid:     WebSocket, sub-second latency (Pro tier)
```
**Cost:** Free tier covers 95% of use cases.
**Register:** https://oddspapi.io/
**Store:** `python3 tools/credentials.py store oddspapi-key <key>`

### Betfair Exchange 🏆 GOLD STANDARD (free for personal use)
**What:** Peer-to-peer betting exchange. The odds ARE the market consensus — no bookmaker
bias. Highest liquidity globally for major events. Political and world events markets.
**Value:** Streaming API, real volume data, no vig to remove.
```
API:     https://api.betfair.com/exchange/betting/rest/v1.0
Stream:  tcp://stream-api.betfair.com:443 (Betfair Exchange Streaming API)
Markets: Politics, elections, entertainment, sports
```
**Cost:** Free for personal use. Account required.
**Register:** betfair.com → My Account → API Keys
**Store:** `python3 tools/credentials.py store betfair-token <token>`

---

## Signal Extraction: What Line Movement Tells Us

```
Bookmaker hierarchy (sharpest → softest):
  Pinnacle > Betfair > Matchbook         ← SHARP BOOKS
  > Bet365 > William Hill > Ladbrokes    ← SOFT BOOKS
  > FanDuel > DraftKings > PointsBet     ← SQUARE/US BOOKS

STEAM MOVE (highest signal):
  Pinnacle + 3+ books move simultaneously within 30min
  → An informed bettor (syndicate/insider) acted. Something happened.
  
REVERSE LINE MOVEMENT:
  70%+ of public bets on Team A, but line moves toward Team A
  → Sharps disagree. Private information favors Team B.
  
DROPPING ODDS:
  Decimal odds drop >10% within 2 hours (e.g. 3.50 → 2.80)
  → Fast consensus forming. High-conviction prediction.
  
CROSS-MARKET SIGNAL:
  Betting prob = 65%, Polymarket = 52% → gap of 13pp
  → Either sharps know something, or one market is wrong.
  → Historical finding: for sports, betting > Polymarket accuracy.
                        for US politics, Polymarket often leads.
```

---

## Updated Acquisition Order (including betting)

### Register today (all free):
```
[ ] The Odds API key   → the-odds-api.com (free 500/mo)
[ ] OddsPapi key       → oddspapi.io (free tier, Pinnacle included)
[ ] Betfair account    → betfair.com (free personal use)
[ ] FRED API key       → fred.stlouisfed.org (free)
[ ] Guardian API key   → bonobo.capi.gutools.co.uk (free)
```

### Run once keys are in vault:
```bash
python3 engine/betting_signals.py scan          # political markets
python3 engine/betting_signals.py sport politics # political line movement
python3 engine/betting_signals.py divergence     # vs Polymarket gap
```
