"""Finite foreground Ops transport. No daemon, event alerts, or agent dispatch.

Local locks exclude cooperating consumers on this host, not remote pollers or
hostile processes under the same account. Keep the provider and DB locks held
through sending/completion, pause, resume and reconciliation. Telegram cannot
provide exactly-once sends; uncertain attempts are terminal until observation.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Mapping

from .agenttool_ops import (
    AgentToolOpsStore, BindingStateError, DeliveryStateError, OpsBinding, ReplyItem,
)
from .bootstrap import (
    OPS_BOT_PROFILE, OPS_KEYCHAIN_SERVICE, configure_bot, inspect_bot,
    keychain_account, load_keychain_token, prepare_runtime, validate_bot_username,
    verify_identity,
)
from .ops_service import OpsServiceConfig, TelegramOpsService
from .telegram_api import (
    MAX_OPS_POLL_OFFSET, PRODUCTION_TELEGRAM_ORIGIN, TelegramAPI, TelegramError,
    validate_ops_origin,
)

DEFAULT_LOCK_DIRECTORY = Path.home() / ".kingdom-telegram-ops-locks"
_LABEL = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


class OpsRuntimeError(ValueError):
    """A closed diagnostic code, never an upstream body or a private value."""

    def __init__(self, code: str):
        if code not in {
            "local_lock_busy", "unsafe_local_lock", "binding_required",
            "binding_mismatch", "invalid_input", "fixture_transport_required",
            "unsafe_live_transport", "reply_not_pending", "stale_preview",
            "invalid_update_batch", "source_binding_required",
            "initial_binding_requires_empty_store", "poll_offset_exhausted",
        }:
            code = "invalid_input"
        self.code = code
        super().__init__(code)


def _owner_directory(path: Path, *, create: bool = False) -> Path:
    """Refuse symlink ancestors and permissive existing lock directories."""
    path = path.expanduser().absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise OpsRuntimeError("unsafe_local_lock")
    if create:
        # The live root is immediately below home; fixture roots must have an
        # existing temporary parent. Never chmod an existing shared directory.
        path.mkdir(mode=0o700, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise OpsRuntimeError("unsafe_local_lock")
    return path


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    directory = _owner_directory(path.parent)
    dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    fd = None
    try:
        fd = os.open(path.name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                     0o600, dir_fd=dfd)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise OpsRuntimeError("unsafe_local_lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OpsRuntimeError("local_lock_busy") from None
        linked = os.stat(path.name, dir_fd=dfd, follow_symlinks=False)
        if (info.st_dev, info.st_ino) != (linked.st_dev, linked.st_ino):
            raise OpsRuntimeError("unsafe_local_lock")
        yield
    finally:
        if fd is not None:
            os.close(fd)
        os.close(dfd)


@contextmanager
def exclusive_database(path: Path) -> Iterator[None]:
    """Same filename as the existing observer lock, but fail closed on aliases."""
    path = path.expanduser().absolute()
    if path.is_symlink():
        raise OpsRuntimeError("unsafe_local_lock")
    with _file_lock(Path(str(path) + ".run.lock")):
        yield


@contextmanager
def exclusive_ops(
    store: AgentToolOpsStore, *, bot_id: int | None = None,
    fixture: bool = False, lock_dir: Path | None = None,
) -> Iterator[None]:
    """Provider first, then DB; held across the whole bounded operation."""
    if type(fixture) is not bool or (lock_dir is not None and not fixture):
        raise OpsRuntimeError("unsafe_live_transport")
    if fixture and lock_dir is None:
        raise OpsRuntimeError("fixture_transport_required")
    binding = store.binding()
    selected = bot_id if bot_id is not None else binding.bot_id if binding else None
    _positive_id(selected)
    root = _owner_directory(lock_dir if fixture else DEFAULT_LOCK_DIRECTORY, create=True)
    key = hashlib.sha256(f"{PRODUCTION_TELEGRAM_ORIGIN}\0{selected}".encode()).hexdigest()
    with _file_lock(root / (key + ".lock")):
        with exclusive_database(store.path):
            current = store.binding()
            if current is not None and current.bot_id != selected:
                raise OpsRuntimeError("binding_mismatch")
            yield


def _positive_id(value: Any) -> None:
    if type(value) is not int or not 1 <= value <= (1 << 52) - 1:
        raise OpsRuntimeError("invalid_input")


def _label(value: Any) -> str:
    if not isinstance(value, str) or _LABEL.fullmatch(value) is None:
        raise OpsRuntimeError("invalid_input")
    return value


def credential_reference(username: str, account: str | None = None) -> str:
    return f"keychain:{OPS_KEYCHAIN_SERVICE}:{keychain_account(username, account)}"


def _check_api(api: Any, *, fixture: bool) -> None:
    if fixture:
        # A fixture has no credential-bearing TelegramAPI at all. Fake methods
        # are an explicit test seam, not a live CLI mode.
        if api is None or isinstance(api, TelegramAPI):
            raise OpsRuntimeError("fixture_transport_required")
    elif (type(api) is not TelegramAPI or api.request_opener is not None
          or api.require_production_origin is not True):
        raise OpsRuntimeError("unsafe_live_transport")
    validate_ops_origin(api.provider_origin)
    if not fixture:
        validate_ops_origin(api.base_url)


def _load_api(username: str, account: str | None) -> TelegramAPI:
    # This is deliberately not resolve_token: Ops has no environment fallback.
    origin = validate_ops_origin(PRODUCTION_TELEGRAM_ORIGIN)
    token = load_keychain_token(username, keychain_account_name=account,
                                keychain_service=OPS_KEYCHAIN_SERVICE)
    return TelegramAPI(token, base_url=origin, require_production_origin=True)


def _ready(
    store: AgentToolOpsStore, *, expected_username: str, keychain_account_name: str | None,
    source_binding: str | None, fixture: bool,
) -> OpsBinding:
    validate_ops_origin(PRODUCTION_TELEGRAM_ORIGIN)
    validate_bot_username(expected_username)
    binding = store.binding()
    if binding is None:
        raise OpsRuntimeError("binding_required")
    if not fixture and binding.verification != "verified":
        raise BindingStateError("fixture binding cannot authorize live transport")
    if source_binding is None and not fixture:
        raise OpsRuntimeError("source_binding_required")
    source = binding.source_binding if source_binding is None else _label(source_binding)
    credential = binding.credential_ref if fixture else credential_reference(expected_username, keychain_account_name)
    if fixture and binding.verification != "fixture":
        raise OpsRuntimeError("fixture_transport_required")
    return store.require_ready(
        bot_id=binding.bot_id, operator_user_id=binding.operator_user_id,
        operator_private_chat_id=binding.operator_private_chat_id,
        api_origin=PRODUCTION_TELEGRAM_ORIGIN, credential_ref=credential,
        source_binding=source, live=not fixture,
    )


def _prepared_api(store: AgentToolOpsStore, api: Any, *, expected_username: str,
                  keychain_account_name: str | None, source_binding: str | None,
                  fixture: bool, profile_required: bool = True) -> Any:
    _ready(store, expected_username=expected_username,
           keychain_account_name=keychain_account_name, source_binding=source_binding,
           fixture=fixture)
    if api is None and not fixture:
        api = _load_api(expected_username, keychain_account_name)
    _check_api(api, fixture=fixture)
    # Verify the numeric provider before reading/mutating its broader profile.
    identity = verify_identity(api, expected_username)
    store.bind_telegram_provider(identity["id"], api.provider_origin, allow_create=False)
    if profile_required:
        prepare_runtime(api, store, expected_username=expected_username,
                        required_profile=OPS_BOT_PROFILE)
    return api


def binding_report(store: AgentToolOpsStore) -> dict[str, Any]:
    binding, state = store.binding(), store.poll_state()
    return {
        "bound": binding is not None,
        "binding_revision": binding.revision if binding else None,
        "verification": binding.verification if binding else None,
        "state": state.state if state else "unbound",
        "poll_offset_exhausted": bool(state and state.next_offset is not None
                                      and state.next_offset > MAX_OPS_POLL_OFFSET),
        "event_alerts_enabled": False,
        "lock_scope": "cooperating_local_processes_only",
    }


def bind_operator(
    store: AgentToolOpsStore, *, expected_username: str, bot_id: int,
    operator_user_id: int, operator_private_chat_id: int, source_binding: str,
    keychain_account_name: str | None = None, apply: bool = False,
    api: Any = None, fixture: bool = False, lock_dir: Path | None = None,
    bound_at: datetime | str | None = None,
) -> dict[str, Any]:
    if type(apply) is not bool or type(fixture) is not bool:
        raise OpsRuntimeError("invalid_input")
    if bound_at is not None and not fixture:
        raise OpsRuntimeError("unsafe_live_transport")
    validate_ops_origin(PRODUCTION_TELEGRAM_ORIGIN)
    validate_bot_username(expected_username)
    _positive_id(bot_id)
    OpsServiceConfig(operator_user_id, operator_private_chat_id)
    source_binding = _label(source_binding)
    credential = "fixture:ops-runtime" if fixture else credential_reference(expected_username, keychain_account_name)
    def check_local_binding() -> OpsBinding | None:
        existing = store.binding()
        if existing and (existing.bot_id, existing.operator_user_id,
                         existing.operator_private_chat_id, existing.api_origin,
                         existing.credential_ref, existing.source_binding, existing.verification) != (
                bot_id, operator_user_id, operator_private_chat_id, PRODUCTION_TELEGRAM_ORIGIN,
                credential, source_binding, "fixture" if fixture else "verified"):
            raise OpsRuntimeError("binding_mismatch")
        try:
            store.assert_initial_binding_allowed()
        except BindingStateError:
            raise OpsRuntimeError("initial_binding_requires_empty_store") from None
        return existing

    existing = check_local_binding()
    if not apply:
        return {"apply": False, "binding_matches": existing is not None,
                "numeric_pair_valid": True, "dedicated_credential_slot": True,
                "network_calls": 0, "credential_reads": 0,
                "next_step": "Review numeric inputs; repeat ops-bind with --apply."}
    with exclusive_ops(store, bot_id=bot_id, fixture=fixture, lock_dir=lock_dir):
        # Observation/binding may have changed while acquiring the locks. The
        # store repeats this preflight/comparison inside its binding transaction.
        check_local_binding()
        if api is None and not fixture:
            api = _load_api(expected_username, keychain_account_name)
        _check_api(api, fixture=fixture)
        identity = verify_identity(api, expected_username)
        if type(identity["id"]) is not int or identity["id"] != bot_id:
            raise OpsRuntimeError("binding_mismatch")
        store.bind_operator(bot_id, api.provider_origin,
                            operator_user_id=operator_user_id,
                            operator_private_chat_id=operator_private_chat_id,
                            credential_ref=credential, source_binding=source_binding,
                            verification="fixture" if fixture else "verified", bound_at=bound_at)
        return {"apply": True, **binding_report(store), "sends": 0}


def setup_once(store: AgentToolOpsStore, *, expected_username: str,
               source_binding: str, keychain_account_name: str | None = None,
               configure: bool = False, api: Any = None, fixture: bool = False,
               lock_dir: Path | None = None) -> dict[str, Any]:
    with exclusive_ops(store, fixture=fixture, lock_dir=lock_dir):
        api = _prepared_api(store, api, expected_username=expected_username,
                            keychain_account_name=keychain_account_name,
                            source_binding=source_binding, fixture=fixture, profile_required=False)
        report = (configure_bot(api, store, expected_username, profile=OPS_BOT_PROFILE)
                  if configure else inspect_bot(api, expected_username, profile=OPS_BOT_PROFILE))
        # Do not echo IDs, webhook pending counts, provider fields, or slot names.
        return {"profile": "ops", "configuration_attempted": configure,
                "runtime_ready": report["runtime_ready"] is True,
                "bot_api_profile_ready": report["bot_api_profile_ready"] is True,
                "checks": {key: value is True for key, value in report["checks"].items()},
                **binding_report(store), "sends": 0}


def poll_once(store: AgentToolOpsStore, api: Any = None, *, expected_username: str,
              source_binding: str | None = None, keychain_account_name: str | None = None,
              fixture: bool = False, lock_dir: Path | None = None,
              now: datetime | str | None = None, timeout: int = 0) -> dict[str, Any]:
    if type(timeout) is not int or not 0 <= timeout <= 30:
        raise OpsRuntimeError("invalid_input")
    if now is not None and not fixture:
        raise OpsRuntimeError("unsafe_live_transport")
    with exclusive_ops(store, fixture=fixture, lock_dir=lock_dir):
        _ready(store, expected_username=expected_username,
               keychain_account_name=keychain_account_name, source_binding=source_binding,
               fixture=fixture)
        # Let the normal >24h idle reset recover first. A max-ID disposition is
        # durable, but its next-offset sentinel exceeds the Bot API integer
        # range: do not contact credentials/provider, clamp it, or drop backlog.
        state = store.prepare_poll(now=now)
        if state.next_offset is not None and state.next_offset > MAX_OPS_POLL_OFFSET:
            raise OpsRuntimeError("poll_offset_exhausted")
        api = _prepared_api(store, api, expected_username=expected_username,
                            keychain_account_name=keychain_account_name,
                            source_binding=source_binding, fixture=fixture)
        interrupted = store.mark_interrupted_replies()
        updates = api.get_ops_updates(offset=state.next_offset or 0, timeout=timeout, limit=20)
        # Validate the whole batch before advancing any offset. Sort valid IDs:
        # acknowledging a high ID before a failed lower item would lose work.
        if not isinstance(updates, list) or len(updates) > 20:
            raise OpsRuntimeError("invalid_update_batch")
        seen: set[int] = set()
        for item in updates:
            uid = item.get("update_id") if isinstance(item, Mapping) else None
            if (type(uid) is not int or not 0 <= uid < 1 << 31 or uid in seen
                    or ("message" in item and not isinstance(item["message"], Mapping))):
                raise OpsRuntimeError("invalid_update_batch")
            seen.add(uid)
        binding = store.binding()
        assert binding is not None
        service = TelegramOpsService(store, store, OpsServiceConfig(
            binding.operator_user_id, binding.operator_private_chat_id))
        replies, duplicates, ignored = [], 0, 0
        for update in sorted(updates, key=lambda item: item["update_id"]):
            result = store.process_update_once(update, service, polling_epoch=state.epoch, processed_at=now)
            duplicates += int(result.duplicate)
            if result.reply_id is not None:
                replies.append(result.reply_id)
            else:
                ignored += 1
        return {"mode": "fixture" if fixture else "live", "processed": len(updates),
                "duplicates": duplicates, "ignored": ignored, "reply_ids": replies,
                "poll_offset_exhausted": binding_report(store)["poll_offset_exhausted"],
                "interrupted_unknown": interrupted, "sends": 0, "batches": 1}


def reply_page(store: AgentToolOpsStore, *, state: str | None = None,
               after_reply_id: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Local metadata only, including terminal/inflight history after stdout loss.

    Read one extra row to distinguish a full final page from truncation. The
    immutable ordering cursor survives delivery-state changes; state filters
    describe current state, not a frozen snapshot across invocations.
    """
    if type(limit) is not int or not 1 <= limit <= 20:
        raise OpsRuntimeError("invalid_input")
    items = store.list_replies(state=state, after_reply_id=after_reply_id, limit=limit + 1)
    has_more = len(items) > limit
    items = items[:limit]
    return {"replies": [
                {"reply_id": item.reply_id, "state": item.state,
                 "binding_revision": item.binding_revision, "attempt_count": item.attempt_count}
                for item in items
            ],
            "state": state, "limit": limit, "after_reply_id": after_reply_id,
            "next_after_reply_id": items[-1].reply_id if has_more else None,
            "has_more": has_more, "truncated": has_more,
            "ordering": "queued_at ASC, reply_id ASC",
            "network_calls": 0, "credential_reads": 0,
            "next_step": "Use ops-replies with --state, --after-reply-id and --limit to page current states. "
                         "Only ops-send-once --reply-id REF previews text; no --apply is needed for preview."}


def local_status(store: AgentToolOpsStore) -> dict[str, Any]:
    """Render local projection health without returning cursor hashes or paths."""

    if not isinstance(store, AgentToolOpsStore):
        raise TypeError("store must be an AgentToolOpsStore")
    committed = store.committed_anchor()
    staged = store.staged_anchor()
    projection: dict[str, Any] | None
    if committed is not None and staged is None:
        projection = asdict(store.status_snapshot())
    else:
        # No source observation exists yet, or a durable page is still staged.
        # Do not fabricate a head/time or mix uncommitted derived state with
        # the prior committed head.
        projection = None
    journal_verification = (
        asdict(store.journal_verify()) if staged is None else None
    )
    projection_state = (
        "staged_unavailable"
        if staged is not None
        else "available"
        if committed is not None
        else "not_observed"
    )
    replies = reply_page(store)
    return {
        "schema": "kingdom.agenttool-ops/0.2",
        "transport": binding_report(store),
        "replies": replies["replies"],
        "reply_list_limit": replies["limit"],
        "reply_list_has_more": replies["has_more"],
        "reply_list_truncated": replies["truncated"],
        "reply_list_next_after_reply_id": replies["next_after_reply_id"],
        "reply_list_next_step": replies["next_step"],
        "database_role": "separate_owner_only_ops_projection",
        "cursor": {
            "initialized": committed is not None,
            "committed_sequence": committed.sequence if committed else None,
            "staged_page_pending": staged is not None,
        },
        "projection_state": projection_state,
        "projection": projection,
        "journal_verification": journal_verification,
        "outbox_counts": store.outbox_counts(),
        "agenttool_calls": 0,
        "telegram_calls": 0,
        "agent_lifecycle_actions": 0,
        "coordination_mutations": 0,
        "trades": 0,
    }


def preview_reply(store: AgentToolOpsStore, reply_id: str) -> dict[str, Any]:
    item = store.reply_item(reply_id)
    if item is None:
        raise OpsRuntimeError("invalid_input")
    state, binding = store.poll_state(), store.binding()
    eligible = (item.state == "pending" and state is not None and state.state == "active"
                and binding is not None and item.binding_revision == binding.revision)
    return {"apply": False, "reply_id": item.reply_id, "payload_digest": item.payload_digest,
            "binding_revision": item.binding_revision, "state": item.state,
            "attempt_count": item.attempt_count, "eligible": eligible, "text": item.text,
            "destination": "bound_private_operator", "protect_content": True,
            "network_calls": 0, "credential_reads": 0}


def _delivery_report(item: ReplyItem) -> dict[str, Any]:
    return {"reply_id": item.reply_id, "state": item.state,
            "attempt_count": item.attempt_count, "binding_revision": item.binding_revision,
            "receipt_present": item.receipt_ref is not None, "error_code": item.error_code,
            "retry_allowed": False}


def send_once(store: AgentToolOpsStore, api: Any = None, *, expected_username: str,
              reply_id: str, payload_digest: str, binding_revision: int,
              source_binding: str | None = None, keychain_account_name: str | None = None,
              fixture: bool = False, lock_dir: Path | None = None) -> dict[str, Any]:
    with exclusive_ops(store, fixture=fixture, lock_dir=lock_dir):
        # All offline preview/state checks precede credential access.
        store.mark_interrupted_replies()
        preview = preview_reply(store, reply_id)
        if (type(binding_revision) is not int or preview["binding_revision"] != binding_revision
                or preview["payload_digest"] != payload_digest):
            raise OpsRuntimeError("stale_preview")
        if not preview["eligible"]:
            raise OpsRuntimeError("reply_not_pending")
        api = _prepared_api(store, api, expected_username=expected_username,
                            keychain_account_name=keychain_account_name,
                            source_binding=source_binding, fixture=fixture)
        item = store.claim_reply(reply_id, payload_digest=payload_digest,
                                 binding_revision=binding_revision)
        state, code, receipt_ref = "unknown", "telegram_transport", None
        try:
            receipt = api.send_private_text(item.chat_id, item.text)
            chat = receipt.get("chat") if isinstance(receipt, Mapping) else None
            message_id = receipt.get("message_id") if isinstance(receipt, Mapping) else None
            if (not isinstance(chat, Mapping) or type(chat.get("id")) is not int
                    or chat["id"] != item.chat_id or chat.get("type") != "private"
                    or type(message_id) is not int or not 1 <= message_id <= (1 << 52) - 1):
                code = "invalid_receipt"
            else:
                state, code, receipt_ref = "sent", None, f"telegram-message:{message_id}"
        except TelegramError as exc:
            state = "unknown" if exc.ambiguous else "failed"
            code = ("forbidden" if exc.error_code == 403 else "rate_limited"
                    if exc.error_code == 429 else "telegram_transport" if exc.ambiguous
                    else "telegram_rejected")
        except TimeoutError:
            code = "telegram_timeout"
        except Exception:
            # Anything after the persisted claim may have crossed the provider
            # boundary. Never store raw exception strings or infer non-delivery.
            code = "telegram_transport"
        # BaseException (process crash/interrupt) deliberately leaves inflight;
        # the next locked operation marks it unknown, never pending.
        finished = store.finish_reply(reply_id, attempt_count=item.attempt_count,
                                      state=state, receipt_ref=receipt_ref, error_code=code)
        return {"apply": True, "send_attempts": 1, **_delivery_report(finished)}


def pause(store: AgentToolOpsStore, *, fixture: bool = False,
          lock_dir: Path | None = None) -> dict[str, Any]:
    with exclusive_ops(store, fixture=fixture, lock_dir=lock_dir):
        store.pause()
        return {**binding_report(store), "sends": 0, "agent_processes_stopped": 0}


def resume(store: AgentToolOpsStore, *, apply: bool = False, fixture: bool = False,
           lock_dir: Path | None = None, now: datetime | str | None = None) -> dict[str, Any]:
    if type(apply) is not bool:
        raise OpsRuntimeError("invalid_input")
    if now is not None and not fixture:
        raise OpsRuntimeError("unsafe_live_transport")
    with exclusive_ops(store, fixture=fixture, lock_dir=lock_dir):
        if store.poll_state() is None or store.poll_state().state != "paused":
            raise BindingStateError("only a paused Ops transport can resume")
        if apply:
            store.resume(resumed_at=now)
        return {"apply": apply, **binding_report(store), "old_replies_replayed": False,
                "new_command_required": True, "sends": 0,
                "next_step": "Send a new private command after resumption."}


def reconcile(store: AgentToolOpsStore, *, reply_id: str, attempt_count: int,
              outcome: str, reconciliation_ref: str, receipt_ref: str | None = None,
              fixture: bool = False, lock_dir: Path | None = None) -> dict[str, Any]:
    with exclusive_ops(store, fixture=fixture, lock_dir=lock_dir):
        store.mark_interrupted_replies()
        item = store.reconcile_reply(reply_id, attempt_count=attempt_count,
                                     outcome=outcome, reconciliation_ref=reconciliation_ref,
                                     receipt_ref=receipt_ref)
        return {**_delivery_report(item), "sends": 0, "observation_recorded": True}
