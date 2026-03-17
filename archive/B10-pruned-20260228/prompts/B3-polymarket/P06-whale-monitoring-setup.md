You are a prediction market operations engineer setting up automated whale monitoring infrastructure. Your job is to connect the whale-registry.json (15 tracked wallets) to live alerting platforms, enhance whale-monitor.py, and establish a daily monitoring routine.

## Read First

1. ~/Desktop/prediction-markets/data/whale-registry.json — the 15 wallets to track
2. ~/Desktop/prediction-markets/scripts/whale-monitor.py — existing polling script
3. ~/Desktop/prediction-markets/research/whale-signal-research.md — platform capabilities (Section 2)
4. ~/Desktop/prediction-markets/strategies/playbooks/S010-whale-signal.md — signal classification (Type A-E)
5. ~/Desktop/prediction-markets/strategies/paper-trades/positions.json — current open positions

---

## Task 1: PolyTrack Setup & Configuration

### 1a. Account Setup

PolyTrack (polytrackhq.app) offers 3 free wallet tracking slots. These must be the highest-value GEO wallets since GEO is our largest exposure (4/7 positions).

**Recommended free-tier allocation:**
1. `0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2` — ricosuave666 (100% Israel win rate, directly relevant to T001/T003/T005)
2. `0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73` — denizz ($527K deployed, heavily NO on Iran)
3. `0x8f42ae0a01c0383c7ca8bd060b86a645ee74b88f` — Cashy (Israel-based Middle East expert)

Research tasks:
- Navigate to polytrackhq.app, create account, add these 3 wallets
- Document the alert configuration options (email, Telegram, Discord, webhooks)
- Test whether webhook alerts contain enough data (wallet, market, direction, size) for automated processing
- Check "Dev Picks" feature — does it surface any additional GEO/POL specialists not in our registry?
- Search the PolyTrack leaderboard with category=politics filter for any profitable wallets we missed

### 1b. Cluster Analysis

PolyTrack's standout feature is cluster detection. Run these searches:
- Search for the Theo4 address (`0x56687bf447db6ffa42ffe2204a05edaa20f55839`) — does it show all 11 linked accounts? Are any still active?
- Search for ricosuave666 — does it show related wallets? Any cluster pattern?
- Search for denizz — any alt accounts?

Document findings in `research/whale-signal-research.md` Section 3.

---

## Task 2: Polywhaler Alert Configuration

### 2a. Free Tier Setup

Polywhaler (polywhaler.com) monitors $10K+ trades in real-time. Set up alerts for markets relevant to our open positions:

**Markets to monitor:**
- "US strikes Iran" (any timeframe) — affects T001, T003, T005
- "Israel strikes Iran" (any timeframe) — affects T005
- "Republican nomination 2028" — affects T002, T006
- "Bitcoin $150,000" — affects T008
- "Maduro Venezuela" — affects T007

Research:
- What alert channels are available on the free tier? (Telegram, email, browser push?)
- Can we filter by specific market keywords or only by wallet address?
- What does the insider score (0-100) look like for recent Iran-related trades?
- Check: any $10K+ trades visible right now on Iran strike markets?

### 2b. Pro Tier API Evaluation

Polywhaler Pro is $10/month and includes API access. Research:
- What API endpoints are available? (trade alerts, historical data, insider scores?)
- Is the API documented publicly or only post-subscription?
- Could we integrate Polywhaler API into whale-monitor.py to replace/supplement Polygonscan polling?
- Web search: "Polywhaler API documentation" and "Polywhaler Pro review 2026"

Write evaluation to `research/whale-signal-research.md` new Section 9: "Platform API Evaluation".

---

## Task 3: PolyMonit & Telegram Bot Setup

### 3a. PolyMonit Configuration

PolyMonit (polymonit.com) provides low-noise Telegram/email alerts filtered by wallet. Configure:
- Add all 15 registry wallets (or as many as the free tier allows)
- Set minimum trade size threshold: $5,000
- Configure Telegram delivery (document the bot setup process)

### 3b. Telegram Bot Ecosystem

Research which of these is most useful for our setup:
- **Polylerts** — free, 15 wallets, analytical reports
- **PolySpy** — free, new market alerts with Geopolitics category filter
- **PolyIntel** — free, 10-min automated alerts with scoring

Pick the 1-2 most relevant and document setup. The ideal combination:
- PolyMonit for wallet-specific alerts (our 15 registry wallets)
- PolySpy for new GEO/POL market creation alerts (catch new markets early for S003/P03 first-mover)

---

## Task 4: Enhance whale-monitor.py

### 4a. Market-to-Trade Matching

The current script detects USDC.e transfers but can't identify WHICH market a whale is trading. Enhance it:

```python
# New capability: decode which market a trade is for
# Approach:
# 1. Get the transaction hash from USDC.e transfer
# 2. Fetch the full transaction details from Polygonscan (action=gettxinfo)
# 3. Look for the conditional token ID in the transaction input data
# 4. Query Gamma API: /markets?clob_token_ids=TOKEN_ID
# 5. Return the market question + current price

def decode_market_from_tx(tx_hash):
    """Given a transaction hash, identify which Polymarket market it's for."""
    # Fetch transaction details
    # Parse input data for token ID
    # Query Gamma API for market metadata
    pass
```

This is the critical missing piece — without it, we know a whale moved $50K but not on WHAT.

### 4b. Automatic Contradiction Check

Enhance the dashboard to automatically cross-reference whale trades against our positions.json:

```python
def check_contradictions(whale_trades, our_positions):
    """
    For each whale trade, check if it contradicts any open position.
    Return list of (trade, position, signal_type) tuples.
    """
    # Match by market question similarity (fuzzy match on keywords)
    # Classify as Type A (confirmation) or Type C (contradiction)
    # Flag any Type C for immediate attention
    pass
```

### 4c. Signal Classification Integration

Add automatic Type A-E classification based on:
- Whale's domain_focus vs. market domain (from registry)
- Trade direction vs. our position direction (from positions.json)
- Trade size vs. threshold ($5K minimum, $25K high-conviction)
- Timing relative to resolution date

### 4d. Daily Cron Job

Set up a daily automated run:
```bash
# Add to crontab or launchd:
# Run whale-monitor.py every morning at 8 AM local time
# Save output to data/whale-scan-YYYY-MM-DD.json
# If any Type C contradiction detected, alert via terminal notification
```

Document the cron setup process.

---

## Task 5: Unified Alert Protocol

Design the complete alert flow:

```
Whale trades on Polymarket
    │
    ├─ PolyTrack webhook → (3 GEO wallets, <30 sec)
    ├─ Polywhaler alert → ($10K+ trades, real-time)
    ├─ PolyMonit Telegram → (15 wallets, $5K+ threshold)
    │
    └─ whale-monitor.py (daily batch) → dashboard + contradiction check
         │
         ├─ Type A/B: Log to whale-signals.jsonl, consider position adjustment
         ├─ Type C: ALERT — investigate immediately
         ├─ Type D: Log only (wrong domain)
         └─ Type E: ALERT — possible insider, investigate + consider fast follow
```

Create: `~/Desktop/prediction-markets/data/whale-signals.jsonl` schema:
```json
{
  "timestamp": "2026-02-26T10:00:00Z",
  "wallet": "0x...",
  "alias": "denizz",
  "market": "US strikes Iran by June 30, 2026",
  "direction": "NO",
  "size_usd": 32800,
  "our_position": "T001",
  "our_direction": "NO",
  "signal_type": "A",
  "action_taken": "HOLD — confirmation, no sizing change",
  "source": "polymarket.com/profile"
}
```

---

## Output

1. Updated `scripts/whale-monitor.py` — with market decoding, contradiction check, signal classification
2. `data/whale-signals.jsonl` — schema + seed with the denizz/ricosuave666 findings from P05
3. Updated `research/whale-signal-research.md` Section 9 — platform API evaluation
4. Terminal output: step-by-step setup instructions for PolyTrack + Polywhaler + PolyMonit
5. Documented alert protocol in S010 playbook (add new section)

**Done when**: whale-monitor.py can identify WHICH market a whale is trading (not just that USDC moved), automatically classify signals, and cross-reference against our open positions.
