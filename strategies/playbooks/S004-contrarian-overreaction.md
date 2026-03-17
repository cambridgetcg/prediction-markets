# S004 — Contrarian Overreaction

**Phase**: ALBEDO (backtest complete, paper trading ready)
**Type**: Mean reversion
**Edge hypothesis**: Markets overreact to news. When a market moves sharply on a single event, the move often partially reverses as emotions cool and base rates reassert.
**Backtest**: `strategies/backtests/S004-overreaction-backtest.md` (2026-02-23)
**Screener**: `scripts/spike-detector.py`

## Why This Exists

Prediction markets are populated by humans (and bots mimicking humans). Humans systematically overreact to:
- Dramatic events (**availability bias** — Tversky & Kahneman 1974)
- Recent events (**recency bias**)
- Events that confirm narratives (**partisan motivated reasoning** — Becker 2025)
- Low-probability high-drama scenarios (**probability weighting** — Kahneman & Tversky 1979)
- YES-side outcomes (**documented "Yes" bias** — Reichenbach & Walther 2025)

**Quantified evidence**: 58% of Polymarket presidential markets show negative serial correlation (Clinton & Huang 2025). Markets revert ~40% of a shock within 7 days (Augenblick et al. 2025). 70% of Polymarket traders lose money (Reichenbach & Walther 2025).

## Rules

### Trigger
- A market moves **≥10% in 24h** OR **≥20% in 7 days**
- Weekly drift is more reliably emotional than daily spikes (backtest finding)
- Minimum $200K total volume, $50K 24h volume
- **ECI Trigger (B01)**: When Emotional Charge Index ≥ 7 AND market moves ≥10%, classify as emotional overreaction. When ECI < 4 AND market moves ≥10%, classify as likely structural — do NOT fade. ECI 4-6 is ambiguous — run classification checklist below for tiebreak. See `psychology/behavioral-foundations.md` Section 4 for full ECI scoring.

### Analysis (before entry)

**Run the classification checklist:**

| Question | Structural (+) | Emotional (+) |
|----------|----------------|---------------|
| Did a verifiable event occur? (election, law, data release) | +3 | +0 |
| Is the source a single tweet, rumor, or unnamed official? | +0 | +2 |
| Did the move happen during low-liquidity hours? | +0 | +1 |
| Was volume >3x average for the day? | +1 | +0 |
| Is the move in the same direction as pre-existing trend? | +2 | +0 |
| Did multiple unrelated markets move the same way? | +2 | +0 |
| Is this a "by date" market with date approaching? | +0 | +1 |
| Does the base rate support the new price? | +2 | +2 |

**Decision**: Structural ≥ 5 → SKIP. Emotional ≥ 4 → FADE. Mixed → HALF-SIZE or SKIP.

### Entry
- Fade the move (bet against it) if classification = EMOTIONAL
- Enter **24-72h** after the spike (let initial panic settle; reversion peaks around 48-72h)
- **Prefer fading YES spikes** (documented Yes bias means YES overreaction is more common)
- **Prefer entering during low-liquidity windows** (weekends, 21:00 UTC) when mispricing peaks
- Size: **3% of bankroll** (high-confidence, emotional score ≥ 6)
- Size: **1.5% of bankroll** (moderate confidence, score 4-5)
- Size: **1% of bankroll** (first paper trades / learning phase)

### Exit
- **Target**: **40% retracement** of the original spike (not 50% — evidence shows ~40% is typical max)
  - Market was at 30%, spiked to 60% → target exit at 48% (30% spike × 40% = 12% retracement)
- **Trailing exit**: After 30% retracement achieved, trail at 50% of gains
- **Time limit**: **7 days** hard cutoff (most reversion happens in days 1-7; holding past day 7 adds risk without proportional return)
- **Stop**: If market continues **8%** further in the spike direction, exit (classification was wrong)

### Do NOT Fade

- Genuine resolution events (election outcomes, court rulings, confirmed data)
- Cascading events (one event triggers another)
- Markets already trending in that direction before the spike
- Markets with very thin liquidity (<$200K total volume)
- ECO or FIN domain markets (too efficient — zero emotional spikes observed)
- Extreme prices (>90% or <10%) — usually structural

### Domain Restrictions (Added 2026-02-25, Scorecard L07)

**GEO CAUTION**: Geopolitical risk is persistent and path-dependent. Military buildups, diplomatic crises, and war threats do NOT fully mean-revert like debate gaffes or crypto FUD. For GEO markets:
- Require ECI ≥ 7 (not 5-6) — only clear emotional overreactions
- Classification score must be unambiguous (emotional ≥ 6, structural ≤ 2)
- Prefer markets with a specific de-escalation catalyst identified (e.g., scheduled talks)
- Do NOT apply S004 to sustained crisis pricing — if a GEO market has been elevated for >7 days, it may be correctly priced, not overreacting

**Best domains for S004**: POL (debate gaffes, partisan panic — reverts in 2-4 weeks), CRY (FUD/hype cycles with documented negative autocorrelation), single-event markets with clear emotional trigger (ECI ≥ 5).

## Expected Edge

**Quantified from backtest + literature:**
- Win rate: ~60% (estimated from reversion rates + classification accuracy)
- Average win: 40% of spike magnitude
- Average loss: 8% (stop-loss)
- Kelly optimal: ~13%, capped at 3% due to classification uncertainty
- Estimated annual return: 15-30% on deployed capital
- Complementary to S006 (time decay) — both edges can stack on the same market

## Domain Priority

| Priority | Domain | Emotional Spike Fraction | Expected Win Rate |
|----------|--------|--------------------------|-------------------|
| 1 | **GEO** | ~45% | 60-65% |
| 2 | **CRY** | ~30% | 55-60% |
| 3 | **POL** | ~50% (small sample) | 55-60% |
| 4 | **OTHER** | ~25% | 50-55% |
| SKIP | **ECO/FIN** | ~0% | N/A |

## What Would Kill This Strategy

- Win rate < 50% over 20+ trades → classification doesn't work
- Average reversion < 20% of spike → edge too small
- Stop-loss hit rate > 40% → markets aren't overreacting, they're repricing
- GEO spike frequency < 2/month → not enough trade opportunities

## Metrics to Track

- Spike classification accuracy (structural vs emotional — target ≥70% correct)
- Average reversion % achieved (target ≥35% of spike)
- Time to reversion (target: majority within 3-7 days)
- Win rate by domain
- Reversion speed by spike source (tweet, official statement, data release)
- Stop-loss hit rate (target < 25%)

## S004 + S006 Synergy

When a time-decay market (S006) experiences a rhetoric spike:
1. S006 identifies the market as overpriced vs. base rates (structural edge)
2. S004 identifies the spike as emotional (tactical entry)
3. Both edges stack — fading an emotional move in an already overpriced market

**Example**: Iran strike by March 31 at 57.5% (S006: implied daily p = 2.3% vs. base rate ~0.3-0.5%). This week's +25% spike on rhetoric (S004: emotional) creates a double-edge opportunity.

## Behavioral Foundation (B01 + B02 Integration)

This strategy exploits the compound of multiple cognitive biases documented in `psychology/behavioral-foundations.md`:

**Primary biases exploited**: Availability heuristic, salience bias, fear premium, herding/social proof, FOMO, narrative fallacy, recency bias.

**Compound patterns**: War Panic Premium (GEO), Narrative Cascade (CRY/POL), Partisan Echo Chamber (POL).

**Key insight from B01**: The ~40% retracement target is explained by belief perseverance — initial beliefs persist even after evidence is discredited, preventing full reversion. The 40% ceiling is not arbitrary but reflects documented psychological limits on correction.

**ECI scoring dimensions**: Fear Factor, Vividness, Narrative Coherence, Identity Activation, Recency Shock, Media Amplification (each 1-10, average = ECI).

### Taxonomy-Based Trigger Enhancement (B02)

The news taxonomy (`psychology/news-emotion-price-taxonomy.md`) maps each news subcategory to its expected emotional response and optimal entry window. Use this for faster classification:

| If the spike is caused by... | Category | Expected Overpricing | Optimal Entry Window | Confidence |
|------------------------------|----------|---------------------|---------------------|-----------|
| Military buildup (no ultimatum) | A1 | +5-15pp | During buildup | High — if no ultimatum, market overprices |
| Ultimatum / deadline rhetoric | A2 | +10-25pp | 24-72h post-ultimatum | High — but check if backed by force posture |
| Diplomatic breakdown | A3 | +5-12pp | When new round is scheduled | Moderate — check if mediators still engaged |
| Strike on secondary markets | A4 | +15-30pp | 6-24h post-strike | High — secondary markets systematically overreact |
| Single poll result | B1 | +3-8pp | 24-48h post-poll | Moderate — aggregate overwrites single poll |
| Debate "knockout" moment | B4 | +5-15pp | 24-72h post-debate | High — debates have 1-3pp actual vote impact |
| Tariff escalation announcement | C5 | +3-10pp | 12-48h post-announcement | Moderate — implementation discount |
| Protocol hack (on unrelated crypto) | D1 | +5-15pp | 6-24h post-hack | High — contagion is emotional not fundamental |
| Influencer tweet (Musk etc.) | D4 | +3-15pp | 4-12h post-tweet | Highest — most reliably overpriced |
| New AI model release (on "best model") | E1 | +3-10pp | 24-48h post-release | Moderate — Arena requires weeks to settle |

### Negative-Positive Asymmetry (B02 Finding)

Negative news produces LARGER and FASTER spikes than positive news (2.4:1 magnitude ratio, ~5x faster to peak). **Implication**: The highest-EV S004 trades are fading NEGATIVE news spikes. Positive news produces smaller, slower moves that don't create clean S004 entry points.

### ECI Validation from Live Data

From our N=20 sample (T001-T008 + SOTU batch):
- **ECI ≥ 7**: 1/1 correctly classified as emotional (T003). S004 entry validated.
- **ECI 4-6**: 8/10 correctly identified (SOTU). Average gap: 14.3pp. These are ALSO tradeable.
- **ECI < 4**: 1/1 correctly identified as structural (T004). SKIP validated — avoiding T004 would have saved -17.5%.

**Domain-specific ECI thresholds** (from B02 participant profiles):
- **GEO**: ECI ≥ 6 sufficient (high-emotion participant base)
- **CRY**: ECI ≥ 6 sufficient (FOMO-driven participants)
- **POL**: ECI ≥ 5 for identity-charged markets (partisan echo chamber amplifies even moderate ECI)
- **TEC**: ECI ≥ 7 (more analytical participants — need higher charge to overreact)

## Evolution Hooks (Validated)

- **GEO overreacts most to rhetoric** — CONFIRMED (45% emotional spike fraction)
- **Optimal entry: 24-72h post-spike** — CONFIRMED (reversion peaks at 48-72h)
- **Weekly drift > daily spikes for S004** — CONFIRMED (daily spikes often structural/resolution)
- **Combine with S006** — CONFIRMED (stacking edges on GEO "by date" markets)
- **Track spike sources** — TODO (need more data on which news sources cause most overreaction)
- **Weekend/off-hours entry** — PROMISING (retail-dominated, more mispricing)
