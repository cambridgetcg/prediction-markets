from __future__ import annotations

import json
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import pytest

from telegram_gateway import bootstrap, cli
from telegram_gateway.bootstrap import (
    DEFAULT_BOT_NAME,
    DEFAULT_DESCRIPTION,
    DEFAULT_SHORT_DESCRIPTION,
    KEYCHAIN_SERVICE,
    PRIVATE_COMMAND_SCOPE,
    build_botfather_plan,
    build_managed_bot_link,
    configure_bot,
    desired_commands,
    inspect_bot,
    keychain_account,
    load_keychain_token,
    prepare_runtime,
    resolve_token,
    store_token_interactively,
    validate_bot_username,
    validate_privacy_url,
)
from telegram_gateway.cli import main
from telegram_gateway.service import BotService
from telegram_gateway.store import GatewayStore
from telegram_gateway.telegram_api import TelegramAPI, TelegramError


TOKEN = "not-a-real-token-value-for-unit-tests"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("bootstrap tests must use fake transports")

    monkeypatch.setattr("socket.create_connection", forbidden)


class FakeStore:
    def __init__(self, *, initially_bound: bool = True) -> None:
        self.bindings: list[tuple[int, str]] = []
        self.bound: tuple[int, str] | None = (
            (7001, "https://api.telegram.org") if initially_bound else None
        )

    def bind_telegram_provider(
        self,
        bot_id: int,
        api_origin: str,
        *,
        allow_create: bool = True,
    ) -> None:
        self.bindings.append((bot_id, api_origin))
        requested = (bot_id, api_origin)
        if self.bound is None:
            if not allow_create:
                raise ValueError("run bot-doctor first")
            self.bound = requested
        elif self.bound != requested:
            raise ValueError("different Telegram provider")


class FakeAPI:
    provider_origin = "https://api.telegram.org"

    def __init__(self) -> None:
        self.identity: dict[str, Any] = {
            "id": 7001,
            "is_bot": True,
            "username": "KingdomResearchBot",
            "can_join_groups": False,
            "can_read_all_group_messages": False,
            "supports_guest_queries": False,
            "supports_inline_queries": False,
            "can_connect_to_business": False,
            "has_main_web_app": False,
            "can_manage_bots": False,
            "supports_join_request_queries": False,
        }
        self.webhook: dict[str, Any] = {
            "configured": False,
            "has_custom_certificate": False,
            "pending_update_count": 0,
            "last_error_present": False,
        }
        self.name = ""
        self.description = ""
        self.short_description = ""
        self.private_commands: list[dict[str, str]] = []
        self.scope_commands: dict[str, list[dict[str, str]]] = {
            "default": [{"command": "old", "description": "Old command"}],
            "all_group_chats": [],
            "all_chat_administrators": [],
        }
        self.menu_type = "default"
        self.calls: list[tuple[str, Any]] = []

    def get_me(self) -> Mapping[str, Any]:
        self.calls.append(("get_me", None))
        return dict(self.identity)

    def get_webhook_info(self) -> Mapping[str, Any]:
        self.calls.append(("get_webhook_info", None))
        return dict(self.webhook)

    def get_my_commands(self, *, scope: Mapping[str, str]) -> list[dict[str, str]]:
        self.calls.append(("get_my_commands", dict(scope)))
        if scope["type"] == "all_private_chats":
            return [dict(item) for item in self.private_commands]
        return [dict(item) for item in self.scope_commands[str(scope["type"])]]

    def set_my_commands(
        self, commands: list[Mapping[str, str]], *, scope: Mapping[str, str]
    ) -> bool:
        self.calls.append(("set_my_commands", (commands, dict(scope))))
        self.private_commands = [dict(item) for item in commands]
        return True

    def delete_my_commands(self, *, scope: Mapping[str, str]) -> bool:
        self.calls.append(("delete_my_commands", dict(scope)))
        self.scope_commands[str(scope["type"])] = []
        return True

    def get_my_name(self) -> str:
        self.calls.append(("get_my_name", None))
        return self.name

    def set_my_name(self, value: str) -> bool:
        self.calls.append(("set_my_name", value))
        self.name = value
        return True

    def get_my_description(self) -> str:
        self.calls.append(("get_my_description", None))
        return self.description

    def set_my_description(self, value: str) -> bool:
        self.calls.append(("set_my_description", value))
        self.description = value
        return True

    def get_my_short_description(self) -> str:
        self.calls.append(("get_my_short_description", None))
        return self.short_description

    def set_my_short_description(self, value: str) -> bool:
        self.calls.append(("set_my_short_description", value))
        self.short_description = value
        return True

    def get_chat_menu_button_type(self) -> str:
        self.calls.append(("get_chat_menu_button_type", None))
        return self.menu_type

    def set_chat_menu_commands(self) -> bool:
        self.calls.append(("set_chat_menu_commands", None))
        self.menu_type = "commands"
        return True


@pytest.mark.parametrize(
    "value,expected",
    [
        ("@KingdomResearchBot", "KingdomResearchBot"),
        ("a_bot", "a_bot"),
        ("A" + "x" * 28 + "Bot", "A" + "x" * 28 + "Bot"),
    ],
)
def test_bot_username_validation(value: str, expected: str) -> None:
    assert validate_bot_username(value) == expected


@pytest.mark.parametrize(
    "value",
    ["bot", "@@KingdomBot", "KingdomResearch", "bad-name-bot", "A" + "x" * 29 + "Bot"],
)
def test_invalid_bot_username_fails(value: str) -> None:
    with pytest.raises(ValueError, match="bot username"):
        validate_bot_username(value)


def test_plan_contains_no_credential_and_keeps_creation_human_confirmed() -> None:
    plan = build_botfather_plan("KingdomResearchBot")
    rendered = repr(plan).lower()
    assert plan["privacy_policy_status"] == "required_before_public_launch"
    assert plan["username_availability"] == "BotFather must confirm"
    assert "human must visibly confirm" in plan["automation_boundary"]
    assert "token" in rendered
    assert TOKEN not in rendered


def test_privacy_url_is_https_and_credential_free() -> None:
    assert validate_privacy_url("https://example.org/kingdom/privacy")
    for value in (
        "http://example.org/privacy",
        "https://user:pass@example.org/privacy",
        "https://example.org/privacy?access=opaque",
        "https://example.org/privacy#secret",
    ):
        with pytest.raises(ValueError, match="privacy policy URL"):
            validate_privacy_url(value)


def test_managed_bot_link_encodes_name_and_never_contains_a_token() -> None:
    link = build_managed_bot_link(
        "KingdomManagerBot", "KingdomChildBot", child_name="KINGDOM Research / EU"
    )
    parsed = urllib.parse.urlsplit(link)
    assert parsed.path == "/newbot/KingdomManagerBot/KingdomChildBot"
    assert urllib.parse.parse_qs(parsed.query) == {"name": ["KINGDOM Research / EU"]}
    assert TOKEN not in link


def test_explicit_environment_source_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KINGDOM_TELEGRAM_BOT_TOKEN", TOKEN)
    with pytest.raises(ValueError, match="required"):
        resolve_token(source="environment", bot_username=None, environment={})
    assert (
        resolve_token(
            source="environment",
            bot_username="IgnoredBot",
            environment={"KINGDOM_TELEGRAM_BOT_TOKEN": TOKEN},
        )
        == TOKEN
    )

    with pytest.raises(ValueError, match="only valid"):
        resolve_token(
            source="environment",
            bot_username="IgnoredBot",
            keychain_account_name="ignoredbot-v2",
            environment={"KINGDOM_TELEGRAM_BOT_TOKEN": TOKEN},
        )


def test_keychain_accounts_are_explicit_lowercase_slots() -> None:
    assert keychain_account("KingdomResearchBot") == "kingdomresearchbot"
    assert (
        keychain_account("KingdomResearchBot", "kingdomresearchbot-v2")
        == "kingdomresearchbot-v2"
    )
    for value in ("KingdomResearchBot-v2", "../kingdomresearchbot", ""):
        with pytest.raises(ValueError, match="Keychain account"):
            keychain_account("KingdomResearchBot", value)


@pytest.mark.parametrize(
    "arguments",
    [
        ["bot-token-store", "--bot-username", "KingdomResearchBot"],
        ["bot-doctor", "--bot-username", "KingdomResearchBot"],
        ["bot-configure", "--bot-username", "KingdomResearchBot"],
        ["bot-campaign", "--bot-username", "KingdomResearchBot"],
        [
            "stars-reconcile",
            "--token-source",
            "keychain",
            "--bot-username",
            "KingdomResearchBot",
        ],
        [
            "run",
            "--token-source",
            "keychain",
            "--bot-username",
            "KingdomResearchBot",
        ],
    ],
)
def test_all_credential_commands_accept_versioned_keychain_slot(
    arguments: list[str],
) -> None:
    parsed = cli.build_parser().parse_args(
        [*arguments, "--keychain-account", "kingdomresearchbot-v2"]
    )
    assert parsed.keychain_account == "kingdomresearchbot-v2"


def test_keychain_read_is_captured_and_never_places_token_in_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[list[str], dict[str, Any]]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        seen.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=(TOKEN + "\n").encode())

    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    assert load_keychain_token("KingdomResearchBot") == TOKEN
    command, kwargs = seen[0]
    assert command[-1] == "-w"
    assert TOKEN not in command
    assert KEYCHAIN_SERVICE in command
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.DEVNULL


def test_keychain_failure_does_not_echo_provider_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 44, stdout=TOKEN.encode(), stderr=TOKEN.encode())

    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    with pytest.raises(OSError) as failure:
        load_keychain_token("KingdomResearchBot")
    assert TOKEN not in str(failure.value)


def test_interactive_store_prompts_with_w_last_and_clears_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        calls.append((command, kwargs))
        return_code = (
            44
            if len(command) > 1 and command[1] == "find-generic-password"
            else 0
        )
        return subprocess.CompletedProcess(command, return_code)

    monkeypatch.setattr(bootstrap.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    result = store_token_interactively(
        "KingdomResearchBot",
        keychain_account_name="kingdomresearchbot-v2",
    )

    add_command = calls[1][0]
    assert add_command[-1] == "-w"
    assert "-A" not in add_command
    assert "-U" not in add_command
    assert TOKEN not in add_command
    assert add_command[add_command.index("-a") + 1] == "kingdomresearchbot-v2"
    assert calls[-1][0] == [str(Path("/usr/bin/pbcopy"))]
    assert calls[-1][1]["input"] == b""
    assert result["clipboard_cleared"] is True
    assert result["keychain_account"] == "kingdomresearchbot-v2"
    assert "same logged-in account" in result["access_boundary"]


def test_interactive_store_refuses_overwrite_and_still_clears_clipboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[Any]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(bootstrap.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    with pytest.raises(ValueError, match="already exists"):
        store_token_interactively("KingdomResearchBot")
    assert calls[-1] == ["/usr/bin/pbcopy"]
    assert not any("add-generic-password" in command for command in calls)


def test_cli_token_store_passes_versioned_slot_without_replace(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: dict[str, Any] = {}

    def store(username: object, *, keychain_account_name: object | None) -> dict[str, Any]:
        seen["username"] = username
        seen["account"] = keychain_account_name
        return {"stored": True, "clipboard_cleared": True}

    monkeypatch.setattr(cli, "store_token_interactively", store)
    assert (
        main(
            [
                "bot-token-store",
                "--bot-username",
                "KingdomResearchBot",
                "--keychain-account",
                "kingdomresearchbot-v2",
            ]
        )
        == 0
    )
    assert seen == {
        "username": "KingdomResearchBot",
        "account": "kingdomresearchbot-v2",
    }
    assert TOKEN not in capsys.readouterr().out


def test_doctor_report_fails_closed_until_profile_is_configured() -> None:
    api = FakeAPI()
    report = inspect_bot(api, "kingdomresearchbot")  # Telegram usernames are case-insensitive.
    assert report["runtime_ready"] is True
    assert report["bot_api_profile_ready"] is False
    assert report["checks"]["private_commands_match"] is False
    assert report["webhook"]["configured"] is False
    assert "manual" in report["privacy_policy_check"]


def test_configure_binds_identity_then_applies_and_verifies_exact_profile() -> None:
    api = FakeAPI()
    store = FakeStore()
    report = configure_bot(api, store, "KingdomResearchBot")

    assert store.bindings == [(7001, "https://api.telegram.org")]
    assert report["bot_api_profile_ready"] is True
    assert report["configuration_status"] == "verified"
    assert api.name == DEFAULT_BOT_NAME
    assert api.description == DEFAULT_DESCRIPTION
    assert api.short_description == DEFAULT_SHORT_DESCRIPTION
    assert api.private_commands == desired_commands()
    assert api.menu_type == "commands"
    assert all(not commands for commands in api.scope_commands.values())


def test_configure_refuses_wrong_identity_before_binding_or_mutation() -> None:
    api = FakeAPI()
    api.identity["username"] = "DifferentBot"
    store = FakeStore()
    with pytest.raises(ValueError, match="different Telegram bot"):
        configure_bot(api, store, "KingdomResearchBot")
    assert store.bindings == []
    assert not any(call[0].startswith("set_") for call in api.calls)


def test_configure_never_deletes_a_conflicting_webhook() -> None:
    api = FakeAPI()
    api.webhook["configured"] = True
    store = FakeStore()
    with pytest.raises(ValueError, match="no webhook was removed"):
        configure_bot(api, store, "KingdomResearchBot")
    assert store.bindings == []
    assert not any(call[0].startswith("set_") for call in api.calls)


def test_configure_names_ambiguous_partial_failure_and_recovery() -> None:
    api = FakeAPI()

    def fail_description(_value: str) -> bool:
        api.calls.append(("set_my_description", None))
        raise TelegramError(TOKEN, ambiguous=True)

    api.set_my_description = fail_description  # type: ignore[method-assign]
    with pytest.raises(ValueError) as failure:
        configure_bot(api, FakeStore(), "KingdomResearchBot")
    message = str(failure.value)
    assert "set_description" in message
    assert "outcome unknown" in message
    assert "bot-doctor" in message
    assert "idempotent" in message
    assert TOKEN not in message
    assert api.name == DEFAULT_BOT_NAME
    assert api.short_description == ""


def test_configure_reports_readback_failure_after_mutation() -> None:
    api = FakeAPI()
    original_get_name = api.get_my_name

    def fail_readback() -> str:
        if api.name:
            raise TelegramError(TOKEN, ambiguous=True)
        return original_get_name()

    api.get_my_name = fail_readback  # type: ignore[method-assign]
    with pytest.raises(ValueError) as failure:
        configure_bot(api, FakeStore(), "KingdomResearchBot")
    message = str(failure.value)
    assert "readback did not verify" in message
    assert "bot-doctor" in message
    assert TOKEN not in message


def test_configure_reports_valid_but_mismatched_readback() -> None:
    api = FakeAPI()

    def leave_default_menu() -> bool:
        api.calls.append(("set_chat_menu_commands", None))
        return True

    api.set_chat_menu_commands = leave_default_menu  # type: ignore[method-assign]
    report = configure_bot(api, FakeStore(), "KingdomResearchBot")
    assert report["bot_api_profile_ready"] is False
    assert report["configuration_status"] == "readback_mismatch"
    assert "bot-doctor" in report["configuration_recovery"]
    assert "idempotent" in report["configuration_recovery"]


def test_runtime_requires_private_only_flags_and_clear_webhook() -> None:
    store = FakeStore()
    api = FakeAPI()
    identity = prepare_runtime(api, store, expected_username="KingdomResearchBot")
    assert identity["id"] == 7001
    assert store.bindings == [(7001, "https://api.telegram.org")]

    unsafe = FakeAPI()
    unsafe.identity["can_join_groups"] = True
    with pytest.raises(ValueError, match="group joins"):
        prepare_runtime(unsafe, FakeStore(), expected_username="KingdomResearchBot")

    elevated = FakeAPI()
    elevated.identity["can_manage_bots"] = True
    with pytest.raises(ValueError, match="non-MVP"):
        prepare_runtime(elevated, FakeStore(), expected_username="KingdomResearchBot")

    topics = FakeAPI()
    topics.identity["has_topics_enabled"] = True
    with pytest.raises(ValueError, match="non-MVP"):
        prepare_runtime(topics, FakeStore(), expected_username="KingdomResearchBot")

    with pytest.raises(ValueError, match="bot-doctor"):
        prepare_runtime(
            FakeAPI(),
            FakeStore(initially_bound=False),
            expected_username="KingdomResearchBot",
        )


def test_offline_plan_and_config_preview_do_not_create_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "private" / "gateway.db"
    assert (
        main(
            [
                "--db",
                str(database),
                "bot-plan",
                "--bot-username",
                "KingdomResearchBot",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "--db",
                str(database),
                "bot-configure",
                "--bot-username",
                "KingdomResearchBot",
            ]
        )
        == 0
    )
    assert not database.exists()
    assert '"network_calls": 0' in capsys.readouterr().out


def test_provider_binding_precedes_runtime_and_bootstrap_campaign_is_idempotent(
    tmp_path: Path,
) -> None:
    with GatewayStore(tmp_path / "private" / "gateway.db") as store:
        with pytest.raises(ValueError, match="bot-doctor"):
            store.bind_telegram_provider(
                7001, "https://api.telegram.org", allow_create=False
            )
        store.bind_telegram_provider(7001, "https://api.telegram.org")
        first_code, first_created = store.get_or_create_bootstrap_campaign()
        second_code, second_created = store.get_or_create_bootstrap_campaign()
        assert first_created is True
        assert second_created is False
        assert second_code == first_code

        assert store.disable_promotion_campaign(first_code) is True
        with pytest.raises(ValueError, match="disabled"):
            store.get_or_create_bootstrap_campaign()


def test_authenticated_provider_username_is_durable_and_immutable(
    tmp_path: Path,
) -> None:
    with GatewayStore(tmp_path / "private" / "gateway.db") as store:
        store.bind_telegram_provider(7001, "https://api.telegram.org")
        with pytest.raises(ValueError, match="no verified Telegram bot username"):
            store.require_telegram_provider_bot_username("KingdomResearchBot")
        with pytest.raises(ValueError, match="bot-doctor"):
            store.bind_authenticated_telegram_provider(
                7001,
                "https://api.telegram.org",
                "KingdomResearchBot",
            )

        store.bind_authenticated_telegram_provider(
            7001,
            "https://api.telegram.org",
            "KingdomResearchBot",
            allow_create=False,
            allow_legacy_username_backfill=True,
        )
        assert (
            store.require_telegram_provider_bot_username("kingdomresearchbot")
            == "KingdomResearchBot"
        )
        with pytest.raises(ValueError, match="different Telegram bot username"):
            store.bind_authenticated_telegram_provider(
                7001,
                "https://api.telegram.org",
                "DifferentResearchBot",
                allow_create=False,
                allow_legacy_username_backfill=True,
            )
        assert (
            store.require_telegram_provider_bot_username("KingdomResearchBot")
            == "KingdomResearchBot"
        )


def test_bot_doctor_persists_authenticated_canonical_username(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "private" / "gateway.db"
    api = FakeAPI()
    monkeypatch.setattr(cli, "resolve_token", lambda **_kwargs: TOKEN)
    monkeypatch.setattr(cli, "TelegramAPI", lambda _token: api)

    assert (
        main(
            [
                "--db",
                str(database),
                "bot-doctor",
                "--bot-username",
                "kingdomresearchbot",
                "--token-source",
                "environment",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["identity"]["username"] == "KingdomResearchBot"
    with GatewayStore(database) as store:
        assert (
            store.require_telegram_provider_bot_username("kingdomresearchbot")
            == "KingdomResearchBot"
        )


def test_bot_campaign_backfills_legacy_binding_after_verified_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "private" / "gateway.db"
    with GatewayStore(database) as store:
        store.bind_telegram_provider(7001, "https://api.telegram.org")

    api = FakeAPI()
    api.name = DEFAULT_BOT_NAME
    api.description = DEFAULT_DESCRIPTION
    api.short_description = DEFAULT_SHORT_DESCRIPTION
    api.private_commands = desired_commands()
    api.scope_commands = {key: [] for key in api.scope_commands}
    api.menu_type = "commands"
    monkeypatch.setattr(cli, "resolve_token", lambda **_kwargs: TOKEN)
    monkeypatch.setattr(cli, "TelegramAPI", lambda _token: api)

    assert (
        main(
            [
                "--db",
                str(database),
                "bot-campaign",
                "--bot-username",
                "kingdomresearchbot",
                "--token-source",
                "environment",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["deep_link"].startswith("https://t.me/KingdomResearchBot?start=")
    with GatewayStore(database) as store:
        assert (
            store.require_telegram_provider_bot_username("kingdomresearchbot")
            == "KingdomResearchBot"
        )


def test_bot_api_webhook_report_drops_url_and_error_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = TOKEN
    api = TelegramAPI(token)

    def call(_self: TelegramAPI, method: str, *_args: Any, **_kwargs: Any) -> Any:
        assert method == "getWebhookInfo"
        return {
            "url": "https://example.org/super-secret-webhook-path",
            "has_custom_certificate": False,
            "pending_update_count": 3,
            "last_error_date": 1,
            "last_error_message": "provider detail that should not escape",
        }

    monkeypatch.setattr(TelegramAPI, "call", call)
    report = api.get_webhook_info()
    assert report == {
        "configured": True,
        "has_custom_certificate": False,
        "pending_update_count": 3,
        "last_error_present": True,
    }
    assert "secret-webhook" not in repr(report)


def test_bot_api_profile_calls_use_exact_private_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Any]] = []

    def call(_self: TelegramAPI, method: str, payload: Any = None, **_kwargs: Any) -> Any:
        calls.append((method, payload))
        if method == "setMyCommands":
            return True
        if method == "getMyCommands":
            return desired_commands()
        raise AssertionError(method)

    monkeypatch.setattr(TelegramAPI, "call", call)
    api = TelegramAPI(TOKEN)
    assert api.set_my_commands(desired_commands(), scope=PRIVATE_COMMAND_SCOPE)
    assert api.get_my_commands(scope=PRIVATE_COMMAND_SCOPE) == desired_commands()
    assert calls[0][1]["scope"] == {"type": "all_private_chats"}
    assert calls[1][1]["scope"] == {"type": "all_private_chats"}


def test_ephemeral_or_future_command_fields_cannot_false_match_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def call(_self: TelegramAPI, _method: str, _payload: Any = None, **_kwargs: Any) -> Any:
        return [
            {
                "command": "start",
                "description": "Open KINGDOM research",
                "is_ephemeral": True,
            }
        ]

    monkeypatch.setattr(TelegramAPI, "call", call)
    with pytest.raises(TelegramError, match="commands"):
        TelegramAPI(TOKEN).get_my_commands(scope=PRIVATE_COMMAND_SCOPE)


def test_get_me_rejects_malformed_capability_without_echoing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def call(_self: TelegramAPI, _method: str, *_args: Any, **_kwargs: Any) -> Any:
        return {
            "id": 7,
            "is_bot": True,
            "username": "KingdomResearchBot",
            "can_join_groups": "false",
        }

    monkeypatch.setattr(TelegramAPI, "call", call)
    with pytest.raises(TelegramError) as failure:
        TelegramAPI(TOKEN).get_me()
    assert TOKEN not in str(failure.value)


@pytest.mark.parametrize(
    ("token", "method", "message"),
    [
        (TOKEN + "/extra", "getMe", "token"),
        (TOKEN, "../getMe", "method"),
    ],
)
def test_direct_api_rejects_unsafe_path_components_before_network(
    token: str,
    method: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "telegram_gateway.telegram_api.open_request",
        lambda *_args, **_kwargs: pytest.fail("unsafe API path reached the network"),
    )
    with pytest.raises(TelegramError, match=message):
        TelegramAPI(token).call(method)


def test_cli_control_only_skips_source_ingestion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ControlOnlyService:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def poll_once(self, **kwargs: Any) -> Mapping[str, int]:
            assert kwargs == {
                "timeout": 0,
                "broadcast": False,
                "deliver_corrections": False,
            }
            return {
                "updates": 0,
                "broadcast_paused": 1,
                "corrections_paused": 1,
            }

    monkeypatch.setenv("KINGDOM_TELEGRAM_STARS_PRICE", "0")
    monkeypatch.setattr(cli, "resolve_token", lambda **_kwargs: TOKEN)
    monkeypatch.setattr(cli, "TelegramAPI", lambda _token: object())
    monkeypatch.setattr(cli, "prepare_runtime", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(cli, "BotService", ControlOnlyService)
    monkeypatch.setattr(
        cli,
        "_import_without_stopping_control_plane",
        lambda *_args, **_kwargs: pytest.fail("signal source was imported"),
    )
    monkeypatch.setattr(
        cli,
        "_import_lifecycle_without_stopping_control_plane",
        lambda *_args, **_kwargs: pytest.fail("lifecycle source was imported"),
    )

    assert (
        main(
            [
                "--db",
                str(tmp_path / "private" / "gateway.db"),
                "run",
                "--once",
                "--control-only",
                "--token-source",
                "keychain",
                "--bot-username",
                "KingdomResearchBot",
            ]
        )
        == 0
    )


def test_control_only_poll_sends_no_group_reply_or_background_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PollTransport:
        def __init__(self) -> None:
            self.sent: list[Mapping[str, Any]] = []

        def get_updates(self, *, offset: int, timeout: int) -> list[Mapping[str, Any]]:
            assert timeout == 0
            return [
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 9,
                        "date": 1_700_000_000,
                        "from": {"id": 77},
                        "chat": {"id": -1001, "type": "group"},
                        "text": "/start",
                    },
                },
                {
                    "update_id": 2,
                    "message": {
                        "message_id": 10,
                        "date": 1_700_000_001,
                        "from": {"id": 88, "is_bot": True},
                        "chat": {"id": 88, "type": "private"},
                        "text": "/start",
                    },
                },
            ]

        def send_text(self, chat_id: int, text: str, **kwargs: Any) -> Mapping[str, Any]:
            self.sent.append({"chat_id": chat_id, "text": text, **kwargs})
            return {"message_id": 1}

    transport = PollTransport()
    with GatewayStore(tmp_path / "private" / "gateway.db") as store:
        service = BotService(store, transport)  # type: ignore[arg-type]
        monkeypatch.setattr(
            service,
            "broadcast_pending_corrections",
            lambda: pytest.fail("control-only mode attempted correction delivery"),
        )
        result = service.poll_once(
            timeout=0,
            broadcast=False,
            deliver_corrections=False,
        )
        assert result["updates"] == 2
        assert result["broadcast_paused"] == 1
        assert result["corrections_paused"] == 1
        assert transport.sent == []
