# Resolution Window Analysis: Empirical Findings

**Date**: 2026-02-25
**Purpose**: Map the timeline from real-world event → price movement → resolution proposal → market settlement. Determine if manual traders can exploit resolution lag.

---

## 1. The Resolution Pipeline (MOOV2)

### How Resolution Works (Post-Aug 2025)

```
EVENT OCCURS in real world
    ↓
Market price reacts (seconds to hours, depending on event clarity)
    ↓
MOOV2 PROPOSER submits resolution answer + $750 bond
    ↓
2-hour liveness period (trading continues)
    ↓
No dispute → Market resolves → Shares redeem at $1.00 or $0.00
```

### MOOV2 Proposers

- **37 whitelisted proposers** (launched via UMIP-189, passed August 6, 2025)
- Composition: Risk Labs employees, Polymarket employees, experienced community members with 20+ proposals at >95% accuracy
- **Key change from OOV2**: Only whitelisted addresses can propose. Anyone can still dispute.
- **Motivation**: Direct response to Ukraine mineral deal governance attack (March 2025)
- **Criticism**: Centralizes resolution authority in ~37 people without fixing UMA voting power concentration

### Dispute Escalation

```
Proposal ($750 bond) → 2h liveness
    ↓ (if disputed)
First dispute ($750 counter-bond) → Adapter ignores, creates new Request
    ↓
Second proposal ($750 bond) → 2h liveness
    ↓ (if disputed again)
DVM escalation → UMA token holder vote (~48-96h)
    ↓
Resolution based on vote
```

**Critical**: Trading continues throughout the entire dispute process. During a dispute, you're betting on how UMA voters will resolve, not on the underlying event.

### Proposal Speed Factors

| Factor | Impact on Speed |
|--------|----------------|
| Event clarity | Binary outcomes (Fed: yes/no) → minutes. Ambiguous ("deal reached") → hours to days |
| Time of day | Proposers are human. 3am UTC = slower |
| Market size | High-volume markets get faster attention |
| Resolution criteria complexity | Simple criteria → fast. Multi-conditional → slow |

---

## 2. Reconstructed Timelines (5 Cases)

### Case 1: 2024 Presidential Election (Clear Outcome, Procedural Delay)

| Timestamp | Event |
|-----------|-------|
| Nov 5, ~11 PM ET | Early returns favor Trump, price climbs toward 90% |
| Nov 6, ~1:45 AM ET | Fox News calls race for Trump. Price at 98.8c |
| Nov 6, ~11 AM ET | AP and NBC officially call the race (Polymarket required AP + NBC + Fox agreement) |
| Nov 6, ~11:15 AM ET | Resolution proposed |
| Nov 6, ~1:15 PM ET | Market resolves (2h liveness, no dispute) |

**Gap**: ~9 hours between "market knows" (98.8c at 1:45 AM) and formal resolution.
**Exploitable?**: NO — price already at 98.8c. The 1.2c remaining was correctly priced resolution risk.

### Case 2: Fed Rate Decisions (Unambiguous, Fast)

| Timestamp | Event |
|-----------|-------|
| T+0 seconds | FOMC statement released |
| T+2-5 seconds | Bots snap price to 99%+ |
| T+5-15 minutes | MOOV2 proposer submits resolution |
| T+2h 15min | Market resolves (undisputed) |

**Gap**: Essentially zero for price movement. 2-5 seconds of lag.
**Exploitable?**: NO — bots dominate. Sub-100ms execution required.
**Note**: Fed decisions have NEVER been disputed on Polymarket. Perfect resolution clarity.

### Case 3: Ukraine Mineral Deal (Ambiguous, Manipulated)

| Timestamp | Event |
|-----------|-------|
| Day 0 | Market at 9% |
| Day 1 | News of "framework discussions." Price surges to ~50% |
| Day 2 | Price reaches 100% with no binding agreement signed |
| Day 2-3 | MOOV2 proposal submitted for YES |
| Day 3 | Dispute filed (counter-bond $750) |
| Day 4-6 | DVM vote. UMA whale casts 5M tokens (25% of voting power) across 3 accounts |
| Day 6 | Resolved YES despite no deal existing |

**Gap**: Multiple days of disputable trading.
**Exploitable?**: YES — but on the wrong side. Manipulation made the "correct" bet lose.
**Lesson**: Ambiguous markets + whale UMA concentration = unpredictable resolution.

### Case 4: Israel-Lebanon "Invasion" (Ambiguous, Multi-Round Dispute)

| Timestamp | Event |
|-----------|-------|
| Sep 2024 | IDF begins "limited ground operations" in southern Lebanon |
| Sep-Oct | Market debates whether this constitutes an "invasion" |
| Round 1 | Proposal: YES. Disputed. |
| Round 2 | Proposal: NO. Disputed. |
| Round 3+ | UMA consistently votes NO across multiple rounds |
| Weeks later | Final resolution: NO |

**Gap**: Weeks of trading at 40-70% while the outcome was being debated.
**Exploitable?**: YES — if you understood UMA's "spirit of the market" principle. "Invasion" in common usage implies large-scale, not "limited operation." UMA voted NO because public understanding of "invasion" didn't match IDF's operation.

### Case 5: Zelenskyy Suit (Ambiguous, High-Value)

| Timestamp | Event |
|-----------|-------|
| Jun 24, 2025 | Zelenskyy appears in what most would call a "suit" at public event |
| Jun 24-25 | Price surges toward YES |
| Jun 25-26 | Dispute filed — market's specific definition of "formal suit" was narrower than common usage |
| Jul 1, 2025 | UMA final ruling: NO (7 days to resolve) |

**Gap**: 7 days of trading while resolution was disputed.
**Financial impact**: $14M direct market, $237M in related markets affected.
**Exploitable?**: YES — the resolution criteria text was more specific than the title suggested. Anyone who read the fine print knew NO was likely.

---

## 3. Post-Event Price Dynamics

### Speed of Price Adjustment by Event Type

| Event Type | Price Adjustment Speed | Who Captures It |
|------------|----------------------|-----------------|
| Fed rate decisions | 2-5 seconds | Bots exclusively |
| Sports results (live) | 15-40 seconds broadcast lag | Bots (one turned $5 → $3.7M) |
| Election calls | 30 min - 2h (builds gradually as sources confirm) | Early bots + informed humans |
| BTC price milestones | 30-90 seconds Polymarket lag vs. exchange price | Bots |
| Geopolitical events | Hours to days (ambiguity delays price adjustment) | Humans with domain knowledge |
| Ambiguous resolutions | Days to weeks (dispute process) | Humans who understand UMA |

### Key Finding: The Speed Gradient

```
FAST (bot-dominated, no human edge)
├── Fed decisions: 2-5 seconds
├── Sports: 15-40 seconds
├── BTC price: 30-90 seconds
├── Clear elections: 30 min - 2h
│
SLOW (human-accessible, judgment required)
├── Ambiguous geopolitical: hours to days
├── "Deal reached" type markets: days
└── Disputed resolutions: days to weeks
```

**The human opportunity exists ONLY in the slow end** — events where:
1. The outcome is ambiguous (does this count as a "strike"?)
2. Resolution criteria are unclear
3. Multiple interpretations are defensible
4. UMA's interpretation principles favor one side

### Bot Landscape

- **Execution speed**: ~80ms average, 99.2% success rate
- **Documented profit**: $5 → $3.7M (one bot, sports broadcast lag)
- **Polymarket response**: Dynamic taker fees on short-duration markets (5-min, 15-min crypto)
- **Coverage**: Bots monitor all high-volume markets continuously

**Conclusion**: Any strategy requiring sub-minute reaction is a bot's game. Human edge requires judgment, not speed.

---

## 4. Dispute Window Trading

### During the 2-Hour Liveness Period

- Trading continues normally
- Price typically sits at 97-99c for undisputed outcomes
- The 1-3% discount is the "resolution risk premium"
- **Annualized return**: Buying at 98c for 2-hour resolution = 1.02% per 2 hours = enormous annualized

### During Dispute Periods (3-6 days)

- Trading continues throughout
- Price reflects market's estimate of how UMA will vote
- Typical range: 60-90% for the side most expect to win
- **The real opportunity**: Understanding UMA voting dynamics better than the market

### The S011 Connection

Buying at 97-99c during the liveness period (when outcome is known but not formally resolved) is S011 — High-Probability Bond Rotation. The risk is exclusively oracle risk.

---

## 5. UMA Interpretation Principles (Ranked by Importance)

### Principle 1: Title Over Technical Rules

UMA consistently resolves based on the market title's "spirit" rather than fine-print technicalities. The title is treated as the primary resolution instrument.

**Example**: If a market is titled "Will Trump invade Mexico?" and the fine print adds nuances about "boots on the ground," UMA will interpret "invade" per common public understanding, not legal definitions of "invasion."

### Principle 2: Public Consensus Over Official Sources

UMA uses Western English-language media as the primary evidence standard. Official government pronouncements from non-Western sources carry less weight.

**Example**: Venezuela presidential election — resolved for Gonzalez based on "credible reporting" from Western media, despite the official Venezuelan government recognizing Maduro.

### Principle 3: "Not a Court"

Lawyerly arguments about precise wording are generally unsuccessful. UMA voters are not judges parsing legal text — they vote based on "reasonable person" interpretation.

### Principle 4: Polymarket Clarifications Are Binding

When Polymarket issues a clarification on resolution criteria, UMA has NEVER overturned that clarification. Polymarket's interpretation is effectively final.

**Exception**: Barron Trump/$DJT market (June 2024) — Polymarket overrode UMA's resolution. This is the only documented case of Polymarket overriding UMA.

### Principle 5: UMA Rarely Reverses Across Rounds

Once UMA votes a direction in Round 1, subsequent rounds almost always confirm the same outcome. The first vote is strongly predictive.

### Principle 6: Status Quo Bias

In genuinely ambiguous cases where neither YES nor NO is clearly supported, UMA tends to vote NO / status quo / no change. This creates a structural tilt toward NO in ambiguous markets.

---

## 6. Resolution Ambiguity Patterns (Top 10)

### Pattern 1: "Action" Definition Ambiguity
**Markets**: "US strikes Iran," "Israel invades Lebanon," "Venezuela invasion"
**Issue**: What constitutes a "strike," "invasion," or "military action"?
**UMA tendency**: Interprets narrowly — "invasion" requires large-scale ground operation, not surgical raids
**Financial impact**: Israel-Lebanon (NO across multiple rounds), Venezuela (NO, payouts withheld)

### Pattern 2: "Agreement" Definition
**Markets**: "Ukraine mineral deal," "Iran nuclear deal," any "deal reached" market
**Issue**: Does a "framework," "preliminary agreement," or "memorandum of understanding" count?
**UMA tendency**: Inconsistent — Ukraine mineral deal resolved YES without a signed document (but was likely manipulated)
**Financial impact**: Ukraine mineral deal ($7M incorrect resolution)

### Pattern 3: "By Date" Temporal Boundary
**Markets**: Any "by [date]" market
**Issue**: Does the event need to occur by the date, or does the resolution criteria allow for events after the date?
**UMA tendency**: Strict temporal cutoff — if the event hasn't occurred by the stated date, resolves NO
**Financial impact**: Generally clean; low ambiguity

### Pattern 4: Clothing/Appearance Definitions
**Markets**: "Zelenskyy wears a suit," dress code markets
**Issue**: What counts as a "suit"? "Formal attire"?
**UMA tendency**: Narrow interpretation per resolution criteria (not common usage)
**Financial impact**: $14M direct, $237M related

### Pattern 5: "Leader" / "President" Definition
**Markets**: "Maduro is leader of Venezuela"
**Issue**: De facto vs. de jure leader? Recognized by whom?
**UMA tendency**: Likely public consensus (Western media interpretation)
**Financial impact**: T007 in our portfolio — potential resolution risk

### Pattern 6: Mention/Reference Markets
**Markets**: SOTU mention markets ("Trump says China," "Trump says MAGA")
**Issue**: Does a passing reference count? A euphemism?
**UMA tendency**: Requires clear, unambiguous mention
**Financial impact**: Large SOTU market complex ($9.5M total)

### Pattern 7: "Best" / Ranking Markets
**Markets**: "Best AI model," "Top-ranked team"
**Issue**: According to which ranking? At what exact time? With what methodology?
**UMA tendency**: Uses the resolution criteria's specified source
**Financial impact**: Moderate — AI model ranking markets

### Pattern 8: Geographic/Territorial
**Markets**: "On Iranian soil," "in Ukraine," "capture of [city]"
**Issue**: What counts as the geographic boundary? Do enclaves count?
**UMA tendency**: Common understanding of geographic borders
**Financial impact**: Myrnohrad capture ($1.3M, manipulated via ISW map data)

### Pattern 9: Retroactive Clarification
**Markets**: Trump/China crypto summit, various
**Issue**: Polymarket retroactively changes or "clarifies" resolution criteria after betting has occurred
**UMA tendency**: Follows Polymarket's clarification (Principle 4)
**Financial impact**: Unknown aggregate; creates systemic unpredictability

### Pattern 10: "Suspended" vs. "Dropped Out" / Status Ambiguity
**Markets**: RFK Jr. dropout, political withdrawal markets
**Issue**: Does "suspended campaign" = "dropped out"?
**UMA tendency**: Status quo — "suspended" ≠ "dropped out"
**Financial impact**: $300K+ (RFK Jr. market)

---

## 7. Strategic Synthesis

### The 98.5% / 1.5% Split

- **98.5% of markets** resolve cleanly in ~2 hours via MOOV2. No human edge in this window — bots dominate.
- **1.5% of markets** enter dispute, creating 3-6+ day windows of mispriced uncertainty. This is where human judgment has edge.

### Where Human Edge Exists

1. **Ambiguous geopolitical markets**: Understanding what "invasion" or "strike" means to UMA voters (not to military analysts) creates predictable resolution bias.

2. **Pre-event resolution criteria analysis (S009)**: Reading the fine print BEFORE the event reveals which markets have narrow criteria that might not match common interpretation.

3. **Dispute window trading**: When a market enters dispute, understanding UMA's 5 principles better than the market creates edge. The market prices dispute outcomes based on the event; the smart trade prices based on UMA voting dynamics.

4. **The "known but unresolved" window**: For clear outcomes (elections, Fed), buying at 97-99c during the 2-hour liveness is S011 territory — low edge per trade but high annualized returns if rotated efficiently.

### Where Human Edge Does NOT Exist

- Sub-minute price reactions to news events (bots)
- Fed decisions, sports results, BTC milestones (bots)
- Any strategy requiring speed rather than judgment

---

## Sources

- UMIP-189 (MOOV2 proposal, August 2025)
- UMA Optimistic Oracle documentation
- Polymarket resolution documentation
- Ukraine mineral deal coverage (Yahoo Finance, BeInCrypto, CryptoSlate)
- Israel-Lebanon dispute coverage
- Zelenskyy suit market coverage
- 2024 Presidential election resolution timeline (multiple sources)
- "How Manipulable Are Prediction Markets?" (Augenblick et al. 2025)
- "Oracle Manipulation in Polymarket 2025" (Orochi Network)
- polymarket-structural-mechanics.md (internal research, sections 4-5)
