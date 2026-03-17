# Module 3: Reaction Interpreter

## Task

Build `scripts/s012/reaction_interpreter.py` — the core LLM module that estimates the rational probability shift a news event should cause on relevant prediction markets.

## Context

This is the intellectual heart of S012. When news breaks, the market reacts. But did it react the *right amount*? This module uses an LLM to estimate what the rational probability shift should be, independent of what the market actually did.

The key insight from our research:
- Markets overreact to dramatic/emotional news (S004 backtest: 58% negative autocorrelation)
- Markets underreact to complex/multi-step implications
- Markets underreact to off-hours news (thin liquidity, slow repricing)
- The LLM doesn't need to be perfectly calibrated — it needs to detect *direction and magnitude* of mispricing

## Requirements

### Input
- `MarketMatch` from Module 2 (event + matched market + current prices)
- Source credibility data from `research/source-credibility-matrix.json`
- Domain context from `domains/{domain}/context.md`

### Output
```python
@dataclass
class Interpretation:
    interpretation_id: str         # UUID
    event_id: str                  # From NewsEvent
    market_id: str                 # From MarketMatch
    market_question: str
    
    # LLM estimates
    prior_probability: float       # What the market SHOULD have been before news
    posterior_probability: float   # What the market SHOULD be after news
    estimated_shift: float         # posterior - prior (the rational adjustment)
    
    # Metadata
    confidence: float              # 0.0-1.0, LLM's self-assessed confidence
    reasoning: str                 # 2-3 sentence explanation
    news_type: str                 # NOVEL | CONFIRMATORY | CONTRADICTORY | AMBIGUOUS
    source_quality: str            # VERIFIED | CREDIBLE | UNCONFIRMED | RUMOR
    
    # Calibration
    interpreted_at: datetime
    model_used: str
    prompt_version: str            # Track prompt iterations for calibration
    
    # Raw
    raw_llm_response: str          # Full response for debugging
```

### The Prompt

This is the most critical piece. The prompt must:
1. Provide the news event summary and source details
2. Provide the market question and current price
3. Ask for prior and posterior probability estimates
4. Force structured reasoning (not just a number)
5. Include calibration anchors (base rates, historical patterns)

```python
INTERPRETATION_PROMPT = """You are an expert prediction market analyst. Your job is to estimate 
how a news event should rationally affect a prediction market's probability.

## The News Event

{event_summary}

Sources ({source_count} independent):
{source_list}

First reported: {first_seen}
Domain: {domain}

## The Market

Question: {market_question}
Current YES price: {current_yes_price} (= {current_yes_pct}% implied probability)
Resolution date: {end_date}
Total volume: ${volume_total:,.0f}
24h volume: ${volume_24h:,.0f}

## Domain Context

{domain_context}

## Your Task

Estimate the RATIONAL probability shift this news should cause on this market.

Think step by step:
1. What was the PRIOR probability (before this news)? Use the market's recent price 
   history if available, or reason from base rates.
2. How NOVEL is this information? (Completely new vs. confirming what was expected)
3. How RELIABLE are the sources? (Official statement vs. "sources say")
4. What is the POSTERIOR probability (after incorporating this news)?
5. How CONFIDENT are you in this estimate?

## Response Format (JSON only)

```json
{{
    "prior_probability": 0.XX,
    "posterior_probability": 0.XX,
    "estimated_shift": 0.XX,
    "confidence": 0.XX,
    "news_type": "NOVEL|CONFIRMATORY|CONTRADICTORY|AMBIGUOUS",
    "source_quality": "VERIFIED|CREDIBLE|UNCONFIRMED|RUMOR",
    "reasoning": "2-3 sentences explaining your estimate."
}}
```

IMPORTANT CALIBRATION NOTES:
- Most news events should shift probabilities by 1-10pp. Shifts >15pp require extraordinary evidence.
- "Sources say" without named officials: discount by 50%.
- Rhetoric without action (threats, ultimatums): 2-5pp max shift.
- Confirmed events (vote passed, strike occurred, data released): can justify 10-30pp shift.
- If the news is CONFIRMATORY (market already expected this), the shift should be near zero.
- Your goal is accuracy, not drama. Boring estimates that are correct beat exciting ones that aren't.
"""
```

### Behavior

1. **Receive** a `MarketMatch` (news event + relevant market + prices)
2. **Enrich** with domain context:
   - Load `domains/{domain}/context.md` for domain background
   - Load source credibility from `research/source-credibility-matrix.json`
   - Include price_before if available (for prior estimate anchoring)
3. **Call LLM** with the interpretation prompt
   - Model: `claude-haiku-4-5-20251001` (fast, cheap — we're calling this frequently)
   - Temperature: 0.0 (we want consistency, not creativity)
   - Max tokens: 500 (structured JSON response, should be compact)
4. **Parse** the JSON response
   - Validate all fields present and in expected ranges
   - prior_probability and posterior_probability must be 0.0-1.0
   - confidence must be 0.0-1.0
   - estimated_shift = posterior - prior (validate matches)
5. **Log** to `data/s012/interpretations.jsonl`
6. **Return** the `Interpretation` dataclass

### LLM Call

Use the Anthropic SDK directly:
```python
import anthropic

client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=500,
    temperature=0.0,
    messages=[{"role": "user", "content": prompt}]
)
```

If `anthropic` is not installed, fall back to `subprocess` calling the API via curl (see archived `truth_extractor.py` for the pattern).

### Source Credibility Integration

Load `research/source-credibility-matrix.json` and format for the prompt:
```
Sources (3 independent):
- Reuters (reliability: 0.92, lean: neutral) — "Iran agrees to resume talks..."
- Press TV (reliability: 0.45, lean: pro-Iran) — "Historic breakthrough in..."  
- BBC (reliability: 0.88, lean: center) — "Cautious optimism as Iran..."
```

If a source domain isn't in the credibility matrix, mark it as "(unrated)".

### Rate Limiting

- Max 20 interpretations per hour (from config `pipeline.max_extractions_per_hour`)
- Cooldown: don't re-interpret the same event+market pair within 60 minutes
- Track in SQLite:
  ```sql
  CREATE TABLE IF NOT EXISTS s012_interpretations (
      interpretation_id TEXT PRIMARY KEY,
      event_id TEXT NOT NULL,
      market_id TEXT NOT NULL,
      prior_probability REAL,
      posterior_probability REAL,
      estimated_shift REAL,
      confidence REAL,
      news_type TEXT,
      source_quality TEXT,
      reasoning TEXT,
      model_used TEXT,
      prompt_version TEXT,
      interpreted_at TEXT NOT NULL,
      raw_response TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_interp_event ON s012_interpretations(event_id);
  CREATE INDEX IF NOT EXISTS idx_interp_market ON s012_interpretations(market_id);
  CREATE INDEX IF NOT EXISTS idx_interp_time ON s012_interpretations(interpreted_at);
  ```

### CLI Interface

```bash
python3 scripts/s012/reaction_interpreter.py --demo          # Run on synthetic event
python3 scripts/s012/reaction_interpreter.py --event <id>    # Interpret specific event
python3 scripts/s012/reaction_interpreter.py --recent        # Show recent interpretations
python3 scripts/s012/reaction_interpreter.py --calibration   # Show LLM calibration stats
```

### Tests

Append to `scripts/s012/test_s012.py`:
- `test_prompt_formatting()` — prompt contains all required fields
- `test_response_parsing()` — valid JSON → correct Interpretation
- `test_response_validation()` — out-of-range values caught
- `test_rate_limiting()` — same event+market within cooldown → skip
- `test_source_credibility_loading()` — credibility matrix loads and formats correctly
- `test_demo_mode()` — demo runs without API calls

### Conventions

- Same as Modules 1-2
- Prompt version tracking: start with `v1.0`, increment on any prompt change
- All interpretations logged to both JSONL and SQLite
- Demo mode must NOT call the real API — use hardcoded synthetic responses
