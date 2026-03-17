You are a systems engineer building an automated calibration and scoring pipeline for a prediction market forecasting system.

## Context from Tier 1

Several scripts already exist:
- `scripts/time-decay-screener.py` — screens "by date" markets for S006 overpricing (working)
- `scripts/calibration-report.py` — basic Brier score report (needs upgrade)
- `scripts/log-prediction.py` — prediction logging (basic, needs interactive mode)
- `scripts/fetch-interesting.sh` — daily market fetch (working)

The strategy-domain matrix and time decay backtest are complete. We now need the infrastructure to actually track predictions, auto-resolve them, and measure calibration across domains.

## Objective

The calibration system at `~/Desktop/prediction-markets/calibration/` needs tooling to automate scoring, visualization, and feedback loops. Build the pipeline.

## Build Tasks

1. **Enhanced calibration report** (`scripts/calibration-report.py`):
   The existing script is basic. Upgrade it to:
   - Brier score calculation with confidence intervals
   - Calibration curve: bucket predictions by confidence level, compare to actual outcomes
   - ASCII visualization of calibration curve (can't install matplotlib, use terminal graphics)
   - Log loss metric (alternative to Brier)
   - Domain breakdown with statistical significance check (is domain X really worse, or just small sample?)
   - Time series of calibration: is it improving over time?
   - Market comparison: for each resolved prediction, what was my Brier vs market's Brier?
   - Kelly criterion analysis: given my calibration, what's the optimal bet sizing?

2. **Automated resolution checker** (`scripts/resolution-checker.py`):
   Write a script that:
   - Reads open predictions from `calibration/predictions.jsonl`
   - Checks Polymarket API for resolution status of each market
   - Auto-logs resolutions to `calibration/resolutions.jsonl`
   - Updates `calibration/by-domain/*.json` stats
   - Generates a resolution summary

3. **Prediction helper** (`scripts/predict.py`):
   Interactive CLI tool for making predictions:
   - Prompts for domain, market description, resolution date
   - Asks for MY ESTIMATE first (before showing market price)
   - Then fetches market price from Polymarket
   - Shows the divergence
   - Asks for reasoning and key factors
   - Logs to predictions.jsonl
   - Optionally creates paper trade (integration with strategies/paper-trades/)

4. **Dashboard updater** (`scripts/update-dashboard.py`):
   Regenerates all markdown dashboards from JSONL data:
   - `calibration/calibration.md`
   - `strategies/paper-trades/pnl-summary.md`
   - Domain-level active.md files (current prices from API)

5. **Feedback loop design**:
   Document the full feedback loop:
   - How does a calibration insight become a domain context update?
   - How does a strategy performance insight become a strategy refinement?
   - How do cross-domain patterns get surfaced?
   - How does all this connect to the Ouroboros loop in the main OpenClaw system?
   Write to: `~/Desktop/prediction-markets/calibration/feedback-loop.md`

## Output

Scripts in `~/Desktop/prediction-markets/scripts/`
Feedback loop doc in `calibration/feedback-loop.md`
Update `calibration/calibration.md` with pipeline documentation

End with:
- Architecture diagram (ASCII) of the full data flow
- What can be automated vs what needs human judgment
- Recommended cron schedule for automated checks
- **Test the pipeline**: make 3 example predictions on active markets (using the predict.py tool you built), then run the calibration report to verify the full chain works

You MUST read existing scripts before building replacements. Extend, don't duplicate. Test everything you write with actual execution.
