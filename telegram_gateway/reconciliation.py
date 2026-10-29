"""Stable, privacy-minimized Telegram Star transaction reconciliation.

This module treats ``getStarTransactions`` as a provider ledger, not as an
entitlement source.  Telegram's transaction history does not contain the
subscription expiration and recurring-payment flags carried by a
``successful_payment`` update, so an observation here must never synthesize
access.  Store-side completion may act on positive, exact refund evidence;
absence is meaningful only after two complete, identical scans.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlsplit


STAR_PAGE_LIMIT = 100
MAX_TELEGRAM_USER_ID = (1 << 52) - 1
MAX_TRANSACTION_ID_BYTES = 256
MAX_INVOICE_PAYLOAD_BYTES = 128
MAX_STAR_AMOUNT = (1 << 63) - 1
MAX_TRANSACTION_DATE = (1 << 31) - 1
SUBSCRIPTION_PERIOD_SECONDS = 2_592_000

_RUN_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z")
_PARTNER_TYPES = frozenset(
    {
        "user",
        "chat",
        "affiliate_program",
        "fragment",
        "telegram_ads",
        "telegram_api",
        "other",
    }
)
_USER_TRANSACTION_TYPES = frozenset(
    {
        "invoice_payment",
        "paid_media_payment",
        "gift_purchase",
        "premium_purchase",
        "business_account_transfer",
    }
)


class StarProvider(Protocol):
    """Narrow provider surface needed by the reconciler."""

    @property
    def provider_origin(self) -> str: ...

    def get_bot_id(self) -> int: ...

    def get_star_transactions(
        self, offset: int, limit: int
    ) -> list[Mapping[str, Any]]: ...


class StarScanStore(Protocol):
    """Persistence boundary implemented by :class:`GatewayStore`."""

    def bind_star_provider(self, bot_id: int, api_origin: str) -> None: ...

    def begin_star_scan(
        self,
        run_id: str,
        bot_id: int,
        api_origin: str,
        *,
        now: datetime | None = None,
    ) -> None: ...

    def fail_star_scan(
        self,
        run_id: str,
        error_code: str,
        *,
        pass_count: int = 0,
        now: datetime | None = None,
    ) -> None: ...

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
    ) -> dict[str, Any]: ...


class StarReconciliationError(RuntimeError):
    """Sanitized configuration or provider-identity failure."""


class StarTransactionValidationError(ValueError):
    """A provider transaction could not be safely normalized."""

    def __init__(
        self,
        reason_code: str,
        *,
        transaction_id: str | None = None,
        direction: str | None = None,
        telegram_user_id: int | None = None,
    ):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.transaction_id = transaction_id
        self.direction = direction
        self.telegram_user_id = telegram_user_id


@dataclass(frozen=True)
class StarTransactionObservation:
    """Allowlisted scalar fields from a Telegram ``StarTransaction``."""

    transaction_id: str
    direction: str
    amount: int
    nanostar_amount: int
    transaction_date: int
    partner_type: str
    transaction_type: str | None
    telegram_user_id: int | None
    invoice_payload: str | None
    subscription_period: int | None
    semantic_digest: str

    @property
    def identity(self) -> tuple[str, str]:
        # Telegram deliberately reuses the original transaction ID for its
        # refund, so direction is part of provider identity.
        return (self.transaction_id, self.direction)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "direction": self.direction,
            "amount": self.amount,
            "nanostar_amount": self.nanostar_amount,
            "transaction_date": self.transaction_date,
            "partner_type": self.partner_type,
            "transaction_type": self.transaction_type,
            "telegram_user_id": self.telegram_user_id,
            "invoice_payload": self.invoice_payload,
            "subscription_period": self.subscription_period,
            "semantic_digest": self.semantic_digest,
        }


@dataclass(frozen=True)
class StarScanIssue:
    """Sanitized evidence that a provider row could not be trusted."""

    issue_key: str
    severity: str
    reason_code: str
    transaction_id: str | None = None
    direction: str | None = None
    telegram_user_id: int | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "issue_key": self.issue_key,
            "severity": self.severity,
            "reason_code": self.reason_code,
            "transaction_id": self.transaction_id,
            "direction": self.direction,
            "telegram_user_id": self.telegram_user_id,
        }


@dataclass(frozen=True)
class StarReconciliationResult:
    run_id: str
    bot_id: int
    provider_origin: str
    clean: bool
    pass_count: int
    transaction_count: int
    terminal_offset: int
    snapshot_digest: str | None
    issue_count: int
    error_code: str | None
    summary: Mapping[str, Any]


@dataclass(frozen=True)
class _PassSnapshot:
    observations: tuple[StarTransactionObservation, ...]
    issues: tuple[StarScanIssue, ...]
    terminal_offset: int
    digest: str


class _ScanFailure(RuntimeError):
    def __init__(self, error_code: str):
        super().__init__(error_code)
        self.error_code = error_code


def reconcile_star_transactions(
    store: StarScanStore,
    api: StarProvider,
    *,
    run_id: str | None = None,
    max_transactions: int = 10_000,
    now: datetime | None = None,
) -> StarReconciliationResult:
    """Fetch two full provider snapshots and atomically offer a stable one.

    A positional provider offset is used only within one pass.  Every pass
    starts at zero, and a failed or drifting scan is recorded without calling
    ``complete_star_scan``.  Store-side completion is responsible for matching
    the stable positive observations against local payment state.
    """

    selected_run_id = _validated_run_id(run_id or "stars-" + uuid.uuid4().hex)
    if (
        isinstance(max_transactions, bool)
        or not isinstance(max_transactions, int)
        or not 1 <= max_transactions <= 1_000_000
    ):
        raise ValueError("max_transactions must be between 1 and 1000000")
    if now is not None and (now.tzinfo is None or now.utcoffset() is None):
        raise ValueError("now must include a timezone")

    origin = _validated_provider_origin(getattr(api, "provider_origin", None))
    try:
        bot_id = api.get_bot_id()
    except Exception:
        # Some HTTP clients place their request URL in the exception chain.
        # A Telegram request URL contains the bot token, so suppress the cause.
        raise StarReconciliationError("Telegram provider identity request failed") from None
    if (
        isinstance(bot_id, bool)
        or not isinstance(bot_id, int)
        or not 1 <= bot_id <= MAX_TELEGRAM_USER_ID
    ):
        raise StarReconciliationError("Telegram provider returned an invalid bot ID")

    # Binding precedes a run so a changed token/origin cannot write a foreign
    # ledger into an existing gateway database.
    store.bind_star_provider(bot_id, origin)
    store.begin_star_scan(selected_run_id, bot_id, origin, now=now)

    pass_count = 0
    first: _PassSnapshot | None = None
    try:
        first = _fetch_full_pass(api, max_transactions=max_transactions)
        pass_count = 1
        second = _fetch_full_pass(api, max_transactions=max_transactions)
        pass_count = 2
        if first.digest != second.digest:
            raise _ScanFailure("unstable_provider_snapshot")

        observation_mappings = [item.to_mapping() for item in second.observations]
        issue_mappings = [item.to_mapping() for item in second.issues]
        summary = store.complete_star_scan(
            selected_run_id,
            observation_mappings,
            second.terminal_offset,
            second.digest,
            issue_mappings,
            pass_digests=(first.digest, second.digest),
            now=now,
        )
        if not isinstance(summary, Mapping):
            raise _ScanFailure("invalid_store_summary")
        summary_copy = dict(summary)
        # The persistence layer also knows about local-only/provider-only
        # mismatches.  It must affirm health explicitly; an incomplete summary
        # can never arm commerce by default.
        store_clean = summary_copy.get("clean") is True
        clean = not issue_mappings and store_clean
        stored_issue_count = summary_copy.get("issues")
        if (
            isinstance(stored_issue_count, bool)
            or not isinstance(stored_issue_count, int)
            or stored_issue_count < 0
        ):
            stored_issue_count = 0
        return StarReconciliationResult(
            run_id=selected_run_id,
            bot_id=bot_id,
            provider_origin=origin,
            clean=clean,
            pass_count=pass_count,
            transaction_count=len(second.observations),
            terminal_offset=second.terminal_offset,
            snapshot_digest=second.digest,
            issue_count=max(len(second.issues), stored_issue_count),
            error_code=None,
            summary=summary_copy,
        )
    except _ScanFailure as exc:
        store.fail_star_scan(
            selected_run_id, exc.error_code, pass_count=pass_count, now=now
        )
        return StarReconciliationResult(
            run_id=selected_run_id,
            bot_id=bot_id,
            provider_origin=origin,
            clean=False,
            pass_count=pass_count,
            transaction_count=len(first.observations) if first is not None else 0,
            terminal_offset=first.terminal_offset if first is not None else 0,
            snapshot_digest=first.digest if first is not None else None,
            issue_count=len(first.issues) if first is not None else 0,
            error_code=exc.error_code,
            summary={},
        )
    except Exception:
        # Provider and persistence failures may carry request URLs or other
        # sensitive detail.  Persist and return only a finite error code.
        error_code = "star_scan_failed"
        store.fail_star_scan(
            selected_run_id, error_code, pass_count=pass_count, now=now
        )
        return StarReconciliationResult(
            run_id=selected_run_id,
            bot_id=bot_id,
            provider_origin=origin,
            clean=False,
            pass_count=pass_count,
            transaction_count=len(first.observations) if first is not None else 0,
            terminal_offset=first.terminal_offset if first is not None else 0,
            snapshot_digest=first.digest if first is not None else None,
            issue_count=len(first.issues) if first is not None else 0,
            error_code=error_code,
            summary={},
        )


def normalize_star_transaction(
    value: Mapping[str, Any],
) -> StarTransactionObservation:
    """Normalize one provider row without retaining nested Telegram objects."""

    if not isinstance(value, Mapping):
        raise StarTransactionValidationError("transaction_not_object")

    transaction_id = _optional_bounded_text(
        value.get("id"), MAX_TRANSACTION_ID_BYTES
    )
    if transaction_id is None:
        raise StarTransactionValidationError("transaction_id_invalid")

    source_present = "source" in value and value.get("source") is not None
    receiver_present = "receiver" in value and value.get("receiver") is not None
    if source_present == receiver_present:
        raise StarTransactionValidationError(
            "transaction_direction_invalid", transaction_id=transaction_id
        )
    direction = "incoming" if source_present else "outgoing"
    partner_value = value.get("source") if source_present else value.get("receiver")
    if not isinstance(partner_value, Mapping):
        raise StarTransactionValidationError(
            "transaction_partner_invalid",
            transaction_id=transaction_id,
            direction=direction,
        )

    amount = value.get("amount")
    if (
        isinstance(amount, bool)
        or not isinstance(amount, int)
        or not 0 <= amount <= MAX_STAR_AMOUNT
    ):
        raise StarTransactionValidationError(
            "transaction_amount_invalid",
            transaction_id=transaction_id,
            direction=direction,
        )
    nanostar_amount = value.get("nanostar_amount", 0)
    if (
        isinstance(nanostar_amount, bool)
        or not isinstance(nanostar_amount, int)
        or not 0 <= nanostar_amount <= 999_999_999
    ):
        raise StarTransactionValidationError(
            "transaction_nanostar_amount_invalid",
            transaction_id=transaction_id,
            direction=direction,
        )
    if amount == 0 and nanostar_amount == 0:
        raise StarTransactionValidationError(
            "transaction_amount_empty",
            transaction_id=transaction_id,
            direction=direction,
        )
    transaction_date = value.get("date")
    if (
        isinstance(transaction_date, bool)
        or not isinstance(transaction_date, int)
        or not 1 <= transaction_date <= MAX_TRANSACTION_DATE
    ):
        raise StarTransactionValidationError(
            "transaction_date_invalid",
            transaction_id=transaction_id,
            direction=direction,
        )

    partner_type = _optional_bounded_text(partner_value.get("type"), 64)
    if partner_type is None:
        raise StarTransactionValidationError(
            "partner_type_invalid",
            transaction_id=transaction_id,
            direction=direction,
        )
    if partner_type not in _PARTNER_TYPES:
        raise StarTransactionValidationError(
            "partner_type_unsupported",
            transaction_id=transaction_id,
            direction=direction,
        )
    if partner_type == "other":
        # Telegram deliberately leaves this partner variant unstructured.
        # Treating it as a clean observation would make a reconciliation run
        # claim more understanding than the provider evidence actually gives.
        raise StarTransactionValidationError(
            "partner_type_other_opaque",
            transaction_id=transaction_id,
            direction=direction,
        )

    transaction_type: str | None = None
    telegram_user_id: int | None = None
    invoice_payload: str | None = None
    subscription_period: int | None = None

    if partner_type == "user":
        parsed_type = _optional_bounded_text(partner_value.get("transaction_type"), 64)
        if parsed_type is None:
            raise StarTransactionValidationError(
                "user_transaction_type_invalid",
                transaction_id=transaction_id,
                direction=direction,
            )
        if parsed_type not in _USER_TRANSACTION_TYPES:
            raise StarTransactionValidationError(
                "user_transaction_type_unsupported",
                transaction_id=transaction_id,
                direction=direction,
            )
        transaction_type = parsed_type
        user = partner_value.get("user")
        user_id = user.get("id") if isinstance(user, Mapping) else None
        if (
            isinstance(user_id, bool)
            or not isinstance(user_id, int)
            or not 1 <= user_id <= MAX_TELEGRAM_USER_ID
        ):
            raise StarTransactionValidationError(
                "telegram_user_id_invalid",
                transaction_id=transaction_id,
                direction=direction,
            )

        if transaction_type == "invoice_payment":
            telegram_user_id = user_id
            if "invoice_payload" in partner_value:
                invoice_payload = _optional_bounded_text(
                    partner_value.get("invoice_payload"), MAX_INVOICE_PAYLOAD_BYTES
                )
                if invoice_payload is None:
                    raise StarTransactionValidationError(
                        "invoice_payload_invalid",
                        transaction_id=transaction_id,
                        direction=direction,
                        telegram_user_id=user_id,
                    )
            if "subscription_period" in partner_value:
                raw_period = partner_value.get("subscription_period")
                if (
                    isinstance(raw_period, bool)
                    or not isinstance(raw_period, int)
                    or raw_period != SUBSCRIPTION_PERIOD_SECONDS
                ):
                    raise StarTransactionValidationError(
                        "subscription_period_unsupported",
                        transaction_id=transaction_id,
                        direction=direction,
                        telegram_user_id=user_id,
                    )
                subscription_period = raw_period
            if (
                invoice_payload is not None
                and invoice_payload.startswith("sub:v1:")
                and partner_value.get("affiliate") is not None
            ):
                raise StarTransactionValidationError(
                    "kingdom_affiliate_unexpected",
                    transaction_id=transaction_id,
                    direction=direction,
                    telegram_user_id=user_id,
                )

    normalized: dict[str, Any] = {
        "transaction_id": transaction_id,
        "direction": direction,
        "amount": amount,
        "nanostar_amount": nanostar_amount,
        "transaction_date": transaction_date,
        "partner_type": partner_type,
        "transaction_type": transaction_type,
        "telegram_user_id": telegram_user_id,
        "invoice_payload": invoice_payload,
        "subscription_period": subscription_period,
    }
    digest = _canonical_digest(normalized)
    return StarTransactionObservation(**normalized, semantic_digest=digest)


def _fetch_full_pass(
    api: StarProvider, *, max_transactions: int
) -> _PassSnapshot:
    observations: dict[tuple[str, str], StarTransactionObservation] = {}
    issues: list[StarScanIssue] = []
    offset = 0

    while True:
        try:
            page = api.get_star_transactions(offset, STAR_PAGE_LIMIT)
        except Exception as exc:
            raise _ScanFailure("provider_transaction_fetch_failed") from exc
        if not isinstance(page, list) or len(page) > STAR_PAGE_LIMIT:
            raise _ScanFailure("provider_transaction_page_invalid")
        if not page:
            break
        if offset + len(page) > max_transactions:
            raise _ScanFailure("provider_transaction_limit_exceeded")

        for page_index, value in enumerate(page):
            ordinal = offset + page_index
            try:
                observation = normalize_star_transaction(value)
            except StarTransactionValidationError as exc:
                issues.append(_issue_from_validation(exc, ordinal=ordinal))
                continue
            if observation.identity in observations:
                # The provider documents transaction IDs as unique, apart from
                # a refund which is distinguished here by the other direction.
                raise _ScanFailure("duplicate_provider_transaction_identity")
            observations[observation.identity] = observation

        offset += len(page)

    ordered_observations = tuple(
        observations[key] for key in sorted(observations)
    )
    ordered_issues = tuple(sorted(issues, key=lambda item: item.issue_key))
    snapshot_payload = {
        "terminal_offset": offset,
        "observations": [item.to_mapping() for item in ordered_observations],
        "issues": [item.to_mapping() for item in ordered_issues],
    }
    return _PassSnapshot(
        observations=ordered_observations,
        issues=ordered_issues,
        terminal_offset=offset,
        digest=_canonical_digest(snapshot_payload),
    )


def _issue_from_validation(
    error: StarTransactionValidationError, *, ordinal: int
) -> StarScanIssue:
    material = {
        "ordinal": ordinal,
        "reason_code": error.reason_code,
        "transaction_id": error.transaction_id,
        "direction": error.direction,
        "telegram_user_id": error.telegram_user_id,
    }
    return StarScanIssue(
        issue_key="star-issue-" + _canonical_digest(material)[:32],
        severity="critical",
        reason_code=error.reason_code,
        transaction_id=error.transaction_id,
        direction=error.direction,
        telegram_user_id=error.telegram_user_id,
    )


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _optional_bounded_text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        return None
    if len(encoded) > limit:
        return None
    return value


def _validated_run_id(value: str) -> str:
    if not isinstance(value, str) or _RUN_ID_RE.fullmatch(value) is None:
        raise ValueError("run_id is invalid")
    return value


def _validated_provider_origin(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("provider_origin is invalid")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError:
        raise ValueError("provider_origin is invalid") from None
    if not 1 <= len(encoded) <= 256:
        raise ValueError("provider_origin is invalid")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError("provider_origin is invalid")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        raise ValueError("provider_origin is invalid") from None
    try:
        loopback = hostname == "localhost" or ipaddress.ip_address(
            hostname or ""
        ).is_loopback
    except ValueError:
        loopback = hostname == "localhost"
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "http" and not loopback)
    ):
        raise ValueError("provider_origin must be a bare HTTP(S) origin")
    return value.rstrip("/")
