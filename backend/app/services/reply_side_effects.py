"""Side-effect dispatchers for classified inbound replies.

For each ``ReplyIntent`` we know how to act. The webhook hands off here
after the classifier produces an actionable result (intent != UNKNOWN AND
confidence >= ACTIONABLE_THRESHOLD).

Every dispatcher:
  - Carries out the DB mutation (acceptance, cooldown, ack-message)
  - Sends an outbound WhatsApp reply via twilio_client + WhatsAppMessage
  - Returns a SideEffectResult so the webhook + audit can render what
    happened in the run log

Dispatchers never call ``db.commit()`` — the caller (webhook handler)
owns transactional boundaries. We just stage rows + ping Twilio.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.models import (
    CooldownReason,
    Donor,
    MessageDirection,
    MessageStatus,
    OutreachCooldown,
    OutreachPing,
    OutreachWave,
    ReplyIntent,
    WhatsAppMessage,
)
from app.models.enums import PingResponse

logger = logging.getLogger(__name__)


# Cooldown windows
OUT_OF_TOWN_COOLDOWN_DAYS = 7
MEDICAL_DEFER_COOLDOWN_DAYS = 14
OPT_OUT_COOLDOWN_DAYS = 365  # effectively indefinite for stop


# ---------------------------------------------------------------------------
# Result envelope
# ---------------------------------------------------------------------------


@dataclass
class SideEffectResult:
    intent: ReplyIntent
    handled: bool
    actions: list[str] = field(default_factory=list)
    cooldown_until: Optional[datetime] = None
    outbound_reply_sid: Optional[str] = None

    def add_action(self, action: str) -> None:
        self.actions.append(action)


# ---------------------------------------------------------------------------
# Acknowledgement messages (English defaults — care agent could re-render
# multilingual later, but this is the polite "we got it" reply.)
# ---------------------------------------------------------------------------


_ACK_RESCHEDULE = (
    "Got it — we'll check whether we can move your slot and confirm shortly. "
    "Thank you for letting us know."
)
_ACK_OUT_OF_TOWN = (
    "Thanks for letting us know — we won't reach out for the next week. "
    "Safe travels!"
)
_ACK_MEDICAL = (
    "Wishing you a quick recovery 🙏 We'll pause requests for the next two weeks. "
    "Take care."
)
_ACK_STOP = (
    "You've been opted out. We won't message you about donations again. "
    "Reply START anytime to opt back in."
)
_ACK_UNKNOWN = (
    "Sorry — I didn't quite catch that. Please reply YES if you can donate, "
    "or NO if you can't."
)


# ---------------------------------------------------------------------------
# Send helper — used by all reply dispatchers
# ---------------------------------------------------------------------------


def _send_ack(db: Session, donor: Donor, body: str, *, intent_label: str) -> Optional[str]:
    """Send a polite acknowledgement back to the donor. Returns Twilio SID."""
    if not donor.phone:
        return None
    try:
        result = twilio_client.send_whatsapp(to_number=donor.phone, body=body)
    except Exception:  # pragma: no cover — defensive
        logger.exception("Twilio ack send failed for donor %s", donor.id)
        return None

    outbound_status = (
        MessageStatus(result.status)
        if result.status in {s.value for s in MessageStatus}
        else MessageStatus.QUEUED
    )
    db.add(
        WhatsAppMessage(
            donor_id=donor.id,
            direction=MessageDirection.OUTBOUND,
            from_number=twilio_client.whatsapp_from(),
            to_number=donor.phone,
            body=body,
            status=outbound_status,
            twilio_sid=result.sid,
            template_key=f"reply_ack_{intent_label}",
            language="en",
        )
    )
    return result.sid


def _set_cooldown(
    db: Session,
    *,
    donor_id: uuid.UUID,
    reason: CooldownReason,
    days: int,
    notes: str,
    now: datetime,
) -> datetime:
    expires = now + timedelta(days=days)
    db.add(
        OutreachCooldown(
            donor_id=donor_id,
            patient_id=None,  # cross-patient
            reason=reason,
            expires_at=expires,
            notes=notes,
        )
    )
    return expires


# ---------------------------------------------------------------------------
# Per-intent dispatchers
# ---------------------------------------------------------------------------


def on_accept(
    db: Session,
    *,
    donor: Donor,
    slot_ref: Optional[str],
    now: Optional[datetime] = None,
) -> SideEffectResult:
    """Existing acceptance flow — delegates to ``confirm_outreach_acceptance``."""
    from app.outreach.dispatch import confirm_outreach_acceptance

    res = SideEffectResult(intent=ReplyIntent.ACCEPT, handled=False)
    wave = confirm_outreach_acceptance(db, donor_id=donor.id, slot_ref=slot_ref, now=now)
    if wave is None:
        return res  # nothing to accept; webhook will fall through
    res.handled = True
    res.add_action(f"accepted_wave={wave.id}")
    return res


def on_decline(
    db: Session,
    *,
    donor: Donor,
    slot_ref: Optional[str],
    now: Optional[datetime] = None,
    reason: Optional[str] = None,
) -> SideEffectResult:
    """Existing decline flow — delegates to ``record_outreach_decline``."""
    from app.outreach.dispatch import record_outreach_decline

    res = SideEffectResult(intent=ReplyIntent.DECLINE, handled=False)
    ping = record_outreach_decline(
        db, donor_id=donor.id, slot_ref=slot_ref, now=now
    )
    if ping is None:
        return res
    res.handled = True
    res.add_action(f"declined_ping={ping.id}")
    if reason:
        res.add_action(f"reason={reason}")
    return res


def on_reschedule_request(
    db: Session,
    *,
    donor: Donor,
    slot_ref: Optional[str],
    preferred_date: Optional[date],
    now: Optional[datetime] = None,
) -> SideEffectResult:
    """Log the request, ack the donor, leave the wave alone.

    The wave stays ACTIVE — the allocator's next cycle will see the
    coordinator hint (via the audit row) and the coordinator can override
    if they want to move the slot. Per problem statement this is the
    "interpret responses to guide next steps" path — we don't auto-move
    transfusion dates from one donor message, but we DO act on the side
    effects (ack + log).
    """
    now = now or datetime.utcnow()
    res = SideEffectResult(intent=ReplyIntent.RESCHEDULE_REQUEST, handled=True)
    sid = _send_ack(db, donor, _ACK_RESCHEDULE, intent_label="reschedule")
    if sid:
        res.outbound_reply_sid = sid
        res.add_action("acked_reschedule")
    if preferred_date is not None:
        res.add_action(f"preferred_date={preferred_date.isoformat()}")
    return res


def on_out_of_town(
    db: Session,
    *,
    donor: Donor,
    now: Optional[datetime] = None,
) -> SideEffectResult:
    now = now or datetime.utcnow()
    res = SideEffectResult(intent=ReplyIntent.OUT_OF_TOWN, handled=True)
    expires = _set_cooldown(
        db,
        donor_id=donor.id,
        reason=CooldownReason.OPT_OUT_TEMPORARY,
        days=OUT_OF_TOWN_COOLDOWN_DAYS,
        notes="Donor reported out of town",
        now=now,
    )
    res.cooldown_until = expires
    res.add_action(f"cooldown_until={expires.date().isoformat()}")
    sid = _send_ack(db, donor, _ACK_OUT_OF_TOWN, intent_label="out_of_town")
    if sid:
        res.outbound_reply_sid = sid
    return res


def on_medical_defer(
    db: Session,
    *,
    donor: Donor,
    reason: Optional[str],
    now: Optional[datetime] = None,
) -> SideEffectResult:
    now = now or datetime.utcnow()
    res = SideEffectResult(intent=ReplyIntent.MEDICAL_DEFER, handled=True)
    expires = _set_cooldown(
        db,
        donor_id=donor.id,
        reason=CooldownReason.OPT_OUT_TEMPORARY,
        days=MEDICAL_DEFER_COOLDOWN_DAYS,
        notes=f"Medical defer: {reason or 'donor reported medical condition'}",
        now=now,
    )
    res.cooldown_until = expires
    res.add_action(f"cooldown_until={expires.date().isoformat()}")
    sid = _send_ack(db, donor, _ACK_MEDICAL, intent_label="medical")
    if sid:
        res.outbound_reply_sid = sid
    return res


def on_unrelated_question(
    db: Session,
    *,
    donor: Donor,
    text: str,
    now: Optional[datetime] = None,
) -> SideEffectResult:
    """Forward to Care Agent (if available) and send a "let me get that"
    holding reply. If the agent isn't configured we still ack so the donor
    isn't ghosted."""
    res = SideEffectResult(intent=ReplyIntent.UNRELATED_QUESTION, handled=True)

    answer: Optional[str] = None
    try:
        from app.agent.engine import answer_question  # type: ignore[attr-defined]

        answer = answer_question(text)
    except Exception:
        # Care Agent not wired or failed — log + ack with a holding message.
        answer = None

    body = answer if answer else (
        "Got your question — a coordinator will follow up shortly."
    )
    sid = _send_ack(db, donor, body, intent_label="agent_forward")
    if sid:
        res.outbound_reply_sid = sid
        res.add_action("forwarded_to_care_agent" if answer else "ack_holding_message")
    return res


def on_stop(
    db: Session,
    *,
    donor: Donor,
    now: Optional[datetime] = None,
) -> SideEffectResult:
    now = now or datetime.utcnow()
    res = SideEffectResult(intent=ReplyIntent.STOP, handled=True)
    expires = _set_cooldown(
        db,
        donor_id=donor.id,
        reason=CooldownReason.OPT_OUT_TEMPORARY,
        days=OPT_OUT_COOLDOWN_DAYS,
        notes="Donor opted out via STOP",
        now=now,
    )
    res.cooldown_until = expires
    res.add_action(f"opted_out_until={expires.date().isoformat()}")
    sid = _send_ack(db, donor, _ACK_STOP, intent_label="stop")
    if sid:
        res.outbound_reply_sid = sid
    return res


def on_unknown(
    db: Session,
    *,
    donor: Donor,
    now: Optional[datetime] = None,
) -> SideEffectResult:
    """No intent matched — send the gentle "please reply YES or NO" hint.

    This dispatcher is only reached when the webhook's legacy fallback ALSO
    couldn't classify the message. We don't set any cooldown — donor might
    just be typing slowly.
    """
    res = SideEffectResult(intent=ReplyIntent.UNKNOWN, handled=True)
    sid = _send_ack(db, donor, _ACK_UNKNOWN, intent_label="unknown")
    if sid:
        res.outbound_reply_sid = sid
        res.add_action("sent_help_hint")
    return res


# ---------------------------------------------------------------------------
# Dispatcher table — keyed by intent
# ---------------------------------------------------------------------------


def dispatch(
    db: Session,
    *,
    intent: ReplyIntent,
    donor: Donor,
    text: str,
    slot_ref: Optional[str] = None,
    preferred_date: Optional[date] = None,
    extracted_reason: Optional[str] = None,
    now: Optional[datetime] = None,
) -> SideEffectResult:
    """Route a classified intent to its handler. Webhook calls this once."""
    if intent == ReplyIntent.ACCEPT:
        return on_accept(db, donor=donor, slot_ref=slot_ref, now=now)
    if intent == ReplyIntent.DECLINE:
        return on_decline(
            db, donor=donor, slot_ref=slot_ref, now=now, reason=extracted_reason
        )
    if intent == ReplyIntent.RESCHEDULE_REQUEST:
        return on_reschedule_request(
            db, donor=donor, slot_ref=slot_ref,
            preferred_date=preferred_date, now=now,
        )
    if intent == ReplyIntent.OUT_OF_TOWN:
        return on_out_of_town(db, donor=donor, now=now)
    if intent == ReplyIntent.MEDICAL_DEFER:
        return on_medical_defer(db, donor=donor, reason=extracted_reason, now=now)
    if intent == ReplyIntent.UNRELATED_QUESTION:
        return on_unrelated_question(db, donor=donor, text=text, now=now)
    if intent == ReplyIntent.STOP:
        return on_stop(db, donor=donor, now=now)
    return on_unknown(db, donor=donor, now=now)
