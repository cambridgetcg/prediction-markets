from __future__ import annotations

import copy
import json
import os
import time
from collections import deque
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

import pytest

import telegram_gateway.agenttool_mcp as agenttool_mcp
from telegram_gateway.agenttool_mcp import (
    MCP_PROTOCOL_VERSION,
    PINNED_SERVER_NAME,
    PINNED_SERVER_VERSION,
    PINNED_TOOL_INVENTORY,
    READ_ONLY_TOOL_ALLOWLIST,
    AgentToolMcpConfig,
    AgentToolMcpError,
    AgentToolMcpReader,
    McpProcessSpec,
    _decode_json_message,
    build_process_spec,
)
from telegram_gateway.agenttool_ops import CursorAnchor


WORKSPACE_ID = "ws_test"
EPOCH_ID = "epoch_test"
ZERO_HASH = "0" * 64
FIRST_HASH = "1" * 64
SECOND_HASH = "2" * 64
THIRD_HASH = "3" * 64
OBSERVED_AT = "2026-09-03T20:00:00.000000Z"
SECRET = "never-copy-this-sensitive-child-content"


def _tool_inventory() -> dict[str, Any]:
    tools = []
    for name in sorted(PINNED_TOOL_INVENTORY):
        annotations = {
            "readOnlyHint": name in READ_ONLY_TOOL_ALLOWLIST,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        tools.append(
            {
                "name": name,
                "description": f"descriptor for {name}",
                "inputSchema": {"type": "object"},
                "annotations": annotations,
            }
        )
    return {"tools": tools}


def _initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "serverInfo": {
            "name": PINNED_SERVER_NAME,
            "version": PINNED_SERVER_VERSION,
        },
        "capabilities": {"tools": {}},
        "instructions": SECRET,
    }


def _success(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "structuredContent": dict(payload),
        "content": [{"type": "text", "text": SECRET}],
    }


class FakeTransport:
    def __init__(
        self,
        calls: list[tuple[str, Mapping[str, Any]]],
        *,
        initialize: Mapping[str, Any] | None = None,
        inventory: Mapping[str, Any] | None = None,
        failure: BaseException | None = None,
        failure_method: str = "tools/call",
    ):
        if not calls or calls[0][0] != "collab_workspace_status":
            calls = [
                ("collab_workspace_status", _success(_status_payload())),
                *calls,
            ]
        self.expected_calls = deque(calls)
        self.initialize = dict(initialize or _initialize_result())
        self.inventory = dict(inventory or _tool_inventory())
        self.failure = failure
        self.failure_method = failure_method
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.notifications: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        copied = dict(params)
        self.requests.append((method, copied))
        if self.failure is not None and method == self.failure_method:
            raise self.failure
        if method == "initialize":
            return self.initialize
        if method == "tools/list":
            return self.inventory
        if method != "tools/call" or not self.expected_calls:
            raise AssertionError(f"unexpected fake MCP request: {method}")
        expected_name, response = self.expected_calls.popleft()
        assert copied["name"] == expected_name
        return response

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        self.notifications.append((method, dict(params)))

    def close(self) -> None:
        self.closed = True


class FakeFactory:
    def __init__(self, transports: list[FakeTransport]):
        self.transports = deque(transports)
        self.specs: list[McpProcessSpec] = []

    def __call__(self, spec: McpProcessSpec) -> FakeTransport:
        self.specs.append(spec)
        if not self.transports:
            raise AssertionError("unexpected MCP child creation")
        return self.transports.popleft()


@pytest.fixture
def enabled_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AgentToolMcpConfig:
    tmp_path.chmod(0o700)
    runtime = tmp_path / "bun"
    runtime.write_bytes(b"fake executable")
    runtime.chmod(0o700)
    bundle = tmp_path / "agenttool-collab-mcp.js"
    bundle.write_bytes(b"pinned fake bundle")
    bundle.chmod(0o700)
    database = tmp_path / "collab.sqlite"
    database.write_bytes(b"fake private database")
    database.chmod(0o600)
    monkeypatch.setattr(
        agenttool_mcp,
        "_bundle_sha256",
        lambda _path: agenttool_mcp.PINNED_BUNDLE_SHA256,
    )
    return AgentToolMcpConfig(
        workspace_id=WORKSPACE_ID,
        expected_workspace_root=Path.cwd().resolve(),
        enabled=True,
        bun_path=runtime,
        bundle_path=bundle,
        database_path=database,
        child_path="/usr/local/bin:/usr/bin:/bin",
        request_timeout_seconds=0.5,
        shutdown_timeout_seconds=0.1,
        max_response_bytes=16_384,
        max_request_bytes=4_096,
        max_messages_per_request=8,
    )


def _status_payload(*, head_sequence: int = 2, head_hash: str = SECOND_HASH) -> dict[str, Any]:
    return {
        "workspace": {
            "id": WORKSPACE_ID,
            "epoch_id": EPOCH_ID,
            "event_head_sequence": head_sequence,
            "event_head_hash": head_hash,
            "root_path": str(Path.cwd().resolve()),
            "name": SECRET,
        },
        "counts": {"open": 3, "claimed": 2, "blocked": 1, "completed": 4},
        "pending_reviews": [{"title": SECRET}, {"description": SECRET}],
        "active_sessions": [{"actor": SECRET}],
        "active_claims": [{"lease_id": SECRET}],
        "recent_reports": [{"body": SECRET}],
    }


def _event_page_payload() -> dict[str, Any]:
    return {
        "cursor": {"epoch_id": EPOCH_ID, "sequence": 0, "hash": ZERO_HASH},
        "next_cursor": 2,
        "next_anchor": {
            "epoch_id": EPOCH_ID,
            "sequence": 2,
            "hash": SECOND_HASH,
        },
        "head_sequence": 2,
        "head_hash": SECOND_HASH,
        "has_more": False,
        "chain_valid": True,
        "verification_scope": "returned_page",
        "events": [
            {
                "protocol": "agenttool.collab/0.2",
                "workspace_id": WORKSPACE_ID,
                "epoch_id": EPOCH_ID,
                "sequence": 1,
                "id": "event_private",
                "type": "task.reported_complete",
                "entity_id": "task_alpha",
                "actor": SECRET,
                "session_id": SECRET,
                "occurred_at": OBSERVED_AT,
                "payload": {
                    "version": 7,
                    "review_status": "pending",
                    "summary": SECRET,
                    "completion_report_id": SECRET,
                    "result_checkpoint": {"root_path": SECRET},
                },
                "prev_hash": ZERO_HASH,
                "hash": FIRST_HASH,
            },
            {
                "protocol": "agenttool.collab/0.2",
                "workspace_id": WORKSPACE_ID,
                "epoch_id": EPOCH_ID,
                "sequence": 2,
                "id": "event_private_two",
                "type": "artifact.attached",
                "entity_id": "task_alpha",
                "actor": SECRET,
                "session_id": SECRET,
                "occurred_at": OBSERVED_AT,
                "payload": {
                    "version": 8,
                    "artifact": {
                        "task_id": "task_alpha",
                        "uri": SECRET,
                        "attached_by_session_id": SECRET,
                    },
                    "lease_id": SECRET,
                },
                "prev_hash": FIRST_HASH,
                "hash": SECOND_HASH,
            },
        ],
    }


def _reader(
    config: AgentToolMcpConfig, transport: FakeTransport
) -> tuple[AgentToolMcpReader, FakeFactory]:
    factory = FakeFactory([transport])
    return AgentToolMcpReader(config, transport_factory=factory), factory


def _write_fake_stdio_child(path: Path, *, mode: str) -> None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "serverInfo": {
                "name": PINNED_SERVER_NAME,
                "version": PINNED_SERVER_VERSION,
            },
            "capabilities": {"tools": {}},
        },
    }
    inventory = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": _tool_inventory(),
    }

    def status(workspace_id: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": 3,
            "result": _success(
                {
                    "workspace": {
                        "id": workspace_id,
                        "epoch_id": EPOCH_ID,
                        "root_path": str(Path.cwd().resolve()),
                        "event_head_sequence": 2,
                        "event_head_hash": SECOND_HASH,
                    },
                    "counts": {
                        "open": 1,
                        "claimed": 0,
                        "blocked": 0,
                        "completed": 0,
                    },
                    "pending_reviews": [],
                    "active_sessions": [],
                }
            ),
        }

    encoded = [
        json.dumps(initialize, separators=(",", ":")),
        json.dumps(inventory, separators=(",", ":")),
        json.dumps(status(WORKSPACE_ID), separators=(",", ":")),
        json.dumps(status("ws_bad_environment"), separators=(",", ":")),
    ]
    escaped = [line.replace("\\", "\\\\").replace('"', '\\"') for line in encoded]
    source = f'''use strict;
use warnings;
use Time::HiRes qw(sleep);
$| = 1;
my $mode = "{mode}";
open(my $pid_handle, ">", $0 . ".pid") or die "pid";
print $pid_handle $$;
close($pid_handle);
my $environment_ok = join("\\n", sort keys %ENV) eq "AGENTOOL_COLLAB_DB\\nPATH";
while (my $line = <STDIN>) {{
    next unless $line =~ /"id":([0-9]+)/;
    my $id = int($1);
    sleep(10) if $mode eq "timeout";
    exit(0) if $mode eq "eof";
    if ($mode eq "oversize") {{
        print "x" x 6000, "\\n";
        next;
    }}
    print "{escaped[0]}\\n" if $id == 1;
    print "{escaped[1]}\\n" if $id == 2;
    print(($environment_ok ? "{escaped[2]}" : "{escaped[3]}") . "\\n") if $id == 3;
}}
'''
    path.write_text(source, encoding="utf-8")
    path.chmod(0o700)


def _assert_child_reaped(pid_path: Path) -> None:
    pid = int(pid_path.read_text(encoding="ascii"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_disabled_by_default_creates_no_child() -> None:
    called = False

    def forbidden_factory(_spec: McpProcessSpec) -> FakeTransport:
        nonlocal called
        called = True
        raise AssertionError("disabled reader must not create a child")

    reader = AgentToolMcpReader(
        AgentToolMcpConfig(
            workspace_id=WORKSPACE_ID,
            expected_workspace_root=Path.cwd().resolve(),
        ),
        transport_factory=forbidden_factory,
    )
    with pytest.raises(AgentToolMcpError) as caught:
        reader.workspace_status()
    assert caught.value.code == "disabled"
    assert called is False


def test_process_spec_has_exact_minimal_environment_and_redacted_repr(
    enabled_config: AgentToolMcpConfig,
) -> None:
    spec = build_process_spec(enabled_config)
    assert spec.argv == (
        str(enabled_config.bun_path),
        str(enabled_config.bundle_path),
    )
    assert spec.environment_dict() == {
        "AGENTOOL_COLLAB_DB": str(enabled_config.database_path),
        "PATH": enabled_config.child_path,
    }
    serialized_keys = " ".join(spec.environment_dict()).lower()
    for forbidden in ("credential", "session", "recovery", "relay", "bearer"):
        assert forbidden not in serialized_keys
    assert str(enabled_config.database_path) not in repr(spec)
    assert str(enabled_config.bundle_path) not in repr(spec)
    assert WORKSPACE_ID not in repr(enabled_config)


def test_real_stdio_boundary_uses_json_lines_exact_env_and_no_shell(
    enabled_config: AgentToolMcpConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = tmp_path / "fake-child; touch shell_injected"
    _write_fake_stdio_child(bundle, mode="success")
    config = replace(
        enabled_config,
        bun_path=Path("/usr/bin/perl"),
        bundle_path=bundle,
    )
    observed_popen: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    real_popen = agenttool_mcp.subprocess.Popen

    def recording_popen(*args: Any, **kwargs: Any) -> Any:
        observed_popen.append((args, kwargs))
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(agenttool_mcp.subprocess, "Popen", recording_popen)

    status = AgentToolMcpReader(config).workspace_status()

    assert status.head == CursorAnchor(EPOCH_ID, 2, SECOND_HASH)
    assert status.open_tasks == 1
    assert not (tmp_path / "shell_injected").exists()
    _assert_child_reaped(Path(f"{config.bundle_path}.pid"))
    assert len(observed_popen) == 1
    args, kwargs = observed_popen[0]
    assert args[0] == [str(config.bun_path), str(config.bundle_path)]
    assert kwargs["shell"] is False
    assert kwargs["env"] == {
        "AGENTOOL_COLLAB_DB": str(config.database_path),
        "PATH": config.child_path,
    }


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        ("timeout", "transport_timeout"),
        ("eof", "transport_eof"),
        ("oversize", "response_too_large"),
    ],
)
def test_real_fake_child_timeout_eof_and_oversize_are_bounded_and_reaped(
    enabled_config: AgentToolMcpConfig,
    tmp_path: Path,
    mode: str,
    expected_code: str,
) -> None:
    bundle = tmp_path / f"fake-child-{mode}.pl"
    _write_fake_stdio_child(bundle, mode=mode)
    config = replace(
        enabled_config,
        bun_path=Path("/usr/bin/perl"),
        bundle_path=bundle,
        request_timeout_seconds=0.5,
        shutdown_timeout_seconds=0.1,
        max_response_bytes=4_096,
    )
    started = time.monotonic()

    with pytest.raises(AgentToolMcpError) as caught:
        AgentToolMcpReader(config).workspace_status()

    assert caught.value.code == expected_code
    assert time.monotonic() - started < 3.0
    _assert_child_reaped(Path(f"{config.bundle_path}.pid"))


def test_bundle_digest_mismatch_fails_before_transport(
    enabled_config: AgentToolMcpConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agenttool_mcp,
        "_bundle_sha256",
        lambda _path: "f" * 64,
    )
    factory = FakeFactory([])
    reader = AgentToolMcpReader(enabled_config, transport_factory=factory)
    with pytest.raises(AgentToolMcpError) as caught:
        reader.workspace_status()
    assert caught.value.code == "bundle_mismatch"
    assert factory.specs == []


@pytest.mark.parametrize("target", ["parent", "wal", "shm"])
def test_database_boundary_rejects_permissive_parent_or_sidecars(
    enabled_config: AgentToolMcpConfig, target: str
) -> None:
    path = enabled_config.database_path
    if target == "parent":
        path.parent.chmod(0o755)
    else:
        sidecar = Path(f"{path}-{target}")
        sidecar.write_bytes(b"unsafe sidecar")
        sidecar.chmod(0o644)
    with pytest.raises(AgentToolMcpError) as caught:
        build_process_spec(enabled_config)
    assert caught.value.code == "database_unavailable"


def test_workspace_status_verifies_handshake_and_strips_private_fields(
    enabled_config: AgentToolMcpConfig,
) -> None:
    transport = FakeTransport(
        [("collab_workspace_status", _success(_status_payload()))]
    )
    reader, factory = _reader(enabled_config, transport)

    status = reader.workspace_status()

    assert status.head == CursorAnchor(EPOCH_ID, 2, SECOND_HASH)
    assert (
        status.open_tasks,
        status.claimed_tasks,
        status.blocked_tasks,
        status.completed_tasks,
    ) == (3, 2, 1, 4)
    assert status.pending_review_tasks == 2
    assert status.active_session_records == 1
    assert SECRET not in repr(status)
    assert transport.closed is True
    assert transport.expected_calls == deque()
    assert [method for method, _ in transport.requests] == [
        "initialize",
        "tools/list",
        "tools/call",
    ]
    assert transport.notifications == [("notifications/initialized", {})]
    assert transport.requests[-1][1] == {
        "name": "collab_workspace_status",
        "arguments": {"workspace_id": WORKSPACE_ID},
    }
    assert len(factory.specs) == 1


def test_every_operation_fails_closed_on_workspace_root_mismatch(
    enabled_config: AgentToolMcpConfig, tmp_path: Path
) -> None:
    wrong_root = tmp_path / "other-workspace"
    wrong_root.mkdir()
    payload = _status_payload()
    payload["workspace"]["root_path"] = str(wrong_root)
    transport = FakeTransport(
        [("collab_workspace_status", _success(payload))]
    )
    reader, _ = _reader(enabled_config, transport)

    with pytest.raises(AgentToolMcpError) as caught:
        reader.list_tasks()

    assert caught.value.code == "workspace_mismatch"
    assert str(wrong_root) not in str(caught.value)
    assert transport.closed is True


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("protocol", "protocol_mismatch"),
        ("server", "server_mismatch"),
        ("inventory", "tool_inventory_mismatch"),
        ("annotation", "tool_inventory_mismatch"),
    ],
)
def test_handshake_fails_closed_on_pin_or_inventory_drift(
    enabled_config: AgentToolMcpConfig,
    mutation: str,
    expected_code: str,
) -> None:
    initialized = _initialize_result()
    inventory = _tool_inventory()
    if mutation == "protocol":
        initialized["protocolVersion"] = "2024-11-05"
    elif mutation == "server":
        initialized["serverInfo"] = {
            "name": PINNED_SERVER_NAME,
            "version": "0.4.1",
        }
    elif mutation == "inventory":
        inventory["tools"].append(
            {
                "name": "collab_release_room_read",
                "annotations": {
                    "readOnlyHint": True,
                    "destructiveHint": False,
                },
            }
        )
    else:
        descriptor = next(
            item
            for item in inventory["tools"]
            if item["name"] == "collab_events_since"
        )
        descriptor["annotations"]["readOnlyHint"] = False
    transport = FakeTransport(
        [("collab_workspace_status", _success(_status_payload()))],
        initialize=initialized,
        inventory=inventory,
    )
    reader, _ = _reader(enabled_config, transport)

    with pytest.raises(AgentToolMcpError) as caught:
        reader.workspace_status()

    assert caught.value.code == expected_code
    assert transport.closed is True
    assert SECRET not in str(caught.value)


def test_exact_anchor_event_page_retains_only_required_safe_scalars(
    enabled_config: AgentToolMcpConfig,
) -> None:
    payload = _event_page_payload()
    transport = FakeTransport(
        [("collab_events_since", _success(payload))]
    )
    reader, _ = _reader(enabled_config, transport)
    anchor = CursorAnchor.genesis(EPOCH_ID)

    page = reader.events_since(anchor, limit=2)

    assert page.current_anchor == anchor
    assert page.next_anchor == CursorAnchor(EPOCH_ID, 2, SECOND_HASH)
    assert page.head_anchor == page.next_anchor
    assert page.has_more is False
    assert page.verification_scope == "returned_page"
    assert page.projection_events() == (
        {
            "protocol": "agenttool.collab/0.2",
            "epoch_id": EPOCH_ID,
            "sequence": 1,
            "type": "task.reported_complete",
            "entity_id": "task_alpha",
            "occurred_at": OBSERVED_AT,
            "prev_hash": ZERO_HASH,
            "hash": FIRST_HASH,
            "payload": {"version": 7, "review_status": "pending"},
        },
        {
            "protocol": "agenttool.collab/0.2",
            "epoch_id": EPOCH_ID,
            "sequence": 2,
            "type": "artifact.attached",
            "entity_id": "task_alpha",
            "occurred_at": OBSERVED_AT,
            "prev_hash": FIRST_HASH,
            "hash": SECOND_HASH,
            "payload": {
                "version": 8,
                "artifact": {"task_id": "task_alpha"},
            },
        },
    )
    serialized = json.dumps(page.projection_events(), sort_keys=True)
    assert SECRET not in serialized
    for forbidden in (
        "actor",
        "session_id",
        "lease_id",
        "summary",
        "uri",
        "root_path",
        "completion_report_id",
    ):
        assert forbidden not in serialized
    assert transport.requests[-1][1] == {
        "name": "collab_events_since",
        "arguments": {
            "workspace_id": WORKSPACE_ID,
            "after_anchor": {
                "epoch_id": EPOCH_ID,
                "sequence": 0,
                "hash": ZERO_HASH,
            },
            "limit": 2,
        },
    }


def test_review_outcome_is_retained_only_for_matching_review_event(
    enabled_config: AgentToolMcpConfig,
) -> None:
    payload = _event_page_payload()
    event = payload["events"][0]
    event["type"] = "task.changes_requested"
    event["payload"] = {
        "version": 7,
        "outcome": "changes_requested",
        "summary": SECRET,
        "review_id": SECRET,
    }
    payload["events"] = [event]
    payload["next_cursor"] = 1
    payload["next_anchor"] = {
        "epoch_id": EPOCH_ID,
        "sequence": 1,
        "hash": FIRST_HASH,
    }
    payload["head_sequence"] = 1
    payload["head_hash"] = FIRST_HASH
    transport = FakeTransport(
        [("collab_events_since", _success(payload))]
    )
    reader, _ = _reader(enabled_config, transport)

    page = reader.events_since(CursorAnchor.genesis(EPOCH_ID), limit=1)

    assert page.projection_events()[0]["payload"] == {
        "version": 7,
        "outcome": "changes_requested",
    }
    assert SECRET not in json.dumps(page.projection_events())


@pytest.mark.parametrize(
    ("expected_action", "source_fields"),
    [
        ("takeover", {"lease_id": "lease_private"}),
        ("release", {"action": "release"}),
        ("block", {"action": "block"}),
    ],
)
def test_all_pinned_recovery_variants_are_typed_without_recovery_details(
    enabled_config: AgentToolMcpConfig,
    expected_action: str,
    source_fields: dict[str, str],
) -> None:
    payload = _event_page_payload()
    event = payload["events"][0]
    event["type"] = "task.recovered"
    event["payload"] = {
        "version": 7,
        **source_fields,
        "recovery_note": SECRET,
        "prior_lease": {"lease_id": SECRET, "session_id": SECRET},
    }
    payload["events"] = [event]
    payload["next_cursor"] = 1
    payload["next_anchor"] = {
        "epoch_id": EPOCH_ID,
        "sequence": 1,
        "hash": FIRST_HASH,
    }
    payload["head_sequence"] = 1
    payload["head_hash"] = FIRST_HASH
    transport = FakeTransport(
        [("collab_events_since", _success(payload))]
    )
    reader, _ = _reader(enabled_config, transport)

    page = reader.events_since(CursorAnchor.genesis(EPOCH_ID), limit=1)

    assert page.projection_events()[0]["payload"] == {
        "version": 7,
        "action": expected_action,
    }
    assert SECRET not in json.dumps(page.projection_events())


def test_explicit_unknown_recovery_action_fails_closed(
    enabled_config: AgentToolMcpConfig,
) -> None:
    payload = _event_page_payload()
    event = payload["events"][0]
    event["type"] = "task.recovered"
    event["payload"] = {
        "version": 7,
        "action": "force_takeover",
        "lease_id": "lease_private",
    }
    payload["events"] = [event]
    payload["next_cursor"] = 1
    payload["next_anchor"] = {
        "epoch_id": EPOCH_ID,
        "sequence": 1,
        "hash": FIRST_HASH,
    }
    payload["head_sequence"] = 1
    payload["head_hash"] = FIRST_HASH
    transport = FakeTransport(
        [("collab_events_since", _success(payload))]
    )
    reader, _ = _reader(enabled_config, transport)

    with pytest.raises(AgentToolMcpError) as caught:
        reader.events_since(CursorAnchor.genesis(EPOCH_ID), limit=1)

    assert caught.value.code == "invalid_response"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("chain_flag", "journal_chain_invalid"),
        ("cursor", "cursor_mismatch"),
        ("next_cursor", "cursor_mismatch"),
        ("previous_hash", "journal_chain_invalid"),
        ("terminal_hash", "journal_chain_invalid"),
        ("head_hash", "cursor_mismatch"),
    ],
)
def test_event_page_fails_closed_on_cursor_hash_or_chain_mismatch(
    enabled_config: AgentToolMcpConfig,
    mutation: str,
    expected_code: str,
) -> None:
    payload = copy.deepcopy(_event_page_payload())
    if mutation == "chain_flag":
        payload["chain_valid"] = False
    elif mutation == "cursor":
        payload["cursor"]["hash"] = THIRD_HASH
    elif mutation == "next_cursor":
        payload["next_cursor"] = 1
    elif mutation == "previous_hash":
        payload["events"][1]["prev_hash"] = THIRD_HASH
    elif mutation == "terminal_hash":
        payload["next_anchor"]["hash"] = THIRD_HASH
        payload["head_hash"] = THIRD_HASH
    else:
        payload["head_hash"] = THIRD_HASH
    transport = FakeTransport(
        [("collab_events_since", _success(payload))]
    )
    reader, _ = _reader(enabled_config, transport)

    with pytest.raises(AgentToolMcpError) as caught:
        reader.events_since(CursorAnchor.genesis(EPOCH_ID), limit=2)

    assert caught.value.code == expected_code
    assert SECRET not in str(caught.value)


def test_remote_tool_error_exposes_only_bounded_machine_code(
    enabled_config: AgentToolMcpConfig,
) -> None:
    transport = FakeTransport(
        [
            (
                "collab_task_get",
                {
                    "isError": True,
                    "structuredContent": {
                        "error": "cursor_fork_detected",
                        "message": SECRET,
                        "credential": SECRET,
                    },
                    "content": [{"type": "text", "text": SECRET}],
                },
            )
        ]
    )
    reader, _ = _reader(enabled_config, transport)

    with pytest.raises(AgentToolMcpError) as caught:
        reader.get_task("task_alpha")

    assert caught.value.code == "remote_tool_error"
    assert caught.value.remote_code == "cursor_fork_detected"
    assert SECRET not in str(caught.value)
    assert SECRET not in repr(caught.value)


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (TimeoutError(SECRET), "transport_timeout"),
        (EOFError(SECRET), "transport_eof"),
        (OSError(SECRET), "transport_failed"),
    ],
)
def test_transport_failures_are_sanitized_and_child_is_closed(
    enabled_config: AgentToolMcpConfig,
    failure: BaseException,
    expected_code: str,
) -> None:
    transport = FakeTransport(
        [("collab_workspace_status", _success(_status_payload()))],
        failure=failure,
    )
    reader, _ = _reader(enabled_config, transport)

    with pytest.raises(AgentToolMcpError) as caught:
        reader.workspace_status()

    assert caught.value.code == expected_code
    assert SECRET not in str(caught.value)
    assert SECRET not in repr(caught.value)
    assert transport.closed is True


def test_injected_programming_error_is_not_mislabeled_as_transport_failure(
    enabled_config: AgentToolMcpConfig,
) -> None:
    transport = FakeTransport(
        [("collab_workspace_status", _success(_status_payload()))],
        failure=AssertionError("programming defect"),
    )
    reader, _ = _reader(enabled_config, transport)

    with pytest.raises(AssertionError, match="programming defect"):
        reader.workspace_status()

    assert transport.closed is True


def test_task_and_report_views_strip_bodies_people_paths_and_lease_ids(
    enabled_config: AgentToolMcpConfig,
) -> None:
    task = {
        "id": "task_alpha",
        "workspace_id": WORKSPACE_ID,
        "status": "completed",
        "effective_status": "accepted",
        "version": 9,
        "review_status": "accepted",
        "lease_id": SECRET,
        "updated_at": OBSERVED_AT,
        "title": SECRET,
        "description": SECRET,
        "assignee": SECRET,
        "path_scopes": [SECRET],
        "artifacts": [{"uri": SECRET}, {"label": SECRET}],
    }
    report = {
        "id": "report_alpha",
        "workspace_id": WORKSPACE_ID,
        "task_id": "task_alpha",
        "kind": "observation",
        "confidence": "high",
        "relation": "supports",
        "event_sequence": 10,
        "evidence_refs": ["event:event_alpha", "artifact:artifact_alpha"],
        "created_at": OBSERVED_AT,
        "body": SECRET,
        "from_actor": SECRET,
        "from_session_id": SECRET,
        "authority_basis": SECRET,
    }
    transports = [
        FakeTransport([("collab_task_list", _success({"tasks": [task]}))]),
        FakeTransport([("collab_task_get", _success({"task": task}))]),
        FakeTransport([("collab_report_list", _success({"reports": [report]}))]),
    ]
    factory = FakeFactory(transports)
    reader = AgentToolMcpReader(enabled_config, transport_factory=factory)

    listed = reader.list_tasks(status="completed")
    fetched = reader.get_task("task_alpha")
    reports = reader.list_reports(task_id="task_alpha", limit=5)

    assert listed[0].evidence_reference_count is None
    assert listed[0].coordination_lease_recorded is True
    assert fetched is not None and fetched.evidence_reference_count == 2
    assert reports[0].evidence_reference_count == 2
    assert SECRET not in repr(listed)
    assert SECRET not in repr(fetched)
    assert SECRET not in repr(reports)
    called = [
        request[1]["name"]
        for transport in transports
        for request in transport.requests
        if request[0] == "tools/call"
    ]
    assert called == [
        "collab_workspace_status",
        "collab_task_list",
        "collab_workspace_status",
        "collab_task_get",
        "collab_workspace_status",
        "collab_report_list",
    ]


def test_task_not_found_returns_none_without_exposing_remote_message(
    enabled_config: AgentToolMcpConfig,
) -> None:
    transport = FakeTransport(
        [
            (
                "collab_task_get",
                {
                    "isError": True,
                    "structuredContent": {
                        "error": "task_not_found",
                        "message": SECRET,
                    },
                },
            )
        ]
    )
    reader, _ = _reader(enabled_config, transport)
    assert reader.get_task("task_missing") is None


def test_journal_verification_uses_one_child_and_attributes_a_stable_head(
    enabled_config: AgentToolMcpConfig,
) -> None:
    transport = FakeTransport(
        [
            ("collab_workspace_status", _success(_status_payload())),
            (
                "collab_journal_verify",
                _success(
                    {
                        "workspace_id": WORKSPACE_ID,
                        "chain_valid": True,
                        "verification_scope": "full_journal",
                    }
                ),
            ),
            ("collab_workspace_status", _success(_status_payload())),
        ]
    )
    reader, factory = _reader(enabled_config, transport)

    verification = reader.verify_journal()

    assert verification.head == CursorAnchor(EPOCH_ID, 2, SECOND_HASH)
    assert verification.chain_valid is True
    assert verification.verification_scope == "full_journal"
    assert len(factory.specs) == 1
    assert [
        request[1]["name"]
        for request in transport.requests
        if request[0] == "tools/call"
    ] == [
        "collab_workspace_status",
        "collab_journal_verify",
        "collab_workspace_status",
    ]


def test_invalid_journal_is_returned_with_its_stable_checked_head(
    enabled_config: AgentToolMcpConfig,
) -> None:
    transport = FakeTransport(
        [
            ("collab_workspace_status", _success(_status_payload())),
            (
                "collab_journal_verify",
                _success(
                    {
                        "workspace_id": WORKSPACE_ID,
                        "chain_valid": False,
                        "verification_scope": "full_journal",
                    }
                ),
            ),
            ("collab_workspace_status", _success(_status_payload())),
        ]
    )
    reader, _ = _reader(enabled_config, transport)

    verification = reader.verify_journal()

    assert verification.head == CursorAnchor(EPOCH_ID, 2, SECOND_HASH)
    assert verification.chain_valid is False
    assert verification.verification_scope == "full_journal"


def test_journal_verification_rejects_a_moving_head(
    enabled_config: AgentToolMcpConfig,
) -> None:
    verification = {
        "workspace_id": WORKSPACE_ID,
        "chain_valid": True,
        "verification_scope": "full_journal",
    }
    transport = FakeTransport(
        [
            ("collab_workspace_status", _success(_status_payload())),
            ("collab_journal_verify", _success(verification)),
            (
                "collab_workspace_status",
                _success(_status_payload(head_sequence=3, head_hash=THIRD_HASH)),
            ),
        ]
    )
    reader, _ = _reader(enabled_config, transport)

    with pytest.raises(AgentToolMcpError) as caught:
        reader.verify_journal()

    assert caught.value.code == "cursor_mismatch"
    assert transport.closed is True


@pytest.mark.parametrize(
    ("raw", "maximum", "expected_code"),
    [
        (b'{"jsonrpc":"2.0","id":1,"id":2}', 100, "invalid_response"),
        (b'{"value":NaN}', 100, "invalid_response"),
        (b'{"value":"too large"}', 4, "response_too_large"),
        (b"not-json", 100, "invalid_response"),
    ],
)
def test_json_decoder_enforces_size_and_strict_json(
    raw: bytes, maximum: int, expected_code: str
) -> None:
    with pytest.raises(AgentToolMcpError) as caught:
        _decode_json_message(raw, maximum)
    assert caught.value.code == expected_code


def test_public_limits_reject_unbounded_requests_before_child_creation(
    enabled_config: AgentToolMcpConfig,
) -> None:
    factory = FakeFactory([])
    reader = AgentToolMcpReader(enabled_config, transport_factory=factory)
    with pytest.raises(ValueError):
        reader.events_since(CursorAnchor.genesis(EPOCH_ID), limit=51)
    with pytest.raises(ValueError):
        reader.list_reports(limit=51)
    assert factory.specs == []
