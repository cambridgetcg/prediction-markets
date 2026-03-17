You are an AI systems architect building S012 — the LLM Ensemble Screener. This is the highest-leverage new strategy identified in the system: using multiple LLMs to screen hundreds of markets, identify mispricings, and feed candidates to human review.

## Why This Is the Highest Priority New Strategy

Evidence chain:
- Bridgewater's AIA Forecaster: **ensemble of AI + market consensus outperforms market consensus alone** — proof that AI adds information
- "Wisdom of the Silicon Crowd" (Science Advances 2024): 12-LLM ensemble matches human crowd accuracy
- ForecastBench: GPT-4.5 Brier score 0.101 vs superforecasters 0.081 — gap closing
- ilovecircle bot: **$2.2M profit in 60 days**, 74% accuracy using neural net + news feeds + social sentiment
- Schoenegger/Tetlock: LLM assistants improve human forecasting by 24-41%
- OLAS/Gnosis: 300+ autonomous agents at 79% prediction accuracy

**The multiplier**: We currently screen 5-10 markets manually via S008. S012 screens hundreds. It doesn't replace human judgment — it tells us WHERE to look.

## Read First

1. ~/Desktop/prediction-markets/strategies/evolution/new-strategy-research.md — S012 section (detailed spec)
2. ~/Desktop/prediction-markets/research/what-doesnt-work.md — Section 3.1 (edge decay), 6.1 (profit models)
3. ~/Desktop/prediction-markets/calibration/predictions.jsonl — our existing predictions (calibration baseline)
4. ~/Desktop/prediction-markets/calibration/resolutions.jsonl — resolved predictions (ground truth)
5. ~/Desktop/prediction-markets/strategies/playbooks/S006-time-decay.md — example of strategy S012 would screen for

---

## Task 1: Architecture Design

### 1a. The Pipeline

```
Active markets (Gamma API, 500+)
    │
    ├─ Filter: volume > $50K, resolution within 180 days
    │
    ├─ Enrich: add domain tag, resolution date, current price, price history
    │
    ├─ Screen: Query 3 LLMs with structured prompt
    │   ├─ Claude (Anthropic API)
    │   ├─ GPT-4 (OpenAI API)
    │   └─ Open-source (Llama 3 70B via Together/Groq)
    │
    ├─ Aggregate: Take median of 3 LLM estimates
    │
    ├─ Calibrate: Apply Platt scaling (once we have 100+ calibration samples)
    │
    ├─ Compare: |P_calibrated - P_market| > 5pp → FLAG for human review
    │
    └─ Output: Ranked list of mispriced markets + confidence scores
```

Design this architecture. For each component, specify:
- Input/output format
- API endpoints used
- Cost per query (we need to budget)
- Error handling (API failures, rate limits, timeouts)

### 1b. The Structured Prompt

The prompt given to each LLM is critical. It must be:
- **Consistent** across models (same format → comparable outputs)
- **Structured** to produce a numeric probability (not narrative)
- **Context-enriched** with base rates and relevant facts
- **Calibration-aware** (explicitly ask for calibrated probability)

Design the prompt template:

```
You are a calibrated forecaster. Given the following prediction market question,
estimate the probability of YES resolution.

QUESTION: {question}
RESOLUTION DATE: {resolution_date}
RESOLUTION CRITERIA: {resolution_criteria}
CURRENT MARKET PRICE: {current_price_yes}
DOMAIN: {domain}
DAYS REMAINING: {days_remaining}

BASE RATE CONTEXT:
- {domain_specific_base_rate}
- Historical: {pct} of similar "{by_date}" markets resolved NO

RECENT RELEVANT INFORMATION:
{top_3_news_items}

Respond with ONLY a JSON object:
{
  "probability_yes": 0.XX,
  "confidence": "low|medium|high",
  "key_factors": ["factor1", "factor2", "factor3"],
  "domain": "{domain}"
}
```

Test this prompt on 5 markets we've already researched (where we have independent estimates) to validate output quality.

### 1c. Cost Analysis

Calculate the cost per screening cycle:

| Component | Cost per market | Markets per cycle | Total |
|-----------|----------------|-------------------|-------|
| Claude Haiku | ~$0.001 | 200 | $0.20 |
| GPT-4o-mini | ~$0.001 | 200 | $0.20 |
| Llama 3 70B (Groq) | ~free | 200 | $0.00 |
| Gamma API | free | 200 | $0.00 |

If the cost per daily screening cycle is <$1, this is trivially affordable. Calculate the real numbers.

---

## Task 2: Build the Screener Script

### 2a. Market Fetcher

```python
# ~/Desktop/prediction-markets/scripts/llm-screener.py

"""
S012 LLM Ensemble Screener — screen Polymarket markets for mispricings.

Usage:
    python3 llm-screener.py                    # Full screen (all active markets)
    python3 llm-screener.py --domain GEO       # Screen only GEO domain
    python3 llm-screener.py --market "Iran"    # Screen markets matching keyword
    python3 llm-screener.py --calibrate        # Run calibration analysis on historical predictions

Requirements:
    - ANTHROPIC_API_KEY (for Claude)
    - OPENAI_API_KEY (for GPT-4)
    - OR: run with --model claude-only / --model gpt-only for single-model mode
    - Gamma API (no key needed)
"""
```

Implement the market fetcher:
1. Paginate Gamma API `/events?limit=100&closed=false&order=volume&ascending=false`
2. For each event, extract markets with: question, resolution date, current price, volume, domain tag
3. Filter: volume > $50K, resolution within 180 days, not expired
4. Tag domain (GEO, POL, ECO, CRY, TEC, LAW, etc.) using keyword matching on question text
5. Output: list of market dicts ready for LLM screening

### 2b. LLM Query Module

Implement the LLM query layer:
1. Format the structured prompt for each market
2. Query each model with appropriate API calls
3. Parse JSON response (handle malformed responses gracefully)
4. Take median of estimates
5. Calculate edge: `edge = median_estimate - market_price`

### 2c. Output Format

```
=== S012 SCREENER — 2026-02-26 ===

FLAGGED MARKETS (|edge| > 5pp, sorted by |edge|):

  1. "Will Netanyahu remain PM by June 30?"
     Market: 72% YES | LLM median: 58% YES | Edge: -14pp (OVERPRICED)
     Domain: GEO | Volume: $2.1M | Confidence: medium
     → Recommendation: Research for S008 entry (NO side)

  2. "Will BTC hit $200K by Dec 31?"
     Market: 12% YES | LLM median: 4% YES | Edge: -8pp (OVERPRICED)
     Domain: CRY | Volume: $890K | Confidence: high
     → Recommendation: S006 time decay candidate (NO side)

  3. "Anthropic releases Claude 5 by March 31?"
     Market: 22% YES | LLM median: 35% YES | Edge: +13pp (UNDERPRICED)
     Domain: TEC | Volume: $340K | Confidence: low
     → Recommendation: Research — LLMs may have insider knowledge bias

MARKETS REVIEWED: 187
FLAGGED: 12 (6.4%)
AVERAGE ABSOLUTE EDGE: 2.3pp (across all markets)
```

---

## Task 3: Calibration Logging

### 3a. Log Every LLM Prediction

Every screening run must log predictions for future calibration:

```json
// ~/Desktop/prediction-markets/calibration/llm-predictions.jsonl
{
  "timestamp": "2026-02-26T10:00:00Z",
  "market_id": "...",
  "question": "US strikes Iran by June 30, 2026?",
  "market_price": 0.695,
  "claude_estimate": 0.55,
  "gpt4_estimate": 0.60,
  "llama_estimate": 0.52,
  "median_estimate": 0.55,
  "human_estimate": 0.40,
  "edge": -0.145,
  "resolution": null,
  "resolution_date": null
}
```

### 3b. Calibration Analysis

After we accumulate 50+ resolved predictions:
- Plot reliability diagram (predicted probability vs. observed frequency)
- Calculate Brier scores per model
- Fit Platt scaling parameters: `P_calibrated = 1 / (1 + exp(-(a * P_raw + b)))`
- Identify systematic biases: which domains are LLMs overconfident on? Underconfident?

### 3c. Integration with Existing Calibration

Our `calibration/predictions.jsonl` already has human predictions. The LLM predictions should:
- Use the same market identifiers for easy comparison
- Eventually allow: "Our human estimate was X, Claude said Y, GPT said Z, the market was W — who was closest?"
- This builds the evidence for whether S012 actually adds value

---

## Task 4: Open-Source Frameworks (Build vs Buy)

### 4a. Polymarket/agents

Web search: "github Polymarket agents framework"
- Official Polymarket AI agent framework
- Uses Gamma API + ChromaDB (RAG) + LLM integration
- Can we fork this and customize for our pipeline?
- What does it do that our custom script doesn't?

### 4b. gnosis/prediction-market-agent

Web search: "github gnosis prediction-market-agent"
- 300+ agents, 79% accuracy
- OLAS (Autonolas) integration
- Architecture and deployment requirements?

### 4c. Build vs Buy Decision

Compare: custom script (Task 2) vs forking an existing framework (Task 4a/4b):

| Factor | Custom Script | Fork Polymarket/agents | Fork Gnosis |
|--------|--------------|----------------------|-------------|
| Setup time | Hours | Days | Days |
| Customization | Full | Moderate | Limited |
| Maintenance | Us | Community | Community |
| RAG support | No (add later) | Yes (ChromaDB) | Yes |
| Cost | API calls only | API calls only | May need OLAS tokens |

Recommend the best approach.

---

## Task 5: S012 Strategy Playbook

Write: `~/Desktop/prediction-markets/strategies/playbooks/S012-llm-ensemble.md`

Include:
- Phase: NIGREDO
- The architecture diagram
- Prompt template
- Calibration requirements (50+ resolved before trusting)
- Integration: S012 screens → human reviews flagged markets → enters via S004/S006/S008
- Known LLM weaknesses: overconfident at 90%+, political bias, knowledge cutoff
- Cost budget: $X/day for screening
- Success criteria: does the screener flag markets where our human research later finds edge?

---

## Output

1. `scripts/llm-screener.py` — working screener with Gamma API + at least 1 LLM model
2. `strategies/playbooks/S012-llm-ensemble.md` — strategy playbook
3. `calibration/llm-predictions.jsonl` — seeded with first screening run
4. Terminal output: first screening results on current active markets
5. Build vs buy recommendation with rationale

**Done when**: The screener can pull 100+ active markets from Gamma API, query at least one LLM, and output a ranked list of potentially mispriced markets. Calibration logging is working. The first screening run has been completed and saved.
