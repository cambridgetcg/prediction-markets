# Strategy Lineage

*The family tree of strategies. Every strategy has ancestry and offspring.*

## Generation 0 — The Founding Eight

```
S001 Hold to Resolution ──── baseline, control
S002 Threshold Exit ──────── risk management variant of S001
S003 News Catalyst ───────── event-driven, forward-looking
S004 Contrarian ──────────── mean reversion, fades spikes
S005 Momentum ────────────── trend following, rides waves
S006 Time Decay ──────────── structural, sells overpriced time premium
S007 Cross-Market Arb ────── structural, exploits inconsistencies
S008 Information Edge ────── research-driven, the meta-strategy
```

## Generation 1 — The Structural Exploiters (2026-02-23)

```
S009 Resolution Arbitrage ── oracle risk overlay (born from platform mechanics research)
S010 Whale Signal ────────── on-chain confirmation signal (born from Polygon transparency)
S011 High-Prob Bond ──────── capital management yield (born from documented profit models)
S012 LLM Ensemble ────────── AI-native screener (born from forecasting literature)
S013 Temporal Spread ─────── nested deadline arb (born from S007 + GEO domain)
S014 Geo-Restriction Edge ── local knowledge asymmetry (born from S008 + EU ban structure)
```

## Relationships

```
S001 (Hold)
 ├── S002 branches off (adds exit rules)
 └── is baseline for ALL strategies

S003 (Catalyst) + S004 (Contrarian) = potential hybrid
 └── "Fade the overreaction to a catalyst that was already priced in"

S004 (Contrarian) ←→ S005 (Momentum) = natural tension
 └── Classification skill: is this a spike or a trend?

S006 (Time Decay) + S004 (Contrarian) = potential hybrid
 └── "By date" market spikes on rhetoric → double signal to sell YES

S008 (Info Edge) = meta-strategy that feeds all others
 └── Domain knowledge determines quality of every other strategy's entries

S007 (Arb) ──► S013 (Temporal Spread)
 └── S007 Type 2 (temporal consistency) made systematic for nested deadline markets

S008 (Info Edge) ──► S014 (Geo-Restriction Edge)
 └── S008 specialized for markets where EU/local traders are blocked

S008 (Info Edge) ──► S012 (LLM Ensemble)
 └── AI scales S008 research capacity 10-100x; screens hundreds of markets

S009 (Resolution Arb) = overlay on ALL strategies
 └── Assess oracle ambiguity risk before any trade entry

S010 (Whale Signal) = confirmation overlay
 └── On-chain whale direction + your thesis = convergence → size up

S011 (High-Prob Bond) = idle capital deployment
 └── Between S006/S004/S008 trades, rotate bankroll into yield
```

## Evolution Rules

### Birth
A new strategy is born when:
- Meta-analysis reveals a consistent pattern not captured by existing strategies
- Two strategies show complementary strengths (hybrid offspring)
- A strategy is profitable in one domain but not others (domain-specialized offspring)
- A parameter variant consistently outperforms the parent (mutation)

### Naming
- Direct offspring: S001a, S001b, S001c
- Hybrids: S009 (S003+S004), S010 (S006+S004)
- Domain specialists: S001-GEO, S001-CRY
- Generation 2+: sequentially numbered from S009

### Death
A strategy is retired when:
- 20+ trades with negative ROI
- Sharpe ratio < 0 after 30+ trades
- A direct descendant strictly dominates it
- The market condition it exploits no longer exists

### Retirement Protocol
1. Document final stats in strategy file
2. Move playbook to `playbooks/retired/`
3. Record cause of death in lineage.md
4. Extract lessons into `evolution/meta-lessons.md`
5. Check: did any offspring inherit its weaknesses?

## Generation Log

| Gen | Strategy | Born From | Status | Notes |
|-----|----------|-----------|--------|-------|
| 0 | S001-S008 | Original design | NIGREDO | All untested (S006 advanced to ALBEDO) |
| 1 | S009 | Platform mechanics research | NIGREDO | Oracle risk overlay |
| 1 | S010 | Polygon on-chain transparency | NIGREDO | Whale confirmation signal |
| 1 | S011 | Documented profit models (ChainCatcher) | NIGREDO | Idle capital yield |
| 1 | S012 | AI forecasting literature (Halawi, AIA Forecaster) | NIGREDO | **Priority — highest leverage** |
| 1 | S013 | S007 + GEO nested deadlines | NIGREDO | Temporal arb extension |
| 1 | S014 | S008 + EU Polymarket ban structure | NIGREDO | **Priority — already practicing** |

## Graveyard

*None yet. Every death teaches.*
