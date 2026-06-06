"""Pydantic request/response schemas."""

from app.schemas.analytics import AnalyticsResponse
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentMessageOut,
    AgentSessionSummary,
    AgentStatusOut,
    CohortMemoryOut,
    ContextSourceOut,
    RetrievedMemoryOut,
)
from app.schemas.whatsapp import (
    ConversationSummary,
    ConversationThread,
    ConversationsList,
    MessageTemplate,
    SendMessageRequest,
    SendMessageResponse,
    TwilioStatusInfo,
    WhatsAppMessageOut,
)
from app.schemas.bridge import (
    BridgeDetail,
    BridgeListItem,
    BridgesPage,
    MembershipDetail,
)
from app.schemas.common import Page
from app.schemas.donor import (
    DonorBridgeMembership,
    DonorDetail,
    DonorListItem,
    DonorSummary,
    DonorsPage,
)
from app.schemas.patient import (
    PatientBridgeRef,
    PatientDetail,
    PatientListItem,
    PatientProfile,
    PatientsPage,
)
from app.schemas.schedule import (
    BridgeScheduleResponse,
    DonorLoadOut,
    ScheduleSlotOut,
)
from app.schemas.recommendation import (
    BridgeRecommendationOut,
    CandidateOut,
    CandidateRationaleOut,
    RecommendationsInbox,
    RecruitRequest,
    RecruitResponse,
    WeakDonorOut,
)
from app.schemas.stability import (
    BridgeStability,
    BridgeStabilityAggregate,
    DonorStability,
    StabilityFactor,
)

__all__ = [
    "Page",
    "DonorSummary",
    "DonorListItem",
    "DonorDetail",
    "DonorBridgeMembership",
    "DonorsPage",
    "PatientDetail",
    "PatientListItem",
    "PatientProfile",
    "PatientBridgeRef",
    "PatientsPage",
    "BridgeListItem",
    "BridgeDetail",
    "BridgesPage",
    "MembershipDetail",
    "StabilityFactor",
    "DonorStability",
    "BridgeStabilityAggregate",
    "BridgeStability",
    "ScheduleSlotOut",
    "DonorLoadOut",
    "BridgeScheduleResponse",
    "CandidateRationaleOut",
    "CandidateOut",
    "WeakDonorOut",
    "BridgeRecommendationOut",
    "RecommendationsInbox",
    "RecruitRequest",
    "RecruitResponse",
    "AnalyticsResponse",
    "WhatsAppMessageOut",
    "ConversationSummary",
    "ConversationThread",
    "ConversationsList",
    "SendMessageRequest",
    "SendMessageResponse",
    "TwilioStatusInfo",
    "MessageTemplate",
    "AgentChatRequest",
    "AgentChatResponse",
    "AgentMessageOut",
    "AgentSessionSummary",
    "AgentStatusOut",
    "CohortMemoryOut",
    "ContextSourceOut",
    "RetrievedMemoryOut",
]
