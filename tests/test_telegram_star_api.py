from __future__ import annotations

import json
from typing import Any

import pytest

from telegram_gateway.telegram_api import TelegramAPI, TelegramError


TEST_TOKEN = "secret-token-value"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("Star transport tests must use fake requests")

    monkeypatch.setattr("socket.create_connection", forbidden)


class _Response:
    def __init__(self, value: Any):
        self.body = json.dumps(value).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


def test_get_bot_id_and_star_transactions_validate_and_unwrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    responses = [
        {"ok": True, "result": {"id": 777, "is_bot": True}},
        {
            "ok": True,
            "result": {"transactions": [{"id": "charge-1"}]},
        },
    ]

    def opened(request: Any, *, timeout: float) -> _Response:
        calls.append((request.full_url, json.loads(request.data)))
        return _Response(responses.pop(0))

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", opened)
    api = TelegramAPI(TEST_TOKEN)

    assert api.get_bot_id() == 777
    assert api.get_star_transactions(5, 25) == [{"id": "charge-1"}]
    assert calls[0][0].endswith(f"/bot{TEST_TOKEN}/getMe")
    assert calls[1][1] == {"offset": 5, "limit": 25}


@pytest.mark.parametrize(
    "base_url",
    [
        "https://user:password@api.telegram.org",
        "https://api.telegram.org/private-prefix",
        "https://api.telegram.org?token=value",
        "http://api.telegram.org",
        "file:///tmp/provider",
    ],
)
def test_provider_origin_cannot_contain_credentials_or_paths(base_url: str) -> None:
    api = TelegramAPI(TEST_TOKEN, base_url=base_url)
    with pytest.raises(TelegramError, match="base URL"):
        _ = api.provider_origin


@pytest.mark.parametrize("base_url", ["http://localhost", "http://127.0.0.1:8080"])
def test_plain_http_is_limited_to_loopback_test_origins(base_url: str) -> None:
    assert TelegramAPI(TEST_TOKEN, base_url=base_url).provider_origin == base_url


def test_invalid_provider_shapes_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        {"ok": True, "result": {"id": 777, "is_bot": False}},
        {"ok": True, "result": {"transactions": "not-a-list"}},
    ]

    def opened(_request: Any, *, timeout: float) -> _Response:
        return _Response(responses.pop(0))

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", opened)
    api = TelegramAPI(TEST_TOKEN)
    with pytest.raises(TelegramError, match="bot identity"):
        api.get_bot_id()
    with pytest.raises(TelegramError, match="transaction list"):
        api.get_star_transactions()


@pytest.mark.parametrize("offset,limit", [(-1, 100), (0, 0), (0, 101), (True, 1)])
def test_star_page_bounds_are_strict(offset: Any, limit: Any) -> None:
    with pytest.raises(ValueError, match="page bounds"):
        TelegramAPI(TEST_TOKEN).get_star_transactions(offset, limit)
