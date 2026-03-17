#!/usr/bin/env python3
"""Field Classifier — L03

Decomposes insider category-level edge into sub-domain specifics.
Generates institutional hypotheses and intelligence dossiers.

Takes L01 (edge-profiles.json) and L02 (insider-registry.json) outputs,
cross-references with raw trade data in edge-cache/, and produces:
  1. classified-insiders.json — full sub-domain breakdown + hypotheses
  2. data/intelligence-dossiers/*.md — per-insider dossiers (score >= 7)
  3. Terminal report — top insiders with primary sub-domain + hypothesis

Usage:
    python3 scripts/field-classifier.py
    python3 scripts/field-classifier.py --min-score 6  # lower threshold
    python3 scripts/field-classifier.py --json          # JSON to stdout
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(DATA_DIR, "edge-cache")
REGISTRY_FILE = os.path.join(DATA_DIR, "insider-registry.json")
EDGE_PROFILES_FILE = os.path.join(DATA_DIR, "edge-profiles.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "classified-insiders.json")
DOSSIER_DIR = os.path.join(DATA_DIR, "intelligence-dossiers")

HIGH_CONFIDENCE_THRESHOLD = 7.0

# ── Sub-Domain Classification ─────────────────────────────────────────────────

SUB_DOMAIN_KEYWORDS = {
    "POL": {
        "us-presidential": [
            "president 2028", "presidential election", "president of the us",
            "next president", "win the 2028", "presidential nominee",
            "win the presidency", "electoral college",
        ],
        "us-republican-primary": [
            "republican nomin", "gop nomin", "rnc", "republican primary",
            "gop primary", "republican candidate", "maga",
            "desantis", "haley", "vivek", "burgum",
        ],
        "us-democratic-primary": [
            "democratic nomin", "dnc", "democratic primary",
            "democratic candidate", "newsom", "whitmer",
        ],
        "us-congressional": [
            "congress", "senate", "house of rep", "speaker",
            "midterm", "congressional", "senate confirm",
            "filibuster", "house vote",
        ],
        "us-executive-action": [
            "executive order", "pardon", "sotu", "state of the union",
            "cabinet", "white house", "oval office", "press secretary",
            "approval rating", "impeach",
        ],
        "trump-admin": [
            "trump", "vance", "trump say", "trump tweet",
            "trump sign", "trump fire", "trump announce",
            "trump meet", "trump talk",
        ],
        "uk-politics": [
            "starmer", "labour", "conservative", "uk parliament",
            "nhs", "brexit", "sunak", "british pm",
        ],
        "eu-politics": [
            "macron", "scholz", "german election", "eu parliament",
            "european commission", "lagarde", "ecb president",
            "meloni", "european council",
        ],
        "latam-politics": [
            "maduro", "venezuela election", "brazil election", "lula",
            "mexico election", "milei", "argentina",
        ],
    },
    "GEO": {
        "middle-east-conflict": [
            "iran", "israel strike", "idf ", "gaza", "hamas", "hezbollah",
            "us military action against iran", "israel military action",
            "yemen", "houthi", "syria", "lebano",
        ],
        "russia-ukraine": [
            "ukraine", "russia", "crimea", "donbas", "donets", "zaporizhzhia",
            "kherson", "zelensky", "russian troop", "russian invasion",
            "minsk", "kyiv",
        ],
        "china-taiwan": [
            "taiwan", "china strait", "south china sea",
            "china invad", "china military", "pla ",
            "xi jinping", "china sanction",
        ],
        "nato-alliances": [
            "nato", "alliance", "article 5", "defense pact",
            "military alliance",
        ],
        "nuclear-risk": [
            "nuclear weapon", "nuclear test", "proliferation",
            "nuclear strike", "atomic", "icbm",
            "nuclear war",
        ],
        "sanctions-diplomacy": [
            "sanction", "ceasefire", "peace deal", "peace talk",
            "diplomatic", "negotiation", "treaty", "accord",
            "truce", "armistice",
        ],
    },
    "ECO": {
        "us-fed-rates": [
            "fed ", "federal reserve", "rate cut", "rate hike",
            "fomc", "powell", "basis point", "fed fund",
            "interest rate", "fed rate",
        ],
        "us-inflation": [
            "inflation", "cpi ", "pce ", "price index",
            "consumer price", "core inflation",
        ],
        "us-recession": [
            "recession", "gdp ", "unemployment", "jobs report",
            "nonfarm", "economic growth", "economic contraction",
        ],
        "central-banks-global": [
            "ecb ", "boe ", "boj ", "rba ", "bank of england",
            "bank of japan", "lagarde", "european central",
        ],
        "trade-tariffs": [
            "tariff", "trade war", "trade deal", "trade deficit",
            "import duty", "export ban",
        ],
        "us-fiscal": [
            "debt ceiling", "government shutdown", "treasury",
            "deficit", "spending bill", "budget",
        ],
    },
    "CRY": {
        "btc-price": [
            "bitcoin", "btc ", "btc price", "bitcoin price",
            "bitcoin above", "bitcoin below", "bitcoin reach",
        ],
        "eth-price": [
            "ethereum", "eth ", "eth price", "ether price",
            "ethereum above", "ethereum below",
        ],
        "altcoins": [
            "solana", "sol ", "doge", "memecoin", "altcoin",
            "cardano", "xrp", "polkadot", "avalanche",
        ],
        "crypto-regulation": [
            "sec crypto", "cftc crypto", "crypto ban",
            "crypto regulation", "stablecoin regulation",
            "crypto legislation",
        ],
        "defi-protocol": [
            "defi", "uniswap", "aave", "compound", "maker",
            "liquidity pool", "yield farm",
        ],
        "crypto-etf": [
            "bitcoin etf", "ethereum etf", "spot etf",
            "crypto etf", "etf approval",
        ],
    },
    "TEC": {
        "ai-models": [
            "gpt", "chatgpt", "claude", "gemini", "llama",
            "ai model", "llm ", "language model", "agi",
            "grok", "copilot", "ai benchmark",
            "reasoning model", "o1 ", "o3 ",
        ],
        "ai-companies": [
            "openai", "anthropic", "deepmind", "google ai",
            "meta ai", "xai ", "mistral",
            "ai company", "ai startup", "ai valuation",
        ],
        "big-tech-products": [
            "iphone", "pixel", "search engine",
            "app store", "play store", "vision pro",
            "windows", "android", "year in search",
        ],
        "semiconductors": [
            "nvidia", "tsmc", "semiconductor", "chip ",
            "gpu ", "h100", "a100", "intel ",
            "qualcomm", "chip shortage",
        ],
        "space": [
            "spacex", "starship", "launch", "mars ",
            "moon landing", "blue origin", "nasa ",
            "rocket", "satellite",
        ],
        "tech-regulation": [
            "antitrust", "tiktok ban", "data privacy",
            "tech regulation", "monopoly", "break up",
        ],
    },
    "FIN": {
        "equity-indices": [
            "s&p 500", "s&p", "dow jones", "nasdaq",
            "stock market", "ftse", "nikkei",
        ],
        "individual-stocks": [
            "tesla stock", "apple stock", "earnings",
            "ipo ", "market cap", "share price",
        ],
        "commodities": [
            "gold price", "oil price", "silver price",
            "commodity", "crude oil", "natural gas",
        ],
        "fx-rates": [
            "dollar", "eur/usd", "exchange rate",
            "forex", "currency",
        ],
    },
    "LAW": {
        "us-scotus": [
            "supreme court", "scotus", "justice ",
            "constitutional", "amendment",
        ],
        "us-criminal": [
            "indict", "guilty", "conviction", "sentenced",
            "arrest", "trial", "charged with",
            "plea deal", "prison",
        ],
        "corporate-litigation": [
            "lawsuit", "class action", "settlement",
            "antitrust suit", "patent dispute",
        ],
        "regulatory-enforcement": [
            "sec ", "cftc", "doj ", "fbi ", "ftc ",
            "regulation", "enforce", "fine ",
            "consent decree",
        ],
    },
    "ENV": {
        "climate-policy": [
            "paris agreement", "climate", "carbon",
            "emission", "epa ", "green new deal",
        ],
        "renewable-energy": [
            "solar energy", "wind energy", "renewable",
            "ev ", "electric vehicle", "clean energy",
        ],
        "weather-disasters": [
            "hurricane", "wildfire", "earthquake",
            "flood", "tornado", "drought",
            "temperature record",
        ],
    },
    "SOC": {
        "entertainment": [
            "oscar", "grammy", "emmy", "box office",
            "movie", "album", "music", "netflix",
            "spotify", "streaming", "tv show",
        ],
        "sports-general": [
            "nba", "nfl", "mlb", "nhl", "ufc",
            "super bowl", "world series", "champion",
            "playoffs", "finals",
        ],
        "viral-pop-culture": [
            "tiktok", "viral", "trending", "celebrity",
            "influencer", "social media",
        ],
    },
}

# ── Institutional Hypotheses ──────────────────────────────────────────────────

INSTITUTIONAL_HYPOTHESES = {
    "us-presidential": [
        "Senior campaign strategist with internal polling",
        "Major party donor with access to internal data",
        "Political consultant connected to both parties",
    ],
    "us-republican-primary": [
        "RNC operative or campaign staffer",
        "Republican-aligned pollster with private polling",
        "Major donor with access to internal polls",
        "PAC analyst with early internal data",
    ],
    "us-democratic-primary": [
        "DNC operative or campaign staffer",
        "Democratic pollster with private polling",
    ],
    "us-congressional": [
        "Congressional staffer with committee access",
        "Lobbyist with vote-count intelligence",
    ],
    "us-executive-action": [
        "White House staffer or press corps insider",
        "Political journalist with off-record sources",
    ],
    "trump-admin": [
        "Trump administration staffer or close advisor",
        "Mar-a-Lago circle member",
        "Political journalist with WH sources",
        "Republican operative plugged into Trump world",
    ],
    "middle-east-conflict": [
        "IDF reservist or active military (cf. Feb 2026 charges)",
        "Israeli government official or intelligence-adjacent",
        "Defense contractor with government contracts in the region",
        "Journalist with embedded military sources",
        "Diplomat or foreign service officer",
    ],
    "russia-ukraine": [
        "Eastern European analyst with government contacts",
        "NATO-adjacent defense analyst",
        "Ukrainian or Russian expat with local intelligence",
        "OSINT specialist with satellite imagery access",
    ],
    "china-taiwan": [
        "Taiwanese government official or military analyst",
        "US State Dept / DoD analyst with Pacific focus",
        "Semiconductor industry insider (TSMC-adjacent)",
    ],
    "sanctions-diplomacy": [
        "Diplomat or trade negotiator",
        "Sanctions compliance professional at financial institution",
        "Foreign affairs journalist with diplomatic sources",
    ],
    "us-fed-rates": [
        "Federal Reserve employee (ILLEGAL: 18 USC 1905)",
        "Primary dealer bank analyst with advance Fed communication",
        "Former Fed official with maintained relationships",
        "Treasury Department employee",
    ],
    "us-inflation": [
        "BLS employee with pre-release access (ILLEGAL)",
        "Economics professor with proprietary nowcasting models",
        "Quantitative hedge fund with alternative data",
    ],
    "trade-tariffs": [
        "USTR employee or trade negotiator",
        "Corporate lobbyist with advance notice of tariff announcements",
        "Commerce Department staffer",
    ],
    "ai-models": [
        "Employee or contractor at OpenAI, Anthropic, Google DeepMind",
        "Investor with NDA access to pre-release benchmarks",
        "Board member or advisor to AI lab",
        "Technical journalist with advance review access",
    ],
    "ai-companies": [
        "Venture capitalist with portfolio company access",
        "Investment banker working on AI deals",
        "Journalist covering AI industry with insider sources",
    ],
    "semiconductors": [
        "NVIDIA/TSMC/Intel employee with product roadmap access",
        "Supply chain analyst at major electronics manufacturer",
        "Industry analyst at semiconductor research firm",
    ],
    "space": [
        "SpaceX employee or contractor",
        "NASA employee with mission schedule access",
        "Aerospace journalist with industry sources",
    ],
    "crypto-regulation": [
        "SEC or CFTC employee (ILLEGAL: 18 USC 1905)",
        "Crypto exchange lobbyist with congressional contacts",
        "Law firm working on regulatory cases",
        "Congressional staffer on financial services committee",
    ],
    "btc-price": [
        "Whale / large holder with market-moving capability",
        "Exchange operator with order flow visibility",
        "OTC desk operator with block trade intelligence",
    ],
    "us-scotus": [
        "SCOTUS clerk (ILLEGAL: potential obstruction)",
        "Supreme Court journalist with reliable sources",
        "Constitutional law professor tracking oral arguments",
    ],
    "us-criminal": [
        "Prosecutor or defense attorney with case access",
        "Court clerk with scheduling/filing intelligence",
        "Legal journalist with courtroom sources",
    ],
    "regulatory-enforcement": [
        "SEC/DOJ employee (ILLEGAL: 18 USC 1905)",
        "Defense attorney with settlement negotiation access",
        "Compliance professional at targeted firm",
    ],
}

HIGH_LEGAL_RISK_SUBDOMAINS = [
    "us-fed-rates",
    "us-inflation",
    "crypto-regulation",
    "us-scotus",
    "regulatory-enforcement",
]

# ── Confidence Classification ─────────────────────────────────────────────────

CONFIDENCE_LEVELS = {
    "SPECULATIVE": "Edge pattern exists; any of several explanations could fit",
    "PLAUSIBLE": "Edge pattern + trade timing + market type all point to this explanation",
    "PROBABLE": "Strong localisation + matches known documented cases",
    "IDENTIFIED": "Already publicly known",
}

# ── Helper Functions ──────────────────────────────────────────────────────────


def classify_subdomain(title, category):
    """Classify a market title into its sub-domain within the given category."""
    if not title or category not in SUB_DOMAIN_KEYWORDS:
        return None
    t = title.lower()
    best_match = None
    best_count = 0
    for subdomain, keywords in SUB_DOMAIN_KEYWORDS[category].items():
        count = sum(1 for kw in keywords if kw in t)
        if count > best_count:
            best_count = count
            best_match = subdomain
    # Also check all categories if primary category didn't match
    if not best_match:
        for cat, subdomains in SUB_DOMAIN_KEYWORDS.items():
            for subdomain, keywords in subdomains.items():
                count = sum(1 for kw in keywords if kw in t)
                if count > best_count:
                    best_count = count
                    best_match = subdomain
    return best_match


def t_test_p(values):
    """One-sample t-test: H0 = mean is zero. Returns (mean, t_stat, p_value)."""
    n = len(values)
    if n < 2:
        return (values[0] if values else 0, 0, 1.0)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else 0.001
    se = std / math.sqrt(n)
    t_stat = mean / se if se > 0 else 0
    # Approximate p-value using normal distribution for large N
    z = abs(t_stat)
    if z > 8:
        p = 1e-15
    elif z > 6:
        p = 1e-09
    elif z > 4:
        p = 0.00003
    elif z > 3:
        p = 0.0013
    elif z > 2.576:
        p = 0.005
    elif z > 1.96:
        p = 0.025
    elif z > 1.645:
        p = 0.05
    else:
        # Rough approximation
        p = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
    return (mean, t_stat, p)


def load_trades(wallet):
    """Load cached trades for a wallet (by prefix match on filename)."""
    if not os.path.exists(CACHE_DIR):
        return []
    # Filenames are like trades-0x0afc7ce56285bd.json (0x + first 14 hex chars)
    w = wallet.lower()
    for fname in os.listdir(CACHE_DIR):
        if not fname.startswith("trades-") or not fname.endswith(".json"):
            continue
        # Extract the wallet prefix from the filename
        file_prefix = fname.replace("trades-", "").replace(".json", "").lower()
        # Match if the wallet starts with this prefix (or vice versa)
        if w.startswith(file_prefix) or file_prefix.startswith(w[:len(file_prefix)]):
            fpath = os.path.join(CACHE_DIR, fname)
            try:
                with open(fpath) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
    return []


def load_resolved_markets():
    """Load resolved markets cache for outcome resolution."""
    cache_file = os.path.join(CACHE_DIR, "resolved-markets.json")
    if not os.path.exists(cache_file):
        return {}
    try:
        with open(cache_file) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def compute_trade_edge(trade, resolved):
    """Compute edge for a single trade given resolution data."""
    cid = trade.get("condition_id", "").lower()
    title = trade.get("title", "")
    price = trade.get("price", 0)
    side = trade.get("side", "BUY")

    # Look up resolution
    res = resolved.get(cid)
    if not res:
        # Try token-based lookup
        asset = trade.get("asset", "")
        res = resolved.get(f"token:{asset}")
    if not res:
        return None

    outcome_prices = res.get("outcome_prices", [])
    if not outcome_prices:
        return None

    # Parse outcome prices
    if isinstance(outcome_prices, str):
        try:
            outcome_prices = json.loads(outcome_prices)
        except json.JSONDecodeError:
            return None

    outcome_idx = trade.get("outcome_index", 0)
    try:
        resolved_price = float(outcome_prices[outcome_idx])
    except (IndexError, ValueError):
        return None

    # Edge = outcome - entry_price for BUY, entry_price - outcome for SELL
    if side == "BUY":
        edge = resolved_price - price
    else:
        edge = price - resolved_price

    return {
        "edge": edge,
        "title": title,
        "price": price,
        "side": side,
        "resolved_price": resolved_price,
        "timestamp": trade.get("timestamp", 0),
        "size": trade.get("size", 0),
        "condition_id": cid,
    }


def determine_hypothesis_confidence(account, subdomain_data):
    """Determine confidence level for institutional hypothesis."""
    primary = subdomain_data.get("primary_subdomain")
    if not primary:
        return "SPECULATIVE"

    # Check known identities
    alias = account.get("alias", "").lower()
    if "alpharaccoon" in alias:
        return "IDENTIFIED"

    # Find the primary subdomain's stats (first positive-edge entry)
    breakdown = subdomain_data.get("subdomain_breakdown", [])
    primary_entry = None
    for sd in breakdown:
        if sd.get("mean_edge", 0) > 0 and sd.get("n", 0) >= 2:
            primary_entry = sd
            break
    if not primary_entry and breakdown:
        primary_entry = breakdown[0]
    if not primary_entry:
        return "SPECULATIVE"

    pct = primary_entry.get("as_pct_of_category_edge", 0)
    p = primary_entry.get("p_value", 1)
    n = primary_entry.get("n", 0)

    # Very high concentration
    if pct > 0.8 and n >= 10:
        if p < 0.001:
            return "PROBABLE"
        elif p < 0.05:
            return "PLAUSIBLE"

    # High concentration
    if pct > 0.5 and n >= 5:
        if p < 0.001:
            return "PROBABLE"
        elif p < 0.01:
            return "PLAUSIBLE"

    # Medium concentration with many trades
    if n >= 20 and p < 0.05:
        return "PLAUSIBLE"

    return "SPECULATIVE"


# ── Main Analysis ─────────────────────────────────────────────────────────────


def analyze_wallet(wallet, alias, dominant_category, registry_entry, resolved):
    """Full sub-domain analysis for a single wallet."""
    trades = load_trades(wallet)

    if not trades:
        # No trade data — return category-level only
        return {
            "wallet": wallet,
            "alias": alias,
            "dominant_category": dominant_category,
            "has_trade_data": False,
            "subdomain_breakdown": [],
            "primary_subdomain": None,
            "institutional_hypothesis": None,
            "hypothesis_confidence": "SPECULATIVE",
            "legal_risk": False,
            "trade_pattern": None,
        }

    # Classify each trade into sub-domain and compute edge
    subdomain_edges = defaultdict(list)
    subdomain_trades = defaultdict(list)
    all_edges = []
    timestamps = []
    sizes = []
    directions = {"BUY": 0, "SELL": 0}
    entry_prices = []

    for trade in trades:
        title = trade.get("title", "")
        # Classify into sub-domain
        subdomain = classify_subdomain(title, dominant_category)

        edge_info = compute_trade_edge(trade, resolved)
        if edge_info is None:
            # Unresolved — still record sub-domain for pattern
            if subdomain:
                subdomain_trades[subdomain].append({
                    "title": title,
                    "price": trade.get("price", 0),
                    "side": trade.get("side", "BUY"),
                    "timestamp": trade.get("timestamp", 0),
                    "size": trade.get("size", 0),
                    "resolved": False,
                })
            continue

        if subdomain:
            subdomain_edges[subdomain].append(edge_info["edge"])
            subdomain_trades[subdomain].append({
                "title": title,
                "price": edge_info["price"],
                "side": edge_info["side"],
                "timestamp": edge_info["timestamp"],
                "size": edge_info["size"],
                "edge": edge_info["edge"],
                "resolved": True,
            })

        all_edges.append(edge_info["edge"])
        timestamps.append(edge_info["timestamp"])
        sizes.append(edge_info["size"] * edge_info["price"])  # wagered USD
        directions[edge_info["side"]] += 1
        entry_prices.append(edge_info["price"])

    # Build sub-domain breakdown
    total_category_edge = sum(abs(e) for e in all_edges) if all_edges else 1
    breakdown = []

    for sd, edges in sorted(subdomain_edges.items(),
                            key=lambda x: -abs(sum(x[1]) / len(x[1]) if x[1] else 0)):
        if len(edges) < 2:
            continue
        mean_edge, t_stat, p_value = t_test_p(edges)
        total_sd_edge = sum(abs(e) for e in edges)
        breakdown.append({
            "subdomain": sd,
            "n": len(edges),
            "mean_edge": round(mean_edge, 4),
            "p_value": round(p_value, 6),
            "as_pct_of_category_edge": round(
                total_sd_edge / total_category_edge, 2) if total_category_edge > 0 else 0,
            "total_n_trades": len(subdomain_trades.get(sd, [])),
        })

    # Sort by positive edge first (best performing sub-domains), then by magnitude
    breakdown.sort(key=lambda x: (-x["mean_edge"], -x["n"]))

    # Primary = sub-domain with dominant share of category edge, or highest positive edge
    primary = None
    # First: check if any sub-domain dominates by volume (>50% of edge, 20+ trades)
    for sd in breakdown:
        if (sd.get("as_pct_of_category_edge", 0) > 0.50
                and sd.get("n", 0) >= 20
                and sd.get("mean_edge", 0) > 0):
            primary = sd["subdomain"]
            break
    # Fallback: highest positive edge with meaningful sample
    if not primary:
        for sd in breakdown:
            if sd["mean_edge"] > 0 and sd["n"] >= 2:
                primary = sd["subdomain"]
                break
    if not primary and breakdown:
        primary = breakdown[0]["subdomain"]

    # Trade pattern analysis
    total_dir = directions["BUY"] + directions["SELL"]
    pattern = None
    if all_edges:
        avg_size = sum(sizes) / len(sizes) if sizes else 0
        avg_entry = sum(entry_prices) / len(entry_prices) if entry_prices else 0
        # Timing: compute typical days before resolution (approximate)
        pattern = {
            "avg_trade_size_usd": round(avg_size, 0),
            "typical_entry_price": round(avg_entry, 3),
            "direction_pct_buy": round(directions["BUY"] / total_dir, 2) if total_dir > 0 else 0,
            "total_resolved_trades": len(all_edges),
            "total_all_trades": len(trades),
            "unique_markets": len(set(t.get("condition_id", "") for t in trades)),
        }

    # Hypothesis
    hypotheses = INSTITUTIONAL_HYPOTHESES.get(primary, [])
    top_hypothesis = hypotheses[0] if hypotheses else None

    # Confidence
    subdomain_data = {
        "primary_subdomain": primary,
        "subdomain_breakdown": breakdown,
    }
    confidence = determine_hypothesis_confidence(
        {"alias": alias}, subdomain_data)

    # Legal risk
    legal_risk = primary in HIGH_LEGAL_RISK_SUBDOMAINS

    return {
        "wallet": wallet,
        "alias": alias,
        "dominant_category": dominant_category,
        "has_trade_data": True,
        "subdomain_breakdown": breakdown,
        "primary_subdomain": primary,
        "institutional_hypothesis": top_hypothesis,
        "all_hypotheses": hypotheses,
        "hypothesis_confidence": confidence,
        "legal_risk": legal_risk,
        "legal_risk_note": (
            "If institutional hypothesis is correct, this person may be committing "
            "a federal crime. Prediction markets have no jurisdiction, but following "
            "their signal means profiting from their illegal activity. "
            "DOCUMENT but flag as ethically grey."
        ) if legal_risk else None,
        "trade_pattern": pattern,
    }


def cross_cluster_analysis(all_results, resolved):
    """Find insiders trading the same markets in the same direction in overlapping windows."""
    # Build market → [(wallet, side, timestamp)] index
    market_activity = defaultdict(list)

    for result in all_results:
        if not result.get("has_trade_data"):
            continue
        wallet = result["wallet"]
        alias = result["alias"]
        trades = load_trades(wallet)

        for trade in trades:
            cid = trade.get("condition_id", "").lower()
            if not cid:
                continue
            market_activity[cid].append({
                "wallet": wallet,
                "alias": alias,
                "side": trade.get("side", "BUY"),
                "timestamp": trade.get("timestamp", 0),
                "price": trade.get("price", 0),
                "title": trade.get("title", ""),
            })

    # Find clusters: 2+ insiders on same market, same direction, within 72h
    clusters = []
    WINDOW_SECS = 72 * 3600  # 72 hours

    for cid, activities in market_activity.items():
        # Group by unique wallets
        wallets = set(a["wallet"] for a in activities)
        if len(wallets) < 2:
            continue

        # Group by direction
        for direction in ["BUY", "SELL"]:
            dir_activities = [a for a in activities if a["side"] == direction]
            dir_wallets = set(a["wallet"] for a in dir_activities)
            if len(dir_wallets) < 2:
                continue

            # Check temporal proximity
            dir_activities.sort(key=lambda x: x["timestamp"])
            # Sliding window
            for i, act_i in enumerate(dir_activities):
                cluster_members = [act_i]
                for j in range(i + 1, len(dir_activities)):
                    if dir_activities[j]["timestamp"] - act_i["timestamp"] <= WINDOW_SECS:
                        if dir_activities[j]["wallet"] != act_i["wallet"]:
                            cluster_members.append(dir_activities[j])

                unique_wallets = set(m["wallet"] for m in cluster_members)
                if len(unique_wallets) >= 2:
                    # Deduplicate members: one entry per wallet (earliest trade)
                    seen_wallets = set()
                    deduped = []
                    for m in sorted(cluster_members, key=lambda x: x["timestamp"]):
                        if m["wallet"] not in seen_wallets:
                            seen_wallets.add(m["wallet"])
                            deduped.append(m)
                    clusters.append({
                        "market": act_i.get("title", cid[:16]),
                        "condition_id": cid,
                        "direction": direction,
                        "n_insiders": len(unique_wallets),
                        "members": [
                            {
                                "alias": m["alias"],
                                "price": round(m["price"], 3),
                                "timestamp": m["timestamp"],
                            }
                            for m in deduped
                        ],
                        "window_hours": round(
                            (max(m["timestamp"] for m in deduped) -
                             min(m["timestamp"] for m in deduped)) / 3600, 1
                        ),
                    })
                    break  # One cluster per cid+direction is enough

    # Deduplicate by condition_id + direction
    seen = set()
    unique_clusters = []
    for c in clusters:
        key = (c["condition_id"], c["direction"])
        if key not in seen:
            seen.add(key)
            unique_clusters.append(c)

    # Sort by number of insiders, then window tightness
    unique_clusters.sort(key=lambda x: (-x["n_insiders"], x["window_hours"]))
    return unique_clusters[:20]  # Top 20


def generate_dossier(result, registry_entry, edge_profile):
    """Generate markdown dossier for a high-confidence insider."""
    w = result["wallet"]
    alias = result["alias"]
    score = registry_entry.get("insider_score", 0)
    acct_type = registry_entry.get("account_type", "UNKNOWN")
    dom_cat = result["dominant_category"]
    primary_sd = result.get("primary_subdomain", "unknown")

    # Pull stats from registry
    top_edge = registry_entry.get("top_category_edge", 0)
    top_n = registry_entry.get("top_category_n", 0)
    top_p = registry_entry.get("top_category_p", 1)
    total_profit = registry_entry.get("total_profit_usd", 0)
    first_trade = registry_entry.get("first_trade") or "unknown"
    last_trade = registry_entry.get("last_trade") or "unknown"
    # Fill from edge profile if available
    if edge_profile and (first_trade == "unknown" or last_trade == "unknown"):
        last_active = edge_profile.get("last_active")
        if last_active and last_trade == "unknown":
            last_trade = last_active
    follow_conf = registry_entry.get("follow_confidence", 0)

    # Sub-domain breakdown text
    breakdown_text = ""
    for sd in result.get("subdomain_breakdown", [])[:5]:
        pct = int(sd["as_pct_of_category_edge"] * 100)
        edge_str = f"+{sd['mean_edge']:.2f}" if sd['mean_edge'] >= 0 else f"{sd['mean_edge']:.2f}"
        breakdown_text += (
            f"- **{sd['subdomain']}**: {sd['n']} resolved, "
            f"mean edge {edge_str}, p={sd['p_value']:.4f}, "
            f"{pct}% of category edge\n"
        )
    if not breakdown_text:
        breakdown_text = "- No sub-domain trade data available\n"

    # Trade pattern
    pattern_text = ""
    tp = result.get("trade_pattern")
    if tp:
        pattern_text = (
            f"- Avg trade size: ${tp['avg_trade_size_usd']:,.0f}\n"
            f"- Typical entry price: {tp['typical_entry_price']:.2f}\n"
            f"- Direction: {int(tp['direction_pct_buy'] * 100)}% BUY\n"
            f"- Resolved trades: {tp['total_resolved_trades']} / {tp['total_all_trades']} total\n"
            f"- Unique markets: {tp['unique_markets']}\n"
        )
    else:
        pattern_text = "- No detailed trade data available\n"

    # Hypothesis
    hyp = result.get("institutional_hypothesis", "No hypothesis generated")
    hyp_conf = result.get("hypothesis_confidence", "SPECULATIVE")
    all_hyps = result.get("all_hypotheses", [])
    hyp_list = "\n".join(f"  {i+1}. {h}" for i, h in enumerate(all_hyps)) if all_hyps else "  None"

    # Legal risk
    legal_note = ""
    if result.get("legal_risk"):
        legal_note = (
            "\n**LEGAL RISK FLAG**: "
            + result.get("legal_risk_note", "Potential illegal insider trading.")
            + "\n"
        )

    # Primary sub-domain label
    primary_label = primary_sd.replace("-", " ").title() if primary_sd else "Unknown"

    dossier = f"""### DOSSIER: {alias}

**Wallet**: `{w}`
**Type**: {acct_type} (score {score}/10)
**Active Period**: {first_trade or 'unknown'} - {last_trade or 'unknown'}

---

**Dominant Field**: {dom_cat} > {primary_label}

**Sub-Domain Breakdown**:
{breakdown_text}
**Trade Pattern**:
{pattern_text}
**Total Profit**: ${total_profit:,.0f}
**Top Category Edge**: +{top_edge:.2f} ({top_n} trades, p={top_p})

---

**Institutional Hypothesis**: {hyp_conf} — {hyp}

All hypotheses considered:
{hyp_list}

Evidence: Sub-domain specificity ({primary_sd}), trade pattern, bet sizing
{legal_note}
---

**Recommended Follow Confidence**: {follow_conf}/5
**Follow only when**: Market is in {dom_cat} > {primary_sd}. Ignore their bets elsewhere.
"""
    return dossier


def main():
    parser = argparse.ArgumentParser(description="L03 Field Classifier")
    parser.add_argument("--min-score", type=float, default=HIGH_CONFIDENCE_THRESHOLD,
                        help="Minimum insider score for dossier generation")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON to stdout")
    args = parser.parse_args()

    # Load inputs
    print("=" * 70, file=sys.stderr)
    print("L03 — FIELD CLASSIFICATION", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    if not os.path.exists(REGISTRY_FILE):
        print(f"ERROR: {REGISTRY_FILE} not found. Run L02 first.", file=sys.stderr)
        sys.exit(1)

    with open(REGISTRY_FILE) as f:
        registry = json.load(f)

    edge_profiles = []
    if os.path.exists(EDGE_PROFILES_FILE):
        with open(EDGE_PROFILES_FILE) as f:
            edge_profiles = json.load(f)

    # Build edge profile lookup
    ep_lookup = {ep["wallet"]: ep for ep in edge_profiles}

    # Load resolved markets for edge computation
    print("  Loading resolved markets cache...", file=sys.stderr)
    resolved = load_resolved_markets()
    print(f"  {len(resolved)} resolved market entries loaded", file=sys.stderr)

    accounts = registry.get("accounts", [])
    print(f"  {len(accounts)} accounts in registry", file=sys.stderr)

    # Process each account
    results = []
    for acct in accounts:
        wallet = acct["wallet"]
        alias = acct.get("alias", wallet[:10])
        dom_cat = acct.get("dominant_category", "OTHER")
        score = acct.get("insider_score", 0)

        result = analyze_wallet(wallet, alias, dom_cat, acct, resolved)
        result["insider_score"] = score
        result["account_type"] = acct.get("account_type", "UNKNOWN")
        result["follow_confidence"] = acct.get("follow_confidence", 0)
        result["total_profit_usd"] = acct.get("total_profit_usd", 0)
        results.append(result)

    # Cross-cluster analysis
    print("\n  Running cross-cluster analysis...", file=sys.stderr)
    clusters = cross_cluster_analysis(results, resolved)
    print(f"  {len(clusters)} temporal clusters found", file=sys.stderr)

    # Generate dossiers for high-confidence insiders
    os.makedirs(DOSSIER_DIR, exist_ok=True)
    dossier_count = 0
    for result in results:
        if result["insider_score"] >= args.min_score:
            acct = next((a for a in accounts if a["wallet"] == result["wallet"]), {})
            ep = ep_lookup.get(result["wallet"])
            dossier_md = generate_dossier(result, acct, ep)
            safe_alias = result["alias"].replace("/", "-").replace(" ", "-").lower()
            dossier_path = os.path.join(DOSSIER_DIR, f"{safe_alias}.md")
            with open(dossier_path, "w") as f:
                f.write(dossier_md)
            dossier_count += 1

    # Build output JSON
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "L03 field classification: sub-domain decomposition + institutional hypothesis",
        "n_accounts_processed": len(results),
        "n_with_trade_data": sum(1 for r in results if r.get("has_trade_data")),
        "n_dossiers_generated": dossier_count,
        "n_temporal_clusters": len(clusters),
        "accounts": [
            {
                "wallet": r["wallet"],
                "alias": r["alias"],
                "insider_score": r["insider_score"],
                "account_type": r["account_type"],
                "dominant_category": r["dominant_category"],
                "primary_subdomain": r.get("primary_subdomain"),
                "has_trade_data": r.get("has_trade_data", False),
                "subdomain_breakdown": r.get("subdomain_breakdown", []),
                "institutional_hypothesis": r.get("institutional_hypothesis"),
                "hypothesis_confidence": r.get("hypothesis_confidence"),
                "legal_risk": r.get("legal_risk", False),
                "trade_pattern": r.get("trade_pattern"),
                "follow_confidence": r.get("follow_confidence", 0),
                "total_profit_usd": r.get("total_profit_usd", 0),
            }
            for r in results
        ],
        "temporal_clusters": clusters,
    }

    # Write output
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Output: {OUTPUT_FILE}", file=sys.stderr)
    print(f"  Dossiers: {DOSSIER_DIR}/ ({dossier_count} files)", file=sys.stderr)

    if args.json:
        print(json.dumps(output, indent=2))
        return

    # Terminal report
    print("\n" + "=" * 70, file=sys.stderr)
    print("TOP INSIDERS — SUB-DOMAIN CLASSIFICATION", file=sys.stderr)
    print("=" * 70, file=sys.stderr)

    # Sort by insider score descending
    sorted_results = sorted(results, key=lambda x: -x["insider_score"])

    for r in sorted_results[:15]:
        score = r["insider_score"]
        alias = r["alias"]
        cat = r["dominant_category"]
        sd = r.get("primary_subdomain", "—")
        hyp = r.get("institutional_hypothesis", "—")
        conf = r.get("hypothesis_confidence", "—")
        profit = r.get("total_profit_usd", 0)
        has_data = "DATA" if r.get("has_trade_data") else "    "
        legal = " LEGAL-RISK" if r.get("legal_risk") else ""

        print(f"\n  [{score}] {alias:<22} {cat}>{sd}", file=sys.stderr)
        print(f"       {conf}: {hyp}{legal}", file=sys.stderr)
        print(f"       Profit: ${profit:>12,.0f}  [{has_data}]", file=sys.stderr)

        # Sub-domain breakdown (top 3)
        for sd_info in r.get("subdomain_breakdown", [])[:3]:
            pct = int(sd_info["as_pct_of_category_edge"] * 100)
            print(f"         {sd_info['subdomain']}: {sd_info['n']}tr, "
                  f"edge={sd_info['mean_edge']:+.3f}, {pct}%",
                  file=sys.stderr)

    # Cluster report
    if clusters:
        print(f"\n{'=' * 70}", file=sys.stderr)
        print("TEMPORAL CLUSTERS — Multiple insiders, same market, same direction", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        for c in clusters[:10]:
            members = ", ".join(m["alias"] for m in c["members"])
            print(f"\n  {c['market'][:60]}", file=sys.stderr)
            print(f"    Direction: {c['direction']} | "
                  f"Insiders: {c['n_insiders']} | "
                  f"Window: {c['window_hours']}h", file=sys.stderr)
            print(f"    Members: {members}", file=sys.stderr)

    # Legal risk summary
    legal_risk_accounts = [r for r in results if r.get("legal_risk")]
    if legal_risk_accounts:
        print(f"\n{'=' * 70}", file=sys.stderr)
        print("LEGAL RISK FLAGS", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        for r in legal_risk_accounts:
            print(f"  {r['alias']}: {r['primary_subdomain']} — "
                  f"{r.get('institutional_hypothesis', '?')}", file=sys.stderr)

    print(f"\n{'=' * 70}", file=sys.stderr)
    print(f"Done. {len(results)} accounts classified, "
          f"{dossier_count} dossiers written, "
          f"{len(clusters)} clusters found.", file=sys.stderr)


if __name__ == "__main__":
    main()
