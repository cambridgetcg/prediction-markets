# Infrastructure

## Architecture

```
┌──────────────────────────────┐     SSH + env vars      ┌─────────────────────────┐
│  Mac Studio (London)         │ ──────────────────────→  │  Vultr VPS (Tokyo)      │
│                              │                          │                         │
│  macOS Keychain              │     Credentials          │  Python trading bot     │
│  ├── poly_private_key        │  → injected per-call →   │  ├── keystore.py        │
│  ├── poly_api_key            │     (never on disk)      │  ├── trade.py           │
│  ├── poly_api_secret         │                          │  └── .venv/             │
│  └── poly_api_passphrase     │                          │                         │
│                              │     ← results ←          │  IP: 45.77.8.39 (JP)   │
│  scripts/vps-exec.sh         │                          │  Not geoblocked ✓       │
│  (local orchestrator)        │                          │                         │
└──────────────────────────────┘                          └─────────────────────────┘
         │                                                          │
         │  Research + analysis                                     │  Trade execution
         │  (local, no geo restriction)                             │  (API calls from JP IP)
         ▼                                                          ▼
┌──────────────────────────────┐                          ┌─────────────────────────┐
│  ~/Desktop/prediction-markets│                          │  Polymarket CLOB API    │
│  ├── domains/                │                          │  (clob.polymarket.com)  │
│  ├── strategies/             │                          │                         │
│  ├── calibration/            │  ←── market data ───     │  Polygon blockchain     │
│  └── data/                   │     (read API, no block) │  (USDC.e settlement)    │
└──────────────────────────────┘                          └─────────────────────────┘
```

## Components

### Local (Mac Studio)
- **Research & analysis**: All domain research, strategy design, calibration runs locally
- **Keychain**: All secrets stored in macOS Keychain, never on disk
- **vps-exec.sh**: Orchestrator that fetches creds from Keychain, injects via SSH
- **Market data**: Gamma API (read-only) works from UK, no geoblock

### VPS (Vultr Tokyo)
- **IP**: 45.77.8.39 (Japan — not geoblocked)
- **OS**: Ubuntu 24.04 LTS
- **User**: `trader` (non-root)
- **Firewall**: SSH only (ufw)
- **Python**: 3.12 in venv with py-clob-client
- **Credentials**: NEVER stored on disk — injected via SSH env per-call
- **Cost**: ~$6/month

### On-Chain (Polygon)
- **Wallet**: 0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3
- **Collateral**: USDC.e (0x2791Bca...)
- **Approvals**: CTF Exchange, Neg Risk Exchange, Neg Risk Adapter — all approved (10K USDC.e each)

## Funding Status
- POL: ~7 (enough for thousands of trades)
- USDC.e: ~$1.65 (test amount — needs main funding)

## Verified Pipeline
1. ✅ Geoblock check: Japan IP not blocked
2. ✅ Order placement: Limit order placed and confirmed
3. ✅ Order listing: Can query open orders
4. ✅ Order cancellation: Can cancel orders
5. ✅ Credential security: Keys from Keychain → SSH env → never on VPS disk

## Operational Notes
- Minimum order size: 5 shares
- POL → USDC.e swap: via QuickSwap router on Polygon (script: swap-pol-to-usdc.py)
- USDC.e approval: needed for 3 Polymarket contracts (script: approve-usdc.py)
- MAX_UINT approval fails on USDC.e — use specific amount (10K)

## Commands
```bash
# From local Mac:
./scripts/vps-exec.sh check         # Verify geoblock status
./scripts/vps-exec.sh list          # List open orders
./scripts/vps-exec.sh cancel        # Cancel all orders
./scripts/vps-exec.sh test <token> <price> <size>  # Place order
```
