You are a prediction market researcher focused on the 2026 State of the Union address as a catalyst event.

## Context

The 2026 State of the Union address is happening around March 4, 2026. Multiple Polymarket markets resolve based on what Trump says. This is a classic S003 (Catalyst) opportunity — binary, short-dated, known event time.

## Why This is High Value

1. **Fast calibration**: These markets resolve within 24h of the speech. First real test of calibration outside of long-duration positions.
2. **Known event structure**: The SOTU follows predictable patterns — Trump's rhetorical habits, likely topics, historical speech analysis
3. **Low sophistication**: Retail traders guessing vs. anyone with Trump speech analysis and topic knowledge
4. **High volume**: $1M+ 24h volume = ample liquidity
5. **Multiple independent bets**: 20+ word/topic markets = diversification within a single event

## Research Tasks

### 1. Fetch Current SOTU Markets

```bash
curl -s "https://gamma-api.polymarket.com/events?q=state+of+the+union&limit=10" | python3 -m json.tool
```

Also check: `https://gamma-api.polymarket.com/events?q=trump+say&limit=20`

For each market, record:
- The specific word/phrase
- Current YES price
- Liquidity and 24h volume
- Resolution criteria (exact rules for counting?)

### 2. Research Trump's Speech Patterns

Use web search to find:
- **Past SOTU transcripts (2017, 2018, 2019, 2020, 2025)** — what words does Trump use repeatedly?
- **Wordcloud analysis** — has anyone done frequency analysis of Trump SOTU speeches?
- **This year's likely topics**: Iran, tariffs, DOGE, the economy, immigration, the Venezuela operation
- **Draft leaks or advance excerpts**: Are any topics confirmed?
- **Speech length estimates**: Previous Trump SOTUs ranged from 60-90 minutes. Longer = more repetition.

Key mental model: Trump's rhetorical style:
- Repetition of key phrases ("beautiful", "the greatest", "we've done something")
- Specific boasts (stock market, jobs numbers, deregulation)
- Villain mentions (Democrats, China, media)
- Rally-style language even in formal settings
- "Many people are saying" — specific Trump rhetorical tic

### 3. Form Estimates for Each Market

For each Polymarket market, form your estimate BEFORE recording market price.

Categories to analyze:
- **Geography markets** ("Will Trump say [country name]?"): Iran? Ukraine? Venezuela? China? Canada?
- **People markets** ("Will Trump say [person]?"): Musk? Zelensky? Khamenei? Pelosi?
- **Topic markets** ("Will Trump say [word] N+ times?"): "America", "great", "job", "tariff", "China", "border"
- **Nickname markets** ("Will Trump say [nickname]?"): These are the most mispriced — retail bids up impossible nicknames

Key heuristics:
- Any country Trump has TAKEN ACTION on in the last year → almost certain to mention (Venezuela, Iran, Canada, China)
- Any country Trump is CURRENTLY negotiating with → very likely
- Market prices for "Trump says [country]" should be 80%+ if he's been publicly vocal about it
- Nickname markets are often 0.5-5% on retail speculation — fades are typically correct

### 4. Identify the Best 3-5 Trades

Criteria:
- Edge ≥ 10pp (my estimate vs market)
- Liquidity ≥ $10K (enough to enter/exit at reasonable prices)
- Clear resolution criteria
- Prefer YES if it's a "Trump definitely says this" play — 80%+ payoff with near-certainty
- Prefer NO if it's a meme/improbable nickname that retail is overpricing

### 5. Calculate Sizing

Per bankroll rules:
- Phase 1: $250 total across SOTU batch
- Max $100 per position (10% of $1,000 Phase 1 implied, but using $125 cap from before)
- If multiple high-confidence YES plays (>80% estimate), concentrate — fewer, larger positions
- If hedging across many NO plays (5-10% each), spread thin ($25-50 each)

The "Iran" mention market deserves special attention:
- Trump is actively negotiating a deal/preparing for strikes
- The chances he doesn't mention Iran in the SOTU are near zero
- If the market prices "Trump mentions Iran" at anything < 70%, it's a strong YES buy

### 6. Execute Paper Trades

For each trade:
1. Log to `calibration/predictions.jsonl`
2. Log to `strategies/paper-trades/trades.jsonl`
3. Update `strategies/paper-trades/positions.json`

### 7. Post-SOTU Protocol

Create a reminder: the day AFTER the speech (around March 5), run through each prediction and:
- Mark resolved YES/NO
- Calculate Brier score for each
- Update `calibration/resolutions.jsonl`
- Write lessons to `calibration/lessons.md`

This batch will be the FIRST real calibration data (fast-resolving vs the 30-180 day positions).

## Output

Trade entries in their respective JSONL files.
Write summary to: `~/Desktop/prediction-markets/strategies/paper-trades/trade-report-sotu-2026.md`

Include: which markets, my estimates vs market, edge calculation, sizing rationale, key risks (e.g., what if Trump gets sick and cancels?).
