You are a crypto/digital asset analyst building a knowledge base for prediction market forecasting.

## Context from Tier 1

The strategy-domain matrix (~/Desktop/prediction-markets/strategies/evolution/strategy-domain-matrix.md) identified CRY as ideal terrain for S002 (threshold exit) and S004 (contrarian overreaction) due to extreme volatility and emotional participants. S006 (time decay) also works well on "BTC by [date]" markets. The time decay backtest found 73.5% of "by date" markets resolve NO, with CRY at 71.1%. Your research should build the domain knowledge to deploy these strategies.

## Objective

Research the 2026 crypto market landscape. Active Polymarket markets include Bitcoin, Ethereum, and Solana price targets, plus regulatory markets. Current signals suggest short-term bearishness (all Feb upside targets at 0%) but the 2026 annual targets still have life ($200k BTC at 6%).

## Research Tasks

1. **Current market state**:
   - Bitcoin, Ethereum, Solana current prices and recent trajectory (last 30-90 days)
   - What caused the recent price action? Macro? Regulatory? Technical?
   - Where are we in the halving cycle? (Last halving April 2024, typically 12-18 months to peak)

2. **On-chain fundamentals**:
   - Bitcoin: hash rate, active addresses, exchange balances, MVRV ratio, long-term holder behavior
   - Ethereum: staking ratio, L2 activity, blob fees, DeFi TVL trends
   - Solana: TPS, developer activity, DeFi growth, meme coin dynamics

3. **ETF flows and institutional adoption**:
   - BTC ETF daily flows (trend over last 3 months)
   - ETH ETF status and flows
   - SOL ETF prospects
   - Institutional allocation trends (pension funds, endowments, corporates)

4. **Regulatory landscape**:
   - Trump admin crypto policy: what's been done vs promised?
   - SEC approach under current leadership
   - Stablecoin legislation status
   - Global regulatory trends (EU MiCA, Asia)

5. **Macro correlation**:
   - How correlated is crypto with risk assets currently?
   - Global liquidity (M2) trend
   - Dollar strength trajectory
   - Risk-on/risk-off regime

6. **Price target analysis**:
   - For the Polymarket "What price will Bitcoin hit in 2026" market, analyze each target:
     - $160k, $180k, $200k — what would need to happen?
   - Historical: in previous cycles, what was the peak-to-halving ratio?
   - Stock-to-flow, power law models — do they still have predictive value?

7. **Tail risks**:
   - What could cause a severe crypto downturn? (Tether, regulation, macro shock)
   - What could cause a blow-off top? (Strategic Bitcoin reserve, sovereign adoption)

## Output

Write to: `~/Desktop/prediction-markets/domains/CRY/research/crypto-2026.md`

Update:
- `~/Desktop/prediction-markets/domains/CRY/context.md` — update with current cycle position and models
- `~/Desktop/prediction-markets/domains/CRY/active.md` — fill in estimates
- `~/Desktop/prediction-markets/domains/CRY/sources.md` — add best data sources (on-chain, flows, etc.)

8. **Strategy deployment plan**:
   - For each active crypto market, which strategy (S002/S004/S005/S006) fits best?
   - Identify the single best first paper trade in CRY with full entry/exit/sizing rationale
   - What volatility patterns make S002 threshold exits viable? Typical swing sizes and durations?

## Output

Write to: `~/Desktop/prediction-markets/domains/CRY/research/crypto-2026.md`

Update:
- `~/Desktop/prediction-markets/domains/CRY/context.md` — update with current cycle position and models
- `~/Desktop/prediction-markets/domains/CRY/active.md` — fill in estimates with reasoning
- `~/Desktop/prediction-markets/domains/CRY/sources.md` — add best data sources (on-chain, flows, etc.)

End with:
- Bull case / bear case for BTC reaching $200k in 2026
- Your probability estimate for each active price target
- **Recommended first CRY paper trade** with full reasoning and strategy assignment
- Key leading indicators to monitor

You MUST use web_search to find current prices and recent data. Cite sources with URLs. Do not hallucinate prices — verify them.
