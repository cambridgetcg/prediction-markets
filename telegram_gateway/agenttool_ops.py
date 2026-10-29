"""Offline, privacy-minimizing AgentTool event projection and delivery queue.

This module is intentionally not a Collab client and not a Telegram client.  A
host adapter may give it already-fetched, read-only Collab event pages and later
deliver the resulting safe projections.  The adapter remains responsible for
fetching after the gateway's exact anchor and performing any external send.  It
does not need a Collab session credential or a Collab cursor acknowledgement.

The store persists only fixed-template projections.  It never persists raw
task/report bodies, prompts, actor labels, paths, artifact URIs, or session
identifiers.  Coordination state is described as observed state; it is not
identity, health, consent, truth, ownership, or action authority.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import os
import re
import secrets
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping


MAX_PAGE_EVENTS = 50
ZERO_HASH = "0" * 64
OPS_DATABASE_ROLE = "kingdom.telegram.agenttool_ops/v2"
OPS_V1_DATABASE_ROLE = "kingdom.telegram.agenttool_ops/v1"
TELEGRAM_PRODUCTION_ORIGIN = "https://api.telegram.org"
OPS_CREDENTIAL_PREFIX = "keychain:dev.kingdom.prediction-markets.telegram-ops-bot-token:"
# Telegram retains updates for at most 24 hours. After a full idle retention
# window no previously processed update can still be queued; reset BEFORE using
# an old offset, which could discard a randomized post-idle update ID.
POLL_EPOCH_IDLE_SECONDS = 86_401
OPS_DATABASE_ROLE_META_KEY = "database_role"

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_EVENT_KEY = re.compile(r"evt_[0-9a-f]{32}\Z")
_OPAQUE_REF = re.compile(r"[a-z]{3}_[0-9a-f]{24}\Z")
_MACHINE_LABEL = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_WORKSPACE_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")
_SAFE_BOUNDARY = (
    "Observed coordination state only; not identity, availability, consent, "
    "truth, ownership, or action authority."
)
# SHA-256 of the canonical non-internal sqlite_schema objects created below.
# A schema change requires a new database role version and digest together.
_OPS_V1_SCHEMA_DIGEST = (
    "61a36aaeb70489cb53d2cd18b6c207102b7c22438dedf5bc849cdbe342482697"
)
_OPS_SCHEMA_DIGEST = "49e6f573d65f4ddd8466f65775be5d9eae9b85a5ab9dbdacb5097571b6374de9"
_OPS_V1_SCHEMA_OBJECTS = frozenset(
    {
        ("index", "idx_ops_outbox_state", "ops_outbox"),
        ("index", "idx_safe_events_sequence", "safe_events"),
        ("table", "cursor_pages", "cursor_pages"),
        ("table", "cursor_state", "cursor_state"),
        ("table", "journal_verification", "journal_verification"),
        ("table", "ops_meta", "ops_meta"),
        ("table", "ops_outbox", "ops_outbox"),
        ("table", "safe_events", "safe_events"),
        ("table", "safe_sessions", "safe_sessions"),
        ("table", "safe_tasks", "safe_tasks"),
        ("table", "telegram_updates", "telegram_updates"),
    }
)
_OPS_META_KEYS = frozenset(
    {OPS_DATABASE_ROLE_META_KEY, "opaque_key", "workspace_alias"}
)
_OPS_SCHEMA_OBJECTS = _OPS_V1_SCHEMA_OBJECTS | frozenset(
    {
        ("table", "ops_bindings", "ops_bindings"),
        ("table", "ops_transport", "ops_transport"),
        ("table", "ops_poll_epochs", "ops_poll_epochs"),
        ("table", "ops_update_dispositions", "ops_update_dispositions"),
        ("table", "ops_replies", "ops_replies"),
        ("table", "ops_reply_attempts", "ops_reply_attempts"),
        ("table", "ops_reply_reconciliations", "ops_reply_reconciliations"),
        ("index", "idx_ops_replies_state", "ops_replies"),
    }
)
# Additive v2 migration: the v1 projection, cursor, event-delivery evidence and
# legacy update claims remain byte-for-byte values in their original tables.
_OPS_V2_SCHEMA = """
CREATE TABLE ops_bindings (
    revision INTEGER PRIMARY KEY CHECK (revision > 0),
    bot_id INTEGER NOT NULL CHECK (bot_id > 0 AND bot_id <= 4503599627370495),
    operator_user_id INTEGER NOT NULL CHECK (operator_user_id > 0),
    operator_private_chat_id INTEGER NOT NULL CHECK (
        operator_private_chat_id = operator_user_id
        AND operator_private_chat_id <= 4503599627370495
    ),
    api_origin TEXT NOT NULL,
    credential_ref TEXT NOT NULL,
    source_binding TEXT NOT NULL,
    verification TEXT NOT NULL CHECK (verification IN ('verified', 'fixture')),
    bound_at TEXT NOT NULL,
    accept_after INTEGER NOT NULL CHECK (accept_after >= 0)
);
CREATE TABLE ops_poll_epochs (
    epoch INTEGER PRIMARY KEY CHECK (epoch > 0),
    binding_revision INTEGER NOT NULL REFERENCES ops_bindings(revision),
    started_at TEXT NOT NULL,
    last_update_at TEXT NOT NULL,
    next_offset INTEGER CHECK (next_offset >= 0 AND next_offset <= 2147483648)
);
CREATE TABLE ops_transport (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    binding_revision INTEGER NOT NULL REFERENCES ops_bindings(revision),
    state TEXT NOT NULL CHECK (state IN ('active', 'paused')),
    polling_epoch INTEGER NOT NULL REFERENCES ops_poll_epochs(epoch)
);
CREATE TABLE ops_update_dispositions (
    polling_epoch INTEGER NOT NULL REFERENCES ops_poll_epochs(epoch),
    update_id INTEGER NOT NULL CHECK (update_id >= 0 AND update_id <= 2147483647),
    disposition TEXT NOT NULL CHECK (
        disposition IN ('reply', 'ignored', 'withdrawn', 'historical_incomplete')
    ),
    reply_id TEXT UNIQUE,
    processed_at TEXT NOT NULL,
    PRIMARY KEY (polling_epoch, update_id),
    CHECK ((disposition = 'reply' AND reply_id IS NOT NULL)
        OR (disposition != 'reply' AND reply_id IS NULL))
);
CREATE TABLE ops_replies (
    reply_id TEXT PRIMARY KEY,
    polling_epoch INTEGER NOT NULL,
    update_id INTEGER NOT NULL,
    binding_revision INTEGER NOT NULL REFERENCES ops_bindings(revision),
    payload_text TEXT NOT NULL CHECK (length(payload_text) BETWEEN 1 AND 3800),
    payload_digest TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('pending', 'inflight', 'sent', 'failed', 'unknown', 'invalidated')
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    queued_at TEXT NOT NULL,
    receipt_ref TEXT,
    error_code TEXT,
    UNIQUE (polling_epoch, update_id),
    FOREIGN KEY (polling_epoch, update_id)
        REFERENCES ops_update_dispositions(polling_epoch, update_id)
);
CREATE INDEX idx_ops_replies_state ON ops_replies(state, queued_at, reply_id);
CREATE TABLE ops_reply_attempts (
    reply_id TEXT NOT NULL REFERENCES ops_replies(reply_id),
    attempt_count INTEGER NOT NULL CHECK (attempt_count > 0),
    state TEXT NOT NULL CHECK (state IN ('inflight', 'sent', 'failed', 'unknown')),
    attempted_at TEXT NOT NULL,
    finished_at TEXT,
    receipt_ref TEXT,
    error_code TEXT,
    PRIMARY KEY (reply_id, attempt_count)
);
CREATE TABLE ops_reply_reconciliations (
    observation_id INTEGER PRIMARY KEY,
    reply_id TEXT NOT NULL,
    attempt_count INTEGER NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('sent', 'failed', 'unknown')),
    reconciliation_ref TEXT NOT NULL CHECK (length(reconciliation_ref) > 0),
    receipt_ref TEXT,
    reconciled_at TEXT NOT NULL,
    FOREIGN KEY (reply_id, attempt_count)
        REFERENCES ops_reply_attempts(reply_id, attempt_count)
);
"""
_REPLY_ID = re.compile(r"rpl_[0-9a-f]{32}\Z")
_CREDENTIAL_ACCOUNT = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
REPLY_ERROR_CODES = frozenset(
    {"telegram_rejected", "telegram_timeout", "telegram_transport", "invalid_receipt",
     "interrupted", "paused", "forbidden", "rate_limited"}
)


class OpsProjectionError(ValueError):
    """A Collab event cannot be represented by the safe projection contract."""


class CursorStateError(RuntimeError):
    """The local page stage is inconsistent with its exact cursor anchors."""


class ProjectionConflict(RuntimeError):
    """A deterministic event identity was reused with different safe content."""


class DeliveryStateError(RuntimeError):
    """An outbox delivery needs explicit reconciliation or review."""


class DatabaseRoleError(RuntimeError):
    """A SQLite file is not the exact database role owned by this store."""


def _timestamp(value: datetime | str | None = None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp is invalid") from exc
    else:
        raise ValueError("timestamp must be an ISO-8601 value")
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _bounded_text(value: Any, *, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise OpsProjectionError(f"{label} is invalid")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise OpsProjectionError(f"{label} is invalid") from exc
    if len(encoded) > limit:
        raise OpsProjectionError(f"{label} is invalid")
    return value


def _check_hash(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise OpsProjectionError(f"{label} is invalid")
    return value


def _check_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) < 32:
        raise ValueError("opaque_key must contain at least 32 bytes")
    return key


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _schema_digest(conn: sqlite3.Connection) -> str:
    """Fingerprint every non-internal schema object without exposing its SQL."""

    try:
        identity_rows = conn.execute(
            """SELECT type, name, tbl_name
               FROM sqlite_schema
               WHERE substr(lower(name), 1, 7) != 'sqlite_'"""
        ).fetchall()
        identities = {
            (str(row[0]), str(row[1]), str(row[2])) for row in identity_rows
        }
        if identities not in (_OPS_V1_SCHEMA_OBJECTS, _OPS_SCHEMA_OBJECTS):
            raise DatabaseRoleError(
                "database is not an exact AgentTool Ops store"
            )
        rows = conn.execute(
            """SELECT type, name, tbl_name, sql
               FROM sqlite_schema
               WHERE substr(lower(name), 1, 7) != 'sqlite_'
               ORDER BY type, name"""
        ).fetchall()
    except sqlite3.DatabaseError:
        raise DatabaseRoleError(
            "database is not an exact AgentTool Ops store"
        ) from None
    objects = [
        {
            "name": str(row[1]),
            "sql": " ".join(str(row[3] or "").split()),
            "table": str(row[2]),
            "type": str(row[0]),
        }
        for row in rows
    ]
    encoded = json.dumps(
        objects, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _role_state(conn: sqlite3.Connection) -> str:
    """Validate bounded metadata and return the exact role marker, or legacy."""

    try:
        rows = conn.execute("SELECT key, value FROM ops_meta ORDER BY key").fetchall()
    except sqlite3.DatabaseError:
        raise DatabaseRoleError(
            "database is not an exact AgentTool Ops store"
        ) from None
    metadata: dict[str, Any] = {}
    for row in rows:
        key = row[0]
        if not isinstance(key, str) or key not in _OPS_META_KEYS:
            raise DatabaseRoleError(
                "database is not an exact AgentTool Ops store"
            )
        metadata[key] = row[1]
    if "opaque_key" in metadata:
        opaque_key = metadata["opaque_key"]
        if (
            not isinstance(opaque_key, (bytes, bytearray, memoryview))
            or len(opaque_key) < 32
        ):
            raise DatabaseRoleError(
                "database is not an exact AgentTool Ops store"
            )
    if "workspace_alias" in metadata:
        alias = metadata["workspace_alias"]
        try:
            decoded_alias = bytes(alias).decode("utf-8")
        except (TypeError, UnicodeError):
            raise DatabaseRoleError(
                "database is not an exact AgentTool Ops store"
            ) from None
        if _WORKSPACE_ALIAS.fullmatch(decoded_alias) is None:
            raise DatabaseRoleError(
                "database is not an exact AgentTool Ops store"
            )
    if OPS_DATABASE_ROLE_META_KEY not in metadata:
        return "legacy"
    marker = metadata[OPS_DATABASE_ROLE_META_KEY]
    if not isinstance(marker, (bytes, bytearray, memoryview)):
        raise DatabaseRoleError("database is not an exact AgentTool Ops store")
    for role, state in ((OPS_DATABASE_ROLE, "current"), (OPS_V1_DATABASE_ROLE, "v1")):
        if hmac.compare_digest(bytes(marker), role.encode("ascii")):
            return state
    raise DatabaseRoleError("database is not an exact AgentTool Ops store")


def _database_version(conn: sqlite3.Connection) -> Literal["current", "v1"]:
    digest, role = _schema_digest(conn), _role_state(conn)
    keys = {row[0] for row in conn.execute("SELECT key FROM ops_meta")}
    if not {"opaque_key", "workspace_alias"} <= keys:
        raise DatabaseRoleError("database is missing its Ops projection metadata")
    if digest == _OPS_SCHEMA_DIGEST and role == "current":
        return "current"
    if digest == _OPS_V1_SCHEMA_DIGEST and role in {"v1", "legacy"}:
        return "v1"
    raise DatabaseRoleError("database is not an exact AgentTool Ops store")


def _inspect_existing_database(path: Path) -> Literal["current", "v1"]:
    """Classify a non-empty file through a non-mutating SQLite connection."""

    uri = path.as_uri() + "?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        raise DatabaseRoleError(
            "database is not an exact AgentTool Ops store"
        ) from None
    try:
        return _database_version(conn)
    finally:
        conn.close()


class MigrationRequiredError(DatabaseRoleError):
    """An exact v1 store requires the explicit preview/apply migration."""


class BindingStateError(DeliveryStateError):
    """The immutable operator/provider binding is missing, paused or mismatched."""


@dataclass(frozen=True)
class OpsBinding:
    revision: int
    bot_id: int
    operator_user_id: int
    operator_private_chat_id: int
    api_origin: str
    credential_ref: str
    source_binding: str
    verification: str
    bound_at: str
    accept_after: int


@dataclass(frozen=True)
class PollState:
    epoch: int
    binding_revision: int
    next_offset: int | None
    last_update_at: str
    state: str


@dataclass(frozen=True)
class UpdateDisposition:
    polling_epoch: int
    update_id: int
    disposition: str
    reply_id: str | None
    duplicate: bool = False


@dataclass(frozen=True)
class ReplyItem:
    reply_id: str
    polling_epoch: int
    update_id: int
    binding: OpsBinding
    text: str
    payload_digest: str
    state: str
    attempt_count: int
    receipt_ref: str | None
    error_code: str | None

    @property
    def binding_revision(self) -> int:
        return self.binding.revision

    @property
    def chat_id(self) -> int:
        return self.binding.operator_private_chat_id

    @property
    def protect_content(self) -> bool:
        return True


@dataclass(frozen=True)
class CursorAnchor:
    """An exact internal Collab epoch/sequence/hash anchor.

    Anchors are persisted for recovery but are not included in Telegram-safe
    projections.  Hash-chain validity detects changes; it does not authenticate
    an actor or prove the recorded claims true.
    """

    epoch_id: str
    sequence: int
    hash: str

    def __post_init__(self) -> None:
        _bounded_text(self.epoch_id, label="epoch_id", limit=160)
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise OpsProjectionError("cursor sequence is invalid")
        _check_hash(self.hash, label="cursor hash")

    @classmethod
    def genesis(cls, epoch_id: str) -> "CursorAnchor":
        return cls(epoch_id=epoch_id, sequence=0, hash=ZERO_HASH)


@dataclass(frozen=True)
class SafeEventProjection:
    """A fixed-schema event view suitable for an owner-only status console."""

    event_key: str
    subject_ref: str
    workspace_alias: str
    sequence: int
    event_kind: str
    state: str
    observed_at: str
    summary: str
    boundary: str = _SAFE_BOUNDARY

    def __post_init__(self) -> None:
        if _EVENT_KEY.fullmatch(self.event_key) is None:
            raise OpsProjectionError("projected event_key is invalid")
        if _OPAQUE_REF.fullmatch(self.subject_ref) is None:
            raise OpsProjectionError("projected subject_ref is invalid")
        if _WORKSPACE_ALIAS.fullmatch(self.workspace_alias) is None:
            raise OpsProjectionError("projected workspace_alias is invalid")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise OpsProjectionError("projected sequence is invalid")
        allowed = set(_EVENT_TEMPLATES.values())
        allowed.add(
            (
                "coordination.event",
                "event",
                "observed",
                "A coordination event was observed; its unrecognized details were not projected.",
            )
        )
        if (self.event_kind, self.subject_ref[:3], self.state, self.summary) not in {
            (kind, _OPAQUE_PREFIX[namespace], state, summary)
            for kind, namespace, state, summary in allowed
        }:
            raise OpsProjectionError("projected event template is invalid")
        canonical_observed_at = _timestamp(self.observed_at)
        if canonical_observed_at != self.observed_at:
            raise OpsProjectionError("projected observed_at is not canonical")
        if self.boundary != _SAFE_BOUNDARY:
            raise OpsProjectionError("projected boundary is invalid")

    def as_dict(self) -> dict[str, Any]:
        return {
            "boundary": self.boundary,
            "event_key": self.event_key,
            "event_kind": self.event_kind,
            "observed_at": self.observed_at,
            "sequence": self.sequence,
            "state": self.state,
            "subject_ref": self.subject_ref,
            "summary": self.summary,
            "workspace_alias": self.workspace_alias,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SafeEventProjection":
        expected = {
            "boundary",
            "event_key",
            "event_kind",
            "observed_at",
            "sequence",
            "state",
            "subject_ref",
            "summary",
            "workspace_alias",
        }
        if set(value) != expected:
            raise ProjectionConflict("stored projection schema is invalid")
        string_fields = expected - {"sequence"}
        if any(not isinstance(value[name], str) for name in string_fields):
            raise ProjectionConflict("stored projection field type is invalid")
        if isinstance(value["sequence"], bool) or not isinstance(
            value["sequence"], int
        ):
            raise ProjectionConflict("stored projection sequence type is invalid")
        return cls(
            event_key=value["event_key"],
            subject_ref=value["subject_ref"],
            workspace_alias=value["workspace_alias"],
            sequence=value["sequence"],
            event_kind=value["event_kind"],
            state=value["state"],
            observed_at=value["observed_at"],
            summary=value["summary"],
            boundary=value["boundary"],
        )


@dataclass(frozen=True)
class PageStage:
    anchor: CursorAnchor
    event_count: int
    enqueued_count: int
    state: Literal["staged", "committed"]
    duplicate: bool = False


@dataclass(frozen=True)
class CursorCommit:
    anchor: CursorAnchor
    duplicate: bool = False


@dataclass(frozen=True)
class OutboxItem:
    event_key: str
    projection: SafeEventProjection
    state: str
    attempt_count: int
    receipt_ref: str | None
    error_code: str | None
    duplicate: bool = False


_EVENT_TEMPLATES: dict[str, tuple[str, str, str, str]] = {
    "workspace.opened": (
        "workspace.opened", "workspace", "observed",
        "A coordination workspace journal was observed.",
    ),
    "worktree.registered": (
        "worktree.registered", "workspace", "observed",
        "A worktree coordination record was observed; no local path was projected.",
    ),
    "session.joined": (
        "session.joined", "session", "observed_active",
        "A coordination or self-declared presence session record was observed as joined.",
    ),
    "session.resumed": (
        "session.resumed", "session", "observed_active",
        "A coordination session was observed as resumed.",
    ),
    "session.heartbeat": (
        "session.heartbeat", "session", "routing_hint_observed",
        "A self-declared presence heartbeat was observed as a routing hint only.",
    ),
    "session.ended": (
        "session.ended", "session", "observed_ended",
        "A coordination session was observed as ended.",
    ),
    "session.cursor_reset": (
        "session.cursor_reset", "session", "cursor_reset_recorded",
        "An audited coordination cursor reset was observed.",
    ),
    "task.created": (
        "task.created", "task", "open",
        "A coordination task was recorded as open.",
    ),
    "task.claimed": (
        "task.claimed", "task", "claimed",
        "An advisory task lease was observed; it is not ownership or action authority.",
    ),
    "task.recovered": (
        "task.recovered", "task", "recovery_recorded",
        "An evidence-aware advisory task recovery was observed; its resulting state is separately projected only when explicit.",
    ),
    "task.claim_expired": (
        "task.claim_expired", "task", "open",
        "An advisory task claim was observed as expired and returned to the open pool.",
    ),
    "task.lease_renewed": (
        "task.lease_renewed", "task", "claimed",
        "An advisory task lease renewal was observed.",
    ),
    "task.progressed": (
        "task.progressed", "task", "progress_recorded",
        "A bounded task progress record was appended.",
    ),
    "task.released": (
        "task.released", "task", "open",
        "An advisory task lease was observed as released.",
    ),
    "task.blocked": (
        "task.blocked", "task", "blocked",
        "A coordination task was observed as blocked.",
    ),
    "task.unblocked": (
        "task.unblocked", "task", "open",
        "A coordination task was observed as returned to the open pool.",
    ),
    "task.completed": (
        "task.completed", "task", "completed",
        "A reported-only task was recorded complete; this is not external acceptance or execution authority.",
    ),
    "task.reported_complete": (
        "task.reported_complete", "task", "reported_complete",
        "Work was reported complete pending distinct-session review; its correctness is not thereby proven.",
    ),
    "task.accepted": (
        "task.accepted", "task", "completed",
        "A distinct-session coordination acceptance was recorded; it is not merge, deployment, truth, or external authority.",
    ),
    "task.changes_requested": (
        "task.changes_requested", "task", "open",
        "A distinct-session coordination review requested changes and returned the task to open.",
    ),
    "artifact.attached": (
        "artifact.attached", "task", "reference_recorded",
        "An evidence reference was recorded; its underlying content was not projected.",
    ),
    "report.posted": (
        "report.posted", "report", "appended",
        "A report was appended to the coordination journal; its claims are not thereby proven.",
    ),
    "decision.recorded": (
        "decision.recorded", "report", "decision_recorded",
        "A scoped decision record was appended; its authority basis was not projected.",
    ),
    "handoff.offered": (
        "handoff.offered", "handoff", "offered",
        "A refusable task handoff was observed as offered.",
    ),
    "handoff.accepted": (
        "handoff.accepted", "handoff", "accepted",
        "A handoff lease transfer was observed; no external authority was transferred.",
    ),
    "handoff.declined": (
        "handoff.declined", "handoff", "declined",
        "A task handoff was observed as declined.",
    ),
    "handoff.expired": (
        "handoff.expired", "handoff", "expired",
        "A task handoff offer was observed as expired.",
    ),
}

_OPAQUE_PREFIX = {
    "artifact": "art",
    "event": "evt",
    "handoff": "hnd",
    "report": "rpt",
    "session": "ses",
    "task": "tsk",
    "workspace": "wsp",
}


def _opaque_ref(key: bytes, namespace: str, raw_value: str, *, size: int) -> str:
    digest = hmac.new(
        key,
        f"kingdom-agenttool-ops/v1\0{namespace}\0{raw_value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    prefix = _OPAQUE_PREFIX.get(namespace, "obj")
    return f"{prefix}_{digest[:size]}"


def project_collab_event(
    event: Mapping[str, Any],
    *,
    opaque_key: bytes,
    workspace_alias: str = "kingdom_ops",
) -> SafeEventProjection:
    """Convert one journal event to a deterministic fixed-template projection.

    Raw payload content is deliberately ignored.  The event hash influences the
    opaque event key, so a changed journal record produces a different identity
    without copying the changed content into the projection.
    """

    if not isinstance(event, Mapping):
        raise OpsProjectionError("event must be a mapping")
    key = _check_key(opaque_key)
    if not isinstance(workspace_alias, str) or _WORKSPACE_ALIAS.fullmatch(
        workspace_alias
    ) is None:
        raise ValueError("workspace_alias is invalid")
    epoch_id = _bounded_text(event.get("epoch_id"), label="event epoch", limit=160)
    sequence = event.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        raise OpsProjectionError("event sequence is invalid")
    event_hash = _check_hash(event.get("hash"), label="event hash")
    event_type = _bounded_text(event.get("type"), label="event type", limit=96)
    entity_id = _bounded_text(event.get("entity_id"), label="entity_id", limit=512)
    observed_at = _timestamp(
        _bounded_text(event.get("occurred_at"), label="occurred_at", limit=64)
    )

    event_kind, namespace, state, summary = _EVENT_TEMPLATES.get(
        event_type,
        (
            "coordination.event",
            "event",
            "observed",
            "A coordination event was observed; its unrecognized details were not projected.",
        ),
    )
    coordinate = f"{epoch_id}\0{sequence}\0{event_hash}"
    return SafeEventProjection(
        event_key=_opaque_ref(key, "event", coordinate, size=32),
        subject_ref=_opaque_ref(key, namespace, entity_id, size=24),
        workspace_alias=workspace_alias,
        sequence=sequence,
        event_kind=event_kind,
        state=state,
        observed_at=observed_at,
        summary=summary,
    )


class AgentToolOpsStore:
    """Owner-only SQLite staging ledger and safe-projection outbox.

    A non-empty database is opened read-only and must match both the exact Ops
    schema and fixed role marker before this class may enable WAL, change modes,
    or run schema initialization. Exact marked or pre-marker v1 stores require
    ``preview_migration`` followed by explicit ``migrate_v1``; opening a store
    never migrates it. New state has the exact v2 role/schema manifest.
    The marker prevents accidental database-role mixing; it is not an
    authenticity proof or authority grant against another local writer.

    ``stage_page`` durably writes projections and an exact terminal anchor.  The
    host then commits that same locally verified returned-page anchor.  A crash
    between those operations leaves the staged anchor visible for explicit
    recovery and never silently skips a page.  This cursor belongs to the
    gateway; no Collab session cursor is read or acknowledged.  Delivery is
    separate: committing a cursor means the event is durably queued, not that
    Telegram received it.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        workspace_alias: str = "kingdom_ops",
        opaque_key: bytes | None = None,
    ):
        if not isinstance(workspace_alias, str) or _WORKSPACE_ALIAS.fullmatch(
            workspace_alias
        ) is None:
            raise ValueError("workspace_alias is invalid")
        if opaque_key is not None:
            _check_key(opaque_key)
        try:
            requested_path = Path(db_path).expanduser().absolute()
            if any(Path(str(requested_path) + suffix).is_symlink() for suffix in ("", "-wal", "-shm")):
                raise PermissionError("AgentTool Ops state must not use symlinks")
            self.path = requested_path.resolve()
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            parent_mode = stat.S_IMODE(self.path.parent.stat().st_mode)
        except (OSError, RuntimeError):
            raise PermissionError(
                "AgentTool Ops directory could not be prepared securely"
            ) from None
        if parent_mode & 0o077:
            raise PermissionError(
                "AgentTool Ops directory must be owner-only (0700)"
            )

        database_state: Literal["fresh", "current", "v1"]
        try:
            existing = self.path.stat()
        except FileNotFoundError:
            try:
                descriptor = os.open(
                    self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                )
                os.close(descriptor)
                existing = self.path.stat()
            except OSError:
                raise PermissionError(
                    "AgentTool Ops state could not be created securely"
                ) from None
            database_state = "fresh"
        except OSError:
            raise PermissionError(
                "AgentTool Ops state could not be inspected securely"
            ) from None
        else:
            if not stat.S_ISREG(existing.st_mode):
                raise DatabaseRoleError(
                    "database is not an exact AgentTool Ops store"
                )
            database_state = (
                _inspect_existing_database(self.path)
                if existing.st_size > 0
                else "fresh"
            )

        if database_state == "v1":
            raise MigrationRequiredError(
                "exact Ops v1 store requires preview_migration and migrate_v1"
            )
        if not stat.S_ISREG(existing.st_mode):
            raise DatabaseRoleError("database is not an exact AgentTool Ops store")
        file_identity = (existing.st_dev, existing.st_ino)
        candidate: sqlite3.Connection | None = None
        try:
            candidate = sqlite3.connect(str(self.path), isolation_level=None)
            candidate.row_factory = sqlite3.Row
            reopened = self.path.stat()
            if (reopened.st_dev, reopened.st_ino) != file_identity:
                raise DatabaseRoleError(
                    "database changed while its Ops role was being checked"
                )
            if database_state == "fresh":
                if candidate.execute(
                    """SELECT 1 FROM sqlite_schema
                       WHERE substr(lower(name), 1, 7) != 'sqlite_'
                       LIMIT 1"""
                ).fetchone() is not None:
                    raise DatabaseRoleError(
                        "database is not an exact AgentTool Ops store"
                    )
            else:
                if _database_version(candidate) != "current":
                    raise DatabaseRoleError(
                        "database is not an exact AgentTool Ops store"
                    )
        except (OSError, sqlite3.Error):
            if candidate is not None:
                candidate.close()
            raise DatabaseRoleError(
                "database could not be safely validated for the AgentTool Ops role"
            ) from None
        except BaseException:
            if candidate is not None:
                candidate.close()
            raise

        assert candidate is not None
        self.conn = candidate
        try:
            self._secure_files()
        except BaseException:
            self.conn.close()
            raise
        self.conn.execute("PRAGMA busy_timeout=2000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA secure_delete=ON")
        v1_schema = (
            """
            CREATE TABLE IF NOT EXISTS ops_meta (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cursor_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                committed_epoch TEXT NOT NULL,
                committed_sequence INTEGER NOT NULL CHECK (committed_sequence >= 0),
                committed_hash TEXT NOT NULL,
                staged_epoch TEXT,
                staged_sequence INTEGER,
                staged_hash TEXT,
                staged_page_digest TEXT,
                CHECK (
                    (staged_epoch IS NULL AND staged_sequence IS NULL
                     AND staged_hash IS NULL AND staged_page_digest IS NULL)
                    OR
                    (staged_epoch IS NOT NULL AND staged_sequence IS NOT NULL
                     AND staged_hash IS NOT NULL AND staged_page_digest IS NOT NULL)
                )
            );

            CREATE TABLE IF NOT EXISTS cursor_pages (
                epoch_id TEXT NOT NULL,
                terminal_sequence INTEGER NOT NULL CHECK (terminal_sequence >= 0),
                terminal_hash TEXT NOT NULL,
                initial_epoch TEXT NOT NULL,
                initial_sequence INTEGER NOT NULL CHECK (initial_sequence >= 0),
                initial_hash TEXT NOT NULL,
                page_digest TEXT NOT NULL,
                event_count INTEGER NOT NULL CHECK (event_count >= 0),
                state TEXT NOT NULL CHECK (state IN ('staged', 'committed')),
                staged_at TEXT NOT NULL,
                committed_at TEXT,
                PRIMARY KEY (epoch_id, terminal_sequence, terminal_hash)
            );

            CREATE TABLE IF NOT EXISTS safe_events (
                event_key TEXT PRIMARY KEY,
                epoch_id TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK (sequence > 0),
                event_hash TEXT NOT NULL,
                projection_json TEXT NOT NULL,
                projection_digest TEXT NOT NULL,
                staged_at TEXT NOT NULL,
                UNIQUE (epoch_id, sequence),
                UNIQUE (epoch_id, event_hash)
            );

            CREATE TABLE IF NOT EXISTS safe_tasks (
                task_ref TEXT PRIMARY KEY,
                state TEXT NOT NULL CHECK (
                    state IN ('open', 'claimed', 'blocked',
                              'reported_complete', 'completed', 'unknown')
                ),
                version INTEGER NOT NULL CHECK (version > 0),
                review_state TEXT NOT NULL CHECK (
                    review_state IN ('not_required', 'pending', 'accepted',
                                     'changes_requested', 'unknown')
                ),
                coordination_lease_recorded INTEGER NOT NULL
                    CHECK (coordination_lease_recorded IN (0, 1)),
                safe_summary TEXT NOT NULL,
                evidence_reference_count INTEGER NOT NULL DEFAULT 0
                    CHECK (evidence_reference_count >= 0),
                last_observed_at TEXT NOT NULL,
                last_sequence INTEGER NOT NULL CHECK (last_sequence > 0)
            );

            CREATE TABLE IF NOT EXISTS safe_sessions (
                session_ref TEXT PRIMARY KEY,
                recorded_active INTEGER NOT NULL CHECK (recorded_active IN (0, 1)),
                last_observed_at TEXT NOT NULL,
                last_sequence INTEGER NOT NULL CHECK (last_sequence > 0)
            );

            CREATE TABLE IF NOT EXISTS ops_outbox (
                event_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                state TEXT NOT NULL CHECK (
                    state IN ('pending', 'inflight', 'sent', 'failed', 'unknown')
                ),
                attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                queued_at TEXT NOT NULL,
                last_attempted_at TEXT,
                finished_at TEXT,
                receipt_ref TEXT,
                error_code TEXT,
                reconciled_at TEXT,
                reconciliation_ref TEXT,
                FOREIGN KEY (event_key) REFERENCES safe_events(event_key)
                    ON DELETE RESTRICT
            );

            CREATE INDEX IF NOT EXISTS idx_ops_outbox_state
                ON ops_outbox(state, queued_at, event_key);
            CREATE INDEX IF NOT EXISTS idx_safe_events_sequence
                ON safe_events(sequence DESC);

            CREATE TABLE IF NOT EXISTS telegram_updates (
                update_id INTEGER PRIMARY KEY CHECK (
                    update_id >= 0 AND update_id <= 2147483647
                ),
                claimed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS journal_verification (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                outcome TEXT NOT NULL CHECK (
                    outcome IN ('valid', 'invalid', 'unavailable')
                ),
                checked_at TEXT NOT NULL,
                journal_head_sequence INTEGER,
                scope_code TEXT NOT NULL CHECK (
                    scope_code IN ('full_collab_hash_chain',
                                   'full_collab_hash_chain_unavailable')
                ),
                CHECK (journal_head_sequence IS NULL
                       OR journal_head_sequence >= 0)
            );
            """
        )
        try:
            if database_state == "fresh":
                # Every schema object and required metadata value belongs to one
                # transaction. executescript would commit a partial v1 store.
                self._begin()
                for statement in v1_schema.split(";"):
                    if statement.strip():
                        self.conn.execute(statement)
                self._install_v2(self.conn)
                self.conn.execute(
                    "INSERT INTO ops_meta (key, value) VALUES (?, ?)",
                    (OPS_DATABASE_ROLE_META_KEY, OPS_DATABASE_ROLE.encode("ascii")),
                )
            self._opaque_key = self._load_or_create_key(opaque_key)
            self.workspace_alias = self._load_or_set_alias(workspace_alias)
            if _database_version(self.conn) != "current":
                raise DatabaseRoleError(
                    "AgentTool Ops schema initialization did not match its role"
                )
            if database_state == "fresh":
                self.conn.commit()
            self.conn.execute("PRAGMA journal_mode=WAL")
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            self.conn.close()
            raise
        self._secure_files()

    @classmethod
    def open_existing(
        cls, db_path: str | Path, *, readonly: bool = True,
    ) -> "AgentToolOpsStore":
        """Open an existing exact v2 store without initialization or repair.

        Read-only inspection holds one SQL read transaction, including current
        committed WAL state, until close. Open, use and close in the same thread.
        SQLite may maintain WAL/shared-memory accounting after the main file
        passes role validation; this is not filesystem immutability.

        The immutable main-file preflight is admission only, NEVER the returned
        snapshot. A not-yet-checkpointed schema or a hot rollback journal is
        conservatively unavailable. This opener requests no journal mode change
        or checkpoint. ``readonly=False`` enables the existing transactional
        mutation methods; provider locks and authorization remain the caller's
        responsibility.
        """
        if type(readonly) is not bool:
            raise ValueError("readonly must be a boolean")
        path = Path(db_path).expanduser().absolute()
        identity = cls._check_existing_files(path)
        if _inspect_existing_database(path) != "current":
            raise MigrationRequiredError(
                "exact Ops v1 store requires preview_migration and migrate_v1"
            )
        cls._check_existing_files(path, identity)
        candidate: sqlite3.Connection | None = None
        try:
            # Validate current WAL state through SQL read-only access BEFORE
            # opening a connection capable of operational writes or recovery.
            candidate = sqlite3.connect(
                path.as_uri() + "?mode=ro", uri=True,
                isolation_level=None, timeout=2.0,
            )
            candidate.execute("PRAGMA query_only=ON")
            candidate.execute("BEGIN")
            if _database_version(candidate) != "current":
                raise MigrationRequiredError("exact Ops v1 store requires explicit migration")
            cls._check_existing_files(path, identity)
            if not readonly:
                # Keep the validated reader alive across the rw open, avoiding
                # a last-reader close/reopen gap and unnecessary WAL teardown.
                reader = candidate
                candidate = None
                try:
                    candidate = sqlite3.connect(
                        path.as_uri() + "?mode=rw", uri=True,
                        isolation_level=None, timeout=2.0,
                    )
                    candidate.execute("PRAGMA query_only=ON")
                    candidate.execute("PRAGMA foreign_keys=ON")
                    candidate.execute("PRAGMA secure_delete=ON")
                    candidate.execute("BEGIN")
                    if _database_version(candidate) != "current":
                        raise DatabaseRoleError("database is not an exact AgentTool Ops store")
                    cls._check_existing_files(path, identity)
                finally:
                    reader.close()
            candidate.row_factory = sqlite3.Row
            # _database_version has validated these exact required metadata
            # values. Do not call the constructor's load-or-create helpers.
            metadata = dict(candidate.execute("SELECT key, value FROM ops_meta"))
            store = cls.__new__(cls)
            store.path = path
            store.conn = candidate
            store._opaque_key = bytes(metadata["opaque_key"])
            store.workspace_alias = bytes(metadata["workspace_alias"]).decode("utf-8")
            store._existing_identity = identity
            store._readonly = readonly
            if not readonly:
                candidate.rollback()
                candidate.execute("PRAGMA query_only=OFF")
            return store
        except sqlite3.Error:
            if candidate is not None:
                candidate.close()
            raise DatabaseRoleError("existing Ops snapshot is unavailable or busy") from None
        except BaseException:
            if candidate is not None:
                candidate.close()
            raise

    @staticmethod
    def _check_existing_files(
        path: Path, identity: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int, int, int]:
        """Check, never repair, the file, private parent and SQLite sidecars.

        Reject symlinks throughout the supplied ancestry before resolving it.
        This guards accidental unsafe paths, not a malicious same-UID writer
        replacing files between filesystem checks and SQLite's own opens.
        """
        try:
            if ".." in path.parts:
                raise PermissionError("AgentTool Ops state must not use parent traversal")
            for parent in reversed(path.parents):
                if not stat.S_ISDIR(parent.lstat().st_mode):
                    raise PermissionError("AgentTool Ops ancestry must use real directories")
            owner = os.geteuid()
            directory = path.parent.lstat()
            if directory.st_uid != owner or stat.S_IMODE(directory.st_mode) & 0o077:
                raise PermissionError("AgentTool Ops directory must be owner-only (0700)")
            database = path.lstat()
            if stat.S_ISLNK(database.st_mode):
                raise PermissionError("AgentTool Ops state must not use symlinks")
            if not stat.S_ISREG(database.st_mode) or database.st_size == 0:
                raise DatabaseRoleError("existing Ops requires a nonempty regular store")
            for suffix in ("", "-wal", "-shm", "-journal"):
                try:
                    info = Path(str(path) + suffix).lstat()
                except FileNotFoundError:
                    if not suffix:
                        raise
                    continue
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner
                        or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1):
                    raise PermissionError("AgentTool Ops state must be regular and owner-only (0600)")
                if suffix == "-journal" and info.st_size:
                    raise DatabaseRoleError("existing Ops snapshot requires offline recovery")
            current = (database.st_dev, database.st_ino, directory.st_dev, directory.st_ino)
            if identity is not None and current != identity:
                raise DatabaseRoleError("database changed during existing Ops validation")
            return current
        except FileNotFoundError:
            raise DatabaseRoleError("existing Ops store is missing") from None
        except OSError:
            raise PermissionError("existing Ops state could not be inspected securely") from None

    @staticmethod
    def _install_v2(conn: sqlite3.Connection) -> None:
        # executescript would implicitly commit and break migration rollback.
        for statement in _OPS_V2_SCHEMA.split(";"):
            if statement.strip():
                conn.execute(statement)

    @staticmethod
    def _migration_path(db_path: str | Path) -> Path:
        path = Path(db_path).expanduser().absolute()
        if path.is_symlink() or not path.is_file():
            raise DatabaseRoleError("migration requires an existing regular Ops store")
        if stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
            raise PermissionError("AgentTool Ops directory must be owner-only (0700)")
        # Immutable inspection must never mistake a WAL-only schema for v1.
        # Migration is an offline operation: close/checkpoint the v1 writer first.
        wal = Path(str(path) + "-wal")
        if wal.exists() and wal.stat().st_size:
            raise DatabaseRoleError("close and checkpoint the Ops store before migration")
        return path.resolve()

    @classmethod
    def preview_migration(cls, db_path: str | Path) -> dict[str, Any]:
        """Read-only exact-schema preview; never initialize, chmod or enable WAL."""
        path = cls._migration_path(db_path)
        version = _inspect_existing_database(path)
        conn = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        try:
            return {
                "from_role": OPS_V1_DATABASE_ROLE if version == "v1" else OPS_DATABASE_ROLE,
                "to_role": OPS_DATABASE_ROLE,
                "migration_required": version == "v1",
                "historical_incomplete_claims": conn.execute(
                    "SELECT COUNT(*) FROM telegram_updates"
                ).fetchone()[0],
                "preserved_event_deliveries": conn.execute(
                    "SELECT COUNT(*) FROM ops_outbox"
                ).fetchone()[0],
            }
        finally:
            conn.close()

    @classmethod
    def migrate_v1(cls, db_path: str | Path) -> dict[str, Any]:
        """Explicit, transactional additive migration of recognized v1 only."""
        preview = cls.preview_migration(db_path)
        if not preview["migration_required"]:
            return preview
        path = cls._migration_path(db_path)
        identity = path.stat()
        conn = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            reopened = path.stat()
            if (identity.st_dev, identity.st_ino) != (reopened.st_dev, reopened.st_ino):
                raise DatabaseRoleError("database changed during migration validation")
            if _database_version(conn) != "v1":
                raise DatabaseRoleError("migration requires the exact v1 schema")
            cls._install_v2(conn)
            conn.execute(
                "INSERT OR REPLACE INTO ops_meta (key, value) VALUES (?, ?)",
                (OPS_DATABASE_ROLE_META_KEY, OPS_DATABASE_ROLE.encode("ascii")),
            )
            if _database_version(conn) != "current":
                raise DatabaseRoleError("migration schema did not match its role")
            conn.commit()
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()
        return {**preview, "applied": True}

    @contextmanager
    def _transaction(self) -> Any:
        self._begin()
        try:
            yield
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        self._secure_files()

    def _load_or_create_key(self, supplied: bytes | None) -> bytes:
        row = self.conn.execute(
            "SELECT value FROM ops_meta WHERE key = 'opaque_key'"
        ).fetchone()
        if row is None:
            selected = supplied if supplied is not None else secrets.token_bytes(32)
            self.conn.execute(
                "INSERT INTO ops_meta (key, value) VALUES ('opaque_key', ?)",
                (selected,),
            )
            return bytes(selected)
        stored = bytes(row["value"])
        if supplied is not None and not hmac.compare_digest(stored, supplied):
            raise ProjectionConflict("opaque projection key does not match this store")
        return stored

    def _load_or_set_alias(self, supplied: str) -> str:
        row = self.conn.execute(
            "SELECT value FROM ops_meta WHERE key = 'workspace_alias'"
        ).fetchone()
        encoded = supplied.encode("utf-8")
        if row is None:
            self.conn.execute(
                "INSERT INTO ops_meta (key, value) VALUES ('workspace_alias', ?)",
                (encoded,),
            )
            return supplied
        try:
            stored = bytes(row["value"]).decode("utf-8")
        except (UnicodeError, TypeError) as exc:
            raise ProjectionConflict("stored workspace alias is invalid") from exc
        if stored != supplied:
            raise ProjectionConflict("workspace alias does not match this store")
        return stored

    def _secure_files(self) -> None:
        if getattr(self, "_existing_identity", None) is not None:
            self._check_existing_files(self.path, self._existing_identity)
            return
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix)
            if candidate.exists():
                try:
                    candidate.chmod(0o600)
                except OSError as exc:
                    raise PermissionError(
                        "AgentTool Ops state must be owner-only (0600)"
                    ) from exc
                if stat.S_IMODE(candidate.stat().st_mode) & 0o077:
                    raise PermissionError(
                        "AgentTool Ops state must be owner-only (0600)"
                    )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "AgentToolOpsStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _begin(self) -> None:
        if getattr(self, "_readonly", False):
            raise sqlite3.OperationalError("AgentTool Ops store is readonly")
        if self.conn.in_transaction:
            raise sqlite3.OperationalError("AgentTool Ops transaction is already active")
        existing_identity = getattr(self, "_existing_identity", None)
        if existing_identity is not None:
            self._check_existing_files(self.path, existing_identity)
        self.conn.execute("BEGIN IMMEDIATE")
        if existing_identity is not None:
            try:
                if _database_version(self.conn) != "current":
                    raise DatabaseRoleError("database is not an exact AgentTool Ops store")
                self._check_existing_files(self.path, existing_identity)
            except BaseException:
                self.conn.rollback()
                raise

    @staticmethod
    def _anchor_from_row(row: sqlite3.Row, prefix: str) -> CursorAnchor:
        return CursorAnchor(
            epoch_id=str(row[f"{prefix}_epoch"]),
            sequence=int(row[f"{prefix}_sequence"]),
            hash=str(row[f"{prefix}_hash"]),
        )

    def committed_anchor(self) -> CursorAnchor | None:
        row = self.conn.execute("SELECT * FROM cursor_state WHERE singleton = 1").fetchone()
        return self._anchor_from_row(row, "committed") if row is not None else None

    def staged_anchor(self) -> CursorAnchor | None:
        row = self.conn.execute("SELECT * FROM cursor_state WHERE singleton = 1").fetchone()
        if row is None or row["staged_epoch"] is None:
            return None
        return self._anchor_from_row(row, "staged")

    def _prepare_page(
        self,
        current_anchor: CursorAnchor,
        next_anchor: CursorAnchor,
        events: Iterable[Mapping[str, Any]],
    ) -> tuple[
        list[tuple[Mapping[str, Any], SafeEventProjection, str, str]], str
    ]:
        if not isinstance(current_anchor, CursorAnchor) or not isinstance(
            next_anchor, CursorAnchor
        ):
            raise TypeError("page anchors must be CursorAnchor values")
        if current_anchor.epoch_id != next_anchor.epoch_id:
            raise CursorStateError("a staged page cannot cross journal epochs")
        if next_anchor.sequence < current_anchor.sequence:
            raise CursorStateError("terminal cursor precedes the current cursor")
        try:
            materialized = list(itertools.islice(iter(events), MAX_PAGE_EVENTS + 1))
        except TypeError as exc:
            raise OpsProjectionError("events must be an iterable page") from exc
        if len(materialized) > MAX_PAGE_EVENTS:
            raise OpsProjectionError("event page exceeds the supported maximum")
        expected_count = next_anchor.sequence - current_anchor.sequence
        if len(materialized) != expected_count:
            raise CursorStateError("event page does not exactly span its cursor anchors")

        prepared: list[
            tuple[Mapping[str, Any], SafeEventProjection, str, str]
        ] = []
        previous_hash = current_anchor.hash
        for offset, event in enumerate(materialized, start=1):
            if not isinstance(event, Mapping):
                raise OpsProjectionError("event page contains a non-mapping value")
            expected_sequence = current_anchor.sequence + offset
            if event.get("epoch_id") != current_anchor.epoch_id:
                raise CursorStateError("event epoch does not match the page anchor")
            if event.get("sequence") != expected_sequence:
                raise CursorStateError("event sequences are not contiguous")
            if event.get("prev_hash") != previous_hash:
                raise CursorStateError("event hash link does not match the prior anchor")
            event_hash = _check_hash(event.get("hash"), label="event hash")
            projection = project_collab_event(
                event,
                opaque_key=self._opaque_key,
                workspace_alias=self.workspace_alias,
            )
            projection_json = _canonical_json(projection.as_dict())
            derived_json = _canonical_json(
                self._derived_digest_material(event, projection)
            )
            prepared.append((event, projection, projection_json, derived_json))
            previous_hash = event_hash
        if previous_hash != next_anchor.hash:
            raise CursorStateError("terminal event hash does not match next_anchor")

        digest_material = {
            "current": {
                "epoch_id": current_anchor.epoch_id,
                "hash": current_anchor.hash,
                "sequence": current_anchor.sequence,
            },
            "next": {
                "epoch_id": next_anchor.epoch_id,
                "hash": next_anchor.hash,
                "sequence": next_anchor.sequence,
            },
            "projections": [entry[2] for entry in prepared],
            "derived_state": [entry[3] for entry in prepared],
        }
        page_digest = "sha256:" + hashlib.sha256(
            _canonical_json(digest_material).encode("utf-8")
        ).hexdigest()
        return prepared, page_digest

    @staticmethod
    def _observed_version(payload: Mapping[str, Any]) -> int | None:
        value = payload.get("version")
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            or value > (1 << 63) - 1
        ):
            return None
        return value

    @staticmethod
    def _observed_review_state(
        event_type: str, payload: Mapping[str, Any]
    ) -> str | None:
        if event_type == "task.reported_complete":
            return "pending"
        if event_type == "task.completed":
            return "not_required"
        if event_type == "task.accepted":
            return "accepted"
        if event_type == "task.changes_requested":
            return "changes_requested"
        raw = payload.get("review_status")
        aliases = {
            "not_required": "not_required",
            "pending": "pending",
            "accepted": "accepted",
            "changes_requested": "changes_requested",
            "request_changes": "changes_requested",
        }
        if isinstance(raw, str) and raw in aliases:
            return aliases[raw]
        return None

    @staticmethod
    def _observed_recovery_action(payload: Mapping[str, Any]) -> str | None:
        value = payload.get("action")
        return value if value in {"takeover", "release", "block"} else None

    def _derived_digest_material(
        self,
        event: Mapping[str, Any],
        projection: SafeEventProjection,
    ) -> dict[str, Any]:
        """Return only the safe scalars consumed by derived state projection."""

        event_type = event.get("type")
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            return {}
        if event_type == "artifact.attached":
            artifact = payload.get("artifact")
            raw_task_id = artifact.get("task_id") if isinstance(artifact, Mapping) else None
            task_ref: str | None = None
            try:
                bounded = _bounded_text(
                    raw_task_id, label="artifact task_id", limit=512
                )
            except OpsProjectionError:
                pass
            else:
                task_ref = _opaque_ref(self._opaque_key, "task", bounded, size=24)
            return {
                "kind": "artifact_task_state",
                "task_ref": task_ref,
                "version": self._observed_version(payload),
                "entity_matches_task": task_ref == projection.subject_ref,
            }
        if (
            isinstance(event_type, str)
            and event_type in _EVENT_TEMPLATES
            and _EVENT_TEMPLATES[event_type][1] == "task"
        ):
            return {
                "kind": "task_state",
                "recovery_action": (
                    self._observed_recovery_action(payload)
                    if event_type == "task.recovered"
                    else None
                ),
                "review_state": self._observed_review_state(event_type, payload),
                "version": self._observed_version(payload),
            }
        return {}

    def _record_derived_state(
        self,
        event: Mapping[str, Any],
        projection: SafeEventProjection,
    ) -> None:
        """Retain only allowlisted scalar state needed by the read-only console."""

        event_type = event.get("type")
        if event_type in {
            "session.joined",
            "session.resumed",
            "session.heartbeat",
            "session.ended",
        }:
            active = 0 if event_type == "session.ended" else 1
            self.conn.execute(
                """INSERT INTO safe_sessions (
                     session_ref, recorded_active, last_observed_at, last_sequence
                   ) VALUES (?, ?, ?, ?)
                   ON CONFLICT(session_ref) DO UPDATE SET
                     recorded_active = excluded.recorded_active,
                     last_observed_at = excluded.last_observed_at,
                     last_sequence = excluded.last_sequence
                   WHERE excluded.last_sequence > safe_sessions.last_sequence""",
                (
                    projection.subject_ref,
                    active,
                    projection.observed_at,
                    projection.sequence,
                ),
            )
            return

        if event_type == "artifact.attached":
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                return
            artifact = payload.get("artifact")
            if not isinstance(artifact, Mapping):
                return
            raw_task_id = artifact.get("task_id")
            try:
                raw_task_id = _bounded_text(
                    raw_task_id, label="artifact task_id", limit=512
                )
            except OpsProjectionError:
                return
            task_ref = _opaque_ref(self._opaque_key, "task", raw_task_id, size=24)
            if task_ref != projection.subject_ref:
                raise ProjectionConflict(
                    "artifact task identity does not match its event entity"
                )
            version = self._observed_version(payload)
            if version is None:
                return
            row = self.conn.execute(
                "SELECT * FROM safe_tasks WHERE task_ref = ?", (task_ref,)
            ).fetchone()
            if row is not None and version < int(row["version"]):
                raise ProjectionConflict("observed task version regressed")
            if row is None:
                self.conn.execute(
                    """INSERT INTO safe_tasks (
                         task_ref, state, version, review_state,
                         coordination_lease_recorded, safe_summary,
                         evidence_reference_count, last_observed_at, last_sequence
                       ) VALUES (?, 'unknown', ?, 'unknown', 0, ?, 1, ?, ?)""",
                    (
                        task_ref,
                        version,
                        projection.summary,
                        projection.observed_at,
                        projection.sequence,
                    ),
                )
            else:
                self.conn.execute(
                    """UPDATE safe_tasks
                       SET version = ?, safe_summary = ?,
                           evidence_reference_count = evidence_reference_count + 1,
                           last_observed_at = ?, last_sequence = ?
                       WHERE task_ref = ? AND ? > last_sequence""",
                    (
                        version,
                        projection.summary,
                        projection.observed_at,
                        projection.sequence,
                        task_ref,
                        projection.sequence,
                    ),
                )
            return

        if (
            not isinstance(event_type, str)
            or event_type not in _EVENT_TEMPLATES
            or _EVENT_TEMPLATES[event_type][1] != "task"
        ):
            return
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            return
        version = self._observed_version(payload)
        # A version of zero or a locally guessed version would misrepresent the
        # task.  Keep the event projection, but omit the derived task snapshot.
        if version is None:
            return
        recovery_action = (
            self._observed_recovery_action(payload)
            if event_type == "task.recovered"
            else None
        )
        if event_type == "task.recovered" and recovery_action is None:
            return
        row = self.conn.execute(
            "SELECT * FROM safe_tasks WHERE task_ref = ?",
            (projection.subject_ref,),
        ).fetchone()
        if row is not None and version < int(row["version"]):
            raise ProjectionConflict("observed task version regressed")

        prior_state = str(row["state"]) if row is not None else "unknown"
        prior_review = str(row["review_state"]) if row is not None else "unknown"
        prior_lease = bool(row["coordination_lease_recorded"]) if row is not None else False
        state = prior_state
        lease = prior_lease
        if event_type in {
            "task.created",
            "task.released",
            "task.unblocked",
            "task.claim_expired",
            "task.changes_requested",
        }:
            state, lease = "open", False
        elif event_type in {
            "task.claimed",
            "task.lease_renewed",
            "task.progressed",
        }:
            state, lease = "claimed", True
        elif event_type == "task.recovered":
            if recovery_action == "takeover":
                state, lease = "claimed", True
            elif recovery_action == "block":
                state, lease = "blocked", False
            else:
                state, lease = "open", False
        elif event_type == "task.blocked":
            state, lease = "blocked", False
        elif event_type == "task.reported_complete":
            state, lease = "reported_complete", False
        elif event_type in {"task.completed", "task.accepted"}:
            state, lease = "completed", False

        observed_review = self._observed_review_state(event_type, payload)
        review_state = observed_review or prior_review
        self.conn.execute(
            """INSERT INTO safe_tasks (
                 task_ref, state, version, review_state,
                 coordination_lease_recorded, safe_summary,
                 evidence_reference_count, last_observed_at, last_sequence
               ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
               ON CONFLICT(task_ref) DO UPDATE SET
                 state = excluded.state,
                 version = excluded.version,
                 review_state = excluded.review_state,
                 coordination_lease_recorded = excluded.coordination_lease_recorded,
                 safe_summary = excluded.safe_summary,
                 last_observed_at = excluded.last_observed_at,
                 last_sequence = excluded.last_sequence
               WHERE excluded.last_sequence > safe_tasks.last_sequence""",
            (
                projection.subject_ref,
                state,
                version,
                review_state,
                int(lease),
                projection.summary,
                projection.observed_at,
                projection.sequence,
            ),
        )

    def stage_page(
        self,
        *,
        current_anchor: CursorAnchor,
        next_anchor: CursorAnchor,
        events: Iterable[Mapping[str, Any]],
        staged_at: datetime | str | None = None,
    ) -> PageStage:
        """Atomically stage exactly one contiguous page and its safe outbox rows."""

        prepared, page_digest = self._prepare_page(current_anchor, next_anchor, events)
        now = _timestamp(staged_at)
        self._begin()
        try:
            transport = self.poll_state()
            if transport is not None and transport.state == "paused":
                raise BindingStateError("Ops transport is paused")
            state_row = self.conn.execute(
                "SELECT * FROM cursor_state WHERE singleton = 1"
            ).fetchone()
            if state_row is None:
                self.conn.execute(
                    """INSERT INTO cursor_state (
                         singleton, committed_epoch, committed_sequence, committed_hash,
                         staged_epoch, staged_sequence, staged_hash, staged_page_digest
                       ) VALUES (1, ?, ?, ?, NULL, NULL, NULL, NULL)""",
                    (current_anchor.epoch_id, current_anchor.sequence, current_anchor.hash),
                )
                committed = current_anchor
                staged = None
            else:
                committed = self._anchor_from_row(state_row, "committed")
                staged = (
                    self._anchor_from_row(state_row, "staged")
                    if state_row["staged_epoch"] is not None
                    else None
                )

            # An exact empty poll at the already-committed head is a no-op,
            # even when that coordinate is also the terminal anchor of the
            # historical non-empty page that first reached it.
            if not prepared and committed == next_anchor and staged is None:
                self.conn.commit()
                return PageStage(
                    anchor=next_anchor,
                    event_count=0,
                    enqueued_count=0,
                    state="committed",
                    duplicate=True,
                )

            prior_page = self.conn.execute(
                """SELECT * FROM cursor_pages
                   WHERE epoch_id = ? AND terminal_sequence = ? AND terminal_hash = ?""",
                (next_anchor.epoch_id, next_anchor.sequence, next_anchor.hash),
            ).fetchone()
            if prior_page is not None:
                same = (
                    prior_page["initial_epoch"] == current_anchor.epoch_id
                    and prior_page["initial_sequence"] == current_anchor.sequence
                    and prior_page["initial_hash"] == current_anchor.hash
                    and prior_page["page_digest"] == page_digest
                    and prior_page["event_count"] == len(prepared)
                )
                if not same:
                    raise ProjectionConflict(
                        "terminal cursor was reused for a different staged page"
                    )
                self.conn.commit()
                self._secure_files()
                return PageStage(
                    anchor=next_anchor,
                    event_count=len(prepared),
                    enqueued_count=0,
                    state=str(prior_page["state"]),  # type: ignore[arg-type]
                    duplicate=True,
                )

            if staged is not None:
                raise CursorStateError(
                    "another exact page is staged; commit it first"
                )
            if committed != current_anchor:
                raise CursorStateError("current_anchor is not the committed local cursor")

            enqueued = 0
            for event, projection, projection_json, _derived_json in prepared:
                projection_digest = "sha256:" + hashlib.sha256(
                    projection_json.encode("utf-8")
                ).hexdigest()
                existing = self.conn.execute(
                    "SELECT * FROM safe_events WHERE event_key = ?",
                    (projection.event_key,),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["epoch_id"] != event["epoch_id"]
                        or existing["sequence"] != event["sequence"]
                        or existing["event_hash"] != event["hash"]
                        or existing["projection_digest"] != projection_digest
                        or existing["projection_json"] != projection_json
                    ):
                        raise ProjectionConflict(
                            "deterministic event key was reused with different content"
                        )
                    continue
                try:
                    self.conn.execute(
                        """INSERT INTO safe_events (
                             event_key, epoch_id, sequence, event_hash,
                             projection_json, projection_digest, staged_at
                           ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            projection.event_key,
                            event["epoch_id"],
                            event["sequence"],
                            event["hash"],
                            projection_json,
                            projection_digest,
                            now,
                        ),
                    )
                    self.conn.execute(
                        """INSERT INTO ops_outbox (
                             event_key, payload_json, payload_digest, state,
                             attempt_count, queued_at
                           ) VALUES (?, ?, ?, 'pending', 0, ?)""",
                        (
                            projection.event_key,
                            projection_json,
                            projection_digest,
                            now,
                        ),
                    )
                    self._record_derived_state(event, projection)
                except sqlite3.IntegrityError as exc:
                    raise ProjectionConflict(
                        "journal coordinate conflicts with an existing projection"
                    ) from exc
                enqueued += 1

            self.conn.execute(
                """INSERT INTO cursor_pages (
                     epoch_id, terminal_sequence, terminal_hash,
                     initial_epoch, initial_sequence, initial_hash,
                     page_digest, event_count, state, staged_at, committed_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'staged', ?, NULL)""",
                (
                    next_anchor.epoch_id,
                    next_anchor.sequence,
                    next_anchor.hash,
                    current_anchor.epoch_id,
                    current_anchor.sequence,
                    current_anchor.hash,
                    page_digest,
                    len(prepared),
                    now,
                ),
            )
            self.conn.execute(
                """UPDATE cursor_state
                   SET staged_epoch = ?, staged_sequence = ?, staged_hash = ?,
                       staged_page_digest = ?
                   WHERE singleton = 1""",
                (
                    next_anchor.epoch_id,
                    next_anchor.sequence,
                    next_anchor.hash,
                    page_digest,
                ),
            )
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        self._secure_files()
        return PageStage(
            anchor=next_anchor,
            event_count=len(prepared),
            enqueued_count=enqueued,
            state="staged",
        )

    def commit_staged_cursor(
        self,
        anchor: CursorAnchor,
        *,
        committed_at: datetime | str | None = None,
    ) -> CursorCommit:
        """Advance the gateway cursor to its exact durably staged page anchor.

        This records local processing only.  It neither calls nor implies a
        Collab session-cursor acknowledgement.
        """

        if not isinstance(anchor, CursorAnchor):
            raise TypeError("anchor must be a CursorAnchor")
        now = _timestamp(committed_at)
        self._begin()
        try:
            row = self.conn.execute(
                "SELECT * FROM cursor_state WHERE singleton = 1"
            ).fetchone()
            if row is None:
                raise CursorStateError("no cursor page has been staged")
            committed = self._anchor_from_row(row, "committed")
            if row["staged_epoch"] is None:
                if committed == anchor:
                    self.conn.commit()
                    return CursorCommit(anchor=anchor, duplicate=True)
                raise CursorStateError("there is no staged cursor to commit")
            staged = self._anchor_from_row(row, "staged")
            if staged != anchor:
                raise CursorStateError("commit anchor does not match the staged page")
            changed = self.conn.execute(
                """UPDATE cursor_pages
                   SET state = 'committed', committed_at = ?
                   WHERE epoch_id = ? AND terminal_sequence = ? AND terminal_hash = ?
                     AND state = 'staged'""",
                (now, anchor.epoch_id, anchor.sequence, anchor.hash),
            ).rowcount
            if changed != 1:
                raise CursorStateError("staged cursor page record is missing")
            self.conn.execute(
                """UPDATE cursor_state
                   SET committed_epoch = staged_epoch,
                       committed_sequence = staged_sequence,
                       committed_hash = staged_hash,
                       staged_epoch = NULL, staged_sequence = NULL,
                       staged_hash = NULL, staged_page_digest = NULL
                   WHERE singleton = 1"""
            )
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        self._secure_files()
        return CursorCommit(anchor=anchor)

    @staticmethod
    def _projection_from_json(
        value: str, *, expected_digest: str | None = None
    ) -> SafeEventProjection:
        if expected_digest is not None:
            actual_digest = "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(actual_digest, expected_digest):
                raise ProjectionConflict("stored projection digest does not match")
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ProjectionConflict("stored projection JSON is invalid") from exc
        if not isinstance(parsed, Mapping):
            raise ProjectionConflict("stored projection JSON is invalid")
        return SafeEventProjection.from_mapping(parsed)

    def _outbox_item(self, row: sqlite3.Row, *, duplicate: bool = False) -> OutboxItem:
        projection = self._projection_from_json(
            str(row["payload_json"]), expected_digest=str(row["payload_digest"])
        )
        if projection.event_key != row["event_key"]:
            raise ProjectionConflict("stored outbox event identity does not match")
        return OutboxItem(
            event_key=str(row["event_key"]),
            projection=projection,
            state=str(row["state"]),
            attempt_count=int(row["attempt_count"]),
            receipt_ref=(
                str(row["receipt_ref"]) if row["receipt_ref"] is not None else None
            ),
            error_code=(
                str(row["error_code"]) if row["error_code"] is not None else None
            ),
            duplicate=duplicate,
        )

    def outbox_item(self, event_key: str) -> OutboxItem | None:
        if not isinstance(event_key, str) or _EVENT_KEY.fullmatch(event_key) is None:
            raise ValueError("event_key is invalid")
        row = self.conn.execute(
            "SELECT * FROM ops_outbox WHERE event_key = ?", (event_key,)
        ).fetchone()
        return self._outbox_item(row) if row is not None else None

    def pending_outbox(self, *, limit: int = 20) -> tuple[OutboxItem, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        rows = self.conn.execute(
            """SELECT o.* FROM ops_outbox AS o
               JOIN safe_events AS e ON e.event_key = o.event_key
               JOIN cursor_state AS c ON c.singleton = 1
               WHERE o.state = 'pending'
                 AND e.epoch_id = c.committed_epoch
                 AND e.sequence <= c.committed_sequence
               ORDER BY e.sequence ASC, o.event_key ASC LIMIT ?""",
            (limit,),
        ).fetchall()
        return tuple(self._outbox_item(row) for row in rows)

    def recent_projections(self, *, limit: int = 20) -> tuple[SafeEventProjection, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        rows = self.conn.execute(
            """SELECT e.projection_json, e.projection_digest
               FROM safe_events AS e
               JOIN cursor_state AS c ON c.singleton = 1
               WHERE e.epoch_id = c.committed_epoch
                 AND e.sequence <= c.committed_sequence
               ORDER BY e.sequence DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return tuple(
            self._projection_from_json(
                str(row["projection_json"]),
                expected_digest=str(row["projection_digest"]),
            )
            for row in rows
        )

    def outbox_counts(self) -> dict[str, int]:
        result = {state: 0 for state in ("pending", "inflight", "sent", "failed", "unknown")}
        for row in self.conn.execute(
            """SELECT o.state, COUNT(*) AS count
               FROM ops_outbox AS o
               JOIN safe_events AS e ON e.event_key = o.event_key
               JOIN cursor_state AS c ON c.singleton = 1
               WHERE e.epoch_id = c.committed_epoch
                 AND e.sequence <= c.committed_sequence
               GROUP BY o.state"""
        ):
            result[str(row["state"])] = int(row["count"])
        return result

    @staticmethod
    def _positive_id(value: Any, label: str, maximum: int = (1 << 52) - 1) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise ValueError(f"{label} is invalid")
        return value

    @staticmethod
    def _binding_from_row(row: sqlite3.Row) -> OpsBinding:
        return OpsBinding(**{name: row[name] for name in OpsBinding.__dataclass_fields__})

    def binding(self) -> OpsBinding | None:
        row = self.conn.execute(
            """SELECT b.* FROM ops_bindings b JOIN ops_transport t
               ON b.revision = t.binding_revision WHERE t.singleton = 1"""
        ).fetchone()
        return self._binding_from_row(row) if row is not None else None

    def assert_initial_binding_allowed(self) -> None:
        """Read-only preflight: unbound state must be pristine before first binding.

        Legacy projections, cursor seeds and verification observations carry no
        proven source binding. A matching alias or opaque key cannot establish
        their provenance. They remain available for offline inspection, but must
        not acquire a new provider/source owner. Already-bound stores are a no-op;
        binding comparison is separately enforced by ``bind_operator``.
        """
        if self.binding() is not None:
            return
        tables = sorted(
            name for kind, name, _table in _OPS_SCHEMA_OBJECTS
            if kind == "table" and name != "ops_meta"
        )
        for table in tables:
            if self.conn.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone() is not None:
                raise BindingStateError(
                    "initial Ops binding requires pristine source state; use a new empty store"
                )

    def bind_operator(
        self,
        bot_id: int,
        api_origin: str,
        *,
        operator_user_id: int,
        operator_private_chat_id: int,
        credential_ref: str,
        source_binding: str,
        verification: Literal["verified", "fixture"] = "verified",
        bound_at: datetime | str | None = None,
    ) -> OpsBinding:
        """Create a complete binding or compare it. Never rebind an old backlog.

        ``verified`` records the host's explicit provider verification; the store
        does not contact Telegram or infer that verification from numeric IDs.
        Tokens, source paths and arbitrary credential references are not accepted.
        """
        self._positive_id(bot_id, "bot_id")
        self._positive_id(operator_user_id, "operator_user_id")
        self._positive_id(operator_private_chat_id, "operator_private_chat_id")
        if operator_user_id != operator_private_chat_id:
            raise ValueError("operator private-chat pair must match")
        if verification not in {"verified", "fixture"}:
            raise ValueError("verification is invalid")
        if api_origin != TELEGRAM_PRODUCTION_ORIGIN:
            # Fixtures use the production origin as a label, never a network call.
            raise ValueError("Ops requires the approved Telegram production origin")
        if not isinstance(credential_ref, str):
            raise ValueError("dedicated credential_ref is invalid")
        if credential_ref.startswith(OPS_CREDENTIAL_PREFIX):
            account = credential_ref[len(OPS_CREDENTIAL_PREFIX):]
            valid_credential = _CREDENTIAL_ACCOUNT.fullmatch(account) is not None
        else:
            valid_credential = (
                verification == "fixture" and credential_ref.startswith("fixture:")
                and _MACHINE_LABEL.fullmatch(credential_ref) is not None
            )
        if not valid_credential:
            raise ValueError("dedicated credential_ref is invalid")
        if self._check_machine_label(source_binding, "source_binding") is None:
            raise ValueError("source_binding is required")
        now = _timestamp(bound_at)
        requested = OpsBinding(
            1, bot_id, operator_user_id, operator_private_chat_id, api_origin,
            credential_ref, source_binding, verification, now,
            int(datetime.fromisoformat(now.replace("Z", "+00:00")).timestamp()),
        )
        with self._transaction():
            existing = self.binding()
            if existing is not None:
                compared = replace(requested, revision=existing.revision,
                                   bound_at=existing.bound_at, accept_after=existing.accept_after)
                if existing != compared:
                    raise BindingStateError("Ops binding mismatch; use a new empty store")
                return existing
            self.assert_initial_binding_allowed()
            self._insert_binding(requested)
            self.conn.execute(
                """INSERT INTO ops_poll_epochs VALUES (1, 1, ?, ?, NULL)""", (now, now)
            )
            self.conn.execute("INSERT INTO ops_transport VALUES (1, 1, 'active', 1)")
        return requested

    def _insert_binding(self, binding: OpsBinding) -> None:
        self.conn.execute(
            "INSERT INTO ops_bindings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(getattr(binding, name) for name in OpsBinding.__dataclass_fields__),
        )

    def bind_telegram_provider(
        self, bot_id: int, api_origin: str, *, allow_create: bool = True
    ) -> None:
        """Bootstrap protocol: compare a complete binding, never partially create."""
        self._positive_id(bot_id, "bot_id")
        if not isinstance(allow_create, bool):
            raise ValueError("allow_create must be a boolean")
        binding = self.binding()
        if binding is None:
            raise BindingStateError("complete Ops operator binding is required")
        if binding.bot_id != bot_id or binding.api_origin != api_origin:
            raise BindingStateError("Ops provider binding mismatch")

    def require_ready(
        self,
        *,
        bot_id: int,
        operator_user_id: int,
        operator_private_chat_id: int,
        api_origin: str,
        credential_ref: str,
        source_binding: str,
        live: bool = True,
    ) -> OpsBinding:
        """Check exact host expectations before any credential-bearing work."""
        for name, value in (("bot_id", bot_id), ("operator_user_id", operator_user_id),
                            ("operator_private_chat_id", operator_private_chat_id)):
            self._positive_id(value, name)
        if not isinstance(live, bool):
            raise ValueError("live must be a boolean")
        binding = self._active_binding()
        expected = (bot_id, operator_user_id, operator_private_chat_id, api_origin,
                    credential_ref, source_binding)
        actual = (binding.bot_id, binding.operator_user_id, binding.operator_private_chat_id,
                  binding.api_origin, binding.credential_ref, binding.source_binding)
        if expected != actual or api_origin != TELEGRAM_PRODUCTION_ORIGIN:
            raise BindingStateError("Ops runtime binding mismatch")
        if live and binding.verification != "verified":
            raise BindingStateError("fixture binding cannot authorize live transport")
        return binding

    def _active_binding(self) -> OpsBinding:
        binding = self.binding()
        state = self.poll_state()
        if binding is None or state is None:
            raise BindingStateError("complete Ops operator binding is required")
        if state.state != "active":
            raise BindingStateError("Ops transport is paused")
        return binding

    def poll_state(self) -> PollState | None:
        row = self.conn.execute(
            """SELECT e.*, t.state FROM ops_poll_epochs e JOIN ops_transport t
               ON e.epoch = t.polling_epoch WHERE t.singleton = 1"""
        ).fetchone()
        if row is None:
            return None
        return PollState(row["epoch"], row["binding_revision"], row["next_offset"],
                         row["last_update_at"], row["state"])

    def prepare_poll(self, *, now: datetime | str | None = None) -> PollState:
        """Commit an idle epoch reset before the host fetches a bounded batch.

        Host must use the returned offset verbatim (None means no offset), then
        process the provider's ascending update order without skipping a failed
        item. A subsequent fetch acknowledges only committed dispositions.
        Cooperating hosts must also hold the provider-scoped runner lock.
        """
        current_time = _timestamp(now)
        with self._transaction():
            self._active_binding()
            state = self.poll_state()
            assert state is not None
            idle = (datetime.fromisoformat(current_time.replace("Z", "+00:00"))
                    - datetime.fromisoformat(state.last_update_at.replace("Z", "+00:00")))
            if idle >= timedelta(seconds=POLL_EPOCH_IDLE_SECONDS):
                self._new_poll_epoch(state.epoch + 1, state.binding_revision, current_time)
            result = self.poll_state()
            assert result is not None
        return result

    def _new_poll_epoch(self, epoch: int, revision: int, now: str) -> None:
        self.conn.execute("INSERT INTO ops_poll_epochs VALUES (?, ?, ?, ?, NULL)",
                          (epoch, revision, now, now))
        self.conn.execute(
            "UPDATE ops_transport SET polling_epoch = ?, binding_revision = ? WHERE singleton = 1",
            (epoch, revision),
        )

    def process_update_once(
        self,
        update: Mapping[str, object],
        service: Any,
        *,
        polling_epoch: int,
        processed_at: datetime | str | None = None,
    ) -> UpdateDisposition:
        """Dedupe + render + disposition/reply + safe offset in one transaction.

        This persists no raw command, update, provider body or exception. The
        source must be this connection's sanitized projection, not a remote
        adapter. A duplicate reuses its disposition and never rerenders it.
        Across recent epochs it returns the original polling_epoch/reply_id;
        only the current epoch's acknowledgment offset may advance.
        Invalid IDs raise without advancing; invalid messages are ignored.
        """
        from .ops_service import OpsReply, TelegramOpsService, MAX_REPLY_CHARACTERS

        update_id = update.get("update_id") if isinstance(update, Mapping) else None
        if isinstance(update_id, bool) or not isinstance(update_id, int) or not 0 <= update_id < 1 << 31:
            raise ValueError("update_id is invalid")
        self._positive_id(polling_epoch, "polling_epoch", (1 << 63) - 1)
        if not isinstance(service, TelegramOpsService) or service.source is not self:
            raise ValueError("atomic rendering requires this store's local projection source")
        now = _timestamp(processed_at)
        with self._transaction():
            binding = self._active_binding()
            state = self.poll_state()
            assert state is not None
            if state.epoch != polling_epoch:
                raise CursorStateError("polling epoch is stale")
            if (service.config.operator_user_id != binding.operator_user_id
                    or service.config.operator_private_chat_id != binding.operator_private_chat_id):
                raise BindingStateError("Ops service recipient binding mismatch")
            retention_start = _timestamp(
                datetime.fromisoformat(now.replace("Z", "+00:00"))
                - timedelta(seconds=POLL_EPOCH_IDLE_SECONDS)
            )
            row = self.conn.execute(
                """SELECT * FROM ops_update_dispositions WHERE update_id = ?
                   AND (polling_epoch = ? OR processed_at >= ?)
                   ORDER BY polling_epoch DESC LIMIT 1""",
                (update_id, polling_epoch, retention_start),
            ).fetchone()
            if row is not None:
                # Keep dedupe across short pause/resume epochs for the provider's
                # retention window: message dates can run ahead of our cutoff.
                # Reuse the ORIGINAL disposition; copying it into a new epoch or
                # refreshing its time could suppress post-idle randomized IDs.
                if state.next_offset is None or update_id >= state.next_offset:
                    self.conn.execute(
                        "UPDATE ops_poll_epochs SET next_offset = ? WHERE epoch = ?",
                        (update_id + 1, polling_epoch),
                    )
                return UpdateDisposition(row["polling_epoch"], update_id, row["disposition"], row["reply_id"], True)
            message = update.get("message")
            date = message.get("date") if isinstance(message, Mapping) else None
            legacy = polling_epoch == 1 and self.conn.execute(
                "SELECT 1 FROM telegram_updates WHERE update_id = ?", (update_id,)
            ).fetchone() is not None
            reply = None
            if legacy:
                disposition = "historical_incomplete"
            elif isinstance(date, bool) or not isinstance(date, int) or date < 0:
                disposition = "ignored"
            elif date <= binding.accept_after:
                disposition = "withdrawn"
            else:
                reply = service.render_update(update)
                disposition = "ignored" if reply is None else "reply"
            reply_id = None
            if reply is not None:
                if (not isinstance(reply, OpsReply) or reply.update_id != update_id
                        or reply.chat_id != binding.operator_private_chat_id
                        or reply.protect_content is not True
                        or not isinstance(reply.text, str) or not 1 <= len(reply.text) <= MAX_REPLY_CHARACTERS
                        or "\x00" in reply.text):
                    raise ProjectionConflict("rendered reply violates its immutable binding")
                try:
                    reply.text.encode("utf-8")
                except UnicodeError:
                    raise ProjectionConflict("rendered reply is invalid") from None
                reply_id = "rpl_" + secrets.token_hex(16)
            self.conn.execute(
                "INSERT INTO ops_update_dispositions VALUES (?, ?, ?, ?, ?)",
                (polling_epoch, update_id, disposition, reply_id, now),
            )
            if reply is not None:
                digest = self._reply_digest(reply_id, polling_epoch, update_id, binding, reply.text)
                self.conn.execute(
                    """INSERT INTO ops_replies (reply_id, polling_epoch, update_id,
                       binding_revision, payload_text, payload_digest, state, queued_at)
                       VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
                    (reply_id, polling_epoch, update_id, binding.revision, reply.text, digest, now),
                )
            # This is the next offset after THIS processed update, not max(ID)
            # dedupe. Ordered batches advance; out-of-order callers can regress
            # the offset conservatively rather than discard unseen work.
            self.conn.execute(
                "UPDATE ops_poll_epochs SET next_offset = ?, last_update_at = ? WHERE epoch = ?",
                (update_id + 1, now, polling_epoch),
            )
        return UpdateDisposition(polling_epoch, update_id, disposition, reply_id)

    @staticmethod
    def _reply_digest(reply_id: str, epoch: int, update_id: int, binding: OpsBinding, text: str) -> str:
        material = {"reply_id": reply_id, "polling_epoch": epoch, "update_id": update_id,
                    "binding": {name: getattr(binding, name) for name in OpsBinding.__dataclass_fields__},
                    "text": text, "protect_content": True}
        return "sha256:" + hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()

    def reply_item(self, reply_id: str) -> ReplyItem | None:
        if not isinstance(reply_id, str) or _REPLY_ID.fullmatch(reply_id) is None:
            raise ValueError("reply_id is invalid")
        row = self.conn.execute("SELECT * FROM ops_replies WHERE reply_id = ?", (reply_id,)).fetchone()
        if row is None:
            return None
        owner = self.conn.execute("SELECT * FROM ops_bindings WHERE revision = ?",
                                  (row["binding_revision"],)).fetchone()
        if owner is None:
            raise ProjectionConflict("reply owner binding is missing")
        binding = self._binding_from_row(owner)
        digest = self._reply_digest(reply_id, row["polling_epoch"], row["update_id"], binding, row["payload_text"])
        if not hmac.compare_digest(digest, row["payload_digest"]):
            raise ProjectionConflict("stored reply digest does not match")
        return ReplyItem(reply_id, row["polling_epoch"], row["update_id"], binding,
                         row["payload_text"], digest, row["state"], row["attempt_count"],
                         row["receipt_ref"], row["error_code"])

    def list_replies(
        self, *, state: str | None = None, limit: int = 20,
        after_reply_id: str | None = None,
    ) -> tuple[ReplyItem, ...]:
        """Read a bounded page ordered by immutable queued_at, then reply_id.

        Continue with the last returned reply_id. A cursor must exist but need
        not match the state filter (delivery may have changed since the page).
        An empty tuple marks the end; no delivery state is changed.
        """
        self._check_query_limit(limit)
        if state is not None and (not isinstance(state, str) or state not in {
            "pending", "inflight", "sent", "failed", "unknown", "invalidated",
        }):
            raise ValueError("reply state is invalid")
        queued_at = None
        if after_reply_id is not None:
            if not isinstance(after_reply_id, str) or _REPLY_ID.fullmatch(after_reply_id) is None:
                raise ValueError("after_reply_id is invalid")
            cursor = self.conn.execute(
                "SELECT queued_at FROM ops_replies WHERE reply_id = ?", (after_reply_id,)
            ).fetchone()
            if cursor is None:
                raise ValueError("after_reply_id does not exist")
            queued_at = cursor["queued_at"]
        rows = self.conn.execute(
            """SELECT reply_id FROM ops_replies WHERE (? IS NULL OR state = ?)
               AND (? IS NULL OR (queued_at, reply_id) > (?, ?))
               ORDER BY queued_at ASC, reply_id ASC LIMIT ?""",
            (state, state, after_reply_id, queued_at, after_reply_id, limit),
        ).fetchall()
        return tuple(self.reply_item(row[0]) for row in rows)  # type: ignore[misc]

    def claim_reply(
        self, reply_id: str, *, payload_digest: str, binding_revision: int,
        attempted_at: datetime | str | None = None,
    ) -> ReplyItem:
        """Commit one exact preview's pending → inflight transition before send.

        No automatic or explicit retry is exposed for command replies. Failure
        can be followed by a fresh user command; unknown never becomes pending.
        """
        self._positive_id(binding_revision, "binding_revision", (1 << 63) - 1)
        now = _timestamp(attempted_at)
        with self._transaction():
            binding = self._active_binding()
            item = self.reply_item(reply_id)
            if item is None:
                raise DeliveryStateError("reply does not exist")
            if (item.binding_revision != binding_revision or binding.revision != binding_revision
                    or not isinstance(payload_digest, str) or item.payload_digest != payload_digest):
                raise BindingStateError("reply preview or binding revision is stale")
            if item.state != "pending":
                raise DeliveryStateError("only a pending reply can be claimed; reconcile unknown delivery")
            self.conn.execute("UPDATE ops_replies SET state = 'inflight', attempt_count = attempt_count + 1 WHERE reply_id = ?", (reply_id,))
            self.conn.execute(
                """INSERT INTO ops_reply_attempts (reply_id, attempt_count, state, attempted_at)
                   VALUES (?, ?, 'inflight', ?)""", (reply_id, item.attempt_count + 1, now)
            )
            result = self.reply_item(reply_id)
            assert result is not None
        return result

    def finish_reply(
        self, reply_id: str, *, attempt_count: int,
        state: Literal["sent", "failed", "unknown"], receipt_ref: str | None = None,
        error_code: str | None = None, finished_at: datetime | str | None = None,
    ) -> ReplyItem:
        """Fence completion by exact attempt; never persist provider error text."""
        self._positive_id(attempt_count, "attempt_count", (1 << 63) - 1)
        if state not in {"sent", "failed", "unknown"}:
            raise ValueError("reply finish state is invalid")
        receipt_ref = self._check_machine_label(receipt_ref, "receipt_ref")
        if error_code is not None and error_code not in REPLY_ERROR_CODES:
            raise ValueError("reply error_code is invalid")
        if state == "sent" and (receipt_ref is None or error_code is not None):
            raise ValueError("sent reply requires a receipt and no error")
        if state != "sent" and receipt_ref is not None:
            raise ValueError("only a sent reply may store a receipt")
        now = _timestamp(finished_at)
        with self._transaction():
            item = self._fenced_reply(reply_id, attempt_count)
            if item.state != "inflight":
                raise DeliveryStateError("only an inflight reply can be finished")
            self.conn.execute(
                "UPDATE ops_replies SET state = ?, receipt_ref = ?, error_code = ? WHERE reply_id = ?",
                (state, receipt_ref, error_code, reply_id),
            )
            self.conn.execute(
                """UPDATE ops_reply_attempts SET state = ?, receipt_ref = ?, error_code = ?, finished_at = ?
                   WHERE reply_id = ? AND attempt_count = ?""",
                (state, receipt_ref, error_code, now, reply_id, attempt_count),
            )
            result = self.reply_item(reply_id)
            assert result is not None
        return result

    def _fenced_reply(self, reply_id: str, attempt_count: int) -> ReplyItem:
        item = self.reply_item(reply_id)
        if item is None:
            raise DeliveryStateError("reply does not exist")
        if item.attempt_count != attempt_count:
            raise DeliveryStateError("reply attempt is stale")
        return item

    def reply_attempts(self, reply_id: str) -> tuple[dict[str, Any], ...]:
        self.reply_item(reply_id)
        return tuple(dict(row) for row in self.conn.execute(
            "SELECT * FROM ops_reply_attempts WHERE reply_id = ? ORDER BY attempt_count", (reply_id,)
        ))

    def reply_reconciliations(self, reply_id: str) -> tuple[dict[str, Any], ...]:
        self.reply_item(reply_id)
        return tuple(dict(row) for row in self.conn.execute(
            "SELECT * FROM ops_reply_reconciliations WHERE reply_id = ? ORDER BY observation_id", (reply_id,)
        ))

    def mark_interrupted_replies(self, *, interrupted_at: datetime | str | None = None) -> int:
        """Local recovery under the runner lock; never retry a lost send attempt."""
        now = _timestamp(interrupted_at)
        with self._transaction():
            count = self._interrupt_replies(now, "interrupted")
        return count

    def _interrupt_replies(self, now: str, code: str) -> int:
        self.conn.execute(
            """UPDATE ops_reply_attempts SET state = 'unknown', error_code = ?, finished_at = ?
               WHERE state = 'inflight' AND reply_id IN
               (SELECT reply_id FROM ops_replies WHERE state = 'inflight')""", (code, now)
        )
        return self.conn.execute(
            "UPDATE ops_replies SET state = 'unknown', error_code = ? WHERE state = 'inflight'", (code,)
        ).rowcount

    def reconcile_reply(
        self, reply_id: str, *, attempt_count: int,
        outcome: Literal["sent", "failed", "unknown"], reconciliation_ref: str,
        receipt_ref: str | None = None, reconciled_at: datetime | str | None = None,
    ) -> ReplyItem:
        """Record one explicit observation without sending or erasing evidence.

        A missing visible message is NOT definitive failure; use unknown. A
        definitive failed reconciliation is terminal, not retry authorization.
        """
        self._positive_id(attempt_count, "attempt_count", (1 << 63) - 1)
        if outcome not in {"sent", "failed", "unknown"}:
            raise ValueError("reconciliation outcome is invalid")
        if self._check_machine_label(reconciliation_ref, "reconciliation_ref") is None:
            raise ValueError("reconciliation_ref is required")
        receipt_ref = self._check_machine_label(receipt_ref, "receipt_ref")
        if outcome == "sent" and receipt_ref is None:
            raise ValueError("sent reconciliation requires a receipt_ref")
        if outcome != "sent" and receipt_ref is not None:
            raise ValueError("only sent reconciliation may store a receipt_ref")
        now = _timestamp(reconciled_at)
        with self._transaction():
            item = self._fenced_reply(reply_id, attempt_count)
            if item.state not in {"inflight", "unknown"}:
                raise DeliveryStateError("only inflight or unknown replies can be reconciled")
            self.conn.execute(
                """INSERT INTO ops_reply_reconciliations
                   (reply_id, attempt_count, outcome, reconciliation_ref, receipt_ref, reconciled_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (reply_id, attempt_count, outcome, reconciliation_ref, receipt_ref, now),
            )
            self.conn.execute(
                "UPDATE ops_replies SET state = ?, receipt_ref = ? WHERE reply_id = ?",
                (outcome, receipt_ref, reply_id),
            )
            result = self.reply_item(reply_id)
            assert result is not None
        return result

    def pause(self, *, paused_at: datetime | str | None = None) -> PollState:
        """Local withdrawal: invalidate unsent disclosures and fence inflight work.

        This cannot unsend an already accepted provider request, erase Telegram
        history, or stop agents. It requires no credential/provider interaction.
        """
        now = _timestamp(paused_at)
        with self._transaction():
            state = self.poll_state()
            if state is None:
                raise BindingStateError("complete Ops operator binding is required")
            self.conn.execute("UPDATE ops_transport SET state = 'paused' WHERE singleton = 1")
            self.conn.execute(
                "UPDATE ops_replies SET state = 'invalidated' WHERE state IN ('pending', 'failed')"
            )
            self._interrupt_replies(now, "paused")
            result = self.poll_state()
            assert result is not None
        return result

    def resume(self, *, resumed_at: datetime | str | None = None) -> OpsBinding:
        """Explicit same-owner resumption; new revision/epoch, no old queue replay."""
        now = _timestamp(resumed_at)
        with self._transaction():
            state, binding = self.poll_state(), self.binding()
            if state is None or binding is None:
                raise BindingStateError("complete Ops operator binding is required")
            if state.state != "paused":
                raise BindingStateError("only a paused transport can resume")
            cutoff = int(datetime.fromisoformat(now.replace("Z", "+00:00")).timestamp())
            if cutoff < binding.accept_after:
                raise ValueError("resumption timestamp precedes the binding")
            result = replace(binding, revision=binding.revision + 1, bound_at=now, accept_after=cutoff)
            self._insert_binding(result)
            self._new_poll_epoch(state.epoch + 1, result.revision, now)
            self.conn.execute("UPDATE ops_transport SET state = 'active' WHERE singleton = 1")
        return result

    def claim_update(
        self,
        update_id: int,
        *,
        claimed_at: datetime | str | None = None,
    ) -> bool:
        """Atomically claim a stable Telegram update ID exactly once.

        IDs are retained individually, so an older unseen ID remains claimable;
        this is not a max-seen cursor.  The method stores no Telegram user,
        chat, username, or message body.
        """

        if (
            isinstance(update_id, bool)
            or not isinstance(update_id, int)
            or not 0 <= update_id <= (1 << 31) - 1
        ):
            raise ValueError("update_id is invalid")
        now = _timestamp(claimed_at)
        self._begin()
        try:
            if self.binding() is not None:
                raise BindingStateError("bound Ops requires atomic process_update_once, not legacy claims")
            inserted = self.conn.execute(
                "INSERT OR IGNORE INTO telegram_updates (update_id, claimed_at) VALUES (?, ?)",
                (update_id, now),
            ).rowcount
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        self._secure_files()
        return inserted == 1

    @staticmethod
    def _check_query_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return limit

    def _require_committed_projection(self) -> None:
        if self.staged_anchor() is not None:
            raise CursorStateError(
                "safe projection is unavailable until the exact staged page is committed"
            )
        if self.committed_anchor() is None:
            raise CursorStateError(
                "safe projection is unavailable until a gateway cursor is initialized"
            )

    @staticmethod
    def _task_projection(row: sqlite3.Row) -> Any:
        # Lazy import keeps the offline store usable without creating a reverse
        # dependency from the command parser to the storage layer.
        from .ops_service import SafeTaskProjection

        return SafeTaskProjection(
            task_id=str(row["task_ref"]),
            state=str(row["state"]),
            version=int(row["version"]),
            review_state=str(row["review_state"]),
            coordination_lease_recorded=bool(row["coordination_lease_recorded"]),
            summary=str(row["safe_summary"]),
            evidence_reference_count=int(row["evidence_reference_count"]),
            last_observed_at=str(row["last_observed_at"]),
        )

    def status_snapshot(self) -> Any:
        """Return the command surface's minimized observed-status projection."""

        from .ops_service import OpsStatusProjection

        self._require_committed_projection()
        task_counts = {
            state: 0
            for state in (
                "open",
                "claimed",
                "blocked",
                "reported_complete",
                "completed",
            )
        }
        for row in self.conn.execute(
            "SELECT state, COUNT(*) AS count FROM safe_tasks GROUP BY state"
        ):
            if str(row["state"]) in task_counts:
                task_counts[str(row["state"])] = int(row["count"])
        pending_reviews = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM safe_tasks WHERE review_state = 'pending'"
            ).fetchone()[0]
        )
        session_row = self.conn.execute(
            """SELECT COUNT(*) AS total,
                      COALESCE(SUM(recorded_active), 0) AS active,
                      MAX(last_observed_at) AS latest
               FROM safe_sessions"""
        ).fetchone()
        anchor = self.committed_anchor()
        return OpsStatusProjection(
            workspace_alias=self.workspace_alias,
            observed_at=_timestamp(),
            journal_head_sequence=anchor.sequence if anchor is not None else 0,
            open_tasks=task_counts["open"],
            claimed_tasks=task_counts["claimed"],
            blocked_tasks=task_counts["blocked"],
            reported_complete_tasks=task_counts["reported_complete"],
            completed_tasks=task_counts["completed"],
            pending_reviews=pending_reviews,
            session_records_observed=int(session_row["total"]),
            sessions_recorded_active=int(session_row["active"]),
            latest_session_event_at=(
                str(session_row["latest"])
                if session_row["latest"] is not None
                else None
            ),
        )

    def list_tasks(self, *, limit: int) -> tuple[Any, ...]:
        self._require_committed_projection()
        limit = self._check_query_limit(limit)
        rows = self.conn.execute(
            """SELECT * FROM safe_tasks
               ORDER BY last_sequence DESC, task_ref ASC LIMIT ?""",
            (limit,),
        ).fetchall()
        return tuple(self._task_projection(row) for row in rows)

    def get_task(self, task_id: str) -> Any | None:
        self._require_committed_projection()
        if (
            not isinstance(task_id, str)
            or _OPAQUE_REF.fullmatch(task_id) is None
            or not task_id.startswith("tsk_")
        ):
            raise ValueError("task_id is invalid")
        row = self.conn.execute(
            "SELECT * FROM safe_tasks WHERE task_ref = ?", (task_id,)
        ).fetchone()
        return self._task_projection(row) if row is not None else None

    def recent_events(self, *, limit: int) -> tuple[Any, ...]:
        from .ops_service import SafeEventProjection as OpsSafeEventProjection

        self._require_committed_projection()
        selected = self.recent_projections(limit=self._check_query_limit(limit))
        return tuple(
            OpsSafeEventProjection(
                event_id=event.event_key,
                kind=event.event_kind,
                observed_at=event.observed_at,
                summary=event.summary,
                task_id=(
                    event.subject_ref
                    if event.subject_ref.startswith("tsk_")
                    else None
                ),
            )
            for event in selected
        )

    def record_journal_verification(
        self,
        *,
        outcome: Literal["valid", "invalid", "unavailable"],
        checked_at: datetime | str,
        journal_head_sequence: int | None,
        scope_code: Literal[
            "full_collab_hash_chain", "full_collab_hash_chain_unavailable"
        ],
    ) -> None:
        """Persist a bounded result supplied by a separate one-shot verifier.

        No provider error, path, report body, or verifier identity is accepted.
        This method records the supplied result; it does not perform the check.
        """

        if outcome not in {"valid", "invalid", "unavailable"}:
            raise ValueError("verification outcome is invalid")
        if scope_code not in {
            "full_collab_hash_chain",
            "full_collab_hash_chain_unavailable",
        }:
            raise ValueError("verification scope_code is invalid")
        if journal_head_sequence is not None and (
            isinstance(journal_head_sequence, bool)
            or not isinstance(journal_head_sequence, int)
            or not 0 <= journal_head_sequence <= (1 << 63) - 1
        ):
            raise ValueError("journal_head_sequence is invalid")
        if outcome in {"valid", "invalid"}:
            if scope_code != "full_collab_hash_chain":
                raise ValueError(
                    "a completed verification requires its full-chain scope"
                )
            if outcome == "valid" and journal_head_sequence is None:
                raise ValueError("a valid verification requires its exact head")
        elif scope_code != "full_collab_hash_chain_unavailable":
            raise ValueError("an unavailable verification requires unavailable scope")
        checked = _timestamp(checked_at)
        self._begin()
        try:
            self.conn.execute(
                """INSERT INTO journal_verification (
                     singleton, outcome, checked_at, journal_head_sequence, scope_code
                   ) VALUES (1, ?, ?, ?, ?)
                   ON CONFLICT(singleton) DO UPDATE SET
                     outcome = excluded.outcome,
                     checked_at = excluded.checked_at,
                     journal_head_sequence = excluded.journal_head_sequence,
                     scope_code = excluded.scope_code""",
                (outcome, checked, journal_head_sequence, scope_code),
            )
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        self._secure_files()

    def journal_verify(self) -> Any:
        """Return the latest separately supplied full-journal check, if any."""

        from .ops_service import JournalVerificationProjection

        if self.staged_anchor() is not None:
            raise CursorStateError(
                "verification projection is unavailable until the exact staged page is committed"
            )
        row = self.conn.execute(
            "SELECT * FROM journal_verification WHERE singleton = 1"
        ).fetchone()
        if row is not None:
            scopes = {
                "full_collab_hash_chain": (
                    "full Collab journal hash-chain recomputation through supplied head"
                ),
                "full_collab_hash_chain_unavailable": (
                    "full Collab journal hash-chain recomputation unavailable"
                ),
            }
            return JournalVerificationProjection(
                outcome=str(row["outcome"]),
                checked_at=str(row["checked_at"]),
                journal_head_sequence=(
                    int(row["journal_head_sequence"])
                    if row["journal_head_sequence"] is not None
                    else None
                ),
                verification_scope=scopes[str(row["scope_code"])],
            )
        anchor = self.committed_anchor()
        return JournalVerificationProjection(
            outcome="unavailable",
            checked_at="not performed",
            journal_head_sequence=anchor.sequence if anchor is not None else None,
            verification_scope=(
                "offline page linkage only; Collab hash recomputation not performed"
            ),
        )

    def claim_delivery(
        self,
        event_key: str,
        *,
        attempted_at: datetime | str | None = None,
        retry_failed: bool = False,
    ) -> OutboxItem:
        """Reserve one delivery; ambiguous/inflight records are never retried."""

        if not isinstance(event_key, str) or _EVENT_KEY.fullmatch(event_key) is None:
            raise ValueError("event_key is invalid")
        if not isinstance(retry_failed, bool):
            raise ValueError("retry_failed must be a boolean")
        now = _timestamp(attempted_at)
        self._begin()
        try:
            if self.binding() is not None:
                raise BindingStateError("event alert delivery is disabled for bound Ops transport")
            row = self.conn.execute(
                """SELECT o.*,
                          CASE WHEN e.epoch_id = c.committed_epoch
                                     AND e.sequence <= c.committed_sequence
                               THEN 1 ELSE 0 END AS cursor_committed
                   FROM ops_outbox AS o
                   JOIN safe_events AS e ON e.event_key = o.event_key
                   JOIN cursor_state AS c ON c.singleton = 1
                   WHERE o.event_key = ?""",
                (event_key,),
            ).fetchone()
            if row is None:
                raise DeliveryStateError("outbox event does not exist")
            if not bool(row["cursor_committed"]):
                raise DeliveryStateError(
                    "event page is staged but its gateway cursor is not committed"
                )
            state = str(row["state"])
            if state == "sent":
                self.conn.commit()
                return self._outbox_item(row, duplicate=True)
            if state in {"inflight", "unknown"}:
                raise DeliveryStateError(
                    "delivery outcome is ambiguous; reconcile before any retry"
                )
            if state == "failed" and not retry_failed:
                raise DeliveryStateError(
                    "delivery previously failed; retry requires explicit review"
                )
            self.conn.execute(
                """UPDATE ops_outbox
                   SET state = 'inflight', attempt_count = attempt_count + 1,
                       last_attempted_at = ?, finished_at = NULL,
                       receipt_ref = NULL, error_code = NULL,
                       reconciled_at = NULL, reconciliation_ref = NULL
                   WHERE event_key = ?""",
                (now, event_key),
            )
            refreshed = self.conn.execute(
                "SELECT * FROM ops_outbox WHERE event_key = ?", (event_key,)
            ).fetchone()
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        if refreshed is None:
            raise DeliveryStateError("outbox receipt disappeared")
        self._secure_files()
        return self._outbox_item(refreshed)

    @staticmethod
    def _check_machine_label(value: str | None, label: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or _MACHINE_LABEL.fullmatch(value) is None:
            raise ValueError(f"{label} is invalid")
        return value

    def finish_delivery(
        self,
        event_key: str,
        *,
        attempt_count: int = 1,
        state: Literal["sent", "failed", "unknown"],
        receipt_ref: str | None = None,
        error_code: str | None = None,
        finished_at: datetime | str | None = None,
    ) -> OutboxItem:
        if not isinstance(event_key, str) or _EVENT_KEY.fullmatch(event_key) is None:
            raise ValueError("event_key is invalid")
        if state not in {"sent", "failed", "unknown"}:
            raise ValueError("delivery finish state is invalid")
        receipt_ref = self._check_machine_label(receipt_ref, "receipt_ref")
        error_code = self._check_machine_label(error_code, "error_code")
        if state == "sent":
            if receipt_ref is None:
                raise ValueError("sent delivery requires a receipt_ref")
            error_code = None
        elif receipt_ref is not None:
            raise ValueError("only a sent delivery may store a receipt_ref")
        now = _timestamp(finished_at)
        self._begin()
        try:
            row = self.conn.execute(
                "SELECT state, attempt_count FROM ops_outbox WHERE event_key = ?", (event_key,)
            ).fetchone()
            if row is None:
                raise DeliveryStateError("outbox event does not exist")
            if row["state"] != "inflight":
                raise DeliveryStateError("only an inflight delivery can be finished")
            self._positive_id(attempt_count, "attempt_count", (1 << 63) - 1)
            if row["attempt_count"] != attempt_count:
                raise DeliveryStateError("event delivery attempt is stale")
            self.conn.execute(
                """UPDATE ops_outbox
                   SET state = ?, receipt_ref = ?, error_code = ?, finished_at = ?
                   WHERE event_key = ?""",
                (state, receipt_ref, error_code, now, event_key),
            )
            refreshed = self.conn.execute(
                "SELECT * FROM ops_outbox WHERE event_key = ?", (event_key,)
            ).fetchone()
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        if refreshed is None:
            raise DeliveryStateError("outbox receipt disappeared")
        self._secure_files()
        return self._outbox_item(refreshed)

    def reconcile_unknown(
        self,
        event_key: str,
        *,
        attempt_count: int = 1,
        outcome: Literal["sent", "failed"],
        reconciliation_ref: str,
        receipt_ref: str | None = None,
        reconciled_at: datetime | str | None = None,
    ) -> OutboxItem:
        """Record an explicit provider/operator check for an ambiguous outcome."""

        if not isinstance(event_key, str) or _EVENT_KEY.fullmatch(event_key) is None:
            raise ValueError("event_key is invalid")
        if outcome not in {"sent", "failed"}:
            raise ValueError("reconciliation outcome is invalid")
        reconciliation_ref = self._check_machine_label(
            reconciliation_ref, "reconciliation_ref"
        )  # type: ignore[assignment]
        if reconciliation_ref is None:
            raise ValueError("reconciliation_ref is required")
        receipt_ref = self._check_machine_label(receipt_ref, "receipt_ref")
        if outcome == "sent" and receipt_ref is None:
            raise ValueError("sent reconciliation requires a receipt_ref")
        if outcome == "failed" and receipt_ref is not None:
            raise ValueError("failed reconciliation cannot store a receipt_ref")
        now = _timestamp(reconciled_at)
        self._begin()
        try:
            row = self.conn.execute(
                "SELECT state, attempt_count FROM ops_outbox WHERE event_key = ?", (event_key,)
            ).fetchone()
            if row is None:
                raise DeliveryStateError("outbox event does not exist")
            self._positive_id(attempt_count, "attempt_count", (1 << 63) - 1)
            if row["attempt_count"] != attempt_count:
                raise DeliveryStateError("event delivery attempt is stale")
            if row["state"] not in {"inflight", "unknown"}:
                raise DeliveryStateError(
                    "only an inflight or unknown delivery can be reconciled"
                )
            self.conn.execute(
                """UPDATE ops_outbox
                   SET state = ?, receipt_ref = ?, error_code = NULL,
                       finished_at = ?, reconciled_at = ?, reconciliation_ref = ?
                   WHERE event_key = ?""",
                (
                    outcome,
                    receipt_ref,
                    now,
                    now,
                    reconciliation_ref,
                    event_key,
                ),
            )
            refreshed = self.conn.execute(
                "SELECT * FROM ops_outbox WHERE event_key = ?", (event_key,)
            ).fetchone()
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        if refreshed is None:
            raise DeliveryStateError("outbox receipt disappeared")
        self._secure_files()
        return self._outbox_item(refreshed)


__all__ = [
    "AgentToolOpsStore",
    "BindingStateError",
    "MigrationRequiredError",
    "OpsBinding",
    "PollState",
    "ReplyItem",
    "UpdateDisposition",
    "OPS_CREDENTIAL_PREFIX",
    "OPS_V1_DATABASE_ROLE",
    "POLL_EPOCH_IDLE_SECONDS",
    "REPLY_ERROR_CODES",
    "TELEGRAM_PRODUCTION_ORIGIN",
    "CursorAnchor",
    "CursorCommit",
    "CursorStateError",
    "DatabaseRoleError",
    "DeliveryStateError",
    "MAX_PAGE_EVENTS",
    "OPS_DATABASE_ROLE",
    "OPS_DATABASE_ROLE_META_KEY",
    "OpsProjectionError",
    "OutboxItem",
    "PageStage",
    "ProjectionConflict",
    "SafeEventProjection",
    "ZERO_HASH",
    "project_collab_event",
]
