"""Plain-text Telegram renderers with explicit evidence and action limits."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

MAX_TELEGRAM_TEXT = 4096
TARGET_TEXT = 3400


def _visible_text(value: Any) -> str:
    text = str(value or "")
    return "".join(
        ch
        for ch in text
        if ch in "\n\t" or unicodedata.category(ch) not in {"Cc", "Cf"}
    )


def _defang_links(text: str) -> str:
    text = re.sub(r"(?i)https://", "hxxps://", text)
    text = re.sub(r"(?i)http://", "hxxp://", text)
    return re.sub(r"(?i)\bwww\.", "www[.]", text)


def _single(value: Any, limit: int = 600) -> str:
    text = re.sub(r"\s+", " ", _visible_text(value)).strip()
    text = _defang_links(text)
    if len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    return text


def _quoted_analysis(value: Any, limit: int = 900) -> list[str]:
    raw = _visible_text(value).replace("\t", " ")
    lines = []
    remaining = limit
    for source_line in raw.splitlines() or [raw]:
        line = _defang_links(re.sub(r" +", " ", source_line).strip())
        if not line:
            continue
        if len(line) > remaining:
            line = line[: max(0, remaining - 1)].rstrip() + "…"
        lines.append("> " + line)
        remaining -= len(line)
        if remaining <= 0:
            break
    return lines


def _pct(value: Any) -> str:
    return f"{float(value):.1%}"


def _bounded(lines: list[str], *, footer: list[str] | None = None) -> str:
    body = "\n".join(lines).strip()
    suffix = "\n".join(footer or []).strip()
    if not suffix:
        return body if len(body) <= TARGET_TEXT else body[: TARGET_TEXT - 1].rstrip() + "…"
    available = TARGET_TEXT - len(suffix) - 2
    if available < 1:
        raise ValueError("mandatory message footer exceeds the Telegram text budget")
    if len(body) > available:
        body = body[: available - 1].rstrip() + "…"
    return f"{body}\n\n{suffix}" if body else suffix


def render_public_signal(envelope: Mapping[str, Any]) -> str:
    market = envelope["market"]
    provenance = envelope["provenance"]
    return _bounded(
        [
            "KINGDOM market research — public preview",
            "",
            "Market: " + _single(market["question"], 700),
            f"Domain: {_single(market.get('domain', 'OTHER'), 24)}",
            f"Issued: {_single(envelope['issued_at'], 40)}",
            f"Evidence: {_single(provenance['status'].replace('_', ' '), 80)}",
            f"Signal ID: {_single(envelope['signal_id'], 80)}",
            "",
            "Direction and analysis are available to research subscribers.",
        ],
        footer=["No trade was placed. Live execution is disabled."],
    )


def render_research_signal(envelope: Mapping[str, Any]) -> str:
    market = envelope["market"]
    forecast = envelope["forecast"]
    provenance = envelope["provenance"]
    risk = envelope["risk"]
    notes = [_single(note, 260) for note in risk.get("notes", [])][:5]
    lines = [
        "KINGDOM research signal — WATCH",
        "",
        "Market: " + _single(market["question"], 700),
        f"Model direction: {_single(market['direction'], 8)}",
        f"Observed outcome-token price: {_pct(market['quoted_outcome_token_price'])}",
        f"Model confidence: {_pct(forecast['confidence'])}",
        f"Signal type: {_single(forecast.get('signal_type'), 60)}",
        f"Domain: {_single(market.get('domain', 'OTHER'), 24)}",
    ]
    reasoning = _quoted_analysis(forecast.get("reasoning"), 900)
    if reasoning:
        lines.extend(["", "Untrusted model analysis (quoted):", *reasoning])
    lines.extend(
        [
            "",
            f"Evidence status: {_single(provenance['status'].replace('_', ' '), 80)}",
        ]
    )
    source_refs = provenance.get("source_observation_refs") or []
    internal_refs = provenance.get("internal_artifact_refs") or []
    if source_refs:
        lines.append(
            "Source observation refs: "
            + ", ".join(_single(ref, 100) for ref in source_refs[:5])
        )
    elif internal_refs:
        lines.append(
            f"Internal artifact links retained locally: {len(internal_refs)}"
        )
    for limitation in provenance.get("limitations", [])[:3]:
        lines.append("Evidence limit: " + _single(limitation, 300))
    if notes:
        lines.extend(["", "Risk notes:"] + [f"- {note}" for note in notes])
    return _bounded(
        lines,
        footer=[
            f"Issued: {_single(envelope['issued_at'], 40)}",
            f"Expires: {_single(envelope['expires_at'], 40)}",
            f"Signal ID: {_single(envelope['signal_id'], 80)}",
            "",
            "Information only. No return is promised. No trade was placed.",
            "Live execution is disabled; venue eligibility is not established here.",
        ],
    )


def render_signal_correction(event: Mapping[str, Any]) -> str:
    """Render a bounded tombstone without repeating the withdrawn analysis."""

    if event.get("status") != "REVOKED":
        raise ValueError("only revoked signals produce correction notices")
    return _bounded(
        [
            "KINGDOM research correction",
            "",
            "A previously distributed research signal has been revoked.",
            f"Signal ID: {_single(event.get('signal_id'), 128)}",
            f"Revoked: {_single(event.get('occurred_at'), 64)}",
            f"Reason code: {_single(event.get('reason_code'), 64)}",
            "",
            "Do not rely on the earlier signal as current KINGDOM research.",
        ],
        footer=[
            "This is a research-status correction, not a market order.",
            "No trade was placed; live execution remains disabled.",
        ],
    )


def render_terms(terms_version: str) -> str:
    return _bounded(
        [
            f"KINGDOM Research Terms — {_single(terms_version, 80)}",
            "",
            "The subscription provides evidence-labelled market research and paper tools.",
            "It does not provide custody, guaranteed returns, personal financial advice, or live trade execution.",
            "Forecasts can be wrong and market positions can lose their full value.",
            "Access does not establish that Polymarket trading is available or lawful in your location.",
            "Starting the bot from a campaign link records only a daily aggregate start count. The opaque campaign code is linked to a numeric Telegram user ID only after an explicit source-linked alert opt-in.",
            "Alert consent, delivery receipts, explicit paper actions, and the minimum payment/support evidence needed for access, refunds, and reconciliation are stored privately. If separately enabled with /personalize, the bot also stores allowlisted topic codes, cadence, and opaque market references. /leave and /stop erase that preference profile and retain minimal suppression markers keyed by the numeric Telegram user ID and latest control-event watermark needed to prevent delayed updates from silently reversing the opt-out.",
            "In this local MVP, /delete_me immediately clears nonfinancial campaign attribution, alert consent and events, preference profiles, delivery receipts, and paper actions, and prevents later research messages until a newer explicit alert opt-in. It retains minimal numeric-ID no-contact watermarks plus finance/support evidence only while an applicable retention hold requires it. SQLite WAL history, filesystem snapshots, backups, and storage-level remnants may persist until separate operator maintenance.",
            "Use /paysupport for payment help. Cancellation stops renewal but keeps already-paid access through the current period.",
        ]
    )


def render_privacy() -> str:
    return _bounded(
        [
            "KINGDOM privacy summary",
            "",
            "Starting the bot from a campaign link stores only a per-campaign daily aggregate start count. A campaign code becomes linked to a numeric Telegram user ID only after an explicit source-linked alert opt-in.",
            "Stored while active: numeric Telegram user/chat IDs, explicit alert-consent events and current state, terms acceptance, subscription/payment state, delivery receipts, and explicit paper actions. If you separately use /personalize, the preference store also keeps allowlisted topic codes, cadence, and opaque market references; it does not infer interests from messages. /leave and /stop erase that profile and retain minimal suppression markers keyed by the numeric user ID and latest control-event watermark so delayed updates cannot silently restore alerts.",
            "Not stored: usernames, profile names, ordinary message bodies, wallet keys, or inferred personal traits.",
            "The local database is owner-only. Telegram still processes bot messages and payments under its own terms.",
            "In this local MVP, /delete_me immediately clears nonfinancial campaign attribution, alert consent and events, preference profiles, delivery receipts, and paper actions, and prevents later research messages until a newer explicit alert opt-in. It retains minimal numeric-ID no-contact watermarks plus finance/support evidence only while an applicable retention hold requires it. SQLite WAL history, filesystem snapshots, backups, and storage-level remnants may persist until separate operator maintenance. A deployed retention policy still requires legal review.",
        ]
    )
