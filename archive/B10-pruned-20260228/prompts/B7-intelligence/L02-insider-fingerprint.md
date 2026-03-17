# L02 — Insider Fingerprint: Localisation Test

You are a quantitative analyst running the second stage of the insider detection pipeline. L01 gave you raw edge profiles for all accounts. L02's job is to distinguish between two very different types of edge:

- **Superforecasters** — broad positive edge across 3+ categories. Good researchers. Edge comes from rigour, not privileged information. Useful signal but not an insider.
- **Insiders** — extreme positive edge in 1-2 categories, near-zero everywhere else. Edge comes from information others cannot access. The category specificity is the fingerprint.

## Read First

1. `~/Desktop/prediction-markets/data/edge-profiles.json` — output from L01 (required)
2. `~/Desktop/prediction-markets/research/whale-signal-research.md` — known profiles for validation
3. `~/Desktop/prediction-markets/prompts/intelligence/L01-edge-calculator.md` — understand edge calculation methodology

---

## Task 1: The Localisation Score

### 1a. Concept

An insider's edge is concentrated. Define **Localisation Score (LS)**:

```
For account A with edge scores e_1, e_2, ... e_k across k categories:

  LS = max(e_i) / (mean(e_all) + ε)

Where:
  max(e_i)  = highest category edge (the speciality)
  mean(e_all) = average edge across ALL categories
  ε = 0.001 (prevent division by zero)

Interpretation:
  LS = 1.0 → edge equally distributed across all categories (superforecaster)
  LS = 5.0 → edge in one category is 5× the average (probable specialist)
  LS > 8.0 → extreme localisation (probable insider)
```

**Important**: Only use categories where N >= 10 resolved trades. Categories with fewer bets are too noisy to include in the calculation.

### 1b. Secondary Test: Edge Contrast

The localisation score alone can be misleading if the overall edge is tiny. Complement with an **Edge Contrast Score**:

```
For account A's top category C:
  ECS = mean_edge(C) − mean_edge(¬C)

Where mean_edge(¬C) = average edge across all categories EXCEPT C

Interpretation:
  ECS > 0.05 → this person knows something specific to this category
  ECS > 0.10 → strong evidence of category-specific advantage
  ECS > 0.20 → very strong evidence — probable insider
```

### 1c. Combined Insider Score

```python
def insider_score(account):
    """
    Combines localisation, edge contrast, and statistical significance
    into a single 0-10 score.

    Components:
    1. Localisation Score (0-4 pts): LS mapped to 0-4 scale
       LS < 2.0  → 0 pts
       LS 2-4    → 1 pt
       LS 4-6    → 2 pts
       LS 6-8    → 3 pts
       LS > 8    → 4 pts

    2. Edge Contrast Score (0-3 pts):
       ECS < 0.05  → 0 pts
       ECS 0.05-0.10 → 1 pt
       ECS 0.10-0.20 → 2 pts
       ECS > 0.20  → 3 pts

    3. Statistical Significance (0-2 pts):
       p > 0.10   → 0 pts
       p 0.05-0.10 → 1 pt
       p < 0.05   → 2 pts

    4. Sample Size Confidence (0-1 pt):
       N_top_category >= 30 → 1 pt
       N_top_category < 30  → 0 pts

    Total: 0-10 scale
    """

    score = 0
    # ... implementation
    return score

INSIDER_SCORE_THRESHOLDS = {
    "high_confidence": 7.0,   # Very likely has category-specific inside info
    "medium_confidence": 4.0, # Worth monitoring, investigate further
    "low_confidence": 2.0,    # Possibly skilled, not clearly insider
}
```

---

## Task 2: Superforecaster vs Insider Separation

### 2a. The Two Profiles

Build a classifier that assigns each account to one of four types:

```python
ACCOUNT_TYPES = {
    "INSIDER":        insider_score >= 7 AND n_significant_categories <= 2,
    "SUPERFORECASTER": n_significant_categories >= 3 AND overall_mean_edge > 0.03,
    "SPECIALIST":     insider_score 4-7 OR (n_sig == 2 AND ECS > 0.08),
    "NOISE":          below significance thresholds — excluded from signal list
}
```

**Why both matter for our system:**
- **INSIDER** → follow only in their dominant category. Ignore their bets elsewhere.
- **SUPERFORECASTER** → follow as a general signal. Their domain bets all carry weight.
- **SPECIALIST** → follow with moderate confidence in their top 1-2 categories.

### 2b. Profile Examples

Expected profiles for known wallets (use as validation):

```
Theo (0x...):
  POL edge: +0.14, n=180, p=0.00001
  GEO edge: +0.02, n=12, p=0.64
  ECO edge: -0.01, n=8, p=0.91
  LS: ~9.0  ECS: ~0.14  → Type: INSIDER (POL)

AlphaRaccoon (0x...):
  TEC edge: +0.31, n=23, p=0.0002
  POL edge: +0.01, n=5, p=0.87
  LS: ~15.0  ECS: ~0.30  → Type: INSIDER (TEC)

Tetlock-style superforecaster (hypothetical):
  POL edge: +0.06, n=120, p=0.001
  GEO edge: +0.05, n=80, p=0.008
  ECO edge: +0.04, n=60, p=0.03
  LS: ~1.2  ECS: ~0.01  → Type: SUPERFORECASTER
```

---

## Task 3: Flag Registry

### 3a. Build the Insider Registry

Output: `~/Desktop/prediction-markets/data/insider-registry.json`

Distinct from `whale-registry.json` (which was manually curated based on P&L). The insider registry is **mathematically derived** — populated entirely from edge profiles, no prior knowledge needed.

```json
{
  "generated_at": "2026-02-26T10:30:00Z",
  "methodology": "L01 edge calculation + L02 localisation test",
  "accounts": [
    {
      "wallet": "0x...",
      "alias": "Inferred-POL-01",  // named by us, not publicly known
      "account_type": "INSIDER",
      "insider_score": 8.4,
      "dominant_category": "POL",
      "secondary_category": null,
      "localisation_score": 9.2,
      "edge_contrast": 0.18,
      "top_category_edge": 0.21,
      "top_category_n": 67,
      "top_category_p": 0.0003,
      "overall_edge": 0.023,
      "total_profit_usd": 8420,
      "first_trade": "2025-03-14",
      "last_trade": "2026-02-18",
      "follow_confidence": 4,  // 1-5
      "notes": "Consistently profitable on US political markets. Negligible edge in all other domains. High conviction bets (avg $3K). Possible political operative or campaign staffer."
    }
  ]
}
```

### 3b. Auto-Generate Aliases

For unknown wallets, auto-generate descriptive aliases:

```python
def generate_alias(wallet, dominant_category, insider_score, profile_index):
    """
    Auto-generate a human-readable alias for an unidentified insider.

    Examples:
      "POL-Insider-01" — high-score POL insider
      "GEO-Specialist-03" — medium-score GEO specialist
      "CRY-Superforecaster-01" — broad crypto/TEC superforecaster
    """
    type_label = "Insider" if insider_score >= 7 else "Specialist"
    return f"{dominant_category}-{type_label}-{profile_index:02d}"
```

---

## Task 4: Sensitivity Analysis

### 4a. False Positive Rate

The biggest risk: a lucky bettor looks like an insider. Estimate the false positive rate:

```python
"""
Simulation: Generate 10,000 synthetic accounts with ZERO true edge.
Give each a random number of trades (drawn from empirical distribution).
Apply edge calculator + localisation test.

Expected result: ~5% will pass the p<0.05 significance threshold by chance.
At N=15,000 accounts → ~750 false positives at p<0.05.
At p<0.01 → ~150 false positives.
At p<0.001 + LS>8 → ~10-20 false positives.

Report: At what combined threshold does the false positive rate drop to
acceptable levels (e.g., <10% of flagged accounts are false positives)?
"""
```

### 4b. Minimum Trade Threshold

Run sensitivity analysis on MIN_TRADES_PER_CATEGORY:
- At N=10: more accounts qualify, more false positives
- At N=20: tighter qualification, fewer false positives but miss accounts who trade selectively
- At N=30: very tight, likely only catches the most systematic insiders
- Recommended default: N=15, with confidence levels reported separately

---

## Output

1. `scripts/insider-fingerprint.py` — takes edge-profiles.json as input, outputs insider-registry.json
2. `data/insider-registry.json` — full registry of mathematically-detected insiders + specialists
3. Terminal report: top 20 accounts by insider score, with their dominant category + edge stats
4. Validation: do Theo, AlphaRaccoon, and known whales appear at the top of the insider list?
5. Sensitivity analysis: estimated false positive rate at current thresholds

**Done when**: The insider registry is populated, false positive rate is estimated, and the known validation cases (Theo, AlphaRaccoon) score at the top of their respective categories.
