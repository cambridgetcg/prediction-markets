from __future__ import annotations

from typing import Any, Mapping

import pytest

from telegram_gateway.bootstrap import (
    OPS_BOT_DESCRIPTION,
    OPS_BOT_NAME,
    OPS_BOT_PROFILE,
    OPS_BOT_SHORT_DESCRIPTION,
    PRIVATE_COMMAND_SCOPE,
    RESEARCH_BOT_PROFILE,
    bot_profile,
    build_botfather_plan,
    configure_bot,
    desired_commands,
    inspect_bot,
    prepare_runtime,
)


class OpsProfileStore:
    def __init__(self) -> None:
        self.bound: list[tuple[int, str, bool]] = []

    def bind_telegram_provider(
        self, bot_id: int, api_origin: str, *, allow_create: bool = True
    ) -> None:
        self.bound.append((bot_id, api_origin, allow_create))


class OpsProfileAPI:
    provider_origin = "https://api.telegram.org"

    def __init__(self) -> None:
        self.identity: dict[str, Any] = {
            "id": 8001,
            "is_bot": True,
            "username": "KingdomOpsBot",
            "can_join_groups": False,
            "can_read_all_group_messages": False,
            "supports_guest_queries": False,
            "supports_inline_queries": False,
            "can_connect_to_business": False,
            "has_main_web_app": False,
            "has_topics_enabled": False,
            "allows_users_to_create_topics": False,
            "can_manage_bots": False,
            "supports_join_request_queries": False,
        }
        self.name = ""
        self.description = ""
        self.short_description = ""
        self.private_commands: list[dict[str, str]] = []
        self.scope_commands: dict[str, list[dict[str, str]]] = {
            "default": [],
            "all_group_chats": [],
            "all_chat_administrators": [],
        }
        self.menu_type = "default"

    def get_me(self) -> Mapping[str, Any]:
        return dict(self.identity)

    def get_webhook_info(self) -> Mapping[str, Any]:
        return {
            "configured": False,
            "has_custom_certificate": False,
            "pending_update_count": 0,
            "last_error_present": False,
        }

    def get_my_commands(self, *, scope: Mapping[str, str]) -> list[dict[str, str]]:
        if scope["type"] == PRIVATE_COMMAND_SCOPE["type"]:
            return [dict(item) for item in self.private_commands]
        return [dict(item) for item in self.scope_commands[str(scope["type"])]]

    def set_my_commands(
        self, commands: list[Mapping[str, str]], *, scope: Mapping[str, str]
    ) -> bool:
        assert scope == PRIVATE_COMMAND_SCOPE
        self.private_commands = [dict(item) for item in commands]
        return True

    def delete_my_commands(self, *, scope: Mapping[str, str]) -> bool:
        self.scope_commands[str(scope["type"])] = []
        return True

    def get_my_name(self) -> str:
        return self.name

    def set_my_name(self, value: str) -> bool:
        self.name = value
        return True

    def get_my_description(self) -> str:
        return self.description

    def set_my_description(self, value: str) -> bool:
        self.description = value
        return True

    def get_my_short_description(self) -> str:
        return self.short_description

    def set_my_short_description(self, value: str) -> bool:
        self.short_description = value
        return True

    def get_chat_menu_button_type(self) -> str:
        return self.menu_type

    def set_chat_menu_commands(self) -> bool:
        self.menu_type = "commands"
        return True


def test_ops_profile_is_explicit_and_read_only() -> None:
    assert bot_profile("ops") is OPS_BOT_PROFILE
    assert OPS_BOT_PROFILE.name == OPS_BOT_NAME
    assert [item["command"] for item in desired_commands(OPS_BOT_PROFILE)] == [
        "agent_status",
        "agent_tasks",
        "agent_task",
        "agent_events",
        "journal_verify",
        "agent_privacy",
        "help",
    ]
    command_names = {
        item["command"] for item in desired_commands(OPS_BOT_PROFILE)
    }
    assert command_names.isdisjoint({"claim", "publish", "buy", "sell", "trade"})
    assert "does not identify beings" in OPS_BOT_DESCRIPTION
    assert "publish, pay, or trade" in OPS_BOT_DESCRIPTION


def test_unknown_profile_fails_closed() -> None:
    for value in ("", "admin", None, True):
        with pytest.raises(ValueError, match="research or ops"):
            bot_profile(value)


def test_ops_botfather_plan_is_credential_free_and_separate() -> None:
    plan = build_botfather_plan("KingdomOpsBot", profile=OPS_BOT_PROFILE)
    assert plan["profile"] == "ops"
    assert plan["bot_name"] == OPS_BOT_NAME
    assert plan["public_profile"]["commands"] == desired_commands(OPS_BOT_PROFILE)
    steps = "\n".join(plan["manual_steps"])
    assert "--db telegram_gateway/var/ops-bot.db" in steps
    assert "ops-bind" in steps
    assert "--bot-id" in steps
    assert "bot-doctor --bot-username" in steps
    assert "bot-configure --bot-username" in steps
    assert "bot-token-store --bot-username KingdomOpsBot --profile ops" in steps
    assert "Never automatically retry unknown delivery" in steps
    assert "bot-campaign" not in steps
    assert "KINGDOM_TELEGRAM_BOT_TOKEN" not in repr(plan)


def test_ops_profile_can_be_configured_and_read_back() -> None:
    api = OpsProfileAPI()
    store = OpsProfileStore()
    result = configure_bot(
        api,
        store,
        "KingdomOpsBot",
        profile=OPS_BOT_PROFILE,
    )
    assert result["profile"] == "ops"
    assert result["bot_api_profile_ready"] is True
    assert api.name == OPS_BOT_NAME
    assert api.description == OPS_BOT_DESCRIPTION
    assert api.short_description == OPS_BOT_SHORT_DESCRIPTION
    assert api.private_commands == desired_commands(OPS_BOT_PROFILE)
    assert store.bound == [(8001, api.provider_origin, False)]
    assert inspect_bot(api, "KingdomOpsBot", profile=OPS_BOT_PROFILE)[
        "bot_api_profile_ready"
    ] is True


def test_research_runner_rejects_an_ops_profile_before_polling() -> None:
    api = OpsProfileAPI()
    store = OpsProfileStore()
    configure_bot(api, store, "KingdomOpsBot", profile=OPS_BOT_PROFILE)

    with pytest.raises(ValueError, match="verified research bot profile"):
        prepare_runtime(
            api,
            store,
            expected_username="KingdomOpsBot",
            required_profile=RESEARCH_BOT_PROFILE,
        )


def test_profile_bound_runtime_accepts_matching_research_profile() -> None:
    api = OpsProfileAPI()
    store = OpsProfileStore()
    configure_bot(api, store, "KingdomOpsBot", profile=RESEARCH_BOT_PROFILE)

    identity = prepare_runtime(
        api,
        store,
        expected_username="KingdomOpsBot",
        required_profile=RESEARCH_BOT_PROFILE,
    )
    assert identity["id"] == 8001


@pytest.mark.parametrize("service", [
    "dev.kingdom.prediction-markets.telegram-bot-token",
    "dev.kingdom.prediction-markets.telegram-ops-bot-token",
])
def test_keychain_helpers_select_service_without_changing_research_defaults(monkeypatch, service):
    from types import SimpleNamespace
    from telegram_gateway import bootstrap
    calls = []
    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        if "find-generic-password" in argv:
            if "-w" in argv:
                return SimpleNamespace(returncode=0, stdout=b"credential-free-test-placeholder\n")
            return SimpleNamespace(returncode=44)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    monkeypatch.setattr(bootstrap.sys.stdin, "isatty", lambda: True)
    options = {} if service == bootstrap.KEYCHAIN_SERVICE else {"keychain_service": service}
    report = bootstrap.store_token_interactively("KingdomOpsBot", **options)
    assert report["keychain_service"] == service
    assert report["clipboard_cleared"] is True
    token = bootstrap.load_keychain_token("KingdomOpsBot", **options)
    assert token == "credential-free-test-placeholder"
    keychain_calls = [argv for argv, _ in calls if "-s" in argv]
    assert len(keychain_calls) == 3
    assert all(argv[argv.index("-s") + 1] == service for argv in keychain_calls)
    assert all(token not in argv for argv in keychain_calls)


def test_invalid_keychain_service_fails_before_subprocess(monkeypatch):
    from telegram_gateway import bootstrap
    def forbidden(*args, **kwargs):
        pytest.fail("invalid service reached Keychain")
    monkeypatch.setattr(bootstrap.subprocess, "run", forbidden)
    with pytest.raises(ValueError):
        bootstrap.load_keychain_token("KingdomOpsBot", keychain_service="unrelated-service")
    with pytest.raises(ValueError):
        bootstrap.store_token_interactively("KingdomOpsBot", keychain_service="unrelated-service")
