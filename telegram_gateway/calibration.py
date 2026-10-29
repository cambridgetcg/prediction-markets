"""Append-only prospective calibration records for paper research signals.

This module deliberately keeps forecast evaluation separate from Telegram
delivery and from any trading capability.  It records an explicit binary YES
probability before resolution, optionally captures a same-time market-price
baseline, and later appends an evidence-linked outcome with proper scores.

The JSONL ledger is hash chained.  That makes accidental edits detectable and
allows callers to retain a small external checkpoint that detects truncation.
The hashes do not prove authorship, truth, or that a timestamp came from a
trusted clock.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Mapping, Sequence

from .envelope import validate_envelope


CALIBRATION_EVENT_SCHEMA = "kingdom.calibration-event/0.1"
CALIBRATION_SCORECARD_SCHEMA = "kingdom.calibration-scorecard/0.1"
PAPER_RESEARCH_SCOPE = "paper_research_only"
MAX_RECORD_BYTES = 65_536
MAX_LEDGER_BYTES = 256 * 1024 * 1024

_EVENT_KEYS = frozenset(
    {
        "schema",
        "event_id",
        "sequence",
        "previous_event_digest",
        "event_type",
        "recorded_at",
        "scope",
        "execution_allowed",
        "payload",
        "integrity",
    }
)
_INTEGRITY_KEYS = frozenset(
    {
        "content_digest",
        "proves_authorship",
        "proves_truth",
        "proves_timestamp",
    }
)
_EVENT_TYPES = frozenset({"forecast_registered", "outcome_resolved"})
_CANONICAL_UTC_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z"
)
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_EVENT_ID_RE = re.compile(r"cal-(?:forecast|outcome)-[0-9a-f]{32}\Z")
_USE_ENVELOPE_BASELINE = object()


class CalibrationError(ValueError):
    """A forecast or outcome violates the calibration contract."""


class CalibrationConflictError(CalibrationError):
    """A signal already has a different immutable forecast or outcome."""


class CalibrationIntegrityError(CalibrationError):
    """The stored ledger cannot prove its expected local hash chain."""


@dataclass(frozen=True)
class LedgerCheckpoint:
    """Small externally anchorable description of one complete ledger head."""

    event_count: int
    head_digest: str | None


@dataclass(frozen=True)
class AppendResult:
    """Result of an idempotent append operation."""

    event: Mapping[str, Any]
    duplicate: bool = False


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _timestamp(value: datetime | str, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CalibrationError(f"{name} must be an ISO-8601 timestamp") from exc
    else:
        raise CalibrationError(f"{name} must be a timezone-aware timestamp")
    if parsed.tzinfo is None:
        raise CalibrationError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | str, name: str) -> str:
    return _timestamp(value, name).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _validate_canonical_timestamp(value: Any, name: str) -> str:
    if not isinstance(value, str) or _CANONICAL_UTC_RE.fullmatch(value) is None:
        raise CalibrationIntegrityError(
            f"{name} must be canonical UTC with microseconds"
        )
    _timestamp(value, name)
    return value


def _bounded_string(value: Any, name: str, *, maximum: int = 2_048) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CalibrationError(f"{name} must be a non-empty canonical string")
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise CalibrationError(f"{name} must be valid UTF-8") from exc
    if len(encoded) > maximum or any(
        unicodedata.category(character).startswith("C") for character in value
    ):
        raise CalibrationError(f"{name} exceeds its safe text bounds")
    return value


def _probability(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationError(f"{name} must be a number between 0 and 1")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise CalibrationError(f"{name} must be a finite number between 0 and 1")
    return result


def _reference_list(
    values: Any,
    name: str,
    *,
    required: bool,
) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise CalibrationError(f"{name} must be a sequence of references")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        reference = _bounded_string(value, name, maximum=1_024)
        if reference in seen:
            raise CalibrationError(f"{name} must not contain duplicates")
        seen.add(reference)
        result.append(reference)
    if required and not result:
        raise CalibrationError(f"{name} must contain at least one reference")
    return result


def _duplicate_safe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CalibrationIntegrityError("ledger JSON contains a duplicate key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> Any:
    raise CalibrationIntegrityError("ledger JSON contains a non-finite constant")


def _event_id_material(event: Mapping[str, Any]) -> dict[str, Any]:
    material = copy.deepcopy(dict(event))
    material.pop("event_id", None)
    material.pop("integrity", None)
    return material


def _event_content_material(event: Mapping[str, Any]) -> dict[str, Any]:
    material = copy.deepcopy(dict(event))
    material.pop("integrity", None)
    return material


def _event_digest(event: Mapping[str, Any]) -> str:
    return _sha256(_canonical_json(_event_content_material(event)).encode("utf-8"))


def _seal_event(event: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(event))
    event_type = result.get("event_type")
    prefix = "forecast" if event_type == "forecast_registered" else "outcome"
    identity_digest = hashlib.sha256(
        _canonical_json(_event_id_material(result)).encode("utf-8")
    ).hexdigest()
    result["event_id"] = f"cal-{prefix}-{identity_digest[:32]}"
    result["integrity"] = {
        "content_digest": _event_digest(result),
        "proves_authorship": False,
        "proves_truth": False,
        "proves_timestamp": False,
    }
    _validate_event(result)
    return result


def _require_exact_keys(
    value: Mapping[str, Any], expected: frozenset[str], name: str
) -> None:
    keys = frozenset(value)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        detail = "missing " + ", ".join(missing) if missing else "extra " + ", ".join(extra)
        raise CalibrationIntegrityError(f"{name} has unsupported shape ({detail})")


def _validate_forecast_payload(payload: Mapping[str, Any]) -> None:
    expected = frozenset(
        {
            "signal_id",
            "signal_envelope_digest",
            "issued_at",
            "expires_at",
            "observed_at",
            "market",
            "provenance",
            "forecast",
            "market_baseline",
        }
    )
    _require_exact_keys(payload, expected, "forecast payload")
    _bounded_string(payload.get("signal_id"), "signal_id", maximum=256)
    digest = payload.get("signal_envelope_digest")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise CalibrationIntegrityError("signal envelope digest is invalid")
    issued_at = _validate_canonical_timestamp(payload.get("issued_at"), "issued_at")
    expires_at = _validate_canonical_timestamp(payload.get("expires_at"), "expires_at")
    observed_at = _validate_canonical_timestamp(payload.get("observed_at"), "observed_at")
    if observed_at != issued_at:
        raise CalibrationIntegrityError("forecast observation must match signal issuance")
    if _timestamp(expires_at, "expires_at") <= _timestamp(issued_at, "issued_at"):
        raise CalibrationIntegrityError("forecast expiry must follow issuance")

    market = payload.get("market")
    if not isinstance(market, Mapping):
        raise CalibrationIntegrityError("forecast market must be an object")
    _require_exact_keys(
        market,
        frozenset(
            {
                "venue",
                "market_id",
                "question_digest",
                "domain",
                "direction",
                "resolution_rules_ref",
                "resolution_rules_status",
            }
        ),
        "forecast market",
    )
    if market.get("venue") != "polymarket":
        raise CalibrationIntegrityError("forecast market venue is invalid")
    _bounded_string(market.get("market_id"), "market.market_id", maximum=512)
    question_digest = market.get("question_digest")
    if not isinstance(question_digest, str) or _SHA256_RE.fullmatch(question_digest) is None:
        raise CalibrationIntegrityError("market question digest is invalid")
    _bounded_string(market.get("domain"), "market.domain", maximum=64)
    if market.get("direction") not in {"YES", "NO"}:
        raise CalibrationIntegrityError("market direction is invalid")
    _bounded_string(
        market.get("resolution_rules_ref"),
        "market.resolution_rules_ref",
        maximum=2_048,
    )
    if market.get("resolution_rules_status") not in {
        "reference_present_not_verified",
        "reference_present_verified_elsewhere",
    }:
        raise CalibrationIntegrityError("market rule-reference status is invalid")

    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise CalibrationIntegrityError("forecast provenance must be an object")
    _require_exact_keys(
        provenance,
        frozenset(
            {
                "source_observation_refs",
                "source_status",
                "references_verified_by_ledger",
            }
        ),
        "forecast provenance",
    )
    _reference_list(
        provenance.get("source_observation_refs"),
        "source_observation_refs",
        required=True,
    )
    if provenance.get("source_status") != "references_present_not_verified":
        raise CalibrationIntegrityError("forecast source status is invalid")
    if provenance.get("references_verified_by_ledger") is not False:
        raise CalibrationIntegrityError("ledger must not claim source verification")

    forecast = payload.get("forecast")
    if not isinstance(forecast, Mapping):
        raise CalibrationIntegrityError("forecast probability must be an object")
    _require_exact_keys(
        forecast,
        frozenset(
            {
                "probability_yes",
                "probability_semantics",
                "source",
                "derived_from_confidence",
            }
        ),
        "forecast probability",
    )
    _probability(forecast.get("probability_yes"), "forecast.probability_yes")
    if forecast.get("probability_semantics") != "binary_yes_outcome":
        raise CalibrationIntegrityError("forecast probability semantics are invalid")
    if forecast.get("source") != "explicit_preregistered_input":
        raise CalibrationIntegrityError("forecast probability source is invalid")
    if forecast.get("derived_from_confidence") is not False:
        raise CalibrationIntegrityError("confidence must not become a forecast probability")

    baseline = payload.get("market_baseline")
    if not isinstance(baseline, Mapping):
        raise CalibrationIntegrityError("market baseline must be an object")
    _require_exact_keys(
        baseline,
        frozenset(
            {
                "available",
                "probability_yes",
                "observed_at",
                "source",
                "observation_ref",
                "unavailable_reason",
            }
        ),
        "market baseline",
    )
    if baseline.get("observed_at") != observed_at:
        raise CalibrationIntegrityError("market baseline must share forecast observation time")
    if baseline.get("available") is True:
        _probability(
            baseline.get("probability_yes"), "market_baseline.probability_yes"
        )
        _bounded_string(baseline.get("source"), "market_baseline.source", maximum=128)
        _bounded_string(
            baseline.get("observation_ref"),
            "market_baseline.observation_ref",
            maximum=1_024,
        )
        if baseline.get("unavailable_reason") is not None:
            raise CalibrationIntegrityError("available baseline has an unavailable reason")
        if baseline.get("source") == "sealed_signal_outcome_token_quote":
            if baseline.get("observation_ref") != (
                "signal-envelope:" + str(payload["signal_envelope_digest"])
            ):
                raise CalibrationIntegrityError(
                    "envelope baseline does not link the sealed signal"
                )
        elif baseline.get("source") == "explicit_same_time_market_observation":
            if baseline.get("observation_ref") not in provenance[
                "source_observation_refs"
            ]:
                raise CalibrationIntegrityError(
                    "explicit baseline is absent from signal provenance"
                )
        else:
            raise CalibrationIntegrityError("market baseline source is invalid")
    elif baseline.get("available") is False:
        if baseline.get("probability_yes") is not None:
            raise CalibrationIntegrityError("unavailable baseline has a probability")
        if baseline.get("source") is not None or baseline.get("observation_ref") is not None:
            raise CalibrationIntegrityError("unavailable baseline has source claims")
        if baseline.get("unavailable_reason") != "not_captured_same_time":
            raise CalibrationIntegrityError("unavailable baseline reason is invalid")
    else:
        raise CalibrationIntegrityError("market baseline availability must be boolean")


def _validate_score(value: Any, name: str) -> None:
    if not isinstance(value, Mapping):
        raise CalibrationIntegrityError(f"{name} score must be an object")
    _require_exact_keys(
        value,
        frozenset(
            {
                "probability_yes",
                "brier_score",
                "log_loss",
                "log_loss_status",
            }
        ),
        f"{name} score",
    )
    probability = _probability(value.get("probability_yes"), f"{name}.probability_yes")
    brier = value.get("brier_score")
    if isinstance(brier, bool) or not isinstance(brier, (int, float)):
        raise CalibrationIntegrityError(f"{name} Brier score is invalid")
    if not math.isfinite(float(brier)) or not 0.0 <= float(brier) <= 1.0:
        raise CalibrationIntegrityError(f"{name} Brier score is invalid")
    status = value.get("log_loss_status")
    if status == "finite":
        log_loss = value.get("log_loss")
        if isinstance(log_loss, bool) or not isinstance(log_loss, (int, float)):
            raise CalibrationIntegrityError(f"{name} log loss is invalid")
        if not math.isfinite(float(log_loss)) or float(log_loss) < 0.0:
            raise CalibrationIntegrityError(f"{name} log loss is invalid")
    elif status == "infinite_zero_probability_assigned":
        if value.get("log_loss") is not None or probability not in {0.0, 1.0}:
            raise CalibrationIntegrityError(f"{name} infinite log-loss state is invalid")
    else:
        raise CalibrationIntegrityError(f"{name} log-loss status is invalid")


def _validate_outcome_payload(payload: Mapping[str, Any]) -> None:
    _require_exact_keys(
        payload,
        frozenset(
            {
                "signal_id",
                "forecast_event_id",
                "forecast_event_digest",
                "resolved_at",
                "outcome",
                "resolution_rules_ref",
                "resolution_evidence_refs",
                "resolution_evidence_content_digest",
                "scores",
            }
        ),
        "outcome payload",
    )
    _bounded_string(payload.get("signal_id"), "signal_id", maximum=256)
    event_id = payload.get("forecast_event_id")
    if not isinstance(event_id, str) or not event_id.startswith("cal-forecast-"):
        raise CalibrationIntegrityError("forecast event reference is invalid")
    forecast_digest = payload.get("forecast_event_digest")
    if not isinstance(forecast_digest, str) or _SHA256_RE.fullmatch(forecast_digest) is None:
        raise CalibrationIntegrityError("forecast event digest is invalid")
    _validate_canonical_timestamp(payload.get("resolved_at"), "resolved_at")
    if payload.get("outcome") not in {"YES", "NO"}:
        raise CalibrationIntegrityError("resolved outcome must be YES or NO")
    _bounded_string(
        payload.get("resolution_rules_ref"),
        "resolution_rules_ref",
        maximum=2_048,
    )
    _reference_list(
        payload.get("resolution_evidence_refs"),
        "resolution_evidence_refs",
        required=True,
    )
    evidence_digest = payload.get("resolution_evidence_content_digest")
    if not isinstance(evidence_digest, str) or _SHA256_RE.fullmatch(evidence_digest) is None:
        raise CalibrationIntegrityError("resolution evidence digest is invalid")

    scores = payload.get("scores")
    if not isinstance(scores, Mapping):
        raise CalibrationIntegrityError("outcome scores must be an object")
    _require_exact_keys(
        scores,
        frozenset({"definition", "agent", "market_baseline", "comparison"}),
        "outcome scores",
    )
    if scores.get("definition") != "binary_single_outcome_natural_log":
        raise CalibrationIntegrityError("outcome score definition is invalid")
    _validate_score(scores.get("agent"), "agent")
    baseline = scores.get("market_baseline")
    if baseline is not None:
        _validate_score(baseline, "market baseline")
    comparison = scores.get("comparison")
    if not isinstance(comparison, Mapping):
        raise CalibrationIntegrityError("score comparison must be an object")
    _require_exact_keys(
        comparison,
        frozenset(
            {
                "brier_advantage_vs_market",
                "log_loss_advantage_vs_market",
                "positive_advantage_means_agent_better",
                "log_loss_comparison_status",
            }
        ),
        "score comparison",
    )
    if comparison.get("positive_advantage_means_agent_better") is not True:
        raise CalibrationIntegrityError("score comparison direction is invalid")
    for name in ("brier_advantage_vs_market", "log_loss_advantage_vs_market"):
        metric = comparison.get(name)
        if metric is not None and (
            isinstance(metric, bool)
            or not isinstance(metric, (int, float))
            or not math.isfinite(float(metric))
        ):
            raise CalibrationIntegrityError(f"{name} is invalid")
    if comparison.get("log_loss_comparison_status") not in {
        "finite",
        "agent_better_baseline_infinite",
        "market_better_agent_infinite",
        "both_infinite",
        "baseline_unavailable",
    }:
        raise CalibrationIntegrityError("log-loss comparison status is invalid")


def _validate_event(event: Mapping[str, Any]) -> None:
    if not isinstance(event, Mapping):
        raise CalibrationIntegrityError("ledger row must be a JSON object")
    _require_exact_keys(event, _EVENT_KEYS, "ledger event")
    if event.get("schema") != CALIBRATION_EVENT_SCHEMA:
        raise CalibrationIntegrityError("unsupported calibration event schema")
    if event.get("event_type") not in _EVENT_TYPES:
        raise CalibrationIntegrityError("unsupported calibration event type")
    if event.get("scope") != PAPER_RESEARCH_SCOPE:
        raise CalibrationIntegrityError("calibration event scope is not paper research")
    if event.get("execution_allowed") is not False:
        raise CalibrationIntegrityError("calibration event cannot grant execution")
    sequence = event.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise CalibrationIntegrityError("event sequence must be a positive integer")
    previous = event.get("previous_event_digest")
    if previous is not None and (
        not isinstance(previous, str) or _SHA256_RE.fullmatch(previous) is None
    ):
        raise CalibrationIntegrityError("previous event digest is invalid")
    _validate_canonical_timestamp(event.get("recorded_at"), "recorded_at")

    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        raise CalibrationIntegrityError("event payload must be an object")
    if event["event_type"] == "forecast_registered":
        _validate_forecast_payload(payload)
    else:
        _validate_outcome_payload(payload)

    event_id = event.get("event_id")
    if not isinstance(event_id, str) or _EVENT_ID_RE.fullmatch(event_id) is None:
        raise CalibrationIntegrityError("calibration event ID is invalid")
    prefix = "forecast" if event["event_type"] == "forecast_registered" else "outcome"
    identity_digest = hashlib.sha256(
        _canonical_json(_event_id_material(event)).encode("utf-8")
    ).hexdigest()
    if event_id != f"cal-{prefix}-{identity_digest[:32]}":
        raise CalibrationIntegrityError("event ID does not match event content")

    integrity = event.get("integrity")
    if not isinstance(integrity, Mapping):
        raise CalibrationIntegrityError("event integrity block is missing")
    _require_exact_keys(integrity, _INTEGRITY_KEYS, "event integrity")
    if integrity.get("content_digest") != _event_digest(event):
        raise CalibrationIntegrityError("event content digest mismatch")
    if any(
        integrity.get(name) is not False
        for name in ("proves_authorship", "proves_truth", "proves_timestamp")
    ):
        raise CalibrationIntegrityError("event digest makes an unsupported proof claim")


def _binary_score(probability_yes: float, outcome: str) -> dict[str, Any]:
    observed = 1.0 if outcome == "YES" else 0.0
    brier = (probability_yes - observed) ** 2
    observed_probability = probability_yes if outcome == "YES" else 1.0 - probability_yes
    if observed_probability == 0.0:
        log_loss: float | None = None
        status = "infinite_zero_probability_assigned"
    else:
        log_loss = -math.log(observed_probability)
        status = "finite"
    return {
        "probability_yes": probability_yes,
        "brier_score": brier,
        "log_loss": log_loss,
        "log_loss_status": status,
    }


def _score_comparison(
    agent: Mapping[str, Any], baseline: Mapping[str, Any] | None
) -> dict[str, Any]:
    if baseline is None:
        return {
            "brier_advantage_vs_market": None,
            "log_loss_advantage_vs_market": None,
            "positive_advantage_means_agent_better": True,
            "log_loss_comparison_status": "baseline_unavailable",
        }
    brier_advantage = float(baseline["brier_score"]) - float(agent["brier_score"])
    agent_status = agent["log_loss_status"]
    baseline_status = baseline["log_loss_status"]
    if agent_status == baseline_status == "finite":
        log_advantage = float(baseline["log_loss"]) - float(agent["log_loss"])
        status = "finite"
    elif agent_status == "finite":
        log_advantage = None
        status = "agent_better_baseline_infinite"
    elif baseline_status == "finite":
        log_advantage = None
        status = "market_better_agent_infinite"
    else:
        log_advantage = None
        status = "both_infinite"
    return {
        "brier_advantage_vs_market": brier_advantage,
        "log_loss_advantage_vs_market": log_advantage,
        "positive_advantage_means_agent_better": True,
        "log_loss_comparison_status": status,
    }


class CalibrationLedger:
    """Owner-private, append-only JSONL ledger of forecasts and outcomes."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        parent_existed = self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent_existed and stat.S_IMODE(self.path.parent.stat().st_mode) & 0o077:
            raise PermissionError(
                f"calibration ledger directory must be owner-only (0700): {self.path.parent}"
            )
        try:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            if not self.path.is_file():
                raise CalibrationIntegrityError("calibration ledger path is not a file")
            if stat.S_IMODE(self.path.stat().st_mode) & 0o077:
                raise PermissionError(
                    f"calibration ledger must be owner-only (0600): {self.path}"
                )
        else:
            os.close(descriptor)

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[BinaryIO]:
        with self.path.open("r+b", buffering=0) as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield handle
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_locked(self, handle: BinaryIO) -> list[dict[str, Any]]:
        handle.seek(0, os.SEEK_END)
        if handle.tell() > MAX_LEDGER_BYTES:
            raise CalibrationIntegrityError("calibration ledger exceeds its safe size limit")
        handle.seek(0)
        events: list[dict[str, Any]] = []
        previous_digest: str | None = None
        expected_sequence = 1
        event_ids: set[str] = set()
        forecast_signal_ids: set[str] = set()
        resolved_signal_ids: set[str] = set()
        while True:
            raw = handle.readline(MAX_RECORD_BYTES + 1)
            if not raw:
                break
            if len(raw) > MAX_RECORD_BYTES:
                raise CalibrationIntegrityError("calibration ledger row is too large")
            if not raw.endswith(b"\n"):
                raise CalibrationIntegrityError("calibration ledger has a partial trailing row")
            if raw == b"\n":
                raise CalibrationIntegrityError("calibration ledger contains a blank row")
            try:
                decoded = raw[:-1].decode("utf-8", errors="strict")
                event = json.loads(
                    decoded,
                    object_pairs_hook=_duplicate_safe_object,
                    parse_constant=_reject_json_constant,
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CalibrationIntegrityError(
                    "calibration ledger contains invalid UTF-8 JSON"
                ) from exc
            _validate_event(event)
            if event["sequence"] != expected_sequence:
                raise CalibrationIntegrityError("calibration event sequence is discontinuous")
            if event["previous_event_digest"] != previous_digest:
                raise CalibrationIntegrityError("calibration event hash chain is broken")
            if event["event_id"] in event_ids:
                raise CalibrationIntegrityError("calibration event ID is duplicated")
            event_ids.add(event["event_id"])
            signal_id = event["payload"]["signal_id"]
            if event["event_type"] == "forecast_registered":
                if signal_id in forecast_signal_ids:
                    raise CalibrationIntegrityError(
                        "signal has more than one preregistered forecast"
                    )
                forecast_signal_ids.add(signal_id)
                recorded = _timestamp(event["recorded_at"], "recorded_at")
                issued = _timestamp(event["payload"]["issued_at"], "issued_at")
                expires = _timestamp(event["payload"]["expires_at"], "expires_at")
                if recorded < issued or recorded >= expires:
                    raise CalibrationIntegrityError(
                        "forecast was not registered within its prospective window"
                    )
            else:
                if signal_id in resolved_signal_ids:
                    raise CalibrationIntegrityError(
                        "signal has more than one recorded resolution"
                    )
                resolved_signal_ids.add(signal_id)
                forecast = next(
                    (
                        candidate
                        for candidate in events
                        if candidate["event_type"] == "forecast_registered"
                        and candidate["payload"]["signal_id"] == event["payload"]["signal_id"]
                    ),
                    None,
                )
                if forecast is None:
                    raise CalibrationIntegrityError("outcome has no prior forecast")
                if event["payload"]["forecast_event_id"] != forecast["event_id"]:
                    raise CalibrationIntegrityError("outcome links the wrong forecast event")
                if (
                    event["payload"]["forecast_event_digest"]
                    != forecast["integrity"]["content_digest"]
                ):
                    raise CalibrationIntegrityError("outcome forecast digest link is broken")
                if (
                    event["payload"]["resolution_rules_ref"]
                    != forecast["payload"]["market"]["resolution_rules_ref"]
                ):
                    raise CalibrationIntegrityError("outcome changed the forecast's rules reference")
                resolved = _timestamp(event["payload"]["resolved_at"], "resolved_at")
                forecast_recorded = _timestamp(forecast["recorded_at"], "recorded_at")
                outcome_recorded = _timestamp(event["recorded_at"], "recorded_at")
                if resolved <= forecast_recorded:
                    raise CalibrationIntegrityError(
                        "outcome does not follow forecast preregistration"
                    )
                if outcome_recorded < resolved:
                    raise CalibrationIntegrityError(
                        "outcome was recorded before its resolution timestamp"
                    )
                expected_agent = _binary_score(
                    float(forecast["payload"]["forecast"]["probability_yes"]),
                    event["payload"]["outcome"],
                )
                baseline = forecast["payload"]["market_baseline"]
                expected_baseline = (
                    _binary_score(
                        float(baseline["probability_yes"]),
                        event["payload"]["outcome"],
                    )
                    if baseline["available"]
                    else None
                )
                expected_scores = {
                    "definition": "binary_single_outcome_natural_log",
                    "agent": expected_agent,
                    "market_baseline": expected_baseline,
                    "comparison": _score_comparison(expected_agent, expected_baseline),
                }
                if event["payload"]["scores"] != expected_scores:
                    raise CalibrationIntegrityError(
                        "outcome scores do not match the preregistered forecast"
                    )
            events.append(event)
            previous_digest = event["integrity"]["content_digest"]
            expected_sequence += 1
        return events

    @staticmethod
    def _checkpoint(events: Sequence[Mapping[str, Any]]) -> LedgerCheckpoint:
        return LedgerCheckpoint(
            event_count=len(events),
            head_digest=(
                str(events[-1]["integrity"]["content_digest"]) if events else None
            ),
        )

    def verify(
        self, *, expected_checkpoint: LedgerCheckpoint | None = None
    ) -> LedgerCheckpoint:
        """Verify the chain and optionally prove an external anchor remains a prefix."""

        with self._locked(exclusive=False) as handle:
            events = self._read_locked(handle)
            checkpoint = self._checkpoint(events)
        if expected_checkpoint is not None:
            if (
                isinstance(expected_checkpoint.event_count, bool)
                or not isinstance(expected_checkpoint.event_count, int)
                or expected_checkpoint.event_count < 0
                or (
                    expected_checkpoint.head_digest is not None
                    and (
                        not isinstance(expected_checkpoint.head_digest, str)
                        or _SHA256_RE.fullmatch(expected_checkpoint.head_digest) is None
                    )
                )
                or (expected_checkpoint.event_count == 0)
                != (expected_checkpoint.head_digest is None)
            ):
                raise CalibrationError("expected checkpoint is invalid")
            anchored_count = expected_checkpoint.event_count
            anchored_digest = (
                events[anchored_count - 1]["integrity"]["content_digest"]
                if 0 < anchored_count <= len(events)
                else None
            )
            if (
                anchored_count > len(events)
                or anchored_digest != expected_checkpoint.head_digest
            ):
                raise CalibrationIntegrityError(
                    "calibration ledger does not match the expected external checkpoint"
                )
        return checkpoint

    def events(self) -> tuple[dict[str, Any], ...]:
        """Return detached event copies after validating the complete chain."""

        with self._locked(exclusive=False) as handle:
            events = self._read_locked(handle)
        return tuple(copy.deepcopy(events))

    @staticmethod
    def _append_locked(handle: BinaryIO, event: Mapping[str, Any]) -> None:
        encoded = (_canonical_json(event) + "\n").encode("utf-8")
        if len(encoded) > MAX_RECORD_BYTES:
            raise CalibrationError("calibration event exceeds its safe row limit")
        handle.seek(0, os.SEEK_END)
        remaining = memoryview(encoded)
        while remaining:
            written = handle.write(remaining)
            if written is None or written <= 0:
                raise OSError("calibration ledger append did not make progress")
            remaining = remaining[written:]
        handle.flush()
        os.fsync(handle.fileno())

    def register_forecast(
        self,
        envelope: Mapping[str, Any],
        *,
        probability_yes: float,
        recorded_at: datetime | str | None = None,
        market_baseline_probability_yes: float | None | object = _USE_ENVELOPE_BASELINE,
        market_baseline_observation_ref: str | None = None,
    ) -> AppendResult:
        """Append one preregistered binary forecast.

        ``probability_yes`` is always explicit and is never inferred from the
        envelope's confidence or target-price fields.  By default, the market
        baseline is derived from the quoted outcome token in the sealed signal
        envelope.  Passing ``None`` records that no same-time baseline was
        captured.  Passing a numeric override requires an immutable observation
        reference already present in the signal's provenance.
        """

        validate_envelope(envelope)
        signal_id = _bounded_string(envelope.get("signal_id"), "signal_id", maximum=256)
        forecast_probability = _probability(probability_yes, "probability_yes")
        issued_at = _iso(envelope["issued_at"], "issued_at")
        expires_at = _iso(envelope["expires_at"], "expires_at")
        registration = _iso(recorded_at or datetime.now(timezone.utc), "recorded_at")
        if _timestamp(registration, "recorded_at") < _timestamp(issued_at, "issued_at"):
            raise CalibrationError("forecast cannot be registered before signal issuance")
        if _timestamp(registration, "recorded_at") >= _timestamp(expires_at, "expires_at"):
            raise CalibrationError("forecast must be registered before signal expiry")

        market = envelope["market"]
        provenance = envelope["provenance"]
        source_refs = _reference_list(
            provenance.get("source_observation_refs"),
            "source_observation_refs",
            required=True,
        )
        rules_ref = _bounded_string(
            market.get("resolution_rules_ref"),
            "resolution_rules_ref",
            maximum=2_048,
        )
        envelope_digest = str(envelope["integrity"]["content_digest"])

        if market_baseline_probability_yes is _USE_ENVELOPE_BASELINE:
            quoted = _probability(
                market.get("quoted_outcome_token_price"),
                "market.quoted_outcome_token_price",
            )
            baseline_probability = quoted if market["direction"] == "YES" else 1.0 - quoted
            baseline = {
                "available": True,
                "probability_yes": baseline_probability,
                "observed_at": issued_at,
                "source": "sealed_signal_outcome_token_quote",
                "observation_ref": f"signal-envelope:{envelope_digest}",
                "unavailable_reason": None,
            }
            if market_baseline_observation_ref is not None:
                raise CalibrationError(
                    "an observation override is not accepted for the envelope baseline"
                )
        elif market_baseline_probability_yes is None:
            if market_baseline_observation_ref is not None:
                raise CalibrationError("an unavailable baseline cannot have an observation ref")
            baseline = {
                "available": False,
                "probability_yes": None,
                "observed_at": issued_at,
                "source": None,
                "observation_ref": None,
                "unavailable_reason": "not_captured_same_time",
            }
        else:
            baseline_probability = _probability(
                market_baseline_probability_yes,
                "market_baseline_probability_yes",
            )
            reference = _bounded_string(
                market_baseline_observation_ref,
                "market_baseline_observation_ref",
                maximum=1_024,
            )
            if reference not in source_refs:
                raise CalibrationError(
                    "market baseline observation ref must be linked in signal provenance"
                )
            baseline = {
                "available": True,
                "probability_yes": baseline_probability,
                "observed_at": issued_at,
                "source": "explicit_same_time_market_observation",
                "observation_ref": reference,
                "unavailable_reason": None,
            }

        payload: dict[str, Any] = {
            "signal_id": signal_id,
            "signal_envelope_digest": envelope_digest,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "observed_at": issued_at,
            "market": {
                "venue": _bounded_string(market.get("venue"), "market.venue", maximum=64),
                "market_id": _bounded_string(
                    market.get("market_id"), "market.market_id", maximum=512
                ),
                "question_digest": _sha256(str(market["question"]).encode("utf-8")),
                "domain": _bounded_string(
                    market.get("domain"), "market.domain", maximum=64
                ),
                "direction": market["direction"],
                "resolution_rules_ref": rules_ref,
                "resolution_rules_status": market["resolution_rules_status"],
            },
            "provenance": {
                "source_observation_refs": source_refs,
                "source_status": _bounded_string(
                    provenance.get("status"), "provenance.status", maximum=64
                ),
                "references_verified_by_ledger": False,
            },
            "forecast": {
                "probability_yes": forecast_probability,
                "probability_semantics": "binary_yes_outcome",
                "source": "explicit_preregistered_input",
                "derived_from_confidence": False,
            },
            "market_baseline": baseline,
        }

        with self._locked(exclusive=True) as handle:
            events = self._read_locked(handle)
            prior = next(
                (
                    event
                    for event in events
                    if event["event_type"] == "forecast_registered"
                    and event["payload"]["signal_id"] == signal_id
                ),
                None,
            )
            if prior is not None:
                if prior["payload"] == payload:
                    return AppendResult(copy.deepcopy(prior), duplicate=True)
                raise CalibrationConflictError(
                    "signal already has a different preregistered forecast"
                )
            event = _seal_event(
                {
                    "schema": CALIBRATION_EVENT_SCHEMA,
                    "sequence": len(events) + 1,
                    "previous_event_digest": (
                        events[-1]["integrity"]["content_digest"] if events else None
                    ),
                    "event_type": "forecast_registered",
                    "recorded_at": registration,
                    "scope": PAPER_RESEARCH_SCOPE,
                    "execution_allowed": False,
                    "payload": payload,
                }
            )
            self._append_locked(handle, event)
            return AppendResult(copy.deepcopy(event))

    def record_resolution(
        self,
        signal_id: str,
        *,
        outcome: str,
        resolved_at: datetime | str,
        resolution_evidence_refs: Sequence[str],
        resolution_evidence_content_digest: str,
        recorded_at: datetime | str | None = None,
    ) -> AppendResult:
        """Append one immutable resolution and its proper scores."""

        normalized_signal_id = _bounded_string(signal_id, "signal_id", maximum=256)
        if outcome not in {"YES", "NO"}:
            raise CalibrationError("outcome must be exactly YES or NO")
        resolution_time = _iso(resolved_at, "resolved_at")
        registration = _iso(recorded_at or datetime.now(timezone.utc), "recorded_at")
        if _timestamp(registration, "recorded_at") < _timestamp(
            resolution_time, "resolved_at"
        ):
            raise CalibrationError("resolution cannot be recorded before it occurred")
        evidence_refs = _reference_list(
            resolution_evidence_refs,
            "resolution_evidence_refs",
            required=True,
        )
        if (
            not isinstance(resolution_evidence_content_digest, str)
            or _SHA256_RE.fullmatch(resolution_evidence_content_digest) is None
        ):
            raise CalibrationError(
                "resolution_evidence_content_digest must be a sha256 digest"
            )

        with self._locked(exclusive=True) as handle:
            events = self._read_locked(handle)
            forecast = next(
                (
                    event
                    for event in events
                    if event["event_type"] == "forecast_registered"
                    and event["payload"]["signal_id"] == normalized_signal_id
                ),
                None,
            )
            if forecast is None:
                raise CalibrationError("resolution requires a prior registered forecast")
            forecast_registered_at = _timestamp(forecast["recorded_at"], "recorded_at")
            if _timestamp(resolution_time, "resolved_at") <= forecast_registered_at:
                raise CalibrationError(
                    "resolved outcome predates forecast registration; scoring would leak hindsight"
                )

            probability = float(forecast["payload"]["forecast"]["probability_yes"])
            agent_score = _binary_score(probability, outcome)
            baseline_record = forecast["payload"]["market_baseline"]
            baseline_score = (
                _binary_score(float(baseline_record["probability_yes"]), outcome)
                if baseline_record["available"]
                else None
            )
            payload: dict[str, Any] = {
                "signal_id": normalized_signal_id,
                "forecast_event_id": forecast["event_id"],
                "forecast_event_digest": forecast["integrity"]["content_digest"],
                "resolved_at": resolution_time,
                "outcome": outcome,
                "resolution_rules_ref": forecast["payload"]["market"][
                    "resolution_rules_ref"
                ],
                "resolution_evidence_refs": evidence_refs,
                "resolution_evidence_content_digest": resolution_evidence_content_digest,
                "scores": {
                    "definition": "binary_single_outcome_natural_log",
                    "agent": agent_score,
                    "market_baseline": baseline_score,
                    "comparison": _score_comparison(agent_score, baseline_score),
                },
            }
            prior = next(
                (
                    event
                    for event in events
                    if event["event_type"] == "outcome_resolved"
                    and event["payload"]["signal_id"] == normalized_signal_id
                ),
                None,
            )
            if prior is not None:
                if prior["payload"] == payload:
                    return AppendResult(copy.deepcopy(prior), duplicate=True)
                raise CalibrationConflictError(
                    "signal already has a different recorded resolution"
                )
            event = _seal_event(
                {
                    "schema": CALIBRATION_EVENT_SCHEMA,
                    "sequence": len(events) + 1,
                    "previous_event_digest": (
                        events[-1]["integrity"]["content_digest"] if events else None
                    ),
                    "event_type": "outcome_resolved",
                    "recorded_at": registration,
                    "scope": PAPER_RESEARCH_SCOPE,
                    "execution_allowed": False,
                    "payload": payload,
                }
            )
            self._append_locked(handle, event)
            return AppendResult(copy.deepcopy(event))

    def scorecard(self, *, domain: str | None = None) -> dict[str, Any]:
        """Aggregate resolved forecasts without hiding infinite log losses."""

        normalized_domain = None
        if domain is not None:
            normalized_domain = _bounded_string(domain, "domain", maximum=64).upper()
        with self._locked(exclusive=False) as handle:
            events = self._read_locked(handle)
        checkpoint = self._checkpoint(events)
        forecasts = {
            event["payload"]["signal_id"]: event
            for event in events
            if event["event_type"] == "forecast_registered"
            and (
                normalized_domain is None
                or event["payload"]["market"]["domain"] == normalized_domain
            )
        }
        resolutions = [
            event
            for event in events
            if event["event_type"] == "outcome_resolved"
            and event["payload"]["signal_id"] in forecasts
        ]

        agent_scores = [event["payload"]["scores"]["agent"] for event in resolutions]
        baseline_scores = [
            event["payload"]["scores"]["market_baseline"]
            for event in resolutions
            if event["payload"]["scores"]["market_baseline"] is not None
        ]
        comparisons = [event["payload"]["scores"]["comparison"] for event in resolutions]

        def metric_summary(scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
            finite_logs = [
                float(score["log_loss"])
                for score in scores
                if score["log_loss_status"] == "finite"
            ]
            infinite_count = len(scores) - len(finite_logs)
            if not scores:
                status = "unavailable"
                log_mean = None
            elif infinite_count:
                status = "contains_infinite"
                log_mean = None
            else:
                status = "finite"
                log_mean = math.fsum(finite_logs) / len(finite_logs)
            return {
                "count": len(scores),
                "brier_mean": (
                    math.fsum(float(score["brier_score"]) for score in scores)
                    / len(scores)
                    if scores
                    else None
                ),
                "log_loss_mean": log_mean,
                "log_loss_status": status,
                "finite_log_loss_count": len(finite_logs),
                "infinite_log_loss_count": infinite_count,
            }

        buckets: dict[int, list[tuple[float, float]]] = {}
        for event in resolutions:
            probability = float(event["payload"]["scores"]["agent"]["probability_yes"])
            observed = 1.0 if event["payload"]["outcome"] == "YES" else 0.0
            index = min(int(probability * 10), 9)
            buckets.setdefault(index, []).append((probability, observed))
        calibration_buckets = []
        for index, observations in sorted(buckets.items()):
            mean_probability = math.fsum(item[0] for item in observations) / len(observations)
            observed_rate = math.fsum(item[1] for item in observations) / len(observations)
            calibration_buckets.append(
                {
                    "lower_bound": index / 10,
                    "upper_bound": (index + 1) / 10,
                    "upper_bound_inclusive": index == 9,
                    "count": len(observations),
                    "mean_probability_yes": mean_probability,
                    "observed_yes_rate": observed_rate,
                    "observed_minus_forecast": observed_rate - mean_probability,
                }
            )

        brier_advantages = [
            float(comparison["brier_advantage_vs_market"])
            for comparison in comparisons
            if comparison["brier_advantage_vs_market"] is not None
        ]
        log_advantages = [
            float(comparison["log_loss_advantage_vs_market"])
            for comparison in comparisons
            if comparison["log_loss_advantage_vs_market"] is not None
        ]
        resolved_ids = {event["payload"]["signal_id"] for event in resolutions}
        return {
            "schema": CALIBRATION_SCORECARD_SCHEMA,
            "scope": PAPER_RESEARCH_SCOPE,
            "execution_allowed": False,
            "filter": {"domain": normalized_domain},
            "ledger": {
                "event_count": checkpoint.event_count,
                "head_digest": checkpoint.head_digest,
                "hashes_prove_authorship": False,
                "hashes_prove_truth": False,
                "hashes_prove_timestamp": False,
            },
            "counts": {
                "registered_forecasts": len(forecasts),
                "resolved_forecasts": len(resolutions),
                "unresolved_forecasts": len(set(forecasts) - resolved_ids),
                "resolved_yes": sum(
                    event["payload"]["outcome"] == "YES" for event in resolutions
                ),
                "resolved_no": sum(
                    event["payload"]["outcome"] == "NO" for event in resolutions
                ),
                "market_baseline_coverage": len(baseline_scores),
            },
            "agent": metric_summary(agent_scores),
            "market_baseline": metric_summary(baseline_scores),
            "comparison": {
                "matched_brier_count": len(brier_advantages),
                "mean_brier_advantage_vs_market": (
                    math.fsum(brier_advantages) / len(brier_advantages)
                    if brier_advantages
                    else None
                ),
                "finite_matched_log_loss_count": len(log_advantages),
                "mean_log_loss_advantage_vs_market": (
                    math.fsum(log_advantages) / len(log_advantages)
                    if log_advantages
                    else None
                ),
                "positive_advantage_means_agent_better": True,
            },
            "calibration_buckets": calibration_buckets,
            "limitations": [
                "The ledger verifies local content linkage, not source truth or trusted time.",
                "Market-price baselines are comparisons, not proof of exploitable edge.",
                "All records are paper research and grant no trading authority.",
            ],
        }
