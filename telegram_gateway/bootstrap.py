"""Safe, resumable bootstrap helpers for a KINGDOM Telegram bot.

The first classic bot is created by a human in Telegram's real BotFather
conversation.  This module deliberately does not automate chat clicks or read
Telegram Desktop state.  It prepares public inputs, stores the resulting token
without putting it in argv, and configures the bot through the documented Bot
API after its identity has been verified.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unicodedata
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .telegram_api import TelegramAPI, TelegramError


BOTFATHER_URL = "tg://resolve?domain=BotFather"
KEYCHAIN_SERVICE = "dev.kingdom.prediction-markets.telegram-bot-token"
OPS_KEYCHAIN_SERVICE = "dev.kingdom.prediction-markets.telegram-ops-bot-token"
TOKEN_ENVIRONMENT_VARIABLE = "KINGDOM_TELEGRAM_BOT_TOKEN"

DEFAULT_BOT_NAME = "KINGDOM Research"
DEFAULT_SHORT_DESCRIPTION = (
    "Evidence-labelled prediction-market research. Information only; "
    "no orders or guaranteed returns."
)
DEFAULT_DESCRIPTION = (
    "KINGDOM delivers evidence-labelled prediction-market research and "
    "paper-only forecasts. It does not place trades, hold funds, or promise "
    "returns. Use /privacy for data handling and /leave to stop alerts."
)

BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Open KINGDOM research"),
    ("brief", "Read the latest approved preview"),
    ("join", "Enable up to two alerts per rolling week"),
    ("personalize", "Enable a minimal preference profile"),
    ("topics", "View or choose research topics"),
    ("cadence", "View or choose alert cadence"),
    ("watchlist", "Show saved market references"),
    ("scorecard", "View paper forecast calibration"),
    ("settings", "Show access and alert status"),
    ("leave", "Stop new research alerts"),
    ("stop", "Stop new research alerts"),
    ("help", "Show available commands"),
    ("privacy", "Read the data summary"),
    ("delete_me", "Purge nonfinancial data and prevent research contact"),
)

OPS_BOT_NAME = "KINGDOM Ops"
OPS_BOT_SHORT_DESCRIPTION = (
    "Private, read-only AgentTool coordination observations. No agent control, publishing, payments, or trading."
)
OPS_BOT_DESCRIPTION = (
    "KINGDOM Ops shows sanitized local AgentTool coordination observations to one "
    "bound private operator. Foreground polling stages replies; explicit sends "
    "deliver one reviewed reply. It does not identify beings, run agents, edit "
    "files, publish, pay, or trade. Use /agent_privacy for the data boundary."
)
OPS_BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("agent_status", "Show sanitized coordination status"),
    ("agent_tasks", "List sanitized task state"),
    ("agent_task", "Show one opaque task reference"),
    ("agent_events", "Show recent sanitized events"),
    ("journal_verify", "Show the last recorded integrity check"),
    ("agent_privacy", "Read the Ops data boundary"),
    ("help", "Show read-only Ops commands"),
)


@dataclass(frozen=True)
class BotProfile:
    """Public Telegram profile data, not runtime or action authority."""

    code: str
    name: str
    short_description: str
    description: str
    commands: tuple[tuple[str, str], ...]


RESEARCH_BOT_PROFILE = BotProfile(
    code="research",
    name=DEFAULT_BOT_NAME,
    short_description=DEFAULT_SHORT_DESCRIPTION,
    description=DEFAULT_DESCRIPTION,
    commands=BOT_COMMANDS,
)
OPS_BOT_PROFILE = BotProfile(
    code="ops",
    name=OPS_BOT_NAME,
    short_description=OPS_BOT_SHORT_DESCRIPTION,
    description=OPS_BOT_DESCRIPTION,
    commands=OPS_BOT_COMMANDS,
)
BOT_PROFILES: Mapping[str, BotProfile] = {
    RESEARCH_BOT_PROFILE.code: RESEARCH_BOT_PROFILE,
    OPS_BOT_PROFILE.code: OPS_BOT_PROFILE,
}

PRIVATE_COMMAND_SCOPE: Mapping[str, str] = {"type": "all_private_chats"}
NON_PRIVATE_COMMAND_SCOPES: tuple[Mapping[str, str], ...] = (
    {"type": "default"},
    {"type": "all_group_chats"},
    {"type": "all_chat_administrators"},
)

_BOT_USERNAME = re.compile(r"[A-Za-z0-9_]{2,29}[Bb][Oo][Tt]\Z")
_KEYCHAIN_ACCOUNT = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_COMMAND = re.compile(r"[a-z0-9_]{1,32}\Z")
_SECURITY = Path("/usr/bin/security")
_OPEN = Path("/usr/bin/open")
_PBCOPY = Path("/usr/bin/pbcopy")


class TelegramProviderStore(Protocol):
    def bind_telegram_provider(
        self,
        bot_id: int,
        api_origin: str,
        *,
        allow_create: bool = True,
    ) -> None: ...


def validate_bot_username(value: object) -> str:
    """Validate a Telegram bot username without querying availability."""

    if isinstance(value, str):
        username = value[1:] if value.startswith("@") else value
    else:
        username = ""
    if not 5 <= len(username) <= 32 or not _BOT_USERNAME.fullmatch(username):
        raise ValueError(
            "bot username must be 5-32 ASCII letters, digits, or underscores, "
            "and end in bot"
        )
    return username


def validate_bot_name(value: object) -> str:
    return _bounded_public_text(value, 64, "bot name")


def validate_description(value: object) -> str:
    return _bounded_public_text(value, 512, "bot description")


def validate_short_description(value: object) -> str:
    return _bounded_public_text(value, 120, "bot short description")


def validate_privacy_url(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("privacy policy URL is required")
    if len(value) > 2_048 or any(ord(char) < 32 for char in value):
        raise ValueError("privacy policy URL is invalid")
    try:
        parsed = urllib.parse.urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise ValueError("privacy policy URL is invalid") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "privacy policy URL must be a public HTTPS URL without credentials, query, or fragment"
        )
    return value


def bot_profile(value: object) -> BotProfile:
    if not isinstance(value, str) or value not in BOT_PROFILES:
        raise ValueError("bot profile must be research or ops")
    return BOT_PROFILES[value]


def desired_commands(
    profile: BotProfile = RESEARCH_BOT_PROFILE,
) -> list[dict[str, str]]:
    commands = [
        {"command": command, "description": description}
        for command, description in profile.commands
    ]
    for item in commands:
        if not _COMMAND.fullmatch(item["command"]) or not 1 <= len(
            item["description"]
        ) <= 256:
            raise ValueError("configured Telegram bot command is invalid")
    return commands


def botfather_command_body(
    profile: BotProfile = RESEARCH_BOT_PROFILE,
) -> str:
    return "\n".join(
        f"{command} - {description}" for command, description in profile.commands
    )


def build_botfather_plan(
    bot_username: object,
    *,
    bot_name: object | None = None,
    privacy_url: object | None = None,
    profile: BotProfile = RESEARCH_BOT_PROFILE,
) -> dict[str, Any]:
    """Build a credential-free checklist; it does not contact Telegram."""

    username = validate_bot_username(bot_username)
    name = validate_bot_name(profile.name if bot_name is None else bot_name)
    policy_url = validate_privacy_url(privacy_url) if privacy_url is not None else None
    profile_flag = "" if profile.code == "research" else f" --profile {profile.code}"
    cli_prefix = "python3 -m telegram_gateway"
    ops_projection_prefix = (
        "python3 -m telegram_gateway --db telegram_gateway/var/ops-bot.db"
    )
    profile_setup_steps = (
        [
            f"Run: {cli_prefix} bot-doctor --bot-username {username}{profile_flag}",
            f"Then apply the public profile: {cli_prefix} bot-configure --bot-username {username}{profile_flag} --apply",
        ]
        if profile.code == "research"
        else [
            "Use a dedicated Ops token slot, never the Research token or environment credential.",
            f"Initialize the separate owner-only Ops database: {ops_projection_prefix} ops-init",
            "Preview ops-bind with --bot-username, --bot-id, --operator-user-id, --operator-private-chat-id and --source-binding; the numeric private-chat pair must match. Review, then repeat with --apply to verify the bot and bind locally.",
            "Use the same opaque workspace ID for --source-binding and ops-watch-once --workspace-id; never use a journal path as the source label.",
            f"Inspect: {ops_projection_prefix} bot-doctor --bot-username {username}{profile_flag} --source-binding SOURCE_LABEL",
            f"Apply the public profile: {ops_projection_prefix} bot-configure --bot-username {username}{profile_flag} --source-binding SOURCE_LABEL --apply",
        ]
    )
    final_steps = (
        [
            f"Create one verified, unpublished launch link: python3 -m telegram_gateway bot-campaign --bot-username {username}",
            f"Smoke-test commands without broadcasts: python3 -m telegram_gateway run --token-source keychain --bot-username {username} --once --control-only",
        ]
        if profile.code == "research"
        else [
            f"Inspect the local projection without AgentTool or Telegram calls: {ops_projection_prefix} ops-status",
            "After binding/configuring, manually send /start privately to the Ops bot; commands must be newer than binding/resume.",
            f"Stage one batch, without sending: {ops_projection_prefix} ops-poll-once --bot-username {username} --source-binding SOURCE_LABEL",
            "Preview one ops-send-once --reply-id REF, then --apply with that exact --payload-digest and --binding-revision. Never automatically retry unknown delivery.",
            "Use ops-pause for local withdrawal; ops-pause --resume previews safe resumption and --resume --apply starts a new cutoff without replaying old replies.",
        ]
    )
    return {
        "profile": profile.code,
        "bot_name": name,
        "bot_username_candidate": username,
        "username_availability": "BotFather must confirm",
        "botfather_url": "https://t.me/BotFather",
        "public_profile": {
            "short_description": profile.short_description,
            "description": profile.description,
            "commands": desired_commands(profile),
        },
        "manual_steps": [
            "In the verified @BotFather chat, send /newbot.",
            f"Submit the public name: {name}",
            f"Submit the username candidate: {username}",
            "Do not paste the returned token into chat, a shell command, or a file.",
            f"Store it from a terminal with: python3 -m telegram_gateway bot-token-store --bot-username {username}{profile_flag}",
            "In BotFather, use /setjoingroups and disable group joins.",
            "In BotFather, use /setprivacy and keep Group Privacy Mode enabled.",
            f"For this {profile.code} bot, leave inline, guest, business, Mini App, private-topic, join-request, Bot-to-Bot Communication, and Bot Management modes disabled.",
            (
                f"In BotFather's bot settings, register the custom policy: {policy_url}"
                if policy_url
                else "Before public launch, publish and register a custom privacy policy in BotFather."
            ),
            *profile_setup_steps,
            *final_steps,
        ],
        "privacy_policy_url": policy_url,
        "privacy_policy_status": (
            "provided_but_not_remotely_verified" if policy_url else "required_before_public_launch"
        ),
        "automation_boundary": (
            "This plan opens or copies public inputs only. A human must visibly confirm "
            "creation in BotFather; no token is read from Telegram Desktop."
        ),
    }


def open_botfather() -> None:
    result = subprocess.run(
        [str(_OPEN), BOTFATHER_URL],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise OSError("Telegram could not open the verified @BotFather chat")


def copy_botfather_value(
    choice: str,
    *,
    bot_username: object,
    bot_name: object | None = None,
    profile: BotProfile = RESEARCH_BOT_PROFILE,
) -> None:
    username = validate_bot_username(bot_username)
    name = validate_bot_name(profile.name if bot_name is None else bot_name)
    values = {
        "newbot": "/newbot",
        "name": name,
        "username": username,
        "commands": botfather_command_body(profile),
    }
    if choice not in values:
        raise ValueError("copy choice is invalid")
    result = subprocess.run(
        [str(_PBCOPY)],
        input=values[choice].encode("utf-8"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise OSError("the public BotFather value could not be copied")


def keychain_account(
    bot_username: object,
    account: object | None = None,
) -> str:
    validate_bot_username(bot_username)
    selected = (
        validate_bot_username(bot_username).lower() if account is None else account
    )
    if not isinstance(selected, str) or not _KEYCHAIN_ACCOUNT.fullmatch(selected):
        raise ValueError(
            "Keychain account must be 1-64 lowercase letters, digits, dots, underscores, or hyphens"
        )
    return selected


def _keychain_service(value: str) -> str:
    if value not in {KEYCHAIN_SERVICE, OPS_KEYCHAIN_SERVICE}:
        raise ValueError("Keychain service must be the dedicated Research or Ops service")
    return value


def store_token_interactively(
    bot_username: object,
    *,
    keychain_account_name: object | None = None,
    keychain_service: str = KEYCHAIN_SERVICE,
) -> dict[str, Any]:
    """Prompt through ``security`` so the token is never a process argument."""

    username = validate_bot_username(bot_username)
    account = keychain_account(username, keychain_account_name)
    service = _keychain_service(keychain_service)
    if not sys.stdin.isatty():
        raise ValueError(
            "bot-token-store requires an interactive terminal; never pipe or pass the token"
        )

    stored_result: dict[str, Any] | None = None
    clipboard_cleared = False
    try:
        existing = subprocess.run(
            [
                str(_SECURITY),
                "find-generic-password",
                "-a",
                account,
                "-s",
                service,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if existing.returncode == 0:
            raise ValueError(
                "a token already exists in this Keychain account; choose a new "
                "--keychain-account so a known-good credential is never overwritten"
            )

        command = [
            str(_SECURITY),
            "add-generic-password",
            "-a",
            account,
            "-s",
            service,
            "-D",
            "application password",
            "-l",
            f"KINGDOM Telegram bot token (@{username})",
            "-j",
            "Full-control Telegram Bot API credential; never export or log.",
        ]
        # With -w present and no following value, macOS security prompts on the
        # inherited terminal instead of placing the secret in argv.
        command.append("-w")
        stored = subprocess.run(command, check=False)
        if stored.returncode != 0:
            raise OSError("macOS Keychain did not store the Telegram bot token")
        stored_result = {
            "stored": True,
            "keychain_service": service,
            "keychain_account": account,
            "bot_username": username,
            "access_boundary": (
                "macOS Keychain at-rest protection and default security-tool ACL; "
                "not isolation from hostile processes in the same logged-in account"
            ),
        }
    finally:
        try:
            cleared = subprocess.run(
                [str(_PBCOPY)],
                input=b"",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            clipboard_cleared = cleared.returncode == 0
        except OSError:
            clipboard_cleared = False
    if stored_result is None:
        raise OSError("macOS Keychain did not confirm token storage")
    stored_result["clipboard_cleared"] = clipboard_cleared
    return stored_result


def load_keychain_token(
    bot_username: object,
    *,
    keychain_account_name: object | None = None,
    keychain_service: str = KEYCHAIN_SERVICE,
) -> str:
    """Load one token into memory without exposing provider output."""

    account = keychain_account(bot_username, keychain_account_name)
    service = _keychain_service(keychain_service)
    try:
        result = subprocess.run(
            [
                str(_SECURITY),
                "find-generic-password",
                "-a",
                account,
                "-s",
                service,
                "-w",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise OSError("the Telegram bot token could not be read from macOS Keychain") from None
    if result.returncode != 0:
        raise OSError(
            "no readable Telegram bot token exists for the requested Keychain account"
        )
    return validate_token_bytes(result.stdout)


def validate_token_bytes(value: object) -> str:
    """Apply transport-safety bounds; ``getMe`` remains the authority check."""

    if not isinstance(value, bytes) or not 1 <= len(value) <= 514:
        raise ValueError("stored Telegram bot token is invalid")
    raw = value.rstrip(b"\r\n")
    if (
        not 16 <= len(raw) <= 512
        or any(byte < 33 or byte > 126 for byte in raw)
        or any(marker in raw for marker in (b"/", b"?", b"#", b"%", b"\\"))
    ):
        raise ValueError("stored Telegram bot token is invalid")
    try:
        return raw.decode("ascii")
    except UnicodeError:
        raise ValueError("stored Telegram bot token is invalid") from None


def resolve_token(
    *,
    source: str,
    bot_username: object | None,
    keychain_account_name: object | None = None,
    environment: Mapping[str, str] | None = None,
) -> str:
    """Resolve exactly one explicitly selected credential source."""

    if source == "keychain":
        if bot_username is None:
            raise ValueError("--bot-username is required with --token-source keychain")
        return load_keychain_token(
            bot_username, keychain_account_name=keychain_account_name
        )
    if source != "environment":
        raise ValueError("token source must be keychain or environment")
    if keychain_account_name is not None:
        raise ValueError("--keychain-account is only valid with --token-source keychain")
    selected_environment = os.environ if environment is None else environment
    raw = selected_environment.get(TOKEN_ENVIRONMENT_VARIABLE, "")
    if not raw:
        raise ValueError(
            f"{TOKEN_ENVIRONMENT_VARIABLE} is required for the environment token source"
        )
    try:
        encoded = raw.encode("ascii")
    except UnicodeError:
        raise ValueError("environment Telegram bot token is invalid") from None
    return validate_token_bytes(encoded)


def build_managed_bot_link(
    manager_username: object,
    child_username: object,
    *,
    child_name: object = DEFAULT_BOT_NAME,
) -> str:
    """Build a user-confirmed Managed Bot creation link without using a token."""

    manager = validate_bot_username(manager_username)
    child = validate_bot_username(child_username)
    name = validate_bot_name(child_name)
    query = urllib.parse.urlencode({"name": name})
    return f"https://t.me/newbot/{manager}/{child}?{query}"


def verify_identity(
    api: TelegramAPI,
    expected_username: object,
) -> Mapping[str, Any]:
    expected = validate_bot_username(expected_username)
    identity = api.get_me()
    actual = str(identity["username"])
    if actual.casefold() != expected.casefold():
        raise ValueError("the credential belongs to a different Telegram bot username")
    return identity


def inspect_bot(
    api: TelegramAPI,
    expected_username: object,
    *,
    profile: BotProfile = RESEARCH_BOT_PROFILE,
) -> dict[str, Any]:
    """Read back only public identity/configuration and sanitized readiness."""

    expected = validate_bot_username(expected_username)
    identity = verify_identity(api, expected)
    webhook = api.get_webhook_info()
    private_commands = api.get_my_commands(scope=PRIVATE_COMMAND_SCOPE)
    broad_commands = {
        str(scope["type"]): api.get_my_commands(scope=scope)
        for scope in NON_PRIVATE_COMMAND_SCOPES
    }
    actual_name = api.get_my_name()
    actual_description = api.get_my_description()
    actual_short_description = api.get_my_short_description()
    menu_type = api.get_chat_menu_button_type()

    capabilities = {
        field: identity.get(field)
        for field in (
            "can_join_groups",
            "can_read_all_group_messages",
            "supports_guest_queries",
            "supports_inline_queries",
            "can_connect_to_business",
            "has_main_web_app",
            "has_topics_enabled",
            "allows_users_to_create_topics",
            "can_manage_bots",
            "supports_join_request_queries",
        )
    }
    checks = {
        "identity_matches": True,
        "group_joins_disabled": identity.get("can_join_groups") is False,
        "group_privacy_enabled": identity.get("can_read_all_group_messages") is False,
        "guest_queries_disabled": identity.get("supports_guest_queries") is not True,
        "inline_mode_disabled": identity.get("supports_inline_queries") is not True,
        "business_connections_disabled": identity.get("can_connect_to_business")
        is not True,
        "main_web_app_disabled": identity.get("has_main_web_app") is not True,
        "private_topics_disabled": identity.get("has_topics_enabled") is not True,
        "user_topic_creation_disabled": identity.get("allows_users_to_create_topics")
        is not True,
        "manager_mode_disabled": identity.get("can_manage_bots") is not True,
        "join_request_queries_disabled": identity.get("supports_join_request_queries")
        is not True,
        "webhook_clear_for_long_polling": webhook["configured"] is False,
        "name_matches": actual_name == profile.name,
        "description_matches": actual_description == profile.description,
        "short_description_matches": actual_short_description
        == profile.short_description,
        "private_commands_match": private_commands == desired_commands(profile),
        "known_broad_command_scopes_clear": all(
            not commands for commands in broad_commands.values()
        ),
        "private_menu_uses_commands": menu_type == "commands",
    }
    runtime_ready = all(
        checks[key]
        for key in (
            "identity_matches",
            "group_joins_disabled",
            "group_privacy_enabled",
            "guest_queries_disabled",
            "inline_mode_disabled",
            "business_connections_disabled",
            "main_web_app_disabled",
            "private_topics_disabled",
            "user_topic_creation_disabled",
            "manager_mode_disabled",
            "join_request_queries_disabled",
            "webhook_clear_for_long_polling",
        )
    )
    bot_api_ready = runtime_ready and all(checks.values())
    return {
        "profile": profile.code,
        "identity": {
            "id": identity["id"],
            "username": identity["username"],
        },
        "capabilities": capabilities,
        "webhook": webhook,
        "checks": checks,
        "runtime_ready": runtime_ready,
        "bot_api_profile_ready": bot_api_ready,
        "public_launch_ready": False,
        "public_launch_blockers": [
            "confirm the published custom privacy policy in BotFather",
            "confirm this is a fresh bot with no unenumerable command/menu overrides",
        ],
        "privacy_policy_check": (
            "manual: Bot API cannot confirm BotFather's custom policy setting or publication"
        ),
        "profile_scope_limit": (
            "Bot API cannot enumerate old per-chat or language-specific command/menu overrides; "
            "bootstrap a fresh bot for this MVP"
        ),
        "webhook_action": "none; this workflow never deletes an existing webhook",
    }


def configure_bot(
    api: TelegramAPI,
    store: TelegramProviderStore,
    expected_username: object,
    *,
    profile: BotProfile = RESEARCH_BOT_PROFILE,
) -> dict[str, Any]:
    """Apply the fixed MVP profile after identity and authority checks."""

    identity = verify_identity(api, expected_username)
    webhook = api.get_webhook_info()
    if webhook["configured"] is not False:
        raise ValueError(
            "a Telegram webhook is configured; no settings were changed and no webhook was removed"
        )
    if identity.get("can_join_groups") is not False:
        raise ValueError(
            "group joins must be disabled in BotFather before automated configuration"
        )
    if identity.get("can_read_all_group_messages") is not False:
        raise ValueError(
            "Group Privacy Mode must be enabled in BotFather before automated configuration"
        )
    if any(
        identity.get(field) is True
        for field in (
            "supports_guest_queries",
            "supports_inline_queries",
            "can_connect_to_business",
            "has_main_web_app",
            "has_topics_enabled",
            "allows_users_to_create_topics",
            "can_manage_bots",
            "supports_join_request_queries",
        )
    ):
        raise ValueError(
            "non-MVP Telegram bot modes must be disabled in BotFather before configuration"
        )

    store.bind_telegram_provider(
        int(identity["id"]), api.provider_origin, allow_create=False
    )

    def apply_phase(label: str, operation: Callable[[], object]) -> None:
        try:
            operation()
        except TelegramError as exc:
            outcome = "outcome unknown" if exc.ambiguous else "rejected"
            raise ValueError(
                f"bot configuration stopped at {label} ({outcome}); earlier phases "
                "may have applied. Run bot-doctor to inspect the bot, then rerun "
                "bot-configure --apply; every phase is idempotent"
            ) from None

    apply_phase("set_name", lambda: api.set_my_name(profile.name))
    apply_phase(
        "set_description", lambda: api.set_my_description(profile.description)
    )
    apply_phase(
        "set_short_description",
        lambda: api.set_my_short_description(profile.short_description),
    )
    apply_phase(
        "set_private_commands",
        lambda: api.set_my_commands(desired_commands(profile), scope=PRIVATE_COMMAND_SCOPE),
    )
    for scope in NON_PRIVATE_COMMAND_SCOPES:
        scope_name = str(scope["type"])
        apply_phase(
            f"clear_{scope_name}_commands",
            lambda selected_scope=scope: api.delete_my_commands(
                scope=selected_scope
            ),
        )
    apply_phase("set_command_menu", api.set_chat_menu_commands)
    try:
        report = inspect_bot(api, expected_username, profile=profile)
    except (TelegramError, ValueError):
        raise ValueError(
            "bot configuration readback did not verify after mutation; settings may "
            "have applied. Run bot-doctor to inspect the bot, then rerun "
            "bot-configure --apply if needed"
        ) from None
    report["configuration_status"] = (
        "verified"
        if report["bot_api_profile_ready"] is True
        else "readback_mismatch"
    )
    if report["bot_api_profile_ready"] is not True:
        report["configuration_recovery"] = (
            "Run bot-doctor to inspect the bot, then rerun bot-configure --apply; "
            "every mutation phase is idempotent"
        )
    return report


def prepare_runtime(
    api: TelegramAPI,
    store: TelegramProviderStore,
    *,
    expected_username: object | None,
    required_profile: BotProfile | None = None,
) -> Mapping[str, Any]:
    """Fail closed before polling if the bot or delivery mode is unsafe."""

    profile_verified = required_profile is not None
    if required_profile is not None:
        if expected_username is None:
            raise ValueError("a profile-bound runtime requires the expected bot username")
        profile_report = inspect_bot(
            api,
            expected_username,
            profile=required_profile,
        )
        if profile_report["bot_api_profile_ready"] is not True:
            raise ValueError(
                f"runtime requires the verified {required_profile.code} bot profile; "
                "run bot-doctor and bot-configure for that profile"
            )
        identity = profile_report["identity"]
        webhook = profile_report["webhook"]
    else:
        identity = (
            verify_identity(api, expected_username)
            if expected_username is not None
            else api.get_me()
        )
        webhook = api.get_webhook_info()
    if not profile_verified:
        if identity.get("can_join_groups") is not False:
            raise ValueError("runtime requires group joins to be disabled in BotFather")
        if identity.get("can_read_all_group_messages") is not False:
            raise ValueError("runtime requires Group Privacy Mode to remain enabled")
        if any(
            identity.get(field) is True
            for field in (
                "supports_guest_queries",
                "supports_inline_queries",
                "can_connect_to_business",
                "has_main_web_app",
                "has_topics_enabled",
                "allows_users_to_create_topics",
                "can_manage_bots",
                "supports_join_request_queries",
            )
        ):
            raise ValueError("runtime refuses non-MVP Telegram bot capability modes")
        if webhook["configured"] is not False:
            raise ValueError(
                "long polling cannot start while a webhook is configured; no webhook was removed"
            )
    store.bind_telegram_provider(
        int(identity["id"]), api.provider_origin, allow_create=False
    )
    return identity


def _bounded_public_text(value: object, limit: int, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ValueError(f"{label} must contain 1-{limit} characters")
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
        raise ValueError(f"{label} contains invalid control characters")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError(f"{label} must be valid UTF-8") from None
    return value
