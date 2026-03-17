#!/usr/bin/env python3
"""NB11: Calibration Engine — Feedback, metrics, and weekly reporting for the News Intelligence Pipeline.

Tracks signal outcomes, computes Brier scores, identifies which country
clusters, strategies, and source domains are most predictive, monitors
request efficiency, detects drift, recommends parameter changes, and
generates weekly calibration reports.

Usage:
    # As library:
    from calibration_engine import CalibrationEngine
    engine = CalibrationEngine()
    engine.record_outcome(signal_id, resolved_yes=True, resolution_price=1.0)
    report = engine.generate_report()

    # CLI:
    python3 scripts/calibration_engine.py --report           # Weekly report
    python3 scripts/calibration_engine.py --brier             # Current Brier score
    python3 scripts/calibration_engine.py --drift             # Drift detection
    python3 scripts/calibration_engine.py --efficiency        # Request efficiency
    python3 scripts/calibration_engine.py --yes-accuracy      # YES/NO split
    python3 scripts/calibration_engine.py --by-country        # Country cluster performance
    python3 scripts/calibration_engine.py --by-source         # Source domain performance
    python3 scripts/calibration_engine.py --diff              # Parameter change recommendations
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
SIGNALS_PATH = PROJECT_ROOT / "data" / "signals.jsonl"
USAGE_PATH = PROJECT_ROOT / "data" / "brave-api-usage.json"
CONFIG_PATH = PROJECT_ROOT / "config" / "news-pipeline.yaml"


# --- Baseline ---
MARKET_BRIER_BASELINE = 0.349
YES_DISCOUNT_DEFAULT = 0.85


def _read_yaml_value(path: Path, key: str) -> str | None:
    """Extract a simple scalar value from a YAML file by key (no full parser)."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"{key}:"):
                    val = stripped.split(":", 1)[1].strip()
                    # Strip inline comments
                    if "#" in val:
                        val = val[:val.index("#")].strip()
                    return val
    except IOError:
        pass
    return None


# --- Data class ---

@dataclass
class SignalOutcome:
    signal_id: str
    cluster_id: str
    market_question: str
    direction: str               # YES | NO
    suggested_probability: float
    current_price: float
    edge: float
    strategy_code: str
    confidence: float
    yes_discount_applied: bool
    generated_at: str
    resolved_yes: bool | None = None
    resolution_price: float | None = None
    resolved_at: str | None = None
    country_clusters: list[str] | None = None
    profitable: bool | None = None


# --- Calibration Engine ---

class CalibrationEngine:
    """Tracks signal outcomes, computes calibration metrics, generates reports."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS signal_outcomes (
                signal_id            TEXT PRIMARY KEY,
                cluster_id           TEXT,
                market_question      TEXT,
                direction            TEXT,
                suggested_probability REAL,
                current_price        REAL,
                edge                 REAL,
                strategy_code        TEXT,
                confidence           REAL,
                yes_discount_applied INTEGER DEFAULT 0,
                generated_at         TEXT,
                resolved_yes         INTEGER,
                resolution_price     REAL,
                resolved_at          TEXT,
                country_clusters     TEXT,
                profitable           INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_outcomes_resolved
                ON signal_outcomes(resolved_at);
            CREATE INDEX IF NOT EXISTS idx_outcomes_strategy
                ON signal_outcomes(strategy_code);
            CREATE INDEX IF NOT EXISTS idx_outcomes_direction
                ON signal_outcomes(direction);
        """)
        self.conn.commit()

    # --- Recording ---

    def record_signal(self, signal_dict: dict, country_clusters: list[str] | None = None) -> None:
        """Record a generated signal (before outcome known)."""
        self.conn.execute("""
            INSERT OR IGNORE INTO signal_outcomes
                (signal_id, cluster_id, market_question, direction,
                 suggested_probability, current_price, edge,
                 strategy_code, confidence, yes_discount_applied,
                 generated_at, country_clusters)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal_dict.get('signal_id'),
            signal_dict.get('cluster_id'),
            signal_dict.get('market_question'),
            signal_dict.get('direction'),
            signal_dict.get('suggested_probability'),
            signal_dict.get('current_price'),
            signal_dict.get('edge'),
            signal_dict.get('strategy_code'),
            signal_dict.get('confidence'),
            int(signal_dict.get('yes_discount_applied', False)),
            signal_dict.get('generated_at'),
            json.dumps(country_clusters or []),
        ))
        self.conn.commit()

    def record_outcome(self, signal_id: str, resolved_yes: bool,
                       resolution_price: float = None) -> None:
        """Record the resolution outcome for a signal."""
        now = datetime.now(timezone.utc).isoformat()
        if resolution_price is None:
            resolution_price = 1.0 if resolved_yes else 0.0

        # Determine profitability
        row = self.conn.execute(
            "SELECT direction, current_price FROM signal_outcomes WHERE signal_id = ?",
            (signal_id,),
        ).fetchone()

        profitable = None
        if row:
            direction, entry_price = row
            if direction == 'YES':
                profitable = resolved_yes  # Bought YES, won if resolved YES
            else:
                profitable = not resolved_yes  # Bought NO, won if resolved NO

        self.conn.execute("""
            UPDATE signal_outcomes SET
                resolved_yes = ?, resolution_price = ?,
                resolved_at = ?, profitable = ?
            WHERE signal_id = ?
        """, (int(resolved_yes), resolution_price, now,
              int(profitable) if profitable is not None else None, signal_id))
        self.conn.commit()

    # --- Brier Score ---

    def compute_brier(self, window_days: int = 30) -> float | None:
        """Compute Brier score for resolved signals within window.

        Brier = mean((suggested_probability - outcome)^2)
        Lower is better. Perfect = 0, uninformed = 0.25.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        rows = self.conn.execute("""
            SELECT suggested_probability, resolved_yes FROM signal_outcomes
            WHERE resolved_at IS NOT NULL AND resolved_at >= ?
        """, (cutoff,)).fetchall()

        if not rows:
            return None

        scores = []
        for prob, outcome in rows:
            scores.append((prob - outcome) ** 2)
        return round(mean(scores), 4)

    def compute_market_brier(self, window_days: int = 30) -> float | None:
        """Compute market's Brier score (using current_price at signal time)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        rows = self.conn.execute("""
            SELECT current_price, resolved_yes FROM signal_outcomes
            WHERE resolved_at IS NOT NULL AND resolved_at >= ?
        """, (cutoff,)).fetchall()

        if not rows:
            return None

        scores = []
        for price, outcome in rows:
            scores.append((price - outcome) ** 2)
        return round(mean(scores), 4)

    # --- YES/NO Accuracy ---

    def track_yes_accuracy(self) -> dict:
        """Track YES prediction accuracy. Returns stats + recommended discount."""
        rows = self.conn.execute("""
            SELECT direction, profitable FROM signal_outcomes
            WHERE resolved_at IS NOT NULL AND profitable IS NOT NULL
        """).fetchall()

        if not rows:
            return {'yes_total': 0, 'yes_correct': 0, 'no_total': 0, 'no_correct': 0,
                    'yes_rate': None, 'no_rate': None,
                    'recommended_discount': YES_DISCOUNT_DEFAULT}

        yes_total = sum(1 for d, _ in rows if d == 'YES')
        yes_correct = sum(1 for d, p in rows if d == 'YES' and p)
        no_total = sum(1 for d, _ in rows if d == 'NO')
        no_correct = sum(1 for d, p in rows if d == 'NO' and p)

        yes_rate = yes_correct / yes_total if yes_total else None
        no_rate = no_correct / no_total if no_total else None

        # Adjust YES discount: if YES accuracy improves, relax discount
        if yes_rate is not None and yes_total >= 5:
            if yes_rate >= 0.7:
                rec = 0.95  # Strong — barely discount
            elif yes_rate >= 0.5:
                rec = 0.90  # Improving — mild discount
            else:
                rec = 0.85  # Still weak — keep current discount
        else:
            rec = YES_DISCOUNT_DEFAULT

        return {
            'yes_total': yes_total, 'yes_correct': yes_correct,
            'no_total': no_total, 'no_correct': no_correct,
            'yes_rate': round(yes_rate, 3) if yes_rate is not None else None,
            'no_rate': round(no_rate, 3) if no_rate is not None else None,
            'recommended_discount': rec,
        }

    # --- Edge Accuracy ---

    def compute_edge_accuracy(self, by_strategy: bool = False) -> dict:
        """How often did edge > 0 correlate with correct direction?

        Returns overall accuracy and optionally per-strategy breakdown.
        """
        rows = self.conn.execute("""
            SELECT strategy_code, edge, profitable FROM signal_outcomes
            WHERE resolved_at IS NOT NULL AND profitable IS NOT NULL
        """).fetchall()

        if not rows:
            return {'total': 0, 'correct': 0, 'accuracy': None, 'by_strategy': {}}

        total = len(rows)
        correct = sum(1 for _, edge, prof in rows if (edge > 0 and prof) or (edge <= 0 and not prof))

        result = {
            'total': total,
            'correct': correct,
            'accuracy': round(correct / total, 3) if total else None,
        }

        if by_strategy:
            strat_map: dict[str, dict] = {}
            for strategy, edge, prof in rows:
                if strategy not in strat_map:
                    strat_map[strategy] = {'total': 0, 'correct': 0}
                strat_map[strategy]['total'] += 1
                if (edge > 0 and prof) or (edge <= 0 and not prof):
                    strat_map[strategy]['correct'] += 1
            for s in strat_map.values():
                s['accuracy'] = round(s['correct'] / s['total'], 3) if s['total'] else None
            result['by_strategy'] = strat_map
        else:
            result['by_strategy'] = {}

        return result

    # --- Country Cluster Analysis ---

    def track_by_country_cluster(self) -> dict[str, dict]:
        """Which country clusters correlate with correct signals?

        Returns {cluster_name: {total, correct, accuracy, avg_divergence}}.
        """
        rows = self.conn.execute("""
            SELECT country_clusters, profitable FROM signal_outcomes
            WHERE resolved_at IS NOT NULL AND profitable IS NOT NULL
              AND country_clusters IS NOT NULL
        """).fetchall()

        cluster_stats: dict[str, dict] = {}
        for clusters_json, profitable in rows:
            try:
                clusters = json.loads(clusters_json)
            except (json.JSONDecodeError, TypeError):
                continue
            for c in clusters:
                if c not in cluster_stats:
                    cluster_stats[c] = {'total': 0, 'correct': 0}
                cluster_stats[c]['total'] += 1
                if profitable:
                    cluster_stats[c]['correct'] += 1

        for c, s in cluster_stats.items():
            s['accuracy'] = round(s['correct'] / s['total'], 3) if s['total'] else 0.0

        return cluster_stats

    # --- Strategy Performance ---

    def track_by_strategy(self) -> dict[str, dict]:
        """Performance by strategy code."""
        rows = self.conn.execute("""
            SELECT strategy_code, suggested_probability, resolved_yes, profitable, edge
            FROM signal_outcomes
            WHERE resolved_at IS NOT NULL AND profitable IS NOT NULL
        """).fetchall()

        strat_stats: dict[str, dict] = {}
        for strategy, prob, outcome, profitable, edge in rows:
            if strategy not in strat_stats:
                strat_stats[strategy] = {
                    'total': 0, 'correct': 0, 'brier_scores': [], 'edges': []
                }
            s = strat_stats[strategy]
            s['total'] += 1
            if profitable:
                s['correct'] += 1
            s['brier_scores'].append((prob - outcome) ** 2)
            s['edges'].append(edge)

        for strategy, s in strat_stats.items():
            s['accuracy'] = round(s['correct'] / s['total'], 3) if s['total'] else 0.0
            s['brier'] = round(mean(s['brier_scores']), 4) if s['brier_scores'] else None
            s['avg_edge'] = round(mean(s['edges']), 4) if s['edges'] else None
            del s['brier_scores']
            del s['edges']

        return strat_stats

    # --- Source Domain Analysis ---

    def track_by_source(self) -> dict[str, dict]:
        """Which source domains are most/least reliable based on signal outcomes?

        Joins signal_outcomes → cluster_articles → articles to trace
        source domains that contributed to each signal's cluster.
        Returns {domain: {total, correct, accuracy, avg_tone}}.
        """
        try:
            rows = self.conn.execute("""
                SELECT a.source_domain, so.profitable, a.tone
                FROM signal_outcomes so
                JOIN cluster_articles ca ON ca.cluster_id = so.cluster_id
                JOIN articles a ON a.url_hash = ca.url_hash
                WHERE so.resolved_at IS NOT NULL AND so.profitable IS NOT NULL
            """).fetchall()
        except sqlite3.OperationalError:
            # Pipeline tables (cluster_articles, articles) may not exist yet
            return {}

        if not rows:
            return {}

        domain_stats: dict[str, dict] = {}
        for domain, profitable, tone in rows:
            if not domain:
                continue
            if domain not in domain_stats:
                domain_stats[domain] = {'total': 0, 'correct': 0, 'tones': []}
            domain_stats[domain]['total'] += 1
            if profitable:
                domain_stats[domain]['correct'] += 1
            if tone is not None:
                domain_stats[domain]['tones'].append(tone)

        for domain, s in domain_stats.items():
            s['accuracy'] = round(s['correct'] / s['total'], 3) if s['total'] else 0.0
            s['avg_tone'] = round(mean(s['tones']), 3) if s['tones'] else None
            del s['tones']

        return domain_stats

    # --- Drift Detection ---

    def detect_drift(self, window_days: int = 30) -> dict:
        """Detect calibration drift. Alert if Brier drops below market baseline."""
        brier = self.compute_brier(window_days)
        market_brier = self.compute_market_brier(window_days)

        n_resolved = self.conn.execute("""
            SELECT COUNT(*) FROM signal_outcomes WHERE resolved_at IS NOT NULL
        """).fetchone()[0]

        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        n_window = self.conn.execute("""
            SELECT COUNT(*) FROM signal_outcomes
            WHERE resolved_at IS NOT NULL AND resolved_at >= ?
        """, (cutoff,)).fetchone()[0]

        alert = False
        message = "OK"
        if brier is not None and brier > MARKET_BRIER_BASELINE:
            alert = True
            message = f"ALERT: Brier {brier:.3f} > market baseline {MARKET_BRIER_BASELINE:.3f}"
        elif brier is not None and market_brier is not None and brier > market_brier:
            alert = True
            message = f"WARNING: Our Brier {brier:.3f} > market's {market_brier:.3f} in window"

        return {
            'brier_ours': brier,
            'brier_market': market_brier,
            'n_resolved_total': n_resolved,
            'n_resolved_window': n_window,
            'window_days': window_days,
            'alert': alert,
            'message': message,
        }

    # --- Request Efficiency ---

    def request_efficiency(self) -> dict:
        """Cost per signal and cost per profitable signal."""
        # Count signals generated (total)
        n_signals = self.conn.execute(
            "SELECT COUNT(*) FROM signal_outcomes"
        ).fetchone()[0]

        n_profitable = self.conn.execute(
            "SELECT COUNT(*) FROM signal_outcomes WHERE profitable = 1"
        ).fetchone()[0]

        # Load API usage
        total_requests = 0
        if USAGE_PATH.exists():
            try:
                with open(USAGE_PATH) as f:
                    usage = json.load(f)
                total_requests = usage.get('total', 0)
            except (json.JSONDecodeError, IOError):
                pass

        cost_per_1000 = 5.0  # $5/1000 requests
        total_cost = total_requests / 1000 * cost_per_1000

        return {
            'total_requests': total_requests,
            'total_cost_usd': round(total_cost, 2),
            'signals_generated': n_signals,
            'signals_profitable': n_profitable,
            'cost_per_signal': round(total_cost / n_signals, 2) if n_signals else None,
            'cost_per_profitable': round(total_cost / n_profitable, 2) if n_profitable else None,
        }

    # --- Brave Country Pruning Recommendations ---

    def country_pruning_recommendations(self) -> list[dict]:
        """Identify country clusters that consume budget without adding signal value."""
        cluster_stats = self.track_by_country_cluster()
        recommendations = []

        for cluster, stats in cluster_stats.items():
            if stats['total'] >= 3 and stats['accuracy'] < 0.3:
                recommendations.append({
                    'cluster': cluster,
                    'total': stats['total'],
                    'accuracy': stats['accuracy'],
                    'action': f"Consider pruning {cluster} from low-value queries",
                })

        return recommendations

    # --- Parameter Recommendations ---

    def parameter_diff(self, config_path: Path = CONFIG_PATH) -> list[dict]:
        """Compute recommended config.yaml parameter changes with evidence.

        Compares current config values to what outcome data suggests.
        Returns list of {param, current, recommended, evidence}.
        """
        recs = []

        # 1. yes_discount_factor
        ya = self.track_yes_accuracy()
        current_discount = _read_yaml_value(config_path, 'yes_discount_factor')
        current_discount = float(current_discount) if current_discount else YES_DISCOUNT_DEFAULT
        if ya['recommended_discount'] != current_discount:
            yes_rate_str = f"{ya['yes_rate']:.0%}" if ya['yes_rate'] is not None else "N/A"
            recs.append({
                'param': 'yes_discount_factor',
                'current': current_discount,
                'recommended': ya['recommended_discount'],
                'evidence': f"YES accuracy {yes_rate_str} ({ya['yes_correct']}/{ya['yes_total']})",
            })

        # 2. min_edge
        current_edge = _read_yaml_value(config_path, 'min_edge')
        current_edge = float(current_edge) if current_edge else 0.05
        edge_acc = self.compute_edge_accuracy()
        if edge_acc['total'] >= 5:
            if edge_acc['accuracy'] is not None and edge_acc['accuracy'] < 0.5:
                # Edge signal is worse than coin flip — tighten threshold
                recs.append({
                    'param': 'min_edge',
                    'current': current_edge,
                    'recommended': round(current_edge + 0.02, 2),
                    'evidence': (f"Edge accuracy only {edge_acc['accuracy']:.0%} "
                                 f"({edge_acc['correct']}/{edge_acc['total']}) — "
                                 f"raise threshold to filter weak signals"),
                })
            elif edge_acc['accuracy'] is not None and edge_acc['accuracy'] > 0.75:
                # Strong edge signal — can loosen threshold
                new_edge = max(0.03, round(current_edge - 0.01, 2))
                if new_edge != current_edge:
                    recs.append({
                        'param': 'min_edge',
                        'current': current_edge,
                        'recommended': new_edge,
                        'evidence': (f"Edge accuracy {edge_acc['accuracy']:.0%} "
                                     f"({edge_acc['correct']}/{edge_acc['total']}) — "
                                     f"can safely lower threshold for more signals"),
                    })

        # 3. divergence_threshold
        current_div = _read_yaml_value(config_path, 'divergence_threshold')
        current_div = float(current_div) if current_div else 3.0
        # Check if lower-divergence clusters still produce correct signals
        try:
            low_div_rows = self.conn.execute("""
                SELECT so.profitable FROM signal_outcomes so
                JOIN event_clusters ec ON ec.cluster_id = so.cluster_id
                WHERE so.resolved_at IS NOT NULL AND so.profitable IS NOT NULL
                  AND ec.divergence_score < ?
            """, (current_div,)).fetchall()
        except sqlite3.OperationalError:
            low_div_rows = []
        if low_div_rows:
            low_correct = sum(1 for (p,) in low_div_rows if p)
            low_total = len(low_div_rows)
            low_rate = low_correct / low_total if low_total else 0
            if low_total >= 3 and low_rate > 0.6:
                recs.append({
                    'param': 'divergence_threshold',
                    'current': current_div,
                    'recommended': round(current_div - 0.5, 1),
                    'evidence': (f"{low_correct}/{low_total} ({low_rate:.0%}) sub-threshold "
                                 f"signals were correct — lower threshold to capture more"),
                })

        # 4. Country pruning
        pruning = self.country_pruning_recommendations()
        for p in pruning:
            recs.append({
                'param': f"queries.*.countries (prune {p['cluster']})",
                'current': 'included',
                'recommended': 'remove',
                'evidence': (f"{p['cluster']} accuracy {p['accuracy']:.0%} "
                             f"over {p['total']} signals — consuming budget for no value"),
            })

        return recs

    # --- Weekly Report ---

    def generate_report(self, window_days: int = 7) -> str:
        """Generate weekly calibration report as markdown."""
        now = datetime.now(timezone.utc)
        lines = [
            f"# Weekly Calibration Report",
            f"**Generated**: {now.strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Window**: Last {window_days} days",
            "",
        ]

        # 1. Brier score
        brier = self.compute_brier(window_days)
        brier_30 = self.compute_brier(30)
        market_brier = self.compute_market_brier(window_days)

        lines.append("## 1. Brier Score")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| This week | **{brier:.4f}** |" if brier is not None else "| This week | N/A (no resolutions) |")
        lines.append(f"| Rolling 30d | {brier_30:.4f} |" if brier_30 is not None else "| Rolling 30d | N/A |")
        lines.append(f"| Market (this week) | {market_brier:.4f} |" if market_brier is not None else "| Market (this week) | N/A |")
        lines.append(f"| Market baseline | {MARKET_BRIER_BASELINE} |")
        lines.append("")

        # Drift
        drift = self.detect_drift(window_days)
        if drift['alert']:
            lines.append(f"> **{drift['message']}**")
            lines.append("")

        # 2. YES/NO accuracy
        ya = self.track_yes_accuracy()
        lines.append("## 2. YES/NO Accuracy")
        lines.append("")
        lines.append(f"| Direction | Total | Correct | Rate |")
        lines.append(f"|-----------|-------|---------|------|")
        yes_rate_str = f"{ya['yes_rate']:.0%}" if ya['yes_rate'] is not None else "N/A"
        no_rate_str = f"{ya['no_rate']:.0%}" if ya['no_rate'] is not None else "N/A"
        lines.append(f"| YES | {ya['yes_total']} | {ya['yes_correct']} | {yes_rate_str} |")
        lines.append(f"| NO | {ya['no_total']} | {ya['no_correct']} | {no_rate_str} |")
        lines.append("")
        lines.append(f"**YES discount**: current={YES_DISCOUNT_DEFAULT}, "
                     f"recommended={ya['recommended_discount']}")
        if ya['recommended_discount'] != YES_DISCOUNT_DEFAULT:
            lines.append(f"> Recommend updating `yes_discount_factor` to "
                        f"{ya['recommended_discount']} in config.yaml")
        lines.append("")

        # 3. Strategy performance
        strats = self.track_by_strategy()
        lines.append("## 3. Strategy Performance")
        lines.append("")
        if strats:
            lines.append(f"| Strategy | Total | Correct | Accuracy | Brier | Avg Edge |")
            lines.append(f"|----------|-------|---------|----------|-------|----------|")
            for code, s in sorted(strats.items()):
                brier_s = f"{s['brier']:.4f}" if s['brier'] is not None else "N/A"
                edge_s = f"{s['avg_edge']:+.4f}" if s['avg_edge'] is not None else "N/A"
                lines.append(f"| {code} | {s['total']} | {s['correct']} | "
                            f"{s['accuracy']:.0%} | {brier_s} | {edge_s} |")
        else:
            lines.append("No resolved signals by strategy yet.")
        lines.append("")

        # 4. Country cluster value
        clusters = self.track_by_country_cluster()
        lines.append("## 4. Country Cluster Value")
        lines.append("")
        if clusters:
            lines.append(f"| Cluster | Signals | Correct | Accuracy |")
            lines.append(f"|---------|---------|---------|----------|")
            for name, s in sorted(clusters.items(), key=lambda x: -x[1]['accuracy']):
                lines.append(f"| {name} | {s['total']} | {s['correct']} | "
                            f"{s['accuracy']:.0%} |")
            lines.append("")

            pruning = self.country_pruning_recommendations()
            if pruning:
                lines.append("### Pruning Recommendations")
                for p in pruning:
                    lines.append(f"- **{p['cluster']}**: {p['accuracy']:.0%} accuracy "
                                f"over {p['total']} signals — {p['action']}")
                lines.append("")
        else:
            lines.append("No country cluster data yet.")
            lines.append("")

        # 5. Request efficiency
        eff = self.request_efficiency()
        lines.append("## 5. Request Efficiency")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Brave API requests (month) | {eff['total_requests']} |")
        lines.append(f"| Estimated cost | ${eff['total_cost_usd']:.2f} |")
        lines.append(f"| Signals generated | {eff['signals_generated']} |")
        lines.append(f"| Signals profitable | {eff['signals_profitable']} |")
        cps = f"${eff['cost_per_signal']:.2f}" if eff['cost_per_signal'] is not None else "N/A"
        cpp = f"${eff['cost_per_profitable']:.2f}" if eff['cost_per_profitable'] is not None else "N/A"
        lines.append(f"| Cost per signal | {cps} |")
        lines.append(f"| Cost per profitable signal | {cpp} |")
        lines.append("")

        # 6. Source Reliability
        sources = self.track_by_source()
        lines.append("## 6. Source Reliability")
        lines.append("")
        if sources:
            sorted_sources = sorted(sources.items(), key=lambda x: -x[1]['total'])[:20]
            lines.append("| Domain | Signals | Correct | Accuracy | Avg Tone |")
            lines.append("|--------|---------|---------|----------|----------|")
            for domain, s in sorted_sources:
                tone_str = f"{s['avg_tone']:+.2f}" if s['avg_tone'] is not None else "N/A"
                lines.append(f"| {domain} | {s['total']} | {s['correct']} | "
                            f"{s['accuracy']:.0%} | {tone_str} |")
            misleading = [d for d, s in sources.items()
                         if s['total'] >= 3 and s['accuracy'] < 0.3]
            if misleading:
                lines.append("")
                lines.append("### Misleading Sources (accuracy < 30%, N >= 3)")
                for d in misleading:
                    s = sources[d]
                    lines.append(f"- **{d}**: {s['accuracy']:.0%} over {s['total']} signals")
        else:
            lines.append("No source data yet (requires resolved signals with cluster linkage).")
        lines.append("")

        # 7. Parameter Diff
        diff = self.parameter_diff()
        lines.append("## 7. Parameter Recommendations")
        lines.append("")
        if diff:
            lines.append("| Parameter | Current | Recommended | Evidence |")
            lines.append("|-----------|---------|-------------|----------|")
            for d in diff:
                lines.append(f"| `{d['param']}` | {d['current']} | "
                            f"**{d['recommended']}** | {d['evidence']} |")
        else:
            lines.append("No parameter changes recommended (insufficient data or all optimal).")
        lines.append("")

        # 8. Signal detail (last N days)
        cutoff = (now - timedelta(days=window_days)).isoformat()
        rows = self.conn.execute("""
            SELECT signal_id, market_question, direction,
                   suggested_probability, current_price, edge,
                   strategy_code, resolved_yes, profitable
            FROM signal_outcomes
            WHERE generated_at >= ? OR resolved_at >= ?
            ORDER BY generated_at DESC
        """, (cutoff, cutoff)).fetchall()

        if rows:
            lines.append("## 8. Signal Detail (This Week)")
            lines.append("")
            lines.append("| Signal | Market | Dir | Est | Mkt | Edge | Strat | Outcome |")
            lines.append("|--------|--------|-----|-----|-----|------|-------|---------|")
            for row in rows:
                sid, q, d, prob, price, edge, strat, resolved, profitable = row
                q_short = (q or "?")[:30]
                outcome = "pending"
                if resolved is not None:
                    outcome = "WIN" if profitable else "LOSS"
                lines.append(
                    f"| {sid[:8]} | {q_short} | {d} | "
                    f"{prob:.0%} | {price:.0%} | {edge:+.0%} | "
                    f"{strat} | {outcome} |"
                )
            lines.append("")

        return "\n".join(lines)

    # --- Import from signals.jsonl ---

    def import_signals(self) -> int:
        """Import signals from signals.jsonl that aren't yet in the outcomes table."""
        if not SIGNALS_PATH.exists():
            return 0

        imported = 0
        with open(SIGNALS_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    signal = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = signal.get('signal_id')
                if not sid:
                    continue
                exists = self.conn.execute(
                    "SELECT 1 FROM signal_outcomes WHERE signal_id = ?", (sid,)
                ).fetchone()
                if not exists:
                    self.record_signal(signal)
                    imported += 1

        return imported

    def close(self):
        self.conn.close()


# --- CLI ---

def main():
    args = sys.argv[1:]

    engine = CalibrationEngine()

    if "--report" in args:
        days = 7
        for i, a in enumerate(args):
            if a == "--days" and i + 1 < len(args):
                days = int(args[i + 1])
        # Import any new signals first
        imported = engine.import_signals()
        if imported:
            print(f"Imported {imported} new signal(s) from signals.jsonl\n")
        report = engine.generate_report(window_days=days)
        print(report)

    elif "--brier" in args:
        days = 30
        for i, a in enumerate(args):
            if a == "--days" and i + 1 < len(args):
                days = int(args[i + 1])
        brier = engine.compute_brier(days)
        market = engine.compute_market_brier(days)
        if brier is not None:
            print(f"Brier (ours, {days}d):   {brier:.4f}")
            print(f"Brier (market, {days}d): {market:.4f}" if market else "Market brier: N/A")
            print(f"Baseline:             {MARKET_BRIER_BASELINE}")
            if brier < MARKET_BRIER_BASELINE:
                print("Status: BEATING market baseline")
            else:
                print("Status: BELOW market baseline")
        else:
            print(f"No resolved signals in last {days} days.")

    elif "--drift" in args:
        drift = engine.detect_drift()
        print(f"Drift detection (30d window):")
        print(f"  Brier (ours):   {drift['brier_ours']}" if drift['brier_ours'] else "  Brier: N/A")
        print(f"  Brier (market): {drift['brier_market']}" if drift['brier_market'] else "  Market: N/A")
        print(f"  Resolved total: {drift['n_resolved_total']}")
        print(f"  Resolved window: {drift['n_resolved_window']}")
        print(f"  Status: {drift['message']}")

    elif "--efficiency" in args:
        eff = engine.request_efficiency()
        print("Request Efficiency:")
        for k, v in eff.items():
            print(f"  {k}: {v}")

    elif "--yes-accuracy" in args:
        ya = engine.track_yes_accuracy()
        print("YES/NO Accuracy:")
        print(f"  YES: {ya['yes_correct']}/{ya['yes_total']}"
              + (f" ({ya['yes_rate']:.0%})" if ya['yes_rate'] is not None else ""))
        print(f"  NO:  {ya['no_correct']}/{ya['no_total']}"
              + (f" ({ya['no_rate']:.0%})" if ya['no_rate'] is not None else ""))
        print(f"  Recommended discount: {ya['recommended_discount']}"
              + (f" (current: {YES_DISCOUNT_DEFAULT})" if ya['recommended_discount'] != YES_DISCOUNT_DEFAULT else " (no change)"))

    elif "--by-country" in args:
        clusters = engine.track_by_country_cluster()
        if clusters:
            print("Country Cluster Performance:")
            for name, s in sorted(clusters.items(), key=lambda x: -x[1]['accuracy']):
                print(f"  {name:12s}  {s['correct']}/{s['total']}  ({s['accuracy']:.0%})")
            pruning = engine.country_pruning_recommendations()
            if pruning:
                print("\nPruning recommendations:")
                for p in pruning:
                    print(f"  {p['action']}")
        else:
            print("No country cluster data yet.")

    elif "--by-source" in args:
        sources = engine.track_by_source()
        if sources:
            print("Source Domain Performance:")
            for domain, s in sorted(sources.items(), key=lambda x: -x[1]['total'])[:20]:
                tone_str = f"{s['avg_tone']:+.2f}" if s['avg_tone'] is not None else "N/A"
                print(f"  {domain:30s}  {s['correct']}/{s['total']}  "
                      f"({s['accuracy']:.0%})  tone={tone_str}")
        else:
            print("No source data yet.")

    elif "--diff" in args:
        diff = engine.parameter_diff()
        if diff:
            print("Parameter Recommendations:")
            for d in diff:
                print(f"  {d['param']}: {d['current']} -> {d['recommended']}")
                print(f"    Evidence: {d['evidence']}")
        else:
            print("No parameter changes recommended.")

    elif "--import" in args:
        imported = engine.import_signals()
        print(f"Imported {imported} signal(s) from signals.jsonl")

    else:
        print("NB11: Calibration Engine")
        print("  --report [--days N]    Weekly calibration report (default 7d)")
        print("  --brier [--days N]     Current Brier score (default 30d)")
        print("  --drift                Drift detection")
        print("  --efficiency           Request efficiency metrics")
        print("  --yes-accuracy         YES/NO accuracy split")
        print("  --by-country           Country cluster performance")
        print("  --by-source            Source domain performance")
        print("  --diff                 Parameter change recommendations")
        print("  --import               Import signals from signals.jsonl")

    engine.close()


if __name__ == "__main__":
    main()
