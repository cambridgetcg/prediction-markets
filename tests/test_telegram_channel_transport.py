from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest

from telegram_gateway.telegram_api import (
    TelegramAPI,
    TelegramError,
    normalize_channel_ref,
)


TEST_TOKEN = "secret-token-value"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("channel transport tests must use fake requests")

    monkeypatch.setattr("socket.create_connection", forbidden)


class _Response:
    def __init__(self, result: Any):
        self.body = json.dumps({"ok": True, "result": result}).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


def _install_responses(
    monkeypatch: pytest.MonkeyPatch, *results: Any
) -> list[dict[str, Any]]:
    queued = list(results)
    calls: list[dict[str, Any]] = []

    def opened(request: Any, *, timeout: float) -> _Response:
        calls.append(
            {
                "url": request.full_url,
                "payload": json.loads(request.data),
                "timeout": timeout,
            }
        )
        if not queued:
            raise AssertionError("unexpected Telegram API call")
        return _Response(queued.pop(0))

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", opened)
    return calls


def test_channel_post_normalizes_target_and_disables_link_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_responses(
        monkeypatch,
        {
            "id": -1001234567890,
            "type": "channel",
            "username": "KingdomDispatch",
        },
        {
            "message_id": 812,
            "chat": {"id": -1001234567890, "type": "channel"},
        },
    )
    result = TelegramAPI(TEST_TOKEN).send_channel_post(
        "@KingdomDispatch",
        "Evidence-labelled research\nhttps://example.com/source",
    )

    assert result["message_id"] == 812
    assert calls[0]["url"].endswith(f"/bot{TEST_TOKEN}/getChat")
    assert calls[0]["payload"] == {"chat_id": "@kingdomdispatch"}
    assert calls[1]["url"].endswith(f"/bot{TEST_TOKEN}/sendMessage")
    assert calls[1]["payload"] == {
        "chat_id": -1001234567890,
        "text": "Evidence-labelled research\nhttps://example.com/source",
        "link_preview_options": {"is_disabled": True},
        "disable_notification": False,
        "protect_content": False,
    }


def test_channel_post_carries_optional_notification_protection_and_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_responses(
        monkeypatch,
        {"id": -1001234567890, "type": "channel"},
        {
            "message_id": 813,
            "chat": {"id": -1001234567890, "type": "channel"},
        },
    )
    result = TelegramAPI(TEST_TOKEN).send_channel_post(
        -1001234567890,
        "Append-only correction",
        disable_link_preview=True,
        disable_notification=True,
        protect_content=True,
        reply_to_message_id=812,
    )

    assert result["message_id"] == 813
    assert calls[0]["payload"] == {"chat_id": -1001234567890}
    assert calls[1]["payload"] == {
        "chat_id": -1001234567890,
        "text": "Append-only correction",
        "link_preview_options": {"is_disabled": True},
        "disable_notification": True,
        "protect_content": True,
        "reply_parameters": {
            "message_id": 812,
            "allow_sending_without_reply": False,
        },
    }


@pytest.mark.parametrize(
    "channel_ref",
    [101, 0, True, "kingdomdispatch", "@bad", "@name-with-dash", -(1 << 52)],
)
def test_channel_post_rejects_private_or_malformed_targets(channel_ref: Any) -> None:
    with pytest.raises(ValueError, match="channel_ref"):
        TelegramAPI(TEST_TOKEN).send_channel_post(channel_ref, "Research")


def test_channel_target_normalization_is_shared_with_publisher() -> None:
    assert normalize_channel_ref("@KingdomDispatch") == (
        "@kingdomdispatch",
        "@kingdomdispatch",
    )
    assert normalize_channel_ref(-1001234567890) == (
        -1001234567890,
        "-1001234567890",
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"disable_link_preview": False},
        {"disable_link_preview": 1},
        {"disable_notification": 1},
        {"protect_content": 0},
        {"reply_to_message_id": 0},
        {"reply_to_message_id": True},
        {"reply_to_message_id": 1 << 52},
    ],
)
def test_channel_post_flags_are_strict(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        TelegramAPI(TEST_TOKEN).send_channel_post(
            "@kingdomdispatch", "Research", **kwargs
        )


@pytest.mark.parametrize("text", ["", "x" * 4_097, "bad\ud800"])
def test_channel_post_text_must_fit_telegram(text: str) -> None:
    with pytest.raises(ValueError, match="channel post"):
        TelegramAPI(TEST_TOKEN).send_channel_post("@kingdomdispatch", text)


@pytest.mark.parametrize(
    "result",
    [None, {}, {"message_id": 0}, {"message_id": True}, {"message_id": "812"}],
)
def test_channel_post_rejects_unconfirmed_results_as_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
    result: Any,
) -> None:
    _install_responses(
        monkeypatch,
        {
            "id": -1001234567890,
            "type": "channel",
            "username": "kingdomdispatch",
        },
        result,
    )
    with pytest.raises(TelegramError, match="invalid sent channel") as captured:
        TelegramAPI(TEST_TOKEN).send_channel_post("@kingdomdispatch", "Research")
    assert captured.value.ambiguous is True


@pytest.mark.parametrize("chat_type", ["private", "group", "supergroup"])
def test_channel_post_rejects_a_resolved_non_channel_without_sending(
    monkeypatch: pytest.MonkeyPatch,
    chat_type: str,
) -> None:
    calls = _install_responses(
        monkeypatch,
        {
            "id": -1001234567890,
            "type": chat_type,
            "username": "kingdomdispatch",
        },
    )
    with pytest.raises(TelegramError, match="valid channel") as captured:
        TelegramAPI(TEST_TOKEN).send_channel_post("@kingdomdispatch", "Research")
    assert captured.value.ambiguous is False
    assert len(calls) == 1
    assert calls[0]["url"].endswith(f"/bot{TEST_TOKEN}/getChat")


@pytest.mark.parametrize(
    "resolved",
    [
        None,
        {},
        {"id": -1001234567890},
        {"id": 101, "type": "channel"},
        {"id": True, "type": "channel"},
        {"id": "-1001234567890", "type": "channel"},
        {"id": -(1 << 52), "type": "channel"},
    ],
)
def test_channel_post_rejects_malformed_get_chat_without_sending(
    monkeypatch: pytest.MonkeyPatch,
    resolved: Any,
) -> None:
    calls = _install_responses(monkeypatch, resolved)
    with pytest.raises(TelegramError, match="valid channel") as captured:
        TelegramAPI(TEST_TOKEN).send_channel_post(-1001234567890, "Research")
    assert captured.value.ambiguous is False
    assert len(calls) == 1


def test_channel_post_rejects_get_chat_numeric_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_responses(
        monkeypatch,
        {"id": -1009876543210, "type": "channel"},
    )
    with pytest.raises(TelegramError, match="different numeric") as captured:
        TelegramAPI(TEST_TOKEN).send_channel_post(-1001234567890, "Research")
    assert captured.value.ambiguous is False
    assert len(calls) == 1


@pytest.mark.parametrize(
    "resolved",
    [
        {"id": -1001234567890, "type": "channel"},
        {
            "id": -1001234567890,
            "type": "channel",
            "username": "anotherchannel",
        },
        {
            "id": -1001234567890,
            "type": "channel",
            "username": 123,
        },
    ],
)
def test_username_lookup_must_resolve_the_requested_username(
    monkeypatch: pytest.MonkeyPatch,
    resolved: Any,
) -> None:
    calls = _install_responses(monkeypatch, resolved)
    with pytest.raises(TelegramError, match="different username") as captured:
        TelegramAPI(TEST_TOKEN).send_channel_post("@kingdomdispatch", "Research")
    assert captured.value.ambiguous is False
    assert len(calls) == 1


@pytest.mark.parametrize(
    "sent_result",
    [
        {
            "message_id": 812,
            "chat": {"id": -1001234567890, "type": "supergroup"},
        },
        {
            "message_id": 812,
            "chat": {"id": -1009876543210, "type": "channel"},
        },
    ],
)
def test_channel_post_rejects_mismatched_send_acknowledgement_as_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
    sent_result: Any,
) -> None:
    _install_responses(
        monkeypatch,
        {
            "id": -1001234567890,
            "type": "channel",
            "username": "kingdomdispatch",
        },
        sent_result,
    )
    with pytest.raises(TelegramError, match="invalid sent channel") as captured:
        TelegramAPI(TEST_TOKEN).send_channel_post("@kingdomdispatch", "Research")
    assert captured.value.ambiguous is True


def test_failed_read_only_lookup_is_not_an_ambiguous_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def opened(*_args: Any, **_kwargs: Any) -> _Response:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", opened)
    with pytest.raises(TelegramError, match="channel lookup") as captured:
        TelegramAPI(TEST_TOKEN).send_channel_post("@kingdomdispatch", "Research")
    assert captured.value.ambiguous is False


def test_transport_failure_after_successful_lookup_remains_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def opened(*_args: Any, **_kwargs: Any) -> _Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _Response(
                {
                    "id": -1001234567890,
                    "type": "channel",
                    "username": "kingdomdispatch",
                }
            )
        raise urllib.error.URLError("response lost")

    monkeypatch.setattr("telegram_gateway.telegram_api.open_request", opened)
    with pytest.raises(TelegramError, match="transport failed") as captured:
        TelegramAPI(TEST_TOKEN).send_channel_post("@kingdomdispatch", "Research")
    assert captured.value.ambiguous is True
    assert call_count == 2
