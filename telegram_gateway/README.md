# KINGDOM Telegram research gateway

Local, information-only pipeline for distributing evidence-labelled
prediction-market research through Telegram. The implemented path is an
auditable development prototype: the bundled runner keeps Stars commerce
disabled, library commerce requires a separate explicit opt-in in addition to
a price, and the package has no wallet or live-order capability.

## Implemented boundary

The gateway currently:

- incrementally imports append-only S012 signal JSONL and seals each signal in
  a `kingdom.signal/0.1` envelope;
- imports the separate `s012.signal-lifecycle/0.1` feed and distributes a
  signal only while its effective state is `APPROVED`;
- validates revisioned `PENDING -> APPROVED | REJECTED | EXPIRED` and
  `APPROVED -> REVOKED | EXPIRED` transitions without rewriting the sealed
  signal envelope;
- quarantines orphaned, conflicting, or out-of-order lifecycle events and
  retries a retained event when its missing signal or prior revision arrives;
- sends a correction notice to every unblocked, unsuppressed recipient whose
  original delivery was recorded as `sent` or `unknown` when an approved
  signal is later `REVOKED`;
- gives free users a preview and entitled users a bounded research view, and
  records explicit simulated paper actions;
- records bounded, already-fetched source artifacts as immutable,
  content-addressed observations without retaining the artifact bytes or
  treating their hashes as truth;
- supports separately consented topic filters, delivery cadence, and opaque
  market watchlists in the same owner-only database, and erases the preference
  profile on `/leave`, `/stop`, or `/delete_me`;
- preregisters explicit paper YES probabilities in an owner-only hash-chained
  ledger, appends evidence-linked outcomes, and reports Brier/log-loss
  calibration against an optional captured market baseline;
- builds stable, forward-safe Dispatch cards from an active approved envelope,
  dry-runs channel posts by default, and, only with `channel-post --apply`,
  verifies the publisher bot and actual Telegram channel before recording a
  sent, failed, or ambiguous publication receipt;
- registers opaque Telegram campaign links locally, records `/start` as a
  per-campaign daily aggregate with no user link, and creates linkable
  attribution only after an explicit source-linked alert opt-in;
- also accepts a direct `/join` without retroactive campaign attribution and
  sends at most two new alerts per rolling seven days;
- makes `/leave`, `/stop`, and `/delete_me` bypass ordinary command throttling,
  retains a minimal numeric-user-ID and event-watermark suppression marker so
  delayed updates cannot undo withdrawal or deletion, and treats blocking the
  bot as withdrawal;
- immediately purges nonfinancial campaign, consent, delivery, and paper data
  on `/delete_me`, sends no later research messages until a newer explicit
  alert opt-in, and retains only the
  no-contact marker plus finance/support evidence subject to retention holds;
- excludes pre-opt-in signal backlog while preserving owed corrections for
  recipients who have neither withdrawn nor deleted their data;
- contains a gated Telegram Stars flow that, when deliberately enabled by an
  embedding, creates user-bound recurring invoice links only after terms
  acceptance and grants access only from a matching `successful_payment`
  update carrying Telegram's subscription expiry;
- reconciles two complete, identical `getStarTransactions` passes against
  local payment state, records sanitized mismatches, and applies exact positive
  refund evidence without treating transaction history as an entitlement
  source;
- provides a synchronous, listener-neutral webhook adapter that checks the
  configured path, Telegram secret header, HTTP framing, body bounds, strict
  JSON, and durable update handling before returning a response;
- provides a disabled-by-default, one-shot AgentTool Collab reader and separate
  owner-only Ops projection/reply database, with explicit private binding,
  foreground poll/send/reconciliation and a credential-free synthetic demo;
  it creates no Collab session, acknowledges no Collab cursor, launches no
  agents and installs no background process; live Ops delivery is unverified;
- scores an already-fetched, bounded Polymarket Gamma snapshot for manual
  research review, binds the report to exact input bytes with SHA-256, and has
  no network or execution method; and
- keeps idempotent update, payment, reconciliation, and per-recipient delivery
  records in an owner-only local SQLite database.

It deliberately does not:

- hold a wallet, private key, CLOB credential, signer, token allowance, or
  order API;
- turn S012 approval, a market score, a Telegram subscription, a bot token, or
  a model output into permission or authority to trade;
- establish a recipient's physical location, venue eligibility, consent to an
  order, or a lawful basis for live execution;
- treat a content hash as authorship, truth, source authentication, or model
  identity;
- create a Telegram bot or channel, grant channel administration, publish a
  discovery link, open a socket, terminate TLS, configure Telegram's webhook,
  or attach itself to Oracle cron jobs, OpenClaw, HIVE, or another service; or
- promise exactly-once Telegram delivery. A lost response after Telegram
  accepted a message is recorded as `unknown` and is not replayed
  automatically.

The intended information flow is:

```text
bounded artifacts --> observations ----------+
                                             |
S012 signal JSONL ---------+                 |
                           +--> sealed signal + effective lifecycle state
S012 lifecycle JSONL ------+                 |
                                             +--> private research delivery
Gamma snapshot --> bounded manual review ----+--> prospective calibration
                                             +--> reviewed Dispatch card

                                             X--> wallet / signer / live order
```

## Offline setup and inspection

```bash
cd ~/Desktop/prediction-markets

# Creates the owner-only gateway/preferences/observation schema plus empty
# calibration and channel-publication ledgers under telegram_gateway/var/.
python3 -m telegram_gateway init

# First observation records EOF and does not import existing history.
python3 -m telegram_gateway ingest
python3 -m telegram_gateway ingest-lifecycle

# Explicit local history classification, if deliberately wanted. Sends nothing.
python3 -m telegram_gateway ingest --backfill
python3 -m telegram_gateway ingest-lifecycle --backfill

python3 -m telegram_gateway preview
python3 -m telegram_gateway preview --public
python3 -m telegram_gateway status

# Verify an empty or populated prospective paper-calibration chain.
python3 -m telegram_gateway calibration-verify
python3 -m telegram_gateway scorecard

# Local-only promotion setup and aggregate reporting. Omitting the username
# creates only an opaque campaign code; a rendered link additionally requires
# the durable Research Bot identity previously established by bot-doctor.
python3 -m telegram_gateway campaign-create \
  --kind telegram_channel
python3 -m telegram_gateway promotion-status
# Exact small-cohort output is re-identification-risk local diagnostics only.
python3 -m telegram_gateway promotion-status --exact-local
python3 -m telegram_gateway campaign-disable CAMPAIGN_CODE

# Explicit maintenance after logical deletions; stop the runner first.
python3 -m telegram_gateway compact
```

The default sources are `data/s012/signals.jsonl` and
`data/s012/signal-lifecycle.jsonl`. Signal and lifecycle importers maintain
separate source-bound cursors. Truncation, replacement, prefix changes,
oversized rows, malformed complete JSON, and unsafe cursor boundaries fail
closed rather than silently replaying data. A trailing partial append waits for
its newline.

S012 review transitions are produced separately:

```bash
python3 scripts/s012/signal_generator.py --pending
python3 scripts/s012/signal_generator.py --approve SIGNAL_ID_PREFIX
python3 scripts/s012/signal_generator.py --reject SIGNAL_ID_PREFIX
python3 scripts/s012/signal_generator.py --revoke SIGNAL_ID_PREFIX
```

These commands update S012's own SQLite state and append the corresponding
lifecycle event. `APPROVED` means approved for research distribution only;
every lifecycle event fixes `execution_allowed` to `false`.

## Offline market-candidate scoring

`market-candidates` reads an already-fetched Gamma `/markets` or `/events`
snapshot. It performs no HTTP request and never returns a trade instruction.

```bash
python3 -m telegram_gateway market-candidates \
  --source /path/to/gamma-snapshot.json \
  --as-of 2026-09-02T20:05:00Z \
  --snapshot-at 2026-09-02T20:04:30Z \
  --endpoint markets
```

Input is capped at 2 MB and 500 candidate records. Snapshot age, a 1-45 day
horizon, explicit resolution evidence, liquidity, 24-hour volume, bid/ask
spread, near-certainty, and initially excluded categories are evaluated with
finite bounds. Every row is one of `MANUAL_REVIEW`, `INCOMPLETE`, or
`EXCLUDED`; even `MANUAL_REVIEW` has `execution_allowed: false`.

No present market has been selected from the repository's cached data. The
bounded March 22, 2026 sample is stale as of September 2, so all 200 inspected
rows fail closed; larger cached files also exceed this command's input bounds.
A later live public-data smoke check and its two September Fed manual-review
candidates are recorded in [MARKET_STRATEGY.md](MARKET_STRATEGY.md). They
remain paper-research subjects, not a direction or trade, until independent
forecasting and manual rule/cost review are complete.

## Evidence, calibration, and Dispatch cards

Record only an artifact already fetched and archived by the operator. The
gateway stores its digest and metadata, not the artifact itself, and makes no
network request:

```bash
python3 -m telegram_gateway evidence-record \
  --market-id MARKET_ID --kind primary_source \
  --source-url https://official.example/release \
  --publisher 'Official publisher' \
  --observed-at 2026-09-03T10:00:00Z \
  --statement 'Bounded factual statement reviewed by the operator.' \
  --artifact /path/to/archived-response --media-type text/html
```

After the resulting observation reference and an explicit resolution-rules
reference have been sealed into S012 and the signal is approved, preregister a
paper probability before resolution:

```bash
python3 -m telegram_gateway forecast-register SIGNAL_ID \
  --probability-yes 0.60
python3 -m telegram_gateway scorecard --domain ECO
```

`channel-post` consumes a bounded JSON list whose objects contain exactly
`observation_ref`, `label`, `url`, `observed_at`, and `is_primary`. Preparation
is the default and reports `network_calls: 0`:

```bash
python3 -m telegram_gateway channel-post SIGNAL_ID \
  --channel @KingdomDispatch \
  --source-links /path/to/reviewed-source-links.json \
  --market-url https://polymarket.com/event/EXAMPLE \
  --published-at 2026-09-03T10:05:00Z \
  --campaign-code ACTIVE_CAMPAIGN_CODE \
  --research-bot-username KingdomResearchBot
```

The campaign options are paired and optional. When present, the campaign must
already be active in this gateway and the Research Bot username must match the
durable identity established by authenticated `bot-doctor`. The publication
text and digest then bind a canonical `t.me/...?...start=` CTA using the stored
Telegram spelling. A missing or mismatched identity fails before credential,
network, or publication-ledger access. `/start` still only records a daily
aggregate, and linkable attribution still requires the separate in-bot opt-in.

Only an explicit rerun with `--apply --bot-username PublisherBot` can contact
Telegram. It verifies the credential identity, resolves the target with
`getChat`, requires Telegram to report `type: channel`, sends to the resolved
numeric channel ID, and writes the separate owner-only publication ledger.
Known failures require operator review before `--retry-failed`; ambiguous sends
must first be resolved with `channel-reconcile`, never blindly replayed. Bot and
channel creation, admin assignment, source review, and publication approval
remain human actions. The complete operating sequence is in
[COMMUNITY_RUNBOOK.md](COMMUNITY_RUNBOOK.md).

## Private AgentTool Ops companion

The separate Ops companion can observe a pinned local AgentTool Collab journal
through a strict read-only MCP allowlist and reduce events to opaque,
fixed-template projections. It atomically stages replies for one bound human
operator. Polling sends nothing; a separate `ops-send-once` preview followed by
explicit `--apply` delivers exactly one selected reply attempt. Unknown outcomes
are recorded and never automatically resent. It does not reuse Research state,
manage agents, mutate Collab coordination, or trade. `run` remains Research-only.

Try the credential-free demonstration first:

```bash
cd ~/Desktop/prediction-markets
python3 -B -m telegram_gateway ops-demo
python3 -B -m telegram_gateway ops-demo --scenario unknown
```

Scenarios: `happy`, `duplicate`, `crash`, `refusal`, `cancellation`, `unknown`.
Each uses disposable local state and fake transports: no real model agents,
Telegram delivery, pinned process attestation, real journal verification, or
earnings. This build has not performed a live Ops smoke test.

```bash
# Separate local schema. Global --db must precede the subcommand.
python3 -m telegram_gateway \
  --db telegram_gateway/var/ops-bot.db ops-init
python3 -m telegram_gateway \
  --db telegram_gateway/var/ops-bot.db ops-status

# Explicit source observation; not part of the synthetic demo.
python3 -m telegram_gateway \
  --db telegram_gateway/var/ops-bot.db ops-watch-once \
  --workspace-id WORKSPACE_ID \
  --collab-db ~/.local/share/agenttool/collab.sqlite
```

The first observation previews the verified head. Explicit `--seed-current-head`
imports no historical events; later runs project at most 50 events each and fail
without cursor advancement if the source head changes during verification. The
MCP child uses read-only API calls but opens its journal SQLite read/write for
initialization; this is not an OS-enforced read-only database boundary.

`ops-status` validates role/schema and enforces local permissions, not a
byte-for-byte read-only open. Recognized v1 stores require explicit
`ops-migrate` preview followed by `ops-migrate --apply`; mixed or unknown schemas
are rejected. No migration fabricates missing historical replies.

See [`AGENTOOL_OPS.md`](AGENTOOL_OPS.md) for the exact dedicated Keychain/binding,
Ops-profile doctor/configure, poll, reviewed send, reconciliation and pause/resume
procedure. For live use, bind a fresh store **before** source observation;
preexisting unbound projections remain offline rather than being silently
assigned to a new operator/source. Previews perform zero credential/provider
calls. Live operations need
the separate Ops bot and exact operator established first. No Ops background
service, event alerts, bot-to-bot collaboration or commerce is activated.

An optional [private Ops MCP server](../integrations/telegram_ops_mcp/README.md)
now wraps the same foreground runtime through local stdio. Its isolated SDK is
not imported by the existing CLI. Default tools expose minimized status, reply
metadata and an explicit exact-text preview; poll/send/pause/reconciliation
require operator-side capability selection. Missing configuration leaves
inspection discovery usable without credentials, database initialization or
provider calls. No general Telegram client or agent dispatcher is exposed.
Native host approval and live Telegram delivery require separate verification.

## Telegram bot bootstrap

The bootstrap is deliberately split into resumable phases. The first classic
bot still needs a visible human confirmation in Telegram's verified
`@BotFather` chat; this code does not script Telegram's UI, send BotFather
messages, or scrape the returned token from Desktop.

```bash
# Offline plan, using a candidate whose availability BotFather must confirm.
python3 -m telegram_gateway bot-plan \
  --bot-username KingdomResearchBot

# Open the genuine BotFather chat, but send nothing automatically.
python3 -m telegram_gateway bot-plan \
  --bot-username KingdomResearchBot --open-botfather

# Optional: copy exactly one public input (newbot, name, username, or commands).
python3 -m telegram_gateway bot-plan \
  --bot-username KingdomResearchBot --copy newbot
```

After BotFather returns the full-control token, run the following command in a
terminal and paste the token only into macOS `security`'s hidden prompt:

```bash
python3 -m telegram_gateway bot-token-store \
  --bot-username KingdomResearchBot
```

The token is stored as a generic-password item under service
`dev.kingdom.prediction-markets.telegram-bot-token` and a lowercase bot
username account. It is never a command argument, plaintext project file,
shell-history entry, or CLI output. The item has macOS Keychain at-rest
protection and the default `/usr/bin/security` access controls; that does not
isolate it from a hostile process running as the same logged-in macOS user.
The command refuses to overwrite an existing item. For a corrected or rotated
token, select a new lowercase versioned slot and then use the same option on
every credential-consuming command:

```bash
python3 -m telegram_gateway bot-token-store \
  --bot-username KingdomResearchBot \
  --keychain-account kingdomresearchbot-v2
python3 -m telegram_gateway bot-doctor \
  --bot-username KingdomResearchBot \
  --keychain-account kingdomresearchbot-v2
```

The store command attempts to clear the current macOS clipboard afterward;
its JSON result says whether that local operation succeeded. Clipboard
managers, Universal Clipboard, and the BotFather message remain outside that
clearing boundary.

In BotFather, disable group joins with `/setjoingroups` and keep Group Privacy
Mode enabled with `/setprivacy`. Leave inline, guest, business, Main Mini App,
private-topic, join-request, and Bot Management modes disabled for this least-authority
research bot. Keep Bot-to-Bot Communication Mode disabled as well. Then verify
and apply the profile:

```bash
python3 -m telegram_gateway bot-doctor \
  --bot-username KingdomResearchBot

# Offline preview; makes no API call.
python3 -m telegram_gateway bot-configure \
  --bot-username KingdomResearchBot

# Explicitly sets the name, descriptions, private command scope, and menu.
python3 -m telegram_gateway bot-configure \
  --bot-username KingdomResearchBot --apply

# Creates one verified campaign once and reuses it on every rerun. It does not
# publish the link.
python3 -m telegram_gateway bot-campaign \
  --bot-username KingdomResearchBot
```

The doctor authenticates with `getMe`, checks the expected username, private-
only capability flags, base-profile readback, and absence of a webhook. It
returns only public identity and sanitized booleans, then binds the local
database to that immutable bot ID, authenticated username, and credential-free
API origin. A different bot cannot later reuse the database or receive a
campaign CTA from it. Neither doctor nor configure deletes a
webhook. Telegram exposes no Bot API setter for `/setjoingroups`, Group Privacy
Mode, or BotFather's custom privacy-policy field, so those remain visible human
checks. The API also cannot enumerate every old per-chat or language-specific
command/menu override, which is why this MVP requires a fresh bot rather than
repurposing one. Complete and publish
[`PRIVACY_POLICY_TEMPLATE.md`](PRIVACY_POLICY_TEMPLATE.md) before promotion;
the local template is not yet a public policy URL. `bot-campaign` verifies the
live base profile and existing database binding before producing a deep link,
but deliberately reports `published: false` and cannot certify those manual
publication checks.

Configuration is an idempotent sequence, not a remote transaction. If a
request outcome is unknown or final readback disagrees, the CLI names the
failed phase and tells the operator to run `bot-doctor` before safely rerunning
`bot-configure --apply`; it does not attempt a blind rollback or retry.

On a fresh bot, the first doctor run can exit successfully with
`runtime_ready: true` while `bot_api_profile_ready` is still false; that is the
expected handoff to `bot-configure --apply`. A nonzero doctor result means an
identity, capability, webhook, API-response, or database-binding preflight did
not pass.

For a later multi-bot product, `managed-bot-link` creates Telegram's official
user-confirmed Managed Bot link. It does not create anything by itself:

```bash
python3 -m telegram_gateway managed-bot-link \
  --manager-username KingdomManagerBot \
  --bot-username KingdomClientBot \
  --name 'KINGDOM Client Research'
```

The manager must first be human-created and have Bot Management Mode enabled;
the user sees and confirms each child creation and remains its owner. Manager
credentials can retrieve or replace managed-child tokens, so that factory is a
separate high-authority service, not part of this MVP runner.

## Telegram development runner

The preferred credential source is the Keychain item created above. A scoped
environment variable remains available for vault-backed child-process
injection, but must be selected explicitly and must never live in `.env`, shell
startup, source control, chat, or command output.

Credential choices for Telegram API commands:

- `--token-source keychain --bot-username YourBot`;
- optionally add the same `--keychain-account yourbot-v2` used at storage time;
- `--token-source environment` with `KINGDOM_TELEGRAM_BOT_TOKEN` present only
  in that process.

Optional:

- `KINGDOM_TELEGRAM_DB`
- `KINGDOM_TELEGRAM_STARS_PRICE` — keep omitted or `0` in this runner
- `KINGDOM_TELEGRAM_TERMS_VERSION`
- `KINGDOM_TELEGRAM_SUPPORT_CONTACT`
- `KINGDOM_TELEGRAM_PROMOTION_NOTICE_VERSION` — change only when the alert
  consent copy changes; prior opt-ins then require `/join` reconfirmation
- `KINGDOM_TELEGRAM_PREFERENCE_NOTICE_VERSION` — change when the
  personalization notice changes; prior filters are not applied until a new
  `/personalize`, while separately consented alerts remain governed by the
  core alert-consent state
- `KINGDOM_CALIBRATION_LEDGER` — owner-only prospective paper ledger
- `KINGDOM_CHANNEL_LEDGER` — owner-only Dispatch publication receipts

```bash
python3 -m telegram_gateway run --token-source keychain \
  --bot-username KingdomResearchBot --once --control-only
python3 -m telegram_gateway run --token-source keychain \
  --bot-username KingdomResearchBot
```

The development runner uses `getUpdates` and must be the sole consumer for the
bot token; Telegram polling and webhooks are mutually exclusive. It does not
delete a webhook or drop pending updates. Before polling, it verifies bot
identity, private-only flags, an empty webhook, and the database binding. A
local lock prevents simultaneous
gateway CLI workers from using the same database. Signal import failures leave
Telegram control processing available. A lifecycle-import failure additionally
pauses new research broadcasts; already-owed revocation notices are attempted
before ordinary signal delivery.

The long-poll runner refuses a nonzero Stars price. Merely constructing a
library `ServiceConfig` with a positive price also leaves commerce off;
an embedding must separately set `enable_stars_commerce=True`. That flag is a
technical activation control, not proof of legal review or operator authority.
Updates in each response are processed in Telegram ID order for restart-safe
payment state, but ordinary work can delay a later pre-checkout update. Because
Telegram may choose a random next update ID after a week without updates, the
runner resets only its fetch offset at six days of observed idle time while
retaining the lifetime replay ledger. This prevents an old high offset from
hiding a later low-ID `/leave` or `/delete_me`. Alert consent uses the Telegram
message timestamp rather than numerical update order, and opt-out is
conservatively dominant. Provider-state ordering still requires production
hardening before commerce is enabled. `--control-only` still answers queued
private commands but pauses both ordinary research broadcasts and owed
correction broadcasts. It also skips signal and lifecycle ingestion, so source
cursors and imported research data remain untouched during the initial smoke
test.
Non-private updates are silently recorded and ignored. This runner is therefore a development
harness, not an adequate merchant backend. See Telegram's official
[`Update`](https://core.telegram.org/bots/api#update) and
[`getUpdates`](https://core.telegram.org/bots/api#getupdates) contracts.

### Always-on control-only LaunchAgent

The device-specific plist at
[`launchd/dev.kingdom.prediction-markets.telegram-control.plist`](launchd/dev.kingdom.prediction-markets.telegram-control.plist)
runs the project virtual environment continuously with `--control-only`. It
reads the token from the explicit Keychain account; the plist contains no
credential. The job can answer user-initiated private commands, but it skips
signal ingestion and cannot send ordinary research or correction broadcasts.
Stars remain fixed to zero, and the gateway still has no wallet or trading
capability.

The installed copy lives in `~/Library/LaunchAgents/`. Its logs are under
`~/Library/Logs/KingdomResearchBot/`; the directory is mode `0700` and both log
files are mode `0600`. Idle polls are intentionally silent. `KeepAlive` and a
60-second throttle provide restart behavior, not a universal availability
guarantee. Logs are not automatically rotated yet.

```bash
# Inspect the loaded job.
launchctl print \
  "gui/$(id -u)/dev.kingdom.prediction-markets.telegram-control"

# Stop it before maintenance or any manual poller using the same bot token.
launchctl bootout \
  "gui/$(id -u)/dev.kingdom.prediction-markets.telegram-control"

# Reload the installed plist afterward.
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/dev.kingdom.prediction-markets.telegram-control.plist"
```

The runner holds `<gateway.db>.run.lock` for its lifetime. Do not start another
`getUpdates` consumer with a different database: that would bypass the local
lock and can create competing Telegram consumers. Stop this job before changing
the bot profile, compacting the database, switching to webhook ingress, or
enabling a broader development runner.

## Webhook integration boundary

`TelegramWebhookIngress` is the reusable validation/dispatch layer for a future
production listener:

```python
from telegram_gateway import TelegramWebhookIngress

ingress = TelegramWebhookIngress(service, secret_token=scoped_webhook_secret)
response = ingress.dispatch(
    method=request_method,
    path=request_path,
    headers=request_headers,
    body=exact_request_bytes,
)
```

The owning listener must still cap the body while reading it, terminate HTTPS,
preserve the exact method/path/headers/body, avoid logging secrets or payloads,
and serialize or safely claim updates. The adapter itself neither binds a port
nor makes a local server internet-safe. Authenticated malformed requests are
permanently rejected and acknowledged without storing their bodies; known
update-processing failures are quarantined when an update ID is available, and
unexpected internal failures return a retryable response.

## Telegram Stars ledger

Run reconciliation only as a deliberate, credential-scoped maintenance action
while no other gateway worker holds the database lock:

```bash
python3 -m telegram_gateway stars-reconcile \
  --token-source keychain --bot-username KingdomResearchBot \
  --max-transactions 10000
python3 -m telegram_gateway stars-status
python3 -m telegram_gateway stars-issues
```

The reconciler binds the database to the Telegram bot ID and credential-free
API origin, starts each pass at offset zero, pages the full bounded history,
normalizes an allowlist of scalar fields, and accepts a snapshot only when two
complete passes have the same canonical digest. Unknown, malformed, mismatched,
missing, refund, and cancellation evidence remains visible as sanitized local
issues. The command exits nonzero unless the completed scan is clean.

Transaction history can confirm a refund, but it lacks the complete expiry and
recurrence evidence used by the `successful_payment` control update. It
therefore never creates entitlement. Likewise, observing an outgoing refund
does not prove that recurring billing was canceled; that remains an explicit
provider-control action and reconciliation issue. Ledger status always reports
`commerce_ready: false` in this prototype.

## Bot commands

- `/start`, `/help`
- `/join`, `/leave`, `/stop`
- `/brief`, `/latest`
- `/personalize`
- `/topics [CODE ...]`, `/cadence [realtime|daily|weekly]`
- `/watch MARKET_REF`, `/unwatch MARKET_REF`, `/watchlist`
- `/scorecard [DOMAIN]`
- `/paper SIGNAL_ID [USD]` — local simulation only
- `/plans`, `/subscribe`
- `/settings`, `/status`, `/cancel`
- `/terms`, `/privacy`
- `/paysupport`
- `/delete_me`

`/trade`, `/execute`, `/buy`, and `/sell` return the hard
`LIVE_EXECUTION_DISABLED` policy decision.

Sending `/start` through an allowlisted campaign deep link increments only its
daily aggregate start count. `/start` itself creates no user-linked attribution
or alert consent. Attribution becomes linkable to a numeric Telegram user ID
only when that person chooses the source-linked alert opt-in; a plain `/join`
does not retroactively claim a campaign conversion.

Attribution rows are append-only. The store requires a matching subscribed
consent event from the same Telegram update and removes legacy orphan rows when
it opens. SQLite triggers preserve that structural relationship through
ordinary row mutations. They do not prove campaign causality or authenticate
evidence fabricated by a privileged database owner who can write matching
rows, alter the schema, or disable its controls; the supported causal boundary
is the notice-bound callback handled by `BotService`.

`/personalize` is separate from alert consent. It stores only the numeric
private-chat identity, allowlisted topic codes, a cadence, and bounded opaque
market references; an empty topic set means all supported topics. Watchlists
can override a topic mismatch, while cadence is a maximum-frequency preference
and never overrides the global two-per-week alert cap. Owed corrections bypass
ordinary preference filters.

`/leave` and `/stop` erase that preference profile and persist minimal
suppression markers keyed by the numeric Telegram user ID and newest
control-event watermark so delayed updates cannot silently opt the person back
in. `/delete_me` immediately removes nonfinancial campaign attribution,
consent/event state, preferences, delivery receipts, and paper actions and
suppresses future research messages until a newer explicit alert opt-in. It
retains minimal no-contact watermarks and only finance/support evidence while
applicable retention holds require it.

The default `promotion-status` report suppresses a campaign's behavioral
counts when any relevant cell is 1–4, including aggregate start events, and
buckets every other nonzero behavioral count into a five-wide range. It also
suppresses global behavioral totals when needed to prevent differencing. This
is disclosure reduction, not an anonymity guarantee: starts are not unique
people, and repeated reports or outside context can still leak information.
Keep reports local. `--exact-local` exposes exact small-cohort counts and is
explicitly unsafe, local-only diagnostics; do not publish or paste that output.
The generic `status` output omits recipient, promotion, and financial behavior.
Metrics describe current retained state, not a lifetime conversion funnel:
`/delete_me` removes linkable rows while aggregate starts remain, so attribution
and consent counts can decrease. Start counts are at-least-once across a hard
process crash and may overcount a retried `/start` update.

## Evidence and authority

Only an unexpired, intact signal with an effective `APPROVED` lifecycle state
can be selected for delivery. `PENDING`, `REJECTED`, `REVOKED`, and `EXPIRED`
signals remain unavailable. Approval is content-addressed, revisioned, and
scoped to `research_distribution_only`; it is not approval of a wager or order.
An imported base signal cannot arrive pre-approved: revision zero accepts only
`PENDING` or risk-rejected input, and only a matching lifecycle event can open
the distribution gate.

Current S012 rows contain internal event and assessment identifiers but do not
yet contain verified immutable WW3 Observation IDs or independently verified
market-resolution rules. They remain labelled `WATCH` with explicit evidence
limitations. A supplied reference records only that a reference was present,
not that the gateway authenticated its content or truth.

The gateway describes forecasting output as an analysis artifact. A model
response, persona, memory artifact, content hash, bot credential, entitlement,
or confidence value does not establish identity, consent, eligibility, or
trading authority. Capability, technical permission, operational authority,
affected-party consent or lawful basis, jurisdiction, and an order-specific
action remain independent gates. The collaboration baseline is
`xenia.rights/0.1`; it changes treatment expectations, not account access.

## Production gaps

The implemented modules are necessary controls, not a deployment claim. Before
accepting Stars or offering any production subscription, the project still
needs:

- an owned, stable HTTPS listener/load-balancer around the webhook adapter,
  Telegram webhook registration, serialized/durable update claiming, health
  gates, and deployment/rollback operations;
- a way to run ledger maintenance without contending with the long-lived
  gateway lock, plus scheduled reconciliation, alerts, operator review, and
  tested refund/cancellation administration;
- end-to-end tests against a separate Telegram test bot, including delayed,
  duplicated, reordered, renewal-failure, refund, and cancellation paths;
- tested encrypted backup/restore, deletion verification, data-retention
  limits, incident response, and legally reviewed customer terms/support;
- fresh bounded Gamma capture, durable storage for archived artifact bytes,
  primary-source and resolution-rule authentication/review, and immutable
  observation identifiers propagated into live S012 inputs;
- a reviewed worker and operator workflow for Dispatch status-successor cards;
  root channel posts are CLI-wired, while amendments, withdrawals, expiries,
  and resolutions remain library-level components;
- prospective calibration before any performance claim: resolved forecasts,
  proper scoring rules, market baselines, post-cost paper results, drawdown,
  abstentions, and dispute tracking; and
- jurisdiction-specific venue, payments, consumer, gambling, marketing,
  privacy, and tax review.

Live execution, if ever designed, belongs in a separate service and requires a
new, explicit scope. It is not the next implicit step of this gateway.

The proposed market universe, scoring gates, product shape, and launch stages
are in [MARKET_STRATEGY.md](MARKET_STRATEGY.md).

Official references:

- <https://core.telegram.org/bots/api#createinvoicelink>
- <https://core.telegram.org/bots/api#successfulpayment>
- <https://core.telegram.org/bots/api#getstartransactions>
- <https://core.telegram.org/bots/api#edituserstarsubscription>
- <https://core.telegram.org/bots/payments-stars>
- <https://help.polymarket.com/en/articles/13364163-geographic-restrictions>
