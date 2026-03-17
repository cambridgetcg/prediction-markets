# NB03: Tone & Entity Extraction
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Context
[Paste NB01 architecture + NB02 Article dataclass here]

## The Gap
Brave gives: title, description, source, age, snippets.
Brave does NOT give: tone score, named entities, themes.
GDELT gave these free. With Brave, we compute them.

## Three approaches — choose and justify:

**Option A: Lightweight NLP (fast, free, offline)**
- Tone: VADER sentiment on `full_text` — fast, free, moderate accuracy
- Entities: spaCy NER (`en_core_web_sm`) — fast, free, good for person/org/location
- Limitation: VADER struggles with geopolitical nuance

**Option B: LLM batch extraction (accurate, ~$0.001/article)**
- Batch 10 articles per Claude call
- Extract: tone (-5 to +5), persons, orgs, locations, key_claim (1 sentence)
- More accurate for geopolitical text

**Option C: Hybrid (recommended)**
- VADER for tone (free, immediate)
- spaCy for entities (free, immediate)
- LLM re-extraction only for clusters flagged as high-divergence candidates
- Best cost/accuracy balance

## Your Task

1. **Choose and implement** per NB01 decision.

2. **ToneEntityExtractor class**:
   - `enrich(articles: list[Article]) -> list[Article]`
   - Adds `tone`, `entities` (and `key_claim` if LLM) in-place
   - Batch LLM processing: 10 articles/call
   - Fallback: if LLM fails, use VADER

3. **LLM batch extraction prompt** (if applicable):
   ```
   For each article, extract as JSON:
   - tone: float -5.0 (very negative) to +5.0 (very positive)
   - persons: [named people]
   - organizations: [orgs, countries, institutions]
   - locations: [places]
   - key_claim: single sentence — the main factual assertion

   Return JSON array, one object per article in order.
   Articles:
   [1] Title: ... Description: ... Snippets: ...
   [2] ...
   ```

4. **Tests**:
   - Known-positive article → tone > 0
   - Known-negative article → tone < 0
   - Geopolitical article → correct entity extraction
   - Batch LLM parsing with mocked response

## Output
`tone_entity_extractor.py` + batch extraction prompt template + tests.
