#!/usr/bin/env python3
"""Offline tests for the Oracle observation-loop brake."""

import importlib.util
import tempfile
from pathlib import Path
from unittest import TestCase, main as unittest_main
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "oracle_run_for_tests", PROJECT_ROOT / "scripts" / "oracle-run.py"
)
oracle_run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oracle_run)


class TestOracleStillBrake(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.still_path = Path(self.tmp_dir.name) / "STILL"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_still_stops_before_first_cycle(self):
        self.still_path.touch()
        with patch.object(oracle_run, "STILL_PATH", self.still_path), patch.object(
            oracle_run, "load_signals"
        ) as load_signals:
            oracle_run.run_loop()

        load_signals.assert_not_called()

    def test_still_is_checked_between_cycles(self):
        def first_sleep_requests_rest(seconds):
            self.assertEqual(seconds, 900)
            self.still_path.touch()

        with patch.object(oracle_run, "STILL_PATH", self.still_path), patch.object(
            oracle_run, "load_signals", return_value=[]
        ) as load_signals, patch.object(
            oracle_run, "run_whale_scanner", return_value=[]
        ), patch.object(
            oracle_run, "save_signals"
        ), patch.object(
            oracle_run, "update_status"
        ), patch("time.sleep", side_effect=first_sleep_requests_rest) as sleep:
            oracle_run.run_loop()

        self.assertEqual(load_signals.call_count, 1)
        sleep.assert_called_once_with(900)


if __name__ == "__main__":
    unittest_main()
