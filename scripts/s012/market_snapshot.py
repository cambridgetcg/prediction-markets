#!/usr/bin/env python3
"""S012 Module 2: Market Snapshot Cache — Polymarket price tracking & news-market matching.

Captures price snapshots, matches news events to relevant markets,
and tracks price movements over time via SQLite.

Usage:
    python3 scripts/s012/market_snapshot.py --scan              # Fetch and display active markets
    python3 scripts/s012/market_snapshot.py --match "Iran nuclear talks"
    python3 scripts/s012/market_snapshot.py --snapshot           # Snapshot watched markets
    python3 scripts/s012/market_snapshot.py --history <market_id> # Price history for a market
    python3 scripts/s012/market_snapshot.py --watchlist          # Show current watchlist
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx required. Install: pip3 install httpx")
    sys.exit(1)

# Import shared pieces from Module 1
from news_ingestor import NewsEvent, classify_domain, DOMAIN_KEYWORDS, extract_entities

logger = logging.getLogger(__name__)

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"

# --- Constants ---

GAMMA_BASE = "https://gamma-api.polymarket.com"
MARKET_CACHE_TTL = 300  # 5 minutes
MIN_VOLUME_WATCHLIST = 100_000  # $100K
MIN_HOURS_TO_RESOLUTION = 24
MAX_MATCHES_PER_EVENT = 5
MIN_RELEVANCE = 0.3

SPORTS_KEYWORDS = [
    'nba', 'nfl', 'nhl', 'mlb', 'ipl', 'premier league', 'serie a',
    'la liga', 'bundesliga', 'champions league', 'ufc', 'atp', 'wta',
    'formula 1', 'nascar', 'pga', 'cricket', 'rugby', 'wnba', 'mma',
    'copa', 'super bowl', 'ncaa', 'world cup', 'fifa', 'bo3', 'bo2',
    'bo1', 'map 1', 'map 2', 'o/u', 'total rounds', 'handicap',
    'masters tournament', 'counter-strike', 'dota', 'valorant',
    'league of legends', 'cs2', 'blast', 'iem', 'esl', 'cct',
    'lck', 'lpl', 'lec', 'up or down',
]


def is_sports(question: str) -> bool:
    """Check if a market is sports-related."""
    q = question.lower()
    return any(kw in q for kw in SPORTS_KEYWORDS)


# --- Dataclasses ---

@dataclass
class MarketSnapshot:
    market_id: str
    question: str
    slug: str
    yes_price: float
    no_price: float
    volume_24h: float
    volume_total: float
    liquidity: float
    end_date: str
    domain: str
    snapshot_time: datetime
    yes_token: str
    no_token: str


@dataclass
class MarketMatch:
    event: NewsEvent
    market: MarketSnapshot
    relevance_score: float        # 0.0-1.0
    price_before: float | None    # YES price before news (from cache)
    price_after: float            # YES price now
    actual_move: float | None     # price_after - price_before


# --- SQLite Snapshot Store ---

class SnapshotStore:
    """SQLite-backed price snapshot storage."""

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
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
        """)
        self.conn.commit()

    def save_snapshot(self, snap: MarketSnapshot, trigger_event_id: str | None = None):
        """Store a single price snapshot."""
        self.conn.execute(
            """INSERT INTO market_snapshots
                   (market_id, yes_price, volume_24h, liquidity, snapshot_time, trigger_event_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (snap.market_id, snap.yes_price, snap.volume_24h,
             snap.liquidity, snap.snapshot_time.isoformat(), trigger_event_id),
        )
        self.conn.commit()

    def save_snapshots(self, snaps: list[MarketSnapshot], trigger_event_id: str | None = None):
        """Store multiple snapshots in a single transaction."""
        rows = [
            (s.market_id, s.yes_price, s.volume_24h,
             s.liquidity, s.snapshot_time.isoformat(), trigger_event_id)
            for s in snaps
        ]
        self.conn.executemany(
            """INSERT INTO market_snapshots
                   (market_id, yes_price, volume_24h, liquidity, snapshot_time, trigger_event_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()

    def get_price_before(self, market_id: str, before: datetime) -> float | None:
        """Get the most recent YES price snapshot BEFORE the given timestamp."""
        row = self.conn.execute(
            """SELECT yes_price FROM market_snapshots
               WHERE market_id = ? AND snapshot_time < ?
               ORDER BY snapshot_time DESC LIMIT 1""",
            (market_id, before.isoformat()),
        ).fetchone()
        return row[0] if row else None

    def get_history(self, market_id: str, limit: int = 50) -> list[dict]:
        """Get recent snapshots for a market."""
        rows = self.conn.execute(
            """SELECT yes_price, volume_24h, liquidity, snapshot_time, trigger_event_id
               FROM market_snapshots
               WHERE market_id = ?
               ORDER BY snapshot_time DESC LIMIT ?""",
            (market_id, limit),
        ).fetchall()
        return [
            {
                "yes_price": r[0],
                "volume_24h": r[1],
                "liquidity": r[2],
                "snapshot_time": r[3],
                "trigger_event_id": r[4],
            }
            for r in rows
        ]

    def close(self):
        self.conn.close()


# --- Market Cache ---

class MarketCache:
    """In-memory cache of active Polymarket markets with TTL-based refresh."""

    def __init__(self):
        self._markets: list[MarketSnapshot] = []
        self._by_id: dict[str, MarketSnapshot] = {}
        self._last_fetch: float = 0.0

    @property
    def stale(self) -> bool:
        return (time.monotonic() - self._last_fetch) > MARKET_CACHE_TTL

    @property
    def markets(self) -> list[MarketSnapshot]:
        return self._markets

    def get(self, market_id: str) -> MarketSnapshot | None:
        return self._by_id.get(market_id)

    def refresh(self) -> int:
        """Fetch active markets from Gamma API. Returns count fetched."""
        raw = _fetch_raw_markets()
        parsed = []
        for m in raw:
            snap = _parse_market(m)
            if snap is not None:
                parsed.append(snap)

        self._markets = parsed
        self._by_id = {s.market_id: s for s in parsed}
        self._last_fetch = time.monotonic()
        return len(parsed)

    def ensure_fresh(self) -> int:
        """Refresh only if cache is stale. Returns count (0 if cache hit)."""
        if self.stale:
            return self.refresh()
        return 0


# --- Gamma API ---

def _fetch_raw_markets() -> list[dict]:
    """Fetch active markets from Gamma API (up to 400)."""
    all_markets: list[dict] = []
    headers = {"User-Agent": "prediction-markets/s012"}
    with httpx.Client(timeout=15.0) as client:
        for offset in range(0, 400, 100):
            url = (f"{GAMMA_BASE}/markets"
                   f"?limit=100&closed=false&order=volume&ascending=false&offset={offset}")
            try:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError) as e:
                logger.error("Gamma API error at offset %d: %s", offset, e)
                break
            all_markets.extend(data)
            if len(data) < 100:
                break
            time.sleep(0.2)
    return all_markets


def _parse_market(m: dict) -> MarketSnapshot | None:
    """Parse a raw Gamma API market dict into a MarketSnapshot."""
    question = m.get("question", "")
    if is_sports(question):
        return None

    try:
        prices = json.loads(m.get("outcomePrices", "[]"))
        yes_price = float(prices[0])
        no_price = float(prices[1]) if len(prices) > 1 else 1.0 - yes_price
    except (json.JSONDecodeError, IndexError, ValueError):
        return None

    try:
        tokens = json.loads(m.get("clobTokenIds", "[]"))
    except json.JSONDecodeError:
        tokens = []
    if not tokens:
        return None

    return MarketSnapshot(
        market_id=m.get("id", ""),
        question=question,
        slug=m.get("slug", ""),
        yes_price=yes_price,
        no_price=no_price,
        volume_24h=float(m.get("volume24hr", 0) or 0),
        volume_total=float(m.get("volumeNum", 0) or 0),
        liquidity=float(m.get("liquidityNum", 0) or 0),
        end_date=m.get("endDate", ""),
        domain=classify_domain(question),
        snapshot_time=datetime.now(timezone.utc),
        yes_token=tokens[0],
        no_token=tokens[1] if len(tokens) > 1 else "",
    )


# --- Market Matching ---

def _question_keywords(question: str) -> set[str]:
    """Extract lowercase content words from a market question."""
    stop = {"will", "the", "a", "an", "in", "on", "at", "to", "for", "of",
            "and", "or", "by", "be", "is", "it", "if", "do", "yes", "no",
            "before", "after", "this", "that", "with", "from", "what", "who",
            "how", "when", "where", "why", "has", "have", "had", "not", "but"}
    words = set()
    for w in question.lower().split():
        clean = w.strip(".,!?;:\"'()[]$%")
        if clean and len(clean) > 1 and clean not in stop:
            words.add(clean)
    return words


def score_relevance(event: NewsEvent, market: MarketSnapshot) -> float:
    """Score how relevant a market is to a news event. Returns 0.0-1.0."""
    score = 0.0

    # Entity overlap: each shared entity = +0.3
    event_entities = {e.lower() for e in event.key_entities}
    market_kw = _question_keywords(market.question)
    shared_entities = event_entities & market_kw
    score += len(shared_entities) * 0.3

    # Domain match: +0.2
    if event.domain == market.domain and event.domain != "OTHER":
        score += 0.2

    # Keyword in question: check if any word from the event summary appears in market question
    summary_words = _question_keywords(event.summary)
    shared_summary = summary_words & market_kw
    if shared_summary:
        score += 0.2

    return min(score, 1.0)


def match_markets(
    event: NewsEvent,
    cache: MarketCache,
    store: SnapshotStore | None = None,
) -> list[MarketMatch]:
    """Find the most relevant markets for a news event."""
    cache.ensure_fresh()

    scored: list[tuple[float, MarketSnapshot]] = []
    for market in cache.markets:
        rel = score_relevance(event, market)
        if rel >= MIN_RELEVANCE:
            scored.append((rel, market))

    scored.sort(key=lambda x: (-x[0], -x[1].volume_total))
    top = scored[:MAX_MATCHES_PER_EVENT]

    matches: list[MarketMatch] = []
    for rel, market in top:
        price_before = None
        actual_move = None
        if store is not None:
            price_before = store.get_price_before(market.market_id, event.first_seen)
        if price_before is not None:
            actual_move = market.yes_price - price_before

        matches.append(MarketMatch(
            event=event,
            market=market,
            relevance_score=rel,
            price_before=price_before,
            price_after=market.yes_price,
            actual_move=actual_move,
        ))

    return matches


# --- Watchlist ---

def build_watchlist(cache: MarketCache) -> list[MarketSnapshot]:
    """Build watchlist: markets in active domains with sufficient volume and time."""
    now = datetime.now(timezone.utc)
    cache.ensure_fresh()

    watchlist: list[MarketSnapshot] = []
    for m in cache.markets:
        # Volume gate
        if m.volume_total < MIN_VOLUME_WATCHLIST:
            continue
        # Domain gate: skip OTHER (unclassifiable)
        if m.domain == "OTHER":
            continue
        # Resolution > 24h away
        if m.end_date:
            try:
                end = datetime.fromisoformat(m.end_date.replace("Z", "+00:00"))
                if (end - now).total_seconds() < MIN_HOURS_TO_RESOLUTION * 3600:
                    continue
            except (ValueError, TypeError):
                pass
        watchlist.append(m)

    watchlist.sort(key=lambda m: m.volume_total, reverse=True)
    return watchlist


# --- CLI Commands ---

def cmd_scan():
    """Fetch and display all active non-sports markets."""
    cache = MarketCache()
    count = cache.refresh()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'=' * 80}")
    print(f"MARKET SCAN — {now}")
    print(f"{'=' * 80}")
    print(f"  {count} non-sports markets fetched\n")

    # Group by domain
    by_domain: dict[str, list[MarketSnapshot]] = {}
    for m in cache.markets:
        by_domain.setdefault(m.domain, []).append(m)

    for domain in sorted(by_domain):
        markets = by_domain[domain]
        print(f"--- {domain} ({len(markets)}) ---")
        for m in markets[:10]:
            print(f"  YES={m.yes_price:.1%} | Vol=${m.volume_total:>12,.0f} "
                  f"| 24h=${m.volume_24h:>10,.0f} | {m.question[:60]}")
        if len(markets) > 10:
            print(f"  ... and {len(markets) - 10} more")
        print()


def cmd_match(query_text: str):
    """Find markets matching free-text query."""
    # Build a synthetic NewsEvent from the query text
    entities = extract_entities(query_text)
    # Also add capitalized words as entities since extract_entities needs sentence structure
    for word in query_text.split():
        clean = word.strip(".,!?;:\"'()[]")
        if clean and len(clean) > 1 and clean not in [e for e in entities]:
            entities.append(clean)

    event = NewsEvent(
        event_id="query",
        articles=[],
        key_entities=entities,
        summary=query_text,
        domain=classify_domain(query_text),
        is_breaking=False,
        first_seen=datetime.now(timezone.utc),
        source_count=0,
        query_names=[],
    )

    cache = MarketCache()
    store = SnapshotStore()
    matches = match_markets(event, cache, store)

    print(f"\nMatches for: \"{query_text}\"")
    print(f"Domain: {event.domain} | Entities: {entities[:5]}\n")

    if not matches:
        print("  No markets found above relevance threshold.")
    else:
        for i, mm in enumerate(matches):
            m = mm.market
            move_str = ""
            if mm.actual_move is not None:
                move_str = f" | Move: {mm.actual_move:+.1%}"
            before_str = ""
            if mm.price_before is not None:
                before_str = f" | Before: {mm.price_before:.1%}"
            print(f"  {i+1}. [{m.domain}] {m.question[:70]}")
            print(f"     Relevance: {mm.relevance_score:.2f} | YES={m.yes_price:.1%}"
                  f"{before_str}{move_str}")
            print(f"     Vol=${m.volume_total:,.0f} | Liq=${m.liquidity:,.0f}"
                  f" | ID: {m.market_id[:12]}...")
            print()

    store.close()


def cmd_snapshot():
    """Take a snapshot of all watched markets."""
    cache = MarketCache()
    store = SnapshotStore()
    watchlist = build_watchlist(cache)

    now = datetime.now(timezone.utc)
    store.save_snapshots(watchlist)

    print(f"Snapshot taken at {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  {len(watchlist)} markets in watchlist\n")

    for m in watchlist[:15]:
        print(f"  [{m.domain:5s}] YES={m.yes_price:.1%} | Vol=${m.volume_total:>12,.0f}"
              f" | {m.question[:55]}")
    if len(watchlist) > 15:
        print(f"  ... and {len(watchlist) - 15} more")

    store.close()


def cmd_history(market_id: str):
    """Show price history for a specific market."""
    store = SnapshotStore()
    history = store.get_history(market_id, limit=30)

    if not history:
        print(f"No snapshots found for market {market_id}")
        store.close()
        return

    # Try to get current market info
    cache = MarketCache()
    cache.refresh()
    current = cache.get(market_id)
    if current:
        print(f"\nMarket: {current.question}")
        print(f"  Current: YES={current.yes_price:.1%} | Domain: {current.domain}")
    else:
        print(f"\nMarket: {market_id} (not in current active markets)")

    print(f"\n{'Timestamp':<28s} {'YES':>8s} {'Vol 24h':>12s} {'Liquidity':>12s} {'Trigger':>10s}")
    print("-" * 75)
    for h in history:
        trigger = h["trigger_event_id"][:8] + "..." if h["trigger_event_id"] else "-"
        vol = f"${h['volume_24h']:,.0f}" if h["volume_24h"] else "-"
        liq = f"${h['liquidity']:,.0f}" if h["liquidity"] else "-"
        print(f"  {h['snapshot_time']:<26s} {h['yes_price']:>7.1%} {vol:>12s} {liq:>12s} {trigger:>10s}")

    store.close()


def cmd_watchlist():
    """Show current watchlist."""
    cache = MarketCache()
    watchlist = build_watchlist(cache)

    now = datetime.now(timezone.utc)
    print(f"\n{'=' * 80}")
    print(f"WATCHLIST — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 80}")
    print(f"  {len(watchlist)} markets (vol > ${MIN_VOLUME_WATCHLIST:,.0f}, >24h to resolution)\n")

    by_domain: dict[str, list[MarketSnapshot]] = {}
    for m in watchlist:
        by_domain.setdefault(m.domain, []).append(m)

    for domain in sorted(by_domain):
        markets = by_domain[domain]
        print(f"--- {domain} ({len(markets)}) ---")
        for m in markets[:8]:
            days_left = ""
            if m.end_date:
                try:
                    end = datetime.fromisoformat(m.end_date.replace("Z", "+00:00"))
                    d = (end - now).days
                    days_left = f" | {d}d left"
                except (ValueError, TypeError):
                    pass
            print(f"  YES={m.yes_price:.1%} | Vol=${m.volume_total:>12,.0f}"
                  f"{days_left} | {m.question[:55]}")
        if len(markets) > 8:
            print(f"  ... and {len(markets) - 8} more")
        print()


# --- Main ---

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    args = sys.argv[1:]

    if "--scan" in args:
        cmd_scan()
    elif "--match" in args:
        idx = args.index("--match")
        text = args[idx + 1] if idx + 1 < len(args) else ""
        if not text:
            print("Usage: --match \"query text\"")
            sys.exit(1)
        cmd_match(text)
    elif "--snapshot" in args:
        cmd_snapshot()
    elif "--history" in args:
        idx = args.index("--history")
        mid = args[idx + 1] if idx + 1 < len(args) else ""
        if not mid:
            print("Usage: --history <market_id>")
            sys.exit(1)
        cmd_history(mid)
    elif "--watchlist" in args:
        cmd_watchlist()
    else:
        print(__doc__)
        sys.exit(0)


if __name__ == "__main__":
    main()
