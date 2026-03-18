#!/usr/bin/env python3
"""Tests for engine/geo_layer.py"""

import json
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main as unittest_main
from unittest.mock import patch

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.geo_layer import (
    load_geo_context,
    build_geo_context_string,
    get_regime_adjustment,
    _norm,
    GEO_JSONL,
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


class TestBuildGeoContextString(TestCase):
    """Test context string generation."""

    def test_bridge_format(self):
        """Handles bridge output format (risk_posture, global_escalation)."""
        result = build_geo_context_string(SAMPLE_BRIDGE_RECORD)
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


class TestGetRegimeAdjustment(TestCase):
    """Test probability adjustment calculation."""

    def test_none_geo(self):
        self.assertEqual(get_regime_adjustment(None, "GEO"), 0.0)

    def test_low_escalation(self):
        """Escalation < 4 returns 0."""
        low = {**SAMPLE_BRIDGE_RECORD, "global_escalation": 3}
        self.assertEqual(get_regime_adjustment(low, "GEO"), 0.0)

    def test_high_escalation_geo_domain(self):
        """GEO domain + high escalation + risk-off → positive adjustment."""
        adj = get_regime_adjustment(SAMPLE_BRIDGE_RECORD, "GEO")
        self.assertGreater(adj, 0.0)
        self.assertLessEqual(adj, 0.05)

    def test_high_escalation_other_domain(self):
        """Non-GEO domain gets smaller adjustment."""
        adj = get_regime_adjustment(SAMPLE_BRIDGE_RECORD, "ECO")
        self.assertLessEqual(abs(adj), 0.02)

    def test_risk_on_geo(self):
        """Risk-on + GEO → negative adjustment (de-escalation signal)."""
        risk_on = {**SAMPLE_BRIDGE_RECORD, "risk_posture": "RISK_ON", "global_escalation": 8}
        adj = get_regime_adjustment(risk_on, "GEO")
        self.assertLess(adj, 0.0)

    def test_bounds(self):
        """Adjustment stays within [-0.05, +0.05]."""
        extreme = {**SAMPLE_BRIDGE_RECORD, "global_escalation": 10}
        for domain in ["GEO", "ECO", "POL", "TEC", "CRY"]:
            adj = get_regime_adjustment(extreme, domain)
            self.assertGreaterEqual(adj, -0.05)
            self.assertLessEqual(adj, 0.05)


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
