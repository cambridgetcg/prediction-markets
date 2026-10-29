"""Incremental, append-only S012 JSONL import with a local cursor."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from .envelope import EnvelopeError, build_s012_envelope
from .store import GatewayStore


class ImportFailure(ValueError):
    """A complete source record could not be safely imported."""


MAX_RECORD_BYTES = 1_048_576


@dataclass(frozen=True)
class ImportResult:
    imported: int
    duplicates: int
    complete_records: int
    cursor: int
    bootstrapped: bool = False
    source_reset: bool = False
    trailing_partial_ignored: bool = False


def _cursor_key(path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24]
    return f"jsonl_cursor:{digest}"


def _region_digest(handle: BinaryIO, start: int, length: int) -> str:
    position = handle.tell()
    handle.seek(start)
    digest = hashlib.sha256(handle.read(length)).hexdigest()
    handle.seek(position)
    return digest


def _is_line_boundary(handle: BinaryIO, cursor: int) -> bool:
    if cursor == 0:
        return True
    position = handle.tell()
    handle.seek(cursor - 1)
    previous = handle.read(1)
    handle.seek(position)
    return previous == b"\n"


def _state(
    handle: BinaryIO, cursor: int, *, discard_until_newline: bool = False
) -> str:
    file_stat = os.fstat(handle.fileno())
    prefix_length = min(file_stat.st_size, 4096)
    anchor_end = min(cursor, file_stat.st_size)
    anchor_start = max(0, anchor_end - 4096)
    anchor_length = anchor_end - anchor_start
    return json.dumps(
        {
            "cursor": cursor,
            "device": file_stat.st_dev,
            "inode": file_stat.st_ino,
            "prefix_length": prefix_length,
            "prefix_digest": _region_digest(handle, 0, prefix_length),
            "anchor_start": anchor_start,
            "anchor_length": anchor_length,
            "anchor_digest": _region_digest(handle, anchor_start, anchor_length),
            "discard_until_newline": discard_until_newline,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def import_s012_jsonl(
    source: str | Path,
    store: GatewayStore,
    *,
    backfill: bool = False,
) -> ImportResult:
    """Import new complete lines.

    On first sight of a source, the safe default records the current end and
    imports nothing.  This prevents a newly configured bot from broadcasting
    a historical backlog.  ``backfill=True`` is an explicit local override.
    """

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise ImportFailure(f"signal source is not a readable file: {path}")
    key = _cursor_key(path)
    saved = store.get_state(key)
    with path.open("rb") as handle:
        file_stat = os.fstat(handle.fileno())
        size = file_stat.st_size
        if saved is None and not backfill:
            discard_until_newline = not _is_line_boundary(handle, size)
            store.set_state(
                key,
                _state(
                    handle,
                    size,
                    discard_until_newline=discard_until_newline,
                ),
            )
            return ImportResult(
                0,
                0,
                0,
                size,
                bootstrapped=True,
                trailing_partial_ignored=discard_until_newline,
            )

        metadata: dict[str, object]
        if saved is not None:
            try:
                decoded = json.loads(saved)
            except json.JSONDecodeError:
                decoded = int(saved) if saved.isdigit() else None
            if (
                isinstance(decoded, dict)
                and isinstance(decoded.get("cursor"), int)
                and not isinstance(decoded.get("cursor"), bool)
                and int(decoded["cursor"]) >= 0
            ):
                metadata = decoded
            elif isinstance(decoded, int) and not isinstance(decoded, bool) and decoded >= 0:
                metadata = {"cursor": decoded}
            elif not backfill:
                discard_until_newline = not _is_line_boundary(handle, size)
                store.set_state(
                    key,
                    _state(
                        handle,
                        size,
                        discard_until_newline=discard_until_newline,
                    ),
                )
                return ImportResult(
                    0,
                    0,
                    0,
                    size,
                    source_reset=True,
                    trailing_partial_ignored=discard_until_newline,
                )
            else:
                metadata = {}
        else:
            metadata = {}

        try:
            offset = 0 if backfill else int(metadata.get("cursor") or 0)
            prefix_length = int(metadata.get("prefix_length") or 0)
            anchor_start = int(metadata.get("anchor_start") or 0)
            anchor_length = int(metadata.get("anchor_length") or 0)
            discard_value = metadata.get("discard_until_newline", False)
            if not isinstance(discard_value, bool):
                raise ValueError("invalid cursor alignment state")
            discard_until_newline = False if backfill else discard_value
        except (OverflowError, TypeError, ValueError):
            if not backfill:
                discard_until_newline = not _is_line_boundary(handle, size)
                store.set_state(
                    key,
                    _state(
                        handle,
                        size,
                        discard_until_newline=discard_until_newline,
                    ),
                )
                return ImportResult(
                    0,
                    0,
                    0,
                    size,
                    source_reset=True,
                    trailing_partial_ignored=discard_until_newline,
                )
            offset = prefix_length = anchor_start = anchor_length = 0
            discard_until_newline = False

        fingerprint_changed = bool(metadata) and (
            (metadata.get("device") is not None and metadata.get("device") != file_stat.st_dev)
            or (metadata.get("inode") is not None and metadata.get("inode") != file_stat.st_ino)
        )
        if (
            prefix_length < 0
            or prefix_length > size
            or (
                prefix_length
                and metadata.get("prefix_digest")
                != _region_digest(handle, 0, prefix_length)
            )
            or anchor_start < 0
            or anchor_length < 0
            or anchor_start + anchor_length > size
            or (
                anchor_length
                and metadata.get("anchor_digest")
                != _region_digest(handle, anchor_start, anchor_length)
            )
        ):
            fingerprint_changed = True
        if (fingerprint_changed or offset < 0 or size < offset) and not backfill:
            # Observed replacement/truncation is not permission to replay a file.
            discard_until_newline = not _is_line_boundary(handle, size)
            store.set_state(
                key,
                _state(
                    handle,
                    size,
                    discard_until_newline=discard_until_newline,
                ),
            )
            return ImportResult(
                0,
                0,
                0,
                size,
                source_reset=True,
                trailing_partial_ignored=discard_until_newline,
            )

        imported = duplicates = complete_records = 0
        cursor = offset
        trailing_partial = False
        if discard_until_newline:
            # The first observation/reset landed inside a concurrent append.
            # That historical fragment is outside the no-backfill boundary, so
            # discard only through its eventual newline before parsing records.
            handle.seek(offset)
            fragment = handle.readline(MAX_RECORD_BYTES + 1)
            if not fragment:
                return ImportResult(0, 0, 0, offset)
            cursor = handle.tell()
            if not fragment.endswith(b"\n"):
                store.set_state(
                    key,
                    _state(handle, cursor, discard_until_newline=True),
                )
                return ImportResult(
                    0,
                    0,
                    0,
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
                raise ImportFailure(
                    f"S012 JSONL record exceeds {MAX_RECORD_BYTES} bytes at byte {start}"
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
                record: Any = json.loads(raw.decode("utf-8"))
                if not isinstance(record, Mapping):
                    raise EnvelopeError("S012 JSONL record must be an object")
                envelope = build_s012_envelope(
                    record,
                    observation_refs=record.get("observation_refs"),
                    resolution_rules_ref=record.get("resolution_rules_ref"),
                    model_ref=record.get("model_ref"),
                )
                if store.put_signal(envelope):
                    imported += 1
                else:
                    duplicates += 1
            except (
                OverflowError,
                RecursionError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                EnvelopeError,
                TypeError,
                ValueError,
            ) as exc:
                raise ImportFailure(
                    f"invalid complete JSONL record at byte {start}: {type(exc).__name__}"
                ) from exc

        store.set_state(key, _state(handle, cursor))
    return ImportResult(
        imported,
        duplicates,
        complete_records,
        cursor,
        trailing_partial_ignored=trailing_partial,
    )
