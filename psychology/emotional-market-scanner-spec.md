# Emotional Market Scanner — Conceptual Design

*Research date: 2026-02-25*
*Purpose: Design spec for a system that detects emotional premiums in prediction markets in real time*
*Status: Conceptual spec (B04 will implement)*
*Prerequisite: behavioral-foundations.md (B01), news-emotion-price-taxonomy.md (B02)*

---

## 1. System Overview

The Emotional Market Scanner (EMS) automates the pipeline from B01/B02:

```
NEWS INGESTION
    ↓
ECI SCORING (automated)
    ↓
AFFECTED MARKET IDENTIFICATION
    ↓
BASE RATE COMPARISON
    ↓
GAP CALCULATION
    ↓
S004 ALERT (if gap > threshold)
```

### What It Replaces

Currently, our process is:
1. Manually notice a news event
2. Manually check which markets moved
3. Manually score ECI
4. Manually look up base rates
5. Manually calculate the gap
6. Decide to trade (or not)

This takes 30-60 minutes per event. The EMS should reduce step 1-5 to <5 minutes by automating ingestion, scoring, and comparison.

---

## 2. Architecture

### 2.1 Inputs

| Input | Source | Frequency | Purpose |
|-------|--------|-----------|---------|
| **Polymarket price movements** | Gamma API `/markets` | Every 5 minutes | Detect markets that moved ≥8% in 24h or ≥15% in 7d |
| **News headlines** | RSS feeds (Reuters, AP, Al Jazeera, Axios) | Real-time | Classify news events by category (A-E from taxonomy) |
| **Social media volume** | Twitter/X trending topics, Reddit mentions | Every 15 minutes | Measure Media Amplification dimension of ECI |
| **Base rate database** | Local file (`calibration/base-rates.jsonl`) | Static, updated quarterly | Compare market price to historical frequency |
| **Domain context** | Local files (`domains/*/context.md`) | Static | Provide domain-specific context for ECI scoring |

### 2.2 Processing Pipeline

```
┌─────────────────────────────────────────────────────┐
│                    NEWS INGESTION                     │
│  RSS feeds → headline extraction → deduplication      │
│  Output: {headline, source, timestamp, category}      │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│                    ECI SCORING                         │
│  For each news event:                                 │
│  1. Fear Factor (keyword matching + category lookup)  │
│  2. Vividness (media type: text=low, video/image=high)│
│  3. Narrative Coherence (does it fit existing story?) │
│  4. Identity Activation (partisan keyword check)      │
│  5. Recency Shock (delta from 7-day price trend)      │
│  6. Media Amplification (headline count + social vol) │
│  Output: ECI score (1-10) with dimension breakdown    │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│              MARKET IDENTIFICATION                     │
│  Match news event → affected Polymarket markets       │
│  Methods:                                             │
│  - Keyword matching (news headline → market question) │
│  - Domain tagging (GEO news → GEO markets)           │
│  - Price correlation (which markets moved when?)      │
│  Output: list of affected markets + price changes     │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│              BASE RATE COMPARISON                      │
│  For each affected market:                            │
│  - Look up reference class in base-rates.jsonl        │
│  - Calculate implied daily hazard rate                │
│  - Compare to historical frequency                    │
│  - Apply domain-specific adjustment                   │
│  Output: fair_value_estimate, market_price, gap       │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│               ALERT GENERATION                        │
│  IF ECI ≥ 7 AND gap ≥ 8pp:                          │
│    → HIGH PRIORITY S004 ALERT                        │
│  IF ECI 4-6 AND gap ≥ 12pp:                         │
│    → MODERATE PRIORITY — run classification checklist │
│  IF ECI < 4 AND gap ≥ 15pp:                         │
│    → LOW PRIORITY — likely structural, flag for S008  │
│  Output: alert with full context for trade decision   │
└─────────────────────────────────────────────────────┘
```

---

## 3. ECI Automation Rules

### 3.1 Fear Factor (1-10)

| Score | Rule |
|-------|------|
| 1-2 | Routine policy, economic data, corporate news |
| 3-4 | Sanctions, diplomatic tension, regulatory announcement |
| 5-6 | Military deployment, ultimatum, significant escalation |
| 7-8 | Active military operation, confirmed strike, multiple-front escalation |
| 9-10 | Nuclear threat, existential risk, civilian casualties confirmed |

**Keyword scoring**: Military keywords ("strike," "troops," "carriers," "missiles," "nuclear") each add +1. Cap at 10. Diplomatic keywords ("talks," "framework," "deal") each subtract -1. Floor at 1.

### 3.2 Vividness (1-10)

| Score | Rule |
|-------|------|
| 1-3 | Text-only coverage, abstract statistics, diplomatic communiqué |
| 4-6 | Photos (satellite, deployment), named officials |
| 7-8 | Video footage, specific casualty numbers, named weapons systems |
| 9-10 | Live footage, graphic imagery, real-time conflict coverage |

**Automated proxy**: Count of image/video URLs in news articles about the event. More visual coverage → higher vividness.

### 3.3 Narrative Coherence (1-10)

| Score | Rule |
|-------|------|
| 1-3 | Contradicts existing market narrative |
| 4-6 | Neutral or ambiguous — doesn't clearly fit any story |
| 7-8 | Confirms and extends the dominant narrative |
| 9-10 | "The next logical step" in a widely-accepted escalation sequence |

**Automated proxy**: Sentiment alignment with prior 7 days of coverage on the same topic. If new headline matches prior direction, Narrative Coherence is high.

### 3.4 Identity Activation (1-10)

| Score | Rule |
|-------|------|
| 1-3 | Bipartisan/apolitical topic |
| 4-6 | Moderate partisan valence |
| 7-8 | Deep partisan divide, us-vs-them framing |
| 9-10 | Core identity issue (gun rights, abortion, immigration, Trump personality) |

**Keyword scoring**: Partisan keywords ("Democrat," "Republican," "liberal," "conservative," "Trump," "Biden") add +1 each. Issue keywords ("abortion," "gun," "immigration," "climate") add +2 if present.

### 3.5 Recency Shock (1-10)

| Score | Rule |
|-------|------|
| 1-3 | Expected, gradual, already priced in (market moved <3% in prior 7d on this topic) |
| 4-6 | Mildly surprising, modest departure from trend |
| 7-8 | Significantly surprising, sharp departure from 7-day trend |
| 9-10 | Completely unexpected, discontinuous from all prior expectations |

**Automated proxy**: |market_price_change_24h| / average_daily_change_7d. Ratio > 3 = score 7+. Ratio > 5 = score 9+.

### 3.6 Media Amplification (1-10)

| Score | Rule |
|-------|------|
| 1-3 | Below-the-fold, niche coverage, <5 major outlets |
| 4-6 | Moderate coverage, 5-15 major outlets |
| 7-8 | Leading headlines on major networks, 15+ outlets, trending on social media |
| 9-10 | Dominating all news cycles, top trending globally, cable news continuous coverage |

**Automated proxy**: Count of unique major news sources covering the event within 4 hours. Cross-reference with Twitter/X trending topics for social amplification.

---

## 4. Minimum Viable Version (Manual Checklist)

Before building the automated system, we can run a manual version using this checklist whenever a market moves ≥8% in 24h:

### EMS Manual Checklist

```
DATE: ___________
MARKET: ___________________________________________
PRICE MOVE: _____% in _____h

STEP 1: NEWS IDENTIFICATION
What news event caused this move?
_______________________________________________
Category (A1-E5): _____

STEP 2: ECI SCORING
Fear Factor:      ___/10
Vividness:        ___/10
Narrative:        ___/10
Identity:         ___/10
Recency Shock:    ___/10
Media Amp:        ___/10
ECI TOTAL:        ___/10

STEP 3: BASE RATE
Reference class: ___________________________________
Historical frequency: _____%
Source: ____________________________________________

STEP 4: GAP CALCULATION
Market price: _____%
Fair value estimate: _____%
Gap: _____pp

STEP 5: COMPOUND PATTERN CHECK
[ ] War Panic Premium (A1-A4 + ECI > 7)
[ ] Narrative Cascade (D3-D4 or B2-B4 + herding signals)
[ ] Deadline Decay Funnel (A2 + approaching deadline)
[ ] Partisan Echo Chamber (B1-B6 + identity > 7)
[ ] Lottery Ticket Illusion (price < $0.15 + multiple conditions)

STEP 6: DECISION
[ ] HIGH PRIORITY (ECI ≥ 7 AND gap ≥ 8pp) → S004 entry analysis
[ ] MODERATE (ECI 4-6 AND gap ≥ 12pp) → Run S004 classification checklist
[ ] LOW (ECI < 4 OR gap < 8pp) → Skip or flag for S008
[ ] STRUCTURAL (ECI < 4 AND move justified) → Do NOT fade
```

**Time to complete**: ~10 minutes. Compared to 30-60 minutes for the current ad hoc process.

---

## 5. Fully Automated Version — Requirements

### 5.1 Data Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Price feed** | Gamma API polling (every 5 min) | Market price monitoring |
| **News feed** | RSS aggregation (feedparser) | Headline ingestion |
| **Social feed** | Twitter/X API or scraping | Media amplification scoring |
| **Base rate DB** | Local JSONL (calibration/base-rates.jsonl) | Reference class lookup |
| **Discrepancy DB** | Local JSONL (psychology/discrepancy-database.jsonl) | Pattern matching |
| **Alert delivery** | Terminal notification + log file | Signal delivery |

### 5.2 Processing Requirements

- **Latency**: <5 minutes from news event to alert. Not competing with bots on speed — competing on ANALYSIS quality.
- **False positive rate**: <30% of alerts should result in "skip" after manual review. Tune ECI thresholds to minimize noise.
- **Coverage**: Monitor top 50 Polymarket markets by volume. Don't track illiquid markets (volume < $200K).

### 5.3 Key Algorithms

**1. Price spike detection**:
```python
# Pseudocode
for market in active_markets:
    change_24h = abs(market.price - market.price_24h_ago)
    change_7d = abs(market.price - market.price_7d_ago)
    if change_24h >= 0.08 or change_7d >= 0.15:
        trigger_eci_scoring(market)
```

**2. News-market matching**:
```python
# Keyword overlap between news headline and market question
# + domain tag matching
# + temporal correlation (price moved within 4h of news publication)
```

**3. ECI scoring** (semi-automated):
- Fear Factor: keyword lookup table
- Vividness: media type detection
- Narrative Coherence: sentiment comparison with 7-day prior coverage
- Identity Activation: partisan keyword density
- Recency Shock: price delta ratio
- Media Amplification: source count within 4h window

**4. Gap calculation**:
```python
# Look up base rate from reference class
# Calculate implied daily hazard rate from market price
# Compare to historical hazard rate
# Gap = market_implied_probability - base_rate_estimate
```

### 5.4 Output Format

Each alert should contain:

```json
{
  "timestamp": "2026-02-XX",
  "market": "Market question text",
  "market_id": "polymarket_id",
  "price_before": 0.XX,
  "price_after": 0.XX,
  "change_pp": X,
  "news_event": "Headline text",
  "news_category": "A2",
  "eci_score": 7.2,
  "eci_breakdown": {
    "fear": 8, "vividness": 6, "narrative": 9,
    "identity": 5, "recency": 7, "media": 8
  },
  "base_rate": 0.XX,
  "fair_value_estimate": 0.XX,
  "gap_pp": X,
  "compound_pattern": "War Panic Premium",
  "priority": "HIGH",
  "recommended_action": "S004 fade — enter NO within 24-72h",
  "classification_checklist_needed": false
}
```

---

## 6. Phased Implementation

### Phase 1: Manual Checklist (NOW)

- Print the manual checklist from §4
- Run it every time a market moves ≥8% in 24h
- Log results to discrepancy-database.jsonl
- Time investment: ~10 min per event
- Goal: Validate ECI scoring on 10+ events before automating

### Phase 2: Semi-Automated Price Monitor (NEXT)

- Script: polls Gamma API every 5 minutes
- Detects: markets with ≥8% 24h move or ≥15% 7d move
- Output: terminal alert with market details
- Manual: ECI scoring and decision still done by human
- Build on: `scripts/spike-detector.py` (already exists)
- Time investment: ~5 min per event (spike detection automated)

### Phase 3: Automated ECI Scoring (LATER)

- Add: RSS feed ingestion + keyword-based ECI scoring
- Add: Base rate lookup from calibration database
- Add: Gap calculation
- Output: full alert JSON with recommended action
- Manual: only the final trade decision
- Time investment: ~2 min per event (review alert + decide)

### Phase 4: Historical Validation (AFTER 20+ EVENTS)

- Backtest: ECI scores vs. actual reversion outcomes
- Calibrate: ECI thresholds (is ≥7 the right cutoff? Should it be ≥6.5?)
- Validate: H1 (ECI ≥ 7 → S004 opportunity >60% of cases)
- Validate: H2 (ECI correlates with gap magnitude)
- Validate: H3 (Fear Factor most predictive for GEO, Identity for POL)

---

## 7. Known Limitations

### 7.1 What ECI Can't Capture

| Phenomenon | Why ECI Misses It | Workaround |
|-----------|------------------|-----------|
| **Present bias discount** (T006) | Not news-driven — it's a capital-allocation psychology | Separate "structural mispricing" scanner needed |
| **Constitutional impossibility premium** (T002) | Chronic mispricing, not event-driven | Flag manually during domain scans |
| **Insider trading spikes** | Price moves without public news | Add "no identified news event" flag → possible insider activity |
| **Wash trading volume distortions** | Fake volume inflates apparent liquidity | Apply 25% discount to volume metrics (Columbia 2025 estimate) |
| **Cross-market contagion** | A hack in Protocol X moves BTC markets | Add cross-market correlation check |

### 7.2 False Positive Scenarios

| Scenario | Why It's a False Positive | How to Filter |
|---------|--------------------------|---------------|
| Genuine structural repricing | Market moves 10%+ on legitimately informative news | ECI < 4 → classify as structural, skip |
| Resolution-driven moves | Market approaches expiration and price converges to 0 or 100 | Check days-to-resolution; if < 7d, likely structural |
| Thin market noise | Market with $50K volume moves 10% on one trade | Volume filter: require $200K+ total volume |
| Bot-driven microstructure | Arb bots move prices briefly before reverting | Require price change to persist for ≥4h |

### 7.3 ECI Calibration Needs

Based on our current N=20 sample (trades + SOTU):

| ECI Range | Current Threshold | Observed Pattern | Adjustment Needed? |
|-----------|------------------|------------------|-------------------|
| ≥7 | S004 at full size | 1/1 correct (T003) | Too small sample. Need 5+ events. |
| 4-6 | Run classification checklist | 8/10 correct (SOTU batch) | Threshold may be too conservative — 4-6 events also produced large gaps |
| <4 | Skip / structural | 1/1 correct (T004 avoided) | Validated but small sample |

**Critical question**: Should the S004 trigger lower to ECI ≥ 6? The SOTU batch suggests that ECI 4-6 events can have LARGER gaps (up to 52pp) than ECI 7+ events. But the SOTU batch is a special case (purely psychological markets with no fundamental uncertainty). For GEO/CRY markets with genuine fundamental uncertainty, 7+ may remain the correct threshold. Track separately by domain.

---

## 8. Integration Points

| System | Integration |
|--------|------------|
| `scripts/spike-detector.py` | Phase 2: Add API polling and alert generation |
| `strategies/playbooks/S004-contrarian-overreaction.md` | ECI trigger already integrated (B01). Scanner provides automated ECI. |
| `psychology/discrepancy-database.jsonl` | Every scanner alert that leads to a trade is logged here |
| `calibration/resolutions.jsonl` | After resolution, log outcome for calibration |
| `BANKROLL.md` | Sizing rules (3% full, 1.5% half) unchanged — scanner doesn't override sizing |

---

## Sources

- System design informed by all B01 and B02 research.
- Gamma API documentation for data feed specifications.
- Columbia University (2025) wash trading study for volume discount estimation.
- All bias citations from behavioral-foundations.md (B01) §Sources.
