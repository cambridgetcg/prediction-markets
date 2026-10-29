"""Offline handler tests. Internal monkeypatches are not a public transport mode."""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import threading
import urllib.parse
import urllib.request
from datetime import timedelta
from pathlib import Path

import anyio
import pytest
from mcp import types
from mcp.shared.message import SessionMessage, ServerMessageMetadata
from pydantic import ValidationError

from telegram_gateway import bootstrap, ops_mcp as mcp, ops_runtime as runtime, telegram_api
from telegram_gateway.agenttool_ops import AgentToolOpsStore
from telegram_gateway.ops_service import OpsServiceConfig, TelegramOpsService
from test_telegram_ops_runtime import BOT, NOW, OPERATOR, USERNAME, FakeAPI, command

SENTINEL = "DO_NOT_LEAK_MCP_PRIVATE_SENTINEL"


@pytest.fixture(autouse=True)
def no_external(monkeypatch, tmp_path):
    root = tmp_path.resolve()
    original_connect = sqlite3.connect
    denied = []

    def forbidden(*args, **kwargs):
        denied.append(True)
        raise AssertionError(SENTINEL)

    def connect(path, *args, **kwargs):
        value = str(path)
        location = urllib.parse.unquote(urllib.parse.urlsplit(value).path) if value.startswith("file:") else value
        assert Path(location).resolve().is_relative_to(root), "nonfixture DB access"
        return original_connect(path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", connect)
    monkeypatch.setattr(bootstrap, "load_keychain_token", forbidden)
    monkeypatch.setattr(runtime, "load_keychain_token", forbidden)
    monkeypatch.setattr(telegram_api, "open_request", forbidden)
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    for name in ("create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(runtime, "DEFAULT_LOCK_DIRECTORY", root / "never-live-locks")
    monkeypatch.setattr(mcp, "CONFIG_PATH", root / "config" / "mcp.json")
    yield
    assert denied == []


def config(path, capabilities=(), **kwargs):
    return mcp.Configuration(config=mcp.Config(
        db_path=str(path), capabilities=tuple(capabilities), **kwargs))


def call(gateway, name, arguments=None):
    async def invoke():
        return await gateway.call_tool(None, types.CallToolRequestParams(name=name, arguments=arguments))
    return anyio.run(invoke)


def data(result):
    assert json.loads(result.content[0].text) == result.structured_content
    return result.structured_content


@pytest.fixture
def account():
    return None


@pytest.fixture
def state(tmp_path, account):
    path = tmp_path.resolve() / "state" / "ops.db"
    with AgentToolOpsStore(path) as store:
        store.bind_operator(BOT, FakeAPI.provider_origin,
                            operator_user_id=OPERATOR, operator_private_chat_id=OPERATOR,
                            credential_ref=runtime.credential_reference(USERNAME, account),
                            source_binding="ws_runtime", verification="fixture", bound_at=NOW)
        service = TelegramOpsService(store, store, OpsServiceConfig(OPERATOR, OPERATOR))
        for uid in range(1, 4):
            store.process_update_once(command(uid), service, polling_epoch=store.poll_state().epoch,
                                      processed_at=NOW + timedelta(seconds=uid + 1))
        reply_ids = [item.reply_id for item in store.list_replies()]
    return path, reply_ids


@pytest.fixture
def live_shape(state, tmp_path, monkeypatch):
    path, reply_ids = state
    api = FakeAPI([command(10)])
    for name in ("poll_once", "send_once", "pause", "reconcile"):
        original = getattr(runtime, name)

        def wrapped(store, _name=name, _fn=original, **kwargs):
            kwargs.update(fixture=True, lock_dir=tmp_path.resolve() / "fixture-locks")
            if _name in {"poll_once", "send_once"}:
                kwargs["api"] = api
            if _name == "poll_once":
                kwargs["now"] = NOW + timedelta(seconds=20)
            return _fn(store, **kwargs)

        monkeypatch.setattr(runtime, name, wrapped)
    cfg = config(path, ("poll", "send", "reconcile"), expected_bot_username=USERNAME,
                 source_binding="ws_runtime", keychain_account_name=USERNAME.lower())
    return mcp.Gateway(cfg), api, reply_ids


def test_startup_discovery_missing_config_no_state_or_locks(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("startup/discovery touched the runtime")
    monkeypatch.setattr(AgentToolOpsStore, "open_existing", forbidden)
    for name in ("local_status", "exclusive_ops", "_load_api"):
        monkeypatch.setattr(runtime, name, forbidden)
    gateway = mcp.Gateway(mcp._load_configuration())
    tools = anyio.run(gateway.list_tools, None, None).tools
    assert [tool.name for tool in tools] == ["ops_status", "ops_replies", "ops_reply_preview"]
    assert data(call(gateway, "ops_status"))["status"] == "not_configured"
    assert data(call(gateway, "ops_replies"))["error"] == "not_configured"
    assert list(tmp_path.iterdir()) == []
    for tool in tools:
        assert tool.input_schema["additionalProperties"] is False
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.open_world_hint is False
    assert tools[-1].meta == {"anthropic/requiresUserInteraction": True}


@pytest.mark.parametrize("capabilities,extra", [
    ((), set()), (("pause",), {"ops_pause"}),
    (("poll",), {"ops_poll_once", "ops_pause"}),
    (("send",), {"ops_reply_send", "ops_pause"}),
    (("reconcile",), {"ops_reconcile", "ops_pause"}),
])
def test_explicit_inventory_and_dispatch_denial_before_runtime(tmp_path, monkeypatch, capabilities, extra):
    def forbidden(*args, **kwargs):
        pytest.fail("disabled tool reached runtime")
    monkeypatch.setattr(AgentToolOpsStore, "open_existing", forbidden)
    gateway = mcp.Gateway(config(tmp_path / "absent.db", capabilities,
        expected_bot_username=USERNAME, source_binding="ws_runtime", keychain_account_name=USERNAME.lower()))
    tools = anyio.run(gateway.list_tools, None, None).tools
    base = {"ops_status", "ops_replies", "ops_reply_preview"}
    assert {t.name for t in tools} == base | extra
    for tool in tools:
        if tool.name in extra:
            assert tool.meta == {"anthropic/requiresUserInteraction": True}
            assert not tool.annotations.read_only_hint
            assert tool.annotations.destructive_hint
    for spec in mcp.TOOLS:
        if spec.name not in base | extra:
            assert data(call(gateway, spec.name, {"secret": SENTINEL}))["error"] == "tool_disabled"
    assert data(call(gateway, SENTINEL))["error"] == "unknown_tool"


@pytest.mark.parametrize("name,args", [
    ("ops_status", {"token": SENTINEL}), ("ops_status", {"approved": True}),
    ("ops_replies", {"limit": True}), ("ops_replies", {"limit": "20"}),
    ("ops_replies", {"limit": 1.0}), ("ops_replies", {"limit": 0}),
    ("ops_replies", {"limit": 21}), ("ops_replies", {"state": None}),
    ("ops_replies", {"state": SENTINEL}), ("ops_replies", {"after_reply_id": SENTINEL}),
    ("ops_reply_preview", {"reply_id": "rpl_" + "a" * 33}),
    ("ops_reply_preview", {"reply_id": "/private/" + SENTINEL}),
    ("ops_reply_send", {"reply_id": "rpl_" + "a" * 32, "payload_digest": "sha256:" + "a" * 64, "binding_revision": True}),
    ("ops_reply_send", {"reply_id": "rpl_" + "a" * 32, "payload_digest": "sha256:" + "a" * 64, "binding_revision": 1 << 31}),
    ("ops_reconcile", {"reply_id": "rpl_" + "a" * 32, "attempt_count": True, "outcome": "unknown", "reconciliation_ref": "check:1"}),
    ("ops_reconcile", {"reply_id": "rpl_" + "a" * 32, "attempt_count": 1, "outcome": "sent", "reconciliation_ref": "check:1"}),
    ("ops_reconcile", {"reply_id": "rpl_" + "a" * 32, "attempt_count": 1, "outcome": "failed", "reconciliation_ref": "a" * 129}),
    ("ops_poll_once", {"timeout": 30}), ("ops_pause", {"resume": True}),
])
def test_strict_same_schema_validation_closed_and_no_runtime(live_shape, monkeypatch, caplog, capsys, name, args):
    gateway, api, _ = live_shape
    def forbidden(*args, **kwargs):
        pytest.fail("invalid argument touched DB")
    monkeypatch.setattr(AgentToolOpsStore, "open_existing", forbidden)
    result = call(gateway, name, args)
    assert result.is_error and data(result)["error"] == "invalid_input"
    assert SENTINEL not in result.model_dump_json()
    assert SENTINEL not in caplog.text + str(capsys.readouterr())
    assert not api.calls and not api.sends


def test_database_only_status_metadata_pagination_preview(state):
    path, reply_ids = state
    gateway = mcp.Gateway(config(path))
    status = data(call(gateway, "ops_status"))
    assert status["transport"]["state"] == "active"
    assert status["provider_identity_checked"] is False
    page = data(call(gateway, "ops_replies", {"limit": 2}))
    assert page["state"] == "pending" and page["has_more"]
    assert all("text" not in item for item in page["replies"])
    final = data(call(gateway, "ops_replies", {"after_reply_id": page["next_after_reply_id"]}))
    assert len(final["replies"]) == 1 and not final["has_more"]
    preview = data(call(gateway, "ops_reply_preview", {"reply_id": reply_ids[0]}))
    assert preview["eligible"] and preview["content_disclosed_to_client_model"]
    assert preview["digest_is_human_approval"] is False
    assert preview["reply_id"] == reply_ids[0] and preview["text"]
    for sentinel in (str(path), str(OPERATOR), "ws_runtime", USERNAME):
        assert sentinel not in json.dumps(status) + json.dumps(page) + json.dumps(preview)
    assert not Path(str(path) + ".run.lock").exists()


@pytest.mark.parametrize("state_name", ["pending", "inflight", "sent", "failed", "unknown", "invalidated", "all"])
def test_all_reply_states_are_discoverable_and_inspection_does_not_recover(state, state_name):
    path, reply_ids = state
    with AgentToolOpsStore.open_existing(path, readonly=False) as store:
        item = store.reply_item(reply_ids[0])
        store.claim_reply(item.reply_id, payload_digest=item.payload_digest, binding_revision=item.binding_revision)
    gateway = mcp.Gateway(config(path))
    result = call(gateway, "ops_replies", {"state": state_name})
    assert not result.is_error
    with AgentToolOpsStore.open_existing(path) as store:
        assert store.reply_item(reply_ids[0]).state == "inflight"


@pytest.mark.parametrize("change", ["source", "username", "slot"])
@pytest.mark.parametrize("tool", ["ops_status", "ops_replies", "ops_reply_preview"])
def test_configured_binding_mismatch_precedes_disclosure(state, change, tool):
    path, reply_ids = state
    if change == "slot":
        with AgentToolOpsStore.open_existing(path, readonly=False) as store:
            store.conn.execute("UPDATE ops_bindings SET credential_ref=?", (runtime.credential_reference(USERNAME, "other-slot"),))
    cfg = config(path, expected_bot_username="OtherFixtureBot" if change == "username" else USERNAME,
                 source_binding="wrong" if change == "source" else "ws_runtime")
    args = {"reply_id": reply_ids[0]} if tool == "ops_reply_preview" else {}
    assert data(call(mcp.Gateway(cfg), tool, args))["error"] == "binding_mismatch"


@pytest.mark.parametrize("account", ["version-2", "ops.primary_v2"])
def test_bound_custom_account_inspection_and_runtime_forwarding(live_shape, state, monkeypatch, account):
    _, api, reply_ids = live_shape
    path, _ = state
    write_config({"db_path": str(path), "expected_bot_username": USERNAME,
                  "source_binding": "ws_runtime", "keychain_account_name": account,
                  "capabilities": ["poll", "send"]})
    loaded = mcp._load_configuration()
    assert loaded.error is None and loaded.config.keychain_account_name == account
    gateway = mcp.Gateway(loaded)
    assert data(call(gateway, "ops_status"))["provider_identity_checked"] is False
    assert data(call(gateway, "ops_replies"))["replies"]
    args = exact(gateway, reply_ids[0])
    assert not api.calls and not api.sends

    forwarded = {}
    for name in ("poll_once", "send_once"):
        original = getattr(runtime, name)

        def checked(store, _name=name, _fn=original, **kwargs):
            forwarded[_name] = dict(kwargs)
            return _fn(store, **kwargs)

        monkeypatch.setattr(runtime, name, checked)
    assert data(call(gateway, "ops_poll_once"))["sends"] == 0
    assert not api.sends
    assert data(call(gateway, "ops_reply_send", args))["state"] == "sent"
    options = {"expected_username": USERNAME, "source_binding": "ws_runtime",
               "keychain_account_name": account}
    assert forwarded == {"poll_once": {**options, "timeout": 0}, "send_once": {**options, **args}}
    assert len(api.sends) == 1  # Internal FakeAPI only; no Telegram transport.


@pytest.mark.parametrize("account", ["version-2"])
@pytest.mark.parametrize("change", ["slot", "service", "scheme", "source"])
@pytest.mark.parametrize("tool", ["ops_status", "ops_replies", "ops_reply_preview", "ops_poll_once", "ops_reply_send"])
def test_custom_account_full_binding_mismatch_precedes_runtime(state, monkeypatch, account, change, tool):
    path, reply_ids = state
    reference = {
        "slot": runtime.credential_reference(USERNAME, "version-3"),
        "service": f"keychain:{bootstrap.KEYCHAIN_SERVICE}:{account}",
        "scheme": f"other:{bootstrap.OPS_KEYCHAIN_SERVICE}:{account}",
        "source": runtime.credential_reference(USERNAME, account),
    }[change]
    with AgentToolOpsStore.open_existing(path, readonly=False) as store:
        item = store.reply_item(reply_ids[0])
        store.conn.execute("UPDATE ops_bindings SET credential_ref=?", (reference,))
    cfg = config(path, ("poll", "send"), expected_bot_username=USERNAME,
                 keychain_account_name=account,
                 source_binding="wrong" if change == "source" else "ws_runtime")

    def forbidden(*args, **kwargs):
        pytest.fail("binding mismatch reached runtime or provider preparation")

    for name in ("local_status", "reply_page", "preview_reply", "poll_once", "send_once", "_load_api"):
        monkeypatch.setattr(runtime, name, forbidden)
    args = {"reply_id": item.reply_id} if tool in {"ops_reply_preview", "ops_reply_send"} else {}
    if tool == "ops_reply_send":
        args.update(payload_digest=item.payload_digest, binding_revision=item.binding_revision)
    result = call(mcp.Gateway(cfg), tool, args)
    assert result.is_error and data(result)["error"] == "binding_mismatch"


@pytest.mark.parametrize("account", [USERNAME.lower(), "version-2"])
@pytest.mark.parametrize("tool", ["ops_poll_once", "ops_reply_send"])
def test_same_slot_wrong_username_is_unverified_offline_and_rejected_by_getme(live_shape, state, account, tool):
    _, api, reply_ids = live_shape
    path, _ = state
    wrong_username = "OtherFixtureBot"
    reference = runtime.credential_reference(USERNAME, account)
    assert runtime.credential_reference(wrong_username, account) == reference
    with AgentToolOpsStore.open_existing(path) as store:
        assert store.binding().credential_ref == reference
    gateway = mcp.Gateway(config(path, ("poll", "send"), expected_bot_username=wrong_username,
                                source_binding="ws_runtime", keychain_account_name=account))
    status = data(call(gateway, "ops_status"))
    assert status["provider_identity_checked"] is False and status["telegram_calls"] == 0
    page = data(call(gateway, "ops_replies"))
    preview = data(call(gateway, "ops_reply_preview", {"reply_id": reply_ids[0]}))
    assert page["network_calls"] == page["credential_reads"] == 0
    assert preview["network_calls"] == preview["credential_reads"] == 0
    assert not api.calls and not api.sends
    args = {key: preview[key] for key in ("reply_id", "payload_digest", "binding_revision")}
    result = call(gateway, tool, args if tool == "ops_reply_send" else {})
    assert result.is_error and data(result)["error"] == "unavailable"
    assert api.calls == ["getMe"] and not api.sends
    with AgentToolOpsStore.open_existing(path) as store:
        item = store.reply_item(reply_ids[0])
        assert item.state == "pending" and item.attempt_count == 0


def test_unbound_and_paused_inspectable(state, tmp_path):
    path, _ = state
    with AgentToolOpsStore.open_existing(path, readonly=False) as store:
        store.pause()
    gateway = mcp.Gateway(config(path, expected_bot_username=USERNAME, source_binding="ws_runtime"))
    assert data(call(gateway, "ops_status"))["transport"]["state"] == "paused"
    assert data(call(gateway, "ops_replies", {"state": "invalidated"}))["replies"]
    unbound = tmp_path.resolve() / "unbound" / "ops.db"
    with AgentToolOpsStore(unbound):
        pass
    assert data(call(mcp.Gateway(config(unbound)), "ops_status"))["transport"]["state"] == "unbound"


def exact(gateway, reply_id):
    preview = data(call(gateway, "ops_reply_preview", {"reply_id": reply_id}))
    return {key: preview[key] for key in ("reply_id", "payload_digest", "binding_revision")}


def test_poll_fixed_batch_zero_sends_and_dedup(live_shape):
    gateway, api, _ = live_shape
    first = data(call(gateway, "ops_poll_once"))
    second = data(call(gateway, "ops_poll_once"))
    assert first["processed"] == 1 and first["sends"] == 0
    assert second["duplicates"] == 1 and second["sends"] == 0
    assert not api.sends
    assert all(c[1]["timeout"] == 0 and c[1]["limit"] == 20 for c in api.calls if isinstance(c, tuple))


def test_exact_send_stale_digest_revision_and_duplicate(live_shape):
    gateway, api, reply_ids = live_shape
    args = exact(gateway, reply_ids[0])
    for field, value in (("payload_digest", "sha256:" + "0" * 64), ("binding_revision", 2)):
        result = call(gateway, "ops_reply_send", {**args, field: value})
        assert data(result)["error"] == "stale_preview"
        assert not api.calls and not api.sends
    result = data(call(gateway, "ops_reply_send", args))
    assert result["state"] == "sent" and result["send_attempts"] == 1 and not result["retry_allowed"]
    assert len(api.sends) == 1
    assert data(call(gateway, "ops_reply_send", args))["error"] == "reply_not_pending"
    assert len(api.sends) == 1


def test_production_handler_cannot_turn_fixture_binding_into_live_authority(state):
    path, reply_ids = state
    gateway = mcp.Gateway(config(path, ("send",), expected_bot_username=USERNAME,
        source_binding="ws_runtime", keychain_account_name=USERNAME.lower()))
    args = exact(gateway, reply_ids[0])
    assert data(call(gateway, "ops_reply_send", args))["error"] == "binding_unavailable"
    with AgentToolOpsStore.open_existing(path) as store:
        item = store.reply_item(reply_ids[0])
        assert item.state == "pending" and item.attempt_count == 0


def test_unknown_pause_reconcile_fence_and_never_resend(live_shape):
    gateway, api, reply_ids = live_shape
    args = exact(gateway, reply_ids[0])
    api.send_error = TimeoutError(SENTINEL)
    result = data(call(gateway, "ops_reply_send", args))
    assert result["state"] == "unknown"
    observed = dict(reply_id=reply_ids[0], attempt_count=1, outcome="sent",
                    reconciliation_ref="fixture-observation:1", receipt_ref="fixture-receipt:1")
    assert data(call(gateway, "ops_reconcile", {**observed, "attempt_count": 2}))["error"] == "delivery_state_conflict"
    reconciled = data(call(gateway, "ops_reconcile", observed))
    assert reconciled["state"] == "sent" and reconciled["sends"] == 0
    assert reconciled["independently_verified"] is False
    assert data(call(gateway, "ops_reply_send", args))["error"] == "reply_not_pending"
    assert data(call(gateway, "ops_pause"))["state"] == "paused"
    assert data(call(gateway, "ops_poll_once"))["error"] == "binding_unavailable"
    assert data(call(gateway, "ops_replies", {"state": "invalidated"}))["replies"]
    assert len(api.sends) == 1


def test_interrupted_reply_recovers_unknown_without_resend(live_shape, state):
    gateway, api, reply_ids = live_shape
    args = exact(gateway, reply_ids[0])
    with AgentToolOpsStore.open_existing(state[0], readonly=False) as store:
        store.claim_reply(**args)
    assert data(call(gateway, "ops_reply_send", args))["error"] == "reply_not_pending"
    assert not api.calls and not api.sends
    assert data(call(gateway, "ops_replies", {"state": "unknown"}))["replies"][0]["reply_id"] == reply_ids[0]


def test_busy_cancellation_retains_slot_connection_and_thread_until_end(state, monkeypatch):
    path, _ = state
    gateway = mcp.Gateway(config(path))
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    main_thread = threading.get_ident()
    traces = []
    original_open = AgentToolOpsStore.open_existing
    original_close = AgentToolOpsStore.close

    def opened(*args, **kwargs):
        traces.append(("open", threading.get_ident(), kwargs["readonly"]))
        return original_open(*args, **kwargs)

    def closed(store):
        traces.append(("close", threading.get_ident(), release.is_set()))
        original_close(store)

    def slow(store):
        traces.append(("use", threading.get_ident(), store.conn.execute("PRAGMA query_only").fetchone()[0]))
        entered.set()
        assert release.wait(5)
        finished.set()
        return {"status": "fixture_finished"}

    monkeypatch.setattr(AgentToolOpsStore, "open_existing", opened)
    monkeypatch.setattr(AgentToolOpsStore, "close", closed)
    monkeypatch.setattr(runtime, "local_status", slow)

    async def scenario():
        scope = anyio.CancelScope()
        async def work():
            with scope:
                await gateway.call_tool(None, types.CallToolRequestParams(name="ops_status"))
        async with anyio.create_task_group() as tg:
            tg.start_soon(work)
            with anyio.fail_after(3):
                while not entered.is_set():
                    await anyio.sleep(.01)
            scope.cancel()
            assert data(await gateway.call_tool(None, types.CallToolRequestParams(name="ops_status")))["error"] == "busy"
            assert not finished.is_set() and len(traces) == 2
            assert len((await gateway.list_tools(None, None)).tools) == 3
            release.set()
        assert not gateway._busy and finished.is_set()

    try:
        anyio.run(scenario)
    finally:
        release.set()
    assert [t[0] for t in traces] == ["open", "use", "close"]
    assert len({t[1] for t in traces}) == 1 and traces[0][1] != main_thread
    assert all(t[2] for t in traces)


def test_cancelled_send_holds_provider_lock_and_admission_until_completion(live_shape, state):
    gateway, api, reply_ids = live_shape
    args = exact(gateway, reply_ids[0])
    entered, release = threading.Event(), threading.Event()

    def hold_send():
        entered.set()
        assert release.wait(5)
    api.on_send = hold_send

    async def scenario():
        scope = anyio.CancelScope()
        async def first():
            with scope:
                await gateway.call_tool(None, types.CallToolRequestParams(name="ops_reply_send", arguments=args))
        async with anyio.create_task_group() as tg:
            tg.start_soon(first)
            with anyio.fail_after(3):
                while not entered.is_set():
                    await anyio.sleep(.01)
            scope.cancel()
            for name, arguments in (("ops_reply_send", args), ("ops_pause", {})):
                result = await gateway.call_tool(None, types.CallToolRequestParams(name=name, arguments=arguments))
                assert data(result)["error"] == "busy"
            with AgentToolOpsStore.open_existing(state[0], readonly=False) as store:
                assert store.reply_item(reply_ids[0]).state == "inflight"
                with pytest.raises(runtime.OpsRuntimeError, match="local_lock_busy"):
                    runtime.pause(store)
            release.set()
        assert not gateway._busy
    try:
        anyio.run(scenario)
    finally:
        release.set()
    assert len(api.sends) == 1
    assert data(call(gateway, "ops_reply_send", args))["error"] == "reply_not_pending"
    assert data(call(gateway, "ops_pause"))["state"] == "paused"
    assert len(api.sends) == 1


@pytest.mark.parametrize("failure", [ValueError(SENTINEL), OSError(SENTINEL), RuntimeError(SENTINEL)])
def test_private_runtime_errors_are_static(state, monkeypatch, failure, caplog, capsys):
    def bad(*args, **kwargs):
        raise failure
    monkeypatch.setattr(runtime, "local_status", bad)
    result = call(mcp.Gateway(config(state[0])), "ops_status")
    assert data(result)["error"] == "unavailable"
    assert SENTINEL not in result.model_dump_json() + caplog.text + str(capsys.readouterr())


def test_oversize_output_fails_without_partial_preview():
    result = mcp._result({"text": SENTINEL * 5000})
    assert data(result)["error"] == "result_too_large"
    assert SENTINEL not in result.model_dump_json()
    assert len(mcp._result({"text": "é" * 4000}).model_dump_json().encode()) < mcp.MAX_FRAME_BYTES


class RecordingWriteStream:
    def __init__(self):
        self.items = []
        self.closed = False
        self.entered = False

    async def send(self, item):
        self.items.append(item)

    async def aclose(self):
        self.closed = True

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *args):
        await self.aclose()


@pytest.mark.parametrize("code", [*mcp._PROTOCOL_ERRORS, 0, 99999])
def test_typed_outbound_error_boundary_sanitizes_every_sdk_route(code, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("boundary serialized the unbounded SDK error")

    monkeypatch.setattr(types.JSONRPCError, "model_dump_json", forbidden)
    original = types.JSONRPCError(jsonrpc="2.0", id="correlation-123",
        error=types.ErrorData(code=code, message=SENTINEL * 10000,
                             data={"requested": SENTINEL * 10000}))
    metadata = ServerMessageMetadata(related_request_id="correlation-123")
    sink = RecordingWriteStream()
    stream = mcp._PrivateWriteStream(sink)

    async def scenario():
        async with stream:
            await stream.send(SessionMessage(original, metadata))
    anyio.run(scenario)
    assert sink.entered and sink.closed and len(sink.items) == 1
    item = sink.items[0]
    expected = code if code in mcp._PROTOCOL_ERRORS else -32603
    assert item.message.id == original.id and item.metadata is metadata
    assert item.message.error.model_dump(exclude_unset=True) == {
        "code": expected, "message": mcp._PROTOCOL_ERRORS[expected]}
    assert SENTINEL not in repr(item.message)
    assert original.error.data["requested"] == SENTINEL * 10000


@pytest.mark.parametrize("shape", ["large_string", "aggregate", "deep", "unicode", "unknown"])
def test_outbound_budget_rejects_before_sdk_serialization_or_stream_send(shape, monkeypatch):
    result = {
        "large_string": {"text": SENTINEL * 10000},
        "aggregate": {"items": [""] * 40000},
        "deep": {"text": "small"},
        "unicode": {"text": "界" * 30000},
        "unknown": {"object": object()},
    }[shape]
    if shape == "deep":
        for _ in range(mcp.MAX_OUTPUT_DEPTH + 1):
            result = {"nested": result}
    def forbidden(*args, **kwargs):
        pytest.fail("oversized outbound envelope reached serialization")
    monkeypatch.setattr(types.JSONRPCResponse, "model_dump_json", forbidden)
    message = types.JSONRPCResponse(jsonrpc="2.0", id=1, result=result)
    sink = RecordingWriteStream()
    with pytest.raises(ValueError, match="^outbound_frame_rejected$"):
        anyio.run(mcp._PrivateWriteStream(sink).send, SessionMessage(message))
    assert sink.items == []


@pytest.mark.parametrize("text", ["x" * 63000, "界" * 20000, "\x00" * 10000, "\\\"\n\t" * 4000])
def test_budget_preserves_bounded_successes_and_sdk_serialization(text):
    message = types.JSONRPCResponse(jsonrpc="2.0", id=1, result={"text": text})
    item = SessionMessage(message, ServerMessageMetadata(related_request_id=1))
    sink = RecordingWriteStream()
    anyio.run(mcp._PrivateWriteStream(sink).send, item)
    assert sink.items == [item] and sink.items[0] is item
    wire = message.model_dump_json(by_alias=True, exclude_unset=True) + "\n"
    assert len(wire.encode()) <= mcp.MAX_FRAME_BYTES
    assert json.loads(wire)["result"]["text"] == text


@pytest.mark.parametrize("race", [False, True])
def test_nonblocking_stdout_handles_partial_writes_and_eagain_without_threads(monkeypatch, race):
    read_fd, write_fd = os.pipe()
    written = bytearray()
    attempts = 0
    waits = []
    main_thread = threading.get_ident()
    try:
        output = mcp._BoundedStdout(write_fd)
        assert not os.get_blocking(write_fd)
        def write(fd, data):
            nonlocal attempts
            assert fd == write_fd and threading.get_ident() == main_thread
            attempts += 1
            if race and attempts in (1, 2, 4):
                raise BlockingIOError()
            count = min(3, len(data))
            written.extend(data[:count])
            return count
        async def ready(fd):
            waits.append(fd)
            await anyio.sleep(0)
        def no_thread(*args, **kwargs):
            pytest.fail("output must not start a blocking writer thread")
        monkeypatch.setattr(os, "write", write)
        monkeypatch.setattr(anyio, "wait_writable", ready)
        monkeypatch.setattr(anyio.to_thread, "run_sync", no_thread)
        text = "partial 界 frame\n"
        async def scenario():
            with anyio.fail_after(1):
                assert await output.write(text) == len(text)
                await output.flush()
        anyio.run(scenario)
        assert written == text.encode()
        assert waits == ([write_fd] * 3 if race else [])
    finally:
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize("progress", [False, True])
def test_stdout_deadline_is_total_not_reset_by_readiness_or_partial_progress(monkeypatch, progress):
    read_fd, write_fd = os.pipe()
    written = bytearray()
    waits = 0
    try:
        output = mcp._BoundedStdout(write_fd)
        monkeypatch.setattr(mcp, "OUTPUT_FRAME_TIMEOUT", .06)
        def write(fd, data):
            assert fd == write_fd
            if progress and len(written) < waits:
                written.extend(data[:1])
                return 1
            raise BlockingIOError()
        async def ready(fd):
            nonlocal waits
            waits += 1
            await anyio.sleep(.01)
        monkeypatch.setattr(os, "write", write)
        monkeypatch.setattr(anyio, "wait_writable", ready)
        async def scenario():
            start = anyio.current_time()
            with anyio.fail_after(1):
                with pytest.raises(TimeoutError):
                    await output.write("x" * 1000)
            assert anyio.current_time() - start < .5
        anyio.run(scenario)
        assert waits > 1
        assert (len(written) > 0) == progress
    finally:
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize("failure", ["zero_write", "broken_pipe", "byte_limit", "character_limit"])
def test_stdout_rejects_invalid_output_and_closed_peer(monkeypatch, failure):
    read_fd, write_fd = os.pipe()
    try:
        output = mcp._BoundedStdout(write_fd)
        def write(fd, data):
            assert fd == write_fd
            assert failure in {"zero_write", "broken_pipe"}, "oversize frame reached os.write"
            if failure == "zero_write":
                return 0
            raise BrokenPipeError()
        monkeypatch.setattr(os, "write", write)
        text = "界" * 30000 if failure == "byte_limit" else "x" * 65537 if failure == "character_limit" else "frame\n"
        error = ValueError if "limit" in failure else BrokenPipeError
        with pytest.raises(error):
            anyio.run(output.write, text)
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_stdout_rejects_regular_files_that_nonblocking_cannot_bound(tmp_path):
    with (tmp_path / "not-a-pipe").open("wb") as file:
        with pytest.raises(ValueError, match="stdio_pipe_required"):
            mcp._BoundedStdout(file.fileno())


def write_config(value):
    path = mcp.CONFIG_PATH
    path.parent.mkdir(mode=0o700)
    path.write_text(value if isinstance(value, str) else json.dumps(value))
    path.chmod(0o600)
    return path


def test_fixed_config_loaded_once_empty_and_database_only(tmp_path):
    path = write_config({})
    assert mcp._load_configuration().error == "not_configured"
    path.write_text(json.dumps({"db_path": str(tmp_path / "absent.db")}))
    loaded = mcp._load_configuration()
    assert loaded.config is not None
    gateway = mcp.Gateway(loaded)
    path.write_text('{"token":"' + SENTINEL + '"}')
    assert data(call(gateway, "ops_status"))["error"] == "unavailable"
    assert mcp._load_configuration().error == "invalid_config"


@pytest.mark.parametrize("extra", [
    {"token": SENTINEL}, {"chat_id": 123}, {"bot_id": 123}, {"fixture": True},
    {"origin": "https://fixture.invalid"}, {"source_path": SENTINEL},
    {"approved": True}, {"capabilities": ["resume"]}, {"capabilities": ["send"]},
    {"capabilities": ["pause", "pause"]}, {"keychain_account_name": "other-slot"},
    {"db_path": "relative.db"}, {"db_path": "/private/../other.db"},
    {"db_path": "/private/\nsecret.db"}, {"db_path": 123},
])
def test_config_extra_secret_authority_keys_and_invalid_values_rejected(tmp_path, extra):
    write_config({"db_path": str(tmp_path / "ops.db"), **extra})
    assert mcp._load_configuration().error == "invalid_config"


@pytest.mark.parametrize("account", ["", "Uppercase", ".slot", "slot/2", "slot:2", "a" * 65, 123, True])
def test_custom_account_still_requires_strict_slot_syntax(tmp_path, account):
    with pytest.raises(ValidationError):
        config(tmp_path / "ops.db", expected_bot_username=USERNAME, keychain_account_name=account)


@pytest.mark.parametrize("capability", ["poll", "send"])
@pytest.mark.parametrize("missing", ["expected_bot_username", "source_binding", "keychain_account_name"])
def test_custom_account_poll_send_still_require_full_configuration(tmp_path, capability, missing):
    options = {"expected_bot_username": USERNAME, "source_binding": "ws_runtime",
               "keychain_account_name": "version-2"}
    options.pop(missing)
    with pytest.raises(ValidationError):
        config(tmp_path / "ops.db", (capability,), **options)


@pytest.mark.parametrize("kind", ["public_file", "public_directory", "file_symlink", "directory_symlink", "hardlink", "fifo", "oversize", "duplicate", "malformed"])
def test_unsafe_config_refused_without_repair(tmp_path, kind):
    path = write_config({"db_path": str(tmp_path / "ops.db")})
    if kind == "public_file":
        path.chmod(0o644)
    elif kind == "public_directory":
        path.parent.chmod(0o755)
    elif kind in {"file_symlink", "hardlink"}:
        target = path.with_name("target")
        path.rename(target)
        path.symlink_to(target) if kind == "file_symlink" else os.link(target, path)
    elif kind == "directory_symlink":
        target = path.parent.with_name("target-directory")
        path.parent.rename(target)
        path.parent.symlink_to(target, target_is_directory=True)
    elif kind == "fifo":
        path.unlink()
        os.mkfifo(path, 0o600)
    elif kind == "oversize":
        path.write_text(SENTINEL * 8192)
    elif kind == "duplicate":
        path.write_text('{"db_path":"/private/a.db","db_path":"/private/b.db"}')
    else:
        path.write_text('{"' + SENTINEL)
    before = path.lstat()
    assert mcp._load_configuration().error == "invalid_config"
    assert path.lstat().st_mode == before.st_mode


@pytest.mark.parametrize("state_kind", ["missing", "empty", "wrong_role", "public", "symlink"])
def test_state_unavailable_never_initialized_or_repaired(tmp_path, state_kind):
    root = tmp_path.resolve() / "state"
    root.mkdir(mode=0o700)
    path = root / "ops.db"
    if state_kind == "empty":
        path.touch(mode=0o600)
    elif state_kind == "wrong_role":
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE private_fixture (secret TEXT)")
        conn.close()
        path.chmod(0o600)
    elif state_kind in {"public", "symlink"}:
        with AgentToolOpsStore(path):
            pass
        if state_kind == "public":
            path.chmod(0o644)
        else:
            target = root / "target.db"
            path.rename(target)
            path.symlink_to(target)
    before = sorted((p.name, p.lstat().st_mode, p.read_bytes()) for p in root.iterdir())
    assert data(call(mcp.Gateway(config(path)), "ops_status"))["error"] == "unavailable"
    assert sorted((p.name, p.lstat().st_mode, p.read_bytes()) for p in root.iterdir()) == before
