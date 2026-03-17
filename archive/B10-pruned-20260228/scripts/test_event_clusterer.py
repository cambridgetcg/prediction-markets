"""Tests for NB05: Event Clustering Engine.

Run: python -m pytest scripts/test_event_clusterer.py -v
  or: python scripts/test_event_clusterer.py
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from brave_ingestor import Article
from event_clusterer import (
    EventCluster,
    EventClusterer,
    _auto_summary,
    _entity_overlap,
    _entity_set,
    _jaccard,
    _make_cluster_id,
    _ranked_entities,
    _title_words,
    _within_time_window,
)


def _make_article(
    url: str = "https://example.com/test",
    title: str = "Test Article",
    entities: list[str] | None = None,
    tone: float | None = None,
    country: str = "US",
    published_at: datetime | None = None,
    key_claim: str | None = None,
    query_name: str = "test",
    source_domain: str = "example.com",
    geo_cluster: str | None = None,
    reliability: float | None = None,
) -> Article:
    if published_at is None:
        published_at = datetime.now(timezone.utc)
    a = Article(
        url=url,
        title=title,
        description="Test description.",
        extra_snippets=[],
        full_text="",
        source_name="Test Source",
        source_domain=source_domain,
        country_queried=country,
        age_raw="1 hour ago",
        published_at=published_at,
        query_name=query_name,
        fetched_at=datetime.now(timezone.utc),
        tone=tone,
        entities=entities,
        key_claim=key_claim,
        geo_cluster=geo_cluster,
        reliability=reliability,
    )
    return a


class TestHelpers(unittest.TestCase):

    def test_make_cluster_id_deterministic(self):
        id1 = _make_cluster_id(["Iran", "IAEA", "Vienna"], "2026-02-27")
        id2 = _make_cluster_id(["Iran", "IAEA", "Vienna"], "2026-02-27")
        self.assertEqual(id1, id2)

    def test_make_cluster_id_order_independent(self):
        """Top-3 are sorted, so order shouldn't matter."""
        id1 = _make_cluster_id(["IAEA", "Iran", "Vienna"], "2026-02-27")
        id2 = _make_cluster_id(["Vienna", "Iran", "IAEA"], "2026-02-27")
        self.assertEqual(id1, id2)

    def test_make_cluster_id_different_date(self):
        id1 = _make_cluster_id(["Iran", "IAEA"], "2026-02-27")
        id2 = _make_cluster_id(["Iran", "IAEA"], "2026-02-28")
        self.assertNotEqual(id1, id2)

    def test_entity_set_normalization(self):
        a = _make_article(entities=["Iran", " IAEA ", "iran"])
        s = _entity_set(a)
        self.assertEqual(s, {"iran", "iaea"})

    def test_entity_set_empty(self):
        a = _make_article(entities=None)
        self.assertEqual(_entity_set(a), set())

    def test_title_words_removes_stop_words(self):
        a = _make_article(title="Iran and the IAEA reach a nuclear deal in Vienna")
        words = _title_words(a)
        self.assertNotIn("and", words)
        self.assertNotIn("the", words)
        self.assertIn("iran", words)
        self.assertIn("iaea", words)

    def test_jaccard_identical(self):
        self.assertAlmostEqual(_jaccard({"a", "b"}, {"a", "b"}), 1.0)

    def test_jaccard_disjoint(self):
        self.assertAlmostEqual(_jaccard({"a", "b"}, {"c", "d"}), 0.0)

    def test_jaccard_partial(self):
        self.assertAlmostEqual(_jaccard({"a", "b", "c"}, {"b", "c", "d"}), 0.5)

    def test_jaccard_empty(self):
        self.assertAlmostEqual(_jaccard(set(), {"a"}), 0.0)

    def test_entity_overlap(self):
        self.assertEqual(
            _entity_overlap({"iran", "iaea", "vienna"}, {"iran", "iaea", "nuclear"}),
            2,
        )

    def test_within_time_window(self):
        t1 = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 2, 28, 12, 0, tzinfo=timezone.utc)  # 24h later
        self.assertTrue(_within_time_window(t1, t2, hours=48))

    def test_outside_time_window(self):
        t1 = datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)  # 3 days later
        self.assertFalse(_within_time_window(t1, t2, hours=48))

    def test_ranked_entities(self):
        articles = [
            _make_article(entities=["Iran", "IAEA", "Vienna"]),
            _make_article(entities=["Iran", "IAEA"]),
            _make_article(entities=["Iran"]),
        ]
        ranked = _ranked_entities(articles)
        self.assertEqual(ranked[0], "Iran")  # 3 occurrences
        self.assertEqual(ranked[1], "IAEA")  # 2 occurrences

    def test_auto_summary(self):
        articles = [
            _make_article(entities=["Iran", "IAEA"], key_claim="IAEA reports progress."),
            _make_article(entities=["Iran", "IAEA"], key_claim="IAEA reports progress."),
            _make_article(entities=["Iran"], key_claim="Iran denies allegations."),
        ]
        summary = _auto_summary(articles)
        self.assertIn("Iran", summary)
        self.assertIn("IAEA reports progress", summary)


class TestClusteringSameEvent(unittest.TestCase):
    """10 articles about the same event → 1 cluster."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.clusterer = EventClusterer(db_path=self.db_path)

    def tearDown(self):
        self.clusterer.close()
        self.db_path.unlink(missing_ok=True)

    def test_10_articles_same_event_1_cluster(self):
        now = datetime.now(timezone.utc)
        articles = []
        for i in range(10):
            articles.append(_make_article(
                url=f"https://example.com/iran-{i}",
                title=f"Iran nuclear talks update {i}",
                entities=["Iran", "IAEA", "Vienna", "nuclear"],
                tone=[-0.5, 0.3, -0.8, 0.1, 0.0][i % 5],
                country=["US", "GB", "RU", "SA", "TR"][i % 5],
                published_at=now - timedelta(hours=i),
                key_claim="IAEA inspectors report on enrichment.",
            ))

        clusters = self.clusterer.cluster(articles)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0].articles), 10)
        self.assertIn("Iran", clusters[0].key_entities)


class TestClusteringMultipleEvents(unittest.TestCase):
    """10 articles across 3 distinct events → 3 clusters."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.clusterer = EventClusterer(db_path=self.db_path)

    def tearDown(self):
        self.clusterer.close()
        self.db_path.unlink(missing_ok=True)

    def test_10_articles_3_events_3_clusters(self):
        now = datetime.now(timezone.utc)
        articles = []

        # Event A: Iran nuclear (4 articles)
        for i in range(4):
            articles.append(_make_article(
                url=f"https://example.com/iran-{i}",
                title=f"Iran nuclear talks update {i}",
                entities=["Iran", "IAEA", "Vienna"],
                published_at=now - timedelta(hours=i),
            ))

        # Event B: Ukraine conflict (3 articles)
        for i in range(3):
            articles.append(_make_article(
                url=f"https://example.com/ukraine-{i}",
                title=f"Ukraine conflict escalation {i}",
                entities=["Ukraine", "Zelensky", "NATO", "Russia"],
                published_at=now - timedelta(hours=i),
            ))

        # Event C: Fed rates (3 articles)
        for i in range(3):
            articles.append(_make_article(
                url=f"https://example.com/fed-{i}",
                title=f"Federal Reserve rate decision {i}",
                entities=["Federal Reserve", "Powell", "Treasury"],
                published_at=now - timedelta(hours=i),
            ))

        clusters = self.clusterer.cluster(articles)
        self.assertEqual(len(clusters), 3)

        sizes = sorted(len(c.articles) for c in clusters)
        self.assertEqual(sizes, [3, 3, 4])


class TestMergeIntoExistingCluster(unittest.TestCase):
    """New article merges into the correct existing cluster."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.clusterer = EventClusterer(db_path=self.db_path)

    def tearDown(self):
        self.clusterer.close()
        self.db_path.unlink(missing_ok=True)

    def test_merge_new_article_into_correct_cluster(self):
        now = datetime.now(timezone.utc)

        # First batch: 2 Iran articles
        batch1 = [
            _make_article(
                url="https://example.com/iran-1",
                title="Iran IAEA Vienna talks",
                entities=["Iran", "IAEA", "Vienna"],
                published_at=now - timedelta(hours=5),
            ),
            _make_article(
                url="https://example.com/iran-2",
                title="Iran nuclear inspectors",
                entities=["Iran", "IAEA", "nuclear"],
                published_at=now - timedelta(hours=4),
            ),
        ]
        clusters = self.clusterer.cluster(batch1)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0].articles), 2)

        # Second batch: 1 new Iran article → should merge
        batch2 = [
            _make_article(
                url="https://example.com/iran-3",
                title="Vienna nuclear agreement",
                entities=["Iran", "IAEA", "agreement"],
                published_at=now - timedelta(hours=2),
            ),
        ]
        clusters = self.clusterer.cluster(batch2, existing_clusters=clusters)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0].articles), 3)

    def test_new_event_creates_separate_cluster(self):
        now = datetime.now(timezone.utc)

        batch1 = [
            _make_article(
                url="https://example.com/iran-1",
                entities=["Iran", "IAEA", "Vienna"],
                published_at=now,
            ),
        ]
        clusters = self.clusterer.cluster(batch1)

        batch2 = [
            _make_article(
                url="https://example.com/fed-1",
                title="Fed raises rates",
                entities=["Federal Reserve", "Powell", "Treasury"],
                published_at=now,
            ),
        ]
        clusters = self.clusterer.cluster(batch2, existing_clusters=clusters)
        self.assertEqual(len(clusters), 2)


class TestTitleJaccardFallback(unittest.TestCase):
    """Fallback to title Jaccard when entities are sparse."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.clusterer = EventClusterer(db_path=self.db_path)

    def tearDown(self):
        self.clusterer.close()
        self.db_path.unlink(missing_ok=True)

    def test_jaccard_fallback_clusters_similar_titles(self):
        now = datetime.now(timezone.utc)
        articles = [
            _make_article(
                url="https://example.com/1",
                title="Iran nuclear talks progress in Vienna today",
                entities=["Iran"],  # Only 1 entity — triggers fallback
                published_at=now,
            ),
            _make_article(
                url="https://example.com/2",
                title="Iran nuclear talks progress reported in Vienna",
                entities=[],  # No entities — triggers fallback
                published_at=now - timedelta(hours=1),
            ),
        ]
        clusters = self.clusterer.cluster(articles)
        self.assertEqual(len(clusters), 1)

    def test_dissimilar_titles_separate_clusters(self):
        now = datetime.now(timezone.utc)
        articles = [
            _make_article(
                url="https://example.com/1",
                title="Iran nuclear talks progress in Vienna",
                entities=["Iran"],
                published_at=now,
            ),
            _make_article(
                url="https://example.com/2",
                title="Federal Reserve raises interest rates sharply",
                entities=[],
                published_at=now,
            ),
        ]
        clusters = self.clusterer.cluster(articles)
        self.assertEqual(len(clusters), 2)


class TestTimeWindowEnforcement(unittest.TestCase):
    """Articles >48h apart should not cluster together."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.clusterer = EventClusterer(db_path=self.db_path)

    def tearDown(self):
        self.clusterer.close()
        self.db_path.unlink(missing_ok=True)

    def test_articles_outside_48h_window_separate(self):
        t1 = datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 2, 28, 12, 0, tzinfo=timezone.utc)  # 72h later

        articles = [
            _make_article(
                url="https://example.com/old",
                entities=["Iran", "IAEA", "Vienna"],
                published_at=t1,
            ),
            _make_article(
                url="https://example.com/new",
                entities=["Iran", "IAEA", "Vienna"],
                published_at=t2,
            ),
        ]
        clusters = self.clusterer.cluster(articles)
        self.assertEqual(len(clusters), 2)


class TestSQLitePersistence(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)

    def test_clusters_persisted_and_loadable(self):
        now = datetime.now(timezone.utc)
        articles = [
            _make_article(
                url=f"https://example.com/{i}",
                entities=["Iran", "IAEA", "Vienna"],
                published_at=now,
            )
            for i in range(3)
        ]

        clusterer = EventClusterer(db_path=self.db_path)
        clusters = clusterer.cluster(articles)
        self.assertEqual(len(clusters), 1)

        # Load from DB
        loaded = clusterer.load_clusters()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].cluster_id, clusters[0].cluster_id)
        self.assertEqual(loaded[0].event_summary, clusters[0].event_summary)
        clusterer.close()

    def test_expire_stale_clusters(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=100)

        # Create a cluster with old last_updated
        articles = [
            _make_article(
                url="https://example.com/old",
                entities=["Iran", "IAEA", "Vienna"],
                published_at=old,
            ),
        ]
        clusterer = EventClusterer(db_path=self.db_path)
        clusterer.cluster(articles)

        # Should be expired (>72h old)
        count = clusterer.expire_stale(expiry_hours=72)
        self.assertEqual(count, 1)

        # No active clusters remain
        active = clusterer.load_clusters()
        self.assertEqual(len(active), 0)
        clusterer.close()


class TestPerspectiveMatrixRecompute(unittest.TestCase):
    """Verify PerspectiveMatrix is recomputed on merge."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.clusterer = EventClusterer(db_path=self.db_path)

    def tearDown(self):
        self.clusterer.close()
        self.db_path.unlink(missing_ok=True)

    def test_matrix_updated_on_merge(self):
        now = datetime.now(timezone.utc)

        # Start with 2 Western articles
        batch1 = [
            _make_article(
                url="https://example.com/w1",
                entities=["Iran", "IAEA", "Vienna"],
                tone=0.5,
                country="US",
                source_domain="reuters.com",
                geo_cluster="Western",
                reliability=0.9,
                published_at=now,
            ),
            _make_article(
                url="https://example.com/w2",
                entities=["Iran", "IAEA"],
                tone=0.4,
                country="GB",
                source_domain="bbc.com",
                geo_cluster="Western",
                reliability=0.8,
                published_at=now,
            ),
        ]
        clusters = self.clusterer.cluster(batch1)
        initial_matrix = clusters[0].perspective_matrix
        self.assertIn("Western", initial_matrix.clusters)

        # Add a Russian article
        batch2 = [
            _make_article(
                url="https://example.com/r1",
                entities=["Iran", "IAEA"],
                tone=-0.7,
                country="RU",
                source_domain="rt.com",
                geo_cluster="Russian",
                reliability=0.3,
                published_at=now,
            ),
        ]
        clusters = self.clusterer.cluster(batch2, existing_clusters=clusters)
        updated_matrix = clusters[0].perspective_matrix
        # Now should have both clusters
        self.assertIn("Western", updated_matrix.clusters)
        self.assertIn("Russian", updated_matrix.clusters)


if __name__ == "__main__":
    unittest.main()
