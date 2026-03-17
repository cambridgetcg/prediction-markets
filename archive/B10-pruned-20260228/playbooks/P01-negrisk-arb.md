# P01 — NegRisk Structural Arbitrage

**Phase**: ALBEDO (analysis complete, paper trading ready)
**Type**: Structural / Mechanical
**Edge hypothesis**: NegRisk multi-outcome markets systematically misprice due to fragmented order books, stale tail outcomes, and retail YES bias. The convert() mechanism makes exploitation capital-efficient. Residual opportunities persist in slow, niche, and newly-listed markets below bot attention thresholds.
**Mathematical foundation**: `research/negrisk-mathematics.md`
**Scanner**: `scripts/negrisk-scanner.py`
**Parent strategy**: Extends S007 Type 1 (overround) with NegRisk-specific mechanics
**Live scan** (2026-02-25): 94 NegRisk opportunities found above 2.5% threshold

## Why This Exists

NegRisk markets generated **$29M (73%) of $40M total arbitrage profit** on Polymarket during April 2024 - April 2025 (IMDEA, Bawa 2025). The convert() mechanism gives 29x capital efficiency over binary arbitrage. While high-frequency bots now capture most opportunities in 2.7 seconds, structural edges persist in:

1. **Low-volume niche markets** (<$50K) below bot monitoring thresholds
2. **Newly listed markets** (indexing lag: minutes to hours)
3. **Markets with many stale-priced tail outcomes** (15+ candidates)
4. **Short-duration events** (weekly resolution = better annualized returns)
5. **Non-US politics / SCI / ENV domains** with lower bot coverage

## The Two Trade Types

### Type A: Overround Play (Σ YES > 1.00) — BUY ALL NO + CONVERT

When YES prices sum to more than $1.00:

```
Entry:     Buy 1 NO in every outcome
Cost:      N - Σ pᵢ  (where N = number of outcomes)
Payout:    N-1 (the N-1 losing outcomes each pay $1.00)
Gross:     Σ pᵢ - 1 = ε (the overround)
Fee:       2% on profit per winning NO
Net:       ε - 0.02 × (Σ pᵢ - p_winner)
Breakeven: ~2.0% overround (worst case), ~3% practical (incl. spread)
```

**With convert()**: Instead of holding NOs to resolution, immediately convert to extract collateral + complementary YES tokens. Faster capital recycling.

**Scanner live findings (2026-02-25):**
- Fed Chair: 11.3% overround, $523M volume (genuine — Warsh 93.9% dominates)
- State primaries: 5-11% overround, $30K-80K volume (thin but real)
- Trump posts/counts: 10-12% overround, short duration, $27-33K volume
- Oscars predictions: 10-13% overround, resolves within days

### Type B: Underround Play (Σ YES < 1.00) — BUY ALL YES

When YES prices sum to less than $1.00:

```
Entry:     Buy 1 YES in every outcome
Cost:      Σ pᵢ < $1.00
Payout:    $1.00 (exactly one outcome wins)
Gross:     1 - Σ pᵢ = |ε|
Fee:       2% on (1 - p_winner)
Net:       |ε| - 0.02 × (1 - E[p_winner])
Breakeven: ~1.4-1.8% underround
```

**Scanner live findings (2026-02-25):**
- Kansas Governor R Primary: 11.0% underround, $31K volume
- Virginia R Senate Primary: 10.9% underround, $68K volume
- New Mexico Governor R Primary: 10.2% underround, $82K volume
- Fed rate end of 2026: 3.0% underround, $254K volume

## Entry Criteria

| Criterion | Type A (Overround) | Type B (Underround) |
|---|---|---|
| **Minimum edge** | ≥3% gross overround | ≥3% gross underround |
| **Net edge** (expected) | ≥1.0% after fees | ≥1.0% after fees |
| **Minimum liquidity** | $10K total across outcomes | $10K total across outcomes |
| **Maximum stale %** | <50% of outcomes stale | <50% of outcomes stale |
| **NegRisk flag** | Must be `negRisk: true` | `negRisk: true` preferred |
| **Mutually exclusive** | Verified (no "by date" series) | Verified (no "by date" series) |
| **Resolution window** | Prefer <6 months (better annualized) | Prefer <6 months |
| **Domain** | ANY except ECO (perfectly priced) | ANY except ECO |

### Stale Price Filter

Many apparent overrounds are artifacts of stale pricing on illiquid tail outcomes. **Filter rules**:
- If >50% of outcomes have $0 24h volume AND <$1K total volume: SKIP (stale artifact)
- If the overround is entirely attributable to one stale outcome: SKIP
- **Exception**: If the NON-stale outcomes still show >3% overround, proceed (the stale tail is noise, not the edge source)

### Verification Checklist

Before entering ANY position:
1. **Manual verification**: Open the event on polymarket.com, check that markets are still active
2. **Resolution criteria**: Read the resolution source — is it clear and unambiguous?
3. **Mutual exclusivity**: Confirm exactly one outcome must win (not "by date" or price buckets)
4. **Order book check**: Verify bid/ask depth supports your position size
5. **Fee check**: Confirm market uses standard 2% winner fee (some markets have custom fees)

## Position Sizing

This is **not Kelly** — these are structural plays with bounded risk:

```
Position size = min(
  available_liquidity × 0.5,    # Don't take more than half available depth
  bankroll × 0.05,              # 5% max bankroll per event
  edge_dollars × 0.8            # Leave 20% margin for execution slippage
)

edge_dollars = overround × position_notional
```

**Per-outcome sizing**: Split position across outcomes. For overround play with N outcomes:
- Each NO position: total_position / N
- Fill limit orders from MOST liquid outcome first (best fill probability)

**Maximum per event**: 5% of bankroll (structural but not risk-free — oracle/resolution risk exists)

## Execution Protocol

### Type A: Overround — Buy All NO

1. **Survey**: Run `negrisk-scanner.py`, identify target event
2. **Order**: Use LIMIT ORDERS only (maker = zero fee on most markets)
3. **Sequence**: Place orders on the most liquid outcomes first (highest volume)
4. **Timing**: Place all orders within 5 minutes to minimize drift
5. **Monitoring**: If partial fill, reassess — does the remaining basket still have edge?
6. **Convert (optional)**: If you obtain NO in ≥2 outcomes, consider convert() to extract collateral
7. **Exit**: Hold to resolution OR exit via convert() + sell complementary YES

### Type B: Underround — Buy All YES

1. **Survey**: Run `negrisk-scanner.py`, identify target event
2. **Order**: LIMIT ORDERS on all outcomes simultaneously
3. **Sequence**: Fill the CHEAPEST outcomes first (highest probability of fill)
4. **Minimum fill**: You need ALL outcomes filled for the arb to work — partial fill = directional bet
5. **Exit**: Hold to resolution ONLY (no early exit — you need the guaranteed $1.00)

### Execution Risk Management

- **Leg risk**: Partial fills create unwanted directional exposure. Mitigation: use limit orders at MID price, accept slower fills
- **Stale quotes**: If a tail outcome shows 5% but the book is empty, you can't actually buy it. Check depth BEFORE calculating edge
- **Convert() gas**: ~$0.10-0.50 per convert on Polygon. Negligible for positions >$50

## The "Slow Market" Screen

Markets where manual execution is viable (bot competition is minimal):

| Signal | Threshold | Why |
|---|---|---|
| 24h volume | <$5,000 | Below bot profit threshold |
| Total volume | <$100,000 | Below bot monitoring threshold |
| Outcome count | >15 | More legs = more execution complexity for bots |
| Domain | SCI, ENV, SOC, LAW | Low bot coverage (crypto/POL/sports are bot-heavy) |
| Market age | <48 hours | Indexing lag before bots add to watch list |
| Event type | State primaries, niche | Low retail attention = less bot incentive |

**Best current opportunities** (from 2026-02-25 scan):
- **State primary elections**: 5-11% over/underround, $30-80K volume, bot-light
- **Novelty count markets** (Trump posts, Andrew Tate posts): 10-12% overround, short duration
- **Oscars/entertainment**: 10-13% overround, resolves within days
- **Japan unemployment rate**: 10.3% overround, imminent resolution

## Risk Factors

| Risk | Severity | Mitigation |
|---|---|---|
| **Stale pricing artifact** | HIGH | Verify 24h volume on each outcome; stale filter |
| **Oracle manipulation** | MEDIUM | Avoid markets with ambiguous resolution criteria |
| **Partial fill / leg risk** | MEDIUM | Limit orders, fill liquid legs first |
| **Market cancellation** | LOW | Diversify across events |
| **Convert() contract risk** | LOW | NegRiskAdapter is audited; use small sizes initially |
| **Resolution delay** | LOW | Factor capital lockup into annualized return calc |

## Expected Returns

### Per-Opportunity

| Market Type | Gross Edge | Net Edge | Frequency | Annualized |
|---|---|---|---|---|
| State primaries (5-11% edge) | 8% avg | 6% avg | Monthly | 6% (long-dated) |
| Short-duration novelty (10-12%) | 11% avg | 9% avg | Weekly | 100-200% |
| Sports championships (3-5%) | 4% avg | 2% avg | Weekly | 50-100% |
| High-volume POL (3-5%) | 4% avg | 2% avg | Monthly | 12-24% |

### Annual Portfolio Estimate

```
Conservative: 5-10 trades/month × $250 avg net × 12 months = $15,000-$30,000
Moderate:     10-20 trades/month × $500 avg net × 12 months = $60,000-$120,000
Aggressive:   20+ trades/month (requires semi-automation) = $120,000+

Required capital: $5,000-$20,000 (5% per event × 4-8 concurrent events)
```

**Reality check**: The $120K+ figure requires catching opportunities quickly and near-full automation. Manual-only realistic range: **$15K-$60K/year** with $10K capital.

## Daily Workflow

```bash
# Morning scan (takes ~30s)
python3 scripts/negrisk-scanner.py --min-edge 0.025

# If opportunities found, drill into top ones:
python3 scripts/negrisk-scanner.py --min-edge 0.025 --depth  # check order books

# Also run existing scanners
python3 scripts/overround-scanner.py
python3 scripts/temporal-checker.py
```

## Relationship to Other Strategies

- **S007 (Cross-Market Arb)**: P01 is the NegRisk-specific execution layer for S007 Type 1
- **S004 (Contrarian Overreaction)**: News spikes that create overround → P01 entry signal
- **S006 (Time Decay)**: Long-dated NegRisk markets with underround may offer S006+P01 overlay
- **S011 (High-Prob Bonds)**: The >95% dominant outcome in overround markets IS a bond play

## Sources

- Bawa, N. (2025). "NegRisk Market Rebalancing: How $29M Was Extracted." Medium.
- Saguillo et al. (2025). "Unravelling the Probabilistic Forest." IMDEA/arXiv.
- Polymarket NegRisk Docs: docs.polymarket.com/developers/neg-risk/overview
- NegRisk CTF Adapter: github.com/Polymarket/neg-risk-ctf-adapter
- S007 analysis: strategies/backtests/S007-arb-analysis.md
- Mathematical derivation: research/negrisk-mathematics.md
