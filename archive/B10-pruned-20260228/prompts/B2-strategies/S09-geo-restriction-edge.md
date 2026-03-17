You are a political analyst formalizing the geo-restriction information edge as strategy S014. You've been practicing this informally — now it becomes a repeatable playbook.

## The Core Thesis

33+ countries are blocked from Polymarket (France, Belgium, Poland, Italy, Netherlands, UK, Portugal, etc.). Markets on events in those countries are priced by NON-LOCAL traders who lack local knowledge. This creates a structural information asymmetry that persists as long as the geo-restrictions exist.

**Evidence:**
- Portugal presidential election (Jan 2026): $5M surged in hours before results. Odds jumped 60% → 95% as exit polls circulated locally — proving local information was dramatically more valuable.
- Theo ($85M): French trader with private polling methodology crushed US election markets — cross-cultural information edge.
- Academic: Baik, Kang & Kim: local investors have measurable edge, especially on high-asymmetry securities.
- Our own European politics research (`domains/POL/research/europe-2026.md`) already identified this: "European political markets are priced primarily by non-European traders."

## Read First

1. ~/Desktop/prediction-markets/strategies/evolution/new-strategy-research.md — S014 section
2. ~/Desktop/prediction-markets/domains/POL/research/europe-2026.md (if exists)
3. ~/Desktop/prediction-markets/psychology/participant-profiles.md — POL domain profile
4. ~/Desktop/prediction-markets/research/what-doesnt-work.md — Section 6.1 (profit models — domain specialization)
5. ~/Desktop/prediction-markets/strategies/playbooks/S008-information-edge.md — the base strategy S014 extends

---

## Task 1: Map the Geo-Restriction Landscape

### 1a. Blocked Countries Inventory

Research which countries are blocked from Polymarket as of Feb 2026:
- Web search: "Polymarket blocked countries list 2026"
- Web search: "Polymarket geo restrictions banned countries"
- Which European countries have active prediction markets on Polymarket?
- Are any blocked countries lifting restrictions? (CFTC approval was Nov 2025 for US — has anything changed for Europe?)

Create a table:

| Country | Blocked? | Active Markets on Polymarket | Local Info Value | Priority |
|---------|----------|---------------------------|-----------------|----------|
| France | Yes | 2027 presidential, EU policy | Very High | 1 |
| UK | Yes | PM succession, elections | High | 2 |
| Germany | Yes | Coalition, elections | High | 3 |
| Italy | Yes | Political instability | Medium | 4 |
| Hungary | ? | PM Orban markets | Medium | 5 |
| Portugal | Yes | Elections, EU | Medium | 6 |
| etc. | | | | |

### 1b. Market Inventory

For each blocked country with active Polymarket markets:
- Fetch from Gamma API: `/events?limit=100&closed=false&order=volume`
- Filter client-side for country-specific events
- Record: question, current price, volume, resolution date
- Flag high-volume markets (>$100K) as primary targets

---

## Task 2: Local Information Sources

### 2a. Source Mapping

For each priority country, identify information sources that:
1. Are NOT typically consumed by US/crypto-native Polymarket traders
2. Provide earlier or more granular information than English-language media
3. Are publicly accessible (no paywalls that would block us too)

| Country | Source Type | Examples | Language | Edge Window |
|---------|-----------|---------|----------|-------------|
| France | Polling | IFOP, Ipsos France, BVA | French | 12-48h before English coverage |
| France | Political analysis | Le Monde, Les Echos editorial | French | Same-day nuance lost in translation |
| UK | Polling | YouGov, Savanta, JL Partners | English | Near-zero (same language) |
| UK | Political analysis | Political Betting, UK Polling Report | English | Moderate (specialist knowledge) |
| Germany | Polling | Infratest dimap, Forschungsgruppe Wahlen | German | 24-48h before English coverage |
| etc. | | | | |

### 2b. Language Advantage Assessment

Key question: can we actually access non-English sources?
- Can LLMs (Claude, GPT-4) read and summarize French/German/Portuguese political analysis?
- Is the information advantage primarily linguistic or contextual?
- For English-speaking blocked countries (UK, Ireland, Australia), the edge is contextual not linguistic

This directly affects which countries we can actually exploit vs. just theorize about.

---

## Task 3: Strategy Formalization

### 3a. Write the S014 Playbook

Write: `~/Desktop/prediction-markets/strategies/playbooks/S014-geo-restriction.md`

Structure:
- **Phase**: NIGREDO (research phase)
- **Edge hypothesis**: Geo-restricted users = blind market
- **Entry rules**:
  1. Market is about an event in a geo-restricted country
  2. Our estimate is informed by local sources (not just English-language media)
  3. Edge > 5pp between our locally-informed estimate and market price
  4. Volume > $100K (sufficient liquidity to trade)
  5. Resolution within 6 months (capital efficiency)
- **Exit rules**: Per underlying strategy (S001/S003/S008 depending on market type)
- **Sizing**: Standard 3-5% bankroll. Size up to 6% if local source is polling data (not just media).
- **Integration**: S014 is S008 (information edge) specialized for European/non-US markets

### 3b. Domain-Strategy Matrix Update

Update the strategy-domain matrix to include S014:

| Domain | S014 Applicability | Notes |
|--------|-------------------|-------|
| POL | HIGH (European elections) | Primary terrain |
| GEO | MEDIUM (European conflict, sanctions) | Where GEO meets European politics |
| LAW | MEDIUM (EU regulation, ECJ rulings) | Regulatory timelines |
| ECO | LOW (ECB policy is globally priced) | Same info worldwide |
| TEC | LOW (tech is global) | No geographic information advantage |

---

## Task 4: Upcoming Opportunities

### 4a. French 2027 Presidential Election

The biggest S014 opportunity on the horizon:
- Web search: "Polymarket French presidential election 2027"
- Web search: "France 2027 election polls candidates"
- Who are the candidates? What are the current polling numbers?
- Is there already a Polymarket market? If so, what's the current pricing?
- What local French sources would give us edge?

### 4b. UK PM Succession

- Web search: "Polymarket UK Prime Minister next"
- Web search: "UK next general election prediction market 2026"
- Starmer's approval ratings, opposition dynamics
- Is there a succession market or only general election timing?

### 4c. Hungarian / Italian / German Markets

Scan for any active Polymarket markets on:
- Hungarian elections or Orban-related events
- Italian coalition or PM markets
- German coalition or Scholz/successor markets
- Any EU-level institutional markets (ECB president, EU Commission)

---

## Task 5: The Translation Pipeline

### 5a. LLM-Assisted Local Research

Design a workflow for using LLMs to process non-English sources:

```
1. Identify relevant polling/analysis in local language
2. Fetch the source (WebFetch or manual)
3. Query Claude/GPT-4: "Summarize this French political analysis.
   Focus on: candidate viability, coalition dynamics, polling methodology,
   any information NOT typically reported in English-language media."
4. Compare LLM summary against current Polymarket pricing
5. If edge > 5pp, enter via S014 rules
```

Test this workflow on one current European market (if any exist).

### 5b. S012 Integration

S014 + S012 (LLM Ensemble Screener) create a compound edge:
- S012 screens hundreds of markets including European ones
- S014 filters to markets where geo-restriction creates information asymmetry
- LLMs process local-language sources that most Polymarket traders can't read
- Human makes final entry decision

Design how S012 output feeds into S014 evaluation.

---

## Output

1. `strategies/playbooks/S014-geo-restriction.md` — full strategy playbook
2. Updated `strategies/evolution/strategy-domain-matrix.md` — add S014 row
3. `domains/POL/research/european-elections-2026-2027.md` — current European political landscape
4. Terminal output: inventory of active European-related markets on Polymarket with pricing
5. Assessment: which specific markets have >5pp edge from geo-restriction information asymmetry?

**Done when**: S014 playbook is written, at least one European market has been evaluated with locally-informed probability estimate, and the geo-restriction advantage has been quantified (or shown to be smaller than hypothesized).
