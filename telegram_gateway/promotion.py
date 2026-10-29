"""Bounded Telegram campaign identifiers and deep-link construction.

Campaign codes are public routing labels, never identity claims or secrets.
Only pre-registered codes are persisted by the gateway, which prevents an
attacker from using arbitrary ``/start`` payloads as unbounded local storage.
"""

from __future__ import annotations

import re
import secrets


MAX_CAMPAIGN_CODE_LENGTH = 64
DEFAULT_PROMOTION_NOTICE_VERSION = "alerts-2026-09-03-v1"
CAMPAIGN_KINDS = frozenset(
    {"direct", "organic", "partner", "telegram_channel", "test"}
)

_CAMPAIGN_CODE = re.compile(r"k1_[A-Za-z0-9_-]{22}\Z")
_BOT_USERNAME = re.compile(r"[A-Za-z0-9_]{2,29}[Bb][Oo][Tt]\Z")
_NOTICE_VERSION = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")


def validate_campaign_code(value: object) -> str:
    """Return a KINGDOM opaque token without normalizing its identity."""

    if not isinstance(value, str) or not _CAMPAIGN_CODE.fullmatch(value):
        raise ValueError(
            "campaign code must be k1_ followed by 22 base64url characters"
        )
    return value


def generate_campaign_code() -> str:
    """Generate 128 random bits encoded as a Telegram-safe public label."""

    value = "k1_" + secrets.token_urlsafe(16)
    return validate_campaign_code(value)


def validate_campaign_kind(value: object) -> str:
    if not isinstance(value, str) or value not in CAMPAIGN_KINDS:
        raise ValueError(
            "campaign kind must be one of: " + ", ".join(sorted(CAMPAIGN_KINDS))
        )
    return value


def validate_notice_version(value: object) -> str:
    """Validate a non-secret identifier for the exact alert consent copy."""

    if not isinstance(value, str) or not _NOTICE_VERSION.fullmatch(value):
        raise ValueError(
            "promotion notice version must be 1-64 lowercase code characters"
        )
    return value


def build_campaign_link(bot_username: object, campaign_code: object) -> str:
    """Build a standard private-chat bot deep link without contacting Telegram."""

    code = validate_campaign_code(campaign_code)
    if not isinstance(bot_username, str) or not _BOT_USERNAME.fullmatch(bot_username):
        raise ValueError(
            "bot username must be 5-32 ASCII username characters and end in bot"
        )
    return f"https://t.me/{bot_username}?start={code}"


def validate_campaign_link(value: object) -> str:
    """Validate one canonical KINGDOM Telegram campaign deep link.

    The deliberately strict round trip rejects alternate Telegram hosts, URL
    encoding, ports, fragments, extra query parameters, and non-KINGDOM start
    payloads.  Campaign links are public routing labels, not credentials.
    """

    if not isinstance(value, str):
        raise ValueError(
            "campaign link must be https://t.me/<bot username>?start=<campaign code>"
        )
    match = re.fullmatch(
        r"https://t\.me/([A-Za-z0-9_]{2,29}[Bb][Oo][Tt])"
        r"\?start=(k1_[A-Za-z0-9_-]{22})",
        value,
    )
    if match is None:
        raise ValueError(
            "campaign link must be https://t.me/<bot username>?start=<campaign code>"
        )
    username, code = match.groups()
    validate_campaign_code(code)
    if build_campaign_link(username, code) != value:
        raise ValueError("campaign link is not canonical")
    return value
