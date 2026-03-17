# S008 — Information Edge

**Phase**: NIGREDO (untested)
**Type**: Research-driven / Alpha generation
**Edge hypothesis**: Deep domain research can identify information that the market hasn't fully priced. Not insider info — public information that requires effort to synthesize.

## Why This Exists

This is the purest expression of the system's purpose. The entire knowledge domain structure (GEO, POL, ECO, etc.) exists to build enough understanding to spot when markets are wrong.

This strategy says: **do the homework the market hasn't done.**

## Types of Information Edge

### Type A: Synthesis Edge
Combining information from multiple sources that individually are known but whose implications haven't been connected.
- Example: Military logistics data + diplomatic timeline + budget allocation → strike probability

### Type B: Base Rate Edge  
Knowing the historical frequency of similar events better than the market.
- Example: "How often do announced tariffs actually get implemented?" → check historical base rate

### Type C: Model Edge
Having a better mental model for the domain than the average market participant.
- Example: Understanding Fed reaction functions better → better rate prediction

### Type D: Speed Edge
Being faster to process new information and understand its implications.
- Example: New economic data released → understand the Fed implications before market adjusts

### Type E: Attention Edge
Noticing markets that are stale or forgotten while relevant new information exists.
- Example: A market at 30% hasn't moved in weeks, but domain context has changed significantly

## Rules

### Research Process
1. **Survey**: Read domain context.md, check sources.md
2. **Deep dive**: Pick a specific market. Read everything relevant.
3. **Synthesize**: What do I know that the market might not be weighting?
4. **Estimate**: Form probability estimate BEFORE checking current market price
5. **Compare**: Check market price. If divergence ≥10%, identify which type of edge (A-E)
6. **Validate**: Can I articulate WHY the market is wrong? If not, assume I'm wrong.

### Entry
- Must document the specific information edge in the trade log
- Must classify edge type (A through E)
- Size: proportional to conviction + edge type:
  - Type A (synthesis): 5% — strong but hard to verify
  - Type B (base rate): 8% — verifiable, high confidence when solid
  - Type C (model): 5% — could be wrong model
  - Type D (speed): 3% — transient edge, market will catch up
  - Type E (attention): 5% — easy to check, edge may vanish

### Exit
- Follow S001 (hold to resolution) as default
- If the information I identified becomes consensus → take profit (edge is gone)
- If new information contradicts my thesis → exit regardless of P&L

### Research Log
Every S008 trade must have a corresponding entry in `domains/XX/research/` documenting:
- The specific information synthesized
- Why the market hasn't priced it
- What would change my mind

## Expected Edge

This is where the domain structure pays off. Over time:
- context.md files build cumulative knowledge
- sources.md files create reliable information pipelines
- research/ folders document what worked and what didn't
- The calibration system measures whether this knowledge actually translates to edge

## What Would Kill This Strategy

- Markets are more efficient than I think → my "edges" are noise
- I have analysis paralysis → spend too long researching, miss the window
- My information synthesis is wrong → confident but wrong is worse than uncertain
- The research effort isn't worth the edge → negative ROI on time

## The Meta-Strategy

S008 is really a **meta-strategy** — it's the reason all the other strategies exist. If the calibration system shows I have edge in a domain, that's an S008-type-C signal. If the time decay math works, that's S008-type-B confirmed. Everything feeds into and from this.

## Evolution Hooks

- Track which edge types are most profitable
- Track which domains yield the most information edge
- Build "information half-life" metric — how long does an edge persist before the market catches up?
- Automated stale market scanner (markets that haven't moved but should have)
- Cross-reference with Ouroboros: domain understanding quality feeds into loop sensing
