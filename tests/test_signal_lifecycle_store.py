from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from telegram_gateway.envelope import build_s012_envelope
from telegram_gateway.service import BotService
from telegram_gateway.store import GatewayStore


NOW = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
SIGNAL_ID = "signal-lifecycle-123456"


def _pending_envelope() -> dict[str, Any]:
    return build_s012_envelope(
        {
            "signal_id": SIGNAL_ID,
            "assessment_id": "assessment-1",
            "event_id": "event-1",
            "market_id": "market-1",
            "market_question": "Will a scheduled release occur?",
            "signal_type": "S012-OVER",
            "direction": "YES",
            "entry_price": 0.42,
            "target_price": 0.50,
            "stop_price": 0.35,
            "time_horizon_hours": 24,
            "size_usdc": 100,
            "size_pct": 0.01,
            "reaction_delta": 0.08,
            "estimated_shift": 0.04,
            "actual_move": 0.12,
            "confidence": 0.68,
            "reasoning": "Bounded lifecycle test analysis.",
            "domain": "ECO",
            "passed_concentration": True,
            "passed_anti_patterns": True,
            "risk_notes": ["Manual review remains required."],
            "status": "PENDING",
            "created_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=2)).isoformat(),
        }
    )


def _event(
    revision: int,
    previous: str,
    status: str,
    *,
    signal_id: str = SIGNAL_ID,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": "s012.signal-lifecycle/0.1",
        "signal_id": signal_id,
        "revision": revision,
        "previous_status": previous,
        "status": status,
        "occurred_at": (NOW + timedelta(minutes=revision)).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        "actor_kind": "local_operator",
        "reason_code": "manual_review" if status == "APPROVED" else "manual_revocation",
        "scope": "research_distribution_only",
        "execution_allowed": False,
    }
    material = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    value["event_id"] = "s012-life-" + hashlib.sha256(material).hexdigest()[:32]
    return value


@pytest.fixture
def store(tmp_path: Path) -> GatewayStore:
    value = GatewayStore(tmp_path / "private" / "gateway.db")
    try:
        yield value
    finally:
        value.close()


def test_pending_requires_approval_and_revocation_removes_visibility(
    store: GatewayStore,
) -> None:
    store.put_signal(_pending_envelope(), now=NOW)
    assert store.latest_signal(now=NOW) is None

    approval = _event(1, "PENDING", "APPROVED")
    assert store.apply_signal_lifecycle(approval, now=NOW) == "applied"
    assert store.apply_signal_lifecycle(approval, now=NOW) == "duplicate"
    assert store.latest_signal(now=NOW)["signal_id"] == SIGNAL_ID

    assert store.apply_signal_lifecycle(
        _event(2, "APPROVED", "REVOKED"), now=NOW
    ) == "applied"
    assert store.latest_signal(now=NOW) is None
    assert store.resolve_signal_prefix("signal-lifec", now=NOW) is None


def test_gap_is_quarantined_then_drained_after_missing_revision(
    store: GatewayStore,
) -> None:
    store.put_signal(_pending_envelope(), now=NOW)
    assert store.apply_signal_lifecycle(
        _event(2, "APPROVED", "REVOKED"), now=NOW
    ) == "quarantined"
    assert store.signal_lifecycle_status()["quarantined"] == 1

    assert store.apply_signal_lifecycle(
        _event(1, "PENDING", "APPROVED"), now=NOW
    ) == "applied"
    status = store.signal_lifecycle_status()
    assert status["states"] == {"REVOKED": 1}
    assert status["events"] == 2
    assert status["quarantined"] == 0


def test_orphan_is_retained_and_applied_when_base_signal_arrives(
    store: GatewayStore,
) -> None:
    approval = _event(1, "PENDING", "APPROVED")
    assert store.apply_signal_lifecycle(approval, now=NOW) == "orphan"
    assert store.signal_lifecycle_status()["quarantined"] == 1

    store.put_signal(_pending_envelope(), now=NOW)
    assert store.latest_signal(now=NOW) is not None
    assert store.signal_lifecycle_status()["quarantined"] == 0


def test_lifecycle_cannot_grant_execution_authority(store: GatewayStore) -> None:
    store.put_signal(_pending_envelope(), now=NOW)
    event = _event(1, "PENDING", "APPROVED")
    event["execution_allowed"] = True

    with pytest.raises(ValueError, match="execution authority"):
        store.apply_signal_lifecycle(event, now=NOW)
    assert store.latest_signal(now=NOW) is None


def test_revocation_sends_one_correction_to_prior_recipient(
    store: GatewayStore,
) -> None:
    class Transport:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []

        def send_text(
            self,
            chat_id: int,
            text: str,
            *,
            reply_markup: dict[str, Any] | None = None,
            protect_content: bool = False,
        ) -> dict[str, Any]:
            self.sent.append(
                {
                    "chat_id": chat_id,
                    "text": text,
                    "protect_content": protect_content,
                }
            )
            return {"message_id": len(self.sent)}

    store.put_signal(_pending_envelope(), now=NOW)
    store.apply_signal_lifecycle(_event(1, "PENDING", "APPROVED"), now=NOW)
    store.register_recipient(101, 101, now=NOW)
    store.record_delivery(
        signal_id=SIGNAL_ID,
        telegram_user_id=101,
        status="sent",
        telegram_message_id=77,
        now=NOW,
    )
    store.apply_signal_lifecycle(_event(2, "APPROVED", "REVOKED"), now=NOW)
    transport = Transport()
    service = BotService(store, transport)  # type: ignore[arg-type]

    assert service.broadcast_pending_corrections()["corrections_sent"] == 1
    assert service.broadcast_pending_corrections()["corrections_sent"] == 0
    assert "has been revoked" in transport.sent[0]["text"]
    assert "Bounded lifecycle test analysis" not in transport.sent[0]["text"]
    assert transport.sent[0]["protect_content"] is False
