"""Tests for NB04: Perspective Matrix Builder.

Run: python -m pytest scripts/test_perspective_matrix.py -v
  or: python scripts/test_perspective_matrix.py
"""

import json
import tempfile
import unittest
from pathlib import Path

from perspective_matrix import (
    COUNTRY_TO_CLUSTER,
    Article,
    ClusterView,
    PerspectiveMatrix,
    PerspectiveTagger,
)


def _make_article(
    domain: str,
    country: str,
    tone: float | None = None,
    entities: list[str] | None = None,
    title: str = "Test Article",
) -> Article:
    return Article(
        url=f"https://{domain}/article",
        title=title,
        description="Test description",
        source_domain=domain,
        country_queried=country,
        tone=tone,
        entities=entities,
    )


# Minimal bias data for testing
_TEST_BIAS = {
    "reuters.com":    {"lean": 0.0,  "reliability": 0.90, "geo": "Western"},
    "bbc.com":        {"lean": -0.3, "reliability": 0.80, "geo": "Western"},
    "rt.com":         {"lean": -1.8, "reliability": 0.30, "geo": "Russian"},
    "tass.com":       {"lean": -2.0, "reliability": 0.25, "geo": "Russian"},
    "xinhuanet.com":  {"lean": -1.5, "reliability": 0.35, "geo": "Chinese"},
    "cgtn.com":       {"lean": -1.5, "reliability": 0.35, "geo": "Chinese"},
    "presstv.ir":     {"lean": -2.0, "reliability": 0.20, "geo": "Iranian"},
    "aljazeera.com":  {"lean": -0.8, "reliability": 0.66, "geo": "Gulf"},
    "foxnews.com":    {"lean": 1.5,  "reliability": 0.46, "geo": "Western"},
    "haaretz.com":    {"lean": -0.5, "reliability": 0.75, "geo": "Israeli"},
    "example.co.uk":  {"lean": 0.0,  "reliability": 0.70, "geo": "Western"},
}


class TestPerspectiveTagger(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(_TEST_BIAS, self.tmp)
        self.tmp.close()
        self.tagger = PerspectiveTagger(bias_path=self.tmp.name)

    def tearDown(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_known_domain_lookup(self):
        article = _make_article("reuters.com", "US")
        self.tagger.tag(article)
        self.assertEqual(article.lean, 0.0)
        self.assertEqual(article.reliability, 0.90)
        self.assertEqual(article.geo_cluster, "Western")

    def test_www_prefix_stripped(self):
        article = _make_article("www.reuters.com", "US")
        self.tagger.tag(article)
        self.assertEqual(article.reliability, 0.90)
        self.assertEqual(article.geo_cluster, "Western")

    def test_subdomain_fallback(self):
        """news.bbc.com should fall back to bbc.com."""
        article = _make_article("news.bbc.com", "GB")
        self.tagger.tag(article)
        self.assertEqual(article.geo_cluster, "Western")
        self.assertEqual(article.reliability, 0.80)

    def test_two_level_tld_subdomain(self):
        """news.example.co.uk should fall back to example.co.uk."""
        article = _make_article("news.example.co.uk", "GB")
        self.tagger.tag(article)
        self.assertEqual(article.geo_cluster, "Western")
        self.assertEqual(article.reliability, 0.70)

    def test_unknown_domain_fallback_to_country(self):
        """Unknown domain should fall back to country_queried cluster."""
        article = _make_article("unknownnews.org", "RU")
        self.tagger.tag(article)
        self.assertEqual(article.geo_cluster, "Russian")
        self.assertEqual(article.reliability, 0.5)
        self.assertEqual(article.lean, 0.0)
        self.assertIn("unknownnews.org", self.tagger.unknown_domains)

    def test_unknown_domain_unknown_country_defaults_western(self):
        """Unknown domain + unknown country → defaults to Western."""
        article = _make_article("mystery.news", "XX")
        self.tagger.tag(article)
        self.assertEqual(article.geo_cluster, "Western")

    def test_batch_tagging(self):
        articles = [
            _make_article("reuters.com", "US"),
            _make_article("rt.com", "RU"),
            _make_article("xinhuanet.com", "CN"),
        ]
        tagged = self.tagger.tag_batch(articles)
        self.assertEqual(len(tagged), 3)
        clusters = [a.geo_cluster for a in tagged]
        self.assertEqual(clusters, ["Western", "Russian", "Chinese"])

    def test_russian_source_properties(self):
        article = _make_article("rt.com", "RU")
        self.tagger.tag(article)
        self.assertEqual(article.geo_cluster, "Russian")
        self.assertLess(article.lean, -1.0)
        self.assertLess(article.reliability, 0.5)


class TestPerspectiveMatrixDivergent(unittest.TestCase):
    """Test with articles that should produce a divergent matrix."""

    def test_divergent_by_tone(self):
        """Western positive + Russian negative → divergent."""
        articles = [
            # Western cluster: positive tone
            _make_article("reuters.com", "US", tone=0.5, entities=["NATO", "Zelensky"]),
            _make_article("bbc.com", "GB", tone=0.4, entities=["NATO", "Ukraine"]),
            _make_article("foxnews.com", "US", tone=0.3, entities=["NATO", "defense"]),
            # Russian cluster: negative tone
            _make_article("rt.com", "RU", tone=-0.6, entities=["Russia", "provocation"]),
            _make_article("tass.com", "RU", tone=-0.7, entities=["Russia", "NATO"]),
        ]
        # Pre-tag articles
        for a in articles:
            bias = _TEST_BIAS.get(a.source_domain, {})
            a.lean = bias.get("lean", 0.0)
            a.reliability = bias.get("reliability", 0.5)
            a.geo_cluster = bias.get("geo", "Western")

        matrix = PerspectiveMatrix.build(articles, tone_threshold=0.6)

        self.assertIn("Western", matrix.clusters)
        self.assertIn("Russian", matrix.clusters)
        self.assertGreater(matrix.divergence_score, 0.6)
        self.assertTrue(matrix.is_divergent)

        # Western mean tone should be positive
        self.assertGreater(matrix.clusters["Western"].mean_tone, 0.0)
        # Russian mean tone should be negative
        self.assertLess(matrix.clusters["Russian"].mean_tone, 0.0)

    def test_divergent_reliability_weighted(self):
        """Reliability weighting should downweight less reliable sources."""
        articles = [
            _make_article("reuters.com", "US", tone=0.8, entities=["test"]),
            _make_article("reuters.com", "US", tone=0.6, entities=["test"]),
            _make_article("rt.com", "RU", tone=-0.5, entities=["test"]),
            _make_article("tass.com", "RU", tone=-0.8, entities=["test"]),
        ]
        for a in articles:
            bias = _TEST_BIAS.get(a.source_domain, {})
            a.lean = bias.get("lean", 0.0)
            a.reliability = bias.get("reliability", 0.5)
            a.geo_cluster = bias.get("geo", "Western")

        matrix = PerspectiveMatrix.build(articles)
        western = matrix.clusters["Western"]
        russian = matrix.clusters["Russian"]

        # Reuters (0.90) > RT (0.30) / TASS (0.25)
        self.assertGreater(western.reliability_weighted_tone, western.mean_tone * 0.8)


class TestPerspectiveMatrixNonDivergent(unittest.TestCase):
    """Test with articles that should NOT produce a divergent matrix."""

    def test_same_cluster_no_divergence(self):
        """All articles from same cluster → no divergence."""
        articles = [
            _make_article("reuters.com", "US", tone=0.2, entities=["economy"]),
            _make_article("bbc.com", "GB", tone=0.3, entities=["economy"]),
            _make_article("foxnews.com", "US", tone=0.1, entities=["economy"]),
        ]
        for a in articles:
            bias = _TEST_BIAS.get(a.source_domain, {})
            a.lean = bias.get("lean", 0.0)
            a.reliability = bias.get("reliability", 0.5)
            a.geo_cluster = bias.get("geo", "Western")

        matrix = PerspectiveMatrix.build(articles)
        self.assertEqual(matrix.divergence_score, 0.0)
        self.assertFalse(matrix.is_divergent)

    def test_similar_tone_across_clusters(self):
        """Both clusters agree → not divergent."""
        articles = [
            _make_article("reuters.com", "US", tone=0.3, entities=["earthquake"]),
            _make_article("bbc.com", "GB", tone=0.2, entities=["earthquake"]),
            _make_article("rt.com", "RU", tone=0.1, entities=["earthquake"]),
            _make_article("tass.com", "RU", tone=0.15, entities=["earthquake"]),
        ]
        for a in articles:
            bias = _TEST_BIAS.get(a.source_domain, {})
            a.lean = bias.get("lean", 0.0)
            a.reliability = bias.get("reliability", 0.5)
            a.geo_cluster = bias.get("geo", "Western")

        matrix = PerspectiveMatrix.build(articles)
        self.assertLess(matrix.divergence_score, 0.6)
        self.assertFalse(matrix.is_divergent)

    def test_single_article_per_cluster_excluded(self):
        """Clusters with <2 articles should be excluded from divergence."""
        articles = [
            _make_article("reuters.com", "US", tone=0.5, entities=["test"]),
            _make_article("bbc.com", "GB", tone=0.4, entities=["test"]),
            _make_article("rt.com", "RU", tone=-0.8, entities=["test"]),  # only 1 Russian
        ]
        for a in articles:
            bias = _TEST_BIAS.get(a.source_domain, {})
            a.lean = bias.get("lean", 0.0)
            a.reliability = bias.get("reliability", 0.5)
            a.geo_cluster = bias.get("geo", "Western")

        matrix = PerspectiveMatrix.build(articles, min_articles_per_cluster=2)
        # Only Western has ≥2 articles, so no divergence possible
        self.assertEqual(matrix.divergence_score, 0.0)
        self.assertFalse(matrix.is_divergent)


class TestPerspectiveMatrixEdgeCases(unittest.TestCase):

    def test_empty_articles(self):
        matrix = PerspectiveMatrix.build([])
        self.assertEqual(matrix.clusters, {})
        self.assertEqual(matrix.divergence_score, 0.0)
        self.assertFalse(matrix.is_divergent)

    def test_articles_without_tone(self):
        """Articles with tone=None should not crash."""
        articles = [
            _make_article("reuters.com", "US", tone=None, entities=["test"]),
            _make_article("bbc.com", "GB", tone=None, entities=["test"]),
        ]
        for a in articles:
            a.geo_cluster = "Western"
            a.reliability = 0.8

        matrix = PerspectiveMatrix.build(articles)
        self.assertEqual(matrix.clusters["Western"].mean_tone, 0.0)

    def test_cluster_view_sources_deduped(self):
        """Same source appearing twice should be deduped in sources list."""
        articles = [
            _make_article("reuters.com", "US", tone=0.3, entities=["A"]),
            _make_article("reuters.com", "GB", tone=0.4, entities=["B"]),
        ]
        for a in articles:
            a.geo_cluster = "Western"
            a.reliability = 0.9

        matrix = PerspectiveMatrix.build(articles)
        self.assertEqual(matrix.clusters["Western"].sources, ["reuters.com"])


class TestCountryClusterMapping(unittest.TestCase):

    def test_all_clusters_represented(self):
        clusters = set(COUNTRY_TO_CLUSTER.values())
        expected = {"Western", "Russian", "Chinese", "Iranian", "Gulf", "Israeli", "Turkish"}
        self.assertEqual(clusters, expected)

    def test_known_countries(self):
        self.assertEqual(COUNTRY_TO_CLUSTER["US"], "Western")
        self.assertEqual(COUNTRY_TO_CLUSTER["RU"], "Russian")
        self.assertEqual(COUNTRY_TO_CLUSTER["CN"], "Chinese")
        self.assertEqual(COUNTRY_TO_CLUSTER["IR"], "Iranian")
        self.assertEqual(COUNTRY_TO_CLUSTER["IL"], "Israeli")
        self.assertEqual(COUNTRY_TO_CLUSTER["TR"], "Turkish")
        self.assertEqual(COUNTRY_TO_CLUSTER["QA"], "Gulf")


class TestSourceBiasJson(unittest.TestCase):
    """Validate the actual source_bias.json file."""

    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parent.parent / "sources" / "source_bias.json"
        if not path.exists():
            raise unittest.SkipTest("source_bias.json not found")
        with open(path) as f:
            cls.bias = json.load(f)

    def test_minimum_200_entries(self):
        self.assertGreaterEqual(len(self.bias), 200)

    def test_all_entries_have_required_fields(self):
        for domain, entry in self.bias.items():
            self.assertIn("lean", entry, f"{domain} missing lean")
            self.assertIn("reliability", entry, f"{domain} missing reliability")
            self.assertIn("geo", entry, f"{domain} missing geo")

    def test_lean_range(self):
        for domain, entry in self.bias.items():
            self.assertGreaterEqual(entry["lean"], -2.0, f"{domain} lean too low")
            self.assertLessEqual(entry["lean"], 2.0, f"{domain} lean too high")

    def test_reliability_range(self):
        for domain, entry in self.bias.items():
            self.assertGreaterEqual(entry["reliability"], 0.0, f"{domain}")
            self.assertLessEqual(entry["reliability"], 1.0, f"{domain}")

    def test_geo_values_valid(self):
        valid_geos = {"Western", "Russian", "Chinese", "Iranian", "Gulf", "Israeli", "Turkish"}
        for domain, entry in self.bias.items():
            self.assertIn(entry["geo"], valid_geos, f"{domain} has invalid geo: {entry['geo']}")

    def test_key_domains_present(self):
        for domain in ["reuters.com", "rt.com", "xinhuanet.com", "presstv.ir",
                        "aljazeera.com", "timesofisrael.com", "dailysabah.com",
                        "bbc.com", "foxnews.com", "nytimes.com"]:
            self.assertIn(domain, self.bias, f"Missing key domain: {domain}")

    def test_multiple_geo_clusters_present(self):
        geos = {entry["geo"] for entry in self.bias.values()}
        self.assertGreaterEqual(len(geos), 5, f"Only {len(geos)} clusters: {geos}")


if __name__ == "__main__":
    unittest.main()
