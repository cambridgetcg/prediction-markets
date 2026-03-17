You are a technology & AI prediction market researcher. The TEC domain is unseeded and Google I/O (May 19-20) is 12 weeks away — perfect lead time for S003 catalyst entries.

## Context

Read first:
1. ~/Desktop/prediction-markets/domains/TEC/context.md — TEC domain context and key players
2. ~/Desktop/prediction-markets/domains/TEC/active.md — current market analysis (Feb 23)
3. ~/Desktop/prediction-markets/domains/TEC/research/ — existing research (if any)
4. ~/Desktop/prediction-markets/strategies/evolution/strategy-domain-matrix.md — TEC strategy fit

## Time-Sensitive: Execute This Trade First

**T009: Anthropic Arena March 31 — YES at 64%**

This was already fully analysed in TEC/active.md (Feb 23) with 8-14pp edge identified but never traded.

1. Fetch current market price:
   `curl -s "https://gamma-api.polymarket.com/events?q=best+ai+model+march&limit=5"`
2. Check if price has moved since Feb 23 analysis
3. Fetch current Arena.ai leaderboard: https://lmarena.ai/?leaderboard
   - Is Claude Opus 4.6 still #1?
   - What Elo gap exists between Anthropic and Google?
   - Has any new model shipped to Arena in the last 48h?
4. If Anthropic still leads AND market is still ≤70% YES:
   - **Execute paper trade**: BUY Anthropic YES at current price
   - Size: $100 (1% bankroll, TEC first position)
   - Strategy: S001 (Hold to Resolution)
   - Log to calibration/predictions.jsonl and strategies/paper-trades/trades.jsonl
   - Resolution: March 31, 2026

**Risk check**: If any new model has shipped to Arena OR the Elo gap has closed to < 5 points → skip the trade. The thesis requires sustained Elo dominance.

---

## Research Task 1: Google I/O Catalyst Mapping (May 19-20)

Google I/O is the single largest AI catalyst between now and Q3 2026. Strategy: S003 (enter 3-7 days before the event, hold through announcement).

**What to research:**

1. **Confirmed announcements** (already leaked or officially teased):
   - Search for "Google I/O 2026 announcements" and "Google I/O 2026 AI"
   - What has Google confirmed? Product launches, Gemini 4, Android AI, etc.
   - Use: https://blog.google/technology/ai/ and recent Google press releases

2. **Historical I/O pattern**: What has Google typically announced at I/O?
   - AI model releases (Gemini versions, PaLM, Bard)
   - Product integrations (Search AI, Workspace, Android)
   - Developer tools (Vertex AI, TensorFlow, Colab)
   - Hardware (TPUs, Pixel, etc.)

3. **What Polymarket markets exist around I/O timing?**
   - Search: `curl -s "https://gamma-api.polymarket.com/events?q=google&limit=20"`
   - Search: `curl -s "https://gamma-api.polymarket.com/events?q=gemini&limit=10"`
   - Look for: Gemini release markets, best AI model by June/Q2, Google products
   - Note: markets resolving around May-June are the S003 targets

4. **The competitive landscape in May**:
   - OpenAI: GPT-6 targeting mid-2026. If it ships before I/O, context shifts
   - Anthropic: Claude Opus 5 timeline? Any hints of a pre-I/O release to counter Google?
   - What does "Gemini 3.5 Pro" or "Gemini 4" release at I/O do to the June Arena market?

**Output**: Create `~/Desktop/prediction-markets/domains/TEC/research/google-io-2026.md`

Structure:
- Confirmed I/O announcements (what we know)
- Historical pattern (what Google typically does)
- Prediction market opportunities (list specific markets + my estimates)
- Trading calendar: when to enter (May 12-16) and what to expect

---

## Research Task 2: AI Model Release Calendar

Build a forward calendar of model releases + their market impact:

| Date | Event | Market Impact | Opportunity |
|------|-------|---------------|-------------|
| Feb 28 | Arena Feb leaderboard locks | End of Feb market | No edge (too close) |
| Mar 31 | Arena Mar leaderboard locks | End of March market | T009 — Anthropic YES |
| ~Apr 2026 | GPT-5.3 or GPT-6? | "Best model" markets | Monitor |
| May 19-20 | Google I/O | Gemini release | S003 entry |
| Jun 30 | Arena Jun leaderboard locks | Q2 market | Depends on I/O |

Research:
1. OpenAI release schedule: search "OpenAI GPT-6 release date 2026" + "OpenAI roadmap"
2. xAI Grok 5 timeline: search "Grok 5 release date" + "xAI compute timeline"
3. DeepSeek R2: search "DeepSeek R2 release 2026"
4. Is there a pre-announced "major model" from anyone before March 31?

**Output**: Add a "Release Calendar" section to `~/Desktop/prediction-markets/domains/TEC/active.md`

---

## Research Task 3: Other TEC Opportunities

Scan current TEC-adjacent Polymarket markets for opportunities we've missed:

```bash
curl -s "https://gamma-api.polymarket.com/events?q=ai+model&limit=10"
curl -s "https://gamma-api.polymarket.com/events?q=openai&limit=10"
curl -s "https://gamma-api.polymarket.com/events?q=anthropic&limit=5"
curl -s "https://gamma-api.polymarket.com/events?q=elon+musk&limit=10"
```

For each market found:
- Is it in our strategy-domain matrix's "sweet spot" for TEC? (S001★, S003★★, S008★)
- Do we have an information edge?
- Is there a catalyst we can identify?

**Prioritize**:
- Short-to-medium duration (< 6 months)
- S003 catalyst plays over S001 long holds
- Markets where tech literacy creates information asymmetry vs. retail traders

---

## Output

1. **T009 trade executed** (or clearly flagged as skipped with reason)
2. `~/Desktop/prediction-markets/domains/TEC/research/google-io-2026.md` — I/O catalyst research
3. Updated `~/Desktop/prediction-markets/domains/TEC/active.md` — release calendar + any new markets found
4. Updated `~/Desktop/prediction-markets/domains/TEC/sources.md` — add any new TEC sources found
5. Brief terminal summary: what TEC trades are live, what's on the catalyst calendar

**Budget**: $100 for T009 only. No other TEC trades without documenting the thesis in active.md first.
