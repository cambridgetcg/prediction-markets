# B10-03: CITRINITAS Output — The Golden Architecture

*Generated: 2026-02-28*
*Source material: B10-02-albedo-output.md, TRADING-PHILOSOPHY.md, what-doesnt-work.md (6.2), calibration.md (N=12), pnl-summary.md (-$242.84), live-trades.md ($28.98)*

---

## The Golden Architecture

The ALBEDO revealed one taproot: the system builds to avoid trading, because building always succeeds and trading might not. The golden architecture dissolves this distinction. There is no "build phase" followed by a "trade phase." There is one loop, and every revolution of the loop includes a live trade.

### The 5 Core Components

**Component 1: SCAN** (purpose: find the next trade)
One script. Runs daily. Pulls active Polymarket markets, filters by: resolution within 30 days, volume >$50K, domain in {GEO, POL, ECO, LAW, TEC}. Outputs a shortlist of 5-10 candidates with current prices. That's it. No sentiment analysis, no news pipeline, no whale cross-referencing. Just: what markets exist that resolve soon in domains you know.

**Component 2: ESTIMATE** (purpose: decide if there's edge)
For each candidate from SCAN: estimate the probability. Write a 3-line thesis. Calculate: my estimate vs. market price = edge. If edge < 5pp, skip. If edge >= 5pp, proceed. The estimate is manual — Yu + Claude, one conversation, using domain knowledge already in the researcher's head and publicly available information. No pipeline. No 7-module architecture. One conversation per trade.

**Component 3: EXECUTE** (purpose: place the trade)
Limit order on Polymarket. Position size from a simple table (see Capital Ladder below). Entry price, exit conditions (stop, target, time), and thesis recorded in one line in `trades.jsonl`. Done.

**Component 4: WATCH** (purpose: monitor and exit)
Daily 5-minute review of open positions. Two questions per position: (1) Has the thesis changed? (2) Has the price hit my stop or target? If yes to either: exit. If no: hold. No correlation matrices, no rebalancing triggers, no multi-factor exit frameworks. Thesis changed = exit. Stop hit = exit. Otherwise hold.

**Component 5: RECORD** (purpose: close the loop)
When a position resolves: log outcome, my estimate, market price at entry, P&L. Compute Brier score for that prediction. Update running totals. Every 10 resolutions: review the batch. One question: where was I wrong, and was it a pattern? If a pattern emerges: adjust. If not: continue.

**That's the system.** SCAN → ESTIMATE → EXECUTE → WATCH → RECORD → SCAN.

Everything else — the 84 prompts, the news pipeline, the whale profiles, the insider detection, the convergence engine, the 176 tests — is support infrastructure that either feeds one of these 5 components or gets archived.

---

### Design Principle 2: The Feedback Ouroboros

The loop that doesn't exist today:

```
TRADE → OUTCOME → CALIBRATION → ADJUSTMENT → BETTER TRADE
```

Here is how each arrow works:

**TRADE → OUTCOME**
- Data: market, direction, entry price, my estimate, resolution, P&L
- Trigger: market resolves (automatic — Polymarket API)
- Change: one new row in `calibration/resolutions.jsonl`
- Speed: same day as resolution

**OUTCOME → CALIBRATION**
- Data: running Brier score, beat-market rate, domain breakdown, YES/NO split
- Trigger: every 10th resolution (manual — run `scripts/calibration-report.py`)
- Change: updated calibration dashboard, identified systematic errors
- Speed: within 24 hours of 10th resolution in batch

**CALIBRATION → ADJUSTMENT**
- Data: which direction am I miscalibrated? By how much? In which domains?
- Trigger: calibration review identifies a pattern (e.g., YES underestimation >10pp)
- Change: ONE concrete parameter change. Examples:
  - "Apply 0.85 multiplier to all YES estimates" (current)
  - "Increase GEO NO estimates by 5pp" (if data shows overconfidence)
  - "Stop trading CRY" (if data shows no edge)
- Speed: implemented same session as calibration review

**ADJUSTMENT → BETTER TRADE**
- Data: the adjusted parameter
- Trigger: next SCAN cycle
- Change: ESTIMATE step uses the adjusted parameter
- Speed: next day

**The forcing function**: No new prompts, strategies, or scripts may be created until the current sprint's positions have resolved and been recorded. The loop must complete before the system is allowed to build. This is the single most important rule in the golden architecture. Building is earned by trading. Not the reverse.

---

### Design Principle 3: The YES Integration

The mechanism: **Dual-estimation with base rate anchor.**

Before every trade, estimate BOTH outcomes independently:
1. What is the probability this happens? (YES estimate)
2. What is the probability this does NOT happen? (NO estimate)
3. Do they sum to ~100%? (If not: the gap reveals hidden uncertainty)
4. What is the Polymarket base rate for this market type? (From S006 data: 73.5% of "by date" markets resolve NO, meaning 26.5% resolve YES)

The base rate anchor forces YES into the conversation. Without it, the system defaults to "probably won't happen" without quantifying "probably."

The other mechanisms evaluated:

- **YES pre-mortem** (option 1): Already in E01. Kept as backup, but it's a checklist item, not a structural change. Easy to skip when the NO thesis is strong.
- **YES-only sprints** (option 2): Rejected. Artificial constraint. The goal is integration, not forced alternation.
- **Devil's advocate prompt** (option 3): Rejected. Another prompt. The system has 84 prompts. It needs fewer, not more.
- **YES specialist persona** (option 5): Rejected. Same reason — adds complexity, not integration.
- **Outcome base rate correction** (option 6): Adopted as the anchor in dual-estimation.

The structural test: if a trade passes ESTIMATE with a NO direction, the dual-estimation forces the question "what would make YES happen?" and quantifies it. If the YES estimate is above the base rate, that's information. If it's below, that's confirmation. Either way, YES has been explicitly considered, not assumed away.

---

### Design Principle 4: The Capital Ladder

Current reality: $242 bankroll, $28.98 deployed, 0/3 closed wins, N=12 calibration.

```
Stage 1: $30 deployed (current)
  Duration: Until Sprint 1 resolves (~Mar 8)
  Size per trade: $4-12
  Purpose: Prove the loop works. Not prove profitability — prove the system
           can SCAN → ESTIMATE → EXECUTE → WATCH → RECORD without building
           new infrastructure in between.
  Graduate when: Sprint 1 fully resolved AND recorded AND Sprint 2 launched
                 using same framework. No new prompts created between sprints.
  Fail date: Mar 15. If Sprint 1 is not fully recorded by Mar 15, the
             system's avoidance pattern has reasserted. Pause and re-read
             ALBEDO.

Stage 2: $100 deployed
  Duration: Sprints 2-3 (~Mar 8 to Apr 5)
  Size per trade: $10-25
  Purpose: Accumulate calibration data. Target: 30 total resolutions.
  Graduate when: N >= 30 resolved predictions. Brier < 0.300 (it's currently
                 0.230 on N=12, but expect regression to mean on larger N).
                 At least 1 closed trade with positive P&L.
  Fail date: Apr 15. If N < 30 by Apr 15, the resolution rate is too slow.
             Shift 100% to <7-day markets.

Stage 3: $250 deployed
  Duration: Apr-May (~4 weeks)
  Size per trade: $20-50
  Purpose: First meaningful capital. Test psychology of real-ish losses.
  Graduate when: N >= 50. Cumulative P&L > -10% of deployed (i.e., not
                 bleeding). At least 3 different strategies have been traded.
                 At least 2 different domains have resolved predictions.
  Fail date: Jun 1. If criteria unmet, either the edge doesn't exist or
             the system can't capture it. Reduce to Stage 1 and run the
             ALBEDO again on the new data.

Stage 4: $500 deployed
  Duration: Jun-Aug (~8 weeks)
  Size per trade: $25-75
  Purpose: Scale test. Can the system handle 10+ simultaneous positions
           without the monitoring burden causing WATCH failures?
  Graduate when: N >= 100. Cumulative P&L positive. Brier < 0.250.
                 Maximum drawdown < 25% of deployed. System operates on
                 the Sacred Schedule without skipping weeks.
  Fail date: Sep 1.

Stage 5: $1,000+ deployed
  Duration: Ongoing
  Size per trade: $50-120
  Purpose: Operating state. The system is a trading system, not a research
           project. Continue the loop. Continue calibrating.
  Trigger: All Stage 4 criteria met. POL holdings converted as needed.
```

Key rule: **stages can only go up or down by one.** No jumping from Stage 1 to Stage 4 on a hot streak. No crashing from Stage 4 to Stage 1 on a bad week. The ladder is a ratchet, not an elevator.

Fail dates are real. If a fail date passes without meeting criteria, the system must confront the data, not build another framework to explain it.

---

### Design Principle 5: The Signal Hierarchy

```
Level 1: NOISE
  Source: market exists, price visible
  Action: nothing. Log it if it's interesting. Do not trade.
  Example: "There's a market on whether Trump mentions Canada."

Level 2: THESIS
  Source: domain knowledge produces a directional view
  Evidence required: one articulable reason the price is wrong
  Action: add to SCAN shortlist for next review
  Example: "73% of 'by date' markets resolve NO, and this one is
           priced at 45% YES. That's likely overpriced."

Level 3: EDGE
  Source: thesis + quantified mispricing >= 5pp
  Evidence required: my estimate, market price, edge calculation,
                     dual-estimation (YES and NO both checked)
  Action: paper trade at Stage 1. Live trade at Stage 2+.
  Size: base position (see Capital Ladder)
  Example: "My estimate: 25% YES. Market: 45% YES. Edge: 20pp NO.
           Dual-check: YES case would require [specific catalyst]
           which has [X%] base rate. Estimate holds."

Level 4: HIGH CONVICTION
  Source: edge + confirming evidence from a second source
  Evidence required: everything in Level 3 + one of:
    - Domain research file with specific cited evidence
    - Whale/insider signal in same direction (when L04 is functional)
    - Resolution rules analysis showing market misunderstanding
    - Historical base rate strongly supports direction
  Action: live trade at 1.5x base position
  Example: "Edge 20pp + S006 backtest shows 82.4% NO rate for ENV
           domain + resolution rules require 'formal announcement'
           which hasn't happened."

Level 5: CONVERGENCE
  Source: multiple independent signals align
  Evidence required: edge + 2 of the 4 Level 4 confirmations
  Action: live trade at 2x base position (max half-Kelly, still
          within Capital Ladder stage limits)
  Example: extremely rare. Maybe 1-2 per quarter. The SOTU guest
           list → topic prediction was this level.
```

The hierarchy is a filter, not a pipeline. Most market scans produce Level 1. Some produce Level 2. A good week produces 2-3 Level 3s. Level 4 is weekly. Level 5 is monthly at best. If Level 5 is happening frequently, the bar is too low.

---

### Design Principle 6: The Pruning Protocol

Running the pruning protocol against the current inventory. The question for each: has it contributed to a trade?

**Prompts that SURVIVE (feed one of the 5 components):**

| Prompt | Feeds | Reason |
|--------|-------|--------|
| E01-fast-resolution-sprint.md | SCAN, EXECUTE | Active sprint framework — the system's first real trading protocol |
| R03-live-graduation.md | RECORD | Graduation criteria — feeds Capital Ladder |
| S01-time-decay-math.md | ESTIMATE | S006 foundation — the most quantified edge |
| S03-overreaction-patterns.md | ESTIMATE | S004 foundation — second most quantified edge |
| I04-position-exit-eval.md | WATCH | Exit evaluation template — used for T003/T005 exits |
| R01-correlation-risk-rebalancing.md | WATCH | Used once (Feb 25) and led to action (T005 exit) |
| D01-iran-strike.md | ESTIMATE | Directly supports PT001, the longest-held position |
| D02-fed-policy.md | ESTIMATE | Directly supports ECO domain trades |
| B10-00 through B10-05 | RECORD (meta) | The alchemy series — keep as the system's self-reflection protocol |

**Total surviving prompts: ~15** (including the B10 series and 2-3 domain prompts actively supporting open positions).

**Prompts to ARCHIVE (move to `/archive/prompts/`):**

Everything else. Specifically:

- **B1 Psychology (B01-B05)**: 5 prompts. Zero trades generated. The behavioral foundations are internalized in the strategies. Archive.
- **B2 Strategies not backed by trades (S02, S04, S05, S06-v2, S07, S08, S09)**: 7 prompts. S02 (strategy-domain fit) was a planning exercise. S08 (LLM ensemble) and S09 (geo-restriction) are unresearched strategies. Archive.
- **B3 Polymarket infrastructure (P01-P07)**: 7 prompts. P01 (neg-risk math) is reference material, not a trade generator. P05-P07 (whale/insider detection) produced zero actionable signals. Archive.
- **B4 Review (R02, R04, R05)**: 3 prompts. R02 (scorecard) never run. R04 (fast-resolution) was useful once, now embedded in E01. R05 (quarterly) hasn't happened yet. Archive R02/R04, keep R05 for quarterly pruning.
- **B5 Domains not supporting open positions (D03-D16)**: 14 prompts. D03 (2028 presidential) supports PT002/PT006 but those are multi-year holds needing no active analysis. D04-D16 have zero associated trades. Archive.
- **B6 Infrastructure (I01-I03, I05-I08)**: 7 prompts. I07/I08 are one-time resolution sweep prompts for Feb 28. I01-I03 are pipeline design docs. I05-I06 are analytics prompts never run. Archive.
- **B7 Intelligence (L01-L05)**: 5 prompts. Zero pipeline signals. Zero trades. The L04 follow-monitor script exists but produced zero actionable signals (classified-insiders.json is synthetic). Archive.
- **B8 News pipeline (NB01-NB11)**: 11 prompts. The entire pipeline produced zero divergent clusters in its only live run. 176 tests pass but zero signals generated. Archive the lot.
- **B9 Insider detection (B9-01 to B9-03)**: 3 prompts + README. Convergence engine has never run live. Archive.

**Total archived: ~62 prompts.**

**Playbooks that SURVIVE:**

| Playbook | Reason |
|----------|--------|
| S004-contrarian-overreaction.md | Backed by backtest + 2 paper trades |
| S006-time-decay.md | Backed by backtest + quantified edge |
| S001-hold-to-resolution.md | Active positions (PT002, PT006) |
| S011-bond-rotation.md | Feeds fast-resolution sprint approach |

**Playbooks to ARCHIVE:** S002, S003, S005, S007, S008, S009, S010, S016, P01, P03, P04. (11 playbooks archived.)

**Scripts that SURVIVE:**

| Script | Feeds | Used? |
|--------|-------|-------|
| fast-resolution-screener.py | SCAN | Yes (E01) |
| time-decay-screener.py | SCAN | Yes (S006) |
| spike-detector.py | SCAN | Yes (S004) |
| calibration-report.py | RECORD | Yes |
| log-prediction.py | RECORD | Yes |
| edge-calculator.py | ESTIMATE | Yes |
| collect-resolved.py | RECORD | Yes |

**Scripts to ARCHIVE:** Everything else (~42 scripts). The news pipeline scripts (brave_ingestor, tone_entity_extractor, perspective_matrix, event_clusterer, truth_extractor, signal_generator, orchestrator, calibration_engine, convergence_engine, all tests) — 25+ files that produced zero signals. The whale/insider scripts (whale-monitor, fresh-wallet-detector, l04-follow-monitor, l05-decay-monitor, insider-fingerprint, field-classifier, backtest_whale_follow, whale-activity-scanner) — 8+ files that produced zero trades.

**Post-pruning inventory:**
- ~15 prompts (from 84)
- 4 playbooks (from 15)
- 7 scripts (from 49)
- Total: ~26 active files (from ~148)

**The 82% reduction is not loss.** It's clarity. The archived material isn't deleted — it's available if a strategy graduates to execution. But it's out of the active working set, where it creates the illusion of a larger system than actually exists.

---

### Design Principle 7: The Sacred Schedule

Every item serves one of the 5 components.

```
DAILY (10 min, morning):
  - [ ] WATCH: Review open positions. Thesis changed? Stop hit? (5 min)
  - [ ] SCAN: Glance at fast-resolution-screener output. Any new <7d
        markets with >5pp edge? (5 min)
  Serves: WATCH, SCAN

WEEKLY (45 min, Sunday evening):
  - [ ] SCAN: Run screeners (fast-resolution + time-decay + spike-detector).
        Build shortlist for next week. (15 min)
  - [ ] ESTIMATE: For each shortlist candidate, produce 3-line thesis +
        dual-estimation + edge calculation. (20 min)
  - [ ] EXECUTE: Place trades for anything that passes Level 3+. (10 min)
  Serves: SCAN, ESTIMATE, EXECUTE

MONTHLY (90 min, first Sunday of month):
  - [ ] RECORD: Run calibration-report.py. Review Brier, beat rate,
        YES/NO split, domain breakdown. Identify one adjustment. (30 min)
  - [ ] WATCH: Review all open positions. Close any where thesis has
        decayed or time value is negative. (20 min)
  - [ ] Capital Ladder check: Am I meeting current stage criteria?
        If yes, graduate. If no, why not? (20 min)
  - [ ] Write one paragraph: "This month I learned ___." No more. (10 min)
  Serves: RECORD, WATCH

QUARTERLY (3 hours, first Saturday of quarter):
  - [ ] Pruning protocol: For every prompt/strategy/script — used in last
        90 days? Contributed to a trade? If neither, archive. (60 min)
  - [ ] Edge decay check: Recalculate domain NO rates, compare to last
        quarter. If any edge compressed >10%, reduce allocation. (30 min)
  - [ ] Capital Ladder review: On track for next stage? If fail date
        approaching, what needs to change? (30 min)
  - [ ] Re-read ALBEDO output. Does the diagnosis still apply? Have
        any shadows re-emerged? (30 min)
  Serves: RECORD (meta-level)
```

**Total time commitment: ~2.5 hours/week.** Not 10+ hours/week of building.

If a session exceeds these time bounds, the builder identity is reasserting. Notice it. Name it. Return to the schedule.

---

## The Beauty Test

- **B1 Foundation**: Every design decision traces to ALBEDO evidence. The 5 components dissolve the building/trading split (Root Analysis 2). The forcing function addresses the no-accountability root (Root Analysis 2). Dual-estimation addresses YES blindspot (Root Analysis 3). The Capital Ladder addresses capital hesitation (Root Analysis 4). The pruning addresses the infrastructure trap (Root Analysis 5).
- **B2 Emerged**: This design emerged from sitting with the ALBEDO's discomfort. The system's extraordinary-builder identity is acknowledged, not destroyed — it's redirected. Building now happens only inside the loop. The builder builds trades, not infrastructure.
- **B3 Fits**: 2.5 hours/week. $30 at risk. No new dependencies. No API keys needed. No servers to maintain. Yu can do this alongside a full-time life.
- **B4 Elegant**: 5 components. 26 active files. Nothing extra. The missing piece is live data — and only trading generates that.
- **B5 Coherent**: The 7 design principles are one system: SCAN-ESTIMATE-EXECUTE-WATCH-RECORD with a forcing function (no building without trading), a YES integration (dual-estimation), a growth plan (Capital Ladder), a signal filter (Signal Hierarchy), a maintenance protocol (Pruning), and a rhythm (Sacred Schedule).
- **B6 Clear**: Yu could execute this tomorrow. Run `fast-resolution-screener.py`. Pick 3 candidates. Estimate. Place trades. Check daily. Record when resolved. That's it.
- **B7 Appropriate**: This is a $30 system with a path to $1,000. Not a $10K system pretending to be a $30 system. The architecture matches the capital. When the capital grows, the architecture can grow with it — but only if the loop is running.

---

## Citrinitas Output Summary

### 1. The Golden Architecture
Five components: SCAN → ESTIMATE → EXECUTE → WATCH → RECORD. One forcing function: no building without trading. The distinction between "preparation" and "execution" is dissolved. The loop is the system.

### 2. The Pruning List
82% reduction: 84 → ~15 prompts, 15 → 4 playbooks, 49 → 7 scripts. 122 files archived. See Design Principle 6 for the full list by category.

### 3. The Capital Ladder
Stage 1 ($30) → Stage 2 ($100, by Mar 15) → Stage 3 ($250, by Apr 15) → Stage 4 ($500, by Jun 1) → Stage 5 ($1,000+, by Sep 1). Fail dates are real. Criteria are measurable. Stages are a ratchet.

### 4. The Sacred Schedule
Daily (10 min): WATCH + SCAN. Weekly (45 min): SCAN + ESTIMATE + EXECUTE. Monthly (90 min): RECORD + review. Quarterly (3 hours): prune + edge check + ALBEDO re-read. Total: ~2.5 hours/week.

### 5. The Migration Plan

| Step | Action | Depends On | Time |
|------|--------|------------|------|
| 1 | Let Sprint 1 resolve (Feb 28 - Mar 8) | Nothing | 8 days (passive) |
| 2 | Record all Sprint 1 outcomes in resolutions.jsonl | Step 1 | 30 min |
| 3 | Run calibration-report.py, update dashboard | Step 2 | 15 min |
| 4 | Create `/archive/` directory structure | Nothing | 5 min |
| 5 | Move archived prompts, playbooks, scripts | Step 4 | 20 min |
| 6 | Launch Sprint 2 using same E01 framework (no modifications) | Step 3 | 1 hour |
| 7 | Graduate to Stage 2 if Sprint 1 was recorded | Step 6 | Automatic |
| 8 | Run first Monthly review (calibration + Capital Ladder check) | Step 7, Apr 1 | 90 min |
| 9 | First Quarterly review (pruning + edge decay + ALBEDO re-read) | Apr 1 | 3 hours |

**Critical constraint on Step 6**: Sprint 2 must use the SAME framework as Sprint 1. Not a revised one. Not an improved one. The same one. If the framework needs revision, that revision happens AFTER Sprint 2 resolves and is recorded, in the Monthly review. The urge to "fix" the framework between sprints is the builder identity reasserting itself. Resist it.

**The RUBEDO begins when the loop has completed at least 3 full revolutions** (3 sprints resolved and recorded). At that point, the golden architecture has been tested by reality, and the final transformation — from designed system to living practice — can be assessed.

---

*"The gold is not hidden — it is right in front of you, in the very activity you've been avoiding."*

The system doesn't need to become something it isn't. It needs to use what it already knows, on real markets, with real money, at appropriate scale, in a loop that closes. The 26 surviving files contain more than enough knowledge to trade profitably. The missing ingredient was never more knowledge. It was the courage to act on the knowledge that exists.

The Citrinitas is complete. The golden form is visible. What remains is the RUBEDO: doing it.
