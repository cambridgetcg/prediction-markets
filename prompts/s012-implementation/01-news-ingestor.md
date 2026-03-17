# Module 1: News Ingestor (Revived)

## Task

Revive and simplify the archived `brave_ingestor.py` into `scripts/s012/news_ingestor.py`.

## Context

The original `brave_ingestor.py` lives in `archive/B10-pruned-20260228/scripts/brave_ingestor.py`.
It was a comprehensive news ingestion system using Brave Search API with:
- Multi-country polling
- SQLite deduplication
- API budget tracking
- Article parsing with age detection

The original was overbuilt for the S012 use case. We need a **stripped-down version** focused on:
1. Speed (detect breaking news fast)
2. Breaking news detection (cluster detection within a time window)
3. Event classification (which domain? which markets might this affect?)

## Requirements

### Input
- Config from `config/news-pipeline.yaml` (queries, intervals, API limits)
- BRAVE_API_KEY from environment

### Output
- `NewsEvent` dataclass containing:
  ```python
  @dataclass
  class NewsEvent:
      event_id: str              # SHA256 of normalized key entities + date
      articles: list[Article]    # Deduplicated articles about this event
      key_entities: list[str]    # People, places, orgs mentioned
      summary: str               # One-line summary of the event
      domain: str                # GEO, POL, CRY, ECO, TEC, ENV, OTHER
      is_breaking: bool          # True if ≥3 sources within 30 min
      first_seen: datetime
      source_count: int          # Number of independent sources
      query_names: list[str]     # Which configured queries matched
  ```

### Behavior

1. **Polling**: Fetch news via Brave Search API for each configured query
2. **Deduplication**: Use existing `seen_urls` table in `data/news-pipeline.db`
3. **Clustering**: Group articles about the same event (shared entities + time proximity)
   - Reuse logic from archived `event_clusterer.py` but simplified:
   - Same entity overlap (≥2 shared entities) OR same title similarity (Jaccard ≥ 0.3)
   - Within 48h time window
4. **Breaking detection**: If ≥3 articles from different source domains arrive within 30 minutes on the same cluster → `is_breaking = True`
5. **Domain classification**: Reuse keyword-based classification from `spike-detector.py` (the `DOMAIN_KEYWORDS` dict)
6. **Budget tracking**: Respect `brave.max_requests_per_month` (900) and `brave.daily_soft_limit` (50)

### API Details

Brave Search API:
```
GET https://api.search.brave.com/res/v1/news/search
Headers: X-Subscription-Token: {BRAVE_API_KEY}
Params: q={query}, count={count}, country={country}, freshness={freshness}
```

Response shape:
```json
{
  "results": [
    {
      "url": "https://...",
      "title": "...",
      "description": "...",
      "age": "3 hours ago",
      "extra_snippets": ["..."],
      "meta_url": {"hostname": "reuters.com"}
    }
  ]
}
```

### What to Copy from Archive

From `archive/B10-pruned-20260228/scripts/brave_ingestor.py`:
- `Article` dataclass (simplify — drop tone/lean/geo_cluster/reliability fields)
- `parse_age()` function (handles "3 hours ago" → datetime)
- `BudgetTracker` class
- `BraveNewsPoller._build_query_string()` and `_poll_single()` methods
- SQLite dedup logic

From `archive/B10-pruned-20260228/scripts/event_clusterer.py`:
- Entity overlap matching
- Cluster ID generation
- But simplify: no PerspectiveMatrix, no divergence scoring

### What NOT to Include

- No tone extraction (that's Module 3's job)
- No perspective matrix
- No truth extraction
- No signal generation (later modules)
- No `--forever` polling loop (the orchestrator handles scheduling)

### CLI Interface

```bash
python3 scripts/s012/news_ingestor.py                     # One-shot poll all queries
python3 scripts/s012/news_ingestor.py --query iran-nuclear # Poll single query
python3 scripts/s012/news_ingestor.py --budget             # Show API budget
python3 scripts/s012/news_ingestor.py --demo               # Synthetic demo data
python3 scripts/s012/news_ingestor.py --events             # Show recent events/clusters
```

### Tests

Write tests in `scripts/s012/test_s012.py` (append to file, don't overwrite):
- `test_parse_age()` — known age strings → correct datetimes
- `test_domain_classification()` — keywords → correct domains
- `test_breaking_detection()` — 3 articles in 30 min → is_breaking
- `test_dedup()` — same URL twice → only stored once
- `test_clustering()` — articles with shared entities → same cluster

### Conventions

- Python 3.12+, type hints everywhere
- Use `httpx` for async HTTP (already a dependency)
- Use `sqlite3` (stdlib) for DB
- Use `dataclasses` (stdlib)
- Path handling via `pathlib`
- Logging via `logging` module (not print)
- All functions should be importable (no side effects on import)
