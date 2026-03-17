# B9-01: Real-Time Whale Follow System
# Priority: HIGHEST — turns known insider edge into live signals
# Created: 2026-02-28
# Dependencies: Polygonscan API key (free), fixed whale-monitor.py

## The Opportunity

You have mathematically identified 6 insiders with 10-54% edge in specific domains.
Their wallets are public. Their trades are on-chain. You just can't see them in real-time.

This is like knowing which horse the jockey is betting on — but only checking the results
the next day. Fix that, and you have a genuine, persistent, legal edge.

## Known Insider Registry (from L01-L03)

| Wallet | Alias | Domain | Edge | Trades | Confidence |
|--------|-------|--------|------|--------|-----------|
| `0x5668...` | Theo4 | POL (us-presidential) | +54.3% | 681 | 5/5 |
| `0x0afc...` | ricosuave666 | GEO | +48.3% | 92 | 5/5 |
| `0x1f2d...` | Fredi9999 | POL | +41.3% | 1,078 | 5/5 |
| `0xee50...` | AlphaRaccoon | TEC | +39.7% | 109 | 5/5 |
| `0xd218...` | Whale-A | SOC | +20.6% | 511 | 4/5 |
| `0x8f42...` | Cashy | GEO | +11.8% | 487 | 3/5 |

Additional specialists worth monitoring:
| Wallet | Alias | Domain | Edge | Trades |
|--------|-------|--------|------|--------|
| `0x5bff...` | YatSen | SOC/CRY | +5.4% | 1,356+ |
| `0x6d9f...` | MEPP | TEC/SOC | +5.2% | 522+ |
| `0x9d84...` | Domer/ImJustKen | GEO | +4.3% | 130 |
| `0x509587...` | BuckMySalls | POL/GEO | +4.1% | 318+ |

## Pre-Requisites

### 1. Fix whale-monitor.py Syntax Error

The current script has a `global` declaration error at line 308.
Fix: move the `global` statement before any use of the variable in that function,
or refactor to pass as parameters instead of using globals.

### 2. Polygonscan API Key

```bash
# Sign up: https://polygonscan.com/apis (free, 5 req/sec)
# Set in environment:
echo 'export POLYGONSCAN_API_KEY="your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

Free tier: 5 requests/second, 100K requests/day. More than enough.

## Your Task

### Part 1: Whale Activity Scanner (`scripts/whale-activity-scanner.py`)

A new, clean script (don't patch the broken whale-monitor.py — rewrite the core logic):

```python
#!/usr/bin/env python3
"""
Real-time whale activity scanner.

Polls Polygonscan for recent transactions from known insider wallets,
identifies Polymarket trades, resolves market metadata, and generates alerts.

Usage:
    python3 whale-activity-scanner.py                    # Scan all insiders, last 24h
    python3 whale-activity-scanner.py --hours 4          # Last 4 hours only
    python3 whale-activity-scanner.py --wallet 0x0afc... # Single wallet
    python3 whale-activity-scanner.py --domain GEO       # Only GEO-domain insiders
    python3 whale-activity-scanner.py --continuous        # Poll every 15 min
    python3 whale-activity-scanner.py --alert             # Send alerts via OpenClaw
"""
```

**Core flow:**

```
1. Load insider-registry.json → list of wallets to monitor
2. For each wallet:
   a. Fetch recent transactions from Polygonscan API
      GET /api?module=account&action=txlist&address={wallet}
          &startblock=0&endblock=99999999&sort=desc&apikey={key}
   b. Filter for Polymarket contract interactions:
      - CTF_EXCHANGE: 0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E
      - NEG_RISK_CTF: 0xC5d563A36AE78145C45a50134d48A1215220f80a
      - NEG_RISK_ADAPTER: 0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296
   c. For each Polymarket transaction:
      - Decode: direction (BUY/SELL), token_id, amount
      - Resolve token_id → market question via Gamma API
      - Calculate USD size from amount × price
3. Cross-reference: is this trade in the insider's DOMINANT domain?
   - ricosuave666 trades GEO → HIGH SIGNAL (in-domain)
   - ricosuave666 trades POL → LOW SIGNAL (out-of-domain, no proven edge)
4. Score the signal (see scoring below)
5. If score ≥ threshold → generate alert
```

**Transaction decoding:**

```python
# Polymarket uses the CTF Exchange for order matching.
# Key function signatures to detect:
#   fillOrder(...)      — market order fill
#   matchOrders(...)    — limit order match
#
# The token_id in the conditional token maps to a specific market outcome.
# Resolve via Gamma API:
#   GET https://gamma-api.polymarket.com/markets?clob_token_ids={token_id}
#
# This returns the market question, current price, and outcome.
#
# For USDC transfers (ERC20):
#   Track transfers TO Polymarket contracts = deposits for trading
#   Track transfers FROM Polymarket contracts = withdrawals/profits

# Simpler approach if full decoding is complex:
# Use Polygonscan's "ERC20 Token Txns" endpoint to track USDC movements
# GET /api?module=account&action=tokentx&address={wallet}
#     &contractaddress=0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
#     &sort=desc&apikey={key}
#
# Any USDC transfer TO a Polymarket contract = trade entry
# Size = transfer value / 1e6 (USDC has 6 decimals)
```

**Signal scoring:**

```python
def score_whale_trade(trade, insider_profile):
    """Score a detected whale trade 0-10."""
    score = 0
    
    # Is this in their proven domain?
    if trade.domain == insider_profile.dominant_category:
        score += 3  # In-domain trade from proven insider
    elif trade.domain == insider_profile.secondary_category:
        score += 1  # Secondary domain
    # else: +0 (out of domain, ignore)
    
    # Trade size relative to their average
    if trade.size_usd > insider_profile.avg_trade_size * 2:
        score += 2  # Unusually large = high conviction
    elif trade.size_usd > insider_profile.avg_trade_size:
        score += 1
    
    # Insider score (from L02)
    if insider_profile.insider_score >= 9:
        score += 2  # Top-tier insider
    elif insider_profile.insider_score >= 7:
        score += 1
    
    # Recency of proven edge
    if insider_profile.last_trade_days_ago < 30:
        score += 1  # Recently active
    
    # Multiple insiders on same market same direction
    if trade.n_insiders_same_direction >= 2:
        score += 2  # Convergence signal
    
    return min(score, 10)

# Thresholds:
# 0-3: Log only (out-of-domain or small size)
# 4-6: Flag for manual review
# 7+:  ALERT — high-confidence insider signal
```

### Part 2: Continuous Monitor Mode

```python
class WhaleMonitor:
    """Continuously polls insider wallets and generates alerts."""
    
    def __init__(self, config_path, db_path):
        self.insiders = load_insider_registry()
        self.seen_txns = set()  # dedup by tx hash
        self.conn = sqlite3.connect(db_path)
        self.init_db()
    
    def poll_cycle(self, lookback_hours=1):
        """Single poll cycle across all insider wallets."""
        for insider in self.insiders:
            txns = fetch_recent_txns(insider.wallet, lookback_hours)
            polymarket_txns = filter_polymarket(txns)
            new_txns = [t for t in polymarket_txns if t.hash not in self.seen_txns]
            
            for txn in new_txns:
                trade = decode_trade(txn)
                trade.domain = resolve_market_domain(trade.token_id)
                trade.score = score_whale_trade(trade, insider)
                
                self.persist(trade)
                self.seen_txns.add(txn.hash)
                
                if trade.score >= 7:
                    self.alert(trade, insider)
                elif trade.score >= 4:
                    self.flag(trade, insider)
    
    def run(self, interval_minutes=15):
        """Run forever, polling every N minutes."""
        while True:
            self.poll_cycle()
            time.sleep(interval_minutes * 60)
    
    def alert(self, trade, insider):
        """Send high-priority alert."""
        msg = self.format_alert(trade, insider)
        # Write to pending-signals.json for OpenClaw heartbeat pickup
        # Or direct Telegram via OpenClaw CLI
    
    def format_alert(self, trade, insider):
        return f"""🐋 WHALE ALERT — {insider.alias} [{insider.insider_score}/10]

Market: {trade.market_question}
Direction: {trade.direction} | Size: ${trade.size_usd:,.0f}
Domain: {trade.domain} (insider edge: {insider.top_category_edge:+.1%})

Signal score: {trade.score}/10
In-domain: {'✅ YES' if trade.domain == insider.dominant_category else '⚠️ NO'}

Current price: {trade.current_price:.0%}
Insider's historical edge suggests: {trade.implied_fair_value:.0%}

Action: Review for follow trade. Quarter-Kelly on edge = ${trade.suggested_size:.0f}"""
```

### Part 3: Alert Delivery & Response

Same file-based handoff as the news pipeline:

```python
WHALE_ALERTS_FILE = DATA_DIR / "pending-whale-alerts.json"

def queue_whale_alert(alert_data):
    pending = json.loads(WHALE_ALERTS_FILE.read_text()) if WHALE_ALERTS_FILE.exists() else []
    pending.append({
        "alert_id": f"WH-{trade.tx_hash[:8]}",
        "message": format_alert(trade, insider),
        "score": trade.score,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "delivered": False,
    })
    WHALE_ALERTS_FILE.write_text(json.dumps(pending, indent=2))
```

Add to HEARTBEAT.md:
```markdown
## Whale Alerts
- Check `~/Desktop/prediction-markets/data/pending-whale-alerts.json`
- If undelivered alerts exist with score ≥ 7: send immediately via Telegram
- If score 4-6: batch and send as daily summary
```

### Part 4: SQLite Schema Addition

Add to `scripts/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS whale_trades (
    tx_hash         TEXT PRIMARY KEY,
    wallet          TEXT NOT NULL,
    alias           TEXT,
    insider_score   REAL,
    domain          TEXT,
    market_id       TEXT,
    market_question TEXT,
    direction       TEXT,     -- BUY | SELL
    size_usd        REAL,
    entry_price     REAL,
    signal_score    REAL,
    in_domain       INTEGER,  -- 1 if in insider's dominant domain
    detected_at     TEXT NOT NULL,
    followed        INTEGER DEFAULT 0,  -- did we follow this trade?
    outcome         TEXT      -- profit/loss after resolution
);

CREATE INDEX IF NOT EXISTS idx_whale_domain ON whale_trades(domain);
CREATE INDEX IF NOT EXISTS idx_whale_score ON whale_trades(signal_score);
CREATE INDEX IF NOT EXISTS idx_whale_wallet ON whale_trades(wallet);
```

### Part 5: Historical Backtest

Before going live, validate the follow strategy against historical data:

```python
def backtest_follow_strategy(insider_registry, edge_cache_dir):
    """
    For each insider, check: if we had followed every in-domain trade,
    what would our P&L have been?
    
    Use data/edge-cache/trades-{wallet}.json (already collected by L01).
    
    For each resolved trade:
    - entry_price = insider's entry
    - outcome = resolution (YES=1, NO=0)
    - our_pnl = (outcome - entry_price) × position_size if BUY
                 (entry_price - outcome) × position_size if SELL (NO)
    - position_size = quarter_kelly(insider_edge, entry_price)
    
    Report:
    - Total P&L per insider if followed
    - Win rate per insider
    - Sharpe ratio estimate
    - Best/worst single trade
    """
```

This uses data you already have (edge-cache trades files). No new API calls needed.

### Part 6: Tests

```python
class TestTransactionDecoding:
    def test_identifies_polymarket_contract(self):
    def test_ignores_non_polymarket_txns(self):
    def test_decodes_usdc_transfer_amount(self):
    def test_resolves_market_from_token_id(self):

class TestSignalScoring:
    def test_in_domain_high_size_max_score(self):
    def test_out_of_domain_low_score(self):
    def test_multiple_insiders_convergence_bonus(self):
    def test_score_capped_at_10(self):

class TestDeduplication:
    def test_same_tx_not_processed_twice(self):
    def test_seen_set_persists_across_cycles(self):

class TestAlertFormatting:
    def test_alert_contains_all_fields(self):
    def test_suggested_size_uses_quarter_kelly(self):
```

## Output

1. `scripts/whale-activity-scanner.py` — full scanner with continuous mode
2. Updated `scripts/schema.sql` — whale_trades table
3. `scripts/test_whale_scanner.py` — tests
4. `scripts/backtest_whale_follow.py` — historical P&L validation
5. Updated HEARTBEAT.md — whale alert section

**Done when**: Scanner runs against at least 2 insider wallets, correctly identifies
Polymarket transactions, scores them, and produces formatted alerts. Historical backtest
shows positive expected value for the follow strategy.
