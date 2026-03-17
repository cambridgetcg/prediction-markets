#!/usr/bin/env python3
"""Approve Polymarket contracts to spend USDC.e."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keystore import _keychain_get

from web3 import Web3

RPC = 'https://polygon-bor-rpc.publicnode.com'
USDC_E = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
FUNDER = '0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3'

# Polymarket contracts that need approval
CTF_EXCHANGE = '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E'
NEG_RISK_EXCHANGE = '0xC5d563A36AE78145C45a50134d48A1215220f80a'
NEG_RISK_ADAPTER = '0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296'

ERC20_ABI = [
    {
        "inputs": [{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],
        "name": "approve",
        "outputs": [{"name":"","type":"bool"}],
        "type": "function"
    },
    {
        "inputs": [{"name":"owner","type":"address"},{"name":"spender","type":"address"}],
        "name": "allowance",
        "outputs": [{"name":"","type":"uint256"}],
        "type": "function"
    }
]

MAX_UINT = 2**256 - 1

def approve_all():
    w3 = Web3(Web3.HTTPProvider(RPC))
    key = _keychain_get('poly_private_key')
    if not key.startswith('0x'):
        key = '0x' + key
    
    usdc = w3.eth.contract(address=USDC_E, abi=ERC20_ABI)
    
    contracts = {
        'CTF Exchange': CTF_EXCHANGE,
        'Neg Risk Exchange': NEG_RISK_EXCHANGE,
        'Neg Risk Adapter': NEG_RISK_ADAPTER,
    }
    
    for name, addr in contracts.items():
        # Check current allowance
        allowance = usdc.functions.allowance(FUNDER, addr).call()
        if allowance > 10**18:  # Already approved with large amount
            print(f"✓ {name} already approved (allowance: {allowance / 1e6:.0f} USDC.e)")
            continue
        
        print(f"Approving {name} ({addr})...")
        nonce = w3.eth.get_transaction_count(FUNDER)
        
        tx = usdc.functions.approve(addr, MAX_UINT).build_transaction({
            'from': FUNDER,
            'gas': 60000,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
            'chainId': 137,
        })
        
        signed = w3.eth.account.sign_transaction(tx, key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        
        if receipt['status'] == 1:
            print(f"  ✓ Approved! Gas: {receipt['gasUsed']}")
        else:
            print(f"  ✗ Failed! TX: {tx_hash.hex()}")
    
    key = None
    print("\n✓ All Polymarket contracts approved")

if __name__ == "__main__":
    approve_all()
