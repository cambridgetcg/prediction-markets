"""Idempotent publication service for canonical Telegram channel cards.

The module defines a deliberately narrow transport boundary: it can send one
plain-text channel post and nothing related to wallets, orders, private chats,
or payments.  External delivery is disabled by default.  The SQLite ledger
prevents automatic retries after an ambiguous send and keeps corrections
threaded to the message they supersede.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol

from .channel_cards import (
    MAX_CHANNEL_TEXT,
    channel_card_digest,
    render_channel_card,
    validate_channel_card,
)
from .promotion import validate_campaign_link
from .telegram_api import TelegramError, normalize_channel_ref


_PUBLICATION_ID = re.compile(r"kingdom-pub-[0-9a-f]{32}\Z")
_CAMPAIGN_CTA_PREFIX = "Private opt-in: receive KINGDOM research alerts"
_NO_TRADE_DISCLOSURE = "Information only. No return is promised. No trade was placed."
_NO_EXECUTION_DISCLOSURE = (
    "Paper/research mode only; live execution and wallet access are disabled."
)


class ChannelPublishingError(RuntimeError):
    """Base error for a local channel publication."""


class ExternalDeliveryDisabled(ChannelPublishingError):
    """External publication was attempted without an explicit runtime gate."""


class PublicationConflict(ChannelPublishingError):
    """A stable publication or revision ID was reused inconsistently."""


class PublicationStateError(ChannelPublishingError):
    """A publication needs reconciliation or an explicit retry decision."""


class ChannelPostTransport(Protocol):
    """Minimum external capability exposed to the publication service."""

    def send_channel_post(
        self,
        channel_ref: int | str,
        text: str,
        *,
        disable_link_preview: bool,
        disable_notification: bool,
        protect_content: bool,
        reply_to_message_id: int | None,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class PreparedChannelPost:
    publication_id: str
    channel_ref: int | str
    canonical_channel_ref: str
    card_id: str
    series_id: str
    signal_id: str
    revision: int
    status: str
    card_digest: str
    text_digest: str
    supersedes_card_id: str | None
    text: str
    campaign_link: str | None = None


@dataclass(frozen=True)
class PublicationReceipt:
    publication_id: str
    channel_ref: str
    card_id: str
    state: str
    attempt_count: int
    telegram_message_id: int | None
    reply_to_publication_id: str | None
    duplicate: bool = False


@dataclass(frozen=True)
class ChannelPublisherConfig:
    external_delivery_enabled: bool = False
    disable_notification: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.external_delivery_enabled, bool):
            raise ValueError("external_delivery_enabled must be a boolean")
        if not isinstance(self.disable_notification, bool):
            raise ValueError("disable_notification must be a boolean")


def _utc_timestamp(value: datetime | str | None = None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
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


def _campaign_cta(campaign_link: str) -> str:
    return (
        f"{_CAMPAIGN_CTA_PREFIX}\n"
        f"{campaign_link}\n"
        "Opening the bot does not enable alerts; opt in there. /leave stops them."
    )


def _validate_campaign_binding(post: PreparedChannelPost) -> None:
    marker = "\n\n" + _CAMPAIGN_CTA_PREFIX + "\n"
    if post.campaign_link is None:
        if marker in post.text:
            raise PublicationConflict(
                "prepared campaign metadata does not match the channel text"
            )
        return
    try:
        campaign_link = validate_campaign_link(post.campaign_link)
    except ValueError as exc:
        raise PublicationConflict("prepared campaign link is invalid") from exc
    expected_suffix = "\n\n" + _campaign_cta(campaign_link)
    if not post.text.endswith(expected_suffix) or post.text.count(marker) != 1:
        raise PublicationConflict(
            "prepared campaign metadata does not match the channel text"
        )


def prepare_channel_post(
    card: Mapping[str, Any],
    channel_ref: int | str,
    *,
    campaign_link: str | None = None,
) -> PreparedChannelPost:
    """Validate and render a deterministic post without any side effect."""

    validate_channel_card(card)
    transport_ref, canonical_ref = normalize_channel_ref(channel_ref)
    text = render_channel_card(card)
    if campaign_link is not None:
        campaign_link = validate_campaign_link(campaign_link)
        text += "\n\n" + _campaign_cta(campaign_link)
    if not text or len(text) > MAX_CHANNEL_TEXT:
        raise ValueError("rendered channel post is outside Telegram's text limit")
    digest = channel_card_digest(card)
    text_digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    material = (
        f"{canonical_ref}\0{card['card_id']}\0{digest}\0{text_digest}".encode("utf-8")
    )
    publication_id = "kingdom-pub-" + hashlib.sha256(material).hexdigest()[:32]
    return PreparedChannelPost(
        publication_id=publication_id,
        channel_ref=transport_ref,
        canonical_channel_ref=canonical_ref,
        card_id=card["card_id"],
        series_id=card["series_id"],
        signal_id=card["signal_id"],
        revision=card["revision"],
        status=card["status"],
        card_digest=digest,
        text_digest=text_digest,
        supersedes_card_id=card["lineage"]["supersedes_card_id"],
        text=text,
        campaign_link=campaign_link,
    )


class ChannelPublicationLedger:
    """Owner-only SQLite evidence for channel delivery and reconciliation."""

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path).expanduser().resolve()
        parent_existed = self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent_existed and stat.S_IMODE(self.path.parent.stat().st_mode) & 0o077:
            raise PermissionError(
                f"channel publication directory must be owner-only (0700): {self.path.parent}"
            )
        if not self.path.exists():
            descriptor = os.open(
                self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            os.close(descriptor)
        else:
            with contextlib.suppress(OSError):
                self.path.chmod(0o600)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=2000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA secure_delete=ON")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS channel_publications (
                publication_id TEXT PRIMARY KEY,
                channel_ref TEXT NOT NULL,
                card_id TEXT NOT NULL,
                series_id TEXT NOT NULL,
                signal_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK (revision > 0),
                card_digest TEXT NOT NULL,
                text_digest TEXT NOT NULL,
                card_status TEXT NOT NULL,
                state TEXT NOT NULL CHECK (
                    state IN ('pending', 'sent', 'failed', 'unknown')
                ),
                attempt_count INTEGER NOT NULL CHECK (attempt_count > 0),
                telegram_message_id INTEGER,
                reply_to_publication_id TEXT,
                error_code TEXT,
                prepared_at TEXT NOT NULL,
                last_attempted_at TEXT NOT NULL,
                sent_at TEXT,
                reconciled_at TEXT,
                reconciliation_ref TEXT,
                UNIQUE (channel_ref, card_id),
                UNIQUE (channel_ref, series_id, revision),
                FOREIGN KEY (reply_to_publication_id)
                    REFERENCES channel_publications(publication_id) ON DELETE RESTRICT
            );
            CREATE INDEX IF NOT EXISTS idx_channel_publication_series
                ON channel_publications(channel_ref, series_id, revision);
            """
        )
        self.conn.commit()
        self._secure_files()

    def _secure_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(self.path) + suffix)
            if candidate.exists():
                with contextlib.suppress(OSError):
                    candidate.chmod(0o600)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ChannelPublicationLedger":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _transaction(self) -> None:
        if self.conn.in_transaction:
            raise sqlite3.OperationalError("publication ledger transaction is already active")
        self.conn.execute("BEGIN IMMEDIATE")

    @staticmethod
    def _check_post(post: PreparedChannelPost) -> None:
        if not isinstance(post, PreparedChannelPost):
            raise TypeError("post must be a PreparedChannelPost")
        if _PUBLICATION_ID.fullmatch(post.publication_id) is None:
            raise PublicationConflict("publication ID is invalid")
        _, canonical = normalize_channel_ref(post.channel_ref)
        if canonical != post.canonical_channel_ref:
            raise PublicationConflict("prepared channel identity changed")
        if (
            not post.text
            or len(post.text) > MAX_CHANNEL_TEXT
            or _NO_TRADE_DISCLOSURE not in post.text
            or _NO_EXECUTION_DISCLOSURE not in post.text
        ):
            raise PublicationConflict(
                "prepared channel text is missing its bounded no-trade disclosure"
            )
        _validate_campaign_binding(post)
        actual_text_digest = "sha256:" + hashlib.sha256(
            post.text.encode("utf-8")
        ).hexdigest()
        if actual_text_digest != post.text_digest:
            raise PublicationConflict("prepared channel text changed")
        material = (
            f"{canonical}\0{post.card_id}\0{post.card_digest}\0{post.text_digest}".encode(
                "utf-8"
            )
        )
        expected = "kingdom-pub-" + hashlib.sha256(material).hexdigest()[:32]
        if post.publication_id != expected:
            raise PublicationConflict("publication ID does not match the prepared content")

    def _row_receipt(
        self, row: sqlite3.Row, *, duplicate: bool = False
    ) -> PublicationReceipt:
        return PublicationReceipt(
            publication_id=str(row["publication_id"]),
            channel_ref=str(row["channel_ref"]),
            card_id=str(row["card_id"]),
            state=str(row["state"]),
            attempt_count=int(row["attempt_count"]),
            telegram_message_id=(
                int(row["telegram_message_id"])
                if row["telegram_message_id"] is not None
                else None
            ),
            reply_to_publication_id=(
                str(row["reply_to_publication_id"])
                if row["reply_to_publication_id"] is not None
                else None
            ),
            duplicate=duplicate,
        )

    def receipt(self, publication_id: str) -> PublicationReceipt | None:
        row = self.conn.execute(
            "SELECT * FROM channel_publications WHERE publication_id = ?",
            (publication_id,),
        ).fetchone()
        return self._row_receipt(row) if row is not None else None

    def _assert_same(self, row: sqlite3.Row, post: PreparedChannelPost) -> None:
        expected = {
            "channel_ref": post.canonical_channel_ref,
            "card_id": post.card_id,
            "series_id": post.series_id,
            "signal_id": post.signal_id,
            "revision": post.revision,
            "card_digest": post.card_digest,
            "text_digest": post.text_digest,
            "card_status": post.status,
        }
        if any(row[name] != value for name, value in expected.items()):
            raise PublicationConflict("stable publication ID was reused with other content")

    def claim(
        self,
        post: PreparedChannelPost,
        *,
        attempted_at: datetime | str | None = None,
        retry_failed: bool = False,
    ) -> tuple[Literal["claimed", "sent", "pending", "failed", "unknown"], PublicationReceipt | None, int | None]:
        """Atomically reserve one send and locate its predecessor message."""

        self._check_post(post)
        now = _utc_timestamp(attempted_at)
        self._transaction()
        try:
            existing = self.conn.execute(
                "SELECT * FROM channel_publications WHERE publication_id = ?",
                (post.publication_id,),
            ).fetchone()
            if existing is not None:
                self._assert_same(existing, post)
                state = str(existing["state"])
                if state == "failed" and retry_failed:
                    self.conn.execute(
                        """UPDATE channel_publications
                           SET state = 'pending', attempt_count = attempt_count + 1,
                               error_code = NULL, last_attempted_at = ?
                           WHERE publication_id = ?""",
                        (now, post.publication_id),
                    )
                    self.conn.commit()
                    refreshed = self.receipt(post.publication_id)
                    return "claimed", refreshed, self._predecessor_message(post)
                self.conn.commit()
                return state, self._row_receipt(existing), self._predecessor_message(post)

            predecessor_publication_id: str | None = None
            predecessor_message_id: int | None = None
            if post.supersedes_card_id is not None:
                predecessor = self.conn.execute(
                    """SELECT publication_id, state, telegram_message_id
                       FROM channel_publications
                       WHERE channel_ref = ? AND card_id = ?""",
                    (post.canonical_channel_ref, post.supersedes_card_id),
                ).fetchone()
                if (
                    predecessor is None
                    or predecessor["state"] != "sent"
                    or predecessor["telegram_message_id"] is None
                ):
                    raise PublicationStateError(
                        "the superseded card is not a reconciled delivery in this channel"
                    )
                predecessor_publication_id = str(predecessor["publication_id"])
                predecessor_message_id = int(predecessor["telegram_message_id"])

            try:
                self.conn.execute(
                    """INSERT INTO channel_publications (
                         publication_id, channel_ref, card_id, series_id, signal_id,
                         revision, card_digest, text_digest, card_status, state, attempt_count,
                         telegram_message_id, reply_to_publication_id, error_code,
                         prepared_at, last_attempted_at, sent_at, reconciled_at,
                         reconciliation_ref
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 1, NULL, ?, NULL,
                                 ?, ?, NULL, NULL, NULL)""",
                    (
                        post.publication_id,
                        post.canonical_channel_ref,
                        post.card_id,
                        post.series_id,
                        post.signal_id,
                        post.revision,
                        post.card_digest,
                        post.text_digest,
                        post.status,
                        predecessor_publication_id,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise PublicationConflict(
                    "another card already occupies this channel series revision"
                ) from exc
            self.conn.commit()
            return "claimed", self.receipt(post.publication_id), predecessor_message_id
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise

    def _predecessor_message(self, post: PreparedChannelPost) -> int | None:
        if post.supersedes_card_id is None:
            return None
        row = self.conn.execute(
            """SELECT telegram_message_id FROM channel_publications
               WHERE channel_ref = ? AND card_id = ? AND state = 'sent'""",
            (post.canonical_channel_ref, post.supersedes_card_id),
        ).fetchone()
        return int(row["telegram_message_id"]) if row is not None else None

    def finish(
        self,
        publication_id: str,
        *,
        state: Literal["sent", "failed", "unknown"],
        telegram_message_id: int | None = None,
        error_code: str | None = None,
        finished_at: datetime | str | None = None,
    ) -> PublicationReceipt:
        if state not in {"sent", "failed", "unknown"}:
            raise ValueError("publication finish state is invalid")
        if state == "sent":
            if (
                isinstance(telegram_message_id, bool)
                or not isinstance(telegram_message_id, int)
                or telegram_message_id <= 0
            ):
                raise ValueError("a sent publication requires a message ID")
            error_code = None
        elif telegram_message_id is not None:
            raise ValueError("only sent publications may store a message ID")
        if error_code is not None:
            if not isinstance(error_code, str) or not re.fullmatch(
                r"[a-z0-9_.-]{1,64}", error_code
            ):
                raise ValueError("error_code must be a bounded machine label")
        now = _utc_timestamp(finished_at)
        self._transaction()
        try:
            row = self.conn.execute(
                "SELECT state FROM channel_publications WHERE publication_id = ?",
                (publication_id,),
            ).fetchone()
            if row is None:
                raise PublicationStateError("publication was not claimed")
            if row["state"] != "pending":
                raise PublicationStateError("only a pending publication can be finished")
            self.conn.execute(
                """UPDATE channel_publications
                   SET state = ?, telegram_message_id = ?, error_code = ?,
                       sent_at = CASE WHEN ? = 'sent' THEN ? ELSE NULL END
                   WHERE publication_id = ?""",
                (state, telegram_message_id, error_code, state, now, publication_id),
            )
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        receipt = self.receipt(publication_id)
        if receipt is None:
            raise PublicationStateError("publication receipt disappeared")
        self._secure_files()
        return receipt

    def reconcile_unknown(
        self,
        publication_id: str,
        *,
        sent_message_id: int | None,
        reconciliation_ref: str,
        reconciled_at: datetime | str | None = None,
    ) -> PublicationReceipt:
        """Record an operator/provider check before retrying an ambiguous send."""

        if not isinstance(reconciliation_ref, str) or not re.fullmatch(
            r"[a-zA-Z0-9_.:-]{1,128}", reconciliation_ref
        ):
            raise ValueError("reconciliation_ref is invalid")
        if sent_message_id is not None and (
            isinstance(sent_message_id, bool)
            or not isinstance(sent_message_id, int)
            or sent_message_id <= 0
        ):
            raise ValueError("sent_message_id is invalid")
        state = "sent" if sent_message_id is not None else "failed"
        now = _utc_timestamp(reconciled_at)
        self._transaction()
        try:
            row = self.conn.execute(
                "SELECT state FROM channel_publications WHERE publication_id = ?",
                (publication_id,),
            ).fetchone()
            if row is None or row["state"] not in {"pending", "unknown"}:
                raise PublicationStateError(
                    "only a pending or unknown publication can be reconciled"
                )
            self.conn.execute(
                """UPDATE channel_publications
                   SET state = ?, telegram_message_id = ?, error_code = NULL,
                       sent_at = CASE WHEN ? = 'sent' THEN ? ELSE NULL END,
                       reconciled_at = ?, reconciliation_ref = ?
                   WHERE publication_id = ?""",
                (
                    state,
                    sent_message_id,
                    state,
                    now,
                    now,
                    reconciliation_ref,
                    publication_id,
                ),
            )
            self.conn.commit()
        except BaseException:
            if self.conn.in_transaction:
                self.conn.rollback()
            raise
        receipt = self.receipt(publication_id)
        if receipt is None:
            raise PublicationStateError("publication receipt disappeared")
        return receipt


class ChannelPublisher:
    """Publish prepared cards behind an explicit external-delivery gate."""

    def __init__(
        self,
        ledger: ChannelPublicationLedger,
        transport: ChannelPostTransport,
        config: ChannelPublisherConfig | None = None,
    ):
        self.ledger = ledger
        self.transport = transport
        self.config = config or ChannelPublisherConfig()

    def prepare(
        self,
        card: Mapping[str, Any],
        channel_ref: int | str,
        *,
        campaign_link: str | None = None,
    ) -> PreparedChannelPost:
        return prepare_channel_post(
            card,
            channel_ref,
            campaign_link=campaign_link,
        )

    def publish(
        self,
        post: PreparedChannelPost,
        *,
        attempted_at: datetime | str | None = None,
        retry_failed: bool = False,
    ) -> PublicationReceipt:
        if not self.config.external_delivery_enabled:
            raise ExternalDeliveryDisabled(
                "external channel delivery is disabled; preparation remains available"
            )
        state, receipt, predecessor_message_id = self.ledger.claim(
            post, attempted_at=attempted_at, retry_failed=retry_failed
        )
        if state == "sent":
            if receipt is None:
                raise PublicationStateError("sent publication lacks a receipt")
            return PublicationReceipt(**{**receipt.__dict__, "duplicate": True})
        if state == "pending":
            raise PublicationStateError(
                "publication is pending from an earlier attempt; reconcile before retry"
            )
        if state == "unknown":
            raise PublicationStateError(
                "publication delivery is unknown; reconcile before retry"
            )
        if state == "failed":
            raise PublicationStateError(
                "publication previously failed; pass retry_failed=True only after review"
            )

        try:
            result = self.transport.send_channel_post(
                post.channel_ref,
                post.text,
                disable_link_preview=True,
                disable_notification=self.config.disable_notification,
                protect_content=False,
                reply_to_message_id=predecessor_message_id,
            )
        except TelegramError as exc:
            error_code = (
                f"telegram_{exc.error_code}"
                if isinstance(exc.error_code, int) and exc.error_code > 0
                else "telegram_transport"
            )
            self.ledger.finish(
                post.publication_id,
                state="unknown" if exc.ambiguous else "failed",
                error_code=error_code,
                finished_at=attempted_at,
            )
            raise
        except BaseException:
            # A generic transport may have completed its external side effect
            # before raising.  Preserve an unknown receipt and never retry it blindly.
            self.ledger.finish(
                post.publication_id,
                state="unknown",
                error_code="unclassified_transport",
                finished_at=attempted_at,
            )
            raise

        message_id = result.get("message_id") if isinstance(result, Mapping) else None
        if (
            isinstance(message_id, bool)
            or not isinstance(message_id, int)
            or message_id <= 0
        ):
            self.ledger.finish(
                post.publication_id,
                state="unknown",
                error_code="invalid_transport_result",
                finished_at=attempted_at,
            )
            raise PublicationStateError(
                "transport returned no trustworthy message ID; reconciliation is required"
            )
        return self.ledger.finish(
            post.publication_id,
            state="sent",
            telegram_message_id=message_id,
            finished_at=attempted_at,
        )
