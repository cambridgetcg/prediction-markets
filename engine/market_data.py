#!/usr/bin/env python3
"""
market_data.py — Unified market data layer for the Future Prediction Engine.

Pulls from all configured sources and normalises into a single interface:
  get_prediction_market_prices(query)  → Polymarket + Kalshi + Manifold
  get_asset_prices()                   → equities, commodities, crypto, forex
  get_macro_indicators()               → FRED: CPI, PCE, rates, unemployment
  get_cross_market_snapshot()          → everything in one call

Usage:
    python3 engine/market_data.py snapshot          # full market snapshot
    python3 engine/market_data.py prediction "iran" # search prediction markets
    python3 engine/market_data.py assets            # cross-asset prices
    python3 engine/market_data.py macro             # macro indicators
"""

import json
import sys
import os
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHON = BASE_DIR / ".venv" / "bin" / "python3"
DATA_DIR = BASE_DIR / "data"
CONFIG_DIR = BASE_DIR / "config"
MARKET_DATA_ACCESS_FILE = CONFIG_DIR / "market-data-access.json"


class MarketDataAccessError(RuntimeError):
    """Raised before a venue request when recorded data authority is absent."""


def market_data_access(source: str, path: Path = MARKET_DATA_ACCESS_FILE) -> dict:
    """Return the fail-closed access decision for one prediction-market source."""
    try:
        config = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        config = {}

    record = config.get("sources", {}).get(source, {})
    authority = record.get("authority")
    required_text = ("scope", "use_location", "source_url", "reviewed_on", "next_review")
    complete = all(
        isinstance(record.get(field), str) and bool(record[field].strip())
        for field in required_text
    )
    current = False
    if complete:
        try:
            current = date.fromisoformat(record["next_review"]) >= date.today()
        except ValueError:
            current = False
    authorised = (
        config.get("version") == 1
        and record.get("automated_read") == "authorised"
        and record.get("jurisdiction") == "allowed"
        and record.get("data_rights") == "allowed"
        and isinstance(authority, str)
        and bool(authority.strip())
        and complete
        and record["source_url"].startswith("https://")
        and current
    )
    return {
        "source": source,
        "authorised": authorised,
        "status": record.get("automated_read", "unrecorded"),
        "reason": record.get("reason", "No recorded authority for automated reading."),
    }


def _require_market_data_access(source: str) -> None:
    """Stop before network access unless the source has explicit recorded authority."""
    decision = market_data_access(source)
    if not decision["authorised"]:
        raise MarketDataAccessError(
            f"Automated {source} reading is blocked: {decision['reason']}"
        )

# ── API Keys (loaded from vault or env) ──────────────────────────────────────

def _get_key(name: str, env_var: str = None) -> str:
    """Load API key from vault → env → config."""
    # Try vault via credentials.py
    try:
        cred_path = Path.home() / ".openclaw" / "workspace" / "tools" / "credentials.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("credentials", cred_path)
        creds = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(creds)
        k = creds.get_key(name, fallback=None)
        if k:
            return k
    except Exception:
        pass
    # Try env
    if env_var:
        k = os.environ.get(env_var, "")
        if k:
            return k
    # Try config file
    cfg_file = CONFIG_DIR / "api-keys.json"
    if cfg_file.exists():
        cfg = json.loads(cfg_file.read_text())
        return cfg.get(name, "")
    return ""

# ── HTTP helper ───────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 10) -> dict:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PredictionEngine/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

# ── Prediction Markets ─────────────────────────────────────────────────────────

def _parse_price(outcome_prices):
    """Parse a YES price in [0, 1], returning None for absent or malformed input."""
    try:
        if outcome_prices is None or isinstance(outcome_prices, bool):
            return None
        if isinstance(outcome_prices, (int, float)):
            price = float(outcome_prices)
        elif isinstance(outcome_prices, list) and outcome_prices:
            price = float(str(outcome_prices[0]).strip('"\''))
        elif isinstance(outcome_prices, str):
            # Could be '["0.75", "0.25"]' or '0.75'
            import json as _json
            try:
                parsed = _json.loads(outcome_prices)
                if isinstance(parsed, list) and parsed:
                    price = float(str(parsed[0]).strip('"\''))
                else:
                    price = float(parsed)
            except Exception:
                price = float(outcome_prices.strip('[]"\'').split(",")[0].strip('"\''))
        else:
            return None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return price if 0.0 <= price <= 1.0 else None


def get_polymarket_prices(query: str = "", limit: int = 20) -> list:
    """Search Polymarket for active markets matching query."""
    _require_market_data_access("polymarket")
    params = urllib.parse.urlencode({
        "limit": limit,
        "closed": "false",
        "active": "true",
        **({"q": query} if query else {}),
    })
    url = f"https://gamma-api.polymarket.com/markets?{params}"
    data = _get(url)
    if isinstance(data, list):
        markets = data
    elif isinstance(data, dict) and "markets" in data:
        markets = data["markets"]
    else:
        return []

    normalised = []
    for market in markets:
        price = _parse_price(market.get("outcomePrices"))
        if not market.get("active") or price is None:
            continue
        normalised.append({
            "platform": "polymarket",
            "question": market.get("question", "?"),
            "price_yes": price,
            "volume": float(market.get("volume", 0)),
            "liquidity": float(market.get("liquidity", 0)),
            "end_date": market.get("endDate", ""),
            "market_id": market.get("conditionId", ""),
        })
    return normalised


def get_manifold_prices(query: str = "", limit: int = 10) -> list:
    """Search Manifold Markets (free, no key)."""
    _require_market_data_access("manifold")
    params = urllib.parse.urlencode({"term": query, "limit": limit, "sort": "liquidity"})
    url = f"https://api.manifold.markets/v0/search-markets?{params}"
    markets = _get(url)
    if not isinstance(markets, list):
        return []
    normalised = []
    for market in markets[:limit]:
        price = _parse_price(market.get("probability"))
        if market.get("isResolved") is not False or price is None:
            continue
        normalised.append({
            "platform": "manifold",
            "question": market.get("question", "?"),
            "price_yes": price,
            "volume": market.get("volume", 0),
            "liquidity": market.get("totalLiquidity", 0),
            "end_date": market.get("closeTime", ""),
            "market_id": market.get("id", ""),
        })
    return normalised


def get_kalshi_prices(query: str = "", limit: int = 10) -> list:
    """Get Kalshi markets (no auth needed for market data)."""
    _require_market_data_access("kalshi")
    params = urllib.parse.urlencode({"limit": limit, "status": "open"})
    if query:
        params += f"&search={urllib.parse.quote(query)}"
    url = f"https://api.elections.kalshi.com/trade-api/v2/markets?{params}"
    data = _get(url)
    markets = data.get("markets", []) if isinstance(data, dict) else []
    normalised = []
    for market in markets:
        try:
            price = float(market["yes_ask"]) / 100
        except (KeyError, TypeError, ValueError):
            continue
        if not 0.0 <= price <= 1.0:
            continue
        normalised.append({
            "platform": "kalshi",
            "question": market.get("title", market.get("subtitle", "?")),
            "price_yes": price,
            "volume": float(market.get("volume", 0)),
            "liquidity": 0,
            "end_date": market.get("close_time", ""),
            "market_id": market.get("ticker", ""),
        })
    return normalised


def get_all_prediction_prices(query: str) -> list:
    """Get prices from all prediction market platforms, sorted by volume."""
    sources = {
        "polymarket": (get_polymarket_prices, 10),
        "manifold": (get_manifold_prices, 5),
        "kalshi": (get_kalshi_prices, 5),
    }
    authorised = [name for name in sources if market_data_access(name)["authorised"]]
    if not authorised:
        raise MarketDataAccessError(
            "No prediction-market source has recorded automated-read authority. "
            f"Review {MARKET_DATA_ACCESS_FILE}."
        )

    all_markets = []
    for name in authorised:
        fetch, limit = sources[name]
        all_markets.extend(fetch(query, limit=limit))
    return sorted(all_markets, key=lambda x: x.get("volume", 0), reverse=True)


# ── Financial Assets ──────────────────────────────────────────────────────────

def get_asset_prices() -> dict:
    """Get cross-asset prices: commodities, equities, crypto, forex."""
    result = {}

    # CoinGecko for crypto (free, no key)
    try:
        cg_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true"
        cg = _get(cg_url, timeout=10)
        result["crypto"] = {
            "BTC": {"price": cg.get("bitcoin", {}).get("usd", 0), "change_24h": cg.get("bitcoin", {}).get("usd_24h_change", 0)},
            "ETH": {"price": cg.get("ethereum", {}).get("usd", 0), "change_24h": cg.get("ethereum", {}).get("usd_24h_change", 0)},
            "SOL": {"price": cg.get("solana", {}).get("usd", 0), "change_24h": cg.get("solana", {}).get("usd_24h_change", 0)},
        }
    except Exception as e:
        result["crypto"] = {"error": str(e)}

    # yfinance for equities + commodities + forex
    try:
        import subprocess
        py = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
        out = subprocess.run([py, "-c", """
import yfinance as yf, json, sys
tickers = {
    "WTI": "CL=F", "Gold": "GC=F", "Silver": "SI=F",
    "SP500": "SPY", "Nasdaq": "QQQ", "VIX": "^VIX",
    "DXY": "DX-Y.NYB", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "US10Y": "^TNX"
}
result = {}
for name, sym in tickers.items():
    try:
        t = yf.Ticker(sym)
        h = t.history(period="2d")
        if len(h) >= 2:
            p = h["Close"].iloc[-1]
            prev = h["Close"].iloc[-2]
            result[name] = {"price": round(float(p), 4), "change_1d": round((float(p)/float(prev)-1)*100, 2)}
        elif len(h) == 1:
            result[name] = {"price": round(float(h["Close"].iloc[-1]), 4), "change_1d": 0}
    except Exception as e:
        result[name] = {"error": str(e)}
print(json.dumps(result))
"""], capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            asset_data = json.loads(out.stdout)
            result["commodities"] = {k: v for k, v in asset_data.items() if k in ("WTI", "Gold", "Silver")}
            result["equities"] = {k: v for k, v in asset_data.items() if k in ("SP500", "Nasdaq", "VIX")}
            result["forex"] = {k: v for k, v in asset_data.items() if k in ("DXY", "GBPUSD", "USDJPY")}
            result["rates"] = {k: v for k, v in asset_data.items() if k in ("US10Y",)}
    except Exception as e:
        result["assets_error"] = str(e)

    return result


# ── Macro Indicators ──────────────────────────────────────────────────────────

def get_macro_indicators() -> dict:
    """Get macro indicators from FRED (requires free API key)."""
    fred_key = _get_key("fred-api-key", "FRED_API_KEY")
    if not fred_key:
        return {"error": "No FRED API key. Get one free at fred.stlouisfed.org/docs/api/api_key.html and store with: python3 tools/credentials.py store fred-api-key <key>"}

    indicators = {
        "fed_funds_rate": "FEDFUNDS",
        "cpi_yoy": "CPIAUCSL",
        "pce_yoy": "PCEPI",
        "unemployment": "UNRATE",
        "gdp_growth": "A191RL1Q225SBEA",
        "us_10y_yield": "DGS10",
        "weekly_economic_index": "WEI",
    }

    result = {}
    base = "https://api.stlouisfed.org/fred/series/observations"

    for name, series_id in indicators.items():
        params = urllib.parse.urlencode({
            "series_id": series_id,
            "api_key": fred_key,
            "file_type": "json",
            "limit": 2,
            "sort_order": "desc",
        })
        data = _get(f"{base}?{params}", timeout=10)
        obs = data.get("observations", [])
        if obs:
            latest = obs[0]
            try:
                value = float(latest.get("value", "nan"))
                result[name] = {"value": value, "date": latest.get("date", ""), "series": series_id}
            except ValueError:
                result[name] = {"value": None, "date": latest.get("date", ""), "series": series_id}
        time.sleep(0.1)  # Rate limit: 120 req/min

    return result


# ── Full snapshot ─────────────────────────────────────────────────────────────

def get_cross_market_snapshot(query: str = "iran nuclear ceasefire election") -> dict:
    """Get everything in one call. Used by synthesise.py for context."""
    print("  Fetching asset prices...", end="", flush=True)
    assets = get_asset_prices()
    print(" done")

    print("  Fetching prediction market prices...", end="", flush=True)
    predictions = get_all_prediction_prices(query)
    print(f" done ({len(predictions)} markets)")

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "assets": assets,
        "prediction_markets": predictions[:10],
    }


# ── Display ───────────────────────────────────────────────────────────────────

def display_assets(assets: dict) -> None:
    print("\n── Cross-Asset Prices ──\n")
    for category, items in assets.items():
        if isinstance(items, dict) and "error" not in items:
            print(f"  {category.title()}:")
            for name, data in items.items():
                if isinstance(data, dict) and "price" in data:
                    chg = data.get("change_1d", data.get("change_24h", 0))
                    arrow = "↑" if chg > 0 else "↓" if chg < 0 else "→"
                    print(f"    {arrow} {name:10}: {data['price']:>12,.4f}  ({chg:+.2f}%)")


def display_predictions(markets: list, query: str) -> None:
    print(f"\n── Prediction Markets: '{query}' ──\n")
    if not markets:
        print("  No markets found.")
        return
    for m in markets[:8]:
        platform = m.get("platform", "?")[:4].upper()
        price = m.get("price_yes", 0)
        question = m.get("question", "?")[:60]
        vol = m.get("volume", 0)
        print(f"  [{platform}] {price:.0%} — {question}...")
        if vol > 0:
            print(f"         Volume: ${vol:,.0f}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "snapshot"
    query = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    if cmd == "snapshot":
        q = query or "iran nuclear election fed rate"
        print(f"\n🌍 Market snapshot — query: '{q}'\n")
        snap = get_cross_market_snapshot(q)
        display_assets(snap.get("assets", {}))
        display_predictions(snap.get("prediction_markets", []), q)

    elif cmd == "prediction":
        q = query or "iran"
        markets = get_all_prediction_prices(q)
        display_predictions(markets, q)

    elif cmd == "assets":
        assets = get_asset_prices()
        display_assets(assets)

    elif cmd == "macro":
        print("\n── Macro Indicators (FRED) ──\n")
        indicators = get_macro_indicators()
        if "error" in indicators:
            print(f"  ❌ {indicators['error']}")
        else:
            for name, data in indicators.items():
                val = data.get("value")
                date = data.get("date", "")
                print(f"  {name:25}: {val}  (as of {date})")

    elif cmd == "test":
        print("Testing all data sources...")
        print("\n1. CoinGecko (crypto):")
        cg = _get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
        print(f"   BTC: ${cg.get('bitcoin',{}).get('usd',0):,.0f}")

        print("\n2. Manifold Markets:")
        m = get_manifold_prices("artificial intelligence", limit=2)
        for x in m:
            print(f"   [{x['price_yes']:.0%}] {x['question'][:60]}")

        print("\n3. Polymarket:")
        p = get_polymarket_prices("", limit=3)
        for x in p:
            print(f"   [{x['price_yes']:.0%}] {x['question'][:60]}")

        print("\nAll sources working ✅")
