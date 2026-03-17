You are a systems engineer integrating multiple prediction market platforms into a unified forecasting system.

## Context from Prior Research
Polymarket's domain coverage gaps identified:
- ENV (climate/energy): almost zero coverage — Metaculus is primary
- SCI (science): very limited — Metaculus is primary
- LAW (legal): limited — Metaculus has some
- SOC (culture): limited beyond sports/entertainment
The AI landscape research showed Metaculus community predictions are well-calibrated. Manifold has the broadest topic coverage but uses play money (lower signal quality). Cross-platform price divergence could itself be a trading signal.

## Objective

Polymarket is our primary source but it skews toward politics, crypto, and sports. Metaculus excels at science/tech/AI questions. Manifold has the broadest coverage. Integrate them.

## Research & Build Tasks

1. **Metaculus API**:
   - Research the Metaculus API: `https://www.metaculus.com/api/`
   - What endpoints are available? Authentication requirements?
   - Can we fetch: active questions, community predictions, resolution status?
   - Write a fetch script: `scripts/fetch-metaculus.py`
   - Focus on: AI/tech, science, climate, geopolitics questions
   - Map to our domain taxonomy (GEO/POL/ECO/etc.)

2. **Manifold Markets API**:
   - Research the Manifold API: `https://docs.manifold.markets/api`
   - Manifold uses play money (mana) — how does this affect signal quality?
   - Write a fetch script: `scripts/fetch-manifold.py`
   - Focus on: unique questions not covered by Polymarket
   - Note: Manifold has user-created markets — quality varies widely

3. **Cross-platform comparison**:
   - Find questions that exist on multiple platforms
   - Compare prices/probabilities: are they consistent?
   - Where they diverge: which platform tends to be more accurate?
   - Write findings to: `sources/cross-platform-analysis.md`

4. **Unified market tracker**:
   Design a unified format:
   ```json
   {
     "question": "...",
     "domain": "TEC",
     "sources": {
       "polymarket": {"price": 0.45, "liquidity": 100000, "url": "..."},
       "metaculus": {"community": 0.52, "participants": 500, "url": "..."},
       "manifold": {"price": 0.48, "volume": 5000, "url": "..."}
     },
     "consensus": 0.48,
     "divergence": 0.07,
     "my_estimate": null
   }
   ```
   Write spec to: `sources/unified-format.md`

5. **Platform strengths mapping**:
   | Platform | Best for | Worst for | Signal quality | Liquidity |
   |----------|----------|-----------|---------------|-----------|
   | Polymarket | ? | ? | ? | ? |
   | Metaculus | ? | ? | ? | ? |
   | Manifold | ? | ? | ? | ? |

6. **Domain coverage gaps**:
   - Which domains are poorly covered by Polymarket but well-covered elsewhere?
   - Write recommendations for which platform to prioritize per domain
   - Identify high-value questions available on other platforms that we should track

## Output

Scripts in `~/Desktop/prediction-markets/scripts/`
Analysis in `~/Desktop/prediction-markets/sources/`
Update domain active.md files with any new trackable markets from other platforms

End with:
- Integration priority: which platform adds the most value next?
- Top 10 non-Polymarket markets worth tracking immediately
- Cross-platform divergence opportunities (if any)
- Recommended daily workflow incorporating multiple platforms
