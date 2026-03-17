# Bankroll Management

## Capital: £1,000 (~$1,250 USDC.e)

### Allocation Model

Not all capital deployed at once. Staged deployment based on confidence:

| Phase | Deployed | Purpose | Duration |
|-------|----------|---------|----------|
| **Phase 1: Proof** | $250 (20%) | Test pipeline, validate S006 + S004 edge | Weeks 1-4 |
| **Phase 2: Scale** | $500 (40%) | Expand to more markets + strategies | Weeks 5-8 |
| **Phase 3: Full** | $1,000 (80%) | Full deployment if Phase 1-2 profitable | Week 9+ |
| **Reserve** | $250 (20%) | Always held back — never deployed | Permanent |

The reserve exists because prediction markets can have correlated resolution events (e.g., geopolitical crisis resolves multiple GEO markets against us simultaneously).

---

## Position Sizing

### Per-Trade Limits

| Parameter | Limit | Rationale |
|-----------|-------|-----------|
| Max single trade | 10% of bankroll | No single bet can ruin us |
| Max per domain | 30% of bankroll | Diversification across knowledge areas |
| Max per strategy | 40% of bankroll | Don't overweight one approach |
| Max open positions | 15 | Manageable to track and research |
| Min trade size | $10 | Below this, fees and spread eat the edge |

### Strategy-Specific Sizing

| Strategy | Default Size | Max Size | Why |
|----------|-------------|----------|-----|
| S001 Hold | 5% | 8% | Calibration must be proven first |
| S002 Threshold | 5% | 8% | Same risk as S001 with exits |
| S003 Catalyst | 3-5% | 5% | Binary event risk |
| S004 Contrarian | 3% | 5% | Fading moves is inherently risky |
| S005 Momentum | 5% | 8% | Better risk/reward if trend is real |
| S006 Time Decay | 5% | 8% | Best validated edge — can size up |
| S007 Arb | 5% | 10% | Structural edge, lower risk |
| S008 Info Edge | 3-8% | 8% | Depends on edge type (see playbook) |

### Kelly Criterion

For each trade, the theoretically optimal bet fraction is:

```
f* = (p × b - q) / b

where:
  p = our estimated probability of winning
  b = payout odds (e.g., buy NO at $0.94, payout $1.00 → b = 0.064)
  q = 1 - p
```

**We use quarter-Kelly (f*/4)** because:
1. Our probability estimates have error bars
2. Kelly assumes infinite trades — we have limited capital
3. Overbetting is far worse than underbetting
4. Quarter-Kelly has ~50% of full-Kelly's return with ~10% of the variance

### Practical Example

S006 trade: Buy NO on "BTC $200K by 2026" at $0.94
- Our estimate: 97% resolves NO (from crypto research)
- Market: 94% NO → 6% YES
- Edge: 3%
- Payout: buy at $0.94, win $1.00 → profit $0.06 per share (6.4% return)
- Kelly: f* = (0.97 × 0.064 - 0.03) / 0.064 = 0.50 (50% of bankroll!)
- Quarter-Kelly: 12.5% of bankroll
- Capped at max 10%: **$125 position** (Phase 1) or **$100 position** (conservative)

---

## Drawdown Limits

### Hard Stops

| Trigger | Action | Recovery |
|---------|--------|----------|
| **-15% drawdown** (bankroll drops to $1,063) | Pause new trades. Review all open positions. | Re-evaluate all strategies. Only resume if cause is identified. |
| **-25% drawdown** (bankroll drops to $938) | Close all positions. Full stop. | 1-week mandatory cooling off. Full strategy review. Resume only with halved sizing. |
| **-40% drawdown** (bankroll drops to $750) | Withdraw remaining capital. | Complete system overhaul. Do not re-enter until root cause is fixed and backtested. |
| **Single trade -50%** | Close that trade immediately. | Document in lessons.md. Review if strategy is fundamentally flawed. |

### Soft Limits

| Trigger | Action |
|---------|--------|
| 3 consecutive losing trades | Reduce next trade size by 50% |
| Losing week | Review: was it bad luck or bad process? |
| Strategy at -10% lifetime P&L | Reduce allocation by 50%. If -20%, retire strategy. |
| Domain at -15% lifetime P&L | Stop trading that domain. Research what you're missing. |

### Drawdown Math

With our sizing (max 10% per trade, max 30% per domain):
- **Worst single trade**: -10% of bankroll ($125)
- **Worst domain blowup**: -30% of bankroll ($375) — only if all domain positions lose
- **Worst realistic scenario**: 3 correlated GEO trades lose + 1 CRY trade loses = ~-25%

This is why the -25% hard stop exists — it's the point where correlated losses become systemically dangerous.

---

## Practical Fund Flow

### Phase 1 ($250 deployed)

```
$1,250 total
├── $250 active trading capital (on Polygon)
│   ├── 2-3 S006 time decay positions ($75-100 each)
│   └── 1 S004 contrarian if spike detected ($50-75)
├── $750 in reserve (Polygon wallet, not deployed)
└── $250 permanent reserve (Polygon wallet)
```

### Phase 1 Target
- 4+ weeks of trading
- 10+ resolved trades
- Positive P&L or identifiable reason for losses
- Calibration data: am I beating the market?

### When to Scale to Phase 2
- Phase 1 P&L > 0%
- Brier score better than market on 5+ resolved predictions
- No hard stop triggered
- At least 2 strategies tested

### When to Scale to Phase 3
- Phase 1+2 combined P&L > 5%
- Drawdown never exceeded -15%
- 20+ resolved trades
- Calibration improving over time

---

## Fee Accounting

| Fee Type | Cost | Impact |
|----------|------|--------|
| Polymarket spread | ~1-2% on entry/exit | Built into trade P&L |
| Polygon gas | <$0.01 per trade | Negligible |
| VPS | $6/month | Fixed cost — need ~$6/month return to break even |
| QuickSwap swap fee | 0.3% | Only on POL→USDC.e swaps |

**Breakeven**: At $1,250 deployed, need 0.5% monthly return ($6.25) just to cover VPS. This is trivially achievable with the validated edges (S006 alone estimates 47-85% annual).

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Polymarket insolvency | Very low | Total loss of deployed capital | Don't deploy full bankroll; keep reserve |
| Geoblock expanded to Japan | Low | Can't trade | Migrate VPS to another non-blocked country |
| Smart contract exploit | Low | Loss of approved funds | Approve specific amounts (10K), not MAX_UINT |
| Correlated GEO events | Medium | Multiple positions lose simultaneously | 30% domain cap |
| Strategy edge disappears | Medium | Returns go to zero | Calibration system detects this; pivot |
| Private key compromise | Very low | Total loss | Dedicated wallet, Keychain only, no disk storage |
| Regulatory change | Medium | Platform restrictions | Diversify to Kalshi/Manifold when available |
| My calibration is bad | Medium | Systematic losses | Phase 1 catches this before scaling |

---

## Daily/Weekly Checklist

### Daily (9 AM cron handles most of this)
- [ ] Check open position P&L
- [ ] Any markets resolved overnight?
- [ ] Any spike opportunities? (spike-detector.py)
- [ ] Total bankroll vs yesterday

### Weekly (Sunday)
- [ ] Run calibration report
- [ ] Check drawdown vs limits
- [ ] Review: any positions to close?
- [ ] Check domain allocation vs limits
- [ ] Update P&L dashboard
- [ ] Log any lessons

### Monthly
- [ ] Full calibration analysis
- [ ] Strategy performance review
- [ ] Phase assessment: scale up/down?
- [ ] Feed insights into Ouroboros loop
