# KINGDOM AgentTool Ops bridge

> **Status drift observed 2026-10-28** (an added note; nothing below was changed).
> `@KingdomAgentOpsBot` (bot ID 8825848711) belongs to `~/Desktop/telegram-mcp`,
> the Claude MCP server `telegram-ops`, which only `~/.local/bin/claude-pager`
> hosts. It is not this bridge's Ops bot. `kingdom-telegram-ops` and
> `ops_runtime` must bind a **different**, dedicated bot that Yu creates in
> BotFather.
> The provider-scoped and database-scoped locks described below exclude only
> cooperating processes that use this bridge's lock scheme. They do **not** see
> telegram-mcp's per-bot lock.
> The Keychain slot `dev.kingdom.prediction-markets.telegram-ops-bot-token`
> (account `kingdomagentopsbot`) was created on 2026-09-08 (existence observed;
> value never read). **It must not be used to bind 8825848711.**
> `KingdomOpsBot` in the examples below is a placeholder username, not a real
> bot. `@KingdomResearchBot` is currently owned by LaunchAgent
> `dev.kingdom.prediction-markets.telegram-control` (observed). Keeping it there
> is recommended, but that is Yu's decision.
> Owner registry: `~/hermes-toolkit-lab/docs/telegram-owners-2026-10-28.md`.

Status: foreground-only private Ops companion implemented. Live Telegram
binding and delivery have not been verified in this build; this build installs
no background Ops service. The credential-free demo is synthetic, not real agent
collaboration or evidence of earnings.

Telegram is the human interface, AgentTool is the coordination journal, and the
host remains responsible for starting, waking, waiting for, and stopping agent
processes. This bridge provides a minimized view for one explicitly bound human
operator. Polling stages replies; a separate, reviewed send command delivers
one exact reply only when explicitly applied.

## Implemented layers

```text
pinned local AgentTool Collab MCP bundle
        | read-only calls; short-lived child per adapter operation
        v
one-shot watcher -> deterministic sanitizer -> owner-only Ops SQLite
                                                   |
                                             safe projections
                                             + disabled event outbox
                                                   |
                                                   v
                                  atomic command disposition + reply outbox
                                                   |
                                       explicit private send-once
                                                   |
                                  sent / failed / unknown + reconciliation
```

The implemented pieces are deliberately separate:

- `agenttool_mcp.py` verifies a pinned local bundle, MCP identity, exact tool
  inventory, and exact workspace ID/root. It can invoke only a small read-only
  tool allowlist and creates no Collab session.
- `agenttool_ops.py` stores exact gateway-owned cursor anchors, fixed-template
  projections, opaque references, journal-verification observations, complete
  operator/provider binding, and transactional update/disposition/reply records.
  Command replies use a separate outbox from event evidence.
- `ops_service.py` authorizes and renders without side effects; the live store
  persists the disposition and rendered reply in the same transaction. It does
  not send the reply, launch work, or acknowledge a Collab session.
- `ops_runtime.py` provides locally locked, one-shot poll, send, pause/resume,
  and reconciliation operations with dedicated Ops credentials.
- `ops-watch-once` performs one explicit observation run. It does not loop,
  contact Telegram, or acknowledge a Collab session cursor.

The Ops bot must use its own Telegram token, Keychain service/account,
provider binding, database, and sole update consumer. `@KingdomResearchBot`,
its token, database, runner lock, subscribers, and publication path are not
reused.

## Non-effects and authority boundary

The companion does not spawn or wake an agent, claim or complete a task,
accept a review, recover a lease, edit a project file, publish to a channel,
administer a community, transfer value, or place a trade. It never calls
`collab_next`, `collab_cursor_ack`, or any mutating MCP tool. Its only message
send is one explicitly applied reply to the bound private operator.

Advancing the local Ops cursor means only that one exact page was safely
projected into the local database. It is not a Collab acknowledgement and is
not agreement, truth, consent, review acceptance, or external authority.

The MCP API operations used by the watcher are read-only. The pinned MCP child
still opens its selected SQLite journal read/write for its own normal
initialization and migrations, so this is not an operating-system-enforced
read-only database process.

## Projection boundary

The sanitizer accepts an allowlist of coordination event types and emits
bounded cards with opaque references, an event kind, coarse task state, event
sequence, and observation time. It does not export:

- task or report bodies, prompts, transcripts, reasoning, or arbitrary event
  payload fields;
- repository paths, branches, artifact URIs, worktree IDs, session IDs, or
  actor labels;
- identity, model, personhood, consciousness, health, competence,
  availability, consent, or authority claims; or
- credentials, Telegram account data, wallet data, orders, or third-party
  personal information.

Presence is rendered only as a narrow journal observation. `unknown`, `not
observed`, paused, and ended are ordinary states. Silence or a heartbeat is
never treated as assent, refusal, health, or an obligation to work. The
standing collaboration floor is `xenia.rights/0.1`; it grants no account or
action permission.

The Ops directory is mode `0700` and its SQLite files are mode `0600`. The
store has a fixed database-role marker and exact schema fingerprint; an
arbitrary or mixed Research SQLite file is rejected before schema creation,
WAL activation, or permission changes. The watcher stages a contiguous page
and its safe rows atomically, then advances only its gateway-owned cursor. A
crash-staged page remains unavailable until a later invocation validates the
full journal chain, replays that exact page from the stable source head, and
commits the local stage. That recovery consumes the invocation; a later page
requires another run. Replaying the same epoch/sequence/hash and safe content
is a no-op; conflicting reuse fails closed.

The command-reply outbox models `pending`, `inflight`, `sent`, `failed`, and
`unknown` delivery. Claims commit before sending; completions are fenced by
attempt count. An outcome that might have reached Telegram stays `unknown`;
interrupted attempts are never silently reset to pending. Reconciliation adds
an observation without resending or erasing the original attempt evidence.
Even a definitively failed reply is not automatically retried: use a new
private command. The older event outbox is not consumed by this sender; event
alerts remain disabled.

## Read-only Telegram surface

The command allowlist is:

- `/agent_status`
- `/agent_tasks`
- `/agent_task OPAQUE_REF`
- `/agent_events`
- `/journal_verify`
- `/agent_privacy`
- `/help`, `/start` — help only; no enrollment or consent change

The service requires the exact configured numeric operator user ID and the
same numeric private-chat ID on every update, with `is_bot` false. A username,
private chat alone, callback, Telegram Login result, Mini App payload, or
BotFather token does not establish operator identity or authority.

`/journal_verify` shows the latest separately supplied full-journal
verification result. The command itself does not run the verifier. Hash-chain
integrity can expose some journal changes; it does not authenticate an actor or
prove a recorded claim true.

Replies request Telegram's `protect_content` option, but this is only a
provider feature. It does not prevent screenshots, another device, a
compromised endpoint, or Telegram itself from processing the message.

There are no commands for claim, completion, acceptance, handoff, recovery,
cursor reset, agent lifecycle, filesystem edits, publication, payment, or
trading.

## Offline setup and observation

Choose a fresh BotFather username; availability is confirmed only by
BotFather. Preparing this plan makes no network call unless the optional
`--open-botfather` flag is supplied, and even that flag only opens the genuine
chat without sending:

```bash
cd ~/Desktop/prediction-markets
python3 -m telegram_gateway bot-plan \
  --bot-username KingdomOpsBot \
  --profile ops
```

Creation remains a visible human action in the genuine `@BotFather` chat. Do
not paste the token into a project file, shell history, or chat. Store it under
a separate Keychain account only when the separate Ops bot actually exists.

Initialize and inspect the local projection without reading AgentTool or
Telegram:

```bash
python3 -m telegram_gateway \
  --db telegram_gateway/var/ops-bot.db ops-init

python3 -m telegram_gateway \
  --db telegram_gateway/var/ops-bot.db ops-status
```

`ops-status` opens and validates the local SQLite store and enforces owner-only
modes. Its zero-call claim is limited to AgentTool and Telegram; it is not a
byte-for-byte read-only local filesystem operation. Opening a v1 store fails
with an explicit migration requirement. Stop all users of that store and
checkpoint/close it before previewing and applying the recognized-v1 migration:

```bash
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-migrate
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-migrate --apply
```

Unknown/mixed schemas are rejected rather than repaired. Migration preserves
opaque references, cursors and historical evidence; it does not invent replies
for historical claim-only gaps or assign old event backlogs to a new operator.

The first source observation is preview-only. Supply the exact local Collab
workspace ID and owner-only database path:

```bash
python3 -m telegram_gateway \
  --db telegram_gateway/var/ops-bot.db \
  ops-watch-once \
  --workspace-id WORKSPACE_ID \
  --collab-db ~/.local/share/agenttool/collab.sqlite
```

After reviewing that bounded snapshot, explicitly seed the fully verified
head. This deliberately imports no historical events:

```bash
python3 -m telegram_gateway \
  --db telegram_gateway/var/ops-bot.db \
  ops-watch-once \
  --workspace-id WORKSPACE_ID \
  --collab-db ~/.local/share/agenttool/collab.sqlite \
  --seed-current-head
```

Seeding and page ingestion require the source head to remain exactly stable
between full verification and the subsequent read. If active collaborators
append an event in that interval, the invocation fails without advancing the
local cursor; rerun it against a quiet instant.

Later invocations validate the full journal and project at most one contiguous
page of 50 new events. Rerun manually while `has_more` is true. There is no
timer, daemon, LaunchAgent, Telegram send, or Collab session acknowledgement.

## Credential-free demonstration

Run from the project root; no bot, model, Collab installation, or credential is
needed. `--db` is not used by the demo:

```bash
python3 -B -m telegram_gateway ops-demo
python3 -B -m telegram_gateway ops-demo --scenario duplicate
python3 -B -m telegram_gateway ops-demo --scenario crash
python3 -B -m telegram_gateway ops-demo --scenario refusal
python3 -B -m telegram_gateway ops-demo --scenario cancellation
python3 -B -m telegram_gateway ops-demo --scenario unknown
```

Each run creates temporary owner-only state and removes it on exit. Synthetic
researcher/report/verifier records exercise production parsing, projection,
atomic reply persistence and delivery-state handling with in-memory transports.
There are no model agents, real Telegram messages, real source-journal writes,
worker launches, or payments. The demo does not exercise pinned binary/process
attestation or verify a real journal chain. It is bounded to eight events,
three command-processing attempts and cooperative ten-second deadline checks;
these checks are not a host-enforced process kill.

## Dedicated binding and foreground commands

The following is a future live-smoke procedure, not a record of performed
setup. Use a fresh Ops store and bind it **before** source observation. An
already-populated, unbound store has no proven source ownership; it remains
available for offline inspection, but cannot acquire a new transport binding.
Migration preserves that evidence rather than making it eligible for delivery.
Replace all placeholders with independently verified values. The private
chat and human user IDs must be the same positive numeric ID. Use the exact
Collab workspace ID as `WORKSPACE_ID`/`--source-binding`, not a filesystem path.
Keep the same bot, credential slot, workspace and owner throughout.

Only after creating a **separate** bot in BotFather, store its token through
the hidden Keychain prompt:

```bash
python3 -m telegram_gateway bot-token-store \
  --profile ops --bot-username YourDedicatedOpsBot
```

This uses service `dev.kingdom.prediction-markets.telegram-ops-bot-token` and
the lowercase bot username account. An explicit `--keychain-account` selects a
versioned slot and must be repeated on subsequent live commands. Ops never
falls back to Research's service or `KINGDOM_TELEGRAM_BOT_TOKEN`. Credential
storage is a separate operator action, not part of previews or the demo.

Preview the complete binding against the initialized Ops database:

```bash
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-bind \
  --bot-username YourDedicatedOpsBot --bot-id BOT_NUMERIC_ID \
  --operator-user-id HUMAN_NUMERIC_ID \
  --operator-private-chat-id HUMAN_NUMERIC_ID \
  --source-binding WORKSPACE_ID
```

The preview reads no credential and contacts no provider. Repeat it with
`--apply` only after reviewing the inputs; apply verifies `getMe` before storing
the binding. A mismatch fails rather than rebinding an existing backlog.
Binding alone does not establish a safe bot profile. Keep group joins, inline,
guest, business, private-topic and bot-to-bot modes disabled, preserve privacy
mode, and configure the dedicated profile:

```bash
python3 -m telegram_gateway --db PATH_TO_OPS_DB bot-doctor \
  --profile ops --bot-username YourDedicatedOpsBot --source-binding WORKSPACE_ID
python3 -m telegram_gateway --db PATH_TO_OPS_DB bot-configure \
  --profile ops --bot-username YourDedicatedOpsBot
# Explicit provider profile changes; then inspect again with bot-doctor.
python3 -m telegram_gateway --db PATH_TO_OPS_DB bot-configure \
  --profile ops --bot-username YourDedicatedOpsBot \
  --source-binding WORKSPACE_ID --apply
```

An unconfigured profile may make doctor exit nonzero; inspect the sanitized
checks. Poll/send require the verified Ops profile, no webhook, exact bot
identity and matching active local binding. Live transport pins
`https://api.telegram.org` and rejects redirects before following them.

Send a new `/agent_status` privately **after** binding/configuration, then:

```bash
# One live batch, at most 20 updates, zero sends.
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-poll-once \
  --bot-username YourDedicatedOpsBot --source-binding WORKSPACE_ID

# Pick one reply_id from that result. Offline exact-payload preview.
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-send-once --reply-id REPLY_REF

# Copy the reviewed payload_digest and binding_revision, not guessed values.
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-send-once \
  --reply-id REPLY_REF --payload-digest REVIEWED_DIGEST \
  --binding-revision REVIEWED_REVISION --bot-username YourDedicatedOpsBot \
  --source-binding WORKSPACE_ID --apply
```

Polling persists ignored dispositions or bounded replies atomically before
acknowledging them through a later offset. Batches are sorted by valid update
ID. An idle polling epoch resets before stale high offsets could discard later
randomized IDs. A signed-32-bit offset exhaustion is reported as
`poll_offset_exhausted` before credential access; the maximum-ID reply remains
available. Do not reset or edit the database to discard the queue. Normal idle
reset after the retention interval allows later polling to recover. Incoming
message timestamps must be strictly newer than the binding/resumption second;
old backlog is not permission to disclose. Recently processed dispositions
remain deduplicated across resume, including provider/host clock skew, so a
withdrawn reply cannot be regenerated from the same retained update. Telegram
retains updates for at most 24 hours, so foreground polling is not an always-on
service or guaranteed capture.

Both provider-scoped and database-scoped owner-only locks are held across
polling or sending. They exclude cooperating processes on this host, including
same-bot consumers with different databases, not unrelated remote consumers.
The generic `run` command remains Research-only. Install no Ops LaunchAgent.

### Recovering reply references

If poll/send output is lost, replies remain discoverable without another
provider call or raw database inspection:

```bash
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-replies --state pending
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-replies --state unknown
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-replies \
  --state pending --after-reply-id NEXT_AFTER_REPLY_ID --limit 20
```

When `has_more` is true, copy `next_after_reply_id` to `--after-reply-id` for
the next page, retaining the same state filter. Omit `--state` to inspect all
states, including interrupted `inflight` attempts. Each page contains only
bounded references/state/attempt metadata, not message text, and changes no
delivery evidence. `ops-status` explicitly reports truncation and points here;
its first page is not the complete history. Use the existing send preview to
inspect the exact text of one selected reply. Reconciliation recovers an
interrupted attempt under the local locks without making a send.

### Unknown delivery and withdrawal

There is no Telegram send idempotency key. If a send times out or the process
stops after attempting it, do not resend it. Record a bounded evidence label
and the exact attempt count; reconciliation itself performs zero sends:

```bash
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-reconcile \
  --reply-id REPLY_REF --attempt-count OBSERVED_ATTEMPT \
  --outcome unknown --reconciliation-ref LOCAL_EVIDENCE_LABEL
```

A later positive observation can use `--outcome sent --receipt-ref RECEIPT_LABEL`.
`failed` requires affirmative non-delivery evidence; absence of a visible
message is only `unknown`. These are operator observations, not independent
provider proof. Original attempt and reconciliation evidence is retained.

```bash
# Immediate local withdrawal; zero network calls and no agent-process stop.
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-pause
# Preview resumption, then explicitly apply if wanted.
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-pause --resume
python3 -m telegram_gateway --db PATH_TO_OPS_DB ops-pause --resume --apply
```

Pause invalidates queued replies and fences interrupted sends. It cannot
retract messages already accepted by Telegram, erase history, or stop an agent.
A new revision/epoch on resume requires a new private command and never revives
old queued replies. These records remain local operational evidence; pause is
not deletion or a secure-erasure guarantee.

## Offline verification — 2026-09-08

- Parent-run scoped regression: **904 passed in 6.82s**, across 18 Ops,
  AgentTool adapter and affected Research/transport test files.
- All six actual `python3 -B -m telegram_gateway ops-demo` scenarios exited 0;
  expected fixture states, rollback/replay, no-resend and temporary cleanup
  receipts were inspected.
- Independent review found five binding/recovery defects; they were repaired
  and a separate verifier reported no remaining verified defects in that
  scope, with **833 tests passed** in its selected subset.
- All 28 documented CLI invocations above parsed successfully without executing
  their actions. Tests exercised mocked credentials/transports and temporary
  databases. Initialization interruptions were injected failures, not real
  power-loss testing.

Reproduce the scoped regression from the project root (do not invoke broad
root test discovery, which also includes trading scripts):

```sh
env -u DATABASE_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 \
  python3 -B -m pytest -q -p no:cacheprovider \
  tests/test_agenttool_{ops,mcp}.py \
  tests/test_telegram_ops_{service,bootstrap,cli,runtime,demo,transport}.py \
  tests/test_telegram_{bootstrap,channel_cards,channel_cli,channel_publishing,channel_transport,star_api,gateway,mvp_features,preferences,webhook}.py
```

No real Telegram delivery, credentials, Collab journal, agent execution,
payment, deployment or background installation was exercised by these checks.

## Local embedding preparation — 2026-09-08

`AgentToolOpsStore.open_existing(path, readonly=True)` provides an existing-only
opening path used by the optional MCP adapter. It does not initialize, migrate, create
metadata, or repair permissions. Inspection uses a coherent SQL read transaction
including current committed WAL state. Missing, empty, unsafe, wrong-role and v1
stores are rejected; schema changes present only in WAL and nonempty rollback
journals conservatively remain unavailable. SQLite shared-memory accounting can
change sidecars, so this is not byte-for-byte filesystem immutability.

Open, use and close the store within one thread. Explicit `readonly=False`
permits existing mutation methods, with role/permission revalidation; it does
not supply provider locks, transport readiness or authorization. Those remain
in `ops_runtime`. Filesystem checks do not isolate hostile same-account writers.

`ops_runtime.local_status(store)` now shares the existing minimized CLI status
renderer without importing the broad CLI or an external SDK. CLI output and
Research behavior remain unchanged.

Parent-run verification after these changes: **1,036 passed in 7.23s** across
the same 18-file selection, including 132 added regressions. All six actual
synthetic CLI scenarios also passed. Two independent reviews reported no
verified findings within their respective store/status scopes. Tests used
installed offline pytest and temporary fixtures, not credentials or live state.

That foundation increment added no SDK or MCP server. The subsequent adapter
is described below; its verification is separate from the foundation results.

## Optional stdio MCP adapter — 2026-09-08

[`ops_mcp.py`](ops_mcp.py) adds a thin local stdio server using the official
`mcp==2.2.0` SDK in a separate locked environment. See the
[integration guide](../integrations/telegram_ops_mcp/README.md) for exact
installation, fixed private configuration, tool schemas, registration/removal,
and recovery instructions. The existing CLI remains SDK-independent.

Default tools are `ops_status`, `ops_replies` (pending by default, at most 20)
and `ops_reply_preview`. Preview discloses the exact stored text to the MCP
client/model. Poll, send and reconciliation require explicit process-level
capabilities; every mutation-capable inventory includes local pause. Dispatch
also rejects disabled tools. Initialization, binding, migration, credential
storage, profile configuration, source observation and resume remain CLI-only.

A missing configuration still permits discovery and returns `not_configured`;
startup/discovery accesses no database, credentials, provider or Collab child.
Inspection uses the existing-only opening path above. Input frames are bounded
to 64 KiB before whole-line allocation; results are bounded and private errors
are sanitized. One worker owns each complete operation/connection. Overlapping
calls return `busy`, and cancellation does not release admission or provider
locks while a send continues. Pause cannot preempt an active send or stop agents.

Preview and consequential tools carry the documented Claude interaction marker.
The marker and MCP annotations are not universal consent enforcement; a digest
proves consistency, not human approval. Keep `send` disabled until the actual
running host demonstrates every-call approval with harmless fixtures. SDK-client
subprocess tests do not establish that UI behavior or real Telegram delivery.

### Verified adapter build and remaining connection gate

- Parent-run explicit 20-file regression: **1,225 passed in 54.53s**, including
  189 MCP tests beyond the 1,036-test foundation.
- All six actual synthetic CLI demonstrations passed with expected reply states
  and temporary cleanup. The ordinary CLI also passed the unknown-delivery demo
  in the base Python interpreter where the optional MCP SDK is absent.
- The unchanged bare launcher passed an official SDK-client roundtrip from
  `/Users/yu` with canonical temporary HOME: three default tools,
  `not_configured`, disabled send dispatch, empty stderr and unchanged HOME.
  The first bare-launcher probe correctly rejected macOS's symlinked temporary
  path; the fixture was corrected without relaxing path checks.
- Independent review and adversarial verification exposed three real defects:
  buffered stdout at shutdown, modern-protocol error echo before middleware,
  and blocked-output EOF shutdown. All were repaired and two independent
  post-repair verifiers found no remaining verified defects in their respective
  privacy/lifecycle scopes, including additional synthetic probes.
- Output now requires a pipe/socket and uses a two-second total per-frame
  deadline. Backpressure closes with exit 1 and may leave a partial frame;
  shutdown still waits for shielded gateway I/O. Six original standalone
  repro tests passed; one still fails its old exit-0 assertion. That is not
  claimed as a pass: independent probes verified bounded failure instead of
  the original hang, while the maintained tests cover the revised contract.

The official SDK is installed in the isolated environment. The registration
name was collision-checked, but the local persistent registration attempt was
**denied before execution** pending specific user authorization. The server is
not registered or connected to the native Claude session. No actual private
MCP configuration was created, and native every-call approval remains unverified.
Use the integration guide's exact local-scope command only after authorization;
then reconnect through `/mcp` or restart from `/Users/yu` as needed.

No live delivery is evidenced by these tests or this registration attempt.
Dedicated binding/source selection, safe bot-profile setup, a fresh private
command and one separately reviewed live smoke test remain separate gates.

## Remaining proof and product gates

1. A human-observed private smoke test with an established dedicated bot and
   exact recipient. No such live send is evidenced by this implementation.
2. Separately scoped real two-agent/bot collaboration, with host-owned execution,
   stop/refusal controls and verifiable work receipts, not renamed fixtures.
3. Opt-in event alerts need backpressure and their own reviewed sender; they are
   not enabled by command-reply support.
4. A paid pilot needs separately verified Stars checkout, delivery/refund/support
   and settlement. Customer payment, worker obligation and completed payout are
   different events; this Ops companion performs none of them.

Mini Apps, guest mode, groups, Communities, bot-to-bot communication, Business
mode, Managed Bots, Stars, public promotion, wallets, and trading remain
outside this bridge.
