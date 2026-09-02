#!/usr/bin/env python3
"""Generate calibration reports from strictly joined forecast resolutions."""

import json
import math
import os
from collections import defaultdict
from pathlib import Path


PRED_FILE = "calibration/predictions.jsonl"
RES_FILE = "calibration/resolutions.jsonl"


def load_jsonl(path):
    entries = []
    path = Path(path)
    if path.exists():
        with path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    return entries


def as_probability(value):
    """Return a finite probability or None; booleans are not probabilities."""
    if isinstance(value, bool):
        return None
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        return None
    return probability


def parse_binary_outcome(value):
    """Return 1.0/0.0 only for explicit binary outcomes; otherwise None."""
    if value is True or value == 1:
        return 1.0
    if value is False or value == 0:
        return 0.0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"yes", "true", "1"}:
            return 1.0
        if normalized in {"no", "false", "0"}:
            return 0.0
    return None


def resolution_forecast_id(resolution):
    """Read either supported ID field, rejecting conflicting identifiers."""
    pred_id = resolution.get("pred_id")
    legacy_id = resolution.get("prediction_id")
    if pred_id and legacy_id and pred_id != legacy_id:
        return None
    forecast_id = pred_id or legacy_id
    return forecast_id if isinstance(forecast_id, str) and forecast_id else None


def join_forecasts(predictions, resolutions):
    """Build strict one-forecast-to-one-resolution joins.

    Retrospective or otherwise unlinked resolution rows remain in ``orphans``.
    Duplicate forecast IDs and duplicate resolutions are excluded rather than
    silently selecting one record.
    """
    prediction_groups = defaultdict(list)
    invalid_predictions = []
    for prediction in predictions:
        forecast_id = prediction.get("id")
        if not isinstance(forecast_id, str) or not forecast_id:
            invalid_predictions.append(prediction)
            continue
        prediction_groups[forecast_id].append(prediction)

    unique_predictions = {}
    for forecast_id, rows in prediction_groups.items():
        if len(rows) == 1:
            unique_predictions[forecast_id] = rows[0]
        else:
            invalid_predictions.extend(rows)

    resolution_groups = defaultdict(list)
    orphans = []
    for resolution in resolutions:
        forecast_id = resolution_forecast_id(resolution)
        if forecast_id not in unique_predictions:
            orphans.append(resolution)
            continue
        resolution_groups[forecast_id].append(resolution)

    joined = []
    duplicate_resolutions = []
    for forecast_id, prediction in unique_predictions.items():
        rows = resolution_groups.get(forecast_id, [])
        if len(rows) == 1:
            joined.append((prediction, rows[0]))
        elif len(rows) > 1:
            duplicate_resolutions.extend(rows)

    return {
        "joined": joined,
        "orphans": orphans,
        "duplicate_resolutions": duplicate_resolutions,
        "invalid_predictions": invalid_predictions,
    }


def build_calibration_data(predictions, resolutions):
    """Join records and calculate scores from committed forecast values."""
    links = join_forecasts(predictions, resolutions)
    evaluations = []

    for prediction, resolution in links["joined"]:
        outcome = parse_binary_outcome(resolution.get("outcome"))
        estimate = as_probability(prediction.get("my_estimate"))
        market_price = as_probability(prediction.get("market_price"))

        my_brier = None
        market_brier = None
        beat_market = None
        if outcome is not None and estimate is not None:
            my_brier = (estimate - outcome) ** 2
        if outcome is not None and market_price is not None:
            market_brier = (market_price - outcome) ** 2
        if my_brier is not None and market_brier is not None:
            beat_market = my_brier < market_brier

        evaluations.append({
            "prediction": prediction,
            "resolution": resolution,
            "domain": prediction.get("domain") or "UNKNOWN",
            "outcome": outcome,
            "estimate": estimate,
            "market_price": market_price,
            "my_brier": my_brier,
            "market_brier": market_brier,
            "beat_market": beat_market,
        })

    return {**links, "evaluations": evaluations}


def _average(values):
    return sum(values) / len(values) if values else None


def _format_score(value):
    return f"{value:.4f}" if value is not None else "N/A"


def report(pred_file=PRED_FILE, res_file=RES_FILE, write_domain_files=True):
    predictions = load_jsonl(pred_file)
    resolutions = load_jsonl(res_file)
    data = build_calibration_data(predictions, resolutions)

    joined_count = len(data["joined"])
    pending_count = len(predictions) - joined_count

    print("=== Calibration Report ===\n")
    print(f"Total predictions: {len(predictions)}")
    print(f"Resolved (strict ID join): {joined_count}")
    print(f"Pending/unjoined predictions: {pending_count}")
    print(f"Retrospective/orphan resolutions: {len(data['orphans'])}")
    print(f"Duplicate resolution rows excluded: {len(data['duplicate_resolutions'])}")
    print(f"Invalid/duplicate prediction rows excluded: {len(data['invalid_predictions'])}\n")

    if not data["joined"]:
        print("No strictly joined resolutions yet.")
        return data

    evaluations = data["evaluations"]
    my_scores = [e["my_brier"] for e in evaluations if e["my_brier"] is not None]
    market_scores = [e["market_brier"] for e in evaluations if e["market_brier"] is not None]
    comparisons = [e for e in evaluations if e["beat_market"] is not None]
    beat_count = sum(1 for e in comparisons if e["beat_market"])

    print(f"My avg Brier score:     {_format_score(_average(my_scores))} (n={len(my_scores)})")
    print(f"Market avg Brier score: {_format_score(_average(market_scores))} (n={len(market_scores)})")
    if comparisons:
        print(f"Beat market: {beat_count}/{len(comparisons)} ({beat_count/len(comparisons):.0%})\n")
    else:
        print("Beat market: N/A (no comparable forecast/market pairs)\n")

    by_domain = defaultdict(list)
    for evaluation in evaluations:
        by_domain[evaluation["domain"]].append(evaluation)

    print("=== By Domain ===\n")
    for domain in sorted(by_domain):
        entries = by_domain[domain]
        domain_scores = [e["my_brier"] for e in entries if e["my_brier"] is not None]
        domain_comparisons = [e for e in entries if e["beat_market"] is not None]
        domain_beats = sum(1 for e in domain_comparisons if e["beat_market"])
        print(
            f"{domain}: {len(entries)} joined | {len(domain_scores)} scored | "
            f"Brier: {_format_score(_average(domain_scores))} | "
            f"Beat market: {domain_beats}/{len(domain_comparisons)}"
        )

        if write_domain_files:
            latest = entries[-1]["resolution"]
            domain_data = {
                "domain": domain,
                "predictions": sum(1 for p in predictions if p.get("domain") == domain),
                "resolved": len(entries),
                "scored": len(domain_scores),
                "brier_score": round(_average(domain_scores), 4) if domain_scores else None,
                "beat_market_rate": (
                    round(domain_beats / len(domain_comparisons), 4)
                    if domain_comparisons else None
                ),
                "last_updated": latest.get("ts", latest.get("ts_resolved", "unknown")),
            }
            domain_file = Path("calibration/by-domain") / f"{domain}.json"
            domain_file.write_text(json.dumps(domain_data, indent=2))

    scored_evaluations = [
        e for e in evaluations
        if e["estimate"] is not None and e["outcome"] is not None
    ]
    if len(scored_evaluations) >= 10:
        print("\n=== Calibration Curve ===\n")
        buckets = defaultdict(lambda: {"count": 0, "yes": 0})
        for evaluation in scored_evaluations:
            bucket = round(evaluation["estimate"] * 10) / 10
            buckets[bucket]["count"] += 1
            buckets[bucket]["yes"] += evaluation["outcome"]

        for bucket in sorted(buckets):
            bucket_data = buckets[bucket]
            actual = bucket_data["yes"] / bucket_data["count"]
            bar = "█" * int(actual * 20)
            print(
                f"  {bucket:>5.0%} estimated → {actual:>5.0%} actual "
                f"(n={bucket_data['count']}) {bar}"
            )

    return data


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")
    report()
