from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pytest

import telegram_gateway.agenttool_mcp as mcp
import telegram_gateway.bootstrap as bootstrap
import telegram_gateway.ops_demo as demo
import telegram_gateway.telegram_api as telegram_api
from telegram_gateway.agenttool_ops import AgentToolOpsStore
from telegram_gateway.ops_service import TelegramOpsService


@pytest.fixture(autouse=True)
def isolated_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Every demo test fails before any process, network, secret or real DB use."""
    observed: dict[str, Any] = {"roots": [], "databases": [], "denied": []}
    original_temporary = tempfile.TemporaryDirectory
    original_connect = sqlite3.connect

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        observed["denied"].append(True)
        raise AssertionError("demo attempted a forbidden external effect")

    def temporary(*args: Any, **kwargs: Any) -> Any:
        result = original_temporary(*args, dir=tmp_path, **kwargs)
        observed["roots"].append(Path(result.name).resolve())
        return result

    def connect(database: Any, *args: Any, **kwargs: Any) -> Any:
        text = str(database)
        path = Path(urllib.parse.unquote(urllib.parse.urlsplit(text).path)
                    if text.startswith("file:") else text).resolve()
        assert any(path.is_relative_to(root) for root in observed["roots"])
        observed["databases"].append(path)
        return original_connect(database, *args, **kwargs)

    monkeypatch.setattr(demo, "TemporaryDirectory", temporary)
    monkeypatch.setattr(sqlite3, "connect", connect)
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(os, "popen", forbidden)
    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(urllib.request, "build_opener", forbidden)
    monkeypatch.setattr(telegram_api, "open_request", forbidden)
    monkeypatch.setattr(time, "sleep", forbidden)
    for name in ("load_keychain_token", "resolve_token", "store_token_interactively"):
        monkeypatch.setattr(bootstrap, name, forbidden)
    monkeypatch.setattr(mcp, "StdioMcpTransport", forbidden)
    # Neither process-spec construction nor any executable/journal attestation
    # belongs to this in-memory demo, even when a local installation exists.
    for name in ("build_process_spec", "_validate_runtime", "_validate_database", "_bundle_sha256"):
        monkeypatch.setattr(mcp, name, forbidden)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "DEMO_ENV_TOKEN_MUST_NOT_LEAVE")
    monkeypatch.setenv("AGENTOOL_COLLAB_DB", str(tmp_path / "DO_NOT_OPEN_SHARED_DB"))
    yield observed
    assert observed["denied"] == []
    assert all(not root.exists() for root in observed["roots"])


@pytest.mark.parametrize(
    "scenario,events,commands,sends,state,task_state,review_state",
    [
        ("happy", 7, 1, 1, "sent", "completed", "accepted"),
        ("duplicate", 7, 2, 1, "sent", "completed", "accepted"),
        ("crash", 7, 3, 1, "sent", "completed", "accepted"),
        ("refusal", 4, 2, 0, "invalidated", "open", "unknown"),
        ("cancellation", 5, 2, 0, "invalidated", "reported_complete", "pending"),
        ("unknown", 7, 1, 1, "unknown", "completed", "accepted"),
    ],
)
def test_scenarios_have_truthful_bounded_observed_receipts(
    isolated_effects: dict[str, Any], scenario: str, events: int, commands: int,
    sends: int, state: str, task_state: str, review_state: str,
) -> None:
    result = demo.run_demo(scenario)
    assert result["scenario"] == scenario
    assert result["synthetic"] is result["no_real_agents"] is result["no_telegram_delivery"] is True
    assert result["label"] == "synthetic workflow: no model agents, real journal verification or Telegram delivery"
    assert "not two-agent execution" in result["exercise"]
    assert result["counts"]["events"] == events <= 8
    assert result["counts"]["command_attempts"] == commands <= 3
    assert result["counts"]["delivery_attempts"] == sends
    assert result["counts"]["replies"] == 1
    assert result["counts"]["telegram_deliveries"] == 0
    assert result["counts"]["event_alert_deliveries"] == 0
    assert result["bounds"]["deadline_seconds"] == 10
    assert 0 <= result["bounds"]["elapsed_seconds"] < 10
    assert result["receipts"]["reply"]["state"] == state
    assert result["receipts"]["reply"]["attempt_count"] == sends
    assert result["receipts"]["projection"]["task_state"] == task_state
    assert result["receipts"]["projection"]["review_state"] == review_state
    assert result["receipts"]["cursor"] == {"committed_sequence": events, "staged": False}
    assert result["receipts"]["fixture_binding_rejected_for_live"] is True
    assert result["receipts"]["mcp"] == {
        "transport": "in_memory_fixture",
        "process_attestation": "not_exercised",
        "binary_attestation": "not_exercised",
        "all_transports_closed": True,
    }
    assert result["state"] == {"temporary": True, "owner_only": True,
                                "cleanup_complete": True, "retained_paths": []}
    assert len(isolated_effects["roots"]) == 1
    assert isolated_effects["databases"]
    assert all(count == 0 for count in result["non_effects"].values())
    assert len(json.dumps(result)) < 12_000


def test_claim_report_review_and_acceptance_are_distinct_records() -> None:
    scripted = demo._fixture_events("happy")
    claimed = next(event for event in scripted if event["type"] == "task.claimed")
    reported = next(event for event in scripted if event["type"] == "task.reported_complete")
    accepted = next(event for event in scripted if event["type"] == "task.accepted")
    reports = [event for event in scripted if event["type"] == "report.posted"]
    assert len(reports) == 2
    report, review = reports
    assert len({claimed["id"], reported["id"], accepted["id"], report["id"], review["id"]}) == 5
    assert report["entity_id"] != review["entity_id"]
    assert claimed["session_id"] == report["session_id"] == reported["session_id"]
    assert review["session_id"] == accepted["session_id"] != reported["session_id"]
    assert reported["sequence"] < review["sequence"] < accepted["sequence"]
    assert review["payload"]["reviewed_report_id"] == report["entity_id"]
    assert accepted["payload"]["review_id"] == review["entity_id"]
    result = demo.run_demo()
    transitions = result["receipts"]["transitions"]
    assert transitions[1]["task_state"] == "claimed"
    assert transitions[4]["task_state"] == transitions[5]["task_state"] == "reported_complete"
    assert transitions[4]["review_state"] == transitions[5]["review_state"] == "pending"
    assert transitions[6]["review_state"] == "accepted"
    assert result["researcher_report"]["independent_agent_review_observed"] is False


def test_fixture_attestation_is_not_stored_as_actual_integrity_proof() -> None:
    result = demo.run_demo()
    journal = result["receipts"]["journal"]
    assert journal == {
        "fixture_attestation_chain_valid": True,
        "fixture_attestation_scope": "full_journal",
        "actual_full_journal_verification": "not_performed",
        "stored_verification_outcome": "unavailable",
    }
    report = result["researcher_report"]
    assert report["evidence_fetched"] is False
    assert report["evidence_refs"] == ["https://example.org/synthetic-research/evidence-1"]
    assert len(report["summary"]) < 320


def test_fixture_reader_reuses_production_checks_and_closes_every_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("_handshake", "_call_read_tool", "_parse_workspace_status",
                 "events_since", "_one_shot", "_parse_event_page",
                 "verify_journal", "_parse_journal_verification"):
        assert getattr(demo._FixtureMcpReader, name) is getattr(mcp.AgentToolMcpReader, name)
    assert demo._FixtureMcpReader._run_one_shot is not mcp.AgentToolMcpReader._run_one_shot
    transports: list[demo._FixtureMcpTransport] = []
    original = demo._FixtureMcpTransport.__init__

    def initialize(self: demo._FixtureMcpTransport, factory: demo._FixtureMcpFactory) -> None:
        original(self, factory)
        transports.append(self)

    monkeypatch.setattr(demo._FixtureMcpTransport, "__init__", initialize)
    demo.run_demo()
    assert len(transports) == 8  # Seven event pages, then the fixture verification.
    assert all(type(child) is demo._FixtureMcpTransport and child.closed for child in transports)
    assert transports[0].factory.tools_called == [
        "collab_workspace_status", "collab_events_since",
    ] * 7 + ["collab_workspace_status", "collab_journal_verify", "collab_workspace_status"]


@pytest.mark.parametrize(
    "failure,code",
    [
        ("protocol", "protocol_mismatch"),
        ("inventory", "tool_inventory_mismatch"),
        ("workspace", "workspace_mismatch"),
        ("event_chain", "journal_chain_invalid"),
        ("journal_scope", "invalid_response"),
    ],
)
def test_fixture_reader_keeps_production_rejections_and_closes_on_error(
    monkeypatch: pytest.MonkeyPatch, isolated_effects: dict[str, Any],
    failure: str, code: str,
) -> None:
    original = demo._FixtureMcpTransport.request
    transports: list[demo._FixtureMcpTransport] = []

    def malformed(self: demo._FixtureMcpTransport, method: str, params: Any) -> Any:
        if self not in transports:
            transports.append(self)
        response = original(self, method, params)
        if failure == "protocol" and method == "initialize":
            response["protocolVersion"] = "not-the-pinned-protocol"
        elif failure == "inventory" and method == "tools/list":
            response["tools"] = []
        elif method == "tools/call":
            payload = response["structuredContent"]
            if failure == "workspace" and params["name"] == "collab_workspace_status":
                payload["workspace"]["root_path"] = str(self.factory.root.parent)
            elif failure == "event_chain" and params["name"] == "collab_events_since":
                payload["events"][0]["prev_hash"] = "f" * 64
            elif failure == "journal_scope" and params["name"] == "collab_journal_verify":
                payload["verification_scope"] = "returned_page"
        return response

    monkeypatch.setattr(demo._FixtureMcpTransport, "request", malformed)
    with pytest.raises(mcp.AgentToolMcpError) as caught:
        demo.run_demo()
    assert caught.value.code == code
    assert transports and all(child.closed for child in transports)
    assert all(not root.exists() for root in isolated_effects["roots"])


def test_deadline_after_operation_still_closes_the_fixture_transport(
    monkeypatch: pytest.MonkeyPatch, isolated_effects: dict[str, Any],
) -> None:
    clock = 0.0
    transports: list[demo._FixtureMcpTransport] = []
    original = demo._FixtureMcpTransport.request

    def expire(self: demo._FixtureMcpTransport, method: str, params: Any) -> Any:
        nonlocal clock
        if self not in transports:
            transports.append(self)
        response = original(self, method, params)
        if method == "tools/call" and params["name"] == "collab_events_since":
            clock = 11.0
        return response

    monkeypatch.setattr(demo.time, "monotonic", lambda: clock)
    monkeypatch.setattr(demo._FixtureMcpTransport, "request", expire)
    with pytest.raises(RuntimeError, match="deadline exceeded"):
        demo.run_demo()
    assert len(transports) == 1 and transports[0].closed
    assert all(not root.exists() for root in isolated_effects["roots"])


def test_duplicate_reuses_persisted_reply_without_render_or_send_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = TelegramOpsService.render_update
    rendered: list[int] = []

    def render(self: TelegramOpsService, update: Any) -> Any:
        rendered.append(update["update_id"])
        return original(self, update)

    monkeypatch.setattr(TelegramOpsService, "render_update", render)
    result = demo.run_demo("duplicate")
    assert rendered == [100]
    assert result["receipts"]["replay"] == {
        "event_page_duplicate": True, "additional_event_rows": 0,
        "update_duplicate": True, "same_reply_id": True,
    }
    assert result["counts"]["validated_fixture_receipts"] == 1
    assert len(result["receipts"]["attempts"]) == 1


def test_crash_injects_after_disposition_then_rolls_back_and_recovers() -> None:
    result = demo.run_demo("crash")
    assert result["receipts"]["rollback"] == {
        "injection": "deny_reply_insert_after_disposition", "rolled_back": True,
        "dispositions_after_rollback": 0, "offset_unchanged": True,
    }
    assert result["receipts"]["replay"]["same_reply_id"] is True
    assert result["receipts"]["reply"]["state"] == "sent"
    assert result["counts"]["delivery_attempts"] == 1


@pytest.mark.parametrize("scenario", ["refusal", "cancellation"])
def test_withdrawal_uses_real_pause_and_no_old_reply_after_resume(scenario: str) -> None:
    result = demo.run_demo(scenario)
    stop = result["receipts"]["stop"]
    for field in ("paused_poll_blocked", "paused_command_blocked", "paused_send_blocked",
                  "old_reply_blocked_after_resume"):
        assert stop[field] is True
    assert stop["resume_revision"] == 2
    assert stop["scope"] == "local_gateway_only_not_agent_process_stop"
    assert result["receipts"]["local_transport_state"] == "paused"
    assert result["receipts"]["attempts"] == []
    assert result["researcher_report"]["review"] == "not accepted"
    assert not any(row["event_kind"] == "task.accepted" for row in result["receipts"]["transitions"])


def test_unknown_keeps_attempt_evidence_and_reconciliation_cannot_resend() -> None:
    result = demo.run_demo("unknown")
    assert result["counts"]["delivery_attempts"] == 1
    assert result["counts"]["validated_fixture_receipts"] == 0
    reply = result["receipts"]["reply"]
    assert reply["state"] == "unknown" and reply["receipt_ref"] is None
    assert reply["error_code"] == "telegram_timeout"
    attempts = result["receipts"]["attempts"]
    assert len(attempts) == 1 and attempts[0]["state"] == "unknown"
    reconciliations = result["receipts"]["reconciliations"]
    assert len(reconciliations) == 1
    assert reconciliations[0]["outcome"] == "unknown"
    assert reconciliations[0]["reconciliation_ref"] == "fixture:inconclusive-observation"
    assert result["receipts"]["stop"]["terminal_reply_resend_blocked"] is True
    assert result["receipts"]["stop"]["reconciliation_resend_blocked"] is True


@pytest.mark.parametrize("scenario", demo.SCENARIOS)
def test_projection_storage_transport_and_output_withhold_private_canaries(
    monkeypatch: pytest.MonkeyPatch, scenario: str,
) -> None:
    dumps: list[str] = []
    requests: list[str] = []
    original_close = AgentToolOpsStore.close
    original_open = demo._FixturePrivateTransport.__call__

    def close(self: AgentToolOpsStore) -> None:
        dumps.append("\n".join(self.conn.iterdump()))
        original_close(self)

    def opener(self: Any, request: Any, **kwargs: Any) -> Any:
        requests.append(request.data.decode("utf-8"))
        return original_open(self, request, **kwargs)

    monkeypatch.setattr(AgentToolOpsStore, "close", close)
    monkeypatch.setattr(demo._FixturePrivateTransport, "__call__", opener)
    result = demo.run_demo(scenario)
    all_text = json.dumps(result) + "\n".join(dumps + requests)
    for sentinel in (demo._PRIVATE_INPUT, demo._PRIVATE_PATH, demo._RESEARCH_SESSION,
                     demo._REVIEW_SESSION, demo._TASK, demo._FIXTURE_TOKEN,
                     "DEMO_ENV_TOKEN_MUST_NOT_LEAVE", "DO_NOT_OPEN_SHARED_DB"):
        assert sentinel not in all_text
    assert dumps
    for encoded in requests:
        payload = json.loads(encoded)
        assert payload["chat_id"] == demo._OPERATOR
        assert payload["protect_content"] is True
        assert payload["link_preview_options"] == {"is_disabled": True}
        assert len(payload["text"]) <= 3800
        assert "Unsupported" not in payload["text"]


def test_error_cleans_temporary_state_without_hiding_failure(
    monkeypatch: pytest.MonkeyPatch, isolated_effects: dict[str, Any],
) -> None:
    def broken(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("deliberately broken fixture")

    monkeypatch.setattr(mcp.AgentToolMcpReader, "events_since", broken)
    with pytest.raises(RuntimeError, match="deliberately broken fixture"):
        demo.run_demo()
    assert isolated_effects["roots"]
    assert all(not root.exists() for root in isolated_effects["roots"])


def test_deadline_failure_is_finite_and_cleans_temp_state(
    monkeypatch: pytest.MonkeyPatch, isolated_effects: dict[str, Any],
) -> None:
    clock = iter([0.0, 0.0, 11.0])
    monkeypatch.setattr(demo.time, "monotonic", lambda: next(clock, 11.0))
    with pytest.raises(RuntimeError, match="deadline exceeded"):
        demo.run_demo()
    assert all(not root.exists() for root in isolated_effects["roots"])


@pytest.mark.parametrize("scenario", ["live", "happy/../../state", "", None, True, []])
def test_unknown_scenario_rejected_before_state_creation(
    scenario: Any, isolated_effects: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="scenario must be"):
        demo.run_demo(scenario)
    assert isolated_effects["roots"] == []


def test_two_runs_have_distinct_temporary_stores_and_no_retained_state(
    isolated_effects: dict[str, Any],
) -> None:
    first, second = demo.run_demo(), demo.run_demo()
    assert first["receipts"]["reply"]["reply_id"] != second["receipts"]["reply"]["reply_id"]
    assert len(set(isolated_effects["roots"])) == 2
    assert first["counts"] == second["counts"]
