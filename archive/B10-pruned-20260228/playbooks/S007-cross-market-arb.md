# S007 — Cross-Market Arbitrage

**Phase**: ALBEDO (analysis complete, paper trading ready)
**Type**: Structural / Relational
**Edge hypothesis**: Related markets sometimes misprice relative to each other. When the sum of probabilities in a mutually exclusive set exceeds 100%, or when logically linked markets are inconsistent, there's a free edge.
**Analysis**: `strategies/backtests/S007-arb-analysis.md` (2026-02-23)
**Tools**: `scripts/overround-scanner.py`, `scripts/temporal-checker.py`
**Spec**: `scripts/cross-platform-spec.md`

## Why This Exists

Polymarket has many markets that are logically connected:
- "Republican Nominee 2028" candidates should sum to ~100% → **actual: 150% (49.7% overround)**
- "US strikes Iran by March" YES should be ≤ "US strikes Iran by June" YES → **confirmed consistent**
- "Fed cuts in March" should be consistent with "Fed decision in March" → **confirmed consistent (100.1%)**
- "Best AI model" probabilities should sum to ~100% → **slight overround**

When they don't, someone is wrong — and the tools now detect it automatically.

## Types of Arbitrage

### Type 1: Overround (Sum > 100%) — PRIMARY
Multi-outcome markets where all YES prices sum to more than 100%.
- **Edge**: Buy the most underpriced NO, or sell the overpriced basket
- **Scanner**: `scripts/overround-scanner.py` (daily run)
- **Live findings** (2026-02-23):
  - Republican Nominee 2028: +49.7% overround (partly stale RFK Jr. pricing)
  - Fed Chair: +10.3% overround (Warsh 94.35%)
  - Presidential Election 2028: **-3.0% underround** (buy all YES = guaranteed profit)
  - Fed March Decision: 0.0% (perfectly priced — ECO domain)
- **Threshold**: ≥3% mispricing after accounting for spread
- **Key insight**: Need 2.5-3% overround to profit after Polymarket's 2% winner fee (T11)

### Type 2: Temporal Consistency — SECONDARY
"By date" markets with nested deadlines should be monotonically increasing.
- **Edge**: If "by March" = 57% and "by April" = 55%, that's inconsistent — one is mispriced
- **Scanner**: `scripts/temporal-checker.py` (daily run)
- **Live findings** (2026-02-23):
  - 155 temporal series analyzed, 22 with violations
  - Iran "US strikes by..." cumulative series: CONSISTENT (17 markets, monotonic)
  - Token launches (Paradex, Fomo, Oro): VIOLATIONS (5-21% edges)
  - "US forces in Venezuela": VIOLATION (13.5% edge)
  - BTC/ETH "on date" markets: FALSE POSITIVES (point-in-time, not cumulative)
- **CRITICAL**: Distinguish "by date" (cumulative → must be monotonic) from "on date" (point-in-time → no constraint)
- **CRITICAL**: "NOT by date" markets have INVERTED temporal direction

### Type 3: Logical Implication — TERTIARY
If A implies B, then P(A) ≤ P(B).
- **Current status**: Extremely rare violations on Polymarket. The US vs US/Israel Iran strike chain has a 0.5% discrepancy (within noise).
- **Frequency**: Too low to actively scan. Monitor manually when doing domain research.

### Type 4: Cross-Platform — DEPRIORITIZED
Same market on Polymarket vs Metaculus vs Kalshi at different prices.
- **Current status**: Windows compressing from minutes to seconds (T07). Not viable for manual trading.
- **Better use**: Metaculus/Manifold consensus as calibration signal for S004/S008.
- **Spec**: `scripts/cross-platform-spec.md` (design only, not built)

## Rules

### Screening
```bash
# Daily morning scan (~90 seconds total)
python3 scripts/overround-scanner.py      # Type 1: overround
python3 scripts/temporal-checker.py       # Type 2: temporal consistency
python3 scripts/spike-detector.py         # S004: overreaction (complementary)
```

### Entry
- Only enter when mispricing is **≥3%** (covers spread, 2% winner fee, and execution friction)
- Hedge both sides where possible (pure arb via neg-risk conversion)
- If can't hedge: take the more confident side, size at 3% of bankroll
- **Type 1 priority**: Buy all YES on underround events (guaranteed profit)
- **Type 2 priority**: Buy YES on underpriced later date, sell YES on overpriced earlier date

### Exit
- Pure arb: hold to resolution (guaranteed profit)
- Impure arb (one-sided): exit when mispricing corrects or at resolution

## Domain Priority

| Priority | Domain | Best Arb Type | Evidence |
|----------|--------|---------------|----------|
| 1 | **POL** | Type 1 (overround in nominations) | 49.7% GOP, -3% Presidential underround |
| 2 | **CRY** | Type 2 (token launch series) | Paradex, Fomo, Oro temporal violations |
| 3 | **GEO** | Type 2 (nested deadlines) | Venezuela 13.5% violation; Iran consistent |
| 4 | **ECO** | Type 1 (Fed Chair) | 10.3% overround |
| SKIP | **ECO** (decisions) | None | 0.0% — perfectly efficient |

## Expected Edge

- **Type 1**: 3-10% on liquid multi-outcome events, always present in POL
- **Type 2**: 5-21% when violations occur, but sporadic (mostly token launches)
- **Combined**: Estimated 5-15% annualized return on deployed capital

## What Would Kill This Strategy

- Mispricings too small after 2% winner fee + spread (need ≥2.5%)
- Mispricings correct before entry (likely for Type 2 in liquid markets)
- Resolution risk (platform rule changes, market cancellations)
- Neg-risk mechanics change

## Evolution Hooks (Status)

- **Automated overround scanner** → BUILT (`overround-scanner.py`)
- **Temporal consistency checker** → BUILT (`temporal-checker.py`)
- **Cross-platform price feed** → DESIGNED (`cross-platform-spec.md`), not built
- **Logical dependency graph** → LOW PRIORITY (too few violations)
- **Neg-risk optimizer** → TODO (calculate optimal position sizing accounting for neg-risk conversion)
- **False positive filter** → TODO (distinguish "by date" from "on date" from "not by date" automatically)
