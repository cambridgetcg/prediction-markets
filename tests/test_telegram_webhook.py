from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, cast

import pytest

from telegram_gateway.service import BotService, ServiceConfig
from telegram_gateway.store import GatewayStore
from telegram_gateway.telegram_api import TelegramError
from telegram_gateway.webhook import TelegramWebhookIngress


SECRET = "test_webhook-secret_2026"
PATH = "/telegram/webhook"


class RecordingStore:
    def __init__(self) -> None:
        self.failed: list[dict[str, Any]] = []
        self.error: Exception | None = None

    def mark_update_failed(
        self, update_id: int, *, error_code: str, ambiguous: bool
    ) -> None:
        if self.error is not None:
            raise self.error
        self.failed.append(
            {
                "update_id": update_id,
                "error_code": error_code,
                "ambiguous": ambiguous,
            }
        )


class RecordingService:
    def __init__(self, *, result: bool = True, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.updates: list[Mapping[str, Any]] = []
        self.store = RecordingStore()

    def handle_update(self, update: Mapping[str, Any]) -> bool:
        self.updates.append(update)
        if self.error is not None:
            raise self.error
        return self.result


class CommerceProbeTransport:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.invoice_calls: list[tuple[str, int]] = []

    def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: Mapping[str, Any] | None = None,
        protect_content: bool = False,
    ) -> Mapping[str, Any]:
        del chat_id, reply_markup, protect_content
        self.sent.append(text)
        return {"message_id": len(self.sent)}

    def create_subscription_link(self, *, payload: str, stars_amount: int) -> str:
        self.invoice_calls.append((payload, stars_amount))
        return "https://example.invalid/invoice"


def ingress(
    service: RecordingService | None = None, *, max_body_bytes: int = 262_144
) -> tuple[TelegramWebhookIngress, RecordingService]:
    target = service or RecordingService()
    adapter = TelegramWebhookIngress(
        cast(BotService, target),
        secret_token=SECRET,
        path=PATH,
        max_body_bytes=max_body_bytes,
    )
    return adapter, target


def request_headers(
    body: bytes,
    *,
    secret: str = SECRET,
    content_type: str = "application/json",
) -> list[tuple[str, str]]:
    return [
        ("X-Telegram-Bot-Api-Secret-Token", secret),
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
    ]


def dispatch(
    adapter: TelegramWebhookIngress,
    body: bytes,
    *,
    method: str = "POST",
    path: str = PATH,
    headers: Mapping[str, str] | list[tuple[str, str]] | None = None,
):
    return adapter.dispatch(
        method=method,
        path=path,
        headers=request_headers(body) if headers is None else headers,
        body=body,
    )


def test_authenticated_json_object_routes_exactly_once() -> None:
    adapter, service = ingress()
    body = json.dumps({"update_id": 42, "message": {"text": "/help"}}).encode()

    response = dispatch(adapter, body)

    assert response.status == 204
    assert response.outcome == "processed"
    assert response.body == b""
    assert service.updates == [{"update_id": 42, "message": {"text": "/help"}}]


def test_service_ignore_is_acknowledged_without_a_second_dispatch() -> None:
    adapter, service = ingress(RecordingService(result=False))
    body = b'{"update_id":42}'

    response = dispatch(adapter, body)

    assert response.status == 204
    assert response.outcome == "ignored"
    assert len(service.updates) == 1


def test_webhook_cannot_turn_a_price_into_commerce_without_explicit_opt_in(
    tmp_path: Path,
) -> None:
    transport = CommerceProbeTransport()
    with GatewayStore(tmp_path / "private" / "gateway.db") as store:
        service = BotService(
            store,
            cast(Any, transport),
            ServiceConfig(stars_amount=250, terms_version="terms-v1"),
        )
        adapter = TelegramWebhookIngress(service, secret_token=SECRET, path=PATH)
        body = json.dumps(
            {
                "update_id": 1,
                "message": {
                    "message_id": 1,
                    "from": {"id": 101},
                    "chat": {"id": 101, "type": "private"},
                    "text": "/subscribe",
                },
            }
        ).encode("utf-8")

        response = dispatch(adapter, body)

    assert response.status == 204
    assert response.outcome == "processed"
    assert transport.invoice_calls == []
    assert "disabled" in transport.sent[-1].lower()


@pytest.mark.parametrize(
    ("method", "path", "expected_status", "expected_outcome"),
    [
        ("GET", PATH, 405, "method_not_allowed"),
        ("post", PATH, 405, "method_not_allowed"),
        ("POST", PATH + "/", 404, "not_found"),
        ("POST", PATH + "?key=value", 404, "not_found"),
    ],
)
def test_method_and_path_are_exact(
    method: str, path: str, expected_status: int, expected_outcome: str
) -> None:
    adapter, service = ingress()

    response = dispatch(adapter, b"{}", method=method, path=path)

    assert response.status == expected_status
    assert response.outcome == expected_outcome
    assert service.updates == []


@pytest.mark.parametrize(
    "headers",
    [
        [("Content-Type", "application/json"), ("Content-Length", "2")],
        request_headers(b"{}", secret="wrong-secret"),
        request_headers(b"{}")
        + [("x-telegram-bot-api-secret-token", SECRET)],
        request_headers(b"{}", secret="test_webhook-secret_2026 "),
        request_headers(b"{}", secret="t\u00f6ken"),
    ],
)
def test_missing_wrong_or_duplicate_secret_is_rejected(
    headers: list[tuple[str, str]],
) -> None:
    adapter, service = ingress()

    response = dispatch(adapter, b"{}", headers=headers)

    assert response.status == 401
    assert response.outcome == "unauthorized"
    assert service.updates == []


def test_secret_comparison_uses_constant_time_primitive(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, _ = ingress()
    calls: list[tuple[bytes, bytes]] = []

    def compared(candidate: bytes, expected: bytes) -> bool:
        calls.append((candidate, expected))
        return False

    monkeypatch.setattr("telegram_gateway.webhook.hmac.compare_digest", compared)

    response = dispatch(adapter, b"{}")

    assert response.status == 401
    assert calls == [(SECRET.encode("ascii"), SECRET.encode("ascii"))]


@pytest.mark.parametrize(
    "content_type",
    ["application/json", "APPLICATION/JSON", "application/json; charset=UTF-8"],
)
def test_supported_json_content_types(content_type: str) -> None:
    adapter, service = ingress()
    body = b'{"update_id":1}'

    response = dispatch(
        adapter, body, headers=request_headers(body, content_type=content_type)
    )

    assert response.status == 204
    assert response.outcome == "processed"
    assert len(service.updates) == 1


@pytest.mark.parametrize(
    "headers",
    [
        [
            ("X-Telegram-Bot-Api-Secret-Token", SECRET),
            ("Content-Length", "2"),
        ],
        request_headers(b"{}", content_type="text/json"),
        request_headers(b"{}", content_type="application/json; version=1"),
        request_headers(b"{}") + [("Content-Type", "application/json")],
    ],
)
def test_invalid_content_type_is_permanently_rejected_and_acknowledged(
    headers: list[tuple[str, str]],
) -> None:
    adapter, service = ingress()

    response = dispatch(adapter, b"{}", headers=headers)

    assert response.status == 204
    assert response.outcome == "rejected_content_type"
    assert service.updates == []


@pytest.mark.parametrize(
    ("body", "headers", "expected_outcome"),
    [
        (
            b"{}",
            [
                ("X-Telegram-Bot-Api-Secret-Token", SECRET),
                ("Content-Type", "application/json"),
            ],
            "rejected_content_length",
        ),
        (b"{}", request_headers(b"{}")[:-1] + [("Content-Length", "+2")], "rejected_content_length"),
        (b"{}", request_headers(b"{}")[:-1] + [("Content-Length", "02")], "rejected_content_length"),
        (b"{}", request_headers(b"x"), "rejected_content_length"),
        (
            b"{}",
            request_headers(b"{}") + [("Content-Length", "2")],
            "rejected_content_length",
        ),
        (
            b"{}",
            request_headers(b"{}") + [("Transfer-Encoding", "chunked")],
            "rejected_transfer_encoding",
        ),
    ],
)
def test_request_framing_is_strict_and_permanent_failures_are_acknowledged(
    body: bytes, headers: list[tuple[str, str]], expected_outcome: str
) -> None:
    adapter, service = ingress()

    response = dispatch(adapter, body, headers=headers)

    assert response.status == 204
    assert response.outcome == expected_outcome
    assert service.updates == []


def test_actual_and_declared_body_sizes_are_bounded() -> None:
    adapter, service = ingress(max_body_bytes=16)
    body = b'{"update_id":123}'
    assert len(body) == 17

    response = dispatch(adapter, body)

    assert response.status == 204
    assert response.outcome == "rejected_body_size"
    assert service.updates == []


@pytest.mark.parametrize(
    ("body", "expected_outcome"),
    [
        (b"", "rejected_json"),
        (b"{", "rejected_json"),
        (b"\xff", "rejected_json"),
        (b'{"update_id":1,"update_id":2}', "rejected_json"),
        (b'{"update_id":NaN}', "rejected_json"),
        (b"[]", "rejected_json_object"),
        (b'"object"', "rejected_json_object"),
    ],
)
def test_invalid_json_never_reaches_the_service(
    body: bytes, expected_outcome: str
) -> None:
    adapter, service = ingress()

    response = dispatch(adapter, body)

    assert response.status == 204
    assert response.outcome == expected_outcome
    assert service.updates == []


@pytest.mark.parametrize(
    ("error", "expected_outcome", "expected_code", "ambiguous"),
    [
        (ValueError("bad update"), "quarantined_invalid_update", "invalid_update", False),
        (
            TelegramError("blocked", error_code=403, ambiguous=False),
            "quarantined_telegram_error",
            "403",
            False,
        ),
        (
            TelegramError("uncertain", ambiguous=True),
            "quarantined_telegram_error",
            "telegram_transport",
            True,
        ),
    ],
)
def test_known_service_failures_are_quarantined_and_acknowledged(
    error: Exception, expected_outcome: str, expected_code: str, ambiguous: bool
) -> None:
    service = RecordingService(error=error)
    adapter, service = ingress(service)
    body = b'{"update_id":9}'

    response = dispatch(adapter, body)

    assert response.status == 204
    assert response.outcome == expected_outcome
    assert service.store.failed == [
        {"update_id": 9, "error_code": expected_code, "ambiguous": ambiguous}
    ]


def test_invalid_update_id_cannot_poison_failure_ledger() -> None:
    service = RecordingService(error=ValueError("bad update"))
    adapter, service = ingress(service)
    body = b'{"update_id":1000000000000}'

    response = dispatch(adapter, body)

    assert response.status == 204
    assert response.outcome == "quarantined_invalid_update"
    assert service.store.failed == []


def test_unexpected_internal_failure_returns_retryable_503_without_details() -> None:
    service = RecordingService(error=RuntimeError("secret internal detail"))
    adapter, service = ingress(service)
    body = b'{"update_id":8}'

    response = dispatch(adapter, body)

    assert response.status == 503
    assert response.outcome == "internal_error"
    assert response.body == b"temporarily unavailable\n"
    assert b"secret internal detail" not in response.body
    assert ("Retry-After", "1") in response.headers
    assert service.store.failed == []


def test_failure_to_write_quarantine_returns_retryable_503() -> None:
    service = RecordingService(error=ValueError("bad update"))
    service.store.error = RuntimeError("database unavailable")
    adapter, _ = ingress(service)
    body = b'{"update_id":8}'

    response = dispatch(adapter, body)

    assert response.status == 503
    assert response.outcome == "failure_quarantine_error"


def test_non_byte_body_is_an_internal_adapter_error() -> None:
    adapter, service = ingress()
    body = b"{}"

    response = adapter.dispatch(
        method="POST",
        path=PATH,
        headers=request_headers(body),
        body="{}",  # type: ignore[arg-type]
    )

    assert response.status == 503
    assert response.outcome == "invalid_body_representation"
    assert service.updates == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"secret_token": ""},
        {"secret_token": "contains space"},
        {"secret_token": "x" * 257},
        {"secret_token": SECRET, "path": "relative"},
        {"secret_token": SECRET, "path": "/hook?query=1"},
        {"secret_token": SECRET, "max_body_bytes": 0},
        {"secret_token": SECRET, "max_body_bytes": True},
        {"secret_token": SECRET, "max_body_bytes": 1_048_577},
    ],
)
def test_configuration_is_bounded(kwargs: dict[str, Any]) -> None:
    service = cast(BotService, RecordingService())
    with pytest.raises(ValueError):
        TelegramWebhookIngress(service, **kwargs)


def test_repr_never_contains_the_secret() -> None:
    adapter, _ = ingress()

    rendered = repr(adapter)

    assert SECRET not in rendered
    assert "<redacted>" in rendered
