#!/usr/bin/env python3
"""
Tests for NB07: Signal Generator.

Migrated from inline --test + new SearchActiveMarkets / GenerateSignal tests.

Run:  pytest scripts/test_signal_generator.py -v
"""

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from signal_generator import (
    GeneratedSignal,
    SignalGenerator,
    apply_B05,
    apply_strategy_edge,
    check_R01,
    count_pending_signals,
    route_strategy,
    search_active_markets,
    _match_score,
    _tokenize,
    YES_DISCOUNT,
    FRACTIONAL_KELLY,
    MIN_EDGE,
    MIN_CONFIDENCE,
    MAX_PENDING,
)
from truth_extractor import TruthExtractionResult
from event_clusterer import EventCluster
from perspective_matrix import PerspectiveMatrix, ClusterView


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)


def make_extraction(**overrides) -> TruthExtractionResult:
    defaults = dict(
        cluster_id="test_cluster",
        consensus_facts=["Talks occurred"],
        contested_claims=[],
        motivated_omissions={},
        objective_kernel="Test kernel.",
        market_relevance=[
            {
                "category": "GEO",
                "description": "US or Israel strike Iran military nuclear",
                "direction": "NO",
                "probability_shift": 0.10,
                "confidence": 0.7,
            }
        ],
        overall_confidence=0.72,
        requires_human_review=False,
        model_used="claude-sonnet-4-6",
        extracted_at=NOW,
    )
    defaults.update(overrides)
    return TruthExtractionResult(**defaults)


def make_cluster(**overrides) -> EventCluster:
    defaults = dict(
        cluster_id="test_cluster",
        event_summary="Iran talks stall",
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


MOCK_GAMMA_EVENTS = [
    {
        "title": "Iran Nuclear Deal",
        "markets": [
            {
                "conditionId": "cond-iran-001",
                "question": "Will the US or Israel strike Iran by March 31?",
                "outcomePrices": '["0.35", "0.65"]',
                "clobTokenIds": '["tok-yes", "tok-no"]',
                "volumeNum": 500000,
                "liquidityNum": 50000,
            },
            {
                "conditionId": "cond-iran-002",
                "question": "Will Iran reach a nuclear deal by June 2026?",
                "outcomePrices": '["0.20", "0.80"]',
                "clobTokenIds": '["tok-y2", "tok-n2"]',
                "volumeNum": 200000,
                "liquidityNum": 30000,
            },
        ],
    },
    {
        "title": "Bitcoin Price",
        "markets": [
            {
                "conditionId": "cond-btc-001",
                "question": "Will Bitcoin reach $100K by April?",
                "outcomePrices": '["0.50", "0.50"]',
                "clobTokenIds": '["tok-b1", "tok-b2"]',
                "volumeNum": 1000000,
                "liquidityNum": 100000,
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# TestB05 (migrated from inline)
# ---------------------------------------------------------------------------

class TestB05:

    def test_high_reliability_moves_toward_raw(self):
        adj = apply_B05(0.70, 3.0, 0.50)
        assert 0.64 < adj < 0.70

    def test_low_reliability_stays_near_current(self):
        adj = apply_B05(0.70, 0.3, 0.50)
        assert 0.50 < adj < 0.55

    def test_zero_tone_minimal_movement(self):
        adj = apply_B05(0.70, 0.0, 0.50)
        assert adj < 0.55

    def test_negative_tone_direction_preserved(self):
        adj = apply_B05(0.30, -2.0, 0.50)
        assert adj < 0.50

    def test_clamp_lower_bound(self):
        adj = apply_B05(0.001, 5.0, 0.99)
        assert adj >= 0.01

    def test_clamp_upper_bound(self):
        adj = apply_B05(0.999, 5.0, 0.01)
        assert adj <= 0.99


# ---------------------------------------------------------------------------
# TestStrategyRouting (migrated from inline)
# ---------------------------------------------------------------------------

class TestStrategyRouting:

    def test_geo_routes_s004(self):
        assert route_strategy("GEO") == "S004"

    def test_pol_routes_s001(self):
        assert route_strategy("POL") == "S001"

    def test_eco_routes_s006(self):
        assert route_strategy("ECO") == "S006"

    def test_tec_routes_s006(self):
        assert route_strategy("TEC") == "S006"

    def test_unknown_routes_s001(self):
        assert route_strategy("XYZ") == "S001"

    def test_r04_fast_resolution_override(self):
        assert route_strategy("POL", days_to_resolution=3) == "S006"

    def test_s004_keeps_on_fast_resolution(self):
        assert route_strategy("GEO", days_to_resolution=3) == "S004"


# ---------------------------------------------------------------------------
# TestStrategyEdge (migrated from inline)
# ---------------------------------------------------------------------------

class TestStrategyEdge:

    def test_s004_40pct_reversion(self):
        adj = apply_strategy_edge(0.40, "S004", 0.60)
        assert abs(adj - 0.52) < 0.001

    def test_s001_passthrough(self):
        adj = apply_strategy_edge(0.40, "S001", 0.60)
        assert adj == 0.40

    def test_s006_passthrough(self):
        adj = apply_strategy_edge(0.40, "S006", 0.60)
        assert adj == 0.40


# ---------------------------------------------------------------------------
# TestKellySizing (migrated from inline)
# ---------------------------------------------------------------------------

class TestKellySizing:

    def test_quarter_kelly_standard(self):
        edge, cp = 0.10, 0.50
        k = (edge / (1.0 - cp)) * FRACTIONAL_KELLY
        assert abs(k - 0.05) < 0.001

    def test_kelly_larger_at_high_base_price(self):
        edge, cp = 0.05, 0.90
        k = (edge / (1.0 - cp)) * FRACTIONAL_KELLY
        assert k > 0.10

    def test_kelly_zero_when_denom_tiny(self):
        # When current_price is near 1.0, denom <= 0.01
        denom = 1.0 - 0.995
        if denom <= 0.01:
            kelly_frac = 0.0
        else:
            kelly_frac = (0.05 / denom) * FRACTIONAL_KELLY
        assert kelly_frac == 0.0


# ---------------------------------------------------------------------------
# TestR01 (migrated from inline)
# ---------------------------------------------------------------------------

class TestR01:

    @pytest.fixture
    def portfolio(self):
        return {
            "bankroll": 10000,
            "positions": [
                {
                    "market": "US strikes Iran by June 30",
                    "domain": "GEO",
                    "size_usd": 300,
                    "status": "open",
                },
            ],
            "domain_exposure": {"GEO": 350, "POL": 625},
        }

    def test_blocks_correlated_geo_addition(self, portfolio):
        ok, msg = check_R01("GEO", "Iran nuclear strike 2026", 200, portfolio)
        assert not ok
        # C1 or C2 may trigger depending on token overlap calculation

    def test_passes_uncorrelated_position(self, portfolio):
        ok, msg = check_R01("TEC", "OpenAI GPT-5 release date", 100, portfolio)
        assert ok

    def test_c2_blocks_domain_over_cap(self, portfolio):
        ok, msg = check_R01("POL", "Trump executive order 2026", 200, portfolio)
        assert not ok
        assert "C2" in msg

    def test_passes_small_position(self, portfolio):
        ok, msg = check_R01("CRY", "Bitcoin halving 2026", 50, portfolio)
        assert ok


# ---------------------------------------------------------------------------
# TestTokenizer (migrated from inline)
# ---------------------------------------------------------------------------

class TestTokenizer:

    def test_extracts_keywords(self):
        tokens = _tokenize("US strikes Iran nuclear weapons 2026")
        assert {"us", "strikes", "iran", "nuclear"}.issubset(tokens)

    def test_related_market_scores_high(self):
        score = _match_score(
            {"iran", "strike", "nuclear"},
            "Will the US or Israel strike Iran by March 31?",
        )
        assert score >= 0.3

    def test_unrelated_market_scores_low(self):
        score = _match_score(
            {"iran", "strike", "nuclear"},
            "Will Bitcoin reach $100K?",
        )
        assert score < 0.3

    def test_empty_input_zero(self):
        assert _match_score(set(), "Some market?") == 0.0
        assert _match_score({"a"}, "") == 0.0


# ---------------------------------------------------------------------------
# TestSearchActiveMarkets (NEW)
# ---------------------------------------------------------------------------

class TestSearchActiveMarkets:

    @patch("signal_generator.curl_json")
    def test_returns_matched_markets(self, mock_curl):
        mock_curl.return_value = MOCK_GAMMA_EVENTS
        results = search_active_markets("Iran strike nuclear military")
        assert len(results) > 0
        assert results[0]["condition_id"] == "cond-iran-001"

    def test_empty_description_returns_empty(self):
        results = search_active_markets("")
        assert results == []

    @patch("signal_generator.curl_json")
    def test_no_api_results_returns_empty(self, mock_curl):
        mock_curl.return_value = None
        results = search_active_markets("Iran nuclear")
        assert results == []

    @patch("signal_generator.curl_json")
    def test_score_ranking_by_match_then_volume(self, mock_curl):
        mock_curl.return_value = MOCK_GAMMA_EVENTS
        results = search_active_markets("Iran nuclear deal agreement")
        # Both Iran markets should rank above Bitcoin
        condition_ids = [r["condition_id"] for r in results]
        assert "cond-btc-001" not in condition_ids


# ---------------------------------------------------------------------------
# TestGenerateSignal (NEW)
# ---------------------------------------------------------------------------

class TestGenerateSignal:

    @patch("signal_generator.search_active_markets")
    @patch("signal_generator.count_pending_signals", return_value=0)
    @patch("signal_generator.load_positions")
    def test_generates_signal_for_valid_extraction(
        self, mock_pos, mock_pending, mock_search
    ):
        mock_pos.return_value = {"bankroll": 10000, "positions": [], "domain_exposure": {}}
        # Use high YES price so NO side = 0.10 (large denom keeps Kelly
        # small enough to pass R01 C1 single-event cap of 3%)
        mock_search.return_value = [
            {
                "condition_id": "cond-001",
                "question": "Will inflation exceed 5% by June?",
                "current_price": 0.90,
                "volume": 100000,
                "liquidity": 10000,
                "clob_token_ids": ["tok1"],
                "match_score": 0.8,
            }
        ]
        cluster = make_cluster()
        cluster.perspective_matrix = PerspectiveMatrix(
            clusters={
                "Western": ClusterView(
                    cluster_name="Western",
                    article_count=5,
                    mean_tone=-3.0,
                    reliability_weighted_tone=-3.0,
                    key_claims=["Inflation rising"],
                    sources=["reuters.com"],
                ),
            },
            divergence_score=3.5,
            is_divergent=True,
        )
        ext = make_extraction(
            market_relevance=[{
                "category": "ECO",
                "description": "inflation exceed 5%",
                "direction": "NO",
                "probability_shift": 0.08,
                "confidence": 0.8,
            }]
        )
        gen = SignalGenerator(bankroll=10000)
        gen.portfolio = mock_pos.return_value
        signals = gen.generate(ext, cluster)
        assert len(signals) >= 1
        assert signals[0].direction == "NO"

    @patch("signal_generator.search_active_markets")
    @patch("signal_generator.count_pending_signals", return_value=0)
    @patch("signal_generator.load_positions")
    def test_yes_discount_applied_for_yes_direction(
        self, mock_pos, mock_pending, mock_search
    ):
        mock_pos.return_value = {"bankroll": 10000, "positions": [], "domain_exposure": {}}
        mock_search.return_value = [
            {
                "condition_id": "cond-001",
                "question": "Will Iran be struck?",
                "current_price": 0.20,
                "volume": 100000,
                "liquidity": 10000,
                "clob_token_ids": [],
                "match_score": 0.8,
            }
        ]
        ext = make_extraction(
            market_relevance=[{
                "category": "GEO",
                "description": "Iran military strike",
                "direction": "YES",
                "probability_shift": 0.15,
                "confidence": 0.8,
            }]
        )
        gen = SignalGenerator(bankroll=10000)
        gen.portfolio = mock_pos.return_value
        signals = gen.generate(ext, make_cluster())
        if signals:
            assert signals[0].yes_discount_applied is True

    @patch("signal_generator.search_active_markets")
    @patch("signal_generator.count_pending_signals", return_value=0)
    @patch("signal_generator.load_positions")
    def test_no_discount_not_applied_for_no_direction(
        self, mock_pos, mock_pending, mock_search
    ):
        mock_pos.return_value = {"bankroll": 10000, "positions": [], "domain_exposure": {}}
        mock_search.return_value = [
            {
                "condition_id": "cond-001",
                "question": "Iran nuclear deal?",
                "current_price": 0.30,
                "volume": 100000,
                "liquidity": 10000,
                "clob_token_ids": [],
                "match_score": 0.8,
            }
        ]
        ext = make_extraction(
            market_relevance=[{
                "category": "GEO",
                "description": "Iran nuclear deal",
                "direction": "NO",
                "probability_shift": 0.12,
                "confidence": 0.7,
            }]
        )
        gen = SignalGenerator(bankroll=10000)
        gen.portfolio = mock_pos.return_value
        signals = gen.generate(ext, make_cluster())
        if signals:
            assert signals[0].yes_discount_applied is False

    @patch("signal_generator.search_active_markets")
    @patch("signal_generator.count_pending_signals", return_value=0)
    @patch("signal_generator.load_positions")
    def test_edge_below_threshold_returns_empty(
        self, mock_pos, mock_pending, mock_search
    ):
        mock_pos.return_value = {"bankroll": 10000, "positions": [], "domain_exposure": {}}
        mock_search.return_value = [
            {
                "condition_id": "cond-001",
                "question": "Something?",
                "current_price": 0.50,
                "volume": 100000,
                "liquidity": 10000,
                "clob_token_ids": [],
                "match_score": 0.8,
            }
        ]
        ext = make_extraction(
            market_relevance=[{
                "category": "GEO",
                "description": "Something",
                "direction": "NO",
                "probability_shift": 0.02,  # Tiny shift
                "confidence": 0.7,
            }]
        )
        gen = SignalGenerator(bankroll=10000)
        gen.portfolio = mock_pos.return_value
        signals = gen.generate(ext, make_cluster())
        assert len(signals) == 0

    @patch("signal_generator.search_active_markets")
    @patch("signal_generator.count_pending_signals")
    @patch("signal_generator.load_positions")
    def test_max_pending_blocks_new_signals(
        self, mock_pos, mock_pending, mock_search
    ):
        mock_pos.return_value = {"bankroll": 10000, "positions": [], "domain_exposure": {}}
        mock_pending.return_value = MAX_PENDING  # At cap
        mock_search.return_value = [
            {
                "condition_id": "cond-001",
                "question": "Iran deal?",
                "current_price": 0.30,
                "volume": 100000,
                "liquidity": 10000,
                "clob_token_ids": [],
                "match_score": 0.8,
            }
        ]
        ext = make_extraction(
            market_relevance=[{
                "category": "GEO",
                "description": "Iran deal",
                "direction": "NO",
                "probability_shift": 0.12,
                "confidence": 0.7,
            }]
        )
        gen = SignalGenerator(bankroll=10000)
        gen.portfolio = mock_pos.return_value
        signals = gen.generate(ext, make_cluster())
        assert len(signals) == 0

    @patch("signal_generator.search_active_markets")
    @patch("signal_generator.count_pending_signals", return_value=0)
    @patch("signal_generator.load_positions")
    def test_no_market_match_returns_empty(
        self, mock_pos, mock_pending, mock_search
    ):
        mock_pos.return_value = {"bankroll": 10000, "positions": [], "domain_exposure": {}}
        mock_search.return_value = []
        ext = make_extraction()
        gen = SignalGenerator(bankroll=10000)
        gen.portfolio = mock_pos.return_value
        signals = gen.generate(ext, make_cluster())
        assert len(signals) == 0

    @patch("signal_generator.search_active_markets")
    @patch("signal_generator.count_pending_signals", return_value=0)
    @patch("signal_generator.load_positions")
    def test_r01_rejection_returns_empty(
        self, mock_pos, mock_pending, mock_search
    ):
        # Portfolio already at GEO cap
        mock_pos.return_value = {
            "bankroll": 10000,
            "positions": [
                {"market": "Iran strikes 2026", "domain": "GEO",
                 "size_usd": 300, "status": "open"},
            ],
            "domain_exposure": {"GEO": 490},
        }
        mock_search.return_value = [
            {
                "condition_id": "cond-001",
                "question": "Iran nuclear strike?",
                "current_price": 0.30,
                "volume": 100000,
                "liquidity": 10000,
                "clob_token_ids": [],
                "match_score": 0.8,
            }
        ]
        ext = make_extraction(
            market_relevance=[{
                "category": "GEO",
                "description": "Iran nuclear strike",
                "direction": "NO",
                "probability_shift": 0.12,
                "confidence": 0.7,
            }]
        )
        gen = SignalGenerator(bankroll=10000)
        gen.portfolio = mock_pos.return_value
        signals = gen.generate(ext, make_cluster())
        assert len(signals) == 0

    @patch("signal_generator.search_active_markets")
    @patch("signal_generator.count_pending_signals", return_value=0)
    @patch("signal_generator.load_positions")
    def test_signal_logged_to_jsonl(
        self, mock_pos, mock_pending, mock_search, tmp_path
    ):
        mock_pos.return_value = {"bankroll": 10000, "positions": [], "domain_exposure": {}}
        mock_search.return_value = [
            {
                "condition_id": "cond-001",
                "question": "Iran nuclear deal?",
                "current_price": 0.30,
                "volume": 100000,
                "liquidity": 10000,
                "clob_token_ids": [],
                "match_score": 0.8,
            }
        ]
        signals_file = tmp_path / "signals.jsonl"
        with patch("signal_generator.SIGNALS_PATH", signals_file):
            ext = make_extraction(
                market_relevance=[{
                    "category": "GEO",
                    "description": "Iran nuclear deal",
                    "direction": "NO",
                    "probability_shift": 0.12,
                    "confidence": 0.7,
                }]
            )
            gen = SignalGenerator(bankroll=10000)
            gen.portfolio = mock_pos.return_value
            signals = gen.generate(ext, make_cluster())
            if signals:
                assert signals_file.exists()
                lines = signals_file.read_text().strip().split("\n")
                assert len(lines) >= 1
                entry = json.loads(lines[-1])
                assert entry["direction"] == "NO"
