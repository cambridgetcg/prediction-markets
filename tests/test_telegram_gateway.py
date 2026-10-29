from __future__ import annotations

import copy
import hashlib
import http.client
import io
import json
import os
import sqlite3
import stat
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

from telegram_gateway.envelope import (
    EnvelopeError,
    build_s012_envelope,
    seal_envelope,
    verify_envelope,
)
from telegram_gateway.cli import _import_without_stopping_control_plane
from telegram_gateway.formatting import render_public_signal, render_research_signal
from telegram_gateway.importer import ImportFailure, import_s012_jsonl
from telegram_gateway.policy import Action, PolicyEngine
from telegram_gateway.service import BotService, ServiceConfig
from telegram_gateway.store import GatewayStore, SignalConflictError
from telegram_gateway.telegram_api import TelegramAPI, TelegramError


def signal_record(
    now: datetime,
    *,
    signal_id: str = "signal-abcdef123456",
    status: str = "PENDING",
    observation_refs: list[str] | None = None,
    concentration_passed: bool = True,
    anti_patterns_passed: bool = True,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "signal_id": signal_id,
        "assessment_id": "assessment-1",
        "event_id": "event-1",
        "market_id": "market-1",
        "market_question": "Will a scheduled event occur by Friday?",
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
        "reasoning": "A bounded synthetic explanation for testing.",
        "domain": "ECO",
        "passed_concentration": concentration_passed,
        "passed_anti_patterns": anti_patterns_passed,
        "risk_notes": ["Verify resolution rules before relying on this analysis."],
        "status": status,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=2)).isoformat(),
    }
    if observation_refs is not None:
        record["observation_refs"] = observation_refs
    return record


def lifecycle_event(
    signal_id: str,
    now: datetime,
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
        "occurred_at": now.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "actor_kind": "local_operator",
        "reason_code": "manual_review" if status == "APPROVED" else "manual_revocation",
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


def approve_signal(
    store: GatewayStore, envelope: Mapping[str, Any], now: datetime
) -> None:
    assert store.apply_signal_lifecycle(
        lifecycle_event(str(envelope["signal_id"]), now), now=now
    ) == "applied"


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture
def store(tmp_path: Path) -> GatewayStore:
    value = GatewayStore(tmp_path / "private" / "gateway.db")
    try:
        yield value
    finally:
        value.close()


def activate_subscription(
    store: GatewayStore,
    now: datetime,
    *,
    user_id: int = 101,
    chat_id: int = 101,
    charge_id: str = "charge-first",
) -> str:
    store.register_recipient(user_id, chat_id, now=now)
    store.accept_terms(user_id, "terms-v1", now=now)
    payload = store.create_invoice_intent(
        telegram_user_id=user_id,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    ok, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=user_id,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="checkout-1",
        current_terms_version="terms-v1",
        now=now,
    )
    assert ok
    store.record_subscription_payment(
        telegram_user_id=user_id,
        private_chat_id=chat_id,
        telegram_payment_charge_id=charge_id,
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=True,
        paid_at=now,
        subscription_expiration_unix=int((now + timedelta(days=30)).timestamp()),
    )
    return payload


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.callbacks: list[tuple[str, str]] = []
        self.checkouts: list[dict[str, Any]] = []
        self.invoice_payloads: list[tuple[str, int]] = []
        self.subscription_edits: list[dict[str, Any]] = []
        self.updates: list[Mapping[str, Any]] = []
        self.send_error: TelegramError | None = None
        self.checkout_error: TelegramError | None = None
        self.edit_result = True
        self.get_updates_error: TelegramError | None = None

    def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: Mapping[str, Any] | None = None,
        protect_content: bool = False,
    ) -> Mapping[str, Any]:
        if self.send_error:
            raise self.send_error
        item = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup,
            "protect_content": protect_content,
            "message_id": len(self.sent) + 1,
        }
        self.sent.append(item)
        return item

    def create_subscription_link(self, *, payload: str, stars_amount: int) -> str:
        self.invoice_payloads.append((payload, stars_amount))
        return "https://t.me/invoice/test"

    def answer_callback(self, callback_query_id: str, text: str = "") -> bool:
        self.callbacks.append((callback_query_id, text))
        return True

    def answer_pre_checkout(
        self,
        pre_checkout_query_id: str,
        *,
        ok: bool,
        error_message: str | None = None,
    ) -> bool:
        if self.checkout_error:
            raise self.checkout_error
        self.checkouts.append(
            {"id": pre_checkout_query_id, "ok": ok, "error": error_message}
        )
        return True

    def edit_subscription(
        self, *, user_id: int, initial_charge_id: str, canceled: bool
    ) -> bool:
        self.subscription_edits.append(
            {
                "user_id": user_id,
                "initial_charge_id": initial_charge_id,
                "canceled": canceled,
            }
        )
        return self.edit_result

    def get_updates(self, *, offset: int, timeout: int) -> list[Mapping[str, Any]]:
        if self.get_updates_error:
            error = self.get_updates_error
            self.get_updates_error = None
            raise error
        return list(self.updates)


def private_message(update_id: int, text: str, *, user_id: int = 101) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": user_id},
            "chat": {"id": user_id, "type": "private"},
            "text": text,
        },
    }


def test_envelope_is_information_only_and_content_bound(now: datetime) -> None:
    envelope = build_s012_envelope(signal_record(now))
    assert verify_envelope(envelope)
    assert envelope["authority"]["execution_allowed"] is False
    assert envelope["authority"]["not_an_authorization"] is True
    assert envelope["integrity"]["proves_authorship"] is False
    assert envelope["integrity"]["proves_truth"] is False
    assert envelope["provenance"]["status"] == "internal_artifact_links_only"
    assert envelope["market"]["resolution_rules_verified"] is False

    tampered = copy.deepcopy(envelope)
    tampered["market"]["question"] = "Changed after sealing"
    assert not verify_envelope(tampered)

    false_claims = []
    for section, field, value in (
        ("market", "resolution_rules_verified", True),
        ("authority", "user_consent_ref", "claimed-consent"),
        ("provenance", "status", "source_observations_linked"),
    ):
        candidate = copy.deepcopy(envelope)
        candidate[section][field] = value
        false_claims.append(candidate)
    for candidate in false_claims:
        with pytest.raises(EnvelopeError):
            seal_envelope(candidate)


def test_subsecond_timestamp_ordering_is_chronological(now: datetime) -> None:
    record = signal_record(now)
    record["created_at"] = "2026-09-02T10:00:00.100000Z"
    record["expires_at"] = "2026-09-02T10:00:00Z"
    with pytest.raises(EnvelopeError, match="later than"):
        build_s012_envelope(record)


def test_observation_refs_must_be_a_list(now: datetime) -> None:
    record = signal_record(now)
    with pytest.raises(EnvelopeError, match="observation_refs"):
        build_s012_envelope(record, observation_refs="observation-1")  # type: ignore[arg-type]


def test_resolution_reference_is_not_claimed_verified(now: datetime) -> None:
    envelope = build_s012_envelope(
        signal_record(now), resolution_rules_ref="https://example.test/rules"
    )
    assert envelope["market"]["resolution_rules_status"] == "reference_present_not_verified"
    assert envelope["market"]["resolution_rules_verified"] is False


def test_observation_references_remain_explicitly_unverified(now: datetime) -> None:
    envelope = build_s012_envelope(
        signal_record(now), observation_refs=["unresolved-observation-reference"]
    )
    assert envelope["provenance"]["status"] == "references_present_not_verified"
    assert envelope["provenance"]["limitations"]


def test_policy_hard_denies_live_execution() -> None:
    policy = PolicyEngine()
    for entitled in (False, True):
        decision = policy.decide(
            Action.PLACE_LIVE_ORDER,
            entitled=entitled,
            explicit_user_request=True,
            amount_usdc=1,
        )
        assert not decision.allowed
        assert decision.code == "LIVE_EXECUTION_DISABLED"


def test_policy_requires_explicit_bounded_paper_action() -> None:
    policy = PolicyEngine()
    assert not policy.decide(Action.RECORD_PAPER_ACTION, amount_usdc=10).allowed
    assert policy.decide(
        Action.RECORD_PAPER_ACTION,
        entitled=True,
        amount_usdc=10,
        explicit_user_request=True,
    ).allowed
    assert not policy.decide(
        Action.RECORD_PAPER_ACTION,
        entitled=True,
        amount_usdc=10_001,
        explicit_user_request=True,
    ).allowed
    assert not policy.decide(
        Action.RECORD_PAPER_ACTION,
        entitled=True,
        amount_usdc=float("nan"),
        explicit_user_request=True,
    ).allowed
    assert not policy.decide(
        Action.RECORD_PAPER_ACTION,
        amount_usdc=10,
        explicit_user_request=True,
    ).allowed


def test_store_is_private_and_signal_ids_are_immutable(
    store: GatewayStore, now: datetime
) -> None:
    envelope = build_s012_envelope(signal_record(now))
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert store.put_signal(envelope, now=now)
    assert not store.put_signal(envelope, now=now)

    changed = copy.deepcopy(envelope)
    changed["forecast"]["reasoning"] = "different"
    changed = seal_envelope(changed)
    with pytest.raises(SignalConflictError):
        store.put_signal(changed, now=now)


def test_base_signal_cannot_self_approve_distribution(
    store: GatewayStore, now: datetime
) -> None:
    envelope = build_s012_envelope(signal_record(now, status="APPROVED"))
    with pytest.raises(ValueError, match="revisioned lifecycle event"):
        store.put_signal(envelope, now=now)
    assert store.latest_signal(now=now) is None


def test_rejected_and_expired_signals_are_not_exposed(
    store: GatewayStore, now: datetime
) -> None:
    rejected = build_s012_envelope(signal_record(now, status="REJECTED"))
    store.put_signal(rejected, now=now)
    assert store.latest_signal(now=now) is None

    active = build_s012_envelope(signal_record(now, signal_id="signal-active-123"))
    store.put_signal(active, now=now)
    approve_signal(store, active, now)
    assert store.latest_signal(now=now)["signal_id"] == "signal-active-123"
    assert store.latest_signal(now=now + timedelta(hours=3)) is None


def test_approved_signal_must_pass_both_risk_gates(
    store: GatewayStore, now: datetime
) -> None:
    failed = build_s012_envelope(
        signal_record(
            now,
            signal_id="signal-risk-failed",
            concentration_passed=False,
        )
    )
    store.put_signal(failed, now=now)
    approve_signal(store, failed, now)
    assert store.latest_signal(now=now) is None
    assert store.resolve_signal_prefix("signal-risk", now=now) is None


def test_signal_prefix_wildcards_are_literal(store: GatewayStore, now: datetime) -> None:
    store.put_signal(build_s012_envelope(signal_record(now)), now=now)
    assert store.resolve_signal_prefix("______", now=now) is None


def test_s012_risk_flags_must_be_real_booleans(now: datetime) -> None:
    record = signal_record(now)
    record["passed_concentration"] = "false"
    with pytest.raises(EnvelopeError, match="passed_concentration"):
        build_s012_envelope(record)


def test_importer_bootstraps_at_eof_then_reads_only_appends(
    store: GatewayStore, tmp_path: Path, now: datetime
) -> None:
    source = tmp_path / "signals.jsonl"
    source.write_text(json.dumps(signal_record(now, signal_id="signal-old-123")) + "\n")
    first = import_s012_jsonl(source, store)
    assert first.bootstrapped
    assert first.imported == 0

    with source.open("a") as handle:
        handle.write(json.dumps(signal_record(now, signal_id="signal-new-123")) + "\n")
    second = import_s012_jsonl(source, store)
    assert second.imported == 1
    assert store.counts(now=now)["signals"] == 1

    third = import_s012_jsonl(source, store)
    assert third.complete_records == 0


def test_importer_bootstrap_during_append_discards_only_unaligned_fragment(
    store: GatewayStore, tmp_path: Path, now: datetime
) -> None:
    source = tmp_path / "signals.jsonl"
    interrupted = json.dumps(signal_record(now, signal_id="signal-interrupted-123"))
    split = len(interrupted) // 2
    source.write_text(interrupted[:split])

    first = import_s012_jsonl(source, store)
    assert first.bootstrapped
    assert first.trailing_partial_ignored

    next_record = json.dumps(signal_record(now, signal_id="signal-after-race-123"))
    with source.open("a") as handle:
        handle.write(interrupted[split:] + "\n" + next_record + "\n")

    second = import_s012_jsonl(source, store)
    assert second.imported == 1
    assert second.complete_records == 1
    approve_signal(
        store,
        build_s012_envelope(
            signal_record(now, signal_id="signal-after-race-123")
        ),
        now,
    )
    assert store.resolve_signal_prefix("signal-interrupted", now=now) is None
    assert store.resolve_signal_prefix("signal-after-race", now=now) is not None


def test_importer_defers_partial_tail_and_rejects_bad_complete_record(
    store: GatewayStore, tmp_path: Path, now: datetime
) -> None:
    source = tmp_path / "signals.jsonl"
    source.write_bytes(b"")
    import_s012_jsonl(source, store)
    payload = json.dumps(signal_record(now, signal_id="signal-tail-123"))
    source.write_text(payload)
    partial = import_s012_jsonl(source, store)
    assert partial.trailing_partial_ignored
    assert partial.imported == 0

    with source.open("a") as handle:
        handle.write("\n")
    complete = import_s012_jsonl(source, store)
    assert complete.imported == 1

    with source.open("a") as handle:
        handle.write("{bad json}\n")
    with pytest.raises(ImportFailure, match="invalid complete JSONL record"):
        import_s012_jsonl(source, store)


def test_importer_reports_non_object_json_as_import_failure(
    store: GatewayStore, tmp_path: Path
) -> None:
    source = tmp_path / "signals.jsonl"
    source.write_text("[]\n")
    with pytest.raises(ImportFailure, match="invalid complete JSONL record"):
        import_s012_jsonl(source, store, backfill=True)


def test_numeric_poison_is_quarantined_without_stopping_control_plane(
    store: GatewayStore, tmp_path: Path, now: datetime
) -> None:
    source = tmp_path / "signals.jsonl"
    source.write_text("")
    import_s012_jsonl(source, store)
    poisoned = signal_record(now)
    poisoned["size_usdc"] = 10**400
    source.write_text(json.dumps(poisoned) + "\n")
    imported, error = _import_without_stopping_control_plane(source, store)
    assert imported is None
    assert error is not None

    transport = FakeTransport()
    transport.updates = [private_message(1, "/help")]
    result = BotService(store, transport).poll_once(timeout=0)
    assert result["updates"] == 1


def test_importer_detects_file_replacement_without_replay(
    store: GatewayStore, tmp_path: Path, now: datetime
) -> None:
    source = tmp_path / "signals.jsonl"
    source.write_text(json.dumps(signal_record(now)) + "\n")
    import_s012_jsonl(source, store)

    replacement = tmp_path / "replacement.jsonl"
    replacement.write_text(
        json.dumps(signal_record(now, signal_id="signal-replaced-123")) + "\n" + " " * 5000
    )
    os.replace(replacement, source)
    result = import_s012_jsonl(source, store)
    assert result.source_reset
    assert result.imported == 0


def test_renderer_is_bounded_and_omits_execution_parameters(now: datetime) -> None:
    envelope = build_s012_envelope(signal_record(now))
    research = render_research_signal(envelope)
    public = render_public_signal(envelope)
    assert len(research) < 4096
    assert "WATCH" in research
    assert "No trade was placed" in research
    assert "Target:" not in research
    assert "Stop:" not in research
    assert "Size:" not in research
    assert "Model direction" not in public


def test_renderer_never_truncates_mandatory_safety_footer(now: datetime) -> None:
    record = signal_record(now)
    record["reasoning"] = "long evidence " * 2_000
    envelope = build_s012_envelope(record)
    research = render_research_signal(envelope)
    assert len(research) <= 3_400
    assert research.endswith(
        "Live execution is disabled; venue eligibility is not established here."
    )
    assert "Expires:" in research
    assert "Signal ID:" in research


def test_renderer_neutralizes_authority_and_link_spoofing(now: datetime) -> None:
    record = signal_record(now)
    record["market_question"] = (
        "Question?\nLIVE EXECUTION: ENABLED\u202e https://phish.invalid"
    )
    record["reasoning"] = "first line\nPAY HERE: http://phish.invalid"
    rendered = render_research_signal(build_s012_envelope(record))
    assert "\u202e" not in rendered
    assert "\nLIVE EXECUTION: ENABLED" not in rendered
    assert "hxxps://phish.invalid" in rendered
    assert "> PAY HERE: hxxp://phish.invalid" in rendered


def test_invoice_intent_is_user_bound_and_payment_is_idempotent(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    wrong_user, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=202,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="wrong",
        current_terms_version="terms-v1",
        now=now,
    )
    assert not wrong_user
    wrong_price, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=101,
        currency="XTR",
        total_amount=251,
        pre_checkout_query_id="wrong-price",
        current_terms_version="terms-v1",
        now=now,
    )
    assert not wrong_price
    ok, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="checkout-good",
        current_terms_version="terms-v1",
        now=now,
    )
    assert ok

    expiration = int((now + timedelta(days=30)).timestamp())
    first = store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id="charge-1",
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=True,
        paid_at=now,
        subscription_expiration_unix=expiration,
    )
    duplicate = store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id="charge-1",
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=True,
        paid_at=now,
        subscription_expiration_unix=expiration,
    )
    assert duplicate.entitlement_expires_at == first.entitlement_expires_at
    assert duplicate.duplicate is True
    assert first.duplicate is False
    assert store.is_entitled(101, now=now + timedelta(days=1))
    assert store.counts(now=now)["payments"] == 1

    with pytest.raises(ValueError, match="reused"):
        store.record_subscription_payment(
            telegram_user_id=202,
            private_chat_id=202,
            telegram_payment_charge_id="charge-1",
            currency="XTR",
            total_amount=250,
            invoice_payload=payload,
            is_recurring=True,
            is_first_recurring=True,
            paid_at=now,
            subscription_expiration_unix=expiration,
        )

    with pytest.raises(ValueError):
        store.record_subscription_payment(
            telegram_user_id=101,
            private_chat_id=101,
            telegram_payment_charge_id="charge-1",
            currency="XTR",
            total_amount=250,
            invoice_payload=payload,
            is_recurring=False,
            is_first_recurring=False,
            paid_at=now,
            subscription_expiration_unix=expiration,
        )


def test_payment_requires_telegram_expiry_and_refund_revokes(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    refund = store.begin_payment_refund(
        "charge-first",
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        now=now + timedelta(days=1),
    )
    assert refund
    assert not store.is_entitled(101, now=now + timedelta(days=1))
    assert store.invoice_intent(payload)["state"] == "paid"
    assert store.recipient_deletion_block(101, now=now + timedelta(days=31)) == (
        "renewal_cancellation_pending"
    )


def test_delayed_renewal_cannot_shorten_entitlement(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    processing_time = now + timedelta(days=59)
    later = int((now + timedelta(days=90)).timestamp())
    earlier = int((now + timedelta(days=60)).timestamp())
    for charge, expiration in (("renewal-later", later), ("renewal-delayed", earlier)):
        store.record_subscription_payment(
            telegram_user_id=101,
            private_chat_id=101,
            telegram_payment_charge_id=charge,
            currency="XTR",
            total_amount=250,
            invoice_payload=payload,
            is_recurring=True,
            is_first_recurring=False,
            paid_at=processing_time,
            subscription_expiration_unix=expiration,
        )
    assert store.recipient_status(101)["entitlement_expires_at"] == (
        now + timedelta(days=90)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")


def test_refunding_old_period_keeps_later_unreffunded_access(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id="renewal-later",
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=False,
        paid_at=now + timedelta(days=29),
        subscription_expiration_unix=int((now + timedelta(days=60)).timestamp()),
    )
    refund = store.begin_payment_refund(
        "charge-first",
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        now=now + timedelta(days=31),
    )
    assert refund["remaining_entitlement_expires_at"] == (
        now + timedelta(days=60)
    ).isoformat(timespec="microseconds").replace("+00:00", "Z")
    assert store.is_entitled(101, now=now + timedelta(days=31))


def test_payment_expiration_overflow_is_a_reconciliation_error(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    with pytest.raises(ValueError, match="supported range"):
        store.record_subscription_payment(
            telegram_user_id=101,
            private_chat_id=101,
            telegram_payment_charge_id="charge-overflow",
            currency="XTR",
            total_amount=250,
            invoice_payload=payload,
            is_recurring=True,
            is_first_recurring=True,
            paid_at=now,
            subscription_expiration_unix=10**100,
        )


def test_refund_before_payment_is_retained_and_prevents_access(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    ok, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="checkout-refund-first",
        current_terms_version="terms-v1",
        now=now,
    )
    assert ok
    assert store.begin_payment_refund(
        "charge-refunded-first",
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        now=now,
    ) is None
    result = store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id="charge-refunded-first",
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=True,
        paid_at=now,
        subscription_expiration_unix=int((now + timedelta(days=30)).timestamp()),
    )
    assert result.refunded
    assert result.cancellation_required
    assert result.entitlement_expires_at is None
    assert not store.is_entitled(101, now=now)


def test_subscription_state_before_payment_is_applied(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    ok, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="checkout-state-first",
        current_terms_version="terms-v1",
        now=now,
    )
    assert ok
    assert store.apply_subscription_update(
        telegram_user_id=101,
        invoice_payload=payload,
        state="canceled",
        update_id=10,
        now=now,
    )
    store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id="charge-state-first",
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=True,
        paid_at=now,
        subscription_expiration_unix=int((now + timedelta(days=30)).timestamp()),
        telegram_update_id=11,
    )
    assert store.latest_subscription(101)["renewal_state"] == "canceled"


def test_refund_and_canceled_state_before_payment_requires_reconfirmation(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    ok, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="checkout-canceled-refund-first",
        current_terms_version="terms-v1",
        now=now,
    )
    assert ok
    store.apply_subscription_update(
        telegram_user_id=101,
        invoice_payload=payload,
        state="canceled",
        update_id=10,
        now=now,
    )
    assert store.begin_payment_refund(
        "charge-canceled-refund-first",
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        now=now,
    ) is None
    result = store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id="charge-canceled-refund-first",
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=True,
        paid_at=now,
        subscription_expiration_unix=int((now + timedelta(days=30)).timestamp()),
        telegram_update_id=11,
    )
    subscription = store.latest_subscription(101)
    assert subscription["renewal_state"] == "canceled"
    assert subscription["cancellation_pending_at"] is not None
    assert result.cancellation_required


def test_invalid_refund_first_cannot_poison_later_payment(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    ok, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="checkout-valid-after-bad-refund",
        current_terms_version="terms-v1",
        now=now,
    )
    assert ok
    with pytest.raises(ValueError):
        store.begin_payment_refund(
            "charge-not-poisoned",
            telegram_user_id=101,
            currency="",
            total_amount=0,
            invoice_payload="",
            now=now,
        )
    assert store.conn.execute("SELECT COUNT(*) FROM refund_events").fetchone()[0] == 0
    result = store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id="charge-not-poisoned",
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=True,
        paid_at=now,
        subscription_expiration_unix=int((now + timedelta(days=30)).timestamp()),
    )
    assert result.entitlement_expires_at is not None


def test_payment_update_watermark_rejects_delayed_failed_state(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    assert store.apply_subscription_update(
        telegram_user_id=101,
        invoice_payload=payload,
        state="failed",
        update_id=20,
        now=now + timedelta(days=29),
    )
    store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id="renewal-after-failure",
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=False,
        paid_at=now + timedelta(days=29),
        subscription_expiration_unix=int((now + timedelta(days=60)).timestamp()),
        telegram_update_id=30,
    )
    assert store.latest_subscription(101)["renewal_state"] == "active"
    assert not store.apply_subscription_update(
        telegram_user_id=101,
        invoice_payload=payload,
        state="failed",
        update_id=25,
        now=now + timedelta(days=29, seconds=1),
    )
    assert store.latest_subscription(101)["renewal_state"] == "active"


def test_refund_cancellation_intent_survives_active_event_and_renewal(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    refund = store.begin_payment_refund(
        "charge-first",
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        now=now + timedelta(days=1),
    )
    assert refund and refund["cancellation_required"]
    assert store.set_subscription_state(
        telegram_user_id=101,
        invoice_payload=payload,
        state="canceled",
        now=now + timedelta(days=1),
    )
    assert not store.apply_subscription_update(
        telegram_user_id=101,
        invoice_payload=payload,
        state="active",
        update_id=20,
        now=now + timedelta(days=2),
    )
    result = store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id="charge-reenabled",
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=False,
        paid_at=now + timedelta(days=2),
        subscription_expiration_unix=int((now + timedelta(days=32)).timestamp()),
        telegram_update_id=21,
    )
    assert result.entitlement_expires_at == now + timedelta(days=32)
    assert store.latest_subscription(101)["renewal_state"] == "canceled"


def test_paid_invoice_cannot_be_reused_as_a_new_first_charge(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    store.set_subscription_state(
        telegram_user_id=101,
        invoice_payload=payload,
        state="canceled",
        now=now + timedelta(days=31),
    )
    with pytest.raises(ValueError, match="pre-checkout"):
        store.record_subscription_payment(
            telegram_user_id=101,
            private_chat_id=101,
            telegram_payment_charge_id="second-first-charge",
            currency="XTR",
            total_amount=250,
            invoice_payload=payload,
            is_recurring=True,
            is_first_recurring=True,
            paid_at=now + timedelta(days=31),
            subscription_expiration_unix=int((now + timedelta(days=61)).timestamp()),
        )


def test_failed_expired_subscription_allows_fresh_checkout(
    store: GatewayStore, now: datetime
) -> None:
    old_payload = activate_subscription(store, now)
    assert store.apply_subscription_update(
        telegram_user_id=101,
        invoice_payload=old_payload,
        state="failed",
        update_id=20,
        now=now + timedelta(days=31),
    )
    store.accept_terms(101, "terms-v1", now=now + timedelta(days=31))
    new_payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now + timedelta(days=31),
    )
    assert new_payload != old_payload


def test_delayed_old_invoice_renewal_cannot_attach_to_new_subscription(
    store: GatewayStore, now: datetime
) -> None:
    old_payload = activate_subscription(store, now)
    store.set_subscription_state(
        telegram_user_id=101,
        invoice_payload=old_payload,
        state="canceled",
        now=now + timedelta(days=1),
    )
    later = now + timedelta(days=31)
    store.accept_terms(101, "terms-v1", now=later)
    new_payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=later,
    )
    ok, _ = store.reserve_invoice_intent(
        payload=new_payload,
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="checkout-new",
        current_terms_version="terms-v1",
        now=later,
    )
    assert ok
    store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id="charge-new",
        currency="XTR",
        total_amount=250,
        invoice_payload=new_payload,
        is_recurring=True,
        is_first_recurring=True,
        paid_at=later,
        subscription_expiration_unix=int((later + timedelta(days=30)).timestamp()),
    )
    with pytest.raises(ValueError, match="matching subscription invoice"):
        store.record_subscription_payment(
            telegram_user_id=101,
            private_chat_id=101,
            telegram_payment_charge_id="old-delayed-renewal",
            currency="XTR",
            total_amount=250,
            invoice_payload=old_payload,
            is_recurring=True,
            is_first_recurring=False,
            paid_at=later + timedelta(days=1),
            subscription_expiration_unix=int((later + timedelta(days=20)).timestamp()),
        )


def test_privacy_notice_is_not_inferred_from_registration(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    row = store.conn.execute(
        "SELECT privacy_notice_at FROM recipients WHERE telegram_user_id = 101"
    ).fetchone()
    assert row["privacy_notice_at"] is None
    store.mark_privacy_notice(101, now=now)
    row = store.conn.execute(
        "SELECT privacy_notice_at FROM recipients WHERE telegram_user_id = 101"
    ).fetchone()
    assert row["privacy_notice_at"] is not None


def test_positive_price_alone_cannot_enable_stars_commerce(
    store: GatewayStore,
) -> None:
    transport = FakeTransport()
    config = ServiceConfig(stars_amount=250, terms_version="terms-v1")
    service = BotService(store, transport, config)

    assert config.commerce_enabled is False
    assert service.handle_update(private_message(1, "/subscribe"))
    assert transport.invoice_payloads == []
    assert "disabled" in transport.sent[-1]["text"].lower()


def test_bot_subscription_flow_and_paper_only_commands(
    store: GatewayStore, now: datetime
) -> None:
    envelope = build_s012_envelope(signal_record(now))
    store.put_signal(envelope, now=now)
    approve_signal(store, envelope, now)
    transport = FakeTransport()
    service = BotService(
        store,
        transport,
        ServiceConfig(
            stars_amount=250,
            enable_stars_commerce=True,
            terms_version="terms-v1",
        ),
    )

    assert service.handle_update(private_message(1, "/start"))
    assert "no wallet" in transport.sent[-1]["text"]

    service.handle_update(private_message(2, "/subscribe"))
    callback_data = transport.sent[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert callback_data.startswith("terms_accept:")

    service.handle_update(
        {
            "update_id": 3,
            "callback_query": {
                "id": "callback-1",
                "from": {"id": 101},
                "data": callback_data,
                "message": {"chat": {"id": 101, "type": "private"}},
            },
        }
    )
    payload, amount = transport.invoice_payloads[-1]
    assert amount == 250

    service.handle_update(
        {
            "update_id": 4,
            "pre_checkout_query": {
                "id": "checkout-1",
                "from": {"id": 101},
                "currency": "XTR",
                "total_amount": 250,
                "invoice_payload": payload,
            },
        }
    )
    assert transport.checkouts[-1]["ok"] is True

    service.handle_update(
        {
            "update_id": 5,
            "message": {
                "message_id": 5,
                "from": {"id": 101},
                "chat": {"id": 101, "type": "private"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 250,
                    "invoice_payload": payload,
                    "subscription_expiration_date": int(
                        (now + timedelta(days=30)).timestamp()
                    ),
                    "is_recurring": True,
                    "is_first_recurring": True,
                    "telegram_payment_charge_id": "charge-service-1",
                    "provider_payment_charge_id": "provider-opaque",
                },
            },
        }
    )
    assert store.is_entitled(101)

    service.handle_update(private_message(6, "/latest"))
    assert "Model direction" in transport.sent[-1]["text"]
    assert transport.sent[-1]["protect_content"] is True

    service.handle_update(private_message(7, "/trade signal-abcdef123456"))
    assert "LIVE_EXECUTION_DISABLED" in transport.sent[-1]["text"]

    service.handle_update(private_message(8, "/paper signal-abcdef 75"))
    assert "No wallet or market was contacted" in transport.sent[-1]["text"]
    assert store.counts()["paper_actions"] == 1

    service.handle_update(private_message(9, "/cancel"))
    assert transport.subscription_edits[-1]["canceled"] is True
    assert "paid access remains" in transport.sent[-1]["text"]

    service.handle_update(private_message(10, "/delete_me"))
    assert "cannot be deleted during a paid period" in transport.sent[-1]["text"]


def test_explicit_cancel_dominates_a_delayed_active_event(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    assert store.apply_subscription_update(
        telegram_user_id=101,
        invoice_payload=payload,
        state="canceled",
        update_id=10,
        now=now,
    )
    transport = FakeTransport()
    service = BotService(store, transport)

    assert service.handle_update(private_message(20, "/cancel"))
    assert len(transport.subscription_edits) == 1
    subscription = store.latest_subscription(101)
    assert subscription["renewal_state"] == "canceled"
    assert subscription["last_provider_update_id"] == 20

    assert service.handle_update(
        {
            "update_id": 15,
            "subscription": {
                "user": {"id": 101},
                "state": "active",
                "invoice_payload": payload,
            },
        }
    )
    subscription = store.latest_subscription(101)
    assert subscription["renewal_state"] == "canceled"
    assert subscription["last_provider_update_id"] == 20


def test_refund_reconfirms_cancel_and_dominates_delayed_active_event(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    assert store.apply_subscription_update(
        telegram_user_id=101,
        invoice_payload=payload,
        state="canceled",
        update_id=10,
        now=now,
    )
    transport = FakeTransport()
    service = BotService(store, transport)

    assert service.handle_update(
        {
            "update_id": 20,
            "message": {
                "message_id": 20,
                "from": {"id": 101},
                "chat": {"id": 101, "type": "private"},
                "refunded_payment": {
                    "currency": "XTR",
                    "total_amount": 250,
                    "invoice_payload": payload,
                    "telegram_payment_charge_id": "charge-first",
                },
            },
        }
    )
    assert len(transport.subscription_edits) == 1
    subscription = store.latest_subscription(101)
    assert subscription["renewal_state"] == "canceled"
    assert subscription["last_provider_update_id"] == 20

    assert service.handle_update(
        {
            "update_id": 15,
            "subscription": {
                "user": {"id": 101},
                "state": "active",
                "invoice_payload": payload,
            },
        }
    )
    subscription = store.latest_subscription(101)
    assert subscription["renewal_state"] == "canceled"
    assert subscription["last_provider_update_id"] == 20


def test_cancel_barrier_rejects_higher_active_event_from_same_fetched_batch(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    transport = FakeTransport()
    transport.updates = [
        private_message(20, "/cancel"),
        {
            "update_id": 21,
            "subscription": {
                "user": {"id": 101},
                "state": "active",
                "invoice_payload": payload,
            },
        },
    ]
    service = BotService(store, transport)

    result = service.poll_once(timeout=0)
    assert result["updates"] == 2
    assert len(transport.subscription_edits) == 2
    subscription = store.latest_subscription(101)
    assert subscription["renewal_state"] == "canceled"
    assert subscription["cancellation_intent_at"] is not None
    assert subscription["cancellation_pending_at"] is None
    assert subscription["last_provider_update_id"] == 21


def test_refund_barrier_rejects_higher_active_event_from_same_fetched_batch(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    transport = FakeTransport()
    transport.updates = [
        {
            "update_id": 20,
            "message": {
                "message_id": 20,
                "from": {"id": 101},
                "chat": {"id": 101, "type": "private"},
                "refunded_payment": {
                    "currency": "XTR",
                    "total_amount": 250,
                    "invoice_payload": payload,
                    "telegram_payment_charge_id": "charge-first",
                },
            },
        },
        {
            "update_id": 21,
            "subscription": {
                "user": {"id": 101},
                "state": "active",
                "invoice_payload": payload,
            },
        },
    ]
    service = BotService(store, transport)

    result = service.poll_once(timeout=0)
    assert result["updates"] == 2
    assert len(transport.subscription_edits) == 2
    subscription = store.latest_subscription(101)
    assert subscription["renewal_state"] == "canceled"
    assert subscription["cancellation_intent_at"] is not None
    assert subscription["cancellation_pending_at"] is None
    assert subscription["last_provider_update_id"] == 21
    assert not store.is_entitled(101, now=now)


def test_reactivation_cancel_failure_keeps_deletion_blocked(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    transport = FakeTransport()
    service = BotService(store, transport)
    assert service.handle_update(private_message(20, "/cancel"))

    transport.edit_result = False
    assert service.handle_update(
        {
            "update_id": 21,
            "subscription": {
                "user": {"id": 101},
                "state": "active",
                "invoice_payload": payload,
            },
        }
    )
    subscription = store.latest_subscription(101)
    assert subscription["renewal_state"] == "canceled"
    assert subscription["cancellation_pending_at"] is not None
    assert store.recipient_deletion_block(101) == "renewal_cancellation_pending"
    assert service.handle_update(private_message(22, "/status"))
    assert "Renewal: cancellation pending (unconfirmed" in transport.sent[-1]["text"]


def test_renewal_payment_preserves_and_reconfirms_cancellation_intent(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    transport = FakeTransport()
    service = BotService(store, transport)
    assert service.handle_update(private_message(20, "/cancel"))

    assert service.handle_update(
        {
            "update_id": 21,
            "message": {
                "message_id": 21,
                "from": {"id": 101},
                "chat": {"id": 101, "type": "private"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": 250,
                    "invoice_payload": payload,
                    "subscription_expiration_date": int(
                        (now + timedelta(days=31)).timestamp()
                    ),
                    "is_recurring": True,
                    "is_first_recurring": False,
                    "telegram_payment_charge_id": "renewal-after-cancel-intent",
                    "provider_payment_charge_id": "provider-opaque-renewal",
                },
            },
        }
    )
    assert len(transport.subscription_edits) == 2
    subscription = store.latest_subscription(101)
    assert subscription["renewal_state"] == "canceled"
    assert subscription["cancellation_intent_at"] is not None
    assert subscription["cancellation_pending_at"] is None
    assert subscription["last_provider_update_id"] == 21
    assert "Renewal remains canceled" in transport.sent[-1]["text"]


def test_unconfirmed_reactivation_cancel_blocks_replacement_checkout(
    store: GatewayStore, now: datetime
) -> None:
    expired_start = now - timedelta(days=31)
    payload = activate_subscription(store, expired_start)
    transport = FakeTransport()
    service = BotService(
        store,
        transport,
        ServiceConfig(
            stars_amount=250,
            enable_stars_commerce=True,
            terms_version="terms-v1",
        ),
    )
    assert service.handle_update(private_message(20, "/cancel"))

    transport.edit_result = False
    assert service.handle_update(
        {
            "update_id": 21,
            "subscription": {
                "user": {"id": 101},
                "state": "active",
                "invoice_payload": payload,
            },
        }
    )
    with pytest.raises(ValueError, match="provider reconciliation"):
        store.create_invoice_intent(
            telegram_user_id=101,
            plan_code="research",
            total_amount=250,
            terms_version="terms-v1",
            now=now,
        )

    service.handle_update(private_message(22, "/subscribe"))
    callback_data = transport.sent[-1]["reply_markup"]["inline_keyboard"][0][0][
        "callback_data"
    ]
    service.handle_update(
        {
            "update_id": 23,
            "callback_query": {
                "id": "replacement-blocked",
                "from": {"id": 101},
                "data": callback_data,
                "message": {"chat": {"id": 101, "type": "private"}},
            },
        }
    )
    assert "not yet confirmed at Telegram" in transport.sent[-1]["text"]


def test_free_user_cannot_use_paper_to_reveal_direction(
    store: GatewayStore, now: datetime
) -> None:
    envelope = build_s012_envelope(signal_record(now))
    store.put_signal(envelope, now=now)
    approve_signal(store, envelope, now)
    transport = FakeTransport()
    service = BotService(store, transport)
    service.handle_update(private_message(1, "/latest"))
    assert "Model direction" not in transport.sent[-1]["text"]
    service.handle_update(private_message(2, "/paper signal-abcdef 10"))
    assert "SUBSCRIPTION_REQUIRED" in transport.sent[-1]["text"]
    assert " at " not in transport.sent[-1]["text"]
    assert store.counts()["paper_actions"] == 0


def test_private_membership_update_blocks_the_human_recipient(
    store: GatewayStore, now: datetime
) -> None:
    activate_subscription(store, now)
    transport = FakeTransport()
    service = BotService(store, transport)
    service.handle_update(
        {
            "update_id": 10,
            "my_chat_member": {
                "from": {"id": 101},
                "chat": {"id": 101, "type": "private"},
                "new_chat_member": {
                    "user": {"id": 999_999, "is_bot": True},
                    "status": "kicked",
                },
            },
        }
    )
    assert store.active_recipients(now=now) == []


def test_deletion_requires_cancellation_even_after_period_end(
    store: GatewayStore, now: datetime
) -> None:
    activate_subscription(store, now)
    future = now + timedelta(days=31)
    assert store.recipient_deletion_block(101, now=future) == "renewal_not_canceled"
    store.set_subscription_state(
        telegram_user_id=101,
        invoice_payload=store.latest_subscription(101)["invoice_payload"],
        state="canceled",
        now=future,
    )
    assert store.recipient_deletion_block(101, now=future) is None


def test_deletion_waits_for_open_invoice_intent(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    assert store.recipient_deletion_block(101, now=now) == "invoice_pending"
    assert store.recipient_deletion_block(101, now=now + timedelta(minutes=16)) is None


def test_reserved_checkout_survives_restart_and_rejects_manual_reconciliation(
    tmp_path: Path, now: datetime
) -> None:
    db = tmp_path / "private" / "gateway.db"
    started = now - timedelta(minutes=20)
    with GatewayStore(db) as first:
        first.register_recipient(101, 101, now=started)
        first.accept_terms(101, "terms-v1", now=started)
        payload = first.create_invoice_intent(
            telegram_user_id=101,
            plan_code="research",
            total_amount=250,
            terms_version="terms-v1",
            now=started,
        )
        ok, _ = first.reserve_invoice_intent(
            payload=payload,
            telegram_user_id=101,
            currency="XTR",
            total_amount=250,
            pre_checkout_query_id="checkout-before-restart",
            current_terms_version="terms-v1",
            now=started + timedelta(minutes=10),
        )
        assert ok

    with GatewayStore(db) as reopened:
        assert reopened.invoice_intent(payload)["state"] == "reserved"
        assert reopened.recipient_deletion_block(101, now=now) == (
            "checkout_reconciliation_pending"
        )
        with pytest.raises(ValueError, match="structured provider evidence"):
            reopened.reconcile_reserved_invoice_no_charge(
                payload, reconciliation_ref="telegram-audit:no-charge", now=now
            )
        assert reopened.invoice_intent(payload)["state"] == "reserved"
        assert reopened.recipient_deletion_block(101, now=now) == (
            "checkout_reconciliation_pending"
        )


def test_unmatched_refund_blocks_deletion_and_manual_reconciliation(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    ok, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="checkout-refund-unmatched",
        current_terms_version="terms-v1",
        now=now,
    )
    assert ok
    assert store.begin_payment_refund(
        "charge-unmatched-refund",
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        now=now,
    ) is None
    assert store.recipient_deletion_block(101, now=now) == (
        "refund_reconciliation_pending"
    )
    with pytest.raises(ValueError, match="structured provider evidence"):
        store.reconcile_reserved_invoice_no_charge(
            payload, reconciliation_ref="telegram-audit:no-charge", now=now
        )
    with pytest.raises(ValueError, match="structured provider evidence"):
        store.reconcile_unmatched_refund(
            "charge-unmatched-refund",
            reconciliation_ref="telegram-audit:fully-refunded-and-canceled",
            now=now,
        )
    assert store.recipient_deletion_block(101, now=now) == (
        "refund_reconciliation_pending"
    )


def test_manual_unmatched_renewal_reconciliation_cannot_assert_cancellation(
    store: GatewayStore, now: datetime
) -> None:
    payload = activate_subscription(store, now)
    assert store.begin_payment_refund(
        "unmatched-renewal-refund",
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        now=now + timedelta(days=29),
    ) is None
    with pytest.raises(ValueError, match="structured provider evidence"):
        store.reconcile_unmatched_refund(
            "unmatched-renewal-refund",
            reconciliation_ref="telegram-audit:refund-and-renewal-canceled",
            now=now + timedelta(days=29),
        )
    assert store.latest_subscription(101)["renewal_state"] == "active"
    assert store.recipient_deletion_block(101, now=now + timedelta(days=31)) == (
        "refund_reconciliation_pending"
    )


def test_wrong_checkout_is_rejected_without_entitlement(
    store: GatewayStore,
) -> None:
    transport = FakeTransport()
    service = BotService(
        store,
        transport,
        ServiceConfig(
            stars_amount=250,
            enable_stars_commerce=True,
            terms_version="terms-v1",
        ),
    )
    service.handle_update(
        {
            "update_id": 1,
            "pre_checkout_query": {
                "id": "checkout-bad",
                "from": {"id": 101},
                "currency": "XTR",
                "total_amount": 250,
                "invoice_payload": "sub:v1:not-real",
            },
        }
    )
    assert transport.checkouts[-1]["ok"] is False
    assert not store.is_entitled(101)


def test_ambiguous_send_is_not_automatically_retried(
    store: GatewayStore, now: datetime
) -> None:
    envelope = build_s012_envelope(signal_record(now))
    store.put_signal(envelope, now=now)
    approve_signal(store, envelope, now)
    activate_subscription(store, now)
    store.set_research_alert_consent(
        101, subscribed=True, telegram_update_id=9001, now=now
    )
    transport = FakeTransport()
    transport.send_error = TelegramError("lost response", ambiguous=True)
    service = BotService(
        store,
        transport,
        ServiceConfig(stars_amount=250, enable_stars_commerce=True),
    )
    result = service.broadcast_pending()
    assert result == {"sent": 0, "failed": 0, "unknown": 1}
    assert store.pending_deliveries(now=now) == []


def test_successful_broadcast_is_deduplicated(
    store: GatewayStore, now: datetime
) -> None:
    envelope = build_s012_envelope(signal_record(now))
    store.put_signal(envelope, now=now)
    approve_signal(store, envelope, now)
    activate_subscription(store, now)
    store.set_research_alert_consent(
        101, subscribed=True, telegram_update_id=9002, now=now
    )
    transport = FakeTransport()
    service = BotService(
        store,
        transport,
        ServiceConfig(stars_amount=250, enable_stars_commerce=True),
    )
    assert service.broadcast_pending()["sent"] == 1
    assert service.broadcast_pending()["sent"] == 0


def test_database_tampering_quarantines_signal(
    store: GatewayStore, now: datetime
) -> None:
    envelope = build_s012_envelope(signal_record(now))
    store.put_signal(envelope, now=now)
    approve_signal(store, envelope, now)
    changed = copy.deepcopy(envelope)
    changed["market"]["question"] = "Tampered question"
    store.conn.execute(
        "UPDATE signals SET envelope_json = ? WHERE signal_id = ?",
        (json.dumps(changed), envelope["signal_id"]),
    )
    store.conn.commit()
    assert store.latest_signal(now=now) is None
    assert store.conn.execute(
        "SELECT distributable FROM signals WHERE signal_id = ?", (envelope["signal_id"],)
    ).fetchone()[0] == 0


def test_update_ids_are_idempotent(store: GatewayStore) -> None:
    transport = FakeTransport()
    service = BotService(store, transport)
    update = private_message(1, "/start")
    assert service.handle_update(update)
    assert not service.handle_update(update)
    assert len(transport.sent) == 1


def test_update_offset_never_moves_backward(store: GatewayStore) -> None:
    store.mark_update_processed(100)
    store.mark_update_processed(50)
    assert store.get_offset() == 101


def test_out_of_order_unprocessed_update_is_not_dropped(store: GatewayStore) -> None:
    transport = FakeTransport()
    service = BotService(store, transport)
    assert service.handle_update(private_message(11, "/help"))
    assert service.handle_update(private_message(10, "/help"))
    assert len(transport.sent) == 2


def test_out_of_range_update_id_cannot_poison_poll_offset(store: GatewayStore) -> None:
    transport = FakeTransport()
    service = BotService(store, transport)
    assert not service.handle_update(private_message(10**12, "/help"))
    assert store.get_offset() == 0
    assert transport.sent == []


def test_interactive_rate_limit_does_not_gate_payment_updates(
    store: GatewayStore, now: datetime
) -> None:
    for _ in range(20):
        assert store.allow_interactive_request(101, now=now)
    assert not store.allow_interactive_request(101, now=now)

    store.register_recipient(101, 101, now=now)
    assert store.delete_recipient(101)
    assert store.conn.execute(
        "SELECT 1 FROM rate_limits WHERE scope = 'user:101'"
    ).fetchone() is None


def test_recipient_deletion_deidentifies_retained_star_ledger(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.conn.execute(
        """INSERT INTO star_transactions
           (transaction_id, direction, amount, nanostar_amount,
            transaction_date, partner_type, transaction_type,
            telegram_user_id, invoice_payload, subscription_period,
            semantic_digest, first_seen_at, last_seen_at,
            last_complete_run_id)
           VALUES ('retained-star-row', 'incoming', 1, 0, 1, 'user',
                   'invoice_payment', 101, NULL, NULL, ?, ?, ?, NULL)""",
        ("0" * 64, now.isoformat(), now.isoformat()),
    )
    store.conn.execute(
        """INSERT INTO star_reconciliation_issues
           (issue_key, severity, state, reason_code, transaction_id,
            direction, telegram_user_id, first_seen_at, last_seen_at,
            resolved_at, reconciliation_ref)
           VALUES ('retained-star-issue', 'warning', 'resolved',
                   'historical_warning', 'retained-star-row', 'incoming',
                   101, ?, ?, ?, 'historical-scan')""",
        (now.isoformat(), now.isoformat(), now.isoformat()),
    )
    store.conn.commit()

    assert store.delete_recipient(101)
    assert store.conn.execute(
        "SELECT telegram_user_id FROM star_transactions WHERE transaction_id = 'retained-star-row'"
    ).fetchone()[0] is None
    assert store.conn.execute(
        "SELECT telegram_user_id FROM star_reconciliation_issues WHERE issue_key = 'retained-star-issue'"
    ).fetchone()[0] is None


def test_retry_delay_metadata_is_bounded(store: GatewayStore, now: datetime) -> None:
    store.put_signal(build_s012_envelope(signal_record(now)), now=now)
    activate_subscription(store, now)
    for delay in (10**100, -1, True, 1.5):
        store.record_delivery(
            signal_id="signal-abcdef123456",
            telegram_user_id=101,
            status="failed",
            retry_after_seconds=delay,  # type: ignore[arg-type]
            now=now,
        )
    row = store.conn.execute(
        "SELECT next_attempt_at FROM delivery_receipts WHERE signal_id = ?",
        ("signal-abcdef123456",),
    ).fetchone()
    assert row is not None
    assert datetime.fromisoformat(row["next_attempt_at"].replace("Z", "+00:00")) <= (
        now + timedelta(hours=1)
    )


def test_lone_surrogate_update_is_quarantined_without_crashing(store: GatewayStore) -> None:
    transport = FakeTransport()
    transport.updates = [private_message(1, "/paper \ud800")]
    result = BotService(store, transport).poll_once(timeout=0)
    assert result["updates"] == 1
    assert transport.sent[-1]["text"] == "Use /help to see the available research commands."


def test_permanent_command_failure_does_not_starve_checkout(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    transport = FakeTransport()
    transport.send_error = TelegramError("blocked", error_code=403)
    transport.updates = [
        private_message(1, "/help"),
        {
            "update_id": 2,
            "pre_checkout_query": {
                "id": "checkout-after-failure",
                "from": {"id": 101},
                "currency": "XTR",
                "total_amount": 250,
                "invoice_payload": payload,
            },
        },
    ]
    result = BotService(
        store,
        transport,
        ServiceConfig(
            stars_amount=250,
            enable_stars_commerce=True,
            terms_version="terms-v1",
        ),
    ).poll_once(timeout=0)
    assert result["failed_updates"] == 1
    assert transport.checkouts[-1]["ok"] is True
    assert store.invoice_intent(payload)["state"] == "reserved"


def test_update_batch_preserves_telegram_chronology(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )

    class OrderedTransport(FakeTransport):
        def __init__(self) -> None:
            super().__init__()
            self.events: list[str] = []

        def send_text(self, *args: Any, **kwargs: Any) -> Mapping[str, Any]:
            self.events.append("send")
            return super().send_text(*args, **kwargs)

        def answer_pre_checkout(self, *args: Any, **kwargs: Any) -> bool:
            self.events.append("checkout")
            return super().answer_pre_checkout(*args, **kwargs)

    transport = OrderedTransport()
    transport.updates = [
        private_message(1, "/help"),
        {
            "update_id": 2,
            "pre_checkout_query": {
                "id": "checkout-priority",
                "from": {"id": 101},
                "currency": "XTR",
                "total_amount": 250,
                "invoice_payload": payload,
            },
        },
    ]
    BotService(
        store,
        transport,
        ServiceConfig(
            stars_amount=250,
            enable_stars_commerce=True,
            terms_version="terms-v1",
        ),
    ).poll_once(timeout=0)
    assert transport.events[:2] == ["send", "checkout"]


def test_fractional_telegram_ids_are_not_coerced(store: GatewayStore) -> None:
    transport = FakeTransport()
    transport.updates = [
        {
            "update_id": 1.5,
            "message": {
                "from": {"id": 101.9},
                "chat": {"id": 101, "type": "private"},
                "text": "/start",
            },
        }
    ]
    result = BotService(store, transport).poll_once(timeout=0)
    assert result["updates"] == 0
    assert store.counts()["recipients"] == 0


def test_only_one_pending_invoice_exists_per_user_and_plan(
    store: GatewayStore, now: datetime
) -> None:
    store.register_recipient(101, 101, now=now)
    store.accept_terms(101, "terms-v1", now=now)
    first = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    second = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=now,
    )
    assert second == first
    assert store.conn.execute(
        "SELECT COUNT(*) FROM invoice_intents WHERE state = 'created'"
    ).fetchone()[0] == 1


def test_api_repr_redacts_token_and_subscription_uses_invoice_link(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, _amount: int = -1) -> bytes:
            return json.dumps({"ok": True, "result": "https://t.me/invoice/ok"}).encode()

    def fake_urlopen(request: Any, timeout: float) -> Response:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", fake_urlopen)
    api = TelegramAPI("secret-bot-token")
    assert "secret-bot-token" not in repr(api)
    link = api.create_subscription_link(payload="sub:v1:opaque", stars_amount=250)
    assert link == "https://t.me/invoice/ok"
    assert captured["body"]["subscription_period"] == 2_592_000
    assert captured["body"]["currency"] == "XTR"
    assert captured["body"]["provider_token"] == ""


def test_api_rejects_unconfirmed_send_message_result(monkeypatch) -> None:
    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, _amount: int = -1) -> bytes:
            return b'{"ok":true,"result":null}'

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", lambda *_args, **_kwargs: Response())
    with pytest.raises(TelegramError) as captured:
        TelegramAPI("secret-bot-token").send_text(101, "hello")
    assert captured.value.ambiguous


def test_api_rejects_zero_message_id(monkeypatch) -> None:
    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, _amount: int = -1) -> bytes:
            return b'{"ok":true,"result":{"message_id":0}}'

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", lambda *_args, **_kwargs: Response())
    with pytest.raises(TelegramError) as captured:
        TelegramAPI("secret-bot-token").send_text(101, "hello")
    assert captured.value.ambiguous


def test_api_rejects_truthy_non_boolean_confirmation(monkeypatch) -> None:
    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, _amount: int = -1) -> bytes:
            return b'{"ok":true,"result":"false"}'

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", lambda *_args, **_kwargs: Response())
    with pytest.raises(TelegramError) as captured:
        TelegramAPI("secret-bot-token").edit_subscription(
            user_id=101, initial_charge_id="charge", canceled=True
        )
    assert captured.value.ambiguous


def test_api_missing_error_code_is_ambiguous(monkeypatch) -> None:
    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, _amount: int = -1) -> bytes:
            return b'{"unexpected":"body"}'

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", lambda *_args, **_kwargs: Response())
    with pytest.raises(TelegramError) as captured:
        TelegramAPI("secret-bot-token").call("sendMessage")
    assert captured.value.ambiguous


def test_http_500_status_remains_ambiguous_if_body_claims_400(monkeypatch) -> None:
    def fail(*_args: Any, **_kwargs: Any) -> None:
        body = b'{"ok":false,"error_code":400,"description":"mismatch"}'
        raise urllib.error.HTTPError(
            "https://api.telegram.org", 500, "error", {}, io.BytesIO(body)
        )

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", fail)
    with pytest.raises(TelegramError) as captured:
        TelegramAPI("secret-bot-token").call("sendMessage")
    assert captured.value.ambiguous


def test_api_normalizes_extreme_json_and_incomplete_reads(monkeypatch) -> None:
    class HugeNumberResponse:
        def __enter__(self) -> "HugeNumberResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, _amount: int = -1) -> bytes:
            return ("{\"ok\":true,\"result\":" + "9" * 5_000 + "}").encode()

    monkeypatch.setattr(
        "telegram_gateway.telegram_api.open_request", lambda *_args, **_kwargs: HugeNumberResponse()
    )
    with pytest.raises(TelegramError) as extreme:
        TelegramAPI("secret-bot-token").call("getMe")
    assert extreme.value.ambiguous

    class IncompleteResponse(HugeNumberResponse):
        def read(self, _amount: int = -1) -> bytes:
            raise http.client.IncompleteRead(b'{"ok":')

    monkeypatch.setattr(
        "telegram_gateway.telegram_api.open_request", lambda *_args, **_kwargs: IncompleteResponse()
    )
    with pytest.raises(TelegramError) as incomplete:
        TelegramAPI("secret-bot-token").call("getMe")
    assert incomplete.value.ambiguous


def test_error_description_redacts_secret_before_truncation(monkeypatch) -> None:
    token = "secret:token-value"

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, _amount: int = -1) -> bytes:
            description = "x" * 295 + "SECRET%3Atoken-value" + "tail"
            return json.dumps(
                {"ok": False, "error_code": 400, "description": description}
            ).encode()

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", lambda *_args, **_kwargs: Response())
    with pytest.raises(TelegramError) as captured:
        TelegramAPI(token).call("getMe")
    assert "secret" not in str(captured.value).lower()
    assert "%3a" not in str(captured.value).lower()


def test_early_schema_is_migrated_without_enum_rewrite(tmp_path: Path) -> None:
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    db = parent / "old.db"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE invoice_intents (
          payload TEXT PRIMARY KEY, telegram_user_id INTEGER, plan_code TEXT,
          currency TEXT, total_amount INTEGER, terms_version TEXT,
          created_at TEXT, expires_at TEXT, state TEXT, pre_checkout_query_id TEXT
        );
        CREATE TABLE subscriptions (
          initial_charge_id TEXT PRIMARY KEY, telegram_user_id INTEGER,
          plan_code TEXT, invoice_payload TEXT, current_period_end TEXT,
          renewal_state TEXT, revoked_at TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE refund_events (
          telegram_payment_charge_id TEXT PRIMARY KEY, telegram_user_id INTEGER,
          currency TEXT, total_amount INTEGER, invoice_payload TEXT,
          received_at TEXT, resolved_at TEXT
        );
        """
    )
    connection.close()
    with GatewayStore(db) as migrated:
        invoice_columns = {
            row["name"] for row in migrated.conn.execute("PRAGMA table_info(invoice_intents)")
        }
        subscription_columns = {
            row["name"] for row in migrated.conn.execute("PRAGMA table_info(subscriptions)")
        }
        refund_columns = {
            row["name"] for row in migrated.conn.execute("PRAGMA table_info(refund_events)")
        }
        assert {"reserved_at", "reconciled_at", "reconciliation_ref"} <= invoice_columns
        assert {
            "cancellation_pending_at",
            "cancellation_intent_at",
            "last_provider_update_id",
        } <= subscription_columns
        assert {"resolution_code", "reconciliation_ref"} <= refund_columns


def test_api_treats_http_500_as_ambiguous_and_redacts_token(monkeypatch) -> None:
    token = "secret:token-value"

    def fail(*_args: Any, **_kwargs: Any) -> None:
        body = json.dumps(
            {"ok": False, "error_code": 500, "description": f"path had {token}"}
        ).encode()
        raise urllib.error.HTTPError(
            "https://api.telegram.org", 500, "error", {}, io.BytesIO(body)
        )

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", fail)
    with pytest.raises(TelegramError) as captured:
        TelegramAPI(token).call("getMe")
    assert captured.value.ambiguous
    assert token not in str(captured.value)
