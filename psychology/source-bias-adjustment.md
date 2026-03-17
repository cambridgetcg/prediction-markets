# Source Bias Adjustment Framework

> Every news source has directional bias, domain reliability, and incentive structure.
> Without a source credibility model, every news item carries equal weight. That's noise averaging, not calibration.

---

## 1. The Probability Update Rule

### Full Bayesian Form

```
Standard:  P(event | news) = P(news | event) × P(event) / P(news)

Adjusted:  P(event | news from S) =
    credibility(S) × P(news | event) × P(event) / P(news)
    + (1 - credibility(S)) × P(event)
```

A perfectly credible source (1.0) gets full Bayesian weight. A completely unreliable source (0.0) returns you to the base rate — you learn nothing.

### Practical Form (without full Bayes)

```
adjusted_estimate = base_rate + credibility × (raw_estimate - base_rate)
```

Where:
- `base_rate` = your estimate BEFORE this specific news item
- `raw_estimate` = where your estimate would go if you trusted the news fully
- `credibility` = 0.0 to 1.0 (composite_score / 5.0 from source matrix)

### Worked Examples

**Fox News reports "Iran accelerating weapons-grade enrichment"**
- Before news: Iran strike probability = 55%
- Naive update (full trust): 70%
- Fox News GEO credibility: 3.5/5 = 0.70
- Adjusted: 55% + 0.70 × (70% - 55%) = **65.5%** (not 70%)

**Reuters reports the same event**
- Reuters credibility: 4.8/5 = 0.96
- Adjusted: 55% + 0.96 × (70% - 55%) = **69.4%**

**PressTV reports "Iran within treaty limits"**
- PressTV credibility: 1.5/5 = 0.30
- Naive update (full trust): 40%
- Adjusted: 55% + 0.30 × (40% - 55%) = **50.5%**

### Multiple Sources (Sequential Updates)

When multiple independent sources report on the same event, update sequentially:

```
estimate_0 = prior
estimate_1 = estimate_0 + cred(S1) × (raw_1 - estimate_0)
estimate_2 = estimate_1 + cred(S2) × (raw_2 - estimate_1)
...
```

**Critical**: Order doesn't matter mathematically for small updates, but psychologically you should read the LEAST biased source first to avoid anchoring.

### Corroborating Sources (Agreement Boost)

When two sources with OPPOSITE known biases agree on the same fact:
- This is strong evidence — boost credibility of the claim
- Example: Haaretz (left-leaning Israeli) AND Times of Israel (establishment Israeli) both report "IDF opposes Iran strike timing" → very high confidence in the factual claim

When two sources with the SAME known bias agree:
- This is weak additional evidence — they likely share the same upstream source
- Treat as ~1.2x one source, not 2x

---

## 2. Source Conflict Resolution Protocol

When credible sources directly contradict each other, do NOT average. Follow this protocol:

### Step 1: Check Source-of-Source
Are both sources reporting from the same underlying event (same briefing, same document, same leak)?
- **Yes** → One is misinterpreting. Go to the primary document.
- **No** → They may have genuinely different information. Proceed to Step 2.

### Step 2: Weight by Domain Expertise
Apply domain-specific credibility, not general credibility:
- TWZ beats FT on military force positioning
- Nick Timiraos (WSJ) beats CNN on Fed policy
- SCOTUS Blog beats NYT on Supreme Court procedure
- Glassnode beats CoinDesk on on-chain metrics

### Step 3: Check Primary vs. Derived
```
Primary source (government statement, filing, data) >
  Secondary (journalist's paraphrase with byline) >
    Tertiary (pundit's summary or analysis)
```
If Source A cites primary and Source B cites "people familiar with the matter," Source A wins.

### Step 4: Apply Directional Bias Adjustment
Subtract known bias before comparing:
- If Fox News says "strike imminent" (known hawkish bias) and Al Jazeera says "talks progressing" (known anti-Western-intervention bias), neither is fully credible on its own
- The OVERLAPPING factual claims (not interpretations) are what matter
- Fox: "B-2 bombers repositioned" → verifiable fact, likely true regardless of framing
- Al Jazeera: "Geneva talks scheduled for Tuesday" → verifiable fact, likely true

### Step 5: Widen Confidence Interval
If after Steps 1-4 the conflict is unresolved:
- Your probability estimate should carry a WIDER confidence interval
- This means: smaller position size, tighter stops, or wait for resolution
- Never force certainty when credible sources genuinely disagree

### Resolution Documentation Template

```
## Source Conflict — [Topic] — [Date]

Source A: [Name] | Claim: [X] | Credibility: [score] | Citation level: [L1-L7]
Source B: [Name] | Claim: [Y] | Credibility: [score] | Citation level: [L1-L7]

Same underlying event? [Yes/No]
Domain expertise winner: [A/B/Neither]
Primary sourcing winner: [A/B/Neither]
After bias adjustment: [Resolved/Unresolved]

Resolution: [Which claim I'm weighting higher and why]
Confidence: [High/Medium/Low]
Action: [Update estimate / Widen interval / Wait for more info]
```

---

## 3. Citation Hierarchy

The strength of a claim depends on how far from primary sourcing it is:

| Level | Description | Example | Trust Weight |
|-------|-------------|---------|-------------|
| **L1 Primary** | Official statement, court filing, verified document, on-chain data | IAEA report, Fed statement, SEC filing, blockchain explorer | 0.95 |
| **L2 Direct Quote** | Named official quoted in established outlet with byline journalist | "Secretary Blinken told reporters..." in Reuters | 0.80 |
| **L3 Paraphrase** | "Officials said..." with named outlet and named journalist | NYT diplomatic correspondent paraphrasing State Dept | 0.65 |
| **L4 Unnamed Sources** | "People familiar with the matter..." | Bloomberg "sources say Fed considering..." | 0.45 |
| **L5 Single Rumour** | One outlet, unverified, no sourcing given | Single blog post or newsletter claim | 0.25 |
| **L6 Social Media** | Twitter/X anonymous accounts, Telegram channels | @cryptowhale123 "hearing that..." | 0.10 |
| **L7 State Propaganda** | RT, PressTV, CGTN, Xinhua on contested domestic topics | PressTV on Iran nuclear programme | 0.05 |

**Note on L7**: State propaganda is useful as a COUNTER-INDICATOR. If PressTV is aggressively denying something, that thing is more likely true. Apply inverse framing — their denial is weak evidence FOR the claim.

### Compound Adjustment Formula

```
final_weight = source_credibility × citation_level_weight
```

**Examples**:
| Source | Citation Level | Calculation | Final Weight |
|--------|---------------|-------------|-------------|
| Reuters at L1 (official statement) | 0.96 × 0.95 | = | **0.91** |
| TWZ at L2 (named military official) | 0.92 × 0.80 | = | **0.74** |
| NYT at L3 (paraphrased diplomat) | 0.80 × 0.65 | = | **0.52** |
| Bloomberg at L4 (unnamed sources) | 0.88 × 0.45 | = | **0.40** |
| Fox News at L4 (unnamed intel official) | 0.55 × 0.45 | = | **0.25** |
| Zero Hedge at L5 (single rumour) | 0.40 × 0.25 | = | **0.10** |
| Crypto Twitter at L6 | 0.20 × 0.10 | = | **0.02** |
| PressTV at L7 | 0.30 × 0.05 | = | **0.015** |

### Practical Decision Rules

- **Final weight > 0.70**: Strong evidence. Update estimate with high confidence.
- **Final weight 0.40-0.70**: Moderate evidence. Update estimate but widen interval.
- **Final weight 0.15-0.40**: Weak evidence. Note but do not update estimate. Seek corroboration.
- **Final weight < 0.15**: Noise. Ignore unless corroborated by independent higher-weight source.

---

## 4. The Source-Bias Premium (Trading Signal)

Source bias creates a tradeable market signal:

### The Signal

```
source_bias_premium = polymarket_price - credible_consensus_estimate
```

- **Positive premium** (market > consensus): Fear/hype amplification from loud, low-credibility sources dominating retail traders' feeds. Fade this — sell the fear.
- **Negative premium** (market < consensus): Market underpricing due to inadequate sourcing by participants. Buy the information gap.

### How to Calculate Credible Consensus

1. Take probability estimates implied by Tier 1-2 sources only
2. Weight by source credibility × citation level
3. Ignore Tier 4-5 sources entirely
4. This is your "informed prior"

### When Source-Bias Premium Is Largest

| Condition | Expected Premium | Strategy |
|-----------|-----------------|----------|
| Breaking news, single loud source | +10-20pp fear premium | S004 fade after 24-72h |
| State media drumbeat, no primary confirmation | +5-15pp manufactured premium | S006 time decay |
| Domain experts unified, general media confused | -5-10pp information gap | S008 info edge |
| All sources agree across bias spectrum | Near zero | No edge — market is efficient here |

### Domain-Specific Source-Bias Patterns

| Domain | Typical Loud Sources | Typical Expert Sources | Usual Premium Direction |
|--------|---------------------|----------------------|------------------------|
| GEO | CNN, Fox, Twitter OSINT | TWZ, ISW, Bellingcat | Positive (fear amplification) |
| POL | Cable news, political Twitter | FiveThirtyEight, Silver Bulletin, campaign filings | Positive (partisan excitement) |
| ECO | CNBC, Zero Hedge | Nick Timiraos, CME FedWatch, BLS data | Mixed (contrarian noise both ways) |
| CRY | Crypto Twitter, influencers | Glassnode, CoinGlass, The Block | Positive (hype cycles) |
| TEC | Tech Twitter, Hacker News | arXiv, company blogs, benchmark data | Positive (hype for capabilities) |
| LAW | Cable news legal pundits | SCOTUS Blog, Lawfare, actual filings | Positive (partisan wishcasting) |

---

## 5. Implementation Checklist

Before updating any probability estimate based on news:

1. **Identify the source** — Who published this? What's their composite credibility score?
2. **Identify the citation level** — L1 primary through L7 propaganda?
3. **Calculate final weight** — credibility × citation level
4. **Apply the update formula** — adjusted = base + final_weight × (naive - base)
5. **Check for conflicts** — Any credible source saying the opposite? Run conflict protocol.
6. **Check for echo chamber** — Am I reading sources that all tilt the same way?
7. **Calculate source-bias premium** — Is the market price driven by loud or credible sources?

---

## References

- Source credibility matrix: `research/source-credibility-matrix.json`
- Quick reference table: `research/source-credibility-matrix.md`
- Domain source maps: `research/domain-source-maps.md`
- Pre-position checklist: `psychology/pre-position-checklist.md`
- Behavioral foundations: `psychology/behavioral-foundations.md`
- News-emotion pipeline: `psychology/news-emotion-price-taxonomy.md`
