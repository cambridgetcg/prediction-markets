# S006 — Time Decay

**Phase**: ALBEDO (backtested, ready for paper trading)
**Type**: Structural / Patience
**Edge hypothesis**: Markets with expiration dates have an inherent time value. As time passes without an event occurring, "No" becomes more likely mechanically. Sell overpriced time premium.
**Backtest result**: 73.5% NO resolution rate across 804 resolved markets (see `backtests/S006-time-decay-backtest.md`)

## Why This Exists

Many Polymarket events are structured as "Will X happen by [date]?" These are analogous to options — they have time value that decays as the deadline approaches.

Consider: "US strikes Iran by March 31" at 57%. If 20 of 37 days pass with no strike, the daily hazard rate implied by 57% gets compressed into fewer remaining days, making the YES price too high unless you believe the daily probability increases over time.

## The Math

### Constant Hazard Model (Primary)
For a "by [date]" market at price P with N days remaining:
- P(event by day N) = 1 - (1-p)^N
- Implied daily p = 1 - (1 - P)^(1/N)

### Decreasing Hazard Model (Most Realistic)
Each day without the event makes it less likely: p_day_k = p_0 × decay^k (decay=0.98)
- Initial probability is higher than constant model
- More appropriate for military action, political promises, market milestones

### Increasing Hazard Model (Rare)
Escalation scenarios where risk grows: p_day_k = p_0 × growth^k (growth=1.02)
- Applicable to: deadline-driven events, government shutdowns

### Edge Detection
If implied daily p > 2× domain base rate → signal to buy NO.

**Screening tool**: `scripts/time-decay-screener.py`

## Rules

### Qualifying Markets
- "Will X happen by [date]?" structure
- 14-90 days remaining (sweet spot)
- **YES price < 25%** (genuine tail event where time decay works mechanically). Above 25%, the trade is S004 (contrarian) or S001 (directional hold), NOT S006. (Scorecard 2026-02-25: T001 at 66.5% YES was misclassified S006 → reclassified S004.)
- Entry range: YES 8-25% (buy NO at 75-92c). The original 40-65% range is S004 territory.
- Implied daily p ≥ 2× domain base rate
- The event has NOT been trending more likely (no momentum)

### Domain Priority (by backtest NO rate)
| Priority | Domain | NO Rate | Notes |
|----------|--------|---------|-------|
| 1 | CRY | 69.5% | Strong edge + best liquidity |
| 2 | OTHER | 80.0% | Strongest edge + high volume |
| 3 | POL | 78.3% | Strong edge, moderate volume |
| 4 | ENV | 82.4% | Strongest edge but low liquidity |
| 5 | TEC | 63.6% | Moderate edge |
| Avoid | GEO | 64.3% | Weakest edge + highest correlation risk |
| Avoid | ECO | 60.0% | Marginal edge, efficient pricing |

### Entry
- Run screener: `python3 scripts/time-decay-screener.py --min-days 14 --multiplier 2`
- Review top opportunities manually (screener is a filter, not a decision-maker)
- Verify no imminent catalyst that would justify current YES price
- Size: 3-5% of bankroll (quarter Kelly)

### Exit
- **Target**: Hold to resolution (73.5% resolve NO historically)
- **Stop-loss**: If position drops 30%, reassess thesis
- **Hard exit**: If fundamental catalyst materializes (troops deploy, deal signed, law enacted)
- **Partial exit**: If market moves 20%+ against you on real news, re-evaluate

### Time Decay Tracking

For each position, track:
```
Entry:  Day 1 of 37, market at 57%, implied daily p = 2.3%
Day 10: Day 10 of 37, market at ??, implied daily p = ??
Day 20: Day 20 of 37, market at ??, implied daily p = ??
```

If the event hasn't happened and the price hasn't dropped proportionally, more time premium remains to capture.

## Expected Edge

"Will X happen by [date]?" markets are systematically overpriced because:
1. Humans overweight dramatic/scary outcomes (availability bias)
2. Media coverage makes events feel imminent (salience)
3. Most threatened events don't happen (base rate neglect)
4. Time premium is invisible to casual bettors

## What Would Kill This Strategy

- Events actually happen at the rate the market implies → no overpricing
- Black swans: one catastrophic loss on a YES resolution wipes many small NO wins
- Liquidity: NO positions may be hard to exit if market panics
- Correlated events: multiple "by date" markets could all trigger on the same catalyst

## Risk Management (Critical)

This strategy has **negative skew**: many small wins, occasional large loss. Must:
- Never let one position exceed 5% of bankroll
- Max 6-8 concurrent positions (30% max capital deployed)
- Max 30% of bankroll in any single domain
- Max 2 positions per geopolitical conflict/theater (correlation protection)
- Hard stops based on fundamental changes (not just price movement)
- Track maximum theoretical loss across all positions
- Keep 70% of bankroll in reserve

### Kelly Criterion Reference
| Entry YES | Quarter Kelly |
|-----------|--------------|
| 40% | 8.4% |
| 50% | 11.8% |
| 60% | 14.0% |

Use 3-5% as practical cap regardless of Kelly output.

## Backtested Performance (2024-2026)

- **Overall NO rate**: 73.5% (804 markets)
- **Conservative annual ROI estimate**: +30-60% (reality-adjusted)
- **Sharpe estimate**: 2.6-4.5 at typical entry (assuming independence)
- **Max monthly drawdown observed**: ~80% YES months existed (Jan 2025, Aug 2025)
- See: `backtests/S006-time-decay-backtest.md` for full analysis

## Evolution Hooks

- ~~Implied daily probability calculator → automated screening tool~~ **DONE**: `scripts/time-decay-screener.py`
- ~~Domain-specific base rates~~ **DONE**: Calibrated in backtest
- **S006a**: Time decay + S004 contrarian overlay (enter after YES spikes on rhetoric)
- **S006b**: Domain-weighted sizing (bigger positions in ENV/POL, smaller in GEO)
- **S006c**: Dynamic base rates that update with new resolution data
- **S006d**: Decreasing hazard model for entry timing (enter after N quiet days)
- Optimal entry window: backtest suggests 14-90 days is sweet spot
- Hedging: pair with S005 momentum on a related market
