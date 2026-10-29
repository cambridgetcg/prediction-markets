"""KINGDOM Telegram research distribution gateway.

The gateway is deliberately information-only.  It can distribute research
signals and record simulated paper actions, but it has no wallet, signing, or
live-order capability.
"""

from .envelope import (
    EnvelopeError,
    build_s012_envelope,
    seal_envelope,
    validate_envelope,
    verify_envelope,
)
from .calibration import CalibrationError, CalibrationLedger
from .agenttool_mcp import AgentToolMcpConfig, AgentToolMcpError, AgentToolMcpReader
from .agenttool_ops import AgentToolOpsStore, CursorAnchor, DatabaseRoleError
from .channel_cards import (
    ChannelCardError,
    build_editorial_event,
    build_research_card,
    build_status_card,
    render_channel_card,
)
from .channel_publishing import (
    ChannelPublicationLedger,
    ChannelPublisher,
    ChannelPublisherConfig,
    prepare_channel_post,
)
from .lifecycle import (
    LifecycleEventError,
    LifecycleImportFailure,
    LifecycleImportResult,
    import_s012_lifecycle_jsonl,
    validate_lifecycle_event,
)
from .market_candidates import (
    CandidateInputError,
    build_candidate_report,
    candidate_report_json,
    dumps_candidate_report,
    score_gamma_candidates,
)
from .policy import Action, PolicyDecision, PolicyEngine
from .observations import (
    ObservationError,
    ObservationLedger,
    build_observation,
    validate_observation,
)
from .ops_service import OpsReply, OpsServiceConfig, TelegramOpsService
from .preferences import PreferenceSnapshot, PreferenceStore
from .promotion import (
    CAMPAIGN_KINDS,
    DEFAULT_PROMOTION_NOTICE_VERSION,
    build_campaign_link,
    generate_campaign_code,
    validate_campaign_code,
    validate_campaign_link,
)
from .reconciliation import (
    StarReconciliationError,
    StarReconciliationResult,
    StarScanIssue,
    StarTransactionObservation,
    StarTransactionValidationError,
    normalize_star_transaction,
    reconcile_star_transactions,
)
from .store import GatewayStore
from .webhook import TelegramWebhookIngress, WebhookResponse

__all__ = [
    "Action",
    "AgentToolMcpConfig",
    "AgentToolMcpError",
    "AgentToolMcpReader",
    "AgentToolOpsStore",
    "CAMPAIGN_KINDS",
    "CandidateInputError",
    "CalibrationError",
    "CalibrationLedger",
    "ChannelCardError",
    "ChannelPublicationLedger",
    "ChannelPublisher",
    "ChannelPublisherConfig",
    "CursorAnchor",
    "DatabaseRoleError",
    "DEFAULT_PROMOTION_NOTICE_VERSION",
    "EnvelopeError",
    "GatewayStore",
    "LifecycleEventError",
    "LifecycleImportFailure",
    "LifecycleImportResult",
    "PolicyDecision",
    "PolicyEngine",
    "PreferenceSnapshot",
    "PreferenceStore",
    "ObservationError",
    "ObservationLedger",
    "OpsReply",
    "OpsServiceConfig",
    "StarReconciliationError",
    "StarReconciliationResult",
    "StarScanIssue",
    "StarTransactionObservation",
    "StarTransactionValidationError",
    "TelegramWebhookIngress",
    "TelegramOpsService",
    "WebhookResponse",
    "build_s012_envelope",
    "build_editorial_event",
    "build_observation",
    "build_research_card",
    "build_status_card",
    "build_candidate_report",
    "build_campaign_link",
    "candidate_report_json",
    "dumps_candidate_report",
    "import_s012_lifecycle_jsonl",
    "generate_campaign_code",
    "normalize_star_transaction",
    "reconcile_star_transactions",
    "render_channel_card",
    "score_gamma_candidates",
    "seal_envelope",
    "validate_envelope",
    "validate_observation",
    "validate_lifecycle_event",
    "validate_campaign_code",
    "validate_campaign_link",
    "verify_envelope",
    "prepare_channel_post",
]
