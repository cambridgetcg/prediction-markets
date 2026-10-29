"""Transport-neutral Telegram update handling and subscriber fan-out."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol

from .calibration import CalibrationError, CalibrationLedger
from .formatting import (
    render_privacy,
    render_public_signal,
    render_research_signal,
    render_signal_correction,
    render_terms,
)
from .policy import Action, PolicyEngine
from .preferences import PreferenceLimitError, PreferenceSnapshot, PreferenceStore
from .promotion import (
    DEFAULT_PROMOTION_NOTICE_VERSION,
    validate_campaign_code,
    validate_notice_version,
)
from .store import GatewayStore
from .telegram_api import TelegramError


class TelegramTransport(Protocol):
    def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: Mapping[str, Any] | None = None,
        protect_content: bool = False,
    ) -> Mapping[str, Any]: ...

    def create_subscription_link(self, *, payload: str, stars_amount: int) -> str: ...
    def answer_callback(self, callback_query_id: str, text: str = "") -> bool: ...
    def answer_pre_checkout(
        self, pre_checkout_query_id: str, *, ok: bool, error_message: str | None = None
    ) -> bool: ...
    def edit_subscription(
        self, *, user_id: int, initial_charge_id: str, canceled: bool
    ) -> bool: ...
    def get_updates(self, *, offset: int, timeout: int) -> list[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class ServiceConfig:
    stars_amount: int = 0
    enable_stars_commerce: bool = False
    terms_version: str = "2026-09-02-v1"
    support_contact: str = "Reply to the operator who provided access to this bot."
    plan_code: str = "research"
    poll_timeout_seconds: int = 45
    promotion_notice_version: str = DEFAULT_PROMOTION_NOTICE_VERSION

    def __post_init__(self) -> None:
        if not 0 <= self.stars_amount <= 10_000:
            raise ValueError("stars_amount must be between 0 and 10000")
        if not isinstance(self.enable_stars_commerce, bool):
            raise ValueError("enable_stars_commerce must be a boolean")
        if not self.terms_version.strip():
            raise ValueError("terms_version is required")
        validate_notice_version(self.promotion_notice_version)
        if not 1 <= self.poll_timeout_seconds <= 50:
            raise ValueError("poll_timeout_seconds must be between 1 and 50")

    @property
    def commerce_enabled(self) -> bool:
        # A configured price is commercial data, not authority to transact.
        # Library embeddings must cross a separate, deliberate activation
        # gate; the bundled CLI never sets it.
        return self.enable_stars_commerce and self.stars_amount > 0


WELCOME = """KINGDOM market research

Evidence-labelled forecasts and simulated paper tools delivered through Telegram.
This bot has no wallet or order signer and cannot place a live trade.
It stores numeric Telegram IDs plus minimal access, preference, payment, delivery, and paper records; use /privacy for detail.

Commands:
/join — opt in to at most two approved alerts per rolling seven days
/leave or /stop — stop new alerts; on-demand commands still work
/brief or /latest — newest active research signal
/personalize — enable a minimal topic, cadence, and watchlist profile
/topics [CODES|all] — view or replace topic filters
/cadence [realtime|daily|weekly] — view or set delivery cadence
/watch MARKET_REF — add an opaque market reference to your watchlist
/unwatch MARKET_REF — remove a market reference
/watchlist — show your saved market references
/scorecard [DOMAIN] — paper forecast calibration, never a return claim
/paper SIGNAL_ID [USD] — record a simulation only
/plans — subscription details
/subscribe — review terms and subscribe
/settings or /status — access and execution status
/cancel — stop subscription renewal
/terms — product and risk terms
/privacy — local data summary
/paysupport — payment support
/delete_me — purge linkable research data and retain a no-contact marker
/help — show this message"""

PROMOTION_JOIN_CALLBACK_PREFIX = "promo_join:"


class BotService:
    def __init__(
        self,
        store: GatewayStore,
        transport: TelegramTransport,
        config: ServiceConfig | None = None,
        policy: PolicyEngine | None = None,
        preferences: PreferenceStore | None = None,
        calibration: CalibrationLedger | None = None,
    ):
        self.store = store
        self.transport = transport
        self.config = config or ServiceConfig()
        self.policy = policy or PolicyEngine()
        self.preferences = preferences
        self.calibration = calibration

    def handle_update(self, update: Mapping[str, Any]) -> bool:
        """Process one Telegram update.

        Effects are idempotent where Telegram exposes stable IDs.  A response
        message can still be duplicated if Telegram accepted it immediately
        before the process lost connectivity; the API has no caller-provided
        idempotency key for ``sendMessage``.
        """

        update_id = _telegram_update_id(update.get("update_id"))
        if update_id is None:
            return False
        # The polling offset is a fetch cursor, not an event-order verdict. A
        # future serialized webhook adapter may legitimately hand us an older
        # update after a newer one, so deduplicate by the update ledger only.
        if self.store.is_update_processed(update_id):
            return False

        if isinstance(update.get("message"), Mapping):
            self._handle_message(update["message"], update_id)
        elif isinstance(update.get("callback_query"), Mapping):
            self._handle_callback(update["callback_query"], update_id)
        elif isinstance(update.get("pre_checkout_query"), Mapping):
            self._handle_pre_checkout(update["pre_checkout_query"])
        elif isinstance(update.get("subscription"), Mapping):
            self._handle_subscription_update(update["subscription"], update_id)
        elif isinstance(update.get("my_chat_member"), Mapping):
            self._handle_membership(update["my_chat_member"], update_id)

        self.store.mark_update_processed(update_id)
        return True

    def _handle_message(self, message: Mapping[str, Any], update_id: int) -> None:
        chat = message.get("chat") if isinstance(message.get("chat"), Mapping) else {}
        sender = message.get("from") if isinstance(message.get("from"), Mapping) else {}
        chat_id = _integer(chat.get("id"))
        user_id = _integer(sender.get("id"))
        if chat_id is None or user_id is None:
            return
        # This MVP serves human-owned private chats. Telegram's optional
        # Bot-to-Bot Communication Mode can otherwise make an automated sender
        # look like a valid private peer and create reply loops.
        if sender.get("is_bot") is True:
            return
        if chat.get("type") != "private":
            # This deployment is private-chat only. Privacy Mode still permits
            # some group service messages and addressed commands, and a reused
            # bot can remain in an old group after future joins are disabled.
            # Silently ignore those updates rather than creating group contact.
            return
        if user_id <= 0 or chat_id != user_id:
            return

        if isinstance(message.get("successful_payment"), Mapping):
            self.store.register_recipient(user_id, chat_id)
            self._handle_successful_payment(
                message["successful_payment"], user_id, chat_id, update_id
            )
            return
        if isinstance(message.get("refunded_payment"), Mapping):
            self.store.register_recipient(user_id, chat_id)
            self._handle_refunded_payment(
                message["refunded_payment"], user_id, chat_id, update_id
            )
            return

        text = _string(message.get("text"), 4_096).strip()
        command = ""
        args: list[str] = []
        if text.startswith("/"):
            command, *args = text.split()
            command = command.split("@", 1)[0].lower()
        event_at = _telegram_message_time(message.get("date"))

        # Consent withdrawal and deletion must remain available even when a
        # sender has exhausted the ordinary command rate limit.
        if command in {"/leave", "/stop", "/unsubscribe"}:
            alert_state = self.store.research_alert_status(
                user_id,
                self.config.promotion_notice_version,
            )["state"]
            if alert_state == "not_joined":
                self.store.record_contact_suppression(
                    user_id,
                    telegram_update_id=update_id,
                    reason="withdrawn",
                    event_at=event_at,
                )
                preference_note = self._withdraw_preferences(
                    user_id,
                    update_id,
                    event_at=event_at,
                )
                self.transport.send_text(
                    chat_id,
                    "Research alerts are off. A minimal numeric ID and event watermark "
                    "are retained so delayed Telegram updates cannot turn them back on."
                    + preference_note,
                )
                return
            changed = self.store.set_research_alert_consent(
                user_id,
                subscribed=False,
                telegram_update_id=update_id,
                notice_version=self.config.promotion_notice_version,
                event_at=event_at,
            )
            preference_note = self._withdraw_preferences(
                user_id,
                update_id,
                event_at=event_at,
            )
            self.transport.send_text(
                chat_id,
                ("Research alerts are now off. " if changed else "Research alerts were already off. ")
                + "No proactive research or corrections will be sent unless you "
                "explicitly /join again."
                + preference_note,
            )
            return
        if command == "/delete_me":
            preference_note = self._delete_preferences(
                user_id,
                update_id,
                event_at=event_at,
            )
            self._delete_recipient_data(
                user_id,
                chat_id,
                update_id=update_id,
                event_at=event_at,
                preference_note=preference_note,
            )
            return

        # A minimal stop/delete marker is also an event-order barrier. Ignore
        # delayed pre-withdrawal messages before they recreate a recipient or
        # cause a reply. A genuinely newer user message can restart a clean
        # interaction, but deleted research stays unavailable until a join.
        if not self.store.contact_action_is_newer(
            user_id,
            update_id,
            event_at=event_at,
        ):
            return
        suppression = self.store.contact_suppression_status(user_id)
        if suppression and suppression["reason"] == "deleted" and command in {
            "/brief",
            "/latest",
            "/paper",
            "/plans",
            "/subscribe",
        }:
            self.transport.send_text(
                chat_id,
                "Your prior local research data was deleted and research remains "
                "disabled. Send /join to give a newer explicit alert preference first.",
            )
            return

        if not self.store.allow_interactive_request(user_id):
            return
        self.store.register_recipient(user_id, chat_id)
        if not command:
            self.transport.send_text(chat_id, "Use /help to see the available research commands.")
            return

        if command == "/start":
            promotion_markup = None
            promotion_disclosure = ""
            if len(args) == 1:
                try:
                    campaign_code = validate_campaign_code(args[0])
                    if self.store.record_promotion_campaign_start(
                        campaign_code,
                        now=event_at,
                    ):
                        promotion_disclosure = (
                            "\n\nCampaign measurement: this visit added one daily "
                            "aggregate count without linking the campaign to your "
                            "account. If you choose the button below, KINGDOM will "
                            "store this opaque source code with your numeric Telegram "
                            "ID under alert notice "
                            f"{self.config.promotion_notice_version}. Alerts are capped "
                            "at two per rolling seven days; /leave stops them and "
                            "/delete_me erases linkable non-financial activity while "
                            "retaining a minimal no-contact marker."
                        )
                        promotion_markup = {
                            "inline_keyboard": [[
                                {
                                    "text": "Enable free alerts from this source",
                                    "callback_data": self._promotion_join_callback_data(
                                        campaign_code
                                    ),
                                }
                            ]]
                        }
                except ValueError:
                    # Start payloads are untrusted public input. Invalid and
                    # unknown codes are neither echoed nor persisted.
                    pass
            self.transport.send_text(
                chat_id,
                WELCOME + promotion_disclosure,
                reply_markup=promotion_markup,
            )
            self.store.mark_privacy_notice(user_id)
        elif command == "/help":
            self.transport.send_text(chat_id, WELCOME)
            self.store.mark_privacy_notice(user_id)
        elif command == "/join":
            changed = self.store.set_research_alert_consent(
                user_id,
                subscribed=True,
                telegram_update_id=update_id,
                notice_version=self.config.promotion_notice_version,
                event_at=event_at,
            )
            alert_state = self.store.research_alert_status(
                user_id, self.config.promotion_notice_version
            )["state"]
            if alert_state == "subscribed":
                prefix = (
                    "Research alerts are now on. "
                    if changed
                    else "Research alerts were already on. "
                )
                self.transport.send_text(
                    chat_id,
                    prefix
                    + "You may receive at most two approved previews per rolling seven "
                    "days. Use /leave or /stop at any time. No trade will be placed. "
                    "Use /personalize separately if you want topic, cadence, or "
                    "watchlist filtering.",
                )
            else:
                self.transport.send_text(
                    chat_id,
                    "This older join did not replace your later alert preference. "
                    "Send /join again if you want to turn alerts on.",
                )
        elif command in {"/brief", "/latest"}:
            self._send_latest(user_id, chat_id)
        elif command == "/personalize":
            self._enable_personalization(
                user_id,
                chat_id,
                update_id,
                event_at=event_at,
            )
        elif command == "/topics":
            self._handle_topics(
                user_id,
                chat_id,
                args,
                update_id,
                event_at=event_at,
            )
        elif command == "/cadence":
            self._handle_cadence(
                user_id,
                chat_id,
                args,
                update_id,
                event_at=event_at,
            )
        elif command == "/watch":
            self._handle_watchlist_change(
                user_id,
                chat_id,
                args,
                update_id,
                remove=False,
                event_at=event_at,
            )
        elif command == "/unwatch":
            self._handle_watchlist_change(
                user_id,
                chat_id,
                args,
                update_id,
                remove=True,
                event_at=event_at,
            )
        elif command == "/watchlist":
            self._show_watchlist(user_id, chat_id)
        elif command == "/scorecard":
            self._show_scorecard(chat_id, args)
        elif command == "/paper":
            self._record_paper(user_id, chat_id, args, update_id)
        elif command in {"/plans", "/subscribe"}:
            self._show_plan(chat_id, include_terms_button=command == "/subscribe")
        elif command in {"/settings", "/status"}:
            self._send_status(user_id, chat_id)
        elif command == "/cancel":
            self._cancel_subscription(user_id, chat_id, update_id)
        elif command == "/terms":
            self.transport.send_text(chat_id, render_terms(self.config.terms_version))
        elif command == "/privacy":
            self.transport.send_text(chat_id, render_privacy())
            self.store.mark_privacy_notice(user_id)
        elif command in {"/paysupport", "/support"}:
            case_id = self.store.open_support_case(user_id)
            self.transport.send_text(
                chat_id,
                f"Payment support case: {case_id}\n{self.config.support_contact}\n"
                "KINGDOM, not Telegram, is responsible for resolving this purchase issue.",
            )
        elif command in {"/trade", "/execute", "/buy", "/sell"}:
            decision = self.policy.decide(Action.PLACE_LIVE_ORDER)
            self.transport.send_text(chat_id, f"{decision.code}: {decision.explanation}")
        else:
            self.transport.send_text(chat_id, "Unknown command. Use /help.")

    def _withdraw_preferences(
        self,
        user_id: int,
        update_id: int,
        *,
        event_at: datetime | None,
    ) -> str:
        if self.preferences is None:
            return ""
        try:
            result = self.preferences.withdraw_consent(
                user_id,
                update_id,
                event_at=event_at,
            )
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return (
                " Personalization cleanup could not be confirmed; send /delete_me "
                "or contact /support."
            )
        if not result.accepted:
            return (
                " A later personalization choice was retained; send /leave again "
                "if you still want that profile erased."
            )
        if result.removed_records:
            return " Topic, cadence, and watchlist preferences were erased."
        return ""

    def _delete_preferences(
        self,
        user_id: int,
        update_id: int,
        *,
        event_at: datetime | None,
    ) -> str:
        if self.preferences is None:
            return ""
        try:
            result = self.preferences.delete_user(
                user_id,
                update_id,
                event_at=event_at,
            )
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return (
                "Personalization-store deletion could not be confirmed; repeat "
                "/delete_me or contact /support. "
            )
        if not result.accepted:
            return (
                "A later personalization choice was retained; send /delete_me "
                "again if you still want it erased. "
            )
        return (
            "Topic, cadence, and watchlist data were deleted or already absent; "
            "a minimal personalization no-contact watermark remains. "
        )

    def _enable_personalization(
        self,
        user_id: int,
        chat_id: int,
        update_id: int,
        *,
        event_at: datetime | None,
    ) -> None:
        if self.preferences is None:
            self.transport.send_text(
                chat_id, "Personalization is unavailable in this runtime."
            )
            return
        try:
            result = self.preferences.grant_consent(
                user_id,
                chat_id,
                update_id,
                event_at=event_at,
            )
        except (OSError, sqlite3.Error, TypeError, ValueError):
            self.transport.send_text(
                chat_id,
                "Personalization could not be saved locally. Nothing was enabled; "
                "try again or use /support.",
            )
            return
        if not result.accepted:
            self.transport.send_text(
                chat_id,
                "That older action did not replace your later privacy preference. "
                "Send /personalize again if you want to enable a profile.",
            )
            return
        snapshot = self._preference_snapshot(user_id)
        if snapshot is None:
            self.transport.send_text(
                chat_id,
                "Personalization was saved, but its local readback could not be "
                "confirmed. Use /status before relying on it.",
            )
            return
        self.transport.send_text(
            chat_id,
            "Personalization is enabled under notice "
            f"{snapshot.notice_version}. Stored fields are limited to your numeric "
            "Telegram ID, allowlisted topic codes, cadence, and opaque market "
            "references. Empty topic selection means all supported topics. "
            f"Current cadence: {snapshot.cadence}. Use /leave to erase the profile "
            "or /delete_me for the broader local deletion flow.",
        )

    @staticmethod
    def _preference_rejection(reason: str) -> str:
        if reason == "notice_reconfirmation_required":
            return "The personalization notice changed. Send /personalize to reconfirm first."
        if reason == "consent_required":
            return "Send /personalize first to create a minimal preference profile."
        return "That older action did not replace your later preference. Send it again if still wanted."

    def _preference_snapshot(
        self, telegram_user_id: int
    ) -> PreferenceSnapshot | None:
        if self.preferences is None:
            return None
        try:
            return self.preferences.snapshot(telegram_user_id)
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return None

    def _handle_topics(
        self,
        user_id: int,
        chat_id: int,
        args: list[str],
        update_id: int,
        *,
        event_at: datetime | None,
    ) -> None:
        if self.preferences is None:
            self.transport.send_text(
                chat_id, "Topic preferences are unavailable in this runtime."
            )
            return
        available = ", ".join(self.preferences.available_topics())
        if not args:
            snapshot = self._preference_snapshot(user_id)
            if snapshot is None:
                self.transport.send_text(
                    chat_id, "Topic preferences could not be read locally."
                )
                return
            selected = ", ".join(snapshot.topics) if snapshot.topics else "all"
            self.transport.send_text(
                chat_id,
                f"Topic filter: {selected}\nAvailable: {available}\n"
                "Use /topics all or /topics CODE [CODE...]. "
                "Send /personalize first if the profile is not active.",
            )
            return
        selected = [
            value.strip().lower()
            for argument in args
            for value in argument.split(",")
            if value.strip()
        ]
        if selected == ["all"]:
            selected = []
        elif "all" in selected:
            self.transport.send_text(chat_id, "Use 'all' by itself, or list topic codes.")
            return
        try:
            result = self.preferences.replace_topics(
                user_id,
                selected,
                update_id,
                event_at=event_at,
            )
        except (PreferenceLimitError, ValueError) as exc:
            self.transport.send_text(chat_id, f"Topic preference rejected: {exc}")
            return
        except (OSError, sqlite3.Error):
            self.transport.send_text(
                chat_id, "Topic preferences could not be saved locally."
            )
            return
        if not result.accepted:
            self.transport.send_text(
                chat_id, self._preference_rejection(result.reason)
            )
            return
        rendered = ", ".join(selected) if selected else "all supported topics"
        self.transport.send_text(
            chat_id,
            f"Topic filter saved: {rendered}. This filters ordinary previews; "
            "owed corrections remain safety messages.",
        )

    def _handle_cadence(
        self,
        user_id: int,
        chat_id: int,
        args: list[str],
        update_id: int,
        *,
        event_at: datetime | None,
    ) -> None:
        if self.preferences is None:
            self.transport.send_text(
                chat_id, "Cadence preferences are unavailable in this runtime."
            )
            return
        if not args:
            snapshot = self._preference_snapshot(user_id)
            if snapshot is None:
                self.transport.send_text(
                    chat_id, "Cadence preferences could not be read locally."
                )
                return
            self.transport.send_text(
                chat_id,
                f"Cadence: {snapshot.cadence or 'not configured'}\n"
                "Choices: realtime, daily, weekly. The global safety cap of two "
                "ordinary previews per rolling seven days always remains in force.",
            )
            return
        if len(args) != 1:
            self.transport.send_text(
                chat_id, "Usage: /cadence realtime|daily|weekly"
            )
            return
        try:
            result = self.preferences.set_cadence(
                user_id,
                args[0].lower(),
                update_id,
                event_at=event_at,
            )
        except ValueError as exc:
            self.transport.send_text(chat_id, f"Cadence rejected: {exc}")
            return
        except (OSError, sqlite3.Error):
            self.transport.send_text(
                chat_id, "Cadence could not be saved locally."
            )
            return
        if not result.accepted:
            self.transport.send_text(
                chat_id, self._preference_rejection(result.reason)
            )
            return
        self.transport.send_text(
            chat_id,
            f"Cadence saved: {args[0].lower()}. It is a maximum-frequency "
            "preference, not a delivery promise; corrections may arrive sooner.",
        )

    def _handle_watchlist_change(
        self,
        user_id: int,
        chat_id: int,
        args: list[str],
        update_id: int,
        *,
        remove: bool,
        event_at: datetime | None,
    ) -> None:
        if self.preferences is None:
            self.transport.send_text(
                chat_id, "Watchlists are unavailable in this runtime."
            )
            return
        command = "/unwatch" if remove else "/watch"
        if len(args) != 1:
            self.transport.send_text(chat_id, f"Usage: {command} MARKET_REF")
            return
        try:
            operation = self.preferences.unwatch if remove else self.preferences.watch
            result = operation(
                user_id,
                args[0],
                update_id,
                event_at=event_at,
            )
        except (PreferenceLimitError, ValueError) as exc:
            self.transport.send_text(chat_id, f"Watchlist change rejected: {exc}")
            return
        except (OSError, sqlite3.Error):
            self.transport.send_text(
                chat_id, "The watchlist change could not be saved locally."
            )
            return
        if not result.accepted:
            self.transport.send_text(
                chat_id, self._preference_rejection(result.reason)
            )
            return
        if remove:
            verb = "removed" if result.changed else "was not present"
        else:
            verb = "added" if result.changed else "was already saved"
        self.transport.send_text(
            chat_id,
            f"Market reference {verb}: {args[0]}. No market or wallet was contacted.",
        )

    def _show_watchlist(self, user_id: int, chat_id: int) -> None:
        if self.preferences is None:
            self.transport.send_text(
                chat_id, "Watchlists are unavailable in this runtime."
            )
            return
        snapshot = self._preference_snapshot(user_id)
        if snapshot is None:
            self.transport.send_text(
                chat_id, "Your watchlist could not be read locally."
            )
            return
        if not snapshot.active:
            self.transport.send_text(
                chat_id, "No active preference profile. Send /personalize first."
            )
            return
        if not snapshot.watchlist:
            self.transport.send_text(
                chat_id, "Your watchlist is empty. Use /watch MARKET_REF."
            )
            return
        self.transport.send_text(
            chat_id,
            "Saved opaque market references:\n- " + "\n- ".join(snapshot.watchlist),
        )

    def _show_scorecard(self, chat_id: int, args: list[str]) -> None:
        if self.calibration is None:
            self.transport.send_text(
                chat_id, "No paper calibration ledger is configured in this runtime."
            )
            return
        if len(args) > 1:
            self.transport.send_text(chat_id, "Usage: /scorecard [DOMAIN]")
            return
        try:
            card = self.calibration.scorecard(domain=args[0] if args else None)
        except (CalibrationError, OSError):
            self.transport.send_text(
                chat_id,
                "The paper scorecard is unavailable because its complete local "
                "integrity check did not pass.",
            )
            return
        counts = card["counts"]
        agent = card["agent"]
        baseline = card["market_baseline"]
        comparison = card["comparison"]

        def metric(value: Any) -> str:
            return "unavailable" if value is None else f"{float(value):.4f}"

        domain = card["filter"]["domain"] or "ALL"
        self.transport.send_text(
            chat_id,
            "KINGDOM paper calibration\n"
            f"Domain: {domain}\n"
            f"Registered: {counts['registered_forecasts']}\n"
            f"Resolved: {counts['resolved_forecasts']}\n"
            f"Unresolved: {counts['unresolved_forecasts']}\n"
            f"Agent mean Brier: {metric(agent['brier_mean'])}\n"
            f"Market mean Brier: {metric(baseline['brier_mean'])}\n"
            "Mean Brier advantage vs market: "
            f"{metric(comparison['mean_brier_advantage_vs_market'])}\n\n"
            "Lower Brier is better; positive advantage means the registered "
            "paper forecast scored better than its captured market baseline. "
            "Historical paper scores do not promise returns or authorize a trade.",
        )

    def _delete_recipient_data(
        self,
        user_id: int,
        chat_id: int,
        *,
        update_id: int,
        event_at: datetime | None,
        preference_note: str = "",
    ) -> None:
        purged = self.store.purge_nonfinancial_recipient_state(
            user_id,
            deletion_update_id=update_id,
            event_at=event_at,
        )
        nonfinancial_cleared = bool(sum(purged.values()))
        cleared_prefix = (
            "Non-financial campaign, consent, delivery, correction, paper, and "
            "closed-support records were deleted. "
            if nonfinancial_cleared
            else "No linkable non-financial activity was stored. "
        )
        cleared_prefix += preference_note
        cleared_prefix += (
            "A minimal numeric Telegram ID and no-contact event watermark remain "
            "so delayed updates cannot recreate consent. "
        )
        deletion_block = self.store.recipient_deletion_block(user_id)
        if deletion_block == "invoice_pending":
            self.transport.send_text(
                chat_id,
                cleared_prefix
                + "An invoice is still open. Wait up to 15 minutes for it to expire, "
                "then use /delete_me again.",
            )
            return
        if deletion_block == "checkout_reconciliation_pending":
            self.transport.send_text(
                chat_id,
                cleared_prefix
                + "A checkout was approved and its payment outcome is unresolved. "
                "Use /paysupport; financial deletion stays blocked until transaction "
                "reconciliation confirms no charge.",
            )
            return
        if deletion_block == "refund_reconciliation_pending":
            self.transport.send_text(
                chat_id,
                cleared_prefix
                + "A refund arrived before its payment ledger event. Use /paysupport; "
                "financial deletion stays blocked until the Star transaction and renewal "
                "are reconciled.",
            )
            return
        if deletion_block == "renewal_not_canceled":
            self.transport.send_text(
                chat_id,
                cleared_prefix
                + "Subscription renewal must be canceled before local payment records "
                "can be deleted. Use /cancel first.",
            )
            return
        if deletion_block == "renewal_cancellation_pending":
            self.transport.send_text(
                chat_id,
                cleared_prefix
                + "Renewal cancellation is not yet confirmed. Use /cancel again or "
                "/paysupport; financial deletion remains blocked.",
            )
            return
        if deletion_block == "paid_period_open":
            self.transport.send_text(
                chat_id,
                cleared_prefix
                + "Local payment records cannot be deleted during a paid period. "
                "Deletion becomes available after access expires.",
            )
            return
        deleted = self.store.delete_recipient(user_id)
        text = (
            cleared_prefix
            + "The remaining local recipient, subscription, payment, and support rows "
            "were deleted with SQLite secure deletion enabled. WAL, backups, or storage "
            "snapshots may persist until separate maintenance."
            if deleted
            else cleared_prefix + "No finance-linked recipient record was present."
        )
        self.transport.send_text(chat_id, text)

    def _send_latest(self, user_id: int, chat_id: int) -> None:
        signal = self.store.latest_signal()
        if not signal:
            self.transport.send_text(chat_id, "No active, risk-passing research signal is available.")
            return
        entitled = self.store.is_entitled(user_id)
        action = Action.VIEW_RESEARCH_SIGNAL if entitled else Action.VIEW_PUBLIC_SIGNAL
        decision = self.policy.decide(action, entitled=entitled)
        if not decision.allowed:
            self.transport.send_text(chat_id, decision.explanation)
            return
        renderer = render_research_signal if entitled else render_public_signal
        self.transport.send_text(chat_id, renderer(signal), protect_content=entitled)

    def _record_paper(
        self, user_id: int, chat_id: int, args: list[str], update_id: int
    ) -> None:
        entitled = self.store.is_entitled(user_id)
        if not entitled:
            decision = self.policy.decide(Action.RECORD_PAPER_ACTION)
            self.transport.send_text(chat_id, f"{decision.code}: {decision.explanation}")
            return
        if not args:
            self.transport.send_text(chat_id, "Usage: /paper SIGNAL_ID [simulated USD amount]")
            return
        amount = 100.0
        if len(args) > 1:
            try:
                amount = float(args[1])
            except ValueError:
                self.transport.send_text(chat_id, "Paper amount must be a number.")
                return
        decision = self.policy.decide(
            Action.RECORD_PAPER_ACTION,
            entitled=entitled,
            explicit_user_request=True,
            amount_usdc=amount,
        )
        if not decision.allowed:
            self.transport.send_text(chat_id, f"{decision.code}: {decision.explanation}")
            return
        signal = self.store.resolve_signal_prefix(args[0])
        if not signal:
            self.transport.send_text(chat_id, "Signal is missing, ambiguous, rejected, or expired.")
            return
        action_id = self.store.record_paper_action(
            telegram_user_id=user_id,
            signal=signal,
            simulated_amount_usdc=amount,
            explicit_request_ref=f"telegram-update:{update_id}",
        )
        self.transport.send_text(
            chat_id,
            f"Paper simulation recorded: {action_id}\n"
            f"{signal['market']['direction']} at "
            f"{signal['market']['quoted_outcome_token_price']:.1%}, ${amount:,.2f} simulated.\n"
            "No wallet or market was contacted.",
        )

    def _show_plan(self, chat_id: int, *, include_terms_button: bool) -> None:
        if not self.config.commerce_enabled:
            self.transport.send_text(
                chat_id,
                "Research subscriptions are disabled in this runtime.",
            )
            return
        text = (
            f"KINGDOM Research: {self.config.stars_amount} Telegram Stars every 30 days.\n"
            "Includes current evidence-labelled signals and subscriber delivery.\n"
            "Forecasts can be wrong; no live execution or return guarantee is included."
        )
        markup = None
        if include_terms_button:
            text += "\n\nReview /terms, then use the button to accept the current terms and create a private invoice."
            markup = {
                "inline_keyboard": [[
                    {
                        "text": "I agree and continue",
                        "callback_data": self._terms_callback_data(),
                    }
                ]]
            }
        self.transport.send_text(chat_id, text, reply_markup=markup)

    def _send_status(self, user_id: int, chat_id: int) -> None:
        status = self.store.recipient_status(user_id) or {}
        alert_status = self.store.research_alert_status(
            user_id, self.config.promotion_notice_version
        )["state"]
        active = bool(status.get("active"))
        subscription = self.store.latest_subscription(user_id, self.config.plan_code)
        renewal_status = (
            "cancellation pending (unconfirmed; use /cancel or /paysupport)"
            if subscription and subscription["cancellation_pending_at"]
            else subscription.get("renewal_state")
            if subscription
            else "none"
        )
        lines = [
            f"Access: {'research' if active else 'free'}",
            f"Access through: {status.get('entitlement_expires_at') or 'not active'}",
            f"Research alerts: {alert_status}",
            f"Renewal: {renewal_status}",
            "Live execution: disabled",
            "Wallet/signing capability: absent",
            "Jurisdiction eligibility: not established by this bot",
        ]
        if self.preferences is not None:
            snapshot = self._preference_snapshot(user_id)
            if snapshot is None:
                lines.append("Personalization: local readback unavailable")
            else:
                topic_summary = (
                    ", ".join(snapshot.topics) if snapshot.topics else "all"
                )
                lines.extend(
                    [
                        f"Personalization: {snapshot.consent_state}",
                        f"Topic filter: {topic_summary if snapshot.active else 'not active'}",
                        f"Cadence: {snapshot.cadence or 'not active'}",
                        f"Watchlist items: {len(snapshot.watchlist)}",
                    ]
                )
        self.transport.send_text(chat_id, "\n".join(lines))

    def _handle_callback(
        self, callback: Mapping[str, Any], update_id: int
    ) -> None:
        callback_id = _string(callback.get("id"), 256)
        sender = callback.get("from") if isinstance(callback.get("from"), Mapping) else {}
        message = callback.get("message") if isinstance(callback.get("message"), Mapping) else {}
        chat = message.get("chat") if isinstance(message.get("chat"), Mapping) else {}
        user_id = _integer(sender.get("id"))
        chat_id = _integer(chat.get("id"))
        if not callback_id:
            return
        # Callback acknowledgement only clears Telegram's client-side spinner;
        # it is not authority for, or a prerequisite to, the local action. A
        # transient acknowledgement failure must not consume an explicit
        # opt-in or payment-control update before its durable effect.
        try:
            self.transport.answer_callback(callback_id)
        except TelegramError:
            pass
        if (
            user_id is None
            or user_id <= 0
            or chat_id is None
            or chat_id != user_id
            or chat.get("type") != "private"
        ):
            return
        data = _string(callback.get("data"), 64)
        received_at = datetime.now(timezone.utc)
        if not self.store.contact_action_is_newer(
            user_id,
            update_id,
            event_at=received_at,
        ):
            return
        if not self.store.allow_interactive_request(user_id):
            return

        promotion = self._parse_promotion_join_callback_data(data)
        if promotion is not None:
            notice_digest, campaign_code = promotion
            if notice_digest != self._promotion_notice_digest():
                self.transport.send_text(
                    chat_id,
                    "That alert invitation uses an older notice. Send /start again "
                    "and review the current disclosure before opting in.",
                )
                return
            if not self.store.is_active_promotion_campaign(campaign_code):
                self.transport.send_text(
                    chat_id,
                    "That campaign invitation is no longer active. Use /join if you "
                    "still want the standard free alerts.",
                )
                return
            self.store.register_recipient(user_id, chat_id, now=received_at)
            promotion_join = self.store.join_promotion_campaign(
                user_id,
                campaign_code,
                update_id,
                notice_version=self.config.promotion_notice_version,
                event_at=received_at,
                now=received_at,
            )
            if not promotion_join["campaign_active"]:
                self.transport.send_text(
                    chat_id,
                    "That campaign invitation is no longer active. Use /join if you "
                    "still want the standard free alerts.",
                )
                return
            if not promotion_join["subscribed"]:
                self.transport.send_text(
                    chat_id,
                    "This alert action did not replace a later no-contact preference. "
                    "Send /join again if you want to turn alerts on.",
                )
                return
            prefix = (
                "Research alerts are now on from this source. "
                if promotion_join["attributed"]
                and promotion_join["consent_changed"]
                else "Research alerts are now on. "
                if promotion_join["consent_changed"]
                else "Research alerts were already on. "
            )
            self.transport.send_text(
                chat_id,
                prefix
                + "You may receive at most two approved previews per rolling seven "
                "days. Use /leave or /stop at any time. No trade will be placed.",
            )
            return

        if data != self._terms_callback_data():
            self.transport.send_text(chat_id, "That action is no longer available. Use /subscribe.")
            return
        self.store.register_recipient(user_id, chat_id, now=received_at)
        if not self.config.commerce_enabled:
            self.transport.send_text(chat_id, "Subscriptions are not currently configured.")
            return
        existing_subscription = self.store.latest_subscription(
            user_id, self.config.plan_code
        )
        if existing_subscription and existing_subscription["cancellation_pending_at"]:
            self.transport.send_text(
                chat_id,
                "The previous renewal cancellation is not yet confirmed at Telegram. "
                "Use /cancel to retry or /paysupport before opening another subscription.",
            )
            return
        if existing_subscription and not (
            existing_subscription["renewal_state"] in {"canceled", "failed"}
            and datetime.fromisoformat(
                existing_subscription["current_period_end"].replace("Z", "+00:00")
            )
            <= datetime.now(timezone.utc)
        ):
            self.transport.send_text(
                chat_id,
                "A subscription is still active or awaiting renewal reconciliation. "
                "Use /status or /cancel before starting another.",
            )
            return

        self.store.accept_terms(user_id, self.config.terms_version)
        try:
            payload = self.store.create_invoice_intent(
                telegram_user_id=user_id,
                plan_code=self.config.plan_code,
                total_amount=self.config.stars_amount,
                terms_version=self.config.terms_version,
            )
        except ValueError:
            self.transport.send_text(
                chat_id,
                "A checkout or subscription is already open. Use /status or try again "
                "after the current invoice expires or /paysupport resolves it.",
            )
            return
        link = self.transport.create_subscription_link(
            payload=payload, stars_amount=self.config.stars_amount
        )
        self.transport.send_text(
            chat_id,
            "Terms acceptance recorded. This invoice is private, single-use, and expires in 15 minutes.",
            reply_markup={
                "inline_keyboard": [[
                    {"text": f"Subscribe — {self.config.stars_amount} ⭐", "url": link}
                ]]
            },
        )

    def _terms_callback_data(self) -> str:
        digest = hashlib.sha256(self.config.terms_version.encode("utf-8")).hexdigest()[:12]
        return "terms_accept:" + digest

    def _promotion_notice_digest(self) -> str:
        return hashlib.sha256(
            self.config.promotion_notice_version.encode("utf-8")
        ).hexdigest()[:12]

    def _promotion_join_callback_data(self, campaign_code: str) -> str:
        code = validate_campaign_code(campaign_code)
        value = (
            PROMOTION_JOIN_CALLBACK_PREFIX
            + self._promotion_notice_digest()
            + ":"
            + code
        )
        if len(value.encode("utf-8")) > 64:
            raise ValueError("promotion callback exceeds Telegram's size limit")
        return value

    def _parse_promotion_join_callback_data(
        self, value: str
    ) -> tuple[str, str] | None:
        if not value.startswith(PROMOTION_JOIN_CALLBACK_PREFIX):
            return None
        parts = value.split(":", 2)
        if len(parts) != 3 or len(parts[1]) != 12:
            return None
        if any(character not in "0123456789abcdef" for character in parts[1]):
            return None
        try:
            code = validate_campaign_code(parts[2])
        except ValueError:
            return None
        return parts[1], code

    def _handle_pre_checkout(self, query: Mapping[str, Any]) -> None:
        query_id = _string(query.get("id"), 256)
        sender = query.get("from") if isinstance(query.get("from"), Mapping) else {}
        user_id = _integer(sender.get("id"))
        if not query_id:
            return
        if user_id is None or user_id <= 0:
            self.transport.answer_pre_checkout(
                query_id, ok=False, error_message="Invalid Telegram account identifier."
            )
            return
        if not self.config.commerce_enabled:
            self.transport.answer_pre_checkout(
                query_id, ok=False, error_message="Subscriptions are currently disabled."
            )
            return
        ok, message = self.store.reserve_invoice_intent(
            payload=_string(query.get("invoice_payload"), 128),
            telegram_user_id=user_id,
            currency=_string(query.get("currency"), 8),
            total_amount=_integer(query.get("total_amount")) or 0,
            pre_checkout_query_id=query_id,
            current_terms_version=self.config.terms_version,
        )
        try:
            accepted = self.transport.answer_pre_checkout(
                query_id, ok=ok, error_message=None if ok else message
            )
        except TelegramError as exc:
            if ok and not exc.ambiguous:
                self.store.release_invoice_reservation(
                    _string(query.get("invoice_payload"), 128), query_id
                )
            raise
        if ok and accepted is not True:
            self.store.release_invoice_reservation(
                _string(query.get("invoice_payload"), 128), query_id
            )
            raise TelegramError("Telegram did not confirm pre-checkout approval")

    def _handle_successful_payment(
        self,
        payment: Mapping[str, Any],
        user_id: int,
        chat_id: int,
        update_id: int,
    ) -> None:
        try:
            result = self.store.record_subscription_payment(
                telegram_user_id=user_id,
                private_chat_id=chat_id,
                telegram_payment_charge_id=_string(
                    payment.get("telegram_payment_charge_id"), 256
                ),
                currency=_string(payment.get("currency"), 8),
                total_amount=_integer(payment.get("total_amount")) or 0,
                invoice_payload=_string(payment.get("invoice_payload"), 128),
                is_recurring=payment.get("is_recurring") is True,
                is_first_recurring=payment.get("is_first_recurring") is True,
                subscription_expiration_unix=_integer(
                    payment.get("subscription_expiration_date")
                ),
                telegram_update_id=update_id,
            )
        except ValueError:
            case_id = self.store.open_support_case(user_id)
            self.transport.send_text(
                chat_id,
                f"Payment was received but could not be reconciled automatically. "
                f"Support case: {case_id}. Access was not granted yet.",
            )
            return
        cancellation_confirmed = not result.cancellation_required
        if result.cancellation_required:
            try:
                provider_result = self.transport.edit_subscription(
                    user_id=user_id,
                    initial_charge_id=result.initial_charge_id,
                    canceled=True,
                )
            except TelegramError:
                provider_result = False
            cancellation_confirmed = provider_result is True and self.store.set_subscription_state(
                telegram_user_id=user_id,
                invoice_payload=result.invoice_payload,
                state="canceled",
                update_id=update_id,
            )
        if result.refunded:
            if not cancellation_confirmed:
                case_id = self.store.open_support_case(user_id)
                self.transport.send_text(
                    chat_id,
                    f"Payment and an earlier refund were reconciled, but renewal "
                    f"cancellation is unconfirmed. Support case: {case_id}.",
                )
                return
            remaining = result.entitlement_expires_at
            detail = (
                "Other paid access remains through "
                + remaining.isoformat(timespec="microseconds").replace("+00:00", "Z")
                + "."
                if remaining
                else "No research access was granted for the refunded charge."
            )
            self.transport.send_text(chat_id, "Refunded charge reconciled. " + detail)
            return
        if not cancellation_confirmed:
            case_id = self.store.open_support_case(user_id)
            self.transport.send_text(
                chat_id,
                "Payment and access were recorded, but the prior renewal-cancellation "
                f"intent is not confirmed at Telegram. Support case: {case_id}.",
            )
            return
        expires = result.entitlement_expires_at
        if expires is None:
            case_id = self.store.open_support_case(user_id)
            self.transport.send_text(
                chat_id,
                f"Payment is recorded but no current entitlement could be derived. "
                f"Support case: {case_id}.",
            )
            return
        renewal_detail = (
            " Renewal remains canceled."
            if result.cancellation_required
            else ""
        )
        self.transport.send_text(
            chat_id,
            "Research access is active through "
            + expires.astimezone(timezone.utc).isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z")
            + "."
            + renewal_detail
            + " Use /status at any time.",
        )

    def _handle_refunded_payment(
        self,
        payment: Mapping[str, Any],
        user_id: int,
        chat_id: int,
        update_id: int,
    ) -> None:
        charge_id = _string(payment.get("telegram_payment_charge_id"), 256)
        try:
            refund = (
                self.store.begin_payment_refund(
                    charge_id,
                    telegram_user_id=user_id,
                    currency=_string(payment.get("currency"), 8),
                    total_amount=_integer(payment.get("total_amount")) or 0,
                    invoice_payload=_string(payment.get("invoice_payload"), 128),
                )
                if charge_id
                else None
            )
        except ValueError:
            refund = None
        if not refund:
            self.store.open_support_case(user_id)
            self.transport.send_text(
                chat_id, "Refund update could not be matched. Use /paysupport."
            )
            return
        if not refund["cancellation_required"]:
            remaining = refund["remaining_entitlement_expires_at"]
            suffix = (
                f" Other paid access continues through {remaining}."
                if remaining
                else " No research access remains for that charge."
            )
            prefix = (
                "Refund was already reconciled."
                if refund["already_refunded"]
                else "Refund recorded."
            )
            self.transport.send_text(chat_id, prefix + suffix)
            return
        try:
            canceled = self.transport.edit_subscription(
                user_id=user_id,
                initial_charge_id=refund["initial_charge_id"],
                canceled=True,
            )
        except TelegramError:
            self.store.open_support_case(user_id)
            self.transport.send_text(
                chat_id,
                "Refund recorded and access reconciled, but renewal cancellation is "
                "still unconfirmed. Use /paysupport; local deletion remains blocked.",
            )
            return
        if canceled is not True or not self.store.set_subscription_state(
            telegram_user_id=user_id,
            invoice_payload=refund["invoice_payload"],
            state="canceled",
            update_id=update_id,
        ):
            self.store.open_support_case(user_id)
            self.transport.send_text(
                chat_id,
                "Refund recorded, but renewal cancellation is not confirmed. "
                "Use /paysupport; local deletion remains blocked.",
            )
            return
        remaining = refund["remaining_entitlement_expires_at"]
        suffix = (
            f" Remaining paid access continues through {remaining}."
            if remaining
            else " Research access was revoked."
        )
        self.transport.send_text(
            chat_id, "Refund recorded and renewal canceled." + suffix
        )

    def _handle_subscription_update(
        self, event: Mapping[str, Any], update_id: int
    ) -> None:
        sender = event.get("user") if isinstance(event.get("user"), Mapping) else {}
        user_id = _integer(sender.get("id"))
        state = _string(event.get("state"), 16)
        payload = _string(event.get("invoice_payload"), 128)
        if (
            user_id is None
            or user_id <= 0
            or state not in {"active", "canceled", "failed"}
            or not payload
        ):
            return
        self.store.register_recipient(user_id, user_id)
        if state == "active":
            cancellation_target = self.store.cancellation_intent_target(
                telegram_user_id=user_id,
                invoice_payload=payload,
            )
            if cancellation_target:
                # Update IDs cannot order a provider event already queued before
                # an editUserStarSubscription call. A durable user/refund intent
                # therefore dominates reactivation until a new subscription.
                self.store.mark_subscription_cancellation_pending(
                    telegram_user_id=user_id,
                    invoice_payload=payload,
                )
                try:
                    confirmed = self.transport.edit_subscription(
                        user_id=user_id,
                        initial_charge_id=cancellation_target["initial_charge_id"],
                        canceled=True,
                    )
                except TelegramError:
                    self.store.open_support_case(user_id)
                    return
                if confirmed is not True or not self.store.set_subscription_state(
                    telegram_user_id=user_id,
                    invoice_payload=payload,
                    state="canceled",
                    update_id=update_id,
                ):
                    self.store.open_support_case(user_id)
                return
        self.store.apply_subscription_update(
            telegram_user_id=user_id,
            invoice_payload=payload,
            state=state,
            update_id=update_id,
        )

    def _cancel_subscription(self, user_id: int, chat_id: int, update_id: int) -> None:
        subscriptions = self.store.subscriptions_for_user(user_id)
        if not subscriptions:
            self.transport.send_text(chat_id, "No current subscription was found.")
            return
        failures = 0
        canceled_count = 0
        for subscription in subscriptions:
            # Re-confirm even a locally canceled subscription.  This command is
            # a newer user intent and must dominate any delayed provider event
            # that could otherwise reactivate renewal after an older cancel.
            self.store.mark_subscription_cancellation_pending(
                telegram_user_id=user_id,
                invoice_payload=subscription["invoice_payload"],
            )
            try:
                confirmed = self.transport.edit_subscription(
                    user_id=user_id,
                    initial_charge_id=subscription["initial_charge_id"],
                    canceled=True,
                )
            except TelegramError:
                failures += 1
                continue
            if confirmed is not True or not self.store.set_subscription_state(
                telegram_user_id=user_id,
                invoice_payload=subscription["invoice_payload"],
                state="canceled",
                update_id=update_id,
            ):
                failures += 1
                continue
            canceled_count += 1
        if failures:
            case_id = self.store.open_support_case(user_id)
            self.transport.send_text(
                chat_id,
                f"Some renewal cancellations remain unconfirmed. Support case: {case_id}. "
                "Use /cancel to retry; local deletion remains blocked.",
            )
            return
        end = max(subscription["current_period_end"] for subscription in subscriptions)
        self.transport.send_text(
            chat_id,
            f"Renewal canceled for {canceled_count or len(subscriptions)} subscription(s). "
            f"Any paid access remains through at most {end}.",
        )

    def _handle_membership(
        self, event: Mapping[str, Any], update_id: int
    ) -> None:
        chat = event.get("chat") if isinstance(event.get("chat"), Mapping) else {}
        member = (
            event.get("new_chat_member")
            if isinstance(event.get("new_chat_member"), Mapping)
            else {}
        )
        chat_id = _integer(chat.get("id"))
        if chat_id is None or chat_id <= 0 or chat.get("type") != "private":
            return
        # In a private ``my_chat_member`` update the new member is the bot.
        # The human recipient is represented by the private chat ID.
        user_id = chat_id
        status = str(member.get("status") or "")
        if status in {"kicked", "left"}:
            occurred_at = _telegram_message_time(event.get("date"))
            if self.preferences is not None:
                try:
                    self.preferences.withdraw_consent(
                        user_id,
                        update_id,
                        event_at=occurred_at,
                    )
                except (OSError, sqlite3.Error, TypeError, ValueError):
                    # Core contact suppression below is the authoritative send
                    # gate. Preference cleanup remains independently retryable
                    # through /delete_me if the user later unblocks the bot.
                    pass
            self.store.record_contact_suppression(
                user_id,
                telegram_update_id=update_id,
                reason="blocked",
                event_at=occurred_at,
            )
            self.store.mark_recipient_blocked(user_id, True)
            if self.store.recipient_status(user_id) is not None:
                self.store.set_research_alert_consent(
                    user_id,
                    subscribed=False,
                    telegram_update_id=update_id,
                    notice_version=self.config.promotion_notice_version,
                    event_at=occurred_at,
                )
        elif status in {"member", "administrator"}:
            occurred_at = _telegram_message_time(event.get("date"))
            if self.store.contact_action_is_newer(
                user_id,
                update_id,
                event_at=occurred_at,
            ):
                self.store.register_recipient(user_id, chat_id)

    def broadcast_pending(self, *, limit: int = 20) -> dict[str, int]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 1_000
        ):
            raise ValueError("delivery limit must be between 1 and 1000")
        result = {"sent": 0, "failed": 0, "unknown": 0}
        # Topic and cadence filters are per-recipient. Inspect the bounded
        # store maximum so an early run of filtered-out recipients cannot
        # starve otherwise eligible deliveries later in the queue.
        candidate_limit = 1_000 if self.preferences else limit
        deliveries = self.store.pending_deliveries(
            limit=candidate_limit,
            notice_version=self.config.promotion_notice_version,
        )
        if self.preferences is not None:
            deliveries = [
                delivery
                for delivery in deliveries
                if self._preference_allows_delivery(delivery)
            ][:limit]
        for delivery in deliveries:
            try:
                research_view = delivery["delivery_view"] == "research"
                response = self.transport.send_text(
                    delivery["private_chat_id"],
                    (
                        render_research_signal(delivery["envelope"])
                        if research_view
                        else render_public_signal(delivery["envelope"])
                    )
                    + "\n\nAlert cadence: at most two per rolling seven days. "
                    "Use /leave or /stop to stop new alerts.",
                    protect_content=research_view,
                )
                message_id = _integer(response.get("message_id"))
                if message_id is None or message_id <= 0:
                    raise TelegramError(
                        "Telegram did not confirm the sent message", ambiguous=True
                    )
                self.store.record_delivery(
                    signal_id=delivery["signal_id"],
                    telegram_user_id=delivery["telegram_user_id"],
                    status="sent",
                    telegram_message_id=message_id,
                )
                result["sent"] += 1
            except TelegramError as exc:
                if exc.error_code == 403:
                    self.store.mark_recipient_blocked(delivery["telegram_user_id"], True)
                    self.store.record_contact_suppression(
                        delivery["telegram_user_id"],
                        telegram_update_id=0,
                        reason="blocked",
                    )
                status = "unknown" if exc.ambiguous else "failed"
                self.store.record_delivery(
                    signal_id=delivery["signal_id"],
                    telegram_user_id=delivery["telegram_user_id"],
                    status=status,
                    error_code=str(exc.error_code or "transport"),
                    retry_after_seconds=exc.retry_after,
                )
                result[status] += 1
        return result

    def _preference_allows_delivery(self, delivery: Mapping[str, Any]) -> bool:
        """Apply optional topic/watchlist/cadence limits before an ordinary alert.

        Corrections deliberately bypass this selector. Alert consent and
        personalization consent are independent: a missing, withdrawn,
        deleted, or stale preference profile means no personalization filter,
        while the core alert-consent and suppression store remains the
        authoritative proactive-send gate.
        """

        if self.preferences is None:
            return True
        user_id = _integer(delivery.get("telegram_user_id"))
        envelope = delivery.get("envelope")
        if user_id is None or not isinstance(envelope, Mapping):
            return False
        try:
            snapshot = self.preferences.snapshot(user_id)
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return False
        if not snapshot.active:
            return True

        market = envelope.get("market")
        if not isinstance(market, Mapping):
            return False
        market_id = str(market.get("market_id") or "")
        signal_id = str(envelope.get("signal_id") or "")
        watched = {
            market_id,
            signal_id,
            f"polymarket:{market_id}",
        } & set(snapshot.watchlist)
        if not watched and snapshot.topics:
            domain_topics = {
                "ECO": {"macro-policy", "economic-releases"},
                "POL": {"elections"},
                "GEO": {"geopolitics"},
                "FIN": {"financial-markets"},
                "CRY": {"crypto-assets"},
                "TEC": {"technology-ai"},
                "SCI": {"science-health"},
                "SOC": {"society-culture"},
                "LAW": {"legal-regulation"},
                "ENV": {"environment-energy"},
            }.get(str(market.get("domain") or "").upper(), set())
            if not domain_topics.intersection(snapshot.topics):
                return False

        if snapshot.cadence == "realtime":
            return True
        interval = timedelta(days=1 if snapshot.cadence == "daily" else 7)
        row = self.store.conn.execute(
            """SELECT attempted_at FROM delivery_receipts
               WHERE telegram_user_id = ? AND status IN ('sent', 'unknown')
               ORDER BY julianday(attempted_at) DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        if row is None:
            return True
        try:
            previous = datetime.fromisoformat(
                str(row["attempted_at"]).replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        except (TypeError, ValueError):
            return False
        return datetime.now(timezone.utc) - previous >= interval

    def broadcast_pending_corrections(self, *, limit: int = 50) -> dict[str, int]:
        result = {
            "corrections_sent": 0,
            "corrections_failed": 0,
            "corrections_unknown": 0,
        }
        for delivery in self.store.pending_signal_corrections(limit=limit):
            try:
                response = self.transport.send_text(
                    delivery["private_chat_id"],
                    render_signal_correction(delivery),
                    protect_content=False,
                )
                message_id = _integer(response.get("message_id"))
                if message_id is None or message_id <= 0:
                    raise TelegramError(
                        "Telegram did not confirm the correction message",
                        ambiguous=True,
                    )
                self.store.record_signal_correction_delivery(
                    event_id=delivery["event_id"],
                    telegram_user_id=delivery["telegram_user_id"],
                    status="sent",
                    telegram_message_id=message_id,
                )
                result["corrections_sent"] += 1
            except TelegramError as exc:
                if exc.error_code == 403:
                    self.store.mark_recipient_blocked(
                        delivery["telegram_user_id"], True
                    )
                    self.store.record_contact_suppression(
                        delivery["telegram_user_id"],
                        telegram_update_id=0,
                        reason="blocked",
                    )
                status = "unknown" if exc.ambiguous else "failed"
                self.store.record_signal_correction_delivery(
                    event_id=delivery["event_id"],
                    telegram_user_id=delivery["telegram_user_id"],
                    status=status,
                    error_code=str(exc.error_code or "transport"),
                    retry_after_seconds=exc.retry_after,
                )
                result[f"corrections_{status}"] += 1
        return result

    def poll_once(
        self,
        *,
        timeout: int | None = None,
        broadcast: bool = True,
        deliver_corrections: bool = True,
    ) -> dict[str, int]:
        wait = self.config.poll_timeout_seconds if timeout is None else timeout
        if not 0 <= wait <= 50:
            raise ValueError("poll timeout must be between 0 and 50 seconds")
        updates = self.transport.get_updates(
            offset=self.store.prepare_update_poll(), timeout=wait
        )
        processed = 0
        failed_updates = 0
        valid_updates = [item for item in updates if isinstance(item, Mapping)]

        for update in sorted(
            valid_updates,
            key=lambda item: (
                value
                if (value := _telegram_update_id(item.get("update_id"))) is not None
                else -1
            ),
        ):
            update_id = _telegram_update_id(update.get("update_id"))
            try:
                if self.handle_update(update):
                    processed += 1
            except TelegramError as exc:
                if update_id is not None and update_id >= 0:
                    self.store.mark_update_failed(
                        update_id,
                        error_code=str(exc.error_code or "telegram_transport"),
                        ambiguous=exc.ambiguous,
                    )
                    failed_updates += 1
            except (OverflowError, TypeError, ValueError):
                if update_id is not None and update_id >= 0:
                    self.store.mark_update_failed(
                        update_id, error_code="invalid_update", ambiguous=False
                    )
                    failed_updates += 1
        corrections = (
            self.broadcast_pending_corrections()
            if deliver_corrections
            else {
                "corrections_sent": 0,
                "corrections_failed": 0,
                "corrections_unknown": 0,
            }
        )
        delivery = (
            self.broadcast_pending()
            if broadcast
            else {"sent": 0, "failed": 0, "unknown": 0}
        )
        return {
            "updates": processed,
            "failed_updates": failed_updates,
            "broadcast_paused": int(not broadcast),
            "corrections_paused": int(not deliver_corrections),
            **corrections,
            **delivery,
        }

    def run(self) -> None:
        while True:
            try:
                self.poll_once()
            except TelegramError as exc:
                delay = exc.retry_after or 5
                time.sleep(min(max(delay, 1), 60))
            except sqlite3.OperationalError:
                time.sleep(1)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if not -(1 << 63) <= value <= (1 << 63) - 1:
        return None
    return value


def _telegram_update_id(value: Any) -> int | None:
    parsed = _integer(value)
    if parsed is None or not 0 <= parsed <= (1 << 31) - 1:
        return None
    return parsed


def _telegram_message_time(value: Any) -> datetime | None:
    parsed = _integer(value)
    if parsed is None or not 0 <= parsed <= 4_102_444_800:
        return None
    try:
        return datetime.fromtimestamp(parsed, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _string(value: Any, limit: int) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        if len(value.encode("utf-8")) > limit:
            return ""
    except UnicodeError:
        return ""
    return value
