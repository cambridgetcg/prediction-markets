# I07 — February 28 Resolution Sweep

You are a calibration analyst and portfolio manager. February 28, 2026 is the single highest-resolution-density day we've encountered since building this system. Dozens of markets resolve simultaneously — SOTU retrospective markets, near-certain NONEs, bond rotation candidates, and our own PT003/PT005 positions.

Run this prompt ON or IMMEDIATELY AFTER Feb 28. It's designed to harvest maximum calibration data and execute the S011 bond rotation sweep in a single pass.

## Read First

1. `~/Desktop/prediction-markets/calibration/predictions.jsonl` — all active predictions
2. `~/Desktop/prediction-markets/calibration/calibration.md` — current Brier score dashboard
3. `~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md` — current portfolio
4. `~/Desktop/prediction-markets/strategies/playbooks/S011-bond-rotation.md` — bond rotation methodology
5. `~/Desktop/prediction-markets/domains/GEO/active.md` — Iran positions (PT003/PT005 may expire today)

---

## Task 1: Resolution Scan — What Resolves Feb 28

### 1a. SOTU Retrospective Markets

The Feb 25 SOTU generated ~$6-7M in sub-markets. By Feb 28, all should be fully resolved. Check each:

From our SOTU analysis (trade-report-sotu-2026.md), we predicted on 20 markets. Fetch resolution status for all.

```
web_search("Polymarket SOTU Trump February 25 2026 resolutions")
```

For each market we predicted on:
- What was the resolution?
- What was our estimate?
- What was the market price at time of our estimate?
- Brier score = (outcome - our_estimate)² and (outcome - market_price)²
- Did we beat the market?

Log ALL to `calibration/resolutions.jsonl` in the format:
```json
{
  "id": "CAL-045",
  "market": "Trump says 'Kamala' during SOTU",
  "resolved": "2026-02-25",
  "outcome": 1,
  "my_estimate": 0.42,
  "market_price_at_estimate": 0.38,
  "my_brier": 0.3364,
  "market_brier": 0.3844,
  "beat_market": true,
  "domain": "POL",
  "strategy": "S007",
  "notes": "Trump said Kamala 3× — correctly predicted"
}
```

### 1b. Near-Certain NONE Markets

The pnl-summary.md noted "dozens of near-certain NONE markets" resolve Feb 28. These are "by Feb 28" markets where YES was near-zero:

- Iran strike by Feb 28 (YES was 10.5% → our estimate 8-12% → resolves NO)
- Fed March cut already priced at ~3% YES
- Various monthly political targets

Fetch current resolution status:
```
web_search("Polymarket February 28 2026 market resolutions")
```

For each that resolves:
1. Confirm outcome
2. Update calibration log
3. If it was in our portfolio (PT003 for Iran Mar 31 is NOT today, but the Feb 28 window was)

### 1c. PT003 / PT005 Status

Check: did PT003 (US strikes Iran by Mar 31) and PT005 (US/Israel strikes Iran by Mar 31) produce any trigger events today?
- These markets resolve Mar 31, NOT Feb 28 — but Feb 28 is within Trump's stated deadline window
- If any Iran strike news broke → check positions immediately
- If T005 was already exited per D12 → confirm exit logged

---

## Task 2: S011 Bond Rotation — Feb 28 Sweep

S011 (Bond Rotation) identified that near-certain "by date" markets resolve at close to $1.00 NO. The strategy: capture the final 1-3¢ of time decay from near-certain outcomes.

### 2a. Candidate Identification

Fetch all Polymarket markets resolving in the next 7 days with:
- YES price currently: 0-10% (market is near-certain NO)
- Volume > $100K (enough liquidity to trade)
- Exact resolution date known (not ambiguous)
- Not already at 0% (there's still time value to capture)

```python
# Candidate profile (from S011 playbook):
# Entry criteria:
#   - YES < 10% (NO > 90%)
#   - Volume > $100K
#   - Resolves within 7 days
#   - Physical/political event not yet confirmed impossible
# Sizing: 1-2% bankroll per position ($100-200)
# Return: 1-3% in <7 days = 50-150% annualized
```

Search:
```
web_search("Polymarket markets resolving February 28 2026 predictions")
web_search("Polymarket markets resolving March 1 2026")
web_search("Polymarket markets resolving March 3 2026")
```

### 2b. Build the Feb 28 + Next-7-Day Opportunity List

For each candidate:
```json
{
  "market": "US strikes Iran by Feb 28",
  "resolution_date": "2026-02-28",
  "yes_price": 0.105,
  "volume_usd": 3250000,
  "position": "NO",
  "entry_price_no": 0.895,
  "days_to_resolution": 2,
  "implied_annualized_return": 0.105/0.895 / 2 * 365,
  "confidence": "high",
  "notes": "Geneva talks active, military officials say forces not in place until mid-March"
}
```

### 2c. Execute Top 3 S011 Positions

From the candidate list, select the 3 highest-conviction candidates that:
1. Have YES < 8% (high NO confidence)
2. Are not correlated with existing GEO positions
3. Resolve within 7 days

Execute as paper trades (or live if wallet is funded):
- Size: $100-150 each (1-1.5% of $10K paper bankroll)
- Log to `strategies/paper-trades/trades.jsonl`
- These are the first "fast-resolution" positions — critical for fixing the calibration bottleneck

---

## Task 3: Calibration Dashboard Update

Run the full calibration update after logging all resolutions.

### 3a. Key Metrics to Update

Current known calibration state (from I05 Feb 25):
- 9/12 SOTU predictions beat market (75%)
- Strong on NO (7/7), weak on YES (2/5)
- Brier score: 0.230 vs market 0.349

After adding today's resolutions:
- New sample size: N = ?
- New overall Brier: ?
- New beat-market rate: ?
- YES vs NO split: still lopsided?
- Domain breakdown: POL, GEO by category

Update `calibration/calibration.md` with:
```markdown
## Update: 2026-02-28

**New resolutions this update**: N
**Cumulative resolved predictions**: N_total

### Brier Score Trend
| Date | N | My Brier | Market Brier | Beat Rate |
|------|---|----------|-------------|-----------|
| Feb 25 (SOTU) | 12 | 0.230 | 0.349 | 75% |
| Feb 28 (sweep) | +N | ? | ? | ? |
| **Cumulative** | N_total | ? | ? | ? |

### YES vs NO Calibration
| Direction | N | Win Rate | Notes |
|-----------|---|---------|-------|
| YES bets | N_y | % | Still weak? |
| NO bets | N_n | % | Consistently strong |

### Domain Performance
| Domain | N | Brier | Beat Market | Edge Direction |
|--------|---|-------|-------------|----------------|
| POL | | | | |
| GEO | | | | |
| ECO | | | | |
```

### 3b. Key Diagnostic: YES Weakness

We're 2/5 on YES predictions. Before entering more YES bets (e.g., TEC trades, French Presidential bets), understand why:
- Were the YES prices too high at entry?
- Were we chasing unlikely outcomes?
- Is this a small-sample artifact?
- Implication for TEC trades (Anthropic March at 64% = a large YES bet)

Log assessment in `calibration/lessons.md`.

---

## Task 4: Portfolio Status Post-Feb 28

After all resolutions:
- Update `strategies/paper-trades/pnl-summary.md` with any resolved positions
- Calculate: what is current bankroll? How has unrealized changed?
- Verify: is PT005 exit logged? (from D12)
- Calculate new effective N (portfolio diversification)

### 4a. Resolution Speed Rebalancing Check

From R04: we need 50% of next $500 in Weekly/Monthly resolution.
- How many S011 positions did we open today? (Task 2c)
- Are we making progress on the resolution speed target?
- Calculate: new allocation by resolution speed category

---

## Task 5: Forward Calendar — Next Catalysts

Build the catalyst calendar for March, updating `data/catalyst-calendar.json`:

```json
[
  {
    "event": "Iran Trump deadline expiry",
    "date": "2026-03-05",
    "domain": "GEO",
    "affects_positions": ["PT001", "PT003"],
    "action": "T003 exit deadline if talks inconclusive"
  },
  {
    "event": "IAEA Board Meeting",
    "date": "2026-03-02",
    "domain": "GEO",
    "affects_positions": ["PT001", "PT003"],
    "action": "Monitor — censure vote changes dynamics"
  },
  {
    "event": "US Feb Jobs Report",
    "date": "2026-03-07",
    "domain": "ECO",
    "affects_positions": [],
    "action": "Signal for April FOMC entry decision (S003)"
  },
  {
    "event": "Feb CPI",
    "date": "2026-03-11",
    "domain": "ECO",
    "affects_positions": [],
    "action": "Second signal for April FOMC"
  },
  {
    "event": "Maduro court hearing",
    "date": "2026-03-17",
    "domain": "GEO",
    "affects_positions": ["PT007"],
    "action": "Monitor — any plea deal or legal development"
  },
  {
    "event": "FOMC Meeting + Dot Plot",
    "date": "2026-03-18",
    "domain": "ECO",
    "affects_positions": [],
    "action": "April FOMC entry signal — BUY YES if dovish dot plot"
  },
  {
    "event": "Iran Mar 31 resolution",
    "date": "2026-03-31",
    "domain": "GEO",
    "affects_positions": ["PT001", "PT003"],
    "action": "PT003 resolution + update PT001 thesis"
  },
  {
    "event": "Eurovision",
    "date": "2026-05-16",
    "domain": "SOC",
    "affects_positions": [],
    "action": "Eurovision arb (Israel 7% vs 22% bookmakers) — monitor participation"
  },
  {
    "event": "Le Pen Appeal Ruling",
    "date": "2026-07-07",
    "domain": "POL",
    "affects_positions": [],
    "action": "KEY catalyst for French 2027 presidential — all French bets hinge on this"
  }
]
```

---

## Output

1. Updated `calibration/resolutions.jsonl` — all Feb 28 resolutions logged
2. Updated `calibration/calibration.md` — new Brier scores, beat-market rates
3. 3 new S011 paper trade entries in `strategies/paper-trades/trades.jsonl`
4. Updated `strategies/paper-trades/pnl-summary.md` — post-Feb 28 portfolio state
5. Updated `data/catalyst-calendar.json` — March forward calendar
6. Terminal output: How many resolutions logged? Updated Brier score? Current portfolio P&L? Which S011 positions opened?

**Done when**: All Feb 28 resolutions are captured in calibration system, Brier score is updated, at least 3 S011 fast-resolution positions are open, and the catalyst calendar is current through June.

**Run on**: Feb 28, 2026 (or as early as possible after market resolutions are confirmed).
