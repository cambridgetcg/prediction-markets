#!/usr/bin/env python3
"""
synthesise.py — The Synthesis Engine.

Takes a question about a real-world event and produces a structured
probability estimate with confidence interval, key drivers, and what
would change it. Uses the domain knowledge base + LLM reasoning.

Usage:
    python3 engine/synthesise.py "Will Iran reach a nuclear deal by June 2026?"
    python3 engine/synthesise.py --domain GEO --interactive
    python3 engine/synthesise.py --load pred-0005  # re-analyse existing prediction
"""

import json
import sys
import os
import argparse
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DOMAINS_DIR = BASE_DIR / "domains"
CALIBRATION_DIR = BASE_DIR / "calibration"
DATA_DIR = BASE_DIR / "data"
ENGINE_DIR = BASE_DIR / "engine"

# ── LLM caller ────────────────────────────────────────────────────────────────

def call_llm(prompt: str, system: str = "", model: str = "claude-sonnet-4-6") -> str:
    """Call Anthropic API for synthesis."""
    import urllib.request
    import urllib.error

    # Load API key from credentials.py or env
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

    if not api_key:
        raise RuntimeError("No ANTHROPIC_API_KEY found")

    payload = json.dumps({
        "model": model,
        "max_tokens": 2000,
        "system": system or "You are a rigorous probabilistic forecaster. You reason carefully from evidence to probability estimates. You always quantify uncertainty.",
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["content"][0]["text"].strip()

# ── Domain context loader ─────────────────────────────────────────────────────

def load_domain_context(domain: str) -> str:
    """Load context.md for a domain."""
    ctx_file = DOMAINS_DIR / domain / "context.md"
    if ctx_file.exists():
        return ctx_file.read_text()[:4000]  # cap to avoid context overload
    return f"No context file found for domain {domain}."

def detect_domain(question: str) -> str:
    """Detect which domain a question belongs to."""
    q = question.lower()
    if any(w in q for w in ["war", "strike", "iran", "ukraine", "russia", "nato", "ceasefire", "attack", "invasion", "military", "conflict"]):
        return "GEO"
    if any(w in q for w in ["fed", "rate", "inflation", "gdp", "recession", "unemployment", "tariff"]):
        return "ECO"
    if any(w in q for w in ["bitcoin", "btc", "crypto", "ethereum", "token", "defi", "blockchain"]):
        return "CRY"
    if any(w in q for w in ["president", "election", "congress", "senate", "trump", "democrat", "republican", "vote"]):
        return "POL"
    if any(w in q for w in ["stock", "equit", "s&p", "nasdaq", "earning", "market cap", "ipo"]):
        return "FIN"
    if any(w in q for w in ["ai", "openai", "anthropic", "google", "claude", "gpt", "model", "tech"]):
        return "TEC"
    if any(w in q for w in ["court", "scotus", "ruling", "lawsuit", "regulation", "law", "legal"]):
        return "LAW"
    return "GEO"  # default to geopolitics for major world events

# ── Synthesis prompt ──────────────────────────────────────────────────────────

SYNTHESIS_SYSTEM = """You are a professional probabilistic forecaster combining Superforecaster methodology with domain expertise.

Your task: given a question about a real-world event, produce a structured probability estimate.

You MUST output your response as valid JSON matching this schema:
{
  "question": "exact question",
  "domain": "GEO|POL|ECO|FIN|CRY|TEC|SCI|SOC|LAW|ENV",
  "my_estimate": 0.XX,
  "confidence_interval": [0.XX, 0.XX],
  "confidence_level": "low|medium|high",
  "base_rate": 0.XX,
  "base_rate_source": "description of base rate",
  "key_drivers": [
    {"factor": "name", "direction": "up|down", "weight": "high|medium|low", "notes": "..."},
    ...
  ],
  "what_would_change_this": [
    {"trigger": "specific event/signal", "new_estimate": 0.XX, "direction": "higher|lower"},
    ...
  ],
  "resolution_criteria": "exactly what needs to happen for YES",
  "resolution_date": "YYYY-MM-DD or null",
  "market_reference": "Polymarket/Manifold question if known, else null",
  "investment_implications": {
    "prediction_market_edge": "description or null if no edge",
    "equity_implications": "description or null",
    "commodity_implications": "description or null",
    "crypto_implications": "description or null",
    "hedge_suggestion": "description or null"
  },
  "reasoning_summary": "2-3 sentence summary of the core reasoning",
  "uncertainty_sources": ["list of main uncertainty drivers"],
  "last_updated": "ISO timestamp"
}

Key principles:
- Start from base rates, then adjust for specific factors
- Be calibrated: 70% means YES roughly 7 times in 10
- Show your work: key_drivers explains the estimate
- Be specific about what would change your mind
- Quantify the investment edge only if it's real"""

def synthesise(question: str, domain: str = None, market_price: float = None,
               context_override: str = None) -> dict:
    """Synthesise a probability estimate for a question."""

    if not domain:
        domain = detect_domain(question)

    domain_ctx = context_override or load_domain_context(domain)

    market_ctx = f"\nCurrent market price (if available): {market_price:.1%}" if market_price else ""

    prompt = f"""Question to forecast: {question}
Domain: {domain}
{market_ctx}

Domain knowledge context:
---
{domain_ctx}
---

Using the domain knowledge above and your own reasoning:
1. Identify the relevant base rate for this type of event
2. Adjust up/down based on specific factors
3. Produce a calibrated probability estimate with confidence interval
4. Identify the 3-5 most important factors driving your estimate
5. Name specific triggers that would change your estimate significantly
6. Assess any investment implications (is there an edge vs market price?)

Output ONLY the JSON schema described in your system prompt. No other text."""

    response = call_llm(prompt, system=SYNTHESIS_SYSTEM)

    # Parse JSON from response
    try:
        # Handle markdown code blocks
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
        result = json.loads(response)
        result["last_updated"] = datetime.now(timezone.utc).isoformat()
        return result
    except json.JSONDecodeError as e:
        # Return raw if JSON parse fails
        return {
            "question": question,
            "domain": domain,
            "raw_response": response,
            "parse_error": str(e),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }

# ── Save and display ──────────────────────────────────────────────────────────

def display_synthesis(result: dict) -> None:
    """Print a synthesis result in human-readable form."""
    if "parse_error" in result:
        print(f"\n⚠️  JSON parse error. Raw response:\n{result.get('raw_response','')}")
        return

    q = result.get("question", "?")
    est = result.get("my_estimate", 0)
    ci = result.get("confidence_interval", [0, 0])
    domain = result.get("domain", "?")
    conf = result.get("confidence_level", "?")

    print(f"\n{'═'*60}")
    print(f"PREDICTION SYNTHESIS — {domain}")
    print(f"{'═'*60}\n")
    print(f"  Question: {q}")
    print(f"  Estimate: {est:.0%}  [{ci[0]:.0%}–{ci[1]:.0%}]  ({conf} confidence)")
    print(f"  Base rate: {result.get('base_rate',0):.0%} — {result.get('base_rate_source','')}")
    print()

    drivers = result.get("key_drivers", [])
    if drivers:
        print("  Key drivers:")
        for d in drivers:
            arrow = "↑" if d.get("direction") == "up" else "↓"
            print(f"    {arrow} [{d.get('weight','?'):6}] {d.get('factor','?')}: {d.get('notes','')}")
    print()

    changes = result.get("what_would_change_this", [])
    if changes:
        print("  What would change this:")
        for c in changes:
            print(f"    → {c.get('trigger','?')} → {c.get('new_estimate',0):.0%} ({c.get('direction','')})")
    print()

    impl = result.get("investment_implications", {})
    edge = impl.get("prediction_market_edge")
    if edge:
        print(f"  📈 Market edge: {edge}")
    for asset, desc in impl.items():
        if desc and asset not in ("prediction_market_edge",) and "null" not in str(desc).lower():
            print(f"  💰 {asset.replace('_',' ').title()}: {desc}")
    print()
    print(f"  Reasoning: {result.get('reasoning_summary','')}")
    print(f"{'─'*60}")


def save_synthesis(result: dict, auto_log: bool = True) -> str:
    """Save synthesis to data/syntheses/ and optionally log to predictions.jsonl."""
    synth_dir = DATA_DIR / "syntheses"
    synth_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = synth_dir / f"synthesis-{ts}.json"
    filename.write_text(json.dumps(result, indent=2))

    if auto_log and "parse_error" not in result and result.get("my_estimate"):
        # Also log to calibration/predictions.jsonl
        pred_file = CALIBRATION_DIR / "predictions.jsonl"
        pred_file.parent.mkdir(parents=True, exist_ok=True)

        # Count existing predictions for ID
        existing = 0
        if pred_file.exists():
            existing = sum(1 for _ in pred_file.read_text().splitlines() if _.strip())

        pred = {
            "id": f"pred-{existing+1:04d}",
            "ts": result["last_updated"],
            "domain": result.get("domain"),
            "question": result.get("question"),
            "market_price": None,  # fill in manually
            "my_estimate": result.get("my_estimate"),
            "confidence_interval": result.get("confidence_interval"),
            "resolution_date": result.get("resolution_date"),
            "resolved": None,
            "outcome": None,
            "brier_score": None,
            "beat_market": None,
            "reasoning": result.get("reasoning_summary", ""),
            "synthesis_file": str(filename),
        }
        with open(pred_file, "a") as f:
            f.write(json.dumps(pred) + "\n")
        print(f"\n  ✅ Logged as {pred['id']} → calibration/predictions.jsonl")

    print(f"  💾 Saved → {filename.name}")
    return str(filename)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Future Prediction Engine — Synthesis")
    parser.add_argument("question", nargs="?", help="Question to forecast")
    parser.add_argument("--domain", "-d", help="Force domain (GEO/POL/ECO/FIN/CRY/TEC)")
    parser.add_argument("--market-price", "-p", type=float, help="Current market price (0-1)")
    parser.add_argument("--no-save", action="store_true", help="Don't save to disk")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if not args.question:
        # Interactive mode
        print("\n🔮 Future Prediction Engine — Synthesis")
        print("Enter a question about a real-world event:\n")
        question = input("> ").strip()
        if not question:
            print("No question provided.")
            sys.exit(1)
    else:
        question = args.question

    market_price = args.market_price
    if market_price is None and not args.question:
        try:
            price_str = input("Market price (0-1, or Enter to skip): ").strip()
            if price_str:
                market_price = float(price_str)
        except (ValueError, EOFError):
            pass

    print(f"\n🔮 Synthesising: {question[:80]}...")
    result = synthesise(question, domain=args.domain, market_price=market_price)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        display_synthesis(result)
        if not args.no_save:
            save_synthesis(result)


if __name__ == "__main__":
    main()
