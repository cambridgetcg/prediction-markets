from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

from telegram_gateway.lifecycle import (
    LIFECYCLE_SCHEMA,
    LIFECYCLE_SCOPE,
    MAX_RECORD_BYTES,
    LifecycleEventError,
    LifecycleImportFailure,
    import_s012_lifecycle_jsonl,
    validate_lifecycle_event,
)
from telegram_gateway.envelope import build_s012_envelope
from telegram_gateway.store import GatewayStore


class FakeLifecycleStore:
    def __init__(self) -> None:
        self.state: dict[str, str] = {}
        self.events: list[dict[str, Any]] = []
        self.seen: set[str] = set()
        self.outcomes: dict[str, str] = {}
        self.failure: Exception | None = None

    def get_state(self, key: str) -> str | None:
        return self.state.get(key)

    def set_state(self, key: str, value: str) -> None:
        self.state[key] = value

    def apply_signal_lifecycle(self, event: Mapping[str, Any]) -> str:
        if self.failure is not None:
            raise self.failure
        copied = dict(event)
        self.events.append(copied)
        event_id = str(copied["event_id"])
        configured = self.outcomes.get(event_id)
        if configured is not None:
            return configured
        if event_id in self.seen:
            return "duplicate"
        self.seen.add(event_id)
        return "applied"


def event_id_for(event: Mapping[str, Any]) -> str:
    material = dict(event)
    material.pop("event_id", None)
    canonical = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "s012-life-" + hashlib.sha256(canonical).hexdigest()[:32]


def lifecycle_event(
    *,
    signal_id: str = "signal-lifecycle-0001",
    revision: int = 1,
    previous_status: str = "PENDING",
    status: str = "APPROVED",
    occurred_at: str = "2026-09-02T12:00:00.000000Z",
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema": LIFECYCLE_SCHEMA,
        "signal_id": signal_id,
        "revision": revision,
        "previous_status": previous_status,
        "status": status,
        "occurred_at": occurred_at,
        "actor_kind": "local_operator",
        "reason_code": "manual_review",
        "scope": LIFECYCLE_SCOPE,
        "execution_allowed": False,
    }
    event["event_id"] = event_id_for(event)
    return event


def reseal(event: dict[str, Any]) -> dict[str, Any]:
    event["event_id"] = event_id_for(event)
    return event


def append_event(path: Path, event: Mapping[str, Any]) -> bytes:
    payload = (
        json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    with path.open("ab") as handle:
        handle.write(payload)
    return payload


def only_cursor(store: FakeLifecycleStore) -> dict[str, Any]:
    assert len(store.state) == 1
    return json.loads(next(iter(store.state.values())))


def test_validate_exact_producer_event_and_content_address() -> None:
    event = lifecycle_event()
    assert validate_lifecycle_event(event) == event

    tampered = dict(event)
    tampered["reason_code"] = "source_correction"
    with pytest.raises(LifecycleEventError, match="event_id does not match"):
        validate_lifecycle_event(tampered)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema", "s012.signal-lifecycle/9.9", "schema"),
        ("scope", "live_execution", "distribution-only"),
        ("execution_allowed", 0, "boolean false"),
        ("revision", True, "positive SQLite integer"),
        ("previous_status", "REJECTED", "transition"),
        ("actor_kind", "Local Operator", "machine label"),
        ("reason_code", "x" * 65, "UTF-8 byte limit"),
        ("occurred_at", "2026-09-02T12:00:00+00:00", "canonical UTC"),
        ("signal_id", "雪" * 43, "UTF-8 byte limit"),
    ],
)
def test_validate_rejects_noncanonical_fields(
    field: str, value: Any, message: str
) -> None:
    event = lifecycle_event()
    event[field] = value
    reseal(event)
    with pytest.raises(LifecycleEventError, match=message):
        validate_lifecycle_event(event)


def test_validate_rejects_missing_extra_and_lone_surrogate() -> None:
    missing = lifecycle_event()
    del missing["actor_kind"]
    with pytest.raises(LifecycleEventError, match="missing required keys"):
        validate_lifecycle_event(missing)

    extra = lifecycle_event()
    extra["wallet_private_key"] = "must-not-exist"
    with pytest.raises(LifecycleEventError, match="unsupported keys"):
        validate_lifecycle_event(extra)

    surrogate = lifecycle_event()
    surrogate["signal_id"] = "signal-\ud800"
    with pytest.raises(LifecycleEventError, match="valid UTF-8"):
        validate_lifecycle_event(surrogate)


def test_backfill_applies_and_deduplicates_stable_event_ids(tmp_path: Path) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    event = lifecycle_event()
    line = json.dumps(event, separators=(",", ":")) + "\n"
    source.write_text(line + line)
    store = FakeLifecycleStore()

    result = import_s012_lifecycle_jsonl(source, store, backfill=True)

    assert result.applied == 1
    assert result.duplicates == 1
    assert result.complete_records == 2
    assert result.cursor == source.stat().st_size
    assert len(store.events) == 2


def test_default_bootstrap_ignores_history_then_reads_only_appends(
    tmp_path: Path,
) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    source.write_text(json.dumps(lifecycle_event()) + "\n")
    store = FakeLifecycleStore()

    first = import_s012_lifecycle_jsonl(source, store)
    assert first.bootstrapped
    assert first.applied == 0
    assert store.events == []

    appended = lifecycle_event(
        revision=2,
        previous_status="APPROVED",
        status="REVOKED",
        occurred_at="2026-09-02T12:01:00.000000Z",
    )
    appended["reason_code"] = "manual_revocation"
    reseal(appended)
    append_event(source, appended)
    second = import_s012_lifecycle_jsonl(source, store)
    assert second.applied == 1
    assert store.events == [appended]


def test_partial_utf8_row_is_retried_from_its_start(tmp_path: Path) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    source.write_bytes(b"")
    store = FakeLifecycleStore()
    import_s012_lifecycle_jsonl(source, store)

    event = lifecycle_event(signal_id="signal-snow-雪")
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    split = payload.index("雪".encode("utf-8")) + 1
    source.write_bytes(payload[:split])
    partial = import_s012_lifecycle_jsonl(source, store)
    assert partial.trailing_partial_ignored
    assert partial.cursor == 0
    assert store.events == []

    with source.open("ab") as handle:
        handle.write(payload[split:] + b"\n")
    complete = import_s012_lifecycle_jsonl(source, store)
    assert complete.applied == 1
    assert store.events == [event]


def test_bootstrap_inside_append_discards_only_that_historical_row(
    tmp_path: Path,
) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    historical = json.dumps(lifecycle_event(), separators=(",", ":")).encode()
    split = len(historical) // 2
    source.write_bytes(historical[:split])
    store = FakeLifecycleStore()

    first = import_s012_lifecycle_jsonl(source, store)
    assert first.bootstrapped
    assert first.trailing_partial_ignored

    new_event = lifecycle_event(signal_id="signal-lifecycle-0002")
    with source.open("ab") as handle:
        handle.write(historical[split:] + b"\n")
        handle.write(json.dumps(new_event, separators=(",", ":")).encode() + b"\n")
    second = import_s012_lifecycle_jsonl(source, store)
    assert second.applied == 1
    assert second.complete_records == 1
    assert store.events == [new_event]


def test_duplicate_json_key_fails_and_pins_cursor_at_bad_row(tmp_path: Path) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    source.write_bytes(b"")
    store = FakeLifecycleStore()
    import_s012_lifecycle_jsonl(source, store)
    good_line = append_event(source, lifecycle_event())
    bad_start = len(good_line)
    with source.open("ab") as handle:
        handle.write(b'{"schema":"one","schema":"two"}\n')

    with pytest.raises(LifecycleImportFailure, match="duplicate key"):
        import_s012_lifecycle_jsonl(source, store)

    assert only_cursor(store)["cursor"] == bad_start
    assert len(store.events) == 1
    with pytest.raises(LifecycleImportFailure, match="byte"):
        import_s012_lifecycle_jsonl(source, store)
    assert only_cursor(store)["cursor"] == bad_start


def test_known_quarantine_and_orphan_dispositions_are_counted(tmp_path: Path) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    quarantined = lifecycle_event(signal_id="signal-gap-0001", revision=3)
    orphan = lifecycle_event(signal_id="signal-missing-0001")
    source.write_bytes(b"")
    store = FakeLifecycleStore()
    import_s012_lifecycle_jsonl(source, store)
    store.outcomes[quarantined["event_id"]] = "quarantined"
    store.outcomes[orphan["event_id"]] = "orphan"
    append_event(source, quarantined)
    append_event(source, orphan)

    result = import_s012_lifecycle_jsonl(source, store)

    assert result.quarantined == 1
    assert result.orphans == 1
    assert result.complete_records == 2
    assert result.cursor == source.stat().st_size


def test_unrecognized_or_failed_store_outcome_does_not_skip_row(tmp_path: Path) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    source.write_bytes(b"")
    store = FakeLifecycleStore()
    import_s012_lifecycle_jsonl(source, store)
    event = lifecycle_event()
    append_event(source, event)
    store.outcomes[event["event_id"]] = "ignored"

    with pytest.raises(LifecycleImportFailure, match="invalid outcome"):
        import_s012_lifecycle_jsonl(source, store)
    assert only_cursor(store)["cursor"] == 0

    store.outcomes.clear()
    store.failure = RuntimeError("synthetic database failure")
    with pytest.raises(LifecycleImportFailure, match="store failed"):
        import_s012_lifecycle_jsonl(source, store)
    assert only_cursor(store)["cursor"] == 0


def test_source_replacement_is_fail_closed_until_explicit_backfill(
    tmp_path: Path,
) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    source.write_bytes(b"")
    store = FakeLifecycleStore()
    import_s012_lifecycle_jsonl(source, store)
    append_event(source, lifecycle_event())
    assert import_s012_lifecycle_jsonl(source, store).applied == 1
    saved_state = dict(store.state)

    replacement = tmp_path / "replacement.jsonl"
    replacement_event = lifecycle_event(signal_id="signal-replacement-0001")
    append_event(replacement, replacement_event)
    os.replace(replacement, source)

    reset = import_s012_lifecycle_jsonl(source, store)
    assert reset.source_reset
    assert reset.applied == 0
    assert store.state == saved_state
    assert replacement_event not in store.events

    recovered = import_s012_lifecycle_jsonl(source, store, backfill=True)
    assert recovered.applied == 1
    assert replacement_event in store.events


def test_in_place_change_before_cursor_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    append_event(source, lifecycle_event())
    store = FakeLifecycleStore()
    import_s012_lifecycle_jsonl(source, store, backfill=True)
    saved_state = dict(store.state)

    content = source.read_bytes()
    source.write_bytes(content.replace(b"manual_review", b"manual_revieX"))
    reset = import_s012_lifecycle_jsonl(source, store)

    assert reset.source_reset
    assert store.state == saved_state


def test_oversized_complete_record_fails_without_advancing(tmp_path: Path) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    source.write_bytes(b"")
    store = FakeLifecycleStore()
    import_s012_lifecycle_jsonl(source, store)
    source.write_bytes(b" " * MAX_RECORD_BYTES + b"x\n")

    with pytest.raises(LifecycleImportFailure, match="exceeds"):
        import_s012_lifecycle_jsonl(source, store)
    assert only_cursor(store)["cursor"] == 0


def test_invalid_saved_cursor_state_requires_explicit_backfill(tmp_path: Path) -> None:
    source = tmp_path / "signal-lifecycle.jsonl"
    append_event(source, lifecycle_event())
    store = FakeLifecycleStore()
    # Establish the path-specific key without importing history, then poison it.
    import_s012_lifecycle_jsonl(source, store)
    key = next(iter(store.state))
    store.state[key] = "not-json"

    result = import_s012_lifecycle_jsonl(source, store)
    assert result.source_reset
    assert store.events == []

    recovered = import_s012_lifecycle_jsonl(source, store, backfill=True)
    assert recovered.applied == 1


def test_producer_timestamp_shape_is_utc_and_bounded() -> None:
    timestamp = datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    event = lifecycle_event(occurred_at=timestamp)
    assert validate_lifecycle_event(event)["occurred_at"] == timestamp


def test_real_gateway_store_applies_approval_then_revocation_without_rewriting_envelope(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
    signal_id = "signal-real-store-0001"
    envelope = build_s012_envelope(
        {
            "signal_id": signal_id,
            "assessment_id": "assessment-real-store-1",
            "event_id": "source-event-real-store-1",
            "market_id": "market-real-store-1",
            "market_question": "Will a scheduled event occur?",
            "signal_type": "S012-OVER",
            "direction": "NO",
            "entry_price": 0.42,
            "target_price": 0.50,
            "stop_price": 0.35,
            "time_horizon_hours": 2,
            "size_usdc": 100.0,
            "size_pct": 0.01,
            "reaction_delta": 0.08,
            "estimated_shift": 0.04,
            "actual_move": 0.12,
            "confidence": 0.68,
            "reasoning": "Synthetic consumer integration signal.",
            "domain": "ECO",
            "passed_concentration": True,
            "passed_anti_patterns": True,
            "risk_notes": ["Verify resolution rules."],
            "status": "PENDING",
            "created_at": (now - timedelta(minutes=1)).isoformat(),
            "expires_at": (now + timedelta(hours=2)).isoformat(),
        }
    )
    store = GatewayStore(tmp_path / "private" / "gateway.db")
    source = tmp_path / "signal-lifecycle.jsonl"
    try:
        assert store.put_signal(envelope, now=now)
        original_json = store.conn.execute(
            "SELECT envelope_json FROM signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()[0]
        assert store.latest_signal(now=now) is None

        approval = lifecycle_event(signal_id=signal_id)
        append_event(source, approval)
        approved = import_s012_lifecycle_jsonl(source, store, backfill=True)
        assert approved.applied == 1
        assert store.latest_signal(now=now) is not None

        revocation = lifecycle_event(
            signal_id=signal_id,
            revision=2,
            previous_status="APPROVED",
            status="REVOKED",
            occurred_at="2026-09-02T12:01:00.000000Z",
        )
        revocation["reason_code"] = "manual_revocation"
        reseal(revocation)
        append_event(source, revocation)
        revoked = import_s012_lifecycle_jsonl(source, store)
        assert revoked.applied == 1
        assert store.latest_signal(now=now) is None

        current_json = store.conn.execute(
            "SELECT envelope_json FROM signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()[0]
        assert current_json == original_json
    finally:
        store.close()
