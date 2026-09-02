#!/usr/bin/env python3
"""S012 Module 7: Orchestrator — main loop chaining all S012 modules.

Chains: News Ingestor -> Market Snapshot -> Reaction Interpreter ->
        Reaction Comparator -> Signal Generator -> Paper Logger

Usage:
    python3 scripts/s012/orchestrator.py --once                  # Single tick
    python3 scripts/s012/orchestrator.py --daemon                # Run continuously
    python3 scripts/s012/orchestrator.py --status                # Show pipeline status
    python3 scripts/s012/orchestrator.py --config custom.yaml    # Custom config
    python3 scripts/s012/orchestrator.py --dry-run               # Log but don't generate signals
    python3 scripts/s012/orchestrator.py --demo                  # Full pipeline with synthetic data
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Module imports (same directory — run from scripts/s012/ or with it on sys.path)
from news_ingestor import (
    BraveNewsPoller, BudgetTracker, SeenStore, EventStore,
    NewsEvent, Article, cluster_articles,
    load_config as load_yaml_config, queries_from_config, QueryConfig,
    _make_demo_article,
)
from market_snapshot import (
    MarketCache, SnapshotStore, match_markets, build_watchlist,
    MarketMatch, MarketSnapshot as MarketSnap,
)
from reaction_interpreter import (
    InterpretationStore, Interpretation, interpret,
)
from reaction_comparator import (
    AssessmentStore, ReactionAssessment, assess,
    log_to_jsonl as assess_log_jsonl,
)
from signal_generator import (
    SignalStore, TradingSignal, generate_signal, format_signal,
    load_positions, log_to_jsonl as signal_log_jsonl,
)
from paper_logger import (
    TradeStore, check_trade, close_trade, fetch_current_yes_price,
    build_calibration_report,
)

logger = logging.getLogger("s012.orchestrator")

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "news-pipeline.yaml"
DELIVERY_PATH = PROJECT_ROOT / "data" / "s012" / "pending-delivery.json"
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
STILL_PATH = PROJECT_ROOT / "STILL"


# --- Config ---

@dataclass
class Config:
    # News
    brave_api_key: str = ""
    queries: list[QueryConfig] = field(default_factory=list)

    # Markets
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    market_cache_ttl_seconds: int = 300
    min_market_volume: float = 100_000

    # Interpretation
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    max_interpretations_per_hour: int = 20

    # Reaction thresholds
    min_move_to_interpret: float = 0.03
    overreaction_threshold: float = 0.05
    geo_overreaction_threshold: float = 0.08

    # Sizing
    bankroll_usd: float = 10_000.0
    max_s012_exposure: float = 0.10

    # Scheduling
    poll_interval_seconds: int = 900

    # Delivery
    delivery_channel: str = "telegram"

    # Circuit breaker
    circuit_breaker_threshold: int = 3
    circuit_breaker_pause_seconds: int = 1800

    # Budget
    brave_monthly_limit: int = 900
    brave_daily_soft_limit: int = 50


def build_config(config_path: Path = CONFIG_PATH) -> Config:
    """Build Config from YAML file merged with environment variables."""
    config = Config()
    raw = load_yaml_config(config_path)

    if raw:
        brave = raw.get("brave", {})
        config.brave_monthly_limit = brave.get("max_requests_per_month", 900)
        config.brave_daily_soft_limit = brave.get("daily_soft_limit", 50)

        pipeline = raw.get("pipeline", {})
        config.max_interpretations_per_hour = pipeline.get(
            "max_extractions_per_hour", 20
        )
        threshold = pipeline.get("divergence_threshold", 3.0)
        if threshold > 1:
            threshold /= 100.0
        config.min_move_to_interpret = threshold
        config.circuit_breaker_threshold = pipeline.get(
            "circuit_breaker_threshold", 3
        )
        config.circuit_breaker_pause_seconds = (
            pipeline.get("circuit_breaker_pause_minutes", 30) * 60
        )

        delivery = raw.get("delivery", {})
        config.delivery_channel = delivery.get("channel", "telegram")

        config.queries = queries_from_config(raw)

    # Environment variable overrides
    for env_key, attr, transform in [
        ("BRAVE_API_KEY", "brave_api_key", str),
        ("ANTHROPIC_API_KEY", "anthropic_api_key", str),
        ("S012_BANKROLL", "bankroll_usd", float),
        ("S012_POLL_INTERVAL", "poll_interval_seconds", int),
        ("S012_DELIVERY", "delivery_channel", str),
    ]:
        val = os.environ.get(env_key)
        if val:
            setattr(config, attr, transform(val))

    return config


# --- Signal Delivery ---

def deliver_signal(signal: TradingSignal, config: Config):
    """Deliver signal to configured channel."""
    formatted = format_signal(signal)

    if config.delivery_channel == "stdout":
        print(formatted)
    elif config.delivery_channel == "telegram":
        DELIVERY_PATH.parent.mkdir(parents=True, exist_ok=True)
        pending = (
            json.loads(DELIVERY_PATH.read_text()) if DELIVERY_PATH.exists() else []
        )
        pending.append({
            "signal_id": signal.signal_id,
            "message": formatted,
            "created_at": signal.created_at.isoformat(),
        })
        DELIVERY_PATH.write_text(json.dumps(pending, indent=2))
        logger.info("Signal %s queued for delivery", signal.signal_id[:12])
    else:
        # Fallback: print
        print(formatted)


# --- Paper Trade Check ---

def check_open_trades(trade_store: TradeStore) -> int:
    """Check all open paper trades against current prices. Returns count closed."""
    open_trades = trade_store.load_open()
    if not open_trades:
        return 0

    now = datetime.now(timezone.utc)
    closed_count = 0

    for trade in open_trades:
        try:
            price = fetch_current_yes_price(trade["market_id"])
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", trade["market_id"][:12], e)
            continue

        if price is None:
            continue

        result = check_trade(trade, price, now)
        if result:
            pnl, pnl_pct = close_trade(
                trade_store, trade, result["exit_price"], result["reason"]
            )
            icon = "+" if pnl >= 0 else ""
            logger.info(
                "Trade %s closed: %s | P&L: %s$%.2f (%+.1f%%)",
                trade["trade_id"], result["reason"], icon, pnl, pnl_pct * 100,
            )
            closed_count += 1

    return closed_count


# --- Periodic Snapshots ---

def periodic_snapshots(cache: MarketCache, snap_store: SnapshotStore) -> int:
    """Take snapshots of watched markets. Returns count stored."""
    watchlist = build_watchlist(cache)
    if not watchlist:
        return 0
    snap_store.save_snapshots(watchlist)
    logger.info("Stored %d periodic snapshots", len(watchlist))
    return len(watchlist)


# --- Main Pipeline Tick ---

async def tick(
    config: Config,
    dry_run: bool = False,
    use_api: bool = True,
) -> list[TradingSignal]:
    """Single tick of the S012 pipeline. Returns generated signals."""

    # Stage 1: Fetch news
    logger.info("Stage 1: Fetching news")
    budget = BudgetTracker(
        monthly_limit=config.brave_monthly_limit,
        daily_soft_limit=config.brave_daily_soft_limit,
    )
    poller = BraveNewsPoller(api_key=config.brave_api_key or None, budget=budget)
    event_store = EventStore()

    all_articles: list[Article] = []
    queries = config.queries or queries_from_config({})

    for query in queries:
        try:
            new_articles = await poller.poll(query)
            all_articles.extend(new_articles)
        except Exception as e:
            logger.error("Poll failed for %s: %s", query.name, e)

    poller.close()

    if not all_articles:
        logger.info("No new articles")
        event_store.close()
        return []

    events = cluster_articles(all_articles)
    event_store.save_events(events)
    event_store.close()

    logger.info("%d articles -> %d events", len(all_articles), len(events))
    if not events:
        return []

    # Stage 2: Match events to markets + periodic snapshots
    logger.info("Stage 2: Matching events to markets")
    cache = MarketCache()
    snap_store = SnapshotStore()

    periodic_snapshots(cache, snap_store)

    all_matches: list[MarketMatch] = []
    for event in events:
        matches = match_markets(event, cache, snap_store)
        if matches:
            for match in matches:
                snap_store.save_snapshot(
                    match.market, trigger_event_id=event.event_id
                )
            all_matches.extend(matches)

    if not all_matches:
        logger.info("%d events, but no market matches", len(events))
        snap_store.close()
        return []

    logger.info("%d events -> %d market matches", len(events), len(all_matches))

    # Stage 3: Interpret each match
    logger.info("Stage 3: Interpreting matches")
    interp_store = InterpretationStore()
    interpretations: list[tuple[MarketMatch, Interpretation]] = []

    for match in all_matches:
        if match.actual_move is None:
            logger.info(
                "No pre-news snapshot for %s, skipping",
                match.market.market_id[:12],
            )
            continue
        if abs(match.actual_move) < config.min_move_to_interpret:
            continue

        try:
            interp = interpret(match, interp_store, use_api=use_api)
            if interp:
                interpretations.append((match, interp))
        except Exception as e:
            logger.error(
                "Interpretation failed for %s: %s",
                match.market.market_id[:12], e,
            )

    interp_store.close()

    if not interpretations:
        logger.info(
            "%d matches, but no interpretable moves", len(all_matches)
        )
        snap_store.close()
        return []

    logger.info("%d interpretations generated", len(interpretations))

    # Stage 4: Compare and classify
    logger.info("Stage 4: Classifying reactions")
    assess_store = AssessmentStore()
    # (assessment, domain, reasoning) triples
    assessed: list[tuple[ReactionAssessment, str, str]] = []

    for match, interp in interpretations:
        assessment = assess(
            interp, match,
            domain=match.event.domain,
            posterior_probability=interp.posterior_probability,
        )
        assess_store.save(assessment)
        assess_log_jsonl(assessment)
        assessed.append((assessment, match.event.domain, interp.reasoning))

    assess_store.close()

    actionable_count = sum(1 for a, _, _ in assessed if a.is_actionable)
    logger.info(
        "%d assessments: %d actionable", len(assessed), actionable_count,
    )

    # Stage 5: Generate signals
    if dry_run:
        for assessment, domain, _ in assessed:
            if assessment.is_actionable:
                logger.info(
                    "DRY RUN: %s on %s (delta %+.1f%%, domain %s)",
                    assessment.reaction_type,
                    assessment.market_question[:40],
                    assessment.reaction_delta * 100,
                    domain,
                )
        snap_store.close()
        return []

    logger.info("Stage 5: Generating signals")
    bankroll, positions = load_positions()
    sig_store = SignalStore()
    signals: list[TradingSignal] = []

    for assessment, domain, reasoning in assessed:
        if not assessment.is_actionable:
            continue

        try:
            recent = sig_store.load_recent_for_market(assessment.market_id)
            signal = generate_signal(
                assessment=assessment,
                bankroll=bankroll,
                positions=positions,
                recent_signals=recent,
                domain=domain,
                reasoning=reasoning,
            )
            sig_store.save(signal)
            signal_log_jsonl(signal)
            signals.append(signal)
            logger.info(
                "Signal: %s %s on %s (%s)",
                signal.signal_type, signal.direction,
                signal.market_question[:40], signal.status,
            )
        except Exception as e:
            logger.error("Signal generation failed: %s", e)

    sig_store.close()

    # Stage 6: Check open paper trades
    logger.info("Stage 6: Checking paper trades")
    trade_store = TradeStore()
    closed = check_open_trades(trade_store)
    if closed:
        logger.info("Closed %d paper trade(s)", closed)
    trade_store.close()

    snap_store.close()

    # Deliver signals
    for signal in signals:
        deliver_signal(signal, config)

    return signals


# --- Daemon ---

async def run_daemon(config: Config, dry_run: bool = False):
    """Run until the project-root STILL file requests rest."""
    consecutive_failures = 0

    logger.info(
        "S012 daemon starting (interval=%ds, delivery=%s)",
        config.poll_interval_seconds, config.delivery_channel,
    )

    while True:
        if STILL_PATH.exists():
            logger.info("S012 daemon resting because %s exists", STILL_PATH)
            return

        tick_start = time.monotonic()

        try:
            signals = await tick(config, dry_run=dry_run)
            consecutive_failures = 0
            if signals:
                logger.info("Tick produced %d signal(s)", len(signals))
        except Exception as e:
            consecutive_failures += 1
            logger.error(
                "Tick failed (%d/%d): %s",
                consecutive_failures, config.circuit_breaker_threshold, e,
                exc_info=True,
            )

            if consecutive_failures >= config.circuit_breaker_threshold:
                pause = config.circuit_breaker_pause_seconds
                logger.warning(
                    "Circuit breaker: %d consecutive failures, pausing %ds",
                    consecutive_failures, pause,
                )
                await asyncio.sleep(pause)
                consecutive_failures = 0
                continue

        elapsed = time.monotonic() - tick_start
        sleep_time = max(0, config.poll_interval_seconds - elapsed)
        logger.debug(
            "Tick completed in %.1fs, sleeping %.1fs", elapsed, sleep_time
        )
        await asyncio.sleep(sleep_time)


# --- Status Dashboard ---

def show_status():
    """Print pipeline status dashboard."""
    now = datetime.now(timezone.utc)

    print(f"\n{'=' * 65}")
    print(f"  S012 PIPELINE STATUS -- {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 65}")

    # News
    event_store = EventStore()
    recent_events = event_store.load_recent(hours=24)
    event_store.close()
    breaking = sum(1 for e in recent_events if e.get("is_breaking"))
    print(f"\n  NEWS (last 24h)")
    print(f"    Events: {len(recent_events)} ({breaking} breaking)")
    if recent_events:
        latest = recent_events[0]
        print(f"    Latest: [{latest['domain']}] {latest['summary'][:60]}")

    # Markets
    try:
        cache = MarketCache()
        watchlist = build_watchlist(cache)
        print(f"\n  MARKETS")
        print(f"    Watchlist: {len(watchlist)} markets")
    except Exception:
        print(f"\n  MARKETS")
        print(f"    Watchlist: (cache unavailable)")

    # Interpretations
    interp_store = InterpretationStore()
    recent_interps = interp_store.load_recent(limit=50)
    today_str = now.strftime("%Y-%m-%d")
    today_interps = [
        r for r in recent_interps
        if r.get("interpreted_at", "")[:10] == today_str
    ]
    interp_store.close()
    print(f"\n  INTERPRETATIONS")
    print(f"    Today: {len(today_interps)}")
    if today_interps:
        avg_conf = (
            sum(r["confidence"] or 0 for r in today_interps)
            / len(today_interps)
        )
        print(f"    Avg confidence: {avg_conf:.0%}")

    # Signals
    sig_store = SignalStore()
    pending = sig_store.load_pending()
    all_sigs = sig_store.load_all(limit=50)
    sig_store.close()
    recent_sigs = [
        s for s in all_sigs
        if s.get("created_at", "")[:10] == today_str
    ]
    print(f"\n  SIGNALS")
    print(f"    Pending: {len(pending)}")
    print(f"    Today: {len(recent_sigs)}")
    for s in pending[:3]:
        print(
            f"    -> {s['signal_type']} {s['direction']} "
            f"on {s['market_id'][:20]}..."
        )

    # Paper trades
    trade_store = TradeStore()
    all_trades = trade_store.load_all()
    trade_store.close()
    open_trades = [t for t in all_trades if t["status"] == "OPEN"]
    closed = [t for t in all_trades if t["status"] in ("CLOSED", "EXPIRED")]
    print(f"\n  PAPER TRADES")
    print(f"    Open: {len(open_trades)} | Closed: {len(closed)}")
    if closed:
        total_pnl = sum(t["pnl_usdc"] or 0 for t in closed)
        wins = sum(1 for t in closed if (t["pnl_usdc"] or 0) > 0)
        icon = "+" if total_pnl >= 0 else ""
        print(f"    Total P&L: {icon}${total_pnl:.2f}")
        if closed:
            print(f"    Win rate: {wins}/{len(closed)} ({wins/len(closed):.0%})")

    # Budget
    budget = BudgetTracker()
    s = budget.summary()
    print(f"\n  BUDGET")
    print(
        f"    Brave API: {s['month_used']}/{s['month_limit']} this month "
        f"({s['month_remaining']} remaining)"
    )
    print(f"    Today: {s['day_used']}/{s['day_soft_limit']} (soft limit)")
    print(f"\n{'=' * 65}")


# --- Demo ---

async def demo_tick() -> list[TradingSignal]:
    """Full pipeline demo with synthetic data. No API calls."""
    now = datetime.now(timezone.utc)

    print("=" * 65)
    print("  S012 ORCHESTRATOR -- Demo Mode (no API calls)")
    print("=" * 65)

    # Stage 1: Synthetic articles
    print("\n[Stage 1] News Ingestor")
    iran_sources = [
        ("reuters.com", "Reuters"), ("bbc.com", "BBC"),
        ("rt.com", "RT"), ("aljazeera.com", "Al Jazeera"),
    ]
    articles: list[Article] = []
    for i, (domain, name) in enumerate(iran_sources):
        articles.append(_make_demo_article(
            url=f"https://{domain}/iran-orch-demo-{i}-{int(now.timestamp())}",
            title="Iran Nuclear Talks Resume in Geneva as IAEA Pushes for Inspections",
            description=f"IAEA inspectors demand access. {name} report.",
            source_name=name,
            source_domain=domain,
            country_queried=["US", "GB", "RU", "SA"][i],
            published_at=now - timedelta(minutes=i * 5),
            query_name="iran-nuclear",
        ))

    events = cluster_articles(articles)
    print(f"  {len(articles)} articles -> {len(events)} event(s)")
    for ev in events:
        breaking = " [BREAKING]" if ev.is_breaking else ""
        print(f"  [{ev.domain}] {ev.summary[:60]}{breaking}")

    if not events:
        print("  No events clustered")
        return []

    # Stage 2: Synthetic market match
    print("\n[Stage 2] Market Snapshot")
    run_id = int(now.timestamp())
    market = MarketSnap(
        market_id=f"demo-orch-mkt-{run_id}",
        question="Will Iran reach a nuclear deal before July 2026?",
        slug="iran-nuclear-deal-jul-2026",
        yes_price=0.53,
        no_price=0.47,
        volume_24h=55000.0,
        volume_total=1500000.0,
        liquidity=350000.0,
        end_date="2026-07-01T00:00:00Z",
        domain="GEO",
        snapshot_time=now,
        yes_token="tok_demo_yes",
        no_token="tok_demo_no",
    )

    # actual_move = 0.18 (big spike), synthetic LLM says shift = 0.07
    # delta = 0.18 - 0.07 = +0.11 > 0.08 GEO threshold -> OVERREACTION STRONG
    match = MarketMatch(
        event=events[0],
        market=market,
        relevance_score=0.85,
        price_before=0.35,
        price_after=0.53,
        actual_move=0.18,
    )
    print(f"  Matched: {market.question[:55]}")
    print(f"  Relevance: {match.relevance_score:.2f} | Move: {match.actual_move:+.1%}")
    print(f"  Before: {match.price_before:.1%} -> After: {match.price_after:.1%}")

    # Stage 3: Synthetic interpretation (no API call)
    print("\n[Stage 3] Reaction Interpreter (synthetic LLM)")
    interp_store = InterpretationStore()
    interp = interpret(match, interp_store, use_api=False)
    interp_store.close()

    if not interp:
        print("  Interpretation skipped (cooldown or rate limit)")
        return []

    print(
        f"  Prior: {interp.prior_probability:.1%} -> "
        f"Posterior: {interp.posterior_probability:.1%}"
    )
    print(f"  Shift: {interp.estimated_shift:+.1%} | Confidence: {interp.confidence:.0%}")
    print(f"  Type: {interp.news_type} | Quality: {interp.source_quality}")

    # Stage 4: Assess
    print("\n[Stage 4] Reaction Comparator")
    assessment = assess(
        interp, match,
        domain=events[0].domain,
        posterior_probability=interp.posterior_probability,
    )
    print(f"  Reaction: {assessment.reaction_type} ({assessment.delta_magnitude})")
    print(
        f"  Delta: {assessment.reaction_delta:+.1%} "
        f"(actual {assessment.actual_move:+.1%} vs "
        f"estimated {assessment.estimated_shift:+.1%})"
    )
    print(f"  Actionable: {assessment.is_actionable}")

    # Stage 5: Signal (if actionable)
    signals: list[TradingSignal] = []
    if assessment.is_actionable:
        print("\n[Stage 5] Signal Generator")
        bankroll, positions = load_positions()
        signal = generate_signal(
            assessment=assessment,
            bankroll=bankroll,
            positions=positions,
            recent_signals=[],
            domain=events[0].domain,
            reasoning=interp.reasoning,
        )
        signals.append(signal)
        print(format_signal(signal))
    else:
        print("\n[Stage 5] No actionable signal (delta below threshold)")

    # Stage 6: Paper trade status
    print("\n[Stage 6] Paper Trade Check")
    trade_store = TradeStore()
    open_trades = trade_store.load_open()
    print(f"  Open trades: {len(open_trades)}")
    trade_store.close()

    print(f"\n{'=' * 65}")
    print(f"  Demo complete: {len(signals)} signal(s) generated")
    print(f"{'=' * 65}")

    return signals


# --- CLI ---

def main():
    args = sys.argv[1:]

    # Logging
    verbose = "--verbose" in args
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Config path
    config_path = CONFIG_PATH
    if "--config" in args:
        idx = args.index("--config")
        if idx + 1 < len(args):
            config_path = Path(args[idx + 1])

    if "--demo" in args:
        asyncio.run(demo_tick())
    elif "--status" in args:
        show_status()
    elif "--once" in args:
        config = build_config(config_path)
        dry_run = "--dry-run" in args
        signals = asyncio.run(tick(config, dry_run=dry_run))
        print(f"\nTick complete: {len(signals)} signal(s)")
    elif "--daemon" in args:
        config = build_config(config_path)
        dry_run = "--dry-run" in args
        try:
            asyncio.run(run_daemon(config, dry_run=dry_run))
        except KeyboardInterrupt:
            logger.info("Daemon stopped by user")
    else:
        print(__doc__)
        sys.exit(0)


if __name__ == "__main__":
    main()
