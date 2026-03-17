# Account Setup Guide

## Overview

£1,000 bankroll split across platforms. Crypto-native is primary (Polymarket). GBP via regulated alternative (Kalshi).

## Platform Priority

| Platform | Funding | Why | Allocation |
|----------|---------|-----|-----------|
| **Polymarket** | USDC on Polygon | Deepest liquidity, best API, most markets | £700 (~$880) |
| **Kalshi** | USD (card/bank) | US-regulated, different markets, GBP-friendly | £200 (~$250) |
| **Manifold** | Play money (mana) | Zero cost, broadest topics, calibration practice | £0 |
| **Metaculus** | No trading | Forecasting only, science/tech focus | £0 |

---

## 1. Polymarket Setup (Primary)

### Georestriction Check
Polymarket officially restricts US users but NOT UK users. UK is fine for the CLOB API.
The UI may geoblock some regions — but the API is permissionless (it's on-chain).

### What You Need

**A. Polygon wallet (new, dedicated)**
```bash
# Generate a fresh wallet for trading only. DO NOT use your main wallet.
# Option 1: Use ethers.js
node -e "const { Wallet } = require('ethers'); const w = Wallet.createRandom(); console.log('Address:', w.address); console.log('Private key:', w.privateKey); console.log('Mnemonic:', w.mnemonic.phrase)"

# Option 2: Use any wallet (MetaMask, Rabby, etc.) and export the private key
```

**B. Fund with USDC on Polygon**
1. Buy USDC on any exchange (Coinbase, Kraken, Binance)
2. Withdraw USDC to your Polygon wallet address
3. Or: bridge from Ethereum → Polygon via https://portal.polygon.technology
4. Need a tiny amount of POL (Polygon's gas token) for transactions (~0.1 POL, pennies)
5. **Amount**: ~$880 USDC (≈ £700)

**C. Approve USDC spending**
The Polymarket CLOB needs allowance to spend your USDC. The Python client handles this:
```python
client.set_allowances()  # One-time approval
```

### API Access I Need

Store these as environment variables (I'll read them at trade time):

```bash
# In ~/.zshrc or a secure .env file
export POLY_PRIVATE_KEY="0x..."           # Wallet private key
export POLY_FUNDER_ADDRESS="0x..."        # Same as wallet address (EOA)
export POLY_API_KEY="..."                 # Generated via client
export POLY_API_SECRET="..."              # Generated via client  
export POLY_PASSPHRASE="..."             # Generated via client
```

### Setup Script

```bash
# Install the Python client
pip install py-clob-client

# Generate API credentials (run once)
python3 -c "
from py_clob_client.client import ClobClient
import os

client = ClobClient(
    host='https://clob.polymarket.com',
    chain_id=137,
    key=os.getenv('POLY_PRIVATE_KEY')
)

creds = client.create_or_derive_api_creds()
print('API Key:', creds.api_key)
print('Secret:', creds.api_secret)
print('Passphrase:', creds.api_passphrase)
print()
print('Add these to your .env file')
"
```

### What I Can Do With This

- Place limit and market orders
- Cancel orders
- Check positions and balances
- Monitor order fills
- Full programmatic trading — no browser needed

### Signature Type

For a standard wallet (MetaMask/generated): **signature_type = 0 (EOA)**
The wallet address is also the funder address.

---

## 2. Kalshi Setup (Secondary)

### UK Access
Kalshi is US-regulated (CFTC) but has been expanding internationally. Check https://kalshi.com for current UK availability. If restricted, skip and allocate to Polymarket.

### If Available
1. Create account at kalshi.com
2. KYC verification (passport/driving licence)
3. Deposit via bank transfer or card (accepts GBP → converts to USD)
4. API key from account settings

### API Access
```bash
export KALSHI_EMAIL="..."
export KALSHI_API_KEY="..."
```

---

## 3. Manifold Markets (Free Calibration)

1. Sign up at manifold.markets (Google/email)
2. Get free mana (play money)
3. Use for calibration practice — no financial risk
4. API: `https://api.manifold.markets/v0/` (API key from profile)

---

## 4. Metaculus (Forecasting Only)

1. Sign up at metaculus.com
2. Make predictions (no money involved)
3. Track calibration score on their platform
4. API: `https://www.metaculus.com/api/` (for data pulling)

---

## Security

### Critical Rules
- **Dedicated wallet**: Never use a wallet that holds other assets
- **Private key storage**: NOT in plaintext files. Use:
  - macOS Keychain: `security add-generic-password -a "polymarket" -s "private_key" -w "0x..."`
  - Or: encrypted .env with `age` or `gpg`
- **Spending limits**: The wallet only ever holds trading capital (£700 max)
- **No seed phrase backup in this repo**: Keep it offline (paper, hardware wallet)

### What I Store vs What You Store

| Item | Stored Where | Who Manages |
|------|-------------|-------------|
| Private key | macOS Keychain or encrypted .env | Yu (never in repo) |
| API credentials | Environment variables | Generated once, Yu stores |
| Trading logic | This repo (scripts/) | Claw |
| Trade logs | This repo (paper-trades/) | Claw |
| Position data | On-chain (Polygon) | Polymarket contracts |

---

## Funding Path (GBP → USDC)

Cheapest route from UK:

1. **Coinbase** (UK bank transfer, FCA registered)
   - Deposit GBP via Faster Payments (free, instant)
   - Buy USDC (0.6% fee)
   - Withdraw USDC to Polygon (low fee)

2. **Kraken** (alternative)
   - GBP deposit via bank transfer
   - Buy USDC
   - Withdraw to Polygon

3. **Direct on-ramp** (simplest but higher fee)
   - Use MoonPay/Transak directly to Polygon wallet
   - Higher fees (~2-3%) but one step

**Estimated costs for £700**:
- Exchange fee: ~£4 (0.6%)
- Withdrawal to Polygon: ~£0.50
- Total: ~£4.50 to get ~$875 USDC on Polygon

---

## Step-by-Step Checklist

- [ ] 1. Generate dedicated Polygon wallet
- [ ] 2. Save private key securely (Keychain)
- [ ] 3. Save wallet address
- [ ] 4. Deposit GBP to Coinbase/Kraken
- [ ] 5. Buy ~$880 USDC
- [ ] 6. Withdraw USDC to Polygon wallet
- [ ] 7. Send 0.1 POL to wallet for gas
- [ ] 8. Install py-clob-client: `pip install py-clob-client`
- [ ] 9. Run credential generation script
- [ ] 10. Store API credentials in environment
- [ ] 11. Run `client.set_allowances()` to approve USDC spending
- [ ] 12. Verify: check balance via API
- [ ] 13. Place a tiny test order ($1) to verify everything works
- [ ] 14. Sign up for Manifold (free calibration)
- [ ] 15. Sign up for Metaculus (forecasting)
- [ ] 16. (Optional) Check Kalshi UK availability

## After Setup

Tell me when the wallet is funded and credentials are in env. I'll:
1. Build the trading bot (scripts/trade.py)
2. Execute the first real trades from S06 (the 5 recommended trades)
3. Start the daily monitoring cycle
