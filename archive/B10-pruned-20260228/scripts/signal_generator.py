#!/usr/bin/env python3
"""NB07: Signal Generator & Polymarket Integration — Stage 7 of the News Intelligence Pipeline.

Converts TruthExtractionResults into actionable trading signals by:
1. Matching extracted insights to active Polymarket markets
2. Applying B05 source bias adjustment
3. Routing through strategy-specific edge calculations
4. Running R01 correlation risk checks
5. Sizing via quarter-Kelly with YES calibration discount

Usage:
    # As library — called by pipeline orchestrator:
    from signal_generator import SignalGenerator
    gen = SignalGenerator()
    signals = gen.generate(extraction, cluster)

    # CLI:
    python3 scripts/signal_generator.py --demo       # Synthetic demo
    python3 scripts/signal_generator.py --show        # Show recent signals
    python3 scripts/signal_generator.py --test        # Run unit tests
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from truth_extractor import TruthExtractionResult  # noqa: E402
from event_clusterer import EventCluster  # noqa: E402

logger = logging.getLogger(__name__)

PROJECT_ROOT = SCRIPT_DIR.parent
SIGNALS_PATH = PROJECT_ROOT / "data" / "signals.jsonl"
POSITIONS_PATH = PROJECT_ROOT / "strategies" / "paper-trades" / "positions.json"

GAMMA_BASE = "https://gamma-api.polymarket.com"

# --- Configuration ---
YES_DISCOUNT = 0.85          # Calibration: YES 2/5 correct, NO 7/7
FRACTIONAL_KELLY = 0.25      # Quarter-Kelly
DEFAULT_BANKROLL = 10000.0
MIN_EDGE = 0.05              # Reject below 5pp edge
MIN_CONFIDENCE = 0.6         # Flag for human review below this
MAX_PENDING = 3              # Max pending signals at once

# R01 thresholds
C1_SINGLE_EVENT_CAP = 0.03   # 3% bankroll per event/thesis
C2_DOMAIN_CAP = 0.05         # 5% bankroll per domain


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GeneratedSignal:
    signal_id: str
    cluster_id: str
    market_id: str
    market_question: str
    direction: str                 # YES | NO
    current_price: float
    suggested_probability: float
    edge: float
    kelly_fraction: float
    kelly_usdc: float
    strategy_code: str
    confidence: float
    yes_discount_applied: bool
    generated_at: datetime
    status: str                    # pending | approved | rejected | executed

    def to_dict(self) -> dict:
        return {
            'signal_id': self.signal_id,
            'cluster_id': self.cluster_id,
            'market_id': self.market_id,
            'market_question': self.market_question,
            'direction': self.direction,
            'current_price': self.current_price,
            'suggested_probability': round(self.suggested_probability, 4),
            'edge': round(self.edge, 4),
            'kelly_fraction': round(self.kelly_fraction, 4),
            'kelly_usdc': round(self.kelly_usdc, 2),
            'strategy_code': self.strategy_code,
            'confidence': round(self.confidence, 3),
            'yes_discount_applied': self.yes_discount_applied,
            'generated_at': self.generated_at.isoformat(),
            'status': self.status,
        }


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def curl_json(url: str) -> dict | list | None:
    """Fetch JSON from URL via curl."""
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '15',
             '-H', 'User-Agent: Mozilla/5.0', url],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Market matching
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Split text into lowercase keyword tokens."""
    return set(re.findall(r'[a-z0-9]+', text.lower()))


def _match_score(query_tokens: set[str], market_question: str) -> float:
    """Score how well market question matches query keywords (0-1)."""
    market_tokens = _tokenize(market_question)
    if not query_tokens or not market_tokens:
        return 0.0
    overlap = query_tokens & market_tokens
    return len(overlap) / len(query_tokens)


def search_active_markets(description: str, max_results: int = 3) -> list[dict]:
    """Search active Polymarket markets matching a relevance description.

    Fetches top active events from Gamma API and keyword-matches against
    the market_relevance description from truth extraction.

    Returns list of dicts: condition_id, question, current_price, volume,
    liquidity, clob_token_ids, match_score.
    """
    query_tokens = _tokenize(description)
    if not query_tokens:
        return []

    candidates = []

    for offset in (0, 100):
        url = (f"{GAMMA_BASE}/events?limit=100&closed=false"
               f"&order=volume&ascending=false&offset={offset}")
        data = curl_json(url)
        if not data or not isinstance(data, list):
            break

        for event in data:
            for m in event.get('markets', []):
                question = m.get('question', '') or event.get('title', '')
                if not question:
                    continue

                score = _match_score(query_tokens, question)
                if score < 0.3:
                    continue

                try:
                    prices = json.loads(m.get('outcomePrices', '[]'))
                    yes_price = float(prices[0]) if prices else 0.5
                except (json.JSONDecodeError, ValueError, IndexError):
                    yes_price = 0.5

                try:
                    tokens = json.loads(m.get('clobTokenIds', '[]'))
                except json.JSONDecodeError:
                    tokens = []

                candidates.append({
                    'condition_id': m.get('conditionId', ''),
                    'question': question,
                    'current_price': yes_price,
                    'volume': float(m.get('volumeNum', 0) or 0),
                    'liquidity': float(m.get('liquidityNum', 0) or 0),
                    'clob_token_ids': tokens,
                    'match_score': score,
                })

    candidates.sort(key=lambda c: (c['match_score'], c['volume']), reverse=True)
    return candidates[:max_results]


# ---------------------------------------------------------------------------
# B05 source bias adjustment
# ---------------------------------------------------------------------------

def apply_B05(raw_estimate: float, reliability_weighted_tone: float,
              current_price: float) -> float:
    """B05: Adjust estimate based on source reliability.

    Maps |reliability_weighted_tone| to credibility (0.10–0.95).
      |rwt| >= 3.5  → credibility ~0.95  (strong reliable signal)
      |rwt| ~1.5    → credibility ~0.43
      |rwt| < 0.35  → credibility ~0.10  (weak / conflicting)

    Formula: adjusted = current_price + credibility × (raw_estimate - current_price)
    """
    credibility = min(0.95, max(0.10, abs(reliability_weighted_tone) / 3.5))
    adjusted = current_price + credibility * (raw_estimate - current_price)
    return max(0.01, min(0.99, adjusted))


# ---------------------------------------------------------------------------
# Strategy routing
# ---------------------------------------------------------------------------

STRATEGY_MAP = {
    'geopolitical': 'S004',
    'GEO':         'S004',
    'political':   'S001',
    'POL':         'S001',
    'economic':    'S006',
    'ECO':         'S006',
    'technology':  'S006',
    'TEC':         'S006',
    'crypto':      'S006',
    'CRY':         'S006',
    'legal':       'S001',
    'LAW':         'S001',
}


def route_strategy(category: str, days_to_resolution: int | None = None) -> str:
    """Route market_relevance category to strategy code."""
    strategy = STRATEGY_MAP.get(category, 'S001')

    # R04 overlay: fast resolution → prefer S006 time decay
    if (days_to_resolution is not None and days_to_resolution < 7
            and strategy not in ('S004',)):
        strategy = 'S006'

    return strategy


def apply_strategy_edge(bias_adjusted: float, strategy_code: str,
                        current_price: float) -> float:
    """Apply strategy-specific edge adjustment.

    S004 (Contrarian): expect 40% reversion toward our estimate.
    S006 (Time Decay): use bias-adjusted directly.
    S001/S007 (Hold/Arb): use bias-adjusted directly.
    """
    if strategy_code == 'S004':
        reversion = 0.40
        return current_price + reversion * (bias_adjusted - current_price)
    return bias_adjusted


# ---------------------------------------------------------------------------
# R01 correlation risk check
# ---------------------------------------------------------------------------

def load_positions() -> dict:
    """Load current portfolio from positions.json."""
    if not POSITIONS_PATH.exists():
        return {'bankroll': DEFAULT_BANKROLL, 'positions': [], 'domain_exposure': {}}
    try:
        with open(POSITIONS_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {'bankroll': DEFAULT_BANKROLL, 'positions': [], 'domain_exposure': {}}


def _estimate_correlation(signal_market: str, signal_domain: str,
                          position: dict) -> float:
    """Estimate correlation between a new signal and an existing position."""
    sig_tokens = _tokenize(signal_market)
    pos_tokens = _tokenize(position.get('market', ''))
    union = sig_tokens | pos_tokens
    overlap = len(sig_tokens & pos_tokens) / max(len(union), 1)

    if overlap > 0.7:
        return 0.95  # Effectively same event
    if position.get('domain', '') == signal_domain:
        return 0.70 if overlap > 0.3 else 0.35
    return 0.10


def check_R01(signal_domain: str, signal_market: str,
              kelly_usdc: float, portfolio: dict) -> tuple[bool, str]:
    """R01 correlation risk gate. Returns (passed, reason)."""
    bankroll = portfolio.get('bankroll', DEFAULT_BANKROLL)
    positions = portfolio.get('positions', [])
    domain_exposure = portfolio.get('domain_exposure', {})

    # C1 — single event cap
    event_exposure = kelly_usdc
    for pos in positions:
        if pos.get('status') != 'open':
            continue
        corr = _estimate_correlation(signal_market, signal_domain, pos)
        if corr > 0.80:
            event_exposure += pos.get('size_usd', 0)
        elif corr > 0.50:
            event_exposure += pos.get('size_usd', 0) * corr

    c1_limit = bankroll * C1_SINGLE_EVENT_CAP
    if event_exposure > c1_limit:
        return False, (f"C1: event exposure ${event_exposure:.0f} "
                       f"> ${c1_limit:.0f} cap")

    # C2 — domain concentration cap
    current = domain_exposure.get(signal_domain, 0)
    if current + kelly_usdc > bankroll * C2_DOMAIN_CAP:
        return False, (f"C2: {signal_domain} ${current + kelly_usdc:.0f} "
                       f"> ${bankroll * C2_DOMAIN_CAP:.0f} cap")

    return True, "R01 passed"


# ---------------------------------------------------------------------------
# Pending signal management
# ---------------------------------------------------------------------------

def count_pending_signals() -> int:
    """Count signals with status='pending' in signals.jsonl."""
    if not SIGNALS_PATH.exists():
        return 0
    count = 0
    try:
        with open(SIGNALS_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        if json.loads(line).get('status') == 'pending':
                            count += 1
                    except json.JSONDecodeError:
                        continue
    except IOError:
        pass
    return count


# ---------------------------------------------------------------------------
# Signal generator
# ---------------------------------------------------------------------------

class SignalGenerator:
    """Converts TruthExtractionResults into sized, risk-checked trading signals.

    Pipeline per market_relevance entry:
      market_relevance → Polymarket match → B05 adjust → strategy route
      → YES discount → Kelly size → R01 check → emit or reject.
    """

    def __init__(self, bankroll: float | None = None):
        self.portfolio = load_positions()
        self.bankroll = bankroll or self.portfolio.get('bankroll', DEFAULT_BANKROLL)

    def generate(self, extraction: TruthExtractionResult,
                 cluster: EventCluster | None = None) -> list[GeneratedSignal]:
        """Generate trading signals from a truth extraction.

        Args:
            extraction: TruthExtractionResult from NB06.
            cluster: Optional EventCluster for B05 reliability tone data.

        Returns:
            List of GeneratedSignal objects (may be empty if all rejected).
        """
        if not extraction.market_relevance:
            return []

        # Compute aggregate reliability-weighted tone from cluster
        rwt = self._aggregate_rwt(cluster)

        signals = []
        for mr in extraction.market_relevance:
            signal = self._score_one(mr, extraction, rwt)
            if signal is not None:
                signals.append(signal)

        return signals

    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_rwt(cluster: EventCluster | None) -> float:
        """Weighted average of reliability_weighted_tone across perspectives."""
        if cluster is None:
            return 0.0
        pm = getattr(cluster, 'perspective_matrix', None)
        if pm is None:
            return 0.0
        clusters = getattr(pm, 'clusters', None)
        if not clusters:
            return 0.0

        total_n = 0
        weighted = 0.0
        for cv in clusters.values():
            n = getattr(cv, 'article_count', 1)
            t = getattr(cv, 'reliability_weighted_tone', 0.0)
            weighted += n * t
            total_n += n
        return weighted / total_n if total_n else 0.0

    def _score_one(self, mr: dict, extraction: TruthExtractionResult,
                   rwt: float) -> GeneratedSignal | None:
        """Process a single market_relevance entry through the full pipeline."""
        category = mr.get('category', '')
        description = mr.get('description', '')
        direction = mr.get('direction', 'YES').upper()
        prob_shift = float(mr.get('probability_shift', 0))
        mr_confidence = float(mr.get('confidence', 0.5))

        if not description:
            return None

        # 1. Market match
        markets = search_active_markets(description, max_results=3)
        if not markets:
            logger.info("No market match: %s", description[:60])
            return None

        best = markets[0]
        market_id = best['condition_id']
        market_question = best['question']
        # YES price from API; for NO direction we work in NO-probability space
        yes_price = best['current_price']
        current_price = (1.0 - yes_price) if direction == 'NO' else yes_price

        # 2. Base estimate = current + probability shift from truth extraction
        base = max(0.01, min(0.99, current_price + prob_shift))

        # 3. B05 source bias adjustment
        bias_adjusted = apply_B05(base, rwt, current_price)

        # 4. Strategy routing
        strategy = route_strategy(category)

        # 5. Strategy-specific edge
        strategy_adjusted = apply_strategy_edge(bias_adjusted, strategy, current_price)

        # 6. YES calibration discount
        yes_applied = False
        if direction == 'YES':
            final = strategy_adjusted * YES_DISCOUNT
            yes_applied = True
        else:
            final = strategy_adjusted
        final = max(0.01, min(0.99, final))

        # 7. Edge
        edge = final - current_price

        # Composite confidence
        confidence = extraction.overall_confidence * mr_confidence

        # --- Guardrails ---

        if edge < MIN_EDGE:
            logger.info("Edge %.3f < %.3f: %s", edge, MIN_EDGE, market_question[:50])
            return None

        # Kelly sizing
        denom = 1.0 - current_price
        if denom <= 0.01:
            kelly_frac = 0.0
        else:
            kelly_frac = max(0.0, min(0.25, (edge / denom) * FRACTIONAL_KELLY))
        kelly_usdc = kelly_frac * self.bankroll

        # R01
        domain = category.upper()[:3]
        r01_ok, r01_msg = check_R01(domain, market_question, kelly_usdc, self.portfolio)
        if not r01_ok:
            logger.info("R01 rejected (%s): %s", r01_msg, market_question[:50])
            return None

        # Pending cap
        if count_pending_signals() >= MAX_PENDING:
            logger.info("Pending cap (%d) reached", MAX_PENDING)
            return None

        status = 'pending'
        if confidence < MIN_CONFIDENCE:
            logger.info("Low confidence %.2f — flagged: %s", confidence, market_question[:50])

        signal = GeneratedSignal(
            signal_id=str(uuid.uuid4())[:12],
            cluster_id=extraction.cluster_id,
            market_id=market_id,
            market_question=market_question,
            direction=direction,
            current_price=round(current_price, 4),
            suggested_probability=round(final, 4),
            edge=round(edge, 4),
            kelly_fraction=round(kelly_frac, 4),
            kelly_usdc=round(kelly_usdc, 2),
            strategy_code=strategy,
            confidence=round(confidence, 3),
            yes_discount_applied=yes_applied,
            generated_at=datetime.now(timezone.utc),
            status=status,
        )

        self._log_signal(signal)
        return signal

    @staticmethod
    def _log_signal(signal: GeneratedSignal) -> None:
        """Append signal to signals.jsonl."""
        try:
            SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(SIGNALS_PATH, 'a') as f:
                f.write(json.dumps(signal.to_dict()) + '\n')
        except IOError as e:
            logger.warning("Failed to log signal: %s", e)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _demo():
    """Run demo with synthetic TruthExtractionResult."""
    print("=" * 70)
    print("NB07 SIGNAL GENERATOR — Demo")
    print("=" * 70)

    now = datetime.now(timezone.utc)

    extraction = TruthExtractionResult(
        cluster_id='demo_iran_nuclear',
        consensus_facts=[
            'Iran nuclear talks stalled over IAEA inspection demands',
            'Western diplomats set March deadline for progress',
        ],
        contested_claims=[
            {'claim': 'Iran accelerating enrichment',
             'support': 'Western', 'deny': 'Iranian'},
        ],
        motivated_omissions={'Iranian': 'Omits IAEA non-compliance findings'},
        objective_kernel='Iran nuclear talks stalled. Western sources report '
                         'enrichment acceleration; Iran maintains civilian narrative.',
        market_relevance=[
            {
                'category': 'GEO',
                'description': 'US or Israel strike Iran military nuclear',
                'direction': 'YES',
                'probability_shift': 0.08,
                'confidence': 0.7,
            },
            {
                'category': 'GEO',
                'description': 'Iran nuclear deal agreement 2026',
                'direction': 'NO',
                'probability_shift': 0.12,
                'confidence': 0.6,
            },
        ],
        overall_confidence=0.72,
        requires_human_review=False,
        model_used='claude-sonnet-4-6',
        extracted_at=now,
    )

    print(f"\nCluster: {extraction.cluster_id}")
    print(f"Confidence: {extraction.overall_confidence}")
    print(f"Market relevance entries: {len(extraction.market_relevance)}")
    for i, mr in enumerate(extraction.market_relevance, 1):
        print(f"  [{i}] {mr['description']} -> {mr['direction']} "
              f"(shift: {mr['probability_shift']}, conf: {mr['confidence']})")

    print("\nSearching Polymarket for matching markets...")

    gen = SignalGenerator()
    signals = gen.generate(extraction)

    print(f"\nGenerated {len(signals)} signal(s):")
    for s in signals:
        flag = " [LOW CONF]" if s.confidence < MIN_CONFIDENCE else ""
        print(f"\n  ID:         {s.signal_id}")
        print(f"  Market:     {s.market_question[:70]}")
        print(f"  Direction:  {s.direction} | Current: {s.current_price:.1%} | "
              f"Suggested: {s.suggested_probability:.1%}")
        print(f"  Edge:       {s.edge:+.1%} | Kelly: ${s.kelly_usdc:.2f} "
              f"({s.kelly_fraction:.1%} bankroll)")
        print(f"  Strategy:   {s.strategy_code} | Confidence: {s.confidence:.2f}{flag}")
        print(f"  YES disc:   {'applied' if s.yes_discount_applied else 'no'}")

    if not signals:
        print("  (All rejected by guardrails — check edge/R01/confidence thresholds)")


def _show():
    """Show recent signals from signals.jsonl."""
    if not SIGNALS_PATH.exists():
        print("No signals generated yet.")
        return

    entries = []
    with open(SIGNALS_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not entries:
        print("No signals generated yet.")
        return

    print(f"\n{'Time':<20} {'Market':<40} {'Dir':>3} {'Price':>6} {'Est':>6} "
          f"{'Edge':>6} {'$Kelly':>8} {'Strat':>5} {'Conf':>5} {'Status':>8}")
    print("-" * 120)

    for e in entries[-20:]:
        ts = e.get('generated_at', '?')[:19]
        q = e.get('market_question', '?')[:38]
        print(f"{ts:<20} {q:<40} {e.get('direction','?'):>3} "
              f"{e.get('current_price',0):>5.1%} "
              f"{e.get('suggested_probability',0):>5.1%} "
              f"{e.get('edge',0):>+5.1%} "
              f"${e.get('kelly_usdc',0):>7.2f} "
              f"{e.get('strategy_code','?'):>5} "
              f"{e.get('confidence',0):>5.2f} "
              f"{e.get('status','?'):>8}")


def _test():
    """Unit tests for signal scoring logic (no network calls)."""
    print("=" * 70)
    print("NB07 SIGNAL GENERATOR — Unit Tests")
    print("=" * 70)

    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name} -- {detail}")

    # ── B05 ───────────────────────────────────────────────────────────
    print("\n[B05 Source Bias Adjustment]")

    adj = apply_B05(0.70, 3.0, 0.50)
    check("High reliability moves estimate toward raw",
          0.64 < adj < 0.70, f"got {adj:.4f}")

    adj = apply_B05(0.70, 0.3, 0.50)
    check("Low reliability stays near current price",
          0.50 < adj < 0.55, f"got {adj:.4f}")

    adj = apply_B05(0.70, 0.0, 0.50)
    check("Zero tone -> minimal movement",
          adj < 0.55, f"got {adj:.4f}")

    adj = apply_B05(0.30, -2.0, 0.50)
    check("Negative tone direction preserved",
          adj < 0.50, f"got {adj:.4f}")

    # Bounds
    adj = apply_B05(0.001, 5.0, 0.99)
    check("B05 clamp lower bound", adj >= 0.01, f"got {adj}")
    adj = apply_B05(0.999, 5.0, 0.01)
    check("B05 clamp upper bound", adj <= 0.99, f"got {adj}")

    # ── Strategy Routing ──────────────────────────────────────────────
    print("\n[Strategy Routing]")

    check("GEO -> S004", route_strategy('GEO') == 'S004')
    check("POL -> S001", route_strategy('POL') == 'S001')
    check("ECO -> S006", route_strategy('ECO') == 'S006')
    check("TEC -> S006", route_strategy('TEC') == 'S006')
    check("Unknown -> S001", route_strategy('XYZ') == 'S001')
    check("R04 fast-resolution override for POL",
          route_strategy('POL', days_to_resolution=3) == 'S006')
    check("S004 keeps timing on fast-res",
          route_strategy('GEO', days_to_resolution=3) == 'S004')

    # ── Strategy Edge ─────────────────────────────────────────────────
    print("\n[Strategy Edge]")

    adj = apply_strategy_edge(0.40, 'S004', 0.60)
    check("S004 40%% reversion: 0.60 + 0.40*(0.40-0.60) = 0.52",
          abs(adj - 0.52) < 0.001, f"got {adj:.4f}")

    adj = apply_strategy_edge(0.40, 'S001', 0.60)
    check("S001 pass-through", adj == 0.40, f"got {adj}")

    adj = apply_strategy_edge(0.40, 'S006', 0.60)
    check("S006 pass-through", adj == 0.40, f"got {adj}")

    # ── YES Discount ──────────────────────────────────────────────────
    print("\n[YES Discount]")

    check("YES discount constant = 0.85", YES_DISCOUNT == 0.85)
    check("Discount lowers YES estimate", 0.70 * YES_DISCOUNT < 0.70)

    # ── Kelly Sizing ──────────────────────────────────────────────────
    print("\n[Kelly Sizing]")

    edge, cp = 0.10, 0.50
    k = (edge / (1.0 - cp)) * FRACTIONAL_KELLY
    check("Quarter Kelly: edge=10pp, price=50%%",
          abs(k - 0.05) < 0.001, f"got {k:.4f}")

    edge, cp = 0.05, 0.90
    k = (edge / (1.0 - cp)) * FRACTIONAL_KELLY
    check("Kelly larger at high base price",
          k > 0.10, f"got {k:.4f}")

    # ── R01 ───────────────────────────────────────────────────────────
    print("\n[R01 Correlation Risk Check]")

    portfolio = {
        'bankroll': 10000,
        'positions': [
            {'market': 'US strikes Iran by June 30', 'domain': 'GEO',
             'size_usd': 300, 'status': 'open'},
        ],
        'domain_exposure': {'GEO': 350, 'POL': 625},
    }

    ok, msg = check_R01('GEO', 'Iran nuclear strike 2026', 200, portfolio)
    check("C1 blocks correlated Iran addition", not ok, msg)

    ok, msg = check_R01('TEC', 'OpenAI GPT-5 release date', 100, portfolio)
    check("R01 passes uncorrelated TEC position", ok, msg)

    ok, msg = check_R01('POL', 'Trump executive order 2026', 200, portfolio)
    check("C2 blocks POL over domain cap (625+200 > 500)", not ok, msg)

    ok, msg = check_R01('CRY', 'Bitcoin halving 2026', 50, portfolio)
    check("R01 passes small CRY position", ok, msg)

    # ── Market Matching (offline) ─────────────────────────────────────
    print("\n[Market Matching — Tokenizer & Scoring]")

    tokens = _tokenize("US strikes Iran nuclear weapons 2026")
    check("Tokenizer extracts keywords",
          {'us', 'strikes', 'iran', 'nuclear'}.issubset(tokens))

    score = _match_score({'iran', 'strike', 'nuclear'},
                         'Will the US or Israel strike Iran by March 31?')
    check("Related market scores >= 0.3", score >= 0.3, f"score={score:.3f}")

    score = _match_score({'iran', 'strike', 'nuclear'},
                         'Will Bitcoin reach $100K?')
    check("Unrelated market scores < 0.3", score < 0.3, f"score={score:.3f}")

    # ── Pending Counter ───────────────────────────────────────────────
    print("\n[Pending Signal Counter]")
    n = count_pending_signals()
    check("Pending count is non-negative integer", isinstance(n, int) and n >= 0)

    # ── Summary ───────────────────────────────────────────────────────
    total = passed + failed
    print(f"\n{'=' * 70}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print(f"{'=' * 70}")
    return failed == 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    if '--demo' in sys.argv:
        _demo()
    elif '--show' in sys.argv:
        _show()
    elif '--test' in sys.argv:
        success = _test()
        sys.exit(0 if success else 1)
    else:
        print("Usage:")
        print("  python3 scripts/signal_generator.py --demo    Run synthetic demo")
        print("  python3 scripts/signal_generator.py --show    Show recent signals")
        print("  python3 scripts/signal_generator.py --test    Run unit tests")
        print()
        print("As library:")
        print("  from signal_generator import SignalGenerator")
        print("  gen = SignalGenerator()")
        print("  signals = gen.generate(extraction, cluster)")
