You are a portfolio manager conducting the first quarterly system review. This is a comprehensive health check of the entire prediction market trading system — strategies, calibration, whale registry, edge decay, and operational readiness.

## Why Quarterly Reviews Matter

Edge decays. From what-doesnt-work.md:
- Cross-platform arb opportunities compressed from 12.3s to 2.7s in one year
- Any discovered edge attracts competition → returns compress toward zero
- The strategies that survive are those requiring domain knowledge, not speed
- Our S006 time-decay edge depends on domain NO rates that may shift over time

This review catches decay before it costs us money.

## Read First

1. ~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md — portfolio state
2. ~/Desktop/prediction-markets/strategies/paper-trades/positions.json — open positions
3. ~/Desktop/prediction-markets/calibration/predictions.jsonl — all predictions
4. ~/Desktop/prediction-markets/calibration/resolutions.jsonl — resolved predictions
5. ~/Desktop/prediction-markets/data/whale-registry.json — whale tracking targets
6. ~/Desktop/prediction-markets/strategies/strategy-scorecard-2026-02-25.md (if exists) — last scorecard
7. ~/Desktop/prediction-markets/strategies/evolution/strategy-domain-matrix.md — strategy-domain fit
8. ~/Desktop/prediction-markets/strategies/backtests/S006-time-decay-backtest.md — baseline S006 data
9. ~/Desktop/prediction-markets/strategies/backtests/S004-overreaction-backtest.md — baseline S004 data

---

## Task 1: Calibration Health Check

### 1a. Prediction Accuracy

Analyze all resolved predictions:
- Overall Brier score
- Brier score by domain (GEO, POL, ECO, CRY, TEC)
- Brier score by strategy (S001-S012)
- Calibration curve: are we overconfident? Underconfident? In which ranges?

### 1b. Paper Trading P&L

- Total realized P&L (closed positions)
- Total unrealized P&L (open positions at current market prices)
- Win rate by strategy and domain
- Average holding period vs. resolution period
- Largest win, largest loss, average position size

### 1c. Edge Measurement

For each active strategy, calculate the observed edge:
- S004: what % of our contrarian entries reverted toward our estimate?
- S006: what % of our time-decay NO entries resolved NO?
- S008: what was our average edge (our estimate - market price) at entry?
- S010: did whale confirmation signals improve our outcomes?

Compare observed edge to the theoretical edge from backtests.

---

## Task 2: Strategy Edge Decay Check

### 2a. S006 Time Decay Recalibration

The S006 backtest found:
- 73.5% count-weighted NO rate (804 markets)
- 60% volume-weighted NO rate
- Domain NO rates: ENV 82.4%, OTHER 80.0%, POL 78.3%, CRY 69.5%, GEO 64.3%, TEC 63.6%, ECO 60.0%

Recalculate with new resolution data:
1. Fetch recently resolved "by date" markets from Gamma API: `/events?limit=100&closed=true&order=end_date_max&ascending=false`
2. Filter to markets with "by" in the question (deadline markets)
3. Calculate updated domain NO rates
4. Compare to baseline — has the edge compressed >10%?

### 2b. S004 Overreaction Recalibration

The S004 backtest found:
- 58% negative serial correlation
- ~40% reversion within 7 days after 5pp shock
- Weekly drift more exploitable than daily spikes

Check:
- Run spike-detector.py with recent data — is the spike frequency changing?
- Are reversion rates holding steady or declining?
- Any new academic papers on prediction market efficiency? Web search: "prediction market efficiency 2026 new research"

### 2c. S007 Overround Check

Run overround-scanner.py on current multi-outcome markets:
- Has the average overround decreased since last check?
- Are the neg-risk conversion opportunities still present?
- Is bot competition compressing the arb window?

---

## Task 3: Whale Registry Refresh

### 3a. P&L Update

For each wallet in whale-registry.json:
1. Check current profile on polymarket.com/profile/{wallet}
2. Update estimated_total_profit
3. Note any significant change in win_rate
4. Check if still active (traded in last 90 days)

### 3b. Prune & Add

- **Prune**: Remove wallets with:
  - Zero activity in last 90 days (unless known dormant-then-reactive pattern like ricosuave666)
  - Declining win rate below 55%
  - Identified as wash trading

- **Add**: Search for new profitable wallets via:
  - PolyTrack leaderboard (new entries since last check)
  - PANews smart money library (new articles)
  - Polymarket official leaderboard (sort by 30-day profit)
  - Web search: "Polymarket top traders 2026 Q1"

### 3c. Follow-Trade P&L

If we've been tracking S010 signals:
- How many Type A confirmations did we receive?
- Did any Type C contradictions save us from a loss?
- What was the P&L contribution specifically from S010 sizing adjustments?
- Should any wallet's follow_confidence be upgraded or downgraded?

---

## Task 4: Operational Review

### 4a. Infrastructure Status

Check all monitoring tools:
- Is whale-monitor.py running daily? Review recent scan files in data/
- Are PolyTrack/Polywhaler/PolyMonit alerts functioning?
- Is the calibration pipeline logging predictions correctly?
- Any scripts that have broken due to API changes?

### 4b. Risk Limits

Review against BANKROLL.md limits:
- Have we hit any drawdown stops (-15%, -25%, -40%)?
- Is domain concentration within limits? (GEO currently 4/7 positions)
- Is maximum position size within 5% bankroll cap?
- Opportunity cost: what's the annualized return on deployed capital? On total bankroll?

### 4c. Knowledge Gaps

What domains or market types are we NOT trading that we should be?
- Are there new high-volume market categories on Polymarket?
- Any new domains emerging (e.g., AI safety, space)?
- Should we expand into LAW now that it's seeded?
- Is TEC domain ready for live positions?

---

## Task 5: Forward Plan

### 5a. Strategy Prioritization

Based on edge decay and performance data, rank strategies by:
1. Observed edge (realized, not theoretical)
2. Capital efficiency (annualized return per dollar deployed)
3. Data richness (how many calibration events per month)
4. Sustainability (is the edge still present or decaying?)

### 5b. Capital Allocation Update

Recommend updated capital allocation across strategies:
- Should we increase/decrease S006 allocation?
- Is S004 performing well enough to increase sizing?
- Should idle capital go to S011 bond rotation?
- What % of bankroll should remain in cash reserve?

### 5c. Next Quarter Goals

Define measurable targets for the next quarter:
- Calibration: target Brier score (e.g., <0.15)
- P&L: target realized P&L (e.g., +5% bankroll)
- Resolution count: target N resolved predictions for calibration
- New strategies: which to advance from NIGREDO to ALBEDO?

---

## Output

1. `strategies/quarterly-review-2026-Q1.md` — comprehensive review document
2. Updated `data/whale-registry.json` — refreshed P&L, pruned inactive, added new
3. Updated `strategies/evolution/strategy-domain-matrix.md` — if strategy rankings changed
4. Terminal output: key metrics summary (Brier scores, P&L, edge status, risk limits)

**Done when**: Every active strategy has been checked for edge decay, the whale registry is refreshed, calibration metrics are current, and a forward plan with measurable targets exists for Q2.
