"""Finite synthetic Ops observer exercise; never two real agents or Telegram.

Only disposable local Ops state is written. Scripted MCP records enter through
an explicit fixture reader boundary; the production reader parses them, the
production store projects/commits them, and production private-send validation
consumes an in-memory response. Nothing starts an MCP child or reads a journal,
credential, environment token, model, or participant's private context.
Process and binary attestation are not exercised by this fixture boundary.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import stat
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping, TypeVar

from .agenttool_mcp import (
    MCP_PROTOCOL_VERSION,
    PINNED_SERVER_NAME,
    PINNED_SERVER_VERSION,
    PINNED_TOOL_INVENTORY,
    READ_ONLY_TOOL_ALLOWLIST,
    AgentToolMcpConfig,
    AgentToolMcpReader,
    McpTransport,
    WorkspaceStatus,
)
from .agenttool_ops import (
    AgentToolOpsStore,
    CursorAnchor,
    DeliveryStateError,
    ReplyItem,
    ZERO_HASH,
)
from .ops_service import OpsServiceConfig, TelegramOpsService
from .telegram_api import PRODUCTION_TELEGRAM_ORIGIN, TelegramAPI, TelegramError


SCENARIOS = ("happy", "duplicate", "crash", "refusal", "cancellation", "unknown")
MAX_EVENTS = 8
MAX_COMMANDS = 3
DEADLINE_SECONDS = 10
_FIXTURE_TIME = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
_WORKSPACE = "fixture_workspace"
_EPOCH = "fixture_epoch"
_TASK = "fixture_private_task"
_OPERATOR = 424242
_BOT = 434343
# Not a token obtained from a provider or secret store; only a parser fixture.
_FIXTURE_TOKEN = "fixture-only-no-provider-credential"
_OPAQUE_KEY = hashlib.sha256(b"public synthetic Ops demonstration key").digest()
# Deliberate canaries in fields the projection must withhold, never real secrets.
_PRIVATE_INPUT = "DEMO_PRIVATE_INPUT_MUST_NOT_LEAVE"
_PRIVATE_PATH = "/private/DEMO_PATH_MUST_NOT_LEAVE"
_RESEARCH_SESSION = "DEMO_RESEARCH_SESSION_MUST_NOT_LEAVE"
_REVIEW_SESSION = "DEMO_REVIEW_SESSION_MUST_NOT_LEAVE"
_PUBLIC_EVIDENCE = "https://example.org/synthetic-research/evidence-1"
_T = TypeVar("_T")


class _Budget:
    def __init__(self) -> None:
        self.started = time.monotonic()
        self.events = 0
        self.commands = 0

    def check(self) -> None:
        if time.monotonic() - self.started >= DEADLINE_SECONDS:
            # A local cooperative stop, not an MCP/Telegram transport timeout.
            raise RuntimeError("synthetic Ops demo deadline exceeded")
        if self.events > MAX_EVENTS or self.commands > MAX_COMMANDS:
            raise RuntimeError("synthetic Ops demo budget exceeded")


def _fixture_events(scenario: str) -> list[dict[str, Any]]:
    """Script records, not actions executed by participants or real journal hashes."""
    records: list[dict[str, Any]] = []

    def append(event_kind: str, subject: str, session: str, **payload: Any) -> None:
        sequence = len(records) + 1
        event = {
            "protocol": "agenttool.collab/0.2",
            "workspace_id": _WORKSPACE,
            "epoch_id": _EPOCH,
            "sequence": sequence,
            "id": f"fixture_event_{sequence}",
            "type": event_kind,
            "entity_id": subject,
            "actor": _PRIVATE_INPUT,
            "session_id": session,
            "occurred_at": (_FIXTURE_TIME + timedelta(seconds=sequence)).isoformat(),
            "payload": {"body": _PRIVATE_INPUT, "path": _PRIVATE_PATH, **payload},
            "prev_hash": records[-1]["hash"] if records else ZERO_HASH,
        }
        # Self-consistent fixture coordinates, NOT the pinned Collab hash codec.
        event["hash"] = hashlib.sha256(
            json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        records.append(event)

    append("task.created", _TASK, _RESEARCH_SESSION, version=1)
    append("task.claimed", _TASK, _RESEARCH_SESSION, version=2)
    if scenario == "refusal":
        append("report.posted", "fixture_refusal_report", _RESEARCH_SESSION,
               kind="decision", relation="withdraws", task_id=_TASK)
        append("task.released", _TASK, _RESEARCH_SESSION, version=3)
        return records
    append("artifact.attached", _TASK, _RESEARCH_SESSION, version=3,
           artifact={"task_id": _TASK, "uri": _PUBLIC_EVIDENCE})
    append("report.posted", "fixture_research_report", _RESEARCH_SESSION,
           kind="observation", relation="supports", task_id=_TASK,
           evidence_refs=[_PUBLIC_EVIDENCE])
    append("task.reported_complete", _TASK, _RESEARCH_SESSION, version=4,
           review_status="pending", completion_report_id="fixture_research_report")
    if scenario != "cancellation":
        append("report.posted", "fixture_verifier_review", _REVIEW_SESSION,
               kind="decision", relation="informs", task_id=_TASK,
               reviewed_report_id="fixture_research_report")
        append("task.accepted", _TASK, _REVIEW_SESSION, version=5,
               outcome="accepted", review_id="fixture_verifier_review")
    return records


class _FixtureMcpTransport:
    """Canonical in-memory MCP responses; no tools execute on the other side."""
    def __init__(self, factory: "_FixtureMcpFactory") -> None:
        self.factory = factory
        self.closed = False

    def request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        self.factory.budget.check()
        if self.closed:
            raise RuntimeError("fixture MCP transport already closed")
        if method == "initialize":
            return {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "serverInfo": {"name": PINNED_SERVER_NAME, "version": PINNED_SERVER_VERSION},
                "capabilities": {"tools": {}},
                "instructions": _PRIVATE_INPUT,
            }
        if method == "tools/list":
            return {"tools": [
                {"name": name, "inputSchema": {"type": "object"},
                 "annotations": {"readOnlyHint": name in READ_ONLY_TOOL_ALLOWLIST,
                                 "destructiveHint": False}}
                for name in sorted(PINNED_TOOL_INVENTORY)
            ]}
        if method != "tools/call":
            raise RuntimeError("unexpected fixture MCP method")
        name, arguments = params["name"], params["arguments"]
        if name not in READ_ONLY_TOOL_ALLOWLIST or arguments["workspace_id"] != _WORKSPACE:
            raise RuntimeError("unexpected fixture MCP operation")
        self.factory.tools_called.append(name)
        head = self.factory.anchor(len(self.factory.events))
        if name == "collab_workspace_status":
            payload: dict[str, Any] = {
                "workspace": {"id": _WORKSPACE, "epoch_id": _EPOCH,
                              "root_path": str(self.factory.root),
                              "event_head_sequence": head.sequence,
                              "event_head_hash": head.hash},
                "counts": {"open": int(self.factory.events[-1]["type"] == "task.released"),
                           "claimed": 0, "blocked": 0,
                           "completed": int(self.factory.events[-1]["type"] != "task.released")},
                "pending_reviews": ([{"title": _PRIVATE_INPUT}]
                                    if self.factory.events[-1]["type"] == "task.reported_complete" else []),
                "active_sessions": [],
            }
        elif name == "collab_events_since":
            current = CursorAnchor(**arguments["after_anchor"])
            if current != self.factory.anchor(current.sequence):
                raise RuntimeError("fixture MCP anchor mismatch")
            limit = arguments["limit"]
            selected = self.factory.events[current.sequence:current.sequence + limit]
            terminal = self.factory.anchor(current.sequence + len(selected))
            payload = {
                "cursor": asdict(current), "next_cursor": terminal.sequence,
                "next_anchor": asdict(terminal), "head_sequence": head.sequence,
                "head_hash": head.hash, "has_more": terminal.sequence < head.sequence,
                "chain_valid": True, "verification_scope": "returned_page", "events": selected,
            }
        elif name == "collab_journal_verify":
            payload = {"workspace_id": _WORKSPACE, "chain_valid": True,
                       "verification_scope": "full_journal"}
        else:
            raise RuntimeError("unscripted fixture MCP operation")
        return {"structuredContent": payload,
                "content": [{"type": "text", "text": _PRIVATE_INPUT}]}

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        if method != "notifications/initialized" or params:
            raise RuntimeError("unexpected fixture MCP notification")

    def close(self) -> None:
        self.closed = True


class _FixtureMcpFactory:
    def __init__(self, root: Path, events: list[dict[str, Any]], budget: _Budget) -> None:
        self.root, self.events, self.budget = root, events, budget
        self.transports: list[_FixtureMcpTransport] = []
        self.tools_called: list[str] = []

    def anchor(self, sequence: int) -> CursorAnchor:
        if not 0 <= sequence <= len(self.events):
            raise RuntimeError("fixture MCP sequence outside script")
        return CursorAnchor(_EPOCH, sequence,
                            self.events[sequence - 1]["hash"] if sequence else ZERO_HASH)


class _FixtureMcpReader(AgentToolMcpReader):
    """Fixture-only lifecycle; production protocol/parser checks, no process spec.

    Process and binary attestation are not exercised. This override constructs
    only the exact in-memory transport, never a caller-provided transport factory.
    The production reader and its executable/bundle pins remain unchanged.
    """

    def __init__(self, config: AgentToolMcpConfig, factory: _FixtureMcpFactory) -> None:
        super().__init__(config)
        self._fixture = factory

    def _run_one_shot(
        self, operation: Callable[[McpTransport, WorkspaceStatus], _T]
    ) -> _T:
        self._fixture.budget.check()
        transport = _FixtureMcpTransport(self._fixture)
        self._fixture.transports.append(transport)
        try:
            self._handshake(transport)
            status = self._parse_workspace_status(
                self._call_read_tool(
                    transport, "collab_workspace_status",
                    {"workspace_id": self.config.workspace_id},
                )
            )
            result = operation(transport, status)
            self._fixture.budget.check()
            return result
        finally:
            transport.close()


def _fixture_reader(root: Path, factory: _FixtureMcpFactory) -> _FixtureMcpReader:
    config = AgentToolMcpConfig(
        workspace_id=_WORKSPACE, expected_workspace_root=root, enabled=True,
        bun_path=root / "not-an-executable", bundle_path=root / "not-a-bundle",
        database_path=root / "not-a-collab-journal",
        request_timeout_seconds=0.1, shutdown_timeout_seconds=0.05,
    )
    return _FixtureMcpReader(config, factory)


class _FixturePrivateTransport:
    def __init__(self, budget: _Budget, *, unknown: bool = False) -> None:
        self.budget, self.unknown = budget, unknown
        self.requests: list[dict[str, Any]] = []
        self.validated_receipts = 0

    def __call__(self, request: Any, *, timeout: float) -> io.BytesIO:
        self.budget.check()
        expected_url = f"{PRODUCTION_TELEGRAM_ORIGIN}/bot{_FIXTURE_TOKEN}/sendMessage"
        if request.full_url != expected_url or request.get_method() != "POST":
            raise RuntimeError("unexpected fixture private request")
        payload = json.loads(request.data)
        if (payload.get("chat_id") != _OPERATOR
                or payload.get("protect_content") is not True
                or payload.get("link_preview_options") != {"is_disabled": True}
                or set(payload) != {"chat_id", "text", "protect_content", "link_preview_options"}):
            raise RuntimeError("fixture private request violated binding")
        self.requests.append(payload)
        if self.unknown:
            raise TimeoutError(_PRIVATE_INPUT)
        return io.BytesIO(json.dumps({
            "ok": True, "result": {"message_id": len(self.requests),
                                    "chat": {"id": _OPERATOR, "type": "private"}},
        }).encode("utf-8"))


def _command(text: str, *, update_id: int = 100) -> dict[str, Any]:
    return {"update_id": update_id, "message": {
        "date": int((_FIXTURE_TIME + timedelta(minutes=1)).timestamp()),
        "from": {"id": _OPERATOR, "is_bot": False, "first_name": _PRIVATE_INPUT},
        "chat": {"id": _OPERATOR, "type": "private", "username": _PRIVATE_INPUT},
        "text": text,
    }}


def _process(store: AgentToolOpsStore, service: TelegramOpsService,
             update: Mapping[str, Any], budget: _Budget) -> Any:
    budget.commands += 1
    budget.check()
    state = store.poll_state()
    if state is None:
        raise RuntimeError("fixture binding was not initialized")
    result = store.process_update_once(update, service, polling_epoch=state.epoch,
                                       processed_at=_FIXTURE_TIME + timedelta(minutes=2))
    budget.check()
    return result


def _require_blocked(operation: Any) -> bool:
    try:
        operation()
    except DeliveryStateError:
        return True
    raise RuntimeError("synthetic Ops stop/no-resend boundary did not hold")


def _claim(store: AgentToolOpsStore, item: ReplyItem) -> ReplyItem:
    return store.claim_reply(item.reply_id, payload_digest=item.payload_digest,
                             binding_revision=item.binding_revision)


def _rollback_command(store: AgentToolOpsStore, service: TelegramOpsService,
                      update: Mapping[str, Any], budget: _Budget) -> dict[str, Any]:
    before = store.poll_state()
    injected = False

    def deny_reply_insert(action: int, table: str, _column: str,
                          _database: str, _trigger: str) -> int:
        nonlocal injected
        if action == sqlite3.SQLITE_INSERT and table == "ops_replies":
            injected = True
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    store.conn.set_authorizer(deny_reply_insert)
    try:
        try:
            _process(store, service, update, budget)
        except sqlite3.DatabaseError:
            if not injected:
                raise
        else:
            raise RuntimeError("fixture rollback injection was not reached")
    finally:
        store.conn.set_authorizer(None)
    rows = store.conn.execute("SELECT COUNT(*) FROM ops_update_dispositions").fetchone()[0]
    rolled_back = (rows == 0 and not store.list_replies() and store.poll_state() == before
                   and not store.conn.in_transaction)
    if not rolled_back:
        raise RuntimeError("atomic command rollback did not preserve state")
    return {"injection": "deny_reply_insert_after_disposition", "rolled_back": True,
            "dispositions_after_rollback": rows, "offset_unchanged": True}


def _owner_only(root: Path) -> bool:
    return all(
        item.stat().st_uid == os.geteuid() and not stat.S_IMODE(item.stat().st_mode) & 0o077
        for item in (root, *root.rglob("*"))
    )


def run_demo(scenario: str = "happy") -> dict[str, Any]:
    """Run one fixed scenario in fresh disposable state and return safe receipts.

    No live mode, state path, credential, transport, actor or arbitrary command
    can be supplied by callers. The ten-second deadline is checked between
    bounded synchronous fixture operations; no background worker or sleep runs.
    """
    if not isinstance(scenario, str) or scenario not in SCENARIOS:
        raise ValueError("scenario must be happy, duplicate, crash, refusal, cancellation or unknown")
    budget = _Budget()
    events = _fixture_events(scenario)
    if len(events) > MAX_EVENTS:
        raise RuntimeError("synthetic event budget exceeded")
    with TemporaryDirectory(prefix="telegram-ops-synthetic-") as directory:
        root = Path(directory).resolve()
        root.chmod(0o700)
        factory = _FixtureMcpFactory(root, events, budget)
        reader = _fixture_reader(root, factory)
        transport = _FixturePrivateTransport(budget, unknown=scenario == "unknown")
        api = TelegramAPI(_FIXTURE_TOKEN, request_opener=transport,
                          require_production_origin=True)
        with AgentToolOpsStore(root / "ops.sqlite3", workspace_alias="synthetic_ops",
                              opaque_key=_OPAQUE_KEY) as store:
            binding = store.bind_operator(
                _BOT, PRODUCTION_TELEGRAM_ORIGIN, operator_user_id=_OPERATOR,
                operator_private_chat_id=_OPERATOR, credential_ref="fixture:ops-demo",
                source_binding="fixture:synthetic-observer", verification="fixture",
                bound_at=_FIXTURE_TIME - timedelta(minutes=1),
            )
            live_blocked = _require_blocked(lambda: store.require_ready(
                bot_id=_BOT, operator_user_id=_OPERATOR, operator_private_chat_id=_OPERATOR,
                api_origin=PRODUCTION_TELEGRAM_ORIGIN, credential_ref=binding.credential_ref,
                source_binding=binding.source_binding, live=True,
            ))
            transitions: list[dict[str, Any]] = []
            anchor = CursorAnchor.genesis(_EPOCH)
            page = None
            for _ in range(len(events)):
                budget.check()
                page = reader.events_since(anchor, limit=1)
                budget.events += len(page.events)
                budget.check()
                stage = store.stage_page(current_anchor=page.current_anchor,
                                         next_anchor=page.next_anchor,
                                         events=page.projection_events())
                store.commit_staged_cursor(stage.anchor)
                task = store.list_tasks(limit=1)[0]
                projected = store.recent_projections(limit=1)[0]
                transitions.append({"sequence": projected.sequence,
                                    "event_kind": projected.event_kind,
                                    "event_ref": projected.event_key,
                                    "task_state": task.state, "review_state": task.review_state})
                anchor = page.next_anchor
            if page is None or page.has_more or budget.events != len(events):
                raise RuntimeError("fixture event page did not reach its exact terminal anchor")
            replay: dict[str, Any] = {}
            if scenario == "duplicate":
                replayed = store.stage_page(current_anchor=page.current_anchor,
                                            next_anchor=page.next_anchor,
                                            events=page.projection_events())
                if not replayed.duplicate or replayed.enqueued_count:
                    raise RuntimeError("fixture page replay was not deduplicated")
                replay["event_page_duplicate"] = True
                replay["additional_event_rows"] = replayed.enqueued_count
            verification = reader.verify_journal()
            # The fixture supplies true to exercise the parser. Do NOT store it
            # as a completed full-journal audit or mislabel /journal_verify.
            journal = store.journal_verify()
            service = TelegramOpsService(store, store, OpsServiceConfig(_OPERATOR, _OPERATOR))
            update = _command("/spawn " + _PRIVATE_INPUT if scenario == "refusal" else "/agent_tasks")
            rollback = _rollback_command(store, service, update, budget) if scenario == "crash" else None
            disposition = _process(store, service, update, budget)
            if disposition.reply_id is None:
                raise RuntimeError("fixture command did not persist a reply")
            item = store.reply_item(disposition.reply_id)
            if item is None:
                raise RuntimeError("fixture reply missing after atomic commit")
            if scenario in {"duplicate", "crash"}:
                duplicate = _process(store, service, update, budget)
                if not duplicate.duplicate or duplicate.reply_id != item.reply_id:
                    raise RuntimeError("fixture update replay was not deduplicated")
                replay["update_duplicate"] = True
                replay["same_reply_id"] = True
            stop: dict[str, Any] = {}
            if scenario in {"refusal", "cancellation"}:
                store.pause(paused_at=_FIXTURE_TIME + timedelta(minutes=3))
                stop["paused_poll_blocked"] = _require_blocked(store.prepare_poll)
                stop["paused_command_blocked"] = _require_blocked(
                    lambda: _process(store, service, _command("/agent_status", update_id=101), budget))
                stop["paused_send_blocked"] = _require_blocked(lambda: _claim(store, item))
                resumed = store.resume(resumed_at=_FIXTURE_TIME + timedelta(minutes=4))
                stop["resume_revision"] = resumed.revision
                stop["old_reply_blocked_after_resume"] = _require_blocked(lambda: _claim(store, item))
                # Leave the fixture locally withdrawn, not silently running again.
                store.pause(paused_at=_FIXTURE_TIME + timedelta(minutes=5))
                stop["scope"] = "local_gateway_only_not_agent_process_stop"
            else:
                budget.check()
                claimed = _claim(store, item)
                try:
                    receipt = api.send_private_text(claimed.chat_id, claimed.text)
                except TelegramError as exc:
                    if scenario != "unknown" or not exc.ambiguous:
                        raise
                    store.finish_reply(item.reply_id, attempt_count=claimed.attempt_count,
                                       state="unknown", error_code="telegram_timeout")
                else:
                    transport.validated_receipts += 1
                    store.finish_reply(item.reply_id, attempt_count=claimed.attempt_count,
                                       state="sent", receipt_ref=f"fixture:message:{receipt['message_id']}")
                budget.check()
                stop["terminal_reply_resend_blocked"] = _require_blocked(lambda: _claim(store, item))
                if scenario == "unknown":
                    store.reconcile_reply(item.reply_id, attempt_count=claimed.attempt_count,
                                          outcome="unknown", reconciliation_ref="fixture:inconclusive-observation")
                    stop["reconciliation_resend_blocked"] = _require_blocked(lambda: _claim(store, item))
            budget.check()
            final = store.reply_item(item.reply_id)
            task = store.list_tasks(limit=1)[0]
            if final is None:
                raise RuntimeError("fixture terminal receipt disappeared")
            owner_only = _owner_only(root)
            if not owner_only:
                raise PermissionError("synthetic state is not owner-only")
            result = {
                "scenario": scenario,
                "label": "synthetic workflow: no model agents, real journal verification or Telegram delivery",
                "synthetic": True, "no_real_agents": True, "no_telegram_delivery": True,
                "exercise": "fixture-backed read-only observer, not two-agent execution",
                "counts": {"events": budget.events, "command_attempts": budget.commands,
                           "replies": len(store.list_replies()), "delivery_attempts": len(transport.requests),
                           "validated_fixture_receipts": transport.validated_receipts,
                           "telegram_deliveries": 0, "event_alert_deliveries": 0},
                "bounds": {"max_events": MAX_EVENTS, "max_commands": MAX_COMMANDS,
                           "deadline_seconds": DEADLINE_SECONDS, "deadline_scope": "cooperative_fixture_steps"},
                "researcher_report": {
                    "kind": "synthetic_bounded_report", "outcome": scenario if scenario in {"refusal", "cancellation"} else "reported",
                    "summary": "A scripted public-example observation; no external research was performed.",
                    "evidence_refs": [] if scenario == "refusal" else [_PUBLIC_EVIDENCE],
                    "evidence_fetched": False,
                    "review": "distinct scripted review record" if task.review_state == "accepted" else "not accepted",
                    "independent_agent_review_observed": False,
                },
                "receipts": {
                    "transitions": transitions,
                    "cursor": {"committed_sequence": store.committed_anchor().sequence,
                               "staged": store.staged_anchor() is not None},
                    "reply": {"reply_id": final.reply_id, "state": final.state,
                              "payload_digest": final.payload_digest, "attempt_count": final.attempt_count,
                              "receipt_ref": final.receipt_ref, "error_code": final.error_code,
                              "binding_revision": final.binding_revision},
                    "attempts": list(store.reply_attempts(final.reply_id)),
                    "reconciliations": list(store.reply_reconciliations(final.reply_id)),
                    "projection": {"task_state": task.state, "review_state": task.review_state,
                                   "evidence_reference_count": task.evidence_reference_count},
                    "mcp": {"transport": "in_memory_fixture",
                            "process_attestation": "not_exercised",
                            "binary_attestation": "not_exercised",
                            "all_transports_closed": all(child.closed for child in factory.transports)},
                    "journal": {"fixture_attestation_chain_valid": verification.chain_valid,
                                "fixture_attestation_scope": verification.verification_scope,
                                "actual_full_journal_verification": "not_performed",
                                "stored_verification_outcome": journal.outcome},
                    "replay": replay, "rollback": rollback, "stop": stop,
                    "fixture_binding_rejected_for_live": live_blocked,
                    "local_transport_state": store.poll_state().state,
                },
                "non_effects": {"network_calls": 0, "subprocesses": 0, "credential_reads": 0,
                                "keychain_operations": 0, "real_journal_reads": 0,
                                "shared_journal_writes": 0, "model_calls": 0, "agent_dispatches": 0,
                                "payments": 0, "trades": 0, "deployments": 0},
                "state": {"temporary": True, "owner_only": owner_only,
                          "retained_paths": [], "cleanup_complete": False},
            }
            if not all(child.closed for child in factory.transports):
                raise RuntimeError("fixture reader left a transport open")
            serialized = json.dumps(result, sort_keys=True)
            persisted = "\n".join(store.conn.iterdump())
            sent = json.dumps(transport.requests)
            for sentinel in (_PRIVATE_INPUT, _PRIVATE_PATH, _RESEARCH_SESSION,
                             _REVIEW_SESSION, _TASK, _FIXTURE_TOKEN, str(root)):
                if any(sentinel in text for text in (serialized, persisted, sent)):
                    raise RuntimeError("synthetic privacy canary escaped the projection")
    result["state"]["cleanup_complete"] = not root.exists()
    if not result["state"]["cleanup_complete"]:
        raise RuntimeError("synthetic state cleanup did not complete")
    budget.check()
    result["bounds"]["elapsed_seconds"] = round(time.monotonic() - budget.started, 6)
    return result
