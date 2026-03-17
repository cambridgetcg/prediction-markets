# Lessons Learned

*Record of forecasting mistakes and what they taught me.*

## Template

### [Date] — [Market]
- **My estimate**: X%
- **Market price**: Y%
- **Outcome**: Yes/No
- **What went wrong**: [analysis]
- **Mental model failure**: [which model broke]
- **Update**: [what I'll do differently]

---

## 2026-02-25 — SOTU 2026 Post-Mortem (Batch Analysis)

### Overall
- 428 sub-markets across 22 events, ~$9.5M total volume
- 70% of mention markets resolved YES (base rate)
- Hypothetical: beat market on 17/20 estimates, 34% better Brier score

### Lesson L01: SOTU ≠ Rally
- **My estimate**: "Fake News" 15%, "MAGA" 35%
- **Market price**: "Fake News" 52%, "MAGA" 87%
- **Outcome**: Both NO
- **What went right**: Recognized that formal SOTU language differs fundamentally from rally language
- **Mental model**: Trump has two registers — rally (nicknames, "fake news", "MAGA") and SOTU (policy, "America", guest stories). Market is dominated by rally-watchers.
- **Update**: For ALL future Trump speech markets, first classify each word as rally-native vs SOTU-native. Rally-native words in SOTU context should be priced at 20-35%, not 50%+.

### Lesson L02: Strategic Omissions Are Predictable
- **My estimate**: China mention 75%
- **Market price**: 93%
- **Outcome**: NO (barely mentioned)
- **What went wrong**: Even with diplomatic calendar insight, I would have been directionally wrong (still >50% YES). Needed to weight the "diplomatic protocol" signal higher.
- **Mental model failure**: Assumed "Trump talks about everything" — but he actually exercises strategic discipline on countries he's about to negotiate with.
- **Update**: Check diplomatic calendar before estimating any country-mention market. Country with upcoming Trump visit/meeting → reduce estimate by 30-40pp from base rate.

### Lesson L03: Guest List = Strongest Pre-Speech Signal
- **Markets affected**: Hockey (YES), Olympics (YES), Alien/immigration content, specific person mentions
- **What went right**: The guest list leaked 48-72h before speech. Each guest maps to a topic segment and related word mentions.
- **Update**: For future SOTU markets, the guest list is the first research step. Each confirmed guest = near-certain topic segment.

### Lesson L04: Length Predicts Threshold Markets
- **Outcome**: 108 minutes, 10,617 words. Longest SOTU since 1964.
- **What went right**: Longer speech → more word mentions → threshold markets ("X times+") become more likely
- **Update**: Trade duration markets FIRST, then condition word-count threshold bets on duration outcome. Trump's pre-speech comment ("it'll be a long speech") was a 30pp signal for the 100+ minute market.

### Lesson L05: What I Missed (Honest)
- **SOTU date**: Assumed March 4, was Feb 24. Would have missed the entire event.
- **"Middle East" as term**: Trump discussed Iran without saying "Middle East" — geographic term vs topic coverage is a different bet.
- **"No No No"**: Underestimated Trump's improvised repetitive negation style.
- **"Obama" blame**: Didn't model the "blame predecessor" pattern.
- **China NO**: Even recognizing the diplomatic calendar, would have been directionally wrong.

### Meta-Lesson T12: Fast-Resolution Events Are Calibration Gold
- 428 markets resolving in 24h = more calibration data than all our long-duration trades combined
- Future strategy: prioritize catalyst events (SOTU, debate, summit) for calibration building
- Paper trade these aggressively even with small size — the learning value exceeds the P&L

---

## 2026-02-25 — Strategy Scorecard Review (Batch Analysis)

### Lesson L06: Strategy Misclassification Distorts Performance Tracking
- **Trades affected**: PT001 (S006→S004), PT002 (S007→S001)
- **What went wrong**: PT001 at 66.5% YES was labeled S006 (time decay) but S006 requires tail events (YES < 25%). PT002 at 2.8% YES was labeled S007 (arb) but was really a hold-to-resolution bet on a legally impossible outcome.
- **Mental model failure**: Assigning strategy labels based on vague thematic fit rather than verifying all entry criteria are met.
- **Update**: Before assigning a strategy label, verify ALL entry criteria from the playbook. If any criterion fails, the trade belongs to a different strategy. Added probability gate to S006: YES < 25% required.

### Lesson L07: Domain Context Determines Strategy Viability
- **Trades affected**: PT003 (S004 in GEO)
- **What went wrong**: S004 contrarian applied to Iran Mar 31 — near-term overreaction was validated (Feb 28 dropped 7.5pp), but medium-term probability ROSE because GEO risk is persistent and path-dependent. Wars don't mean-revert like debate gaffes.
- **Mental model failure**: Treating all domains equally for mean reversion. POL/CRY revert well; GEO does not.
- **Update**: Added domain restrictions to S004 playbook. GEO requires ECI ≥ 7, unambiguous emotional classification, and specific de-escalation catalyst. Best domains for S004: POL, CRY.

### Lesson L08: Capital Efficiency Is a Strategy Dimension
- **Trades affected**: PT006 (S001, Vance 2028, 2.5 year hold)
- **What went wrong**: Locking $125 for 2.5 years at a $10K bankroll. S011 could cycle through 100+ trades in the same period with higher expected returns.
- **Mental model failure**: Evaluating edge per trade without considering edge per unit of capital-time.
- **Update**: S001 restricted to < 1 year duration until bankroll exceeds $50K. Score every trade on capital efficiency before entering.

### Lesson L09: Correlation Exposure Hides in Strategy Labels
- **Trades affected**: PT003 (S004) + PT005 (S008), both Iran Mar 31 NO
- **What went wrong**: $600 exposure (6% of bankroll) to one geopolitical outcome. The different strategy labels (S004 vs S008) made them look diversified, but both lose if Iran is struck by Mar 31.
- **Mental model failure**: Treating strategy diversification as risk diversification. Same outcome = same risk, regardless of the strategy that found it.
- **Update**: Before opening any position, check if new trade has >80% outcome correlation with an existing position. If yes, skip or treat combined position as one unit for sizing.

---

## 2026-02-26 — R01 Correlation Risk Audit (Quantitative Follow-Up to L09)

*Full analysis: strategies/paper-trades/risk-report-2026-02-25.md*
*Rules: research/position-sizing-rules.md*

### Lesson L10: Effective N Is the Real Position Count
- **Finding**: 7 nominal positions, weight-adjusted effective N = **2.4 independent bets** (34% diversification efficiency). The Iran cluster (3 positions, ρ ≈ 0.92) counts as ~1.1 bets despite being 53.4% of deployed capital.
- **Why it matters**: "I have 7 positions" feels safe. "I have 2.4 bets, and one of them is 53% of my capital" does not. The effective N calculation makes concentration risk visceral.
- **Update**: Include effective N in every portfolio review. Target: effective N ≥ 0.7 × nominal N (i.e., ≥70% diversification efficiency). Current 34% is unacceptable.

### Lesson L11: Kelly Shrinks to Nearly Zero for Correlated Adds
- **Finding**: Kelly-adjusted size for the 2nd Iran position (T003) was 0.78% of bankroll ($78). Actual: $300 (3.8× oversized). For the 3rd (T005): 0.87% ($87). Actual: $300 (3.4× oversized). The formula: `f*_adj = f* × (1 - ρ_avg)`. At ρ = 0.92, only 8% of Kelly remains.
- **Why it matters**: The marginal information value of a correlated position is (1 - ρ). At 0.92 correlation, the 2nd position adds 8% incremental information but 100% incremental risk. This is a terrible trade.
- **Update**: Apply correlated-Kelly before every add to an existing thesis. If the adjustment shrinks below 1%, the position is not worth opening.

### Lesson L12: Verify Hedges Have Negative Correlation
- **Finding**: T002 (Trump NO) and T006 (Vance YES) were described as a "natural hedge." They are actually POSITIVELY correlated (ρ ≈ 0.50). Both profit from the same scenario (Trump doesn't run → Vance frontrunner). Both lose from the same scenario (Trump runs and wins nom).
- **Mental model failure**: "Opposite-sounding" ≠ negatively correlated. "Trump NO" and "Vance YES" sound like opposite sides but they're on the SAME side of the real question: "Does Trump leave the field?"
- **Update**: Before calling any position pair a "hedge," write out the 3-4 scenarios and check: is there a scenario where one wins and the other loses? If both win/lose together in the dominant scenarios, it's concentration, not hedging. This portfolio had zero natural hedges.

### Lesson L13: Concentration Rules Must Live Above Individual Playbooks
- **Finding**: S006 had good guardrails ("max 2 per conflict"). S004 and S008 had none. When T003 (S004) and T005 (S008) opened on Iran, neither strategy checked what S006 had already deployed. The system failed at the portfolio level, not the strategy level.
- **Update**: Rules C1-C4 (3% event cap, 10% domain cap, ρ<0.30 for same-event adds, pre-entry delta check) now sit above all playbooks. Every strategy sizing section should reference the Pre-Position Concentration Check template. No strategy operates in isolation.

---

## 2026-02-27 — T003/T005 Double Exit (Geneva Talks + R01 Execution)

*Full memo: strategies/paper-trades/exit-decision-2026-02-27.md*

### Lesson L14: Execute Risk Reductions Immediately
- **Finding**: R01 audit recommended T005 exit on Feb 26 at -$10.97. Execution happened Feb 27. In 24 hours, T005 moved from -$10.97 to -$73.17 — a **$62.20 cost of delay** (the single most expensive lesson in the portfolio).
- **Why it matters**: Risk reductions have negative expected value the longer they're delayed. The scenarios that trigger the reduction (adverse moves) also increase the loss. "Wait for more data" is not a valid reason to delay a risk exit — the audit finding IS the data.
- **Update**: When a risk audit recommends an exit, execute within the same session. No waiting for catalysts, next-day data, or "one more look." This is now a hard rule.

### Lesson L15: Pre-Committed Stops Are the Only Stops That Work
- **Finding**: T003's stop at 65% YES was written on Feb 26 during clear, unemotional analysis. On Feb 27 at 66% YES, the temptation was to "wait for Vienna talks" or "give it one more day." The pre-committed stop removed that option. T003 exited at -$60.00; without the stop, holding to 70%+ would have cost ~$100+.
- **Why it matters**: Stops written during calm periods are more reliable than real-time judgment during drawdowns. The whole point of a stop is that it fires when you don't want it to.
- **Update**: Every position must have a written stop in positions.json exit_rules BEFORE entry. Stops are non-negotiable once written — the only valid change is tightening, never loosening.

### Lesson L16: Wider-Scope Markets Move Faster in Crises
- **Finding**: T005 (US/Israel strikes by Mar 31) moved +8.5pp while T003 (US strikes by Mar 31) moved +5.5pp on the same day. The "Israel" component added ~3pp of additional adverse movement. Markets with broader trigger conditions (OR-type resolution) reprice more aggressively because any catalyst component can move them.
- **Why it matters**: NO positions on OR-type markets (A or B happens) are systematically riskier than NO positions on single-trigger markets during escalation. The wider the scope, the more attack surface for adverse moves.
- **Update**: When choosing between similar markets, prefer the narrower scope for NO positions. If taking wider-scope NO, size smaller to reflect the additional risk surface.

---

## 2026-03-08 — GEO Iran Strike Post-Mortem (3 Predictions Resolved)

### Lesson L17: Contrarian GEO Discount Is a Systematic Bias

- **Predictions affected**: pred-0001, pred-0003, pred-0005 (all Iran strike markets)
- **Pattern**: In all 3 cases, I estimated YES probability BELOW the market. All resolved YES. I lost to the market on all 3.
  - pred-0001: 63% mine vs 66.5% market (3.5pp below)
  - pred-0003: 52% mine vs 57.5% market (5.5pp below)
  - pred-0005: 55% mine vs 59% market (4pp below)
- **What went wrong**: I applied a "contrarian diplomatic thesis" discount to all three — Geneva talks, Gulf state basing denials, THAAD depletion, Trump not wanting war. These factors were real but insufficient against the actual escalation dynamics.
- **Root cause**: L07 (GEO doesn't mean-revert) was identified on Feb 25 but I didn't update the predictions. I stopped out the trades (L15 worked) but the underlying probability estimates remained wrong.
- **Mental model failure**: Weighting diplomatic signals as strong negative evidence against military action, when military forces were already positioned. Pre-positioned forces get used more often than they stand down.
- **Update**: For GEO military questions where forces are pre-positioned and market is >50% YES, do NOT apply a contrarian discount unless there is concrete evidence of stand-down (troop withdrawal, public de-escalation statements from heads of state, signed agreement). Diplomatic talks in progress are NOT sufficient de-escalation evidence.

### Lesson L18: GEO YES Underestimation Confirms the YES Bias Pattern

- **Combined evidence**: SOTU YES predictions: 4/7 beat market (57%). GEO YES predictions: 0/3 beat market (0%). All NO predictions: 5/5 beat market (100%).
- **The pattern is clear**: I am good at identifying what WON'T happen (NO) and systematically underestimate what WILL happen (YES). This is consistent across domains.
- **Possible causes**: (1) Anchoring to base rates when current conditions are elevated, (2) Over-weighting contrarian/diplomatic/cooling signals, (3) A general temperamental preference for NO (conservative/skeptical bias).
- **Update**: Before estimating any YES-likely outcome (market >50%), actively ask: "Am I under-weighting the evidence FOR this happening?" Apply a +3-5pp adjustment when I notice myself reaching for reasons it won't happen.

### Lesson L19: Stop-Losses Saved Capital Even When Predictions Were Wrong

- **Finding**: PT003 stopped out at -$60 and PT005 at -$73.17 on Feb 27 (L14, L15). Had they held to resolution (YES), losses would have been -$300 and -$410 respectively ($537 more). LT001 ($12 position) held through and is a total loss.
- **What went right**: Pre-committed stops (L15) and immediate execution (L14) together saved ~$537 in paper losses. The $62.20 cost-of-delay lesson (L14) was itself small compared to the total saved.
- **Update**: Stop-loss discipline is confirmed as the most valuable risk management tool. Even wrong predictions can be survived with proper exits. Continue enforcing: every position has a written stop BEFORE entry.
