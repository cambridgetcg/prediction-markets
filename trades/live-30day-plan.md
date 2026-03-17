# Live Account 30-Day Plan (Feb 25 — Mar 27, 2026)

*Current Level: 0 (System Testing) | Max size: $12/trade | Target: Level 1 by ~Mar 7*

---

## Objective

Graduate from Level 0 → Level 1 → approaching Level 2 in 30 days by maximizing the number of clean, fast-resolving live trades while maintaining disciplined record-keeping.

---

## Priority Stack (Ordered)

### Priority 1: Bond Rotation (S011) — 5-10 trades

The fastest path to resolved trades and calibration data. Every qualifying market gets a live trade.

**Criteria**: >95% probability, <7 days to resolution, binary outcome, >$10K liquidity
**Target**: 1-2 per week
**Size**: Full $12 (Level 0) or $25 (Level 1)

**Known upcoming S011 candidates**:
| Window | Market Type | Expected |
|--------|-----------|----------|
| Mar 17-18 | FOMC hold (if >97% hold) | High confidence — trade night before |
| Weekly | Sports/earnings if criteria met | Scan Fridays |
| Mar 3+ | State primary results (if >95% polling leader) | Check weekly |

**Action**: Run S011 screener every Monday and Thursday. Any qualifying market → immediate live entry.

### Priority 2: Primary/Election Markets (S003 variant) — 2-4 trades

Fast-resolving, high-information political events.

**Known targets**:
| Date | Market | Current Status |
|------|--------|----------------|
| Mar 3 | LT003 Ken Paxton TX primary | OPEN — resolve pending |
| Mar 3 | Any other TX primary races with clear leaders | Scan by Feb 28 |
| TBD | State primaries, special elections | Scan weekly |

**Size**: Full current-level max

### Priority 3: Maintain LT001 (GEO directional) — 0 new trades

LT001 (Iran Mar 31 NO) is already open. Do NOT add more GEO positions in live.

**Rules**:
- No new Iran positions in live while LT001 is open
- If Feb 26 Geneva talks produce breakthrough → LT001 thesis strengthens, hold
- If talks collapse → monitor closely, consider early exit if YES breaches 70%
- Let this one ride to resolution (Mar 31) for long-duration calibration data

### Priority 4: Opportunistic — 0-2 trades

If a clear, fast-resolving opportunity appears that doesn't fit the above categories:
- Must meet paper-to-live filter (Tier 1 or approved Tier 3)
- Must resolve within 14 days
- Must have clear, unambiguous resolution criteria

---

## Week-by-Week Plan

### Week 1: Feb 25 — Mar 2
- **Monitor**: LT002 (Feb 28 resolution), Geneva talks impact on LT001
- **Action**: Record LT002 resolution accurately. First live P&L entry.
- **Scan**: S011 screener for bond rotation opportunities
- **Scan**: TX primary polling for additional Mar 3 entries

### Week 2: Mar 3 — Mar 9
- **Monitor**: LT003 (Mar 3 resolution)
- **Action**: Record LT003 resolution. Now have 2 live resolutions.
- **Target**: Open 2 more positions (LT004, LT005) to hit 5 total opens → Level 0 complete
- **Candidates**: S011 bond rotation, any >95% short-duration markets
- **Milestone**: Level 0 → Level 1 graduation (if 5 opens + clean records)

### Week 3: Mar 10 — Mar 16
- **Monitor**: FOMC pre-meeting pricing (Mar 17-18)
- **Action**: If rate hold is >97% by Mar 16, enter S011 bond rotation trade
- **Target**: Continue opening and closing fast-resolution trades
- **Scan**: New market detector for first-mover opportunities (P03)

### Week 4: Mar 17 — Mar 23
- **Monitor**: FOMC resolution (overnight Mar 18), approach to Mar 31 Iran deadline
- **Action**: FOMC S011 trade resolves (if placed). Scan for post-FOMC opportunities.
- **Target**: Should have 4-6 resolved live positions by now
- **Scan**: Any >95% markets resolving before Mar 27

### Week 5 (partial): Mar 24 — Mar 27
- **Monitor**: LT001 Iran Mar 31 approaching resolution
- **Review**: Count resolved positions. If 5+ clean resolutions → Level 1 → 2 promotion assessment
- **Action**: Write first live-resolution-report if not already done

---

## 30-Day Targets

| Metric | Target | Tracking |
|--------|--------|----------|
| Positions opened | 8-12 | trade-index.md |
| Positions resolved | 6-10 | live-trades.md closed section |
| Execution errors | 0 | Any error blocks Level 1 graduation |
| New strategies tested | 1-2 (S011 mainly) | paper-to-live-filter.md |
| Calibration predictions logged | 8-12 | calibration/predictions.jsonl |
| Level achieved | Level 1, approaching Level 2 | graduation-criteria.md |

---

## What NOT to Do in the Next 30 Days

1. **No long-duration live positions** (>30 days except LT001 already open)
2. **No second GEO position in live** (correlation cap)
3. **No untested strategies in live** (paper first, 3 resolutions minimum)
4. **No size increases until Level 1** (stay at $12 until 5 clean opens)
5. **No emotional entries** — if Iran escalates, do NOT panic-trade in live; paper only
6. **No skipping record-keeping** — every trade logged immediately, no "I'll do it later"

---

## Exit Criteria Checklist (End of 30 Days)

By March 27, assess:
- [ ] How many live positions resolved? (target: 6-10)
- [ ] Any execution errors? (target: zero)
- [ ] Live P&L positive or within -10%? (acceptable at this stage)
- [ ] Paper account providing useful divergence data vs live?
- [ ] Ready for Level 2 promotion? (need 10 closed for Level 2)
- [ ] Bond rotation (S011) proven as reliable live strategy?

Write assessment in: `trades/live-30day-review-2026-03-27.md`
