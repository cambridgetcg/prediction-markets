# S003 — News Catalyst

**Phase**: NIGREDO (untested)
**Type**: Event-driven
**Edge hypothesis**: Predictable information events (scheduled announcements, meetings, deadlines) create predictable price movements. Position before the event, profit from the resolution of uncertainty.

## Why This Exists

Many markets have known future information events that will dramatically move prices:
- Fed meetings → ECO markets
- Election dates → POL markets
- Earnings reports → FIN markets
- Treaty deadlines → GEO markets
- Court rulings → LAW markets
- Product launches → TEC markets

The edge isn't knowing the outcome — it's understanding that uncertainty premium compresses as the event approaches, and understanding the asymmetry of possible outcomes.

## Rules

### Entry
- **Identify catalyst**: A known future event that will resolve or significantly move a market
- **Pre-position window**: Enter 3-7 days before the catalyst. **HARD RULE — no exceptions.** (T004 post-mortem: entering 23 days early exposed the trade to thesis-killing data. See `calibration/lessons.md` T15.)
- **Direction**: Based on research + domain context, which outcome is underpriced?
- **Direction verification (CME divergence)**: When using CME FedWatch vs Polymarket divergence, verify which market is more likely correct for the specific probability range. Below 10%, Polymarket retail may be MORE accurate than CME institutional hedgers. Above 30%, CME is likely more accurate. (T04 post-mortem: T13.)
- **Size**: 3-5% of bankroll (moderate — catalysts are binary, risk is real)

### Catalyst Types

| Type | Example | Typical Entry Window |
|------|---------|---------------------|
| **Scheduled** | Fed meeting, election day | 3-7 days before |
| **Deadline** | Treaty expiry, regulatory deadline | 5-14 days before |
| **Seasonal** | Budget announcements, Nobel season | 7-14 days before |
| **Conditional** | "If X happens, then Y" chains | When X becomes likely |

### Exit
- **On catalyst day**: Regardless of outcome, evaluate position
- **Pre-catalyst exit**: If market moves >20% in your direction before the event, take half off
- **Post-catalyst hold**: If catalyst confirms your thesis but market hasn't fully priced it, hold up to 48h post-event
- **Stop**: -30% pre-catalyst (thesis was wrong or priced out)

### Research Requirements (higher bar)
- Must identify the specific catalyst event and date
- Must articulate why the market is mispricing the catalyst outcome
- Must check: is the catalyst already priced in? (If yes, no edge)
- Log in `domains/XX/research/` with catalyst analysis

## Expected Edge

Markets are forward-looking but imperfect. They often:
1. Underweight scheduled events that seem routine (Fed meetings when "nothing will change")
2. Overweight dramatic but unlikely catalysts (war fears)
3. Misprice conditional chains (if A then B)
4. Slowly price known information (sluggish Bayesian updating)

## What Would Kill This Strategy

- Catalysts are already perfectly priced → no edge, just noise
- My catalyst analysis is wrong → I'm not identifying real catalysts
- Entry timing is off → too early (capital locked) or too late (already priced)

## Metrics to Track

- Same as S001, plus:
- Catalyst type distribution
- Pre-catalyst vs post-catalyst returns
- Hit rate by catalyst type
- "Already priced in" miss rate

## Evolution Hooks

- Which catalyst types have the most edge? Specialize.
- Combine with S002 thresholds for exit management
- Build a catalyst calendar (upcoming events by domain)
- Track "information velocity" — how fast markets price catalysts
