# AI Landscape Research — February 2026

*Research date: 2026-02-23*
*Supports: S001 (calibration edge), S008 (information edge), S003 (catalyst)*

---

## 1. Current Frontier Models

### Anthropic (Claude)

| Model | Released | SWE-bench | Arena Elo | Context | Pricing (in/out per M) |
|-------|----------|-----------|-----------|---------|----------------------|
| Claude Opus 4.6 | Feb 5, 2026 | 80.8% | ~1505 | 1M (beta), 128K out | $5 / $25 |
| Claude Sonnet 4.6 | Feb 17, 2026 | 79.6% | TBD | 1M | $3 / $15 |
| Claude Opus 4.5 | Nov 24, 2025 | 80.9% | 1466 | 200K | $5 / $25 |
| Claude 4 / Opus 4 | May 22, 2025 | — | — | 200K | — |

**Key strengths**: SWE-bench dominance, practical coding (Claude Code at $2.5B ARR), adaptive thinking in Opus 4.6.
**Recent moves**: $30B Series G at $380B valuation (Feb 12, 2026). $14B ARR. 500+ customers spending $1M+/year.

### OpenAI (GPT / o-series)

| Model | Released | Key Benchmark | Arena Elo | Context | Pricing (in/out per M) |
|-------|----------|--------------|-----------|---------|----------------------|
| GPT-5.3-Codex | Feb 5, 2026 | Agentic coding | — | — | — |
| GPT-5.2 | Dec 11, 2025 | GPQA 93.2% (Pro), AIME 100% | 1465 | 400K in / 128K out | $1.75 / $14 |
| GPT-5 | Aug 7, 2025 | MATH 98.1% | — | — | — |
| o3-pro | Jun 10, 2025 | Reliable reasoning | — | — | — |
| o3 / o4-mini | Apr 16, 2025 | Agentic tool use | — | — | — |

**Key strengths**: Math (MATH 98.1%, AIME 100%), FrontierMath (40.3%), ARC-AGI-1 (>90%). Massive compute infrastructure (Stargate).
**Recent moves**: Finalizing $100B round at $850B+ valuation. $20B ARR. Projects $14B in losses for 2026. GPT-6 targeting mid-2026.

### Google (Gemini)

| Model | Released | Key Benchmark | Arena Elo | Context | Pricing (in/out per M) |
|-------|----------|--------------|-----------|---------|----------------------|
| Gemini 3.1 Pro Preview | Feb 19, 2026 | ARC-AGI-2 77.1%, GPQA 94.3% | ~1500 | 1M | $2 / $12 |
| Gemini 3 Pro | Late 2025 | HLE 37.52% | 1492 | 1M | $2 / $12 |
| Gemini 3 Flash | Late 2025 | Fast + capable | 1470 | 1M | Cheap |
| Gemini 2.5 Pro | Mar 2025 | Adaptive reasoning | 1460 | 1M | — |

**Key strengths**: Scientific reasoning (GPQA, Humanity's Last Exam), novel reasoning (ARC-AGI-2 77.1% — best by far), multimodal, distribution to 2B+ Search users.
**Recent moves**: Gemini 3.1 Pro Preview just dropped Feb 19. Google I/O May 19-20 is major catalyst.

### xAI (Grok)

| Model | Released | Key Benchmark | Arena Elo | Context | Notes |
|-------|----------|--------------|-----------|---------|-------|
| Grok 4.20 Beta | Feb 17, 2026 | Alpha Arena (trading) | — | — | 4-agent collaboration |
| Grok 4.1 | Nov 17, 2025 | — | 1482 (thinking) | — | Reduced hallucination |
| Grok 4 | Jul 9, 2025 | — | — | — | First-principles reasoning |

**Key strengths**: Thinking/reasoning (Arena #2), financial applications, X platform data access.
**Recent moves**: SpaceX-xAI merger ($1.25T combined). Grok 5 (6T params) training, Q1 2026 target. Open-sourcing Grok 3.

### DeepSeek

| Model | Released | Key Benchmark | Context | Notes |
|-------|----------|--------------|---------|-------|
| DeepSeek V4 | Mid-Feb 2026 | ~80%+ SWE-bench (internal) | 1M | 1T params, 10-40x cheaper |
| DeepSeek R1 | Jan 2025 | Frontier reasoning | — | "Sputnik moment" |

**Key strengths**: Cost efficiency (10-40x cheaper), open-source (Apache 2.0), runs on dual RTX 4090s.
**Constraints**: US chip export controls, Huawei chip difficulties. R2 delayed (76% chance before Mar 1 per prediction markets).

### Meta (Llama)

| Model | Released | Key Feature | Context | Notes |
|-------|----------|------------|---------|-------|
| Llama 4 Maverick | Apr 5, 2025 | 17B active / 128 experts | 1M | Open weights |
| Llama 4 Scout | Apr 5, 2025 | 17B active / 16 experts | 10M | Industry-leading context |
| Llama 4 Behemoth | NOT released | 288B active / ~2T total | — | Still training, delayed |

**Status**: $115-135B capex planned for 2026. Behemoth repeatedly delayed. 11/14 original Llama researchers left. Qwen has overtaken Llama in open-weight community.

### Other Notable

| Model | Lab | Released | Key Metric |
|-------|-----|----------|-----------|
| Qwen 3.5 | Alibaba | Feb 16, 2026 | SWE-bench 76.4%, 201 languages, Apache 2.0 |
| MiniMax M2.5 | MiniMax | Feb 12, 2026 | SWE-bench 80.2%, open-source, extremely cheap |
| Mistral Large 3 | Mistral | Dec 2, 2025 | 675B total MoE, Apache 2.0 |
| ERNIE 5.0 | Baidu | — | Arena Elo 1461 (#9) |

---

## 2. Chatbot Arena Rankings (Feb 2026)

### Overall Rankings (from LMSYS/arena.ai)

| Rank | Model | Organization | Elo |
|------|-------|-------------|-----|
| 1 | Claude Opus 4.6 (thinking) | Anthropic | ~1505 |
| 2 | Claude Opus 4.6 | Anthropic | ~1502 |
| 3 | Gemini 3.1 Pro Preview | Google | ~1500 |
| 4 | Gemini 3 Pro | Google | 1492 |
| 5 | Grok-4.1-Thinking | xAI | 1482 |
| 6 | Gemini 3 Flash | Google | 1470 |
| 7 | Claude Opus 4.5 (thinking-32k) | Anthropic | 1466 |
| 8 | GPT-5.2-high | OpenAI | 1465 |
| 9 | GPT-5.1-high | OpenAI | 1464 |
| 10 | Grok-4.1 | xAI | 1463 |

**CRITICAL for Polymarket**: Resolution uses **arena.ai Text tab, style control OFF**. Claude Opus 4.6 is reported #1 with style control off (Anthropic models typically rise when style is controlled for — they're less verbose, so controlling for style rewards substance).

### Benchmark Leadership by Domain

| Domain | Leader | Model | Score |
|--------|--------|-------|-------|
| Software Engineering | Anthropic | Opus 4.5 | SWE-bench 80.9% |
| Science (GPQA) | Google | Gemini 3.1 Pro | 94.3% |
| Math (MATH L5) | OpenAI | GPT-5 | 98.1% |
| Novel Reasoning (ARC-AGI-2) | Google | Gemini 3.1 Pro | 77.1% |
| Expert Knowledge (HLE) | Google | Gemini 3 Pro | 37.52% |
| Long-Context | OpenAI | o3 (medium) | 100% Fiction.liveBench |
| Financial/Trading | xAI | Grok 4.20 Beta | Only profitable Alpha Arena model |

**Key insight**: No single model dominates everything. The "best" model depends entirely on domain/task.

---

## 3. Scaling & Compute

### Infrastructure

- Inference now **two-thirds of all AI compute** (up from one-third in 2023)
- Datacenter spending: **$400B in 2026** from OpenAI, Meta, Google, xAI combined
- OpenAI targets ~$600B compute by 2030
- Meta 2026 capex: $115-135B (up from $72.2B in 2025)

### Inference Costs

- **10x cost reduction per year** for equivalent-quality inference
- $60/M tokens in 2021 → $0.06/M tokens today
- DeepSeek and Chinese labs undercut Western providers by ~90%
- MiniMax M2.5: "$1 to run continuously for 1 hour at 100 tokens/sec"
- Gartner: AI services cost will surpass performance as chief competitive factor by 2026

### Open Source vs Closed

The gap has **effectively collapsed**:
- Open models trail by only 5-7 quality index points on average
- MiniMax M2.5 (open): SWE-bench 80.2% vs Claude Opus 4.5 (closed): 80.9%
- Qwen 3.5, DeepSeek V4, Mistral Large 3 all Apache 2.0 at frontier quality
- Where closed still leads: managed API simplicity, absolute SWE-bench top, polished consumer experiences

---

## 4. AI Agents

### Coding Agents (Key Market)

| Agent | Revenue/Adoption | Key Metric |
|-------|-----------------|-----------|
| Claude Code | $2.5B ARR (Feb 2026) | 29M VS Code daily installs, 4% of GitHub commits |
| GitHub Copilot | Top 3 adoption | Deep IDE integration |
| Cursor | Top 3 adoption | Power user favorite |
| Devin | Goldman, Santander, Nubank | 3-4x output boost per Goldman CTO |
| OpenAI Codex | GPT-5.3-Codex | "Most capable agentic coding model" (OpenAI claim) |

### Enterprise Adoption

- Gartner: 40% of enterprise apps will have task-specific AI agents by end of 2026 (up from <5% in 2025)
- 40-70% reduction in development time reported
- Goldman Sachs: targeting 100% employee AI adoption by 2026, "hundreds to thousands" of Devin instances
- 1 in 5 businesses on Ramp now pay for Anthropic (was 1 in 25 a year ago)

---

## 5. Upcoming Releases & Catalysts

### Expected Q1-Q2 2026

| Model | Lab | Window | Confidence | Source |
|-------|-----|--------|-----------|--------|
| Grok 5 | xAI | Q1 2026 | Medium (Musk timeline risk) | Confirmed by Musk, 6T params |
| DeepSeek R2 | DeepSeek | 76% before Mar 1 | Medium-High | Polymarket, chip difficulties |
| Claude 5 | Anthropic | Q2-Q3 2026 | High (by Q3) | "claude-sonnet-5@20260203" leaked in Vertex AI |
| GPT-6 | OpenAI | Mid-2026 | Medium | Altman: "significant gains from 5.2 in Q1" |
| Llama 4 Behemoth | Meta | TBD 2026 | Low | Still training, team exodus |

### Catalyst Calendar

| Date | Event | Why It Matters |
|------|-------|---------------|
| Feb 28, 2026 | Polymarket "best AI model Feb" resolution | Arena.ai leaderboard snapshot |
| Mar 16-19, 2026 | NVIDIA GTC 2026 | AI infrastructure, chip announcements |
| Q1 2026 (anytime) | Grok 5 release window | 6T params, potential leaderboard shift |
| Q1 2026 (anytime) | DeepSeek R2 release | Could be another "Sputnik moment" |
| May 19-20, 2026 | Google I/O 2026 | "Most AI-centric event in company history" |
| Jun 2026 | Apple WWDC 2026 | AI integration across platforms |
| TBD 2026 | LlamaCon | Meta's first dedicated Llama conference |

### Release Cadence

**Model leadership changes hands every 2-4 months** (accelerating from 6-9 month cycles in 2023-2024):
- Nov 2025-Jan 2026: Google (Gemini 3)
- Feb 2026-present: Anthropic (Claude Opus 4.6)
- Next shift: likely Mar-May 2026 (Google I/O or Grok 5 or GPT-6 preview)

---

## 6. Regulation

### EU AI Act

- **Now**: Prohibited practices and AI literacy obligations enforceable (since Feb 2, 2025)
- **Active**: GPAI governance rules (since Aug 2, 2025)
- **CRITICAL**: Aug 2, 2026 — High-risk AI requirements fully enforceable. **Penalties up to 35M EUR or 7% global revenue.**
- **Implication**: Major compliance costs for AI companies serving EU market. Potential market for "EU-compliant AI" prediction markets.

### US Regulation

- **No comprehensive federal AI law** — patchwork of agency enforcement + executive orders
- Trump admin (2025-present): "Innovation-first" approach, executive order to restrict state AI regulation (Dec 11, 2025)
- Multiple state laws took effect Jan 1, 2026 (California, Texas, others) — but federal preemption creates uncertainty
- **Implication**: Lighter regulatory burden for US-based AI companies vs EU. Creates prediction market opportunity around specific regulatory actions.

---

## 7. Financial Landscape

| Company | ARR / Revenue | Valuation | Latest Funding | 2026 Capex |
|---------|--------------|-----------|----------------|-----------|
| OpenAI | $20B ARR | ~$850B (pending) | $100B closing Q1 | ~$600B target by 2030 |
| Anthropic | $14B ARR | $380B | $30B Series G (Feb 2026) | Not disclosed |
| xAI | Not disclosed | $250B (in SpaceX merger) | $20B (Jan 2026) | Part of SpaceX-xAI |
| Google (AI) | Not broken out | $2.3T+ (Alphabet) | Internal | $115B+ planned |
| Meta (AI) | $15-20B est. | $1.5T+ | Internal | $115-135B |
| DeepSeek | Not disclosed | Not valued | State-adjacent | Chip-constrained |

**Industry total**: ~$514B narrow AI market revenue in 2026. $4.8T projected by 2033.

---

## 8. Market Opportunities & Where Participants Are Wrong

### Common Misconceptions to Exploit

1. **"Best model" = one model dominates everything**. Reality: different models lead different domains. Markets asking "best model" depend on specific benchmark (e.g., Arena with style control OFF). Many participants vote on vibes, not the actual resolution criteria.

2. **Overweight recency bias on model releases**. A model released 2 weeks before resolution may not accumulate enough Arena votes to rank. The Feb 20 cutoff for new models to get Arena traction is real.

3. **Underestimate Chinese open-source labs**. DeepSeek V4 and MiniMax M2.5 match frontier SWE-bench at fraction of cost. Market has DeepSeek at only 0.2% for Feb — correct for Arena metric, but watch for future months.

4. **Overestimate OpenAI's current position**. GPT-5.2 is at Elo 1465 (#8 overall) and SWE-bench 69% (some sources say 80% for Pro). Market has OpenAI at only 0.4% for Feb — correctly priced. But 6.8% for March and 9.5% for June may be too low if GPT-6 materializes.

5. **Underestimate Anthropic's sustained lead**. Claude has held or shared the #1 Arena position since Opus 4.6 launched Feb 5. Market correctly prices Feb at 95% but March at only 64% — the question is whether any competitor can leapfrog in 5 weeks.

6. **Model release timelines are unreliable**. Grok 5 was "Q1 2026" and hasn't appeared. Llama 4 Behemoth has been delayed repeatedly. DeepSeek R2 hit chip problems. Markets pricing timeline certainty should be discounted.

### Specific Mispricing Opportunities

**March "best AI model" — Anthropic at 64%**: Probably underpriced. Claude Opus 4.6 has a commanding Arena lead (+19 Elo over Gemini 3 Pro). For Google to overtake by March 31, Gemini 3.1 Pro Preview would need to accumulate enough votes AND surpass Opus 4.6. Possible but the Arena lead is substantial. Fair value closer to 70-75%.

**March "best AI model" — Google at 21.5%**: Gemini 3.1 Pro Preview (1500 Elo) is close to Claude Opus 4.6 (~1505). If Google polishes 3.1 Pro from "Preview" to GA and it gains Arena traction, it could overtake. 21.5% may be slightly overpriced given the 5-point gap. Fair value ~15-18%.

**June "best AI model" — Anthropic at 37%**: Probably underpriced. Even if Claude 5 doesn't ship until Q3, Claude Opus 4.6 could hold Arena #1 through June. With Claude 5 leak suggesting imminent development, Anthropic could release it before June. Fair value ~45%.

**June "best AI model" — Google at 39.5%**: Google I/O (May 19-20) is a massive catalyst. New model announcement could shift Arena rankings before June 30. But Google would need to surpass Anthropic's lead. 39.5% feels about right given I/O catalyst.

**Claude 5 by April 30 at 40.5%**: The leaked "claude-sonnet-5@20260203" identifier and Anthropic's ~9-month cycle from Opus 4 (May 2025) points to Q1-Q2 2026. But Anthropic just released Opus 4.6 and Sonnet 4.6 in Feb — shipping Claude 5 by April would be unprecedented pace. 40.5% feels slightly overpriced. Fair value ~30-35%.

**GPT-6 by June 30 at 20%**: Altman promised "significant gains from 5.2 in Q1." But GPT-6 by June is aggressive given GPT-5 shipped Aug 2025 and GPT-5.2 Dec 2025. The naming is unclear — could be GPT-5.5 or 5.3 instead. 20% feels about right.

---

## 9. Recommended First TEC Paper Trade

### Trade: BUY Anthropic in "Best AI model end of March" at 64%

**Strategy**: S001 (Hold to Resolution) + S008 (Information Edge)

**Thesis**: Claude Opus 4.6 holds a commanding Chatbot Arena lead (~1505 Elo vs next non-Anthropic at ~1500 for Gemini 3.1 Pro Preview). With only 5 weeks until March 31 resolution:
- Anthropic currently holds #1 AND #2 on Arena (Opus 4.6 thinking + non-thinking)
- For Google to overtake, Gemini 3.1 Pro must go from "Preview" to GA, accumulate Arena votes, AND surpass Opus 4.6 — possible but tall order in 5 weeks
- No other lab (OpenAI, xAI, DeepSeek) has a realistic path to #1 by March 31
- The 64% price implies ~36% chance of someone overtaking Anthropic — likely too high given current Arena gap

**Edge type**: S008 Type A (synthesis of Arena data + model release timelines + vote accumulation dynamics)

**Entry**: 64% (current market)
**My estimate**: 72-78%
**Divergence**: +8-14% → exceeds 10% threshold
**Sizing**: 3% bankroll (quarter Kelly on ~12% edge)
**Exit**: Hold to resolution March 31

**Risk factors**:
- Google ships polished Gemini 3.1 Pro GA and it surges on Arena (moderate probability)
- Leaderboard methodology change (low probability)
- Claude Opus 4.6 discovered to have gaming/contamination issue (very low probability)

### Alternative Trade: SELL Google in "Best AI model end of March" at 21.5%

If Google feels overpriced at 21.5%, buying NO Google at ~78.5% offers small but likely profit. The gap from Gemini 3.1 Pro Preview (1500) to Claude Opus 4.6 (1505) is narrow but real, and "Preview" models face uncertainty about full Arena inclusion.

---

## Sources

### Benchmarks & Rankings
- [Arena.ai Leaderboard](https://arena.ai/leaderboard/text)
- [LM Council Benchmarks](https://lmcouncil.ai/benchmarks)
- [LMSYS Chatbot Arena Rankings](https://aidevdayindia.org/blogs/lmsys-chatbot-arena-current-rankings/lmsys-chatbot-arena-leaderboard-current-top-models.html)
- [LLM-Stats Benchmarks](https://llm-stats.com/benchmarks)
- [Artificial Analysis](https://artificialanalysis.ai/)
- [ARC Prize 2025 Results](https://arcprize.org/blog/arc-prize-2025-results-analysis)
- [Humanity's Last Exam Leaderboard](https://artificialanalysis.ai/evaluations/humanitys-last-exam)

### Model Releases
- [Anthropic: Claude Opus 4.6](https://www.anthropic.com/news/claude-opus-4-6)
- [Anthropic: Sonnet 4.6](https://winbuzzer.com/2026/02/17/anthropic-claude-sonnet-4-6-flagship-performance-mid-tier-pricing-xcxwbn/)
- [OpenAI: GPT-5.2](https://openai.com/index/introducing-gpt-5-2/)
- [OpenAI: GPT-5.3-Codex](https://openai.com/index/introducing-gpt-5-3-codex/)
- [Google: Gemini 3.1 Pro](https://venturebeat.com/technology/google-launches-gemini-3-1-pro-retaking-ai-crown-with-2x-reasoning)
- [DeepSeek V4](https://introl.com/blog/deepseek-v4-trillion-parameter-coding-model-february-2026)
- [Alibaba: Qwen 3.5](https://www.cnbc.com/2026/02/17/china-alibaba-qwen-ai-agent-latest-model.html)
- [MiniMax M2.5](https://www.minimax.io/news/minimax-m25)

### Industry & Finance
- [Anthropic $30B Series G](https://www.anthropic.com/news/anthropic-raises-30-billion-series-g-funding-380-billion-post-money-valuation)
- [OpenAI $100B round](https://techcrunch.com/2026/02/19/openai-reportedly-finalizing-100b-deal-at-more-than-850b-valuation/)
- [SpaceX-xAI merger](https://www.cnbc.com/2026/02/03/musk-xai-spacex-biggest-merger-ever.html)
- [Claude Code revenue](https://www.uncoveralpha.com/p/anthropics-claude-code-is-having)
- [Epoch AI: Inference price trends](https://epoch.ai/data-insights/llm-inference-price-trends)

### Regulation
- [EU AI Act Timeline](https://artificialintelligenceact.eu/implementation-timeline/)
- [US AI Legislation Overview](https://www.softwareimprovementgroup.com/blog/us-ai-legislation-overview/)

### Polymarket
- [Best AI Model End of February](https://polymarket.com/event/which-company-has-the-best-ai-model-end-of-february)
- [Best AI Model End of March](https://polymarket.com/event/which-company-has-the-best-ai-model-end-of-march-751)
- [Best AI Model End of June](https://polymarket.com/event/which-company-has-best-ai-model-end-of-june)
- [Claude 5 Released By](https://polymarket.com/event/claude-5-released-by)
- [GPT-6 Released By](https://polymarket.com/event/gpt-6-released-by)
