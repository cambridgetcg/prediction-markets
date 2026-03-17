# D14 — European Value Bets Execution

You are a trading analyst executing on previously researched European political market opportunities. Multiple value bets across three markets have been identified with clear edges. The research is largely done. This prompt evaluates, sizes, and executes them.

## Read First

1. `~/Desktop/prediction-markets/domains/POL/active.md` — full European market analysis (required)
2. `~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md` — current portfolio + capacity
3. `~/Desktop/prediction-markets/strategies/BANKROLL.md` — sizing rules

## Identified Opportunities (from Batch 3-4 research)

| # | Market | Trade | Entry | Edge | Domain | Liquidity |
|---|--------|-------|-------|------|--------|-----------|
| E1 | **UK: No Next PM in 2026** | YES | 39.5% | **+18pp** | POL | $458K |
| E2 | **French: Edouard Philippe wins 2027** | YES | 14.5% | **+4pp** | POL | $1.7M |
| E3 | **French: Raphaël Glucksmann wins 2027** | YES | 2.0% | **+3pp** | POL | $1.7M |
| E4 | **French: Melenchon NO (sells)** | NO | ~10% | **+3pp** | POL | $1.7M |
| E5 | **Eurovision: Israel participation risk** | Cross-platform arb | 7% (Poly) vs 22% (bookies) | **+15pp discrepancy** | SOC | $1.37M |

---

## Task 1: Live Price Check

Verify current prices — POL markets move quickly:

```
web_search("Polymarket UK next prime minister 2026 No change")
web_search("Polymarket French presidential 2027 Philippe Glucksmann")
web_search("Polymarket Eurovision 2026 Israel winner odds")
web_search("Polymarket Starmer out 2026")
```

Also check: **Le Pen appeal ruling** — any updates since Feb 25? This gates the entire French market.

For each opportunity, record:
```
Current price: X%
Price vs. D06 analysis: +/- Y pp
Edge still valid (>5pp)? Y/N
Liquidity still adequate? Y/N
```

**Minimum edge threshold for entry: 5pp** (not worth the liquidity risk below this).

---

## Task 2: UK "No Next PM in 2026" — Execute E1

This is the highest-conviction European bet with the widest edge.

### Thesis Recap
- "No Next PM in 2026" at 39.5%: our estimate 55-65%
- Starmer has a 400+ seat majority — the largest since 1997
- No credible challenger has publicly positioned against him
- UK Labour MPs have zero incentive to trigger a leadership crisis before the next election
- The market is pricing meaningful probability on something that requires: coup, vote of no confidence (needs 51% Labour MPs), challenger to emerge, and Starmer to resign — all in one year

### Price Sensitivity
- At 39.5% YES → edge = ~18pp → enter
- At 45% YES → edge = ~13pp → enter (still wide)
- At 50% YES → edge = ~8pp → smaller position
- At 55% YES → edge = ~3pp → SKIP (not enough for liquidity risk)

### Sizing

```
My estimate: 60% NO change (i.e., 60% YES "no next PM")
Entry YES price: 39.5% (assume unchanged)
Edge = 0.60 - 0.395 = 0.205
Kelly = 0.205 / (1 - 0.395) = 0.339 → too large
Quarter-Kelly = 8.5% → cap at 3% of bankroll
Size: $300 max (PT012)
```

### Risk Factors
- Low liquidity ($458K total) — $300 position is acceptable, don't go larger
- Market has 61 sub-markets (61 candidates for "next PM") — overround is high ~30%
- The 39.5% for "no change" means YES prices on all candidates sum to 60.5% → our $0.40 costs $0.60 after overround adjustment
- S004 strategy: contrarian — we're fading the market's overestimate of regime instability

Log: "PT012 — S004 Contrarian — POL — UK No Next PM 2026 YES"

---

## Task 3: French Presidential 2027 — Execute E2, E3, E4

### Context
- Election: Spring 2027 (14 months away)
- **CRITICAL GATE: July 7, 2026** — Le Pen appeal ruling. If ban upheld → Bardella consolidates, Philippe becomes primary alternative. If ban lifted → Le Pen frontrunner returns.
- Overround is high (~27%) — NegRisk structure may apply
- Liquidity at $1.7M is adequate but not deep

### Pre-check: Le Pen Ruling Update

```
web_search("Marine Le Pen appeal ruling 2026 France update")
web_search("France court Le Pen ban appeal February 2026")
```

If Le Pen ban has already been lifted → ALL French presidential estimates need revision. Bardella recedes, Le Pen is frontrunner (estimate: 25-35% win probability vs current 10.5%). Philippe becomes less important. Do NOT execute E2/E3 as described if Le Pen ruling has changed.

If still pending for Jul 7 → proceed with analysis as written.

### E2: Philippe YES at 14.5%

Thesis: Philippe is the most popular politician in France (consistently #1-2 in approval polls). He's the clearest anti-populist, anti-extreme alternative in the center-right. If ban upheld (removing Le Pen), Philippe consolidates the moderate-right vote.

At 14.5%, even with front républicain uncertainty, this is underpriced for the most electable candidate.

**Sizing**:
```
My estimate: ~19% win probability
Edge = 0.19 - 0.145 = 0.045
Quarter-Kelly = minimal → small position
Size: $100 (1% bankroll) — small position given 14-month horizon and Le Pen gate (PT013)
```

Wait factor: **Consider waiting until Jul 7 appeal ruling** for full position. The Oct ruling might resolve a key binary. Enter 50% now ($50), 50% on Jul 7 outcome.

Log: "PT013 — S001 Hold — POL — France 2027 Philippe YES"

### E3: Glucksmann YES at 2.0%

Thesis: Glucksmann is polling 11-13% but priced at 2% on Polymarket. This is a 5-7x discrepancy. He leads the revived PS center-left, is the strongest non-Macron progressive option, and could consolidate the entire center-left if Mélenchon's NFP collapses.

At 2%, this is lottery-ticket sizing — even if the true probability is 5%, that's a 2.5× mispricing.

**Sizing**:
```
My estimate: ~6% win probability (conservative — 14 months out)
Edge = 0.06 - 0.02 = 0.04 (modest)
BUT: the mispricing ratio is high (3:1). Risk is limited at 2% entry.
Size: $50 (0.5% bankroll) — lottery-ticket position (PT014)
```

Rationale: At $50, the downside is $50. The upside at $1.00 resolution is $2,500. Even at 4% probability (2× the market), this has positive EV.

Log: "PT014 — S008 Info Edge — POL — France 2027 Glucksmann YES"

### E4: Mélenchon NO at 10%

Thesis: Mélenchon is 74 years old, loses to Bardella 74-26 in R2 (catastrophic numbers), and represents divisive left politics that damages his coalition more than helps. He's priced at 10% but our estimate is 5-8%.

**Note**: This is SELLING YES on Mélenchon = BUYING NO at ~90%.
- Enter NO position at ~$0.90 per share
- Return if NO: ~11% (from $0.90 to $1.00)
- This is a modest time-decay play on an overpriced candidate

**Sizing**:
```
My estimate: 7% YES → 93% NO
Entry NO: ~$0.90
Edge on NO = 0.93 - 0.90 = 0.03 → tiny
Quarter-Kelly → tiny
Size: $75 (0.75% bankroll, PT015) — this is barely worth the effort; include only if Phase 1 capital is available
```

**Threshold check**: If YES is now below 8% → edge on NO is too thin → SKIP E4.

Log: "PT015 — S006 Time Decay — POL — France 2027 Melenchon NO"

---

## Task 4: Eurovision 2026 Israel Arb — Evaluate E5

This is a cross-platform discrepancy, not a straightforward trade:
- Polymarket: Israel 7% (influenced by political sentiment against Israeli participation)
- Traditional bookmakers: Israel 22% (pure performance-based odds)

### 4a. Research the Discrepancy

```
web_search("Eurovision 2026 Israel participation boycott ban")
web_search("Eurovision 2026 Israel odds bookmakers vs prediction markets")
web_search("EBU Israel Eurovision 2026 decision")
```

Key question: **Is Israel definitely participating in Eurovision 2026?**
- If there's real risk of a participation ban/withdrawal → Polymarket at 7% is correct (participation risk + win probability)
- If Israel is definitely participating → Polymarket at 7% is a political sentiment discount = arb opportunity

### 4b. Decision Framework

| Scenario | Action |
|----------|--------|
| Israel definitely participating, bookmakers right at 22% | BUY YES on Polymarket — 15pp edge. Size: $150 (PT016) |
| Israel participation uncertain | DO NOT TRADE — the risk is in the binary, not the performance |
| Israel participation confirmed, but bookmakers have already moved to 10% | Edge too thin → SKIP |

### 4c. If Arb Confirmed

```
Size: $150 (1.5% bankroll)
Strategy: S007 Cross-Market Arb
Logic: Buy Polymarket YES at 7¢, simultaneously note bookmaker implied probability at 22%
Return if won: 14.3× = $2,150 (extremely asymmetric)
Loss if lost: $150
EV at 15% true probability: $150 × 0.15 × (1/0.07 - 1) - $150 × 0.85 = positive
```

Log: "PT016 — S007 Cross-Market Arb — SOC — Eurovision 2026 Israel YES (if confirmed participating)"

---

## Task 5: European Domain Summary

After executing all positions, update `domains/POL/active.md` and create `domains/SOC/active.md` if needed:

### POL Domain

European positions added:
| ID | Market | Dir | Size | Strategy | Entry |
|----|--------|-----|------|----------|-------|
| PT012 | UK No Next PM 2026 | YES | $300 | S004 | 39.5% |
| PT013 | France 2027 Philippe | YES | $50-100 | S001 | 14.5% |
| PT014 | France 2027 Glucksmann | YES | $50 | S008 | 2.0% |
| PT015 | France 2027 Melenchon | NO | $75 | S006 | 90% NO |
| PT016 | Eurovision 2026 Israel | YES | $150 | S007 | 7.0% |

### Domain Exposure Update

After entering:
- POL domain total: PT002 ($500) + PT006 ($125) + PT012 ($300) + PT013 ($75) + PT014 ($50) + PT015 ($75) = **$1,125 (11.25% of $10K bankroll)**
- Domain cap (D2): 10% of bankroll = $1,000 → **OVER CAP** if all entered
- Priority if over cap: Drop PT015 (Melenchon NO, lowest edge) to stay within D2 limit
- If PT012, PT013, PT014 all entered → POL = $975 (9.75%) → within cap

**Check before executing PT015**: Is POL under 10%? If not, skip.

---

## Output

1. Logged paper trades: PT012-PT016 (where executed)
2. Updated `domains/POL/active.md` — current European positions and prices
3. Updated `strategies/paper-trades/pnl-summary.md` — new domain allocation
4. If Eurovision arb confirmed: note in `research/` the discrepancy and decision
5. Terminal output: Which trades executed? Current POL domain exposure (must be ≤10%)? Current bankroll allocation?

**Done when**: At minimum PT012 (UK No PM) is executed with $300 — this is the highest-edge, most liquid European bet and should be the priority. French positions are secondary. Eurovision only if participation is confirmed.

**Time sensitivity**: 
- UK No PM: Low — can enter any time in 2026 
- French 2027: Low — 14 months out, prices are stable
- Eurovision: **Medium** — Israel participation decision may come before the event. Monitor.
