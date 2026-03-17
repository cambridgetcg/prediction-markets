You are a market microstructure researcher building a strategy around Polymarket's resolution mechanics — the 2-hour window between when an event occurs and when the market resolves. This is episodic but extremely high EV when it fires.

## Read First

1. ~/Desktop/prediction-markets/research/polymarket-structural-mechanics.md — sections 4-5 (Oracle mechanics, MOOV2)
2. ~/Desktop/prediction-markets/strategies/evolution/new-strategy-research.md — S009 identification
3. ~/Desktop/prediction-markets/research/what-doesnt-work.md — resolution risk section

## The Core Mechanic

When an event happens in the real world:
```
EVENT OCCURS (e.g., election called, strike confirmed)
        ↓
Market price: still at pre-event level (e.g., 65% YES)
        ↓  [Minutes to hours of stale pricing]
MOOV2 PROPOSER submits resolution
        ↓
2-hour liveness period with no dispute
        ↓
MARKET RESOLVES at $1.00 (YES) or $0.00 (NO)
```

**The opportunity**: During the window between event occurrence and market resolution, shares trade at stale prices. If you know the outcome before the market resolves, you can buy YES at 65 cents that will pay $1.00 in 2 hours — a 54% return in 2 hours (~235,000% annualised).

---

## Task 1: Map the Resolution Pipeline

### 1a. The MOOV2 Process in Detail

Research the exact resolution process:

1. **Who are the 37 MOOV2 proposers?** Are they identifiable? Do they have public profiles?
   - Search: "Polymarket MOOV2 proposers" + "Polymarket managed oracle v2"
   - Check: https://github.com/Polymarket/UMA-MOOV2 or similar repos

2. **How fast do proposers typically submit?** Measure from event occurrence to proposal submission:
   - Search for examples in 2025-2026 where we can track timing
   - Hypothesis: Election markets (clear outcomes) resolve faster than geopolitical markets (ambiguous outcomes)

3. **What determines proposal speed?**
   - Time of day (proposers are human — slower at 3am)
   - Event type clarity (binary elections vs. ambiguous treaty language)
   - Market size (big markets get faster attention)
   - Pre-positioning by proposers?

4. **The liveness period**: 2 hours of trading at "correct" prices while shares are technically still uncollateralised at the new value. This is the window.

### 1b. Post-Occurrence Price Dynamics

When an event occurs but before resolution:
- What happens to market prices in practice?
- Do prices jump immediately to ~99% (correctly reflecting the outcome)?
- Or do they lag, staying at stale prices for minutes/hours?

**Research this empirically:**
- Find 3-5 cases from 2025-2026 where we can reconstruct the timeline:
  1. When did the real-world event occur? (news timestamp)
  2. When did Polymarket prices move to ~99%?
  3. When was the resolution proposed?
  4. When did the market fully resolve?
- Look for: election results, Fed rate decisions, major market events

**Key question**: Is there a consistent lag between event and price? Or do bots instantly move prices to 99%?

Answer determines if this opportunity is accessible to manual traders.

### 1c. Dispute Window Trading

A separate opportunity: after resolution is proposed, during the 2-hour liveness:
- If outcome is contested (ambiguous criteria), price may settle at 90-95% while dispute risk holds it from 100%
- The price premium for "near-certain but technically not resolved" is typically 2-10%
- Risk: the 24-48h dispute period and potential DVM vote

**This is S011 (High-Probability Bond Rotation)** — formalise it here.

---

## Task 2: Ambiguous Resolution Criteria — The Oracle Trader (S009)

This is the deeper, less competitive play. Instead of racing to buy after the event, you identify BEFOREHAND which markets have ambiguous resolution criteria and price in the interpretation risk.

### 2a. Resolution Criteria Analysis

Polymarket markets have written resolution criteria. The UMA oracle interprets these criteria against events. Systematic biases exist in how UMA interprets:

**Research UMA's stated principles:**
- "The title reflects the spirit of the market" — UMA prioritises the market name over fine print
- "Public understanding" — common sense interpretation over technical legal language
- Precedent matters — previous similar markets' resolutions affect future interpretations
- Status quo bias — in genuinely ambiguous cases, UMA often votes NO/no-change

**Documented cases of ambiguity:**
- "US strikes Iran" — does a drone strike count? A cyber strike? A strike by proxies?
- "Trump invades country X" — what counts as an invasion?
- "Deal signed" — what counts as "signed"? Preliminary agreement? Framework? Formal treaty?
- "Best AI model" — Arena.ai ranking as of what exact time? With style control on or off?

**Task**: Search for: "Polymarket resolution ambiguity" + "UMA oracle interpretation" + "Polymarket disputed market"

Document the top 10 resolution criteria patterns that have historically created ambiguity.

### 2b. The S009 Trade Construction

For a market with ambiguous criteria:

**Scenario**: "US and Iran reach a nuclear deal by March 31"
- Criteria says "comprehensive agreement signed"
- Current market: 35% YES
- In reality: a "framework agreement" is announced but the full text isn't signed

**Two layers to price:**
1. Event probability: probability that ANY agreement occurs = 40%
2. Resolution probability: probability that any agreement that DOES occur will be interpreted as satisfying the criteria = 60%
3. Combined: 40% × 60% = 24% true YES probability vs. 35% market price → SELL YES (BUY NO)

**Build a framework:**
- For each market we follow, score: "Resolution Ambiguity Index" (1-5)
  - 1 = perfectly clear (price of BTC on a specific date)
  - 5 = deeply ambiguous ("deal reached", "invasion began", "agreed to")
- Price adjustment formula: true_probability = event_probability × resolution_probability
- When true_probability < market_price AND gap > 5pp → S009 entry

**Apply this to our current markets:**
- T001: "US strikes Iran by Jun 30" — what counts as a "strike"? Score the ambiguity.
- T003: "US strikes Iran by Mar 31" — same question
- T006: "JD Vance wins 2028 Republican nomination" — very clear, Score 1
- T007: "Nicolas Maduro is leader of Venezuela" — ambiguous! Rodriguez calls him "legitimate president" — Score 4

**The T007 risk is S009's anti-pattern**: We entered T007 assuming the resolution is based on actual power, but if "leader" is interpreted as "recognised leader" by the Chavista government, Maduro might resolve YES even from prison. This is exactly the S009 risk we should have priced in.

---

## Task 3: News Monitoring Infrastructure

The resolution window opportunity requires being faster than the market. This needs infrastructure.

### 3a. News-to-Trade Pipeline Design

Design a minimal system that:

1. **Monitors news sources** for events that could resolve active Polymarket markets
   - RSS feeds: Reuters, AP, BBC
   - Twitter/X: official government accounts, major wire services
   - Specific monitors: AP Alerts, Reuters Breaking News

2. **Maps news events to open Polymarket markets**
   - Maintain a registry: market_id → relevant_keywords
   - On news alert: check if any keyword matches an open market

3. **Price check on match**
   - Fetch current prices from CLOB API
   - If price is still stale (hasn't moved to 95%+), flag the opportunity

4. **Alert threshold**
   - If genuine outcome AND price < 90% → IMMEDIATE ALERT
   - If genuine outcome AND price = 90-97% → MONITOR (may still have 3-10% return available)

**You don't need to build this now** — just design the spec. What's the minimum viable version that could be run manually (checking a phone/computer)?

### 3b. The Market-Outcome Registry

Create a seed registry for our current open positions:

```json
[
  {
    "market": "US strikes Iran by March 31",
    "market_id": "[polymarket_market_id]",
    "resolution_YES": ["US military conducts air strikes, cruise missile strikes, or special operations raids against Iranian military targets on Iranian soil"],
    "resolution_NO": ["Deadline passes without qualifying strike. Diplomatic deal. Proxy strikes only (Israel unilateral)"],
    "ambiguity_score": 4,
    "ambiguity_notes": "Does 'Iranian soil' include IRGC proxies in Iraq? Does cyber strike qualify? Documented ambiguity on 'US strike' definition.",
    "news_monitors": ["iran strike", "us attacks iran", "military action iran", "B-2 iran", "carrier strike iran"],
    "current_price_YES": 0.605
  }
]
```

Build this for all 7 open positions. Store at: `~/Desktop/prediction-markets/data/market-resolution-registry.json`

---

## Task 4: Build S009 and S011 Playbooks

### S009 — Oracle Trader

Using the ambiguity framework from Task 2:

Write: `~/Desktop/prediction-markets/strategies/playbooks/S009-oracle-trader.md`

Include:
- Resolution Ambiguity Index scoring rubric (1-5 scale with examples)
- Trade construction: event_probability × resolution_probability
- Entry rule: when gap > 5pp after ambiguity adjustment
- Sizing: reduce by 50% vs. normal for Score 4-5 markets (extra resolution risk)
- Exit rule: hold to resolution OR exit if resolution criteria clarification issued
- Risk factors: UMA whale attack, retroactive rule changes, MOOV2 interpretation shifts

### S011 — High-Probability Bond Rotation

Write: `~/Desktop/prediction-markets/strategies/playbooks/S011-bond-rotation.md`

Include:
- Screen criteria: >95% probability, <7 days to resolution, >$50K liquidity
- Annualised return calculation (show the math)
- Position sizing: max 5% of bankroll per position
- Exit: hold to resolution (never sell early — the 1-3% remaining upside isn't worth the spread cost)
- Risk: oracle manipulation on any near-certain outcome. Mitigation: use MOOV2-only markets, check proposer history
- The "overnight decay" opportunity: Fed meeting markets at 97% the night before → buy → collect next day

---

## Output

1. `~/Desktop/prediction-markets/strategies/playbooks/S009-oracle-trader.md`
2. `~/Desktop/prediction-markets/strategies/playbooks/S011-bond-rotation.md`
3. `~/Desktop/prediction-markets/data/market-resolution-registry.json` — our current positions with resolution analysis
4. `~/Desktop/prediction-markets/research/resolution-window-analysis.md` — empirical findings on resolution lag
5. Terminal report: "For our current positions, what is the S009 ambiguity risk? Which trades should we have priced lower because of ambiguity?"

**Key sources to research:**
- https://docs.polymarket.com/predict/outcome-tokens/binary-vs-multi-outcome
- https://github.com/UMAprotocol/UMIPs (UMA Improvement Proposals — contains resolution principles)
- "Polymarket Resolution Guide" (any official documentation)
- Case studies of disputed markets from 2025 (search "Polymarket dispute 2025")
