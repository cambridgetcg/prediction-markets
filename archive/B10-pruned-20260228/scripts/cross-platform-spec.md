# Cross-Platform Price Comparison — Design Specification

**Date**: 2026-02-23
**Status**: Design only (not implemented)
**Purpose**: S007 Type 4 — detect price discrepancies on the same question across prediction market platforms

---

## 1. Target Platforms

| Platform | API Access | Market Type | Fees | Position Limits |
|----------|-----------|-------------|------|-----------------|
| **Polymarket** | Public REST (Gamma + CLOB) | Crypto-settled, binary/multi | 0% trading fee | None |
| **Metaculus** | Public REST (`metaculus.com/api2/`) | Reputation-based, continuous | N/A (not real-money) | N/A |
| **Manifold** | Public REST (`api.manifold.markets/v0/`) | Play-money + Mana | N/A | N/A |
| **Kalshi** | REST (requires auth) | USD-settled, binary | 1% fee | $25K event limit |
| **PredictIt** | Limited (no official API) | USD-settled, binary | 10% profit fee + 5% withdrawal | $850/contract |

### Viability Assessment

- **Polymarket ↔ Kalshi**: Only actionable cross-platform arb (both real-money). But different settlement currencies (USDC vs USD), different resolution rules, and Kalshi's fee structure erodes small edges.
- **Polymarket ↔ Metaculus/Manifold**: Useful for calibration signals (if Metaculus consensus differs from Polymarket price, who's more accurate?) but NOT for financial arb since Metaculus/Manifold aren't real-money platforms.
- **Historical accuracy**: PredictIt was 93% accurate vs Polymarket's 67% on 2024 elections (Clinton & Huang 2025). Platform-specific biases are real.

---

## 2. Data Model

### Market Identity

The core problem: matching "the same question" across platforms with different wording.

```python
class CrossPlatformMarket:
    """A question tracked across multiple platforms."""

    # Canonical form
    canonical_question: str     # Normalized question text
    category: str               # GEO, POL, ECO, etc.
    resolution_date: str        # ISO date
    resolution_criteria: str    # How outcome is determined

    # Platform-specific instances
    instances: list[PlatformInstance]

class PlatformInstance:
    """A specific market on one platform."""

    platform: str               # 'polymarket', 'kalshi', 'metaculus', 'manifold'
    market_id: str              # Platform-native ID
    question_text: str          # Exact wording on that platform
    yes_price: float            # Current YES price (0-1)
    last_updated: datetime
    volume: float               # In USD equivalent
    liquidity: float            # Available liquidity
    resolution_rules: str       # Platform-specific resolution text

    # For arb calculation
    buy_yes_cost: float         # Actual cost including spread
    sell_yes_revenue: float     # Revenue after spread
    fees_pct: float             # Platform fees
```

### Matching Algorithm

Markets should be matched by:
1. **Exact canonical match**: Same normalized question text (after removing platform-specific prefixes/suffixes)
2. **Fuzzy match**: TF-IDF or embedding similarity > 0.9, same resolution date ± 3 days
3. **Manual curation**: Known equivalent markets stored in a mapping file

```python
# Example mapping file: cross-platform-mappings.json
{
    "mappings": [
        {
            "canonical": "US strikes Iran by March 31, 2026",
            "polymarket": "110790003121442365...",  # clobTokenId
            "kalshi": "IRAN-STRIKE-2026MAR",        # Kalshi ticker
            "metaculus": 12345,                      # Metaculus question ID
        },
        ...
    ]
}
```

---

## 3. API Integration Design

### Polymarket (implemented — reuse from existing scripts)

```python
def fetch_polymarket_price(token_id: str) -> float:
    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval=1h"
    # Returns tick-level trade data
    # Current price = last trade price
```

### Kalshi

```python
def fetch_kalshi_price(ticker: str) -> float:
    # Requires API key + auth
    url = f"https://trading-api.kalshi.com/trade-api/v2/markets/{ticker}"
    headers = {"Authorization": f"Bearer {api_key}"}
    # Returns: yes_price, no_price, volume, open_interest
```

### Metaculus

```python
def fetch_metaculus_price(question_id: int) -> float:
    url = f"https://www.metaculus.com/api2/questions/{question_id}/"
    # Returns: community_prediction (median), number of forecasters
    # Note: This is a probability estimate, not a market price
```

### Manifold

```python
def fetch_manifold_price(market_id: str) -> float:
    url = f"https://api.manifold.markets/v0/market/{market_id}"
    # Returns: probability (current market price), volume, liquidity
```

---

## 4. Arb Detection Logic

```python
def detect_cross_platform_arb(market: CrossPlatformMarket,
                              min_edge: float = 0.03) -> dict:
    """Detect price discrepancies across platforms."""

    # Get prices from all platforms
    prices = {}
    for inst in market.instances:
        prices[inst.platform] = {
            'buy_yes': inst.buy_yes_cost,
            'sell_yes': inst.sell_yes_revenue,
            'fees': inst.fees_pct,
        }

    # Find max and min prices
    best_buy = min(prices.items(), key=lambda x: x[1]['buy_yes'])
    best_sell = max(prices.items(), key=lambda x: x[1]['sell_yes'])

    # Calculate edge after fees
    buy_platform, buy_data = best_buy
    sell_platform, sell_data = best_sell

    gross_edge = sell_data['sell_yes'] - buy_data['buy_yes']
    net_edge = gross_edge - buy_data['fees'] - sell_data['fees']

    if net_edge >= min_edge:
        return {
            'canonical': market.canonical_question,
            'buy_on': buy_platform,
            'buy_price': buy_data['buy_yes'],
            'sell_on': sell_platform,
            'sell_price': sell_data['sell_yes'],
            'gross_edge': gross_edge,
            'net_edge': net_edge,
            'action': f"Buy YES on {buy_platform} at {buy_data['buy_yes']:.1%}, "
                      f"Sell YES on {sell_platform} at {sell_data['sell_yes']:.1%}",
        }

    return None
```

---

## 5. Known Challenges

### Resolution Risk
Different platforms may resolve the "same" question differently:
- Polymarket: "US strikes Iran" may include proxy strikes via Israel
- Kalshi: May define "US strikes" as only direct US military action
- This is the #1 risk in cross-platform arb and has caused real losses

### Execution Friction
- Polymarket: USDC on Polygon, crypto wallet required
- Kalshi: USD, US bank account required
- Can't atomically execute both legs — one may move before the other

### Fee Asymmetry
- Polymarket: 0% trading fee (but gas costs on Polygon)
- Kalshi: 1% fee on profits
- PredictIt: 10% profit fee + 5% withdrawal fee
- A 5% apparent price gap between Polymarket and PredictIt may be entirely consumed by PredictIt's fees

### Timing
- Meta-lesson T07: Cross-platform arb windows have compressed from minutes to seconds
- Manual cross-platform trading is too slow for most opportunities
- Automated execution would require API keys on both platforms + a co-located server

---

## 6. Implementation Roadmap

### Phase 1: Signal Only (Now)
- Manually curate 10-20 high-volume markets that exist on both Polymarket and Kalshi/Metaculus
- Daily price comparison (manual or simple script)
- Log discrepancies for calibration — are Polymarket prices systematically biased vs. other platforms?
- **No execution** — information only

### Phase 2: Calibration Signal (Month 2)
- Use Metaculus/Manifold as "wisdom of crowds" calibration
- When Polymarket price diverges >10% from Metaculus consensus, flag as potential S004/S008 opportunity
- This isn't arb — it's using cross-platform data as an information edge

### Phase 3: Automated Scanning (Month 3+)
- Build matcher using embedding similarity (requires API for OpenAI/Claude embeddings)
- Automated daily scan across 2-3 platforms
- Alert when net edge > 3%
- Still manual execution (automated trading is Phase 4)

### Phase 4: Automated Execution (Future)
- Only if Phase 3 validates sufficient frequency of actionable signals
- Requires Kalshi API key + Polymarket trading bot
- Co-located execution to minimize timing risk
- Capital allocation: max 5% bankroll per cross-platform trade

---

## 7. Recommendation

**Don't build cross-platform arb yet.** The meta-lesson (T07) is clear: windows are compressing, institutional competition is fierce, and the resolution risk (different platforms defining questions differently) is the silent killer. Instead:

1. **Focus on intra-Polymarket Type 1 (overround) and Type 2 (temporal)** — less competed, no cross-platform friction
2. **Use Metaculus/Manifold as calibration signals** for S004 (overreaction) and S008 (information edge) — this is the real cross-platform alpha
3. **Revisit cross-platform arb** only if Phase 1 signal collection shows consistent >5% discrepancies after fees
