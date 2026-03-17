# Prediction Markets Observatory

A structured system for learning about real-world events through prediction markets, building domain knowledge, and calibrating forecasting ability over time.

## Purpose

1. **Learn** — Acquire deep context across major disciplines
2. **Predict** — Form independent estimates before checking markets
3. **Track** — Record predictions, market prices, and outcomes
4. **Calibrate** — Compare predictions vs reality to improve

## Disciplines

Markets are organized by knowledge domain. Each domain has:
- Research notes (context, models, key actors, history)
- Active market tracking (prices, own estimates, reasoning)
- Resolution log (outcomes vs predictions)
- Source list (trusted information sources for that domain)

| Code | Domain | Covers |
|------|--------|--------|
| `GEO` | Geopolitics & Conflict | Wars, diplomacy, treaties, sanctions, territorial disputes, military action |
| `POL` | Domestic Politics | Elections, legislation, appointments, party dynamics, polling |
| `ECO` | Economics & Monetary | Central banks, interest rates, inflation, GDP, employment, trade |
| `FIN` | Financial Markets | Equities, indices, commodities, corporate (earnings, M&A, market cap) |
| `CRY` | Crypto & Digital Assets | Bitcoin, ETH, altcoins, regulation, DeFi, adoption milestones |
| `TEC` | Technology & AI | AI capabilities, product launches, regulation, company moves, compute |
| `SCI` | Science & Health | Pandemics, climate, space, energy, medical breakthroughs, Nobel prizes |
| `SOC` | Society & Culture | Demographics, media, entertainment, sports governance, social trends |
| `LAW` | Legal & Regulatory | Court rulings, investigations, regulatory actions, constitutional questions |
| `ENV` | Environment & Energy | Climate targets, energy policy, natural disasters, resource markets |

## Directory Structure

```
prediction-markets/
├── README.md                    # This file
│
├── domains/                     # Knowledge domains
│   ├── GEO/                     # Geopolitics & Conflict
│   │   ├── context.md           # Background knowledge, models, key actors
│   │   ├── sources.md           # Trusted sources for this domain
│   │   ├── active.md            # Currently tracked markets + own estimates
│   │   └── research/            # Deep dives on specific topics
│   │       └── iran-us-2026.md  # Example: research notes
│   ├── POL/
│   ├── ECO/
│   ├── FIN/
│   ├── CRY/
│   ├── TEC/
│   ├── SCI/
│   ├── SOC/
│   ├── LAW/
│   └── ENV/
│
├── calibration/                 # Self-improvement system
│   ├── predictions.jsonl        # All predictions logged
│   ├── resolutions.jsonl        # Resolved markets + outcomes
│   ├── calibration.md           # Periodic calibration analysis
│   ├── lessons.md               # What I learned from being wrong
│   └── by-domain/               # Per-domain calibration stats
│       ├── GEO.json
│       ├── POL.json
│       └── ...
│
├── sources/                     # Cross-domain source infrastructure
│   ├── polymarket/              # Polymarket-specific
│   │   └── watchlist.md         # Tracked markets
│   ├── metaculus/               # Metaculus (future)
│   └── manifold/                # Manifold (future)
│
├── data/                        # Raw data snapshots
│   └── polymarket/
│       └── snapshot-YYYY-MM-DD.json
│
└── scripts/                     # Automation
    ├── fetch-polymarket.sh      # Raw fetch
    ├── fetch-interesting.sh     # Filtered fetch
    └── log-prediction.sh        # Log a prediction entry
```

## Prediction Schema

Every prediction is logged in `calibration/predictions.jsonl`:

```json
{
  "id": "pred-001",
  "ts": "2026-02-23T10:00:00Z",
  "domain": "GEO",
  "market": "US strikes Iran by March 31, 2026",
  "market_id": "polymarket:1234",
  "market_price": 0.57,
  "my_estimate": 0.45,
  "confidence": "medium",
  "reasoning": "Market seems to overweight recent rhetoric. Historical base rate for US strikes on sovereign nations is lower. But current admin is hawkish.",
  "key_factors": ["admin rhetoric", "base rate", "Iran nuclear timeline"],
  "research_ref": "domains/GEO/research/iran-us-2026.md",
  "resolution_date": "2026-03-31",
  "resolved": false,
  "outcome": null
}
```

## Resolution Schema

When a market resolves, log in `calibration/resolutions.jsonl`:

```json
{
  "pred_id": "pred-001",
  "ts": "2026-03-31T00:00:00Z",
  "domain": "GEO",
  "outcome": "No",
  "my_estimate_was": 0.45,
  "market_price_was": 0.57,
  "my_error": 0.45,
  "market_error": 0.57,
  "beat_market": true,
  "lesson": "Base rate reasoning held. Rhetoric != action.",
  "update_context": true
}
```

## Calibration

Periodically analyze: for all predictions where I said X%, what fraction actually happened?

Perfect calibration: of events I rate at 70%, exactly 70% occur.

Track:
- **Brier score** — overall accuracy (lower = better)
- **Calibration curve** — plot estimated vs actual frequency
- **Domain breakdown** — which domains am I calibrated in? Where am I overconfident?
- **Market comparison** — am I beating the market? Where and why?

## Workflow

### Daily (9AM cron)
1. Fetch fresh market data
2. Flag significant moves (>5% shifts)
3. Update active.md files in affected domains
4. Note any newly resolved markets → log resolutions

### Per New Market
1. Classify by domain
2. Research: read context.md, check sources, do web research
3. Form independent estimate with reasoning BEFORE checking market price
4. Log prediction
5. Compare with market — if divergent, research deeper

### Weekly Review
1. Review all active predictions
2. Update estimates if new information
3. Check resolutions
4. Run calibration analysis
5. Update lessons.md

### Monthly Calibration
1. Full calibration curve analysis
2. Domain-level performance review
3. Update context.md files with learned models
4. Feed insights into the Ouroboros loop (sense → reflect)
