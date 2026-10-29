"""Canonical, append-only research cards for Telegram channels.

The private bot renderers intentionally defang untrusted links.  Channel posts
need a different contract: a small number of explicitly validated evidence
links, a stable revision identity, and visible correction lineage.  This
module creates that contract without granting trade authority or contacting
Telegram.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
import re
import unicodedata
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .envelope import validate_envelope
from .lifecycle import validate_lifecycle_event


CARD_SCHEMA = "kingdom.telegram-channel-card/0.1"
EDITORIAL_EVENT_SCHEMA = "kingdom.telegram-channel-editorial/0.1"
CARD_AUTHORITY_MODE = "information_only"
CARD_STATUSES = frozenset(
    {"ACTIVE", "AMENDED", "WITHDRAWN", "RESOLVED", "EXPIRED"}
)
UPDATE_STATUSES = CARD_STATUSES - {"ACTIVE"}
MAX_CHANNEL_TEXT = 4_096
TARGET_CHANNEL_TEXT = 3_900
MAX_SOURCE_LINKS = 8
MAX_RENDERED_SOURCE_LINKS = 4

_CARD_KEYS = frozenset(
    {
        "schema",
        "card_id",
        "series_id",
        "signal_id",
        "revision",
        "kind",
        "status",
        "published_at",
        "valid_until",
        "lineage",
        "market",
        "research",
        "editorial",
        "evidence",
        "authority",
        "integrity",
    }
)
_SOURCE_KEYS = frozenset(
    {"observation_ref", "label", "url", "observed_at", "is_primary"}
)
_EDITORIAL_EVENT_KEYS = frozenset(
    {
        "schema",
        "event_id",
        "signal_id",
        "revision",
        "previous_card_id",
        "previous_status",
        "status",
        "occurred_at",
        "actor_kind",
        "reason_code",
        "summary",
        "scope",
        "execution_allowed",
    }
)
_MARKET_KEYS = frozenset(
    {
        "venue",
        "market_id",
        "question",
        "domain",
        "direction",
        "quoted_probability",
        "market_url",
        "resolution_rules_ref",
        "resolution_rules_url",
        "resolution_rules_verified",
    }
)
_RESEARCH_KEYS = frozenset(
    {"signal_type", "confidence", "horizon_hours", "reasoning"}
)
_EVIDENCE_KEYS = frozenset(
    {
        "envelope_status",
        "link_validation",
        "sources",
        "unlinked_observation_refs",
        "limitations",
    }
)
_AUTHORITY_KEYS = frozenset(
    {
        "mode",
        "execution_allowed",
        "paper_only",
        "wallet_access",
        "jurisdiction_verified",
    }
)
_INTEGRITY_KEYS = frozenset(
    {"source_envelope_digest", "content_digest", "proves_authorship", "proves_truth"}
)
_MACHINE_LABEL = re.compile(r"[a-z0-9_.-]{1,64}\Z")
_EVENT_ID = re.compile(r"kingdom-edit-[0-9a-f]{32}\Z")
_CARD_ID = re.compile(r"kingdom-card-[0-9a-f]{32}\Z")
_SERIES_ID = re.compile(r"kingdom-series-[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CHANNEL_FOOTER = (
    "Information only. No return is promised. No trade was placed.\n"
    "Paper/research mode only; live execution and wallet access are disabled."
)


class ChannelCardError(ValueError):
    """A channel card or editorial event violates the public contract."""


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    keys = frozenset(value)
    if keys == expected:
        return
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    if missing:
        raise ChannelCardError(f"{label} is missing keys: {', '.join(missing)}")
    raise ChannelCardError(f"{label} contains unsupported keys: {', '.join(extra)}")


def _text(
    value: Any,
    label: str,
    *,
    maximum: int,
    one_line: bool = True,
    machine_label: bool = False,
) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ChannelCardError(f"{label} must be a non-empty canonical string")
    if unicodedata.normalize("NFC", value) != value:
        raise ChannelCardError(f"{label} must use NFC Unicode normalization")
    if any(
        unicodedata.category(character).startswith("C")
        and not (not one_line and character == "\n")
        for character in value
    ):
        raise ChannelCardError(f"{label} contains a control character")
    if one_line and any(character in value for character in "\r\n\t"):
        raise ChannelCardError(f"{label} must be one line")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ChannelCardError(f"{label} must be valid UTF-8") from exc
    if len(encoded) > maximum:
        raise ChannelCardError(f"{label} exceeds its UTF-8 byte limit")
    if machine_label and _MACHINE_LABEL.fullmatch(value) is None:
        raise ChannelCardError(f"{label} must be a bounded machine label")
    return value


def _timestamp(value: Any, label: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ChannelCardError(f"{label} is not a valid timestamp") from exc
    else:
        raise ChannelCardError(f"{label} must be an ISO-8601 timestamp")
    if parsed.tzinfo is None:
        raise ChannelCardError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _https_url(value: Any, label: str, *, polymarket_only: bool = False) -> str:
    url = _text(value, label, maximum=512)
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ChannelCardError(f"{label} is not a valid URL") from exc
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
    ):
        raise ChannelCardError(
            f"{label} must be an absolute HTTPS URL without credentials or fragments"
        )
    if polymarket_only and not (
        hostname == "polymarket.com" or hostname.endswith(".polymarket.com")
    ):
        raise ChannelCardError(f"{label} must point to an official Polymarket host")
    return url


def _probability(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ChannelCardError(f"{label} must be a probability")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ChannelCardError(f"{label} must be between zero and one")
    return result


def _source_links(
    links: Sequence[Mapping[str, Any]],
    *,
    published_at: str,
    allowed_refs: set[str] | None,
    require_one: bool,
) -> list[dict[str, Any]]:
    if isinstance(links, (str, bytes)) or not isinstance(links, Sequence):
        raise ChannelCardError("source_links must be a sequence")
    if len(links) > MAX_SOURCE_LINKS:
        raise ChannelCardError(f"source_links cannot exceed {MAX_SOURCE_LINKS} items")
    if require_one and not links:
        raise ChannelCardError("an active research card requires an evidence link")

    published = _timestamp(published_at, "published_at")
    seen_refs: set[str] = set()
    seen_urls: set[str] = set()
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(links):
        if not isinstance(raw, Mapping):
            raise ChannelCardError(f"source_links[{index}] must be an object")
        _exact_keys(raw, _SOURCE_KEYS, f"source_links[{index}]")
        observation_ref = _text(
            raw["observation_ref"],
            f"source_links[{index}].observation_ref",
            maximum=160,
        )
        if allowed_refs is not None and observation_ref not in allowed_refs:
            raise ChannelCardError(
                "a linked observation is not present in the sealed signal envelope"
            )
        label = _text(
            raw["label"], f"source_links[{index}].label", maximum=120
        )
        url = _https_url(raw["url"], f"source_links[{index}].url")
        observed_at = _timestamp(
            raw["observed_at"], f"source_links[{index}].observed_at"
        )
        if observed_at > published:
            raise ChannelCardError("an evidence observation cannot postdate the card")
        if not isinstance(raw["is_primary"], bool):
            raise ChannelCardError("source is_primary must be a boolean")
        if observation_ref in seen_refs or url in seen_urls:
            raise ChannelCardError("source links must have unique references and URLs")
        seen_refs.add(observation_ref)
        seen_urls.add(url)
        result.append(
            {
                "observation_ref": observation_ref,
                "label": label,
                "url": url,
                "observed_at": observed_at,
                "is_primary": raw["is_primary"],
            }
        )
    return sorted(
        result,
        key=lambda source: (
            not source["is_primary"],
            source["observed_at"],
            source["observation_ref"],
        ),
    )


def _series_id(signal_id: str) -> str:
    material = signal_id.encode("utf-8", errors="strict")
    return "kingdom-series-" + hashlib.sha256(material).hexdigest()[:32]


def _card_id(series_id: str, revision: int, editorial_event_id: str) -> str:
    material = f"{series_id}\0{revision}\0{editorial_event_id}".encode("utf-8")
    return "kingdom-card-" + hashlib.sha256(material).hexdigest()[:32]


def _without_content_digest(card: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(card))
    integrity = result.get("integrity")
    if isinstance(integrity, dict):
        integrity.pop("content_digest", None)
    return result


def canonical_card_json(card: Mapping[str, Any]) -> str:
    """Return canonical JSON used for the local tamper-evident digest."""

    return json.dumps(
        _without_content_digest(card),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def channel_card_digest(card: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_card_json(card).encode("utf-8")).hexdigest()


def _seal_card(card: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(card))
    source_digest = result.get("integrity", {}).get("source_envelope_digest")
    result["integrity"] = {
        "source_envelope_digest": source_digest,
        "content_digest": channel_card_digest(result),
        "proves_authorship": False,
        "proves_truth": False,
    }
    validate_channel_card(result)
    return result


def build_research_card(
    envelope: Mapping[str, Any],
    approval_event: Mapping[str, Any],
    *,
    source_links: Sequence[Mapping[str, Any]],
    market_url: str,
    published_at: str | datetime,
) -> dict[str, Any]:
    """Build revision one from a sealed signal and its approval evidence.

    URL syntax and lineage are validated, but the function does not authenticate
    a source, an editor, or the truth of the forecast.
    """

    try:
        validate_envelope(envelope)
        approval = validate_lifecycle_event(approval_event)
    except ValueError as exc:
        raise ChannelCardError(str(exc)) from exc
    if approval["status"] != "APPROVED":
        raise ChannelCardError("an active channel card requires an APPROVED event")
    signal_id = _text(envelope["signal_id"], "signal_id", maximum=128)
    if approval["signal_id"] != signal_id:
        raise ChannelCardError("approval event and envelope signal IDs differ")
    if envelope["authority"].get("execution_allowed") is not False:
        raise ChannelCardError("channel research cannot grant execution authority")

    published = _timestamp(published_at, "published_at")
    issued_at = _timestamp(envelope["issued_at"], "envelope.issued_at")
    expires_at = _timestamp(envelope["expires_at"], "envelope.expires_at")
    if published < issued_at or published < approval["occurred_at"]:
        raise ChannelCardError("publication cannot predate the signal or its approval")
    if published >= expires_at:
        raise ChannelCardError("an expired signal cannot become an active channel card")

    references = {
        _text(reference, "source observation ref", maximum=160)
        for reference in envelope["provenance"]["source_observation_refs"]
    }
    if not references:
        raise ChannelCardError(
            "an active channel card requires sealed source observation references"
        )
    sources = _source_links(
        source_links,
        published_at=published,
        allowed_refs=references,
        require_one=True,
    )
    linked_refs = {source["observation_ref"] for source in sources}

    market = envelope["market"]
    forecast = envelope["forecast"]
    rules_ref = market.get("resolution_rules_ref")
    if not isinstance(rules_ref, str) or not rules_ref.strip():
        raise ChannelCardError("a channel card requires a resolution-rules reference")
    rules_ref = _text(rules_ref, "resolution_rules_ref", maximum=512)
    rules_url = None
    if rules_ref.lower().startswith("https://"):
        rules_url = _https_url(
            rules_ref, "resolution_rules_ref", polymarket_only=True
        )

    series_id = _series_id(signal_id)
    card_id = _card_id(series_id, 1, approval["event_id"])
    result: dict[str, Any] = {
        "schema": CARD_SCHEMA,
        "card_id": card_id,
        "series_id": series_id,
        "signal_id": signal_id,
        "revision": 1,
        "kind": "RESEARCH",
        "status": "ACTIVE",
        "published_at": published,
        "valid_until": expires_at,
        "lineage": {
            "root_card_id": card_id,
            "supersedes_card_id": None,
        },
        "market": {
            "venue": "polymarket",
            "market_id": _text(market["market_id"], "market_id", maximum=256),
            "question": _text(market["question"], "market question", maximum=700),
            "domain": _text(
                str(market.get("domain") or "OTHER"), "market domain", maximum=32
            ),
            "direction": market["direction"],
            "quoted_probability": _probability(
                market["quoted_outcome_token_price"], "quoted probability"
            ),
            "market_url": _https_url(
                market_url, "market_url", polymarket_only=True
            ),
            "resolution_rules_ref": rules_ref,
            "resolution_rules_url": rules_url,
            "resolution_rules_verified": False,
        },
        "research": {
            "signal_type": _text(
                str(forecast.get("signal_type") or "UNKNOWN"),
                "signal type",
                maximum=80,
            ),
            "confidence": _probability(forecast["confidence"], "confidence"),
            "horizon_hours": forecast["horizon_hours"],
            "reasoning": _text(
                str(forecast.get("reasoning") or "No reasoning supplied."),
                "reasoning",
                maximum=1_600,
                one_line=False,
            ),
        },
        "editorial": copy.deepcopy(approval),
        "evidence": {
            "envelope_status": envelope["provenance"]["status"],
            "link_validation": "https_syntax_only_not_authenticated",
            "sources": sources,
            "unlinked_observation_refs": sorted(references - linked_refs),
            "limitations": [
                _text(
                    str(limit),
                    "evidence limitation",
                    maximum=400,
                    one_line=False,
                )
                for limit in envelope["provenance"].get("limitations", [])[:4]
            ],
        },
        "authority": {
            "mode": CARD_AUTHORITY_MODE,
            "execution_allowed": False,
            "paper_only": True,
            "wallet_access": False,
            "jurisdiction_verified": False,
        },
        "integrity": {
            "source_envelope_digest": envelope["integrity"]["content_digest"],
            "content_digest": "",
            "proves_authorship": False,
            "proves_truth": False,
        },
    }
    return _seal_card(result)


def build_editorial_event(
    previous_card: Mapping[str, Any],
    *,
    status: str,
    occurred_at: str | datetime,
    actor_kind: str,
    reason_code: str,
    summary: str,
) -> dict[str, Any]:
    """Create a content-bound editorial event for one append-only successor."""

    validate_channel_card(previous_card)
    if status not in UPDATE_STATUSES:
        raise ChannelCardError("an editorial successor must change the active status")
    if previous_card["status"] in {"WITHDRAWN", "RESOLVED", "EXPIRED"}:
        raise ChannelCardError("a terminal channel card cannot receive a successor")
    material: dict[str, Any] = {
        "schema": EDITORIAL_EVENT_SCHEMA,
        "signal_id": previous_card["signal_id"],
        "revision": previous_card["revision"] + 1,
        "previous_card_id": previous_card["card_id"],
        "previous_status": previous_card["status"],
        "status": status,
        "occurred_at": _timestamp(occurred_at, "occurred_at"),
        "actor_kind": _text(
            actor_kind, "actor_kind", maximum=64, machine_label=True
        ),
        "reason_code": _text(
            reason_code, "reason_code", maximum=64, machine_label=True
        ),
        "summary": _text(summary, "summary", maximum=800, one_line=False),
        "scope": "research_distribution_only",
        "execution_allowed": False,
    }
    canonical = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    material["event_id"] = "kingdom-edit-" + hashlib.sha256(canonical).hexdigest()[:32]
    return validate_editorial_event(material)


def validate_editorial_event(event: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise ChannelCardError("editorial event must be an object")
    _exact_keys(event, _EDITORIAL_EVENT_KEYS, "editorial event")
    if event["schema"] != EDITORIAL_EVENT_SCHEMA:
        raise ChannelCardError("unsupported editorial event schema")
    event_id = _text(event["event_id"], "event_id", maximum=45)
    if _EVENT_ID.fullmatch(event_id) is None:
        raise ChannelCardError("editorial event ID is invalid")
    _text(event["signal_id"], "signal_id", maximum=128)
    revision = event["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 2:
        raise ChannelCardError("editorial event revision must be at least two")
    _text(event["previous_card_id"], "previous_card_id", maximum=45)
    if _CARD_ID.fullmatch(event["previous_card_id"]) is None:
        raise ChannelCardError("previous_card_id is invalid")
    if event["previous_status"] not in CARD_STATUSES:
        raise ChannelCardError("previous editorial status is invalid")
    if event["status"] not in UPDATE_STATUSES:
        raise ChannelCardError("editorial status is invalid")
    if event["previous_status"] in {"WITHDRAWN", "RESOLVED", "EXPIRED"}:
        raise ChannelCardError("a terminal status cannot transition")
    _timestamp(event["occurred_at"], "occurred_at")
    _text(event["actor_kind"], "actor_kind", maximum=64, machine_label=True)
    _text(event["reason_code"], "reason_code", maximum=64, machine_label=True)
    _text(event["summary"], "summary", maximum=800, one_line=False)
    if event["scope"] != "research_distribution_only":
        raise ChannelCardError("editorial scope must remain research-only")
    if event["execution_allowed"] is not False:
        raise ChannelCardError("editorial events cannot grant trade authority")

    material = dict(event)
    del material["event_id"]
    canonical = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    expected = "kingdom-edit-" + hashlib.sha256(canonical).hexdigest()[:32]
    if not hmac.compare_digest(event_id, expected):
        raise ChannelCardError("editorial event ID does not match its content")
    return copy.deepcopy(dict(event))


def build_status_card(
    previous_card: Mapping[str, Any],
    editorial_event: Mapping[str, Any],
    *,
    source_links: Sequence[Mapping[str, Any]] = (),
    published_at: str | datetime | None = None,
) -> dict[str, Any]:
    """Append an amendment, withdrawal, expiry, or resolution card.

    The old research is deliberately not copied into the update, which avoids
    making revoked analysis look current when the correction is forwarded.
    """

    validate_channel_card(previous_card)
    event = validate_editorial_event(editorial_event)
    if event["signal_id"] != previous_card["signal_id"]:
        raise ChannelCardError("editorial event and prior card signal IDs differ")
    if event["revision"] != previous_card["revision"] + 1:
        raise ChannelCardError("editorial revision does not follow the prior card")
    if event["previous_card_id"] != previous_card["card_id"]:
        raise ChannelCardError("editorial event does not supersede the prior card")
    if event["previous_status"] != previous_card["status"]:
        raise ChannelCardError("editorial previous status does not match the prior card")

    published = _timestamp(
        published_at if published_at is not None else event["occurred_at"],
        "published_at",
    )
    if published < event["occurred_at"] or published < previous_card["published_at"]:
        raise ChannelCardError("a status card cannot predate its event or predecessor")
    sources = _source_links(
        source_links,
        published_at=published,
        allowed_refs=None,
        require_one=event["status"] == "RESOLVED",
    )
    card_id = _card_id(
        previous_card["series_id"], event["revision"], event["event_id"]
    )
    result: dict[str, Any] = {
        "schema": CARD_SCHEMA,
        "card_id": card_id,
        "series_id": previous_card["series_id"],
        "signal_id": previous_card["signal_id"],
        "revision": event["revision"],
        "kind": "STATUS_UPDATE",
        "status": event["status"],
        "published_at": published,
        "valid_until": previous_card["valid_until"],
        "lineage": {
            "root_card_id": previous_card["lineage"]["root_card_id"],
            "supersedes_card_id": previous_card["card_id"],
        },
        "market": copy.deepcopy(previous_card["market"]),
        "research": None,
        "editorial": copy.deepcopy(event),
        "evidence": {
            "envelope_status": None,
            "link_validation": (
                "https_syntax_only_not_authenticated" if sources else "no_external_links"
            ),
            "sources": sources,
            "unlinked_observation_refs": [],
            "limitations": [
                "Links are syntax-validated but source identity and claims are not authenticated by this module."
            ],
        },
        "authority": copy.deepcopy(previous_card["authority"]),
        "integrity": {
            "source_envelope_digest": previous_card["integrity"][
                "source_envelope_digest"
            ],
            "content_digest": "",
            "proves_authorship": False,
            "proves_truth": False,
        },
    }
    return _seal_card(result)


def validate_channel_card(card: Mapping[str, Any]) -> None:
    """Validate a complete card and its local tamper-evident digest."""

    if not isinstance(card, Mapping):
        raise ChannelCardError("channel card must be an object")
    _exact_keys(card, _CARD_KEYS, "channel card")
    if card["schema"] != CARD_SCHEMA:
        raise ChannelCardError("unsupported channel card schema")
    card_id = _text(card["card_id"], "card_id", maximum=45)
    series_id = _text(card["series_id"], "series_id", maximum=47)
    if _CARD_ID.fullmatch(card_id) is None or _SERIES_ID.fullmatch(series_id) is None:
        raise ChannelCardError("card or series ID is invalid")
    signal_id = _text(card["signal_id"], "signal_id", maximum=128)
    if series_id != _series_id(signal_id):
        raise ChannelCardError("series ID does not match the signal ID")
    revision = card["revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ChannelCardError("card revision must be a positive integer")
    if card["status"] not in CARD_STATUSES:
        raise ChannelCardError("channel card status is invalid")
    published = _timestamp(card["published_at"], "published_at")
    _timestamp(card["valid_until"], "valid_until")

    lineage = card["lineage"]
    if not isinstance(lineage, Mapping) or frozenset(lineage) != {
        "root_card_id",
        "supersedes_card_id",
    }:
        raise ChannelCardError("channel card lineage is invalid")
    root_card_id = _text(lineage["root_card_id"], "root_card_id", maximum=45)
    if _CARD_ID.fullmatch(root_card_id) is None:
        raise ChannelCardError("root_card_id is invalid")

    if revision == 1:
        if (
            card["kind"] != "RESEARCH"
            or card["status"] != "ACTIVE"
            or card["research"] is None
            or root_card_id != card_id
            or lineage["supersedes_card_id"] is not None
        ):
            raise ChannelCardError("revision one must be an active root research card")
        try:
            editorial = validate_lifecycle_event(card["editorial"])
        except ValueError as exc:
            raise ChannelCardError("root research card lacks valid approval evidence") from exc
        if (
            editorial["status"] != "APPROVED"
            or editorial["signal_id"] != signal_id
            or published < editorial["occurred_at"]
        ):
            raise ChannelCardError("root research approval and card differ")
        event_id = editorial["event_id"]
    else:
        if (
            card["kind"] != "STATUS_UPDATE"
            or card["status"] not in UPDATE_STATUSES
            or card["research"] is not None
        ):
            raise ChannelCardError("successor revisions must be status-only cards")
        predecessor = lineage["supersedes_card_id"]
        if not isinstance(predecessor, str) or _CARD_ID.fullmatch(predecessor) is None:
            raise ChannelCardError("a successor must name the card it supersedes")
        editorial = validate_editorial_event(card["editorial"])
        if (
            editorial["signal_id"] != signal_id
            or editorial["revision"] != revision
            or editorial["previous_card_id"] != predecessor
            or editorial["status"] != card["status"]
            or published < editorial["occurred_at"]
        ):
            raise ChannelCardError("editorial event and card lineage differ")
        event_id = editorial["event_id"]

    if card_id != _card_id(series_id, revision, event_id):
        raise ChannelCardError("card ID does not match its series, revision, and event")

    market = card["market"]
    if not isinstance(market, Mapping) or market.get("venue") != "polymarket":
        raise ChannelCardError("channel card market must be Polymarket")
    _exact_keys(market, _MARKET_KEYS, "channel card market")
    _text(market.get("market_id"), "market_id", maximum=256)
    _text(market.get("question"), "market question", maximum=700)
    if market.get("direction") not in {"YES", "NO"}:
        raise ChannelCardError("market direction is invalid")
    _probability(market.get("quoted_probability"), "quoted probability")
    _https_url(market.get("market_url"), "market_url", polymarket_only=True)
    _text(market.get("resolution_rules_ref"), "resolution_rules_ref", maximum=512)
    rules_url = market.get("resolution_rules_url")
    if rules_url is not None:
        _https_url(rules_url, "resolution_rules_url", polymarket_only=True)
    if market.get("resolution_rules_verified") is not False:
        raise ChannelCardError("this module cannot mark resolution rules verified")

    if revision == 1:
        research = card["research"]
        if not isinstance(research, Mapping):
            raise ChannelCardError("root research content is invalid")
        _exact_keys(research, _RESEARCH_KEYS, "channel card research")
        _text(research.get("signal_type"), "signal_type", maximum=80)
        _probability(research.get("confidence"), "confidence")
        horizon = research.get("horizon_hours")
        if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 8_760:
            raise ChannelCardError("research horizon is invalid")
        _text(
            research.get("reasoning"),
            "reasoning",
            maximum=1_600,
            one_line=False,
        )

    evidence = card["evidence"]
    if not isinstance(evidence, Mapping):
        raise ChannelCardError("channel card evidence is invalid")
    _exact_keys(evidence, _EVIDENCE_KEYS, "channel card evidence")
    sources = _source_links(
        evidence.get("sources"),
        published_at=published,
        allowed_refs=None,
        require_one=revision == 1 or card["status"] == "RESOLVED",
    )
    if sources != evidence["sources"]:
        raise ChannelCardError("source links are not in canonical order")
    if not isinstance(evidence.get("unlinked_observation_refs"), list):
        raise ChannelCardError("unlinked observation refs must be a list")
    if not isinstance(evidence.get("limitations"), list):
        raise ChannelCardError("evidence limitations must be a list")

    authority = card["authority"]
    if not isinstance(authority, Mapping):
        raise ChannelCardError("channel card authority is invalid")
    _exact_keys(authority, _AUTHORITY_KEYS, "channel card authority")
    if authority != {
        "mode": CARD_AUTHORITY_MODE,
        "execution_allowed": False,
        "paper_only": True,
        "wallet_access": False,
        "jurisdiction_verified": False,
    }:
        raise ChannelCardError("channel card authority must remain paper-only")

    integrity = card["integrity"]
    if not isinstance(integrity, Mapping):
        raise ChannelCardError("channel card integrity is missing")
    _exact_keys(integrity, _INTEGRITY_KEYS, "channel card integrity")
    source_digest = integrity.get("source_envelope_digest")
    content = integrity.get("content_digest")
    if not isinstance(source_digest, str) or _DIGEST.fullmatch(source_digest) is None:
        raise ChannelCardError("source envelope digest is invalid")
    if not isinstance(content, str) or _DIGEST.fullmatch(content) is None:
        raise ChannelCardError("channel card content digest is invalid")
    if integrity.get("proves_authorship") is not False or integrity.get("proves_truth") is not False:
        raise ChannelCardError("a content digest cannot claim authorship or truth")
    if not hmac.compare_digest(content, channel_card_digest(card)):
        raise ChannelCardError("channel card content digest mismatch")


def verify_channel_card(card: Mapping[str, Any]) -> bool:
    try:
        validate_channel_card(card)
    except (ChannelCardError, TypeError, ValueError):
        return False
    return True


def validate_successor(previous: Mapping[str, Any], successor: Mapping[str, Any]) -> None:
    """Validate the relationship between two independently valid cards."""

    validate_channel_card(previous)
    validate_channel_card(successor)
    if successor["signal_id"] != previous["signal_id"]:
        raise ChannelCardError("successor changed the signal ID")
    if successor["series_id"] != previous["series_id"]:
        raise ChannelCardError("successor changed the series ID")
    if successor["revision"] != previous["revision"] + 1:
        raise ChannelCardError("successor revision is not contiguous")
    if successor["lineage"]["root_card_id"] != previous["lineage"]["root_card_id"]:
        raise ChannelCardError("successor changed the lineage root")
    if successor["lineage"]["supersedes_card_id"] != previous["card_id"]:
        raise ChannelCardError("successor does not supersede the prior card")
    if successor["published_at"] < previous["published_at"]:
        raise ChannelCardError("successor predates its predecessor")


def _defang_untrusted(value: Any, maximum: int) -> str:
    text = str(value or "")
    text = "".join(
        character
        for character in text
        if character in "\n\t" or not unicodedata.category(character).startswith("C")
    )
    text = re.sub(r"(?i)https://", "hxxps://", text)
    text = re.sub(r"(?i)http://", "hxxp://", text)
    text = re.sub(r"(?i)\bwww\.", "www[.]", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) > maximum:
        text = text[: maximum - 1].rstrip() + "…"
    return text


def _source_lines(card: Mapping[str, Any]) -> list[str]:
    sources = card["evidence"]["sources"]
    if not sources:
        return ["Evidence links: none attached to this status update."]
    lines = ["Evidence links (syntax-validated; not authenticated here):"]
    for index, source in enumerate(sources[:MAX_RENDERED_SOURCE_LINKS], start=1):
        source_kind = "primary" if source["is_primary"] else "secondary"
        lines.extend(
            [
                f"{index}. {_defang_untrusted(source['label'], 120)} ({source_kind})",
                f"   Observed: {source['observed_at']}",
                f"   Ref: {_defang_untrusted(source['observation_ref'], 160)}",
                f"   {source['url']}",
            ]
        )
    if len(sources) > MAX_RENDERED_SOURCE_LINKS:
        lines.append(
            f"+ {len(sources) - MAX_RENDERED_SOURCE_LINKS} more source link(s) in the canonical card."
        )
    unlinked = card["evidence"]["unlinked_observation_refs"]
    if unlinked:
        lines.append(f"Unlinked sealed observation refs: {len(unlinked)}")
    return lines


def render_channel_card(card: Mapping[str, Any]) -> str:
    """Render one plain-text, forward-safe Telegram channel message."""

    validate_channel_card(card)
    market = card["market"]
    heading = (
        "KINGDOM RESEARCH • ACTIVE"
        if card["kind"] == "RESEARCH"
        else f"KINGDOM STATUS • {card['status']}"
    )
    lines = [
        heading,
        "",
        _defang_untrusted(market["question"], 700),
        f"Signal: {card['signal_id']} • Revision {card['revision']}",
    ]
    if card["kind"] == "RESEARCH":
        research = card["research"]
        lines.extend(
            [
                f"Model direction: {market['direction']}",
                f"Observed market probability: {market['quoted_probability']:.1%}",
                f"Model confidence: {research['confidence']:.1%}",
                f"Horizon: {research['horizon_hours']}h",
                f"Signal type: {_defang_untrusted(research['signal_type'], 80)}",
                "",
                "Untrusted model analysis:",
            ]
        )
        reasoning = _defang_untrusted(research["reasoning"], 900)
        lines.extend("> " + line for line in reasoning.splitlines() if line.strip())
    else:
        editorial = card["editorial"]
        lines.extend(
            [
                "",
                f"Reason: {_defang_untrusted(editorial['reason_code'], 64)}",
                _defang_untrusted(editorial["summary"], 650),
                "The superseded research is not repeated in this update.",
            ]
        )

    lines.extend(["", *_source_lines(card), "", "Official market:", market["market_url"]])
    if market["resolution_rules_url"]:
        lines.extend(["Resolution rules:", market["resolution_rules_url"]])
    else:
        lines.append(
            "Resolution rules ref: "
            + _defang_untrusted(market["resolution_rules_ref"], 300)
        )
    lines.extend(
        [
            "Resolution rules have not been independently verified by this module.",
            "",
            f"Published: {card['published_at']}",
            f"Card ID: {card['card_id']}",
            f"Root card: {card['lineage']['root_card_id']}",
        ]
    )
    if card["lineage"]["supersedes_card_id"]:
        lines.append(f"Supersedes: {card['lineage']['supersedes_card_id']}")

    footer = "\n\n" + _CHANNEL_FOOTER
    body = "\n".join(lines).strip()
    available = TARGET_CHANNEL_TEXT - len(footer)
    if len(body) > available:
        body = body[: available - 1].rstrip() + "…"
    rendered = body + footer
    if len(rendered) > MAX_CHANNEL_TEXT:
        raise ChannelCardError("rendered channel card exceeds Telegram's text limit")
    return rendered
