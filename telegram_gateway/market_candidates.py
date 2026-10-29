"""Bounded, read-only scoring of Polymarket Gamma market snapshots.

The module accepts already-fetched ``/markets`` or ``/events`` JSON.  It has
no HTTP client, wallet, signer, token identifiers, or order methods.  Even a
fully evidenced row is labelled ``MANUAL_REVIEW`` rather than executable.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit


SCHEMA = "kingdom.market-candidates/0.1"

MAX_PAYLOAD_BYTES = 2_000_000
MAX_RECORDS = 500
MAX_MARKETS_PER_EVENT = 100
MAX_TOTAL_NODES = 50_000
MAX_DEPTH = 16
MAX_TOTAL_STRING_CHARS = 2_000_000
MAX_INPUT_STRING_CHARS = 16_384
MAX_REPORT_NODES = 300_000
MAX_REPORT_STRING_CHARS = 8_000_000

MIN_HORIZON = timedelta(days=1)
MAX_HORIZON = timedelta(days=45)
MAX_SNAPSHOT_AGE = timedelta(minutes=30)
MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)
MIN_LIQUIDITY_USD = 25_000.0
MIN_VOLUME_24H_USD = 10_000.0
MAX_SPREAD = 0.05
NEAR_CERTAINTY_LOW = 0.03
NEAR_CERTAINTY_HIGH = 0.97
MAX_USD_NUMBER = 1_000_000_000_000_000.0

_CONTROL_AND_BIDI = re.compile(
    r"[\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]"
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_NUMBER = re.compile(
    r"^[+-]?(?:\d{1,18}(?:\.\d{0,18})?|\.\d{1,18})(?:[eE][+-]?\d{1,3})?$"
)
_FAST_CRYPTO_LANGUAGE = re.compile(
    r"\b(?:5[ -]?min(?:ute)?s?|15[ -]?min(?:ute)?s?|"
    r"30[ -]?min(?:ute)?s?|hourly|next hour)\b",
    re.IGNORECASE,
)
_AMBIGUOUS_WORDS = re.compile(
    r"\b(?:escalat\w*|invasion|war|major|meaningful|significant|"
    r"nominee|dating|break up|celebrity)\b",
    re.IGNORECASE,
)
_SPORTS_TEXT = re.compile(
    r"\b(?:"
    r"tennis|basketball|baseball|ice hockey|hockey|soccer|"
    r"american football|cricket|rugby|golf|motorsports?|boxing|"
    r"nfl|nba|wnba|mlb|nhl|ncaa[bf]?|ufc|mma|atp|wta|ipl|pga|"
    r"formula[ -]?1|nascar|"
    r"premier league|champions league|conference league|la liga|"
    r"bundesliga|serie a|copa (?:america|libertadores)|"
    r"(?:men(?:'s|’s)|women(?:'s|’s)) us open|wimbledon|roland garros|"
    r"australian open|french open|super bowl|stanley cup|world series|"
    r"world cup|ryder cup|masters tournament|grand slam|ballon d(?:'|’)or|"
    r"counter[ -]?strike|cs2|dota(?: 2)?|valorant|league of legends|"
    r"best[ -]?of[ -]?[1-7]|bo[1-7]"
    r")\b",
    re.IGNORECASE,
)
_SPORTS_METADATA = re.compile(r"\b(?:sports?|esports?)\b", re.IGNORECASE)
_MATCHUP_MARKER = re.compile(r"\b(?:vs\.?|versus|against)\b", re.IGNORECASE)
_GAME_CONTEXT = re.compile(
    r"\b(?:game|match|fixture|sets?|innings?|goals?|score|moneyline|"
    r"playoffs?|quarterfinals?|semifinals?|finals?|rounds?|maps?)\b|\bo/u\b",
    re.IGNORECASE,
)

Endpoint = Literal["markets", "events"]


class CandidateInputError(ValueError):
    """The supplied snapshot is malformed or exceeds a parsing bound."""


def _utc_timestamp(value: Any, *, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and 0 < len(value) <= 80:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except (OverflowError, ValueError) as exc:
            raise CandidateInputError(f"{field} must be a valid ISO-8601 timestamp") from exc
    else:
        raise CandidateInputError(f"{field} must be a timezone-aware ISO-8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CandidateInputError(f"{field} must include a timezone")
    parsed = parsed.astimezone(timezone.utc)
    if not datetime(2020, 1, 1, tzinfo=timezone.utc) <= parsed <= datetime(
        2100, 1, 1, tzinfo=timezone.utc
    ):
        raise CandidateInputError(f"{field} is outside the supported date range")
    return parsed


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _reject_json_constant(value: str) -> None:
    raise CandidateInputError(f"non-finite JSON number is not allowed: {value}")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateInputError(f"duplicate JSON object key: {key[:80]!r}")
        result[key] = value
    return result


def _decode_payload(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray, memoryview)):
        raw = bytes(payload)
        if len(raw) > MAX_PAYLOAD_BYTES:
            raise CandidateInputError(
                f"payload exceeds the {MAX_PAYLOAD_BYTES}-byte limit"
            )
        try:
            text = raw.decode("utf-8", errors="strict")
            value = json.loads(
                text,
                parse_float=Decimal,
                parse_constant=_reject_json_constant,
                object_pairs_hook=_object_without_duplicate_keys,
            )
        except CandidateInputError:
            raise
        except (json.JSONDecodeError, ValueError, RecursionError, UnicodeDecodeError) as exc:
            raise CandidateInputError("payload is not bounded, valid UTF-8 JSON") from exc
    elif isinstance(payload, (dict, list)):
        value = payload
    else:
        raise CandidateInputError("payload must be JSON bytes, a dict, or a list")
    _validate_json_like(value)
    return value


def _payload_digest(payload: Any, value: Any) -> tuple[str, str]:
    """Bind a report to exact bytes or an unambiguous typed Python value."""

    if isinstance(payload, (bytes, bytearray, memoryview)):
        material = bytes(payload)
        basis = "input_bytes"
    else:

        def tagged(item: Any) -> Any:
            if item is None:
                return ["null"]
            if isinstance(item, bool):
                return ["boolean", item]
            if isinstance(item, int):
                return ["integer", str(item)]
            if isinstance(item, float):
                return ["float", repr(item)]
            if isinstance(item, Decimal):
                return ["decimal", str(item)]
            if isinstance(item, str):
                return ["string", item]
            if isinstance(item, list):
                return ["array", [tagged(child) for child in item]]
            if isinstance(item, dict):
                return [
                    "object",
                    [[key, tagged(item[key])] for key in sorted(item)],
                ]
            raise CandidateInputError("payload contains an unsupported digest type")

        material = json.dumps(
            tagged(value),
            ensure_ascii=True,
            sort_keys=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
        basis = "typed_python_json_value_v1"
    return basis, hashlib.sha256(material).hexdigest()


def _validate_json_like(
    root: Any,
    *,
    max_nodes: int = MAX_TOTAL_NODES,
    max_string_chars: int = MAX_TOTAL_STRING_CHARS,
) -> None:
    """Reject cyclic, deep, huge, non-finite, or non-JSON Python objects."""

    stack: list[tuple[Any, int]] = [(root, 0)]
    active: set[int] = set()
    exit_marker = object()
    node_count = 0
    string_chars = 0
    while stack:
        value, depth = stack.pop()
        if value is exit_marker:
            active.discard(depth)
            continue
        node_count += 1
        if node_count > max_nodes:
            raise CandidateInputError(f"payload exceeds the {max_nodes}-node limit")
        if depth > MAX_DEPTH:
            raise CandidateInputError(f"payload exceeds the maximum depth of {MAX_DEPTH}")

        if isinstance(value, str):
            string_chars += len(value)
            if len(value) > MAX_INPUT_STRING_CHARS:
                raise CandidateInputError("payload contains an oversized string")
            if string_chars > max_string_chars:
                raise CandidateInputError("payload contains too much string data")
            continue
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, int):
            if abs(value) > 10**30:
                raise CandidateInputError("payload contains an out-of-range integer")
            continue
        if isinstance(value, (float, Decimal)):
            try:
                finite = math.isfinite(float(value))
            except (OverflowError, TypeError, ValueError):
                finite = False
            if not finite or abs(value) > Decimal("1e30"):
                raise CandidateInputError("payload contains an out-of-range finite number")
            continue
        if isinstance(value, (dict, list)):
            object_id = id(value)
            if object_id in active:
                raise CandidateInputError("payload contains a cycle")
            active.add(object_id)
            stack.append((exit_marker, object_id))
            if isinstance(value, dict):
                for key, child in reversed(list(value.items())):
                    if not isinstance(key, str):
                        raise CandidateInputError("object keys must be strings")
                    stack.append((child, depth + 1))
                    stack.append((key, depth + 1))
            else:
                for child in reversed(value):
                    stack.append((child, depth + 1))
            continue
        raise CandidateInputError(
            f"payload contains unsupported Python type: {type(value).__name__}"
        )


def _safe_text(value: Any, *, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = _CONTROL_AND_BIDI.sub("", value)
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        return None
    return cleaned[:maximum]


def _safe_id(value: Any) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if _SAFE_ID.fullmatch(value) else None


def _strict_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _first(mapping: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _number(
    value: Any,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        if isinstance(value, str):
            stripped = value.strip()
            if len(stripped) > 64 or not _NUMBER.fullmatch(stripped):
                return None
            decimal = Decimal(stripped)
        elif isinstance(value, (int, float, Decimal)):
            decimal = Decimal(str(value))
        else:
            return None
    except (InvalidOperation, OverflowError, ValueError):
        return None
    if not decimal.is_finite():
        return None
    lower = Decimal(str(minimum))
    upper = Decimal(str(maximum))
    if not lower <= decimal <= upper:
        return None
    result = float(decimal)
    if not math.isfinite(result):
        return None
    return result


def _url(value: Any) -> str | None:
    text = _safe_text(value, maximum=MAX_INPUT_STRING_CHARS)
    if text is None or len(text) > 2_048:
        return None
    try:
        parts = urlsplit(text)
        if (
            parts.scheme.lower() not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            return None
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, ""))


def _tags(record: dict[str, Any], event: dict[str, Any] | None) -> list[str]:
    values: list[str] = []
    for owner in (record, event or {}):
        raw = owner.get("tags")
        if not isinstance(raw, list):
            continue
        for item in raw[:32]:
            candidates: tuple[Any, ...]
            if isinstance(item, dict):
                candidates = (item.get("slug"), item.get("label"), item.get("name"))
            else:
                candidates = (item,)
            for candidate in candidates:
                text = _safe_text(candidate, maximum=80)
                if text:
                    values.append(text.lower())
    return sorted(set(values))[:32]


def _one_mapping(owner: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Return at most one bounded mapping from an object-or-list field."""

    value = owner.get(name)
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None


def _parent_event(
    record: dict[str, Any], endpoint_event: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, bool]:
    if endpoint_event is not None:
        return endpoint_event, False
    embedded = _one_mapping(record, "events") or _one_mapping(record, "event")
    return embedded, embedded is not None


def _series_metadata(
    record: dict[str, Any], event: dict[str, Any] | None
) -> dict[str, Any] | None:
    if event is not None:
        series = _one_mapping(event, "series")
        if series is not None:
            return series
    return _one_mapping(record, "series")


def _parse_optional_timestamp(value: Any) -> tuple[datetime | None, bool]:
    if value is None:
        return None, False
    try:
        return _utc_timestamp(value, field="timestamp"), False
    except CandidateInputError:
        return None, True


def _resolution_evidence(
    record: dict[str, Any], event: dict[str, Any] | None
) -> tuple[str, str | None, str | None, bool]:
    reference_fields = ("resolutionSource", "resolutionSourceUrl", "resolution_source")
    raw_ref = next(
        (
            value
            for owner in (record, event or {})
            for name in reference_fields
            if (value := owner.get(name)) is not None
            and _safe_text(value, maximum=2_048) is not None
        ),
        None,
    )
    reference = _url(raw_ref)
    invalid_reference = raw_ref is not None and reference is None

    rules_fields = ("rules", "resolutionRules", "resolutionCriteria", "description")
    raw_rules = next(
        (
            value
            for owner in (record, event or {})
            for name in rules_fields
            if (value := owner.get(name)) is not None
            and _safe_text(value, maximum=MAX_INPUT_STRING_CHARS) is not None
        ),
        None,
    )
    rules = _safe_text(raw_rules, maximum=MAX_INPUT_STRING_CHARS)
    rules_digest = None
    if rules and len(rules) >= 20:
        rules_digest = hashlib.sha256(rules.encode("utf-8")).hexdigest()

    if reference:
        status = "REFERENCE_PRESENT_NOT_VERIFIED"
    elif rules_digest:
        status = "RULES_TEXT_PRESENT_NOT_VERIFIED"
    else:
        status = "MISSING"
    return status, reference, rules_digest, invalid_reference


def _extract_records(
    value: Any, endpoint: Endpoint | None
) -> tuple[
    list[tuple[int, int | None, dict[str, Any] | None, dict[str, Any] | None]],
    Endpoint,
    int,
    list[str],
    Any,
]:
    wrapper_snapshot: Any = None
    source_issues: list[str] = []
    if isinstance(value, dict):
        wrapper_snapshot = _first(value, ("snapshot_at", "captured_at", "asOf"))
        if endpoint == "events" or (endpoint is None and "events" in value):
            endpoint = "events"
            raw_records = value.get("events")
        elif endpoint == "markets" or (endpoint is None and "markets" in value):
            endpoint = "markets"
            raw_records = value.get("markets")
        elif endpoint is None:
            endpoint = "events" if isinstance(value.get("markets"), list) else "markets"
            raw_records = [value]
        else:
            raw_records = [value]
    else:
        raw_records = value
        if endpoint is None:
            endpoint = "events" if any(
                isinstance(row, dict) and isinstance(row.get("markets"), list)
                for row in raw_records[: min(len(raw_records), MAX_RECORDS + 1)]
            ) else "markets"

    if not isinstance(raw_records, list):
        raise CandidateInputError(f"/{endpoint} payload must contain a list")
    if len(raw_records) > MAX_RECORDS:
        raise CandidateInputError(f"/{endpoint} response exceeds {MAX_RECORDS} records")

    extracted: list[
        tuple[int, int | None, dict[str, Any] | None, dict[str, Any] | None]
    ] = []
    if endpoint == "markets":
        for index, record in enumerate(raw_records):
            extracted.append(
                (index, None, record if isinstance(record, dict) else None, None)
            )
    else:
        for event_index, event_raw in enumerate(raw_records):
            event = event_raw if isinstance(event_raw, dict) else None
            markets = event.get("markets") if event is not None else None
            if not isinstance(markets, list):
                source_issues.append("EVENT_WITHOUT_MARKET_LIST")
                extracted.append((event_index, None, None, event))
                continue
            if len(markets) > MAX_MARKETS_PER_EVENT:
                raise CandidateInputError(
                    f"event {event_index} exceeds {MAX_MARKETS_PER_EVENT} markets"
                )
            if not markets:
                source_issues.append("EVENT_WITHOUT_MARKETS")
            for market_index, market in enumerate(markets):
                extracted.append(
                    (
                        event_index,
                        market_index,
                        market if isinstance(market, dict) else None,
                        event,
                    )
                )
        if len(extracted) > MAX_RECORDS:
            raise CandidateInputError(
                f"flattened /events response exceeds {MAX_RECORDS} markets"
            )
    return extracted, endpoint, len(raw_records), sorted(set(source_issues)), wrapper_snapshot


def _gate(
    name: str,
    points: int,
    result: Literal["PASS", "FAIL", "UNKNOWN"],
    failure_status: Literal["EXCLUDED", "INCOMPLETE"],
    reason_codes: list[str],
    detail: str,
) -> dict[str, Any]:
    return {
        "gate": name,
        "result": result,
        "failure_status": failure_status,
        "reason_codes": reason_codes,
        "detail": detail,
        "points_awarded": points if result == "PASS" else 0,
        "points_possible": points,
    }


def _candidate(
    record: dict[str, Any] | None,
    event: dict[str, Any] | None,
    *,
    event_index: int,
    market_index: int | None,
    as_of: datetime,
    default_snapshot_at: datetime | None,
    default_snapshot_invalid: bool,
    snapshot_conflict: bool,
) -> dict[str, Any]:
    row = record or {}
    event, embedded_event_used = _parent_event(row, event)
    series = _series_metadata(row, event)
    market_id = _safe_id(_first(row, ("id", "marketId", "market_id")))
    condition_id = _safe_id(_first(row, ("conditionId", "condition_id")))
    event_id = _safe_id(_first(event or {}, ("id", "eventId", "event_id")))
    event_title = _safe_text(
        (event or {}).get("title"), maximum=500
    )
    full_question = _safe_text(
        _first(row, ("question", "title")), maximum=MAX_INPUT_STRING_CHARS
    )
    if full_question is None and event is not None:
        full_question = _safe_text(
            event.get("title"), maximum=MAX_INPUT_STRING_CHARS
        )
    question_truncated = full_question is not None and len(full_question) > 500
    question = full_question[:500] if full_question is not None else None
    full_slug = _safe_text(
        _first(row, ("slug", "marketSlug")), maximum=MAX_INPUT_STRING_CHARS
    )
    slug = full_slug if full_slug is not None and len(full_slug) <= 256 else None

    active = _strict_bool(row.get("active"))
    closed = _strict_bool(row.get("closed"))
    archived = _strict_bool(row.get("archived"))
    enable_order_book = _strict_bool(
        _first(row, ("enableOrderBook", "enable_order_book"))
    )
    accepting_orders = _strict_bool(
        _first(row, ("acceptingOrders", "accepting_orders"))
    )

    end_at, end_invalid = _parse_optional_timestamp(
        _first(row, ("endDate", "endDateIso", "end_date"))
    )
    if end_at is None and event is not None:
        event_end_at, event_end_invalid = _parse_optional_timestamp(
            _first(event, ("endDate", "endDateIso", "end_date"))
        )
        end_at = event_end_at
        end_invalid = end_invalid or event_end_invalid

    row_snapshot_raw = _first(
        row, ("snapshot_at", "captured_at", "snapshotAt", "capturedAt")
    )
    row_snapshot_at, row_snapshot_invalid = _parse_optional_timestamp(row_snapshot_raw)
    # The caller/wrapper capture time is authoritative.  An untrusted row may
    # add evidence but must not make an older snapshot appear current.
    snapshot_at = default_snapshot_at or row_snapshot_at
    row_snapshot_conflict = bool(
        row_snapshot_at is not None
        and default_snapshot_at is not None
        and row_snapshot_at != default_snapshot_at
    )
    snapshot_invalid = default_snapshot_invalid or row_snapshot_invalid

    liquidity = _number(
        _first(row, ("liquidityNum", "liquidity", "liquidityClob")),
        minimum=0.0,
        maximum=MAX_USD_NUMBER,
    )
    volume_24h = _number(
        _first(row, ("volume24hr", "volume24h", "volume24hrClob", "volume_24h")),
        minimum=0.0,
        maximum=MAX_USD_NUMBER,
    )
    best_bid = _number(
        _first(row, ("bestBid", "best_bid")), minimum=0.0, maximum=1.0
    )
    best_ask = _number(
        _first(row, ("bestAsk", "best_ask")), minimum=0.0, maximum=1.0
    )
    stated_spread_raw = _first(row, ("spread", "bidAskSpread"))
    stated_spread = _number(stated_spread_raw, minimum=0.0, maximum=1.0)
    stated_spread_invalid = stated_spread_raw is not None and stated_spread is None
    derived_spread = (
        round(best_ask - best_bid, 12)
        if best_bid is not None and best_ask is not None and best_ask >= best_bid
        else None
    )
    spread = derived_spread if derived_spread is not None else stated_spread
    spread_source = (
        "DERIVED_FROM_BID_ASK"
        if derived_spread is not None
        else "GAMMA_FIELD"
        if stated_spread is not None
        else None
    )
    spread_conflict = (
        derived_spread is not None
        and stated_spread is not None
        and abs(derived_spread - stated_spread) > 0.005
    )
    midpoint = (
        round((best_bid + best_ask) / 2.0, 12)
        if best_bid is not None and best_ask is not None
        else None
    )

    evidence, resolution_ref, rules_digest, invalid_ref = _resolution_evidence(
        row, event
    )
    tags = _tags(row, event)
    category_values = [
        text.lower()
        for owner in (row, event or {}, series or {})
        for name in ("category", "subcategory")
        if (text := _safe_text(owner.get(name), maximum=80)) is not None
    ]
    category_text = " ".join([*tags, *category_values])
    explicit_sports = any(
        _safe_text(value, maximum=80) is not None
        for owner in (row, event or {})
        for value in (
            owner.get("sportsMarketType"),
            owner.get("gameId"),
            owner.get("gameStartTime"),
        )
    )
    series_values = [
        text
        for owner, names in (
            (row, ("seriesSlug", "seriesTitle", "ticker")),
            (event or {}, ("seriesSlug", "seriesTitle", "ticker")),
            (series or {}, ("slug", "title", "ticker")),
        )
        for name in names
        if (text := _safe_text(owner.get(name), maximum=160)) is not None
    ]
    question_corpus = " ".join([question or "", event_title or ""])
    metadata_corpus = " ".join([category_text, *series_values])
    sports_corpus = " ".join([question_corpus, metadata_corpus])
    text_sports = _SPORTS_TEXT.search(question_corpus) is not None
    metadata_sports = bool(
        _SPORTS_METADATA.search(category_text)
        or _SPORTS_TEXT.search(metadata_corpus)
    )
    matchup_sports = bool(
        _MATCHUP_MARKER.search(sports_corpus)
        and _GAME_CONTEXT.search(sports_corpus)
    )
    sports_evidence: list[str] = []
    if explicit_sports:
        sports_evidence.append("EXPLICIT_GAME_METADATA")
    if text_sports:
        sports_evidence.append("SPORT_OR_COMPETITION_LANGUAGE")
    if metadata_sports:
        sports_evidence.append("SPORTS_SERIES_OR_CATEGORY_METADATA")
    if matchup_sports:
        sports_evidence.append("MATCHUP_WITH_GAME_CONTEXT")
    is_sports = bool(sports_evidence)
    crypto_terms = ("crypto", "cryptocurrency", "bitcoin", "btc", "ethereum", "eth", "solana")
    question_and_tags = f"{question or ''} {category_text}".lower()
    is_crypto = any(
        re.search(rf"\b{re.escape(term)}\b", question_and_tags)
        for term in crypto_terms
    )
    horizon = end_at - as_of if end_at is not None else None
    latency_crypto = bool(
        is_crypto
        and (
            _FAST_CRYPTO_LANGUAGE.search(question_and_tags)
            or (horizon is not None and horizon <= timedelta(days=2))
        )
    )
    ambiguous_long_horizon = bool(
        horizon is not None
        and horizon > timedelta(days=30)
        and _AMBIGUOUS_WORDS.search(question_and_tags)
    )

    gates: list[dict[str, Any]] = []
    record_reasons: list[str] = []
    if record is None or not market_id or not question:
        record_reasons.append("MALFORMED_OR_UNIDENTIFIED_MARKET")
    if question_truncated:
        record_reasons.append("QUESTION_EXCEEDS_SAFE_LENGTH")
    gates.append(
        _gate(
            "record",
            0,
            "UNKNOWN" if record_reasons else "PASS",
            "INCOMPLETE",
            record_reasons,
            "A bounded market object, stable identifier, and question are required.",
        )
    )

    state_reasons: list[str] = []
    if closed is True or archived is True:
        state_reasons.append("CLOSED_OR_ARCHIVED")
    if active is False:
        state_reasons.append("INACTIVE_MARKET")
    if state_reasons:
        state_result: Literal["PASS", "FAIL", "UNKNOWN"] = "FAIL"
        state_failure: Literal["EXCLUDED", "INCOMPLETE"] = "EXCLUDED"
    elif active is None or closed is None:
        state_result = "UNKNOWN"
        state_failure = "INCOMPLETE"
        state_reasons = ["MARKET_STATE_MISSING_OR_INVALID"]
    else:
        state_result = "PASS"
        state_failure = "EXCLUDED"
    gates.append(
        _gate(
            "market_state", 10, state_result, state_failure, state_reasons,
            "The market must be explicitly active, open, and not archived.",
        )
    )

    book_reasons: list[str] = []
    if enable_order_book is False:
        book_reasons.append("ORDER_BOOK_DISABLED")
    if accepting_orders is False:
        book_reasons.append("ORDERS_NOT_ACCEPTED")
    if book_reasons:
        book_result: Literal["PASS", "FAIL", "UNKNOWN"] = "FAIL"
        book_failure: Literal["EXCLUDED", "INCOMPLETE"] = "EXCLUDED"
    elif enable_order_book is None or accepting_orders is None:
        book_result = "UNKNOWN"
        book_failure = "INCOMPLETE"
        book_reasons = ["ORDER_BOOK_STATE_MISSING_OR_INVALID"]
    else:
        book_result = "PASS"
        book_failure = "EXCLUDED"
    gates.append(
        _gate(
            "order_book", 10, book_result, book_failure, book_reasons,
            "Gamma must explicitly show an enabled order book accepting orders.",
        )
    )

    category_reasons: list[str] = []
    if is_sports:
        category_reasons.append("SPORTS_OR_ESPORTS")
    if latency_crypto:
        category_reasons.append("LATENCY_SENSITIVE_CRYPTO")
    if ambiguous_long_horizon:
        category_reasons.append("AMBIGUOUS_LONG_HORIZON")
    gates.append(
        _gate(
            "market_type", 10, "FAIL" if category_reasons else "PASS", "EXCLUDED",
            category_reasons,
            "Sports, esports, latency races, and ambiguous long-horizon markets are excluded.",
        )
    )

    if end_invalid:
        horizon_result: Literal["PASS", "FAIL", "UNKNOWN"] = "FAIL"
        horizon_reasons = ["INVALID_END_DATE"]
    elif end_at is None:
        horizon_result: Literal["PASS", "FAIL", "UNKNOWN"] = "FAIL"
        horizon_reasons = ["MISSING_END_DATE"]
    elif horizon is None or not MIN_HORIZON <= horizon <= MAX_HORIZON:
        horizon_result = "FAIL"
        horizon_reasons = ["HORIZON_OUTSIDE_1_TO_45_DAYS"]
    else:
        horizon_result = "PASS"
        horizon_reasons = []
    gates.append(
        _gate(
            "horizon", 15, horizon_result, "EXCLUDED", horizon_reasons,
            "Expiry must be between 1 and 45 days after the explicit as-of time.",
        )
    )

    resolution_reasons: list[str] = []
    if invalid_ref:
        resolution_reasons.append("INVALID_RESOLUTION_REFERENCE")
    if evidence == "MISSING":
        resolution_reasons.append("RESOLUTION_EVIDENCE_MISSING")
    gates.append(
        _gate(
            "resolution", 15,
            "UNKNOWN" if resolution_reasons else "PASS", "INCOMPLETE",
            resolution_reasons,
            "Rules text or an HTTP(S) resolution reference must be present; "
            "neither is verified here.",
        )
    )

    freshness_reasons: list[str] = []
    if snapshot_invalid:
        freshness_reasons.append("INVALID_SNAPSHOT_TIMESTAMP")
    if snapshot_conflict or row_snapshot_conflict:
        freshness_reasons.append("SNAPSHOT_TIMESTAMP_CONFLICT")
    if snapshot_at is None:
        freshness_result: Literal["PASS", "FAIL", "UNKNOWN"] = "UNKNOWN"
        freshness_failure: Literal["EXCLUDED", "INCOMPLETE"] = "INCOMPLETE"
        freshness_reasons.append("SNAPSHOT_TIMESTAMP_MISSING")
    elif snapshot_at > as_of + MAX_FUTURE_CLOCK_SKEW:
        freshness_result = "FAIL"
        freshness_failure = "EXCLUDED"
        freshness_reasons.append("SNAPSHOT_FROM_FUTURE")
    elif as_of - snapshot_at > MAX_SNAPSHOT_AGE:
        freshness_result = "FAIL"
        freshness_failure = "EXCLUDED"
        freshness_reasons.append("STALE_SNAPSHOT")
    elif freshness_reasons:
        freshness_result = "UNKNOWN"
        freshness_failure = "INCOMPLETE"
    else:
        freshness_result = "PASS"
        freshness_failure = "EXCLUDED"
    gates.append(
        _gate(
            "freshness", 10, freshness_result, freshness_failure,
            sorted(set(freshness_reasons)),
            "The capture time must be within 30 minutes of as-of and no more "
            "than 5 minutes ahead.",
        )
    )

    liquidity_result: Literal["PASS", "FAIL", "UNKNOWN"]
    if liquidity is None:
        liquidity_result = "UNKNOWN"
        liquidity_reasons = ["LIQUIDITY_MISSING_OR_INVALID"]
        liquidity_failure: Literal["EXCLUDED", "INCOMPLETE"] = "INCOMPLETE"
    elif liquidity < MIN_LIQUIDITY_USD:
        liquidity_result = "FAIL"
        liquidity_reasons = ["THIN_LIQUIDITY"]
        liquidity_failure = "EXCLUDED"
    else:
        liquidity_result = "PASS"
        liquidity_reasons = []
        liquidity_failure = "EXCLUDED"
    gates.append(
        _gate(
            "liquidity", 10, liquidity_result, liquidity_failure, liquidity_reasons,
            f"Reported liquidity must be at least ${MIN_LIQUIDITY_USD:,.0f}.",
        )
    )

    if volume_24h is None:
        volume_result: Literal["PASS", "FAIL", "UNKNOWN"] = "UNKNOWN"
        volume_reasons = ["VOLUME_24H_MISSING_OR_INVALID"]
        volume_failure: Literal["EXCLUDED", "INCOMPLETE"] = "INCOMPLETE"
    elif volume_24h < MIN_VOLUME_24H_USD:
        volume_result = "FAIL"
        volume_reasons = ["THIN_VOLUME_24H"]
        volume_failure = "EXCLUDED"
    else:
        volume_result = "PASS"
        volume_reasons = []
        volume_failure = "EXCLUDED"
    gates.append(
        _gate(
            "volume_24h", 10, volume_result, volume_failure, volume_reasons,
            f"Reported 24-hour volume must be at least ${MIN_VOLUME_24H_USD:,.0f}.",
        )
    )

    market_reasons: list[str] = []
    if (
        best_bid is None
        or best_ask is None
        or not 0.0 < best_bid < best_ask < 1.0
    ):
        market_reasons.append("TWO_SIDED_BID_ASK_MISSING_OR_INVALID")
    if stated_spread_raw is None:
        market_reasons.append("SPREAD_MISSING_OR_INVALID")
    elif spread is None:
        market_reasons.append("SPREAD_MISSING_OR_INVALID")
    elif spread > MAX_SPREAD:
        market_reasons.append("SPREAD_TOO_WIDE")
    if stated_spread_invalid:
        market_reasons.append("SPREAD_MISSING_OR_INVALID")
    if spread_conflict:
        market_reasons.append("SPREAD_CONFLICTS_WITH_BID_ASK")
    gates.append(
        _gate(
            "two_sided_market", 5, "FAIL" if market_reasons else "PASS", "EXCLUDED",
            market_reasons,
            f"A two-sided bid/ask and a spread no wider than {MAX_SPREAD:.2f} are required.",
        )
    )

    price_reasons: list[str] = []
    if midpoint is None:
        price_result: Literal["PASS", "FAIL", "UNKNOWN"] = "UNKNOWN"
        price_failure: Literal["EXCLUDED", "INCOMPLETE"] = "INCOMPLETE"
        price_reasons.append("MIDPOINT_UNAVAILABLE")
    elif midpoint <= NEAR_CERTAINTY_LOW or midpoint >= NEAR_CERTAINTY_HIGH:
        price_result = "FAIL"
        price_failure = "EXCLUDED"
        price_reasons.append("NEAR_ZERO_OR_ONE_WITHOUT_DEPTH_EVIDENCE")
    else:
        price_result = "PASS"
        price_failure = "EXCLUDED"
    gates.append(
        _gate(
            "price_extremity", 5, price_result, price_failure, price_reasons,
            "Prices at or beyond 0.03/0.97 are excluded because Gamma summary "
            "data does not prove exit depth.",
        )
    )

    failures = [gate for gate in gates if gate["result"] != "PASS"]
    if any(gate["failure_status"] == "EXCLUDED" for gate in failures):
        status = "EXCLUDED"
    elif failures:
        status = "INCOMPLETE"
    else:
        status = "MANUAL_REVIEW"
    reasons = [
        reason
        for gate in gates
        for reason in gate["reason_codes"]
    ]
    score = sum(gate["points_awarded"] for gate in gates)

    normalized = {
        "market_id": market_id,
        "condition_id": condition_id,
        "event_id": event_id,
        "event_title": event_title,
        "embedded_event_metadata_used": embedded_event_used,
        "slug": slug,
        "question": question,
        "active": active,
        "closed": closed,
        "archived": archived,
        "enable_order_book": enable_order_book,
        "accepting_orders": accepting_orders,
        "end_at": _iso(end_at) if end_at is not None else None,
        "horizon_days": (
            round(horizon.total_seconds() / 86_400, 6)
            if horizon is not None
            else None
        ),
        "snapshot_at": _iso(snapshot_at) if snapshot_at is not None else None,
        "liquidity_usd": liquidity,
        "volume_24h_usd": volume_24h,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "spread_source": spread_source,
        "midpoint": midpoint,
        "resolution_evidence": evidence,
        "resolution_ref": resolution_ref,
        "rules_sha256": rules_digest,
        "category_flags": {
            "sports_or_esports": is_sports,
            "sports_evidence": sports_evidence,
            "crypto": is_crypto,
            "latency_sensitive_crypto": latency_crypto,
            "ambiguous_long_horizon": ambiguous_long_horizon,
        },
    }
    fallback_id = (
        f"event:{event_index}:market:{market_index}"
        if market_index is not None
        else f"record:{event_index}"
    )
    return {
        "candidate_id": market_id or condition_id or fallback_id,
        "source_position": {
            "record_index": event_index,
            "market_index": market_index,
        },
        "status": status,
        "score": score,
        "score_max": 100,
        "reason_codes": reasons,
        "normalized": normalized,
        "gates": gates,
        "authority": {
            "mode": "RESEARCH_REVIEW_ONLY",
            "execution_allowed": False,
            "manual_review_required": True,
            "jurisdiction_verified": False,
        },
    }


def build_candidate_report(
    payload: Any,
    *,
    as_of: datetime | str,
    snapshot_at: datetime | str | None = None,
    endpoint: Endpoint | None = None,
) -> dict[str, Any]:
    """Parse and score a bounded Gamma snapshot without any network activity.

    ``as_of`` is mandatory so historical payloads cannot silently masquerade
    as current.  ``snapshot_at`` should be the caller's capture timestamp; a
    wrapper-level ``snapshot_at``/``captured_at`` is also accepted.  Missing,
    conflicting, future, or stale capture evidence fails closed.
    """

    if endpoint not in {None, "markets", "events"}:
        raise CandidateInputError("endpoint must be 'markets' or 'events'")
    current = _utc_timestamp(as_of, field="as_of")
    value = _decode_payload(payload)
    digest_basis, payload_sha256 = _payload_digest(payload, value)
    records, detected_endpoint, source_record_count, source_issues, wrapper_raw = (
        _extract_records(value, endpoint)
    )

    explicit_snapshot, explicit_invalid = _parse_optional_timestamp(snapshot_at)
    wrapper_snapshot, wrapper_invalid = _parse_optional_timestamp(wrapper_raw)
    conflict = bool(
        explicit_snapshot is not None
        and wrapper_snapshot is not None
        and explicit_snapshot != wrapper_snapshot
    )
    default_snapshot = explicit_snapshot or wrapper_snapshot
    default_snapshot_invalid = explicit_invalid or wrapper_invalid

    candidates = [
        _candidate(
            record,
            event,
            event_index=event_index,
            market_index=market_index,
            as_of=current,
            default_snapshot_at=default_snapshot,
            default_snapshot_invalid=default_snapshot_invalid,
            snapshot_conflict=conflict,
        )
        for event_index, market_index, record, event in records
    ]
    candidates.sort(
        key=lambda item: (
            item["candidate_id"],
            item["source_position"]["record_index"],
            item["source_position"]["market_index"]
            if item["source_position"]["market_index"] is not None
            else -1,
        )
    )
    summary = {
        status: sum(item["status"] == status for item in candidates)
        for status in ("MANUAL_REVIEW", "INCOMPLETE", "EXCLUDED")
    }
    summary["total"] = len(candidates)

    return {
        "schema": SCHEMA,
        "as_of": _iso(current),
        "source": {
            "venue": "polymarket",
            "api_family": "gamma",
            "endpoint": f"/{detected_endpoint}",
            "record_count": source_record_count,
            "candidate_count": len(candidates),
            "snapshot_at": _iso(default_snapshot) if default_snapshot else None,
            "payload_sha256": payload_sha256,
            "payload_digest_basis": digest_basis,
            "issues": source_issues,
            "network_access": False,
        },
        "thresholds": {
            "horizon_days_min": 1,
            "horizon_days_max": 45,
            "snapshot_age_minutes_max": 30,
            "liquidity_usd_min": MIN_LIQUIDITY_USD,
            "volume_24h_usd_min": MIN_VOLUME_24H_USD,
            "spread_max": MAX_SPREAD,
            "near_certainty_low": NEAR_CERTAINTY_LOW,
            "near_certainty_high": NEAR_CERTAINTY_HIGH,
        },
        "summary": summary,
        "candidates": candidates,
        "authority": {
            "mode": "RESEARCH_REVIEW_ONLY",
            "execution_allowed": False,
            "can_place_orders": False,
            "manual_review_required": True,
        },
    }


def candidate_report_json(report: dict[str, Any]) -> str:
    """Serialize a report canonically for hashing, diffing, or JSONL output."""

    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise CandidateInputError(f"report must use schema {SCHEMA}")
    authority = report.get("authority")
    candidates = report.get("candidates")
    if (
        not isinstance(authority, dict)
        or authority.get("mode") != "RESEARCH_REVIEW_ONLY"
        or authority.get("execution_allowed") is not False
        or authority.get("can_place_orders") is not False
        or authority.get("manual_review_required") is not True
        or not isinstance(candidates, list)
        or len(candidates) > MAX_RECORDS
    ):
        raise CandidateInputError("report authority must remain manual-review-only")
    for candidate in candidates:
        candidate_authority = (
            candidate.get("authority") if isinstance(candidate, dict) else None
        )
        if (
            not isinstance(candidate, dict)
            or candidate.get("status") not in {"MANUAL_REVIEW", "INCOMPLETE", "EXCLUDED"}
            or not isinstance(candidate_authority, dict)
            or candidate_authority.get("execution_allowed") is not False
            or candidate_authority.get("manual_review_required") is not True
        ):
            raise CandidateInputError("candidate authority must remain manual-review-only")
    # The deterministic report expands each bounded input row into fixed gate
    # metadata, so its structural ceiling is intentionally larger than the
    # untrusted-input ceiling while still remaining finite.
    _validate_json_like(
        report,
        max_nodes=MAX_REPORT_NODES,
        max_string_chars=MAX_REPORT_STRING_CHARS,
    )
    try:
        return json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise CandidateInputError("report is not bounded canonical JSON") from exc


# Concise aliases for callers that naturally think in terms of scoring/dumping.
score_gamma_candidates = build_candidate_report
dumps_candidate_report = candidate_report_json


__all__ = [
    "CandidateInputError",
    "SCHEMA",
    "build_candidate_report",
    "candidate_report_json",
    "dumps_candidate_report",
    "score_gamma_candidates",
]
