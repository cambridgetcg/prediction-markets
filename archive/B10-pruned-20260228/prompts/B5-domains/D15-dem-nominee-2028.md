# D15 — Democratic Nominee 2028: Deep Dive

You are a political analyst researching the 2028 Democratic presidential nomination. Multiple candidates have identified edges in the existing POL domain analysis (Shapiro +6pp, Beshear +3pp, Kamala Harris +6pp, Mark Kelly +BUY). This prompt builds the deep knowledge base before committing capital to 2.5-year positions.

## Read First

1. `~/Desktop/prediction-markets/domains/POL/active.md` — existing Democratic nominee analysis (required)
2. `~/Desktop/prediction-markets/strategies/BANKROLL.md` — note POL domain cap (already near it after D14)
3. `~/Desktop/prediction-markets/research/tetlock-superforecasting-framework.md` — calibration mindset

## The Stakes

$35.7M liquidity in the Democratic nominee market — the deepest political liquidity pool we track. This means:
1. Serious money is already on this. Smart traders have done the research.
2. Edges that exist must be sustained by information asymmetry or systematic market bias.
3. 2.5-year duration = high uncertainty. Size small.

---

## Task 1: Current Market Landscape

Fetch current prices (may have moved substantially since Feb 23):

```
web_search("Polymarket 2028 Democratic presidential nominee odds February 2026")
web_search("Polymarket Josh Shapiro president 2028")
web_search("Polymarket Andy Beshear 2028 president odds")
web_search("Polymarket Kamala Harris 2028 presidential prediction")
web_search("Polymarket Mark Kelly 2028 president odds")
web_search("Cory Booker 2028 presidential announcement")
```

Build updated price table:

| Candidate | Market Price (Feb 23) | Current Price | Δ | My Estimate | Edge |
|-----------|----------------------|---------------|---|-------------|------|
| Gavin Newsom | 28-30% | ? | ? | 18-22% | SELL ~8pp |
| AOC | 9.5% | ? | ? | 8-11% | HOLD |
| Kamala Harris | 8% | ? | ? | 12-18% | BUY ~6pp |
| Josh Shapiro | 6% | ? | ? | 10-15% | BUY ~6pp |
| Pete Buttigieg | 4.6% | ? | ? | 6-8% | BUY ~2pp |
| Andy Beshear | 4.2% | ? | ? | 6-10% | BUY ~3pp |
| JB Pritzker | 4% | ? | ? | 4-6% | HOLD |
| Gretchen Whitmer | 3.4% | ? | ? | 2-4% | SELL |
| Wes Moore | 2.6% | ? | ? | <1% | SELL |
| Mark Kelly | low | ? | ? | 4-7% | BUY |
| Jon Ossoff | low | ? | ? | 2-4% | WATCH |
| Cory Booker | rising | ? | ? | 3-5% | WATCH |

---

## Task 2: The Core Unknowns

Before estimating probabilities, you need to answer three structural questions:

### 2a. Will Gavin Newsom Run?

Newsom at 28-30% is based on assumption he RUNS. If he's not the candidate, that probability collapses.

```
web_search("Gavin Newsom 2028 presidential campaign announcement")
web_search("Gavin Newsom 2028 president definitely running")
```

Key factors:
- He's been preparing since 2024 (national TV appearances, "Fighting Chance" newsletter, France trip)
- California record will define him in general election (homelessness, crime, wildfires, $1M homes)
- Democrats who've seen Newsom nationally are often less impressed than CA watchers
- His strongest path: early Dem primary consolidation before negative ads hit

**Verdict needed**: Is he definitely running (no ifs), probably running, or uncertain?

If definitely running: his 28-30% may be JUSTIFIED — he has massive fundraising advantage and early structural leads.
If uncertain: his price embeds both "he runs and wins primary" and "he runs and wins general" — both need to be true. That's not 28-30%.

### 2b. The Electability Question in 2028

2028 is special: Dems are running as challengers against an incumbent Republican party. Historically:
- The more "electable" candidate wins Dem primaries when they're out of power (Obama 2008, Biden 2020)
- The most progressive candidate tends to win when Dems are in power (didn't quite happen in 2024, but the base matters more in primaries)

In 2028, the electability frame DOMINATES. The 2024 loss will be the defining issue.

**Electability ranking** (based on general election polls, swing state performance, and attack ad vulnerability):

1. **Josh Shapiro**: PA governor (most important swing state), 60%+ approval, "boring but trustworthy," Jewish (attack-resistant). Has built the strongest actual infrastructure.
2. **Andy Beshear**: Won 3× in Kentucky (Trump+26). The most purely "electability" candidate. Has the DGA chair platform. Little national name recognition — but that's solvable.
3. **Mark Kelly**: AZ senator, astronaut, husband of gun violence survivor Gabby Giffords, $33M raised. Swing state credential. But AZ is getting less swinging.
4. **Pete Buttigieg**: Leads New Hampshire polling. Exceptional communicator. Lost South Bend by 30pp in 2024 cycle. Younger, less experience.
5. **Kamala Harris**: Prior nominee, 39% in some polls, 90% Dem favorability. But she just lost to Trump — the "she tried and failed" narrative is the primary attack.
6. **Gavin Newsom**: Best fundraiser, worst general election resume. Every Republican TV ad writes itself ("California: where $1M won't buy a house and the homeless own the streets").

### 2c. The Kamala Question

Is Kamala Harris likely to run? This is probably the single biggest binary in the entire field.

```
web_search("Kamala Harris 2028 presidential run announcement")
web_search("Kamala Harris 2028 campaign team")
```

If she runs:
- She consolidates the Black vote (crucial in SC primary)
- She has the organizational infrastructure
- She has a 40%+ floor in early primary polls
- BUT: the 2024 loss is an enormous liability in a general

If she doesn't run:
- Harris voters disperse, mostly to Shapiro/Beshear/Kelly (electability-minded)
- AOC gets some progressive votes
- The race is genuinely open

**Assessment**: The market at 8% for Harris suggests she probably doesn't run (or runs and loses). At 12-18%, we think she's underpriced. But this hinges entirely on her running decision.

**Key signal to watch**: Does she hire campaign staff? Does she file exploratory committee? These are the only reliable leading indicators.

---

## Task 3: Historical Base Rate Analysis

### 3a. Primary Governor Base Rate

Recent Democratic nominees from Governor positions:
- Bill Clinton (AR Gov) → 1992 nominee
- Michael Dukakis (MA Gov) → 1988 nominee
- Jimmy Carter (GA Gov) → 1976 nominee

How many sitting governors won the Democratic nomination in the modern era? Research:

```
web_search("Democratic presidential nominees governors historical 1976 2024")
```

Governor advantage in Dem primaries:
- Governors run on record, not just rhetoric (harder to caricature as "just a Senator")
- Executive experience argument
- BUT: no national profile unless governor of large/important state

Shapiro (PA) and Beshear (KY) are in different buckets: PA is a swing state; KY is a ruby-red state where winning as a Democrat is proof of electability but provides no electoral college padding.

### 3b. VP Nomination Base Rate (Republican vs Democrat)

In the Republican analysis, VP base rate was ~80% for GOP nomination. What about Democrats?

Historical Democratic sitting VP nominees: Al Gore (2000), Walter Mondale (1984), Hubert Humphrey (1968). All three won the primary. But:
- Gore, Mondale, Humphrey all benefited from incumbency advantage
- Harris has the OPPOSITE dynamic — running as the VP of an administration that lost

**Revised Harris base rate**: Standard VP base rate (~80%) doesn't apply. She's a losing VP candidate, not an incumbent VP. Appropriate comparison: Geraldine Ferraro, Paul Ryan, Sarah Palin — all lost.

---

## Task 4: Build Position Thesis

For each of our 4 target candidates, build a one-paragraph thesis:

### Shapiro (BUY at ~6%)

**Why underpriced**: Governing PA, the most important swing state in the union. 60%+ approval. Won a close race in 2022. Excellent communicator without being polarizing. Democrats need Pennsylvania to win. Having the PA governor as the nominee is a structural advantage. 6% for this candidate is too cheap — the market has not yet converged on his electability case.

**Why the market is skeptical**: No national profile. Jewish (some segments of the Democratic coalition have strained views on Israel/Gaza). "Boring" doesn't generate primary enthusiasm. He's not a culture war combatant.

**Edge verdict**: At 6%, YES. At 10%+, HOLD. The edge closes if Shapiro enters the market more visibly.

### Beshear (BUY at 4.2%)

**Why underpriced**: The single best electability argument in the field. Three wins in a state Trump won by 26. DGA chair = organizational infrastructure. Makes the "can a Democrat win in red America?" case that the party desperately needs after 2024. Almost unknown nationally — but name recognition is the one solvable problem.

**Why the market is skeptical**: Who? Beshear has almost no national name recognition. He's not yet declared. Kentucky winning ≠ Ohio or Pennsylvania winning.

**Edge verdict**: At 4.2%, YES. His upside is capped (can't get above 20%) but his floor is probably higher than 4%. The edge is in the probability of him even entering the top tier.

### Kamala Harris (BUY at 8%)

**Why underpriced**: She has 39% in some early polls, 90% favorable among Dems, $20M in unused donor relationships, and a team already assembled. The incumbent-Vice-President-lost precedent overstates her weakness. If she runs, 8% for the candidate with the highest primary-season floor in the field seems too low.

**Why the market is skeptical**: She just lost. Decisively. To Trump. Twice (2020 VP race / 2024 presidential). The market is pricing in "she probably doesn't run or she runs and faces a Mondale-like campaign."

**Key binary**: Does she run? If yes → probably 20-30% probability of nomination. If no → 0%. At 8%, the market implies P(run) × P(win|run) ≈ 8%. If P(run) = 40% and P(win|run) = 20% = 8%. That seems right if she's a coin flip to run. If P(run) > 50%, the market is mispriced.

### Mark Kelly (BUY at ~2%)

**Why underpriced**: Astronaut, gun violence narrative (Gabby Giffords), AZ senator (swing-state adjacent), $33M raised and "seriously considering." Not yet on most people's radar but has a very clean brand and no skeletons. The "authentic American hero" framing is extremely durable.

**Why the market is skeptical**: AZ is trending red. He barely won re-election in 2022. Less policy depth than Shapiro. Less executive experience.

**Edge verdict**: At 2%, small lottery-ticket position justified. His ceiling is maybe 15-20% probability if everything clicks, making 2% clearly underpriced on EV.

---

## Task 5: Position Sizing + Entry Decision

### 5a. POL Domain Cap Check

From D14, POL domain is likely at or near $1,000 cap (10% of bankroll). Check current POL exposure:

```
[Load from pnl-summary.md after D14 executions]
```

If POL is already at cap → **DEFER all D15 positions until POL exposure drops** (post-resolution of PT002 or PT006).

If capacity remains:
- Maximum D15 allocation: whatever remains under $1,000 total POL cap

### 5b. Position Plan (if capacity exists)

Given the 2.5-year duration and genuine uncertainty, use minimum sizing:

| Position | Size | Priority | Entry Condition |
|----------|------|---------|-----------------|
| Shapiro YES | $75 | 1 | Enter if POL under 9.5% |
| Beshear YES | $50 | 2 | Enter if POL under 10% |
| Kelly YES | $25 | 3 | Lottery ticket — enter any time |
| Harris YES | $50 | 4 | ONLY IF she announces campaign team |

Total max: $200 across all four = 2% of bankroll.

Log as PT017 (Shapiro), PT018 (Beshear), PT019 (Kelly), PT020 (Harris if applicable).

### 5c. The Newsom SELL

We estimate Newsom at 18-22%, market at 28-30% = 8pp sell opportunity.

**BUT**: Selling Newsom requires buying NO, which costs ~72¢ per share and returns $1.00 if he loses. At $300 investment: $300/0.72 × $1.00 = $416.67 if right. That's a 39% return, but on a 2.5-year hold.

**Timing issue**: With 2.5 years until the primary, Newsom NO is not a good S006 (time decay) play. The time decay works AGAINST a NO position at 72¢ — there's no decay benefit when the resolution is 30 months away.

**Decision**: Hold the Newsom SELL analysis but DO NOT enter now. Wait for Q4 2026 when primary season approaches and time decay becomes meaningful.

---

## Output

1. Updated `domains/POL/active.md` — new Democratic nominee table with current prices and updated estimates
2. New research file: `domains/POL/research/dem-nominee-2028.md` — full candidate analysis, base rates, the Kamala binary
3. Position entries (if POL cap allows): PT017-PT020 logged in `strategies/paper-trades/trades.jsonl`
4. Updated `strategies/paper-trades/pnl-summary.md`
5. Terminal output: What is current POL domain exposure? Which Dem positions could we enter? Updated market prices for all major Dem candidates?

**Done when**: A dedicated research file exists for the Democratic nominee race, prices are updated, POL cap is checked, and any available positions are entered with rationale. The Newsom SELL thesis is documented but deferred.

**Key watchlist items to add to HEARTBEAT.md**:
- Kamala Harris campaign team/exploratory filing
- Josh Shapiro national events / endorsement announcements
- Cory Booker continuation of 25-hour filibuster momentum
- Mark Kelly official campaign announcement
