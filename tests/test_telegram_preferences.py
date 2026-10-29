from __future__ import annotations

import os
import sqlite3
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from telegram_gateway.preferences import (
    DEFAULT_PREFERENCE_NOTICE_VERSION,
    MAX_WATCHLIST_ITEMS,
    PreferenceLimitError,
    PreferenceStore,
)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path: Path) -> PreferenceStore:
    value = PreferenceStore(tmp_path / "private" / "preferences.db")
    try:
        yield value
    finally:
        value.close()


def grant(store: PreferenceStore, now: datetime, *, update_id: int = 1) -> None:
    result = store.grant_consent(101, 101, update_id, event_at=now, now=now)
    assert result.accepted


def test_topics_cadence_and_watchlist_persist_across_reopen(
    tmp_path: Path, now: datetime
) -> None:
    path = tmp_path / "private" / "preferences.db"
    with PreferenceStore(path) as first:
        grant(first, now)
        result = first.replace_topics(
            101,
            ["macro-policy", "elections"],
            2,
            event_at=now + timedelta(seconds=1),
            now=now + timedelta(seconds=1),
        )
        assert result.accepted and result.changed
        assert first.set_cadence(
            101,
            "daily",
            3,
            event_at=now + timedelta(seconds=2),
            now=now + timedelta(seconds=2),
        ).changed
        assert first.watch(
            101,
            "polymarket:2252244",
            4,
            event_at=now + timedelta(seconds=3),
            now=now + timedelta(seconds=3),
        ).changed

    with PreferenceStore(path) as reopened:
        snapshot = reopened.snapshot(101)
        assert snapshot.active
        assert snapshot.notice_version == DEFAULT_PREFERENCE_NOTICE_VERSION
        assert snapshot.topics == ("macro-policy", "elections")
        assert snapshot.cadence == "daily"
        assert snapshot.watchlist == ("polymarket:2252244",)


def test_mutations_require_current_explicit_consent(
    store: PreferenceStore, now: datetime
) -> None:
    missing = store.watch(101, "market-1", 1, event_at=now, now=now)
    assert not missing.accepted
    assert missing.reason == "consent_required"

    grant(store, now, update_id=2)
    rotated = PreferenceStore(
        store.path,
        notice_version="2026-09-04-preferences-v2",
    )
    try:
        snapshot = rotated.snapshot(101)
        assert snapshot.consent_state == "needs_reconfirmation"
        rejected = rotated.set_cadence(
            101,
            "daily",
            3,
            event_at=now + timedelta(seconds=1),
            now=now + timedelta(seconds=1),
        )
        assert not rejected.accepted
        assert rejected.reason == "notice_reconfirmation_required"
        assert rotated.grant_consent(
            101,
            101,
            4,
            event_at=now + timedelta(seconds=2),
            now=now + timedelta(seconds=2),
        ).changed
        assert rotated.snapshot(101).active
    finally:
        rotated.close()


def test_withdrawal_erases_profile_and_stale_updates_cannot_restore_it(
    store: PreferenceStore, now: datetime
) -> None:
    grant(store, now)
    assert store.replace_topics(
        101,
        ["geopolitics"],
        2,
        event_at=now + timedelta(seconds=1),
        now=now + timedelta(seconds=1),
    ).accepted
    assert store.watch(
        101,
        "market-1",
        3,
        event_at=now + timedelta(seconds=2),
        now=now + timedelta(seconds=2),
    ).accepted

    removed = store.withdraw_consent(
        101,
        4,
        event_at=now + timedelta(seconds=3),
        now=now + timedelta(seconds=3),
    )
    assert removed.removed_records == 3
    assert store.snapshot(101).consent_state == "withdrawn"
    assert store.conn.execute(
        "SELECT 1 FROM preference_profiles WHERE telegram_user_id = 101"
    ).fetchone() is None

    stale = store.grant_consent(
        101,
        101,
        5,
        event_at=now + timedelta(seconds=2),
        now=now + timedelta(seconds=4),
    )
    assert not stale.accepted
    assert store.snapshot(101).consent_state == "withdrawn"

    newer = store.grant_consent(
        101,
        101,
        6,
        event_at=now + timedelta(seconds=5),
        now=now + timedelta(seconds=5),
    )
    assert newer.accepted
    assert store.snapshot(101).active
    assert store.snapshot(101).topics == ()
    assert store.snapshot(101).watchlist == ()


def test_privacy_delete_keeps_only_minimal_ordering_marker(
    store: PreferenceStore, now: datetime
) -> None:
    grant(store, now)
    store.replace_topics(
        101,
        ["macro-policy"],
        2,
        event_at=now + timedelta(seconds=1),
        now=now + timedelta(seconds=1),
    )
    store.watch(
        101,
        "polymarket:2252244",
        3,
        event_at=now + timedelta(seconds=2),
        now=now + timedelta(seconds=2),
    )
    result = store.delete_user(
        101,
        4,
        event_at=now + timedelta(seconds=3),
        now=now + timedelta(seconds=3),
    )

    assert result.removed_records == 3
    assert store.snapshot(101).consent_state == "deleted"
    for table in ("preference_profiles", "preference_topics", "preference_watchlist"):
        assert store.conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE telegram_user_id = 101"
        ).fetchone()[0] == 0
    marker = store.conn.execute(
        "SELECT * FROM preference_suppressions WHERE telegram_user_id = 101"
    ).fetchone()
    assert set(marker.keys()) == {
        "telegram_user_id",
        "reason",
        "event_at",
        "update_id",
        "recorded_at",
    }
    assert marker["reason"] == "deleted"

    # A later stop command must not downgrade the stronger deletion marker.
    repeat = store.withdraw_consent(
        101,
        5,
        event_at=now + timedelta(seconds=4),
        now=now + timedelta(seconds=4),
    )
    assert repeat.accepted and not repeat.changed
    assert store.snapshot(101).consent_state == "deleted"


def test_noop_mutation_advances_ordering_watermark(
    store: PreferenceStore, now: datetime
) -> None:
    grant(store, now)
    noop = store.unwatch(
        101,
        "market-1",
        10,
        event_at=now + timedelta(seconds=10),
        now=now + timedelta(seconds=10),
    )
    assert noop.accepted and not noop.changed
    stale = store.watch(
        101,
        "market-1",
        9,
        event_at=now + timedelta(seconds=9),
        now=now + timedelta(seconds=11),
    )
    assert not stale.accepted
    assert store.snapshot(101).watchlist == ()


def test_later_event_can_use_lower_update_id_after_telegram_reset(
    store: PreferenceStore, now: datetime
) -> None:
    assert store.grant_consent(101, 101, 100, event_at=now, now=now).accepted
    later = store.watch(
        101,
        "market-after-id-reset",
        10,
        event_at=now + timedelta(days=7),
        now=now + timedelta(days=7),
    )
    assert later.accepted and later.changed

    replay = store.unwatch(
        101,
        "market-after-id-reset",
        10,
        event_at=now + timedelta(days=8),
        now=now + timedelta(days=8),
    )
    assert not replay.accepted
    assert store.snapshot(101).watchlist == ("market-after-id-reset",)


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda value, n: value.replace_topics(101, ["unknown"], 2, now=n), "unknown topic"),
        (lambda value, n: value.replace_topics(101, ["macro-policy"] * 2, 2, now=n), "duplicates"),
        (lambda value, n: value.set_cadence(101, "hourly", 2, now=n), "cadence"),
        (
            lambda value, n: value.watch(
                101, "https://example.test/market", 2, now=n
            ),
            "market reference",
        ),
        (
            lambda value, n: value.watch(101, "wallet key with spaces", 2, now=n),
            "market reference",
        ),
    ],
)
def test_invalid_preference_inputs_are_rejected_before_storage(
    store: PreferenceStore,
    now: datetime,
    operation: object,
    message: str,
) -> None:
    grant(store, now)
    with pytest.raises(ValueError, match=message):
        operation(store, now)  # type: ignore[operator]
    assert store.snapshot(101).topics == ()
    assert store.snapshot(101).watchlist == ()


def test_identity_update_and_timestamp_inputs_are_bounded(
    store: PreferenceStore, now: datetime
) -> None:
    with pytest.raises(ValueError, match="identity"):
        store.grant_consent(True, True, 1, now=now)
    with pytest.raises(ValueError, match="identity"):
        store.grant_consent(101, 102, 1, now=now)
    with pytest.raises(ValueError, match="update ID"):
        store.grant_consent(101, 101, True, now=now)
    with pytest.raises(ValueError, match="timezone"):
        store.grant_consent(101, 101, 1, now=now.replace(tzinfo=None))
    with pytest.raises(ValueError, match="future"):
        store.grant_consent(
            101,
            101,
            1,
            event_at=now + timedelta(minutes=6),
            now=now,
        )


def test_watchlist_bound_is_enforced_without_partial_write(
    store: PreferenceStore, now: datetime
) -> None:
    grant(store, now)
    for index in range(MAX_WATCHLIST_ITEMS):
        result = store.watch(
            101,
            f"market-{index}",
            index + 2,
            event_at=now + timedelta(seconds=index + 1),
            now=now + timedelta(seconds=index + 1),
        )
        assert result.accepted and result.changed
    with pytest.raises(PreferenceLimitError, match=str(MAX_WATCHLIST_ITEMS)):
        store.watch(
            101,
            "one-too-many",
            100,
            event_at=now + timedelta(seconds=100),
            now=now + timedelta(seconds=100),
        )
    assert len(store.snapshot(101).watchlist) == MAX_WATCHLIST_ITEMS


def test_topic_replacement_rolls_back_on_sqlite_failure(
    store: PreferenceStore, now: datetime
) -> None:
    grant(store, now)
    store.replace_topics(
        101,
        ["macro-policy"],
        2,
        event_at=now + timedelta(seconds=1),
        now=now + timedelta(seconds=1),
    )
    before = store.snapshot(101)
    store.conn.execute(
        """CREATE TRIGGER fail_elections_preference
           BEFORE INSERT ON preference_topics
           WHEN NEW.topic_code = 'elections'
           BEGIN SELECT RAISE(ABORT, 'injected failure'); END"""
    )
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        store.replace_topics(
            101,
            ["elections"],
            3,
            event_at=now + timedelta(seconds=2),
            now=now + timedelta(seconds=2),
        )
    after = store.snapshot(101)
    assert after.topics == before.topics
    assert after.updated_at == before.updated_at


def test_database_and_sidecars_are_owner_only(tmp_path: Path, now: datetime) -> None:
    path = tmp_path / "private" / "preferences.db"
    with PreferenceStore(path) as value:
        grant(value, now)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists():
                assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600

    insecure = tmp_path / "shared"
    insecure.mkdir(mode=0o755)
    os.chmod(insecure, 0o755)
    with pytest.raises(PermissionError, match="owner-only"):
        PreferenceStore(insecure / "preferences.db")
