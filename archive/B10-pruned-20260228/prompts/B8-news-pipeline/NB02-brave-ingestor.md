# NB02: Brave News Ingestor
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Context
[Paste NB01 architecture output here]

## Brave News API Reference
```python
import httpx

response = httpx.get(
    "https://api.search.brave.com/res/v1/news/search",
    headers={"X-Subscription-Token": BRAVE_API_KEY},
    params={
        "q": "Iran nuclear talks",
        "count": 20,
        "country": "US",
        "freshness": "pd",
        "extra_snippets": "true"
    }
)

# Response structure per article:
{
  "title": "US-Iran talks end with no deal",
  "url": "https://reuters.com/...",
  "description": "Hours of negotiation ended with no breakthrough...",
  "age": "9 hours ago",
  "source": {"name": "Reuters", "url": "https://reuters.com"},
  "extra_snippets": ["snippet 1", "snippet 2"]
}
```

## Your Task
Produce production-ready Python code:

1. **Article dataclass**:
   ```python
   @dataclass
   class Article:
       url: str
       title: str
       description: str
       extra_snippets: list[str]
       full_text: str               # title + description + snippets joined
       source_name: str
       source_domain: str           # extracted from source.url
       country_queried: str         # which country param returned this
       age_raw: str                 # "9 hours ago" or ISO
       published_at: datetime       # parsed from age_raw
       query_name: str              # which QueryConfig produced this
       fetched_at: datetime
       # Computed downstream:
       tone: float | None = None
       entities: list[str] | None = None
       lean: float | None = None
       geo_cluster: str | None = None
       reliability: float | None = None
   ```

2. **BraveNewsPoller class**:
   - `poll(query: QueryConfig) -> list[Article]`
   - Runs all country variants in parallel (asyncio or ThreadPoolExecutor)
   - Deduplicates by URL across countries — but keeps both records when same article
     appears in multiple country indexes (different country_queried = separate perspective data)
   - Respects rate limits (~1 req/sec)
   - Budget tracking: count requests, warn at 900/month

3. **QueryConfig dataclass**:
   ```python
   @dataclass
   class QueryConfig:
       name: str
       keywords: list[str]
       boolean_mode: str            # "OR" | "AND"
       countries: list[str]         # ["US", "GB", "RU", "IR", "QA", "CN"]
       freshness: str               # "pd" | "pw"
       count_per_country: int
       interval_minutes: int
       extra_snippets: bool
   ```

4. **Age parser** — convert "X hours ago" / "X days ago" / ISO → datetime

5. **URL deduplication** — SQLite seen-set, persist across poll cycles

6. **Polling scheduler**:
   - `run_forever(queries: list[QueryConfig])`
   - Tracks last poll time per query
   - Skips poll if interval not elapsed

7. **Request budget tracker**:
   - Count requests per hour/day/month
   - Log cost estimate ($5/1000)

8. **Tests** (pytest + httpx mock):
   - Multi-country poll, deduplication
   - Age parsing (all Brave formats)
   - Rate limit compliance
   - Budget warning trigger

## Output
`brave_ingestor.py` + `test_brave_ingestor.py`. Working code, no pseudocode.
