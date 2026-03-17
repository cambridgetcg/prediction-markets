# S001 — Hold to Resolution

**Phase**: NIGREDO (untested)
**Type**: Baseline / Control
**Edge hypothesis**: If my calibration is better than the market, buying underpriced outcomes and holding to resolution should be profitable over time.

## Why This Exists

This is the **control strategy**. Every other strategy is measured against this. If you can't beat buy-and-hold-to-resolution with your fancy exits and timing, your complexity is waste.

## Rules

### Entry
- **Signal**: My independent estimate diverges from market price by ≥10%
- **Direction**: Buy YES if I estimate higher than market; buy NO if I estimate lower
- **Size**: Proportional to conviction gap:
  - 10-20% divergence → 3% of bankroll
  - 20-30% divergence → 5% of bankroll
  - 30%+ divergence → 8% of bankroll
- **Research minimum**: Must have read domain context.md and done ≥1 web research pass

### Exit
- **Only on resolution**. No early exit. Ever.
- This is the point — we're testing calibration, not timing.

### Position Management
- No averaging down/up
- No hedging
- Set and forget

## Expected Edge

If my Brier score is better than the market's, this should be profitable. The magnitude depends on:
1. How often I disagree with the market (frequency)
2. How right I am when I disagree (accuracy)
3. How large the disagreements are (magnitude)

## What Would Kill This Strategy

- My calibration is consistently worse than the market → stop trading, improve calibration first
- Edge exists but is too small to cover transaction costs → need larger divergences
- Edge exists only in certain domains → specialize (spawn domain-specific variant)

## Metrics to Track
- ROI per trade
- Win rate
- Average edge vs market
- Domain breakdown
- Brier score: mine vs market (on traded markets only)

## Evolution Hooks
- If profitable in some domains but not others → spawn S001a (domain-specialized)
- If profitable but drawdowns are painful → spawn S001b (position-sizing variant)
- Compare against every other strategy as baseline
