#!/usr/bin/env python3
"""
whale-monitor.py — Monitor known whale wallets for Polymarket activity on Polygon.

Usage:
    python3 whale-monitor.py                    # Full scan + dashboard
    python3 whale-monitor.py --wallet 0x9d84... # Single wallet deep dive
    python3 whale-monitor.py --market "Iran"    # Filter by market keyword

Requirements:
    - Polygonscan API key (free: https://polygonscan.com/apis)
    - Set env: export POLYGONSCAN_API_KEY=your_key
    - whale-registry.json in ../data/

All dependencies are stdlib (json, urllib, datetime, os, sys).
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

# --- Configuration ---

POLYGONSCAN_API = "https://api.polygonscan.com/api"
POLYGONSCAN_API_KEY = os.environ.get("POLYGONSCAN_API_KEY", "")

# Polymarket contract addresses (Polygon mainnet)
POLYMARKET_CONTRACTS = {
    "CTF_EXCHANGE": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
    "NEG_RISK_CTF": "0xC5d563A36AE78145C45a50134d48A1215220f80a",
    "NEG_RISK_ADAPTER": "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
    "CONDITIONAL_TOKENS": "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",
    "USDC_E": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
}

POLYMARKET_CONTRACT_SET = {v.lower() for v in POLYMARKET_CONTRACTS.values()}

# Gamma API for market metadata
GAMMA_API = "https://gamma-api.polymarket.com"

# Minimum trade size to alert (in USDC, 6 decimals)
MIN_ALERT_SIZE_USD = 5000

# How far back to look (hours)
LOOKBACK_HOURS = 24

# Rate limiting
POLYGONSCAN_DELAY = 0.25  # seconds between API calls (free tier: 5 req/s)

# --- File paths ---

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
REGISTRY_PATH = DATA_DIR / "whale-registry.json"

# --- Helpers ---


def load_registry():
    """Load whale-registry.json. Returns list of wallet dicts."""
    if not REGISTRY_PATH.exists():
        print(f"ERROR: {REGISTRY_PATH} not found.")
        sys.exit(1)
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)
    # Filter to wallets with actual addresses (not UNKNOWN/PARTIAL)
    valid = []
    for w in registry:
        addr = w.get("wallet", "")
        if addr.startswith("0x") and len(addr) == 42:
            valid.append(w)
    return valid


def polygonscan_request(params):
    """Make a Polygonscan API request. Returns parsed JSON or None."""
    if not POLYGONSCAN_API_KEY:
        print("WARNING: No POLYGONSCAN_API_KEY set. Using keyless mode (very limited).")
    else:
        params["apikey"] = POLYGONSCAN_API_KEY

    url = f"{POLYGONSCAN_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "whale-monitor/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "1":
                return data.get("result", [])
            elif data.get("message") == "No transactions found":
                return []
            else:
                print(f"  API warning: {data.get('message', 'unknown')}")
                return []
    except Exception as e:
        print(f"  API error: {e}")
        return []


def get_wallet_txns(wallet_addr, start_timestamp):
    """
    Fetch recent transactions FROM a wallet to Polymarket contracts.
    Returns list of transaction dicts.
    """
    params = {
        "module": "account",
        "action": "txlist",
        "address": wallet_addr,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "page": 1,
        "offset": 50,  # Last 50 txns
    }
    txns = polygonscan_request(params)
    if not txns:
        return []

    # Filter to Polymarket contracts and recent timeframe
    polymarket_txns = []
    for tx in txns:
        ts = int(tx.get("timeStamp", 0))
        to_addr = tx.get("to", "").lower()
        if ts >= start_timestamp and to_addr in POLYMARKET_CONTRACT_SET:
            polymarket_txns.append(tx)

    return polymarket_txns


def get_erc20_transfers(wallet_addr, start_timestamp):
    """
    Fetch ERC-20 token transfers (USDC.e) for a wallet.
    More reliable for detecting trade sizes than raw txns.
    """
    params = {
        "module": "account",
        "action": "tokentx",
        "address": wallet_addr,
        "contractaddress": POLYMARKET_CONTRACTS["USDC_E"],
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "page": 1,
        "offset": 50,
    }
    transfers = polygonscan_request(params)
    if not transfers:
        return []

    recent = []
    for tx in transfers:
        ts = int(tx.get("timeStamp", 0))
        if ts >= start_timestamp:
            recent.append(tx)

    return recent


def estimate_trade_size(transfers, wallet_addr):
    """
    Estimate trade sizes from USDC.e transfers.
    Outgoing USDC = buying shares. Incoming USDC = selling shares or resolution payout.
    Returns list of (timestamp, direction, amount_usd).
    """
    trades = []
    for tx in transfers:
        amount_raw = int(tx.get("value", 0))
        amount_usd = amount_raw / 1_000_000  # USDC has 6 decimals
        ts = int(tx.get("timeStamp", 0))
        from_addr = tx.get("from", "").lower()

        if amount_usd < MIN_ALERT_SIZE_USD:
            continue

        if from_addr == wallet_addr.lower():
            direction = "BUYING"  # USDC leaving wallet = buying shares
        else:
            direction = "SELLING/PAYOUT"  # USDC entering wallet

        trades.append({
            "timestamp": ts,
            "datetime": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC"),
            "direction": direction,
            "amount_usd": round(amount_usd, 2),
            "tx_hash": tx.get("hash", ""),
        })

    return trades


def gamma_search_markets(keyword):
    """
    Search Gamma API for markets matching a keyword.
    Used to decode which market a trade is related to (by timing correlation).
    """
    url = f"{GAMMA_API}/markets?limit=10&closed=false&order=volume&ascending=false"
    req = urllib.request.Request(url, headers={"User-Agent": "whale-monitor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            markets = json.loads(resp.read().decode())
            if keyword:
                return [m for m in markets if keyword.lower() in m.get("question", "").lower()]
            return markets
    except Exception as e:
        print(f"  Gamma API error: {e}")
        return []


def load_open_positions():
    """
    Load our open paper-trading positions for contradiction analysis.
    Returns list of position dicts.
    """
    positions_path = SCRIPT_DIR.parent / "strategies" / "paper-trades" / "positions.json"
    if not positions_path.exists():
        return []
    with open(positions_path) as f:
        data = json.load(f)
    # Handle both list and dict-with-positions format
    if isinstance(data, dict):
        return data.get("positions", data.get("open_positions", []))
    return data


# --- Dashboard Output ---


def print_dashboard(results, positions):
    """Print the whale signal dashboard."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'=' * 60}")
    print(f"  WHALE SIGNAL DASHBOARD — {now}")
    print(f"{'=' * 60}\n")

    if not results:
        print("  NO WHALE ACTIVITY detected in the lookback window.")
        print(f"  (Checked {LOOKBACK_HOURS}h window on wallets with valid addresses)")
        print()
    else:
        print(f"  RECENT WHALE ACTIVITY (last {LOOKBACK_HOURS}h):\n")
        for r in results:
            alias = r["alias"]
            wallet_short = r["wallet"][:8] + "..." + r["wallet"][-4:]
            domain = ", ".join(r.get("domain_focus", ["?"]))

            print(f"  [{wallet_short}] (alias: {alias})")
            for trade in r["trades"]:
                print(f"    {trade['direction']} ${trade['amount_usd']:,.0f} USDC at {trade['datetime']}")
                print(f"    Domain focus: {domain} | Follow confidence: {r.get('follow_confidence', '?')}/5")
                print(f"    Tx: https://polygonscan.com/tx/{trade['tx_hash']}")
                print()

    # Position contradiction analysis
    if positions:
        print(f"{'─' * 60}")
        print(f"  POSITION CONTRADICTION CHECK\n")
        print(f"  Open positions: {len(positions)}")
        print()

        if not results:
            print("  No whale activity to cross-reference against open positions.")
        else:
            print("  Cross-referencing whale activity against positions...")
            print("  (Manual review required — market-to-trade matching is approximate)")
            print()
            for pos in positions:
                trade_id = pos.get("trade_id", pos.get("id", "?"))
                market = pos.get("market", pos.get("question", "?"))
                direction = pos.get("direction", pos.get("side", "?"))
                print(f"  {trade_id}: {direction} on \"{market[:60]}\"")
            print()
            print("  ACTION: Check whale trades above against these positions manually.")
            print("  Whale profile pages for quick check:")
            for r in results:
                print(f"    {r['alias']}: https://polymarket.com/profile/{r['wallet']}")

    print()
    print(f"{'─' * 60}")
    print("  EXTERNAL MONITORING (check manually):\n")
    print("  Polywhaler:  https://polywhaler.com        ($10K+ trades, real-time)")
    print("  HashDive:    https://hashdive.com           (Smart Scores, whale volume)")
    print("  PolyTrack:   https://polytrackhq.app        (Cluster detection)")
    print("  PolyMonit:   https://polymonit.com          (Telegram alerts)")
    print("  Arkham:      https://intel.arkm.com/explorer/entity/polymarket")
    print()
    print(f"{'=' * 60}\n")


# --- Main ---


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Monitor Polymarket whale wallets")
    parser.add_argument("--wallet", help="Scan a specific wallet address")
    parser.add_argument("--market", help="Filter by market keyword")
    parser.add_argument("--hours", type=int, default=LOOKBACK_HOURS, help="Lookback window in hours")
    parser.add_argument("--min-size", type=float, default=MIN_ALERT_SIZE_USD, help="Minimum trade size (USD)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be scanned without API calls")
    args = parser.parse_args()

    global LOOKBACK_HOURS, MIN_ALERT_SIZE_USD
    LOOKBACK_HOURS = args.hours
    MIN_ALERT_SIZE_USD = args.min_size

    # Load registry
    registry = load_registry()
    print(f"Loaded {len(registry)} wallets with valid addresses from registry.")

    if args.wallet:
        # Override: scan a specific wallet
        registry = [{"wallet": args.wallet, "alias": "Manual", "domain_focus": ["?"], "follow_confidence": 0}]

    if args.dry_run:
        print("\n[DRY RUN] Would scan these wallets:")
        for w in registry:
            print(f"  {w['wallet'][:12]}... ({w['alias']})")
        sys.exit(0)

    # Calculate lookback timestamp
    start_time = int((datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)).timestamp())

    # Scan each wallet
    results = []
    for i, whale in enumerate(registry):
        addr = whale["wallet"]
        alias = whale["alias"]
        print(f"Scanning [{i + 1}/{len(registry)}] {alias} ({addr[:12]}...)... ", end="", flush=True)

        # Get USDC.e transfers (more reliable for trade size estimation)
        transfers = get_erc20_transfers(addr, start_time)
        time.sleep(POLYGONSCAN_DELAY)

        # Estimate trade sizes
        trades = estimate_trade_size(transfers, addr)

        if trades:
            print(f"FOUND {len(trades)} trades >${MIN_ALERT_SIZE_USD:,.0f}")
            results.append({
                "wallet": addr,
                "alias": alias,
                "domain_focus": whale.get("domain_focus", []),
                "follow_confidence": whale.get("follow_confidence", 0),
                "trades": trades,
            })
        else:
            print("quiet")

        # Also get raw txns for Polymarket contract interactions
        txns = get_wallet_txns(addr, start_time)
        time.sleep(POLYGONSCAN_DELAY)

        if txns:
            print(f"  + {len(txns)} Polymarket contract interactions")

    # Load our positions for contradiction analysis
    positions = load_open_positions()

    # Print dashboard
    print_dashboard(results, positions)

    # Save results to file
    output_path = DATA_DIR / f"whale-scan-{datetime.utcnow().strftime('%Y-%m-%d')}.json"
    output_data = {
        "scan_time": datetime.utcnow().isoformat() + "Z",
        "lookback_hours": LOOKBACK_HOURS,
        "min_alert_size": MIN_ALERT_SIZE_USD,
        "wallets_scanned": len(registry),
        "wallets_with_activity": len(results),
        "results": results,
    }
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
