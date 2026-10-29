"""Immutable local provenance records for KINGDOM research inputs.

The gateway intentionally does not fetch URLs.  Callers archive an exact,
bounded artifact themselves and pass its bytes here.  A content digest can
show that the same bytes were reviewed later; it cannot authenticate the
publisher, prove the statement true, or grant authority to trade.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Mapping


SCHEMA = "kingdom.observation/0.1"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
OBSERVATION_KINDS = frozenset(
    {
        "market_quote",
        "order_book",
        "primary_source",
        "resolution_rule",
        "catalyst",
        "outcome",
    }
)


class ObservationError(ValueError):
    """An observation failed the public provenance contract."""


class ObservationConflictError(ObservationError):
    """An existing observation identifier carried different content."""


def _bounded_text(value: object, limit: int, label: str) -> str:
    if not isinstance(value, str):
        raise ObservationError(f"{label} must be text")
    text = value.strip()
    if not text or "\x00" in text:
        raise ObservationError(f"{label} is required")
    try:
        encoded = text.encode("utf-8")
    except UnicodeError as exc:
        raise ObservationError(f"{label} must be valid UTF-8") from exc
    if len(encoded) > limit:
        raise ObservationError(f"{label} exceeds {limit} UTF-8 bytes")
    return text


def _utc(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ObservationError(f"{label} must be an ISO-8601 timestamp") from exc
    else:
        raise ObservationError(f"{label} must be an ISO-8601 timestamp")
    if parsed.tzinfo is None:
        raise ObservationError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _source_url(value: object) -> str:
    text = _bounded_text(value, 2_048, "source_url")
    try:
        parsed = urllib.parse.urlsplit(text)
        _ = parsed.port
    except ValueError:
        raise ObservationError("source_url is invalid") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ObservationError(
            "source_url must be HTTPS without credentials or a fragment"
        )
    return text


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ObservationError("observation is not canonical JSON") from exc


def build_observation(
    *,
    market_id: object,
    kind: object,
    statement: object,
    source_url: object,
    source_publisher: object,
    observed_at: object,
    captured_at: object,
    artifact: bytes,
    media_type: object = "application/octet-stream",
) -> dict[str, Any]:
    """Create one content-addressed, explicitly limited observation."""

    market = _bounded_text(market_id, 256, "market_id")
    observation_kind = _bounded_text(kind, 32, "kind").lower()
    if observation_kind not in OBSERVATION_KINDS:
        raise ObservationError("kind is not an allowed observation kind")
    claim = _bounded_text(statement, 2_000, "statement")
    publisher = _bounded_text(source_publisher, 256, "source_publisher")
    content_type = _bounded_text(media_type, 128, "media_type").lower()
    if not isinstance(artifact, bytes):
        raise ObservationError("artifact must be exact bytes")
    if not artifact:
        raise ObservationError("artifact must not be empty")
    if len(artifact) > MAX_ARTIFACT_BYTES:
        raise ObservationError(
            f"artifact exceeds the {MAX_ARTIFACT_BYTES}-byte limit"
        )
    observed = _utc(observed_at, "observed_at")
    captured = _utc(captured_at, "captured_at")
    if observed > captured:
        raise ObservationError("observed_at cannot be later than captured_at")

    body: dict[str, Any] = {
        "schema": SCHEMA,
        "market_id": market,
        "kind": observation_kind,
        "statement": claim,
        "observed_at": _iso(observed),
        "captured_at": _iso(captured),
        "source": {
            "url": _source_url(source_url),
            "publisher": publisher,
        },
        "artifact": {
            "sha256": hashlib.sha256(artifact).hexdigest(),
            "byte_length": len(artifact),
            "media_type": content_type,
        },
        "limitations": {
            "source_authenticated": False,
            "statement_proven": False,
            "artifact_stored_in_ledger": False,
            "notes": (
                "The digest binds this record to caller-supplied bytes. It does not "
                "prove where those bytes came from or that the statement is true."
            ),
        },
        "authority": {
            "mode": "information_only",
            "execution_allowed": False,
            "not_an_authorization": True,
        },
    }
    digest = hashlib.sha256(_canonical(body)).hexdigest()
    return {
        **body,
        "observation_id": "obs-" + digest[:32],
        "integrity": {
            "algorithm": "sha256",
            "record_digest": "sha256:" + digest,
            "proves_authorship": False,
            "proves_truth": False,
        },
    }


def validate_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a record by rebuilding its content-addressed identity."""

    if not isinstance(value, Mapping):
        raise ObservationError("observation must be a mapping")
    record = dict(value)
    if record.get("schema") != SCHEMA:
        raise ObservationError("unsupported observation schema")
    artifact = record.get("artifact")
    source = record.get("source")
    if not isinstance(artifact, Mapping) or not isinstance(source, Mapping):
        raise ObservationError("observation source and artifact are required")
    length = artifact.get("byte_length")
    if (
        isinstance(length, bool)
        or not isinstance(length, int)
        or not 1 <= length <= MAX_ARTIFACT_BYTES
    ):
        raise ObservationError("artifact byte_length is invalid")
    sha256 = artifact.get("sha256")
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(char not in "0123456789abcdef" for char in sha256)
    ):
        raise ObservationError("artifact sha256 is invalid")
    # Validate all externally controlled scalar values without needing the
    # original artifact bytes again.
    _bounded_text(record.get("market_id"), 256, "market_id")
    kind = _bounded_text(record.get("kind"), 32, "kind")
    if kind not in OBSERVATION_KINDS:
        raise ObservationError("kind is not an allowed observation kind")
    _bounded_text(record.get("statement"), 2_000, "statement")
    _source_url(source.get("url"))
    _bounded_text(source.get("publisher"), 256, "source_publisher")
    _bounded_text(artifact.get("media_type"), 128, "media_type")
    observed = _utc(record.get("observed_at"), "observed_at")
    captured = _utc(record.get("captured_at"), "captured_at")
    if observed > captured:
        raise ObservationError("observed_at cannot be later than captured_at")
    if record.get("authority") != {
        "mode": "information_only",
        "execution_allowed": False,
        "not_an_authorization": True,
    }:
        raise ObservationError("observation authority boundary is invalid")
    limitations = record.get("limitations")
    if not isinstance(limitations, Mapping) or any(
        limitations.get(field) is not False
        for field in (
            "source_authenticated",
            "statement_proven",
            "artifact_stored_in_ledger",
        )
    ):
        raise ObservationError("observation limitations are invalid")

    body = dict(record)
    observation_id = body.pop("observation_id", None)
    integrity = body.pop("integrity", None)
    digest = hashlib.sha256(_canonical(body)).hexdigest()
    expected_id = "obs-" + digest[:32]
    if observation_id != expected_id:
        raise ObservationError("observation ID does not match its content")
    if integrity != {
        "algorithm": "sha256",
        "record_digest": "sha256:" + digest,
        "proves_authorship": False,
        "proves_truth": False,
    }:
        raise ObservationError("observation integrity record is invalid")
    return record


class ObservationLedger:
    """Append-only observation index backed by an existing SQLite connection."""

    def __init__(self, connection: sqlite3.Connection):
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be sqlite3.Connection")
        self.conn = connection
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_observations (
                observation_id TEXT PRIMARY KEY,
                market_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                record_digest TEXT NOT NULL UNIQUE,
                record_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_research_observations_market
                ON research_observations(market_id, observed_at, observation_id);
            CREATE TRIGGER IF NOT EXISTS research_observations_no_update
            BEFORE UPDATE ON research_observations
            BEGIN
                SELECT RAISE(ABORT, 'research observations are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS research_observations_no_delete
            BEFORE DELETE ON research_observations
            BEGIN
                SELECT RAISE(ABORT, 'research observations are append-only');
            END;
            """
        )
        self.conn.commit()

    def append(self, observation: Mapping[str, Any]) -> bool:
        record = validate_observation(observation)
        serialized = _canonical(record).decode("utf-8")
        existing = self.conn.execute(
            """SELECT record_json FROM research_observations
               WHERE observation_id = ?""",
            (record["observation_id"],),
        ).fetchone()
        if existing is not None:
            existing_json = existing[0]
            if existing_json != serialized:
                raise ObservationConflictError(
                    "observation ID conflicts with stored content"
                )
            return False
        try:
            self.conn.execute(
                """INSERT INTO research_observations
                   (observation_id, market_id, kind, observed_at, captured_at,
                    record_digest, record_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["observation_id"],
                    record["market_id"],
                    record["kind"],
                    record["observed_at"],
                    record["captured_at"],
                    record["integrity"]["record_digest"],
                    serialized,
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            raise ObservationConflictError(
                "observation conflicts with stored content"
            ) from exc
        return True

    def get(self, observation_id: str) -> dict[str, Any] | None:
        identifier = _bounded_text(observation_id, 64, "observation_id")
        row = self.conn.execute(
            """SELECT record_json FROM research_observations
               WHERE observation_id = ?""",
            (identifier,),
        ).fetchone()
        if row is None:
            return None
        record = json.loads(str(row[0]))
        return validate_observation(record)

    def list_for_market(
        self, market_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        market = _bounded_text(market_id, 256, "market_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ObservationError("limit must be between 1 and 500")
        rows = self.conn.execute(
            """SELECT record_json FROM research_observations
               WHERE market_id = ?
               ORDER BY observed_at, observation_id LIMIT ?""",
            (market, limit),
        ).fetchall()
        return [validate_observation(json.loads(str(row[0]))) for row in rows]

    def summary(self) -> dict[str, Any]:
        rows = self.conn.execute(
            """SELECT kind, COUNT(*) AS count FROM research_observations
               GROUP BY kind ORDER BY kind"""
        ).fetchall()
        return {
            "schema": SCHEMA,
            "total": sum(int(row[1]) for row in rows),
            "by_kind": {str(row[0]): int(row[1]) for row in rows},
            "append_only": True,
            "execution_allowed": False,
        }
