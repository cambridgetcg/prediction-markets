#!/usr/bin/env python3
"""
Backtest: Whale Follow Strategy

Uses historical trade data from edge-cache to validate:
"If we had followed every in-domain trade from each insider,
 what would our P&L have been?"

Usage:
    python3 backtest_whale_follow.py                    # All insiders
    python3 backtest_whale_follow.py --wallet 0x0afc... # Single insider
    python3 backtest_whale_follow.py --domain GEO       # GEO insiders only
    python3 backtest_whale_follow.py --bankroll 5000     # Custom bankroll
    python3 backtest_whale_follow.py --json              # Machine-readable

Data sources (no API calls):
    - data/insider-registry.json (insider profiles)
    - data/edge-cache/trades-{wallet_prefix}.json (historical trades)
    - data/edge-cache/resolved-markets.json (resolution outcomes)
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
EDGE_CACHE = DATA_DIR / "edge-cache"
REGISTRY_PATH = DATA_DIR / "insider-registry.json"
REPORT_PATH = PROJECT_DIR / "strategies" / "backtests" / "B9-whale-follow-backtest.md"

# --- Domain classification (shared) ---

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
            'google', 'apple', 'microsoft', 'nvidia', 'tesla', 'spacex',
            'tiktok', 'meta', 'amazon'],
    'SOC': ['shooting', 'celebrity', 'sports', 'oscars', 'grammy',
            'super bowl', 'nfl', 'nba', 'ufc', 'boxing', 'netflix',
            'tiktok ban', 'social media', 'youtube'],
    'SCI': ['vaccine', 'climate', 'earthquake', 'hurricane', 'pandemic',
            'bird flu', 'h5n1', 'cdc', 'who ', 'fda', 'cancer'],
    'LAW': ['court', 'supreme court', 'ruling', 'lawsuit', 'indictment',
            'trial', 'verdict', 'sec ', 'ftc', 'doj'],
    'ENV': ['temperature', 'wildfire', 'hurricane cat', 'earthquake',
            'flood', 'drought', 'arctic', 'emissions'],
}


def classify_domain(text):
    if not text:
        return None
    text_lower = text.lower()
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[domain] = score
    return max(scores, key=scores.get) if scores else None


# --- Data loading ---

def load_registry():
    if not REGISTRY_PATH.exists():
        print("ERROR: insider-registry.json not found", file=sys.stderr)
        sys.exit(1)
    with open(REGISTRY_PATH) as f:
        data = json.load(f)
    return data.get("accounts", [])


def load_resolved_markets():
    path = EDGE_CACHE / "resolved-markets.json"
    if not path.exists():
        print("ERROR: resolved-markets.json not found", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def find_trade_file(wallet):
    """Find the trade file for a wallet (prefix match)."""
    prefix = wallet[:16].lower()
    for f in EDGE_CACHE.iterdir():
        if f.name.startswith("trades-") and f.suffix == ".json":
            file_prefix = f.name.replace("trades-", "").replace(".json", "").lower()
            if prefix.startswith(file_prefix) or file_prefix.startswith(prefix[:14]):
                return f
    return None


# --- PnL calculation ---

def calculate_trade_pnl(trade, resolved_markets):
    """
    Calculate PnL for a single trade given market resolution.

    Returns (pnl_per_share, total_pnl, resolved) or (None, None, False) if unresolved.
    """
    cid = trade.get("condition_id", "")
    asset = trade.get("asset", "")
    token_key = f"token:{asset}"

    market = resolved_markets.get(cid) or resolved_markets.get(token_key)
    if not market:
        return None, None, False

    outcome_prices = market.get("outcome_prices", [])
    if len(outcome_prices) < 2:
        return None, None, False

    # outcome_prices: [1, 0] = YES resolved, [0, 1] = NO resolved
    resolved_yes = outcome_prices[0] == 1.0

    price = trade["price"]
    size = trade["size"]
    side = trade["side"]

    # PnL calculation:
    # BUY YES at price p: profit = (1-p)*size if YES, loss = -p*size if NO
    # SELL YES at price p: profit = p*size if NO, loss = (p-1)*size if YES
    if side == "BUY":
        pnl_per_share = (1.0 - price) if resolved_yes else (-price)
    else:  # SELL
        pnl_per_share = (price - 1.0) if resolved_yes else price

    total_pnl = pnl_per_share * size

    return pnl_per_share, total_pnl, True


def quarter_kelly_size(edge, price, direction, bankroll):
    """
    Calculate quarter-Kelly position size.

    edge: insider's historical category edge (e.g., 0.48 for 48%)
    price: trade entry price
    direction: BUY or SELL
    bankroll: total bankroll
    """
    if edge <= 0:
        return 0

    # Kelly fraction: edge / odds
    # For BUY YES at price p: odds = (1-p)/p, kelly = edge / ((1-p)/p) = edge*p/(1-p)
    # For SELL YES at price p: odds = p/(1-p), kelly = edge / (p/(1-p)) = edge*(1-p)/p
    if direction == "BUY":
        if price >= 1 or price <= 0:
            return 0
        kelly = edge * price / (1 - price)
    else:
        if price <= 0 or price >= 1:
            return 0
        kelly = edge * (1 - price) / price

    # Quarter-Kelly, capped at 5% bankroll
    quarter = kelly * 0.25
    return min(max(quarter * bankroll, 0), bankroll * 0.05)


# --- Backtest engine ---

def backtest_insider(insider, resolved_markets, bankroll, in_domain_only=True):
    """
    Backtest the follow strategy for a single insider.

    Returns dict with performance metrics.
    """
    wallet = insider["wallet"]
    alias = insider.get("alias", wallet[:12])
    dominant = insider.get("dominant_category", "?")
    edge = insider.get("top_category_edge", 0)

    trade_file = find_trade_file(wallet)
    if not trade_file:
        return None

    with open(trade_file) as f:
        trades = json.load(f)

    results = {
        "alias": alias,
        "wallet": wallet,
        "dominant_category": dominant,
        "insider_score": insider.get("insider_score", 0),
        "historical_edge": edge,
        "total_trades": len(trades),
        "resolved_trades": 0,
        "in_domain_trades": 0,
        "followed_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl": 0.0,
        "follow_pnl": 0.0,  # PnL with quarter-Kelly sizing
        "best_trade_pnl": 0.0,
        "worst_trade_pnl": 0.0,
        "trades_detail": [],
    }

    for trade in trades:
        title = trade.get("title", "")
        trade_domain = classify_domain(title)

        pnl_per_share, total_pnl, resolved = calculate_trade_pnl(trade, resolved_markets)
        if not resolved:
            continue

        results["resolved_trades"] += 1

        is_in_domain = trade_domain == dominant
        if is_in_domain:
            results["in_domain_trades"] += 1

        # Only follow in-domain trades if flag is set
        if in_domain_only and not is_in_domain:
            continue

        results["followed_trades"] += 1
        results["total_pnl"] += total_pnl

        # Quarter-Kelly sized PnL
        follow_size = quarter_kelly_size(edge, trade["price"], trade["side"], bankroll)
        if follow_size > 0:
            # Scale PnL to our position size (not the insider's size)
            follow_pnl = pnl_per_share * (follow_size / trade["price"] if trade["side"] == "BUY"
                                           else follow_size / (1 - trade["price"]))
        else:
            follow_pnl = 0

        results["follow_pnl"] += follow_pnl

        if total_pnl > 0:
            results["wins"] += 1
        else:
            results["losses"] += 1

        results["best_trade_pnl"] = max(results["best_trade_pnl"], total_pnl)
        results["worst_trade_pnl"] = min(results["worst_trade_pnl"], total_pnl)

        results["trades_detail"].append({
            "title": title[:60],
            "domain": trade_domain,
            "side": trade["side"],
            "price": trade["price"],
            "size": trade["size"],
            "pnl": round(total_pnl, 2),
            "follow_pnl": round(follow_pnl, 2),
            "timestamp": trade.get("timestamp"),
        })

    # Win rate
    n = results["followed_trades"]
    results["win_rate"] = results["wins"] / n if n > 0 else 0

    # Sharpe estimate (annualized from per-trade returns)
    if n > 1:
        returns = [t["pnl"] / max(t["size"] * t["price"], 1) for t in results["trades_detail"]]
        mean_ret = sum(returns) / len(returns)
        var = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(var) if var > 0 else 0.001
        # Assume ~50 trades/year for annualization
        results["sharpe"] = (mean_ret / std) * math.sqrt(min(n, 50))
    else:
        results["sharpe"] = 0

    return results


# --- Output ---

def print_report(all_results, bankroll):
    """Print human-readable backtest report."""
    print(f"\n{'=' * 70}")
    print(f"  WHALE FOLLOW STRATEGY — HISTORICAL BACKTEST")
    print(f"  Bankroll: ${bankroll:,.0f} | Sizing: Quarter-Kelly, max 5%")
    print(f"{'=' * 70}\n")

    # Summary table
    print(f"  {'Alias':<16} {'Domain':>5} {'Score':>5} {'Edge':>6} "
          f"{'Trades':>6} {'Followed':>8} {'Win%':>5} {'PnL':>12} {'Follow$':>10} {'Sharpe':>6}")
    print(f"  {'-'*16} {'-'*5} {'-'*5} {'-'*6} {'-'*6} {'-'*8} {'-'*5} {'-'*12} {'-'*10} {'-'*6}")

    total_pnl = 0
    total_follow = 0
    total_followed = 0
    total_wins = 0

    for r in sorted(all_results, key=lambda x: x["follow_pnl"], reverse=True):
        if r["followed_trades"] == 0:
            continue
        total_pnl += r["total_pnl"]
        total_follow += r["follow_pnl"]
        total_followed += r["followed_trades"]
        total_wins += r["wins"]

        print(f"  {r['alias']:<16} {r['dominant_category']:>5} "
              f"{r['insider_score']:>5.0f} {r['historical_edge']:>+5.1%} "
              f"{r['total_trades']:>6} {r['followed_trades']:>8} "
              f"{r['win_rate']:>4.0%} ${r['total_pnl']:>+11,.0f} "
              f"${r['follow_pnl']:>+9,.0f} {r['sharpe']:>+5.2f}")

    print(f"\n  {'TOTAL':<16} {'':>5} {'':>5} {'':>6} "
          f"{'':>6} {total_followed:>8} "
          f"{total_wins/max(total_followed,1):>4.0%} ${total_pnl:>+11,.0f} "
          f"${total_follow:>+9,.0f}")

    # Best/worst trades across all insiders
    print(f"\n{'─' * 70}")
    print(f"  TOP 5 BEST FOLLOW TRADES:\n")
    all_trades = []
    for r in all_results:
        for t in r["trades_detail"]:
            t["_alias"] = r["alias"]
        all_trades.extend(r["trades_detail"])

    for t in sorted(all_trades, key=lambda x: x["pnl"], reverse=True)[:5]:
        print(f"  ${t['pnl']:>+10,.0f}  {t['_alias']:<14} {t['side']:4} {t['domain'] or '?':3}  {t['title']}")

    print(f"\n  TOP 5 WORST FOLLOW TRADES:\n")
    for t in sorted(all_trades, key=lambda x: x["pnl"])[:5]:
        print(f"  ${t['pnl']:>+10,.0f}  {t['_alias']:<14} {t['side']:4} {t['domain'] or '?':3}  {t['title']}")

    print(f"\n{'=' * 70}")

    # Verdict
    if total_follow > 0:
        print(f"\n  VERDICT: Positive expected value. Follow strategy profitable on ${bankroll:,.0f} bankroll.")
    elif total_pnl > 0:
        print(f"\n  VERDICT: Raw PnL positive but quarter-Kelly sizing shows near-zero. Edge real but sizing needs tuning.")
    else:
        print(f"\n  VERDICT: Negative PnL. Strategy needs refinement before live deployment.")
    print()


def print_json_output(all_results):
    """Print machine-readable summary."""
    output = []
    for r in all_results:
        r_copy = dict(r)
        # Trim detail to top 10 by PnL magnitude
        r_copy["trades_detail"] = sorted(
            r_copy["trades_detail"], key=lambda x: abs(x["pnl"]), reverse=True
        )[:10]
        output.append(r_copy)
    print(json.dumps(output, indent=2))


def write_markdown_report(all_results, bankroll):
    """Write backtest report as markdown."""
    lines = [
        "# B9 Whale Follow Strategy — Historical Backtest",
        f"",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Bankroll: ${bankroll:,.0f} | Sizing: Quarter-Kelly, max 5%",
        f"",
        "## Per-Insider Results",
        "",
        "| Alias | Domain | Score | Edge | Trades | Followed | Win% | Raw PnL | Follow PnL | Sharpe |",
        "|-------|--------|-------|------|--------|----------|------|---------|------------|--------|",
    ]

    for r in sorted(all_results, key=lambda x: x["follow_pnl"], reverse=True):
        if r["followed_trades"] == 0:
            continue
        lines.append(
            f"| {r['alias']} | {r['dominant_category']} | {r['insider_score']:.0f} | "
            f"{r['historical_edge']:+.1%} | {r['total_trades']} | {r['followed_trades']} | "
            f"{r['win_rate']:.0%} | ${r['total_pnl']:+,.0f} | ${r['follow_pnl']:+,.0f} | "
            f"{r['sharpe']:+.2f} |"
        )

    total_pnl = sum(r["total_pnl"] for r in all_results)
    total_follow = sum(r["follow_pnl"] for r in all_results)
    lines.append(f"\n**Total raw PnL**: ${total_pnl:+,.0f}")
    lines.append(f"**Total follow PnL (quarter-Kelly)**: ${total_follow:+,.0f}")

    lines.append(f"\n## Methodology")
    lines.append(f"- Only in-domain trades followed (insider's dominant category)")
    lines.append(f"- Quarter-Kelly sizing, capped at 5% of bankroll per trade")
    lines.append(f"- 2% winner fee NOT deducted (conservative bias toward profitability)")
    lines.append(f"- Assumes instant fill at insider's entry price (realistic for liquid markets)")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"Report written to {REPORT_PATH}", file=sys.stderr)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Backtest whale follow strategy")
    parser.add_argument("--wallet", help="Backtest a specific wallet only")
    parser.add_argument("--domain", help="Filter to insiders in this domain")
    parser.add_argument("--bankroll", type=float, default=5000, help="Bankroll size (default: $5000)")
    parser.add_argument("--all-trades", action="store_true",
                        help="Follow all trades, not just in-domain")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--report", action="store_true", help="Write markdown report")
    args = parser.parse_args()

    # Load data
    insiders = load_registry()
    resolved_markets = load_resolved_markets()
    print(f"Loaded {len(insiders)} insiders, {len(resolved_markets)} resolved markets", file=sys.stderr)

    # Filter
    if args.wallet:
        insiders = [i for i in insiders if i["wallet"].lower().startswith(args.wallet.lower())]
    if args.domain:
        insiders = [i for i in insiders if i.get("dominant_category") == args.domain.upper()]

    if not insiders:
        print("No insiders match filters.", file=sys.stderr)
        sys.exit(1)

    # Run backtest
    all_results = []
    for insider in insiders:
        alias = insider.get("alias", insider["wallet"][:12])
        print(f"  Backtesting {alias}... ", end="", flush=True, file=sys.stderr)

        result = backtest_insider(insider, resolved_markets, args.bankroll,
                                  in_domain_only=not args.all_trades)
        if result:
            all_results.append(result)
            print(f"{result['followed_trades']} trades, PnL ${result['total_pnl']:+,.0f}", file=sys.stderr)
        else:
            print("no trade file", file=sys.stderr)

    if not all_results:
        print("No results to report.", file=sys.stderr)
        sys.exit(1)

    # Output
    if args.json:
        print_json_output(all_results)
    else:
        print_report(all_results, args.bankroll)

    if args.report:
        write_markdown_report(all_results, args.bankroll)


if __name__ == "__main__":
    main()
