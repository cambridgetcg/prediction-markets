# L03 — Field Classification: What Do They Know, and Why?

You are an intelligence analyst. L01 told you WHO has edge. L02 told you WHERE their edge is localised. L03's job is to go deeper: within a category, **what specific sub-domain drives their edge**, and **what institutional position could explain it?**

This isn't just academic. Knowing that "POL-Insider-01" wins specifically on **Republican primary elections** (not all political markets) narrows who they might be (RNC operative, campaign staffer, political pollster) — and crucially, tells you WHICH markets to follow them on vs. which to ignore.

## Read First

1. `~/Desktop/prediction-markets/data/insider-registry.json` — output from L02 (required)
2. `~/Desktop/prediction-markets/data/edge-profiles.json` — full edge profiles (required)
3. `~/Desktop/prediction-markets/psychology/participant-profiles.md` — existing participant archetypes
4. `~/Desktop/prediction-markets/prompts/intelligence/L02-insider-fingerprint.md` — methodology so far

---

## Task 1: Sub-Domain Edge Decomposition

### 1a. Category Sub-Domains

Each of our 10 categories has sub-domains. For each insider in the registry, decompose their category edge to the sub-domain level:

```python
SUB_DOMAINS = {
    "POL": [
        "us-presidential",       # General election markets
        "us-republican-primary",  # GOP nomination markets
        "us-democratic-primary",  # Dem nomination markets
        "us-congressional",       # House/Senate races
        "uk-politics",            # Starmer, Labour, NHS
        "eu-politics",            # Macron, German elections
        "latam-politics",         # Maduro, Brazil, Mexico
    ],
    "GEO": [
        "middle-east-conflict",   # Iran, Israel, Gaza
        "russia-ukraine",         # War, sanctions, territory
        "china-taiwan",           # Taiwan strait, tech war
        "nato-alliances",         # NATO expansion, defence
        "nuclear-risk",           # Proliferation, arms deals
    ],
    "ECO": [
        "us-fed-rates",           # FOMC decisions
        "us-inflation",           # CPI, PCE
        "us-recession",           # GDP, unemployment
        "central-banks-global",   # BOE, ECB, BOJ
        "trade-tariffs",          # Trade war, tariffs
    ],
    "CRY": [
        "btc-price",              # Bitcoin price targets
        "eth-price",              # Ethereum
        "altcoins",               # Other tokens
        "crypto-regulation",      # SEC, CFTC rulings
        "defi-protocol",          # DeFi-specific events
        "crypto-etf",             # ETF approvals
    ],
    "TEC": [
        "ai-models",              # Model releases (GPT, Claude)
        "ai-companies",           # OpenAI, Anthropic, Google
        "big-tech-products",      # iPhone, Google Search
        "semiconductors",         # NVIDIA, TSMC, chip supply
        "tech-regulation",        # Antitrust, data laws
    ],
    "FIN": [
        "equity-indices",         # S&P, NASDAQ, FTSE
        "individual-stocks",      # Single company events
        "commodities",            # Oil, gold, wheat
        "fx-rates",               # Dollar, EUR/USD
    ],
    "LAW": [
        "us-scotus",              # Supreme Court decisions
        "us-criminal",            # High-profile criminal cases
        "corporate-litigation",   # Company lawsuits
        "international-law",      # ICC, UN resolutions
    ],
}
```

### 1b. Sub-Domain Edge Calculation

For each insider in the registry, compute edge at the sub-domain level:

```python
def subdomain_edge(wallet, category):
    """
    Takes all resolved trades for (wallet, category).
    Groups by sub-domain tag.
    Returns ranked list of sub-domains by edge.
    """
    # Filter trades to wallet + category
    # Group by sub-domain
    # For each sub-domain: compute mean_edge, N, p_value
    # Return ranked list
```

**Output per insider:**
```json
{
  "wallet": "0x...",
  "dominant_category": "POL",
  "subdomain_breakdown": [
    {
      "subdomain": "us-republican-primary",
      "n": 34,
      "mean_edge": 0.28,
      "p_value": 0.0001,
      "as_pct_of_category_edge": 0.71  // 71% of total POL edge comes from this sub-domain
    },
    {
      "subdomain": "us-presidential",
      "n": 18,
      "mean_edge": 0.09,
      "p_value": 0.08
    },
    {
      "subdomain": "us-congressional",
      "n": 12,
      "mean_edge": 0.01,
      "p_value": 0.91
    }
  ],
  "primary_subdomain": "us-republican-primary"
}
```

---

## Task 2: Institutional Hypothesis

For each top insider, generate the most plausible explanation for their edge:

### 2a. Hypothesis Framework

```python
INSTITUTIONAL_HYPOTHESES = {
    "us-republican-primary": [
        "RNC operative or campaign staffer",
        "Republican-aligned pollster with private polling",
        "Major donor with access to internal polls",
        "Political journalist with off-record sources",
        "PAC analyst with early internal data"
    ],
    "middle-east-conflict": [
        "IDF reservist or active military (cf. Feb 2026 charges)",
        "Israeli government official or intelligence-adjacent",
        "Defense contractor with government contracts in the region",
        "Journalist with embedded military sources",
        "Diplomat or foreign service officer"
    ],
    "ai-models": [
        "Employee or contractor at OpenAI, Anthropic, Google DeepMind",
        "Investor with NDA access to pre-release benchmarks",
        "Board member or advisor",
        "Technical journalist with advance review access"
    ],
    "crypto-regulation": [
        "SEC or CFTC employee (illegal but documented elsewhere)",
        "Crypto exchange lobbyist with congressional contacts",
        "Law firm working on regulatory cases",
        "Congressional staffer on financial services committee"
    ],
    "us-fed-rates": [
        "Federal Reserve employee (illegal under 18 USC 1905)",
        "Primary dealer bank analyst with advance Fed communication",
        "Former Fed official with maintained relationships",
        "Treasury Department employee"
    ],
}
```

### 2b. Red Flags for Specific Hypotheses

Some hypotheses carry legal risk. Flag them explicitly:

```python
HIGH_LEGAL_RISK_SUBDOMAINS = [
    "us-fed-rates",         # Federal employee trading on inside info = federal crime
    "crypto-regulation",    # If SEC employee = 18 USC 1905 violation
    "us-scotus",            # SCOTUS leaks = potential obstruction
    "corporate-litigation", # May involve MNPI (material non-public information)
]

# For these, note in output: "If institutional hypothesis is correct, this person
# is committing a federal crime. Prediction markets have no jurisdiction, but
# following their signal means profiting from their illegal activity.
# DOCUMENT but flag as ethically grey."
```

**Note to Claude Code**: Surface this in output. Yu will decide whether to follow these signals. Don't suppress them — just label them clearly.

### 2c. Confidence Classification

Rate each institutional hypothesis:

```
SPECULATIVE: We see the edge pattern; any of several explanations could fit
PLAUSIBLE:   Edge pattern + trade timing + market type all point to this explanation
PROBABLE:    Strong localisation + matches known documented cases (e.g. IDF + GEO)
IDENTIFIED:  Already publicly known (e.g. AlphaRaccoon → Google)
```

---

## Task 3: Cross-Account Cluster Analysis

Some insiders may be part of the **same network** — sharing information or acting on the same source.

### 3a. Temporal Clustering

```python
"""
Detection: Multiple insiders buying the same market within a narrow time window
before a known announcement, even without wallet links.

Method:
1. For each market with upcoming announcement (catalyst-calendar.json)
2. Identify all accounts with >= 1 trade in the 24-72h window before announcement
3. Cross-reference against insider-registry.json
4. If >= 2 registered insiders trade the SAME direction in the SAME window → cluster signal

Interpretation:
  - 2 insiders agreeing independently → strong confirmation
  - 3+ insiders in same direction → very high confidence signal
  - Some agreeing, some opposing → contradiction to investigate
"""
```

### 3b. Common Funding Source Detection

```python
"""
Wallets funded from the same exchange withdrawal or the same intermediary address
may be linked persons (shared information network).

Use Polygonscan: trace USDC deposits back 1-2 hops.
If multiple insider wallets received funds from same source address → likely same person
or information network.

This is NOT required for L03 (too resource-heavy). Flag for potential future work.
"""
```

---

## Task 4: Output — The Intelligence Dossier

For each high-confidence insider (score >= 7.0), produce a one-page intelligence dossier:

```markdown
### DOSSIER: POL-Insider-01

**Wallet**: 0x...  
**Type**: INSIDER (high confidence)  
**Insider Score**: 8.4 / 10  
**Active Period**: Mar 2025 – Feb 2026  

**Dominant Field**: US Republican Primary Politics  
- 34 resolved bets, mean edge +0.28, p=0.0001  
- 71% of total POL edge concentrated in this sub-domain  
- Near-zero edge in all other political sub-domains and other categories  

**Trade Pattern**:  
- Avg trade size: $2,800  
- Typical timing: 8-15 days before resolution  
- Direction: 78% YES bets (skews bullish/confident)  
- Average entry: 0.41 (prefers moderately-priced markets, not near-certainties)  

**Institutional Hypothesis**: PLAUSIBLE — Republican campaign staffer or pollster  
Evidence: sub-domain specificity (primary only, not general), timing pattern (pre-debate weeks), bet sizing consistent with salary-level capital  

**Recommended Follow Confidence**: 4/5  
**Follow only when**: Market is US Republican primary/nomination. Ignore their bets elsewhere.  
**Last known bet**: 2026-02-18, "Vance wins 2028 GOP nomination" NO at $0.42  
**Follow note**: Their last bet opposes our T006 position (Vance YES). Investigate.
```

---

## Output

1. `scripts/field-classifier.py` — takes insider-registry.json, outputs classified-insiders.json
2. `data/classified-insiders.json` — full classification with sub-domain breakdown + institutional hypotheses
3. `data/intelligence-dossiers/` — one markdown file per high-confidence insider
4. Terminal report: top 10 insiders, their primary sub-domain, institutional hypothesis, and confidence
5. Cross-cluster analysis: any cases of 2+ insiders trading the same market same direction in same window?

**Done when**: Each high-confidence insider has a dossier, at least 3 institutional hypotheses have been generated across different categories, and the cross-cluster analysis has run on all markets in catalyst-calendar.json.
