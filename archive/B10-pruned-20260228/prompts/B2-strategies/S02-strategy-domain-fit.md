You are a prediction market strategist analyzing which trading strategies work best in which knowledge domains.

## Objective

Build a strategy-domain fit matrix. Not all strategies work in all domains. Some domains are noisy (crypto), some are information-rich (politics), some are structurally mispriced (geopolitics). Match the right tool to the right terrain.

## Research Tasks

1. **Domain characteristics analysis**:
   For each domain (GEO, POL, ECO, FIN, CRY, TEC, SCI, SOC, LAW, ENV), assess:
   - **Information density**: How much public info exists? How fast does new info arrive?
   - **Participant sophistication**: Who's trading? Retail gamblers vs quants vs domain experts?
   - **Liquidity**: Typical market size, depth, spread
   - **Volatility**: How much do prices swing? On what timescale?
   - **Resolution clarity**: Binary outcomes vs fuzzy resolution criteria
   - **Time horizons**: Short (days), medium (weeks), long (months)
   - **Structural features**: "By date" markets, multi-outcome, conditional chains

2. **Strategy-domain compatibility scoring**:
   For each of the 8 strategies (S001-S008), rate compatibility (1-5) with each domain:

   | Strategy | Exploits | Best when domain has... |
   |----------|----------|------------------------|
   | S001 Hold | Calibration edge | High information density (I can know more) |
   | S002 Threshold | Volatility | Price swings but mean-reverts |
   | S003 Catalyst | Known future events | Scheduled events, clear catalysts |
   | S004 Contrarian | Overreaction | Emotional participants, dramatic events |
   | S005 Momentum | Persistent trends | Slow information digestion, narratives |
   | S006 Time Decay | Time premium overpricing | Fear-driven "by date" markets |
   | S007 Arb | Inconsistencies | Multi-outcome markets, nested deadlines |
   | S008 Info Edge | Research advantage | High info density + effort barrier |

3. **Historical evidence**:
   Research academic literature and blog posts on prediction market strategies:
   - Which strategies have been documented as profitable?
   - What does the literature say about prediction market efficiency by domain?
   - Key papers: Manski (2006), Arrow et al. (2008), prediction market efficiency studies
   - Practical: what do known prediction market traders (e.g., Polymarket leaderboard) seem to do?

4. **Recommended playbook by domain**:
   For each domain, produce a prioritized list: "Try these strategies first, in this order."
   Include reasoning.

5. **Anti-patterns**:
   Which strategy-domain combinations should be AVOIDED? Why?
   Example: S005 Momentum in ECO might be terrible because Fed decisions are discrete events, not trends.

## Output

Write to: `~/Desktop/prediction-markets/strategies/evolution/strategy-domain-matrix.md`

Create a visual matrix (markdown table) showing:
- Rows: strategies
- Columns: domains  
- Cells: compatibility score (1-5) with brief note

Also write recommended playbooks per domain to each domain's directory:
- `~/Desktop/prediction-markets/domains/GEO/recommended-strategies.md`
- (same for all 10 domains)

Update `~/Desktop/prediction-markets/strategies/evolution/meta-lessons.md` with any theoretical insights.

End with:
- Top 5 strategy-domain pairs to prioritize for first paper trades
- Top 5 strategy-domain pairs to avoid
- Where the biggest edge probably lives (domain + strategy + reasoning)
