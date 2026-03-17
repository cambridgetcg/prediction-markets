# S011 — High-Probability Bond Rotation

**Phase**: NIGREDO (researched, not yet backtested)
**Type**: Capital Efficiency / Yield
**Edge hypothesis**: Buying >95% probability contracts with near-term resolution turns prediction markets into a yield instrument. Systematically rotating through short-duration, high-probability contracts generates returns exceeding Treasury bills with prediction-market-specific tail risk.
**Research**: `strategies/evolution/new-strategy-research.md`, `research/resolution-window-analysis.md`

## Why This Exists

Between directional trades (S004, S006, S008), bankroll sits idle. Prediction markets have a structural equivalent to short-term bonds: contracts trading at 95-99c that will resolve within days.

The favorite-longshot bias (documented across betting markets for decades, confirmed on Polymarket by Reichenbach & Walther 2025) means high-probability contracts are systematically underpriced — they resolve correctly MORE often than their price implies.

```
Buy at $0.96 → Resolve YES in 5 days → $1.00 payout
Net return: $0.04 / $0.96 = 4.17%
Annualized: (1.0417)^(365/5) - 1 = 1,967% (theoretical)
After 2% winner fee: ($0.04 - $0.02) / $0.96 = 2.08% per 5 days = 612% annualized
```

**The catch**: One failure at 96c wipes out 48 successful 96c trades (before fees). This is not risk-free — it's structured risk with fat tails.

## The Math

### Return per Trade

```
gross_return = (1.00 - entry_price) / entry_price
fee = 0.02 × 1.00 = $0.02 per winning share (2% winner fee)
net_return = (1.00 - entry_price - 0.02) / entry_price
```

### Returns at Various Entry Prices

| Entry | Gross Return | Net (after 2% fee) | Trades to Recover 1 Loss | Min Win Rate |
|-------|-------------|---------------------|--------------------------|-------------|
| $0.95 | 5.26% | 3.16% | 32 trades | 96.9% |
| $0.96 | 4.17% | 2.08% | 48 trades | 97.9% |
| $0.97 | 3.09% | 1.03% | 97 trades | 99.0% |
| $0.98 | 2.04% | 0.00% | ∞ (break-even) | 100.0% |
| $0.99 | 1.01% | -1.01% | N/A (net negative) | >100% (impossible) |

**Critical insight**: **At $0.98+, the 2% winner fee makes this strategy NET NEGATIVE.** The bond rotation sweet spot is $0.95-0.97. Above $0.97, fee drag exceeds the available spread.

### Annualized Returns (Net of Fee)

| Entry | 3-day resolve | 5-day resolve | 7-day resolve |
|-------|--------------|--------------|--------------|
| $0.95 | 2,847% | 1,432% | 930% |
| $0.96 | 1,361% | 612% | 378% |
| $0.97 | 401% | 139% | 76% |

These numbers look extraordinary but are misleading:
1. You can't compound infinitely — one loss resets
2. Finding enough qualifying markets to maintain continuous rotation is the constraint
3. The 2-5% failure rate at 95c has outsized impact

### Expected Value Calculation

Assuming 97% true success rate at 95c entry (favorite-longshot bias gives ~2pp edge):
```
EV = 0.97 × $0.0316 + 0.03 × (-$0.95 + $0.00)
EV = $0.0307 - $0.0285
EV = +$0.0022 per share (+0.23% per trade)
```

This is thin. The edge comes from:
1. Compounding many small positive-EV trades
2. The favorite-longshot bias providing the ~2pp calibration edge
3. Efficient capital deployment during otherwise idle periods

## Rules

### Screening Criteria

All must be true:
1. **Probability > 95%** on one side (YES or NO)
2. **Resolution within 7 days** (shorter = better capital efficiency)
3. **Liquidity > $50K** total volume (need to enter and exit without moving price)
4. **RAI ≤ 2** (S009 overlay — ONLY crystal-clear resolution criteria)
5. **Entry price ≤ $0.97** (fee-adjusted breakeven — above this, returns are zero or negative)
6. **Not a fee-enabled market** (sports/crypto short-term markets have additional taker fees that compress returns further)

### Qualifying Market Types (Best to Worst)

| Type | Resolution Speed | Typical Entry | Fee Impact | Priority |
|------|-----------------|---------------|------------|----------|
| **Fed rate decisions** (night before) | Next day | 96-97c | None (fee-free) | 1st — highest conviction |
| **Scheduled political events** | 1-3 days | 95-97c | None | 2nd — clear resolution |
| **"By date" markets** (date imminent, event hasn't happened) | 1-7 days | 95-97c NO | None | 3rd — S006 synergy |
| **Election results** (after early returns) | Hours | 97-99c | None | 4th — thin spread |
| **BTC/crypto thresholds** | Varies | 95-97c | Possible fees | 5th — volatility risk |

### The "Overnight Decay" Opportunity

The highest-conviction S011 trade is the night before a scheduled binary event:

**Example**: Fed March 2026 meeting. CME FedWatch shows 98% probability of no cut. Polymarket "Fed cuts rates" trading at 3c YES / 97c NO.

- Buy NO at 97c the night before
- Fed announces no cut (98% base rate probability)
- Collect $1.00 next day
- Net: 1.03% in ~16 hours (after fee)

**Why this works**: The 97c price already implies 97% probability, but CME FedWatch and bond markets are pricing 98%+. The 1pp edge is real (prediction markets slightly discount vs. derivatives markets on Fed decisions). AND the 2% failure rate includes genuine surprise scenarios that you can evaluate as even lower when CME is at 98%+.

### Entry Process

1. Run daily screen: markets at >95% with <7 day resolution
2. Verify resolution criteria are clear (RAI ≤ 2)
3. Check that the 95%+ price is genuine (not stale/illiquid): verify last trade within 24h, check news
4. Calculate net return after 2% fee: (1.00 - price - 0.02) / price. Must be > 0.5%.
5. Place **limit order** at target entry price (never market order — spread matters at these margins)
6. Max 5% of bankroll per position

### Exit Rules

- **HOLD TO RESOLUTION. ALWAYS.**
- Never sell early. The 1-3% remaining upside is small, but the spread cost of exiting and re-entering another bond position destroys the economics.
- Exception: If you discover new information that lowers your confidence below 95% → exit immediately (this should be rare if screening criteria are met).

### Position Sizing

- **Max 5% of bankroll per S011 position**
- **Max 20% of bankroll deployed in S011 total** (4 concurrent positions max)
- **This is SUPPLEMENTARY capital deployment**: S011 uses bankroll that would otherwise sit idle between S004/S006/S008 trades
- **Never let S011 crowd out directional trades**: If a high-conviction S006 or S004 opportunity appears, exit S011 positions early if needed (accept the spread cost)

## What Would Kill This Strategy

- **Oracle manipulation on a near-certain market**: Ukraine mineral deal ($7M) and Fort Knox ($3.5M) were both manipulated. One manipulation at 95c wipes 32 successful trades.
- **The 2% fee increasing**: If Polymarket raises the winner fee, the already-thin margin evaporates. At 3% fee, S011 is unviable at any entry price.
- **Favorite-longshot bias disappearing**: If high-probability contracts become properly calibrated, the ~2pp edge vanishes and S011 becomes zero-EV after fees.
- **Insufficient qualifying markets**: If there aren't enough 95-97c markets with <7d resolution, capital sits idle anyway.

## Risk Management

### The Steamroller Problem

S011 is the textbook "picking up pennies in front of a steamroller." Mitigations:

1. **RAI filter is non-negotiable**: Only RAI 1-2 markets. The failure cases (Ukraine deal, Fort Knox, UFO) were all RAI 4-5. Clean-resolution markets (Fed decisions, elections with clear criteria) have near-zero manipulation history.

2. **Position cap at 5%**: Even a total loss on one position is survivable.

3. **Diversify across resolution types**: Don't stack all 4 positions on the same event type. Mix Fed decisions, political milestones, crypto thresholds.

4. **Check MOOV2 proposer history**: Markets proposed by experienced, high-accuracy proposers are safer. Avoid markets where the proposer has had prior disputes.

5. **Monitor during liveness period**: If a dispute is filed during the 2-hour liveness, the risk profile changes entirely. Be prepared to exit (at a loss) if dispute appears.

### Expected Drawdown

At 97% win rate, 4 concurrent positions, 5% sizing each:
- Probability of ≥1 loss per 10 rotations: 1 - 0.97^10 = 26%
- Expected loss magnitude: 5% of bankroll (one position)
- Maximum realistic drawdown from S011: 5% (single loss) or 10% (two coincident losses, extremely unlikely)

This is acceptable as a secondary strategy that deploys idle capital.

## S011 vs. Treasury Bills

| Metric | S011 (prediction markets) | 3-Month T-Bill |
|--------|--------------------------|----------------|
| Annualized return (net) | 50-150% (realistic, not theoretical) | ~5.0% |
| Failure mode | Catastrophic (0 or 1 payoff) | None (risk-free) |
| Liquidity | Limited (hold to resolution) | Highly liquid |
| Counterparty risk | Oracle manipulation, platform risk | US government |
| Capital efficiency | ~20% of bankroll deployed | 100% deployable |
| Effort | Daily screening + monitoring | Zero |

**S011 is NOT a T-Bill replacement.** It's a way to earn excess return on idle prediction market bankroll that can't be easily withdrawn and redeployed to traditional instruments between trades.

## Screener (R04)

**Built**: `scripts/fast-resolution-screener.py`

```bash
# Daily screen (S011 sweet spot)
python3 scripts/fast-resolution-screener.py --days 7 --min-prob 0.95

# Broader scan with deployment recommendation
python3 scripts/fast-resolution-screener.py --days 30 --min-prob 0.90 --deploy

# Event day (tight parameters)
python3 scripts/fast-resolution-screener.py --days 2 --min-prob 0.93 --min-liq 50000
```

### Initial Screening Results (2026-02-25)

- **16 S011-viable** opportunities in next 7 days (entry ≤97c, net return >0.5%)
- **25 S011-viable** in next 30 days
- Most abundant: sports spread markets (but fee-enabled — caution), Iran daily "next strike" markets, AI model ranking markets, commodity threshold markets
- Best non-sports candidates: Iran daily strike NO at 95-97c, Google AI model NO at 96.4c, Gold $5,500 NO at 96.7c
- **Key finding**: Sports spread markets dominate the screen but have taker fees (rule 6 violation). Filter these out for true S011 — or treat separately as fee-adjusted trades where net return remains positive.

### Calendar Integration

See `strategies/fast-resolution-calendar.md` for:
- S011 rotation calendar (FOMC, NFP, CPI overnight opportunities)
- 60-day event calendar
- Monthly recurring SOTU-pattern events

## Evolution Hooks

- ~~**Automated screener**: Build `scripts/bond-screener.py`~~ → **DONE**: `scripts/fast-resolution-screener.py`
- **Track S011 win rate**: Log every trade. If win rate drops below 95% over 20+ trades, re-evaluate.
- **Fee monitoring**: Track any Polymarket fee changes. If winner fee increases, S011 may become unviable.
- **Combine with S009**: Use RAI score as a hard filter. S011 + S009 = only enter bonds on RAI 1-2 markets.
- **Resolution speed data**: Track actual resolution speed (event → settlement). Shorter = better capital efficiency. Build historical database.
- **The "liveness arbitrage"**: If bots aren't already doing this, buying at 97-99c during the 2-hour liveness period (after proposal, before settlement) is the lowest-risk version of S011. Research whether this is already competed away.
- **Sports fee filter**: Add `--exclude-sports` flag to screener to filter out fee-enabled markets (NCAAB, Serie A, crypto short-term).
