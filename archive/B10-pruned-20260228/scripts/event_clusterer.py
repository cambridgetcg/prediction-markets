#!/usr/bin/env python3
"""NB05: Event Clustering Engine — Stage 5 of the News Intelligence Pipeline.

Groups articles about the same real-world event using entity overlap + date
proximity. Persists clusters to SQLite. Recomputes PerspectiveMatrix on merge.

Usage:
    # As library — called by pipeline orchestrator:
    from event_clusterer import EventClusterer
    clusterer = EventClusterer()
    clusters = clusterer.cluster(new_articles)

    # CLI:
    python3 scripts/event_clusterer.py --demo
    python3 scripts/event_clusterer.py --show          # Show active clusters
    python3 scripts/event_clusterer.py --expire         # Archive stale clusters
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from brave_ingestor import Article  # noqa: E402
from perspective_matrix import PerspectiveMatrix  # noqa: E402

logger = logging.getLogger(__name__)

PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"

# --- Matching thresholds ---
MIN_SHARED_ENTITIES = 2
TIME_WINDOW_HOURS = 48
JACCARD_FALLBACK_THRESHOLD = 0.3
EXPIRY_HOURS = 72


# --- Dataclass ---

@dataclass
class EventCluster:
    cluster_id: str
    event_summary: str                # "{top_entity}: {key_claim}"
    first_seen: datetime
    last_updated: datetime
    articles: list[Article]
    key_entities: list[str]           # union, sorted by frequency
    perspective_matrix: PerspectiveMatrix
    divergence_score: float
    is_divergent: bool
    query_sources: list[str]


# --- Helpers ---

def _make_cluster_id(entities: list[str], date_str: str) -> str:
    """Deterministic hash of sorted top-3 entities + date."""
    top3 = sorted(entities[:3]) if entities else ["unknown"]
    raw = "|".join(top3) + "|" + date_str
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _entity_set(article: Article) -> set[str]:
    """Normalized entity set for an article."""
    if not article.entities:
        return set()
    return {e.lower().strip() for e in article.entities if e.strip()}


def _title_words(article: Article) -> set[str]:
    """Lowercase word set from title (for Jaccard fallback)."""
    stop = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and",
            "or", "is", "are", "was", "were", "be", "by", "with", "from",
            "that", "this", "it", "as", "has", "had", "have", "not", "but",
            "will", "its", "may", "can", "could", "would", "should", "been"}
    words = set(article.title.lower().split()) - stop
    return {w.strip(".,!?;:\"'()[]") for w in words if len(w) > 2}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _entity_overlap(a: set[str], b: set[str]) -> int:
    return len(a & b)


def _within_time_window(dt1: datetime, dt2: datetime, hours: int = TIME_WINDOW_HOURS) -> bool:
    return abs((dt1 - dt2).total_seconds()) <= hours * 3600


def _ranked_entities(articles: list[Article]) -> list[str]:
    """Union of entities across articles, sorted by frequency descending."""
    counts: dict[str, int] = {}
    for a in articles:
        for e in (a.entities or []):
            key = e.strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
    return sorted(counts, key=lambda e: (-counts[e], e))


def _auto_summary(articles: list[Article]) -> str:
    """'{most_mentioned_entity} — {most_common_key_claim}'"""
    ranked = _ranked_entities(articles)
    top_entity = ranked[0] if ranked else "Unknown"

    # Find most common key_claim
    claims: dict[str, int] = {}
    for a in articles:
        if a.key_claim:
            claims[a.key_claim] = claims.get(a.key_claim, 0) + 1
    if claims:
        best_claim = max(claims, key=claims.get)
    else:
        # Fallback: shortest title as summary
        best_claim = min((a.title for a in articles), key=len, default="")
    return f"{top_entity}: {best_claim[:120]}"


# --- Clusterer ---

class EventClusterer:
    """Groups articles into EventClusters by entity overlap + date proximity.

    Matching rules:
      1. Primary: ≥2 shared named entities AND published within 48h
      2. Fallback: title Jaccard similarity ≥0.3 if entity extraction failed
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS event_clusters (
                cluster_id       TEXT PRIMARY KEY,
                event_summary    TEXT,
                domain           TEXT,
                key_entities     TEXT,
                first_seen       TEXT,
                last_updated     TEXT,
                article_count    INTEGER DEFAULT 0,
                query_sources    TEXT,
                divergence_score REAL DEFAULT 0.0,
                is_divergent     INTEGER DEFAULT 0,
                status           TEXT DEFAULT 'active'
            );
            CREATE TABLE IF NOT EXISTS cluster_articles (
                cluster_id   TEXT,
                url_hash     TEXT,
                PRIMARY KEY (cluster_id, url_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_clusters_status
                ON event_clusters(status);
        """)
        self.conn.commit()

    def cluster(
        self,
        new_articles: list[Article],
        existing_clusters: list[EventCluster] | None = None,
    ) -> list[EventCluster]:
        """Assign new articles to existing clusters or create new ones.

        Returns the full list of active (non-archived) clusters.
        """
        if existing_clusters is None:
            existing_clusters = []

        clusters = list(existing_clusters)

        for article in new_articles:
            matched = self._find_match(article, clusters)
            if matched is not None:
                self._merge(article, matched)
            else:
                clusters.append(self._new_cluster(article))

        # Persist all clusters
        for c in clusters:
            self._persist(c)

        return clusters

    def _find_match(self, article: Article, clusters: list[EventCluster]) -> EventCluster | None:
        """Find the best matching cluster for an article, or None."""
        art_entities = _entity_set(article)
        art_title_words = _title_words(article)
        best: EventCluster | None = None
        best_score = 0

        for c in clusters:
            # Time window check against cluster span
            if not _within_time_window(article.published_at, c.first_seen):
                continue

            # Primary: entity overlap
            cluster_entities = {e.lower().strip() for e in c.key_entities if e.strip()}
            overlap = _entity_overlap(art_entities, cluster_entities)
            if overlap >= MIN_SHARED_ENTITIES and overlap > best_score:
                best = c
                best_score = overlap
                continue

            # Fallback: title Jaccard if entities are sparse
            if len(art_entities) < 2:
                for ca in c.articles:
                    jacc = _jaccard(art_title_words, _title_words(ca))
                    if jacc >= JACCARD_FALLBACK_THRESHOLD and jacc > best_score:
                        best = c
                        best_score = jacc

        return best

    def _merge(self, article: Article, cluster: EventCluster) -> None:
        """Merge an article into an existing cluster. Recompute matrix."""
        cluster.articles.append(article)
        cluster.key_entities = _ranked_entities(cluster.articles)
        cluster.last_updated = max(cluster.last_updated, article.published_at)
        cluster.event_summary = _auto_summary(cluster.articles)
        if article.query_name and article.query_name not in cluster.query_sources:
            cluster.query_sources.append(article.query_name)

        # Recompute perspective matrix
        matrix = PerspectiveMatrix.build(cluster.articles)
        cluster.perspective_matrix = matrix
        cluster.divergence_score = matrix.divergence_score
        cluster.is_divergent = matrix.is_divergent

    def _new_cluster(self, article: Article) -> EventCluster:
        """Create a new cluster from a single article."""
        entities = _ranked_entities([article])
        date_str = article.published_at.strftime("%Y-%m-%d")
        cluster_id = _make_cluster_id(entities, date_str)

        matrix = PerspectiveMatrix.build([article])

        return EventCluster(
            cluster_id=cluster_id,
            event_summary=_auto_summary([article]),
            first_seen=article.published_at,
            last_updated=article.published_at,
            articles=[article],
            key_entities=entities,
            perspective_matrix=matrix,
            divergence_score=matrix.divergence_score,
            is_divergent=matrix.is_divergent,
            query_sources=[article.query_name] if article.query_name else [],
        )

    # --- SQLite persistence ---

    def _persist(self, cluster: EventCluster) -> None:
        """Upsert a cluster and its article memberships to SQLite."""
        self.conn.execute("""
            INSERT INTO event_clusters
                (cluster_id, event_summary, key_entities, first_seen,
                 last_updated, article_count, query_sources,
                 divergence_score, is_divergent, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            ON CONFLICT(cluster_id) DO UPDATE SET
                event_summary = excluded.event_summary,
                key_entities = excluded.key_entities,
                last_updated = excluded.last_updated,
                article_count = excluded.article_count,
                query_sources = excluded.query_sources,
                divergence_score = excluded.divergence_score,
                is_divergent = excluded.is_divergent
        """, (
            cluster.cluster_id,
            cluster.event_summary,
            json.dumps(cluster.key_entities),
            cluster.first_seen.isoformat(),
            cluster.last_updated.isoformat(),
            len(cluster.articles),
            json.dumps(cluster.query_sources),
            cluster.divergence_score,
            int(cluster.is_divergent),
        ))
        for a in cluster.articles:
            self.conn.execute(
                "INSERT OR IGNORE INTO cluster_articles (cluster_id, url_hash) VALUES (?, ?)",
                (cluster.cluster_id, a.url_hash),
            )
        self.conn.commit()

    def load_clusters(self) -> list[EventCluster]:
        """Load active clusters from SQLite (without full Article objects)."""
        rows = self.conn.execute(
            "SELECT cluster_id, event_summary, key_entities, first_seen, "
            "last_updated, article_count, query_sources, divergence_score, "
            "is_divergent FROM event_clusters WHERE status = 'active'"
        ).fetchall()

        clusters = []
        for row in rows:
            clusters.append(EventCluster(
                cluster_id=row[0],
                event_summary=row[1],
                first_seen=datetime.fromisoformat(row[3]),
                last_updated=datetime.fromisoformat(row[4]),
                articles=[],  # Articles not hydrated from DB
                key_entities=json.loads(row[2]) if row[2] else [],
                perspective_matrix=PerspectiveMatrix(clusters={}, divergence_score=0.0, is_divergent=False),
                divergence_score=row[7] or 0.0,
                is_divergent=bool(row[8]),
                query_sources=json.loads(row[6]) if row[6] else [],
            ))
        return clusters

    def expire_stale(self, expiry_hours: int = EXPIRY_HOURS) -> int:
        """Archive clusters with no new articles for `expiry_hours`. Returns count archived."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=expiry_hours)).isoformat()
        cursor = self.conn.execute(
            "UPDATE event_clusters SET status = 'archived' "
            "WHERE status = 'active' AND last_updated < ?",
            (cutoff,),
        )
        self.conn.commit()
        return cursor.rowcount

    def close(self):
        self.conn.close()


# --- CLI ---

def _make_test_article(**overrides) -> Article:
    from datetime import datetime, timezone
    defaults = dict(
        url="https://example.com/test",
        title="Test Article",
        description="A test description.",
        extra_snippets=[],
        full_text="",
        source_name="Test Source",
        source_domain="example.com",
        country_queried="US",
        age_raw="1 hour ago",
        published_at=datetime.now(timezone.utc),
        query_name="test",
        fetched_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Article(**defaults)


def cmd_demo():
    """Run clustering on demo articles."""
    import tempfile
    now = datetime.now(timezone.utc)

    # 10 articles about the same Iran event
    iran_articles = []
    for i in range(10):
        country = ["US", "GB", "RU", "SA", "TR"][i % 5]
        sources = [
            ("reuters.com", "Reuters"), ("bbc.com", "BBC"),
            ("rt.com", "RT"), ("arabnews.com", "Arab News"),
            ("dailysabah.com", "Daily Sabah"),
        ]
        src_domain, src_name = sources[i % 5]
        iran_articles.append(_make_test_article(
            url=f"https://{src_domain}/iran-nuclear-{i}",
            title=f"Iran nuclear talks {['progress', 'stall', 'advance', 'continue', 'resume'][i % 5]} in Vienna",
            description=f"IAEA inspectors report on Iran enrichment levels. Article {i}.",
            source_domain=src_domain,
            source_name=src_name,
            country_queried=country,
            published_at=now - timedelta(hours=i),
            entities=["Iran", "IAEA", "Vienna", "nuclear"],
            tone=[-0.5, 0.3, -0.8, 0.1, 0.0][i % 5],
            key_claim="IAEA reports enrichment levels below threshold.",
        ))

    # 5 articles about a different event (Ukraine)
    ukr_articles = []
    for i in range(5):
        country = ["US", "GB", "RU"][i % 3]
        ukr_articles.append(_make_test_article(
            url=f"https://example.com/ukraine-{i}",
            title=f"Ukraine {'counter-offensive', 'ceasefire', 'talks'}  update {i}",
            description=f"Zelensky addresses NATO on defense aid. Article {i}.",
            source_domain="reuters.com",
            source_name="Reuters",
            country_queried=country,
            published_at=now - timedelta(hours=i),
            entities=["Ukraine", "Zelensky", "NATO", "Russia"],
            tone=[0.2, -0.3, -0.6, 0.1, -0.2][i % 5],
            key_claim="Zelensky calls for increased NATO support.",
        ))

    # Use temp DB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)

    clusterer = EventClusterer(db_path=db_path)
    all_articles = iran_articles + ukr_articles
    clusters = clusterer.cluster(all_articles)

    print(f"Input: {len(all_articles)} articles")
    print(f"Output: {len(clusters)} clusters\n")

    for c in clusters:
        print(f"--- Cluster {c.cluster_id} ---")
        print(f"  Summary:    {c.event_summary}")
        print(f"  Articles:   {len(c.articles)}")
        print(f"  Entities:   {c.key_entities[:5]}")
        print(f"  Divergence: {c.divergence_score:.4f} {'(DIVERGENT)' if c.is_divergent else ''}")
        print(f"  Queries:    {c.query_sources}")
        print()

    clusterer.close()
    db_path.unlink(missing_ok=True)


def cmd_show():
    """Show active clusters from the pipeline DB."""
    if not DB_PATH.exists():
        print(f"No database at {DB_PATH}")
        return

    clusterer = EventClusterer(db_path=DB_PATH)
    clusters = clusterer.load_clusters()

    if not clusters:
        print("No active clusters.")
    else:
        print(f"{len(clusters)} active cluster(s):\n")
        for c in clusters:
            print(f"  [{c.cluster_id}] {c.event_summary}")
            print(f"    Entities: {c.key_entities[:5]}")
            print(f"    Divergence: {c.divergence_score:.4f} {'DIVERGENT' if c.is_divergent else ''}")
            print(f"    Updated: {c.last_updated.isoformat()}")
            print()

    clusterer.close()


def cmd_expire():
    """Archive stale clusters."""
    if not DB_PATH.exists():
        print(f"No database at {DB_PATH}")
        return

    clusterer = EventClusterer(db_path=DB_PATH)
    count = clusterer.expire_stale()
    print(f"Archived {count} stale cluster(s).")
    clusterer.close()


def main():
    args = sys.argv[1:]
    if "--demo" in args:
        cmd_demo()
    elif "--show" in args:
        cmd_show()
    elif "--expire" in args:
        cmd_expire()
    else:
        print("NB05: Event Clustering Engine")
        print("  --demo    Run with demo articles")
        print("  --show    Show active clusters from pipeline DB")
        print("  --expire  Archive stale clusters (72h)")


if __name__ == "__main__":
    main()
