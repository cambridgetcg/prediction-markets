# D13 — TEC Execution: Enter the AI Model Positions

You are a trading analyst executing on previously researched TEC domain opportunities. D11 identified three high-conviction AI model trades. The research is done. This prompt executes them.

## Read First

1. `~/Desktop/prediction-markets/domains/TEC/active.md` — all AI model market analysis (required)
2. `~/Desktop/prediction-markets/strategies/paper-trades/pnl-summary.md` — current portfolio + available capital
3. `~/Desktop/prediction-markets/strategies/BANKROLL.md` — sizing rules (Phase 1 constraints)
4. `~/Desktop/prediction-markets/calibration/calibration.md` — YES calibration weakness (2/5 YES bets correct so far)

## Context

Three trades were identified in D11 with sufficient edge to enter. They have not been executed yet. Time pressure exists on two of them:

| Trade | Direction | Entry Price | My Estimate | Edge | Deadline Risk |
|-------|-----------|-------------|-------------|------|---------------|
| **T1**: Anthropic wins "Best AI Model Mar 31" | YES | 63.9% | 72-78% | **+8-14pp** | Resolves Mar 31 — enter by mid-March at latest |
| **T2**: Claude 5 released by Apr 30 | NO | 40.5% | ~65% NO confidence | **+5-10pp** | SELL window: price likely to fall as Apr approaches |
| **T3**: Anthropic wins "Best AI Model Jun 30" | YES | 37.0% | 42-48% | **+5-11pp** | Longer dated, less urgent |

---

## Task 1: Live Price Check

Before executing, verify current prices (they may have moved since D11 on Feb 23):

```
web_search("Polymarket best AI model March 2026 Anthropic Claude")
web_search("Polymarket Claude 5 release date April 2026")
web_search("Polymarket best AI model June 2026 prediction")
```

Also check: **Has the Feb 28 Arena AI model market resolved?** (It should, as of today).
- If Anthropic won Feb 28 → thesis strengthened for March and June bets
- If Anthropic lost Feb 28 (unexpected) → STOP and reassess. Do not enter March trade until you understand what happened.

For each trade, record:
```
Current YES price: X%
Price vs. D11 analysis (Feb 23): +/- Y pp
Edge still valid? Y/N
Thesis status: intact / weakened / strengthened
```

---

## Task 2: Pre-Trade Calibration Check

### 2a. YES Calibration Problem

We are 2/5 on YES bets (40%) vs 7/7 on NO bets (100%). Both TEC T1 and T3 are YES bets.

**Before entering YES positions:**
- Is this a small-sample artifact? (N=5 is very small)
- Were previous YES failures in a different domain/type?
- Does the AI model market behave differently from political YES markets (where overconfidence in underdog candidates was the failure mode)?

**AI Model YES rationale** (why these might be different):
- This is an empirical question (Arena.ai Elo score), not a political opinion
- We have specific domain expertise (Claude is already #1 with 19-point Elo gap)
- The edge is based on statistical lead, not subjective assessment
- Historical base rate for #1 model holding lead through 30 days: high

**Verdict**: If Feb 28 resolved Anthropic YES → confirms thesis → enter T1 and T3 as planned. If Feb 28 had unexpected result → reduce T1/T3 size or defer.

### 2b. Phase 1 Constraints

Current available capital (after T005 exit, check pnl-summary.md):
- Phase 1 allows up to $250 per batch
- Current allocation check: what's available?

If already at Phase 1 capacity, defer T3 (longest-dated, least urgent) until capital is freed.

---

## Task 3: Execute Trade 1 — Anthropic March

**Only execute if**: Feb 28 Arena resolved Anthropic YES (or is still in progress with lead intact).

**Position**: BUY YES "Anthropic/Claude wins Best AI Model March 31, 2026"
- Target entry: 63.9% YES (or current price if moved)
- If price has risen above 70% → reconsider. Edge shrinks: at 70%, edge is only +2-8pp. Min required edge: 5pp.
- If price has fallen below 60% → larger edge. Buy more.

**Sizing (quarter-Kelly)**:
```
Edge = 0.75 (midpoint of 72-78% estimate) - entry_price
Kelly fraction = edge / (1 - entry_price)
Quarter-Kelly size = Kelly_fraction × 0.25 × bankroll
Cap at 3% of bankroll ($300 max on Phase 1 paper account = $10K × 3%)
```

Expected size at 64% entry, 75% estimate:
- Edge = 0.75 - 0.64 = 0.11
- Kelly = 0.11 / (1 - 0.64) = 0.305 = 30.5% of bankroll → absurd
- Quarter-Kelly = 7.6% → still too large
- **Cap at 3% = $300**. Log as PT009.

Log entry: "PT009 — S008 Info Edge + S001 Hold — TEC — Anthropic March Arena YES"

### 3a. Monitor Trigger

Set the following triggers for T1 after entry:
- **Exit if**: Google Gemini 3.1 officially goes GA and claims Arena #1 before March 15
- **Exit if**: Arena methodology changes and Claude's lead is invalidated
- **Hold until resolution** otherwise (S001 strategy: hold to resolution)
- No time-decay concern — this is a thesis play, not a S006 trade

---

## Task 4: Execute Trade 2 — Claude 5 NO (SELL)

**Position**: BUY NO "Claude 5 released by April 30, 2026"
- Target entry: 40.5% YES → NO costs $0.595 per share
- If YES is now above 45% → edge better for NO. Larger position.
- If YES is now below 35% → edge shrinking. Still worth small position.

**Thesis recap**:
- Anthropic released Claude Opus 4.6 on Feb 17, 2026 (9 days ago)
- "claude-sonnet-5@20260203" leak in Vertex AI = suggestive but not confirmed
- Anthropic's release cadence: Opus 4 (May 2025) → 4.5 (Nov 2025) → 4.6 (Feb 2026) = incremental ~3-month steps
- Full generation jump to "5" within 10 weeks of shipping 4.6 seems fast
- Base rate for "company ships major release within 10 weeks of prior release": low

**Sizing (quarter-Kelly on NO)**:
```
My NO probability estimate: ~65%
Entry NO price: ~59.5¢ (if YES is 40.5%)
Edge on NO = 0.65 - 0.595 = 0.055
Kelly = 0.055 / (1 - 0.595) = 0.136 = 13.6%
Quarter-Kelly = 3.4% → over 3% cap
Cap at 3% = $300 max, log as PT010
```

**Important**: This is a TIME DECAY trade (S006) as much as an information trade (S008). If YES stays at 40% through March, time decay works against YES and benefits our NO. Enter sooner rather than later to maximize decay capture.

Log entry: "PT010 — S006 Time Decay + S008 Info Edge — TEC — Claude 5 NO by Apr 30"

---

## Task 5: Evaluate Trade 3 — Anthropic June

This is the most uncertain trade:
- 5-month duration (resolves Jun 30)
- Google I/O (May 19-20) is a live wildcard
- Claude 5 may or may not ship by then
- Edge: +5-11pp at current price (37% YES, estimate 42-48%)

**Decision criteria**:
1. If Phase 1 capital is already at capacity after T1 and T2 → **DEFER**. This is the lowest-urgency trade.
2. If capital available → enter at 2% of bankroll ($200 max, PT011) — smaller than T1/T2 due to greater uncertainty
3. If YES has moved above 42% since D11 → edge too thin to enter (< 5pp). **SKIP**.

**If entering PT011**:
- Size: $200 (2% bankroll)
- Strategy: S001 Hold (too long-dated for time decay)
- Monitor: Google I/O May 19-20 as primary risk event
- Add note: "Re-evaluate at end of April if Claude 5 has shipped"

---

## Task 6: Arena AI Model Research Update

For context on the March and June trades, pull current Arena.ai standings:

```
web_search("LMSYS chatbot arena leaderboard February 2026")
web_search("Claude Opus 4.6 arena elo score ranking February 2026")
web_search("Gemini 3 arena leaderboard February 2026")
```

Update `~/Desktop/prediction-markets/domains/TEC/research/` with:
- Current Elo scores for top 5 models
- Gap between #1 and #2
- Any new model arrivals in the last week that could threaten Claude's lead
- Google I/O announcement timeline

---

## Output

1. PT009 entry logged in `strategies/paper-trades/trades.jsonl` — Anthropic March YES (if Feb 28 resolved correctly)
2. PT010 entry logged — Claude 5 NO by Apr 30
3. PT011 entry logged (if capital available) — Anthropic June YES
4. Updated `domains/TEC/active.md` — current prices, open positions, Arena update
5. Updated `strategies/paper-trades/pnl-summary.md` — new allocations
6. Terminal output: What prices did we enter at? What's the edge at current price? What is the Feb 28 Arena result that validates/invalidates the March thesis?

**Done when**: T1 (Anthropic March) and T2 (Claude 5 NO) are executed (if prices remain within edge threshold), Arena data is updated, and portfolio reflects the new TEC positions.

**Hard stop**: If Feb 28 Arena resolved to anything OTHER than Anthropic → do not enter T1 or T3. Investigate what happened first. T2 (Claude 5 NO) remains valid regardless.
