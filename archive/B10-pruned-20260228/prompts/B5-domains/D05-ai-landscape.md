You are an AI/technology research analyst building a knowledge base for prediction market forecasting.

## Context from Tier 1

The strategy-domain matrix identified TEC as best suited for S001 (hold — calibration edge from domain knowledge), S008 (info edge — arxiv/benchmark analysis), and S003 (catalysts — product launches). This domain has moderate competition but genuine effort barriers. Your research directly supports the system operator's work on AI-related projects (Legible Money blockchain, knowledge verification).

## Objective

Research the current AI model landscape. Polymarket has a "Which company has the best AI model end of February?" market with $2.9M liquidity. More broadly, build the TEC domain knowledge for forecasting AI-related markets.

## Research Tasks

1. **Current frontier models**:
   - List all major frontier models available as of Feb 2026: OpenAI (GPT series), Anthropic (Claude series), Google (Gemini), Meta (Llama), Mistral, xAI (Grok), DeepSeek, others
   - For each: release date, key benchmarks, notable capabilities, pricing
   - What benchmarks is the Polymarket "best model" market likely using? (LMSYS Chatbot Arena? MMLU? Custom?)

2. **Benchmark analysis**:
   - Current LMSYS Chatbot Arena rankings
   - Key benchmark results: MMLU, MATH, HumanEval, GPQA, ARC-AGI
   - Limitations of current benchmarks (saturation, gaming, narrow scope)
   - What would a "best model" actually mean in practice?

3. **Upcoming releases**:
   - What's expected in Q1-Q2 2026? Rumors, announcements, patterns
   - Which lab is most likely to make a leap? Why?
   - Release cadence patterns (how often does the "best" model change hands?)

4. **Scaling and compute**:
   - Current state of scaling laws — are we hitting diminishing returns?
   - Major datacenter buildouts (who, where, how much)
   - Inference cost trends
   - Open source vs closed: is the gap widening or narrowing?

5. **AI agents and deployment**:
   - State of AI agent capabilities (coding, research, workflow automation)
   - Which companies are furthest in agent deployment?
   - Enterprise adoption trends
   - Revenue trajectories for AI companies

6. **Regulation and safety**:
   - EU AI Act enforcement status
   - US regulatory approach under current admin
   - AI safety debates: current temperature
   - Impact on model development and deployment

7. **Market opportunities**:
   - What AI-related prediction markets exist or should exist?
   - Where do market participants systematically misunderstand AI capability?
   - Common misconceptions to exploit

## Output

Write to: `~/Desktop/prediction-markets/domains/TEC/research/ai-landscape-2026.md`

Update:
- `~/Desktop/prediction-markets/domains/TEC/context.md` — current models, key players, timeline
- `~/Desktop/prediction-markets/domains/TEC/active.md` — fill in estimates for "best AI model" market
- `~/Desktop/prediction-markets/domains/TEC/sources.md` — best sources for tracking AI developments

8. **Concrete market assessment**:
   - For the "best AI model end of Feb" market: fetch the actual sub-market prices from Polymarket and form an independent estimate for each candidate
   - What benchmark or definition is the market using? (Check resolution criteria)
   - Any other active AI/tech markets on Polymarket worth tracking?

## Output

Write to: `~/Desktop/prediction-markets/domains/TEC/research/ai-landscape-2026.md`

Update:
- `~/Desktop/prediction-markets/domains/TEC/context.md` — current models, key players, timeline
- `~/Desktop/prediction-markets/domains/TEC/active.md` — fill in estimates with reasoning for EACH sub-market
- `~/Desktop/prediction-markets/domains/TEC/sources.md` — best sources for tracking AI developments

End with:
- Assessment of "best AI model end of Feb" market — specific estimates per candidate
- Predicted AI developments for rest of 2026
- Where market participants are most likely wrong about AI
- **Recommended first TEC paper trade** with strategy assignment and reasoning

You MUST use web_search to find current LMSYS rankings, benchmark results, and recent model releases. Cite sources with URLs. Do not hallucinate model capabilities or benchmark scores.
