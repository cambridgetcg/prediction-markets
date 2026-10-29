"""Focused tests for the owner-only, read-only Telegram Ops surface."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from typing import Sequence

from telegram_gateway.agenttool_ops import (
    AgentToolOpsStore, BindingStateError, CursorStateError, DeliveryStateError,
    ProjectionConflict, TELEGRAM_PRODUCTION_ORIGIN,
)

import pytest

from telegram_gateway.ops_service import (
    JournalVerificationProjection,
    OpsReply,
    OpsServiceConfig,
    OpsStatusProjection,
    SafeEventProjection,
    SafeTaskProjection,
    TelegramOpsService,
)


# Synthetic Telegram-shaped ID; deployment supplies the real operator pair.
OPERATOR_ID = 4_242_424_242


@dataclass
class MemoryDedupe:
    seen: set[int] = field(default_factory=set)
    calls: list[int] = field(default_factory=list)

    def claim_update(self, update_id: int) -> bool:
        self.calls.append(update_id)
        if update_id in self.seen:
            return False
        self.seen.add(update_id)
        return True


@dataclass
class FakeProjectionSource:
    calls: list[object] = field(default_factory=list)
    tasks: tuple[SafeTaskProjection, ...] = (
        SafeTaskProjection(
            task_id="tsk_alpha7",
            state="claimed",
            version=3,
            review_state="pending",
            coordination_lease_recorded=True,
            summary="Inspect the bounded read-only adapter.",
            evidence_reference_count=2,
            last_observed_at="2026-09-03T20:00:00Z",
        ),
        SafeTaskProjection(
            task_id="tsk_beta8",
            state="open",
            version=1,
            review_state="not_required",
        ),
    )
    events: tuple[SafeEventProjection, ...] = (
        SafeEventProjection(
            event_id="evt_a1",
            kind="task.claimed",
            observed_at="2026-09-03T20:00:00Z",
            summary="A coordination lease was recorded.",
            task_id="tsk_alpha7",
        ),
    )

    def status_snapshot(self) -> OpsStatusProjection:
        self.calls.append("status")
        return OpsStatusProjection(
            workspace_alias="kingdom_ops",
            observed_at="2026-09-03T20:01:00Z",
            journal_head_sequence=42,
            open_tasks=1,
            claimed_tasks=1,
            blocked_tasks=0,
            reported_complete_tasks=0,
            completed_tasks=3,
            pending_reviews=1,
            session_records_observed=4,
            sessions_recorded_active=2,
            latest_session_event_at="2026-09-03T20:00:00Z",
        )

    def list_tasks(self, *, limit: int) -> Sequence[SafeTaskProjection]:
        self.calls.append(("tasks", limit))
        return self.tasks[:limit]

    def get_task(self, task_id: str) -> SafeTaskProjection | None:
        self.calls.append(("task", task_id))
        return next((task for task in self.tasks if task.task_id == task_id), None)

    def recent_events(self, *, limit: int) -> Sequence[SafeEventProjection]:
        self.calls.append(("events", limit))
        return self.events[:limit]

    def journal_verify(self) -> JournalVerificationProjection:
        self.calls.append("verify")
        return JournalVerificationProjection(
            outcome="valid",
            checked_at="2026-09-03T20:02:00Z",
            journal_head_sequence=42,
            verification_scope="local workspace journal through the observed head",
        )


def telegram_message(
    update_id: int,
    text: object,
    *,
    user_id: object = OPERATOR_ID,
    chat_id: object = OPERATOR_ID,
    chat_type: object = "private",
    is_bot: object = False,
) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": user_id, "is_bot": is_bot},
            "chat": {"id": chat_id, "type": chat_type},
            "text": text,
        },
    }


@pytest.fixture
def source() -> FakeProjectionSource:
    return FakeProjectionSource()


@pytest.fixture
def dedupe() -> MemoryDedupe:
    return MemoryDedupe()


@pytest.fixture
def service(
    source: FakeProjectionSource, dedupe: MemoryDedupe
) -> TelegramOpsService:
    return TelegramOpsService(
        source,
        dedupe,
        OpsServiceConfig(
            operator_user_id=OPERATOR_ID,
            operator_private_chat_id=OPERATOR_ID,
        ),
    )


@pytest.mark.parametrize(
    "user_id,chat_id,chat_type,is_bot",
    [
        (OPERATOR_ID + 1, OPERATOR_ID + 1, "private", False),
        (OPERATOR_ID, OPERATOR_ID + 1, "private", False),
        (OPERATOR_ID, OPERATOR_ID, "group", False),
        (OPERATOR_ID, OPERATOR_ID, "supergroup", False),
        (OPERATOR_ID, OPERATOR_ID, "private", True),
        (OPERATOR_ID, OPERATOR_ID, "private", None),
    ],
)
def test_unauthorized_bot_and_non_private_updates_are_silently_rejected(
    service: TelegramOpsService,
    source: FakeProjectionSource,
    dedupe: MemoryDedupe,
    user_id: object,
    chat_id: object,
    chat_type: object,
    is_bot: object,
) -> None:
    update_id = 100 + len(dedupe.calls)
    assert service.handle_update(
        telegram_message(
            update_id,
            "/agent_status",
            user_id=user_id,
            chat_id=chat_id,
            chat_type=chat_type,
            is_bot=is_bot,
        )
    ) is None
    assert source.calls == []
    assert dedupe.calls[-1] == update_id


@pytest.mark.parametrize(
    "update",
    [
        {},
        {"update_id": True},
        {"update_id": "1"},
        {"update_id": -1},
        {"update_id": 1 << 31},
    ],
)
def test_invalid_update_ids_are_rejected_before_dedupe(
    service: TelegramOpsService,
    dedupe: MemoryDedupe,
    update: dict[str, object],
) -> None:
    assert service.handle_update(update) is None
    assert dedupe.calls == []


@pytest.mark.parametrize(
    "message",
    [
        None,
        {},
        {"from": {}, "chat": {}},
        {
            "from": {"id": True, "is_bot": False},
            "chat": {"id": OPERATOR_ID, "type": "private"},
            "text": "/help",
        },
        {
            "from": {"id": OPERATOR_ID, "is_bot": False},
            "chat": {"id": OPERATOR_ID, "type": "private"},
            "text": None,
        },
    ],
)
def test_malformed_message_is_ignored_after_stable_update_claim(
    service: TelegramOpsService,
    source: FakeProjectionSource,
    dedupe: MemoryDedupe,
    message: object,
) -> None:
    update = {"update_id": 7, "message": message}
    assert service.handle_update(update) is None
    assert dedupe.calls == [7]
    assert source.calls == []


def test_duplicate_update_is_suppressed_and_out_of_order_ids_are_not(
    service: TelegramOpsService,
    source: FakeProjectionSource,
    dedupe: MemoryDedupe,
) -> None:
    first = service.handle_update(telegram_message(20, "/agent_status"))
    duplicate = service.handle_update(telegram_message(20, "/agent_status"))
    older = service.handle_update(telegram_message(5, "/agent_status"))

    assert isinstance(first, OpsReply)
    assert duplicate is None
    assert isinstance(older, OpsReply)
    assert source.calls == ["status", "status"]
    assert dedupe.calls == [20, 20, 5]
    assert first.idempotency_key == "telegram-ops-update-20-reply-v1"
    assert first.protect_content is True


def test_all_read_only_commands_route_to_the_projection(
    service: TelegramOpsService, source: FakeProjectionSource
) -> None:
    status = service.handle_update(telegram_message(1, "/agent_status"))
    tasks = service.handle_update(telegram_message(2, "/agent_tasks"))
    task = service.handle_update(
        telegram_message(3, "/agent_task tsk_alpha7")
    )
    events = service.handle_update(telegram_message(4, "/agent_events"))
    verify = service.handle_update(telegram_message(5, "/journal_verify"))

    assert isinstance(status, OpsReply)
    assert "observed coordination status" in status.text
    assert "Sessions whose recorded state was active at snapshot: 2" in status.text
    assert isinstance(tasks, OpsReply)
    assert "tsk_alpha7: claimed" in tasks.text
    assert isinstance(task, OpsReply)
    assert "Safe summary: Inspect the bounded read-only adapter." in task.text
    assert isinstance(events, OpsReply)
    assert "task.claimed" in events.text
    assert isinstance(verify, OpsReply)
    assert "internally valid" in verify.text
    assert source.calls == [
        "status",
        ("tasks", 10),
        ("task", "tsk_alpha7"),
        ("events", 8),
        "verify",
    ]


def test_presence_and_integrity_wording_preserves_epistemic_boundaries(
    service: TelegramOpsService,
) -> None:
    status = service.handle_update(telegram_message(1, "/agent_status"))
    verify = service.handle_update(telegram_message(2, "/journal_verify"))
    assert status is not None and verify is not None

    assert "recorded state" in status.text.lower()
    for boundary in (
        "identity",
        "consciousness",
        "health",
        "availability",
        "consent",
        "authority",
    ):
        assert boundary in status.text.lower()
    assert "authenticate a person or model" in verify.text
    assert "prove recorded claims true" in verify.text
    assert "grant authority" in verify.text
    assert "online" not in status.text.lower()
    assert "alive" not in status.text.lower()


def test_help_and_privacy_are_constant_and_do_not_query_projection(
    service: TelegramOpsService, source: FakeProjectionSource
) -> None:
    help_reply = service.handle_update(telegram_message(1, "/help"))
    privacy = service.handle_update(telegram_message(2, "/agent_privacy"))
    assert help_reply is not None and privacy is not None

    assert "/agent_status" in help_reply.text
    assert "latest separately supplied full-journal verification result" in help_reply.text
    assert "cannot spawn or stop agents" in help_reply.text
    assert "silently rejects bots and non-private chats" in privacy.text
    assert "does not use usernames as authorization" in privacy.text
    assert "append-only" in privacy.text
    assert "cannot spawn or stop an agent" in privacy.text
    assert source.calls == []


@pytest.mark.parametrize(
    "text",
    [
        "/agent_status@KingdomOpsBot",
        "/agent_tasks@KingdomOpsBot",
        "/agent_task@KingdomResearchBot tsk_alpha7",
        "/agent_events@KingdomOpsBot",
        "/journal_verify@KingdomOpsBot",
        "/agent_privacy@KingdomOpsBot",
        "/help@KingdomOpsBot",
    ],
)
def test_bot_addressed_commands_are_rejected_until_runner_verifies_bot_username(
    service: TelegramOpsService,
    source: FakeProjectionSource,
    text: str,
) -> None:
    reply = service.handle_update(telegram_message(abs(hash(text)) % 10_000, text))

    assert reply is not None
    assert reply.text == "Read-only Ops commands only. Use /help."
    assert source.calls == []


@pytest.mark.parametrize(
    "text,usage",
    [
        ("/agent_status extra", "/agent_status"),
        ("/agent_tasks open", "/agent_tasks"),
        ("/agent_task", "/agent_task TASK_ID"),
        ("/agent_task ../../private", "/agent_task TASK_ID"),
        ("/agent_task one two", "/agent_task TASK_ID"),
        ("/agent_events 50", "/agent_events"),
        ("/journal_verify now", "/journal_verify"),
        ("/agent_privacy all", "/agent_privacy"),
        ("/help please", "/help"),
    ],
)
def test_malformed_command_arguments_return_only_fixed_usage(
    service: TelegramOpsService,
    source: FakeProjectionSource,
    text: str,
    usage: str,
) -> None:
    reply = service.handle_update(telegram_message(abs(hash(text)) % 10_000, text))
    assert reply is not None
    assert reply.text == f"Usage: {usage}"
    assert source.calls == []


@pytest.mark.parametrize(
    "text",
    [
        "/claim tsk_alpha7",
        "/recover tsk_alpha7",
        "/spawn researcher",
        "/publish",
        "/pay",
        "/trade",
        "/buy YES",
        "/sell YES",
    ],
)
def test_mutating_or_external_commands_are_not_exposed_or_dispatched(
    service: TelegramOpsService,
    source: FakeProjectionSource,
    text: str,
) -> None:
    reply = service.handle_update(telegram_message(abs(hash(text)) % 10_000, text))
    assert reply is not None
    assert reply.text == "Unsupported read-only Ops command. Use /help."
    assert text not in reply.text
    assert source.calls == []


def test_missing_task_is_observation_scoped(
    service: TelegramOpsService,
) -> None:
    reply = service.handle_update(
        telegram_message(1, "/agent_task tsk_missing9")
    )
    assert reply is not None
    assert "No safe task projection was found" in reply.text
    assert "does not establish that no task exists" in reply.text


def test_projection_failure_never_leaks_exception_or_path(
    dedupe: MemoryDedupe,
) -> None:
    class BrokenProjection(FakeProjectionSource):
        def status_snapshot(self) -> OpsStatusProjection:
            raise RuntimeError("secret at /Users/operator/private/journal.sqlite")

    service = TelegramOpsService(
        BrokenProjection(),
        dedupe,
        OpsServiceConfig(OPERATOR_ID, OPERATOR_ID),
    )
    reply = service.handle_update(telegram_message(1, "/agent_status"))
    assert reply is not None
    assert "temporarily unavailable" in reply.text
    assert "secret" not in reply.text
    assert "/Users" not in reply.text
    assert "No coordination or external action was performed" in reply.text


def test_mismatched_task_projection_fails_closed(
    source: FakeProjectionSource, dedupe: MemoryDedupe
) -> None:
    class MismatchProjection(FakeProjectionSource):
        def get_task(self, task_id: str) -> SafeTaskProjection | None:
            return self.tasks[1]

    service = TelegramOpsService(
        MismatchProjection(),
        dedupe,
        OpsServiceConfig(OPERATOR_ID, OPERATOR_ID),
    )
    reply = service.handle_update(
        telegram_message(1, "/agent_task tsk_alpha7")
    )
    assert reply is not None
    assert "temporarily unavailable" in reply.text
    assert "tsk_beta8" not in reply.text


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operator_user_id": True, "operator_private_chat_id": 1},
        {"operator_user_id": "1", "operator_private_chat_id": 1},
        {"operator_user_id": 0, "operator_private_chat_id": 0},
        {"operator_user_id": 1, "operator_private_chat_id": 2},
        {"operator_user_id": 1, "operator_private_chat_id": 1, "task_list_limit": 0},
        {"operator_user_id": 1, "operator_private_chat_id": 1, "event_list_limit": 21},
    ],
)
def test_operator_configuration_requires_exact_numeric_private_pair(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        OpsServiceConfig(**kwargs)  # type: ignore[arg-type]


def test_operator_ids_are_redacted_from_config_repr() -> None:
    config = OpsServiceConfig(OPERATOR_ID, OPERATOR_ID)
    rendered = repr(config)
    assert str(OPERATOR_ID) not in rendered
    assert "<configured>" in rendered


@pytest.mark.parametrize(
    "factory",
    [
        lambda: SafeTaskProjection(
            task_id="tsk_one",
            state="open",
            version=1,
            summary="unsafe\nsecond line",
        ),
        lambda: SafeEventProjection(
            event_id="evt_one",
            kind="task.created",
            observed_at="2026-09-03T20:00:00Z",
            summary="spoof\u202estatus",
        ),
        lambda: SafeTaskProjection(
            task_id="../journal",
            state="open",
            version=1,
        ),
    ],
)
def test_safe_projection_values_reject_control_and_format_injection(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()  # type: ignore[operator]


def test_non_boolean_dedupe_result_fails_closed(
    source: FakeProjectionSource,
) -> None:
    class InvalidDedupe:
        def claim_update(self, update_id: int) -> bool:
            return 1  # type: ignore[return-value]

    service = TelegramOpsService(
        source,
        InvalidDedupe(),
        OpsServiceConfig(OPERATOR_ID, OPERATOR_ID),
    )
    with pytest.raises(TypeError, match="must return a boolean"):
        service.handle_update(telegram_message(1, "/help"))


def test_unknown_or_plain_text_never_echoes_user_input(
    service: TelegramOpsService,
) -> None:
    unknown = service.handle_update(
        telegram_message(1, "/unknown secret-prompt-content")
    )
    plain = service.handle_update(
        telegram_message(2, "secret-prompt-content")
    )
    assert unknown is not None and plain is not None
    assert "secret-prompt-content" not in unknown.text
    assert "secret-prompt-content" not in plain.text


def test_render_update_has_no_claim_and_start_is_help_without_consent(
    service: TelegramOpsService, source: FakeProjectionSource, dedupe: MemoryDedupe,
) -> None:
    start = service.render_update(telegram_message(1, "/start"))
    help_reply = service.render_update(telegram_message(1, "/help"))
    assert start is not None and help_reply is not None
    assert start.text == help_reply.text
    assert source.calls == [] and dedupe.calls == [] and dedupe.seen == set()
    assert service.handle_update(telegram_message(1, "/start")) == start
    assert dedupe.calls == [1]


@pytest.mark.parametrize("text", ["/agent_task RAW_PRIVATE_SENTINEL", "/start RAW_PRIVATE_SENTINEL"])
def test_missing_reference_and_start_arguments_never_echo_input(
    service: TelegramOpsService, text: str,
) -> None:
    reply = service.render_update(telegram_message(1, text))
    assert reply is not None and "RAW_PRIVATE_SENTINEL" not in reply.text


def test_render_authorization_is_identical_without_persisting_rejected_ids(
    service: TelegramOpsService, source: FakeProjectionSource, dedupe: MemoryDedupe,
) -> None:
    for update in (
        telegram_message(1, "/help", user_id=OPERATOR_ID + 1),
        telegram_message(2, "/help", is_bot=True),
        telegram_message(3, "/agent_status", chat_type="group"),
        {"update_id": True},
    ):
        assert service.render_update(update) is None
    assert dedupe.calls == [] and source.calls == []


def test_render_update_never_claims_and_can_be_replayed(
    service: TelegramOpsService, source: FakeProjectionSource, dedupe: MemoryDedupe,
) -> None:
    update = telegram_message(70, "/agent_status")
    first, second = service.render_update(update), service.render_update(update)
    assert first == second
    assert first is not None
    assert source.calls == ["status", "status"]
    assert dedupe.calls == []
    assert dedupe.seen == set()


def test_start_is_help_only_not_enrollment(
    service: TelegramOpsService, source: FakeProjectionSource, dedupe: MemoryDedupe,
) -> None:
    start = service.render_update(telegram_message(71, "/start"))
    help_reply = service.render_update(telegram_message(72, "/help"))
    assert start is not None and help_reply is not None
    assert start.text == help_reply.text
    assert service.render_update(telegram_message(73, "/start private-token")).text == "Usage: /start"
    assert source.calls == dedupe.calls == []


@pytest.mark.parametrize("text", ["/agent_task PRIVATE_SENTINEL_abcdef", "/start private-sentinel"])
def test_render_does_not_echo_unknown_reference_or_start_payload(
    service: TelegramOpsService, text: str,
) -> None:
    reply = service.render_update(telegram_message(74, text))
    assert reply is not None
    assert "SENTINEL" not in reply.text and "private-sentinel" not in reply.text


@pytest.mark.parametrize("update", [
    {}, {"update_id": True}, {"update_id": 1, "message": {}},
    telegram_message(2, "/help", is_bot=True),
    telegram_message(3, "/help", chat_type="group"),
    telegram_message(4, "/help", user_id=OPERATOR_ID + 1),
])
def test_pure_render_keeps_silent_authorization_without_claim(
    service: TelegramOpsService, dedupe: MemoryDedupe, update: dict[str, object],
) -> None:
    assert service.render_update(update) is None
    assert dedupe.calls == []


BOUND_AT = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _bound_service(store: AgentToolOpsStore) -> TelegramOpsService:
    store.bind_operator(
        1234567, TELEGRAM_PRODUCTION_ORIGIN,
        operator_user_id=OPERATOR_ID, operator_private_chat_id=OPERATOR_ID,
        credential_ref="fixture:ops-test", source_binding="fixture:source",
        verification="fixture", bound_at=BOUND_AT,
    )
    return TelegramOpsService(store, store, OpsServiceConfig(OPERATOR_ID, OPERATOR_ID))


def _dated_update(update_id: int, text: str = "/help", *, seconds: int = 10) -> dict[str, object]:
    update = telegram_message(update_id, text)
    update["message"]["date"] = int(BOUND_AT.timestamp()) + seconds
    return update


@pytest.fixture
def atomic_service(tmp_path: Path):
    with AgentToolOpsStore(tmp_path / "atomic-private" / "ops.db") as store:
        yield store, _bound_service(store)


def test_atomic_reply_and_disposition_survive_reopen_and_duplicate_does_not_render(
    atomic_service, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, service = atomic_service
    staged = store.process_update_once(_dated_update(20), service, polling_epoch=1,
                                      processed_at=BOUND_AT + timedelta(seconds=10))
    item = store.reply_item(staged.reply_id)
    assert item.state == "pending" and item.attempt_count == 0
    assert store.poll_state().next_offset == 21
    assert store.conn.execute("SELECT COUNT(*) FROM telegram_updates").fetchone()[0] == 0

    def must_not_render(*args):
        pytest.fail("duplicate was rerendered")

    monkeypatch.setattr(TelegramOpsService, "render_update", must_not_render)
    with AgentToolOpsStore(store.path) as reopened:
        replay = reopened.process_update_once(
            _dated_update(20, "/unknown DIFFERENT_PRIVATE_BODY"),
            _bound_service(reopened), polling_epoch=1,
        )
        assert replay.duplicate and replay.reply_id == staged.reply_id
        assert reopened.reply_item(replay.reply_id) == item
        assert "DIFFERENT_PRIVATE_BODY" not in "\n".join(reopened.conn.iterdump())


@pytest.mark.parametrize("failure_point", ["render", "persist"])
def test_atomic_render_or_persistence_crash_rolls_back_claim_reply_and_offset(
    atomic_service, monkeypatch: pytest.MonkeyPatch, failure_point: str,
) -> None:
    store, service = atomic_service
    before = store.poll_state()

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt("PRIVATE_PROVIDER_ERROR_SENTINEL")

    with monkeypatch.context() as patch:
        if failure_point == "render":
            patch.setattr(TelegramOpsService, "render_update", interrupted)
        else:
            patch.setattr(AgentToolOpsStore, "_reply_digest", staticmethod(interrupted))
        with pytest.raises(KeyboardInterrupt):
            store.process_update_once(_dated_update(31), service, polling_epoch=1)
    assert store.poll_state() == before
    assert store.list_replies() == ()
    assert store.conn.execute("SELECT COUNT(*) FROM ops_update_dispositions").fetchone()[0] == 0
    assert "PRIVATE_PROVIDER_ERROR_SENTINEL" not in "\n".join(store.conn.iterdump())
    assert store.process_update_once(_dated_update(31), service, polling_epoch=1).duplicate is False


def test_atomic_projection_exception_persists_only_fixed_unavailable_reply(
    atomic_service, monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, service = atomic_service

    def broken(*args):
        raise RuntimeError("RAW_REPORT_SENTINEL /private/provider/body")

    monkeypatch.setattr(AgentToolOpsStore, "status_snapshot", broken)
    result = store.process_update_once(_dated_update(32, "/agent_status"), service, polling_epoch=1)
    assert "temporarily unavailable" in store.reply_item(result.reply_id).text
    dump = "\n".join(store.conn.iterdump())
    for private in ("RAW_REPORT_SENTINEL", "/private/provider/body", "/agent_status"):
        assert private not in dump


@pytest.mark.parametrize("mutation", ["bot", "group", "other-user", "missing-message", "missing-date"])
def test_atomic_ignored_disposition_dedupes_without_disclosure(atomic_service, mutation: str) -> None:
    store, service = atomic_service
    update = _dated_update(40, "PRIVATE_INCOMING_BODY")
    if mutation == "bot":
        update["message"]["from"]["is_bot"] = True
    elif mutation == "group":
        update["message"]["chat"]["type"] = "group"
    elif mutation == "other-user":
        update["message"]["from"]["id"] = OPERATOR_ID + 1
    elif mutation == "missing-message":
        del update["message"]
    else:
        del update["message"]["date"]
    result = store.process_update_once(update, service, polling_epoch=1)
    assert result.disposition == "ignored" and result.reply_id is None
    assert store.process_update_once(_dated_update(40), service, polling_epoch=1).duplicate
    assert store.list_replies() == ()
    assert store.poll_state().next_offset == 41
    assert "PRIVATE_INCOMING_BODY" not in "\n".join(store.conn.iterdump())


def test_legacy_claim_gap_remains_offline_without_fabricated_reply(tmp_path: Path) -> None:
    with AgentToolOpsStore(tmp_path / "legacy-private" / "ops.db") as store:
        assert store.claim_update(51)
        before = "\n".join(store.conn.iterdump())
        with pytest.raises(BindingStateError, match="pristine"):
            _bound_service(store)
        assert store.binding() is None and store.poll_state() is None
        assert store.list_replies() == ()
        assert "\n".join(store.conn.iterdump()) == before
        assert store.conn.execute("SELECT update_id FROM telegram_updates").fetchone()[0] == 51
        with pytest.raises(CursorStateError, match="cursor is initialized"):
            store.status_snapshot()
        assert store.claim_update(51) is False


def test_bound_service_rejects_legacy_claim_only_handling(atomic_service) -> None:
    store, service = atomic_service
    with pytest.raises(BindingStateError, match="atomic"):
        service.handle_update(_dated_update(52))
    assert store.process_update_once(_dated_update(52), service, polling_epoch=1).reply_id


def test_atomic_path_rejects_wrong_projection_connection_or_service_pair(atomic_service) -> None:
    store, service = atomic_service
    wrong_pair = TelegramOpsService(store, store, OpsServiceConfig(OPERATOR_ID + 1, OPERATOR_ID + 1))
    with pytest.raises(BindingStateError, match="recipient"):
        store.process_update_once(_dated_update(61), wrong_pair, polling_epoch=1)
    wrong_source = TelegramOpsService(FakeProjectionSource(), store, service.config)
    with pytest.raises(ValueError, match="local projection"):
        store.process_update_once(_dated_update(61), wrong_source, polling_epoch=1)
    assert store.list_replies() == ()
    assert store.poll_state().next_offset is None


def test_atomic_same_update_concurrent_connections_render_once(tmp_path: Path) -> None:
    path = tmp_path / "concurrent-private" / "ops.db"
    with AgentToolOpsStore(path) as initial:
        _bound_service(initial)
    barrier = Barrier(2)

    def process():
        with AgentToolOpsStore(path) as store:
            service = _bound_service(store)
            barrier.wait(timeout=5)
            return store.process_update_once(_dated_update(71), service, polling_epoch=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: process(), range(2)))
    assert sorted(result.duplicate for result in results) == [False, True]
    assert len({result.reply_id for result in results}) == 1
    with AgentToolOpsStore(path) as reopened:
        assert len(reopened.list_replies()) == 1
        assert reopened.poll_state().next_offset == 72


def test_poll_epoch_reset_precedes_random_lower_or_reused_id_and_fences_old_batch(atomic_service) -> None:
    store, service = atomic_service
    high = store.process_update_once(_dated_update(900), service, polling_epoch=1,
                                    processed_at=BOUND_AT + timedelta(seconds=10))
    assert store.prepare_poll(now=BOUND_AT + timedelta(hours=23)).next_offset == 901
    reset = store.prepare_poll(now=BOUND_AT + timedelta(days=8))
    assert reset.epoch == 2 and reset.next_offset is None
    with pytest.raises(CursorStateError, match="stale"):
        store.process_update_once(_dated_update(2, seconds=700000), service, polling_epoch=1)
    low = store.process_update_once(_dated_update(2, seconds=700000), service, polling_epoch=2)
    reused = store.process_update_once(_dated_update(900, seconds=700001), service, polling_epoch=2)
    assert low.reply_id and reused.reply_id != high.reply_id
    assert store.poll_state().next_offset == 901


def test_out_of_order_id_is_not_max_deduped_and_duplicate_can_acknowledge(atomic_service) -> None:
    store, service = atomic_service
    store.process_update_once(_dated_update(90), service, polling_epoch=1)
    older = store.process_update_once(_dated_update(5), service, polling_epoch=1)
    assert older.reply_id and store.poll_state().next_offset == 6
    assert store.process_update_once(_dated_update(90), service, polling_epoch=1).duplicate
    assert store.poll_state().next_offset == 91


def test_pause_invalidates_old_replies_and_resume_rejects_provider_backlog(atomic_service) -> None:
    store, service = atomic_service
    pending = store.process_update_once(_dated_update(101), service, polling_epoch=1,
                                        processed_at=BOUND_AT + timedelta(seconds=10))
    inflight = store.process_update_once(_dated_update(102), service, polling_epoch=1,
                                         processed_at=BOUND_AT + timedelta(seconds=11))
    preview = store.reply_item(inflight.reply_id)
    attempt = store.claim_reply(preview.reply_id, payload_digest=preview.payload_digest,
                                binding_revision=preview.binding_revision)
    assert store.pause(paused_at=BOUND_AT + timedelta(seconds=20)).state == "paused"
    assert store.reply_item(pending.reply_id).state == "invalidated"
    assert store.reply_item(inflight.reply_id).state == "unknown"
    for operation in (
        lambda: store.prepare_poll(),
        lambda: store.process_update_once(_dated_update(103), service, polling_epoch=1),
        lambda: store.claim_reply(preview.reply_id, payload_digest=preview.payload_digest, binding_revision=1),
    ):
        with pytest.raises(BindingStateError, match="paused"):
            operation()
    with pytest.raises(DeliveryStateError, match="inflight"):
        store.finish_reply(preview.reply_id, attempt_count=attempt.attempt_count,
                           state="sent", receipt_ref="telegram:123")
    resumed = store.resume(resumed_at=BOUND_AT + timedelta(seconds=30))
    assert resumed.revision == 2 and store.poll_state().epoch == 2
    replay = store.process_update_once(_dated_update(101), service, polling_epoch=2,
                                       processed_at=BOUND_AT + timedelta(seconds=31))
    assert replay.duplicate and replay.reply_id == pending.reply_id
    assert store.reply_item(replay.reply_id).state == "invalidated"
    for update_id, seconds in ((103, 25), (104, 30)):
        result = store.process_update_once(_dated_update(update_id, seconds=seconds), service,
                                           polling_epoch=2, processed_at=BOUND_AT + timedelta(seconds=31))
        assert result.disposition == "withdrawn" and result.reply_id is None
    assert store.process_update_once(_dated_update(105, seconds=31), service, polling_epoch=2,
                                     processed_at=BOUND_AT + timedelta(seconds=32)).reply_id
    assert store.reply_item(pending.reply_id).binding_revision == 1
    assert store.reply_item(pending.reply_id).state == "invalidated"
