# TEC — Sources

*Best sources for tracking AI developments relevant to prediction market forecasting.*

## Tier 1: Check Daily

### Benchmarks & Rankings
- **Arena.ai Leaderboard** — [arena.ai/leaderboard/text](https://arena.ai/leaderboard/text) — THE resolution criterion for "best AI model" Polymarket markets. Check style control ON vs OFF.
- **LM Council Benchmarks** — [lmcouncil.ai/benchmarks](https://lmcouncil.ai/benchmarks) — Cross-benchmark comparison: GPQA, SWE-bench, MMLU-Pro, MATH, HLE.
- **LLM-Stats** — [llm-stats.com](https://llm-stats.com/) — Aggregated benchmark results, model comparisons, leaderboard tracking.
- **Artificial Analysis** — [artificialanalysis.ai](https://artificialanalysis.ai/) — Pricing, speed, quality comparisons. HLE leaderboard.

### News & Releases
- **Anthropic Blog** — [anthropic.com/news](https://www.anthropic.com/news) — Claude releases, research, company updates.
- **OpenAI Blog** — [openai.com/index](https://openai.com/index/) — GPT releases, API changes.
- **Google AI Blog** — [blog.google/innovation-and-ai](https://blog.google/innovation-and-ai/) — Gemini releases, DeepMind research.
- **xAI Blog** — [x.ai](https://x.ai/) — Grok releases.
- **Hacker News** — [news.ycombinator.com](https://news.ycombinator.com/) — First place most AI releases get discussed. Good for sentiment.

## Tier 2: Check Weekly

### Research & Analysis
- **arxiv (cs.AI, cs.CL, cs.LG)** — [arxiv.org/list/cs.AI/recent](https://arxiv.org/list/cs.AI/recent) — Pre-prints. Leading indicator of model capabilities.
- **Epoch AI** — [epoch.ai](https://epoch.ai/) — Compute trends, training cost analysis, inference pricing data.
- **a16z AI research** — [a16z.com](https://a16z.com/) — Industry analysis, LLMflation tracking.
- **LMSYS Blog** — [lmsys.org/blog](https://lmsys.org/blog/) — Arena methodology changes, new features.
- **ARC Prize** — [arcprize.org](https://arcprize.org/) — ARC-AGI benchmark updates.

### Industry Tracking
- **VentureBeat AI** — [venturebeat.com/category/ai](https://venturebeat.com/category/ai/) — Enterprise AI coverage.
- **TechCrunch AI** — [techcrunch.com/category/artificial-intelligence](https://techcrunch.com/category/artificial-intelligence/) — Funding rounds, company news.
- **The Information** — [theinformation.com](https://theinformation.com/) — Insider scoops (paywall but high signal).
- **Interconnects** — [interconnects.ai](https://www.interconnects.ai/) — Nathan Lambert's analysis of model releases, open-source trends.

### Open Source Tracking
- **Hugging Face** — [huggingface.co/models](https://huggingface.co/models) — Open model releases, trending models.
- **DeepSeek Blog** — [deepseek.com](https://www.deepseek.com/) — DeepSeek releases.
- **Qwen Blog** — [qwenlm.github.io](https://qwenlm.github.io/) — Alibaba/Qwen model releases.
- **MiniMax** — [minimax.io/news](https://www.minimax.io/news) — MiniMax model releases.

## Tier 3: Check Monthly / Event-Driven

### Conferences & Events
- **NVIDIA GTC** — March 16-19, 2026. Infrastructure, chip announcements.
- **Google I/O** — May 19-20, 2026. Gemini updates, major AI announcements.
- **Apple WWDC** — June 2026. AI integration across Apple platforms.
- **NeurIPS, ICML, ICLR** — Academic conferences. Research previews.
- **LlamaCon** — TBD 2026. Meta's Llama conference.

### Regulatory
- **EU AI Act tracker** — [artificialintelligenceact.eu](https://artificialintelligenceact.eu/) — Enforcement timeline.
- **AI Policy Newsletter** — Various. Track US state/federal regulation.

### Financial
- **Statista AI** — [statista.com/outlook/tmo/artificial-intelligence](https://www.statista.com/outlook/tmo/artificial-intelligence/) — Market size forecasts.
- **Company earnings calls** — Alphabet, Meta, Microsoft for AI capex/revenue signals.

## Polymarket-Specific

### Resolution Sources
- **"Best AI model" markets** → Arena.ai Text tab, style control OFF, highest Arena Score
- **"Released by" markets** → Public availability of named model (API or consumer product)
- **Check resolution criteria on EACH market** — they differ subtly

### API Endpoints
```bash
# Search AI markets
curl -s "https://gamma-api.polymarket.com/events?limit=100&active=true&tag=ai"

# Specific event by slug
curl -s "https://gamma-api.polymarket.com/events?slug=which-company-has-the-best-ai-model-end-of-march-751"
```

## Signal Sources for Edge

| Signal | Source | Edge Type |
|--------|--------|----------|
| New model on Arena leaderboard | arena.ai | Minutes-to-hours before Polymarket reacts |
| arxiv pre-print with benchmark claims | arxiv.org | Days before mainstream coverage |
| Model API appearing in cloud console | Vertex AI, Bedrock, Azure | Hours-to-days before official announcement |
| Hiring patterns at AI labs | LinkedIn, company pages | Weeks-to-months leading indicator |
| Compute infrastructure announcements | GTC, company blogs | Months-ahead signal for model capabilities |
| Benchmark methodology changes | LMSYS blog | Can shift resolution criteria interpretation |
