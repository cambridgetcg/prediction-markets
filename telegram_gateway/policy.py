"""Fail-closed authority policy for Telegram-facing actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class Action(str, Enum):
    VIEW_PUBLIC_SIGNAL = "view_public_signal"
    VIEW_RESEARCH_SIGNAL = "view_research_signal"
    RECORD_PAPER_ACTION = "record_paper_action"
    PLACE_LIVE_ORDER = "place_live_order"


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str
    explanation: str


class PolicyEngine:
    """Separate capability, entitlement, consent, and execution checks.

    There is intentionally no configuration switch that enables live orders.
    A future executor must be a separately reviewed component rather than an
    environment variable that weakens this product's core boundary.
    """

    MAX_PAPER_USDC = 10_000.0

    def decide(
        self,
        action: Action,
        *,
        entitled: bool = False,
        explicit_user_request: bool = False,
        amount_usdc: float | None = None,
    ) -> PolicyDecision:
        if action is Action.PLACE_LIVE_ORDER:
            return PolicyDecision(
                False,
                "LIVE_EXECUTION_DISABLED",
                "This gateway has no wallet, signer, or authority to place live orders.",
            )
        if action is Action.VIEW_PUBLIC_SIGNAL:
            return PolicyDecision(True, "PUBLIC", "Public research preview is available.")
        if action is Action.VIEW_RESEARCH_SIGNAL:
            if not entitled:
                return PolicyDecision(
                    False,
                    "SUBSCRIPTION_REQUIRED",
                    "An active research subscription is required.",
                )
            return PolicyDecision(True, "ENTITLED", "Research entitlement is active.")
        if action is Action.RECORD_PAPER_ACTION:
            if not entitled:
                return PolicyDecision(
                    False,
                    "SUBSCRIPTION_REQUIRED",
                    "An active research subscription is required for paper tools.",
                )
            if not explicit_user_request:
                return PolicyDecision(
                    False,
                    "EXPLICIT_REQUEST_REQUIRED",
                    "A paper action requires a direct user command.",
                )
            if (
                amount_usdc is None
                or isinstance(amount_usdc, bool)
                or not isinstance(amount_usdc, (int, float))
                or not math.isfinite(float(amount_usdc))
                or amount_usdc <= 0
            ):
                return PolicyDecision(False, "INVALID_AMOUNT", "Paper amount must be positive.")
            if amount_usdc > self.MAX_PAPER_USDC:
                return PolicyDecision(
                    False,
                    "PAPER_LIMIT_EXCEEDED",
                    f"Paper amount cannot exceed ${self.MAX_PAPER_USDC:,.0f}.",
                )
            return PolicyDecision(
                True,
                "PAPER_ONLY",
                "A simulated paper action may be recorded; no external order will be sent.",
            )
        return PolicyDecision(False, "UNKNOWN_ACTION", "Unknown actions fail closed.")
