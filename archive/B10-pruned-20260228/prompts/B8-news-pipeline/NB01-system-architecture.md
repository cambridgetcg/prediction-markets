# NB01: System Architecture & Tech Stack Decision
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Context
You are designing a fully automated news intelligence pipeline for a prediction markets trader.
The pipeline uses the **Brave Search News API** as its primary ingestion source.

**Core architectural insight:**
Running the same query with different `country` parameters returns region-specific news coverage.
This gives us geographic perspective diversity natively — no scraping, no GDELT, no extra infrastructure.

```
query="Iran nuclear talks" + country=US  → American media perspective
query="Iran nuclear talks" + country=GB  → British media perspective
query="Iran nuclear talks" + country=RU  → Russian media perspective
query="Iran nuclear talks" + country=IR  → Iranian media perspective
query="Iran nuclear talks" + country=QA  → Gulf/Al Jazeera perspective
query="Iran nuclear talks" + country=CN  → Chinese media perspective
```

Same event. Six perspectives. One API call per country. ~$0.03 total.

## Brave News API Reference
```
GET https://api.search.brave.com/res/v1/news/search
Headers: X-Subscription-Token: {BRAVE_API_KEY}

Key parameters:
  q             Query string (supports boolean: AND, OR, NOT, quotes, site:)
  count         Results per request (max 50, default 20)
  offset        Pagination (0-based, max 9)
  country       2-letter country code (US, GB, RU, IR, CN, QA, DE, FR, IL, SA...)
  search_lang   Language filter (en, ar, ru, zh, fa, fr...)
  freshness     pd (24h) | pw (7d) | pm (31d) | py (1y) | YYYY-MM-DDtoYYYY-MM-DD
  extra_snippets true → up to 5 additional excerpts per article (more context)

Returns per article: title, url, description, age, source.name, source.url, extra_snippets[]
```

**Rate/cost:** $5 per 1,000 requests. Free $5/month credit = 1,000 free requests/month.
A 6-country poll on 1 query = 6 requests. 10 queries × 6 countries × 4 polls/hour = 240 req/hour.
At scale this costs ~$1.20/hour. Design for efficiency.

## Existing System Context
- **B03**: Live Sentiment Signal — news → market signals
- **B05**: Source Bias Adjustment — credibility matrix
- **R01**: Correlation risk rules C1-C4
- **R04**: Fast Resolution Pipeline
- Calibration: Brier 0.230 vs market 0.349 | NO: 7/7 ✓ | YES: 2/5 ✗

## Your Task
Produce a complete Architecture Decision Record (ADR):

1. **Data Flow Diagram** (ASCII):
   ```
   Config (queries × country_clusters)
        ↓
   BravePoller (parallel country requests)
        ↓
   Article dedup + storage
        ↓
   ToneEntityExtractor (LLM or VADER/spaCy)
        ↓
   PerspectiveTagger (domain bias lookup)
        ↓
   EventClusterer (entity+date overlap)
        ↓
   DivergenceDetector (tone split across country clusters)
        ↓  [only divergent clusters]
   TruthExtractor (LLM synthesis)
        ↓
   SignalGenerator (Polymarket match + Kelly)
        ↓
   Delivery (Telegram via OpenClaw)
   ```

2. **Tech stack decisions** (commit, don't suggest):
   - Language/runtime
   - Database (SQLite recommended for portability — justify or override)
   - Async vs sync (parallel country requests benefit from async)
   - LLM for truth extraction (model choice + why)
   - Tone scoring approach (LLM-based since Brave doesn't provide tone — or VADER/TextBlob?)

3. **Country cluster config** — define the perspective groups:
   - Which countries map to which perspective cluster?
   - Minimum viable set (cost-efficient) vs full coverage
   - How to handle countries with no results for a query?

4. **Request budget** — given 1,000 free requests/month:
   - How many queries? How many countries per query? What poll interval?
   - Design the budget allocation explicitly.

5. **What Brave provides vs what we compute**:
   - Brave gives: title, url, description, source name, age, extra_snippets
   - We must compute: tone score, named entities, event cluster membership
   - Decision: LLM for entity+tone extraction, or lightweight NLP library?

6. **Pipeline stages** with input/output contracts

7. **State management**: what persists, how long, schema overview

## Output
Structured markdown ADR. All decisions explicit with rationale. No hedging.
