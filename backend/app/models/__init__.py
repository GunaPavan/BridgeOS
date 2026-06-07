"""SQLAlchemy ORM models for Bridge OS."""

from app.db import Base
from app.models.agent_message import AgentMessage, AgentMessageRole
from app.models.bridge import Bridge, BridgeMembership
from app.models.cohort_memory import CohortMemory, MemoryKind
from app.models.donor import Donor
from app.models.message import MessageDirection, MessageStatus, WhatsAppMessage
from app.models.response_event import DonorResponseEvent, ResponseEventKind
from app.models.geocode_cache import GeocodeCache
from app.models.schedule_log import ScheduleResolveLog
from app.models.scheduler import ScheduledJob, ScheduledJobRun
from app.models.reply_classification import ReplyClassification
from app.models.email_message import EmailMessage
from app.models.call_escalation import CallEscalation, EscalationStatus, EscalationChannel
from app.models.swap_request import SlotSwapRequest, SwapStatus
from app.models.enums import (
    BloodGroup,
    BridgeHealth,
    BridgeStatus,
    CaregiverRelation,
    ContactChannel,
    CooldownReason,
    DonorType,
    EmergencyEventStatus,
    Gender,
    InactiveReason,
    Language,
    MembershipRole,
    MembershipStatus,
    OutreachChannel,
    OutreachTier,
    OutreachWaveStatus,
    PingResponse,
    ReplyIntent,
    UrgencyTier,
)
from app.models.outreach import (
    EmergencyEvent,
    OutreachCooldown,
    OutreachPing,
    OutreachWave,
)
from app.models.patient import Patient
from app.models.types import GUID

__all__ = [
    "Base",
    "GUID",
    "BloodGroup",
    "Language",
    "BridgeStatus",
    "MembershipStatus",
    "MembershipRole",
    "BridgeHealth",
    "CaregiverRelation",
    "ContactChannel",
    "DonorType",
    "Gender",
    "InactiveReason",
    "Patient",
    "Donor",
    "Bridge",
    "BridgeMembership",
    "WhatsAppMessage",
    "MessageDirection",
    "MessageStatus",
    "AgentMessage",
    "AgentMessageRole",
    "CohortMemory",
    "MemoryKind",
    "DonorResponseEvent",
    "ResponseEventKind",
    "ScheduleResolveLog",
    "SlotSwapRequest",
    "SwapStatus",
    "GeocodeCache",
    "ScheduledJob",
    "ScheduledJobRun",
    "ReplyClassification",
    "ReplyIntent",
    "EmailMessage",
    "CallEscalation",
    "EscalationStatus",
    "EscalationChannel",
    # Alert Allocator
    "OutreachWave",
    "OutreachPing",
    "EmergencyEvent",
    "OutreachCooldown",
    "UrgencyTier",
    "OutreachTier",
    "OutreachWaveStatus",
    "OutreachChannel",
    "PingResponse",
    "EmergencyEventStatus",
    "CooldownReason",
]
