# Whale Signal Research

*Research date: 2026-02-25 (updated)*
*Purpose: Identify profitable Polymarket wallets, tracking tools, and smart money infrastructure*
*Status: Registry populated (15 wallets, 4 confirmed GEO specialists), monitoring scaffolded, platforms surveyed*

---

## 1. The Profit Concentration Problem

From DefiOasis/ChainCatcher analysis of 1.73M Polymarket addresses and 95M on-chain transactions:

| Metric | Value |
|--------|-------|
| Traders with losses | 70% |
| Wallets with profit > $1,000 | 0.51% |
| Top 0.04% share of total profits | >70% ($3.7B) |
| Addresses with losses < $1,000 | 63.5% (1.1M addresses) |
| Addresses with losses > $1M | 149 |
| Only 7.6% of wallets profitable | ~120K making money vs 1.5M+ losing |
| Total nominal volume (2025) | $21.5B+ |

**The power law is extreme.** The profitable minority is small enough to track individually. Their on-chain activity is public. This is the S010 thesis.

---

## 2. Tracking Platforms (12 Identified)

### Tier 1 -- Primary Stack (Free, Active Feb 2026)

**PolyTrack** (polytrackhq.app) -- BEST FOR DOMAIN SPECIALIST DISCOVERY
- Cluster detection: identified Theo's 11 wallets as one entity
- Methods: temporal correlation, counterparty analysis, gas preferences, funding chains
- Entity linking is the standout feature -- no other free tool does this
- Category-based filtering: politics, sports, crypto, entertainment
- "Dev Picks" feature: pre-vetted whales meeting 60%+ win rate criteria
- Free (3 wallets tracked) / Pro $19/mo (unlimited)
- Webhook alerts available (usable as pseudo-API)
- Copy trading with "25ms execution" advertised
- Active and maintained in 2026 (blog posts dated 2026)

**HashDive** (hashdive.com) -- BEST FOR INDIVIDUAL WALLET SCORING
- Smart Score: rates traders -100 to +100 based on historical performance, open bets, consistency
- Methodology is proprietary ("secret sauce" -- treat as black-box signal)
- Covers both Polymarket AND Kalshi (unique)
- Market Screener: filter by liquidity, volume, whale activity, momentum
- Bot Detection feature
- Free for all core features; no API available
- Cannot search "top GEO wallets" -- must know wallet address first

**Polywhaler** (polywhaler.com) -- BEST FOR REAL-TIME ALERTS
- Real-time monitoring of $10K+ trades
- Insider score (0-100): unusual bet sizes, improbable outcomes, suspicious timing
- Trade impact scoring (High/Medium/Low)
- Market sentiment combining volume ratios + BTC/ETH/SPY/QQQ
- Free tier: real-time monitoring, sentiment, impact scoring, insider detection
- Pro $10/mo: API access, price predictions, advanced insider detection, portfolio tracking
- Categories: crypto, stocks, politics (no explicit GEO/ECO filter)

**PolyMonit** (polymonit.com)
- Low-noise alerts via Telegram/email
- Filterable by wallet address and trade size
- Best for: push notifications on registry wallets

### Tier 2 -- Supplementary

**Arkham Intelligence** (intel.arkm.com)
- Entity labeling -- identifies who's behind wallets
- Tags 800M+ addresses associated with 450K+ entities
- Polymarket entity page: intel.arkm.com/explorer/entity/polymarket
- Has API (requires authentication)
- Best for: deanonymizing new wallets; cross-referencing with polymarketanalytics.com

**Dune Analytics** -- Key Dashboards:
- `filarm/polymarket-activity` -- volume + activity metrics
- `genejp999/polymarket-leaderboard` -- trader rankings by P&L
- `rchen8/polymarket` -- general analytics
- `lujanodera/polymarket-analysis` -- deep analysis
- `dune/polymarket-capital-flows-and-users` -- official inflows/outflows
- Best for: custom SQL queries to identify domain-specialist wallets
- Limitation: dashboards require browser (JS-rendered, not scrapeable)

**Polymarket Analytics** (polymarketanalytics.com)
- Search/analyze all trades by any account
- Trader leaderboard: 1M+ traders, filter by P&L, win rate, position size
- Category filters: politics, crypto, sports
- Portfolio tracking across multiple wallets

### Tier 3 -- Specialized

**pselamy/polymarket-insider-tracker** (GitHub) -- BEST FOR FRONT-RUN DETECTION
- Self-hosted Python tool (60 commits, active development)
- Stack: Python 3.11+, PostgreSQL 15, Redis 7, Docker
- Detects: fresh wallets (<5 txns), unusual sizing (>2% of book), niche entries (<$50K volume)
- Uses DBSCAN clustering for related wallet detection
- Alerts: Discord, Telegram
- Flagged 5 alerts before a $442K insider trade in Jan 2026
- GEO/ECO relevance: niche market detection naturally surfaces these lower-volume domains

**NickNaskida/polymarket-insider-bot** (GitHub)
- Async Python alternative (2 commits, early stage, Jan 2026)
- Detection: fresh wallets (<30 days), unusual sizing (3x+ market average), high concentration (60%+)
- Scoring: 0-10 per trade for suspicious patterns
- Educational/research tool ("100% written by AI")

### Tier 4 -- Telegram Bots & Browser Extensions

| Tool | Free? | Key Feature |
|------|-------|-------------|
| Polylerts (Telegram) | Free (15 wallets) | Wallet tracking + analytical reports |
| PolyAlertHub (Telegram) | Freemium | AI analytics + email/Telegram alerts |
| PolyIntel (Telegram) | Free | 10-min automated alerts with scoring |
| PolySpy (Telegram) | Free | New market alerts with GEO/POL/TEC category filtering |
| Polymarket Whale Tracker (Chrome) | Free | Side panel, $10K-$100K threshold, 30-sec updates |
| Unusual Predictions (unusualwhales.com) | Unknown | Options flow platform extended to prediction markets |

### Ecosystem Scale

170+ tools across 19 categories as of Feb 2026. The Polymarket tooling space has exploded. Full directory at polymark.et.

---

## 3. Known Profitable Wallets

### GEO Specialists (CRITICAL GAP FILLED)

| Wallet | Address | Est. Profit | Win Rate | Domain | Follow Confidence |
|--------|---------|-------------|----------|--------|-------------------|
| ricosuave666 | `0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2` | $155K | 100% (Israel bets) | GEO (Israel/Iran) | 4/5 |
| denizz | `0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73` | $500K | Unknown | GEO (Middle East) | 4/5 |
| Cashy | `0x8f42ae0a01c0383c7ca8bd060b86a645ee74b88f` | Unknown | Unknown | GEO (Israel-based) | 3/5 |
| BuckMySalls | `0x509587cbb541251c74f261df3421f1fcc9fdc97c` | $920K | Unknown | GEO/POL | 3/5 |
| MEPP | `0x6d9fc316c3b8377060a44b852ba664adbfd59790` | Unknown | Unknown | POL/GEO | 2/5 |

**ricosuave666 is the standout.** 100% win rate on all Israel-related bets over 7 months. Went dormant, then reactivated Jan 2026 specifically for Iran strike bets. Two Israelis (IDF reservist + civilian) were separately charged with Polymarket insider trading (NPR, Feb 2026). This wallet is directly relevant to T001, T003, T005.

### POL Specialists

| Wallet | Address | Est. Profit | Win Rate | Follow Confidence |
|--------|---------|-------------|----------|-------------------|
| Theo4 | `0x56687bf447db6ffa42ffe2204a05edaa20f55839` | $22.05M | 72% | 5/5 |
| Fredi9999 | `0x1f2dd6d473f3e824cd2f8a89d9c69fb96f6ad0cf` | $16.62M | 72% | 5/5 |
| aenews2 | `0x44c1dfe43260c94ed4f1d00de2e1f80fb113ebc1` | $4.35M | 72.9% | 4/5 |
| YatSen | `0x5bffcf561bcae83af680ad600cb99f1184d6ffbe` | $2.21M | Unknown | 3/5 |
| debased | `0x24c8cf69a0e0a17eee21f69d29752bfa32e823e1` | $1.51M | 64.6% | 3/5 |
| scottilicious | `0x000d257d2dc7616feaef4ae0f14600fdf50a758e` | $1.35M | 84.1% | 4/5 |
| Kapii | `0xb74711992caf6d04fa55eecc46b8efc95311b050` | $1.01M | 60.2% | 3/5 |

**scottilicious is notable**: PhD Political Science, 84.1% win rate, "bond strategy" (enters late at >$0.70). His contradictions on POL markets deserve serious attention.

### TEC Specialists

| Wallet | Address | Est. Profit | Win Rate | Follow Confidence |
|--------|---------|-------------|----------|-------------------|
| AlphaRaccoon | `0xee50a31c3f5a7c77824b12a941a54388a2827ed6` | $1.36M | 96% | 4/5 |
| bamesjond | `0xe598435df0cdf5d22bdd5082d557f75f9180a0a8` | $500K | Unknown | 2/5 |
| LlamaEnjoyer | `0x9b979a065641e8cfde3022a30ed2d9415cf55e12` | $3.22M | Unknown | 2/5 |

**AlphaRaccoon address now confirmed**: `0xee50a31c3f5a7c77824b12a941a54388a2827ed6`. 22/23 on Google markets. $3M deposit, $1M profit in 24 hours. ROI 36.71%.

### ECO Specialists

| Wallet | Address | Est. Profit | Win Rate | Follow Confidence |
|--------|---------|-------------|----------|-------------------|
| crudeoilmoney | `0x27cb4e127fbfd433122ff801efc10954f33b169e` | Unknown | Unknown | 1/5 |

**Key finding**: No publicly identified ECO-specialist whales exist. This confirms participant-profiles.md assessment that ECO is "perfectly priced" with professional participants. Any wallet found consistently profitable in ECO would have exceptional edge and warrant high follow-confidence.

### Cross-Domain Generalists

| Wallet | Address | Est. Profit | Win Rate | Follow Confidence |
|--------|---------|-------------|----------|-------------------|
| Domer | `0x9d84ce0306f8551e02efef1680475fc0f1dc1344` | $2.6M+ | 63% | 5/5 |
| Whale-A | `0xd218e474776403a330142299f7796e8ba32eb5c9` | $958K | 67% | 3/5 |

### Iran-Specific Activity (Feb 2026)

| Wallet | Activity | Amount | Direction |
|--------|----------|--------|-----------|
| ricosuave666 | Reactivated Jan 2026 for Iran strikes | $155K+ | Unknown — needs live check |
| dfhgdhfthrfhr | Fresh wallet, single bet | $180K | NO on US-Iran strike by March 4, 2026 |
| 0xEFD06D1A | Fresh wallet, Iran bets only | $2,888 | Unknown |

**dfhgdhfthrfhr is directly relevant**: $180K bet AGAINST US-Iran strike by March 4. This aligns with S006 time-decay thesis (73.5% of "by date" markets resolve NO). If this is a fresh wallet making a single $180K contrarian bet, it could be insider signal or sophisticated S006 player.

---

## 4. The Theo Case Study

The most documented whale analysis in prediction markets:

- **Scale**: $85M profit across 11 accounts, $70M+ wagered
- **Confirmed addresses**: Theo4 (`0x5668...`), Fredi9999 (`0x1f2d...`). PrincessCaro ($6.08M, 8th all-time) and Michie addresses not independently confirmed.
- **Method**: Commissioned private polling through Selzer & Company
- **Timing**: Entered ~7 days before election day when private polls diverged from public
- **Market share**: Held 25% of Trump Electoral College contracts and 40%+ of Trump popular vote contracts
- **Detection**: PolyTrack cluster analysis identified all 11 accounts as one entity
- **Aftermath**: Identity revealed by WSJ. Trading volume decreased but accounts remain active.

**Lesson for S010**: Theo's on-chain flow was visible and identifiable before his identity was known. The 7-day entry window gave followers time to act.

**Anti-lesson**: zxgngl (one of Theo's accounts) lost $3.6M on Tyson vs. Paul. **Domain is the filter, not wallet address.**

---

## 5. Insider Trading Patterns

### Documented Cases

| Case | Amount | Pattern | Domain |
|------|--------|---------|--------|
| AlphaRaccoon (Google) | $1.36M | 22/23 correct on Google Year in Search | TEC |
| Venezuela/Maduro | $32K -> $400K+ | Single trade, hours before event | GEO/POL |
| Jan 2026 political event | $35K -> $442K (12.6x) | Fresh wallet, <5 prior txns | POL |
| Portugal election | $5M surge | Hours before exit polls | POL |
| ricosuave666 (Israel) | $155K | 100% win rate, 7-month dormancy then reactivation | GEO |
| Israeli traders (charged) | Unknown | IDF reservist + civilian charged Feb 2026 (NPR) | GEO |

### Detection Methodology (pselamy/polymarket-insider-tracker)

The tracker flags wallets matching ANY of:
1. **Fresh wallet**: <5 prior transactions on Polygon
2. **Unusual sizing**: Trade is >2% of the market's total order book
3. **Niche market**: Market has <$50K total volume
4. **Funding chain**: Wallet received USDC from a known exchange within 24h of first Polymarket trade

DBSCAN clustering then groups flagged wallets by temporal proximity and counterparty patterns.

### Front-Running Detection vs. S004

| Signal | S004 (Contrarian) | Front-Run Detection |
|--------|-------------------|---------------------|
| Price movement | Large (5pp+ spike) | Small (3-8% drift) |
| News catalyst | YES -- overreaction to news | NO -- no news explains movement |
| Volume | Above average | Below average |
| Action | Fade (go opposite direction) | Follow (go same direction) |
| Timing | After the move | During the drift |

---

## 6. Polymarket Contract Architecture

### On-Chain Settlement (Polygon Mainnet)

| Contract | Address | Purpose |
|----------|---------|---------|
| CTF Exchange | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` | Binary market settlement |
| Neg Risk CTF Exchange | `0xC5d563A36AE78145C45a50134d48A1215220f80a` | Multi-outcome market settlement |
| Neg Risk Adapter | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` | Convert NO shares across outcomes |
| Conditional Tokens | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` | ERC-1155 position tokens |
| USDC.e | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` | Collateral token |
| Proxy Wallet Factory | `0xaB45c5A4B0c941a2F231C04C3f49182e1A254052` | User wallet creation |

### Trade Detection Logic

To detect a Polymarket trade for a specific wallet:
1. Monitor USDC.e ERC-20 transfers FROM/TO the wallet
2. Filter to transfers involving CTF Exchange or Neg Risk CTF Exchange contracts
3. USDC leaving wallet -> buying shares (directional entry)
4. USDC entering wallet -> selling shares or receiving resolution payout
5. Decode CTF Exchange calldata for: token ID, amount, direction (YES/NO)

Token ID mapped to market question via Gamma API: `/markets?clob_token_ids=TOKEN_ID`

### Monitoring Approaches

**Polling** (implemented in whale-monitor.py):
- Polygonscan API `tokentx` endpoint for USDC.e transfers
- Poll every 5-15 minutes per wallet
- Free tier: 5 requests/second, sufficient for 15 wallets

**WebSocket** (for real-time):
- Alchemy or Infura WebSocket API on Polygon
- Subscribe to `Transfer` events filtered by whale addresses
- Latency: sub-second
- Cost: Alchemy free tier may suffice

**External platforms** (recommended for daily use):
- PolyTrack webhooks for wallet alerts (free, 3 wallets)
- Polywhaler for $10K+ trade alerts (free)
- PolyMonit for Telegram push notifications (free)

---

## 7. Wash Trading Contamination

Columbia University study (2025) estimates 25% of Polymarket volume may be artificial:

| Period | Wash Trading % |
|--------|---------------|
| Peak weeks (Dec 2024) | Up to 60% |
| Election markets peak | Up to 95% in one week |
| Sports markets (historical avg) | 45% |
| Election markets (overall avg) | 17% |
| Flagged wallets | 14% of 1.26M total |

**Implication for S010**: Whale trades must be cross-referenced against wash trading patterns. Use PolyTrack cluster detection and HashDive bot detection to distinguish genuine directional trades from coordinated wash activity.

---

## 8. Implications for Open Positions

### Current Portfolio (T001-T008)

Our open positions are concentrated in GEO (4/7 trades) and POL (2/7). The most actionable whale signals:

1. **ricosuave666** (`0x0afc...`) — 100% Israel bet win rate. Reactivated Jan 2026 for Iran strike markets. Directly relevant to T001, T003, T005. **If this wallet enters new GEO positions, classify as Type E and investigate immediately.**

2. **denizz** (`0xbaa2...`) — Middle East specialist, community-recommended. Monitor for Iran/ceasefire market entries. Relevant to T001, T003, T005.

3. **dfhgdhfthrfhr** — Fresh wallet, $180K AGAINST US-Iran strike by March 4, 2026. Aligns with S006 thesis. Either sophisticated S006 player or insider signal.

4. **Theo4/Fredi9999** (`0x5668...`, `0x1f2d...`) — Monitor for 2028 political market entries. Relevant to T002, T006.

5. **Domer** (`0x9d84...`) — Cross-domain generalist. Worth monitoring as general signal on any market.

### Action Items

1. **IMMEDIATE**: Run whale-monitor.py with `--hours 168` (7 days) to check recent activity from confirmed GEO specialist wallets
2. **IMMEDIATE**: Set up PolyTrack free tier — track ricosuave666, denizz, Cashy (3 wallet limit on free)
3. **THIS WEEK**: Set up Polywhaler alerts for >$10K trades on Iran strike, 2028 GOP nomination, BTC $150K markets
4. **THIS WEEK**: Check ricosuave666 current positions on polymarket.com/profile/0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2
5. **THIS WEEK**: Check dfhgdhfthrfhr $180K Iran bet status — if still active and market hasn't moved, this is S006 confirmation
6. **ONGOING**: Run whale-monitor.py daily to build activity baseline
7. **ONGOING**: Quarterly registry review — update wallet P&L and follow-confidence scores

---

## Sources

### Academic & Industry Reports
1. DefiOasis/ChainCatcher (2025). Profit concentration study: 95M transactions, 1.73M addresses.
2. Columbia University (2025). Wash trading study: 25% of volume may be artificial.
3. Clinton & Huang (2025). Prediction market accuracy and efficiency: $2.4B analyzed.

### Wallet Research
4. [PANews: How to Build Your Smart Money Address Library](https://www.panewslab.com/en/articles/019c7f59-d7e0-773b-82a4-e755ef21dfca) -- richest single source, 30+ wallet addresses
5. [Odaily: Complete Guide to Finding and Following Smart Money](https://www.odaily.news/en/post/5207604) -- sector breakdowns
6. [Stand.trade: Three US Elections Traders](https://news.stand.trade/p/three-us-elections-polymarket-traders) -- scottilicious, Kapii, aenews2, debased
7. [Phemex: Top 10 Profitable Wallets](https://phemex.com/news/article/top-10-polymarket-wallets-profit-from-hype-markets-54536) -- 0xd218, 0xee61
8. [Dyutam: Israel-Iran Insider Trading Wallets](https://dyutam.com/news/polymarket-israel-iran-conflict-insider-trading/) -- ricosuave666, 0xEFD0
9. [Yahoo Finance: AlphaRaccoon / Google Insider](https://finance.yahoo.com/news/polymarket-trader-makes-1-million-090001027.html)
10. [CNBC: French Trader 4 Accounts](https://www.cnbc.com/2024/10/24/polymarket-trump-french-election-bet.html) -- Theo cluster
11. [Entrepreneur: Theo $85M](https://www.entrepreneur.com/business-news/how-trump-whale-theo-made-48-million-neighbor-effect/482539)
12. [NPR: Israelis Charged with Polymarket Insider Trading](https://www.npr.org/2026/02/12/nx-s1-5712801/polymarket-bets-traders-israel-military) -- Feb 2026
13. [Phemex: $180K Against Iran Strike](https://phemex.com/news/article/new-polymarket-wallet-bets-180k-against-us-strike-on-iran-62626)

### Tracking Platforms
14. PolyTrack: https://polytrackhq.app (cluster detection, category filtering, webhooks)
15. HashDive: https://hashdive.com (Smart Scores -100 to +100, Kalshi coverage)
16. Polywhaler: https://polywhaler.com ($10K+ alerts, insider score 0-100, Pro API $10/mo)
17. PolyMonit: https://polymonit.com (Telegram/email alerts)
18. Arkham Intelligence: https://intel.arkm.com/explorer/entity/polymarket (800M+ tagged addresses)
19. Polymarket Analytics: https://polymarketanalytics.com/traders (1M+ traders searchable)
20. Unusual Whales Predictions: https://unusualwhales.com/predictions

### Dune Dashboards
21. filarm/polymarket-activity
22. genejp999/polymarket-leaderboard
23. rchen8/polymarket
24. lujanodera/polymarket-analysis
25. dune/polymarket-capital-flows-and-users

### Open Source Tools
26. pselamy/polymarket-insider-tracker (GitHub) -- 60 commits, Docker, DBSCAN
27. NickNaskida/polymarket-insider-bot (GitHub) -- async alternative
28. harish-garg/Awesome-Polymarket-Tools (GitHub) -- ecosystem directory (170+ tools)
