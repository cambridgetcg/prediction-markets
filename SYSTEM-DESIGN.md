# Prediction Markets Observatory — System Design

## Present Truth

The observatory is dormant, read-only, and paper-only as of 2 September 2026.
`NO-LIVE-TRADING` is present. No part of this design authorizes an account,
wallet, order, stake, or attempt to evade a geographic restriction.

The purpose is modest: test whether an independently formed probability adds
information after real execution costs and resolution risk are counted.

## One Owner for Each Kind of Record

| Home | Owns | Does not own |
| --- | --- | --- |
| Oracle | Evidence, independent forecasts, revisions, and forecast calibration | Prediction-market prices, orders, or venue eligibility |
| Prediction Markets Observatory | Venue rules, permitted quotes, question matching, paper comparisons, and paper evaluation | Oracle's evidence or original forecast |
| KINGDOM OS | Source-owned declarations and declared relationships | Operation, scheduling, consent, or trading authority |
| Castle | Small, reviewed lessons that remain useful | Raw licensed feeds, credentials, orders, or mutable working state |

A live executor does not exist in this design. If one is ever proposed, it must
be a separately reviewed boundary rather than a hidden extension of Oracle or
this observatory.

## The Order of Work

### 1. Decide whether observation is permitted

Before any automated fetch, record a decision for the exact source, use, person
or entity, and location:

- jurisdiction: `allowed`, `denied`, or `unknown`;
- data rights: allowed uses such as manual reading, API collection, storage,
  derived analysis, publication, and commercial use;
- authority: the official rule or agreement, its version or date, URL, review
  time, and next review time.

`config/market-data-access.json` is the checked-in gate for the adapters that
exist today. Code treats an absent, incomplete, expired, denied, or unknown
record as a stop and makes no venue request.

`Denied` and `unknown` both stop the adapter. A venue's technical availability
does not override local law or its data terms. No proxy, VPN, alternate domain,
or other bypass is part of this system.

Current Swiss posture:

| Source | Current boundary |
| --- | --- |
| Polymarket | Execution off: `polymarket.com` is on Gespa's blocklist. Automated data use is also off until its lawful and licensed scope is recorded. |
| Kalshi | Execution off: Switzerland is restricted by its Member Agreement and `kalshi.com` is on Gespa's blocklist. Automated or AI data use is off without written permission. |
| ForecastEx through IBKR | Execution off: Swiss product eligibility and legal classification have not been affirmatively established. |
| Manifold and Metaculus | Signal research only, within their documented non-commercial/API scope or separate written permission. They are not execution venues for this design. |

This posture is an operational stop, not legal advice. Its main official bases
are [Gespa's prediction-market notice](https://www.gespa.ch/en/news), the
[current Gespa blocklist](https://blocklist.gespa.ch/gespa_blocklist.pdf),
Kalshi's [Member Agreement](https://kalshi.com/docs/kalshi-member-agreement.pdf)
and [Data Terms](https://kalshi-public-docs.s3.amazonaws.com/kalshi-data-terms-of-service.pdf),
the [ForecastEx rulebook](https://data.forecastex.com/regulatory/ForecastEx_LLC_Rulebook.pdf),
and the official [Manifold](https://docs.manifold.markets/data) and
[Metaculus](https://www.metaculus.com/api/) data pages. Recheck the live source;
never treat this dated summary as permanent permission.

### 2. Seal a market-blind forecast

The question and its exact outcome rules may be passed to Oracle without any
price, order book, implied probability, community forecast, or commentary that
reveals consensus. Oracle returns the immutable ForecastEnvelope defined in its
`FORECAST-CONTRACT.md`.

The envelope is sealed before prices are opened. If the forecaster saw a price
or consensus first, say so. That forecast may remain in the record, but it is
not evidence of market-blind edge.

### 3. Capture the market as it really was

Only after the forecast is sealed may a permitted adapter create a market
snapshot. The snapshot records:

- venue, contract identifier, outcomes, close and settlement times with time
  zones;
- the complete resolution rules, named source, fallbacks, ambiguity or void
  treatment, every later clarification, and a digest of the exact captured
  bytes;
- source URL or endpoint, source timestamp, observation time, release or data
  vintage, and raw-record digest;
- executable best bid and ask on each side, available size and relevant depth;
- fee schedule and vintage, spread, expected slippage, currency conversion,
  chain or custody cost where applicable, and cost of locked capital.

A displayed probability or midpoint is context, not an executable price.
Missing size, stale quotes, missing fees, or unavailable rules stop the
comparison.

### 4. Prove that the questions match

Matching names are not enough. Compare the exact outcomes, definitions,
deadline and time zone, resolution source, fallback, cancellation, ambiguity,
and amendment powers.

The result is `compatible`, `incompatible`, or `unknown`, with reasons and the
digests of both rule sets. Only `compatible` questions enter paper comparison.
Neither `unknown` nor a later rules change may be guessed away.

### 5. Compare on paper after all costs

For a binary contract paying one unit:

- paper YES edge = independent YES probability minus all-in executable YES ask;
- paper NO edge = independent NO probability minus all-in executable NO ask.

All-in cost includes every observed fee and conservative allowance above. Use
the quote and size available at the recorded time. Keep raw difference, each
cost, uncertainty allowance, and final paper difference separate. A positive
paper difference is a research hypothesis, not a recommendation or order.

### 6. Evaluate without rewriting history

Forecasts, snapshots, comparisons, revisions, resolutions, and corrections are
append-only. Each new record points to the exact earlier record and its digest.
Never replace an old probability with a later one.

At resolution, record provisional and final states separately, including the
official source, publication and observation times, vintage, exact rule version,
and digest. Ambiguous, annulled, void, disputed, or changed-rule cases remain
named as such; they are not forced into a win or loss.

Score the independent forecast with a proper score such as Brier or log score,
compare it with the same-time executable market snapshot, and keep hypothetical
profit and loss separate from calibration. A reviewed durable lesson may then
return to Castle without raw licensed data or private material.

## Progression Gates

There is no automatic progression between these stages.

1. **Dormant — current.** Read documentation and historical records only. The
   brake remains raised.
2. **Bounded read-only trial.** Requires an explicit invitation, a named source
   and scope, current `allowed` jurisdiction and data-rights records, a rate
   bound, a time bound, and a tested stop. It creates no order or account action.
3. **Paper evaluation.** Requires sealed ForecastEnvelopes, compatible exact
   rules, executable quote snapshots, complete costs, append-only records, and
   an evaluation period and sample size chosen before results are known.
4. **Possible future live review.** Paper results do not unlock this stage. It
   would require a written Swiss legal determination, venue eligibility and
   data rights, explicit current authority naming venue, strategy, capital and
   time bounds, and an independent review of a separate executor. That executor
   would need hard exposure and loss limits, stale-data rejection, duplicate
   prevention, reconciliation, an audit trail, manual approval, and a tested
   kill switch.

Both the source brake and every required approval must be deliberately cleared
in a separate recorded change. The absence or deletion of
`NO-LIVE-TRADING` alone means nothing.

## Stop Conditions

Stop and return to rest when law, eligibility, data rights, source provenance,
rules, quote freshness, executable cost, or authority is denied, missing,
changed, or uncertain. Also stop on confidential or stolen information,
influence over the outcome, manipulation, or any request to hide provenance.
