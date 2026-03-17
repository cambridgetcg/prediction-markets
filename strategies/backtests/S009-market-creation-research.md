# S009 Market Creation Mechanics Research

> Date: 2026-02-25
> Status: Research complete
> Sources: Polymarket docs, Gamma API live testing, web research

---

## Q1: Who Creates Markets? (Centralized Curation)

**Answer: Polymarket operates a fully centralized curation model.**

Markets are created exclusively by Polymarket's internal "markets team" with community input. Users CANNOT create markets directly.

### Submission channels:
- Discord `#market-suggestion` channel
- Twitter/X by tagging @polymarket

### Submission requirements:
- Market title
- Resolution source (how outcome will be determined)
- Evidence of trading demand

### Implications:
- **Human bottleneck** — Polymarket operates more like a media company than a protocol
- No permissionless market creation (unlike Augur v2, Azuro, SX Bet)
- Editorial judgment determines what gets listed
- This means **speed-to-market on breaking events** depends on Polymarket's team noticing or being alerted
- Community can influence what gets listed but cannot bypass the curation layer

### Source:
- [How Are Markets Created? — Polymarket Help Center](https://help.polymarket.com/en/articles/13364541-how-are-markets-created)
- [Landscape of Prediction Markets: Centralization vs. Permissionless — BeInCrypto](https://beincrypto.com/landscape-of-prediction-markets-centralization-vs-permissionless-protocols/)

---

## Q2: How Initial Prices Are Set

**Answer: No default price. Pure order-book price discovery by market makers.**

### Mechanism:
1. When a market is created, there are **zero shares and no prices**
2. Market makers post limit orders for YES and NO sides
3. When a YES bid + NO bid = $1.00, the system mints 1 YES + 1 NO share
4. The first matched orders establish the initial market price
5. Displayed price = **midpoint of bid-ask spread** (unless spread > $0.10, then last traded price)

### Key insight — NOT $0.50 default:
The system has no hardcoded default price. However, empirical observation from live API data shows:

| Market Type | Typical Initial Price | Evidence |
|---|---|---|
| Crypto Up/Down (automated) | Exactly $0.50/$0.50 | Automated market maker seeds at 50/50 |
| Sports markets (automated) | Varies: $0.50 to $0.93/$0.07 | Pre-seeded by sports odds engine |
| Manual prediction markets | No initial price until first orders | Depends on market maker activity |
| Breaking news markets | First orders set price | ZachXBT market: varied by sub-market |

### Historical context:
- Polymarket originally used **LMSR (Logarithmic Market Scoring Rule)** AMM for pricing
- Transitioned to pure **CLOB (Central Limit Order Book)** model
- The CLOB is a hybrid: quotes/matching happen off-chain (low latency), settlement on-chain (Polygon)

### Source:
- [How Are Prices Calculated? — Polymarket Help Center](https://help.polymarket.com/en/articles/13364488-how-are-prices-calculated)
- [From AMM to Order Book: Polymarket's Pricing Mechanism — PANews](https://www.panewslab.com/en/articles/fz20kk02b04n)

---

## Q3: How Initial Liquidity Works

**Answer: No automatic AMM seeding. Liquidity bootstraps via market maker limit orders + rewards program.**

### Current model (CLOB):
- **No automated liquidity** — the platform does NOT seed new markets with funds
- Market makers must voluntarily post limit orders to bootstrap a book
- The minting mechanism (1 USDC → 1 YES + 1 NO) creates shares only when opposing orders match

### Liquidity rewards program:
Polymarket incentivizes market making through a quadratic rewards formula:

```
Score = ((v - s) / v)² × b
```

Where:
- `v` = max allowed spread from midpoint
- `s` = actual spread from adjusted midpoint
- `b` = in-game multiplier (currently 3.0)

Key parameters per market (available via CLOB API):
- `rewardsMinSize` — minimum order size for rewards (e.g., $50)
- `rewardsMaxSpread` — maximum spread to qualify (e.g., 4.5 cents)
- `max_incentive_spread` and `min_incentive_size` — configurable per market

Rewards are distributed **daily at midnight UTC**, minimum $1 payout.

### Two-sided requirement:
- When midpoint is outside [0.10, 0.90]: **must** provide both YES and NO liquidity
- When midpoint is inside [0.10, 0.90]: single-sided OK but rewards divided by 3.0

### Practical observation from API testing:
- Automated markets (crypto up/down, sports) get **pre-seeded liquidity** at creation
  - BTC Up/Down 24h: $15,353 liquidity at creation, zero volume
  - ETH Up/Down 24h: $12,237 liquidity at creation, zero volume
  - LoL esports: $80-$229 liquidity at creation
- Manual markets (political, etc.): liquidity builds over hours/days after creation

### Source:
- [Liquidity Rewards — Polymarket Docs](https://docs.polymarket.com/developers/market-makers/liquidity-rewards)
- [Reverse Engineering Polymarket Liquidity Rewards — Medium](https://medium.com/@wanguolin/my-two-week-deep-dive-into-polymarket-liquidity-rewards-a-technical-postmortem-88d3a954a058)

---

## Q4: Time from Submission to Live

**Answer: Highly variable — from ~1 minute (automated) to 8+ days (manual).**

### Measured from live API data (2,587 markets):

| Gap (createdAt → acceptingOrdersTimestamp) | Count | % |
|---|---|---|
| 0-2 minutes | 320 | 12.4% |
| 2-5 minutes | 101 | 3.9% |
| 5-30 minutes | 404 | 15.6% |
| 30-60 minutes | 60 | 2.3% |
| 1-6 hours | 520 | 20.1% |
| 6-24 hours | 178 | 6.9% |
| 1-7 days | 780 | 30.2% |
| 7+ days | 224 | 8.7% |

### Market lifecycle timestamps:
1. `createdAt` — Record created in Gamma database
2. `acceptingOrdersTimestamp` — CLOB starts accepting limit orders
3. `startDate` — Market becomes publicly visible/active

### Observed lifecycle for the ZachXBT market (Feb 23, 2026):
- `createdAt`: 15:49:47 UTC
- `acceptingOrdersTimestamp`: ~17:01 UTC (+71 min)
- `startDate`: ~17:02-17:06 UTC (+73 min)
- Total creation-to-live: **~73 minutes**

### Automated vs manual:
- **Automated series** (crypto up/down, sports): created and live within **1-5 minutes**
- **Event-driven markets**: typically **1-6 hours**
- **Forward-looking markets** (2028 election, etc.): created **days-weeks** before activation
- **Breaking news**: Polymarket team can spin up within **~70 minutes** (ZachXBT case)

### No public submission-to-listing SLA exists.

---

## Q5: API Detection of New Markets

**Answer: YES — the Gamma API supports new market detection via `createdAt` sorting.**

### Primary detection method:

```
GET https://gamma-api.polymarket.com/events?
  active=true&
  closed=false&
  order=createdAt&
  ascending=false&
  limit=100
```

Returns newest events first with full market metadata.

### Key fields for detection:

| Field | Type | Purpose |
|---|---|---|
| `createdAt` | ISO 8601 timestamp | When record was created in Gamma |
| `startDate` | ISO 8601 timestamp | When market became publicly active |
| `acceptingOrdersTimestamp` | ISO 8601 timestamp | When CLOB started taking orders |
| `new` | boolean | **Appears non-functional** — always false in testing (0/200 recent events) |
| `featured` | boolean | Whether Polymarket is featuring this market |
| `active` | boolean | Whether market is currently tradable |
| `approved` | boolean | Whether market has been approved |
| `volume` | float | Volume traded (0 = brand new) |
| `liquidity` | float | Current book depth |
| `outcomePrices` | JSON string | Current YES/NO prices |
| `ready` | boolean | Purpose unclear (often false even for active markets) |
| `funded` | boolean | Purpose unclear (often false even for active markets) |

### Detection strategy:
1. **Poll events endpoint** every 1-5 minutes sorted by `createdAt` desc
2. Track `createdAt` timestamps to identify new entries
3. Filter out automated series (crypto up/down, sports) by checking:
   - `series` field presence (automated markets belong to series like "btc-up-or-down-5m")
   - slug patterns: `updown`, `(bo3)`, `(bo5)`, etc.
4. Alert when a non-series, non-sports event appears
5. Check `acceptingOrdersTimestamp` — if present and recent, orders are already possible

### What the `new` flag actually means:
Despite being documented, this flag appears to be an **editorial/UI flag**, not a programmatic indicator. It was `false` for all 200+ recently created events tested. Do NOT rely on it for detection.

### Practical early-detection window:
The gap between `createdAt` and `acceptingOrdersTimestamp` is the **pre-trading window**:
- 16.3% of markets have < 5 min gap (mostly automated — no edge)
- 15.6% have 5-30 min gap (some manual markets — possible edge)
- 20.1% have 1-6 hour gap (many manual markets — **primary opportunity window**)

The true edge is detecting markets that have `createdAt` set but `acceptingOrdersTimestamp` not yet set or very recent — these are markets where the order book is brand new and thin.

### Source:
- [Get Markets — Polymarket Docs](https://docs.polymarket.com/developers/gamma-markets-api/get-markets)
- [Gamma Structure — Polymarket Docs](https://docs.polymarket.com/developers/gamma-markets-api/gamma-structure)
- [Fetch Markets Guide — Polymarket Docs](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide)
- [Polymarket API Architecture — Medium](https://medium.com/@gwrx2005/the-polymarket-api-architecture-endpoints-and-use-cases-f1d88fa6c1bf)
- Direct API testing: `gamma-api.polymarket.com` (2026-02-25)

---

## Summary Table

| Question | Answer | Confidence |
|---|---|---|
| Who creates markets? | Polymarket's internal markets team only | High (official docs) |
| Can users create markets? | No — suggest via Discord/Twitter only | High (official docs) |
| Default initial price? | No default — first matched orders set price | High (official docs + API) |
| Automated market initial price? | Typically $0.50/$0.50 (crypto), odds-based (sports) | High (API observation) |
| AMM or CLOB? | Pure CLOB (transitioned from LMSR AMM) | High (official docs) |
| Automatic liquidity seeding? | No for manual markets; yes for automated series | Medium (API observation) |
| Liquidity incentives? | Quadratic rewards program for market makers | High (official docs) |
| Time submission → live? | Varies: 1 min (auto) to 8+ days (manual) | High (API measurement) |
| Breaking news → live? | ~70 minutes observed (ZachXBT case) | Medium (single case) |
| API for new market detection? | Yes — `GET /events?order=createdAt&ascending=false` | High (API tested) |
| `new` flag reliable? | No — appears non-functional (always false) | High (API tested) |

---

## Edge Implications for Trading

1. **First-mover advantage**: Markets with thin books in first hours may have mispriced outcomes
2. **Automated markets**: No edge — pre-seeded by sophisticated market makers
3. **Manual breaking-news markets**: ~70 min creation-to-live gives time to prepare if you detect the event first
4. **Detection feasibility**: Simple polling script can catch new non-series events within minutes
5. **Liquidity concern**: New markets have $0 volume — position sizing must be minimal until book deepens
6. **The real edge**: Knowing the event context (domain expertise) BEFORE the market appears, then being ready to act in the first hours when prices reflect low-information market making
