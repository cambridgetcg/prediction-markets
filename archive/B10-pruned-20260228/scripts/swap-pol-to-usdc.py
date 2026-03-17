#!/usr/bin/env python3
"""Swap POL → USDC.e on QuickSwap (Polygon)."""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from keystore import _keychain_get

from web3 import Web3

RPC = 'https://polygon-bor-rpc.publicnode.com'
QUICKSWAP_ROUTER = '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff'
WMATIC = '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270'
USDC_E = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'
FUNDER = '0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3'

ROUTER_ABI = [
    {
        "inputs": [{"name":"amountIn","type":"uint256"},{"name":"path","type":"address[]"}],
        "name": "getAmountsOut",
        "outputs": [{"name":"amounts","type":"uint256[]"}],
        "type": "function"
    },
    {
        "inputs": [
            {"name":"amountOutMin","type":"uint256"},
            {"name":"path","type":"address[]"},
            {"name":"to","type":"address"},
            {"name":"deadline","type":"uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"name":"amounts","type":"uint256[]"}],
        "type": "function",
        "stateMutability": "payable"
    }
]

def swap_pol_to_usdc(amount_pol: float, slippage_pct: float = 1.0):
    w3 = Web3(Web3.HTTPProvider(RPC))
    
    key = _keychain_get('poly_private_key')
    if not key.startswith('0x'):
        key = '0x' + key
    
    router = w3.eth.contract(address=QUICKSWAP_ROUTER, abi=ROUTER_ABI)
    amount_in = w3.to_wei(amount_pol, 'ether')
    
    # Get quote
    amounts = router.functions.getAmountsOut(amount_in, [WMATIC, USDC_E]).call()
    expected_usdc = amounts[1]
    min_usdc = int(expected_usdc * (1 - slippage_pct / 100))
    
    print(f"Swapping {amount_pol} POL → ~${expected_usdc / 1e6:.4f} USDC.e")
    print(f"Min output (with {slippage_pct}% slippage): ${min_usdc / 1e6:.4f}")
    
    # Build transaction
    deadline = int(time.time()) + 300  # 5 min
    nonce = w3.eth.get_transaction_count(FUNDER)
    
    tx = router.functions.swapExactETHForTokens(
        min_usdc,
        [WMATIC, USDC_E],
        FUNDER,
        deadline
    ).build_transaction({
        'from': FUNDER,
        'value': amount_in,
        'gas': 250000,
        'gasPrice': w3.eth.gas_price,
        'nonce': nonce,
        'chainId': 137,
    })
    
    # Sign and send
    signed = w3.eth.account.sign_transaction(tx, key)
    key = None  # Clear key immediately
    
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"TX sent: https://polygonscan.com/tx/{tx_hash.hex()}")
    
    # Wait for confirmation
    print("Waiting for confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    
    if receipt['status'] == 1:
        # Check new USDC.e balance
        usdc_abi = [{'constant':True,'inputs':[{'name':'_owner','type':'address'}],'name':'balanceOf','outputs':[{'name':'balance','type':'uint256'}],'type':'function'}]
        usdc = w3.eth.contract(address=USDC_E, abi=usdc_abi)
        new_bal = usdc.functions.balanceOf(FUNDER).call() / 1e6
        pol_bal = w3.from_wei(w3.eth.get_balance(FUNDER), 'ether')
        
        print(f"✓ Swap confirmed!")
        print(f"  USDC.e balance: ${new_bal:.4f}")
        print(f"  POL remaining: {pol_bal:.4f}")
        print(f"  Gas used: {receipt['gasUsed']}")
        return True
    else:
        print(f"✗ Swap failed! TX: {tx_hash.hex()}")
        return False

if __name__ == "__main__":
    amount = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
    swap_pol_to_usdc(amount)
