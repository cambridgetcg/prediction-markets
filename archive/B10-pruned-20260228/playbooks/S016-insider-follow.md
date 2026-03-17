# S016 — Insider Follow

**Phase**: NIGREDO (framework built, awaiting L01-L03 pipeline data for full activation)
**Type**: Signal modifier / Confirmation overlay (extends S010)
**Edge hypothesis**: Mathematically-identified insiders — accounts with statistically significant, localised edge in specific sub-domains — provide the highest-confidence follow signal. When an insider trades in their dominant field and the signal aligns with our independent thesis, sizing up is justified.

## Why This Exists

S010 (Whale Signal) tracks manually-curated profitable wallets. S016 extends this with the **intelligence pipeline** (L01→L02→L03→L04):

| Layer | Purpose | Output |
|-------|---------|--------|
| L01 | Edge calculation | `data/edge-profiles.json` |
| L02 | Localisation test | `data/insider-registry.json` |
| L03 | Field classification | `data/classified-insiders.json` |
| **L04** | **Follow decision** | **`data/follow-signals.jsonl`** |

S010 asks "is this wallet profitable?" S016 asks "is this wallet's edge *localised* to a specific sub-domain, and are they trading *in that sub-domain right now*?"

The difference matters. zxgngl earned $29M in political markets, then lost $3.6M copying into Tyson vs. Paul. Domain specificity is the fingerprint that separates signal from noise.

## The 4-Gate Decision Framework

Every potential follow signal must pass all 4 gates before action:

### Gate 1 — Field Match (binary, must-pass)

The insider's bet MUST be in their dominant sub-domain. This is the single most important rule.

```
POL-Insider-01 (primary: us-republican-primary) bets on:
  "Vance wins 2028 GOP"     → MATCH ✓ (follow candidate)
  "UK general election"     → NO MATCH ✗ (ignore)
  "Bitcoin $150K"           → NO MATCH ✗ (ignore)
```

**If field doesn't match: DO NOT FOLLOW. End of decision tree.**

### Gate 2 — Direction Check

| Outcome | Action |
|---------|--------|
| AGREE, no position | New entry opportunity → proceed to sizing |
| AGREE, have position | Confirmation → consider adding 25-50% |
| CONTRADICT | Do NOT follow. Investigate. May need to reassess thesis. |
| CONTRADICT + score >= 8.0 | Serious re-evaluation required |

For CONTRADICT signals: do not panic-exit. Run L03-level analysis on the specific market. Reasons an insider might oppose your thesis:
1. They have information you don't → update toward their direction
2. They're hedging real-world exposure in the opposite direction
3. They made an error (even insiders are wrong outside their specialty — but this IS their specialty)
4. Your thesis was already wrong before this signal

### Gate 3 — Timing Quality

| Window | Interpretation | Confidence Modifier |
|--------|---------------|-------------------|
| >30 days | Patient research-based entry | 0.85x |
| 8-30 days | Sweet spot — informed but not day-of | 1.0x |
| 2-7 days | High conviction, possible pre-announcement | 1.15x |
| <48 hours | Mopping up OR day-before insider | 0.5x (check price first) |

### Gate 4 — Price Impact

Has the insider's bet already moved the price?

| Price Movement | Modifier | Interpretation |
|---------------|----------|---------------|
| <1% | 1.0x | Signal not yet priced in |
| 1-5% | 0.9x | Slight move, mostly available |
| >5% | 0.7x | Partially priced in, reduce size |

## Entry Criteria

ALL must be met:
1. **All 4 gates pass** (Gate 1 = match, Gate 2 ≠ CONTRADICT)
2. **ICM >= 0.8** (Insider Conviction Multiplier — see below)
3. **Independent estimate exists** — never enter solely on insider signal
4. **Bankroll caps respected** — ICM amplifies but never overrides risk limits

## Position Sizing

### Insider Conviction Multiplier (ICM)

Multiplier on standard strategy position size:

```
ICM = score_adj × conf_adj × n_adj × timing_modifier

Score adjustment (L02 insider score 0-10):
  <4  → 0.5x    4-6 → 0.8x    6-8 → 1.0x    8+ → 1.25x

Follow confidence (L03 dossier 1-5):
  1 → 0.5x    2 → 0.7x    3 → 1.0x    4 → 1.3x    5 → 1.6x

Sample size:
  N < 20 → 0.8x    20-50 → 1.0x    50+ → 1.1x

Output range: 0.5x to 2.0x standard size (capped)
```

### Bankroll Constraints (from BANKROLL.md)

The ICM multiplies standard size but ALWAYS caps at:
- Max 10% of bankroll per single position
- Max 30% per domain
- Max 40% per strategy
- S016 amplification can never push total position beyond 8% of bankroll per market (2x the standard 4% cap)

### Entry Cases

**Case 1: No existing position**
```
Enter at: current market price
Size: ICM-adjusted standard size (subject to bankroll caps)
Log: "L04 signal — [Insider Alias] — field: [subdomain]"
```

**Case 2: Already have a position, insider agrees**
```
Add: 25-50% of ICM-adjusted size (don't double — you already have exposure)
Cap: total position <= 10% bankroll
Log: "L04 confirmation — adding to [existing trade ID] — [Insider Alias]"
```

## Exit Rules

- **Primary**: Exit per the underlying strategy (S004, S006, S008, etc.)
- **S016 is a modifier, not standalone** — it adjusts conviction and sizing, not trade thesis
- **Whale exit signal**: If insider exits → investigate why, but don't blindly follow exit
- **Whale contradiction**: If insider who confirmed your position later takes opposite side → exit or reduce significantly

## Risk Factors

### Known Risks
1. **Signal already priced in**: Other followers may have moved the price
2. **Insider error**: Even insiders are wrong sometimes
3. **Hedging behavior**: Insider may be hedging real-world exposure, not expressing directional view
4. **False positive from L02**: Lucky bettor looks like insider (managed by sensitivity analysis)
5. **Stale profile**: Insider's edge may have decayed (quarterly registry review required)
6. **Herding risk**: If many follow same insiders, follow-edge gets arbitraged away

### What Would Kill This Strategy
- Whale wallets become randomised (privacy tech on Polygon)
- All profitable traders move to private execution
- Follow-trading becomes so popular that prices move before we can enter
- The L01-L03 pipeline has systematic false positive rates above our threshold

## Anti-Patterns

| Anti-Pattern | Why It Fails | Prevention |
|-------------|-------------|-----------|
| Following outside field match | THE cardinal sin — zxgngl lost $3.6M | Gate 1 is binary, no exceptions |
| Ignoring bankroll caps | ICM tempts oversizing | Caps are hard limits, checked by script |
| Acting on CONTRADICT without investigation | Panic selling destroys returns | Gate 2 routes to INVESTIGATE, not EXIT |
| Using S016 standalone (no independent thesis) | You're just copy-trading | Require independent estimate before following |
| Following <48h signals at full size | Likely already priced in | Gate 3 applies 0.5x modifier |
| Treating all insiders equally | Score 3 ≠ score 9 | ICM adjusts sizing by evidence quality |

## Tools

| Tool | Purpose | Status |
|------|---------|--------|
| `scripts/l04-follow-monitor.py` | 4-gate framework, position cross-check | Built |
| `data/follow-signals.jsonl` | Signal log for performance tracking | Initialised |
| `data/classified-insiders.json` | L03 output (primary data source) | Awaiting L01-L03 |
| `data/whale-registry.json` | Manual whale list (fallback) | Active, 15 wallets |

## Integration with Other Strategies

S016 is a **modifier**, never standalone:

| Base Strategy | S016 Integration |
|---------------|-----------------|
| **S004 (Contrarian)** | After spike, check if classified insider is fading same direction |
| **S006 (Time Decay)** | When screening "by date" markets, check if insiders positioned NO |
| **S007 (Arb)** | When overround detected, check if insiders exploiting same mispricing |
| **S008 (Info Edge)** | Research yields edge estimate → check if insiders positioned similarly |

## Evolution

1. **Track L04 signal performance separately** in P&L — does following insiders actually beat our base rate?
2. **Monthly calibration review** — how many CONFIRM signals were correct? How many CONTRADICT signals were we right to ignore?
3. **Upgrade data source** when L01-L03 pipeline is built — switch from whale-registry to classified-insiders
4. **Integrate on-chain monitoring** — PolyTrack, Polywhaler, Polygonscan for real-time trade detection
5. **Quarterly registry review** — prune inactive wallets, add newly discovered specialists

## Lineage

- **Parent**: S010 (Whale Signal)
- **Data pipeline**: L01→L02→L03→L04
- **Number note**: S012-S015 assigned in `strategies/evolution/new-strategy-research.md` (LLM Ensemble, Temporal Spread, Geo-Restriction, Calendar Patterns). S016 is the next available.
