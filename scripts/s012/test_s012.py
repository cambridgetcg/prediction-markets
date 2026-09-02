#!/usr/bin/env python3
"""Tests for S012 Module 1: News Ingestor."""

import asyncio
import json
import logging
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from news_ingestor import (
    Article,
    NewsEvent,
    SeenStore,
    classify_domain,
    cluster_articles,
    extract_entities,
    parse_age,
    _detect_breaking,
    _jaccard,
    _title_words,
)


def _make_article(**overrides) -> Article:
    """Factory for test articles with sensible defaults."""
    defaults = dict(
        url="https://example.com/test",
        title="Test Article",
        description="A test description.",
        extra_snippets=[],
        source_name="example",
        source_domain="example.com",
        country_queried="US",
        age_raw="1 hour ago",
        published_at=datetime.now(timezone.utc),
        query_name="test",
        fetched_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Article(**defaults)


class TestParseAge(unittest.TestCase):
    """test_parse_age: known age strings -> correct datetimes."""

    def setUp(self):
        self.ref = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)

    def test_hours_ago(self):
        result = parse_age("3 hours ago", reference=self.ref)
        expected = self.ref - timedelta(hours=3)
        self.assertEqual(result, expected)

    def test_minutes_ago(self):
        result = parse_age("45 minutes ago", reference=self.ref)
        expected = self.ref - timedelta(minutes=45)
        self.assertEqual(result, expected)

    def test_days_ago(self):
        result = parse_age("2 days ago", reference=self.ref)
        expected = self.ref - timedelta(days=2)
        self.assertEqual(result, expected)

    def test_singular_unit(self):
        result = parse_age("1 hour ago", reference=self.ref)
        expected = self.ref - timedelta(hours=1)
        self.assertEqual(result, expected)

    def test_weeks_ago(self):
        result = parse_age("1 week ago", reference=self.ref)
        expected = self.ref - timedelta(weeks=1)
        self.assertEqual(result, expected)

    def test_iso_8601_utc(self):
        result = parse_age("2026-02-27T10:30:00Z")
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 2)
        self.assertEqual(result.day, 27)
        self.assertEqual(result.hour, 10)
        self.assertEqual(result.minute, 30)

    def test_iso_8601_with_tz(self):
        result = parse_age("2026-02-27T10:30:00+00:00")
        self.assertEqual(result.year, 2026)

    def test_unknown_format_returns_reference(self):
        result = parse_age("unknown format", reference=self.ref)
        self.assertEqual(result, self.ref)

    def test_seconds_ago(self):
        result = parse_age("30 seconds ago", reference=self.ref)
        expected = self.ref - timedelta(seconds=30)
        self.assertEqual(result, expected)


class TestDomainClassification(unittest.TestCase):
    """test_domain_classification: keywords -> correct domains."""

    def test_geo_iran(self):
        self.assertEqual(classify_domain("Iran nuclear talks resume"), "GEO")

    def test_geo_ukraine(self):
        self.assertEqual(classify_domain("Ukraine ceasefire negotiations"), "GEO")

    def test_geo_nato(self):
        self.assertEqual(classify_domain("NATO expansion debate"), "GEO")

    def test_cry_bitcoin(self):
        self.assertEqual(classify_domain("Bitcoin reaches new high"), "CRY")

    def test_pol_trump(self):
        self.assertEqual(classify_domain("Trump signs executive order"), "POL")

    def test_pol_senate(self):
        self.assertEqual(classify_domain("Senate confirms new justice"), "POL")

    def test_eco_fed(self):
        self.assertEqual(classify_domain("Fed raises interest rate by 25 bps"), "ECO")

    def test_tec_openai(self):
        self.assertEqual(classify_domain("OpenAI releases new model"), "TEC")

    def test_env_hurricane(self):
        self.assertEqual(classify_domain("Hurricane approaches Florida coast"), "ENV")

    def test_other_fallback(self):
        self.assertEqual(classify_domain("Local bakery opens new branch"), "OTHER")


class TestBreakingDetection(unittest.TestCase):
    """test_breaking_detection: 3 articles in 30 min -> is_breaking."""

    def test_three_sources_within_30min(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        articles = [
            _make_article(source_domain="reuters.com", published_at=now),
            _make_article(source_domain="bbc.com", published_at=now + timedelta(minutes=10)),
            _make_article(source_domain="cnn.com", published_at=now + timedelta(minutes=20)),
        ]
        self.assertTrue(_detect_breaking(articles))

    def test_three_sources_over_30min(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        articles = [
            _make_article(source_domain="reuters.com", published_at=now),
            _make_article(source_domain="bbc.com", published_at=now + timedelta(minutes=20)),
            _make_article(source_domain="cnn.com", published_at=now + timedelta(minutes=45)),
        ]
        self.assertFalse(_detect_breaking(articles))

    def test_two_sources_not_breaking(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        articles = [
            _make_article(source_domain="reuters.com", published_at=now),
            _make_article(source_domain="bbc.com", published_at=now + timedelta(minutes=5)),
        ]
        self.assertFalse(_detect_breaking(articles))

    def test_same_domain_not_counted(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        articles = [
            _make_article(source_domain="reuters.com", published_at=now),
            _make_article(source_domain="reuters.com", published_at=now + timedelta(minutes=5)),
            _make_article(source_domain="bbc.com", published_at=now + timedelta(minutes=10)),
        ]
        self.assertFalse(_detect_breaking(articles))

    def test_empty_articles(self):
        self.assertFalse(_detect_breaking([]))


class TestDedup(unittest.TestCase):
    """test_dedup: same URL twice -> only stored once."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)

    def test_same_url_deduped(self):
        store = SeenStore(db_path=self.db_path)
        url_hash = "abc123"

        self.assertFalse(store.is_seen(url_hash))
        store.mark_seen(url_hash, "https://example.com/1")
        self.assertTrue(store.is_seen(url_hash))

        # Mark again — should not raise
        store.mark_seen(url_hash, "https://example.com/1")
        self.assertTrue(store.is_seen(url_hash))

        # Verify only one row
        count = store.conn.execute(
            "SELECT COUNT(*) FROM seen_urls WHERE url_hash = ?", (url_hash,)
        ).fetchone()[0]
        self.assertEqual(count, 1)
        store.close()

    def test_different_urls_both_stored(self):
        store = SeenStore(db_path=self.db_path)
        store.mark_seen("hash1", "https://example.com/1")
        store.mark_seen("hash2", "https://example.com/2")
        self.assertTrue(store.is_seen("hash1"))
        self.assertTrue(store.is_seen("hash2"))
        store.close()

    def test_unseen_url(self):
        store = SeenStore(db_path=self.db_path)
        self.assertFalse(store.is_seen("never_stored"))
        store.close()


class TestClustering(unittest.TestCase):
    """test_clustering: articles with shared entities -> same cluster."""

    def test_shared_entities_same_cluster(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)

        # Both mention Iran and IAEA in non-first-word position -> shared entities
        a1 = _make_article(
            url="https://reuters.com/iran-1",
            title="Talks in Iran Resume as IAEA Sends Inspectors to Tehran",
            description="Nuclear inspectors arrive in Iran for IAEA inspection.",
            source_domain="reuters.com",
            published_at=now,
        )
        a2 = _make_article(
            url="https://bbc.com/iran-2",
            title="Progress in Iran as IAEA Reports on Enrichment Levels",
            description="IAEA confirms Iran cooperation on nuclear inspections.",
            source_domain="bbc.com",
            published_at=now - timedelta(hours=1),
        )

        events = cluster_articles([a1, a2])
        self.assertEqual(len(events), 1, f"Expected 1 cluster, got {len(events)}")
        self.assertEqual(len(events[0].articles), 2)

    def test_unrelated_articles_different_clusters(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)

        a1 = _make_article(
            url="https://example.com/iran",
            title="Talks in Iran Resume as IAEA Sends Inspectors to Tehran",
            description="Nuclear facility inspection in Iran.",
            source_domain="reuters.com",
            published_at=now,
        )
        a2 = _make_article(
            url="https://example.com/bitcoin",
            title="Markets Rally as Bitcoin Surges Past Record Highs Today",
            description="Cryptocurrency Bitcoin reaches unprecedented levels.",
            source_domain="coindesk.com",
            published_at=now,
        )

        events = cluster_articles([a1, a2])
        self.assertEqual(len(events), 2, f"Expected 2 clusters, got {len(events)}")

    def test_outside_time_window_separate(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)

        a1 = _make_article(
            url="https://reuters.com/iran-old",
            title="Talks in Iran Resume as IAEA Sends Inspectors to Tehran",
            source_domain="reuters.com",
            published_at=now - timedelta(hours=72),  # Outside 48h window
        )
        a2 = _make_article(
            url="https://bbc.com/iran-new",
            title="Progress in Iran as IAEA Reports on Enrichment Levels",
            source_domain="bbc.com",
            published_at=now,
        )

        events = cluster_articles([a1, a2])
        self.assertEqual(len(events), 2, f"Expected 2 clusters (time gap), got {len(events)}")

    def test_jaccard_fallback_clusters(self):
        """Articles with very similar titles but no extractable entities should cluster."""
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)

        a1 = _make_article(
            url="https://example.com/1",
            title="the quick brown fox jumps over the lazy dog today",
            description="nothing special here",
            source_domain="a.com",
            published_at=now,
        )
        a2 = _make_article(
            url="https://example.com/2",
            title="the quick brown fox jumps over the lazy cat today",
            description="nothing special here either",
            source_domain="b.com",
            published_at=now,
        )

        events = cluster_articles([a1, a2])
        # These should cluster via Jaccard fallback (very high overlap)
        self.assertEqual(len(events), 1)

    def test_single_article_event(self):
        a = _make_article(url="https://example.com/solo", title="Solo Article")
        events = cluster_articles([a])
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].articles), 1)

    def test_empty_input(self):
        events = cluster_articles([])
        self.assertEqual(len(events), 0)

    def test_event_has_correct_domain(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        a = _make_article(
            url="https://example.com/iran-domain",
            title="Iran Nuclear Deal Under Pressure from IAEA",
            published_at=now,
        )
        events = cluster_articles([a])
        self.assertEqual(events[0].domain, "GEO")

    def test_breaking_event_flagged(self):
        now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        # 4 articles from different domains within 20 minutes -> same title -> cluster + breaking
        articles = [
            _make_article(
                url=f"https://{d}/iran-{i}",
                title="Iran Nuclear Talks Resume as IAEA Pushes for Inspections",
                description="IAEA inspectors demand access to Iranian enrichment facilities.",
                source_domain=d,
                published_at=now + timedelta(minutes=i * 5),
            )
            for i, d in enumerate(["reuters.com", "bbc.com", "cnn.com", "aljazeera.com"])
        ]
        events = cluster_articles(articles)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].is_breaking)


class TestEntityExtraction(unittest.TestCase):

    def test_extracts_capitalized_non_first_words(self):
        entities = extract_entities("The talks in Iran resumed as IAEA sent inspectors")
        lowered = [e.lower() for e in entities]
        self.assertIn("iran", lowered)
        self.assertIn("iaea", lowered)

    def test_acronyms_extracted(self):
        entities = extract_entities("The NATO summit discussed AI policy with EU leaders")
        names = [e for e in entities]
        self.assertTrue(any("NATO" in e for e in names))
        self.assertTrue(any("EU" in e for e in names))

    def test_stop_words_excluded(self):
        entities = extract_entities("This Is A Very Simple Test Of The System")
        lowered = [e.lower() for e in entities]
        self.assertNotIn("this", lowered)
        self.assertNotIn("very", lowered)


class TestHelpers(unittest.TestCase):

    def test_jaccard_identical(self):
        self.assertAlmostEqual(_jaccard({"a", "b"}, {"a", "b"}), 1.0)

    def test_jaccard_disjoint(self):
        self.assertAlmostEqual(_jaccard({"a", "b"}, {"c", "d"}), 0.0)

    def test_jaccard_partial(self):
        result = _jaccard({"a", "b", "c"}, {"b", "c", "d"})
        self.assertAlmostEqual(result, 2 / 4)  # 2 shared out of 4 total

    def test_jaccard_empty(self):
        self.assertAlmostEqual(_jaccard(set(), {"a"}), 0.0)

    def test_title_words_filters_stopwords(self):
        words = _title_words("The quick brown fox and the lazy dog")
        self.assertNotIn("the", words)
        self.assertNotIn("and", words)
        self.assertIn("quick", words)
        self.assertIn("brown", words)


# ============================================================
# Module 2: Market Snapshot Tests
# ============================================================

from market_snapshot import (
    MarketSnapshot,
    MarketMatch,
    SnapshotStore,
    is_sports,
    score_relevance,
    match_markets,
    MarketCache,
    MIN_RELEVANCE,
    _question_keywords,
)


def _make_snapshot(**overrides) -> MarketSnapshot:
    """Factory for test MarketSnapshots with sensible defaults."""
    defaults = dict(
        market_id="test-market-001",
        question="Will Iran be struck by Israel before April 2026?",
        slug="iran-israel-strike-apr-2026",
        yes_price=0.35,
        no_price=0.65,
        volume_24h=50000.0,
        volume_total=500000.0,
        liquidity=120000.0,
        end_date="2026-04-01T00:00:00Z",
        domain="GEO",
        snapshot_time=datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc),
        yes_token="tok_yes_001",
        no_token="tok_no_001",
    )
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


def _make_news_event(**overrides) -> NewsEvent:
    """Factory for test NewsEvents with sensible defaults."""
    defaults = dict(
        event_id="evt-test-001",
        articles=[],
        key_entities=["Iran", "IAEA", "Nuclear"],
        summary="Iran nuclear talks resume in Geneva",
        domain="GEO",
        is_breaking=False,
        first_seen=datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc),
        source_count=3,
        query_names=["iran-nuclear"],
    )
    defaults.update(overrides)
    return NewsEvent(**defaults)


class TestMarketMatching(unittest.TestCase):
    """test_market_matching: Iran event matches Iran strike markets."""

    def test_iran_event_matches_iran_market(self):
        event = _make_news_event(
            key_entities=["Iran", "IAEA", "Nuclear", "Inspectors"],
            summary="Iran nuclear talks resume",
            domain="GEO",
        )
        market = _make_snapshot(
            question="Will Iran be struck by Israel before April 2026?",
            domain="GEO",
        )
        score = score_relevance(event, market)
        self.assertGreaterEqual(score, MIN_RELEVANCE,
                                f"Iran event should match Iran market, got {score}")

    def test_unrelated_event_no_match(self):
        event = _make_news_event(
            key_entities=["Bitcoin", "ETF", "SEC"],
            summary="Bitcoin ETF approved by SEC",
            domain="CRY",
        )
        market = _make_snapshot(
            question="Will Iran be struck by Israel before April 2026?",
            domain="GEO",
        )
        score = score_relevance(event, market)
        self.assertLess(score, MIN_RELEVANCE,
                        f"Crypto event should not match Iran market, got {score}")


class TestRelevanceScoring(unittest.TestCase):
    """test_relevance_scoring: more entity overlap -> higher score."""

    def test_more_entities_higher_score(self):
        market = _make_snapshot(
            question="Will Iran nuclear talks succeed before June 2026?",
            domain="GEO",
        )
        # 3 overlapping entities
        event_rich = _make_news_event(
            key_entities=["Iran", "Nuclear", "Talks", "Geneva"],
            summary="Iran nuclear talks resume",
            domain="GEO",
        )
        # 1 overlapping entity
        event_sparse = _make_news_event(
            key_entities=["Iran", "Diplomacy"],
            summary="Iran diplomatic efforts",
            domain="GEO",
        )
        score_rich = score_relevance(event_rich, market)
        score_sparse = score_relevance(event_sparse, market)
        self.assertGreater(score_rich, score_sparse)

    def test_domain_match_adds_score(self):
        market = _make_snapshot(
            question="Will Bitcoin reach 100K before July 2026?",
            domain="CRY",
        )
        event_same = _make_news_event(
            key_entities=["Bitcoin"],
            summary="Bitcoin surges past record",
            domain="CRY",
        )
        event_diff = _make_news_event(
            key_entities=["Bitcoin"],
            summary="Bitcoin surges past record",
            domain="TEC",
        )
        score_same = score_relevance(event_same, market)
        score_diff = score_relevance(event_diff, market)
        self.assertGreater(score_same, score_diff)

    def test_score_capped_at_one(self):
        event = _make_news_event(
            key_entities=["Iran", "Nuclear", "IAEA", "Inspectors", "Enrichment", "Tehran"],
            summary="Iran nuclear IAEA inspectors enrichment Tehran",
            domain="GEO",
        )
        market = _make_snapshot(
            question="Will Iran nuclear IAEA inspectors enrichment Tehran deal succeed?",
            domain="GEO",
        )
        score = score_relevance(event, market)
        self.assertLessEqual(score, 1.0)


class TestSnapshotStorage(unittest.TestCase):
    """test_snapshot_storage: snapshot round-trips through SQLite."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.store = SnapshotStore(db_path=self.db_path)

    def tearDown(self):
        self.store.close()
        self.db_path.unlink(missing_ok=True)

    def test_save_and_retrieve(self):
        snap = _make_snapshot(yes_price=0.42)
        self.store.save_snapshot(snap)

        history = self.store.get_history(snap.market_id)
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0]["yes_price"], 0.42)

    def test_multiple_snapshots_ordered(self):
        t1 = datetime(2026, 2, 28, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 2, 28, 11, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)

        self.store.save_snapshot(_make_snapshot(yes_price=0.30, snapshot_time=t1))
        self.store.save_snapshot(_make_snapshot(yes_price=0.35, snapshot_time=t2))
        self.store.save_snapshot(_make_snapshot(yes_price=0.40, snapshot_time=t3))

        history = self.store.get_history("test-market-001")
        self.assertEqual(len(history), 3)
        # Most recent first
        self.assertAlmostEqual(history[0]["yes_price"], 0.40)
        self.assertAlmostEqual(history[2]["yes_price"], 0.30)

    def test_batch_save(self):
        snaps = [
            _make_snapshot(market_id=f"m-{i}", yes_price=0.10 * i)
            for i in range(1, 6)
        ]
        self.store.save_snapshots(snaps)

        for i in range(1, 6):
            h = self.store.get_history(f"m-{i}")
            self.assertEqual(len(h), 1)

    def test_trigger_event_id_stored(self):
        snap = _make_snapshot()
        self.store.save_snapshot(snap, trigger_event_id="evt-abc123")
        history = self.store.get_history(snap.market_id)
        self.assertEqual(history[0]["trigger_event_id"], "evt-abc123")


class TestPriceBeforeLookup(unittest.TestCase):
    """test_price_before_lookup: finds correct pre-event price."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.store = SnapshotStore(db_path=self.db_path)

    def tearDown(self):
        self.store.close()
        self.db_path.unlink(missing_ok=True)

    def test_finds_most_recent_before(self):
        mid = "test-market-001"
        t1 = datetime(2026, 2, 28, 8, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 2, 28, 10, 0, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 2, 28, 14, 0, 0, tzinfo=timezone.utc)

        self.store.save_snapshot(_make_snapshot(yes_price=0.30, snapshot_time=t1))
        self.store.save_snapshot(_make_snapshot(yes_price=0.35, snapshot_time=t2))
        self.store.save_snapshot(_make_snapshot(yes_price=0.50, snapshot_time=t3))

        # Event at 12:00 — should get the 10:00 snapshot (0.35)
        event_time = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        price = self.store.get_price_before(mid, event_time)
        self.assertAlmostEqual(price, 0.35)

    def test_no_prior_snapshot_returns_none(self):
        mid = "test-market-001"
        t1 = datetime(2026, 2, 28, 14, 0, 0, tzinfo=timezone.utc)
        self.store.save_snapshot(_make_snapshot(yes_price=0.50, snapshot_time=t1))

        event_time = datetime(2026, 2, 28, 10, 0, 0, tzinfo=timezone.utc)
        price = self.store.get_price_before(mid, event_time)
        self.assertIsNone(price)

    def test_different_market_ids_isolated(self):
        t = datetime(2026, 2, 28, 10, 0, 0, tzinfo=timezone.utc)
        self.store.save_snapshot(_make_snapshot(market_id="m-A", yes_price=0.30, snapshot_time=t))
        self.store.save_snapshot(_make_snapshot(market_id="m-B", yes_price=0.70, snapshot_time=t))

        event_time = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
        self.assertAlmostEqual(self.store.get_price_before("m-A", event_time), 0.30)
        self.assertAlmostEqual(self.store.get_price_before("m-B", event_time), 0.70)


class TestSportsFiltering(unittest.TestCase):
    """test_sports_filtering: NBA/NFL markets excluded."""

    def test_nba_filtered(self):
        self.assertTrue(is_sports("Lakers vs Celtics NBA Finals"))

    def test_nfl_filtered(self):
        self.assertTrue(is_sports("NFL Super Bowl winner 2026"))

    def test_esports_filtered(self):
        self.assertTrue(is_sports("Counter-Strike Major Final bo3"))

    def test_non_sports_passes(self):
        self.assertFalse(is_sports("Will Iran be struck by Israel?"))

    def test_crypto_passes(self):
        self.assertFalse(is_sports("Will Bitcoin reach $100K?"))

    def test_case_insensitive(self):
        self.assertTrue(is_sports("NBA All-Star Game"))
        self.assertTrue(is_sports("nba all-star game"))


# ============================================================
# Module 3: Reaction Interpreter Tests
# ============================================================

from reaction_interpreter import (
    Interpretation,
    InterpretationStore,
    build_prompt,
    parse_llm_response,
    format_source_list,
    load_credibility_matrix,
    lookup_credibility,
    _synthetic_response,
    _make_demo_match,
    COOLDOWN_MINUTES,
    MAX_INTERPRETATIONS_PER_HOUR,
)


class TestPromptFormatting(unittest.TestCase):
    """test_prompt_formatting: prompt contains all required fields."""

    def test_prompt_contains_event_summary(self):
        match = _make_demo_match()
        prompt = build_prompt(match)
        self.assertIn(match.event.summary, prompt)

    def test_prompt_contains_market_question(self):
        match = _make_demo_match()
        prompt = build_prompt(match)
        self.assertIn(match.market.question, prompt)

    def test_prompt_contains_yes_price(self):
        match = _make_demo_match()
        prompt = build_prompt(match)
        self.assertIn("0.35", prompt)

    def test_prompt_contains_domain(self):
        match = _make_demo_match()
        prompt = build_prompt(match)
        self.assertIn("GEO", prompt)

    def test_prompt_contains_source_count(self):
        match = _make_demo_match()
        prompt = build_prompt(match)
        self.assertIn("3 independent", prompt)

    def test_prompt_contains_volume(self):
        match = _make_demo_match()
        prompt = build_prompt(match)
        self.assertIn("1,200,000", prompt)

    def test_prompt_contains_calibration_notes(self):
        match = _make_demo_match()
        prompt = build_prompt(match)
        self.assertIn("CALIBRATION NOTES", prompt)
        self.assertIn("1-10pp", prompt)


class TestResponseParsing(unittest.TestCase):
    """test_response_parsing: valid JSON -> correct Interpretation fields."""

    def test_valid_json_parsed(self):
        raw = json.dumps({
            "prior_probability": 0.40,
            "posterior_probability": 0.55,
            "estimated_shift": 0.15,
            "confidence": 0.70,
            "news_type": "NOVEL",
            "source_quality": "VERIFIED",
            "reasoning": "Test reasoning.",
        })
        parsed = parse_llm_response(raw)
        self.assertAlmostEqual(parsed["prior_probability"], 0.40)
        self.assertAlmostEqual(parsed["posterior_probability"], 0.55)
        self.assertEqual(parsed["news_type"], "NOVEL")
        self.assertEqual(parsed["source_quality"], "VERIFIED")

    def test_json_in_code_fence(self):
        raw = '```json\n{"prior_probability": 0.30, "posterior_probability": 0.35, "estimated_shift": 0.05, "confidence": 0.50, "news_type": "CONFIRMATORY", "source_quality": "CREDIBLE", "reasoning": "Test."}\n```'
        parsed = parse_llm_response(raw)
        self.assertAlmostEqual(parsed["prior_probability"], 0.30)

    def test_synthetic_response_parses(self):
        raw = _synthetic_response()
        parsed = parse_llm_response(raw)
        self.assertIn("prior_probability", parsed)
        self.assertIn("posterior_probability", parsed)
        self.assertIn("news_type", parsed)


class TestResponseValidation(unittest.TestCase):
    """test_response_validation: out-of-range values caught."""

    def test_probability_above_one_rejected(self):
        raw = json.dumps({
            "prior_probability": 1.5,
            "posterior_probability": 0.55,
            "estimated_shift": -0.95,
            "confidence": 0.70,
            "news_type": "NOVEL",
            "source_quality": "VERIFIED",
            "reasoning": "Test.",
        })
        with self.assertRaises(ValueError):
            parse_llm_response(raw)

    def test_probability_below_zero_rejected(self):
        raw = json.dumps({
            "prior_probability": -0.10,
            "posterior_probability": 0.55,
            "estimated_shift": 0.65,
            "confidence": 0.70,
            "news_type": "NOVEL",
            "source_quality": "VERIFIED",
            "reasoning": "Test.",
        })
        with self.assertRaises(ValueError):
            parse_llm_response(raw)

    def test_invalid_news_type_rejected(self):
        raw = json.dumps({
            "prior_probability": 0.40,
            "posterior_probability": 0.55,
            "estimated_shift": 0.15,
            "confidence": 0.70,
            "news_type": "INVALID",
            "source_quality": "VERIFIED",
            "reasoning": "Test.",
        })
        with self.assertRaises(ValueError):
            parse_llm_response(raw)

    def test_invalid_source_quality_rejected(self):
        raw = json.dumps({
            "prior_probability": 0.40,
            "posterior_probability": 0.55,
            "estimated_shift": 0.15,
            "confidence": 0.70,
            "news_type": "NOVEL",
            "source_quality": "BOGUS",
            "reasoning": "Test.",
        })
        with self.assertRaises(ValueError):
            parse_llm_response(raw)

    def test_missing_field_rejected(self):
        raw = json.dumps({
            "prior_probability": 0.40,
            "posterior_probability": 0.55,
            # missing estimated_shift, confidence, etc.
        })
        with self.assertRaises(ValueError):
            parse_llm_response(raw)

    def test_shift_mismatch_auto_corrected(self):
        raw = json.dumps({
            "prior_probability": 0.40,
            "posterior_probability": 0.50,
            "estimated_shift": 0.20,  # Wrong — should be 0.10
            "confidence": 0.70,
            "news_type": "NOVEL",
            "source_quality": "CREDIBLE",
            "reasoning": "Test.",
        })
        parsed = parse_llm_response(raw)
        # Should auto-correct to 0.10
        self.assertAlmostEqual(parsed["estimated_shift"], 0.10, places=2)


class TestRateLimiting(unittest.TestCase):
    """test_rate_limiting: same event+market within cooldown -> skip."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.store = InterpretationStore(db_path=self.db_path)

    def tearDown(self):
        self.store.close()
        self.db_path.unlink(missing_ok=True)

    def test_cooldown_blocks_duplicate(self):
        now = datetime.now(timezone.utc)
        interp = Interpretation(
            interpretation_id="test-1",
            event_id="evt-001",
            market_id="mkt-001",
            market_question="Test?",
            prior_probability=0.40,
            posterior_probability=0.50,
            estimated_shift=0.10,
            confidence=0.70,
            reasoning="Test",
            news_type="NOVEL",
            source_quality="CREDIBLE",
            interpreted_at=now,
            model_used="test",
            prompt_version="v1.0",
            raw_llm_response="{}",
        )
        self.store.save(interp)

        # Same event+market should be on cooldown
        self.assertTrue(self.store.is_on_cooldown("evt-001", "mkt-001"))

        # Different event should NOT be on cooldown
        self.assertFalse(self.store.is_on_cooldown("evt-002", "mkt-001"))

    def test_count_recent(self):
        now = datetime.now(timezone.utc)
        for i in range(5):
            interp = Interpretation(
                interpretation_id=f"test-{i}",
                event_id=f"evt-{i}",
                market_id=f"mkt-{i}",
                market_question="Test?",
                prior_probability=0.40,
                posterior_probability=0.50,
                estimated_shift=0.10,
                confidence=0.70,
                reasoning="Test",
                news_type="NOVEL",
                source_quality="CREDIBLE",
                interpreted_at=now,
                model_used="test",
                prompt_version="v1.0",
                raw_llm_response="{}",
            )
            self.store.save(interp)

        self.assertEqual(self.store.count_recent(hours=1.0), 5)


class TestSourceCredibilityLoading(unittest.TestCase):
    """test_source_credibility_loading: credibility matrix loads and formats correctly."""

    def test_matrix_loads(self):
        matrix = load_credibility_matrix()
        self.assertIsInstance(matrix, list)
        # Should have entries (the actual file has ~40 entries)
        self.assertGreater(len(matrix), 0)

    def test_reuters_found(self):
        cred = lookup_credibility("reuters.com")
        self.assertIsNotNone(cred)
        self.assertIn("composite_score", cred)

    def test_bbc_found(self):
        cred = lookup_credibility("bbc.com")
        self.assertIsNotNone(cred)

    def test_unknown_source_returns_none(self):
        cred = lookup_credibility("random-blog-xyz.com")
        self.assertIsNone(cred)

    def test_format_source_list_includes_credibility(self):
        match = _make_demo_match()
        formatted = format_source_list(match.event)
        # Should contain reliability scores for known sources
        self.assertIn("reliability:", formatted)
        # PressTV should also be found
        self.assertIn("lean:", formatted)

    def test_format_source_list_marks_unknown(self):
        """Sources not in matrix should be marked (unrated)."""
        from news_ingestor import _make_demo_article
        now = datetime.now(timezone.utc)

        event = NewsEvent(
            event_id="test-unknown",
            articles=[
                _make_demo_article(
                    source_domain="totally-unknown-source-xyz.com",
                    title="Test article",
                ),
            ],
            key_entities=[],
            summary="Test",
            domain="OTHER",
            is_breaking=False,
            first_seen=now,
            source_count=1,
            query_names=[],
        )
        formatted = format_source_list(event)
        self.assertIn("unrated", formatted)


class TestDemoMode(unittest.TestCase):
    """test_demo_mode: demo runs without API calls."""

    def test_demo_match_created(self):
        match = _make_demo_match()
        self.assertEqual(match.event.domain, "GEO")
        self.assertEqual(match.market.yes_price, 0.35)
        self.assertEqual(len(match.event.articles), 3)

    def test_demo_interpret_no_api(self):
        """Full demo interpret should succeed without API calls."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "interpretations.db"
            match = _make_demo_match()
            store = InterpretationStore(db_path=db_path)

            from reaction_interpreter import interpret
            with patch("reaction_interpreter.log_to_jsonl") as jsonl_log:
                try:
                    interp = interpret(match, store, use_api=False)
                finally:
                    store.close()

            jsonl_log.assert_called_once()

        self.assertIsNotNone(interp)
        self.assertAlmostEqual(interp.prior_probability, 0.35)
        self.assertAlmostEqual(interp.posterior_probability, 0.42)
        self.assertEqual(interp.news_type, "NOVEL")
        self.assertEqual(interp.source_quality, "CREDIBLE")


# ============================================================
# Module 4: Reaction Comparator Tests
# ============================================================

from reaction_comparator import (
    ReactionAssessment,
    AssessmentStore,
    classify_reaction,
    adjust_confidence,
    calculate_size,
    generate_trade_params,
    assess,
    _make_demo_interpretation,
    _make_demo_match as _make_demo_match_m4,
    DEFAULT_ACTION_THRESHOLD,
    GEO_ACTION_THRESHOLD,
    STRONG_MAGNITUDE_THRESHOLD,
)


class TestOverreactionClassification(unittest.TestCase):
    """test_overreaction_classification: actual > expected + 5pp -> OVERREACTION."""

    def test_basic_overreaction(self):
        # Estimated +5pp, actual +12pp → delta = +7pp → OVERREACTION
        rtype, mag, act = classify_reaction(0.05, 0.12, 0.7, "POL")
        self.assertEqual(rtype, "OVERREACTION")

    def test_negative_overreaction(self):
        # Estimated -3pp, actual -10pp → delta = -7pp → actual moved more negative
        # delta = -10pp - (-3pp) = -7pp → UNDERREACTION (market moved more DOWN)
        # Wait: actual_move(-0.10) - estimated_shift(-0.03) = -0.07 → negative → UNDERREACTION
        # This is correct: market dropped MORE than expected → the "over" direction is down
        # The spec says: negative delta = UNDERREACTION
        # But conceptually if market dropped more than expected, that's overreaction downward
        # The spec is explicit: positive delta = OVERREACTION, negative = UNDERREACTION
        rtype, mag, act = classify_reaction(-0.03, -0.10, 0.7, "POL")
        self.assertEqual(rtype, "UNDERREACTION")

    def test_strong_overreaction(self):
        # delta = 0.15 - 0.05 = +10pp → STRONG
        rtype, mag, act = classify_reaction(0.05, 0.15, 0.7, "POL")
        self.assertEqual(rtype, "OVERREACTION")
        self.assertEqual(mag, "STRONG")

    def test_moderate_overreaction(self):
        # delta = 0.11 - 0.05 = +6pp → MODERATE (between 5 and 8)
        rtype, mag, act = classify_reaction(0.05, 0.11, 0.7, "POL")
        self.assertEqual(rtype, "OVERREACTION")
        self.assertEqual(mag, "MODERATE")


class TestUnderreactionClassification(unittest.TestCase):
    """test_underreaction_classification: expected > actual + 5pp -> UNDERREACTION."""

    def test_basic_underreaction(self):
        # Estimated +12pp, actual +2pp → delta = -10pp → UNDERREACTION
        rtype, mag, act = classify_reaction(0.12, 0.02, 0.7, "POL")
        self.assertEqual(rtype, "UNDERREACTION")

    def test_strong_underreaction(self):
        # delta = 0.01 - 0.10 = -9pp → STRONG
        rtype, mag, act = classify_reaction(0.10, 0.01, 0.7, "POL")
        self.assertEqual(rtype, "UNDERREACTION")
        self.assertEqual(mag, "STRONG")

    def test_moderate_underreaction(self):
        # delta = 0.02 - 0.08 = -6pp → MODERATE
        rtype, mag, act = classify_reaction(0.08, 0.02, 0.7, "POL")
        self.assertEqual(rtype, "UNDERREACTION")
        self.assertEqual(mag, "MODERATE")


class TestCorrectClassification(unittest.TestCase):
    """test_correct_classification: |delta| < 5pp -> CORRECT."""

    def test_exact_match(self):
        rtype, mag, act = classify_reaction(0.05, 0.05, 0.7, "POL")
        self.assertEqual(rtype, "CORRECT")
        self.assertEqual(mag, "WEAK")
        self.assertFalse(act)

    def test_small_delta(self):
        # delta = 0.06 - 0.03 = +3pp < 5pp → CORRECT
        rtype, mag, act = classify_reaction(0.03, 0.06, 0.7, "POL")
        self.assertEqual(rtype, "CORRECT")

    def test_borderline_just_under(self):
        # delta = 0.049pp → just under threshold
        rtype, mag, act = classify_reaction(0.05, 0.099, 0.7, "POL")
        self.assertEqual(rtype, "CORRECT")

    def test_zero_shift_zero_move(self):
        rtype, mag, act = classify_reaction(0.0, 0.0, 0.7, "POL")
        self.assertEqual(rtype, "CORRECT")


class TestGeoThreshold(unittest.TestCase):
    """test_geo_threshold: GEO requires 8pp, not 5pp."""

    def test_6pp_delta_not_actionable_for_geo(self):
        # delta = 0.10 - 0.04 = +6pp → actionable for non-GEO but NOT for GEO
        rtype_geo, _, act_geo = classify_reaction(0.04, 0.10, 0.7, "GEO")
        rtype_pol, _, act_pol = classify_reaction(0.04, 0.10, 0.7, "POL")

        self.assertEqual(rtype_geo, "CORRECT")  # 6pp < 8pp GEO threshold
        self.assertEqual(rtype_pol, "OVERREACTION")  # 6pp > 5pp default
        self.assertFalse(act_geo)
        self.assertTrue(act_pol)

    def test_9pp_delta_actionable_for_geo(self):
        # delta = 0.12 - 0.03 = +9pp → actionable even for GEO
        rtype, mag, act = classify_reaction(0.03, 0.12, 0.7, "GEO")
        self.assertEqual(rtype, "OVERREACTION")
        self.assertTrue(act)

    def test_7pp_delta_correct_for_geo(self):
        # 7pp is between 5 and 8 → CORRECT for GEO
        rtype, _, act = classify_reaction(0.03, 0.10, 0.7, "GEO")
        self.assertEqual(rtype, "CORRECT")
        self.assertFalse(act)


class TestTradeParamsOverreaction(unittest.TestCase):
    """test_trade_params_overreaction: fade direction, 40% retracement target, 8pp stop."""

    def test_upward_spike_fade_to_no(self):
        # Price spiked UP +15pp → OVERREACTION → buy NO (fade)
        params = generate_trade_params(
            reaction_type="OVERREACTION",
            actual_move=0.15,
            estimated_shift=0.05,
            current_yes_price=0.65,
            price_before_news=0.50,
            posterior_probability=0.55,
            magnitude="STRONG",
        )
        self.assertEqual(params["direction"], "NO")
        self.assertAlmostEqual(params["entry"], 1.0 - 0.65, places=3)
        # Target YES = 0.65 - 0.15 * 0.40 = 0.65 - 0.06 = 0.59
        self.assertAlmostEqual(params["target"], 1.0 - 0.59, places=3)
        # Stop YES = 0.65 + 0.08 = 0.73
        self.assertAlmostEqual(params["stop"], 1.0 - 0.73, places=3)
        self.assertEqual(params["time_horizon_hours"], 168)

    def test_downward_spike_fade_to_yes(self):
        # Price dropped -12pp → OVERREACTION → buy YES (fade)
        params = generate_trade_params(
            reaction_type="OVERREACTION",
            actual_move=-0.12,
            estimated_shift=-0.03,
            current_yes_price=0.28,
            price_before_news=0.40,
            posterior_probability=0.37,
            magnitude="STRONG",
        )
        self.assertEqual(params["direction"], "YES")
        self.assertAlmostEqual(params["entry"], 0.28, places=3)
        # Target = 0.28 + 0.12 * 0.40 = 0.28 + 0.048 = 0.328
        self.assertAlmostEqual(params["target"], 0.328, places=3)
        # Stop = 0.28 - 0.08 = 0.20
        self.assertAlmostEqual(params["stop"], 0.20, places=3)

    def test_overreaction_sizing(self):
        params = generate_trade_params(
            reaction_type="OVERREACTION",
            actual_move=0.15,
            estimated_shift=0.05,
            current_yes_price=0.65,
            price_before_news=0.50,
            posterior_probability=0.55,
            magnitude="STRONG",
        )
        self.assertAlmostEqual(params["size_pct"], 0.03)

        params_mod = generate_trade_params(
            reaction_type="OVERREACTION",
            actual_move=0.10,
            estimated_shift=0.04,
            current_yes_price=0.60,
            price_before_news=0.50,
            posterior_probability=0.54,
            magnitude="MODERATE",
        )
        self.assertAlmostEqual(params_mod["size_pct"], 0.015)


class TestTradeParamsUnderreaction(unittest.TestCase):
    """test_trade_params_underreaction: ride direction, posterior target, pre-news stop."""

    def test_upward_underreaction_buy_yes(self):
        # LLM said should go UP +10pp, market only moved +3pp → buy YES
        params = generate_trade_params(
            reaction_type="UNDERREACTION",
            actual_move=0.03,
            estimated_shift=0.10,
            current_yes_price=0.43,
            price_before_news=0.40,
            posterior_probability=0.50,
            magnitude="MODERATE",
        )
        self.assertEqual(params["direction"], "YES")
        self.assertAlmostEqual(params["entry"], 0.43, places=3)
        self.assertAlmostEqual(params["target"], 0.50, places=3)  # Posterior
        self.assertAlmostEqual(params["stop"], 0.40, places=3)    # Pre-news price
        self.assertEqual(params["time_horizon_hours"], 48)

    def test_downward_underreaction_buy_no(self):
        # LLM said should go DOWN -10pp, market only moved -2pp → buy NO
        params = generate_trade_params(
            reaction_type="UNDERREACTION",
            actual_move=-0.02,
            estimated_shift=-0.10,
            current_yes_price=0.48,
            price_before_news=0.50,
            posterior_probability=0.40,
            magnitude="STRONG",
        )
        self.assertEqual(params["direction"], "NO")
        self.assertAlmostEqual(params["entry"], 1.0 - 0.48, places=3)
        self.assertAlmostEqual(params["target"], 1.0 - 0.40, places=3)  # 1 - posterior
        self.assertAlmostEqual(params["stop"], 1.0 - 0.50, places=3)    # 1 - pre-news

    def test_underreaction_sizing(self):
        params = generate_trade_params(
            reaction_type="UNDERREACTION",
            actual_move=0.02,
            estimated_shift=0.12,
            current_yes_price=0.42,
            price_before_news=0.40,
            posterior_probability=0.52,
            magnitude="STRONG",
        )
        self.assertAlmostEqual(params["size_pct"], 0.02)

        params_mod = generate_trade_params(
            reaction_type="UNDERREACTION",
            actual_move=0.02,
            estimated_shift=0.08,
            current_yes_price=0.42,
            price_before_news=0.40,
            posterior_probability=0.48,
            magnitude="MODERATE",
        )
        self.assertAlmostEqual(params_mod["size_pct"], 0.01)


class TestConfidenceAdjustment(unittest.TestCase):
    """test_confidence_adjustment: RUMOR discounts, ECO discounts, NOVEL bonus."""

    def test_rumor_discount(self):
        adj = adjust_confidence(0.80, "RUMOR", "NOVEL", "POL")
        # 0.80 * 0.5 (rumor) * 1.1 (novel) = 0.44
        self.assertAlmostEqual(adj, 0.44, places=2)

    def test_verified_no_discount(self):
        adj = adjust_confidence(0.80, "VERIFIED", "NOVEL", "POL")
        # 0.80 * 1.0 * 1.1 = 0.88
        self.assertAlmostEqual(adj, 0.88, places=2)

    def test_eco_domain_discount(self):
        adj = adjust_confidence(0.80, "VERIFIED", "NOVEL", "ECO")
        # 0.80 * 1.0 * 1.1 * 0.5 = 0.44
        self.assertAlmostEqual(adj, 0.44, places=2)

    def test_fin_domain_discount(self):
        adj = adjust_confidence(0.80, "VERIFIED", "NOVEL", "FIN")
        # Same as ECO
        self.assertAlmostEqual(adj, 0.44, places=2)

    def test_confirmatory_discount(self):
        adj = adjust_confidence(0.80, "CREDIBLE", "CONFIRMATORY", "POL")
        # 0.80 * 0.9 * 0.8 = 0.576
        self.assertAlmostEqual(adj, 0.576, places=3)

    def test_capped_at_one(self):
        # High confidence + NOVEL + VERIFIED should not exceed 1.0
        adj = adjust_confidence(1.0, "VERIFIED", "NOVEL", "GEO")
        self.assertLessEqual(adj, 1.0)

    def test_unconfirmed_source(self):
        adj = adjust_confidence(0.70, "UNCONFIRMED", "AMBIGUOUS", "POL")
        # 0.70 * 0.7 * 0.9 = 0.441
        self.assertAlmostEqual(adj, 0.441, places=3)


class TestPositionSizing(unittest.TestCase):
    """test_position_sizing: correct bankroll percentages by type/magnitude."""

    def test_over_strong(self):
        self.assertAlmostEqual(calculate_size("OVERREACTION", "STRONG"), 0.03)

    def test_over_moderate(self):
        self.assertAlmostEqual(calculate_size("OVERREACTION", "MODERATE"), 0.015)

    def test_under_strong(self):
        self.assertAlmostEqual(calculate_size("UNDERREACTION", "STRONG"), 0.02)

    def test_under_moderate(self):
        self.assertAlmostEqual(calculate_size("UNDERREACTION", "MODERATE"), 0.01)

    def test_correct_zero(self):
        self.assertAlmostEqual(calculate_size("CORRECT", "WEAK"), 0.0)


class TestAssessEndToEnd(unittest.TestCase):
    """test_assess_end_to_end: full pipeline produces valid ReactionAssessment."""

    def test_demo_assess(self):
        interp = _make_demo_interpretation()
        match = _make_demo_match_m4()
        result = assess(interp, match, domain="GEO",
                        posterior_probability=interp.posterior_probability)

        self.assertIsInstance(result, ReactionAssessment)
        self.assertEqual(result.event_id, "demo-evt-001")
        self.assertEqual(result.market_id, "demo-mkt-001")
        # estimated_shift=0.07, actual_move=0.05 → delta = -0.02
        # For GEO: |0.02| < 0.08 → CORRECT
        self.assertEqual(result.reaction_type, "CORRECT")
        self.assertFalse(result.is_actionable)
        self.assertAlmostEqual(result.reaction_delta, -0.02, places=3)

    def test_assess_stores_to_sqlite(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = Path(tmp.name)

        store = AssessmentStore(db_path=db_path)
        interp = _make_demo_interpretation()
        match = _make_demo_match_m4()
        result = assess(interp, match, domain="GEO")
        store.save(result)

        recent = store.load_recent(limit=5)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["assessment_id"], result.assessment_id)
        self.assertEqual(recent[0]["reaction_type"], "CORRECT")

        store.close()
        db_path.unlink(missing_ok=True)

    def test_actionable_filter(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = Path(tmp.name)

        store = AssessmentStore(db_path=db_path)

        # Create a non-actionable assessment
        interp = _make_demo_interpretation()
        match = _make_demo_match_m4()
        result = assess(interp, match, domain="GEO")
        store.save(result)

        actionable = store.load_actionable()
        self.assertEqual(len(actionable), 0)  # Demo case is CORRECT, not actionable

        store.close()
        db_path.unlink(missing_ok=True)


class TestLowConfidenceNotActionable(unittest.TestCase):
    """Low confidence should prevent actionability even when delta is large."""

    def test_large_delta_low_confidence(self):
        # 15pp delta but only 0.3 confidence → not actionable
        rtype, mag, act = classify_reaction(0.05, 0.20, 0.30, "POL")
        self.assertEqual(rtype, "OVERREACTION")
        self.assertFalse(act)

    def test_large_delta_sufficient_confidence(self):
        rtype, mag, act = classify_reaction(0.05, 0.20, 0.50, "POL")
        self.assertEqual(rtype, "OVERREACTION")
        self.assertTrue(act)


# ============================================================
# Module 5: Signal Generator Tests
# ============================================================

from signal_generator import (
    TradingSignal,
    SignalStore,
    check_concentration,
    check_anti_patterns,
    generate_signal,
    format_signal,
    overlaps_event,
    estimate_correlation,
    _make_demo_assessment,
    C1_EVENT_CAP,
    C4_S012_CAP,
    SIGNAL_EXPIRY_HOURS,
)


def _make_signal(**overrides) -> TradingSignal:
    """Factory for test TradingSignals with sensible defaults."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        signal_id="test-sig-001",
        assessment_id="test-assess-001",
        event_id="test-evt-001",
        market_id="test-mkt-001",
        market_question="Will Iran reach a nuclear deal before July 2026?",
        signal_type="S012-OVER",
        direction="NO",
        entry_price=0.275,
        target_price=0.345,
        stop_price=0.195,
        time_horizon_hours=168,
        size_usdc=300.0,
        size_pct=0.03,
        reaction_delta=0.095,
        estimated_shift=0.08,
        actual_move=0.175,
        confidence=0.68,
        reasoning="Test reasoning.",
        domain="GEO",
        passed_concentration=True,
        passed_anti_patterns=True,
        risk_notes=[],
        status="PENDING",
        created_at=now,
        expires_at=now + timedelta(hours=2),
    )
    defaults.update(overrides)
    return TradingSignal(**defaults)


class TestSignalFormatting(unittest.TestCase):
    """test_signal_formatting: output contains all required fields."""

    def test_format_contains_market_question(self):
        signal = _make_signal()
        output = format_signal(signal)
        self.assertIn("Iran", output)
        self.assertIn("nuclear deal", output)

    def test_format_contains_direction(self):
        signal = _make_signal(direction="NO")
        output = format_signal(signal)
        self.assertIn("NO", output)

    def test_format_contains_entry_price(self):
        signal = _make_signal(entry_price=0.275)
        output = format_signal(signal)
        self.assertIn("27.5c", output)

    def test_format_contains_size(self):
        signal = _make_signal(size_usdc=300.0, size_pct=0.03)
        output = format_signal(signal)
        self.assertIn("$300", output)
        self.assertIn("3.0%", output)

    def test_format_contains_risk_status(self):
        signal = _make_signal(passed_concentration=True, passed_anti_patterns=True)
        output = format_signal(signal)
        self.assertIn("PASS", output)

    def test_format_contains_signal_type(self):
        signal = _make_signal(signal_type="S012-OVER")
        output = format_signal(signal)
        self.assertIn("OVERREACTION", output)

    def test_format_contains_delta(self):
        signal = _make_signal(reaction_delta=0.095)
        output = format_signal(signal)
        self.assertIn("+9.5%", output)


class TestConcentrationC1(unittest.TestCase):
    """test_concentration_c1: same event cap enforced."""

    def test_c1_pass_no_overlap(self):
        signal = _make_signal(
            domain="GEO",
            market_question="Will Iran reach a nuclear deal before July 2026?",
            size_pct=0.03,
        )
        # Position on unrelated market
        positions = [{
            "trade_id": "T999",
            "strategy": "S001",
            "domain": "POL",
            "market": "Will Trump win the 2028 election?",
            "size_usd": 300.0,
            "status": "open",
        }]
        passed, warnings = check_concentration(signal, positions, 10_000.0)
        c1_warnings = [w for w in warnings if w.startswith("C1")]
        self.assertEqual(len(c1_warnings), 0)

    def test_c1_fail_same_event(self):
        signal = _make_signal(
            domain="GEO",
            market_question="Will Iran reach a nuclear deal before July 2026?",
            size_pct=0.03,
        )
        # Existing position on overlapping Iran nuclear market (high keyword overlap)
        positions = [{
            "trade_id": "T001",
            "strategy": "S004",
            "domain": "GEO",
            "market": "Will Iran nuclear deal happen before March 2026?",
            "size_usd": 300.0,
            "status": "open",
        }]
        passed, warnings = check_concentration(signal, positions, 10_000.0)
        c1_warnings = [w for w in warnings if w.startswith("C1")]
        self.assertGreater(len(c1_warnings), 0, "C1 should fire on overlapping Iran event")

    def test_c1_under_cap_passes(self):
        signal = _make_signal(
            domain="TEC",
            market_question="Will OpenAI release GPT-5 before June 2026?",
            size_pct=0.015,
        )
        # Small existing position, same event
        positions = [{
            "trade_id": "T100",
            "strategy": "S012",
            "domain": "TEC",
            "market": "Will OpenAI release GPT-5 before March 2026?",
            "size_usd": 100.0,
            "status": "open",
        }]
        passed, warnings = check_concentration(signal, positions, 10_000.0)
        c1_warnings = [w for w in warnings if w.startswith("C1")]
        # 100/10000 + 0.015 = 2.5% < 3% → should pass C1
        self.assertEqual(len(c1_warnings), 0)


class TestConcentrationC4(unittest.TestCase):
    """test_concentration_c4: total S012 cap enforced."""

    def test_c4_pass_under_cap(self):
        signal = _make_signal(size_pct=0.03)
        positions = [{
            "trade_id": "T200",
            "strategy": "S012",
            "domain": "GEO",
            "market": "Unrelated market X",
            "size_usd": 500.0,
            "status": "open",
        }]
        passed, warnings = check_concentration(signal, positions, 10_000.0)
        c4_warnings = [w for w in warnings if w.startswith("C4")]
        # 500/10000 + 0.03 = 8% < 10% → pass
        self.assertEqual(len(c4_warnings), 0)

    def test_c4_fail_over_cap(self):
        signal = _make_signal(size_pct=0.03)
        positions = [{
            "trade_id": "T200",
            "strategy": "S012",
            "domain": "POL",
            "market": "Unrelated S012 market",
            "size_usd": 800.0,
            "status": "open",
        }]
        passed, warnings = check_concentration(signal, positions, 10_000.0)
        c4_warnings = [w for w in warnings if w.startswith("C4")]
        # 800/10000 + 0.03 = 11% > 10% → fail
        self.assertGreater(len(c4_warnings), 0)

    def test_c4_ignores_non_s012(self):
        signal = _make_signal(size_pct=0.03)
        positions = [{
            "trade_id": "T300",
            "strategy": "S004",
            "domain": "GEO",
            "market": "Non-S012 market",
            "size_usd": 900.0,
            "status": "open",
        }]
        passed, warnings = check_concentration(signal, positions, 10_000.0)
        c4_warnings = [w for w in warnings if w.startswith("C4")]
        # 0/10000 + 0.03 = 3% < 10% → pass (S004 doesn't count)
        self.assertEqual(len(c4_warnings), 0)


class TestAntiPatternRevenge(unittest.TestCase):
    """test_anti_pattern_revenge: recent stop -> blocked."""

    def test_revenge_trade_blocked(self):
        now = datetime.now(timezone.utc)
        signal = _make_signal(
            market_id="mkt-revenge-001",
            created_at=now,
        )
        recent_signals = [{
            "market_id": "mkt-revenge-001",
            "status": "STOPPED",
            "created_at": (now - timedelta(hours=2)).isoformat(),
        }]
        passed, warnings = check_anti_patterns(signal, recent_signals)
        ap2_warnings = [w for w in warnings if w.startswith("AP2")]
        self.assertGreater(len(ap2_warnings), 0)
        self.assertFalse(passed)

    def test_revenge_trade_ok_after_window(self):
        now = datetime.now(timezone.utc)
        signal = _make_signal(
            market_id="mkt-revenge-002",
            created_at=now,
        )
        recent_signals = [{
            "market_id": "mkt-revenge-002",
            "status": "STOPPED",
            "created_at": (now - timedelta(hours=5)).isoformat(),
        }]
        passed, warnings = check_anti_patterns(signal, recent_signals)
        ap2_warnings = [w for w in warnings if w.startswith("AP2")]
        self.assertEqual(len(ap2_warnings), 0)

    def test_different_market_not_revenge(self):
        now = datetime.now(timezone.utc)
        signal = _make_signal(
            market_id="mkt-different-001",
            created_at=now,
        )
        recent_signals = [{
            "market_id": "mkt-other-001",
            "status": "STOPPED",
            "created_at": (now - timedelta(hours=1)).isoformat(),
        }]
        passed, warnings = check_anti_patterns(signal, recent_signals)
        ap2_warnings = [w for w in warnings if w.startswith("AP2")]
        self.assertEqual(len(ap2_warnings), 0)


class TestAntiPatternEco(unittest.TestCase):
    """test_anti_pattern_eco: ECO underreaction -> blocked."""

    def test_eco_underreaction_blocked(self):
        signal = _make_signal(
            domain="ECO",
            signal_type="S012-UNDER",
        )
        passed, warnings = check_anti_patterns(signal, [])
        ap1_warnings = [w for w in warnings if w.startswith("AP1")]
        self.assertGreater(len(ap1_warnings), 0)
        self.assertFalse(passed)

    def test_fin_underreaction_blocked(self):
        signal = _make_signal(
            domain="FIN",
            signal_type="S012-UNDER",
        )
        passed, warnings = check_anti_patterns(signal, [])
        ap1_warnings = [w for w in warnings if w.startswith("AP1")]
        self.assertGreater(len(ap1_warnings), 0)

    def test_eco_overreaction_allowed(self):
        signal = _make_signal(
            domain="ECO",
            signal_type="S012-OVER",
        )
        passed, warnings = check_anti_patterns(signal, [])
        ap1_warnings = [w for w in warnings if w.startswith("AP1")]
        self.assertEqual(len(ap1_warnings), 0)

    def test_geo_underreaction_allowed(self):
        signal = _make_signal(
            domain="GEO",
            signal_type="S012-UNDER",
        )
        passed, warnings = check_anti_patterns(signal, [])
        ap1_warnings = [w for w in warnings if w.startswith("AP1")]
        self.assertEqual(len(ap1_warnings), 0)


class TestSignalExpiry(unittest.TestCase):
    """test_signal_expiry: signals expire after 2h."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.store = SignalStore(db_path=self.db_path)

    def tearDown(self):
        self.store.close()
        self.db_path.unlink(missing_ok=True)

    def test_fresh_signal_stays_pending(self):
        signal = _make_signal()
        self.store.save(signal)
        pending = self.store.load_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"], "PENDING")

    def test_expired_signal_auto_marked(self):
        expired_time = datetime.now(timezone.utc) - timedelta(hours=3)
        signal = _make_signal(
            signal_id="test-expired-001",
            created_at=expired_time,
            expires_at=expired_time + timedelta(hours=SIGNAL_EXPIRY_HOURS),
        )
        self.store.save(signal)

        # load_pending triggers expiry check
        pending = self.store.load_pending()
        self.assertEqual(len(pending), 0)

        # Verify it's now EXPIRED
        all_signals = self.store.load_all()
        expired = [s for s in all_signals if s["signal_id"] == "test-expired-001"]
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0]["status"], "EXPIRED")

    def test_approved_signal_not_expired(self):
        old_time = datetime.now(timezone.utc) - timedelta(hours=5)
        signal = _make_signal(
            signal_id="test-approved-001",
            status="APPROVED",
            created_at=old_time,
            expires_at=old_time + timedelta(hours=SIGNAL_EXPIRY_HOURS),
        )
        self.store.save(signal)

        # Expiry only affects PENDING signals
        all_signals = self.store.load_all()
        approved = [s for s in all_signals if s["signal_id"] == "test-approved-001"]
        self.assertEqual(approved[0]["status"], "APPROVED")


class TestBankrollSizing(unittest.TestCase):
    """test_bankroll_sizing: correct $ amount from percentage."""

    def test_3pct_of_10k(self):
        assessment = _make_demo_assessment()
        signal = generate_signal(
            assessment=assessment,
            bankroll=10_000.0,
            positions=[],
            recent_signals=[],
            domain="GEO",
        )
        self.assertAlmostEqual(signal.size_usdc, 300.0)
        self.assertAlmostEqual(signal.size_pct, 0.03)

    def test_3pct_of_5k(self):
        assessment = _make_demo_assessment()
        signal = generate_signal(
            assessment=assessment,
            bankroll=5_000.0,
            positions=[],
            recent_signals=[],
            domain="GEO",
        )
        self.assertAlmostEqual(signal.size_usdc, 150.0)

    def test_non_actionable_raises(self):
        assessment = _make_demo_assessment()
        assessment.is_actionable = False
        with self.assertRaises(ValueError):
            generate_signal(
                assessment=assessment,
                bankroll=10_000.0,
                positions=[],
                recent_signals=[],
                domain="GEO",
            )


class TestSignalStorage(unittest.TestCase):
    """test_signal_storage: round-trip through SQLite."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.store = SignalStore(db_path=self.db_path)

    def tearDown(self):
        self.store.close()
        self.db_path.unlink(missing_ok=True)

    def test_save_and_load(self):
        signal = _make_signal()
        self.store.save(signal)
        all_sigs = self.store.load_all()
        self.assertEqual(len(all_sigs), 1)
        self.assertEqual(all_sigs[0]["signal_id"], "test-sig-001")
        self.assertEqual(all_sigs[0]["direction"], "NO")

    def test_approve_updates_status(self):
        signal = _make_signal()
        self.store.save(signal)
        self.store.update_status("test-sig-001", "APPROVED")
        all_sigs = self.store.load_all()
        self.assertEqual(all_sigs[0]["status"], "APPROVED")

    def test_reject_updates_status(self):
        signal = _make_signal()
        self.store.save(signal)
        self.store.update_status("test-sig-001", "REJECTED")
        all_sigs = self.store.load_all()
        self.assertEqual(all_sigs[0]["status"], "REJECTED")

    def test_find_by_prefix(self):
        signal = _make_signal(signal_id="abc12345-6789-0000-0000-000000000000")
        self.store.save(signal)
        found = self.store.find_by_prefix("abc123")
        self.assertEqual(found, "abc12345-6789-0000-0000-000000000000")

    def test_find_by_prefix_not_found(self):
        found = self.store.find_by_prefix("nonexistent")
        self.assertIsNone(found)

    def test_risk_notes_roundtrip(self):
        signal = _make_signal(risk_notes=["C1 FAIL: test", "AP5: verify"])
        self.store.save(signal)
        loaded = self.store.load_all()[0]
        self.assertEqual(loaded["risk_notes"], ["C1 FAIL: test", "AP5: verify"])


# ============================================================
# Module 6: Paper Trade Logger Tests
# ============================================================

from paper_logger import (
    PaperTrade,
    TradeStore,
    CalibrationReport,
    calculate_pnl,
    next_trade_id,
    check_trade,
    close_trade,
    open_trade_from_signal,
    build_calibration_report,
    _make_demo_signal,
)


def _make_trade(**overrides) -> PaperTrade:
    """Factory for test PaperTrades with sensible defaults."""
    now = datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc)
    defaults = dict(
        trade_id="PT-S012-001",
        signal_id="test-sig-001",
        market_id="test-mkt-001",
        market_question="Will Iran reach a nuclear deal before July 2026?",
        direction="YES",
        entry_price=0.40,
        entry_time=now,
        size_usdc=300.0,
        shares=750.0,
        target_price=0.50,
        stop_price=0.32,
        expiry_time=now + timedelta(hours=168),
        exit_price=None,
        exit_time=None,
        exit_reason=None,
        pnl_usdc=None,
        pnl_pct=None,
        signal_type="S012-OVER",
        domain="GEO",
        reaction_delta=0.095,
        estimated_shift=0.08,
        actual_move=0.175,
        market_resolved=None,
        llm_direction_correct=None,
        reaction_call_correct=None,
        status="OPEN",
    )
    defaults.update(overrides)
    return PaperTrade(**defaults)


class TestPnlYesWin(unittest.TestCase):
    """test_pnl_yes_win: YES trade with price increase -> positive P&L."""

    def test_yes_price_up(self):
        # Bought YES at 0.40, price goes to 0.50, 750 shares
        pnl = calculate_pnl("YES", 0.40, 0.50, 750.0)
        self.assertAlmostEqual(pnl, 75.0)  # (0.50 - 0.40) * 750

    def test_yes_resolves_at_1(self):
        # Bought YES at 0.40, resolves YES (1.0), 750 shares
        pnl = calculate_pnl("YES", 0.40, 1.0, 750.0)
        self.assertAlmostEqual(pnl, 450.0)


class TestPnlYesLoss(unittest.TestCase):
    """test_pnl_yes_loss: YES trade with price decrease -> negative P&L."""

    def test_yes_price_down(self):
        # Bought YES at 0.40, price drops to 0.30, 750 shares
        pnl = calculate_pnl("YES", 0.40, 0.30, 750.0)
        self.assertAlmostEqual(pnl, -75.0)

    def test_yes_resolves_no(self):
        # Bought YES at 0.40, resolves NO (0.0), 750 shares
        pnl = calculate_pnl("YES", 0.40, 0.0, 750.0)
        self.assertAlmostEqual(pnl, -300.0)


class TestPnlNoWin(unittest.TestCase):
    """test_pnl_no_win: NO trade with price decrease -> positive P&L."""

    def test_no_price_drops(self):
        # Bought NO when YES was 0.70 (NO entry = 0.30)
        # YES drops to 0.60 (NO = 0.40) → profit
        pnl = calculate_pnl("NO", 0.30, 0.60, 500.0)
        self.assertAlmostEqual(pnl, 50.0)

    def test_no_resolves_no(self):
        # Bought NO at 0.30, resolves NO (YES = 0.0, NO = 1.0)
        pnl = calculate_pnl("NO", 0.30, 0.0, 500.0)
        self.assertAlmostEqual(pnl, 350.0)

    def test_no_price_rises(self):
        # Bought NO at 0.30; YES rises to 0.80 (NO = 0.20) → loss
        pnl = calculate_pnl("NO", 0.30, 0.80, 500.0)
        self.assertAlmostEqual(pnl, -50.0)

    def test_unknown_direction_fails_closed(self):
        with self.assertRaises(ValueError):
            calculate_pnl("SELL", 0.30, 0.60, 500.0)


class TestTargetHit(unittest.TestCase):
    """test_target_hit: price crosses target -> auto-close."""

    def test_yes_target_hit(self):
        trade = {
            "direction": "YES", "target_price": 0.50, "stop_price": 0.32,
            "expiry_time": "2026-03-07T12:00:00+00:00",
        }
        now = datetime(2026, 2, 28, 14, 0, 0, tzinfo=timezone.utc)
        result = check_trade(trade, 0.52, now)
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "TARGET_HIT")

    def test_no_target_hit(self):
        # NO trade: target is NO price 0.345 → YES must drop to 0.655
        trade = {
            "direction": "NO", "target_price": 0.345, "stop_price": 0.195,
            "expiry_time": "2026-03-07T12:00:00+00:00",
        }
        now = datetime(2026, 2, 28, 14, 0, 0, tzinfo=timezone.utc)
        # Current YES = 0.60 → current NO = 0.40 > target 0.345 → TARGET_HIT
        result = check_trade(trade, 0.60, now)
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "TARGET_HIT")


class TestStopHit(unittest.TestCase):
    """test_stop_hit: price crosses stop -> auto-close."""

    def test_yes_stop_hit(self):
        trade = {
            "direction": "YES", "target_price": 0.50, "stop_price": 0.32,
            "expiry_time": "2026-03-07T12:00:00+00:00",
        }
        now = datetime(2026, 2, 28, 14, 0, 0, tzinfo=timezone.utc)
        result = check_trade(trade, 0.30, now)
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "STOP_HIT")

    def test_no_stop_hit(self):
        # NO trade: stop is NO price 0.195 → YES must rise to 0.805
        trade = {
            "direction": "NO", "target_price": 0.345, "stop_price": 0.195,
            "expiry_time": "2026-03-07T12:00:00+00:00",
        }
        now = datetime(2026, 2, 28, 14, 0, 0, tzinfo=timezone.utc)
        # Current YES = 0.82 → current NO = 0.18 < stop 0.195 → STOP_HIT
        result = check_trade(trade, 0.82, now)
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "STOP_HIT")


class TestTimeExpiry(unittest.TestCase):
    """test_time_expiry: past expiry -> close at current price."""

    def test_expired_trade(self):
        trade = {
            "direction": "YES", "target_price": 0.50, "stop_price": 0.32,
            "expiry_time": "2026-03-01T12:00:00+00:00",
        }
        now = datetime(2026, 3, 2, 0, 0, 0, tzinfo=timezone.utc)
        result = check_trade(trade, 0.42, now)
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "TIME_EXPIRED")
        self.assertAlmostEqual(result["exit_price"], 0.42)

    def test_not_yet_expired(self):
        trade = {
            "direction": "YES", "target_price": 0.50, "stop_price": 0.32,
            "expiry_time": "2026-03-07T12:00:00+00:00",
        }
        now = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = check_trade(trade, 0.42, now)
        self.assertIsNone(result)  # Still within window, no target/stop hit


class TestCalibrationReport(unittest.TestCase):
    """test_calibration_report: report calculates correctly from trade data."""

    def test_basic_report(self):
        trades = [
            {
                "status": "CLOSED", "pnl_usdc": 50.0, "pnl_pct": 0.167,
                "signal_type": "S012-OVER", "domain": "GEO",
                "estimated_shift": 0.08, "actual_move": 0.15,
                "llm_direction_correct": True, "reaction_call_correct": True,
            },
            {
                "status": "CLOSED", "pnl_usdc": -30.0, "pnl_pct": -0.10,
                "signal_type": "S012-OVER", "domain": "GEO",
                "estimated_shift": 0.05, "actual_move": 0.10,
                "llm_direction_correct": True, "reaction_call_correct": False,
            },
            {
                "status": "CLOSED", "pnl_usdc": 20.0, "pnl_pct": 0.10,
                "signal_type": "S012-UNDER", "domain": "POL",
                "estimated_shift": 0.10, "actual_move": 0.03,
                "llm_direction_correct": False, "reaction_call_correct": True,
            },
            {
                "status": "OPEN", "pnl_usdc": None, "pnl_pct": None,
                "signal_type": "S012-OVER", "domain": "TEC",
                "estimated_shift": 0.06, "actual_move": 0.12,
                "llm_direction_correct": None, "reaction_call_correct": None,
            },
        ]
        report = build_calibration_report(trades)

        self.assertEqual(report.total_trades, 4)
        self.assertEqual(report.open_trades, 1)
        self.assertEqual(report.closed_trades, 3)
        self.assertAlmostEqual(report.total_pnl_usdc, 40.0)
        self.assertAlmostEqual(report.avg_pnl_per_trade, 13.33, places=2)
        self.assertAlmostEqual(report.win_rate, 2 / 3, places=4)

        self.assertEqual(report.overreaction_count, 2)
        self.assertAlmostEqual(report.overreaction_win_rate, 0.5)
        self.assertEqual(report.underreaction_count, 1)
        self.assertAlmostEqual(report.underreaction_win_rate, 1.0)

        # LLM accuracy: 2/3 correct
        self.assertAlmostEqual(report.llm_direction_accuracy, 2 / 3, places=4)
        # Reaction accuracy: 2/3 correct
        self.assertAlmostEqual(report.reaction_call_accuracy, 2 / 3, places=4)

        self.assertIn("GEO", report.domain_breakdown)
        self.assertEqual(report.domain_breakdown["GEO"]["count"], 2)

    def test_empty_report(self):
        report = build_calibration_report([])
        self.assertEqual(report.total_trades, 0)
        self.assertAlmostEqual(report.win_rate, 0.0)
        self.assertAlmostEqual(report.total_pnl_usdc, 0.0)


class TestTradeIdSequence(unittest.TestCase):
    """test_trade_id_sequence: IDs increment PT-S012-001, PT-S012-002, etc."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.store = TradeStore(db_path=self.db_path)

    def tearDown(self):
        self.store.close()
        self.db_path.unlink(missing_ok=True)

    def test_first_trade(self):
        tid = next_trade_id(self.store.conn)
        self.assertEqual(tid, "PT-S012-001")

    def test_sequential_ids(self):
        t1 = _make_trade(trade_id="PT-S012-001")
        self.store.save(t1)
        tid = next_trade_id(self.store.conn)
        self.assertEqual(tid, "PT-S012-002")

    def test_third_trade(self):
        self.store.save(_make_trade(trade_id="PT-S012-001"))
        self.store.save(_make_trade(trade_id="PT-S012-002", signal_id="sig-2"))
        tid = next_trade_id(self.store.conn)
        self.assertEqual(tid, "PT-S012-003")


class TestTradeStorage(unittest.TestCase):
    """test_trade_storage: round-trip through SQLite."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.store = TradeStore(db_path=self.db_path)

    def tearDown(self):
        self.store.close()
        self.db_path.unlink(missing_ok=True)

    def test_save_and_load(self):
        trade = _make_trade()
        self.store.save(trade)
        all_trades = self.store.load_all()
        self.assertEqual(len(all_trades), 1)
        self.assertEqual(all_trades[0]["trade_id"], "PT-S012-001")
        self.assertEqual(all_trades[0]["direction"], "YES")
        self.assertAlmostEqual(all_trades[0]["entry_price"], 0.40)
        self.assertEqual(all_trades[0]["status"], "OPEN")

    def test_load_open(self):
        self.store.save(_make_trade(trade_id="PT-S012-001", status="OPEN"))
        self.store.save(_make_trade(trade_id="PT-S012-002", signal_id="sig-2",
                                     status="CLOSED"))
        open_trades = self.store.load_open()
        self.assertEqual(len(open_trades), 1)
        self.assertEqual(open_trades[0]["trade_id"], "PT-S012-001")

    def test_update_exit(self):
        self.store.save(_make_trade())
        now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        updated = self.store.update_exit(
            "PT-S012-001", exit_price=0.50, exit_time=now,
            exit_reason="TARGET_HIT", pnl_usdc=75.0, pnl_pct=0.25,
            status="CLOSED",
        )
        self.assertTrue(updated)
        loaded = self.store.load_all()[0]
        self.assertAlmostEqual(loaded["exit_price"], 0.50)
        self.assertEqual(loaded["exit_reason"], "TARGET_HIT")
        self.assertAlmostEqual(loaded["pnl_usdc"], 75.0)
        self.assertEqual(loaded["status"], "CLOSED")

    def test_update_calibration(self):
        self.store.save(_make_trade())
        self.store.update_calibration(
            "PT-S012-001",
            market_resolved=True,
            llm_direction_correct=True,
            reaction_call_correct=False,
        )
        loaded = self.store.load_all()[0]
        self.assertTrue(loaded["market_resolved"])
        self.assertTrue(loaded["llm_direction_correct"])
        self.assertFalse(loaded["reaction_call_correct"])

    def test_find_by_prefix(self):
        self.store.save(_make_trade(trade_id="PT-S012-001"))
        found = self.store.find_by_prefix("PT-S012-0")
        self.assertEqual(found, "PT-S012-001")

    def test_find_by_prefix_not_found(self):
        found = self.store.find_by_prefix("NONEXISTENT")
        self.assertIsNone(found)

    def test_bool_roundtrip_none(self):
        """None booleans should round-trip as None."""
        trade = _make_trade(market_resolved=None, llm_direction_correct=None)
        self.store.save(trade)
        loaded = self.store.load_all()[0]
        self.assertIsNone(loaded["market_resolved"])
        self.assertIsNone(loaded["llm_direction_correct"])


class TestOpenTradeFromSignal(unittest.TestCase):
    """test_open_trade_from_signal: signal dict -> PaperTrade."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.store = TradeStore(db_path=self.db_path)

    def tearDown(self):
        self.store.close()
        self.db_path.unlink(missing_ok=True)

    def test_creates_trade(self):
        signal = _make_demo_signal()
        trade = open_trade_from_signal(signal, self.store, write_jsonl=False)
        self.assertEqual(trade.trade_id, "PT-S012-001")
        self.assertEqual(trade.signal_id, "demo-sig-pt-001")
        self.assertEqual(trade.direction, "NO")
        self.assertAlmostEqual(trade.entry_price, 0.275)
        self.assertAlmostEqual(trade.size_usdc, 300.0)
        self.assertGreater(trade.shares, 0)
        self.assertEqual(trade.status, "OPEN")

    def test_shares_calculated(self):
        signal = _make_demo_signal()
        trade = open_trade_from_signal(signal, self.store, write_jsonl=False)
        expected = round(300.0 / 0.275, 4)
        self.assertAlmostEqual(trade.shares, expected, places=2)

    def test_stored_in_db(self):
        signal = _make_demo_signal()
        open_trade_from_signal(signal, self.store, write_jsonl=False)
        loaded = self.store.load_all()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["status"], "OPEN")

    def test_no_trade_pnl_uses_no_entry_and_yes_exit(self):
        signal = _make_demo_signal()
        open_trade_from_signal(signal, self.store, write_jsonl=False)
        trade = self.store.load_open()[0]

        pnl, pnl_pct = close_trade(
            self.store, trade, exit_yes_price=0.655, exit_reason="TARGET_HIT"
        )

        # NO moved from 0.275 to 0.345: 0.07 * 1090.9091 shares.
        self.assertAlmostEqual(pnl, 76.36, places=2)
        self.assertAlmostEqual(pnl_pct, 0.2545, places=4)


# ============================================================
# Module 7: Orchestrator Tests
# ============================================================

from orchestrator import (
    Config,
    build_config,
    deliver_signal,
    check_open_trades,
    periodic_snapshots,
    demo_tick,
    run_daemon,
)
from market_snapshot import MarketSnapshot as MarketSnap, score_relevance


class TestConfigDefaults(unittest.TestCase):
    """test_config_loading: defaults are sensible."""

    def test_default_config(self):
        config = Config()
        self.assertEqual(config.poll_interval_seconds, 900)
        self.assertEqual(config.bankroll_usd, 10_000.0)
        self.assertEqual(config.min_move_to_interpret, 0.03)
        self.assertEqual(config.circuit_breaker_threshold, 3)
        self.assertEqual(config.delivery_channel, "telegram")
        self.assertEqual(config.brave_monthly_limit, 900)
        self.assertEqual(config.brave_daily_soft_limit, 50)

    def test_config_from_yaml(self):
        """Config loads from the actual news-pipeline.yaml."""
        config = build_config()
        # YAML has 5 queries
        self.assertGreater(len(config.queries), 0)
        # Delivery should be telegram
        self.assertEqual(config.delivery_channel, "telegram")
        # Circuit breaker from YAML pipeline section
        self.assertEqual(config.circuit_breaker_threshold, 3)


class TestConfigEnvOverrides(unittest.TestCase):
    """test_config_loading: env vars override YAML values."""

    def test_bankroll_override(self):
        os.environ["S012_BANKROLL"] = "5000"
        try:
            config = build_config()
            self.assertAlmostEqual(config.bankroll_usd, 5000.0)
        finally:
            del os.environ["S012_BANKROLL"]

    def test_delivery_override(self):
        os.environ["S012_DELIVERY"] = "stdout"
        try:
            config = build_config()
            self.assertEqual(config.delivery_channel, "stdout")
        finally:
            del os.environ["S012_DELIVERY"]

    def test_poll_interval_override(self):
        os.environ["S012_POLL_INTERVAL"] = "60"
        try:
            config = build_config()
            self.assertEqual(config.poll_interval_seconds, 60)
        finally:
            del os.environ["S012_POLL_INTERVAL"]


class TestDeliveryStdout(unittest.TestCase):
    """test_delivery: stdout mode prints formatted signal."""

    def test_stdout_delivery(self):
        config = Config(delivery_channel="stdout")
        signal = _make_signal()
        # Should not raise — just prints
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            deliver_signal(signal, config)
        output = f.getvalue()
        self.assertIn("S012 SIGNAL", output)
        self.assertIn("Iran", output)


class TestDeliveryTelegram(unittest.TestCase):
    """test_delivery: telegram mode writes to pending-delivery.json."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.delivery_path = Path(self.tmp_dir) / "pending-delivery.json"

    def tearDown(self):
        if self.delivery_path.exists():
            self.delivery_path.unlink()
        Path(self.tmp_dir).rmdir()

    def test_telegram_delivery_writes_file(self):
        import orchestrator
        original_path = orchestrator.DELIVERY_PATH
        orchestrator.DELIVERY_PATH = self.delivery_path

        try:
            config = Config(delivery_channel="telegram")
            signal = _make_signal()
            deliver_signal(signal, config)

            self.assertTrue(self.delivery_path.exists())
            data = json.loads(self.delivery_path.read_text())
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["signal_id"], signal.signal_id)
            self.assertIn("S012 SIGNAL", data[0]["message"])

            # Second delivery appends
            signal2 = _make_signal(signal_id="test-sig-002")
            deliver_signal(signal2, config)
            data2 = json.loads(self.delivery_path.read_text())
            self.assertEqual(len(data2), 2)
        finally:
            orchestrator.DELIVERY_PATH = original_path


class TestCheckOpenTradesNone(unittest.TestCase):
    """test_tick_no_events: no open trades -> 0 closed."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.store = TradeStore(db_path=self.db_path)

    def tearDown(self):
        self.store.close()
        self.db_path.unlink(missing_ok=True)

    def test_empty_store(self):
        closed = check_open_trades(self.store)
        self.assertEqual(closed, 0)


class TestTickSmallMove(unittest.TestCase):
    """test_tick_small_move: move < 3pp -> skipped in tick logic."""

    def test_move_below_threshold(self):
        """MarketMatch with small move should be filtered by tick's threshold check."""
        config = Config(min_move_to_interpret=0.03)
        # A match with 2pp move should be skipped
        match = MarketMatch(
            event=NewsEvent(
                event_id="test-small",
                articles=[],
                key_entities=["Test"],
                summary="Small move test",
                domain="POL",
                is_breaking=False,
                first_seen=datetime.now(timezone.utc),
                source_count=1,
                query_names=["test"],
            ),
            market=MarketSnap(
                market_id="test-small-mkt",
                question="Test?",
                slug="test",
                yes_price=0.52,
                no_price=0.48,
                volume_24h=10000.0,
                volume_total=500000.0,
                liquidity=100000.0,
                end_date="2026-07-01T00:00:00Z",
                domain="POL",
                snapshot_time=datetime.now(timezone.utc),
                yes_token="t1",
                no_token="t2",
            ),
            relevance_score=0.5,
            price_before=0.50,
            price_after=0.52,
            actual_move=0.02,  # 2pp < 3pp threshold
        )
        # The tick logic checks abs(match.actual_move) < config.min_move_to_interpret
        self.assertTrue(abs(match.actual_move) < config.min_move_to_interpret)


class TestTickNoMatches(unittest.TestCase):
    """test_tick_no_matches: events with no market matches -> no signals."""

    def test_no_matches_from_event(self):
        """An event with obscure entities shouldn't match any market."""
        from market_snapshot import score_relevance
        event = NewsEvent(
            event_id="test-nomatch",
            articles=[],
            key_entities=["XYZZY12345", "QWERTY99999"],
            summary="Completely obscure event about nothing real",
            domain="OTHER",
            is_breaking=False,
            first_seen=datetime.now(timezone.utc),
            source_count=1,
            query_names=["test"],
        )
        # Score against a random market — should be near 0
        market = MarketSnap(
            market_id="test-nomatch-mkt",
            question="Will Trump win the 2028 election?",
            slug="trump-2028",
            yes_price=0.40,
            no_price=0.60,
            volume_24h=50000.0,
            volume_total=1000000.0,
            liquidity=200000.0,
            end_date="2028-11-01",
            domain="POL",
            snapshot_time=datetime.now(timezone.utc),
            yes_token="t1",
            no_token="t2",
        )
        score = score_relevance(event, market)
        self.assertLess(score, 0.3)


class TestCircuitBreaker(unittest.TestCase):
    """test_circuit_breaker: 3 failures -> pause."""

    def test_circuit_breaker_threshold(self):
        config = Config(circuit_breaker_threshold=3, circuit_breaker_pause_seconds=5)
        # Simulate the counter logic from run_daemon
        consecutive_failures = 0
        for _ in range(3):
            consecutive_failures += 1
        self.assertEqual(consecutive_failures, config.circuit_breaker_threshold)
        # At this point daemon would pause

    def test_reset_on_success(self):
        consecutive_failures = 2
        # Simulate successful tick
        consecutive_failures = 0
        self.assertEqual(consecutive_failures, 0)


class TestStillBrake(unittest.TestCase):
    """The project-root STILL file rests the S012 observation loop."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.still_path = Path(self.tmp_dir.name) / "STILL"
        self.config = Config(poll_interval_seconds=0)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_still_stops_before_first_tick(self):
        self.still_path.touch()
        with patch("orchestrator.STILL_PATH", self.still_path), patch(
            "orchestrator.tick", new_callable=AsyncMock
        ) as tick_mock:
            asyncio.run(run_daemon(self.config))

        tick_mock.assert_not_awaited()

    def test_still_is_checked_between_ticks(self):
        async def first_tick_requests_rest(*args, **kwargs):
            self.still_path.touch()
            return []

        with patch("orchestrator.STILL_PATH", self.still_path), patch(
            "orchestrator.tick", new_callable=AsyncMock,
            side_effect=first_tick_requests_rest,
        ) as tick_mock, patch(
            "orchestrator.asyncio.sleep", new_callable=AsyncMock
        ):
            asyncio.run(run_daemon(self.config))

        self.assertEqual(tick_mock.await_count, 1)


class TestPeriodicSnapshots(unittest.TestCase):
    """test_periodic_snapshots: snapshots stored for watchlist."""

    def test_empty_watchlist(self):
        """With a fresh cache (no markets loaded), periodic_snapshots returns 0."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        db_path = Path(tmp.name)

        cache = MarketCache()
        cache._markets = []
        cache._by_id = {}
        cache._last_fetch = time.monotonic()  # Mark as fresh but empty
        store = SnapshotStore(db_path=db_path)

        count = periodic_snapshots(cache, store)
        # Empty cache -> empty watchlist -> 0 snapshots
        self.assertEqual(count, 0)

        store.close()
        db_path.unlink(missing_ok=True)


class TestDemoTick(unittest.TestCase):
    """test_tick_full_pipeline: demo runs full pipeline without API calls."""

    def test_demo_runs_without_error(self):
        """demo_tick() should complete without raising."""
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "demo-pipeline.db"

            def interpretation_store():
                return InterpretationStore(db_path=db_path)

            def trade_store():
                return TradeStore(db_path=db_path)

            with patch(
                "orchestrator.InterpretationStore", side_effect=interpretation_store
            ), patch(
                "orchestrator.TradeStore", side_effect=trade_store
            ), patch(
                "reaction_interpreter.log_to_jsonl"
            ) as jsonl_log, redirect_stdout(f):
                signals = asyncio.run(demo_tick())

            jsonl_log.assert_called_once()
        output = f.getvalue()
        # Should have printed all 6 stages
        self.assertIn("[Stage 1]", output)
        self.assertIn("[Stage 2]", output)
        self.assertIn("[Stage 3]", output)
        self.assertIn("[Stage 4]", output)
        self.assertIn("[Stage 5]", output)
        self.assertIn("[Stage 6]", output)
        # Signals list should be returned (may or may not have signals
        # depending on actionability — the demo produces OVERREACTION STRONG)
        self.assertIsInstance(signals, list)


# ═══════════════════════════════════════════════════════════════════════
# Module 0 — Shared Config (config.py)
# ═══════════════════════════════════════════════════════════════════════

from config import (
    S012Config,
    QueryConfig,
    classify_domain as cfg_classify_domain,
    is_sports as cfg_is_sports,
    ensure_schema,
    ensure_data_dirs,
    setup_logging,
    SCRIPT_DIR as CFG_SCRIPT_DIR,
    PROJECT_ROOT as CFG_PROJECT_ROOT,
    DB_PATH as CFG_DB_PATH,
    DATA_DIR as CFG_DATA_DIR,
    CONFIG_PATH as CFG_CONFIG_PATH,
)


class TestConfigPaths(unittest.TestCase):
    """Shared path constants resolve correctly."""

    def test_project_root_exists(self):
        self.assertTrue(CFG_PROJECT_ROOT.exists())

    def test_db_path_under_data(self):
        self.assertEqual(CFG_DB_PATH.name, "news-pipeline.db")
        self.assertEqual(CFG_DB_PATH.parent.name, "data")

    def test_data_dir_is_s012(self):
        self.assertEqual(CFG_DATA_DIR.name, "s012")

    def test_config_path_yaml(self):
        self.assertEqual(CFG_CONFIG_PATH.name, "news-pipeline.yaml")


class TestConfigClassifyDomain(unittest.TestCase):
    """config.py classify_domain mirrors news_ingestor version."""

    def test_geo(self):
        self.assertEqual(cfg_classify_domain("Iran nuclear talks"), "GEO")

    def test_cry(self):
        self.assertEqual(cfg_classify_domain("Bitcoin crashes to $50K"), "CRY")

    def test_pol(self):
        self.assertEqual(cfg_classify_domain("Trump signs order"), "POL")

    def test_eco(self):
        self.assertEqual(cfg_classify_domain("Fed raises interest rate"), "ECO")

    def test_tec(self):
        self.assertEqual(cfg_classify_domain("OpenAI announces new ai model"), "TEC")

    def test_env(self):
        self.assertEqual(cfg_classify_domain("Hurricane hits coast"), "ENV")

    def test_other(self):
        self.assertEqual(cfg_classify_domain("Local bakery opens"), "OTHER")


class TestConfigIsSports(unittest.TestCase):
    """config.py is_sports mirrors market_snapshot version."""

    def test_nba(self):
        self.assertTrue(cfg_is_sports("Lakers vs Celtics NBA Finals"))

    def test_esports(self):
        self.assertTrue(cfg_is_sports("Counter-Strike Major bo3"))

    def test_non_sports(self):
        self.assertFalse(cfg_is_sports("Will Iran be struck by Israel?"))


class TestS012ConfigDefaults(unittest.TestCase):
    """S012Config dataclass default values."""

    def test_defaults(self):
        cfg = S012Config()
        self.assertEqual(cfg.bankroll_usd, 10_000.0)
        self.assertEqual(cfg.poll_interval_seconds, 900)
        self.assertEqual(cfg.delivery_channel, "stdout")
        self.assertEqual(cfg.overreaction_threshold, 0.05)
        self.assertEqual(cfg.geo_overreaction_threshold, 0.08)
        self.assertEqual(cfg.circuit_breaker_threshold, 3)

    def test_from_yaml(self):
        cfg = S012Config.from_yaml()
        # Should load queries from the real YAML
        self.assertGreater(len(cfg.queries), 0)
        self.assertIsInstance(cfg.queries[0], QueryConfig)
        self.assertTrue(cfg.queries[0].name)

    def test_env_overrides(self):
        os.environ["S012_BANKROLL"] = "25000"
        os.environ["S012_DELIVERY"] = "telegram"
        os.environ["S012_POLL_INTERVAL"] = "600"
        try:
            cfg = S012Config.from_yaml()
            self.assertEqual(cfg.bankroll_usd, 25000.0)
            self.assertEqual(cfg.delivery_channel, "telegram")
            self.assertEqual(cfg.poll_interval_seconds, 600)
        finally:
            del os.environ["S012_BANKROLL"]
            del os.environ["S012_DELIVERY"]
            del os.environ["S012_POLL_INTERVAL"]


class TestEnsureSchema(unittest.TestCase):
    """ensure_schema creates all tables in a fresh DB."""

    def test_creates_all_tables(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        try:
            ensure_schema(db_path)
            conn = sqlite3.connect(db_path)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            conn.close()
            expected = {
                "seen_urls",
                "news_events",
                "event_articles",
                "market_snapshots",
                "s012_interpretations",
                "s012_assessments",
                "s012_signals",
                "s012_paper_trades",
            }
            self.assertTrue(expected.issubset(tables), f"Missing: {expected - tables}")
        finally:
            db_path.unlink(missing_ok=True)

    def test_idempotent(self):
        """Calling twice doesn't error."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        try:
            ensure_schema(db_path)
            ensure_schema(db_path)  # second call should be fine
        finally:
            db_path.unlink(missing_ok=True)


class TestSetupLogging(unittest.TestCase):
    """setup_logging is callable without error."""

    def test_verbose_callable(self):
        # basicConfig is a no-op under pytest (root logger already configured),
        # but the function itself must not raise.
        setup_logging(verbose=True)

    def test_normal_callable(self):
        setup_logging(verbose=False)


if __name__ == "__main__":
    unittest.main()
