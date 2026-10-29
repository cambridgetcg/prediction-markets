# Private Telegram Ops MCP

> **Status drift observed 2026-10-28** (an added note; nothing below was changed).
> `@KingdomAgentOpsBot` (bot ID 8825848711) belongs to `~/Desktop/telegram-mcp`,
> the Claude MCP server `telegram-ops`, which only `~/.local/bin/claude-pager`
> hosts. This adapter (`kingdom-telegram-ops`) and `ops_runtime` must bind a
> **different**, dedicated bot that Yu creates in BotFather.
> Their locks (`~/.kingdom-telegram-ops-locks/` and the database run lock) do
> **not** exclude telegram-mcp's per-bot lock, so local locking cannot stop two
> consumers of one token.
> A login-keychain slot exists: service
> `dev.kingdom.prediction-markets.telegram-ops-bot-token`, account
> `kingdomagentopsbot`, created 2026-09-08 (existence observed; value never
> read). **Do not use it to bind 8825848711.** Yu decides which copy of that
> token is canonical and renames the other rather than deleting it.
> Owner registry: `~/hermes-toolkit-lab/docs/telegram-owners-2026-10-28.md`.

A local, foreground stdio adapter over [`ops_runtime`](../../telegram_gateway/ops_runtime.py), not a general Telegram client or agent dispatcher. The SDK is optional and isolated here; the existing gateway CLI needs no MCP SDK.

Default tools inspect an **existing** dedicated Ops database. No configuration means discovery still works and `ops_status` returns `not_configured`. Connecting does not initialize a database, inspect a source journal, load a credential, poll Telegram, or send a message. This integration installs no HTTP listener, daemon, timer, or background Ops service.

## Install and launch

Use an existing Python 3.12+ interpreter and install the locked dependencies explicitly. Do not install on every MCP connection:

```sh
cd ~/Desktop/prediction-markets
uv sync --project integrations/telegram_ops_mcp --locked --no-python-downloads
```

The dependency-only project pins the official PyPI `mcp==2.2.0` SDK and locks its dependencies in `uv.lock`. Its `.venv` is separate from Research. The launcher imports only the repository beside it; it does not package runtime databases or private configuration. It rejects command-line arguments and does not accept a fixture mode or environment-based authority overrides.

The absolute launch command, independent of working directory:

```sh
/Users/yu/Desktop/prediction-markets/integrations/telegram_ops_mcp/.venv/bin/python -I -B \
  /Users/yu/Desktop/prediction-markets/integrations/telegram_ops_mcp/run.py
```

Stdin/stdout carry MCP frames, not an interactive shell. Do not paste credentials into them.

## Fixed private configuration

The process reads `~/.config/kingdom-telegram-ops/mcp.json` once at startup. Restart/reconnect after an intentional configuration change. No tool can rewrite or select this configuration.

- Parent directory: owned by the current user, mode `0700`.
- File: regular, owned by the current user, mode `0600`, no hard links or symlink ancestry, at most 8 KiB.
- Missing file or `{}`: unconfigured, default inspection inventory only.
- Unsafe, malformed, duplicate-key or unknown-field configuration: closed `invalid_config` result; no implicit repair.
- **Never put a token in this file.** Do not copy private configuration into the repository.

`config.example.json` intentionally contains `{}`. After separately initializing a dedicated Ops store, a minimal inspection configuration is:

```json
{
  "db_path": "/absolute/path/to/dedicated-ops/ops.db"
}
```

`db_path` must be absolute, with no `..` components. The existing store and its directory must meet the Ops owner-only checks. Missing, empty, v1, wrong-role, mixed or unsafe stores are unavailable; MCP never initializes, migrates, changes journal mode or repairs permissions. Inspection reads a coherent current WAL-visible SQL snapshot. SQLite may update/create shared-memory sidecars: read-only here is **SQL read-only**, not byte-for-byte filesystem immutability. WAL-only schema initialization and nonempty rollback journals are conservatively rejected.

Additional fields are operator-controlled:

| Field | Meaning |
|---|---|
| `expected_bot_username` | Dedicated bot username, without `@`; live runtime verifies it with `getMe` |
| `source_binding` | Exact Collab workspace ID already stored in the Ops binding; not a path |
| `keychain_account_name` | Exact lowercase dedicated Ops slot, including a versioned/custom slot when used |
| `capabilities` | Explicit list drawn from `poll`, `send`, `pause`, `reconcile`; defaults to `[]` |

Poll/send require all three binding fields. Numeric bot and sole private recipient IDs come only from the existing durable binding, never tool arguments. Offline checks compare the configured source and complete dedicated credential reference; a Keychain slot name does not authenticate the bot's current username. Live identity verification remains in the runtime. There is no Research credential or environment-token fallback.

Keep capabilities absent while live setup or host interaction verification is incomplete. Adding `send` makes the sending handler available; it is not proof of consent or a host approval check.

## Exact tool surface

| Tool | Exposure and effect |
|---|---|
| `ops_status()` | Default; minimized local state, provider identity not checked by this inspection |
| `ops_replies(state="pending", limit=20, after_reply_id=null)` | Default; metadata only, limit 1–20 |
| `ops_reply_preview(reply_id)` | Default; discloses one exact stored reply to the MCP client/model |
| `ops_poll_once()` | `poll`; one batch of at most 20 updates, timeout 0, persist dispositions/replies, zero sends |
| `ops_reply_send(reply_id, payload_digest, binding_revision)` | `send`; one exact queued reply attempt, no automatic retry |
| `ops_pause()` | Any mutation capability, including `pause` alone; invalidate pending replies locally |
| `ops_reconcile(reply_id, attempt_count, outcome, reconciliation_ref, receipt_ref=null)` | `reconcile`; append supplied delivery evidence, never resend |

Reply states: `pending`, `inflight`, `sent`, `failed`, `unknown`, `invalidated`, `all`. Retain the same state filter while paging with `next_after_reply_id`. Unlike the CLI's all-state default, MCP defaults to pending. Reconciliation requires a receipt label for `sent` and forbids it for other outcomes.

Tool schemas and dispatch share strict validation: no extra arguments, bool-as-int coercion, paths, recipients, arbitrary message text, tokens, provider URLs, clock overrides or `approved=true` flags. Disabled tools are rejected even if called without discovery.

Initialization, migration, binding, token storage, bot configuration, source observation and resume remain CLI-only. See the [Ops runbook](../../telegram_gateway/AGENTOOL_OPS.md#dedicated-binding-and-foreground-commands). There are no raw updates, history/file tools, personal-account sessions, worker execution, payments or trading.

## Disclosure, approval and stopping

Preview sends the complete stored reply text to the MCP client/model, where normal host/provider retention applies. A matching digest/revision proves payload consistency, **not human approval**.

Preview and all consequential tools advertise `_meta["anthropic/requiresUserInteraction"] = true`. Standard MCP annotations are hints. Current [Claude Code documentation](https://code.claude.com/docs/en/mcp) describes an every-call interaction requirement for that marker on supported hosts; other clients and older versions can ignore it. **Demonstrate the actual running host's approval UI with harmless fixtures before enabling live send.** A passing SDK-client test or installed version number is not that demonstration. Use separately reviewed CLI delivery when the host cannot establish this boundary. Do not add broad auto-allow rules.

One gateway operation runs at a time. Overlapping calls return `busy` immediately rather than queueing mutations; protocol controls remain responsive. The SQLite connection, operation and admission slot remain together in one worker thread. Cancellation or a client timeout does not abandon an in-progress send or release its locks early. Normal provider I/O has finite timeouts; Python threads cannot be forcibly stopped safely, and host process termination can interrupt delivery.

Pause cannot preempt an already-running operation, retract accepted Telegram messages, erase provider history or stop agents. Local locks coordinate cooperating host processes, not hostile same-account writers or unrelated remote consumers. Keep one update consumer for the dedicated bot.

A timeout, cancellation or lost client response is **not permission to retry sending**. Inspect `inflight`/`unknown` metadata and reconcile the exact attempt. Reconciliation is a supplied observation, not independent provider verification; it preserves original evidence. Telegram has no native send idempotency key. A fresh post-resumption private command is required instead of reviving old replies.

Input frames are limited to 64 KiB before complete-line allocation. Oversized or invalid UTF-8 input closes the transport. Results and outbound envelopes are bounded; an oversized preview is rejected, never truncated. Outbound error sanitization covers both legacy and modern SDK routing, including errors raised before tool middleware. Ordinary buffered stdout stays diverted even during interpreter shutdown; stderr suppresses private diagnostics.

The output endpoint must be a pipe or socket, as supplied by an MCP client; a terminal or regular-file redirection is rejected. Nonblocking partial writes share a **two-second total deadline per frame**. A stalled/broken output pipe closes with exit 1 rather than hanging or claiming successful output. Already-written partial frames cannot be retracted. Shutdown still waits for any admitted shielded gateway operation to finish; the output deadline is not a two-second kill deadline for a send. Inspect readiness through tools, not raw debug logging.

## Claude Code registration

Local status on 2026-09-08: installed and SDK-tested, **not registered**. The name was collision-checked; the persistent local registration was denied before execution pending specific user authorization. No actual private configuration was created. Native session connection and every-call approval remain unverified. The commands below are a procedure to use after explicit authorization, not a claim they ran.

First check that `kingdom-telegram-ops` is not already registered in the intended scope. These commands are local to **`/Users/yu`**, not the additional repository working directory:

```sh
cd /Users/yu
/Users/yu/.local/bin/claude mcp get kingdom-telegram-ops
# Add only if absent; do not overwrite another registration.
/Users/yu/.local/bin/claude mcp add --transport stdio --scope local kingdom-telegram-ops -- \
  /Users/yu/Desktop/prediction-markets/integrations/telegram_ops_mcp/.venv/bin/python -I -B \
  /Users/yu/Desktop/prediction-markets/integrations/telegram_ops_mcp/run.py
/Users/yu/.local/bin/claude mcp get kingdom-telegram-ops
```

In Claude Code, use `/mcp` to connect/reconnect this server if available. Otherwise restart Claude from `/Users/yu`. Registration does not inject tools into every already-running session. Confirm the exact three default tools and call `ops_status` while configuration is absent. Installed, registered, SDK-connected, native-host-connected, approval-verified and live-ready are separate claims.

To remove this one registration, without deleting the database or credential:

```sh
cd /Users/yu
/Users/yu/.local/bin/claude mcp remove --scope local kingdom-telegram-ops
```

Disconnect the active session too. Removing a registration does not retract messages or cancel a send already in flight.

## Offline verification

From the repository root, use the isolated environment and explicit test files only; broad root discovery includes unrelated trading scripts:

```sh
env -u DATABASE_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 \
  integrations/telegram_ops_mcp/.venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_agenttool_{ops,mcp}.py \
  tests/test_telegram_ops_{service,bootstrap,cli,runtime,demo,transport,mcp,mcp_stdio}.py \
  tests/test_telegram_{bootstrap,channel_cards,channel_cli,channel_publishing,channel_transport,star_api,gateway,mvp_features,preferences,webhook}.py
```

The subprocess suite uses the official SDK client and unchanged real launcher via an internal test bootstrap that installs child-local effect guards. Fixtures cover missing/configured discovery, inspection, preview, strict errors, overload, cancellation, deadlines, frame bounds, EOF and cleanup. This is not native Claude approval verification. Live-capable handlers use internal credential-free test dependencies, with no production fixture selector.

Parent verification on 2026-09-08: **1,225 passed in 54.53s**, including 189 new MCP regressions beyond the 1,036-test foundation. All six actual synthetic CLI demonstrations passed with expected states and temporary cleanup. The ordinary CLI also ran successfully in the base interpreter where `mcp` is absent. A separate bare-launcher official SDK roundtrip, without the guard bootstrap, passed with a canonical empty temporary HOME: exact three-tool inventory, `not_configured`, disabled send dispatch, empty stderr and unchanged HOME. The initial bare-launcher probe used macOS's symlinked temporary path and was correctly rejected; the fixture path was corrected, not the safety check.

Independent review initially exposed three real gaps despite passing tests: buffered stdout at shutdown, private modern-protocol errors, and blocked-output EOF. Repairs add raw post-exit drain checks, both protocol eras, partial-write/deadline and active-send lock-retention tests. Output timeout intentionally exits 1; the older standalone EOF reproducer's exit-0 assertion is not the repaired contract. Independent post-repair review and local registration are recorded separately in the Ops runbook.

The [Ops runbook](../../telegram_gateway/AGENTOOL_OPS.md) records verification milestones and the separate live-smoke procedure. Synthetic demos are not real agent collaboration or earnings.
