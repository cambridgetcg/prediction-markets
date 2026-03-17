You are a quantitative analyst building portfolio analytics tools to track metrics that our paper trading system currently doesn't measure: annualized returns, follow-trade P&L separation, wallet scoring, and capital efficiency.

## Why These Metrics Matter

From what-doesnt-work.md Section 7.2 (Where We're Still Vulnerable):
- **Time value of money**: Not tracked. Capital locked in a 6-month position earning 10% has an opportunity cost.
- **Win-rate trap**: We need to track payoff asymmetry per trade, not just win/loss.
- **Backtest-live gap**: We need to track realized edge vs theoretical edge.

From S010 evolution hooks:
- **Follow-trade P&L**: Isolate S010's contribution from base strategy P&L.
- **Wallet scoring**: Which tracked whales actually improve our decisions?

## Read First

1. ~/Desktop/prediction-markets/strategies/paper-trades/positions.json — current portfolio
2. ~/Desktop/prediction-markets/strategies/paper-trades/trades.jsonl — trade log
3. ~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md — current P&L summary
4. ~/Desktop/prediction-markets/calibration/predictions.jsonl — prediction log
5. ~/Desktop/prediction-markets/calibration/resolutions.jsonl — resolution log
6. ~/Desktop/prediction-markets/data/whale-registry.json — whale tracking targets
7. ~/Desktop/prediction-markets/data/whale-signals.jsonl (if P06 has run — S010 signal log)

---

## Task 1: Annualized Return Calculator

### 1a. Per-Position Annualized Returns

Every position should have an annualized return calculation. The formula:

```python
# For open positions:
holding_days = (today - entry_date).days
if holding_days == 0:
    holding_days = 1
period_return = (current_value - size_usd) / size_usd
annualized_return = (1 + period_return) ** (365 / holding_days) - 1

# For closed positions:
holding_days = (exit_date - entry_date).days
period_return = realized_pnl / size_usd
annualized_return = (1 + period_return) ** (365 / holding_days) - 1
```

**Why this matters**: A 10% return over 6 months is ~20% annualized. The same return in 2 weeks is ~260% annualized. Capital locked in long-duration positions with mediocre returns has a real opportunity cost.

### 1b. Portfolio-Level Metrics

Build a portfolio analytics script:

```python
# ~/Desktop/prediction-markets/scripts/portfolio-analytics.py

"""
Portfolio Analytics — calculate comprehensive performance metrics.

Usage:
    python3 portfolio-analytics.py              # Full analytics dashboard
    python3 portfolio-analytics.py --trade T001 # Single trade deep dive
    python3 portfolio-analytics.py --strategy S006 # Strategy-level metrics
    python3 portfolio-analytics.py --domain GEO    # Domain-level metrics
"""
```

Metrics to calculate:
- **Per-position**: annualized return, days held, payoff ratio (max gain / max loss), current edge
- **Per-strategy**: average annualized return, win rate, average edge at entry, Sharpe-like ratio
- **Per-domain**: total P&L, capital deployed, annualized return, number of positions
- **Portfolio**: total bankroll return, deployed capital efficiency, opportunity cost estimate

### 1c. Capital Efficiency Score

Rank positions by capital efficiency:

```
Capital Efficiency = annualized_return × (1 - correlation_with_other_positions)
```

Positions that earn high annualized returns AND are uncorrelated with the rest of the portfolio are the most capital-efficient. Positions earning low annualized returns that are highly correlated with others (like multiple Iran strike positions) are the least efficient.

This directly informs R05's capital allocation recommendations.

---

## Task 2: Payoff Asymmetry Tracker

### 2a. The Win-Rate Trap Detection

From what-doesnt-work.md: "A trader right 30% of the time on $0.10 contracts will outperform a trader right 70% of the time on $0.70 contracts."

For each trade, calculate:

```python
# Entry price defines the payoff asymmetry
entry_price = position["entry_price"]  # This is the NO price for NO positions

# For NO positions: we pay (1 - YES_price) and gain YES_price if NO resolves
if direction == "NO":
    risk = 1 - entry_price        # What we pay per share
    reward = entry_price           # What we gain if NO resolves
else:
    risk = entry_price
    reward = 1 - entry_price

payoff_ratio = reward / risk
breakeven_winrate = risk / (risk + reward)  # = 1 / (1 + payoff_ratio)
```

### 2b. Zone Classification

Classify every trade entry by price zone (from what-doesnt-work.md action items):

| Zone | Entry Price (YES) | Payoff Ratio | Risk Level |
|------|------------------|-------------|------------|
| 1 | $0.01 - $0.20 | 4:1 to 80:1 | Low risk, high reward, low probability |
| 2 | $0.20 - $0.40 | 1.5:1 to 4:1 | Moderate — sweet spot for contrarian |
| 3 | $0.40 - $0.60 | 0.67:1 to 1.5:1 | Coin flip territory |
| 4 | $0.60 - $0.80 | 0.25:1 to 0.67:1 | High risk — need strong thesis |
| 5 | $0.80 - $0.99 | 0.01:1 to 0.25:1 | Bond territory — one loss wipes many wins |

Track P&L by zone. Flag any trade entering Zone 4-5 without exceptional documented justification.

### 2c. Expected Value at Entry

For each trade, calculate the EV at time of entry:

```python
# Our probability estimate vs entry price
our_estimate_no = 1 - our_estimate_yes  # Our P(NO)
ev_per_share = (our_estimate_no * 1.0) - (1 - our_estimate_no) * (entry_price / (1 - entry_price))
# Simplified: ev = our_estimate - entry_price (for the side we're buying)
```

Track: are our EV-positive trades actually profitable? This separates skill from luck.

---

## Task 3: S010 Follow-Trade P&L Isolation

### 3a. The Problem

S010 (whale signal) is a modifier, not standalone. When denizz confirms our T001 NO position and we size up, the additional profit (or loss) from the sizing adjustment is S010's contribution. We need to track this separately.

### 3b. Schema

```json
// Add to each position in positions.json:
{
  "s010_signals": [
    {
      "date": "2026-02-26",
      "whale": "denizz",
      "signal_type": "A",
      "action": "HOLD — confirmation, no sizing change",
      "sizing_impact_usd": 0,
      "notes": "$32.8K NO on same market"
    }
  ],
  "s010_pnl_contribution": 0.00
}
```

### 3c. Attribution Logic

```python
# When a Type A signal causes sizing up:
s010_contribution = additional_shares * (exit_price - entry_price)

# When a Type C signal causes early exit:
s010_contribution = avoided_loss  # (what we would have lost if we stayed in)

# When no S010 signal on a position:
s010_contribution = 0
```

Build this into portfolio-analytics.py as a separate "S010 Attribution Report" section.

---

## Task 4: Wallet Scoring Model

### 4a. The Question

Which tracked whales actually improve our decisions? Not all 15 registry wallets are equally valuable. We need a scoring model.

### 4b. Scoring Dimensions

For each wallet, track:

```python
wallet_score = {
    "accuracy_in_domain": 0,      # Win rate on trades in their documented domain
    "signal_timeliness": 0,        # How far before resolution they typically enter
    "signal_actionability": 0,     # Could we have followed in time? (not 5min before resolution)
    "size_consistency": 0,         # Do they size up on their best ideas?
    "our_follow_success": 0,       # When we followed their signal, did it work?
    "contradiction_value": 0,      # When they contradicted us, were they right?
}

# Composite score (weighted):
composite = (
    0.3 * accuracy_in_domain +
    0.2 * signal_timeliness +
    0.1 * signal_actionability +
    0.1 * size_consistency +
    0.2 * our_follow_success +
    0.1 * contradiction_value
)
```

### 4c. Quarterly Update

Each R05 quarterly review should recalculate wallet scores and update follow_confidence in whale-registry.json accordingly.

---

## Task 5: Dashboard Output

### 5a. Design the Dashboard

```
=== PORTFOLIO ANALYTICS — 2026-02-26 ===

PORTFOLIO SUMMARY:
  Bankroll: $10,000 | Deployed: $1,685 (16.9%) | Available: $8,315
  Realized P&L: -$35.09 | Unrealized P&L: -$57.48
  Portfolio Return: -0.92% | Annualized: -XX%

POSITION BREAKDOWN (sorted by annualized return):
  T002 | NO Trump 2028  | Ann. Ret: +XX% | Zone 5 | Payoff 0.03:1 | Edge: 60pp
  T008 | NO BTC $150K   | Ann. Ret: +0%  | Zone 5 | Payoff 0.09:1 | Edge: 6pp
  T006 | YES Vance 2028 | Ann. Ret: +0%  | Zone 3 | Payoff 1.40:1 | Edge: 14pp
  T007 | NO Maduro      | Ann. Ret: +0%  | Zone 5 | Payoff 0.15:1 | Edge: 13pp
  T003 | NO Iran Mar31  | Ann. Ret: -XX% | Zone 3 | Payoff 0.72:1 | Edge: 3pp
  T005 | NO US/Israel   | Ann. Ret: -XX% | Zone 3 | Payoff 0.70:1 | Edge: 2pp
  T001 | NO Iran Jun30  | Ann. Ret: -XX% | Zone 4 | Payoff 0.50:1 | Edge: 4pp

STRATEGY PERFORMANCE:
  S001: 2 positions, avg ann. ret XX%, capital $625
  S004: 2 positions, avg ann. ret XX%, capital $600
  S006: 1 position,  avg ann. ret XX%, capital $75
  S008: 2 positions, avg ann. ret XX%, capital $350

DOMAIN CONCENTRATION:
  GEO: 56% of deployed capital (4 positions) ← CONCENTRATED
  POL: 37% (2 positions)
  CRY: 4% (1 position)

S010 ATTRIBUTION:
  Type A confirmations: 3 (denizz on T001/T003/T005)
  Type C contradictions: 0
  S010 P&L contribution: $0 (no sizing adjustments made yet)

ALERTS:
  ⚠ T001 in Zone 4 — payoff ratio 0.50:1, requires 67% win rate to break even
  ⚠ GEO concentration 56% — consider diversifying
```

### 5b. Implement the Script

Build `scripts/portfolio-analytics.py` that generates this dashboard from positions.json, trades.jsonl, and whale-signals.jsonl.

---

## Output

1. `scripts/portfolio-analytics.py` — comprehensive analytics script
2. Updated `strategies/paper-trades/positions.json` — add s010_signals field to each position
3. Terminal output: first analytics dashboard run with real data
4. Assessment: which positions are capital-efficient and which are dragging?

**Done when**: portfolio-analytics.py runs and produces the full dashboard with annualized returns, zone classification, payoff ratios, strategy/domain breakdowns, and S010 attribution. All calculations use real data from positions.json.
