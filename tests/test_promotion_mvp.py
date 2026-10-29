from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

from telegram_gateway.cli import main
from telegram_gateway.envelope import build_s012_envelope
from telegram_gateway.promotion import generate_campaign_code
from telegram_gateway.service import BotService, ServiceConfig
from telegram_gateway.store import GatewayStore
from telegram_gateway.telegram_api import TelegramError


UTC = timezone.utc


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.updates: list[Mapping[str, Any]] = []
        self.requested_offsets: list[int] = []

    def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: Mapping[str, Any] | None = None,
        protect_content: bool = False,
    ) -> Mapping[str, Any]:
        self.sent.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
                "protect_content": protect_content,
            }
        )
        return {"message_id": len(self.sent)}

    def get_updates(self, *, offset: int, timeout: int) -> list[Mapping[str, Any]]:
        self.requested_offsets.append(offset)
        updates = list(self.updates)
        self.updates.clear()
        return updates

    def answer_callback(self, callback_query_id: str, text: str = "") -> bool:
        return True

    def answer_pre_checkout(
        self,
        pre_checkout_query_id: str,
        *,
        ok: bool,
        error_message: str | None = None,
    ) -> bool:
        return True

    def create_subscription_link(self, *, payload: str, stars_amount: int) -> str:
        raise AssertionError("the free MVP must not create an invoice link")

    def edit_subscription(
        self, *, user_id: int, initial_charge_id: str, canceled: bool
    ) -> bool:
        raise AssertionError("the free MVP must not edit a Star subscription")


class FailingCallbackAckTransport(FakeTransport):
    def answer_callback(self, callback_query_id: str, text: str = "") -> bool:
        raise TelegramError(
            "synthetic callback acknowledgement failure",
            error_code=500,
            ambiguous=False,
        )


@pytest.fixture
def store(tmp_path: Path) -> GatewayStore:
    value = GatewayStore(tmp_path / "private" / "gateway.db")
    try:
        yield value
    finally:
        value.close()


def private_message(
    update_id: int,
    user_id: int,
    text: str,
    when: datetime,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(when.timestamp()),
            "from": {"id": user_id},
            "chat": {"id": user_id, "type": "private"},
            "text": text,
        },
    }


def callback_query(
    update_id: int,
    user_id: int,
    data: str,
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"callback-{update_id}",
            "from": {"id": user_id},
            "message": {
                "message_id": update_id,
                "chat": {"id": user_id, "type": "private"},
            },
            "data": data,
        },
    }


def pending_envelope(
    signal_id: str,
    issued_at: datetime,
    *,
    expires_after: timedelta = timedelta(days=30),
) -> dict[str, Any]:
    return build_s012_envelope(
        {
            "signal_id": signal_id,
            "assessment_id": "assessment-1",
            "event_id": "event-1",
            "market_id": "market-1",
            "market_question": f"Will the bounded test event {signal_id} occur?",
            "signal_type": "S012-OVER",
            "direction": "NO",
            "entry_price": 0.42,
            "target_price": 0.50,
            "stop_price": 0.35,
            "time_horizon_hours": 24,
            "size_usdc": 100.0,
            "size_pct": 0.01,
            "reaction_delta": 0.08,
            "estimated_shift": 0.04,
            "actual_move": 0.12,
            "confidence": 0.68,
            "reasoning": "Bounded synthetic promotion test analysis.",
            "domain": "ECO",
            "passed_concentration": True,
            "passed_anti_patterns": True,
            "risk_notes": ["Manual review remains required."],
            "status": "PENDING",
            "created_at": issued_at.isoformat(),
            "expires_at": (issued_at + expires_after).isoformat(),
        }
    )


def lifecycle_event(
    signal_id: str,
    occurred_at: datetime,
    *,
    revision: int = 1,
    previous_status: str = "PENDING",
    status: str = "APPROVED",
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema": "s012.signal-lifecycle/0.1",
        "signal_id": signal_id,
        "revision": revision,
        "previous_status": previous_status,
        "status": status,
        "occurred_at": occurred_at.astimezone(UTC).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        "actor_kind": "local_operator",
        "reason_code": (
            "manual_review" if status == "APPROVED" else "manual_revocation"
        ),
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
    return event


def put_approved(
    store: GatewayStore,
    signal_id: str,
    issued_at: datetime,
    *,
    expires_after: timedelta = timedelta(days=30),
) -> dict[str, Any]:
    envelope = pending_envelope(
        signal_id,
        issued_at,
        expires_after=expires_after,
    )
    store.put_signal(envelope, now=issued_at)
    assert (
        store.apply_signal_lifecycle(
            lifecycle_event(signal_id, issued_at + timedelta(seconds=1)),
            now=issued_at + timedelta(seconds=1),
        )
        == "applied"
    )
    return envelope


def test_campaign_start_is_aggregate_until_explicit_source_opt_in(
    store: GatewayStore,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    first = generate_campaign_code()
    second = generate_campaign_code()
    assert store.create_promotion_campaign(first, campaign_kind="telegram_channel")
    assert store.create_promotion_campaign(second, campaign_kind="partner")
    transport = FakeTransport()
    service = BotService(store, transport)

    assert service.handle_update(private_message(10, 101, f"/start {first}", now))
    assert store.research_alert_status(101)["state"] == "not_joined"
    assert store.conn.execute(
        "SELECT COUNT(*) FROM promotion_attributions WHERE telegram_user_id = 101"
    ).fetchone()[0] == 0
    assert dict(
        store.conn.execute(
            "SELECT campaign_code, observed_on, start_count "
            "FROM promotion_campaign_starts"
        ).fetchone()
    ) == {
        "campaign_code": first,
        "observed_on": now.date().isoformat(),
        "start_count": 1,
    }
    callback_data = transport.sent[-1]["reply_markup"]["inline_keyboard"][0][0][
        "callback_data"
    ]
    assert service.handle_update(callback_query(11, 101, callback_data))
    assert store.research_alert_status(101)["state"] == "subscribed"
    assert store.conn.execute(
        "SELECT campaign_code FROM promotion_attributions WHERE telegram_user_id = 101"
    ).fetchone()[0] == first

    # Later visits remain aggregate observations and cannot rewrite attribution.
    assert service.handle_update(private_message(12, 101, f"/start {second}", now))
    assert service.handle_update(
        private_message(13, 101, f"/start {generate_campaign_code()}", now)
    )
    assert store.conn.execute(
        "SELECT campaign_code FROM promotion_attributions WHERE telegram_user_id = 101"
    ).fetchone()[0] == first


def test_callback_ack_failure_does_not_consume_source_linked_opt_in(
    store: GatewayStore,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=1)
    campaign = generate_campaign_code()
    assert store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
    transport = FailingCallbackAckTransport()
    service = BotService(store, transport)
    service.handle_update(private_message(10, 101, f"/start {campaign}", now))
    callback_data = transport.sent[-1]["reply_markup"]["inline_keyboard"][0][0][
        "callback_data"
    ]

    assert service.handle_update(callback_query(11, 101, callback_data))

    assert store.research_alert_status(101)["state"] == "subscribed"
    assert store.conn.execute(
        "SELECT campaign_code FROM promotion_attributions WHERE telegram_user_id = 101"
    ).fetchone()[0] == campaign
    assert store.is_update_processed(11)


def test_delayed_old_join_cannot_override_newer_leave(store: GatewayStore) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    transport = FakeTransport()
    service = BotService(store, transport)

    service.handle_update(private_message(100, 101, "/join", now))
    service.handle_update(
        private_message(300, 101, "/leave", now + timedelta(minutes=2))
    )
    leave_response = dict(transport.sent[-1])
    sent_count = len(transport.sent)
    service.handle_update(
        private_message(200, 101, "/join", now + timedelta(minutes=1))
    )

    assert store.research_alert_status(101)["state"] == "unsubscribed"
    assert len(transport.sent) == sent_count
    assert transport.sent[-1] == leave_response


def test_fresh_leave_tombstone_blocks_a_delayed_older_join(
    store: GatewayStore,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    transport = FakeTransport()
    service = BotService(store, transport)

    service.handle_update(
        private_message(300, 101, "/leave", now + timedelta(minutes=2))
    )
    leave_response = dict(transport.sent[-1])
    service.handle_update(
        private_message(200, 101, "/join", now + timedelta(minutes=1))
    )

    assert store.recipient_status(101) is None
    assert store.research_alert_status(101)["state"] == "not_joined"
    assert store.contact_suppression_status(101)["reason"] == "withdrawn"
    assert transport.sent == [leave_response]


def test_repeated_leave_advances_watermark_against_delayed_join(
    store: GatewayStore,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    service = BotService(store, FakeTransport())

    service.handle_update(private_message(100, 101, "/join", now))
    service.handle_update(
        private_message(300, 101, "/leave", now + timedelta(minutes=2))
    )
    service.handle_update(
        private_message(500, 101, "/leave", now + timedelta(minutes=4))
    )
    service.handle_update(
        private_message(400, 101, "/join", now + timedelta(minutes=3))
    )

    assert store.research_alert_status(101)["state"] == "unsubscribed"


def test_lower_random_update_id_after_week_can_still_withdraw(
    store: GatewayStore,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(days=10)
    service = BotService(store, FakeTransport())

    service.handle_update(private_message(1_000_000, 101, "/join", now))
    service.handle_update(
        private_message(5, 101, "/stop", now + timedelta(days=8))
    )

    assert store.research_alert_status(101)["state"] == "unsubscribed"
    assert store.conn.execute(
        "SELECT COUNT(*) FROM research_alert_consent_events "
        "WHERE telegram_user_id = 101"
    ).fetchone()[0] == 2


def test_idle_cursor_epoch_reset_is_one_shot_until_a_new_update(
    store: GatewayStore,
) -> None:
    reset_at = datetime.now(UTC).replace(microsecond=0)
    old_event_at = reset_at - timedelta(days=7)
    store.mark_update_processed(1_000_000, now=old_event_at)
    store.mark_update_failed(
        999_999,
        error_code="old_epoch_failure",
        ambiguous=False,
        now=old_event_at,
    )

    assert store.prepare_update_poll(now=reset_at) == 0
    first_reset_marker = store.get_state("telegram_update_epoch_reset_at")
    assert first_reset_marker == reset_at.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    assert store.conn.execute("SELECT COUNT(*) FROM processed_updates").fetchone()[
        0
    ] == 2
    assert (
        store.conn.execute("SELECT COUNT(*) FROM failed_updates").fetchone()[0] == 1
    )
    assert store.is_update_processed(1_000_000)
    assert store.is_update_processed(999_999)

    # Empty polls in the reset epoch must not repeatedly reset its marker.
    assert store.prepare_update_poll(now=reset_at + timedelta(hours=1)) == 0
    assert store.get_state("telegram_update_epoch_reset_at") == first_reset_marker

    new_event_at = reset_at + timedelta(hours=2)
    store.mark_update_processed(5, now=new_event_at)
    assert store.get_offset() == 6
    assert (
        store.prepare_update_poll(
            now=new_event_at + timedelta(days=5, hours=23, minutes=59)
        )
        == 6
    )
    assert store.prepare_update_poll(now=new_event_at + timedelta(days=6)) == 0


def test_poll_once_uses_idle_reset_before_fetching_low_random_update_id(
    store: GatewayStore,
) -> None:
    store.mark_update_processed(
        1_000_000,
        now=datetime.now(UTC).replace(microsecond=0) - timedelta(days=7),
    )
    transport = FakeTransport()
    transport.updates.append({"update_id": 5})
    service = BotService(store, transport)

    result = service.poll_once(timeout=0, broadcast=False)

    assert result["updates"] == 1
    assert transport.requested_offsets == [0]
    assert store.get_offset() == 6
    assert store.is_update_processed(5)
    assert store.is_update_processed(1_000_000)

    service.poll_once(timeout=0, broadcast=False)
    assert transport.requested_offsets == [0, 6]


def test_cursor_reset_rearms_even_if_wall_clock_steps_backward(
    store: GatewayStore,
) -> None:
    reset_at = datetime.now(UTC).replace(microsecond=0)
    store.mark_update_processed(1_000_000, now=reset_at - timedelta(days=7))
    assert store.prepare_update_poll(now=reset_at) == 0
    assert store.get_state("telegram_update_seen_since_reset") == "0"

    backward_receipt = reset_at - timedelta(hours=1)
    store.mark_update_processed(5, now=backward_receipt)
    assert store.get_offset() == 6
    assert store.get_state("telegram_update_seen_since_reset") == "1"
    assert (
        store.prepare_update_poll(
            now=backward_receipt + timedelta(days=5, hours=23, minutes=59)
        )
        == 6
    )
    assert (
        store.prepare_update_poll(now=backward_receipt + timedelta(days=6)) == 0
    )
    assert store.get_state("telegram_update_seen_since_reset") == "0"


@pytest.mark.parametrize("command", ["/leave", "/stop", "/unsubscribe"])
def test_withdrawal_bypasses_interactive_rate_limit(
    store: GatewayStore,
    command: str,
) -> None:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    store.register_recipient(101, 101, now=now)
    store.set_research_alert_consent(
        101,
        subscribed=True,
        telegram_update_id=10,
        event_at=now,
        now=now,
    )
    for _ in range(20):
        assert store.allow_interactive_request(101, now=now)
    assert not store.allow_interactive_request(101, now=now)

    service = BotService(store, FakeTransport())
    service.handle_update(
        private_message(11, 101, command, now + timedelta(seconds=1))
    )

    assert store.research_alert_status(101)["state"] == "unsubscribed"


def test_unblocking_bot_does_not_restore_old_alert_consent(
    store: GatewayStore,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    service = BotService(store, FakeTransport())
    service.handle_update(private_message(10, 101, "/join", now))

    def membership(update_id: int, status: str) -> dict[str, Any]:
        return {
            "update_id": update_id,
            "my_chat_member": {
                "date": int((now + timedelta(minutes=update_id)).timestamp()),
                "from": {"id": 101},
                "chat": {"id": 101, "type": "private"},
                "old_chat_member": {"status": "member"},
                "new_chat_member": {"status": status},
            },
        }

    service.handle_update(membership(11, "kicked"))
    service.handle_update(membership(12, "member"))

    assert store.research_alert_status(101)["state"] != "subscribed"


def test_new_notice_requires_explicit_reconfirmation(store: GatewayStore) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    store.register_recipient(101, 101, now=now)
    store.set_research_alert_consent(
        101,
        subscribed=True,
        telegram_update_id=10,
        notice_version="alerts-v1",
        event_at=now,
        now=now,
    )

    assert store.research_alert_status(101, "alerts-v2")["state"] == (
        "needs_reconfirmation"
    )
    assert store.pending_deliveries(now=now, notice_version="alerts-v2") == []

    service = BotService(
        store,
        FakeTransport(),
        config=ServiceConfig(promotion_notice_version="alerts-v2"),
    )
    service.handle_update(
        private_message(11, 101, "/join", now + timedelta(minutes=1))
    )
    assert store.research_alert_status(101, "alerts-v2")["state"] == "subscribed"


def test_stale_notice_bound_campaign_callback_cannot_opt_in_or_attribute(
    store: GatewayStore,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=1)
    campaign = generate_campaign_code()
    assert store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
    transport = FakeTransport()
    old_service = BotService(
        store,
        transport,
        config=ServiceConfig(promotion_notice_version="alerts-v1"),
    )
    old_service.handle_update(private_message(10, 101, f"/start {campaign}", now))
    callback_data = transport.sent[-1]["reply_markup"]["inline_keyboard"][0][0][
        "callback_data"
    ]

    current_service = BotService(
        store,
        transport,
        config=ServiceConfig(promotion_notice_version="alerts-v2"),
    )
    current_service.handle_update(callback_query(11, 101, callback_data))

    assert store.research_alert_status(101, "alerts-v2")["state"] == "not_joined"
    assert store.conn.execute(
        "SELECT COUNT(*) FROM promotion_attributions WHERE telegram_user_id = 101"
    ).fetchone()[0] == 0
    assert "older notice" in transport.sent[-1]["text"]


def test_existing_direct_consent_cannot_gain_retroactive_campaign_attribution(
    store: GatewayStore,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=1)
    campaign = generate_campaign_code()
    assert store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
    transport = FakeTransport()
    service = BotService(store, transport)
    service.handle_update(private_message(10, 101, "/join", now))
    service.handle_update(
        private_message(11, 101, f"/start {campaign}", now + timedelta(seconds=1))
    )
    callback_data = transport.sent[-1]["reply_markup"]["inline_keyboard"][0][0][
        "callback_data"
    ]

    service.handle_update(callback_query(12, 101, callback_data))

    assert store.research_alert_status(101)["state"] == "subscribed"
    assert store.conn.execute(
        "SELECT COUNT(*) FROM promotion_attributions WHERE telegram_user_id = 101"
    ).fetchone()[0] == 0
    assert "already on" in transport.sent[-1]["text"]


def test_alerts_are_future_only_and_capped_at_two_per_rolling_week(
    store: GatewayStore,
) -> None:
    joined = datetime.now(UTC).replace(microsecond=0) - timedelta(days=20)
    store.register_recipient(101, 101, now=joined)
    store.set_research_alert_consent(
        101,
        subscribed=True,
        telegram_update_id=10,
        event_at=joined,
        now=joined,
    )
    put_approved(store, "signal-before-join", joined - timedelta(hours=1))
    for index in range(1, 4):
        put_approved(
            store,
            f"signal-after-join-{index}",
            joined + timedelta(minutes=index),
        )

    first_pass_at = joined + timedelta(minutes=5)
    pending = store.pending_deliveries(now=first_pass_at)
    assert [item["signal_id"] for item in pending] == [
        "signal-after-join-1",
        "signal-after-join-2",
    ]
    for index, item in enumerate(pending, start=1):
        store.record_delivery(
            signal_id=item["signal_id"],
            telegram_user_id=101,
            status="sent",
            telegram_message_id=index,
            now=first_pass_at,
        )
    assert store.pending_deliveries(now=first_pass_at) == []
    assert [
        item["signal_id"]
        for item in store.pending_deliveries(now=first_pass_at + timedelta(days=8))
    ] == ["signal-after-join-3"]


def test_delete_me_purges_marketing_state_even_when_financial_deletion_waits(
    store: GatewayStore,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=1)
    campaign = generate_campaign_code()
    store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
    store.register_recipient(101, 101, now=now)
    result = store.join_promotion_campaign(
        101,
        campaign,
        10,
        event_at=now,
        now=now,
    )
    assert result["attributed"]
    envelope = put_approved(store, "signal-delete-held", now + timedelta(seconds=1))
    store.record_delivery(
        signal_id=str(envelope["signal_id"]),
        telegram_user_id=101,
        status="sent",
        telegram_message_id=99,
        now=now + timedelta(seconds=2),
    )
    store.conn.execute(
        """INSERT INTO paper_actions
             (paper_action_id, telegram_user_id, signal_id, direction,
              entry_probability, simulated_amount_usdc, created_at,
              explicit_request_ref)
           VALUES ('paper-delete-held', 101, ?, 'NO', 0.42, 100.0, ?,
                   'test:delete-held')""",
        (
            str(envelope["signal_id"]),
            (now + timedelta(seconds=2)).isoformat(),
        ),
    )
    store.conn.commit()
    store.accept_terms(101, "terms-v1", now=now)
    store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )

    transport = FakeTransport()
    BotService(store, transport).handle_update(
        private_message(12, 101, "/delete_me", now + timedelta(seconds=1))
    )

    assert store.recipient_status(101) is not None
    assert store.research_alert_status(101)["state"] == "not_joined"
    assert store.conn.execute(
        "SELECT COUNT(*) FROM promotion_attributions WHERE telegram_user_id = 101"
    ).fetchone()[0] == 0
    assert store.conn.execute(
        "SELECT COUNT(*) FROM research_alert_consent_events "
        "WHERE telegram_user_id = 101"
    ).fetchone()[0] == 0
    assert store.conn.execute(
        "SELECT COUNT(*) FROM delivery_receipts WHERE telegram_user_id = 101"
    ).fetchone()[0] == 0
    assert store.conn.execute(
        "SELECT COUNT(*) FROM paper_actions WHERE telegram_user_id = 101"
    ).fetchone()[0] == 0
    assert store.contact_suppression_status(101)["reason"] == "deleted"
    assert "Non-financial campaign, consent" in transport.sent[-1]["text"]
    assert "minimal numeric Telegram ID" in transport.sent[-1]["text"]

    assert (
        store.apply_signal_lifecycle(
            lifecycle_event(
                str(envelope["signal_id"]),
                now + timedelta(seconds=3),
                revision=2,
                previous_status="APPROVED",
                status="REVOKED",
            ),
            now=now + timedelta(seconds=3),
        )
        == "applied"
    )
    sent_count = len(transport.sent)
    assert BotService(store, transport).broadcast_pending_corrections()[
        "corrections_sent"
    ] == 0
    assert len(transport.sent) == sent_count


def test_delete_tombstone_blocks_delayed_join_and_campaign_start(
    store: GatewayStore,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    campaign = generate_campaign_code()
    assert store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
    transport = FakeTransport()
    service = BotService(store, transport)
    service.handle_update(private_message(100, 101, "/join", now))
    service.handle_update(
        private_message(400, 101, "/delete_me", now + timedelta(minutes=3))
    )
    delete_response = dict(transport.sent[-1])

    service.handle_update(
        private_message(200, 101, "/join", now + timedelta(minutes=1))
    )
    service.handle_update(
        private_message(300, 101, f"/start {campaign}", now + timedelta(minutes=2))
    )

    assert store.recipient_status(101) is None
    assert store.research_alert_status(101)["state"] == "not_joined"
    assert store.contact_suppression_status(101)["reason"] == "deleted"
    assert store.conn.execute(
        "SELECT COUNT(*) FROM promotion_campaign_starts WHERE campaign_code = ?",
        (campaign,),
    ).fetchone()[0] == 0
    assert transport.sent[-1] == delete_response

    # A genuinely newer, explicit source-linked opt-in starts a clean cycle.
    assert service.handle_update(
        private_message(500, 101, f"/start {campaign}", now + timedelta(minutes=4))
    )
    callback_data = transport.sent[-1]["reply_markup"]["inline_keyboard"][0][0][
        "callback_data"
    ]
    assert service.handle_update(callback_query(501, 101, callback_data))
    assert store.research_alert_status(101)["state"] == "subscribed"
    assert store.contact_suppression_status(101) is None
    attribution = store.conn.execute(
        """SELECT campaign_code, attribution_update_id
           FROM promotion_attributions WHERE telegram_user_id = 101"""
    ).fetchone()
    assert tuple(attribution) == (campaign, 501)


def test_free_alert_is_public_and_leave_suppresses_its_later_correction(
    store: GatewayStore,
) -> None:
    joined = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    for user_id, update_id in ((101, 10), (202, 20)):
        store.register_recipient(user_id, user_id, now=joined)
        assert store.set_research_alert_consent(
            user_id,
            subscribed=True,
            telegram_update_id=update_id,
            event_at=joined,
            now=joined,
        )
    transport = FakeTransport()
    service = BotService(store, transport)
    envelope = put_approved(
        store,
        "signal-free-correction",
        joined + timedelta(minutes=1),
    )

    assert service.broadcast_pending()["sent"] == 2
    assert "public preview" in transport.sent[-1]["text"]
    assert "Model direction" not in transport.sent[-1]["text"]
    service.handle_update(
        private_message(11, 101, "/leave", joined + timedelta(minutes=2))
    )
    assert (
        store.apply_signal_lifecycle(
            lifecycle_event(
                str(envelope["signal_id"]),
                joined + timedelta(minutes=3),
                revision=2,
                previous_status="APPROVED",
                status="REVOKED",
            ),
            now=joined + timedelta(minutes=3),
        )
        == "applied"
    )

    assert service.broadcast_pending_corrections()["corrections_sent"] == 1
    assert transport.sent[-1]["chat_id"] == 202
    assert "has been revoked" in transport.sent[-1]["text"]


def test_campaign_cli_create_report_and_disable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "gateway.db"
    with GatewayStore(database) as store:
        store.bind_authenticated_telegram_provider(
            7001,
            "https://api.telegram.org",
            "KingdomResearchBot",
        )
    assert (
        main(
            [
                "--db",
                str(database),
                "campaign-create",
                "--kind",
                "telegram_channel",
                "--bot-username",
                "kingdomresearchbot",
            ]
        )
        == 0
    )
    created = json.loads(capsys.readouterr().out)
    assert created["created"] is True
    assert created["deep_link"] == (
        f"https://t.me/KingdomResearchBot?start={created['campaign_code']}"
    )

    assert main(["--db", str(database), "promotion-status"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["campaigns"] == 1
    assert report["campaigns"][0]["campaign_code"] == created["campaign_code"]
    assert "telegram_user_id" not in report["campaigns"][0]

    assert (
        main(
            [
                "--db",
                str(database),
                "campaign-disable",
                created["campaign_code"],
            ]
        )
        == 0
    )
    disabled = json.loads(capsys.readouterr().out)
    assert disabled["disabled"] is True


@pytest.mark.parametrize(
    ("stored_bot_username", "error_fragment"),
    [
        (None, "no verified Telegram bot username"),
        ("DifferentResearchBot", "does not match the verified gateway binding"),
    ],
)
def test_campaign_create_deep_link_requires_verified_matching_bot_username(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    stored_bot_username: str | None,
    error_fragment: str,
) -> None:
    database = tmp_path / "gateway.db"
    with GatewayStore(database) as store:
        if stored_bot_username is None:
            store.bind_telegram_provider(7001, "https://api.telegram.org")
        else:
            store.bind_authenticated_telegram_provider(
                7001,
                "https://api.telegram.org",
                stored_bot_username,
            )

    assert (
        main(
            [
                "--db",
                str(database),
                "campaign-create",
                "--kind",
                "telegram_channel",
                "--bot-username",
                "KingdomResearchBot",
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert error_fragment in output.err
    with GatewayStore(database) as store:
        assert (
            store.conn.execute("SELECT COUNT(*) FROM promotion_campaigns").fetchone()[0]
            == 0
        )


def test_cli_metrics_use_the_configured_notice_version(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    with GatewayStore(database) as value:
        value.register_recipient(101, 101, now=now)
        assert value.set_research_alert_consent(
            101,
            subscribed=True,
            telegram_update_id=10,
            notice_version="alerts-v1",
            event_at=now,
            now=now,
        )
    monkeypatch.setenv("KINGDOM_TELEGRAM_PROMOTION_NOTICE_VERSION", "alerts-v2")

    assert main(["--db", str(database), "promotion-status"]) == 0
    promotion = json.loads(capsys.readouterr().out)
    assert promotion["notice_version"] == "alerts-v2"
    assert promotion["privacy_status"] == "small_cells_suppressed"
    assert promotion["summary"]["alerts_subscribed"] is None
    assert promotion["summary"]["alerts_need_reconfirmation"] is None

    assert (
        main(["--db", str(database), "promotion-status", "--exact-local"]) == 0
    )
    exact = json.loads(capsys.readouterr().out)
    assert exact["notice_version"] == "alerts-v2"
    assert exact["privacy_status"] == "exact_local_unsafe"
    assert exact["summary"]["alerts_subscribed"] == 0
    assert exact["summary"]["alerts_need_reconfirmation"] == 1

    assert main(["--db", str(database), "status"]) == 0
    status = json.loads(capsys.readouterr().out.splitlines()[0])
    assert status["promotion_notice_version"] == "alerts-v2"
    assert "alerts_subscribed" not in status["counts"]
    assert "recipient" in status["counts_privacy"]
    assert "promotion-status" in status["counts_privacy"]
