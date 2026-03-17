# NB07: Signal Generator & Polymarket Integration
# Batch NB: News Intelligence Pipeline — Brave API Edition
# Created: 2026-02-27

## Context
[Paste NB01 + TruthExtractionResult + S-series strategies + B03/B05 formulas here]
Calibration: Brier 0.230 | YES 2/5 ✗ — apply systematic YES discount.

## Requirements

1. **Polymarket market search**:
   ```python
   GET https://clob.polymarket.com/markets?active=true&limit=100
   # Keyword-match question text against market_relevance description
   ```
   Return top 3 candidate markets with current prices.

2. **Signal scoring**:
   ```python
   base = market_relevance.probability_shift + current_price
   bias_adjusted = apply_B05(base, reliability_weighted_tone)
   strategy_adjusted = apply_strategy_edge(bias_adjusted, strategy_code)
   
   # YES asymmetry correction (known calibration gap: NO 7/7, YES 2/5)
   if direction == "YES":
       final = strategy_adjusted * YES_DISCOUNT  # config: 0.85 default
   else:
       final = strategy_adjusted
   
   edge = final - current_price
   kelly = (edge / (1 - current_price)) * FRACTIONAL_KELLY  # 0.25 fractional Kelly
   kelly_usdc = kelly * bankroll
   ```

3. **GeneratedSignal dataclass**:
   ```python
   @dataclass
   class GeneratedSignal:
       signal_id: str
       cluster_id: str
       market_id: str
       market_question: str
       direction: str                 # YES | NO
       current_price: float           # current market probability
       suggested_probability: float   # our estimate
       edge: float                    # suggested - current
       kelly_fraction: float
       kelly_usdc: float              # dollar amount
       strategy_code: str
       confidence: float
       yes_discount_applied: bool     # track calibration correction
       generated_at: datetime
       status: str                    # pending | approved | rejected | executed
   ```

4. **Strategy routing**:
   - `category=geopolitical` → S04 + R01 correlation check
   - `category=political` → S01/S07
   - `category=economic` → S06
   - Resolution < 7 days → also apply R04 (fast resolution pipeline)

5. **Guardrails**:
   - Reject if `edge < 0.05`
   - Reject if R01 correlation check fails (cluster over C1/C2 cap)
   - Flag for human review if `confidence < 0.6`
   - Max 3 pending signals awaiting approval at once

## Output
`signal_generator.py` + Polymarket market matching utility + tests.
