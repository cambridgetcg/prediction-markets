You are a behavioral market analyst building a systematic taxonomy of how news events translate into emotional responses and price distortions on prediction markets.

## Prerequisite

Read first:
1. ~/Desktop/prediction-markets/psychology/behavioral-foundations.md — the bias inventory and ECI framework (from B01)
2. ~/Desktop/prediction-markets/research/what-doesnt-work.md — the documented failure modes
3. ~/Desktop/prediction-markets/domains/GEO/research/iran-us-2026.md — live case study
4. ~/Desktop/prediction-markets/strategies/paper-trades/trade-report-sotu-2026.md — SOTU case study

## The Core Pipeline

```
NEWS EVENT
    ↓
[Emotional Valence Assessment]
    ↓
PARTICIPANT EMOTIONAL RESPONSE
    ↓
[Behavioral bias activation]
    ↓
BETTING BEHAVIOR CHANGE
    ↓
[Price distortion]
    ↓
MARKET PRICE (biased)
    ↓
[Gap = Fundamental Probability - Market Price]
    ↓
EXPLOITABLE EDGE
```

Your job is to map this pipeline systematically for every major news category we trade.

---

## Task 1: The News Taxonomy

Create a classification system for news events. For each type, document the FULL pipeline above.

### Category A: Threat / Conflict News

**Subcategories:**
1. **Military buildup** (troops deployed, carriers repositioned, exercises announced)
2. **Ultimatum issued** (deadline set, demands made, warnings given)
3. **Diplomatic breakdown** (talks fail, ambassador recalled, sanctions escalate)
4. **Actual strike/attack** (military action confirmed)
5. **Diplomatic breakthrough** (deal reached, talks resume, framework announced)

For each subcategory, document:
- **Immediate emotional response**: What does this news make retail traders FEEL? (Fear, relief, excitement, etc.)
- **Which biases activate**: From B01 bias inventory — which biases fire?
- **Direction of price distortion**: Does YES go UP or DOWN, and by how much?
- **Speed and duration**: How fast does the distortion happen? How long does it persist?
- **Reality check**: What does the BASE RATE say about this news type's actual predictive value?
- **The gap**: How far does emotional price tend to deviate from base rate?
- **Trade signal**: Which strategy exploits this? Entry trigger? Exit target?

**Case study to anchor this**: Apply it to our Iran experience (T001, T003, T005). For each news event in the iran-us-2026.md research file, classify it and run the pipeline. Did the market's reaction match this taxonomy?

### Category B: Political / Leadership News

**Subcategories:**
1. **Poll release** (candidate up/down, favorable/unfavorable shift)
2. **Endorsement** (major figure endorses a candidate)
3. **Scandal revelation** (corruption, affair, legal issue)
4. **Debate performance** (strong/weak debate moment)
5. **Party division / internal conflict**
6. **Policy announcement** (major new position or flip)

For each, same pipeline. Focus especially on **partisan bias** — polls often cause larger moves on Polymarket than on prediction markets dominated by domain experts. Why? Map the psychological mechanism.

**Case study**: Apply to the 2028 presidential market (T002, T006). The "Trump 2028 at 2.8%" market (held by retail wishful thinking despite 22nd Amendment) is a clean case study in identity-protective cognition. The "Vance at 41.6%" discount is a case study in what happens when the VP lacks personal charisma — retail discounts a structural advantage because of emotional dislike.

### Category C: Economic Data News

**Subcategories:**
1. **Inflation data** (CPI, PCE beat/miss expectations)
2. **Jobs data** (NFP, JOLTS surprise)
3. **Fed communication** (statement, speech, minutes)
4. **Corporate earnings** (major company beats/misses)
5. **Trade/tariff announcement**

The ECO domain is the most "professional" — institutional traders dominate. But retail bias STILL appears. Identify:
- Where does retail overreact in ECO markets?
- Why did our T004 (March Fed cut) lose money? Was it a psychological error, or a legitimate fundamental change? (Answer: both — the PCE release killed the fundamental thesis, but did we also anchor on the CME divergence too long?)
- The "recency bias" trap: after a hot CPI print, markets overprice future hot prints; after a soft print, markets overprice soft. Document the magnitude.

### Category D: Crypto / Asset Price News

**Subcategories:**
1. **Protocol hack / security breach**
2. **Regulatory action** (approval, ban, enforcement)
3. **Whale movement** (large wallet buys/sells)
4. **Social media influencer call** (Musk tweet, prominent endorsement)
5. **Macro catalyst** (Fed pivot, recession signal, dollar move)
6. **ETF flow data** (weekly in/out flows)

CRY is the most psychologically volatile domain. The participant base is:
- Retail-heavy (high risk tolerance, narrative-driven)
- FOMO/FUD oscillation is extreme
- "Diamond hands" belief system creates denial during drawdowns
- Musk effect is documented and quantified

**Critical insight to research**: The Fear & Greed Index is at 5 (extreme fear). What has historically happened to price 30/60/90 days after extreme fear? Is this itself a psychological bias (people are TOO fearful after a crash), or is it correctly pricing a continued bear market? This directly affects T008 (BTC $150K NO).

### Category E: Technology / AI News

**Subcategories:**
1. **New model release** (benchmark improvement, new capability)
2. **Company funding/valuation**
3. **Government regulation announcement**
4. **Safety incident** (AI harm, alignment failure)
5. **Competitive landscape shift** (new entrant, incumbent acquires startup)

TEC has a specific psychology: the **hype cycle**. Gartner's hype cycle (Peak of Inflated Expectations → Trough of Disillusionment → Slope of Enlightenment) applies to AI news. Map which stages create which biases.

**Key question**: When a new AI model is announced with superhuman benchmarks, does the "best model" prediction market immediately overreact? What's the typical price move vs. the actual Arena impact? (Hint: the Arena ranking requires weeks of votes — a new model launch doesn't immediately change the Arena leader, but markets often act as if it does.)

---

## Task 2: The Participant Psychology Profiles

Each domain attracts a different psychological profile of bettor. Understanding WHO is on the other side of your trade tells you WHICH biases they're subject to.

Research and document for each domain:

### GEO (Geopolitics)
- **Who bets here?**: Doom-scrollers, geopolitical hobbyists, military/policy analysts (rare), news junkies
- **Primary motivation**: Following news, feeling "in the know," excitement of predicting conflict
- **Dominant biases**: Availability heuristic (vivid war imagery), fear premium, YES bias on dramatic outcomes
- **Information asymmetry**: Heavy. Government insiders, military analysts, diplomatic sources know far more than retail. The question is: do they trade on Polymarket? (Evidence: yes, some do. The Iran strike market is believed to have insider participation.)
- **Emotional trigger**: Any breaking news with military imagery → immediate buying surge on YES
- **Our edge**: We do more research per bet. We apply base rates. We check diplomatic calendars. We distinguish "imminent" from "eventual."

Do this for ALL 10 domains: GEO, POL, ECO, FIN, CRY, TEC, SCI, SOC, LAW, ENV.

### Cross-domain insight
The "who bets here?" question reveals something important: different domains have different SOPHISTICATION GRADIENTS. ECO is the most efficient (institutional traders, Fed watchers). SCI is least efficient (almost no domain experts trading Polymarket SCI markets). ENV is similar. **Edge is inversely proportional to domain sophistication.**

---

## Task 3: Live Case Study Decomposition

Apply the full pipeline to our own trading history.

For EACH of our predictions (pred-0001 through pred-0009), document:

| | Question | News Event That Drove Price | ECI Score (1-60) | Biases Active | Distortion Direction | My Estimate | Market Price | Gap | Was Market Emotional? |
|-|----------|----------------------------|------------------|---------------|----------------------|-------------|--------------|-----|-----------------------|

Then for the SOTU retrospective resolutions:
| | Market | ECI Score | Dominant Bias | Outcome | Did Psychology Predict Direction? |
|-|--------|-----------|---------------|---------|-----------------------------------|

**The goal**: Empirically validate that ECI score correlates with the size of the gap between emotional market price and true probability. If the data supports this, ECI becomes a quantified entry trigger.

---

## Task 4: The "Emotional Market Scanner" — Conceptual Design

Based on tasks 1-3, design the conceptual architecture for a system that:

1. **Ingests news** (RSS, Polymarket price movements, social media sentiment)
2. **Scores emotional charge** (ECI)
3. **Identifies which markets are affected**
4. **Compares emotional price to fundamental base rate**
5. **Flags potential S004 entries** when gap > threshold

You don't need to build this yet — just design the spec. Answer:
- What inputs does it need?
- What data sources feed it?
- What's the minimum viable version (could be done manually with a checklist)?
- What would a fully automated version require?

This becomes the spec for B04 (the live detection tool).

---

## Task 5: The Discrepancy Database

Create the seed of a living database: news events where the emotional market response demonstrably diverged from the reality check.

Format:
```jsonl
{"date":"2026-02-XX","domain":"GEO","news":"Trump issues 10-15 day deadline on Iran","emotional_response":"Fear, immediacy","biases":["availability","fear_premium","YES_bias"],"eci":8,"market_move":"+7pp (from 57% to 64%)","reality_check":"Deadlines extended historically; diplomatic track active; military not in place until mid-March","fair_value_estimate":52,"market_price":64,"gap":12,"outcome":"PENDING","lesson":"Deadline rhetoric ≠ imminent action. Diplomatic calendar matters more than headline."}
```

Seed it with at minimum:
- The Iran deadline news (Feb 19-22)
- The Feb 26 Geneva talks (positive diplomatic signals)
- The SOTU "MAGA/Fake News" markets (pure participant psychology error)
- The T004 CME-Polymarket divergence (CME was wrong, Polymarket was right — unusual)
- Trump's 2028 constitutional impossibility (pure identity/tribal wishful pricing)

Write to: `~/Desktop/prediction-markets/psychology/discrepancy-database.jsonl`

---

## Output

1. `~/Desktop/prediction-markets/psychology/news-emotion-price-taxonomy.md` — the full taxonomy
2. `~/Desktop/prediction-markets/psychology/participant-profiles.md` — the domain psychology profiles
3. `~/Desktop/prediction-markets/psychology/discrepancy-database.jsonl` — seed entries
4. `~/Desktop/prediction-markets/psychology/emotional-market-scanner-spec.md` — the scanner design

**Also update**:
- `~/Desktop/prediction-markets/strategies/playbooks/S004-contrarian-overreaction.md` — add the ECI scoring to the trigger criteria
- `~/Desktop/prediction-markets/strategies/evolution/strategy-domain-matrix.md` — add a "Psychological Edge Score" column for each domain (how susceptible is this domain to emotional mispricings?)
