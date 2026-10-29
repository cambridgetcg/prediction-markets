# KINGDOM Telegram community runbook

This is the operating contract for the Telegram MVP. It describes repository
code, not a claim that a bot, channel, payment service, or public community has
been launched.

## Community shape

| Surface | Purpose | Current boundary |
|---|---|---|
| **KINGDOM Dispatch** | Public, forward-safe research cards and visible status updates | Card construction, rendering, delivery gating, receipts, and reconciliation are implemented. `channel-post` is a network-free dry run unless the operator supplies `--apply`; status-successor cards remain a library workflow. |
| **KINGDOM Research Bot** | Private opt-in alerts, on-demand briefs, preferences, paper actions, scorecards, privacy, and support | Implemented for private chats. The bundled development runner loads the consent-bound preference store and paper calibration ledger; it is not a production service and Stars commerce remains disabled. |
| **KINGDOM Lab** | Future forum for sourced challenges, discussion, and postmortems | Not implemented. It must use a separate bot credential, moderation boundary, and least-privilege data store; it must not receive subscriber, payment, or Research Bot credentials. |

Telegram is the interaction and distribution layer. The canonical evidence,
signal, lifecycle, delivery, and calibration records remain local. Telegram
messages are not the system of record.

```text
official/public source artifact supplied by operator
                    |
                    v
       content-bound observation record
                    |
                    v
   S012 signal -> sealed envelope -> lifecycle review
                    |                   |
                    |              APPROVED only
                    v                   v
        prospective calibration     canonical card
                    |              /            \
                    v        Dispatch          Research Bot
          evidence-linked       |                  |
             outcome            +---- status -----+
                    |                updates
                    v
          paper scorecard

                    X wallet / signer / order API
```

## Roles and authority

- The **collector** supplies already-fetched, bounded source artifacts. The
  observation code does not fetch URLs and does not retain artifact bytes; the
  operator must preserve the referenced source material separately.
- The **research pipeline** produces a signal and sealed envelope. A digest
  detects local content drift; it does not authenticate a publisher or prove a
  statement true.
- A **reviewer** explicitly approves, rejects, revokes, or expires research.
  `APPROVED` means suitable for research distribution only.
- The **publisher** turns an approved envelope into a stable card and records
  each attempted channel delivery. It cannot grant trading authority.
- The **Research Bot** routes private commands, consent, preferences, delivery,
  paper actions, and support. A Telegram account is routing evidence, not proof
  of identity, location, eligibility, or consent to trade.
- The future **Lab moderator** manages discussion only. Discussion, polls, and
  popularity are not evidence until a source is deliberately submitted and
  recorded through the evidence path.

## User journeys

### Discover and opt in

1. A person encounters a Dispatch post or an operator-published campaign deep
   link.
2. `/start` explains the service. A campaign start adds a daily aggregate count
   without linking the campaign to a user.
3. The source-linked opt-in button may store the opaque campaign code with the
   numeric Telegram ID. A plain `/join` enables alerts without retroactive
   campaign attribution.
4. Alerts are prospective and capped at two ordinary previews per rolling
   seven days. `/leave` or `/stop` turns them off immediately.

Campaign creation is local and produces an unpublished link. Publication is a
separate human decision. Do not use Telegram Ads for this prediction-market
offer; the repository strategy excludes that promotion path.

### Read and personalize

- `/brief` or `/latest` returns the newest active, risk-passing research item.
- `/personalize` separately consents to a minimal preference profile. Alert
  consent does not silently create a personalization profile.
- `/topics` selects allowlisted topics; an empty selection means all supported
  topics.
- `/cadence realtime|daily|weekly` records a maximum-frequency preference. It
  does not override policy or the global two-per-week preview cap.
- `/watch MARKET_REF`, `/unwatch MARKET_REF`, and `/watchlist` manage bounded,
  opaque references. They do not contact a market or wallet.
- `/scorecard [DOMAIN]` reports paper calibration when a valid ledger is
  configured. It is not a return claim.

Corrections are safety messages: topic, cadence, and watchlist preferences do
not suppress an owed correction. If a preference profile is absent, withdrawn,
deleted, or awaiting notice reconfirmation, its filters are not applied; the
separate core alert consent still decides whether ordinary alerts may be sent.

### Paper research and exit

- `/paper SIGNAL_ID [USD]` records a simulation for an entitled user; it sends
  no order.
- `/settings` or `/status` shows access, alerts, preferences, and the absent
  wallet/execution capability. `/terms` shows the product boundary.
- `/plans`, `/subscribe`, and `/cancel` expose the subscription workflow, but
  the bundled runner keeps commerce disabled and will not open a purchase.
- `/trade`, `/execute`, `/buy`, and `/sell` return
  `LIVE_EXECUTION_DISABLED`.
- `/privacy` describes retained local data.
- `/leave` and `/stop` erase the personalization profile, stop new alerts, and
  retain a minimal numeric-ID/event watermark so delayed updates cannot reverse
  the choice.
- `/delete_me` purges linkable nonfinancial state and leaves the minimum
  no-contact marker. Finance or open-support evidence may remain only while an
  applicable retention hold blocks deletion; WAL files and backups require
  separate lifecycle maintenance.
- `/support` or `/paysupport` opens a support case. Paid operation is not enabled
  by the bundled runner.

The BotFather command menu should expose the private command set only. The
service may accept aliases such as `/latest`, `/status`, and `/support` in
addition to the displayed commands.

## Evidence-to-publication procedure

1. **Capture evidence.** Fetch outside this gateway, archive the exact artifact,
   then run `evidence-record`. The local observation binds source metadata to
   the supplied bytes and emits an `obs-...` ID; it does not retain those bytes,
   authenticate the source, or prove the claim.
2. **Create the signal.** Propagate observation IDs and a resolution-rule
   reference into the S012 record. Importing a signal cannot make it approved.
3. **Review lifecycle.** Use the S012 review commands to append a valid
   `PENDING -> APPROVED | REJECTED | EXPIRED` event. Later, an approved signal
   may become `REVOKED` or `EXPIRED`; the sealed envelope is never rewritten.
4. **Build the card.** A root Dispatch card requires an intact, unexpired
   envelope, a matching `APPROVED` event, at least one linked source, and a
   resolution-rule reference. URLs are syntax/host checked, not authenticated.
5. **Prepare and publish deliberately.** `channel-post` is side-effect free by
   default. `--apply` verifies the publisher bot, resolves the target with
   Telegram, requires its actual type to be `channel`, sends to the resolved
   numeric ID, and records a stable publication ID, card/text digests, attempt
   state, and Telegram message ID. A campaign CTA also requires the Research
   Bot username previously established by authenticated `bot-doctor`; it cannot
   be redirected by supplying another syntactically valid username. Never
   blindly retry `pending` or `unknown`; reconcile the provider outcome first.
6. **Append changes.** Publish a successor card for `AMENDED`, `WITHDRAWN`,
   `EXPIRED`, or `RESOLVED`. A status card links to its predecessor and does not
   repeat superseded research. `RESOLVED` requires source evidence. Publish it
   as a reply to the preceding Dispatch message when that receipt is known.
7. **Correct private delivery.** A lifecycle revocation queues a correction for
   prior private recipients whose original delivery was `sent` or `unknown`,
   unless they withdrew, deleted data, or blocked the bot. Dispatch successor
   publication remains a separate, deliberate publisher operation.

Never edit an old card to conceal a mistake. Preserve its ID and append the
correction, withdrawal, expiry, or resolution.

The source-link file is bounded JSON. Every observation reference must already
be sealed into the signal; links are HTTPS-validated but not authenticated.

```json
[
  {
    "observation_ref": "obs-REPLACE_WITH_CONTENT_ADDRESSED_ID",
    "label": "Primary resolution source",
    "url": "https://primary.example/source",
    "observed_at": "2026-09-03T12:00:00Z",
    "is_primary": true
  }
]
```

```bash
# Default: validate, render, and print the card/post with zero network calls.
python3 -m telegram_gateway channel-post SIGNAL_ID \
  --channel @KingdomDispatch \
  --source-links /owner/private/source-links.json \
  --market-url https://polymarket.com/event/REPLACE_ME \
  --published-at 2026-09-03T12:05:00Z \
  --campaign-code ACTIVE_CAMPAIGN_CODE \
  --research-bot-username KingdomResearchBot

# External send: repeat the reviewed command and add explicit authority.
python3 -m telegram_gateway channel-post SIGNAL_ID \
  --channel @KingdomDispatch \
  --source-links /owner/private/source-links.json \
  --market-url https://polymarket.com/event/REPLACE_ME \
  --published-at 2026-09-03T12:05:00Z \
  --campaign-code ACTIVE_CAMPAIGN_CODE \
  --research-bot-username KingdomResearchBot \
  --apply --token-source keychain --bot-username KingdomPublisherBot

python3 -m telegram_gateway channel-receipt PUBLICATION_ID

# Only after an independent check of an ambiguous/pending provider outcome:
python3 -m telegram_gateway channel-reconcile PUBLICATION_ID \
  --reconciliation-ref operator-check-20260903 --not-sent
```

`channel-reconcile` records the operator/provider check locally; it does not
perform that check. Use `--sent-message-id ID` when the post exists. Retry a
known failed publication with `--retry-failed` only after confirming it was not
sent, using the same immutable card inputs.

The paired campaign options are optional, but when supplied the code must be
active in this gateway. The canonical Research Bot link is included in the
post text digest and publication identity; changing it is a different
publication and cannot silently replace a prior card receipt. Opening the bot
records only the campaign's aggregate start event. It does not opt a person in.

## Prospective calibration procedure

Calibration uses an owner-private, append-only, hash-chained JSONL ledger.

```bash
# The signal must still be active and must carry observation IDs and rules.
python3 -m telegram_gateway forecast-register SIGNAL_ID \
  --probability-yes 0.60

# After objective resolution, cite the archived evidence and its content hash.
python3 -m telegram_gateway outcome-record SIGNAL_ID \
  --outcome YES \
  --resolved-at 2026-09-30T12:00:00Z \
  --resolution-evidence-ref OBSERVATION_ID \
  --resolution-evidence-digest sha256:REPLACE_WITH_64_LOWERCASE_HEX

python3 -m telegram_gateway calibration-verify
python3 -m telegram_gateway scorecard
```

- Register an explicit probability of the binary **YES** outcome before the
  outcome occurs. Confidence and target-price fields are never converted into
  that probability.
- By default, the sealed outcome-token quote becomes the same-time market
  baseline, converted to YES probability when the quoted token is NO. An
  explicit baseline must link to an observation already in the signal; use
  `--no-market-baseline` when none was captured.
- Resolution appends Brier score and natural-log loss for the forecast and,
  when present, the market baseline. Lower scores are better; positive reported
  advantage means the registered forecast scored better than the baseline.
- Ledger hashes and checkpoints detect local drift and truncation when anchored
  externally. They do not prove authorship, source truth, or trusted time.

Do not market performance from a handful of examples. The current strategy's
internal standard is at least 200 resolved preregistered forecasts across
multiple regimes and three months, followed by cost, slippage, drawdown,
abstention, revision, and dispute analysis.

## BotFather and Telegram administration

Use a fresh bot for the Research Bot.

1. Generate the offline plan with `bot-plan`; open the verified `@BotFather`
   conversation only through the supplied helper or Telegram itself. Creation
   remains a visible human-confirmed action.
2. Never put the BotFather token in chat, argv, a project file, shell startup,
   or documentation. Store it through `bot-token-store`, which prompts directly
   into a bot-specific macOS Keychain account and refuses overwrite.
3. In BotFather, disable group joins and keep Group Privacy Mode enabled. Leave
   inline, guest, business, Mini App, private-topic, join-request, Bot-to-Bot,
   and Bot Management modes off for this bot.
4. Publish the completed privacy policy at a stable HTTPS URL and register it
   in BotFather. The repository template is not publishable as-is.
5. Run `bot-doctor`, inspect every manual check, preview `bot-configure`, then
   use `bot-configure --apply`. Rerun the doctor after any ambiguous result; do
   not rotate or retry blindly.
6. Run the first command smoke test with `--once --control-only`. This processes
   private commands while pausing ingestion and all ordinary/correction
   broadcasts.
7. When Dispatch is ready, add only the dedicated publisher identity and grant
   only the permission needed to post. `channel-post --apply` verifies the
   target is a channel, but the repository does not configure or certify its
   admin permissions. Do not make the private Research Bot a group moderator.
8. Give the future Lab its own bot, Keychain account, storage, and narrowly
   scoped moderation permissions. Do not reuse Research Bot or publisher
   credentials.

The long-poll runner must be the sole update consumer for its token. It refuses
a configured Stars price and requires no webhook. A future production webhook
listener replaces polling; it does not run beside it.

## Standing safety and community rules

- Paper research only: no wallet, private key, signer, CLOB credential, token
  allowance, custody, live order, VPN bypass, or inferred trading consent.
- No Telegram scraping. The implemented collectors accept explicit artifacts,
  S012 feeds, and bounded market snapshots; Lab/channel history must not become
  an automatic research or model-training corpus.
- No guaranteed truth, identity, expertise, returns, or “alpha” claims. Hashes,
  credentials, subscriptions, model outputs, votes, and roles do not establish
  those claims.
- Keep evidence and dissent visible. Credit a useful correction; do not punish
  opt-out, disagreement, or a well-supported challenge.
- Do not rank people by trade volume, loss, spend, or engagement streaks.
- Do not paywall corrections, privacy information, deletion, or support.
- Never publish exact small-cohort promotion diagnostics. The default report
  reduces disclosure but does not guarantee anonymity.

## Staged launch checklist

### 0 — Offline evidence and paper loop

- [ ] Run the test suite and `status`; resolve every integrity/quarantine issue.
- [ ] Record and separately archive source and resolution-rule artifacts.
- [ ] Preregister forecasts before seeing outcomes; verify the calibration
      chain and produce an internal scorecard.
- [ ] Dry-run `channel-post` and inspect root/status cards offline. Confirm every
      card says information-only, paper-only, no wallet, and no execution.

### 1 — Private operator smoke test

- [ ] Create and verify a fresh Research Bot using the least-privilege steps.
- [ ] Complete and publish the privacy policy.
- [ ] Run one `--control-only` poll and test `/privacy`, `/join`, `/leave`,
      `/personalize`, preference commands, `/scorecard`, and `/delete_me` with
      test identities.
- [ ] If continuous private-command response is wanted, load the documented
      per-user LaunchAgent in `--control-only` mode. Confirm its owner-only logs,
      sole-consumer lock, and stable PID; stop it before manual polling or
      maintenance.
- [ ] Confirm that live-trade commands fail closed and no alert was broadcast.

### 2 — Closed free alpha

- [ ] Create one allowlisted campaign link; keep it unpublished until reviewed.
- [ ] Invite a small, known test cohort manually and exercise opt-in/opt-out.
- [ ] Use only scheduled, objectively resolvable paper markets with complete
      provenance; the strategy recommends 10–20 macro-policy markets first.
- [ ] Review delivery receipts, unknown outcomes, revocations, corrections,
      preferences, and deletion behavior after every cycle.

### 3 — Dispatch pilot

- [ ] Create the channel manually and grant posting-only administration.
- [ ] Dry-run the exact `channel-post` inputs; only then repeat with `--apply`
      and the dedicated publisher credential.
- [ ] Inspect the publication with `channel-receipt`. Exercise `channel-reconcile`
      for simulated pending/unknown outcomes before relying on manual recovery.
- [ ] Verify amendment, withdrawal, expiry, resolution, reply lineage, and
      duplicate suppression through the status-card library workflow. Do not
      call Dispatch correction operations complete until that successor path
      has a reviewed operator command or worker.

### 4 — Lab/forum, later

- [ ] Establish separate credentials, storage, moderation rules, human
      escalation, retention, deletion, and abuse response.
- [ ] Treat community submissions as untrusted until deliberately archived and
      reviewed; do not auto-promote chat consensus into a signal.
- [ ] Link the Lab only after Dispatch correction practice is reliable.

### 5 — Paid or production service, not yet

- [ ] Deploy owned HTTPS ingress, durable serialized update handling,
      monitoring, rollback, encrypted backup/restore, and deletion verification.
- [ ] Complete Stars reconciliation, cancellation, refund, `/paysupport`, terms,
      privacy, consumer, marketing, jurisdiction, and tax review.
- [ ] Meet the prospective calibration standard before making any performance
      claim. A subscription must never imply authority to trade.

See [README.md](README.md), [MARKET_STRATEGY.md](MARKET_STRATEGY.md), and
[PRIVACY_POLICY_TEMPLATE.md](PRIVACY_POLICY_TEMPLATE.md) for the underlying
implementation and launch boundaries.
