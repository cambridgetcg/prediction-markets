# Live Resolution Report — [LT0XX] [Market Name]

*Resolution date: YYYY-MM-DD | Report date: YYYY-MM-DD*

---

## Trade Summary

| Field | Value |
|-------|-------|
| Trade ID | LT0XX |
| Market | [Full market question] |
| Side | YES / NO |
| Strategy | S0XX |
| Domain | XXX |
| Entry price | $X.XX |
| Entry date | YYYY-MM-DD |
| Size | $XX.XX |
| Tokens acquired | XX.XX |
| Resolution | YES / NO |
| Exit price | $X.XX (1.00 if won, 0.00 if lost) |
| P&L | +/- $XX.XX |
| Return | +/- XX.X% |
| Hold duration | X days |

---

## Prediction vs. Outcome

| Metric | Value |
|--------|-------|
| My estimate at entry | XX% |
| Market price at entry | XX% |
| Implied edge | +/- XXpp |
| Actual outcome | YES / NO |
| Brier score (mine) | X.XXX |
| Brier score (market) | X.XXX |
| Beat market? | YES / NO |

---

## Thesis Review

**Original thesis** (from calibration/predictions.jsonl):
> [Paste reasoning from prediction entry]

**What actually happened**:
> [Describe the actual events that led to resolution]

**Was the thesis correct?**
- [ ] Core thesis validated
- [ ] Core thesis partially correct but reasoning flawed
- [ ] Core thesis wrong — different mechanism drove outcome
- [ ] Core thesis wrong — outcome opposite of expected

---

## Paper Comparison

| Question | Answer |
|----------|--------|
| Did paper account hold the same market? | YES (PT0XX) / NO |
| If yes, same direction? | YES / NO |
| Paper entry price | $X.XX |
| Paper size | $XX.XX |
| Would paper have called this trade? | YES / NO |
| Paper P&L on same market | +/- $XX.XX |

**Divergence analysis** (if paper and live differed):
> [Explain why the accounts took different positions or sizes]

---

## Sizing Review

| Question | Answer |
|----------|--------|
| Size within level max? | YES / NO |
| Size appropriate for edge size? | YES / NO (edge was Xpp, Kelly suggests Y%) |
| Would you size differently now? | [Explain] |

---

## Execution Quality

| Check | Pass? |
|-------|-------|
| Correct market selected? | YES / NO |
| Correct side (YES/NO)? | YES / NO |
| Transaction confirmed on-chain? | YES / NO |
| Recorded in live-trades.md immediately? | YES / NO |
| Prediction logged in predictions.jsonl? | YES / NO |
| Resolution logged in resolutions.jsonl? | YES / NO |
| Any execution errors? | NONE / [describe] |

---

## Lessons

**What went well**:
1. [...]

**What went wrong**:
1. [...]

**What to do differently**:
1. [...]

**New lesson ID** (if applicable): T[XX] — [one-line summary]

---

## Graduation Impact

| Question | Answer |
|----------|--------|
| Current level | X |
| Resolved positions count (after this) | X |
| Win rate (after this) | X/Y (XX%) |
| Level promotion triggered? | YES / NO |
| If yes, new level | X → Y |

---

## Checklist Before Filing

- [ ] live-trades.md updated (moved from Open to Closed)
- [ ] trade-index.md updated (status → CLOSED)
- [ ] calibration/predictions.jsonl updated (resolved, outcome, brier scores)
- [ ] calibration/resolutions.jsonl new entry added
- [ ] graduation-criteria.md status updated
- [ ] Lesson captured (if any)
- [ ] This report saved as: `trades/live-resolution-LT0XX-YYYY-MM-DD.md`
