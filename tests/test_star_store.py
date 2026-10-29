from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from telegram_gateway.store import GatewayStore


NOW = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)


def _activate(store: GatewayStore) -> tuple[str, str]:
    store.register_recipient(101, 101, now=NOW)
    store.accept_terms(101, "terms-v1", now=NOW)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=NOW,
    )
    accepted, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="checkout-1",
        current_terms_version="terms-v1",
        now=NOW,
    )
    assert accepted
    charge_id = "charge-provider-1"
    store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id=charge_id,
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=True,
        paid_at=NOW,
        subscription_expiration_unix=int((NOW + timedelta(days=30)).timestamp()),
    )
    return payload, charge_id


def _reserve(store: GatewayStore) -> str:
    store.register_recipient(101, 101, now=NOW)
    store.accept_terms(101, "terms-v1", now=NOW)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=NOW,
    )
    accepted, _ = store.reserve_invoice_intent(
        payload=payload,
        telegram_user_id=101,
        currency="XTR",
        total_amount=250,
        pre_checkout_query_id="checkout-reserved",
        current_terms_version="terms-v1",
        now=NOW,
    )
    assert accepted
    return payload


def _record_payment(
    store: GatewayStore,
    *,
    payload: str,
    charge_id: str,
    paid_at: datetime = NOW,
):
    return store.record_subscription_payment(
        telegram_user_id=101,
        private_chat_id=101,
        telegram_payment_charge_id=charge_id,
        currency="XTR",
        total_amount=250,
        invoice_payload=payload,
        is_recurring=True,
        is_first_recurring=True,
        paid_at=paid_at,
        subscription_expiration_unix=int((NOW + timedelta(days=30)).timestamp()),
    )


class _FailFirstCommit:
    def __init__(self, connection: Any):
        self.connection = connection
        self.should_fail = True

    def __getattr__(self, name: str) -> Any:
        return getattr(self.connection, name)

    def commit(self) -> None:
        if self.should_fail:
            self.should_fail = False
            raise OSError("simulated durable commit failure")
        self.connection.commit()


def _observation(
    *,
    charge_id: str,
    payload: str | None,
    direction: str,
    user_id: int = 101,
    amount: int = 250,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "transaction_id": charge_id,
        "direction": direction,
        "amount": amount,
        "nanostar_amount": 0,
        "transaction_date": int(NOW.timestamp()),
        "partner_type": "user",
        "transaction_type": "invoice_payment",
        "telegram_user_id": user_id,
        "invoice_payload": payload,
        "subscription_period": 2_592_000,
    }
    material = json.dumps(
        result, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    result["semantic_digest"] = hashlib.sha256(material).hexdigest()
    return result


def _snapshot_digest(observations: list[dict[str, Any]]) -> str:
    material = json.dumps(
        {
            "terminal_offset": len(observations),
            "observations": observations,
            "issues": [],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


@pytest.fixture
def store(tmp_path: Path) -> GatewayStore:
    value = GatewayStore(tmp_path / "private" / "gateway.db")
    try:
        yield value
    finally:
        value.close()


def test_provider_binding_refuses_database_reuse(store: GatewayStore) -> None:
    store.bind_star_provider(1234, "https://api.telegram.org")
    store.bind_star_provider(1234, "https://api.telegram.org")

    with pytest.raises(ValueError, match="different Telegram provider"):
        store.bind_star_provider(5678, "https://api.telegram.org")
    with pytest.raises(ValueError, match="different Telegram provider"):
        store.bind_star_provider(1234, "https://example.invalid")


def test_store_rejects_opaque_partner_even_with_self_consistent_digests(
    store: GatewayStore,
) -> None:
    observation = _observation(
        charge_id="opaque-provider-row", payload=None, direction="incoming"
    )
    observation.update(
        partner_type="other",
        transaction_type=None,
        telegram_user_id=None,
        subscription_period=None,
    )
    semantic_material = {
        key: value for key, value in observation.items() if key != "semantic_digest"
    }
    observation["semantic_digest"] = hashlib.sha256(
        json.dumps(
            semantic_material,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    digest = _snapshot_digest([observation])
    store.begin_star_scan("scan-opaque", 1234, "https://api.telegram.org", now=NOW)

    with pytest.raises(ValueError, match="partner type is unsupported"):
        store.complete_star_scan(
            "scan-opaque",
            [observation],
            1,
            digest,
            [],
            pass_digests=(digest, digest),
            now=NOW,
        )

    assert store.conn.execute("SELECT COUNT(*) FROM star_transactions").fetchone()[0] == 0


def test_duplicate_scan_run_id_rolls_back_and_leaves_connection_usable(
    store: GatewayStore,
) -> None:
    store.begin_star_scan("scan-duplicate", 1234, "https://api.telegram.org", now=NOW)

    with pytest.raises(ValueError, match="already used"):
        store.begin_star_scan(
            "scan-duplicate", 1234, "https://api.telegram.org", now=NOW
        )

    assert not store.conn.in_transaction
    store.begin_star_scan("scan-after-duplicate", 1234, "https://api.telegram.org", now=NOW)
    store.fail_star_scan(
        "scan-after-duplicate", "operator_test", pass_count=0, now=NOW
    )


def test_clean_incoming_snapshot_confirms_but_does_not_create_access(
    store: GatewayStore,
) -> None:
    payload, charge_id = _activate(store)
    observation = _observation(
        charge_id=charge_id, payload=payload, direction="incoming"
    )
    store.begin_star_scan("scan-1", 1234, "https://api.telegram.org", now=NOW)
    result = store.complete_star_scan(
        "scan-1",
        [observation],
        1,
        _snapshot_digest([observation]),
        [],
        pass_digests=(
            _snapshot_digest([observation]),
            _snapshot_digest([observation]),
        ),
        now=NOW,
    )

    assert result["critical_issues"] == 0
    row = store.conn.execute(
        "SELECT provider_confirmed_at FROM payments WHERE telegram_payment_charge_id = ?",
        (charge_id,),
    ).fetchone()
    assert row["provider_confirmed_at"] is not None
    assert store.is_entitled(101, now=NOW)


def test_absence_from_clean_snapshot_only_opens_warning(store: GatewayStore) -> None:
    _activate(store)
    store.begin_star_scan("scan-empty", 1234, "https://api.telegram.org", now=NOW)
    result = store.complete_star_scan(
        "scan-empty",
        [],
        0,
        _snapshot_digest([]),
        [],
        pass_digests=(_snapshot_digest([]), _snapshot_digest([])),
        now=NOW,
    )

    assert result["issues"] == 1
    assert store.is_entitled(101, now=NOW)
    assert store.unresolved_star_issues()[0]["reason_code"] == (
        "local_payment_absent_from_provider_snapshot"
    )


def test_positive_refund_evidence_revokes_access_once_and_requires_cancellation(
    store: GatewayStore,
) -> None:
    payload, charge_id = _activate(store)
    incoming = _observation(
        charge_id=charge_id, payload=payload, direction="incoming"
    )
    outgoing = _observation(
        charge_id=charge_id, payload=payload, direction="outgoing"
    )
    observations = [incoming, outgoing]
    store.begin_star_scan("scan-refund", 1234, "https://api.telegram.org", now=NOW)
    result = store.complete_star_scan(
        "scan-refund",
        observations,
        2,
        _snapshot_digest(observations),
        [],
        pass_digests=(
            _snapshot_digest(observations),
            _snapshot_digest(observations),
        ),
        now=NOW + timedelta(minutes=1),
    )

    assert result["refunds_applied"] == 1
    assert not store.is_entitled(101, now=NOW + timedelta(minutes=1))
    subscription = store.latest_subscription(101)
    assert subscription is not None
    assert subscription["cancellation_pending_at"] is not None

    store.begin_star_scan(
        "scan-refund-repeat",
        1234,
        "https://api.telegram.org",
        now=NOW + timedelta(minutes=2),
    )
    repeated = store.complete_star_scan(
        "scan-refund-repeat",
        observations,
        2,
        _snapshot_digest(observations),
        [],
        pass_digests=(
            _snapshot_digest(observations),
            _snapshot_digest(observations),
        ),
        now=NOW + timedelta(minutes=2),
    )
    assert repeated["refunds_applied"] == 0
    assert any(
        issue["reason_code"] == "provider_refund_cancellation_unconfirmed"
        for issue in store.unresolved_star_issues()
    )


def test_provider_only_payment_is_quarantined_without_entitlement(
    store: GatewayStore,
) -> None:
    store.register_recipient(101, 101, now=NOW)
    store.accept_terms(101, "terms-v1", now=NOW)
    payload = store.create_invoice_intent(
        telegram_user_id=101,
        plan_code="research",
        total_amount=250,
        terms_version="terms-v1",
        now=NOW,
    )
    observation = _observation(
        charge_id="provider-only", payload=payload, direction="incoming"
    )
    store.begin_star_scan("scan-provider-only", 1234, "https://api.telegram.org", now=NOW)
    result = store.complete_star_scan(
        "scan-provider-only",
        [observation],
        1,
        _snapshot_digest([observation]),
        [],
        pass_digests=(
            _snapshot_digest([observation]),
            _snapshot_digest([observation]),
        ),
        now=NOW,
    )

    assert result["critical_issues"] == 1
    assert not store.is_entitled(101, now=NOW)
    assert store.conn.execute("SELECT COUNT(*) FROM support_cases").fetchone()[0] == 1


def test_failed_scan_cannot_be_completed(store: GatewayStore) -> None:
    store.begin_star_scan("scan-failed", 1234, "https://api.telegram.org", now=NOW)
    store.fail_star_scan("scan-failed", "provider_transport", pass_count=1, now=NOW)

    with pytest.raises(ValueError, match="not open"):
        store.complete_star_scan(
            "scan-failed",
            [],
            0,
            _snapshot_digest([]),
            [],
            pass_digests=(_snapshot_digest([]), _snapshot_digest([])),
            now=NOW,
        )


def test_empty_snapshot_holds_write_reservation_across_local_ledger_reads(
    store: GatewayStore,
) -> None:
    payload = _reserve(store)
    concurrent = GatewayStore(store.path)
    try:
        concurrent.conn.execute("PRAGMA busy_timeout=0")
        store.begin_star_scan(
            "scan-empty-race", 1234, "https://api.telegram.org", now=NOW
        )
        attempt: dict[str, Any] = {"ran": False, "locked": False}

        def inject_late_payment(statement: str) -> None:
            if (
                attempt["ran"]
                or "UPDATE star_scan_runs" not in statement
                or "state = 'complete'" not in statement
            ):
                return
            attempt["ran"] = True
            try:
                _record_payment(
                    concurrent,
                    payload=payload,
                    charge_id="charge-after-snapshot",
                )
            except sqlite3.OperationalError as exc:
                attempt["locked"] = "locked" in str(exc).lower()

        store.conn.set_trace_callback(inject_late_payment)
        empty_digest = _snapshot_digest([])
        result = store.complete_star_scan(
            "scan-empty-race",
            [],
            0,
            empty_digest,
            [],
            pass_digests=(empty_digest, empty_digest),
            now=NOW,
        )
        store.conn.set_trace_callback(None)

        assert attempt == {"ran": True, "locked": True}
        assert result["clean"] is True
        assert not concurrent.conn.in_transaction
        assert (
            store.conn.execute(
                "SELECT COUNT(*) FROM payments WHERE telegram_payment_charge_id = ?",
                ("charge-after-snapshot",),
            ).fetchone()[0]
            == 0
        )

        _record_payment(
            concurrent,
            payload=payload,
            charge_id="charge-after-snapshot",
            paid_at=NOW + timedelta(minutes=1),
        )
        store.begin_star_scan(
            "scan-after-late-payment",
            1234,
            "https://api.telegram.org",
            now=NOW + timedelta(minutes=2),
        )
        followup = store.complete_star_scan(
            "scan-after-late-payment",
            [],
            0,
            empty_digest,
            [],
            pass_digests=(empty_digest, empty_digest),
            now=NOW + timedelta(minutes=2),
        )

        assert followup["clean"] is False
        assert any(
            issue["reason_code"] == "local_payment_absent_from_provider_snapshot"
            for issue in store.unresolved_star_issues()
        )
    finally:
        store.conn.set_trace_callback(None)
        concurrent.close()


def test_commit_failure_rolls_back_all_reconciliation_effects(
    store: GatewayStore,
) -> None:
    payload, charge_id = _activate(store)
    observations = [
        _observation(charge_id=charge_id, payload=payload, direction="incoming"),
        _observation(charge_id=charge_id, payload=payload, direction="outgoing"),
    ]
    digest = _snapshot_digest(observations)
    store.begin_star_scan(
        "scan-commit-failure", 1234, "https://api.telegram.org", now=NOW
    )
    store.conn = _FailFirstCommit(store.conn)

    with pytest.raises(OSError, match="simulated durable commit failure"):
        store.complete_star_scan(
            "scan-commit-failure",
            observations,
            2,
            digest,
            [],
            pass_digests=(digest, digest),
            now=NOW + timedelta(minutes=1),
        )

    assert not store.conn.in_transaction
    payment = store.conn.execute(
        """SELECT refunded_at, provider_confirmed_at, provider_refund_confirmed_at
           FROM payments WHERE telegram_payment_charge_id = ?""",
        (charge_id,),
    ).fetchone()
    assert dict(payment) == {
        "refunded_at": None,
        "provider_confirmed_at": None,
        "provider_refund_confirmed_at": None,
    }
    assert store.conn.execute("SELECT COUNT(*) FROM star_transactions").fetchone()[0] == 0
    assert store.conn.execute("SELECT COUNT(*) FROM star_reconciliation_issues").fetchone()[0] == 0
    assert store.is_entitled(101, now=NOW + timedelta(minutes=1))
    run = store.conn.execute(
        "SELECT state, pass_count FROM star_scan_runs WHERE run_id = ?",
        ("scan-commit-failure",),
    ).fetchone()
    assert dict(run) == {"state": "running", "pass_count": 0}

    store.fail_star_scan(
        "scan-commit-failure",
        "star_scan_failed",
        pass_count=2,
        now=NOW + timedelta(minutes=1),
    )
    assert (
        store.conn.execute(
            "SELECT state FROM star_scan_runs WHERE run_id = ?",
            ("scan-commit-failure",),
        ).fetchone()["state"]
        == "failed"
    )


def test_payload_optional_provider_refund_blocks_delayed_payment_access(
    store: GatewayStore,
) -> None:
    payload = _reserve(store)
    charge_id = "charge-refund-without-payload"
    outgoing = _observation(
        charge_id=charge_id,
        payload=None,
        direction="outgoing",
    )
    digest = _snapshot_digest([outgoing])
    store.begin_star_scan(
        "scan-refund-without-payload",
        1234,
        "https://api.telegram.org",
        now=NOW,
    )
    scan = store.complete_star_scan(
        "scan-refund-without-payload",
        [outgoing],
        1,
        digest,
        [],
        pass_digests=(digest, digest),
        now=NOW,
    )

    assert scan["clean"] is False
    payment = _record_payment(
        store,
        payload=payload,
        charge_id=charge_id,
        paid_at=NOW + timedelta(minutes=1),
    )

    assert payment.refunded is True
    assert payment.cancellation_required is True
    assert payment.entitlement_expires_at is None
    assert not store.is_entitled(101, now=NOW + timedelta(minutes=1))
    persisted = store.conn.execute(
        """SELECT p.refunded_at, r.resolution_code
           FROM payments p JOIN refund_events r
             ON r.telegram_payment_charge_id = p.telegram_payment_charge_id
           WHERE p.telegram_payment_charge_id = ?""",
        (charge_id,),
    ).fetchone()
    assert persisted["refunded_at"] is not None
    assert persisted["resolution_code"] == "matched_payment"
    subscription = store.latest_subscription(101)
    assert subscription is not None
    assert subscription["cancellation_pending_at"] is not None
