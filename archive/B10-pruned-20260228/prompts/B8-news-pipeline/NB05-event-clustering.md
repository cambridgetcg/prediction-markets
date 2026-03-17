# NB05: Event Clustering Engine
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Context
[Paste NB01 + Article dataclass + PerspectiveMatrix here]

## Approach: Entity + Date Overlap
- Match: ≥2 shared named entities AND published within 48h
- Cluster ID: deterministic hash of sorted top-3 entities + date (YYYY-MM-DD)
- Fallback: title Jaccard similarity ≥0.3 if entity extraction failed

## Requirements

1. **EventCluster dataclass**:
   ```python
   @dataclass
   class EventCluster:
       cluster_id: str
       event_summary: str           # "{top_entity}: {key_claim}"
       first_seen: datetime
       last_updated: datetime
       articles: list[Article]
       key_entities: list[str]      # union, sorted by frequency
       perspective_matrix: PerspectiveMatrix
       divergence_score: float
       is_divergent: bool
       query_sources: list[str]
   ```

2. **EventClusterer class**:
   - `cluster(new_articles, existing_clusters) -> list[EventCluster]`
   - Entity overlap matching
   - Merge into existing OR create new
   - Recompute perspective_matrix on merge
   - Cluster expiry: 72h no new articles → archive

3. **Auto-summary**: `"{most_mentioned_entity} — {most_common_key_claim}"`

4. **SQLite persistence**: clusters + archive tables

5. **Tests**:
   - 10 articles same event → 1 cluster
   - 10 articles 3 events → 3 clusters
   - Merge new article into correct cluster

## Output
`event_clusterer.py` + `schema.sql` + tests.
