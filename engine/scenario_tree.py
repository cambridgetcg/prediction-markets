#!/usr/bin/env python3
"""
scenario_tree.py — Causal chain builder for investment decision-making.

Builds scenario trees: Event A → P(B|A) × P(C|B) → investment impact.
Used to understand downstream consequences of major events across assets.

Usage:
    python3 engine/scenario_tree.py "Iran nuclear deal collapses"
    python3 engine/scenario_tree.py --load synthesis-20260317-123456.json
"""

import json
import sys
import os
import argparse
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

def call_llm(prompt: str) -> str:
    import urllib.request
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        try:
            cred_path = Path.home() / ".openclaw" / "workspace" / "tools" / "credentials.py"
            import importlib.util
            spec = importlib.util.spec_from_file_location("credentials", cred_path)
            creds = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(creds)
            api_key = creds.get_key("anthropic-primary", fallback="")
        except Exception:
            pass
    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 3000,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["content"][0]["text"].strip()

TREE_SYSTEM = """You are a scenario analyst. Given a triggering event, build a causal chain of consequences across:
- Geopolitics (what military/diplomatic events follow?)
- Economics (GDP, inflation, trade impacts?)  
- Financial markets (equities, sectors?)
- Commodities (oil, gold, food?)
- Crypto (risk-on/off, specific coins?)
- Prediction markets (what other markets move?)

Output ONLY valid JSON:
{
  "trigger_event": "string",
  "trigger_probability": 0.XX,
  "timeframe": "days|weeks|months",
  "scenario_branches": [
    {
      "branch_name": "string",
      "probability": 0.XX,
      "description": "string",
      "consequences": {
        "geopolitics": "string",
        "economics": "string",
        "equities": {"direction": "up|down|neutral", "sectors": ["..."], "magnitude": "small|medium|large"},
        "commodities": {"oil": "up|down|neutral", "gold": "up|down|neutral", "notes": "string"},
        "crypto": {"direction": "up|down|neutral", "notes": "string"},
        "prediction_markets": ["list of markets that move significantly"]
      },
      "investment_signals": [
        {"action": "buy|sell|watch|hedge", "instrument": "string", "reasoning": "string", "confidence": "low|medium|high"}
      ]
    }
  ],
  "key_monitoring_signals": ["what to watch to know which branch we're in"],
  "portfolio_hedge": "what position reduces risk across all branches"
}"""

def build_tree(event: str, probability: float = None) -> dict:
    prob_ctx = f" (probability: {probability:.0%})" if probability else ""
    prompt = f"""Triggering event: {event}{prob_ctx}

Build a scenario tree showing 2-3 branches of how this event unfolds across the next 4-8 weeks.
For each branch, show the investment implications across all major asset classes.
Focus on actionable signals — what should an investor actually do?

Output ONLY the JSON schema."""

    response = call_llm(prompt)
    if "```json" in response:
        response = response.split("```json")[1].split("```")[0].strip()
    elif "```" in response:
        response = response.split("```")[1].split("```")[0].strip()
    return json.loads(response)


def display_tree(tree: dict) -> None:
    print(f"\n{'═'*60}")
    print(f"SCENARIO TREE: {tree.get('trigger_event','?')}")
    if tree.get("trigger_probability"):
        print(f"Trigger probability: {tree['trigger_probability']:.0%}")
    print(f"Timeframe: {tree.get('timeframe','?')}")
    print(f"{'═'*60}\n")

    for branch in tree.get("scenario_branches", []):
        print(f"  Branch: {branch['branch_name']} ({branch['probability']:.0%} probability)")
        print(f"  {branch['description']}")
        c = branch.get("consequences", {})
        eq = c.get("equities", {})
        print(f"    Equities: {eq.get('direction','?')} ({eq.get('magnitude','?')}) — {', '.join(eq.get('sectors',[]))}")
        comm = c.get("commodities", {})
        print(f"    Oil: {comm.get('oil','?')}  Gold: {comm.get('gold','?')}")
        print(f"    Crypto: {c.get('crypto',{}).get('direction','?')} — {c.get('crypto',{}).get('notes','')}")
        print()
        for sig in branch.get("investment_signals", []):
            action = sig["action"].upper()
            emoji = {"BUY":"📈","SELL":"📉","HEDGE":"🛡️","WATCH":"👁️"}.get(action,"•")
            print(f"    {emoji} {action}: {sig['instrument']} [{sig['confidence']}] — {sig['reasoning']}")
        print()

    monitors = tree.get("key_monitoring_signals", [])
    if monitors:
        print("  Monitor for:")
        for m in monitors:
            print(f"    • {m}")

    hedge = tree.get("portfolio_hedge")
    if hedge:
        print(f"\n  🛡️  Portfolio hedge: {hedge}")
    print(f"\n{'─'*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scenario Tree Builder")
    parser.add_argument("event", nargs="?", help="Triggering event")
    parser.add_argument("--probability", "-p", type=float, help="Event probability (0-1)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    event = args.event or input("Triggering event: ").strip()
    print(f"\n🌳 Building scenario tree for: {event[:80]}...")
    tree = build_tree(event, args.probability)

    if args.json:
        print(json.dumps(tree, indent=2))
    else:
        display_tree(tree)

    out = DATA_DIR / "scenario-trees" / f"tree-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tree, indent=2))
    print(f"\n  💾 Saved → {out.name}")
