#!/usr/bin/env python3
"""NB08: News Intelligence Pipeline — Orchestrator.

Main loop that chains NB02-NB07 stages:
  BravePoller → ToneEntityExtractor → PerspectiveTagger →
  EventClusterer → TruthExtractor → SignalGenerator → Deliver

Usage:
    python3 scripts/orchestrator.py                              # Run with default config
    python3 scripts/orchestrator.py --config config/custom.yaml  # Custom config
    python3 scripts/orchestrator.py --once                       # Single tick, then exit
    python3 scripts/orchestrator.py --dry-run                    # Log actions, don't execute
    python3 scripts/orchestrator.py --status                     # Show pipeline state
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

# Pipeline modules
from brave_ingestor import Article, BraveNewsPoller, QueryConfig, BudgetTracker  # noqa: E402
from tone_entity_extractor import ToneEntityExtractor  # noqa: E402
from perspective_matrix import PerspectiveTagger, PerspectiveMatrix  # noqa: E402
from event_clusterer import EventClusterer, EventCluster  # noqa: E402
from truth_extractor import TruthExtractor, TruthExtractionResult  # noqa: E402
from signal_generator import SignalGenerator, GeneratedSignal  # noqa: E402

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger("pipeline")

# --- Paths ---
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
SCHEMA_PATH = SCRIPT_DIR / "schema.sql"
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "news-pipeline.yaml"
PENDING_SIGNALS_FILE = PROJECT_ROOT / "data" / "pending-signals.json"


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    """Parsed pipeline configuration."""
    queries: list[QueryConfig]
    divergence_threshold: float
    max_extractions_per_hour: int
    max_pending_signals: int
    cluster_expiry_hours: int
    yes_discount_factor: float
    min_edge: float
    min_confidence: float
    circuit_breaker_threshold: int
    circuit_breaker_pause_minutes: int
    tone_use_llm: bool
    tone_model: str
    delivery_channel: str
    webhook_url: str
    log_level: str
    log_file: str


def _env_sub(val: str) -> str:
    """Replace ${VAR} with os.environ.get(VAR, '')."""
    if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
        return os.environ.get(val[2:-1], "")
    return val


def load_config(path: Path) -> PipelineConfig:
    """Load YAML config with env var substitution."""
    if yaml is None:
        raise ImportError("pyyaml required. Install: pip3 install pyyaml")

    with open(path) as f:
        raw = yaml.safe_load(f)

    queries = []
    for q in raw.get("queries", []):
        queries.append(QueryConfig(
            name=q["name"],
            keywords=q["keywords"],
            boolean_mode=q.get("boolean_mode", "OR"),
            countries=q.get("countries", ["US", "GB"]),
            freshness=q.get("freshness", "pd"),
            count_per_country=q.get("count_per_country", 20),
            interval_minutes=q.get("interval_minutes", 1440),
            extra_snippets=q.get("extra_snippets", True),
        ))

    pipe = raw.get("pipeline", {})
    delivery = raw.get("delivery", {})
    log_cfg = raw.get("logging", {})

    return PipelineConfig(
        queries=queries,
        divergence_threshold=pipe.get("divergence_threshold", 3.0),
        max_extractions_per_hour=pipe.get("max_extractions_per_hour", 20),
        max_pending_signals=pipe.get("max_pending_signals", 3),
        cluster_expiry_hours=pipe.get("cluster_expiry_hours", 72),
        yes_discount_factor=pipe.get("yes_discount_factor", 0.85),
        min_edge=pipe.get("min_edge", 0.05),
        min_confidence=pipe.get("min_confidence", 0.6),
        circuit_breaker_threshold=pipe.get("circuit_breaker_threshold", 3),
        circuit_breaker_pause_minutes=pipe.get("circuit_breaker_pause_minutes", 30),
        tone_use_llm=pipe.get("tone_use_llm", True),
        tone_model=pipe.get("tone_model", "claude-haiku-4-5-20251001"),
        delivery_channel=delivery.get("channel", "telegram"),
        webhook_url=_env_sub(delivery.get("webhook_url", "")),
        log_level=log_cfg.get("level", "INFO"),
        log_file=log_cfg.get("file", "data/news-pipeline.log"),
    )


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Initialize SQLite database from schema.sql."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    if SCHEMA_PATH.exists():
        schema = SCHEMA_PATH.read_text()
        # Execute each statement separately (skip PRAGMA lines already set)
        for statement in schema.split(";"):
            stmt = statement.strip()
            if stmt and not stmt.upper().startswith("PRAGMA"):
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass  # Table/index already exists
        conn.commit()
    else:
        logger.warning("schema.sql not found at %s — using module-level schemas", SCHEMA_PATH)

    return conn


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Trips after N consecutive failures. Resets after pause period."""

    def __init__(self, threshold: int = 3, pause_minutes: int = 30):
        self.threshold = threshold
        self.pause_minutes = pause_minutes
        self._failures = 0
        self._tripped_at: float | None = None

    def record_success(self):
        self._failures = 0
        self._tripped_at = None

    def record_failure(self):
        self._failures += 1
        if self._failures >= self.threshold:
            self._tripped_at = time.time()
            logger.error("Circuit breaker TRIPPED after %d failures. "
                         "Pausing %d min.", self._failures, self.pause_minutes)

    @property
    def is_open(self) -> bool:
        if self._tripped_at is None:
            return False
        elapsed = (time.time() - self._tripped_at) / 60
        if elapsed >= self.pause_minutes:
            logger.info("Circuit breaker RESET after %.0f min pause.", elapsed)
            self._failures = 0
            self._tripped_at = None
            return False
        return True

    @property
    def minutes_until_reset(self) -> float:
        if self._tripped_at is None:
            return 0
        return max(0, self.pause_minutes - (time.time() - self._tripped_at) / 60)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def format_signal_message(signal: GeneratedSignal,
                          extraction: TruthExtractionResult | None = None,
                          cluster: EventCluster | None = None) -> str:
    """Format a signal for Telegram delivery per NB08 spec."""
    lines = [
        f"SIGNAL [SIG-{signal.signal_id}] — {signal.market_question}",
        "",
        f"Direction: {signal.direction} | Edge: {signal.edge:+.1%} | "
        f"Confidence: {signal.confidence:.0%}",
        f"Size: ${signal.kelly_usdc:.0f} USDC (Kelly {signal.kelly_fraction:.2f})",
        f"Strategy: {signal.strategy_code}",
    ]

    if extraction and extraction.objective_kernel:
        lines.extend([
            "",
            "Truth kernel:",
            extraction.objective_kernel,
        ])

    if cluster and cluster.perspective_matrix:
        pm = cluster.perspective_matrix
        persp_parts = []
        for name, cv in sorted(pm.clusters.items()):
            persp_parts.append(f"{name} {cv.mean_tone:+.1f}")
        persp_line = " | ".join(persp_parts)

        n_articles = len(cluster.articles) if cluster.articles else 0
        n_countries = len(set(
            a.country_queried for a in cluster.articles
        )) if cluster.articles else 0

        lines.extend([
            "",
            "Perspective split:",
            persp_line,
            f"Divergence: {cluster.divergence_score:.1f} | "
            f"Sources: {n_articles} articles, {n_countries} countries",
        ])

    lines.extend([
        "",
        f"Reply A=Approve  R=Reject  I=More info (ref: SIG-{signal.signal_id})",
    ])

    return "\n".join(lines)


def deliver_signal(message: str, webhook_url: str, signal_id: str,
                   conn: sqlite3.Connection) -> bool:
    """Send signal via webhook. Returns True on success."""
    if not webhook_url:
        logger.info("No webhook URL — logging signal locally only.")
        print(f"\n{'=' * 60}")
        print(message)
        print(f"{'=' * 60}\n")
        return False

    try:
        payload = json.dumps({"text": message})
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", webhook_url,
             "-H", "Content-Type: application/json",
             "-d", payload, "--max-time", "15"],
            capture_output=True, text=True, timeout=20,
        )
        success = result.returncode == 0
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.error("Delivery failed: %s", e)
        success = False

    # Log delivery
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO delivery_log (signal_id, channel, message, sent_at, ack_received) "
        "VALUES (?, 'telegram', ?, ?, ?)",
        (signal_id, message, now, int(success)),
    )
    conn.commit()

    if success:
        conn.execute(
            "UPDATE signals SET status = 'pending', delivered_at = ? WHERE signal_id = ?",
            (now, signal_id),
        )
        conn.commit()

    return success


# ---------------------------------------------------------------------------
# File-based delivery queue (for OpenClaw heartbeat pickup)
# ---------------------------------------------------------------------------

def queue_for_delivery(signal: GeneratedSignal, message: str):
    """Write signal to pending file for OpenClaw heartbeat pickup."""
    pending = json.loads(PENDING_SIGNALS_FILE.read_text()) if PENDING_SIGNALS_FILE.exists() else []
    pending.append({
        "signal_id": signal.signal_id,
        "message": message,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "delivered": False,
    })
    PENDING_SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_SIGNALS_FILE.write_text(json.dumps(pending, indent=2))


# ---------------------------------------------------------------------------
# Approval handler
# ---------------------------------------------------------------------------

def handle_approval(signal_id: str, action: str, conn: sqlite3.Connection) -> str:
    """Process A/R/I reply from Telegram. Returns response message."""
    now = datetime.now(timezone.utc).isoformat()
    action = action.strip().upper()

    if action == 'A':
        conn.execute(
            "UPDATE signals SET status='approved' WHERE signal_id=?",
            (signal_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT market_id, market_question, kelly_usdc, direction "
            "FROM signals WHERE signal_id=?",
            (signal_id,),
        ).fetchone()
        if row:
            return (f"Approved SIG-{signal_id}.\n"
                    f"Execute: {row[1]}\n"
                    f"Size: ${row[2]:.0f} {row[3]}\n"
                    f"https://polymarket.com/event/{row[0]}")
        return f"Approved SIG-{signal_id}."

    elif action == 'R':
        conn.execute(
            "UPDATE signals SET status='rejected' WHERE signal_id=?",
            (signal_id,),
        )
        conn.commit()
        return f"Rejected SIG-{signal_id}."

    elif action == 'I':
        row = conn.execute(
            "SELECT e.objective_kernel, e.consensus_facts, e.contested_claims "
            "FROM signals s JOIN extractions e ON s.cluster_id = e.cluster_id "
            "WHERE s.signal_id=? ORDER BY e.extracted_at DESC LIMIT 1",
            (signal_id,),
        ).fetchone()
        if row:
            return (f"Details for SIG-{signal_id}:\n\n"
                    f"Kernel: {row[0]}\n"
                    f"Facts: {row[1]}\n"
                    f"Contested: {row[2]}")
        return f"No extraction data found for SIG-{signal_id}."

    return f"Unknown action '{action}'. Use A=Approve, R=Reject, I=Info."


# ---------------------------------------------------------------------------
# Dead letter queue
# ---------------------------------------------------------------------------

def dead_letter(conn: sqlite3.Connection, stage: str, payload: str, error: str):
    """Write a failed item to the dead letter queue."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO dead_letters (stage, payload, error, created_at) VALUES (?, ?, ?, ?)",
        (stage, payload, error, now),
    )
    conn.commit()
    logger.warning("Dead letter [%s]: %s", stage, error[:200])


# ---------------------------------------------------------------------------
# Signal persistence (SQLite)
# ---------------------------------------------------------------------------

def persist_signal(conn: sqlite3.Connection, signal: GeneratedSignal,
                   extraction_id: int | None = None):
    """Write a GeneratedSignal to the signals table."""
    conn.execute("""
        INSERT OR REPLACE INTO signals
            (signal_id, cluster_id, extraction_id, market_id, market_question,
             direction, current_price, suggested_probability, edge,
             kelly_fraction, kelly_usdc, strategy_code, confidence,
             yes_discount_applied, generated_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        signal.signal_id,
        signal.cluster_id,
        extraction_id,
        signal.market_id,
        signal.market_question,
        signal.direction,
        signal.current_price,
        signal.suggested_probability,
        signal.edge,
        signal.kelly_fraction,
        signal.kelly_usdc,
        signal.strategy_code,
        signal.confidence,
        int(signal.yes_discount_applied),
        signal.generated_at.isoformat(),
        signal.status,
    ))
    conn.commit()


def persist_extraction(conn: sqlite3.Connection,
                       result: TruthExtractionResult,
                       article_count: int) -> int:
    """Write a TruthExtractionResult to the extractions table. Returns extraction_id."""
    cursor = conn.execute("""
        INSERT INTO extractions
            (cluster_id, consensus_facts, contested_claims, motivated_omissions,
             objective_kernel, market_relevance, overall_confidence,
             requires_human_review, model_used, input_article_count, extracted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.cluster_id,
        json.dumps(result.consensus_facts),
        json.dumps(result.contested_claims),
        json.dumps(result.motivated_omissions),
        result.objective_kernel,
        json.dumps(result.market_relevance),
        result.overall_confidence,
        int(result.requires_human_review),
        result.model_used,
        article_count,
        result.extracted_at.isoformat(),
    ))
    conn.commit()
    return cursor.lastrowid


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """Main pipeline runner. Chains NB02-NB07 stages per tick."""

    def __init__(self, config: PipelineConfig, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self._shutdown = False

        # Initialize components
        self.conn = init_db()
        self.poller = BraveNewsPoller()
        self.tone_extractor = ToneEntityExtractor(
            use_llm=config.tone_use_llm, model=config.tone_model,
        )
        self.perspective_tagger = PerspectiveTagger()
        self.clusterer = EventClusterer()
        self.truth_extractor = TruthExtractor()
        self.signal_generator = SignalGenerator()
        self.circuit_breaker = CircuitBreaker(
            threshold=config.circuit_breaker_threshold,
            pause_minutes=config.circuit_breaker_pause_minutes,
        )

        # Poll scheduling
        self._last_poll: dict[str, float] = {}

        # Register signal handlers
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s — finishing current tick then exiting.", sig_name)
        self._shutdown = True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        """Main blocking loop. Polls queries on their intervals."""
        logger.info("Pipeline started. %d queries configured. dry_run=%s",
                     len(self.config.queries), self.dry_run)
        logger.info("Budget: %s", json.dumps(self.poller.budget.summary()))

        try:
            while not self._shutdown:
                self._run_due_queries()

                if self._shutdown:
                    break

                # Sleep in small intervals to allow shutdown check
                for _ in range(60):
                    if self._shutdown:
                        break
                    time.sleep(1)

        except Exception as e:
            logger.exception("Fatal pipeline error: %s", e)
        finally:
            self._cleanup()

    def run_once(self):
        """Single pass: tick all queries regardless of interval."""
        logger.info("Running single pass — all queries.")
        for query in self.config.queries:
            if self._shutdown:
                break
            try:
                self._tick(query)
            except Exception as e:
                logger.error("Tick failed for %s: %s", query.name, e)

        # Post-tick: expire stale clusters
        archived = self.clusterer.expire_stale(self.config.cluster_expiry_hours)
        if archived:
            logger.info("Archived %d stale clusters.", archived)

        self._cleanup()

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def _run_due_queries(self):
        """Check each query and tick if its interval has elapsed."""
        now = time.monotonic()

        for query in self.config.queries:
            if self._shutdown:
                break

            last = self._last_poll.get(query.name, 0)
            interval_sec = query.interval_minutes * 60

            if now - last < interval_sec and last > 0:
                continue

            try:
                self._tick(query)
                self._last_poll[query.name] = time.monotonic()
            except Exception as e:
                logger.error("Tick failed for %s: %s", query.name, e)
                dead_letter(self.conn, "tick", json.dumps({"query": query.name}), str(e))

        # Periodic cluster expiry (every pass)
        try:
            archived = self.clusterer.expire_stale(self.config.cluster_expiry_hours)
            if archived:
                logger.info("Archived %d stale clusters.", archived)
        except Exception as e:
            logger.warning("Cluster expiry failed: %s", e)

    # ------------------------------------------------------------------
    # Single tick (one query)
    # ------------------------------------------------------------------

    def _tick(self, query: QueryConfig):
        """Full pipeline tick for one query."""
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        logger.info("[%s] Tick: %s", ts, query.name)

        # --- Circuit breaker check ---
        if self.circuit_breaker.is_open:
            logger.warning("Circuit breaker open. %.0f min until reset.",
                           self.circuit_breaker.minutes_until_reset)
            return

        # --- Stage 1: Poll Brave ---
        try:
            new_articles = asyncio.run(self.poller.poll(query))
            self.circuit_breaker.record_success()
        except Exception as e:
            logger.error("Brave poll failed for %s: %s", query.name, e)
            self.circuit_breaker.record_failure()
            dead_letter(self.conn, "poll", json.dumps({"query": query.name}), str(e))
            return

        # Update poll state
        self._update_poll_state(query.name, len(new_articles))

        if not new_articles:
            logger.info("  0 new articles for %s", query.name)
            return

        logger.info("  %d new articles for %s", len(new_articles), query.name)

        if self.dry_run:
            for a in new_articles[:3]:
                logger.info("    [DRY] %s — %s", a.source_domain, a.title[:70])
            return

        # --- Stage 2-3: Tone & Entity Extraction ---
        try:
            self.tone_extractor.enrich(new_articles)
            logger.info("  Enriched: %s", self.tone_extractor.stats)
        except Exception as e:
            logger.error("Tone extraction failed: %s", e)
            dead_letter(self.conn, "tone", json.dumps({
                "query": query.name, "count": len(new_articles),
            }), str(e))
            # Continue with heuristic-enriched articles

        # --- Stage 4: Perspective Tagging ---
        try:
            self.perspective_tagger.tag_batch(new_articles)
        except Exception as e:
            logger.error("Perspective tagging failed: %s", e)

        # --- Persist articles ---
        self._persist_articles(new_articles)

        # --- Stage 5: Event Clustering ---
        try:
            existing = self.clusterer.load_clusters()
            clusters = self.clusterer.cluster(new_articles, existing)
            logger.info("  %d active clusters", len(clusters))
        except Exception as e:
            logger.error("Clustering failed: %s", e)
            dead_letter(self.conn, "clustering", json.dumps({
                "query": query.name,
            }), str(e))
            return

        # --- Stage 6-7: Extract + Generate (divergent clusters only) ---
        divergent = [c for c in clusters if c.is_divergent]
        if not divergent:
            logger.info("  No divergent clusters.")
            return

        logger.info("  %d divergent cluster(s) — processing.", len(divergent))

        for cluster in divergent:
            if self._shutdown:
                break
            self._process_divergent_cluster(cluster)

    # ------------------------------------------------------------------
    # Process divergent cluster: extract truth → generate signal → deliver
    # ------------------------------------------------------------------

    def _process_divergent_cluster(self, cluster: EventCluster):
        """Run truth extraction → signal generation → delivery for one cluster."""

        # --- Stage 6: Truth Extraction ---
        try:
            extraction = self.truth_extractor.extract(cluster)
        except Exception as e:
            logger.error("Truth extraction failed for %s: %s",
                         cluster.cluster_id, e)
            dead_letter(self.conn, "extraction", json.dumps({
                "cluster_id": cluster.cluster_id,
            }), str(e))
            return

        if extraction is None:
            return

        # Persist extraction
        try:
            extraction_id = persist_extraction(
                self.conn, extraction, len(cluster.articles),
            )
        except Exception as e:
            logger.warning("Failed to persist extraction: %s", e)
            extraction_id = None

        logger.info("  Extraction: cluster=%s conf=%.2f review=%s",
                     cluster.cluster_id, extraction.overall_confidence,
                     extraction.requires_human_review)

        if not extraction.market_relevance:
            logger.info("  No market relevance — skipping signal generation.")
            return

        # --- Stage 7: Signal Generation ---
        try:
            signals = self.signal_generator.generate(extraction, cluster)
        except Exception as e:
            logger.error("Signal generation failed: %s", e)
            dead_letter(self.conn, "signal", json.dumps({
                "cluster_id": cluster.cluster_id,
            }), str(e))
            return

        if not signals:
            logger.info("  No signals passed guardrails.")
            return

        # --- Stage 8: Deliver ---
        for sig in signals:
            # Persist
            try:
                persist_signal(self.conn, sig, extraction_id)
            except Exception as e:
                logger.warning("Failed to persist signal: %s", e)

            # Format message
            message = format_signal_message(sig, extraction, cluster)

            # Queue for file-based delivery (OpenClaw heartbeat pickup)
            try:
                queue_for_delivery(sig, message)
            except Exception as e:
                logger.warning("Failed to queue for file delivery: %s", e)

            # Deliver via webhook
            try:
                delivered = deliver_signal(
                    message, self.config.webhook_url, sig.signal_id, self.conn,
                )
                status = "delivered" if delivered else "pending (local)"
            except Exception as e:
                logger.error("Delivery failed: %s", e)
                dead_letter(self.conn, "delivery", json.dumps({
                    "signal_id": sig.signal_id,
                }), str(e))
                status = "failed"

            logger.info("  SIGNAL %s: %s %s edge=%+.1f%% kelly=$%.0f [%s]",
                         sig.signal_id, sig.direction, sig.market_question[:40],
                         sig.edge * 100, sig.kelly_usdc, status)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _persist_articles(self, articles: list[Article]):
        """Write enriched articles to SQLite."""
        for a in articles:
            try:
                self.conn.execute("""
                    INSERT OR IGNORE INTO articles
                        (url_hash, url, title, description, extra_snippets,
                         source_name, source_domain, country_queried, age_raw,
                         published_at, fetched_at, query_name,
                         tone, entities, key_claim, lean, geo_cluster,
                         reliability, processed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    a.url_hash,
                    a.url,
                    a.title,
                    a.description,
                    json.dumps(a.extra_snippets),
                    a.source_name,
                    a.source_domain,
                    a.country_queried,
                    a.age_raw,
                    a.published_at.isoformat(),
                    a.fetched_at.isoformat(),
                    a.query_name,
                    a.tone,
                    json.dumps(a.entities) if a.entities else None,
                    a.key_claim,
                    a.lean,
                    a.geo_cluster,
                    a.reliability,
                ))
            except sqlite3.Error as e:
                logger.debug("Article persist error: %s", e)
        self.conn.commit()

    def _update_poll_state(self, query_name: str, new_count: int):
        """Update the poll_state table."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute("""
            INSERT INTO poll_state (query_name, last_poll_time, articles_seen, articles_new)
            VALUES (?, ?, 0, ?)
            ON CONFLICT(query_name) DO UPDATE SET
                last_poll_time = excluded.last_poll_time,
                articles_seen = articles_seen + excluded.articles_new,
                articles_new = excluded.articles_new
        """, (query_name, now, new_count))
        self.conn.commit()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self):
        """Graceful shutdown: close DB connections."""
        logger.info("Pipeline shutting down.")
        try:
            self.poller.close()
        except Exception:
            pass
        try:
            self.clusterer.close()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def show_status():
    """Print pipeline status summary."""
    if not DB_PATH.exists():
        print("No pipeline database found.")
        return

    conn = sqlite3.connect(str(DB_PATH))

    print("=" * 60)
    print("NEWS INTELLIGENCE PIPELINE — Status")
    print("=" * 60)

    # Articles
    row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
    print(f"\nArticles:  {row[0]}")

    # Clusters
    row = conn.execute(
        "SELECT COUNT(*), SUM(is_divergent) FROM event_clusters WHERE status='active'"
    ).fetchone()
    print(f"Clusters:  {row[0] or 0} active ({row[1] or 0} divergent)")

    # Extractions
    row = conn.execute("SELECT COUNT(*) FROM extractions").fetchone()
    print(f"Extractions: {row[0]}")

    # Signals
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM signals GROUP BY status"
    ).fetchall()
    if rows:
        parts = [f"{r[0]}={r[1]}" for r in rows]
        print(f"Signals:   {', '.join(parts)}")
    else:
        print("Signals:   0")

    # Poll state
    print("\nPoll state:")
    rows = conn.execute(
        "SELECT query_name, last_poll_time, articles_seen, articles_new "
        "FROM poll_state ORDER BY query_name"
    ).fetchall()
    if rows:
        for r in rows:
            ts = r[1][:19] if r[1] else "never"
            print(f"  {r[0]:<20} last={ts}  total={r[2]}  last_new={r[3]}")
    else:
        print("  (no polls yet)")

    # Dead letters
    row = conn.execute("SELECT COUNT(*) FROM dead_letters").fetchone()
    if row[0]:
        print(f"\nDead letters: {row[0]}")
        recent = conn.execute(
            "SELECT stage, error, created_at FROM dead_letters "
            "ORDER BY id DESC LIMIT 3"
        ).fetchall()
        for r in recent:
            print(f"  [{r[0]}] {r[1][:60]}  ({r[2][:19]})")

    # Budget
    budget = BudgetTracker()
    s = budget.summary()
    print(f"\nBudget: {s['month_used']}/{s['month_limit']} this month "
          f"(${s['estimated_cost']:.2f})")

    conn.close()


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO", log_file: str | None = None):
    """Configure structured logging."""
    fmt = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file:
        log_path = PROJECT_ROOT / log_file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(
            str(log_path), maxBytes=10 * 1024 * 1024, backupCount=3,
        )
        fh.setFormatter(logging.Formatter(fmt, datefmt))
        handlers.append(fh)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="NB08: News Intelligence Pipeline")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                        help="Config YAML path")
    parser.add_argument("--once", action="store_true",
                        help="Run single pass then exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log actions without executing pipeline stages")
    parser.add_argument("--status", action="store_true",
                        help="Show pipeline status")
    parser.add_argument("--init-db", action="store_true",
                        help="Initialize database schema only")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.init_db:
        conn = init_db()
        print(f"Database initialized at {DB_PATH}")
        conn.close()
        return

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        print("Copy deploy/.env.example to .env and create config/news-pipeline.yaml")
        sys.exit(1)

    config = load_config(config_path)
    setup_logging(config.log_level, config.log_file)

    orchestrator = Orchestrator(config, dry_run=args.dry_run)

    if args.once:
        orchestrator.run_once()
    else:
        orchestrator.run()


if __name__ == "__main__":
    main()
