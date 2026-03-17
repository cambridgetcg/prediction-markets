# D16 — Hungary PM 2026: Institutional Dynamics Research

You are a political analyst building Hungary domain expertise. This is a $21.6M market with a fascinating tension: Peter Magyar's TISZA party is ahead in polls, but Viktor Orbán controls every institutional lever of power — media, courts, electoral infrastructure, civil society.

This prompt builds the GEO/POL research base before we can estimate whether the market (Magyar 57.5%, Orbán 38.5%) is correctly priced.

## Read First

1. `~/Desktop/prediction-markets/domains/POL/active.md` — brief Hungary section
2. `~/Desktop/prediction-markets/domains/GEO/context.md` — geopolitical context framework

## Why This Market is Complex

Unlike most Polymarket markets, Hungary 2026 is NOT just a polling question. It's a question of:
1. Whether the election is free and fair (Orbán has degraded democratic norms)
2. Whether the opposition can coordinate (historically fragmented)
3. Whether institutional barriers can be overcome (media blackout, gerrymandering)

Simply extrapolating polling data gives the wrong answer.

---

## Task 1: Current Political Landscape

### 1a. Peter Magyar and TISZA

```
web_search("Peter Magyar TISZA party Hungary polls 2026")
web_search("Peter Magyar Hungary election 2026 latest")
web_search("TISZA Fidesz Hungary poll February 2026")
```

Key questions:
- What is TISZA's current polling lead? (Latest polls, not just Polymarket's 57.5%)
- Who is Peter Magyar? Background, credibility, weaknesses?
- Has TISZA maintained momentum since the 2024 European Parliament election (where they won 29% vs Fidesz 44%)?
- Is TISZA running alone or in coalition? Have other opposition parties endorsed Magyar?

### 1b. Viktor Orbán and Fidesz

```
web_search("Orban Fidesz polls 2026 Hungary election")
web_search("Hungary 2026 election Orban chances")
web_search("Orban Hungary opposition coalition 2026")
```

Key questions:
- Fidesz controls: ~80% of Hungarian media, Constitutional Court, National Election Commission, gerrymandered districts
- What is Fidesz's current polling vs TISZA?
- Has there been any significant defection from Fidesz coalition parties?
- What is Orbán's approval rating vs Magyar's?

### 1c. Election Date and Process

```
web_search("Hungary 2026 election date parliamentary")
web_search("Hungary election rules 2026 balloting system")
```

- When exactly is the election? (Spring 2026 is "expected" but confirm)
- Is it a parliamentary election (PM chosen by parliament) or direct?
- How does the Hungarian electoral system work? (Single-member constituencies + list seats)
- What percentage of seats does Fidesz currently hold?
- What majority does TISZA need to form government?

---

## Task 2: The Institutional Advantage Framework

This is the most important part. Research each institutional lever:

### 2a. Media Control

Fidesz controls ~80% of Hungarian media through:
- KESMA (Central European Press and Media Foundation) — consolidation of 500+ outlets
- State public media (MTVA)
- Advertising pressure on independent outlets

Key question: Has this coverage advantage ever been overcome? What's the base rate for opposition winning in heavily media-biased environments?

Historical comparison: Look at cases where a heavily media-biased incumbent lost (Slovakia's Fico 2023 is different; Poland's PiS 2023 is relevant):

```
web_search("Poland PiS 2023 election media control opposition win")
web_search("opposition wins despite state media control historical")
```

**Poland 2023 parallel**: PiS controlled state media, gerrymandered districts, filled courts — and still lost when the opposition ran as a united front and turnout surged. Is Magyar following the same playbook?

### 2b. Electoral System Gerrymandering

Hungary uses a mixed system: single-member constituencies (106 seats) + national list (93 seats).

Key question: How favorable is the current district map to Fidesz?
- After 2010 redistricting, Fidesz is estimated to need ~35-40% of the national vote to win a majority
- TISZA needs ~45-50%+ to break through the gerrymander
- If TISZA is polling at 45%+ → gerrymander is surmountable. If at 40% → probably not.

```
web_search("Hungary electoral system gerrymander 2026 analysis")
web_search("TISZA Magyar seat projection 2026 Hungary")
```

### 2c. National Election Commission (NEC)

The NEC is filled with Fidesz loyalists. Powers include:
- Ruling on candidate eligibility
- Interpreting electoral rules
- Certifying results

Realistic risk: NEC finds procedural grounds to disqualify Magyar or TISZA in key constituencies.

```
web_search("Hungary National Election Commission Fidesz bias 2026")
web_search("Magyar TISZA election registration Hungary")
```

Has TISZA faced any NEC challenges already? What's the status?

### 2d. The Civil Society Squeeze

Fidesz has used the "foreign agent" law (copied from Russia) to constrain NGOs. Get-out-the-vote organizations are restricted. This matters because Magyar's path to victory requires:
1. High turnout (historically, high turnout favors opposition)
2. Youth vote activation
3. Rural votes in Fidesz-dominated areas

---

## Task 3: Probability Estimate

### 3a. Build the Probability Tree

```
P(Magyar wins PM) = 
  P(election is reasonably fair) × P(Magyar wins fair election)
  + P(election is unfair/manipulated) × P(Magyar wins despite manipulation)

Where:
  P(election is reasonably fair) = estimate based on NEC/court risk
  P(Magyar wins fair election) = based on polling + Poland parallel
  P(Magyar wins despite manipulation) = based on magnitude of lead needed
```

This is more sophisticated than raw polling. Model it explicitly.

### 3b. Key Variables to Estimate

| Variable | Your Estimate | Key Evidence |
|----------|--------------|-------------|
| Current TISZA polling lead (%) | ? | Latest polls |
| Seat conversion at current lead | ? | Electoral system math |
| P(NEC disqualifies TISZA) | ? | NEC track record |
| P(election fairly contested) | ? | Poland parallel |
| Orban concedes if Magyar wins | ? | Historical: he left office after 2002 |
| P(Magyar wins given fair election) | ? | Polls × seat math |

### 3c. Historical Base Rate

**Important reference**: Orbán LOST the 2002 election when polling showed him behind. He conceded and left office. He came back in 2010. So he's not constitutionally incapable of losing — he's done it before.

The more relevant question is whether he's MORE or LESS willing to accept a loss now (after 16 years of building authoritarian infrastructure).

```
web_search("Orban 2002 election loss Hungary concede")
web_search("Hungary democratic backsliding 2026 election integrity concerns")
```

---

## Task 4: Market Price Assessment

After completing Tasks 1-3, assess the current Polymarket prices:

**Magyar 57.5%**: Is this correct?
- If polls show 50-55% support AND gerrymander requires 45% to win → Magyar wins in a fair election
- If NEC risk and media bias account for the 15pp discount from polling → 57.5% is reasonable
- If institutional barriers are stronger than Poland 2023 parallel suggests → Magyar is overpriced

**Orbán 38.5%**: Is this correct?
- With 16 years of institutional entrenchment, 38.5% seems low for someone who has never truly lost an election on his own terms
- If there's a 20-30% probability of meaningful electoral manipulation → Orbán might be underpriced at 38.5%

**Your verdict**: Is the market:
A. Correctly priced (no edge, don't trade)
B. Magyar overpriced (edge on Orbán NO — sell Magyar)
C. Orbán overpriced (edge on Magyar YES)
D. Too uncertain to trade (more research needed, return for D17)

---

## Task 5: Edge Assessment and Position Recommendation

### If Edge Found:

**If Magyar YES (market 57.5%, estimate >65%)**:
- BUY Magyar YES
- Sizing: $100 (1% bankroll) — modest given complexity
- Strategy: S008 Info Edge
- Log: PT021

**If Orbán YES (market 38.5%, estimate >50%)**:
- BUY Orbán YES
- Sizing: $75 (0.75% bankroll)
- Strategy: S008 Info Edge
- Log: PT021 (either Magyar or Orbán, not both)

**If no clear edge**: Document the research and set price alerts:
- Alert if Magyar drops to 48% → potentially attractive
- Alert if Orbán drops to 30% → potentially underpriced
- Return for D17 with more data (next Hungarian poll release)

### If POL Domain is Already at Cap:

Log the thesis, set price alerts, defer entry until capacity opens.

---

## Output

1. New research file: `domains/POL/research/hungary-pm-2026.md` — comprehensive analysis including polling, institutional factors, probability estimate, Poland parallel
2. Updated `domains/POL/active.md` — expanded Hungary section with full estimates table
3. Position entry (if edge found): PT021 logged in `strategies/paper-trades/trades.jsonl`
4. Terminal output: What's our edge verdict? Magyar vs Orbán pricing assessment? What is the single biggest factor (polling? gerrymander? NEC?) driving our estimate away from the market?

**Done when**: A comprehensive research file exists for Hungary 2026, probability estimate is built using the institutional framework (not just raw polls), and a clear trade/no-trade verdict is reached.

**Note**: If research reveals that the election is scheduled for spring 2026 (within 6 weeks), time-pressure significantly increases. Update the catalyst calendar accordingly.
