#!/usr/bin/env python3
"""Log a prediction to calibration/predictions.jsonl"""

import json
import sys
from datetime import datetime

def log_prediction(domain, market, market_id, market_price, my_estimate,
                   confidence, reasoning, key_factors=None, resolution_date=None,
                   research_ref=None):
    """Append a prediction entry."""
    
    # Count existing predictions for ID
    pred_file = "calibration/predictions.jsonl"
    try:
        with open(pred_file) as f:
            count = sum(1 for _ in f)
    except FileNotFoundError:
        count = 0
    
    entry = {
        "id": f"pred-{count+1:04d}",
        "ts": datetime.utcnow().isoformat() + "Z",
        "domain": domain,
        "market": market,
        "market_id": market_id or "",
        "market_price": market_price,
        "my_estimate": my_estimate,
        "confidence": confidence,
        "reasoning": reasoning,
        "key_factors": key_factors or [],
        "research_ref": research_ref or "",
        "resolution_date": resolution_date or "",
        "resolved": False,
        "outcome": None
    }
    
    with open(pred_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
    
    delta = my_estimate - market_price
    direction = "above" if delta > 0 else "below"
    print(f"Logged {entry['id']}: {market}")
    print(f"  Market: {market_price:.0%} | Mine: {my_estimate:.0%} ({abs(delta):.0%} {direction})")
    print(f"  Domain: {domain} | Confidence: {confidence}")
    return entry

def log_resolution(pred_id, outcome, lesson=""):
    """Resolve a prediction."""
    pred_file = "calibration/predictions.jsonl"
    res_file = "calibration/resolutions.jsonl"
    
    # Find the prediction
    predictions = []
    target = None
    with open(pred_file) as f:
        for line in f:
            p = json.loads(line)
            if p["id"] == pred_id:
                target = p
                p["resolved"] = True
                p["outcome"] = outcome
            predictions.append(p)
    
    if not target:
        print(f"Prediction {pred_id} not found")
        return
    
    # Calculate errors
    outcome_val = 1.0 if outcome.lower() in ("yes", "true", "1") else 0.0
    my_error = (target["my_estimate"] - outcome_val) ** 2
    market_error = (target["market_price"] - outcome_val) ** 2
    
    resolution = {
        "pred_id": pred_id,
        "ts": datetime.utcnow().isoformat() + "Z",
        "domain": target["domain"],
        "market": target["market"],
        "outcome": outcome,
        "my_estimate_was": target["my_estimate"],
        "market_price_was": target["market_price"],
        "my_brier": my_error,
        "market_brier": market_error,
        "beat_market": my_error < market_error,
        "lesson": lesson
    }
    
    # Write resolution
    with open(res_file, "a") as f:
        f.write(json.dumps(resolution) + "\n")
    
    # Update predictions file
    with open(pred_file, "w") as f:
        for p in predictions:
            f.write(json.dumps(p) + "\n")
    
    beat = "✓ Beat market" if resolution["beat_market"] else "✗ Market was better"
    print(f"Resolved {pred_id}: {outcome}")
    print(f"  My Brier: {my_error:.4f} | Market Brier: {market_error:.4f} | {beat}")

if __name__ == "__main__":
    print("Usage: import and call log_prediction() or log_resolution()")
    print("Or use from CLI: python3 log-prediction.py <action> <args>")
