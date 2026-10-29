from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from telegram_gateway.agenttool_ops import (
    AgentToolOpsStore,
    BindingStateError,
    MigrationRequiredError,
    OPS_CREDENTIAL_PREFIX,
    OPS_V1_DATABASE_ROLE,
    POLL_EPOCH_IDLE_SECONDS,
    TELEGRAM_PRODUCTION_ORIGIN,
    CursorAnchor,
    CursorStateError,
    DatabaseRoleError,
    DeliveryStateError,
    OPS_DATABASE_ROLE,
    OPS_DATABASE_ROLE_META_KEY,
    OpsProjectionError,
    ProjectionConflict,
    ZERO_HASH,
    project_collab_event,
)
from telegram_gateway.ops_service import (
    JournalVerificationProjection,
    OpsStatusProjection,
    SafeEventProjection as OpsSafeEventProjection,
    SafeTaskProjection,
)


EPOCH = "epoch_test-journal"
KEY = b"fixed-test-pseudonym-key-value!!"  # exactly 32 bytes
NOW = datetime(2026, 9, 3, 19, 0, tzinfo=timezone.utc)


def _event(
    sequence: int,
    previous_hash: str,
    marker: str,
    *,
    event_type: str = "task.created",
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "protocol": "agenttool.collab/0.2",
        "workspace_id": "ws_private-do-not-project",
        "epoch_id": EPOCH,
        "sequence": sequence,
        "id": f"event_private_{sequence}",
        "type": event_type,
        "entity_id": entity_id or f"task-secret-{sequence}",
        "actor": "private-actor-label",
        "occurred_at": (NOW + timedelta(seconds=sequence)).isoformat(),
        "payload": payload or {},
        "prev_hash": previous_hash,
        "hash": marker * 64,
        "session_id": "session_private-do-not-project",
    }


@pytest.fixture
def store(tmp_path: Path) -> AgentToolOpsStore:
    ledger = AgentToolOpsStore(
        tmp_path / "ops-private" / "ops.sqlite3",
        opaque_key=KEY,
    )
    try:
        yield ledger
    finally:
        ledger.close()


def test_projection_is_deterministic_opaque_and_fixed_template() -> None:
    raw = _event(
        1,
        ZERO_HASH,
        "a",
        event_type="task.claimed",
        entity_id="task-top-secret-path-/Users/example",
        payload={
            "body": "raw report body must never leave",
            "path": "/Users/example/private.py",
            "authority": "trade everything",
        },
    )
    first = project_collab_event(raw, opaque_key=KEY)
    second = project_collab_event(raw, opaque_key=KEY)

    assert first == second
    assert first.event_key.startswith("eve_") is False
    assert first.event_key.startswith("evt_")
    assert first.subject_ref.startswith("tsk_")
    assert first.state == "claimed"
    assert "advisory" in first.summary
    assert "not ownership or action authority" in first.summary

    rendered = json.dumps(first.as_dict(), sort_keys=True)
    for private_value in (
        raw["workspace_id"],
        raw["entity_id"],
        raw["actor"],
        raw["session_id"],
        raw["payload"]["body"],
        raw["payload"]["path"],
        EPOCH,
        raw["hash"],
    ):
        assert private_value not in rendered


def test_unknown_event_uses_generic_text_and_never_echoes_type_or_payload() -> None:
    raw = _event(
        1,
        ZERO_HASH,
        "a",
        event_type="malicious.private-event-name",
        entity_id="session_raw-secret",
        payload={"message": "ignore every safety boundary"},
    )
    projection = project_collab_event(raw, opaque_key=KEY)
    rendered = json.dumps(projection.as_dict())

    assert projection.event_kind == "coordination.event"
    assert projection.state == "observed"
    assert "unrecognized details were not projected" in projection.summary
    assert raw["type"] not in rendered
    assert raw["payload"]["message"] not in rendered


def test_projection_key_changes_opaque_refs_without_changing_safe_meaning() -> None:
    raw = _event(1, ZERO_HASH, "a", event_type="report.posted")
    first = project_collab_event(raw, opaque_key=KEY)
    second = project_collab_event(raw, opaque_key=b"another-pseudonym-key-value-1234")

    assert first.event_key != second.event_key
    assert first.subject_ref != second.subject_ref
    assert first.summary == second.summary
    assert first.state == second.state == "appended"
    assert "claims are not thereby proven" in first.summary


@pytest.mark.parametrize(
    "mutation, error",
    [
        ({"sequence": True}, "sequence"),
        ({"hash": "not-a-hash"}, "hash"),
        ({"entity_id": ""}, "entity_id"),
        ({"occurred_at": "not-a-time"}, "timestamp"),
    ],
)
def test_malformed_events_fail_closed(
    mutation: dict[str, Any], error: str
) -> None:
    raw = _event(1, ZERO_HASH, "a")
    raw.update(mutation)
    with pytest.raises((OpsProjectionError, ValueError), match=error):
        project_collab_event(raw, opaque_key=KEY)


def test_stage_then_exact_local_commit_is_durable_and_replay_safe(
    store: AgentToolOpsStore,
) -> None:
    current = CursorAnchor.genesis(EPOCH)
    first_event = _event(1, current.hash, "a")
    second_event = _event(2, first_event["hash"], "b", event_type="report.posted")
    terminal = CursorAnchor(EPOCH, 2, second_event["hash"])

    staged = store.stage_page(
        current_anchor=current,
        next_anchor=terminal,
        events=[first_event, second_event],
        staged_at=NOW,
    )
    assert staged.state == "staged"
    assert staged.event_count == staged.enqueued_count == 2
    assert store.committed_anchor() == current
    assert store.staged_anchor() == terminal
    assert store.pending_outbox() == ()
    assert store.recent_projections() == ()
    assert store.outbox_counts() == {
        "pending": 0,
        "inflight": 0,
        "sent": 0,
        "failed": 0,
        "unknown": 0,
    }
    staged_projection = project_collab_event(first_event, opaque_key=KEY)
    with pytest.raises(DeliveryStateError, match="cursor is not committed"):
        store.claim_delivery(staged_projection.event_key)
    staged_task_ref = staged_projection.subject_ref
    for query in (
        store.status_snapshot,
        lambda: store.list_tasks(limit=10),
        lambda: store.get_task(staged_task_ref),
        lambda: store.recent_events(limit=10),
        store.journal_verify,
    ):
        with pytest.raises(CursorStateError, match="exact staged page"):
            query()

    # Retrying before the host acknowledges does not enqueue a second copy.
    duplicate_stage = store.stage_page(
        current_anchor=current,
        next_anchor=terminal,
        events=[first_event, second_event],
        staged_at=NOW + timedelta(seconds=1),
    )
    assert duplicate_stage.duplicate is True
    assert duplicate_stage.state == "staged"
    assert duplicate_stage.enqueued_count == 0

    wrong = CursorAnchor(EPOCH, 1, first_event["hash"])
    with pytest.raises(CursorStateError, match="does not match"):
        store.commit_staged_cursor(wrong, committed_at=NOW)
    assert store.staged_anchor() == terminal

    committed = store.commit_staged_cursor(terminal, committed_at=NOW)
    assert committed.duplicate is False
    assert store.committed_anchor() == terminal
    assert store.staged_anchor() is None
    assert [item.projection.sequence for item in store.pending_outbox()] == [1, 2]

    assert store.commit_staged_cursor(terminal).duplicate is True
    empty_poll = store.stage_page(
        current_anchor=terminal,
        next_anchor=terminal,
        events=(),
    )
    assert empty_poll == type(empty_poll)(terminal, 0, 0, "committed", True)
    assert len(store.pending_outbox()) == 2

    replay = store.stage_page(
        current_anchor=current,
        next_anchor=terminal,
        events=[first_event, second_event],
    )
    assert replay == type(replay)(terminal, 2, 0, "committed", True)
    assert len(store.pending_outbox()) == 2


def test_stage_rejects_gaps_bad_links_and_a_second_uncommitted_page(
    store: AgentToolOpsStore,
) -> None:
    current = CursorAnchor.genesis(EPOCH)
    first = _event(1, current.hash, "a")
    terminal = CursorAnchor(EPOCH, 1, first["hash"])

    with pytest.raises(CursorStateError, match="exactly span"):
        store.stage_page(
            current_anchor=current,
            next_anchor=CursorAnchor(EPOCH, 2, "b" * 64),
            events=[first],
        )

    bad_link = _event(1, "f" * 64, "a")
    with pytest.raises(CursorStateError, match="hash link"):
        store.stage_page(
            current_anchor=current,
            next_anchor=terminal,
            events=[bad_link],
        )
    assert store.committed_anchor() is None

    store.stage_page(current_anchor=current, next_anchor=terminal, events=[first])
    second = _event(2, first["hash"], "b")
    with pytest.raises(CursorStateError, match="another exact page"):
        store.stage_page(
            current_anchor=terminal,
            next_anchor=CursorAnchor(EPOCH, 2, second["hash"]),
            events=[second],
        )


def test_page_iterable_is_bounded_before_full_materialization(
    store: AgentToolOpsStore,
) -> None:
    yielded = 0

    def endless_events() -> Any:
        nonlocal yielded
        while True:
            yielded += 1
            yield _event(yielded, ZERO_HASH, "a")

    with pytest.raises(OpsProjectionError, match="supported maximum"):
        store.stage_page(
            current_anchor=CursorAnchor.genesis(EPOCH),
            next_anchor=CursorAnchor(EPOCH, 51, "a" * 64),
            events=endless_events(),
        )
    assert yielded == 51
    assert store.committed_anchor() is None


def test_page_replay_digest_binds_only_consumed_safe_scalars(
    tmp_path: Path,
) -> None:
    cases = []
    created = _event(
        1,
        ZERO_HASH,
        "a",
        event_type="task.created",
        entity_id="task-safe-scalar",
        payload={"version": 1, "review_status": "not_required"},
    )
    changed_version = dict(created)
    changed_version["payload"] = {"version": 2, "review_status": "not_required"}
    cases.append((created, changed_version))

    changed_review = dict(created)
    changed_review["payload"] = {"version": 1, "review_status": "pending"}
    cases.append((created, changed_review))

    artifact = _event(
        1,
        ZERO_HASH,
        "b",
        event_type="artifact.attached",
        entity_id="task-artifact-link",
        payload={
            "version": 7,
            "artifact": {"task_id": "task-artifact-link", "uri": "/private/a"},
        },
    )
    changed_link = dict(artifact)
    changed_link["payload"] = {
        "version": 7,
        "artifact": {"task_id": "task-other-link", "uri": "/private/b"},
    }
    cases.append((artifact, changed_link))

    for index, (original, changed) in enumerate(cases):
        path = tmp_path / f"derived-{index}" / "ops.sqlite3"
        with AgentToolOpsStore(path, opaque_key=KEY) as ledger:
            terminal = CursorAnchor(EPOCH, 1, original["hash"])
            ledger.stage_page(
                current_anchor=CursorAnchor.genesis(EPOCH),
                next_anchor=terminal,
                events=[original],
            )
            with pytest.raises(ProjectionConflict, match="different staged page"):
                ledger.stage_page(
                    current_anchor=CursorAnchor.genesis(EPOCH),
                    next_anchor=terminal,
                    events=[changed],
                )


def test_page_transaction_rolls_back_projection_conflicts(
    store: AgentToolOpsStore,
) -> None:
    current = CursorAnchor.genesis(EPOCH)
    first = _event(1, current.hash, "a")
    store.stage_page(
        current_anchor=current,
        next_anchor=CursorAnchor(EPOCH, 1, first["hash"]),
        events=[first],
    )
    store.commit_staged_cursor(CursorAnchor(EPOCH, 1, first["hash"]))

    # A distinct hash at the already-used journal sequence is never accepted.
    conflicting = _event(1, current.hash, "c")
    with pytest.raises((CursorStateError, ProjectionConflict)):
        store.stage_page(
            current_anchor=current,
            next_anchor=CursorAnchor(EPOCH, 1, conflicting["hash"]),
            events=[conflicting],
        )
    assert len(store.recent_projections()) == 1


def test_store_persists_only_safe_projection_not_raw_private_fields(
    store: AgentToolOpsStore,
) -> None:
    secrets_in_event = {
        "task": "task-private-raw-id",
        "report": "a raw report body with private facts",
        "path": "/Users/person/secret/project.py",
        "session": "session_private_raw_id",
        "actor": "operator-personal-name",
    }
    raw = _event(
        1,
        ZERO_HASH,
        "a",
        entity_id=secrets_in_event["task"],
        payload={"body": secrets_in_event["report"], "path": secrets_in_event["path"]},
    )
    raw["session_id"] = secrets_in_event["session"]
    raw["actor"] = secrets_in_event["actor"]
    store.stage_page(
        current_anchor=CursorAnchor.genesis(EPOCH),
        next_anchor=CursorAnchor(EPOCH, 1, raw["hash"]),
        events=[raw],
    )

    sql_dump = "\n".join(store.conn.iterdump())
    for private_value in secrets_in_event.values():
        assert private_value not in sql_dump
    assert "Observed coordination state only" in sql_dump


def test_unknown_delivery_is_not_retried_until_explicit_reconciliation(
    store: AgentToolOpsStore,
) -> None:
    raw = _event(1, ZERO_HASH, "a")
    store.stage_page(
        current_anchor=CursorAnchor.genesis(EPOCH),
        next_anchor=CursorAnchor(EPOCH, 1, raw["hash"]),
        events=[raw],
    )
    store.commit_staged_cursor(CursorAnchor(EPOCH, 1, raw["hash"]))
    key = store.pending_outbox()[0].event_key

    claimed = store.claim_delivery(key, attempted_at=NOW)
    assert claimed.state == "inflight"
    assert claimed.attempt_count == 1
    unknown = store.finish_delivery(
        key,
        state="unknown",
        error_code="telegram_timeout",
        finished_at=NOW + timedelta(seconds=1),
    )
    assert unknown.state == "unknown"
    assert store.pending_outbox() == ()
    with pytest.raises(DeliveryStateError, match="reconcile"):
        store.claim_delivery(key)

    reconciled = store.reconcile_unknown(
        key,
        outcome="sent",
        receipt_ref="telegram:321",
        reconciliation_ref="operator-check:321",
        reconciled_at=NOW + timedelta(seconds=2),
    )
    assert reconciled.state == "sent"
    assert reconciled.receipt_ref == "telegram:321"
    duplicate = store.claim_delivery(key)
    assert duplicate.state == "sent"
    assert duplicate.duplicate is True
    assert duplicate.attempt_count == 1


def test_failed_delivery_requires_explicit_retry_and_inflight_can_reconcile(
    store: AgentToolOpsStore,
) -> None:
    raw = _event(1, ZERO_HASH, "a")
    store.stage_page(
        current_anchor=CursorAnchor.genesis(EPOCH),
        next_anchor=CursorAnchor(EPOCH, 1, raw["hash"]),
        events=[raw],
    )
    store.commit_staged_cursor(CursorAnchor(EPOCH, 1, raw["hash"]))
    key = store.pending_outbox()[0].event_key
    store.claim_delivery(key)
    failed = store.finish_delivery(key, state="failed", error_code="forbidden")
    assert failed.state == "failed"
    with pytest.raises(DeliveryStateError, match="explicit review"):
        store.claim_delivery(key)

    second = store.claim_delivery(key, retry_failed=True)
    assert second.state == "inflight"
    assert second.attempt_count == 2
    reconciled = store.reconcile_unknown(
        key,
        outcome="failed",
        attempt_count=second.attempt_count,
        reconciliation_ref="provider-check:not-found",
    )
    assert reconciled.state == "failed"
    assert reconciled.receipt_ref is None


def test_sent_delivery_requires_bounded_receipt_and_only_inflight_can_finish(
    store: AgentToolOpsStore,
) -> None:
    raw = _event(1, ZERO_HASH, "a")
    store.stage_page(
        current_anchor=CursorAnchor.genesis(EPOCH),
        next_anchor=CursorAnchor(EPOCH, 1, raw["hash"]),
        events=[raw],
    )
    store.commit_staged_cursor(CursorAnchor(EPOCH, 1, raw["hash"]))
    key = store.pending_outbox()[0].event_key
    with pytest.raises(DeliveryStateError, match="inflight"):
        store.finish_delivery(key, state="unknown")
    store.claim_delivery(key)
    with pytest.raises(ValueError, match="requires a receipt"):
        store.finish_delivery(key, state="sent")
    sent = store.finish_delivery(key, state="sent", receipt_ref="telegram:42")
    assert sent.state == "sent"
    assert store.outbox_counts() == {
        "pending": 0,
        "inflight": 0,
        "sent": 1,
        "failed": 0,
        "unknown": 0,
    }


def test_opaque_key_and_alias_are_stable_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "stable" / "ops.sqlite3"
    raw = _event(1, ZERO_HASH, "a")
    with AgentToolOpsStore(path, opaque_key=KEY) as first:
        projected = project_collab_event(raw, opaque_key=KEY)
        first.stage_page(
            current_anchor=CursorAnchor.genesis(EPOCH),
            next_anchor=CursorAnchor(EPOCH, 1, raw["hash"]),
            events=[raw],
        )
        first.commit_staged_cursor(CursorAnchor(EPOCH, 1, raw["hash"]))

    with AgentToolOpsStore(path, opaque_key=KEY) as reopened:
        assert reopened.recent_projections() == (projected,)
    with pytest.raises(ProjectionConflict, match="key"):
        AgentToolOpsStore(path, opaque_key=b"different-key-material-value-12345")
    with pytest.raises(ProjectionConflict, match="alias"):
        AgentToolOpsStore(path, workspace_alias="Another_Ops", opaque_key=KEY)


def test_store_is_a_safe_read_only_projection_source(
    store: AgentToolOpsStore,
) -> None:
    raw_task_id = "task-raw-private-alpha"
    events = [
        _event(
            1,
            ZERO_HASH,
            "a",
            event_type="task.created",
            entity_id=raw_task_id,
            payload={"version": 1, "review_status": "not_required"},
        ),
        _event(
            2,
            "a" * 64,
            "b",
            event_type="task.claimed",
            entity_id=raw_task_id,
            payload={
                "version": 2,
                "body": "private task description",
                "path_scopes": ["/Users/private/project.py"],
            },
        ),
        _event(
            3,
            "b" * 64,
            "c",
            event_type="session.joined",
            entity_id="session-private-alpha",
            payload={"actor": "private person"},
        ),
        _event(
            4,
            "c" * 64,
            "d",
            event_type="artifact.attached",
            entity_id=raw_task_id,
            payload={
                "version": 3,
                "artifact": {
                    "task_id": raw_task_id,
                    "id": "artifact-private-alpha",
                    "uri": "/Users/private/evidence.txt",
                },
            },
        ),
    ]
    terminal = CursorAnchor(EPOCH, 4, "d" * 64)
    store.stage_page(
        current_anchor=CursorAnchor.genesis(EPOCH),
        next_anchor=terminal,
        events=events,
    )
    store.commit_staged_cursor(terminal)

    status = store.status_snapshot()
    assert isinstance(status, OpsStatusProjection)
    assert status.workspace_alias == "kingdom_ops"
    assert status.journal_head_sequence == 4
    assert status.claimed_tasks == 1
    assert status.session_records_observed == 1
    assert status.sessions_recorded_active == 1

    tasks = store.list_tasks(limit=10)
    assert len(tasks) == 1 and isinstance(tasks[0], SafeTaskProjection)
    task = tasks[0]
    assert task.task_id.startswith("tsk_")
    assert task.task_id != raw_task_id
    assert task.state == "claimed"
    assert task.version == 3
    assert task.coordination_lease_recorded is True
    assert task.review_state == "not_required"
    assert task.evidence_reference_count == 1
    assert store.get_task(task.task_id) == task

    recent = store.recent_events(limit=10)
    assert all(isinstance(item, OpsSafeEventProjection) for item in recent)
    assert [item.kind for item in recent] == [
        "artifact.attached",
        "session.joined",
        "task.claimed",
        "task.created",
    ]
    assert recent[2].task_id == task.task_id
    assert recent[0].task_id == task.task_id

    verification = store.journal_verify()
    assert isinstance(verification, JournalVerificationProjection)
    assert verification.outcome == "unavailable"
    assert verification.journal_head_sequence == 4
    assert "hash recomputation not performed" in verification.verification_scope

    dump = "\n".join(store.conn.iterdump())
    for raw_value in (
        raw_task_id,
        "private task description",
        "/Users/private/project.py",
        "session-private-alpha",
        "private person",
        "artifact-private-alpha",
        "/Users/private/evidence.txt",
    ):
        assert raw_value not in dump


def test_task_state_uses_only_observed_version_and_review_scalars(
    store: AgentToolOpsStore,
) -> None:
    raw_task_id = "task-private-review"
    events = [
        _event(
            1,
            ZERO_HASH,
            "a",
            event_type="task.created",
            entity_id=raw_task_id,
            payload={"title": "no version must not be invented"},
        ),
        _event(
            2,
            "a" * 64,
            "b",
            event_type="task.reported_complete",
            entity_id=raw_task_id,
            payload={"version": 3, "review_status": "pending"},
        ),
        _event(
            3,
            "b" * 64,
            "c",
            event_type="task.accepted",
            entity_id=raw_task_id,
            payload={"version": 4, "outcome": "accepted"},
        ),
    ]
    terminal = CursorAnchor(EPOCH, 3, "c" * 64)
    store.stage_page(
        current_anchor=CursorAnchor.genesis(EPOCH),
        next_anchor=terminal,
        events=events,
    )
    store.commit_staged_cursor(terminal)

    task = store.list_tasks(limit=10)[0]
    assert task.version == 4
    assert task.state == "completed"
    assert task.review_state == "accepted"
    assert task.coordination_lease_recorded is False
    assert "external authority" in task.summary


def test_installed_collab_event_names_drive_exact_conservative_state(
    store: AgentToolOpsStore,
) -> None:
    events: list[dict[str, Any]] = []

    def append(
        event_type: str,
        entity_id: str,
        payload: dict[str, Any],
    ) -> None:
        sequence = len(events) + 1
        previous = events[-1]["hash"] if events else ZERO_HASH
        event = _event(
            sequence,
            previous,
            "a",
            event_type=event_type,
            entity_id=entity_id,
            payload=payload,
        )
        event["hash"] = hashlib.sha256(f"event-{sequence}".encode()).hexdigest()
        events.append(event)

    append("task.created", "task-expiry", {"version": 1})
    append("task.claimed", "task-expiry", {"version": 2})
    append("task.progressed", "task-expiry", {"version": 3, "message": "private"})
    append("task.lease_renewed", "task-expiry", {"version": 4})
    append("task.claim_expired", "task-expiry", {"version": 5})

    append("task.created", "task-accepted", {"version": 1})
    append("task.claimed", "task-accepted", {"version": 2})
    append("task.reported_complete", "task-accepted", {"version": 3})
    append("task.accepted", "task-accepted", {"version": 4})

    append("task.created", "task-changes", {"version": 1})
    append("task.claimed", "task-changes", {"version": 2})
    append("task.reported_complete", "task-changes", {"version": 3})
    append("task.changes_requested", "task-changes", {"version": 4})

    append("task.created", "task-reported-policy", {"version": 1})
    append("task.claimed", "task-reported-policy", {"version": 2})
    append("task.completed", "task-reported-policy", {"version": 3})

    append("session.joined", "session-bound", {})
    append("session.resumed", "session-bound", {})
    append("session.ended", "session-bound", {})
    append("session.heartbeat", "presence-hint", {"version": 2})

    terminal = CursorAnchor(EPOCH, len(events), events[-1]["hash"])
    store.stage_page(
        current_anchor=CursorAnchor.genesis(EPOCH),
        next_anchor=terminal,
        events=events,
    )
    store.commit_staged_cursor(terminal)

    tasks = {task.task_id: task for task in store.list_tasks(limit=20)}

    def task_for(raw_id: str) -> SafeTaskProjection:
        event = next(item for item in events if item["entity_id"] == raw_id)
        ref = project_collab_event(event, opaque_key=KEY).subject_ref
        return tasks[ref]

    expired = task_for("task-expiry")
    assert (expired.state, expired.version, expired.coordination_lease_recorded) == (
        "open",
        5,
        False,
    )
    accepted = task_for("task-accepted")
    assert (accepted.state, accepted.review_state, accepted.version) == (
        "completed",
        "accepted",
        4,
    )
    changes = task_for("task-changes")
    assert (changes.state, changes.review_state, changes.version) == (
        "open",
        "changes_requested",
        4,
    )
    reported_policy = task_for("task-reported-policy")
    assert (reported_policy.state, reported_policy.review_state) == (
        "completed",
        "not_required",
    )

    status = store.status_snapshot()
    assert status.open_tasks == 2
    assert status.completed_tasks == 2
    assert status.reported_complete_tasks == 0
    assert status.session_records_observed == 2
    assert status.sessions_recorded_active == 1


@pytest.mark.parametrize(
    "action,expected_state,expected_lease,expected_version",
    [
        ("takeover", "claimed", True, 2),
        ("release", "open", False, 2),
        ("block", "blocked", False, 2),
        (None, "open", False, 1),
        ("unexpected", "open", False, 1),
    ],
)
def test_recovery_state_requires_an_explicit_allowlisted_action(
    tmp_path: Path,
    action: str | None,
    expected_state: str,
    expected_lease: bool,
    expected_version: int,
) -> None:
    created = _event(
        1,
        ZERO_HASH,
        "a",
        event_type="task.created",
        entity_id="task-recovery-action",
        payload={"version": 1},
    )
    payload: dict[str, Any] = {"version": 2}
    if action is not None:
        payload["action"] = action
    recovered = _event(
        2,
        created["hash"],
        "b",
        event_type="task.recovered",
        entity_id="task-recovery-action",
        payload=payload,
    )
    with AgentToolOpsStore(
        tmp_path / f"recovery-{action}" / "ops.sqlite3",
        opaque_key=KEY,
    ) as ledger:
        terminal = CursorAnchor(EPOCH, 2, recovered["hash"])
        ledger.stage_page(
            current_anchor=CursorAnchor.genesis(EPOCH),
            next_anchor=terminal,
            events=[created, recovered],
        )
        ledger.commit_staged_cursor(terminal)
        task = ledger.list_tasks(limit=10)[0]
        assert task.state == expected_state
        assert task.coordination_lease_recorded is expected_lease
        assert task.version == expected_version
        recovery_event = ledger.recent_events(limit=1)[0]
        assert recovery_event.kind == "task.recovered"
        assert "resulting state is separately projected only when explicit" in (
            recovery_event.summary
        )


def test_update_claims_are_atomic_durable_and_not_a_max_seen_cursor(
    tmp_path: Path,
) -> None:
    path = tmp_path / "updates" / "ops.sqlite3"
    with AgentToolOpsStore(path, opaque_key=KEY) as first:
        assert first.claim_update(20, claimed_at=NOW) is True
        assert first.claim_update(20, claimed_at=NOW + timedelta(seconds=1)) is False
        assert first.claim_update(5, claimed_at=NOW + timedelta(seconds=2)) is True
    with AgentToolOpsStore(path, opaque_key=KEY) as reopened:
        assert reopened.claim_update(20) is False
        assert reopened.claim_update(5) is False
        assert reopened.claim_update(19) is True
        rows = reopened.conn.execute(
            "SELECT update_id FROM telegram_updates ORDER BY update_id"
        ).fetchall()
        assert [int(row[0]) for row in rows] == [5, 19, 20]


def test_latest_supplied_full_journal_verification_is_bounded_and_honest(
    store: AgentToolOpsStore,
) -> None:
    # No verifier has run: local page-link checks are not mislabeled as a full
    # Collab hash recomputation.
    initial = store.journal_verify()
    assert initial.outcome == "unavailable"
    assert initial.checked_at == "not performed"
    assert "not performed" in initial.verification_scope

    store.record_journal_verification(
        outcome="valid",
        checked_at=NOW,
        journal_head_sequence=42,
        scope_code="full_collab_hash_chain",
    )
    observed = store.journal_verify()
    assert observed.outcome == "valid"
    assert observed.checked_at == "2026-09-03T19:00:00.000000Z"
    assert observed.journal_head_sequence == 42
    assert observed.verification_scope == (
        "full Collab journal hash-chain recomputation through supplied head"
    )

    store.record_journal_verification(
        outcome="invalid",
        checked_at=NOW + timedelta(seconds=30),
        journal_head_sequence=None,
        scope_code="full_collab_hash_chain",
    )
    invalid = store.journal_verify()
    assert invalid.outcome == "invalid"
    assert invalid.journal_head_sequence is None

    store.record_journal_verification(
        outcome="unavailable",
        checked_at=NOW + timedelta(minutes=1),
        journal_head_sequence=None,
        scope_code="full_collab_hash_chain_unavailable",
    )
    unavailable = store.journal_verify()
    assert unavailable.outcome == "unavailable"
    assert unavailable.journal_head_sequence is None
    assert unavailable.verification_scope.endswith("unavailable")

    with pytest.raises(ValueError, match="requires its full-chain scope"):
        store.record_journal_verification(
            outcome="valid",
            checked_at=NOW,
            journal_head_sequence=None,
            scope_code="full_collab_hash_chain_unavailable",
        )


@pytest.mark.parametrize("update_id", [True, -1, 1 << 31, "5"])
def test_invalid_update_claims_fail_closed(
    store: AgentToolOpsStore, update_id: object
) -> None:
    with pytest.raises(ValueError, match="update_id"):
        store.claim_update(update_id)  # type: ignore[arg-type]


def test_database_and_sidecars_are_owner_only(store: AgentToolOpsStore) -> None:
    raw = _event(1, ZERO_HASH, "a")
    store.stage_page(
        current_anchor=CursorAnchor.genesis(EPOCH),
        next_anchor=CursorAnchor(EPOCH, 1, raw["hash"]),
        events=[raw],
    )

    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(store.path) + suffix)
        if sidecar.exists():
            assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600


def _restore_v1_schema(path: Path, *, marker: bool = True) -> None:
    """Remove only additive v2 objects to recreate the exact recognized v1."""
    from telegram_gateway.agenttool_ops import _OPS_SCHEMA_OBJECTS, _OPS_V1_SCHEMA_OBJECTS

    legacy = sqlite3.connect(path)
    for kind, name, _table in sorted(_OPS_SCHEMA_OBJECTS - _OPS_V1_SCHEMA_OBJECTS):
        legacy.execute(f'DROP {kind.upper()} "{name}"')
    if marker:
        legacy.execute("UPDATE ops_meta SET value = ? WHERE key = ?",
                       (OPS_V1_DATABASE_ROLE.encode("ascii"), OPS_DATABASE_ROLE_META_KEY))
    else:
        legacy.execute("DELETE FROM ops_meta WHERE key = ?", (OPS_DATABASE_ROLE_META_KEY,))
    legacy.commit()
    legacy.close()


@pytest.mark.parametrize("marker", [True, False])
def test_fresh_store_records_fixed_database_role_and_legacy_store_migrates(
    tmp_path: Path, marker: bool,
) -> None:
    path = tmp_path / "role-migration" / "ops.sqlite3"
    with AgentToolOpsStore(path, opaque_key=KEY) as created:
        role = created.conn.execute(
            "SELECT typeof(value), value FROM ops_meta WHERE key = ?",
            (OPS_DATABASE_ROLE_META_KEY,),
        ).fetchone()
        assert tuple(role) == ("blob", OPS_DATABASE_ROLE.encode("ascii"))
        created.claim_update(41, claimed_at=NOW)
        original_alias = created.workspace_alias
    _restore_v1_schema(path, marker=marker)
    before = path.read_bytes()
    with pytest.raises(MigrationRequiredError):
        AgentToolOpsStore(path, opaque_key=KEY)
    preview = AgentToolOpsStore.preview_migration(path)
    assert preview["migration_required"] is True
    assert preview["historical_incomplete_claims"] == 1
    assert path.read_bytes() == before
    assert AgentToolOpsStore.migrate_v1(path)["applied"] is True
    with AgentToolOpsStore(path, opaque_key=KEY) as migrated:
        assert migrated.workspace_alias == original_alias
        assert migrated.claim_update(41) is False
        assert migrated.binding() is None
        assert migrated.list_replies() == ()
        marker_row = migrated.conn.execute(
            "SELECT value FROM ops_meta WHERE key = ?", (OPS_DATABASE_ROLE_META_KEY,),
        ).fetchone()
        assert bytes(marker_row[0]) == OPS_DATABASE_ROLE.encode("ascii")
    assert AgentToolOpsStore.preview_migration(path)["migration_required"] is False


def test_foreign_sqlite_database_is_rejected_without_mutation_or_chmod(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "foreign-research"
    parent.mkdir(mode=0o700)
    os.chmod(parent, 0o700)
    path = parent / "research.sqlite3"
    foreign = sqlite3.connect(path)
    foreign.execute("CREATE TABLE research_signals (private_value TEXT NOT NULL)")
    foreign.execute("INSERT INTO research_signals VALUES ('private-sentinel')")
    foreign.commit()
    foreign.close()
    os.chmod(path, 0o640)
    original_bytes = path.read_bytes()
    original_mode = stat.S_IMODE(path.stat().st_mode)

    with pytest.raises(DatabaseRoleError) as captured:
        AgentToolOpsStore(path, opaque_key=KEY)

    assert str(path) not in str(captured.value)
    assert "research_signals" not in str(captured.value)
    assert "private-sentinel" not in str(captured.value)
    assert path.read_bytes() == original_bytes
    assert stat.S_IMODE(path.stat().st_mode) == original_mode == 0o640
    assert not Path(str(path) + "-wal").exists()
    assert not Path(str(path) + "-shm").exists()
    check = sqlite3.connect(path)
    try:
        assert check.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert check.execute("SELECT * FROM research_signals").fetchall() == [
            ("private-sentinel",)
        ]
        assert check.execute(
            "SELECT 1 FROM sqlite_schema WHERE name = 'ops_meta'"
        ).fetchone() is None
    finally:
        check.close()


def test_mixed_database_is_rejected_before_role_validation_can_mutate_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mixed-role" / "ops.sqlite3"
    with AgentToolOpsStore(path, opaque_key=KEY):
        pass
    mixed = sqlite3.connect(path)
    mixed.execute("CREATE TABLE research_private (value TEXT)")
    mixed.execute("INSERT INTO research_private VALUES ('preserve-me')")
    mixed.commit()
    mixed.close()
    os.chmod(path, 0o640)
    original_bytes = path.read_bytes()

    with pytest.raises(DatabaseRoleError) as captured:
        AgentToolOpsStore(path, opaque_key=KEY)

    assert str(path) not in str(captured.value)
    assert "research_private" not in str(captured.value)
    assert path.read_bytes() == original_bytes
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_wrong_database_role_is_rejected_on_every_open_without_repair(
    tmp_path: Path,
) -> None:
    path = tmp_path / "wrong-role" / "ops.sqlite3"
    with AgentToolOpsStore(path, opaque_key=KEY):
        pass
    changed = sqlite3.connect(path)
    changed.execute(
        "UPDATE ops_meta SET value = ? WHERE key = ?",
        (b"kingdom.research/v1", OPS_DATABASE_ROLE_META_KEY),
    )
    changed.commit()
    changed.close()
    original_bytes = path.read_bytes()

    with pytest.raises(DatabaseRoleError) as captured:
        AgentToolOpsStore(path, opaque_key=KEY)

    assert str(path) not in str(captured.value)
    assert "kingdom.research" not in str(captured.value)
    assert path.read_bytes() == original_bytes


def test_insecure_existing_directory_is_rejected(tmp_path: Path) -> None:
    parent = tmp_path / "insecure"
    parent.mkdir()
    os.chmod(parent, 0o755)
    with pytest.raises(PermissionError, match="owner-only") as captured:
        AgentToolOpsStore(parent / "ops.sqlite3", opaque_key=KEY)
    assert str(parent) not in str(captured.value)


def test_uninitialized_store_does_not_invent_an_observed_head_or_task_state(
    store: AgentToolOpsStore,
) -> None:
    for query in (
        store.status_snapshot,
        lambda: store.list_tasks(limit=10),
        lambda: store.get_task("tsk_" + "a" * 24),
        lambda: store.recent_events(limit=10),
    ):
        with pytest.raises(CursorStateError, match="cursor is initialized"):
            query()
    verification = store.journal_verify()
    assert verification.outcome == "unavailable"
    assert verification.journal_head_sequence is None


def test_cursor_anchor_rejects_ambiguous_values() -> None:
    with pytest.raises(OpsProjectionError, match="sequence"):
        CursorAnchor(EPOCH, True, ZERO_HASH)  # type: ignore[arg-type]
    with pytest.raises(OpsProjectionError, match="hash"):
        CursorAnchor(EPOCH, 0, "A" * 64)
    with pytest.raises(OpsProjectionError, match="epoch"):
        CursorAnchor("", 0, ZERO_HASH)


def test_staging_is_safe_under_sqlite_write_contention(tmp_path: Path) -> None:
    path = tmp_path / "contended" / "ops.sqlite3"
    with AgentToolOpsStore(path, opaque_key=KEY) as first, AgentToolOpsStore(
        path, opaque_key=KEY
    ) as second:
        first.conn.execute("BEGIN IMMEDIATE")
        raw = _event(1, ZERO_HASH, "a")
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                second.stage_page(
                    current_anchor=CursorAnchor.genesis(EPOCH),
                    next_anchor=CursorAnchor(EPOCH, 1, raw["hash"]),
                    events=[raw],
                )
        finally:
            first.conn.rollback()
        assert second.committed_anchor() is None


# Durable command-reply foundation. All identities and timestamps are synthetic.
OPERATOR = 424242
BOT = 919191


def _bind(ledger: AgentToolOpsStore, **overrides: Any) -> Any:
    values = dict(
        bot_id=BOT, api_origin=TELEGRAM_PRODUCTION_ORIGIN,
        operator_user_id=OPERATOR, operator_private_chat_id=OPERATOR,
        credential_ref="fixture:ops-test", source_binding="synthetic-journal",
        verification="fixture", bound_at=NOW,
    )
    values.update(overrides)
    return ledger.bind_operator(**values)


def _command(update_id: int = 100, text: str = "/help", *, at: datetime | None = None) -> dict[str, Any]:
    return {"update_id": update_id, "message": {
        "date": int((at or NOW + timedelta(seconds=10)).timestamp()),
        "from": {"id": OPERATOR, "is_bot": False},
        "chat": {"id": OPERATOR, "type": "private"}, "text": text,
    }}


def _service(ledger: AgentToolOpsStore) -> Any:
    from telegram_gateway.ops_service import OpsServiceConfig, TelegramOpsService
    return TelegramOpsService(ledger, ledger, OpsServiceConfig(OPERATOR, OPERATOR))


def _stage_reply(ledger: AgentToolOpsStore, update_id: int = 100) -> Any:
    state = ledger.poll_state()
    staged = ledger.process_update_once(
        _command(update_id), _service(ledger), polling_epoch=state.epoch,
        processed_at=NOW + timedelta(seconds=10),
    )
    return ledger.reply_item(staged.reply_id)


def _claim_reply(ledger: AgentToolOpsStore, item: Any) -> Any:
    return ledger.claim_reply(item.reply_id, payload_digest=item.payload_digest,
                              binding_revision=item.binding_revision, attempted_at=NOW)


def test_binding_is_durable_compare_not_rebind_and_live_rejects_fixture(store: AgentToolOpsStore) -> None:
    bound = _bind(store)
    assert _bind(store, bound_at=NOW + timedelta(minutes=1)) == bound
    assert bound.revision == 1 and bound.verification == "fixture"
    store.bind_telegram_provider(BOT, TELEGRAM_PRODUCTION_ORIGIN, allow_create=False)
    for overrides in (
        {"bot_id": BOT + 1}, {"operator_user_id": OPERATOR + 1, "operator_private_chat_id": OPERATOR + 1},
        {"source_binding": "another-journal"}, {"credential_ref": "fixture:another"},
        {"verification": "verified", "credential_ref": OPS_CREDENTIAL_PREFIX + "test-bot"},
    ):
        with pytest.raises(BindingStateError, match="mismatch"):
            _bind(store, **overrides)
    with pytest.raises(BindingStateError, match="fixture"):
        store.require_ready(bot_id=BOT, operator_user_id=OPERATOR,
            operator_private_chat_id=OPERATOR, api_origin=TELEGRAM_PRODUCTION_ORIGIN,
            credential_ref="fixture:ops-test", source_binding="synthetic-journal")
    with AgentToolOpsStore(store.path, opaque_key=KEY) as reopened:
        assert reopened.binding() == bound
    assert store.binding() == bound


@pytest.mark.parametrize("overrides", [
    {"bot_id": True}, {"operator_private_chat_id": OPERATOR + 1},
    {"api_origin": "https://unapproved.invalid"}, {"source_binding": None},
    {"source_binding": "/private/path"}, {"credential_ref": "12345:raw-token-sentinel"},
    {"credential_ref": "keychain:dev.kingdom.prediction-markets.telegram-bot-token:research"},
    {"verification": "verified", "credential_ref": "fixture:not-live"},
])
def test_binding_rejects_invalid_or_shared_credential_inputs(store: AgentToolOpsStore, overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _bind(store, **overrides)
    assert store.binding() is None
    assert "raw-token-sentinel" not in "\n".join(store.conn.iterdump())


def test_provider_protocol_never_creates_partial_binding_and_expectations_are_exact(store: AgentToolOpsStore) -> None:
    with pytest.raises(BindingStateError):
        store.bind_telegram_provider(BOT, TELEGRAM_PRODUCTION_ORIGIN)
    binding = _bind(store, verification="verified", credential_ref=OPS_CREDENTIAL_PREFIX + "ops-test")
    expected = dict(bot_id=BOT, operator_user_id=OPERATOR, operator_private_chat_id=OPERATOR,
        api_origin=TELEGRAM_PRODUCTION_ORIGIN, credential_ref=binding.credential_ref,
        source_binding=binding.source_binding)
    assert store.require_ready(**expected) == binding
    for field, value in (("bot_id", BOT + 1), ("operator_user_id", OPERATOR + 1),
                         ("operator_private_chat_id", OPERATOR + 1), ("api_origin", "https://other.invalid"),
                         ("credential_ref", "other"), ("source_binding", "other")):
        with pytest.raises(BindingStateError):
            store.require_ready(**{**expected, field: value})
    with pytest.raises(BindingStateError):
        store.bind_telegram_provider(BOT + 1, TELEGRAM_PRODUCTION_ORIGIN, allow_create=False)


def test_atomic_reply_dedupes_without_legacy_claim_or_rerender(store: AgentToolOpsStore, monkeypatch: Any) -> None:
    _bind(store)
    item = _stage_reply(store)
    assert item.state == "pending" and item.chat_id == OPERATOR
    assert store.conn.execute("SELECT COUNT(*) FROM telegram_updates").fetchone()[0] == 0
    from telegram_gateway.ops_service import TelegramOpsService
    monkeypatch.setattr(TelegramOpsService, "render_update", lambda *_: pytest.fail("duplicate rerender"))
    disposition = store.process_update_once(_command(text="private-duplicate-sentinel"),
        _service(store), polling_epoch=1, processed_at=NOW + timedelta(seconds=20))
    assert disposition.duplicate is True and disposition.reply_id == item.reply_id
    assert store.reply_item(item.reply_id) == item
    assert store.poll_state().next_offset == 101
    assert "private-duplicate-sentinel" not in "\n".join(store.conn.iterdump())


@pytest.mark.parametrize("failure", ["render", "persist", "commit"])
def test_atomic_crash_rolls_back_claim_reply_and_cursor(store: AgentToolOpsStore, monkeypatch: Any, failure: str) -> None:
    _bind(store)
    before = "\n".join(store.conn.iterdump())
    class Crash(BaseException):
        pass
    def crash(*args: Any, **kwargs: Any) -> Any:
        raise Crash("unpersisted-private-error")
    with monkeypatch.context() as patch:
        if failure == "render":
            from telegram_gateway.ops_service import TelegramOpsService
            patch.setattr(TelegramOpsService, "render_update", crash)
        elif failure == "persist":
            patch.setattr(store, "_reply_digest", crash)
        else:
            real_connection = store.conn
            class CommitCrash:
                def __getattr__(self, name: str) -> Any:
                    return getattr(real_connection, name)
                def commit(self) -> None:
                    crash()
            patch.setattr(store, "conn", CommitCrash())
        with pytest.raises(Crash):
            _stage_reply(store)
    assert "\n".join(store.conn.iterdump()) == before
    assert store.conn.in_transaction is False
    assert _stage_reply(store).state == "pending"


def test_concurrent_updates_render_once_and_rollback_loser_has_no_claim_gap(store: AgentToolOpsStore, monkeypatch: Any) -> None:
    import concurrent.futures
    import threading
    from telegram_gateway.ops_service import TelegramOpsService
    _bind(store)
    barrier = threading.Barrier(2)
    calls = []
    render = TelegramOpsService.render_update
    def observed_render(self: Any, update: Any) -> Any:
        calls.append(update["update_id"])
        return render(self, update)
    monkeypatch.setattr(TelegramOpsService, "render_update", observed_render)
    def worker() -> Any:
        with AgentToolOpsStore(store.path, opaque_key=KEY) as local:
            barrier.wait(timeout=5)
            return local.process_update_once(_command(), _service(local), polling_epoch=1,
                                             processed_at=NOW + timedelta(seconds=10))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    assert sorted(result.duplicate for result in results) == [False, True]
    assert results[0].reply_id == results[1].reply_id
    assert calls == [100] and len(store.list_replies()) == 1


def test_legacy_claim_gap_stays_offline_without_fabricating_reply_or_binding(store: AgentToolOpsStore) -> None:
    assert _service(store).handle_update(_command()) is not None
    before = "\n".join(store.conn.iterdump())
    with pytest.raises(BindingStateError, match="pristine source"):
        _bind(store)
    assert store.binding() is None and store.list_replies() == ()
    assert store.claim_update(100) is False
    assert "\n".join(store.conn.iterdump()) == before


def test_bound_service_cannot_use_legacy_claim_path(store: AgentToolOpsStore) -> None:
    _bind(store)
    with pytest.raises(BindingStateError, match="atomic"):
        _service(store).handle_update(_command(101))
    assert store.conn.execute("SELECT COUNT(*) FROM telegram_updates").fetchone()[0] == 0


def test_atomic_path_rejects_different_source_or_operator_even_for_help(store: AgentToolOpsStore, tmp_path: Path) -> None:
    from telegram_gateway.ops_service import OpsServiceConfig, TelegramOpsService
    _bind(store)
    with AgentToolOpsStore(tmp_path / "another" / "ops.db") as other:
        with pytest.raises(ValueError, match="local projection"):
            store.process_update_once(_command(), _service(other), polling_epoch=1)
    service = TelegramOpsService(store, store, OpsServiceConfig(OPERATOR + 1, OPERATOR + 1))
    with pytest.raises(BindingStateError, match="recipient"):
        store.process_update_once(_command(), service, polling_epoch=1)
    assert store.list_replies() == () and store.poll_state().next_offset is None


def test_ignored_dispositions_are_durable_and_never_persist_raw_inputs(store: AgentToolOpsStore) -> None:
    _bind(store)
    for index, mutation in enumerate((
        {"chat": {"id": OPERATOR, "type": "group"}},
        {"from": {"id": OPERATOR, "is_bot": True}},
        {"from": {"id": OPERATOR + 1, "is_bot": False}}, {"date": None},
    )):
        update = _command(index, "incoming-private-sentinel")
        update["message"].update(mutation)
        result = store.process_update_once(update, _service(store), polling_epoch=1)
        assert result.disposition == "ignored" and result.reply_id is None
    assert store.list_replies() == ()
    assert store.poll_state().next_offset == 4
    assert "incoming-private-sentinel" not in "\n".join(store.conn.iterdump())


def test_poll_epochs_accept_randomized_ids_without_skipping_or_max_dedupe(store: AgentToolOpsStore) -> None:
    _bind(store)
    first = _stage_reply(store, 2_000_000_000)
    older_unseen = _stage_reply(store, 50)
    assert first.reply_id != older_unseen.reply_id
    assert store.poll_state().next_offset == 51
    # A long idle gap may randomize IDs. Reset BEFORE using an old positive offset.
    later = NOW + timedelta(days=8)
    reset = store.prepare_poll(now=later)
    assert reset.epoch == 2 and reset.next_offset is None
    result = store.process_update_once(_command(50, at=later + timedelta(seconds=1)),
        _service(store), polling_epoch=2, processed_at=later + timedelta(seconds=1))
    assert result.duplicate is False and result.reply_id != older_unseen.reply_id
    assert store.prepare_poll(now=later + timedelta(seconds=2)).next_offset == 51
    with pytest.raises(CursorStateError, match="stale"):
        store.process_update_once(_command(51), _service(store), polling_epoch=1)


def test_reply_delivery_is_fenced_unknown_never_retries_and_evidence_is_append_only(store: AgentToolOpsStore) -> None:
    _bind(store)
    item = _stage_reply(store)
    attempt = _claim_reply(store, item)
    assert attempt.attempt_count == 1 and attempt.state == "inflight"
    with pytest.raises(DeliveryStateError, match="stale"):
        store.finish_reply(item.reply_id, attempt_count=2, state="sent", receipt_ref="telegram:42")
    store.finish_reply(item.reply_id, attempt_count=1, state="unknown", error_code="telegram_timeout")
    with pytest.raises(DeliveryStateError):
        _claim_reply(store, item)
    store.reconcile_reply(item.reply_id, attempt_count=1, outcome="unknown", reconciliation_ref="operator:absence-not-proof")
    store.reconcile_reply(item.reply_id, attempt_count=1, outcome="sent", reconciliation_ref="operator:found", receipt_ref="telegram:42")
    assert store.reply_item(item.reply_id).state == "sent"
    evidence = store.reply_attempts(item.reply_id)
    assert evidence[0]["state"] == "unknown" and evidence[0]["error_code"] == "telegram_timeout"
    reconciliations = store.reply_reconciliations(item.reply_id)
    assert [row["outcome"] for row in reconciliations] == ["unknown", "sent"]
    assert reconciliations[-1]["receipt_ref"] == "telegram:42"
    with pytest.raises(DeliveryStateError):
        store.finish_reply(item.reply_id, attempt_count=1, state="failed")


@pytest.mark.parametrize("evidence", [None, "", " ", "provider body /private/sentinel"])
def test_reply_reconcile_requires_nonempty_safe_evidence(store: AgentToolOpsStore, evidence: Any) -> None:
    _bind(store)
    item = _stage_reply(store)
    _claim_reply(store, item)
    with pytest.raises(ValueError):
        store.reconcile_reply(item.reply_id, attempt_count=1, outcome="failed", reconciliation_ref=evidence)
    assert store.reply_item(item.reply_id).state == "inflight"
    assert store.reply_reconciliations(item.reply_id) == ()


def test_interrupted_attempt_becomes_unknown_and_closed_errors_reject_provider_body(store: AgentToolOpsStore) -> None:
    _bind(store)
    item = _stage_reply(store)
    _claim_reply(store, item)
    with pytest.raises(ValueError, match="error_code"):
        store.finish_reply(item.reply_id, attempt_count=1, state="unknown", error_code="RAW_PRIVATE_PROVIDER_ERROR")
    assert store.mark_interrupted_replies() == 1
    assert store.mark_interrupted_replies() == 0
    assert store.reply_item(item.reply_id).state == "unknown"
    assert store.reply_attempts(item.reply_id)[0]["error_code"] == "interrupted"
    with pytest.raises(DeliveryStateError):
        _claim_reply(store, item)
    assert "RAW_PRIVATE_PROVIDER_ERROR" not in "\n".join(store.conn.iterdump())


def test_reply_preview_digest_binds_text_owner_and_revision(store: AgentToolOpsStore) -> None:
    _bind(store)
    item = _stage_reply(store)
    with pytest.raises(BindingStateError, match="stale"):
        store.claim_reply(item.reply_id, payload_digest="sha256:" + "0" * 64, binding_revision=1)
    with pytest.raises(BindingStateError, match="stale"):
        store.claim_reply(item.reply_id, payload_digest=item.payload_digest, binding_revision=2)
    store.conn.execute("UPDATE ops_replies SET payload_text = 'changed' WHERE reply_id = ?", (item.reply_id,))
    with pytest.raises(ProjectionConflict, match="digest"):
        _claim_reply(store, item)
    store.conn.execute("UPDATE ops_replies SET payload_text = ? WHERE reply_id = ?", (item.text, item.reply_id))
    store.conn.execute("UPDATE ops_bindings SET operator_user_id = ?, operator_private_chat_id = ?", (OPERATOR + 1, OPERATOR + 1))
    with pytest.raises(ProjectionConflict, match="digest"):
        store.reply_item(item.reply_id)


def test_pause_fences_inflight_invalidates_pending_and_resume_cannot_replay_backlog(store: AgentToolOpsStore) -> None:
    _bind(store)
    pending = _stage_reply(store, 100)
    inflight = _stage_reply(store, 101)
    _claim_reply(store, inflight)
    store.pause(paused_at=NOW + timedelta(seconds=20))
    assert store.reply_item(pending.reply_id).state == "invalidated"
    assert store.reply_item(inflight.reply_id).state == "unknown"
    assert store.reply_attempts(inflight.reply_id)[0]["error_code"] == "paused"
    for work in (
        store.prepare_poll, lambda: _claim_reply(store, pending),
        lambda: store.process_update_once(_command(102), _service(store), polling_epoch=1),
        lambda: store.stage_page(current_anchor=CursorAnchor.genesis(EPOCH), next_anchor=CursorAnchor.genesis(EPOCH), events=[]),
    ):
        with pytest.raises(BindingStateError, match="paused"):
            work()
    with pytest.raises(DeliveryStateError):
        store.finish_reply(inflight.reply_id, attempt_count=1, state="sent", receipt_ref="telegram:42")
    resumed = store.resume(resumed_at=NOW + timedelta(seconds=30))
    assert resumed.revision == 2 and store.poll_state().epoch == 2
    assert store.list_replies(state="pending") == ()
    backlog = store.process_update_once(_command(102, at=NOW + timedelta(seconds=25)),
        _service(store), polling_epoch=2)
    assert backlog.disposition == "withdrawn"
    fresh = store.process_update_once(_command(103, at=NOW + timedelta(seconds=31)),
        _service(store), polling_epoch=2)
    assert fresh.disposition == "reply"
    with pytest.raises(BindingStateError, match="stale"):
        _claim_reply(store, pending)


def test_initial_binding_does_not_adopt_old_commands_or_event_delivery(store: AgentToolOpsStore) -> None:
    _bind(store)
    raw = _event(1, ZERO_HASH, "a")
    terminal = CursorAnchor(EPOCH, 1, raw["hash"])
    store.stage_page(current_anchor=CursorAnchor.genesis(EPOCH), next_anchor=terminal, events=[raw])
    store.commit_staged_cursor(terminal)
    event = store.pending_outbox()[0]
    with pytest.raises(BindingStateError, match="disabled"):
        store.claim_delivery(event.event_key)
    assert store.outbox_item(event.event_key) == event
    old = store.process_update_once(_command(at=NOW), _service(store), polling_epoch=1)
    assert old.disposition == "withdrawn"
    assert store.list_replies() == ()


def test_migration_preserves_projection_key_cursor_and_event_evidence(tmp_path: Path) -> None:
    path = tmp_path / "preserved-v1" / "ops.db"
    with AgentToolOpsStore(path, opaque_key=KEY) as ledger:
        raw = _event(1, ZERO_HASH, "a", payload={"version": 1})
        terminal = CursorAnchor(EPOCH, 1, raw["hash"])
        ledger.stage_page(current_anchor=CursorAnchor.genesis(EPOCH), next_anchor=terminal, events=[raw])
        ledger.commit_staged_cursor(terminal)
        item = ledger.pending_outbox()[0]
        ledger.claim_delivery(item.event_key)
        ledger.finish_delivery(item.event_key, state="unknown", error_code="telegram_timeout")
        ledger.claim_update(77)
        expected = ledger.outbox_item(item.event_key)
    _restore_v1_schema(path)
    AgentToolOpsStore.migrate_v1(path)
    with AgentToolOpsStore(path, opaque_key=KEY) as ledger:
        assert ledger.committed_anchor() == terminal
        assert ledger.outbox_item(item.event_key) == expected
        assert ledger.list_tasks(limit=1)[0].version == 1
        assert ledger.claim_update(77) is False
        assert ledger.binding() is None and ledger.list_replies() == ()
        before_binding = "\n".join(ledger.conn.iterdump())
        with pytest.raises(BindingStateError, match="pristine source"):
            ledger.assert_initial_binding_allowed()
        with pytest.raises(BindingStateError, match="pristine source"):
            _bind(ledger, source_binding="different-source")
        assert "\n".join(ledger.conn.iterdump()) == before_binding
        assert ledger.status_snapshot().journal_head_sequence == 1


@pytest.mark.parametrize("marker", [True, False])
def test_migrated_pristine_store_can_bind_before_observing_source(tmp_path: Path, marker: bool) -> None:
    path = tmp_path / "pristine-legacy" / "ops.db"
    with AgentToolOpsStore(path, opaque_key=KEY):
        pass
    _restore_v1_schema(path, marker=marker)
    AgentToolOpsStore.migrate_v1(path)
    with AgentToolOpsStore(path, opaque_key=KEY) as ledger:
        ledger.assert_initial_binding_allowed()
        _bind(ledger)
        anchor = CursorAnchor.genesis(EPOCH)
        ledger.stage_page(current_anchor=anchor, next_anchor=anchor, events=[])
        assert ledger.status_snapshot().journal_head_sequence == 0


def test_migration_failure_rolls_back_every_schema_and_role_change(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "migration-rollback" / "ops.db"
    with AgentToolOpsStore(path, opaque_key=KEY) as ledger:
        ledger.claim_update(19)
    _restore_v1_schema(path)
    before = path.read_bytes()
    installer = AgentToolOpsStore._install_v2
    def broken(conn: sqlite3.Connection) -> None:
        installer(conn)
        raise RuntimeError("synthetic interruption")
    with monkeypatch.context() as patch:
        patch.setattr(AgentToolOpsStore, "_install_v2", staticmethod(broken))
        with pytest.raises(RuntimeError, match="interruption"):
            AgentToolOpsStore.migrate_v1(path)
    assert path.read_bytes() == before
    assert AgentToolOpsStore.preview_migration(path)["migration_required"] is True
    AgentToolOpsStore.migrate_v1(path)


@pytest.mark.parametrize("mutation", [
    "CREATE TABLE research_private (value TEXT)",
    "CREATE TRIGGER altered AFTER INSERT ON telegram_updates BEGIN DELETE FROM telegram_updates; END",
    "DROP INDEX idx_ops_outbox_state",
    "DELETE FROM ops_meta WHERE key = 'database_role'",
])
def test_v2_schema_tampering_is_rejected_without_mutation(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "schema-tamper" / "ops.db"
    with AgentToolOpsStore(path, opaque_key=KEY):
        pass
    conn = sqlite3.connect(path)
    conn.execute(mutation)
    conn.commit()
    conn.close()
    os.chmod(path, 0o640)
    before = path.read_bytes()
    for operation in (AgentToolOpsStore, AgentToolOpsStore.preview_migration, AgentToolOpsStore.migrate_v1):
        with pytest.raises(DatabaseRoleError):
            operation(path)
        assert path.read_bytes() == before and stat.S_IMODE(path.stat().st_mode) == 0o640


def test_v1_extra_schema_is_not_a_migration_candidate(tmp_path: Path) -> None:
    path = tmp_path / "mixed-v1" / "ops.db"
    with AgentToolOpsStore(path, opaque_key=KEY):
        pass
    _restore_v1_schema(path)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE research_state (secret TEXT)")
    conn.commit()
    conn.close()
    before = path.read_bytes()
    with pytest.raises(DatabaseRoleError):
        AgentToolOpsStore.migrate_v1(path)
    assert path.read_bytes() == before


def test_event_reconciliation_rejects_null_evidence_and_stale_finish(store: AgentToolOpsStore) -> None:
    raw = _event(1, ZERO_HASH, "a")
    terminal = CursorAnchor(EPOCH, 1, raw["hash"])
    store.stage_page(current_anchor=CursorAnchor.genesis(EPOCH), next_anchor=terminal, events=[raw])
    store.commit_staged_cursor(terminal)
    key = store.pending_outbox()[0].event_key
    store.claim_delivery(key)
    with pytest.raises(ValueError, match="required"):
        store.reconcile_unknown(key, outcome="failed", reconciliation_ref=None)
    store.finish_delivery(key, state="failed", error_code="forbidden")
    second = store.claim_delivery(key, retry_failed=True)
    with pytest.raises(DeliveryStateError, match="stale"):
        store.finish_delivery(key, state="sent", receipt_ref="telegram:42", attempt_count=1)
    assert store.finish_delivery(key, state="sent", receipt_ref="telegram:43", attempt_count=second.attempt_count).state == "sent"


@pytest.mark.parametrize("phase", ["v1", "v2", "key", "alias", "commit"])
def test_fresh_initialization_interruption_rolls_back_schema_and_metadata_for_retry(
    tmp_path: Path, monkeypatch: Any, phase: str,
) -> None:
    path = tmp_path / "fresh-interruption" / "ops.db"

    class Interruption(BaseException):
        pass

    class InterruptibleConnection(sqlite3.Connection):
        def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
            result = super().execute(sql, *args, **kwargs)
            if phase == "v1" and "CREATE TABLE IF NOT EXISTS journal_verification" in sql:
                assert self.in_transaction
                raise Interruption()
            return result

        def commit(self) -> None:
            if phase == "commit":
                assert self.in_transaction
                assert self.execute("SELECT COUNT(*) FROM ops_meta").fetchone()[0] == 3
                raise Interruption()
            super().commit()

    connect = sqlite3.connect
    installer = AgentToolOpsStore._install_v2
    key_loader = AgentToolOpsStore._load_or_create_key
    alias_loader = AgentToolOpsStore._load_or_set_alias

    def interrupted_installer(conn: sqlite3.Connection) -> None:
        installer(conn)
        assert conn.in_transaction
        if phase == "v2":
            raise Interruption()

    def interrupted_key(ledger: AgentToolOpsStore, supplied: Any) -> bytes:
        result = key_loader(ledger, supplied)
        if phase == "key":
            raise Interruption()
        return result

    def interrupted_alias(ledger: AgentToolOpsStore, supplied: str) -> str:
        result = alias_loader(ledger, supplied)
        if phase == "alias":
            raise Interruption()
        return result

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", lambda *args, **kwargs: connect(
            *args, **kwargs, factory=InterruptibleConnection))
        patch.setattr(AgentToolOpsStore, "_install_v2", staticmethod(interrupted_installer))
        patch.setattr(AgentToolOpsStore, "_load_or_create_key", interrupted_key)
        patch.setattr(AgentToolOpsStore, "_load_or_set_alias", interrupted_alias)
        with pytest.raises(Interruption):
            AgentToolOpsStore(path, opaque_key=KEY)

    assert path.stat().st_size == 0
    assert not Path(str(path) + "-wal").exists()
    assert not Path(str(path) + "-shm").exists()
    with AgentToolOpsStore(path, opaque_key=KEY) as retried:
        assert retried.workspace_alias == "kingdom_ops"
        assert retried.conn.execute("SELECT COUNT(*) FROM ops_meta").fetchone()[0] == 3
        assert retried.binding() is None
        retried.assert_initial_binding_allowed()
        _bind(retried)
    with AgentToolOpsStore(path, opaque_key=KEY) as reopened:
        assert reopened.binding().revision == 1


@pytest.mark.parametrize("legacy", [False, True])
def test_incomplete_recognized_schema_is_not_repaired_as_interrupted_initialization(
    tmp_path: Path, legacy: bool,
) -> None:
    path = tmp_path / "incomplete" / "ops.db"
    with AgentToolOpsStore(path, opaque_key=KEY):
        pass
    if legacy:
        _restore_v1_schema(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM ops_meta")
        conn.commit()
    finally:
        conn.close()
    os.chmod(path, 0o640)
    before = path.read_bytes()
    for operation in (AgentToolOpsStore, AgentToolOpsStore.preview_migration, AgentToolOpsStore.migrate_v1):
        with pytest.raises(DatabaseRoleError, match="metadata"):
            operation(path)
        assert path.read_bytes() == before
        assert stat.S_IMODE(path.stat().st_mode) == 0o640


@pytest.mark.parametrize("prior_state", ["pending", "unknown", "sent", "ignored", "withdrawn"])
def test_pause_resume_dedupes_clock_skewed_updates_across_reopens(
    store: AgentToolOpsStore, monkeypatch: Any, prior_state: str,
) -> None:
    from telegram_gateway.ops_service import TelegramOpsService

    _bind(store)
    processed = NOW + timedelta(seconds=10)
    update = _command(7, at=processed + timedelta(seconds=30))
    if prior_state == "ignored":
        update["message"]["from"]["is_bot"] = True
    elif prior_state == "withdrawn":
        update["message"]["date"] = int(NOW.timestamp())
    original = store.process_update_once(update, _service(store), polling_epoch=1, processed_at=processed)
    if prior_state in {"unknown", "sent"}:
        item = store.reply_item(original.reply_id)
        _claim_reply(store, item)
        store.finish_reply(item.reply_id, attempt_count=1, state=prior_state,
                           receipt_ref="telegram:42" if prior_state == "sent" else None)
    store.pause(paused_at=processed + timedelta(seconds=1))
    store.resume(resumed_at=processed + timedelta(seconds=2))
    monkeypatch.setattr(TelegramOpsService, "render_update", lambda *_: pytest.fail("withdrawn update rerendered"))

    with AgentToolOpsStore(store.path, opaque_key=KEY) as reopened:
        for elapsed in (2, 60, POLL_EPOCH_IDLE_SECONDS - 1):
            now = processed + timedelta(seconds=elapsed)
            state = reopened.prepare_poll(now=now)
            duplicate = reopened.process_update_once(update, _service(reopened),
                polling_epoch=state.epoch, processed_at=now)
            assert duplicate.duplicate is True
            assert (duplicate.polling_epoch, duplicate.disposition, duplicate.reply_id) == (
                original.polling_epoch, original.disposition, original.reply_id)
            assert reopened.poll_state().next_offset == 8
            assert reopened.poll_state().last_update_at == state.last_update_at
            assert reopened.list_replies(state="pending") == ()
        assert reopened.conn.execute("SELECT COUNT(*) FROM ops_update_dispositions").fetchone()[0] == 1
        if original.reply_id is not None:
            item = reopened.reply_item(original.reply_id)
            assert item.state == ("invalidated" if prior_state == "pending" else prior_state)
            with pytest.raises(BindingStateError, match="stale"):
                _claim_reply(reopened, item)


def test_repeated_resumption_does_not_permanently_dedupe_randomized_post_idle_id(
    store: AgentToolOpsStore,
) -> None:
    _bind(store)
    original = _stage_reply(store, 7)
    processed = NOW + timedelta(seconds=10)
    update = _command(7, at=processed + timedelta(seconds=30))
    for elapsed in (2, POLL_EPOCH_IDLE_SECONDS - 1):
        resumed = processed + timedelta(seconds=elapsed)
        store.pause(paused_at=resumed)
        store.resume(resumed_at=resumed)
        duplicate = store.process_update_once(update, _service(store),
            polling_epoch=store.poll_state().epoch, processed_at=resumed)
        assert duplicate.duplicate is True and duplicate.reply_id == original.reply_id
    later = processed + timedelta(days=8)
    state = store.prepare_poll(now=later)
    assert state.next_offset is None
    fresh = store.process_update_once(_command(7, at=later), _service(store),
        polling_epoch=state.epoch, processed_at=later)
    assert fresh.duplicate is False and fresh.reply_id != original.reply_id
    assert store.reply_item(fresh.reply_id).state == "pending"
    assert store.reply_item(original.reply_id).state == "invalidated"
    assert store.conn.execute("SELECT COUNT(*) FROM ops_update_dispositions").fetchone()[0] == 2


@pytest.mark.parametrize("source_state", ["staged", "committed", "seeded", "verification", "legacy_claim"])
def test_first_binding_rejects_unproven_source_state_read_only(
    store: AgentToolOpsStore, source_state: str,
) -> None:
    initial = CursorAnchor.genesis(EPOCH)
    if source_state in {"staged", "committed"}:
        raw = _event(1, ZERO_HASH, "a", payload={"version": 1})
        terminal = CursorAnchor(EPOCH, 1, raw["hash"])
        store.stage_page(current_anchor=initial, next_anchor=terminal, events=[raw])
        if source_state == "committed":
            store.commit_staged_cursor(terminal)
    elif source_state == "seeded":
        store.stage_page(current_anchor=initial, next_anchor=initial, events=[])
    elif source_state == "verification":
        store.record_journal_verification(outcome="valid", checked_at=NOW,
            journal_head_sequence=0, scope_code="full_collab_hash_chain")
    else:
        store.claim_update(7, claimed_at=NOW)
    before = "\n".join(store.conn.iterdump())
    changes = store.conn.total_changes
    statements = []
    store.conn.set_trace_callback(statements.append)
    try:
        with pytest.raises(BindingStateError, match="pristine source"):
            store.assert_initial_binding_allowed()
    finally:
        store.conn.set_trace_callback(None)
    assert statements and all(sql.lstrip().startswith("SELECT") for sql in statements)
    assert store.conn.in_transaction is False
    for source in ("source-A", "source-B", "synthetic-journal"):
        with pytest.raises(BindingStateError, match="pristine source"):
            _bind(store, source_binding=source)
    assert store.conn.total_changes == changes
    assert "\n".join(store.conn.iterdump()) == before
    assert store.binding() is None and store.poll_state() is None
    if source_state == "committed":
        assert store.status_snapshot().journal_head_sequence == 1
        assert len(store.list_tasks(limit=10)) == len(store.recent_events(limit=10)) == 1
    elif source_state == "verification":
        assert store.journal_verify().outcome == "valid"


def test_initial_binding_preflight_is_noop_for_bound_populated_or_paused_store(
    store: AgentToolOpsStore,
) -> None:
    assert store.assert_initial_binding_allowed() is None
    bound = _bind(store)
    raw = _event(1, ZERO_HASH, "a")
    terminal = CursorAnchor(EPOCH, 1, raw["hash"])
    store.stage_page(current_anchor=CursorAnchor.genesis(EPOCH), next_anchor=terminal, events=[raw])
    store.commit_staged_cursor(terminal)
    for paused in (False, True):
        if paused:
            store.pause(paused_at=NOW + timedelta(seconds=1))
        before = "\n".join(store.conn.iterdump())
        assert store.assert_initial_binding_allowed() is None
        assert "\n".join(store.conn.iterdump()) == before
        assert _bind(store) == bound
        with pytest.raises(BindingStateError, match="mismatch"):
            _bind(store, source_binding="source-B")


def test_initial_binding_rechecks_source_under_write_transaction(
    store: AgentToolOpsStore, monkeypatch: Any,
) -> None:
    store.assert_initial_binding_allowed()
    with AgentToolOpsStore(store.path, opaque_key=KEY) as observer:
        observer.record_journal_verification(outcome="unavailable", checked_at=NOW,
            journal_head_sequence=None, scope_code="full_collab_hash_chain_unavailable")
    checked = []
    guard = store.assert_initial_binding_allowed

    def observed_guard() -> None:
        checked.append(store.conn.in_transaction)
        guard()

    monkeypatch.setattr(store, "assert_initial_binding_allowed", observed_guard)
    with pytest.raises(BindingStateError, match="pristine source"):
        _bind(store)
    assert checked == [True]
    assert store.binding() is None and store.conn.in_transaction is False


@pytest.mark.parametrize("state", [None, "pending", "unknown", "sent", "failed", "inflight", "invalidated"])
def test_reply_cursor_discovers_all_states_beyond_twenty_with_stable_ties(
    store: AgentToolOpsStore, state: str | None, monkeypatch: Any,
) -> None:
    _bind(store)
    # Tied timestamps within each epoch, deliberately reverse-sorted reply IDs.
    # Offset/update ordering must not substitute for the immutable cursor tuple.
    ids = iter(f"{number:032x}" for number in range(150, 0, -1))
    monkeypatch.setattr("telegram_gateway.agenttool_ops.secrets.token_hex", lambda _: next(ids))
    for index in range(150):
        when = NOW + timedelta(seconds=10 if index < 25 else 20)
        disposition = store.process_update_once(_command(index, at=when), _service(store),
            polling_epoch=store.poll_state().epoch, processed_at=when)
        item = store.reply_item(disposition.reply_id)
        if index == 24:
            store.pause(paused_at=NOW + timedelta(seconds=11))
            store.resume(resumed_at=NOW + timedelta(seconds=12))
        elif index >= 25 and index % 5 != 0:
            _claim_reply(store, item)
            if index % 5 != 4:
                outcome = {1: "unknown", 2: "sent", 3: "failed"}[index % 5]
                store.finish_reply(item.reply_id, attempt_count=1, state=outcome,
                                   receipt_ref="telegram:42" if outcome == "sent" else None)
    expected = [row[0] for row in store.conn.execute(
        "SELECT reply_id FROM ops_replies WHERE (? IS NULL OR state = ?) ORDER BY queued_at, reply_id",
        (state, state))]
    before = "\n".join(store.conn.iterdump())
    assert len(expected) == (150 if state is None else 25)
    assert [item.reply_id for item in store.list_replies(state=state)] == expected[:20]
    seen = []
    cursor = None
    for _ in range(9):
        page = store.list_replies(state=state, after_reply_id=cursor)
        assert len(page) <= 20
        if not page:
            break
        seen.extend(item.reply_id for item in page)
        cursor = page[-1].reply_id
    else:
        pytest.fail("bounded reply discovery did not terminate")
    assert seen == expected and len(seen) == len(set(seen))
    assert "\n".join(store.conn.iterdump()) == before
    assert len(store.list_replies(limit=100)) == 100


def test_reply_cursor_uses_timestamp_before_id_and_survives_filter_changes(
    store: AgentToolOpsStore, monkeypatch: Any,
) -> None:
    _bind(store)
    ids = iter(["f" * 32, "a" * 32, "b" * 32])
    monkeypatch.setattr("telegram_gateway.agenttool_ops.secrets.token_hex", lambda _: next(ids))
    items = []
    for index, elapsed in enumerate((10, 20, 30)):
        when = NOW + timedelta(seconds=elapsed)
        disposition = store.process_update_once(_command(index, at=when), _service(store),
            polling_epoch=1, processed_at=when)
        items.append(store.reply_item(disposition.reply_id))
    first, second, third = items
    assert store.list_replies(limit=1) == (first,)
    _claim_reply(store, first)
    store.finish_reply(first.reply_id, attempt_count=1, state="sent", receipt_ref="telegram:42")
    assert store.list_replies(state="pending", after_reply_id=first.reply_id, limit=1) == (second,)
    assert store.list_replies(after_reply_id=second.reply_id) == (third,)
    assert store.list_replies(after_reply_id=third.reply_id) == ()
    assert store.list_replies(state="sent", after_reply_id=first.reply_id) == ()


@pytest.mark.parametrize("cursor", ["", " ", "not-a-reply", "rpl_" + "0" * 32, True, 7, []])
def test_reply_cursor_rejects_invalid_or_nonexistent_reference(
    store: AgentToolOpsStore, cursor: Any,
) -> None:
    before = "\n".join(store.conn.iterdump())
    with pytest.raises(ValueError, match="after_reply_id"):
        store.list_replies(after_reply_id=cursor)
    assert "\n".join(store.conn.iterdump()) == before


@pytest.mark.parametrize("options", [
    {"limit": 0}, {"limit": 101}, {"limit": True}, {"limit": "20"},
    {"state": "all"}, {"state": ""}, {"state": []},
])
def test_reply_pages_reject_invalid_limits_and_filters(store: AgentToolOpsStore, options: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        store.list_replies(**options)


def _existing_file_snapshot(directory: Path) -> dict[str, Any]:
    """Bytes and durable file metadata, excluding read-induced access times."""
    result = {}
    for path in (directory, *sorted(directory.iterdir())):
        info = path.lstat()
        result[path.name] = (
            info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            path.read_bytes() if stat.S_ISREG(info.st_mode) else None,
            os.readlink(path) if stat.S_ISLNK(info.st_mode) else None,
        )
    return result


@pytest.mark.parametrize("readonly", [True, False])
@pytest.mark.parametrize("state", ["missing", "missing-parent", "empty", "directory", "fifo", "garbage"])
def test_open_existing_rejects_absent_or_nonstores_without_creation(
    tmp_path: Path, readonly: bool, state: str,
) -> None:
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    path = parent / "ops.db"
    if state == "missing-parent":
        path = parent / "absent" / "ops.db"
    elif state == "empty":
        path.touch(mode=0o600)
    elif state == "directory":
        path.mkdir(mode=0o700)
    elif state == "fifo":
        os.mkfifo(path, mode=0o600)
    elif state == "garbage":
        path.write_bytes(b"not-a-sqlite-database-private-sentinel")
        path.chmod(0o600)
    before = _existing_file_snapshot(parent)
    with pytest.raises(DatabaseRoleError) as error:
        AgentToolOpsStore.open_existing(path, readonly=readonly)
    assert str(path) not in str(error.value)
    assert "private-sentinel" not in str(error.value)
    assert _existing_file_snapshot(parent) == before


@pytest.mark.parametrize("readonly", [True, False])
@pytest.mark.parametrize("state", [
    "research", "mixed", "wrong-role", "v1", "legacy-v1", "missing-key", "missing-alias",
    "missing-role", "extra-meta", "invalid-key", "invalid-alias", "text-role", "trigger", "index",
])
def test_open_existing_rejects_exact_role_and_metadata_failures_before_mutable_open(
    tmp_path: Path, monkeypatch: Any, readonly: bool, state: str,
) -> None:
    path = tmp_path / "private" / "ops.db"
    if state == "research":
        path.parent.mkdir(mode=0o700)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE research_private (value TEXT)")
        conn.execute("INSERT INTO research_private VALUES ('private-research-sentinel')")
        conn.commit()
        conn.close()
    else:
        with AgentToolOpsStore(path, opaque_key=KEY):
            pass
        if state in {"v1", "legacy-v1"}:
            _restore_v1_schema(path, marker=state == "v1")
        else:
            mutations = {
                "mixed": "CREATE TABLE research_private (value TEXT)",
                "wrong-role": "UPDATE ops_meta SET value = X'00' WHERE key = 'database_role'",
                "missing-key": "DELETE FROM ops_meta WHERE key = 'opaque_key'",
                "missing-alias": "DELETE FROM ops_meta WHERE key = 'workspace_alias'",
                "missing-role": "DELETE FROM ops_meta WHERE key = 'database_role'",
                "extra-meta": "INSERT INTO ops_meta VALUES ('unexpected', X'00')",
                "invalid-key": "UPDATE ops_meta SET value = X'00' WHERE key = 'opaque_key'",
                "invalid-alias": "UPDATE ops_meta SET value = X'FF' WHERE key = 'workspace_alias'",
                "text-role": "UPDATE ops_meta SET value = CAST(value AS TEXT) WHERE key = 'database_role'",
                "trigger": "CREATE TRIGGER tampered AFTER INSERT ON telegram_updates BEGIN DELETE FROM telegram_updates; END",
                "index": "DROP INDEX idx_ops_outbox_state",
            }
            conn = sqlite3.connect(path)
            conn.execute(mutations[state])
            conn.commit()
            conn.close()
    path.chmod(0o600)
    before = _existing_file_snapshot(path.parent)
    connect = sqlite3.connect
    opened = []

    def preflight_only(uri: str, /, **options: Any) -> sqlite3.Connection:
        opened.append(uri)
        assert uri.endswith("?mode=ro&immutable=1")
        return connect(uri, **options)

    monkeypatch.setattr(sqlite3, "connect", preflight_only)
    error_class = MigrationRequiredError if state in {"v1", "legacy-v1"} else DatabaseRoleError
    with pytest.raises(error_class) as error:
        AgentToolOpsStore.open_existing(path, readonly=readonly)
    assert len(opened) == 1
    assert str(path) not in str(error.value)
    assert "research_private" not in str(error.value)
    assert _existing_file_snapshot(path.parent) == before


@pytest.mark.parametrize("readonly", [True, False])
@pytest.mark.parametrize("unsafe", [
    "file-mode", "directory-mode", "file-owner", "directory-owner", "file-symlink",
    "ancestor-symlink", "parent-traversal", "file-hardlink",
    "wal-mode", "shm-mode", "journal-mode", "wal-owner", "shm-owner", "journal-owner",
    "wal-symlink", "shm-symlink", "journal-symlink", "wal-directory", "shm-fifo",
    "journal-hot",
])
def test_open_existing_rejects_unsafe_paths_and_sidecars_before_sqlite(
    tmp_path: Path, monkeypatch: Any, readonly: bool, unsafe: str,
) -> None:
    path = tmp_path / "private" / "ops.db"
    with AgentToolOpsStore(path, opaque_key=KEY):
        pass
    requested = path
    target = path
    if unsafe.startswith(("wal-", "shm-", "journal-")):
        suffix = unsafe.split("-")[0]
        target = Path(str(path) + "-" + suffix)
        if unsafe.endswith("directory"):
            target.mkdir(mode=0o700)
        elif unsafe.endswith("fifo"):
            os.mkfifo(target, mode=0o600)
        elif unsafe.endswith("symlink"):
            target.symlink_to(path)
        else:
            target.touch(mode=0o600)
            if unsafe.endswith("mode"):
                target.chmod(0o640)
            elif unsafe == "journal-hot":
                target.write_bytes(b"unrecovered journal")
    elif unsafe == "file-mode":
        path.chmod(0o640)
    elif unsafe == "directory-mode":
        path.parent.chmod(0o750)
    elif unsafe == "file-symlink":
        requested = path.parent / "link.db"
        requested.symlink_to(path)
    elif unsafe == "ancestor-symlink":
        link = tmp_path / "link"
        link.symlink_to(path.parent, target_is_directory=True)
        requested = link / "ops.db"
    elif unsafe == "parent-traversal":
        requested = path.parent / ".." / "private" / "ops.db"
    elif unsafe == "file-hardlink":
        os.link(path, path.parent / "hardlink.db")
    if unsafe.endswith("owner"):
        target = path.parent if unsafe == "directory-owner" else target
        real_lstat = Path.lstat

        def wrong_owner(candidate: Path, *args: Any, **kwargs: Any) -> Any:
            result = real_lstat(candidate, *args, **kwargs)
            if candidate == target:
                fields = list(result)
                fields[4] = os.geteuid() + 1
                return os.stat_result(fields)
            return result

        monkeypatch.setattr(Path, "lstat", wrong_owner)
    before = _existing_file_snapshot(path.parent)
    monkeypatch.setattr(sqlite3, "connect", lambda *_a, **_k: pytest.fail("unsafe SQLite open"))
    with pytest.raises((PermissionError, DatabaseRoleError)) as error:
        AgentToolOpsStore.open_existing(requested, readonly=readonly)
    assert str(path) not in str(error.value)
    assert _existing_file_snapshot(path.parent) == before


@pytest.mark.parametrize("readonly", [None, 0, 1, "false", "true", [], {}])
def test_open_existing_requires_strict_boolean_before_filesystem_access(
    monkeypatch: Any, readonly: Any,
) -> None:
    monkeypatch.setattr(Path, "lstat", lambda *_a, **_k: pytest.fail("unexpected filesystem access"))
    with pytest.raises(ValueError, match="readonly must be a boolean"):
        AgentToolOpsStore.open_existing("/unopened/ops.db", readonly=readonly)


@pytest.mark.parametrize("readonly", [True, False])
@pytest.mark.parametrize("bound_state", ["unbound", "active", "paused"])
def test_open_existing_bypasses_initialization_and_inspects_unbound_or_paused(
    tmp_path: Path, monkeypatch: Any, readonly: bool, bound_state: str,
) -> None:
    path = tmp_path / "private" / "ops ?#% encoded.db"
    with AgentToolOpsStore(path, workspace_alias="Stored_Alias", opaque_key=KEY) as created:
        if bound_state != "unbound":
            _bind(created)
            _stage_reply(created)
        anchor = CursorAnchor.genesis(EPOCH)
        created.stage_page(current_anchor=anchor, next_anchor=anchor, events=[])
        if bound_state == "paused":
            created.pause(paused_at=NOW + timedelta(seconds=20))
        expected_binding = created.binding()
        expected_poll = created.poll_state()
        expected_replies = created.list_replies()
        before_rows = "\n".join(created.conn.iterdump())
    before_main = _existing_file_snapshot(path.parent)[path.name]
    opened, statements = [], []
    connect = sqlite3.connect

    def checked_connect(uri: str, /, **options: Any) -> sqlite3.Connection:
        opened.append(uri)
        assert options["uri"] is True
        assert options.get("check_same_thread", True) is True
        connection = connect(uri, **options)
        connection.set_trace_callback(statements.append)
        return connection

    def no_initialization(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("existing access must not initialize, migrate, generate metadata or chmod")

    monkeypatch.setattr(sqlite3, "connect", checked_connect)
    for method in ("__init__", "_install_v2", "_load_or_create_key", "_load_or_set_alias", "_secure_files"):
        monkeypatch.setattr(AgentToolOpsStore, method, no_initialization)
    monkeypatch.setattr(Path, "chmod", no_initialization)
    monkeypatch.setattr(os, "chmod", no_initialization)
    with AgentToolOpsStore.open_existing(path, readonly=readonly) as inspected:
        assert inspected.path == path
        assert inspected.workspace_alias == "Stored_Alias"
        assert inspected._opaque_key == KEY
        assert inspected.binding() == expected_binding
        assert inspected.poll_state() == expected_poll
        assert inspected.list_replies() == expected_replies
        assert inspected.committed_anchor() == anchor
        assert inspected.staged_anchor() is None
        assert inspected.status_snapshot().journal_head_sequence == 0
        assert inspected.list_tasks(limit=20) == ()
        assert inspected.recent_events(limit=20) == ()
        assert inspected.journal_verify().outcome == "unavailable"
        assert inspected.conn.in_transaction is readonly
        assert inspected.conn.total_changes == 0
        assert "\n".join(inspected.conn.iterdump()) == before_rows
        if not readonly:
            assert inspected.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            assert inspected.conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        inspected.binding()
    assert opened[0].endswith("?mode=ro&immutable=1")
    assert opened[1].endswith("?mode=ro")
    assert len(opened) == (2 if readonly else 3)
    if not readonly:
        assert opened[2].endswith("?mode=rw")
    assert not any("journal_mode=" in sql.lower() or "wal_checkpoint" in sql.lower() for sql in statements)
    assert _existing_file_snapshot(path.parent)[path.name] == before_main


def test_open_existing_readonly_refuses_sql_and_store_mutations_without_losing_snapshot(
    store: AgentToolOpsStore,
) -> None:
    _bind(store)
    item = _stage_reply(store)
    before = "\n".join(store.conn.iterdump())
    with AgentToolOpsStore.open_existing(store.path) as reader:
        operations = [
            lambda: reader.conn.execute("DELETE FROM ops_replies"),
            lambda: reader.conn.execute("UPDATE ops_meta SET value = X'00'"),
            lambda: reader.conn.execute("CREATE TABLE extra (value TEXT)"),
            lambda: reader.claim_update(101),
            lambda: reader.prepare_poll(now=NOW + timedelta(days=8)),
            lambda: _claim_reply(reader, item),
            lambda: reader.process_update_once(_command(101), _service(reader), polling_epoch=1),
            reader.pause, reader.resume, reader.mark_interrupted_replies,
            lambda: _bind(reader),
            lambda: reader.record_journal_verification(outcome="valid", checked_at=NOW,
                journal_head_sequence=0, scope_code="full_collab_hash_chain"),
            lambda: reader.stage_page(current_anchor=CursorAnchor.genesis(EPOCH),
                next_anchor=CursorAnchor.genesis(EPOCH), events=[]),
            lambda: reader.commit_staged_cursor(CursorAnchor.genesis(EPOCH)),
        ]
        for operation in operations:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                operation()
            assert reader.conn.in_transaction
            assert reader.list_replies() == (item,)
            assert reader.conn.total_changes == 0
        # SQL read-only access remains enforced even if a caller disables the
        # connection-local convenience guard or ends the held read transaction.
        reader.conn.rollback()
        reader.conn.execute("PRAGMA query_only=OFF")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            reader.conn.execute("DELETE FROM ops_replies")
    assert "\n".join(store.conn.iterdump()) == before


def test_open_existing_reads_current_wal_and_keeps_one_coherent_read_snapshot(
    store: AgentToolOpsStore,
) -> None:
    _bind(store)
    store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    item = _stage_reply(store)
    wal = Path(str(store.path) + "-wal")
    assert wal.stat().st_size > 0
    main_before, wal_before = store.path.read_bytes(), wal.read_bytes()
    with AgentToolOpsStore.open_existing(store.path) as reader:
        # The queued reply, offset and attempt state exist only in the WAL.
        assert reader.list_replies() == (item,)
        assert reader.poll_state().next_offset == 101
        _claim_reply(store, item)
        assert reader.reply_item(item.reply_id) == item
        assert reader.reply_attempts(item.reply_id) == ()
        store.pause(paused_at=NOW + timedelta(seconds=20))
        assert reader.poll_state().state == "active"
        assert reader.reply_item(item.reply_id).state == "pending"
        with AgentToolOpsStore.open_existing(store.path) as later:
            assert later.poll_state().state == "paused"
            assert later.reply_item(item.reply_id).state == "unknown"
            assert later.reply_attempts(item.reply_id)[0]["error_code"] == "paused"
    assert store.path.read_bytes() == main_before
    assert wal.read_bytes().startswith(wal_before)


@pytest.mark.parametrize("readonly", [True, False])
def test_open_existing_is_conservatively_unavailable_for_wal_only_schema(
    tmp_path: Path, readonly: bool,
) -> None:
    with AgentToolOpsStore(tmp_path / "template" / "ops.db", opaque_key=KEY) as template:
        schema_and_metadata = "\n".join(template.conn.iterdump())
    path = tmp_path / "wal-only" / "ops.db"
    path.parent.mkdir(mode=0o700)
    producer = sqlite3.connect(path, isolation_level=None)
    try:
        producer.execute("PRAGMA journal_mode=WAL")
        producer.executescript(schema_and_metadata)
        for suffix in ("", "-wal", "-shm"):
            Path(str(path) + suffix).chmod(0o600)
        before = _existing_file_snapshot(path.parent)
        with pytest.raises(DatabaseRoleError):
            AgentToolOpsStore.open_existing(path, readonly=readonly)
        assert _existing_file_snapshot(path.parent) == before
        # A checkpoint is explicit fixture setup, never requested by the opener.
        producer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with AgentToolOpsStore.open_existing(path, readonly=readonly) as admitted:
            assert admitted.binding() is None
            assert admitted.workspace_alias == "kingdom_ops"
    finally:
        producer.close()


@pytest.mark.parametrize("readonly", [True, False])
def test_open_existing_uses_last_committed_state_while_a_writer_holds_uncommitted_changes(
    store: AgentToolOpsStore, readonly: bool,
) -> None:
    _bind(store)
    item = _stage_reply(store)
    store.conn.execute("BEGIN IMMEDIATE")
    store.conn.execute("CREATE TABLE uncommitted_foreign (value TEXT)")
    store.conn.execute("UPDATE ops_meta SET value = X'00' WHERE key = 'database_role'")
    try:
        with AgentToolOpsStore.open_existing(store.path, readonly=readonly) as inspected:
            assert inspected.list_replies() == (item,)
            assert inspected.poll_state().state == "active"
            if not readonly:
                inspected.conn.execute("PRAGMA busy_timeout=10")
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    inspected.pause()
                assert not inspected.conn.in_transaction
    finally:
        store.conn.rollback()
    assert store.reply_item(item.reply_id) == item


@pytest.mark.parametrize("readonly", [True, False])
@pytest.mark.parametrize("mutation", [
    "CREATE TABLE research_private (value TEXT)",
    "UPDATE ops_meta SET value = X'00' WHERE key = 'database_role'",
    "DELETE FROM ops_meta WHERE key = 'opaque_key'",
])
def test_open_existing_checks_wal_role_and_schema_before_any_rw_connection(
    store: AgentToolOpsStore, monkeypatch: Any, readonly: bool, mutation: str,
) -> None:
    store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    main_before = store.path.read_bytes()
    store.conn.execute(mutation)
    assert store.path.read_bytes() == main_before
    wal = Path(str(store.path) + "-wal")
    before = _existing_file_snapshot(store.path.parent)
    connect = sqlite3.connect
    opened = []

    def readonly_only(uri: str, /, **options: Any) -> sqlite3.Connection:
        opened.append(uri)
        assert "?mode=ro" in uri and "?mode=rw" not in uri
        return connect(uri, **options)

    monkeypatch.setattr(sqlite3, "connect", readonly_only)
    with pytest.raises(DatabaseRoleError):
        AgentToolOpsStore.open_existing(store.path, readonly=readonly)
    assert len(opened) == 2
    after = _existing_file_snapshot(store.path.parent)
    assert after[store.path.name] == before[store.path.name]
    assert after[wal.name] == before[wal.name]
    # The main-file-admitted store may incur SQLite shm read-lock accounting.
    # It must not initialize metadata, change WAL contents or open mode=rw.
    assert set(after) == set(before)


def test_open_existing_readwrite_reuses_fencing_transactions_without_permission_repair(
    store: AgentToolOpsStore, monkeypatch: Any,
) -> None:
    _bind(store)
    item = _stage_reply(store)
    monkeypatch.setattr(Path, "chmod", lambda *_a, **_k: pytest.fail("permission repair"))
    monkeypatch.setattr(os, "chmod", lambda *_a, **_k: pytest.fail("permission repair"))
    with AgentToolOpsStore.open_existing(store.path, readonly=False) as writer:
        assert not writer.conn.in_transaction
        with pytest.raises(BindingStateError, match="stale"):
            writer.claim_reply(item.reply_id, payload_digest="sha256:" + "0" * 64, binding_revision=1)
        assert writer.reply_item(item.reply_id) == item
        claimed = _claim_reply(writer, item)
        assert claimed.state == "inflight" and claimed.attempt_count == 1
        with pytest.raises(DeliveryStateError, match="stale"):
            writer.finish_reply(item.reply_id, attempt_count=2, state="unknown")
        writer.finish_reply(item.reply_id, attempt_count=1, state="unknown", error_code="interrupted")
        writer.reconcile_reply(item.reply_id, attempt_count=1, outcome="sent",
            reconciliation_ref="fixture:observed", receipt_ref="telegram:42")
        writer.pause(paused_at=NOW + timedelta(seconds=20))
    assert store.reply_item(item.reply_id).state == "sent"
    assert store.reply_attempts(item.reply_id)[0]["state"] == "unknown"
    assert store.reply_reconciliations(item.reply_id)[0]["receipt_ref"] == "telegram:42"
    assert store.poll_state().state == "paused"


@pytest.mark.parametrize("readonly", [True, False])
def test_open_existing_thread_local_concurrent_connections_and_atomic_claims(
    store: AgentToolOpsStore, readonly: bool,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    _bind(store)
    item = _stage_reply(store)
    barrier = Barrier(2)

    def worker() -> str:
        with AgentToolOpsStore.open_existing(store.path, readonly=readonly) as local:
            barrier.wait(timeout=5)
            if readonly:
                assert local.list_replies() == (item,)
                return local.poll_state().state
            try:
                return _claim_reply(local, item).state
            except DeliveryStateError:
                return "already-claimed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    if readonly:
        assert results == ["active", "active"]
        assert store.reply_attempts(item.reply_id) == ()
    else:
        assert sorted(results) == ["already-claimed", "inflight"]
        assert len(store.reply_attempts(item.reply_id)) == 1


def test_open_existing_preserves_sqlite_thread_affinity_and_context_cleanup(store: AgentToolOpsStore) -> None:
    from concurrent.futures import ThreadPoolExecutor

    with AgentToolOpsStore.open_existing(store.path) as reader:
        with ThreadPoolExecutor(max_workers=1) as pool:
            for operation in (reader.binding, reader.close):
                with pytest.raises(sqlite3.ProgrammingError, match="same thread"):
                    pool.submit(operation).result(timeout=5)
        assert reader.binding() is None
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        reader.binding()
    with pytest.raises(RuntimeError, match="synthetic"):
        with AgentToolOpsStore.open_existing(store.path) as interrupted:
            raise RuntimeError("synthetic")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        interrupted.binding()


@pytest.mark.parametrize("readonly", [True, False])
def test_open_existing_busy_snapshot_closes_connections_with_bounded_error(
    tmp_path: Path, monkeypatch: Any, readonly: bool,
) -> None:
    path = tmp_path / "private" / "ops.db"
    with AgentToolOpsStore(path):
        pass
    writer = sqlite3.connect(path, isolation_level=None)
    writer.execute("PRAGMA journal_mode=DELETE")
    writer.execute("BEGIN EXCLUSIVE")
    before = _existing_file_snapshot(path.parent)
    connect = sqlite3.connect
    connections = []

    def fast_connection(uri: str, /, **options: Any) -> sqlite3.Connection:
        # Keep the production timeout finite, shorten it for this lock fixture.
        assert options.get("timeout", 2.0) <= 2.0
        options["timeout"] = 0.01
        connection = connect(uri, **options)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", fast_connection)
    try:
        with pytest.raises(DatabaseRoleError) as error:
            AgentToolOpsStore.open_existing(path, readonly=readonly)
        assert str(path) not in str(error.value)
        assert _existing_file_snapshot(path.parent) == before
        for connection in connections:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connection.execute("SELECT 1")
    finally:
        writer.rollback()
        writer.close()


def test_open_existing_revalidates_path_changes_before_sqlite_setup(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    import telegram_gateway.agenttool_ops as module

    path = tmp_path / "private" / "ops.db"
    with AgentToolOpsStore(path):
        pass
    inspect = module._inspect_existing_database
    replacement = path.parent / "replacement.db"
    replacement.write_bytes(path.read_bytes())
    replacement.chmod(0o600)

    def replace_after_preflight(candidate: Path) -> str:
        version = inspect(candidate)
        os.replace(replacement, candidate)
        return version

    monkeypatch.setattr(module, "_inspect_existing_database", replace_after_preflight)
    with pytest.raises(DatabaseRoleError, match="changed"):
        AgentToolOpsStore.open_existing(path)
    assert not Path(str(path) + "-wal").exists()
    assert not Path(str(path) + "-shm").exists()


def test_open_existing_rw_is_existing_only_even_when_validated_path_disappears(
    store: AgentToolOpsStore, monkeypatch: Any,
) -> None:
    connect = sqlite3.connect
    connections = []
    moved = store.path.with_name("preserved.db")

    def remove_before_rw(uri: str, /, **options: Any) -> sqlite3.Connection:
        if uri.endswith("?mode=rw"):
            store.path.rename(moved)
        connection = connect(uri, **options)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", remove_before_rw)
    try:
        with pytest.raises(DatabaseRoleError, match="unavailable"):
            AgentToolOpsStore.open_existing(store.path, readonly=False)
        assert not store.path.exists()
        assert moved.exists()
        for connection in connections:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connection.execute("SELECT 1")
    finally:
        moved.rename(store.path)


def test_open_existing_rw_rechecks_permissions_and_role_under_each_mutation(
    store: AgentToolOpsStore,
) -> None:
    _bind(store)
    item = _stage_reply(store)
    with AgentToolOpsStore.open_existing(store.path, readonly=False) as writer:
        store.path.chmod(0o640)
        with pytest.raises(PermissionError):
            writer.pause()
        assert stat.S_IMODE(store.path.stat().st_mode) == 0o640
        store.path.chmod(0o600)
        store.conn.execute("UPDATE ops_meta SET value = X'00' WHERE key = 'database_role'")
        with pytest.raises(DatabaseRoleError):
            _claim_reply(writer, item)
        assert not writer.conn.in_transaction
        assert writer.reply_item(item.reply_id) == item

