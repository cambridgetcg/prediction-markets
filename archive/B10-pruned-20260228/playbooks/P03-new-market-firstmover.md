# P03 — New Market First-Mover

**Phase**: ALBEDO (research complete, detector built, ready for paper trading)
**Type**: Structural / Speed + Domain Knowledge
**Edge hypothesis**: New Polymarket markets launch with uninformative prices (anchored at $0.50 or round numbers) and undergo a predictable discovery window before sophisticated participants reprice them. Traders with existing domain research can exploit this window.
**Evidence**: 52.7% of new sub-markets launch at ~50%, vs 1.1% of mature (>$50K) markets. The $0.50 anchor is the single most common initial price. Discovery window = hours to days.

## Why This Exists

Every Polymarket market starts with a first price. That price is set by:
1. The Polymarket markets team (centralized curation — users cannot create markets directly)
2. Early market makers posting limit orders (pure CLOB since AMM deprecation)
3. The $0.50 default anchor when no informed trader has arrived

The person setting the initial price often has **no special information** about the true probability. They anchor on round numbers ($0.50 default), recent sentiment, or adjacent market prices without adjusting for structural differences.

## Market Creation Mechanics

### Who Creates Markets
- **Polymarket's internal markets team** creates all markets (centralized)
- Users propose via Discord `#market-suggestion` or Twitter @polymarket
- No permissionless creation (despite historical "Gamma system" references)

### How Initial Prices Form
- No default starting price — CLOB starts empty (zero shares)
- Price forms when market maker YES bid + NO bid = $1.00 → mint + match
- Displayed probability = midpoint of best bid-ask spread
- **Automated series** (crypto up/down, sports) get pre-seeded at specific prices
- **Manual prediction markets** start empty → first limit orders set the price

### The Anchoring Evidence (30-Day Analysis, N=7,932 sub-markets)

| Metric | Value | Implication |
|--------|-------|-------------|
| Markets at ~50% (48-52%) | 52.7% | Massive $0.50 anchor |
| Low-volume (<$5K) at ~50% | 55.3% | Discovery window = default prices |
| High-volume (>$50K) at ~50% | 1.1% | Informed traders reprice |
| Prices at round 5% increments | 60.8% | Round number anchoring |
| Most common initial price | 50% | 4,367 out of 7,932 sub-markets |

**Key finding**: The gap between low-volume (55.3% at 50%) and high-volume (1.1% at 50%) proves the discovery window hypothesis. New markets are uninformative; mature markets are repriced.

## The Edge

Our competitive advantage is **existing domain research** that lets us evaluate a new market within minutes, while the broader market takes hours to days.

### Domain Readiness Map

| Domain | Research Depth | First-Mover Ready | Evaluation Time | Key Edge Source |
|--------|---------------|-------------------|-----------------|-----------------|
| **TEC** | Deep (19K words) | 9/10 | 5-15 min | Arena.ai leaderboard, model calendars |
| **GEO** | Deep (Iran, Venezuela) | 9/10 | 5-15 min | Force posture, escalation ladder, base rates |
| **POL** | Good (2028, Europe, SOTU) | 8/10 | 10-20 min | Electoral math, base rates, catalyst calendar |
| **ECO** | Good (Fed policy, tariffs) | 8/10 | 10-20 min | CME FedWatch baseline, data pipeline |
| **LAW** | Good (SCOTUS, crypto reg) | 7/10 | 15-30 min | Legal timeline, regulatory direction |
| **CRY** | Good (cycles, on-chain) | 7/10 | 15-30 min | Macro correlation, sentiment extremes |
| ENV | Basic | 3/10 | 60+ min | No edge |
| SCI | Minimal | 2/10 | 60+ min | No edge |

### Spin-Off Market Opportunity

New markets often launch as follow-ons to existing hot markets:
- "Iran strikes by March 31" → "Iran strikes by April 30"
- "Who leads Venezuela EOY 2026?" → "Maduro leader by June 30?"

These spin-offs anchor to parent market prices without adjusting for:
- **Time value** (longer horizon = different probability)
- **New information** (what happened since parent opened?)
- **Conditional structure** (April market ≠ March market + 30 days)

When our temporal checker (S007) flags a temporal inconsistency at launch, that's a first-mover signal.

## Rules

### Qualifying Markets
1. Created within last 12 hours (manually: check 2x/day; automated: detector script)
2. In a domain with deep research (GEO/POL/ECO/TEC/LAW)
3. Our existing knowledge gives a confident estimate (±10pp or better)
4. Initial price is >8pp from our estimate
5. Volume <$10K (still in discovery window)

### Entry Trigger
All 5 qualifying criteria must be YES:

```
1. New market detected (detector or manual scan)? → YES
2. Strong research domain (GEO/POL/ECO/TEC/LAW)?  → YES
3. Confident estimate available (±10pp)?            → YES
4. |market_price - our_estimate| > 8pp?             → YES
5. Total volume < $10K?                             → YES
→→→ ENTER immediately
```

### Sizing Rules (Conservative)

| Volume Tier | Max Position | Rationale |
|-------------|-------------|-----------|
| Discovery (<$5K) | $50 | Highest uncertainty, resolution criteria untested |
| Early ($5-10K) | $75 | Price still forming, some discovery complete |
| Forming ($10-50K) | $125 | Moderate repricing underway |
| Mature (>$50K) | Standard (3-5% bankroll) | Discovery window closed, normal rules |

Reason for smaller sizing: new markets have higher resolution ambiguity risk (criteria not yet stress-tested) and higher probability we're missing information the creator had.

### Detection Protocol

**Manual (current)**:
- Morning check (8am UTC): `python3 scripts/new-market-detector.py --hours 720` (12h lookback)
- Afternoon check (2pm UTC): `python3 scripts/new-market-detector.py --hours 360` (6h)
- After major news: `python3 scripts/new-market-detector.py --hours 60` (1h)

**Screening tool**: `scripts/new-market-detector.py`

### Exit
- Standard exit per underlying strategy (S001 hold-to-resolution, S002 threshold, etc.)
- If volume grows past $50K and price moves to match our estimate: take profit
- If volume grows past $50K and price moves AGAINST us: reassess — the informed market may know something

## Anti-Patterns (When NOT to Enter)

### Red Flags — You Are the Uninformed Party

| Red Flag | What It Means | Action |
|----------|---------------|--------|
| Volume jumps to $50K+ on day 1 | Sophisticated whales already in | SKIP — discovery window closed |
| First trades are $10K+ | Informed large entry | SKIP — you're late |
| Created after non-public briefing | Creator may have insider info | SKIP — information asymmetry against you |
| Market at 50% but event is genuinely uncertain | Market is correctly priced | SKIP — no edge exists |
| Liquidity-seeded $0.50 | Bet-both-sides mechanism, not a price signal | Check CLOB depth before entering |
| Automated series (crypto up/down, earnings) | Pre-seeded, no anchoring edge | SKIP — different mechanism |

### The Speed vs. Accuracy Tension

- **Speed** wins the discovery window (enter before correction)
- **Accuracy** wins the calibration (don't enter bad trades)
- **Resolution**: Only enter domains where you have EXISTING research. Never enter a new domain cold.

## Market Creation Type Breakdown

### Type 1: Manual Prediction Markets (Primary Target)
- Created by Polymarket team, start empty on CLOB
- Price forms from first market maker limit orders
- Discovery window: 1-24 hours
- **This is where P03 edge lives**

### Type 2: Automated Series (Low Priority)
- Crypto up/down, sports, earnings beat markets
- Pre-seeded at specific prices by automated systems
- Discovery window: minutes (already seeded)
- **Not a first-mover target** — different pricing mechanism

### Type 3: Spin-Off Markets (High Value)
- Follow-on to existing hot event (new timeframe or condition)
- Anchored to parent market without adjustment
- Discovery window: 2-8 hours
- **Highest-value first-mover target** — our domain research directly applies

## 30-Day Opportunity Size

Analysis of 1,338 new events over 30 days:

| Metric | Count |
|--------|-------|
| Total new events | 1,338 |
| In strong domains (GEO/POL/ECO/TEC/LAW) | ~80 (excluding sports false positives) |
| In discovery window (<$10K volume) | ~65 |
| Strong domain + discovery (first-mover targets) | ~45-50 |
| After excluding automated series | ~15-25 real targets |

**Estimated monthly opportunity**: 15-25 genuine first-mover targets across our strong domains. At 2-3 viable entries per month (after filtering for edge > 8pp), sizing at $50-125 per trade, this adds ~$100-375/month in deployed capital with structural edge.

The opportunity is **small in absolute dollars but high in edge quality** — the anchoring evidence (55% at 50% for low-volume vs 1.1% for high-volume) proves systematic mispricing exists.

## Integration with Other Strategies

| Strategy | P03 Integration |
|----------|----------------|
| S006 (Time Decay) | New "by date" markets in GEO/POL are prime P03 targets |
| S007 (Cross-Market Arb) | Temporal checker flags spin-off market inconsistencies at launch |
| S008 (Information Edge) | Domain research enables instant evaluation |
| S004 (Contrarian) | New markets after news spikes = combined S004 + P03 signal |
| S011 (High-Prob Bond) | New markets that quickly move to >95% = bond rotation entry |

## Catalysts That Create Markets

Markets are created in response to news. Monitoring these increases detection speed:

| Catalyst Type | Example | Response Time |
|---------------|---------|---------------|
| Breaking news | Iran negotiations collapse | Markets created within 1-4 hours |
| Scheduled events | FOMC meeting, election day | Markets created 1-7 days before |
| Viral moments | SOTU mentions, celebrity events | Markets created within 2-12 hours |
| Spin-offs | Existing hot market expires → new deadline | Markets created within 1-3 days |

**Priority**: After major GEO/POL/ECO news, run detector with 1-hour lookback immediately.
