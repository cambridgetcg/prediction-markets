"""Consent-bound Telegram research preferences with local SQLite persistence.

This module is deliberately transport-neutral.  It stores only numeric private-chat
identifiers, allowlisted topic codes, a bounded delivery cadence, and opaque market
references.  It does not store usernames, message bodies, wallet data, credentials,
or inferred interests.

Every mutation takes the Telegram update ID and event time.  Event time is the
primary ordering key because Telegram update IDs may reset after a sufficiently
long idle period.  Withdrawal and privacy deletion erase the preference profile
atomically while retaining one minimal no-contact watermark; only a newer explicit
consent event can create another profile.
"""

from __future__ import annotations

import contextlib
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal, Sequence, cast


PREFERENCE_SCHEMA_VERSION = "1"
DEFAULT_PREFERENCE_NOTICE_VERSION = "2026-09-03-preferences-v1"
DEFAULT_TOPIC_CODES = (
    "macro-policy",
    "economic-releases",
    "elections",
    "geopolitics",
    "financial-markets",
    "crypto-assets",
    "technology-ai",
    "science-health",
    "society-culture",
    "legal-regulation",
    "environment-energy",
)
ALLOWED_CADENCES = frozenset({"realtime", "daily", "weekly"})
DEFAULT_CADENCE = "weekly"

MAX_TELEGRAM_USER_ID = (1 << 52) - 1
MAX_TELEGRAM_UPDATE_ID = (1 << 31) - 1
MAX_TOPICS = 32
MAX_WATCHLIST_ITEMS = 50
MAX_MARKET_REF_BYTES = 256
MAX_FUTURE_EVENT_SKEW = timedelta(minutes=5)

_TOPIC_CODE = re.compile(r"^[a-z][a-z0-9-]{0,39}$")
_NOTICE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_MARKET_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")

ConsentState = Literal[
    "active",
    "needs_reconfirmation",
    "not_joined",
    "withdrawn",
    "deleted",
]
MutationReason = Literal[
    "applied",
    "stale_update",
    "consent_required",
    "notice_reconfirmation_required",
]


@dataclass(frozen=True)
class PreferenceMutation:
    """Result of a consent or preference mutation.

    ``accepted`` means the update passed ordering and consent checks. ``changed``
    describes user-visible preference/consent state, not internal watermarks.
    ``removed_records`` is populated by withdrawal and privacy deletion only.
    """

    accepted: bool
    changed: bool
    reason: MutationReason
    removed_records: int = 0


@dataclass(frozen=True)
class PreferenceSnapshot:
    """One coherent, immutable view of a Telegram user's preference state."""

    telegram_user_id: int
    consent_state: ConsentState
    notice_version: str | None
    cadence: str | None
    topics: tuple[str, ...]
    watchlist: tuple[str, ...]
    consented_at: datetime | None
    updated_at: datetime | None

    @property
    def active(self) -> bool:
        return self.consent_state == "active"


class PreferenceLimitError(ValueError):
    """A bounded preference collection would exceed its configured limit."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime, *, label: str = "timestamp") -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    current = value.astimezone(timezone.utc)
    if not datetime(2020, 1, 1, tzinfo=timezone.utc) <= current <= datetime(
        2100, 1, 1, tzinfo=timezone.utc
    ):
        raise ValueError(f"{label} is outside the supported date range")
    return current.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("stored timestamp does not include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_identity(telegram_user_id: Any, private_chat_id: Any | None = None) -> int:
    if (
        isinstance(telegram_user_id, bool)
        or not isinstance(telegram_user_id, int)
        or not 0 < telegram_user_id <= MAX_TELEGRAM_USER_ID
        or (private_chat_id is not None and private_chat_id != telegram_user_id)
    ):
        raise ValueError("private Telegram user/chat identity is invalid")
    return telegram_user_id


def _validate_update_id(telegram_update_id: Any) -> int:
    if (
        isinstance(telegram_update_id, bool)
        or not isinstance(telegram_update_id, int)
        or not 0 <= telegram_update_id <= MAX_TELEGRAM_UPDATE_ID
    ):
        raise ValueError("Telegram update ID is invalid")
    return telegram_update_id


def _validate_notice_version(value: Any) -> str:
    if not isinstance(value, str) or not _NOTICE_VERSION.fullmatch(value):
        raise ValueError("preference notice version is invalid")
    return value


def _validate_topic_code(value: Any) -> str:
    if not isinstance(value, str) or not _TOPIC_CODE.fullmatch(value):
        raise ValueError("topic code is invalid")
    return value


def _validate_cadence(value: Any) -> str:
    if not isinstance(value, str) or value not in ALLOWED_CADENCES:
        allowed = ", ".join(sorted(ALLOWED_CADENCES))
        raise ValueError(f"cadence must be one of: {allowed}")
    return value


def _validate_market_ref(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("market reference is invalid")
    try:
        encoded = value.encode("ascii", errors="strict")
    except UnicodeError as exc:
        raise ValueError("market reference is invalid") from exc
    if (
        not encoded
        or len(encoded) > MAX_MARKET_REF_BYTES
        or not _MARKET_REF.fullmatch(value)
    ):
        raise ValueError("market reference is invalid")
    return value


def _event_values(
    event_at: datetime | None,
    now: datetime | None,
) -> tuple[datetime, datetime, str, str]:
    received = now or _utc_now()
    received_iso = _iso_utc(received, label="receipt time")
    occurred = event_at or received
    occurred_iso = _iso_utc(occurred, label="event time")
    received_utc = _parse_utc(received_iso)
    occurred_utc = _parse_utc(occurred_iso)
    if occurred_utc > received_utc + MAX_FUTURE_EVENT_SKEW:
        raise ValueError("event time is too far in the future")
    return occurred_utc, received_utc, occurred_iso, received_iso


def _is_newer(
    event_at: datetime,
    update_id: int,
    stored_event_at: str,
    stored_update_id: int,
) -> bool:
    # An exact update ID is a replay even if an inconsistent caller supplies a
    # different timestamp.  Otherwise event time dominates IDs so a legitimate
    # post-idle Telegram update-ID reset cannot freeze the profile.
    if update_id == stored_update_id:
        return False
    return (event_at, update_id) > (_parse_utc(stored_event_at), stored_update_id)


class PreferenceStore:
    """SQLite-backed topic, cadence, and watchlist preferences.

    A deployment may place this schema in its gateway database or in a separate
    owner-only database.  Table names are namespaced and the component does not
    depend on :class:`telegram_gateway.store.GatewayStore`.

    ``realtime`` is a delivery preference, not a promise: policy, safety, global
    frequency limits, and corrections may override any requested cadence.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        notice_version: str = DEFAULT_PREFERENCE_NOTICE_VERSION,
        topic_codes: Sequence[str] = DEFAULT_TOPIC_CODES,
        default_cadence: str = DEFAULT_CADENCE,
    ) -> None:
        self.notice_version = _validate_notice_version(notice_version)
        self.default_cadence = _validate_cadence(default_cadence)
        if isinstance(topic_codes, (str, bytes)):
            raise ValueError("topic catalog must be a sequence of topic codes")
        if not 1 <= len(topic_codes) <= MAX_TOPICS:
            raise ValueError("topic catalog must contain 1 to 32 unique topic codes")
        catalog = tuple(_validate_topic_code(item) for item in topic_codes)
        if len(set(catalog)) != len(catalog):
            raise ValueError("topic catalog must contain 1 to 32 unique topic codes")
        self.topic_codes = catalog
        self._topic_set = frozenset(catalog)

        self.path = Path(db_path).expanduser().resolve()
        parent_existed = self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent_existed and stat.S_IMODE(self.path.parent.stat().st_mode) & 0o077:
            raise PermissionError(
                f"preference database directory must be owner-only (0700): {self.path.parent}"
            )
        if not self.path.exists():
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        elif not self.path.is_file():
            raise ValueError("preference database path must be a regular file")
        else:
            try:
                self.path.chmod(0o600)
            except OSError:
                pass

        self.conn = sqlite3.connect(str(self.path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=2000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA secure_delete=ON")
        self.conn.execute("PRAGMA trusted_schema=OFF")
        self._initialize_schema()
        self._secure_sqlite_files()

    def _initialize_schema(self) -> None:
        statements = (
            """CREATE TABLE IF NOT EXISTS preference_store_meta (
                   key TEXT PRIMARY KEY,
                   value TEXT NOT NULL
               )""",
            """CREATE TABLE IF NOT EXISTS preference_profiles (
                   telegram_user_id INTEGER PRIMARY KEY
                       CHECK (telegram_user_id > 0),
                   private_chat_id INTEGER NOT NULL
                       CHECK (private_chat_id = telegram_user_id),
                   notice_version TEXT NOT NULL,
                   cadence TEXT NOT NULL
                       CHECK (cadence IN ('realtime', 'daily', 'weekly')),
                   consented_at TEXT NOT NULL,
                   last_event_at TEXT NOT NULL,
                   last_update_id INTEGER NOT NULL
                       CHECK (last_update_id >= 0),
                   updated_at TEXT NOT NULL
               )""",
            """CREATE TABLE IF NOT EXISTS preference_topics (
                   telegram_user_id INTEGER NOT NULL,
                   topic_code TEXT NOT NULL,
                   selected_at TEXT NOT NULL,
                   PRIMARY KEY (telegram_user_id, topic_code),
                   FOREIGN KEY (telegram_user_id)
                       REFERENCES preference_profiles(telegram_user_id)
                       ON DELETE CASCADE
               )""",
            """CREATE TABLE IF NOT EXISTS preference_watchlist (
                   telegram_user_id INTEGER NOT NULL,
                   market_ref TEXT NOT NULL,
                   watched_at TEXT NOT NULL,
                   PRIMARY KEY (telegram_user_id, market_ref),
                   FOREIGN KEY (telegram_user_id)
                       REFERENCES preference_profiles(telegram_user_id)
                       ON DELETE CASCADE
               )""",
            """CREATE TABLE IF NOT EXISTS preference_suppressions (
                   telegram_user_id INTEGER PRIMARY KEY
                       CHECK (telegram_user_id > 0),
                   reason TEXT NOT NULL CHECK (reason IN ('withdrawn', 'deleted')),
                   event_at TEXT NOT NULL,
                   update_id INTEGER NOT NULL CHECK (update_id >= 0),
                   recorded_at TEXT NOT NULL
               )""",
        )
        with self._write_transaction():
            for statement in statements:
                self.conn.execute(statement)
            row = self.conn.execute(
                "SELECT value FROM preference_store_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row and row["value"] != PREFERENCE_SCHEMA_VERSION:
                raise ValueError("unsupported preference database schema version")
            self.conn.execute(
                """INSERT OR IGNORE INTO preference_store_meta (key, value)
                   VALUES ('schema_version', ?)""",
                (PREFERENCE_SCHEMA_VERSION,),
            )

    @contextlib.contextmanager
    def _write_transaction(self) -> Iterator[None]:
        if self.conn.in_transaction:
            raise sqlite3.OperationalError(
                "atomic preference operation cannot run inside another transaction"
            )
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            if not self.conn.in_transaction:
                raise sqlite3.OperationalError(
                    "atomic preference operation ended its transaction early"
                )
            self.conn.commit()
        except BaseException:
            try:
                self.conn.rollback()
            except BaseException:
                self.conn.close()
                raise sqlite3.OperationalError("atomic preference rollback failed") from None
            if self.conn.in_transaction:
                self.conn.close()
                raise sqlite3.OperationalError(
                    "atomic preference rollback did not finish"
                ) from None
            raise
        finally:
            self._secure_sqlite_files()

    @contextlib.contextmanager
    def _read_transaction(self) -> Iterator[None]:
        if self.conn.in_transaction:
            raise sqlite3.OperationalError(
                "preference snapshot cannot run inside another transaction"
            )
        self.conn.execute("BEGIN")
        try:
            yield
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    def _secure_sqlite_files(self) -> None:
        for path in (
            self.path,
            Path(str(self.path) + "-wal"),
            Path(str(self.path) + "-shm"),
        ):
            if path.exists():
                try:
                    path.chmod(0o600)
                except OSError:
                    pass

    def available_topics(self) -> tuple[str, ...]:
        return self.topic_codes

    def _latest_row(self, telegram_user_id: int) -> sqlite3.Row | None:
        rows = self.conn.execute(
            """SELECT last_event_at AS event_at, last_update_id AS update_id
                 FROM preference_profiles WHERE telegram_user_id = ?
               UNION ALL
               SELECT event_at, update_id FROM preference_suppressions
                 WHERE telegram_user_id = ?""",
            (telegram_user_id, telegram_user_id),
        ).fetchall()
        if not rows:
            return None
        return max(
            rows,
            key=lambda row: (_parse_utc(str(row["event_at"])), int(row["update_id"])),
        )

    @staticmethod
    def _preference_gate_reason(
        profile: sqlite3.Row | None, current_notice: str
    ) -> MutationReason | None:
        if profile is None:
            return "consent_required"
        if str(profile["notice_version"]) != current_notice:
            return "notice_reconfirmation_required"
        return None

    def grant_consent(
        self,
        telegram_user_id: int,
        private_chat_id: int,
        telegram_update_id: int,
        *,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> PreferenceMutation:
        """Record explicit consent to the currently configured preference notice."""

        user_id = _validate_identity(telegram_user_id, private_chat_id)
        update_id = _validate_update_id(telegram_update_id)
        occurred, _, occurred_iso, received_iso = _event_values(event_at, now)
        with self._write_transaction():
            latest = self._latest_row(user_id)
            if latest and not _is_newer(
                occurred,
                update_id,
                str(latest["event_at"]),
                int(latest["update_id"]),
            ):
                return PreferenceMutation(False, False, "stale_update")
            profile = self.conn.execute(
                "SELECT notice_version FROM preference_profiles WHERE telegram_user_id = ?",
                (user_id,),
            ).fetchone()
            changed = profile is None or str(profile["notice_version"]) != self.notice_version
            if profile is None:
                self.conn.execute(
                    """INSERT INTO preference_profiles
                       (telegram_user_id, private_chat_id, notice_version, cadence,
                        consented_at, last_event_at, last_update_id, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user_id,
                        private_chat_id,
                        self.notice_version,
                        self.default_cadence,
                        occurred_iso,
                        occurred_iso,
                        update_id,
                        received_iso,
                    ),
                )
            else:
                self.conn.execute(
                    """UPDATE preference_profiles
                       SET private_chat_id = ?, notice_version = ?,
                           consented_at = CASE
                               WHEN notice_version != ? THEN ? ELSE consented_at END,
                           last_event_at = ?, last_update_id = ?, updated_at = ?
                       WHERE telegram_user_id = ?""",
                    (
                        private_chat_id,
                        self.notice_version,
                        self.notice_version,
                        occurred_iso,
                        occurred_iso,
                        update_id,
                        received_iso,
                        user_id,
                    ),
                )
            self.conn.execute(
                "DELETE FROM preference_suppressions WHERE telegram_user_id = ?",
                (user_id,),
            )
            return PreferenceMutation(True, changed, "applied")

    def _suppress_and_purge(
        self,
        telegram_user_id: int,
        telegram_update_id: int,
        reason: Literal["withdrawn", "deleted"],
        *,
        event_at: datetime | None,
        now: datetime | None,
    ) -> PreferenceMutation:
        user_id = _validate_identity(telegram_user_id)
        update_id = _validate_update_id(telegram_update_id)
        occurred, _, occurred_iso, received_iso = _event_values(event_at, now)
        with self._write_transaction():
            latest = self._latest_row(user_id)
            if latest and not _is_newer(
                occurred,
                update_id,
                str(latest["event_at"]),
                int(latest["update_id"]),
            ):
                return PreferenceMutation(False, False, "stale_update")
            prior_suppression = self.conn.execute(
                """SELECT reason FROM preference_suppressions
                   WHERE telegram_user_id = ?""",
                (user_id,),
            ).fetchone()
            topic_count = int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM preference_topics WHERE telegram_user_id = ?",
                    (user_id,),
                ).fetchone()[0]
            )
            watch_count = int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM preference_watchlist WHERE telegram_user_id = ?",
                    (user_id,),
                ).fetchone()[0]
            )
            profile_count = self.conn.execute(
                "DELETE FROM preference_profiles WHERE telegram_user_id = ?",
                (user_id,),
            ).rowcount
            stored_reason = (
                "deleted"
                if prior_suppression and prior_suppression["reason"] == "deleted"
                else reason
            )
            self.conn.execute(
                """INSERT INTO preference_suppressions
                   (telegram_user_id, reason, event_at, update_id, recorded_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(telegram_user_id) DO UPDATE SET
                     reason = excluded.reason,
                     event_at = excluded.event_at,
                     update_id = excluded.update_id,
                     recorded_at = excluded.recorded_at""",
                (user_id, stored_reason, occurred_iso, update_id, received_iso),
            )
            removed = int(profile_count) + topic_count + watch_count
            changed = bool(
                removed
                or prior_suppression is None
                or str(prior_suppression["reason"]) != stored_reason
            )
            return PreferenceMutation(True, changed, "applied", removed)

    def withdraw_consent(
        self,
        telegram_user_id: int,
        telegram_update_id: int,
        *,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> PreferenceMutation:
        """Erase preferences and retain only a minimal withdrawal watermark."""

        return self._suppress_and_purge(
            telegram_user_id,
            telegram_update_id,
            "withdrawn",
            event_at=event_at,
            now=now,
        )

    def delete_user(
        self,
        telegram_user_id: int,
        telegram_update_id: int,
        *,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> PreferenceMutation:
        """Erase all preference data and retain only a deletion watermark."""

        return self._suppress_and_purge(
            telegram_user_id,
            telegram_update_id,
            "deleted",
            event_at=event_at,
            now=now,
        )

    def _begin_preference_mutation(
        self,
        telegram_user_id: int,
        telegram_update_id: int,
        event_at: datetime | None,
        now: datetime | None,
    ) -> tuple[PreferenceMutation | None, sqlite3.Row | None, str, str]:
        user_id = _validate_identity(telegram_user_id)
        update_id = _validate_update_id(telegram_update_id)
        occurred, _, occurred_iso, received_iso = _event_values(event_at, now)
        profile = self.conn.execute(
            """SELECT notice_version, last_event_at, last_update_id
               FROM preference_profiles WHERE telegram_user_id = ?""",
            (user_id,),
        ).fetchone()
        suppression = self.conn.execute(
            "SELECT 1 FROM preference_suppressions WHERE telegram_user_id = ?",
            (user_id,),
        ).fetchone()
        if suppression is not None:
            # Both rows cannot arise through this API.  If manual database
            # changes create them, fail closed until explicit consent repairs
            # the state through ``grant_consent``.
            return (
                PreferenceMutation(False, False, "consent_required"),
                profile,
                occurred_iso,
                received_iso,
            )
        gate = self._preference_gate_reason(profile, self.notice_version)
        if gate is not None:
            return PreferenceMutation(False, False, gate), profile, occurred_iso, received_iso
        assert profile is not None
        if not _is_newer(
            occurred,
            update_id,
            str(profile["last_event_at"]),
            int(profile["last_update_id"]),
        ):
            return (
                PreferenceMutation(False, False, "stale_update"),
                profile,
                occurred_iso,
                received_iso,
            )
        return None, profile, occurred_iso, received_iso

    def _advance_profile(
        self,
        telegram_user_id: int,
        telegram_update_id: int,
        event_at_iso: str,
        received_at_iso: str,
    ) -> None:
        cursor = self.conn.execute(
            """UPDATE preference_profiles
               SET last_event_at = ?, last_update_id = ?, updated_at = ?
               WHERE telegram_user_id = ? AND notice_version = ?""",
            (
                event_at_iso,
                telegram_update_id,
                received_at_iso,
                telegram_user_id,
                self.notice_version,
            ),
        )
        if cursor.rowcount != 1:
            raise sqlite3.IntegrityError("preference consent changed during mutation")

    def replace_topics(
        self,
        telegram_user_id: int,
        topics: Iterable[str],
        telegram_update_id: int,
        *,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> PreferenceMutation:
        """Replace the selected topic set; an empty set is valid."""

        if isinstance(topics, (str, bytes)):
            raise ValueError("topics must be an iterable of topic codes")
        selected_values: list[str] = []
        for topic in topics:
            if len(selected_values) == MAX_TOPICS:
                raise PreferenceLimitError(
                    f"at most {MAX_TOPICS} topics may be selected"
                )
            selected_values.append(_validate_topic_code(topic))
        selected = tuple(selected_values)
        if len(set(selected)) != len(selected):
            raise ValueError("topics must not contain duplicates")
        unknown = sorted(set(selected) - self._topic_set)
        if unknown:
            raise ValueError(f"unknown topic code: {unknown[0]}")
        user_id = _validate_identity(telegram_user_id)
        update_id = _validate_update_id(telegram_update_id)
        with self._write_transaction():
            rejected, _, occurred_iso, received_iso = self._begin_preference_mutation(
                user_id, update_id, event_at, now
            )
            if rejected:
                return rejected
            current = {
                str(row["topic_code"])
                for row in self.conn.execute(
                    "SELECT topic_code FROM preference_topics WHERE telegram_user_id = ?",
                    (user_id,),
                )
            }
            desired = set(selected)
            changed = current != desired
            if changed:
                self.conn.execute(
                    "DELETE FROM preference_topics WHERE telegram_user_id = ?",
                    (user_id,),
                )
                self.conn.executemany(
                    """INSERT INTO preference_topics
                       (telegram_user_id, topic_code, selected_at) VALUES (?, ?, ?)""",
                    ((user_id, topic, occurred_iso) for topic in selected),
                )
            self._advance_profile(user_id, update_id, occurred_iso, received_iso)
            return PreferenceMutation(True, changed, "applied")

    def set_cadence(
        self,
        telegram_user_id: int,
        cadence: str,
        telegram_update_id: int,
        *,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> PreferenceMutation:
        selected = _validate_cadence(cadence)
        user_id = _validate_identity(telegram_user_id)
        update_id = _validate_update_id(telegram_update_id)
        with self._write_transaction():
            rejected, _, occurred_iso, received_iso = self._begin_preference_mutation(
                user_id, update_id, event_at, now
            )
            if rejected:
                return rejected
            row = self.conn.execute(
                "SELECT cadence FROM preference_profiles WHERE telegram_user_id = ?",
                (user_id,),
            ).fetchone()
            changed = str(row["cadence"]) != selected
            if changed:
                self.conn.execute(
                    "UPDATE preference_profiles SET cadence = ? WHERE telegram_user_id = ?",
                    (selected, user_id),
                )
            self._advance_profile(user_id, update_id, occurred_iso, received_iso)
            return PreferenceMutation(True, changed, "applied")

    def watch(
        self,
        telegram_user_id: int,
        market_ref: str,
        telegram_update_id: int,
        *,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> PreferenceMutation:
        reference = _validate_market_ref(market_ref)
        user_id = _validate_identity(telegram_user_id)
        update_id = _validate_update_id(telegram_update_id)
        with self._write_transaction():
            rejected, _, occurred_iso, received_iso = self._begin_preference_mutation(
                user_id, update_id, event_at, now
            )
            if rejected:
                return rejected
            exists = self.conn.execute(
                """SELECT 1 FROM preference_watchlist
                   WHERE telegram_user_id = ? AND market_ref = ?""",
                (user_id, reference),
            ).fetchone()
            if not exists:
                count = int(
                    self.conn.execute(
                        """SELECT COUNT(*) FROM preference_watchlist
                           WHERE telegram_user_id = ?""",
                        (user_id,),
                    ).fetchone()[0]
                )
                if count >= MAX_WATCHLIST_ITEMS:
                    raise PreferenceLimitError(
                        f"watchlist is limited to {MAX_WATCHLIST_ITEMS} markets"
                    )
                self.conn.execute(
                    """INSERT INTO preference_watchlist
                       (telegram_user_id, market_ref, watched_at) VALUES (?, ?, ?)""",
                    (user_id, reference, occurred_iso),
                )
            self._advance_profile(user_id, update_id, occurred_iso, received_iso)
            return PreferenceMutation(True, not bool(exists), "applied")

    def unwatch(
        self,
        telegram_user_id: int,
        market_ref: str,
        telegram_update_id: int,
        *,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> PreferenceMutation:
        reference = _validate_market_ref(market_ref)
        user_id = _validate_identity(telegram_user_id)
        update_id = _validate_update_id(telegram_update_id)
        with self._write_transaction():
            rejected, _, occurred_iso, received_iso = self._begin_preference_mutation(
                user_id, update_id, event_at, now
            )
            if rejected:
                return rejected
            removed = self.conn.execute(
                """DELETE FROM preference_watchlist
                   WHERE telegram_user_id = ? AND market_ref = ?""",
                (user_id, reference),
            ).rowcount
            self._advance_profile(user_id, update_id, occurred_iso, received_iso)
            return PreferenceMutation(True, bool(removed), "applied")

    def snapshot(self, telegram_user_id: int) -> PreferenceSnapshot:
        user_id = _validate_identity(telegram_user_id)
        with self._read_transaction():
            profile = self.conn.execute(
                """SELECT notice_version, cadence, consented_at, updated_at
                   FROM preference_profiles WHERE telegram_user_id = ?""",
                (user_id,),
            ).fetchone()
            suppression = self.conn.execute(
                """SELECT reason FROM preference_suppressions
                   WHERE telegram_user_id = ?""",
                (user_id,),
            ).fetchone()
            if profile is None or suppression is not None:
                state = cast(
                    ConsentState,
                    str(suppression["reason"]) if suppression else "not_joined",
                )
                return PreferenceSnapshot(
                    user_id, state, None, None, (), (), None, None
                )
            state = (
                "active"
                if str(profile["notice_version"]) == self.notice_version
                else "needs_reconfirmation"
            )
            selected = {
                str(row["topic_code"])
                for row in self.conn.execute(
                    "SELECT topic_code FROM preference_topics WHERE telegram_user_id = ?",
                    (user_id,),
                )
            }
            # A deployment changing its catalog must not make previously stored
            # data invisible.  Known topics retain catalog order; retired codes
            # remain visible until the user replaces or deletes the selection.
            topics = tuple(topic for topic in self.topic_codes if topic in selected) + tuple(
                sorted(selected - self._topic_set)
            )
            watchlist = tuple(
                str(row["market_ref"])
                for row in self.conn.execute(
                    """SELECT market_ref FROM preference_watchlist
                       WHERE telegram_user_id = ?
                       ORDER BY julianday(watched_at), market_ref""",
                    (user_id,),
                )
            )
            return PreferenceSnapshot(
                telegram_user_id=user_id,
                consent_state=state,
                notice_version=str(profile["notice_version"]),
                cadence=str(profile["cadence"]),
                topics=topics,
                watchlist=watchlist,
                consented_at=_parse_utc(str(profile["consented_at"])),
                updated_at=_parse_utc(str(profile["updated_at"])),
            )

    def compact_storage(self) -> None:
        """Operator-triggered removal of SQLite free pages and WAL remnants."""

        if self.conn.in_transaction:
            raise sqlite3.OperationalError("cannot compact during a transaction")
        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.execute("VACUUM")
        self._secure_sqlite_files()

    def close(self) -> None:
        self.conn.close()
        self._secure_sqlite_files()

    def __enter__(self) -> "PreferenceStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
