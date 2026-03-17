# Polymarket Resolution Mechanics: Deep Dive

**Research Date**: 2026-02-25
**Status**: COMPLETE
**Relevance**: S004, S006, S007, S008 (all strategies that depend on resolution timing)

---

## 1. MOOV2 (Managed Optimistic Oracle V2)

### What Changed from OOV2

| Feature | OOV2 | MOOV2 |
|---------|------|-------|
| Who can propose | Anyone | **Whitelisted addresses only** |
| Who can dispute | Anyone | Anyone (unchanged) |
| Bond configuration | Fixed | Manager-adjustable via `requestManagerSetBond()` |
| Whitelist controls | None | `setDefaultProposerWhitelist()` + per-request `requestManagerSetProposerWhitelist()` |
| Governance | UMIP standard | **UMIP-189** (passed August 6, 2025) |

### Whitelisted Proposers

- **37 initial whitelisted addresses** announced by Risk Labs
- Composition: Risk Labs employees, Polymarket employees, and users with 20+ proposals and >95% accuracy
- Rationale: Under OOV2, many proposals were submitted prematurely by inexperienced proposers, causing bond forfeiture and resolution delays of up to 4 days
- Anyone can still *tag* a whitelisted proposer to submit on their behalf

### Criticism

- Centralizes proposal authority to a small group
- Critics argue better market rules would solve disputes more effectively than restricting proposers
- MOOV2 passed August 2025 -- directly in response to the Ukraine mineral deal governance attack (March 2025)

**Sources**: [The Block](https://www.theblock.co/post/366507/polymarket-uma-oracle-update), [AInvest](https://www.ainvest.com/news/uma-restricts-resolution-proposers-37-whitelisted-addresses-polymarket-2508/), [CryptoTimes](https://www.cryptotimes.io/2025/08/12/uma-limits-polymarket-resolutions-to-whitelisted-parties-only/), [RocknBlock](https://rocknblock.io/blog/how-prediction-markets-resolution-works-uma-optimistic-oracle-polymarket)

---

## 2. Resolution Timeline: How Markets Actually Resolve

### The 11-Step Flow

```
1. Smart contract requests oracle resolution
2. Whitelisted proposer posts bonded answer ($750 USDC.e)
   └── Fields: identifier, timestamp, claim, currency, bond
3. 2-hour liveness period begins (challenge window)
4a. NO DISPUTE → proposal accepted, market resolves (~2 hours)
4b. FIRST DISPUTE → disputer posts $750 counter-bond
   └── System resets, ignores first dispute (anti-frivolous mechanism)
   └── New proposal requested (~2 additional days)
5. SECOND DISPUTE → escalates to DVM
   └── Commit phase: UMA stakers submit hashed votes (private)
   └── Reveal phase: votes published, tallied
   └── Duration: 48-96 hours
   └── Quorum: GAT (minimum participation) + SPAT (50% agreement)
6. Result returned to smart contract
7. Market settles, trading stops
8. Winners redeem at $1.00 per share
```

### Timing Summary

| Scenario | Duration | Frequency |
|----------|----------|-----------|
| Uncontested | ~2 hours | ~98.5% of all markets |
| One dispute | ~2-3 days | ~1% |
| Two disputes (DVM) | 4-6 days | ~0.5% |
| DVM + complications | Days to weeks | Rare |

### Bond Economics

- **Proposer bond**: $750 USDC.e (typical)
- **Disputer bond**: Same as proposer ($750)
- **If proposer wins**: Gets bond back + 50% of disputer's bond
- **If disputer wins**: Gets bond back + 50% of proposer's bond
- **"Too Early" ruling**: Disputer wins, market stays unresolved
- **"Unknown/50-50"**: Each token = $0.50; disputer gets bond + half

### DVM Voting Mechanics

- **Two-stage commit-reveal** prevents vote coordination
- **Token-weighted** (NOT one-person-one-vote) — large holders dominate
- **Slashing**: Minority voters and non-participants face penalties
- **SPAT**: At least 50% staked token agreement required
- **Critical structural concern**: UMA market cap (~$44M) vs. Polymarket TVL (~$330M) = 15:1 ratio. Controlling the oracle costs a fraction of capital at stake.

**Sources**: [Polymarket Docs](https://docs.polymarket.com/developers/resolution/UMA), [RocknBlock](https://rocknblock.io/blog/how-prediction-markets-resolution-works-uma-optimistic-oracle-polymarket), [DeFi Rate](https://defirate.com/prediction-markets/how-contracts-settle/)

---

## 3. Resolution Timing: Real Examples

### Example 1: 2024 Presidential Election (Clear, Fast — with structural delay)

**Timeline**:
| Time (ET, Nov 5-6 2024) | Event | Trump Price |
|--------------------------|-------|-------------|
| Nov 5, 7:00 PM | Polls close in early states | ~60c |
| Nov 5, ~11:00 PM | Key swing state results flowing | ~85c |
| Nov 6, ~1:45 AM | Fox News calls race for Trump | ~95c+ |
| Nov 6, early AM | Market prices in Trump victory | ~98.8c |
| Nov 6, ~11:00 AM | AP and NBC call the race | ~99c+ |
| Nov 6, ~11:00 AM | Polymarket resolves (minutes after AP/NBC) | $1.00 |

**Key insight**: Market priced Trump at 98.8c by early morning — HOURS before AP/NBC called. Fox called at 1:45 AM but Polymarket required ALL THREE (AP + NBC + Fox) to resolve. Gap between "market knows" and "market resolves" was ~9 hours.

**Trading volume**: $3.6 billion total on presidential contract.

### Example 2: Fed Rate Decisions (Clear, Fast)

- Sep 2024 FOMC: 91% of Polymarket traders correctly predicted 25bp cut. $188M volume.
- Fed markets resolve mechanically — FOMC statement comes at 2:00 PM ET, decision is unambiguous.
- Price snaps to 99%+ within seconds of FOMC statement.
- Proposal typically submitted within minutes; resolves in ~2 hours.
- **Never disputed** — Fed decisions are objectively verifiable.

### Example 3: Ukraine Mineral Deal (Ambiguous, Manipulated — March 2025)

**Timeline**:
| Date | Event |
|------|-------|
| Feb 2, 2025 | Market opens: "Ukraine agrees to Trump mineral deal before April?" |
| Early March | Market trading at ~9% YES |
| Mar 24-25 | Price surges from 9% to 100% |
| Mar 25 | Market resolved as YES despite no official confirmation |
| Mar 25 | Polymarket calls it "unprecedented governance attack" |
| Mar 25 | Single UMA whale with 3 accounts, 5M tokens controlled ~25% of vote |
| Post-resolution | Polymarket refuses refunds: "not a market failure" |

**Financial impact**: $7M+ in trading volume. Incorrect YES resolution.

### Example 4: Israel-Lebanon Invasion (Ambiguous, Slow — Sep 2024)

- Market: "Will Israel invade Lebanon before September?"
- Ground operation launched October 1, 2024
- Dispute centered on definition of "invasion" vs "limited ground operation"
- UMA maintained consistent "No" votes across multiple dispute rounds
- Resolution took multiple dispute cycles

### Example 5: Zelenskyy Suit (Ambiguous, Controversial — Jul 2025)

**Timeline**:
| Date | Event |
|------|-------|
| May 22, 2025 | Market opens: "Will Zelenskyy wear a suit before June?" |
| Jun 24, 2025 | Zelenskyy appears at NATO in black jacket + matching trousers + collared shirt |
| Jun 24 | 40+ media outlets describe outfit as "a suit" |
| Jul 1, 2025 | UMA resolves as NO — "reporting consensus not sufficiently established" |
| Jul 1 | Martin Shkreli calls it a "scam" on live broadcast |
| Jul 7 | CoinDesk reports $160M+ controversy |

**Financial impact**: ~$14M direct market, $160-237M across related markets.

**Sources**: [CoinDesk](https://www.coindesk.com/markets/2024/11/06/polymarket-resolves-presidential-election-contract), [Polymarket Docs](https://docs.polymarket.com/developers/resolution/UMA), [CNN](https://www.cnn.com/2024/11/08/business/polymarket-election-trump-nightcap)

---

## 4. Post-Event Price Dynamics

### Do prices jump instantly to 99%?

**Yes, for unambiguous events.** Fed decisions snap to 99%+ within seconds. Election results ramp over hours as results stream in. Sports outcomes resolve near-instantly.

**No, for ambiguous events.** Geopolitical events (invasions, ceasefires, diplomatic deals) can hover at 80-95% for days due to definitional uncertainty.

### Bot Ecosystem — "Reality Arbitrage"

A documented algorithm ("swisstony wallet") turned **$5 into $3.7M** (740,000% ROI) by exploiting **broadcast lag** in sports markets:
- Live events have 15-40 second broadcast delay
- Bot received real-time data directly from stadiums via API
- Bought undervalued bets before broadcast caught up
- Polymarket responded with **dynamic taker fees** on short-duration markets (15-min crypto)

### Crypto Market Latency

- **BTC price lag**: 30-90 seconds between spot price movement and Polymarket odds update
- **Bot execution**: 80ms average response time, 99.2% success rate
- Polymarket removed 500ms taker price delay, changing dynamics for 5-min and 15-min markets

### Tail-End Trading (Resolution Sniping)

- Strategy: Buy shares at 97-99c, hold until $1.00 resolution
- Returns: 0.1-3% per trade, scalable across many markets
- Risk: Shares at 99c can crash to 50c or 0c during disputes
- Example: UFO market — someone bought $615,000 at ~99c right before resolution for ~$1,230 expected profit

### Key Insight for Our Strategies

The "gap" between event occurrence and market resolution is real but varies dramatically:
- **Fed decisions**: Seconds (bots dominate)
- **Elections**: Hours (structural — needs multiple source confirmations)
- **Geopolitical**: Days to weeks (definitional ambiguity)
- **Ambiguous markets**: The dispute window IS the opportunity, but it's also where manipulation risk is highest

**Sources**: [Phemex](https://phemex.com/news/article/algorithm-exploits-broadcast-lag-to-turn-5-into-37m-on-polymarket-53969), [QuantVPS](https://www.quantvps.com/blog/how-latency-impacts-polymarket-trading-performance), [FinanceMagnates](https://www.financemagnates.com/cryptocurrency/polymarket-introduces-dynamic-fees-to-curb-latency-arbitrage-in-short-term-crypto-markets/)

---

## 5. The Dispute Window: Can You Still Trade?

### YES — Markets remain open throughout the entire dispute process.

This is critical: trading continues during:
- The 2-hour liveness period
- The 24-48 hour debate period (after first dispute)
- The 48-96 hour DVM voting period (after second dispute)

**What this means**: During a dispute, you are essentially betting on how UMA voters will resolve. The market price reflects the probability-weighted outcome of the UMA vote, not the underlying event.

### Dispute Window Trading Dynamics

1. **Pre-dispute (market proposed)**: Price snaps to ~95-99c for the proposed outcome. Remaining shares are cheap calls on a reversal.
2. **First dispute filed**: Price drops to 70-85c as uncertainty increases. Counter-outcome rises.
3. **DVM escalation**: Price reflects market's assessment of UMA voter behavior. Can be volatile.
4. **DVM vote result**: Final snap to 99-100c or reversal.

### Risk: Manipulation During Disputes

- ~200 individual voters per dispute, but voting power is token-weighted
- Large UMA holders can coordinate
- Polymarket (as UMA's largest client) influences decision-making
- The $750 bond is too small to prevent strategic disputes on high-volume markets

**Sources**: [Polymarket Docs](https://docs.polymarket.com/developers/resolution/UMA), [Substack/ariverwhale](https://ariverwhale.substack.com/p/understanding-uma-and-dispute-resolution)

---

## 6. UMA Oracle Interpretation Principles

### Core Principles (ranked by importance)

1. **Market Title Over Technical Rules**: "The title reflects the spirit of the market and is more important than the rule." How users perceive the market takes precedence.

2. **Public Consensus Over Official Sources**: When credible news outlets contradict primary sources, UMA follows mainstream reporting. (Venezuela election example: despite official sources favoring Maduro, UMA resolved based on "credible reporting" supporting Gonzalez.)

3. **"Not a Court System"**: Attempts to "lawyer" one's way to a desired outcome through technical interpretations are unlikely to resonate with UMA voters.

4. **English-Language Western Media Bias**: NYT, CNN, WSJ, BBC carry significant weight. Non-Western and non-English sources receive minimal consideration.

5. **Binding Clarifications**: Polymarket clarifications are treated as binding market rules and have **never been overturned** by UMA.

6. **Consistency Across Rounds**: UMA rarely reverses initial decisions across voting rounds.

### The "Headline Template" Method

UMA uses what could be called the "Headline Template" method: would a reasonable person reading a major English-language news headline about this event conclude the market should resolve YES or NO?

### Key Implications for Trading

- **Title is king**: If the title says X, and the rules say Y, title wins.
- **Polymarket clarifications are gospel**: Once Polymarket issues a clarification, it becomes binding. This was used controversially in the Trump/China crypto summit case (retroactive clarification that "mentioning China" didn't count).
- **Western media consensus drives resolution**: Non-Western perspectives are structurally disadvantaged.
- **Polymarket has overridden UMA exactly once**: Barron Trump / $DJT case (June 2024). Polymarket refunded YES holders after UMA resolved NO, calling the resolution "conclusively wrong."

**Sources**: [Substack/ariverwhale](https://ariverwhale.substack.com/p/understanding-uma-and-dispute-resolution), [Polymarket Legacy Docs](https://legacy-docs.polymarket.com/polymarket-+-uma), [CoinDesk](https://finance.yahoo.com/news/polymarket-contradicts-oracle-rarity-prediction-022105806.html)

---

## 7. Top 10+ Disputed/Ambiguous Resolutions (2024-2026)

### 1. Ukraine Mineral Deal — "Governance Attack" (March 2025)

| Field | Detail |
|-------|--------|
| **Market** | "Ukraine agrees to Trump mineral deal before April?" |
| **Volume** | $7M+ |
| **Ambiguity** | No official deal confirmed; UMA whale with 5M tokens (3 accounts) forced YES vote |
| **Resolution** | YES (incorrect by most accounts) |
| **Impact** | $7M+ affected. Polymarket refused refunds. Led directly to MOOV2 proposal. |
| **Lesson** | Oracle manipulation is real. Single whale controlled ~25% of vote. |

### 2. Zelenskyy Suit (May-July 2025)

| Field | Detail |
|-------|--------|
| **Market** | "Will Zelenskyy wear a suit before July?" |
| **Volume** | ~$14M direct; $160-237M across related markets |
| **Ambiguity** | Zelenskyy wore black jacket + matching trousers + collared shirt. 40+ media outlets called it "a suit." UMA ruled NO — "reporting consensus not established" |
| **Resolution** | NO |
| **Impact** | Largest Polymarket controversy by dollar value. Triggered mainstream media coverage. |
| **Lesson** | Subjective/definitional markets are inherently dangerous. UMA's "suit" definition was narrower than common usage. |

### 3. UFO Declassification (April-December 2025)

| Field | Detail |
|-------|--------|
| **Market** | "Trump declassifies UFO files in 2025?" |
| **Volume** | $16M |
| **Ambiguity** | AARO released procedural guidance about declassification processes, not actual declassified files. Market sat at 5.5% then rocketed to 90% on Dec 7. |
| **Resolution** | YES (disputed — token-weighted vote overruled trader consensus) |
| **Impact** | $16M. Critics labeled it "proof-of-whales" governance. |
| **Lesson** | Subjective government-action contracts are exploitable. Late-session snipers bought at 99c before finalization. |

### 4. Venezuela Invasion (January 2026)

| Field | Detail |
|-------|--------|
| **Market** | "US invades Venezuela by January 31, 2026?" |
| **Volume** | $10.5M+ |
| **Ambiguity** | US special forces seized Maduro from Caracas compound, killed 75 people. Polymarket ruled this was "snatch-and-extract," not "military offensive to establish control." |
| **Resolution** | NO (payouts withheld, then settled as NO) |
| **Impact** | $10.5M. Prompted Rep. Torres to introduce prediction market regulation bill. |
| **Lesson** | Military operations exist on a spectrum. "Invasion" definition is inherently ambiguous. |

### 5. TikTok Ban (January 2025)

| Field | Detail |
|-------|--------|
| **Market** | "TikTok banned in the US before May 2025?" |
| **Volume** | $120M |
| **Ambiguity** | Supreme Court upheld ban law (Jan 19). TikTok briefly went dark. Trump signed executive order granting extension on Jan 20. Was it "banned"? |
| **Resolution** | YES — the law took effect Jan 19, regardless of subsequent executive action |
| **Impact** | Major backlash. Petition for accountability (few signatures). |
| **Lesson** | Temporal snapshots matter. "Did event X happen" is different from "is event X currently in effect." |

### 6. Israel-Lebanon Invasion (September 2024)

| Field | Detail |
|-------|--------|
| **Market** | "Will Israel invade Lebanon before September?" and "in September?" |
| **Volume** | Not public |
| **Ambiguity** | Israel launched ground operation Oct 1. Was it an "invasion" or "limited operation"? |
| **Resolution** | NO (before September), then disputed for the September market |
| **Impact** | UMA maintained NO across multiple dispute rounds. |
| **Lesson** | Consistent UMA voting — they rarely reverse. Military terminology is inherently ambiguous. |

### 7. Myrnohrad Town Capture (November 2025)

| Field | Detail |
|-------|--------|
| **Market** | "Will Russia capture Myrnohrad by November 15?" |
| **Volume** | $1.3M |
| **Ambiguity** | ISW staffer made unauthorized edit to frontline map, showing fake Russian advance. Polymarket used ISW maps as resolution source. |
| **Resolution** | YES (based on manipulated map data) |
| **Impact** | 33,000% profit for some bettors. ISW staffer fired. Led to Congressional scrutiny. |
| **Lesson** | Resolution sources can be compromised. Single-source resolution is vulnerable to manipulation. |

### 8. RFK Jr. Dropout (August 2024)

| Field | Detail |
|-------|--------|
| **Market** | "Will RFK drop out before November?" |
| **Volume** | ~$300K+ |
| **Ambiguity** | Kennedy said "I'm not terminating my campaign, I'm simply suspending it." Under FEC rules, suspension differs from dropping out. |
| **Resolution** | Disputed — market language said "withdrawal" |
| **Impact** | Moderate. Set precedent for how suspension vs. withdrawal is interpreted. |
| **Lesson** | Contract wording must be precise. Political candidates rarely "drop out" — they "suspend." |

### 9. Barron Trump / $DJT Token (June 2024)

| Field | Detail |
|-------|--------|
| **Market** | "Was Barron Trump involved in $DJT?" |
| **Volume** | Not public |
| **Ambiguity** | UMA resolved NO. Polymarket disagreed, calling it "conclusive" that Barron was involved. |
| **Resolution** | **Polymarket overrode UMA** — refunded YES holders. Only time this has happened. |
| **Impact** | Set precedent that Polymarket CAN override its oracle. Undermines oracle independence claims. |
| **Lesson** | The oracle is not truly independent. Polymarket is the ultimate authority. |

### 10. Trump/China at Crypto Summit (March 2025)

| Field | Detail |
|-------|--------|
| **Market** | "Will Trump say China during crypto summit?" |
| **Volume** | Not public |
| **Ambiguity** | Trump mentioned China. Polymarket issued retroactive clarification declaring it "didn't count." Resolved NO. |
| **Resolution** | NO (via retroactive clarification) |
| **Impact** | Backlash over retroactive rule changes. |
| **Lesson** | Polymarket clarifications are binding and can be issued retroactively. Never bet against a potential clarification. |

### 11. Fort Knox Gold (February-March 2025)

| Field | Detail |
|-------|--------|
| **Market** | "Gold missing from Fort Knox?" |
| **Volume** | ~$3.5M |
| **Ambiguity** | Resolved as NO. Dispute button allegedly disappeared during the 2-hour challenge window, preventing challenges. |
| **Resolution** | NO (disputed process) |
| **Impact** | ~$3.5M. Allegations of coordinated whale voting. |
| **Lesson** | UI issues during challenge windows can prevent legitimate disputes. |

---

## 8. Structural Implications for Our Strategies

### Resolution Risk Matrix

| Market Type | Resolution Speed | Dispute Risk | Manipulation Risk |
|-------------|-----------------|--------------|-------------------|
| Fed rates | Minutes → 2 hours | Near zero | Near zero |
| Election results | Hours (multi-source) | Low | Low |
| Sports outcomes | Minutes | Very low | Medium (broadcast lag) |
| Crypto prices | Seconds-minutes | Low | Medium (latency arb) |
| "Say X" / mention | Hours | **High** | **High** (retroactive clarifications) |
| Military/geopolitical | Days-weeks | **Very high** | **Very high** |
| Subjective/definitional | Days-weeks | **Very high** | **Very high** |

### Key Takeaways

1. **~98.5% of markets resolve without dispute in ~2 hours**. The dispute system is the exception, not the norm.

2. **Polymarket International vs US have DIFFERENT resolution processes**. US version: Markets Team decides directly. International: UMA oracle.

3. **MOOV2 (Aug 2025) tightened proposer access** to 37 whitelisted addresses but didn't fix the underlying UMA voting power concentration problem.

4. **Trading continues during disputes** — this is a strategic opportunity AND a risk. You're betting on UMA voter behavior, not the underlying event.

5. **Polymarket clarifications are nuclear weapons**. They are retroactive, binding, and have never been overturned by UMA. If Polymarket issues a clarification, it WILL determine the outcome.

6. **The UMA market cap vs Polymarket TVL ratio (1:7.5)** means governance attacks are economically rational for large positions. This was proven in the Ukraine mineral deal case.

7. **Post-event price dynamics vary by market type**:
   - Objective events: Bots dominate, price snaps in seconds
   - Subjective events: Price hovers 80-95% for days, creating opportunity
   - The "last mile" from 95c to $1.00 is where disputes live

8. **Resolution source manipulation is real**: ISW map editing for Myrnohrad, retroactive clarifications for crypto summit. Always verify the independence of resolution sources.

### Strategy Implications

- **S004 (Overreaction)**: Post-event spikes in geopolitical markets may not fully resolve for days due to definitional ambiguity. This extends the reversion window but also increases resolution risk.
- **S006 (Time Decay)**: "By date" markets have clean resolution — either it happened or it didn't. Lower dispute risk.
- **S007 (Cross-Market Arb)**: Overround in related markets is partially explained by dispute risk premiums on subjective markets.
- **S008 (potential resolution delay strategy)**: The gap between event occurrence and market resolution IS an edge — but bots own the fast end (sports, crypto, Fed), and manipulation risk owns the slow end (geopolitical). The sweet spot is elections and regulatory decisions: clear outcomes, structural delays.

---

## 9. Polymarket US vs International: Dual Resolution Systems

| Feature | Polymarket International | Polymarket US |
|---------|--------------------------|---------------|
| **Decision maker** | UMA Oracle (token holder vote) | Markets Team (internal) |
| **Speed** | 2h minimum; days if disputed | Typically hours |
| **Dispute mechanism** | $750 bond → DVM vote | None for traders; internal review |
| **Recourse** | UMA vote is final | Email, Discord |
| **Risk** | Governance/whale manipulation | Operational/human error |
| **Override possible** | Once (Barron Trump case) | Regularly |

Polymarket US launched in 2025/2026 without UMA — the Markets Team directly determines outcomes. This is a fundamentally different product with different risks.

**Sources**: [DeFi Rate](https://defirate.com/prediction-markets/how-contracts-settle/), [Sportico](https://www.sportico.com/business/sports-betting/2025/polymarket-uma-resolution-crypto-1234878760/)

---

## Sources (Full List)

- [Polymarket Resolution Docs](https://docs.polymarket.com/developers/resolution/UMA)
- [The Block — MOOV2 Update](https://www.theblock.co/post/366507/polymarket-uma-oracle-update)
- [RocknBlock — Inside UMA Oracle](https://rocknblock.io/blog/how-prediction-markets-resolution-works-uma-optimistic-oracle-polymarket)
- [DeFi Rate — How Kalshi and Polymarket Settle](https://defirate.com/prediction-markets/how-contracts-settle/)
- [Substack/ariverwhale — Understanding UMA](https://ariverwhale.substack.com/p/understanding-uma-and-dispute-resolution)
- [CryptoSlate — UFO Market Crisis](https://cryptoslate.com/polymarket-faces-major-credibility-crisis-after-whales-forced-a-yes-ufo-vote-without-evidence/)
- [CoinDesk — Zelenskyy Suit $160M](https://www.coindesk.com/markets/2025/07/07/polymarket-embroiled-in-usd160m-controversy-over-whether-zelensky-wore-a-suit-at-nato)
- [Decrypt — Zelenskyy Suit NO](https://decrypt.co/329210/polymarket-rules-no-237m-bet-zelenskyys)
- [The Defiant — Ukraine Mineral Deal Whale](https://thedefiant.io/news/defi/polymarket-s-usd7m-ukraine-mineral-deal-debacle-traced-to-oracle-whale)
- [CoinMarketCap — Governance Attack](https://coinmarketcap.com/academy/article/polymarket-reports-unprecedented-governance-attack-by-uma-whale-on-bet-resolution)
- [Yahoo Finance — Venezuela Invasion](https://finance.yahoo.com/news/polymarket-withholds-payouts-venezuela-invasion-130701655.html)
- [CoinTelegraph — TikTok Ban](https://cointelegraph.com/news/polymarket-faces-backlash-over-tik-tok-ban-prediction-resolution)
- [404 Media — Myrnohrad Map Manipulation](https://www.404media.co/unauthorized-edit-to-ukraines-frontline-maps-point-to-polymarkets-war-betting/)
- [CoinDesk — RFK Dropout](https://www.coindesk.com/markets/2024/08/26/did-rfk-jr-really-drop-out-polymarket-bettors-argue-over-contract-resolution)
- [Yahoo Finance — Barron Trump Override](https://finance.yahoo.com/news/polymarket-contradicts-oracle-rarity-prediction-022105806.html)
- [Phemex — $5 to $3.7M Algorithm](https://phemex.com/news/article/algorithm-exploits-broadcast-lag-to-turn-5-into-37m-on-polymarket-53969)
- [QuantVPS — Bot Latency](https://www.quantvps.com/blog/how-latency-impacts-polymarket-trading-performance)
- [Polymarket Legacy Docs — UMA Integration](https://legacy-docs.polymarket.com/polymarket-+-uma)
- [CNN — Election Night Prediction](https://www.cnn.com/2024/11/08/business/polymarket-election-trump-nightcap)
- [Webopedia — UMA Controversy](https://www.webopedia.com/crypto/learn/polymarkets-uma-oracle-controversy/)
