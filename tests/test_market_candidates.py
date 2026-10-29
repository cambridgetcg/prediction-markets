from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone

import pytest

from telegram_gateway.market_candidates import (
    CandidateInputError,
    MAX_PAYLOAD_BYTES,
    build_candidate_report,
    candidate_report_json,
)


AS_OF = "2026-09-02T12:00:00Z"
CAPTURED = "2026-09-02T11:55:00Z"


def market(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": "market-fed-september",
        "conditionId": "condition-fed-september",
        "slug": "fed-september-decision",
        "question": "Will the Federal Reserve cut rates at its September meeting?",
        "active": True,
        "closed": False,
        "archived": False,
        "enableOrderBook": True,
        "acceptingOrders": True,
        "endDate": "2026-09-20T18:00:00Z",
        "liquidityNum": "50000.50",
        "volume24hr": "25000",
        "bestBid": "0.44",
        "bestAsk": "0.46",
        "spread": "0.02",
        "resolutionSource": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "tags": [{"slug": "fed"}, {"label": "Economy"}],
        # These execution-oriented and arbitrary fields must never be projected.
        "clobTokenIds": '["token-secret-a", "token-secret-b"]',
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.45", "0.55"]',
        "private_note": "do not distribute this arbitrary source field",
    }
    value.update(changes)
    return value


def one_candidate(
    value: dict[str, object] | None = None,
    *,
    as_of: str = AS_OF,
    snapshot_at: str | None = CAPTURED,
) -> dict[str, object]:
    report = build_candidate_report(
        [value or market()], as_of=as_of, snapshot_at=snapshot_at
    )
    return report["candidates"][0]


def test_safe_complete_market_is_manual_review_only() -> None:
    payload = json.dumps([market()]).encode()
    report = build_candidate_report(payload, as_of=AS_OF, snapshot_at=CAPTURED)
    candidate = report["candidates"][0]

    assert candidate["status"] == "MANUAL_REVIEW"
    assert candidate["score"] == 100
    assert candidate["reason_codes"] == []
    assert candidate["authority"] == {
        "mode": "RESEARCH_REVIEW_ONLY",
        "execution_allowed": False,
        "manual_review_required": True,
        "jurisdiction_verified": False,
    }
    assert report["authority"]["can_place_orders"] is False
    assert report["source"]["network_access"] is False
    assert report["source"]["payload_digest_basis"] == "input_bytes"
    assert report["source"]["payload_sha256"] == hashlib.sha256(payload).hexdigest()
    assert candidate["normalized"]["spread"] == pytest.approx(0.02)
    assert candidate["normalized"]["spread_source"] == "DERIVED_FROM_BID_ASK"

    serialized = candidate_report_json(report)
    assert "token-secret" not in serialized
    assert "private_note" not in serialized
    assert "outcomePrices" not in serialized


def test_report_json_is_canonical_and_deterministic() -> None:
    left = build_candidate_report(
        [market(id="z-market"), market(id="a-market")],
        as_of=AS_OF,
        snapshot_at=CAPTURED,
    )
    right = build_candidate_report(
        [market(id="z-market"), market(id="a-market")],
        as_of=datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
        snapshot_at=CAPTURED,
    )

    assert [item["candidate_id"] for item in left["candidates"]] == [
        "a-market",
        "z-market",
    ]
    assert candidate_report_json(left) == candidate_report_json(right)
    assert left["source"]["payload_digest_basis"] == "typed_python_json_value_v1"
    assert '"as_of": ' not in candidate_report_json(left)
    assert '}, "authority"' not in candidate_report_json(left)

    tampered = copy.deepcopy(left)
    tampered["authority"]["execution_allowed"] = True
    with pytest.raises(CandidateInputError, match="manual-review-only"):
        candidate_report_json(tampered)


def test_bounded_multi_market_report_serializes_expanded_gate_metadata() -> None:
    report = build_candidate_report(
        [market(id=f"market-{index:03d}") for index in range(200)],
        as_of=AS_OF,
        snapshot_at=CAPTURED,
        endpoint="markets",
    )

    serialized = candidate_report_json(report)
    assert len(report["candidates"]) == 200
    assert '"candidate_count":200' in serialized


def test_events_are_flattened_with_bounded_safe_context() -> None:
    payload = {
        "snapshot_at": CAPTURED,
        "events": [
            {
                "id": "event-fed",
                "title": "September central-bank decision",
                "endDate": "2026-09-20T18:00:00Z",
                "resolutionSource": "https://www.federalreserve.gov/",
                "markets": [
                    market(
                        id="market-no-own-end",
                        endDate=None,
                        resolutionSource=None,
                    )
                ],
            }
        ],
    }
    report = build_candidate_report(payload, endpoint="events", as_of=AS_OF)
    candidate = report["candidates"][0]

    assert report["source"]["endpoint"] == "/events"
    assert candidate["normalized"]["event_id"] == "event-fed"
    assert candidate["normalized"]["end_at"] == "2026-09-20T18:00:00Z"
    assert candidate["normalized"]["resolution_ref"] == "https://www.federalreserve.gov/"
    assert candidate["status"] == "MANUAL_REVIEW"


def test_tennis_future_is_excluded_from_question_language() -> None:
    candidate = one_candidate(
        market(
            id="1088472",
            question="Will Carlos Alcaraz win the 2026 Men's US Open?",
            tags=[],
        )
    )

    assert candidate["status"] == "EXCLUDED"
    assert "SPORTS_OR_ESPORTS" in candidate["reason_codes"]
    assert candidate["normalized"]["category_flags"]["sports_evidence"] == [
        "SPORT_OR_COMPETITION_LANGUAGE"
    ]


def test_markets_endpoint_uses_one_embedded_parent_event_for_sports() -> None:
    candidate = one_candidate(
        market(
            id="embedded-sports-market",
            question="Will Carlos win this competition?",
            tags=[],
            events=[
                {
                    "id": "us-open-2026",
                    "title": "2026 Men's US Open tennis championship",
                    "tags": [{"label": "Sports"}],
                    "series": [
                        {"slug": "atp-tour", "title": "ATP Tour"},
                        {"slug": "ignored-second-series"},
                    ],
                },
                {
                    "id": "ignored-second-event",
                    "title": "Politics",
                },
            ],
        )
    )

    assert candidate["status"] == "EXCLUDED"
    assert "SPORTS_OR_ESPORTS" in candidate["reason_codes"]
    assert candidate["normalized"]["event_id"] == "us-open-2026"
    assert candidate["normalized"]["event_title"] == (
        "2026 Men's US Open tennis championship"
    )
    assert candidate["normalized"]["embedded_event_metadata_used"] is True
    assert "SPORTS_SERIES_OR_CATEGORY_METADATA" in (
        candidate["normalized"]["category_flags"]["sports_evidence"]
    )


@pytest.mark.parametrize(
    "question",
    [
        "Lakers versus Celtics: who will win the game?",
        "Team Liquid vs. G2 — best-of-3 match winner",
        "Will Chelsea win the 2026 English Premier League?",
    ],
)
def test_obvious_game_matchup_and_sports_future_language_is_excluded(
    question: str,
) -> None:
    candidate = one_candidate(market(question=question, tags=[]))
    assert candidate["status"] == "EXCLUDED"
    assert "SPORTS_OR_ESPORTS" in candidate["reason_codes"]


@pytest.mark.parametrize(
    "question",
    [
        "Will the US open a new embassy in Cuba?",
        "Will Alice beat Bob in the mayoral election?",
        "Will the Supreme Court match the lower court's ruling?",
        "Will sports betting be legalized in California?",
        "Will OpenAI win the government cloud contract?",
    ],
)
def test_non_sports_word_collisions_are_not_excluded(question: str) -> None:
    candidate = one_candidate(market(question=question, tags=[]))
    assert candidate["status"] == "MANUAL_REVIEW"
    assert "SPORTS_OR_ESPORTS" not in candidate["reason_codes"]


def test_non_latency_longer_horizon_crypto_market_is_not_hard_excluded() -> None:
    candidate = one_candidate(
        market(
            question="Will Bitcoin reach $150,000 by the September meeting?",
            category="Crypto",
            endDate="2026-09-20T18:00:00Z",
        )
    )
    assert candidate["status"] == "MANUAL_REVIEW"
    assert candidate["normalized"]["category_flags"]["crypto"] is True
    assert (
        candidate["normalized"]["category_flags"]["latency_sensitive_crypto"]
        is False
    )
    assert "LATENCY_SENSITIVE_CRYPTO" not in candidate["reason_codes"]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"closed": True}, "CLOSED_OR_ARCHIVED"),
        ({"active": False}, "INACTIVE_MARKET"),
        ({"enableOrderBook": False}, "ORDER_BOOK_DISABLED"),
        ({"acceptingOrders": False}, "ORDERS_NOT_ACCEPTED"),
        ({"tags": [{"slug": "sports"}]}, "SPORTS_OR_ESPORTS"),
        ({"tags": [{"slug": "esports"}]}, "SPORTS_OR_ESPORTS"),
        ({"category": "Sports"}, "SPORTS_OR_ESPORTS"),
        (
            {
                "question": "Bitcoin up or down in the next 15 minutes?",
                "tags": [{"slug": "crypto"}],
                "endDate": "2026-09-02T12:15:00Z",
            },
            "LATENCY_SENSITIVE_CRYPTO",
        ),
        (
            {
                "question": "Will there be a major escalation this year?",
                "endDate": "2026-10-07T12:00:00Z",
            },
            "AMBIGUOUS_LONG_HORIZON",
        ),
        ({"endDate": None}, "MISSING_END_DATE"),
        ({"endDate": "not-a-date"}, "INVALID_END_DATE"),
        ({"endDate": "2026-09-03T11:59:59Z"}, "HORIZON_OUTSIDE_1_TO_45_DAYS"),
        ({"endDate": "2026-10-18T12:00:00Z"}, "HORIZON_OUTSIDE_1_TO_45_DAYS"),
        ({"liquidityNum": "24999.99"}, "THIN_LIQUIDITY"),
        ({"volume24hr": 9999}, "THIN_VOLUME_24H"),
        ({"bestBid": 0.40, "bestAsk": 0.46, "spread": 0.06}, "SPREAD_TOO_WIDE"),
        (
            {"bestBid": None, "bestAsk": None, "spread": None},
            "SPREAD_MISSING_OR_INVALID",
        ),
        ({"spread": None}, "SPREAD_MISSING_OR_INVALID"),
        (
            {"bestBid": 0.01, "bestAsk": 0.03, "spread": 0.02},
            "NEAR_ZERO_OR_ONE_WITHOUT_DEPTH_EVIDENCE",
        ),
        (
            {"bestBid": 0.97, "bestAsk": 0.99, "spread": 0.02},
            "NEAR_ZERO_OR_ONE_WITHOUT_DEPTH_EVIDENCE",
        ),
    ],
)
def test_hard_exclusion_gates(changes: dict[str, object], reason: str) -> None:
    candidate = one_candidate(market(**changes))
    assert candidate["status"] == "EXCLUDED"
    assert reason in candidate["reason_codes"]


def test_missing_required_evidence_is_incomplete_not_approved() -> None:
    candidate = one_candidate(
        market(
            resolutionSource=None,
            description=None,
            liquidityNum=None,
            volume24hr=None,
        )
    )

    assert candidate["status"] == "INCOMPLETE"
    assert set(candidate["reason_codes"]) >= {
        "RESOLUTION_EVIDENCE_MISSING",
        "LIQUIDITY_MISSING_OR_INVALID",
        "VOLUME_24H_MISSING_OR_INVALID",
    }
    assert candidate["score"] < candidate["score_max"]


def test_missing_capture_time_is_incomplete() -> None:
    candidate = one_candidate(snapshot_at=None)
    assert candidate["status"] == "INCOMPLETE"
    assert "SNAPSHOT_TIMESTAMP_MISSING" in candidate["reason_codes"]


def test_march_2026_snapshot_is_stale_in_september() -> None:
    candidate = one_candidate(snapshot_at="2026-03-15T12:00:00Z")
    assert candidate["status"] == "EXCLUDED"
    assert "STALE_SNAPSHOT" in candidate["reason_codes"]


def test_capture_time_conflict_is_incomplete() -> None:
    payload = {"snapshot_at": "2026-09-02T11:54:00Z", "markets": [market()]}
    candidate = build_candidate_report(
        payload, as_of=AS_OF, snapshot_at=CAPTURED
    )["candidates"][0]
    assert candidate["status"] == "INCOMPLETE"
    assert "SNAPSHOT_TIMESTAMP_CONFLICT" in candidate["reason_codes"]


def test_row_timestamp_cannot_override_stale_authoritative_capture() -> None:
    candidate = one_candidate(
        market(snapshotAt=CAPTURED), snapshot_at="2026-03-15T12:00:00Z"
    )
    assert candidate["status"] == "EXCLUDED"
    assert "STALE_SNAPSHOT" in candidate["reason_codes"]
    assert "SNAPSHOT_TIMESTAMP_CONFLICT" in candidate["reason_codes"]
    assert candidate["normalized"]["snapshot_at"] == "2026-03-15T12:00:00Z"


def test_rules_text_is_hashed_not_redistributed() -> None:
    secretish_rules = "Resolves from the official release after all revisions are final."
    candidate = one_candidate(
        market(resolutionSource=None, description=secretish_rules)
    )
    serialized = json.dumps(candidate)

    assert candidate["status"] == "MANUAL_REVIEW"
    assert candidate["normalized"]["resolution_evidence"] == (
        "RULES_TEXT_PRESENT_NOT_VERIFIED"
    )
    assert len(candidate["normalized"]["rules_sha256"]) == 64
    assert secretish_rules not in serialized


def test_oversized_question_is_bounded_and_not_admitted() -> None:
    candidate = one_candidate(market(question="Q" * 1_000))
    assert candidate["status"] == "INCOMPLETE"
    assert "QUESTION_EXCEEDS_SAFE_LENGTH" in candidate["reason_codes"]
    assert len(candidate["normalized"]["question"]) == 500


def test_invalid_numbers_fail_closed_without_nan_in_report() -> None:
    candidate = one_candidate(
        market(liquidityNum="NaN", volume24hr="Infinity", bestBid="1e999")
    )
    assert candidate["status"] in {"INCOMPLETE", "EXCLUDED"}
    assert "LIQUIDITY_MISSING_OR_INVALID" in candidate["reason_codes"]
    assert "VOLUME_24H_MISSING_OR_INVALID" in candidate["reason_codes"]
    assert "NaN" not in candidate_report_json(
        build_candidate_report(
            [market(liquidityNum="NaN", volume24hr="Infinity", bestBid="1e999")],
            as_of=AS_OF,
            snapshot_at=CAPTURED,
        )
    )

    with pytest.raises(CandidateInputError, match="out-of-range finite number"):
        build_candidate_report(
            [market(liquidityNum=float("nan"))],
            as_of=AS_OF,
            snapshot_at=CAPTURED,
        )


def test_spread_mismatch_is_excluded() -> None:
    candidate = one_candidate(market(bestBid=0.44, bestAsk=0.46, spread=0.20))
    assert candidate["status"] == "EXCLUDED"
    assert "SPREAD_CONFLICTS_WITH_BID_ASK" in candidate["reason_codes"]


def test_invalid_reported_spread_does_not_hide_behind_derived_spread() -> None:
    candidate = one_candidate(market(spread="NaN"))
    assert candidate["status"] == "EXCLUDED"
    assert "SPREAD_MISSING_OR_INVALID" in candidate["reason_codes"]


def test_input_bounds_and_cycles_are_rejected() -> None:
    with pytest.raises(CandidateInputError, match="byte limit"):
        build_candidate_report(
            b" " * (MAX_PAYLOAD_BYTES + 1), as_of=AS_OF, snapshot_at=CAPTURED
        )

    nested: object = None
    for _ in range(20):
        nested = [nested]
    with pytest.raises(CandidateInputError, match="maximum depth"):
        build_candidate_report(nested, as_of=AS_OF, snapshot_at=CAPTURED)

    cycle: list[object] = []
    cycle.append(cycle)
    with pytest.raises(CandidateInputError, match="cycle"):
        build_candidate_report(cycle, as_of=AS_OF, snapshot_at=CAPTURED)


def test_duplicate_json_keys_and_excess_records_are_rejected() -> None:
    duplicate = b'[{"id":"one","id":"two"}]'
    with pytest.raises(CandidateInputError, match="duplicate JSON object key"):
        build_candidate_report(duplicate, as_of=AS_OF, snapshot_at=CAPTURED)

    with pytest.raises(CandidateInputError, match="exceeds 500 records"):
        build_candidate_report(
            [{} for _ in range(501)], as_of=AS_OF, snapshot_at=CAPTURED
        )


def test_as_of_is_explicit_bounded_and_timezone_aware() -> None:
    with pytest.raises(CandidateInputError, match="include a timezone"):
        build_candidate_report([], as_of="2026-09-02T12:00:00")
    with pytest.raises(CandidateInputError, match="supported date range"):
        build_candidate_report([], as_of="2200-01-01T00:00:00Z")


def test_python_input_is_not_mutated() -> None:
    payload = {"snapshot_at": CAPTURED, "markets": [market()]}
    before = copy.deepcopy(payload)
    build_candidate_report(payload, as_of=AS_OF)
    assert payload == before
