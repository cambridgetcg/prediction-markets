from __future__ import annotations

import copy
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from telegram_gateway.cli import main
from telegram_gateway.observations import (
    MAX_ARTIFACT_BYTES,
    ObservationError,
    ObservationLedger,
    build_observation,
    validate_observation,
)


UTC = timezone.utc


def example_observation(**overrides: object) -> dict[str, object]:
    captured = datetime(2026, 9, 3, 12, 1, tzinfo=UTC)
    values: dict[str, object] = {
        "market_id": "market-fed-september",
        "kind": "resolution_rule",
        "statement": "The named official release is the resolution source.",
        "source_url": "https://example.test/official-release?edition=1",
        "source_publisher": "Example primary publisher",
        "observed_at": captured - timedelta(minutes=1),
        "captured_at": captured,
        "artifact": b"exact archived response bytes",
        "media_type": "text/html",
    }
    values.update(overrides)
    return build_observation(**values)


def test_observation_is_content_bound_and_denies_execution() -> None:
    observation = example_observation()
    assert validate_observation(observation) == observation
    assert observation["observation_id"].startswith("obs-")
    assert observation["authority"] == {
        "mode": "information_only",
        "execution_allowed": False,
        "not_an_authorization": True,
    }
    assert observation["limitations"]["source_authenticated"] is False
    assert observation["limitations"]["statement_proven"] is False

    changed = copy.deepcopy(observation)
    changed["statement"] = "A later unsupported rewrite."
    with pytest.raises(ObservationError, match="does not match"):
        validate_observation(changed)


def test_observation_rejects_unsafe_or_unbounded_inputs() -> None:
    with pytest.raises(ObservationError, match="HTTPS"):
        example_observation(source_url="http://example.test/source")
    with pytest.raises(ObservationError, match="credentials"):
        example_observation(source_url="https://user:pass@example.test/source")
    with pytest.raises(ObservationError, match="later"):
        example_observation(
            observed_at=datetime(2026, 9, 4, tzinfo=UTC),
            captured_at=datetime(2026, 9, 3, tzinfo=UTC),
        )
    with pytest.raises(ObservationError, match="byte limit"):
        example_observation(artifact=b"x" * (MAX_ARTIFACT_BYTES + 1))
    with pytest.raises(ObservationError, match="allowed"):
        example_observation(kind="telegram_scrape")


def test_ledger_is_idempotent_append_only_and_queryable() -> None:
    connection = sqlite3.connect(":memory:")
    ledger = ObservationLedger(connection)
    first = example_observation()
    second = example_observation(
        kind="catalyst",
        statement="The scheduled publication time is 18:00 UTC.",
        artifact=b"another exact artifact",
    )

    assert ledger.append(first)
    assert not ledger.append(first)
    assert ledger.append(second)
    assert ledger.get(str(first["observation_id"])) == first
    assert ledger.list_for_market("market-fed-september") == [first, second]
    assert ledger.summary() == {
        "schema": "kingdom.observation/0.1",
        "total": 2,
        "by_kind": {"catalyst": 1, "resolution_rule": 1},
        "append_only": True,
        "execution_allowed": False,
    }

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute(
            "UPDATE research_observations SET kind = 'outcome'"
        )
    connection.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("DELETE FROM research_observations")


def test_ledger_refuses_invalid_limit() -> None:
    ledger = ObservationLedger(sqlite3.connect(":memory:"))
    with pytest.raises(ObservationError, match="between 1 and 500"):
        ledger.list_for_market("market-fed-september", limit=0)


def test_cli_records_and_lists_only_an_existing_bounded_artifact(
    tmp_path, capsys
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    artifact = tmp_path / "release.html"
    artifact.write_bytes(b"archived official release")
    database = private / "gateway.db"
    arguments = [
        "--db",
        str(database),
        "evidence-record",
        "--market-id",
        "market-1",
        "--kind",
        "primary_source",
        "--source-url",
        "https://example.test/release",
        "--publisher",
        "Example publisher",
        "--observed-at",
        "2026-09-03T11:00:00Z",
        "--captured-at",
        "2026-09-03T11:01:00Z",
        "--statement",
        "The release reports the bounded test outcome.",
        "--artifact",
        str(artifact),
        "--media-type",
        "text/html",
    ]
    assert main(arguments) == 0
    created = __import__("json").loads(capsys.readouterr().out)
    assert created["created"] is True
    assert created["artifact_retained"] is False
    assert created["execution_allowed"] is False

    assert main(arguments) == 0
    duplicate = __import__("json").loads(capsys.readouterr().out)
    assert duplicate["created"] is False

    assert main(
        [
            "--db",
            str(database),
            "evidence-list",
            "--market-id",
            "market-1",
        ]
    ) == 0
    listed = __import__("json").loads(capsys.readouterr().out)
    assert len(listed["observations"]) == 1
    assert listed["observations"][0]["statement"].startswith("The release")
