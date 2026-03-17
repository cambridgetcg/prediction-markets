#!/usr/bin/env python3
"""S012 Module 4: Reaction Comparator — classifies market over/underreaction to news.

Compares the LLM's estimated rational shift (Module 3) against the market's
actual move (Module 2 snapshots) to produce OVERREACTION / UNDERREACTION / CORRECT
classifications and actionable trade parameters.

Usage:
    python3 scripts/s012/reaction_comparator.py --demo          # Demo with synthetic data
    python3 scripts/s012/reaction_comparator.py --recent         # Show recent assessments
    python3 scripts/s012/reaction_comparator.py --actionable     # Show only actionable signals
    python3 scripts/s012/reaction_comparator.py --stats          # Classification distribution stats
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reaction_interpreter import Interpretation, InterpretationStore
from market_snapshot import MarketMatch, MarketSnapshot

logger = logging.getLogger(__name__)

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "news-pipeline.db"
JSONL_PATH = PROJECT_ROOT / "data" / "s012" / "assessments.jsonl"

# --- Classification Thresholds (module-level for easy tuning) ---
DEFAULT_ACTION_THRESHOLD = 0.05   # 5pp delta to be actionable
GEO_ACTION_THRESHOLD = 0.08      # 8pp for GEO domain (L07)
STRONG_MAGNITUDE_THRESHOLD = 0.08 # ≥8pp absolute delta = STRONG
MIN_CONFIDENCE = 0.50             # Minimum adjusted confidence for actionable

# --- Trade Parameters ---
OVERREACTION_RETRACEMENT = 0.40   # S004: target 40% retracement
OVERREACTION_STOP_PP = 0.08       # 8pp stop-loss
OVERREACTION_HORIZON_HOURS = 168  # 7 days

UNDERREACTION_HORIZON_HOURS = 48  # 48 hours — shorter window

# --- Position Sizing (bankroll %) ---
SIZE_OVER_STRONG = 0.03           # 3% for strong overreaction
SIZE_OVER_MODERATE = 0.015        # 1.5% for moderate overreaction
SIZE_UNDER_STRONG = 0.02          # 2% for strong underreaction
SIZE_UNDER_MODERATE = 0.01        # 1% for moderate underreaction

# --- Confidence Adjustment Multipliers ---
SOURCE_QUALITY_DISCOUNT = {
    "RUMOR": 0.5,
    "UNCONFIRMED": 0.7,
    "CREDIBLE": 0.9,
    "VERIFIED": 1.0,
}
NEWS_TYPE_MULTIPLIER = {
    "NOVEL": 1.1,
    "CONTRADICTORY": 1.0,
    "AMBIGUOUS": 0.9,
    "CONFIRMATORY": 0.8,
}
EFFICIENT_DOMAINS = {"ECO", "FIN"}
EFFICIENT_DOMAIN_DISCOUNT = 0.5


# --- Dataclass ---

@dataclass
class ReactionAssessment:
    assessment_id: str
    interpretation_id: str
    event_id: str
    market_id: str
    market_question: str

    # The comparison
    estimated_shift: float
    actual_move: float
    reaction_delta: float           # actual_move - estimated_shift

    # Classification
    reaction_type: str              # OVERREACTION | UNDERREACTION | CORRECT
    delta_magnitude: str            # STRONG | MODERATE | WEAK

    # Confidence adjustments
    raw_confidence: float
    adjusted_confidence: float

    # Trade parameters (if actionable)
    is_actionable: bool
    suggested_direction: str | None
    suggested_entry: float | None
    suggested_target: float | None
    suggested_stop: float | None
    time_horizon_hours: int | None
    size_pct: float | None

    # Prices
    current_yes_price: float
    price_before_news: float | None

    assessed_at: datetime


# --- Core Classification Logic ---

def classify_reaction(estimated_shift: float, actual_move: float,
                      confidence: float, domain: str) -> tuple[str, str, bool]:
    """Classify the market's reaction as OVERREACTION, UNDERREACTION, or CORRECT.

    Returns (reaction_type, magnitude, is_actionable).

    The delta is: actual_move - estimated_shift
    - Positive delta = market moved MORE than expected = OVERREACTION
    - Negative delta = market moved LESS than expected = UNDERREACTION
    - Small delta = market moved about right = CORRECT
    """
    delta = actual_move - estimated_shift
    abs_delta = abs(delta)

    # Domain-specific thresholds
    action_threshold = GEO_ACTION_THRESHOLD if domain == "GEO" else DEFAULT_ACTION_THRESHOLD

    # Classification
    if abs_delta < action_threshold:
        return "CORRECT", "WEAK", False

    reaction_type = "OVERREACTION" if delta > 0 else "UNDERREACTION"
    magnitude = "STRONG" if abs_delta >= STRONG_MAGNITUDE_THRESHOLD else "MODERATE"

    # Actionable if: delta exceeds threshold AND confidence sufficient
    is_actionable = abs_delta >= action_threshold and confidence >= MIN_CONFIDENCE

    return reaction_type, magnitude, is_actionable


# --- Confidence Adjustment ---

def adjust_confidence(raw_confidence: float, source_quality: str,
                      news_type: str, domain: str) -> float:
    """Adjust raw LLM confidence based on source quality, news type, and domain efficiency."""
    adj = raw_confidence

    adj *= SOURCE_QUALITY_DISCOUNT.get(source_quality, 1.0)
    adj *= NEWS_TYPE_MULTIPLIER.get(news_type, 1.0)

    if domain in EFFICIENT_DOMAINS:
        adj *= EFFICIENT_DOMAIN_DISCOUNT

    return min(adj, 1.0)


# --- Position Sizing ---

def calculate_size(reaction_type: str, magnitude: str) -> float:
    """Return bankroll percentage for position sizing."""
    if reaction_type == "OVERREACTION":
        return SIZE_OVER_STRONG if magnitude == "STRONG" else SIZE_OVER_MODERATE
    elif reaction_type == "UNDERREACTION":
        return SIZE_UNDER_STRONG if magnitude == "STRONG" else SIZE_UNDER_MODERATE
    return 0.0


# --- Trade Parameter Generation ---

def generate_trade_params(
    reaction_type: str,
    actual_move: float,
    estimated_shift: float,
    current_yes_price: float,
    price_before_news: float | None,
    posterior_probability: float,
    magnitude: str,
) -> dict:
    """Generate trade parameters for an actionable signal.

    Returns dict with: direction, entry, target, stop, time_horizon_hours, size_pct.
    """
    if reaction_type == "OVERREACTION":
        # Fade the move — target 40% retracement
        if actual_move > 0:
            # Price spiked UP → buy NO
            direction = "NO"
            entry = 1.0 - current_yes_price
            target_yes = current_yes_price - abs(actual_move) * OVERREACTION_RETRACEMENT
            target = 1.0 - target_yes
            stop_yes = current_yes_price + OVERREACTION_STOP_PP
            stop = 1.0 - stop_yes
        else:
            # Price dropped → buy YES
            direction = "YES"
            entry = current_yes_price
            target = current_yes_price + abs(actual_move) * OVERREACTION_RETRACEMENT
            stop = current_yes_price - OVERREACTION_STOP_PP

        time_horizon = OVERREACTION_HORIZON_HOURS

    elif reaction_type == "UNDERREACTION":
        # Ride in the direction the market SHOULD have moved
        if estimated_shift > 0:
            # Should have gone UP more → buy YES
            direction = "YES"
            entry = current_yes_price
            target = posterior_probability
            stop = price_before_news if price_before_news is not None else current_yes_price - 0.08
        else:
            # Should have gone DOWN more → buy NO
            direction = "NO"
            entry = 1.0 - current_yes_price
            target = 1.0 - posterior_probability
            stop = (1.0 - price_before_news) if price_before_news is not None else entry - 0.08

        time_horizon = UNDERREACTION_HORIZON_HOURS
    else:
        return {
            "direction": None, "entry": None, "target": None,
            "stop": None, "time_horizon_hours": None, "size_pct": 0.0,
        }

    size = calculate_size(reaction_type, magnitude)

    return {
        "direction": direction,
        "entry": round(entry, 4),
        "target": round(target, 4),
        "stop": round(stop, 4),
        "time_horizon_hours": time_horizon,
        "size_pct": size,
    }


# --- Core Assess Function ---

def assess(
    interp: Interpretation,
    match: MarketMatch,
    domain: str,
    posterior_probability: float | None = None,
) -> ReactionAssessment:
    """Run the full comparison for a single interpretation + market match.

    Returns a ReactionAssessment with classification and trade parameters.
    """
    estimated_shift = interp.estimated_shift
    actual_move = match.actual_move if match.actual_move is not None else 0.0
    posterior = posterior_probability if posterior_probability is not None else interp.posterior_probability

    # Adjust confidence
    adj_confidence = adjust_confidence(
        interp.confidence, interp.source_quality, interp.news_type, domain,
    )

    # Classify
    reaction_type, magnitude, is_actionable = classify_reaction(
        estimated_shift, actual_move, adj_confidence, domain,
    )

    # Generate trade params if actionable
    if is_actionable:
        params = generate_trade_params(
            reaction_type=reaction_type,
            actual_move=actual_move,
            estimated_shift=estimated_shift,
            current_yes_price=match.market.yes_price,
            price_before_news=match.price_before,
            posterior_probability=posterior,
            magnitude=magnitude,
        )
    else:
        params = {
            "direction": None, "entry": None, "target": None,
            "stop": None, "time_horizon_hours": None, "size_pct": 0.0,
        }

    now = datetime.now(timezone.utc)
    delta = actual_move - estimated_shift

    return ReactionAssessment(
        assessment_id=str(uuid.uuid4()),
        interpretation_id=interp.interpretation_id,
        event_id=interp.event_id,
        market_id=interp.market_id,
        market_question=interp.market_question,
        estimated_shift=estimated_shift,
        actual_move=actual_move,
        reaction_delta=round(delta, 4),
        reaction_type=reaction_type,
        delta_magnitude=magnitude,
        raw_confidence=interp.confidence,
        adjusted_confidence=round(adj_confidence, 4),
        is_actionable=is_actionable,
        suggested_direction=params["direction"],
        suggested_entry=params["entry"],
        suggested_target=params["target"],
        suggested_stop=params["stop"],
        time_horizon_hours=params["time_horizon_hours"],
        size_pct=params["size_pct"],
        current_yes_price=match.market.yes_price,
        price_before_news=match.price_before,
        assessed_at=now,
    )


# --- SQLite Store ---

class AssessmentStore:
    """SQLite-backed assessment storage."""

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS s012_assessments (
                assessment_id TEXT PRIMARY KEY,
                interpretation_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                market_id TEXT NOT NULL,
                estimated_shift REAL,
                actual_move REAL,
                reaction_delta REAL,
                reaction_type TEXT,
                delta_magnitude TEXT,
                is_actionable INTEGER,
                suggested_direction TEXT,
                suggested_entry REAL,
                suggested_target REAL,
                suggested_stop REAL,
                time_horizon_hours INTEGER,
                size_pct REAL,
                adjusted_confidence REAL,
                assessed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_assess_event ON s012_assessments(event_id);
            CREATE INDEX IF NOT EXISTS idx_assess_actionable ON s012_assessments(is_actionable);
        """)
        self.conn.commit()

    def save(self, a: ReactionAssessment):
        """Persist an assessment to SQLite."""
        self.conn.execute("""
            INSERT OR REPLACE INTO s012_assessments
                (assessment_id, interpretation_id, event_id, market_id,
                 estimated_shift, actual_move, reaction_delta,
                 reaction_type, delta_magnitude, is_actionable,
                 suggested_direction, suggested_entry, suggested_target,
                 suggested_stop, time_horizon_hours, size_pct,
                 adjusted_confidence, assessed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            a.assessment_id, a.interpretation_id, a.event_id, a.market_id,
            a.estimated_shift, a.actual_move, a.reaction_delta,
            a.reaction_type, a.delta_magnitude, int(a.is_actionable),
            a.suggested_direction, a.suggested_entry, a.suggested_target,
            a.suggested_stop, a.time_horizon_hours, a.size_pct,
            a.adjusted_confidence, a.assessed_at.isoformat(),
        ))
        self.conn.commit()

    def load_recent(self, limit: int = 20) -> list[dict]:
        """Load recent assessments."""
        rows = self.conn.execute("""
            SELECT assessment_id, interpretation_id, event_id, market_id,
                   estimated_shift, actual_move, reaction_delta,
                   reaction_type, delta_magnitude, is_actionable,
                   suggested_direction, suggested_entry, suggested_target,
                   suggested_stop, time_horizon_hours, size_pct,
                   adjusted_confidence, assessed_at
            FROM s012_assessments
            ORDER BY assessed_at DESC LIMIT ?
        """, (limit,)).fetchall()

        return [
            {
                "assessment_id": r[0], "interpretation_id": r[1],
                "event_id": r[2], "market_id": r[3],
                "estimated_shift": r[4], "actual_move": r[5],
                "reaction_delta": r[6], "reaction_type": r[7],
                "delta_magnitude": r[8], "is_actionable": bool(r[9]),
                "suggested_direction": r[10], "suggested_entry": r[11],
                "suggested_target": r[12], "suggested_stop": r[13],
                "time_horizon_hours": r[14], "size_pct": r[15],
                "adjusted_confidence": r[16], "assessed_at": r[17],
            }
            for r in rows
        ]

    def load_actionable(self, limit: int = 20) -> list[dict]:
        """Load only actionable assessments."""
        rows = self.conn.execute("""
            SELECT assessment_id, interpretation_id, event_id, market_id,
                   estimated_shift, actual_move, reaction_delta,
                   reaction_type, delta_magnitude, is_actionable,
                   suggested_direction, suggested_entry, suggested_target,
                   suggested_stop, time_horizon_hours, size_pct,
                   adjusted_confidence, assessed_at
            FROM s012_assessments
            WHERE is_actionable = 1
            ORDER BY assessed_at DESC LIMIT ?
        """, (limit,)).fetchall()

        return [
            {
                "assessment_id": r[0], "interpretation_id": r[1],
                "event_id": r[2], "market_id": r[3],
                "estimated_shift": r[4], "actual_move": r[5],
                "reaction_delta": r[6], "reaction_type": r[7],
                "delta_magnitude": r[8], "is_actionable": bool(r[9]),
                "suggested_direction": r[10], "suggested_entry": r[11],
                "suggested_target": r[12], "suggested_stop": r[13],
                "time_horizon_hours": r[14], "size_pct": r[15],
                "adjusted_confidence": r[16], "assessed_at": r[17],
            }
            for r in rows
        ]

    def load_all_for_stats(self) -> list[dict]:
        """Load all assessments for statistics."""
        rows = self.conn.execute("""
            SELECT reaction_type, delta_magnitude, is_actionable,
                   reaction_delta, adjusted_confidence, suggested_direction
            FROM s012_assessments
            ORDER BY assessed_at
        """).fetchall()

        return [
            {
                "reaction_type": r[0], "delta_magnitude": r[1],
                "is_actionable": bool(r[2]), "reaction_delta": r[3],
                "adjusted_confidence": r[4], "suggested_direction": r[5],
            }
            for r in rows
        ]

    def close(self):
        self.conn.close()


# --- JSONL Logger ---

def log_to_jsonl(a: ReactionAssessment):
    """Append assessment to JSONL file."""
    JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "assessment_id": a.assessment_id,
        "interpretation_id": a.interpretation_id,
        "event_id": a.event_id,
        "market_id": a.market_id,
        "market_question": a.market_question,
        "estimated_shift": a.estimated_shift,
        "actual_move": a.actual_move,
        "reaction_delta": a.reaction_delta,
        "reaction_type": a.reaction_type,
        "delta_magnitude": a.delta_magnitude,
        "raw_confidence": a.raw_confidence,
        "adjusted_confidence": a.adjusted_confidence,
        "is_actionable": a.is_actionable,
        "suggested_direction": a.suggested_direction,
        "suggested_entry": a.suggested_entry,
        "suggested_target": a.suggested_target,
        "suggested_stop": a.suggested_stop,
        "time_horizon_hours": a.time_horizon_hours,
        "size_pct": a.size_pct,
        "current_yes_price": a.current_yes_price,
        "price_before_news": a.price_before_news,
        "assessed_at": a.assessed_at.isoformat(),
    }

    with open(JSONL_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


# --- Synthetic Demo ---

def _make_demo_interpretation() -> Interpretation:
    """Build a synthetic Interpretation for demo mode."""
    return Interpretation(
        interpretation_id="demo-interp-001",
        event_id="demo-evt-001",
        market_id="demo-mkt-001",
        market_question="Will Iran reach a nuclear deal before July 2026?",
        prior_probability=0.35,
        posterior_probability=0.42,
        estimated_shift=0.07,
        confidence=0.65,
        reasoning="The resumption of IAEA inspections represents a modest increase in deal probability.",
        news_type="NOVEL",
        source_quality="CREDIBLE",
        interpreted_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        model_used="claude-haiku-4-5",
        prompt_version="v1.0",
        raw_llm_response="{}",
    )


def _make_demo_match() -> MarketMatch:
    """Build a synthetic MarketMatch for demo mode."""
    from news_ingestor import NewsEvent

    now = datetime.now(timezone.utc)

    event = NewsEvent(
        event_id="demo-evt-001",
        articles=[],
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
        yes_price=0.38,
        no_price=0.62,
        volume_24h=45000.0,
        volume_total=1200000.0,
        liquidity=300000.0,
        end_date="2026-07-01T00:00:00Z",
        domain="GEO",
        snapshot_time=now,
        yes_token="tok_demo_yes",
        no_token="tok_demo_no",
    )

    # Market moved from 0.33 to 0.38 = +5pp actual move
    # But LLM estimated +7pp shift → UNDERREACTION (market didn't move enough)
    return MarketMatch(
        event=event,
        market=market,
        relevance_score=0.85,
        price_before=0.33,
        price_after=0.38,
        actual_move=0.05,
    )


# --- CLI Commands ---

def cmd_demo():
    """Run a synthetic demo without any API calls."""
    interp = _make_demo_interpretation()
    match = _make_demo_match()

    print("=" * 70)
    print("REACTION COMPARATOR — Demo Mode")
    print("=" * 70)

    print(f"\nEvent: {match.event.summary}")
    print(f"  Market: {match.market.question}")
    print(f"  YES price now: {match.market.yes_price:.1%}")
    print(f"  Price before news: {match.price_before:.1%}")
    print(f"  Actual move: {match.actual_move:+.1%}")

    print(f"\nLLM Interpretation:")
    print(f"  Estimated shift: {interp.estimated_shift:+.1%}")
    print(f"  Confidence: {interp.confidence:.0%}")
    print(f"  News type: {interp.news_type}")
    print(f"  Source quality: {interp.source_quality}")

    # Run assessment
    result = assess(interp, match, domain=match.event.domain,
                    posterior_probability=interp.posterior_probability)

    # Persist
    store = AssessmentStore()
    store.save(result)
    store.close()
    log_to_jsonl(result)

    print(f"\n--- Assessment ---")
    print(f"  Reaction type: {result.reaction_type}")
    print(f"  Magnitude: {result.delta_magnitude}")
    print(f"  Delta: {result.reaction_delta:+.1%} "
          f"(actual {result.actual_move:+.1%} vs estimated {result.estimated_shift:+.1%})")
    print(f"  Raw confidence: {result.raw_confidence:.0%}")
    print(f"  Adjusted confidence: {result.adjusted_confidence:.0%}")
    print(f"  Actionable: {result.is_actionable}")

    if result.is_actionable:
        print(f"\n--- Trade Signal ---")
        print(f"  Direction: {result.suggested_direction}")
        print(f"  Entry: {result.suggested_entry:.1%}")
        print(f"  Target: {result.suggested_target:.1%}")
        print(f"  Stop: {result.suggested_stop:.1%}")
        print(f"  Horizon: {result.time_horizon_hours}h")
        print(f"  Size: {result.size_pct:.1%} of bankroll")
    else:
        print(f"\n  (Not actionable — delta below threshold or confidence too low)")

    print(f"\n  ID: {result.assessment_id}")


def cmd_recent():
    """Show recent assessments."""
    store = AssessmentStore()
    recent = store.load_recent(limit=20)
    store.close()

    if not recent:
        print("No assessments yet. Run --demo first.")
        return

    now = datetime.now(timezone.utc)
    print(f"\n{'=' * 80}")
    print(f"RECENT ASSESSMENTS — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 80}")
    print(f"  {len(recent)} assessment(s)\n")

    for r in recent:
        delta_str = f"{r['reaction_delta']:+.1%}" if r['reaction_delta'] is not None else "N/A"
        conf_str = f"{r['adjusted_confidence']:.0%}" if r['adjusted_confidence'] is not None else "N/A"
        act_str = "ACTIONABLE" if r["is_actionable"] else "---"

        print(f"  [{r['reaction_type']:14s}] {r['delta_magnitude']:8s} | "
              f"Delta: {delta_str:>6s} | Conf: {conf_str} | {act_str}")

        if r["is_actionable"] and r["suggested_direction"]:
            print(f"    -> {r['suggested_direction']} @ {r['suggested_entry']:.1%} "
                  f"target {r['suggested_target']:.1%} "
                  f"stop {r['suggested_stop']:.1%} "
                  f"({r['time_horizon_hours']}h, {r['size_pct']:.1%} size)")

        print(f"    Event: {r['event_id'][:12]}... | Market: {r['market_id'][:12]}...")
        print(f"    At: {r['assessed_at']}")
        print()


def cmd_actionable():
    """Show only actionable signals."""
    store = AssessmentStore()
    signals = store.load_actionable(limit=20)
    store.close()

    if not signals:
        print("No actionable signals yet.")
        return

    now = datetime.now(timezone.utc)
    print(f"\n{'=' * 80}")
    print(f"ACTIONABLE SIGNALS — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 80}")
    print(f"  {len(signals)} signal(s)\n")

    for r in signals:
        delta_str = f"{r['reaction_delta']:+.1%}" if r['reaction_delta'] is not None else "N/A"
        print(f"  {r['reaction_type']} ({r['delta_magnitude']}) | Delta: {delta_str}")
        print(f"    -> {r['suggested_direction']} @ {r['suggested_entry']:.1%} "
              f"target {r['suggested_target']:.1%} "
              f"stop {r['suggested_stop']:.1%}")
        print(f"    Horizon: {r['time_horizon_hours']}h | "
              f"Size: {r['size_pct']:.1%} bankroll | "
              f"Confidence: {r['adjusted_confidence']:.0%}")
        print(f"    Event: {r['event_id'][:12]}... | Market: {r['market_id'][:12]}...")
        print()


def cmd_stats():
    """Show classification distribution statistics."""
    store = AssessmentStore()
    all_data = store.load_all_for_stats()
    store.close()

    if not all_data:
        print("No assessments for stats. Run --demo or pipeline first.")
        return

    n = len(all_data)

    # Reaction type distribution
    type_counts: dict[str, int] = {}
    for r in all_data:
        t = r.get("reaction_type", "UNKNOWN")
        type_counts[t] = type_counts.get(t, 0) + 1

    # Magnitude distribution
    mag_counts: dict[str, int] = {}
    for r in all_data:
        m = r.get("delta_magnitude", "UNKNOWN")
        mag_counts[m] = mag_counts.get(m, 0) + 1

    # Actionable count
    actionable = sum(1 for r in all_data if r["is_actionable"])

    # Direction distribution (actionable only)
    dir_counts: dict[str, int] = {}
    for r in all_data:
        if r["is_actionable"] and r["suggested_direction"]:
            d = r["suggested_direction"]
            dir_counts[d] = dir_counts.get(d, 0) + 1

    # Delta statistics
    deltas = [r["reaction_delta"] for r in all_data if r["reaction_delta"] is not None]

    print(f"\n{'=' * 60}")
    print("CLASSIFICATION STATS")
    print(f"{'=' * 60}")
    print(f"  Total assessments: {n}")
    print(f"  Actionable: {actionable} ({actionable/n:.0%})")

    print(f"\n  Reaction Type Distribution:")
    for t, c in sorted(type_counts.items()):
        print(f"    {t:14s}: {c:>4d} ({c/n:.0%})")

    print(f"\n  Magnitude Distribution:")
    for m, c in sorted(mag_counts.items()):
        print(f"    {m:14s}: {c:>4d} ({c/n:.0%})")

    if dir_counts:
        print(f"\n  Direction Distribution (actionable only):")
        for d, c in sorted(dir_counts.items()):
            print(f"    {d:14s}: {c:>4d}")

    if deltas:
        avg_delta = sum(abs(d) for d in deltas) / len(deltas)
        max_delta = max(abs(d) for d in deltas)
        print(f"\n  Delta Statistics:")
        print(f"    Avg absolute delta: {avg_delta:.1%}")
        print(f"    Max absolute delta: {max_delta:.1%}")

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
    elif "--recent" in args:
        cmd_recent()
    elif "--actionable" in args:
        cmd_actionable()
    elif "--stats" in args:
        cmd_stats()
    else:
        print(__doc__)
        sys.exit(0)


if __name__ == "__main__":
    main()
