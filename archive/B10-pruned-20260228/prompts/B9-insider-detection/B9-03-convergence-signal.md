# B9-03: Pipeline × Whale Convergence Signal
# Priority: HIGH — highest conviction signals in the entire system
# Created: 2026-02-28
# Dependencies: B8 (news pipeline running), B9-01 (whale scanner), B9-02 (fresh wallet detector)

## The Thesis

No single signal source is reliable enough to trade blindly:
- News pipeline alone: detects divergence but can't confirm direction
- Whale follow alone: insiders can be wrong, or trading for non-obvious reasons
- Fresh wallet alone: could be a wealthy retail gambler, not an insider

But when multiple independent signals converge on the same market in the same
direction, the probability of being correct compounds multiplicatively.

**Convergence hierarchy (weakest → strongest):**

| Level | Signals | Confidence | Sizing |
|-------|---------|-----------|--------|
| 1 | News divergence only | Low | Paper trade only |
| 2 | News divergence + known whale trade (in-domain) | Medium | Quarter-Kelly |
| 3 | News divergence + fresh wallet anomaly (score ≥ 7) | Medium-High | Quarter-Kelly |
| 4 | Known whale + fresh wallet (same direction) | High | Half-Kelly |
| 5 | News + whale + fresh wallet (triple convergence) | Very High | Half-Kelly (max sizing) |

## Data Sources (Input)

### From B8 (News Pipeline)
```python
# SQLite: data/news-pipeline.db
# Tables: signals (GeneratedSignal), extractions (TruthExtractionResult), clusters (EventCluster)
# Key fields: market_question, direction, edge, confidence, divergence_score
```

### From B9-01 (Whale Scanner)
```python
# SQLite: data/news-pipeline.db (shared)
# Table: whale_trades
# Key fields: wallet, alias, domain, market_question, direction, size_usd, signal_score, in_domain
```

### From B9-02 (Fresh Wallet Detector)
```python
# SQLite: data/news-pipeline.db (shared)  
# Table: fresh_wallet_anomalies
# Key fields: wallet, market_question, direction, size_usd, anomaly_score, wallet_age_days, total_txns
```

## Your Task

### Part 1: Convergence Engine (`scripts/convergence_engine.py`)

```python
#!/usr/bin/env python3
"""
Convergence Engine — combines news pipeline, whale, and fresh wallet signals
into unified high-conviction trading signals.

Usage:
    python3 convergence_engine.py                  # Check for convergent signals now
    python3 convergence_engine.py --continuous      # Poll every 15 min
    python3 convergence_engine.py --backtest        # Historical convergence analysis
    python3 convergence_engine.py --report          # Convergence report for all active markets
"""

@dataclass
class ConvergenceSignal:
    signal_id: str
    market_question: str
    market_id: str
    direction: str                    # YES | NO
    convergence_level: int            # 1-5 (see hierarchy above)
    
    # Component signals
    news_signal: dict | None          # from NB pipeline (edge, confidence, kernel)
    whale_signal: dict | None         # from B9-01 (alias, domain, size, score)
    fresh_wallet_signal: dict | None  # from B9-02 (anomaly_score, wallet_age)
    
    # Derived
    combined_confidence: float        # 0-1
    suggested_sizing: str             # "quarter-kelly" | "half-kelly"
    kelly_usd: float
    
    # Context
    our_position: dict | None         # existing position if any
    agrees_with_position: bool | None
    
    generated_at: datetime
    status: str                       # pending | approved | rejected | executed
```

### Part 2: Market Matching

The hardest part: matching signals across three different data sources that
may describe the same market differently.

```python
def match_market(news_market: str, whale_market: str, fresh_wallet_market: str) -> bool:
    """
    Determine if signals from different sources refer to the same market.
    
    Challenges:
    - News pipeline uses market_question text from Polymarket
    - Whale scanner resolves token_id → market via Gamma API
    - Fresh wallet detector watches specific market condition_ids
    
    Matching strategies:
    1. Exact condition_id match (best, if available)
    2. Token_id match (via Gamma API lookup)
    3. Fuzzy text match on market_question (fallback)
    """
    
    # Strategy 1: condition_id
    if all_have_condition_id(news, whale, fresh):
        return news.condition_id == whale.condition_id == fresh.condition_id
    
    # Strategy 2: token overlap
    if token_sets_overlap(news, whale, fresh):
        return True
    
    # Strategy 3: fuzzy text (Jaccard on keywords, threshold 0.5)
    return fuzzy_market_match(news_market, whale_market) > 0.5
```

### Part 3: Confidence Calculation

```python
def compute_convergence_confidence(news, whale, fresh_wallet):
    """
    Combine independent signal confidences.
    
    Using Bayesian update:
    - Prior: market price (current consensus)
    - Each signal is an independent likelihood ratio
    
    Simplified formula:
    P(correct) = 1 - (1 - p_news) × (1 - p_whale) × (1 - p_fresh)
    
    Where:
    - p_news = news_signal.confidence × 0.7  (news alone is moderate)
    - p_whale = insider_edge × in_domain_weight  (domain-specific)
    - p_fresh = anomaly_score / 10 × 0.5  (unknown quality)
    """
    
    components = []
    
    if news:
        p_news = news['confidence'] * 0.7
        components.append(p_news)
    
    if whale:
        in_domain_mult = 1.0 if whale['in_domain'] else 0.3
        p_whale = min(whale['insider_edge'], 0.5) * in_domain_mult
        components.append(p_whale)
    
    if fresh_wallet:
        p_fresh = (fresh_wallet['anomaly_score'] / 10) * 0.5
        components.append(p_fresh)
    
    if not components:
        return 0.0
    
    # Combined: 1 - product of (1 - p_i)
    combined = 1.0
    for p in components:
        combined *= (1 - p)
    
    return 1 - combined
```

### Part 4: Sizing Rules

```python
def compute_sizing(convergence_level, combined_confidence, current_price, bankroll):
    """
    Position sizing based on convergence level.
    
    Rules:
    - Level 1 (news only): Paper trade, no real money
    - Level 2-3 (two signals): Quarter-Kelly
    - Level 4-5 (three signals or whale+fresh): Half-Kelly
    
    Always subject to R01 rules:
    - C1: max 3% of bankroll per event
    - C2: max 10% per domain
    - C3: correlation check
    """
    
    edge = combined_confidence - current_price if direction == "YES" else (1 - combined_confidence) - (1 - current_price)
    
    if edge < 0.05:
        return 0  # No edge, no trade
    
    if convergence_level <= 1:
        return 0  # Paper only
    elif convergence_level <= 3:
        kelly_fraction = 0.25  # Quarter-Kelly
    else:
        kelly_fraction = 0.50  # Half-Kelly (max conviction)
    
    full_kelly = edge / (1 - current_price)
    sized = full_kelly * kelly_fraction * bankroll
    
    # Apply caps
    c1_cap = bankroll * 0.03  # 3% event cap
    return min(sized, c1_cap)
```

### Part 5: Convergence Scanner Loop

```python
def scan_for_convergence(db_conn, lookback_hours=4):
    """
    Main convergence scan:
    1. Fetch recent news signals (last N hours)
    2. Fetch recent whale trades (last N hours)
    3. Fetch recent fresh wallet anomalies (last N hours)
    4. Group all by market (using market matching)
    5. For each market with 2+ signal types: compute convergence
    6. Generate ConvergenceSignal for any level ≥ 2
    """
    
    news_signals = fetch_recent_news_signals(db_conn, lookback_hours)
    whale_trades = fetch_recent_whale_trades(db_conn, lookback_hours)
    fresh_anomalies = fetch_recent_anomalies(db_conn, lookback_hours)
    
    # Group by market
    markets = group_by_market(news_signals, whale_trades, fresh_anomalies)
    
    convergent = []
    for market_key, signals in markets.items():
        n_sources = sum([
            1 if signals.get('news') else 0,
            1 if signals.get('whale') else 0,
            1 if signals.get('fresh') else 0,
        ])
        
        if n_sources < 2:
            continue
        
        # Check direction agreement
        directions = set()
        if signals.get('news'): directions.add(signals['news']['direction'])
        if signals.get('whale'): directions.add(signals['whale']['direction'])
        if signals.get('fresh'): directions.add(signals['fresh']['direction'])
        
        if len(directions) > 1:
            # Signals disagree — log as conflict, don't trade
            log_conflict(market_key, signals)
            continue
        
        # All agree — compute convergence
        level = compute_convergence_level(signals)
        confidence = compute_convergence_confidence(
            signals.get('news'), signals.get('whale'), signals.get('fresh'))
        
        convergent.append(ConvergenceSignal(
            signal_id=f"CV-{market_key[:8]}-{datetime.now().strftime('%H%M')}",
            market_question=market_key,
            direction=directions.pop(),
            convergence_level=level,
            news_signal=signals.get('news'),
            whale_signal=signals.get('whale'),
            fresh_wallet_signal=signals.get('fresh'),
            combined_confidence=confidence,
            # ... fill remaining fields
        ))
    
    return convergent
```

### Part 6: Alert Format

```
🎯 CONVERGENCE SIGNAL [Level 4/5] — CV-abc12345

Market: Will US or Israel strike Iran by March 31?
Direction: NO | Combined confidence: 78%

📰 NEWS: Divergence 5.5 — Western: talks progressing | Russian: collapse imminent
   Truth kernel: "Geneva round 2 set for next week. No breakdown in dialogue."
   Edge: +8pp vs market

🐋 WHALE: ricosuave666 [10/10 insider, GEO specialist]
   Bought $15K NO @ 47¢ (2 hours ago)
   In-domain: ✅ | Historical GEO edge: +48.3%

🆕 FRESH WALLET: 0x7a3f... [Score 8/10]
   Created 3 days ago, 2 prior txns
   Bought $8K NO @ 46¢ (45 min ago)
   Funded from Coinbase deposit

Sizing: Half-Kelly = $142 (1.4% of bankroll)
Strategy: S006 (time decay) + S010 (whale follow)

Our position: LT001 NO @ 41¢ — AGREES ✅
Action: Consider adding $142 to LT001

Reply A=Approve R=Reject I=Details
```

### Part 7: Conflict Detection

When signals DISAGREE — this is also valuable information:

```
⚠️ SIGNAL CONFLICT — Iran strike market

📰 NEWS says: NO (talks progressing, divergence 4.2)
🐋 WHALE says: YES (Cashy bought $20K YES, GEO domain)
🆕 FRESH says: YES (unknown wallet, $12K YES, score 6/10)

2 vs 1 in favor of YES. News pipeline may be lagging whale intel.

Action: DO NOT add to position. Monitor closely.
If whale + fresh are correct, our NO position is at risk.
```

### Part 8: Tests

```python
class TestConvergenceLevel:
    def test_news_only_level_1(self):
    def test_news_plus_whale_level_2(self):
    def test_news_plus_fresh_level_3(self):
    def test_whale_plus_fresh_level_4(self):
    def test_all_three_level_5(self):

class TestMarketMatching:
    def test_exact_condition_id_match(self):
    def test_fuzzy_text_match(self):
    def test_different_markets_no_match(self):

class TestConfidenceCalculation:
    def test_single_source_moderate(self):
    def test_two_sources_higher(self):
    def test_three_sources_highest(self):
    def test_out_of_domain_whale_discounted(self):

class TestDirectionConflict:
    def test_all_agree_no_conflict(self):
    def test_disagreement_logged_not_traded(self):

class TestSizing:
    def test_level_1_zero_sizing(self):
    def test_level_2_quarter_kelly(self):
    def test_level_4_half_kelly(self):
    def test_c1_cap_applied(self):
    def test_no_edge_no_trade(self):

class TestPortfolioAgreement:
    def test_signal_agrees_with_existing(self):
    def test_signal_contradicts_existing(self):
    def test_no_existing_position(self):
```

## Output

1. `scripts/convergence_engine.py` — full convergence scanner + continuous mode
2. `scripts/test_convergence_engine.py` — tests
3. Updated `scripts/schema.sql` — convergence_signals table
4. Alert format templates for Level 2-5 + conflict detection
5. Integration notes: how to wire into orchestrator.py

**Done when**: Convergence engine can read from all three signal sources (news DB,
whale_trades table, fresh_wallet_anomalies table), match markets across sources,
detect direction agreement/conflict, compute convergence level + confidence,
and produce formatted alerts. Tests cover all 5 convergence levels + conflict case.
