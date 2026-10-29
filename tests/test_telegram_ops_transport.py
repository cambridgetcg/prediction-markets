from __future__ import annotations

import http.client
import io
import json
import urllib.error
import urllib.request
import urllib.response
from email.message import Message
from typing import Any

import pytest

from telegram_gateway.telegram_api import (
    PRODUCTION_TELEGRAM_ORIGIN,
    TelegramAPI,
    TelegramError,
    validate_ops_origin,
)


TOKEN = "fixture:telegram-token-never-live"
PRIVATE_ID = 701
MAX_ID = (1 << 52) - 1


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("transport tests must not open a network connection")

    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)


class Response:
    def __init__(self, body: bytes):
        self.body = io.BytesIO(body)
        self.read_limits: list[int] = []

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.body.close()

    def read(self, limit: int) -> bytes:
        self.read_limits.append(limit)
        return self.body.read(limit)


class FakeOpener:
    def __init__(self, *responses: Any):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: Any, *, timeout: float) -> Response:
        self.calls.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "payload": json.loads(request.data),
                "timeout": timeout,
            }
        )
        assert self.responses, "unexpected Telegram request"
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, Response):
            return result
        return Response(json.dumps({"ok": True, "result": result}).encode())


def private_receipt(**changes: Any) -> dict[str, Any]:
    return {
        "message_id": 901,
        "chat": {"type": "private", "id": PRIVATE_ID},
        **changes,
    }


def test_private_send_uses_exact_numeric_binding_and_fixed_protections() -> None:
    opener = FakeOpener(private_receipt())
    api = TelegramAPI(TOKEN, request_opener=opener, require_production_origin=True)
    text = "Read-only journal status\nhttps://example.invalid/source"
    assert api.send_private_text(PRIVATE_ID, text) == private_receipt()
    assert opener.calls == [
        {
            "url": f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            "method": "POST",
            "payload": {
                "chat_id": PRIVATE_ID,
                "text": text,
                "link_preview_options": {"is_disabled": True},
                "protect_content": True,
            },
            "timeout": 15.0,
        }
    ]
    assert TOKEN not in repr(api)


@pytest.mark.parametrize("chat_id", [None, True, False, 0, -701, 1.0, "701", "@person", 1 << 52])
def test_private_recipient_must_be_a_bounded_positive_integer(chat_id: Any) -> None:
    opener = FakeOpener()
    with pytest.raises(ValueError, match="private chat_id"):
        TelegramAPI(TOKEN, request_opener=opener).send_private_text(chat_id, "Status")
    assert opener.calls == []


@pytest.mark.parametrize("text", [None, 1, True, "", " \n\t", "x" * 3_801, "bad\x00text", "bad\ud800"])
def test_private_text_is_validated_before_sending(text: Any) -> None:
    opener = FakeOpener()
    with pytest.raises(ValueError, match="private message"):
        TelegramAPI(TOKEN, request_opener=opener).send_private_text(PRIVATE_ID, text)
    assert opener.calls == []


@pytest.mark.parametrize("chat_id", [1, MAX_ID])
def test_private_send_accepts_exact_text_and_id_bounds(chat_id: int) -> None:
    result = private_receipt(chat={"id": chat_id, "type": "private"})
    opener = FakeOpener(result)
    assert TelegramAPI(TOKEN, request_opener=opener).send_private_text(chat_id, "x" * 3_800) == result


@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        {},
        private_receipt(message_id=None),
        private_receipt(message_id=True),
        private_receipt(message_id=False),
        private_receipt(message_id=0),
        private_receipt(message_id=-1),
        private_receipt(message_id="901"),
        private_receipt(message_id=1.0),
        private_receipt(message_id=1 << 52),
        private_receipt(chat=None),
        private_receipt(chat={}),
        private_receipt(chat={"id": PRIVATE_ID, "type": "group"}),
        private_receipt(chat={"id": PRIVATE_ID, "type": "supergroup"}),
        private_receipt(chat={"id": PRIVATE_ID, "type": "channel"}),
        private_receipt(chat={"id": PRIVATE_ID + 1, "type": "private"}),
        private_receipt(chat={"id": str(PRIVATE_ID), "type": "private"}),
        private_receipt(chat={"id": -PRIVATE_ID, "type": "private"}),
    ],
)
def test_invalid_post_send_receipt_is_always_ambiguous(result: Any) -> None:
    opener = FakeOpener(result)
    with pytest.raises(TelegramError, match="invalid sent private") as failure:
        TelegramAPI(TOKEN, request_opener=opener).send_private_text(PRIVATE_ID, "Status")
    assert failure.value.ambiguous is True
    assert len(opener.calls) == 1


def test_boolean_response_chat_id_cannot_equal_numeric_recipient_one() -> None:
    opener = FakeOpener(private_receipt(chat={"id": True, "type": "private"}))
    with pytest.raises(TelegramError) as failure:
        TelegramAPI(TOKEN, request_opener=opener).send_private_text(1, "Status")
    assert failure.value.ambiguous is True


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(TOKEN),
        urllib.error.URLError(TOKEN),
        OSError(TOKEN),
        http.client.IncompleteRead(TOKEN.encode()),
    ],
)
def test_private_transport_failures_are_sanitized_and_never_retried(error: Exception) -> None:
    opener = FakeOpener(error)
    with pytest.raises(TelegramError) as failure:
        TelegramAPI(TOKEN, request_opener=opener).send_private_text(PRIVATE_ID, "Status")
    assert failure.value.ambiguous is True
    assert TOKEN not in str(failure.value)
    assert len(opener.calls) == 1


@pytest.mark.parametrize(
    "http_status,error_code,ambiguous",
    [(400, 400, False), (403, 403, False), (429, 429, False), (500, 500, True),
     (503, 400, True), (400, 500, True), (302, 400, True)],
)
def test_http_rejections_distinguish_definitive_and_unknown_sends(
    http_status: int, error_code: int, ambiguous: bool
) -> None:
    private_text = "PRIVATE_REPLY_SENTINEL"
    raw = json.dumps(
        {
            "ok": False,
            "error_code": error_code,
            "description": TOKEN + private_text,
            "parameters": {"retry_after": 9_999},
        }
    ).encode()
    provider_body = io.BytesIO(raw)
    error = urllib.error.HTTPError(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        http_status, TOKEN, {}, provider_body,
    )
    opener = FakeOpener(error)
    with pytest.raises(TelegramError) as failure:
        TelegramAPI(TOKEN, request_opener=opener).send_private_text(PRIVATE_ID, private_text)
    assert failure.value.ambiguous is ambiguous
    assert failure.value.error_code == (http_status if http_status == 302 else error_code)
    assert failure.value.retry_after == (None if http_status == 302 else 3_600)
    assert TOKEN not in str(failure.value)
    assert private_text not in str(failure.value)
    assert provider_body.closed
    assert len(opener.calls) == 1


@pytest.mark.parametrize("error_code,ambiguous", [(400, False), (429, False), (500, True), (True, True), (None, True)])
def test_json_rejections_remain_sanitized(error_code: Any, ambiguous: bool) -> None:
    response = Response(json.dumps({"ok": False, "error_code": error_code, "description": TOKEN}).encode())
    opener = FakeOpener(response)
    with pytest.raises(TelegramError) as failure:
        TelegramAPI(TOKEN, request_opener=opener).send_private_text(PRIVATE_ID, "Status")
    assert failure.value.ambiguous is ambiguous
    assert TOKEN not in str(failure.value)


@pytest.mark.parametrize(
    "raw",
    [
        b"not JSON", b"", b"\xff", b"[]", b"null", b"{}",
        b'{"ok":1,"error_code":400}',
        b'{"ok":"false","error_code":400}',
        b'{"ok":true,"result":NaN}',
        b'{"ok":true,"result":Infinity}',
        b'{"ok":false,"ok":true,"error_code":400}',
        b'{"ok":true,"result":{"message_id":1,"message_id":2}}',
        b'{"ok":true,"result":' + b"9" * 5_000 + b"}",
        b"[" * 2_000 + b"]" * 2_000,
    ],
)
def test_malformed_json_is_an_ambiguous_send(raw: bytes) -> None:
    opener = FakeOpener(Response(raw))
    with pytest.raises(TelegramError) as failure:
        TelegramAPI(TOKEN, request_opener=opener).send_private_text(PRIVATE_ID, "Status")
    assert failure.value.ambiguous is True
    assert len(opener.calls) == 1


def test_response_read_is_bounded_and_oversize_success_is_unknown() -> None:
    raw = json.dumps({"ok": True, "result": private_receipt()}).encode()
    response = Response(raw + b" " * 1_048_576)
    opener = FakeOpener(response)
    with pytest.raises(TelegramError) as failure:
        TelegramAPI(TOKEN, request_opener=opener).send_private_text(PRIVATE_ID, "Status")
    assert failure.value.ambiguous is True
    assert response.read_limits == [1_048_577]


def test_response_at_byte_limit_is_accepted() -> None:
    raw = json.dumps({"ok": True, "result": private_receipt()}).encode()
    response = Response(raw + b" " * (1_048_576 - len(raw)))
    opener = FakeOpener(response)
    assert TelegramAPI(TOKEN, request_opener=opener).send_private_text(PRIVATE_ID, "Status") == private_receipt()
    assert response.read_limits == [1_048_577]


@pytest.mark.parametrize("base_url", ["https://api.telegram.org", "https://API.TELEGRAM.ORG/"])
def test_ops_production_origin_is_credential_free_and_canonical(base_url: str) -> None:
    assert validate_ops_origin(base_url) == PRODUCTION_TELEGRAM_ORIGIN
    assert TelegramAPI(TOKEN, base_url, require_production_origin=True).provider_origin == PRODUCTION_TELEGRAM_ORIGIN


@pytest.mark.parametrize(
    "base_url",
    ["http://localhost:8080", "http://127.0.0.1:8080", "https://fixture.invalid",
     "https://api.telegram.org:443", "https://api.telegram.org.attacker.invalid",
     "https://api.telegram.org/bot" + TOKEN, "https://user:pass@api.telegram.org",
     "https://api.telegram.org?credential=" + TOKEN, "https://api.telegram.org#" + TOKEN,
     "http://api.telegram.org", "https://api.telegram.org:\n443", "https://[bad",
     "https://api.telegram.org\\@other.invalid", None, b"https://api.telegram.org"],
)
def test_strict_ops_origin_rejects_before_opening_a_credential_request(base_url: Any) -> None:
    opener = FakeOpener()
    with pytest.raises(TelegramError) as failure:
        TelegramAPI(TOKEN, base_url, request_opener=opener, require_production_origin=True).get_me()
    assert opener.calls == []
    assert TOKEN not in str(failure.value)
    with pytest.raises(TelegramError):
        validate_ops_origin(base_url)


@pytest.mark.parametrize("base_url", ["http://localhost:8080", "http://127.0.0.1:8080", "http://[::1]:8080", "https://self-hosted.invalid"])
def test_research_origins_still_work_with_offline_injected_transport(base_url: str) -> None:
    opener = FakeOpener({"id": 7, "is_bot": True})
    api = TelegramAPI(TOKEN, base_url, request_opener=opener)
    assert api.provider_origin == base_url
    assert api.get_bot_id() == 7
    assert opener.calls[0]["url"].startswith(base_url + "/bot")


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize(
    "location",
    [f"https://elsewhere.invalid/bot{TOKEN}/sendMessage",
     f"https://api.telegram.org/bot{TOKEN}/anotherMethod",
     f"/bot{TOKEN}/sameOriginPath",
     f"http://127.0.0.1:8080/bot{TOKEN}/sendMessage"],
)
def test_default_opener_never_follows_same_or_cross_origin_redirects(
    monkeypatch: pytest.MonkeyPatch, status: int, location: str
) -> None:
    opened_urls: list[str] = []
    real_build_opener = urllib.request.build_opener

    def respond(request: Any) -> Any:
        opened_urls.append(request.full_url)
        headers = Message()
        headers["Location"] = location
        body = b'{"ok":false,"error_code":400}'
        response = urllib.response.addinfourl(io.BytesIO(body), headers, request.full_url, status)
        response.msg = "Redirect with " + TOKEN
        return response

    class FakeHTTPS(urllib.request.HTTPSHandler):
        def https_open(self, request: Any) -> Any:
            return respond(request)

    class FakeHTTP(urllib.request.HTTPHandler):
        def http_open(self, request: Any) -> Any:
            return respond(request)

    def build(*handlers: Any) -> Any:
        return real_build_opener(*handlers, FakeHTTPS(), FakeHTTP())

    monkeypatch.setattr(urllib.request, "build_opener", build)
    with pytest.raises(TelegramError, match="redirects are not allowed") as failure:
        TelegramAPI(TOKEN, require_production_origin=True).call("sendMessage", {"chat_id": PRIVATE_ID, "text": "Status"})
    assert failure.value.ambiguous is True
    assert TOKEN not in str(failure.value)
    assert opened_urls == [f"https://api.telegram.org/bot{TOKEN}/sendMessage"]


def test_ops_poll_is_one_bounded_message_only_fetch_and_preserves_wire_order() -> None:
    updates = [{"update_id": value, "message": {}} for value in (901, 3, 701)]
    opener = FakeOpener(updates)
    api = TelegramAPI(TOKEN, request_opener=opener, require_production_origin=True)
    assert api.get_ops_updates(offset=0) == updates
    assert opener.calls == [
        {
            "url": f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            "method": "POST",
            "payload": {"offset": 0, "limit": 20, "timeout": 0, "allowed_updates": ["message"]},
            "timeout": 15.0,
        }
    ]


def test_ops_poll_accepts_highest_signed32_offset_and_finite_timeout() -> None:
    opener = FakeOpener([])
    assert TelegramAPI(TOKEN, request_opener=opener).get_ops_updates(offset=(1 << 31) - 1, timeout=30, limit=1) == []
    assert opener.calls[0]["timeout"] == 40.0
    assert opener.calls[0]["payload"] == {"offset": (1 << 31) - 1, "limit": 1, "timeout": 30, "allowed_updates": ["message"]}


@pytest.mark.parametrize(
    "kwargs",
    [{"offset": -1}, {"offset": True}, {"offset": "1"}, {"offset": 1 << 31}, {"offset": (1 << 31) + 1},
     {"limit": 0}, {"limit": 21}, {"limit": True}, {"limit": 1.0},
     {"timeout": -1}, {"timeout": 31}, {"timeout": True}, {"timeout": 1.0},
     {"timeout": float("inf")}, {"timeout": float("nan")}, {"timeout": None}],
)
def test_ops_poll_bounds_are_validated_without_a_request(kwargs: dict[str, Any]) -> None:
    opener = FakeOpener()
    with pytest.raises(ValueError, match="Ops update page bounds"):
        TelegramAPI(TOKEN, request_opener=opener).get_ops_updates(**{"offset": 0, **kwargs})
    assert opener.calls == []


@pytest.mark.parametrize(
    "result",
    [None, {}, [None], [{}], [{"update_id": True}], [{"update_id": "1"}],
     [{"update_id": -1}], [{"update_id": 1 << 31}], [{"update_id": 1.0}],
     [{"update_id": 1}, {"update_id": 1}], [{"update_id": 1, "message": None}],
     [{"update_id": 1, "message": "bad"}], [{"update_id": 1}, {"message": {}}],
     [{"update_id": value} for value in range(21)]],
)
def test_ops_poll_rejects_whole_malformed_duplicate_or_oversize_batch(result: Any) -> None:
    opener = FakeOpener(result)
    with pytest.raises(TelegramError, match="invalid Ops updates list") as failure:
        TelegramAPI(TOKEN, request_opener=opener).get_ops_updates(offset=0)
    assert failure.value.ambiguous is True
    assert len(opener.calls) == 1


def test_ops_poll_respects_requested_count_and_does_not_discard_old_update_kinds() -> None:
    old_update = {"update_id": 0, "callback_query": {"data": "old-queued-kind"}}
    newest_update = {"update_id": (1 << 31) - 1, "message": {}}
    opener = FakeOpener([old_update, newest_update], [old_update, newest_update])
    api = TelegramAPI(TOKEN, request_opener=opener)
    assert api.get_ops_updates(offset=0) == [old_update, newest_update]
    with pytest.raises(TelegramError, match="invalid Ops updates list"):
        api.get_ops_updates(offset=0, limit=1)


def test_ops_poll_timeout_is_sanitized_without_retry() -> None:
    opener = FakeOpener(TimeoutError(TOKEN))
    with pytest.raises(TelegramError, match="Ops polling failed") as failure:
        TelegramAPI(TOKEN, request_opener=opener).get_ops_updates(offset=0)
    assert TOKEN not in str(failure.value)
    assert len(opener.calls) == 1


def test_research_poll_keeps_existing_inventory_limit_and_timeout_defaults() -> None:
    opener = FakeOpener([])
    assert TelegramAPI(TOKEN, request_opener=opener).get_updates(offset=55, timeout=50) == []
    assert opener.calls[0]["payload"] == {
        "offset": 55,
        "limit": 100,
        "timeout": 50,
        "allowed_updates": ["message", "callback_query", "pre_checkout_query", "subscription", "my_chat_member"],
    }
    assert opener.calls[0]["timeout"] == 60.0


@pytest.mark.parametrize("timeout", [True, False, 0, -1, "15", float("inf"), float("nan")])
def test_direct_transport_requires_finite_positive_timeout(timeout: Any) -> None:
    opener = FakeOpener()
    with pytest.raises(ValueError, match="timeout"):
        TelegramAPI(TOKEN, request_opener=opener).call("getMe", timeout=timeout)
    assert opener.calls == []
