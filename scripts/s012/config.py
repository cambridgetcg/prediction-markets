"""S012 shared configuration.

Canonical path constants, pipeline config, domain classification,
sports filtering, DB schema, and logging setup.

Individual modules define their own copies of paths/keywords inline
for standalone use.  This module provides the shared reference that
new code (and the orchestrator) can import.
"""

from __future__ import annotations

import os
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger("s012")

# ── Paths ────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # scripts/s012/ → scripts/ → project root
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
DATA_DIR = PROJECT_ROOT / "data" / "s012"
CONFIG_PATH = PROJECT_ROOT / "config" / "news-pipeline.yaml"

# ── Domain Keywords ──────────────────────────────────────────────────

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "GEO": [
        "iran", "strike", "war", "invasion", "ceasefire", "nato", "ukraine",
        "russia", "china", "taiwan", "israel", "lebanon", "khamenei",
        "regime", "leader out", "prime minister", "grenell", "venezuela",
        "greenland", "annex", "invade",
    ],
    "CRY": [
        "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp",
        "crypto", "token", "fdv", "launch", "dip to", "reach $",
    ],
    "POL": [
        "president", "nomination", "democrat", "republican", "trump",
        "election", "nominate", "congress", "senate", "governor",
        "fed chair", "speaker",
    ],
    "ECO": [
        "fed ", "interest rate", "bps", "gdp", "inflation", "cpi",
        "unemployment", "revenue", "treasury",
    ],
    "TEC": [
        "ai model", "anthropic", "openai", "google", "chatgpt", "claude",
        "gemini", "gpt",
    ],
    "ENV": [
        "earthquake", "hurricane", "snow", "temperature", "wildfire",
        "climate", "storm",
    ],
}

SPORTS_KEYWORDS: list[str] = [
    "nba", "nfl", "nhl", "mlb", "ipl", "premier league", "serie a",
    "la liga", "bundesliga", "champions league", "ufc", "atp", "wta",
    "formula 1", "nascar", "pga", "cricket", "rugby", "wnba", "mma",
    "copa", "super bowl", "ncaa", "world cup", "fifa", "bo3", "bo2",
    "bo1", "map 1", "map 2", "o/u", "total rounds", "handicap",
    "masters tournament", "counter-strike", "dota", "valorant",
    "league of legends", "cs2", "blast", "iem", "esl", "cct",
    "lck", "lpl", "lec", "up or down",
]


# ── Helpers ──────────────────────────────────────────────────────────

def classify_domain(text: str) -> str:
    """Classify text into a domain using keyword matching."""
    t = text.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in t:
                return domain
    return "OTHER"


def is_sports(text: str) -> bool:
    """Check if text is sports-related."""
    t = text.lower()
    return any(kw in t for kw in SPORTS_KEYWORDS)


def ensure_data_dirs() -> None:
    """Create data directories if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for S012 modules."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ── Query Config ─────────────────────────────────────────────────────

@dataclass
class QueryConfig:
    """Configuration for a single news query."""
    name: str
    keywords: list[str]
    boolean_mode: str = "OR"
    countries: list[str] = field(default_factory=lambda: ["US", "GB"])
    freshness: str = "pd"
    count_per_country: int = 15
    interval_minutes: int = 30
    extra_snippets: bool = True


# ── Pipeline Config ──────────────────────────────────────────────────

@dataclass
class S012Config:
    """Full S012 pipeline configuration."""

    # News
    brave_api_key: str = ""
    queries: list[QueryConfig] = field(default_factory=list)
    max_requests_per_month: int = 900
    daily_soft_limit: int = 50

    # Markets
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    market_cache_ttl_seconds: int = 300
    min_market_volume: float = 100_000
    snapshot_interval_seconds: int = 900

    # Interpretation
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    max_interpretations_per_hour: int = 20
    interpretation_cooldown_seconds: int = 3600

    # Reaction thresholds
    min_move_to_interpret: float = 0.03
    overreaction_threshold: float = 0.05
    geo_overreaction_threshold: float = 0.08
    min_confidence: float = 0.5

    # Sizing
    bankroll_usd: float = 10_000.0
    max_s012_exposure: float = 0.10
    overreaction_strong_size: float = 0.03
    overreaction_moderate_size: float = 0.015
    underreaction_strong_size: float = 0.02
    underreaction_moderate_size: float = 0.01

    # Scheduling
    poll_interval_seconds: int = 900
    circuit_breaker_threshold: int = 3
    circuit_breaker_pause_seconds: int = 1800

    # Delivery
    delivery_channel: str = "stdout"

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> S012Config:
        """Load config from YAML, merge with environment variables."""
        config = cls()

        yaml_path = path or CONFIG_PATH
        if yaml_path.exists() and yaml is not None:
            with open(yaml_path) as f:
                raw = yaml.safe_load(f)

            if raw:
                brave = raw.get("brave", {})
                config.max_requests_per_month = brave.get(
                    "max_requests_per_month", 900
                )
                config.daily_soft_limit = brave.get("daily_soft_limit", 50)

                for q in raw.get("queries", []):
                    config.queries.append(QueryConfig(
                        name=q["name"],
                        keywords=q.get("keywords", []),
                        boolean_mode=q.get("boolean_mode", "OR"),
                        countries=q.get("countries", ["US", "GB"]),
                        freshness=q.get("freshness", "pd"),
                        count_per_country=q.get("count_per_country", 15),
                        interval_minutes=q.get("interval_minutes", 30),
                        extra_snippets=q.get("extra_snippets", True),
                    ))

                pipeline = raw.get("pipeline", {})
                config.min_move_to_interpret = pipeline.get("min_edge", 0.05)
                config.min_confidence = pipeline.get("min_confidence", 0.6)
                config.max_interpretations_per_hour = pipeline.get(
                    "max_extractions_per_hour", 20
                )
                config.circuit_breaker_threshold = pipeline.get(
                    "circuit_breaker_threshold", 3
                )

                delivery = raw.get("delivery", {})
                config.delivery_channel = delivery.get("channel", "stdout")

        # Environment overrides
        config.brave_api_key = os.environ.get(
            "BRAVE_API_KEY", config.brave_api_key
        )
        config.anthropic_api_key = os.environ.get(
            "ANTHROPIC_API_KEY", config.anthropic_api_key
        )
        if os.environ.get("S012_BANKROLL"):
            config.bankroll_usd = float(os.environ["S012_BANKROLL"])
        if os.environ.get("S012_DELIVERY"):
            config.delivery_channel = os.environ["S012_DELIVERY"]
        if os.environ.get("S012_POLL_INTERVAL"):
            config.poll_interval_seconds = int(os.environ["S012_POLL_INTERVAL"])

        return config


# ── DB Schema ────────────────────────────────────────────────────────

def ensure_schema(db_path: Path = DB_PATH) -> None:
    """Create all S012 tables if they don't exist.

    Idempotent — safe to call on every startup.  Individual modules
    also create their own tables, so this is a convenience for fresh
    setups or migration scripts.
    """
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        -- Module 1: News Ingestor
        CREATE TABLE IF NOT EXISTS seen_urls (
            url TEXT PRIMARY KEY,
            first_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS news_events (
            event_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            domain TEXT,
            article_count INTEGER,
            avg_age_hours REAL,
            newest_article TEXT,
            entities TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS event_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            source TEXT,
            age TEXT,
            snippet TEXT,
            FOREIGN KEY (event_id) REFERENCES news_events(event_id)
        );

        -- Module 2: Market Snapshots
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            yes_price REAL NOT NULL,
            volume_24h REAL,
            liquidity REAL,
            snapshot_time TEXT NOT NULL,
            trigger_event_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_market
            ON market_snapshots(market_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_time
            ON market_snapshots(snapshot_time);

        -- Module 3: Interpretations
        CREATE TABLE IF NOT EXISTS s012_interpretations (
            interpretation_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            market_id TEXT NOT NULL,
            prior_probability REAL,
            posterior_probability REAL,
            estimated_shift REAL,
            confidence REAL,
            news_type TEXT,
            source_quality TEXT,
            reasoning TEXT,
            model_used TEXT,
            prompt_version TEXT,
            interpreted_at TEXT NOT NULL,
            raw_response TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_interp_event
            ON s012_interpretations(event_id);
        CREATE INDEX IF NOT EXISTS idx_interp_market
            ON s012_interpretations(market_id);

        -- Module 4: Assessments
        CREATE TABLE IF NOT EXISTS s012_assessments (
            assessment_id TEXT PRIMARY KEY,
            interpretation_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            market_id TEXT NOT NULL,
            estimated_shift REAL,
            actual_move REAL,
            reaction_delta REAL,
            reaction_type TEXT,
            delta_magnitude TEXT,
            is_actionable INTEGER,
            suggested_direction TEXT,
            suggested_entry REAL,
            suggested_target REAL,
            suggested_stop REAL,
            time_horizon_hours INTEGER,
            size_pct REAL,
            adjusted_confidence REAL,
            assessed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assess_actionable
            ON s012_assessments(is_actionable);

        -- Module 5: Signals
        CREATE TABLE IF NOT EXISTS s012_signals (
            signal_id TEXT PRIMARY KEY,
            assessment_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            market_id TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            time_horizon_hours INTEGER,
            size_usdc REAL,
            size_pct REAL,
            reaction_delta REAL,
            confidence REAL,
            passed_concentration INTEGER,
            passed_anti_patterns INTEGER,
            risk_notes TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        -- Module 6: Paper Trades
        CREATE TABLE IF NOT EXISTS s012_paper_trades (
            trade_id TEXT PRIMARY KEY,
            signal_id TEXT NOT NULL,
            market_id TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            entry_time TEXT NOT NULL,
            size_usdc REAL NOT NULL,
            shares REAL NOT NULL,
            target_price REAL,
            stop_price REAL,
            expiry_time TEXT,
            exit_price REAL,
            exit_time TEXT,
            exit_reason TEXT,
            pnl_usdc REAL,
            pnl_pct REAL,
            signal_type TEXT,
            domain TEXT,
            reaction_delta REAL,
            estimated_shift REAL,
            actual_move REAL,
            market_resolved INTEGER,
            llm_direction_correct INTEGER,
            reaction_call_correct INTEGER,
            status TEXT DEFAULT 'OPEN'
        );
    """)
    conn.close()
    logger.debug("S012 schema ensured at %s", db_path)
