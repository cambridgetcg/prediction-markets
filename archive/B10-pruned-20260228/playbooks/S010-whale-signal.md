# S010 — Whale Signal

**Phase**: ALBEDO (research complete, registry populated, monitoring scaffolded — ready for paper trading integration)
**Type**: Signal modifier / Confirmation overlay
**Edge hypothesis**: On-chain visibility of historically profitable wallets provides a confirmation signal. When a tracked whale's directional bet aligns with our independent estimate, conviction increases. S010 is a MODIFIER — it amplifies S004, S006, S008 signals. It never replaces them.

## Why This Exists

All Polymarket trades settle on Polygon. Every trade is a public on-chain event. The top 0.04% of traders capture >70% of all profits ($3.7B from 1.73M addresses). Their wallets are permanently recorded, indexable, and identifiable by P&L, trade frequency, domain specialization, and timing.

**The edge hierarchy** (documented in what-doesnt-work.md:440-449):
- Theo ($85M): commissioned private polling — pure information advantage
- zxgngl ($29M): extreme POL expertise, 10-30 trades/year, extreme conviction
- Axios (96% win rate): Trump-market specialist, unknown methodology
- Domer (#1 by volume): 5,000+ markets, manual "slow motion poker"
- AlphaRaccoon ($1.36M): 22/23 on Google markets — suspected insider
- ricosuave666: 100% win rate on Israel bets — possible GEO insider
- aenews2 ($4.35M): news trader, 72.9% win rate across 1,954 bets
- scottilicious ($1.35M): PhD Political Science, 84.1% win rate

**These people are still trading.** Their signal is still visible.

## The Critical Anti-Pattern

**Blind copying kills.** zxgngl earned $29M in political markets, then lost $3.6M copying into Tyson vs. Paul (sports — zero domain expertise). Domain matters more than wallet track record (what-doesnt-work.md:97-99).

S010 exists to prevent this: the signal only activates when the whale trades in their documented specialization AND your independent thesis agrees.

## Signal Classification

When a whale trade is detected, classify it:

### Type A — Confirmation
Your independent estimate agrees AND whale agrees in their specialization domain.
**Action**: Size up existing position by 50%.

### Type B — Entry Trigger
You've been watching a market but hadn't entered. Whale enters same direction in their domain.
**Action**: Enter at standard size. The whale provides the timing catalyst.

### Type C — Contradiction
Your estimate disagrees with whale direction.
**Action**: Investigate further. Do NOT automatically follow. The whale may have information you don't — or you may be right and they're wrong.

### Type D — Unknown Domain
Whale is trading outside their documented specialization.
**Action**: Lower follow confidence. Monitor but don't act. This is the zxgngl-on-Tyson failure mode.

### Type E — Suspicious
Trade right before news, unusual wallet behavior, front-running pattern.
**Action**: Investigate immediately. Consider following fast if pattern matches front-running criteria (see Section 6). Could be inside information OR could be manipulation.

## Entry Rules

### Signal Activation Criteria (ALL must be met)

1. **Independent estimate exists**: You have your own probability estimate from S004/S006/S007/S008 research BEFORE seeing the whale trade
2. **Domain match**: The whale's trade is in their documented specialization (per whale-registry.json)
3. **Size threshold**: Trade is >$5K (minimum signal), ideally >$25K (high conviction)
4. **Directional consistency**: No recent pattern of trades in opposite direction (not hedging)
5. **Timing sense**: Not within 1 hour of resolution (that's mopping up, not signal)

### Sizing Rules

| Signal Type | Action | Sizing |
|-------------|--------|--------|
| Type A (Confirmation) | Size up existing position | +50% of original position |
| Type B (Entry trigger) | New entry | Standard strategy sizing (per S004/S006/S008 rules) |
| Type C (Contradiction) | Investigate, don't follow | No new position. Document findings. |
| Type D (Unknown domain) | Monitor only | No position |
| Type E (Suspicious) | Investigate + possibly follow | If following: half standard size (risk of manipulation) |

### Maximum Whale-Attributed Sizing

S010 amplification can never push total position beyond **8% of bankroll** per market (2x the standard 4% cap). The whale signal adds conviction, not recklessness.

## Exit Rules

- **Primary**: Exit per the underlying strategy (S006 time decay, S004 reversion target, S008 thesis invalidation)
- **Whale exit signal**: If the tracked whale exits the same market → investigate why. Don't blindly follow the exit, but treat it as an information event that requires thesis re-evaluation.
- **Whale contradiction**: If the whale who confirmed your position later takes the opposite side → exit or significantly reduce position

## Whale Identification Criteria

What makes a wallet worth tracking (per research/whale-signal-research.md):

### Must-Have
1. **Documented profitability**: Positive realized P&L over >20 trades (not lucky streaks)
2. **Identifiable domain pattern**: Consistent trading in 1-3 domains, not random
3. **Non-wash-trading**: Activity pattern inconsistent with known wash trading signals (14% of wallets flagged per Columbia study)

### Nice-to-Have
4. **Known identity or methodology**: Understanding WHY they're profitable increases signal quality
5. **Active in 2026**: Wallet has traded in the last 90 days
6. **HashDive Smart Score >50**: Independent third-party validation (though methodology is proprietary)

### Disqualifiers
- Win rate >90% with <20 trades (likely luck, not skill)
- Profits concentrated in a single large bet (survivorship bias)
- Wallet shows bot-like patterns (sub-second execution, uniform sizing) — bots exploit speed, not information
- Wallet associated with known wash trading clusters

## Whale Timing Interpretation

| Window | Interpretation | Follow Signal |
|--------|---------------|---------------|
| 7-30 days pre-resolution | Informed but patient — likely research/OSINT-based | Standard follow (Type A/B) |
| 3-7 days pre-resolution | Elevated confidence — closer to information | Strong follow signal |
| 24-48h pre-resolution | High conviction or information edge | Follow with caution (may be priced in) |
| Day of resolution | Mopping up stale prices | Only follow if market is genuinely stale |

**Theo's documented pattern**: Entered ~7 days before election day when private polling diverged from public polls. His entry BEFORE public polls moved was the signal.

## Front-Running Detection

A separate but related edge: identifying when a market is being front-run by an insider BEFORE you trade.

### The Pattern

Insider (political staffer, corporate executive, government official) knows outcome before public:
1. They enter quietly 24-48h before announcement
2. Price drifts 3-8% in their direction WITHOUT corresponding news
3. Volume is below average (quiet, deliberate — not a news reaction)
4. Public announcement → price jumps 20-40%

### Detection Criteria (ALL must be met)

1. Market has a known upcoming announcement (election day, FOMC, company earnings, diplomatic meeting)
2. Price is moving 4-8% in a specific direction without news catalyst
3. Move started 24-72h before announcement (consistent with insider timing)
4. Volume is below average (not a public reaction)
5. Move direction aligns with your independent estimate (confirmation, not contradiction)

### How This Differs from S004

- **S004**: Large move WITH news → fade the overreaction (mean reversion)
- **Front-run detection**: Small move WITHOUT news → follow the informed flow (momentum)

These are opposite strategies triggered by opposite conditions.

### The Risk

The insider might be wrong. Or it might be random noise. Or wash trading. Or someone else front-running a false lead. Never rely solely on this signal.

### Legality

No SEC-equivalent insider trading rules apply to prediction markets. CFTC has not brought insider trading cases on Polymarket (what-doesnt-work.md:391-395). Polymarket's CEO explicitly says insider trading improves market efficiency.

Ethically: following price signals from unknown sophisticated traders is standard practice in all markets — equivalent to using order flow as a signal in equity trading.

## Monitoring Infrastructure

### Recommended Stack (free tier)

| Tool | Purpose | Status |
|------|---------|--------|
| **PolyTrack** (polytrackhq.app) | Cluster detection, category filtering, webhooks | Active, free (3 wallets) / $19/mo |
| **HashDive** (hashdive.com) | Smart Scores (-100 to +100), bot detection | Active, free (no API) |
| **Polywhaler** (polywhaler.com) | $10K+ trades, insider score 0-100 | Active, free / Pro $10/mo (API) |
| **PolyMonit** (polymonit.com) | Telegram/email alerts, filtered by wallet | Active, free |
| **Arkham Intelligence** | Entity labeling (800M+ addresses), API | Active, free tier |
| **PolymarketAnalytics.com** | 1M+ trader search, leaderboard, P&L | Active, free |
| **pselamy/polymarket-insider-tracker** | DBSCAN insider detection (60 commits) | GitHub, Docker |
| **whale-monitor.py** (custom) | Registry polling + signal dashboard | scripts/whale-monitor.py |
| **Unusual Whales Predictions** | Options-style flow analysis for prediction markets | Active |

### Contract Addresses (Polygon Mainnet)

- CTF Exchange: `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E`
- Neg Risk CTF Exchange: `0xC5d563A36AE78145C45a50134d48A1215220f80a`
- Neg Risk Adapter: `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296`
- Conditional Tokens: `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045`

### Alert Protocol

When whale-monitor.py or Polywhaler detects activity:
1. Check: Is this wallet in whale-registry.json?
2. Check: Is this trade in the whale's documented domain?
3. Check: Do we have an independent estimate for this market?
4. Classify: Type A/B/C/D/E
5. Act: Per sizing rules above

## Risk Factors

### Known Risks
1. **Wash trading contamination** (25% of volume may be fake per Columbia study): Whale trades could be fake volume. Cross-reference with PolyTrack cluster analysis.
2. **Identity confusion**: Multiple wallets may belong to same entity (Theo had 11 accounts). PolyTrack cluster detection mitigates this.
3. **Context misread**: Whale may be hedging, not expressing a directional view. Check for opposite-direction trades in related markets.
4. **Stale registry**: Whale strategies evolve. Quarterly review of whale-registry.json required.
5. **Herding risk**: If many people follow the same whales, the follow signal gets arbitraged away. We're early but this edge will compress.

### What Would Kill This Strategy
- Whale wallets become randomized (privacy tech on Polygon) → signal disappears
- All profitable traders move to private execution (dark pools) → no observable flow
- Whale tracking becomes so popular that follow-trades move prices before we can enter → edge compressed
- The whales we track have a losing streak → our confirmation signal becomes noise

## Integration with Other Strategies

S010 is a **modifier**, never standalone:

| Base Strategy | S010 Integration |
|---------------|-----------------|
| **S004 (Contrarian)** | After spike detected, check if any whale is entering the fade direction → Type A confirmation, size up |
| **S006 (Time Decay)** | When screening "by date" markets, check if whales are already positioned NO → Type B entry trigger |
| **S007 (Cross-Market Arb)** | When overround detected, check if whales are exploiting the same mispricing → conviction boost |
| **S008 (Info Edge)** | When research yields an edge estimate, check if informed whales are positioned similarly → strongest confirmation |

## Expected Edge

The edge from S010 is NOT alpha generation — it's **conviction calibration**. If our independent estimate is correct, whale confirmation should improve our sizing accuracy. If our estimate is wrong, whale contradiction is an early warning.

Expected impact: 0-3% improvement in annualized return via better sizing, with primary value in **avoided losses** from Type C contradiction warnings.

## Data Requirements

- `data/whale-registry.json` — Target wallet list (maintained quarterly)
- `scripts/whale-monitor.py` — Polling + signal dashboard
- Polygonscan API key (free tier: 5 req/s)
- PolyTrack account (free)
- HashDive account (free)
- Polywhaler bookmarks / Telegram alerts

## Registry Summary (Feb 2026)

15 wallets in `data/whale-registry.json`:
- **GEO specialists**: ricosuave666 (100% Israel win rate), denizz (Middle East), Cashy (Israel-based), BuckMySalls ($920K)
- **POL specialists**: Theo4 ($22M), Fredi9999 ($16.6M), aenews2 ($4.35M), scottilicious ($1.35M, 84% win rate), debased ($1.51M), YatSen ($2.21M)
- **TEC specialist**: AlphaRaccoon ($1.36M, address confirmed)
- **ECO lead**: crudeoilmoney (unconfirmed P&L — best available ECO lead)
- **Generalists**: Domer ($2.6M), Whale-A ($958K)
- **GEO/POL**: MEPP (top 100, unconfirmed P&L)

### GEO Gap Status: FILLED
Previously zero identified GEO-specialist wallets. Now 4 confirmed addresses with Middle East/Iran focus. ricosuave666 is the highest-signal wallet for T001/T003/T005 positions.

### ECO Gap Status: PARTIALLY FILLED
crudeoilmoney is the only lead. Consistent with finding that ECO is "perfectly priced" — no individual ECO whales have been profiled publicly. Any ECO-profitable wallet found in future warrants maximum follow-confidence.

## Evolution Hooks

- Track follow-trade P&L separately from base strategy P&L (isolate S010's contribution)
- Build wallet scoring model: which tracked wallets actually improve our decisions?
- Set up PolyTrack free tier: track ricosuave666, denizz, Cashy as the 3 free wallet slots (all GEO)
- Set up Polywhaler alerts for $10K+ trades on Iran/2028 political/BTC markets
- Quarterly registry review: update P&L, prune inactive wallets, add newly discovered specialists
- Check Polywhaler Pro ($10/mo) API for automated pipeline integration with whale-monitor.py
