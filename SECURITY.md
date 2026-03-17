# Security Model

## Architecture

```
┌─────────────────────────────────────────┐
│  macOS Keychain (encrypted at rest)     │
│                                         │
│  poly_private_key     ← wallet key      │
│  poly_api_key         ← CLOB auth       │
│  poly_api_secret      ← CLOB auth       │
│  poly_api_passphrase  ← CLOB auth       │
└──────────────┬──────────────────────────┘
               │
               │  Retrieved per-call via
               │  `security find-generic-password`
               │
┌──────────────▼──────────────────────────┐
│  scripts/keystore.py                     │
│                                         │
│  get_trading_client()                    │
│    → fetches creds from Keychain        │
│    → creates ClobClient                 │
│    → clears local key reference         │
│    → returns client                     │
│                                         │
│  get_readonly_client()                   │
│    → no credentials needed              │
│    → for data fetching only             │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Trading scripts                         │
│  (import from keystore, never touch     │
│   raw keys directly)                    │
└─────────────────────────────────────────┘
```

## What's Protected

| Secret | Storage | Exposure |
|--------|---------|----------|
| Private key | Keychain only | Fetched per-call, cleared after client init |
| API key | Keychain only | Fetched per-call |
| API secret | Keychain only | Fetched per-call |
| API passphrase | Keychain only | Fetched per-call |
| Wallet address | .zshrc env var | Public (not a secret) |

## What's NOT in

| Location | Contains secrets? |
|----------|------------------|
| Environment variables | NO — removed from .zshrc |
| Any file in this repo | NO — scanned and verified |
| Git history | NO — keys were never committed |
| Scripts | NO — all use keystore.py |

## Threat Model

| Threat | Mitigation | Residual Risk |
|--------|-----------|---------------|
| Process reads env vars | Keys not in env | ✓ Eliminated |
| File leak (repo shared) | Keys not in files | ✓ Eliminated |
| Malicious script | Must call keystore.py, which calls Keychain | Keychain access prompt if new process |
| Machine compromised | Keychain encrypted at rest, locked on sleep | Root access could extract — but so could anything |
| Claw session leak | Private key not in chat history | Key printed once in setup, now deleted |
| Wallet drained | Dedicated wallet, only trading capital (~$880) | Max loss = bankroll |

## Operational Rules

1. **Never print or log the private key** — setup is done, it's in Keychain
2. **All trading scripts import from keystore.py** — no direct Keychain calls
3. **No secrets in git** — .gitignore covers .env, but we don't use .env
4. **Dedicated wallet** — only holds trading capital, no other assets
5. **Position limits** — max 10% per trade, max 30% per domain (enforced in trade logic)

## Recovery

If the Keychain entry is lost:
- The wallet can be recovered from the private key (which you should have noted during setup)
- API credentials can be re-derived from the private key using `setup-api-creds.py`
- USDC on Polygon is always accessible with the private key via any wallet app

## Monitoring

The `verify-setup.py` script checks:
- Credentials exist in Keychain
- No secrets leaked to environment variables
- CLOB connection works
- On-chain balance (POL + USDC)
