# Pre-Position Source Diversity Checklist

> Complete this checklist BEFORE entering any position. No exceptions for positions >$100.
> This is the counter-strategy to source bias — structural diversity that forces multi-perspective research.

---

## 1. Minimum Source Basket

| Position Size | Min Sources | Must Include |
|--------------|-------------|--------------|
| Small ($50-100) | 2 independent | At least 1 Tier 1-2 source |
| Standard ($100-200) | 3 independent | 1 primary + 1 from different national perspective |
| Large ($200+) | 4 independent | Primary + 2 Tier 2 + adversarial perspective |

**"Independent" means**: Sources that do NOT share the same underlying source. Reuters and AP both reporting from a Pentagon briefing = ONE source, not two. Check the source-of-source.

**"Adversarial perspective" means**: The source MOST LIKELY to contradict your thesis.
- On Iran: read Iran International (anti-regime) AND Al-Monitor (regional) AND TWZ (military)
- On Fed policy: read Zero Hedge (contrarian) AND Nick Timiraos (consensus)
- On crypto: read both bull (exchange blogs) AND bear (traditional finance skeptics)

---

## 2. Pre-Position Research Template

Copy this template for every new position:

```markdown
## Source Check — [Market Name] — [Date]

### Position Details
- Market: ___
- Direction: ___
- Estimated size: $___
- Required source basket: [Small/Standard/Large]

### Primary Sources Consulted
- [ ] Official statement / document / on-chain data / court filing
  - Source: ___ | Date: ___ | Key claim: ___
  - Citation level: L___

### Domain Expert Sources
- Source 1: ___ | Key claim: ___ | Credibility: ___/5 | Citation level: L___
- Source 2: ___ | Key claim: ___ | Credibility: ___/5 | Citation level: L___

### Adversarial Perspective
- Source: ___ (should have opposing institutional bias to your thesis)
- Key claim: ___ | Credibility: ___/5
- Did this change my estimate? [Yes: from ___% to ___% / No: because ___]

### Agreement Zone (high confidence)
What do ALL credible sources agree on?
- ___
- ___

### Disagreement Zone (widen confidence interval)
What do credible sources disagree on?
- ___
- ___

### Strongest Counter-Argument (from best-credible source)
___

### Source Conflict Resolution
Applied? [Yes/No]
If yes: Source A [___] vs Source B [___] → Winner: ___ because ___

### Adjusted Probability
- Before source-quality weighting: ___%
- After adjustment formula: ___%
- Delta: ___pp
- Source-bias premium vs market price: ___pp
```

---

## 3. Recommended Reading Stack (RSS/Alert Diversity)

### Tier 1 — Primary Signals (read FIRST, before any interpretation)

| Domain | Primary Sources |
|--------|----------------|
| GEO | IAEA press releases, State Dept briefings, Pentagon transcripts, UN press office |
| POL | Electoral commission filings, FiveThirtyEight, official campaign statements, Congress.gov |
| ECO | Fed press releases (federalreserve.gov), BLS data releases, BEA PCE/GDP reports |
| FIN | Exchange data feeds, Treasury auction results, CFTC COT reports |
| CRY | Glassnode (on-chain), CoinGlass (derivatives), exchange announcements, blockchain explorers |
| TEC | arXiv preprints, company blogs (Anthropic/Google/OpenAI), Arena.ai leaderboard |
| SCI | NASA/ESA press releases, Nature/Science, NIH/WHO reports |
| SOC | Official entity statements, court records, primary polling data |
| LAW | SCOTUS Blog, PACER filings, DOJ press releases, SEC EDGAR |
| ENV | IPCC reports, EPA data, COP official documents, NOAA data |

### Tier 2 — Domain Experts (interpret primary signals)

| Domain | Expert Sources |
|--------|---------------|
| GEO | The War Zone, Bellingcat, ISW daily updates, International Crisis Group |
| POL | Silver Bulletin (Nate Silver), Cook Political Report, academic political scientists |
| ECO | Nick Timiraos (WSJ), CME FedWatch, JPMorgan/Goldman research, Fed Listens |
| FIN | Bloomberg terminal data, Barron's, FT Alphaville |
| CRY | The Block, Delphi Digital, verified on-chain analysts |
| TEC | Andrej Karpathy, Ethan Mollick, domain-specialist AI researchers (verified) |
| SCI | Domain journals (Lancet, PNAS), academic preprint servers |
| SOC | Pew Research, Gallup, academic demographers |
| LAW | SCOTUS Blog analysis, Lawfare, Law360 |
| ENV | Carbon Brief, Climate Action Tracker, domain researchers |

### Tier 3 — Geographically Diverse (prevent Western-only framing)

| Region | Sources |
|--------|---------|
| Middle East | Al Jazeera, Middle East Eye, Iran International (UK-based), Al-Monitor |
| Russia/Ukraine | Meduza (independent Russian in exile), Kyiv Independent |
| China | Caixin (independent business), South China Morning Post (HK) |
| Israel | Haaretz (left), Times of Israel (centre), Ynet (right) |
| Gulf States | Al Arabiya (Saudi-adjacent), The National (UAE), Gulf News |
| Latin America | Reuters Latam, AP Latam, local court filings |
| Global Economy | FT, Nikkei Asia, El Economista |

### Tier 4 — Speed Layer (monitor for breaking, VERIFY before updating)

| Domain | Speed Sources |
|--------|--------------|
| All | Reuters/AP breaking alerts |
| GEO | Watcher.Guru, OSINTdefender (Twitter), Liveuamap |
| POL | Decision Desk HQ, AP election alerts |
| ECO | CME FedWatch real-time, @NickTimiraos |
| CRY | Verified exchange accounts, @WuBlockchain, @whale_alert |
| TEC | Company Twitter accounts, @_jasonwei (Google), @demaborhgaard (Anthropic) |

---

## 4. Counter-Reading Rule

**Mandatory for positions >$100:**

> For every bullish source on your thesis, you MUST read one bearish source before finalising the estimate.

This is non-optional. The bearish source should be:
1. Credible (Tier 1-3, not a random Twitter account)
2. From a different institutional perspective than your bullish source
3. Addressing the same core question (not a tangential objection)

If you cannot find a credible bearish source, one of two things is true:
- You haven't looked hard enough (most likely)
- The market is massively mispriced in your favour (rare — verify with extra skepticism)

---

## 5. Echo Chamber Detection Test

Run this BEFORE finalising any probability estimate:

```
1. Can I name 2 credible sources that DISAGREE with my estimate?
   [ ] Yes → Proceed
   [ ] No  → STOP. Research more before entering.

2. Are all my sources from the SAME country or institutional perspective?
   [ ] No  → Proceed
   [ ] Yes → STOP. Add at least one source from a different national perspective.

3. Did I form my estimate BEFORE reading the market price?
   [ ] Yes → Proceed
   [ ] No  → WARNING: I've been anchored. Re-estimate independently, then compare.

4. Is my main source also the LOUDEST source? (most coverage, most discussed)
   [ ] No  → Proceed
   [ ] Yes → Apply amplification discount. Louder ≠ more likely.

5. When was the last time I updated an estimate AGAINST my existing position?
   [ ] Recently → Proceed (I'm seeking disconfirmation)
   [ ] Never   → WARNING: I'm confirming, not calibrating. Actively seek counter-evidence.
```

**If 2+ checks fail**: Do NOT enter the position until resolved.

---

## 6. Post-Entry Source Monitoring

After entering a position, set up ongoing source diversity:

1. **Weekly adversarial check**: Read 1 credible source that argues against your position
2. **Source rotation**: Don't read only the same 2-3 sources every day
3. **Primary source alerts**: Set up alerts for the primary data sources relevant to your position (e.g., IAEA reports for Iran, FOMC minutes for ECO)
4. **Conflict flag**: If two Tier 1-2 sources start disagreeing on your market, reassess immediately

---

## References

- Source credibility matrix: `research/source-credibility-matrix.json`
- Adjustment formula: `psychology/source-bias-adjustment.md`
- Domain source maps: `research/domain-source-maps.md`
- Behavioral foundations: `psychology/behavioral-foundations.md`
