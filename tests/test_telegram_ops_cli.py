from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from telegram_gateway import cli
from telegram_gateway import agenttool_mcp
from telegram_gateway import bootstrap, ops_runtime, telegram_api


@pytest.fixture(autouse=True)
def _no_live_ops_side_effects(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("offline CLI test reached credentials or real transport")
    monkeypatch.setattr(ops_runtime, "load_keychain_token", forbidden)
    monkeypatch.setattr(bootstrap, "load_keychain_token", forbidden)
    monkeypatch.setattr(telegram_api, "open_request", forbidden)
    monkeypatch.setattr(ops_runtime, "DEFAULT_LOCK_DIRECTORY", tmp_path / "ops-locks")

from telegram_gateway.agenttool_mcp import (
    CollabEvent,
    EventPage,
    JournalVerification,
    WorkspaceStatus,
)
from telegram_gateway.agenttool_ops import (
    AgentToolOpsStore,
    CursorAnchor,
    CursorStateError,
)
from telegram_gateway.bootstrap import OPS_BOT_NAME, OPS_BOT_PROFILE, desired_commands


def test_ops_profile_parser_is_opt_in() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(
        ["bot-plan", "--bot-username", "KingdomOpsBot"]
    ).profile == "research"
    assert parser.parse_args(
        [
            "bot-configure",
            "--bot-username",
            "KingdomOpsBot",
            "--profile",
            "ops",
        ]
    ).profile == "ops"


def test_ops_plan_cli_is_offline(capsys: object) -> None:
    assert (
        cli.main(
            [
                "bot-plan",
                "--bot-username",
                "KingdomOpsBot",
                "--profile",
                "ops",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert output["profile"] == "ops"
    assert output["bot_name"] == OPS_BOT_NAME
    assert output["botfather_opened"] is False
    assert output["public_profile"]["commands"] == desired_commands(OPS_BOT_PROFILE)


def test_ops_configuration_preview_reads_no_credential(capsys: object) -> None:
    assert (
        cli.main(
            [
                "bot-configure",
                "--bot-username",
                "KingdomOpsBot",
                "--profile",
                "ops",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert output == {
        "apply": False,
        "bot_name": OPS_BOT_NAME,
        "bot_username": "KingdomOpsBot",
        "commands": desired_commands(OPS_BOT_PROFILE),
        "keychain_account": "kingdomopsbot",
        "keychain_service": "dev.kingdom.prediction-markets.telegram-ops-bot-token",
        "network_calls": 0,
        "note": "Bind the dedicated Ops database with ops-bind --apply; then repeat with --source-binding and --apply",
        "profile": "ops",
    }


@pytest.mark.parametrize(
    "argv",
    [
        [
            "bot-doctor",
            "--bot-username",
            "KingdomOpsBot",
            "--profile",
            "ops",
        ],
        [
            "bot-configure",
            "--bot-username",
            "KingdomOpsBot",
            "--profile",
            "ops",
            "--apply",
        ],
    ],
)
def test_live_ops_bot_setup_fails_before_credential_or_gateway_store_access(
    argv: list[str],
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_token(**_kwargs: object) -> str:
        pytest.fail("an Ops credential was read before the unsupported path failed")

    class ForbiddenGatewayStore:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pytest.fail("the Research GatewayStore was opened for an Ops bot")

    monkeypatch.setattr(cli, "resolve_token", forbidden_token)
    monkeypatch.setattr(cli, "GatewayStore", ForbiddenGatewayStore)
    assert cli.main(argv) == 1
    error = capsys.readouterr().err  # type: ignore[attr-defined]
    assert json.loads(error)["error_code"] == "invalid_input_or_state"
    assert "KingdomOpsBot" not in error


def test_ops_init_and_status_are_offline_and_owner_only(
    tmp_path: Path, capsys: object
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    argv = ["--db", str(ops_db), "ops-init"]
    assert cli.main(argv) == 0
    initialized = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]

    assert initialized["projection_schema_initialized"] is True
    assert initialized["database_file_preexisted"] is False
    assert initialized["database_role"] == "separate_owner_only_ops_projection"
    assert initialized["cursor"] == {
        "committed_sequence": None,
        "initialized": False,
        "staged_page_pending": False,
    }
    assert initialized["projection"] is None
    assert initialized["projection_state"] == "not_observed"
    assert initialized["agenttool_calls"] == 0
    assert initialized["telegram_calls"] == 0
    assert initialized["coordination_mutations"] == 0
    assert initialized["trades"] == 0
    assert str(ops_db) not in json.dumps(initialized)
    assert stat.S_IMODE(ops_db.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(ops_db.stat().st_mode) == 0o600

    assert cli.main(["--db", str(ops_db), "ops-status"]) == 0
    inspected = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert inspected["database_file_preexisted"] is True
    assert inspected["projection"] is None
    assert inspected["projection_state"] == "not_observed"
    assert inspected["agenttool_calls"] == 0
    assert inspected["telegram_calls"] == 0


def test_ops_commands_refuse_the_research_database(capsys: object) -> None:
    assert cli.main(["ops-init"]) == 1
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "requires a separate database" in captured.err


def test_ops_status_does_not_create_a_missing_database(
    tmp_path: Path, capsys: object
) -> None:
    missing = tmp_path / "private-ops" / "missing.sqlite3"
    assert cli.main(["--db", str(missing), "ops-status"]) == 1
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "run ops-init first" in captured.err
    assert not missing.exists()


def test_ops_permission_failure_does_not_print_the_private_path(
    tmp_path: Path, capsys: object
) -> None:
    parent = tmp_path / "private-operator-name"
    parent.mkdir()
    parent.chmod(0o755)
    ops_db = parent / "ops.sqlite3"

    assert cli.main(["--db", str(ops_db), "ops-init"]) == 1
    error = capsys.readouterr().err  # type: ignore[attr-defined]
    assert "owner-only permission check" in error
    assert str(ops_db) not in error
    assert str(parent) not in error


def _status(head: CursorAnchor) -> WorkspaceStatus:
    return WorkspaceStatus(
        head=head,
        open_tasks=2,
        claimed_tasks=1,
        blocked_tasks=0,
        completed_tasks=3,
        pending_review_tasks=1,
        active_session_records=1,
    )


def test_ops_watch_previews_then_seeds_without_historical_replay(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    collab_db = tmp_path / "private-source" / "collab.sqlite"
    head = CursorAnchor("epoch_cli", 5, "5" * 64)
    assert cli.main(["--db", str(ops_db), "ops-init"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    configs: list[object] = []

    class PreviewReader:
        def __init__(self, config: object) -> None:
            configs.append(config)

        def verify_journal(self) -> JournalVerification:
            return JournalVerification(head=head)

        def workspace_status(self) -> WorkspaceStatus:
            return _status(head)

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", PreviewReader)
    base = [
        "--db",
        str(ops_db),
        "ops-watch-once",
        "--workspace-id",
        "ws_cli",
        "--collab-db",
        str(collab_db),
    ]
    assert cli.main(base) == 0
    preview = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert preview["action"] == "preview_only_unseeded"
    assert preview["events_observed"] == 0
    assert preview["local"]["cursor"]["initialized"] is False
    assert "historical replay is not automatic" in preview["next_step"]
    assert str(ops_db) not in json.dumps(preview)
    assert str(collab_db) not in json.dumps(preview)

    assert cli.main([*base, "--seed-current-head"]) == 0
    seeded = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert seeded["action"] == "seeded_verified_current_head"
    assert seeded["events_observed"] == 0
    assert seeded["events_enqueued"] == 0
    assert seeded["local"]["cursor"] == {
        "committed_sequence": 5,
        "initialized": True,
        "staged_page_pending": False,
    }
    assert seeded["local"]["outbox_counts"]["pending"] == 0
    assert seeded["collab_session_created"] is False
    assert seeded["collab_cursor_acknowledged"] is False
    assert seeded["telegram_calls"] == 0
    assert seeded["coordination_mutations"] == 0
    assert all(getattr(config, "enabled") is True for config in configs)


def test_ops_watch_does_not_seed_a_head_that_advanced_after_verification(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    collab_db = tmp_path / "private-source" / "collab.sqlite"
    verified = CursorAnchor("epoch_cli", 5, "5" * 64)
    advanced = CursorAnchor("epoch_cli", 6, "6" * 64)
    assert cli.main(["--db", str(ops_db), "ops-init"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    class AdvancedReader:
        def __init__(self, _config: object) -> None:
            pass

        def verify_journal(self) -> JournalVerification:
            return JournalVerification(head=verified)

        def workspace_status(self) -> WorkspaceStatus:
            return _status(advanced)

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", AdvancedReader)
    assert (
        cli.main(
            [
                "--db",
                str(ops_db),
                "ops-watch-once",
                "--workspace-id",
                "ws_cli",
                "--collab-db",
                str(collab_db),
                "--seed-current-head",
            ]
        )
        == 1
    )
    assert "no source cursor was seeded" in capsys.readouterr().err  # type: ignore[attr-defined]
    with AgentToolOpsStore(ops_db) as store:
        assert store.committed_anchor() is None
        assert store.staged_anchor() is None


def test_ops_watch_ingests_one_sanitized_page_without_sending(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    collab_db = tmp_path / "private-source" / "collab.sqlite"
    initial = CursorAnchor("epoch_cli", 5, "5" * 64)
    terminal = CursorAnchor("epoch_cli", 6, "6" * 64)
    assert cli.main(["--db", str(ops_db), "ops-init"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    class SeedReader:
        def __init__(self, _config: object) -> None:
            pass

        def verify_journal(self) -> JournalVerification:
            return JournalVerification(head=initial)

        def workspace_status(self) -> WorkspaceStatus:
            return _status(initial)

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", SeedReader)
    base = [
        "--db",
        str(ops_db),
        "ops-watch-once",
        "--workspace-id",
        "ws_cli",
        "--collab-db",
        str(collab_db),
    ]
    assert cli.main([*base, "--seed-current-head"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    raw_task_id = "task_private_cli"

    class PageReader:
        def __init__(self, _config: object) -> None:
            pass

        def verify_journal(self) -> JournalVerification:
            return JournalVerification(head=terminal)

        def events_since(self, anchor: CursorAnchor, *, limit: int) -> EventPage:
            assert anchor == initial
            assert limit == 50
            event = CollabEvent(
                protocol="agenttool.collab/0.2",
                epoch_id=anchor.epoch_id,
                sequence=6,
                kind="task.created",
                subject_id=raw_task_id,
                occurred_at="2026-09-03T20:00:00.000000Z",
                previous_hash=anchor.hash,
                hash=terminal.hash,
                observed_version=1,
            )
            return EventPage(
                current_anchor=anchor,
                next_anchor=terminal,
                head_anchor=terminal,
                events=(event,),
                has_more=False,
            )

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", PageReader)
    assert cli.main(base) == 0
    observed = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    serialized = json.dumps(observed, sort_keys=True)
    assert observed["action"] == "observed_one_page"
    assert observed["events_observed"] == 1
    assert observed["events_enqueued"] == 1
    assert observed["committed_sequence"] == 6
    assert observed["local"]["projection"]["open_tasks"] == 1
    assert observed["local"]["outbox_counts"]["pending"] == 1
    assert observed["telegram_calls"] == 0
    assert observed["agent_lifecycle_actions"] == 0
    assert observed["coordination_mutations"] == 0
    assert observed["trades"] == 0
    assert raw_task_id not in serialized


def test_ops_watch_does_not_publish_a_recovered_stage_when_full_chain_is_invalid(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    collab_db = tmp_path / "private-source" / "collab.sqlite"
    initial = CursorAnchor("epoch_cli", 5, "5" * 64)
    terminal = CursorAnchor("epoch_cli", 6, "6" * 64)
    with AgentToolOpsStore(ops_db) as store:
        event = CollabEvent(
            protocol="agenttool.collab/0.2",
            epoch_id=initial.epoch_id,
            sequence=6,
            kind="task.created",
            subject_id="task_private_recovery",
            occurred_at="2026-09-03T20:00:00.000000Z",
            previous_hash=initial.hash,
            hash=terminal.hash,
            observed_version=1,
        )
        staged = store.stage_page(
            current_anchor=initial,
            next_anchor=terminal,
            events=(event.projection_input(),),
        )
        assert staged.state == "staged"

    class InvalidReader:
        def __init__(self, _config: object) -> None:
            pass

        def verify_journal(self) -> JournalVerification:
            return JournalVerification(head=terminal, chain_valid=False)

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", InvalidReader)
    assert (
        cli.main(
            [
                "--db",
                str(ops_db),
                "ops-watch-once",
                "--workspace-id",
                "ws_cli",
                "--collab-db",
                str(collab_db),
            ]
        )
        == 1
    )
    error = capsys.readouterr().err  # type: ignore[attr-defined]
    assert "hash chain was invalid" in error
    assert str(ops_db) not in error
    assert str(collab_db) not in error

    with AgentToolOpsStore(ops_db) as store:
        assert store.committed_anchor() == initial
        assert store.staged_anchor() == terminal
        with pytest.raises(CursorStateError):
            store.list_tasks(limit=10)


def test_ops_watch_records_an_invalid_full_chain_without_initializing_cursor(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    collab_db = tmp_path / "private-source" / "collab.sqlite"
    head = CursorAnchor("epoch_cli", 9, "9" * 64)
    assert cli.main(["--db", str(ops_db), "ops-init"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    class InvalidReader:
        def __init__(self, _config: object) -> None:
            pass

        def verify_journal(self) -> JournalVerification:
            return JournalVerification(head=head, chain_valid=False)

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", InvalidReader)
    base = [
        "--db",
        str(ops_db),
        "ops-watch-once",
        "--workspace-id",
        "ws_cli",
        "--collab-db",
        str(collab_db),
    ]
    assert cli.main(base) == 1
    assert "hash chain was invalid" in capsys.readouterr().err  # type: ignore[attr-defined]

    assert cli.main(["--db", str(ops_db), "ops-status"]) == 0
    status = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert status["cursor"]["initialized"] is False
    assert status["projection_state"] == "not_observed"
    assert status["journal_verification"]["outcome"] == "invalid"
    assert status["journal_verification"]["journal_head_sequence"] == 9


def test_ops_watch_rejects_a_page_from_a_head_newer_than_full_verification(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    collab_db = tmp_path / "private-source" / "collab.sqlite"
    initial = CursorAnchor("epoch_cli", 5, "5" * 64)
    verified = CursorAnchor("epoch_cli", 6, "6" * 64)
    newer = CursorAnchor("epoch_cli", 7, "7" * 64)
    with AgentToolOpsStore(ops_db) as store:
        store.stage_page(current_anchor=initial, next_anchor=initial, events=())

    class AdvancedReader:
        def __init__(self, _config: object) -> None:
            pass

        def verify_journal(self) -> JournalVerification:
            return JournalVerification(head=verified)

        def events_since(self, anchor: CursorAnchor, *, limit: int) -> EventPage:
            assert anchor == initial
            assert limit == 50
            event = CollabEvent(
                protocol="agenttool.collab/0.2",
                epoch_id=initial.epoch_id,
                sequence=6,
                kind="task.created",
                subject_id="task_after_audit",
                occurred_at="2026-09-03T20:00:00.000000Z",
                previous_hash=initial.hash,
                hash=verified.hash,
                observed_version=1,
            )
            return EventPage(
                current_anchor=initial,
                next_anchor=verified,
                head_anchor=newer,
                events=(event,),
                has_more=True,
            )

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", AdvancedReader)
    assert (
        cli.main(
            [
                "--db",
                str(ops_db),
                "ops-watch-once",
                "--workspace-id",
                "ws_cli",
                "--collab-db",
                str(collab_db),
            ]
        )
        == 1
    )
    assert "changed after full verification" in capsys.readouterr().err  # type: ignore[attr-defined]
    with AgentToolOpsStore(ops_db) as store:
        assert store.committed_anchor() == initial
        assert store.staged_anchor() is None
        assert store.list_tasks(limit=10) == ()


def test_ops_watch_revalidates_an_exact_staged_page_before_recovery(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    collab_db = tmp_path / "private-source" / "collab.sqlite"
    initial = CursorAnchor("epoch_cli", 5, "5" * 64)
    terminal = CursorAnchor("epoch_cli", 6, "6" * 64)
    event = CollabEvent(
        protocol="agenttool.collab/0.2",
        epoch_id=initial.epoch_id,
        sequence=6,
        kind="task.created",
        subject_id="task_private_recovery",
        occurred_at="2026-09-03T20:00:00.000000Z",
        previous_hash=initial.hash,
        hash=terminal.hash,
        observed_version=1,
    )
    with AgentToolOpsStore(ops_db) as store:
        store.stage_page(
            current_anchor=initial,
            next_anchor=terminal,
            events=(event.projection_input(),),
        )

    calls: list[tuple[CursorAnchor, int]] = []

    class RecoveryReader:
        def __init__(self, _config: object) -> None:
            pass

        def verify_journal(self) -> JournalVerification:
            return JournalVerification(head=terminal)

        def events_since(self, anchor: CursorAnchor, *, limit: int) -> EventPage:
            calls.append((anchor, limit))
            if anchor == initial:
                return EventPage(
                    current_anchor=initial,
                    next_anchor=terminal,
                    head_anchor=terminal,
                    events=(event,),
                    has_more=False,
                )
            assert anchor == terminal
            return EventPage(
                current_anchor=terminal,
                next_anchor=terminal,
                head_anchor=terminal,
                events=(),
                has_more=False,
            )

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", RecoveryReader)
    assert (
        cli.main(
            [
                "--db",
                str(ops_db),
                "ops-watch-once",
                "--workspace-id",
                "ws_cli",
                "--collab-db",
                str(collab_db),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert output["recovered_staged_page"] is True
    assert output["action"] == "recovered_exact_staged_page"
    assert output["events_observed"] == 1
    assert output["events_enqueued"] == 0
    assert output["committed_sequence"] == 6
    assert calls == [(initial, 1)]


def test_ops_watch_keeps_a_staged_page_when_source_anchor_no_longer_matches(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    collab_db = tmp_path / "private-source" / "collab.sqlite"
    initial = CursorAnchor("epoch_cli", 5, "5" * 64)
    staged_anchor = CursorAnchor("epoch_cli", 6, "6" * 64)
    source_anchor = CursorAnchor("epoch_cli", 6, "a" * 64)
    staged_event = CollabEvent(
        protocol="agenttool.collab/0.2",
        epoch_id=initial.epoch_id,
        sequence=6,
        kind="task.created",
        subject_id="task_staged",
        occurred_at="2026-09-03T20:00:00.000000Z",
        previous_hash=initial.hash,
        hash=staged_anchor.hash,
        observed_version=1,
    )
    with AgentToolOpsStore(ops_db) as store:
        store.stage_page(
            current_anchor=initial,
            next_anchor=staged_anchor,
            events=(staged_event.projection_input(),),
        )

    class ForkedReader:
        def __init__(self, _config: object) -> None:
            pass

        def verify_journal(self) -> JournalVerification:
            return JournalVerification(head=source_anchor)

        def events_since(self, anchor: CursorAnchor, *, limit: int) -> EventPage:
            assert anchor == initial
            assert limit == 1
            source_event = CollabEvent(
                protocol="agenttool.collab/0.2",
                epoch_id=initial.epoch_id,
                sequence=6,
                kind="task.created",
                subject_id="task_source",
                occurred_at="2026-09-03T20:00:00.000000Z",
                previous_hash=initial.hash,
                hash=source_anchor.hash,
                observed_version=1,
            )
            return EventPage(
                current_anchor=initial,
                next_anchor=source_anchor,
                head_anchor=source_anchor,
                events=(source_event,),
                has_more=False,
            )

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", ForkedReader)
    assert (
        cli.main(
            [
                "--db",
                str(ops_db),
                "ops-watch-once",
                "--workspace-id",
                "ws_cli",
                "--collab-db",
                str(collab_db),
            ]
        )
        == 1
    )
    assert "no longer matches its source anchor" in capsys.readouterr().err  # type: ignore[attr-defined]
    with AgentToolOpsStore(ops_db) as store:
        assert store.committed_anchor() == initial
        assert store.staged_anchor() == staged_anchor


def test_ops_watch_missing_store_creates_no_database_or_mcp_reader(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "private-ops" / "ops.sqlite3"
    source = tmp_path / "private-source" / "collab.sqlite"

    class ForbiddenReader:
        def __init__(self, _config: object) -> None:
            pytest.fail("MCP reader was created before the Ops store preflight")

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", ForbiddenReader)
    assert (
        cli.main(
            [
                "--db",
                str(missing),
                "ops-watch-once",
                "--workspace-id",
                "ws_cli",
                "--collab-db",
                str(source),
            ]
        )
        == 1
    )
    assert "run ops-init first" in capsys.readouterr().err  # type: ignore[attr-defined]
    assert not missing.exists()
    assert not source.exists()


def test_ops_watch_rejects_using_the_ops_store_as_the_collab_source(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    assert cli.main(["--db", str(ops_db), "ops-init"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]

    class ForbiddenReader:
        def __init__(self, _config: object) -> None:
            pytest.fail("MCP reader was created for the Ops projection database")

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", ForbiddenReader)
    assert (
        cli.main(
            [
                "--db",
                str(ops_db),
                "ops-watch-once",
                "--workspace-id",
                "ws_cli",
                "--collab-db",
                str(ops_db),
            ]
        )
        == 1
    )
    error = capsys.readouterr().err  # type: ignore[attr-defined]
    assert "separate AgentTool journal" in error
    assert str(ops_db) not in error


def test_ops_watch_rejects_a_hardlink_to_the_ops_store_as_collab_source(
    tmp_path: Path,
    capsys: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ops_db = tmp_path / "private-ops" / "ops.sqlite3"
    alias = ops_db.with_name("collab-alias.sqlite3")
    assert cli.main(["--db", str(ops_db), "ops-init"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]
    os.link(ops_db, alias)

    class ForbiddenReader:
        def __init__(self, _config: object) -> None:
            pytest.fail("MCP reader was created for a hardlink to the Ops store")

    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", ForbiddenReader)
    assert (
        cli.main(
            [
                "--db",
                str(ops_db),
                "ops-watch-once",
                "--workspace-id",
                "ws_cli",
                "--collab-db",
                str(alias),
            ]
        )
        == 1
    )
    error = capsys.readouterr().err  # type: ignore[attr-defined]
    assert "separate AgentTool journal" in error
    assert str(ops_db) not in error
    assert str(alias) not in error


def _binding_args():
    return ["--bot-username", "KingdomOpsBot", "--bot-id", "8001",
            "--operator-user-id", "77223311", "--operator-private-chat-id", "77223311",
            "--source-binding", "ws_cli"]


def _fake_live_api(monkeypatch):
    from datetime import datetime, timezone
    from telegram_gateway.telegram_api import TelegramError
    calls, reads = [], []
    state = {"send_error": None, "bot_id": 8001, "username": "KingdomOpsBot"}
    def load(username, **kwargs):
        reads.append((username, kwargs))
        return "credential-free-cli-test-placeholder"
    def call(self, method, payload=None, **kwargs):
        payload = payload or {}
        calls.append((method, payload))
        values = {
            "getMe": {"id": state["bot_id"], "is_bot": True, "username": state["username"],
                      "can_join_groups": False, "can_read_all_group_messages": False},
            "getWebhookInfo": {"url": "", "has_custom_certificate": False, "pending_update_count": 0},
            "getMyName": {"name": OPS_BOT_PROFILE.name},
            "getMyDescription": {"description": OPS_BOT_PROFILE.description},
            "getMyShortDescription": {"short_description": OPS_BOT_PROFILE.short_description},
            "getChatMenuButton": {"type": "commands"},
        }
        if method == "getMyCommands":
            return desired_commands(OPS_BOT_PROFILE) if payload.get("scope", {}).get("type") == "all_private_chats" else []
        if method == "getUpdates":
            return [{"update_id": 9, "message": {
                "date": int(datetime.now(timezone.utc).timestamp()) + 2,
                "from": {"id": 77223311, "is_bot": False},
                "chat": {"id": 77223311, "type": "private"}, "text": "/start",
            }}]
        if method == "sendMessage":
            if state["send_error"]:
                raise TelegramError("SECRET_ACCOUNT_PATH_PROVIDER_BODY", ambiguous=True)
            return {"message_id": 42, "chat": {"id": 77223311, "type": "private"}}
        if method.startswith("set") or method == "deleteMyCommands":
            return True
        return values[method]
    monkeypatch.setattr(ops_runtime, "load_keychain_token", load)
    monkeypatch.setattr(telegram_api.TelegramAPI, "call", call)
    return calls, reads, state


def test_bind_preview_and_numeric_mismatch_zero_secret_reads(tmp_path, capsys, monkeypatch):
    path = tmp_path / "ops" / "ops.db"
    with AgentToolOpsStore(path):
        pass
    args = ["--db", str(path), "ops-bind", *_binding_args()]
    assert cli.main(args) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["credential_reads"] == 0 and preview["network_calls"] == 0
    assert "77223311" not in json.dumps(preview)
    calls, reads, state = _fake_live_api(monkeypatch)
    state["bot_id"] = 8002
    assert cli.main([*args, "--apply"]) == 1
    error = capsys.readouterr().err
    assert json.loads(error)["error_code"] == "binding_mismatch"
    assert "8002" not in error
    with AgentToolOpsStore(path) as store:
        assert store.binding() is None
    assert len(reads) == 1 and calls == [("getMe", {})]


def test_cli_binding_setup_poll_preview_exact_send_and_safe_pause(tmp_path, capsys, monkeypatch):
    path = tmp_path / "ops" / "ops.db"
    calls, reads, state = _fake_live_api(monkeypatch)
    class ForbiddenResearch:
        def __init__(self, *args, **kwargs):
            pytest.fail("Ops opened Research state")
    monkeypatch.setattr(cli, "GatewayStore", ForbiddenResearch)
    def forbidden(*args, **kwargs):
        pytest.fail("Ops used shared token resolver")
    monkeypatch.setattr(cli, "resolve_token", forbidden)
    base = ["--db", str(path)]
    assert cli.main([*base, "ops-init"]) == 0
    capsys.readouterr()
    assert cli.main([*base, "ops-bind", *_binding_args(), "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["bound"] is True
    setup = ["--bot-username", "KingdomOpsBot", "--profile", "ops", "--source-binding", "ws_cli"]
    assert cli.main([*base, "bot-doctor", *setup]) == 0
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["bot_api_profile_ready"] is True
    assert "identity" not in doctor and "77223311" not in json.dumps(doctor)
    assert cli.main([*base, "bot-configure", *setup, "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["configuration_attempted"] is True
    live = ["--bot-username", "KingdomOpsBot", "--source-binding", "ws_cli"]
    assert cli.main([*base, "ops-poll-once", *live]) == 0
    poll = json.loads(capsys.readouterr().out)
    assert poll["sends"] == 0 and len(poll["reply_ids"]) == 1
    rid = poll["reply_ids"][0]
    before = len(reads), len(calls)
    assert cli.main([*base, "ops-send-once", "--reply-id", rid]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert (len(reads), len(calls)) == before
    exact = ["--reply-id", rid, "--payload-digest", preview["payload_digest"],
             "--binding-revision", str(preview["binding_revision"])]
    assert cli.main([*base, "ops-send-once", *exact, *live, "--apply"]) == 0
    sent = json.loads(capsys.readouterr().out)
    assert sent["state"] == "sent" and sent["attempt_count"] == 1
    send_calls = [payload for method, payload in calls if method == "sendMessage"]
    assert len(send_calls) == 1
    assert send_calls[0]["chat_id"] == 77223311
    assert send_calls[0]["protect_content"] is True
    assert send_calls[0]["link_preview_options"] == {"is_disabled": True}
    before = len(reads), len(calls)
    assert cli.main([*base, "ops-send-once", *exact, *live, "--apply"]) == 1
    assert json.loads(capsys.readouterr().err)["error_code"] == "reply_not_pending"
    assert cli.main([*base, "ops-pause"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "paused"
    assert cli.main([*base, "ops-pause", "--resume"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "paused"
    assert cli.main([*base, "ops-pause", "--resume", "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["binding_revision"] == 2
    assert (len(reads), len(calls)) == before
    assert all(kwargs["keychain_service"] == bootstrap.OPS_KEYCHAIN_SERVICE for _, kwargs in reads)


def test_cli_unknown_delivery_reconciliation_has_no_provider_calls_or_leaks(tmp_path, capsys, monkeypatch):
    path = tmp_path / "ops" / "ops.db"
    calls, reads, state = _fake_live_api(monkeypatch)
    with AgentToolOpsStore(path):
        pass
    base = ["--db", str(path)]
    assert cli.main([*base, "ops-bind", *_binding_args(), "--apply"]) == 0
    capsys.readouterr()
    live = ["--bot-username", "KingdomOpsBot", "--source-binding", "ws_cli"]
    assert cli.main([*base, "ops-poll-once", *live]) == 0
    rid = json.loads(capsys.readouterr().out)["reply_ids"][0]
    assert cli.main([*base, "ops-send-once", "--reply-id", rid]) == 0
    preview = json.loads(capsys.readouterr().out)
    state["send_error"] = True
    assert cli.main([*base, "ops-send-once", "--reply-id", rid, *live, "--apply",
                     "--payload-digest", preview["payload_digest"], "--binding-revision", "1"]) == 1
    result = capsys.readouterr()
    assert "SECRET_ACCOUNT_PATH_PROVIDER_BODY" not in result.out + result.err
    assert json.loads(result.out)["state"] == "unknown"
    before = len(calls), len(reads)
    assert cli.main([*base, "ops-reconcile", "--reply-id", rid, "--attempt-count", "1",
                     "--outcome", "unknown", "--reconciliation-ref", "check:no-visible-message"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "unknown"
    assert (len(calls), len(reads)) == before
    assert cli.main([*base, "ops-reconcile", "--reply-id", rid, "--attempt-count", "1",
                     "--outcome", "sent", "--receipt-ref", "message:42",
                     "--reconciliation-ref", "check:provider-receipt"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "sent"
    assert (len(calls), len(reads)) == before


@pytest.mark.parametrize("command", ["bot-doctor", "bot-configure"])
@pytest.mark.parametrize("problem", ["unbound", "fixture", "paused", "slot", "source", "environment"])
def test_ops_doctor_configure_local_failure_before_credentials(tmp_path, capsys, command, problem):
    from datetime import datetime, timezone
    path = tmp_path / "ops" / "ops.db"
    with AgentToolOpsStore(path) as store:
        if problem != "unbound":
            store.bind_operator(8001, "https://api.telegram.org", operator_user_id=77223311,
                                operator_private_chat_id=77223311,
                                credential_ref="fixture:test" if problem == "fixture" else
                                    ops_runtime.credential_reference("KingdomOpsBot"),
                                source_binding="ws_cli", verification="fixture" if problem == "fixture" else "verified")
            if problem == "paused":
                store.pause()
    args = ["--db", str(path), command, "--bot-username", "KingdomOpsBot", "--profile", "ops",
            "--source-binding", "wrong" if problem == "source" else "ws_cli"]
    if command == "bot-configure":
        args.append("--apply")
    if problem == "slot":
        args.extend(["--keychain-account", "private-account-sentinel"])
    if problem == "environment":
        args.extend(["--token-source", "environment"])
    assert cli.main(args) == 1
    result = capsys.readouterr()
    assert json.loads(result.err)["ok"] is False
    assert str(path) not in result.err and "private-account-sentinel" not in result.err


def test_cli_demo_is_lazy_and_passes_exact_scenario(capsys, monkeypatch):
    import sys
    from types import ModuleType
    demo = ModuleType("telegram_gateway.ops_demo")
    seen = []
    def run_demo(scenario="happy"):
        seen.append(scenario)
        return {"scenario": scenario, "synthetic": True}
    demo.run_demo = run_demo
    monkeypatch.setitem(sys.modules, "telegram_gateway.ops_demo", demo)
    assert cli.main(["ops-demo", "--scenario", "unknown"]) == 0
    assert json.loads(capsys.readouterr().out) == {"scenario": "unknown", "synthetic": True}
    assert seen == ["unknown"]


def test_explicit_v1_migration_preview_then_apply_without_creating_research_state(tmp_path, capsys):
    from telegram_gateway import agenttool_ops as ops
    path = tmp_path / "ops" / "ops.db"
    with AgentToolOpsStore(path) as store:
        store.conn.execute("PRAGMA foreign_keys=OFF")
        for name in ("ops_reply_reconciliations", "ops_reply_attempts", "ops_replies",
                     "ops_update_dispositions", "ops_transport", "ops_poll_epochs", "ops_bindings"):
            store.conn.execute(f"DROP TABLE {name}")
        store.conn.execute("UPDATE ops_meta SET value=? WHERE key='database_role'",
                           (ops.OPS_V1_DATABASE_ROLE.encode(),))
        store.conn.execute("PRAGMA journal_mode=DELETE")
    before = path.read_bytes()
    base = ["--db", str(path), "ops-migrate"]
    assert cli.main(base) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["migration_required"] is True and preview["apply"] is False
    assert path.read_bytes() == before
    assert cli.main([*base, "--apply"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["applied"] is True
    with AgentToolOpsStore(path) as store:
        assert store.binding() is None
    assert cli.main(base) == 0
    assert json.loads(capsys.readouterr().out)["migration_required"] is False


def test_ops_token_store_selects_dedicated_service(capsys, monkeypatch):
    observed = []
    def fake_store(username, **kwargs):
        observed.append((username, kwargs))
        return {"stored": True}
    monkeypatch.setattr(cli, "store_token_interactively", fake_store)
    assert cli.main(["bot-token-store", "--bot-username", "KingdomOpsBot", "--profile", "ops"]) == 0
    capsys.readouterr()
    assert observed == [("KingdomOpsBot", {"keychain_account_name": None,
                                            "keychain_service": bootstrap.OPS_KEYCHAIN_SERVICE})]


@pytest.mark.parametrize("arguments", [
    ["ops-bind", "--bot-username", "KingdomOpsBot", "--bot-id", "SECRET_SENTINEL"],
    ["ops-reconcile", "--reply-id", "rpl_" + "0" * 32, "--attempt-count", "1",
     "--outcome", "/private/SECRET_SENTINEL", "--reconciliation-ref", "ref"],
    ["ops-pause", "--SECRET_SENTINEL"],
    ["bot-configure", "--profile", "ops", "--bot-username", "KingdomOpsBot", "--SECRET_SENTINEL"],
])
def test_ops_parser_errors_do_not_echo_private_inputs(arguments, capsys):
    assert cli.main(arguments) == 1
    result = capsys.readouterr()
    assert result.out == ""
    assert json.loads(result.err)["error_code"] == "invalid_arguments"
    assert "SECRET_SENTINEL" not in result.err


@pytest.mark.parametrize("paused", [False, True])
def test_bound_observer_mismatch_or_pause_contacts_no_source(tmp_path, capsys, monkeypatch, paused):
    path = tmp_path / "ops" / "ops.db"
    with AgentToolOpsStore(path) as store:
        store.bind_operator(8001, "https://api.telegram.org", operator_user_id=77223311,
                            operator_private_chat_id=77223311, credential_ref="fixture:watch",
                            source_binding="ws_expected", verification="fixture")
        if paused:
            store.pause()
    class Reader:
        def __init__(self, config):
            pass
        def verify_journal(self):
            pytest.fail("bound observer read a mismatched or paused source")
    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", Reader)
    assert cli.main(["--db", str(path), "ops-watch-once", "--workspace-id",
                     "ws_expected" if paused else "ws_wrong", "--collab-db",
                     str(tmp_path / "no-source.db")]) == 1
    error = capsys.readouterr().err
    assert str(path) not in error
    assert "paused" in error if paused else "source binding" in error


@pytest.mark.parametrize("source", ["ws_cli", "ws_other"])
@pytest.mark.parametrize("seed", [False, True])
def test_cli_refuses_first_binding_after_unbound_source_observation_without_credentials(
    tmp_path, capsys, monkeypatch, source, seed,
):
    path = tmp_path / "ops" / "ops.db"
    head = CursorAnchor("epoch_source_a", 5, "5" * 64)
    class Reader:
        def __init__(self, config):
            assert config.workspace_id == "ws_cli"
        def verify_journal(self):
            return JournalVerification(head=head)
        def workspace_status(self):
            return _status(head)
    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", Reader)
    calls, reads, _ = _fake_live_api(monkeypatch)
    base = ["--db", str(path)]
    assert cli.main([*base, "ops-init"]) == 0
    capsys.readouterr()
    watch = [*base, "ops-watch-once", "--workspace-id", "ws_cli",
             "--collab-db", str(tmp_path / "never-open-real-source.db")]
    assert cli.main([*watch, *(["--seed-current-head"] if seed else [])]) == 0
    capsys.readouterr()
    with AgentToolOpsStore(path) as store:
        before = "\n".join(store.conn.iterdump())
    args = _binding_args()
    args[-1] = source
    for apply in ([], ["--apply"]):
        assert cli.main([*base, "ops-bind", *args, *apply]) == 1
        output = capsys.readouterr()
        error = json.loads(output.err)
        assert output.out == "" and error["error_code"] == "initial_binding_requires_empty_store"
        assert "new empty Ops database" in error["next_step"]
        assert str(path) not in output.err
        assert calls == reads == []
    assert cli.main([*base, "ops-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["transport"]["bound"] is False
    assert status["journal_verification"]["outcome"] == "valid"
    with AgentToolOpsStore(path) as store:
        assert "\n".join(store.conn.iterdump()) == before


def test_fresh_cli_binds_before_observing_only_that_source(tmp_path, capsys, monkeypatch):
    path = tmp_path / "ops" / "ops.db"
    base = ["--db", str(path)]
    _fake_live_api(monkeypatch)
    assert cli.main([*base, "ops-init"]) == 0
    capsys.readouterr()
    assert cli.main([*base, "ops-bind", *_binding_args(), "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["bound"]
    observations = []
    head = CursorAnchor("epoch_source_a", 5, "5" * 64)
    class Reader:
        def __init__(self, config):
            self.workspace = config.workspace_id
        def verify_journal(self):
            with AgentToolOpsStore(path) as store:
                assert store.binding().source_binding == self.workspace == "ws_cli"
            observations.append(self.workspace)
            return JournalVerification(head=head)
        def workspace_status(self):
            return _status(head)
    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", Reader)
    watch = [*base, "ops-watch-once", "--collab-db", str(tmp_path / "fixture-source.db"),
             "--seed-current-head", "--workspace-id"]
    assert cli.main([*watch, "ws_cli"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["action"] == "seeded_verified_current_head"
    assert cli.main([*watch, "ws_other"]) == 1
    assert "source binding" in capsys.readouterr().err
    assert observations == ["ws_cli"]


def _reply_history(path):
    """150 production-store replies; early terminal history hides later attempts."""
    from telegram_gateway.ops_service import OpsServiceConfig, TelegramOpsService

    now = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    expected = []
    with AgentToolOpsStore(path) as store:
        store.bind_operator(8001, "https://api.telegram.org", operator_user_id=77223311,
                            operator_private_chat_id=77223311, credential_ref="fixture:private-slot",
                            source_binding="private-source-label", verification="fixture", bound_at=now)
        service = TelegramOpsService(store, store, OpsServiceConfig(77223311, 77223311))
        for index, state in enumerate(("invalidated", "sent", "failed", "pending", "unknown", "inflight")):
            for j in range(25):
                uid = index * 25 + j + 1
                at = now + timedelta(seconds=uid * 2)
                update = {"update_id": uid, "message": {
                    "date": int(at.timestamp()), "text": "/start", "from": {"id": 77223311, "is_bot": False},
                    "chat": {"id": 77223311, "type": "private"},
                }}
                result = store.process_update_once(update, service, polling_epoch=store.poll_state().epoch,
                                                   processed_at=at)
                item = store.reply_item(result.reply_id)
                if state in {"sent", "failed", "unknown", "inflight"}:
                    store.claim_reply(item.reply_id, payload_digest=item.payload_digest,
                                      binding_revision=item.binding_revision)
                    if state != "inflight":
                        store.finish_reply(item.reply_id, attempt_count=1, state=state,
                                           receipt_ref="private-receipt-ref" if state == "sent" else None,
                                           error_code=None if state == "sent" else "telegram_transport")
                expected.append((item.reply_id, state))
            if state == "invalidated":
                store.pause()
                store.resume(resumed_at=at + timedelta(seconds=1))
        before = "\n".join(store.conn.iterdump())
        text = store.reply_item(expected[0][0]).text
    return expected, before, text


def test_ops_replies_recovers_all_states_after_stdout_loss_without_text_or_effects(tmp_path, capsys, monkeypatch):
    path = tmp_path / "ops" / "ops.db"
    expected, before, private_text = _reply_history(path)
    def forbidden(*args, **kwargs):
        pytest.fail("local reply listing reached a source, credential or provider")
    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", forbidden)
    monkeypatch.setattr(cli, "resolve_token", forbidden)
    monkeypatch.setattr(cli, "GatewayStore", forbidden)
    base = ["--db", str(path)]
    assert cli.main([*base, "ops-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert len(status["replies"]) == 20
    assert status["reply_list_has_more"] is status["reply_list_truncated"] is True
    assert status["reply_list_next_after_reply_id"] == expected[19][0]
    assert "ops-replies" in status["reply_list_next_step"]
    assert all(row["state"] == "invalidated" for row in status["replies"])

    for state in (None, "pending", "inflight", "unknown", "sent", "failed", "invalidated"):
        cursor, recovered = None, []
        wanted = [pair for pair in expected if state is None or pair[1] == state]
        for _ in range(9):  # Finite even if a broken cursor repeats its page.
            args = [*base, "ops-replies", "--limit", "20"]
            if state is not None:
                args.extend(["--state", state])
            if cursor is not None:
                args.extend(["--after-reply-id", cursor])
            assert cli.main(args) == 0
            captured = capsys.readouterr()
            assert captured.err == ""
            page = json.loads(captured.out)
            assert page["network_calls"] == page["credential_reads"] == 0
            assert page["ordering"] == "queued_at ASC, reply_id ASC"
            assert page["state"] == state and page["after_reply_id"] == cursor
            assert 1 <= len(page["replies"]) <= 20
            for row in page["replies"]:
                assert set(row) == {"reply_id", "state", "binding_revision", "attempt_count"}
                recovered.append((row["reply_id"], row["state"]))
            for sentinel in (private_text, str(path), "77223311", "private-slot", "private-source-label", "private-receipt-ref"):
                assert sentinel not in captured.out
            more = len(recovered) < len(wanted)
            assert page["has_more"] is page["truncated"] is more
            cursor = page["next_after_reply_id"]
            if not more:
                assert cursor is None
                break
            assert cursor == page["replies"][-1]["reply_id"]
        assert recovered == wanted

    # Exhausted cursors return an explicit empty final page, not the oldest page.
    assert cli.main([*base, "ops-replies", "--after-reply-id", expected[-1][0]]) == 0
    final = json.loads(capsys.readouterr().out)
    assert final["replies"] == [] and not final["has_more"] and final["next_after_reply_id"] is None
    with AgentToolOpsStore(path) as store:
        assert "\n".join(store.conn.iterdump()) == before
        assert len(store.list_replies(state="inflight", limit=100)) == 25
    # The existing explicit preview is the first output containing stored text.
    assert cli.main([*base, "ops-send-once", "--reply-id", expected[-1][0]]) == 0
    assert json.loads(capsys.readouterr().out)["text"] == private_text


@pytest.mark.parametrize("args,code", [
    (["--limit", "0"], "invalid_input"), (["--limit", "21"], "invalid_input"),
    (["--limit", "PRIVATE_SENTINEL"], "invalid_arguments"),
    (["--state", "PRIVATE_SENTINEL"], "invalid_arguments"),
    (["--after-reply-id", "PRIVATE_SENTINEL"], "invalid_input_or_state"),
    (["--after-reply-id", "rpl_" + "0" * 32], "invalid_input_or_state"),
])
def test_ops_replies_bad_pagination_is_closed_and_local(tmp_path, capsys, args, code):
    path = tmp_path / "ops" / "ops.db"
    with AgentToolOpsStore(path):
        pass
    assert cli.main(["--db", str(path), "ops-replies", *args]) == 1
    result = capsys.readouterr()
    assert result.out == "" and json.loads(result.err)["error_code"] == code
    assert "PRIVATE_SENTINEL" not in result.err and str(path) not in result.err


def test_ops_replies_empty_and_missing_store_are_explicit(tmp_path, capsys):
    path = tmp_path / "ops" / "ops.db"
    assert cli.main(["--db", str(path), "ops-replies"]) == 1
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert not path.exists()
    with AgentToolOpsStore(path):
        pass
    assert cli.main(["--db", str(path), "ops-replies"]) == 0
    page = json.loads(capsys.readouterr().out)
    assert page["replies"] == [] and page["next_after_reply_id"] is None
    assert page["has_more"] is page["truncated"] is False
    assert cli.main(["--db", str(path), "ops-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["reply_list_has_more"] is status["reply_list_truncated"] is False


def test_cli_exhausted_offset_diagnostic_precedes_credentials_and_preserves_replies(tmp_path, capsys, monkeypatch):
    from telegram_gateway.ops_service import OpsServiceConfig, TelegramOpsService

    path = tmp_path / "ops" / "ops.db"
    now = datetime.now(timezone.utc)
    with AgentToolOpsStore(path) as store:
        store.bind_operator(8001, "https://api.telegram.org", operator_user_id=77223311,
                            operator_private_chat_id=77223311,
                            credential_ref=ops_runtime.credential_reference("KingdomOpsBot"),
                            source_binding="ws_cli", bound_at=now - timedelta(seconds=2))
        service = TelegramOpsService(store, store, OpsServiceConfig(77223311, 77223311))
        result = store.process_update_once({"update_id": (1 << 31) - 1, "message": {
            "date": int(now.timestamp()), "text": "/start", "from": {"id": 77223311, "is_bot": False},
            "chat": {"id": 77223311, "type": "private"},
        }}, service, polling_epoch=1, processed_at=now)
        before = "\n".join(store.conn.iterdump())
    calls, reads, _ = _fake_live_api(monkeypatch)
    base = ["--db", str(path)]
    for _ in range(2):
        assert cli.main([*base, "ops-poll-once", "--bot-username", "KingdomOpsBot",
                         "--source-binding", "ws_cli"]) == 1
        error = json.loads(capsys.readouterr().err)
        assert error["error_code"] == "poll_offset_exhausted"
        assert "86,401 seconds" in error["next_step"] and "ops-replies" in error["next_step"]
        assert calls == reads == []
    assert cli.main([*base, "ops-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["transport"]["poll_offset_exhausted"] is True
    assert status["replies"][0]["reply_id"] == result.reply_id
    with AgentToolOpsStore(path) as store:
        assert "\n".join(store.conn.iterdump()) == before


@pytest.mark.parametrize("scenario,events,commands,sends,state", [
    ("happy", 7, 1, 1, "sent"), ("duplicate", 7, 2, 1, "sent"),
    ("crash", 7, 3, 1, "sent"), ("refusal", 4, 2, 0, "invalidated"),
    ("cancellation", 5, 2, 0, "invalidated"), ("unknown", 7, 1, 1, "unknown"),
])
def test_cli_runs_canonical_demos_offline(tmp_path, capsys, monkeypatch, scenario, events, commands, sends, state):
    import socket
    import subprocess
    from tempfile import TemporaryDirectory
    from telegram_gateway import ops_demo

    def forbidden(*args, **kwargs):
        pytest.fail("CLI demo attempted an external effect")
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)
    monkeypatch.setattr(agenttool_mcp, "StdioMcpTransport", forbidden)
    monkeypatch.setattr(ops_demo, "TemporaryDirectory", lambda **kwargs: TemporaryDirectory(dir=tmp_path, **kwargs))
    assert cli.main(["ops-demo", "--scenario", scenario]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    result = json.loads(output.out)
    assert result["label"] == "synthetic workflow: no model agents, real journal verification or Telegram delivery"
    assert result["counts"]["events"] == events
    assert result["counts"]["command_attempts"] == commands
    assert result["counts"]["delivery_attempts"] == sends
    assert result["receipts"]["reply"]["state"] == state
    assert result["state"]["cleanup_complete"] is True
    assert all(count == 0 for count in result["non_effects"].values())


def test_ops_local_status_helper_delegates_without_changing_the_result(monkeypatch):
    store, result = object(), {"schema": "fixture-status"}
    seen = []

    def local_status(opened):
        seen.append(opened)
        return result

    monkeypatch.setattr(ops_runtime, "local_status", local_status)
    assert cli._ops_local_status(store) is result
    assert seen == [store]


def test_ops_status_cli_preserves_runtime_contract_and_cli_only_fields(tmp_path, capsys, monkeypatch):
    path = tmp_path / "ops" / "ops.db"
    with AgentToolOpsStore(path) as store:
        expected = ops_runtime.local_status(store)
    calls = []
    original = ops_runtime.local_status

    def local_status(store):
        calls.append(store.path)
        return original(store)

    def forbidden(*args, **kwargs):
        pytest.fail("local Ops status opened a source or Research state")

    monkeypatch.setattr(ops_runtime, "local_status", local_status)
    monkeypatch.setattr(agenttool_mcp, "AgentToolMcpReader", forbidden)
    monkeypatch.setattr(cli, "GatewayStore", forbidden)
    monkeypatch.setattr(cli, "resolve_token", forbidden)
    assert cli.main(["--db", str(path), "ops-status"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        **expected, "projection_schema_initialized": True, "database_file_preexisted": True,
    }
    assert calls == [path]
    assert "projection_schema_initialized" not in expected
    assert "database_file_preexisted" not in expected


def test_ops_replies_cli_defaults_remain_all_states_and_twenty():
    args = cli.build_parser().parse_args(["ops-replies"])
    assert args.state is None and args.after_reply_id is None and args.limit == 20
