#!/usr/bin/env python3
"""Offline tests for strict forecast/resolution calibration joins."""

import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import TestCase, main as unittest_main


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "scripts" / "calibration-report.py"
SPEC = importlib.util.spec_from_file_location("calibration_report", MODULE_PATH)
calibration_report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = calibration_report
SPEC.loader.exec_module(calibration_report)


class TestStrictJoins(TestCase):
    def test_orphan_resolution_is_separate_and_pending_never_negative(self):
        predictions = [
            {"id": "pred-1", "my_estimate": 0.8, "market_price": 0.7},
            {"id": "pred-2", "my_estimate": 0.4, "market_price": 0.5},
        ]
        resolutions = [
            {"pred_id": "pred-1", "outcome": "YES"},
            {"prediction_id": "retrospective", "outcome": "NO"},
            {"prediction_id": "retrospective", "outcome": "YES"},
        ]

        data = calibration_report.build_calibration_data(predictions, resolutions)

        self.assertEqual(len(data["joined"]), 1)
        self.assertEqual(len(data["orphans"]), 2)
        self.assertEqual(len(predictions) - len(data["joined"]), 1)

    def test_duplicate_resolutions_are_all_excluded(self):
        predictions = [{"id": "pred-1", "my_estimate": 0.8, "market_price": 0.7}]
        resolutions = [
            {"pred_id": "pred-1", "outcome": "YES"},
            {"prediction_id": "pred-1", "outcome": "YES"},
        ]

        data = calibration_report.build_calibration_data(predictions, resolutions)

        self.assertEqual(data["joined"], [])
        self.assertEqual(len(data["duplicate_resolutions"]), 2)


class TestStrictScoring(TestCase):
    def test_unknown_outcome_is_not_treated_as_no(self):
        predictions = [{"id": "pred-1", "my_estimate": 0.8, "market_price": 0.7}]
        resolutions = [{"pred_id": "pred-1", "outcome": "AMBIGUOUS"}]

        evaluation = calibration_report.build_calibration_data(
            predictions, resolutions
        )["evaluations"][0]

        self.assertIsNone(evaluation["outcome"])
        self.assertIsNone(evaluation["my_brier"])
        self.assertIsNone(evaluation["market_brier"])
        self.assertIsNone(evaluation["beat_market"])

    def test_missing_estimate_is_not_a_perfect_score(self):
        predictions = [
            {"id": "pred-1", "my_estimate": 0.8, "market_price": 0.7},
            {"id": "pred-2", "market_price": 0.6},
        ]
        resolutions = [
            {"pred_id": "pred-1", "outcome": "YES"},
            {"pred_id": "pred-2", "outcome": "YES"},
        ]

        evaluations = calibration_report.build_calibration_data(
            predictions, resolutions
        )["evaluations"]
        scores = [e["my_brier"] for e in evaluations if e["my_brier"] is not None]

        self.assertEqual(len(scores), 1)
        self.assertAlmostEqual(scores[0], 0.04)

    def test_scores_are_recomputed_from_forecast_not_resolution_claims(self):
        predictions = [{"id": "pred-1", "my_estimate": 0.8, "market_price": 0.7}]
        resolutions = [{
            "pred_id": "pred-1",
            "outcome": "YES",
            "my_brier": 0.0,
            "market_brier": 0.0,
        }]

        evaluation = calibration_report.build_calibration_data(
            predictions, resolutions
        )["evaluations"][0]

        self.assertAlmostEqual(evaluation["my_brier"], 0.04)
        self.assertAlmostEqual(evaluation["market_brier"], 0.09)


class TestReportOutput(TestCase):
    def test_report_names_strict_and_orphan_counts_without_writing_domains(self):
        with tempfile.TemporaryDirectory() as tmp:
            pred_file = Path(tmp) / "predictions.jsonl"
            res_file = Path(tmp) / "resolutions.jsonl"
            pred_file.write_text(
                json.dumps({
                    "id": "pred-1", "domain": "POL",
                    "my_estimate": 0.8, "market_price": 0.7,
                }) + "\n"
            )
            res_file.write_text(
                json.dumps({"pred_id": "pred-1", "outcome": "YES"}) + "\n" +
                json.dumps({"prediction_id": "retro", "outcome": "NO"}) + "\n"
            )
            output = io.StringIO()
            with redirect_stdout(output):
                calibration_report.report(
                    pred_file, res_file, write_domain_files=False
                )

        rendered = output.getvalue()
        self.assertIn("Resolved (strict ID join): 1", rendered)
        self.assertIn("Pending/unjoined predictions: 0", rendered)
        self.assertIn("Retrospective/orphan resolutions: 1", rendered)
        self.assertIn("My avg Brier score:     0.0400 (n=1)", rendered)


if __name__ == "__main__":
    unittest_main()
