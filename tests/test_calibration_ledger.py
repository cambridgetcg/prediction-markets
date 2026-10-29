from __future__ import annotations

import json
import math
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from telegram_gateway.calibration import (
    CALIBRATION_EVENT_SCHEMA,
    PAPER_RESEARCH_SCOPE,
    CalibrationConflictError,
    CalibrationError,
    CalibrationIntegrityError,
    CalibrationLedger,
)
from telegram_gateway.envelope import build_s012_envelope


ISSUED_AT = datetime(2026, 9, 3, 12, tzinfo=timezone.utc)
REGISTERED_AT = ISSUED_AT + timedelta(minutes=1)
RESOLVED_AT = ISSUED_AT + timedelta(hours=4)
RECORDED_RESOLUTION_AT = RESOLVED_AT + timedelta(minutes=1)
RULES_REF = "https://primary.example.test/rules/fomc-september"
OBSERVATION_REF = "observation:market:fomc:2026-09-03T12:00:00Z"
RESOLUTION_REF = "observation:resolution:fomc:2026-09-03"
EVIDENCE_DIGEST = "sha256:" + "a" * 64


def _envelope(
    *,
    signal_id: str = "signal-calibration-0001",
    direction: str = "YES",
    quoted_price: float = 0.60,
    domain: str = "ECO",
    with_sources: bool = True,
    with_rules: bool = True,
) -> dict[str, Any]:
    return build_s012_envelope(
        {
            "signal_id": signal_id,
            "assessment_id": "assessment-calibration-1",
            "event_id": "event-calibration-1",
            "market_id": "market-fomc-september",
            "market_question": "Will the FOMC cut its target range in September?",
            "signal_type": "PROSPECTIVE_BINARY",
            "direction": direction,
            "entry_price": quoted_price,
            "target_price": 0.70,
            "stop_price": 0.45,
            "time_horizon_hours": 48,
            "size_usdc": 0.0,
            "size_pct": 0.0,
            "reaction_delta": None,
            "estimated_shift": None,
            "actual_move": None,
            "confidence": 0.91,
            "reasoning": "Synthetic, prospective test forecast.",
            "domain": domain,
            "passed_concentration": True,
            "passed_anti_patterns": True,
            "risk_notes": ["Paper research only."],
            "status": "APPROVED",
            "created_at": ISSUED_AT.isoformat(),
            "expires_at": (ISSUED_AT + timedelta(hours=2)).isoformat(),
        },
        observation_refs=[OBSERVATION_REF] if with_sources else None,
        resolution_rules_ref=RULES_REF if with_rules else None,
    )


@pytest.fixture
def ledger(tmp_path: Path) -> CalibrationLedger:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    return CalibrationLedger(private / "calibration.jsonl")


def _register(
    ledger: CalibrationLedger,
    *,
    envelope: dict[str, Any] | None = None,
    probability_yes: float = 0.70,
    **kwargs: Any,
) -> dict[str, Any]:
    result = ledger.register_forecast(
        envelope or _envelope(),
        probability_yes=probability_yes,
        recorded_at=REGISTERED_AT,
        **kwargs,
    )
    assert not result.duplicate
    return dict(result.event)


def _resolve(
    ledger: CalibrationLedger,
    *,
    signal_id: str = "signal-calibration-0001",
    outcome: str = "YES",
    **kwargs: Any,
) -> dict[str, Any]:
    result = ledger.record_resolution(
        signal_id,
        outcome=outcome,
        resolved_at=RESOLVED_AT,
        resolution_evidence_refs=[RESOLUTION_REF],
        resolution_evidence_content_digest=EVIDENCE_DIGEST,
        recorded_at=RECORDED_RESOLUTION_AT,
        **kwargs,
    )
    assert not result.duplicate
    return dict(result.event)


def test_preregistration_freezes_evidence_rules_and_same_time_baseline(
    ledger: CalibrationLedger,
) -> None:
    event = _register(ledger)

    assert event["schema"] == CALIBRATION_EVENT_SCHEMA
    assert event["scope"] == PAPER_RESEARCH_SCOPE
    assert event["execution_allowed"] is False
    assert event["payload"]["forecast"] == {
        "probability_yes": 0.70,
        "probability_semantics": "binary_yes_outcome",
        "source": "explicit_preregistered_input",
        "derived_from_confidence": False,
    }
    assert event["payload"]["provenance"]["source_observation_refs"] == [
        OBSERVATION_REF
    ]
    assert event["payload"]["provenance"]["references_verified_by_ledger"] is False
    assert event["payload"]["market"]["resolution_rules_ref"] == RULES_REF
    baseline = event["payload"]["market_baseline"]
    assert baseline["available"] is True
    assert baseline["probability_yes"] == pytest.approx(0.60)
    assert baseline["observed_at"] == event["payload"]["observed_at"]
    assert baseline["observation_ref"].startswith("signal-envelope:sha256:")
    assert event["integrity"] == {
        "content_digest": event["integrity"]["content_digest"],
        "proves_authorship": False,
        "proves_truth": False,
        "proves_timestamp": False,
    }

    checkpoint = ledger.verify()
    assert checkpoint.event_count == 1
    assert checkpoint.head_digest == event["integrity"]["content_digest"]
    assert stat.S_IMODE(ledger.path.stat().st_mode) == 0o600


def test_no_direction_quote_is_converted_to_yes_baseline(
    ledger: CalibrationLedger,
) -> None:
    event = _register(
        ledger,
        envelope=_envelope(direction="NO", quoted_price=0.72),
    )
    assert event["payload"]["market_baseline"]["probability_yes"] == pytest.approx(
        0.28
    )


def test_explicit_baseline_must_link_to_same_signal_provenance(
    ledger: CalibrationLedger,
) -> None:
    event = _register(
        ledger,
        market_baseline_probability_yes=0.64,
        market_baseline_observation_ref=OBSERVATION_REF,
    )
    assert event["payload"]["market_baseline"] == {
        "available": True,
        "probability_yes": 0.64,
        "observed_at": "2026-09-03T12:00:00.000000Z",
        "source": "explicit_same_time_market_observation",
        "observation_ref": OBSERVATION_REF,
        "unavailable_reason": None,
    }

    other_private = ledger.path.parent / "other.jsonl"
    other = CalibrationLedger(other_private)
    with pytest.raises(CalibrationError, match="linked in signal provenance"):
        other.register_forecast(
            _envelope(signal_id="signal-other"),
            probability_yes=0.6,
            recorded_at=REGISTERED_AT,
            market_baseline_probability_yes=0.5,
            market_baseline_observation_ref="observation:not-in-envelope",
        )


def test_optional_missing_baseline_keeps_agent_scoring_available(
    ledger: CalibrationLedger,
) -> None:
    _register(ledger, market_baseline_probability_yes=None)
    resolution = _resolve(ledger, outcome="NO")

    scores = resolution["payload"]["scores"]
    assert scores["agent"]["brier_score"] == pytest.approx(0.49)
    assert scores["agent"]["log_loss"] == pytest.approx(-math.log(0.30))
    assert scores["market_baseline"] is None
    assert scores["comparison"] == {
        "brier_advantage_vs_market": None,
        "log_loss_advantage_vs_market": None,
        "positive_advantage_means_agent_better": True,
        "log_loss_comparison_status": "baseline_unavailable",
    }


def test_resolution_scores_agent_and_market_with_proper_rules(
    ledger: CalibrationLedger,
) -> None:
    forecast = _register(ledger, probability_yes=0.70)
    resolution = _resolve(ledger, outcome="YES")

    assert resolution["previous_event_digest"] == forecast["integrity"][
        "content_digest"
    ]
    payload = resolution["payload"]
    assert payload["forecast_event_id"] == forecast["event_id"]
    assert payload["forecast_event_digest"] == forecast["integrity"]["content_digest"]
    assert payload["resolution_rules_ref"] == RULES_REF
    assert payload["resolution_evidence_refs"] == [RESOLUTION_REF]
    assert payload["resolution_evidence_content_digest"] == EVIDENCE_DIGEST
    scores = payload["scores"]
    assert scores["definition"] == "binary_single_outcome_natural_log"
    assert scores["agent"]["brier_score"] == pytest.approx(0.09)
    assert scores["agent"]["log_loss"] == pytest.approx(-math.log(0.70))
    assert scores["market_baseline"]["brier_score"] == pytest.approx(0.16)
    assert scores["market_baseline"]["log_loss"] == pytest.approx(-math.log(0.60))
    assert scores["comparison"]["brier_advantage_vs_market"] == pytest.approx(
        0.07
    )
    assert scores["comparison"]["log_loss_advantage_vs_market"] == pytest.approx(
        -math.log(0.60) + math.log(0.70)
    )
    assert ledger.verify().event_count == 2


@pytest.mark.parametrize(
    ("probability", "outcome", "status", "log_loss"),
    [
        (1.0, "YES", "finite", 0.0),
        (1.0, "NO", "infinite_zero_probability_assigned", None),
        (0.0, "NO", "finite", 0.0),
        (0.0, "YES", "infinite_zero_probability_assigned", None),
    ],
)
def test_log_loss_preserves_infinite_certainty_penalty(
    tmp_path: Path,
    probability: float,
    outcome: str,
    status: str,
    log_loss: float | None,
) -> None:
    directory = tmp_path / f"p-{probability}-{outcome}"
    directory.mkdir(mode=0o700)
    ledger = CalibrationLedger(directory / "ledger.jsonl")
    _register(ledger, probability_yes=probability)
    event = _resolve(ledger, outcome=outcome)
    agent = event["payload"]["scores"]["agent"]
    assert agent["log_loss_status"] == status
    assert agent["log_loss"] == log_loss
    scorecard = ledger.scorecard()
    if log_loss is None:
        assert scorecard["agent"]["log_loss_status"] == "contains_infinite"
        assert scorecard["agent"]["log_loss_mean"] is None
    else:
        assert scorecard["agent"]["log_loss_status"] == "finite"
        assert scorecard["agent"]["log_loss_mean"] == 0.0


def test_forecast_requires_evidence_rules_and_valid_sealed_envelope(
    ledger: CalibrationLedger,
) -> None:
    with pytest.raises(CalibrationError, match="source_observation_refs"):
        ledger.register_forecast(
            _envelope(with_sources=False),
            probability_yes=0.5,
            recorded_at=REGISTERED_AT,
        )
    with pytest.raises(CalibrationError, match="resolution_rules_ref"):
        ledger.register_forecast(
            _envelope(with_rules=False),
            probability_yes=0.5,
            recorded_at=REGISTERED_AT,
        )

    tampered = _envelope()
    tampered["market"]["market_id"] = "changed-after-sealing"
    with pytest.raises(ValueError, match="digest"):
        ledger.register_forecast(
            tampered,
            probability_yes=0.5,
            recorded_at=REGISTERED_AT,
        )


@pytest.mark.parametrize("probability", [-0.01, 1.01, math.nan, math.inf, True])
def test_forecast_rejects_invalid_probability(
    ledger: CalibrationLedger, probability: Any
) -> None:
    with pytest.raises(CalibrationError, match="probability_yes"):
        ledger.register_forecast(
            _envelope(),
            probability_yes=probability,
            recorded_at=REGISTERED_AT,
        )


def test_forecast_is_prospective_and_must_be_registered_while_live(
    ledger: CalibrationLedger,
) -> None:
    with pytest.raises(CalibrationError, match="before signal issuance"):
        ledger.register_forecast(
            _envelope(),
            probability_yes=0.5,
            recorded_at=ISSUED_AT - timedelta(microseconds=1),
        )
    with pytest.raises(CalibrationError, match="before signal expiry"):
        ledger.register_forecast(
            _envelope(),
            probability_yes=0.5,
            recorded_at=ISSUED_AT + timedelta(hours=2, microseconds=1),
        )
    assert ledger.verify().event_count == 0


def test_resolution_rejects_hindsight_and_missing_evidence(
    ledger: CalibrationLedger,
) -> None:
    _register(ledger)
    with pytest.raises(CalibrationError, match="hindsight"):
        ledger.record_resolution(
            "signal-calibration-0001",
            outcome="YES",
            resolved_at=ISSUED_AT + timedelta(seconds=30),
            resolution_evidence_refs=[RESOLUTION_REF],
            resolution_evidence_content_digest=EVIDENCE_DIGEST,
            recorded_at=REGISTERED_AT + timedelta(minutes=1),
        )
    with pytest.raises(CalibrationError, match="before it occurred"):
        ledger.record_resolution(
            "signal-calibration-0001",
            outcome="YES",
            resolved_at=RESOLVED_AT,
            resolution_evidence_refs=[RESOLUTION_REF],
            resolution_evidence_content_digest=EVIDENCE_DIGEST,
            recorded_at=RESOLVED_AT - timedelta(microseconds=1),
        )
    with pytest.raises(CalibrationError, match="at least one"):
        ledger.record_resolution(
            "signal-calibration-0001",
            outcome="YES",
            resolved_at=RESOLVED_AT,
            resolution_evidence_refs=[],
            resolution_evidence_content_digest=EVIDENCE_DIGEST,
            recorded_at=RECORDED_RESOLUTION_AT,
        )
    with pytest.raises(CalibrationError, match="sha256"):
        ledger.record_resolution(
            "signal-calibration-0001",
            outcome="YES",
            resolved_at=RESOLVED_AT,
            resolution_evidence_refs=[RESOLUTION_REF],
            resolution_evidence_content_digest="not-a-digest",
            recorded_at=RECORDED_RESOLUTION_AT,
        )


def test_registration_and_resolution_are_idempotent_but_conflicts_fail(
    ledger: CalibrationLedger,
) -> None:
    first = ledger.register_forecast(
        _envelope(), probability_yes=0.7, recorded_at=REGISTERED_AT
    )
    duplicate = ledger.register_forecast(
        _envelope(), probability_yes=0.7, recorded_at=REGISTERED_AT
    )
    assert duplicate.duplicate
    assert duplicate.event == first.event
    with pytest.raises(CalibrationConflictError, match="different preregistered"):
        ledger.register_forecast(
            _envelope(), probability_yes=0.71, recorded_at=REGISTERED_AT
        )

    resolution = ledger.record_resolution(
        "signal-calibration-0001",
        outcome="YES",
        resolved_at=RESOLVED_AT,
        resolution_evidence_refs=[RESOLUTION_REF],
        resolution_evidence_content_digest=EVIDENCE_DIGEST,
        recorded_at=RECORDED_RESOLUTION_AT,
    )
    repeated = ledger.record_resolution(
        "signal-calibration-0001",
        outcome="YES",
        resolved_at=RESOLVED_AT,
        resolution_evidence_refs=[RESOLUTION_REF],
        resolution_evidence_content_digest=EVIDENCE_DIGEST,
        recorded_at=RECORDED_RESOLUTION_AT,
    )
    assert repeated.duplicate
    assert repeated.event == resolution.event
    with pytest.raises(CalibrationConflictError, match="different recorded resolution"):
        ledger.record_resolution(
            "signal-calibration-0001",
            outcome="NO",
            resolved_at=RESOLVED_AT,
            resolution_evidence_refs=[RESOLUTION_REF],
            resolution_evidence_content_digest=EVIDENCE_DIGEST,
            recorded_at=RECORDED_RESOLUTION_AT,
        )
    assert ledger.verify().event_count == 2


def test_resolution_requires_a_prior_forecast(ledger: CalibrationLedger) -> None:
    with pytest.raises(CalibrationError, match="prior registered forecast"):
        _resolve(ledger)


def test_scorecard_aggregates_baseline_advantage_and_calibration_buckets(
    ledger: CalibrationLedger,
) -> None:
    _register(ledger, probability_yes=0.70)
    _resolve(ledger, outcome="YES")

    second = _envelope(
        signal_id="signal-calibration-0002",
        quoted_price=0.40,
        domain="ECO",
    )
    ledger.register_forecast(
        second,
        probability_yes=0.20,
        recorded_at=REGISTERED_AT,
    )
    ledger.record_resolution(
        "signal-calibration-0002",
        outcome="NO",
        resolved_at=RESOLVED_AT,
        resolution_evidence_refs=["observation:resolution:second"],
        resolution_evidence_content_digest="sha256:" + "b" * 64,
        recorded_at=RECORDED_RESOLUTION_AT,
    )

    third = _envelope(signal_id="signal-calibration-0003", domain="GEO")
    ledger.register_forecast(
        third,
        probability_yes=0.50,
        recorded_at=REGISTERED_AT,
        market_baseline_probability_yes=None,
    )

    scorecard = ledger.scorecard()
    assert scorecard["scope"] == PAPER_RESEARCH_SCOPE
    assert scorecard["execution_allowed"] is False
    assert scorecard["counts"] == {
        "registered_forecasts": 3,
        "resolved_forecasts": 2,
        "unresolved_forecasts": 1,
        "resolved_yes": 1,
        "resolved_no": 1,
        "market_baseline_coverage": 2,
    }
    assert scorecard["agent"]["brier_mean"] == pytest.approx((0.09 + 0.04) / 2)
    assert scorecard["market_baseline"]["brier_mean"] == pytest.approx(
        (0.16 + 0.16) / 2
    )
    assert scorecard["comparison"]["mean_brier_advantage_vs_market"] == pytest.approx(
        ((0.16 - 0.09) + (0.16 - 0.04)) / 2
    )
    assert [bucket["count"] for bucket in scorecard["calibration_buckets"]] == [1, 1]
    assert scorecard["ledger"]["event_count"] == 5

    eco = ledger.scorecard(domain="eco")
    assert eco["filter"] == {"domain": "ECO"}
    assert eco["counts"]["registered_forecasts"] == 2
    assert eco["counts"]["resolved_forecasts"] == 2
    geo = ledger.scorecard(domain="GEO")
    assert geo["counts"]["registered_forecasts"] == 1
    assert geo["counts"]["unresolved_forecasts"] == 1
    assert geo["agent"]["brier_mean"] is None


def test_content_tampering_and_partial_rows_fail_closed(
    ledger: CalibrationLedger,
) -> None:
    _register(ledger)
    raw = ledger.path.read_text(encoding="utf-8")
    ledger.path.write_text(raw.replace('"probability_yes":0.7', '"probability_yes":0.8'), encoding="utf-8")
    os.chmod(ledger.path, 0o600)
    with pytest.raises(CalibrationIntegrityError, match="event ID|digest"):
        ledger.verify()

    other = CalibrationLedger(ledger.path.parent / "partial.jsonl")
    with other.path.open("ab") as handle:
        handle.write(b'{"schema":"incomplete"}')
    with pytest.raises(CalibrationIntegrityError, match="partial trailing row"):
        other.verify()


def test_external_checkpoint_detects_valid_prefix_truncation(
    ledger: CalibrationLedger,
) -> None:
    _register(ledger)
    forecast_checkpoint = ledger.verify()
    _resolve(ledger)
    complete_checkpoint = ledger.verify()
    assert ledger.verify(expected_checkpoint=forecast_checkpoint) == complete_checkpoint
    lines = ledger.path.read_bytes().splitlines(keepends=True)
    ledger.path.write_bytes(lines[0])
    os.chmod(ledger.path, 0o600)

    assert ledger.verify().event_count == 1
    with pytest.raises(CalibrationIntegrityError, match="external checkpoint"):
        ledger.verify(expected_checkpoint=complete_checkpoint)


def test_detached_events_cannot_mutate_the_ledger(ledger: CalibrationLedger) -> None:
    _register(ledger)
    returned = ledger.events()
    returned[0]["payload"]["forecast"]["probability_yes"] = 0.01
    assert ledger.events()[0]["payload"]["forecast"]["probability_yes"] == 0.70


def test_existing_permissive_file_or_directory_is_rejected(tmp_path: Path) -> None:
    permissive = tmp_path / "permissive"
    permissive.mkdir(mode=0o755)
    with pytest.raises(PermissionError, match="directory"):
        CalibrationLedger(permissive / "ledger.jsonl")

    private = tmp_path / "private-mode"
    private.mkdir(mode=0o700)
    path = private / "ledger.jsonl"
    path.touch(mode=0o644)
    with pytest.raises(PermissionError, match="ledger must be owner-only"):
        CalibrationLedger(path)


def test_jsonl_is_canonical_and_one_complete_object_per_line(
    ledger: CalibrationLedger,
) -> None:
    _register(ledger)
    _resolve(ledger)
    raw = ledger.path.read_bytes()
    assert raw.endswith(b"\n")
    lines = raw.splitlines()
    assert len(lines) == 2
    for line in lines:
        decoded = line.decode("utf-8")
        parsed = json.loads(decoded)
        assert decoded == json.dumps(
            parsed,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
