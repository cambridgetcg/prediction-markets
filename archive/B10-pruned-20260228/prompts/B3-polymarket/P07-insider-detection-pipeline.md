You are a blockchain intelligence analyst building an insider/front-running detection pipeline for Polymarket. This is the automated version of S010's "Type E — Suspicious" signal classification.

## Why This Matters

Documented insider trading on Polymarket:
- AlphaRaccoon: $1.36M on 22/23 Google predictions (suspected Google insider)
- Venezuela/Maduro: $32K → $400K+ from a single pre-event trade
- Jan 2026 political event: $35K → $442K (12.6x return, fresh wallet)
- Portugal election: $5M surge hours before exit polls
- Two Israelis (IDF reservist + civilian) charged Feb 2026 with Polymarket insider trading on military operations

There are no SEC-equivalent insider trading laws for prediction markets. The CFTC has brought zero enforcement actions. This means:
1. Insiders trade openly on Polymarket
2. Their trades are visible on-chain
3. Detecting their activity BEFORE the public announcement is a genuine edge

## Read First

1. ~/Desktop/prediction-markets/research/whale-signal-research.md — Section 5 (Insider Trading Patterns)
2. ~/Desktop/prediction-markets/strategies/playbooks/S010-whale-signal.md — Section 6 (Front-Running Detection)
3. ~/Desktop/prediction-markets/research/what-doesnt-work.md — Section 5.4 (Market Manipulation)
4. ~/Desktop/prediction-markets/scripts/whale-monitor.py — existing monitoring infrastructure

---

## Task 1: Evaluate pselamy/polymarket-insider-tracker

### 1a. Repository Analysis

Fetch and analyze the GitHub repository:
- Web search: "github pselamy polymarket-insider-tracker" — find the repo
- Read the README, architecture docs, and detection methodology
- What detection signals does it implement? (Fresh wallets, unusual sizing, niche markets, funding chains)
- What infrastructure does it require? (PostgreSQL 15, Redis 7, Docker — confirmed from research)
- How does the DBSCAN clustering work for related wallet detection?
- What APIs does it use? (Polymarket CLOB API, Polygon RPC, Market Metadata)

### 1b. Deployment Feasibility

Can we run this locally?
- Does our machine have Docker installed? Check: `docker --version`
- What environment variables / API keys are needed?
- Is Polygon RPC free tier sufficient? (Alchemy: 300M compute units/month)
- Estimated resource usage: CPU, RAM, disk for PostgreSQL + Redis
- Can it run on a schedule (cron) or does it need to run continuously?

### 1c. Alternative: NickNaskida/polymarket-insider-bot

This is a lighter-weight async alternative:
- Web search: "github NickNaskida polymarket-insider-bot"
- Compare: detection signals, infrastructure requirements, ease of setup
- Does it use SQLite (simpler) vs PostgreSQL (heavier)?
- Is the 0-10 scoring system useful for our workflow?

Pick the better option for our use case (daily monitoring, low infrastructure overhead, GEO/ECO focus).

---

## Task 2: Build Simplified Front-Run Detector

If the full pselamy tracker is too heavy, build a lightweight alternative using our existing infrastructure.

### 2a. The Detection Algorithm

```python
# ~/Desktop/prediction-markets/scripts/frontrun-detector.py

"""
Front-Run Detector — identifies potential insider activity on Polymarket.

Detection signals (from S010 research):
1. Fresh wallet: <5 prior transactions making >$5K bet
2. Price drift: 4-8% move in one direction WITHOUT news catalyst
3. Low volume: below-average volume during the drift (quiet, deliberate)
4. Upcoming announcement: market has a known catalyst date within 72h
5. Niche market: <$50K total volume + large relative bet

The key distinction from S004:
- S004: Large move WITH news → fade the overreaction
- Front-run: Small move WITHOUT news → follow the informed flow
"""

# Approach:
# 1. Fetch all active markets from Gamma API with upcoming catalyst dates
# 2. For each market, check 24h price change and volume
# 3. Flag markets where: price moved 4-8% AND volume is below 7-day average
# 4. Cross-reference flagged markets against known announcement calendar
# 5. Check if any fresh wallets appeared in the flagged markets (Polygonscan)
```

### 2b. Announcement Calendar

Build a catalyst calendar that the detector checks against:

```json
// ~/Desktop/prediction-markets/data/catalyst-calendar.json
[
  {
    "event": "FOMC Decision",
    "date": "2026-03-19",
    "domain": "ECO",
    "markets": ["Fed rate decision March 2026"],
    "frontrun_window_hours": 72
  },
  {
    "event": "Iran nuclear talks",
    "date": "2026-03-15",
    "domain": "GEO",
    "markets": ["US strikes Iran by March 31"],
    "frontrun_window_hours": 48
  }
]
```

Populate this with all known upcoming catalysts for our open positions (T001-T008).

### 2c. Historical Validation

Test the detector against known insider cases:
- Can we reconstruct the AlphaRaccoon pattern? (22/23 Google predictions, 24-72h before announcements)
- Can we detect the Venezuela/Maduro trade retroactively? (fresh wallet, $32K single bet)
- What would the Jan 2026 $442K trade have looked like to our detector?

Use Polygonscan historical data and Gamma API for resolved markets.

---

## Task 3: Fresh Wallet Monitor

The simplest high-value detection: watch for NEW wallets making large first bets on markets we're trading.

### 3a. Implementation

```python
# Add to whale-monitor.py or create separate script:
# ~/Desktop/prediction-markets/scripts/fresh-wallet-detector.py

"""
Monitor markets in our portfolio for large bets from fresh wallets.

A 'fresh wallet' is defined as:
- Created within the last 30 days (first transaction timestamp)
- Fewer than 10 total transactions on Polygon
- Making a bet > $5,000 on a single market

This is the strongest insider signal because:
- Insiders create new wallets to avoid linking to their identity
- They deposit USDC, make one large directional bet, and wait
- The wallet creation timestamp is publicly visible on Polygonscan
"""
```

### 3b. Markets to Monitor

From our open positions:
- "US strikes Iran by June 30, 2026" (T001)
- "US strikes Iran by March 31, 2026" (T003)
- "Will US or Israel strike Iran by March 31, 2026?" (T005)
- "Will Donald Trump win the 2028 Republican presidential nomination?" (T002)
- "Will J.D. Vance win the 2028 Republican presidential nomination?" (T006)
- "Will Nicolas Maduro be the leader of Venezuela at end of 2026?" (T007)
- "Will Bitcoin reach $150,000 by December 31, 2026?" (T008)

For each, we need the Polymarket condition token IDs to filter on-chain activity. Get these from Gamma API.

---

## Task 4: Alert Integration

### 4a. Signal Scoring

Each detected anomaly gets a score (0-10):

| Signal | Score |
|--------|-------|
| Fresh wallet (<5 txns) + large bet (>$5K) | +3 |
| Niche market (<$50K volume) | +2 |
| Trade size >2% of order book | +2 |
| Known upcoming catalyst within 72h | +2 |
| Price drifting 4-8% without news | +1 |
| Wallet funded from fresh exchange deposit | +1 |
| Multiple fresh wallets trading same market same direction | +3 (cluster) |

**Alert thresholds:**
- Score 0-3: Log only
- Score 4-6: Flag for manual review
- Score 7+: IMMEDIATE ALERT — probable insider

### 4b. Response Protocol

When an insider signal is detected on a market we're trading:

```
1. CHECK: Does the insider direction agree or contradict our position?
2. IF agree (same direction as our trade):
   → Type A confirmation. Consider sizing up by 25-50%.
   → Document: the insider ALSO thinks this outcome is likely.
3. IF contradict (opposite direction to our trade):
   → Type C. DO NOT panic exit.
   → Investigate: who funded the wallet? How large relative to market?
   → If score 7+ and contradicts: reduce position by 50%.
4. LOG everything to data/insider-signals.jsonl
```

---

## Output

1. `scripts/frontrun-detector.py` — lightweight front-running detection script
2. `scripts/fresh-wallet-detector.py` — fresh wallet monitor for our markets
3. `data/catalyst-calendar.json` — populated with all known upcoming catalysts
4. `data/insider-signals.jsonl` — schema for logging detected anomalies
5. Updated `strategies/playbooks/S010-whale-signal.md` — add insider detection protocol section
6. Evaluation: pselamy vs NickNaskida vs custom — which to deploy?

**Done when**: We have at least one working insider detection script that can scan our 7 open-position markets and flag fresh wallets making large directional bets. Historical validation against at least one known insider case.
