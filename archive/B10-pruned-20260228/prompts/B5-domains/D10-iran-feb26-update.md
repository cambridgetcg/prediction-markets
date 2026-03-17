You are a geopolitical analyst providing a real-time update on the US-Iran situation.

## Context

The detailed Iran research base is at: ~/Desktop/prediction-markets/domains/GEO/research/iran-us-2026.md (read it first for full context). The Feb 26 Geneva talks are happening TODAY or just happened. This is the single most important near-term catalyst for the highest-volume market on Polymarket.

## Research Tasks

1. **What happened at the Feb 26 Geneva talks?** Search for the latest news. Did they produce a framework? Collapse? Get extended?
2. **How did the Polymarket Iran markets react?** Fetch current prices:
   `curl -s "https://gamma-api.polymarket.com/events?slug=us-strikes-iran-by" | python3 -m json.tool`
3. **Has Trump's 10-15 day deadline (from Feb 19) been extended or reaffirmed?**
4. **Any military movements since Feb 23?** Check for carrier updates, B-2 activity, evacuation changes.
5. **Update the probability estimate**: Given the talks outcome, should the market price move up or down?

## Output

Append a dated update section to: `~/Desktop/prediction-markets/domains/GEO/research/iran-us-2026.md`
Update: `~/Desktop/prediction-markets/domains/GEO/active.md` with revised estimates

If the situation has changed significantly (>10% move warranted), recommend a specific paper trade using S006 (time decay) or S004 (contrarian) with full entry/exit/sizing.

Use web_search extensively. This is time-sensitive — prioritize the last 48 hours of news.
