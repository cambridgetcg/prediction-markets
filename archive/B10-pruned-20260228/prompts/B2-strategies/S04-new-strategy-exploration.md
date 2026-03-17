You are a prediction market strategist exploring strategies we haven't thought of yet.

## Context from Prior Research
What we know works:
- S006 time decay: 73.5% of "by date" markets resolve NO. Sweet spot: YES 40-65%, 14-90 days, estimated 47-85% annual return.
- S004 contrarian: 58% negative serial correlation, ~40% reversion in 7 days post-spike. Best in GEO/CRY.
- Informational asymmetry: EU users blocked from trading → European political markets underinformed. Same likely applies to other blocked regions.
- YES bias: systematic overtrading of YES side across all markets.
- 70% of Polymarket traders lose money — large pool of unsophisticated counterparties.
- Neg risk markets enable capital-efficient multi-outcome trading.
Build on these findings — don't rediscover them. Look for what we're MISSING.

## Objective

The current strategy set (S001-S008) covers the obvious plays. But prediction markets have unique structural features that enable strategies impossible in traditional finance. Find them.

## Research Tasks

1. **Study the Polymarket structure**:
   - Order book mechanics (CLOB): how do limit orders work here?
   - Market making: is there an edge in providing liquidity? What are the rewards programs?
   - Neg-risk markets: what are they and how do they create opportunities?
   - Resolution mechanics: UMA oracle, resolution disputes — any edges here?
   - Fee structure: what are actual costs? How do they affect edge thresholds?

2. **Unique prediction market strategies** (research what's been tried):
   - **Resolution arbitrage**: Markets where resolution criteria are ambiguous — bet on the resolution mechanism, not the event
   - **Comment/sentiment analysis**: Do Polymarket comments predict price moves? Can sentiment be quantified?
   - **Whale watching**: Do large traders (visible on-chain) predict outcomes? Follow the smart money?
   - **Market creation edge**: Being first to recognize a new market will attract volume
   - **Correlation trading**: Betting on the spread between related markets
   - **Calendar effects**: Do prediction markets have day-of-week or time-of-day patterns?
   - **Liquidity provision**: Market making in prediction markets — the math
   - **Conditional chains**: If A resolves YES, what happens to market B? Pre-position for the chain.

3. **Cross-platform strategies**:
   - Same question on Polymarket vs Metaculus vs Manifold at different prices
   - Different resolution criteria across platforms for "same" event
   - Speed advantage: which platform prices information first?

4. **AI-native strategies**:
   - Using LLMs to process news faster than the market
   - Automated research pipelines that update probability estimates
   - Ensemble methods: combine multiple model estimates
   - Sentiment analysis of social media / news flow as real-time signal
   - Can an AI system be a consistently profitable prediction market trader? Literature review.

5. **Anti-strategies** (what definitely doesn't work):
   - Common retail mistakes in prediction markets
   - Why most "systems" fail
   - Survivorship bias in trader success stories

## Output

Write to: `~/Desktop/prediction-markets/strategies/evolution/new-strategy-research.md`

For each promising strategy discovered:
- Name and codename
- Edge hypothesis
- Rough entry/exit rules
- Data requirements
- Feasibility assessment (1-5)
- Should we add it to the playbook?

Update `~/Desktop/prediction-markets/strategies/README.md` if new strategies should be added to the registry.
Update `~/Desktop/prediction-markets/strategies/evolution/lineage.md` with any new additions.

End with:
- Top 3 new strategies worth pursuing
- Top 3 strategies that sound good but probably don't work
- Biggest structural edge unique to prediction markets
