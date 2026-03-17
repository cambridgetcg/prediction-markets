#!/usr/bin/env python3
"""
Tests for convergence_engine.py

Run: python3 -m pytest scripts/test_convergence_engine.py -v
  or: python3 scripts/test_convergence_engine.py
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent))

from convergence_engine import (
    NewsSignal,
    WhaleSignal,
    FreshWalletSignal,
    ConvergenceSignal,
    tokenize,
    jaccard_similarity,
    fuzzy_market_match,
    extract_market_key,
    group_signals_by_market,
    determine_convergence_level,
    compute_convergence_confidence,
    compute_sizing,
    find_matching_position,
    check_position_agreement,
    get_majority_direction,
    build_convergence_signal,
    format_convergence_alert,
    init_convergence_table,
    persist_signal,
)


# --- Fixtures ---

def make_news(question="Will US strike Iran by June 30?", direction="NO",
              confidence=0.7, edge=0.15, price=0.35, prob=0.20) -> NewsSignal:
    return NewsSignal(
        signal_id="SIG-test001",
        market_question=question,
        market_id="mkt-001",
        direction=direction,
        current_price=price,
        suggested_probability=prob,
        edge=edge,
        confidence=confidence,
        cluster_id="CL-001",
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def make_whale(question="Will US strike Iran by June 30?", direction="SELL",
               alias="ricosuave666", insider_score=9.0, signal_score=8.0,
               size_usd=15000, in_domain=True, domain="GEO",
               entry_price=0.47) -> WhaleSignal:
    return WhaleSignal(
        tx_hash="0xabc123def456",
        wallet="0x1234567890abcdef1234567890abcdef12345678",
        alias=alias,
        insider_score=insider_score,
        domain=domain,
        market_id="mkt-001",
        market_question=question,
        direction=direction,
        size_usd=size_usd,
        entry_price=entry_price,
        signal_score=signal_score,
        in_domain=in_domain,
        detected_at=datetime.now(timezone.utc).isoformat(),
    )


def make_fresh(question="Will US strike Iran by June 30?", direction="NO",
               anomaly_score=8, trade_size_usd=8000, wallet_age_days=3,
               wallet_txn_count=2) -> FreshWalletSignal:
    return FreshWalletSignal(
        wallet="0x7a3f000000000000000000000000000000000001",
        market_question=question,
        domain="GEO",
        direction=direction,
        trade_size_usd=trade_size_usd,
        entry_price=0.46,
        anomaly_score=anomaly_score,
        wallet_age_days=wallet_age_days,
        wallet_txn_count=wallet_txn_count,
        funding_source="Coinbase",
        is_cluster=False,
        detected_at=datetime.now(timezone.utc).isoformat(),
    )


POSITIONS = [
    {
        "trade_id": "T001",
        "strategy": "S004",
        "domain": "GEO",
        "market": "US strikes Iran by June 30, 2026",
        "direction": "NO",
        "entry_price": 0.335,
        "status": "open",
    },
    {
        "trade_id": "T002",
        "strategy": "S001",
        "domain": "POL",
        "market": "Will Donald Trump win the 2028 Republican presidential nomination?",
        "direction": "NO",
        "entry_price": 0.972,
        "status": "open",
    },
]


# --- Test: Convergence Level ---

class TestConvergenceLevel(unittest.TestCase):

    def test_news_only_level_1(self):
        level = determine_convergence_level(has_news=True, has_whale=False, has_fresh=False)
        self.assertEqual(level, 1)

    def test_news_plus_whale_level_2(self):
        level = determine_convergence_level(has_news=True, has_whale=True, has_fresh=False)
        self.assertEqual(level, 2)

    def test_news_plus_fresh_level_3(self):
        level = determine_convergence_level(has_news=True, has_whale=False, has_fresh=True)
        self.assertEqual(level, 3)

    def test_whale_plus_fresh_level_4(self):
        level = determine_convergence_level(has_news=False, has_whale=True, has_fresh=True)
        self.assertEqual(level, 4)

    def test_all_three_level_5(self):
        level = determine_convergence_level(has_news=True, has_whale=True, has_fresh=True)
        self.assertEqual(level, 5)

    def test_no_sources_level_0(self):
        level = determine_convergence_level(has_news=False, has_whale=False, has_fresh=False)
        self.assertEqual(level, 0)

    def test_whale_only_level_1(self):
        level = determine_convergence_level(has_news=False, has_whale=True, has_fresh=False)
        self.assertEqual(level, 1)

    def test_fresh_only_level_1(self):
        level = determine_convergence_level(has_news=False, has_whale=False, has_fresh=True)
        self.assertEqual(level, 1)


# --- Test: Market Matching ---

class TestMarketMatching(unittest.TestCase):

    def test_exact_match(self):
        self.assertTrue(fuzzy_market_match(
            "Will US strike Iran by June 30?",
            "Will US strike Iran by June 30?",
        ))

    def test_exact_match_case_insensitive(self):
        self.assertTrue(fuzzy_market_match(
            "Will US Strike Iran by June 30?",
            "will us strike iran by june 30?",
        ))

    def test_fuzzy_text_match(self):
        self.assertTrue(fuzzy_market_match(
            "Will US strike Iran by June 30?",
            "US strikes Iran by June 30, 2026",
        ))

    def test_different_markets_no_match(self):
        self.assertFalse(fuzzy_market_match(
            "Will US strike Iran by June 30?",
            "Will Bitcoin reach $150,000 by December 31?",
        ))

    def test_similar_but_different_dates(self):
        """Markets with same topic but different dates should still match on topic."""
        # These share enough keywords to pass threshold
        result = fuzzy_market_match(
            "Will US strike Iran by March 31?",
            "Will US strike Iran by June 30?",
            threshold=0.5,
        )
        # These should match — same topic, different dates
        self.assertTrue(result)

    def test_empty_strings(self):
        self.assertFalse(fuzzy_market_match("", ""))
        self.assertFalse(fuzzy_market_match("some market", ""))
        self.assertFalse(fuzzy_market_match("", "some market"))

    def test_tokenize_removes_stop_words(self):
        tokens = tokenize("Will the price of Bitcoin be above $66,000?")
        self.assertNotIn("will", tokens)
        self.assertNotIn("the", tokens)
        self.assertNotIn("of", tokens)
        self.assertNotIn("be", tokens)
        self.assertIn("bitcoin", tokens)
        self.assertIn("price", tokens)

    def test_tokenize_keeps_years(self):
        tokens = tokenize("Trump wins 2028 election")
        self.assertIn("2028", tokens)

    def test_jaccard_identical(self):
        s = {"a", "b", "c"}
        self.assertEqual(jaccard_similarity(s, s), 1.0)

    def test_jaccard_disjoint(self):
        self.assertEqual(jaccard_similarity({"a", "b"}, {"c", "d"}), 0.0)

    def test_jaccard_partial(self):
        # {a, b, c} & {b, c, d} = {b, c}, union = {a, b, c, d}
        self.assertAlmostEqual(
            jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"}),
            2 / 4,
        )


# --- Test: Confidence Calculation ---

class TestConfidenceCalculation(unittest.TestCase):

    def test_single_news_moderate(self):
        """Single news source should give moderate confidence."""
        conf = compute_convergence_confidence(
            news=make_news(confidence=0.8),
            whale=None,
            fresh=None,
        )
        # 1 - (1 - 0.8*0.7) = 1 - (1 - 0.56) = 0.56
        self.assertAlmostEqual(conf, 0.56, places=2)

    def test_two_sources_higher(self):
        """Two sources should give higher confidence than one."""
        conf_one = compute_convergence_confidence(
            news=make_news(confidence=0.8),
            whale=None,
            fresh=None,
        )
        conf_two = compute_convergence_confidence(
            news=make_news(confidence=0.8),
            whale=make_whale(insider_score=8),
            fresh=None,
        )
        self.assertGreater(conf_two, conf_one)

    def test_three_sources_highest(self):
        """Three sources should give highest confidence."""
        conf_two = compute_convergence_confidence(
            news=make_news(confidence=0.8),
            whale=make_whale(insider_score=8),
            fresh=None,
        )
        conf_three = compute_convergence_confidence(
            news=make_news(confidence=0.8),
            whale=make_whale(insider_score=8),
            fresh=make_fresh(anomaly_score=7),
        )
        self.assertGreater(conf_three, conf_two)

    def test_out_of_domain_whale_discounted(self):
        """Out-of-domain whale should have lower confidence contribution."""
        conf_in = compute_convergence_confidence(
            news=None,
            whale=make_whale(in_domain=True, insider_score=8),
            fresh=None,
        )
        conf_out = compute_convergence_confidence(
            news=None,
            whale=make_whale(in_domain=False, insider_score=8),
            fresh=None,
        )
        self.assertGreater(conf_in, conf_out)

    def test_no_sources_zero(self):
        conf = compute_convergence_confidence(None, None, None)
        self.assertEqual(conf, 0.0)

    def test_confidence_bounded(self):
        """Confidence should never exceed 1.0."""
        conf = compute_convergence_confidence(
            news=make_news(confidence=1.0),
            whale=make_whale(insider_score=10, in_domain=True),
            fresh=make_fresh(anomaly_score=10),
        )
        self.assertLessEqual(conf, 1.0)
        self.assertGreater(conf, 0.0)


# --- Test: Direction Conflict ---

class TestDirectionConflict(unittest.TestCase):

    def test_all_agree_no_conflict(self):
        direction, conflict = get_majority_direction(
            [make_news(direction="NO")],
            [make_whale(direction="SELL")],  # SELL → NO
            [make_fresh(direction="NO")],
        )
        self.assertEqual(direction, "NO")
        self.assertFalse(conflict)

    def test_disagreement_detected(self):
        direction, conflict = get_majority_direction(
            [make_news(direction="NO")],
            [make_whale(direction="BUY")],  # BUY → YES, disagrees
            [make_fresh(direction="YES")],
        )
        self.assertTrue(conflict)
        # Majority: 2 YES vs 1 NO
        self.assertEqual(direction, "YES")

    def test_single_source_no_conflict(self):
        direction, conflict = get_majority_direction(
            [make_news(direction="YES")],
            [],
            [],
        )
        self.assertEqual(direction, "YES")
        self.assertFalse(conflict)

    def test_no_signals_no_direction(self):
        direction, conflict = get_majority_direction([], [], [])
        self.assertIsNone(direction)
        self.assertFalse(conflict)

    def test_whale_buy_maps_to_yes(self):
        """Verify BUY → YES mapping."""
        whale = make_whale(direction="BUY")
        self.assertEqual(whale.normalized_direction, "YES")

    def test_whale_sell_maps_to_no(self):
        """Verify SELL → NO mapping."""
        whale = make_whale(direction="SELL")
        self.assertEqual(whale.normalized_direction, "NO")


# --- Test: Sizing ---

class TestSizing(unittest.TestCase):

    def test_level_1_zero_sizing(self):
        label, usd = compute_sizing(
            convergence_level=1,
            combined_confidence=0.7,
            current_price=0.5,
            direction="YES",
            bankroll=10000,
        )
        self.assertEqual(label, "paper-only")
        self.assertEqual(usd, 0.0)

    def test_level_2_quarter_kelly(self):
        label, usd = compute_sizing(
            convergence_level=2,
            combined_confidence=0.7,
            current_price=0.4,
            direction="YES",
            bankroll=10000,
        )
        self.assertEqual(label, "quarter-kelly")
        self.assertGreater(usd, 0)

    def test_level_4_half_kelly(self):
        label, usd = compute_sizing(
            convergence_level=4,
            combined_confidence=0.7,
            current_price=0.4,
            direction="YES",
            bankroll=10000,
        )
        self.assertEqual(label, "half-kelly")
        self.assertGreater(usd, 0)

    def test_level_5_half_kelly(self):
        label, usd = compute_sizing(
            convergence_level=5,
            combined_confidence=0.8,
            current_price=0.4,
            direction="YES",
            bankroll=10000,
        )
        self.assertEqual(label, "half-kelly")
        self.assertGreater(usd, 0)

    def test_c1_cap_applied(self):
        """Position should never exceed 3% of bankroll."""
        _, usd = compute_sizing(
            convergence_level=5,
            combined_confidence=0.95,
            current_price=0.1,
            direction="YES",
            bankroll=10000,
        )
        self.assertLessEqual(usd, 300.0)  # 3% of 10000

    def test_no_edge_no_trade(self):
        """No trade when edge is below threshold."""
        label, usd = compute_sizing(
            convergence_level=5,
            combined_confidence=0.5,
            current_price=0.5,
            direction="YES",
            bankroll=10000,
        )
        self.assertEqual(label, "no-edge")
        self.assertEqual(usd, 0.0)

    def test_half_kelly_bigger_than_quarter(self):
        """Half-Kelly should produce larger sizing than quarter-Kelly."""
        # Use small edge so neither hits the C1 cap (3% = $300)
        _, usd_quarter = compute_sizing(
            convergence_level=2,
            combined_confidence=0.555,
            current_price=0.5,
            direction="YES",
            bankroll=10000,
        )
        _, usd_half = compute_sizing(
            convergence_level=4,
            combined_confidence=0.555,
            current_price=0.5,
            direction="YES",
            bankroll=10000,
        )
        self.assertGreater(usd_half, usd_quarter)

    def test_no_direction_sizing(self):
        """NO direction sizing works correctly."""
        label, usd = compute_sizing(
            convergence_level=3,
            combined_confidence=0.3,  # We think 30% YES → 70% NO
            current_price=0.5,        # Market says 50% YES
            direction="NO",
            bankroll=10000,
        )
        # Edge for NO: current_price - combined_confidence = 0.5 - 0.3 = 0.2
        self.assertEqual(label, "quarter-kelly")
        self.assertGreater(usd, 0)


# --- Test: Portfolio Agreement ---

class TestPortfolioAgreement(unittest.TestCase):

    def test_signal_agrees_with_existing(self):
        pos = find_matching_position("Will US strike Iran by June 30?", POSITIONS)
        self.assertIsNotNone(pos)
        agrees = check_position_agreement(pos, "NO")
        self.assertTrue(agrees)

    def test_signal_contradicts_existing(self):
        pos = find_matching_position("Will US strike Iran by June 30?", POSITIONS)
        self.assertIsNotNone(pos)
        agrees = check_position_agreement(pos, "YES")
        self.assertFalse(agrees)

    def test_no_existing_position(self):
        pos = find_matching_position("Will Bitcoin hit $1M by 2030?", POSITIONS)
        self.assertIsNone(pos)
        agrees = check_position_agreement(pos, "YES")
        self.assertIsNone(agrees)

    def test_fuzzy_position_match(self):
        """Position matching should handle slight text differences."""
        pos = find_matching_position(
            "US strikes Iran by June 30, 2026", POSITIONS)
        self.assertIsNotNone(pos)
        self.assertEqual(pos["trade_id"], "T001")


# --- Test: Signal Grouping ---

class TestSignalGrouping(unittest.TestCase):

    def test_same_market_grouped(self):
        news = [make_news("Will US strike Iran by June 30?")]
        whales = [make_whale("Will US strike Iran by June 30?")]
        fresh = [make_fresh("Will US strike Iran by June 30?")]

        groups = group_signals_by_market(news, whales, fresh)
        self.assertEqual(len(groups), 1)
        key = list(groups.keys())[0]
        self.assertEqual(len(groups[key]["news"]), 1)
        self.assertEqual(len(groups[key]["whale"]), 1)
        self.assertEqual(len(groups[key]["fresh"]), 1)

    def test_different_markets_separate(self):
        news = [make_news("Will US strike Iran by June 30?")]
        whales = [make_whale("Will Bitcoin reach $150,000?")]
        fresh = []

        groups = group_signals_by_market(news, whales, fresh)
        self.assertEqual(len(groups), 2)

    def test_fuzzy_match_groups_together(self):
        news = [make_news("Will US strike Iran by June 30?")]
        whales = [make_whale("US strikes Iran by June 30, 2026")]
        fresh = []

        groups = group_signals_by_market(news, whales, fresh)
        self.assertEqual(len(groups), 1)


# --- Test: Full Convergence Signal Building ---

class TestBuildConvergenceSignal(unittest.TestCase):

    def test_two_source_convergence(self):
        sig = build_convergence_signal(
            market_question="Will US strike Iran by June 30?",
            market_id="mkt-001",
            news_signals=[make_news(direction="NO")],
            whale_signals=[make_whale(direction="SELL")],
            fresh_signals=[],
            positions=POSITIONS,
            bankroll=10000,
        )
        self.assertIsNotNone(sig)
        self.assertEqual(sig.convergence_level, 2)
        self.assertEqual(sig.direction, "NO")
        self.assertFalse(sig.conflict_detected)

    def test_triple_convergence(self):
        sig = build_convergence_signal(
            market_question="Will US strike Iran by June 30?",
            market_id="mkt-001",
            news_signals=[make_news(direction="NO")],
            whale_signals=[make_whale(direction="SELL")],
            fresh_signals=[make_fresh(direction="NO")],
            positions=POSITIONS,
            bankroll=10000,
        )
        self.assertIsNotNone(sig)
        self.assertEqual(sig.convergence_level, 5)
        self.assertEqual(sig.direction, "NO")
        self.assertTrue(sig.agrees_with_position)  # T001 is NO

    def test_single_source_returns_none(self):
        sig = build_convergence_signal(
            market_question="Will US strike Iran by June 30?",
            market_id="mkt-001",
            news_signals=[make_news()],
            whale_signals=[],
            fresh_signals=[],
            positions=[],
            bankroll=10000,
        )
        self.assertIsNone(sig)

    def test_conflict_detected_no_sizing(self):
        sig = build_convergence_signal(
            market_question="Will US strike Iran by June 30?",
            market_id="mkt-001",
            news_signals=[make_news(direction="NO")],
            whale_signals=[make_whale(direction="BUY")],  # BUY → YES, conflicts
            fresh_signals=[],
            positions=[],
            bankroll=10000,
        )
        self.assertIsNotNone(sig)
        self.assertTrue(sig.conflict_detected)
        self.assertEqual(sig.suggested_sizing, "paper-only")
        self.assertEqual(sig.kelly_usd, 0.0)


# --- Test: Alert Formatting ---

class TestAlertFormatting(unittest.TestCase):

    def test_convergence_alert_has_key_fields(self):
        sig = build_convergence_signal(
            market_question="Will US strike Iran by June 30?",
            market_id="mkt-001",
            news_signals=[make_news(direction="NO", confidence=0.8)],
            whale_signals=[make_whale(direction="SELL", alias="ricosuave666")],
            fresh_signals=[make_fresh(direction="NO", anomaly_score=8)],
            positions=POSITIONS,
            bankroll=10000,
        )
        alert = format_convergence_alert(sig)
        self.assertIn("CONVERGENCE SIGNAL", alert)
        self.assertIn("Level 5/5", alert)
        self.assertIn("Iran", alert)
        self.assertIn("NEWS", alert)
        self.assertIn("WHALE", alert)
        self.assertIn("ricosuave666", alert)
        self.assertIn("FRESH WALLET", alert)

    def test_conflict_alert_format(self):
        sig = build_convergence_signal(
            market_question="Will US strike Iran by June 30?",
            market_id="mkt-001",
            news_signals=[make_news(direction="NO")],
            whale_signals=[make_whale(direction="BUY")],
            fresh_signals=[],
            positions=[],
            bankroll=10000,
        )
        alert = format_convergence_alert(sig)
        self.assertIn("SIGNAL CONFLICT", alert)
        self.assertIn("DO NOT TRADE", alert)


# --- Test: SQLite Persistence ---

class TestPersistence(unittest.TestCase):

    def test_init_and_persist(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            conn = init_convergence_table(tmp_path)

            sig = ConvergenceSignal(
                signal_id="CV-test-001",
                market_question="Test market",
                market_id="mkt-test",
                direction="YES",
                convergence_level=3,
                news_signal={"confidence": 0.8},
                whale_signal=None,
                fresh_wallet_signal={"anomaly_score": 7},
                combined_confidence=0.65,
                suggested_sizing="quarter-kelly",
                kelly_usd=150.0,
                our_position=None,
                agrees_with_position=None,
                generated_at=datetime.now(timezone.utc).isoformat(),
                status="pending",
                conflict_detected=False,
                conflict_detail=None,
            )

            persist_signal(conn, sig)

            # Read back
            row = conn.execute(
                "SELECT * FROM convergence_signals WHERE signal_id = ?",
                ("CV-test-001",)
            ).fetchone()

            self.assertIsNotNone(row)
            conn.close()
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_replace_on_duplicate(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            conn = init_convergence_table(tmp_path)

            sig = ConvergenceSignal(
                signal_id="CV-dup-001",
                market_question="Dup test",
                market_id=None,
                direction="NO",
                convergence_level=2,
                news_signal=None,
                whale_signal=None,
                fresh_wallet_signal=None,
                combined_confidence=0.5,
                suggested_sizing="quarter-kelly",
                kelly_usd=100.0,
                our_position=None,
                agrees_with_position=None,
                generated_at=datetime.now(timezone.utc).isoformat(),
                status="pending",
            )

            persist_signal(conn, sig)

            # Update status and re-persist
            sig.status = "approved"
            persist_signal(conn, sig)

            count = conn.execute(
                "SELECT COUNT(*) FROM convergence_signals WHERE signal_id = ?",
                ("CV-dup-001",)
            ).fetchone()[0]
            self.assertEqual(count, 1)

            conn.close()
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
