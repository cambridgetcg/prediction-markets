# Module 6: Paper Trade Logger

## Task

Build `scripts/s012/paper_logger.py` — tracks paper trades from S012 signals and measures calibration of the LLM interpreter.

## Context

Before S012 goes live, we need 30+ paper trades to validate:
1. LLM calibration (are estimated shifts accurate?)
2. Overreaction classification accuracy (do fades actually revert?)
3. Underreaction classification accuracy (does the market catch up?)
4. Overall P&L (is this actually profitable after sizing?)

This module is simple but critical — it's how we know if S012 works.

## Requirements

### Input
- Approved `TradingSignal` from Module 5

### Output
```python
@dataclass
class PaperTrade:
    trade_id: str                   # PT-S012-001, PT-S012-002, etc.
    signal_id: str
    market_id: str
    market_question: str
    
    # Entry
    direction: str                  # YES | NO
    entry_price: float
    entry_time: datetime
    size_usdc: float
    shares: float                   # size_usdc / entry_price
    
    # Targets
    target_price: float
    stop_price: float
    expiry_time: datetime           # entry_time + time_horizon
    
    # Exit (filled when closed)
    exit_price: float | None
    exit_time: datetime | None
    exit_reason: str | None         # TARGET_HIT | STOP_HIT | TIME_EXPIRED | MANUAL
    
    # P&L
    pnl_usdc: float | None         # (exit_price - entry_price) * shares (for YES), adjusted for NO
    pnl_pct: float | None          # pnl_usdc / size_usdc
    
    # Classification
    signal_type: str                # S012-OVER | S012-UNDER
    domain: str
    reaction_delta: float
    estimated_shift: float
    actual_move: float
    
    # Calibration (filled at resolution)
    market_resolved: bool | None    # Did the market resolve YES or NO?
    llm_direction_correct: bool | None  # Was the LLM's shift direction right?
    reaction_call_correct: bool | None  # Was over/under classification right?
    
    status: str                     # OPEN | CLOSED | EXPIRED
```

### Behavior

1. **Open trade**: When a signal is approved, create PaperTrade with entry details
2. **Monitor**: Periodically check current prices against targets/stops
   - Fetch current YES price from Gamma API
   - If target hit → close with TARGET_HIT
   - If stop hit → close with STOP_HIT
   - If time expired → close with TIME_EXPIRED at current price
3. **Close trade**: Record exit details and calculate P&L
4. **Calibration**: When market resolves, record resolution and LLM accuracy

### P&L Calculation

```python
def calculate_pnl(direction: str, entry_price: float, exit_price: float, 
                  shares: float) -> float:
    """Calculate P&L for a paper trade."""
    if direction == 'YES':
        # Bought YES shares at entry_price, sold/resolved at exit_price
        return (exit_price - entry_price) * shares
    else:
        # Bought NO shares at (1 - yes_entry), NO price moved to (1 - yes_exit)
        no_entry = 1.0 - entry_price   # This is what we paid
        no_exit = 1.0 - exit_price     # This is current NO value
        # Wait — for paper tracking, track the YES price and compute NO P&L:
        # We entered NO at (1 - entry_yes_price)
        # Current NO value is (1 - current_yes_price)
        # P&L = (current_no - entry_no) * shares
        return ((1.0 - exit_price) - (1.0 - entry_price)) * shares
        # Simplifies to: (entry_price - exit_price) * shares
```

### Calibration Tracking

After 10+ trades, compute and display:

```python
@dataclass
class CalibrationReport:
    total_trades: int
    open_trades: int
    closed_trades: int
    
    # P&L
    total_pnl_usdc: float
    avg_pnl_per_trade: float
    win_rate: float                # % of closed trades with positive P&L
    
    # By type
    overreaction_count: int
    overreaction_win_rate: float
    underreaction_count: int
    underreaction_win_rate: float
    
    # LLM calibration
    llm_direction_accuracy: float  # % of times LLM got shift direction right
    avg_estimated_shift: float
    avg_actual_shift: float        # Measured at resolution
    
    # Classification accuracy
    reaction_call_accuracy: float  # % of over/under calls that were correct
    
    # By domain
    domain_breakdown: dict[str, dict]  # domain → {count, win_rate, avg_pnl}
```

### Storage

```sql
CREATE TABLE IF NOT EXISTS s012_paper_trades (
    trade_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    market_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    entry_time TEXT NOT NULL,
    size_usdc REAL NOT NULL,
    shares REAL NOT NULL,
    target_price REAL,
    stop_price REAL,
    expiry_time TEXT,
    exit_price REAL,
    exit_time TEXT,
    exit_reason TEXT,
    pnl_usdc REAL,
    pnl_pct REAL,
    signal_type TEXT,
    domain TEXT,
    reaction_delta REAL,
    estimated_shift REAL,
    actual_move REAL,
    market_resolved INTEGER,
    llm_direction_correct INTEGER,
    reaction_call_correct INTEGER,
    status TEXT DEFAULT 'OPEN'
);
```

Also JSONL at `data/s012/paper-trades.jsonl`.

### CLI Interface

```bash
python3 scripts/s012/paper_logger.py --open <signal_id>      # Open paper trade from signal
python3 scripts/s012/paper_logger.py --check                  # Check all open trades vs targets
python3 scripts/s012/paper_logger.py --close <trade_id> --reason manual  # Manual close
python3 scripts/s012/paper_logger.py --status                 # Show all trades
python3 scripts/s012/paper_logger.py --calibration            # Show calibration report
python3 scripts/s012/paper_logger.py --pnl                    # Show P&L summary
```

### Tests

Append to `scripts/s012/test_s012.py`:
- `test_pnl_yes_win()` — YES trade with price increase → positive P&L
- `test_pnl_yes_loss()` — YES trade with price decrease → negative P&L
- `test_pnl_no_win()` — NO trade with price decrease → positive P&L
- `test_target_hit()` — price crosses target → auto-close
- `test_stop_hit()` — price crosses stop → auto-close
- `test_time_expiry()` — past expiry → close at current price
- `test_calibration_report()` — report calculates correctly from trade data
- `test_trade_id_sequence()` — IDs increment: PT-S012-001, PT-S012-002, etc.

### Conventions

- Same as previous modules
- Trade IDs are sequential: PT-S012-001, PT-S012-002, etc.
- Auto-increment by checking max existing ID in DB
- All monetary values in USDC (not GBP)
- Paper bankroll: use value from `bankroll/state.json` (or $10,000 default for paper)
