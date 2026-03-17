# Prediction Markets — Heartbeat Checklist

## Whale Alerts
- Check `~/Desktop/prediction-markets/data/pending-whale-alerts.json`
- If undelivered alerts exist with score >= 7: send immediately via Telegram
- If score 4-6: batch and send as daily summary
- Run scanner: `python3 scripts/whale-activity-scanner.py --hours 4 --alert`
- Continuous mode: `python3 scripts/whale-activity-scanner.py --continuous --interval 15 --alert`

### Alert Priority
| Score | Action | Urgency |
|-------|--------|---------|
| 7-10  | Send immediately | Real-time |
| 4-6   | Daily summary | End of day |
| 0-3   | Log only | Weekly review |

### Quick Commands
```bash
# One-shot scan, last 4 hours, queue alerts
python3 scripts/whale-activity-scanner.py --hours 4 --alert

# GEO insiders only
python3 scripts/whale-activity-scanner.py --domain GEO --alert

# ricosuave666 deep dive
python3 scripts/whale-activity-scanner.py --wallet 0x0afc --hours 72

# Machine-readable for pipeline integration
python3 scripts/whale-activity-scanner.py --json --min-score 4
```

## News Intelligence Pipeline
- Check `~/Desktop/prediction-markets/data/signals.jsonl` for pending signals
- Review dead letters in `data/news-pipeline.db` (dead_letters table)

## Paper Trading Positions
- Review `strategies/paper-trades/positions.json` for stop-loss triggers
- Cross-reference whale activity against open positions for contradictions
