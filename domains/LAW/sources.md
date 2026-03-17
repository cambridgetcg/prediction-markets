# LAW — Sources

*Best sources for tracking legal/regulatory developments relevant to prediction markets.*

## Tier 1: Check Daily/Weekly

### Courts
- **SCOTUSblog** — [scotusblog.com](https://www.scotusblog.com/) — THE source for Supreme Court tracking. Case pages, oral argument analysis, opinion announcements.
- **PACER/RECAP** — [courtlistener.com](https://www.courtlistener.com/) — Federal court filings. Free via RECAP browser extension.
- **Supreme Court Calendar** — [supremecourt.gov/oral_arguments](https://www.supremecourt.gov/oral_arguments/argument_calendars.aspx) — Official argument schedule.
- **Ballotpedia SCOTUS** — [ballotpedia.org](https://ballotpedia.org/Supreme_Court_cases,_October_term_2025-2026) — Case tracking with plain-language summaries.

### Regulatory Agencies
- **CFTC** — [cftc.gov/PressRoom](https://www.cftc.gov/PressRoom/PressReleases) — Prediction market rulemaking, enforcement actions.
- **SEC** — [sec.gov/newsroom](https://www.sec.gov/newsroom) — Crypto enforcement, ETF decisions, policy statements.
- **Federal Register** — [federalregister.gov](https://www.federalregister.gov/) — Proposed rules, final rules, executive orders.
- **Congress.gov** — [congress.gov](https://www.congress.gov/) — Bill tracking (BITCOIN Act, market structure, AI bills).

### News & Analysis
- **CoinDesk Policy** — [coindesk.com/policy](https://www.coindesk.com/policy/) — Crypto regulation coverage.
- **The Block** — [theblock.co](https://www.theblock.co/) — Institutional crypto/DeFi regulation.
- **National Law Review** — [natlawreview.com](https://natlawreview.com/) — Legal analysis of regulatory developments.
- **Law360** — [law360.com](https://www.law360.com/) — Comprehensive legal news (paywall).

## Tier 2: Check Weekly/Biweekly

### Legal Analysis (Law Firms)
- **Sidley Austin** — Excellent on CFTC/prediction market regulation
- **Gibson Dunn** — Crypto regulation guides
- **Paul Hastings** — Crypto policy tracker
- **Skadden** — MiCA and EU AI Act analysis
- **King & Spalding** — State AI law tracking
- **Wilson Sonsini** — DOJ/FTC antitrust priorities
- **Holland & Knight** — Prediction markets at a crossroads analysis

### Think Tanks & Research
- **Brookings** — [brookings.edu](https://www.brookings.edu/) — Tracking regulatory changes in Trump admin.
- **Cato Institute** — DOGE and deregulation analysis
- **Transparency Coalition AI** — [transparencycoalition.ai](https://www.transparencycoalition.ai/) — AI legislative updates

### International
- **EU AI Act Service Desk** — [ai-act-service-desk.ec.europa.eu](https://ai-act-service-desk.ec.europa.eu/) — Official implementation timeline.
- **ESMA (MiCA)** — [esma.europa.eu](https://www.esma.europa.eu/esmas-activities/digital-finance-and-innovation/markets-crypto-assets-regulation-mica) — MiCA enforcement.
- **FCA (UK)** — [fca.org.uk](https://www.fca.org.uk/firms/new-regime-cryptoasset-regulation) — UK crypto regime.

## Tier 3: Event-Driven

### Conferences & Events
- **SCOTUS oral arguments**: Published calendar. Key dates in April-May.
- **Congressional committee markups**: Senate Banking, Senate Agriculture for crypto bills.
- **CFTC open meetings**: Rulemaking announcements.
- **EU implementation deadlines**: MiCA (Jul 1), AI Act (Aug 2).

## Polymarket-Specific

### API Searches for Legal Markets
```bash
# Search for legal/regulatory markets
for slug in "scotus" "supreme-court" "antitrust" "bitcoin-act" "stablecoin" "genius-act" "crypto-executive" "ai-bill" "google-breakup" "prediction-market"; do
  curl -s "https://gamma-api.polymarket.com/markets?limit=10&active=true&closed=false&slug_contains=$slug"
done
```

## Signal Sources for Edge

| Signal | Source | Edge Type |
|--------|--------|----------|
| SCOTUS oral argument transcript | supremecourt.gov | Hours — predict ruling direction from questioning |
| Court filing on PACER | courtlistener.com | Hours-to-days before mainstream coverage |
| CFTC/SEC rulemaking notice | Federal Register | Days before market reaction |
| Law firm analysis of new regulation | Am Law 200 blogs | Days — legal interpretation edge |
| Congressional committee vote schedule | congress.gov | Days — predict bill passage |
| EU implementation guidance | ESMA, AI Act Service Desk | Weeks — enforcement approach signals |
| State AG enforcement actions | State AG websites | Days — state-level regulatory shifts |
