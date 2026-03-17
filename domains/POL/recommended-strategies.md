# POL — Recommended Strategies

*Politics offers the deepest liquidity and the richest structural arb surface.*

## Why POL Matters

- **Highest liquidity** of any domain ($2.4B on 2024 election). Positions can be sized meaningfully.
- **Multi-outcome markets** (nomination fields) create structural mispricing. Candidate probabilities should sum to ~100% but often don't.
- **Sophisticated participants** make calibration edge harder — but behavioral biases (partisan reasoning, debate gaffe panic) still create patterned inefficiencies.
- **Richest catalyst calendar**: primaries, debates, conventions, elections, appointments — all on schedule.
- **2024 evidence**: Cross-platform price divergences, negative daily autocorrelation (overreaction-correction cycles), arbitrage peaking near resolution.

## Strategy Priority (ordered)

### 1. S007 Cross-Market Arb — **PRIMARY** (Score: 5/5)

Multi-outcome nomination markets are the best arb terrain across all domains.

**Why it works here**: Republican 2028 field (Vance 41%, etc.) and Democratic 2028 field (wide open) — both should sum to ~100%. In practice they often sum to 103-110%, creating overround arbs. Buy NO on the most overpriced candidates.

**How to deploy**:
- Daily: sum all YES prices on multi-outcome political markets
- If sum > 103% → overround arb exists
- Identify the most overpriced NO (the candidate most unlikely relative to their price)
- Also check: temporal consistency between related deadline markets ("by midterms" vs "by 2028")

**Watch for**: Resolution criteria (does "nominee" mean declared candidate, delegate count, or convention vote?).

### 2. S003 News Catalyst — **PRIMARY** (Score: 5/5)

Politics has the most predictable and consequential catalyst calendar of any domain.

**Why it works here**: Debates, primaries, conventions, election days, confirmation hearings, appointment announcements — all scheduled. The uncertainty premium compresses as catalysts approach, and outcome asymmetry is often misunderstood.

**How to deploy**:
- Build a political catalyst calendar (next 6 months)
- For each upcoming catalyst: assess which markets it affects
- Enter 3-7 days before catalyst
- Direction: research + polling data + historical analogue → which outcome is underpriced?
- Exit: on catalyst day (evaluate), or hold 48h post if thesis confirmed but not fully priced

**Key catalysts**: FOMC appointments, 2026 midterms, 2028 primary debates, state-level races.

### 3. S005 Momentum — **SECONDARY** (Score: 4/5)

Political primaries are the textbook momentum environment.

**Why it works here**: "Big Mo" — candidates who win early primaries gain narrative momentum that the market slowly prices. Polling trends create persistent directional moves over weeks. Tetlock's research shows slow Bayesian updating in political forecasts.

**How to deploy**:
- Trigger: candidate moves 10%+ over 7+ days on multiple supporting events (poll win + endorsement + fundraising)
- Enter on 3-5% pullback within the trend
- Trailing 15% stop
- Exit if trend exhaustion signals appear (volume declining, price >85%)

**Watch for**: Primary momentum is real but can reverse violently (Dean Scream, debate disasters). S005 and S004 are in natural tension here.

### 4. S004 Contrarian Overreaction — **SECONDARY** (Score: 4/5)

Partisan motivated reasoning creates reliable overreaction.

**Why it works here**: After debates, political gaffes, scandal breaks — partisans overreact in both directions. The market spikes on emotional energy, then reverts as polling data (which moves slowly) reasserts fundamentals.

**How to deploy**:
- Trigger: 15%+ move in 24-48h on political event
- Is this debate performance, gaffe, or scandal? (Emotional → fade)
- Or election result, law passed, court ruling? (Structural → don't fade)
- Enter 24-48h after spike, target 50% retracement, 14-day limit

**Watch for**: Distinguishing real narrative shifts from noise. 2016 showed that "fundamentals" don't always reassert.

### 5. S008 Information Edge — **FOUNDATIONAL** (Score: 4/5)

Polling internals, demographic modeling, and historical analogues provide real edge.

**Why it works here**: Most market participants follow headline polling. Few dig into cross-tabs, likely voter screens, state-level demographics, or historical analogues from similar political environments. Type A (synthesis) and Type B (base rate) edges are both available.

**How to deploy**:
- For each active political market: research polling methodology, historical analogues
- Build probability estimate from fundamentals (economy, approval ratings, demographics) BEFORE checking market
- If divergence ≥10%, document edge type and enter
- Cumulative: build `POL/research/` as ongoing resource

## Strategies to Skip in POL

- **S006 Time Decay (3/5)**: Fewer "by date" structures than GEO. When they exist, professional participants price them efficiently.
- **S002 Threshold (3/5)**: Moderate volatility doesn't trigger thresholds as reliably as GEO/CRY. Fine as overlay but not primary.
- **S001 Hold (3/5)**: Sophisticated competition. Use as benchmark only.

## Current Opportunities (as of 2026-02-23)

- **Republican 2028 Nominee**: Vance at 41%. Multi-outcome market — check overround (S007).
- **Democratic 2028 field**: Completely open. No frontrunner >single digits. Watch for momentum signals (S005) as the field develops.
- **Fed Chair (Warsh at 94%)**: Near-certain. S001/S002 as high-probability bond, but reward is thin.
- **2026 midterms**: Building catalyst calendar now.
