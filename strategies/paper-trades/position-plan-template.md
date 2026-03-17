# Pre-Position Concentration Check

*Complete this checklist before opening ANY new position. Rules reference: research/position-sizing-rules.md*

---

## Step 1: Identify the Thesis

**What is the underlying event/thesis this bet depends on?**

> _______________________________________________

**Is this a new thesis or one I already have exposure to?**

> [ ] New thesis (no existing positions depend on this outcome)
> [ ] Existing thesis (go to Step 2)

---

## Step 2: Check Existing Exposure

**What existing positions depend on the SAME underlying event?**

| Position | Market | Deployed | Direction |
|----------|--------|----------|-----------|
| | | $ | |
| | | $ | |
| | | $ | |

**Current deployed exposure to this thesis**: $_______ / _______% of bankroll

**After this trade, thesis exposure would be**: $_______ / _______% of bankroll

---

## Step 3: Rule C1 — Single Event Cap (3%)

**Does this trade push thesis exposure above 3% of bankroll ($300)?**

> [ ] NO → Proceed to Step 4
> [ ] YES → STOP. Either:
>   - Reduce size to fit within cap
>   - Document override rationale below (hard cap: 5% / $500)

**Override rationale (if applicable):**

> _______________________________________________
> Why is additional exposure justified? What differentiates this from the existing position(s)?

---

## Step 4: Rule C3 — Correlation Check

**Estimated correlation with existing same-thesis positions:**

| Existing Position | Estimated ρ |
|-------------------|-------------|
| | |
| | |

**Average ρ with existing thesis positions**: _______

> [ ] ρ < 0.30 → Position is sufficiently differentiated. Proceed.
> [ ] ρ ≥ 0.30 → Position is correlated. Must be sized via Kelly adjustment (Step 5).
> [ ] ρ ≥ 0.80 → Position is functionally identical. **Should not be opened** unless hedging.

---

## Step 5: Kelly-Adjusted Position Size

```
Strategy-specific size:         $_______  (from playbook)
Full Kelly:                     f* = (bp - q) / b = _______
Quarter Kelly:                  0.25 × f* = _______% = $_______
Correlation adjustment:         (1 - ρ_avg) = _______
Kelly-adjusted size:            quarter_Kelly × (1 - ρ_avg) = $_______
C1 remaining cap:               3% cap - existing exposure = $_______
C2 remaining cap:               10% domain cap - domain exposure = $_______
```

**Final position size = min of all four**: **$_______**

---

## Step 6: Rule C2 — Domain Check

**What domain is this position in?** _______

**Current domain exposure**: $_______ / _______% of bankroll

**After this trade**: $_______ / _______% of bankroll

**Does this exceed the 10% domain cap?**

> [ ] NO → Proceed
> [ ] YES → Reduce size or choose a different domain

---

## Step 7: Portfolio Snapshot

| Cluster | Positions | Deployed | % Bankroll | After This Trade |
|---------|-----------|----------|------------|------------------|
| | | $ | % | $ / % |
| | | $ | % | $ / % |
| | | $ | % | $ / % |
| **Total** | | $ | % | $ / % |

**Effective N before this trade**: _______
**Effective N after this trade**: _______

---

## Approval

> [ ] All concentration checks passed
> [ ] Override documented (if applicable)
> [ ] Position sized at minimum of Kelly-adjusted, C1, C2, and strategy-specific

**Proceed with entry at: $_______ size**
