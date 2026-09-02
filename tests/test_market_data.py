import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "engine" / "market_data.py"
SPEC = importlib.util.spec_from_file_location("market_data", MODULE_PATH)
market_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(market_data)


class MarketDataTests(unittest.TestCase):
    def test_parse_price_is_fail_closed(self):
        cases = [
            (None, None),
            (True, None),
            ("not-a-price", None),
            (1.1, None),
            (-0.1, None),
            ('["0.73", "0.27"]', 0.73),
            (["0.42", "0.58"], 0.42),
            (0.0, 0.0),
            (1.0, 1.0),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(market_data._parse_price(raw), expected)

    def test_default_access_file_blocks_every_source(self):
        for source in ("polymarket", "kalshi", "manifold"):
            with self.subTest(source=source):
                self.assertFalse(market_data.market_data_access(source)["authorised"])

    def test_authority_requires_complete_current_record(self):
        record = {
            "version": 1,
            "sources": {
                "example": {
                    "automated_read": "authorised",
                    "jurisdiction": "allowed",
                    "data_rights": "allowed",
                    "authority": "Written permission reference 123",
                    "scope": "Private research snapshots",
                    "use_location": "Switzerland",
                    "source_url": "https://example.test/terms",
                    "reviewed_on": "2026-09-02",
                    "next_review": "2099-01-01",
                    "reason": "Recorded written permission",
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "access.json"
            path.write_text(json.dumps(record))
            self.assertTrue(market_data.market_data_access("example", path)["authorised"])
            del record["sources"]["example"]["scope"]
            path.write_text(json.dumps(record))
            self.assertFalse(market_data.market_data_access("example", path)["authorised"])

    def test_blocked_source_stops_before_network(self):
        with mock.patch.object(
            market_data, "_get", side_effect=AssertionError("network should not be reached")
        ) as get:
            with self.assertRaises(market_data.MarketDataAccessError):
                market_data.get_kalshi_prices()
            get.assert_not_called()

    def test_aggregate_reader_fails_when_nothing_is_authorised(self):
        with mock.patch.object(
            market_data,
            "market_data_access",
            side_effect=lambda source: {"source": source, "authorised": False},
        ):
            with self.assertRaises(market_data.MarketDataAccessError):
                market_data.get_all_prediction_prices("example")


if __name__ == "__main__":
    unittest.main()
