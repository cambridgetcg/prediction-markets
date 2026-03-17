# Strategy Lab

A recursive testing ground for prediction market strategies. Every strategy is a hypothesis. Every trade is an experiment. Every result feeds back into better strategies.

## Philosophy

```
STRATEGY (hypothesis)
    │
    ├── PAPER TRADE (experiment)
    │       │
    │       ├── OUTCOME (data)
    │       │       │
    │       │       └── ANALYSIS (understanding)
    │       │               │
    │       │               └── REFINEMENT (better strategy)
    │       │                       │
    │       │                       └── PAPER TRADE (experiment)
    │       │                               └── ...
    │       │
    │       └── META-ANALYSIS (patterns across strategies)
    │               │
    │               └── NEW STRATEGY (emergence)
    │                       └── ...
    │
    └── DEATH (strategy retired with documented reason)
```

Every strategy passes through four phases:

| Phase | Name | Description |
|-------|------|-------------|
| **NIGREDO** | Raw Hypothesis | Untested idea. Define entry/exit rules, expected edge. |
| **ALBEDO** | Paper Testing | Live paper trades. No real money. Collect data. |
| **CITRINITAS** | Analysis | Enough data to evaluate. Is the edge real? Why/why not? |
| **RUBEDO** | Refinement/Death | Refine what works, kill what doesn't. Birth new variants. |

## Strategy Registry

Each strategy gets a codename, a playbook, and a scorecard.

### Active Strategies

| ID | Name | Type | Phase | Trades | P&L | Sharpe | Status |
|----|------|------|-------|--------|-----|--------|--------|
| S001 | Hold to Resolution | Baseline | **ALBEDO** | 2 | +$1.54 | — | PT002 (reclassified), PT006 active |
| S002 | Threshold Exit | Risk Mgmt | NIGREDO | 0 | — | — | Awaiting first trade |
| S003 | News Catalyst | Event-Driven | NIGREDO | 0 | -$35.09 | — | **PAUSED** — 1 closed trade (loss); timing violation |
| S004 | Contrarian Overreaction | Mean Reversion | **ALBEDO** | 2 | -$48.05 | — | PT001 (reclassified), PT003 active; domain restrictions added |
| S005 | Momentum Rider | Trend Following | NIGREDO | 0 | — | — | Awaiting first trade |
| S006 | Time Decay | Structural | **ALBEDO** | 1 | $0.00 | est. 2.6-4.5 | PT008 only; probability gate added (YES < 25%) |
| S007 | Cross-Market Arb | Structural | NIGREDO | 0 | — | — | PT002 reclassified to S001; awaiting NegRisk (P01) |
| S008 | Information Edge | Research-Driven | **ALBEDO** | 2 | -$10.97 | — | PT005 + PT007 active; add S009 overlay |
| S009 | Resolution Arbitrage | Structural (overlay) | NIGREDO | 0 | — | — | Overlay — assess oracle risk on all trades |
| S010 | Whale Signal | On-Chain Signal | NIGREDO | 0 | — | — | Confirmation signal via on-chain whale tracking |
| S011 | High-Prob Bond | Yield / Capital Mgmt | **ALBEDO** | 1 | pending | — | Live trade active; formalize paper tracking |
| S012 | LLM Ensemble Screener | AI-Native | NIGREDO | 0 | — | — | **Priority** — AI screens, human decides |
| S013 | Temporal Spread | Structural (S007 ext) | NIGREDO | 0 | — | — | Nested deadline mispricing in GEO |
| S014 | Geo-Restriction Edge | Info Asymmetry | NIGREDO | 0 | — | — | **Priority** — non-US local knowledge edge |

---

## Deployment Priority (Next 30 Days — Updated 2026-02-25)

*Source: `strategies/strategy-scorecard-2026-02-25.md`*

### Tier A — Deploy Capital First

| Strategy | Score | Rationale |
|----------|-------|-----------|
| **S011** Bond Rotation | 3.50 | Highest system fit (5/5); deploys idle capital; short duration 3-7d; formalize screener |
| **S008** Info Edge | 3.75 | Highest thesis quality (5/5); leverages domain knowledge; add S009 overlay |
| **S006** Time Decay | 3.75 | Strongest backtest (73.5% NO, 804 markets); after probability gate, clean systematic |

### Tier B — Deploy Selectively (with conditions)

| Strategy | Score | Condition |
|----------|-------|-----------|
| **S004** Contrarian | 3.25 | POL/CRY preferred. GEO only when ECI ≥ 7 and clear de-escalation catalyst identified |
| **S007** Arb | 3.00 | ≥3% edge after fees only. Real multi-outcome arb awaits P01 NegRisk |

### Tier C — Pause or Restrict

| Strategy | Score | Action Needed |
|----------|-------|---------------|
| **S003** Catalyst | 2.50 | **Paused** until timing discipline proven. Next test: June FOMC (enter no earlier than Apr 23) |
| **S001** Hold | 2.75 | **Restricted** to < 1 year duration. No new multi-year holds at current bankroll |

### Research Queue (not yet strategies)

| ID | Name | Status | Notes |
|----|------|--------|-------|
| R01 | Calendar Patterns | Needs Dune analysis | No published evidence yet — run data first |

### Retired Strategies

| ID | Name | Reason for Death | Lessons |
|----|------|-----------------|---------|
| — | — | — | — |

## Directory Structure

```
strategies/
├── README.md              # This file (registry + philosophy)
├── playbooks/             # Strategy definitions (the hypotheses)
│   ├── S001-hold-to-resolution.md
│   ├── S002-threshold-exit.md
│   ├── S003-news-catalyst.md
│   ├── S004-contrarian-overreaction.md
│   ├── S005-momentum-rider.md
│   ├── S006-time-decay.md
│   ├── S007-cross-market-arb.md
│   ├── S008-information-edge.md
│   ├── S009-resolution-arbitrage.md     (overlay)
│   ├── S010-whale-signal.md             (signal)
│   ├── S011-high-prob-bond.md           (capital mgmt)
│   ├── S012-llm-ensemble-screener.md    (AI-native)
│   ├── S013-temporal-spread.md          (S007 extension)
│   └── S014-geo-restriction-edge.md     (info asymmetry)
├── paper-trades/          # Trade log and position tracking
│   ├── trades.jsonl       # All paper trades
│   ├── positions.json     # Current open positions
│   └── pnl-summary.md     # Profit/loss dashboard
├── backtests/             # Historical analysis
│   └── README.md          # Backtesting methodology
└── evolution/             # Strategy evolution tracking
    ├── lineage.md         # Family tree of strategies
    ├── mutations.jsonl    # Strategy changes over time
    └── meta-lessons.md    # Cross-strategy patterns
```

## Paper Trading Rules

1. **Starting bankroll**: $10,000 (simulated)
2. **Position sizing**: Max 10% of bankroll per trade, max 30% per domain
3. **Entry**: Must log reasoning, strategy ID, expected edge
4. **Exit**: Must follow playbook rules (no discretionary overrides during ALBEDO phase)
5. **Tracking**: All trades in trades.jsonl with full metadata
6. **No hindsight**: Entry price = market price at time of logging (or specified limit)

## Metrics

| Metric | What It Measures | Good |
|--------|-----------------|------|
| **ROI** | Total return on capital | >0% |
| **Win Rate** | % of trades that profit | >50% for most strategies |
| **Avg Edge** | Mean profit per trade | >2% (covers fees/spread) |
| **Sharpe Ratio** | Risk-adjusted return | >1.0 |
| **Max Drawdown** | Worst peak-to-trough | <20% |
| **Domain Alpha** | Returns by domain | Identify strengths |
| **Strategy Alpha** | Returns by strategy | Kill underperformers |

## The Recursive Loop

```
             ┌─────── META-ANALYSIS ───────┐
             │                              │
             ▼                              │
    ┌─── Strategy A ───┐                    │
    │   trade, trade,   │──── results ──────┤
    │   trade, trade    │                   │
    └───────────────────┘                   │
    ┌─── Strategy B ───┐                    │
    │   trade, trade,   │──── results ──────┤
    │   trade, trade    │                   │
    └───────────────────┘                   │
    ┌─── Strategy C ───┐                    │
    │   (born from      │──── results ──────┘
    │    meta-analysis) │
    └───────────────────┘
```

Strategies don't just compete — they breed. When meta-analysis reveals that elements of two strategies combine well, a new hybrid is born. When a strategy dies, its lessons become selection pressure on survivors.
