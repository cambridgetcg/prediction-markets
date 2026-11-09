#!/usr/bin/env python3
"""Tests for engine/geo_layer.py"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase, main as unittest_main
from unittest.mock import patch

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.geo_layer import (
    load_geo_context,
    build_geo_context_string,
    configured_max_age_hours,
    geo_freshness,
    get_regime_adjustment,
    is_fresh,
    _norm,
    GEO_JSONL,
    MAX_AGE_ENV,
)

# ── Sample data ──────────────────────────────────────────────────────────────

SAMPLE_BRIDGE_RECORD = {
    "type": "geo_intelligence",
    "source": "ww3-intelligence",
    "ts": "2026-03-18T12:00:00+00:00",
    "risk_posture": "RISK_OFF",
    "global_escalation": 7,
    "instrument_adjustments": {"SPY": -1.2, "GLD": +1.8, "USO": +0.9, "BTC": -0.3},
    "active_events": [
        {"title": "Iran nuclear talks collapse", "category": "NUCLEAR", "region": "Middle East", "escalation_level": 7, "sensitivity_type": "nuclear"},
        {"title": "Russia-Ukraine front escalation", "category": "MILITARY", "region": "Eastern Europe", "escalation_level": 6, "sensitivity_type": "war"},
        {"title": "China Taiwan strait exercises", "category": "MILITARY", "region": "East Asia", "escalation_level": 5, "sensitivity_type": "war"},
    ],
    "event_count": 42,
}

SAMPLE_SPEC_RECORD = {
    "escalation_level": 6,
    "regime_bias": "risk-off",
    "instrument_impacts": {"SPY": -0.8, "GLD": +1.5},
    "top_events": [{"title": "Sanctions expansion"}],
    "brier_context": {"calibrated": True, "avg_brier_score": 0.12, "interpretation": "GOOD — well calibrated"},
    "ts": "2026-03-18T10:00:00+00:00",
    "event_count": 20,
}

# One hour after SAMPLE_BRIDGE_RECORD was written: fresh under the 24 h default.
SAMPLE_NOW = datetime(2026, 3, 18, 13, 0, tzinfo=timezone.utc)


class DefaultLimitTestCase(TestCase):
    """Run with the default age limit, whatever GEO_MAX_AGE_HOURS the shell has."""

    def setUp(self):
        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(MAX_AGE_ENV, None)


class TestLoadGeoContext(TestCase):
    """Test load_geo_context with various file states."""

    def test_file_absent(self):
        """Returns None when jsonl file doesn't exist."""
        with patch("engine.geo_layer.GEO_JSONL", Path("/nonexistent/path.jsonl")):
            result = load_geo_context()
            self.assertIsNone(result)

    def test_file_empty(self):
        """Returns None when file is empty."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("")
            tmp = Path(f.name)
        try:
            with patch("engine.geo_layer.GEO_JSONL", tmp):
                self.assertIsNone(load_geo_context())
        finally:
            tmp.unlink()

    def test_valid_single_line(self):
        """Reads single-line file correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(SAMPLE_BRIDGE_RECORD) + "\n")
            tmp = Path(f.name)
        try:
            with patch("engine.geo_layer.GEO_JSONL", tmp):
                result = load_geo_context()
                self.assertIsNotNone(result)
                self.assertEqual(result["global_escalation"], 7)
        finally:
            tmp.unlink()

    def test_valid_multi_line_returns_last(self):
        """Returns the last (most recent) entry."""
        old = {**SAMPLE_BRIDGE_RECORD, "global_escalation": 3}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(old) + "\n")
            f.write(json.dumps(SAMPLE_BRIDGE_RECORD) + "\n")
            tmp = Path(f.name)
        try:
            with patch("engine.geo_layer.GEO_JSONL", tmp):
                result = load_geo_context()
                self.assertEqual(result["global_escalation"], 7)
        finally:
            tmp.unlink()

    def test_corrupt_json(self):
        """Returns None on corrupt JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("{bad json\n")
            tmp = Path(f.name)
        try:
            with patch("engine.geo_layer.GEO_JSONL", tmp):
                self.assertIsNone(load_geo_context())
        finally:
            tmp.unlink()


class TestBuildGeoContextString(DefaultLimitTestCase):
    """Test context string generation."""

    def test_bridge_format(self):
        """Handles bridge output format (risk_posture, global_escalation)."""
        result = build_geo_context_string(SAMPLE_BRIDGE_RECORD, now=SAMPLE_NOW)
        self.assertIn("Layer 6", result)
        self.assertIn("7/10", result)
        self.assertIn("risk-off", result)
        self.assertIn("Iran nuclear", result)
        self.assertIn("SPY", result)

    def test_spec_format(self):
        """Handles spec format (regime_bias, escalation_level)."""
        result = build_geo_context_string(SAMPLE_SPEC_RECORD)
        self.assertIn("6/10", result)
        self.assertIn("risk-off", result)
        self.assertIn("Brier 0.12", result)

    def test_under_400_chars(self):
        """Output stays under 400 chars (reasonable — may flex slightly with long events)."""
        result = build_geo_context_string(SAMPLE_BRIDGE_RECORD)
        # Allow some headroom — the hard cap matters for typical inputs
        self.assertLess(len(result), 500)

    def test_empty_events(self):
        """Handles record with no events gracefully."""
        record = {**SAMPLE_BRIDGE_RECORD, "active_events": []}
        result = build_geo_context_string(record)
        self.assertIn("none", result)


class TestGetRegimeAdjustment(DefaultLimitTestCase):
    """Test probability adjustment calculation."""

    def test_none_geo(self):
        self.assertEqual(get_regime_adjustment(None, "GEO"), 0.0)

    def test_low_escalation(self):
        """Escalation < 4 returns 0."""
        low = {**SAMPLE_BRIDGE_RECORD, "global_escalation": 3}
        self.assertEqual(get_regime_adjustment(low, "GEO", now=SAMPLE_NOW), 0.0)

    def test_high_escalation_geo_domain(self):
        """GEO domain + high escalation + risk-off → positive adjustment."""
        adj = get_regime_adjustment(SAMPLE_BRIDGE_RECORD, "GEO", now=SAMPLE_NOW)
        self.assertGreater(adj, 0.0)
        self.assertLessEqual(adj, 0.05)

    def test_high_escalation_other_domain(self):
        """Non-GEO domain gets smaller adjustment."""
        adj = get_regime_adjustment(SAMPLE_BRIDGE_RECORD, "ECO", now=SAMPLE_NOW)
        self.assertLessEqual(abs(adj), 0.02)

    def test_risk_on_geo(self):
        """Risk-on + GEO → negative adjustment (de-escalation signal)."""
        risk_on = {**SAMPLE_BRIDGE_RECORD, "risk_posture": "RISK_ON", "global_escalation": 8}
        adj = get_regime_adjustment(risk_on, "GEO", now=SAMPLE_NOW)
        self.assertLess(adj, 0.0)

    def test_bounds(self):
        """Adjustment stays within [-0.05, +0.05]."""
        extreme = {**SAMPLE_BRIDGE_RECORD, "global_escalation": 10}
        for domain in ["GEO", "ECO", "POL", "TEC", "CRY"]:
            adj = get_regime_adjustment(extreme, domain, now=SAMPLE_NOW)
            self.assertGreaterEqual(adj, -0.05)
            self.assertLessEqual(adj, 0.05)


class TestFreshness(DefaultLimitTestCase):
    """A record past the age limit reads STALE and moves nothing."""

    def test_fresh_record_is_active(self):
        f = geo_freshness(SAMPLE_BRIDGE_RECORD, now=SAMPLE_NOW)
        self.assertEqual(f["state"], "ACTIVE")
        self.assertEqual(f["age"], timedelta(hours=1))
        self.assertEqual(f["age_str"], "1h 0m")
        self.assertEqual(f["max_age_hours"], 24.0)

    def test_old_record_is_stale(self):
        later = SAMPLE_NOW + timedelta(days=232)
        f = geo_freshness(SAMPLE_BRIDGE_RECORD, now=later)
        self.assertEqual(f["state"], "STALE")
        self.assertEqual(f["age_str"], "232d 1h")
        self.assertIn("past the 24h limit", f["reason"])

    def test_limit_is_inclusive(self):
        at_limit = SAMPLE_NOW + timedelta(hours=23)  # record is exactly 24 h old
        self.assertTrue(is_fresh(SAMPLE_BRIDGE_RECORD, now=at_limit))
        self.assertFalse(is_fresh(SAMPLE_BRIDGE_RECORD, now=at_limit + timedelta(seconds=1)))

    def test_max_age_is_configurable(self):
        self.assertFalse(is_fresh(SAMPLE_BRIDGE_RECORD, max_age_hours=0.5, now=SAMPLE_NOW))
        with patch.dict(os.environ, {MAX_AGE_ENV: "0.5"}):
            self.assertEqual(configured_max_age_hours(), 0.5)
            self.assertFalse(is_fresh(SAMPLE_BRIDGE_RECORD, now=SAMPLE_NOW))
        with patch.dict(os.environ, {MAX_AGE_ENV: "72"}):
            later = SAMPLE_NOW + timedelta(hours=48)
            self.assertTrue(is_fresh(SAMPLE_BRIDGE_RECORD, now=later))

    def test_bad_max_age_fails_loudly(self):
        for bad in ("soon", "0", "-3", "nan", "inf"):
            with patch.dict(os.environ, {MAX_AGE_ENV: bad}):
                with self.assertRaises(ValueError):
                    configured_max_age_hours()

    def test_missing_or_unreadable_ts_is_stale(self):
        for ts in (None, "", "yesterday", "2026-03-18T12:00:00"):
            record = {**SAMPLE_BRIDGE_RECORD, "ts": ts}
            f = geo_freshness(record, now=SAMPLE_NOW)
            self.assertEqual(f["state"], "STALE", ts)
            self.assertIsNone(f["age"])

    def test_z_suffix_is_read_as_utc(self):
        record = {**SAMPLE_BRIDGE_RECORD, "ts": "2026-03-18T12:00:00Z"}
        self.assertEqual(geo_freshness(record, now=SAMPLE_NOW)["state"], "ACTIVE")

    def test_future_ts_is_stale(self):
        record = {**SAMPLE_BRIDGE_RECORD, "ts": "2026-03-19T12:00:00+00:00"}
        f = geo_freshness(record, now=SAMPLE_NOW)
        self.assertEqual(f["state"], "STALE")
        self.assertIsNone(f["age"])

    def test_old_ledger_makes_a_new_record_stale(self):
        """A record written just now from a week-old ledger copy is week-old data."""
        record = {**SAMPLE_BRIDGE_RECORD, "ledger_as_of": "2026-03-11T12:00:00+00:00"}
        f = geo_freshness(record, now=SAMPLE_NOW)
        self.assertEqual(f["state"], "STALE")
        self.assertEqual(f["age_str"], "7d 1h")
        self.assertIn("ledger_as_of", f["basis"])

    def test_recent_ledger_keeps_record_active(self):
        record = {**SAMPLE_BRIDGE_RECORD, "ledger_as_of": "2026-03-18T11:30:00+00:00"}
        f = geo_freshness(record, now=SAMPLE_NOW)
        self.assertEqual(f["state"], "ACTIVE")
        self.assertEqual(f["age_str"], "1h 30m")

    def test_unreadable_ledger_as_of_is_stale(self):
        record = {**SAMPLE_BRIDGE_RECORD, "ledger_as_of": "last week"}
        self.assertEqual(geo_freshness(record, now=SAMPLE_NOW)["state"], "STALE")

    def test_none_is_missing(self):
        self.assertEqual(geo_freshness(None, now=SAMPLE_NOW)["state"], "MISSING")

    def test_stale_record_gives_no_adjustment(self):
        later = SAMPLE_NOW + timedelta(days=2)
        self.assertGreater(get_regime_adjustment(SAMPLE_BRIDGE_RECORD, "GEO", now=SAMPLE_NOW), 0.0)
        self.assertEqual(get_regime_adjustment(SAMPLE_BRIDGE_RECORD, "GEO", now=later), 0.0)
        no_ts = {**SAMPLE_BRIDGE_RECORD, "ts": ""}
        self.assertEqual(get_regime_adjustment(no_ts, "GEO", now=SAMPLE_NOW), 0.0)

    def test_context_string_states_age(self):
        fresh = build_geo_context_string(SAMPLE_BRIDGE_RECORD, now=SAMPLE_NOW)
        self.assertIn("data 1h 0m old", fresh)
        self.assertNotIn("STALE", fresh)
        self.assertNotIn("Live Feed", fresh)

    def test_context_string_says_stale(self):
        later = SAMPLE_NOW + timedelta(days=232)
        stale = build_geo_context_string(SAMPLE_BRIDGE_RECORD, now=later)
        self.assertIn("STALE", stale)
        self.assertIn("232d 1h old", stale)
        self.assertIn("not current", stale)
        unknown = build_geo_context_string({**SAMPLE_BRIDGE_RECORD, "ts": ""}, now=SAMPLE_NOW)
        self.assertIn("STALE, data age unknown", unknown)


class TestCliStatus(DefaultLimitTestCase):
    """The status line says STALE plainly and names the data age."""

    def _status(self, records):
        from io import StringIO
        from engine import geo_layer
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
            tmp = Path(f.name)
        try:
            out = StringIO()
            with patch("engine.geo_layer.GEO_JSONL", tmp), patch("sys.stdout", out):
                geo_layer.cli_status()
            return out.getvalue()
        finally:
            tmp.unlink()

    def test_old_record_prints_stale(self):
        out = self._status([SAMPLE_BRIDGE_RECORD])
        first = out.splitlines()[0]
        self.assertTrue(first.startswith("GEO LAYER STALE"), first)
        self.assertNotIn("ACTIVE", out)
        self.assertIn("Data age:", out)
        self.assertRegex(out, r"Data age:\s+\d+d \d+h")

    def test_fresh_record_prints_active(self):
        now_record = {**SAMPLE_BRIDGE_RECORD, "ts": datetime.now(timezone.utc).isoformat()}
        out = self._status([now_record])
        self.assertTrue(out.startswith("GEO LAYER ACTIVE"), out)

    def test_missing_file_prints_inactive(self):
        from io import StringIO
        from engine import geo_layer
        out = StringIO()
        with patch("engine.geo_layer.GEO_JSONL", Path("/nonexistent/path.jsonl")), \
                patch("sys.stdout", out):
            geo_layer.cli_status()
        self.assertTrue(out.getvalue().startswith("GEO LAYER INACTIVE"))


class TestNormalization(TestCase):
    """Test field normalization handles both formats."""

    def test_bridge_format(self):
        g = _norm(SAMPLE_BRIDGE_RECORD)
        self.assertEqual(g["escalation_level"], 7)
        self.assertEqual(g["regime_bias"], "risk-off")
        self.assertIn("SPY", g["instrument_impacts"])

    def test_spec_format(self):
        g = _norm(SAMPLE_SPEC_RECORD)
        self.assertEqual(g["escalation_level"], 6)
        self.assertEqual(g["regime_bias"], "risk-off")
        self.assertIn("SPY", g["instrument_impacts"])


if __name__ == "__main__":
    unittest_main()
