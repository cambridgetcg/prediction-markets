from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import pytest

from telegram_gateway.channel_cards import (
    MAX_CHANNEL_TEXT,
    ChannelCardError,
    build_editorial_event,
    build_research_card,
    build_status_card,
    canonical_card_json,
    render_channel_card,
    validate_channel_card,
    validate_editorial_event,
    validate_successor,
    verify_channel_card,
)
from telegram_gateway.envelope import build_s012_envelope


def _lifecycle_event(signal_id: str, at: datetime) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema": "s012.signal-lifecycle/0.1",
        "signal_id": signal_id,
        "revision": 1,
        "previous_status": "PENDING",
        "status": "APPROVED",
        "occurred_at": at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
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


@pytest.fixture
def times() -> dict[str, datetime]:
    issued = datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc)
    return {
        "observed": issued - timedelta(minutes=5),
        "issued": issued,
        "approved": issued + timedelta(minutes=1),
        "published": issued + timedelta(minutes=2),
        "expires": issued + timedelta(hours=12),
    }


@pytest.fixture
def envelope(times: Mapping[str, datetime]) -> dict[str, Any]:
    signal = {
        "signal_id": "signal-channel-abcdef12",
        "assessment_id": "assessment-1",
        "event_id": "event-1",
        "market_id": "market-fed-september",
        "market_question": "Will the Fed cut at its September meeting?",
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
        "reasoning": "The primary release moved the base case. https://untrusted.test/x",
        "domain": "ECO",
        "passed_concentration": True,
        "passed_anti_patterns": True,
        "risk_notes": ["Resolution wording still needs independent review."],
        "status": "PENDING",
        "created_at": times["issued"].isoformat(),
        "expires_at": times["expires"].isoformat(),
    }
    return build_s012_envelope(
        signal,
        observation_refs=["obs-fomc-001", "obs-cme-002"],
        resolution_rules_ref="https://polymarket.com/event/fed-september",
        model_ref="model:test",
    )


@pytest.fixture
def sources(times: Mapping[str, datetime]) -> list[dict[str, Any]]:
    return [
        {
            "observation_ref": "obs-fomc-001",
            "label": "Federal Reserve calendar",
            "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            "observed_at": times["observed"],
            "is_primary": True,
        },
        {
            "observation_ref": "obs-cme-002",
            "label": "CME rate probabilities",
            "url": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
            "observed_at": times["observed"],
            "is_primary": False,
        },
    ]


@pytest.fixture
def card(
    envelope: Mapping[str, Any],
    sources: list[dict[str, Any]],
    times: Mapping[str, datetime],
) -> dict[str, Any]:
    return build_research_card(
        envelope,
        _lifecycle_event(str(envelope["signal_id"]), times["approved"]),
        source_links=sources,
        market_url="https://polymarket.com/event/fed-september",
        published_at=times["published"],
    )


def test_research_card_is_stable_evidence_labelled_and_paper_only(
    card: Mapping[str, Any],
    envelope: Mapping[str, Any],
) -> None:
    validate_channel_card(card)
    assert verify_channel_card(card)
    assert card["revision"] == 1
    assert card["lineage"]["root_card_id"] == card["card_id"]
    assert card["lineage"]["supersedes_card_id"] is None
    assert card["authority"] == {
        "mode": "information_only",
        "execution_allowed": False,
        "paper_only": True,
        "wallet_access": False,
        "jurisdiction_verified": False,
    }
    assert card["integrity"]["source_envelope_digest"] == envelope["integrity"][
        "content_digest"
    ]
    assert [source["observation_ref"] for source in card["evidence"]["sources"]] == [
        "obs-fomc-001",
        "obs-cme-002",
    ]


def test_same_approved_material_produces_same_card(
    card: Mapping[str, Any],
    envelope: Mapping[str, Any],
    sources: list[dict[str, Any]],
    times: Mapping[str, datetime],
) -> None:
    rebuilt = build_research_card(
        envelope,
        _lifecycle_event(str(envelope["signal_id"]), times["approved"]),
        source_links=list(reversed(sources)),
        market_url="https://polymarket.com/event/fed-september",
        published_at=times["published"],
    )
    assert rebuilt == card
    assert canonical_card_json(rebuilt) == canonical_card_json(card)


def test_render_is_forward_safe_and_only_validated_links_are_clickable(
    card: Mapping[str, Any],
) -> None:
    rendered = render_channel_card(card)
    assert len(rendered) <= MAX_CHANNEL_TEXT
    assert "KINGDOM RESEARCH • ACTIVE" in rendered
    assert "https://www.federalreserve.gov/" in rendered
    assert "https://polymarket.com/event/fed-september" in rendered
    assert "https://untrusted.test" not in rendered
    assert "hxxps://untrusted.test" in rendered
    assert "No trade was placed" in rendered
    assert "live execution and wallet access are disabled" in rendered


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda item: item["research"].update({"confidence": 0.99}), "digest"),
        (lambda item: item["authority"].update({"execution_allowed": True}), "paper-only"),
        (lambda item: item["lineage"].update({"root_card_id": "bad"}), "root_card_id"),
    ],
)
def test_tampering_is_rejected(
    card: Mapping[str, Any], mutator: Any, message: str
) -> None:
    changed = copy.deepcopy(card)
    mutator(changed)
    with pytest.raises(ChannelCardError, match=message):
        validate_channel_card(changed)


def test_research_card_requires_approved_matching_review(
    envelope: Mapping[str, Any],
    sources: list[dict[str, Any]],
    times: Mapping[str, datetime],
) -> None:
    approval = _lifecycle_event("another-signal", times["approved"])
    with pytest.raises(ChannelCardError, match="signal IDs differ"):
        build_research_card(
            envelope,
            approval,
            source_links=sources,
            market_url="https://polymarket.com/event/fed-september",
            published_at=times["published"],
        )


@pytest.mark.parametrize(
    ("source_change", "error"),
    [
        ({"url": "http://example.com/source"}, "absolute HTTPS"),
        ({"observation_ref": "not-sealed"}, "not present"),
        ({"observed_at": datetime(2027, 1, 1, tzinfo=timezone.utc)}, "postdate"),
    ],
)
def test_research_card_rejects_unsafe_or_unsealed_evidence(
    envelope: Mapping[str, Any],
    sources: list[dict[str, Any]],
    times: Mapping[str, datetime],
    source_change: Mapping[str, Any],
    error: str,
) -> None:
    changed_sources = copy.deepcopy(sources)
    changed_sources[0].update(source_change)
    with pytest.raises(ChannelCardError, match=error):
        build_research_card(
            envelope,
            _lifecycle_event(str(envelope["signal_id"]), times["approved"]),
            source_links=changed_sources,
            market_url="https://polymarket.com/event/fed-september",
            published_at=times["published"],
        )


def test_official_market_link_cannot_be_replaced_with_a_lookalike(
    envelope: Mapping[str, Any],
    sources: list[dict[str, Any]],
    times: Mapping[str, datetime],
) -> None:
    with pytest.raises(ChannelCardError, match="official Polymarket"):
        build_research_card(
            envelope,
            _lifecycle_event(str(envelope["signal_id"]), times["approved"]),
            source_links=sources,
            market_url="https://polymarket.com.evil.example/event/fed",
            published_at=times["published"],
        )


def test_status_card_is_append_only_and_does_not_repeat_withdrawn_analysis(
    card: Mapping[str, Any], times: Mapping[str, datetime]
) -> None:
    event = build_editorial_event(
        card,
        status="WITHDRAWN",
        occurred_at=times["published"] + timedelta(minutes=10),
        actor_kind="local_operator",
        reason_code="source_conflict",
        summary="A primary source contradicted the earlier interpretation.",
    )
    successor = build_status_card(card, event)
    validate_successor(card, successor)
    assert successor["revision"] == 2
    assert successor["research"] is None
    assert successor["lineage"]["supersedes_card_id"] == card["card_id"]
    rendered = render_channel_card(successor)
    assert "KINGDOM STATUS • WITHDRAWN" in rendered
    assert "The superseded research is not repeated" in rendered
    assert "moved the base case" not in rendered
    assert card["card_id"] in rendered


def test_editorial_event_is_content_bound(card: Mapping[str, Any]) -> None:
    event = build_editorial_event(
        card,
        status="AMENDED",
        occurred_at="2026-09-03T09:00:00Z",
        actor_kind="local_operator",
        reason_code="clarified_wording",
        summary="Clarified the evidence limitation; forecast unchanged.",
    )
    changed = copy.deepcopy(event)
    changed["summary"] = "A different claim."
    with pytest.raises(ChannelCardError, match="does not match"):
        validate_editorial_event(changed)


def test_resolved_card_requires_a_resolution_source(
    card: Mapping[str, Any], times: Mapping[str, datetime]
) -> None:
    event = build_editorial_event(
        card,
        status="RESOLVED",
        occurred_at=times["published"] + timedelta(hours=1),
        actor_kind="resolution_agent",
        reason_code="official_outcome",
        summary="The official decision was published.",
    )
    with pytest.raises(ChannelCardError, match="requires an evidence link"):
        build_status_card(card, event)


def test_terminal_card_cannot_receive_another_editorial_event(
    card: Mapping[str, Any], times: Mapping[str, datetime]
) -> None:
    event = build_editorial_event(
        card,
        status="WITHDRAWN",
        occurred_at=times["published"] + timedelta(minutes=10),
        actor_kind="local_operator",
        reason_code="source_conflict",
        summary="Withdrawn after review.",
    )
    withdrawn = build_status_card(card, event)
    with pytest.raises(ChannelCardError, match="terminal"):
        build_editorial_event(
            withdrawn,
            status="AMENDED",
            occurred_at=times["published"] + timedelta(minutes=20),
            actor_kind="local_operator",
            reason_code="retry",
            summary="This transition is not permitted.",
        )
