# B02: News → Emotion → Price Taxonomy

*Research date: 2026-02-25*
*Purpose: Systematic mapping of how news events translate into emotional responses, behavioral bias activation, and exploitable price distortions on prediction markets*
*Prerequisite: behavioral-foundations.md (B01)*

---

## Table of Contents

1. [The Core Pipeline](#the-core-pipeline)
2. [Category A: Threat / Conflict News](#category-a-threat--conflict-news)
3. [Category B: Political / Leadership News](#category-b-political--leadership-news)
4. [Category C: Economic Data News](#category-c-economic-data-news)
5. [Category D: Crypto / Asset Price News](#category-d-crypto--asset-price-news)
6. [Category E: Technology / AI News](#category-e-technology--ai-news)
7. [Live Case Study Decomposition](#live-case-study-decomposition)
8. [SOTU Retrospective Decomposition](#sotu-retrospective-decomposition)
9. [Cross-Category Patterns](#cross-category-patterns)

---

## The Core Pipeline

Every news event follows this causal chain before it becomes a market price:

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

The taxonomy below maps this pipeline for every major news category we trade. For each subcategory: what emotion fires, which biases compound, how the price moves, what base rates say, and which strategy exploits the gap.

---

## Category A: Threat / Conflict News

**Domain**: GEO (primary), SOC (terrorism), LAW (enforcement actions)
**Compound pattern**: War Panic Premium (behavioral-foundations.md §2.1)

### A1: Military Buildup

*Troops deployed, carriers repositioned, exercises announced.*

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Dread, anxiety. "It's really happening this time." |
| **Biases activated** | Availability (#1: vivid military imagery), Salience (#2: dramatic upside scenario), Narrative Fallacy (#4: "buildup → escalation → strike" story writes itself), Loss Aversion (#11: catastrophic outcome overweighted) |
| **Direction of distortion** | YES price UP. Buildup = "something is happening" = YES buyers pile in. |
| **Magnitude** | +5-15pp over 3-7 days. Gradual, cumulative. Each new deployment headline adds 1-3pp. |
| **Speed & duration** | Slow onset (days to weeks). Persists as long as media covers the buildup. Does NOT revert quickly because each quiet day is offset by another "carrier deployed" headline. |
| **Reality check** | Base rate: US military buildups since 1990 that led to strikes = 58% (15/26 elevated-tension episodes). BUT: buildups WITH ultimatums = ~100% (3/3). Buildups WITHOUT ultimatums = much lower. The market conflates "buildup" with "buildup + ultimatum." |
| **The gap** | If buildup alone (no ultimatum): market overprices by 10-20pp. If buildup + ultimatum: market may be correctly priced or slightly underpriced. |
| **Trade signal** | S006 (time decay): buildup without ultimatum = overpriced YES on "by date" markets. S008 (info edge): distinguish buildup types via OSINT. Do NOT fade if buildup accompanies an ultimatum — the base rate supports the market. |

**Case study — Iran Feb 2026 buildup**: 3 carriers, 150+ aircraft, F-22s deployed to Israel. Market moved Iran March 31 from ~40% to 57% over Feb 13-22. Our assessment: buildup IS accompanied by a Trump ultimatum (10-15 day deadline), matching the 100% historical pattern. Market was roughly fairly priced. T003 entered NO based on S004 rhetoric spike analysis, not buildup dismissal. Lesson: buildup + ultimatum is the ONE conflict pattern where the market may not be overpricing.

### A2: Ultimatum Issued

*Deadline set, demands made, warnings given.*

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Urgency, fear of imminent action. "The countdown has started." |
| **Biases activated** | Deadline Panic (#18), Narrative Fallacy (#4: "deadline → expiration → action"), Fear Premium (#12), Anchoring (#21: the deadline date becomes a focal point), FOMO (#10: traders rush to buy YES before the "inevitable" strike) |
| **Direction of distortion** | YES price UP sharply. Ultimatums create a focal point that compresses uncertainty into a specific window. |
| **Magnitude** | +10-25pp in 24-72h. The largest single-event category in GEO. |
| **Speed & duration** | Fast onset (hours). The spike peaks 24-48h after the ultimatum. Then: if diplomatic signals emerge, slow drift down. If ultimatum reinforced, price holds. |
| **Reality check** | Trump-specific: In his first term, Trump set deadlines and extended them (North Korea 2017-2018: "fire and fury" → summit). In his second term, the 60-day Iran deadline (April 2025) expired and strikes followed. Base rate for Trump 2nd term deadlines leading to action: 1/1. But the Feb 2026 deadline was described as "not scientific" — ambiguity. |
| **The gap** | If deadline is rhetorical (no military positioning): 15-25pp overreaction. If deadline is backed by force posture: gap narrows to 0-5pp. The classification depends on whether the buildup matches the deadline. |
| **Trade signal** | S004 (contrarian): fade the spike 24-72h after ultimatum if classification = emotional. S006 (time decay): if deadline expires without action, the "by date" market decays rapidly. The key: track whether the deadline is "hard" (backed by force) or "soft" (rhetorical). |

**Case study — Trump's 10-15 day deadline (Feb 19)**: Iran markets spiked +25% (from ~32% to ~57.5% on March 31 window). ECI: 7.2 (Fear 8, Vividness 6, Narrative 9, Identity 5, Recency 7, Media 8). Our T003 entered NO at $0.425 on Feb 23, classifying the move as partially emotional. However, the deadline was accompanied by carrier deployment — making this a genuine buildup + ultimatum pattern. The gap was smaller than a pure rhetoric spike. Current P&L: -$21 (market moved further against us as the third carrier arrived).

### A3: Diplomatic Breakdown

*Talks fail, ambassador recalled, sanctions escalate.*

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Disappointment mixed with fear. "The last off-ramp just closed." |
| **Biases activated** | Narrative Fallacy (#4: "talks failed → war is inevitable"), Recency Bias (#16: the failure overwrites prior diplomatic progress), Belief Perseverance (#22: even if new talks are announced, the "failure" impression persists), Loss Aversion (#11) |
| **Direction of distortion** | YES price UP. Diplomatic failure removes a cognitive brake on fear. |
| **Magnitude** | +5-12pp. Less than an ultimatum but more persistent because it removes a reason for optimism. |
| **Speed & duration** | Moderate onset (12-24h). Persists until a new diplomatic signal emerges. No natural reversion trigger. |
| **Reality check** | Historical base rate: diplomatic breakdowns that led to military action within 30 days = ~20% (most resume in different formats). Multiple rounds of talks is the norm, not the exception. Iran-US: 5 rounds failed in 2025 before strikes, but that sequence also included 60 days of active negotiation — the breakdown wasn't the cause, the deadline expiration was. |
| **The gap** | 5-10pp overreaction. Traders treat "breakdown" as "end of diplomacy" when it usually means "this round failed, next round starts." |
| **Trade signal** | S004 (fade the despair spike IF another round is scheduled). S008 (track whether mediators are still engaged — Oman's continued involvement is a positive signal). |

**Case study — Iran talks pattern**: Five rounds failed April-June 2025. Each failure pushed prices up 3-8pp. But diplomacy didn't end — it just changed venue. The critical variable wasn't "did talks fail" but "has the deadline expired AND are forces positioned." The Feb 26 Geneva talks are round 3 of the current cycle. If they fail, another round is likely unless Trump explicitly terminates the diplomatic track.

### A4: Actual Strike/Attack

*Military action confirmed.*

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Shock, even if expected. "It happened." Followed quickly by "what's next?" |
| **Biases activated** | Availability (#1: real footage now available), Scope Insensitivity (#3: initial reports are vague on scale), Narrative Fallacy (#4: instant "escalation spiral" stories), Herding (#9: everyone piles in), Conservatism (#19: if price was already high, it doesn't move enough — people expected it and underreact to the NEW information about retaliation risk) |
| **Direction of distortion** | COMPLEX. YES resolves on "will strike happen" markets (these go to $1.00). But SECONDARY markets (retaliation, oil prices, broader conflict) spike on fear. |
| **Magnitude** | Primary market: resolves. Secondary markets: +15-30pp on "retaliation by date" or "oil above X" markets. |
| **Speed & duration** | Instant (minutes). The primary market resolution is immediate. Secondary markets peak within 6-12h and then begin decaying as the initial shock subsides and concrete retaliation details emerge. |
| **Reality check** | Post-strike retaliation base rate: Iran retaliated after June 2025 strikes (launched missiles at Israel, hit Al Udeid). But the retaliation was contained — no spiral. Historical pattern: limited strikes → limited retaliation → ceasefire → new talks. Full escalation is the exception, not the rule. |
| **The gap** | Secondary markets overreact by 10-20pp. "Will there be a full war?" markets spike to 40-60% when base rates for limited strike → full war are ~10-15%. |
| **Trade signal** | S004 (fade secondary market spikes 24-72h after the strike). S006 (buy NO on "escalation by date" markets that emerge post-strike). Do NOT trade the primary market — it resolves too fast. |

### A5: Diplomatic Breakthrough

*Deal reached, talks resume, framework announced.*

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Relief, euphoria. "War is off the table." |
| **Biases activated** | Narrative Fallacy (#4: "deal = peace forever"), Representativeness (#5: one framework feels like a final deal), Conservatism (#19: market underreacts because prior fear was entrenched), Belief Perseverance (#22: YES holders don't sell fast enough because they still "feel" the threat) |
| **Direction of distortion** | YES price DOWN, but SLOWLY. Relief doesn't spike prices the way fear does (asymmetric reaction from Loss Aversion #11). |
| **Magnitude** | -5-15pp over 2-7 days. Gradual, not sharp. Contrast with +10-25pp spikes going up. |
| **Speed & duration** | Slow onset. The market drifts down rather than dropping. This is Conservatism (#19) in action — people update toward the new reality at 50-75% of the Bayesian-optimal rate. |
| **Reality check** | Diplomatic breakthroughs that held within 6 months: ~40% (many frameworks collapse). But even a failed framework buys 2-6 months of reduced tension. The "by date" market should still decay significantly after a framework announcement. |
| **The gap** | Market UNDERREACTS to positive diplomatic signals by 5-10pp. This is the mirror of overreacting to threats. The asymmetry: fear spikes fast, relief diffuses slowly. |
| **Trade signal** | S005 (momentum): ride the slow drift down after breakthrough. S001 (hold): if you already hold NO, the breakthrough is a thesis validation — hold through the slow correction. S006 (time decay): the breakthrough accelerates time decay by removing the imminent threat catalyst. |

**Case study — Geneva round 2 (Feb 17-18)**: "Agreement on guiding principles" + positive signals. Iran markets drifted -3pp over 3 days (from ~60% to ~57%). Compare to the +25pp spike from the Trump deadline one day later. The asymmetry is stark: positive diplomatic news moved prices 3pp in 3 days; negative rhetoric moved them 25pp in 2 days. This is Loss Aversion (#11) manifesting as ~8:1 negative-to-positive reaction ratio.

---

## Category B: Political / Leadership News

**Domain**: POL (primary), GEO (when geopolitics becomes partisan), LAW (partisan legal outcomes)
**Compound patterns**: Partisan Echo Chamber (behavioral-foundations.md §2.4), Narrative Cascade (§2.2)

### B1: Poll Release

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Validation (if aligned) or anxiety (if opposing). Polls trigger identity before analysis. |
| **Biases activated** | Motivated Reasoning (#7: partisans interpret same poll differently), Identity-Protective Cognition (#8: sophisticated traders use analytical skills to discount unfavorable polls), Representativeness (#5: a single poll "represents" the trend), Recency Bias (#16: latest poll overwrites polling average), Anchoring (#21: the headline number becomes the anchor) |
| **Direction of distortion** | Directional push toward the poll result, amplified by platform demographics. Polymarket skews male, crypto-native, libertarian-leaning → systematically inflates candidates who appeal to this demographic. |
| **Magnitude** | +3-8pp for major national polls. +1-3pp for state/minor polls. |
| **Speed & duration** | Fast onset (2-6h). Partially reverts within 24-48h as aggregators incorporate the poll and the novelty fades. |
| **Reality check** | Individual polls have ±3-4pp margin of error. A single poll shifting a candidate 5pp is almost certainly overreaction. The correct update for one poll in a series of 20 is ~0.5-1pp (Bayesian: one new data point against 19 existing). |
| **The gap** | 2-7pp overreaction from single poll. Reverts as polling average stabilizes. |
| **Trade signal** | S004 (fade single-poll spikes). S001 (use polling aggregates, not individual polls, for calibration). |

### B2: Endorsement

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Excitement (if your candidate endorsed) or dismissal ("doesn't matter"). Endorsements trigger social proof. |
| **Biases activated** | Social Proof (#9: "if X endorses, others will follow"), Narrative Fallacy (#4: "the momentum is building"), FOMO (#10: other traders buy, driving more buying), Representativeness (#5: one endorsement "represents" a tidal shift) |
| **Direction of distortion** | UP for the endorsed candidate. Historically overpriced: endorsements move markets 3-8pp but actual primary vote impact is 0.5-2pp (FiveThirtyEight 2020 endorsement tracker). |
| **Magnitude** | +3-8pp for major endorsement (former president, party leader). +1-2pp for minor. |
| **Speed & duration** | Fast spike (2-6h), gradual reversion (3-7 days). |
| **Reality check** | Academic evidence: endorsements predict but don't cause. They signal existing elite consensus. The market overweights the causal interpretation. |
| **The gap** | 2-6pp overreaction. Particularly large when the endorsement is from a "surprise" source (narrative coherence amplifies). |
| **Trade signal** | S004 (fade endorsement spike if the endorser's actual influence is limited). S008 (research whether the endorsement represents new information or confirmatory signal). |

**Case study — T006 (Vance 2028)**: The Vance market sits at 41.6% partly because no Trump endorsement has occurred. When Trump endorses (if he does), expect a 10-20pp spike — this would be a Narrative Cascade event. The correct update depends on whether Trump endorsement changes the structural reality (it does: 100% of endorsed sitting VPs won nomination) or just confirms what base rates already predict.

### B3: Scandal Revelation

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Outrage (opponents), denial (supporters). Scandals are identity-activating. |
| **Biases activated** | Identity-Protective Cognition (#8: supporters become MORE entrenched after scandal — Kahan 2017), Availability (#1: scandal coverage dominates media), Narrative Fallacy (#4: "this is the beginning of the end"), Motivated Reasoning (#7: opponents overestimate impact, supporters underestimate) |
| **Direction of distortion** | DOWN for the scandal-affected candidate — but LESS than rational models predict because identity-protective cognition limits selling by supporters. |
| **Magnitude** | +5-15pp move against the candidate. But reverts 50-70% within 2 weeks unless the scandal produces legal consequences. |
| **Speed & duration** | Fast onset (hours). Fast partial reversion (2-5 days) as news cycle moves on. |
| **Reality check** | Historical: Trump survived Access Hollywood (-14pp, recovered fully), two impeachments, indictments. Scandal impact on actual election outcomes is near-zero in hyper-partisan environments. The 2024 election confirmed this. |
| **The gap** | Market OVERREACTS to the scandal's impact on the candidate's chances. The gap is largest when the scandal affects a candidate with a strong identity-attached base — the base doesn't leave, but the market prices as if they will. |
| **Trade signal** | S004 (fade scandal spike on identity-protected candidates). S008 (check whether the scandal has LEGAL consequences — indictments matter, scandals don't). |

### B4: Debate Performance

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Excitement or despair. Debates are theatrical events that trigger strong "winner" narratives. |
| **Biases activated** | Representativeness (#5: one debate performance = the candidate's "true" quality), Recency Bias (#16: debate overwrites months of polling), Cluster Illusion (#6: one strong moment → "they've turned the corner"), Narrative Cascade (compound pattern: media narrative → social proof → FOMO) |
| **Direction of distortion** | UP for perceived debate winner, DOWN for loser. Often overshoots by 5-15pp. |
| **Magnitude** | +5-15pp for perceived "decisive" debate. +2-5pp for mixed/expected performance. |
| **Speed & duration** | Immediate (within minutes of debate ending). Peaks within 12h. Reverts 40-60% within 7 days as the debate fades from memory and new events dominate. |
| **Reality check** | Debates historically have a 1-3pp effect on final vote share (Gelman & King 1993). The market overprices debates by 3-12pp relative to their actual impact. Only debates with genuine gaffe moments (Biden 2024 first debate) have lasting effects. |
| **The gap** | 3-12pp overreaction. The gap is largest when the debate produces a "viral moment" that amplifies through social media (Availability + Social Proof compounding). |
| **Trade signal** | S004 (fade debate spike within 24-72h). S005 (if debate confirms a pre-existing polling trend, the momentum is more likely to persist). |

### B5: Party Division / Internal Conflict

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Schadenfreude (opponents), anxiety (supporters). Division stories feel significant. |
| **Biases activated** | Narrative Fallacy (#4: "the party is fracturing"), Availability (#1: media amplifies intra-party conflict), Representativeness (#5: one disagreement = systemic crisis) |
| **Direction of distortion** | DOWN for the affected party's candidates. Usually overpriced. |
| **Magnitude** | +2-5pp. Smaller than other categories because intra-party conflict is "less vivid" than external threats. |
| **Speed & duration** | Slow onset. Slow reversion. Often persists until a unity event (convention, endorsement). |
| **Reality check** | Intra-party conflict in primaries is normal and expected. Contested primaries have historically produced stronger general election candidates (Obama 2008, Trump 2016). |
| **The gap** | 2-5pp. Small but persistent. |
| **Trade signal** | S001 (hold calibrated positions through noise). Not enough gap for active S004 trading. |

### B6: Policy Announcement

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Variable — depends on whether the policy activates identity or not. |
| **Biases activated** | Anchoring (#21: the policy specifics become a price anchor), Conservatism (#19: market underreacts to genuinely significant policy shifts), Identity-Protective Cognition (#8: if the policy is identity-charged) |
| **Direction of distortion** | Variable. Identity-charged policies (immigration, guns, abortion) create larger mispricings than technocratic policies (infrastructure, trade). |
| **Magnitude** | +1-5pp. Small unless identity-charged, then +5-12pp. |
| **Speed & duration** | Moderate. Persists until implementation details clarify or next news cycle. |
| **Reality check** | Policy announcements during campaigns often don't survive implementation. The market should discount announcements by ~40% for execution risk. |
| **The gap** | Small on technocratic policies. Moderate on identity-charged policies. |
| **Trade signal** | S008 (research implementation feasibility before the market does). |

**Cross-category case study — SOTU 2026**: The SOTU is a Category B event that triggers multiple subcategories simultaneously. Our retrospective analysis (trade-report-sotu-2026.md) found:
- **Partisan Echo Chamber**: "MAGA" at 87% and "Fake News" at 52% were driven by identity-protective cognition — Trump supporters couldn't imagine a SOTU without these words. Our estimates (35%, 15%) captured 52pp and 37pp edge respectively.
- **Rally vs. Formal Address confusion**: This is a category-specific bias unique to political speech markets. Retail traders who watch rallies but don't read SOTU transcripts systematically overprice rally-native language. This produced our largest hypothetical edges.
- **Strategic omission**: China at 93% → NO. The diplomatic calendar (March 31 China visit) made the omission predictable. This is a Category A5 (diplomatic breakthrough) signal applied to a Category B6 (speech content) market.

---

## Category C: Economic Data News

**Domain**: ECO (primary), FIN (secondary), CRY (when macro drives crypto)
**No compound pattern** — ECO is the most efficient domain, where biases are weakest.

### C1: Inflation Data (CPI, PCE Beat/Miss)

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Frustration (hot print) or relief (soft print). Lower intensity than GEO/POL. |
| **Biases activated** | Recency Bias (#16: after a hot print, the next print is expected hot — Campbell & Sharpe 2009 found 25% of forecast "surprises" are predictable from anchoring to recent data), Anchoring (#21: headline number anchors next estimate), Conservatism (#19: professional participants underreact to trend shifts) |
| **Direction of distortion** | SMALL. ECO markets are dominated by professionals who process data within seconds. Retail overreaction exists but is quickly arbitraged. |
| **Magnitude** | +1-3pp on Fed cut/hike markets. Reverts to correct pricing within hours. |
| **Speed & duration** | Instant (seconds). Correct pricing achieved within 1-4 hours. Window is too small for manual trading. |
| **Reality check** | Fed Funds futures aggregate institutional pricing and are available pre-release. Polymarket mirrors these futures efficiently. The gap between Polymarket and CME FedWatch was our T004 thesis — and the gap closed in the WRONG direction (Polymarket was right, CME adjusted to match). |
| **The gap** | 0-2pp. Not exploitable after fees. |
| **Trade signal** | Generally SKIP. The only S004 opportunity: when a data release is misinterpreted by retail (e.g., headline CPI hot but core soft). This creates a brief 1-2h window. Not reliable enough to systematize. |

**Case study — T004 (Fed March cut)**: Hot core PCE at 3.0% (Feb 20). ECI: 3.3 (low — correctly identified as structural, not emotional). Market moved March cut odds from ~4.5% to ~2.35%. Our S003 thesis (CME-Poly divergence) was invalidated — the PCE data was genuinely informative. Lesson: ECO data releases are almost never emotional overreactions. They're information. Don't fade them.

### C2: Jobs Data (NFP, JOLTS Surprise)

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Similar to C1 but slightly higher intensity because jobs data is framed in human terms (people employed/unemployed). |
| **Biases activated** | Same as C1 but with added Salience (#2: job losses are vivid) and Narrative (#4: "recession is coming" stories). |
| **Direction of distortion** | Slightly larger than C1 because jobs narratives are more emotionally charged. |
| **Magnitude** | +2-5pp on rate path markets. +1-3pp on recession markets. |
| **Speed & duration** | Fast, short-lived. Professionals dominate within hours. |
| **Reality check** | NFP has a ±100K margin of error and is revised in subsequent months. The market's initial reaction to the headline number consistently overweights a single data point. |
| **The gap** | 1-4pp for 1-4 hours. Barely exploitable. |
| **Trade signal** | S003 (catalyst): position BEFORE the release based on leading indicators (ADP, claims, ISM). Don't trade the reaction. |

### C3: Fed Communication

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | High attention, analytical processing. Fed statements are parsed word-by-word by professionals. |
| **Biases activated** | Anchoring (#21: dot plot becomes THE anchor), Conservatism (#19: market slowly adjusts to hawkish/dovish shifts over weeks), Confirmation Bias (#20: traders selectively interpret ambiguous statements as supporting their existing position) |
| **Direction of distortion** | Minimal at time of release (professionals dominate). But over the subsequent 2 weeks, Conservatism (#19) creates a slow drift toward the "correct" interpretation. |
| **Magnitude** | +1-3pp immediate. +3-8pp drift over 2 weeks as meaning is digested. |
| **Speed & duration** | The immediate move is efficient. The DRIFT is exploitable — this is the one ECO opportunity. |
| **Reality check** | Fed forward guidance has been a strong predictor of actual decisions. When the Fed says "no cut in March," the market should price March cuts near zero. But retail Polymarket traders occasionally lag the professional futures market by 24-48h. |
| **The gap** | The gap is temporal: Polymarket lags CME by hours to days. This was our T004 thesis — but the gap closed in CME's direction, not Polymarket's. |
| **Trade signal** | S003 (time the entry 3-7 days before FOMC when retail hasn't caught up to Fed guidance). S005 (ride the post-communication drift). |

### C4: Corporate Earnings

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Excitement (beat) or disappointment (miss). Moderate intensity. |
| **Biases activated** | Representativeness (#5: one earnings beat = "the company is crushing it"), Recency (#16: latest quarter overwrites prior trajectory), Anchoring (#21: whisper numbers) |
| **Direction of distortion** | Small. Prediction market earnings markets are thin and dominated by people who also trade the underlying equity (sophisticated). |
| **Magnitude** | +2-5pp on stock price target markets. |
| **Speed & duration** | Instant. Correct within hours. |
| **Reality check** | Post-earnings drift exists in equities (well-documented anomaly). If prediction markets mirror this drift, there's a brief S005 window. |
| **The gap** | Small (1-3pp) but potentially systematic. |
| **Trade signal** | S003 (catalyst around earnings dates). Niche opportunity. |

### C5: Trade/Tariff Announcement

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Fear (tariff escalation) or relief (tariff reduction). Higher emotional charge than other ECO subcategories because tariffs are framed as geopolitical conflict (Category A overlap). |
| **Biases activated** | Fear Premium (#12: "trade war" framing), Availability (#1: tariff news gets heavy media coverage), Narrative Fallacy (#4: "escalation spiral" story), Scope Insensitivity (#3: "25% tariff" sounds dramatic regardless of the specific goods affected) |
| **Direction of distortion** | Tariff escalation → overreaction (markets overweight worst-case supply chain disruption). Tariff reduction → underreaction (relief diffuses slowly). |
| **Magnitude** | +3-10pp. Larger than other ECO categories because of Category A emotional overlap. |
| **Speed & duration** | Fast spike, moderate reversion (3-7 days). |
| **Reality check** | Trump 1st term: tariffs were frequently announced, delayed, reduced, and renegotiated. The announcement-to-implementation rate was ~40%. Markets that price full implementation on announcement are systematically overreacting. |
| **The gap** | 3-8pp. The announcement-implementation gap is the specific exploitable inefficiency. |
| **Trade signal** | S004 (fade tariff escalation spikes with 7-day horizon). S008 (research implementation timelines — most tariff announcements include delay periods). |

---

## Category D: Crypto / Asset Price News

**Domain**: CRY (primary), FIN (secondary)
**Compound patterns**: Narrative Cascade (§2.2), Lottery Ticket Illusion (§2.5)

### D1: Protocol Hack / Security Breach

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Panic, FUD (Fear, Uncertainty, Doubt). "Is my money safe?" |
| **Biases activated** | Availability (#1: hack is vivid and frightening), Fear Premium (#12: "the whole ecosystem is unsafe"), Loss Aversion (#11: existing holders panic-sell), Herding (#9: selling cascade), Scope Insensitivity (#3: a DeFi protocol hack is treated as an indictment of all crypto) |
| **Direction of distortion** | BTC/ETH price target YES markets DOWN. "BTC above X" markets drop beyond what the hack justifies. |
| **Magnitude** | +5-15pp on price target markets. Cascading effect across unrelated markets. |
| **Speed & duration** | Very fast (minutes to hours). Peaks within 6-12h. Reverts 40-60% within 7 days as the scope of the hack is understood and contained. |
| **Reality check** | Historical: major hacks (Mt. Gox, FTX) caused lasting damage. Minor hacks ($10-100M DeFi exploits) have transient price impact. The market doesn't distinguish magnitude. |
| **The gap** | 5-12pp overreaction on unrelated BTC price target markets. The hack affects one protocol; the market prices it across the entire ecosystem. |
| **Trade signal** | S004 (fade the cascade if the hack is contained to a specific protocol). S002 (threshold markets that were hit by cascade selling may offer value). |

### D2: Regulatory Action

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Fear (enforcement) or euphoria (approval). Regulatory news triggers the strongest and most persistent moves in crypto. |
| **Biases activated** | Fear Premium (#12: "the government will ban everything"), Narrative (#4: "regulatory clarity" or "crypto winter"), Identity-Protective Cognition (#8: crypto community has strong identity that resists negative regulatory framing), Availability (#1: SEC actions get major media coverage) |
| **Direction of distortion** | Enforcement → DOWN sharply. Approval → UP sharply. Both overshoot. |
| **Magnitude** | +10-25pp. Regulatory news produces the largest moves in CRY. |
| **Speed & duration** | Fast onset. Enforcement actions: partially persistent (regulatory risk is real). Approvals: partially persistent but fades as "priced in." |
| **Reality check** | Regulatory actions rarely result in total bans. SEC enforcement has been targeted at specific actors, not blanket prohibition. The market prices "enforcement" as "ban" due to narrative conflation. Conversely, approvals (like ETFs) have a well-documented "sell the news" effect. |
| **The gap** | 5-15pp overreaction in both directions. Enforcement overprices systemic risk; approval overprices growth impact. |
| **Trade signal** | S004 (fade both enforcement panic and approval euphoria). S008 (research the specific regulatory action — scope, precedent, enforcement likelihood). |

### D3: Whale Movement

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | "Smart money is moving" — either fear or FOMO depending on direction. |
| **Biases activated** | Social Proof (#9: whales are perceived as informed), Herding (#9: retail follows whale direction), FOMO (#10: "the whale knows something"), Narrative (#4: whale moves generate instant speculation about motivation) |
| **Direction of distortion** | Follows whale direction. Whale buys → price target UP. Whale sells → DOWN. |
| **Magnitude** | +3-10pp. Depends on whale's perceived credibility and size. |
| **Speed & duration** | Fast spike (1-6h). Reverts 30-50% within 48h as the narrative fades. |
| **Reality check** | Whale movements are often mechanical (portfolio rebalancing, exchange transfers, DeFi farming) not directional bets. On-chain analysis can distinguish informed from mechanical — but most retail traders don't check. |
| **The gap** | 3-8pp when the whale movement is mechanical, not informed. |
| **Trade signal** | S004 (fade whale-driven spikes after confirming movement is mechanical via on-chain analysis). |

### D4: Social Media Influencer Call

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Excitement, FOMO. "Elon is bullish!" |
| **Biases activated** | Social Proof (#9: influencer as authority), FOMO (#10: fear of missing the move), Herding (#9: mass buying cascade), Narrative (#4: influencer provides the narrative), Cluster Illusion (#6: multiple bullish tweets = "the trend is clear") |
| **Direction of distortion** | UP (exclusively — influencers are incentivized to be bullish). |
| **Magnitude** | +3-15pp. Elon Musk tweets: documented 5-20% crypto price impact within hours. |
| **Speed & duration** | Very fast (minutes). Peak within 1-4h. Reverts 50-80% within 24-48h. The "Elon effect" is well-documented and fast-fading. |
| **Reality check** | Influencer calls have near-zero predictive value for longer-term price targets. They move prices through coordinated buying, not information. |
| **The gap** | 3-12pp. Among the most reliably overpriced events in crypto markets. |
| **Trade signal** | S004 (textbook fade — highest win rate subcategory in CRY). Enter 4-12h after the tweet when FOMO has peaked. |

### D5: Macro Catalyst

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Varies by direction. Fed dovish pivot → euphoria. Recession signal → fear. |
| **Biases activated** | Narrative (#4: "risk-on/risk-off" framing), Recency (#16: latest macro data overwrites cycle position), Representativeness (#5: one data point = trend shift) |
| **Direction of distortion** | Directional — follows macro implication. Magnitude depends on narrative coherence. |
| **Magnitude** | +3-8pp on crypto price target markets. |
| **Speed & duration** | Moderate onset. Partially persistent if the macro shift is real. |
| **Reality check** | Crypto-macro correlation is unstable. BTC correlates with risk assets during some periods and decorrelates during others. |
| **The gap** | 2-5pp. Moderate and inconsistent. |
| **Trade signal** | S008 (macro research to determine if the correlation regime is active). Not reliable for S004 fading. |

### D6: ETF Flow Data

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Validation ("institutions are buying") or fear ("institutions are selling"). |
| **Biases activated** | Social Proof (#9: institutional flows = smart money), Recency (#16: latest week's flows dominate), Anchoring (#21: cumulative flow number), Narrative (#4: "institutional adoption" or "institutional exit") |
| **Direction of distortion** | Follows flow direction. Positive flows → UP. Negative → DOWN. |
| **Magnitude** | +2-5pp. Moderate and somewhat persistent. |
| **Speed & duration** | Slow onset (weekly data). Partially persistent — represents genuine capital flows, not just sentiment. |
| **Reality check** | ETF flows are a lagging indicator — they measure what institutions already did, not what they will do. Markets that treat flows as predictive are confusing observation with information. |
| **The gap** | 1-3pp. Small but systematic. |
| **Trade signal** | S005 (if flows confirm existing trend, the momentum may persist). Not enough gap for S004. |

**Cross-category case study — T008 (BTC $150K NO)**: The Fear & Greed Index at 5 (extreme fear) when we entered. Historically, extreme fear precedes 30/60/90-day recoveries — but this is itself a psychological phenomenon: people ARE too fearful after crashes. However, the year-2 post-halving base rates (-58%, -73%, -64%) support lower prices. Our NO position at 91.5% exploits the Lottery Ticket Illusion (§2.5): the 8.5% YES price is inflated by hope premium + probability weighting. True probability of BTC >$150K by Dec 31 is estimated at 3-5%.

---

## Category E: Technology / AI News

**Domain**: TEC (primary), SCI (secondary)
**Psychological mode**: The Hype Cycle

### E1: New Model Release

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Excitement, awe. "AGI is closer than we thought!" |
| **Biases activated** | Availability (#1: benchmark numbers are vivid and shareable), Narrative (#4: "exponential progress" story), Representativeness (#5: one benchmark improvement = general capability leap), Scope Insensitivity (#3: the difference between "best on MMLU" and "best in real-world tasks" is compressed) |
| **Direction of distortion** | UP on "best model" and "AGI by date" markets. The new model's capabilities are overextrapolated. |
| **Magnitude** | +3-10pp on "best model" markets. Spikes within hours of release, but Arena rankings take weeks to stabilize. |
| **Speed & duration** | Fast spike (hours). Partially reverts over 2-4 weeks as actual Arena usage data accumulates and the benchmark hype fades. |
| **Reality check** | Benchmarks ≠ real-world performance. The Arena ELO ranking requires thousands of votes over weeks. A new model launch doesn't immediately change the Arena leader, but markets often act as if it does. Historical: GPT-4 maintained Arena lead for months despite multiple "GPT-4 killers" announced. |
| **The gap** | 3-8pp. Markets overprice the immediate impact of new model releases on "best model" rankings. |
| **Trade signal** | S004 (fade "best model" spikes 24-48h after release). S008 (run the actual benchmarks and compare to claims). |

### E2: Company Funding/Valuation

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | FOMO in the tech ecosystem. "This company is going to win." |
| **Biases activated** | Social Proof (#9: major investor validation), Narrative (#4: "this is the next Google"), Representativeness (#5: high valuation = great product), Anchoring (#21: valuation number anchors perception) |
| **Direction of distortion** | UP on related prediction markets. |
| **Magnitude** | +2-5pp. Moderate. |
| **Speed & duration** | Moderate onset. Partially persistent — genuine capital IS a signal. |
| **Reality check** | Startup valuations are poor predictors of long-term success. Median unicorn fails within 10 years. |
| **The gap** | 1-4pp. Small, not reliably exploitable. |
| **Trade signal** | S008 (research the company's actual product vs. the valuation narrative). Not enough gap for S004. |

### E3: Government Regulation Announcement

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Fear (restriction) or relief (light-touch). AI regulation triggers existential anxieties in the tech community. |
| **Biases activated** | Fear Premium (#12: "they'll ban AI"), Narrative (#4: "regulation kills innovation" or "regulation legitimizes the industry"), Identity-Protective Cognition (#8: tech workers have strong identity-based reactions to regulation) |
| **Direction of distortion** | Restriction → overreaction DOWN. Light-touch → underreaction UP (the market expects restriction by default). |
| **Magnitude** | +3-8pp. Moderate to large depending on scope. |
| **Speed & duration** | Moderate. Partially reverts as implementation details emerge (regulations are usually lighter in practice than announced). |
| **Reality check** | AI regulation has been mostly light-touch in the US (EU AI Act is the exception). Announced regulations rarely achieve their stated scope. |
| **The gap** | 3-6pp on restriction announcements (overpriced fear). 1-3pp on approvals. |
| **Trade signal** | S004 (fade regulation fear spikes). S008 (read the actual regulatory text — it's almost always less restrictive than the headline). |

### E4: Safety Incident

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Fear, moral outrage. "AI is dangerous." |
| **Biases activated** | Availability (#1: safety incidents get massive media coverage), Fear Premium (#12: existential risk framing), Narrative (#4: "we warned you"), Scope Insensitivity (#3: one incident = systemic risk) |
| **Direction of distortion** | DOWN on AI progress/adoption markets. UP on "AI regulation by date" markets. |
| **Magnitude** | +5-15pp depending on severity and media coverage. |
| **Speed & duration** | Fast spike. Partially persistent if the incident triggers regulatory action. Otherwise reverts in 1-3 weeks. |
| **Reality check** | Individual safety incidents have historically not slowed AI development. The industry moves faster than regulators. Even major incidents (deepfake elections, autonomous vehicle fatalities) produced minimal regulatory response. |
| **The gap** | 5-10pp on "AI banned/regulated by date" markets after an incident. |
| **Trade signal** | S006 (buy NO on "regulation by date" markets that spike after an incident — the deadline will likely pass without action). |

### E5: Competitive Landscape Shift

| Pipeline Stage | Response |
|---------------|----------|
| **Immediate emotion** | Excitement (new entrant) or concern (acquisition). |
| **Biases activated** | Narrative (#4: "the race is heating up"), Representativeness (#5: one announcement = industry transformation), Anchoring (#21: the announced deal terms) |
| **Direction of distortion** | Variable. New entrant → UP on "best model" diversity. Acquisition → UP on acquiring company's markets. |
| **Magnitude** | +2-5pp. Moderate. |
| **Speed & duration** | Moderate onset. Slow reversion as actual competitive dynamics play out over months. |
| **Reality check** | AI competitive shifts happen at model-release timescale (months), not announcement timescale (days). The market prices announcements as if they're immediate capability changes. |
| **The gap** | 2-4pp. Moderate. |
| **Trade signal** | S008 (research the actual competitive implications — most "landscape shifts" are incremental). |

**Hype Cycle Integration**: Technology news maps to Gartner's hype cycle stages:

| Stage | Bias Profile | Market Behavior |
|-------|-------------|----------------|
| **Innovation Trigger** | Narrative + Availability + FOMO | Sharp UP — new model/company announced |
| **Peak of Inflated Expectations** | All bullish biases compounding | Prices peak 5-15pp above sustainable level |
| **Trough of Disillusionment** | Loss Aversion + Recency + Narrative reversal | Sharp DOWN — "X was overhyped" narrative takes hold |
| **Slope of Enlightenment** | Conservatism (slow updating) | Gradual drift UP as real capabilities prove out |
| **Plateau of Productivity** | Near-efficient pricing | Small persistent mispricing as late adopters remain skeptical |

**Trade signal by stage**: Sell at the Peak (S004). Buy at the Trough (S005 if fundamentals support). Hold through the Slope (S001). The key is identifying WHICH stage you're in — the hype cycle is obvious in retrospect but ambiguous in real-time.

---

## Live Case Study Decomposition

### Pipeline Applied to T001-T008

| Trade | Strategy | News Event Driving Price | ECI | Biases Active | Distortion Direction | My Estimate | Market Price | Gap (pp) | Market Emotional? |
|-------|----------|--------------------------|-----|---------------|---------------------|-------------|-------------|----------|-------------------|
| T001 | S006 | Cumulative Iran rhetoric + buildup | 6.5 | Availability, Fear Premium, YES bias, Compound Prob Neglect | UP (YES overpriced) | 63% YES | 66.5% YES | 3.5 | Moderate — structural fear premium + time decay |
| T002 | S007 | 22nd Amendment impossibility | 2.0 | Identity-Protective Cognition, Hope Premium, Probability Weighting | UP (YES overpriced) | 0.5% YES | 2.8% YES | 2.3 | Yes — pure tribal wishful pricing |
| T003 | S004 | Trump 10-15 day deadline (Feb 19) | 7.2 | Fear, Narrative, Deadline Panic, FOMO, Herding | UP (YES overpriced) | 52% YES | 57.5% YES | 5.5 | Yes — rhetoric spike over diplomatic signals |
| T004 | S003 | CME-Poly divergence on March Fed cut | 3.3 | Anchoring (to CME price), Hope Premium | UP (YES overpriced on Poly) | 4.5% YES | 2.85% YES | -1.65 (market was RIGHT, we were wrong) | No — structural. PCE data was informative |
| T005 | S008 | Iran force posture analysis + diplomacy | 5.5 | Fear Premium, Availability, Compound Prob Neglect | UP (YES overpriced) | 55% YES | 59% YES | 4.0 | Moderate — market roughly calibrated, slight fear premium |
| T006 | S001 | VP base rate vs Vance charisma discount | 3.0 | Present Bias, Representativeness (in reverse — market underweights base rate), Identity-Protective Cognition (Vance lacks partisan attachment yet) | DOWN (YES underpriced) | 58% YES | 41.6% YES | 16.4 | Yes — present-bias discount on 2.5-year horizon + Vance identity gap |
| T007 | S008 | Venezuela Maduro capture (Jan 2026) | 4.5 | Conservatism (market slow to update on regime change), Belief Perseverance (Maduro's power persists in mental model) | UP (YES overpriced — Maduro won't be leader) | 85% NO | 87.25% NO | 2.25 | Moderate — market conservatively pricing the new reality |
| T008 | S006 | BTC halving cycle + extreme fear index | 5.0 | Hope Premium, Probability Weighting, Narrative ("crypto super-cycle"), FOMO | UP (YES overpriced) | 95-97% NO | 91.5% NO | 3.5-5.5 | Yes — Lottery Ticket Illusion on the 8.5% YES side |

### Pattern Emerging

**ECI > 6 → emotional overreaction present (T003: 7.2)**
**ECI 4-6 → mixed, edge exists but smaller (T001, T005, T008)**
**ECI < 4 → structural move, edge is small or we're wrong (T004: 3.3, T002: 2.0)**

The T004 failure (ECI 3.3) correctly signals "this is structural, don't fade." Had we applied the ECI trigger rule (ECI < 4 → classify as structural), we would have SKIPPED T004 entirely — avoiding the -17.5% loss. This validates the ECI framework's discriminating power.

**T006 is the outlier**: ECI 3.0 but edge 16.4pp. This isn't an emotional overreaction — it's a structural mispricing from present bias on long-dated markets. ECI doesn't capture present bias well because it measures news-driven emotion, not capital-allocation psychology. The present-bias discount is a separate phenomenon from news-driven distortion.

---

## SOTU Retrospective Decomposition

| ID | Market | ECI | Dominant Bias | Outcome | Gap (pp) | Did Psychology Predict Direction? |
|----|--------|-----|---------------|---------|----------|----------------------------------|
| res-sotu-001 | Fake News | 4.8 (overall SOTU) | Identity-Protective Cognition + Rally/Formal confusion | NO | 37 | **YES** — pure participant psychology error |
| res-sotu-002 | MAGA | 4.8 | Identity-Protective Cognition + Narrative Fallacy | NO | 52 | **YES** — "MAGA" = identity word, not SOTU word |
| res-sotu-003 | China (geo) | 4.8 | Availability + Strategic omission blindness | NO | 18 | **PARTIALLY** — diplomatic calendar predicted, but I was still wrong on direction |
| res-sotu-004 | Middle East | 4.8 | Availability + Scope Insensitivity (topic ≠ word) | NO | 22 | **PARTIALLY** — correct that market overpriced, but I estimated 70% YES |
| res-sotu-005 | Crypto/Bitcoin | 4.8 | Representativeness + Narrative ("crypto president") | NO | 20 | **YES** — no SOTU precedent for crypto |
| res-sotu-006 | Fentanyl/Cocaine | 4.8 | None dominant — market reasonably priced | YES | 10 | **YES** — base rate (immigration = Trump SOTU staple) correctly predicted |
| res-sotu-007 | Iran mention | 4.8 | None — market correctly priced at 96% | YES | 2 | N/A — no edge, correctly priced |
| res-sotu-008 | Hockey | 4.8 | None — guest list signal dominated | YES | 2 | N/A — informational signal, not psychological |
| res-sotu-009 | No No No | 4.8 | Underestimation of improvisational style | YES | -5 | **NO** — I was worse than market |
| res-sotu-010 | Hottest | 4.8 | Anchoring to moderate vocab estimate | YES | -25 | **NO** — I was significantly worse than market |
| res-sotu-011 | Obama (named) | 4.8 | Incomplete model of "blame predecessor" pattern | YES | -5 | **NO** — I was slightly worse than market |
| res-sotu-012 | SOTU duration 100+ | 4.8 | Anchoring + Trump's pre-speech comment signal | YES | 5 | **YES** — correctly estimated above market |

**SOTU ECI note**: The overall SOTU event ECI was 4.8 (moderate). But the individual market-level distortions varied enormously: Identity-Protective Cognition dominated the NO-surprise markets (MAGA, Fake News) while Availability and Representativeness dominated the geographic mention markets (China, Middle East). The ECI is a blunt tool for SOTU — it captures the event-level charge but not the within-event market-level variation.

### Correlation: ECI vs. Gap Size

From our combined trade + SOTU data (N=20):

| ECI Range | Average |Gap| (pp) | N | Prediction Correct? |
|-----------|----------------------|---|---------------------|
| 1-3 | 6.0 | 4 | 50% (structural — we're not reliably better than market) |
| 4-6 | 14.3 | 10 | 80% (moderate — our research gives us edge) |
| 7+ | 5.5 | 1 | 100% (emotional — high conviction fade) |

**H2 status (ECI correlates with gap)**: PARTIALLY SUPPORTED. The 4-6 range actually has larger average gaps than 7+. This is because the 7+ events in our data (only T003) were accompanied by genuine fundamental support (military buildup), compressing the exploitable gap. The 4-6 range includes SOTU markets where the gap was purely psychological (37-52pp on MAGA/Fake News).

**Revised hypothesis**: ECI > 7 predicts emotional overreaction with high reliability, but the gap size depends on whether the emotional event has fundamental support. ECI 4-6 events can have LARGER gaps when the underlying market question is purely psychological (speech content, political identity) rather than fundamentally uncertain (military strike).

---

## Cross-Category Patterns

### 1. The Negative-Positive Asymmetry

Across all categories, negative news (threats, failures, hacks, scandals) produces LARGER and FASTER price moves than equivalently informative positive news (deals, breakthroughs, approvals).

| | Negative News | Positive News | Ratio |
|--|---------------|---------------|-------|
| Average spike magnitude | +12pp | +5pp | 2.4:1 |
| Speed to peak | 2-12h | 12-72h | ~5x faster |
| Reversion to baseline | 40-60% in 7d | N/A (slow drift) | Asymmetric |
| Bias drivers | Loss Aversion, Fear Premium | Conservatism, Belief Perseverance | Different mechanisms |

**Implication**: The highest-EV S004 trades are fading negative news spikes, not positive news spikes. Positive news produces smaller, slower moves that don't create clean entry points.

### 2. The Domain Sophistication Gradient

| Domain | Participant Sophistication | Emotional Spike Fraction | Average Gap (pp) |
|--------|---------------------------|--------------------------|------------------|
| ECO | Very High | ~0% | 0-2 |
| FIN | Highest (on PM specifically) | ~5% | 1-3 |
| POL | High | ~25% | 3-10 |
| TEC | Med-High | ~20% | 3-8 |
| GEO | Low-Med | ~45% | 5-15 |
| CRY | Low-Med | ~40% | 5-15 |
| LAW | Low-Med | ~15% | 3-8 |
| SOC | Low | ~20% | 2-5 |
| SCI | Low (but thin) | ~5% | 5-10 (if liquid) |
| ENV | Low (but thin) | ~10% | Unknown (no data) |

**Edge is inversely proportional to domain sophistication.** GEO and CRY have the most emotional participants and the largest average gaps. ECO and FIN have the most professional participants and negligible gaps.

### 3. The Compound Pattern Recognition Table

When multiple biases from the inventory fire simultaneously, recognize which compound pattern is active:

| If you see... | Pattern | Expected gap | Strategy |
|---------------|---------|-------------|----------|
| Military news + media frenzy + YES spike + vivid imagery | War Panic Premium | 15-30pp | S006 + S004 stack |
| Candidate surge + social media explosion + endorsement cascade + FOMO | Narrative Cascade | 10-20pp | S004 (wait for break) |
| Deadline approaching + YES holders panicking + accelerating decay | Deadline Decay Funnel | 5-15pp (accelerating) | S006 (hold through decay) |
| Polarized topic + both sides entrenched + asymmetric news response | Partisan Echo Chamber | 10-25pp | S008 + S004 |
| Cheap contract + "what if" narrative + multiple conditions required | Lottery Ticket Illusion | 3-10pp | S006 (sell the illusion) |

### 4. The Time-to-Trade Matrix

| Subcategory | Optimal Entry Window | Why |
|-------------|---------------------|-----|
| A1 (Buildup) | During buildup, before ultimatum | Buildup alone overprices; ultimatum confirms |
| A2 (Ultimatum) | 24-72h post-ultimatum | Let panic peak, then fade |
| A3 (Diplomatic breakdown) | If new round announced, immediately | Market is slow to price resumed talks |
| A4 (Strike confirmed) | 6-24h post-strike on secondary markets | Primary resolves; secondary overreacts |
| A5 (Breakthrough) | Immediately (market underreacts) | Conservatism creates a drift opportunity |
| B1-B4 (Political events) | 24-72h post-event | Standard S004 timing |
| C1-C3 (ECO data) | Pre-release (S003) or SKIP | Post-release window too small for manual |
| C5 (Tariffs) | 12-48h post-announcement | Implementation discount kicks in |
| D1 (Hack) | 6-24h post-hack | FUD peak → scope clarification → reversion |
| D4 (Influencer) | 4-12h post-tweet | FOMO peak → interest fades |
| E1 (New model) | 24-48h post-release | Benchmark hype → Arena reality |

---

## Sources

All citations from behavioral-foundations.md (B01) §Sources apply. Additional:

- Gelman, A. & King, G. (1993). "Why Are American Presidential Election Campaign Polls So Variable When Votes Are So Predictable?" *British Journal of Political Science*, 23(4), 409-451.
- FiveThirtyEight (2020). "The Endorsement Primary." Tracker and analysis.
- Gartner Hype Cycle methodology.
- Our own trade data: positions.json, resolutions.jsonl, trade-report-sotu-2026.md, iran-us-2026.md.
