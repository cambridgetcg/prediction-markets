# E01: Fast Resolution Execution Sprint
# Priority: HIGHEST — fixes the calibration bottleneck
# Created: 2026-02-27
# Frequency: Run 2-3× per week until 50 resolved predictions reached
# Current: 12 resolved (all SOTU) → Target: 50 by end of April

## The Problem

Your edge is real (Brier 0.230 vs market 0.349) but validated on only 12 data points
from one event type (SOTU word markets). Every other system layer — strategies, risk
management, intelligence, psychology, news pipeline — is waiting for calibration data
to validate against. You are infrastructure-rich and data-poor.

**The fix is simple: trade more markets that resolve fast.**

## Current Calibration State

| Metric | Value | Target |
|--------|-------|--------|
| Total resolved | 12 | 50 by Apr 30 |
| Resolution sources | 1 (SOTU) | 5+ domains |
| NO accuracy | 7/7 (100%) | Maintain |
| YES accuracy | 2/5 (40%) | >60% |
| Brier score | 0.230 | <0.200 |
| Weekly resolution rate | 0 | 5-10 |

## Step 1: Market Screening (10 minutes)

Run the fast-resolution screener to find candidates:

```bash
python3 scripts/fast-resolution-screener.py
```

If the screener is stale or fails, manually pull from Gamma API:

```bash
curl -s "https://gamma-api.polymarket.com/events?limit=100&closed=false&order=volume&ascending=false" | \
  python3 -c "
import json, sys
from datetime import datetime, timezone, timedelta
cutoff = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
events = json.load(sys.stdin)
for e in events:
    for m in e.get('markets', []):
        end = m.get('endDate', '') or ''
        if end and end < cutoff and float(m.get('volumeNum',0) or 0) > 10000:
            prices = json.loads(m.get('outcomePrices','[]'))
            yes = float(prices[0]) if prices else 0.5
            print(f'{yes:.0%} YES | \${float(m.get(\"volumeNum\",0)):,.0f} vol | {end[:10]} | {m.get(\"question\",\"\")[:80]}')
"
```

### Selection Criteria

Pick **10 markets** that meet ALL of:

1. **Resolves within 7 days** (overnight to weekly)
2. **Volume > $10,000** (enough liquidity to enter/exit)
3. **Spread < 5%** (bid-ask not too wide)
4. **Domain diversity** — at minimum 2 different domains. Ideal: 3-4 from GEO, 3-4 from POL, 2-3 from ECO/TEC/SOC
5. **Mix of YES and NO** — at least 3 where your estimate will be YES (addressing the YES calibration gap)
6. **Not already in portfolio** — fresh markets only (no correlation with LT001-LT003 or paper positions)

### Avoid

- Markets at 97%+ or <3% (no edge to find, near-certain outcomes)
- Markets you have zero domain knowledge about (stick to your researched domains)
- Markets with ambiguous resolution criteria (check the rules)

## Step 2: Independent Estimation (30 minutes)

For each of the 10 selected markets, **estimate probability BEFORE looking at the market price**.

Use this template per market:

```markdown
### [Market Question]
**Resolution date**: YYYY-MM-DD
**Domain**: GEO/POL/ECO/TEC/CRY/SOC/LAW

**Base rate reasoning**:
- What is the historical base rate for this type of event?
- What is the implied daily probability if market price is used?

**Evidence for YES**:
1. [specific evidence]
2. [specific evidence]

**Evidence for NO**:
1. [specific evidence]
2. [specific evidence]

**Key uncertainty**: [what you don't know that would change your estimate most]

**My estimate**: X% (BEFORE seeing market price)
**Market price**: Y%
**Edge**: X - Y = ±Z pp
**Direction**: YES/NO
**Confidence**: Low/Medium/High

**Pre-mortem (if YES)**:
- What scenario makes this YES? How surprising would it really be?
- Am I underestimating this because of NO bias? (YES accuracy: 40%)

**Pre-mortem (if NO)**:
- Am I anchoring to my NO strength? Is this genuinely a NO, or am I defaulting?

**Strategy fit**: S001/S003/S004/S006/S008 (which playbook matches?)
```

### Critical: YES Pre-Mortem

Your single biggest calibration weakness is YES underestimation (40% accuracy).
For EVERY market where your initial estimate leans NO, force yourself to:

1. Write the specific scenario where YES happens
2. Rate how "surprising" that scenario would actually be (1-10)
3. If surprise < 7, add 5-10pp to your YES estimate
4. Check: did you underweight available evidence? (Lesson L05: the info existed for SOTU, you just missed it)

## Step 3: Position Sizing (10 minutes)

For each market with edge ≥ 5pp:

```
edge = |my_estimate - market_price|
kelly_full = edge / (1 - market_price)  # for NO direction
kelly_quarter = kelly_full × 0.25       # quarter Kelly
position_size = min(kelly_quarter × bankroll, bankroll × C1_CAP)

# Apply R01 checks:
# C1: position_size ≤ 3% of bankroll per event
# C2: total domain exposure ≤ 10% of bankroll
# C3: ρ < 0.30 with any existing position (or skip)
# C4: check portfolio delta before entry
```

For paper trades with ~$10K notional bankroll:
- Max per position: $300 (3% of $10K)
- Max per domain: $1,000 (10% of $10K)
- Typical position: $50-150 (quarter Kelly on 5-10pp edge)

## Step 4: Paper Trade Entry (10 minutes)

Log each trade in `strategies/paper-trades/positions.json`:

```json
{
  "id": "FT001",
  "market": "[question]",
  "market_id": "[condition_id]",
  "domain": "GEO",
  "strategy": "S006",
  "direction": "NO",
  "entry_price": 0.08,
  "my_estimate": 0.03,
  "market_price_at_entry": 0.08,
  "edge": 0.05,
  "size_usd": 100,
  "kelly_fraction": 0.018,
  "entry_date": "2026-02-28",
  "resolution_date": "2026-03-03",
  "stop_loss": null,
  "status": "open",
  "notes": "Fast resolution sprint FT001"
}
```

Naming: FT001-FT010 for fast-resolution trades (separate from PT paper trades).

## Step 5: Resolution & Calibration Harvest (when markets resolve)

As each market resolves:

1. **Record outcome**:
   ```bash
   python3 scripts/collect_outcomes.py --signal FT001 --resolved yes
   # or manually update positions.json
   ```

2. **Compute calibration**:
   - My Brier: (my_estimate - outcome)²
   - Market Brier: (market_price - outcome)²
   - Beat market? my_brier < market_brier

3. **Update calibration.md** with new predictions added to the table

4. **Log lessons** if estimate was >10pp off:
   - Which mental model failed?
   - Which evidence did I under/overweight?
   - Does this update any domain context?

5. **Track YES specifically**:
   - For every resolved YES: did I estimate ≥50%? If not, why?
   - Is the YES discount (0.85) still correct?

## Step 6: Weekly Calibration Check

After 10 fast-resolution trades resolve, run:

```markdown
### Sprint Calibration Check

| FT# | Market | My Est | Market | Outcome | My Brier | Mkt Brier | Beat? |
|-----|--------|--------|--------|---------|----------|-----------|-------|
| FT001 | ... | 0.03 | 0.08 | NO | 0.001 | 0.006 | YES |
| FT002 | ... | ... | ... | ... | ... | ... | ... |

**Sprint Brier**: [average]
**Sprint beat rate**: [X/10]
**YES accuracy this sprint**: [X/Y]
**NO accuracy this sprint**: [X/Y]
**New total resolved**: [12 + N]
**Domain breakdown**: GEO: X, POL: Y, ECO: Z

### Lessons from this sprint:
1. [biggest miss and why]
2. [biggest hit and why]
3. [YES calibration update]

### Parameter updates:
- YES discount: 0.85 → [new value if evidence warrants]
- Domain confidence adjustments: [any domain-specific insights]
```

## Budget & Pace

- **Time per sprint**: ~1 hour (screening + estimation + logging)
- **Frequency**: 2-3× per week
- **Cost**: $0 (paper trades)
- **Resolution cadence**: if selecting 7-day markets, ~10 resolutions per sprint
- **Projected timeline to 50**: 4-5 sprints = 2-3 weeks

## What This Unlocks

At 50 resolved predictions:
- Calibration curve becomes statistically meaningful (5+ per bucket)
- Domain-specific Brier scores become actionable (currently only POL has data)
- YES/NO asymmetry gets real measurement (currently N=5 for YES)
- Strategy-level performance tracking starts working
- The news pipeline's truth extraction calibration has ground truth to train against
- Whale signal correlation can be validated (do whale-aligned trades outperform?)

## Integration with Existing Systems

- **R04 (Fast Resolution Pipeline)**: E01 is the execution layer for R04's design
- **News Pipeline (NB)**: resolved FT trades feed NB09 calibration engine
- **Whale Monitor**: flag any FT market where a tracked whale has a position → compare outcomes
- **I05 (Calibration Report)**: FT data feeds directly into the weekly report
- **B04 (Psychology Calibration)**: FT trades give data to measure anchoring, YES bias, domain effects

## Output

1. 10 market selections with full estimation template
2. Paper trade entries in `positions.json` (FT001-FT010)
3. Updated `fast-resolution-calendar.md` with selected markets highlighted
4. After resolution: updated `calibration/calibration.md` with new rows
5. After resolution: any new lessons in `calibration/lessons.md`
