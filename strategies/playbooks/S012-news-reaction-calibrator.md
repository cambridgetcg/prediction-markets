# S012 — News Reaction Calibrator

**Phase**: NIGREDO (design complete, implementation pending)
**Type**: Reaction calibration (over/underreaction detection)
**Edge hypothesis**: Markets systematically over- or underreact to news events. An LLM can estimate the *rational* probability shift faster and more accurately than the crowd, and the delta between expected and actual market movement creates a tradeable signal.
**Dependencies**: Revived news pipeline (archived B10), spike-detector.py (S004), Gamma API

## Why This Exists

S004 catches overreactions *after* they happen (24-72h delay, backward-looking spike detection). S012 catches them *as they happen* by comparing news content against market movement in near real-time.

The gap in the current system:
- ✅ `spike-detector.py` — finds price spikes (no news context)
- ✅ `brave_ingestor.py` (archived) — collects news (no market matching)
- ✅ S004 playbook — fades overreactions (delayed entry, no underreaction capture)
- ❌ Nothing connects news → expected impact → actual market reaction → trade signal

## Reaction Types

| Type | Delta | Direction | Entry | Target | Time Horizon |
|------|-------|-----------|-------|--------|--------------|
| **OVERREACTION** | actual > expected + 5pp | Against the move | Hours post-news | 40% retracement (S004) | 7 days |
| **UNDERREACTION** | expected > actual + 5pp | With the move | Immediately | LLM posterior estimate | 48h |
| **CORRECT** | |delta| < 5pp | None | No trade | — | — |

## Position Sizing

- **Overreaction** (high confidence, δ ≥ 8pp): 3% bankroll
- **Overreaction** (moderate, 5pp ≤ δ < 8pp): 1.5% bankroll
- **Underreaction** (high confidence, δ ≥ 8pp): 2% bankroll
- **Underreaction** (moderate, 5pp ≤ δ < 8pp): 1% bankroll
- **Max S012 exposure**: 10% bankroll
- Pre-position concentration check (C1-C4) applies

## Domain Restrictions

Same as S004:
- **Best**: POL (partisan panic), CRY (FUD/hype)
- **Good**: GEO (with higher thresholds — δ ≥ 8pp required)
- **Skip**: ECO/FIN (too efficient, no mispricing window)

## Calibration Requirements

Before live:
1. Paper trade 30 signals minimum
2. Track LLM calibration (estimated shift vs actual resolution)
3. Min 60% hit rate on overreaction calls
4. Min 50% hit rate on underreaction calls

## What Would Kill This Strategy

- LLM calibration < 50% on direction
- Average actionable delta < 3pp
- News latency > 30 min (market already moved)
- Insufficient qualifying signals (< 2/week)
