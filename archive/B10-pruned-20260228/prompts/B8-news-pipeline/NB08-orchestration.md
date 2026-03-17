# NB08: Orchestration, State & Delivery
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Context
[Paste NB01 + all module summaries here]

## Full Pipeline Execution Flow
```
Every N minutes (per query config):
  BravePoller.poll(query) → articles (parallel by country)
  ToneEntityExtractor.enrich(articles)
  PerspectiveTagger.tag(articles)
  EventClusterer.cluster(articles, existing_clusters)
  
  For each new/updated cluster where is_divergent=True:
    TruthExtractor.extract(cluster)
    SignalGenerator.generate(extraction)
    
  Deliver pending signals

Continuously:
  Monitor signal status (pending → executed/rejected)
  Log outcomes for calibration
```

## Requirements

1. **Orchestrator class**:
   - `run()` — main blocking loop
   - `tick(query: QueryConfig)` — single poll cycle for one query
   - Async-capable (parallel country requests)
   - Graceful shutdown on SIGTERM/SIGINT → finish current tick, exit clean

2. **Complete SQLite schema** (`schema.sql`):
   Tables:
   - `articles`: url, title, source_domain, country_queried, tone, geo_cluster, cluster_id, published_at, fetched_at
   - `clusters`: cluster_id, summary, created, updated, article_count, divergence_score, is_divergent, state (active|archived)
   - `extractions`: cluster_id, result_json, model_used, extracted_at, requires_human_review
   - `signals`: all GeneratedSignal fields + outcome + resolved_at
   - `poll_state`: query_name, last_poll_time, articles_seen_count
   - `request_budget`: date, request_count, cost_estimate
   Include indexes for: cluster_id, published_at, is_divergent, status

3. **Config file** (`config.yaml`):
   ```yaml
   brave:
     api_key: ${BRAVE_API_KEY}
     max_requests_per_month: 900   # leave 100 buffer from 1000 free

   queries:
     - name: iran_nuclear
       keywords: ["Iran", "nuclear", "IAEA", "enrichment", "Geneva talks"]
       boolean_mode: OR
       countries: [US, GB, RU, IR, QA, IL]
       freshness: pd
       count_per_country: 15
       interval_minutes: 30
       extra_snippets: true

     - name: us_politics
       keywords: ["Trump", "Congress", "Senate", "executive order", "tariff"]
       boolean_mode: OR
       countries: [US, GB, CN, RU]
       freshness: pd
       count_per_country: 20
       interval_minutes: 30

     - name: markets_macro
       keywords: ["Federal Reserve", "interest rate", "inflation", "GDP", "recession"]
       boolean_mode: OR
       countries: [US, GB, DE, CN]
       freshness: pd
       count_per_country: 15
       interval_minutes: 60

   pipeline:
     divergence_threshold: 3.0
     max_extractions_per_hour: 20
     max_pending_signals: 3
     cluster_expiry_hours: 72
     yes_discount_factor: 0.85

   delivery:
     channel: telegram
     signal_format: full
   ```

4. **Delivery message format** (Telegram via OpenClaw):
   ```
   🔔 SIGNAL — {market_question}

   Direction: {YES/NO} | Edge: {edge:+.1%} | Confidence: {confidence:.0%}
   Size: ${kelly_usdc:.0f} USDC (Kelly {kelly_fraction:.2f})
   Strategy: {strategy_code}

   Truth kernel:
   {objective_kernel}

   Perspective split:
   Western {western_tone:+.1f} | Russian {russian_tone:+.1f} | Iranian {iranian_tone:+.1f}
   Divergence: {divergence_score:.1f} | Sources: {n} articles, {n_countries} countries

   Reply A=Approve  R=Reject  I=More info
   ```

5. **Approval handler** (stretch goal):
   - Parse reply from Yu (A/R/I)
   - On A: update signal status → approved, log timestamp
   - On R: update status → rejected, log reason if provided
   - On I: send full cluster detail (all articles + full extraction)

6. **Error handling**:
   - Each stage wrapped in try/except with structured logging
   - Circuit breaker: Brave fails 3× consecutively → pause 30 min + alert
   - Dead letter queue for failed extractions

7. **Deployment**:
   - `Dockerfile` (Python 3.12, slim)
   - `docker-compose.yml` with SQLite volume mount
   - `.env.example` with all required env vars
   - `systemd` service file for always-on deployment

## Output
`orchestrator.py` + `config.yaml` + `schema.sql` + `Dockerfile` + `docker-compose.yml` + `.env.example`
