# S009 — Oracle Trader

**Phase**: NIGREDO (researched, not yet backtested)
**Type**: Resolution Risk Pricing / Overlay
**Edge hypothesis**: Markets with ambiguous resolution criteria have mispriced resolution risk. Retail traders price only event probability; the true price should be event_probability × resolution_probability. The gap is exploitable.
**Research**: `research/resolution-window-analysis.md`, `strategies/evolution/new-strategy-research.md`

## Why This Exists

Every Polymarket market has two layers of uncertainty:

1. **Event probability**: Will the event actually happen in the real world?
2. **Resolution probability**: IF the event happens, will UMA's oracle interpret it as satisfying the market's resolution criteria?

Most traders price only layer 1. Layer 2 creates systematic mispricing:

```
True price = P(event) × P(resolution_YES | event) + P(no event) × P(resolution_YES | no event)

For a well-defined market:   P(res|event) ≈ 1.0  → true ≈ market
For an ambiguous market:     P(res|event) ≈ 0.6  → true < market
```

**Example**: "US strikes Iran by March 31" at 60% YES.
- P(some US military action involving Iran) = 65%
- P(UMA resolves YES | military action occurs) = 70% (does a drone strike count? does cyber count? does a proxy strike count?)
- True YES = 0.65 × 0.70 = 0.455 = 45.5%
- Market at 60% → 14.5pp of mispriced ambiguity → BUY NO

## Resolution Ambiguity Index (RAI)

Score every market 1-5 before entry:

### RAI 1 — Crystal Clear
**Definition**: Resolution criteria reference a specific, verifiable data point with no interpretation needed.
**Examples**: "BTC above $100K on March 31" (exact price, exact date, exact source), "Fed cuts rates at March meeting" (binary FOMC statement)
**Resolution characteristics**: Always resolves cleanly. Never disputed. P(resolution|event) ≈ 1.0.
**Adjustment**: None. Trade at face value.

### RAI 2 — Minor Edge Cases
**Definition**: Criteria are clear for 95%+ of likely outcomes, but edge cases exist that could complicate.
**Examples**: "JD Vance wins 2028 Republican nomination" (clear, but: what if convention is contested?), "Trump signs executive order on X" (clear, but: what if it's a presidential memorandum not technically an EO?)
**Resolution characteristics**: Disputes rare (<2%). P(resolution|event) ≈ 0.95.
**Adjustment**: Haircut YES price by 2-5% in edge-case scenarios.

### RAI 3 — Moderate Ambiguity
**Definition**: Resolution criteria use language that has defensible multiple interpretations for plausible event outcomes.
**Examples**: "Deal reached" (framework vs. signed treaty), "Best AI model" (which benchmark? which date?), "Government shutdown" (partial vs. full)
**Resolution characteristics**: 5-15% chance of dispute. UMA's "title spirit" principle usually resolves predictably, but not always.
**Adjustment**: Price in 10-20% resolution discount. P(resolution|event) ≈ 0.80-0.90.

### RAI 4 — Significant Ambiguity
**Definition**: Resolution criteria involve subjective judgment or terms with no clear definition for likely outcomes.
**Examples**: "US strikes Iran" (drone? cyber? proxy? on Iranian soil vs. IRGC in Iraq), "Maduro is leader of Venezuela" (de facto vs. de jure vs. recognized by whom), "Country X invades Y" (limited operation vs. full invasion)
**Resolution characteristics**: 15-30% chance of dispute. UMA voting dynamics become important. Whale UMA holders may influence.
**Adjustment**: Price in 25-40% resolution discount. P(resolution|event) ≈ 0.60-0.75.

### RAI 5 — Deep Ambiguity / Manipulation Risk
**Definition**: Resolution criteria are fundamentally contested, or the market has attracted enough volume that UMA whale manipulation is economically rational.
**Examples**: "Ukraine agrees to mineral deal" (no clear definition of "agrees"), "UFO declassification" (what counts as "declassified"?), any >$5M market with RAI ≥ 4
**Resolution characteristics**: >30% chance of dispute. DVM escalation likely. Oracle manipulation risk non-trivial.
**Adjustment**: Price in 40-60% resolution discount OR avoid entirely. P(resolution|event) ≈ 0.40-0.60.

## Rules

### Entry Criteria

1. **Identify ambiguity**: Read the full resolution criteria for every market you consider. Score the RAI.
2. **Estimate both layers**: Separately estimate P(event) and P(resolution|event).
3. **Calculate true price**: true_YES = P(event) × P(resolution|event)
4. **Compare to market**: If |true_YES - market_YES| > 5pp AND the gap is driven by resolution mispricing → entry signal.
5. **Direction**: Usually BUY NO (because UMA's status quo bias + narrow interpretation tendency makes NO the safer resolution in ambiguous cases).

### Entry Sizing

| RAI Score | Max Position Size | Rationale |
|-----------|------------------|-----------|
| 1 | Per underlying strategy | No S009 overlay needed |
| 2 | Per underlying strategy | Minimal adjustment |
| 3 | 3% of bankroll | Standard S009 position |
| 4 | 1.5% of bankroll | Reduced — oracle risk is real |
| 5 | 0.5% of bankroll OR skip | High manipulation risk |

**Why reduce size for high RAI?** Oracle manipulation is a fat-tailed risk. The Ukraine mineral deal ($7M) and Fort Knox ($3.5M) show that being "right" doesn't guarantee correct resolution. Size reduction is insurance against UMA whale attacks.

### Exit Rules

- **Hold to resolution** (this is fundamentally a resolution bet, not a directional bet)
- **Exit if Polymarket issues a clarification** that changes the resolution probability. Polymarket clarifications are binding (UMA has never overturned one). If the clarification makes your side less likely → exit immediately.
- **Exit if UMA Round 1 votes against you**: Round 1 is strongly predictive of final outcome. If you're holding NO and UMA Round 1 votes YES → exit at market price, don't wait for Round 2.
- **Never hold through a DVM escalation against your position**: DVM votes are dominated by ~5M UMA tokens held by 2-3 whales. If DVM escalates and the signal is against you, exit.

### UMA Prediction Heuristics

When estimating P(resolution|event), apply these principles (ranked by reliability):

1. **Polymarket clarification exists?** → Follow it. 100% reliability.
2. **Title interpretation**: What would a "reasonable person" reading only the title think? UMA follows this.
3. **Western media consensus**: What would Reuters/AP/BBC report? UMA uses this as evidence standard.
4. **Status quo bias**: In true 50/50 ambiguity, lean NO / no change.
5. **Narrow interpretation of action verbs**: "Invade" means large-scale ground operation. "Strike" means kinetic military action (not cyber, not proxy). "Agree" means formal documented agreement (not verbal commitment).
6. **Precedent**: How did UMA resolve similar markets in the past? (Israel-Lebanon "invasion" → NO sets precedent for future "invasion" markets)

## Expected Edge

### Theoretical

- **Base rate of resolution ambiguity**: ~1.5% of markets enter dispute (low frequency)
- **But**: For markets with RAI ≥ 3, resolution risk is materially mispriced because:
  - Retail traders ignore resolution criteria entirely (documented in calibration lessons)
  - The YES bias (Reichenbach & Walther 2025) amplifies mispricing on ambiguous YES conditions
  - UMA's status quo bias creates predictable NO tilt that the market doesn't price

### Practical

- This is an **overlay strategy**, not standalone. It modifies entry/exit decisions for positions taken under S004, S006, S008, etc.
- Primary value: **avoiding bad trades** (T007 Maduro: should have priced resolution ambiguity before entry) and **improving sizing** (reduce size on RAI 4-5 markets).
- Secondary value: Direct S009 trades on grossly mispriced resolution are rare but high-EV when found.
- Expected contribution: Reduces portfolio losses by 5-10% annually by avoiding resolution traps.

## What Would Kill This Strategy

- UMA reforms voting to eliminate whale concentration → resolution becomes unpredictable via principles alone
- Polymarket moves to a different oracle (not UMA) with different interpretation principles
- Markets improve resolution criteria quality (less ambiguity = fewer S009 opportunities)
- UMA interpretation principles shift unpredictably (no longer follows "title spirit" or status quo)

## Risk Management

- **Never >1.5% of bankroll on a RAI ≥ 4 market**. Oracle manipulation can override correct positioning.
- **Monitor UMA voting power concentration**: If new whales accumulate UMA tokens, risk profile changes.
- **Track Polymarket clarifications in real-time**: These are binding and can instantly change resolution probability.
- **Pair with S002 (threshold exit)**: On ambiguous markets, consider exiting at 85-90% rather than holding to resolution. The last 10-15% carries disproportionate oracle risk.

## S009 Applied to Current Portfolio

### T001: "US strikes Iran by June 30" — RAI 4
- **Ambiguity**: "Strike" is subjective. Does a drone strike on IRGC in Iraq count? Cyber strike? Proxy action?
- **UMA precedent**: Israel-Lebanon "invasion" resolved NO for "limited operation." Sets precedent for narrow interpretation.
- **Resolution adjustment**: P(res_YES|strike occurs) ≈ 0.70 (not all strike types qualify)
- **Implication**: Our NO position is supported by both S006 (time decay) AND S009 (resolution ambiguity favors NO)

### T002: "Trump wins 2028 GOP nomination" — RAI 1
- **Ambiguity**: None. Nomination is a verifiable event.
- **Resolution adjustment**: None needed.

### T003: "US strikes Iran by March 31" — RAI 4
- Same as T001. Same ambiguity, shorter timeframe.
- **Implication**: NO position doubly supported (time decay + resolution ambiguity)

### T005: "US or Israel strikes Iran by March 31" — RAI 3
- **Ambiguity**: "US or Israel" broadens the actor. Less ambiguous on actor identity, but same "strike" definition issue.
- **Resolution adjustment**: P(res_YES|strike occurs) ≈ 0.80 (slightly clearer than T001/T003 because Israel strikes are more conventional)

### T006: "JD Vance wins 2028 GOP nomination" — RAI 2
- **Ambiguity**: Minimal. Convention nomination is clear. Edge case: contested convention.
- **Resolution adjustment**: Negligible.

### T007: "Maduro is leader of Venezuela at end of 2026" — RAI 4
- **Ambiguity**: "Leader" is deeply ambiguous. De facto control? Constitutional recognition? Western media recognition?
- **UMA heuristic**: Western media consensus + "reasonable person" reading of title. If Maduro is in exile but Chavistas still call him president → likely NO (not actually "leading"). But if he maintains de facto power through proxies → could go either way.
- **Resolution adjustment**: P(res_YES|Maduro retains some form of power) ≈ 0.65 (multiple interpretations of "leader")
- **THIS IS THE HIGHEST S009 RISK IN OUR PORTFOLIO.** The prompt correctly identified it.
- **Action**: Consider reducing T007 size or tightening exit criteria based on RAI 4 classification.

### T008: "BTC reaches $150K by Dec 31" — RAI 1
- **Ambiguity**: None. Exact price, exact date, exact source (CoinGecko or similar).
- **Resolution adjustment**: None needed.

## Evolution Hooks

- **Build RAI database**: Score every market researched with RAI. Track resolution outcomes vs. scores to validate the index.
- **UMA voting power tracker**: Monitor UMA token distribution. Alert if concentration increases.
- **Resolution criteria NLP**: Future S012 (LLM ensemble) could automatically score RAI from resolution text.
- **Dispute frequency tracking**: If dispute rate increases above 1.5%, S009 becomes more valuable as standalone strategy.
- **Post-resolution audit**: For every disputed market, document how UMA voted vs. our prediction. Build calibration data for P(resolution|event) estimates.
