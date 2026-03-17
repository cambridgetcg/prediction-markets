#!/usr/bin/env python3
"""S012 Module 1: News Ingestor — Brave Search API poller with clustering.

Polls Brave News API, deduplicates via SQLite, clusters articles into
NewsEvents, and detects breaking news.

Usage:
    python3 scripts/s012/news_ingestor.py                     # One-shot poll all queries
    python3 scripts/s012/news_ingestor.py --query iran-nuclear # Poll single query
    python3 scripts/s012/news_ingestor.py --budget             # Show API budget
    python3 scripts/s012/news_ingestor.py --demo               # Synthetic demo data
    python3 scripts/s012/news_ingestor.py --events             # Show recent events/clusters
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import httpx
except ImportError:
    print("ERROR: httpx required. Install: pip3 install httpx")
    sys.exit(1)

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
USAGE_PATH = PROJECT_ROOT / "data" / "brave-api-usage.json"
CONFIG_PATH = PROJECT_ROOT / "config" / "news-pipeline.yaml"


# --- Domain Classification (from spike-detector.py) ---

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    'GEO': ['iran', 'strike', 'war', 'invasion', 'ceasefire', 'nato', 'ukraine',
             'russia', 'china', 'taiwan', 'israel', 'lebanon', 'khamenei',
             'regime', 'leader out', 'prime minister', 'grenell', 'venezuela',
             'greenland', 'annex', 'invade'],
    'CRY': ['bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol', 'xrp',
             'crypto', 'token', 'fdv', 'launch', 'dip to', 'reach $'],
    'POL': ['president', 'nomination', 'democrat', 'republican', 'trump',
             'election', 'nominate', 'congress', 'senate', 'governor',
             'fed chair', 'speaker'],
    'ECO': ['fed ', 'interest rate', 'bps', 'gdp', 'inflation', 'cpi',
             'unemployment', 'revenue', 'treasury'],
    'TEC': ['ai model', 'anthropic', 'openai', 'google', 'chatgpt', 'claude',
             'gemini', 'gpt'],
    'ENV': ['earthquake', 'hurricane', 'snow', 'temperature', 'wildfire',
             'climate', 'storm'],
}


def classify_domain(text: str) -> str:
    """Classify text into a domain based on keyword matching."""
    t = text.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in t:
                return domain
    return 'OTHER'


# --- Dataclasses ---

@dataclass
class Article:
    url: str
    title: str
    description: str
    extra_snippets: list[str]
    source_name: str
    source_domain: str
    country_queried: str
    age_raw: str
    published_at: datetime
    query_name: str
    fetched_at: datetime

    @property
    def url_hash(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()

    @property
    def full_text(self) -> str:
        return " ".join(filter(None, [self.title, self.description] + self.extra_snippets))


@dataclass
class NewsEvent:
    event_id: str              # SHA256 of normalized key entities + date
    articles: list[Article]    # Deduplicated articles about this event
    key_entities: list[str]    # People, places, orgs mentioned
    summary: str               # One-line summary of the event
    domain: str                # GEO, POL, CRY, ECO, TEC, ENV, OTHER
    is_breaking: bool          # True if >=3 sources within 30 min
    first_seen: datetime
    source_count: int          # Number of independent sources
    query_names: list[str]     # Which configured queries matched


# --- Age Parser ---

def parse_age(age_raw: str, reference: datetime | None = None) -> datetime:
    """Convert Brave's age strings to datetime.

    Handles:
        "9 hours ago", "2 days ago", "3 minutes ago", "1 month ago"
        ISO 8601 strings like "2026-02-27T10:30:00Z"
    """
    ref = reference or datetime.now(timezone.utc)

    # Try ISO 8601 first
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(age_raw, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue

    # Relative time: "N <unit> ago"
    m = re.match(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", age_raw, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        delta_map = {
            "second": timedelta(seconds=n),
            "minute": timedelta(minutes=n),
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=n * 30),
            "year": timedelta(days=n * 365),
        }
        return ref - delta_map[unit]

    # Fallback: return reference time
    return ref


# --- Entity Extraction (lightweight) ---

STOP_WORDS = frozenset({
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or",
    "is", "are", "was", "were", "be", "by", "with", "from", "that", "this",
    "it", "as", "has", "had", "have", "not", "but", "will", "its", "may",
    "can", "could", "would", "should", "been", "new", "says", "said",
    "after", "before", "over", "under", "about", "into", "up", "out",
    "all", "more", "than", "what", "who", "how", "when", "where", "why",
    "just", "now", "also", "very", "still", "even", "much", "some", "any",
})


def extract_entities(text: str) -> list[str]:
    """Extract rough entities from text (capitalized words not at sentence starts).

    Returns deduplicated entities sorted by frequency descending.
    """
    counts: dict[str, int] = {}

    # Split into sentences, skip first word of each (sentence-start capitalization)
    sentences = re.split(r'[.!?]+', text)
    for sentence in sentences:
        words = sentence.strip().split()
        for i, word in enumerate(words):
            clean = word.strip(".,!?;:\"'()[]")
            if not clean or len(clean) < 2:
                continue
            # Skip first word (sentence-start caps) and stop words
            if i == 0:
                continue
            if clean.lower() in STOP_WORDS:
                continue
            if clean[0].isupper():
                counts[clean] = counts.get(clean, 0) + 1

    # Also catch acronyms (all-caps, >=2 chars) regardless of position
    for word in text.split():
        clean = word.strip(".,!?;:\"'()[]")
        if clean.isupper() and len(clean) >= 2 and clean.lower() not in STOP_WORDS:
            counts[clean] = counts.get(clean, 0) + 1

    return sorted(counts, key=lambda e: (-counts[e], e))


# --- SQLite Seen-Set ---

class SeenStore:
    """SQLite-backed URL deduplication that persists across poll cycles."""

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_urls (
                url_hash    TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                first_seen  TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def is_seen(self, url_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_urls WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        return row is not None

    def mark_seen(self, url_hash: str, url: str):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_urls (url_hash, url, first_seen) VALUES (?, ?, ?)",
            (url_hash, url, now),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


# --- Budget Tracker ---

class BudgetTracker:
    """Track Brave API requests per day/month. Persists to JSON."""

    def __init__(self, monthly_limit: int = 900, daily_soft_limit: int = 50,
                 usage_path: Path = USAGE_PATH):
        self.monthly_limit = monthly_limit
        self.daily_soft_limit = daily_soft_limit
        self.path = usage_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path) as f:
                return json.load(f)
        return {"month": "", "daily": {}, "total": 0}

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)

    def _current_month(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _current_day(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _reset_if_new_month(self):
        month = self._current_month()
        if self.data.get("month") != month:
            self.data = {"month": month, "daily": {}, "total": 0}

    def record(self, count: int = 1):
        self._reset_if_new_month()
        day = self._current_day()
        self.data["total"] = self.data.get("total", 0) + count
        self.data["daily"][day] = self.data["daily"].get(day, 0) + count
        self._save()

    def can_request(self, count: int = 1) -> tuple[bool, str]:
        """Check if we can make `count` more requests. Returns (ok, reason)."""
        self._reset_if_new_month()
        month_used = self.data.get("total", 0)
        if month_used + count > self.monthly_limit:
            return False, f"Monthly limit reached: {month_used}/{self.monthly_limit}"

        day = self._current_day()
        day_used = self.data["daily"].get(day, 0)
        if day_used + count > self.daily_soft_limit:
            logger.warning(
                "Daily soft limit: %d/%d (month: %d/%d)",
                day_used + count, self.daily_soft_limit,
                month_used + count, self.monthly_limit,
            )

        return True, ""

    def summary(self) -> dict:
        self._reset_if_new_month()
        month_used = self.data.get("total", 0)
        day = self._current_day()
        day_used = self.data["daily"].get(day, 0)
        return {
            "month": self.data.get("month", ""),
            "month_used": month_used,
            "month_limit": self.monthly_limit,
            "month_remaining": self.monthly_limit - month_used,
            "day_used": day_used,
            "day_soft_limit": self.daily_soft_limit,
        }


# --- Config ---

@dataclass
class QueryConfig:
    name: str
    keywords: list[str]
    boolean_mode: str = "OR"
    countries: list[str] = field(default_factory=lambda: ["US", "GB"])
    freshness: str = "pd"
    count_per_country: int = 15
    interval_minutes: int = 60
    extra_snippets: bool = True


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    """Load pipeline config from YAML file."""
    if not config_path.exists():
        logger.warning("Config not found at %s, using defaults", config_path)
        return {}
    if yaml is None:
        logger.error("PyYAML not installed. Install: pip3 install pyyaml")
        return {}
    text = config_path.read_text()
    return yaml.safe_load(text) or {}


def queries_from_config(config: dict) -> list[QueryConfig]:
    """Build QueryConfig list from parsed YAML config."""
    queries_raw = config.get("queries", [])
    if not queries_raw:
        return _default_queries()

    queries = []
    for q in queries_raw:
        queries.append(QueryConfig(
            name=q["name"],
            keywords=q.get("keywords", []),
            boolean_mode=q.get("boolean_mode", "OR"),
            countries=q.get("countries", ["US", "GB"]),
            freshness=q.get("freshness", "pd"),
            count_per_country=q.get("count_per_country", 15),
            interval_minutes=q.get("interval_minutes", 60),
            extra_snippets=q.get("extra_snippets", True),
        ))
    return queries


def _default_queries() -> list[QueryConfig]:
    return [
        QueryConfig(name="iran-nuclear", keywords=["Iran nuclear"],
                    countries=["US", "GB", "RU", "SA", "TR", "IN"]),
        QueryConfig(name="russia-ukraine", keywords=["Russia Ukraine"],
                    countries=["US", "GB", "RU", "SA"]),
        QueryConfig(name="us-politics", keywords=["Trump", "Congress"],
                    countries=["US", "GB"]),
        QueryConfig(name="markets-macro", keywords=["Federal Reserve", "interest rates"],
                    countries=["US", "GB"]),
    ]


# --- Brave News Poller ---

class BraveNewsPoller:
    """Polls Brave News Search API across multiple country indexes."""

    BASE_URL = "https://api.search.brave.com/res/v1/news/search"
    RATE_LIMIT_SECONDS = 1.0

    def __init__(self, api_key: str | None = None,
                 budget: BudgetTracker | None = None,
                 seen: SeenStore | None = None):
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "") or self._keychain_get()
        if not self.api_key:
            raise ValueError("BRAVE_API_KEY not set. Pass it, set env var, or store in keychain.")
        self.budget = budget or BudgetTracker()
        self.seen = seen or SeenStore()
        self._last_request_time = 0.0

    @staticmethod
    def _keychain_get() -> str:
        """Try to retrieve Brave API key from macOS Keychain."""
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-a", "prediction-markets",
                 "-s", "brave_api_key", "-w"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    async def poll(self, query: QueryConfig) -> list[Article]:
        """Poll all country variants for a query. Returns new (unseen) articles."""
        query_text = self._build_query_text(query)
        now = datetime.now(timezone.utc)

        n_countries = len(query.countries)
        ok, reason = self.budget.can_request(n_countries)
        if not ok:
            logger.warning("BUDGET BLOCK: %s", reason)
            return []

        all_articles: list[Article] = []
        for country in query.countries:
            await self._rate_limit()
            articles = await self._fetch_country(query_text, query, country, now)
            if articles is not None:
                all_articles.extend(articles)
                self.budget.record(1)

        # Deduplicate
        new_articles: list[Article] = []
        for article in all_articles:
            if not self.seen.is_seen(article.url_hash):
                self.seen.mark_seen(article.url_hash, article.url)
                new_articles.append(article)

        return new_articles

    def _build_query_text(self, query: QueryConfig) -> str:
        if len(query.keywords) == 1:
            return query.keywords[0]
        joiner = " OR " if query.boolean_mode == "OR" else " AND "
        return joiner.join(query.keywords)

    async def _rate_limit(self):
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.RATE_LIMIT_SECONDS:
            await asyncio.sleep(self.RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = time.monotonic()

    async def _fetch_country(
        self, query_text: str, query: QueryConfig, country: str, now: datetime
    ) -> list[Article] | None:
        """Fetch articles for a single country index."""
        params = {
            "q": query_text,
            "count": query.count_per_country,
            "country": country,
            "freshness": query.freshness,
        }
        if query.extra_snippets:
            params["extra_snippets"] = "true"

        headers = {
            "X-Subscription-Token": self.api_key,
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self.BASE_URL, params=params, headers=headers, timeout=15.0)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("HTTP %d for %s/%s: %s", e.response.status_code, country, query.name, e)
            return None
        except httpx.RequestError as e:
            logger.error("Request error for %s/%s: %s", country, query.name, e)
            return None

        results = data.get("results", [])
        articles = []
        for r in results:
            meta_url = r.get("meta_url", {}) or {}
            hostname = meta_url.get("hostname", "")
            if not hostname:
                hostname = urlparse(r.get("url", "")).netloc
            snippets = r.get("extra_snippets", []) or []
            title = r.get("title", "")
            desc = r.get("description", "")
            age_raw = r.get("age", "")

            articles.append(Article(
                url=r.get("url", ""),
                title=title,
                description=desc,
                extra_snippets=snippets,
                source_name=hostname.replace("www.", "").split(".")[0] if hostname else "",
                source_domain=hostname,
                country_queried=country,
                age_raw=age_raw,
                published_at=parse_age(age_raw, reference=now),
                query_name=query.name,
                fetched_at=now,
            ))

        return articles

    def close(self):
        self.seen.close()


# --- Event Clustering ---

JACCARD_THRESHOLD = 0.3
MIN_SHARED_ENTITIES = 2
TIME_WINDOW_HOURS = 48
BREAKING_WINDOW_MINUTES = 30
BREAKING_SOURCE_THRESHOLD = 3


def _title_words(text: str) -> set[str]:
    """Lowercase content words from text (for Jaccard similarity)."""
    words = set(text.lower().split()) - STOP_WORDS
    return {w.strip(".,!?;:\"'()[]") for w in words if len(w) > 2}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _within_window(dt1: datetime, dt2: datetime, hours: int = TIME_WINDOW_HOURS) -> bool:
    return abs((dt1 - dt2).total_seconds()) <= hours * 3600


def _make_event_id(entities: list[str], date_str: str) -> str:
    """Deterministic hash of sorted top-3 entities + date."""
    top3 = sorted(e.lower() for e in entities[:3]) if entities else ["unknown"]
    raw = "|".join(top3) + "|" + date_str
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _detect_breaking(articles: list[Article]) -> bool:
    """True if >=3 articles from different source domains arrived within 30 minutes."""
    if len(articles) < BREAKING_SOURCE_THRESHOLD:
        return False

    sorted_arts = sorted(articles, key=lambda a: a.published_at)
    for i, anchor in enumerate(sorted_arts):
        window_end = anchor.published_at + timedelta(minutes=BREAKING_WINDOW_MINUTES)
        domains_in_window: set[str] = set()
        for j in range(i, len(sorted_arts)):
            if sorted_arts[j].published_at <= window_end:
                domains_in_window.add(sorted_arts[j].source_domain)
            else:
                break
        if len(domains_in_window) >= BREAKING_SOURCE_THRESHOLD:
            return True
    return False


def _ranked_entities(articles: list[Article]) -> list[str]:
    """Union of entities across articles, sorted by frequency descending."""
    counts: dict[str, int] = {}
    for a in articles:
        for e in extract_entities(a.full_text):
            counts[e] = counts.get(e, 0) + 1
    return sorted(counts, key=lambda e: (-counts[e], e))


def cluster_articles(articles: list[Article]) -> list[NewsEvent]:
    """Group articles into NewsEvents by entity overlap + title similarity.

    Uses incremental matching: each article is matched against existing clusters
    (growing entity set), or starts a new cluster.
    """
    # Working clusters: list of (articles, entity_set, title_words_union)
    clusters: list[tuple[list[Article], set[str], set[str]]] = []

    for article in articles:
        art_entities = {e.lower() for e in extract_entities(article.full_text)}
        art_title = _title_words(article.title)

        best_idx: int | None = None
        best_score: float = 0

        for ci, (c_arts, c_entities, c_title_words) in enumerate(clusters):
            # Time window: compare against cluster's first article
            if not _within_window(article.published_at, c_arts[0].published_at):
                continue

            # Primary: entity overlap against cluster's accumulated entities
            overlap = len(art_entities & c_entities)
            if overlap >= MIN_SHARED_ENTITIES and overlap > best_score:
                best_idx = ci
                best_score = overlap
                continue

            # Fallback: title Jaccard if entities are sparse
            if len(art_entities) < MIN_SHARED_ENTITIES:
                jacc = _jaccard(art_title, c_title_words)
                if jacc >= JACCARD_THRESHOLD and jacc > best_score:
                    best_idx = ci
                    best_score = jacc

        if best_idx is not None:
            # Merge into existing cluster
            c_arts, c_entities, c_title_words = clusters[best_idx]
            c_arts.append(article)
            c_entities.update(art_entities)
            c_title_words.update(art_title)
        else:
            # New cluster
            clusters.append(([article], set(art_entities), set(art_title)))

    # Convert working clusters to NewsEvents
    events: list[NewsEvent] = []
    for c_arts, _, _ in clusters:
        ranked = _ranked_entities(c_arts)
        first_seen = min(a.published_at for a in c_arts)
        event_id = _make_event_id(ranked, first_seen.strftime("%Y-%m-%d"))

        combined_titles = " ".join(a.title for a in c_arts)
        domain = classify_domain(combined_titles)
        summary = min((a.title for a in c_arts), key=len, default="")
        source_domains = {a.source_domain for a in c_arts}
        query_names = sorted({a.query_name for a in c_arts})

        events.append(NewsEvent(
            event_id=event_id,
            articles=c_arts,
            key_entities=ranked[:10],
            summary=summary,
            domain=domain,
            is_breaking=_detect_breaking(c_arts),
            first_seen=first_seen,
            source_count=len(source_domains),
            query_names=query_names,
        ))

    return events


# --- Event Persistence ---

class EventStore:
    """SQLite-backed event persistence."""

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS news_events (
                event_id      TEXT PRIMARY KEY,
                summary       TEXT,
                domain        TEXT,
                key_entities  TEXT,
                is_breaking   INTEGER DEFAULT 0,
                first_seen    TEXT,
                source_count  INTEGER,
                query_names   TEXT,
                article_count INTEGER,
                created_at    TEXT
            );
            CREATE TABLE IF NOT EXISTS event_articles (
                event_id      TEXT,
                url_hash      TEXT,
                url           TEXT,
                title         TEXT,
                source_domain TEXT,
                published_at  TEXT,
                PRIMARY KEY (event_id, url_hash)
            );
        """)
        self.conn.commit()

    def save_events(self, events: list[NewsEvent]):
        for ev in events:
            self.conn.execute("""
                INSERT INTO news_events
                    (event_id, summary, domain, key_entities, is_breaking,
                     first_seen, source_count, query_names, article_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    summary = excluded.summary,
                    source_count = excluded.source_count,
                    article_count = excluded.article_count,
                    key_entities = excluded.key_entities,
                    is_breaking = MAX(news_events.is_breaking, excluded.is_breaking)
            """, (
                ev.event_id, ev.summary, ev.domain,
                json.dumps(ev.key_entities), int(ev.is_breaking),
                ev.first_seen.isoformat(), ev.source_count,
                json.dumps(ev.query_names), len(ev.articles),
                datetime.now(timezone.utc).isoformat(),
            ))
            for art in ev.articles:
                self.conn.execute("""
                    INSERT OR IGNORE INTO event_articles
                        (event_id, url_hash, url, title, source_domain, published_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    ev.event_id, art.url_hash, art.url, art.title,
                    art.source_domain, art.published_at.isoformat(),
                ))
        self.conn.commit()

    def load_recent(self, hours: int = 72) -> list[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = self.conn.execute("""
            SELECT event_id, summary, domain, key_entities, is_breaking,
                   first_seen, source_count, query_names, article_count
            FROM news_events
            WHERE first_seen > ?
            ORDER BY first_seen DESC
        """, (cutoff,)).fetchall()

        events = []
        for row in rows:
            events.append({
                "event_id": row[0],
                "summary": row[1],
                "domain": row[2],
                "key_entities": json.loads(row[3]) if row[3] else [],
                "is_breaking": bool(row[4]),
                "first_seen": row[5],
                "source_count": row[6],
                "query_names": json.loads(row[7]) if row[7] else [],
                "article_count": row[8],
            })
        return events

    def close(self):
        self.conn.close()


# --- Demo ---

def _make_demo_article(**overrides) -> Article:
    defaults = dict(
        url="https://example.com/test",
        title="Test Article",
        description="A test description.",
        extra_snippets=[],
        source_name="example",
        source_domain="example.com",
        country_queried="US",
        age_raw="1 hour ago",
        published_at=datetime.now(timezone.utc),
        query_name="test",
        fetched_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Article(**defaults)


def cmd_demo():
    """Run clustering on synthetic demo data."""
    now = datetime.now(timezone.utc)

    articles: list[Article] = []

    # Iran cluster: 5 articles from different sources, tight timing -> breaking
    iran_sources = [
        ("reuters.com", "Reuters"), ("bbc.com", "BBC"),
        ("rt.com", "RT"), ("aljazeera.com", "Al Jazeera"),
        ("nytimes.com", "NYT"),
    ]
    for i, (domain, name) in enumerate(iran_sources):
        articles.append(_make_demo_article(
            url=f"https://{domain}/iran-nuclear-{i}",
            title="Iran Nuclear Talks Resume in Geneva as IAEA Pushes for Inspections",
            description=f"IAEA inspectors demand access to Iranian enrichment facilities. {name} report.",
            source_name=name,
            source_domain=domain,
            country_queried=["US", "GB", "RU", "SA", "TR"][i],
            published_at=now - timedelta(minutes=i * 5),
            query_name="iran-nuclear",
        ))

    # Ukraine cluster: 3 articles, spread out
    for i in range(3):
        articles.append(_make_demo_article(
            url=f"https://example.com/ukraine-{i}",
            title="Ukraine Ceasefire Talks Stall as Zelensky Rejects Russian Terms",
            description="NATO allies discuss next steps. Russia demands withdrawal from Crimea.",
            source_name=["Reuters", "BBC", "CNN"][i],
            source_domain=["reuters.com", "bbc.com", "cnn.com"][i],
            country_queried=["US", "GB", "RU"][i],
            published_at=now - timedelta(hours=2 + i),
            query_name="russia-ukraine",
        ))

    # Unrelated singleton
    articles.append(_make_demo_article(
        url="https://techcrunch.com/ai-regulation-1",
        title="EU Passes New AI Regulation Framework Targeting Foundation Models",
        description="European Parliament votes on comprehensive AI safety requirements.",
        source_name="TechCrunch",
        source_domain="techcrunch.com",
        published_at=now - timedelta(hours=6),
        query_name="ai-regulation",
    ))

    events = cluster_articles(articles)

    print(f"Input: {len(articles)} articles")
    print(f"Output: {len(events)} events\n")

    for ev in events:
        breaking = " [BREAKING]" if ev.is_breaking else ""
        print(f"--- Event {ev.event_id}{breaking} ---")
        print(f"  Domain:   {ev.domain}")
        print(f"  Summary:  {ev.summary}")
        print(f"  Articles: {len(ev.articles)} from {ev.source_count} sources")
        print(f"  Entities: {ev.key_entities[:5]}")
        print(f"  Queries:  {ev.query_names}")
        print()


# --- CLI Commands ---

def cmd_budget():
    config = load_config()
    brave_cfg = config.get("brave", {})
    tracker = BudgetTracker(
        monthly_limit=brave_cfg.get("max_requests_per_month", 900),
        daily_soft_limit=brave_cfg.get("daily_soft_limit", 50),
    )
    s = tracker.summary()
    print("Brave API Budget")
    print(f"  Month:     {s['month']}")
    print(f"  Used:      {s['month_used']}/{s['month_limit']} ({s['month_remaining']} remaining)")
    print(f"  Today:     {s['day_used']}/{s['day_soft_limit']} (soft limit)")


def cmd_events():
    store = EventStore()
    events = store.load_recent(hours=72)
    store.close()

    if not events:
        print("No recent events (last 72h).")
        return

    print(f"{len(events)} event(s) in last 72h:\n")
    for ev in events:
        breaking = " [BREAKING]" if ev["is_breaking"] else ""
        print(f"  [{ev['domain']}] {ev['summary'][:80]}{breaking}")
        print(f"    ID: {ev['event_id']} | Sources: {ev['source_count']} | Articles: {ev['article_count']}")
        print(f"    Entities: {ev['key_entities'][:5]}")
        print(f"    First seen: {ev['first_seen']}")
        print()


def cmd_poll(query_filter: str | None = None):
    config = load_config()
    queries = queries_from_config(config)

    if query_filter:
        queries = [q for q in queries if query_filter.lower() in q.name.lower()]
        if not queries:
            print(f"No queries matching '{query_filter}'")
            return

    brave_cfg = config.get("brave", {})
    budget = BudgetTracker(
        monthly_limit=brave_cfg.get("max_requests_per_month", 900),
        daily_soft_limit=brave_cfg.get("daily_soft_limit", 50),
    )
    poller = BraveNewsPoller(budget=budget)
    event_store = EventStore()

    async def _run():
        all_articles: list[Article] = []
        for q in queries:
            logger.info("Polling: %s", q.name)
            new = await poller.poll(q)
            if new:
                print(f"  {q.name}: {len(new)} new articles")
                for a in new[:3]:
                    print(f"    [{a.source_domain}] {a.title[:80]}")
                if len(new) > 3:
                    print(f"    ... and {len(new) - 3} more")
            else:
                print(f"  {q.name}: 0 new articles")
            all_articles.extend(new)

        if all_articles:
            events = cluster_articles(all_articles)
            event_store.save_events(events)
            print(f"\n{len(all_articles)} articles -> {len(events)} events")
            for ev in events:
                breaking = " [BREAKING]" if ev.is_breaking else ""
                print(f"  [{ev.domain}] {ev.summary[:80]}{breaking} ({ev.source_count} sources)")
        else:
            print("\nNo new articles.")

    asyncio.run(_run())

    budget_s = budget.summary()
    print(f"\nBudget: {budget_s['month_used']}/{budget_s['month_limit']} this month")
    poller.close()
    event_store.close()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    args = sys.argv[1:]
    if "--budget" in args:
        cmd_budget()
    elif "--demo" in args:
        cmd_demo()
    elif "--events" in args:
        cmd_events()
    elif "--query" in args:
        idx = args.index("--query")
        q = args[idx + 1] if idx + 1 < len(args) else None
        cmd_poll(q)
    else:
        cmd_poll()


if __name__ == "__main__":
    main()
