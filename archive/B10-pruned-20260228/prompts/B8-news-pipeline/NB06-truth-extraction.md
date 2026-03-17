# NB06: Truth Extraction Engine
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Context
[Paste NB01 + EventCluster + PerspectiveMatrix here]

## Philosophy
Triangulation, not summarisation. Find what all perspectives agree on (= likely true),
what they disagree on (= contested/uncertain), what each side omits (= motivated silence),
and extract the prediction-market-relevant kernel.

This is the intelligence core of the pipeline.

## Requirements

1. **Truth extraction prompt** (`prompts/truth_extraction_brave.txt`):

   Input format (articles grouped by perspective cluster):
   ```
   EVENT: {event_summary}
   DIVERGENCE: {divergence_score:.1f}

   === WESTERN ({n} articles, tone: {mean_tone:+.1f}) ===
   [1] {source} | {tone:+.1f} | {key_claim}
       {description} {snippets}

   === RUSSIAN ({n} articles, tone: {mean_tone:+.1f}) ===
   ...

   === IRANIAN ({n} articles, tone: {mean_tone:+.1f}) ===
   ...
   ```

   Output JSON:
   ```json
   {
     "consensus_facts": ["..."],
     "contested_claims": [
       {
         "claim": "...",
         "western_view": "...",
         "russian_view": "...",
         "resolution": "uncertain|likely_true|likely_false"
       }
     ],
     "motivated_omissions": {
       "Western": "...",
       "Russian": "..."
     },
     "objective_kernel": "2-3 sentence synthesis of most likely truth",
     "market_relevance": [
       {
         "category": "geopolitical|political|economic|legal",
         "description": "Which markets are affected",
         "direction": "YES|NO",
         "probability_shift": 0.05,
         "confidence": 0.7,
         "key_uncertainty": "Whether next round of talks produces deal"
       }
     ],
     "overall_confidence": 0.75
   }
   ```

2. **TruthExtractor class**:
   - `extract(cluster: EventCluster) -> TruthExtractionResult`
   - Format cluster → prompt template
   - Call Anthropic API
   - Parse JSON response
   - Model selection:
     - `divergence_score > 6.0` → claude-opus (high stakes, complex disagreement)
     - `divergence_score 3.0-6.0` → claude-sonnet (standard)
   - Retry × 2 on JSON parse failure
   - Set `requires_human_review=True` if confidence < 0.6 or retry exhausted

3. **TruthExtractionResult dataclass**:
   ```python
   @dataclass
   class TruthExtractionResult:
       cluster_id: str
       consensus_facts: list[str]
       contested_claims: list[dict]
       motivated_omissions: dict[str, str]
       objective_kernel: str
       market_relevance: list[dict]
       overall_confidence: float
       requires_human_review: bool
       model_used: str
       extracted_at: datetime
   ```

4. **Extraction triggers**:
   - Only `is_divergent=True` clusters
   - Skip if extracted in last 60 min (unless new articles added since)
   - Max 20 extractions/hour (cost + rate limit control)

5. **Calibration logging**:
   - Log every extraction with cluster snapshot
   - Later: label whether signal led to profitable trade

## Output
`truth_extractor.py` + `prompts/truth_extraction_brave.txt` (the full prompt) + tests with mocked LLM.
