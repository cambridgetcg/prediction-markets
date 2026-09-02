#!/usr/bin/env python3
"""Offline correctness tests for engine/decision_engine.py."""

import json
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main as unittest_main
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.decision_engine import (  # noqa: E402
    kelly_fraction,
    load_active_predictions,
    score_opportunity,
)


class TestDirectionalKelly(TestCase):
    def test_yes_uses_yes_probability_and_price(self):
        result = score_opportunity({
            "my_estimate": 0.70,
            "market_price": 0.60,
            "yes_ask": 0.60,
            "cost_per_contract": 0.0,
            "confidence_interval": [0.65, 0.75],
        })

        self.assertEqual(result["recommended_action"], "PAPER_CANDIDATE")
        self.assertFalse(result["execution_authorized"])
        self.assertTrue(result["direction"].startswith("YES"))
        self.assertEqual(result["selected_token_probability"], 0.70)
        self.assertEqual(result["selected_token_price"], 0.60)
        self.assertAlmostEqual(result["kelly_fraction"], 6.25)

    def test_no_uses_complement_probability_and_price(self):
        result = score_opportunity({
            "my_estimate": 0.30,
            "market_price": 0.40,
            "no_ask": 0.60,
            "cost_per_contract": 0.0,
            "confidence_interval": [0.25, 0.35],
        })

        self.assertEqual(result["recommended_action"], "PAPER_CANDIDATE")
        self.assertTrue(result["direction"].startswith("NO"))
        self.assertEqual(result["selected_token_probability"], 0.70)
        self.assertEqual(result["selected_token_price"], 0.60)
        self.assertAlmostEqual(result["kelly_fraction"], 6.25)

    def test_selected_outcome_kelly_contract_is_symmetric(self):
        self.assertAlmostEqual(
            kelly_fraction(0.70, 0.60),
            kelly_fraction(1.0 - 0.30, 1.0 - 0.40),
        )

    def test_legacy_kelly_keyword_names_remain_supported(self):
        self.assertAlmostEqual(
            kelly_fraction(my_estimate=0.70, market_price=0.60), 0.0625
        )

    def test_invalid_probability_fails_closed(self):
        result = score_opportunity({"my_estimate": "unknown", "market_price": 0.40})
        self.assertEqual(result["decision"], "INVALID_PROBABILITY")
        self.assertIsNone(result["recommended_action"])

    def test_malformed_confidence_intervals_fail_closed(self):
        for interval in (None, "0.2,0.4", [0.2], [0.8, 0.2], [0.2, None]):
            with self.subTest(interval=interval):
                result = score_opportunity({
                    "my_estimate": 0.30,
                    "market_price": 0.40,
                    "confidence_interval": interval,
                })
                self.assertEqual(result["decision"], "INVALID_CONFIDENCE_INTERVAL")
                self.assertIsNone(result["recommended_action"])

    def test_missing_executable_quote_or_cost_can_only_be_watched(self):
        result = score_opportunity({
            "my_estimate": 0.30,
            "market_price": 0.40,
            "confidence_interval": [0.25, 0.35],
        })

        self.assertEqual(result["recommended_action"], "WATCH")
        self.assertEqual(result["quote_basis"], "derived_reference")
        self.assertIsNone(result["paper_edge_pct"])
        self.assertEqual(result["position_size_usd"], 0.0)

    def test_explicit_costs_can_remove_a_reference_edge(self):
        result = score_opportunity({
            "my_estimate": 0.70,
            "market_price": 0.60,
            "yes_ask": 0.64,
            "cost_per_contract": 0.03,
            "confidence_interval": [0.65, 0.75],
        })

        self.assertEqual(result["recommended_action"], "PASS")
        self.assertAlmostEqual(result["paper_edge_pct"], 3.0)

    def test_executable_asks_choose_the_better_side_not_the_midpoint_lean(self):
        result = score_opportunity({
            "my_estimate": 0.55,
            "market_price": 0.50,
            "yes_ask": 0.70,
            "no_ask": 0.30,
            "cost_per_contract": 0.0,
            "confidence_interval": [0.50, 0.60],
        })

        self.assertEqual(result["side"], "NO")
        self.assertEqual(result["recommended_action"], "PAPER_CANDIDATE")
        self.assertAlmostEqual(result["paper_edge_pct"], 15.0)

    def test_kelly_invalid_inputs_fail_closed(self):
        self.assertEqual(kelly_fraction("unknown", 0.5), 0.0)
        self.assertEqual(kelly_fraction(0.6, float("nan")), 0.0)


class TestLoadActivePredictions(TestCase):
    def test_false_and_legacy_null_are_active_but_true_is_not(self):
        records = [
            {"id": "false", "resolved": False, "market_price": 0.40},
            {"id": "null", "resolved": None, "market_price": 0.50},
            {"id": "true", "resolved": True, "market_price": 0.60},
            {"id": "missing-price", "resolved": False, "market_price": None},
            {"id": "invalid-price", "resolved": False, "market_price": "unknown"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            calibration_dir = Path(tmp)
            predictions = calibration_dir / "predictions.jsonl"
            predictions.write_text("".join(json.dumps(r) + "\n" for r in records))
            with patch("engine.decision_engine.CALIBRATION_DIR", calibration_dir):
                loaded = load_active_predictions()

        self.assertEqual([record["id"] for record in loaded], ["false", "null"])


if __name__ == "__main__":
    unittest_main()
