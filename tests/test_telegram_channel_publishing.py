from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

from telegram_gateway.channel_cards import (
    build_editorial_event,
    build_research_card,
    build_status_card,
    render_channel_card,
)
from telegram_gateway.channel_publishing import (
    ChannelPublicationLedger,
    ChannelPublisher,
    ChannelPublisherConfig,
    ExternalDeliveryDisabled,
    PublicationConflict,
    PublicationStateError,
    normalize_channel_ref,
    prepare_channel_post,
)
from telegram_gateway.envelope import build_s012_envelope
from telegram_gateway.promotion import build_campaign_link, validate_campaign_link
from telegram_gateway.telegram_api import TelegramError


CAMPAIGN_ONE = "k1_" + "A" * 22
CAMPAIGN_TWO = "k1_" + "B" * 22


def _approval(signal_id: str, at: datetime) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema": "s012.signal-lifecycle/0.1",
        "signal_id": signal_id,
        "revision": 1,
        "previous_status": "PENDING",
        "status": "APPROVED",
        "occurred_at": at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "actor_kind": "local_operator",
        "reason_code": "manual_review",
        "scope": "research_distribution_only",
        "execution_allowed": False,
    }
    material = json.dumps(
        event, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    event["event_id"] = "s012-life-" + hashlib.sha256(material).hexdigest()[:32]
    return event


def _card(now: datetime) -> dict[str, Any]:
    signal = {
        "signal_id": "signal-publisher-abcdef12",
        "assessment_id": "assessment-1",
        "event_id": "event-1",
        "market_id": "market-1",
        "market_question": "Will the scheduled decision occur?",
        "signal_type": "S012-OVER",
        "direction": "YES",
        "entry_price": 0.42,
        "target_price": 0.55,
        "stop_price": 0.34,
        "time_horizon_hours": 48,
        "size_usdc": 25.0,
        "size_pct": 0.01,
        "reaction_delta": 0.08,
        "estimated_shift": 0.04,
        "actual_move": 0.12,
        "confidence": 0.68,
        "reasoning": "A bounded paper-only interpretation.",
        "domain": "ECO",
        "passed_concentration": True,
        "passed_anti_patterns": True,
        "risk_notes": ["Check the official resolution wording."],
        "status": "PENDING",
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=12)).isoformat(),
    }
    envelope = build_s012_envelope(
        signal,
        observation_refs=["obs-primary-1"],
        resolution_rules_ref="https://polymarket.com/event/scheduled-decision",
    )
    return build_research_card(
        envelope,
        _approval(signal["signal_id"], now + timedelta(minutes=1)),
        source_links=[
            {
                "observation_ref": "obs-primary-1",
                "label": "Official decision calendar",
                "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                "observed_at": now - timedelta(minutes=1),
                "is_primary": True,
            }
        ],
        market_url="https://polymarket.com/event/scheduled-decision",
        published_at=now + timedelta(minutes=2),
    )


class FakeChannelTransport:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.error: BaseException | None = None
        self.invalid_result = False

    def send_channel_post(
        self,
        channel_ref: int | str,
        text: str,
        *,
        disable_link_preview: bool,
        disable_notification: bool,
        protect_content: bool,
        reply_to_message_id: int | None,
    ) -> Mapping[str, Any]:
        if self.error is not None:
            raise self.error
        item = {
            "channel_ref": channel_ref,
            "text": text,
            "disable_link_preview": disable_link_preview,
            "disable_notification": disable_notification,
            "protect_content": protect_content,
            "reply_to_message_id": reply_to_message_id,
            "message_id": len(self.sent) + 101,
        }
        self.sent.append(item)
        return {} if self.invalid_result else item


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def card(now: datetime) -> dict[str, Any]:
    return _card(now)


@pytest.fixture
def ledger(tmp_path: Path) -> ChannelPublicationLedger:
    value = ChannelPublicationLedger(tmp_path / "private" / "channel.db")
    try:
        yield value
    finally:
        value.close()


def _enabled_publisher(
    ledger: ChannelPublicationLedger, transport: FakeChannelTransport
) -> ChannelPublisher:
    return ChannelPublisher(
        ledger,
        transport,
        ChannelPublisherConfig(external_delivery_enabled=True),
    )


def test_prepare_is_deterministic_and_channel_only(card: Mapping[str, Any]) -> None:
    first = prepare_channel_post(card, "@KingdomDispatch")
    second = prepare_channel_post(card, "@kingdomdispatch")
    assert first == second
    assert first.canonical_channel_ref == "@kingdomdispatch"
    assert first.card_digest == card["integrity"]["content_digest"]
    with pytest.raises(ValueError, match="negative"):
        prepare_channel_post(card, 12345)


def test_prepare_without_campaign_preserves_legacy_text_and_identity(
    card: Mapping[str, Any],
) -> None:
    post = prepare_channel_post(card, "@KingdomDispatch")
    legacy_text = render_channel_card(card)
    legacy_text_digest = "sha256:" + hashlib.sha256(
        legacy_text.encode("utf-8")
    ).hexdigest()
    legacy_material = (
        f"@kingdomdispatch\0{card['card_id']}\0"
        f"{card['integrity']['content_digest']}\0{legacy_text_digest}"
    ).encode("utf-8")

    assert post.campaign_link is None
    assert post.text == legacy_text
    assert post.text_digest == legacy_text_digest
    assert post.publication_id == (
        "kingdom-pub-" + hashlib.sha256(legacy_material).hexdigest()[:32]
    )


@pytest.mark.parametrize(
    "value",
    [
        "http://t.me/KingdomResearchBot?start=" + CAMPAIGN_ONE,
        "https://telegram.me/KingdomResearchBot?start=" + CAMPAIGN_ONE,
        "https://T.ME/KingdomResearchBot?start=" + CAMPAIGN_ONE,
        "https://t.me/KingdomResearch?start=" + CAMPAIGN_ONE,
        "https://t.me/KingdomResearchBot?start=not-a-kingdom-code",
        "https://t.me/KingdomResearchBot?start=" + CAMPAIGN_ONE + "&x=1",
        "https://t.me/KingdomResearchBot?start=" + CAMPAIGN_ONE + "#fragment",
        "https://t.me/KingdomResearchBot?start%3D" + CAMPAIGN_ONE,
    ],
)
def test_campaign_link_shape_is_strict(
    card: Mapping[str, Any], value: str
) -> None:
    with pytest.raises(ValueError, match="campaign link"):
        validate_campaign_link(value)
    with pytest.raises(ValueError, match="campaign link"):
        prepare_channel_post(
            card,
            "@kingdomdispatch",
            campaign_link=value,
        )


def test_campaign_cta_is_deterministic_bounded_and_card_neutral(
    card: Mapping[str, Any],
) -> None:
    original = json.loads(json.dumps(card))
    link = build_campaign_link("KingdomResearchBot", CAMPAIGN_ONE)
    first = prepare_channel_post(
        card,
        "@KingdomDispatch",
        campaign_link=link,
    )
    second = prepare_channel_post(
        card,
        "@kingdomdispatch",
        campaign_link=link,
    )

    assert first == second
    assert first.campaign_link == link
    assert first.text.endswith(
        "Private opt-in: receive KINGDOM research alerts\n"
        f"{link}\n"
        "Opening the bot does not enable alerts; opt in there. /leave stops them."
    )
    assert "No trade was placed." in first.text
    assert "live execution and wallet access are disabled." in first.text
    assert len(first.text) <= 4_096
    assert card == original
    assert first.card_digest == card["integrity"]["content_digest"]


def test_changed_campaign_changes_publication_identity_not_card_identity(
    card: Mapping[str, Any],
) -> None:
    first = prepare_channel_post(
        card,
        "@kingdomdispatch",
        campaign_link=build_campaign_link("KingdomResearchBot", CAMPAIGN_ONE),
    )
    second = prepare_channel_post(
        card,
        "@kingdomdispatch",
        campaign_link=build_campaign_link("KingdomResearchBot", CAMPAIGN_TWO),
    )

    assert first.publication_id != second.publication_id
    assert first.text_digest != second.text_digest
    assert first.card_id == second.card_id == card["card_id"]
    assert first.card_digest == second.card_digest


def test_campaign_metadata_and_text_must_match(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
) -> None:
    first_link = build_campaign_link("KingdomResearchBot", CAMPAIGN_ONE)
    second_link = build_campaign_link("KingdomResearchBot", CAMPAIGN_TWO)
    post = prepare_channel_post(
        card,
        "@kingdomdispatch",
        campaign_link=first_link,
    )

    with pytest.raises(PublicationConflict, match="metadata"):
        ledger.claim(replace(post, campaign_link=second_link))
    with pytest.raises(PublicationConflict, match="metadata"):
        ledger.claim(replace(post, campaign_link=None))
    assert ledger.receipt(post.publication_id) is None


def test_ledger_prevents_republishing_one_card_with_another_campaign(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
    now: datetime,
) -> None:
    transport = FakeChannelTransport()
    publisher = _enabled_publisher(ledger, transport)
    first = publisher.prepare(
        card,
        "@kingdomdispatch",
        campaign_link=build_campaign_link("KingdomResearchBot", CAMPAIGN_ONE),
    )
    competing = publisher.prepare(
        card,
        "@kingdomdispatch",
        campaign_link=build_campaign_link("KingdomResearchBot", CAMPAIGN_TWO),
    )

    publisher.publish(first, attempted_at=now + timedelta(minutes=3))
    with pytest.raises(PublicationConflict):
        publisher.publish(competing, attempted_at=now + timedelta(minutes=4))
    assert len(transport.sent) == 1
    assert ledger.receipt(first.publication_id) is not None
    assert ledger.receipt(competing.publication_id) is None


@pytest.mark.parametrize("value", [True, "channel", "@bad", 0, -(1 << 53)])
def test_channel_identity_rejects_private_or_malformed_targets(value: Any) -> None:
    with pytest.raises(ValueError):
        normalize_channel_ref(value)


def test_external_delivery_is_off_by_default_and_has_no_side_effect(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
) -> None:
    transport = FakeChannelTransport()
    publisher = ChannelPublisher(ledger, transport)
    post = publisher.prepare(card, "@kingdomdispatch")
    with pytest.raises(ExternalDeliveryDisabled):
        publisher.publish(post)
    assert transport.sent == []
    assert ledger.receipt(post.publication_id) is None


def test_publish_is_idempotent_and_keeps_posts_forwardable(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
    now: datetime,
) -> None:
    transport = FakeChannelTransport()
    publisher = _enabled_publisher(ledger, transport)
    post = publisher.prepare(card, -1001234567890)
    first = publisher.publish(post, attempted_at=now + timedelta(minutes=3))
    duplicate = publisher.publish(post, attempted_at=now + timedelta(minutes=4))
    assert first.state == "sent"
    assert first.telegram_message_id == 101
    assert duplicate.duplicate is True
    assert duplicate.telegram_message_id == 101
    assert len(transport.sent) == 1
    assert transport.sent[0]["protect_content"] is False
    assert transport.sent[0]["disable_link_preview"] is True


def test_prepared_text_is_content_bound(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
    now: datetime,
) -> None:
    transport = FakeChannelTransport()
    publisher = _enabled_publisher(ledger, transport)
    post = publisher.prepare(card, "@kingdomdispatch")
    changed = replace(post, text=post.text + "\nBuy now")
    with pytest.raises(PublicationConflict, match="text changed"):
        publisher.publish(changed, attempted_at=now + timedelta(minutes=3))
    assert transport.sent == []


def test_status_update_replies_to_the_superseded_channel_message(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
    now: datetime,
) -> None:
    transport = FakeChannelTransport()
    publisher = _enabled_publisher(ledger, transport)
    root_post = publisher.prepare(card, "@kingdomdispatch")
    publisher.publish(root_post, attempted_at=now + timedelta(minutes=3))

    event = build_editorial_event(
        card,
        status="WITHDRAWN",
        occurred_at=now + timedelta(minutes=4),
        actor_kind="local_operator",
        reason_code="source_conflict",
        summary="The primary source contradicted the original interpretation.",
    )
    update = build_status_card(card, event)
    update_post = publisher.prepare(update, "@kingdomdispatch")
    receipt = publisher.publish(update_post, attempted_at=now + timedelta(minutes=5))

    assert receipt.reply_to_publication_id == root_post.publication_id
    assert transport.sent[1]["reply_to_message_id"] == 101
    assert transport.sent[1]["message_id"] == 102


def test_status_update_requires_predecessor_delivery_in_same_channel(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
    now: datetime,
) -> None:
    transport = FakeChannelTransport()
    publisher = _enabled_publisher(ledger, transport)
    event = build_editorial_event(
        card,
        status="WITHDRAWN",
        occurred_at=now + timedelta(minutes=4),
        actor_kind="local_operator",
        reason_code="source_conflict",
        summary="Withdrawn after review.",
    )
    update = build_status_card(card, event)
    post = publisher.prepare(update, "@kingdomdispatch")
    with pytest.raises(PublicationStateError, match="superseded card"):
        publisher.publish(post, attempted_at=now + timedelta(minutes=5))
    assert transport.sent == []
    assert ledger.receipt(post.publication_id) is None


def test_ambiguous_failure_is_not_retried_without_reconciliation(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
    now: datetime,
) -> None:
    transport = FakeChannelTransport()
    transport.error = TelegramError("timeout", ambiguous=True)
    publisher = _enabled_publisher(ledger, transport)
    post = publisher.prepare(card, "@kingdomdispatch")
    with pytest.raises(TelegramError):
        publisher.publish(post, attempted_at=now + timedelta(minutes=3))
    assert ledger.receipt(post.publication_id).state == "unknown"  # type: ignore[union-attr]

    transport.error = None
    with pytest.raises(PublicationStateError, match="unknown"):
        publisher.publish(post, attempted_at=now + timedelta(minutes=4))
    assert transport.sent == []

    reconciled = ledger.reconcile_unknown(
        post.publication_id,
        sent_message_id=777,
        reconciliation_ref="operator-check:777",
        reconciled_at=now + timedelta(minutes=5),
    )
    duplicate = publisher.publish(post, attempted_at=now + timedelta(minutes=6))
    assert reconciled.state == "sent"
    assert duplicate.duplicate is True
    assert duplicate.telegram_message_id == 777
    assert transport.sent == []


def test_crash_left_pending_receipt_can_be_explicitly_reconciled(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
    now: datetime,
) -> None:
    transport = FakeChannelTransport()
    publisher = _enabled_publisher(ledger, transport)
    post = publisher.prepare(card, "@kingdomdispatch")
    state, _, _ = ledger.claim(post, attempted_at=now + timedelta(minutes=3))
    assert state == "claimed"

    with pytest.raises(PublicationStateError, match="pending"):
        publisher.publish(post, attempted_at=now + timedelta(minutes=4))
    reconciled = ledger.reconcile_unknown(
        post.publication_id,
        sent_message_id=None,
        reconciliation_ref="operator-check:not-found",
        reconciled_at=now + timedelta(minutes=5),
    )
    assert reconciled.state == "failed"
    sent = publisher.publish(
        post,
        attempted_at=now + timedelta(minutes=6),
        retry_failed=True,
    )
    assert sent.state == "sent"
    assert sent.attempt_count == 2


def test_known_failure_needs_explicit_retry(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
    now: datetime,
) -> None:
    transport = FakeChannelTransport()
    transport.error = TelegramError("forbidden", error_code=403, ambiguous=False)
    publisher = _enabled_publisher(ledger, transport)
    post = publisher.prepare(card, "@kingdomdispatch")
    with pytest.raises(TelegramError):
        publisher.publish(post, attempted_at=now + timedelta(minutes=3))
    receipt = ledger.receipt(post.publication_id)
    assert receipt is not None and receipt.state == "failed"

    transport.error = None
    with pytest.raises(PublicationStateError, match="retry_failed"):
        publisher.publish(post, attempted_at=now + timedelta(minutes=4))
    delivered = publisher.publish(
        post,
        attempted_at=now + timedelta(minutes=5),
        retry_failed=True,
    )
    assert delivered.state == "sent"
    assert delivered.attempt_count == 2
    assert len(transport.sent) == 1


def test_invalid_transport_result_is_unknown_not_automatically_retried(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
    now: datetime,
) -> None:
    transport = FakeChannelTransport()
    transport.invalid_result = True
    publisher = _enabled_publisher(ledger, transport)
    post = publisher.prepare(card, "@kingdomdispatch")
    with pytest.raises(PublicationStateError, match="reconciliation"):
        publisher.publish(post, attempted_at=now + timedelta(minutes=3))
    receipt = ledger.receipt(post.publication_id)
    assert receipt is not None and receipt.state == "unknown"
    assert len(transport.sent) == 1


def test_competing_cards_cannot_occupy_same_series_revision(
    card: Mapping[str, Any],
    ledger: ChannelPublicationLedger,
    now: datetime,
) -> None:
    transport = FakeChannelTransport()
    publisher = _enabled_publisher(ledger, transport)
    root = publisher.prepare(card, "@kingdomdispatch")
    publisher.publish(root, attempted_at=now + timedelta(minutes=3))

    first_event = build_editorial_event(
        card,
        status="AMENDED",
        occurred_at=now + timedelta(minutes=4),
        actor_kind="local_operator",
        reason_code="clarification",
        summary="First editorial branch.",
    )
    second_event = build_editorial_event(
        card,
        status="AMENDED",
        occurred_at=now + timedelta(minutes=4),
        actor_kind="local_operator",
        reason_code="clarification",
        summary="Competing editorial branch.",
    )
    first = publisher.prepare(build_status_card(card, first_event), "@kingdomdispatch")
    second = publisher.prepare(build_status_card(card, second_event), "@kingdomdispatch")
    publisher.publish(first, attempted_at=now + timedelta(minutes=5))
    with pytest.raises(PublicationConflict, match="series revision"):
        publisher.publish(second, attempted_at=now + timedelta(minutes=6))
    assert len(transport.sent) == 2


def test_publication_database_is_owner_only(
    ledger: ChannelPublicationLedger,
) -> None:
    assert stat.S_IMODE(ledger.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(ledger.path.parent.stat().st_mode) == 0o700
