# Module 4: Reaction Comparator

## Task

Build `scripts/s012/reaction_comparator.py` — compares the LLM's estimated rational shift against the market's actual reaction to classify over/underreaction.

## Context

This is the decision module. It takes:
- What the LLM thinks the shift SHOULD be (from Module 3)
- What the market ACTUALLY did (from Module 2's snapshots)
- And produces a classification: OVERREACTION, UNDERREACTION, or CORRECT

## Requirements

### Input
- `Interpretation` from Module 3 (estimated_shift, confidence)
- `MarketMatch` from Module 2 (actual_move, price_before, price_after)

### Output
```python
@dataclass
class ReactionAssessment:
    assessment_id: str              # UUID
    interpretation_id: str          # Link to Module 3
    event_id: str
    market_id: str
    market_question: str
    
    # The comparison
    estimated_shift: float          # LLM's estimate (from Module 3)
    actual_move: float              # Market's actual move (from Module 2)
    reaction_delta: float           # actual_move - estimated_shift
    
    # Classification
    reaction_type: str              # OVERREACTION | UNDERREACTION | CORRECT
    delta_magnitude: str            # STRONG (≥8pp) | MODERATE (5-8pp) | WEAK (<5pp)
    
    # Confidence adjustments
    raw_confidence: float           # From LLM interpretation
    adjusted_confidence: float      # After domain/source adjustments
    
    # Trade parameters (if actionable)
    is_actionable: bool             # True if delta ≥ 5pp AND confidence ≥ 0.5
    suggested_direction: str | None # YES | NO | None
    suggested_entry: float | None   # Entry price
    suggested_target: float | None  # Target price
    suggested_stop: float | None    # Stop-loss price
    time_horizon_hours: int | None  # Hours to hold
    size_pct: float | None          # Bankroll percentage
    
    # Prices
    current_yes_price: float
    price_before_news: float | None
    
    assessed_at: datetime
```

### Classification Logic

```python
def classify_reaction(estimated_shift: float, actual_move: float, 
                      confidence: float, domain: str) -> tuple[str, str, bool]:
    """
    Returns (reaction_type, magnitude, is_actionable).
    
    The delta is: actual_move - estimated_shift
    - Positive delta = market moved MORE than expected = OVERREACTION
    - Negative delta = market moved LESS than expected = UNDERREACTION
    - Small delta = market moved about right = CORRECT
    """
    delta = actual_move - estimated_shift
    abs_delta = abs(delta)
    
    # Domain-specific thresholds
    if domain == 'GEO':
        action_threshold = 0.08   # 8pp for GEO (higher bar — L07)
    else:
        action_threshold = 0.05   # 5pp for all other domains
    
    # Classification
    if abs_delta < action_threshold:
        return 'CORRECT', 'WEAK', False
    
    if delta > 0:
        reaction_type = 'OVERREACTION'
    else:
        reaction_type = 'UNDERREACTION'
    
    magnitude = 'STRONG' if abs_delta >= 0.08 else 'MODERATE'
    
    # Actionable if: delta exceeds threshold AND confidence sufficient
    is_actionable = abs_delta >= action_threshold and confidence >= 0.5
    
    return reaction_type, magnitude, is_actionable
```

### Trade Parameter Generation

For **OVERREACTION** signals (market moved too far → fade):
```python
# S004 logic: fade the move, target 40% retracement
if reaction_type == 'OVERREACTION':
    if actual_move > 0:  # Price spiked UP → buy NO
        direction = 'NO'
        entry = 1.0 - current_yes_price
        target_yes = current_yes_price - abs(actual_move) * 0.40
        target = 1.0 - target_yes
        stop_yes = current_yes_price + 0.08
        stop = 1.0 - stop_yes
    else:  # Price dropped → buy YES
        direction = 'YES'
        entry = current_yes_price
        target = current_yes_price + abs(actual_move) * 0.40
        stop = current_yes_price - 0.08
    
    time_horizon = 168  # 7 days (S004 standard)
```

For **UNDERREACTION** signals (market didn't move enough → ride):
```python
if reaction_type == 'UNDERREACTION':
    # Ride in the direction the market SHOULD have moved
    if estimated_shift > 0:  # Should have gone UP more → buy YES
        direction = 'YES'
        entry = current_yes_price
        target = posterior_probability  # LLM's estimate of where it should be
        stop = price_before_news  # If reverts to pre-news, thesis is wrong
    else:  # Should have gone DOWN more → buy NO
        direction = 'NO'
        entry = 1.0 - current_yes_price
        target = 1.0 - posterior_probability
        stop = 1.0 - price_before_news
    
    time_horizon = 48  # 48 hours (shorter — if market hasn't caught up by then, we're wrong)
```

### Position Sizing

From the S012 playbook:
```python
def calculate_size(reaction_type: str, magnitude: str) -> float:
    """Returns bankroll percentage for position sizing."""
    if reaction_type == 'OVERREACTION':
        return 0.03 if magnitude == 'STRONG' else 0.015
    elif reaction_type == 'UNDERREACTION':
        return 0.02 if magnitude == 'STRONG' else 0.01
    return 0.0
```

### Confidence Adjustments

Adjust the LLM's raw confidence based on:
```python
def adjust_confidence(raw_confidence: float, source_quality: str, 
                      news_type: str, domain: str) -> float:
    adj = raw_confidence
    
    # Source quality discount
    if source_quality == 'RUMOR':
        adj *= 0.5
    elif source_quality == 'UNCONFIRMED':
        adj *= 0.7
    elif source_quality == 'CREDIBLE':
        adj *= 0.9
    # VERIFIED: no discount
    
    # Novelty bonus
    if news_type == 'NOVEL':
        adj *= 1.1  # Novel info is more likely to be underpriced
    elif news_type == 'CONFIRMATORY':
        adj *= 0.8  # Confirmatory → market probably already priced this
    
    # Domain efficiency discount
    if domain in ('ECO', 'FIN'):
        adj *= 0.5  # Efficient domains → our edge is weaker
    
    return min(adj, 1.0)
```

### Storage

SQLite table in `data/news-pipeline.db`:
```sql
CREATE TABLE IF NOT EXISTS s012_assessments (
    assessment_id TEXT PRIMARY KEY,
    interpretation_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    estimated_shift REAL,
    actual_move REAL,
    reaction_delta REAL,
    reaction_type TEXT,
    delta_magnitude TEXT,
    is_actionable INTEGER,
    suggested_direction TEXT,
    suggested_entry REAL,
    suggested_target REAL,
    suggested_stop REAL,
    time_horizon_hours INTEGER,
    size_pct REAL,
    adjusted_confidence REAL,
    assessed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assess_event ON s012_assessments(event_id);
CREATE INDEX IF NOT EXISTS idx_assess_actionable ON s012_assessments(is_actionable);
```

Also append to `data/s012/assessments.jsonl` for easy review.

### CLI Interface

```bash
python3 scripts/s012/reaction_comparator.py --demo          # Demo with synthetic data
python3 scripts/s012/reaction_comparator.py --recent         # Show recent assessments
python3 scripts/s012/reaction_comparator.py --actionable     # Show only actionable signals
python3 scripts/s012/reaction_comparator.py --stats          # Classification distribution stats
```

### Tests

Append to `scripts/s012/test_s012.py`:
- `test_overreaction_classification()` — actual > expected + 5pp → OVERREACTION
- `test_underreaction_classification()` — expected > actual + 5pp → UNDERREACTION
- `test_correct_classification()` — |delta| < 5pp → CORRECT
- `test_geo_threshold()` — GEO requires 8pp, not 5pp
- `test_trade_params_overreaction()` — fade direction, 40% retracement target, 8pp stop
- `test_trade_params_underreaction()` — ride direction, posterior target, pre-news stop
- `test_confidence_adjustment()` — RUMOR discounts, ECO discounts, NOVEL bonus
- `test_position_sizing()` — correct bankroll percentages by type/magnitude

### Conventions

- Same as previous modules
- Pure logic — no API calls, no LLM calls (those happen in Module 3)
- All classification thresholds as module-level constants (easy to tune)
