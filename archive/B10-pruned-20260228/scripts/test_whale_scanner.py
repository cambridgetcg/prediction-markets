#!/usr/bin/env python3
"""
Tests for whale-activity-scanner.py

Run: python3 -m pytest scripts/test_whale_scanner.py -v
  or: python3 scripts/test_whale_scanner.py
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

# Add scripts dir to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import importlib
scanner = importlib.import_module("whale-activity-scanner")


# --- Test fixtures ---

MOCK_INSIDER = {
    "wallet": "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2",
    "alias": "ricosuave666",
    "account_type": "INSIDER",
    "insider_score": 10,
    "dominant_category": "GEO",
    "secondary_category": None,
    "top_category_edge": 0.4831,
    "top_category_n": 92,
    "total_profit_usd": 216497.77,
    "follow_confidence": 5,
    "last_trade": "2026-01-07T05:42:53+00:00",
}

MOCK_INSIDER_2 = {
    "wallet": "0x56687bf447db6ffa42ffe2204a05edaa20f55839",
    "alias": "Theo4",
    "account_type": "INSIDER",
    "insider_score": 10,
    "dominant_category": "POL",
    "secondary_category": None,
    "top_category_edge": 0.5433,
    "top_category_n": 681,
    "total_profit_usd": 8027218.3,
    "follow_confidence": 5,
    "last_trade": "2024-11-13T09:16:49+00:00",
}


def make_trade(direction="BUY", size_usd=10000, domain="GEO", tx_hash="0xabc123",
               market_question="Israel strikes Iran by March 31, 2026?",
               timestamp=None, wallet="0x0afc"):
    return {
        "tx_hash": tx_hash,
        "timestamp": timestamp or int(datetime.now(timezone.utc).timestamp()),
        "datetime": "2026-02-28 10:00 UTC",
        "direction": direction,
        "size_usd": size_usd,
        "from_addr": wallet,
        "to_addr": "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",
        "token_id": None,
        "market_question": market_question,
        "domain": domain,
        "_wallet": wallet,
    }


# --- Test classes ---

class TestTransactionDecoding(unittest.TestCase):
    """Tests for USDC transfer → trade conversion."""

    def test_identifies_polymarket_buy(self):
        """USDC leaving wallet TO Polymarket contract = BUY."""
        wallet = "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2"
        transfers = [{
            "hash": "0xabc123",
            "timeStamp": "1709100000",
            "value": "50000000000",  # 50,000 USDC (6 decimals)
            "from": wallet,
            "to": scanner.POLYMARKET_CONTRACTS["CTF_EXCHANGE"].lower(),
        }]
        trades = scanner.decode_usdc_transfers(transfers, wallet)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["direction"], "BUY")
        self.assertEqual(trades[0]["size_usd"], 50000.0)

    def test_identifies_polymarket_sell(self):
        """USDC entering wallet FROM Polymarket contract = SELL."""
        wallet = "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2"
        transfers = [{
            "hash": "0xdef456",
            "timeStamp": "1709100000",
            "value": "25000000000",  # 25,000 USDC
            "from": scanner.POLYMARKET_CONTRACTS["NEG_RISK_CTF"].lower(),
            "to": wallet,
        }]
        trades = scanner.decode_usdc_transfers(transfers, wallet)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["direction"], "SELL")
        self.assertEqual(trades[0]["size_usd"], 25000.0)

    def test_ignores_non_polymarket_transfers(self):
        """Transfers to/from non-Polymarket addresses are filtered out."""
        wallet = "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2"
        transfers = [{
            "hash": "0xghi789",
            "timeStamp": "1709100000",
            "value": "100000000000",  # 100K USDC
            "from": wallet,
            "to": "0x1234567890abcdef1234567890abcdef12345678",  # random address
        }]
        trades = scanner.decode_usdc_transfers(transfers, wallet)
        self.assertEqual(len(trades), 0)

    def test_filters_small_transfers(self):
        """Transfers below MIN_TRADE_USD are filtered."""
        wallet = "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2"
        transfers = [{
            "hash": "0xsmall",
            "timeStamp": "1709100000",
            "value": "50000",  # $0.05 USDC
            "from": wallet,
            "to": scanner.POLYMARKET_CONTRACTS["CTF_EXCHANGE"].lower(),
        }]
        trades = scanner.decode_usdc_transfers(transfers, wallet)
        self.assertEqual(len(trades), 0)

    def test_decodes_usdc_amount_correctly(self):
        """USDC has 6 decimals: 1000000 raw = $1.00."""
        wallet = "0x0afc7ce56285bde1fbe3a75efaffdfc86d6530b2"
        transfers = [{
            "hash": "0xamount",
            "timeStamp": "1709100000",
            "value": "12345678901",  # $12,345.678901
            "from": wallet,
            "to": scanner.POLYMARKET_CONTRACTS["CTF_EXCHANGE"].lower(),
        }]
        trades = scanner.decode_usdc_transfers(transfers, wallet)
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0]["size_usd"], 12345.68, places=1)


class TestDomainClassification(unittest.TestCase):
    """Tests for market question → domain classification."""

    def test_geo_classification(self):
        self.assertEqual(scanner.classify_domain("Israel strikes Iran by March 31?"), "GEO")

    def test_pol_classification(self):
        self.assertEqual(scanner.classify_domain("Will Trump win the 2028 election?"), "POL")

    def test_eco_classification(self):
        self.assertEqual(scanner.classify_domain("Fed interest rate cut in March?"), "ECO")

    def test_tec_classification(self):
        self.assertEqual(scanner.classify_domain("Will OpenAI release GPT-5?"), "TEC")

    def test_unknown_returns_none(self):
        self.assertIsNone(scanner.classify_domain("Will a unicorn land on Mars in July?"))

    def test_none_input(self):
        self.assertIsNone(scanner.classify_domain(None))


class TestSignalScoring(unittest.TestCase):
    """Tests for the signal scoring system."""

    def test_in_domain_high_size_high_score(self):
        """In-domain + large size + high insider score = near maximum."""
        trade = make_trade(direction="BUY", size_usd=500000, domain="GEO")
        score = scanner.score_whale_trade(trade, MOCK_INSIDER, [])
        # Domain match (3) + large size (2) + insider score 10 (2) + recent (1) = 8
        self.assertGreaterEqual(score, 7)

    def test_out_of_domain_low_score(self):
        """Out-of-domain trade scores low regardless of size."""
        trade = make_trade(direction="BUY", size_usd=500000, domain="ECO")
        score = scanner.score_whale_trade(trade, MOCK_INSIDER, [])
        # No domain match (0) + large size (2) + insider score (2) + recent (1) = 5
        self.assertLessEqual(score, 6)

    def test_secondary_domain_partial_score(self):
        """Secondary domain gets 1 point instead of 3."""
        insider = dict(MOCK_INSIDER)
        insider["secondary_category"] = "POL"
        trade = make_trade(domain="POL")
        score = scanner.score_whale_trade(trade, insider, [])
        # Secondary (1) + ... < in-domain score
        trade2 = make_trade(domain="GEO")
        score2 = scanner.score_whale_trade(trade2, insider, [])
        self.assertLess(score, score2)

    def test_multiple_insiders_convergence_bonus(self):
        """Multiple insiders on same market/direction adds +1 or +2."""
        trade = make_trade(market_question="Iran strike?", direction="BUY", wallet="0x0afc")
        other_trade = make_trade(market_question="Iran strike?", direction="BUY", wallet="0x5668")

        score_alone = scanner.score_whale_trade(trade, MOCK_INSIDER, [])
        score_convergence = scanner.score_whale_trade(trade, MOCK_INSIDER, [other_trade])
        self.assertGreater(score_convergence, score_alone)

    def test_score_capped_at_10(self):
        """Score never exceeds 10."""
        # Construct a scenario that could theoretically score >10
        trade = make_trade(direction="BUY", size_usd=10_000_000, domain="GEO")
        others = [
            make_trade(market_question=trade["market_question"], direction="BUY", wallet=f"0x{i:04d}")
            for i in range(5)
        ]
        score = scanner.score_whale_trade(trade, MOCK_INSIDER, others)
        self.assertLessEqual(score, 10)

    def test_small_trade_lower_score(self):
        """Small trade size scores lower than large."""
        small = make_trade(size_usd=500)
        large = make_trade(size_usd=500000, tx_hash="0xbig")
        score_small = scanner.score_whale_trade(small, MOCK_INSIDER, [])
        score_large = scanner.score_whale_trade(large, MOCK_INSIDER, [])
        self.assertLessEqual(score_small, score_large)


class TestDeduplication(unittest.TestCase):
    """Tests for transaction deduplication."""

    def test_same_tx_not_processed_twice(self):
        """DB-based dedup prevents reprocessing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = scanner.init_db(db_path)

            # Insert a trade
            trade = make_trade(tx_hash="0xdedup_test_123")
            trade["signal_score"] = 5
            scanner.persist_trade(conn, trade, MOCK_INSIDER)

            # Check it's seen
            self.assertTrue(scanner.is_seen(conn, "0xdedup_test_123"))
            self.assertFalse(scanner.is_seen(conn, "0xnew_trade"))

            conn.close()
        finally:
            os.unlink(db_path)

    def test_seen_set_dedup(self):
        """In-memory seen_hashes set prevents reprocessing within a cycle."""
        seen = set()
        seen.add("0xabc")
        self.assertIn("0xabc", seen)
        self.assertNotIn("0xdef", seen)

    def test_insert_or_ignore_on_duplicate(self):
        """Duplicate insert doesn't raise error."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = scanner.init_db(db_path)
            trade = make_trade(tx_hash="0xdup")
            trade["signal_score"] = 5

            # Insert twice — should not error
            scanner.persist_trade(conn, trade, MOCK_INSIDER)
            scanner.persist_trade(conn, trade, MOCK_INSIDER)

            # Only one row
            count = conn.execute("SELECT COUNT(*) FROM whale_trades WHERE tx_hash = '0xdup'").fetchone()[0]
            self.assertEqual(count, 1)

            conn.close()
        finally:
            os.unlink(db_path)


class TestAlertFormatting(unittest.TestCase):
    """Tests for alert message formatting."""

    def test_alert_contains_all_fields(self):
        """Alert message includes alias, market, direction, size, score."""
        trade = make_trade(direction="BUY", size_usd=50000, domain="GEO")
        trade["signal_score"] = 8
        trade["entry_price"] = 0.35

        msg = scanner.format_alert(trade, MOCK_INSIDER)

        self.assertIn("ricosuave666", msg)
        self.assertIn("BUY", msg)
        self.assertIn("50,000", msg)
        self.assertIn("GEO", msg)
        self.assertIn("8/10", msg)
        self.assertIn("In-domain: YES", msg)
        self.assertIn("polygonscan.com/tx/", msg)

    def test_out_of_domain_flag(self):
        """Out-of-domain trades are clearly flagged."""
        trade = make_trade(domain="ECO")
        trade["signal_score"] = 4
        msg = scanner.format_alert(trade, MOCK_INSIDER)
        self.assertIn("In-domain: NO", msg)

    def test_suggested_size_uses_quarter_kelly(self):
        """Alert includes quarter-Kelly sizing suggestion for in-domain trades."""
        trade = make_trade(direction="BUY", size_usd=50000, domain="GEO")
        trade["signal_score"] = 8
        trade["entry_price"] = 0.35

        msg = scanner.format_alert(trade, MOCK_INSIDER)
        self.assertIn("Quarter-Kelly", msg)


class TestDatabaseSchema(unittest.TestCase):
    """Tests for SQLite schema and persistence."""

    def test_db_creation(self):
        """Database and table are created correctly."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = scanner.init_db(db_path)
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = [t[0] for t in tables]
            self.assertIn("whale_trades", table_names)
            conn.close()
        finally:
            os.unlink(db_path)

    def test_indexes_created(self):
        """All three indexes are created."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = scanner.init_db(db_path)
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
            index_names = [i[0] for i in indexes]
            self.assertIn("idx_whale_domain", index_names)
            self.assertIn("idx_whale_score", index_names)
            self.assertIn("idx_whale_wallet", index_names)
            conn.close()
        finally:
            os.unlink(db_path)


class TestAlertQueue(unittest.TestCase):
    """Tests for alert queuing to JSON file."""

    def test_queue_creates_file(self):
        """Queuing an alert creates the JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_path = Path(tmpdir) / "test-alerts.json"
            # Temporarily override ALERTS_PATH
            original = scanner.ALERTS_PATH
            scanner.ALERTS_PATH = alerts_path
            try:
                trade = make_trade()
                trade["signal_score"] = 8
                scanner.queue_alert(trade, MOCK_INSIDER, "Test alert message")

                self.assertTrue(alerts_path.exists())
                data = json.loads(alerts_path.read_text())
                self.assertEqual(len(data), 1)
                self.assertEqual(data[0]["alias"], "ricosuave666")
                self.assertFalse(data[0]["delivered"])
                self.assertIn("WH-", data[0]["alert_id"])
            finally:
                scanner.ALERTS_PATH = original

    def test_queue_appends(self):
        """Subsequent alerts append to existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            alerts_path = Path(tmpdir) / "test-alerts.json"
            original = scanner.ALERTS_PATH
            scanner.ALERTS_PATH = alerts_path
            try:
                t1 = make_trade(tx_hash="0x111")
                t1["signal_score"] = 8
                scanner.queue_alert(t1, MOCK_INSIDER, "Alert 1")

                t2 = make_trade(tx_hash="0x222")
                t2["signal_score"] = 9
                scanner.queue_alert(t2, MOCK_INSIDER_2, "Alert 2")

                data = json.loads(alerts_path.read_text())
                self.assertEqual(len(data), 2)
            finally:
                scanner.ALERTS_PATH = original


# --- Run ---

if __name__ == "__main__":
    unittest.main()
