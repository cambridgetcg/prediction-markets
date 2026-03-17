#!/usr/bin/env python3
"""Generate calibration report from predictions and resolutions."""

import json
import os
from collections import defaultdict

PRED_FILE = "calibration/predictions.jsonl"
RES_FILE = "calibration/resolutions.jsonl"

def load_jsonl(path):
    entries = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    return entries

def report():
    predictions = load_jsonl(PRED_FILE)
    resolutions = load_jsonl(RES_FILE)
    
    total = len(predictions)
    resolved = len(resolutions)
    unresolved = total - resolved
    
    print(f"=== Calibration Report ===\n")
    print(f"Total predictions: {total}")
    print(f"Resolved: {resolved}")
    print(f"Pending: {unresolved}\n")
    
    if not resolutions:
        print("No resolutions yet. Make predictions and wait for outcomes!")
        return
    
    # Overall Brier scores (handle both field name conventions)
    def get_brier_mine(r):
        return r.get("brier_mine", r.get("my_brier", 0))
    def get_brier_market(r):
        return r.get("brier_market", r.get("market_brier", 0))

    my_brier = sum(get_brier_mine(r) for r in resolutions) / len(resolutions)
    mkt_brier = sum(get_brier_market(r) for r in resolutions) / len(resolutions)
    beat_count = sum(1 for r in resolutions if r.get("beat_market", False))
    
    print(f"My avg Brier score:     {my_brier:.4f}")
    print(f"Market avg Brier score: {mkt_brier:.4f}")
    print(f"Beat market: {beat_count}/{resolved} ({beat_count/resolved:.0%})\n")
    
    # By domain
    by_domain = defaultdict(list)
    for r in resolutions:
        by_domain[r["domain"]].append(r)
    
    print("=== By Domain ===\n")
    for domain in sorted(by_domain.keys()):
        entries = by_domain[domain]
        n = len(entries)
        d_brier = sum(get_brier_mine(e) for e in entries) / n
        d_beat = sum(1 for e in entries if e.get("beat_market", False))
        print(f"{domain}: {n} resolved | Brier: {d_brier:.4f} | Beat market: {d_beat}/{n}")
        
        # Update domain calibration file
        domain_file = f"calibration/by-domain/{domain}.json"
        domain_data = {
            "domain": domain,
            "predictions": sum(1 for p in predictions if p["domain"] == domain),
            "resolved": n,
            "brier_score": round(d_brier, 4),
            "beat_market_rate": round(d_beat / n, 4) if n > 0 else None,
            "last_updated": resolutions[-1].get("ts", resolutions[-1].get("ts_resolved", "unknown"))
        }
        with open(domain_file, "w") as f:
            json.dump(domain_data, f, indent=2)
    
    # Calibration buckets (when we have enough data)
    if resolved >= 10:
        print("\n=== Calibration Curve ===\n")
        buckets = defaultdict(lambda: {"count": 0, "correct": 0})
        for r in resolutions:
            est = r.get("my_estimate", r.get("my_estimate_was", 0.5))
            bucket = round(est * 10) / 10  # Round to nearest 10%
            outcome_val = 1.0 if r["outcome"].lower() in ("yes", "true", "1") else 0.0
            buckets[bucket]["count"] += 1
            buckets[bucket]["correct"] += outcome_val
        
        for bucket in sorted(buckets.keys()):
            data = buckets[bucket]
            actual = data["correct"] / data["count"] if data["count"] > 0 else 0
            n = data["count"]
            bar = "█" * int(actual * 20)
            print(f"  {bucket:>5.0%} estimated → {actual:>5.0%} actual (n={n}) {bar}")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")
    report()
