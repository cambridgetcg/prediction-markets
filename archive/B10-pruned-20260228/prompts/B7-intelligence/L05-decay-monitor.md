# L05 — Decay Monitor: Signal Freshness and Edge Degradation

You are a quantitative analyst managing the long-term health of the insider intelligence pipeline. L01-L04 identify and act on insider signals. L05's job is to answer: **is the signal still valid?**

Insider edges degrade. Markets adapt. Insiders get exposed. Behaviour changes. A wallet that had massive edge in 2024 might be ghost-trading on reputation alone in 2026. This prompt builds the monitoring system that keeps the insider registry fresh and culls dead signals.

## Read First

1. `~/Desktop/prediction-markets/data/classified-insiders.json` — current insider registry (L03 output)
2. `~/Desktop/prediction-markets/data/follow-signals.jsonl` — history of signals generated (L04 output)
3. `~/Desktop/prediction-markets/data/edge-profiles.json` — raw edge data (L01 output)
4. `~/Desktop/prediction-markets/memory/loop/` — Ouroboros loop structure (conceptual parallel: this is the loop's decay detection, applied to the trading system)

---

## Task 1: Edge Degradation Detection

### 1a. Rolling Window Analysis

The core question: is an insider's edge holding up over time, or has it decayed?

```python
def rolling_edge(wallet, category, window_days=90):
    """
    Compute edge for this account in this category over a rolling window.
    Run for windows ending at: now, 3mo ago, 6mo ago, 12mo ago.

    Returns:
      [
        {"period_end": "2026-02-26", "mean_edge": 0.21, "n": 12, "p": 0.003},
        {"period_end": "2025-11-26", "mean_edge": 0.19, "n": 14, "p": 0.001},
        {"period_end": "2025-08-26", "mean_edge": 0.24, "n": 18, "p": 0.0004},
        {"period_end": "2025-05-26", "mean_edge": 0.28, "n": 21, "p": 0.00001},
      ]

    Trend analysis: is edge stable, growing, or decaying?
    """
```

**Decay patterns to watch for:**

| Pattern | Signal | Action |
|---------|--------|--------|
| Edge declining each window | Market adapting to their behaviour | Lower follow confidence. Flag for review. |
| Edge went to ~zero in last window | Lost the information source | Remove from active registry. Archive. |
| N bets declining sharply | Person became cautious (may have been warned) | Flag — they're still a person, just quieter |
| Edge stable across all windows | Durable structural advantage | Maintain confidence. Raise if improving. |
| Edge increasing | Gaining better access or deeper expertise | Raise confidence. |

### 1b. The Exposure Test

When an insider is publicly identified (like AlphaRaccoon), their edge typically collapses because:
1. The market prices in their likely positions before they make them
2. Polymarket may restrict their account
3. They change wallets (though the new wallet starts with no track record)

```python
def exposure_check(wallet, alias):
    """
    Web search: "[wallet address] polymarket" + "[alias] polymarket"
    Check: has this wallet been publicly identified in news, Twitter, research reports?

    If yes:
      - Note exposure date
      - Check if edge degraded after exposure date
      - Mark as "Exposed" in registry
      - Lower follow confidence to 2/5 maximum (they may continue but others are watching too)
    """
```

**Known exposed accounts to check:**
- AlphaRaccoon (Google insider) — public since ~2024
- The two Israeli defendants charged Feb 2026 — now public, likely abandoned wallets

---

## Task 2: Refresh Schedule

### 2a. Automated Refresh Pipeline

```python
# ~/Desktop/prediction-markets/scripts/l05-decay-monitor.py

"""
L05 Decay Monitor — scheduled maintenance for insider registry

Schedule: Run weekly (Sundays, same window as calibration review)

Tasks per run:
  1. Pull latest resolved trades since last run
  2. Update edge-profiles.json with new data points
  3. Re-compute rolling windows for all active insiders
  4. Check decay patterns
  5. Run exposure checks on any insiders with insider_score >= 7
  6. Update classified-insiders.json:
     - Adjust follow_confidence where warranted
     - Mark decayed accounts as "archived"
     - Promote new accounts if edge has strengthened
  7. Output decay report
"""

DECAY_THRESHOLDS = {
    "soft_flag":   0.30,  # Edge in latest window < 30% of historical max → flag for review
    "hard_flag":   0.10,  # Edge in latest window < 10% of historical max → lower confidence
    "archive":     0.00,  # Edge in latest window <= 0 over 3+ consecutive windows → archive
    "inactive":    90,    # No new bets in 90 days → flag as possibly inactive
}
```

### 2b. Confidence Update Rules

The follow_confidence rating (1-5) should update dynamically:

```python
def update_confidence(insider, decay_analysis):
    """
    Confidence update rules:

    INCREASE by 1 if:
      - Latest 90-day window edge > historical average (improving signal)
      - N bets increasing (more active, more data)
      - Correctly called 2+ of our recent follow signals (calibration confirmed)

    DECREASE by 1 if:
      - Latest 90-day window edge < 50% of historical average
      - Account publicly exposed (add: exposure_penalty = -1)
      - 2+ consecutive follow signals generated losses (under-performing)
      - Inactive > 60 days (may have abandoned the account)

    SET TO 1 (minimum watch) if:
      - Edge reversed (now negative in their speciality)
      - Account confirmed abandoned

    Archive if confidence stays at 1 for 2 refresh cycles with no new activity.
    """
```

---

## Task 3: Registry Lifecycle Management

### 3a. Three States

Every account in the registry exists in one of three states:

```python
REGISTRY_STATES = {
    "ACTIVE":    "Following. Confidence 3-5. Edge holding.",
    "WATCHING":  "Monitoring. Confidence 1-2. Edge weakening or account inactive.",
    "ARCHIVED":  "Not following. Edge gone or account abandoned. Kept for historical analysis."
}
```

### 3b. State Transition Log

Every change in registry state must be logged:

```jsonl
{"ts":"2026-03-15T10:00:00Z","wallet":"0x...","alias":"POL-Insider-01","event":"confidence_downgrade","from":4,"to":3,"reason":"Latest 90-day window edge 0.14 vs historical avg 0.21. -33% decay. Soft flag triggered.","action":"continue watching"}
{"ts":"2026-04-20T10:00:00Z","wallet":"0x...","alias":"TEC-Insider-02","event":"state_change","from":"ACTIVE","to":"WATCHING","reason":"No new bets in 95 days. Possible account abandonment or warning received."}
{"ts":"2026-05-01T10:00:00Z","wallet":"0x...","alias":"GEO-Specialist-01","event":"exposure_flagged","source":"Twitter — @PolymarketAlerts identified wallet in thread","action":"Reduce follow confidence to 2. Others will front-run their entries."}
```

Write to: `data/registry-events.jsonl`

### 3c. New Account Discovery

L05 isn't just about decay — it also promotes new insiders as they accumulate track records:

```python
def check_emerging_insiders(edge_profiles, current_registry):
    """
    Identify accounts NOT yet in insider-registry.json who now qualify.

    Promotion criteria (conservative — new accounts must earn trust):
      - insider_score >= 6.0 (lower than initial 7.0 threshold for ongoing discovery)
      - N bets in dominant category >= 20 (increased threshold for new promotions)
      - p < 0.01 (tighter than initial 0.05)
      - Active in last 60 days (currently trading)

    For qualifying accounts:
      - Add to registry with follow_confidence = 2 (watch first, don't follow)
      - After 2 refresh cycles with maintained edge: raise to 3 (follow)
    """
```

---

## Task 4: Performance Attribution

### 4a. Did Following Actually Work?

Track the P&L specifically attributable to L04 follow signals:

```python
"""
For every entry in follow-signals.jsonl with action "FOLLOW" or "ADD":
  - Find the corresponding trade in our P&L records
  - Calculate: P&L if we had NOT followed vs. actual P&L
  - Was the insider signal a net positive?

Report monthly:
  L04-attributed trades: N
  Win rate (L04 signals): X%
  Win rate (non-L04 trades): Y%
  L04 edge vs. baseline: Z%

This is the acid test. If following insiders doesn't beat our base rate,
the entire L-series pipeline needs reassessment.
"""
```

### 4b. False Positive Audit

From L02's sensitivity analysis, ~5% of accounts pass significance by chance.
Monthly, audit a random sample of "NOISE" tier accounts that are close to the threshold:
- Are any of them actually showing consistent edge we missed?
- Adjust thresholds if systematic bias found.

---

## Task 5: Integration with Calibration Review

The weekly calibration review (R04 prompt) should include an L05 section:

```markdown
## Insider Signal Performance (L05 Section — added to R02/R04)

Active insiders: N  
Accounts downgraded this week: X  
Accounts archived this week: Y  
New accounts promoted to WATCHING: Z  

L04 signal performance (last 30 days):
  Signals generated: 12
  Followed: 8 (4 AGREE_NO_POSITION, 4 AGREE_WITH_POSITION)
  Not followed: 4 (2 field mismatch, 1 CONTRADICT, 1 timing too late)
  
  P&L on followed signals: +$xxx (+X%)
  vs. counterfactual (no follow): +$yyy
  
  Net L04 attribution: +$zzz
```

---

## Output

1. `scripts/l05-decay-monitor.py` — weekly decay monitoring script
2. `data/registry-events.jsonl` — lifecycle event log (create with initial state entries for all current insiders)
3. Updated `data/classified-insiders.json` — add `registry_state`, `confidence_trend`, `last_decay_check` fields to each entry
4. Updated cron suggestion: add L05 to Sunday calibration window (run after R02, R04)
5. Terminal output: decay analysis for any current active insiders based on whatever historical data is available right now

**Done when**: The decay monitor script exists, the registry has lifecycle state fields, and we have at least one complete decay analysis run showing trend data for each high-confidence insider. The pipeline is closed-loop: L01 populates → L02 scores → L03 classifies → L04 follows → L05 monitors and culls.
