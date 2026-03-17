# Module 7: Orchestrator

## Task

Build `scripts/s012/orchestrator.py` — the main loop that chains all S012 modules together and can run as a daemon or one-shot.

## Context

This is the glue. It connects:
1. News Ingestor (Module 1) → detects events
2. Market Snapshot (Module 2) → matches events to markets, captures prices
3. Reaction Interpreter (Module 3) → LLM estimates rational shift
4. Reaction Comparator (Module 4) → classifies over/underreaction
5. Signal Generator (Module 5) → produces trading signals
6. Paper Logger (Module 6) → tracks paper trades

## Requirements

### Main Loop

```python
async def tick(config: Config) -> list[TradingSignal]:
    """Single tick of the S012 pipeline. Called by scheduler or manually."""
    
    # Stage 1: Fetch news
    ingestor = NewsIngestor(config)
    events = await ingestor.poll()
    
    if not events:
        logger.info("No new events")
        return []
    
    # Stage 2: Match events to markets
    snapper = MarketSnapshot(config)
    await snapper.refresh_market_cache()
    
    matches = []
    for event in events:
        event_matches = snapper.match_event(event)
        if event_matches:
            # Take snapshot at this moment (the "after" price)
            for match in event_matches:
                snapper.store_snapshot(match.market, trigger_event_id=event.event_id)
            matches.extend(event_matches)
    
    if not matches:
        logger.info(f"{len(events)} events, but no market matches")
        return []
    
    # Stage 3: Interpret each match
    interpreter = ReactionInterpreter(config)
    interpretations = []
    for match in matches:
        if match.actual_move is None:
            # No pre-news snapshot → can't compute delta → skip
            logger.info(f"No pre-news snapshot for {match.market.market_id}, skipping")
            continue
        if abs(match.actual_move) < 0.03:
            # Move too small to be interesting
            continue
        
        interp = await interpreter.interpret(match)
        if interp:
            interpretations.append((match, interp))
    
    if not interpretations:
        logger.info(f"{len(matches)} matches, but no interpretable moves")
        return []
    
    # Stage 4: Compare and classify
    comparator = ReactionComparator(config)
    assessments = []
    for match, interp in interpretations:
        assessment = comparator.assess(interp, match)
        assessments.append(assessment)
    
    # Stage 5: Generate signals (only for actionable assessments)
    generator = SignalGenerator(config)
    signals = []
    for assessment in assessments:
        if assessment.is_actionable:
            signal = generator.generate(assessment)
            if signal:
                signals.append(signal)
    
    # Stage 6: Check open paper trades
    paper_logger = PaperLogger(config)
    paper_logger.check_open_trades()
    
    # Deliver signals
    for signal in signals:
        deliver_signal(signal, config)
    
    return signals
```

### Scheduling

Two modes:

**One-shot** (`--once`): Run a single tick, print results, exit.

**Daemon** (`--daemon`): Run continuously with configurable interval.
```python
async def run_daemon(config: Config):
    """Run the pipeline on a schedule."""
    interval = config.poll_interval_seconds  # Default: 900 (15 min)
    
    while True:
        try:
            signals = await tick(config)
            if signals:
                logger.info(f"Generated {len(signals)} signals")
            
            # Also check paper trades every tick
            paper_logger = PaperLogger(config)
            paper_logger.check_open_trades()
            
        except Exception as e:
            logger.error(f"Tick failed: {e}", exc_info=True)
            # Circuit breaker: if 3 consecutive failures, pause 30 min
        
        await asyncio.sleep(interval)
```

### Configuration

```python
@dataclass
class Config:
    # News
    brave_api_key: str
    queries: list[QueryConfig]       # From news-pipeline.yaml
    
    # Markets
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    market_cache_ttl_seconds: int = 300    # 5 min
    min_market_volume: float = 100_000     # $100K
    
    # Interpretation
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    max_interpretations_per_hour: int = 20
    
    # Reaction thresholds
    min_move_to_interpret: float = 0.03    # 3pp minimum market move
    overreaction_threshold: float = 0.05   # 5pp delta
    geo_overreaction_threshold: float = 0.08  # 8pp for GEO
    
    # Sizing
    bankroll_usd: float = 10_000.0         # Paper bankroll
    max_s012_exposure: float = 0.10        # 10%
    
    # Scheduling
    poll_interval_seconds: int = 900       # 15 min
    
    # Delivery
    delivery_channel: str = "telegram"     # or "stdout"
```

Load config from `config/news-pipeline.yaml` merged with environment variables.

### Signal Delivery

```python
def deliver_signal(signal: TradingSignal, config: Config):
    """Deliver signal to configured channel."""
    formatted = signal.format_human_readable()
    
    if config.delivery_channel == "stdout":
        print(formatted)
    elif config.delivery_channel == "telegram":
        # Write to a delivery file that OpenClaw cron can pick up
        delivery_path = PROJECT_ROOT / "data" / "s012" / "pending-delivery.json"
        pending = json.loads(delivery_path.read_text()) if delivery_path.exists() else []
        pending.append({
            "signal_id": signal.signal_id,
            "message": formatted,
            "created_at": signal.created_at.isoformat(),
        })
        delivery_path.write_text(json.dumps(pending, indent=2))
        logger.info(f"Signal {signal.signal_id} queued for delivery")
```

### Status Dashboard

```python
def show_status():
    """Print pipeline status dashboard."""
    # News: last poll time, articles in last 24h, active events
    # Markets: watchlist size, last snapshot time
    # Interpretations: count today, avg confidence
    # Signals: pending count, recent signals
    # Paper trades: open count, total P&L, calibration summary
    # Budget: Brave API usage, LLM token usage
```

### Periodic Snapshot Job

The orchestrator should also take periodic market snapshots (independent of news events) to build price history:

```python
async def periodic_snapshots(config: Config):
    """Take snapshots of watched markets every 15 min."""
    snapper = MarketSnapshot(config)
    await snapper.refresh_market_cache()
    
    for market in snapper.get_watchlist():
        snapper.store_snapshot(market, trigger_event_id=None)
    
    logger.info(f"Stored {len(snapper.get_watchlist())} periodic snapshots")
```

This runs on every tick, ensuring we always have "before" prices when news hits.

### Error Handling

```python
# Circuit breaker
consecutive_failures = 0
MAX_FAILURES = 3
CIRCUIT_BREAKER_PAUSE = 1800  # 30 min

# Per-stage error handling: if one stage fails, log and skip to next tick
# Don't let a single bad interpretation crash the whole pipeline
# Rate limit errors: exponential backoff
```

### CLI Interface

```bash
python3 scripts/s012/orchestrator.py --once                  # Single tick
python3 scripts/s012/orchestrator.py --daemon                # Run continuously
python3 scripts/s012/orchestrator.py --status                # Show pipeline status
python3 scripts/s012/orchestrator.py --config custom.yaml    # Custom config
python3 scripts/s012/orchestrator.py --dry-run               # Log but don't generate signals
python3 scripts/s012/orchestrator.py --demo                  # Full pipeline with synthetic data
```

### File Structure

Create these directories/files on first run:
```
scripts/s012/
    __init__.py
    config.py               # Shared Config dataclass + loader
    news_ingestor.py        # Module 1
    market_snapshot.py       # Module 2
    reaction_interpreter.py # Module 3
    reaction_comparator.py  # Module 4
    signal_generator.py     # Module 5
    paper_logger.py         # Module 6
    orchestrator.py         # Module 7 (this file)
    test_s012.py            # All tests

data/s012/                  # Created by orchestrator on first run
    interpretations.jsonl
    assessments.jsonl
    signals.jsonl
    paper-trades.jsonl
    calibration.jsonl
    pending-delivery.json
```

### Tests

Append to `scripts/s012/test_s012.py`:
- `test_tick_no_events()` — empty poll → no signals
- `test_tick_no_matches()` — events but no market matches → no signals
- `test_tick_small_move()` — move < 3pp → skipped
- `test_tick_full_pipeline()` — synthetic event → market match → interpretation → assessment → signal
- `test_circuit_breaker()` — 3 failures → pause
- `test_config_loading()` — YAML + env vars merge correctly
- `test_periodic_snapshots()` — snapshots stored for watchlist

### Conventions

- Same as all previous modules
- The orchestrator MUST be runnable without an API key (demo mode with synthetic data)
- All inter-module communication via dataclasses (no raw dicts between modules)
- Logging at INFO level by default, DEBUG available via --verbose
- Each tick should complete in <30 seconds (excluding LLM calls)
- LLM calls are the bottleneck — batch interpretations if possible
