# Module 5: Signal Generator

## Task

Build `scripts/s012/signal_generator.py` — converts actionable `ReactionAssessment`s into formatted trading signals, applies portfolio-level risk checks (R01 correlation), and delivers them.

## Context

This module is the last filter before a signal reaches the trader. It applies:
1. Portfolio concentration checks (C1-C4 from `research/position-sizing-rules.md`)
2. Existing position correlation check
3. Anti-pattern verification (from `research/what-doesnt-work.md` Section 7.3)
4. Signal formatting for human review

## Requirements

### Input
- `ReactionAssessment` from Module 4 (only where `is_actionable == True`)
- Current positions from `strategies/paper-trades/positions.json`
- Position sizing rules from `research/position-sizing-rules.md`

### Output
```python
@dataclass
class TradingSignal:
    signal_id: str                  # UUID
    assessment_id: str              # Link to Module 4
    event_id: str
    market_id: str
    market_question: str
    
    # Signal
    signal_type: str                # S012-OVER | S012-UNDER
    direction: str                  # YES | NO
    entry_price: float
    target_price: float
    stop_price: float
    time_horizon_hours: int
    size_usdc: float                # Actual $ amount
    size_pct: float                 # Bankroll percentage
    
    # Context
    reaction_delta: float
    estimated_shift: float
    actual_move: float
    confidence: float
    reasoning: str                  # From LLM interpretation
    
    # Risk checks
    passed_concentration: bool      # C1-C4 checks
    passed_anti_patterns: bool      # Not revenge trading, not outside domain, etc.
    risk_notes: list[str]           # Any warnings
    
    # Status
    status: str                     # PENDING | APPROVED | REJECTED | EXPIRED
    created_at: datetime
    expires_at: datetime            # Auto-expire if not acted on within 2h
```

### Portfolio Risk Checks (C1-C4)

From `research/position-sizing-rules.md`:

```python
def check_concentration(signal: TradingSignal, positions: list) -> tuple[bool, list[str]]:
    """Apply C1-C4 concentration rules. Returns (passed, warnings)."""
    warnings = []
    passed = True
    
    # C1: Max 3% bankroll on any single event/thesis
    same_event = [p for p in positions if overlaps_event(p, signal)]
    total_event_exposure = sum(p.size_pct for p in same_event) + signal.size_pct
    if total_event_exposure > 0.03:
        warnings.append(f"C1 FAIL: {total_event_exposure:.1%} on same event (max 3%)")
        passed = False
    
    # C2: Max 10% bankroll per domain (loosened from 5% for S012)
    same_domain = [p for p in positions if p.domain == signal.domain]
    total_domain = sum(p.size_pct for p in same_domain) + signal.size_pct
    if total_domain > 0.10:
        warnings.append(f"C2 FAIL: {total_domain:.1%} in {signal.domain} (max 10%)")
        passed = False
    
    # C3: Correlation check — don't add to highly correlated existing position
    for p in positions:
        if estimate_correlation(p, signal) > 0.80:
            warnings.append(f"C3 FAIL: ρ>{0.80} with {p.market_question[:40]}")
            passed = False
            break
    
    # C4: Max total S012 exposure 10%
    s012_positions = [p for p in positions if p.strategy.startswith('S012')]
    total_s012 = sum(p.size_pct for p in s012_positions) + signal.size_pct
    if total_s012 > 0.10:
        warnings.append(f"C4 FAIL: {total_s012:.1%} total S012 (max 10%)")
        passed = False
    
    return passed, warnings
```

### Anti-Pattern Check

From lessons and what-doesnt-work research:

```python
def check_anti_patterns(signal: TradingSignal, recent_signals: list) -> tuple[bool, list[str]]:
    """Verify this signal doesn't fall into known failure patterns."""
    warnings = []
    passed = True
    
    # AP1: Not trading outside our domain expertise
    if signal.domain in ('ECO', 'FIN') and signal.signal_type == 'S012-UNDER':
        warnings.append("AP1: Underreaction trades in ECO/FIN are low-edge (too efficient)")
        passed = False
    
    # AP2: Not revenge trading (signal within 4h of a stopped-out S012 trade on same market)
    recent_stops = [s for s in recent_signals 
                    if s.market_id == signal.market_id 
                    and s.status == 'STOPPED'
                    and (signal.created_at - s.created_at).total_seconds() < 14400]
    if recent_stops:
        warnings.append("AP2: Possible revenge trade — same market stopped out <4h ago")
        passed = False
    
    # AP3: Entry price in Zone 4-5 (>$0.70) needs extra justification
    if signal.entry_price > 0.70:
        warnings.append(f"AP3: Entry at {signal.entry_price:.2f} is Zone 4+ — high asymmetric risk")
        # Warning only, don't fail — overreaction fades can be at high prices
    
    # AP4: Market has sufficient liquidity
    # (This should be caught by Module 2, but double-check)
    
    # AP5: Resolution rules read? (Flag for human verification)
    warnings.append("AP5: Verify resolution rules before executing")
    
    return passed, warnings
```

### Signal Formatting (for human review)

When delivering a signal, format it like:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 S012 SIGNAL: OVERREACTION DETECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Market: Will Iran resume nuclear talks by March 15?
Current YES: 72.5% | Pre-news: 55.0% | Move: +17.5pp

News: "Sources say Iran open to resuming Geneva format"
Type: UNCONFIRMED | Domain: GEO

LLM Estimate: +8pp rational shift
Actual Move:  +17.5pp
Delta:        +9.5pp OVERREACTION (STRONG)
Confidence:   0.68

TRADE: Buy NO at 27.5¢
  Target: YES drops to 65.5% (40% retracement)
  Stop:   YES rises to 80.5%
  Size:   $30 (3% of $1,000 bankroll)
  Horizon: 7 days

Risk: ✅ C1-C4 passed | ⚠️ Verify resolution rules
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Storage

```sql
CREATE TABLE IF NOT EXISTS s012_signals (
    signal_id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL,
    target_price REAL,
    stop_price REAL,
    time_horizon_hours INTEGER,
    size_usdc REAL,
    size_pct REAL,
    reaction_delta REAL,
    confidence REAL,
    passed_concentration INTEGER,
    passed_anti_patterns INTEGER,
    risk_notes TEXT,              -- JSON array
    status TEXT DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
```

Also append to `data/s012/signals.jsonl`.

### CLI Interface

```bash
python3 scripts/s012/signal_generator.py --demo              # Demo with synthetic assessment
python3 scripts/s012/signal_generator.py --pending           # Show pending signals
python3 scripts/s012/signal_generator.py --history           # Show all signals with outcomes
python3 scripts/s012/signal_generator.py --approve <id>      # Mark signal as approved
python3 scripts/s012/signal_generator.py --reject <id>       # Mark signal as rejected
```

### Tests

Append to `scripts/s012/test_s012.py`:
- `test_signal_formatting()` — output contains all required fields
- `test_concentration_c1()` — same event cap enforced
- `test_concentration_c4()` — total S012 cap enforced
- `test_anti_pattern_revenge()` — recent stop → blocked
- `test_anti_pattern_eco()` — ECO underreaction → blocked
- `test_signal_expiry()` — signals expire after 2h
- `test_bankroll_sizing()` — correct $ amount from percentage

### Conventions

- Same as previous modules
- Signals are NEVER auto-executed — always PENDING for human review
- Human approves/rejects via CLI or via orchestrator notification
- Expired signals auto-marked as EXPIRED after 2h
