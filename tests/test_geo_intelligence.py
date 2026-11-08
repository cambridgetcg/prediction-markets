#!/usr/bin/env python3
"""Offline tests for pipeline/geo_intelligence.py against ww3's current schema.

The fixture builds the tables the bridge reads with the DDL that
ww3-intelligence's init_db emits (schema v2), written out here as SQL so the
test does not import ww3. If ww3 changes these tables, update WW3_SCHEMA_SQL
from a fresh init_db and let the tests say what the bridge must change.
"""

import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase, main as unittest_main
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "geo_intelligence_for_tests", PROJECT_ROOT / "pipeline" / "geo_intelligence.py"
)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)

sys.path.insert(0, str(PROJECT_ROOT))
from engine import geo_layer  # noqa: E402

# ww3 init_db DDL for the tables the bridge touches. Prediction's links to
# scenarionode and analysisrun are left out; the bridge does not read them.
WW3_SCHEMA_SQL = """
CREATE TABLE "event" ("id" INTEGER NOT NULL PRIMARY KEY, "title" VARCHAR(255) NOT NULL, "date" DATE NOT NULL, "location_name" VARCHAR(255), "lat" REAL, "lon" REAL, "category" VARCHAR(255) NOT NULL, "subcategory" VARCHAR(255), "classification" VARCHAR(255) NOT NULL, "significance" INTEGER NOT NULL, "summary" TEXT, "full_analysis" TEXT, "confidence_score" REAL, "created_at" DATETIME NOT NULL, "updated_at" DATETIME NOT NULL);
CREATE TABLE "escalationstate" ("id" INTEGER NOT NULL PRIMARY KEY, "region" VARCHAR(255) NOT NULL, "current_level" INTEGER NOT NULL, "level_description" TEXT, "triggers_for_next" TEXT, "de_escalation_pathways" TEXT, "assessed_at" DATETIME NOT NULL, "event_id" INTEGER, FOREIGN KEY ("event_id") REFERENCES "event" ("id"));
CREATE TABLE "impactassessment" ("id" INTEGER NOT NULL PRIMARY KEY, "event_id" INTEGER NOT NULL, "military_regional" INTEGER NOT NULL, "military_global" INTEGER NOT NULL, "economic_regional" INTEGER NOT NULL, "economic_global" INTEGER NOT NULL, "humanitarian_regional" INTEGER NOT NULL, "humanitarian_global" INTEGER NOT NULL, "diplomatic_regional" INTEGER NOT NULL, "diplomatic_global" INTEGER NOT NULL, "assessed_at" DATETIME NOT NULL, FOREIGN KEY ("event_id") REFERENCES "event" ("id"));
CREATE TABLE "prediction" ("id" INTEGER NOT NULL PRIMARY KEY, "event_id" INTEGER NOT NULL, "scenario_node_id" INTEGER, "analysis_run_id" INTEGER, "authorship" VARCHAR(255), "probability" INTEGER NOT NULL, "confidence" VARCHAR(255) NOT NULL, "timeframe" VARCHAR(255), "horizon" VARCHAR(255), "reasoning" TEXT NOT NULL, "created_at" DATETIME NOT NULL, "resolved_at" DATETIME, "outcome" TEXT, "brier_score" REAL, FOREIGN KEY ("event_id") REFERENCES "event" ("id"));
CREATE TABLE "observation" ("id" INTEGER NOT NULL PRIMARY KEY, "dedupe_key" VARCHAR(255) NOT NULL, "source" VARCHAR(255) NOT NULL, "source_record_id" TEXT, "type" VARCHAR(255) NOT NULL, "raw_text" TEXT NOT NULL, "content_hash" VARCHAR(255) NOT NULL, "canonical_url" TEXT, "published_at" DATETIME, "fetched_at" DATETIME NOT NULL, "geo_lat" REAL, "geo_lon" REAL, "location_name" VARCHAR(255), "source_confidence" VARCHAR(255) NOT NULL, "synthetic" INTEGER NOT NULL, "supersedes_id" INTEGER, "created_at" DATETIME NOT NULL, FOREIGN KEY ("supersedes_id") REFERENCES "observation" ("id") ON DELETE SET NULL);
"""

WW3_CATEGORIES = {"seismic", "military", "political", "cyber", "economic", "other"}

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


class Ledger:
    """A temp SQLite file with ww3's current schema and helpers to add rows."""

    def __init__(self, schema_sql=WW3_SCHEMA_SQL):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "ww3.db"
        conn = sqlite3.connect(self.path)
        conn.executescript(schema_sql)
        conn.commit()
        conn.close()

    def cleanup(self):
        self.dir.cleanup()

    def execute(self, sql, params=()):
        conn = sqlite3.connect(self.path)
        try:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def add_event(self, title, date, category="military", significance=5):
        return self.execute(
            'INSERT INTO event (title, date, category, classification, significance, '
            'created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (title, date, category, "reported", significance,
             "2026-11-08 00:00:00", "2026-11-08 00:00:00"),
        )

    def add_escalation(self, event_id, level, region="Region", assessed_at="2026-11-08 01:00:00"):
        return self.execute(
            'INSERT INTO escalationstate (region, current_level, assessed_at, event_id) '
            'VALUES (?, ?, ?, ?)',
            (region, level, assessed_at, event_id),
        )

    def add_impact(self, event_id, economic_global, economic_regional=1,
                   assessed_at="2026-11-08 01:00:00"):
        return self.execute(
            'INSERT INTO impactassessment (event_id, military_regional, military_global, '
            'economic_regional, economic_global, humanitarian_regional, humanitarian_global, '
            'diplomatic_regional, diplomatic_global, assessed_at) '
            'VALUES (?, 1, 1, ?, ?, 1, 1, 1, 1, ?)',
            (event_id, economic_regional, economic_global, assessed_at),
        )

    def add_observation(self, fetched_at):
        return self.execute(
            'INSERT INTO observation (dedupe_key, source, type, raw_text, content_hash, '
            'fetched_at, source_confidence, synthetic, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (f"k-{fetched_at}", "usgs", "seismic", "text", "h", fetched_at,
             "not-assessed", 0, fetched_at),
        )

    def add_prediction(self, event_id, probability, brier_score, resolved_at):
        return self.execute(
            'INSERT INTO prediction (event_id, probability, confidence, reasoning, '
            'created_at, resolved_at, brier_score) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (event_id, probability, "medium", "r", "2026-11-01 00:00:00",
             resolved_at, brier_score),
        )


class LedgerTestCase(TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.addCleanup(self.ledger.cleanup)
        env = patch.dict(os.environ, {bridge.WW3_DB_ENV: str(self.ledger.path)})
        env.start()
        self.addCleanup(env.stop)


class TestDbPath(TestCase):
    def test_env_var_names_the_ledger(self):
        with patch.dict(os.environ, {"WW3_DB_PATH": "/some/where/ww3.db"}):
            self.assertEqual(bridge.ww3_db_path(), Path("/some/where/ww3.db"))

    def test_unset_falls_back_to_old_default(self):
        with patch.dict(os.environ):
            os.environ.pop("WW3_DB_PATH", None)
            self.assertEqual(bridge.ww3_db_path(), bridge.DEFAULT_WW3_DB)
        with patch.dict(os.environ, {"WW3_DB_PATH": "  "}):
            self.assertEqual(bridge.ww3_db_path(), bridge.DEFAULT_WW3_DB)

    def test_missing_ledger_names_the_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "absent.db"
            with patch.dict(os.environ, {"WW3_DB_PATH": str(missing)}):
                with self.assertRaises(bridge.WW3LedgerError) as caught:
                    bridge.read_ww3_events(now=NOW)
        message = str(caught.exception)
        self.assertIn("not found", message)
        self.assertIn("WW3_DB_PATH", message)
        self.assertIn(str(missing), message)


class TestSchemaContract(LedgerTestCase):
    def test_current_schema_has_every_column(self):
        conn = sqlite3.connect(self.ledger.path)
        try:
            self.assertEqual(bridge.missing_ledger_columns(conn), [])
        finally:
            conn.close()

    def test_drifted_schema_fails_loudly(self):
        """No silent fallback: a missing column is named, not papered over."""
        drifted = Ledger(WW3_SCHEMA_SQL.replace('"economic_global" INTEGER NOT NULL, ', ''))
        self.addCleanup(drifted.cleanup)
        with self.assertRaises(bridge.WW3LedgerError) as caught:
            bridge.read_ww3_events(db_path=drifted.path, now=NOW)
        self.assertIn("impactassessment.economic_global", str(caught.exception))

    def test_missing_table_is_named(self):
        no_escalation = Ledger(
            "\n".join(line for line in WW3_SCHEMA_SQL.splitlines()
                      if '"escalationstate"' not in line)
        )
        self.addCleanup(no_escalation.cleanup)
        with self.assertRaises(bridge.WW3LedgerError) as caught:
            bridge.read_ww3_events(db_path=no_escalation.path, now=NOW)
        self.assertIn("escalationstate (whole table)", str(caught.exception))

    def test_file_that_is_not_sqlite_fails_as_ledger_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            garbage = Path(tmp) / "ww3.db"
            garbage.write_text("not a database")
            with self.assertRaises(bridge.WW3LedgerError) as caught:
                bridge.read_ww3_events(db_path=garbage, now=NOW)
            out = io.StringIO()
            with patch.dict(os.environ, {"WW3_DB_PATH": str(garbage)}), \
                    patch("sys.stdout", out):
                bridge.display_status()
        self.assertIn("not a database", str(caught.exception))
        self.assertIn("cannot be read", out.getvalue())

    def test_reads_are_read_only(self):
        conn = bridge._connect_ww3(self.ledger.path)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM event")
        finally:
            conn.close()


class TestReadEvents(LedgerTestCase):
    def test_event_carries_escalation_and_impact(self):
        event_id = self.ledger.add_event("Strike", "2026-11-07")
        self.ledger.add_escalation(event_id, 8, region="Gulf")
        self.ledger.add_impact(event_id, economic_global=7, economic_regional=9)
        rows = bridge.read_ww3_events(now=NOW)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["escalation_level"], 8)
        self.assertEqual(row["escalation_region"], "Gulf")
        self.assertEqual(row["economic_global"], 7)
        self.assertEqual(row["economic_regional"], 9)
        self.assertEqual(row["category"], "military")

    def test_newest_assessment_wins_without_duplicate_rows(self):
        event_id = self.ledger.add_event("Strike", "2026-11-07")
        self.ledger.add_escalation(event_id, 3, assessed_at="2026-11-07 01:00:00")
        self.ledger.add_escalation(event_id, 9, assessed_at="2026-11-08 01:00:00")
        self.ledger.add_impact(event_id, 2, assessed_at="2026-11-08 02:00:00")
        self.ledger.add_impact(event_id, 6, assessed_at="2026-11-07 02:00:00")
        rows = bridge.read_ww3_events(now=NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["escalation_level"], 9)
        self.assertEqual(rows[0]["economic_global"], 2)

    def test_unassessed_event_reads_as_none(self):
        self.ledger.add_event("Statement", "2026-11-07", category="political")
        row = bridge.read_ww3_events(now=NOW)[0]
        self.assertIsNone(row["escalation_level"])
        self.assertIsNone(row["economic_global"])

    def test_event_dated_on_cutoff_day_is_included(self):
        """Event.date is 'YYYY-MM-DD'; the cutoff day itself counts."""
        self.ledger.add_event("On cutoff day", "2026-11-01")
        self.ledger.add_event("Day before", "2026-10-31")
        titles = [r["title"] for r in bridge.read_ww3_events(days=7, now=NOW)]
        self.assertEqual(titles, ["On cutoff day"])

    def test_min_significance_filters(self):
        self.ledger.add_event("Minor", "2026-11-07", significance=4)
        self.ledger.add_event("Major", "2026-11-07", significance=5)
        self.assertEqual([r["title"] for r in bridge.read_ww3_events(now=NOW)], ["Major"])
        both = bridge.read_ww3_events(min_significance=3, now=NOW)
        self.assertEqual(sorted(r["title"] for r in both), ["Major", "Minor"])

    def test_empty_ledger_reads_no_events(self):
        self.assertEqual(bridge.read_ww3_events(now=NOW), [])


class TestLedgerAsOf(LedgerTestCase):
    def test_newest_observation_as_utc(self):
        self.ledger.add_observation("2026-11-01 06:41:00.123456")
        self.ledger.add_observation("2026-11-02 06:41:00")
        self.assertEqual(bridge.read_ledger_as_of(), "2026-11-02T06:41:00+00:00")

    def test_no_observations_is_none(self):
        self.assertIsNone(bridge.read_ledger_as_of())

    def test_counts(self):
        self.ledger.add_observation("2026-11-02 06:41:00")
        self.assertEqual(bridge.count_ww3_rows(), {"event": 0, "observation": 1})


class TestReadPredictions(LedgerTestCase):
    def test_cutoff_compares_naive_utc_text(self):
        event_id = self.ledger.add_event("Strike", "2026-10-01")
        # 30 days before NOW is 2026-10-09 12:00:00 UTC.
        self.ledger.add_prediction(event_id, 70, 0.09, "2026-10-09 13:00:00")
        self.ledger.add_prediction(event_id, 40, 0.16, "2026-10-09 11:00:00")
        self.ledger.add_prediction(event_id, 20, None, "2026-11-01 00:00:00")
        rows = bridge.read_ww3_predictions(days=30, now=NOW)
        self.assertEqual([r["probability"] for r in rows], [70])
        self.assertEqual(rows[0]["event_title"], "Strike")


class TestCategories(TestCase):
    def test_mapping_covers_exactly_ww3_categories(self):
        self.assertEqual(set(bridge.CATEGORY_TO_TYPE), WW3_CATEGORIES)
        for profile in bridge.CATEGORY_TO_TYPE.values():
            self.assertIn(profile, bridge.GEO_SENSITIVITY)

    def test_stored_lowercase_categories_match(self):
        expected = {"military": "war", "cyber": "cyber_attack", "economic": "sanctions",
                    "political": "default", "seismic": "default", "other": "default"}
        for category, profile in expected.items():
            event = {"title": category, "category": category, "escalation_level": 5,
                     "economic_global": 5}
            signals = bridge.generate_geo_signals([event])
            self.assertEqual(signals["active_events"][0]["sensitivity_type"], profile, category)


class TestSignals(TestCase):
    def test_escalation_uses_ww3_ten_point_scale(self):
        event = {"title": "Strike", "category": "military", "escalation_level": 8,
                 "economic_global": 7}
        signals = bridge.generate_geo_signals([event])
        self.assertEqual(signals["global_escalation_level"], 8)
        # weight = 8/10 * 7/10 = 0.56; war GLD prior is +2.0
        self.assertAlmostEqual(signals["instrument_adjustments"]["GLD"], 1.12)
        self.assertEqual(signals["active_events"][0]["escalation_level"], 8)

    def test_active_threshold_matches_geo_layer(self):
        low = {"title": "Low", "category": "military", "escalation_level": 3, "economic_global": 5}
        high = {"title": "High", "category": "military", "escalation_level": 4, "economic_global": 5}
        signals = bridge.generate_geo_signals([low, high])
        self.assertEqual([e["title"] for e in signals["active_events"]], ["High"])

    def test_unassessed_event_moves_nothing(self):
        event = {"title": "Statement", "category": "political", "escalation_level": None,
                 "economic_global": None}
        signals = bridge.generate_geo_signals([event])
        self.assertEqual(signals["event_count"], 1)
        self.assertEqual(signals["escalation_assessed"], 0)
        self.assertEqual(signals["global_escalation_level"], 0)
        self.assertTrue(all(v == 0.0 for v in signals["instrument_adjustments"].values()))
        self.assertEqual(signals["risk_posture"], "NEUTRAL")

    def test_missing_impact_uses_stated_factor(self):
        event = {"title": "Strike", "category": "military", "escalation_level": 10,
                 "economic_global": None}
        signals = bridge.generate_geo_signals([event])
        self.assertAlmostEqual(signals["instrument_adjustments"]["GLD"],
                               2.0 * bridge.UNASSESSED_IMPACT_FACTOR)

    def test_active_events_ordered_by_escalation(self):
        events = [{"title": f"E{level}", "category": "military", "escalation_level": level,
                   "economic_global": 5} for level in (4, 9, 6)]
        signals = bridge.generate_geo_signals(events)
        self.assertEqual([e["title"] for e in signals["active_events"]], ["E9", "E6", "E4"])


class TestLedgerToGeoLayer(LedgerTestCase):
    """End to end: a ledger with assessed events can now move a probability."""

    def setUp(self):
        super().setUp()
        self.stream = tempfile.TemporaryDirectory()
        self.addCleanup(self.stream.cleanup)
        geo = Path(self.stream.name) / "geo_intelligence.jsonl"
        news = Path(self.stream.name) / "news.jsonl"
        for target, path in (("ORACLE_GEO_JSONL", geo), ("ORACLE_NEWS_JSONL", news)):
            patcher = patch.object(bridge, target, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.geo_path = geo

    def _inject(self):
        events = bridge.read_ww3_events(days=14, now=NOW)
        signals = bridge.generate_geo_signals(events, ledger_as_of=bridge.read_ledger_as_of())
        return bridge.inject_geo_signals(signals)

    def test_assessed_military_event_reaches_regime_adjustment(self):
        event_id = self.ledger.add_event("Strike", "2026-11-07")
        self.ledger.add_escalation(event_id, 9)
        self.ledger.add_impact(event_id, economic_global=9)
        self.ledger.add_observation("2026-11-08 10:00:00")
        record = self._inject()
        self.assertEqual(record["risk_posture"], "RISK_OFF")
        self.assertEqual(record["global_escalation"], 9)
        self.assertEqual(record["ledger_as_of"], "2026-11-08T10:00:00+00:00")
        written = json.loads(self.geo_path.read_text().splitlines()[-1])
        self.assertEqual(written, record)
        just_after = datetime.fromisoformat(record["ts"])
        adj = geo_layer.get_regime_adjustment(written, "GEO", max_age_hours=24, now=just_after)
        self.assertGreater(adj, 0.0)

    def test_old_ledger_copy_reads_stale(self):
        """A record written now from a week-old ledger copy is not current."""
        event_id = self.ledger.add_event("Strike", "2026-11-07")
        self.ledger.add_escalation(event_id, 9)
        self.ledger.add_impact(event_id, economic_global=9)
        self.ledger.add_observation("2026-10-30 10:00:00")
        record = self._inject()
        just_after = datetime.fromisoformat(record["ts"])
        fresh = geo_layer.geo_freshness(record, max_age_hours=24, now=just_after)
        self.assertEqual(fresh["state"], "STALE")
        self.assertEqual(geo_layer.get_regime_adjustment(record, "GEO", max_age_hours=24,
                                                         now=just_after), 0.0)


class TestCli(TestCase):
    def test_inject_without_ledger_exits_nonzero_naming_the_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "absent.db"
            err = io.StringIO()
            with patch.dict(os.environ, {"WW3_DB_PATH": str(missing)}), \
                    patch.object(sys, "argv", ["geo_intelligence.py", "inject"]), \
                    patch("sys.stderr", err), \
                    patch.object(bridge, "inject_geo_signals") as inject:
                with self.assertRaises(SystemExit) as caught:
                    bridge.main()
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("WW3_DB_PATH", err.getvalue())
        self.assertIn("not found", err.getvalue())
        inject.assert_not_called()

    def test_watch_injects_nothing_when_there_are_no_events(self):
        out = io.StringIO()
        with patch.object(sys, "argv", ["geo_intelligence.py", "watch"]), \
                patch.object(bridge, "read_ww3_events", return_value=[]), \
                patch.object(bridge, "read_ledger_as_of", return_value=None), \
                patch.object(bridge, "inject_geo_signals") as inject, \
                patch.object(bridge.time, "sleep", side_effect=KeyboardInterrupt), \
                patch("sys.stdout", out):
            bridge.main()
        inject.assert_not_called()
        self.assertIn("nothing injected", out.getvalue())

    def test_status_on_a_current_ledger_without_events(self):
        ledger = Ledger()
        self.addCleanup(ledger.cleanup)
        ledger.add_observation("2026-11-02 06:41:00")
        out = io.StringIO()
        with patch.dict(os.environ, {"WW3_DB_PATH": str(ledger.path)}), \
                patch("sys.stdout", out):
            bridge.display_status()
        text = out.getvalue()
        self.assertIn("from WW3_DB_PATH", text)
        self.assertIn("has every column this bridge reads", text)
        self.assertIn("Event rows:   0", text)
        self.assertIn("model layer", text)
        self.assertIn("2026-11-02T06:41:00+00:00", text)

    def test_status_names_missing_columns(self):
        drifted = Ledger(WW3_SCHEMA_SQL.replace('"significance" INTEGER NOT NULL, ', ''))
        self.addCleanup(drifted.cleanup)
        out = io.StringIO()
        with patch.dict(os.environ, {"WW3_DB_PATH": str(drifted.path)}), \
                patch("sys.stdout", out):
            bridge.display_status()
        self.assertIn("missing event.significance", out.getvalue())


if __name__ == "__main__":
    unittest_main()
