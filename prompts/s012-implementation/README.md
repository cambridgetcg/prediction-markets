# S012 Implementation Prompts

Implementation batch for the News Reaction Calibrator strategy.

## Build Order (sequential — each depends on the previous)

| # | Module | Prompt File | Depends On | Est. Complexity |
|---|--------|-------------|------------|-----------------|
| 1 | News Ingestor (revived) | `01-news-ingestor.md` | Archived `brave_ingestor.py` | [S] Standard |
| 2 | Market Snapshot Cache | `02-market-snapshot.md` | Gamma API | [S] Standard |
| 3 | Reaction Interpreter | `03-reaction-interpreter.md` | Module 1 + 2 | [C] Complex |
| 4 | Reaction Comparator | `04-reaction-comparator.md` | Module 2 + 3 | [S] Standard |
| 5 | Signal Generator | `05-signal-generator.md` | Module 4 | [S] Standard |
| 6 | Paper Trade Logger | `06-paper-trade-logger.md` | Module 5 | [T] Trivial |
| 7 | Orchestrator | `07-orchestrator.md` | All modules | [C] Complex |

## Architecture

```
scripts/
  s012/
    __init__.py
    news_ingestor.py      # Module 1 — revived + simplified from B10
    market_snapshot.py     # Module 2 — Polymarket price snapshots
    reaction_interpreter.py  # Module 3 — LLM probability estimation
    reaction_comparator.py   # Module 4 — expected vs actual delta
    signal_generator.py      # Module 5 — trade signal production
    paper_logger.py          # Module 6 — paper trade tracking
    orchestrator.py          # Module 7 — main loop
    config.py                # Shared config
    test_s012.py             # Tests for all modules

data/
  s012/
    interpretations.jsonl    # LLM interpretation log
    snapshots.jsonl          # Market price snapshots at news time
    signals.jsonl            # Generated signals
    paper-trades.jsonl       # Paper trade log
    calibration.jsonl        # LLM calibration tracking
```

## Shared Context for All Prompts

Every coding agent session should receive:
- This README
- The playbook: `strategies/playbooks/S012-news-reaction-calibrator.md`
- The config: `config/news-pipeline.yaml`
- The trading philosophy: `TRADING-PHILOSOPHY.md` (position sizing, edge thresholds)
- The lessons: `calibration/lessons.md` (what went wrong before)
- Python conventions: Python 3.12+, type hints, dataclasses, no heavy frameworks
- DB: SQLite at `data/news-pipeline.db` (schema already exists from B10 pipeline)
- API: Gamma API for market data, Brave Search for news, Anthropic for LLM
- All scripts must work standalone (`--demo` mode) AND as importable modules
