from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from telegram_gateway import bootstrap, ops_runtime as runtime, telegram_api
from telegram_gateway.agenttool_ops import AgentToolOpsStore, BindingStateError, CursorAnchor, DeliveryStateError
from telegram_gateway.bootstrap import OPS_BOT_PROFILE, desired_commands
from telegram_gateway.ops_service import OpsServiceConfig, TelegramOpsService
from telegram_gateway.telegram_api import TelegramAPI, TelegramError

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
OPERATOR = 77223311
BOT = 8001
USERNAME = "KingdomOpsBot"


class FakeAPI:
    provider_origin = "https://api.telegram.org"

    def __init__(self, updates=None):
        self.updates = [] if updates is None else updates
        self.calls = []
        self.sends = []
        self.identity = {"id": BOT, "is_bot": True, "username": USERNAME,
                         "can_join_groups": False, "can_read_all_group_messages": False}
        self.receipt = {"message_id": 17, "chat": {"id": OPERATOR, "type": "private"}}
        self.send_error = None
        self.on_send = None

    def get_me(self):
        self.calls.append("getMe")
        return dict(self.identity)

    def get_webhook_info(self):
        return {"configured": False}

    def get_my_commands(self, *, scope):
        return desired_commands(OPS_BOT_PROFILE) if scope["type"] == "all_private_chats" else []

    def get_my_name(self):
        return OPS_BOT_PROFILE.name

    def get_my_description(self):
        return OPS_BOT_PROFILE.description

    def get_my_short_description(self):
        return OPS_BOT_PROFILE.short_description

    def get_chat_menu_button_type(self):
        return "commands"

    def get_ops_updates(self, **kwargs):
        assert 0 <= kwargs["offset"] <= (1 << 31) - 1
        self.calls.append(("getUpdates", kwargs))
        return self.updates

    def send_private_text(self, chat_id, text):
        self.sends.append((chat_id, text))
        if self.on_send:
            self.on_send()
        if self.send_error:
            raise self.send_error
        return self.receipt


def command(uid=1, *, text="/start", date=None):
    return {"update_id": uid, "message": {
        "date": int(NOW.timestamp()) + 1 if date is None else date,
        "from": {"id": OPERATOR, "is_bot": False},
        "chat": {"id": OPERATOR, "type": "private"}, "text": text,
    }}


def bound_store(path: Path, *, verification="fixture"):
    store = AgentToolOpsStore(path)
    store.bind_operator(BOT, FakeAPI.provider_origin,
                        operator_user_id=OPERATOR, operator_private_chat_id=OPERATOR,
                        credential_ref=("fixture:runtime-test" if verification == "fixture"
                                        else runtime.credential_reference(USERNAME)),
                        source_binding="ws_runtime", verification=verification,
                        bound_at=NOW)
    return store


@pytest.fixture(autouse=True)
def no_external(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("credential or real transport access in offline runtime test")
    monkeypatch.setattr(runtime, "load_keychain_token", forbidden)
    monkeypatch.setattr(bootstrap, "load_keychain_token", forbidden)
    monkeypatch.setattr(telegram_api, "open_request", forbidden)
    monkeypatch.setattr(runtime, "DEFAULT_LOCK_DIRECTORY", tmp_path / "live-locks")


@pytest.fixture
def store(tmp_path):
    with bound_store(tmp_path / "state" / "ops.db") as opened:
        yield opened


@pytest.fixture
def options(tmp_path):
    return {"expected_username": USERNAME, "fixture": True,
            "lock_dir": tmp_path / "fixture-locks"}


def staged(store, options, api=None):
    api = FakeAPI([command()]) if api is None else api
    result = runtime.poll_once(store, api, now=NOW + timedelta(seconds=2), **options)
    rid = result["reply_ids"][0]
    preview = runtime.preview_reply(store, rid)
    return api, {key: preview[key] for key in ("reply_id", "payload_digest", "binding_revision")}


def test_poll_one_batch_stages_and_next_poll_acknowledges_only_committed(store, options):
    api = FakeAPI([command(20), command(10)])
    first = runtime.poll_once(store, api, now=NOW + timedelta(seconds=2), **options)
    assert first["processed"] == 2 and first["sends"] == 0 and first["batches"] == 1
    assert store.poll_state().next_offset == 21
    assert api.calls[-1] == ("getUpdates", {"offset": 0, "timeout": 0, "limit": 20})
    second = runtime.poll_once(store, api, now=NOW + timedelta(seconds=3), **options)
    assert second["duplicates"] == 2
    assert len(store.list_replies()) == 2 and not api.sends
    assert api.calls[-1][1]["offset"] == 21


@pytest.mark.parametrize("updates", [[command()] * 2, [command(True)], [command(-1)],
                                     [command(1 << 31)], [command(i) for i in range(21)],
                                     [{"private_sentinel": "DO_NOT_LEAK"}], {}, [None],
                                     [{"update_id": 1, "message": "malformed"}]])
def test_invalid_batch_changes_no_offset_or_replies(store, options, updates):
    api = FakeAPI(updates)
    with pytest.raises(runtime.OpsRuntimeError, match="invalid_update_batch"):
        runtime.poll_once(store, api, now=NOW + timedelta(seconds=2), **options)
    assert store.poll_state().next_offset is None and store.list_replies() == ()
    assert not api.sends


def test_failure_at_lower_id_cannot_acknowledge_later_update(store, options, monkeypatch):
    original = store.process_update_once
    def fail(update, service, **kwargs):
        if update["update_id"] == 2:
            raise RuntimeError("private command sentinel")
        return original(update, service, **kwargs)
    monkeypatch.setattr(store, "process_update_once", fail)
    api = FakeAPI([command(3), command(2), command(1)])
    with pytest.raises(RuntimeError):
        runtime.poll_once(store, api, now=NOW + timedelta(seconds=2), **options)
    assert store.poll_state().next_offset == 2
    assert len(store.list_replies()) == 1


def test_retention_idle_resets_offset_before_randomized_lower_id(store, options):
    api = FakeAPI([command(1000)])
    runtime.poll_once(store, api, now=NOW + timedelta(seconds=2), **options)
    old = store.poll_state().epoch
    api.updates = [command(3, date=int((NOW + timedelta(days=2)).timestamp()))]
    result = runtime.poll_once(store, api, now=NOW + timedelta(days=2, seconds=2), **options)
    assert api.calls[-1][1]["offset"] == 0
    assert store.poll_state().epoch > old
    assert store.poll_state().next_offset == 4
    assert result["duplicates"] == 0


def test_postbinding_private_human_only_and_no_raw_command_retention(store, options):
    updates = [command(1, date=int(NOW.timestamp())), command(2), command(3), command(4)]
    updates[1]["message"]["from"]["is_bot"] = True
    updates[2]["message"]["chat"]["type"] = "group"
    updates[3]["message"]["text"] = "/not_a_command DO_NOT_RETAIN_PRIVATE_TEXT"
    result = runtime.poll_once(store, FakeAPI(updates), now=NOW + timedelta(seconds=2), **options)
    assert result["ignored"] == 3 and len(result["reply_ids"]) == 1
    assert "DO_NOT_RETAIN_PRIVATE_TEXT" not in "\n".join(store.conn.iterdump())


def test_preview_and_one_send_use_exact_binding_and_committed_attempt(store, options):
    api, exact = staged(store, options)
    preview = runtime.preview_reply(store, exact["reply_id"])
    assert preview["eligible"] and preview["network_calls"] == 0
    def verify_claim():
        with AgentToolOpsStore(store.path) as other:
            item = other.reply_item(exact["reply_id"])
            assert item.state == "inflight" and item.attempt_count == 1
    api.on_send = verify_claim
    result = runtime.send_once(store, api, **exact, **options)
    assert result["state"] == "sent" and result["receipt_present"]
    assert result["send_attempts"] == 1 and result["retry_allowed"] is False
    assert api.sends == [(OPERATOR, preview["text"])]
    with pytest.raises(runtime.OpsRuntimeError, match="reply_not_pending"):
        runtime.send_once(store, api, **exact, **options)
    assert len(api.sends) == 1


@pytest.mark.parametrize("field,value", [("payload_digest", "sha256:" + "0" * 64),
                                         ("binding_revision", 2), ("binding_revision", True)])
def test_stale_exact_preview_fails_before_api_access(store, options, field, value):
    api, exact = staged(store, options)
    api.calls.clear()
    exact[field] = value
    with pytest.raises(runtime.OpsRuntimeError, match="stale_preview"):
        runtime.send_once(store, api, **exact, **options)
    assert not api.calls and not api.sends


@pytest.mark.parametrize("error,state,code", [
    (TelegramError("SECRET rejected", error_code=403), "failed", "forbidden"),
    (TelegramError("SECRET rate", error_code=429), "failed", "rate_limited"),
    (TelegramError("SECRET rejected"), "failed", "telegram_rejected"),
    (TelegramError("SECRET accepted maybe", ambiguous=True), "unknown", "telegram_transport"),
    (TimeoutError("SECRET"), "unknown", "telegram_timeout"),
    (OSError("SECRET path"), "unknown", "telegram_transport"),
    (ValueError("SECRET malformed"), "unknown", "telegram_transport"),
])
def test_send_failures_are_closed_terminal_evidence(store, options, error, state, code):
    api, exact = staged(store, options)
    api.send_error = error
    result = runtime.send_once(store, api, **exact, **options)
    assert result["state"] == state and result["error_code"] == code
    assert "SECRET" not in json.dumps(result)
    assert "SECRET" not in "\n".join(store.conn.iterdump())
    with pytest.raises(runtime.OpsRuntimeError, match="reply_not_pending"):
        runtime.send_once(store, api, **exact, **options)
    assert len(api.sends) == 1


@pytest.mark.parametrize("receipt", [None, {}, {"message_id": True},
    {"message_id": 1, "chat": {"id": OPERATOR + 1, "type": "private"}},
    {"message_id": 1, "chat": {"id": OPERATOR, "type": "group"}},
])
def test_invalid_receipt_is_unknown_never_failed(store, options, receipt):
    api, exact = staged(store, options)
    api.receipt = receipt
    result = runtime.send_once(store, api, **exact, **options)
    assert result["state"] == "unknown" and result["error_code"] == "invalid_receipt"


def test_interrupted_inflight_becomes_unknown_without_automatic_retry(store, options):
    api, exact = staged(store, options)
    api.send_error = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        runtime.send_once(store, api, **exact, **options)
    assert store.reply_item(exact["reply_id"]).state == "inflight"
    api.calls.clear()
    with pytest.raises(runtime.OpsRuntimeError, match="reply_not_pending"):
        runtime.send_once(store, api, **exact, **options)
    assert store.reply_item(exact["reply_id"]).state == "unknown"
    assert len(api.sends) == 1 and api.calls == []


def test_reconciliation_is_local_fenced_and_not_retry_permission(store, options):
    api, exact = staged(store, options)
    api.send_error = TelegramError("timeout", ambiguous=True)
    runtime.send_once(store, api, **exact, **options)
    local = {key: options[key] for key in ("fixture", "lock_dir")}
    for ref in (None, "", " ", "/private/path"):
        with pytest.raises(ValueError):
            runtime.reconcile(store, reply_id=exact["reply_id"], attempt_count=1,
                              outcome="unknown", reconciliation_ref=ref, **local)
    with pytest.raises(DeliveryStateError):
        runtime.reconcile(store, reply_id=exact["reply_id"], attempt_count=2,
                          outcome="sent", reconciliation_ref="check:1", receipt_ref="message:17", **local)
    result = runtime.reconcile(store, reply_id=exact["reply_id"], attempt_count=1,
                               outcome="sent", reconciliation_ref="check:1", receipt_ref="message:17", **local)
    assert result["state"] == "sent" and result["sends"] == 0 and len(api.sends) == 1
    assert store.reply_attempts(exact["reply_id"])[0]["state"] == "unknown"


def test_pause_and_explicit_resume_invalidate_queue_and_reset_cutoff(store, options):
    api, exact = staged(store, options)
    local = {key: options[key] for key in ("fixture", "lock_dir")}
    paused = runtime.pause(store, **local)
    assert paused["state"] == "paused"
    assert store.reply_item(exact["reply_id"]).state == "invalidated"
    api.calls.clear()
    with pytest.raises(BindingStateError):
        runtime.poll_once(store, api, **options)
    with pytest.raises(runtime.OpsRuntimeError):
        runtime.send_once(store, api, **exact, **options)
    assert api.calls == [] and api.sends == []
    preview = runtime.resume(store, **local)
    assert preview["apply"] is False and store.poll_state().state == "paused"
    result = runtime.resume(store, apply=True, now=NOW + timedelta(seconds=10), **local)
    assert result["binding_revision"] == 2 and result["old_replies_replayed"] is False
    api.updates = [command(2, date=int(NOW.timestamp()) + 10), command(3, date=int(NOW.timestamp()) + 11)]
    result = runtime.poll_once(store, api, now=NOW + timedelta(seconds=12), **options)
    assert result["ignored"] == 1 and len(result["reply_ids"]) == 1


def test_send_and_pause_share_lock_so_completed_pause_cannot_race_later_send(store, options):
    api, exact = staged(store, options)
    local = {key: options[key] for key in ("fixture", "lock_dir")}
    def while_sending():
        with AgentToolOpsStore(store.path) as other:
            with pytest.raises(runtime.OpsRuntimeError, match="local_lock_busy"):
                runtime.pause(other, **local)
    api.on_send = while_sending
    assert runtime.send_once(store, api, **exact, **options)["state"] == "sent"
    assert runtime.pause(store, **local)["state"] == "paused"
    assert len(api.sends) == 1


def test_same_provider_different_databases_contend_and_lock_permissions(store, options, tmp_path):
    local = {key: options[key] for key in ("fixture", "lock_dir")}
    with bound_store(tmp_path / "other-state" / "ops.db") as other:
        with runtime.exclusive_ops(store, **local):
            with pytest.raises(runtime.OpsRuntimeError, match="local_lock_busy"):
                with runtime.exclusive_ops(other, **local):
                    pytest.fail("second provider runner acquired lock")
    assert stat.S_IMODE(options["lock_dir"].stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in options["lock_dir"].iterdir())


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "public", "fifo"])
def test_unsafe_db_lock_refused_without_chmod_or_secret(store, options, tmp_path, kind):
    lock = Path(str(store.path) + ".run.lock")
    target = tmp_path / "target"
    target.write_text("private sentinel")
    if kind == "symlink":
        lock.symlink_to(target)
    elif kind == "hardlink":
        os.link(target, lock)
    elif kind == "public":
        lock.write_text("not private")
        lock.chmod(0o644)
    else:
        os.mkfifo(lock, 0o600)
    api = FakeAPI()
    with pytest.raises((runtime.OpsRuntimeError, OSError)):
        runtime.poll_once(store, api, **options)
    assert target.read_text() == "private sentinel" and api.calls == []
    if kind == "public":
        assert stat.S_IMODE(lock.stat().st_mode) == 0o644


def test_fixture_binding_refused_live_before_credentials(store):
    with pytest.raises(BindingStateError, match="fixture binding"):
        runtime.poll_once(store, expected_username=USERNAME, source_binding="ws_runtime")


def test_fixture_mode_requires_explicit_fake_api_and_temp_locks(store, options):
    with pytest.raises(runtime.OpsRuntimeError, match="fixture_transport_required"):
        runtime.poll_once(store, expected_username=USERNAME, fixture=True)
    for api in (None, TelegramAPI("fixture-only-token-123456789")):
        with pytest.raises(runtime.OpsRuntimeError, match="fixture_transport_required"):
            runtime.poll_once(store, api, **options)


def test_verified_store_refuses_fixture_downgrade_before_provider(tmp_path, options):
    with bound_store(tmp_path / "verified" / "ops.db", verification="verified") as store:
        api = FakeAPI()
        with pytest.raises(runtime.OpsRuntimeError, match="fixture_transport_required"):
            runtime.poll_once(store, api, **options)
        assert not api.calls


def test_wrong_numeric_provider_fails_before_poll_or_profile(store, options):
    api = FakeAPI()
    api.identity["id"] = BOT + 1
    with pytest.raises(BindingStateError):
        runtime.poll_once(store, api, **options)
    assert api.calls == ["getMe"]


@pytest.mark.parametrize("kwargs", [{"source_binding": "wrong"}, {"keychain_account_name": "other-slot"}, {}])
def test_live_binding_expectations_checked_before_credentials(tmp_path, kwargs):
    with bound_store(tmp_path / "verified" / "ops.db", verification="verified") as store:
        with pytest.raises((BindingStateError, runtime.OpsRuntimeError)):
            runtime.poll_once(store, expected_username=USERNAME, **kwargs)


def test_live_runtime_rejects_injected_opener_and_fake_class(tmp_path):
    with bound_store(tmp_path / "verified" / "ops.db", verification="verified") as store:
        candidates = [FakeAPI(), TelegramAPI("fixture-only-token-123456789", request_opener=lambda *a, **k: None,
                                             require_production_origin=True),
                      TelegramAPI("fixture-only-token-123456789")]
        for api in candidates:
            with pytest.raises(runtime.OpsRuntimeError, match="unsafe_live_transport"):
                runtime.poll_once(store, api, expected_username=USERNAME, source_binding="ws_runtime")


def test_invalid_origin_rejected_before_keychain(tmp_path, monkeypatch):
    with bound_store(tmp_path / "verified" / "ops.db", verification="verified") as store:
        monkeypatch.setattr(runtime, "PRODUCTION_TELEGRAM_ORIGIN", "https://not-telegram.invalid")
        with pytest.raises(TelegramError):
            runtime.poll_once(store, expected_username=USERNAME, source_binding="ws_runtime")


def test_dedicated_live_loader_never_resolves_environment(monkeypatch):
    reads = []
    monkeypatch.setenv("KINGDOM_TELEGRAM_BOT_TOKEN", "DO_NOT_USE_RESEARCH_ENVIRONMENT")
    def fake_load(username, **kwargs):
        reads.append((username, kwargs))
        return "credential-free-placeholder-token"
    monkeypatch.setattr(runtime, "load_keychain_token", fake_load)
    api = runtime._load_api(USERNAME, "version-2")
    assert reads == [(USERNAME, {"keychain_account_name": "version-2",
                                "keychain_service": bootstrap.OPS_KEYCHAIN_SERVICE})]
    assert api.request_opener is None and api.require_production_origin is True
    assert "DO_NOT_USE_RESEARCH_ENVIRONMENT" not in repr(api)


@pytest.mark.parametrize("mode", ["symlink", "public"])
def test_provider_lock_root_refuses_unsafe_directory(store, options, tmp_path, mode):
    root = options["lock_dir"]
    if mode == "symlink":
        target = tmp_path / "other-owner-state"
        target.mkdir(mode=0o700)
        root.symlink_to(target, target_is_directory=True)
    else:
        root.mkdir(mode=0o755)
        root.chmod(0o755)
    api = FakeAPI()
    with pytest.raises(runtime.OpsRuntimeError, match="unsafe_local_lock"):
        runtime.poll_once(store, api, **options)
    assert api.calls == []
    if mode == "symlink":
        assert list(target.iterdir()) == []
    else:
        assert stat.S_IMODE(root.stat().st_mode) == 0o755


def test_live_clock_or_lock_override_is_not_a_fixture_shortcut(store, tmp_path):
    with pytest.raises(runtime.OpsRuntimeError, match="unsafe_live_transport"):
        runtime.poll_once(store, expected_username=USERNAME, now=NOW)
    with pytest.raises(runtime.OpsRuntimeError, match="unsafe_live_transport"):
        runtime.poll_once(store, expected_username=USERNAME, lock_dir=tmp_path / "override")
    with pytest.raises(runtime.OpsRuntimeError, match="unsafe_live_transport"):
        runtime.bind_operator(store, expected_username=USERNAME, bot_id=BOT,
                              operator_user_id=OPERATOR, operator_private_chat_id=OPERATOR,
                              source_binding="ws_runtime", bound_at=NOW)


def test_binding_preview_checks_complete_numeric_source_and_slot_tuple(store, options):
    # An existing fixture cannot become a verified binding or silently transfer
    # its source/destination while preserving its old reply backlog.
    with pytest.raises(runtime.OpsRuntimeError, match="binding_mismatch"):
        runtime.bind_operator(store, expected_username=USERNAME, bot_id=BOT,
                              operator_user_id=OPERATOR, operator_private_chat_id=OPERATOR,
                              source_binding="ws_runtime")
    with pytest.raises(ValueError):
        runtime.bind_operator(store, expected_username=USERNAME, bot_id=BOT,
                              operator_user_id=OPERATOR, operator_private_chat_id=OPERATOR + 1,
                              source_binding="ws_runtime")


@pytest.mark.parametrize("population", ["seed", "verification", "legacy_claim"])
@pytest.mark.parametrize("source", ["ws_source_a", "ws_source_b"])
@pytest.mark.parametrize("fixture", [False, True])
def test_populated_unbound_store_refuses_before_any_credentials_or_provider(
    tmp_path, population, source, fixture,
):
    with AgentToolOpsStore(tmp_path / "unbound" / "ops.db") as store:
        if population == "seed":
            anchor = CursorAnchor("epoch_source_a", 1, "1" * 64)
            store.stage_page(current_anchor=anchor, next_anchor=anchor, events=())
        elif population == "verification":
            store.record_journal_verification(outcome="valid", checked_at=NOW,
                                              journal_head_sequence=1,
                                              scope_code="full_collab_hash_chain")
        else:
            store.claim_update(1)
        before = "\n".join(store.conn.iterdump())
        api = FakeAPI()
        options = {"fixture": True, "api": api, "lock_dir": tmp_path / "locks"} if fixture else {}
        for apply in (False, True):
            with pytest.raises(runtime.OpsRuntimeError, match="initial_binding_requires_empty_store"):
                runtime.bind_operator(store, expected_username=USERNAME, bot_id=BOT,
                                      operator_user_id=OPERATOR, operator_private_chat_id=OPERATOR,
                                      source_binding=source, apply=apply, **options)
            assert store.binding() is None and store.poll_state() is None
            assert "\n".join(store.conn.iterdump()) == before
        assert not api.calls and not api.sends


def test_initial_binding_preflight_is_rechecked_after_lock_before_provider(tmp_path, monkeypatch):
    from contextlib import contextmanager

    original_lock = runtime.exclusive_ops
    with AgentToolOpsStore(tmp_path / "unbound" / "ops.db") as store:
        @contextmanager
        def changed_before_lock(*args, **kwargs):
            with original_lock(*args, **kwargs):
                # Simulate an observer committing before this invocation got the lock.
                store.claim_update(11)
                yield
        monkeypatch.setattr(runtime, "exclusive_ops", changed_before_lock)
        api = FakeAPI()
        with pytest.raises(runtime.OpsRuntimeError, match="initial_binding_requires_empty_store"):
            runtime.bind_operator(store, expected_username=USERNAME, bot_id=BOT,
                                  operator_user_id=OPERATOR, operator_private_chat_id=OPERATOR,
                                  source_binding="ws_runtime", apply=True, api=api,
                                  fixture=True, lock_dir=tmp_path / "locks")
        assert store.binding() is None and api.calls == []
        assert not store.claim_update(11)


def test_fresh_binding_preflight_rechecks_in_store_transaction_and_existing_binding_is_usable(
    tmp_path, monkeypatch,
):
    with AgentToolOpsStore(tmp_path / "fresh" / "ops.db") as store:
        checks = []
        original = store.assert_initial_binding_allowed
        def checked():
            checks.append(store.conn.in_transaction)
            original()
        monkeypatch.setattr(store, "assert_initial_binding_allowed", checked)
        args = dict(expected_username=USERNAME, bot_id=BOT, operator_user_id=OPERATOR,
                    operator_private_chat_id=OPERATOR, source_binding="ws_runtime",
                    api=FakeAPI(), fixture=True, lock_dir=tmp_path / "locks", bound_at=NOW)
        assert runtime.bind_operator(store, apply=True, **args)["bound"]
        assert checks == [False, False, True]
        # Once bound, local observations do not block an identical rebind/preview.
        store.record_journal_verification(outcome="valid", checked_at=NOW,
                                          journal_head_sequence=0, scope_code="full_collab_hash_chain")
        assert runtime.bind_operator(store, **args)["binding_matches"]
        assert runtime.bind_operator(store, apply=True, **args)["binding_revision"] == 1


@pytest.mark.parametrize("randomized_id", [3, (1 << 31) - 1])
def test_max_update_id_is_durable_exhaustion_is_local_and_idle_reset_recovers(
    store, options, randomized_id,
):
    maximum = (1 << 31) - 1
    api = FakeAPI([command(maximum)])
    result = runtime.poll_once(store, api, now=NOW + timedelta(seconds=2), **options)
    rid = result["reply_ids"][0]
    epoch = store.poll_state().epoch
    assert result["poll_offset_exhausted"] is True and result["sends"] == 0
    assert store.poll_state().next_offset == 1 << 31
    assert store.reply_item(rid).update_id == maximum
    before = "\n".join(store.conn.iterdump())
    api.calls.clear()
    # Reopening also preserves the explicit exhausted state, without a replay or
    # timestamp refresh that could keep extending the >24h recovery interval.
    with AgentToolOpsStore(store.path) as reopened:
        for seconds in (3, 3_600, 86_402):
            with pytest.raises(runtime.OpsRuntimeError, match="poll_offset_exhausted"):
                runtime.poll_once(reopened, api, now=NOW + timedelta(seconds=seconds), **options)
            assert "\n".join(reopened.conn.iterdump()) == before
        assert not api.calls and not api.sends
        assert runtime.preview_reply(reopened, rid)["eligible"]
        reset_time = NOW + timedelta(seconds=86_404)
        api.updates = [command(randomized_id, date=int(reset_time.timestamp()))]
        recovered = runtime.poll_once(reopened, api, now=reset_time, **options)
        assert api.calls[-1][1]["offset"] == 0
        assert recovered["duplicates"] == 0 and recovered["reply_ids"] != [rid]
        assert reopened.poll_state().epoch == epoch + 1
        assert reopened.poll_state().next_offset == randomized_id + 1
        assert len(reopened.list_replies()) == 2 and not api.sends


def test_live_exhausted_poll_checks_ready_and_prepares_under_lock_before_credentials(tmp_path, monkeypatch):
    with bound_store(tmp_path / "verified" / "ops.db", verification="verified") as store:
        now = datetime.now(timezone.utc)
        service = TelegramOpsService(store, store, OpsServiceConfig(OPERATOR, OPERATOR))
        store.process_update_once(command((1 << 31) - 1, date=int(now.timestamp()) + 1),
                                  service, polling_epoch=store.poll_state().epoch, processed_at=now)
        prepared = []
        original = store.prepare_poll
        def prepare(**kwargs):
            with pytest.raises(runtime.OpsRuntimeError, match="local_lock_busy"):
                with runtime.exclusive_ops(store):
                    pytest.fail("poll preparation was not locked")
            prepared.append(True)
            return original(**kwargs)
        monkeypatch.setattr(store, "prepare_poll", prepare)
        with pytest.raises(BindingStateError):
            runtime.poll_once(store, expected_username=USERNAME, source_binding="wrong")
        assert not prepared  # Local readiness precedes even the idle reset.
        before = "\n".join(store.conn.iterdump())
        with pytest.raises(runtime.OpsRuntimeError, match="poll_offset_exhausted"):
            runtime.poll_once(store, expected_username=USERNAME, source_binding="ws_runtime")
        assert prepared == [True]
        assert "\n".join(store.conn.iterdump()) == before


@pytest.mark.parametrize("limit", [0, 21, -1, True, 1.0, None, "20"])
def test_reply_page_rejects_invalid_limit_locally(store, limit):
    with pytest.raises(runtime.OpsRuntimeError, match="invalid_input"):
        runtime.reply_page(store, limit=limit)


def test_reply_page_exact_final_page_and_changed_state_cursor_are_read_only(store, options):
    api = FakeAPI([command(uid) for uid in range(1, 21)])
    runtime.poll_once(store, api, now=NOW + timedelta(seconds=2), **options)
    first = runtime.reply_page(store, state="pending", limit=1)
    cursor = first["next_after_reply_id"]
    assert first["has_more"] is first["truncated"] is True
    item = store.reply_item(cursor)
    store.claim_reply(cursor, payload_digest=item.payload_digest, binding_revision=item.binding_revision)
    before = "\n".join(store.conn.iterdump())
    final = runtime.reply_page(store, state="pending", after_reply_id=cursor, limit=19)
    assert len(final["replies"]) == 19
    assert final["has_more"] is final["truncated"] is False
    assert final["next_after_reply_id"] is None
    assert cursor not in [item["reply_id"] for item in final["replies"]]
    inflight = runtime.reply_page(store, state="inflight")
    assert inflight["replies"][0]["reply_id"] == cursor
    assert "text" not in inflight["replies"][0]
    assert "\n".join(store.conn.iterdump()) == before


def test_local_status_empty_store_exact_contract(tmp_path):
    with AgentToolOpsStore(tmp_path / "unbound" / "ops.db") as store:
        assert runtime.local_status(store) == {
            "schema": "kingdom.agenttool-ops/0.2",
            "transport": {
                "bound": False, "binding_revision": None, "verification": None,
                "state": "unbound", "poll_offset_exhausted": False,
                "event_alerts_enabled": False,
                "lock_scope": "cooperating_local_processes_only",
            },
            "replies": [], "reply_list_limit": 20,
            "reply_list_has_more": False, "reply_list_truncated": False,
            "reply_list_next_after_reply_id": None,
            "reply_list_next_step": (
                "Use ops-replies with --state, --after-reply-id and --limit to page current states. "
                "Only ops-send-once --reply-id REF previews text; no --apply is needed for preview."
            ),
            "database_role": "separate_owner_only_ops_projection",
            "cursor": {"initialized": False, "committed_sequence": None, "staged_page_pending": False},
            "projection_state": "not_observed", "projection": None,
            "journal_verification": {
                "outcome": "unavailable", "checked_at": "not performed",
                "journal_head_sequence": None,
                "verification_scope": "offline page linkage only; Collab hash recomputation not performed",
            },
            "outbox_counts": {"pending": 0, "inflight": 0, "sent": 0, "failed": 0, "unknown": 0},
            "agenttool_calls": 0, "telegram_calls": 0, "agent_lifecycle_actions": 0,
            "coordination_mutations": 0, "trades": 0,
        }


@pytest.mark.parametrize("transport", ["unbound", "active", "paused"])
@pytest.mark.parametrize("projection_state", ["not_observed", "available", "staged_unavailable"])
def test_local_status_projection_states_are_read_only_and_zero_external(
    tmp_path, monkeypatch, transport, projection_state,
):
    import socket
    import subprocess
    from dataclasses import asdict

    def forbidden(*args, **kwargs):
        pytest.fail("local status reached a runtime lock, live readiness, credential or external process")

    for name in ("_ready", "_load_api", "exclusive_ops", "exclusive_database"):
        monkeypatch.setattr(runtime, name, forbidden)
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)

    path = tmp_path / "private-status" / "ops.db"
    opened = AgentToolOpsStore(path) if transport == "unbound" else bound_store(path)
    with opened as store:
        initial = CursorAnchor("epoch_private_status", 5, "5" * 64)
        terminal = CursorAnchor(initial.epoch_id, 6, "6" * 64)
        if projection_state != "not_observed":
            store.stage_page(current_anchor=initial, next_anchor=terminal, events=({
                "protocol": "agenttool.collab/0.2", "epoch_id": initial.epoch_id,
                "sequence": 6, "type": "task.created", "entity_id": "task_private_status",
                "occurred_at": NOW.isoformat(), "payload": {"version": 1},
                "prev_hash": initial.hash, "hash": terminal.hash,
            },), staged_at=NOW)
            if projection_state == "available":
                store.commit_staged_cursor(terminal)
        store.record_journal_verification(outcome="valid", checked_at=NOW,
                                          journal_head_sequence=6, scope_code="full_collab_hash_chain")
        if transport == "paused":
            store.pause()
        if projection_state != "available":
            monkeypatch.setattr(store, "status_snapshot", forbidden)
        if projection_state == "staged_unavailable":
            monkeypatch.setattr(store, "journal_verify", forbidden)
        before = "\n".join(store.conn.iterdump())
        store.conn.execute("PRAGMA query_only=ON")
        result = runtime.local_status(store)
        assert "\n".join(store.conn.iterdump()) == before
        assert result["transport"]["state"] == transport
        assert result["projection_state"] == projection_state
        assert result["cursor"] == {
            "initialized": projection_state != "not_observed",
            "committed_sequence": 6 if projection_state == "available" else
                                  5 if projection_state == "staged_unavailable" else None,
            "staged_page_pending": projection_state == "staged_unavailable",
        }
        if projection_state == "available":
            snapshot = asdict(store.status_snapshot())
            assert datetime.fromisoformat(result["projection"]["observed_at"]).tzinfo is not None
            snapshot["observed_at"] = result["projection"]["observed_at"]
            assert result["projection"] == snapshot
            assert result["projection"]["open_tasks"] == 1
        else:
            assert result["projection"] is None
        assert result["journal_verification"] == (
            None if projection_state == "staged_unavailable" else asdict(store.journal_verify())
        )
        assert result["outbox_counts"]["pending"] == (1 if projection_state == "available" else 0)
        for key in ("agenttool_calls", "telegram_calls", "agent_lifecycle_actions", "coordination_mutations", "trades"):
            assert result[key] == 0
        for sentinel in (str(path), initial.epoch_id, initial.hash, terminal.hash,
                         "task_private_status", str(OPERATOR), "ws_runtime", "fixture:runtime-test"):
            assert sentinel not in json.dumps(result)
        assert not Path(str(path) + ".run.lock").exists()
        assert not runtime.DEFAULT_LOCK_DIRECTORY.exists()


def test_local_status_reply_page_is_metadata_only_and_preserves_inflight(store, options):
    service = TelegramOpsService(store, store, OpsServiceConfig(OPERATOR, OPERATOR))
    for uid in range(1, 22):
        store.process_update_once(command(uid), service, polling_epoch=store.poll_state().epoch,
                                  processed_at=NOW + timedelta(seconds=uid + 1))
    items = store.list_replies(limit=21)
    for item, outcome in zip(items, ("sent", "unknown", "inflight")):
        store.claim_reply(item.reply_id, payload_digest=item.payload_digest,
                          binding_revision=item.binding_revision)
        if outcome != "inflight":
            store.finish_reply(item.reply_id, attempt_count=1, state=outcome,
                               receipt_ref="private-receipt" if outcome == "sent" else None,
                               error_code="telegram_transport" if outcome == "unknown" else None)
    items = store.list_replies(limit=21)
    before = "\n".join(store.conn.iterdump())
    # Inspection does not contend on the transport locks or recover attempts.
    with runtime.exclusive_ops(store, fixture=True, lock_dir=options["lock_dir"]):
        store.conn.execute("PRAGMA query_only=ON")
        result = runtime.local_status(store)
    assert result["replies"] == [
        {"reply_id": item.reply_id, "state": item.state,
         "binding_revision": item.binding_revision, "attempt_count": item.attempt_count}
        for item in items[:20]
    ]
    assert result["reply_list_limit"] == 20
    assert result["reply_list_has_more"] is result["reply_list_truncated"] is True
    assert result["reply_list_next_after_reply_id"] == items[19].reply_id
    for sentinel in (items[0].text, items[0].payload_digest, "private-receipt", str(OPERATOR)):
        assert sentinel not in json.dumps(result)
    assert "\n".join(store.conn.iterdump()) == before


@pytest.mark.parametrize("value", [None, object(), {}])
def test_local_status_requires_ops_store(value):
    with pytest.raises(TypeError, match="^store must be an AgentToolOpsStore$"):
        runtime.local_status(value)


def test_runtime_import_needs_no_cli_sdk_database_or_external_effects(tmp_path):
    import subprocess
    import sys

    code = """
import fcntl, os, sqlite3, subprocess, sys

class LocalOnlyImports:
    def find_spec(self, fullname, path=None, target=None):
        assert fullname != "telegram_gateway.cli", fullname
        if fullname.partition(".")[0] not in sys.stdlib_module_names | {"telegram_gateway"}:
            raise ModuleNotFoundError("nonstandard imports disabled")

sys.meta_path.insert(0, LocalOnlyImports())
def forbidden(*args, **kwargs):
    raise AssertionError("import attempted an external or stateful effect")

def audit(event, args):
    if event.startswith("socket."):
        forbidden()

sys.addaudithook(audit)
sqlite3.connect = fcntl.flock = os.open = os.mkdir = os.chmod = forbidden
subprocess.Popen = subprocess.run = subprocess.call = subprocess.check_call = subprocess.check_output = forbidden
sys.path.insert(0, sys.argv[1])
from telegram_gateway import ops_runtime
assert callable(ops_runtime.local_status)
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-S", "-c", code, str(Path(__file__).resolve().parents[1])],
        cwd=tmp_path, env={"PATH": os.defpath, "HOME": str(tmp_path)},
        capture_output=True, text=True, timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == completed.stderr == ""
    assert list(tmp_path.iterdir()) == []
