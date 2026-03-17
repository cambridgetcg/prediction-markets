# NB10: Pipeline Wiring, Integration Testing & End-to-End Validation
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Implementation Status (as of 2026-02-27)

All core modules built and unit-tested (148/148 tests pass):

| Module | File | Tests | Status |
|--------|------|-------|--------|
| NB02 Ingestor | `scripts/brave_ingestor.py` | `test_brave_ingestor.py` (36 tests) | ✅ |
| NB03 Tone/Entity | `scripts/tone_entity_extractor.py` | `test_tone_entity_extractor.py` (21 tests) | ✅ |
| NB04 Perspective | `scripts/perspective_matrix.py` | `test_perspective_matrix.py` (14 tests) | ✅ |
| NB05 Clustering | `scripts/event_clusterer.py` | `test_event_clusterer.py` (19 tests) | ✅ |
| NB06 Truth Extract | `scripts/truth_extractor.py` | `test_truth_extractor.py` (30 tests) | ✅ |
| NB07 Signal Gen | `scripts/signal_generator.py` | inline `--test` (28 tests) | ✅ |
| NB08 Orchestrator | `scripts/orchestrator.py` | — | ✅ Code complete, NO TESTS |
| Schema | `scripts/schema.sql` | — | ✅ |
| Config | `config/news-pipeline.yaml` | — | ✅ |
| Source Bias | `sources/source_bias.json` (200+ entries) | — | ✅ |
| Truth Prompt | `prompts/truth_extraction_brave.txt` | — | ✅ |
| Deploy | `deploy/` (Dockerfile, compose, systemd, .env) | — | ✅ |

### What's Missing

1. **NB09: Calibration engine** — `calibration_engine.py`, `collect_outcomes.py`, `weekly_calibration_brave.md`
2. **Orchestrator tests** — `test_orchestrator.py`
3. **Signal generator pytest file** — `test_signal_generator.py` (currently inline only)
4. **Integration test** — full pipeline end-to-end with mocked APIs
5. **Live smoke test** — `orchestrator.py --once` against real Brave API
6. **Delivery wiring** — OpenClaw Telegram integration (currently webhook-only)
7. **Approval handler** — parsing A/R/I replies from Telegram

## Current Architecture

```
scripts/
├── brave_ingestor.py           NB02 — Brave News API poller
├── tone_entity_extractor.py    NB03 — LLM/heuristic tone + entity extraction
├── perspective_matrix.py       NB04 — Source bias tagger + perspective matrix
├── event_clusterer.py          NB05 — Entity-overlap clustering + SQLite
├── truth_extractor.py          NB06 — LLM truth triangulation
├── signal_generator.py         NB07 — Polymarket matching + Kelly sizing
├── orchestrator.py             NB08 — Main loop wiring all stages
├── schema.sql                  Complete SQLite schema
├── test_brave_ingestor.py      36 tests ✅
├── test_tone_entity_extractor.py  21 tests ✅
├── test_perspective_matrix.py  14 tests ✅
├── test_event_clusterer.py     19 tests ✅
└── test_truth_extractor.py     30 tests ✅

config/news-pipeline.yaml       5 query configs, pipeline params, delivery settings
sources/source_bias.json        200+ domain bias entries
prompts/truth_extraction_brave.txt  LLM truth extraction prompt template
deploy/                         Dockerfile, docker-compose, systemd, .env.example
data/news-pipeline.db           SQLite (articles, clusters, extractions, signals, poll_state, dead_letters)
```

Import chain: `orchestrator.py` imports all modules. Each module imports its upstream dependency:
```
orchestrator → brave_ingestor, tone_entity_extractor, perspective_matrix,
               event_clusterer, truth_extractor, signal_generator
signal_generator → truth_extractor, event_clusterer
truth_extractor → event_clusterer, perspective_matrix
event_clusterer → brave_ingestor, perspective_matrix
perspective_matrix → (standalone, defines Article locally)
tone_entity_extractor → brave_ingestor (Article)
```

**Key design note**: `perspective_matrix.py` defines its own `Article` dataclass
separately from `brave_ingestor.py`. The orchestrator uses the `brave_ingestor.Article`
everywhere. This works because `perspective_matrix.PerspectiveTagger.tag()` operates
on duck-typed objects (any object with `.source_domain`, `.country_queried` attributes).
The integration test must verify this cross-module compatibility.

## Your Task

### Part 1: Integration Test (`test_integration_pipeline.py`)

Write a comprehensive end-to-end integration test that exercises the full pipeline
without making real API calls. Mock at boundaries (Brave HTTP, Anthropic API),
exercise everything in between with real code.

**10 test scenarios:**

```python
class TestFullPipelineIntegration:
    """End-to-end: mock Brave → ingest → enrich → tag → cluster → extract → signal."""

    def setup_method(self):
        """Fresh temp DB + fresh module instances for each test."""

    # 1. Single divergent event → signal generated
    def test_divergent_iran_event_produces_signal(self):
        """
        Mock: 6 Brave responses (US/GB/RU/SA/TR/IN) for "Iran nuclear"
              Western articles tone=-2, Russian articles tone=+2
        Assert: 1 cluster, is_divergent=True, truth extraction called, ≥1 signal
        """

    # 2. Non-divergent event → no extraction
    def test_non_divergent_event_skips_extraction(self):
        """
        Mock: Articles with similar tone across all countries
        Assert: Cluster created, is_divergent=False, truth extractor NOT called
        """

    # 3. Multiple events → correct clustering
    def test_multiple_events_cluster_separately(self):
        """
        Mock: 2 distinct topics (Iran + Ukraine) in same poll
        Assert: 2 separate clusters, each with correct articles
        """

    # 4. Budget exhaustion → graceful stop
    def test_budget_exhaustion_stops_polling(self):
        """
        Mock: Budget tracker at 899/900
        Assert: Poller refuses to poll, returns []
        """

    # 5. Circuit breaker trips
    def test_circuit_breaker_after_3_failures(self):
        """
        Mock: Brave API returns 500 for 3 consecutive polls
        Assert: Circuit breaker trips, next tick skipped
        """

    # 6. Low edge → signal rejected
    def test_low_edge_signal_rejected(self):
        """
        Mock: Extraction with probability_shift=0.02
        Assert: Signal generator rejects (edge < 0.05 MIN_EDGE)
        """

    # 7. R01 correlation → signal rejected
    def test_r01_blocks_concentrated_signal(self):
        """
        Mock: Portfolio has GEO positions at cap, new signal adds more GEO
        Assert: R01 blocks signal generation
        """

    # 8. Dead letter queue on failure
    def test_failed_extraction_goes_to_dead_letter(self):
        """
        Mock: Anthropic API raises exception
        Assert: Dead letter entry in DB with stage='extraction'
        """

    # 9. Article dedup across polls
    def test_duplicate_articles_not_reprocessed(self):
        """
        Mock: Same articles returned in two consecutive polls
        Assert: 0 new articles on second poll
        """

    # 10. Full orchestrator tick
    def test_orchestrator_tick_wires_all_stages(self):
        """
        Mock: Full orchestrator with all mocks, tick() once
        Assert: articles table has rows, clusters table has rows,
                signals in DB, all stages executed in order
        """
```

**Mock fixtures:**

```python
MOCK_BRAVE_WESTERN = {
    "type": "news",
    "results": [
        {
            "title": "Iran nuclear talks stall as Western diplomats push",
            "url": "https://reuters.com/iran-talks-stall-123",
            "description": "IAEA demands full inspection access to undeclared sites",
            "age": "2 hours ago",
            "source": {"name": "Reuters", "url": "https://reuters.com"},
            "extra_snippets": ["US threatens new sanctions by March"]
        },
        # 4+ more articles per country, negative tone for Western
    ]
}

MOCK_BRAVE_RUSSIAN = {
    "results": [
        {
            "title": "Iran rightfully defends nuclear sovereignty against Western pressure",
            "url": "https://rt.com/iran-sovereignty-456",
            "description": "Tehran says Western demands violate NPT rights",
            "age": "1 hour ago",
            "source": {"name": "RT", "url": "https://rt.com"},
            "extra_snippets": []
        },
        # articles with pro-Iran/positive tone
    ]
}

MOCK_LLM_EXTRACTION_RESPONSE = json.dumps({
    "consensus_facts": ["Talks occurred in Geneva", "No deal reached"],
    "contested_claims": [
        {"claim": "Iran accelerating enrichment",
         "western_view": "IAEA confirmed",
         "russian_view": "Western fabrication",
         "resolution": "likely_true"}
    ],
    "motivated_omissions": {
        "Western": "Not mentioning previous US deal violations",
        "Russian": "Not mentioning Iran IAEA non-compliance record"
    },
    "objective_kernel": "Geneva talks ended without agreement. IAEA inspection access remains key sticking point.",
    "market_relevance": [
        {"category": "GEO", "description": "US or Israel military strike on Iran",
         "direction": "NO", "probability_shift": -0.08, "confidence": 0.65,
         "key_uncertainty": "Next round of talks"}
    ],
    "overall_confidence": 0.72
})
```

**Test infrastructure:**
- `tempfile.NamedTemporaryFile(suffix='.db')` for SQLite (fresh per test)
- `unittest.mock.patch` for Brave HTTP and Anthropic API
- Each test gets fresh module instances (no cross-test state)
- Assert DB state after each scenario (query articles/clusters/signals tables)
- Use `brave_ingestor.Article` dataclass throughout (not perspective_matrix.Article)

### Part 2: Orchestrator Unit Tests (`test_orchestrator.py`)

```python
class TestPipelineConfig:
    def test_load_valid_config(self):
    def test_env_var_substitution(self):
    def test_missing_config_raises(self):
    def test_query_config_defaults(self):

class TestCircuitBreaker:
    def test_trips_after_threshold(self):
    def test_resets_after_pause(self):
    def test_success_resets_counter(self):
    def test_is_open_before_pause_elapsed(self):
    def test_minutes_until_reset(self):

class TestFormatSignalMessage:
    def test_all_fields_present(self):
    def test_with_extraction_kernel(self):
    def test_with_perspective_split(self):
    def test_without_optional_fields(self):
    def test_approve_reject_prompt_included(self):

class TestPersistSignal:
    def test_inserts_to_signals_table(self):
    def test_upsert_on_duplicate(self):
    def test_all_fields_stored(self):

class TestPersistExtraction:
    def test_inserts_and_returns_id(self):
    def test_json_fields_stored_correctly(self):

class TestDeadLetter:
    def test_writes_to_dead_letter_queue(self):
    def test_stage_and_error_stored(self):

class TestPollState:
    def test_tracks_last_poll_time(self):
    def test_increments_article_count(self):
    def test_upsert_on_second_poll(self):
```

### Part 3: Signal Generator Pytest File (`test_signal_generator.py`)

Extract the inline `--test` logic into proper pytest, then add:

```python
class TestB05:
    # (migrate from inline --test)

class TestStrategyRouting:
    # (migrate from inline --test)

class TestStrategyEdge:
    # (migrate from inline --test)

class TestKellySizing:
    # (migrate from inline --test)

class TestR01:
    # (migrate from inline --test)

class TestTokenizer:
    # (migrate from inline --test)

# NEW tests:
class TestSearchActiveMarkets:
    """Mock Gamma API calls."""
    def test_returns_matched_markets(self):
    def test_empty_description_returns_empty(self):
    def test_no_api_results_returns_empty(self):
    def test_score_ranking_by_match_then_volume(self):

class TestGenerateSignal:
    """Full generate() with mocked market search."""
    def test_generates_signal_for_valid_extraction(self):
    def test_yes_discount_applied_for_yes_direction(self):
    def test_no_discount_not_applied_for_no_direction(self):
    def test_edge_below_threshold_returns_empty(self):
    def test_max_pending_blocks_new_signals(self):
    def test_no_market_match_returns_empty(self):
    def test_r01_rejection_returns_empty(self):
    def test_signal_logged_to_jsonl(self):
```

### Part 4: Live Smoke Test (`smoke_test.py`)

Real Brave API (2 requests), mocked LLM. Verify end-to-end data flow:

```python
#!/usr/bin/env python3
"""Smoke test: real Brave API, mocked LLM, all stages verified.
Cost: 2 Brave API requests (~$0.01)
Time: <30 seconds
"""

def smoke_test():
    # 1. Poll Brave (real, 1 query "Iran nuclear", 2 countries US+GB = 2 requests)
    #    Assert: articles returned with title, url, source_domain
    #    Assert: budget tracker incremented by 2

    # 2. Tone extraction (heuristic mode — --no-llm, zero cost)
    #    Assert: every article has tone (float) and entities (list)

    # 3. Perspective tagging
    #    Assert: every article has geo_cluster, lean, reliability

    # 4. Event clustering
    #    Assert: ≥1 cluster created
    #    Assert: cluster has key_entities and event_summary

    # 5. Truth extraction (MOCK — inject canned response)
    #    Assert: result has consensus_facts, objective_kernel, market_relevance

    # 6. Signal generation (MOCK market search — deterministic)
    #    Assert: signal generated or properly rejected with reason logged

    # 7. Message formatting
    #    Assert: formatted message contains Direction, Edge, Kelly, Truth kernel

    # 8. SQLite verification
    #    Assert: articles table populated, clusters table has rows

    print("✅ Smoke test passed — pipeline end-to-end verified")
    print(f"   Articles: {n_articles}, Clusters: {n_clusters}")
    print(f"   Budget used: +2 requests")
```

### Part 5: Delivery Wiring Update

Update `orchestrator.py` to support file-based delivery for OpenClaw heartbeat pickup:

```python
PENDING_SIGNALS_FILE = PROJECT_ROOT / "data" / "pending-signals.json"

def queue_for_delivery(signal: GeneratedSignal, message: str):
    """Write signal to pending file for OpenClaw heartbeat pickup."""
    pending = json.loads(PENDING_SIGNALS_FILE.read_text()) if PENDING_SIGNALS_FILE.exists() else []
    pending.append({
        "signal_id": signal.signal_id,
        "message": message,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "delivered": False,
    })
    PENDING_SIGNALS_FILE.write_text(json.dumps(pending, indent=2))
```

Add signal ID tag in delivery messages:
```
🔔 SIGNAL [SIG-{signal_id}] — {market_question}
...
Reply A=Approve R=Reject I=Info (ref: SIG-{signal_id})
```

Add approval handler:
```python
def handle_approval(signal_id: str, action: str, conn: sqlite3.Connection) -> str:
    """Process A/R/I reply. Returns response message."""
    now = datetime.now(timezone.utc).isoformat()
    if action.upper() == 'A':
        conn.execute("UPDATE signals SET status='approved' WHERE signal_id=?", (signal_id,))
        conn.commit()
        # Fetch market link
        row = conn.execute("SELECT market_id, market_question, kelly_usdc, direction FROM signals WHERE signal_id=?", (signal_id,)).fetchone()
        return f"✅ Approved SIG-{signal_id}.\nExecute: {row[1]}\nSize: ${row[2]:.0f} {row[3]}\nhttps://polymarket.com/event/{row[0]}"
    elif action.upper() == 'R':
        conn.execute("UPDATE signals SET status='rejected' WHERE signal_id=?", (signal_id,))
        conn.commit()
        return f"❌ Rejected SIG-{signal_id}."
    elif action.upper() == 'I':
        # Fetch full extraction details
        row = conn.execute(
            "SELECT e.objective_kernel, e.consensus_facts, e.contested_claims "
            "FROM signals s JOIN extractions e ON s.cluster_id = e.cluster_id "
            "WHERE s.signal_id=? ORDER BY e.extracted_at DESC LIMIT 1",
            (signal_id,)
        ).fetchone()
        if row:
            return f"📋 Details for SIG-{signal_id}:\n\nKernel: {row[0]}\nFacts: {row[1]}\nContested: {row[2]}"
        return f"No extraction data found for SIG-{signal_id}."
```

### Part 6: HEARTBEAT.md Signal Check Addition

Add this section to HEARTBEAT.md:
```markdown
## Pipeline Signals
- Check `~/Desktop/prediction-markets/data/pending-signals.json`
- If undelivered signals exist:
  1. Send each via Telegram
  2. Mark as delivered in the JSON file
- Check `~/Desktop/prediction-markets/data/signals.jsonl` tail for any recent signals
```

## Output

1. `scripts/test_integration_pipeline.py` — 10 integration scenarios
2. `scripts/test_orchestrator.py` — orchestrator component tests
3. `scripts/test_signal_generator.py` — pytest version of signal gen tests + new tests
4. `scripts/smoke_test.py` — live smoke test (2 API calls, <30s)
5. Updated `scripts/orchestrator.py` — file delivery, signal ID tags, approval handler
6. HEARTBEAT.md signal check section

All tests must pass: `python3 -m pytest scripts/test_*.py -v`
Smoke test must pass: `python3 scripts/smoke_test.py`
