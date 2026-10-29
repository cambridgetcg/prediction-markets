"""Small Telegram Bot API client with sanitized failures."""

from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


_BOT_API_METHOD = re.compile(r"[A-Za-z][A-Za-z0-9]{0,63}\Z")
_CHANNEL_USERNAME = re.compile(r"@[A-Za-z][A-Za-z0-9_]{4,31}\Z")
_MAX_TELEGRAM_ID = (1 << 52) - 1
_MAX_RESPONSE_BYTES = 1_048_576
PRODUCTION_TELEGRAM_ORIGIN = "https://api.telegram.org"
MAX_OPS_POLL_OFFSET = (1 << 31) - 1


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        # Even a same-origin redirect can disclose the token to another path.
        # Returning None makes urllib raise HTTPError without opening newurl.
        return None


def open_request(request: urllib.request.Request, *, timeout: float) -> Any:
    """Open one request without redirects; replace this seam for offline tests."""

    return urllib.request.build_opener(_RejectRedirects()).open(request, timeout=timeout)


class TelegramError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: int | None = None,
        retry_after: int | None = None,
        ambiguous: bool = False,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.retry_after = retry_after
        self.ambiguous = ambiguous


@dataclass(frozen=True)
class TelegramAPI:
    token: str
    base_url: str = PRODUCTION_TELEGRAM_ORIGIN
    # Inject only trusted, no-network fixtures here, not redirect-following
    # transports. Live Ops startup must use the default opener and strict origin.
    request_opener: Callable[..., Any] | None = field(
        default=None, kw_only=True, repr=False, compare=False
    )
    require_production_origin: bool = field(default=False, kw_only=True)

    def __repr__(self) -> str:
        return "TelegramAPI(token=<redacted>, base_url=<configured>)"

    @property
    def provider_origin(self) -> str:
        """Return a credential-free provider identity suitable for DB binding."""

        if not isinstance(self.require_production_origin, bool):
            raise TelegramError("Telegram origin policy is invalid")
        if self.require_production_origin:
            return validate_ops_origin(self.base_url)
        return _provider_origin(self.base_url)

    def call(
        self,
        method: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout: float = 15.0,
    ) -> Any:
        if not isinstance(self.token, str):
            raise TelegramError("Telegram bot token is invalid")
        try:
            token_bytes = self.token.encode("ascii")
        except UnicodeError:
            raise TelegramError("Telegram bot token is invalid") from None
        if (
            not 16 <= len(token_bytes) <= 512
            or any(byte < 33 or byte > 126 for byte in token_bytes)
            or any(marker in token_bytes for marker in (b"/", b"?", b"#", b"%", b"\\"))
        ):
            raise TelegramError("Telegram bot token is invalid")
        if not isinstance(method, str) or not _BOT_API_METHOD.fullmatch(method):
            raise TelegramError("Telegram Bot API method is invalid")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 < timeout < float("inf")
        ):
            raise ValueError("Telegram request timeout must be finite and positive")
        url = f"{self.provider_origin}/bot{self.token}/{method}"
        try:
            body = json.dumps(
                dict(payload or {}), separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        except (RecursionError, TypeError, UnicodeError, ValueError):
            raise TelegramError("Telegram request payload is invalid") from None
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "kingdom-telegram-gateway/0.1"},
        )
        try:
            opener = self.request_opener if self.request_opener is not None else open_request
            with opener(request, timeout=timeout) as response:
                result = _read_response(response)
        except urllib.error.HTTPError as exc:
            result = {}
            try:
                with exc:
                    result = _read_response(exc)
            except (
                RecursionError,
                UnicodeError,
                ValueError,
                OSError,
                http.client.HTTPException,
            ):
                pass
            if 300 <= exc.code < 400:
                # The first endpoint might have accepted a send before redirecting.
                raise TelegramError(
                    "Telegram redirects are not allowed",
                    error_code=exc.code,
                    ambiguous=True,
                ) from None
            if not isinstance(result, Mapping):
                result = {}
            parameters = result.get("parameters")
            parameters = parameters if isinstance(parameters, Mapping) else {}
            error_code = _safe_int(result.get("error_code")) or exc.code
            raise TelegramError(
                _safe_description(
                    result.get("description"),
                    fallback=f"Telegram API HTTP {exc.code}",
                    secret=self.token,
                ),
                error_code=error_code,
                retry_after=_safe_retry_after(parameters.get("retry_after")),
                ambiguous=(
                    exc.code >= 500 or not 400 <= error_code < 500
                ),
            ) from None
        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
            OSError,
            http.client.HTTPException,
        ):
            # The request may have reached Telegram even though no response was
            # observed, so callers must not blindly retry a message send.
            raise TelegramError(
                "Telegram transport failed before a response was observed",
                ambiguous=True,
            ) from None
        except (RecursionError, UnicodeError, ValueError):
            raise TelegramError("Telegram returned an invalid response", ambiguous=True) from None

        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            raise TelegramError("Telegram returned an invalid response", ambiguous=True)
        if result["ok"] is False:
            parameters = result.get("parameters")
            parameters = parameters if isinstance(parameters, Mapping) else {}
            error_code = _safe_int(result.get("error_code"))
            raise TelegramError(
                _safe_description(
                    result.get("description"),
                    fallback="Telegram rejected the request",
                    secret=self.token,
                ),
                error_code=error_code,
                retry_after=_safe_retry_after(parameters.get("retry_after")),
                ambiguous=not (
                    error_code is not None and 400 <= error_code < 500
                ),
            )
        return result.get("result")

    def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: Mapping[str, Any] | None = None,
        protect_content: bool = False,
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "link_preview_options": {"is_disabled": True},
            "protect_content": protect_content,
        }
        if reply_markup is not None:
            payload["reply_markup"] = dict(reply_markup)
        result = self.call("sendMessage", payload)
        if (
            not isinstance(result, Mapping)
            or (_safe_int(result.get("message_id")) or 0) <= 0
        ):
            raise TelegramError("Telegram returned an invalid sent message", ambiguous=True)
        return result

    def send_private_text(self, chat_id: int, text: str) -> Mapping[str, Any]:
        """Send one protected plain-text reply to an exact private numeric ID.

        The caller supplies the stored binding, not an incoming update's target.
        Content protection does not provide end-to-end encryption or erasure.
        An invalid receipt is unknown delivery, never permission to retry.
        """

        if (
            isinstance(chat_id, bool)
            or not isinstance(chat_id, int)
            or not 1 <= chat_id <= _MAX_TELEGRAM_ID
        ):
            raise ValueError("private chat_id is invalid")
        body = _bounded_text(text, 3_800, "private message")
        if not body.strip():
            raise ValueError("private message is invalid")
        try:
            result = self.call(
                "sendMessage",
                {
                    "chat_id": chat_id,
                    "text": body,
                    "link_preview_options": {"is_disabled": True},
                    "protect_content": True,
                },
            )
        except TelegramError as exc:
            # Ops errors do not echo provider descriptions or command text.
            raise TelegramError(
                "Telegram private send failed",
                error_code=exc.error_code,
                retry_after=exc.retry_after,
                ambiguous=exc.ambiguous,
            ) from None
        sent_chat = result.get("chat") if isinstance(result, Mapping) else None
        message_id = _safe_int(result.get("message_id")) if isinstance(result, Mapping) else None
        if (
            message_id is None
            or not 1 <= message_id <= _MAX_TELEGRAM_ID
            or not isinstance(sent_chat, Mapping)
            or sent_chat.get("type") != "private"
            or _safe_int(sent_chat.get("id")) != chat_id
        ):
            raise TelegramError(
                "Telegram returned an invalid sent private message", ambiguous=True
            )
        return result

    def send_channel_post(
        self,
        channel_ref: int | str,
        text: str,
        *,
        disable_link_preview: bool = True,
        disable_notification: bool = False,
        protect_content: bool = False,
        reply_to_message_id: int | None = None,
    ) -> Mapping[str, Any]:
        """Send one plain-text post through the channel-only transport surface.

        A negative numeric ID can also name a supergroup at the Bot API level,
        so every target is resolved with ``getChat`` and must report
        ``type=channel``.  The subsequent send uses that resolved numeric ID,
        not a reusable username.
        """

        target, canonical = normalize_channel_ref(channel_ref)
        body = _bounded_text(text, 4_096, "channel post")
        if disable_link_preview is not True:
            raise ValueError("channel post link previews must remain disabled")
        if not isinstance(disable_notification, bool):
            raise ValueError("disable_notification must be a boolean")
        if not isinstance(protect_content, bool):
            raise ValueError("protect_content must be a boolean")
        if reply_to_message_id is not None and (
            isinstance(reply_to_message_id, bool)
            or not isinstance(reply_to_message_id, int)
            or not 1 <= reply_to_message_id <= _MAX_TELEGRAM_ID
        ):
            raise ValueError("reply_to_message_id is invalid")

        try:
            resolved = self.call("getChat", {"chat_id": target})
        except TelegramError as exc:
            # getChat is read-only: even a lost response cannot have published
            # the message, so the publisher may safely classify this attempt
            # as a known failure rather than an unknown send.
            raise TelegramError(
                "Telegram channel lookup failed",
                error_code=exc.error_code,
                retry_after=exc.retry_after,
                ambiguous=False,
            ) from None
        resolved_id = _safe_int(resolved.get("id")) if isinstance(resolved, Mapping) else None
        resolved_type = resolved.get("type") if isinstance(resolved, Mapping) else None
        if (
            resolved_type != "channel"
            or resolved_id is None
            or not -_MAX_TELEGRAM_ID <= resolved_id < 0
        ):
            raise TelegramError(
                "Telegram target did not resolve to a valid channel",
                ambiguous=False,
            )
        if isinstance(target, int) and resolved_id != target:
            raise TelegramError(
                "Telegram channel lookup returned a different numeric target",
                ambiguous=False,
            )
        if isinstance(target, str):
            username = resolved.get("username")
            if (
                not isinstance(username, str)
                or not _CHANNEL_USERNAME.fullmatch("@" + username)
                or "@" + username.lower() != canonical
            ):
                raise TelegramError(
                    "Telegram channel lookup returned a different username",
                    ambiguous=False,
                )

        payload: dict[str, Any] = {
            "chat_id": resolved_id,
            "text": body,
            "link_preview_options": {"is_disabled": True},
            "disable_notification": disable_notification,
            "protect_content": protect_content,
        }
        if reply_to_message_id is not None:
            payload["reply_parameters"] = {
                "message_id": reply_to_message_id,
                "allow_sending_without_reply": False,
            }
        result = self.call("sendMessage", payload)
        sent_chat = result.get("chat") if isinstance(result, Mapping) else None
        if (
            not isinstance(result, Mapping)
            or (_safe_int(result.get("message_id")) or 0) <= 0
            or not isinstance(sent_chat, Mapping)
            or sent_chat.get("type") != "channel"
            or _safe_int(sent_chat.get("id")) != resolved_id
        ):
            # Telegram may have accepted the post before returning a malformed
            # or lost acknowledgement, so callers must reconcile before retry.
            raise TelegramError(
                "Telegram returned an invalid sent channel message", ambiguous=True
            )
        return result

    def create_subscription_link(
        self,
        *,
        payload: str,
        stars_amount: int,
    ) -> str:
        result = self.call(
            "createInvoiceLink",
            {
                "title": "KINGDOM Research",
                "description": "30-day recurring access to evidence-labelled market research.",
                "payload": payload,
                "provider_token": "",
                "currency": "XTR",
                "prices": [{"label": "30-day research access", "amount": stars_amount}],
                "subscription_period": 2_592_000,
            },
        )
        if not isinstance(result, str) or not result.startswith("https://"):
            raise TelegramError("Telegram returned an invalid invoice link", ambiguous=True)
        return result

    def answer_callback(self, callback_query_id: str, text: str = "") -> bool:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:200]
        return self._require_true("answerCallbackQuery", payload)

    def answer_pre_checkout(
        self, pre_checkout_query_id: str, *, ok: bool, error_message: str | None = None
    ) -> bool:
        payload: dict[str, Any] = {"pre_checkout_query_id": pre_checkout_query_id, "ok": ok}
        if not ok:
            payload["error_message"] = (error_message or "Checkout could not be verified.")[:200]
        return self._require_true("answerPreCheckoutQuery", payload, timeout=8.0)

    def edit_subscription(
        self, *, user_id: int, initial_charge_id: str, canceled: bool
    ) -> bool:
        return self._require_true(
            "editUserStarSubscription",
            {
                "user_id": user_id,
                "telegram_payment_charge_id": initial_charge_id,
                "is_canceled": canceled,
            },
        )

    def _require_true(
        self,
        method: str,
        payload: Mapping[str, Any],
        *,
        timeout: float = 15.0,
    ) -> bool:
        if self.call(method, payload, timeout=timeout) is not True:
            raise TelegramError(
                f"Telegram returned an invalid {method} confirmation", ambiguous=True
            )
        return True

    def get_me(self) -> Mapping[str, Any]:
        """Return a bounded allowlist from ``getMe``; never echo the token."""

        result = self.call("getMe")
        if not isinstance(result, Mapping) or result.get("is_bot") is not True:
            raise TelegramError("Telegram returned an invalid bot identity", ambiguous=True)
        bot_id = _safe_int(result.get("id"))
        username = result.get("username")
        if (
            bot_id is None
            or bot_id <= 0
            or not isinstance(username, str)
            or not 5 <= len(username) <= 32
            or not re.fullmatch(r"[A-Za-z0-9_]{2,29}[Bb][Oo][Tt]", username)
        ):
            raise TelegramError("Telegram returned an invalid bot identity", ambiguous=True)
        safe: dict[str, Any] = {
            "id": bot_id,
            "is_bot": True,
            "username": username,
        }
        for field in (
            "can_join_groups",
            "can_read_all_group_messages",
            "supports_guest_queries",
            "supports_inline_queries",
            "can_connect_to_business",
            "has_main_web_app",
            "has_topics_enabled",
            "allows_users_to_create_topics",
            "can_manage_bots",
            "supports_join_request_queries",
        ):
            value = result.get(field)
            if value is not None and not isinstance(value, bool):
                raise TelegramError(
                    "Telegram returned invalid bot capabilities", ambiguous=True
                )
            safe[field] = value
        return safe

    def get_webhook_info(self) -> Mapping[str, Any]:
        """Return webhook health without returning its potentially secret URL."""

        result = self.call("getWebhookInfo")
        if not isinstance(result, Mapping):
            raise TelegramError("Telegram returned invalid webhook information", ambiguous=True)
        url = result.get("url")
        pending = _safe_int(result.get("pending_update_count"))
        custom_certificate = result.get("has_custom_certificate")
        if (
            not isinstance(url, str)
            or len(url) > 4_096
            or pending is None
            or pending < 0
            or not isinstance(custom_certificate, bool)
        ):
            raise TelegramError("Telegram returned invalid webhook information", ambiguous=True)
        error_dates = (
            result.get("last_error_date"),
            result.get("last_synchronization_error_date"),
        )
        if any(
            value is not None
            and ((parsed := _safe_int(value)) is None or parsed < 0)
            for value in error_dates
        ):
            raise TelegramError("Telegram returned invalid webhook information", ambiguous=True)
        return {
            "configured": bool(url),
            "has_custom_certificate": custom_certificate,
            "pending_update_count": pending,
            "last_error_present": any(value is not None for value in error_dates),
        }

    def set_my_commands(
        self,
        commands: list[Mapping[str, str]],
        *,
        scope: Mapping[str, str],
    ) -> bool:
        return self._require_true(
            "setMyCommands",
            {
                "commands": _validated_commands(commands),
                "scope": _validated_command_scope(scope),
            },
        )

    def get_my_commands(
        self, *, scope: Mapping[str, str]
    ) -> list[dict[str, str]]:
        result = self.call(
            "getMyCommands", {"scope": _validated_command_scope(scope)}
        )
        if not isinstance(result, list):
            raise TelegramError("Telegram returned invalid bot commands", ambiguous=True)
        try:
            return _validated_commands(result)
        except ValueError:
            raise TelegramError("Telegram returned invalid bot commands", ambiguous=True) from None

    def delete_my_commands(self, *, scope: Mapping[str, str]) -> bool:
        return self._require_true(
            "deleteMyCommands", {"scope": _validated_command_scope(scope)}
        )

    def set_my_name(self, name: str) -> bool:
        return self._require_true(
            "setMyName", {"name": _bounded_text(name, 64, "bot name")}
        )

    def get_my_name(self) -> str:
        return self._get_public_profile_text("getMyName", "name", 64)

    def set_my_description(self, description: str) -> bool:
        return self._require_true(
            "setMyDescription",
            {"description": _bounded_text(description, 512, "bot description")},
        )

    def get_my_description(self) -> str:
        return self._get_public_profile_text("getMyDescription", "description", 512)

    def set_my_short_description(self, short_description: str) -> bool:
        return self._require_true(
            "setMyShortDescription",
            {
                "short_description": _bounded_text(
                    short_description, 120, "bot short description"
                )
            },
        )

    def get_my_short_description(self) -> str:
        return self._get_public_profile_text(
            "getMyShortDescription", "short_description", 120
        )

    def _get_public_profile_text(self, method: str, field: str, limit: int) -> str:
        result = self.call(method)
        value = result.get(field) if isinstance(result, Mapping) else None
        if not isinstance(value, str) or len(value) > limit or "\x00" in value:
            raise TelegramError("Telegram returned invalid bot profile text", ambiguous=True)
        return value

    def set_chat_menu_commands(self) -> bool:
        return self._require_true(
            "setChatMenuButton", {"menu_button": {"type": "commands"}}
        )

    def get_chat_menu_button_type(self) -> str:
        result = self.call("getChatMenuButton")
        menu_type = result.get("type") if isinstance(result, Mapping) else None
        if menu_type not in {"default", "commands", "web_app"}:
            raise TelegramError("Telegram returned an invalid chat menu", ambiguous=True)
        return str(menu_type)

    def get_updates(self, *, offset: int, timeout: int) -> list[Mapping[str, Any]]:
        result = self.call(
            "getUpdates",
            {
                "offset": offset,
                "limit": 100,
                "timeout": timeout,
                "allowed_updates": [
                    "message",
                    "callback_query",
                    "pre_checkout_query",
                    "subscription",
                    "my_chat_member",
                ],
            },
            timeout=max(15.0, float(timeout) + 10.0),
        )
        if not isinstance(result, list) or not all(
            isinstance(item, Mapping)
            and (
                update_id := _safe_int(item.get("update_id"))
            ) is not None
            and 0 <= update_id <= (1 << 31) - 1
            for item in result
        ):
            raise TelegramError("Telegram returned an invalid updates list", ambiguous=True)
        return result

    def get_ops_updates(
        self, *, offset: int, timeout: int = 0, limit: int = 20
    ) -> list[Mapping[str, Any]]:
        """Fetch one bounded message-only Ops batch; never send or advance state.

        Offset is a signed 32-bit Bot API integer. The store's exhausted
        max(update_id) + 1 sentinel cannot be sent; idle recovery belongs to the
        runtime. Older queued update kinds may still arrive despite
        allowed_updates; return them for disposition.
        """

        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 <= offset <= MAX_OPS_POLL_OFFSET
            or isinstance(timeout, bool)
            or not isinstance(timeout, int)
            or not 0 <= timeout <= 30
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 20
        ):
            raise ValueError("Ops update page bounds are invalid")
        try:
            result = self.call(
                "getUpdates",
                {
                    "offset": offset,
                    "limit": limit,
                    "timeout": timeout,
                    "allowed_updates": ["message"],
                },
                timeout=max(15.0, float(timeout) + 10.0),
            )
        except TelegramError as exc:
            raise TelegramError(
                "Telegram Ops polling failed",
                error_code=exc.error_code,
                retry_after=exc.retry_after,
                ambiguous=exc.ambiguous,
            ) from None
        if not isinstance(result, list) or len(result) > limit:
            raise TelegramError("Telegram returned an invalid Ops updates list", ambiguous=True)
        seen: set[int] = set()
        for item in result:
            update_id = _safe_int(item.get("update_id")) if isinstance(item, Mapping) else None
            if (
                update_id is None
                or not 0 <= update_id <= (1 << 31) - 1
                or update_id in seen
                or ("message" in item and not isinstance(item["message"], Mapping))
            ):
                # Reject the whole batch, rather than losing malformed entries
                # when the caller acknowledges an offset after valid entries.
                raise TelegramError(
                    "Telegram returned an invalid Ops updates list", ambiguous=True
                )
            seen.add(update_id)
        return result

    def get_bot_id(self) -> int:
        # Reconciliation only needs the immutable numeric identity. Keep this
        # narrow method compatible with minimal Bot API fixtures; bootstrap
        # uses get_me() when public username and capability checks are needed.
        result = self.call("getMe")
        if not isinstance(result, Mapping) or result.get("is_bot") is not True:
            raise TelegramError("Telegram returned an invalid bot identity", ambiguous=True)
        bot_id = _safe_int(result.get("id"))
        if bot_id is None or bot_id <= 0:
            raise TelegramError("Telegram returned an invalid bot identity", ambiguous=True)
        return bot_id

    def get_star_transactions(
        self, offset: int = 0, limit: int = 100
    ) -> list[Mapping[str, Any]]:
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 <= offset <= (1 << 52)
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("Star transaction page bounds are invalid")
        result = self.call(
            "getStarTransactions", {"offset": offset, "limit": limit}
        )
        transactions = result.get("transactions") if isinstance(result, Mapping) else None
        if (
            not isinstance(transactions, list)
            or len(transactions) > limit
            or not all(isinstance(item, Mapping) for item in transactions)
        ):
            raise TelegramError(
                "Telegram returned an invalid Star transaction list", ambiguous=True
            )
        return transactions


def validate_ops_origin(base_url: str) -> str:
    """Validate the live Ops origin before loading any credential.

    Research may still use HTTPS self-hosted providers and HTTP loopback fixtures
    through the default (non-Ops) origin policy.
    """

    origin = _provider_origin(base_url)
    if origin != PRODUCTION_TELEGRAM_ORIGIN:
        raise TelegramError("Ops requires the approved Telegram production origin")
    return origin


def _provider_origin(base_url: str) -> str:
    if (
        not isinstance(base_url, str)
        or any(ord(character) <= 32 or ord(character) == 127 for character in base_url)
        or "\\" in base_url
    ):
        raise TelegramError("Telegram API base URL is invalid")
    try:
        parsed = urllib.parse.urlsplit(base_url)
        _ = parsed.port
    except ValueError:
        raise TelegramError("Telegram API base URL is invalid") from None
    try:
        loopback = parsed.hostname == "localhost" or ipaddress.ip_address(
            parsed.hostname or ""
        ).is_loopback
    except ValueError:
        loopback = parsed.hostname == "localhost"
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (parsed.scheme == "http" and not loopback)
    ):
        raise TelegramError("Telegram API base URL is invalid")
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), "", "", "")
    )


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Telegram response field")
        result[key] = value
    return result


def _invalid_json_constant(_value: str) -> Any:
    raise ValueError("invalid Telegram response number")


def _read_response(response: Any) -> Any:
    raw = response.read(_MAX_RESPONSE_BYTES + 1)
    if not isinstance(raw, bytes) or len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("Telegram response exceeds the size limit or is invalid")
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_json_object,
        parse_constant=_invalid_json_constant,
    )


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if not -(1 << 52) <= value <= (1 << 52):
        return None
    return value


def normalize_channel_ref(value: Any) -> tuple[int | str, str]:
    """Canonicalize a channel-shaped target without permitting private IDs."""

    if isinstance(value, bool):
        raise ValueError("channel_ref is invalid")
    if isinstance(value, int):
        if not -_MAX_TELEGRAM_ID <= value < 0:
            raise ValueError("numeric channel_ref must be a negative Telegram chat ID")
        return value, str(value)
    if isinstance(value, str) and _CHANNEL_USERNAME.fullmatch(value):
        normalized = value.lower()
        return normalized, normalized
    raise ValueError("channel_ref must be a negative chat ID or @channel username")


def _safe_retry_after(value: Any) -> int | None:
    parsed = _safe_int(value)
    if parsed is None or parsed <= 0:
        return None
    return min(parsed, 3_600)


def _safe_description(value: Any, *, fallback: str, secret: str = "") -> str:
    text = value if isinstance(value, str) and value else fallback
    # JSON permits escaped lone surrogates while Telegram requires UTF-8.
    # Replacing them keeps error reporting itself from becoming a crash path.
    text = text.encode("utf-8", errors="replace").decode("utf-8")
    text = text.replace("\n", " ").replace("\r", " ")
    if secret:
        for variant in (secret, urllib.parse.quote(secret, safe="")):
            text = re.sub(re.escape(variant), "<redacted>", text, flags=re.IGNORECASE)
    return text[:300]


def _bounded_text(value: Any, limit: int, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit or "\x00" in value:
        raise ValueError(f"{label} is invalid")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError(f"{label} is invalid") from None
    return value


def _validated_commands(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError("Telegram bot commands are invalid")
    commands: list[dict[str, str]] = []
    for item in value:
        command = item.get("command") if isinstance(item, Mapping) else None
        description = item.get("description") if isinstance(item, Mapping) else None
        if (
            not isinstance(command, str)
            or not re.fullmatch(r"[a-z0-9_]{1,32}", command)
            or not isinstance(description, str)
            or not 1 <= len(description) <= 256
            or "\x00" in description
            or set(item) != {"command", "description"}
        ):
            raise ValueError("Telegram bot commands are invalid")
        commands.append({"command": command, "description": description})
    return commands


def _validated_command_scope(value: Any) -> dict[str, str]:
    scope_type = value.get("type") if isinstance(value, Mapping) else None
    if scope_type not in {
        "default",
        "all_private_chats",
        "all_group_chats",
        "all_chat_administrators",
    } or set(value) != {"type"}:
        raise ValueError("Telegram command scope is invalid")
    return {"type": str(scope_type)}
