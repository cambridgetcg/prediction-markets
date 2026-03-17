# Calibration Dashboard

*Last updated: 2026-03-08 (Weekly calibration review — Iran resolutions added)*

## Overall Stats

| Metric | Value |
|--------|-------|
| Total predictions | 15 |
| Resolved | 15 |
| Brier score (mine) | **0.222** |
| Brier score (market) | **0.310** |
| Beat market rate | **9/15 (60%)** |
| Average edge (when beating) | +19.1pp |
| Average miss (when losing) | varies |

## By Outcome

| Outcome | Count | My Brier | Market Brier | Beat Rate |
|---------|-------|----------|-------------|-----------|
| YES | 10 | 0.209 | — | 4/10 (40%) |
| NO | 5 | 0.248 | — | 5/5 (100%) |

**Key insight**: Strong on NO predictions (100% beat rate), weak on YES calibration (40%). Pattern confirmed across two domains (POL SOTU + GEO Iran). YES underestimation is the primary calibration failure.

## By Domain

| Domain | Predictions | Resolved | Brier | Beat Market | Notes |
|--------|------------|----------|-------|-------------|-------|
| POL | 12 | 12 | 0.230 | 75% | SOTU batch |
| GEO | 3 | 3 | 0.190 | 0% | **All 3 lost to market** — systematic contrarian underestimation |
| ECO | 0 | 0 | — | — | pred-0004 resolves Mar 18 |
| CRY | 0 | 0 | — | — | pred-0008 pending (EOY) |

## Resolution Speed Metrics

| Source | Resolutions | Time | Rate |
|--------|-------------|------|------|
| SOTU batch (retro) | 12 | 1 day | **12.0/day** |
| Paper positions | 0 | 2+ months | 0.0/day |
| Live positions | 0 | 3 days | 0.0/day (T008/T009 pending) |

**Calibration bottleneck**: 100% of calibration data comes from retrospective analysis, 0% from live trading. Fast-resolution pipeline (R04) designed to fix this.

## Calibration Curve

| Confidence Bucket | Predictions | Correct | Observed Rate | Calibrated? |
|-------------------|-------------|---------|---------------|-------------|
| 0-20% | 4 | 1 (YES) | 25% | ~OK (small N) |
| 20-40% | 2 | 2 (YES) | 100% | Underconfident? (N=2) |
| 60-80% | 3 | 2 | 67% | ~OK |
| 80-100% | 3 | 2 | 67% | Overconfident? |

**Need 50+ predictions to draw meaningful calibration curve.** Current N=12 is insufficient for bucketed analysis.

## Prediction Detail

| # | Question | My Est | Market | Outcome | My Brier | Mkt Brier | Beat? |
|---|----------|--------|--------|---------|----------|-----------|-------|
| 1 | Trump says "Fake News" | 0.15 | 0.52 | NO | 0.023 | 0.270 | YES |
| 2 | Trump says "MAGA" | 0.35 | 0.87 | NO | 0.123 | 0.757 | YES |
| 3 | Trump mentions China | 0.75 | 0.93 | NO | 0.563 | 0.865 | YES |
| 4 | Trump says "Middle East" | 0.70 | 0.92 | NO | 0.490 | 0.846 | YES |
| 5 | Trump says "Crypto/Bitcoin" | 0.20 | 0.40 | NO | 0.040 | 0.160 | YES |
| 6 | Trump says "Fentanyl/Cocaine" | 0.90 | 0.80 | YES | 0.010 | 0.040 | YES |
| 7 | Trump mentions Iran | 0.98 | 0.96 | YES | 0.000 | 0.002 | YES |
| 8 | Trump says "Hockey" | 0.97 | 0.95 | YES | 0.001 | 0.003 | YES |
| 9 | Trump says "No No No" | 0.25 | 0.30 | YES | 0.563 | 0.490 | **NO** |
| 10 | "Hottest" in SOTU | 0.60 | 0.85 | YES | 0.160 | 0.023 | **NO** |
| 11 | Obama named in SOTU | 0.15 | 0.20 | YES | 0.723 | 0.640 | **NO** |
| 12 | SOTU 100+ minutes | 0.75 | 0.70 | YES | 0.063 | 0.090 | YES |

## Known Biases (Updated with Evidence)

- **Anchoring**: Less than market (avg edge +19pp when beating). SOTU-specific knowledge provided strong deanchoring.
- **Availability**: Not yet measurable (need cross-domain data).
- **YES underestimation**: 3/3 misses were on YES outcomes. Pattern: underestimating Trump's improvisational/boasting vocabulary.
- **NO overconfidence**: 7/7 NO predictions beat market. Strong at identifying what WON'T happen. Risk: this may not generalize outside SOTU-type word markets.

## Path to 50 Resolutions

| Source | Expected Resolutions | Timeline |
|--------|---------------------|----------|
| Current paper portfolio | ~4 (T003/T005 Mar 31, T007/T008 EOY) | 1-10 months |
| Live portfolio | ~2 (LT002 Feb 28, LT003 Mar 3) | 3-6 days |
| S011 rotation fund | ~6/month | Ongoing |
| Monthly Trump batches (calibration-only) | ~20-40/month | End of each month |
| FOMC/data releases | ~2/month | Ongoing |
| Oscars Mar 15 | ~5-10 | 18 days |
| **Projected total by Apr 30** | **~50-80** | **~60 days** |

**The fast-resolution pipeline makes 50 resolutions achievable by end of April**, vs. ~2027 at the current portfolio rate.

## Improvement Protocol

When a prediction resolves wrong and I was >10% off:
1. Log in `lessons.md`
2. Identify which mental model failed
3. Update domain `context.md` if the model needs revision
4. Feed into Ouroboros loop as a sense entry
