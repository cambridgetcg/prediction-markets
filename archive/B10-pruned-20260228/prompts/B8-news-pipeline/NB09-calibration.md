# NB09: Calibration, Feedback & Weekly Report
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Context
[Paste NB01 + GeneratedSignal + current calibration baseline here]
Baseline: Brier 0.230 | Market 0.349 | NO 7/7 | YES 2/5 | YES discount: 0.85

## Metrics to Track

### Signal Quality
- Brier score of `suggested_probability` vs resolution
- Edge accuracy: edge > 0 → correct direction correlation
- By strategy code: which routes perform best?
- By source cluster: which perspective weightings are most predictive?

### Pipeline Health
- Articles ingested per hour (Brave availability)
- Clusters created vs dissolved per day
- Extraction success rate (divergent clusters → successful extraction)
- Signal acceptance rate (human approval %)
- False positive rate (signals rejected as not market-relevant)

### Drift Detection
- Rolling 30-day Brier score window
- Alert if drops below market baseline (0.349)
- Track YES/NO asymmetry — currently systemic weakness on YES

## Requirements

1. **CalibrationEngine class**:
   - `record_outcome(signal_id, resolved_yes: bool, resolution_price: float)`
   - `compute_brier(window_days: int = 30) -> float`
   - `track_yes_accuracy() -> float` → tune YES discount factor as accuracy improves
   - `track_by_country_cluster() -> dict` → which country perspectives most predictive?
   - `generate_report() -> str` ← markdown format, run weekly

2. **Brave-specific feedback**:
   - Track which country-cluster combinations correlate with correct signals
   - E.g.: "Signals where Iranian tone was most negative AND Western was neutral → 80% correct on NO"
   - Prune low-signal countries from queries to save request budget
   - Update `source_bias.json` monthly based on signal outcomes

3. **Request efficiency tracking**:
   - Cost per signal generated
   - Cost per profitable signal
   - Which queries justify their budget? Consider pruning low-signal queries.

4. **Weekly calibration prompt** (`prompts/weekly_calibration_brave.md`):
   ```
   Run every Sunday.
   Input: 7 days of pipeline output (signals, outcomes, perspective matrices).

   Analyse:
   1. Signals generated → approved → executed → won/lost this week
   2. Brier score this week vs rolling 30-day vs market 0.349 baseline
   3. YES accuracy — is the 0.85 discount still correct? Adjust up or down?
   4. Which perspective divergences were real (signal correct) vs noise (signal wrong)?
   5. Country cluster value: which countries added signal vs just consumed request budget?
      Recommend pruning any countries from queries?
   6. Request budget: actual vs 900/month ceiling, cost per signal, cost per profitable signal
   7. Source bias table: any domains consistently misclassified? Specific updates?
   8. 3 specific config.yaml parameter changes recommended, with evidence

   Output: Calibration report + config diff (what to change in config.yaml)
   ```

5. **Polymarket outcome collector**:
   - Poll Polymarket CLOB API for resolution status of tracked markets
   - Auto-label signal outcomes when market resolves
   - CLI: `python collect_outcomes.py --days 7`

## Output
`calibration_engine.py` + `prompts/weekly_calibration_brave.md` + `collect_outcomes.py` + tests.
