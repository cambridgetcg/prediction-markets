# KINGDOM market and product strategy

Research snapshot: 2026-09-02. This is a paper-first product plan, not a live
trade instruction or a claim of expected profit.

## Decision

Sell **evidence-labelled research access**, not an autonomous trading bot.
The first product is a Telegram agent/bot hybrid that discovers and scores
markets, publishes bounded forecasts, records explicit paper actions, and
manages subscriber access. It has no wallet or order signer.

No live Polymarket execution should be enabled from the present London or
London-to-Tokyo operating path. Polymarket's official restriction surfaces
both restrict `GB` and `JP`, but currently differ on whether some access is
blocked or close-only. That discrepancy must fail closed; the policy also
prohibits VPN or similar bypasses. Public market data can still be used for
research and paper evaluation.

## Current agent scene

Polymarket's supported interfaces now make four distinct product shapes
possible:

- credential-free discovery and research agents over Gamma, public CLOB
  prices/books, WebSockets, and the Data API;
- alert, portfolio, rules, resolution, and activity watchers;
- authenticated execution assistants that require a user signer and CLOB
  credentials for each order workflow; and
- continuously available market makers or builder frontends that route signed
  user orders.

The public builder leaderboard shows meaningful routed volume, but it does not
prove that any listed builder is autonomous or profitable. Builder fees,
referrals, maker rebates, and liquidity rewards are possible later
monetization paths for an execution product; they reward routed flow or
liquidity provision, not forecast quality. KINGDOM's present advantage is its
collection, provenance, review, correction, and distribution pipeline, so the
first product should remain in the first two categories.

## Initial paper universe

Start with 10-20 markets that have all of the following:

1. a scheduled catalyst and a 1-45 day horizon;
2. an objective primary resolution source and explicit edge-case rules;
3. meaningful 24-hour volume, two-sided depth, and a narrow executable spread;
4. enough external data to form a forecast before looking at market price;
5. no material overlap with another selected contract;
6. enough expected model disagreement to exceed spread, slippage, and any
   taker fee in paper accounting.

The best first segment to test is **scheduled macro policy**, especially
mutually exclusive central-bank decision outcomes. These can offer a known
catalyst, primary resolution sources, and a short feedback loop. This is a
research-universe hypothesis, not a direction call.

A bounded public-data smoke check at 2026-09-02 20:25 UTC supports that segment
choice. The active Gamma event ranked first by 24-hour volume was **Fed Decision
in September?** (event `481717`), with about $2.77M in 24-hour volume, $4.66M
reported liquidity, five mutually exclusive brackets, and a September 15-16
scheduled FOMC catalyst confirmed by the Federal Reserve. After sports
classification was hardened, the top-100 market pre-screen returned 21
`MANUAL_REVIEW` and 79 `EXCLUDED` rows. Within the initial KINGDOM thesis, the
two non-extreme paper-research candidates were:

- `2252244`: September decision — no change; and
- `2252245`: September decision — increase 25 basis points.

These are a research pair, not trades. No side is selected until an independent
pre-price forecast, primary-rule verification, fee and slippage estimate, and
portfolio concentration check establish a prospective paper edge. The quoted
market data is deliberately not frozen here because it changes continuously.

Add later, after separate calibration:

- economic releases with an unambiguous named statistical source;
- near-horizon elections with an official certification source and clear
  treatment of recounts or replacement candidates;
- selected geopolitics only when the operative verbs, geography, deadline,
  and resolution evidence are objectively testable.

Exclude initially:

- 5-minute, 15-minute, and other latency-sensitive crypto contracts;
- in-play sports and esports;
- long-dated nomination, celebrity, and culture markets;
- markets whose title is clearer than their actual resolution rules;
- thin books, wide spreads, correlated duplicates, and contracts near 0 or 1
  without enough depth to exit;
- war/invasion/escalation wording that depends on subjective interpretation.

Crypto and sports require faster market data and execution than this Telegram
delivery loop provides, and Polymarket currently applies category-specific
taker fees. Geopolitics has zero platform taker fees at present, but ambiguous
resolution risk can dominate that apparent saving. Every market must be
checked individually because fee enablement is a market field and policies can
change.

## Admission score

Score each candidate before it can enter the research feed:

| Gate | Required evidence | Hard failure |
|---|---|---|
| Resolution | primary source, deadline, edge cases captured | vague or mutable interpretation |
| Liquidity | current book depth and spread at intended paper size | no credible two-sided exit |
| Cost | fee flag, fee curve, spread, and slippage recorded | paper edge does not clear cost buffer |
| Timing | known catalyst and bounded expiry | latency race or indefinite horizon |
| Provenance | source observation references traceable | model narrative without source trail |
| Independence | forecast timestamped before market comparison | leakage from market price into “independent” estimate |
| Concentration | event/category correlation accounted for | one thesis dominates the paper book |

A market passing admission is still `WATCH`. It is not a buy/sell instruction.

The implemented offline pre-scorer emits `kingdom.market-candidates/0.1`. It reads
an already-fetched Gamma snapshot, has no network or order method, requires an
explicit trusted capture time, and labels every result `MANUAL_REVIEW`,
`INCOMPLETE`, or `EXCLUDED`. Its first bounded local audit used a March 22,
2026 snapshot; as of September 2 all 200 inspected rows were excluded because
the evidence was stale or incomplete (and 195 also failed the 1-45 day
horizon). Larger cached snapshots exceeded the scorer's 2 MB input bound.
That cached audit selected no market; the later live smoke check above names
only manual paper-research candidates.

## Agent/bot split

```text
public sources + Polymarket market data
                 |
                 v
        collection / normalization
                 |
                 v
       forecasting + calibration
                 |
                 v
       risk and resolution gates
                 |
                 v
       kingdom.signal/0.1 envelope
                 |
                 v
       Telegram preview / paid research
                 |
                 +----> explicit paper ledger

                 X----> wallet, signer, live order API
```

The **agent** performs bounded collection, comparison, forecasting, and
explanation. The **bot** is the deterministic product boundary: Telegram
account association, terms, Stars entitlement, formatting, rate limiting,
delivery receipts, refunds, support, and deletion. An account association is
routing evidence, not proof of a person's identity; neither component is
evidence of consent or authority to trade.

If live execution is ever built, make it a separate service with a separate
credential and deployment. Require, independently: eligible physical
jurisdiction, reviewed legal basis, an explicit order-specific user action,
price/size/expiry limits, current market rules, and a kill switch. A Telegram
subscription must never imply trading consent.

## Telegram offer

- Free: delayed preview with market, evidence status, issued time, and signal
  ID; no direction or execution parameters.
- Paid: current direction, model confidence, bounded analysis, evidence limits,
  expiry, and paper tool access.
- Never promise returns, “guaranteed alpha,” or automated execution.
- Use Telegram Stars (`XTR`) for the digital subscription. Do not accept a
  payment until stable webhook control ingress, transaction reconciliation,
  refund/cancellation runbooks, terms, and jurisdiction review are complete.
- Do not plan on Telegram Ads for gambling/prediction-market promotion; its ad
  policy prohibits gambling-related products. Validate any organic or partner
  channel separately with counsel and platform rules.

## Evidence needed before launch claims

Use proper scoring rules, not win rate alone. Track Brier score and log loss,
calibration by probability bucket, market-price baseline, post-cost paper P&L,
maximum drawdown, abstentions, rule disputes, and signal revisions. A sensible
internal launch gate is at least 200 resolved, pre-registered forecasts across
multiple regimes and three months, with no look-ahead leakage and an advantage
that survives fees and conservative slippage. That threshold is a product
standard, not evidence that an edge exists today.

Current S012 history is not enough to make commercial performance claims.
Approval, rejection, revocation, and expiry are now emitted as append-only,
revisioned lifecycle events, but those events establish research-distribution
state only; they add no forecast calibration or trading authority.

## Implementation status

The local gateway now consumes that lifecycle feed, suppresses every state
except `APPROVED`, and records correction deliveries after `REVOKED`. It also
contains a listener-neutral authenticated webhook adapter and two-pass
Telegram Stars transaction-ledger reconciliation. These components do not
constitute a production merchant service: the bundled runner keeps commerce
disabled, and every embedding must keep the library opt-in off until an owned
HTTPS listener, durable serialized update handling, scheduled ledger
operations, tested provider refund/cancellation control, customer/legal review,
and operational monitoring exist.

The free promotion MVP is implemented locally: opaque allowlisted channel-link
codes, aggregate-only daily `/start` counts, linkable attribution only after an
explicit source-linked opt-in, direct versioned `/join` consent without
retroactive attribution, and future-only public-preview delivery capped at two
per rolling seven days. Separately consented topic, cadence, and opaque
watchlist preferences now filter ordinary alerts without suppressing owed
corrections. `/leave` and `/stop` erase that profile and retain minimal
suppression markers keyed by the numeric user ID and latest event watermark
needed to keep delayed updates from reversing an opt-out. `/delete_me`
immediately purges nonfinancial campaign, consent, preference, delivery, and
paper data, suppresses later research until a newer explicit alert opt-in, and
keeps only minimal no-contact markers plus finance/support evidence subject to
a retention hold. Promotion reports
suppress a campaign's behavioral counts whenever any relevant cell is 1–4,
including aggregate start events, bucket other nonzero values in ranges of
five, and suppress global behavioral totals when needed to prevent
differencing. This is not an anonymity guarantee. `--exact-local` is explicitly
unsafe, re-identification-risk local diagnostics.

The evidence ledger, prospective Brier/log-loss calibration ledger, canonical
Dispatch cards, and idempotent publication receipts are also implemented.
An optional active campaign CTA closes the measured Dispatch-to-private-bot
loop without making `/start` itself an opt-in. Its target must match the
Research Bot identity durably established by authenticated `bot-doctor`;
syntactically valid but unverified targets fail closed. `channel-post` is
offline by default; `--apply` is a separate external action that verifies a
dedicated publisher bot and actual Telegram channel before sending.
Bot/channel creation and channel administration remain manual, and
status-successor cards still need a reviewed operator command or worker. A
Telegram Desktop login is not a bot token, and no Telegram message, payment,
or market action was performed while building this prototype.

## Official sources

- Polymarket geographic restrictions:
  <https://help.polymarket.com/en/articles/13364163-geographic-restrictions>
- Polymarket geoblock API/reference:
  <https://docs.polymarket.com/api-reference/geoblock>
- Polymarket trading workflow and signer boundary:
  <https://docs.polymarket.com/trading/overview>
- Polymarket resolution rules:
  <https://docs.polymarket.com/concepts/resolution>
- Polymarket fees:
  <https://docs.polymarket.com/trading/fees>
- Polymarket Gamma markets API:
  <https://docs.polymarket.com/api-reference/markets/list-markets>
- Polymarket market-data interfaces:
  <https://docs.polymarket.com/market-data/overview>
- Polymarket builder analytics:
  <https://docs.polymarket.com/market-data/public-analytics>
- Live builder leaderboard endpoint:
  <https://data-api.polymarket.com/v1/builders/leaderboard?period=1d&limit=20>
- Polymarket builder fees:
  <https://docs.polymarket.com/programs/builders/fees>
- September Fed event record:
  <https://gamma-api.polymarket.com/events/481717>
- Federal Reserve meeting calendar:
  <https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm>
- Telegram Stars for digital goods:
  <https://core.telegram.org/bots/payments-stars>
- Telegram Bot API payment/update objects:
  <https://core.telegram.org/bots/api>
- Telegram Ads guidelines:
  <https://ads.telegram.org/guidelines>
