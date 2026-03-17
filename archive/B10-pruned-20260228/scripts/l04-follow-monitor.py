#!/usr/bin/env python3
"""
L04 Follow Monitor — Insider Signal Decision Framework

Checks classified insiders (L03 output) or whale registry (fallback) for
trades that may support or contradict our current positions. Applies the
4-gate decision framework and outputs actionable alerts.

Usage:
    python scripts/l04-follow-monitor.py                    # Full scan
    python scripts/l04-follow-monitor.py --wallet 0x...     # Single wallet
    python scripts/l04-follow-monitor.py --domain GEO       # Filter by domain
    python scripts/l04-follow-monitor.py --json             # Machine-readable
    python scripts/l04-follow-monitor.py --dry-run          # Skip API calls
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"

# Data sources (L03 preferred, whale registry as fallback)
CLASSIFIED_INSIDERS_PATH = DATA_DIR / "classified-insiders.json"
WHALE_REGISTRY_PATH = DATA_DIR / "whale-registry.json"
POSITIONS_PATH = PROJECT_DIR / "strategies" / "paper-trades" / "positions.json"
BANKROLL_PATH = PROJECT_DIR / "strategies" / "BANKROLL.md"
FOLLOW_SIGNALS_PATH = DATA_DIR / "follow-signals.jsonl"

GAMMA_API = "https://gamma-api.polymarket.com"
POLYGONSCAN_API = "https://api.polygonscan.com/api"
POLYGONSCAN_DELAY = 0.25  # 5 req/s free tier

# CTF Exchange addresses (Polygon Mainnet)
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEGRISK_CTF = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

# ── Domain classification ──────────────────────────────────────────────

DOMAIN_KEYWORDS = {
    'GEO': ['iran', 'strike', 'war', 'military', 'invasion', 'ceasefire',
            'nato', 'ukraine', 'russia', 'israel', 'gaza', 'hamas',
            'hezbollah', 'taiwan', 'china threat', 'north korea', 'maduro',
            'venezuela', 'conflict'],
    'POL': ['president', 'trump', 'biden', 'election', 'governor', 'senate',
            'congress', 'nominee', 'nomination', 'vance', 'republican',
            'democrat', 'gop', 'dnc', 'rnc', 'impeach', 'executive order',
            'cabinet', 'starmer', 'macron'],
    'ECO': ['fed ', 'fomc', 'interest rate', 'inflation', 'cpi', 'gdp',
            'recession', 'unemployment', 'tariff', 'trade war', 'pce',
            'rate cut', 'rate hike', 'ecb', 'lagarde', 'treasury'],
    'CRY': ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'token',
            'solana', 'defi', 'nft', 'altcoin', 'halving', 'etf approval'],
    'TEC': ['ai ', 'artificial intelligence', 'openai', 'gpt', 'claude',
            'google', 'apple', 'microsoft', 'nvidia', 'semiconductor',
            'chip', 'antitrust', 'tiktok'],
    'FIN': ['s&p', 'nasdaq', 'dow', 'stock', 'gold', 'oil price',
            'commodity', 'treasury yield'],
    'LAW': ['supreme court', 'scotus', 'lawsuit', 'indictment', 'trial',
            'verdict', 'ruling', 'regulate'],
    'SOC': ['oscars', 'super bowl', 'grammy', 'person of the year',
            'viral', 'celebrity'],
    'SCI': ['climate', 'pandemic', 'vaccine', 'fda', 'who ', 'cdc'],
    'SPS': ['nba', 'nfl', 'mlb', 'ufc', 'fight', 'match', 'game',
            'playoff', 'championship', 'world series', 'super bowl'],
}


def classify_domain(question):
    q = question.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                return domain
    return 'OTHER'


# ── API helpers ────────────────────────────────────────────────────────

def curl_json(url, timeout=15):
    """Fetch JSON from URL via curl (matches codebase pattern)."""
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', str(timeout),
             '-H', 'User-Agent: Mozilla/5.0',
             url],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (json.JSONDecodeError, Exception):
        return None


def fetch_active_markets(limit=100, offset=0):
    """Fetch active markets from Gamma API."""
    url = (f"{GAMMA_API}/markets?limit={limit}&offset={offset}"
           f"&closed=false&order=volume&ascending=false")
    return curl_json(url) or []


def fetch_market_by_slug(slug):
    """Fetch a specific market by slug."""
    url = f"{GAMMA_API}/markets/{slug}"
    return curl_json(url)


# ── Data loading ───────────────────────────────────────────────────────

def _is_synthetic(accounts):
    """Detect placeholder/synthetic data (e.g. 0x1111...1111)."""
    for a in accounts[:3]:
        wallet = a.get("wallet", "")
        if len(set(wallet.replace("0x", ""))) <= 2:
            return True
    return False


def load_insiders():
    """Load classified insiders (L03) or fall back to whale registry.

    If classified-insiders.json contains synthetic data (placeholder wallets),
    falls back to whale-registry.json instead.
    """
    source = "classified-insiders"

    if CLASSIFIED_INSIDERS_PATH.exists():
        with open(CLASSIFIED_INSIDERS_PATH) as f:
            data = json.load(f)
        accounts = data.get("accounts", data) if isinstance(data, dict) else data
        if not _is_synthetic(accounts):
            return accounts, source
        # Synthetic data — fall through to whale registry
        print("NOTE: classified-insiders.json contains synthetic data, using whale-registry",
              file=sys.stderr)

    if WHALE_REGISTRY_PATH.exists():
        source = "whale-registry"
        with open(WHALE_REGISTRY_PATH) as f:
            accounts = json.load(f)
        # Normalise whale-registry fields to L03 format
        normalised = []
        for w in accounts:
            normalised.append({
                "wallet": w.get("wallet", ""),
                "alias": w.get("alias", "Unknown"),
                "account_type": "INSIDER" if w.get("follow_confidence", 0) >= 4 else "SPECIALIST",
                "insider_score": _confidence_to_score(w.get("follow_confidence", 1)),
                "dominant_category": w.get("domain_focus", ["OTHER"])[0] if w.get("domain_focus") else "OTHER",
                "secondary_category": w["domain_focus"][1] if len(w.get("domain_focus", [])) > 1 else None,
                "top_category_n": None,  # Unknown from registry
                "follow_confidence": w.get("follow_confidence", 1),
                "notes": w.get("notes", ""),
                "known_strategy": w.get("known_strategy", ""),
                "typical_timing": w.get("typical_timing", ""),
                "win_rate": w.get("win_rate"),
                "estimated_total_profit": w.get("estimated_total_profit"),
                "cluster": w.get("cluster"),
                # Preserve domain_focus list for multi-domain wallets
                "_domain_focus": w.get("domain_focus", []),
            })
        return normalised, source

    print("ERROR: No insider data found.", file=sys.stderr)
    print(f"  Expected: {CLASSIFIED_INSIDERS_PATH}", file=sys.stderr)
    print(f"  Fallback: {WHALE_REGISTRY_PATH}", file=sys.stderr)
    sys.exit(1)


def _confidence_to_score(confidence):
    """Map follow_confidence (1-5) to approximate insider_score (0-10)."""
    return {1: 2.0, 2: 4.0, 3: 5.5, 4: 7.0, 5: 9.0}.get(confidence, 2.0)


def load_positions():
    """Load current paper-trade positions."""
    if not POSITIONS_PATH.exists():
        return []
    with open(POSITIONS_PATH) as f:
        data = json.load(f)
    return [p for p in data.get("positions", []) if p.get("status") == "open"]


# ── Gate Framework ─────────────────────────────────────────────────────

def gate1_field_match(insider, market_domain):
    """Gate 1: Does the market fall within the insider's dominant field?"""
    dominant = insider.get("dominant_category", "")
    secondary = insider.get("secondary_category")
    domain_focus = insider.get("_domain_focus", [dominant])

    if market_domain in domain_focus or market_domain == dominant:
        return True, "MATCH", f"{market_domain} in [{', '.join(domain_focus)}]"
    if secondary and market_domain == secondary:
        return True, "SECONDARY", f"{market_domain} = secondary field"
    return False, "NO_MATCH", f"{market_domain} not in [{', '.join(domain_focus)}]"


def gate2_direction_check(insider_direction, position):
    """Gate 2: Does the insider's likely direction agree or contradict our position?"""
    if position is None:
        return "AGREE_NO_POSITION", "No existing position — new entry opportunity"

    our_direction = position.get("direction", "").upper()

    # For now, we infer insider direction from their domain expertise
    # Full implementation requires on-chain trade detection
    if insider_direction == our_direction:
        return "AGREE_WITH_POSITION", f"Confirms our {our_direction} thesis"
    elif insider_direction:
        return "CONTRADICT_POSITION", f"Insider favours {insider_direction}, we hold {our_direction}"
    else:
        return "UNKNOWN", "Direction unknown — cannot determine agreement"


def gate3_timing_quality(resolution_date_str):
    """Gate 3: How much time remains before resolution?"""
    if not resolution_date_str:
        return 1.0, "UNKNOWN", "No resolution date"

    try:
        res_date = datetime.strptime(resolution_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return 1.0, "UNKNOWN", f"Cannot parse: {resolution_date_str}"

    now = datetime.now(timezone.utc)
    days_remaining = (res_date - now).days

    if days_remaining > 30:
        return 0.85, ">30d", f"{days_remaining}d — patient entry, slight confidence reduction"
    elif days_remaining >= 8:
        return 1.0, "8-30d", f"{days_remaining}d — sweet spot, full confidence"
    elif days_remaining >= 2:
        return 1.15, "2-7d", f"{days_remaining}d — elevated conviction"
    else:
        return 0.5, "<48h", f"{days_remaining}d — heavy discount, check if priced in"


def gate4_price_impact(market_data=None):
    """Gate 4: Has the insider's bet already moved the price?

    Full implementation requires on-chain trade timestamp + historical prices.
    Currently returns conservative estimate.
    """
    if market_data is None:
        return 1.0, "UNKNOWN", "No market data — assuming no price impact"

    # Use 1-day price change as proxy
    one_day_change = market_data.get("oneDayPriceChange")
    if one_day_change is not None:
        try:
            change = abs(float(one_day_change))
        except (ValueError, TypeError):
            return 1.0, "UNKNOWN", "Cannot parse price change"

        if change > 0.05:
            return 0.7, "PARTIALLY_PRICED", f"1d change {change:.1%} — signal partially priced in"
        elif change > 0.01:
            return 0.9, "SLIGHT_MOVE", f"1d change {change:.1%} — minor price movement"
        else:
            return 1.0, "NOT_PRICED", f"1d change {change:.1%} — signal not yet priced in"

    return 1.0, "UNKNOWN", "No price change data"


# ── Insider Conviction Multiplier ──────────────────────────────────────

def compute_icm(insider, timing_modifier=1.0):
    """Compute Insider Conviction Multiplier (0.5x to 2.0x standard size)."""
    base = 1.0

    # 1. Insider score adjustment (0-10 scale)
    score = insider.get("insider_score", 5.0)
    if score < 4:
        score_adj = 0.5
    elif score < 6:
        score_adj = 0.8
    elif score < 8:
        score_adj = 1.0
    else:
        score_adj = 1.25

    # 2. Follow confidence adjustment (1-5 scale)
    conf = insider.get("follow_confidence", 3)
    conf_map = {1: 0.5, 2: 0.7, 3: 1.0, 4: 1.3, 5: 1.6}
    conf_adj = conf_map.get(conf, 1.0)

    # 3. Sample size adjustment
    n = insider.get("top_category_n")
    if n is None:
        n_adj = 0.9  # Unknown sample size → slight penalty
    elif n < 20:
        n_adj = 0.8
    elif n < 50:
        n_adj = 1.0
    else:
        n_adj = 1.1

    icm = base * score_adj * conf_adj * n_adj * timing_modifier
    return min(2.0, max(0.5, icm))


# ── Position Matching ──────────────────────────────────────────────────

def match_position_to_insider(positions, insider):
    """Check if any open position overlaps with this insider's domain."""
    matches = []
    dominant = insider.get("dominant_category", "")
    domain_focus = insider.get("_domain_focus", [dominant])

    for pos in positions:
        pos_domain = pos.get("domain", "")
        if pos_domain in domain_focus:
            matches.append(pos)

    return matches


# ── Signal Generation ──────────────────────────────────────────────────

def generate_signal(insider, position, gates, icm):
    """Generate a follow signal from gate results."""
    g1_pass, g1_status, g1_detail = gates["gate1"]
    g2_outcome, g2_detail = gates["gate2"]
    g3_modifier, g3_window, g3_detail = gates["gate3"]
    g4_modifier, g4_status, g4_detail = gates["gate4"]

    # Decision logic
    if not g1_pass:
        action = "IGNORE"
        reason = f"Field mismatch: {g1_detail}"
    elif g2_outcome == "CONTRADICT_POSITION":
        insider_score = insider.get("insider_score", 5.0)
        if insider_score >= 8.0:
            action = "INVESTIGATE_URGENT"
            reason = f"High-score insider contradicts position (score {insider_score})"
        else:
            action = "INVESTIGATE"
            reason = f"Insider contradicts position: {g2_detail}"
    elif g2_outcome == "AGREE_NO_POSITION":
        action = "CONSIDER_ENTRY"
        reason = f"Insider signal in their domain, no existing position"
    elif g2_outcome == "AGREE_WITH_POSITION":
        action = "CONFIRM"
        reason = f"Insider confirms our thesis: {g2_detail}"
    elif g2_outcome == "UNKNOWN":
        action = "MONITOR"
        reason = "Direction unknown — track for future signals"
    else:
        action = "MONITOR"
        reason = f"Unhandled direction outcome: {g2_outcome}"

    signal = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "insider_alias": insider.get("alias", "Unknown"),
        "insider_wallet": insider.get("wallet", "")[:10] + "...",
        "insider_score": insider.get("insider_score", 0),
        "follow_confidence": insider.get("follow_confidence", 0),
        "dominant_field": insider.get("dominant_category", ""),
        "position_trade_id": position.get("trade_id") if position else None,
        "position_market": position.get("market") if position else None,
        "position_direction": position.get("direction") if position else None,
        "gate1": {"pass": g1_pass, "status": g1_status, "detail": g1_detail},
        "gate2": {"outcome": g2_outcome, "detail": g2_detail},
        "gate3": {"modifier": g3_modifier, "window": g3_window, "detail": g3_detail},
        "gate4": {"modifier": g4_modifier, "status": g4_status, "detail": g4_detail},
        "icm": round(icm, 2),
        "action": action,
        "reason": reason,
    }

    return signal


# ── Display ────────────────────────────────────────────────────────────

def print_signal(signal, verbose=True):
    """Print formatted alert for a signal."""
    action = signal["action"]

    # Colour-code by action
    icons = {
        "IGNORE": "  ",
        "MONITOR": "👁 ",
        "CONFIRM": "✓ ",
        "CONSIDER_ENTRY": "→ ",
        "INVESTIGATE": "⚠ ",
        "INVESTIGATE_URGENT": "‼ ",
    }
    icon = icons.get(action, "  ")

    if action == "IGNORE" and not verbose:
        return

    width = 78
    print()
    print("=" * width)
    print(f" L04 FOLLOW SIGNAL — {signal['timestamp'][:19]}Z")
    print("=" * width)
    print()
    print(f"  INSIDER:  {signal['insider_alias']} "
          f"(score: {signal['insider_score']}, conf: {signal['follow_confidence']}/5)")
    print(f"  WALLET:   {signal['insider_wallet']}")
    print(f"  FIELD:    {signal['dominant_field']}")

    if signal.get("position_trade_id"):
        print()
        print(f"  POSITION: {signal['position_trade_id']} — {signal['position_market']}")
        print(f"  OUR DIR:  {signal['position_direction']}")

    print()
    g1 = signal["gate1"]
    g2 = signal["gate2"]
    g3 = signal["gate3"]
    g4 = signal["gate4"]

    g1_mark = "✓" if g1["pass"] else "✗"
    print(f"  GATE 1 [{g1_mark}] Field:     {g1['detail']}")
    g2_mark = "✓" if g2["outcome"] in ("AGREE_NO_POSITION", "AGREE_WITH_POSITION") else "✗" if "CONTRADICT" in g2["outcome"] else "?"
    print(f"  GATE 2 [{g2_mark}] Direction: {g2['detail']}")
    print(f"  GATE 3 [·] Timing:    {g3['detail']} (modifier: {g3['modifier']:.2f})")
    print(f"  GATE 4 [·] Impact:    {g4['detail']} (modifier: {g4['modifier']:.2f})")

    print()
    print(f"  {icon}DECISION: {action}")
    print(f"  REASON:   {signal['reason']}")
    print(f"  ICM:      {signal['icm']:.2f}x standard size")
    print()
    print("-" * width)


def print_summary(signals, source):
    """Print summary table of all signals."""
    width = 78
    print()
    print("=" * width)
    print(f" L04 FOLLOW MONITOR — SUMMARY")
    print(f" Source: {source}")
    print(f" Scan time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print("=" * width)

    # Group by action
    actions = {}
    for s in signals:
        a = s["action"]
        actions.setdefault(a, []).append(s)

    priority_order = [
        "INVESTIGATE_URGENT", "INVESTIGATE", "CONSIDER_ENTRY",
        "CONFIRM", "MONITOR", "IGNORE"
    ]

    total_actionable = 0
    for action in priority_order:
        group = actions.get(action, [])
        if not group:
            continue
        if action not in ("IGNORE", "MONITOR"):
            total_actionable += len(group)

        print(f"\n  {action} ({len(group)}):")
        for s in group:
            tid = s.get("position_trade_id") or "-"
            print(f"    {s['insider_alias']:<20} → {tid:<5}  "
                  f"ICM {s['icm']:.1f}x  {s['reason'][:40]}")

    print()
    print(f"  Total signals: {len(signals)}")
    print(f"  Actionable:    {total_actionable}")
    print("=" * width)
    print()


# ── JSONL logging ──────────────────────────────────────────────────────

def append_signal_jsonl(signal):
    """Append signal to follow-signals.jsonl."""
    with open(FOLLOW_SIGNALS_PATH, 'a') as f:
        f.write(json.dumps(signal) + '\n')


# ── Main scan ──────────────────────────────────────────────────────────

def run_scan(args):
    """Run the full L04 follow monitor scan."""
    insiders, source = load_insiders()
    positions = load_positions()

    if args.wallet:
        insiders = [i for i in insiders if args.wallet.lower() in i.get("wallet", "").lower()]
        if not insiders:
            print(f"No insider found matching wallet: {args.wallet}", file=sys.stderr)
            return []

    if args.domain:
        insiders = [i for i in insiders
                    if args.domain.upper() in i.get("_domain_focus", [i.get("dominant_category", "")])]

    print(f"Loading {len(insiders)} insiders from {source}...")
    print(f"Checking against {len(positions)} open positions...")

    signals = []

    for insider in insiders:
        alias = insider.get("alias", "Unknown")
        dominant = insider.get("dominant_category", "OTHER")
        domain_focus = insider.get("_domain_focus", [dominant])

        # Check each position against this insider
        matched_positions = match_position_to_insider(positions, insider)

        if matched_positions:
            for pos in matched_positions:
                pos_domain = pos.get("domain", "OTHER")

                # Gate 1: Field match
                g1 = gate1_field_match(insider, pos_domain)

                # Gate 2: Direction check
                # Without on-chain data, we can't know insider's current direction.
                # For known wallets, use their documented thesis if available.
                insider_dir = _infer_direction(insider, pos)
                g2 = gate2_direction_check(insider_dir, pos)

                # Gate 3: Timing
                g3 = gate3_timing_quality(pos.get("resolution_date"))

                # Gate 4: Price impact (would need live market data)
                g4 = gate4_price_impact(None)

                gates = {"gate1": g1, "gate2": g2, "gate3": g3, "gate4": g4}
                icm = compute_icm(insider, g3[0])
                signal = generate_signal(insider, pos, gates, icm)
                signals.append(signal)
        else:
            # Insider has no overlap with our positions — check if they cover
            # domains we're watching but haven't entered
            for domain in domain_focus:
                g1 = gate1_field_match(insider, domain)
                g2 = gate2_direction_check(None, None)
                g3 = (1.0, "N/A", "No specific market")
                g4 = (1.0, "N/A", "No market data")
                gates = {"gate1": g1, "gate2": g2, "gate3": g3, "gate4": g4}
                icm = compute_icm(insider, 1.0)
                signal = generate_signal(insider, {}, gates, icm)
                signals.append(signal)

    return signals, source


def _infer_direction(insider, position):
    """Infer insider's likely direction from their documented profile.

    This is a HEURISTIC until on-chain trade data is available from L01-L03.
    Returns None if direction can't be inferred.
    """
    alias = insider.get("alias", "").lower()
    notes = insider.get("notes", "").lower()
    market = position.get("market", "").lower()

    # ricosuave666: 100% Israel bet win rate, reactivated for Iran strikes
    # Their historical pattern is GEO-bullish (events DO happen)
    if "ricosuave666" in alias:
        if "iran" in market or "israel" in market:
            # ricosuave666 historically bets YES on Israel/Iran events
            return "YES"

    # Theo cluster: POL specialist, commissioned private polling
    if insider.get("cluster") == "theo":
        return None  # Can't infer without specific trade data

    # scottilicious: Bond strategy, enters late at >70% for reliable returns
    if "scottilicious" in alias:
        return None  # His strategy is to buy high-prob, can't infer direction

    return None  # Default: cannot infer


# ── Entry point ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="L04 Follow Monitor — Insider Signal Decision Framework"
    )
    parser.add_argument("--wallet", help="Filter to specific wallet address")
    parser.add_argument("--domain", help="Filter to specific domain (GEO, POL, etc)")
    parser.add_argument("--json", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show all signals including IGNORE")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip API calls, use cached/inferred data only")
    parser.add_argument("--no-log", action="store_true",
                        help="Don't append to follow-signals.jsonl")
    args = parser.parse_args()

    signals, source = run_scan(args)

    if args.json:
        print(json.dumps(signals, indent=2))
    else:
        # Print individual signals (skip IGNORE unless verbose)
        actionable = [s for s in signals if s["action"] != "IGNORE"]
        display = signals if args.verbose else actionable

        for signal in display:
            print_signal(signal, verbose=args.verbose)

        print_summary(signals, source)

    # Log to JSONL
    if not args.no_log:
        for s in signals:
            if s["action"] not in ("IGNORE",):
                append_signal_jsonl(s)

    # Return exit code: 2 if urgent investigation needed
    if any(s["action"] == "INVESTIGATE_URGENT" for s in signals):
        sys.exit(2)
    elif any(s["action"] == "INVESTIGATE" for s in signals):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
