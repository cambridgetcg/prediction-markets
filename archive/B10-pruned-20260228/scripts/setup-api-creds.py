#!/usr/bin/env python3
"""
Generate Polymarket API credentials and set up trading access.
Run AFTER wallet is funded with USDC + POL on Polygon.
"""

import os
import sys

def get_private_key():
    """Get private key from env or Keychain."""
    key = os.getenv("POLY_PRIVATE_KEY")
    if not key:
        import subprocess
        try:
            key = subprocess.check_output(
                ["security", "find-generic-password", "-a", "polymarket", "-s", "poly_private_key", "-w"],
                text=True
            ).strip()
        except:
            pass
    if not key:
        print("ERROR: No private key found. Set POLY_PRIVATE_KEY or store in Keychain.")
        sys.exit(1)
    # Ensure 0x prefix
    if not key.startswith("0x"):
        key = "0x" + key
    return key

def main():
    key = get_private_key()
    funder = os.getenv("POLY_FUNDER_ADDRESS", "0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3")
    
    print("Connecting to Polymarket CLOB...")
    
    from py_clob_client.client import ClobClient
    
    client = ClobClient(
        host="https://clob.polymarket.com",
        chain_id=137,
        key=key,
    )
    
    print("Generating API credentials...")
    creds = client.create_or_derive_api_creds()
    
    print()
    print("=" * 60)
    print("  API CREDENTIALS")
    print("=" * 60)
    print(f"  API Key:    {creds.api_key}")
    print(f"  Secret:     {creds.api_secret}")
    print(f"  Passphrase: {creds.api_passphrase}")
    print("=" * 60)
    print()
    
    # Store in Keychain
    import subprocess
    for name, val in [("poly_api_key", creds.api_key), 
                       ("poly_api_secret", creds.api_secret),
                       ("poly_api_passphrase", creds.api_passphrase)]:
        try:
            # Delete existing if any
            subprocess.run(["security", "delete-generic-password", "-a", "polymarket", "-s", name],
                         capture_output=True)
        except:
            pass
        subprocess.run(["security", "add-generic-password", "-a", "polymarket", "-s", name, "-w", val],
                      check=True, capture_output=True)
    
    print("✓ Credentials stored in macOS Keychain")
    print()
    
    # Add to .zshrc
    zshrc_addition = '''
# Polymarket API credentials (from Keychain)
export POLY_API_KEY=$(security find-generic-password -a "polymarket" -s "poly_api_key" -w 2>/dev/null)
export POLY_API_SECRET=$(security find-generic-password -a "polymarket" -s "poly_api_secret" -w 2>/dev/null)
export POLY_PASSPHRASE=$(security find-generic-password -a "polymarket" -s "poly_api_passphrase" -w 2>/dev/null)
'''
    
    with open(os.path.expanduser("~/.zshrc"), "r") as f:
        content = f.read()
    
    if "POLY_API_KEY" not in content:
        with open(os.path.expanduser("~/.zshrc"), "a") as f:
            f.write(zshrc_addition)
        print("✓ Added credential exports to ~/.zshrc")
    
    print()
    print("Now setting up allowances (approving USDC spending)...")
    
    # Re-init with full creds for trading
    from py_clob_client.clob_types import ApiCreds
    
    trading_client = ClobClient(
        host="https://clob.polymarket.com",
        chain_id=137,
        key=key,
        creds=ApiCreds(
            api_key=creds.api_key,
            api_secret=creds.api_secret,
            api_passphrase=creds.api_passphrase,
        ),
        signature_type=0,  # EOA wallet
        funder=funder,
    )
    
    try:
        trading_client.set_allowances()
        print("✓ USDC allowances set")
    except Exception as e:
        print(f"⚠ Allowance setup failed (wallet may need funding first): {e}")
        print("  Run this script again after funding the wallet.")
    
    # Check balance
    print()
    print("Checking balances...")
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        
        # POL balance
        pol_bal = w3.eth.get_balance(funder)
        print(f"  POL: {w3.from_wei(pol_bal, 'ether'):.4f}")
        
        # USDC balance (Polygon USDC contract)
        usdc_addr = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
        usdc_abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
        usdc = w3.eth.contract(address=usdc_addr, abi=usdc_abi)
        usdc_bal = usdc.functions.balanceOf(funder).call()
        print(f"  USDC: {usdc_bal / 1e6:.2f}")
    except Exception as e:
        print(f"  Balance check failed: {e}")
        print("  (web3 may not be installed — that's fine, check on Polygonscan)")
    
    print()
    print(f"View wallet on Polygonscan:")
    print(f"  https://polygonscan.com/address/{funder}")
    print()
    print("NEXT STEPS:")
    print(f"  1. Fund wallet: send USDC (Polygon) + POL to {funder}")
    print(f"  2. Run this script again after funding to set allowances")
    print(f"  3. Run verify-setup.py to confirm everything works")

if __name__ == "__main__":
    main()
