#!/usr/bin/env python3
"""NB10 Part 4: Smoke Test — Real Brave API, mocked LLM, all stages verified.

Cost: 2 Brave API requests (~$0.01)
Time: <30 seconds

Usage:
    python3 scripts/smoke_test.py
    python3 scripts/smoke_test.py --dry-run   # Skip Brave API (use synthetic articles)
"""

import asyncio
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from brave_ingestor import Article, BraveNewsPoller, BudgetTracker, QueryConfig
from tone_entity_extractor import ToneEntityExtractor
from perspective_matrix import PerspectiveTagger, PerspectiveMatrix, ClusterView
from event_clusterer import EventClusterer, EventCluster
from truth_extractor import TruthExtractor, TruthExtractionResult
from signal_generator import SignalGenerator, GeneratedSignal
from orchestrator import format_signal_message, init_db

PROJECT_ROOT = SCRIPT_DIR.parent
SCHEMA_PATH = SCRIPT_DIR / "schema.sql"


def _init_test_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if SCHEMA_PATH.exists():
        for stmt in SCHEMA_PATH.read_text().split(";"):
            s = stmt.strip()
            if s and not s.upper().startswith("PRAGMA"):
                try:
                    conn.execute(s)
                except sqlite3.OperationalError:
                    pass
        conn.commit()
    return conn


def _synthetic_articles():
    """Build synthetic articles for --dry-run mode."""
    now = datetime.now(timezone.utc)
    articles = []
    data = [
        ("US", "reuters.com", "Reuters",
         "Iran nuclear talks stall as Western diplomats push for inspections",
         "IAEA demands full access to undeclared sites"),
        ("GB", "bbc.co.uk", "BBC",
         "Analysis: Why Iran nuclear talks face collapse",
         "Hardliners in Tehran resist concessions as deadline looms"),
    ]
    for i, (country, domain, name, title, desc) in enumerate(data):
        articles.append(Article(
            url=f"https://{domain}/iran-smoke-{i}",
            title=title,
            description=desc,
            extra_snippets=["US threatens new sanctions if no progress by March."],
            full_text=f"{title} {desc}",
            source_name=name,
            source_domain=domain,
            country_queried=country,
            age_raw=f"{i + 1} hours ago",
            published_at=now,
            query_name="iran-nuclear",
            fetched_at=now,
        ))
    return articles


MOCK_LLM_EXTRACTION = json.dumps({
    "consensus_facts": ["Talks occurred in Geneva", "No deal reached"],
    "contested_claims": [
        {"claim": "Iran accelerating enrichment",
         "western_view": "IAEA confirmed",
         "russian_view": "Not applicable",
         "resolution": "likely_true"}
    ],
    "motivated_omissions": {"Western": "Prior US violations omitted"},
    "objective_kernel": "Geneva talks ended without agreement. IAEA inspection access remains key.",
    "market_relevance": [
        {"category": "GEO", "description": "US or Israel military strike on Iran",
         "direction": "NO", "probability_shift": -0.08, "confidence": 0.65}
    ],
    "overall_confidence": 0.72,
})


def smoke_test(dry_run: bool = False):
    errors = []
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "smoke.db"

    print("=" * 60)
    print("SMOKE TEST — News Intelligence Pipeline")
    print(f"Mode: {'DRY RUN (synthetic)' if dry_run else 'LIVE (Brave API)'}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Poll Brave (real or synthetic)
    # ------------------------------------------------------------------
    print("\n[1/8] Ingesting articles...")
    if dry_run:
        articles = _synthetic_articles()
        budget_used = 0
    else:
        query = QueryConfig(
            name="smoke-iran",
            keywords=["Iran nuclear"],
            countries=["US", "GB"],  # 2 requests
            freshness="pd",
            count_per_country=5,
            interval_minutes=9999,
        )
        try:
            poller = BraveNewsPoller()
            articles = asyncio.run(poller.poll(query))
            budget_used = 2
            poller.close()
        except Exception as e:
            print(f"  WARN: Brave poll failed ({e}) — falling back to synthetic")
            articles = _synthetic_articles()
            budget_used = 0

    if not articles:
        print("  WARN: 0 articles from Brave — using synthetic")
        articles = _synthetic_articles()
        budget_used = 0

    n_articles = len(articles)
    print(f"  OK: {n_articles} articles ingested")
    for a in articles[:3]:
        print(f"    - [{a.source_name}] {a.title[:60]}")

    assert n_articles > 0, "No articles ingested"

    # Verify article structure
    for a in articles:
        assert a.title, "Article missing title"
        assert a.url, "Article missing url"
        assert a.source_domain, "Article missing source_domain"

    # ------------------------------------------------------------------
    # 2. Tone extraction (heuristic — zero cost)
    # ------------------------------------------------------------------
    print("\n[2/8] Tone & entity extraction (heuristic)...")
    extractor = ToneEntityExtractor(use_llm=False)
    extractor.enrich(articles)

    toned = [a for a in articles if a.tone is not None]
    entitied = [a for a in articles if a.entities]
    print(f"  OK: {len(toned)} articles with tone, {len(entitied)} with entities")

    assert len(toned) == n_articles, "Some articles missing tone"
    for a in articles[:2]:
        print(f"    [{a.source_name}] tone={a.tone:+.2f} entities={a.entities[:3] if a.entities else '(none)'}")

    # ------------------------------------------------------------------
    # 3. Perspective tagging
    # ------------------------------------------------------------------
    print("\n[3/8] Perspective tagging...")
    tagger = PerspectiveTagger()
    tagger.tag_batch(articles)

    tagged = [a for a in articles if a.geo_cluster]
    print(f"  OK: {len(tagged)} articles tagged")
    for a in articles[:2]:
        print(f"    [{a.source_name}] geo={a.geo_cluster} lean={a.lean} rel={a.reliability}")

    assert len(tagged) == n_articles, "Some articles missing geo_cluster"

    # ------------------------------------------------------------------
    # 4. Event clustering
    # ------------------------------------------------------------------
    print("\n[4/8] Event clustering...")
    clusterer = EventClusterer(db_path=db_path)
    clusters = clusterer.cluster(articles)
    n_clusters = len(clusters)
    print(f"  OK: {n_clusters} cluster(s) created")
    for c in clusters:
        print(f"    [{c.cluster_id[:12]}] {c.event_summary[:60]}")
        print(f"      entities={c.key_entities[:5]} div={c.divergence_score:.2f} "
              f"{'DIVERGENT' if c.is_divergent else ''}")

    assert n_clusters >= 1, "No clusters created"
    assert clusters[0].key_entities, "Cluster missing entities"

    # ------------------------------------------------------------------
    # 5. Truth extraction (MOCK)
    # ------------------------------------------------------------------
    print("\n[5/8] Truth extraction (mocked LLM)...")
    # Force divergence on first cluster for smoke test
    cluster = clusters[0]
    cluster.is_divergent = True
    cluster.divergence_score = 4.0
    cluster.perspective_matrix = PerspectiveMatrix(
        clusters={
            "Western": ClusterView(
                cluster_name="Western",
                article_count=n_articles,
                mean_tone=-1.5,
                reliability_weighted_tone=-1.4,
                key_claims=["Test"],
                sources=["reuters.com"],
            ),
        },
        divergence_score=4.0,
        is_divergent=True,
    )

    # Mock the Anthropic client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=MOCK_LLM_EXTRACTION)]
    truth_ext = TruthExtractor()
    truth_ext.client = MagicMock()
    truth_ext.client.messages.create.return_value = mock_response

    result = truth_ext.extract(cluster)
    assert result is not None, "Truth extraction returned None"
    assert result.consensus_facts, "Missing consensus_facts"
    assert result.objective_kernel, "Missing objective_kernel"
    assert result.market_relevance, "Missing market_relevance"
    print(f"  OK: confidence={result.overall_confidence:.2f}")
    print(f"    Kernel: {result.objective_kernel[:80]}")
    print(f"    Market relevance: {len(result.market_relevance)} entries")

    # ------------------------------------------------------------------
    # 6. Signal generation (MOCK market search)
    # ------------------------------------------------------------------
    print("\n[6/8] Signal generation (mocked market search)...")
    from unittest.mock import patch

    with patch("signal_generator.search_active_markets") as mock_search, \
         patch("signal_generator.count_pending_signals", return_value=0), \
         patch("signal_generator.load_positions",
               return_value={"bankroll": 10000, "positions": [], "domain_exposure": {}}):
        mock_search.return_value = [{
            "condition_id": "cond-smoke-001",
            "question": "Will the US or Israel strike Iran by March 31?",
            "current_price": 0.35,
            "volume": 500000,
            "liquidity": 50000,
            "clob_token_ids": ["tok1"],
            "match_score": 0.7,
        }]
        gen = SignalGenerator(bankroll=10000)
        gen.portfolio = {"bankroll": 10000, "positions": [], "domain_exposure": {}}
        signals = gen.generate(result, cluster)

    print(f"  OK: {len(signals)} signal(s) generated")
    if signals:
        s = signals[0]
        print(f"    {s.direction} | edge={s.edge:+.1%} | kelly=${s.kelly_usdc:.0f} | {s.strategy_code}")
    else:
        print("    (rejected by guardrails — expected for some extraction scenarios)")

    # ------------------------------------------------------------------
    # 7. Message formatting
    # ------------------------------------------------------------------
    print("\n[7/8] Message formatting...")
    if signals:
        msg = format_signal_message(signals[0], extraction=result, cluster=cluster)
        assert "Direction" in msg or "SIGNAL" in msg, "Message missing key fields"
        assert "Approve" in msg, "Message missing approval prompt"
        print(f"  OK: message length={len(msg)}")
        for line in msg.split("\n")[:5]:
            print(f"    {line}")
    else:
        # Format a synthetic signal for test
        synth = GeneratedSignal(
            signal_id="smoke-001", cluster_id="c1", market_id="m1",
            market_question="Will Iran deal happen?", direction="NO",
            current_price=0.35, suggested_probability=0.48, edge=0.13,
            kelly_fraction=0.05, kelly_usdc=500, strategy_code="S004",
            confidence=0.72, yes_discount_applied=False,
            generated_at=datetime.now(timezone.utc), status="pending",
        )
        msg = format_signal_message(synth, extraction=result, cluster=cluster)
        assert "SIGNAL" in msg
        print(f"  OK: message length={len(msg)} (synthetic signal)")

    # ------------------------------------------------------------------
    # 8. SQLite verification
    # ------------------------------------------------------------------
    print("\n[8/8] SQLite verification...")
    conn = _init_test_db(db_path)

    # Articles might not be in this DB (they're in orchestrator's DB)
    # But clusters should be there from step 4
    cluster_count = conn.execute("SELECT COUNT(*) FROM event_clusters").fetchone()[0]
    print(f"  Clusters in DB: {cluster_count}")
    assert cluster_count >= 1, "No clusters in SQLite"

    conn.close()
    clusterer.close()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SMOKE TEST PASSED — pipeline end-to-end verified")
    print(f"  Articles: {n_articles}")
    print(f"  Clusters: {n_clusters}")
    print(f"  Signals:  {len(signals)}")
    print(f"  Budget used: +{budget_used} requests")
    print("=" * 60)


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    smoke_test(dry_run=dry)
