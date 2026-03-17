# Weekly Calibration Prompt — News Intelligence Pipeline (Brave API Edition)

**Schedule**: Run every Sunday.
**Input**: 7 days of pipeline output (signals, outcomes, perspective matrices).
**Generate input**: `python3 scripts/calibration_engine.py --report --days 7`

---

You are calibrating a news intelligence pipeline that generates prediction market trading signals. The pipeline uses the Brave News API to ingest articles from multiple country indexes (US, GB, RU, SA, TR, IN), clusters them by event, detects tone divergence across geographic perspectives, and generates signals when perspectives disagree significantly.

## Baseline

- Brier score (ours): **0.230** | Market: **0.349** | Beat rate: **75%** (N=12)
- YES accuracy: 2/5 (40%) | NO accuracy: 7/7 (100%)
- YES discount factor: **0.85** (penalizes YES direction predictions)
- Signal gates: edge >= 5pp, confidence >= 0.6, R01 correlation check, max 3 pending

## Analyse the following from this week's pipeline output:

### 1. Signal Flow
- Signals generated → approved → executed → resolved (won/lost) this week
- What percentage passed each gate? Where is the bottleneck?

### 2. Brier Score
- This week vs rolling 30-day vs market 0.349 baseline
- Are we improving, stable, or degrading?
- If degrading: is it YES-side or NO-side? Which strategy?

### 3. YES Discount Calibration
- Is 0.85 still the right discount factor?
- Track YES accuracy over the last 30 signals
- If YES accuracy is now >50%, recommend relaxing to 0.90
- If YES accuracy is still <40%, consider tightening to 0.80

### 4. Perspective Divergence Quality
- Which divergences were real signals (led to correct predictions)?
- Which were noise (led to incorrect signals or no-trades)?
- Pattern: "Western positive + Russian negative → X% correct on [direction]"
- Are there specific perspective combinations that are systematically wrong?

### 5. Country Cluster Value
For each country in the Brave polling config (US, GB, RU, SA, TR, IN):
- How many articles did it contribute?
- How many of those articles ended up in divergent clusters?
- How many of those clusters generated correct signals?
- **Recommendation**: Should any countries be pruned from specific queries to save budget?
- **Recommendation**: Should any new countries be added (DE, FR, CN via proxy)?

### 6. Request Budget
- Actual requests vs 900/month ceiling
- Cost per signal generated (total Brave cost / signals)
- Cost per profitable signal (total cost / profitable signals)
- If cost per profitable signal > $1.00, flag for budget review
- Are any queries consuming budget without generating signals? Recommend pruning.

### 7. Source Bias Table
- Were any domains consistently misclassified (wrong lean or wrong reliability)?
- Did any unknown domains appear frequently? Add to source_bias.json.
- Specific updates recommended for source_bias.json entries?

### 8. Config Recommendations
Provide exactly **3 specific config.yaml parameter changes** with evidence:
```yaml
# Example format:
# CHANGE 1: divergence threshold 0.8 → 0.6
#   Evidence: 4 correct signals came from clusters with divergence 0.6-0.8
#   Expected impact: +2 signals/week, ~60% accuracy on marginal signals

# CHANGE 2: ...
# CHANGE 3: ...
```

## Output Format

```markdown
# Calibration Report — Week of YYYY-MM-DD

## Summary
[3 bullet points: best finding, worst finding, key recommendation]

## Brier Score Trend
[Table: week, ours, market, beat_rate, n_resolved]

## YES/NO Breakdown
[Table with recommendation for discount adjustment]

## Perspective Analysis
[Which combinations worked, which didn't]

## Country Value Matrix
[Table: country, articles, divergent_clusters, correct_signals, verdict]

## Budget
[Table: requests, cost, signals, cost_per_signal, cost_per_profitable]

## Config Diff
[3 specific changes with evidence]
```
