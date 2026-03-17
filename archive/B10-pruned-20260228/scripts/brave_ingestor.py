#!/usr/bin/env python3
"""
NB02: Brave News Ingestor — Stage 1 of the News Intelligence Pipeline.

Polls the Brave News Search API across multiple country indexes,
deduplicates articles via SQLite, tracks API budget, and runs on
a configurable polling schedule.

Usage:
    python3 scripts/brave_ingestor.py                          # One-shot poll all queries
    python3 scripts/brave_ingestor.py --forever                # Polling scheduler loop
    python3 scripts/brave_ingestor.py --budget                 # Show budget usage
    python3 scripts/brave_ingestor.py --query "Iran nuclear"   # Poll single query
"""

import asyncio
import hashlib
import json
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

# --- Project root ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
USAGE_PATH = PROJECT_ROOT / "data" / "brave-api-usage.json"


# --- Dataclasses ---

@dataclass
class QueryConfig:
    name: str
    keywords: list[str]
    boolean_mode: str = "OR"          # "OR" | "AND"
    countries: list[str] = field(default_factory=lambda: ["US", "GB", "RU", "QA"])
    freshness: str = "pd"             # "pd" (past day) | "pw" (past week)
    count_per_country: int = 20
    interval_minutes: int = 1440      # 24h default (hot tier)
    extra_snippets: bool = True


@dataclass
class Article:
    url: str
    title: str
    description: str
    extra_snippets: list[str]
    full_text: str
    source_name: str
    source_domain: str
    country_queried: str
    age_raw: str
    published_at: datetime
    query_name: str
    fetched_at: datetime
    # Computed downstream (NB03+)
    tone: float | None = None
    entities: list[str] | None = None
    key_claim: str | None = None
    lean: float | None = None
    geo_cluster: str | None = None
    reliability: float | None = None

    @property
    def url_hash(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()


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
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS article_countries (
                url_hash TEXT,
                country  TEXT NOT NULL,
                PRIMARY KEY (url_hash, country)
            )
        """)
        self.conn.commit()

    def is_seen(self, url_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_urls WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        return row is not None

    def mark_seen(self, url_hash: str, url: str, country: str):
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_urls (url_hash, url, first_seen) VALUES (?, ?, ?)",
            (url_hash, url, now),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO article_countries (url_hash, country) VALUES (?, ?)",
            (url_hash, country),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


# --- Budget Tracker ---

class BudgetTracker:
    """Track Brave API requests per hour/day/month. Persists to JSON."""

    MONTHLY_LIMIT = 900
    DAILY_SOFT_LIMIT = 35
    COST_PER_1000 = 5.0  # $5 per 1000 requests

    def __init__(self, usage_path: Path = USAGE_PATH):
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
        if month_used + count > self.MONTHLY_LIMIT:
            return False, f"Monthly limit reached: {month_used}/{self.MONTHLY_LIMIT}"

        day = self._current_day()
        day_used = self.data["daily"].get(day, 0)
        if day_used + count > self.DAILY_SOFT_LIMIT:
            # Soft limit — warn but allow
            cost = (month_used + count) / 1000 * self.COST_PER_1000
            print(f"  ⚠ Daily soft limit: {day_used + count}/{self.DAILY_SOFT_LIMIT} "
                  f"(month: {month_used + count}/{self.MONTHLY_LIMIT}, est ${cost:.2f})")

        return True, ""

    def summary(self) -> dict:
        self._reset_if_new_month()
        month_used = self.data.get("total", 0)
        day = self._current_day()
        day_used = self.data["daily"].get(day, 0)
        cost = month_used / 1000 * self.COST_PER_1000
        return {
            "month": self.data.get("month", ""),
            "month_used": month_used,
            "month_limit": self.MONTHLY_LIMIT,
            "month_remaining": self.MONTHLY_LIMIT - month_used,
            "day_used": day_used,
            "day_soft_limit": self.DAILY_SOFT_LIMIT,
            "estimated_cost": round(cost, 2),
        }


# --- Brave News Poller ---

class BraveNewsPoller:
    """Polls Brave News Search API across multiple country indexes."""

    BASE_URL = "https://api.search.brave.com/res/v1/news/search"
    RATE_LIMIT_SECONDS = 1.0  # Min time between requests

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "") or self._keychain_get()
        if not self.api_key:
            raise ValueError("BRAVE_API_KEY not set. Pass it, set env var, or store in keychain.")
        self.budget = BudgetTracker()
        self.seen = SeenStore()
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

        # Check budget for all countries
        n_countries = len(query.countries)
        ok, reason = self.budget.can_request(n_countries)
        if not ok:
            print(f"  BUDGET BLOCK: {reason}")
            return []

        # Fetch all countries with rate limiting
        all_articles: list[Article] = []
        for country in query.countries:
            await self._rate_limit()
            articles = await self._fetch_country(query_text, query, country, now)
            if articles is not None:  # None = HTTP error (don't count budget)
                all_articles.extend(articles)
                self.budget.record(1)

        # Deduplicate: keep article if URL not yet seen from this country
        new_articles: list[Article] = []
        for article in all_articles:
            url_hash = article.url_hash
            was_seen = self.seen.is_seen(url_hash)
            # Always record the country observation
            self.seen.mark_seen(url_hash, article.url, article.country_queried)
            if not was_seen:
                new_articles.append(article)

        return new_articles

    def _build_query_text(self, query: QueryConfig) -> str:
        if len(query.keywords) == 1:
            return query.keywords[0]
        joiner = " OR " if query.boolean_mode == "OR" else " AND "
        return joiner.join(query.keywords)

    async def _rate_limit(self):
        """Ensure minimum gap between requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.RATE_LIMIT_SECONDS:
            await asyncio.sleep(self.RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = time.monotonic()

    async def _fetch_country(
        self, query_text: str, query: QueryConfig, country: str, now: datetime
    ) -> list[Article]:
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
            print(f"  HTTP {e.response.status_code} for {country}/{query.name}: {e}")
            return None
        except httpx.RequestError as e:
            print(f"  Request error for {country}/{query.name}: {e}")
            return None

        results = data.get("results", [])
        articles = []
        for r in results:
            source = r.get("source", {})
            source_url = source.get("url", "")
            domain = urlparse(source_url).netloc if source_url else ""
            snippets = r.get("extra_snippets", []) or []
            title = r.get("title", "")
            desc = r.get("description", "")
            full_text = " ".join(filter(None, [title, desc] + snippets))
            age_raw = r.get("age", "")

            articles.append(Article(
                url=r.get("url", ""),
                title=title,
                description=desc,
                extra_snippets=snippets,
                full_text=full_text,
                source_name=source.get("name", ""),
                source_domain=domain,
                country_queried=country,
                age_raw=age_raw,
                published_at=parse_age(age_raw, reference=now),
                query_name=query.name,
                fetched_at=now,
            ))

        return articles

    def close(self):
        self.seen.close()


# --- Polling Scheduler ---

class PollScheduler:
    """Runs queries on their configured intervals forever."""

    def __init__(self, poller: BraveNewsPoller, queries: list[QueryConfig]):
        self.poller = poller
        self.queries = queries
        self._last_poll: dict[str, float] = {}

    async def run_once(self) -> list[Article]:
        """Run all due queries. Returns all new articles."""
        all_new = []
        now = time.monotonic()

        for q in self.queries:
            last = self._last_poll.get(q.name, 0)
            interval_sec = q.interval_minutes * 60
            if now - last < interval_sec and last > 0:
                continue

            print(f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Polling: {q.name}")
            new_articles = await self.poller.poll(q)
            self._last_poll[q.name] = time.monotonic()

            if new_articles:
                print(f"  → {len(new_articles)} new articles")
                for a in new_articles[:3]:
                    print(f"    • [{a.source_name}] {a.title[:80]}")
                if len(new_articles) > 3:
                    print(f"    ... and {len(new_articles) - 3} more")
            else:
                print(f"  → 0 new articles")

            all_new.extend(new_articles)

        return all_new

    async def run_forever(self, check_interval: int = 60):
        """Loop: check for due queries every `check_interval` seconds."""
        print(f"Scheduler started. {len(self.queries)} queries configured.")
        print(f"Budget: {json.dumps(self.poller.budget.summary(), indent=2)}")
        print(f"Checking every {check_interval}s for due queries.\n")

        try:
            while True:
                await self.run_once()
                await asyncio.sleep(check_interval)
        except KeyboardInterrupt:
            print("\nScheduler stopped.")
        finally:
            self.poller.close()


# --- Default Queries (from NB01 config) ---

# Brave-supported country codes (verified):
#   US, GB, RU, CN, DE, FR, IN, AU, SA, TR, JP — all return 200
#   QA, IR, IL, AE — return 422 (unsupported)
# Substitutions: QA→SA (Gulf perspective), IR/IL→TR (regional)

DEFAULT_QUERIES = [
    QueryConfig(
        name="iran-nuclear",
        keywords=["Iran nuclear"],
        countries=["US", "GB", "RU", "SA", "TR", "IN"],
        freshness="pd",
        interval_minutes=1440,
    ),
    QueryConfig(
        name="russia-ukraine",
        keywords=["Russia Ukraine"],
        countries=["US", "GB", "RU", "SA"],
        freshness="pd",
        interval_minutes=1440,
    ),
    QueryConfig(
        name="trump-tariffs",
        keywords=["Trump tariffs", "trade war"],
        boolean_mode="OR",
        countries=["US", "GB", "CN", "SA"],
        freshness="pd",
        interval_minutes=3360,  # ~56h (warm)
    ),
    QueryConfig(
        name="fed-rates",
        keywords=["Federal Reserve", "interest rates"],
        boolean_mode="OR",
        countries=["US", "GB"],
        freshness="pd",
        interval_minutes=3360,
    ),
    QueryConfig(
        name="ai-regulation",
        keywords=["AI regulation"],
        countries=["US", "GB"],
        freshness="pw",
        interval_minutes=5040,  # ~84h (cold)
    ),
]


# --- CLI ---

def cmd_budget():
    tracker = BudgetTracker()
    s = tracker.summary()
    print("Brave API Budget")
    print(f"  Month:     {s['month']}")
    print(f"  Used:      {s['month_used']}/{s['month_limit']} ({s['month_remaining']} remaining)")
    print(f"  Today:     {s['day_used']}/{s['day_soft_limit']} (soft limit)")
    print(f"  Est. cost: ${s['estimated_cost']}")


def cmd_poll(query_filter: str | None = None):
    queries = DEFAULT_QUERIES
    if query_filter:
        queries = [q for q in queries if query_filter.lower() in q.name.lower()
                   or query_filter.lower() in " ".join(q.keywords).lower()]
        if not queries:
            print(f"No queries matching '{query_filter}'")
            return

    poller = BraveNewsPoller()
    scheduler = PollScheduler(poller, queries)

    articles = asyncio.run(scheduler.run_once())
    print(f"\nTotal new articles: {len(articles)}")

    budget = poller.budget.summary()
    print(f"Budget: {budget['month_used']}/{budget['month_limit']} this month")
    poller.close()


def cmd_forever():
    poller = BraveNewsPoller()
    scheduler = PollScheduler(poller, DEFAULT_QUERIES)
    asyncio.run(scheduler.run_forever())


def main():
    args = sys.argv[1:]

    if "--budget" in args:
        cmd_budget()
    elif "--forever" in args:
        cmd_forever()
    elif "--query" in args:
        idx = args.index("--query")
        q = args[idx + 1] if idx + 1 < len(args) else None
        cmd_poll(q)
    else:
        cmd_poll()


if __name__ == "__main__":
    main()
