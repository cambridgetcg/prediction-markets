"""Authenticated, transport-neutral Telegram webhook ingress.

The adapter is deliberately synchronous: one authenticated JSON update is
handed directly to :class:`~telegram_gateway.service.BotService` before the
response is returned.  It does not open a socket, terminate TLS, trust proxy
headers, or make a local listener internet-safe.  A deployment must put it
behind a reviewed HTTPS listener and preserve the request method, target,
headers, and exact body bytes supplied here.

Telegram retries webhook deliveries when it does not receive a successful
HTTP response.  Authenticated requests that are permanently unusable are
therefore acknowledged with 204 after being rejected locally.  Authentication
and routing failures remain ordinary HTTP errors, while unexpected internal
failures return 503 so an update is never silently acknowledged as processed.
"""

from __future__ import annotations

import hmac
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, TypeAlias

from .service import BotService
from .telegram_api import TelegramError


TELEGRAM_SECRET_HEADER = "x-telegram-bot-api-secret-token"
DEFAULT_WEBHOOK_PATH = "/telegram/webhook"
DEFAULT_MAX_BODY_BYTES = 256 * 1024
MAX_CONFIGURED_BODY_BYTES = 1024 * 1024
MAX_TELEGRAM_UPDATE_ID = (1 << 31) - 1

HeaderItems: TypeAlias = Mapping[str, str] | Iterable[tuple[str, str]]

_SECRET_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")
_CONTENT_LENGTH = re.compile(r"(?:0|[1-9][0-9]*)\Z")


@dataclass(frozen=True)
class WebhookResponse:
    """A small HTTP response value for the owning listener to translate."""

    status: int
    outcome: str
    headers: tuple[tuple[str, str], ...]
    body: bytes = b""


class _DuplicateJSONObjectKey(ValueError):
    pass


class TelegramWebhookIngress:
    """Validate and synchronously dispatch one Telegram webhook request.

    ``dispatch`` expects the exact request body, rather than a decoded string.
    The caller must itself cap reads to ``max_body_bytes``; this adapter also
    checks both the declared and actual size before JSON decoding.
    """

    __slots__ = ("service", "path", "max_body_bytes", "_secret_token")

    def __init__(
        self,
        service: BotService,
        *,
        secret_token: str,
        path: str = DEFAULT_WEBHOOK_PATH,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        if not isinstance(secret_token, str) or not _SECRET_TOKEN.fullmatch(secret_token):
            raise ValueError(
                "secret_token must contain 1-256 ASCII letters, digits, underscores, or hyphens"
            )
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or "?" in path
            or "#" in path
            or "\x00" in path
            or len(path.encode("utf-8")) > 512
        ):
            raise ValueError("path must be an absolute, query-free path of at most 512 bytes")
        if (
            isinstance(max_body_bytes, bool)
            or not isinstance(max_body_bytes, int)
            or not 1 <= max_body_bytes <= MAX_CONFIGURED_BODY_BYTES
        ):
            raise ValueError(
                f"max_body_bytes must be between 1 and {MAX_CONFIGURED_BODY_BYTES}"
            )
        self.service = service
        self.path = path
        self.max_body_bytes = max_body_bytes
        self._secret_token = secret_token.encode("ascii")

    def __repr__(self) -> str:
        return (
            f"TelegramWebhookIngress(service={self.service!r}, "
            f"secret_token=<redacted>, path={self.path!r}, "
            f"max_body_bytes={self.max_body_bytes!r})"
        )

    def dispatch(
        self,
        *,
        method: str,
        path: str,
        headers: HeaderItems,
        body: bytes,
    ) -> WebhookResponse:
        """Validate a request and route at most one update to ``BotService``.

        Outcomes are intentionally more specific than public HTTP bodies so a
        local listener can record bounded operational metrics without logging
        request content or the secret token.
        """

        if method != "POST":
            return _text_response(
                405,
                "method_not_allowed",
                b"method not allowed\n",
                extra_headers=(("Allow", "POST"),),
            )
        if path != self.path:
            return _text_response(404, "not_found", b"not found\n")

        try:
            normalized_headers = _normalize_headers(headers)
        except (TypeError, ValueError, UnicodeError):
            return _temporary_failure("invalid_header_representation")

        supplied_secrets = normalized_headers.get(TELEGRAM_SECRET_HEADER, ())
        candidate = supplied_secrets[0] if len(supplied_secrets) == 1 else ""
        if not self._secret_matches(candidate):
            return _text_response(401, "unauthorized", b"unauthorized\n")

        # From this point onward the sender knew the configured secret.  Any
        # framing or JSON rejection is permanent for these exact bytes, so a
        # 204 prevents an unproductive Telegram retry loop.
        if not isinstance(body, bytes):
            return _temporary_failure("invalid_body_representation")
        if normalized_headers.get("transfer-encoding"):
            return _acknowledged_rejection("rejected_transfer_encoding")

        content_lengths = normalized_headers.get("content-length", ())
        if len(content_lengths) != 1 or not _CONTENT_LENGTH.fullmatch(
            content_lengths[0]
        ):
            return _acknowledged_rejection("rejected_content_length")
        declared_size = int(content_lengths[0])
        if declared_size > self.max_body_bytes or len(body) > self.max_body_bytes:
            return _acknowledged_rejection("rejected_body_size")
        if declared_size != len(body):
            return _acknowledged_rejection("rejected_content_length")

        content_types = normalized_headers.get("content-type", ())
        if len(content_types) != 1 or not _is_json_content_type(content_types[0]):
            return _acknowledged_rejection("rejected_content_type")

        try:
            update = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_json_constant,
            )
        except (
            _DuplicateJSONObjectKey,
            RecursionError,
            UnicodeError,
            ValueError,
        ):
            return _acknowledged_rejection("rejected_json")
        if not isinstance(update, dict):
            return _acknowledged_rejection("rejected_json_object")

        update_id = _telegram_update_id(update.get("update_id"))
        try:
            handled = self.service.handle_update(update)
        except TelegramError as exc:
            return self._quarantine_known_failure(
                update_id,
                error_code=str(exc.error_code or "telegram_transport"),
                ambiguous=exc.ambiguous,
                outcome="quarantined_telegram_error",
            )
        except (OverflowError, TypeError, ValueError):
            return self._quarantine_known_failure(
                update_id,
                error_code="invalid_update",
                ambiguous=False,
                outcome="quarantined_invalid_update",
            )
        except Exception:
            # Do not expose exception text: it may contain request data or a
            # downstream URL containing a bot credential.
            return _temporary_failure("internal_error")

        return _empty_response(204, "processed" if handled else "ignored")

    def _secret_matches(self, candidate: str) -> bool:
        try:
            candidate_bytes = candidate.encode("ascii")
        except (AttributeError, UnicodeError):
            candidate_bytes = b""
        # Always use the constant-time comparison primitive, including for a
        # missing, duplicated, oversized, or non-ASCII supplied value.
        if len(candidate_bytes) > 256:
            candidate_bytes = b""
        return hmac.compare_digest(candidate_bytes, self._secret_token)

    def _quarantine_known_failure(
        self,
        update_id: int | None,
        *,
        error_code: str,
        ambiguous: bool,
        outcome: str,
    ) -> WebhookResponse:
        if update_id is not None:
            try:
                self.service.store.mark_update_failed(
                    update_id,
                    error_code=error_code,
                    ambiguous=ambiguous,
                )
            except Exception:
                return _temporary_failure("failure_quarantine_error")
        return _empty_response(204, outcome)


def _normalize_headers(headers: HeaderItems) -> dict[str, tuple[str, ...]]:
    source = headers.items() if isinstance(headers, Mapping) else headers
    collected: dict[str, list[str]] = {}
    count = 0
    for item in source:
        count += 1
        if count > 64:
            raise ValueError("too many headers")
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("headers must contain name/value pairs")
        name, value = item
        if not isinstance(name, str) or not isinstance(value, str):
            raise TypeError("header names and values must be strings")
        lowered = name.casefold()
        if not lowered or any(ord(character) > 127 for character in lowered):
            raise ValueError("header name must be ASCII")
        if len(name) > 256 or len(value) > 1_024:
            raise ValueError("header is too large")
        collected.setdefault(lowered, []).append(value)
    return {name: tuple(values) for name, values in collected.items()}


def _is_json_content_type(value: str) -> bool:
    parts = [part.strip().casefold() for part in value.split(";")]
    if not parts or parts[0] != "application/json":
        return False
    if len(parts) == 1:
        return True
    return len(parts) == 2 and parts[1] == "charset=utf-8"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONObjectKey("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON number is not permitted: {value}")


def _telegram_update_id(value: Any) -> int | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MAX_TELEGRAM_UPDATE_ID
    ):
        return None
    return value


def _empty_response(status: int, outcome: str) -> WebhookResponse:
    return WebhookResponse(
        status=status,
        outcome=outcome,
        headers=(("Content-Length", "0"), ("Cache-Control", "no-store")),
    )


def _acknowledged_rejection(outcome: str) -> WebhookResponse:
    return _empty_response(204, outcome)


def _temporary_failure(outcome: str) -> WebhookResponse:
    return _text_response(
        503,
        outcome,
        b"temporarily unavailable\n",
        extra_headers=(("Retry-After", "1"),),
    )


def _text_response(
    status: int,
    outcome: str,
    body: bytes,
    *,
    extra_headers: tuple[tuple[str, str], ...] = (),
) -> WebhookResponse:
    return WebhookResponse(
        status=status,
        outcome=outcome,
        headers=(
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            *extra_headers,
        ),
        body=body,
    )
