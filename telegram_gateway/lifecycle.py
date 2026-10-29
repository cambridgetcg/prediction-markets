"""Strict incremental import of append-only S012 lifecycle events.

The lifecycle feed carries distribution-review state only.  Importing an
approval never grants trading authority, and this module neither creates a
missing signal nor rewrites its immutable signal envelope.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Protocol


LIFECYCLE_SCHEMA = "s012.signal-lifecycle/0.1"
LIFECYCLE_SCOPE = "research_distribution_only"
MAX_RECORD_BYTES = 65_536
MAX_SIGNAL_ID_BYTES = 128
MAX_REVISION = 1_000_000

_EVENT_KEYS = frozenset(
    {
        "schema",
        "event_id",
        "signal_id",
        "revision",
        "previous_status",
        "status",
        "occurred_at",
        "actor_kind",
        "reason_code",
        "scope",
        "execution_allowed",
    }
)
_TRANSITIONS = frozenset(
    {
        ("PENDING", "APPROVED"),
        ("PENDING", "REJECTED"),
        ("PENDING", "EXPIRED"),
        ("APPROVED", "REVOKED"),
        ("APPROVED", "EXPIRED"),
    }
)
_EVENT_ID_RE = re.compile(r"s012-life-[0-9a-f]{32}\Z")
_LABEL_RE = re.compile(r"[a-z0-9_.-]{1,64}\Z")
_OCCURRED_AT_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z"
)
_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_OUTCOMES = frozenset({"applied", "duplicate", "quarantined", "orphan"})
_CURSOR_VERSION = 1


class LifecycleEventError(ValueError):
    """A lifecycle event violates the producer/consumer contract."""


class LifecycleImportFailure(ValueError):
    """A complete lifecycle row could not be safely classified."""


class LifecycleStore(Protocol):
    """Minimum store surface required by the lifecycle importer."""

    def get_state(self, key: str) -> str | None: ...

    def set_state(self, key: str, value: str) -> None: ...

    def apply_signal_lifecycle(self, event: Mapping[str, Any]) -> str: ...


@dataclass(frozen=True)
class LifecycleImportResult:
    applied: int
    duplicates: int
    quarantined: int
    orphans: int
    complete_records: int
    cursor: int
    bootstrapped: bool = False
    source_reset: bool = False
    trailing_partial_ignored: bool = False


def _duplicate_safe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleEventError("JSON object contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> Any:
    raise LifecycleEventError("JSON constants must be finite standard values")


def _decode_event(raw: bytes) -> dict[str, Any]:
    try:
        decoded = raw.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=_duplicate_safe_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LifecycleEventError("row must contain one valid UTF-8 JSON object") from exc
    if not isinstance(value, dict):
        raise LifecycleEventError("lifecycle row must be a JSON object")
    return value


def _bounded_utf8(
    name: str,
    value: Any,
    *,
    maximum: int,
    machine_label: bool = False,
) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise LifecycleEventError(f"{name} must be a non-empty canonical string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise LifecycleEventError(f"{name} must be valid UTF-8") from exc
    if len(encoded) > maximum:
        raise LifecycleEventError(f"{name} exceeds its UTF-8 byte limit")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise LifecycleEventError(f"{name} contains a control character")
    if machine_label and _LABEL_RE.fullmatch(value) is None:
        raise LifecycleEventError(f"{name} must be a bounded machine label")
    return value


def _validate_occurred_at(value: Any) -> str:
    if not isinstance(value, str) or _OCCURRED_AT_RE.fullmatch(value) is None:
        raise LifecycleEventError("occurred_at must be canonical UTC with microseconds")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LifecycleEventError("occurred_at is not a valid timestamp") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise LifecycleEventError("occurred_at must use UTC")
    return value


def validate_lifecycle_event(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and copy one exact ``s012.signal-lifecycle/0.1`` event."""

    if not isinstance(record, Mapping):
        raise LifecycleEventError("lifecycle event must be a mapping")
    if any(not isinstance(key, str) for key in record):
        raise LifecycleEventError("lifecycle event keys must be strings")
    keys = frozenset(record)
    if keys != _EVENT_KEYS:
        missing = sorted(_EVENT_KEYS - keys)
        extra = sorted(keys - _EVENT_KEYS)
        if missing:
            raise LifecycleEventError(
                "lifecycle event is missing required keys: " + ", ".join(missing)
            )
        raise LifecycleEventError(
            "lifecycle event contains unsupported keys: " + ", ".join(extra)
        )

    if record["schema"] != LIFECYCLE_SCHEMA:
        raise LifecycleEventError("unsupported lifecycle schema")
    if record["scope"] != LIFECYCLE_SCOPE:
        raise LifecycleEventError("lifecycle scope is not distribution-only")
    if record["execution_allowed"] is not False:
        raise LifecycleEventError("execution_allowed must be the boolean false")

    event_id = _bounded_utf8("event_id", record["event_id"], maximum=42)
    if _EVENT_ID_RE.fullmatch(event_id) is None:
        raise LifecycleEventError("event_id has an invalid format")
    _bounded_utf8(
        "signal_id",
        record["signal_id"],
        maximum=MAX_SIGNAL_ID_BYTES,
    )
    revision = record["revision"]
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or not 1 <= revision <= MAX_REVISION
    ):
        raise LifecycleEventError("revision must be a positive SQLite integer")

    previous = record["previous_status"]
    status = record["status"]
    if not isinstance(previous, str) or not isinstance(status, str):
        raise LifecycleEventError("lifecycle statuses must be strings")
    if (previous, status) not in _TRANSITIONS:
        raise LifecycleEventError("lifecycle transition is not allowed")

    _validate_occurred_at(record["occurred_at"])
    _bounded_utf8(
        "actor_kind",
        record["actor_kind"],
        maximum=64,
        machine_label=True,
    )
    _bounded_utf8(
        "reason_code",
        record["reason_code"],
        maximum=64,
        machine_label=True,
    )

    event = dict(record)
    material = dict(event)
    del material["event_id"]
    canonical = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    expected_id = "s012-life-" + hashlib.sha256(canonical).hexdigest()[:32]
    if not hmac.compare_digest(event_id, expected_id):
        raise LifecycleEventError("event_id does not match the event content")
    return event


def _cursor_key(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:24]
    return f"s012_lifecycle_cursor:{digest}"


def _region_digest(handle: BinaryIO, start: int, length: int) -> str:
    position = handle.tell()
    handle.seek(start)
    digest = hashlib.sha256()
    remaining = length
    while remaining:
        chunk = handle.read(min(remaining, 1_048_576))
        if not chunk:
            break
        digest.update(chunk)
        remaining -= len(chunk)
    handle.seek(position)
    if remaining:
        raise LifecycleImportFailure("lifecycle source changed while it was read")
    return digest.hexdigest()


def _is_line_boundary(handle: BinaryIO, cursor: int) -> bool:
    if cursor == 0:
        return True
    position = handle.tell()
    handle.seek(cursor - 1)
    previous = handle.read(1)
    handle.seek(position)
    return previous == b"\n"


def _state(
    handle: BinaryIO,
    cursor: int,
    *,
    discard_until_newline: bool = False,
) -> str:
    file_stat = os.fstat(handle.fileno())
    if cursor < 0 or cursor > file_stat.st_size:
        raise LifecycleImportFailure("lifecycle cursor is outside the source")
    return json.dumps(
        {
            "version": _CURSOR_VERSION,
            "cursor": cursor,
            "device": file_stat.st_dev,
            "inode": file_stat.st_ino,
            "processed_digest": _region_digest(handle, 0, cursor),
            "discard_until_newline": discard_until_newline,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _nonnegative_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _load_cursor(saved: str) -> dict[str, object] | None:
    try:
        metadata = json.loads(saved)
    except (json.JSONDecodeError, TypeError):
        return None
    if (
        not isinstance(metadata, dict)
        or isinstance(metadata.get("version"), bool)
        or metadata.get("version") != _CURSOR_VERSION
    ):
        return None
    if _nonnegative_integer(metadata.get("cursor")) is None:
        return None
    if _nonnegative_integer(metadata.get("device")) is None:
        return None
    if _nonnegative_integer(metadata.get("inode")) is None:
        return None
    digest = metadata.get("processed_digest")
    if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
        return None
    if not isinstance(metadata.get("discard_until_newline"), bool):
        return None
    return metadata


def _empty_result(
    cursor: int,
    *,
    bootstrapped: bool = False,
    source_reset: bool = False,
    trailing_partial_ignored: bool = False,
) -> LifecycleImportResult:
    return LifecycleImportResult(
        applied=0,
        duplicates=0,
        quarantined=0,
        orphans=0,
        complete_records=0,
        cursor=cursor,
        bootstrapped=bootstrapped,
        source_reset=source_reset,
        trailing_partial_ignored=trailing_partial_ignored,
    )


def import_s012_lifecycle_jsonl(
    source: str | Path,
    store: LifecycleStore,
    *,
    backfill: bool = False,
) -> LifecycleImportResult:
    """Import complete lifecycle rows after the durable per-source cursor.

    First observation starts at EOF unless ``backfill`` is explicitly enabled.
    A changed/truncated source is never silently accepted: the saved cursor is
    left untouched and ``source_reset`` is reported until an explicit backfill
    establishes a new history.  Structurally invalid complete rows similarly
    pin the cursor at that row.  Recognized store outcomes are expected to be
    durable classifications, so quarantined and orphan rows can be audited
    without creating a signal or changing an immutable envelope.
    """

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise LifecycleImportFailure(
            f"lifecycle source is not a readable file: {path}"
        )
    key = _cursor_key(path)
    saved = store.get_state(key)

    try:
        handle_context = path.open("rb")
    except OSError as exc:
        raise LifecycleImportFailure(
            f"lifecycle source is not a readable file: {path}"
        ) from exc

    with handle_context as handle:
        file_stat = os.fstat(handle.fileno())
        size = file_stat.st_size
        if saved is None and not backfill:
            discard = not _is_line_boundary(handle, size)
            store.set_state(
                key,
                _state(handle, size, discard_until_newline=discard),
            )
            return _empty_result(
                size,
                bootstrapped=True,
                trailing_partial_ignored=discard,
            )

        metadata = _load_cursor(saved) if saved is not None else None
        if saved is not None and metadata is None and not backfill:
            return _empty_result(0, source_reset=True)

        if backfill:
            offset = 0
            discard_until_newline = False
        else:
            assert metadata is not None
            offset = int(metadata["cursor"])
            discard_until_newline = bool(metadata["discard_until_newline"])
            reset = (
                metadata["device"] != file_stat.st_dev
                or metadata["inode"] != file_stat.st_ino
                or offset > size
            )
            if not reset:
                try:
                    reset = not hmac.compare_digest(
                        str(metadata["processed_digest"]),
                        _region_digest(handle, 0, offset),
                    )
                except LifecycleImportFailure:
                    reset = True
            if not reset and not discard_until_newline:
                reset = not _is_line_boundary(handle, offset)
            if reset:
                return _empty_result(offset, source_reset=True)

        applied = duplicates = quarantined = orphans = complete_records = 0
        cursor = offset
        trailing_partial = False

        if discard_until_newline:
            handle.seek(offset)
            fragment = handle.readline(MAX_RECORD_BYTES + 1)
            if not fragment:
                return _empty_result(offset, trailing_partial_ignored=True)
            if len(fragment) > MAX_RECORD_BYTES:
                raise LifecycleImportFailure(
                    "discarded lifecycle fragment exceeds the record byte limit"
                )
            cursor = handle.tell()
            if not fragment.endswith(b"\n"):
                store.set_state(
                    key,
                    _state(handle, cursor, discard_until_newline=True),
                )
                return _empty_result(
                    cursor,
                    trailing_partial_ignored=True,
                )
            offset = cursor

        handle.seek(offset)
        while True:
            start = handle.tell()
            raw = handle.readline(MAX_RECORD_BYTES + 1)
            if not raw:
                break
            if len(raw) > MAX_RECORD_BYTES:
                store.set_state(key, _state(handle, start))
                raise LifecycleImportFailure(
                    f"lifecycle JSONL record exceeds {MAX_RECORD_BYTES} bytes "
                    f"at byte {start}"
                )
            if not raw.endswith(b"\n"):
                trailing_partial = True
                cursor = start
                break
            cursor = handle.tell()
            if not raw.strip():
                continue
            complete_records += 1
            try:
                event = validate_lifecycle_event(_decode_event(raw))
            except (LifecycleEventError, OverflowError, RecursionError) as exc:
                store.set_state(key, _state(handle, start))
                raise LifecycleImportFailure(
                    f"invalid complete lifecycle record at byte {start}: {exc}"
                ) from exc

            try:
                outcome = store.apply_signal_lifecycle(event)
            except Exception as exc:
                store.set_state(key, _state(handle, start))
                raise LifecycleImportFailure(
                    f"lifecycle store failed at byte {start}: {type(exc).__name__}"
                ) from exc
            if outcome not in _OUTCOMES:
                store.set_state(key, _state(handle, start))
                raise LifecycleImportFailure(
                    f"lifecycle store returned an invalid outcome at byte {start}"
                )
            if outcome == "applied":
                applied += 1
            elif outcome == "duplicate":
                duplicates += 1
            elif outcome == "quarantined":
                quarantined += 1
            else:
                orphans += 1

        store.set_state(key, _state(handle, cursor))
        return LifecycleImportResult(
            applied=applied,
            duplicates=duplicates,
            quarantined=quarantined,
            orphans=orphans,
            complete_records=complete_records,
            cursor=cursor,
            trailing_partial_ignored=trailing_partial,
        )
