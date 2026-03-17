#!/usr/bin/env python3
"""
Tests for NB08: Pipeline Orchestrator.

Run:  pytest scripts/test_orchestrator.py -v
"""

import json
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brave_ingestor import Article, QueryConfig
from event_clusterer import EventCluster
from perspective_matrix import PerspectiveMatrix, ClusterView
from signal_generator import GeneratedSignal
from truth_extractor import TruthExtractionResult
from orchestrator import (
    CircuitBreaker,
    PipelineConfig,
    dead_letter,
    format_signal_message,
    init_db,
    load_config,
    persist_extraction,
    persist_signal,
    _env_sub,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


@pytest.fixture
def db():
    """Fresh in-memory DB initialized from schema.sql."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if SCHEMA_PATH.exists():
        schema = SCHEMA_PATH.read_text()
        for statement in schema.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.upper().startswith("PRAGMA"):
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass
        conn.commit()
    yield conn
    conn.close()


def make_signal(**overrides) -> GeneratedSignal:
    defaults = dict(
        signal_id="sig-abc123",
        cluster_id="cluster-001",
        market_id="cond-xyz",
        market_question="Will Iran reach a nuclear deal by June?",
        direction="NO",
        current_price=0.35,
        suggested_probability=0.48,
        edge=0.13,
        kelly_fraction=0.05,
        kelly_usdc=500.0,
        strategy_code="S004",
        confidence=0.72,
        yes_discount_applied=False,
        generated_at=NOW,
        status="pending",
    )
    defaults.update(overrides)
    return GeneratedSignal(**defaults)


def make_extraction(**overrides) -> TruthExtractionResult:
    defaults = dict(
        cluster_id="cluster-001",
        consensus_facts=["Talks occurred in Geneva", "No deal reached"],
        contested_claims=[{"claim": "enrichment", "resolution": "likely_true"}],
        motivated_omissions={"Western": "Omitted prior violations"},
        objective_kernel="Geneva talks ended without agreement.",
        market_relevance=[{"category": "GEO", "description": "Iran strike"}],
        overall_confidence=0.72,
        requires_human_review=False,
        model_used="claude-sonnet-4-6",
        extracted_at=NOW,
    )
    defaults.update(overrides)
    return TruthExtractionResult(**defaults)


def make_cluster(**overrides) -> EventCluster:
    defaults = dict(
        cluster_id="cluster-001",
        event_summary="Iran: Nuclear talks stall",
        first_seen=NOW,
        last_updated=NOW,
        articles=[],
        key_entities=["Iran", "IAEA"],
        perspective_matrix=PerspectiveMatrix(
            clusters={
                "Western": ClusterView(
                    cluster_name="Western",
                    article_count=3,
                    mean_tone=-1.5,
                    reliability_weighted_tone=-1.4,
                    key_claims=["Talks stall"],
                    sources=["reuters.com"],
                ),
                "Iranian": ClusterView(
                    cluster_name="Iranian",
                    article_count=2,
                    mean_tone=2.0,
                    reliability_weighted_tone=2.0,
                    key_claims=["Iran asserts sovereignty"],
                    sources=["presstv.ir"],
                ),
            },
            divergence_score=3.5,
            is_divergent=True,
        ),
        divergence_score=3.5,
        is_divergent=True,
        query_sources=["iran-nuclear"],
    )
    defaults.update(overrides)
    return EventCluster(**defaults)


# ---------------------------------------------------------------------------
# TestPipelineConfig
# ---------------------------------------------------------------------------

class TestPipelineConfig:

    def test_load_valid_config(self, tmp_path):
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text("""
queries:
  - name: test-query
    keywords: ["test"]
    countries: [US, GB]
    freshness: pd
pipeline:
  divergence_threshold: 3.5
  min_edge: 0.06
delivery:
  channel: telegram
  webhook_url: "https://hook.example.com"
logging:
  level: DEBUG
""")
        config = load_config(cfg_file)
        assert len(config.queries) == 1
        assert config.queries[0].name == "test-query"
        assert config.divergence_threshold == 3.5
        assert config.min_edge == 0.06
        assert config.delivery_channel == "telegram"
        assert config.log_level == "DEBUG"

    def test_env_var_substitution(self):
        with patch.dict("os.environ", {"MY_KEY": "secret123"}):
            assert _env_sub("${MY_KEY}") == "secret123"

    def test_env_var_missing_returns_empty(self):
        assert _env_sub("${NONEXISTENT_VAR_12345}") == ""

    def test_non_env_string_passthrough(self):
        assert _env_sub("plain text") == "plain text"

    def test_missing_config_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_query_config_defaults(self, tmp_path):
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text("""
queries:
  - name: minimal
    keywords: ["test"]
""")
        config = load_config(cfg_file)
        q = config.queries[0]
        assert q.boolean_mode == "OR"
        assert q.countries == ["US", "GB"]
        assert q.freshness == "pd"
        assert q.count_per_country == 20
        assert q.interval_minutes == 1440
        assert q.extra_snippets is True


# ---------------------------------------------------------------------------
# TestCircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:

    def test_trips_after_threshold(self):
        cb = CircuitBreaker(threshold=3, pause_minutes=30)
        for _ in range(3):
            cb.record_failure()
        assert cb.is_open is True

    def test_does_not_trip_below_threshold(self):
        cb = CircuitBreaker(threshold=3, pause_minutes=30)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is False

    def test_resets_after_pause(self):
        cb = CircuitBreaker(threshold=2, pause_minutes=1)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open is True
        # Simulate time passing
        cb._tripped_at = time.time() - 120  # 2 min ago
        assert cb.is_open is False

    def test_success_resets_counter(self):
        cb = CircuitBreaker(threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        # Only 1 failure since reset
        assert cb.is_open is False

    def test_is_open_before_pause_elapsed(self):
        cb = CircuitBreaker(threshold=1, pause_minutes=60)
        cb.record_failure()
        assert cb.is_open is True

    def test_minutes_until_reset_zero_when_not_tripped(self):
        cb = CircuitBreaker(threshold=3)
        assert cb.minutes_until_reset == 0

    def test_minutes_until_reset_positive_when_tripped(self):
        cb = CircuitBreaker(threshold=1, pause_minutes=30)
        cb.record_failure()
        assert cb.minutes_until_reset > 0
        assert cb.minutes_until_reset <= 30


# ---------------------------------------------------------------------------
# TestFormatSignalMessage
# ---------------------------------------------------------------------------

class TestFormatSignalMessage:

    def test_all_fields_present(self):
        sig = make_signal()
        msg = format_signal_message(sig)
        assert "SIGNAL" in msg
        assert "Iran" in msg
        assert "NO" in msg
        assert "Edge" in msg
        assert "Kelly" in msg
        assert "S004" in msg
        assert "Approve" in msg

    def test_with_extraction_kernel(self):
        sig = make_signal()
        ext = make_extraction()
        msg = format_signal_message(sig, extraction=ext)
        assert "Truth kernel:" in msg
        assert "Geneva talks ended" in msg

    def test_with_perspective_split(self):
        sig = make_signal()
        cluster = make_cluster()
        # Need articles in cluster for perspective display
        article = Article(
            url="https://reuters.com/test",
            title="Test",
            description="Test",
            extra_snippets=[],
            full_text="",
            source_name="Reuters",
            source_domain="reuters.com",
            country_queried="US",
            age_raw="1h ago",
            published_at=NOW,
            query_name="iran",
            fetched_at=NOW,
            geo_cluster="Western",
        )
        cluster.articles = [article]
        msg = format_signal_message(sig, cluster=cluster)
        assert "Perspective split:" in msg
        assert "Divergence:" in msg

    def test_without_optional_fields(self):
        sig = make_signal()
        msg = format_signal_message(sig, extraction=None, cluster=None)
        assert "SIGNAL" in msg
        assert "Truth kernel:" not in msg
        assert "Perspective split:" not in msg

    def test_approve_reject_prompt_included(self):
        sig = make_signal()
        msg = format_signal_message(sig)
        assert "A=Approve" in msg
        assert "R=Reject" in msg
        assert "I=More info" in msg


# ---------------------------------------------------------------------------
# TestPersistSignal
# ---------------------------------------------------------------------------

class TestPersistSignal:

    def test_inserts_to_signals_table(self, db):
        sig = make_signal()
        persist_signal(db, sig, extraction_id=1)
        row = db.execute("SELECT signal_id, direction FROM signals").fetchone()
        assert row[0] == "sig-abc123"
        assert row[1] == "NO"

    def test_upsert_on_duplicate(self, db):
        sig = make_signal(status="pending")
        persist_signal(db, sig)
        sig2 = make_signal(status="approved")
        persist_signal(db, sig2)
        count = db.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        assert count == 1
        status = db.execute("SELECT status FROM signals").fetchone()[0]
        assert status == "approved"

    def test_all_fields_stored(self, db):
        sig = make_signal()
        persist_signal(db, sig, extraction_id=42)
        row = db.execute("""
            SELECT signal_id, cluster_id, extraction_id, market_id,
                   market_question, direction, current_price,
                   suggested_probability, edge, kelly_fraction,
                   kelly_usdc, strategy_code, confidence,
                   yes_discount_applied, status
            FROM signals
        """).fetchone()
        assert row[0] == "sig-abc123"
        assert row[1] == "cluster-001"
        assert row[2] == 42
        assert row[3] == "cond-xyz"
        assert "Iran" in row[4]
        assert row[5] == "NO"
        assert abs(row[6] - 0.35) < 0.01
        assert abs(row[7] - 0.48) < 0.01
        assert abs(row[8] - 0.13) < 0.01
        assert row[14] == "pending"


# ---------------------------------------------------------------------------
# TestPersistExtraction
# ---------------------------------------------------------------------------

class TestPersistExtraction:

    def test_inserts_and_returns_id(self, db):
        ext = make_extraction()
        eid = persist_extraction(db, ext, article_count=5)
        assert isinstance(eid, int)
        assert eid >= 1

    def test_json_fields_stored_correctly(self, db):
        ext = make_extraction()
        eid = persist_extraction(db, ext, article_count=5)
        row = db.execute(
            "SELECT consensus_facts, contested_claims, motivated_omissions, "
            "objective_kernel, market_relevance, overall_confidence "
            "FROM extractions WHERE extraction_id = ?",
            (eid,),
        ).fetchone()
        facts = json.loads(row[0])
        assert "Talks occurred in Geneva" in facts
        claims = json.loads(row[1])
        assert isinstance(claims, list)
        omissions = json.loads(row[2])
        assert "Western" in omissions
        assert row[3] == "Geneva talks ended without agreement."
        relevance = json.loads(row[4])
        assert relevance[0]["category"] == "GEO"
        assert abs(row[5] - 0.72) < 0.01


# ---------------------------------------------------------------------------
# TestDeadLetter
# ---------------------------------------------------------------------------

class TestDeadLetter:

    def test_writes_to_dead_letter_queue(self, db):
        dead_letter(db, "extraction", '{"cluster_id": "c1"}', "API timeout")
        count = db.execute("SELECT COUNT(*) FROM dead_letters").fetchone()[0]
        assert count == 1

    def test_stage_and_error_stored(self, db):
        dead_letter(db, "signal", '{"id": "s1"}', "R01 cap exceeded")
        row = db.execute(
            "SELECT stage, error FROM dead_letters"
        ).fetchone()
        assert row[0] == "signal"
        assert "R01" in row[1]


# ---------------------------------------------------------------------------
# TestPollState
# ---------------------------------------------------------------------------

class TestPollState:

    def _update(self, db, query_name, new_count):
        """Mirror orchestrator._update_poll_state logic."""
        now = datetime.now(timezone.utc).isoformat()
        db.execute("""
            INSERT INTO poll_state (query_name, last_poll_time, articles_seen, articles_new)
            VALUES (?, ?, 0, ?)
            ON CONFLICT(query_name) DO UPDATE SET
                last_poll_time = excluded.last_poll_time,
                articles_seen = articles_seen + excluded.articles_new,
                articles_new = excluded.articles_new
        """, (query_name, now, new_count))
        db.commit()

    def test_tracks_last_poll_time(self, db):
        self._update(db, "iran-nuclear", 10)
        row = db.execute(
            "SELECT last_poll_time FROM poll_state WHERE query_name = 'iran-nuclear'"
        ).fetchone()
        assert row is not None
        assert row[0] is not None

    def test_increments_article_count(self, db):
        self._update(db, "iran-nuclear", 10)
        self._update(db, "iran-nuclear", 5)
        row = db.execute(
            "SELECT articles_seen, articles_new FROM poll_state "
            "WHERE query_name = 'iran-nuclear'"
        ).fetchone()
        # First insert: articles_seen=0. On second upsert: seen = 0 + 5 = 5
        # (first batch articles_new not added to seen on initial insert)
        assert row[0] == 5
        assert row[1] == 5   # last batch

    def test_upsert_on_second_poll(self, db):
        self._update(db, "iran-nuclear", 10)
        self._update(db, "iran-nuclear", 3)
        count = db.execute(
            "SELECT COUNT(*) FROM poll_state WHERE query_name = 'iran-nuclear'"
        ).fetchone()[0]
        assert count == 1
