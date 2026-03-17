# NB01 Output: Architecture Decision Record
# News Intelligence Pipeline — Brave API Edition
# Date: 2026-02-27

---

## 1. Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  config.yaml                                                      │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ queries[]        │  │ country_clusters  │  │ schedule       │  │
│  │  .text           │  │  Western: [US,GB] │  │  interval: 4h  │  │
│  │  .domain         │  │  Russian: [RU]    │  │  freshness: pd │  │
│  │  .freshness      │  │  Chinese: [CN]    │  │  budget: 900   │  │
│  │  .countries[]    │  │  Iranian: [IR]    │  │                │  │
│  └─────────────────┘  │  Gulf: [QA]       │  └────────────────┘  │
│                        │  Israeli: [IL]    │                      │
│                        └──────────────────┘                      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 1: BravePoller                                            │
│  asyncio + httpx — parallel country requests per query           │
│  Rate: ≤1 req/100ms (10/sec), budget counter per run             │
│  Input:  query × country pairs from config                       │
│  Output: list[RawArticle] with country_queried tag               │
│  Dedup:  SHA256(url) against seen_urls in SQLite                 │
└──────────────────────────────┬───────────────────────────────────┘
                               │ new articles only
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 2: ArticleStore                                           │
│  SQLite INSERT — articles table                                  │
│  Columns: url_hash, url, title, description, snippets,           │
│           source_name, source_domain, country_queried,           │
│           age_raw, age_parsed_utc, query_text, domain,           │
│           fetched_at, processed (bool)                           │
└──────────────────────────────┬───────────────────────────────────┘
                               │ batch of unprocessed articles
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 3: ToneEntityExtractor                                    │
│  VADER (tone: -1.0 to +1.0) + spaCy (entities: GPE, ORG, PER)  │
│  Input:  full_text = title + description + extra_snippets        │
│  Output: tone_score, entities[], key_claims[] (regex heuristic)  │
│  Writes: article_analysis table in SQLite                        │
│  Cost:   $0 (local NLP, no API calls)                            │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 4: PerspectiveTagger                                      │
│  Lookup source_domain against credibility-matrix.json (B05)      │
│  Map country_queried → cluster name (Western/Russian/etc.)       │
│  Input:  article + analysis                                      │
│  Output: cluster, credibility_score, bias_direction,             │
│          compound_weight (credibility × citation_level)           │
│  Writes: perspective column in article_analysis                   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 5: EventClusterer                                         │
│  Group articles by shared entities + date proximity (48h window) │
│  Jaccard similarity on entity sets, threshold ≥ 0.3              │
│  Input:  all unassigned articles with entities                   │
│  Output: event_clusters table (cluster_id, articles[], created,  │
│          domain, key_entities[], avg_tone_by_cluster)             │
│  Expiry: clusters with no new articles for 72h → archived        │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 6: DivergenceDetector                                     │
│  Per event cluster: compute avg tone per country_cluster         │
│  Divergence = max(cluster_tones) - min(cluster_tones)            │
│  Input:  event_clusters with ≥2 country_clusters represented     │
│  Output: divergence_score, cluster_tone_map, is_divergent (bool) │
│  Gate:   divergence ≥ 0.8 OR ≥2 clusters with opposing sign     │
│  Pass:   → Stage 7 (TruthExtractor)                             │
│  Fail:   → log as "consensus" event, skip to Stage 8 check      │
└──────────────────────────────┬───────────────────────────────────┘
                               │ divergent clusters only
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 7: TruthExtractor                                         │
│  Claude Sonnet 4.6 — structured prompt with all cluster articles │
│  Input:  event cluster + articles grouped by perspective         │
│  Prompt: "Given these N articles from M perspectives on [event], │
│           extract: (1) objective facts all sources agree on,     │
│           (2) claims that diverge by perspective, (3) what each  │
│           side omits, (4) your probability estimate for [market] │
│           (5) confidence 0-1"                                    │
│  Output: truth_kernel, divergent_claims[], omissions[],          │
│          probability_estimate, confidence, reasoning             │
│  Cost:   ~$0.01-0.03 per extraction (Sonnet, ~2K input tokens)  │
│  Writes: truth_extractions table in SQLite                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 8: SignalGenerator                                        │
│  Match truth extraction → active Polymarket markets              │
│  Apply: B05 credibility weighting, YES discount (0.85),          │
│         R01 correlation check, Kelly sizing (quarter-Kelly)      │
│  Input:  truth_extraction + positions.json + market data         │
│  Output: signal (market, direction, edge, size, strategy,        │
│          truth_kernel, perspective_split, confidence)             │
│  Gates:  edge ≥ 5pp, confidence ≥ 0.6, R01 pass,               │
│          pending_signals < 3                                     │
│  Writes: signals table in SQLite + signals.jsonl                 │
└──────────────────────────────┬───────────────────────────────────┘
                               │ signals that pass all gates
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  Stage 9: Delivery                                               │
│  Format signal → Telegram message via OpenClaw announce mode     │
│  Message format:                                                 │
│    SIGNAL — {market_question}                                    │
│    Direction: YES/NO | Edge: +X.X% | Confidence: X%             │
│    Size: $XXX (Kelly X.XX) | Strategy: SXXX                     │
│    Truth kernel: {objective_kernel}                              │
│    Perspective split: Western +1.2 | Russian -4.3 | ...         │
│    Divergence: X.X | Sources: N articles, M countries            │
│  Writes: delivery_log table in SQLite                            │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Tech Stack Decisions

### Language: Python 3.10+

**Committed.** Every existing script in the observatory is Python. The news-calibrator, spike-detector, overround-scanner, temporal-checker — all Python. The credibility-matrix.json consumer is Python. No runtime ambiguity.

### Database: SQLite

**Committed.** Rationale:
- Single-file portable database. No daemon. `cp pipeline.db backup.db` is the backup strategy.
- Existing project has zero external database dependencies. Every data store is JSON/JSONL files. SQLite is one step up — structured queries, dedup via UNIQUE constraints, expiry via DELETE WHERE — without introducing infrastructure.
- WAL mode for concurrent reads during long poll cycles.
- At our scale (hundreds of articles/day, not millions), SQLite is not the bottleneck. The Brave API rate limit is.
- Schema migrations via a `schema_version` pragma and inline SQL in the main script. No ORM.

### Async: asyncio + httpx

**Committed.** A single poll cycle fires 6 country requests per query. With 10 queries that's 60 requests. Sequential at 100ms each = 6 seconds. Async with connection pooling = ~1 second. httpx is the async-native HTTP client — requests doesn't support async. The poller is the only async component; downstream stages run synchronously on batches.

### LLM: Claude Sonnet 4.6 for truth extraction

**Committed.** Rationale:
- Truth extraction is the only stage that requires LLM. It runs only on divergent clusters (maybe 20-30% of events). Cost: ~$0.01-0.03 per extraction at Sonnet pricing.
- Sonnet is fast enough for a 4-hour poll cycle (not real-time). Opus would cost 5× more with marginal quality gain for structured extraction tasks.
- The existing news-calibrator already uses the Anthropic Python SDK. Same dependency.
- Structured output via system prompt specifying JSON schema. No function calling needed.

### Tone Scoring: VADER (primary) + spaCy en_core_web_sm (entities)

**Committed.** Rationale:
- VADER is free, fast, works on English news headlines without fine-tuning. Compound score -1.0 to +1.0 maps directly to our tone axis.
- spaCy `en_core_web_sm` extracts GPE (countries), ORG (organizations), PERSON entities — exactly what we need for event clustering.
- LLM-based tone scoring would cost ~$0.003 per article × 200 articles/day = $0.60/day = $18/month. VADER costs $0.
- The divergence detector doesn't need perfect tone — it needs consistent tone so that cross-cluster deltas are meaningful. VADER's biases are systematic and cancel out in delta computation.
- Key claims extraction: regex heuristics on sentence structure ("X said", "according to", "announced", "denied") — good enough for clustering. LLM only enters at Stage 7 for synthesis.

**Dependency install:** `pip3 install vaderSentiment spacy httpx anthropic && python3 -m spacy download en_core_web_sm`

---

## 3. Country Cluster Configuration

### Cluster Definitions

```yaml
country_clusters:
  Western:
    countries: [US, GB]
    search_lang: en
    role: "Baseline perspective. Largest English-language news volume."

  Russian:
    countries: [RU]
    search_lang: en    # English-language Russian outlets (RT, TASS English)
    role: "Counter-narrative on GEO/sanctions/military. Inverse signal."

  Chinese:
    countries: [CN]
    search_lang: en    # English-language Chinese outlets (CGTN, Xinhua English)
    role: "Counter-narrative on TEC/trade/Taiwan. Belt & Road lens."

  Iranian:
    countries: [IR]
    search_lang: en    # PressTV, Tehran Times English
    role: "Direct party perspective on Iran/nuclear markets."

  Gulf:
    countries: [QA]
    search_lang: en    # Al Jazeera English dominates QA results
    role: "Regional mediator perspective. Strong on GEO/energy."

  Israeli:
    countries: [IL]
    search_lang: en    # Times of Israel, Haaretz English, i24
    role: "Direct party perspective on Iran/Palestine markets."
```

### Minimum Viable Set (budget-optimized)

**4 clusters, 4 countries:** US, GB, RU, QA = 4 requests per query.

This captures the primary axis of divergence for GEO-heavy markets (Western vs. Russian vs. Gulf). GB provides Commonwealth/European angle distinct from US.

**Full set:** US, GB, RU, CN, IR, QA, IL = 7 requests per query.

Use full set for GEO queries (Iran, Russia-Ukraine, China-Taiwan). Use minimum set for ECO/TEC/POL queries where non-Western perspectives add less signal.

### No-Results Handling

When a country returns 0 results for a query:
1. Log it (the absence is itself a signal — a country's media not covering a topic tells you something).
2. Do NOT retry with different parameters — that wastes budget.
3. Exclude that cluster from divergence calculation for this event (require ≥2 clusters with results to compute divergence).
4. After 5 consecutive empty polls for a country×query pair, demote it from that query's country list until manual review.

---

## 4. Request Budget

### Budget: 1,000 free requests/month (with $5 credit)

Reserve 100 requests (10%) as buffer for ad-hoc manual queries and debugging. **Usable budget: 900 requests/month.**

### Allocation

```
Tier 1: Active Position Queries (highest priority)
  Queries matching held positions or watchlist
  Estimated: 5 queries × 4 countries × 2 polls/day × 30 days = 1,200 req/month
  → TOO EXPENSIVE at full coverage

Revised plan — staggered polling:

  HOT queries (active positions):     5 queries × 4 countries × 1 poll/day = 600 req/month
  WARM queries (watchlist/calendar):  3 queries × 4 countries × 3 polls/week = 144 req/month
  COLD queries (domain scanning):     3 queries × 2 countries × 2 polls/week =  48 req/month
  BURST (breaking news, manual):      reserved buffer                        = 108 req/month
                                                                      TOTAL =  900 req/month
```

### Implementation

```yaml
budget:
  monthly_limit: 900          # hard cap, script refuses after this
  daily_soft_limit: 35        # warn if exceeded (900/30 = 30, + burst headroom)
  burst_reserve: 108          # held back for manual/breaking-news triggers
  counter_file: data/brave-api-usage.json  # {month: "2026-02", used: 412, by_query: {...}}

poll_schedule:
  hot:                        # Positions + near-term catalysts
    interval_hours: 24
    countries: [US, GB, RU, QA]
    freshness: pd             # last 24 hours
  warm:                       # Watchlist + calendar events within 14 days
    interval_hours: 56        # ~3x/week
    countries: [US, GB, RU, QA]
    freshness: pd
  cold:                       # Domain scan for new edges
    interval_hours: 84        # ~2x/week
    countries: [US, GB]
    freshness: pw             # last 7 days (wider net)
```

### Cost at Scale (if free tier exceeded)

At $5/1,000 requests: 900 requests = $4.50/month. Even doubling to 1,800 requests = $9.00/month. The Brave API is not the cost bottleneck — Claude API calls for truth extraction are (~$0.03 × 5 divergent clusters/day × 30 = $4.50/month). Total pipeline cost at full load: **~$15/month.**

---

## 5. What Brave Provides vs. What We Compute

### Brave Returns (per article)

| Field | Type | Notes |
|-------|------|-------|
| `title` | string | Headline — high signal for tone |
| `url` | string | Dedupe key (SHA256) |
| `description` | string | 1-2 sentence summary — main text for NLP |
| `age` | string | "9 hours ago", "2 days ago" — must parse |
| `source.name` | string | "Reuters", "RT" — B05 credibility lookup key |
| `source.url` | string | Domain extraction for bias mapping |
| `extra_snippets[]` | string[] | Up to 5 additional excerpts (with `extra_snippets=true`) |

**Brave does NOT provide:** full article text, tone/sentiment, named entities, event categorization, topic tags, credibility ratings, or any analytical metadata.

### We Compute

| Computed Field | Method | Cost |
|----------------|--------|------|
| `full_text` | Concatenate title + description + extra_snippets | Free |
| `age_parsed_utc` | Regex parse "N hours/days ago" → datetime | Free |
| `source_domain` | Extract domain from source.url | Free |
| `tone_score` | VADER compound on full_text (-1.0 to +1.0) | Free |
| `entities[]` | spaCy NER on full_text (GPE, ORG, PERSON) | Free |
| `key_claims[]` | Regex: sentences containing "said", "announced", "denied", "according to" | Free |
| `cluster` | Country cluster lookup from config | Free |
| `credibility` | source_domain → credibility-matrix.json B05 lookup | Free |
| `bias_direction` | source_domain → credibility-matrix.json B05 lookup | Free |
| `event_cluster_id` | Jaccard similarity on entity sets + date overlap | Free |
| `divergence_score` | max-min of avg tone across country clusters per event | Free |
| `truth_kernel` | Claude Sonnet synthesis of divergent cluster | ~$0.02/event |
| `probability_est` | Claude Sonnet structured output | (same call) |
| `signal` | Edge calc + Kelly + R01 check + strategy routing | Free |

**LLM cost is gated:** only divergent clusters (divergence ≥ 0.8) trigger Claude. Consensus events (most events) never call the LLM. Expected: 3-8 LLM calls per daily poll cycle = $0.06-0.24/day.

---

## 6. Pipeline Stages — Input/Output Contracts

### Stage 1: BravePoller

```python
@dataclass
class RawArticle:
    url: str
    title: str
    description: str
    extra_snippets: list[str]
    source_name: str
    source_url: str
    age_raw: str                # "9 hours ago"
    country_queried: str        # "US"
    query_text: str             # "Iran nuclear talks"
    query_domain: str           # "GEO"
    fetched_at: str             # ISO 8601

# Input:  config.yaml (queries × countries)
# Output: list[RawArticle]
# Side:   increments data/brave-api-usage.json counter
```

### Stage 2: ArticleStore

```python
# Input:  list[RawArticle]
# Output: list[RawArticle]  (only NEW articles, deduped by url_hash)
# Side:   INSERT INTO articles table, skip existing url_hash (UNIQUE constraint)
# Dedup:  SHA256(url) — same article from different country queries stored once,
#         but country_queried stored in article_countries junction table
```

### Stage 3: ToneEntityExtractor

```python
@dataclass
class ArticleAnalysis:
    url_hash: str
    tone_score: float          # VADER compound: -1.0 to +1.0
    entities: list[str]        # ["Iran", "IAEA", "Biden"] — deduplicated
    entity_types: dict         # {"Iran": "GPE", "IAEA": "ORG"}
    key_claims: list[str]      # Extracted sentences with attribution
    full_text: str             # title + description + snippets (for downstream)

# Input:  list[RawArticle] (new articles from Stage 2)
# Output: list[ArticleAnalysis]
# Side:   INSERT INTO article_analysis table
```

### Stage 4: PerspectiveTagger

```python
@dataclass
class TaggedArticle:
    url_hash: str
    cluster_name: str          # "Western", "Russian", etc.
    credibility_score: float   # 0.0-5.0 from credibility-matrix.json
    bias_direction: str        # "pro-Western", "pro-Russian", etc.
    compound_weight: float     # credibility × citation_level_weight

# Input:  ArticleAnalysis + source_domain + country_queried
# Output: TaggedArticle (appended to analysis)
# Side:   UPDATE article_analysis SET cluster, credibility, bias
# Lookup: sources/credibility-matrix.json (B05)
#         Unknown sources default to credibility=2.5, bias="unknown"
```

### Stage 5: EventClusterer

```python
@dataclass
class EventCluster:
    cluster_id: str            # UUID
    domain: str                # "GEO", "POL", etc.
    key_entities: list[str]    # Union of entities across member articles
    article_hashes: list[str]  # Member article url_hashes
    created_at: str            # ISO 8601
    last_updated: str          # ISO 8601
    article_count: int
    countries_represented: list[str]

# Input:  list[ArticleAnalysis] + existing EventClusters
# Output: list[EventCluster] (new or updated)
# Side:   UPSERT event_clusters table
# Logic:  Jaccard(entity_sets) ≥ 0.3 → same cluster
#         Articles older than 48h vs cluster start → new cluster
#         Clusters with no new articles for 72h → status='archived'
```

### Stage 6: DivergenceDetector

```python
@dataclass
class DivergenceReport:
    cluster_id: str
    cluster_tones: dict        # {"Western": 0.3, "Russian": -0.7, "Gulf": -0.2}
    divergence_score: float    # max - min of cluster_tones
    is_divergent: bool         # score ≥ 0.8 OR opposing signs in ≥2 clusters
    article_count_by_cluster: dict  # {"Western": 8, "Russian": 3}

# Input:  EventCluster with ≥2 country_clusters represented
# Output: DivergenceReport
# Side:   UPDATE event_clusters SET divergence_score, is_divergent
# Gate:   Only clusters where is_divergent=True proceed to Stage 7
```

### Stage 7: TruthExtractor

```python
@dataclass
class TruthExtraction:
    cluster_id: str
    truth_kernel: str          # What all sources agree on
    divergent_claims: list[dict]  # [{claim, clusters_supporting, clusters_denying}]
    omissions: list[dict]      # [{what_omitted, which_cluster_omits}]
    probability_estimate: float  # 0.0-1.0
    confidence: float          # 0.0-1.0
    reasoning: str             # Chain of thought
    model_used: str            # "claude-sonnet-4-6"
    input_article_count: int
    input_token_count: int
    cost_usd: float

# Input:  DivergenceReport + all member articles grouped by cluster
# Output: TruthExtraction
# Side:   INSERT INTO truth_extractions table
# LLM:    Claude Sonnet 4.6 via Anthropic SDK, structured JSON output
```

### Stage 8: SignalGenerator

```python
@dataclass
class Signal:
    signal_id: str             # UUID
    market_question: str       # Matched Polymarket question
    market_token_id: str       # CLOB token ID
    direction: str             # "YES" or "NO"
    our_estimate: float        # From TruthExtraction.probability_estimate
    market_price: float        # Current Polymarket price
    edge: float                # our_estimate - market_price (adjusted)
    yes_discount_applied: bool # True if YES direction (0.85 factor)
    kelly_fraction: float      # Quarter-Kelly sizing
    suggested_size_usd: float
    strategy: str              # "S004", "S006", etc.
    r01_pass: bool             # Correlation check passed
    truth_kernel: str
    perspective_split: dict    # {"Western": 0.3, "Russian": -0.7}
    divergence_score: float
    source_count: int
    country_count: int
    confidence: float
    created_at: str

# Input:  TruthExtraction + positions.json + Polymarket API (market prices)
# Output: Signal (or None if gates fail)
# Gates:  edge ≥ 0.05, confidence ≥ 0.6, r01_pass=True, pending_signals < 3
# Side:   INSERT INTO signals table + APPEND to data/signals.jsonl
```

### Stage 9: Delivery

```python
# Input:  Signal
# Output: Formatted Telegram message (string)
# Side:   Send via OpenClaw announce mode
#         INSERT INTO delivery_log table
# Format: See data flow diagram above
```

---

## 7. State Management

### SQLite Schema Overview

**Database file:** `data/news-pipeline.db`

```sql
-- Schema version tracking
PRAGMA user_version = 1;

-- Stage 2: Raw article storage
CREATE TABLE articles (
    url_hash     TEXT PRIMARY KEY,        -- SHA256(url)
    url          TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT,
    extra_snippets TEXT,                  -- JSON array
    source_name  TEXT,
    source_domain TEXT,
    age_raw      TEXT,
    age_parsed   TEXT,                    -- ISO 8601 UTC
    query_text   TEXT,
    domain       TEXT,                    -- GEO, POL, ECO...
    fetched_at   TEXT NOT NULL,           -- ISO 8601 UTC
    processed    INTEGER DEFAULT 0        -- 0=pending, 1=analyzed
);

-- Junction: same article found via multiple country queries
CREATE TABLE article_countries (
    url_hash     TEXT REFERENCES articles(url_hash),
    country      TEXT NOT NULL,           -- US, GB, RU...
    PRIMARY KEY (url_hash, country)
);

-- Stage 3-4: NLP analysis + perspective tags
CREATE TABLE article_analysis (
    url_hash         TEXT PRIMARY KEY REFERENCES articles(url_hash),
    tone_score       REAL,                -- VADER: -1.0 to +1.0
    entities         TEXT,                -- JSON array
    entity_types     TEXT,                -- JSON dict
    key_claims       TEXT,                -- JSON array
    cluster_name     TEXT,                -- Western, Russian, etc.
    credibility      REAL,                -- 0.0-5.0
    bias_direction   TEXT,
    compound_weight  REAL,
    analyzed_at      TEXT                 -- ISO 8601 UTC
);

-- Stage 5: Event clusters
CREATE TABLE event_clusters (
    cluster_id       TEXT PRIMARY KEY,    -- UUID
    domain           TEXT,
    key_entities     TEXT,                -- JSON array
    created_at       TEXT,
    last_updated     TEXT,
    article_count    INTEGER DEFAULT 0,
    countries_repr   TEXT,                -- JSON array
    divergence_score REAL,
    is_divergent     INTEGER DEFAULT 0,
    status           TEXT DEFAULT 'active'  -- active | archived
);

-- Junction: articles → event clusters
CREATE TABLE cluster_articles (
    cluster_id   TEXT REFERENCES event_clusters(cluster_id),
    url_hash     TEXT REFERENCES articles(url_hash),
    PRIMARY KEY (cluster_id, url_hash)
);

-- Stage 7: LLM truth extractions
CREATE TABLE truth_extractions (
    extraction_id    TEXT PRIMARY KEY,    -- UUID
    cluster_id       TEXT REFERENCES event_clusters(cluster_id),
    truth_kernel     TEXT,
    divergent_claims TEXT,                -- JSON array
    omissions        TEXT,                -- JSON array
    probability_est  REAL,
    confidence       REAL,
    reasoning        TEXT,
    model_used       TEXT,
    input_articles   INTEGER,
    input_tokens     INTEGER,
    cost_usd         REAL,
    extracted_at     TEXT
);

-- Stage 8: Generated signals
CREATE TABLE signals (
    signal_id        TEXT PRIMARY KEY,
    cluster_id       TEXT REFERENCES event_clusters(cluster_id),
    extraction_id    TEXT REFERENCES truth_extractions(extraction_id),
    market_question  TEXT,
    market_token_id  TEXT,
    direction        TEXT,                -- YES | NO
    our_estimate     REAL,
    market_price     REAL,
    edge             REAL,
    kelly_fraction   REAL,
    suggested_size   REAL,
    strategy         TEXT,
    r01_pass         INTEGER,
    confidence       REAL,
    status           TEXT DEFAULT 'pending',  -- pending | approved | rejected | expired
    created_at       TEXT,
    delivered_at     TEXT
);

-- Stage 9: Delivery log
CREATE TABLE delivery_log (
    delivery_id  TEXT PRIMARY KEY,
    signal_id    TEXT REFERENCES signals(signal_id),
    channel      TEXT,                    -- telegram
    message      TEXT,
    sent_at      TEXT,
    ack_received TEXT                     -- user response: A/R/I
);

-- Budget tracking (alternative to JSON file)
CREATE TABLE api_usage (
    date         TEXT,                    -- YYYY-MM-DD
    query_text   TEXT,
    country      TEXT,
    requests     INTEGER DEFAULT 1,
    PRIMARY KEY (date, query_text, country)
);

-- Indexes
CREATE INDEX idx_articles_domain ON articles(domain);
CREATE INDEX idx_articles_processed ON articles(processed);
CREATE INDEX idx_articles_fetched ON articles(fetched_at);
CREATE INDEX idx_analysis_cluster ON article_analysis(cluster_name);
CREATE INDEX idx_clusters_status ON event_clusters(status);
CREATE INDEX idx_clusters_divergent ON event_clusters(is_divergent);
CREATE INDEX idx_signals_status ON signals(status);
```

### Retention Policy

| Table | Retention | Rationale |
|-------|-----------|-----------|
| articles | 90 days | Source material for backtesting |
| article_analysis | 90 days | Tied to articles |
| event_clusters | 30 days active, then archived | Archived clusters kept 90 days for calibration |
| truth_extractions | Permanent | Core intellectual output, calibration data |
| signals | Permanent | Trade decision audit trail |
| delivery_log | Permanent | Delivery audit trail |
| api_usage | Permanent | Budget tracking |

Cleanup job: `DELETE FROM articles WHERE fetched_at < date('now', '-90 days')` — runs weekly.

### Config File

**Location:** `config/news-pipeline.yaml`

```yaml
brave_api:
  base_url: "https://api.search.brave.com/res/v1/news/search"
  key_env_var: "BRAVE_API_KEY"        # reads from environment
  extra_snippets: true
  default_count: 20
  rate_limit_ms: 100                  # min 100ms between requests

queries:
  - text: "Iran nuclear"
    domain: GEO
    tier: hot
    countries: [US, GB, RU, QA, IR, IL]    # full set for GEO
  - text: "Russia Ukraine"
    domain: GEO
    tier: hot
    countries: [US, GB, RU, QA]
  - text: "Trump tariffs trade"
    domain: ECO
    tier: warm
    countries: [US, GB, CN, QA]
  - text: "Federal Reserve interest rates"
    domain: ECO
    tier: warm
    countries: [US, GB]
  - text: "AI regulation"
    domain: TEC
    tier: cold
    countries: [US, GB]
  # ... additional queries added/removed based on active positions

country_clusters:
  Western:  [US, GB]
  Russian:  [RU]
  Chinese:  [CN]
  Iranian:  [IR]
  Gulf:     [QA]
  Israeli:  [IL]

divergence:
  min_clusters: 2                     # need ≥2 clusters to compute
  threshold: 0.8                      # VADER divergence score
  opposing_sign_trigger: true         # also trigger if ≥2 clusters have opposing tone sign

truth_extraction:
  model: "claude-sonnet-4-6"
  max_input_articles: 30              # cap to control token count
  temperature: 0.2                    # low for factual extraction
  yes_discount: 0.85                  # calibration: YES overestimated

signal_generation:
  min_edge: 0.05                      # 5 percentage points
  min_confidence: 0.6
  max_pending: 3
  kelly_fraction: 0.25                # quarter-Kelly
  strategy_routing:
    GEO: [S004, S006]
    POL: [S001, S007]
    ECO: [S003, S006]
    TEC: [S006]
    CRY: [S006, S007]

budget:
  monthly_limit: 900
  daily_soft_limit: 35
  burst_reserve: 108
  usage_file: "data/brave-api-usage.json"

database:
  path: "data/news-pipeline.db"
  wal_mode: true
  retention_days: 90

delivery:
  mode: "openclaw-announce"           # uses existing OpenClaw Telegram integration
  channel: "prediction-markets"
```

---

## Decision Log

| # | Decision | Alternatives Considered | Rationale |
|---|----------|------------------------|-----------|
| D1 | Python 3.10+ | Node.js, Go | All existing scripts are Python. Zero context-switching cost. |
| D2 | SQLite with WAL | PostgreSQL, JSON files | Portable, zero-config, sufficient at our scale. JSON files (current approach) don't support efficient dedup or querying. Postgres would require a daemon. |
| D3 | asyncio + httpx | requests (sync), aiohttp | httpx is async-native with sync fallback. aiohttp works but httpx has cleaner API and is the modern choice. requests can't do async. |
| D4 | VADER + spaCy | LLM-only, TextBlob, transformers | Free, fast, deterministic. LLM tone scoring wastes money on non-divergent articles. TextBlob is less accurate on news text. Transformers models are overkill and slow. |
| D5 | Claude Sonnet 4.6 | Claude Opus, GPT-4o, local LLM | Sonnet is 5× cheaper than Opus with sufficient quality for structured extraction. Already have Anthropic SDK. Local LLMs can't match quality on geopolitical reasoning. |
| D6 | Divergence gating | LLM on all events | Most events show consensus across perspectives. Running LLM on consensus events wastes money and produces no actionable signal. Gate at divergence ≥ 0.8 to focus spend. |
| D7 | 4-country minimum set | 2-country, 7-country | 2 countries (US+GB) misses the adversarial perspectives that create divergence signals. 7 countries exceeds budget on warm/cold queries. 4 (US, GB, RU, QA) captures the primary axes at sustainable cost. |
| D8 | 900 req/month budget | 500, 1500 | 500 forces too-infrequent polling (miss breaking news). 1500 exceeds free tier. 900 leaves 10% buffer within free $5 credit. |
| D9 | Single script, stage functions | Microservices, Celery | We're one person running this on a laptop. No need for message queues, containers, or distributed workers. One `main()` that calls stages sequentially, with the poller stage using async internally. |
| D10 | OpenClaw delivery | Direct Telegram bot, email | OpenClaw is already configured with Telegram announce mode and cron scheduling. Zero new infrastructure. |
