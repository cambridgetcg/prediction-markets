# B9: Insider Detection & Convergence Signals

Turns on-chain intelligence into live trading signals.

| Prompt | Name | What it builds | Dependencies |
|--------|------|---------------|-------------|
| **B9-01** | Real-Time Whale Follow | `whale-activity-scanner.py` — polls known insider wallets, scores trades, alerts when they move in-domain | Polygonscan API key |
| **B9-02** | Fresh Wallet Detector | `fresh-wallet-detector.py` — watches markets for new wallets making large bets (the insider creation pattern) | Polygonscan API key |
| **B9-03** | Convergence Signal | `convergence_engine.py` — combines news pipeline + whale + fresh wallet into unified high-conviction signals | B8, B9-01, B9-02 |

## Run Order

```
B9-01 + B9-02 → can run in parallel (independent)
      ↓
    B9-03 → needs both above + B8 (news pipeline)
```

## Pre-Requisite

Get a free Polygonscan API key: https://polygonscan.com/apis

```bash
echo 'export POLYGONSCAN_API_KEY="your-key"' >> ~/.zshrc
```
