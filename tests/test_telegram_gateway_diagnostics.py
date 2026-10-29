"""Offline tests for the Research gateway's stderr diagnostics.

Covers the UTC timestamp prefix, credential-free failure-class tags, and the
low-volume liveness cadence. No test opens a network connection: every
TelegramAPI here uses an injected opener that raises or returns fixtures.
"""

from __future__ import annotations

import http.client
import io
import json
import re
import sys
import urllib.error
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import pytest

from telegram_gateway import cli
from telegram_gateway.cli import (
    LIVENESS_INTERVAL_SECONDS,
    _GatewayLiveness,
    _TimestampedLines,
    _run_gateway,
    _timestamped_stderr,
    _utc_stamp,
    main,
)
from telegram_gateway.service import ServiceConfig
from telegram_gateway.store import GatewayStore
from telegram_gateway.telegram_api import TelegramAPI, TelegramError

# Synthetic, token-shaped fixture; never a real credential.
TOKEN = "123456789:AAFixtureOnlyTokenValue_abcdefghijklmn"
MESSAGE_MARKER = "EXCEPTION_MESSAGE_MARKER"
BODY_MARKER = "RESPONSE_BODY_MARKER"
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z ")
FIXED = datetime(2026, 10, 29, 10, 15, 2, 123456, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def idle_report(**overrides: int) -> dict[str, int]:
    report = {
        "updates": 0,
        "failed_updates": 0,
        "broadcast_paused": 1,
        "corrections_paused": 1,
        "corrections_sent": 0,
        "corrections_failed": 0,
        "corrections_unknown": 0,
        "sent": 0,
        "failed": 0,
        "unknown": 0,
    }
    report.update(overrides)
    return report


def assert_credential_free(text: str) -> None:
    assert TOKEN not in text
    assert TOKEN.split(":", 1)[1] not in text
    assert "api.telegram.org" not in text
    assert "/bot" not in text
    assert MESSAGE_MARKER not in text
    assert BODY_MARKER not in text


# --- (a) timestamps ---------------------------------------------------------


def test_utc_stamp_is_iso8601_utc_with_milliseconds() -> None:
    assert _utc_stamp(FIXED) == "2026-10-29T10:15:02.123Z"
    plus_nine = timezone(timedelta(hours=9))
    assert _utc_stamp(FIXED.astimezone(plus_nine)) == "2026-10-29T10:15:02.123Z"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", _utc_stamp())


def test_every_stderr_line_is_stamped_once_even_across_partial_writes() -> None:
    sink = io.StringIO()
    stream = _TimestampedLines(sink, clock=lambda: FIXED)
    stream.write("gateway: first")
    stream.write(" line continues\n")
    stream.write("Traceback (most recent call last):\n  File \"x\", line 1\n\n")
    stream.writelines(["tail without newline"])
    stream.flush()
    stamp = "2026-10-29T10:15:02.123Z "
    assert sink.getvalue() == (
        f"{stamp}gateway: first line continues\n"
        f"{stamp}Traceback (most recent call last):\n"
        f"{stamp}  File \"x\", line 1\n"
        f"{stamp}\n"
        f"{stamp}tail without newline"
    )
    assert stream.write("") == 0
    assert stream.getvalue() == sink.getvalue()  # other attributes delegate


def test_timestamped_stderr_restores_after_normal_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = io.StringIO()
    monkeypatch.setattr(sys, "stderr", sink)
    with _timestamped_stderr(clock=lambda: FIXED):
        print("gateway: inside", file=sys.stderr)
    assert sys.stderr is sink
    print("after", file=sys.stderr)
    assert sink.getvalue() == "2026-10-29T10:15:02.123Z gateway: inside\nafter\n"


def test_timestamped_stderr_keeps_stamping_for_a_crash_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink = io.StringIO()
    monkeypatch.setattr(sys, "stderr", sink)
    with pytest.raises(RuntimeError):
        with _timestamped_stderr(clock=lambda: FIXED):
            raise RuntimeError("crash")
    # The interpreter prints the traceback after the block exits.
    assert isinstance(sys.stderr, _TimestampedLines)
    print("Traceback (most recent call last):", file=sys.stderr)
    assert sink.getvalue() == (
        "2026-10-29T10:15:02.123Z Traceback (most recent call last):\n"
    )


def _cli_run_arguments(tmp_path: Path) -> list[str]:
    return [
        "--db",
        str(tmp_path / "private" / "gateway.db"),
        "--calibration-ledger",
        str(tmp_path / "private" / "calibration.jsonl"),
        "run",
        "--control-only",
        "--token-source",
        "keychain",
        "--bot-username",
        "KingdomResearchBot",
    ]


def test_cli_run_stamps_boot_line_and_restores_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("KINGDOM_TELEGRAM_STARS_PRICE", "0")
    monkeypatch.setattr(cli, "resolve_token", lambda **_kwargs: TOKEN)
    monkeypatch.setattr(cli, "TelegramAPI", lambda _token: object())
    monkeypatch.setattr(cli, "prepare_runtime", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(cli, "_run_gateway", lambda *_args, **_kwargs: 0)
    captured_stream = sys.stderr

    assert main(_cli_run_arguments(tmp_path)) == 0

    assert sys.stderr is captured_stream
    output = capsys.readouterr()
    assert output.out == ""
    lines = output.err.splitlines()
    assert len(lines) == 1
    assert STAMP.match(lines[0])
    assert lines[0].endswith(
        "gateway: boot checks passed: bot identity and research profile "
        "verified; runner lock held; polling starts"
    )


def test_cli_run_boot_transport_failure_is_stamped_and_class_tagged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failing_boot(*_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
        raise TelegramError(
            "Telegram transport failed before a response was observed",
            ambiguous=True,
            failure_class="URLError/gaierror",
        )

    monkeypatch.setenv("KINGDOM_TELEGRAM_STARS_PRICE", "0")
    monkeypatch.setattr(cli, "resolve_token", lambda **_kwargs: TOKEN)
    monkeypatch.setattr(cli, "TelegramAPI", lambda _token: object())
    monkeypatch.setattr(cli, "prepare_runtime", failing_boot)
    monkeypatch.setattr(
        cli, "_run_gateway", lambda *_a, **_k: pytest.fail("polled after failed boot")
    )

    assert main(_cli_run_arguments(tmp_path)) == 1

    err = capsys.readouterr().err
    assert STAMP.match(err)
    assert err.endswith(
        "gateway: Telegram transport failed before a response was observed "
        "[class=URLError/gaierror]\n"
    )
    assert "boot checks passed" not in err
    assert_credential_free(err)


def test_non_run_commands_are_not_stamped(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing-signals.jsonl"
    db = tmp_path / "private" / "gateway.db"
    assert main(["--db", str(db), "ingest", "--source", str(missing)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("gateway: signal source is not a readable file")
    assert not STAMP.search(err)


# --- (b) failure-class tags -------------------------------------------------


def _http_error(url: str, code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url, code, f"{MESSAGE_MARKER} {TOKEN}", {}, io.BytesIO(body)  # type: ignore[arg-type]
    )


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = io.BytesIO(body)

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._body.read(limit)


def _raise(factory: Callable[[str], BaseException]) -> Callable[..., Any]:
    def opener(request: Any, *, timeout: float) -> Any:
        raise factory(request.full_url)

    return opener


def _respond(body: bytes) -> Callable[..., Any]:
    def opener(_request: Any, *, timeout: float) -> Any:
        return _Response(body)

    return opener


CONFLICT_BODY = json.dumps(
    {
        "ok": False,
        "error_code": 409,
        "description": f"Conflict: {BODY_MARKER} {TOKEN}",
    }
).encode()

FAILURES: list[tuple[Callable[..., Any], str]] = [
    (
        _raise(lambda url: urllib.error.URLError(
            ConnectionResetError(f"{MESSAGE_MARKER} reset at {url}")
        )),
        "URLError/ConnectionResetError",
    ),
    (_raise(lambda url: TimeoutError(f"{MESSAGE_MARKER} {url}")), "TimeoutError"),
    (
        _raise(lambda url: http.client.RemoteDisconnected(f"{MESSAGE_MARKER} {url}")),
        "RemoteDisconnected",
    ),
    (_raise(lambda url: _http_error(url, 409, CONFLICT_BODY)), "HTTP409"),
    (_raise(lambda url: _http_error(url, 502, f"<html>{BODY_MARKER}</html>".encode())), "HTTP502"),
    (_respond(f"not json {BODY_MARKER} {TOKEN}".encode()), "invalid_response/JSONDecodeError"),
    (
        _respond(json.dumps({"ok": False, "error_code": 400, "description": BODY_MARKER}).encode()),
        "ok_false/400",
    ),
    (_respond(json.dumps({"ok": True, "result": [{"update_id": -1}]}).encode()), "invalid_updates"),
]


@pytest.mark.parametrize(("opener", "expected"), FAILURES)
def test_transport_failures_carry_type_name_tags_only(
    opener: Callable[..., Any], expected: str
) -> None:
    api = TelegramAPI(TOKEN, request_opener=opener)
    with pytest.raises(TelegramError) as failure:
        api.get_updates(offset=0, timeout=0)
    assert failure.value.failure_class == expected
    assert_credential_free(failure.value.failure_class)


def test_run_loop_failure_lines_never_carry_url_token_message_or_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Drive the real BotService and TelegramAPI.call through each failure."""

    openers = iter(opener for opener, _expected in FAILURES)
    current: dict[str, Callable[..., Any]] = {"opener": next(openers)}

    def opener(request: Any, *, timeout: float) -> Any:
        assert TOKEN in request.full_url  # the secret is present at the seam
        return current["opener"](request, timeout=timeout)

    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        try:
            current["opener"] = next(openers)
        except StopIteration:
            raise KeyboardInterrupt from None

    monkeypatch.setattr(cli.time, "sleep", fake_sleep)
    private = tmp_path / "private"
    gateway = GatewayStore(private / "gateway.db")
    args = Namespace(
        once=False, control_only=True, calibration_ledger=private / "calibration.jsonl"
    )
    api = TelegramAPI(TOKEN, request_opener=opener)
    liveness = _GatewayLiveness(clock=FakeClock())
    try:
        with pytest.raises(KeyboardInterrupt):
            _run_gateway(args, gateway, api, ServiceConfig(), liveness=liveness)
    finally:
        gateway.close()

    output = capsys.readouterr()
    assert output.out == ""
    assert_credential_free(output.err)
    failures = [
        line for line in output.err.splitlines()
        if line.startswith("gateway: transient Telegram failure: ")
    ]
    assert [line.split("class=", 1)[1].split(" ", 1)[0] for line in failures] == [
        expected for _opener, expected in FAILURES
    ]
    conflict = [line for line in failures if "class=HTTP409" in line]
    assert conflict == [
        "gateway: transient Telegram failure: class=HTTP409 retry_in_s=5 "
        "(409 conflict: another getUpdates poller or a webhook is active for this bot)"
    ]
    assert sum("409 conflict" in line for line in failures) == 1
    # Retry timing is unchanged: no retry_after, so the existing 5 s pause.
    assert sleeps == [5] * len(FAILURES)
    # The first liveness line follows the first attempt; later ones wait 6 h.
    alive = [line for line in output.err.splitlines() if line.startswith("gateway: alive")]
    assert alive == [
        "gateway: alive window_s=0 polls_ok=0 updates_seen=0 updates_failed=0 "
        "transient_failures=1 by_class=URLError/ConnectionResetError:1 db_busy=0"
    ]


def test_rate_limit_retry_after_is_honoured_and_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    body = json.dumps(
        {"ok": False, "error_code": 429, "description": BODY_MARKER,
         "parameters": {"retry_after": 7}}
    ).encode()
    api = TelegramAPI(TOKEN, request_opener=_raise(lambda url: _http_error(url, 429, body)))
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", fake_sleep)
    private = tmp_path / "private"
    gateway = GatewayStore(private / "gateway.db")
    args = Namespace(
        once=False, control_only=True, calibration_ledger=private / "calibration.jsonl"
    )
    try:
        with pytest.raises(KeyboardInterrupt):
            _run_gateway(args, gateway, api, ServiceConfig(), liveness=_GatewayLiveness())
    finally:
        gateway.close()
    err = capsys.readouterr().err
    assert sleeps == [7]
    assert "gateway: transient Telegram failure: class=HTTP429 retry_in_s=7\n" in err
    assert "409" not in err
    assert_credential_free(err)


def test_untagged_or_unsafe_failure_class_falls_back_to_type_name() -> None:
    assert cli._transient_failure_class(TelegramError("x")) == "TelegramError"
    assert cli._transient_failure_class(TelegramError("x", error_code=403)) == "TelegramError/403"
    unsafe = TelegramError("x", failure_class=f"https://api.telegram.org/bot{TOKEN}/getUpdates")
    assert cli._transient_failure_class(unsafe) == "TelegramError"


# --- (c) liveness cadence ---------------------------------------------------


def test_liveness_first_line_then_at_most_one_per_interval() -> None:
    clock = FakeClock(1000.0)
    liveness = _GatewayLiveness(clock=clock)
    clock.now += 45
    liveness.record_poll(idle_report(updates=2, failed_updates=1))
    assert liveness.due_line() == (
        "gateway: alive window_s=45 polls_ok=1 updates_seen=3 updates_failed=1 "
        "transient_failures=0 db_busy=0"
    )
    last = clock.now
    for _ in range(100):
        clock.now += 60
        liveness.record_poll(idle_report())
        assert liveness.due_line() is None
    liveness.record_transient("HTTP502")
    liveness.record_transient("URLError/TimeoutError")
    liveness.record_transient("HTTP502")
    liveness.record_db_busy()
    clock.now = last + LIVENESS_INTERVAL_SECONDS - 0.001
    assert liveness.due_line() is None
    clock.now = last + LIVENESS_INTERVAL_SECONDS
    assert liveness.due_line() == (
        "gateway: alive window_s=21600 polls_ok=100 updates_seen=0 updates_failed=0 "
        "transient_failures=3 by_class=HTTP502:2,URLError/TimeoutError:1 db_busy=1"
    )
    # Counts reset: the next line reports only its own interval.
    clock.now += LIVENESS_INTERVAL_SECONDS
    assert liveness.due_line() == (
        "gateway: alive window_s=21600 polls_ok=0 updates_seen=0 updates_failed=0 "
        "transient_failures=0 db_busy=0"
    )


def test_liveness_ignores_non_count_values() -> None:
    liveness = _GatewayLiveness(clock=FakeClock())
    liveness.record_poll({"updates": True, "failed_updates": -3})
    liveness.record_poll({"updates": "7"})
    assert liveness.due_line() == (
        "gateway: alive window_s=0 polls_ok=2 updates_seen=0 updates_failed=0 "
        "transient_failures=0 db_busy=0"
    )


def test_run_loop_emits_one_alive_line_per_six_hours_and_keeps_stdout_quiet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = FakeClock()
    polls = 1000  # 1000 idle 45 s long polls = 12.5 hours

    class IdleService:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.count = 0

        def poll_once(self, **kwargs: Any) -> Mapping[str, int]:
            assert kwargs == {"broadcast": False, "deliver_corrections": False}
            if self.count == polls:
                raise KeyboardInterrupt
            self.count += 1
            clock.now += 45
            return idle_report(updates=1 if self.count == 300 else 0)

    monkeypatch.setattr(cli, "BotService", IdleService)
    monkeypatch.setattr(cli.time, "sleep", lambda _s: pytest.fail("idle loop slept"))
    private = tmp_path / "private"
    gateway = GatewayStore(private / "gateway.db")
    args = Namespace(
        once=False, control_only=True, calibration_ledger=private / "calibration.jsonl"
    )
    try:
        with pytest.raises(KeyboardInterrupt):
            _run_gateway(
                args, gateway, object(), ServiceConfig(),  # type: ignore[arg-type]
                liveness=_GatewayLiveness(clock=clock),
            )
    finally:
        gateway.close()

    output = capsys.readouterr()
    # stdout keeps its existing contract: only polls with activity print.
    assert [json.loads(line)["updates"] for line in output.out.splitlines()] == [1]
    assert output.err.splitlines() == [
        "gateway: alive window_s=45 polls_ok=1 updates_seen=0 updates_failed=0 "
        "transient_failures=0 db_busy=0",
        "gateway: alive window_s=21600 polls_ok=480 updates_seen=1 updates_failed=0 "
        "transient_failures=0 db_busy=0",
        "gateway: alive window_s=21600 polls_ok=480 updates_seen=0 updates_failed=0 "
        "transient_failures=0 db_busy=0",
    ]
