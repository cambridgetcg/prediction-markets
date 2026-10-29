"""One-shot, read-only AgentTool Collab MCP adapter.

The adapter is disabled unless a caller explicitly sets ``enabled=True``.  It
starts the exact pinned device bundle as a short-lived stdio child, verifies
the MCP, tool inventory, and configured workspace binding, performs one
bounded read-only operation, and closes the child.
It never reads the Collab SQLite file or a session credential, creates a
Collab session, acknowledges a Collab cursor, contacts Telegram, or loops in
the background.

The child MCP server still owns its normal SQLite initialization boundary and
opens the selected journal read/write.  Consequently these are read-only MCP
operations, not an OS-enforced read-only database process.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import select
import stat
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, TypeVar

from .agenttool_ops import CursorAnchor


MCP_PROTOCOL_VERSION = "2025-11-25"
PINNED_SERVER_NAME = "agenttool-collab"
PINNED_SERVER_VERSION = "0.4.0"
PINNED_BUNDLE_SHA256 = (
    "aa44ee81cdcca46f7633fff53067ca2d4e73cde36e9a1a545ff5d7d218fc3a9f"
)

DEFAULT_BUN_PATH = Path("/usr/local/bin/bun")
DEFAULT_BUNDLE_PATH = (
    Path.home()
    / ".local/share/node-tools/node_modules/@agenttool/collab/"
    "dist/agenttool-collab-mcp.js"
)
DEFAULT_DATABASE_PATH = Path.home() / ".local/share/agenttool/collab.sqlite"
DEFAULT_CHILD_PATH = "/usr/local/bin:/usr/bin:/bin"

MAX_BUNDLE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_REQUEST_BYTES = 64 * 1024
DEFAULT_MAX_MESSAGES_PER_REQUEST = 64
MAX_PAGE_EVENTS = 50
MAX_LIST_ROWS = 50

# Exact npm 0.4.0 witness build.  Requiring this inventory also prevents the
# mutable, same-version release-room source checkout from being used by error.
PINNED_TOOL_INVENTORY = frozenset(
    {
        "collab_anchor_status",
        "collab_artifact_attach",
        "collab_cursor_ack",
        "collab_cursor_reset",
        "collab_decision_record",
        "collab_events_since",
        "collab_handoff_offer",
        "collab_handoff_respond",
        "collab_journal_verify",
        "collab_next",
        "collab_report_append",
        "collab_report_list",
        "collab_session_end",
        "collab_session_heartbeat",
        "collab_session_join",
        "collab_session_leave",
        "collab_session_list",
        "collab_session_start",
        "collab_task_block",
        "collab_task_claim",
        "collab_task_complete",
        "collab_task_create",
        "collab_task_get",
        "collab_task_list",
        "collab_task_progress",
        "collab_task_recover",
        "collab_task_release",
        "collab_task_renew",
        "collab_task_review",
        "collab_task_unblock",
        "collab_workspace_open",
        "collab_workspace_status",
    }
)

# Deliberately restricted to the read-only surface common to Collab 0.3.1 and
# the pinned npm 0.4.0 witness build.  anchor_status is not in the common set.
READ_ONLY_TOOL_ALLOWLIST = frozenset(
    {
        "collab_events_since",
        "collab_journal_verify",
        "collab_report_list",
        "collab_task_get",
        "collab_task_list",
        "collab_workspace_status",
    }
)

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MACHINE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}\Z")
_REMOTE_ERROR = re.compile(r"[a-z][a-z0-9_]{0,95}\Z")
_CONTROL_AND_BIDI = re.compile(
    r"[\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]"
)
_TASK_STATES = frozenset({"open", "claimed", "blocked", "completed"})
_EFFECTIVE_TASK_STATES = frozenset(
    {
        "open",
        "claimed",
        "blocked",
        "completed",
        "lease_expired",
        "recovery_required",
        "reported_complete",
        "accepted",
    }
)
_REVIEW_STATES = frozenset(
    {
        "legacy_unreviewed",
        "not_required",
        "pending",
        "accepted",
        "changes_requested",
    }
)
_TASK_EVENT_KINDS = frozenset(
    {
        "task.created",
        "task.claimed",
        "task.recovered",
        "task.claim_expired",
        "task.lease_renewed",
        "task.progressed",
        "task.released",
        "task.blocked",
        "task.unblocked",
        "task.completed",
        "task.reported_complete",
        "task.accepted",
        "task.changes_requested",
    }
)
_TASK_REVIEW_STATUS_BY_EVENT = {
    "task.completed": "not_required",
    "task.reported_complete": "pending",
}
_TASK_REVIEW_OUTCOME_BY_EVENT = {
    "task.accepted": "accepted",
    "task.changes_requested": "changes_requested",
}
_REPORT_KINDS = frozenset({"observation", "inference", "proposal", "decision"})
_REPORT_RELATIONS = frozenset(
    {"informs", "supports", "challenges", "corrects", "withdraws", "supersedes", "resolves"}
)
_CONFIDENCE = frozenset({"high", "medium", "low", "unknown"})
_FORBIDDEN_CHILD_ENV = frozenset(
    {
        "AGENTOOL_COLLAB_SESSION_FILE",
        "AGENTOOL_COLLAB_ALLOW_CURSOR_RECOVERY",
        "AGENTOOL_COLLAB_RELAY_URL",
        "AGENTOOL_COLLAB_RELAY_TOKEN",
        "AGENTOOL_COLLAB_RELAY_CREDENTIAL_FILE",
        "AGENTOOL_COLLAB_PROJECT_BEARER",
    }
)


_ERROR_MESSAGES = {
    "disabled": "AgentTool MCP one-shot access is disabled",
    "invalid_config": "AgentTool MCP configuration is invalid",
    "runtime_unavailable": "The pinned AgentTool MCP runtime is unavailable",
    "bundle_unavailable": "The pinned AgentTool MCP bundle is unavailable",
    "bundle_mismatch": "The AgentTool MCP bundle fingerprint does not match the pin",
    "database_unavailable": "The configured AgentTool journal is unavailable",
    "transport_failed": "The AgentTool MCP transport failed",
    "transport_timeout": "The AgentTool MCP request timed out",
    "transport_eof": "The AgentTool MCP child closed before replying",
    "request_too_large": "The AgentTool MCP request exceeded its size bound",
    "response_too_large": "The AgentTool MCP response exceeded its size bound",
    "invalid_response": "AgentTool MCP returned an invalid response",
    "protocol_mismatch": "The AgentTool MCP protocol does not match the pin",
    "server_mismatch": "The AgentTool MCP server identity does not match the pin",
    "tool_inventory_mismatch": "The AgentTool MCP tool inventory does not match the pin",
    "workspace_mismatch": "The AgentTool MCP workspace does not match the configured root",
    "tool_not_allowed": "The requested AgentTool MCP operation is not allowed",
    "remote_tool_error": "AgentTool MCP rejected the read operation",
    "cursor_mismatch": "The AgentTool journal cursor does not match the requested anchor",
    "journal_chain_invalid": "The AgentTool journal chain did not validate",
}


class AgentToolMcpError(RuntimeError):
    """A bounded failure that never includes child output or journal content."""

    def __init__(self, code: str, *, remote_code: str | None = None):
        if code not in _ERROR_MESSAGES:
            code = "invalid_response"
        safe_remote = (
            remote_code
            if isinstance(remote_code, str) and _REMOTE_ERROR.fullmatch(remote_code)
            else None
        )
        self.code = code
        self.remote_code = safe_remote
        message = _ERROR_MESSAGES[code]
        if safe_remote is not None:
            message = f"{message} ({safe_remote})"
        super().__init__(message)


@dataclass(frozen=True)
class AgentToolMcpConfig:
    """Explicit runtime pin and one-shot resource bounds."""

    workspace_id: str
    expected_workspace_root: Path
    enabled: bool = False
    bun_path: Path = DEFAULT_BUN_PATH
    bundle_path: Path = DEFAULT_BUNDLE_PATH
    database_path: Path = DEFAULT_DATABASE_PATH
    child_path: str = DEFAULT_CHILD_PATH
    request_timeout_seconds: float = 5.0
    shutdown_timeout_seconds: float = 1.0
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    max_messages_per_request: int = DEFAULT_MAX_MESSAGES_PER_REQUEST

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a boolean")
        _require_machine_id(self.workspace_id, "workspace_id")
        for name in (
            "expected_workspace_root",
            "bun_path",
            "bundle_path",
            "database_path",
        ):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                raise ValueError(f"{name} must be an absolute Path")
        try:
            canonical_root = self.expected_workspace_root.resolve(strict=True)
        except OSError:
            raise ValueError("expected_workspace_root is unavailable") from None
        if not canonical_root.is_dir():
            raise ValueError("expected_workspace_root must be a directory")
        object.__setattr__(self, "expected_workspace_root", canonical_root)
        if (
            not isinstance(self.child_path, str)
            or not self.child_path
            or "\x00" in self.child_path
            or "\n" in self.child_path
        ):
            raise ValueError("child_path is invalid")
        _bounded_number(
            self.request_timeout_seconds,
            "request_timeout_seconds",
            minimum=0.05,
            maximum=30.0,
        )
        _bounded_number(
            self.shutdown_timeout_seconds,
            "shutdown_timeout_seconds",
            minimum=0.05,
            maximum=5.0,
        )
        _bounded_int(
            self.max_response_bytes,
            "max_response_bytes",
            minimum=4_096,
            maximum=4 * 1024 * 1024,
        )
        _bounded_int(
            self.max_request_bytes,
            "max_request_bytes",
            minimum=1_024,
            maximum=256 * 1024,
        )
        _bounded_int(
            self.max_messages_per_request,
            "max_messages_per_request",
            minimum=1,
            maximum=256,
        )

    def __repr__(self) -> str:
        return (
            "AgentToolMcpConfig(workspace_id=<configured>, "
            f"enabled={self.enabled!r}, expected_workspace_root=<configured>, "
            "bun_path=<configured>, "
            "bundle_path=<configured>, database_path=<configured>, "
            f"request_timeout_seconds={self.request_timeout_seconds!r})"
        )


@dataclass(frozen=True)
class McpProcessSpec:
    argv: tuple[str, str]
    environment: tuple[tuple[str, str], ...]
    cwd: str
    request_timeout_seconds: float
    shutdown_timeout_seconds: float
    max_response_bytes: int
    max_request_bytes: int
    max_messages_per_request: int

    def environment_dict(self) -> dict[str, str]:
        return dict(self.environment)

    def __repr__(self) -> str:
        return (
            "McpProcessSpec(argv=<configured>, environment=<minimal-redacted>, "
            "cwd=<configured>, "
            f"request_timeout_seconds={self.request_timeout_seconds!r}, "
            f"shutdown_timeout_seconds={self.shutdown_timeout_seconds!r}, "
            f"max_response_bytes={self.max_response_bytes!r}, "
            f"max_request_bytes={self.max_request_bytes!r}, "
            f"max_messages_per_request={self.max_messages_per_request!r})"
        )


@dataclass(frozen=True)
class WorkspaceStatus:
    head: CursorAnchor
    open_tasks: int
    claimed_tasks: int
    blocked_tasks: int
    completed_tasks: int
    pending_review_tasks: int
    active_session_records: int


@dataclass(frozen=True)
class ReadOnlyTask:
    task_id: str
    status: str
    effective_status: str
    version: int
    review_status: str
    coordination_lease_recorded: bool
    evidence_reference_count: int | None
    updated_at: str


@dataclass(frozen=True)
class ReadOnlyReport:
    report_id: str
    task_id: str | None
    kind: str
    confidence: str
    relation: str | None
    event_sequence: int
    evidence_reference_count: int
    created_at: str


@dataclass(frozen=True)
class CollabEvent:
    """Minimum event fields needed for hash-link and safe projection checks."""

    protocol: str
    epoch_id: str
    sequence: int
    kind: str
    subject_id: str
    occurred_at: str
    previous_hash: str
    hash: str
    observed_version: int | None = None
    observed_review_status: str | None = None
    observed_review_outcome: str | None = None
    observed_recovery_action: str | None = None
    artifact_task_id: str | None = None

    def projection_input(self) -> dict[str, Any]:
        """Return only the fields consumed by ``project_collab_event``."""

        projected: dict[str, Any] = {
            "protocol": self.protocol,
            "epoch_id": self.epoch_id,
            "sequence": self.sequence,
            "type": self.kind,
            "entity_id": self.subject_id,
            "occurred_at": self.occurred_at,
            "prev_hash": self.previous_hash,
            "hash": self.hash,
        }
        payload: dict[str, Any] = {}
        if self.observed_version is not None:
            payload["version"] = self.observed_version
        if self.observed_review_status is not None:
            payload["review_status"] = self.observed_review_status
        if self.observed_review_outcome is not None:
            payload["outcome"] = self.observed_review_outcome
        if self.observed_recovery_action is not None:
            payload["action"] = self.observed_recovery_action
        if self.artifact_task_id is not None:
            payload["artifact"] = {"task_id": self.artifact_task_id}
        if payload:
            projected["payload"] = payload
        return projected


@dataclass(frozen=True)
class EventPage:
    current_anchor: CursorAnchor
    next_anchor: CursorAnchor
    head_anchor: CursorAnchor
    events: tuple[CollabEvent, ...]
    has_more: bool
    verification_scope: str = "returned_page"

    def projection_events(self) -> tuple[dict[str, Any], ...]:
        return tuple(event.projection_input() for event in self.events)


@dataclass(frozen=True)
class JournalVerification:
    head: CursorAnchor
    chain_valid: bool = True
    verification_scope: str = "full_journal"


class McpTransport(Protocol):
    def request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def notify(self, method: str, params: Mapping[str, Any]) -> None: ...

    def close(self) -> None: ...


TransportFactory = Callable[[McpProcessSpec], McpTransport]
T = TypeVar("T")


def build_process_spec(config: AgentToolMcpConfig) -> McpProcessSpec:
    """Validate the explicit pin and return a minimal child-process contract."""

    if not config.enabled:
        raise AgentToolMcpError("disabled")
    _validate_runtime(config.bun_path)
    _validate_database(config.database_path)
    if _bundle_sha256(config.bundle_path) != PINNED_BUNDLE_SHA256:
        raise AgentToolMcpError("bundle_mismatch")
    environment = (
        ("AGENTOOL_COLLAB_DB", str(config.database_path)),
        ("PATH", config.child_path),
    )
    if _FORBIDDEN_CHILD_ENV.intersection(dict(environment)):
        raise AgentToolMcpError("invalid_config")
    return McpProcessSpec(
        argv=(str(config.bun_path), str(config.bundle_path)),
        environment=environment,
        cwd=str(config.bundle_path.parent),
        request_timeout_seconds=config.request_timeout_seconds,
        shutdown_timeout_seconds=config.shutdown_timeout_seconds,
        max_response_bytes=config.max_response_bytes,
        max_request_bytes=config.max_request_bytes,
        max_messages_per_request=config.max_messages_per_request,
    )


class AgentToolMcpReader:
    """Run one short-lived, verified read-only MCP child per public call."""

    def __init__(
        self,
        config: AgentToolMcpConfig,
        *,
        transport_factory: TransportFactory | None = None,
    ):
        if not isinstance(config, AgentToolMcpConfig):
            raise TypeError("config must be AgentToolMcpConfig")
        self.config = config
        self._transport_factory = transport_factory or StdioMcpTransport

    def workspace_status(self) -> WorkspaceStatus:
        return self._run_one_shot(lambda _transport, status: status)

    def events_since(
        self, anchor: CursorAnchor, *, limit: int = MAX_PAGE_EVENTS
    ) -> EventPage:
        if not isinstance(anchor, CursorAnchor):
            raise TypeError("anchor must be CursorAnchor")
        _bounded_int(limit, "limit", minimum=1, maximum=MAX_PAGE_EVENTS)
        return self._one_shot(
            "collab_events_since",
            {
                "workspace_id": self.config.workspace_id,
                "after_anchor": _anchor_dict(anchor),
                "limit": limit,
            },
            lambda payload: self._parse_event_page(payload, anchor, limit),
        )

    def list_tasks(self, *, status: str | None = None) -> tuple[ReadOnlyTask, ...]:
        if status is not None and status not in {"open", "claimed", "blocked", "completed"}:
            raise ValueError("status is invalid")
        arguments: dict[str, Any] = {"workspace_id": self.config.workspace_id}
        if status is not None:
            arguments["status"] = status
        return self._one_shot(
            "collab_task_list", arguments, self._parse_task_list
        )

    def get_task(self, task_id: str) -> ReadOnlyTask | None:
        task_id = _require_machine_id(task_id, "task_id")
        try:
            return self._one_shot(
                "collab_task_get",
                {"workspace_id": self.config.workspace_id, "task_id": task_id},
                self._parse_task_get,
            )
        except AgentToolMcpError as exc:
            if exc.code == "remote_tool_error" and exc.remote_code == "task_not_found":
                return None
            raise

    def list_reports(
        self,
        *,
        task_id: str | None = None,
        after_event_sequence: int | None = None,
        limit: int = MAX_LIST_ROWS,
    ) -> tuple[ReadOnlyReport, ...]:
        _bounded_int(limit, "limit", minimum=1, maximum=MAX_LIST_ROWS)
        arguments: dict[str, Any] = {
            "workspace_id": self.config.workspace_id,
            "limit": limit,
        }
        if task_id is not None:
            arguments["task_id"] = _require_machine_id(task_id, "task_id")
        if after_event_sequence is not None:
            _bounded_int(
                after_event_sequence,
                "after_event_sequence",
                minimum=0,
                maximum=(1 << 63) - 1,
            )
            arguments["after_event_sequence"] = after_event_sequence
        return self._one_shot(
            "collab_report_list", arguments, self._parse_report_list
        )

    def verify_journal(self) -> JournalVerification:
        def verify_at_stable_head(
            transport: McpTransport, before: WorkspaceStatus
        ) -> JournalVerification:
            chain_valid = self._parse_journal_verification(
                self._call_read_tool(
                    transport,
                    "collab_journal_verify",
                    {"workspace_id": self.config.workspace_id},
                )
            )
            after = self._parse_workspace_status(
                self._call_read_tool(
                    transport,
                    "collab_workspace_status",
                    {"workspace_id": self.config.workspace_id},
                )
            )
            if after.head != before.head:
                # A successful full audit cannot be attributed to a later head.
                # The caller may explicitly retry the whole one-shot operation.
                raise AgentToolMcpError("cursor_mismatch")
            return JournalVerification(head=after.head, chain_valid=chain_valid)

        return self._run_one_shot(verify_at_stable_head)

    def _one_shot(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        parser: Callable[[Mapping[str, Any]], T],
    ) -> T:
        return self._run_one_shot(
            lambda transport, _status: parser(
                self._call_read_tool(transport, tool_name, arguments)
            )
        )

    def _run_one_shot(
        self, operation: Callable[[McpTransport, WorkspaceStatus], T]
    ) -> T:
        spec = build_process_spec(self.config)
        transport: McpTransport | None = None
        try:
            transport = self._transport_factory(spec)
            self._handshake(transport)
            status = self._parse_workspace_status(
                self._call_read_tool(
                    transport,
                    "collab_workspace_status",
                    {"workspace_id": self.config.workspace_id},
                )
            )
            return operation(transport, status)
        except AgentToolMcpError:
            raise
        except TimeoutError:
            raise AgentToolMcpError("transport_timeout") from None
        except EOFError:
            raise AgentToolMcpError("transport_eof") from None
        except (OSError, BrokenPipeError, subprocess.SubprocessError):
            raise AgentToolMcpError("transport_failed") from None
        except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            raise AgentToolMcpError("invalid_response") from None
        finally:
            if transport is not None:
                with contextlib.suppress(Exception):
                    transport.close()

    @staticmethod
    def _call_read_tool(
        transport: McpTransport,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if tool_name not in READ_ONLY_TOOL_ALLOWLIST:
            raise AgentToolMcpError("tool_not_allowed")
        response = transport.request(
            "tools/call", {"name": tool_name, "arguments": dict(arguments)}
        )
        return _tool_payload(response)

    @staticmethod
    def _handshake(transport: McpTransport) -> None:
        initialized = transport.request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "kingdom-agenttool-readonly",
                    "version": "0.1.0",
                },
            },
        )
        if initialized.get("protocolVersion") != MCP_PROTOCOL_VERSION:
            raise AgentToolMcpError("protocol_mismatch")
        server = _mapping(initialized.get("serverInfo"))
        if (
            server.get("name") != PINNED_SERVER_NAME
            or server.get("version") != PINNED_SERVER_VERSION
        ):
            raise AgentToolMcpError("server_mismatch")
        capabilities = _mapping(initialized.get("capabilities"))
        if not isinstance(capabilities.get("tools"), Mapping):
            raise AgentToolMcpError("protocol_mismatch")
        transport.notify("notifications/initialized", {})
        inventory = transport.request("tools/list", {})
        _verify_tool_inventory(inventory)

    def _parse_workspace_status(self, payload: Mapping[str, Any]) -> WorkspaceStatus:
        workspace = _mapping(payload.get("workspace"))
        if workspace.get("id") != self.config.workspace_id:
            raise AgentToolMcpError("invalid_response")
        root_path = _safe_text(workspace.get("root_path"), "workspace root", 4_096)
        try:
            observed_root = Path(root_path).resolve(strict=True)
        except OSError:
            raise AgentToolMcpError("invalid_response") from None
        if observed_root != self.config.expected_workspace_root:
            raise AgentToolMcpError("workspace_mismatch")
        head = _head_anchor(workspace)
        counts = _mapping(payload.get("counts"))
        return WorkspaceStatus(
            head=head,
            open_tasks=_nonnegative(counts.get("open"), "open"),
            claimed_tasks=_nonnegative(counts.get("claimed"), "claimed"),
            blocked_tasks=_nonnegative(counts.get("blocked"), "blocked"),
            completed_tasks=_nonnegative(counts.get("completed"), "completed"),
            pending_review_tasks=len(_bounded_list(payload.get("pending_reviews"))),
            active_session_records=len(_bounded_list(payload.get("active_sessions"))),
        )

    def _parse_event_page(
        self,
        payload: Mapping[str, Any],
        requested: CursorAnchor,
        limit: int,
    ) -> EventPage:
        if payload.get("chain_valid") is not True:
            raise AgentToolMcpError("journal_chain_invalid")
        if payload.get("verification_scope") != "returned_page":
            raise AgentToolMcpError("invalid_response")
        current = _parse_anchor(payload.get("cursor"))
        if current != requested:
            raise AgentToolMcpError("cursor_mismatch")
        next_anchor = _parse_anchor(payload.get("next_anchor"))
        if next_anchor.epoch_id != current.epoch_id or next_anchor.sequence < current.sequence:
            raise AgentToolMcpError("cursor_mismatch")
        if payload.get("next_cursor") != next_anchor.sequence:
            raise AgentToolMcpError("cursor_mismatch")
        head = CursorAnchor(
            epoch_id=current.epoch_id,
            sequence=_nonnegative(payload.get("head_sequence"), "head_sequence"),
            hash=_require_hash(payload.get("head_hash"), "head_hash"),
        )
        if head.sequence < next_anchor.sequence:
            raise AgentToolMcpError("cursor_mismatch")
        if head.sequence == next_anchor.sequence and head.hash != next_anchor.hash:
            raise AgentToolMcpError("cursor_mismatch")
        has_more = payload.get("has_more")
        if not isinstance(has_more, bool) or has_more != (next_anchor.sequence < head.sequence):
            raise AgentToolMcpError("cursor_mismatch")

        raw_events = _bounded_list(payload.get("events"), maximum=limit)
        if len(raw_events) != next_anchor.sequence - current.sequence:
            raise AgentToolMcpError("cursor_mismatch")
        events: list[CollabEvent] = []
        previous_hash = current.hash
        for offset, raw in enumerate(raw_events, start=1):
            event = _mapping(raw)
            if event.get("workspace_id") != self.config.workspace_id:
                raise AgentToolMcpError("invalid_response")
            if event.get("epoch_id") != current.epoch_id:
                raise AgentToolMcpError("cursor_mismatch")
            sequence = _positive(event.get("sequence"), "event sequence")
            if sequence != current.sequence + offset:
                raise AgentToolMcpError("cursor_mismatch")
            prior = _require_hash(event.get("prev_hash"), "event prev_hash")
            event_hash = _require_hash(event.get("hash"), "event hash")
            if prior != previous_hash:
                raise AgentToolMcpError("journal_chain_invalid")
            protocol = _safe_text(event.get("protocol"), "event protocol", 64)
            if protocol not in {"agenttool.collab/0.1", "agenttool.collab/0.2"}:
                raise AgentToolMcpError("invalid_response")
            kind = _safe_text(event.get("type"), "event type", 96)
            (
                observed_version,
                observed_review_status,
                observed_review_outcome,
                observed_recovery_action,
                artifact_task_id,
            ) = _safe_event_payload(kind, event.get("payload"))
            events.append(
                CollabEvent(
                    protocol=protocol,
                    epoch_id=current.epoch_id,
                    sequence=sequence,
                    kind=kind,
                    subject_id=_safe_text(
                        event.get("entity_id"), "event subject", 512
                    ),
                    occurred_at=_timestamp(event.get("occurred_at"), "occurred_at"),
                    previous_hash=prior,
                    hash=event_hash,
                    observed_version=observed_version,
                    observed_review_status=observed_review_status,
                    observed_review_outcome=observed_review_outcome,
                    observed_recovery_action=observed_recovery_action,
                    artifact_task_id=artifact_task_id,
                )
            )
            previous_hash = event_hash
        if previous_hash != next_anchor.hash:
            raise AgentToolMcpError("journal_chain_invalid")
        return EventPage(
            current_anchor=current,
            next_anchor=next_anchor,
            head_anchor=head,
            events=tuple(events),
            has_more=has_more,
        )

    def _parse_task_list(self, payload: Mapping[str, Any]) -> tuple[ReadOnlyTask, ...]:
        tasks = _bounded_list(payload.get("tasks"), maximum=10_000)
        return tuple(self._parse_task(_mapping(task), include_artifacts=False) for task in tasks)

    def _parse_task_get(self, payload: Mapping[str, Any]) -> ReadOnlyTask:
        return self._parse_task(_mapping(payload.get("task")), include_artifacts=True)

    def _parse_task(
        self, task: Mapping[str, Any], *, include_artifacts: bool
    ) -> ReadOnlyTask:
        if task.get("workspace_id") != self.config.workspace_id:
            raise AgentToolMcpError("invalid_response")
        status = _safe_enum(task.get("status"), _TASK_STATES, "task status")
        effective = _safe_enum(
            task.get("effective_status"),
            _EFFECTIVE_TASK_STATES,
            "effective task status",
        )
        review = _safe_enum(
            task.get("review_status"), _REVIEW_STATES, "review status"
        )
        lease = task.get("lease_id")
        if lease is not None and not isinstance(lease, str):
            raise AgentToolMcpError("invalid_response")
        artifacts = task.get("artifacts") if include_artifacts else None
        artifact_count = (
            len(_bounded_list(artifacts, maximum=10_000))
            if artifacts is not None
            else None
        )
        return ReadOnlyTask(
            task_id=_require_machine_id(task.get("id"), "task id"),
            status=status,
            effective_status=effective,
            version=_positive(task.get("version"), "task version"),
            review_status=review,
            coordination_lease_recorded=lease is not None,
            evidence_reference_count=artifact_count,
            updated_at=_timestamp(task.get("updated_at"), "task updated_at"),
        )

    def _parse_report_list(
        self, payload: Mapping[str, Any]
    ) -> tuple[ReadOnlyReport, ...]:
        reports = _bounded_list(payload.get("reports"), maximum=MAX_LIST_ROWS)
        projected: list[ReadOnlyReport] = []
        for raw in reports:
            report = _mapping(raw)
            if report.get("workspace_id") != self.config.workspace_id:
                raise AgentToolMcpError("invalid_response")
            task_id = report.get("task_id")
            if task_id is not None:
                task_id = _require_machine_id(task_id, "task id")
            relation = report.get("relation")
            if relation is not None:
                relation = _safe_enum(
                    relation, _REPORT_RELATIONS, "report relation"
                )
            projected.append(
                ReadOnlyReport(
                    report_id=_require_machine_id(report.get("id"), "report id"),
                    task_id=task_id,
                    kind=_safe_enum(report.get("kind"), _REPORT_KINDS, "report kind"),
                    confidence=_safe_enum(
                        report.get("confidence"), _CONFIDENCE, "report confidence"
                    ),
                    relation=relation,
                    event_sequence=_positive(
                        report.get("event_sequence"), "report event sequence"
                    ),
                    evidence_reference_count=len(
                        _bounded_list(report.get("evidence_refs"), maximum=10_000)
                    ),
                    created_at=_timestamp(report.get("created_at"), "report created_at"),
                )
            )
        return tuple(projected)

    def _parse_journal_verification(self, payload: Mapping[str, Any]) -> bool:
        if payload.get("workspace_id") != self.config.workspace_id:
            raise AgentToolMcpError("invalid_response")
        if payload.get("verification_scope") != "full_journal":
            raise AgentToolMcpError("invalid_response")
        chain_valid = payload.get("chain_valid")
        if not isinstance(chain_valid, bool):
            raise AgentToolMcpError("invalid_response")
        return chain_valid


class StdioMcpTransport:
    """Bounded JSON-line MCP stdio transport for one short-lived child."""

    def __init__(self, spec: McpProcessSpec):
        self._spec = spec
        self._next_id = 1
        self._buffer = bytearray()
        self._closed = False
        try:
            self._process = subprocess.Popen(
                list(spec.argv),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=spec.cwd,
                env=spec.environment_dict(),
                shell=False,
                close_fds=True,
                bufsize=0,
            )
        except (OSError, subprocess.SubprocessError):
            raise AgentToolMcpError("transport_failed") from None
        if self._process.stdin is None or self._process.stdout is None:
            self.close()
            raise AgentToolMcpError("transport_failed")
        self._stdin_fd = self._process.stdin.fileno()
        self._stdout_fd = self._process.stdout.fileno()
        try:
            os.set_blocking(self._stdin_fd, False)
            os.set_blocking(self._stdout_fd, False)
        except OSError:
            self.close()
            raise AgentToolMcpError("transport_failed") from None

    def request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._write(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)}
        )
        deadline = time.monotonic() + self._spec.request_timeout_seconds
        output_bytes = [0]
        for _ in range(self._spec.max_messages_per_request):
            message = self._read(deadline, output_bytes)
            message_id = message.get("id")
            if type(message_id) is not int or message_id != request_id:
                continue
            if message.get("jsonrpc") != "2.0":
                raise AgentToolMcpError("invalid_response")
            if "error" in message:
                raise AgentToolMcpError("transport_failed")
            return _mapping(message.get("result"))
        raise AgentToolMcpError("invalid_response")

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    def _write(self, message: Mapping[str, Any]) -> None:
        if self._closed:
            raise EOFError
        try:
            encoded = (
                json.dumps(
                    dict(message),
                    ensure_ascii=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("ascii")
                + b"\n"
            )
        except (TypeError, ValueError, RecursionError):
            raise AgentToolMcpError("invalid_config") from None
        if len(encoded) > self._spec.max_request_bytes:
            raise AgentToolMcpError("request_too_large")
        deadline = time.monotonic() + self._spec.request_timeout_seconds
        view = memoryview(encoded)
        while view:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            _, writable, _ = select.select([], [self._stdin_fd], [], remaining)
            if not writable:
                raise TimeoutError
            try:
                written = os.write(self._stdin_fd, view)
            except BlockingIOError:
                continue
            if written <= 0:
                raise EOFError
            view = view[written:]

    def _read(self, deadline: float, output_bytes: list[int]) -> Mapping[str, Any]:
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                if newline > self._spec.max_response_bytes:
                    raise AgentToolMcpError("response_too_large")
                raw = bytes(self._buffer[:newline])
                del self._buffer[: newline + 1]
                if not raw.strip():
                    continue
                return _decode_json_message(raw, self._spec.max_response_bytes)
            if len(self._buffer) > self._spec.max_response_bytes:
                raise AgentToolMcpError("response_too_large")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            readable, _, _ = select.select([self._stdout_fd], [], [], remaining)
            if not readable:
                raise TimeoutError
            try:
                remaining_bytes = self._spec.max_response_bytes - output_bytes[0]
                if remaining_bytes <= 0:
                    raise AgentToolMcpError("response_too_large")
                chunk = os.read(self._stdout_fd, min(65_536, remaining_bytes + 1))
            except BlockingIOError:
                continue
            if not chunk:
                raise EOFError
            output_bytes[0] += len(chunk)
            if output_bytes[0] > self._spec.max_response_bytes:
                raise AgentToolMcpError("response_too_large")
            self._buffer.extend(chunk)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(OSError):
            if self._process.stdin is not None:
                self._process.stdin.close()
        try:
            self._process.wait(timeout=self._spec.shutdown_timeout_seconds)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                self._process.terminate()
            try:
                self._process.wait(timeout=self._spec.shutdown_timeout_seconds)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(OSError):
                    self._process.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    self._process.wait(timeout=self._spec.shutdown_timeout_seconds)
        with contextlib.suppress(OSError):
            if self._process.stdout is not None:
                self._process.stdout.close()


def _verify_tool_inventory(value: Mapping[str, Any]) -> None:
    raw_tools = _bounded_list(value.get("tools"), maximum=64)
    if value.get("nextCursor") not in (None, ""):
        raise AgentToolMcpError("tool_inventory_mismatch")
    descriptors: dict[str, Mapping[str, Any]] = {}
    for raw in raw_tools:
        descriptor = _mapping(raw)
        name = descriptor.get("name")
        if not isinstance(name, str) or name in descriptors:
            raise AgentToolMcpError("tool_inventory_mismatch")
        descriptors[name] = descriptor
    if frozenset(descriptors) != PINNED_TOOL_INVENTORY:
        raise AgentToolMcpError("tool_inventory_mismatch")
    for name in READ_ONLY_TOOL_ALLOWLIST:
        annotations = _mapping(descriptors[name].get("annotations"))
        if (
            annotations.get("readOnlyHint") is not True
            or annotations.get("destructiveHint") is not False
        ):
            raise AgentToolMcpError("tool_inventory_mismatch")


def _tool_payload(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if value.get("isError") is True:
        structured = value.get("structuredContent")
        remote_code = structured.get("error") if isinstance(structured, Mapping) else None
        raise AgentToolMcpError("remote_tool_error", remote_code=remote_code)
    if value.get("isError") not in (None, False):
        raise AgentToolMcpError("invalid_response")
    return _mapping(value.get("structuredContent"))


def _decode_json_message(raw: bytes, maximum: int) -> Mapping[str, Any]:
    if not isinstance(raw, bytes) or len(raw) > maximum:
        raise AgentToolMcpError("response_too_large")

    def reject_constant(_value: str) -> None:
        raise ValueError("non-finite JSON")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            raw.decode("utf-8", errors="strict"),
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except (UnicodeError, ValueError, RecursionError, json.JSONDecodeError):
        raise AgentToolMcpError("invalid_response") from None
    return _mapping(parsed)


def _safe_event_payload(
    kind: str, value: Any
) -> tuple[int | None, str | None, str | None, str | None, str | None]:
    """Extract only event-kind-specific scalars required by the ops store."""

    if kind not in _TASK_EVENT_KINDS and kind != "artifact.attached":
        return None, None, None, None, None
    payload = _mapping(value)
    version = _positive(payload.get("version"), "event task version")

    if kind == "artifact.attached":
        artifact = _mapping(payload.get("artifact"))
        task_id = _safe_text(artifact.get("task_id"), "artifact task_id", 512)
        return version, None, None, None, task_id

    review_status: str | None = None
    expected_review = _TASK_REVIEW_STATUS_BY_EVENT.get(kind)
    raw_review = payload.get("review_status")
    if expected_review is not None and raw_review is not None:
        review_status = _safe_enum(raw_review, _REVIEW_STATES, "event review status")
        if review_status != expected_review:
            raise AgentToolMcpError("invalid_response")

    review_outcome: str | None = None
    expected_outcome = _TASK_REVIEW_OUTCOME_BY_EVENT.get(kind)
    raw_outcome = payload.get("outcome")
    if expected_outcome is not None and raw_outcome is not None:
        review_outcome = _safe_enum(
            raw_outcome,
            frozenset(_TASK_REVIEW_OUTCOME_BY_EVENT.values()),
            "event review outcome",
        )
        if review_outcome != expected_outcome:
            raise AgentToolMcpError("invalid_response")
    recovery_action: str | None = None
    raw_recovery_action = payload.get("action")
    if kind == "task.recovered" and raw_recovery_action in {
        "takeover",
        "release",
        "block",
    }:
        recovery_action = raw_recovery_action
    elif kind == "task.recovered" and raw_recovery_action is None:
        # In the pinned 0.4.0 bundle, takeover events omit ``action`` but carry
        # a new lease.  Validate that discriminator without retaining the ID.
        raw_lease_id = payload.get("lease_id")
        if raw_lease_id is not None:
            _require_machine_id(raw_lease_id, "recovery lease_id")
            recovery_action = "takeover"
    elif kind == "task.recovered":
        raise AgentToolMcpError("invalid_response")
    return version, review_status, review_outcome, recovery_action, None


def _validate_runtime(path: Path) -> None:
    try:
        resolved = path.stat()
    except OSError:
        raise AgentToolMcpError("runtime_unavailable") from None
    if not stat.S_ISREG(resolved.st_mode) or not os.access(path, os.X_OK):
        raise AgentToolMcpError("runtime_unavailable")


def _validate_database(path: Path) -> None:
    try:
        parent = path.parent.lstat()
    except OSError:
        raise AgentToolMcpError("database_unavailable") from None
    if (
        not stat.S_ISDIR(parent.st_mode)
        or stat.S_ISLNK(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) & 0o077
    ):
        raise AgentToolMcpError("database_unavailable")
    try:
        metadata = path.lstat()
    except OSError:
        raise AgentToolMcpError("database_unavailable") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise AgentToolMcpError("database_unavailable")
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        try:
            metadata = sidecar.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise AgentToolMcpError("database_unavailable") from None
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise AgentToolMcpError("database_unavailable")


def _bundle_sha256(path: Path) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise AgentToolMcpError("bundle_unavailable") from None
    digest = hashlib.sha256()
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= MAX_BUNDLE_BYTES:
            raise AgentToolMcpError("bundle_unavailable")
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise AgentToolMcpError("bundle_unavailable")
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise AgentToolMcpError("bundle_unavailable")
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise AgentToolMcpError("invalid_response")
    return value


def _bounded_list(value: Any, *, maximum: int = 10_000) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        raise AgentToolMcpError("invalid_response")
    return value


def _require_machine_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or _MACHINE_ID.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{label} is invalid")
    return value


def _safe_text(value: Any, label: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or _CONTROL_AND_BIDI.search(value) is not None
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _timestamp(value: Any, label: str) -> str:
    text = _safe_text(value, label, 80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (OverflowError, ValueError):
        raise ValueError(f"{label} is invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} is invalid")
    return text


def _safe_enum(value: Any, choices: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{label} is invalid")
    return value


def _bounded_int(
    value: Any, label: str, *, minimum: int, maximum: int
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _bounded_number(
    value: Any, label: str, *, minimum: float, maximum: float
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not minimum <= float(value) <= maximum
    ):
        raise ValueError(f"{label} is invalid")
    return float(value)


def _nonnegative(value: Any, label: str) -> int:
    return _bounded_int(value, label, minimum=0, maximum=(1 << 63) - 1)


def _positive(value: Any, label: str) -> int:
    return _bounded_int(value, label, minimum=1, maximum=(1 << 63) - 1)


def _parse_anchor(value: Any) -> CursorAnchor:
    anchor = _mapping(value)
    return CursorAnchor(
        epoch_id=_safe_text(anchor.get("epoch_id"), "anchor epoch", 160),
        sequence=_nonnegative(anchor.get("sequence"), "anchor sequence"),
        hash=_require_hash(anchor.get("hash"), "anchor hash"),
    )


def _head_anchor(workspace: Mapping[str, Any]) -> CursorAnchor:
    return CursorAnchor(
        epoch_id=_safe_text(workspace.get("epoch_id"), "workspace epoch", 160),
        sequence=_nonnegative(
            workspace.get("event_head_sequence"), "workspace head sequence"
        ),
        hash=_require_hash(workspace.get("event_head_hash"), "workspace head hash"),
    )


def _anchor_dict(anchor: CursorAnchor) -> dict[str, Any]:
    return {
        "epoch_id": anchor.epoch_id,
        "sequence": anchor.sequence,
        "hash": anchor.hash,
    }
