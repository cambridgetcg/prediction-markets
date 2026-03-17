# S002 — Threshold Exit

**Phase**: NIGREDO (untested)
**Type**: Risk management / Profit-taking
**Edge hypothesis**: Markets overshoot on news. Taking profits when odds move significantly in your favor locks in gains that might revert.

## Why This Exists

Hold-to-resolution leaves money on the table when a market swings heavily in your favor but hasn't resolved yet. This strategy captures that by exiting at predetermined thresholds.

## Rules

### Entry
- Same as S001: ≥10% divergence between my estimate and market
- Same sizing rules

### Exit (the difference)
- **Profit target**: Exit when position is worth ≥1.5x entry cost
  - Bought at 0.40 → sell at 0.60+ (50% profit)
- **Stop loss**: Exit when position loses ≥40% of value
  - Bought at 0.40 → sell if drops to 0.24
- **Time decay trigger**: If <7 days to resolution and position is profitable, hold to resolution (switch to S001 behavior)
- **Momentum override**: If price moves >15% in my direction in <24h, tighten stop to breakeven

### Threshold Variants (test simultaneously)

| Variant | Profit Target | Stop Loss | Notes |
|---------|--------------|-----------|-------|
| S002a | 1.3x (30%) | -30% | Tight |
| S002b | 1.5x (50%) | -40% | Standard |
| S002c | 2.0x (100%) | -50% | Wide |
| S002d | Trailing 20% | -40% | Trailing stop |

## Expected Edge

Markets are noisy. Prices overshoot in both directions. If I can:
1. Enter with correct direction (calibration edge)
2. Capture the overshoot without waiting for resolution (timing edge)
3. Cut losses before they compound (risk management)

Then I should achieve better risk-adjusted returns than S001, even if raw ROI is similar.

## What Would Kill This Strategy

- Markets don't overshoot enough → thresholds never hit, degrades to S001
- My entries are wrong often → stops trigger frequently, death by a thousand cuts
- Whipsaws: price hits stop then reverses → worse than S001

## Metrics to Track

- Same as S001, plus:
- Average hold time (vs S001)
- Stop-loss trigger rate
- Profit-target trigger rate
- Missed gains (what would S001 have returned on the same trades?)

## Evolution Hooks

- Optimal threshold discovery: which variant (a/b/c/d) performs best?
- Domain-dependent thresholds: GEO markets may need wider stops than ECO
- Volatility-adjusted thresholds: scale stops with market's historical volatility
