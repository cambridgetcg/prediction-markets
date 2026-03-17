#!/usr/bin/env python3
"""
Fresh Wallet Detector — monitors markets for insider-pattern activity.

Watches markets in our portfolio + watchlist for large bets from
wallets with minimal transaction history. B9-02 complements B9-01
(known insider tracking) by catching UNKNOWN insiders via behavioral
pattern detection.

Pattern: Fresh wallet → fund from exchange → one large directional bet
         → wait for resolution → profit → abandon wallet

Usage:
    python3 fresh-wallet-detector.py                     # Scan portfolio markets
    python3 fresh-wallet-detector.py --market "Iran"     # Specific market keyword
    python3 fresh-wallet-detector.py --continuous        # Poll every 30 min
    python3 fresh-wallet-detector.py --threshold 5000    # Min bet size (default $5K)
    python3 fresh-wallet-detector.py --max-history 10    # Max prior txns (default 10)
    python3 fresh-wallet-detector.py --all-markets       # Scan top markets by volume
    python3 fresh-wallet-detector.py --json              # Machine-readable output
    python3 fresh-wallet-detector.py --dry-run           # Use mock data, skip APIs
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
DETECTED_DIR = DATA_DIR / "detected-wallets"
POSITIONS_PATH = PROJECT_DIR / "strategies" / "paper-trades" / "positions.json"
CATALYST_PATH = DATA_DIR / "catalyst-calendar.json"
ANOMALY_LOG_PATH = DATA_DIR / "fresh-wallet-anomalies.jsonl"

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
POLYGONSCAN_API = "https://api.polygonscan.com/api"
POLYGONSCAN_DELAY = 0.25  # 5 req/s free tier

# CTF Exchange addresses (Polygon Mainnet)
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEGRISK_CTF = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

# Known exchange deposit addresses (Polygon)
KNOWN_EXCHANGES = {
    "0x1ab4973a48dc892cd9971ece8e01dcc7688f8f23": "Coinbase",
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance",
    "0xf89d7b9c864f589bbf53a82105107622b35eaa40": "Bybit",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance",
}

# ── Domain classification (matches l04-follow-monitor.py) ─────────────

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


# ── API helpers ───────────────────────────────────────────────────────

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


def fetch_clob_trades(token_id, limit=100):
    """Fetch recent trades from CLOB API for a specific market token."""
    url = f"{CLOB_API}/trades?asset_id={token_id}&limit={limit}"
    return curl_json(url) or []


def fetch_active_markets(limit=100, offset=0):
    """Fetch active markets from Gamma API."""
    url = (f"{GAMMA_API}/markets?limit={limit}&offset={offset}"
           f"&closed=false&order=volume&ascending=false")
    return curl_json(url) or []


def fetch_wallet_history_polygonscan(wallet, api_key=None):
    """Fetch transaction history for a wallet from Polygonscan.

    Returns dict with: total_txns, first_txn_time, age_days, recent_txns.
    """
    params = {
        "module": "account",
        "action": "txlist",
        "address": wallet,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 50,  # Enough to check freshness
        "sort": "asc",
    }
    if api_key:
        params["apikey"] = api_key

    url = f"{POLYGONSCAN_API}?{urlencode(params)}"
    time.sleep(POLYGONSCAN_DELAY)
    data = curl_json(url, timeout=20)

    if not data or data.get("status") != "1":
        # Try txn count as fallback
        return _fetch_txn_count(wallet, api_key)

    txns = data.get("result", [])
    if not txns:
        return {
            "total_txns": 0,
            "first_txn_time": None,
            "age_days": 0,
            "funding_source": None,
            "funded_from_exchange": False,
            "first_deposit_hours_ago": None,
        }

    first_ts = int(txns[0].get("timeStamp", 0))
    first_time = datetime.fromtimestamp(first_ts, tz=timezone.utc) if first_ts else None
    age_days = (datetime.now(timezone.utc) - first_time).days if first_time else 0

    # Check if first incoming txn is from a known exchange
    funding_source = None
    funded_from_exchange = False
    first_deposit_hours_ago = None
    for tx in txns:
        if tx.get("to", "").lower() == wallet.lower():
            from_addr = tx.get("from", "").lower()
            if from_addr in KNOWN_EXCHANGES:
                funding_source = KNOWN_EXCHANGES[from_addr]
                funded_from_exchange = True
                tx_ts = int(tx.get("timeStamp", 0))
                if tx_ts:
                    deposit_time = datetime.fromtimestamp(tx_ts, tz=timezone.utc)
                    first_deposit_hours_ago = (datetime.now(timezone.utc) - deposit_time).total_seconds() / 3600
                break

    return {
        "total_txns": len(txns),  # Capped at 50; if 50, likely more
        "first_txn_time": first_time.isoformat() if first_time else None,
        "age_days": age_days,
        "funding_source": funding_source,
        "funded_from_exchange": funded_from_exchange,
        "first_deposit_hours_ago": first_deposit_hours_ago,
    }


def _fetch_txn_count(wallet, api_key=None):
    """Fallback: get just the transaction count."""
    params = {
        "module": "proxy",
        "action": "eth_getTransactionCount",
        "address": wallet,
        "tag": "latest",
    }
    if api_key:
        params["apikey"] = api_key

    url = f"{POLYGONSCAN_API}?{urlencode(params)}"
    time.sleep(POLYGONSCAN_DELAY)
    data = curl_json(url, timeout=20)

    count = 0
    if data and data.get("result"):
        try:
            count = int(data["result"], 16)
        except (ValueError, TypeError):
            pass

    return {
        "total_txns": count,
        "first_txn_time": None,
        "age_days": None,
        "funding_source": None,
        "funded_from_exchange": False,
        "first_deposit_hours_ago": None,
    }


# ── Position & Catalyst Loading ──────────────────────────────────────

def load_positions():
    """Load current paper-trade positions."""
    if not POSITIONS_PATH.exists():
        return []
    with open(POSITIONS_PATH) as f:
        data = json.load(f)
    return [p for p in data.get("positions", []) if p.get("status") == "open"]


def load_catalyst_calendar():
    """Load the catalyst calendar for proximity scoring."""
    if not CATALYST_PATH.exists():
        return []
    with open(CATALYST_PATH) as f:
        data = json.load(f)
    return data.get("events", [])


def get_position_for_market(positions, market_question):
    """Find matching open position for a market question."""
    q = market_question.lower()
    for pos in positions:
        pos_market = pos.get("market", "").lower()
        # Fuzzy match: check if key terms overlap
        pos_words = set(pos_market.split())
        q_words = set(q.split())
        overlap = pos_words & q_words
        # Require at least 3 word overlap or substring match
        if len(overlap) >= 3 or pos_market in q or q in pos_market:
            return pos
    return None


# ── Catalyst Proximity ────────────────────────────────────────────────

def nearest_catalyst(market_question, catalysts):
    """Find nearest upcoming catalyst for a market. Returns days or None."""
    if not catalysts or not market_question:
        return None

    now = datetime.now(timezone.utc)
    q = market_question.lower()
    best = None

    for cat in catalysts:
        # Check if catalyst is related to this market
        related = cat.get("related_markets", [])
        matched = any(r.lower() in q or q in r.lower() for r in related)
        if not matched:
            # Fuzzy: check domain + keyword overlap
            event_words = set(cat.get("event", "").lower().split())
            q_words = set(q.split())
            if len(event_words & q_words) < 2:
                continue

        try:
            cat_date = datetime.strptime(cat["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue

        days = (cat_date - now).days
        if days < 0:
            continue  # Expired

        if best is None or days < best:
            best = days

    return best


# ── Anomaly Scoring ───────────────────────────────────────────────────

def score_fresh_wallet_anomaly(wallet_info, trade_size_usd, market_volume,
                               market_question, catalysts):
    """Score 0-10 for fresh wallet insider probability.

    Higher = more suspicious. Thresholds:
      0-3: Log only
      4-6: Flag for manual review
      7+:  ALERT — probable insider (new, unknown)
    """
    score = 0

    total_txns = wallet_info.get("total_txns", 999)
    age_days = wallet_info.get("age_days")

    # Wallet freshness (max 3)
    if total_txns <= 5:
        score += 3
    elif total_txns <= 10:
        score += 2
    elif total_txns <= 20:
        score += 1

    # Wallet age (max 2)
    if age_days is not None:
        if age_days <= 7:
            score += 2
        elif age_days <= 30:
            score += 1

    # Trade size relative to market (max 2)
    if market_volume and market_volume > 0:
        if trade_size_usd > market_volume * 0.02:
            score += 2
        elif trade_size_usd > 10000:
            score += 1
    elif trade_size_usd > 10000:
        score += 1

    # Niche market bonus (max 1)
    if market_volume is not None and market_volume < 50000:
        score += 1

    # Catalyst proximity (max 2)
    days_to_catalyst = nearest_catalyst(market_question, catalysts)
    if days_to_catalyst is not None and days_to_catalyst <= 3:
        score += 2
    elif days_to_catalyst is not None and days_to_catalyst <= 7:
        score += 1

    # Funding from fresh exchange deposit (max 1)
    if wallet_info.get("funded_from_exchange"):
        hours = wallet_info.get("first_deposit_hours_ago")
        if hours is not None and hours < 48:
            score += 1

    return min(score, 10)


# ── Cluster Detection ─────────────────────────────────────────────────

def detect_clusters(anomalies):
    """Detect clusters of fresh wallets betting the same direction on the same market.

    A cluster = 3+ fresh wallets, same direction, same market.
    This is the strongest insider signal — multiple people know something.
    """
    # Group by (market_question, direction)
    groups = {}
    for a in anomalies:
        key = (a.get("market_question", ""), a.get("direction", ""))
        groups.setdefault(key, []).append(a)

    clusters = []
    for (market, direction), members in groups.items():
        if len(members) >= 3:
            clusters.append({
                "market": market,
                "direction": direction,
                "count": len(members),
                "wallets": [m["wallet"] for m in members],
                "total_usd": sum(m.get("trade_size_usd", 0) for m in members),
                "avg_score": sum(m.get("anomaly_score", 0) for m in members) / len(members),
            })

    return clusters


# ── Unknown Insider Profiling ─────────────────────────────────────────

def create_preliminary_profile(wallet_addr, wallet_info, trade_info, score):
    """Create a stub dossier for a newly detected suspected insider."""
    domain = classify_domain(trade_info.get("market_question", ""))
    alias = f"UNKNOWN-{domain}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

    return {
        "wallet": wallet_addr,
        "alias": alias,
        "first_detected": datetime.now(timezone.utc).isoformat(),
        "detection_method": "fresh-wallet-detector",
        "anomaly_score": score,
        "trades": [
            {
                "market": trade_info.get("market_question", ""),
                "domain": domain,
                "direction": trade_info.get("direction", "UNKNOWN"),
                "size_usd": trade_info.get("trade_size_usd", 0),
                "entry_price": trade_info.get("entry_price"),
                "timestamp": trade_info.get("timestamp"),
            }
        ],
        "wallet_info": {
            "total_txns": wallet_info.get("total_txns", 0),
            "age_days": wallet_info.get("age_days"),
            "funding_source": wallet_info.get("funding_source"),
        },
        "status": "monitoring",
        "notes": "",
    }


def save_profile(profile):
    """Save preliminary insider profile to data/detected-wallets/."""
    DETECTED_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{profile['alias']}.json"
    filepath = DETECTED_DIR / filename

    # If file exists (same domain, same day), merge trades
    if filepath.exists():
        with open(filepath) as f:
            existing = json.load(f)
        existing["trades"].extend(profile["trades"])
        existing["anomaly_score"] = max(existing["anomaly_score"], profile["anomaly_score"])
        profile = existing

    with open(filepath, 'w') as f:
        json.dump(profile, f, indent=2)
    return filepath


# ── Portfolio Integration ─────────────────────────────────────────────

def assess_portfolio_impact(anomaly, position):
    """Assess impact of fresh wallet anomaly on our existing position.

    Returns (action, detail) tuple.
    """
    if position is None:
        return "NEW_INTEL", "No position — potential entry signal from unknown insider"

    our_direction = position.get("direction", "").upper()
    anomaly_direction = anomaly.get("direction", "").upper()

    if not anomaly_direction or anomaly_direction == "UNKNOWN":
        return "MONITOR", "Direction unknown — cannot assess agreement"

    if anomaly_direction == our_direction:
        return "CONFIRMATION", (
            f"Fresh wallet AGREES with our {our_direction} position. "
            f"Consider sizing up 25% within C1/C2 caps."
        )
    else:
        return "CONTRADICTION", (
            f"Fresh wallet CONTRADICTS our {our_direction} position "
            f"(insider bets {anomaly_direction}). "
            f"Do NOT panic exit — check if cluster."
        )


def assess_cluster_impact(cluster, position):
    """Assess cluster impact — strongest insider signal."""
    if position is None:
        return "CLUSTER_NEW", (
            f"Cluster of {cluster['count']} fresh wallets betting {cluster['direction']}. "
            f"Strong entry signal from multiple unknown insiders."
        )

    our_direction = position.get("direction", "").upper()
    if cluster["direction"] == our_direction:
        return "CLUSTER_CONFIRM", (
            f"Cluster of {cluster['count']} fresh wallets CONFIRMS our {our_direction}. "
            f"High-confidence confirmation."
        )
    else:
        return "CLUSTER_CONTRADICT", (
            f"CRITICAL: {cluster['count']} fresh wallets CONTRADICT our {our_direction}. "
            f"REDUCE POSITION BY 50%. This is the strongest insider signal."
        )


# ── Market Token Resolution ──────────────────────────────────────────

def get_token_ids_for_position(position):
    """Extract CLOB token IDs for a position's market.

    Searches Gamma API markets to find the matching market and its token IDs.
    """
    market_q = position.get("market", "")
    # Search by fetching markets and matching question text
    markets = fetch_active_markets(limit=100)
    for m in markets:
        if m.get("question", "").lower() == market_q.lower():
            try:
                return json.loads(m.get("clobTokenIds", "[]"))
            except (json.JSONDecodeError, TypeError):
                pass
    return []


def get_token_ids_for_keyword(keyword, limit=20):
    """Find markets matching a keyword and return their token IDs + metadata."""
    results = []
    markets = fetch_active_markets(limit=200)
    kw = keyword.lower()
    for m in markets:
        q = m.get("question", "").lower()
        if kw in q:
            try:
                token_ids = json.loads(m.get("clobTokenIds", "[]"))
            except (json.JSONDecodeError, TypeError):
                token_ids = []
            results.append({
                "question": m.get("question", ""),
                "token_ids": token_ids,
                "volume": m.get("volumeNum", 0),
                "liquidity": m.get("liquidityNum", 0),
            })
            if len(results) >= limit:
                break
    return results


# ── Trade Parsing ─────────────────────────────────────────────────────

def parse_trade(raw_trade, market_question="", market_volume=0):
    """Parse a raw CLOB trade into normalized format."""
    # CLOB trade format varies; handle common fields
    size = 0
    price = 0
    direction = "UNKNOWN"

    if isinstance(raw_trade, dict):
        # Size in USDC
        size = float(raw_trade.get("size", 0) or 0)
        price = float(raw_trade.get("price", 0) or 0)

        # Direction from side field
        side = raw_trade.get("side", "").upper()
        if side == "BUY":
            direction = "YES"
        elif side == "SELL":
            direction = "NO"

        # Alternative: outcome field
        outcome = raw_trade.get("outcome", "")
        if outcome and direction == "UNKNOWN":
            direction = outcome.upper()

    return {
        "wallet": raw_trade.get("maker_address") or raw_trade.get("taker_address") or raw_trade.get("owner", ""),
        "direction": direction,
        "trade_size_usd": size * price if size and price else size,
        "entry_price": price,
        "timestamp": raw_trade.get("created_at") or raw_trade.get("timestamp", ""),
        "market_question": market_question,
        "market_volume": market_volume,
    }


# ── Display ───────────────────────────────────────────────────────────

def print_anomaly(anomaly, portfolio_action=None):
    """Print formatted alert for a fresh wallet anomaly."""
    score = anomaly.get("anomaly_score", 0)

    # Severity icon
    if score >= 7:
        icon = "!! "
        label = "ALERT"
    elif score >= 4:
        icon = "?  "
        label = "FLAG"
    else:
        icon = "   "
        label = "LOG"

    width = 78
    print()
    print("=" * width)
    print(f" B9-02 FRESH WALLET {label} — Score {score}/10")
    print("=" * width)
    print()
    print(f"  WALLET:     {anomaly.get('wallet', '?')}")
    print(f"  MARKET:     {anomaly.get('market_question', '?')[:60]}")
    print(f"  DOMAIN:     {classify_domain(anomaly.get('market_question', ''))}")
    print(f"  DIRECTION:  {anomaly.get('direction', 'UNKNOWN')}")
    print(f"  SIZE:       ${anomaly.get('trade_size_usd', 0):,.0f}")
    print(f"  PRICE:      {anomaly.get('entry_price', '?')}")

    wi = anomaly.get("wallet_info", {})
    print()
    print(f"  TXN COUNT:  {wi.get('total_txns', '?')}")
    print(f"  WALLET AGE: {wi.get('age_days', '?')} days")
    print(f"  FUNDED BY:  {wi.get('funding_source') or 'Unknown'}")

    cat_days = anomaly.get("catalyst_days")
    if cat_days is not None:
        print(f"  CATALYST:   {cat_days}d away")

    if portfolio_action:
        action, detail = portfolio_action
        print()
        print(f"  {icon}PORTFOLIO: {action}")
        print(f"  DETAIL:     {detail}")

    print()
    print("-" * width)


def print_cluster_alert(cluster, portfolio_action=None):
    """Print alert for a detected cluster."""
    width = 78
    print()
    print("!" * width)
    print(f" B9-02 CLUSTER ALERT — {cluster['count']} fresh wallets")
    print("!" * width)
    print()
    print(f"  MARKET:     {cluster['market'][:60]}")
    print(f"  DIRECTION:  {cluster['direction']}")
    print(f"  WALLETS:    {cluster['count']}")
    print(f"  TOTAL USD:  ${cluster['total_usd']:,.0f}")
    print(f"  AVG SCORE:  {cluster['avg_score']:.1f}/10")
    print()
    for w in cluster["wallets"]:
        print(f"    - {w}")

    if portfolio_action:
        action, detail = portfolio_action
        print()
        print(f"  IMPACT: {action}")
        print(f"  {detail}")

    print()
    print("!" * width)


def print_summary(anomalies, clusters):
    """Print summary of scan results."""
    width = 78
    print()
    print("=" * width)
    print(f" B9-02 FRESH WALLET DETECTOR — SUMMARY")
    print(f" Scan time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print("=" * width)

    alerts = [a for a in anomalies if a.get("anomaly_score", 0) >= 7]
    flags = [a for a in anomalies if 4 <= a.get("anomaly_score", 0) < 7]
    logs = [a for a in anomalies if a.get("anomaly_score", 0) < 4]

    print()
    print(f"  ALERTS (7+):     {len(alerts)}")
    print(f"  FLAGS  (4-6):    {len(flags)}")
    print(f"  LOGGED (0-3):    {len(logs)}")
    print(f"  CLUSTERS:        {len(clusters)}")

    if alerts:
        print()
        print("  ALERTS:")
        for a in alerts:
            domain = classify_domain(a.get("market_question", ""))
            print(f"    [{a['anomaly_score']}] {a['wallet'][:14]}... "
                  f"${a.get('trade_size_usd', 0):,.0f} {a.get('direction', '?')} "
                  f"[{domain}] {a.get('market_question', '')[:35]}")

    if flags:
        print()
        print("  FLAGS:")
        for a in flags:
            domain = classify_domain(a.get("market_question", ""))
            print(f"    [{a['anomaly_score']}] {a['wallet'][:14]}... "
                  f"${a.get('trade_size_usd', 0):,.0f} {a.get('direction', '?')} "
                  f"[{domain}] {a.get('market_question', '')[:35]}")

    if clusters:
        print()
        print("  CLUSTERS (CRITICAL):")
        for c in clusters:
            print(f"    {c['count']} wallets → {c['direction']} on {c['market'][:40]} "
                  f"(${c['total_usd']:,.0f})")

    print()
    print("=" * width)
    print()


# ── JSONL Logging ─────────────────────────────────────────────────────

def append_anomaly_jsonl(anomaly):
    """Append anomaly to fresh-wallet-anomalies.jsonl."""
    with open(ANOMALY_LOG_PATH, 'a') as f:
        f.write(json.dumps(anomaly) + '\n')


# ── Dry Run Mock Data ─────────────────────────────────────────────────

def mock_trades_for_market(market_question):
    """Generate mock trades for dry-run testing."""
    return [
        {
            "wallet": "0xABCD1234567890abcdef1234567890abcdef1234",
            "direction": "YES",
            "trade_size_usd": 25000,
            "entry_price": 0.65,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_question": market_question,
            "market_volume": 150000,
        },
        {
            "wallet": "0x9876FEDCBA0987654321fedcba0987654321FEDC",
            "direction": "NO",
            "trade_size_usd": 8000,
            "entry_price": 0.35,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_question": market_question,
            "market_volume": 150000,
        },
    ]


def mock_wallet_info(wallet):
    """Generate mock wallet info for dry-run testing."""
    # First mock wallet is fresh, second is established
    if wallet.startswith("0xABCD"):
        return {
            "total_txns": 3,
            "first_txn_time": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
            "age_days": 5,
            "funding_source": "Coinbase",
            "funded_from_exchange": True,
            "first_deposit_hours_ago": 36,
        }
    return {
        "total_txns": 150,
        "first_txn_time": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
        "age_days": 400,
        "funding_source": None,
        "funded_from_exchange": False,
        "first_deposit_hours_ago": None,
    }


# ── Main Scan ─────────────────────────────────────────────────────────

def scan_market(token_ids, market_question, market_volume, threshold,
                max_history, catalysts, dry_run=False, api_key=None):
    """Scan a single market for fresh wallet anomalies."""
    anomalies = []

    if dry_run:
        trades = mock_trades_for_market(market_question)
    else:
        trades = []
        for tid in token_ids:
            raw = fetch_clob_trades(tid, limit=100)
            if isinstance(raw, list):
                for rt in raw:
                    trades.append(parse_trade(rt, market_question, market_volume))
            elif isinstance(raw, dict) and "data" in raw:
                for rt in raw["data"]:
                    trades.append(parse_trade(rt, market_question, market_volume))

    for trade in trades:
        size = trade.get("trade_size_usd", 0)
        if size < threshold:
            continue

        wallet = trade.get("wallet", "")
        if not wallet:
            continue

        # Check wallet history
        if dry_run:
            wallet_info = mock_wallet_info(wallet)
        else:
            wallet_info = fetch_wallet_history_polygonscan(wallet, api_key)

        total_txns = wallet_info.get("total_txns", 999)
        if total_txns > max_history:
            continue  # Established wallet — skip

        # Score the anomaly
        score = score_fresh_wallet_anomaly(
            wallet_info, size, market_volume, market_question, catalysts
        )

        cat_days = nearest_catalyst(market_question, catalysts)

        anomaly = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "wallet": wallet,
            "market_question": market_question,
            "direction": trade.get("direction", "UNKNOWN"),
            "trade_size_usd": size,
            "entry_price": trade.get("entry_price"),
            "market_volume": market_volume,
            "wallet_info": wallet_info,
            "anomaly_score": score,
            "catalyst_days": cat_days,
        }
        anomalies.append(anomaly)

    return anomalies


def run_scan(args):
    """Run the full B9-02 fresh wallet detector scan."""
    positions = load_positions()
    catalysts = load_catalyst_calendar()
    api_key = os.environ.get("POLYGONSCAN_API_KEY")

    print(f"Loaded {len(positions)} open positions")
    print(f"Loaded {len(catalysts)} catalyst events")
    if api_key:
        print("Polygonscan API key: configured")
    else:
        print("Polygonscan API key: not set (rate-limited)")
    print()

    all_anomalies = []

    # Build market list to scan
    markets_to_scan = []

    if args.market:
        # Search for specific market by keyword
        print(f"Searching for markets matching: {args.market}")
        if args.dry_run:
            markets_to_scan.append({
                "question": f"Mock market: {args.market}",
                "token_ids": ["mock_token"],
                "volume": 150000,
            })
        else:
            matches = get_token_ids_for_keyword(args.market)
            for m in matches:
                markets_to_scan.append({
                    "question": m["question"],
                    "token_ids": m["token_ids"],
                    "volume": m.get("volume", 0),
                })
            if not matches:
                print(f"  No active markets found for '{args.market}'")

    elif args.all_markets:
        # Scan top markets by volume
        print("Scanning top markets by volume...")
        if args.dry_run:
            markets_to_scan = [
                {"question": "Will US strike Iran by June 30, 2026?",
                 "token_ids": ["mock_1"], "volume": 500000},
                {"question": "Will Bitcoin reach $150,000 by December 31, 2026?",
                 "token_ids": ["mock_2"], "volume": 2000000},
            ]
        else:
            raw = fetch_active_markets(limit=50)
            for m in raw:
                try:
                    tids = json.loads(m.get("clobTokenIds", "[]"))
                except (json.JSONDecodeError, TypeError):
                    tids = []
                markets_to_scan.append({
                    "question": m.get("question", ""),
                    "token_ids": tids,
                    "volume": m.get("volumeNum", 0),
                })

    else:
        # Default: scan portfolio markets
        print("Scanning portfolio markets...")
        for pos in positions:
            if args.dry_run:
                markets_to_scan.append({
                    "question": pos.get("market", ""),
                    "token_ids": ["mock_token"],
                    "volume": 150000,
                })
            else:
                tids = get_token_ids_for_position(pos)
                markets_to_scan.append({
                    "question": pos.get("market", ""),
                    "token_ids": tids,
                    "volume": None,  # Will use market data if available
                })

    print(f"Markets to scan: {len(markets_to_scan)}")
    print()

    for i, mkt in enumerate(markets_to_scan, 1):
        q = mkt["question"]
        print(f"[{i}/{len(markets_to_scan)}] {q[:60]}...")

        anomalies = scan_market(
            token_ids=mkt["token_ids"],
            market_question=q,
            market_volume=mkt.get("volume", 0),
            threshold=args.threshold,
            max_history=args.max_history,
            catalysts=catalysts,
            dry_run=args.dry_run,
            api_key=api_key,
        )

        if anomalies:
            print(f"         Found {len(anomalies)} anomalies")
        all_anomalies.extend(anomalies)

    # Cluster detection
    clusters = detect_clusters(all_anomalies)

    # Portfolio impact assessment
    portfolio_actions = {}
    for a in all_anomalies:
        pos = get_position_for_market(positions, a.get("market_question", ""))
        if pos or a.get("anomaly_score", 0) >= 4:
            portfolio_actions[a["wallet"]] = assess_portfolio_impact(a, pos)

    cluster_actions = {}
    for c in clusters:
        pos = get_position_for_market(positions, c["market"])
        cluster_actions[c["market"]] = assess_cluster_impact(c, pos)

    return all_anomalies, clusters, portfolio_actions, cluster_actions


# ── Entry Point ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="B9-02 Fresh Wallet Detector — market-centric insider pattern monitor"
    )
    parser.add_argument("--market", help="Search for specific market by keyword")
    parser.add_argument("--all-markets", action="store_true",
                        help="Scan top 50 markets by volume")
    parser.add_argument("--continuous", action="store_true",
                        help="Poll every 30 minutes")
    parser.add_argument("--threshold", type=float, default=5000,
                        help="Minimum trade size in USD (default: 5000)")
    parser.add_argument("--max-history", type=int, default=10,
                        help="Max prior transactions for 'fresh' wallet (default: 10)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON to stdout")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use mock data, skip API calls")
    parser.add_argument("--no-log", action="store_true",
                        help="Don't append to anomalies JSONL")
    parser.add_argument("--no-profile", action="store_true",
                        help="Don't create preliminary profiles for 7+ scores")
    args = parser.parse_args()

    while True:
        anomalies, clusters, portfolio_actions, cluster_actions = run_scan(args)

        if args.json:
            output = {
                "scan_time": datetime.now(timezone.utc).isoformat(),
                "anomalies": anomalies,
                "clusters": clusters,
                "portfolio_actions": {k: {"action": v[0], "detail": v[1]}
                                      for k, v in portfolio_actions.items()},
                "cluster_actions": {k: {"action": v[0], "detail": v[1]}
                                    for k, v in cluster_actions.items()},
            }
            print(json.dumps(output, indent=2))
        else:
            # Print individual anomalies (4+ only)
            for a in anomalies:
                if a.get("anomaly_score", 0) >= 4:
                    pa = portfolio_actions.get(a["wallet"])
                    print_anomaly(a, pa)

            # Print cluster alerts
            for c in clusters:
                ca = cluster_actions.get(c["market"])
                print_cluster_alert(c, ca)

            print_summary(anomalies, clusters)

        # Log anomalies
        if not args.no_log:
            for a in anomalies:
                if a.get("anomaly_score", 0) >= 4:
                    append_anomaly_jsonl(a)

        # Save profiles for high-score anomalies
        if not args.no_profile:
            for a in anomalies:
                if a.get("anomaly_score", 0) >= 7:
                    profile = create_preliminary_profile(
                        a["wallet"], a.get("wallet_info", {}), a, a["anomaly_score"]
                    )
                    path = save_profile(profile)
                    print(f"  Profile saved: {path}")

        # Exit codes
        if not args.continuous:
            has_cluster_contradict = any(
                v[0] == "CLUSTER_CONTRADICT" for v in cluster_actions.values()
            )
            has_alert = any(a.get("anomaly_score", 0) >= 7 for a in anomalies)

            if has_cluster_contradict:
                sys.exit(3)
            elif has_alert:
                sys.exit(2)
            elif any(a.get("anomaly_score", 0) >= 4 for a in anomalies):
                sys.exit(1)
            sys.exit(0)

        # Continuous mode: wait and repeat
        print(f"Next scan in 30 minutes...")
        time.sleep(1800)


if __name__ == "__main__":
    main()
