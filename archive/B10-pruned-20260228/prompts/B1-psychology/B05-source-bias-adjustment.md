You are an epistemologist and information analyst building a systematic framework for adjusting probability estimates based on the source of the news — and a counter-strategy to reduce dependence on any single information channel.

## The Core Problem

Two pieces of news can describe the same event differently, and both can be "true" in the narrow sense while being systematically misleading:

> "Iran enriching uranium to near-weapons-grade levels" — Fox News
> "Iran confirms continued civilian nuclear programme within JCPOA-adjacent parameters" — PressTV (Iranian state)

The event is identical. The framing, emphasis, and implied probability are opposite. A trader who reads only one source forms a systematically wrong estimate.

**The structural problem**: Every news source has:
1. **Directional bias** — which way it tilts on contested narratives
2. **Domain reliability** — where it's accurate vs. sloppy
3. **Source-of-source quality** — does it cite primary sources or amplify secondhand claims?
4. **Timing reliability** — is breaking news from this outlet usually confirmed or usually wrong?
5. **Incentive structure** — who funds it, what does it gain from certain narratives?

Without a source credibility model, every news item carries equal weight in your estimate. That's not calibration — it's noise averaging.

---

## Read First

1. ~/Desktop/prediction-markets/psychology/behavioral-foundations.md — bias inventory (B01)
2. ~/Desktop/prediction-markets/psychology/news-emotion-price-taxonomy.md — the news pipeline (B02)
3. ~/Desktop/prediction-markets/domains/GEO/research/iran-us-2026.md — live example with multi-source conflict
4. ~/Desktop/prediction-markets/research/what-doesnt-work.md — confirmation bias and motivated reasoning section

---

## Task 1: The Source Credibility Matrix

Build a comprehensive database of news sources relevant to our domains, rated across five dimensions.

### Rating Dimensions (each 1-5)

| Dimension | 1 (Lowest) | 5 (Highest) |
|-----------|------------|-------------|
| **Factual accuracy** | Frequent errors, fabrications, or unchecked rumour | Consistently accurate, corrections policy, primary sourcing |
| **Directional bias** | Strong systematic tilt (always one direction) | No detectable editorial bias (wire service standard) |
| **Domain expertise** | Generic coverage, no specialist staff | Domain-specialist journalists and researchers |
| **Source-of-source quality** | "Reports suggest", unnamed officials, single source | Named sources, documents, multiple independent confirmation |
| **Breaking news reliability** | First reports frequently wrong or retracted | Conservative; waits for confirmation before publishing |

**Composite credibility score**: Weighted average (factual accuracy × 40%, directional bias × 20%, domain expertise × 20%, source quality × 10%, breaking reliability × 10%)

### Domains to Cover

Build the matrix for **every source we've used or are likely to use** across our 10 trading domains:

#### Wire Services (use these as your baseline)
- Reuters
- Associated Press (AP)
- Agence France-Presse (AFP)

#### US Domestic (political/economic angle)
- New York Times, Washington Post, Wall Street Journal
- Bloomberg, Financial Times (FT), Barron's
- Politico, The Hill, Axios
- CNN, MSNBC, Fox News

#### UK / European
- BBC, The Guardian, The Economist
- Financial Times (also under US for ECO)
- Euronews, Der Spiegel (English)

#### Middle East / Geopolitical
- Al Jazeera
- The Times of Israel, Haaretz
- Middle East Eye
- Iran International (London-based, anti-regime)
- PressTV (Iranian state media)
- Al-Monitor (regional specialist)

#### Defense / Military
- The War Zone (TWZ) — critically important for GEO military assessment
- Defense News, Breaking Defense
- Jane's (Janes.com) — premium, highly accurate
- Bellingcat (OSINT verification)
- Institute for the Study of War (ISW)

#### Financial / Economic
- Bloomberg, FT (also listed above)
- CME FedWatch (not a news source — a data source)
- WSJ Fed coverage (Nick Timiraos — the "Fed whisperer")
- Zero Hedge (contrarian, sometimes early, often wrong)

#### Crypto / Digital Assets
- CoinDesk, The Block, Decrypt
- Glassnode (on-chain data — NOT editorial)
- CoinGlass (on-chain derivatives data)
- Crypto Twitter / X (speed signal only)

#### AI / Technology
- arXiv (preprints — primary source, not editorial)
- The Verge, Ars Technica, Wired
- Anthropic/Google/OpenAI official blogs (primary but promotional)
- VentureBeat (industry-focused)

#### Legal / Regulatory
- SCOTUS Blog (highest domain credibility for SCOTUS)
- Law360
- Courthouse News Service

#### Social / Twitter
- Twitter/X verified accounts of official entities (treat as primary)
- Twitter/X journalists (treat as wire service equivalent if employed by known outlet)
- Twitter/X anonymous accounts (near-zero weight unless independently verified)

---

### The Matrix Output

For each source, produce:

```json
{
  "source": "The War Zone",
  "url": "thewarzone.com",
  "credibility_scores": {
    "factual_accuracy": 5,
    "directional_bias": 4,
    "domain_expertise": 5,
    "source_quality": 4,
    "breaking_reliability": 4
  },
  "composite_score": 4.6,
  "bias_direction": "Slightly pro-Western military establishment; anti-adversary framing",
  "bias_magnitude": "Low — primarily affects framing, not factual content",
  "strongest_domains": ["GEO military", "defence procurement", "OSINT confirmation"],
  "weakest_domains": ["Diplomatic nuance", "economic context", "political interpretation"],
  "known_blind_spots": ["Overweights US military capability assessments; underweights adversary adaptation"],
  "best_use": "Technical military facts, equipment capability, force positioning",
  "worst_use": "Predicting diplomatic outcomes, political decisions",
  "adjustment_factor": 1.0,
  "notes": "The single most reliable public source for military operational analysis. Their Diego Garcia B-2 status report (UK blocking use) is the kind of technical reporting that changes probability estimates."
}
```

Write the full matrix to: `~/Desktop/prediction-markets/research/source-credibility-matrix.json`

Also produce a quick-reference table: `~/Desktop/prediction-markets/research/source-credibility-matrix.md`

---

## Task 2: The Adjustment Formula

### 2a. The Probability Update Rule

When a news item arrives from a source with known bias, the Bayesian update should be discounted:

```
Standard update: P(event | news) = P(news | event) × P(event) / P(news)

Adjusted update: P(event | news from source S) = 
    credibility(S) × P(news | event) × P(event) / P(news)
    + (1 - credibility(S)) × P(event)  ← base rate unchanged component
```

**In plain English**: A highly credible source (score 5.0) gets full weight. A completely unreliable source (score 1.0) returns you to the base rate — you learn nothing from the news item. A moderate source (score 3.0) moves you halfway.

**Practical version** (without full Bayes):
```
adjusted_estimate = base_rate + credibility × (raw_estimate - base_rate)
```

Where:
- `base_rate` = your estimate before this specific news item
- `raw_estimate` = where your estimate would go if you trusted the news fully
- `credibility` = 0.0 to 1.0 (map composite score from 5-point scale)

**Example**:
- Before news: Iran strike probability = 55%
- Fox News reports "Iran accelerating weapons-grade enrichment" → naive update: 70%
- Fox News GEO credibility: 3.5/5 = 0.70
- Adjusted: 55% + 0.70 × (70% - 55%) = 55% + 10.5% = 65.5% (not 70%)

**Now run the same item through Reuters (credibility 4.8/5 = 0.96)**:
- Adjusted: 55% + 0.96 × (70% - 55%) = 55% + 14.4% = 69.4%

**And PressTV (Iranian state, credibility 1.5/5 = 0.30)**:
- PressTV reports "Iran within treaty limits" → naive update: 40%
- Adjusted: 55% + 0.30 × (40% - 55%) = 55% - 4.5% = 50.5%

The formula quantifies how much information to extract from each source.

### 2b. The Source Conflict Resolution Rule

When two credible sources directly contradict each other, the resolution is NOT to average them. It is to:

1. **Check the source-of-source**: Are they reporting from the same underlying event? If so, one is wrong.
2. **Weight by domain expertise**: TWZ beats FT on military facts. Nick Timiraos (WSJ) beats CNN on Fed policy.
3. **Check primary vs. derived**: Primary source (government statement) > secondary (journalist's paraphrase) > tertiary (pundit's summary)
4. **Apply directional bias adjustment**: If both sources are biased in OPPOSITE directions and they agree on a fact, that's strong evidence. If they disagree, subtract out the known bias first.

**Document this as the "Source Conflict Protocol"** — a step-by-step resolution method for when your research surfaces contradictory reports.

### 2c. The Citation Hierarchy

Formalise the strength of a claim based on how far from primary sourcing it is:

| Level | Example | Trust Weight |
|-------|---------|-------------|
| **L1 Primary** | Official government statement, court filing, verified document, on-chain data | 0.95 |
| **L2 Direct Quote** | Named official quoted in established outlet with byline journalist | 0.80 |
| **L3 Paraphrase** | "Officials said..." with named outlet and named journalist | 0.65 |
| **L4 Unnamed Sources** | "People familiar with the matter..." | 0.45 |
| **L5 Single Rumour** | One outlet, unverified, no sourcing given | 0.25 |
| **L6 Social Media** | Twitter/X anonymous accounts, Telegram channels | 0.10 |
| **L7 State Propaganda** | RT for Russia/Ukraine, PressTV for Iran/Israel | 0.05 (inverse framing: use as counter-indicator) |

**Compound adjustment**: Source credibility × Citation level = Final information weight

TWZ at L2 (named military official, direct quote) = 0.92 × 0.80 = 0.74
Fox News at L4 (unnamed intelligence official) = 0.55 × 0.45 = 0.25
Reuters at L1 (official government statement) = 0.96 × 0.95 = 0.91

---

## Task 3: Domain-Specific Source Maps

For each of our 10 trading domains, build a ranked source list:

**Template:**

```markdown
## GEO — Geopolitics Source Map

### Tier 1: Primary / Near-Primary
- **Official statements**: US State Dept, Pentagon, IAEA, UN press offices
- **Intelligence-adjacent**: Director of National Intelligence public reports
- **On-the-ground**: AP/Reuters correspondents with named bylines IN THE REGION

### Tier 2: Domain Experts
- **The War Zone**: Military operational analysis (#1 for force positioning, equipment)
- **Bellingcat**: OSINT verification, satellite imagery analysis
- **ISW (Institute for the Study of War)**: Conflict mapping, daily updates
- **IAEA reports**: Nuclear-specific, primary for enrichment data
- **International Crisis Group**: Diplomatic analysis, conflict de-escalation tracking

### Tier 3: Reliable General
- Reuters, AP (wire services, L2-L3 sourcing typical)
- FT, Economist (context and diplomatic analysis, slight Western bias)
- BBC World Service (factual accuracy high, British foreign policy framing)

### Tier 4: Useful with Adjustment
- NYT, WaPo (good reporting, strong editorial bias in interpretation)
- Al Jazeera (essential for Middle East regional perspective; Qatar-adjacent)
- Haaretz (critical Israeli perspective, left-leaning)
- Times of Israel (more establishment Israeli perspective)

### Tier 5: Use with Heavy Discount
- Fox News, CNN (amplification, US domestic framing, low domain expertise)
- PressTV, RT (state propaganda; useful ONLY as counter-indicator or to understand adversary messaging)
- Twitter/X: Use for speed signal only — verify everything before updating estimates

### Blind Spots This Map Has
- Non-English sources (Persian/Arabic/Hebrew media) — requires translation and context
- Regional media that breaks stories before wire services — need monitoring
- Intelligence community leaks — directional but intentional, must assess cui bono
```

Build this Tier system for ALL 10 domains: GEO, POL, ECO, FIN, CRY, TEC, SCI, SOC, LAW, ENV.

Write to: `~/Desktop/prediction-markets/research/domain-source-maps.md`

---

## Task 4: The Counter-Strategy — Source Diversification Protocol

The meta-problem: knowing biases and having adjustment formulas is worthless if you only ever read one source. The counter-strategy is structural diversity — building habits and systems that force multi-source consumption BEFORE forming probability estimates.

### 4a. The Minimum Source Basket

For any market position:

| Confidence Required | Minimum Sources | Must Include |
|--------------------|----------------|--------------|
| Small position ($50-100) | 2 independent sources | At least 1 Tier 1-2 |
| Standard position ($100-200) | 3 independent sources | At least 1 primary; at least 1 from different national perspective |
| Large position ($200+) | 4 independent sources | Primary + 2 Tier 2 + adversarial perspective |

**"Independent" definition**: Sources that do NOT share the same underlying source. Reuters and AP both reporting from a Pentagon briefing is ONE source, not two.

**"Adversarial perspective"**: Always read the source that is MOST LIKELY to contradict your thesis. On Iran: read Iran International (anti-regime) AND Al-Monitor (regional) AND TWZ (military). On Fed policy: read Zero Hedge (contrarian) AND Nick Timiraos (consensus). Adversarial sourcing finds your blind spots before the market does.

### 4b. The Pre-Position Research Checklist

Before entering any position, document:

```markdown
## Source Check — [Market Name] — [Date]

**Primary sources consulted:**
- [ ] Official statement / document / on-chain data
- Source: ___ | Date: ___ | Key claim: ___

**Domain expert sources:**
- Source 1: ___ | Key claim: ___ | Credibility score: ___
- Source 2: ___ | Key claim: ___ | Credibility score: ___

**Adversarial perspective:**
- Source: ___ (should have opposing institutional bias to your thesis)
- Key claim: ___ | Credibility score: ___

**What do sources AGREE on?** (High confidence zone)
___

**What do sources DISAGREE on?** (Uncertainty zone — widen confidence interval)
___

**Strongest counter-argument from best-credible source:**
___

**Source conflict resolution applied?** Yes / No
If yes, which source won and why?
___

**Adjusted probability after source-quality weighting:**
Before adjustment: ___%
After adjustment: ___%
```

Add this checklist to: `~/Desktop/prediction-markets/psychology/pre-position-checklist.md`

### 4c. The RSS / Alert Diversity Stack

Build a recommended reading stack that forces geographical and institutional diversity:

**Tier 1 (read first — primary signals):**
```
GEO:  IAEA press releases, State Dept briefings, Pentagon transcripts
POL:  Electoral commission filings, FiveThirtyEight, official campaign statements
ECO:  Fed press releases, BLS data releases, BEA PCE reports
CRY:  Glassnode (on-chain), CoinGlass, exchange announcements
TEC:  arXiv, company blogs (Anthropic/Google/OpenAI), Arena.ai leaderboard
LAW:  SCOTUS Blog, PACER filings, DOJ press releases
```

**Tier 2 (domain experts — interpret primary signals):**
```
GEO:  The War Zone, Bellingcat, ISW daily updates
POL:  Silver Bulletin (Nate Silver), academic political scientists
ECO:  Nick Timiraos (WSJ), CME FedWatch, JPMorgan/Goldman research notes
CRY:  The Block, Delphi Digital, on-chain analyst accounts (verified)
TEC:  Andrej Karpathy, Ethan Mollick, AI researcher Twitter (verified)
LAW:  SCOTUS Blog, Lawfare
```

**Tier 3 (geographically diverse — prevents western-only framing):**
```
GEO/Middle East: Al Jazeera, Middle East Eye, Iran International (UK-based)
GEO/Russia: Meduza (independent Russian in exile), Kyiv Independent (Ukrainian)
GEO/China: Caixin (independent business), South China Morning Post (HK)
GEO/Israel: Haaretz (left), Times of Israel (centre), Ynet (right)
ECO/Global: FT, Nikkei, El Economista
```

**Tier 4 (speed layer — monitor for breaking, verify before updating):**
```
All domains: Reuters / AP breaking alerts (set up)
GEO:  Watcher.Guru, OSINTdefender (Twitter)
POL:  Decision Desk HQ, Associated Press election alerts
CRY:  Twitter alerts from verified exchange accounts, @WuBlockchain
```

**Counter-reading rule**: For every bullish source on your thesis, you MUST read one bearish source before finalising the estimate. This is non-optional for positions >$100.

### 4d. The "Echo Chamber Detection" Test

Before finalising a probability estimate, run this self-check:

```
1. Can I name 2 credible sources that DISAGREE with my estimate? 
   No → I haven't looked hard enough. Research more before entering.

2. Are all my sources from the SAME country or institutional perspective?
   Yes → Add at least one source from a different national perspective.

3. Did I form my estimate BEFORE reading the market price?
   No → I've been anchored. Re-estimate independently, then compare.

4. Is my main source also the LOUDEST source? (most coverage, most discussed)
   Yes → Apply amplification discount. Louder ≠ more likely.

5. When was the last time I updated my estimate in a direction that HURT my existing position?
   Never → I'm not seeking disconfirmation. I'm confirming, not calibrating.
```

---

## Task 5: Apply to Current Positions

### 5a. Source Audit for T001-T008

For each open position, answer:
- What were the primary sources used to form the estimate?
- What is each source's credibility score (from Task 1)?
- What adversarial sources were consulted?
- Apply the adjustment formula: does the source-weighted estimate differ significantly from the raw estimate?

| Trade | Key Sources Used | Avg Credibility | Adversarial Source Consulted? | Adjusted Estimate | Original Estimate | Delta |
|-------|-----------------|-----------------|-------------------------------|-------------------|-------------------|-------|
| T001 (Iran Jun 30) | TWZ, Reuters, NYT | ? | ? | ? | 37% | ? |
| T003 (Iran Mar 31) | TWZ, Reuters | ? | No PressTV perspective | ? | 48% | ? |
| T006 (Vance 2028) | Polling, Axios | ? | ? | ? | 58% | ? |
| ... | | | | | | |

### 5b. The Biggest Source Risk in Our Portfolio

Identify: which of our positions is MOST dependent on a single source or a single geographic/institutional perspective?

GEO positions (T001, T003, T005): Heavily weighted to Western/US military media (TWZ, Reuters). We have almost NO Iranian or Russian perspective, no Gulf state perspective.

**This is a genuine blind spot.** The Gulf states (UAE, Saudi, Qatar) have the most to lose from an Iran strike. Their media and diplomatic signals are significantly underweighted in our research. They also have the most sensitive intelligence (proximity).

**Task**: Find and evaluate 3 Gulf-state or non-Western sources on the Iran situation that should be added to the reading stack:
- Web search: "Gulf state Iran deal 2026 news" + "Saudi Arabia Iran nuclear February 2026" + "UAE Iran talks 2026"
- Do these sources shift the probability estimate? If so, by how much?

---

## Task 6: The Source Bias Signal

**A meta-insight**: Source bias itself is a market signal.

When ALL credible Western media are reporting that a strike is imminent → the fear premium on Polymarket is JUSTIFIED by that consensus.

When ONLY partisan/state sources are reporting high strike probability → the fear premium is UNJUSTIFIED.

The divergence between:
- "Consensus of credible sources" probability
- "Polymarket price"

...is where the edge lives. If credible consensus says 40% but Polymarket says 60%, the gap is psychological (fear amplification from partisan/loud sources dominating retail traders' feeds). That's S004 territory.

Conversely: if credible consensus says 60% but Polymarket says 40%, the market is underpricing based on inadequate sourcing. That's S008 territory (we have better sources than the market).

**Build the signal**: For each domain, document what "source credibility consensus" looks like vs. "loud media consensus". The delta between the two IS the source-bias premium.

---

## Output

1. `~/Desktop/prediction-markets/research/source-credibility-matrix.json` — full JSON database, every source rated
2. `~/Desktop/prediction-markets/research/source-credibility-matrix.md` — quick reference table
3. `~/Desktop/prediction-markets/research/domain-source-maps.md` — tiered source maps for all 10 domains
4. `~/Desktop/prediction-markets/psychology/pre-position-checklist.md` — the source diversity checklist
5. `~/Desktop/prediction-markets/psychology/source-bias-adjustment.md` — the adjustment formula, conflict protocol, citation hierarchy
6. Source audit of T001-T008 (terminal output — identify the biggest blind spot in our current portfolio)

**Update**: Append to `~/Desktop/prediction-markets/psychology/discrepancy-database.jsonl` any cases where re-running the adjustment formula on existing positions changes the estimate by >3pp.

**The key deliverable**: A reading stack (Tier 1-4 sources per domain) that, if followed before any new position, would systematically expose our estimates to the full range of credible perspectives — including those that challenge our thesis.
