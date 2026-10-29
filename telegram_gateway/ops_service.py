"""Owner-bound, read-only Telegram command surface for AgentTool projections.

This module parses one Telegram update and returns a transport-neutral reply.
It does not send messages, open the AgentTool journal, manage agent sessions,
or mutate coordination state.  The caller supplies both a stable update
deduplicator and a deliberately small, already-sanitized projection source.

The service describes only what the projection source observed.  In
particular, a recorded session state or journal event is not evidence of a
persistent identity, consciousness, health, availability, consent, truth, or
authority.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Literal, Mapping, Protocol, Sequence


MAX_TELEGRAM_ID = (1 << 52) - 1
MAX_TELEGRAM_UPDATE_ID = (1 << 31) - 1
MAX_REPLY_CHARACTERS = 3_800

# Bot-addressed forms stay outside this transport-neutral layer until a live
# runner can supply and verify the exact Ops bot username.
_COMMAND_TOKEN = re.compile(r"/(?P<name>[A-Za-z_]{1,32})\Z")
_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_WORKSPACE_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")
_EVENT_KIND = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")

TaskState = Literal[
    "open",
    "claimed",
    "blocked",
    "reported_complete",
    "completed",
    "unknown",
]
ReviewState = Literal[
    "not_required",
    "pending",
    "accepted",
    "changes_requested",
    "unknown",
]
JournalVerificationOutcome = Literal["valid", "invalid", "unavailable"]

_TASK_STATES = frozenset(
    {"open", "claimed", "blocked", "reported_complete", "completed", "unknown"}
)
_REVIEW_STATES = frozenset(
    {"not_required", "pending", "accepted", "changes_requested", "unknown"}
)
_JOURNAL_OUTCOMES = frozenset({"valid", "invalid", "unavailable"})


class UpdateDeduplicator(Protocol):
    """Atomically retain stable Telegram update IDs.

    ``claim_update`` must return ``True`` exactly once for an update ID and
    ``False`` for every later call, including when updates arrive out of
    numeric order.  Implementations should be durable when this service is
    connected to a live transport; a max-seen cursor alone is insufficient.
    """

    def claim_update(self, update_id: int) -> bool: ...


class OpsProjectionSource(Protocol):
    """Read-only, sanitized projection boundary over coordination state."""

    def status_snapshot(self) -> "OpsStatusProjection": ...

    def list_tasks(self, *, limit: int) -> Sequence["SafeTaskProjection"]: ...

    def get_task(self, task_id: str) -> "SafeTaskProjection | None": ...

    def recent_events(self, *, limit: int) -> Sequence["SafeEventProjection"]: ...

    def journal_verify(self) -> "JournalVerificationProjection": ...


@dataclass(frozen=True)
class OpsServiceConfig:
    """Exact Telegram operator binding and bounded projection sizes."""

    operator_user_id: int
    operator_private_chat_id: int
    task_list_limit: int = 10
    event_list_limit: int = 8

    def __post_init__(self) -> None:
        _require_telegram_id("operator_user_id", self.operator_user_id)
        _require_telegram_id(
            "operator_private_chat_id", self.operator_private_chat_id
        )
        if self.operator_user_id != self.operator_private_chat_id:
            raise ValueError(
                "operator_user_id and operator_private_chat_id must match for a "
                "Telegram private chat"
            )
        _require_bounded_int("task_list_limit", self.task_list_limit, 1, 20)
        _require_bounded_int("event_list_limit", self.event_list_limit, 1, 20)

    def __repr__(self) -> str:
        return (
            "OpsServiceConfig(operator_user_id=<configured>, "
            "operator_private_chat_id=<configured>, "
            f"task_list_limit={self.task_list_limit!r}, "
            f"event_list_limit={self.event_list_limit!r})"
        )


@dataclass(frozen=True)
class OpsReply:
    """A reply for the owning durable outbox/transport to deliver."""

    update_id: int
    chat_id: int
    text: str
    protect_content: bool = True

    @property
    def idempotency_key(self) -> str:
        """Stable local outbox key; Telegram itself has no send idempotency key."""

        return f"telegram-ops-update-{self.update_id}-reply-v1"


@dataclass(frozen=True)
class OpsStatusProjection:
    """Minimized status fields safe for the private Ops surface."""

    workspace_alias: str
    observed_at: str
    journal_head_sequence: int
    open_tasks: int
    claimed_tasks: int
    blocked_tasks: int
    reported_complete_tasks: int
    completed_tasks: int
    pending_reviews: int
    session_records_observed: int
    sessions_recorded_active: int
    latest_session_event_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_alias, str) or not _WORKSPACE_ALIAS.fullmatch(
            self.workspace_alias
        ):
            raise ValueError("workspace_alias is invalid")
        _require_safe_line("observed_at", self.observed_at, 80)
        for name in (
            "journal_head_sequence",
            "open_tasks",
            "claimed_tasks",
            "blocked_tasks",
            "reported_complete_tasks",
            "completed_tasks",
            "pending_reviews",
            "session_records_observed",
            "sessions_recorded_active",
        ):
            _require_bounded_int(name, getattr(self, name), 0, (1 << 63) - 1)
        if self.sessions_recorded_active > self.session_records_observed:
            raise ValueError(
                "sessions_recorded_active cannot exceed session_records_observed"
            )
        if self.latest_session_event_at is not None:
            _require_safe_line(
                "latest_session_event_at", self.latest_session_event_at, 80
            )


@dataclass(frozen=True)
class SafeTaskProjection:
    """A task projection with no actor/session identity or local path fields."""

    task_id: str
    state: TaskState
    version: int
    review_state: ReviewState = "unknown"
    coordination_lease_recorded: bool = False
    summary: str | None = None
    evidence_reference_count: int = 0
    last_observed_at: str | None = None

    def __post_init__(self) -> None:
        _require_opaque_id("task_id", self.task_id)
        if self.state not in _TASK_STATES:
            raise ValueError("state is invalid")
        if self.review_state not in _REVIEW_STATES:
            raise ValueError("review_state is invalid")
        _require_bounded_int("version", self.version, 0, (1 << 63) - 1)
        if not isinstance(self.coordination_lease_recorded, bool):
            raise ValueError("coordination_lease_recorded must be a boolean")
        _require_bounded_int(
            "evidence_reference_count",
            self.evidence_reference_count,
            0,
            1_000_000,
        )
        if self.summary is not None:
            _require_safe_line("summary", self.summary, 320)
        if self.last_observed_at is not None:
            _require_safe_line("last_observed_at", self.last_observed_at, 80)


@dataclass(frozen=True)
class SafeEventProjection:
    """A bounded journal observation suitable for a private Telegram reply."""

    event_id: str
    kind: str
    observed_at: str
    summary: str
    task_id: str | None = None

    def __post_init__(self) -> None:
        _require_opaque_id("event_id", self.event_id)
        if not isinstance(self.kind, str) or not _EVENT_KIND.fullmatch(self.kind):
            raise ValueError("kind is invalid")
        _require_safe_line("observed_at", self.observed_at, 80)
        _require_safe_line("summary", self.summary, 320)
        if self.task_id is not None:
            _require_opaque_id("task_id", self.task_id)


@dataclass(frozen=True)
class JournalVerificationProjection:
    """Result of a read-only hash-chain check, not a truth/authenticity proof."""

    outcome: JournalVerificationOutcome
    checked_at: str
    journal_head_sequence: int | None
    verification_scope: str

    def __post_init__(self) -> None:
        if self.outcome not in _JOURNAL_OUTCOMES:
            raise ValueError("outcome is invalid")
        _require_safe_line("checked_at", self.checked_at, 80)
        if self.journal_head_sequence is not None:
            _require_bounded_int(
                "journal_head_sequence",
                self.journal_head_sequence,
                0,
                (1 << 63) - 1,
            )
        _require_safe_line("verification_scope", self.verification_scope, 160)


HELP_TEXT = """KINGDOM Ops — read-only coordination observations

/agent_status — bounded workspace and recorded-session status
/agent_tasks — bounded task projection list
/agent_task TASK_ID — one task projection
/agent_events — recent sanitized journal observations
/journal_verify — show the latest separately supplied full-journal verification result
/agent_privacy — data and authority boundaries
/help — show this message

These commands cannot spawn or stop agents, claim or recover work, change the journal, publish, pay, or trade."""

PRIVACY_TEXT = """KINGDOM Ops privacy and authority boundary

This surface accepts only the exact configured numeric operator user/private-chat pair and silently rejects bots and non-private chats. It does not use usernames as authorization.

Stable Telegram update IDs are passed to the configured dedupe store. Replies contain only bounded safe projections; they omit actor and session identifiers, prompts, transcripts, reasoning, credentials, local paths, artifact locations, and raw report bodies. Telegram still processes every delivered reply.

AgentTool's collaboration journal is shared local plaintext and append-only. This command neither reads arbitrary journal bodies nor deletes that history. Recorded presence and task state do not establish identity, consciousness, health, availability, consent, truth, ownership, permission, or authority.

This command surface is read-only. It cannot spawn or stop an agent, claim or recover a lease, publish, pay, or trade."""

_PRESENCE_LIMIT = (
    "Recorded session state is a coordination observation only; it does not "
    "establish identity, consciousness, health, availability, consent, or authority."
)
_TASK_LIMIT = (
    "Task and lease fields are journal projections, not ownership, truth, "
    "consent, permission, or action authority."
)
_EVENT_LIMIT = (
    "These are sanitized journal observations, not proof of identity, truth, "
    "consent, or authority."
)


class TelegramOpsService:
    """Parse owner-bound Telegram updates into read-only Ops replies."""

    __slots__ = ("source", "deduplicator", "config")

    def __init__(
        self,
        source: OpsProjectionSource,
        deduplicator: UpdateDeduplicator,
        config: OpsServiceConfig,
    ) -> None:
        self.source = source
        self.deduplicator = deduplicator
        self.config = config

    def handle_update(self, update: Mapping[str, object]) -> OpsReply | None:
        """Legacy claim-and-render API, not a crash-safe delivery path.

        A crash after the claim can lose the reply. Live callers must use the
        store's ``process_update_once(update, service, polling_epoch=...)``;
        it calls ``render_update`` within its own reply/disposition transaction.
        Historical legacy claims remain incomplete rather than being replayed.
        """

        if not isinstance(update, Mapping):
            return None
        update_id = _strict_int(update.get("update_id"))
        if (
            update_id is None
            or update_id < 0
            or update_id > MAX_TELEGRAM_UPDATE_ID
        ):
            return None

        claimed = self.deduplicator.claim_update(update_id)
        if not isinstance(claimed, bool):
            raise TypeError("claim_update must return a boolean")
        if not claimed:
            return None
        return self.render_update(update)

    def render_update(self, update: Mapping[str, object]) -> OpsReply | None:
        """Authorize and render only; no update claim, persistence, or send."""

        if not isinstance(update, Mapping):
            return None
        update_id = _strict_int(update.get("update_id"))
        if update_id is None or not 0 <= update_id <= MAX_TELEGRAM_UPDATE_ID:
            return None
        message = update.get("message")
        if not isinstance(message, Mapping):
            return None
        sender = message.get("from")
        chat = message.get("chat")
        if not isinstance(sender, Mapping) or not isinstance(chat, Mapping):
            return None
        if sender.get("is_bot") is not False or chat.get("type") != "private":
            return None

        user_id = _strict_int(sender.get("id"))
        chat_id = _strict_int(chat.get("id"))
        if user_id is None or chat_id is None:
            return None
        if not _valid_telegram_id(user_id) or not _valid_telegram_id(chat_id):
            return None
        if user_id != chat_id:
            return None
        if (
            user_id != self.config.operator_user_id
            or chat_id != self.config.operator_private_chat_id
        ):
            return None

        text = message.get("text")
        if not isinstance(text, str) or not 1 <= len(text) <= 4_096:
            return None
        parsed = _parse_command(text)
        if parsed is None:
            return self._reply(
                update_id,
                chat_id,
                "Read-only Ops commands only. Use /help.",
            )
        command, args = parsed

        if command in {"/help", "/start"}:
            if args:
                return self._usage(update_id, chat_id, command)
            return self._reply(update_id, chat_id, HELP_TEXT)
        if command == "/agent_privacy":
            if args:
                return self._usage(update_id, chat_id, "/agent_privacy")
            return self._reply(update_id, chat_id, PRIVACY_TEXT)
        if command == "/agent_status":
            if args:
                return self._usage(update_id, chat_id, "/agent_status")
            return self._projected_reply(
                update_id,
                chat_id,
                lambda: _render_status(self.source.status_snapshot()),
            )
        if command == "/agent_tasks":
            if args:
                return self._usage(update_id, chat_id, "/agent_tasks")
            return self._projected_reply(
                update_id,
                chat_id,
                lambda: _render_tasks(
                    self.source.list_tasks(limit=self.config.task_list_limit),
                    limit=self.config.task_list_limit,
                ),
            )
        if command == "/agent_task":
            if len(args) != 1 or not _valid_opaque_id(args[0]):
                return self._usage(
                    update_id, chat_id, "/agent_task TASK_ID"
                )
            task_id = args[0]
            return self._projected_reply(
                update_id,
                chat_id,
                lambda: _render_task_result(task_id, self.source.get_task(task_id)),
            )
        if command == "/agent_events":
            if args:
                return self._usage(update_id, chat_id, "/agent_events")
            return self._projected_reply(
                update_id,
                chat_id,
                lambda: _render_events(
                    self.source.recent_events(limit=self.config.event_list_limit),
                    limit=self.config.event_list_limit,
                ),
            )
        if command == "/journal_verify":
            if args:
                return self._usage(update_id, chat_id, "/journal_verify")
            return self._projected_reply(
                update_id,
                chat_id,
                lambda: _render_journal_verification(self.source.journal_verify()),
            )

        # Do not echo untrusted command text or advertise mutating operations.
        return self._reply(
            update_id,
            chat_id,
            "Unsupported read-only Ops command. Use /help.",
        )

    def _projected_reply(
        self,
        update_id: int,
        chat_id: int,
        render: Callable[[], str],
    ) -> OpsReply:
        try:
            text = render()
        except Exception:
            # A projection failure may contain private journal/path data.  The
            # Telegram response therefore remains fixed and content-free.
            text = (
                "The read-only Ops projection is temporarily unavailable. "
                "No coordination or external action was performed."
            )
        return self._reply(update_id, chat_id, text)

    def _usage(self, update_id: int, chat_id: int, syntax: str) -> OpsReply:
        return self._reply(update_id, chat_id, f"Usage: {syntax}")

    @staticmethod
    def _reply(update_id: int, chat_id: int, text: str) -> OpsReply:
        return OpsReply(
            update_id=update_id,
            chat_id=chat_id,
            text=_bound_reply(text),
            protect_content=True,
        )


def _render_status(status: OpsStatusProjection) -> str:
    if not isinstance(status, OpsStatusProjection):
        raise TypeError("status_snapshot returned an invalid projection")
    latest = status.latest_session_event_at or "not observed in this projection"
    return "\n".join(
        (
            "KINGDOM Ops — observed coordination status",
            f"Workspace projection: {status.workspace_alias}",
            f"Snapshot observed at: {status.observed_at}",
            f"Journal head sequence observed: {status.journal_head_sequence}",
            "Recorded tasks: "
            f"open {status.open_tasks}; claimed {status.claimed_tasks}; "
            f"blocked {status.blocked_tasks}; reported complete "
            f"{status.reported_complete_tasks}; completed {status.completed_tasks}",
            f"Review records pending: {status.pending_reviews}",
            f"Session records observed: {status.session_records_observed}",
            "Sessions whose recorded state was active at snapshot: "
            f"{status.sessions_recorded_active}",
            f"Latest session-related journal event: {latest}",
            "",
            _PRESENCE_LIMIT,
        )
    )


def _render_tasks(tasks: Sequence[SafeTaskProjection], *, limit: int) -> str:
    if isinstance(tasks, (str, bytes)) or not isinstance(tasks, Sequence):
        raise TypeError("list_tasks returned an invalid projection")
    selected = tuple(tasks[:limit])
    if any(not isinstance(task, SafeTaskProjection) for task in selected):
        raise TypeError("list_tasks returned an invalid task projection")
    lines = ["KINGDOM Ops — observed task projections"]
    if not selected:
        lines.append("No task records were returned by this projection.")
    for task in selected:
        review = (
            ""
            if task.review_state == "not_required"
            else f"; review {task.review_state.replace('_', ' ')}"
        )
        lease = "; coordination lease recorded" if task.coordination_lease_recorded else ""
        lines.append(
            f"- {task.task_id}: {task.state.replace('_', ' ')}; "
            f"version {task.version}{review}{lease}"
        )
    lines.extend(("", _TASK_LIMIT))
    return "\n".join(lines)


def _render_task_result(
    requested_task_id: str, task: SafeTaskProjection | None
) -> str:
    if task is None:
        return (
            "No safe task projection was found for that reference. "
            "This does not establish that no task exists."
        )
    if not isinstance(task, SafeTaskProjection) or task.task_id != requested_task_id:
        raise TypeError("get_task returned a mismatched projection")
    summary = task.summary or "withheld or not present in this safe projection"
    observed_at = task.last_observed_at or "not observed in this projection"
    return "\n".join(
        (
            f"KINGDOM Ops — task {task.task_id}",
            f"Observed task state: {task.state.replace('_', ' ')}",
            f"Version: {task.version}",
            "Coordination lease record: "
            + ("present" if task.coordination_lease_recorded else "not present"),
            f"Review record: {task.review_state.replace('_', ' ')}",
            f"Safe summary: {summary}",
            f"Evidence reference count: {task.evidence_reference_count}",
            f"Last task event observed at: {observed_at}",
            "",
            _TASK_LIMIT,
        )
    )


def _render_events(events: Sequence[SafeEventProjection], *, limit: int) -> str:
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        raise TypeError("recent_events returned an invalid projection")
    selected = tuple(events[:limit])
    if any(not isinstance(event, SafeEventProjection) for event in selected):
        raise TypeError("recent_events returned an invalid event projection")
    lines = ["KINGDOM Ops — recent sanitized journal observations"]
    if not selected:
        lines.append("No event records were returned by this projection.")
    for event in selected:
        task = f"; task {event.task_id}" if event.task_id else ""
        lines.append(
            f"- {event.observed_at}; {event.kind}{task}; {event.summary} "
            f"[{event.event_id}]"
        )
    lines.extend(("", _EVENT_LIMIT))
    return "\n".join(lines)


def _render_journal_verification(result: JournalVerificationProjection) -> str:
    if not isinstance(result, JournalVerificationProjection):
        raise TypeError("journal_verify returned an invalid projection")
    head = (
        str(result.journal_head_sequence)
        if result.journal_head_sequence is not None
        else "not available"
    )
    if result.outcome == "valid":
        finding = "The checked hash chain was internally valid."
    elif result.outcome == "invalid":
        finding = "The checked hash chain was invalid. Treat projections as unverified."
    else:
        finding = "The hash-chain check was unavailable."
    return "\n".join(
        (
            "KINGDOM Ops — journal integrity observation",
            finding,
            f"Checked at: {result.checked_at}",
            f"Journal head sequence checked: {head}",
            f"Verification scope: {result.verification_scope}",
            "",
            "Hash-chain integrity can detect some journal changes. It does not "
            "authenticate a person or model, prove recorded claims true, establish "
            "consent, or grant authority.",
        )
    )


def _parse_command(text: str) -> tuple[str, tuple[str, ...]] | None:
    stripped = text.strip()
    if not stripped:
        return None
    parts = stripped.split()
    match = _COMMAND_TOKEN.fullmatch(parts[0])
    if match is None:
        return None
    return "/" + match.group("name").lower(), tuple(parts[1:])


def _bound_reply(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("reply text must be a string")
    if len(text) <= MAX_REPLY_CHARACTERS:
        return text
    marker = "\n\n[Projection truncated by the read-only Ops surface.]"
    return text[: MAX_REPLY_CHARACTERS - len(marker)].rstrip() + marker


def _require_safe_line(name: str, value: object, max_characters: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > max_characters
        or value != value.strip()
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        raise ValueError(f"{name} must be a bounded, trimmed, single safe line")


def _valid_opaque_id(value: object) -> bool:
    return isinstance(value, str) and _OPAQUE_ID.fullmatch(value) is not None


def _require_opaque_id(name: str, value: object) -> None:
    if not _valid_opaque_id(value):
        raise ValueError(f"{name} is invalid")


def _strict_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _valid_telegram_id(value: object) -> bool:
    parsed = _strict_int(value)
    return parsed is not None and 1 <= parsed <= MAX_TELEGRAM_ID


def _require_telegram_id(name: str, value: object) -> None:
    if not _valid_telegram_id(value):
        raise ValueError(f"{name} must be a positive numeric Telegram ID")


def _require_bounded_int(name: str, value: object, minimum: int, maximum: int) -> None:
    parsed = _strict_int(value)
    if parsed is None or not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
