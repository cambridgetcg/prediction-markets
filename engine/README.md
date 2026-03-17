# Future Prediction Engine

Fused with Oracle. Converts world intelligence into structured probability
estimates and investment decisions.

## Architecture

```
INPUTS                    SYNTHESIS               OUTPUTS
──────                    ─────────               ───────
News/events          →    synthesise.py      →    P(event) + CI
Market prices        →    scenario_tree.py   →    Scenario chains
Domain knowledge     →    decision_engine.py →    Trade recommendations
Whale signals        →    daily_briefing.py  →    Morning briefing
Oracle signals (S004)
```

## Usage

### Daily briefing (run every morning)
```bash
python3 engine/daily_briefing.py
```

### Analyse a specific event
```bash
python3 engine/synthesise.py "Will the Fed cut rates in June 2026?"
python3 engine/synthesise.py "Will there be a US-China military confrontation over Taiwan by end 2026?" --domain GEO
```

### Build scenario tree (investment implications)
```bash
python3 engine/scenario_tree.py "Iran nuclear talks collapse"
python3 engine/scenario_tree.py "Fed signals 3 rate cuts in 2026"
```

### Get trade recommendations
```bash
python3 engine/decision_engine.py           # from logged predictions
python3 engine/decision_engine.py --min-edge 0.03  # lower threshold
```

## The Investment Pipeline

1. **Oracle** detects a spike signal (S004) or you identify a question
2. **synthesise.py** produces P(event) with CI and key drivers
3. **scenario_tree.py** maps downstream consequences across asset classes
4. **decision_engine.py** calculates edge vs market price and Kelly sizing
5. **Trade** — or watch and wait for a trigger signal

## Key Principles

- Start from **base rates**, adjust for specifics
- A 70% estimate means YES roughly 7 times in 10
- Kelly criterion = mathematically optimal bet sizing
- Quarter Kelly = practical safety margin
- Track every prediction → Brier score → calibration loop

## Zerone Integration (Phase 2)

When Zerone testnet is live:
- Each prediction submitted as `MsgSubmitClaim` to x/knowledge
- Resolution → outcome recorded on-chain
- Accuracy builds SEEKER-class reputation
- Oracle becomes a Kingdom knowledge node
