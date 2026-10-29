from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import pytest

from telegram_gateway.reconciliation import (
    MAX_TELEGRAM_USER_ID,
    STAR_PAGE_LIMIT,
    StarReconciliationError,
    StarTransactionValidationError,
    normalize_star_transaction,
    reconcile_star_transactions,
)


NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def star_payment(
    transaction_id: str,
    *,
    user_id: int = 101,
    payload: str | None = "sub:v1:test-payload",
    amount: int = 250,
    nanostar_amount: int = 0,
    date: int = 1_788_350_400,
    outgoing: bool = False,
    subscription_period: int | None = 2_592_000,
) -> dict[str, Any]:
    partner: dict[str, Any] = {
        "type": "user",
        "transaction_type": "invoice_payment",
        "user": {
            "id": user_id,
            "is_bot": False,
            "first_name": "must not persist",
            "username": "must_not_persist",
        },
    }
    if payload is not None:
        partner["invoice_payload"] = payload
    if subscription_period is not None:
        partner["subscription_period"] = subscription_period
    result = {
        "id": transaction_id,
        "amount": amount,
        "date": date,
        "receiver" if outgoing else "source": partner,
    }
    if nanostar_amount:
        result["nanostar_amount"] = nanostar_amount
    return result


class FakeStarAPI:
    provider_origin = "https://api.telegram.org"

    def __init__(
        self,
        snapshots: Sequence[Sequence[Mapping[str, Any]]],
        *,
        bot_id: int = 777,
        fail_call: int | None = None,
        page_size: int | None = None,
    ):
        self.snapshots = [list(snapshot) for snapshot in snapshots]
        self.bot_id = bot_id
        self.fail_call = fail_call
        self.page_size = page_size
        self.calls: list[tuple[int, int]] = []
        self._pass_index = -1

    def get_bot_id(self) -> int:
        return self.bot_id

    def get_star_transactions(
        self, offset: int, limit: int
    ) -> list[Mapping[str, Any]]:
        self.calls.append((offset, limit))
        if self.fail_call is not None and len(self.calls) == self.fail_call:
            raise RuntimeError("provider detail that must not escape")
        if offset == 0:
            self._pass_index += 1
        snapshot = self.snapshots[self._pass_index]
        effective_limit = min(limit, self.page_size or limit)
        return snapshot[offset : offset + effective_limit]


class FakeStarStore:
    def __init__(self, *, summary: Mapping[str, Any] | None = None):
        self.summary = dict(summary or {"clean": True})
        self.bound: list[tuple[int, str]] = []
        self.begun: list[tuple[str, int, str, datetime | None]] = []
        self.failed: list[tuple[str, str, int, datetime | None]] = []
        self.completed: list[dict[str, Any]] = []

    def bind_star_provider(self, bot_id: int, api_origin: str) -> None:
        self.bound.append((bot_id, api_origin))

    def begin_star_scan(
        self,
        run_id: str,
        bot_id: int,
        api_origin: str,
        now: datetime | None = None,
    ) -> None:
        self.begun.append((run_id, bot_id, api_origin, now))

    def fail_star_scan(
        self,
        run_id: str,
        error_code: str,
        pass_count: int = 0,
        now: datetime | None = None,
    ) -> None:
        self.failed.append((run_id, error_code, pass_count, now))

    def complete_star_scan(
        self,
        run_id: str,
        observations: Sequence[Mapping[str, Any]],
        terminal_offset: int,
        snapshot_digest: str,
        issues: Sequence[Mapping[str, Any]],
        *,
        pass_digests: Sequence[str],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.completed.append(
            {
                "run_id": run_id,
                "observations": [dict(item) for item in observations],
                "terminal_offset": terminal_offset,
                "snapshot_digest": snapshot_digest,
                "issues": [dict(item) for item in issues],
                "pass_digests": list(pass_digests),
                "now": now,
            }
        )
        result = dict(self.summary)
        if issues:
            result["clean"] = False
        return result


def test_normalizes_only_allowlisted_invoice_fields() -> None:
    observation = normalize_star_transaction(star_payment("charge-1"))
    mapping = observation.to_mapping()

    assert set(mapping) == {
        "transaction_id",
        "direction",
        "amount",
        "nanostar_amount",
        "transaction_date",
        "partner_type",
        "transaction_type",
        "telegram_user_id",
        "invoice_payload",
        "subscription_period",
        "semantic_digest",
    }
    assert mapping["direction"] == "incoming"
    assert mapping["telegram_user_id"] == 101
    assert mapping["nanostar_amount"] == 0
    assert len(mapping["semantic_digest"]) == 64
    assert "first_name" not in repr(mapping)
    assert "username" not in repr(mapping)


def test_payment_and_refund_share_id_but_have_distinct_identity() -> None:
    payment = normalize_star_transaction(star_payment("same-charge"))
    refund = normalize_star_transaction(star_payment("same-charge", outgoing=True))

    assert payment.identity == ("same-charge", "incoming")
    assert refund.identity == ("same-charge", "outgoing")
    assert payment.identity != refund.identity


def test_fractional_star_transaction_with_zero_whole_stars_is_valid() -> None:
    observation = normalize_star_transaction(
        star_payment("fractional", amount=0, nanostar_amount=1)
    )

    assert observation.amount == 0
    assert observation.nanostar_amount == 1


@pytest.mark.parametrize(
    ("change", "reason_code"),
    [
        (lambda row: row.update(amount=True), "transaction_amount_invalid"),
        (
            lambda row: row.update(nanostar_amount=1_000_000_000),
            "transaction_nanostar_amount_invalid",
        ),
        (lambda row: row.update(date=False), "transaction_date_invalid"),
        (
            lambda row: row["source"].update(subscription_period=60),
            "subscription_period_unsupported",
        ),
        (
            lambda row: row.update(receiver=dict(row["source"])),
            "transaction_direction_invalid",
        ),
        (
            lambda row: row.update(source={"type": "other"}),
            "partner_type_other_opaque",
        ),
    ],
)
def test_strict_transaction_validation(change: Any, reason_code: str) -> None:
    row = star_payment("invalid-charge")
    change(row)

    with pytest.raises(StarTransactionValidationError) as raised:
        normalize_star_transaction(row)

    assert raised.value.reason_code == reason_code


def test_user_id_accepts_telegram_52_bit_boundary() -> None:
    assert (
        normalize_star_transaction(
            star_payment("large-user", user_id=MAX_TELEGRAM_USER_ID)
        ).telegram_user_id
        == MAX_TELEGRAM_USER_ID
    )
    with pytest.raises(StarTransactionValidationError) as raised:
        normalize_star_transaction(
            star_payment("too-large-user", user_id=MAX_TELEGRAM_USER_ID + 1)
        )
    assert raised.value.reason_code == "telegram_user_id_invalid"


def test_stable_scan_uses_two_complete_offset_zero_passes() -> None:
    transactions = [
        star_payment(f"charge-{index:03d}", date=1_788_350_400 + index)
        for index in range(205)
    ]
    api = FakeStarAPI([transactions, transactions])
    store = FakeStarStore()

    result = reconcile_star_transactions(
        store,
        api,
        run_id="stars-stable",
        max_transactions=300,
        now=NOW,
    )

    assert result.clean is True
    assert result.pass_count == 2
    assert result.transaction_count == 205
    assert result.terminal_offset == 205
    assert result.error_code is None
    assert api.calls == [
        (0, STAR_PAGE_LIMIT),
        (100, STAR_PAGE_LIMIT),
        (200, STAR_PAGE_LIMIT),
        (205, STAR_PAGE_LIMIT),
        (0, STAR_PAGE_LIMIT),
        (100, STAR_PAGE_LIMIT),
        (200, STAR_PAGE_LIMIT),
        (205, STAR_PAGE_LIMIT),
    ]
    assert store.bound == [(777, "https://api.telegram.org")]
    assert store.begun == [
        ("stars-stable", 777, "https://api.telegram.org", NOW)
    ]
    assert not store.failed
    assert len(store.completed) == 1
    assert len(store.completed[0]["observations"]) == 205


def test_short_pages_require_an_explicit_empty_terminator() -> None:
    transactions = [star_payment(f"charge-{index:03d}") for index in range(80)]
    api = FakeStarAPI([transactions, transactions], page_size=40)
    store = FakeStarStore()

    result = reconcile_star_transactions(
        store,
        api,
        run_id="stars-fragmented-pages",
        max_transactions=100,
        now=NOW,
    )

    assert result.clean is True
    assert result.transaction_count == 80
    assert result.terminal_offset == 80
    assert api.calls == [
        (0, STAR_PAGE_LIMIT),
        (40, STAR_PAGE_LIMIT),
        (80, STAR_PAGE_LIMIT),
        (0, STAR_PAGE_LIMIT),
        (40, STAR_PAGE_LIMIT),
        (80, STAR_PAGE_LIMIT),
    ]


def test_empty_stable_scan_completes_without_inventing_observations() -> None:
    api = FakeStarAPI([[], []])
    store = FakeStarStore()

    result = reconcile_star_transactions(store, api, run_id="stars-empty", now=NOW)

    assert result.clean is True
    assert result.transaction_count == 0
    assert store.completed[0]["observations"] == []
    assert store.completed[0]["issues"] == []
    assert api.calls == [(0, 100), (0, 100)]


def test_snapshot_drift_fails_without_store_completion() -> None:
    first = [star_payment("charge-1")]
    second = [star_payment("charge-1"), star_payment("charge-2")]
    api = FakeStarAPI([first, second])
    store = FakeStarStore()

    result = reconcile_star_transactions(store, api, run_id="stars-drift", now=NOW)

    assert result.clean is False
    assert result.error_code == "unstable_provider_snapshot"
    assert result.pass_count == 2
    assert not store.completed
    assert store.failed == [
        ("stars-drift", "unstable_provider_snapshot", 2, NOW)
    ]


def test_provider_failure_is_sanitized_and_fails_run() -> None:
    api = FakeStarAPI([[star_payment("charge-1")]], fail_call=1)
    store = FakeStarStore()

    result = reconcile_star_transactions(store, api, run_id="stars-error", now=NOW)

    assert result.error_code == "provider_transaction_fetch_failed"
    assert "provider detail" not in repr(result)
    assert store.failed == [
        ("stars-error", "provider_transaction_fetch_failed", 0, NOW)
    ]
    assert not store.completed


def test_duplicate_identity_in_one_pass_fails_closed() -> None:
    duplicate = [star_payment("charge-1"), star_payment("charge-1")]
    api = FakeStarAPI([duplicate])
    store = FakeStarStore()

    result = reconcile_star_transactions(
        store, api, run_id="stars-duplicate", now=NOW
    )

    assert result.error_code == "duplicate_provider_transaction_identity"
    assert store.failed == [
        ("stars-duplicate", "duplicate_provider_transaction_identity", 0, NOW)
    ]
    assert not store.completed


def test_same_charge_payment_and_refund_are_both_persisted() -> None:
    snapshot = [
        star_payment("charge-1"),
        star_payment("charge-1", outgoing=True, date=1_788_350_500),
    ]
    api = FakeStarAPI([snapshot, snapshot])
    store = FakeStarStore()

    result = reconcile_star_transactions(store, api, run_id="stars-refund", now=NOW)

    assert result.clean is True
    persisted = store.completed[0]["observations"]
    assert {(item["transaction_id"], item["direction"]) for item in persisted} == {
        ("charge-1", "incoming"),
        ("charge-1", "outgoing"),
    }


def test_stable_malformed_row_is_quarantined_and_scan_is_not_clean() -> None:
    malformed = star_payment("bad-charge")
    malformed["amount"] = "250"
    api = FakeStarAPI([[malformed], [malformed]])
    store = FakeStarStore()

    result = reconcile_star_transactions(store, api, run_id="stars-bad", now=NOW)

    assert result.error_code is None
    assert result.clean is False
    assert result.issue_count == 1
    assert len(store.completed) == 1
    assert store.completed[0]["observations"] == []
    issue = store.completed[0]["issues"][0]
    assert set(issue) == {
        "issue_key",
        "severity",
        "reason_code",
        "transaction_id",
        "direction",
        "telegram_user_id",
    }
    assert issue["reason_code"] == "transaction_amount_invalid"
    assert issue["severity"] == "critical"
    assert "must not persist" not in repr(store.completed)


def test_transaction_cap_requires_observing_a_terminal_page() -> None:
    transactions = [star_payment(f"charge-{index}") for index in range(101)]
    api = FakeStarAPI([transactions])
    store = FakeStarStore()

    result = reconcile_star_transactions(
        store,
        api,
        run_id="stars-cap",
        max_transactions=100,
        now=NOW,
    )

    assert result.error_code == "provider_transaction_limit_exceeded"
    assert api.calls == [(0, 100), (100, 100)]
    assert not store.completed


def test_store_summary_can_keep_stable_scan_unhealthy() -> None:
    snapshot = [star_payment("provider-only-charge")]
    api = FakeStarAPI([snapshot, snapshot])
    store = FakeStarStore(summary={"clean": False, "provider_only": 1})

    result = reconcile_star_transactions(
        store, api, run_id="stars-local-mismatch", now=NOW
    )

    assert result.error_code is None
    assert result.clean is False
    assert result.summary == {"clean": False, "provider_only": 1}


def test_result_issue_count_includes_store_discovered_issues() -> None:
    api = FakeStarAPI([[], []])
    store = FakeStarStore(summary={"clean": False, "issues": 3})

    result = reconcile_star_transactions(
        store, api, run_id="stars-local-issues", now=NOW
    )

    assert result.clean is False
    assert result.issue_count == 3


def test_invalid_provider_identity_never_begins_scan() -> None:
    api = FakeStarAPI([[]], bot_id=True)
    store = FakeStarStore()

    with pytest.raises(StarReconciliationError):
        reconcile_star_transactions(store, api, run_id="stars-identity", now=NOW)

    assert not store.bound
    assert not store.begun


def test_provider_origin_must_not_contain_credentials_or_paths() -> None:
    api = FakeStarAPI([[]])
    api.provider_origin = "https://token@example.test/bot-secret"
    store = FakeStarStore()

    with pytest.raises(ValueError):
        reconcile_star_transactions(store, api, run_id="stars-origin", now=NOW)

    assert not store.bound
    assert not store.begun


def test_non_loopback_plain_http_provider_origin_is_rejected() -> None:
    api = FakeStarAPI([[]])
    api.provider_origin = "http://api.telegram.org"
    store = FakeStarStore()

    with pytest.raises(ValueError):
        reconcile_star_transactions(store, api, run_id="stars-http-origin", now=NOW)

    assert not store.bound
    assert not store.begun
