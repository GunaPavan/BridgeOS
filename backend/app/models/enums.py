"""Shared enum types for the domain.

These are stored as strings in the DB (cross-dialect compatible) and validated
at the Pydantic boundary.
"""

from enum import Enum


class BloodGroup(str, Enum):
    """ABO + Rh blood groups.

    BOMBAY is the hh phenotype — extremely rare (~1/10,000 in India) but
    important to model because hh recipients can ONLY receive from other hh
    donors, not from O-negative. The Blood Warriors dataset has 2 explicit
    Bombay rows, so we represent it as a first-class group.
    """

    O_POS = "O+"
    O_NEG = "O-"
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    BOMBAY = "Bombay"
    UNKNOWN = "unknown"  # for "Do not Know" rows — common in Guest pool


class ContactChannel(str, Enum):
    """Outbound contact channel preference.

    Default = WHATSAPP because it's the only channel where the donor reply
    actually comes back to us (Twilio webhook) and feeds the automation
    loop: classify intent → cooldown / re-fire / EMA update. Email
    (SES) is the bidirectional caregiver fallback.

    SMS via SNS direct-publish is **outbound only** — AWS does not provide
    a free path to inbound SMS in India (DLT registration takes weeks,
    short codes cost $300/mo). So SMS is reserved for one-way emergency
    notifications whose body asks the recipient to phone the coordinator
    back. NEVER use SMS as a donor's primary channel — they'll reply into
    the void.

    Practical decision rule:
      - WhatsApp opt-in confirmed   → WHATSAPP  (full loop)
      - Caregiver, no WhatsApp      → EMAIL     (full loop)
      - Donor has no WhatsApp       → SMS       (alert-only, one-way)
    """

    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"  # outbound-only; "call coordinator if you can help" body


class DonorType(str, Enum):
    """How the donor relates to the Blood Bridge program.

    Sourced from Blood Warriors' ``donor_type`` column:
        ONE_TIME — emergency / one-off donation, not on a recurring bridge
        REGULAR  — part of a Bridge cohort, donating on a transfusion cycle
        OTHER    — Guests, Volunteers, Patients (non-donors)
    """

    ONE_TIME = "one_time"
    REGULAR = "regular"
    OTHER = "other"


class InactiveReason(str, Enum):
    """Why a donor was labeled Inactive — drives differentiated intervention.

    Sourced from Blood Warriors' ``inactive_trigger_comment``:
        NOT_DONATED_1Y       — "Not donated in last 1 year" (361 donors)
                               Intervention: send reminder, conversion likely
        LIMITED_DESPITE_CALLS — "Very limited activity despite multiple calls"
                                (321 donors)
                                Intervention: stop calling, accept loss
    """

    NOT_DONATED_1Y = "not_donated_1y"
    LIMITED_DESPITE_CALLS = "limited_despite_calls"


class Gender(str, Enum):
    """Patient / donor gender — required for some clinical contexts (e.g.
    women of reproductive age need extended phenotype matching to avoid
    alloimmunization)."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class Language(str, Enum):
    """Preferred communication language."""

    ENGLISH = "en"
    HINDI = "hi"
    TELUGU = "te"
    TAMIL = "ta"
    MARATHI = "mr"
    BENGALI = "bn"
    KANNADA = "kn"
    GUJARATI = "gu"


class BridgeStatus(str, Enum):
    """Lifecycle status of a Blood Bridge."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class MembershipStatus(str, Enum):
    """Status of a donor's membership in a bridge.

    Lifecycle:
        PENDING   — coordinator invited the donor; WhatsApp consent message
                    has been sent; awaiting donor's YES / NO.
        ACTIVE    — donor is on the cohort (counted toward `active_donor_count`).
        PAUSED    — temporary leave (medical / travel); not counted as active.
        EXITED    — left the cohort permanently (resigned, swapped out).
        REJECTED  — donor explicitly declined the invite.

    Replacement model: when a PENDING membership has its `replaces_donor_id`
    set, the linked ACTIVE membership stays ACTIVE during the pending window
    (so the bridge is never briefly understaffed). On YES, the PENDING flips
    to ACTIVE and the replaced membership flips to EXITED — atomically.
    """

    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    EXITED = "exited"
    REJECTED = "rejected"


class MembershipRole(str, Enum):
    """Donor's role in a bridge."""

    PRIMARY = "primary"
    BACKUP = "backup"


class CaregiverRelation(str, Enum):
    """Patient's primary caregiver relationship (G5)."""

    MOTHER = "mother"
    FATHER = "father"
    GUARDIAN = "guardian"
    SELF = "self"
    SPOUSE = "spouse"
    SIBLING = "sibling"


class BridgeHealth(str, Enum):
    """Health classification of a bridge.

    Phase 1: stubbed from donor count.
    Phase 4: replaced by Cohort Stability Predictor (XGBoost).
    """

    STABLE = "stable"
    AT_RISK = "at_risk"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Alert Allocator enums (Phase A — outreach)
# ---------------------------------------------------------------------------


class UrgencyTier(str, Enum):
    """How time-sensitive a patient slot is, computed from
    ``gap = days_until_next_transfusion`` and ``cadence = transfusion_cadence_days``.

        CRITICAL  — gap ≤ 1d   (regardless of cadence)
        HIGH      — gap ≤ 3d AND gap / cadence ≤ 0.15
        MEDIUM    — gap ≤ 7d AND gap / cadence ≤ 0.35
        PLANNED   — anything further out (handled by rotation scheduler, not allocator)

    The ``gap / cadence`` ratio makes this normalised across the 9–58-day range
    of transfusion cadences in the real Blood Warriors dataset.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    PLANNED = "planned"


class OutreachTier(str, Enum):
    """Where in the escalation ladder this wave sits.

    The ladder is fully automated — there is no human-in-the-loop tier.
    Waves escalate by reaching for a wider donor pool, a softer template,
    and finally an external inventory lookup. Coordinators only intervene
    via the explicit EMERGENCY button.

        TIER_1          — smallest minimal-batch WhatsApp (target P_accept = 0.70–0.95)
        TIER_2          — expanded batch, includes recent decliners eligible to re-ask
        TIER_3          — full pool broadcast incl. ``inactive_limited_despite_calls``
                          cohort on a softer template
        TIER_4_EXTERNAL — eRaktKosh inventory + ICMR RDRI lookup; coordinator alerted
        EMERGENCY       — coordinator-triggered geo-radius broadcast, cooldowns waived
    """

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"
    TIER_4_EXTERNAL = "tier_4_external"
    EMERGENCY = "emergency"


class OutreachWaveStatus(str, Enum):
    """Lifecycle of a wave."""

    ACTIVE = "active"
    ACCEPTED = "accepted"     # one of the pings turned into a YES
    EXPIRED = "expired"       # window closed with no accept; allocator escalated
    CANCELLED = "cancelled"   # superseded (e.g. slot covered by another wave or manual override)


class OutreachChannel(str, Enum):
    """How a ping was delivered."""

    WHATSAPP = "whatsapp"
    PHONE = "phone"


class PingResponse(str, Enum):
    """Outcome of a single ping in a wave.

        PENDING    — sent, awaiting reply
        ACCEPTED   — donor said yes
        DECLINED   — donor said no
        NO_REPLY   — window closed without response
        CANCELLED  — silently closed (sibling ping accepted, or wave cancelled)
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    NO_REPLY = "no_reply"
    CANCELLED = "cancelled"


class EmergencyEventStatus(str, Enum):
    """Lifecycle of the coordinator-triggered emergency wave."""

    ACTIVE = "active"
    RESOLVED = "resolved"
    EXPIRED = "expired"


class ReplyIntent(str, Enum):
    """Smart-classified intent for an inbound WhatsApp message.

    The legacy YES/NO/STOP keyword parser only knew 3 outcomes. The Bedrock
    classifier interprets free-text replies into a richer space so the
    automation engine can do the right thing per message:

        ACCEPT              → existing accept flow
        DECLINE             → existing decline flow
        RESCHEDULE_REQUEST  → log preferred date, ask donor to confirm
        OUT_OF_TOWN         → 7-day cross-patient cooldown
        MEDICAL_DEFER       → 14-day cross-patient cooldown
        UNRELATED_QUESTION  → forward to Care Agent for an answer
        STOP                → opt out
        UNKNOWN             → fall through to the legacy YES/NO/STOP parser

    Confidence below the threshold (0.7) is treated as UNKNOWN even if the
    model returned a specific intent — better to fall back to keyword
    matching than dispatch a wrong side-effect.
    """

    ACCEPT = "accept"
    DECLINE = "decline"
    RESCHEDULE_REQUEST = "reschedule_request"
    OUT_OF_TOWN = "out_of_town"
    MEDICAL_DEFER = "medical_defer"
    UNRELATED_QUESTION = "unrelated_question"
    STOP = "stop"
    UNKNOWN = "unknown"


class CooldownReason(str, Enum):
    """Why a donor was placed on outreach cooldown for a (donor, patient) pair.

    The pair is denormalised on ``OutreachCooldown``; patient_id NULL means the
    cooldown applies to every patient (e.g. donor declined a generic recruit
    invite or asked to be paused).
    """

    DECLINED = "declined"               # explicit NO — 30d cooldown for the same patient
    NO_REPLY = "no_reply"               # silence — 7d cooldown across all patients
    RECENT_DONATION = "recent_donation" # 90d clinical deferral after a confirmed donation
    OPT_OUT_TEMPORARY = "opt_out_temporary"  # donor said "pause me for a while"
