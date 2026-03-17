# S005 — Momentum Rider

**Phase**: NIGREDO (untested)
**Type**: Trend following
**Edge hypothesis**: Once a market starts moving in a direction on real information, it often continues further than expected because new participants and narrative reinforcement create persistent trends.

## Why This Exists

The opposite bet from S004. Both can be true — overreactions happen on spikes, but sustained trends exist on slower structural shifts. The key is distinguishing:
- **Spike** (single event, fast move) → S004 fades it
- **Trend** (accumulating evidence, gradual move) → S005 rides it

## Rules

### Trigger
- A market moves ≥10% over 7+ days in a consistent direction
- At least 2 distinct information events support the direction (not just one)
- Volume is increasing (more participants confirming the trend)

### Entry
- Enter in the direction of the trend
- Wait for a 3-5% pullback within the trend (buy the dip in a trend)
- Size: 5% of bankroll (trends have better risk/reward than contrarian)

### Exit
- **Trailing stop**: 15% from peak favorable price
- **Trend break**: If market reverses >10% from recent peak, exit
- **Target**: If market reaches 80%+ (for YES) or 20%- (for NO), take profit — extreme prices have limited upside
- **Time**: Hold as long as trend persists, max 30 days

### Trend Confirmation Signals
- Multiple supporting news events
- Increasing volume and liquidity
- Other related markets moving in the same direction (correlation)
- Expert/analyst consensus shifting

### Trend Exhaustion Signals
- Volume declining while price still moving
- Supporting narrative becoming consensus ("everyone knows this")
- Contrarian voices getting louder with good arguments
- Price approaching extremes (>85% or <15%)

## Expected Edge

Behavioral finance consistently shows:
- Underreaction to gradual information (slow Bayesian updating)
- Trending persists in prediction markets similar to financial markets
- Narrative momentum creates self-reinforcing cycles

## What Would Kill This Strategy

- Trends don't exist in prediction markets (random walk) → entering noise
- Trends exist but reverse right after entry → whipsawed
- My trend identification is just hindsight → only see trends after they're done

## Tension With S004

S004 and S005 are natural enemies. The meta-question: is this move a spike or a trend?

**Decision rule**:
- Fast (1-2 days), single-cause → spike → S004
- Slow (7+ days), multi-cause → trend → S005
- Ambiguous → skip (sit out, observe, learn)

Tracking which classification is more often correct will itself be valuable data.

## Evolution Hooks

- Optimal trend definition (10% over 7 days? 15% over 14 days?)
- Domain-specific trend behavior (crypto trends harder than political?)
- Combine with S003: trend that has a known catalyst ahead → stronger signal
- Trend strength scoring → position size proportional to strength
