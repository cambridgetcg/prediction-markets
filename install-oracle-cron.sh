#!/usr/bin/env bash
#
# Install Oracle cron jobs for automated signal generation.
#
# Usage:
#   bash install-oracle-cron.sh          # Install cron entries
#   bash install-oracle-cron.sh --remove # Remove Oracle cron entries
#

PM_DIR="$HOME/Desktop/prediction-markets"
PYTHON="python3"

CRON_RUN="*/30 * * * * cd $PM_DIR && $PYTHON scripts/oracle-run.py >> data/oracle-run.log 2>&1"
CRON_DELIVER="*/15 * * * * cd $PM_DIR && $PYTHON scripts/oracle-deliver.py >> data/oracle-deliver.log 2>&1"
MARKER="# ORACLE-PIPELINE"

if [ "$1" = "--remove" ]; then
    echo "Removing Oracle cron entries..."
    crontab -l 2>/dev/null | grep -v "$MARKER" | crontab -
    echo "Done. Current crontab:"
    crontab -l 2>/dev/null || echo "(empty)"
    exit 0
fi

echo "Installing Oracle cron entries..."
echo ""
echo "  oracle-run.py    — every 30 minutes"
echo "  oracle-deliver.py — every 15 minutes"
echo ""

# Remove existing Oracle entries, then add fresh ones
(
    crontab -l 2>/dev/null | grep -v "$MARKER"
    echo "$CRON_RUN $MARKER"
    echo "$CRON_DELIVER $MARKER"
) | crontab -

echo "Installed. Current crontab:"
crontab -l
echo ""
echo "To remove: bash $0 --remove"
echo "Logs: $PM_DIR/data/oracle-run.log, $PM_DIR/data/oracle-deliver.log"
