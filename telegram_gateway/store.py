"""Private local SQLite store for signals, entitlements, and delivery receipts."""

from __future__ import annotations

import contextlib
import functools
import hashlib
import ipaddress
import json
import math
import os
import re
import secrets
import sqlite3
import stat
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .envelope import content_digest, validate_envelope, verify_envelope
from .promotion import (
    DEFAULT_PROMOTION_NOTICE_VERSION,
    generate_campaign_code,
    validate_campaign_code,
    validate_campaign_kind,
    validate_notice_version,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _bounded_utf8(value: Any, limit: int, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{label} must be valid UTF-8") from exc
    if len(encoded) > limit or "\x00" in value:
        raise ValueError(f"{label} is invalid")
    return value


def _validate_private_identity(telegram_user_id: Any, private_chat_id: Any) -> None:
    if (
        isinstance(telegram_user_id, bool)
        or not isinstance(telegram_user_id, int)
        or telegram_user_id <= 0
        or telegram_user_id > (1 << 52) - 1
        or private_chat_id != telegram_user_id
    ):
        raise ValueError("private Telegram user/chat identity is invalid")


class SignalConflictError(ValueError):
    """A reused signal ID carried different content."""


@dataclass(frozen=True)
class PaymentResult:
    entitlement_expires_at: datetime | None
    initial_charge_id: str
    invoice_payload: str
    refunded: bool
    cancellation_required: bool
    duplicate: bool = False


MAX_TELEGRAM_UPDATE_ID = (1 << 31) - 1
_TELEGRAM_BOT_USERNAME = re.compile(r"[A-Za-z0-9_]{2,29}[Bb][Oo][Tt]\Z")
SIGNAL_PIPELINE_STATUSES = frozenset(
    {"PENDING", "APPROVED", "REJECTED", "REVOKED", "EXPIRED"}
)
SIGNAL_PIPELINE_TRANSITIONS = {
    "PENDING": frozenset({"APPROVED", "REJECTED", "EXPIRED"}),
    "APPROVED": frozenset({"REVOKED", "EXPIRED"}),
    "REJECTED": frozenset(),
    "REVOKED": frozenset(),
    "EXPIRED": frozenset(),
}
STAR_PARTNER_TYPES = frozenset(
    {"user", "chat", "affiliate_program", "fragment", "telegram_ads", "telegram_api"}
)
STAR_USER_TRANSACTION_TYPES = frozenset(
    {
        "invoice_payment",
        "paid_media_payment",
        "gift_purchase",
        "premium_purchase",
        "business_account_transfer",
    }
)
STAR_SUBSCRIPTION_PERIOD_SECONDS = 2_592_000
MAX_ALERT_DELIVERIES_PER_ROLLING_WEEK = 2
TELEGRAM_UPDATE_EPOCH_RESET_AFTER = timedelta(days=6)
CONTACT_SUPPRESSION_REASONS = frozenset({"withdrawn", "blocked", "deleted"})
CONTACT_SUPPRESSION_PRIORITY = {"withdrawn": 1, "blocked": 2, "deleted": 3}


def _atomic_store_method(method: Any) -> Any:
    """Run a store method behind an eager SQLite write reservation.

    ``with connection`` does not begin a transaction for an initial SELECT.
    Reconciliation must lock its local evidence snapshot before reading it, so
    explicitly use ``BEGIN IMMEDIATE`` and refuse ambiguous nested use.
    """

    @functools.wraps(method)
    def wrapped(self: "GatewayStore", *args: Any, **kwargs: Any) -> Any:
        if self.conn.in_transaction:
            raise sqlite3.OperationalError(
                "atomic store method cannot run inside an existing transaction"
            )
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            result = method(self, *args, **kwargs)
            if not self.conn.in_transaction:
                raise sqlite3.OperationalError(
                    "atomic store method ended its transaction early"
                )
            self.conn.commit()
        except BaseException:
            try:
                self.conn.rollback()
            except BaseException:
                # The connection can no longer prove a clean transaction
                # boundary.  Close it rather than risk committing mixed state.
                self.conn.close()
                raise sqlite3.OperationalError("atomic rollback failed") from None
            if self.conn.in_transaction:
                self.conn.close()
                raise sqlite3.OperationalError("atomic rollback did not finish") from None
            raise
        return result

    return wrapped


class GatewayStore:
    """Minimized local state.

    Telegram numeric user/chat identifiers are retained because push delivery
    and subscription reconciliation require them.  Names, usernames, message
    bodies, credentials, and inferred traits are not stored.
    """

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path).expanduser().resolve()
        self.reservation_conflicts = 0
        parent_existed = self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent_existed and stat.S_IMODE(self.path.parent.stat().st_mode) & 0o077:
            raise PermissionError(
                f"gateway database directory must be owner-only (0700): {self.path.parent}"
            )
        if not self.path.exists():
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        else:
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=2000")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA recursive_triggers=ON")
        self.conn.execute("PRAGMA secure_delete=ON")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY,
                envelope_json TEXT NOT NULL,
                content_digest TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                pipeline_status TEXT NOT NULL,
                status_revision INTEGER NOT NULL DEFAULT 0
                    CHECK (status_revision >= 0),
                status_updated_at TEXT,
                lifecycle_event_id TEXT,
                distributable INTEGER NOT NULL CHECK (distributable IN (0, 1)),
                imported_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signal_lifecycle_events (
                event_id TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK (revision > 0),
                previous_status TEXT NOT NULL,
                status TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                actor_kind TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                event_json TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                UNIQUE (signal_id, revision),
                FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
                    ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS signal_lifecycle_quarantine (
                event_id TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signal_correction_delivery_receipts (
                event_id TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'unknown')),
                telegram_message_id INTEGER,
                error_code TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT,
                attempted_at TEXT NOT NULL,
                PRIMARY KEY (event_id, telegram_user_id),
                FOREIGN KEY (event_id) REFERENCES signal_lifecycle_events(event_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS recipients (
                telegram_user_id INTEGER PRIMARY KEY,
                private_chat_id INTEGER NOT NULL,
                tier TEXT NOT NULL CHECK (tier IN ('free', 'research')),
                entitlement_expires_at TEXT,
                terms_version TEXT,
                terms_accepted_at TEXT,
                blocked_at TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                privacy_notice_at TEXT
            );

            CREATE TABLE IF NOT EXISTS promotion_campaigns (
                campaign_code TEXT PRIMARY KEY,
                campaign_kind TEXT NOT NULL CHECK (
                    campaign_kind IN ('direct', 'organic', 'partner',
                                      'telegram_channel', 'test')
                ),
                active INTEGER NOT NULL CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL,
                disabled_at TEXT
            );

            CREATE TABLE IF NOT EXISTS promotion_attributions (
                telegram_user_id INTEGER PRIMARY KEY,
                campaign_code TEXT NOT NULL,
                attribution_update_id INTEGER NOT NULL UNIQUE,
                attributed_on TEXT NOT NULL,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (campaign_code) REFERENCES promotion_campaigns(campaign_code)
                    ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS promotion_campaign_starts (
                campaign_code TEXT NOT NULL,
                observed_on TEXT NOT NULL,
                start_count INTEGER NOT NULL CHECK (start_count > 0),
                PRIMARY KEY (campaign_code, observed_on),
                FOREIGN KEY (campaign_code) REFERENCES promotion_campaigns(campaign_code)
                    ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS research_alert_consents (
                telegram_user_id INTEGER PRIMARY KEY,
                state TEXT NOT NULL CHECK (state IN ('subscribed', 'unsubscribed')),
                revision INTEGER NOT NULL CHECK (revision > 0),
                last_update_id INTEGER NOT NULL UNIQUE,
                notice_version TEXT NOT NULL,
                first_subscribed_at TEXT,
                current_subscribed_at TEXT,
                last_event_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS research_alert_consent_events (
                telegram_update_id INTEGER PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('subscribed', 'unsubscribed')),
                notice_version TEXT NOT NULL,
                event_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS contact_suppressions (
                telegram_user_id INTEGER PRIMARY KEY,
                reason TEXT NOT NULL CHECK (reason IN ('withdrawn', 'blocked', 'deleted')),
                event_at TEXT NOT NULL,
                update_id INTEGER NOT NULL,
                recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS invoice_intents (
                payload TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL,
                currency TEXT NOT NULL,
                total_amount INTEGER NOT NULL,
                terms_version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('created', 'reserved', 'paid', 'expired')),
                pre_checkout_query_id TEXT,
                reserved_at TEXT,
                reconciled_at TEXT,
                reconciliation_ref TEXT,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                initial_charge_id TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL,
                invoice_payload TEXT NOT NULL,
                current_period_end TEXT NOT NULL,
                renewal_state TEXT NOT NULL CHECK (renewal_state IN ('active', 'canceled', 'failed')),
                cancellation_pending_at TEXT,
                cancellation_intent_at TEXT,
                last_provider_update_id INTEGER,
                revoked_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS payments (
                telegram_payment_charge_id TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                initial_charge_id TEXT NOT NULL,
                currency TEXT NOT NULL,
                total_amount INTEGER NOT NULL,
                invoice_payload TEXT NOT NULL,
                paid_at TEXT NOT NULL,
                entitlement_expires_at TEXT NOT NULL,
                is_recurring INTEGER NOT NULL,
                is_first_recurring INTEGER NOT NULL,
                refunded_at TEXT,
                provider_confirmed_at TEXT,
                provider_refund_confirmed_at TEXT,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (initial_charge_id) REFERENCES subscriptions(initial_charge_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS refund_events (
                telegram_payment_charge_id TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                currency TEXT NOT NULL,
                total_amount INTEGER NOT NULL,
                invoice_payload TEXT NOT NULL,
                received_at TEXT NOT NULL,
                resolved_at TEXT,
                resolution_code TEXT,
                reconciliation_ref TEXT,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS pending_subscription_states (
                telegram_user_id INTEGER NOT NULL,
                invoice_payload TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('active', 'canceled', 'failed')),
                update_id INTEGER NOT NULL,
                received_at TEXT NOT NULL,
                PRIMARY KEY (telegram_user_id, invoice_payload),
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS delivery_receipts (
                signal_id TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'unknown')),
                telegram_message_id INTEGER,
                error_code TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT,
                attempted_at TEXT NOT NULL,
                PRIMARY KEY (signal_id, telegram_user_id),
                FOREIGN KEY (signal_id) REFERENCES signals(signal_id) ON DELETE CASCADE,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS paper_actions (
                paper_action_id TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                signal_id TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_probability REAL NOT NULL,
                simulated_amount_usdc REAL NOT NULL,
                created_at TEXT NOT NULL,
                explicit_request_ref TEXT NOT NULL UNIQUE,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE,
                FOREIGN KEY (signal_id) REFERENCES signals(signal_id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processed_updates (
                update_id INTEGER PRIMARY KEY,
                processed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS failed_updates (
                update_id INTEGER PRIMARY KEY,
                error_code TEXT NOT NULL,
                ambiguous INTEGER NOT NULL CHECK (ambiguous IN (0, 1)),
                failed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rate_limits (
                scope TEXT PRIMARY KEY,
                minute_bucket INTEGER NOT NULL,
                request_count INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS support_cases (
                case_id TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('open', 'closed')),
                created_at TEXT NOT NULL,
                closed_at TEXT,
                FOREIGN KEY (telegram_user_id) REFERENCES recipients(telegram_user_id)
                    ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS star_scan_runs (
                run_id TEXT PRIMARY KEY,
                telegram_bot_id INTEGER NOT NULL,
                api_origin TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                state TEXT NOT NULL CHECK (
                    state IN ('running', 'complete', 'failed')
                ),
                pass_count INTEGER NOT NULL DEFAULT 0,
                transaction_count INTEGER NOT NULL DEFAULT 0,
                terminal_offset INTEGER,
                snapshot_digest TEXT,
                issue_count INTEGER NOT NULL DEFAULT 0,
                error_code TEXT
            );

            CREATE TABLE IF NOT EXISTS star_transactions (
                transaction_id TEXT NOT NULL,
                direction TEXT NOT NULL CHECK (direction IN ('incoming', 'outgoing')),
                amount INTEGER NOT NULL,
                nanostar_amount INTEGER NOT NULL,
                transaction_date INTEGER NOT NULL,
                partner_type TEXT NOT NULL,
                transaction_type TEXT,
                telegram_user_id INTEGER,
                invoice_payload TEXT,
                subscription_period INTEGER,
                semantic_digest TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_complete_run_id TEXT,
                PRIMARY KEY (transaction_id, direction),
                FOREIGN KEY (last_complete_run_id) REFERENCES star_scan_runs(run_id)
                    ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS star_reconciliation_issues (
                issue_key TEXT PRIMARY KEY,
                severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical')),
                state TEXT NOT NULL CHECK (state IN ('open', 'resolved')),
                reason_code TEXT NOT NULL,
                transaction_id TEXT,
                direction TEXT CHECK (
                    direction IS NULL OR direction IN ('incoming', 'outgoing')
                ),
                telegram_user_id INTEGER,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                resolved_at TEXT,
                reconciliation_ref TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_promotion_attributions_campaign
                ON promotion_attributions(campaign_code);
            CREATE INDEX IF NOT EXISTS idx_promotion_campaign_starts_campaign
                ON promotion_campaign_starts(campaign_code, observed_on);
            CREATE INDEX IF NOT EXISTS idx_research_alert_consents_state
                ON research_alert_consents(state);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_research_alert_consents_update
                ON research_alert_consents(last_update_id);
            CREATE INDEX IF NOT EXISTS idx_research_alert_consent_events_user
                ON research_alert_consent_events(telegram_user_id, event_at);
            """
        )
        self._migrate_signal_lifecycle_columns()
        self._migrate_signal_distribution_gate()
        self._migrate_checkout_and_subscription_columns()
        self._migrate_star_reconciliation_columns()
        self._migrate_promotion_columns()
        self._ensure_promotion_attribution_invariant()
        self._ensure_single_pending_invoice()
        self._ensure_unique_subscription_invoice()
        self.conn.commit()
        self._secure_sqlite_files()

    def _migrate_signal_lifecycle_columns(self) -> None:
        columns = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(signals)").fetchall()
        }
        for name, declaration in (
            (
                "status_revision",
                "INTEGER NOT NULL DEFAULT 0 CHECK (status_revision >= 0)",
            ),
            ("status_updated_at", "TEXT"),
            ("lifecycle_event_id", "TEXT"),
        ):
            if name not in columns:
                self.conn.execute(
                    f"ALTER TABLE signals ADD COLUMN {name} {declaration}"
                )
        self.conn.execute(
            """UPDATE signals SET status_updated_at = issued_at
               WHERE status_updated_at IS NULL"""
        )

    def _migrate_star_reconciliation_columns(self) -> None:
        """Add provider evidence timestamps to databases from earlier builds."""

        payment_columns = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(payments)").fetchall()
        }
        for name in ("provider_confirmed_at", "provider_refund_confirmed_at"):
            if name not in payment_columns:
                self.conn.execute(f"ALTER TABLE payments ADD COLUMN {name} TEXT")

    def _migrate_promotion_columns(self) -> None:
        """Conservatively migrate databases made during local MVP development."""

        attribution_columns = {
            str(row["name"])
            for row in self.conn.execute(
                "PRAGMA table_info(promotion_attributions)"
            ).fetchall()
        }
        expected_attribution_columns = {
            "telegram_user_id",
            "campaign_code",
            "attribution_update_id",
            "attributed_on",
        }
        if attribution_columns != expected_attribution_columns:
            # The first local prototype retained an unnecessary exact
            # timestamp and named the evidence after /start. Rebuild rather
            # than leaving stale required columns behind.
            source_update = (
                "attribution_update_id"
                if "attribution_update_id" in attribution_columns
                else "start_update_id"
                if "start_update_id" in attribution_columns
                else None
            )
            if source_update is None:
                raise ValueError("promotion attribution evidence requires migration")
            legacy_start_attribution = "attribution_update_id" not in attribution_columns
            self.conn.execute(
                "ALTER TABLE promotion_attributions RENAME TO promotion_attributions_legacy"
            )
            self.conn.execute(
                """CREATE TABLE promotion_attributions (
                     telegram_user_id INTEGER PRIMARY KEY,
                     campaign_code TEXT NOT NULL,
                     attribution_update_id INTEGER NOT NULL UNIQUE,
                     attributed_on TEXT NOT NULL,
                     FOREIGN KEY (telegram_user_id)
                       REFERENCES recipients(telegram_user_id) ON DELETE CASCADE,
                     FOREIGN KEY (campaign_code)
                       REFERENCES promotion_campaigns(campaign_code) ON DELETE RESTRICT
                   )"""
            )
            source_date = (
                "COALESCE(attributed_on, substr(attributed_at, 1, 10))"
                if {"attributed_on", "attributed_at"} <= attribution_columns
                else "attributed_on"
                if "attributed_on" in attribution_columns
                else "substr(attributed_at, 1, 10)"
                if "attributed_at" in attribution_columns
                else "date('now')"
            )
            if legacy_start_attribution:
                # A row captured at /start predates the explicit source-linked
                # opt-in contract. Preserve only its non-linkable daily count;
                # never relabel the old user association as consent evidence.
                self.conn.execute(
                    """INSERT INTO promotion_campaign_starts
                         (campaign_code, observed_on, start_count)
                       SELECT campaign_code, """
                    + source_date
                    + """, COUNT(*)
                       FROM promotion_attributions_legacy
                       GROUP BY campaign_code, """
                    + source_date
                    + """
                       ON CONFLICT(campaign_code, observed_on) DO UPDATE SET
                         start_count = start_count + excluded.start_count"""
                )
            else:
                self.conn.execute(
                    """INSERT INTO promotion_attributions
                         (telegram_user_id, campaign_code, attribution_update_id, attributed_on)
                       SELECT telegram_user_id, campaign_code, """
                    + source_update
                    + ", "
                    + source_date
                    + " FROM promotion_attributions_legacy"
                )
            self.conn.execute("DROP TABLE promotion_attributions_legacy")
            self.conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_promotion_attributions_campaign
                   ON promotion_attributions(campaign_code)"""
            )
        consent_columns = {
            str(row["name"])
            for row in self.conn.execute(
                "PRAGMA table_info(research_alert_consents)"
            ).fetchall()
        }
        additions = (
            (
                "notice_version",
                "TEXT NOT NULL DEFAULT 'legacy-unversioned'",
            ),
            ("current_subscribed_at", "TEXT"),
            ("last_event_at", "TEXT"),
        )
        for name, declaration in additions:
            if name not in consent_columns:
                self.conn.execute(
                    f"ALTER TABLE research_alert_consents ADD COLUMN {name} {declaration}"
                )
        self.conn.execute(
            """UPDATE research_alert_consents
               SET last_event_at = updated_at
               WHERE last_event_at IS NULL"""
        )
        self.conn.execute(
            """UPDATE research_alert_consents
               SET current_subscribed_at = updated_at
               WHERE state = 'subscribed' AND current_subscribed_at IS NULL"""
        )

    def _ensure_promotion_attribution_invariant(self) -> None:
        """Keep linkable campaign attribution behind matching opt-in evidence.

        Earlier local MVP builds could commit attribution before consent. Drop
        those orphan rows on open, then enforce the relationship for direct SQL
        writes as well as the supported store API. Consent events are immutable
        in normal operation; defensive cleanup triggers preserve the invariant
        if an operator deletes or rewrites one manually.
        """

        trigger_names = (
            "promotion_attribution_requires_consent",
            "promotion_attribution_insert_is_first_write",
            "promotion_attribution_update_requires_consent",
            "promotion_attribution_campaign_is_immutable",
            "promotion_attribution_update_is_forbidden",
            "promotion_consent_event_delete_clears_attribution",
            "promotion_consent_event_update_clears_attribution",
            "promotion_consent_event_update_reconciles_attribution",
            "promotion_consent_event_insert_reconciles_attribution",
        )
        for trigger_name in trigger_names:
            self.conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
        self.conn.execute(
            """DELETE FROM promotion_attributions
               WHERE NOT EXISTS (
                 SELECT 1 FROM research_alert_consent_events AS consent_event
                 WHERE consent_event.telegram_user_id =
                         promotion_attributions.telegram_user_id
                   AND consent_event.telegram_update_id =
                         promotion_attributions.attribution_update_id
                   AND consent_event.state = 'subscribed'
               )"""
        )
        self.conn.execute(
            """CREATE TRIGGER promotion_attribution_requires_consent
               BEFORE INSERT ON promotion_attributions
               WHEN NOT EXISTS (
                 SELECT 1
                 FROM research_alert_consent_events AS consent_event
                 JOIN research_alert_consents AS consent
                   ON consent.telegram_user_id = consent_event.telegram_user_id
                 WHERE consent_event.telegram_user_id = NEW.telegram_user_id
                   AND consent_event.telegram_update_id = NEW.attribution_update_id
                   AND consent_event.state = 'subscribed'
                   AND consent.state = 'subscribed'
                   AND consent.last_update_id = consent_event.telegram_update_id
                   AND consent.notice_version = consent_event.notice_version
                   AND NOT EXISTS (
                     SELECT 1 FROM contact_suppressions AS suppression
                     WHERE suppression.telegram_user_id =
                             consent_event.telegram_user_id
                   )
                   AND 1 = (
                     SELECT COUNT(*)
                     FROM research_alert_consent_events AS history
                     WHERE history.telegram_user_id =
                             consent_event.telegram_user_id
                   )
               )
               BEGIN
                 SELECT RAISE(
                   ABORT,
                   'campaign attribution requires matching subscribed consent'
                 );
               END"""
        )
        self.conn.execute(
            """CREATE TRIGGER promotion_attribution_insert_is_first_write
               BEFORE INSERT ON promotion_attributions
               WHEN EXISTS (
                 SELECT 1 FROM promotion_attributions AS attribution
                 WHERE attribution.telegram_user_id = NEW.telegram_user_id
                    OR attribution.attribution_update_id =
                         NEW.attribution_update_id
               )
               BEGIN
                 SELECT RAISE(ABORT, 'campaign attribution is immutable');
               END"""
        )
        self.conn.execute(
            """CREATE TRIGGER promotion_attribution_update_is_forbidden
               BEFORE UPDATE ON promotion_attributions
               BEGIN
                 SELECT RAISE(ABORT, 'campaign attribution is immutable');
               END"""
        )
        self.conn.execute(
            """CREATE TRIGGER promotion_consent_event_delete_clears_attribution
               AFTER DELETE ON research_alert_consent_events
               WHEN OLD.state = 'subscribed'
               BEGIN
                 DELETE FROM promotion_attributions
                 WHERE telegram_user_id = OLD.telegram_user_id
                   AND attribution_update_id = OLD.telegram_update_id;
               END"""
        )
        self.conn.execute(
            """CREATE TRIGGER promotion_consent_event_update_clears_attribution
               AFTER UPDATE ON research_alert_consent_events
               WHEN OLD.state = 'subscribed'
                 AND (
                   NEW.state != 'subscribed'
                   OR NEW.telegram_user_id != OLD.telegram_user_id
                   OR NEW.telegram_update_id != OLD.telegram_update_id
                 )
               BEGIN
                 DELETE FROM promotion_attributions
                 WHERE telegram_user_id = OLD.telegram_user_id
                   AND attribution_update_id = OLD.telegram_update_id;
               END"""
        )
        self.conn.execute(
            """CREATE TRIGGER promotion_consent_event_update_reconciles_attribution
               AFTER UPDATE ON research_alert_consent_events
               BEGIN
                 DELETE FROM promotion_attributions
                 WHERE attribution_update_id = NEW.telegram_update_id
                   AND (
                     telegram_user_id != NEW.telegram_user_id
                     OR NEW.state != 'subscribed'
                   );
               END"""
        )
        self.conn.execute(
            """CREATE TRIGGER promotion_consent_event_insert_reconciles_attribution
               AFTER INSERT ON research_alert_consent_events
               WHEN NEW.state != 'subscribed'
                 OR EXISTS (
                   SELECT 1 FROM promotion_attributions AS attribution
                   WHERE attribution.attribution_update_id = NEW.telegram_update_id
                     AND attribution.telegram_user_id != NEW.telegram_user_id
                 )
               BEGIN
                 DELETE FROM promotion_attributions
                 WHERE attribution_update_id = NEW.telegram_update_id
                   AND (
                     telegram_user_id != NEW.telegram_user_id
                     OR NEW.state != 'subscribed'
                   );
               END"""
        )

    def _migrate_signal_distribution_gate(self) -> None:
        """Add and derive the risk gate for databases made by early MVP builds."""

        columns = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(signals)").fetchall()
        }
        if "distributable" not in columns:
            self.conn.execute(
                "ALTER TABLE signals ADD COLUMN distributable INTEGER NOT NULL DEFAULT 0 "
                "CHECK (distributable IN (0, 1))"
            )
        rows = self.conn.execute(
            """SELECT s.signal_id, s.envelope_json, s.content_digest,
                      s.pipeline_status, s.status_revision, s.lifecycle_event_id,
                      EXISTS (
                        SELECT 1 FROM signal_lifecycle_events e
                        WHERE e.event_id = s.lifecycle_event_id
                          AND e.signal_id = s.signal_id
                          AND e.revision = s.status_revision
                          AND e.status = 'APPROVED'
                      ) AS has_approval_evidence
               FROM signals s"""
        ).fetchall()
        for row in rows:
            try:
                envelope = json.loads(row["envelope_json"])
                distributable = int(
                    verify_envelope(envelope)
                    and content_digest(envelope) == row["content_digest"]
                    and row["pipeline_status"] == "APPROVED"
                    and int(row["status_revision"]) > 0
                    and bool(row["lifecycle_event_id"])
                    and bool(row["has_approval_evidence"])
                    and self._passes_static_risk(envelope)
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                distributable = 0
            self.conn.execute(
                "UPDATE signals SET distributable = ? WHERE signal_id = ?",
                (distributable, row["signal_id"]),
            )

    @staticmethod
    def _passes_static_risk(envelope: Mapping[str, Any]) -> bool:
        risk = envelope.get("risk")
        return bool(
            isinstance(risk, Mapping)
            and risk.get("concentration_passed") is True
            and risk.get("anti_patterns_passed") is True
        )

    def _ensure_single_pending_invoice(self) -> None:
        """Repair early MVP duplicates, then enforce one pending checkout per plan."""

        timestamp = iso_utc(utc_now())
        self.conn.execute(
            """UPDATE invoice_intents SET state = 'expired'
               WHERE state = 'created' AND julianday(expires_at) <= julianday(?)""",
            (timestamp,),
        )
        rows = self.conn.execute(
            """SELECT payload, telegram_user_id, plan_code, state FROM invoice_intents
               WHERE state IN ('created', 'reserved')
               ORDER BY telegram_user_id, plan_code,
                        CASE state WHEN 'reserved' THEN 0 ELSE 1 END,
                        created_at DESC"""
        ).fetchall()
        seen: set[tuple[int, str]] = set()
        ambiguous_reservations = 0
        for row in rows:
            key = (int(row["telegram_user_id"]), str(row["plan_code"]))
            if key in seen:
                if row["state"] == "reserved":
                    ambiguous_reservations += 1
                else:
                    self.conn.execute(
                        "UPDATE invoice_intents SET state = 'expired' WHERE payload = ?",
                        (row["payload"],),
                    )
            else:
                seen.add(key)
        self.reservation_conflicts = ambiguous_reservations
        if not ambiguous_reservations:
            self.conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS one_pending_invoice_per_plan
                   ON invoice_intents(telegram_user_id, plan_code)
                   WHERE state IN ('created', 'reserved')"""
            )

    def _migrate_checkout_and_subscription_columns(self) -> None:
        invoice_columns = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(invoice_intents)").fetchall()
        }
        if "reserved_at" not in invoice_columns:
            self.conn.execute("ALTER TABLE invoice_intents ADD COLUMN reserved_at TEXT")
            self.conn.execute(
                """UPDATE invoice_intents SET reserved_at = created_at
                   WHERE state = 'reserved' AND reserved_at IS NULL"""
            )
        for name in ("reconciled_at", "reconciliation_ref"):
            if name not in invoice_columns:
                self.conn.execute(
                    f"ALTER TABLE invoice_intents ADD COLUMN {name} TEXT"
                )

        subscription_columns = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(subscriptions)").fetchall()
        }
        for name, declaration in (
            ("cancellation_pending_at", "TEXT"),
            ("cancellation_intent_at", "TEXT"),
            ("last_provider_update_id", "INTEGER"),
        ):
            if name not in subscription_columns:
                self.conn.execute(
                    f"ALTER TABLE subscriptions ADD COLUMN {name} {declaration}"
                )

        refund_columns = {
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info(refund_events)").fetchall()
        }
        for name in ("resolution_code", "reconciliation_ref"):
            if name not in refund_columns:
                self.conn.execute(
                    f"ALTER TABLE refund_events ADD COLUMN {name} TEXT"
                )

    def _ensure_unique_subscription_invoice(self) -> None:
        duplicate = self.conn.execute(
            """SELECT invoice_payload FROM subscriptions
               GROUP BY invoice_payload HAVING COUNT(*) > 1 LIMIT 1"""
        ).fetchone()
        if duplicate:
            raise ValueError(
                "duplicate subscription invoice payloads require payment reconciliation"
            )
        self.conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS one_subscription_per_invoice
               ON subscriptions(invoice_payload)"""
        )

    def _secure_sqlite_files(self) -> None:
        for path in (self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")):
            if path.exists():
                try:
                    path.chmod(0o600)
                except OSError:
                    pass

    def _decode_signal_row(self, row: sqlite3.Row) -> dict[str, Any] | None:
        try:
            envelope = json.loads(row["envelope_json"])
            approval = self.conn.execute(
                """SELECT 1 FROM signal_lifecycle_events
                   WHERE event_id = ? AND signal_id = ? AND revision = ?
                     AND status = 'APPROVED'""",
                (
                    row["lifecycle_event_id"],
                    row["signal_id"],
                    row["status_revision"],
                ),
            ).fetchone()
            valid = (
                isinstance(envelope, Mapping)
                and verify_envelope(envelope)
                and content_digest(envelope) == row["content_digest"]
                and row["pipeline_status"] == "APPROVED"
                and int(row["status_revision"]) > 0
                and approval is not None
                and self._passes_static_risk(envelope)
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            valid = False
            envelope = None
        if valid:
            return dict(envelope)
        self.conn.execute(
            "UPDATE signals SET distributable = 0 WHERE signal_id = ?",
            (row["signal_id"],),
        )
        self.conn.commit()
        return None

    def put_signal(self, envelope: Mapping[str, Any], *, now: datetime | None = None) -> bool:
        validate_envelope(envelope)
        digest = content_digest(envelope)
        signal_id = str(envelope["signal_id"])
        existing = self.conn.execute(
            "SELECT content_digest FROM signals WHERE signal_id = ?", (signal_id,)
        ).fetchone()
        if existing:
            if existing["content_digest"] != digest:
                raise SignalConflictError(
                    f"signal ID {signal_id!r} was reused with different content"
                )
            return False
        timestamp = iso_utc(now or utc_now())
        pipeline_status = str(envelope["risk"]["pipeline_status"]).upper()
        if pipeline_status not in SIGNAL_PIPELINE_STATUSES:
            raise ValueError("signal pipeline status is invalid")
        if pipeline_status not in {"PENDING", "REJECTED"}:
            raise ValueError(
                "base signal status must be PENDING or REJECTED; approval requires "
                "a revisioned lifecycle event"
            )
        self.conn.execute(
            """INSERT INTO signals
               (signal_id, envelope_json, content_digest, issued_at, expires_at,
                pipeline_status, status_revision, status_updated_at,
                lifecycle_event_id, distributable, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, NULL, ?, ?)""",
            (
                signal_id,
                json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                digest,
                envelope["issued_at"],
                envelope["expires_at"],
                pipeline_status,
                envelope["issued_at"],
                0,
                timestamp,
            ),
        )
        self.conn.commit()
        self._retry_signal_lifecycle_quarantine(signal_id)
        return True

    def _retry_signal_lifecycle_quarantine(self, signal_id: str) -> int:
        """Apply any now-contiguous orphan/gap events retained for a signal."""

        applied = 0
        while True:
            current = self.conn.execute(
                "SELECT status_revision FROM signals WHERE signal_id = ?",
                (signal_id,),
            ).fetchone()
            if not current:
                return applied
            row = self.conn.execute(
                """SELECT event_json FROM signal_lifecycle_quarantine
                   WHERE signal_id = ? AND revision = ?
                   ORDER BY first_seen_at, event_id LIMIT 1""",
                (signal_id, int(current["status_revision"]) + 1),
            ).fetchone()
            if not row:
                return applied
            try:
                event = json.loads(str(row["event_json"]))
            except (json.JSONDecodeError, TypeError, ValueError):
                return applied
            outcome = self.apply_signal_lifecycle(event, _drain_quarantine=False)
            if outcome != "applied":
                return applied
            applied += 1

    @staticmethod
    def _validated_signal_lifecycle_event(
        value: Mapping[str, Any],
    ) -> tuple[dict[str, Any], str]:
        expected = {
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
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("signal lifecycle event shape is invalid")
        event = dict(value)
        if event["schema"] != "s012.signal-lifecycle/0.1":
            raise ValueError("signal lifecycle schema is invalid")
        event_id = _bounded_utf8(event["event_id"], 128, "lifecycle event ID")
        signal_id = _bounded_utf8(event["signal_id"], 128, "lifecycle signal ID")
        if not re.fullmatch(r"s012-life-[0-9a-f]{32}", event_id):
            raise ValueError("lifecycle event ID is invalid")
        revision = event["revision"]
        if (
            isinstance(revision, bool)
            or not isinstance(revision, int)
            or not 1 <= revision <= 1_000_000
        ):
            raise ValueError("signal lifecycle revision is invalid")
        previous = event["previous_status"]
        status = event["status"]
        if previous not in SIGNAL_PIPELINE_STATUSES or status not in SIGNAL_PIPELINE_STATUSES:
            raise ValueError("signal lifecycle status is invalid")
        if status == "PENDING":
            raise ValueError("signal lifecycle cannot transition back to pending")
        occurred = _bounded_utf8(event["occurred_at"], 64, "lifecycle timestamp")
        parse_utc(occurred)
        for name in ("actor_kind", "reason_code"):
            item = event[name]
            if not isinstance(item, str) or not re.fullmatch(
                r"[a-z0-9_.-]{1,64}", item
            ):
                raise ValueError(f"signal lifecycle {name} is invalid")
        if event["scope"] != "research_distribution_only":
            raise ValueError("signal lifecycle scope is invalid")
        if event["execution_allowed"] is not False:
            raise ValueError("signal lifecycle cannot grant execution authority")
        material = dict(event)
        material.pop("event_id")
        expected_id = "s012-life-" + hashlib.sha256(
            json.dumps(
                material,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()[:32]
        if not secrets.compare_digest(event_id, expected_id):
            raise ValueError("signal lifecycle event ID does not match content")
        event_json = json.dumps(
            event,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        event["event_id"] = event_id
        event["signal_id"] = signal_id
        return event, event_json

    def _quarantine_signal_lifecycle(
        self,
        event: Mapping[str, Any],
        event_json: str,
        reason_code: str,
        timestamp: str,
    ) -> str:
        self.conn.execute(
            """INSERT INTO signal_lifecycle_quarantine
               (event_id, signal_id, revision, event_json, reason_code,
                first_seen_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(event_id) DO UPDATE SET
                 reason_code = excluded.reason_code,
                 last_seen_at = excluded.last_seen_at""",
            (
                event["event_id"],
                event["signal_id"],
                event["revision"],
                event_json,
                reason_code,
                timestamp,
                timestamp,
            ),
        )
        return "orphan" if reason_code == "signal_not_imported" else "quarantined"

    def apply_signal_lifecycle(
        self,
        event: Mapping[str, Any],
        *,
        now: datetime | None = None,
        _drain_quarantine: bool = True,
    ) -> str:
        """Apply one revisioned distribution state without mutating its envelope."""

        normalized, event_json = self._validated_signal_lifecycle_event(event)
        timestamp = iso_utc(now or utc_now())
        with self.conn:
            applied = self.conn.execute(
                """SELECT event_json FROM signal_lifecycle_events
                   WHERE event_id = ?""",
                (normalized["event_id"],),
            ).fetchone()
            if applied:
                if not secrets.compare_digest(str(applied["event_json"]), event_json):
                    return self._quarantine_signal_lifecycle(
                        normalized,
                        event_json,
                        "event_id_content_conflict",
                        timestamp,
                    )
                return "duplicate"

            signal = self.conn.execute(
                """SELECT envelope_json, content_digest, issued_at, expires_at,
                          pipeline_status, status_revision
                   FROM signals WHERE signal_id = ?""",
                (normalized["signal_id"],),
            ).fetchone()
            if not signal:
                return self._quarantine_signal_lifecycle(
                    normalized, event_json, "signal_not_imported", timestamp
                )

            reason: str | None = None
            current_status = str(signal["pipeline_status"])
            current_revision = int(signal["status_revision"])
            if normalized["revision"] != current_revision + 1:
                reason = "revision_gap_or_reuse"
            elif normalized["previous_status"] != current_status:
                reason = "previous_status_mismatch"
            elif normalized["status"] not in SIGNAL_PIPELINE_TRANSITIONS.get(
                current_status, frozenset()
            ):
                reason = "invalid_status_transition"
            else:
                occurred = parse_utc(str(normalized["occurred_at"]))
                if occurred < parse_utc(str(signal["issued_at"])):
                    reason = "event_predates_signal"
                elif (
                    normalized["status"] == "APPROVED"
                    and occurred >= parse_utc(str(signal["expires_at"]))
                ):
                    reason = "approval_after_expiry"
            if reason:
                return self._quarantine_signal_lifecycle(
                    normalized, event_json, reason, timestamp
                )

            try:
                envelope = json.loads(str(signal["envelope_json"]))
                static_risk_passed = bool(
                    isinstance(envelope, Mapping)
                    and verify_envelope(envelope)
                    and content_digest(envelope) == signal["content_digest"]
                    and self._passes_static_risk(envelope)
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                static_risk_passed = False
            distributable = int(
                normalized["status"] == "APPROVED" and static_risk_passed
            )
            try:
                self.conn.execute(
                    """INSERT INTO signal_lifecycle_events
                       (event_id, signal_id, revision, previous_status, status,
                        occurred_at, actor_kind, reason_code, event_json, applied_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        normalized["event_id"],
                        normalized["signal_id"],
                        normalized["revision"],
                        normalized["previous_status"],
                        normalized["status"],
                        normalized["occurred_at"],
                        normalized["actor_kind"],
                        normalized["reason_code"],
                        event_json,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError:
                return self._quarantine_signal_lifecycle(
                    normalized, event_json, "revision_conflict", timestamp
                )
            cursor = self.conn.execute(
                """UPDATE signals
                   SET pipeline_status = ?, status_revision = ?,
                       status_updated_at = ?, lifecycle_event_id = ?,
                       distributable = ?
                   WHERE signal_id = ? AND status_revision = ?
                     AND pipeline_status = ?""",
                (
                    normalized["status"],
                    normalized["revision"],
                    normalized["occurred_at"],
                    normalized["event_id"],
                    distributable,
                    normalized["signal_id"],
                    current_revision,
                    current_status,
                ),
            )
            if cursor.rowcount != 1:
                raise sqlite3.OperationalError(
                    "signal lifecycle compare-and-swap lost its transaction"
                )
            self.conn.execute(
                "DELETE FROM signal_lifecycle_quarantine WHERE event_id = ?",
                (normalized["event_id"],),
            )
        if _drain_quarantine:
            self._retry_signal_lifecycle_quarantine(str(normalized["signal_id"]))
        return "applied"

    def signal_lifecycle_status(self) -> dict[str, Any]:
        state_counts = {
            str(row["pipeline_status"]): int(row["count"])
            for row in self.conn.execute(
                """SELECT pipeline_status, COUNT(*) AS count FROM signals
                   GROUP BY pipeline_status"""
            ).fetchall()
        }
        return {
            "states": state_counts,
            "events": int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM signal_lifecycle_events"
                ).fetchone()[0]
            ),
            "quarantined": int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM signal_lifecycle_quarantine"
                ).fetchone()[0]
            ),
        }

    def latest_signal(self, *, now: datetime | None = None) -> dict[str, Any] | None:
        timestamp = iso_utc(now or utc_now())
        rows = self.conn.execute(
            """SELECT signal_id, envelope_json, content_digest, pipeline_status,
                      status_revision, lifecycle_event_id
               FROM signals
               WHERE distributable = 1 AND julianday(expires_at) > julianday(?)
               ORDER BY julianday(issued_at) DESC LIMIT 100""",
            (timestamp,),
        ).fetchall()
        for row in rows:
            envelope = self._decode_signal_row(row)
            if envelope is not None:
                return envelope
        return None

    def resolve_signal_prefix(
        self, prefix: str, *, now: datetime | None = None
    ) -> dict[str, Any] | None:
        clean = prefix.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}", clean):
            return None
        timestamp = iso_utc(now or utc_now())
        rows = self.conn.execute(
            """SELECT signal_id, envelope_json, content_digest, pipeline_status,
                      status_revision, lifecycle_event_id
               FROM signals
               WHERE substr(signal_id, 1, length(?)) = ?
                 AND distributable = 1
                 AND julianday(expires_at) > julianday(?)
               ORDER BY julianday(issued_at) DESC LIMIT 2""",
            (clean, clean, timestamp),
        ).fetchall()
        valid = [value for row in rows if (value := self._decode_signal_row(row))]
        if len(valid) != 1:
            return None
        return valid[0]

    def register_recipient(
        self,
        telegram_user_id: int,
        private_chat_id: int,
        *,
        now: datetime | None = None,
    ) -> None:
        _validate_private_identity(telegram_user_id, private_chat_id)
        timestamp = iso_utc(now or utc_now())
        self.conn.execute(
            """INSERT INTO recipients
               (telegram_user_id, private_chat_id, tier, entitlement_expires_at,
                terms_version, terms_accepted_at, blocked_at,
                first_seen_at, last_seen_at, privacy_notice_at)
               VALUES (?, ?, 'free', NULL, NULL, NULL, NULL, ?, ?, NULL)
               ON CONFLICT(telegram_user_id) DO UPDATE SET
                 private_chat_id = excluded.private_chat_id,
                 blocked_at = NULL,
                 last_seen_at = excluded.last_seen_at""",
            (telegram_user_id, private_chat_id, timestamp, timestamp),
        )
        self.conn.commit()

    @_atomic_store_method
    def create_promotion_campaign(
        self,
        campaign_code: str,
        *,
        campaign_kind: str,
        now: datetime | None = None,
    ) -> bool:
        """Register one bounded public deep-link label; never a person label."""

        code = validate_campaign_code(campaign_code)
        kind = validate_campaign_kind(campaign_kind)
        existing = self.conn.execute(
            """SELECT campaign_kind, active FROM promotion_campaigns
               WHERE campaign_code = ?""",
            (code,),
        ).fetchone()
        if existing:
            if existing["campaign_kind"] != kind:
                raise ValueError("campaign code is already bound to another kind")
            if not bool(existing["active"]):
                raise ValueError("disabled campaign codes cannot be silently reactivated")
            return False
        self.conn.execute(
            """INSERT INTO promotion_campaigns
               (campaign_code, campaign_kind, active, created_at, disabled_at)
               VALUES (?, ?, 1, ?, NULL)""",
            (code, kind, iso_utc(now or utc_now())),
        )
        return True

    @_atomic_store_method
    def get_or_create_bootstrap_campaign(
        self, *, now: datetime | None = None
    ) -> tuple[str, bool]:
        """Return one durable launch campaign without minting codes on reruns."""

        state_key = "telegram_bootstrap_campaign_code"
        state = self.conn.execute(
            "SELECT value FROM bot_state WHERE key = ?", (state_key,)
        ).fetchone()
        if state:
            code = validate_campaign_code(str(state["value"]))
            campaign = self.conn.execute(
                """SELECT campaign_kind, active FROM promotion_campaigns
                   WHERE campaign_code = ?""",
                (code,),
            ).fetchone()
            if not campaign or campaign["campaign_kind"] != "telegram_channel":
                raise ValueError("bootstrap campaign binding is incomplete")
            if not bool(campaign["active"]):
                raise ValueError(
                    "the bootstrap campaign is disabled and cannot be silently replaced"
                )
            return code, False

        code = generate_campaign_code()
        self.conn.execute(
            """INSERT INTO promotion_campaigns
               (campaign_code, campaign_kind, active, created_at, disabled_at)
               VALUES (?, 'telegram_channel', 1, ?, NULL)""",
            (code, iso_utc(now or utc_now())),
        )
        self.conn.execute(
            "INSERT INTO bot_state(key, value) VALUES (?, ?)", (state_key, code)
        )
        return code, True

    @_atomic_store_method
    def disable_promotion_campaign(
        self, campaign_code: str, *, now: datetime | None = None
    ) -> bool:
        code = validate_campaign_code(campaign_code)
        cursor = self.conn.execute(
            """UPDATE promotion_campaigns
               SET active = 0, disabled_at = ?
               WHERE campaign_code = ? AND active = 1""",
            (iso_utc(now or utc_now()), code),
        )
        return cursor.rowcount == 1

    def is_active_promotion_campaign(self, campaign_code: str) -> bool:
        code = validate_campaign_code(campaign_code)
        return (
            self.conn.execute(
                """SELECT 1 FROM promotion_campaigns
                   WHERE campaign_code = ? AND active = 1""",
                (code,),
            ).fetchone()
            is not None
        )

    @_atomic_store_method
    def record_promotion_campaign_start(
        self,
        campaign_code: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Increment a daily campaign counter without retaining a user link."""

        code = validate_campaign_code(campaign_code)
        if not self.conn.execute(
            """SELECT 1 FROM promotion_campaigns
               WHERE campaign_code = ? AND active = 1""",
            (code,),
        ).fetchone():
            return False
        current = now or utc_now()
        iso_utc(current)
        observed_on = current.astimezone(timezone.utc).date().isoformat()
        self.conn.execute(
            """INSERT INTO promotion_campaign_starts
                 (campaign_code, observed_on, start_count)
               VALUES (?, ?, 1)
               ON CONFLICT(campaign_code, observed_on) DO UPDATE SET
                 start_count = start_count + 1""",
            (code, observed_on),
        )
        return True

    def _record_promotion_attribution(
        self,
        telegram_user_id: int,
        campaign_code: str,
        telegram_update_id: int,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Attribute an explicit source-linked opt-in to an active campaign."""

        _validate_private_identity(telegram_user_id, telegram_user_id)
        code = validate_campaign_code(campaign_code)
        if (
            isinstance(telegram_update_id, bool)
            or not isinstance(telegram_update_id, int)
            or not 0 <= telegram_update_id <= MAX_TELEGRAM_UPDATE_ID
        ):
            raise ValueError("Telegram update ID is invalid")
        active = self.conn.execute(
            """SELECT 1 FROM promotion_campaigns
               WHERE campaign_code = ? AND active = 1""",
            (code,),
        ).fetchone()
        if not active:
            return False
        existing = self.conn.execute(
            """SELECT campaign_code, attribution_update_id FROM promotion_attributions
               WHERE telegram_user_id = ?""",
            (telegram_user_id,),
        ).fetchone()
        if existing:
            return False
        matching_first_consent = self.conn.execute(
            """SELECT 1
               FROM research_alert_consent_events AS consent_event
               JOIN research_alert_consents AS consent
                 ON consent.telegram_user_id = consent_event.telegram_user_id
               WHERE consent_event.telegram_update_id = ?
                 AND consent_event.telegram_user_id = ?
                 AND consent_event.state = 'subscribed'
                 AND consent.state = 'subscribed'
                 AND consent.last_update_id = consent_event.telegram_update_id
                 AND consent.notice_version = consent_event.notice_version
                 AND NOT EXISTS (
                   SELECT 1 FROM contact_suppressions AS suppression
                   WHERE suppression.telegram_user_id =
                           consent_event.telegram_user_id
                 )
                 AND 1 = (
                   SELECT COUNT(*) FROM research_alert_consent_events AS history
                   WHERE history.telegram_user_id = consent_event.telegram_user_id
                 )""",
            (telegram_update_id, telegram_user_id),
        ).fetchone()
        if not matching_first_consent:
            return False
        current = now or utc_now()
        iso_utc(current)
        try:
            cursor = self.conn.execute(
                """INSERT INTO promotion_attributions
                   (telegram_user_id, campaign_code, attribution_update_id, attributed_on)
                   VALUES (?, ?, ?, ?)""",
                (
                    telegram_user_id,
                    code,
                    telegram_update_id,
                    current.astimezone(timezone.utc).date().isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("campaign attribution conflicts with stored evidence") from exc
        return cursor.rowcount == 1

    def _upsert_contact_suppression(
        self,
        telegram_user_id: int,
        *,
        telegram_update_id: int,
        reason: str,
        event_at: datetime,
        recorded_at: datetime,
    ) -> bool:
        """Persist a minimal no-contact watermark inside the active transaction."""

        event_timestamp = iso_utc(event_at)
        recorded_timestamp = iso_utc(recorded_at)
        existing = self.conn.execute(
            """SELECT reason, event_at, update_id FROM contact_suppressions
               WHERE telegram_user_id = ?""",
            (telegram_user_id,),
        ).fetchone()
        if not existing:
            self.conn.execute(
                """INSERT INTO contact_suppressions
                   (telegram_user_id, reason, event_at, update_id, recorded_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    telegram_user_id,
                    reason,
                    event_timestamp,
                    telegram_update_id,
                    recorded_timestamp,
                ),
            )
            return True

        stored_order = (
            parse_utc(str(existing["event_at"])),
            int(existing["update_id"]),
        )
        incoming_order = (event_at.astimezone(timezone.utc), telegram_update_id)
        stored_reason = str(existing["reason"])
        chosen_reason = (
            reason
            if CONTACT_SUPPRESSION_PRIORITY[reason]
            > CONTACT_SUPPRESSION_PRIORITY[stored_reason]
            else stored_reason
        )
        if incoming_order > stored_order:
            chosen_event_at = event_timestamp
            chosen_update_id = telegram_update_id
        else:
            chosen_event_at = str(existing["event_at"])
            chosen_update_id = int(existing["update_id"])
        changed = (
            chosen_reason != stored_reason
            or chosen_event_at != str(existing["event_at"])
            or chosen_update_id != int(existing["update_id"])
        )
        if changed:
            self.conn.execute(
                """UPDATE contact_suppressions
                   SET reason = ?, event_at = ?, update_id = ?, recorded_at = ?
                   WHERE telegram_user_id = ?""",
                (
                    chosen_reason,
                    chosen_event_at,
                    chosen_update_id,
                    recorded_timestamp,
                    telegram_user_id,
                ),
            )
        return changed

    @_atomic_store_method
    def record_contact_suppression(
        self,
        telegram_user_id: int,
        *,
        telegram_update_id: int,
        reason: str,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Remember only enough ordering evidence to honor stop/delete requests."""

        _validate_private_identity(telegram_user_id, telegram_user_id)
        if reason not in CONTACT_SUPPRESSION_REASONS:
            raise ValueError("contact suppression reason is invalid")
        if (
            isinstance(telegram_update_id, bool)
            or not isinstance(telegram_update_id, int)
            or not 0 <= telegram_update_id <= MAX_TELEGRAM_UPDATE_ID
        ):
            raise ValueError("Telegram update ID is invalid")
        recorded = now or utc_now()
        occurred = event_at or recorded
        return self._upsert_contact_suppression(
            telegram_user_id,
            telegram_update_id=telegram_update_id,
            reason=reason,
            event_at=occurred,
            recorded_at=recorded,
        )

    def contact_action_is_newer(
        self,
        telegram_user_id: int,
        telegram_update_id: int,
        *,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Return whether a contact action is later than the no-contact marker."""

        _validate_private_identity(telegram_user_id, telegram_user_id)
        if (
            isinstance(telegram_update_id, bool)
            or not isinstance(telegram_update_id, int)
            or not 0 <= telegram_update_id <= MAX_TELEGRAM_UPDATE_ID
        ):
            raise ValueError("Telegram update ID is invalid")
        row = self.conn.execute(
            """SELECT event_at, update_id FROM contact_suppressions
               WHERE telegram_user_id = ?""",
            (telegram_user_id,),
        ).fetchone()
        if not row:
            return True
        occurred = event_at or now or utc_now()
        iso_utc(occurred)
        return (
            occurred.astimezone(timezone.utc),
            telegram_update_id,
        ) > (parse_utc(str(row["event_at"])), int(row["update_id"]))

    def contact_suppression_status(
        self, telegram_user_id: int
    ) -> dict[str, Any] | None:
        _validate_private_identity(telegram_user_id, telegram_user_id)
        row = self.conn.execute(
            """SELECT reason, event_at, update_id, recorded_at
               FROM contact_suppressions WHERE telegram_user_id = ?""",
            (telegram_user_id,),
        ).fetchone()
        return dict(row) if row else None

    def _set_research_alert_consent(
        self,
        telegram_user_id: int,
        *,
        subscribed: bool,
        telegram_update_id: int,
        notice_version: str = DEFAULT_PROMOTION_NOTICE_VERSION,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> bool:
        """Apply explicit alert consent using event time, not perpetual ID order.

        Telegram update IDs can become random after a long idle period. They
        are therefore replay keys only. A join must be newer than the current
        event watermark; an opt-out always wins conservatively.
        """

        _validate_private_identity(telegram_user_id, telegram_user_id)
        if not isinstance(subscribed, bool):
            raise ValueError("research alert consent must be a boolean")
        notice = validate_notice_version(notice_version)
        if (
            isinstance(telegram_update_id, bool)
            or not isinstance(telegram_update_id, int)
            or not 0 <= telegram_update_id <= MAX_TELEGRAM_UPDATE_ID
        ):
            raise ValueError("Telegram update ID is invalid")
        recipient = self.conn.execute(
            "SELECT 1 FROM recipients WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        if not recipient:
            raise ValueError("recipient must be registered before alert consent")
        desired = "subscribed" if subscribed else "unsubscribed"
        received = now or utc_now()
        occurred = event_at or received
        timestamp = iso_utc(received)
        event_timestamp = iso_utc(occurred)

        suppression = None
        if subscribed:
            suppression = self.conn.execute(
                """SELECT event_at, update_id FROM contact_suppressions
                   WHERE telegram_user_id = ?""",
                (telegram_user_id,),
            ).fetchone()
            if suppression and (
                occurred.astimezone(timezone.utc),
                telegram_update_id,
            ) <= (
                parse_utc(str(suppression["event_at"])),
                int(suppression["update_id"]),
            ):
                return False

        replay = self.conn.execute(
            """SELECT telegram_user_id, state, notice_version
               FROM research_alert_consent_events
               WHERE telegram_update_id = ?""",
            (telegram_update_id,),
        ).fetchone()
        if replay:
            if (
                int(replay["telegram_user_id"]) != telegram_user_id
                or str(replay["state"]) != desired
                or str(replay["notice_version"]) != notice
            ):
                raise ValueError("Telegram update ID conflicts with consent evidence")
            return False

        existing = self.conn.execute(
            """SELECT state, revision, last_update_id, notice_version,
                      first_subscribed_at, current_subscribed_at,
                      last_event_at, updated_at
               FROM research_alert_consents WHERE telegram_user_id = ?""",
            (telegram_user_id,),
        ).fetchone()
        if existing:
            watermark = (
                parse_utc(str(existing["last_event_at"])),
                int(existing["last_update_id"]),
            )
            event_order = (occurred.astimezone(timezone.utc), telegram_update_id)
            if subscribed and event_order <= watermark:
                return False
            if (
                subscribed
                and existing["state"] == desired
                and str(existing["notice_version"]) == notice
                and suppression is None
            ):
                return False
            revision = int(existing["revision"]) + 1
            first_subscribed_at = existing["first_subscribed_at"]
            if event_order > watermark:
                watermark_event_at = event_timestamp
                watermark_update_id = telegram_update_id
            else:
                # Withdrawal remains effective without lowering the event
                # watermark that protects it from an older delayed join.
                watermark_event_at = str(existing["last_event_at"])
                watermark_update_id = int(existing["last_update_id"])
        else:
            revision = 1
            first_subscribed_at = None
            watermark_event_at = event_timestamp
            watermark_update_id = telegram_update_id
        if subscribed and first_subscribed_at is None:
            first_subscribed_at = timestamp
        current_subscribed_at = timestamp if subscribed else None
        try:
            self.conn.execute(
                """INSERT INTO research_alert_consent_events
                   (telegram_update_id, telegram_user_id, state, notice_version,
                    event_at, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    telegram_update_id,
                    telegram_user_id,
                    desired,
                    notice,
                    event_timestamp,
                    timestamp,
                ),
            )
            self.conn.execute(
            """INSERT INTO research_alert_consents
               (telegram_user_id, state, revision, last_update_id,
                notice_version, first_subscribed_at, current_subscribed_at,
                last_event_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(telegram_user_id) DO UPDATE SET
                 state = excluded.state,
                 revision = excluded.revision,
                 last_update_id = excluded.last_update_id,
                 notice_version = excluded.notice_version,
                 first_subscribed_at = excluded.first_subscribed_at,
                 current_subscribed_at = excluded.current_subscribed_at,
                 last_event_at = excluded.last_event_at,
                 updated_at = excluded.updated_at""",
                (
                    telegram_user_id,
                    desired,
                    revision,
                    watermark_update_id,
                    notice,
                    first_subscribed_at,
                    current_subscribed_at,
                    watermark_event_at,
                    timestamp,
                ),
            )
            if subscribed:
                self.conn.execute(
                    "DELETE FROM contact_suppressions WHERE telegram_user_id = ?",
                    (telegram_user_id,),
                )
            else:
                self._upsert_contact_suppression(
                    telegram_user_id,
                    telegram_update_id=telegram_update_id,
                    reason="withdrawn",
                    event_at=occurred,
                    recorded_at=received,
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("alert consent conflicts with stored evidence") from exc
        return True

    @_atomic_store_method
    def set_research_alert_consent(
        self,
        telegram_user_id: int,
        *,
        subscribed: bool,
        telegram_update_id: int,
        notice_version: str = DEFAULT_PROMOTION_NOTICE_VERSION,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> bool:
        return self._set_research_alert_consent(
            telegram_user_id,
            subscribed=subscribed,
            telegram_update_id=telegram_update_id,
            notice_version=notice_version,
            event_at=event_at,
            now=now,
        )

    @_atomic_store_method
    def join_promotion_campaign(
        self,
        telegram_user_id: int,
        campaign_code: str,
        telegram_update_id: int,
        *,
        notice_version: str = DEFAULT_PROMOTION_NOTICE_VERSION,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> dict[str, bool]:
        """Atomically apply a notice-bound source attribution and alert opt-in."""

        _validate_private_identity(telegram_user_id, telegram_user_id)
        code = validate_campaign_code(campaign_code)
        active = self.conn.execute(
            """SELECT 1 FROM promotion_campaigns
               WHERE campaign_code = ? AND active = 1""",
            (code,),
        ).fetchone()
        if not active:
            return {
                "campaign_active": False,
                "attributed": False,
                "consent_changed": False,
                "subscribed": False,
            }
        prior_history = self.conn.execute(
            """SELECT 1 FROM research_alert_consents
               WHERE telegram_user_id = ?
               UNION ALL
               SELECT 1 FROM research_alert_consent_events
               WHERE telegram_user_id = ?
               UNION ALL
               SELECT 1 FROM promotion_attributions
               WHERE telegram_user_id = ?
               LIMIT 1""",
            (telegram_user_id, telegram_user_id, telegram_user_id),
        ).fetchone()
        eligible_for_attribution = prior_history is None
        changed = self._set_research_alert_consent(
            telegram_user_id,
            subscribed=True,
            telegram_update_id=telegram_update_id,
            notice_version=notice_version,
            event_at=event_at,
            now=now,
        )
        notice = validate_notice_version(notice_version)
        state = self.conn.execute(
            """SELECT state, notice_version FROM research_alert_consents
               WHERE telegram_user_id = ?""",
            (telegram_user_id,),
        ).fetchone()
        subscribed = bool(
            state
            and str(state["state"]) == "subscribed"
            and str(state["notice_version"]) == notice
        )
        attributed = False
        if eligible_for_attribution and changed and subscribed:
            attributed = self._record_promotion_attribution(
                telegram_user_id,
                code,
                telegram_update_id,
                now=now,
            )
        return {
            "campaign_active": True,
            "attributed": attributed,
            "consent_changed": changed,
            "subscribed": subscribed,
        }

    def research_alert_status(
        self,
        telegram_user_id: int,
        current_notice_version: str = DEFAULT_PROMOTION_NOTICE_VERSION,
    ) -> dict[str, Any]:
        _validate_private_identity(telegram_user_id, telegram_user_id)
        current_notice = validate_notice_version(current_notice_version)
        row = self.conn.execute(
            """SELECT state, revision, notice_version, first_subscribed_at,
                      current_subscribed_at, last_event_at, updated_at
               FROM research_alert_consents WHERE telegram_user_id = ?""",
            (telegram_user_id,),
        ).fetchone()
        if not row:
            return {
                "state": "not_joined",
                "revision": 0,
                "notice_version": None,
                "first_subscribed_at": None,
                "current_subscribed_at": None,
                "last_event_at": None,
                "updated_at": None,
            }
        result = dict(row)
        if (
            result["state"] == "subscribed"
            and result["notice_version"] != current_notice
        ):
            result["state"] = "needs_reconfirmation"
        return result

    @_atomic_store_method
    def purge_promotion_state(self, telegram_user_id: int) -> dict[str, int]:
        """Remove revocable campaign and alert state without touching ledgers."""

        _validate_private_identity(telegram_user_id, telegram_user_id)
        event_count = self.conn.execute(
            """SELECT COUNT(*) FROM research_alert_consent_events
               WHERE telegram_user_id = ?""",
            (telegram_user_id,),
        ).fetchone()[0]
        consent = self.conn.execute(
            "DELETE FROM research_alert_consents WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).rowcount
        attribution = self.conn.execute(
            "DELETE FROM promotion_attributions WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).rowcount
        # Events normally cascade with the consent owner, but a recipient may
        # remain because financial evidence is temporarily deletion-blocked.
        self.conn.execute(
            "DELETE FROM research_alert_consent_events WHERE telegram_user_id = ?",
            (telegram_user_id,),
        )
        return {
            "attributions": int(attribution),
            "consents": int(consent),
            "consent_events": int(event_count),
        }

    @_atomic_store_method
    def purge_nonfinancial_recipient_state(
        self,
        telegram_user_id: int,
        *,
        deletion_update_id: int | None = None,
        event_at: datetime | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Atomically suppress contact and purge behavior while ledgers may remain."""

        _validate_private_identity(telegram_user_id, telegram_user_id)
        current = now or utc_now()
        timestamp = iso_utc(current)
        if deletion_update_id is not None:
            if (
                isinstance(deletion_update_id, bool)
                or not isinstance(deletion_update_id, int)
                or not 0 <= deletion_update_id <= MAX_TELEGRAM_UPDATE_ID
            ):
                raise ValueError("Telegram update ID is invalid")
            self._upsert_contact_suppression(
                telegram_user_id,
                telegram_update_id=deletion_update_id,
                reason="deleted",
                event_at=event_at or current,
                recorded_at=current,
            )
        counts: dict[str, int] = {}
        for key, table in (
            ("correction_deliveries", "signal_correction_delivery_receipts"),
            ("deliveries", "delivery_receipts"),
            ("paper_actions", "paper_actions"),
            ("attributions", "promotion_attributions"),
            ("consent_events", "research_alert_consent_events"),
            ("consents", "research_alert_consents"),
        ):
            cursor = self.conn.execute(
                f"DELETE FROM {table} WHERE telegram_user_id = ?",
                (telegram_user_id,),
            )
            counts[key] = int(cursor.rowcount)
        counts["closed_support_cases"] = int(
            self.conn.execute(
                """DELETE FROM support_cases
                   WHERE telegram_user_id = ? AND state = 'closed'""",
                (telegram_user_id,),
            ).rowcount
        )
        counts["rate_limits"] = int(
            self.conn.execute(
                "DELETE FROM rate_limits WHERE scope = ?",
                (f"user:{telegram_user_id}",),
            ).rowcount
        )
        # When a finance/support hold needs the recipient row as an FK anchor,
        # minimize it to the no-contact identity and request time.
        self.conn.execute(
            """UPDATE recipients
               SET tier = 'free', entitlement_expires_at = NULL,
                   terms_version = NULL, terms_accepted_at = NULL,
                   privacy_notice_at = NULL, blocked_at = ?,
                   first_seen_at = ?, last_seen_at = ?
               WHERE telegram_user_id = ?""",
            (timestamp, timestamp, timestamp, telegram_user_id),
        )
        return counts

    def promotion_summary(
        self,
        current_notice_version: str = DEFAULT_PROMOTION_NOTICE_VERSION,
    ) -> dict[str, int]:
        current_notice = validate_notice_version(current_notice_version)
        return {
            "campaigns": int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM promotion_campaigns"
                ).fetchone()[0]
            ),
            "active_campaigns": int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM promotion_campaigns WHERE active = 1"
                ).fetchone()[0]
            ),
            "start_events": int(
                self.conn.execute(
                    "SELECT COALESCE(SUM(start_count), 0) FROM promotion_campaign_starts"
                ).fetchone()[0]
            ),
            "attributed_recipients": int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM promotion_attributions"
                ).fetchone()[0]
            ),
            "alerts_subscribed": int(
                self.conn.execute(
                    """SELECT COUNT(*) FROM research_alert_consents
                       WHERE state = 'subscribed' AND notice_version = ?""",
                    (current_notice,),
                ).fetchone()[0]
            ),
            "alerts_unsubscribed": int(
                self.conn.execute(
                    """SELECT COUNT(*) FROM research_alert_consents
                       WHERE state = 'unsubscribed'"""
                ).fetchone()[0]
            ),
            "alerts_need_reconfirmation": int(
                self.conn.execute(
                    """SELECT COUNT(*) FROM research_alert_consents
                       WHERE state = 'subscribed' AND notice_version <> ?""",
                    (current_notice,),
                ).fetchone()[0]
            ),
            "alert_consent_events": int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM research_alert_consent_events"
                ).fetchone()[0]
            ),
        }

    def promotion_campaign_metrics(
        self,
        current_notice_version: str = DEFAULT_PROMOTION_NOTICE_VERSION,
    ) -> list[dict[str, Any]]:
        """Return local campaign aggregates without recipient identifiers."""

        current_notice = validate_notice_version(current_notice_version)

        campaigns = self.conn.execute(
            """SELECT campaign_code, campaign_kind, active, created_at, disabled_at
               FROM promotion_campaigns ORDER BY campaign_code"""
        ).fetchall()
        result: list[dict[str, Any]] = []
        for campaign in campaigns:
            code = str(campaign["campaign_code"])
            start_events = int(
                self.conn.execute(
                    """SELECT COALESCE(SUM(start_count), 0)
                       FROM promotion_campaign_starts WHERE campaign_code = ?""",
                    (code,),
                ).fetchone()[0]
            )
            counts = self.conn.execute(
                """SELECT
                     COUNT(*) AS attributed_recipients,
                     COALESCE(SUM(CASE WHEN c.state = 'subscribed'
                                            AND c.notice_version = ?
                                       THEN 1 ELSE 0 END), 0)
                       AS currently_subscribed,
                     COALESCE(SUM(CASE WHEN c.state = 'unsubscribed' THEN 1 ELSE 0 END), 0)
                       AS currently_unsubscribed,
                     COALESCE(SUM(CASE WHEN c.state = 'subscribed'
                                            AND c.notice_version <> ?
                                       THEN 1 ELSE 0 END), 0)
                       AS needs_reconfirmation,
                     COALESCE(SUM(CASE WHEN EXISTS (
                       SELECT 1 FROM research_alert_consent_events e
                       WHERE e.telegram_user_id = a.telegram_user_id
                         AND e.state = 'subscribed'
                     ) THEN 1 ELSE 0 END), 0) AS ever_opted_in,
                     COALESCE(SUM(CASE WHEN EXISTS (
                       SELECT 1 FROM research_alert_consent_events e
                       WHERE e.telegram_user_id = a.telegram_user_id
                         AND e.state = 'unsubscribed'
                     ) THEN 1 ELSE 0 END), 0) AS ever_opted_out
                   FROM promotion_attributions a
                   LEFT JOIN research_alert_consents c
                     ON c.telegram_user_id = a.telegram_user_id
                   WHERE a.campaign_code = ?""",
                (current_notice, current_notice, code),
            ).fetchone()
            delivery = self.conn.execute(
                """SELECT
                     COALESCE(SUM(CASE WHEN d.status = 'sent' THEN 1 ELSE 0 END), 0)
                       AS signals_sent,
                     COALESCE(SUM(CASE WHEN d.status = 'unknown' THEN 1 ELSE 0 END), 0)
                       AS signals_unknown,
                     COUNT(DISTINCT CASE WHEN d.status = 'sent'
                                         THEN d.telegram_user_id END)
                       AS delivered_recipients
                   FROM promotion_attributions a
                   LEFT JOIN delivery_receipts d
                     ON d.telegram_user_id = a.telegram_user_id
                   WHERE a.campaign_code = ?""",
                (code,),
            ).fetchone()
            paper_actions = self.conn.execute(
                """SELECT COUNT(*) AS actions,
                          COUNT(DISTINCT p.telegram_user_id) AS actors
                   FROM paper_actions p
                   JOIN promotion_attributions a
                     ON a.telegram_user_id = p.telegram_user_id
                   WHERE a.campaign_code = ?""",
                (code,),
            ).fetchone()
            result.append(
                {
                    "campaign_code": code,
                    "campaign_kind": str(campaign["campaign_kind"]),
                    "active": bool(campaign["active"]),
                    "created_at": str(campaign["created_at"]),
                    "disabled_at": campaign["disabled_at"],
                    "start_events": start_events,
                    "attributed_recipients": int(counts["attributed_recipients"]),
                    "ever_opted_in": int(counts["ever_opted_in"]),
                    "ever_opted_out": int(counts["ever_opted_out"]),
                    "currently_subscribed": int(counts["currently_subscribed"]),
                    "currently_unsubscribed": int(counts["currently_unsubscribed"]),
                    "needs_reconfirmation": int(counts["needs_reconfirmation"]),
                    "delivered_recipients": int(delivery["delivered_recipients"]),
                    "signals_sent": int(delivery["signals_sent"]),
                    "signals_unknown": int(delivery["signals_unknown"]),
                    "paper_actors": int(paper_actions["actors"]),
                    "paper_actions": int(paper_actions["actions"]),
                }
            )
        return result

    def promotion_metrics_snapshot(
        self,
        current_notice_version: str = DEFAULT_PROMOTION_NOTICE_VERSION,
    ) -> tuple[dict[str, int], list[dict[str, Any]]]:
        """Read all promotion aggregates from one consistent SQLite snapshot."""

        if self.conn.in_transaction:
            raise sqlite3.OperationalError(
                "promotion snapshot cannot start inside an existing transaction"
            )
        self.conn.execute("BEGIN")
        try:
            summary = self.promotion_summary(current_notice_version)
            campaigns = self.promotion_campaign_metrics(current_notice_version)
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise
        return summary, campaigns

    def allow_interactive_request(
        self,
        telegram_user_id: int,
        *,
        now: datetime | None = None,
        per_user_per_minute: int = 20,
        global_per_minute: int = 300,
    ) -> bool:
        """Bound command/reply load without delaying payment control updates."""

        _validate_private_identity(telegram_user_id, telegram_user_id)
        if per_user_per_minute < 1 or global_per_minute < 1:
            raise ValueError("rate limits must be positive")
        minute = int((now or utc_now()).timestamp() // 60)
        limits = (("global", global_per_minute), (f"user:{telegram_user_id}", per_user_per_minute))
        with self.conn:
            rows: dict[str, sqlite3.Row | None] = {
                scope: self.conn.execute(
                    "SELECT minute_bucket, request_count FROM rate_limits WHERE scope = ?",
                    (scope,),
                ).fetchone()
                for scope, _ in limits
            }
            if any(
                row is not None
                and int(row["minute_bucket"]) == minute
                and int(row["request_count"]) >= limit
                for (scope, limit), row in ((item, rows[item[0]]) for item in limits)
            ):
                return False
            for scope, _ in limits:
                self.conn.execute(
                    """INSERT INTO rate_limits(scope, minute_bucket, request_count)
                       VALUES (?, ?, 1)
                       ON CONFLICT(scope) DO UPDATE SET
                         request_count = CASE
                           WHEN minute_bucket = excluded.minute_bucket
                           THEN request_count + 1 ELSE 1 END,
                         minute_bucket = excluded.minute_bucket""",
                    (scope, minute),
                )
            self.conn.execute(
                "DELETE FROM rate_limits WHERE minute_bucket < ?",
                (minute - 1_440,),
            )
        return True

    def mark_privacy_notice(
        self, telegram_user_id: int, *, now: datetime | None = None
    ) -> bool:
        cursor = self.conn.execute(
            """UPDATE recipients SET privacy_notice_at = COALESCE(privacy_notice_at, ?)
               WHERE telegram_user_id = ?""",
            (iso_utc(now or utc_now()), telegram_user_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def accept_terms(
        self,
        telegram_user_id: int,
        terms_version: str,
        *,
        now: datetime | None = None,
    ) -> None:
        version = terms_version.strip()
        if not version:
            raise ValueError("terms version is required")
        timestamp = iso_utc(now or utc_now())
        cursor = self.conn.execute(
            """UPDATE recipients SET terms_version = ?, terms_accepted_at = ?,
                                      last_seen_at = ?
               WHERE telegram_user_id = ?""",
            (version, timestamp, timestamp, telegram_user_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("recipient must be registered before accepting terms")
        self.conn.commit()

    def has_accepted_terms(self, telegram_user_id: int, terms_version: str) -> bool:
        row = self.conn.execute(
            """SELECT 1 FROM recipients
               WHERE telegram_user_id = ? AND terms_version = ?
                 AND terms_accepted_at IS NOT NULL""",
            (telegram_user_id, terms_version),
        ).fetchone()
        return row is not None

    def create_invoice_intent(
        self,
        *,
        telegram_user_id: int,
        plan_code: str,
        total_amount: int,
        terms_version: str,
        now: datetime | None = None,
        ttl_minutes: int = 15,
    ) -> str:
        if total_amount <= 0 or total_amount > 10_000:
            raise ValueError("Stars amount must be between 1 and 10000")
        if not self.has_accepted_terms(telegram_user_id, terms_version):
            raise ValueError("current terms have not been accepted")
        created = now or utc_now()
        with self.conn:
            self.conn.execute(
                """UPDATE invoice_intents SET state = 'expired'
                   WHERE telegram_user_id = ? AND plan_code = ?
                     AND state = 'created'
                     AND julianday(expires_at) <= julianday(?)""",
                (telegram_user_id, plan_code, iso_utc(created)),
            )
            pending = self.conn.execute(
                """SELECT payload, state, currency, total_amount, terms_version
                   FROM invoice_intents
                   WHERE telegram_user_id = ? AND plan_code = ?
                     AND state IN ('created', 'reserved') LIMIT 1""",
                (telegram_user_id, plan_code),
            ).fetchone()
            if pending:
                if (
                    pending["state"] == "created"
                    and pending["currency"] == "XTR"
                    and pending["total_amount"] == total_amount
                    and pending["terms_version"] == terms_version
                ):
                    return str(pending["payload"])
                raise ValueError("a subscription checkout is already in progress")
            existing = self.latest_subscription(telegram_user_id, plan_code)
            if existing:
                if existing["cancellation_pending_at"]:
                    raise ValueError(
                        "subscription cancellation requires provider reconciliation"
                    )
                period_ended = parse_utc(existing["current_period_end"]) <= created
                if existing["renewal_state"] not in {"canceled", "failed"} or not period_ended:
                    raise ValueError(
                        "the previous subscription must be canceled and its paid period ended"
                    )
                self.conn.execute(
                    """UPDATE subscriptions SET revoked_at = ?, updated_at = ?
                       WHERE initial_charge_id = ?""",
                    (
                        iso_utc(created),
                        iso_utc(created),
                        existing["initial_charge_id"],
                    ),
                )
        expires = created + timedelta(minutes=ttl_minutes)
        payload = "sub:v1:" + secrets.token_urlsafe(18)
        self.conn.execute(
            """INSERT INTO invoice_intents
               (payload, telegram_user_id, plan_code, currency, total_amount,
                terms_version, created_at, expires_at, state,
                pre_checkout_query_id, reserved_at)
               VALUES (?, ?, ?, 'XTR', ?, ?, ?, ?, 'created', NULL, NULL)""",
            (
                payload,
                telegram_user_id,
                plan_code,
                total_amount,
                terms_version,
                iso_utc(created),
                iso_utc(expires),
            ),
        )
        self.conn.commit()
        return payload

    def invoice_intent(self, payload: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM invoice_intents WHERE payload = ?", (payload,)
        ).fetchone()
        return dict(row) if row else None

    def release_invoice_reservation(
        self, payload: str, pre_checkout_query_id: str
    ) -> bool:
        """Release only a checkout Telegram explicitly failed to approve."""

        cursor = self.conn.execute(
            """UPDATE invoice_intents
               SET state = 'created', pre_checkout_query_id = NULL, reserved_at = NULL
               WHERE payload = ? AND state = 'reserved'
                 AND pre_checkout_query_id = ?""",
            (payload, pre_checkout_query_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def reconcile_reserved_invoice_no_charge(
        self,
        payload: str,
        *,
        reconciliation_ref: str,
        now: datetime | None = None,
    ) -> bool:
        """Reject legacy free-text assertions; provider evidence is required."""

        del payload, reconciliation_ref, now
        raise ValueError(
            "manual no-charge reconciliation is disabled; "
            "structured provider evidence is required"
        )

    def reserve_invoice_intent(
        self,
        *,
        payload: str,
        telegram_user_id: int,
        currency: str,
        total_amount: int,
        pre_checkout_query_id: str,
        current_terms_version: str,
        now: datetime | None = None,
    ) -> tuple[bool, str]:
        current = now or utc_now()
        timestamp = iso_utc(current)
        with self.conn:
            row = self.conn.execute(
                "SELECT * FROM invoice_intents WHERE payload = ?", (payload,)
            ).fetchone()
            if not row:
                return False, "Unknown or expired invoice. Please start again."
            if row["telegram_user_id"] != telegram_user_id:
                return False, "This invoice belongs to a different Telegram account."
            if row["currency"] != currency or row["total_amount"] != total_amount:
                return False, "Invoice price or currency does not match."
            if row["terms_version"] != current_terms_version:
                return False, "Terms changed; please review the current version."
            if parse_utc(row["expires_at"]) <= current:
                self.conn.execute(
                    "UPDATE invoice_intents SET state = 'expired' WHERE payload = ?",
                    (payload,),
                )
                return False, "This invoice expired. Please request a new one."
            if row["state"] == "reserved" and row["pre_checkout_query_id"] == pre_checkout_query_id:
                return True, "Checkout already verified."
            if row["state"] != "created":
                return False, "This invoice has already been used."
            if self.open_subscription(telegram_user_id, row["plan_code"], now=now):
                return False, "An active subscription already exists."
            reserved = self.conn.execute(
                """UPDATE invoice_intents
                   SET state = 'reserved', pre_checkout_query_id = ?, reserved_at = ?
                   WHERE payload = ? AND state = 'created'""",
                (pre_checkout_query_id, timestamp, payload),
            )
            if reserved.rowcount != 1:
                winner = self.conn.execute(
                    """SELECT state, pre_checkout_query_id FROM invoice_intents
                       WHERE payload = ?""",
                    (payload,),
                ).fetchone()
                if (
                    winner
                    and winner["state"] == "reserved"
                    and winner["pre_checkout_query_id"] == pre_checkout_query_id
                ):
                    return True, "Checkout already verified."
                return False, "This invoice is already being processed."
        return True, "Checkout verified."

    def is_entitled(self, telegram_user_id: int, *, now: datetime | None = None) -> bool:
        timestamp = iso_utc(now or utc_now())
        row = self.conn.execute(
            """SELECT 1 FROM recipients
               WHERE telegram_user_id = ? AND tier = 'research'
                 AND julianday(entitlement_expires_at) > julianday(?)""",
            (telegram_user_id, timestamp),
        ).fetchone()
        return row is not None

    def open_subscription(
        self,
        telegram_user_id: int,
        plan_code: str = "research",
        *,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        timestamp = iso_utc(now or utc_now())
        row = self.conn.execute(
            """SELECT * FROM subscriptions
               WHERE telegram_user_id = ? AND plan_code = ? AND revoked_at IS NULL
                 AND julianday(current_period_end) > julianday(?)
               ORDER BY julianday(created_at) DESC LIMIT 1""",
            (telegram_user_id, plan_code, timestamp),
        ).fetchone()
        return dict(row) if row else None

    def recipient_status(
        self, telegram_user_id: int, *, now: datetime | None = None
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """SELECT tier, entitlement_expires_at, first_seen_at, last_seen_at
               FROM recipients WHERE telegram_user_id = ?""",
            (telegram_user_id,),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["active"] = self.is_entitled(telegram_user_id, now=now)
        return result

    def _recompute_recipient_entitlement(
        self, telegram_user_id: int, current: datetime
    ) -> datetime | None:
        timestamp = iso_utc(current)
        row = self.conn.execute(
            """SELECT entitlement_expires_at FROM payments
               WHERE telegram_user_id = ? AND refunded_at IS NULL
                 AND julianday(entitlement_expires_at) > julianday(?)
               ORDER BY julianday(entitlement_expires_at) DESC LIMIT 1""",
            (telegram_user_id, timestamp),
        ).fetchone()
        expires = parse_utc(row["entitlement_expires_at"]) if row else None
        self.conn.execute(
            """UPDATE recipients
               SET tier = CASE WHEN ? IS NULL THEN 'free' ELSE 'research' END,
                   entitlement_expires_at = ?
               WHERE telegram_user_id = ?""",
            (
                iso_utc(expires) if expires else None,
                iso_utc(expires) if expires else None,
                telegram_user_id,
            ),
        )
        return expires

    def _recompute_subscription_period(
        self, initial_charge_id: str, current: datetime
    ) -> datetime:
        row = self.conn.execute(
            """SELECT entitlement_expires_at FROM payments
               WHERE initial_charge_id = ? AND refunded_at IS NULL
               ORDER BY julianday(entitlement_expires_at) DESC LIMIT 1""",
            (initial_charge_id,),
        ).fetchone()
        period_end = parse_utc(row["entitlement_expires_at"]) if row else current
        self.conn.execute(
            """UPDATE subscriptions SET current_period_end = ?
               WHERE initial_charge_id = ?""",
            (iso_utc(period_end), initial_charge_id),
        )
        return period_end

    @_atomic_store_method
    def record_subscription_payment(
        self,
        *,
        telegram_user_id: int,
        private_chat_id: int,
        telegram_payment_charge_id: str,
        currency: str,
        total_amount: int,
        invoice_payload: str,
        is_recurring: bool,
        is_first_recurring: bool,
        paid_at: datetime | None = None,
        subscription_expiration_unix: int | None,
        telegram_update_id: int | None = None,
    ) -> PaymentResult:
        now = paid_at or utc_now()
        _validate_private_identity(telegram_user_id, private_chat_id)
        _bounded_utf8(telegram_payment_charge_id, 256, "Telegram payment charge ID")
        _bounded_utf8(invoice_payload, 128, "invoice payload")
        if not invoice_payload.startswith("sub:v1:"):
            raise ValueError("invoice payload is invalid")
        if currency != "XTR":
            raise ValueError("subscription payment must use Telegram Stars")
        if isinstance(total_amount, bool) or not isinstance(total_amount, int):
            raise ValueError("subscription amount must be an integer")
        if total_amount <= 0 or total_amount > 10_000:
            raise ValueError("subscription amount is outside the supported range")
        if not isinstance(is_recurring, bool) or not isinstance(is_first_recurring, bool):
            raise ValueError("subscription flags must be booleans")
        if not is_recurring:
            raise ValueError("a recurring payment is required")
        if (
            isinstance(subscription_expiration_unix, bool)
            or not isinstance(subscription_expiration_unix, int)
        ):
            raise ValueError("a Telegram subscription expiration is required")
        if telegram_update_id is not None and (
            isinstance(telegram_update_id, bool)
            or not isinstance(telegram_update_id, int)
            or not 0 <= telegram_update_id <= MAX_TELEGRAM_UPDATE_ID
        ):
            raise ValueError("invalid Telegram payment update ID")
        try:
            expires = datetime.fromtimestamp(subscription_expiration_unix, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError("subscription expiration is outside the supported range") from exc
        if expires < now - timedelta(days=32) or expires > now + timedelta(days=32):
            raise ValueError("subscription expiration exceeds the supported reconciliation window")

        # A completed provider scan can observe a refund before Telegram
        # delivers the corresponding successful_payment update.  The provider
        # may omit invoice_payload on that outgoing row, so bind the durable
        # evidence to the charge, user, whole-Star amount, and invoice type;
        # then materialize the payload-bearing refund event from the validated
        # payment update.  This keeps the delayed payment from ever granting
        # access.  The eager transaction serializes this lookup with scan
        # completion.
        provider_refund = self.conn.execute(
            """SELECT st.amount, st.nanostar_amount, st.partner_type,
                      st.transaction_type, st.telegram_user_id,
                      st.invoice_payload, st.subscription_period,
                      st.first_seen_at
               FROM star_transactions st
               JOIN star_scan_runs sr
                 ON sr.run_id = st.last_complete_run_id
                AND sr.state = 'complete'
               WHERE st.transaction_id = ? AND st.direction = 'outgoing'""",
            (telegram_payment_charge_id,),
        ).fetchone()
        if provider_refund:
            provider_refund_matches = bool(
                provider_refund["partner_type"] == "user"
                and provider_refund["transaction_type"] == "invoice_payment"
                and provider_refund["telegram_user_id"] == telegram_user_id
                and provider_refund["amount"] == total_amount
                and provider_refund["nanostar_amount"] == 0
                and provider_refund["subscription_period"] in {None, 2_592_000}
                and provider_refund["invoice_payload"] in {None, invoice_payload}
            )
            if not provider_refund_matches:
                raise ValueError(
                    "payment conflicts with completed provider refund evidence"
                )
            self._begin_payment_refund_in_transaction(
                telegram_payment_charge_id,
                telegram_user_id=telegram_user_id,
                currency=currency,
                total_amount=total_amount,
                invoice_payload=invoice_payload,
                current=now,
            )

        existing = self.conn.execute(
            """SELECT telegram_user_id, currency, total_amount, invoice_payload,
                      entitlement_expires_at, initial_charge_id, refunded_at,
                      is_recurring, is_first_recurring
               FROM payments
               WHERE telegram_payment_charge_id = ?""",
            (telegram_payment_charge_id,),
        ).fetchone()
        if existing:
            if (
                existing["telegram_user_id"] != telegram_user_id
                or existing["currency"] != currency
                or existing["total_amount"] != total_amount
                or existing["invoice_payload"] != invoice_payload
                or bool(existing["is_recurring"]) != is_recurring
                or bool(existing["is_first_recurring"]) != is_first_recurring
                or int(parse_utc(existing["entitlement_expires_at"]).timestamp())
                != subscription_expiration_unix
            ):
                raise ValueError("payment charge ID was reused with different details")
            with contextlib.nullcontext():
                entitlement = self._recompute_recipient_entitlement(
                    telegram_user_id, now
                )
            subscription = self.conn.execute(
                """SELECT cancellation_pending_at, cancellation_intent_at, revoked_at
                   FROM subscriptions
                   WHERE initial_charge_id = ?""",
                (existing["initial_charge_id"],),
            ).fetchone()
            cancellation_required = bool(
                subscription
                and subscription["revoked_at"] is None
                and (
                    existing["refunded_at"] is not None
                    or subscription["cancellation_intent_at"] is not None
                )
            )
            if cancellation_required:
                with contextlib.nullcontext():
                    self.conn.execute(
                        """UPDATE subscriptions
                           SET cancellation_pending_at = COALESCE(cancellation_pending_at, ?),
                               cancellation_intent_at = COALESCE(cancellation_intent_at, ?),
                               updated_at = ?
                           WHERE initial_charge_id = ? AND revoked_at IS NULL""",
                        (
                            iso_utc(now),
                            iso_utc(now),
                            iso_utc(now),
                            existing["initial_charge_id"],
                        ),
                    )
            return PaymentResult(
                entitlement_expires_at=entitlement,
                initial_charge_id=str(existing["initial_charge_id"]),
                invoice_payload=invoice_payload,
                refunded=existing["refunded_at"] is not None,
                cancellation_required=cancellation_required,
                duplicate=True,
            )

        intent = self.invoice_intent(invoice_payload)
        if not intent or intent["telegram_user_id"] != telegram_user_id:
            raise ValueError("payment does not match a user-bound invoice intent")
        if intent["currency"] != currency or intent["total_amount"] != total_amount:
            raise ValueError("payment does not match invoice amount or currency")
        expected_intent_state = "reserved" if is_first_recurring else "paid"
        if intent["state"] != expected_intent_state:
            raise ValueError("invoice was not approved at pre-checkout")

        timestamp = iso_utc(now)
        self.conn.execute(
            """INSERT INTO recipients
               (telegram_user_id, private_chat_id, tier, entitlement_expires_at,
                terms_version, terms_accepted_at, blocked_at,
                first_seen_at, last_seen_at, privacy_notice_at)
               VALUES (?, ?, 'free', NULL, NULL, NULL, NULL, ?, ?, NULL)
               ON CONFLICT(telegram_user_id) DO UPDATE SET
                 private_chat_id = excluded.private_chat_id,
                 blocked_at = NULL,
                 last_seen_at = excluded.last_seen_at""",
            (telegram_user_id, private_chat_id, timestamp, timestamp),
        )

        if is_first_recurring:
            existing_subscription = self.latest_subscription(
                telegram_user_id, intent["plan_code"]
            )
            if existing_subscription:
                raise ValueError("an active subscription already exists")
            initial_charge_id = telegram_payment_charge_id
        else:
            row = self.conn.execute(
                """SELECT * FROM subscriptions
                   WHERE telegram_user_id = ? AND plan_code = ?
                     AND invoice_payload = ? AND revoked_at IS NULL
                   ORDER BY julianday(created_at) DESC LIMIT 1""",
                (telegram_user_id, intent["plan_code"], invoice_payload),
            ).fetchone()
            existing_subscription = dict(row) if row else None
            if not existing_subscription:
                raise ValueError("renewal has no matching subscription invoice")
            initial_charge_id = existing_subscription["initial_charge_id"]

        pending_refund = self.conn.execute(
            """SELECT * FROM refund_events
               WHERE telegram_payment_charge_id = ?""",
            (telegram_payment_charge_id,),
        ).fetchone()
        if pending_refund and (
            pending_refund["telegram_user_id"] != telegram_user_id
            or pending_refund["currency"] != currency
            or pending_refund["total_amount"] != total_amount
            or pending_refund["invoice_payload"] != invoice_payload
        ):
            raise ValueError("payment does not match the earlier refund event")

        paid_at_text = iso_utc(now)
        durable_cancellation_at = (
            str(pending_refund["received_at"])
            if pending_refund
            else str(existing_subscription["cancellation_intent_at"])
            if existing_subscription and existing_subscription["cancellation_intent_at"]
            else None
        )
        cancellation_required = durable_cancellation_at is not None
        expires_text = iso_utc(expires)
        effective_entitlement: datetime | None = expires
        with contextlib.nullcontext():
            if is_first_recurring:
                pending_state = self.conn.execute(
                    """SELECT state, update_id FROM pending_subscription_states
                       WHERE telegram_user_id = ? AND invoice_payload = ?""",
                    (telegram_user_id, invoice_payload),
                ).fetchone()
                pending_update_id = (
                    int(pending_state["update_id"]) if pending_state else None
                )
                pending_is_newer = bool(
                    pending_state
                    and (
                        telegram_update_id is None
                        or pending_update_id is not None
                        and pending_update_id > telegram_update_id
                    )
                )
                pending_state_name = str(pending_state["state"]) if pending_state else None
                renewal_state = (
                    "canceled"
                    if durable_cancellation_at or pending_state_name == "canceled"
                    else pending_state_name
                    if pending_is_newer
                    else "active"
                )
                observed_update_ids = [
                    value
                    for value in (pending_update_id, telegram_update_id)
                    if value is not None
                ]
                last_provider_update_id = max(observed_update_ids, default=None)
                try:
                    self.conn.execute(
                        """INSERT INTO subscriptions
                        (initial_charge_id, telegram_user_id, plan_code,
                        invoice_payload, current_period_end, renewal_state,
                        cancellation_pending_at, cancellation_intent_at,
                        last_provider_update_id,
                        revoked_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                        (
                            initial_charge_id,
                            telegram_user_id,
                            intent["plan_code"],
                            invoice_payload,
                            expires_text,
                            renewal_state,
                            paid_at_text if cancellation_required else None,
                            durable_cancellation_at,
                            last_provider_update_id,
                            paid_at_text,
                            paid_at_text,
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ValueError(
                        "invoice payload already belongs to a subscription"
                    ) from exc
                self.conn.execute(
                    """DELETE FROM pending_subscription_states
                       WHERE telegram_user_id = ? AND invoice_payload = ?""",
                    (telegram_user_id, invoice_payload),
                )
            else:
                current_period_end = parse_utc(existing_subscription["current_period_end"])
                effective_period_end = max(current_period_end, expires)
                previous_update_id = existing_subscription["last_provider_update_id"]
                payment_is_newer = bool(
                    telegram_update_id is not None
                    and (
                        previous_update_id is None
                        or telegram_update_id > int(previous_update_id)
                    )
                )
                renewal_state = str(existing_subscription["renewal_state"])
                if durable_cancellation_at:
                    renewal_state = "canceled"
                elif payment_is_newer and renewal_state != "canceled":
                    renewal_state = "active"
                last_provider_update_id = (
                    telegram_update_id if payment_is_newer else previous_update_id
                )
                self.conn.execute(
                    """UPDATE subscriptions
                       SET current_period_end = ?,
                           renewal_state = ?,
                           last_provider_update_id = ?,
                           cancellation_pending_at = CASE
                             WHEN ? IS NOT NULL THEN ? ELSE cancellation_pending_at END,
                           cancellation_intent_at = CASE
                             WHEN ? IS NOT NULL THEN COALESCE(cancellation_intent_at, ?)
                             ELSE cancellation_intent_at END,
                           updated_at = ?
                       WHERE initial_charge_id = ?""",
                    (
                        iso_utc(effective_period_end),
                        renewal_state,
                        last_provider_update_id,
                        durable_cancellation_at,
                        paid_at_text,
                        durable_cancellation_at,
                        durable_cancellation_at,
                        paid_at_text,
                        initial_charge_id,
                    ),
                )
            self.conn.execute(
                """INSERT INTO payments
                   (telegram_payment_charge_id, telegram_user_id, currency,
                    initial_charge_id, total_amount, invoice_payload, paid_at,
                    entitlement_expires_at, is_recurring, is_first_recurring,
                    refunded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    telegram_payment_charge_id,
                    telegram_user_id,
                    currency,
                    initial_charge_id,
                    total_amount,
                    invoice_payload,
                    paid_at_text,
                    expires_text,
                    int(is_recurring),
                    int(is_first_recurring),
                    pending_refund["received_at"] if pending_refund else None,
                ),
            )
            if pending_refund:
                self.conn.execute(
                    """UPDATE refund_events
                       SET resolved_at = ?, resolution_code = 'matched_payment'
                       WHERE telegram_payment_charge_id = ?""",
                    (paid_at_text, telegram_payment_charge_id),
                )
            self.conn.execute(
                "UPDATE invoice_intents SET state = 'paid' WHERE payload = ?",
                (invoice_payload,),
            )
            self._recompute_subscription_period(initial_charge_id, now)
            effective_entitlement = self._recompute_recipient_entitlement(
                telegram_user_id, now
            )
            self.conn.execute(
                """UPDATE recipients
                   SET last_seen_at = ?
                   WHERE telegram_user_id = ?""",
                (paid_at_text, telegram_user_id),
            )
        return PaymentResult(
            entitlement_expires_at=effective_entitlement,
            initial_charge_id=str(initial_charge_id),
            invoice_payload=invoice_payload,
            refunded=pending_refund is not None,
            cancellation_required=cancellation_required,
        )

    def set_subscription_state(
        self,
        *,
        telegram_user_id: int,
        invoice_payload: str,
        state: str,
        update_id: int | None = None,
        now: datetime | None = None,
    ) -> bool:
        if state not in {"active", "canceled", "failed"}:
            raise ValueError("unsupported subscription state")
        if update_id is not None and (
            isinstance(update_id, bool)
            or not isinstance(update_id, int)
            or not 0 <= update_id <= MAX_TELEGRAM_UPDATE_ID
        ):
            raise ValueError("invalid Telegram update ID")
        timestamp = iso_utc(now or utc_now())
        with self.conn:
            cursor = self.conn.execute(
                """UPDATE subscriptions
                   SET renewal_state = ?, updated_at = ?,
                       last_provider_update_id = CASE
                         WHEN ? IS NULL THEN last_provider_update_id
                         WHEN last_provider_update_id IS NULL OR ? > last_provider_update_id
                         THEN ? ELSE last_provider_update_id END,
                       cancellation_pending_at = CASE
                         WHEN ? = 'canceled' THEN NULL ELSE cancellation_pending_at END
                   WHERE telegram_user_id = ? AND invoice_payload = ?
                     AND revoked_at IS NULL""",
                (
                    state,
                    timestamp,
                    update_id,
                    update_id,
                    update_id,
                    state,
                    telegram_user_id,
                    invoice_payload,
                ),
            )
        return cursor.rowcount > 0

    def mark_subscription_cancellation_pending(
        self,
        *,
        telegram_user_id: int,
        invoice_payload: str,
        now: datetime | None = None,
    ) -> bool:
        timestamp = iso_utc(now or utc_now())
        cursor = self.conn.execute(
            """UPDATE subscriptions
               SET cancellation_pending_at = COALESCE(cancellation_pending_at, ?),
                   cancellation_intent_at = COALESCE(cancellation_intent_at, ?),
                   updated_at = ?
               WHERE telegram_user_id = ? AND invoice_payload = ?
                 AND revoked_at IS NULL""",
            (timestamp, timestamp, timestamp, telegram_user_id, invoice_payload),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def apply_subscription_update(
        self,
        *,
        telegram_user_id: int,
        invoice_payload: str,
        state: str,
        update_id: int,
        now: datetime | None = None,
    ) -> bool:
        """Apply an ordered BotSubscriptionUpdated or retain it until payment."""

        if state not in {"active", "canceled", "failed"}:
            raise ValueError("unsupported subscription state")
        if update_id < 0 or update_id > MAX_TELEGRAM_UPDATE_ID:
            raise ValueError("invalid Telegram update ID")
        timestamp = iso_utc(now or utc_now())
        with self.conn:
            subscription = self.conn.execute(
                """SELECT initial_charge_id, last_provider_update_id,
                          cancellation_intent_at
                   FROM subscriptions
                   WHERE telegram_user_id = ? AND invoice_payload = ?
                     AND revoked_at IS NULL""",
                (telegram_user_id, invoice_payload),
            ).fetchone()
            if subscription:
                if state == "active" and subscription["cancellation_intent_at"]:
                    return False
                previous = subscription["last_provider_update_id"]
                if previous is not None and int(previous) >= update_id:
                    return False
                self.conn.execute(
                    """UPDATE subscriptions
                       SET renewal_state = ?, last_provider_update_id = ?,
                           cancellation_pending_at = CASE
                             WHEN ? = 'canceled' THEN NULL ELSE cancellation_pending_at END,
                           updated_at = ?
                       WHERE initial_charge_id = ?""",
                    (
                        state,
                        update_id,
                        state,
                        timestamp,
                        subscription["initial_charge_id"],
                    ),
                )
                return True
            self.conn.execute(
                """INSERT INTO pending_subscription_states
                   (telegram_user_id, invoice_payload, state, update_id, received_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(telegram_user_id, invoice_payload) DO UPDATE SET
                     state = CASE WHEN excluded.update_id > update_id
                                  THEN excluded.state ELSE state END,
                     received_at = CASE WHEN excluded.update_id > update_id
                                        THEN excluded.received_at ELSE received_at END,
                     update_id = MAX(update_id, excluded.update_id)""",
                (telegram_user_id, invoice_payload, state, update_id, timestamp),
            )
        return True

    def cancellation_intent_target(
        self, *, telegram_user_id: int, invoice_payload: str
    ) -> dict[str, str] | None:
        row = self.conn.execute(
            """SELECT initial_charge_id, invoice_payload
               FROM subscriptions
               WHERE telegram_user_id = ? AND invoice_payload = ?
                 AND revoked_at IS NULL AND cancellation_intent_at IS NOT NULL""",
            (telegram_user_id, invoice_payload),
        ).fetchone()
        return dict(row) if row else None

    def latest_subscription(
        self, telegram_user_id: int, plan_code: str = "research"
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """SELECT * FROM subscriptions
               WHERE telegram_user_id = ? AND plan_code = ? AND revoked_at IS NULL
               ORDER BY julianday(created_at) DESC LIMIT 1""",
            (telegram_user_id, plan_code),
        ).fetchone()
        return dict(row) if row else None

    def begin_payment_refund(
        self,
        telegram_payment_charge_id: str,
        *,
        telegram_user_id: int,
        currency: str,
        total_amount: int,
        invoice_payload: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        current = now or utc_now()
        with self.conn:
            return self._begin_payment_refund_in_transaction(
                telegram_payment_charge_id,
                telegram_user_id=telegram_user_id,
                currency=currency,
                total_amount=total_amount,
                invoice_payload=invoice_payload,
                current=current,
            )

    def _begin_payment_refund_in_transaction(
        self,
        telegram_payment_charge_id: str,
        *,
        telegram_user_id: int,
        currency: str,
        total_amount: int,
        invoice_payload: str,
        current: datetime,
    ) -> dict[str, Any] | None:
        """Apply refund evidence inside the caller's existing transaction."""

        timestamp = iso_utc(current)
        _validate_private_identity(telegram_user_id, telegram_user_id)
        _bounded_utf8(telegram_payment_charge_id, 256, "Telegram payment charge ID")
        _bounded_utf8(invoice_payload, 128, "invoice payload")
        if not invoice_payload.startswith("sub:v1:"):
            raise ValueError("invoice payload is invalid")
        if currency != "XTR":
            raise ValueError("refund must use Telegram Stars")
        if (
            isinstance(total_amount, bool)
            or not isinstance(total_amount, int)
            or total_amount <= 0
            or total_amount > 10_000
        ):
            raise ValueError("refund amount is outside the supported range")
        intent = self.invoice_intent(invoice_payload)
        if (
            not intent
            or intent["telegram_user_id"] != telegram_user_id
            or intent["currency"] != currency
            or intent["total_amount"] != total_amount
            or intent["state"] not in {"reserved", "paid"}
        ):
            raise ValueError("refund does not match a user-bound checkout")
        recorded_event = self.conn.execute(
            """SELECT * FROM refund_events
               WHERE telegram_payment_charge_id = ?""",
            (telegram_payment_charge_id,),
        ).fetchone()
        if recorded_event and (
            recorded_event["telegram_user_id"] != telegram_user_id
            or recorded_event["currency"] != currency
            or recorded_event["total_amount"] != total_amount
            or recorded_event["invoice_payload"] != invoice_payload
        ):
            raise ValueError("refund charge ID was reused with different details")
        if not recorded_event:
            self.conn.execute(
                """INSERT INTO refund_events
                   (telegram_payment_charge_id, telegram_user_id, currency,
                    total_amount, invoice_payload, received_at, resolved_at)
                   VALUES (?, ?, ?, ?, ?, ?, NULL)""",
                (
                    telegram_payment_charge_id,
                    telegram_user_id,
                    currency,
                    total_amount,
                    invoice_payload,
                    timestamp,
                ),
            )
        payment = self.conn.execute(
            """SELECT telegram_user_id, initial_charge_id, currency, total_amount,
                      invoice_payload, refunded_at
               FROM payments WHERE telegram_payment_charge_id = ?""",
            (telegram_payment_charge_id,),
        ).fetchone()
        if not payment:
            return None
        if (
            payment["telegram_user_id"] != telegram_user_id
            or payment["currency"] != currency
            or payment["total_amount"] != total_amount
            or payment["invoice_payload"] != invoice_payload
        ):
            raise ValueError("refund does not match the recorded payment")
        self.conn.execute(
            """UPDATE payments SET refunded_at = COALESCE(refunded_at, ?)
               WHERE telegram_payment_charge_id = ?""",
            (timestamp, telegram_payment_charge_id),
        )
        subscription = self.conn.execute(
            """SELECT initial_charge_id, invoice_payload, current_period_end,
                      renewal_state, cancellation_pending_at, revoked_at
               FROM subscriptions
               WHERE initial_charge_id = ?""",
            (payment["initial_charge_id"],),
        ).fetchone()
        if subscription:
            # A refund is a fresh reason to make renewal impossible.  Do not
            # trust an older local cancellation observation until this new
            # refund-driven intent has been confirmed at the provider.
            cancellation_required = subscription["revoked_at"] is None
            if cancellation_required:
                self.conn.execute(
                    """UPDATE subscriptions
                       SET cancellation_pending_at = COALESCE(cancellation_pending_at, ?),
                           cancellation_intent_at = COALESCE(cancellation_intent_at, ?),
                           updated_at = ?
                       WHERE initial_charge_id = ?""",
                    (
                        timestamp,
                        timestamp,
                        timestamp,
                        payment["initial_charge_id"],
                    ),
                )
            self._recompute_subscription_period(
                str(payment["initial_charge_id"]), current
            )
            remaining_value = self._recompute_recipient_entitlement(
                telegram_user_id, current
            )
            remaining = iso_utc(remaining_value) if remaining_value else None
            self.conn.execute(
                """UPDATE refund_events
                   SET resolved_at = COALESCE(resolved_at, ?),
                       resolution_code = COALESCE(resolution_code, 'matched_payment')
                   WHERE telegram_payment_charge_id = ?""",
                (timestamp, telegram_payment_charge_id),
            )
        if not subscription:
            return None
        return {
            "initial_charge_id": str(subscription["initial_charge_id"]),
            "invoice_payload": str(subscription["invoice_payload"]),
            "remaining_entitlement_expires_at": remaining,
            "cancellation_required": cancellation_required,
            "already_refunded": payment["refunded_at"] is not None,
        }

    def reconcile_unmatched_refund(
        self,
        telegram_payment_charge_id: str,
        *,
        reconciliation_ref: str,
        now: datetime | None = None,
    ) -> bool:
        """Reject legacy free-text assertions; provider evidence is required."""

        del telegram_payment_charge_id, reconciliation_ref, now
        raise ValueError(
            "manual refund reconciliation is disabled; "
            "structured provider evidence is required"
        )

    def initial_subscription_charge(self, telegram_user_id: int) -> str | None:
        row = self.conn.execute(
            """SELECT initial_charge_id FROM subscriptions
               WHERE telegram_user_id = ? AND revoked_at IS NULL
               ORDER BY julianday(created_at) DESC LIMIT 1""",
            (telegram_user_id,),
        ).fetchone()
        return str(row["initial_charge_id"]) if row else None

    def open_support_case(
        self, telegram_user_id: int, *, now: datetime | None = None
    ) -> str:
        existing = self.conn.execute(
            """SELECT case_id FROM support_cases
               WHERE telegram_user_id = ? AND state = 'open'
               ORDER BY julianday(created_at) DESC LIMIT 1""",
            (telegram_user_id,),
        ).fetchone()
        if existing:
            return str(existing["case_id"])
        case_id = "support-" + uuid.uuid4().hex[:12]
        self.conn.execute(
            """INSERT INTO support_cases
               (case_id, telegram_user_id, state, created_at, closed_at)
               VALUES (?, ?, 'open', ?, NULL)""",
            (case_id, telegram_user_id, iso_utc(now or utc_now())),
        )
        self.conn.commit()
        return case_id

    def active_recipients(self, *, now: datetime | None = None) -> list[dict[str, int]]:
        timestamp = iso_utc(now or utc_now())
        rows = self.conn.execute(
            """SELECT telegram_user_id, private_chat_id FROM recipients
               WHERE tier = 'research'
                 AND julianday(entitlement_expires_at) > julianday(?)
                 AND blocked_at IS NULL
               ORDER BY telegram_user_id""",
            (timestamp,),
        ).fetchall()
        return [dict(row) for row in rows]

    def pending_deliveries(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
        notice_version: str = DEFAULT_PROMOTION_NOTICE_VERSION,
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1_000:
            raise ValueError("delivery limit must be between 1 and 1000")
        notice = validate_notice_version(notice_version)
        timestamp = iso_utc(now or utc_now())
        rows = self.conn.execute(
            """WITH eligible AS (
                 SELECT s.signal_id, s.envelope_json, s.content_digest,
                        s.pipeline_status, s.status_revision,
                        s.lifecycle_event_id, s.issued_at,
                        r.telegram_user_id, r.private_chat_id,
                        CASE
                          WHEN r.tier = 'research'
                           AND julianday(r.entitlement_expires_at) > julianday(?)
                          THEN 'research' ELSE 'public'
                        END AS delivery_view,
                        ROW_NUMBER() OVER (
                          PARTITION BY r.telegram_user_id
                          ORDER BY julianday(s.issued_at), s.signal_id
                        ) AS queued_rank,
                        (
                          SELECT COUNT(*) FROM delivery_receipts recent
                          WHERE recent.telegram_user_id = r.telegram_user_id
                            AND recent.status IN ('sent', 'unknown')
                            AND julianday(recent.attempted_at) >
                                julianday(?, '-7 days')
                        ) AS recent_delivery_count
                 FROM signals s CROSS JOIN recipients r
                 JOIN research_alert_consents c
                   ON c.telegram_user_id = r.telegram_user_id
                  AND c.state = 'subscribed'
                  AND c.notice_version = ?
                 LEFT JOIN delivery_receipts d
                   ON d.signal_id = s.signal_id
                  AND d.telegram_user_id = r.telegram_user_id
                 WHERE s.distributable = 1
                   AND julianday(s.expires_at) > julianday(?)
                   AND julianday(s.issued_at) >=
                       julianday(c.current_subscribed_at)
                   AND r.blocked_at IS NULL
                   AND NOT EXISTS (
                     SELECT 1 FROM contact_suppressions suppression
                     WHERE suppression.telegram_user_id = r.telegram_user_id
                   )
                   AND (d.status IS NULL OR
                        (d.status = 'failed' AND d.attempt_count < 5
                         AND (d.next_attempt_at IS NULL OR
                              julianday(d.next_attempt_at) <= julianday(?))))
               )
               SELECT * FROM eligible
               WHERE recent_delivery_count + queued_rank <= ?
               ORDER BY julianday(issued_at), telegram_user_id
               LIMIT ?""",
            (
                timestamp,
                timestamp,
                notice,
                timestamp,
                timestamp,
                MAX_ALERT_DELIVERIES_PER_ROLLING_WEEK,
                int(limit),
            ),
        ).fetchall()
        return [
            {
                "signal_id": row["signal_id"],
                "envelope": envelope,
                "telegram_user_id": row["telegram_user_id"],
                "private_chat_id": row["private_chat_id"],
                "delivery_view": row["delivery_view"],
            }
            for row in rows
            if (envelope := self._decode_signal_row(row)) is not None
        ]

    def pending_signal_corrections(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Return revocation notices owed to recipients of the original signal."""

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 1_000
        ):
            raise ValueError("correction delivery limit is invalid")
        timestamp = iso_utc(now or utc_now())
        rows = self.conn.execute(
            """SELECT e.event_id, e.signal_id, e.status, e.occurred_at,
                      e.reason_code, r.telegram_user_id, r.private_chat_id
               FROM signal_lifecycle_events e
               JOIN delivery_receipts original
                 ON original.signal_id = e.signal_id
                AND original.status IN ('sent', 'unknown')
               JOIN recipients r
                 ON r.telegram_user_id = original.telegram_user_id
               LEFT JOIN signal_correction_delivery_receipts correction
                 ON correction.event_id = e.event_id
                AND correction.telegram_user_id = r.telegram_user_id
               WHERE e.status = 'REVOKED'
                 AND r.blocked_at IS NULL
                 AND NOT EXISTS (
                   SELECT 1 FROM contact_suppressions suppression
                   WHERE suppression.telegram_user_id = r.telegram_user_id
                 )
                 AND (correction.status IS NULL OR
                      (correction.status = 'failed'
                       AND correction.attempt_count < 5
                       AND (correction.next_attempt_at IS NULL OR
                            julianday(correction.next_attempt_at) <= julianday(?))))
               ORDER BY julianday(e.occurred_at), e.event_id, r.telegram_user_id
               LIMIT ?""",
            (timestamp, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_signal_correction_delivery(
        self,
        *,
        event_id: str,
        telegram_user_id: int,
        status: str,
        telegram_message_id: int | None = None,
        error_code: str | None = None,
        retry_after_seconds: int | None = None,
        now: datetime | None = None,
    ) -> None:
        _bounded_utf8(event_id, 128, "lifecycle event ID")
        _validate_private_identity(telegram_user_id, telegram_user_id)
        if status not in {"sent", "failed", "unknown"}:
            raise ValueError("correction status must be sent, failed, or unknown")
        attempted = now or utc_now()
        previous = self.conn.execute(
            """SELECT attempt_count FROM signal_correction_delivery_receipts
               WHERE event_id = ? AND telegram_user_id = ?""",
            (event_id, telegram_user_id),
        ).fetchone()
        attempt_count = int(previous["attempt_count"]) + 1 if previous else 1
        if status == "failed":
            delay = retry_after_seconds
            if isinstance(delay, bool) or not isinstance(delay, int) or delay <= 0:
                delay = min(3_600, 30 * (2 ** min(attempt_count - 1, 7)))
            next_attempt = iso_utc(
                attempted + timedelta(seconds=min(delay, 3_600))
            )
        else:
            next_attempt = None
        code = (
            re.sub(r"[^A-Za-z0-9_.-]", "_", str(error_code))[:80]
            if error_code is not None
            else None
        )
        self.conn.execute(
            """INSERT INTO signal_correction_delivery_receipts
               (event_id, telegram_user_id, status, telegram_message_id,
                error_code, attempt_count, next_attempt_at, attempted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(event_id, telegram_user_id) DO UPDATE SET
                 status = excluded.status,
                 telegram_message_id = excluded.telegram_message_id,
                 error_code = excluded.error_code,
                 attempt_count = excluded.attempt_count,
                 next_attempt_at = excluded.next_attempt_at,
                 attempted_at = excluded.attempted_at""",
            (
                event_id,
                telegram_user_id,
                status,
                telegram_message_id,
                code,
                attempt_count,
                next_attempt,
                iso_utc(attempted),
            ),
        )
        self.conn.commit()

    def record_delivery(
        self,
        *,
        signal_id: str,
        telegram_user_id: int,
        status: str,
        telegram_message_id: int | None = None,
        error_code: str | None = None,
        retry_after_seconds: int | None = None,
        now: datetime | None = None,
    ) -> None:
        if status not in {"sent", "failed", "unknown"}:
            raise ValueError("delivery status must be sent, failed, or unknown")
        attempted = now or utc_now()
        previous = self.conn.execute(
            """SELECT attempt_count FROM delivery_receipts
               WHERE signal_id = ? AND telegram_user_id = ?""",
            (signal_id, telegram_user_id),
        ).fetchone()
        attempt_count = int(previous["attempt_count"]) + 1 if previous else 1
        if status == "failed":
            delay = retry_after_seconds
            if isinstance(delay, bool) or not isinstance(delay, int) or delay <= 0:
                delay = min(3600, 30 * (2 ** min(attempt_count - 1, 7)))
            delay = min(delay, 3_600)
            next_attempt = iso_utc(attempted + timedelta(seconds=delay))
        else:
            next_attempt = None
        self.conn.execute(
            """INSERT INTO delivery_receipts
               (signal_id, telegram_user_id, status, telegram_message_id,
                error_code, attempt_count, next_attempt_at, attempted_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(signal_id, telegram_user_id) DO UPDATE SET
                 status = excluded.status,
                 telegram_message_id = excluded.telegram_message_id,
                 error_code = excluded.error_code,
                 attempt_count = excluded.attempt_count,
                 next_attempt_at = excluded.next_attempt_at,
                 attempted_at = excluded.attempted_at""",
            (
                signal_id,
                telegram_user_id,
                status,
                telegram_message_id,
                error_code,
                attempt_count,
                next_attempt,
                iso_utc(attempted),
            ),
        )
        self.conn.commit()

    def mark_recipient_blocked(
        self, telegram_user_id: int, blocked: bool, *, now: datetime | None = None
    ) -> bool:
        value = iso_utc(now or utc_now()) if blocked else None
        cursor = self.conn.execute(
            "UPDATE recipients SET blocked_at = ? WHERE telegram_user_id = ?",
            (value, telegram_user_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def record_paper_action(
        self,
        *,
        telegram_user_id: int,
        signal: Mapping[str, Any],
        simulated_amount_usdc: float,
        explicit_request_ref: str,
        now: datetime | None = None,
    ) -> str:
        if not self.is_entitled(telegram_user_id, now=now):
            raise ValueError("an active research entitlement is required")
        if (
            isinstance(simulated_amount_usdc, bool)
            or not math.isfinite(float(simulated_amount_usdc))
            or simulated_amount_usdc <= 0
            or simulated_amount_usdc > 10_000
        ):
            raise ValueError("simulated amount must be finite and between 0 and 10000")
        existing = self.conn.execute(
            "SELECT paper_action_id FROM paper_actions WHERE explicit_request_ref = ?",
            (explicit_request_ref,),
        ).fetchone()
        if existing:
            return str(existing["paper_action_id"])
        action_id = "paper-" + uuid.uuid4().hex[:16]
        self.conn.execute(
            """INSERT INTO paper_actions
               (paper_action_id, telegram_user_id, signal_id, direction,
                entry_probability, simulated_amount_usdc, created_at,
                explicit_request_ref)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                action_id,
                telegram_user_id,
                signal["signal_id"],
                signal["market"]["direction"],
                signal["market"]["quoted_outcome_token_price"],
                float(simulated_amount_usdc),
                iso_utc(now or utc_now()),
                explicit_request_ref,
            ),
        )
        self.conn.commit()
        return action_id

    def delete_recipient(self, telegram_user_id: int) -> bool:
        with self.conn:
            # Provider-ledger evidence is intentionally retained for payment
            # integrity, but it no longer needs to remain linkable to a
            # deleted recipient once the financial deletion gate has passed.
            self.conn.execute(
                """UPDATE star_transactions SET telegram_user_id = NULL
                   WHERE telegram_user_id = ?""",
                (telegram_user_id,),
            )
            self.conn.execute(
                """UPDATE star_reconciliation_issues SET telegram_user_id = NULL
                   WHERE telegram_user_id = ?""",
                (telegram_user_id,),
            )
            cursor = self.conn.execute(
                "DELETE FROM recipients WHERE telegram_user_id = ?",
                (telegram_user_id,),
            )
            self.conn.execute(
                "DELETE FROM rate_limits WHERE scope = ?",
                (f"user:{telegram_user_id}",),
            )
        return cursor.rowcount > 0

    def compact_storage(self) -> None:
        """Operator-triggered compaction, kept off the interactive update path."""

        self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.conn.execute("VACUUM")
        self._secure_sqlite_files()

    def recipient_deletion_block(
        self, telegram_user_id: int, *, now: datetime | None = None
    ) -> str | None:
        """Return why local deletion is unsafe, or ``None`` when it is safe."""

        current = now or utc_now()
        timestamp = iso_utc(current)
        unresolved_refund = self.conn.execute(
            """SELECT 1 FROM refund_events
               WHERE telegram_user_id = ? AND resolved_at IS NULL LIMIT 1""",
            (telegram_user_id,),
        ).fetchone()
        if unresolved_refund:
            return "refund_reconciliation_pending"
        reserved_checkout = self.conn.execute(
            """SELECT 1 FROM invoice_intents
               WHERE telegram_user_id = ? AND state = 'reserved' LIMIT 1""",
            (telegram_user_id,),
        ).fetchone()
        if reserved_checkout:
            return "checkout_reconciliation_pending"
        pending_invoice = self.conn.execute(
            """SELECT 1 FROM invoice_intents
               WHERE telegram_user_id = ?
                 AND state = 'created'
                 AND julianday(expires_at) > julianday(?)
               LIMIT 1""",
            (telegram_user_id, timestamp),
        ).fetchone()
        if pending_invoice:
            return "invoice_pending"

        subscriptions = self.conn.execute(
            """SELECT * FROM subscriptions
               WHERE telegram_user_id = ? AND revoked_at IS NULL
               ORDER BY julianday(created_at) DESC""",
            (telegram_user_id,),
        ).fetchall()
        if any(row["cancellation_pending_at"] for row in subscriptions):
            return "renewal_cancellation_pending"
        if any(row["renewal_state"] not in {"canceled", "failed"} for row in subscriptions):
            return "renewal_not_canceled"
        if any(parse_utc(row["current_period_end"]) > current for row in subscriptions):
            return "paid_period_open"
        return None

    def subscriptions_for_user(self, telegram_user_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT * FROM subscriptions
               WHERE telegram_user_id = ? AND revoked_at IS NULL
               ORDER BY julianday(created_at)""",
            (telegram_user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def bind_telegram_provider(
        self,
        bot_id: int,
        api_origin: str,
        *,
        allow_create: bool = True,
    ) -> None:
        """Bind this database to one bot and one credential-free API origin."""

        self._bind_telegram_provider(
            bot_id,
            api_origin,
            authenticated_bot_username=None,
            allow_create=allow_create,
            allow_legacy_username_backfill=False,
        )

    def bind_authenticated_telegram_provider(
        self,
        bot_id: int,
        api_origin: str,
        bot_username: object,
        *,
        allow_create: bool = True,
        allow_legacy_username_backfill: bool = False,
    ) -> None:
        """Bind the canonical username returned by an authenticated ``getMe``.

        Callers must not pass a user-supplied username here.  A legacy database
        containing only the matching ID/origin pair is upgraded only when the
        authenticated caller explicitly permits that one-way backfill.
        """

        username = self._validate_telegram_bot_username(bot_username)
        self._bind_telegram_provider(
            bot_id,
            api_origin,
            authenticated_bot_username=username,
            allow_create=allow_create,
            allow_legacy_username_backfill=allow_legacy_username_backfill,
        )

    def _bind_telegram_provider(
        self,
        bot_id: int,
        api_origin: str,
        *,
        authenticated_bot_username: str | None,
        allow_create: bool,
        allow_legacy_username_backfill: bool,
    ) -> None:

        if (
            isinstance(bot_id, bool)
            or not isinstance(bot_id, int)
            or not 0 < bot_id <= (1 << 52) - 1
        ):
            raise ValueError("Telegram provider bot ID is invalid")
        origin = _bounded_utf8(api_origin, 500, "Telegram API origin")
        try:
            parsed_origin = urllib.parse.urlsplit(origin)
            _ = parsed_origin.port
        except ValueError:
            parsed_origin = urllib.parse.SplitResult("", "", "", "", "")
        try:
            loopback = parsed_origin.hostname == "localhost" or ipaddress.ip_address(
                parsed_origin.hostname or ""
            ).is_loopback
        except ValueError:
            loopback = False
        if (
            parsed_origin.scheme not in {"http", "https"}
            or not parsed_origin.hostname
            or parsed_origin.username is not None
            or parsed_origin.password is not None
            or parsed_origin.path not in {"", "/"}
            or parsed_origin.query
            or parsed_origin.fragment
            or (parsed_origin.scheme == "http" and not loopback)
        ):
            raise ValueError("Telegram API origin must be a credential-free bare origin")
        origin = origin.rstrip("/")
        with self.conn:
            rows = {
                str(row["key"]): str(row["value"])
                for row in self.conn.execute(
                    """SELECT key, value FROM bot_state
                       WHERE key IN ('telegram_provider_bot_id',
                                     'telegram_provider_api_origin',
                                     'telegram_provider_bot_username')"""
                ).fetchall()
            }
            provider_keys = {
                "telegram_provider_bot_id",
                "telegram_provider_api_origin",
            }
            present_provider_keys = provider_keys.intersection(rows)
            if present_provider_keys and present_provider_keys != provider_keys:
                raise ValueError("Telegram provider binding is incomplete")
            if "telegram_provider_bot_username" in rows and not present_provider_keys:
                raise ValueError("Telegram provider binding is incomplete")
            if present_provider_keys:
                try:
                    bound_bot_id = int(rows["telegram_provider_bot_id"])
                except (KeyError, ValueError) as exc:
                    raise ValueError("Telegram provider binding is invalid") from exc
                if bound_bot_id != bot_id or not secrets.compare_digest(
                    rows["telegram_provider_api_origin"], origin
                ):
                    raise ValueError(
                        "gateway database is bound to a different Telegram provider"
                    )
                bound_username = rows.get("telegram_provider_bot_username")
                if bound_username is not None:
                    bound_username = self._validate_telegram_bot_username(
                        bound_username
                    )
                if authenticated_bot_username is not None:
                    if bound_username is not None:
                        if not secrets.compare_digest(
                            bound_username.casefold(),
                            authenticated_bot_username.casefold(),
                        ):
                            raise ValueError(
                                "gateway database is bound to a different Telegram bot username"
                            )
                    elif allow_legacy_username_backfill:
                        self.conn.execute(
                            "INSERT INTO bot_state(key, value) VALUES (?, ?)",
                            (
                                "telegram_provider_bot_username",
                                authenticated_bot_username,
                            ),
                        )
                    else:
                        raise ValueError(
                            "gateway database has no verified Telegram bot username; "
                            "run bot-doctor first"
                        )
                return
            if not allow_create:
                raise ValueError(
                    "gateway database is not bound to a Telegram bot; run bot-doctor first"
                )
            values = [
                ("telegram_provider_bot_id", str(bot_id)),
                ("telegram_provider_api_origin", origin),
            ]
            if authenticated_bot_username is not None:
                values.append(
                    (
                        "telegram_provider_bot_username",
                        authenticated_bot_username,
                    )
                )
            self.conn.executemany(
                "INSERT INTO bot_state(key, value) VALUES (?, ?)",
                values,
            )

    def require_telegram_provider_bot_username(
        self, expected_username: object
    ) -> str:
        """Return durable provider spelling after a case-insensitive match."""

        expected = self._validate_telegram_bot_username(expected_username)
        rows = {
            str(row["key"]): str(row["value"])
            for row in self.conn.execute(
                """SELECT key, value FROM bot_state
                   WHERE key IN ('telegram_provider_bot_id',
                                 'telegram_provider_api_origin',
                                 'telegram_provider_bot_username')"""
            ).fetchall()
        }
        if not {
            "telegram_provider_bot_id",
            "telegram_provider_api_origin",
        }.issubset(rows):
            raise ValueError(
                "gateway database has no verified Telegram bot username; "
                "run bot-doctor first"
            )
        bound = rows.get("telegram_provider_bot_username")
        if bound is None:
            raise ValueError(
                "gateway database has no verified Telegram bot username; "
                "run bot-doctor first"
            )
        bound = self._validate_telegram_bot_username(bound)
        if not secrets.compare_digest(bound.casefold(), expected.casefold()):
            raise ValueError(
                "requested Research Bot username does not match the verified gateway binding"
            )
        return bound

    @staticmethod
    def _validate_telegram_bot_username(value: object) -> str:
        if (
            not isinstance(value, str)
            or not 5 <= len(value) <= 32
            or not _TELEGRAM_BOT_USERNAME.fullmatch(value)
        ):
            raise ValueError(
                "bot username must be 5-32 ASCII letters, digits, or underscores, "
                "and end in bot"
            )
        return value

    def bind_star_provider(self, bot_id: int, api_origin: str) -> None:
        """Backward-compatible name for the gateway-wide provider binding."""

        self.bind_telegram_provider(bot_id, api_origin)

    def begin_star_scan(
        self,
        run_id: str,
        bot_id: int,
        api_origin: str,
        *,
        now: datetime | None = None,
    ) -> None:
        run = _bounded_utf8(run_id, 128, "Star scan run ID")
        origin = _bounded_utf8(api_origin, 500, "Telegram API origin").rstrip("/")
        self.bind_telegram_provider(bot_id, origin)
        try:
            with self.conn:
                self.conn.execute(
                    """INSERT INTO star_scan_runs
                       (run_id, telegram_bot_id, api_origin, started_at, state)
                       VALUES (?, ?, ?, ?, 'running')""",
                    (run, bot_id, origin, iso_utc(now or utc_now())),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Star scan run ID was already used") from exc

    @_atomic_store_method
    def fail_star_scan(
        self,
        run_id: str,
        error_code: str,
        *,
        pass_count: int = 0,
        now: datetime | None = None,
    ) -> None:
        run = _bounded_utf8(run_id, 128, "Star scan run ID")
        code = re.sub(r"[^A-Za-z0-9_.-]", "_", str(error_code))[:80] or "unknown"
        if (
            isinstance(pass_count, bool)
            or not isinstance(pass_count, int)
            or not 0 <= pass_count <= 2
        ):
            raise ValueError("Star scan pass count is invalid")
        cursor = self.conn.execute(
            """UPDATE star_scan_runs
               SET state = 'failed', completed_at = ?, pass_count = ?, error_code = ?
               WHERE run_id = ? AND state = 'running'""",
            (iso_utc(now or utc_now()), pass_count, code, run),
        )
        if cursor.rowcount != 1:
            raise ValueError("Star scan run is not open")

    @staticmethod
    def _validated_star_observation(value: Mapping[str, Any]) -> dict[str, Any]:
        expected = {
            "transaction_id",
            "direction",
            "amount",
            "nanostar_amount",
            "transaction_date",
            "partner_type",
            "transaction_type",
            "telegram_user_id",
            "invoice_payload",
            "subscription_period",
            "semantic_digest",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("Star observation shape is invalid")
        result = dict(value)
        result["transaction_id"] = _bounded_utf8(
            result["transaction_id"], 256, "Star transaction ID"
        )
        if result["direction"] not in {"incoming", "outgoing"}:
            raise ValueError("Star transaction direction is invalid")
        for name, minimum, maximum in (
            ("amount", 0, (1 << 63) - 1),
            ("nanostar_amount", 0, 999_999_999),
            ("transaction_date", 1, (1 << 31) - 1),
        ):
            item = result[name]
            if (
                isinstance(item, bool)
                or not isinstance(item, int)
                or not minimum <= item <= maximum
            ):
                raise ValueError(f"Star {name.replace('_', ' ')} is invalid")
        if result["amount"] == 0 and result["nanostar_amount"] == 0:
            raise ValueError("Star transaction amount is empty")
        result["partner_type"] = _bounded_utf8(
            result["partner_type"], 80, "Star transaction partner type"
        )
        for name, limit in (("transaction_type", 80), ("invoice_payload", 128)):
            item = result[name]
            if item is not None:
                result[name] = _bounded_utf8(item, limit, f"Star {name.replace('_', ' ')}")
        user_id = result["telegram_user_id"]
        if user_id is not None:
            _validate_private_identity(user_id, user_id)
        period = result["subscription_period"]
        if period is not None and (
            isinstance(period, bool)
            or not isinstance(period, int)
            or not 0 < period <= (1 << 31) - 1
        ):
            raise ValueError("Star subscription period is invalid")
        partner_type = result["partner_type"]
        transaction_type = result["transaction_type"]
        invoice_payload = result["invoice_payload"]
        if partner_type not in STAR_PARTNER_TYPES:
            raise ValueError("Star transaction partner type is unsupported")
        if partner_type == "user":
            if transaction_type not in STAR_USER_TRANSACTION_TYPES:
                raise ValueError("Star user transaction type is unsupported")
            if transaction_type == "invoice_payment":
                if user_id is None:
                    raise ValueError("Star invoice payment user is required")
                if period not in {None, STAR_SUBSCRIPTION_PERIOD_SECONDS}:
                    raise ValueError("Star subscription period is unsupported")
            elif any(item is not None for item in (user_id, invoice_payload, period)):
                raise ValueError("Star non-invoice user fields are invalid")
        elif any(
            item is not None
            for item in (transaction_type, user_id, invoice_payload, period)
        ):
            raise ValueError("Star non-user partner fields are invalid")
        digest = result["semantic_digest"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Star transaction semantic digest is invalid")
        semantic_material = {
            name: result[name] for name in expected if name != "semantic_digest"
        }
        calculated = hashlib.sha256(
            json.dumps(
                semantic_material,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("ascii")
        ).hexdigest()
        if not secrets.compare_digest(digest, calculated):
            raise ValueError("Star transaction semantic digest does not match")
        return result

    @staticmethod
    def _star_issue_key(
        reason_code: str, transaction_id: str | None, direction: str | None
    ) -> str:
        material = json.dumps(
            [reason_code, transaction_id, direction],
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "star-issue-" + hashlib.sha256(material).hexdigest()[:32]

    @staticmethod
    def _validated_star_issue(value: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {
            "issue_key",
            "severity",
            "reason_code",
            "transaction_id",
            "direction",
            "telegram_user_id",
        }
        if not isinstance(value, Mapping) or not set(value) <= allowed:
            raise ValueError("Star reconciliation issue shape is invalid")
        result = {name: value.get(name) for name in allowed}
        result["issue_key"] = _bounded_utf8(
            result["issue_key"], 128, "Star issue key"
        )
        if result["severity"] not in {"warning", "critical"}:
            raise ValueError("Star issue severity is invalid")
        code = result["reason_code"]
        if not isinstance(code, str) or not re.fullmatch(r"[a-z0-9_]{1,80}", code):
            raise ValueError("Star issue reason code is invalid")
        if result["transaction_id"] is not None:
            result["transaction_id"] = _bounded_utf8(
                result["transaction_id"], 256, "Star issue transaction ID"
            )
        if result["direction"] not in {None, "incoming", "outgoing"}:
            raise ValueError("Star issue direction is invalid")
        if result["telegram_user_id"] is not None:
            _validate_private_identity(
                result["telegram_user_id"], result["telegram_user_id"]
            )
        return result

    def _open_star_support_case(self, telegram_user_id: int, timestamp: str) -> None:
        existing = self.conn.execute(
            """SELECT 1 FROM support_cases
               WHERE telegram_user_id = ? AND state = 'open' LIMIT 1""",
            (telegram_user_id,),
        ).fetchone()
        if not existing:
            self.conn.execute(
                """INSERT INTO support_cases
                   (case_id, telegram_user_id, state, created_at, closed_at)
                   VALUES (?, ?, 'open', ?, NULL)""",
                ("support-" + uuid.uuid4().hex[:12], telegram_user_id, timestamp),
            )

    @_atomic_store_method
    def complete_star_scan(
        self,
        run_id: str,
        observations: Iterable[Mapping[str, Any]],
        terminal_offset: int,
        snapshot_digest: str,
        issues: Iterable[Mapping[str, Any]],
        *,
        pass_digests: Sequence[str],
        now: datetime | None = None,
    ) -> dict[str, int | bool | str]:
        """Persist one stable full provider snapshot and apply positive evidence only."""

        run = _bounded_utf8(run_id, 128, "Star scan run ID")
        if (
            isinstance(terminal_offset, bool)
            or not isinstance(terminal_offset, int)
            or terminal_offset < 0
            or terminal_offset > (1 << 52)
        ):
            raise ValueError("Star scan terminal offset is invalid")
        if not isinstance(snapshot_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", snapshot_digest
        ):
            raise ValueError("Star snapshot digest is invalid")
        normalized = [self._validated_star_observation(item) for item in observations]
        supplied_issues = [self._validated_star_issue(item) for item in issues]
        if (
            len(pass_digests) != 2
            or any(
                not isinstance(item, str)
                or not re.fullmatch(r"[0-9a-f]{64}", item)
                for item in pass_digests
            )
            or not all(
                secrets.compare_digest(item, snapshot_digest)
                for item in pass_digests
            )
        ):
            raise ValueError("Star scan pass attestations are invalid")
        observation_keys = [
            (str(item["transaction_id"]), str(item["direction"]))
            for item in normalized
        ]
        issue_keys = [str(item["issue_key"]) for item in supplied_issues]
        if (
            observation_keys != sorted(observation_keys)
            or len(observation_keys) != len(set(observation_keys))
            or issue_keys != sorted(issue_keys)
            or len(issue_keys) != len(set(issue_keys))
            or terminal_offset != len(normalized) + len(supplied_issues)
        ):
            raise ValueError("Star snapshot membership or ordering is invalid")
        calculated_snapshot_digest = hashlib.sha256(
            json.dumps(
                {
                    "terminal_offset": terminal_offset,
                    "observations": normalized,
                    "issues": supplied_issues,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("ascii")
        ).hexdigest()
        if not secrets.compare_digest(snapshot_digest, calculated_snapshot_digest):
            raise ValueError("Star snapshot digest does not match its contents")
        current = now or utc_now()
        timestamp = iso_utc(current)
        row = self.conn.execute(
            "SELECT state FROM star_scan_runs WHERE run_id = ?", (run,)
        ).fetchone()
        if not row or row["state"] != "running":
            raise ValueError("Star scan run is not open")

        generated: dict[str, dict[str, Any]] = {
            str(item["issue_key"]): item for item in supplied_issues
        }
        resolved_issue_keys: set[str] = set()

        def add_issue(
            reason: str,
            observation: Mapping[str, Any] | None,
            *,
            severity: str = "critical",
            telegram_user_id: int | None = None,
        ) -> None:
            transaction_id = (
                str(observation["transaction_id"]) if observation else None
            )
            direction = str(observation["direction"]) if observation else None
            key = self._star_issue_key(reason, transaction_id, direction)
            generated[key] = {
                "issue_key": key,
                "severity": severity,
                "reason_code": reason,
                "transaction_id": transaction_id,
                "direction": direction,
                "telegram_user_id": telegram_user_id,
            }

        def resolve_issue(
            reason: str, observation: Mapping[str, Any]
        ) -> None:
            resolved_issue_keys.add(
                self._star_issue_key(
                    reason,
                    str(observation["transaction_id"]),
                    str(observation["direction"]),
                )
            )

        unique: dict[tuple[str, str], dict[str, Any]] = {}
        conflicted_keys: set[tuple[str, str]] = set()
        with contextlib.nullcontext():
            for observation in normalized:
                key = (
                    str(observation["transaction_id"]),
                    str(observation["direction"]),
                )
                if key in conflicted_keys:
                    continue
                duplicate = unique.get(key)
                if duplicate and duplicate["semantic_digest"] != observation["semantic_digest"]:
                    add_issue("snapshot_duplicate_semantic_conflict", observation)
                    unique.pop(key, None)
                    conflicted_keys.add(key)
                    continue
                unique[key] = observation
                existing = self.conn.execute(
                    """SELECT semantic_digest FROM star_transactions
                       WHERE transaction_id = ? AND direction = ?""",
                    key,
                ).fetchone()
                if existing and existing["semantic_digest"] != observation["semantic_digest"]:
                    add_issue("stored_transaction_semantic_conflict", observation)
                    unique.pop(key, None)
                    conflicted_keys.add(key)
                    self.conn.execute(
                        """UPDATE star_transactions SET last_seen_at = ?
                           WHERE transaction_id = ? AND direction = ?""",
                        (timestamp, *key),
                    )
                    continue
                self.conn.execute(
                    """INSERT INTO star_transactions
                       (transaction_id, direction, amount, nanostar_amount,
                        transaction_date, partner_type, transaction_type,
                        telegram_user_id, invoice_payload, subscription_period,
                        semantic_digest, first_seen_at, last_seen_at,
                        last_complete_run_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(transaction_id, direction) DO UPDATE SET
                         last_seen_at = excluded.last_seen_at,
                         last_complete_run_id = excluded.last_complete_run_id""",
                    (
                        observation["transaction_id"],
                        observation["direction"],
                        observation["amount"],
                        observation["nanostar_amount"],
                        observation["transaction_date"],
                        observation["partner_type"],
                        observation["transaction_type"],
                        observation["telegram_user_id"],
                        observation["invoice_payload"],
                        observation["subscription_period"],
                        observation["semantic_digest"],
                        timestamp,
                        timestamp,
                        run,
                    ),
                )

        confirmed_incoming_ids: set[str] = set()
        refund_actions: list[tuple[dict[str, Any], sqlite3.Row | None]] = []
        with contextlib.nullcontext():
            for observation in unique.values():
                payment = self.conn.execute(
                    """SELECT * FROM payments
                       WHERE telegram_payment_charge_id = ?""",
                    (observation["transaction_id"],),
                ).fetchone()
                if (
                    observation["partner_type"] != "user"
                    or observation["transaction_type"] != "invoice_payment"
                ):
                    if payment or (
                        isinstance(observation["invoice_payload"], str)
                        and observation["invoice_payload"].startswith("sub:v1:")
                    ):
                        add_issue(
                            "provider_transaction_type_mismatch",
                            observation,
                            telegram_user_id=(
                                int(payment["telegram_user_id"]) if payment else None
                            ),
                        )
                    continue
                observed_user = observation["telegram_user_id"]
                observed_payload = observation["invoice_payload"]
                exact_payment = bool(
                    payment
                    and observed_user == payment["telegram_user_id"]
                    and observation["amount"] == payment["total_amount"]
                    and observation["nanostar_amount"] == 0
                    and observation["subscription_period"] in {None, 2_592_000}
                    and (
                        observed_payload is None
                        or observed_payload == payment["invoice_payload"]
                    )
                )
                if payment and not exact_payment:
                    add_issue(
                        "provider_local_payment_mismatch",
                        observation,
                        telegram_user_id=int(payment["telegram_user_id"]),
                    )
                    continue
                if observation["direction"] == "incoming" and exact_payment:
                    confirmed_incoming_ids.add(str(observation["transaction_id"]))
                    self.conn.execute(
                        """UPDATE payments
                           SET provider_confirmed_at = COALESCE(provider_confirmed_at, ?)
                           WHERE telegram_payment_charge_id = ?""",
                        (timestamp, observation["transaction_id"]),
                    )
                    for reason in (
                        "local_payment_absent_from_provider_snapshot",
                        "provider_local_payment_mismatch",
                        "provider_payment_without_successful_update",
                        "provider_transaction_type_mismatch",
                        "provider_transaction_unknown_or_mismatched",
                        "unmatched_provider_invoice_payment",
                    ):
                        resolve_issue(reason, observation)
                    continue
                if observation["direction"] == "outgoing" and exact_payment:
                    for reason in (
                        "provider_local_payment_mismatch",
                        "provider_refund_without_payment_update",
                        "provider_transaction_type_mismatch",
                        "provider_transaction_unknown_or_mismatched",
                        "unmatched_provider_invoice_payment",
                    ):
                        resolve_issue(reason, observation)
                    if payment["provider_refund_confirmed_at"] is None:
                        refund_actions.append((observation, payment))
                    else:
                        subscription = self.conn.execute(
                            """SELECT cancellation_pending_at FROM subscriptions
                               WHERE initial_charge_id = ?""",
                            (payment["initial_charge_id"],),
                        ).fetchone()
                        if subscription and subscription["cancellation_pending_at"]:
                            add_issue(
                                "provider_refund_cancellation_unconfirmed",
                                observation,
                                severity="warning",
                                telegram_user_id=int(payment["telegram_user_id"]),
                            )
                    continue
                intent = (
                    self.conn.execute(
                        "SELECT * FROM invoice_intents WHERE payload = ?",
                        (observed_payload,),
                    ).fetchone()
                    if isinstance(observed_payload, str)
                    and observed_payload.startswith("sub:v1:")
                    else None
                )
                exact_intent = bool(
                    intent
                    and observed_user == intent["telegram_user_id"]
                    and observation["amount"] == intent["total_amount"]
                    and observation["nanostar_amount"] == 0
                    and observation["subscription_period"] in {None, 2_592_000}
                )
                reason = (
                    "provider_payment_without_successful_update"
                    if observation["direction"] == "incoming" and exact_intent
                    else "provider_refund_without_payment_update"
                    if observation["direction"] == "outgoing" and exact_intent
                    else "provider_transaction_unknown_or_mismatched"
                    if observed_payload is not None
                    else "unmatched_provider_invoice_payment"
                )
                add_issue(reason, observation, telegram_user_id=observed_user)
                if exact_intent and observed_user is not None:
                    self._open_star_support_case(observed_user, timestamp)
                    if (
                        observation["direction"] == "outgoing"
                        and intent["state"] in {"reserved", "paid"}
                    ):
                        try:
                            self._begin_payment_refund_in_transaction(
                                str(observation["transaction_id"]),
                                telegram_user_id=int(observed_user),
                                currency=str(intent["currency"]),
                                total_amount=int(intent["total_amount"]),
                                invoice_payload=str(intent["payload"]),
                                current=current,
                            )
                        except ValueError:
                            add_issue(
                                "provider_refund_local_apply_failed",
                                observation,
                                telegram_user_id=int(observed_user),
                            )

            for payment in self.conn.execute(
                """SELECT telegram_payment_charge_id, telegram_user_id FROM payments"""
            ).fetchall():
                if str(payment["telegram_payment_charge_id"]) not in confirmed_incoming_ids:
                    add_issue(
                        "local_payment_absent_from_provider_snapshot",
                        {
                            "transaction_id": str(payment["telegram_payment_charge_id"]),
                            "direction": "incoming",
                        },
                        severity="warning",
                        telegram_user_id=int(payment["telegram_user_id"]),
                    )

        refunds_applied = 0
        for observation, payment in refund_actions:
            try:
                self._begin_payment_refund_in_transaction(
                    str(observation["transaction_id"]),
                    telegram_user_id=int(payment["telegram_user_id"]),
                    currency=str(payment["currency"]),
                    total_amount=int(payment["total_amount"]),
                    invoice_payload=str(payment["invoice_payload"]),
                    current=current,
                )
            except ValueError:
                add_issue(
                    "provider_refund_local_apply_failed",
                    observation,
                    telegram_user_id=int(payment["telegram_user_id"]),
                )
                continue
            refunds_applied += 1
            with contextlib.nullcontext():
                self.conn.execute(
                    """UPDATE payments
                       SET provider_refund_confirmed_at =
                           COALESCE(provider_refund_confirmed_at, ?)
                       WHERE telegram_payment_charge_id = ?""",
                    (timestamp, observation["transaction_id"]),
                )
            add_issue(
                "provider_refund_cancellation_unconfirmed",
                observation,
                severity="warning",
                telegram_user_id=int(payment["telegram_user_id"]),
            )

        for row in self.conn.execute(
            """SELECT p.telegram_payment_charge_id, p.telegram_user_id,
                      s.cancellation_pending_at
               FROM payments p
               JOIN subscriptions s
                 ON s.initial_charge_id = p.initial_charge_id
               WHERE p.provider_refund_confirmed_at IS NOT NULL"""
        ).fetchall():
            observation = {
                "transaction_id": str(row["telegram_payment_charge_id"]),
                "direction": "outgoing",
            }
            if row["cancellation_pending_at"]:
                add_issue(
                    "provider_refund_cancellation_unconfirmed",
                    observation,
                    severity="warning",
                    telegram_user_id=int(row["telegram_user_id"]),
                )
            else:
                resolve_issue(
                    "provider_refund_cancellation_unconfirmed", observation
                )

        issue_values = [self._validated_star_issue(item) for item in generated.values()]
        open_keys = {str(item["issue_key"]) for item in issue_values}
        with contextlib.nullcontext():
            for issue in issue_values:
                self.conn.execute(
                    """INSERT INTO star_reconciliation_issues
                       (issue_key, severity, state, reason_code, transaction_id,
                        direction, telegram_user_id, first_seen_at, last_seen_at,
                        resolved_at, reconciliation_ref)
                       VALUES (?, ?, 'open', ?, ?, ?, ?, ?, ?, NULL, ?)
                       ON CONFLICT(issue_key) DO UPDATE SET
                         severity = excluded.severity,
                         state = 'open',
                         last_seen_at = excluded.last_seen_at,
                         resolved_at = NULL,
                         reconciliation_ref = excluded.reconciliation_ref""",
                    (
                        issue["issue_key"],
                        issue["severity"],
                        issue["reason_code"],
                        issue["transaction_id"],
                        issue["direction"],
                        issue["telegram_user_id"],
                        timestamp,
                        timestamp,
                        run,
                    ),
                )
            for issue_key in sorted(resolved_issue_keys - open_keys):
                self.conn.execute(
                    """UPDATE star_reconciliation_issues
                       SET state = 'resolved', resolved_at = ?
                       WHERE issue_key = ? AND state = 'open'""",
                    (timestamp, issue_key),
                )
            cursor = self.conn.execute(
                """UPDATE star_scan_runs
                   SET state = 'complete', completed_at = ?, pass_count = 2,
                       transaction_count = ?, terminal_offset = ?,
                       snapshot_digest = ?, issue_count = ?, error_code = NULL
                   WHERE run_id = ? AND state = 'running'""",
                (
                    timestamp,
                    len(unique),
                    terminal_offset,
                    snapshot_digest,
                    len(issue_values),
                    run,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("Star scan run is not open")
        open_counts = {
            str(row["severity"]): int(row["count"])
            for row in self.conn.execute(
                """SELECT severity, COUNT(*) AS count
                   FROM star_reconciliation_issues WHERE state = 'open'
                   GROUP BY severity"""
            ).fetchall()
        }
        critical = open_counts.get("critical", 0)
        warnings = open_counts.get("warning", 0)
        return {
            "run_id": run,
            "clean": critical == 0 and warnings == 0,
            "complete": True,
            "transactions": len(unique),
            "issues": critical + warnings,
            "critical_issues": critical,
            "warnings": warnings,
            "refunds_applied": refunds_applied,
            "commerce_ready": False,
        }

    def star_reconciliation_status(self) -> dict[str, Any]:
        binding = {
            str(row["key"]): str(row["value"])
            for row in self.conn.execute(
                """SELECT key, value FROM bot_state
                   WHERE key IN ('telegram_provider_bot_id',
                                 'telegram_provider_api_origin')"""
            ).fetchall()
        }
        latest = self.conn.execute(
            """SELECT run_id, started_at, completed_at, state, pass_count,
                      transaction_count, issue_count, error_code
               FROM star_scan_runs ORDER BY julianday(started_at) DESC LIMIT 1"""
        ).fetchone()
        open_counts = {
            str(row["severity"]): int(row["count"])
            for row in self.conn.execute(
                """SELECT severity, COUNT(*) AS count
                   FROM star_reconciliation_issues WHERE state = 'open'
                   GROUP BY severity"""
            ).fetchall()
        }
        return {
            "provider_bound": len(binding) == 2,
            "api_origin": binding.get("telegram_provider_api_origin"),
            "latest_run": dict(latest) if latest else None,
            "open_critical_issues": open_counts.get("critical", 0),
            "open_warnings": open_counts.get("warning", 0),
            "commerce_ready": False,
            "readiness_reason": "production commerce remains explicitly disabled",
        }

    def unresolved_star_issues(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT issue_key, severity, reason_code, direction,
                      first_seen_at, last_seen_at, reconciliation_ref
               FROM star_reconciliation_issues
               WHERE state = 'open'
               ORDER BY CASE severity WHEN 'critical' THEN 0 ELSE 1 END,
                        first_seen_at, issue_key"""
        ).fetchall()
        return [dict(row) for row in rows]

    def get_offset(self) -> int:
        row = self.conn.execute(
            "SELECT value FROM bot_state WHERE key = 'telegram_update_offset'"
        ).fetchone()
        if not row:
            return 0
        value = int(row["value"])
        if not 0 <= value <= MAX_TELEGRAM_UPDATE_ID + 1:
            raise ValueError("stored Telegram update offset is invalid")
        return value

    @_atomic_store_method
    def prepare_update_poll(self, *, now: datetime | None = None) -> int:
        """Reset the long-poll cursor before Telegram may randomize update IDs.

        Telegram can choose a random next update ID after a week without new
        updates. At six days of locally observed idle time, start a fresh
        fetch-cursor epoch at zero. Lifetime replay evidence remains intact:
        randomness changes ordering, while Telegram still defines each
        update ID as the update's unique identifier.
        """

        current = now or utc_now()
        current_timestamp = iso_utc(current)
        last_row = self.conn.execute(
            "SELECT value FROM bot_state WHERE key = 'telegram_last_update_received_at'"
        ).fetchone()
        reset_row = self.conn.execute(
            "SELECT value FROM bot_state WHERE key = 'telegram_update_epoch_reset_at'"
        ).fetchone()
        seen_row = self.conn.execute(
            "SELECT value FROM bot_state WHERE key = 'telegram_update_seen_since_reset'"
        ).fetchone()
        last_received = parse_utc(str(last_row["value"])) if last_row else None
        reset_at = parse_utc(str(reset_row["value"])) if reset_row else None
        if seen_row:
            if str(seen_row["value"]) not in {"0", "1"}:
                raise ValueError("stored Telegram cursor reset state is invalid")
            seen_since_reset = str(seen_row["value"]) == "1"
        else:
            # Conservative migration for a database written during the local
            # cursor-reset prototype. A strictly later receipt proves re-arm;
            # equality remains unarmed until the next observed update.
            seen_since_reset = (
                reset_at is None
                or (
                    last_received is not None
                    and last_received > reset_at
                )
            )
        idle = (
            last_received is None
            or current.astimezone(timezone.utc) - last_received
            >= TELEGRAM_UPDATE_EPOCH_RESET_AFTER
        )
        reset_needed = idle and (reset_at is None or seen_since_reset)
        if reset_needed:
            self.conn.execute(
                """INSERT INTO bot_state(key, value)
                   VALUES ('telegram_update_offset', '0')
                   ON CONFLICT(key) DO UPDATE SET value = '0'"""
            )
            self.conn.execute(
                """INSERT INTO bot_state(key, value)
                   VALUES ('telegram_update_epoch_reset_at', ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (current_timestamp,),
            )
            self.conn.execute(
                """INSERT INTO bot_state(key, value)
                   VALUES ('telegram_update_seen_since_reset', '0')
                   ON CONFLICT(key) DO UPDATE SET value = '0'"""
            )
            return 0
        row = self.conn.execute(
            "SELECT value FROM bot_state WHERE key = 'telegram_update_offset'"
        ).fetchone()
        if not row:
            return 0
        value = int(row["value"])
        if not 0 <= value <= MAX_TELEGRAM_UPDATE_ID + 1:
            raise ValueError("stored Telegram update offset is invalid")
        return value

    def set_offset(self, offset: int) -> None:
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 <= offset <= MAX_TELEGRAM_UPDATE_ID + 1
        ):
            raise ValueError("Telegram update offset is invalid")
        self.conn.execute(
            """INSERT INTO bot_state(key, value)
               VALUES ('telegram_update_offset', ?)
               ON CONFLICT(key) DO UPDATE SET value =
                 CAST(MAX(CAST(bot_state.value AS INTEGER),
                          CAST(excluded.value AS INTEGER)) AS TEXT)""",
            (str(int(offset)),),
        )
        self.conn.commit()

    def get_state(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM bot_state WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row else None

    def set_state(self, key: str, value: str) -> None:
        self.conn.execute(
            """INSERT INTO bot_state(key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        self.conn.commit()

    def is_update_processed(self, update_id: int) -> bool:
        if (
            isinstance(update_id, bool)
            or not isinstance(update_id, int)
            or not 0 <= update_id <= MAX_TELEGRAM_UPDATE_ID
        ):
            return False
        row = self.conn.execute(
            "SELECT 1 FROM processed_updates WHERE update_id = ?", (int(update_id),)
        ).fetchone()
        return row is not None

    def mark_update_processed(self, update_id: int, *, now: datetime | None = None) -> None:
        if (
            isinstance(update_id, bool)
            or not isinstance(update_id, int)
            or not 0 <= update_id <= MAX_TELEGRAM_UPDATE_ID
        ):
            raise ValueError("Telegram update ID is invalid")
        timestamp = iso_utc(now or utc_now())
        with self.conn:
            self.conn.execute(
                """INSERT OR IGNORE INTO processed_updates(update_id, processed_at)
                   VALUES (?, ?)""",
                (int(update_id), timestamp),
            )
            self.conn.execute(
                """INSERT INTO bot_state(key, value)
                   VALUES ('telegram_update_offset', ?)
                   ON CONFLICT(key) DO UPDATE SET value =
                     CAST(MAX(CAST(bot_state.value AS INTEGER),
                              CAST(excluded.value AS INTEGER)) AS TEXT)""",
                (str(int(update_id) + 1),),
            )
            self.conn.execute(
                """INSERT INTO bot_state(key, value)
                   VALUES ('telegram_last_update_received_at', ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (timestamp,),
            )
            self.conn.execute(
                """INSERT INTO bot_state(key, value)
                   VALUES ('telegram_update_seen_since_reset', '1')
                   ON CONFLICT(key) DO UPDATE SET value = '1'"""
            )

    def mark_update_failed(
        self,
        update_id: int,
        *,
        error_code: str,
        ambiguous: bool,
        now: datetime | None = None,
    ) -> None:
        if (
            isinstance(update_id, bool)
            or not isinstance(update_id, int)
            or not 0 <= update_id <= MAX_TELEGRAM_UPDATE_ID
        ):
            raise ValueError("Telegram update ID is invalid")
        timestamp = iso_utc(now or utc_now())
        code = re.sub(r"[^A-Za-z0-9_.-]", "_", error_code)[:80] or "unknown"
        with self.conn:
            self.conn.execute(
                """INSERT INTO failed_updates(update_id, error_code, ambiguous, failed_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(update_id) DO UPDATE SET
                     error_code = excluded.error_code,
                     ambiguous = excluded.ambiguous,
                     failed_at = excluded.failed_at""",
                (int(update_id), code, int(ambiguous), timestamp),
            )
            self.conn.execute(
                """INSERT INTO processed_updates(update_id, processed_at)
                   VALUES (?, ?) ON CONFLICT(update_id) DO NOTHING""",
                (int(update_id), timestamp),
            )
            self.conn.execute(
                """INSERT INTO bot_state(key, value)
                   VALUES ('telegram_update_offset', ?)
                   ON CONFLICT(key) DO UPDATE SET value =
                     CAST(MAX(CAST(bot_state.value AS INTEGER),
                              CAST(excluded.value AS INTEGER)) AS TEXT)""",
                (str(int(update_id) + 1),),
            )
            self.conn.execute(
                """INSERT INTO bot_state(key, value)
                   VALUES ('telegram_last_update_received_at', ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (timestamp,),
            )
            self.conn.execute(
                """INSERT INTO bot_state(key, value)
                   VALUES ('telegram_update_seen_since_reset', '1')
                   ON CONFLICT(key) DO UPDATE SET value = '1'"""
            )

    def counts(
        self,
        *,
        now: datetime | None = None,
        promotion_notice_version: str = DEFAULT_PROMOTION_NOTICE_VERSION,
    ) -> dict[str, int]:
        timestamp = iso_utc(now or utc_now())
        values: dict[str, int] = {}
        values["signals"] = self.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        values["recipients"] = self.conn.execute("SELECT COUNT(*) FROM recipients").fetchone()[0]
        values["active_research"] = self.conn.execute(
            """SELECT COUNT(*) FROM recipients
               WHERE tier = 'research'
                 AND julianday(entitlement_expires_at) > julianday(?)""",
            (timestamp,),
        ).fetchone()[0]
        values["payments"] = self.conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
        values["reservation_conflicts"] = self.reservation_conflicts
        values["open_subscriptions"] = self.conn.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE revoked_at IS NULL"
        ).fetchone()[0]
        values["paper_actions"] = self.conn.execute("SELECT COUNT(*) FROM paper_actions").fetchone()[0]
        values["sent"] = self.conn.execute(
            "SELECT COUNT(*) FROM delivery_receipts WHERE status = 'sent'"
        ).fetchone()[0]
        values["failed_updates"] = self.conn.execute(
            "SELECT COUNT(*) FROM failed_updates"
        ).fetchone()[0]
        values["contact_suppressions"] = self.conn.execute(
            "SELECT COUNT(*) FROM contact_suppressions"
        ).fetchone()[0]
        values.update(self.promotion_summary(promotion_notice_version))
        return values

    def close(self) -> None:
        self.conn.close()
        self._secure_sqlite_files()

    def __enter__(self) -> "GatewayStore":
        return self

    def __exit__(self, *_: Iterable[Any]) -> None:
        self.close()
