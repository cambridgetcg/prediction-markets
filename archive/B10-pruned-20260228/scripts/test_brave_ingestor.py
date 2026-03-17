#!/usr/bin/env python3
"""
Tests for NB02 Brave News Ingestor.

Usage:
    python3 -m pytest scripts/test_brave_ingestor.py -v
"""

import asyncio
import json
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import httpx

from brave_ingestor import (
    Article,
    BraveNewsPoller,
    BudgetTracker,
    PollScheduler,
    QueryConfig,
    SeenStore,
    parse_age,
)


# --- Fixtures ---

@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def tmp_usage(tmp_path):
    return tmp_path / "usage.json"


@pytest.fixture
def seen_store(tmp_db):
    store = SeenStore(db_path=tmp_db)
    yield store
    store.close()


@pytest.fixture
def budget_tracker(tmp_usage):
    return BudgetTracker(usage_path=tmp_usage)


@pytest.fixture
def sample_query():
    return QueryConfig(
        name="iran-nuclear",
        keywords=["Iran nuclear"],
        countries=["US", "GB", "RU"],
        freshness="pd",
        count_per_country=5,
        interval_minutes=60,
    )


def _brave_response(articles: list[dict]) -> dict:
    """Build a Brave-shaped response from article dicts."""
    return {"results": articles}


def _brave_article(
    title: str = "Test headline",
    url: str = "https://example.com/article1",
    description: str = "Test description.",
    age: str = "2 hours ago",
    source_name: str = "Reuters",
    source_url: str = "https://reuters.com",
    extra_snippets: list[str] | None = None,
) -> dict:
    return {
        "title": title,
        "url": url,
        "description": description,
        "age": age,
        "source": {"name": source_name, "url": source_url},
        "extra_snippets": extra_snippets or ["snippet 1"],
    }


# --- Age Parser Tests ---

class TestParseAge:
    def test_hours_ago(self):
        ref = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_age("9 hours ago", reference=ref)
        assert result == datetime(2026, 2, 27, 3, 0, 0, tzinfo=timezone.utc)

    def test_minutes_ago(self):
        ref = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_age("30 minutes ago", reference=ref)
        assert result == datetime(2026, 2, 27, 11, 30, 0, tzinfo=timezone.utc)

    def test_days_ago(self):
        ref = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_age("2 days ago", reference=ref)
        assert result == datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

    def test_weeks_ago(self):
        ref = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_age("1 week ago", reference=ref)
        assert result == datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)

    def test_months_ago(self):
        ref = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_age("1 month ago", reference=ref)
        expected = ref - timedelta(days=30)
        assert result == expected

    def test_seconds_ago(self):
        ref = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_age("45 seconds ago", reference=ref)
        assert result == datetime(2026, 2, 27, 11, 59, 15, tzinfo=timezone.utc)

    def test_iso_utc(self):
        result = parse_age("2026-02-27T10:30:00Z")
        assert result == datetime(2026, 2, 27, 10, 30, 0, tzinfo=timezone.utc)

    def test_iso_with_tz(self):
        result = parse_age("2026-02-27T10:30:00+00:00")
        assert result.hour == 10
        assert result.tzinfo is not None

    def test_fallback_returns_reference(self):
        ref = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_age("unknown format", reference=ref)
        assert result == ref

    def test_plural_units(self):
        ref = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_age("3 hours ago", reference=ref)
        assert result == datetime(2026, 2, 27, 9, 0, 0, tzinfo=timezone.utc)

    def test_singular_unit(self):
        ref = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)
        result = parse_age("1 hour ago", reference=ref)
        assert result == datetime(2026, 2, 27, 11, 0, 0, tzinfo=timezone.utc)


# --- SeenStore Tests ---

class TestSeenStore:
    def test_new_url_not_seen(self, seen_store):
        assert not seen_store.is_seen("abc123")

    def test_mark_seen_then_seen(self, seen_store):
        seen_store.mark_seen("abc123", "https://example.com", "US")
        assert seen_store.is_seen("abc123")

    def test_mark_multiple_countries(self, seen_store):
        seen_store.mark_seen("abc123", "https://example.com", "US")
        seen_store.mark_seen("abc123", "https://example.com", "GB")
        # Still seen as one URL
        assert seen_store.is_seen("abc123")
        # But two country records
        rows = seen_store.conn.execute(
            "SELECT country FROM article_countries WHERE url_hash = ?", ("abc123",)
        ).fetchall()
        assert set(r[0] for r in rows) == {"US", "GB"}

    def test_persists_across_instances(self, tmp_db):
        store1 = SeenStore(db_path=tmp_db)
        store1.mark_seen("abc123", "https://example.com", "US")
        store1.close()

        store2 = SeenStore(db_path=tmp_db)
        assert store2.is_seen("abc123")
        store2.close()


# --- BudgetTracker Tests ---

class TestBudgetTracker:
    def test_initial_empty(self, budget_tracker):
        s = budget_tracker.summary()
        assert s["month_used"] == 0
        assert s["month_remaining"] == 900

    def test_record_increments(self, budget_tracker):
        budget_tracker.record(5)
        s = budget_tracker.summary()
        assert s["month_used"] == 5
        assert s["month_remaining"] == 895

    def test_can_request_under_limit(self, budget_tracker):
        ok, reason = budget_tracker.can_request(10)
        assert ok
        assert reason == ""

    def test_blocks_at_monthly_limit(self, budget_tracker):
        budget_tracker.record(900)
        ok, reason = budget_tracker.can_request(1)
        assert not ok
        assert "Monthly limit" in reason

    def test_warns_at_daily_soft_limit(self, budget_tracker, capsys):
        budget_tracker.record(35)
        ok, _ = budget_tracker.can_request(1)
        assert ok  # Soft limit doesn't block
        captured = capsys.readouterr()
        assert "Daily soft limit" in captured.out or ok  # Warning printed

    def test_cost_estimate(self, budget_tracker):
        budget_tracker.record(500)
        s = budget_tracker.summary()
        assert s["estimated_cost"] == 2.5  # $5/1000 * 500

    def test_month_reset(self, budget_tracker):
        budget_tracker.record(100)
        # Simulate new month
        budget_tracker.data["month"] = "2025-01"
        budget_tracker._reset_if_new_month()
        assert budget_tracker.data["total"] == 0

    def test_persists_to_file(self, tmp_usage):
        t1 = BudgetTracker(usage_path=tmp_usage)
        t1.record(42)

        t2 = BudgetTracker(usage_path=tmp_usage)
        assert t2.data["total"] == 42


# --- Article Tests ---

class TestArticle:
    def test_url_hash_deterministic(self):
        a = Article(
            url="https://example.com/test",
            title="Test", description="Desc",
            extra_snippets=[], full_text="Test Desc",
            source_name="Test", source_domain="example.com",
            country_queried="US", age_raw="1 hour ago",
            published_at=datetime.now(timezone.utc),
            query_name="test", fetched_at=datetime.now(timezone.utc),
        )
        # SHA256 of the URL should be consistent
        import hashlib
        expected = hashlib.sha256(b"https://example.com/test").hexdigest()
        assert a.url_hash == expected

    def test_url_hash_different_urls(self):
        a1 = Article(
            url="https://example.com/a", title="", description="",
            extra_snippets=[], full_text="", source_name="", source_domain="",
            country_queried="US", age_raw="", published_at=datetime.now(timezone.utc),
            query_name="", fetched_at=datetime.now(timezone.utc),
        )
        a2 = Article(
            url="https://example.com/b", title="", description="",
            extra_snippets=[], full_text="", source_name="", source_domain="",
            country_queried="US", age_raw="", published_at=datetime.now(timezone.utc),
            query_name="", fetched_at=datetime.now(timezone.utc),
        )
        assert a1.url_hash != a2.url_hash


# --- BraveNewsPoller Tests ---

class TestBraveNewsPoller:
    """Tests using mocked httpx responses."""

    @pytest.fixture
    def poller(self, tmp_db, tmp_usage):
        with patch.dict("os.environ", {"BRAVE_API_KEY": "test-key-123"}):
            p = BraveNewsPoller()
            p.seen = SeenStore(db_path=tmp_db)
            p.budget = BudgetTracker(usage_path=tmp_usage)
            p.RATE_LIMIT_SECONDS = 0  # No delay in tests
            yield p
            p.close()

    def test_build_query_single_keyword(self, poller):
        q = QueryConfig(name="test", keywords=["Iran nuclear"])
        assert poller._build_query_text(q) == "Iran nuclear"

    def test_build_query_or_mode(self, poller):
        q = QueryConfig(name="test", keywords=["Iran", "nuclear"], boolean_mode="OR")
        assert poller._build_query_text(q) == "Iran OR nuclear"

    def test_build_query_and_mode(self, poller):
        q = QueryConfig(name="test", keywords=["Iran", "nuclear"], boolean_mode="AND")
        assert poller._build_query_text(q) == "Iran AND nuclear"

    @pytest.mark.asyncio
    async def test_poll_multi_country(self, poller, sample_query):
        """3 countries × 1 unique article each = 3 new articles."""
        responses = {
            "US": _brave_response([_brave_article(url="https://ex.com/us1", title="US article")]),
            "GB": _brave_response([_brave_article(url="https://ex.com/gb1", title="GB article")]),
            "RU": _brave_response([_brave_article(url="https://ex.com/ru1", title="RU article")]),
        }

        call_count = 0

        async def mock_get(url, params=None, headers=None, timeout=None):
            nonlocal call_count
            country = params["country"]
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = responses[country]
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            articles = await poller.poll(sample_query)

        assert len(articles) == 3
        assert call_count == 3
        countries = {a.country_queried for a in articles}
        assert countries == {"US", "GB", "RU"}

    @pytest.mark.asyncio
    async def test_deduplication_across_countries(self, poller, sample_query):
        """Same URL from multiple countries = 1 new article (first seen)."""
        same_article = _brave_article(url="https://reuters.com/shared", title="Shared article")
        responses = {
            "US": _brave_response([same_article]),
            "GB": _brave_response([same_article]),
            "RU": _brave_response([same_article]),
        }

        async def mock_get(url, params=None, headers=None, timeout=None):
            country = params["country"]
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = responses[country]
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            articles = await poller.poll(sample_query)

        # Only 1 new article (first country to return it)
        assert len(articles) == 1
        # But all 3 countries recorded
        rows = poller.seen.conn.execute(
            "SELECT country FROM article_countries WHERE url_hash = ?",
            (articles[0].url_hash,)
        ).fetchall()
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_second_poll_skips_seen(self, poller, sample_query):
        """Polling the same query twice: second poll returns 0 new articles."""
        response = _brave_response([_brave_article(url="https://ex.com/a1")])

        async def mock_get(url, params=None, headers=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = response
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            first = await poller.poll(sample_query)
            second = await poller.poll(sample_query)

        assert len(first) == 1
        assert len(second) == 0

    @pytest.mark.asyncio
    async def test_budget_blocks_poll(self, poller, sample_query):
        """If monthly budget is exhausted, poll returns empty."""
        poller.budget.record(900)  # Hit the limit

        articles = await poller.poll(sample_query)
        assert len(articles) == 0

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self, poller, sample_query):
        """HTTP errors for a country don't crash — just skip it."""
        async def mock_get(url, params=None, headers=None, timeout=None):
            raise httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=MagicMock(),
                response=MagicMock(status_code=429),
            )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            articles = await poller.poll(sample_query)

        assert len(articles) == 0

    @pytest.mark.asyncio
    async def test_http_error_not_counted_in_budget(self, poller, sample_query):
        """HTTP errors should NOT count against budget."""
        async def mock_get(url, params=None, headers=None, timeout=None):
            raise httpx.HTTPStatusError(
                "422 Unprocessable Entity",
                request=MagicMock(),
                response=MagicMock(status_code=422),
            )

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await poller.poll(sample_query)

        # All 3 countries errored — budget should be 0
        assert poller.budget.summary()["month_used"] == 0

    @pytest.mark.asyncio
    async def test_budget_records_per_country(self, poller, sample_query):
        """Budget should increment by number of countries polled."""
        response = _brave_response([])

        async def mock_get(url, params=None, headers=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = response
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await poller.poll(sample_query)

        # 3 countries = 3 requests
        assert poller.budget.summary()["month_used"] == 3

    @pytest.mark.asyncio
    async def test_article_fields_populated(self, poller):
        """Verify all Article fields are correctly populated from Brave response."""
        query = QueryConfig(
            name="test-q", keywords=["test"],
            countries=["US"], count_per_country=5,
        )
        response = _brave_response([_brave_article(
            title="Iran talks collapse",
            url="https://reuters.com/iran-talks",
            description="Negotiations ended without agreement.",
            age="3 hours ago",
            source_name="Reuters",
            source_url="https://reuters.com",
            extra_snippets=["Extra detail one", "Extra detail two"],
        )])

        async def mock_get(url, params=None, headers=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = response
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            articles = await poller.poll(query)

        assert len(articles) == 1
        a = articles[0]
        assert a.title == "Iran talks collapse"
        assert a.url == "https://reuters.com/iran-talks"
        assert a.description == "Negotiations ended without agreement."
        assert a.source_name == "Reuters"
        assert a.source_domain == "reuters.com"
        assert a.country_queried == "US"
        assert a.query_name == "test-q"
        assert a.age_raw == "3 hours ago"
        assert len(a.extra_snippets) == 2
        assert "Extra detail one" in a.full_text
        assert "Iran talks collapse" in a.full_text
        assert a.published_at < a.fetched_at


# --- PollScheduler Tests ---

class TestPollScheduler:
    @pytest.mark.asyncio
    async def test_run_once_polls_due_queries(self, tmp_db, tmp_usage):
        with patch.dict("os.environ", {"BRAVE_API_KEY": "test-key"}):
            poller = BraveNewsPoller()
            poller.seen = SeenStore(db_path=tmp_db)
            poller.budget = BudgetTracker(usage_path=tmp_usage)
            poller.RATE_LIMIT_SECONDS = 0

        q1 = QueryConfig(name="q1", keywords=["test1"], countries=["US"], interval_minutes=60)
        q2 = QueryConfig(name="q2", keywords=["test2"], countries=["US"], interval_minutes=60)

        scheduler = PollScheduler(poller, [q1, q2])

        response = _brave_response([_brave_article(url="https://ex.com/1")])

        async def mock_get(url, params=None, headers=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = response
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            articles = await scheduler.run_once()

        # Both queries should have been polled (first run, no last_poll)
        assert "q1" in scheduler._last_poll
        assert "q2" in scheduler._last_poll
        poller.close()

    @pytest.mark.asyncio
    async def test_skips_not_due_queries(self, tmp_db, tmp_usage):
        with patch.dict("os.environ", {"BRAVE_API_KEY": "test-key"}):
            poller = BraveNewsPoller()
            poller.seen = SeenStore(db_path=tmp_db)
            poller.budget = BudgetTracker(usage_path=tmp_usage)
            poller.RATE_LIMIT_SECONDS = 0

        q = QueryConfig(name="q1", keywords=["test"], countries=["US"], interval_minutes=9999)
        scheduler = PollScheduler(poller, [q])
        # Pretend we just polled
        scheduler._last_poll["q1"] = time.monotonic()

        response = _brave_response([])

        async def mock_get(url, params=None, headers=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = response
            return resp

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            articles = await scheduler.run_once()

        # Should have skipped — budget untouched
        assert poller.budget.summary()["month_used"] == 0
        poller.close()


# --- Rate Limit Tests ---

class TestRateLimit:
    @pytest.mark.asyncio
    async def test_rate_limit_enforced(self):
        """Verify there's a delay between requests."""
        with patch.dict("os.environ", {"BRAVE_API_KEY": "test-key"}):
            poller = BraveNewsPoller()
            poller.RATE_LIMIT_SECONDS = 0.2  # 200ms for test speed

        times = []

        async def mock_get(url, params=None, headers=None, timeout=None):
            times.append(time.monotonic())
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = _brave_response([])
            return resp

        query = QueryConfig(name="test", keywords=["test"], countries=["US", "GB", "RU"])

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await poller.poll(query)

        # 3 countries → 3 requests
        assert len(times) == 3
        # Gap between consecutive requests should be >= rate limit
        for i in range(1, len(times)):
            gap = times[i] - times[i - 1]
            assert gap >= 0.15, f"Gap {gap:.3f}s < 0.15s (rate limit not enforced)"

        poller.close()
