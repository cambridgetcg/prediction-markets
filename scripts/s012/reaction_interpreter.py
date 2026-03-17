#!/usr/bin/env python3
"""S012 Module 3: Reaction Interpreter — LLM-based rational probability shift estimator.

Receives a MarketMatch (news event + matched market + prices), calls an LLM to
estimate the rational probability shift the news should cause, and logs the
interpretation to JSONL + SQLite.

Usage:
    python3 scripts/s012/reaction_interpreter.py --demo          # Synthetic demo (no API)
    python3 scripts/s012/reaction_interpreter.py --event <id>    # Interpret specific event
    python3 scripts/s012/reaction_interpreter.py --recent        # Show recent interpretations
    python3 scripts/s012/reaction_interpreter.py --calibration   # Show LLM calibration stats
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Import shared pieces from Modules 1 & 2
from news_ingestor import NewsEvent, EventStore, classify_domain
from market_snapshot import (
    MarketMatch,
    MarketSnapshot,
    MarketCache,
    SnapshotStore,
    match_markets,
)

logger = logging.getLogger(__name__)

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
JSONL_PATH = PROJECT_ROOT / "data" / "s012" / "interpretations.jsonl"
CREDIBILITY_PATH = PROJECT_ROOT / "research" / "source-credibility-matrix.json"

# --- Config ---
PROMPT_VERSION = "v1.0"
MODEL = "claude-haiku-4-5"
MAX_TOKENS = 500
TEMPERATURE = 0.0
MAX_INTERPRETATIONS_PER_HOUR = 20
COOLDOWN_MINUTES = 60


# --- Dataclass ---

@dataclass
class Interpretation:
    interpretation_id: str
    event_id: str
    market_id: str
    market_question: str

    # LLM estimates
    prior_probability: float
    posterior_probability: float
    estimated_shift: float

    # Metadata
    confidence: float
    reasoning: str
    news_type: str       # NOVEL | CONFIRMATORY | CONTRADICTORY | AMBIGUOUS
    source_quality: str  # VERIFIED | CREDIBLE | UNCONFIRMED | RUMOR

    # Calibration
    interpreted_at: datetime
    model_used: str
    prompt_version: str

    # Raw
    raw_llm_response: str


# --- Prompt ---

INTERPRETATION_PROMPT = """You are an expert prediction market analyst. Your job is to estimate \
how a news event should rationally affect a prediction market's probability.

## The News Event

{event_summary}

Sources ({source_count} independent):
{source_list}

First reported: {first_seen}
Domain: {domain}

## The Market

Question: {market_question}
Current YES price: {current_yes_price} (= {current_yes_pct}% implied probability)
Resolution date: {end_date}
Total volume: ${volume_total:,.0f}
24h volume: ${volume_24h:,.0f}

## Domain Context

{domain_context}

## Your Task

Estimate the RATIONAL probability shift this news should cause on this market.

Think step by step:
1. What was the PRIOR probability (before this news)? Use the market's recent price \
history if available, or reason from base rates.
2. How NOVEL is this information? (Completely new vs. confirming what was expected)
3. How RELIABLE are the sources? (Official statement vs. "sources say")
4. What is the POSTERIOR probability (after incorporating this news)?
5. How CONFIDENT are you in this estimate?

## Response Format (JSON only)

```json
{{
    "prior_probability": 0.XX,
    "posterior_probability": 0.XX,
    "estimated_shift": 0.XX,
    "confidence": 0.XX,
    "news_type": "NOVEL|CONFIRMATORY|CONTRADICTORY|AMBIGUOUS",
    "source_quality": "VERIFIED|CREDIBLE|UNCONFIRMED|RUMOR",
    "reasoning": "2-3 sentences explaining your estimate."
}}
```

IMPORTANT CALIBRATION NOTES:
- Most news events should shift probabilities by 1-10pp. Shifts >15pp require extraordinary evidence.
- "Sources say" without named officials: discount by 50%.
- Rhetoric without action (threats, ultimatums): 2-5pp max shift.
- Confirmed events (vote passed, strike occurred, data released): can justify 10-30pp shift.
- If the news is CONFIRMATORY (market already expected this), the shift should be near zero.
- Your goal is accuracy, not drama. Boring estimates that are correct beat exciting ones that aren't.
"""


# --- Source Credibility ---

_credibility_cache: list[dict] | None = None


def load_credibility_matrix() -> list[dict]:
    """Load the source credibility matrix from JSON. Cached after first load."""
    global _credibility_cache
    if _credibility_cache is not None:
        return _credibility_cache

    if not CREDIBILITY_PATH.exists():
        logger.warning("Credibility matrix not found at %s", CREDIBILITY_PATH)
        _credibility_cache = []
        return _credibility_cache

    with open(CREDIBILITY_PATH) as f:
        _credibility_cache = json.load(f)
    return _credibility_cache


def _normalize_domain(domain: str) -> str:
    """Normalize a source domain for matching against credibility matrix."""
    d = domain.lower().replace("www.", "")
    # Strip port/path
    d = d.split("/")[0].split(":")[0]
    return d


def lookup_credibility(source_domain: str) -> dict | None:
    """Find credibility entry for a source domain."""
    matrix = load_credibility_matrix()
    norm = _normalize_domain(source_domain)

    for entry in matrix:
        entry_domain = entry.get("url", "")
        # Extract domain from URL
        entry_norm = _normalize_domain(
            entry_domain.replace("https://", "").replace("http://", "")
        )
        if not entry_norm:
            continue
        # Match by substring: "reuters.com" in "reuters.com" or vice versa
        if norm in entry_norm or entry_norm in norm:
            return entry

    return None


def format_source_list(event: NewsEvent) -> str:
    """Format source list with credibility info for the prompt."""
    if not event.articles:
        return "(no articles available)"

    seen_domains: set[str] = set()
    lines: list[str] = []

    for art in event.articles:
        if art.source_domain in seen_domains:
            continue
        seen_domains.add(art.source_domain)

        cred = lookup_credibility(art.source_domain)
        if cred:
            score = cred.get("composite_score", 0)
            # Normalize to 0-1 range (scores are 0-5)
            reliability = score / 5.0
            bias = cred.get("bias_direction", "unknown")
            lines.append(
                f"- {cred.get('source', art.source_domain)} "
                f"(reliability: {reliability:.2f}, lean: {bias}) "
                f"— \"{art.title[:80]}\""
            )
        else:
            lines.append(
                f"- {art.source_domain} (unrated) — \"{art.title[:80]}\""
            )

    return "\n".join(lines) if lines else "(no sources)"


# --- Domain Context ---

def load_domain_context(domain: str) -> str:
    """Load domain context from domains/{domain}/context.md, truncated to ~500 chars."""
    context_path = PROJECT_ROOT / "domains" / domain / "context.md"
    if not context_path.exists():
        return f"(No domain context available for {domain})"

    text = context_path.read_text()
    # Truncate to first ~500 chars to keep prompt size reasonable
    if len(text) > 500:
        text = text[:500] + "\n... (truncated)"
    return text


# --- Prompt Builder ---

def build_prompt(match: MarketMatch) -> str:
    """Build the interpretation prompt from a MarketMatch."""
    event = match.event
    market = match.market

    source_list = format_source_list(event)
    domain_context = load_domain_context(event.domain)

    return INTERPRETATION_PROMPT.format(
        event_summary=event.summary,
        source_count=event.source_count,
        source_list=source_list,
        first_seen=event.first_seen.strftime("%Y-%m-%d %H:%M UTC")
            if isinstance(event.first_seen, datetime) else str(event.first_seen),
        domain=event.domain,
        market_question=market.question,
        current_yes_price=f"{market.yes_price:.2f}",
        current_yes_pct=f"{market.yes_price * 100:.1f}",
        end_date=market.end_date or "Not specified",
        volume_total=market.volume_total,
        volume_24h=market.volume_24h,
        domain_context=domain_context,
    )


# --- LLM Call ---

def call_llm(prompt: str) -> str:
    """Call the Anthropic API. Tries the SDK first, falls back to curl."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except ImportError:
        logger.info("anthropic SDK not installed, falling back to curl")
    except Exception as e:
        logger.error("Anthropic SDK error: %s, falling back to curl", e)

    return _call_llm_curl(prompt)


def _call_llm_curl(prompt: str) -> str:
    """Fallback: call the Anthropic API via curl."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
        "messages": [{"role": "user", "content": prompt}],
    })

    result = subprocess.run(
        [
            "curl", "-s", "https://api.anthropic.com/v1/messages",
            "-H", "Content-Type: application/json",
            "-H", f"x-api-key: {api_key}",
            "-H", "anthropic-version: 2023-06-01",
            "-d", payload,
        ],
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")

    data = json.loads(result.stdout)
    if "content" not in data:
        raise RuntimeError(f"Unexpected API response: {result.stdout[:200]}")

    return data["content"][0]["text"]


# --- Response Parser ---

def parse_llm_response(raw: str) -> dict:
    """Parse JSON from LLM response. Handles markdown code fences."""
    # Strip markdown code fences
    cleaned = raw.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
    if m:
        cleaned = m.group(1).strip()

    data = json.loads(cleaned)

    # Validate required fields
    required = [
        "prior_probability", "posterior_probability", "estimated_shift",
        "confidence", "news_type", "source_quality", "reasoning",
    ]
    for field in required:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    # Validate ranges
    for prob_field in ("prior_probability", "posterior_probability", "confidence"):
        val = float(data[prob_field])
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"{prob_field} must be 0.0-1.0, got {val}")
        data[prob_field] = val

    data["estimated_shift"] = float(data["estimated_shift"])

    # Validate shift consistency (allow small floating-point tolerance)
    expected_shift = data["posterior_probability"] - data["prior_probability"]
    if abs(data["estimated_shift"] - expected_shift) > 0.02:
        logger.warning(
            "Shift mismatch: stated %.3f vs computed %.3f — using computed",
            data["estimated_shift"], expected_shift,
        )
        data["estimated_shift"] = round(expected_shift, 4)

    # Validate enums
    valid_news_types = {"NOVEL", "CONFIRMATORY", "CONTRADICTORY", "AMBIGUOUS"}
    if data["news_type"] not in valid_news_types:
        raise ValueError(f"Invalid news_type: {data['news_type']}")

    valid_source_qualities = {"VERIFIED", "CREDIBLE", "UNCONFIRMED", "RUMOR"}
    if data["source_quality"] not in valid_source_qualities:
        raise ValueError(f"Invalid source_quality: {data['source_quality']}")

    return data


# --- SQLite Store ---

class InterpretationStore:
    """SQLite-backed interpretation storage + rate limiting."""

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
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
            CREATE INDEX IF NOT EXISTS idx_interp_time
                ON s012_interpretations(interpreted_at);
        """)
        self.conn.commit()

    def save(self, interp: Interpretation):
        """Persist an interpretation to SQLite."""
        self.conn.execute("""
            INSERT OR REPLACE INTO s012_interpretations
                (interpretation_id, event_id, market_id, prior_probability,
                 posterior_probability, estimated_shift, confidence,
                 news_type, source_quality, reasoning, model_used,
                 prompt_version, interpreted_at, raw_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            interp.interpretation_id, interp.event_id, interp.market_id,
            interp.prior_probability, interp.posterior_probability,
            interp.estimated_shift, interp.confidence,
            interp.news_type, interp.source_quality, interp.reasoning,
            interp.model_used, interp.prompt_version,
            interp.interpreted_at.isoformat(), interp.raw_llm_response,
        ))
        self.conn.commit()

    def is_on_cooldown(self, event_id: str, market_id: str) -> bool:
        """Check if this event+market pair was interpreted within cooldown."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=COOLDOWN_MINUTES)
        ).isoformat()
        row = self.conn.execute(
            """SELECT 1 FROM s012_interpretations
               WHERE event_id = ? AND market_id = ? AND interpreted_at > ?
               LIMIT 1""",
            (event_id, market_id, cutoff),
        ).fetchone()
        return row is not None

    def count_recent(self, hours: float = 1.0) -> int:
        """Count interpretations in the last N hours."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) FROM s012_interpretations WHERE interpreted_at > ?",
            (cutoff,),
        ).fetchone()
        return row[0] if row else 0

    def load_recent(self, limit: int = 20) -> list[dict]:
        """Load recent interpretations."""
        rows = self.conn.execute("""
            SELECT interpretation_id, event_id, market_id,
                   prior_probability, posterior_probability, estimated_shift,
                   confidence, news_type, source_quality, reasoning,
                   model_used, prompt_version, interpreted_at
            FROM s012_interpretations
            ORDER BY interpreted_at DESC LIMIT ?
        """, (limit,)).fetchall()

        return [
            {
                "interpretation_id": r[0], "event_id": r[1], "market_id": r[2],
                "prior": r[3], "posterior": r[4], "shift": r[5],
                "confidence": r[6], "news_type": r[7], "source_quality": r[8],
                "reasoning": r[9], "model": r[10], "prompt_version": r[11],
                "interpreted_at": r[12],
            }
            for r in rows
        ]

    def load_all_for_calibration(self) -> list[dict]:
        """Load all interpretations for calibration analysis."""
        rows = self.conn.execute("""
            SELECT prior_probability, posterior_probability, estimated_shift,
                   confidence, news_type, source_quality, prompt_version
            FROM s012_interpretations
            ORDER BY interpreted_at
        """).fetchall()

        return [
            {
                "prior": r[0], "posterior": r[1], "shift": r[2],
                "confidence": r[3], "news_type": r[4], "source_quality": r[5],
                "prompt_version": r[6],
            }
            for r in rows
        ]

    def close(self):
        self.conn.close()


# --- JSONL Logger ---

def log_to_jsonl(interp: Interpretation):
    """Append interpretation to JSONL file."""
    JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "interpretation_id": interp.interpretation_id,
        "event_id": interp.event_id,
        "market_id": interp.market_id,
        "market_question": interp.market_question,
        "prior_probability": interp.prior_probability,
        "posterior_probability": interp.posterior_probability,
        "estimated_shift": interp.estimated_shift,
        "confidence": interp.confidence,
        "news_type": interp.news_type,
        "source_quality": interp.source_quality,
        "reasoning": interp.reasoning,
        "model_used": interp.model_used,
        "prompt_version": interp.prompt_version,
        "interpreted_at": interp.interpreted_at.isoformat(),
    }

    with open(JSONL_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


# --- Core Interpret Function ---

def interpret(match: MarketMatch, store: InterpretationStore,
              use_api: bool = True) -> Interpretation | None:
    """Run the full interpretation pipeline for a single MarketMatch.

    Returns None if rate-limited or on cooldown.
    """
    event = match.event
    market = match.market

    # Rate limit check
    if store.count_recent(hours=1.0) >= MAX_INTERPRETATIONS_PER_HOUR:
        logger.warning("Rate limit reached: %d/hr", MAX_INTERPRETATIONS_PER_HOUR)
        return None

    # Cooldown check
    if store.is_on_cooldown(event.event_id, market.market_id):
        logger.info("Cooldown: %s + %s already interpreted recently",
                     event.event_id[:8], market.market_id[:8])
        return None

    # Build prompt
    prompt = build_prompt(match)

    # Call LLM (or use synthetic in demo)
    if use_api:
        raw = call_llm(prompt)
    else:
        raw = _synthetic_response()

    # Parse
    parsed = parse_llm_response(raw)

    now = datetime.now(timezone.utc)
    interp = Interpretation(
        interpretation_id=str(uuid.uuid4()),
        event_id=event.event_id,
        market_id=market.market_id,
        market_question=market.question,
        prior_probability=parsed["prior_probability"],
        posterior_probability=parsed["posterior_probability"],
        estimated_shift=parsed["estimated_shift"],
        confidence=parsed["confidence"],
        reasoning=parsed["reasoning"],
        news_type=parsed["news_type"],
        source_quality=parsed["source_quality"],
        interpreted_at=now,
        model_used=MODEL,
        prompt_version=PROMPT_VERSION,
        raw_llm_response=raw,
    )

    # Persist
    store.save(interp)
    log_to_jsonl(interp)

    return interp


# --- Synthetic Demo ---

def _synthetic_response() -> str:
    """Return a hardcoded synthetic LLM response for demo mode."""
    return json.dumps({
        "prior_probability": 0.35,
        "posterior_probability": 0.42,
        "estimated_shift": 0.07,
        "confidence": 0.65,
        "news_type": "NOVEL",
        "source_quality": "CREDIBLE",
        "reasoning": (
            "The resumption of IAEA inspections represents a modest but real "
            "increase in the probability of a deal, moving from the prior of "
            "35% to 42%. The shift is limited because talks have resumed "
            "before without producing lasting agreements."
        ),
    })


def _make_demo_match() -> MarketMatch:
    """Build a synthetic MarketMatch for demo mode."""
    from news_ingestor import Article, _make_demo_article

    now = datetime.now(timezone.utc)

    articles = [
        _make_demo_article(
            url="https://reuters.com/iran-talks-1",
            title="Iran Nuclear Talks Resume in Geneva as IAEA Pushes for Inspections",
            description="IAEA inspectors demand access to Iranian enrichment facilities.",
            source_name="Reuters",
            source_domain="reuters.com",
            published_at=now - timedelta(minutes=30),
            query_name="iran-nuclear",
        ),
        _make_demo_article(
            url="https://bbc.com/iran-talks-2",
            title="Cautious Optimism as Iran Returns to Negotiating Table",
            description="BBC reports on renewed diplomatic efforts in Geneva.",
            source_name="BBC",
            source_domain="bbc.com",
            published_at=now - timedelta(minutes=20),
            query_name="iran-nuclear",
        ),
        _make_demo_article(
            url="https://presstv.ir/iran-talks-3",
            title="Historic Breakthrough: Iran Shows Willingness to Cooperate",
            description="PressTV hails Iranian diplomatic initiative.",
            source_name="PressTV",
            source_domain="presstv.ir",
            published_at=now - timedelta(minutes=15),
            query_name="iran-nuclear",
        ),
    ]

    event = NewsEvent(
        event_id="demo-evt-001",
        articles=articles,
        key_entities=["Iran", "IAEA", "Geneva", "Nuclear"],
        summary="Iran nuclear talks resume in Geneva as IAEA pushes for inspections",
        domain="GEO",
        is_breaking=True,
        first_seen=now - timedelta(minutes=30),
        source_count=3,
        query_names=["iran-nuclear"],
    )

    market = MarketSnapshot(
        market_id="demo-mkt-001",
        question="Will Iran reach a nuclear deal before July 2026?",
        slug="iran-nuclear-deal-jul-2026",
        yes_price=0.35,
        no_price=0.65,
        volume_24h=45000.0,
        volume_total=1200000.0,
        liquidity=300000.0,
        end_date="2026-07-01T00:00:00Z",
        domain="GEO",
        snapshot_time=now,
        yes_token="tok_demo_yes",
        no_token="tok_demo_no",
    )

    return MarketMatch(
        event=event,
        market=market,
        relevance_score=0.85,
        price_before=0.33,
        price_after=0.35,
        actual_move=0.02,
    )


# --- CLI Commands ---

def cmd_demo():
    """Run a synthetic demo without calling the real API."""
    match = _make_demo_match()

    print("=" * 70)
    print("REACTION INTERPRETER — Demo Mode (no API calls)")
    print("=" * 70)

    print(f"\nEvent: {match.event.summary}")
    print(f"  Domain: {match.event.domain}")
    print(f"  Sources: {match.event.source_count}")
    print(f"  Breaking: {match.event.is_breaking}")

    print(f"\nMarket: {match.market.question}")
    print(f"  YES price: {match.market.yes_price:.1%}")
    print(f"  Volume: ${match.market.volume_total:,.0f}")

    # Show source credibility
    print("\nSource credibility:")
    print(format_source_list(match.event))

    # Show prompt (truncated)
    prompt = build_prompt(match)
    print(f"\nPrompt length: {len(prompt)} chars")

    # Use synthetic response
    store = InterpretationStore()
    interp = interpret(match, store, use_api=False)
    store.close()

    if interp:
        print(f"\n--- Interpretation ---")
        print(f"  Prior:     {interp.prior_probability:.1%}")
        print(f"  Posterior: {interp.posterior_probability:.1%}")
        print(f"  Shift:     {interp.estimated_shift:+.1%}")
        print(f"  Confidence: {interp.confidence:.0%}")
        print(f"  News type: {interp.news_type}")
        print(f"  Source quality: {interp.source_quality}")
        print(f"  Reasoning: {interp.reasoning}")
        print(f"  Model: {interp.model_used} ({interp.prompt_version})")
        print(f"  ID: {interp.interpretation_id}")


def cmd_event(event_id: str):
    """Interpret a specific event from the database."""
    event_store = EventStore()
    recent = event_store.load_recent(hours=168)  # 7 days
    event_store.close()

    target = None
    for ev in recent:
        if ev["event_id"] == event_id or ev["event_id"].startswith(event_id):
            target = ev
            break

    if not target:
        print(f"Event not found: {event_id}")
        print("Use --events on news_ingestor.py to list recent events.")
        return

    # Reconstruct NewsEvent (articles not available from summary)
    event = NewsEvent(
        event_id=target["event_id"],
        articles=[],
        key_entities=target.get("key_entities", []),
        summary=target.get("summary", ""),
        domain=target.get("domain", "OTHER"),
        is_breaking=target.get("is_breaking", False),
        first_seen=datetime.fromisoformat(target["first_seen"])
            if isinstance(target["first_seen"], str)
            else target["first_seen"],
        source_count=target.get("source_count", 0),
        query_names=target.get("query_names", []),
    )

    # Match to markets
    cache = MarketCache()
    snap_store = SnapshotStore()
    matches = match_markets(event, cache, snap_store)

    if not matches:
        print(f"No market matches found for event: {event.summary}")
        snap_store.close()
        return

    print(f"Event: {event.summary}")
    print(f"  Found {len(matches)} market match(es)\n")

    interp_store = InterpretationStore()
    for i, m in enumerate(matches):
        print(f"  [{i+1}] {m.market.question[:70]}")
        print(f"      Relevance: {m.relevance_score:.2f} | YES={m.market.yes_price:.1%}")

        interp = interpret(m, interp_store, use_api=True)
        if interp:
            print(f"      -> Shift: {interp.estimated_shift:+.1%} "
                  f"(prior={interp.prior_probability:.1%} -> "
                  f"posterior={interp.posterior_probability:.1%})")
            print(f"      -> Confidence: {interp.confidence:.0%} | "
                  f"{interp.news_type} | {interp.source_quality}")
            print(f"      -> {interp.reasoning}")
        else:
            print("      -> Skipped (rate limit or cooldown)")
        print()

    interp_store.close()
    snap_store.close()


def cmd_recent():
    """Show recent interpretations."""
    store = InterpretationStore()
    recent = store.load_recent(limit=20)
    store.close()

    if not recent:
        print("No interpretations yet.")
        return

    now = datetime.now(timezone.utc)
    print(f"\n{'=' * 80}")
    print(f"RECENT INTERPRETATIONS — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 80}")
    print(f"  {len(recent)} interpretation(s)\n")

    for r in recent:
        shift_str = f"{r['shift']:+.1%}" if r['shift'] is not None else "N/A"
        conf_str = f"{r['confidence']:.0%}" if r['confidence'] is not None else "N/A"
        print(f"  [{r['news_type']:13s}] Shift: {shift_str:>6s} | "
              f"Conf: {conf_str} | {r['source_quality']}")
        print(f"    Prior: {r['prior']:.1%} -> Post: {r['posterior']:.1%}")
        print(f"    {r['reasoning'][:100]}")
        print(f"    Event: {r['event_id'][:12]}... | Market: {r['market_id'][:12]}...")
        print(f"    At: {r['interpreted_at']} | {r['model']} {r['prompt_version']}")
        print()


def cmd_calibration():
    """Show LLM calibration statistics."""
    store = InterpretationStore()
    all_interps = store.load_all_for_calibration()
    store.close()

    if not all_interps:
        print("No interpretations for calibration. Run --demo or --event first.")
        return

    n = len(all_interps)
    shifts = [r["shift"] for r in all_interps if r["shift"] is not None]
    confidences = [r["confidence"] for r in all_interps if r["confidence"] is not None]

    # News type distribution
    type_counts: dict[str, int] = {}
    for r in all_interps:
        t = r.get("news_type", "UNKNOWN")
        type_counts[t] = type_counts.get(t, 0) + 1

    # Source quality distribution
    quality_counts: dict[str, int] = {}
    for r in all_interps:
        q = r.get("source_quality", "UNKNOWN")
        quality_counts[q] = quality_counts.get(q, 0) + 1

    # Prompt version distribution
    version_counts: dict[str, int] = {}
    for r in all_interps:
        v = r.get("prompt_version", "unknown")
        version_counts[v] = version_counts.get(v, 0) + 1

    print(f"\n{'=' * 60}")
    print("LLM CALIBRATION STATS")
    print(f"{'=' * 60}")
    print(f"  Total interpretations: {n}")

    if shifts:
        avg_shift = sum(abs(s) for s in shifts) / len(shifts)
        max_shift = max(abs(s) for s in shifts)
        pos_shifts = sum(1 for s in shifts if s > 0)
        neg_shifts = sum(1 for s in shifts if s < 0)
        zero_shifts = sum(1 for s in shifts if s == 0)

        print(f"\n  Shift Statistics:")
        print(f"    Avg absolute shift: {avg_shift:.1%}")
        print(f"    Max absolute shift: {max_shift:.1%}")
        print(f"    Positive shifts: {pos_shifts} ({pos_shifts/len(shifts):.0%})")
        print(f"    Negative shifts: {neg_shifts} ({neg_shifts/len(shifts):.0%})")
        print(f"    Zero shifts:     {zero_shifts}")

    if confidences:
        avg_conf = sum(confidences) / len(confidences)
        print(f"\n  Confidence Statistics:")
        print(f"    Avg confidence: {avg_conf:.0%}")
        print(f"    Min: {min(confidences):.0%} | Max: {max(confidences):.0%}")

    print(f"\n  News Type Distribution:")
    for t, c in sorted(type_counts.items()):
        print(f"    {t:14s}: {c:>4d} ({c/n:.0%})")

    print(f"\n  Source Quality Distribution:")
    for q, c in sorted(quality_counts.items()):
        print(f"    {q:14s}: {c:>4d} ({c/n:.0%})")

    print(f"\n  Prompt Versions:")
    for v, c in sorted(version_counts.items()):
        print(f"    {v}: {c} interpretations")

    print()


# --- Main ---

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    args = sys.argv[1:]
    if "--demo" in args:
        cmd_demo()
    elif "--event" in args:
        idx = args.index("--event")
        eid = args[idx + 1] if idx + 1 < len(args) else ""
        if not eid:
            print("Usage: --event <event_id>")
            sys.exit(1)
        cmd_event(eid)
    elif "--recent" in args:
        cmd_recent()
    elif "--calibration" in args:
        cmd_calibration()
    else:
        print(__doc__)
        sys.exit(0)


if __name__ == "__main__":
    main()
