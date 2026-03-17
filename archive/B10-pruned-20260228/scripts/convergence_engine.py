#!/usr/bin/env python3
"""
Convergence Engine — combines news pipeline, whale, and fresh wallet signals
into unified high-conviction trading signals.

Usage:
    python3 convergence_engine.py                  # Check for convergent signals now
    python3 convergence_engine.py --continuous      # Poll every 15 min
    python3 convergence_engine.py --lookback 8      # Custom lookback hours (default: 4)
    python3 convergence_engine.py --report          # Full report across all recent signals
    python3 convergence_engine.py --json            # Machine-readable output
    python3 convergence_engine.py --dry-run         # Show data sources without scanning

Dependencies: stdlib only (json, sqlite3, datetime, os, sys, argparse, time, re, math)
Data sources:
    - News pipeline:    data/news-pipeline.db    (signals table)
    - Whale scanner:    data/whale-trades.db     (whale_trades table)
    - Fresh wallets:    data/fresh-wallet-anomalies.jsonl
    - Positions:        strategies/paper-trades/positions.json
"""

import argparse
import json
import math
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- Paths ---

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
POSITIONS_PATH = PROJECT_DIR / "strategies" / "paper-trades" / "positions.json"

# Data sources
NEWS_DB_PATH = DATA_DIR / "news-pipeline.db"
WHALE_DB_PATH = DATA_DIR / "whale-trades.db"
FRESH_WALLET_JSONL = DATA_DIR / "fresh-wallet-anomalies.jsonl"

# Output
CONVERGENCE_DB_PATH = DATA_DIR / "news-pipeline.db"  # write convergence signals here
CONVERGENCE_LOG = DATA_DIR / "convergence-signals.jsonl"
CONFLICT_LOG = DATA_DIR / "convergence-conflicts.jsonl"

# --- Configuration ---

DEFAULT_LOOKBACK_HOURS = 4
DEFAULT_BANKROLL = 10000
MIN_EDGE_THRESHOLD = 0.05  # 5pp minimum edge to trade
MIN_ANOMALY_SCORE = 4      # fresh wallet minimum anomaly score
MIN_WHALE_SCORE = 4        # whale minimum signal score

# Convergence level definitions
LEVEL_NAMES = {
    1: "News only",
    2: "News + Whale",
    3: "News + Fresh Wallet",
    4: "Whale + Fresh Wallet",
    5: "Triple Convergence",
}


# --- Data classes ---

@dataclass
class NewsSignal:
    signal_id: str
    market_question: str
    market_id: str | None
    direction: str           # YES | NO
    current_price: float
    suggested_probability: float
    edge: float
    confidence: float
    cluster_id: str | None
    generated_at: str

    @property
    def normalized_direction(self) -> str:
        return self.direction.upper()


@dataclass
class WhaleSignal:
    tx_hash: str
    wallet: str
    alias: str
    insider_score: float
    domain: str | None
    market_id: str | None
    market_question: str | None
    direction: str           # BUY | SELL (from scanner)
    size_usd: float
    entry_price: float | None
    signal_score: float
    in_domain: bool
    detected_at: str

    @property
    def normalized_direction(self) -> str:
        """Map BUY/SELL to YES/NO."""
        d = self.direction.upper()
        if d == "BUY":
            return "YES"
        elif d == "SELL":
            return "NO"
        return d  # already YES/NO


@dataclass
class FreshWalletSignal:
    wallet: str
    market_question: str
    domain: str | None
    direction: str           # YES | NO | UNKNOWN
    trade_size_usd: float
    entry_price: float | None
    anomaly_score: int
    wallet_age_days: int | None
    wallet_txn_count: int | None
    funding_source: str | None
    is_cluster: bool
    detected_at: str

    @property
    def normalized_direction(self) -> str:
        return self.direction.upper()


@dataclass
class ConvergenceSignal:
    signal_id: str
    market_question: str
    market_id: str | None
    direction: str                     # YES | NO
    convergence_level: int             # 1-5

    # Component signals
    news_signal: dict | None
    whale_signal: dict | None
    fresh_wallet_signal: dict | None

    # Derived
    combined_confidence: float         # 0-1
    suggested_sizing: str              # "paper-only" | "quarter-kelly" | "half-kelly"
    kelly_usd: float

    # Context
    our_position: dict | None
    agrees_with_position: bool | None

    generated_at: str
    status: str = "pending"            # pending | approved | rejected | executed
    conflict_detected: bool = False
    conflict_detail: str | None = None


# --- Data fetching ---

def fetch_news_signals(lookback_hours: int) -> list[NewsSignal]:
    """Fetch recent news pipeline signals from SQLite."""
    if not NEWS_DB_PATH.exists():
        print(f"  News DB not found: {NEWS_DB_PATH}", file=sys.stderr)
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    conn = sqlite3.connect(str(NEWS_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT signal_id, market_question, market_id, direction,
                   current_price, suggested_probability, edge, confidence,
                   cluster_id, generated_at
            FROM signals
            WHERE generated_at > ?
              AND status IN ('pending', 'approved')
              AND direction IS NOT NULL
            ORDER BY generated_at DESC
        """, (cutoff,)).fetchall()

        signals = []
        for r in rows:
            signals.append(NewsSignal(
                signal_id=r["signal_id"],
                market_question=r["market_question"] or "",
                market_id=r["market_id"],
                direction=r["direction"],
                current_price=r["current_price"] or 0,
                suggested_probability=r["suggested_probability"] or 0,
                edge=r["edge"] or 0,
                confidence=r["confidence"] or 0,
                cluster_id=r["cluster_id"],
                generated_at=r["generated_at"] or "",
            ))
        return signals
    finally:
        conn.close()


def fetch_whale_trades(lookback_hours: int) -> list[WhaleSignal]:
    """Fetch recent whale trades from SQLite."""
    if not WHALE_DB_PATH.exists():
        print(f"  Whale DB not found: {WHALE_DB_PATH}", file=sys.stderr)
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    conn = sqlite3.connect(str(WHALE_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT tx_hash, wallet, alias, insider_score, domain, market_id,
                   market_question, direction, size_usd, entry_price,
                   signal_score, in_domain, detected_at
            FROM whale_trades
            WHERE detected_at > ?
              AND signal_score >= ?
            ORDER BY detected_at DESC
        """, (cutoff, MIN_WHALE_SCORE)).fetchall()

        signals = []
        for r in rows:
            signals.append(WhaleSignal(
                tx_hash=r["tx_hash"],
                wallet=r["wallet"],
                alias=r["alias"] or "",
                insider_score=r["insider_score"] or 0,
                domain=r["domain"],
                market_id=r["market_id"],
                market_question=r["market_question"] or "",
                direction=r["direction"] or "",
                size_usd=r["size_usd"] or 0,
                entry_price=r["entry_price"],
                signal_score=r["signal_score"] or 0,
                in_domain=bool(r["in_domain"]),
                detected_at=r["detected_at"] or "",
            ))
        return signals
    finally:
        conn.close()


def fetch_fresh_wallet_anomalies(lookback_hours: int) -> list[FreshWalletSignal]:
    """Fetch recent fresh wallet anomalies from JSONL."""
    if not FRESH_WALLET_JSONL.exists():
        print(f"  Fresh wallet JSONL not found: {FRESH_WALLET_JSONL}", file=sys.stderr)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    signals = []

    with open(FRESH_WALLET_JSONL) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Parse detected_at
            detected_str = rec.get("detected_at", "")
            try:
                detected_dt = datetime.fromisoformat(detected_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            if detected_dt < cutoff:
                continue

            score = rec.get("anomaly_score", 0)
            if score < MIN_ANOMALY_SCORE:
                continue

            direction = rec.get("direction", "UNKNOWN")
            if direction == "UNKNOWN":
                continue  # can't determine convergence without direction

            status = rec.get("status", "monitoring")
            if status == "false_positive":
                continue

            signals.append(FreshWalletSignal(
                wallet=rec.get("wallet", ""),
                market_question=rec.get("market_question", ""),
                domain=rec.get("domain"),
                direction=direction,
                trade_size_usd=rec.get("trade_size_usd", 0),
                entry_price=rec.get("entry_price"),
                anomaly_score=score,
                wallet_age_days=rec.get("wallet_age_days"),
                wallet_txn_count=rec.get("wallet_txn_count"),
                funding_source=rec.get("funding_source"),
                is_cluster=bool(rec.get("is_cluster", False)),
                detected_at=detected_str,
            ))

    return signals


def load_positions() -> list[dict]:
    """Load open positions from positions.json."""
    if not POSITIONS_PATH.exists():
        return []
    try:
        data = json.loads(POSITIONS_PATH.read_text())
        return [p for p in data.get("positions", []) if p.get("status") == "open"]
    except (json.JSONDecodeError, Exception):
        return []


def load_bankroll() -> float:
    """Load current bankroll from positions.json."""
    if not POSITIONS_PATH.exists():
        return DEFAULT_BANKROLL
    try:
        data = json.loads(POSITIONS_PATH.read_text())
        return data.get("bankroll", DEFAULT_BANKROLL)
    except (json.JSONDecodeError, Exception):
        return DEFAULT_BANKROLL


# --- Market matching ---

def tokenize(text: str) -> set[str]:
    """Extract meaningful tokens from a market question."""
    text = text.lower()
    # Remove common stop words and punctuation
    text = re.sub(r'[^\w\s]', ' ', text)
    stop_words = {
        'will', 'the', 'be', 'a', 'an', 'by', 'in', 'on', 'of', 'to',
        'is', 'at', 'or', 'and', 'for', 'this', 'that', 'with', 'from',
        'has', 'have', 'had', 'do', 'does', 'did', 'not', 'no', 'yes',
        'than', 'more', 'less', 'above', 'below', 'between', 'after',
        'before', 'next', 'end', 'greater',
    }
    tokens = set(text.split()) - stop_words
    # Remove single-char tokens and pure numbers (unless they look like years)
    tokens = {t for t in tokens if len(t) > 1 and (not t.isdigit() or len(t) == 4)}
    return tokens


def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard similarity coefficient between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def fuzzy_market_match(question_a: str, question_b: str, threshold: float = 0.5) -> bool:
    """
    Determine if two market question strings refer to the same market.
    Uses Jaccard similarity on keyword tokens.
    """
    if not question_a or not question_b:
        return False

    # Exact match (fast path)
    if question_a.strip().lower() == question_b.strip().lower():
        return True

    tokens_a = tokenize(question_a)
    tokens_b = tokenize(question_b)

    similarity = jaccard_similarity(tokens_a, tokens_b)
    return similarity >= threshold


def extract_market_key(question: str) -> str:
    """
    Normalize a market question into a grouping key.
    Strips common prefixes and normalizes whitespace.
    """
    q = question.strip().lower()
    # Remove "will " prefix if present
    if q.startswith("will "):
        q = q[5:]
    q = re.sub(r'\s+', ' ', q)
    return q


def group_signals_by_market(
    news_signals: list[NewsSignal],
    whale_signals: list[WhaleSignal],
    fresh_signals: list[FreshWalletSignal],
) -> dict[str, dict]:
    """
    Group signals from all three sources by market.

    Returns dict keyed by market_question, with values:
    {
        "market_question": str,
        "market_id": str | None,
        "news": [NewsSignal, ...],
        "whale": [WhaleSignal, ...],
        "fresh": [FreshWalletSignal, ...],
    }
    """
    groups: dict[str, dict] = {}

    def find_or_create_group(question: str, market_id: str | None = None) -> str:
        """Find existing group matching this question, or create new one."""
        if not question:
            return ""

        # Try exact match first
        key = extract_market_key(question)
        if key in groups:
            return key

        # Try fuzzy match against existing groups
        for existing_key, group in groups.items():
            if fuzzy_market_match(question, group["market_question"]):
                return existing_key

        # Create new group
        groups[key] = {
            "market_question": question,
            "market_id": market_id,
            "news": [],
            "whale": [],
            "fresh": [],
        }
        return key

    # Add news signals
    for sig in news_signals:
        key = find_or_create_group(sig.market_question, sig.market_id)
        if key:
            groups[key]["news"].append(sig)
            if sig.market_id and not groups[key]["market_id"]:
                groups[key]["market_id"] = sig.market_id

    # Add whale signals
    for sig in whale_signals:
        key = find_or_create_group(sig.market_question or "", sig.market_id)
        if key:
            groups[key]["whale"].append(sig)

    # Add fresh wallet signals
    for sig in fresh_signals:
        key = find_or_create_group(sig.market_question or "")
        if key:
            groups[key]["fresh"].append(sig)

    return groups


# --- Convergence calculation ---

def determine_convergence_level(has_news: bool, has_whale: bool, has_fresh: bool) -> int:
    """
    Determine convergence level 1-5.

    Level 1: News only
    Level 2: News + Whale
    Level 3: News + Fresh Wallet
    Level 4: Whale + Fresh Wallet (no news)
    Level 5: All three (triple convergence)
    """
    count = sum([has_news, has_whale, has_fresh])

    if count <= 0:
        return 0

    if count == 1:
        return 1  # Single source

    if count == 3:
        return 5  # Triple convergence

    # Two sources
    if has_whale and has_fresh:
        return 4  # Whale + Fresh (highest two-signal level)
    elif has_news and has_fresh:
        return 3  # News + Fresh
    elif has_news and has_whale:
        return 2  # News + Whale
    else:
        return 1  # Shouldn't reach here


def compute_convergence_confidence(
    news: NewsSignal | None,
    whale: WhaleSignal | None,
    fresh: FreshWalletSignal | None,
) -> float:
    """
    Combine independent signal confidences using:
    P(correct) = 1 - (1 - p_news) * (1 - p_whale) * (1 - p_fresh)

    Where:
    - p_news = news.confidence * 0.7 (news alone is moderate)
    - p_whale = min(insider_edge, 0.5) * in_domain_weight
    - p_fresh = (anomaly_score / 10) * 0.5 (unknown quality)
    """
    components = []

    if news:
        p_news = news.confidence * 0.7
        components.append(min(p_news, 0.95))

    if whale:
        in_domain_mult = 1.0 if whale.in_domain else 0.3
        insider_edge = whale.insider_score / 10.0  # normalize 0-10 → 0-1
        p_whale = min(insider_edge, 0.5) * in_domain_mult
        components.append(min(p_whale, 0.95))

    if fresh:
        p_fresh = (fresh.anomaly_score / 10.0) * 0.5
        components.append(min(p_fresh, 0.95))

    if not components:
        return 0.0

    # Combined: 1 - product of (1 - p_i)
    combined = 1.0
    for p in components:
        combined *= (1 - p)

    return round(1.0 - combined, 4)


def compute_sizing(
    convergence_level: int,
    combined_confidence: float,
    current_price: float,
    direction: str,
    bankroll: float,
) -> tuple[str, float]:
    """
    Position sizing based on convergence level.

    Returns (sizing_label, kelly_usd).

    Rules:
    - Level 1: Paper trade only
    - Level 2-3: Quarter-Kelly
    - Level 4-5: Half-Kelly
    - Always capped at 3% bankroll (C1 rule)
    """
    # Edge calculation
    if direction == "YES":
        edge = combined_confidence - current_price
    else:
        edge = (1 - combined_confidence) - (1 - current_price)
        # Simplified: edge = current_price - combined_confidence for NO

    if edge < MIN_EDGE_THRESHOLD:
        return ("no-edge", 0.0)

    if convergence_level <= 1:
        return ("paper-only", 0.0)
    elif convergence_level <= 3:
        kelly_fraction = 0.25
        label = "quarter-kelly"
    else:
        kelly_fraction = 0.50
        label = "half-kelly"

    # Full Kelly = edge / odds
    if direction == "YES":
        odds = (1 / current_price) - 1 if current_price > 0 else 0
    else:
        odds = (1 / (1 - current_price)) - 1 if current_price < 1 else 0

    if odds <= 0:
        return (label, 0.0)

    full_kelly = edge / odds
    sized = full_kelly * kelly_fraction * bankroll

    # C1 cap: max 3% of bankroll per event
    c1_cap = bankroll * 0.03
    sized = min(sized, c1_cap)
    sized = max(sized, 0)

    return (label, round(sized, 2))


# --- Portfolio matching ---

def find_matching_position(market_question: str, positions: list[dict]) -> dict | None:
    """Find an existing position matching this market question."""
    for pos in positions:
        pos_market = pos.get("market", "")
        if fuzzy_market_match(market_question, pos_market, threshold=0.4):
            return pos
    return None


def check_position_agreement(position: dict | None, direction: str) -> bool | None:
    """Check if a convergence signal agrees with our existing position."""
    if not position:
        return None

    pos_direction = position.get("direction", "").upper()
    return pos_direction == direction.upper()


# --- Direction analysis ---

def get_majority_direction(
    news_signals: list[NewsSignal],
    whale_signals: list[WhaleSignal],
    fresh_signals: list[FreshWalletSignal],
) -> tuple[str | None, bool]:
    """
    Determine majority direction across all signal sources.

    Returns (direction, has_conflict).
    direction is None if no clear signal.
    has_conflict is True if sources disagree.
    """
    source_directions: dict[str, set[str]] = {
        "news": set(),
        "whale": set(),
        "fresh": set(),
    }

    for sig in news_signals:
        source_directions["news"].add(sig.normalized_direction)
    for sig in whale_signals:
        source_directions["whale"].add(sig.normalized_direction)
    for sig in fresh_signals:
        d = sig.normalized_direction
        if d in ("YES", "NO"):
            source_directions["fresh"].add(d)

    # Collect per-source directions (pick majority within each source)
    resolved: dict[str, str] = {}
    for source, dirs in source_directions.items():
        dirs_filtered = dirs - {"UNKNOWN"}
        if len(dirs_filtered) == 1:
            resolved[source] = dirs_filtered.pop()
        elif len(dirs_filtered) > 1:
            # Mixed within a source — ambiguous, take nothing
            pass

    if not resolved:
        return (None, False)

    unique_directions = set(resolved.values())

    if len(unique_directions) == 1:
        return (unique_directions.pop(), False)
    else:
        # Conflict: sources disagree
        # Return majority vote
        yes_count = sum(1 for d in resolved.values() if d == "YES")
        no_count = sum(1 for d in resolved.values() if d == "NO")
        majority = "YES" if yes_count > no_count else "NO"
        return (majority, True)


# --- Signal generation ---

def build_convergence_signal(
    market_question: str,
    market_id: str | None,
    news_signals: list[NewsSignal],
    whale_signals: list[WhaleSignal],
    fresh_signals: list[FreshWalletSignal],
    positions: list[dict],
    bankroll: float,
) -> ConvergenceSignal | None:
    """Build a ConvergenceSignal from grouped signals for a single market."""

    has_news = len(news_signals) > 0
    has_whale = len(whale_signals) > 0
    has_fresh = len(fresh_signals) > 0

    n_sources = sum([has_news, has_whale, has_fresh])
    if n_sources < 2:
        return None  # Need at least 2 signal sources for convergence

    # Determine direction and check for conflicts
    direction, has_conflict = get_majority_direction(
        news_signals, whale_signals, fresh_signals)

    if direction is None:
        return None

    # Pick best signal from each source
    best_news = max(news_signals, key=lambda s: s.confidence) if news_signals else None
    best_whale = max(whale_signals, key=lambda s: s.signal_score) if whale_signals else None
    best_fresh = max(fresh_signals, key=lambda s: s.anomaly_score) if fresh_signals else None

    # Convergence level
    level = determine_convergence_level(has_news, has_whale, has_fresh)

    # Confidence
    confidence = compute_convergence_confidence(best_news, best_whale, best_fresh)

    # Current price (from news signal if available, else estimate)
    current_price = 0.5  # default
    if best_news and best_news.current_price:
        current_price = best_news.current_price
    elif best_whale and best_whale.entry_price:
        current_price = best_whale.entry_price
    elif best_fresh and best_fresh.entry_price:
        current_price = best_fresh.entry_price

    # Sizing
    sizing_label, kelly_usd = compute_sizing(
        level, confidence, current_price, direction, bankroll)

    # Portfolio check
    position = find_matching_position(market_question, positions)
    agrees = check_position_agreement(position, direction)

    # Signal ID
    ts_suffix = datetime.now(timezone.utc).strftime("%H%M%S")
    sig_id = f"CV-{hash(market_question) % 100000:05d}-{ts_suffix}"

    # Build component signal dicts
    news_dict = None
    if best_news:
        news_dict = {
            "signal_id": best_news.signal_id,
            "confidence": best_news.confidence,
            "edge": best_news.edge,
            "direction": best_news.normalized_direction,
            "suggested_probability": best_news.suggested_probability,
        }

    whale_dict = None
    if best_whale:
        whale_dict = {
            "alias": best_whale.alias,
            "wallet": best_whale.wallet,
            "insider_score": best_whale.insider_score,
            "domain": best_whale.domain,
            "direction": best_whale.normalized_direction,
            "size_usd": best_whale.size_usd,
            "signal_score": best_whale.signal_score,
            "in_domain": best_whale.in_domain,
        }

    fresh_dict = None
    if best_fresh:
        fresh_dict = {
            "wallet": best_fresh.wallet,
            "direction": best_fresh.normalized_direction,
            "anomaly_score": best_fresh.anomaly_score,
            "trade_size_usd": best_fresh.trade_size_usd,
            "wallet_age_days": best_fresh.wallet_age_days,
            "wallet_txn_count": best_fresh.wallet_txn_count,
            "funding_source": best_fresh.funding_source,
            "is_cluster": best_fresh.is_cluster,
        }

    # Conflict detail
    conflict_detail = None
    if has_conflict:
        parts = []
        if best_news:
            parts.append(f"NEWS says {best_news.normalized_direction} (conf {best_news.confidence:.2f})")
        if best_whale:
            parts.append(f"WHALE ({best_whale.alias}) says {best_whale.normalized_direction} (${best_whale.size_usd:,.0f})")
        if best_fresh:
            parts.append(f"FRESH says {best_fresh.normalized_direction} (score {best_fresh.anomaly_score}/10)")
        conflict_detail = " vs ".join(parts)

    return ConvergenceSignal(
        signal_id=sig_id,
        market_question=market_question,
        market_id=market_id,
        direction=direction,
        convergence_level=level,
        news_signal=news_dict,
        whale_signal=whale_dict,
        fresh_wallet_signal=fresh_dict,
        combined_confidence=confidence,
        suggested_sizing=sizing_label if not has_conflict else "paper-only",
        kelly_usd=kelly_usd if not has_conflict else 0.0,
        our_position={
            "trade_id": position.get("trade_id"),
            "direction": position.get("direction"),
            "entry_price": position.get("entry_price"),
        } if position else None,
        agrees_with_position=agrees,
        generated_at=datetime.now(timezone.utc).isoformat(),
        conflict_detected=has_conflict,
        conflict_detail=conflict_detail,
    )


# --- Main scan ---

def scan_for_convergence(lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> list[ConvergenceSignal]:
    """
    Main convergence scan:
    1. Fetch recent news signals
    2. Fetch recent whale trades
    3. Fetch recent fresh wallet anomalies
    4. Group by market (using fuzzy matching)
    5. For each market with 2+ signal types: compute convergence
    6. Return ConvergenceSignals for level >= 2
    """
    # Fetch from all sources
    news = fetch_news_signals(lookback_hours)
    whales = fetch_whale_trades(lookback_hours)
    fresh = fetch_fresh_wallet_anomalies(lookback_hours)

    print(f"  Sources: {len(news)} news, {len(whales)} whale, {len(fresh)} fresh wallet signals",
          file=sys.stderr)

    if not news and not whales and not fresh:
        return []

    # Load portfolio context
    positions = load_positions()
    bankroll = load_bankroll()

    # Group by market
    groups = group_signals_by_market(news, whales, fresh)
    print(f"  Grouped into {len(groups)} distinct markets", file=sys.stderr)

    # Build convergence signals
    convergent = []
    for key, group in groups.items():
        signal = build_convergence_signal(
            market_question=group["market_question"],
            market_id=group["market_id"],
            news_signals=group["news"],
            whale_signals=group["whale"],
            fresh_signals=group["fresh"],
            positions=positions,
            bankroll=bankroll,
        )
        if signal:
            convergent.append(signal)

    # Sort by convergence level (highest first), then confidence
    convergent.sort(key=lambda s: (s.convergence_level, s.combined_confidence), reverse=True)

    return convergent


# --- Persistence ---

def init_convergence_table(db_path: Path = CONVERGENCE_DB_PATH):
    """Create convergence_signals table if not exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS convergence_signals (
            signal_id           TEXT PRIMARY KEY,
            market_question     TEXT NOT NULL,
            market_id           TEXT,
            direction           TEXT CHECK(direction IN ('YES', 'NO')),
            convergence_level   INTEGER CHECK(convergence_level BETWEEN 1 AND 5),

            -- Component signals (JSON)
            news_signal         TEXT,
            whale_signal        TEXT,
            fresh_wallet_signal TEXT,

            -- Combined
            combined_confidence REAL,
            suggested_sizing    TEXT,
            kelly_usd           REAL,

            -- Context
            our_position        TEXT,
            agrees_with_position INTEGER,

            generated_at        TEXT NOT NULL,
            status              TEXT DEFAULT 'pending'
                                CHECK(status IN ('pending', 'approved', 'rejected', 'executed', 'expired')),
            conflict_detected   INTEGER DEFAULT 0,
            conflict_detail     TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_convergence_level ON convergence_signals(convergence_level)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_convergence_status ON convergence_signals(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_convergence_generated ON convergence_signals(generated_at)")
    conn.commit()
    return conn


def persist_signal(conn: sqlite3.Connection, signal: ConvergenceSignal):
    """Write a convergence signal to SQLite."""
    conn.execute("""
        INSERT OR REPLACE INTO convergence_signals
        (signal_id, market_question, market_id, direction, convergence_level,
         news_signal, whale_signal, fresh_wallet_signal,
         combined_confidence, suggested_sizing, kelly_usd,
         our_position, agrees_with_position,
         generated_at, status, conflict_detected, conflict_detail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        signal.signal_id,
        signal.market_question,
        signal.market_id,
        signal.direction,
        signal.convergence_level,
        json.dumps(signal.news_signal) if signal.news_signal else None,
        json.dumps(signal.whale_signal) if signal.whale_signal else None,
        json.dumps(signal.fresh_wallet_signal) if signal.fresh_wallet_signal else None,
        signal.combined_confidence,
        signal.suggested_sizing,
        signal.kelly_usd,
        json.dumps(signal.our_position) if signal.our_position else None,
        1 if signal.agrees_with_position else (0 if signal.agrees_with_position is False else None),
        signal.generated_at,
        signal.status,
        1 if signal.conflict_detected else 0,
        signal.conflict_detail,
    ))
    conn.commit()


def append_to_jsonl(signal: ConvergenceSignal, path: Path):
    """Append signal to JSONL log."""
    record = {
        "signal_id": signal.signal_id,
        "market_question": signal.market_question,
        "direction": signal.direction,
        "convergence_level": signal.convergence_level,
        "combined_confidence": signal.combined_confidence,
        "suggested_sizing": signal.suggested_sizing,
        "kelly_usd": signal.kelly_usd,
        "conflict_detected": signal.conflict_detected,
        "generated_at": signal.generated_at,
    }
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


# --- Alert formatting ---

def format_convergence_alert(signal: ConvergenceSignal) -> str:
    """Format a convergence signal as a human-readable alert."""
    lines = []

    if signal.conflict_detected:
        lines.append(f"!! SIGNAL CONFLICT -- {signal.market_question}")
    else:
        lines.append(
            f"CONVERGENCE SIGNAL [Level {signal.convergence_level}/5] -- {signal.signal_id}")

    lines.append("")
    lines.append(f"Market: {signal.market_question}")
    lines.append(f"Direction: {signal.direction} | Combined confidence: {signal.combined_confidence:.0%}")
    lines.append("")

    # News component
    if signal.news_signal:
        ns = signal.news_signal
        lines.append(f"  NEWS: Confidence {ns['confidence']:.2f}, Edge {ns['edge']:+.2f}")
        lines.append(f"    Direction: {ns['direction']} | Suggested prob: {ns['suggested_probability']:.2f}")
        lines.append("")

    # Whale component
    if signal.whale_signal:
        ws = signal.whale_signal
        domain_marker = "YES" if ws["in_domain"] else "NO"
        lines.append(
            f"  WHALE: {ws['alias']} [{ws['insider_score']:.0f}/10 insider"
            f"{', ' + ws['domain'] + ' specialist' if ws['domain'] else ''}]")
        lines.append(f"    {ws['direction']} ${ws['size_usd']:,.0f}")
        lines.append(f"    In-domain: {domain_marker} | Signal score: {ws['signal_score']:.0f}/10")
        lines.append("")

    # Fresh wallet component
    if signal.fresh_wallet_signal:
        fw = signal.fresh_wallet_signal
        lines.append(f"  FRESH WALLET: {fw['wallet'][:10]}... [Score {fw['anomaly_score']}/10]")
        age_str = f"{fw['wallet_age_days']}d old" if fw['wallet_age_days'] is not None else "age unknown"
        txn_str = f"{fw['wallet_txn_count']} txns" if fw['wallet_txn_count'] is not None else ""
        lines.append(f"    {fw['direction']} ${fw['trade_size_usd']:,.0f} | {age_str}, {txn_str}")
        if fw.get("funding_source"):
            lines.append(f"    Funded from: {fw['funding_source']}")
        if fw.get("is_cluster"):
            lines.append("    Part of fresh wallet CLUSTER")
        lines.append("")

    # Sizing
    if signal.conflict_detected:
        lines.append(f"Conflict: {signal.conflict_detail}")
        lines.append("Action: DO NOT TRADE. Monitor closely.")
    else:
        lines.append(f"Sizing: {signal.suggested_sizing} = ${signal.kelly_usd:,.0f}")

    # Portfolio context
    if signal.our_position:
        pos = signal.our_position
        agree_marker = "AGREES" if signal.agrees_with_position else "CONTRADICTS"
        lines.append(
            f"Our position: {pos['trade_id']} {pos['direction']} @ {pos['entry_price']}"
            f" -- {agree_marker}")

        if signal.agrees_with_position and not signal.conflict_detected:
            lines.append(f"Action: Consider adding ${signal.kelly_usd:,.0f} to {pos['trade_id']}")
        elif not signal.agrees_with_position:
            lines.append("Action: ALERT -- signal contradicts our position")
    elif not signal.conflict_detected and signal.kelly_usd > 0:
        lines.append(f"Action: New position ${signal.kelly_usd:,.0f} {signal.direction}")

    lines.append("")

    return "\n".join(lines)


def format_conflict_alert(signal: ConvergenceSignal) -> str:
    """Format a conflict alert."""
    return format_convergence_alert(signal)  # Same format, conflict flag changes content


# --- Output ---

def print_dashboard(signals: list[ConvergenceSignal], scan_time: str):
    """Print human-readable dashboard."""
    print(f"\n{'=' * 70}")
    print(f"  CONVERGENCE ENGINE -- {scan_time}")
    print(f"  Signals: {len(signals)} convergent markets detected")
    print(f"{'=' * 70}\n")

    if not signals:
        print("  No convergent signals detected.\n")
        return

    # Separate convergent from conflicting
    convergent = [s for s in signals if not s.conflict_detected]
    conflicts = [s for s in signals if s.conflict_detected]

    if convergent:
        print(f"  CONVERGENT SIGNALS ({len(convergent)}):\n")
        for sig in convergent:
            print(format_convergence_alert(sig))
            print(f"  {'- ' * 35}\n")

    if conflicts:
        print(f"  SIGNAL CONFLICTS ({len(conflicts)}):\n")
        for sig in conflicts:
            print(format_conflict_alert(sig))
            print(f"  {'- ' * 35}\n")

    print(f"{'=' * 70}\n")


def print_json_output(signals: list[ConvergenceSignal]):
    """Print machine-readable JSON output."""
    output = []
    for sig in signals:
        output.append({
            "signal_id": sig.signal_id,
            "market_question": sig.market_question,
            "market_id": sig.market_id,
            "direction": sig.direction,
            "convergence_level": sig.convergence_level,
            "level_name": LEVEL_NAMES.get(sig.convergence_level, "Unknown"),
            "combined_confidence": sig.combined_confidence,
            "suggested_sizing": sig.suggested_sizing,
            "kelly_usd": sig.kelly_usd,
            "conflict_detected": sig.conflict_detected,
            "conflict_detail": sig.conflict_detail,
            "agrees_with_position": sig.agrees_with_position,
            "news_signal": sig.news_signal,
            "whale_signal": sig.whale_signal,
            "fresh_wallet_signal": sig.fresh_wallet_signal,
            "generated_at": sig.generated_at,
        })
    print(json.dumps(output, indent=2))


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Convergence Engine — combine news, whale, and fresh wallet signals")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK_HOURS,
                        help=f"Lookback window in hours (default: {DEFAULT_LOOKBACK_HOURS})")
    parser.add_argument("--continuous", action="store_true",
                        help="Run continuously, polling every --interval minutes")
    parser.add_argument("--interval", type=int, default=15,
                        help="Poll interval in minutes for continuous mode (default: 15)")
    parser.add_argument("--report", action="store_true",
                        help="Generate full report across all recent signals")
    parser.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show data source status without scanning")
    parser.add_argument("--no-db", action="store_true",
                        help="Skip SQLite persistence")
    args = parser.parse_args()

    if args.report:
        args.lookback = 24  # Full day for reports

    # Dry run — just check data sources
    if args.dry_run:
        print("\n[DRY RUN] Data source status:")
        print(f"  News DB:     {'EXISTS' if NEWS_DB_PATH.exists() else 'MISSING'} ({NEWS_DB_PATH})")
        print(f"  Whale DB:    {'EXISTS' if WHALE_DB_PATH.exists() else 'MISSING'} ({WHALE_DB_PATH})")
        print(f"  Fresh JSONL: {'EXISTS' if FRESH_WALLET_JSONL.exists() else 'MISSING'} ({FRESH_WALLET_JSONL})")
        print(f"  Positions:   {'EXISTS' if POSITIONS_PATH.exists() else 'MISSING'} ({POSITIONS_PATH})")
        print(f"  Bankroll:    ${load_bankroll():,.0f}")
        print(f"  Open positions: {len(load_positions())}")
        return

    # Initialize convergence table
    db_conn = None
    if not args.no_db:
        db_conn = init_convergence_table()

    if args.continuous:
        print(f"\nContinuous mode: polling every {args.interval} min (Ctrl+C to stop)\n",
              file=sys.stderr)
        cycle = 0
        try:
            while True:
                cycle += 1
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                print(f"\n--- Cycle {cycle} at {now} ---\n", file=sys.stderr)

                signals = scan_for_convergence(args.lookback)

                # Persist
                if db_conn:
                    for sig in signals:
                        persist_signal(db_conn, sig)

                for sig in signals:
                    log_path = CONFLICT_LOG if sig.conflict_detected else CONVERGENCE_LOG
                    append_to_jsonl(sig, log_path)

                # Output
                if args.json:
                    print_json_output(signals)
                else:
                    print_dashboard(signals, now)

                print(f"  Sleeping {args.interval} min...", file=sys.stderr)
                time.sleep(args.interval * 60)
        except KeyboardInterrupt:
            print("\nStopped.", file=sys.stderr)
    else:
        # Single scan
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"\nConvergence scan (lookback: {args.lookback}h)...\n", file=sys.stderr)

        signals = scan_for_convergence(args.lookback)

        # Persist
        if db_conn:
            for sig in signals:
                persist_signal(db_conn, sig)

        for sig in signals:
            log_path = CONFLICT_LOG if sig.conflict_detected else CONVERGENCE_LOG
            append_to_jsonl(sig, log_path)

        # Output
        if args.json:
            print_json_output(signals)
        else:
            print_dashboard(signals, now)

        # Summary
        convergent = [s for s in signals if not s.conflict_detected]
        conflicts = [s for s in signals if s.conflict_detected]
        print(f"Summary: {len(convergent)} convergent, {len(conflicts)} conflicts",
              file=sys.stderr)

    if db_conn:
        db_conn.close()


if __name__ == "__main__":
    main()
