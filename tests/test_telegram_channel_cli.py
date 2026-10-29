from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import telegram_gateway.cli as cli
from telegram_gateway.channel_publishing import (
    ChannelPublicationLedger,
    PreparedChannelPost,
)
from telegram_gateway.envelope import build_s012_envelope
from telegram_gateway.promotion import build_campaign_link, generate_campaign_code
from telegram_gateway.store import GatewayStore


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")


def _current_envelope(now: datetime, *, signal_id: str) -> dict[str, Any]:
    signal = {
        "signal_id": signal_id,
        "assessment_id": "assessment-channel-cli",
        "event_id": "event-channel-cli",
        "market_id": "market-channel-cli",
        "market_question": "Will the scheduled policy decision occur?",
        "signal_type": "S012-OVER",
        "direction": "YES",
        "entry_price": 0.42,
        "target_price": 0.55,
        "stop_price": 0.34,
        "time_horizon_hours": 48,
        "size_usdc": 25.0,
        "size_pct": 0.01,
        "reaction_delta": 0.08,
        "estimated_shift": 0.04,
        "actual_move": 0.12,
        "confidence": 0.68,
        "reasoning": "A bounded, paper-only interpretation for the channel CLI.",
        "domain": "ECO",
        "passed_concentration": True,
        "passed_anti_patterns": True,
        "risk_notes": ["Confirm the official resolution wording."],
        "status": "PENDING",
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(hours=6)),
    }
    return build_s012_envelope(
        signal,
        observation_refs=["observation-channel-cli-primary"],
        resolution_rules_ref=(
            "https://polymarket.com/event/scheduled-policy-decision"
        ),
    )


def _approval(signal_id: str, occurred_at: datetime) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema": "s012.signal-lifecycle/0.1",
        "signal_id": signal_id,
        "revision": 1,
        "previous_status": "PENDING",
        "status": "APPROVED",
        "occurred_at": _iso(occurred_at),
        "actor_kind": "local_operator",
        "reason_code": "manual_review",
        "scope": "research_distribution_only",
        "execution_allowed": False,
    }
    material = json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    event["event_id"] = "s012-life-" + hashlib.sha256(material).hexdigest()[:32]
    return event


def _seed_signal(
    db_path: Path,
    *,
    approve: bool,
) -> tuple[dict[str, Any], datetime, datetime]:
    issued_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(
        minutes=5
    )
    approved_at = issued_at + timedelta(minutes=1)
    published_at = issued_at + timedelta(minutes=2)
    envelope = _current_envelope(
        issued_at,
        signal_id=(
            "signal-channel-cli-approved"
            if approve
            else "signal-channel-cli-pending"
        ),
    )
    with GatewayStore(db_path) as store:
        assert store.put_signal(envelope, now=issued_at)
        if approve:
            assert (
                store.apply_signal_lifecycle(
                    _approval(str(envelope["signal_id"]), approved_at),
                    now=approved_at,
                )
                == "applied"
            )
    return envelope, issued_at, published_at


def _write_source_links(path: Path, observed_at: datetime) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "observation_ref": "observation-channel-cli-primary",
                    "label": "Official policy calendar",
                    "url": (
                        "https://www.federalreserve.gov/monetarypolicy/"
                        "fomccalendars.htm"
                    ),
                    "observed_at": _iso(observed_at),
                    "is_primary": True,
                }
            ]
        ),
        encoding="utf-8",
    )


def _channel_post_argv(
    db_path: Path,
    ledger_path: Path,
    source_links_path: Path,
    signal_id: str,
    published_at: datetime,
    *,
    campaign_code: str | None = None,
    research_bot_username: str | None = None,
) -> list[str]:
    result = [
        "--db",
        str(db_path),
        "--channel-ledger",
        str(ledger_path),
        "channel-post",
        signal_id,
        "--channel",
        "@KingdomDispatch",
        "--source-links",
        str(source_links_path),
        "--market-url",
        "https://polymarket.com/event/scheduled-policy-decision",
        "--published-at",
        _iso(published_at),
    ]
    if campaign_code is not None:
        result.extend(["--campaign-code", campaign_code])
    if research_bot_username is not None:
        result.extend(["--research-bot-username", research_bot_username])
    return result


def test_channel_post_is_deterministic_zero_network_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "gateway-private" / "gateway.db"
    ledger_path = tmp_path / "channel-private" / "channel.db"
    envelope, issued_at, published_at = _seed_signal(db_path, approve=True)
    source_links_path = tmp_path / "source-links.json"
    _write_source_links(source_links_path, issued_at + timedelta(seconds=30))

    def unexpected_external_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run channel preparation reached a credential/network path")

    monkeypatch.setattr(cli, "resolve_token", unexpected_external_call)
    monkeypatch.setattr(cli, "TelegramAPI", unexpected_external_call)
    argv = _channel_post_argv(
        db_path,
        ledger_path,
        source_links_path,
        str(envelope["signal_id"]),
        published_at,
    )

    assert cli.main(argv) == 0
    first = json.loads(capsys.readouterr().out)
    assert cli.main(argv) == 0
    second = json.loads(capsys.readouterr().out)

    assert first == second
    assert first["apply"] is False
    assert first["network_calls"] == 0
    assert first["external_delivery_enabled"] is False
    assert first["execution_allowed"] is False
    assert first["card"]["schema"] == "kingdom.telegram-channel-card/0.1"
    assert first["card"]["integrity"]["content_digest"] == first["post"][
        "card_digest"
    ]
    assert first["post"]["canonical_channel_ref"] == "@kingdomdispatch"
    assert first["post"]["channel_ref"] == "@kingdomdispatch"
    assert first["post"]["publication_id"].startswith("kingdom-pub-")
    assert "KINGDOM RESEARCH • ACTIVE" in first["post"]["text"]
    assert "No trade was placed" in first["post"]["text"]
    assert not ledger_path.exists()


def test_channel_post_can_append_bound_private_bot_cta_without_mutating_card(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "gateway-private" / "gateway.db"
    ledger_path = tmp_path / "channel-private" / "channel.db"
    envelope, issued_at, published_at = _seed_signal(db_path, approve=True)
    source_links_path = tmp_path / "source-links.json"
    _write_source_links(source_links_path, issued_at + timedelta(seconds=30))
    campaign_code = generate_campaign_code()
    stored_bot_username = "KingdomResearchBot"
    research_bot_username = "kingdomresearchbot"
    with GatewayStore(db_path) as store:
        store.bind_authenticated_telegram_provider(
            7001,
            "https://api.telegram.org",
            stored_bot_username,
        )
        assert store.create_promotion_campaign(
            campaign_code,
            campaign_kind="telegram_channel",
            now=issued_at,
        )

    def unexpected_external_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dry-run CTA preparation reached a credential/network path")

    monkeypatch.setattr(cli, "resolve_token", unexpected_external_call)
    monkeypatch.setattr(cli, "TelegramAPI", unexpected_external_call)
    base_argv = _channel_post_argv(
        db_path,
        ledger_path,
        source_links_path,
        str(envelope["signal_id"]),
        published_at,
    )
    assert cli.main(base_argv) == 0
    neutral = json.loads(capsys.readouterr().out)

    cta_argv = _channel_post_argv(
        db_path,
        ledger_path,
        source_links_path,
        str(envelope["signal_id"]),
        published_at,
        campaign_code=campaign_code,
        research_bot_username=research_bot_username,
    )
    assert cli.main(cta_argv) == 0
    with_cta = json.loads(capsys.readouterr().out)

    expected_link = build_campaign_link(stored_bot_username, campaign_code)
    expected_cta = (
        "\n\nPrivate opt-in: receive KINGDOM research alerts\n"
        f"{expected_link}\n"
        "Opening the bot does not enable alerts; opt in there. /leave stops them."
    )
    assert with_cta["network_calls"] == 0
    assert with_cta["post"]["campaign_link"] == expected_link
    assert with_cta["post"]["text"] == neutral["post"]["text"] + expected_cta
    assert with_cta["post"]["publication_id"] != neutral["post"]["publication_id"]
    assert with_cta["card"] == neutral["card"]
    assert expected_link not in json.dumps(with_cta["card"], sort_keys=True)
    assert "campaign_link" not in with_cta["card"]
    assert not ledger_path.exists()


@pytest.mark.parametrize(
    ("stored_bot_username", "error_fragment"),
    [
        (None, "no verified Telegram bot username"),
        ("DifferentResearchBot", "does not match the verified gateway binding"),
    ],
)
def test_channel_post_cta_requires_matching_verified_research_bot_before_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stored_bot_username: str | None,
    error_fragment: str,
) -> None:
    db_path = tmp_path / "gateway-private" / "gateway.db"
    ledger_path = tmp_path / "channel-private" / "channel.db"
    envelope, issued_at, published_at = _seed_signal(db_path, approve=True)
    source_links_path = tmp_path / "source-links.json"
    _write_source_links(source_links_path, issued_at + timedelta(seconds=30))
    campaign_code = generate_campaign_code()
    with GatewayStore(db_path) as store:
        if stored_bot_username is None:
            store.bind_telegram_provider(7001, "https://api.telegram.org")
        else:
            store.bind_authenticated_telegram_provider(
                7001,
                "https://api.telegram.org",
                stored_bot_username,
            )
        assert store.create_promotion_campaign(
            campaign_code,
            campaign_kind="telegram_channel",
            now=issued_at,
        )

    def unexpected_external_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid CTA binding reached a credential/network path")

    monkeypatch.setattr(cli, "resolve_token", unexpected_external_call)
    monkeypatch.setattr(cli, "TelegramAPI", unexpected_external_call)
    argv = _channel_post_argv(
        db_path,
        ledger_path,
        source_links_path,
        str(envelope["signal_id"]),
        published_at,
        campaign_code=campaign_code,
        research_bot_username="KingdomResearchBot",
    )

    assert cli.main(argv) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert error_fragment in output.err
    assert not ledger_path.exists()


@pytest.mark.parametrize(
    ("campaign_state", "include_code", "include_username", "error_fragment"),
    [
        (
            "missing",
            True,
            True,
            "campaign code is missing or disabled in this gateway",
        ),
        (
            "disabled",
            True,
            True,
            "campaign code is missing or disabled in this gateway",
        ),
        (
            "active",
            True,
            False,
            "--campaign-code and --research-bot-username must be used together",
        ),
        (
            "active",
            False,
            True,
            "--campaign-code and --research-bot-username must be used together",
        ),
    ],
)
def test_channel_post_rejects_missing_disabled_or_unpaired_campaign_before_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    campaign_state: str,
    include_code: bool,
    include_username: bool,
    error_fragment: str,
) -> None:
    db_path = tmp_path / "gateway-private" / "gateway.db"
    ledger_path = tmp_path / "channel-private" / "channel.db"
    envelope, issued_at, published_at = _seed_signal(db_path, approve=True)
    source_links_path = tmp_path / "source-links.json"
    _write_source_links(source_links_path, issued_at + timedelta(seconds=30))
    campaign_code = generate_campaign_code()
    if campaign_state != "missing":
        with GatewayStore(db_path) as store:
            assert store.create_promotion_campaign(
                campaign_code,
                campaign_kind="telegram_channel",
                now=issued_at,
            )
            if campaign_state == "disabled":
                assert store.disable_promotion_campaign(
                    campaign_code,
                    now=issued_at + timedelta(seconds=1),
                )

    def unexpected_external_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid CTA binding reached a credential/network path")

    monkeypatch.setattr(cli, "resolve_token", unexpected_external_call)
    monkeypatch.setattr(cli, "TelegramAPI", unexpected_external_call)
    argv = _channel_post_argv(
        db_path,
        ledger_path,
        source_links_path,
        str(envelope["signal_id"]),
        published_at,
        campaign_code=campaign_code if include_code else None,
        research_bot_username="KingdomResearchBot" if include_username else None,
    )

    assert cli.main(argv) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert error_fragment in output.err
    assert not ledger_path.exists()


@pytest.mark.parametrize(
    ("approve", "malformed_sources", "error_fragment"),
    [
        (False, False, "signal is missing, ambiguous, inactive, or expired"),
        (True, True, "source-links input must be a JSON list of objects"),
    ],
)
def test_channel_post_fails_closed_before_any_external_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    approve: bool,
    malformed_sources: bool,
    error_fragment: str,
) -> None:
    case = "approved" if approve else "pending"
    db_path = tmp_path / case / "gateway.db"
    ledger_path = tmp_path / case / "channel.db"
    envelope, issued_at, published_at = _seed_signal(db_path, approve=approve)
    source_links_path = tmp_path / f"{case}-sources.json"
    if malformed_sources:
        source_links_path.write_text('{"not": "a list"}', encoding="utf-8")
    else:
        _write_source_links(source_links_path, issued_at + timedelta(seconds=30))

    def unexpected_external_call(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("invalid channel input reached a credential/network path")

    monkeypatch.setattr(cli, "resolve_token", unexpected_external_call)
    monkeypatch.setattr(cli, "TelegramAPI", unexpected_external_call)

    assert (
        cli.main(
            _channel_post_argv(
                db_path,
                ledger_path,
                source_links_path,
                str(envelope["signal_id"]),
                published_at,
            )
        )
        == 1
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert error_fragment in output.err
    assert not ledger_path.exists()


def test_channel_receipt_and_reconcile_are_local_and_explicit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "gateway-private" / "gateway.db"
    ledger_path = tmp_path / "channel-private" / "channel.db"
    envelope, issued_at, published_at = _seed_signal(db_path, approve=True)
    source_links_path = tmp_path / "source-links.json"
    _write_source_links(source_links_path, issued_at + timedelta(seconds=30))
    assert (
        cli.main(
            _channel_post_argv(
                db_path,
                ledger_path,
                source_links_path,
                str(envelope["signal_id"]),
                published_at,
            )
        )
        == 0
    )
    prepared_payload = json.loads(capsys.readouterr().out)["post"]
    prepared = PreparedChannelPost(**prepared_payload)

    with ChannelPublicationLedger(ledger_path) as ledger:
        state, receipt, predecessor = ledger.claim(
            prepared,
            attempted_at=published_at + timedelta(minutes=1),
        )
        assert state == "claimed"
        assert receipt is not None and receipt.state == "pending"
        assert predecessor is None

    receipt_args = [
        "--channel-ledger",
        str(ledger_path),
        "channel-receipt",
        prepared.publication_id,
    ]
    assert cli.main(receipt_args) == 0
    pending = json.loads(capsys.readouterr().out)
    assert pending["found"] is True
    assert pending["receipt"]["state"] == "pending"
    assert pending["receipt"]["telegram_message_id"] is None

    reconcile_args = [
        "--channel-ledger",
        str(ledger_path),
        "channel-reconcile",
        prepared.publication_id,
        "--reconciliation-ref",
        "operator:telegram-history:1",
        "--sent-message-id",
        "734",
    ]
    assert cli.main(reconcile_args) == 0
    reconciled = json.loads(capsys.readouterr().out)
    assert reconciled["publication_id"] == prepared.publication_id
    assert reconciled["state"] == "sent"
    assert reconciled["telegram_message_id"] == 734

    assert cli.main(receipt_args) == 0
    final = json.loads(capsys.readouterr().out)
    assert final["receipt"]["state"] == "sent"
    assert final["receipt"]["telegram_message_id"] == 734
