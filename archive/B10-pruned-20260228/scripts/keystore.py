#!/usr/bin/env python3
"""
Secure credential loader for Polymarket trading.

Keys are stored in macOS Keychain and retrieved ONLY when needed for signing.
They never persist in environment variables or memory longer than necessary.

Usage:
    from keystore import get_trading_client, get_readonly_client
    
    # For placing trades (needs private key — fetched from Keychain per-call)
    client = get_trading_client()
    
    # For reading data only (no private key needed)
    client = get_readonly_client()
"""

import subprocess
import sys


def _keychain_get(service: str) -> str | None:
    """Retrieve a value from macOS Keychain. Returns None if not found."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", "polymarket", "-s", service, "-w"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _keychain_set(service: str, value: str):
    """Store a value in macOS Keychain."""
    # Delete existing
    subprocess.run(
        ["security", "delete-generic-password", "-a", "polymarket", "-s", service],
        capture_output=True
    )
    subprocess.run(
        ["security", "add-generic-password", "-a", "polymarket", "-s", service, "-w", value],
        check=True, capture_output=True
    )


def get_credentials() -> dict:
    """
    Fetch all credentials from Keychain at the moment they're needed.
    Returns dict with keys: private_key, funder, api_key, api_secret, api_passphrase
    Raises if any critical credential is missing.
    """
    creds = {
        "private_key": _keychain_get("poly_private_key"),
        "funder": "0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3",
        "api_key": _keychain_get("poly_api_key"),
        "api_secret": _keychain_get("poly_api_secret"),
        "api_passphrase": _keychain_get("poly_api_passphrase"),
    }
    
    missing = [k for k, v in creds.items() if v is None and k != "funder"]
    if missing:
        raise RuntimeError(f"Missing credentials in Keychain: {missing}. Run setup-api-creds.py first.")
    
    # Ensure 0x prefix on private key
    if not creds["private_key"].startswith("0x"):
        creds["private_key"] = "0x" + creds["private_key"]
    
    return creds


def get_trading_client():
    """
    Create a fully authenticated Polymarket CLOB client.
    Private key is fetched from Keychain, used to init the client, 
    then the local reference goes out of scope.
    """
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds
    
    creds = get_credentials()
    
    client = ClobClient(
        host="https://clob.polymarket.com",
        chain_id=137,
        key=creds["private_key"],
        creds=ApiCreds(
            api_key=creds["api_key"],
            api_secret=creds["api_secret"],
            api_passphrase=creds["api_passphrase"],
        ),
        signature_type=0,  # EOA
        funder=creds["funder"],
    )
    
    # Clear local reference to private key
    creds["private_key"] = None
    del creds
    
    return client


def get_readonly_client():
    """
    Create a read-only CLOB client (no private key needed).
    For fetching prices, orderbooks, market data.
    """
    from py_clob_client.client import ClobClient
    
    return ClobClient(
        host="https://clob.polymarket.com",
        chain_id=137,
    )


if __name__ == "__main__":
    print("Keystore credential check:")
    try:
        creds = get_credentials()
        for k, v in creds.items():
            if k == "private_key":
                print(f"  {k}: {'✓ found' if v else '✗ missing'} ({v[:6]}...{v[-4:]})")
            elif v:
                print(f"  {k}: ✓ found")
            else:
                print(f"  {k}: ✗ missing")
        print("\n✓ All credentials available in Keychain")
    except RuntimeError as e:
        print(f"\n✗ {e}")
