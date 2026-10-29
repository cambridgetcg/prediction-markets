from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from telegram_gateway.cli import _promotion_report, main
from telegram_gateway.promotion import generate_campaign_code
from telegram_gateway.store import GatewayStore


UTC = timezone.utc


def test_promotion_status_suppresses_small_cells_by_default(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        store.record_promotion_campaign_start(campaign, now=now)
        store.register_recipient(101, 101, now=now)
        assert store.join_promotion_campaign(
            101,
            campaign,
            10,
            event_at=now,
            now=now,
        ) == {
            "campaign_active": True,
            "attributed": True,
            "consent_changed": True,
            "subscribed": True,
        }

    assert main(["--db", str(database), "promotion-status"]) == 0
    safe = json.loads(capsys.readouterr().out)
    assert safe["privacy_status"] == "small_cells_suppressed"
    assert safe["summary"]["start_events"] is None
    assert safe["summary"]["alerts_subscribed"] is None
    assert safe["campaigns"][0]["privacy_status"] == "suppressed_below_5"
    assert safe["campaigns"][0]["start_events"] is None
    assert safe["campaigns"][0]["attributed_recipients"] is None

    assert (
        main(["--db", str(database), "promotion-status", "--exact-local"])
        == 0
    )
    exact = json.loads(capsys.readouterr().out)
    assert exact["privacy_status"] == "exact_local_unsafe"
    assert "identify" in exact["privacy_warning"].lower()
    assert exact["summary"]["start_events"] == 1
    assert exact["summary"]["alerts_subscribed"] == 1
    assert exact["campaigns"][0]["attributed_recipients"] == 1

    assert main(["--db", str(database), "status"]) == 0
    health = json.loads(capsys.readouterr().out.splitlines()[0])
    assert "alerts_subscribed" not in health["counts"]
    assert "attributed_recipients" not in health["counts"]
    assert "paper_actions" not in health["counts"]
    assert "sent" not in health["counts"]
    assert "promotion-status" in health["counts_privacy"]


def test_global_totals_are_hidden_when_subtraction_reveals_direct_join(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        for index in range(5):
            user_id = 100 + index
            event = now + timedelta(seconds=index)
            store.record_promotion_campaign_start(campaign, now=event)
            store.register_recipient(user_id, user_id, now=event)
            assert store.join_promotion_campaign(
                user_id,
                campaign,
                10 + index,
                event_at=event,
                now=event,
            )["attributed"]
        store.register_recipient(999, 999, now=now + timedelta(minutes=1))
        assert store.set_research_alert_consent(
            999,
            subscribed=True,
            telegram_update_id=99,
            event_at=now + timedelta(minutes=1),
            now=now + timedelta(minutes=1),
        )

    assert main(["--db", str(database), "promotion-status"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["campaigns"][0]["currently_subscribed"] == "5-9"
    assert report["campaigns"][0]["privacy_status"] == "bucketed_in_fives"
    assert report["summary"]["alerts_subscribed"] is None
    assert report["summary"]["privacy_status"] == (
        "suppressed_to_prevent_differencing"
    )


def test_early_start_attribution_schema_is_deidentified_during_migration(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gateway.db"
    campaign = generate_campaign_code()
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE recipients (
                telegram_user_id INTEGER PRIMARY KEY
            );
            CREATE TABLE promotion_campaigns (
                campaign_code TEXT PRIMARY KEY,
                campaign_kind TEXT NOT NULL,
                active INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                disabled_at TEXT
            );
            CREATE TABLE promotion_attributions (
                telegram_user_id INTEGER PRIMARY KEY,
                campaign_code TEXT NOT NULL,
                start_update_id INTEGER NOT NULL UNIQUE,
                attributed_at TEXT NOT NULL
            );
            """
        )
        connection.execute("INSERT INTO recipients VALUES (101)")
        connection.execute(
            """INSERT INTO promotion_campaigns
               VALUES (?, 'test', 1, '2026-09-01T00:00:00Z', NULL)""",
            (campaign,),
        )
        connection.execute(
            """INSERT INTO promotion_attributions
               VALUES (101, ?, 55, '2026-09-02T03:04:05Z')""",
            (campaign,),
        )

    with GatewayStore(database) as store:
        columns = {
            str(row["name"])
            for row in store.conn.execute(
                "PRAGMA table_info(promotion_attributions)"
            ).fetchall()
        }
        assert columns == {
            "telegram_user_id",
            "campaign_code",
            "attribution_update_id",
            "attributed_on",
        }
        assert store.conn.execute(
            "SELECT COUNT(*) FROM promotion_attributions"
        ).fetchone()[0] == 0
        start = store.conn.execute(
            """SELECT observed_on, start_count FROM promotion_campaign_starts
               WHERE campaign_code = ?""",
            (campaign,),
        ).fetchone()
        assert dict(start) == {"observed_on": "2026-09-02", "start_count": 1}


def test_attribution_requires_matching_subscribed_update_at_sql_boundary(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        store.register_recipient(101, 101, now=now)

        with pytest.raises(
            sqlite3.IntegrityError,
            match="requires matching subscribed consent",
        ):
            store.conn.execute(
                """INSERT INTO promotion_attributions
                     (telegram_user_id, campaign_code, attribution_update_id,
                      attributed_on)
                   VALUES (101, ?, 10, '2026-09-03')""",
                (campaign,),
            )
        store.conn.rollback()

        assert store.join_promotion_campaign(
            101,
            campaign,
            10,
            event_at=now,
            now=now,
        )["attributed"]
        with pytest.raises(
            sqlite3.IntegrityError,
            match="immutable",
        ):
            store.conn.execute(
                """UPDATE promotion_attributions
                   SET attribution_update_id = 11
                   WHERE telegram_user_id = 101"""
            )
        store.conn.rollback()

        other_campaign = generate_campaign_code()
        store.create_promotion_campaign(
            other_campaign,
            campaign_kind="test",
            now=now,
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store.conn.execute(
                """UPDATE promotion_attributions SET campaign_code = ?
                   WHERE telegram_user_id = 101""",
                (other_campaign,),
            )
        store.conn.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store.conn.execute(
                """INSERT OR REPLACE INTO promotion_attributions
                     (telegram_user_id, campaign_code, attribution_update_id,
                      attributed_on)
                   VALUES (101, ?, 10, '2026-09-03')""",
                (other_campaign,),
            )
        store.conn.rollback()
        assert store.conn.execute(
            """SELECT campaign_code FROM promotion_attributions
               WHERE telegram_user_id = 101"""
        ).fetchone()[0] == campaign

        store.conn.execute(
            """DELETE FROM research_alert_consent_events
               WHERE telegram_update_id = 10"""
        )
        store.conn.commit()
        assert store.conn.execute(
            "SELECT COUNT(*) FROM promotion_attributions"
        ).fetchone()[0] == 0


def test_join_rolls_back_new_consent_when_attribution_insert_fails(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        store.register_recipient(101, 101, now=now)
        store.conn.execute(
            """CREATE TRIGGER test_force_attribution_failure
               BEFORE INSERT ON promotion_attributions
               BEGIN
                 SELECT RAISE(ABORT, 'forced attribution failure');
               END"""
        )
        store.conn.commit()

        with pytest.raises(ValueError, match="conflicts with stored evidence"):
            store.join_promotion_campaign(
                101,
                campaign,
                10,
                event_at=now,
                now=now,
            )

        assert store.research_alert_status(101)["state"] == "not_joined"
        assert store.conn.execute(
            """SELECT COUNT(*) FROM research_alert_consents
               WHERE telegram_user_id = 101"""
        ).fetchone()[0] == 0
        assert store.conn.execute(
            """SELECT COUNT(*) FROM research_alert_consent_events
               WHERE telegram_user_id = 101"""
        ).fetchone()[0] == 0
        assert store.conn.execute(
            """SELECT COUNT(*) FROM promotion_attributions
               WHERE telegram_user_id = 101"""
        ).fetchone()[0] == 0


def test_exact_campaign_join_replay_does_not_duplicate_evidence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        store.register_recipient(101, 101, now=now)

        first = store.join_promotion_campaign(
            101,
            campaign,
            10,
            event_at=now,
            now=now,
        )
        replay = store.join_promotion_campaign(
            101,
            campaign,
            10,
            event_at=now,
            now=now + timedelta(seconds=1),
        )

        assert first == {
            "campaign_active": True,
            "attributed": True,
            "consent_changed": True,
            "subscribed": True,
        }
        assert replay == {
            "campaign_active": True,
            "attributed": False,
            "consent_changed": False,
            "subscribed": True,
        }
        assert store.conn.execute(
            """SELECT COUNT(*) FROM research_alert_consent_events
               WHERE telegram_user_id = 101"""
        ).fetchone()[0] == 1
        assert store.conn.execute(
            """SELECT COUNT(*) FROM promotion_attributions
               WHERE telegram_user_id = 101"""
        ).fetchone()[0] == 1


def test_historical_attribution_survives_later_unsubscribe(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        store.register_recipient(101, 101, now=now)
        assert store.join_promotion_campaign(
            101,
            campaign,
            10,
            event_at=now,
            now=now,
        )["attributed"]
        assert store.set_research_alert_consent(
            101,
            subscribed=False,
            telegram_update_id=11,
            event_at=now + timedelta(minutes=1),
            now=now + timedelta(minutes=1),
        )

    with GatewayStore(database) as store:
        assert store.research_alert_status(101)["state"] == "unsubscribed"
        row = store.conn.execute(
            """SELECT campaign_code, attribution_update_id
               FROM promotion_attributions WHERE telegram_user_id = 101"""
        ).fetchone()
        assert tuple(row) == (campaign, 10)
        store.conn.execute(
            "DELETE FROM promotion_attributions WHERE telegram_user_id = 101"
        )
        store.conn.commit()
        with pytest.raises(
            sqlite3.IntegrityError,
            match="requires matching subscribed consent",
        ):
            store.conn.execute(
                """INSERT INTO promotion_attributions
                     (telegram_user_id, campaign_code, attribution_update_id,
                      attributed_on)
                   VALUES (101, ?, 10, '2026-09-03')""",
                (campaign,),
            )
        store.conn.rollback()


def test_insert_or_replace_cannot_orphan_attribution(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        store.register_recipient(101, 101, now=now)
        assert store.join_promotion_campaign(
            101,
            campaign,
            10,
            event_at=now,
            now=now,
        )["attributed"]

    timestamp = now.isoformat().replace("+00:00", "Z")
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 0
        connection.execute(
            """INSERT OR REPLACE INTO research_alert_consent_events
                 (telegram_update_id, telegram_user_id, state, notice_version,
                  event_at, recorded_at)
               VALUES (10, 101, 'unsubscribed', 'alerts-v1', ?, ?)""",
            (timestamp, timestamp),
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM promotion_attributions"
        ).fetchone()[0] == 0


def test_update_or_replace_cannot_orphan_conflicting_attribution(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        for user_id, update_id in ((101, 10), (202, 20)):
            store.register_recipient(user_id, user_id, now=now)
            assert store.join_promotion_campaign(
                user_id,
                campaign,
                update_id,
                event_at=now,
                now=now,
            )["attributed"]

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 0
        connection.execute(
            """UPDATE OR REPLACE research_alert_consent_events
               SET telegram_update_id = 20
               WHERE telegram_update_id = 10"""
        )
        orphan_count = connection.execute(
            """SELECT COUNT(*)
               FROM promotion_attributions AS attribution
               WHERE NOT EXISTS (
                 SELECT 1 FROM research_alert_consent_events AS consent_event
                 WHERE consent_event.telegram_user_id =
                         attribution.telegram_user_id
                   AND consent_event.telegram_update_id =
                         attribution.attribution_update_id
                   AND consent_event.state = 'subscribed'
               )"""
        ).fetchone()[0]
        assert orphan_count == 0


def test_rowid_alias_updates_cannot_orphan_or_rewrite_attribution(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        for user_id, update_id in ((101, 10), (202, 20)):
            store.register_recipient(user_id, user_id, now=now)
            assert store.join_promotion_campaign(
                user_id,
                campaign,
                update_id,
                event_at=now,
                now=now,
            )["attributed"]

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """UPDATE promotion_attributions SET rowid = 303
                   WHERE rowid = 202"""
            )
        connection.rollback()
        assert connection.execute(
            """SELECT telegram_user_id FROM promotion_attributions
               WHERE attribution_update_id = 20"""
        ).fetchone()[0] == 202

        connection.execute(
            """UPDATE research_alert_consent_events SET rowid = 11
               WHERE rowid = 10"""
        )
        orphan_count = connection.execute(
            """SELECT COUNT(*)
               FROM promotion_attributions AS attribution
               WHERE NOT EXISTS (
                 SELECT 1 FROM research_alert_consent_events AS consent_event
                 WHERE consent_event.telegram_user_id =
                         attribution.telegram_user_id
                   AND consent_event.telegram_update_id =
                         attribution.attribution_update_id
                   AND consent_event.state = 'subscribed'
               )"""
        ).fetchone()[0]
        assert orphan_count == 0
        assert connection.execute(
            """SELECT COUNT(*) FROM promotion_attributions
               WHERE telegram_user_id = 101"""
        ).fetchone()[0] == 0


@pytest.mark.parametrize("rebuild_attribution_table", [False, True])
def test_orphan_attribution_is_scrubbed_on_open(
    tmp_path: Path,
    rebuild_attribution_table: bool,
) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        store.register_recipient(101, 101, now=now)
        store.register_recipient(202, 202, now=now)
        assert store.join_promotion_campaign(
            202,
            campaign,
            20,
            event_at=now,
            now=now,
        )["attributed"]

    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER promotion_attribution_requires_consent")
        connection.execute(
            """INSERT INTO promotion_attributions
                 (telegram_user_id, campaign_code, attribution_update_id,
                  attributed_on)
               VALUES (101, ?, 10, '2026-09-03')""",
            (campaign,),
        )
        if rebuild_attribution_table:
            connection.execute(
                "ALTER TABLE promotion_attributions ADD COLUMN attributed_at TEXT"
            )

    with GatewayStore(database) as store:
        assert {
            str(row["name"])
            for row in store.conn.execute(
                "PRAGMA table_info(promotion_attributions)"
            ).fetchall()
        } == {
            "telegram_user_id",
            "campaign_code",
            "attribution_update_id",
            "attributed_on",
        }
        rows = store.conn.execute(
            """SELECT telegram_user_id, attribution_update_id
               FROM promotion_attributions ORDER BY telegram_user_id"""
        ).fetchall()
        assert [tuple(row) for row in rows] == [(202, 20)]
        triggers = {
            str(row[0])
            for row in store.conn.execute(
                """SELECT name FROM sqlite_master
                   WHERE type = 'trigger' AND name LIKE 'promotion_%'"""
            ).fetchall()
        }
        assert triggers == {
            "promotion_attribution_requires_consent",
            "promotion_attribution_insert_is_first_write",
            "promotion_attribution_update_is_forbidden",
            "promotion_consent_event_delete_clears_attribution",
            "promotion_consent_event_update_clears_attribution",
            "promotion_consent_event_update_reconciles_attribution",
            "promotion_consent_event_insert_reconciles_attribution",
        }


def test_impossible_negative_metric_residual_fails_closed() -> None:
    summary = {
        "campaigns": 1,
        "active_campaigns": 1,
        "start_events": 10,
        "attributed_recipients": 10,
        "alerts_subscribed": 10,
        "alerts_unsubscribed": 10,
        "alerts_need_reconfirmation": 10,
        "alert_consent_events": 10,
    }
    campaign = {
        "campaign_code": generate_campaign_code(),
        "campaign_kind": "test",
        "active": True,
        "created_at": "2026-09-03T00:00:00Z",
        "disabled_at": None,
        "start_events": 10,
        "attributed_recipients": 11,
        "ever_opted_in": 10,
        "ever_opted_out": 10,
        "currently_subscribed": 10,
        "currently_unsubscribed": 10,
        "needs_reconfirmation": 10,
        "delivered_recipients": 10,
        "signals_sent": 10,
        "signals_unknown": 10,
        "paper_actors": 10,
        "paper_actions": 10,
    }

    report = _promotion_report(
        notice_version="alerts-v1",
        summary=summary,
        campaigns=[campaign],
        exact_local=False,
    )

    assert report["summary"]["attributed_recipients"] is None
    assert report["privacy_status"] == "small_cells_suppressed"


def test_source_attribution_rolls_back_when_opt_in_is_stale(tmp_path: Path) -> None:
    database = tmp_path / "gateway.db"
    now = datetime.now(UTC).replace(microsecond=0)
    campaign = generate_campaign_code()
    with GatewayStore(database) as store:
        store.create_promotion_campaign(campaign, campaign_kind="test", now=now)
        store.register_recipient(101, 101, now=now)
        store.record_contact_suppression(
            101,
            telegram_update_id=20,
            reason="withdrawn",
            event_at=now + timedelta(minutes=2),
            now=now + timedelta(minutes=2),
        )

        result = store.join_promotion_campaign(
            101,
            campaign,
            10,
            event_at=now + timedelta(minutes=1),
            now=now + timedelta(minutes=3),
        )

        assert result == {
            "campaign_active": True,
            "attributed": False,
            "consent_changed": False,
            "subscribed": False,
        }
        assert store.conn.execute(
            "SELECT COUNT(*) FROM promotion_attributions"
        ).fetchone()[0] == 0
        assert store.research_alert_status(101)["state"] == "not_joined"
