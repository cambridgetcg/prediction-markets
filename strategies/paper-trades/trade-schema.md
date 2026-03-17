# Trade Schema

Every paper trade in `trades.jsonl` follows this schema:

```json
{
  "id": "T001",
  "ts_entry": "2026-02-23T10:00:00Z",
  "ts_exit": null,
  "strategy": "S001",
  "domain": "GEO",
  "market": "US strikes Iran by March 31, 2026",
  "market_id": "polymarket:xxxxx",
  "direction": "NO",
  "entry_price": 0.43,
  "exit_price": null,
  "size_usd": 500.00,
  "shares": 1162.79,
  "current_price": null,
  "current_value": null,
  "pnl_usd": null,
  "pnl_pct": null,
  "status": "open",
  "reasoning": "Base rate for US strikes on sovereign nations is ~X%. Market implies daily p of Y%, which seems high given...",
  "edge_type": null,
  "exit_reason": null,
  "prediction_id": "pred-0001",
  "notes": ""
}
```

## Fields

| Field | Type | Description |
|-------|------|-------------|
| id | string | Sequential trade ID (T001, T002...) |
| ts_entry | ISO date | When the trade was entered |
| ts_exit | ISO date | When the trade was closed (null if open) |
| strategy | string | Strategy ID (S001-S008+) |
| domain | string | Knowledge domain code |
| market | string | Human-readable market description |
| market_id | string | Platform:id reference |
| direction | YES/NO | Which outcome we're buying |
| entry_price | float | Price of the outcome we bought (0-1) |
| exit_price | float | Price we sold at (null if open, 1.0 or 0.0 if held to resolution) |
| size_usd | float | Dollar amount allocated |
| shares | float | size_usd / entry_price = number of shares |
| current_price | float | Latest market price (updated on snapshots) |
| current_value | float | shares * current_price |
| pnl_usd | float | Realized or unrealized P&L |
| pnl_pct | float | P&L as percentage of entry cost |
| status | string | open / closed / resolved |
| reasoning | string | Why this trade was entered |
| edge_type | string | For S008: A/B/C/D/E. For others: null |
| exit_reason | string | Why closed: resolution / target / stop / thesis-change / time-limit |
| prediction_id | string | Link to calibration/predictions.jsonl entry |
| notes | string | Any additional observations |
