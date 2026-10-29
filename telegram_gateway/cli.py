"""Command-line entry point for the local KINGDOM Telegram gateway."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sqlite3
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .bootstrap import (
    DEFAULT_BOT_NAME,
    KEYCHAIN_SERVICE,
    OPS_KEYCHAIN_SERVICE,
    bot_profile,
    build_botfather_plan,
    build_managed_bot_link,
    configure_bot,
    copy_botfather_value,
    desired_commands,
    inspect_bot,
    keychain_account,
    open_botfather,
    prepare_runtime,
    resolve_token,
    store_token_interactively,
    validate_bot_username,
    verify_identity,
)
from .calibration import CalibrationLedger
from .channel_cards import build_research_card
from .channel_publishing import (
    ChannelPublicationLedger,
    ChannelPublisher,
    ChannelPublisherConfig,
    ChannelPublishingError,
    prepare_channel_post,
)
from .formatting import render_public_signal, render_research_signal
from .importer import ImportFailure, import_s012_jsonl
from .lifecycle import LifecycleImportFailure, import_s012_lifecycle_jsonl
from .market_candidates import (
    MAX_PAYLOAD_BYTES,
    CandidateInputError,
    build_candidate_report,
    candidate_report_json,
)
from .observations import (
    MAX_ARTIFACT_BYTES,
    ObservationLedger,
    build_observation,
)
from .policy import Action, PolicyEngine
from .preferences import DEFAULT_PREFERENCE_NOTICE_VERSION, PreferenceStore
from .promotion import (
    CAMPAIGN_KINDS,
    DEFAULT_PROMOTION_NOTICE_VERSION,
    build_campaign_link,
    generate_campaign_code,
    validate_notice_version,
)
from .reconciliation import StarReconciliationError, reconcile_star_transactions
from .service import BotService, ServiceConfig
from .store import GatewayStore
from .telegram_api import TelegramAPI, TelegramError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = Path(__file__).resolve().parent / "var" / "gateway.db"
DEFAULT_SIGNALS = PROJECT_ROOT / "data" / "s012" / "signals.jsonl"
DEFAULT_LIFECYCLE = PROJECT_ROOT / "data" / "s012" / "signal-lifecycle.jsonl"
DEFAULT_CALIBRATION_LEDGER = Path(__file__).resolve().parent / "var" / "calibration.jsonl"
DEFAULT_CHANNEL_LEDGER = (
    Path(__file__).resolve().parent / "var" / "channel-publications.db"
)
DEFAULT_OPS_DB = Path(__file__).resolve().parent / "var" / "ops-bot.db"
MAX_CHANNEL_SOURCE_LINK_BYTES = 64 * 1024

PROMOTION_PRIVACY_THRESHOLD = 5
PROMOTION_SUMMARY_BEHAVIOR_FIELDS = (
    "start_events",
    "attributed_recipients",
    "alerts_subscribed",
    "alerts_unsubscribed",
    "alerts_need_reconfirmation",
    "alert_consent_events",
)
PROMOTION_CAMPAIGN_BEHAVIOR_FIELDS = (
    "start_events",
    "attributed_recipients",
    "ever_opted_in",
    "ever_opted_out",
    "currently_subscribed",
    "currently_unsubscribed",
    "needs_reconfirmation",
    "delivered_recipients",
    "signals_sent",
    "signals_unknown",
    "paper_actors",
    "paper_actions",
)


def _promotion_count_bucket(value: int) -> int | str:
    if value == 0:
        return 0
    lower = value - value % PROMOTION_PRIVACY_THRESHOLD
    return f"{lower}-{lower + PROMOTION_PRIVACY_THRESHOLD - 1}"


class _OpsArgumentError(ValueError):
    pass


class _OpsArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse's default error text echoes user input, which can include
        # mistaken credentials or private paths. Ops diagnostics are closed.
        raise _OpsArgumentError("invalid Ops command arguments")


def build_parser(*, sanitize_ops_errors: bool = False) -> argparse.ArgumentParser:
    parser_type = _OpsArgumentParser if sanitize_ops_errors else argparse.ArgumentParser
    parser = parser_type(
        prog="python -m telegram_gateway",
        description="Data-only Telegram research distribution gateway",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("KINGDOM_TELEGRAM_DB", DEFAULT_DB)),
        help="private gateway SQLite path",
    )
    parser.add_argument(
        "--calibration-ledger",
        type=Path,
        default=Path(
            os.environ.get(
                "KINGDOM_CALIBRATION_LEDGER", DEFAULT_CALIBRATION_LEDGER
            )
        ),
        help="owner-private append-only paper forecast ledger",
    )
    parser.add_argument(
        "--channel-ledger",
        type=Path,
        default=Path(
            os.environ.get("KINGDOM_CHANNEL_LEDGER", DEFAULT_CHANNEL_LEDGER)
        ),
        help="owner-private Telegram channel publication ledger",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bot_plan = sub.add_parser(
        "bot-plan",
        help="prepare the human-confirmed BotFather bootstrap without a token",
    )
    bot_plan.add_argument("--bot-username", required=True)
    bot_plan.add_argument(
        "--profile", choices=("research", "ops"), default="research"
    )
    bot_plan.add_argument("--privacy-url")
    bot_plan.add_argument(
        "--open-botfather",
        action="store_true",
        help="open the verified @BotFather chat; never sends a message",
    )
    bot_plan.add_argument(
        "--copy",
        choices=("newbot", "name", "username", "commands"),
        help="copy one non-secret BotFather input to the macOS clipboard",
    )

    token_store = sub.add_parser(
        "bot-token-store",
        help="prompt for a BotFather token directly into macOS Keychain",
    )
    token_store.add_argument("--bot-username", required=True)
    token_store.add_argument("--profile", choices=("research", "ops"), default="research")
    token_store.add_argument(
        "--keychain-account",
        help="new lowercase Keychain slot; defaults to the lowercase bot username",
    )

    bot_doctor = sub.add_parser(
        "bot-doctor",
        help="verify bot identity, configuration, and long-poll readiness",
    )
    bot_doctor.add_argument("--bot-username", required=True)
    bot_doctor.add_argument(
        "--profile", choices=("research", "ops"), default="research"
    )
    bot_doctor.add_argument(
        "--token-source",
        choices=("keychain", "environment"),
        default="keychain",
    )
    bot_doctor.add_argument(
        "--keychain-account",
        help="versioned Keychain slot; defaults to the lowercase bot username",
    )

    bot_doctor.add_argument("--source-binding", help="exact opaque Ops source label")
    bot_configure = sub.add_parser(
        "bot-configure",
        help="preview or apply the fixed KINGDOM Bot API profile",
    )
    bot_configure.add_argument("--bot-username", required=True)
    bot_configure.add_argument(
        "--profile", choices=("research", "ops"), default="research"
    )
    bot_configure.add_argument(
        "--token-source",
        choices=("keychain", "environment"),
        default="keychain",
    )
    bot_configure.add_argument(
        "--keychain-account",
        help="versioned Keychain slot; defaults to the lowercase bot username",
    )
    bot_configure.add_argument(
        "--apply",
        action="store_true",
        help="mutate the verified bot profile; otherwise this is an offline preview",
    )

    bot_configure.add_argument("--source-binding", help="exact opaque Ops source label")
    bot_campaign = sub.add_parser(
        "bot-campaign",
        help="create or reuse one verified, unpublished bootstrap campaign link",
    )
    bot_campaign.add_argument("--bot-username", required=True)
    bot_campaign.add_argument(
        "--token-source",
        choices=("keychain", "environment"),
        default="keychain",
    )
    bot_campaign.add_argument(
        "--keychain-account",
        help="versioned Keychain slot; defaults to the lowercase bot username",
    )

    managed_link = sub.add_parser(
        "managed-bot-link",
        help="build a user-confirmed Telegram Managed Bot creation link",
    )
    managed_link.add_argument("--manager-username", required=True)
    managed_link.add_argument("--bot-username", required=True)
    managed_link.add_argument("--name", default=DEFAULT_BOT_NAME)

    sub.add_parser("init", help="create the private local database")

    sub.add_parser(
        "ops-init",
        help=(
            "initialize a separate owner-only AgentTool Ops projection database; "
            "requires an explicit non-Research --db path"
        ),
    )
    sub.add_parser(
        "ops-status",
        help=(
            "inspect a previously initialized local AgentTool Ops projection; "
            "performs no AgentTool or Telegram call"
        ),
    )
    ops_replies = sub.add_parser(
        "ops-replies", help="page local reply references and states, without text or provider calls"
    )
    ops_replies.add_argument("--state", choices=("pending", "inflight", "sent", "failed", "unknown", "invalidated"))
    ops_replies.add_argument("--after-reply-id", help="last reference from the preceding page")
    ops_replies.add_argument("--limit", type=int, default=20, help="page size (1-20)")
    ops_watch = sub.add_parser(
        "ops-watch-once",
        help=(
            "run one explicit pinned read-only AgentTool MCP observation; "
            "never contacts Telegram"
        ),
    )
    ops_watch.add_argument(
        "--workspace-id",
        required=True,
        help="exact AgentTool workspace ID expected from the local journal",
    )
    ops_watch.add_argument(
        "--collab-db",
        type=Path,
        required=True,
        help="existing owner-only AgentTool Collab SQLite database",
    )
    ops_watch.add_argument(
        "--event-limit",
        type=int,
        default=50,
        help="maximum contiguous events to stage in this invocation (1-50)",
    )
    ops_watch.add_argument(
        "--seed-current-head",
        action="store_true",
        help=(
            "on an unseeded Ops store, record the fully verified current head; "
            "no historical events are imported"
        ),
    )

    ops_migrate = sub.add_parser("ops-migrate", help="preview exact v1 to v2 migration offline")
    ops_migrate.add_argument("--apply", action="store_true")
    ops_bind = sub.add_parser("ops-bind", help="preview numeric Ops binding; verify only with --apply")
    ops_bind.add_argument("--bot-username", required=True)
    ops_bind.add_argument("--bot-id", type=int, required=True)
    ops_bind.add_argument("--operator-user-id", type=int, required=True)
    ops_bind.add_argument("--operator-private-chat-id", type=int, required=True)
    ops_bind.add_argument("--source-binding", required=True, help="opaque source label, never a path")
    ops_bind.add_argument("--keychain-account")
    ops_bind.add_argument("--apply", action="store_true")
    ops_poll = sub.add_parser("ops-poll-once", help="one live max-20 batch; stage replies without sending")
    ops_poll.add_argument("--bot-username", required=True)
    ops_poll.add_argument("--source-binding", required=True)
    ops_poll.add_argument("--keychain-account")
    ops_poll.add_argument("--poll-timeout", type=int, default=0)
    ops_send = sub.add_parser("ops-send-once", help="preview one reply; explicitly apply its exact digest/revision")
    ops_send.add_argument("--reply-id", required=True)
    ops_send.add_argument("--apply", action="store_true")
    ops_send.add_argument("--payload-digest")
    ops_send.add_argument("--binding-revision", type=int)
    ops_send.add_argument("--bot-username")
    ops_send.add_argument("--source-binding")
    ops_send.add_argument("--keychain-account")
    ops_reconcile = sub.add_parser("ops-reconcile", help="record delivery observation locally; never resend")
    ops_reconcile.add_argument("--reply-id", required=True)
    ops_reconcile.add_argument("--attempt-count", type=int, required=True)
    ops_reconcile.add_argument("--outcome", choices=("sent", "failed", "unknown"), required=True,
                               help="absence of a visible message means unknown, not failed")
    ops_reconcile.add_argument("--reconciliation-ref", required=True, help="nonempty opaque evidence label")
    ops_reconcile.add_argument("--receipt-ref", help="required only for observed sent outcome")
    ops_pause = sub.add_parser("ops-pause", help="local withdrawal; does not stop agents or erase Telegram history")
    ops_pause.add_argument("--resume", action="store_true", help="preview same-owner resume with a new command cutoff")
    ops_pause.add_argument("--apply", action="store_true", help="explicitly apply --resume; never replays old replies")
    ops_demo = sub.add_parser("ops-demo", help="isolated synthetic demo; no live mode")
    ops_demo.add_argument("--scenario", default="happy",
                          choices=("happy", "duplicate", "crash", "refusal", "cancellation", "unknown"))

    ingest = sub.add_parser("ingest", help="import new S012 JSONL records locally")
    ingest.add_argument("--source", type=Path, default=DEFAULT_SIGNALS)
    ingest.add_argument(
        "--backfill",
        action="store_true",
        help="explicitly import existing history; never broadcasts by itself",
    )

    ingest_lifecycle = sub.add_parser(
        "ingest-lifecycle", help="import S012 approval/revocation events locally"
    )
    ingest_lifecycle.add_argument("--source", type=Path, default=DEFAULT_LIFECYCLE)
    ingest_lifecycle.add_argument(
        "--backfill",
        action="store_true",
        help="explicitly classify existing lifecycle history",
    )

    preview = sub.add_parser("preview", help="render the latest imported signal offline")
    preview.add_argument("--public", action="store_true", help="show the free preview")

    sub.add_parser("status", help="show local counts and hard authority boundary")
    campaign_create = sub.add_parser(
        "campaign-create",
        help="create one opaque, allowlisted Telegram promotion code locally",
    )
    campaign_create.add_argument(
        "--kind",
        choices=sorted(CAMPAIGN_KINDS),
        default="telegram_channel",
    )
    campaign_create.add_argument(
        "--bot-username",
        help="optional BotFather username used to render the standard deep link",
    )
    campaign_disable = sub.add_parser(
        "campaign-disable", help="disable a promotion code for future attribution"
    )
    campaign_disable.add_argument("campaign_code")
    promotion_status = sub.add_parser(
        "promotion-status",
        help="show local aggregate campaign and alert metrics",
    )
    promotion_status.add_argument(
        "--exact-local",
        action="store_true",
        help=(
            "unsafe local diagnostics: reveal exact small-cohort behavior; "
            "never publish or paste"
        ),
    )
    sub.add_parser("stars-status", help="show sanitized local provider-ledger health")
    sub.add_parser("stars-issues", help="list sanitized unresolved ledger issues")

    stars_reconcile = sub.add_parser(
        "stars-reconcile",
        help="read and reconcile two complete Telegram Star transaction snapshots",
    )
    stars_reconcile.add_argument(
        "--max-transactions", type=int, default=10_000, help="bounded full-history cap"
    )
    stars_reconcile.add_argument(
        "--token-source",
        choices=("keychain", "environment"),
        required=True,
    )
    stars_reconcile.add_argument(
        "--bot-username",
        required=True,
        help="expected bot username and Keychain account identity",
    )
    stars_reconcile.add_argument(
        "--keychain-account",
        help="versioned Keychain slot; defaults to the lowercase bot username",
    )

    candidates = sub.add_parser(
        "market-candidates",
        help="score an already-fetched Gamma snapshot for manual research review",
    )
    candidates.add_argument("--source", type=Path, required=True)
    candidates.add_argument("--as-of", required=True, help="timezone-aware ISO timestamp")
    candidates.add_argument(
        "--snapshot-at", help="trusted capture timestamp when absent from the wrapper"
    )
    candidates.add_argument("--endpoint", choices=("markets", "events"))

    evidence_record = sub.add_parser(
        "evidence-record",
        help="content-bind one already-fetched primary-source artifact locally",
    )
    evidence_record.add_argument("--market-id", required=True)
    evidence_record.add_argument(
        "--kind",
        required=True,
        choices=(
            "market_quote",
            "order_book",
            "primary_source",
            "resolution_rule",
            "catalyst",
            "outcome",
        ),
    )
    evidence_record.add_argument("--source-url", required=True)
    evidence_record.add_argument("--publisher", required=True)
    evidence_record.add_argument("--observed-at", required=True)
    evidence_record.add_argument(
        "--captured-at",
        help="capture time; defaults to the current UTC time",
    )
    evidence_record.add_argument("--statement", required=True)
    evidence_record.add_argument("--artifact", type=Path, required=True)
    evidence_record.add_argument(
        "--media-type", default="application/octet-stream"
    )

    evidence_list = sub.add_parser(
        "evidence-list",
        help="list immutable local observation records for one market",
    )
    evidence_list.add_argument("--market-id", required=True)
    evidence_list.add_argument("--limit", type=int, default=100)

    forecast_register = sub.add_parser(
        "forecast-register",
        help="preregister an explicit paper forecast before resolution",
    )
    forecast_register.add_argument("signal_id", help="unique active signal prefix")
    forecast_register.add_argument(
        "--probability-yes", type=float, required=True
    )
    forecast_register.add_argument("--recorded-at")
    baseline = forecast_register.add_mutually_exclusive_group()
    baseline.add_argument(
        "--no-market-baseline",
        action="store_true",
        help="record that no same-time market baseline was captured",
    )
    baseline.add_argument("--market-baseline-probability-yes", type=float)
    forecast_register.add_argument("--market-baseline-observation-ref")

    outcome_record = sub.add_parser(
        "outcome-record",
        help="append an evidence-linked outcome to a preregistered forecast",
    )
    outcome_record.add_argument("signal_id")
    outcome_record.add_argument("--outcome", choices=("YES", "NO"), required=True)
    outcome_record.add_argument("--resolved-at", required=True)
    outcome_record.add_argument("--recorded-at")
    outcome_record.add_argument(
        "--resolution-evidence-ref", action="append", required=True
    )
    outcome_record.add_argument(
        "--resolution-evidence-digest",
        required=True,
        help="sha256:<64 lowercase hex characters>",
    )

    scorecard = sub.add_parser(
        "scorecard", help="render the paper forecast calibration scorecard"
    )
    scorecard.add_argument("--domain")
    sub.add_parser(
        "calibration-verify",
        help="verify the complete calibration hash chain",
    )

    channel_post = sub.add_parser(
        "channel-post",
        help="prepare an approved channel card; publish only with --apply",
    )
    channel_post.add_argument("signal_id", help="unique active signal prefix")
    channel_post.add_argument(
        "--channel",
        required=True,
        help="public @channel username or negative Telegram channel ID",
    )
    channel_post.add_argument(
        "--source-links",
        type=Path,
        required=True,
        help="bounded JSON list linking sealed observation refs to HTTPS sources",
    )
    channel_post.add_argument(
        "--market-url",
        required=True,
        help="official Polymarket market URL",
    )
    channel_post.add_argument(
        "--campaign-code",
        help="active local campaign code for an optional private-bot CTA",
    )
    channel_post.add_argument(
        "--research-bot-username",
        help="private Research Bot target paired with --campaign-code",
    )
    channel_post.add_argument(
        "--published-at",
        required=True,
        help="timezone-aware publication timestamp used in the immutable card",
    )
    channel_post.add_argument(
        "--apply",
        action="store_true",
        help="perform the externally visible Telegram channel send",
    )
    channel_post.add_argument(
        "--retry-failed",
        action="store_true",
        help="retry only a known failed receipt after operator review",
    )
    channel_post.add_argument(
        "--disable-notification",
        action="store_true",
        help="request a silent Telegram channel post",
    )
    channel_post.add_argument(
        "--token-source",
        choices=("keychain", "environment"),
        default="keychain",
    )
    channel_post.add_argument(
        "--bot-username",
        help="expected publisher bot username; required with --apply",
    )
    channel_post.add_argument(
        "--keychain-account",
        help="versioned publisher-bot Keychain slot",
    )

    channel_receipt = sub.add_parser(
        "channel-receipt",
        help="inspect one sanitized local channel-publication receipt",
    )
    channel_receipt.add_argument("publication_id")

    channel_reconcile = sub.add_parser(
        "channel-reconcile",
        help="resolve a pending or ambiguous channel-send receipt locally",
    )
    channel_reconcile.add_argument("publication_id")
    channel_reconcile.add_argument("--reconciliation-ref", required=True)
    reconciliation = channel_reconcile.add_mutually_exclusive_group(required=True)
    reconciliation.add_argument("--sent-message-id", type=int)
    reconciliation.add_argument(
        "--not-sent",
        action="store_true",
        help="record that an operator/provider check found no sent message",
    )

    sub.add_parser(
        "compact",
        help="operator-only WAL checkpoint and database compaction after logical deletion",
    )

    run = sub.add_parser(
        "run",
        help="run the sole Research Bot long-poll consumer; Ops is not supported",
    )
    run.add_argument("--source", type=Path, default=DEFAULT_SIGNALS)
    run.add_argument("--lifecycle-source", type=Path, default=DEFAULT_LIFECYCLE)
    run.add_argument("--once", action="store_true", help="one short poll and delivery pass")
    run.add_argument("--poll-timeout", type=int, default=None)
    run.add_argument(
        "--token-source",
        choices=("keychain", "environment"),
        required=True,
    )
    run.add_argument(
        "--bot-username",
        required=True,
        help="expected bot username and Keychain account identity",
    )
    run.add_argument(
        "--keychain-account",
        help="versioned Keychain slot; defaults to the lowercase bot username",
    )
    run.add_argument(
        "--control-only",
        action="store_true",
        help="process commands but pause both research and correction broadcasts",
    )

    return parser


def service_config_from_env(*, poll_timeout: int | None = None) -> ServiceConfig:
    raw_price = os.environ.get("KINGDOM_TELEGRAM_STARS_PRICE", "0")
    try:
        stars_amount = int(raw_price)
    except ValueError as exc:
        raise ValueError("KINGDOM_TELEGRAM_STARS_PRICE must be an integer") from exc
    return ServiceConfig(
        stars_amount=stars_amount,
        terms_version=os.environ.get("KINGDOM_TELEGRAM_TERMS_VERSION", "2026-09-02-v1"),
        support_contact=os.environ.get(
            "KINGDOM_TELEGRAM_SUPPORT_CONTACT",
            "Reply to the operator who provided access to this bot.",
        ),
        poll_timeout_seconds=45 if poll_timeout is None else poll_timeout,
        promotion_notice_version=promotion_notice_version_from_env(),
    )


def promotion_notice_version_from_env() -> str:
    return validate_notice_version(
        os.environ.get(
            "KINGDOM_TELEGRAM_PROMOTION_NOTICE_VERSION",
            DEFAULT_PROMOTION_NOTICE_VERSION,
        )
    )


def _print_import(result: object) -> None:
    print(json.dumps(vars(result), sort_keys=True))


def _ops_database_path(value: Path, *, must_exist: bool) -> Path:
    """Resolve the dedicated Ops store without falling back to Research state."""

    requested = value.expanduser().absolute()
    if requested.is_symlink() or any(parent.is_symlink() for parent in requested.parents):
        raise ValueError("AgentTool Ops state must not use symlinks")
    resolved = requested.resolve()
    if resolved == DEFAULT_DB.expanduser().resolve():
        raise ValueError(
            "AgentTool Ops requires a separate database; pass "
            f"--db {DEFAULT_OPS_DB.relative_to(PROJECT_ROOT)} before the ops command"
        )
    if must_exist and not resolved.is_file():
        raise ValueError("AgentTool Ops database is not initialized; run ops-init first")
    return resolved


def _ops_local_status(store: object) -> dict[str, Any]:
    """Compatibility wrapper for the shared local Ops status renderer."""
    from .ops_runtime import local_status

    return local_status(store)


def _ops_watch_once(args: argparse.Namespace) -> dict[str, Any]:
    """Run one explicit no-session Collab read and commit one safe local page."""

    from .agenttool_mcp import (
        AgentToolMcpConfig,
        AgentToolMcpError,
        AgentToolMcpReader,
    )
    from .agenttool_ops import (
        AgentToolOpsStore,
        CursorStateError,
        DatabaseRoleError,
        OpsProjectionError,
        ProjectionConflict,
    )

    if (
        isinstance(args.event_limit, bool)
        or not isinstance(args.event_limit, int)
        or not 1 <= args.event_limit <= 50
    ):
        raise ValueError("--event-limit must be an integer between 1 and 50")
    ops_path = _ops_database_path(args.db, must_exist=True)
    collab_path = args.collab_db.expanduser().resolve()
    try:
        same_database_file = os.path.samefile(collab_path, ops_path)
    except OSError:
        same_database_file = collab_path == ops_path
    if same_database_file:
        raise ValueError(
            "--collab-db must identify a separate AgentTool journal, not the "
            "local Ops projection database"
        )
    config = AgentToolMcpConfig(
        workspace_id=args.workspace_id,
        expected_workspace_root=PROJECT_ROOT.resolve(),
        enabled=True,
        database_path=collab_path,
    )
    reader = AgentToolMcpReader(config)

    from .ops_runtime import exclusive_database

    try:
        with exclusive_database(ops_path):
            with AgentToolOpsStore(ops_path) as store:
                binding = store.binding()
                if binding is not None and binding.source_binding != args.workspace_id:
                    raise ValueError("AgentTool Ops source binding does not match the requested workspace")
                if store.poll_state() is not None and store.poll_state().state == "paused":
                    raise ValueError("AgentTool Ops transport is paused; no source was contacted")
                recovered_staged_page = False
                recovered_stage_result = None
                staged = store.staged_anchor()
                current = store.committed_anchor()
                if current is not None and args.seed_current_head:
                    raise ValueError(
                        "--seed-current-head is only valid before the Ops source "
                        "cursor has been initialized"
                    )

                verification = reader.verify_journal()
                checked_at = datetime.now(timezone.utc)
                store.record_journal_verification(
                    outcome="valid" if verification.chain_valid else "invalid",
                    checked_at=checked_at,
                    journal_head_sequence=verification.head.sequence,
                    scope_code="full_collab_hash_chain",
                )
                if not verification.chain_valid:
                    raise ValueError(
                        "the full AgentTool journal hash chain was invalid; "
                        "no event page was staged"
                    )

                if staged is not None:
                    if (
                        current is None
                        or staged.epoch_id != current.epoch_id
                        or not 1 <= staged.sequence - current.sequence <= 50
                    ):
                        raise ValueError(
                            "the staged AgentTool Ops page cannot be safely recovered"
                        )
                    recovery_page = reader.events_since(
                        current,
                        limit=staged.sequence - current.sequence,
                    )
                    if recovery_page.head_anchor != verification.head:
                        raise ValueError(
                            "the AgentTool journal changed after full verification; "
                            "no staged page was committed"
                        )
                    if recovery_page.next_anchor != staged:
                        raise ValueError(
                            "the staged AgentTool Ops page no longer matches its "
                            "source anchor"
                        )
                    replay = store.stage_page(
                        current_anchor=recovery_page.current_anchor,
                        next_anchor=recovery_page.next_anchor,
                        events=recovery_page.projection_events(),
                    )
                    if replay.state != "staged" or replay.duplicate is not True:
                        raise ValueError(
                            "the staged AgentTool Ops page failed exact replay validation"
                        )
                    # The exact safe page now matches a page within the stable,
                    # fully verified source head. Advancing this gateway-owned
                    # cursor does not acknowledge a Collab session cursor.
                    store.commit_staged_cursor(staged)
                    recovered_staged_page = True
                    recovered_stage_result = replay
                    current = store.committed_anchor()

                result: dict[str, Any] = {
                    "schema": "kingdom.agenttool-ops-watch/0.1",
                    "mode": "explicit_one_shot_read_only_mcp",
                    "recovered_staged_page": recovered_staged_page,
                    "journal_verification": {
                        "outcome": "valid",
                        "head_sequence": verification.head.sequence,
                        "scope": verification.verification_scope,
                    },
                    "source_boundary": (
                        "read-only MCP methods; the pinned MCP child opens its "
                        "SQLite journal read/write for initialization"
                    ),
                    "collab_session_created": False,
                    "collab_cursor_acknowledged": False,
                    "telegram_calls": 0,
                    "agent_lifecycle_actions": 0,
                    "coordination_mutations": 0,
                    "trades": 0,
                }

                if recovered_stage_result is not None:
                    result.update(
                        {
                            "action": "recovered_exact_staged_page",
                            "events_observed": recovered_stage_result.event_count,
                            "events_enqueued": 0,
                            "source_head_sequence": verification.head.sequence,
                            "committed_sequence": recovered_stage_result.anchor.sequence,
                            "has_more": (
                                recovered_stage_result.anchor.sequence
                                < verification.head.sequence
                            ),
                        }
                    )
                    result["local"] = _ops_local_status(store)
                    return result

                if current is None:
                    source = reader.workspace_status()
                    if source.head.epoch_id != verification.head.epoch_id:
                        raise ValueError(
                            "the AgentTool journal epoch changed during first-run "
                            "observation; rerun the one-shot command"
                        )
                    if source.head.sequence < verification.head.sequence or (
                        source.head.sequence == verification.head.sequence
                        and source.head.hash != verification.head.hash
                    ):
                        raise ValueError(
                            "the AgentTool journal head changed incompatibly during "
                            "first-run observation; rerun the one-shot command"
                        )
                    result["source_snapshot"] = {
                        "head_sequence": source.head.sequence,
                        "open_tasks": source.open_tasks,
                        "claimed_tasks": source.claimed_tasks,
                        "blocked_tasks": source.blocked_tasks,
                        "completed_tasks": source.completed_tasks,
                        "pending_review_tasks": source.pending_review_tasks,
                        "active_session_records": source.active_session_records,
                    }
                    result["events_observed"] = 0
                    result["events_enqueued"] = 0
                    result["has_more"] = source.head.sequence > verification.head.sequence
                    if args.seed_current_head:
                        if source.head != verification.head:
                            raise ValueError(
                                "the AgentTool journal changed after full verification; "
                                "no source cursor was seeded"
                            )
                        store.stage_page(
                            current_anchor=verification.head,
                            next_anchor=verification.head,
                            events=(),
                        )
                        result["action"] = "seeded_verified_current_head"
                    else:
                        result["action"] = "preview_only_unseeded"
                        result["next_step"] = (
                            "review this bounded snapshot, then rerun with "
                            "--seed-current-head; historical replay is not automatic"
                        )
                else:
                    page = reader.events_since(current, limit=args.event_limit)
                    if page.head_anchor != verification.head:
                        raise ValueError(
                            "the AgentTool journal changed after full verification; "
                            "no event page was staged"
                        )
                    staged_result = store.stage_page(
                        current_anchor=page.current_anchor,
                        next_anchor=page.next_anchor,
                        events=page.projection_events(),
                    )
                    if staged_result.state == "staged":
                        store.commit_staged_cursor(page.next_anchor)
                    result.update(
                        {
                            "action": "observed_one_page",
                            "events_observed": staged_result.event_count,
                            "events_enqueued": staged_result.enqueued_count,
                            "source_head_sequence": page.head_anchor.sequence,
                            "committed_sequence": page.next_anchor.sequence,
                            "has_more": page.has_more,
                        }
                    )

                result["local"] = _ops_local_status(store)
                return result
    except AgentToolMcpError as exc:
        raise ValueError(f"AgentTool Ops one-shot failed: {exc}") from None
    except (
        CursorStateError,
        DatabaseRoleError,
        OpsProjectionError,
        ProjectionConflict,
    ) as exc:
        raise ValueError(f"AgentTool Ops projection rejected the page: {exc}") from None
    except ValueError as exc:
        if "another gateway runner already holds" in str(exc):
            raise ValueError("another AgentTool Ops process holds the local lock") from None
        raise
    except PermissionError:
        raise ValueError(
            "AgentTool Ops local state failed its owner-only permission check"
        ) from None
    except (OSError, sqlite3.Error):
        raise ValueError("AgentTool Ops local state is unavailable or busy") from None


def _read_bounded_file(path: Path, limit: int) -> bytes:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"input is not a readable file: {resolved}")
    with resolved.open("rb") as handle:
        payload = handle.read(limit + 1)
    if len(payload) > limit:
        raise ValueError(f"input exceeds the {limit}-byte limit")
    return payload


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON input contains a duplicate key: {key}")
        result[key] = value
    return result


def _read_channel_source_links(path: Path) -> list[dict[str, Any]]:
    payload = _read_bounded_file(path, MAX_CHANNEL_SOURCE_LINK_BYTES)
    try:
        decoded = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (RecursionError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("channel source-links input is not valid UTF-8 JSON") from exc
    if not isinstance(decoded, list) or not all(
        isinstance(item, dict) for item in decoded
    ):
        raise ValueError("channel source-links input must be a JSON list of objects")
    return decoded


def _parse_channel_ref(value: str) -> int | str:
    if value.startswith("-") and value[1:].isdigit():
        try:
            return int(value)
        except ValueError:
            pass
    return value


def _active_approval_event(
    store: GatewayStore, signal_id: str
) -> dict[str, Any]:
    row = store.conn.execute(
        """SELECT e.event_json
           FROM signals s
           JOIN signal_lifecycle_events e ON e.event_id = s.lifecycle_event_id
           WHERE s.signal_id = ?
             AND s.pipeline_status = 'APPROVED'
             AND s.distributable = 1
             AND e.status = 'APPROVED'""",
        (signal_id,),
    ).fetchone()
    if row is None:
        raise ValueError("active signal has no current approval evidence")
    try:
        event = json.loads(str(row["event_json"]))
    except (RecursionError, TypeError, ValueError) as exc:
        raise ValueError("stored approval evidence is invalid") from exc
    if not isinstance(event, dict):
        raise ValueError("stored approval evidence is invalid")
    return event


def _import_changed(result: object) -> bool:
    values = vars(result)
    return any(
        bool(values.get(name))
        for name in (
            "bootstrapped",
            "source_reset",
            "complete_records",
            "imported",
            "applied",
            "duplicates",
            "quarantined",
            "orphans",
            "trailing_partial_ignored",
        )
    )


def _acquire_runner_lock(db_path: Path) -> int:
    lock_path = Path(str(db_path) + ".run.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    os.chmod(lock_path, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise ValueError(
            f"another gateway runner already holds {lock_path}"
        ) from exc
    return fd


@contextmanager
def _exclusive_gateway(db_path: Path) -> Iterator[None]:
    fd = _acquire_runner_lock(db_path)
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _import_without_stopping_control_plane(
    source: Path,
    store: GatewayStore,
    *,
    previous_error: str | None = None,
) -> tuple[object | None, str | None]:
    try:
        result = import_s012_jsonl(source, store)
    except (ImportFailure, OSError, OverflowError) as exc:
        message = str(exc)
        if message != previous_error:
            print(
                "gateway: signal import quarantined; Telegram control processing continues: "
                + message,
                file=sys.stderr,
            )
        return None, message
    if previous_error is not None:
        print("gateway: signal import recovered", file=sys.stderr)
    return result, None


def _import_lifecycle_without_stopping_control_plane(
    source: Path,
    store: GatewayStore,
    *,
    previous_error: str | None = None,
) -> tuple[object | None, str | None]:
    try:
        result = import_s012_lifecycle_jsonl(source, store)
    except (LifecycleImportFailure, OSError, OverflowError) as exc:
        message = str(exc)
        if message != previous_error:
            print(
                "gateway: signal lifecycle import quarantined; broadcasts are paused "
                "while Telegram control processing continues: " + message,
                file=sys.stderr,
            )
        return None, message
    if previous_error is not None:
        print("gateway: signal lifecycle import recovered", file=sys.stderr)
    return result, None


def _promotion_report(
    *,
    notice_version: str,
    summary: dict[str, int],
    campaigns: list[dict[str, Any]],
    exact_local: bool,
) -> dict[str, Any]:
    """Render promotion metrics without exposing small behavioral cohorts."""

    if exact_local:
        return {
            "notice_version": notice_version,
            "measurement_scope": "current_retained_state_not_lifetime_funnel",
            "start_count_semantics": "at_least_once_across_process_crashes",
            "privacy_status": "exact_local_unsafe",
            "privacy_warning": (
                "Exact campaign behavior can identify or expose small cohorts. "
                "Keep this output local; never publish, paste, or forward it."
            ),
            "summary": dict(summary),
            "campaigns": [dict(campaign) for campaign in campaigns],
        }

    original_campaigns = [dict(campaign) for campaign in campaigns]
    safe_campaigns: list[dict[str, Any]] = []
    campaign_suppressed = False
    for campaign in original_campaigns:
        suppress = any(
            isinstance(campaign.get(field), int)
            and not isinstance(campaign.get(field), bool)
            and 0 < int(campaign[field]) < PROMOTION_PRIVACY_THRESHOLD
            for field in PROMOTION_CAMPAIGN_BEHAVIOR_FIELDS
        )
        rendered = dict(campaign)
        if suppress:
            campaign_suppressed = True
            for field in PROMOTION_CAMPAIGN_BEHAVIOR_FIELDS:
                if field in rendered:
                    rendered[field] = None
            rendered["privacy_status"] = "suppressed_below_5"
        else:
            for field in PROMOTION_CAMPAIGN_BEHAVIOR_FIELDS:
                if field in rendered:
                    rendered[field] = _promotion_count_bucket(int(rendered[field]))
            rendered["privacy_status"] = "bucketed_in_fives"
        safe_campaigns.append(rendered)

    suppress_summary = campaign_suppressed or any(
        0 < int(summary.get(field, 0)) < PROMOTION_PRIVACY_THRESHOLD
        for field in PROMOTION_SUMMARY_BEHAVIOR_FIELDS
    )
    # Global totals can expose a small direct-/join cohort by subtraction even
    # when every individual campaign cell is large enough to report.
    residual_pairs = (
        ("start_events", "start_events"),
        ("attributed_recipients", "attributed_recipients"),
        ("alerts_subscribed", "currently_subscribed"),
        ("alerts_unsubscribed", "currently_unsubscribed"),
        ("alerts_need_reconfirmation", "needs_reconfirmation"),
    )
    if not suppress_summary:
        for summary_field, campaign_field in residual_pairs:
            residual = int(summary.get(summary_field, 0)) - sum(
                int(campaign.get(campaign_field, 0))
                for campaign in original_campaigns
            )
            if residual < 0 or 0 < residual < PROMOTION_PRIVACY_THRESHOLD:
                suppress_summary = True
                break

    safe_summary: dict[str, Any] = dict(summary)
    if suppress_summary:
        for field in PROMOTION_SUMMARY_BEHAVIOR_FIELDS:
            if field in safe_summary:
                safe_summary[field] = None
        safe_summary["privacy_status"] = "suppressed_to_prevent_differencing"
    else:
        for field in PROMOTION_SUMMARY_BEHAVIOR_FIELDS:
            if field in safe_summary:
                safe_summary[field] = _promotion_count_bucket(int(safe_summary[field]))
        safe_summary["privacy_status"] = "bucketed_in_fives"
    return {
        "notice_version": notice_version,
        "measurement_scope": "current_retained_state_not_lifetime_funnel",
        "start_count_semantics": "at_least_once_across_process_crashes",
        "privacy_status": (
            "small_cells_suppressed" if suppress_summary else "bucketed"
        ),
        "privacy_threshold": PROMOTION_PRIVACY_THRESHOLD,
        "summary": safe_summary,
        "campaigns": safe_campaigns,
    }


def _run_gateway(
    args: argparse.Namespace,
    store: GatewayStore,
    api: TelegramAPI,
    config: ServiceConfig,
) -> int:
    """Run one locally serialized poller with consent-bound preferences."""

    with PreferenceStore(
        store.path,
        notice_version=os.environ.get(
            "KINGDOM_TELEGRAM_PREFERENCE_NOTICE_VERSION",
            DEFAULT_PREFERENCE_NOTICE_VERSION,
        ),
    ) as preferences:
        service = BotService(
            store,
            api,
            config=config,
            preferences=preferences,
            calibration=CalibrationLedger(args.calibration_ledger),
        )
        if args.once:
            lifecycle_error: str | None = None
            if not args.control_only:
                imported, _ = _import_without_stopping_control_plane(
                    args.source, store
                )
                if imported is not None:
                    _print_import(imported)
                lifecycle, lifecycle_error = (
                    _import_lifecycle_without_stopping_control_plane(
                        args.lifecycle_source, store
                    )
                )
                if lifecycle is not None:
                    _print_import(lifecycle)
            result = service.poll_once(
                timeout=0,
                broadcast=lifecycle_error is None and not args.control_only,
                deliver_corrections=not args.control_only,
            )
            print(json.dumps(result, sort_keys=True))
            return 0

        last_import_error: str | None = None
        last_lifecycle_error: str | None = None
        while True:
            if not args.control_only:
                imported, last_import_error = (
                    _import_without_stopping_control_plane(
                        args.source,
                        store,
                        previous_error=last_import_error,
                    )
                )
                if imported is not None and _import_changed(imported):
                    _print_import(imported)
                lifecycle, last_lifecycle_error = (
                    _import_lifecycle_without_stopping_control_plane(
                        args.lifecycle_source,
                        store,
                        previous_error=last_lifecycle_error,
                    )
                )
                if lifecycle is not None and _import_changed(lifecycle):
                    _print_import(lifecycle)
            try:
                result = service.poll_once(
                    broadcast=(
                        last_lifecycle_error is None and not args.control_only
                    ),
                    deliver_corrections=not args.control_only,
                )
            except TelegramError as exc:
                print(
                    f"gateway: transient Telegram failure: {exc}",
                    file=sys.stderr,
                )
                delay = exc.retry_after or 5
                time.sleep(min(max(delay, 1), 60))
                continue
            except sqlite3.OperationalError:
                print(
                    "gateway: database busy; update was not acknowledged and will be retried",
                    file=sys.stderr,
                )
                time.sleep(1)
                continue
            if any(
                value
                for field, value in result.items()
                if field not in {"broadcast_paused", "corrections_paused"}
            ):
                print(json.dumps(result, sort_keys=True))


def _ops_command(args: argparse.Namespace) -> dict[str, Any]:
    """Dedicated routing; never enter the Research store or token resolver."""
    from .agenttool_ops import AgentToolOpsStore
    from . import ops_runtime as runtime

    if args.command == "ops-demo":
        from .ops_demo import run_demo
        return run_demo(scenario=args.scenario)
    if args.command in {"bot-doctor", "bot-configure"} and args.token_source != "keychain":
        raise runtime.OpsRuntimeError("unsafe_live_transport")
    path = _ops_database_path(args.db, must_exist=True)
    if args.command == "ops-migrate":
        with runtime.exclusive_database(path):
            result = (AgentToolOpsStore.migrate_v1(path) if args.apply
                      else AgentToolOpsStore.preview_migration(path))
        return {**result, "apply": args.apply, "network_calls": 0, "credential_reads": 0}
    with AgentToolOpsStore(path) as store:
        if args.command == "ops-replies":
            return runtime.reply_page(store, state=args.state, limit=args.limit,
                                      after_reply_id=args.after_reply_id)
        if args.command == "ops-bind":
            return runtime.bind_operator(
                store, expected_username=args.bot_username, bot_id=args.bot_id,
                operator_user_id=args.operator_user_id,
                operator_private_chat_id=args.operator_private_chat_id,
                source_binding=args.source_binding, keychain_account_name=args.keychain_account,
                apply=args.apply,
            )
        if args.command == "ops-poll-once":
            return runtime.poll_once(store, expected_username=args.bot_username,
                                     source_binding=args.source_binding,
                                     keychain_account_name=args.keychain_account,
                                     timeout=args.poll_timeout)
        if args.command == "ops-send-once":
            if not args.apply:
                return runtime.preview_reply(store, args.reply_id)
            if (not args.bot_username or not args.source_binding or not args.payload_digest
                    or args.binding_revision is None):
                raise runtime.OpsRuntimeError("invalid_input")
            return runtime.send_once(store, expected_username=args.bot_username,
                                     source_binding=args.source_binding,
                                     keychain_account_name=args.keychain_account,
                                     reply_id=args.reply_id, payload_digest=args.payload_digest,
                                     binding_revision=args.binding_revision)
        if args.command == "ops-reconcile":
            return runtime.reconcile(store, reply_id=args.reply_id, attempt_count=args.attempt_count,
                                     outcome=args.outcome, reconciliation_ref=args.reconciliation_ref,
                                     receipt_ref=args.receipt_ref)
        if args.command == "ops-pause":
            if args.resume:
                return runtime.resume(store, apply=args.apply)
            if args.apply:
                raise runtime.OpsRuntimeError("invalid_input")
            return runtime.pause(store)
        if args.command in {"bot-doctor", "bot-configure"}:
            return runtime.setup_once(store, expected_username=args.bot_username,
                                      source_binding=args.source_binding,
                                      keychain_account_name=args.keychain_account,
                                      configure=args.command == "bot-configure")
    raise runtime.OpsRuntimeError("invalid_input")


def _ops_error(exc: Exception) -> dict[str, Any]:
    from .agenttool_ops import (
        BindingStateError, DatabaseRoleError, DeliveryStateError, MigrationRequiredError,
    )
    from .ops_runtime import OpsRuntimeError
    if isinstance(exc, OpsRuntimeError):
        code = exc.code
    elif isinstance(exc, MigrationRequiredError):
        code = "migration_required"
    elif isinstance(exc, BindingStateError):
        code = "binding_unavailable_or_mismatched"
    elif isinstance(exc, DatabaseRoleError):
        code = "wrong_database_role"
    elif isinstance(exc, DeliveryStateError):
        code = "delivery_state_conflict"
    elif isinstance(exc, TelegramError):
        code = "telegram_outcome_unknown" if exc.ambiguous else "telegram_rejected"
    elif isinstance(exc, (OSError, sqlite3.Error)):
        code = "local_state_unavailable"
    else:
        code = "invalid_input_or_state"
    next_step = {
        "initial_binding_requires_empty_store": (
            "Keep this populated unbound store for offline inspection. Use a new empty Ops database, "
            "bind it first, then observe only that same source. Existing provenance cannot be inferred."
        ),
        "poll_offset_exhausted": (
            "The maximum update ID is stored safely; no provider call was made. "
            "Use ops-replies to recover replies. Retry polling after the normal idle reset "
            "(86,401 seconds since the current epoch's last update or start); do not discard or manually reset offsets."
        ),
    }.get(code, "Inspect local ops-status; use ops-replies to recover references and ops-migrate for v1. "
                "Review binding or exact reply/attempt inputs. No automatic resend.")
    return {"ok": False, "error_code": code, "next_step": next_step}


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    ops_arguments = any(value.startswith("ops-") for value in arguments) or any(
        arguments[index:index + 2] == ["--profile", "ops"]
        for index in range(len(arguments))
    ) or "--profile=ops" in arguments
    try:
        args = build_parser(sanitize_ops_errors=ops_arguments).parse_args(arguments)
    except _OpsArgumentError:
        print(json.dumps({"ok": False, "error_code": "invalid_arguments",
                          "next_step": "Use the Ops command --help; no input values were logged."}),
              file=sys.stderr)
        return 1
    dedicated_ops = (
        args.command in {"ops-bind", "ops-migrate", "ops-poll-once", "ops-send-once",
                         "ops-reconcile", "ops-pause", "ops-demo", "ops-replies"}
        or (args.command in {"bot-doctor", "bot-configure"} and args.profile == "ops"
            and (args.command == "bot-doctor" or args.apply))
    )
    if dedicated_ops:
        try:
            result = _ops_command(args)
            print(json.dumps(result, sort_keys=True))
            if args.command in {"bot-doctor", "bot-configure"}:
                return 0 if result["bot_api_profile_ready"] else 1
            if args.command == "ops-send-once" and args.apply:
                return 0 if result["state"] == "sent" else 1
            return 0
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(json.dumps(_ops_error(exc), sort_keys=True), file=sys.stderr)
            return 1
    try:
        if args.command == "bot-plan":
            selected_profile = bot_profile(args.profile)
            plan = build_botfather_plan(
                args.bot_username,
                privacy_url=args.privacy_url,
                profile=selected_profile,
            )
            if args.copy:
                copy_botfather_value(
                    args.copy,
                    bot_username=args.bot_username,
                    profile=selected_profile,
                )
            if args.open_botfather:
                open_botfather()
            plan["botfather_opened"] = bool(args.open_botfather)
            plan["clipboard_value"] = args.copy
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0
        if args.command == "bot-token-store":
            token_options = ({"keychain_service": OPS_KEYCHAIN_SERVICE}
                             if args.profile == "ops" else {})
            result = store_token_interactively(
                args.bot_username,
                keychain_account_name=args.keychain_account,
                **token_options,
            )
            print(json.dumps(result, sort_keys=True))
            print(
                "Clipboard clearing cannot erase clipboard-manager, Universal Clipboard, "
                "or BotFather message history copies.",
                file=sys.stderr,
            )
            return 0
        if args.command == "managed-bot-link":
            print(
                json.dumps(
                    {
                        "creation_link": build_managed_bot_link(
                            args.manager_username,
                            args.bot_username,
                            child_name=args.name,
                        ),
                        "requires": (
                            "manager Bot Management Mode plus visible user confirmation; "
                            "the confirming user remains the child bot owner"
                        ),
                        "token_in_link": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "bot-configure" and not args.apply:
            username = validate_bot_username(args.bot_username)
            selected_profile = bot_profile(args.profile)
            if selected_profile.code == "ops":
                from .telegram_api import PRODUCTION_TELEGRAM_ORIGIN, validate_ops_origin
                validate_ops_origin(PRODUCTION_TELEGRAM_ORIGIN)
                if args.token_source != "keychain":
                    raise ValueError("Ops requires its dedicated Keychain service; environment credentials are not supported")
            account = None
            if args.token_source == "keychain":
                account = keychain_account(username, args.keychain_account)
            elif args.keychain_account is not None:
                raise ValueError(
                    "--keychain-account is only valid with --token-source keychain"
                )
            print(
                json.dumps(
                    {
                        "apply": False,
                        "bot_username": username,
                        "profile": selected_profile.code,
                        "bot_name": selected_profile.name,
                        "commands": desired_commands(selected_profile),
                        "keychain_service": (
                            (OPS_KEYCHAIN_SERVICE if selected_profile.code == "ops" else KEYCHAIN_SERVICE)
                            if args.token_source == "keychain"
                            else None
                        ),
                        "keychain_account": account,
                        "network_calls": 0,
                        "note": (
                            "rerun with --apply only after bot-doctor identity and BotFather checks"
                            if selected_profile.code == "research"
                            else "Bind the dedicated Ops database with ops-bind --apply; then repeat with --source-binding and --apply"
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "market-candidates":
            payload = _read_bounded_file(args.source, MAX_PAYLOAD_BYTES)
            report = build_candidate_report(
                payload,
                as_of=args.as_of,
                snapshot_at=args.snapshot_at,
                endpoint=args.endpoint,
            )
            print(candidate_report_json(report))
            return 0
        if args.command in {"ops-init", "ops-status"}:
            from .agenttool_ops import (
                AgentToolOpsStore,
                CursorStateError,
                DatabaseRoleError,
                MigrationRequiredError,
                OpsProjectionError,
                ProjectionConflict,
            )

            ops_path = _ops_database_path(
                args.db,
                must_exist=args.command == "ops-status",
            )
            existed = ops_path.is_file()
            try:
                with AgentToolOpsStore(ops_path) as ops_store:
                    result = _ops_local_status(ops_store)
            except MigrationRequiredError:
                raise ValueError("AgentTool Ops v1 requires explicit ops-migrate preview, then ops-migrate --apply") from None
            except PermissionError:
                raise ValueError(
                    "AgentTool Ops local state failed its owner-only permission check"
                ) from None
            except (OSError, sqlite3.Error):
                raise ValueError(
                    "AgentTool Ops local state is unavailable or busy"
                ) from None
            except (
                CursorStateError,
                DatabaseRoleError,
                OpsProjectionError,
                ProjectionConflict,
            ):
                raise ValueError(
                    "AgentTool Ops local state failed integrity validation"
                ) from None
            result["projection_schema_initialized"] = True
            result["database_file_preexisted"] = existed
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.command == "ops-watch-once":
            print(json.dumps(_ops_watch_once(args), indent=2, sort_keys=True))
            return 0
        if args.command in {"channel-receipt", "channel-reconcile"}:
            ledger_path = args.channel_ledger.expanduser().resolve()
            if not ledger_path.is_file():
                raise ValueError(
                    f"channel publication ledger does not exist: {ledger_path}"
                )
            with ChannelPublicationLedger(ledger_path) as ledger:
                if args.command == "channel-receipt":
                    receipt = ledger.receipt(args.publication_id)
                    print(
                        json.dumps(
                            {
                                "found": receipt is not None,
                                "receipt": asdict(receipt) if receipt else None,
                            },
                            sort_keys=True,
                        )
                    )
                    return 0 if receipt is not None else 1
                receipt = ledger.reconcile_unknown(
                    args.publication_id,
                    sent_message_id=(
                        None if args.not_sent else args.sent_message_id
                    ),
                    reconciliation_ref=args.reconciliation_ref,
                )
                print(json.dumps(asdict(receipt), sort_keys=True))
                return 0
        with GatewayStore(args.db) as store:
            if args.command == "bot-doctor":
                token = resolve_token(
                    source=args.token_source,
                    bot_username=args.bot_username,
                    keychain_account_name=args.keychain_account,
                )
                api = TelegramAPI(token)
                report = inspect_bot(
                    api,
                    args.bot_username,
                    profile=bot_profile(args.profile),
                )
                with _exclusive_gateway(store.path):
                    store.bind_authenticated_telegram_provider(
                        int(report["identity"]["id"]),
                        api.provider_origin,
                        str(report["identity"]["username"]),
                        allow_legacy_username_backfill=True,
                    )
                report["database_provider_bound"] = True
                print(json.dumps(report, indent=2, sort_keys=True))
                return 0 if report["runtime_ready"] is True else 1
            if args.command == "bot-configure":
                token = resolve_token(
                    source=args.token_source,
                    bot_username=args.bot_username,
                    keychain_account_name=args.keychain_account,
                )
                with _exclusive_gateway(store.path):
                    report = configure_bot(
                        TelegramAPI(token),
                        store,
                        args.bot_username,
                        profile=bot_profile(args.profile),
                    )
                report["configuration_attempted"] = True
                report["configuration_verified"] = (
                    report["bot_api_profile_ready"] is True
                )
                print(json.dumps(report, indent=2, sort_keys=True))
                return 0 if report["bot_api_profile_ready"] is True else 1
            if args.command == "bot-campaign":
                token = resolve_token(
                    source=args.token_source,
                    bot_username=args.bot_username,
                    keychain_account_name=args.keychain_account,
                )
                api = TelegramAPI(token)
                report = inspect_bot(api, args.bot_username)
                if report["bot_api_profile_ready"] is not True:
                    raise ValueError(
                        "verified Bot API base profile is not ready; run bot-doctor and bot-configure"
                    )
                with _exclusive_gateway(store.path):
                    store.bind_authenticated_telegram_provider(
                        int(report["identity"]["id"]),
                        api.provider_origin,
                        str(report["identity"]["username"]),
                        allow_create=False,
                        allow_legacy_username_backfill=True,
                    )
                    canonical_bot_username = (
                        store.require_telegram_provider_bot_username(
                            str(report["identity"]["username"])
                        )
                    )
                    campaign_code, created = store.get_or_create_bootstrap_campaign()
                print(
                    json.dumps(
                        {
                            "campaign_code": campaign_code,
                            "created": created,
                            "deep_link": build_campaign_link(
                                canonical_bot_username, campaign_code
                            ),
                            "verified_bot_id": report["identity"]["id"],
                            "published": False,
                            "publication_check": (
                                "manual: complete and register the public privacy policy first"
                            ),
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if args.command == "init":
                with _exclusive_gateway(store.path):
                    ObservationLedger(store.conn)
                    with PreferenceStore(
                        store.path,
                        notice_version=os.environ.get(
                            "KINGDOM_TELEGRAM_PREFERENCE_NOTICE_VERSION",
                            DEFAULT_PREFERENCE_NOTICE_VERSION,
                        ),
                    ):
                        pass
                    CalibrationLedger(args.calibration_ledger)
                    with ChannelPublicationLedger(args.channel_ledger):
                        pass
                    print(f"Initialized private gateway database: {store.path}")
                    print(
                        "Initialized observations, consent-bound preferences, paper "
                        "calibration, and channel-publication receipts."
                    )
                return 0
            if args.command == "ingest":
                with _exclusive_gateway(store.path):
                    _print_import(
                        import_s012_jsonl(args.source, store, backfill=args.backfill)
                    )
                return 0
            if args.command == "ingest-lifecycle":
                with _exclusive_gateway(store.path):
                    _print_import(
                        import_s012_lifecycle_jsonl(
                            args.source, store, backfill=args.backfill
                        )
                    )
                return 0
            if args.command == "evidence-record":
                artifact = _read_bounded_file(args.artifact, MAX_ARTIFACT_BYTES)
                observation = build_observation(
                    market_id=args.market_id,
                    kind=args.kind,
                    statement=args.statement,
                    source_url=args.source_url,
                    source_publisher=args.publisher,
                    observed_at=args.observed_at,
                    captured_at=args.captured_at
                    or datetime.now(timezone.utc),
                    artifact=artifact,
                    media_type=args.media_type,
                )
                with _exclusive_gateway(store.path):
                    created = ObservationLedger(store.conn).append(observation)
                print(
                    json.dumps(
                        {
                            "created": created,
                            "observation": observation,
                            "artifact_retained": False,
                            "execution_allowed": False,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if args.command == "evidence-list":
                with _exclusive_gateway(store.path):
                    observations = ObservationLedger(store.conn).list_for_market(
                        args.market_id, limit=args.limit
                    )
                print(
                    json.dumps(
                        {
                            "market_id": args.market_id,
                            "observations": observations,
                            "execution_allowed": False,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if args.command == "forecast-register":
                signal = store.resolve_signal_prefix(args.signal_id)
                if signal is None:
                    raise ValueError(
                        "signal is missing, ambiguous, inactive, or expired"
                    )
                ledger = CalibrationLedger(args.calibration_ledger)
                common = {
                    "probability_yes": args.probability_yes,
                    "recorded_at": args.recorded_at,
                }
                if args.no_market_baseline:
                    if args.market_baseline_observation_ref is not None:
                        raise ValueError(
                            "--market-baseline-observation-ref cannot accompany "
                            "--no-market-baseline"
                        )
                    result = ledger.register_forecast(
                        signal,
                        market_baseline_probability_yes=None,
                        **common,
                    )
                elif args.market_baseline_probability_yes is not None:
                    if args.market_baseline_observation_ref is None:
                        raise ValueError(
                            "an explicit market baseline requires "
                            "--market-baseline-observation-ref"
                        )
                    result = ledger.register_forecast(
                        signal,
                        market_baseline_probability_yes=(
                            args.market_baseline_probability_yes
                        ),
                        market_baseline_observation_ref=(
                            args.market_baseline_observation_ref
                        ),
                        **common,
                    )
                else:
                    if args.market_baseline_observation_ref is not None:
                        raise ValueError(
                            "--market-baseline-observation-ref requires an explicit "
                            "baseline probability"
                        )
                    result = ledger.register_forecast(signal, **common)
                print(
                    json.dumps(
                        {
                            "duplicate": result.duplicate,
                            "event": result.event,
                            "execution_allowed": False,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if args.command == "outcome-record":
                ledger = CalibrationLedger(args.calibration_ledger)
                result = ledger.record_resolution(
                    args.signal_id,
                    outcome=args.outcome,
                    resolved_at=args.resolved_at,
                    recorded_at=args.recorded_at,
                    resolution_evidence_refs=args.resolution_evidence_ref,
                    resolution_evidence_content_digest=(
                        args.resolution_evidence_digest
                    ),
                )
                print(
                    json.dumps(
                        {
                            "duplicate": result.duplicate,
                            "event": result.event,
                            "execution_allowed": False,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if args.command == "scorecard":
                print(
                    json.dumps(
                        CalibrationLedger(args.calibration_ledger).scorecard(
                            domain=args.domain
                        ),
                        sort_keys=True,
                    )
                )
                return 0
            if args.command == "calibration-verify":
                checkpoint = CalibrationLedger(args.calibration_ledger).verify()
                print(json.dumps(asdict(checkpoint), sort_keys=True))
                return 0
            if args.command == "channel-post":
                if (
                    args.keychain_account is not None
                    and args.token_source != "keychain"
                ):
                    raise ValueError(
                        "--keychain-account is only valid with --token-source keychain"
                    )
                signal = store.resolve_signal_prefix(args.signal_id)
                if signal is None:
                    raise ValueError(
                        "signal is missing, ambiguous, inactive, or expired"
                    )
                approval = _active_approval_event(
                    store, str(signal["signal_id"])
                )
                card = build_research_card(
                    signal,
                    approval,
                    source_links=_read_channel_source_links(args.source_links),
                    market_url=args.market_url,
                    published_at=args.published_at,
                )
                campaign_link = None
                if (args.campaign_code is None) != (
                    args.research_bot_username is None
                ):
                    raise ValueError(
                        "--campaign-code and --research-bot-username must be used together"
                    )
                if args.campaign_code is not None:
                    if not store.is_active_promotion_campaign(args.campaign_code):
                        raise ValueError(
                            "campaign code is missing or disabled in this gateway"
                        )
                    canonical_bot_username = (
                        store.require_telegram_provider_bot_username(
                            args.research_bot_username
                        )
                    )
                    campaign_link = build_campaign_link(
                        canonical_bot_username, args.campaign_code
                    )
                post = prepare_channel_post(
                    card,
                    _parse_channel_ref(args.channel),
                    campaign_link=campaign_link,
                )
                if not args.apply:
                    print(
                        json.dumps(
                            {
                                "apply": False,
                                "card": card,
                                "post": asdict(post),
                                "network_calls": 0,
                                "external_delivery_enabled": False,
                                "execution_allowed": False,
                            },
                            sort_keys=True,
                        )
                    )
                    return 0
                if not args.bot_username:
                    raise ValueError("--bot-username is required with --apply")
                token = resolve_token(
                    source=args.token_source,
                    bot_username=args.bot_username,
                    keychain_account_name=args.keychain_account,
                )
                api = TelegramAPI(token)
                identity = verify_identity(api, args.bot_username)
                with ChannelPublicationLedger(args.channel_ledger) as ledger:
                    receipt = ChannelPublisher(
                        ledger,
                        api,
                        ChannelPublisherConfig(
                            external_delivery_enabled=True,
                            disable_notification=args.disable_notification,
                        ),
                    ).publish(post, retry_failed=args.retry_failed)
                print(
                    json.dumps(
                        {
                            "apply": True,
                            "publisher_bot": {
                                "id": identity["id"],
                                "username": identity["username"],
                            },
                            "receipt": asdict(receipt),
                            "execution_allowed": False,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if args.command == "preview":
                signal = store.latest_signal()
                if not signal:
                    print("No active imported signal.")
                    return 1
                print(
                    render_public_signal(signal)
                    if args.public
                    else render_research_signal(signal)
                )
                return 0
            if args.command == "status":
                policy = PolicyEngine().decide(Action.PLACE_LIVE_ORDER)
                promotion_notice = promotion_notice_version_from_env()
                raw_counts = store.counts(
                    promotion_notice_version=promotion_notice
                )
                # Generic health output is commonly pasted into diagnostics.
                # Keep recipient/promotion behavior on the separately
                # thresholded promotion-status surface.
                operational_count_keys = {
                    "signals",
                    "reservation_conflicts",
                    "failed_updates",
                }
                operational_counts = {
                    key: raw_counts[key]
                    for key in sorted(operational_count_keys)
                    if key in raw_counts
                }
                print(
                    json.dumps(
                        {
                            "counts": operational_counts,
                            "counts_privacy": (
                                "recipient, promotion, and financial behavior omitted; "
                                "use privacy-filtered promotion-status or stars-status"
                            ),
                            "promotion_notice_version": promotion_notice,
                            "signal_lifecycle": store.signal_lifecycle_status(),
                            "stars": store.star_reconciliation_status(),
                        },
                        sort_keys=True,
                    )
                )
                print(f"{policy.code}: {policy.explanation}")
                return 0
            if args.command == "campaign-create":
                canonical_bot_username = (
                    store.require_telegram_provider_bot_username(args.bot_username)
                    if args.bot_username
                    else None
                )
                campaign_code = generate_campaign_code()
                deep_link = (
                    build_campaign_link(canonical_bot_username, campaign_code)
                    if canonical_bot_username
                    else None
                )
                with _exclusive_gateway(store.path):
                    created = store.create_promotion_campaign(
                        campaign_code, campaign_kind=args.kind
                    )
                print(
                    json.dumps(
                        {
                            "campaign_code": campaign_code,
                            "campaign_kind": args.kind,
                            "created": created,
                            "deep_link": deep_link,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if args.command == "campaign-disable":
                with _exclusive_gateway(store.path):
                    disabled = store.disable_promotion_campaign(args.campaign_code)
                print(
                    json.dumps(
                        {
                            "campaign_code": args.campaign_code,
                            "disabled": disabled,
                        },
                        sort_keys=True,
                    )
                )
                return 0 if disabled else 1
            if args.command == "promotion-status":
                promotion_notice = promotion_notice_version_from_env()
                summary, campaigns = store.promotion_metrics_snapshot(
                    promotion_notice
                )
                print(
                    json.dumps(
                        _promotion_report(
                            notice_version=promotion_notice,
                            summary=summary,
                            campaigns=campaigns,
                            exact_local=args.exact_local,
                        ),
                        sort_keys=True,
                    )
                )
                return 0
            if args.command == "stars-status":
                print(json.dumps(store.star_reconciliation_status(), sort_keys=True))
                return 0
            if args.command == "stars-issues":
                print(json.dumps(store.unresolved_star_issues(), sort_keys=True))
                return 0
            if args.command == "stars-reconcile":
                token = resolve_token(
                    source=args.token_source,
                    bot_username=args.bot_username,
                    keychain_account_name=args.keychain_account,
                )
                api = TelegramAPI(token)
                identity = verify_identity(api, args.bot_username)
                with _exclusive_gateway(store.path):
                    store.bind_telegram_provider(
                        int(identity["id"]), api.provider_origin, allow_create=False
                    )
                    result = reconcile_star_transactions(
                        store,
                        api,
                        max_transactions=args.max_transactions,
                    )
                print(json.dumps(asdict(result), sort_keys=True))
                return 0 if result.error_code is None and result.clean is True else 1
            if args.command == "compact":
                with _exclusive_gateway(store.path):
                    store.compact_storage()
                print("Gateway WAL checkpoint and database compaction completed.")
                return 0
            if args.command == "run":
                token = resolve_token(
                    source=args.token_source,
                    bot_username=args.bot_username,
                    keychain_account_name=args.keychain_account,
                )
                with _exclusive_gateway(store.path):
                    config = service_config_from_env(poll_timeout=args.poll_timeout)
                    if config.stars_amount > 0:
                        raise ValueError(
                            "the development long-poll runner refuses live Stars commerce; "
                            "use price 0 until reviewed HTTPS webhook/control ingress exists"
                        )
                    api = TelegramAPI(token)
                    prepare_runtime(
                        api,
                        store,
                        expected_username=args.bot_username,
                        required_profile=bot_profile("research"),
                    )
                    return _run_gateway(args, store, api, config)
    except (
        CandidateInputError,
        ChannelPublishingError,
        ImportFailure,
        LifecycleImportFailure,
        StarReconciliationError,
        TelegramError,
        ValueError,
        OSError,
        sqlite3.Error,
    ) as exc:
        print(f"gateway: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
