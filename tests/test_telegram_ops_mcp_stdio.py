"""Real launcher and official 2.2 SDK client, with child-local external guards.

The generated test bootstrap installs internal patches, then runpy executes the
UNCHANGED production launcher from /Users/yu using isolated -I -B Python. No
fixture switch, alternative transport, clock or config path is exposed by MCP.
"""
from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import textwrap
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import anyio
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError

from telegram_gateway.agenttool_ops import AgentToolOpsStore
from telegram_gateway.ops_service import OpsServiceConfig, TelegramOpsService
from telegram_gateway import ops_runtime as runtime
from test_telegram_ops_runtime import BOT, NOW, OPERATOR, USERNAME, FakeAPI, command

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "integrations" / "telegram_ops_mcp" / "run.py"
PYTHON = ROOT / "integrations" / "telegram_ops_mcp" / ".venv" / "bin" / "python"
SENTINEL = "NEVER_ECHO_PRIVATE_PROTOCOL_SENTINEL"


def child(tmp_path, *, populated=False, slow=False, broken=False, flush_output=False, sending=False):
    root = tmp_path.resolve()
    home = root / "home"
    home.mkdir(mode=0o700)
    path = root / "state" / "ops.db"
    reply_id = None
    if populated:
        with AgentToolOpsStore(path) as store:
            store.bind_operator(BOT, FakeAPI.provider_origin,
                operator_user_id=OPERATOR, operator_private_chat_id=OPERATOR,
                credential_ref=runtime.credential_reference(USERNAME), source_binding="ws_runtime",
                verification="fixture", bound_at=NOW)
            service = TelegramOpsService(store, store, OpsServiceConfig(OPERATOR, OPERATOR))
            reply_id = store.process_update_once(command(), service,
                polling_epoch=store.poll_state().epoch, processed_at=NOW + timedelta(seconds=2)).reply_id
        config_dir = home / ".config" / "kingdom-telegram-ops"
        config_dir.mkdir(mode=0o700, parents=True)
        cfg = config_dir / "mcp.json"
        configuration = {"db_path": str(path)}
        if sending:
            configuration.update(capabilities=["send"], expected_bot_username=USERNAME,
                                 source_binding="ws_runtime", keychain_account_name=USERNAME.lower())
        cfg.write_text(json.dumps(configuration))
        cfg.chmod(0o600)
    bootstrap = root / "guarded-launcher.py"
    bootstrap.write_text(textwrap.dedent(f'''
        import json, os, pathlib, runpy, socket, sqlite3, subprocess, sys, threading, time, urllib.parse
        ROOT = pathlib.Path({str(ROOT)!r})
        FIXTURE = pathlib.Path({str(root)!r})
        sys.path.insert(0, str(ROOT))
        def record(event):
            with (FIXTURE / "trace.jsonl").open("a") as out:
                out.write(json.dumps({{"event": event, "thread": threading.get_ident()}}) + "\\n")
        def forbidden(*args, **kwargs):
            record("FORBIDDEN")
            raise AssertionError({SENTINEL!r})
        def audit(event, args):
            if event in {{"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}}:
                forbidden()
            if event == "socket.__new__" and args[1] in (socket.AF_INET, socket.AF_INET6):
                forbidden()
            if event == "sqlite3.connect":
                value = str(args[0])
                location = urllib.parse.unquote(urllib.parse.urlsplit(value).path) if value.startswith("file:") else value
                if not pathlib.Path(location).resolve().is_relative_to(FIXTURE):
                    forbidden()
            if event == "open" and isinstance(args[0], (str, bytes)):
                name = os.fsdecode(args[0])
                if name.endswith((".db", ".sqlite", ".sqlite3", ".jsonl")) and str(FIXTURE) not in name:
                    forbidden()
                if name == "/Users/yu/.config/kingdom-telegram-ops/mcp.json":
                    forbidden()
        sys.addaudithook(audit)
        from telegram_gateway import bootstrap, ops_runtime, telegram_api, agenttool_mcp
        from telegram_gateway.agenttool_ops import AgentToolOpsStore
        bootstrap.load_keychain_token = ops_runtime.load_keychain_token = forbidden
        telegram_api.open_request = forbidden
        telegram_api.TelegramAPI.__init__ = forbidden
        agenttool_mcp.AgentToolMcpReader.__init__ = forbidden
        agenttool_mcp.StdioMcpTransport.__init__ = forbidden
        subprocess.Popen = subprocess.run = subprocess.call = subprocess.check_output = forbidden
        # Guard the real runtime and state opener; never substitute the gateway.
        original_open = AgentToolOpsStore.open_existing
        original_close = AgentToolOpsStore.close
        def opened(*args, **kwargs):
            assert str(FIXTURE) in str(args[0])
            record("open")
            return original_open(*args, **kwargs)
        def closed(store):
            record("close")
            return original_close(store)
        AgentToolOpsStore.open_existing = opened
        AgentToolOpsStore.close = closed
        original_status = ops_runtime.local_status
        def status(store):
            record("entered")
            if {slow!r}:
                deadline = time.monotonic() + 6
                while not (FIXTURE / "release").exists():
                    if time.monotonic() > deadline:
                        raise AssertionError("fixture release timed out")
                    time.sleep(.01)
            if {broken!r}:
                # Python, fd-level, logger and exception diagnostics must all
                # miss both stderr and protocol stdout in the real launcher.
                import atexit, logging
                print({SENTINEL!r})
                print({SENTINEL!r}, file=sys.__stdout__)
                sys.stdout.buffer.write({SENTINEL.encode()!r})
                sys.__stdout__.buffer.write({SENTINEL.encode()!r})
                if {flush_output!r}:
                    sys.stdout.flush()
                    sys.__stdout__.flush()
                atexit.register(lambda: sys.__stdout__.write({SENTINEL!r}))
                print({SENTINEL!r}, file=sys.stderr)
                os.write(1, {SENTINEL.encode()!r})
                os.write(2, {SENTINEL.encode()!r})
                logging.critical({SENTINEL!r})
                raise RuntimeError({SENTINEL!r})
            result = original_status(store)
            record("finished")
            return result
        ops_runtime.local_status = status
        if {sending!r}:
            sys.path.insert(0, str(ROOT / "tests"))
            from test_telegram_ops_runtime import FakeAPI
            api = FakeAPI()
            def held_send():
                record("send_entered")
                deadline = time.monotonic() + 10
                while not (FIXTURE / "release").exists():
                    if time.monotonic() > deadline:
                        raise AssertionError("fixture send release timed out")
                    time.sleep(.01)
                record("send_finished")
            api.on_send = held_send
            original_send = ops_runtime.send_once
            def send_fixture(store, **kwargs):
                result = original_send(store, fixture=True, api=api,
                                       lock_dir=FIXTURE / "fixture-locks", **kwargs)
                assert len(api.sends) == 1
                record("send_" + result["state"])
                return result
            ops_runtime.send_once = send_fixture
        (FIXTURE / "pid").write_text(str(os.getpid()))
        record("startup")
        assert pathlib.Path.cwd() == pathlib.Path("/Users/yu")
        assert pathlib.Path.home() == pathlib.Path({str(home)!r})
        sys.argv = [{str(LAUNCHER)!r}]
        try:
            runpy.run_path({str(LAUNCHER)!r}, run_name="__main__")
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise
        record("launcher_returned")
        if {broken!r}:
            sys.stdout.write({SENTINEL!r})
            sys.__stdout__.write({SENTINEL!r})
    '''))
    env = {"HOME": str(home), "PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1",
           "KINGDOM_TELEGRAM_BOT_TOKEN": SENTINEL, "DATABASE_URL": SENTINEL}
    params = StdioServerParameters(command=str(PYTHON), args=["-I", "-B", str(bootstrap)],
                                   cwd="/Users/yu", env=env)
    return root, params, reply_id


def payload(result):
    assert json.loads(result.content[0].text) == result.structured_content
    return result.structured_content


def trace(root):
    file = root / "trace.jsonl"
    return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []


def assert_reaped(root):
    pid = int((root / "pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    assert "FORBIDDEN" not in [event["event"] for event in trace(root)]


def run(coro):
    async def bounded():
        with anyio.fail_after(15):
            await coro()
    anyio.run(bounded)


def test_official_sdk_initialize_discovery_absent_config_status_and_eof(tmp_path):
    root, params, _ = child(tmp_path)
    stderr_path = root / "stderr"
    async def scenario():
        with stderr_path.open("w") as err:
            async with stdio_client(params, errlog=err) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=3.0) as session:
                    initialized = await session.initialize()
                    assert initialized.protocol_version == "2025-11-25"
                    tools = await session.list_tools()
                    assert [t.name for t in tools.tools] == ["ops_status", "ops_replies", "ops_reply_preview"]
                    assert tools.tools[2].meta == {"anthropic/requiresUserInteraction": True}
                    assert all(t.annotations.read_only_hint for t in tools.tools)
                    status = await session.call_tool("ops_status", {})
                    assert not status.is_error and payload(status)["status"] == "not_configured"
                    assert payload(await session.call_tool("ops_replies", {}))["error"] == "not_configured"
                    assert payload(await session.call_tool("ops_reply_send", {}))["error"] == "tool_disabled"
                    assert [e["event"] for e in trace(root)] == ["startup"]
                    await session.send_ping()
    run(scenario)
    assert stderr_path.read_text() == ""
    assert [e["event"] for e in trace(root)] == ["startup", "launcher_returned"]
    assert_reaped(root)


def test_official_sdk_fixture_status_replies_preview_and_private_errors(tmp_path):
    root, params, reply_id = child(tmp_path, populated=True)
    stderr_path = root / "stderr"
    async def scenario():
        with stderr_path.open("w") as err:
            async with stdio_client(params, errlog=err) as streams:
                async with ClientSession(*streams, read_timeout_seconds=3.0) as session:
                    await session.initialize()
                    await session.list_tools()
                    assert [e["event"] for e in trace(root)] == ["startup"]
                    status = payload(await session.call_tool("ops_status", {}))
                    assert status["transport"]["state"] == "active"
                    page = payload(await session.call_tool("ops_replies", {}))
                    assert page["replies"][0]["reply_id"] == reply_id and page["state"] == "pending"
                    preview = payload(await session.call_tool("ops_reply_preview", {"reply_id": reply_id}))
                    assert preview["text"] and preview["content_disclosed_to_client_model"]
                    for name, args, error in (
                        (SENTINEL, {}, "unknown_tool"), ("ops_replies", {"limit": True}, "invalid_input"),
                        ("ops_status", {"token": SENTINEL}, "invalid_input"),
                        ("ops_reply_preview", {"reply_id": "rpl_" + "f" * 32}, "invalid_input"),
                    ):
                        result = await session.call_tool(name, args)
                        assert result.is_error and payload(result)["error"] == error
                        assert SENTINEL not in result.model_dump_json()
                    for private in (str(OPERATOR), str(root), "ws_runtime", USERNAME):
                        assert private not in json.dumps(status) + json.dumps(page) + json.dumps(preview)
    run(scenario)
    assert stderr_path.read_text() == ""
    events = trace(root)
    assert len([e for e in events if e["event"] == "open"]) == 4
    assert len([e for e in events if e["event"] == "close"]) == 4
    assert_reaped(root)


@pytest.mark.parametrize("cancel_mode", ["scope", "timeout"])
def test_official_sdk_busy_cancellation_controls_and_connection_lifetime(tmp_path, cancel_mode):
    root, params, _ = child(tmp_path, populated=True, slow=True)
    stderr_path = root / "stderr"
    async def scenario():
        with stderr_path.open("w") as err:
            async with stdio_client(params, errlog=err) as streams:
                async with ClientSession(*streams, read_timeout_seconds=3.0) as session:
                    await session.initialize()
                    scope = anyio.CancelScope()
                    timed_out = anyio.Event()
                    async def first():
                        if cancel_mode == "timeout":
                            with pytest.raises(MCPError) as error:
                                await session.call_tool("ops_status", {}, read_timeout_seconds=.2)
                            assert error.value.error.code == -32001
                            timed_out.set()
                        else:
                            with scope:
                                await session.call_tool("ops_status", {})
                    async with anyio.create_task_group() as tg:
                        tg.start_soon(first)
                        with anyio.fail_after(3):
                            while "entered" not in [e["event"] for e in trace(root)]:
                                await anyio.sleep(.01)
                        assert payload(await session.call_tool("ops_replies", {}))["error"] == "busy"
                        if cancel_mode == "timeout":
                            await timed_out.wait()
                        else:
                            scope.cancel()  # SDK sends notifications/cancelled for abandoned call.
                        await anyio.sleep(.05)
                        assert payload(await session.call_tool("ops_status", {}))["error"] == "busy"
                        assert len((await session.list_tools()).tools) == 3
                        await session.send_ping()
                        assert [e["event"] for e in trace(root)] == ["startup", "open", "entered"]
                        (root / "release").touch()
                    with anyio.fail_after(3):
                        while "close" not in [e["event"] for e in trace(root)]:
                            await anyio.sleep(.01)
                    assert not (await session.call_tool("ops_replies", {})).is_error
    try:
        run(scenario)
    finally:
        (root / "release").touch()
    assert stderr_path.read_text() == ""
    sequence = trace(root)
    assert [e["event"] for e in sequence[:5]] == ["startup", "open", "entered", "finished", "close"]
    assert len({e["thread"] for e in sequence[1:5]}) == 1
    assert sequence[1]["thread"] != sequence[0]["thread"]
    assert_reaped(root)


def test_official_sdk_runtime_prints_logs_fd_writes_and_traceback_contained(tmp_path):
    root, params, _ = child(tmp_path, populated=True, broken=True)
    stderr_path = root / "stderr"
    async def scenario():
        with stderr_path.open("w") as err:
            async with stdio_client(params, errlog=err) as streams:
                async with ClientSession(*streams, read_timeout_seconds=3.0) as session:
                    await session.initialize()
                    result = await session.call_tool("ops_status", {})
                    assert payload(result)["error"] == "unavailable"
                    assert SENTINEL not in result.model_dump_json()
                    assert len((await session.list_tools()).tools) == 3
    run(scenario)
    assert stderr_path.read_text() == ""
    assert_reaped(root)


@contextmanager
def raw_process(params):
    process = subprocess.Popen([params.command, *params.args], cwd=params.cwd,
                               env=params.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, bufsize=0)
    try:
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def send(process, value):
    process.stdin.write((json.dumps(value) + "\n").encode())
    process.stdin.flush()


def frame(process, timeout=4):
    deadline = time.monotonic() + timeout
    line = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while not line.endswith(b"\n"):
            assert len(line) < 65536
            assert selector.select(max(0, deadline - time.monotonic())), "no protocol response"
            chunk = os.read(process.stdout.fileno(), 1)
            assert chunk, "unexpected protocol EOF"
            line.extend(chunk)
    return json.loads(line)


def initialize(process):
    send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-11-25", "capabilities": {},
        "clientInfo": {"name": "fixture-privacy-client", "version": "1"}}})
    assert "result" in frame(process)
    send(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})


def test_raw_malformed_envelopes_unknown_protocol_and_secrets_never_echo(tmp_path):
    root, params, _ = child(tmp_path)
    captured = []
    with raw_process(params) as process:
        initialize(process)
        # SDK owns malformed envelope parsing; invalid stream values are dropped.
        for raw in (
            '{"jsonrpc":"2.0","id":2,"method":' + json.dumps(SENTINEL) + ',"params":[]}',
            '{"jsonrpc":"2.0","id":2,"method":null,"secret":' + json.dumps(SENTINEL) + '}',
            '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":',
            '["' + SENTINEL + '"]',
        ):
            process.stdin.write((raw + "\n").encode())
        for number, method, params_value in (
            (10, SENTINEL, {}),
            (11, "tools/call", {"name": "ops_status", "arguments": {}, "secret": SENTINEL}),
            (12, "tools/call", {"name": "ops_status", "arguments": SENTINEL}),
            (13, "tools/call", {"name": SENTINEL, "arguments": {"token": SENTINEL}}),
            (14, "tools/list", {"cursor": SENTINEL}),
        ):
            send(process, {"jsonrpc": "2.0", "id": number, "method": method, "params": params_value})
            answer = frame(process)
            assert answer["id"] == number
            assert "error" in answer or answer["result"]["isError"] is True
            captured.append(answer)
        send(process, {"jsonrpc": "2.0", "id": 20, "method": "ping"})
        assert "result" in frame(process)
        process.stdin.close()
        process.wait(timeout=4)
        assert process.returncode == 0
        assert process.stderr.read() == b""
    assert SENTINEL not in json.dumps(captured)
    assert_reaped(root)


@pytest.mark.parametrize("suffix", [b"", b"\n", b"\n" + b'{"jsonrpc":"2.0","id":99,"method":"ping"}\n'])
def test_oversize_line_closes_without_waiting_for_unbounded_line(tmp_path, suffix):
    root, params, _ = child(tmp_path)
    with raw_process(params) as process:
        initialize(process)
        try:
            process.stdin.write(b"x" * 65536 + suffix)
            process.stdin.flush()
        except BrokenPipeError:
            pass
        process.wait(timeout=4)
        assert process.returncode == 1
        assert process.stdout.read() == b"" and process.stderr.read() == b""
    assert_reaped(root)


def test_exact_frame_limit_and_bad_utf8(tmp_path):
    root, params, _ = child(tmp_path)
    with raw_process(params) as process:
        initialize(process)
        ping = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}).encode()
        process.stdin.write(ping + b" " * (65535 - len(ping)) + b"\n")
        assert frame(process)["id"] == 2
        process.stdin.write(b"\xff\n")
        process.wait(timeout=4)
        assert process.returncode == 1 and process.stderr.read() == b""
    assert_reaped(root)


def test_eof_during_worker_does_not_close_connection_early(tmp_path):
    root, params, _ = child(tmp_path, populated=True, slow=True)
    with raw_process(params) as process:
        initialize(process)
        send(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "ops_status"}})
        deadline = time.monotonic() + 3
        while "entered" not in [e["event"] for e in trace(root)]:
            assert time.monotonic() < deadline
            time.sleep(.01)
        process.stdin.close()
        time.sleep(.1)
        assert process.poll() is None
        assert [e["event"] for e in trace(root)] == ["startup", "open", "entered"]
        (root / "release").touch()
        process.wait(timeout=4)
        assert "close" in [e["event"] for e in trace(root)]
        assert process.stderr.read() == b""
    assert_reaped(root)


@pytest.mark.parametrize("mode", ["healthy", "buffered", "flushed"])
@pytest.mark.parametrize("ending", ["eof", "oversize", "backpressure"])
def test_raw_stdout_remains_private_through_interpreter_shutdown(tmp_path, mode, ending):
    root, params, _ = child(tmp_path, populated=True, broken=mode != "healthy",
                            flush_output=mode == "flushed")
    with raw_process(params) as process:
        initialize(process)
        send(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": "ops_status"}})
        result = frame(process)
        assert result["id"] == 2 and SENTINEL not in json.dumps(result)
        assert result["result"].get("isError", False) == (mode != "healthy")
        if ending == "oversize":
            try:
                process.stdin.write(b"x" * 65536)
            except BrokenPipeError:
                pass
        elif ending == "backpressure":
            for request_id in range(10, 90):
                send(process, {"jsonrpc": "2.0", "id": request_id, "method": "tools/list"})
            time.sleep(.5)
        process.stdin.close()
        process.wait(timeout=3)
        # Read the actual pipe to EOF AFTER interpreter finalizers, not merely
        # parsed SDK responses. A parser/client teardown can miss trailing prints.
        remaining = process.stdout.read()
        assert SENTINEL.encode() not in remaining
        assert process.stderr.read() == b""
        assert process.returncode == (0 if ending == "eof" else 1)
        if ending != "backpressure":
            assert remaining == b""
    assert_reaped(root)


@pytest.mark.parametrize("legacy_first", [True, False])
def test_raw_era_routing_errors_are_sanitized_before_sdk_serialization(tmp_path, legacy_first):
    root, params, _ = child(tmp_path)
    with raw_process(params) as process:
        if legacy_first:
            initialize(process)
        send(process, {"jsonrpc": "2.0", "id": 10, "method": "tools/list", "params": {
            "_meta": {"io.modelcontextprotocol/protocolVersion": SENTINEL,
                      "io.modelcontextprotocol/clientCapabilities": {}}}})
        response = frame(process)
        assert response["id"] == 10
        assert response["error"] == (
            {"code": -32600, "message": "Invalid request"} if legacy_first else
            {"code": -32022, "message": "Unsupported protocol version"})
        send(process, {"jsonrpc": "2.0", "id": 11, "method": "initialize", "params": {
            "protocolVersion": SENTINEL, "capabilities": {},
            "clientInfo": {"name": SENTINEL, "version": "1"}}})
        response = frame(process)
        assert response["id"] == 11 and SENTINEL not in json.dumps(response)
        if not legacy_first:
            assert response["error"] == {"code": -32022, "message": "Unsupported protocol version"}
            # Valid modern requests still route, even after earlier rejections.
            for request_id, meta in enumerate((
                {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                 "io.modelcontextprotocol/clientCapabilities": SENTINEL},
                {"io.modelcontextprotocol/protocolVersion": "2026-07-28"},
            ), 12):
                send(process, {"jsonrpc": "2.0", "id": request_id, "method": "tools/list",
                               "params": {"_meta": meta}})
                response = frame(process)
                assert response["error"] == {"code": -32602, "message": "Invalid request parameters"}
        process.stdin.close()
        process.wait(timeout=3)
        assert process.returncode == 0
        assert process.stdout.read() == process.stderr.read() == b""
    assert [e["event"] for e in trace(root)] == ["startup", "launcher_returned"]
    assert_reaped(root)


@pytest.mark.parametrize("version", ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"])
def test_raw_all_official_sdk_protocol_versions_remain_usable(tmp_path, version):
    root, params, _ = child(tmp_path)
    modern = version == "2026-07-28"
    meta = {"_meta": {"io.modelcontextprotocol/protocolVersion": version,
                     "io.modelcontextprotocol/clientCapabilities": {}}} if modern else {}
    with raw_process(params) as process:
        if not modern:
            send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": version, "capabilities": {},
                "clientInfo": {"name": "fixture", "version": "1"}}})
            assert frame(process)["result"]["protocolVersion"] == version
            send(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        else:
            send(process, {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": meta})
            assert frame(process)["result"]["supportedVersions"] == [version]
        for request_id, method, args in (
            (2, "tools/list", {}), (3, "tools/call", {"name": "ops_status"}), (4, "ping", {}),
        ):
            send(process, {"jsonrpc": "2.0", "id": request_id, "method": method, "params": {**meta, **args}})
            response = frame(process)
            if modern and method == "ping":
                # Ping is not part of this SDK's modern protocol surface.
                assert response["error"] == {"code": -32601, "message": "Method not found"}
                continue
            assert "result" in response, (method, response)
            result = response["result"]
            if modern:
                assert result["resultType"] == "complete"
                assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "kingdom-telegram-ops"
            if method == "tools/list":
                assert [tool["name"] for tool in result["tools"]] == ["ops_status", "ops_replies", "ops_reply_preview"]
            elif method == "tools/call":
                assert json.loads(result["content"][0]["text"])["status"] == "not_configured"
        process.stdin.close()
        process.wait(timeout=3)
        assert process.returncode == 0
        assert process.stdout.read() == process.stderr.read() == b""
    assert_reaped(root)


@pytest.mark.parametrize("ending", ["eof", "malformed", "oversize", "no_eof", "reader_closed"])
def test_output_backpressure_fails_closed_without_a_stdout_reader(tmp_path, ending):
    root, params, _ = child(tmp_path)
    with raw_process(params) as process:
        initialize(process)
        for request_id in range(2, 82):
            send(process, {"jsonrpc": "2.0", "id": request_id, "method": "tools/list"})
        time.sleep(.5)
        start = time.monotonic()
        if ending == "reader_closed":
            process.stdout.close()
        if ending == "malformed":
            process.stdin.write(("[" + json.dumps(SENTINEL) + "]\n").encode())
        elif ending == "oversize":
            try:
                process.stdin.write(b"x" * 65536)
            except BrokenPipeError:
                pass
        if ending != "no_eof":
            process.stdin.close()
        # DO NOT communicate/drain before wait: that would relieve backpressure
        # and turn the independently confirmed hang into a false pass.
        process.wait(timeout=3)
        assert time.monotonic() - start < 3
        assert process.returncode == 1  # Failed delivery is not a clean success.
        assert process.stderr.read() == b""
        if ending != "reader_closed":
            output = process.stdout.read()
            assert output and SENTINEL.encode() not in output
            # A timeout can leave one trailing partial frame, never a retry.
            lines = output.split(b"\n")
            ids = [json.loads(line)["id"] for line in lines[:-1]]
            assert ids and len(ids) == len(set(ids))
    assert_reaped(root)


@pytest.mark.parametrize("ending", ["eof", "malformed", "oversize"])
def test_blocked_output_shutdown_keeps_active_send_admission_and_provider_lock(tmp_path, ending):
    root, params, reply_id = child(tmp_path, populated=True, sending=True)
    with raw_process(params) as process:
        try:
            initialize(process)
            with AgentToolOpsStore.open_existing(root / "state" / "ops.db") as store:
                item = store.reply_item(reply_id)
            args = {"reply_id": reply_id, "payload_digest": item.payload_digest,
                    "binding_revision": item.binding_revision}
            send(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                           "params": {"name": "ops_reply_send", "arguments": args}})
            deadline = time.monotonic() + 3
            while "send_entered" not in [e["event"] for e in trace(root)]:
                assert time.monotonic() < deadline
                time.sleep(.01)
            for request_id, name, arguments in ((3, "ops_reply_send", args), (4, "ops_pause", {})):
                send(process, {"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                               "params": {"name": name, "arguments": arguments}})
                assert frame(process)["result"]["structuredContent"]["error"] == "busy"
            send(process, {"jsonrpc": "2.0", "id": 5, "method": "ping"})
            assert frame(process)["id"] == 5
            for request_id in range(10, 90):
                send(process, {"jsonrpc": "2.0", "id": request_id, "method": "tools/list"})
            time.sleep(.5)
            if ending == "malformed":
                process.stdin.write(("[" + json.dumps(SENTINEL) + "]\n").encode())
            elif ending == "oversize":
                try:
                    process.stdin.write(b"x" * 65536)
                except BrokenPipeError:
                    pass
            process.stdin.close()
            time.sleep(2.2)  # The 2s writer deadline has elapsed; worker is held.
            assert process.poll() is None
            assert [e["event"] for e in trace(root)] == ["startup", "open", "send_entered"]
            with AgentToolOpsStore.open_existing(root / "state" / "ops.db", readonly=False) as store:
                assert store.reply_item(reply_id).state == "inflight"
                with pytest.raises(runtime.OpsRuntimeError, match="local_lock_busy"):
                    runtime.pause(store, fixture=True, lock_dir=root / "fixture-locks")
            (root / "release").touch()
            process.wait(timeout=3)
            assert process.returncode == 1
            assert process.stderr.read() == b""
            assert SENTINEL.encode() not in process.stdout.read()
            events = trace(root)
            assert [e["event"] for e in events] == ["startup", "open", "send_entered", "send_finished", "send_sent", "close"]
            assert len({e["thread"] for e in events[1:]}) == 1
            assert events[0]["thread"] != events[1]["thread"]
            with AgentToolOpsStore.open_existing(root / "state" / "ops.db") as store:
                item = store.reply_item(reply_id)
                assert item.state == "sent" and item.attempt_count == 1
        finally:
            (root / "release").touch()
    assert_reaped(root)


def test_base_gateway_and_cli_need_no_optional_sdk(tmp_path):
    code = '''
import fcntl, os, sqlite3, subprocess, sys
sys.path.insert(0, sys.argv[1])
class StdlibGatewayOnly:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition(".")[0] not in sys.stdlib_module_names | {"telegram_gateway"}:
            raise ModuleNotFoundError("optional dependency disabled")
sys.meta_path.insert(0, StdlibGatewayOnly())
def forbidden(*args, **kwargs):
    raise AssertionError("unexpected external effect")
def audit(event, args):
    if event.startswith("socket."):
        forbidden()
sys.addaudithook(audit)
sqlite3.connect = fcntl.flock = forbidden
subprocess.Popen = subprocess.run = forbidden
import telegram_gateway
from telegram_gateway import ops_runtime, cli
assert "mcp" not in sys.modules and "pydantic" not in sys.modules
sys.argv = ["telegram_gateway", "--help"]
cli.main()
'''
    result = subprocess.run([str(PYTHON), "-I", "-B", "-S", "-c", code, str(ROOT)],
                            cwd="/Users/yu", env={"HOME": str(tmp_path), "PATH": os.defpath},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout and result.stderr == ""
    assert not list(tmp_path.iterdir())
