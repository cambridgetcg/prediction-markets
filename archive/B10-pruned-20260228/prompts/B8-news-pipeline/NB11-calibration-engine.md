# NB11: Calibration Engine, Outcome Collection & Weekly Report
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Context
[Paste NB01 architecture + signal_generator.py GeneratedSignal dataclass here]

The pipeline is fully implemented (NB02-NB08), tested (148 unit tests passing),
and wired (NB10). This prompt builds the missing calibration layer — the system
that measures pipeline quality and improves it over time.

### Current Calibration Baseline
- Brier score: 0.230 (vs market 0.349)
- NO accuracy: 7/7 (100%)
- YES accuracy: 2/5 (40%) — systematic weakness, YES discount = 0.85
- 75% of predictions beat market price
- Feb 28 = major resolution day (LT002)

### Existing Files
- `data/signals.jsonl` — all generated signals with status
- `data/truth_extractions.jsonl` — extraction calibration log
- `data/news-pipeline.db` — SQLite with articles, clusters, extractions, signals tables
- `config/news-pipeline.yaml` — pipeline parameters (yes_discount_factor, min_edge, etc.)

## Your Task

### Part 1: Calibration Engine (`scripts/calibration_engine.py`)

```python
class CalibrationEngine:
    """Measures pipeline quality and recommends parameter adjustments."""

    def __init__(self, db_path: Path = DB_PATH):
        self.conn = sqlite3.connect(str(db_path))

    # --- Core Metrics ---

    def record_outcome(self, signal_id: str, resolved_yes: bool,
                       resolution_price: float):
        """Record how a signal resolved. Updates signals table."""
        # Set resolved_at, outcome (profit/loss calc)
        # Update status to 'resolved'

    def compute_brier(self, window_days: int = 30) -> float:
        """Brier score for resolved signals in the window."""
        # Brier = mean((predicted_prob - actual_outcome)^2)
        # actual_outcome = 1.0 if resolved_yes else 0.0
        # predicted_prob = suggested_probability

    def compute_edge_accuracy(self, by_strategy: bool = False) -> dict:
        """How often did edge > 0 correlate with correct direction?"""
        # Overall: % of signals where (edge > 0 AND direction correct)
        # If by_strategy: break down by strategy_code

    def track_yes_accuracy(self) -> dict:
        """YES vs NO accuracy split + recommended discount factor."""
        # Count YES signals: correct / total
        # Count NO signals: correct / total
        # Compute recommended YES discount:
        #   If YES accuracy < 50%: tighten discount (e.g. 0.80)
        #   If YES accuracy > 60%: loosen discount (e.g. 0.90)
        #   Return current vs recommended

    def track_by_country_cluster(self) -> dict:
        """Which country perspective combinations are most predictive?"""
        # For resolved signals, trace back to cluster → articles → country_queried
        # Compute accuracy by country combination
        # Identify: which countries add signal vs just noise?

    def track_by_source(self) -> dict:
        """Which source domains are most/least reliable based on outcomes?"""
        # For resolved signals → cluster → articles → source_domain
        # Compare source's tone contribution to outcome direction
        # Flag domains that consistently mislead

    # --- Reports ---

    def generate_report(self, window_days: int = 30) -> str:
        """Full calibration report in markdown format."""
        # Include: Brier score, edge accuracy, YES/NO split,
        #          country cluster performance, source reliability,
        #          request budget efficiency, parameter recommendations

    def parameter_diff(self) -> dict:
        """Compute recommended config.yaml parameter changes with evidence."""
        # Compare current params to what outcomes suggest:
        #   - yes_discount_factor
        #   - min_edge threshold
        #   - divergence_threshold
        #   - country lists (prune/add)
        # Return: {"param": {"current": X, "recommended": Y, "evidence": "..."}}

    # --- Drift Detection ---

    def check_drift(self) -> dict:
        """Rolling 30-day Brier vs baseline. Alert if degrading."""
        # Compute 30-day rolling Brier
        # Compare to market baseline (0.349) and historical best (0.230)
        # Return: {"brier_30d": X, "vs_market": +/-Y, "alert": bool, "message": "..."}
```

### Part 2: Outcome Collector (`scripts/collect_outcomes.py`)

CLI tool that polls Polymarket for resolution status and auto-labels signal outcomes.

```python
#!/usr/bin/env python3
"""Collect Polymarket resolution outcomes and label signals.

Usage:
    python3 scripts/collect_outcomes.py                # Check all pending signals
    python3 scripts/collect_outcomes.py --days 7       # Check signals from last 7 days
    python3 scripts/collect_outcomes.py --signal SIG-abc # Check specific signal
    python3 scripts/collect_outcomes.py --manual SIG-abc yes  # Manual label
"""

def check_market_resolution(market_id: str) -> dict | None:
    """Poll Gamma API for market resolution status."""
    # GET https://gamma-api.polymarket.com/markets/{condition_id}
    # Check if resolved, resolution price

def collect_outcomes(days: int = 30):
    """Check all pending/approved/executed signals for resolution."""
    # For each signal with status in (approved, executed):
    #   If market resolved → record_outcome()
    #   Print summary

def manual_label(signal_id: str, resolved_yes: bool):
    """Manually label a signal's outcome."""
    # Useful when auto-collection fails or for paper trades
```

### Part 3: Weekly Calibration Prompt (`prompts/weekly_calibration_brave.md`)

```markdown
# Weekly Pipeline Calibration Report

Run every Sunday. Input: last 7 days of pipeline data.

## Data to Prepare

Before running this prompt, execute:
```bash
python3 scripts/collect_outcomes.py --days 7
python3 scripts/calibration_engine.py --report --days 7
```

Paste the output below.

## Analysis Required

1. **Signal Performance**
   - Signals generated → approved → executed → won/lost this week
   - Win rate by direction (YES vs NO)
   - Average edge on winning vs losing signals

2. **Brier Score**
   - This week's Brier score
   - Rolling 30-day Brier vs market baseline (0.349)
   - Trajectory: improving or degrading?

3. **YES Calibration**
   - Current YES discount factor: {from config}
   - YES accuracy this week
   - Recommended adjustment (with evidence)

4. **Perspective Divergence Quality**
   - Which divergent clusters produced correct signals?
   - Which were noise (divergent but signal was wrong)?
   - Common features of real vs noise divergence?

5. **Country Cluster Value**
   - Which countries added genuine signal?
   - Which just consumed request budget for no information gain?
   - Recommendation: prune any countries from queries?

6. **Source Reliability**
   - Any domains consistently misclassified in source_bias.json?
   - Specific lean/reliability adjustments recommended?

7. **Request Budget**
   - Requests used this week vs 900/month ceiling
   - Cost per signal generated
   - Cost per profitable signal
   - Any query producing zero useful clusters? Consider removing.

8. **Parameter Recommendations**
   - 3 specific config.yaml changes with evidence
   - Format: `param: current → recommended (reason)`

## Output Format

Structured markdown report + parameter diff table.
```

### Part 4: Calibration Engine CLI

Add CLI to `calibration_engine.py`:

```
python3 scripts/calibration_engine.py --report              # Full calibration report
python3 scripts/calibration_engine.py --report --days 7     # Last 7 days only
python3 scripts/calibration_engine.py --brier               # Brier score only
python3 scripts/calibration_engine.py --drift               # Drift check
python3 scripts/calibration_engine.py --diff                # Parameter diff
python3 scripts/calibration_engine.py --yes-accuracy        # YES/NO split
python3 scripts/calibration_engine.py --by-country          # Country cluster performance
python3 scripts/calibration_engine.py --by-source           # Source domain performance
```

### Part 5: Tests (`test_calibration_engine.py`)

```python
class TestRecordOutcome:
    def test_records_resolved_yes(self):
    def test_records_resolved_no(self):
    def test_computes_profit_loss(self):
    def test_updates_signal_status(self):

class TestBrierScore:
    def test_perfect_predictions(self):     # Brier = 0
    def test_worst_predictions(self):       # Brier = 1
    def test_mixed_predictions(self):
    def test_window_filter(self):
    def test_no_resolved_signals(self):

class TestEdgeAccuracy:
    def test_all_correct(self):
    def test_mixed(self):
    def test_by_strategy_breakdown(self):

class TestYesAccuracy:
    def test_yes_no_split(self):
    def test_discount_recommendation_tighten(self):
    def test_discount_recommendation_loosen(self):

class TestDriftDetection:
    def test_no_alert_when_below_market(self):
    def test_alert_when_above_market(self):

class TestParameterDiff:
    def test_recommends_changes(self):
    def test_no_changes_needed(self):

class TestReport:
    def test_generates_markdown(self):
    def test_includes_all_sections(self):
```

## Output

1. `scripts/calibration_engine.py` — full CalibrationEngine class + CLI
2. `scripts/collect_outcomes.py` — Polymarket resolution polling + manual labeling CLI
3. `prompts/weekly_calibration_brave.md` — weekly calibration prompt
4. `scripts/test_calibration_engine.py` — tests
