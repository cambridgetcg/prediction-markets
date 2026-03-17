#!/bin/bash
# Execute a trading command on the VPS with credentials injected from local Keychain
# Credentials are passed via SSH environment — never stored on VPS disk
#
# Usage:
#   ./vps-exec.sh check          # Check geoblock status
#   ./vps-exec.sh list           # List open orders
#   ./vps-exec.sh cancel         # Cancel all orders
#   ./vps-exec.sh test <token> <price> <size>  # Place test order
#   ./vps-exec.sh python "code"  # Run arbitrary Python

VPS_HOST="trader@45.77.8.39"
VPS_PYTHON="/home/trader/polymarket/.venv/bin/python3"

# Fetch credentials from local Keychain
POLY_PRIVATE_KEY=$(security find-generic-password -a "polymarket" -s "poly_private_key" -w 2>/dev/null)
POLY_API_KEY=$(security find-generic-password -a "polymarket" -s "poly_api_key" -w 2>/dev/null)
POLY_API_SECRET=$(security find-generic-password -a "polymarket" -s "poly_api_secret" -w 2>/dev/null)
POLY_PASSPHRASE=$(security find-generic-password -a "polymarket" -s "poly_api_passphrase" -w 2>/dev/null)

if [ -z "$POLY_PRIVATE_KEY" ]; then
    echo "Error: Could not read credentials from Keychain"
    exit 1
fi

CMD="$1"
shift

case "$CMD" in
    check|list|cancel)
        ssh "$VPS_HOST" "cd /home/trader/polymarket && \
            POLY_PRIVATE_KEY='$POLY_PRIVATE_KEY' \
            POLY_API_KEY='$POLY_API_KEY' \
            POLY_API_SECRET='$POLY_API_SECRET' \
            POLY_PASSPHRASE='$POLY_PASSPHRASE' \
            POLY_FUNDER_ADDRESS='0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3' \
            $VPS_PYTHON scripts/trade.py $CMD $@"
        ;;
    test)
        ssh "$VPS_HOST" "cd /home/trader/polymarket && \
            POLY_PRIVATE_KEY='$POLY_PRIVATE_KEY' \
            POLY_API_KEY='$POLY_API_KEY' \
            POLY_API_SECRET='$POLY_API_SECRET' \
            POLY_PASSPHRASE='$POLY_PASSPHRASE' \
            POLY_FUNDER_ADDRESS='0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3' \
            $VPS_PYTHON scripts/trade.py test $@"
        ;;
    python)
        ssh "$VPS_HOST" "cd /home/trader/polymarket && \
            POLY_PRIVATE_KEY='$POLY_PRIVATE_KEY' \
            POLY_API_KEY='$POLY_API_KEY' \
            POLY_API_SECRET='$POLY_API_SECRET' \
            POLY_PASSPHRASE='$POLY_PASSPHRASE' \
            POLY_FUNDER_ADDRESS='0x4576F0B2b9Fe86359C6254Fc0C141d8C5090cDC3' \
            $VPS_PYTHON -c '$@'"
        ;;
    *)
        echo "Usage: vps-exec.sh <check|list|cancel|test|python> [args...]"
        ;;
esac
