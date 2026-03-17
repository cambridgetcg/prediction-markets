# NB04: Perspective Matrix Builder
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Context
[Paste NB01 + NB02 Article dataclass (with tone/entities) here]

## Two Layers of Perspective Signal

1. **`country_queried`** — which regional Brave index surfaced this article
   - Same article in US and RU index = cross-perspective confirmation
   - Article only in RU index = likely Russian-specific coverage

2. **Source domain bias** — publication's known lean + reliability

## Country → Cluster Mapping
```python
COUNTRY_TO_CLUSTER = {
    "US": "Western", "GB": "Western", "AU": "Western",
    "DE": "Western", "FR": "Western", "CA": "Western",
    "RU": "Russian", "BY": "Russian",
    "CN": "Chinese", "HK": "Chinese",
    "IR": "Iranian",
    "QA": "Gulf", "SA": "Gulf", "AE": "Gulf",
    "IL": "Israeli",
    "TR": "Turkish",
}
```

## Requirements

1. **`source_bias.json`** — 200+ domains:
   ```json
   {
     "reuters.com":       {"lean": 0.0,  "reliability": 0.95, "geo": "Western"},
     "apnews.com":        {"lean": 0.0,  "reliability": 0.95, "geo": "Western"},
     "bbc.co.uk":         {"lean": -0.3, "reliability": 0.90, "geo": "Western"},
     "guardian.com":      {"lean": -0.8, "reliability": 0.82, "geo": "Western"},
     "foxnews.com":       {"lean":  1.5, "reliability": 0.55, "geo": "Western"},
     "rt.com":            {"lean": -1.8, "reliability": 0.30, "geo": "Russian"},
     "tass.com":          {"lean": -2.0, "reliability": 0.25, "geo": "Russian"},
     "aljazeera.com":     {"lean": -0.5, "reliability": 0.75, "geo": "Gulf"},
     "presstv.ir":        {"lean": -2.0, "reliability": 0.20, "geo": "Iranian"},
     "timesofisrael.com": {"lean":  0.8, "reliability": 0.70, "geo": "Israeli"},
     "xinhuanet.com":     {"lean": -1.5, "reliability": 0.35, "geo": "Chinese"},
     "cgtn.com":          {"lean": -1.5, "reliability": 0.35, "geo": "Chinese"},
     ...200+ total
   }
   ```

2. **PerspectiveTagger class**:
   - `tag(article: Article) -> Article`
   - Domain lookup → country fallback
   - Log unknown domains for table expansion

3. **PerspectiveMatrix**:
   ```python
   @dataclass
   class ClusterView:
       cluster_name: str
       article_count: int
       mean_tone: float
       reliability_weighted_tone: float
       key_claims: list[str]
       sources: list[str]

   @dataclass
   class PerspectiveMatrix:
       clusters: dict[str, ClusterView]
       divergence_score: float         # max_tone - min_tone across clusters
       is_divergent: bool
   ```

4. **Divergence detection**:
   - Primary: `max(mean_tone) - min(mean_tone)` across clusters with ≥2 articles
   - Secondary: claim divergence (non-overlapping key entities across clusters)
   - Threshold: 3.0 tone divergence OR ≥2 clusters with distinct key claims

5. **Tests**: divergent set, non-divergent set, unknown domain fallback

## Output
`perspective_matrix.py` + `source_bias.json` (200+ entries) + tests.
