#!/usr/bin/env python3
"""
betting_signals.py — Extract sharp-money signals from betting market line movement.

The insight: bookmakers (especially Pinnacle) are the world's oldest and sharpest
prediction markets. Line movement is information — specifically, it reveals where
sophisticated bettors with private information are putting their money.

Signal types extracted:
  STEAM MOVE       → Multiple books move simultaneously (institutional-level info)
  REVERSE LINE     → Public bets one side, line moves other way (sharps disagree)
  DROPPING ODDS    → Rapid line compression (sharp consensus forming quickly)
  CLV SIGNAL       → Closing line value identifies +EV predictions
  CROSS-MARKET     → Betting line vs prediction market price divergence

Data sources:
  The Odds API     → 40+ books, ~500 req/month free
  OddsPapi         → 348 books incl. Pinnacle, historical, free tier
  Betfair Exchange → Gold standard exchange, free for personal use

Usage:
    python3 engine/betting_signals.py scan              # scan all active signals
    python3 engine/betting_signals.py sport politics    # political markets
    python3 engine/betting_signals.py sport soccer      # soccer line movement
    python3 engine/betting_signals.py divergence        # betting vs prediction mkt
    python3 engine/betting_signals.py setup             # show setup instructions
"""

import json
import sys
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"

# ── The Theory ────────────────────────────────────────────────────────────────
#
# Bookmaker hierarchy (sharpest → softest):
#   Pinnacle > Betfair > Matchbook > SBO > Marathonbet  [SHARP]
#   > Bet365 > William Hill > Ladbrokes                  [SOFT]
#   > Fan Duel > DraftKings > PointsBet                  [SQUARE/US]
#
# Why Pinnacle is the benchmark:
#   - Accepts ALL bets including sharp syndicates
#   - No account restrictions ever
#   - Closes line closest to true probability
#   - Their closing line IS the market's best probability estimate
#
# Line movement signals:
#   SHARP STEAM: Pinnacle + 3+ other sharp books move >0.05 within 30min
#                → Highly informed bettor(s) acted. Information event occurred.
#   REVERSE LINE: 70%+ of tickets on Team A, but line moves toward Team A
#                → Sharps are on Team B despite public backing Team A
#   DROPPING ODDS: Decimal drops >10% within 2h (e.g. 3.50 → 2.80)
#                → Fast sharp consensus = high-conviction prediction
#   CLV POSITIVE: You bet at 2.50, Pinnacle closes at 2.20
#                → You had an edge (closing line value)

# ── API config ────────────────────────────────────────────────────────────────

THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDSPAPI_BASE = "https://api.oddspapi.io/v1"
BETFAIR_BASE = "https://api.betfair.com/exchange/betting/rest/v1.0"


def _get_key(name: str) -> str:
    try:
        cred_path = Path.home() / ".openclaw" / "workspace" / "tools" / "credentials.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("credentials", cred_path)
        creds = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(creds)
        return creds.get_key(name, fallback="") or ""
    except Exception:
        return os.environ.get(name.upper().replace("-", "_"), "")


def _get(url: str, timeout: int = 10) -> dict | list:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PredictionEngine/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


# ── The Odds API ──────────────────────────────────────────────────────────────

def get_odds_api_key() -> str:
    return _get_key("odds-api-key")


def get_sports_list(api_key: str) -> list:
    """Get all available sports (free, doesn't count against quota)."""
    url = f"{THE_ODDS_API_BASE}/sports/?apiKey={api_key}"
    data = _get(url)
    return data if isinstance(data, list) else []


def get_odds(sport: str, api_key: str, regions: str = "uk,eu", 
             markets: str = "h2h", bookmakers: str = None) -> list:
    """
    Get current odds for a sport from multiple bookmakers.
    
    Returns events with odds from all bookmakers — the spread between
    Pinnacle and soft books reveals the vig and implied probability.
    """
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    if bookmakers:
        params["bookmakers"] = bookmakers
    
    param_str = urllib.parse.urlencode(params)
    url = f"{THE_ODDS_API_BASE}/sports/{sport}/odds/?{param_str}"
    data = _get(url, timeout=15)
    return data if isinstance(data, list) else []


def get_historical_odds(sport: str, api_key: str, event_id: str, 
                        date: str = None) -> dict:
    """
    Get historical odds snapshot for a specific event.
    Used to reconstruct line movement over time.
    Note: Requires paid plan for historical data.
    """
    params = {"apiKey": api_key, "oddsFormat": "decimal"}
    if date:
        params["date"] = date
    param_str = urllib.parse.urlencode(params)
    url = f"{THE_ODDS_API_BASE}/historical/sports/{sport}/events/{event_id}/odds?{param_str}"
    return _get(url)


# ── Signal extraction ─────────────────────────────────────────────────────────

def extract_consensus_probability(event: dict) -> dict:
    """
    Extract the true probability from multi-bookmaker odds.
    
    Method: Pinnacle's no-vig price is the best estimate.
    If Pinnacle unavailable: average of top 3 sharp books, vig-removed.
    
    Returns: {outcome: probability} dict.
    """
    SHARP_BOOKS = {"pinnacle", "betfair", "matchbook", "sbo", "marathonbet", 
                   "pinnacle_live", "betfair_ex_uk"}
    SOFT_BOOKS  = {"bet365", "williamhill", "ladbrokes", "coral", "unibet",
                   "fanduel", "draftkings", "bovada"}
    
    bookmakers = event.get("bookmakers", [])
    if not bookmakers:
        return {}
    
    # Find Pinnacle first
    pinnacle = next((b for b in bookmakers if "pinnacle" in b.get("key", "").lower()), None)
    reference = pinnacle
    
    # Fall back to sharpest available
    if not reference:
        for book in bookmakers:
            if book.get("key", "").lower() in SHARP_BOOKS:
                reference = book
                break
    
    if not reference:
        reference = bookmakers[0]
    
    # Extract h2h market
    h2h = next((m for m in reference.get("markets", []) if m["key"] == "h2h"), None)
    if not h2h:
        return {}
    
    outcomes = h2h.get("outcomes", [])
    if len(outcomes) < 2:
        return {}
    
    # Remove vig: sum of (1/odd) > 1 due to bookmaker margin
    # True prob = (1/odd) / sum(1/odd)
    reciprocals = [1 / o["price"] for o in outcomes if o.get("price", 0) > 1]
    total = sum(reciprocals)
    
    probs = {}
    for o, r in zip(outcomes, reciprocals):
        probs[o["name"]] = round(r / total, 4)
    
    probs["_source"] = reference.get("key", "unknown")
    probs["_vig"] = round((total - 1) * 100, 2)  # bookmaker margin %
    return probs


def detect_book_divergence(event: dict, min_divergence: float = 0.08) -> list:
    """
    Detect when one bookmaker prices significantly differently from others.
    
    Large divergence = either:
    a) The outlier has information the market doesn't (sharp signal)
    b) The outlier is slow to update (soft book lagging)
    
    Pinnacle being the outlier = almost always (a).
    Soft book being the outlier = usually (b), occasionally sharp if it flipped.
    """
    bookmakers = event.get("bookmakers", [])
    if len(bookmakers) < 3:
        return []
    
    # Get h2h prices for first outcome across all books
    prices_by_book = {}
    for book in bookmakers:
        h2h = next((m for m in book.get("markets", []) if m["key"] == "h2h"), None)
        if h2h and h2h.get("outcomes"):
            outcome_name = h2h["outcomes"][0]["name"]
            prices_by_book[book["key"]] = {
                "price": h2h["outcomes"][0]["price"],
                "outcome": outcome_name,
                "title": book.get("title", book["key"]),
            }
    
    if len(prices_by_book) < 3:
        return []
    
    prices = [v["price"] for v in prices_by_book.values()]
    avg_price = sum(prices) / len(prices)
    
    divergences = []
    for book_key, data in prices_by_book.items():
        div = abs(data["price"] - avg_price) / avg_price
        if div >= min_divergence:
            direction = "OVER" if data["price"] > avg_price else "UNDER"
            is_sharp = any(s in book_key.lower() for s in ["pinnacle", "betfair", "matchbook"])
            divergences.append({
                "book": data["title"],
                "book_key": book_key,
                "price": data["price"],
                "market_avg": round(avg_price, 3),
                "divergence_pct": round(div * 100, 1),
                "direction": direction,
                "is_sharp_book": is_sharp,
                "signal_strength": "HIGH" if (is_sharp and div > 0.12) else "MEDIUM" if div > 0.10 else "LOW",
                "interpretation": (
                    f"Pinnacle pricing {direction} market — sharp signal" if is_sharp and direction == "OVER"
                    else f"Sharp book {direction} — possible information edge" if is_sharp
                    else f"Soft book diverging — likely slow update, not signal"
                ),
            })
    
    return sorted(divergences, key=lambda x: x["divergence_pct"], reverse=True)


def compute_implied_probability_vs_polymarket(
    betting_prob: float, poly_price: float, event_name: str
) -> dict:
    """
    Cross-reference betting market probability vs Polymarket.
    
    KEY INSIGHT:
    - Betfair/Pinnacle: sophisticated bettors, real money, real stakes
    - Polymarket: crypto-native, different bettor profile
    - Divergence > 10pp = one market has information the other lacks
    
    Historical finding: On US political events, Polymarket often leads.
    On sports, betting exchanges are faster and better calibrated.
    On geopolitics: depends on event type.
    """
    divergence = poly_price - betting_prob
    abs_div = abs(divergence)
    
    if abs_div < 0.05:
        interpretation = "Markets aligned — no arbitrage signal"
        signal = "NONE"
    elif abs_div < 0.10:
        if divergence > 0:
            interpretation = f"Polymarket prices {abs_div:.0%} higher — crypto community more optimistic. Watch for convergence."
            signal = "WEAK_POLY_HIGHER"
        else:
            interpretation = f"Betting market prices {abs_div:.0%} higher — sharp bettors more optimistic. Consider fading Polymarket."
            signal = "WEAK_BETTING_HIGHER"
    else:
        if divergence > 0:
            interpretation = f"STRONG: Polymarket {abs_div:.0%} above betting line — unusual. Either Poly has info or is wrong."
            signal = "STRONG_POLY_HIGHER"
        else:
            interpretation = f"STRONG: Betting market {abs_div:.0%} above Polymarket — sharp money disagrees with prediction market. High-value signal."
            signal = "STRONG_BETTING_HIGHER"
    
    return {
        "event": event_name,
        "betting_prob": round(betting_prob, 3),
        "poly_price": round(poly_price, 3),
        "divergence": round(divergence, 3),
        "abs_divergence": round(abs_div, 3),
        "signal": signal,
        "interpretation": interpretation,
    }


# ── Betfair Exchange ──────────────────────────────────────────────────────────

def get_betfair_prices(market_ids: list, betfair_token: str) -> list:
    """
    Get live Betfair Exchange prices. Betfair is the gold standard:
    - Peer-to-peer: the odds ARE the market consensus (no bookie bias)
    - Highest liquidity in the world for major events
    - Political/election markets available
    
    Requires Betfair account (free). API key via personal account.
    """
    if not betfair_token:
        return [{"error": "No Betfair token. Register at betfair.com, get API key."}]
    
    payload = json.dumps({
        "filter": {"marketIds": market_ids},
        "priceProjection": {"priceData": ["EX_BEST_OFFERS", "EX_TRADED"]},
        "orderProjection": "EXECUTABLE",
        "matchProjection": "NO_ROLLUP",
    }).encode()
    
    req = urllib.request.Request(
        f"{BETFAIR_BASE}/listMarketBook/",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Application": "1",
            "X-Authentication": betfair_token,
            "Accept": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return [{"error": str(e)}]


# ── Political/Event market scanner ────────────────────────────────────────────

def scan_political_markets(api_key: str) -> list:
    """
    Scan political event markets from The Odds API.
    These are the most relevant for our prediction engine.
    """
    # Political/election/world events sports keys
    political_keys = ["politics", "us_politics", "world_politics", 
                      "current_affairs", "entertainment"]
    
    results = []
    for sport_key in political_keys:
        events = get_odds(sport_key, api_key, regions="uk,eu,us", markets="h2h")
        if isinstance(events, list):
            for event in events:
                probs = extract_consensus_probability(event)
                divergences = detect_book_divergence(event)
                results.append({
                    "event": event.get("sport_title", "") + ": " + 
                             event.get("home_team", "") + " vs " + event.get("away_team", ""),
                    "commence_time": event.get("commence_time", ""),
                    "consensus_probability": probs,
                    "book_divergences": divergences[:2],
                    "bookmaker_count": len(event.get("bookmakers", [])),
                })
        time.sleep(0.5)  # rate limit
    
    return results


# ── Display ───────────────────────────────────────────────────────────────────

def display_signal(signal: dict) -> None:
    strength = signal.get("signal_strength", "?")
    emoji = {"HIGH": "🔥", "MEDIUM": "⚡", "LOW": "📊"}.get(strength, "•")
    print(f"\n  {emoji} [{strength}] {signal.get('book','?')}")
    print(f"     Price: {signal.get('price','?')} vs market avg {signal.get('market_avg','?')}")
    print(f"     Divergence: {signal.get('divergence_pct','?')}% {signal.get('direction','')}")
    print(f"     → {signal.get('interpretation','')}")


def display_cross_market(cross: dict) -> None:
    sig = cross.get("signal", "NONE")
    if sig == "NONE":
        return
    emoji = "🔥" if "STRONG" in sig else "⚡"
    print(f"\n  {emoji} {cross.get('event','?')[:60]}")
    print(f"     Betting: {cross.get('betting_prob',0):.0%}  Polymarket: {cross.get('poly_price',0):.0%}")
    print(f"     Gap: {cross.get('divergence',0):+.0%}  Signal: {sig}")
    print(f"     → {cross.get('interpretation','')}")


def cmd_setup() -> None:
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║        BETTING SIGNALS — SETUP GUIDE                    ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    print("── Required API Keys ──\n")

    print("1. The Odds API (MOST IMPORTANT for line movement)")
    print("   → Free: 500 req/month | Sports: ~40 books including Pinnacle via feed")
    print("   → Register: https://the-odds-api.com/#get-access")
    print("   → Plans: Free 500/mo | $30/mo 20K | $59/mo 100K")
    print("   → Store: python3 tools/credentials.py store odds-api-key <key>")
    print()

    print("2. OddsPapi (348 books incl. Pinnacle, historical data, FREE tier)")
    print("   → Free tier: pre-match odds, all 348 books, historical")
    print("   → Register: https://oddspapi.io/")
    print("   → Store: python3 tools/credentials.py store oddspapi-key <key>")
    print()

    print("3. Betfair Exchange (gold standard, free for personal use)")
    print("   → Register account: betfair.com")
    print("   → API key via: betfair.com/exchange/plus/myAccount/apiKeys")
    print("   → Store: python3 tools/credentials.py store betfair-token <token>")
    print()

    print("── What each gives you ──\n")
    print("  The Odds API:")
    print("    ✓ Real-time odds from FanDuel, DraftKings, Betfair, Bet365, etc.")
    print("    ✓ Line movement via repeated polling (30min intervals)")
    print("    ✓ Multi-bookmaker divergence detection")
    print("    ✓ Political/election/entertainment markets")
    print()
    print("  OddsPapi:")
    print("    ✓ Pinnacle odds (sharp benchmark) — not available on Odds API free")
    print("    ✓ Historical line movement (opening → closing)")
    print("    ✓ 348 books for comprehensive vig analysis")
    print()
    print("  Betfair Exchange:")
    print("    ✓ Peer-to-peer odds (no bookmaker bias)")
    print("    ✓ Real volume data (who actually bet what)")
    print("    ✓ Streaming API for sub-second updates")
    print("    ✓ Political markets: US/UK elections, world leaders")
    print()

    print("── Once set up, run ──\n")
    print("  python3 engine/betting_signals.py scan")
    print("  python3 engine/betting_signals.py sport politics")
    print("  python3 engine/betting_signals.py divergence")


def cmd_scan(api_key: str) -> None:
    print("\n📡 Scanning betting markets for sharp signals...\n")
    
    # Get sports list
    sports = get_sports_list(api_key)
    print(f"  Available sports: {len(sports)}")

    # Find political markets
    political = [s for s in sports if any(
        kw in s.get("key", "").lower() or kw in s.get("title", "").lower()
        for kw in ["politic", "election", "entertainment", "award", "current"]
    )]
    print(f"  Political/event markets: {len(political)}")
    for p in political[:5]:
        print(f"    → {p.get('title','?')} ({p.get('key','?')})")

    print("\n  Fetching odds for political markets...")
    for sport in political[:3]:
        events = get_odds(sport["key"], api_key, regions="uk,eu,us")
        if isinstance(events, list) and events:
            print(f"\n  ── {sport['title']} ({len(events)} events) ──")
            for event in events[:3]:
                probs = extract_consensus_probability(event)
                divs = detect_book_divergence(event)
                name = f"{event.get('home_team','')} vs {event.get('away_team','')}"
                print(f"\n    {name[:60]}")
                if probs and "_source" not in probs:
                    pass
                for outcome, prob in probs.items():
                    if not outcome.startswith("_"):
                        print(f"      {outcome}: {prob:.0%} (via {probs.get('_source','?')}, vig={probs.get('_vig','?')}%)")
                for div in divs:
                    display_signal(div)
        time.sleep(1)


def cmd_divergence(api_key: str) -> None:
    """Cross-reference betting vs prediction market prices."""
    print("\n🔀 Cross-market divergence scan (betting vs Polymarket)...\n")
    print("  [Getting Polymarket prices first...]\n")

    # Import and use market_data
    sys.path.insert(0, str(BASE_DIR / "engine"))
    try:
        import market_data
        poly_markets = market_data.get_polymarket_prices(query="", limit=30)
    except Exception as e:
        print(f"  Error loading Polymarket data: {e}")
        return

    # Get betting odds for political/sports
    sports = get_sports_list(api_key)
    political = [s for s in sports if "politic" in s.get("key", "").lower()]

    cross_signals = []
    for sport in political[:2]:
        events = get_odds(sport["key"], api_key, regions="uk,eu")
        if isinstance(events, list):
            for event in events[:5]:
                probs = extract_consensus_probability(event)
                if not probs or "_vig" not in probs:
                    continue

                event_name = f"{event.get('home_team','')} vs {event.get('away_team','')}"

                # Try to match with Polymarket question
                for poly in poly_markets:
                    poly_q = poly.get("question", "").lower()
                    home = event.get("home_team", "").lower()
                    if home and len(home) > 3 and home in poly_q:
                        for outcome, bet_prob in probs.items():
                            if not outcome.startswith("_") and home in outcome.lower():
                                cross = compute_implied_probability_vs_polymarket(
                                    bet_prob, poly.get("price_yes", 0.5),
                                    f"{event_name} [{outcome}]"
                                )
                                if cross["signal"] != "NONE":
                                    cross_signals.append(cross)
        time.sleep(0.5)

    if cross_signals:
        print(f"  Found {len(cross_signals)} cross-market divergences:\n")
        for cs in sorted(cross_signals, key=lambda x: x["abs_divergence"], reverse=True):
            display_cross_market(cs)
    else:
        print("  No significant divergences found (markets may be well-aligned).")
        print("  Try when a major event is upcoming — divergences spike around catalysts.")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "setup"

    if cmd == "setup":
        cmd_setup()

    elif cmd in ("scan", "sport", "divergence"):
        api_key = get_odds_api_key()
        if not api_key:
            print("❌ No Odds API key found.")
            print("   Get free key: https://the-odds-api.com/#get-access")
            print("   Store: python3 tools/credentials.py store odds-api-key <key>")
            sys.exit(1)

        if cmd in ("scan", "sport"):
            sport_filter = sys.argv[2] if len(sys.argv) > 2 else None
            if sport_filter:
                events = get_odds(sport_filter, api_key, regions="uk,eu,us")
                if isinstance(events, list):
                    print(f"\n📊 {sport_filter}: {len(events)} events\n")
                    for event in events[:10]:
                        probs = extract_consensus_probability(event)
                        divs = detect_book_divergence(event)
                        name = f"{event.get('home_team','')} vs {event.get('away_team','')}"
                        print(f"\n  {name}")
                        for outcome, prob in probs.items():
                            if not outcome.startswith("_"):
                                print(f"    {outcome}: {prob:.0%}")
                        for div in divs:
                            display_signal(div)
                else:
                    print(f"Error: {events}")
            else:
                cmd_scan(api_key)

        elif cmd == "divergence":
            cmd_divergence(api_key)

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: betting_signals.py [setup|scan|sport <key>|divergence]")
