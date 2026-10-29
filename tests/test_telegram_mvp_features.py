"""Transport-bound integration tests for the Telegram MVP feature layer."""

from __future__ import annotations

import hashlib
import json
import stat
from argparse import Namespace
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

from telegram_gateway.calibration import CalibrationLedger
from telegram_gateway.cli import _run_gateway
from telegram_gateway.envelope import build_s012_envelope
from telegram_gateway.preferences import PreferenceStore
from telegram_gateway.service import BotService, ServiceConfig
from telegram_gateway.store import GatewayStore


class CaptureTransport:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: Mapping[str, Any] | None = None,
        protect_content: bool = False,
    ) -> Mapping[str, Any]:
        message = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup,
            "protect_content": protect_content,
            "message_id": len(self.sent) + 1,
        }
        self.sent.append(message)
        return message


class RunnerTransport(CaptureTransport):
    def __init__(self, updates: list[Mapping[str, Any]]) -> None:
        super().__init__()
        self.updates = updates
        self.polls: list[tuple[int, int]] = []

    def get_updates(self, *, offset: int, timeout: int) -> list[Mapping[str, Any]]:
        self.polls.append((offset, timeout))
        return list(self.updates)


@dataclass
class Harness:
    gateway: GatewayStore
    preferences: PreferenceStore
    calibration: CalibrationLedger
    transport: CaptureTransport
    service: BotService
    now: datetime


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    private = tmp_path / "private"
    gateway = GatewayStore(private / "gateway.db")
    preferences = PreferenceStore(private / "preferences.db")
    calibration = CalibrationLedger(private / "calibration.jsonl")
    transport = CaptureTransport()
    service = BotService(
        gateway,
        transport,
        preferences=preferences,
        calibration=calibration,
    )
    try:
        yield Harness(
            gateway,
            preferences,
            calibration,
            transport,
            service,
            now,
        )
    finally:
        preferences.close()
        gateway.close()


def private_message(
    update_id: int,
    text: str,
    when: datetime,
    *,
    user_id: int = 101,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": user_id},
            "chat": {"id": user_id, "type": "private"},
            "date": int(when.timestamp()),
            "text": text,
        },
    }


def send(
    harness: Harness,
    update_id: int,
    text: str,
    *,
    seconds: int | None = None,
    user_id: int = 101,
) -> str:
    before = len(harness.transport.sent)
    when = harness.now + timedelta(seconds=seconds if seconds is not None else update_id)
    assert harness.service.handle_update(
        private_message(update_id, text, when, user_id=user_id)
    )
    assert len(harness.transport.sent) == before + 1
    return str(harness.transport.sent[-1]["text"])


def signal_envelope(
    issued_at: datetime,
    *,
    signal_id: str = "signal-mvp-eco-0001",
    market_id: str = "market-eco-1",
    domain: str = "ECO",
    status: str = "PENDING",
) -> dict[str, Any]:
    return build_s012_envelope(
        {
            "signal_id": signal_id,
            "assessment_id": "assessment-mvp-1",
            "event_id": "event-mvp-1",
            "market_id": market_id,
            "market_question": "Will a scheduled policy event occur?",
            "signal_type": "PROSPECTIVE_BINARY",
            "direction": "YES",
            "entry_price": 0.60,
            "target_price": 0.70,
            "stop_price": 0.45,
            "time_horizon_hours": 48,
            "size_usdc": 0.0,
            "size_pct": 0.0,
            "reaction_delta": None,
            "estimated_shift": None,
            "actual_move": None,
            "confidence": 0.70,
            "reasoning": "Synthetic evidence-labelled integration forecast.",
            "domain": domain,
            "passed_concentration": True,
            "passed_anti_patterns": True,
            "risk_notes": ["Paper research only."],
            "status": status,
            "created_at": issued_at.isoformat(),
            "expires_at": (issued_at + timedelta(hours=2)).isoformat(),
        },
        observation_refs=["observation:primary:mvp-1"],
        resolution_rules_ref="https://primary.example.test/rules/mvp-1",
    )


def approve_signal(
    gateway: GatewayStore,
    envelope: Mapping[str, Any],
    occurred_at: datetime,
) -> None:
    event: dict[str, Any] = {
        "schema": "s012.signal-lifecycle/0.1",
        "signal_id": str(envelope["signal_id"]),
        "revision": 1,
        "previous_status": "PENDING",
        "status": "APPROVED",
        "occurred_at": occurred_at.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "actor_kind": "local_operator",
        "reason_code": "manual_review",
        "scope": "research_distribution_only",
        "execution_allowed": False,
    }
    material = json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    event["event_id"] = "s012-life-" + hashlib.sha256(material).hexdigest()[:32]
    assert gateway.apply_signal_lifecycle(event, now=occurred_at) == "applied"


def test_personalization_topic_cadence_and_watchlist_commands(
    harness: Harness,
) -> None:
    text = send(harness, 1, "/personalize")
    assert "Personalization is enabled" in text
    initial = harness.preferences.snapshot(101)
    assert initial.active
    assert initial.cadence == "weekly"
    assert initial.topics == ()

    text = send(harness, 2, "/topics macro-policy,elections")
    assert "Topic filter saved: macro-policy, elections" in text
    text = send(harness, 3, "/topics")
    assert "Topic filter: macro-policy, elections" in text

    text = send(harness, 4, "/cadence daily")
    assert "Cadence saved: daily" in text
    text = send(harness, 5, "/watch polymarket:2252244")
    assert "added: polymarket:2252244" in text
    assert "No market or wallet was contacted" in text
    text = send(harness, 6, "/watchlist")
    assert "- polymarket:2252244" in text

    text = send(harness, 7, "/unwatch polymarket:2252244")
    assert "removed: polymarket:2252244" in text
    snapshot = harness.preferences.snapshot(101)
    assert snapshot.active
    assert snapshot.topics == ("macro-policy", "elections")
    assert snapshot.cadence == "daily"
    assert snapshot.watchlist == ()


def test_leave_turns_off_alerts_and_erases_personalization(
    harness: Harness,
) -> None:
    send(harness, 1, "/join")
    send(harness, 2, "/personalize")
    send(harness, 3, "/topics geopolitics")
    send(harness, 4, "/watch market-geo-1")

    text = send(harness, 5, "/leave")
    assert "Research alerts are now off" in text
    assert "Topic, cadence, and watchlist preferences were erased" in text
    assert harness.gateway.research_alert_status(101)["state"] == "unsubscribed"
    snapshot = harness.preferences.snapshot(101)
    assert snapshot.consent_state == "withdrawn"
    assert snapshot.topics == ()
    assert snapshot.watchlist == ()


def test_new_join_restores_alerts_without_recreating_personalization(
    harness: Harness,
) -> None:
    send(harness, 1, "/personalize")
    send(harness, 2, "/topics geopolitics")
    send(harness, 3, "/watch market-geo-1")

    send(harness, 4, "/leave")
    withdrawn = harness.preferences.snapshot(101)
    assert withdrawn.consent_state == "withdrawn"
    assert withdrawn.topics == ()
    assert withdrawn.watchlist == ()
    assert harness.gateway.contact_suppression_status(101)["reason"] == "withdrawn"

    join_text = send(harness, 5, "/join")
    assert "Research alerts are now on" in join_text
    assert "Use /personalize separately" in join_text
    assert "topic, cadence, or watchlist filtering" in join_text
    assert harness.gateway.research_alert_status(101)["state"] == "subscribed"
    assert harness.gateway.contact_suppression_status(101) is None
    still_withdrawn = harness.preferences.snapshot(101)
    assert still_withdrawn.consent_state == "withdrawn"
    assert still_withdrawn.topics == ()
    assert still_withdrawn.watchlist == ()

    issued = harness.now + timedelta(seconds=6)
    envelope = signal_envelope(
        issued,
        signal_id="signal-after-independent-rejoin",
        market_id="market-eco-after-rejoin",
        domain="ECO",
    )
    harness.gateway.put_signal(envelope, now=issued)
    approve_signal(harness.gateway, envelope, issued + timedelta(microseconds=1))

    assert harness.service.broadcast_pending() == {
        "sent": 1,
        "failed": 0,
        "unknown": 0,
    }
    delivered = harness.transport.sent[-1]
    assert delivered["chat_id"] == 101
    assert "Will a scheduled policy event occur?" in delivered["text"]
    assert harness.preferences.snapshot(101).consent_state == "withdrawn"


def test_delete_me_purges_preference_profile_and_keeps_minimal_tombstone(
    harness: Harness,
) -> None:
    send(harness, 1, "/personalize")
    send(harness, 2, "/topics economic-releases")
    send(harness, 3, "/watch polymarket:2252244")

    text = send(harness, 4, "/delete_me")
    assert "Topic, cadence, and watchlist data were deleted" in text
    assert "minimal personalization no-contact watermark remains" in text
    snapshot = harness.preferences.snapshot(101)
    assert snapshot.consent_state == "deleted"
    assert snapshot.topics == ()
    assert snapshot.watchlist == ()
    assert harness.gateway.recipient_status(101) is None
    assert harness.gateway.contact_suppression_status(101)["reason"] == "deleted"
    assert harness.preferences.conn.execute(
        "SELECT COUNT(*) FROM preference_profiles WHERE telegram_user_id = 101"
    ).fetchone()[0] == 0
    assert harness.preferences.conn.execute(
        "SELECT COUNT(*) FROM preference_suppressions WHERE telegram_user_id = 101"
    ).fetchone()[0] == 1


def test_scorecard_command_renders_resolved_domain_metrics(harness: Harness) -> None:
    issued = harness.now
    envelope = signal_envelope(issued, status="APPROVED")
    harness.calibration.register_forecast(
        envelope,
        probability_yes=0.70,
        recorded_at=issued + timedelta(minutes=1),
    )
    harness.calibration.record_resolution(
        str(envelope["signal_id"]),
        outcome="YES",
        resolved_at=issued + timedelta(hours=3),
        resolution_evidence_refs=["observation:resolution:mvp-1"],
        resolution_evidence_content_digest="sha256:" + "a" * 64,
        recorded_at=issued + timedelta(hours=3, minutes=1),
    )

    text = send(harness, 1, "/scorecard eco")
    assert "KINGDOM paper calibration" in text
    assert "Domain: ECO" in text
    assert "Registered: 1" in text
    assert "Resolved: 1" in text
    assert "Agent mean Brier: 0.0900" in text
    assert "Market mean Brier: 0.1600" in text
    assert "Mean Brier advantage vs market: 0.0700" in text
    assert "do not promise returns or authorize a trade" in text


def test_topic_filter_blocks_preview_until_matching_watchlist_override(
    harness: Harness,
) -> None:
    send(harness, 1, "/join")
    send(harness, 2, "/personalize")
    send(harness, 3, "/topics geopolitics")
    send(harness, 4, "/cadence realtime")

    issued = harness.now + timedelta(seconds=5)
    envelope = signal_envelope(issued, market_id="market-eco-1", domain="ECO")
    harness.gateway.put_signal(envelope, now=issued)
    approve_signal(harness.gateway, envelope, issued + timedelta(microseconds=1))

    before = len(harness.transport.sent)
    assert harness.service.broadcast_pending() == {
        "sent": 0,
        "failed": 0,
        "unknown": 0,
    }
    assert len(harness.transport.sent) == before

    text = send(harness, 5, "/watch market-eco-1", seconds=6)
    assert "added: market-eco-1" in text
    result = harness.service.broadcast_pending()
    assert result == {"sent": 1, "failed": 0, "unknown": 0}
    delivered = harness.transport.sent[-1]
    assert delivered["chat_id"] == 101
    assert "Will a scheduled policy event occur?" in delivered["text"]
    assert "Live execution is disabled" in delivered["text"]


def test_bundled_runner_wires_preferences_and_calibration_without_network(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = tmp_path / "private"
    gateway = GatewayStore(private / "gateway.db")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    api = RunnerTransport(
        [
            private_message(1, "/personalize", now),
            private_message(2, "/scorecard", now + timedelta(seconds=1)),
        ]
    )
    calibration_path = private / "calibration.jsonl"
    args = Namespace(
        once=True,
        control_only=True,
        calibration_ledger=calibration_path,
    )

    try:
        result = _run_gateway(args, gateway, api, ServiceConfig())  # type: ignore[arg-type]
        assert result == 0
        report = json.loads(capsys.readouterr().out)
        assert report["updates"] == 2
        assert report["failed_updates"] == 0
        assert report["broadcast_paused"] == 1
        assert report["corrections_paused"] == 1
        assert api.polls == [(0, 0)]

        assert "Personalization is enabled" in api.sent[0]["text"]
        assert "KINGDOM paper calibration" in api.sent[1]["text"]
        assert "Registered: 0" in api.sent[1]["text"]
        table_names = {
            str(row[0])
            for row in gateway.conn.execute(
                """SELECT name FROM sqlite_master
                   WHERE type = 'table' AND name LIKE 'preference_%'"""
            )
        }
        assert table_names == {
            "preference_profiles",
            "preference_store_meta",
            "preference_suppressions",
            "preference_topics",
            "preference_watchlist",
        }
        profile = gateway.conn.execute(
            """SELECT telegram_user_id, private_chat_id, cadence
               FROM preference_profiles WHERE telegram_user_id = 101"""
        ).fetchone()
        assert dict(profile) == {
            "telegram_user_id": 101,
            "private_chat_id": 101,
            "cadence": "weekly",
        }
        assert calibration_path.is_file()
        assert stat.S_IMODE(calibration_path.stat().st_mode) == 0o600
    finally:
        gateway.close()


def test_persistent_control_only_runner_is_quiet_when_idle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class IdleThenStopService:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.polls = 0

        def poll_once(self, **kwargs: Any) -> Mapping[str, int]:
            assert kwargs == {
                "broadcast": False,
                "deliver_corrections": False,
            }
            self.polls += 1
            if self.polls > 1:
                raise KeyboardInterrupt
            return {
                "updates": 0,
                "failed_updates": 0,
                "broadcast_paused": 1,
                "corrections_paused": 1,
                "corrections_sent": 0,
                "corrections_failed": 0,
                "corrections_unknown": 0,
                "sent": 0,
                "failed": 0,
                "unknown": 0,
            }

    monkeypatch.setattr("telegram_gateway.cli.BotService", IdleThenStopService)
    private = tmp_path / "private"
    gateway = GatewayStore(private / "gateway.db")
    args = Namespace(
        once=False,
        control_only=True,
        calibration_ledger=private / "calibration.jsonl",
    )

    try:
        with pytest.raises(KeyboardInterrupt):
            _run_gateway(args, gateway, object(), ServiceConfig())  # type: ignore[arg-type]
        assert capsys.readouterr().out == ""
    finally:
        gateway.close()


def test_persistent_control_only_runner_prints_activity_and_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reports = iter(
        [
            {
                "updates": 2,
                "failed_updates": 0,
                "broadcast_paused": 1,
                "corrections_paused": 1,
            },
            {
                "updates": 0,
                "failed_updates": 1,
                "broadcast_paused": 1,
                "corrections_paused": 1,
            },
        ]
    )

    class ActivityThenStopService:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def poll_once(self, **kwargs: Any) -> Mapping[str, int]:
            assert kwargs == {
                "broadcast": False,
                "deliver_corrections": False,
            }
            try:
                return next(reports)
            except StopIteration:
                raise KeyboardInterrupt from None

    monkeypatch.setattr("telegram_gateway.cli.BotService", ActivityThenStopService)
    private = tmp_path / "private"
    gateway = GatewayStore(private / "gateway.db")
    args = Namespace(
        once=False,
        control_only=True,
        calibration_ledger=private / "calibration.jsonl",
    )

    try:
        with pytest.raises(KeyboardInterrupt):
            _run_gateway(args, gateway, object(), ServiceConfig())  # type: ignore[arg-type]
        printed = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        assert [report["updates"] for report in printed] == [2, 0]
        assert [report["failed_updates"] for report in printed] == [0, 1]
    finally:
        gateway.close()
