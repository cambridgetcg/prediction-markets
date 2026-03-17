# B9-02: Fresh Wallet Detector
# Priority: HIGH — catches new insiders before they're profiled
# Created: 2026-02-28
# Dependencies: Polygonscan API key, Gamma API (free)

## The Pattern

Every documented Polymarket insider case follows the same playbook:
1. Create fresh wallet (0 prior transactions)
2. Fund with USDC from exchange (Coinbase, Binance, etc.)
3. Make ONE large directional bet on a specific market
4. Wait for resolution → collect profit → abandon wallet

Cases:
- **Venezuela/Maduro**: Fresh wallet, $32K → $400K+ (12.5×)
- **Jan 2026 political event**: Fresh wallet, $35K → $442K (12.6×)
- **IDF reservist + civilian**: Fresh wallets, charged by SEC Feb 2026
- **Portugal election**: $5M surge from low-history wallets hours before exit polls

The B9-01 whale scanner tracks KNOWN insiders. B9-02 catches UNKNOWN insiders
by watching for the behavioral pattern, not the wallet identity.

## Your Task

### Part 1: Market-Centric Fresh Wallet Monitor (`scripts/fresh-wallet-detector.py`)

Instead of tracking known wallets (B9-01's job), this script watches specific
MARKETS for suspicious new participants.

```python
#!/usr/bin/env python3
"""
Fresh Wallet Detector — monitors markets for insider-pattern activity.

Watches markets in our portfolio + watchlist for large bets from
wallets with minimal transaction history.

Usage:
    python3 fresh-wallet-detector.py                     # Scan portfolio markets
    python3 fresh-wallet-detector.py --market "Iran"     # Specific market keyword
    python3 fresh-wallet-detector.py --continuous         # Poll every 30 min
    python3 fresh-wallet-detector.py --threshold 5000    # Min bet size (default $5K)
    python3 fresh-wallet-detector.py --max-history 10    # Max prior txns (default 10)
"""
```

**Core approach:**

```
For each monitored market:
  1. Fetch recent trades from Polymarket CLOB API:
     GET https://clob.polymarket.com/trades?market={token_id}&limit=100
     
  2. For each trade above $5K:
     a. Check the wallet's transaction history on Polygonscan
     b. Count total prior transactions
     c. Check wallet creation date (first transaction timestamp)
     d. Check funding source (which exchange deposited the USDC?)
     
  3. Flag if:
     - Wallet has < 10 prior Polymarket transactions AND
     - Trade size > $5,000 AND
     - Wallet age < 30 days
     
  4. Score the anomaly (see scoring)
  5. Cross-reference with catalyst calendar
```

**Alternative approach (if CLOB trade history is limited):**

```
Use Polygonscan to watch the Polymarket CTF Exchange contract:
  1. Fetch recent transactions TO the CTF Exchange:
     GET /api?module=account&action=txlist
         &address=0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E
         &sort=desc&page=1&offset=100
  
  2. For each transaction, get the sender wallet
  3. Check sender's history (as above)
  4. Resolve which market the trade was for (from input data / token transfer)

This is broader but catches activity across ALL markets, not just monitored ones.
For cost efficiency, only do the full wallet history check when USDC transfer > $5K.
```

### Part 2: Catalyst Calendar (`data/catalyst-calendar.json`)

The front-run window: insiders trade 24-72h before announcements.
Build and maintain a calendar of known upcoming catalysts:

```json
{
  "generated_at": "2026-02-28T00:00:00Z",
  "events": [
    {
      "event": "LT002 Resolution — US tariff revenue data",
      "date": "2026-02-28",
      "domain": "ECO",
      "related_markets": ["US collect <$100b revenue FY2025"],
      "frontrun_window_hours": 48,
      "our_position": "LT002 YES @ $0.965"
    },
    {
      "event": "Texas GOP Primary — Ken Paxton",
      "date": "2026-03-03",
      "domain": "POL",
      "related_markets": ["Ken Paxton wins TX GOP primary"],
      "frontrun_window_hours": 72,
      "our_position": "LT003 YES @ $0.83"
    },
    {
      "event": "Iran nuclear talks — Round 2",
      "date": "2026-03-05",
      "domain": "GEO",
      "related_markets": ["US strikes Iran by Mar 31", "US/Israel strikes Iran by Mar 31"],
      "frontrun_window_hours": 48,
      "our_position": "LT001 NO @ $0.41"
    },
    {
      "event": "FOMC Meeting",
      "date": "2026-03-19",
      "domain": "ECO",
      "related_markets": ["Fed rate decision March 2026"],
      "frontrun_window_hours": 72,
      "our_position": null
    },
    {
      "event": "Iran Mar 31 deadline",
      "date": "2026-03-31",
      "domain": "GEO",
      "related_markets": ["US strikes Iran by Mar 31"],
      "frontrun_window_hours": 168,
      "our_position": "LT001 NO, PT001 NO"
    },
    {
      "event": "Oscars ceremony",
      "date": "2026-03-15",
      "domain": "SOC",
      "related_markets": ["Best Picture", "Best Director", "Best Actor"],
      "frontrun_window_hours": 48,
      "our_position": null
    }
  ]
}
```

**Maintenance protocol**: Update weekly when running E01 (Fast Resolution Sprint).
Each new market entry should check for upcoming catalysts and add to calendar.

### Part 3: Anomaly Scoring

```python
def score_fresh_wallet_anomaly(wallet_info, trade, catalyst_calendar):
    """Score 0-10 for fresh wallet insider probability."""
    score = 0
    
    # Wallet freshness
    if wallet_info.total_txns <= 5:
        score += 3           # Very fresh — classic insider pattern
    elif wallet_info.total_txns <= 10:
        score += 2
    elif wallet_info.total_txns <= 20:
        score += 1
    
    # Wallet age
    if wallet_info.age_days <= 7:
        score += 2           # Created this week
    elif wallet_info.age_days <= 30:
        score += 1
    
    # Trade size relative to market
    if trade.size_usd > trade.market_volume * 0.02:
        score += 2           # >2% of total market volume
    elif trade.size_usd > 10000:
        score += 1
    
    # Niche market
    if trade.market_volume < 50000:
        score += 1           # Low-volume market = higher signal
    
    # Catalyst proximity
    days_to_catalyst = nearest_catalyst(trade.market, catalyst_calendar)
    if days_to_catalyst is not None and days_to_catalyst <= 3:
        score += 2           # Known catalyst within 72h
    elif days_to_catalyst is not None and days_to_catalyst <= 7:
        score += 1
    
    # Funding from fresh exchange deposit (if detectable)
    if wallet_info.funded_from_exchange and wallet_info.first_deposit_hours_ago < 48:
        score += 1           # Just deposited from exchange → new actor
    
    return min(score, 10)

# Thresholds (same as B9-01):
# 0-3: Log only
# 4-6: Flag for manual review  
# 7+:  ALERT — probable insider (new, unknown)
```

### Part 4: Unknown Insider Profiling

When a fresh wallet scores 7+, automatically create a preliminary profile:

```python
def create_preliminary_profile(wallet, trade):
    """Create a stub dossier for a newly detected suspected insider."""
    return {
        "wallet": wallet.address,
        "alias": f"UNKNOWN-{trade.domain}-{datetime.now().strftime('%Y%m%d')}",
        "first_detected": datetime.now(timezone.utc).isoformat(),
        "detection_method": "fresh-wallet-detector",
        "anomaly_score": trade.score,
        "trades": [
            {
                "market": trade.market_question,
                "domain": trade.domain,
                "direction": trade.direction,
                "size_usd": trade.size_usd,
                "entry_price": trade.entry_price,
                "timestamp": trade.timestamp,
            }
        ],
        "wallet_info": {
            "total_txns": wallet.total_txns,
            "age_days": wallet.age_days,
            "usdc_balance": wallet.usdc_balance,
            "funding_source": wallet.funding_source,  # exchange address if detected
        },
        "status": "monitoring",  # monitoring | confirmed_insider | false_positive
        "notes": "",
    }
```

Save to `data/detected-wallets/UNKNOWN-{domain}-{date}.json`.
After resolution: was their trade correct? If yes → add to insider-registry for L01-L03 processing.

### Part 5: Integration with Portfolio

When a fresh wallet anomaly is detected on a market where we have a position:

```
IF anomaly direction AGREES with our position:
  → Log as "confirmation signal"
  → Consider sizing up 25% (within C1/C2 caps)
  → Note: unknown insider also expects this outcome

IF anomaly direction CONTRADICTS our position:
  → ALERT immediately
  → Do NOT panic exit (could be noise)
  → Check: is this a single wallet or a CLUSTER?
  → If cluster (3+ fresh wallets, same direction, same market):
    → Reduce position by 50%
    → This is the strongest insider signal — multiple people know something
  → If single wallet:
    → Flag for review, hold position
```

### Part 6: Tests

```python
class TestWalletHistoryCheck:
    def test_fresh_wallet_detected(self):        # <5 txns = fresh
    def test_established_wallet_ignored(self):    # >20 txns = not fresh
    def test_wallet_age_calculation(self):

class TestAnomalyScoring:
    def test_max_score_fresh_large_catalyst(self):
    def test_min_score_established_small(self):
    def test_niche_market_bonus(self):
    def test_catalyst_proximity_bonus(self):

class TestCatalystCalendar:
    def test_nearest_catalyst_found(self):
    def test_no_catalyst_returns_none(self):
    def test_expired_catalyst_ignored(self):

class TestClusterDetection:
    def test_three_fresh_wallets_same_market(self):   # cluster = true
    def test_one_fresh_wallet(self):                   # cluster = false
    def test_fresh_wallets_different_markets(self):    # not a cluster

class TestPortfolioIntegration:
    def test_agrees_with_position(self):
    def test_contradicts_position(self):
    def test_no_position_on_market(self):
```

## Output

1. `scripts/fresh-wallet-detector.py` — market-centric fresh wallet monitor
2. `data/catalyst-calendar.json` — populated with all known upcoming catalysts
3. `data/detected-wallets/` directory structure for unknown insider profiles
4. `scripts/test_fresh_wallet_detector.py` — tests
5. Updated `scripts/schema.sql` — fresh_wallet_anomalies table

**Done when**: Detector can scan at least 3 of our open-position markets,
identify any wallets with <10 transactions making >$5K bets, score them,
and cross-reference against the catalyst calendar. Test with historical
data from at least one known insider case if available.
