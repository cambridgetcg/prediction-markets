# KINGDOM Telegram bot privacy policy — publication template

Status: **not ready for publication**. Replace every bracketed field, choose a
retention schedule with appropriate legal review, publish at a stable public
HTTPS URL, and register that URL in BotFather before promoting the bot.

Effective date: [YYYY-MM-DD]

Operator: [LEGAL OR PUBLIC OPERATOR NAME]

Contact: [PRIVACY CONTACT]

## What this bot does

KINGDOM distributes evidence-labelled prediction-market research and optional
paper-only forecasts in private Telegram chats. It does not place trades, hold
funds or wallet keys, determine whether a venue is lawful for a user, or
guarantee returns.

## Data processed

Telegram supplies the bot with update data needed to respond to a person. The
local KINGDOM gateway may retain:

- numeric Telegram user and private-chat identifiers;
- explicit alert opt-in/opt-out events, current consent state, and the minimum
  event watermark needed to prevent delayed updates from reversing a choice;
- a source campaign code linked to the numeric user identifier only after an
  explicit source-linked alert opt-in, plus non-linkable daily campaign-start
  aggregates;
- terms/privacy-notice timestamps, delivery and correction receipts, rate-limit
  state, explicit paper-simulation actions, and support-case state;
- only after a separate `/personalize` action, allowlisted topic codes, a
  requested delivery cadence, and bounded opaque market references associated
  with the numeric Telegram identifier; and
- if paid access is later enabled, the minimum Telegram Stars invoice,
  subscription, charge, refund, and reconciliation evidence needed to provide
  access and handle support. The bundled development runner keeps paid commerce
  disabled.

The gateway does not intentionally retain Telegram usernames, profile names,
ordinary message bodies, wallet credentials, or inferred personal traits.
Telegram independently processes messages and account data under Telegram's
own terms and policies.

## Purposes and choices

The data is used to answer commands, enforce explicit alert and personalization
choices, filter ordinary research by chosen topics, cadence, or saved market
references, deliver approved research and owed corrections, prevent duplicate
processing, measure privacy-filtered promotion performance, protect the
service from abuse, and—only if commerce is separately enabled—administer
access and payments.

`/join` enables limited alerts. `/personalize` separately creates the minimal
preference profile described above. `/leave` or `/stop` disables new research
alerts and erases that profile. `/privacy` shows an in-chat summary.
`/delete_me` requests deletion of linkable nonfinancial activity and prevents
later research contact until a newer explicit opt-in.

## Retention and deletion

On `/delete_me`, the current gateway immediately purges campaign attribution,
alert-consent history, personalization topics/cadence/watchlist, delivery and
correction receipts, paper actions, rate-limit state, and closed support
records associated with that numeric Telegram user identifier. It retains
minimal numeric-ID no-contact markers and event watermarks so older Telegram
updates cannot recreate consent or preferences. Finance or open support
evidence may be retained while a legitimate retention obligation or active
request applies.

Production retention periods: [DEFINE EACH RETAINED DATA CATEGORY AND PERIOD].
SQLite write-ahead-log history, filesystem snapshots, backups, and storage
remnants may take additional time to expire under: [DEFINE BACKUP/COMPACTION
SCHEDULE].

## Sharing, security, and rights

Local gateway data is kept in owner-only storage. It is not sold. Data is
shared only with [LIST PROCESSORS, HOSTS, MODEL PROVIDERS, ANALYTICS PROVIDERS,
AND LEGALLY REQUIRED DISCLOSURES]. Do not claim that no third party receives
data if messages or identifiers are sent to a hosting, model, logging, or
analytics provider.

To request access, correction, deletion, restriction, or another applicable
privacy right, contact [PRIVACY CONTACT]. State the relevant jurisdictions,
lawful basis, complaint route, age rules, international transfers, and
controller/processor roles here after review: [REQUIRED LOCAL TERMS].

This template documents the current software boundary; it is not legal advice
and does not establish that a deployment complies with every applicable law.
