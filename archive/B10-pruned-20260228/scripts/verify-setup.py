#!/usr/bin/env python3
"""Verify Polymarket trading setup is working end-to-end."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keystore import get_credentials, get_trading_client, _keychain_get

def main():
    print("=" * 60)
    print("  POLYMARKET SETUP VERIFICATION")
    print("=" * 60)
    print()
    
    checks = {
        "Private Key": False,
        "Funder Address": False,
        "API Key": False,
        "API Secret": False,
        "API Passphrase": False,
        "CLOB Connection": False,
        "Balance Check": False,
        "Order Capability": False,
    }
    
    # 1. Credentials (from Keychain only — never env vars)
    cred_map = {
        "Private Key": "poly_private_key",
        "API Key": "poly_api_key",
        "API Secret": "poly_api_secret",
        "API Passphrase": "poly_api_passphrase",
    }
    
    for name, service in cred_map.items():
        val = _keychain_get(service)
        if val:
            checks[name] = True
            if name == "Private Key":
                print(f"✓ {name} in Keychain ({val[:6]}...{val[-4:]})")
            else:
                print(f"✓ {name} in Keychain")
        else:
            print(f"✗ {name} NOT in Keychain — run setup-api-creds.py")
    
    funder = os.getenv("POLY_FUNDER_ADDRESS", "0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3")
    checks["Funder Address"] = True
    print(f"✓ Funder Address: {funder}")
    
    # Check env vars are NOT leaking secrets
    for env_var in ["POLY_PRIVATE_KEY", "POLY_API_KEY", "POLY_API_SECRET", "POLY_PASSPHRASE"]:
        if os.getenv(env_var):
            print(f"⚠ WARNING: {env_var} found in environment — should only be in Keychain!")
    
    if not all(checks.get(k, False) for k in cred_map):
        print("\n⚠ Missing credentials. Run setup-api-creds.py first.")
        print_summary(checks)
        return
    
    # 2. CLOB Connection (via keystore — key fetched from Keychain per-call)
    print("\nConnecting to CLOB (credentials from Keychain)...")
    try:
        client = get_trading_client()
        server_time = client.get_server_time()
        checks["CLOB Connection"] = True
        print(f"✓ CLOB connected (server time: {server_time})")
    except Exception as e:
        print(f"✗ CLOB connection failed: {e}")
        print_summary(checks)
        return
    
    # 3. Balance
    print("\nChecking on-chain balances...")
    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider("https://polygon-bor-rpc.publicnode.com"))
        
        pol_bal = w3.eth.get_balance(funder)
        pol_display = w3.from_wei(pol_bal, 'ether')
        
        usdc_addr = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e (Polymarket collateral)
        usdc_abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
        usdc = w3.eth.contract(address=usdc_addr, abi=usdc_abi)
        usdc_bal = usdc.functions.balanceOf(funder).call() / 1e6
        
        checks["Balance Check"] = True
        print(f"  POL:  {pol_display:.4f}")
        print(f"  USDC: ${usdc_bal:.2f}")
        if usdc_bal > 0:
            print(f"  ✓ Wallet is funded")
        else:
            print(f"  ⚠ Wallet is empty — fund with USDC on Polygon")
    except Exception as e:
        print(f"⚠ Balance check: {e}")
        print(f"  Check: https://polygonscan.com/address/{funder}")
    
    # 4. Order capability
    print("\nChecking order capability...")
    try:
        orders = client.get_orders()
        checks["Order Capability"] = True
        print(f"✓ Can query orders ({len(orders)} open)")
    except Exception as e:
        print(f"⚠ Order query: {e}")
    
    print()
    print_summary(checks)

def print_summary(checks):
    print()
    print("=" * 60)
    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    print(f"  RESULT: {passed}/{total} checks passed")
    print("=" * 60)
    for name, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {name}")
    print("=" * 60)
    
    if all(checks.values()):
        print("\n🟢 READY TO TRADE")
    elif checks["Private Key"] and checks["API Key"]:
        print("\n🟡 CREDENTIALS OK — fund wallet and set allowances")
    else:
        print("\n🔴 SETUP INCOMPLETE")

if __name__ == "__main__":
    main()
