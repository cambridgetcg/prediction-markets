# Polymarket Whale Tracking & Smart Money Research

> Compiled: 2026-02-25
> Status: Initial research sweep

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Dune Analytics Dashboards](#dune-analytics-dashboards)
3. [Dedicated Tracking Platforms](#dedicated-tracking-platforms)
4. [On-Chain Analysis Studies](#on-chain-analysis-studies)
5. [Known Wallet Addresses](#known-wallet-addresses)
6. [Polymarket Contract Addresses](#polymarket-contract-addresses)
7. [Insider Trading Detection](#insider-trading-detection)
8. [Named Profitable Traders](#named-profitable-traders)
9. [Actionable Takeaways](#actionable-takeaways)

---

## Executive Summary

The Polymarket whale-tracking ecosystem is surprisingly mature, with 170+ third-party tools across 19 categories. Key findings:

- **70% of Polymarket traders lose money** (DefiOasis study, Dec 2025)
- **Top 0.04% of addresses captured $3.7B** in realized profits
- **Only 0.51% of wallets** achieved profits exceeding $1,000
- **$40M+ extracted by arbitrageurs** (Apr 2024 - Apr 2025), top 3 wallets alone: $4.2M
- **95 million transactions** processed in 2025, $21.5B nominal volume
- Polymarket treats insider trading as a feature ("insiders having an edge is a good thing" -- CEO Shayne Coplan)

---

## Dune Analytics Dashboards

### 1. Polymarket 2025: Capital & Whales (thxshogun)
- **URL**: https://dune.com/thxshogun/polymarket-2025-capital-and-whales
- **Data**: Whale wallet identification, capital flows, position sizing
- **Status**: Active (2025 data)
- **Best for**: Identifying large wallets and capital concentration

### 2. Polymarket Leaderboard (genejp999)
- **URL**: https://dune.com/genejp999/polymarket-leaderboard
- **Data**: Trader rankings by P&L, volume, win rate
- **Status**: Active
- **Best for**: Finding consistently profitable wallets

### 3. Polymarket Activity and Volume (filarm)
- **URL**: https://dune.com/filarm/polymarket-activity
- **Data**: Platform-wide activity metrics, volume trends, user counts
- **Status**: Active
- **Best for**: Macro view of platform activity

### 4. Polymarket (rchen8)
- **URL**: https://dune.com/rchen8/polymarket
- **Data**: General Polymarket analytics
- **Status**: Active
- **Best for**: Overview metrics

### 5. Polymarket Trade Activity Tracker (0xclark_kent)
- **URL**: https://dune.com/0xclark_kent/polymarket-trade-activity-tracker
- **Data**: Individual trade-level tracking
- **Status**: Active
- **Best for**: Granular trade analysis

### 6. Polymarket CLOB Stats (lifewillbeokay)
- **URL**: https://dune.com/lifewillbeokay/polymarket-clob-stats
- **Data**: Order book statistics, maker/taker analysis
- **Status**: Active
- **Best for**: Understanding market microstructure

### 7. Polymarket on Polygon (petertherock)
- **URL**: https://dune.com/petertherock/polymarket-on-polygon
- **Data**: Polygon-level transaction analysis
- **Status**: Active
- **Best for**: On-chain settlement analysis

### 8. Polymarket Analysis (lujanodera)
- **URL**: https://dune.com/lujanodera/polymarket-analysis
- **Data**: General analytical dashboard
- **Status**: Active

### 9. Polymarket Overview (datadashboards)
- **URL**: https://dune.com/datadashboards/polymarket-overview
- **Data**: High-level platform metrics
- **Status**: Active

### 10. Polymarket Address Tracker / Airdrop Eligibility (seoul)
- **URL**: https://dune.com/seoul/poly
- **Data**: Address-level activity tracking, potential airdrop eligibility
- **Status**: Active
- **Best for**: Tracking specific wallet activity

### 11. Prediction Markets (datadashboards)
- **URL**: https://dune.com/datadashboards/prediction-markets
- **Data**: Cross-platform comparison (Polymarket, Kalshi, Limitless, Myriad)
- **Status**: Active
- **Best for**: Cross-platform analysis

### 12. Polymarket Trading Volume (genejp999)
- **URL**: https://dune.com/genejp999/polymarket-trading-volume
- **Data**: Volume analytics
- **Status**: Active

---

## Dedicated Tracking Platforms

### 1. HashDive
- **URL**: https://www.hashdive.com/
- **Twitter**: https://x.com/hash_dive
- **Status**: ACTIVE
- **Key Feature**: Smart Score (-100 to +100)
  - Proprietary metric rating traders based on historical performance, open bets, consistency
  - Formula is secret ("secret sauce")
  - Projection feature shows where score might land if all positions closed today
- **Other Features**:
  - Market Screener: filter by liquidity, volume, whale activity, momentum
  - Wallet & Position Tracking: smart-money flow visibility
  - Charts: candlesticks with RSI, MACD, SMA, whale volume breakdowns, buyer/seller counts
  - Top 20 Markets view ordered by liquidity and volume
  - Human vs AI-calculated probability comparison
  - Individual Polygon address lookup
- **Pricing**: Not publicly disclosed
- **Best for**: Evaluating trader skill before copy-trading

### 2. PolyTrack
- **URL**: https://www.polytrackhq.app/
- **Status**: ACTIVE (regularly publishing blog content through 2026)
- **Key Feature**: Cluster Detection
  - Identifies related wallets controlled by same entity
  - Methods: temporal trading correlation (seconds/minutes), counterparty analysis, gas price preferences, funding chain analysis (round numbers from same source)
  - Example: identified Theo's 11 wallets as one whale
- **Other Features**:
  - Leaderboards, whale profiles, real-time alerts
  - Copy trading bot tutorials
  - Insider trading detection guides
- **Pricing**: Core features (leaderboards, whale profiles, cluster detection, alerts) are FREE
- **Best for**: Seeing through multi-wallet obfuscation

### 3. Polywhaler
- **URL**: https://www.polywhaler.com/
- **Status**: ACTIVE
- **Key Features**:
  - Real-time monitoring of $10K+ trades
  - Market sentiment analysis
  - Insider activity detection
  - AI-powered predictions
- **Best for**: Real-time large trade alerts

### 4. PolyMonit
- **URL**: https://polymonit.com/
- **Status**: ACTIVE
- **Key Features**:
  - Live feed of wallet activity
  - Whale watch
  - Smart alerts (routed by wallet and trade size)
  - Wallet discovery, search, favorites
  - Telegram and email alerts
- **Best for**: Low-noise targeted alerts

### 5. PolymarketScan
- **URL**: https://polymarketscan.org/whales
- **Status**: ACTIVE
- **Key Features**:
  - Whale page with large position tracking
  - Market and data explorer
  - Free real-time analytics
- **Best for**: Quick whale overview

### 6. Polymarket Analytics
- **URL**: https://polymarketanalytics.com/
- **Status**: ACTIVE
- **Key Features**:
  - Traders leaderboard with P&L, positions, wins & losses
  - Filter/analyze 1M+ Polymarket traders
  - Market data and dashboards
- **Best for**: Comprehensive leaderboard analysis

### 7. Polydupe
- **URL**: https://polydupe.com/traders
- **Status**: ACTIVE
- **Key Features**:
  - Polymarket leaderboard sorted by top P&L traders
- **Best for**: Quick leaderboard check

### 8. PolyWallet
- **URL**: https://polymark.et/product/polywallet
- **Status**: ACTIVE
- **Key Features**:
  - Deep wallet analysis
  - Transaction tracking
- **Best for**: Individual wallet deep-dives

### 9. PolyxBot
- **URL**: Telegram bot
- **Status**: ACTIVE
- **Key Features**:
  - PLX Score combining quantitative data (orderbook depth, liquidity, spread, volume) with qualitative sentiment (news, social narratives, historical patterns)
  - AI-powered market rating
  - Whale alerts via Telegram
- **Best for**: Telegram-native whale alerts

### 10. Polymarket Whale Tracker (Chrome Extension)
- **URL**: https://chromewebstore.google.com/detail/polymarket-whale-tracker/onhhaghaecempnnodenjjlhkobgpkkfj
- **Status**: ACTIVE
- **Best for**: In-browser whale monitoring while browsing Polymarket

### 11. Arkham Intelligence
- **URL**: https://intel.arkm.com/explorer/entity/polymarket
- **Status**: ACTIVE
- **Key Features**:
  - Entity labeling (identifies wallets belonging to firms, influencers, etc.)
  - Polymarket entity page with holdings, wallets, inflows, outflows, counterparties
  - KOL tracking tag (950+ addresses as of Mar 2025)
  - Wallet clustering via AI/deanonymization
- **Best for**: Identifying the real-world entities behind wallets

### 12. Unusual Whales (Predictions)
- **URL**: https://unusualwhales.com/predictions
- **Status**: ACTIVE
- **Best for**: Cross-asset unusual activity (stocks + prediction markets)

---

## On-Chain Analysis Studies

### DefiOasis Study (December 2025)
- **Subject**: Profit concentration across 1,733,785 unique trading addresses
- **Key Findings**:
  - 70% of addresses have negative realized returns
  - Top 0.04% captured $3.7B (70%+ of total realized profits)
  - 24.56% of addresses earned $0-$1,000 (only 0.86% of total profits)
  - 63.5% of addresses lost $0-$1,000
  - Only 0.51% exceeded $1,000 in profit
- **Implication**: Polymarket is a zero-sum winner-takes-all environment. Retail traders are net donors.
- **Sources**: [CryptoNews](https://cryptonews.com/news/70-of-polymarket-traders-lost-money-as-top-0-04-captured-most-profits-research/), [Blockonomi](https://blockonomi.com/polymarket-data-reveals-70-trading-loss-rate-as-top-0-04-capture-3-7b-in-profits/)

### ChainCatcher/Odaily "Six Profit Models" Report (2025)
- **Subject**: Analysis of 95M transactions (Apr 2024 - Dec 2025), $21.5B nominal volume
- **Six Verified Profitable Strategies**:

| Strategy | Key Metrics | Example |
|----------|------------|---------|
| **1. Information Arbitrage** | $85M return (Theo) on ~$100K research investment | "Neighbor effect" polling |
| **2. Cross-Platform Arbitrage** | $40M+ extracted, top 3 wallets = $4.2M | BTC priced YES $0.45 on Poly, NO $0.48 on Kalshi = 7.5% risk-free |
| **3. High-Probability Bond** | Up to 1,800% annualized | Buy 95c+ YES shares near expiry |
| **4. Liquidity Provision** | 80-200% annualized, $700-800/day peak | Market making on new markets |
| **5. Domain Specialization** | $1.4M (HyperLiquid0xb), 96% win rate (Mention) | Deep expertise in one vertical |
| **6. Speed Trading** | $4.2M total across top algo traders (10,200+ trades) | Algorithmic execution |

- **Sources**: [ChainCatcher](https://www.chaincatcher.com/en/article/2233047), [Odaily](https://www.odaily.news/en/post/5208434), [PANews](https://www.panewslab.com/en/articles/c1772590-4a84-46c0-87e2-4e83bb5c8ad9)

---

## Known Wallet Addresses

### Confirmed Addresses

| Wallet | Address | P&L | Win Rate | Notes |
|--------|---------|-----|----------|-------|
| **Domer** (#1 all-time) | `0x9d84ce0306f8551e02efef1680475fc0f1dc1344` | $2.6M+ (30d), ~$10M+ all-time (est.) | 63% | 5000+ markets, ~$300M volume, manual trader |
| **Unnamed Whale A** | `0xd218e474776403a330142299f7796e8ba32eb5c9` | $900K-$958K | 65-67% | Consistent across hype markets |
| **Unnamed Whale B** | `0xee613b3fc183ee44f9da9c05f53e2da107e3debf` | $1.34M (7d) | 52% | $1.4M 7d volume, high turnover |
| **AlphaRaccoon (suspected Google insider)** | `0xafEe...` (partial) | ~$1M (24h on Google search markets) + $150K (Gemini 3.0 Flash date) | 96% (22/23) | $3M deposited, flagged by Meta engineer Jeong Haeju |

### Theo (French Whale) -- Multiple Accounts

Theo controlled **at least 11 accounts** (WSJ investigation, Chainalysis wallet clustering):

| Account Name | Wallet Address | Notes |
|--------------|---------------|-------|
| **Fredi9999** | Not publicly indexed | $16.47M profit from election alone |
| **Theo4** | `0x5668...` (partial, from one source) | One of the primary accounts |
| **PrincessCaro** | Not publicly indexed | Cover account created Sep/Oct 2024 |
| **zxgngl** | Not publicly indexed | Held 25% of Trump Electoral College contracts, 40%+ of popular vote contracts |
| **Michie** | Not publicly indexed | Cover account |
| **(6 more unnamed)** | Unknown | Total: 11 accounts, $70M+ wagered, $85M profit |

**Strategy**: Spread trades over days. Mixed large ($4,302) with small ($0.30-$187) orders. 1,600+ trades in 24h during peaks. Created additional accounts when market makers stopped quoting when Fredi9999 was buying.

### Other Named Profitable Traders (addresses not publicly confirmed)

| Username | Profit | Win Rate | Specialization |
|----------|--------|----------|----------------|
| **HyperLiquid0xb** | $1.4M total | Not listed | Sports (largest: $755K baseball) |
| **Mention / Axios** | Not listed | 96% | Political speech analysis |
| **WindWalk3** | $1.1M+ | Not listed | RFK Jr. predictions |
| **Erasmus** | $1.3M+ | Not listed | Political markets (largest: $95K) |
| **1j59y6nk** | $1.4M | Not listed | Sports/games (largest: $90K football) |
| **SeriouslySirius** | Unknown (notable $440K single loss) | Not listed | Unknown |
| **@defiance_cr** | $700-800/day peak | Not listed | LP / domain spec, started with $10K |

---

## Polymarket Contract Addresses (Polygon Mainnet, Chain ID 137)

Source: [Official Polymarket Documentation](https://docs.polymarket.com/resources/contract-addresses)

### Core Trading Contracts
| Contract | Address |
|----------|---------|
| **CTF Exchange** | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` |
| **Neg Risk CTF Exchange** | `0xC5d563A36AE78145C45a50134d48A1215220f80a` |
| **Neg Risk Adapter** | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` |
| **Conditional Tokens (CTF)** | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` |

### Token Contracts
| Contract | Address |
|----------|---------|
| **USDC.e (Bridged)** | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` |
| **Native USDC** | `0x3c499c542cef5e3811e1192ce70d8cc03d5c3359` |

### Wallet Factory Contracts
| Contract | Address |
|----------|---------|
| **Gnosis Safe Factory** | `0xaacfeea03eb1561c4e67d661e40682bd20e3541b` |
| **Proxy Wallet Factory** | `0xaB45c5A4B0c941a2F231C04C3f49182e1A254052` |

### Resolution Contracts
| Contract | Address |
|----------|---------|
| **UMA Adapter** | `0x6A9D222616C90FcA5754cd1333cFD9b7fb6a4F74` |
| **UMA Optimistic Oracle** | `0xCB1822859cEF82Cd2Eb4E6276C7916e692995130` |

### Liquidity
| Contract | Address |
|----------|---------|
| **Uniswap v3 USDC.e/USDC Pool** | `0xd36ec33c8bed5a9f7b6630855f1533455b98a418` |

### How Trading Works On-Chain
- Binary markets: settled through **CTF Exchange** (`0x4bFb...`)
- Multi-outcome (neg risk) markets: settled through **Neg Risk CTF Exchange** (`0xC5d5...`)
- All trades use **USDC.e** as collateral on Polygon
- Each user has a **proxy wallet** (Gnosis Safe) deployed via the factory contracts
- The CLOB API endpoint is `https://clob.polymarket.com` (Chain ID 137)

---

## Insider Trading Detection

### Tools

#### 1. pselamy/polymarket-insider-tracker (Open Source)
- **URL**: https://github.com/pselamy/polymarket-insider-tracker
- **Status**: ACTIVE
- **Detection Signals**:
  1. **Fresh Wallets**: <5 lifetime transactions making $1,000+ trades
  2. **Unusual Sizing**: Trades consuming >2% of visible order book depth
  3. **Niche Markets**: Activity in <$50K daily volume markets
  4. **Funding Chains**: Tracing capital origins to link seemingly unrelated accounts
- **Technical Architecture**:
  - Data ingestion from Polymarket CLOB API + Polygon RPC
  - Wallet profiling via Polygon node history analysis
  - DBSCAN clustering for coordinated activity patterns
  - Multi-channel alerts (Discord, Telegram, Email)
  - Correlates trading timing with external news (1-4h windows)
- **Real Example**: Jan 2026 -- wallet turned $35K into $442K (12.6x) hours before a major market move. Tool flagged 5 alerts before event.

#### 2. NickNaskida/polymarket-insider-bot (Open Source)
- **URL**: https://github.com/NickNaskida/polymarket-insider-bot
- **Status**: ACTIVE
- **Description**: High-performance async bot for insider detection

#### 3. Polywhaler Insider Detection
- **URL**: https://www.polywhaler.com/
- **Status**: ACTIVE (built into Polywhaler platform)

### Notable Insider Trading Cases

| Date | Trader | Details | Outcome |
|------|--------|---------|---------|
| Dec 2025 | AlphaRaccoon (`0xafEe...`) | 22/23 on Google Year in Search bets | ~$1M profit, alleged Google insider |
| Jan 2026 | Anonymous | $32K on Maduro downfall hours before Trump announced capture | $400K+ profit |
| Jan 2026 | Anonymous | $35K position hours before major political event | $442K (12.6x), flagged by pselamy tool |
| 2024 | AlphaRaccoon | Predicted exact Gemini 3.0 Flash release date | $150K profit |

### Polymarket's Stance
- CEO Shayne Coplan: "insiders having an edge on the market is a good thing"
- Platform views informed trading as improving market efficiency
- CFTC approval (Dec 2025) brought stock-market-style surveillance and position limits
- ZachXBT insider trading expose (Feb 26, 2026) drew $3M in volume on prediction of which crypto firm would be exposed

---

## Named Profitable Traders (Detailed Profiles)

### Tier 1: $10M+

**Theo (French Whale)**
- Profit: ~$85M (2024 election)
- Strategy: Information arbitrage via proprietary "neighbor effect" polling methodology
- Invested ~$100K in polling research, wagered $70M+ across 11 accounts
- Accounts: Fredi9999, Theo4, PrincessCaro, zxgngl, Michie, +6 unknown
- Key address: Fredi9999 alone = $16.47M profit
- Now: France investigating Polymarket; French users blocked; ANJ ban 2025

### Tier 2: $1-10M

**Domer**
- Address: `0x9d84ce0306f8551e02efef1680475fc0f1dc1344`
- Profit: $2.6M+ (recent 30d), estimated $10M+ all-time
- Volume: ~$300M total across 5,000+ markets
- Win Rate: 63%
- Strategy: Manual; starts with gut feeling for small bets, then deep research for scaling. Consults subject matter experts. Views markets as "slow motion poker hands."
- Philosophy: "Bet in accordance with your edge. If you don't find an edge, don't bet."

**Erasmus**
- Profit: $1.3M+
- Specialization: Political markets
- Largest single win: $95K

**1j59y6nk**
- Profit: ~$1.4M
- Specialization: Games and sports
- Largest single win: $90K (football)

**HyperLiquid0xb**
- Profit: $1.4M total
- Specialization: Sports markets
- Largest single win: $755K (baseball prediction)

**WindWalk3**
- Profit: $1.1M+
- Specialization: RFK Jr. predictions

### Tier 3: Methodology Notable

**Mention / Axios**
- Win Rate: 96%
- Specialization: Political speech analysis
- Notable for: Extremely high win rate with domain-specific methodology

**@defiance_cr**
- Peak Daily: $700-800
- Starting Capital: $10K
- Specialization: Liquidity provision

---

## Actionable Takeaways

### For Our Trading Operation

1. **Copy-trading infrastructure**: The tools exist to follow profitable wallets in real-time. Key targets:
   - Domer (`0x9d84...1344`) -- the most accessible high-performer with confirmed address
   - `0xee61...debf` -- high-turnover whale, 52% win rate but massive volume
   - `0xd218...eb5c9` -- consistent 65-67% win rate

2. **Cluster detection matters**: Theo hid $70M+ across 11 wallets. Any whale analysis that doesn't account for clustering will undercount true conviction.

3. **Insider signal is real and exploitable**: The pselamy tool flagged 5 alerts before the $442K insider trade. Even without copying insiders, monitoring for fresh-wallet+large-size+niche-market signals could provide actionable intelligence.

4. **Best free tool stack**:
   - **PolyTrack** (cluster detection + leaderboards + alerts) -- free
   - **HashDive** (Smart Score for evaluating traders) -- pricing unknown
   - **Dune: thxshogun dashboard** (whale capital flows) -- free
   - **Dune: genejp999 leaderboard** (P&L rankings) -- free
   - **Arkham Intelligence** (entity identification) -- free tier available
   - **pselamy/polymarket-insider-tracker** (insider detection) -- open source

5. **Strategy fit with our playbooks**:
   - S004 (Contrarian Overreaction): whale exits/entries could confirm reversion signals
   - S007 (Cross-Market Arb): cross-platform arb is a verified $40M+ strategy
   - S006 (Time Decay): high-probability bond strategy (1,800% annualized) is essentially our time-decay approach at the extreme

6. **Next steps**:
   - [ ] Set up PolyTrack alerts for Domer and top 5 whale wallets
   - [ ] Deploy pselamy insider tracker (or fork it) for fresh-wallet monitoring
   - [ ] Build Dune query to track whale flow into our target domains (POL, GEO, TEC)
   - [ ] Cross-reference HashDive Smart Scores with our screener output
   - [ ] Monitor Arkham entity labels for institutional Polymarket activity

---

## Sources

### Dune Dashboards
- [Polymarket 2025: Capital & Whales](https://dune.com/thxshogun/polymarket-2025-capital-and-whales)
- [Polymarket Leaderboard](https://dune.com/genejp999/polymarket-leaderboard)
- [Polymarket Activity & Volume](https://dune.com/filarm/polymarket-activity)
- [Polymarket (rchen8)](https://dune.com/rchen8/polymarket)
- [Polymarket Trade Activity Tracker](https://dune.com/0xclark_kent/polymarket-trade-activity-tracker)
- [Polymarket CLOB Stats](https://dune.com/lifewillbeokay/polymarket-clob-stats)
- [Polymarket on Polygon](https://dune.com/petertherock/polymarket-on-polygon)
- [Polymarket Analysis](https://dune.com/lujanodera/polymarket-analysis)
- [Polymarket Overview](https://dune.com/datadashboards/polymarket-overview)
- [Polymarket Address Tracker](https://dune.com/seoul/poly)
- [Prediction Markets Dashboard](https://dune.com/datadashboards/prediction-markets)
- [Polymarket Trading Volume](https://dune.com/genejp999/polymarket-trading-volume)

### Tracking Platforms
- [HashDive](https://www.hashdive.com/) | [Twitter](https://x.com/hash_dive)
- [PolyTrack](https://www.polytrackhq.app/)
- [Polywhaler](https://www.polywhaler.com/)
- [PolyMonit](https://polymonit.com/)
- [PolymarketScan](https://polymarketscan.org/whales)
- [Polymarket Analytics](https://polymarketanalytics.com/)
- [Polydupe](https://polydupe.com/traders)
- [Arkham Intelligence - Polymarket](https://intel.arkm.com/explorer/entity/polymarket)
- [Unusual Whales Predictions](https://unusualwhales.com/predictions)

### Research & Analysis
- [DefiOasis Profit Concentration Study (CryptoNews)](https://cryptonews.com/news/70-of-polymarket-traders-lost-money-as-top-0-04-captured-most-profits-research/)
- [DefiOasis Study (Blockonomi)](https://blockonomi.com/polymarket-data-reveals-70-trading-loss-rate-as-top-0-04-capture-3-7b-in-profits/)
- [Six Profit Models Report (ChainCatcher)](https://www.chaincatcher.com/en/article/2233047)
- [Six Profit Models Report (Odaily)](https://www.odaily.news/en/post/5208434)
- [Six Profit Models Report (PANews)](https://www.panewslab.com/en/articles/c1772590-4a84-46c0-87e2-4e83bb5c8ad9)
- [Top 10 Profitable Wallets (Phemex)](https://phemex.com/news/article/top-10-polymarket-wallets-profit-from-hype-markets-54536)
- [Top 10 Consistent Wallets (Phemex)](https://phemex.com/news/article/top-10-polymarket-wallets-identified-for-consistent-profits-in-hype-markets-52633)

### Insider Trading
- [pselamy/polymarket-insider-tracker (GitHub)](https://github.com/pselamy/polymarket-insider-tracker)
- [NickNaskida/polymarket-insider-bot (GitHub)](https://github.com/NickNaskida/polymarket-insider-bot)
- [Insider Trading Cases (BitcoinChaser)](https://bitcoinchaser.com/cases-insider-trading-polymarket/)
- [AlphaRaccoon Google Insider (BeInCrypto)](https://beincrypto.com/alleged-google-insider-trade-polymarket/)
- [Insider Trading Regulation Analysis](https://philippdubach.com/posts/the-absolute-insider-mess-of-prediction-markets/)

### Theo / French Whale
- [French Whale Case Study (PolyTrack)](https://www.polytrackhq.app/blog/polymarket-french-whale-case-study)
- [How French Whale Made $85M (The Free Press)](https://www.thefp.com/p/french-whale-makes-85-million-on-polymarket-trump-win)
- [French Whale WSJ Report (CBS/60 Minutes)](https://www.cbsnews.com/news/french-whale-made-over-80-million-on-polymarket-betting-on-trump-election-win-60-minutes/)
- [Domer Interview (OnChain Times)](https://www.onchaintimes.com/a-chat-with-domer-the-1-trader-on-polymarket/)

### Official Documentation
- [Polymarket Contract Addresses](https://docs.polymarket.com/resources/contract-addresses)
- [Polymarket CLOB Quickstart](https://docs.polymarket.com/developers/CLOB/quickstart)
- [Polymarket Proxy Wallet](https://docs.polymarket.com/developers/proxy-wallet)
- [CTF Exchange GitHub](https://github.com/Polymarket/ctf-exchange)
- [Neg Risk Adapter GitHub](https://github.com/Polymarket/neg-risk-ctf-adapter)

### Ecosystem Overviews
- [170+ Tools Guide (DeFi Prime)](https://defiprime.com/definitive-guide-to-the-polymarket-ecosystem)
- [Ecosystem Guide (MEXC)](https://www.mexc.co/news/457778)
- [Top 10 Analytics Tools (CoinCodeCap)](https://signals.coincodecap.com/top-polymarket-analytics-tools)
- [Awesome Polymarket Tools (GitHub)](https://github.com/harish-garg/Awesome-Polymarket-Tools)
- [On-Chain Order Data Analysis (Zichao Yang)](https://yzc.me/x01Crypto/decoding-polymarket)
