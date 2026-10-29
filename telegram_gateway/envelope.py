"""Immutable, evidence-labelled signal envelopes for external distribution."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA = "kingdom.signal/0.1"
INFORMATION_ONLY = "information_only"


class EnvelopeError(ValueError):
    """Raised when a signal envelope violates the public contract."""


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EnvelopeError(f"invalid timestamp: {value!r}") from exc
    else:
        raise EnvelopeError("timestamp must be a non-empty ISO-8601 value")
    if parsed.tzinfo is None:
        raise EnvelopeError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: Any) -> str:
    return _timestamp(value).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _probability(name: str, value: Any, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EnvelopeError(f"{name} must be a number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise EnvelopeError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise EnvelopeError(f"{name} must be a finite number")
    if not 0.0 <= result <= 1.0:
        raise EnvelopeError(f"{name} must be between 0 and 1")
    return result


def _finite_number(
    name: str,
    value: Any,
    *,
    optional: bool = False,
    minimum: float = -1_000_000_000.0,
    maximum: float = 1_000_000_000.0,
) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EnvelopeError(f"{name} must be a number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise EnvelopeError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise EnvelopeError(f"{name} is outside the supported finite range")
    return result


def _bounded_integer(name: str, value: Any, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EnvelopeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise EnvelopeError(f"{name} is outside the supported range")
    return value


def _plain_record(signal: Any) -> dict[str, Any]:
    if is_dataclass(signal):
        return asdict(signal)
    if isinstance(signal, Mapping):
        return dict(signal)
    raise EnvelopeError("S012 signal must be a dataclass or mapping")


def build_s012_envelope(
    signal: Any,
    *,
    observation_refs: list[str] | None = None,
    resolution_rules_ref: str | None = None,
    model_ref: str | None = None,
) -> dict[str, Any]:
    """Project one S012 signal into the distribution contract.

    Existing S012 records currently carry event and assessment identifiers but
    not WW3 Observation IDs.  The envelope states that limitation instead of
    upgrading internal links into source provenance.
    """

    record = _plain_record(signal)
    signal_id = str(record.get("signal_id") or "").strip()
    market_id = str(record.get("market_id") or "").strip()
    question = str(record.get("market_question") or "").strip()
    direction = str(record.get("direction") or "").upper()
    if not signal_id or not market_id or not question:
        raise EnvelopeError("signal_id, market_id, and market_question are required")
    if direction not in {"YES", "NO"}:
        raise EnvelopeError("direction must be YES or NO")

    if resolution_rules_ref is not None:
        if not isinstance(resolution_rules_ref, str) or not resolution_rules_ref.strip():
            raise EnvelopeError("resolution_rules_ref must be a non-empty string or null")
        resolution_rules_ref = resolution_rules_ref.strip()

    issued_at = _iso(record.get("created_at"))
    expires_at = _iso(record.get("expires_at"))
    if _timestamp(expires_at) <= _timestamp(issued_at):
        raise EnvelopeError("expires_at must be later than issued_at")

    internal_refs = []
    for kind in ("event_id", "assessment_id"):
        value = str(record.get(kind) or "").strip()
        if value:
            internal_refs.append(f"s012:{kind.removesuffix('_id')}:{value}")

    if observation_refs is not None and not isinstance(observation_refs, list):
        raise EnvelopeError("observation_refs must be a list when present")
    source_refs = sorted({str(ref).strip() for ref in observation_refs or [] if str(ref).strip()})
    evidence_status = (
        "references_present_not_verified" if source_refs else "internal_artifact_links_only"
    )

    risk_notes = record.get("risk_notes") or []
    if not isinstance(risk_notes, list):
        raise EnvelopeError("risk_notes must be a list")

    envelope: dict[str, Any] = {
        "schema": SCHEMA,
        "signal_id": signal_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "market": {
            "venue": "polymarket",
            "market_id": market_id,
            "question": question,
            "domain": str(record.get("domain") or "OTHER").upper(),
            "direction": direction,
            "quoted_outcome_token_price": _probability(
                "entry_price", record.get("entry_price")
            ),
            "resolution_rules_ref": resolution_rules_ref,
            "resolution_rules_status": (
                "reference_present_not_verified" if resolution_rules_ref else "missing"
            ),
            "resolution_rules_verified": False,
        },
        "forecast": {
            "signal_type": str(record.get("signal_type") or "UNKNOWN"),
            "confidence": _probability("confidence", record.get("confidence")),
            "estimated_shift": _finite_number(
                "estimated_shift", record.get("estimated_shift"), optional=True
            ),
            "actual_move": _finite_number(
                "actual_move", record.get("actual_move"), optional=True
            ),
            "reaction_delta": _finite_number(
                "reaction_delta", record.get("reaction_delta"), optional=True
            ),
            "target_probability": _probability(
                "target_price", record.get("target_price"), optional=True
            ),
            "stop_probability": _probability(
                "stop_price", record.get("stop_price"), optional=True
            ),
            "horizon_hours": _bounded_integer(
                "time_horizon_hours",
                record.get("time_horizon_hours"),
                minimum=1,
                maximum=8_760,
            ),
            "reasoning": str(record.get("reasoning") or "").strip(),
            "model_ref": model_ref,
        },
        "provenance": {
            "status": evidence_status,
            "source_observation_refs": source_refs,
            "internal_artifact_refs": internal_refs,
            "limitations": [
                (
                    "Observation references were supplied but this gateway did not verify "
                    "their format, existence, immutability, or source authentication."
                    if source_refs
                    else "No immutable source Observation IDs were attached by the S012 producer."
                )
            ],
        },
        "risk": {
            "pipeline_status": str(record.get("status") or "UNKNOWN").upper(),
            "concentration_passed": _boolean(
                "passed_concentration", record.get("passed_concentration")
            ),
            "anti_patterns_passed": _boolean(
                "passed_anti_patterns", record.get("passed_anti_patterns")
            ),
            "notes": [str(note) for note in risk_notes],
            "suggested_paper_size_usdc": _finite_number(
                "size_usdc", record.get("size_usdc"), minimum=0.0
            ),
            "suggested_bankroll_fraction": _probability(
                "size_pct", record.get("size_pct")
            ),
        },
        "authority": {
            "mode": INFORMATION_ONLY,
            "execution_allowed": False,
            "not_an_authorization": True,
            "jurisdiction_verified": False,
            "user_consent_ref": None,
            "denial_reasons": [
                "The distribution gateway has no wallet or order-signing capability.",
                "Venue eligibility and jurisdiction have not been established for the recipient.",
                "A delivered signal is information, not consent or authority to trade."
            ],
        },
    }
    return seal_envelope(envelope)


def _without_integrity(envelope: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(envelope))
    payload.pop("integrity", None)
    return payload


def canonical_json(envelope: Mapping[str, Any]) -> str:
    """Return the content-bound canonical JSON used by the local digest."""

    return json.dumps(
        _without_integrity(envelope),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_digest(envelope: Mapping[str, Any]) -> str:
    payload = canonical_json(envelope).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def seal_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and add a content digest.

    The digest detects local content drift.  It is deliberately labelled as
    neither an author signature nor evidence that the forecast is true.
    """

    result = _without_integrity(envelope)
    validate_envelope(result, require_digest=False)
    result["integrity"] = {
        "content_digest": content_digest(result),
        "proves_authorship": False,
        "proves_truth": False,
    }
    validate_envelope(result, require_digest=True)
    return result


def validate_envelope(
    envelope: Mapping[str, Any], *, require_digest: bool = True
) -> None:
    if not isinstance(envelope, Mapping):
        raise EnvelopeError("envelope must be an object")
    if envelope.get("schema") != SCHEMA:
        raise EnvelopeError(f"schema must be {SCHEMA}")
    for name in ("signal_id", "issued_at", "expires_at"):
        if not isinstance(envelope.get(name), str) or not envelope[name].strip():
            raise EnvelopeError(f"{name} must be a non-empty string")
    issued_at = _timestamp(envelope["issued_at"])
    expires_at = _timestamp(envelope["expires_at"])
    if expires_at <= issued_at:
        raise EnvelopeError("expires_at must be later than issued_at")

    market = envelope.get("market")
    if not isinstance(market, Mapping):
        raise EnvelopeError("market must be an object")
    if market.get("venue") != "polymarket":
        raise EnvelopeError("market venue must be polymarket in schema 0.1")
    if market.get("direction") not in {"YES", "NO"}:
        raise EnvelopeError("market direction must be YES or NO")
    for name in ("market_id", "question"):
        if not isinstance(market.get(name), str) or not market[name].strip():
            raise EnvelopeError(f"market.{name} must be a non-empty string")
    _probability("market.quoted_outcome_token_price", market.get("quoted_outcome_token_price"))
    rules_ref = market.get("resolution_rules_ref")
    if rules_ref is not None and (
        not isinstance(rules_ref, str) or not rules_ref.strip()
    ):
        raise EnvelopeError("market.resolution_rules_ref must be a non-empty string or null")
    expected_rules_status = (
        "reference_present_not_verified" if rules_ref is not None else "missing"
    )
    if market.get("resolution_rules_status") != expected_rules_status:
        raise EnvelopeError("market resolution-rule status is inconsistent")
    if market.get("resolution_rules_verified") is not False:
        raise EnvelopeError("market resolution rules are not verified by this gateway")

    forecast = envelope.get("forecast")
    if not isinstance(forecast, Mapping):
        raise EnvelopeError("forecast must be an object")
    _probability("forecast.confidence", forecast.get("confidence"))
    _probability("forecast.target_probability", forecast.get("target_probability"), optional=True)
    _probability("forecast.stop_probability", forecast.get("stop_probability"), optional=True)
    for name in ("estimated_shift", "actual_move", "reaction_delta"):
        _finite_number(f"forecast.{name}", forecast.get(name), optional=True)
    _bounded_integer(
        "forecast.horizon_hours",
        forecast.get("horizon_hours"),
        minimum=1,
        maximum=8_760,
    )

    provenance = envelope.get("provenance")
    if not isinstance(provenance, Mapping):
        raise EnvelopeError("provenance must be an object")
    if provenance.get("status") not in {
        "internal_artifact_links_only",
        "references_present_not_verified",
    }:
        raise EnvelopeError("unsupported provenance status")
    for name in ("source_observation_refs", "internal_artifact_refs", "limitations"):
        if not isinstance(provenance.get(name), list):
            raise EnvelopeError(f"provenance.{name} must be a list")
    source_refs = provenance["source_observation_refs"]
    if provenance.get("status") == "references_present_not_verified" and not source_refs:
        raise EnvelopeError("reference-present provenance requires observation references")
    if provenance.get("status") == "internal_artifact_links_only" and source_refs:
        raise EnvelopeError("internal-only provenance cannot claim source observations")

    risk = envelope.get("risk")
    if not isinstance(risk, Mapping) or not isinstance(risk.get("notes"), list):
        raise EnvelopeError("risk and risk.notes are required")
    if not isinstance(risk.get("pipeline_status"), str):
        raise EnvelopeError("risk.pipeline_status must be a string")
    for name in ("concentration_passed", "anti_patterns_passed"):
        if not isinstance(risk.get(name), bool):
            raise EnvelopeError(f"risk.{name} must be a boolean")
    _finite_number(
        "risk.suggested_paper_size_usdc",
        risk.get("suggested_paper_size_usdc"),
        minimum=0.0,
    )
    _probability(
        "risk.suggested_bankroll_fraction",
        risk.get("suggested_bankroll_fraction"),
    )

    authority = envelope.get("authority")
    if not isinstance(authority, Mapping):
        raise EnvelopeError("authority must be an object")
    if authority.get("mode") != INFORMATION_ONLY:
        raise EnvelopeError("schema 0.1 only supports information_only mode")
    if authority.get("execution_allowed") is not False:
        raise EnvelopeError("live execution must be disabled")
    if authority.get("not_an_authorization") is not True:
        raise EnvelopeError("authority must state that it is not an authorization")
    if authority.get("jurisdiction_verified") is not False:
        raise EnvelopeError("recipient jurisdiction cannot be asserted by this gateway")
    if authority.get("user_consent_ref") is not None:
        raise EnvelopeError("a research envelope cannot assert user consent")
    if not isinstance(authority.get("denial_reasons"), list) or not authority["denial_reasons"]:
        raise EnvelopeError("authority.denial_reasons must be non-empty")

    if require_digest:
        integrity = envelope.get("integrity")
        if not isinstance(integrity, Mapping):
            raise EnvelopeError("integrity block is required")
        if integrity.get("proves_authorship") is not False:
            raise EnvelopeError("digest must not claim authorship")
        if integrity.get("proves_truth") is not False:
            raise EnvelopeError("digest must not claim truth")
        if integrity.get("content_digest") != content_digest(envelope):
            raise EnvelopeError("content digest mismatch")


def verify_envelope(envelope: Mapping[str, Any]) -> bool:
    try:
        validate_envelope(envelope)
    except (EnvelopeError, TypeError, ValueError):
        return False
    return True


def _boolean(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise EnvelopeError(f"{name} must be a boolean")
    return value
