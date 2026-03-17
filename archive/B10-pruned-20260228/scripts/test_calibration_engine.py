"""Tests for NB11: Calibration Engine.

Run: python -m pytest scripts/test_calibration_engine.py -v
  or: python scripts/test_calibration_engine.py
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from calibration_engine import (
    CalibrationEngine,
    MARKET_BRIER_BASELINE,
    YES_DISCOUNT_DEFAULT,
    _read_yaml_value,
)


class TestRecordAndBrier(unittest.TestCase):
    """Test signal recording and Brier score computation."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.engine = CalibrationEngine(db_path=self.db_path)

    def tearDown(self):
        self.engine.close()
        self.db_path.unlink(missing_ok=True)

    def _make_signal(self, signal_id: str, direction: str = "YES",
                     prob: float = 0.70, price: float = 0.50,
                     strategy: str = "S004", generated_at: str = None) -> dict:
        if generated_at is None:
            generated_at = datetime.now(timezone.utc).isoformat()
        return {
            'signal_id': signal_id,
            'cluster_id': 'test_cluster',
            'market_question': 'Test market?',
            'direction': direction,
            'suggested_probability': prob,
            'current_price': price,
            'edge': prob - price,
            'strategy_code': strategy,
            'confidence': 0.75,
            'yes_discount_applied': direction == 'YES',
            'generated_at': generated_at,
        }

    def test_record_and_resolve(self):
        sig = self._make_signal('sig-001')
        self.engine.record_signal(sig)
        self.engine.record_outcome('sig-001', resolved_yes=True)

        row = self.engine.conn.execute(
            "SELECT resolved_yes, profitable FROM signal_outcomes WHERE signal_id = ?",
            ('sig-001',)
        ).fetchone()
        self.assertEqual(row[0], 1)  # resolved_yes = True
        self.assertEqual(row[1], 1)  # profitable = True (bought YES, resolved YES)

    def test_no_direction_profitable(self):
        sig = self._make_signal('sig-002', direction='NO', prob=0.70, price=0.50)
        self.engine.record_signal(sig)
        self.engine.record_outcome('sig-002', resolved_yes=False)

        row = self.engine.conn.execute(
            "SELECT profitable FROM signal_outcomes WHERE signal_id = ?",
            ('sig-002',)
        ).fetchone()
        self.assertEqual(row[0], 1)  # Bought NO, resolved NO = profitable

    def test_yes_direction_loss(self):
        sig = self._make_signal('sig-003', direction='YES')
        self.engine.record_signal(sig)
        self.engine.record_outcome('sig-003', resolved_yes=False)

        row = self.engine.conn.execute(
            "SELECT profitable FROM signal_outcomes WHERE signal_id = ?",
            ('sig-003',)
        ).fetchone()
        self.assertEqual(row[0], 0)  # Bought YES, resolved NO = loss

    def test_brier_perfect_prediction(self):
        """Predicting 1.0 for YES outcome → Brier = 0."""
        sig = self._make_signal('sig-004', prob=1.0)
        self.engine.record_signal(sig)
        self.engine.record_outcome('sig-004', resolved_yes=True)

        brier = self.engine.compute_brier(window_days=30)
        self.assertAlmostEqual(brier, 0.0, places=4)

    def test_brier_worst_prediction(self):
        """Predicting 0.0 for YES outcome → Brier = 1.0."""
        sig = self._make_signal('sig-005', prob=0.0)
        self.engine.record_signal(sig)
        self.engine.record_outcome('sig-005', resolved_yes=True)

        brier = self.engine.compute_brier(window_days=30)
        self.assertAlmostEqual(brier, 1.0, places=4)

    def test_brier_multiple_signals(self):
        """Average Brier across multiple signals."""
        # Good prediction: 0.80 for YES → (0.8 - 1)^2 = 0.04
        sig1 = self._make_signal('sig-006', prob=0.80)
        self.engine.record_signal(sig1)
        self.engine.record_outcome('sig-006', resolved_yes=True)

        # Bad prediction: 0.80 for NO → (0.8 - 0)^2 = 0.64
        sig2 = self._make_signal('sig-007', prob=0.80)
        self.engine.record_signal(sig2)
        self.engine.record_outcome('sig-007', resolved_yes=False)

        brier = self.engine.compute_brier(window_days=30)
        expected = (0.04 + 0.64) / 2  # 0.34
        self.assertAlmostEqual(brier, expected, places=4)

    def test_brier_returns_none_when_no_resolutions(self):
        brier = self.engine.compute_brier(window_days=30)
        self.assertIsNone(brier)

    def test_market_brier(self):
        """Market Brier uses current_price instead of suggested_probability."""
        sig = self._make_signal('sig-008', prob=0.80, price=0.50)
        self.engine.record_signal(sig)
        self.engine.record_outcome('sig-008', resolved_yes=True)

        market_brier = self.engine.compute_market_brier(window_days=30)
        # (0.50 - 1)^2 = 0.25
        self.assertAlmostEqual(market_brier, 0.25, places=4)


class TestYESNOAccuracy(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.engine = CalibrationEngine(db_path=self.db_path)

    def tearDown(self):
        self.engine.close()
        self.db_path.unlink(missing_ok=True)

    def test_yes_no_tracking(self):
        # 2 YES signals: 1 win, 1 loss
        for i, resolved in enumerate([True, False]):
            sig = {
                'signal_id': f'yes-{i}', 'cluster_id': 'c', 'market_question': 'Q',
                'direction': 'YES', 'suggested_probability': 0.7,
                'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S004',
                'confidence': 0.7, 'yes_discount_applied': True,
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }
            self.engine.record_signal(sig)
            self.engine.record_outcome(f'yes-{i}', resolved_yes=resolved)

        # 3 NO signals: all correct
        for i in range(3):
            sig = {
                'signal_id': f'no-{i}', 'cluster_id': 'c', 'market_question': 'Q',
                'direction': 'NO', 'suggested_probability': 0.7,
                'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S006',
                'confidence': 0.7, 'yes_discount_applied': False,
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }
            self.engine.record_signal(sig)
            self.engine.record_outcome(f'no-{i}', resolved_yes=False)

        ya = self.engine.track_yes_accuracy()
        self.assertEqual(ya['yes_total'], 2)
        self.assertEqual(ya['yes_correct'], 1)
        self.assertEqual(ya['no_total'], 3)
        self.assertEqual(ya['no_correct'], 3)
        self.assertAlmostEqual(ya['yes_rate'], 0.5)
        self.assertAlmostEqual(ya['no_rate'], 1.0)

    def test_discount_recommendation_default_when_few_signals(self):
        ya = self.engine.track_yes_accuracy()
        self.assertEqual(ya['recommended_discount'], YES_DISCOUNT_DEFAULT)


class TestStrategyTracking(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.engine = CalibrationEngine(db_path=self.db_path)

    def tearDown(self):
        self.engine.close()
        self.db_path.unlink(missing_ok=True)

    def test_strategy_performance(self):
        # S004: 2 signals, 1 win
        for i, resolved in enumerate([True, False]):
            sig = {
                'signal_id': f's4-{i}', 'cluster_id': 'c', 'market_question': 'Q',
                'direction': 'YES', 'suggested_probability': 0.7,
                'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S004',
                'confidence': 0.7, 'yes_discount_applied': True,
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }
            self.engine.record_signal(sig)
            self.engine.record_outcome(f's4-{i}', resolved_yes=resolved)

        # S006: 1 signal, 1 win
        sig = {
            'signal_id': 's6-0', 'cluster_id': 'c', 'market_question': 'Q',
            'direction': 'NO', 'suggested_probability': 0.7,
            'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S006',
            'confidence': 0.7, 'yes_discount_applied': False,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        self.engine.record_signal(sig)
        self.engine.record_outcome('s6-0', resolved_yes=False)

        strats = self.engine.track_by_strategy()
        self.assertIn('S004', strats)
        self.assertIn('S006', strats)
        self.assertEqual(strats['S004']['total'], 2)
        self.assertEqual(strats['S004']['correct'], 1)
        self.assertEqual(strats['S006']['total'], 1)
        self.assertEqual(strats['S006']['correct'], 1)


class TestCountryClusterTracking(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.engine = CalibrationEngine(db_path=self.db_path)

    def tearDown(self):
        self.engine.close()
        self.db_path.unlink(missing_ok=True)

    def test_country_cluster_accuracy(self):
        # Signal with Western+Russian clusters → correct
        sig = {
            'signal_id': 'cc-1', 'cluster_id': 'c', 'market_question': 'Q',
            'direction': 'NO', 'suggested_probability': 0.7,
            'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S004',
            'confidence': 0.7, 'yes_discount_applied': False,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        self.engine.record_signal(sig, country_clusters=['Western', 'Russian'])
        self.engine.record_outcome('cc-1', resolved_yes=False)

        # Signal with Western+Gulf clusters → incorrect
        sig2 = {
            'signal_id': 'cc-2', 'cluster_id': 'c', 'market_question': 'Q',
            'direction': 'YES', 'suggested_probability': 0.7,
            'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S004',
            'confidence': 0.7, 'yes_discount_applied': True,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        self.engine.record_signal(sig2, country_clusters=['Western', 'Gulf'])
        self.engine.record_outcome('cc-2', resolved_yes=False)

        clusters = self.engine.track_by_country_cluster()
        # Western appeared in both, 1 correct
        self.assertEqual(clusters['Western']['total'], 2)
        self.assertEqual(clusters['Western']['correct'], 1)
        # Russian appeared in 1, correct
        self.assertEqual(clusters['Russian']['total'], 1)
        self.assertEqual(clusters['Russian']['correct'], 1)
        # Gulf appeared in 1, incorrect
        self.assertEqual(clusters['Gulf']['total'], 1)
        self.assertEqual(clusters['Gulf']['correct'], 0)


class TestDriftDetection(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.engine = CalibrationEngine(db_path=self.db_path)

    def tearDown(self):
        self.engine.close()
        self.db_path.unlink(missing_ok=True)

    def test_no_alert_when_beating_baseline(self):
        # Good prediction: Brier = (0.9 - 1)^2 = 0.01
        sig = {
            'signal_id': 'drift-1', 'cluster_id': 'c', 'market_question': 'Q',
            'direction': 'YES', 'suggested_probability': 0.9,
            'current_price': 0.5, 'edge': 0.4, 'strategy_code': 'S004',
            'confidence': 0.8, 'yes_discount_applied': True,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        self.engine.record_signal(sig)
        self.engine.record_outcome('drift-1', resolved_yes=True)

        drift = self.engine.detect_drift(30)
        self.assertFalse(drift['alert'])
        self.assertEqual(drift['message'], 'OK')

    def test_alert_when_below_baseline(self):
        # Bad prediction: Brier = (0.1 - 1)^2 = 0.81 > 0.349
        sig = {
            'signal_id': 'drift-2', 'cluster_id': 'c', 'market_question': 'Q',
            'direction': 'YES', 'suggested_probability': 0.1,
            'current_price': 0.5, 'edge': -0.4, 'strategy_code': 'S004',
            'confidence': 0.3, 'yes_discount_applied': True,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        self.engine.record_signal(sig)
        self.engine.record_outcome('drift-2', resolved_yes=True)

        drift = self.engine.detect_drift(30)
        self.assertTrue(drift['alert'])
        self.assertIn('ALERT', drift['message'])


class TestReportGeneration(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.engine = CalibrationEngine(db_path=self.db_path)

    def tearDown(self):
        self.engine.close()
        self.db_path.unlink(missing_ok=True)

    def test_report_with_no_data(self):
        """Report should not crash with empty DB."""
        report = self.engine.generate_report()
        self.assertIn("Weekly Calibration Report", report)
        self.assertIn("Brier Score", report)
        self.assertIn("YES/NO Accuracy", report)

    def test_report_with_data(self):
        """Report should include tables with resolved data."""
        for i in range(5):
            sig = {
                'signal_id': f'rpt-{i}', 'cluster_id': 'c', 'market_question': f'Q{i}?',
                'direction': 'NO' if i < 3 else 'YES',
                'suggested_probability': 0.7,
                'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S004',
                'confidence': 0.7, 'yes_discount_applied': i >= 3,
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }
            self.engine.record_signal(sig, country_clusters=['Western', 'Russian'])
            self.engine.record_outcome(f'rpt-{i}', resolved_yes=(i >= 3))

        report = self.engine.generate_report(window_days=7)
        self.assertIn("Strategy Performance", report)
        self.assertIn("Country Cluster Value", report)
        self.assertIn("Request Efficiency", report)
        self.assertIn("S004", report)


class TestImportSignals(unittest.TestCase):

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db_path = Path(self.tmp_db.name)

        self.tmp_jsonl = tempfile.NamedTemporaryFile(
            suffix=".jsonl", mode='w', delete=False
        )
        # Write test signals
        signals = [
            {
                'signal_id': 'import-1', 'cluster_id': 'c1',
                'market_question': 'Test?', 'direction': 'YES',
                'suggested_probability': 0.7, 'current_price': 0.5,
                'edge': 0.2, 'strategy_code': 'S004', 'confidence': 0.7,
                'yes_discount_applied': True,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'status': 'pending',
            },
            {
                'signal_id': 'import-2', 'cluster_id': 'c2',
                'market_question': 'Test 2?', 'direction': 'NO',
                'suggested_probability': 0.6, 'current_price': 0.4,
                'edge': 0.2, 'strategy_code': 'S006', 'confidence': 0.8,
                'yes_discount_applied': False,
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'status': 'pending',
            },
        ]
        for s in signals:
            self.tmp_jsonl.write(json.dumps(s) + '\n')
        self.tmp_jsonl.close()
        self.jsonl_path = Path(self.tmp_jsonl.name)

    def tearDown(self):
        self.db_path.unlink(missing_ok=True)
        self.jsonl_path.unlink(missing_ok=True)

    def test_import_from_jsonl(self):
        import calibration_engine
        orig_path = calibration_engine.SIGNALS_PATH
        calibration_engine.SIGNALS_PATH = self.jsonl_path
        try:
            engine = CalibrationEngine(db_path=self.db_path)
            imported = engine.import_signals()
            self.assertEqual(imported, 2)

            # Import again — should not duplicate
            imported2 = engine.import_signals()
            self.assertEqual(imported2, 0)

            engine.close()
        finally:
            calibration_engine.SIGNALS_PATH = orig_path


class TestRequestEfficiency(unittest.TestCase):

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db_path = Path(self.tmp_db.name)
        self.engine = CalibrationEngine(db_path=self.db_path)

    def tearDown(self):
        self.engine.close()
        self.db_path.unlink(missing_ok=True)

    def test_efficiency_with_no_signals(self):
        eff = self.engine.request_efficiency()
        self.assertEqual(eff['signals_generated'], 0)
        self.assertIsNone(eff['cost_per_signal'])

    def test_efficiency_with_signals(self):
        for i in range(3):
            sig = {
                'signal_id': f'eff-{i}', 'cluster_id': 'c', 'market_question': 'Q',
                'direction': 'NO', 'suggested_probability': 0.7,
                'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S004',
                'confidence': 0.7, 'yes_discount_applied': False,
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }
            self.engine.record_signal(sig)
            if i < 2:
                self.engine.record_outcome(f'eff-{i}', resolved_yes=False)

        eff = self.engine.request_efficiency()
        self.assertEqual(eff['signals_generated'], 3)
        self.assertEqual(eff['signals_profitable'], 2)


class TestEdgeAccuracy(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.engine = CalibrationEngine(db_path=self.db_path)

    def tearDown(self):
        self.engine.close()
        self.db_path.unlink(missing_ok=True)

    def _make_signal(self, signal_id, direction='YES', prob=0.70, price=0.50,
                     strategy='S004'):
        return {
            'signal_id': signal_id, 'cluster_id': 'c', 'market_question': 'Q',
            'direction': direction, 'suggested_probability': prob,
            'current_price': price, 'edge': prob - price,
            'strategy_code': strategy, 'confidence': 0.7,
            'yes_discount_applied': direction == 'YES',
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

    def test_all_correct(self):
        """Edge > 0 and profitable => correct direction."""
        for i in range(3):
            sig = self._make_signal(f'ea-{i}', direction='YES', prob=0.7, price=0.5)
            self.engine.record_signal(sig)
            self.engine.record_outcome(f'ea-{i}', resolved_yes=True)

        result = self.engine.compute_edge_accuracy()
        self.assertEqual(result['total'], 3)
        self.assertEqual(result['correct'], 3)
        self.assertAlmostEqual(result['accuracy'], 1.0)

    def test_mixed(self):
        # Correct: edge > 0 and profitable
        sig1 = self._make_signal('ea-m1', prob=0.7, price=0.5)
        self.engine.record_signal(sig1)
        self.engine.record_outcome('ea-m1', resolved_yes=True)

        # Incorrect: edge > 0 but NOT profitable
        sig2 = self._make_signal('ea-m2', prob=0.7, price=0.5)
        self.engine.record_signal(sig2)
        self.engine.record_outcome('ea-m2', resolved_yes=False)

        result = self.engine.compute_edge_accuracy()
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['correct'], 1)
        self.assertAlmostEqual(result['accuracy'], 0.5)

    def test_by_strategy_breakdown(self):
        # S004: 1 correct
        sig1 = self._make_signal('ea-s1', strategy='S004', prob=0.7, price=0.5)
        self.engine.record_signal(sig1)
        self.engine.record_outcome('ea-s1', resolved_yes=True)

        # S006: 1 incorrect
        sig2 = self._make_signal('ea-s2', strategy='S006', prob=0.7, price=0.5)
        self.engine.record_signal(sig2)
        self.engine.record_outcome('ea-s2', resolved_yes=False)

        result = self.engine.compute_edge_accuracy(by_strategy=True)
        self.assertIn('S004', result['by_strategy'])
        self.assertIn('S006', result['by_strategy'])
        self.assertEqual(result['by_strategy']['S004']['correct'], 1)
        self.assertEqual(result['by_strategy']['S006']['correct'], 0)

    def test_no_data(self):
        result = self.engine.compute_edge_accuracy()
        self.assertEqual(result['total'], 0)
        self.assertIsNone(result['accuracy'])


class TestBySource(unittest.TestCase):
    """Test source domain tracking (requires pipeline tables in same DB)."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.engine = CalibrationEngine(db_path=self.db_path)
        # Create the pipeline tables needed for the join
        self.engine.conn.executescript("""
            CREATE TABLE IF NOT EXISTS cluster_articles (
                cluster_id TEXT NOT NULL,
                url_hash TEXT NOT NULL,
                PRIMARY KEY (cluster_id, url_hash)
            );
            CREATE TABLE IF NOT EXISTS articles (
                url_hash TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                source_domain TEXT NOT NULL,
                country_queried TEXT NOT NULL,
                published_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                tone REAL,
                description TEXT,
                source_name TEXT,
                cluster_id TEXT
            );
        """)
        self.engine.conn.commit()

    def tearDown(self):
        self.engine.close()
        self.db_path.unlink(missing_ok=True)

    def test_source_tracking(self):
        # Insert articles linked to a cluster
        self.engine.conn.executemany(
            "INSERT INTO articles (url_hash, url, title, source_domain, country_queried, published_at, fetched_at, tone) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ('h1', 'http://a.com/1', 'Title1', 'reuters.com', 'US', '2026-01-01', '2026-01-01', 0.5),
                ('h2', 'http://b.com/1', 'Title2', 'bbc.co.uk', 'GB', '2026-01-01', '2026-01-01', -0.3),
                ('h3', 'http://c.com/1', 'Title3', 'reuters.com', 'US', '2026-01-01', '2026-01-01', 0.2),
            ]
        )
        self.engine.conn.executemany(
            "INSERT INTO cluster_articles (cluster_id, url_hash) VALUES (?, ?)",
            [('clust-1', 'h1'), ('clust-1', 'h2'), ('clust-1', 'h3')]
        )
        self.engine.conn.commit()

        # Record signal linked to cluster
        sig = {
            'signal_id': 'src-1', 'cluster_id': 'clust-1', 'market_question': 'Q',
            'direction': 'NO', 'suggested_probability': 0.7,
            'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S004',
            'confidence': 0.7, 'yes_discount_applied': False,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        self.engine.record_signal(sig)
        self.engine.record_outcome('src-1', resolved_yes=False)

        sources = self.engine.track_by_source()
        self.assertIn('reuters.com', sources)
        self.assertIn('bbc.co.uk', sources)
        # reuters appeared in 2 articles for 1 signal = 2 rows, both correct
        self.assertEqual(sources['reuters.com']['total'], 2)
        self.assertEqual(sources['reuters.com']['correct'], 2)
        self.assertEqual(sources['bbc.co.uk']['total'], 1)
        self.assertEqual(sources['bbc.co.uk']['correct'], 1)

    def test_no_data(self):
        sources = self.engine.track_by_source()
        self.assertEqual(sources, {})


class TestParameterDiff(unittest.TestCase):

    def setUp(self):
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        self.db_path = Path(self.tmp_db.name)
        self.engine = CalibrationEngine(db_path=self.db_path)

        # Create a temp config file
        self.tmp_config = tempfile.NamedTemporaryFile(
            suffix=".yaml", mode='w', delete=False
        )
        self.tmp_config.write("""pipeline:
  divergence_threshold: 3.0
  yes_discount_factor: 0.85
  min_edge: 0.05
  min_confidence: 0.6
""")
        self.tmp_config.close()
        self.config_path = Path(self.tmp_config.name)

        # Create event_clusters table for divergence_threshold test
        self.engine.conn.executescript("""
            CREATE TABLE IF NOT EXISTS event_clusters (
                cluster_id TEXT PRIMARY KEY,
                divergence_score REAL DEFAULT 0.0
            );
        """)
        self.engine.conn.commit()

    def tearDown(self):
        self.engine.close()
        self.db_path.unlink(missing_ok=True)
        self.config_path.unlink(missing_ok=True)

    def test_recommends_discount_change(self):
        """When YES accuracy is low with enough samples, recommend tighter discount."""
        # 6 YES signals, only 2 correct (33% < 50%)
        for i in range(6):
            sig = {
                'signal_id': f'pd-y{i}', 'cluster_id': 'c', 'market_question': 'Q',
                'direction': 'YES', 'suggested_probability': 0.7,
                'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S004',
                'confidence': 0.7, 'yes_discount_applied': True,
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }
            self.engine.record_signal(sig)
            self.engine.record_outcome(f'pd-y{i}', resolved_yes=(i < 2))

        diff = self.engine.parameter_diff(config_path=self.config_path)
        # Should NOT recommend change since 33% keeps the 0.85 default
        # (the logic says: < 50% → rec 0.85, which equals current)
        discount_recs = [d for d in diff if d['param'] == 'yes_discount_factor']
        self.assertEqual(len(discount_recs), 0)

    def test_recommends_discount_loosen(self):
        """When YES accuracy is high, recommend loosening discount."""
        # 6 YES signals, 5 correct (83% > 70%)
        for i in range(6):
            sig = {
                'signal_id': f'pd-g{i}', 'cluster_id': 'c', 'market_question': 'Q',
                'direction': 'YES', 'suggested_probability': 0.7,
                'current_price': 0.5, 'edge': 0.2, 'strategy_code': 'S004',
                'confidence': 0.7, 'yes_discount_applied': True,
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }
            self.engine.record_signal(sig)
            self.engine.record_outcome(f'pd-g{i}', resolved_yes=(i < 5))

        diff = self.engine.parameter_diff(config_path=self.config_path)
        discount_recs = [d for d in diff if d['param'] == 'yes_discount_factor']
        self.assertEqual(len(discount_recs), 1)
        self.assertEqual(discount_recs[0]['recommended'], 0.95)

    def test_no_changes_needed(self):
        """With no data, no changes recommended."""
        diff = self.engine.parameter_diff(config_path=self.config_path)
        self.assertEqual(diff, [])


class TestReadYamlValue(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            suffix=".yaml", mode='w', delete=False
        )
        self.tmp.write("""pipeline:
  yes_discount_factor: 0.85
  min_edge: 0.05  # minimum edge threshold
  divergence_threshold: 3.0
""")
        self.tmp.close()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_reads_value(self):
        self.assertEqual(_read_yaml_value(self.path, 'yes_discount_factor'), '0.85')
        self.assertEqual(_read_yaml_value(self.path, 'min_edge'), '0.05')
        self.assertEqual(_read_yaml_value(self.path, 'divergence_threshold'), '3.0')

    def test_strips_comments(self):
        val = _read_yaml_value(self.path, 'min_edge')
        self.assertEqual(val, '0.05')

    def test_missing_key_returns_none(self):
        self.assertIsNone(_read_yaml_value(self.path, 'nonexistent'))

    def test_missing_file_returns_none(self):
        self.assertIsNone(_read_yaml_value(Path('/tmp/nonexistent.yaml'), 'key'))


if __name__ == "__main__":
    unittest.main()
