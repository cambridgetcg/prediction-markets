-- NB08: News Intelligence Pipeline — Complete SQLite Schema
-- Created: 2026-02-27
-- Usage: sqlite3 data/news-pipeline.db < scripts/schema.sql

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- -----------------------------------------------------------------------
-- Stage 1-2: Articles (ingested from Brave, deduplicated)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS articles (
    url_hash        TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    extra_snippets  TEXT,           -- JSON array
    source_name     TEXT,
    source_domain   TEXT NOT NULL,
    country_queried TEXT NOT NULL,
    age_raw         TEXT,
    published_at    TEXT NOT NULL,
    fetched_at      TEXT NOT NULL,
    query_name      TEXT,
    -- NB03 enrichment
    tone            REAL,
    entities        TEXT,           -- JSON array
    key_claim       TEXT,
    -- NB04 perspective tagging
    lean            REAL,
    geo_cluster     TEXT,
    reliability     REAL,
    -- Processing state
    cluster_id      TEXT,
    processed       INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_articles_published   ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_fetched     ON articles(fetched_at);
CREATE INDEX IF NOT EXISTS idx_articles_cluster     ON articles(cluster_id);
CREATE INDEX IF NOT EXISTS idx_articles_domain      ON articles(source_domain);
CREATE INDEX IF NOT EXISTS idx_articles_processed   ON articles(processed);

-- -----------------------------------------------------------------------
-- Stage 1: Article-Country junction (cross-index dedup)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS article_countries (
    url_hash TEXT NOT NULL,
    country  TEXT NOT NULL,
    PRIMARY KEY (url_hash, country)
);

-- -----------------------------------------------------------------------
-- Stage 5: Event Clusters
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS event_clusters (
    cluster_id       TEXT PRIMARY KEY,
    event_summary    TEXT,
    domain           TEXT,
    key_entities     TEXT,           -- JSON array
    first_seen       TEXT NOT NULL,
    last_updated     TEXT NOT NULL,
    article_count    INTEGER DEFAULT 0,
    query_sources    TEXT,           -- JSON array
    divergence_score REAL DEFAULT 0.0,
    is_divergent     INTEGER DEFAULT 0,
    status           TEXT DEFAULT 'active' CHECK(status IN ('active', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_clusters_status    ON event_clusters(status);
CREATE INDEX IF NOT EXISTS idx_clusters_divergent ON event_clusters(is_divergent);
CREATE INDEX IF NOT EXISTS idx_clusters_updated   ON event_clusters(last_updated);

-- -----------------------------------------------------------------------
-- Stage 5: Cluster-Article junction
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cluster_articles (
    cluster_id TEXT NOT NULL,
    url_hash   TEXT NOT NULL,
    PRIMARY KEY (cluster_id, url_hash)
);

-- -----------------------------------------------------------------------
-- Stage 6: Truth Extractions
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extractions (
    extraction_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id          TEXT NOT NULL,
    consensus_facts     TEXT,        -- JSON array
    contested_claims    TEXT,        -- JSON array
    motivated_omissions TEXT,        -- JSON object
    objective_kernel    TEXT,
    market_relevance    TEXT,        -- JSON array
    overall_confidence  REAL,
    requires_human_review INTEGER DEFAULT 0,
    model_used          TEXT,
    input_article_count INTEGER,
    extracted_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_extractions_cluster ON extractions(cluster_id);
CREATE INDEX IF NOT EXISTS idx_extractions_time    ON extractions(extracted_at);

-- -----------------------------------------------------------------------
-- Stage 7: Generated Signals
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signals (
    signal_id           TEXT PRIMARY KEY,
    cluster_id          TEXT,
    extraction_id       INTEGER,
    market_id           TEXT,
    market_question     TEXT,
    direction           TEXT CHECK(direction IN ('YES', 'NO')),
    current_price       REAL,
    suggested_probability REAL,
    edge                REAL,
    kelly_fraction      REAL,
    kelly_usdc          REAL,
    strategy_code       TEXT,
    confidence          REAL,
    yes_discount_applied INTEGER DEFAULT 0,
    generated_at        TEXT NOT NULL,
    delivered_at        TEXT,
    status              TEXT DEFAULT 'pending'
                        CHECK(status IN ('pending', 'approved', 'rejected', 'executed', 'expired')),
    resolved_at         TEXT,
    outcome             TEXT           -- profit/loss after resolution
);

CREATE INDEX IF NOT EXISTS idx_signals_status  ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_cluster ON signals(cluster_id);
CREATE INDEX IF NOT EXISTS idx_signals_time    ON signals(generated_at);

-- -----------------------------------------------------------------------
-- Stage 9: Delivery Log
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS delivery_log (
    delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   TEXT NOT NULL,
    channel     TEXT NOT NULL,
    message     TEXT,
    sent_at     TEXT NOT NULL,
    ack_received INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_delivery_signal ON delivery_log(signal_id);

-- -----------------------------------------------------------------------
-- Orchestration: Poll State
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS poll_state (
    query_name        TEXT PRIMARY KEY,
    last_poll_time    TEXT,
    articles_seen     INTEGER DEFAULT 0,
    articles_new      INTEGER DEFAULT 0
);

-- -----------------------------------------------------------------------
-- Orchestration: Request Budget (daily tracking)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS request_budget (
    date           TEXT NOT NULL,
    request_count  INTEGER DEFAULT 0,
    cost_estimate  REAL DEFAULT 0.0,
    PRIMARY KEY (date)
);

-- -----------------------------------------------------------------------
-- Orchestration: Dead Letter Queue (failed stages)
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dead_letters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    stage       TEXT NOT NULL,         -- 'extraction', 'signal', 'delivery'
    payload     TEXT,                  -- JSON of failed item
    error       TEXT,
    created_at  TEXT NOT NULL,
    retried     INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_dead_letters_stage ON dead_letters(stage);

-- -----------------------------------------------------------------------
-- B9: Whale Activity Scanner — Insider trade tracking
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS whale_trades (
    tx_hash         TEXT PRIMARY KEY,
    wallet          TEXT NOT NULL,
    alias           TEXT,
    insider_score   REAL,
    domain          TEXT,
    market_id       TEXT,
    market_question TEXT,
    direction       TEXT,     -- BUY | SELL
    size_usd        REAL,
    entry_price     REAL,
    signal_score    REAL,
    in_domain       INTEGER,  -- 1 if in insider's dominant domain
    detected_at     TEXT NOT NULL,
    followed        INTEGER DEFAULT 0,  -- did we follow this trade?
    outcome         TEXT      -- profit/loss after resolution
);

CREATE INDEX IF NOT EXISTS idx_whale_domain ON whale_trades(domain);
CREATE INDEX IF NOT EXISTS idx_whale_score ON whale_trades(signal_score);
CREATE INDEX IF NOT EXISTS idx_whale_wallet ON whale_trades(wallet);

-- -----------------------------------------------------------------------
-- B9-02: Fresh Wallet Anomalies — unknown insider detection
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fresh_wallet_anomalies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet          TEXT NOT NULL,
    market_question TEXT,
    domain          TEXT,
    direction       TEXT,          -- YES | NO | UNKNOWN
    trade_size_usd  REAL,
    entry_price     REAL,
    market_volume   REAL,
    wallet_txn_count INTEGER,
    wallet_age_days  INTEGER,
    funding_source  TEXT,          -- exchange name or NULL
    anomaly_score   INTEGER,       -- 0-10
    catalyst_days   INTEGER,       -- days to nearest catalyst or NULL
    is_cluster      INTEGER DEFAULT 0,  -- part of 3+ wallet cluster
    cluster_id      TEXT,          -- links cluster members
    detected_at     TEXT NOT NULL,
    portfolio_action TEXT,         -- CONFIRMATION | CONTRADICTION | NEW_INTEL | MONITOR
    position_trade_id TEXT,        -- our position if any
    resolved_at     TEXT,          -- when the market resolved
    insider_correct INTEGER,       -- 1 if their bet was right
    status          TEXT DEFAULT 'monitoring'
                    CHECK(status IN ('monitoring', 'confirmed_insider', 'false_positive', 'resolved'))
);

CREATE INDEX IF NOT EXISTS idx_fwa_wallet ON fresh_wallet_anomalies(wallet);
CREATE INDEX IF NOT EXISTS idx_fwa_score ON fresh_wallet_anomalies(anomaly_score);
CREATE INDEX IF NOT EXISTS idx_fwa_domain ON fresh_wallet_anomalies(domain);
CREATE INDEX IF NOT EXISTS idx_fwa_status ON fresh_wallet_anomalies(status);
CREATE INDEX IF NOT EXISTS idx_fwa_cluster ON fresh_wallet_anomalies(cluster_id);
CREATE INDEX IF NOT EXISTS idx_fwa_detected ON fresh_wallet_anomalies(detected_at);

-- -----------------------------------------------------------------------
-- B9-03: Convergence Signals — combined news × whale × fresh wallet
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS convergence_signals (
    signal_id           TEXT PRIMARY KEY,
    market_question     TEXT NOT NULL,
    market_id           TEXT,
    direction           TEXT CHECK(direction IN ('YES', 'NO')),
    convergence_level   INTEGER CHECK(convergence_level BETWEEN 1 AND 5),

    -- Component signals (JSON)
    news_signal         TEXT,           -- JSON: signal_id, confidence, edge, direction
    whale_signal        TEXT,           -- JSON: alias, wallet, insider_score, domain, size_usd
    fresh_wallet_signal TEXT,           -- JSON: wallet, anomaly_score, trade_size_usd

    -- Combined
    combined_confidence REAL,
    suggested_sizing    TEXT,           -- "paper-only" | "quarter-kelly" | "half-kelly"
    kelly_usd           REAL,

    -- Context
    our_position        TEXT,           -- JSON: trade_id, direction, entry_price
    agrees_with_position INTEGER,       -- 0 | 1 | NULL

    generated_at        TEXT NOT NULL,
    status              TEXT DEFAULT 'pending'
                        CHECK(status IN ('pending', 'approved', 'rejected', 'executed', 'expired')),
    conflict_detected   INTEGER DEFAULT 0,
    conflict_detail     TEXT
);

CREATE INDEX IF NOT EXISTS idx_convergence_level ON convergence_signals(convergence_level);
CREATE INDEX IF NOT EXISTS idx_convergence_status ON convergence_signals(status);
CREATE INDEX IF NOT EXISTS idx_convergence_generated ON convergence_signals(generated_at);
