# GEO — Recommended Strategies

*Geopolitics is the single richest domain for multi-strategy deployment.*

## Why GEO Is Prime Hunting Ground

- **Participant quality is lowest where stakes feel highest.** War fears attract scared retail, not calibrated analysts.
- **"By date" market structure creates exploitable time premium.** Fear overprices systematically.
- **Information asymmetry is structural.** OSINT synthesis is available but effortful. Most participants trade on headlines.
- **Liquidity has reached institutional scale.** $155M+ on individual events (Iran strikes). No longer a ghost town.
- **Volatility is extreme and patterned.** Rhetoric spikes → mean reversion is the dominant cycle.

## Strategy Priority (ordered)

### 1. S006 Time Decay — **PRIMARY** (Score: 5/5)

The quantitative backbone. GEO "by date" markets are structurally overpriced.

**Why it works here**: "US strikes Iran by March 31" at 57% with 37 days remaining implies ~2.3% daily hazard rate. Historical base rate for US military strikes on sovereign nations (when tensions elevated): ~0.3%/day. That's 7x overpriced.

**How to deploy**:
- Screen all GEO "by date" markets
- Calculate implied daily probability vs base rate
- Enter when implied > 2x base rate (buy NO)
- Hold to resolution — most resolve NO

**Watch for**: Genuine escalation signals (troop mobilization, carrier deployment) that invalidate the base rate assumption.

### 2. S004 Contrarian Overreaction — **PRIMARY** (Score: 5/5)

The tactical entry signal. GEO produces the most dramatic emotional spikes.

**Why it works here**: A single bellicose speech, a drone incident, or a satellite image leak can move markets 15-20% in 24h. These moves consistently overshoot — rhetoric ≠ action, and the market knows this 48h later.

**How to deploy**:
- Monitor for 15%+ moves in 24-48h on single events
- Classify: structural change (war declared, missiles launched) vs emotional spike (rhetoric, rumors)
- If emotional: fade after 24-48h, target 50% retracement
- 14-day time limit

**Watch for**: Cascading events where the spike was the beginning, not the overreaction.

### 3. S008 Information Edge — **CORE** (Score: 5/5)

The conviction multiplier. OSINT research translates directly to sizing confidence.

**Why it works here**: Geopolitics has the highest information asymmetry of any domain. Military logistics, diplomatic cables, satellite imagery, budget allocation data, and historical precedent analysis are publicly available but require synthesis effort (Type A edge). Base rate research (Type B) is extremely powerful here because base rate neglect is the dominant bias.

**How to deploy**:
- Build cumulative research in `GEO/research/`
- For each active market: synthesize military posture + diplomatic signals + historical base rate
- Form probability estimate BEFORE checking market price
- If divergence ≥10%, classify edge type and enter
- Document everything

**Watch for**: Overconfidence in your model. Government insiders (info Type D/speed) will occasionally know things you can't.

### 4. S002 Threshold Exit — **TACTICAL** (Score: 5/5)

Captures volatility. GEO markets swing enough to hit profit-taking thresholds regularly.

**Why it works here**: GEO volatility means 50% profit targets hit within days on rhetoric-driven swings. Rather than holding all positions to resolution (S001), S002 locks in gains on the volatile ones.

**How to deploy**:
- Apply S002b (1.5x profit / -40% stop) as default
- Consider S002c (2.0x / -50%) for GEO specifically — wider thresholds match wider swings
- Momentum override: if price moves 15%+ in your direction in 24h, tighten stop to breakeven

**Watch for**: Whipsaws on multi-day escalation arcs.

### 5. S007 Cross-Market Arb — **STRUCTURAL** (Score: 4/5)

Nested deadline arbs. GEO has the best Type 2 (temporal consistency) arb terrain.

**Why it works here**: "Iran strikes by March" at 18%, "by June" at 57%, "by December" at 66%. These must be monotonically increasing. If they're not, or if the implied conditional probabilities are inconsistent, free edge.

**How to deploy**:
- Daily: check temporal consistency of nested "by date" series
- If "by [earlier]" > "by [later]" → pure arb, enter both sides
- If implied conditional rates are inconsistent → impure arb, take the more confident side

**Watch for**: Resolution criteria differences between seemingly linked markets.

## Strategies to Skip in GEO

- **S005 Momentum (3/5)**: Escalation ladders create trends, but distinguishing a genuine trend from a rhetoric spike is the hardest classification problem. If uncertain between S004 and S005 in GEO, default to S004 — overreaction is more common than sustained escalation.
- **S001 Hold (4/5)**: Works fine as baseline but S002 dominates in GEO's high-volatility environment. Use S001 only as a benchmark.

## The GEO Playbook in Practice

```
1. SCAN: Check all GEO "by date" markets daily
2. MATH: For each, calculate implied daily prob vs base rate (S006 screen)
3. RESEARCH: For interesting candidates, do OSINT synthesis (S008)
4. WAIT: If no rhetoric spike, enter on S006 math alone (buy NO)
5. SPIKE: If 15%+ rhetoric spike, S004 trigger → fade after 24-48h
6. SIZE: S008 conviction determines position size (3-8% bankroll)
7. EXIT: S002 thresholds for volatile positions; hold-to-resolution for high-conviction
8. ARB: Weekly check for temporal inconsistencies (S007)
```

## Current Opportunities (as of 2026-02-23)

- **Iran strikes**: by Feb 28 (18%), by Mar 31 (57%), by Jun 30 (66%). Prime S006 + S007 terrain.
- **Venezuela**: Regime vs opposition outcome markets. S008 info edge opportunity.
- **Escalation theatres**: Ukraine, Taiwan. Watch for S004 rhetoric spike triggers.
