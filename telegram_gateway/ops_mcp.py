"""Optional, finite stdio MCP adapter for the private foreground Ops runtime.

Only this module imports the isolated MCP dependencies. No configuration,
credentials, databases or locks are opened at import time or tool discovery.
The interaction metadata is a host hint, not proof of approval. A digest is
payload-consistency evidence only. Configure sending only after independently
verifying the running host's every-call interaction UI with harmless fixtures.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import stat
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import anyio
import anyio.lowlevel
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.shared.message import SessionMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from . import ops_runtime as runtime
from .agenttool_ops import AgentToolOpsStore, BindingStateError, DatabaseRoleError, DeliveryStateError

MAX_FRAME_BYTES = 64 * 1024
MAX_RESULT_BYTES = 48 * 1024
MAX_CONFIG_BYTES = 8192
OUTPUT_FRAME_TIMEOUT = 2.0
MAX_OUTPUT_DEPTH = 64
CONFIG_PATH = Path.home() / ".config" / "kingdom-telegram-ops" / "mcp.json"

ReplyId = Annotated[str, Field(min_length=36, max_length=36, pattern=r"^rpl_[0-9a-f]{32}$")]
Digest = Annotated[str, Field(min_length=71, max_length=71, pattern=r"^sha256:[0-9a-f]{64}$")]
Label = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
Positive = Annotated[int, Field(ge=1, le=(1 << 31) - 1)]
State = Literal["pending", "inflight", "sent", "failed", "unknown", "invalidated", "all"]
Capability = Literal["poll", "send", "pause", "reconcile"]


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, hide_input_in_errors=True)


class EmptyInput(StrictModel):
    pass


class RepliesInput(StrictModel):
    state: State = "pending"
    limit: Annotated[int, Field(ge=1, le=20)] = 20
    after_reply_id: ReplyId | None = None


class PreviewInput(StrictModel):
    reply_id: ReplyId


class SendInput(PreviewInput):
    payload_digest: Digest
    binding_revision: Positive


class ReconcileInput(PreviewInput):
    attempt_count: Positive
    outcome: Literal["sent", "failed", "unknown"]
    reconciliation_ref: Label
    receipt_ref: Label | None = None

    @model_validator(mode="after")
    def receipt_matches_outcome(self) -> Self:
        if (self.outcome == "sent") != (self.receipt_ref is not None):
            raise ValueError("invalid_input")
        return self


class Config(StrictModel):
    """Operator-only file, never a tool argument or environment override.

    Custom/versioned dedicated Ops slots are valid credential locators, just
    like username-derived slots. This v2 store has no durable username field;
    only the live runtime's getMe check verifies the configured bot username.
    """

    db_path: Annotated[str, Field(min_length=1, max_length=4096)]
    expected_bot_username: Annotated[str, Field(
        min_length=5, max_length=32, pattern=r"^[A-Za-z0-9_]{2,29}[Bb][Oo][Tt]$"
    )] | None = None
    source_binding: Label | None = None
    keychain_account_name: Annotated[str, Field(
        min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$"
    )] | None = None
    capabilities: Annotated[tuple[Capability, ...], Field(max_length=4)] = ()

    @model_validator(mode="after")
    def coherent(self) -> Self:
        path = Path(self.db_path)
        if (not path.is_absolute() or ".." in path.parts
                or any(ord(char) < 32 for char in self.db_path)):
            raise ValueError("invalid_config")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("invalid_config")
        username, account = self.expected_bot_username, self.keychain_account_name
        if account is not None and username is None:
            raise ValueError("invalid_config")
        if {"poll", "send"}.intersection(self.capabilities):
            if username is None or account is None or self.source_binding is None:
                raise ValueError("invalid_config")
        return self


@dataclass(frozen=True)
class Configuration:
    config: Config | None = None
    error: str | None = None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid_config")
        result[key] = value
    return result


def _load_configuration() -> Configuration:
    """Read the fixed owner-only file once, bounded, without creating anything."""
    path = CONFIG_PATH
    try:
        # lstat all ancestors: no symlink traversal, including a dangling link.
        for part in reversed((path, *path.parents)):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("unsafe_config")
        parent = path.parent.stat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
                or parent.st_mode & 0o077):
            raise ValueError("unsafe_config")
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_mode & 0o077 or info.st_nlink != 1
                        or info.st_size > MAX_CONFIG_BYTES):
                    raise ValueError("unsafe_config")
                data = bytearray()
                while len(data) <= MAX_CONFIG_BYTES:
                    chunk = os.read(fd, min(4096, MAX_CONFIG_BYTES + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                linked = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
                if (len(data) > MAX_CONFIG_BYTES or
                        (linked.st_dev, linked.st_ino) != (info.st_dev, info.st_ino)):
                    raise ValueError("unsafe_config")
            finally:
                os.close(fd)
        finally:
            os.close(directory)
        raw = json.loads(data, object_pairs_hook=_unique_object)
        if raw == {}:
            return Configuration(error="not_configured")
        # JSON's list -> immutable tuple conversion belongs to JSON validation,
        # not permissive Python argument coercion. Reject duplicate keys above.
        config = Config.model_validate_json(json.dumps(raw))
        return Configuration(config=config)
    except FileNotFoundError:
        return Configuration(error="not_configured")
    except Exception:
        return Configuration(error="invalid_config")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    model: type[StrictModel]
    description: str
    capability: str | None = None
    interaction: bool = False
    external: bool = False
    destructive: bool = False
    idempotent: bool = False


TOOLS = (
    ToolSpec("ops_status", EmptyInput, "Minimized local Ops state. No credentials, provider or source-journal access.", idempotent=True),
    ToolSpec("ops_replies", RepliesInput, "Page local reply metadata only; pending by default, at most 20. Use all for terminal/inflight history.", idempotent=True),
    ToolSpec("ops_reply_preview", PreviewInput, "Disclose one exact stored reply's text to the MCP client/model, with digest, revision and eligibility. Neither digest nor eligibility is human approval.", interaction=True, idempotent=True),
    ToolSpec("ops_poll_once", EmptyInput, "Poll one batch of at most 20 updates, timeout 0; persist dispositions/replies, send zero messages.", capability="poll", interaction=True, external=True, destructive=True),
    ToolSpec("ops_reply_send", SendInput, "Attempt exactly one queued reply with matching digest/revision. No automatic retry. Requires separately verified host interaction; digest is not approval.", capability="send", interaction=True, external=True, destructive=True),
    ToolSpec("ops_pause", EmptyInput, "Pause locally and invalidate pending replies. Does not retract messages, resume, or stop agents. Busy while another operation is still running.", capability="pause", interaction=True, destructive=True, idempotent=True),
    ToolSpec("ops_reconcile", ReconcileInput, "Record one supplied delivery observation, fenced to its attempt. Not independently verified; never resends or permits retry.", capability="reconcile", interaction=True, destructive=True),
)

_ERROR_CODES = frozenset({
    "not_configured", "invalid_config", "invalid_input", "tool_disabled", "unknown_tool",
    "busy", "unavailable", "binding_mismatch", "binding_required", "source_binding_required",
    "reply_not_pending", "stale_preview", "poll_offset_exhausted", "invalid_update_batch",
    "binding_unavailable", "delivery_state_conflict", "result_too_large",
})


def _error(code: str) -> types.CallToolResult:
    code = code if code in _ERROR_CODES else "unavailable"
    payload = {"error": code, "automatic_retry": False}
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(payload))],
                                structured_content=payload, is_error=True)


def _result(payload: dict[str, Any]) -> types.CallToolResult:
    # iterencode stops before serializing an entire oversized result. Individual
    # stored strings are bounded by the runtime; do not truncate exact previews.
    parts: list[str] = []
    size = 0
    for part in json.JSONEncoder(ensure_ascii=True, allow_nan=False).iterencode(payload):
        size += len(part)
        if size > MAX_RESULT_BYTES:
            return _error("result_too_large")
        parts.append(part)
    result = types.CallToolResult(content=[types.TextContent(type="text", text="".join(parts))],
                                  structured_content=payload, is_error=False)
    if len(result.model_dump_json(by_alias=True).encode("utf-8")) > MAX_FRAME_BYTES - 1024:
        return _error("result_too_large")
    return result


class Gateway:
    def __init__(self, configuration: Configuration):
        self.configuration = configuration
        self._busy = False
        config = configuration.config
        capabilities = set(config.capabilities) if config else set()
        if capabilities:
            capabilities.add("pause")
        self.tools = {tool.name: tool for tool in TOOLS
                      if tool.capability is None or tool.capability in capabilities}

    async def list_tools(self, ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[types.Tool(
            name=tool.name, description=tool.description, input_schema=tool.model.model_json_schema(),
            annotations=types.ToolAnnotations(
                read_only_hint=tool.capability is None,
                destructive_hint=tool.destructive,
                idempotent_hint=tool.idempotent,
                open_world_hint=tool.external,
            ),
            meta={"anthropic/requiresUserInteraction": True} if tool.interaction else None,
        ) for tool in self.tools.values()])

    async def call_tool(self, ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        spec = self.tools.get(params.name)
        if spec is None:
            return _error("tool_disabled" if any(t.name == params.name for t in TOOLS) else "unknown_tool")
        try:
            arguments = spec.model.model_validate({} if params.arguments is None else params.arguments)
        except Exception:
            return _error("invalid_input")
        if self._busy:
            return _error("busy")
        self._busy = True  # No await between checking and claiming the slot.
        try:
            # Cancellation must not release admission or close the SQLite
            # connection while synchronous I/O still runs. Shutdown waits too.
            with anyio.CancelScope(shield=True):
                return await anyio.to_thread.run_sync(self._execute, spec, arguments, abandon_on_cancel=False)
        finally:
            self._busy = False

    def _check_binding(self, store: AgentToolOpsStore) -> None:
        config = self.configuration.config
        assert config is not None
        binding = store.binding()
        if binding is None:
            return  # Unbound local projection remains inspectable.
        if (binding.api_origin != runtime.PRODUCTION_TELEGRAM_ORIGIN
                or (config.source_binding is not None and binding.source_binding != config.source_binding)):
            raise runtime.OpsRuntimeError("binding_mismatch")
        if config.expected_bot_username is not None:
            expected = runtime.credential_reference(config.expected_bot_username, config.keychain_account_name)
            if binding.credential_ref != expected:
                raise runtime.OpsRuntimeError("binding_mismatch")

    def _execute(self, spec: ToolSpec, arguments: StrictModel) -> types.CallToolResult:
        try:
            config = self.configuration.config
            if config is None:
                code = self.configuration.error or "not_configured"
                if spec.name == "ops_status" and code == "not_configured":
                    return _result({"status": "not_configured", "live_ready": False,
                                    "network_calls": 0, "credential_reads": 0})
                return _error(code)
            with AgentToolOpsStore.open_existing(config.db_path, readonly=spec.capability is None) as store:
                self._check_binding(store)
                args = arguments.model_dump()
                if spec.name == "ops_status":
                    payload = runtime.local_status(store)
                    payload["provider_identity_checked"] = False
                    payload["host_approval_verification"] = "not_established_by_server"
                elif spec.name == "ops_replies":
                    args["state"] = None if args["state"] == "all" else args["state"]
                    payload = runtime.reply_page(store, **args)
                elif spec.name == "ops_reply_preview":
                    payload = runtime.preview_reply(store, **args)
                    payload["content_disclosed_to_client_model"] = True
                    payload["digest_is_human_approval"] = False
                elif spec.name in {"ops_poll_once", "ops_reply_send"}:
                    options = {"expected_username": config.expected_bot_username,
                               "source_binding": config.source_binding,
                               "keychain_account_name": config.keychain_account_name}
                    if spec.name == "ops_poll_once":
                        payload = runtime.poll_once(store, timeout=0, **options)
                    else:
                        payload = runtime.send_once(store, **args, **options)
                elif spec.name == "ops_pause":
                    payload = runtime.pause(store)
                else:
                    payload = runtime.reconcile(store, **args)
                    payload["independently_verified"] = False
                return _result(payload)
        except runtime.OpsRuntimeError as exc:
            return _error("busy" if exc.code == "local_lock_busy" else exc.code)
        except BindingStateError:
            return _error("binding_unavailable")
        except DeliveryStateError:
            return _error("delivery_state_conflict")
        except (DatabaseRoleError, sqlite3.Error, OSError):
            return _error("unavailable")
        except Exception:
            return _error("unavailable")


class _CallEnvelope(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")]
    arguments: dict[str, Any] | None = None
    meta: dict[str, Any] | None = Field(default=None, alias="_meta")


async def _private_errors(ctx: Any, call_next: Any) -> Any:
    """Public SDK middleware: suppress raw method/validation/handler diagnostics."""
    try:
        if ctx.method == "tools/call":
            _CallEnvelope.model_validate(ctx.params or {})
        if ctx.method == "tools/list" and (ctx.params or {}).get("cursor") is not None:
            raise ValueError("invalid_input")
        return await call_next(ctx)
    except MCPError as exc:
        code = exc.error.code
        safe = {-32601: "Method not found", -32602: "Invalid request parameters"}
        raise MCPError(code=code if code in safe else -32603,
                       message=safe.get(code, "Request unavailable")) from None
    except (ValidationError, ValueError):
        raise MCPError(code=-32602, message="Invalid request parameters") from None
    except Exception:
        raise MCPError(code=-32603, message="Request unavailable") from None


def create_server(configuration: Configuration) -> Server:
    gateway = Gateway(configuration)
    server = Server("kingdom-telegram-ops", on_list_tools=gateway.list_tools, on_call_tool=gateway.call_tool)
    # No telemetry/logging middleware gets access to private protocol arguments.
    server.middleware[:] = [_private_errors]
    return server


class _BoundedStdin:
    """SDK stdin seam: bounded byte reads, before decoding or allocating a line.

    Oversize/invalid UTF-8 input closes the transport; never drain an unlimited
    line or return part of it as a new request. Ordinary malformed JSON is left
    to the SDK. This iterator reads only its privately owned pipe descriptor.
    """
    def __init__(self, fd: int):
        self.fd = fd
        self.rejected = False

    async def __aiter__(self) -> AsyncIterator[str]:
        pending = bytearray()
        while True:
            newline = pending.find(b"\n")
            if newline >= 0:
                if newline + 1 > MAX_FRAME_BYTES:
                    self.rejected = True
                    return
                frame = bytes(pending[:newline + 1])
                del pending[:newline + 1]
                try:
                    yield frame.decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    self.rejected = True
                    return
                continue
            if len(pending) >= MAX_FRAME_BYTES:
                self.rejected = True
                return
            await anyio.wait_readable(self.fd)
            chunk = os.read(self.fd, min(8192, MAX_FRAME_BYTES - len(pending)))
            if not chunk:
                if pending:
                    try:
                        yield pending.decode("utf-8", errors="strict")
                    except UnicodeDecodeError:
                        self.rejected = True
                return
            pending.extend(chunk)


_PROTOCOL_ERRORS = {
    -32700: "Parse error",
    -32600: "Invalid request",
    -32601: "Method not found",
    -32602: "Invalid request parameters",
    -32603: "Request unavailable",
    -32000: "Connection closed",
    -32001: "Request timed out",
    -32021: "Required client capability unavailable",
    -32022: "Unsupported protocol version",
}


def _check_wire_budget(message: types.JSONRPCMessage) -> None:
    """Bound the SDK envelope *before* its JSON serialization, without dumping it.

    These SDK envelope models have unaliased JSON fields and no custom serializers.
    Results/params are already plain JSON trees. Count conservatively (including
    unset fields and spare separators); stop on size/depth, not after a full copy.
    Unknown values fail closed rather than invoking arbitrary serialization hooks.
    """
    remaining = MAX_FRAME_BYTES - 1  # SDK appends a newline.

    def spend(size: int) -> None:
        nonlocal remaining
        remaining -= size
        if remaining < 0:
            raise ValueError("outbound_frame_rejected")

    def visit(value: Any, depth: int = 0) -> None:
        if depth > MAX_OUTPUT_DEPTH:
            raise ValueError("outbound_frame_rejected")
        if type(value) in (types.JSONRPCResponse, types.JSONRPCError, types.JSONRPCRequest,
                           types.JSONRPCNotification, types.ErrorData):
            visit(vars(value), depth + 1)
        elif isinstance(value, str):
            spend(len(value) + 2)  # Reject huge strings before scanning/encoding.
            for char in value:
                code = ord(char)
                if char in ('"', "\\"):
                    spend(1)
                elif code < 32:
                    spend(5)
                elif code >= 128:
                    spend(1 if code < 2048 else 2 if code < 65536 else 3)
        elif value is None or isinstance(value, bool):
            spend(5)
        elif isinstance(value, int):
            # A decimal digit holds at most four bits. Bound before str(int).
            if value.bit_length() > remaining * 4:
                raise ValueError("outbound_frame_rejected")
            spend(len(str(value)))
        elif isinstance(value, float):
            spend(32)
        elif isinstance(value, dict):
            spend(2)
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("outbound_frame_rejected")
                visit(key, depth + 1)
                spend(2)
                visit(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            spend(2)
            for item in value:
                spend(1)
                visit(item, depth + 1)
        else:
            raise ValueError("outbound_frame_rejected")

    visit(message)


class _PrivateWriteStream:
    """Typed SDK write boundary, including errors raised before middleware.

    Leave era routing, IDs, successful results and serialization to the SDK.
    Error codes/messages are allowlisted; arbitrary error data never reaches it.
    """
    def __init__(self, stream: Any):
        self.stream = stream

    async def send(self, item: SessionMessage) -> None:
        message = item.message
        if isinstance(message, types.JSONRPCError):
            code = message.error.code if message.error.code in _PROTOCOL_ERRORS else -32603
            message = types.JSONRPCError(jsonrpc="2.0", id=message.id,
                error=types.ErrorData(code=code, message=_PROTOCOL_ERRORS[code]))
            item = SessionMessage(message, item.metadata)
        _check_wire_budget(message)
        await self.stream.send(item)

    async def aclose(self) -> None:
        await self.stream.aclose()

    async def __aenter__(self) -> Self:
        await self.stream.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> Any:
        return await self.stream.__aexit__(*args)


class _BoundedStdout:
    """Only the SDK's single writer may use this private, nonblocking pipe.

    No output thread or Python buffering. One total deadline covers all partial
    writes, including repeated EAGAIN/readiness races; progress never resets it.
    A timeout/broken pipe fails the transport, whose task group still waits for
    shielded gateway I/O. A partly written frame cannot be retracted or retried.
    """
    def __init__(self, fd: int):
        if not (stat.S_ISFIFO(os.fstat(fd).st_mode) or stat.S_ISSOCK(os.fstat(fd).st_mode)):
            # O_NONBLOCK cannot bound regular-file/device writes.
            raise ValueError("stdio_pipe_required")
        self.fd = fd
        os.set_blocking(fd, False)

    async def write(self, text: str) -> int:
        with anyio.fail_after(OUTPUT_FRAME_TIMEOUT):
            if len(text) > MAX_FRAME_BYTES:
                raise ValueError("outbound_frame_rejected")
            data = text.encode("utf-8")
            if len(data) > MAX_FRAME_BYTES:
                raise ValueError("outbound_frame_rejected")
            pending = memoryview(data)
            while pending:
                await anyio.lowlevel.checkpoint()
                try:
                    written = os.write(self.fd, pending)
                except BlockingIOError:
                    await anyio.wait_writable(self.fd)
                    continue
                if written <= 0:
                    raise BrokenPipeError("output_closed")
                pending = pending[written:]
        return len(text)

    async def flush(self) -> None:
        pass  # write() already delivered every byte; there is no buffer.


async def _serve(configuration: Configuration, stdin: _BoundedStdin, stdout: _BoundedStdout) -> None:
    server = create_server(configuration)
    async with stdio_server(stdin=stdin, stdout=stdout) as (read, write):
        await server.run(read, _PrivateWriteStream(write), server.create_initialization_options())


def main() -> None:
    """Standalone launcher only. No command-line or environment authority inputs."""
    if len(sys.argv) != 1:
        raise SystemExit(2)
    # Contain SDK malformed-envelope logs, third-party tracebacks, warnings and
    # accidental writes below Python's logging layer, including worker threads.
    logging.disable(sys.maxsize)
    null = os.open(os.devnull, os.O_RDWR)
    wire_in = os.dup(0)
    wire_out = os.dup(1)
    try:
        os.dup2(null, 2)
        os.dup2(null, 0)
        os.dup2(null, 1)
        # Explicit streams bypass SDK fd diversion/restoration. Keep fd1 null
        # even after _serve returns: sys.stdout/sys.__stdout__ may flush buffered
        # handler output at interpreter shutdown. Never restore the wire to fd1.
        stdin = _BoundedStdin(wire_in)
        try:
            anyio.run(_serve, _load_configuration(), stdin, _BoundedStdout(wire_out))
        except BaseException:
            raise SystemExit(1) from None
        if stdin.rejected:
            raise SystemExit(1)
    finally:
        os.close(wire_in)
        os.close(wire_out)
        os.close(null)
