"""WhatsApp messaging API.

Three concerns:
    1. List conversations + a single donor's thread (UI rendering)
    2. Send outbound (template or free-form) — routes through Twilio if configured
    3. Twilio inbound webhook — accepts the donor's reply, stores it, and
       returns a brief TwiML acknowledgement
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.integrations import twilio_client
from app.models import (
    Bridge,
    BridgeMembership,
    Donor,
    MembershipStatus,
    MessageDirection,
    MessageStatus,
    Patient,
    WhatsAppMessage,
)
from app.schemas.whatsapp import (
    CaregiverConversationThread,
    CaregiverRef,
    ConversationSummary,
    ConversationThread,
    ConversationsList,
    DonorSummaryRef,
    MessageTemplate,
    SendMessageRequest,
    SendMessageResponse,
    TwilioStatusInfo,
    WhatsAppMessageOut,
)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


# ----- Templates (G4: multilingual) -----

# The template store lives in app.services.whatsapp_templates and holds all
# 4 templates × 8 languages = 32 hand-authored strings. /whatsapp/templates
# exposes the metadata; /whatsapp/send picks the donor's preferred_language
# unless overridden, then renders via the service.

from app.services import whatsapp_templates as _tmpl


def _api_template(t: _tmpl.TemplateDef) -> MessageTemplate:
    return MessageTemplate(
        key=t.key,
        label=t.label,
        requires_bridge=t.requires_bridge,
        bodies=dict(t.bodies),
        supported_languages=_tmpl.supported_languages(t),
    )


def _template_or_400(key: str) -> _tmpl.TemplateDef:
    t = _tmpl.get_template(key)
    if t is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown template_key '{key}'",
        )
    return t


# ----- Status + templates endpoints -----


@router.get("/status", response_model=TwilioStatusInfo, summary="Twilio configuration status")
def get_twilio_status() -> TwilioStatusInfo:
    return TwilioStatusInfo(
        is_live=twilio_client.is_live(),
        from_number=twilio_client.whatsapp_from(),
        sandbox_join_instructions=(
            "To opt in to the Twilio WhatsApp Sandbox: open WhatsApp, send "
            "'join <your-sandbox-keyword>' to "
            f"{twilio_client.whatsapp_from().replace('whatsapp:', '')}, "
            "then this number can message you."
        ),
    )


@router.get(
    "/templates",
    response_model=list[MessageTemplate],
    summary="Predefined outbound message templates (G4: with per-language bodies)",
)
def list_templates() -> list[MessageTemplate]:
    return [_api_template(t) for t in _tmpl.all_templates()]


# ----- Conversations -----


@router.get(
    "/conversations",
    response_model=ConversationsList,
    summary="One row per donor or caregiver with at least one message (G5)",
)
def list_conversations(
    db: Session = Depends(get_db),
) -> ConversationsList:
    conversations: list[ConversationSummary] = []

    # ----- Donor conversations -----
    donor_subq = (
        select(
            WhatsAppMessage.donor_id,
            func.max(WhatsAppMessage.created_at).label("last_at"),
            func.count(WhatsAppMessage.id).label("msg_count"),
        )
        .where(WhatsAppMessage.donor_id.is_not(None))
        .group_by(WhatsAppMessage.donor_id)
        .order_by(desc("last_at"))
        .subquery()
    )
    for donor, last_at, count in db.execute(
        select(Donor, donor_subq.c.last_at, donor_subq.c.msg_count)
        .join(donor_subq, Donor.id == donor_subq.c.donor_id)
        .order_by(desc(donor_subq.c.last_at))
    ).all():
        last_msg = db.execute(
            select(WhatsAppMessage)
            .where(WhatsAppMessage.donor_id == donor.id)
            .order_by(desc(WhatsAppMessage.created_at))
            .limit(1)
        ).scalar_one()
        conversations.append(
            ConversationSummary(
                kind="donor",
                donor=DonorSummaryRef.model_validate(donor),
                caregiver=None,
                last_message=WhatsAppMessageOut.model_validate(last_msg),
                message_count=int(count),
            )
        )

    # ----- G5: Caregiver conversations (donor_id IS NULL + patient_id set) -----
    caregiver_subq = (
        select(
            WhatsAppMessage.patient_id,
            func.max(WhatsAppMessage.created_at).label("last_at"),
            func.count(WhatsAppMessage.id).label("msg_count"),
        )
        .where(
            WhatsAppMessage.donor_id.is_(None),
            WhatsAppMessage.patient_id.is_not(None),
        )
        .group_by(WhatsAppMessage.patient_id)
        .order_by(desc("last_at"))
        .subquery()
    )
    for patient, last_at, count in db.execute(
        select(Patient, caregiver_subq.c.last_at, caregiver_subq.c.msg_count)
        .join(caregiver_subq, Patient.id == caregiver_subq.c.patient_id)
        .order_by(desc(caregiver_subq.c.last_at))
    ).all():
        if not patient.caregiver_name or not patient.caregiver_phone:
            continue
        last_msg = db.execute(
            select(WhatsAppMessage)
            .where(
                WhatsAppMessage.donor_id.is_(None),
                WhatsAppMessage.patient_id == patient.id,
            )
            .order_by(desc(WhatsAppMessage.created_at))
            .limit(1)
        ).scalar_one()
        conversations.append(
            ConversationSummary(
                kind="caregiver",
                donor=None,
                caregiver=CaregiverRef(
                    patient_id=patient.id,
                    patient_name=patient.name,
                    patient_blood_group=patient.blood_group,
                    caregiver_name=patient.caregiver_name,
                    caregiver_relation=(
                        getattr(patient.caregiver_relation, "value", patient.caregiver_relation)
                        if patient.caregiver_relation is not None
                        else None
                    ),
                    caregiver_phone=patient.caregiver_phone,
                ),
                last_message=WhatsAppMessageOut.model_validate(last_msg),
                message_count=int(count),
            )
        )

    # Final sort by most recent across both kinds
    conversations.sort(
        key=lambda c: c.last_message.created_at, reverse=True
    )
    return ConversationsList(conversations=conversations, total=len(conversations))


@router.get(
    "/conversations/caregiver/{patient_id}",
    response_model=CaregiverConversationThread,
    summary="G5: full thread of caregiver messages tied to one patient",
)
def get_caregiver_thread(
    patient_id: uuid.UUID, db: Session = Depends(get_db)
) -> CaregiverConversationThread:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient {patient_id} not found",
        )
    if not patient.caregiver_name or not patient.caregiver_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Patient {patient.name} has no caregiver configured",
        )
    messages = (
        db.execute(
            select(WhatsAppMessage)
            .where(
                WhatsAppMessage.donor_id.is_(None),
                WhatsAppMessage.patient_id == patient_id,
            )
            .order_by(WhatsAppMessage.created_at)
        )
        .scalars()
        .all()
    )
    return CaregiverConversationThread(
        caregiver=CaregiverRef(
            patient_id=patient.id,
            patient_name=patient.name,
            patient_blood_group=patient.blood_group,
            caregiver_name=patient.caregiver_name,
            caregiver_relation=(
                getattr(patient.caregiver_relation, "value", patient.caregiver_relation)
                if patient.caregiver_relation is not None
                else None
            ),
            caregiver_phone=patient.caregiver_phone,
        ),
        messages=[WhatsAppMessageOut.model_validate(m) for m in messages],
    )


@router.get(
    "/conversations/{donor_id}",
    response_model=ConversationThread,
    summary="Full message thread for one donor",
)
def get_thread(donor_id: uuid.UUID, db: Session = Depends(get_db)) -> ConversationThread:
    donor = db.get(Donor, donor_id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Donor {donor_id} not found",
        )
    messages = (
        db.execute(
            select(WhatsAppMessage)
            .where(WhatsAppMessage.donor_id == donor_id)
            .order_by(WhatsAppMessage.created_at)
        )
        .scalars()
        .all()
    )
    return ConversationThread(
        donor=DonorSummaryRef.model_validate(donor),
        messages=[WhatsAppMessageOut.model_validate(m) for m in messages],
    )


@router.get(
    "/messages",
    response_model=list[WhatsAppMessageOut],
    summary="Recent messages across all donors",
)
def list_messages(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[WhatsAppMessageOut]:
    msgs = (
        db.execute(
            select(WhatsAppMessage)
            .order_by(desc(WhatsAppMessage.created_at))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [WhatsAppMessageOut.model_validate(m) for m in msgs]


# ----- Send -----


@router.post(
    "/send",
    response_model=SendMessageResponse,
    summary="Send a WhatsApp message (via Twilio if configured, mock otherwise)",
)
def send_message(
    payload: SendMessageRequest = Body(...),
    db: Session = Depends(get_db),
) -> SendMessageResponse:
    donor = db.get(Donor, payload.donor_id)
    if donor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Donor {payload.donor_id} not found",
        )

    # Resolve language: explicit override > donor's preferred_language > "en"
    chosen_lang = (
        payload.language
        or getattr(donor.preferred_language, "value", str(donor.preferred_language))
        or "en"
    )

    # Resolve body — template > free-form
    body_text: str
    template_key: Optional[str] = None
    language_used: Optional[str] = None
    fallback_used = False
    if payload.template_key:
        template = _template_or_400(payload.template_key)
        patient: Optional[Patient] = None
        if template.requires_bridge:
            if payload.bridge_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Template '{template.key}' requires bridge_id",
                )
            from app.models import Bridge

            bridge = db.get(Bridge, payload.bridge_id)
            if bridge is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Bridge {payload.bridge_id} not found",
                )
            patient = bridge.patient
        donor_first = donor.name.split()[0] if donor.name else "there"
        rendered = _tmpl.render(
            template.key,
            language=chosen_lang,
            donor_first=donor_first,
            donor_name=donor.name,
            patient_name=patient.name if patient else "",
            patient_age=patient.age if patient else 0,
            patient_blood_group=(
                getattr(patient.blood_group, "value", str(patient.blood_group))
                if patient
                else ""
            ),
        )
        body_text = rendered.body
        template_key = template.key
        language_used = rendered.language_used
        fallback_used = rendered.was_fallback
    elif payload.body:
        body_text = payload.body
        # Free-form: persist the requested language verbatim (no fallback path)
        language_used = chosen_lang if payload.language else None
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either body or template_key",
        )

    # Send via Twilio (or mock)
    result = twilio_client.send_whatsapp(to_number=donor.phone, body=body_text)

    msg = WhatsAppMessage(
        donor_id=donor.id,
        bridge_id=payload.bridge_id,
        direction=MessageDirection.OUTBOUND,
        from_number=twilio_client.whatsapp_from(),
        to_number=donor.phone,
        body=body_text,
        status=MessageStatus(result.status) if result.status in {s.value for s in MessageStatus} else MessageStatus.QUEUED,
        twilio_sid=result.sid,
        template_key=template_key,
        language=language_used,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return SendMessageResponse(
        message=WhatsAppMessageOut.model_validate(msg),
        is_live_twilio=not result.is_mock,
        language_used=language_used,  # type: ignore[arg-type]
        fallback_used=fallback_used,
    )


# ----- Twilio inbound webhook -----


@router.post(
    "/webhook",
    response_class=PlainTextResponse,
    summary="Twilio inbound webhook — parses YES/NO, flips PENDING memberships, ACKs",
)
async def twilio_webhook(
    request: Request,
    db: Session = Depends(get_db),
    From: str = Form(default=""),
    To: str = Form(default=""),
    Body: str = Form(default=""),
    MessageSid: str = Form(default=""),
) -> PlainTextResponse:
    """Twilio posts form-encoded data here when an opted-in donor sends a WhatsApp.

    G1 behaviour:
        - Store the inbound row tied to the donor (by phone match).
        - If the donor has a PENDING BridgeMembership, classify the reply:
            ACCEPT  -> flip PENDING->ACTIVE; if `replaces_donor_id` is set, flip
                       that membership ACTIVE->EXITED. Bridge cohort updates
                       atomically. Reply in donor's invite language.
            DECLINE -> flip PENDING->REJECTED. Replaced donor stays ACTIVE.
            OTHER   -> leave the PENDING alone. Reply with a hint to send YES/NO.
        - If there's no PENDING, fall through to a generic ack.
    """
    sender_phone = From.replace("whatsapp:", "").strip()
    donor = None
    if sender_phone:
        donor = (
            db.execute(select(Donor).where(Donor.phone == sender_phone))
            .scalars()
            .first()
        )

    inbound = WhatsAppMessage(
        donor_id=donor.id if donor else None,
        bridge_id=None,
        direction=MessageDirection.INBOUND,
        from_number=From or sender_phone,
        to_number=To or twilio_client.whatsapp_from(),
        body=Body,
        status=MessageStatus.RECEIVED,
        twilio_sid=MessageSid or None,
    )
    db.add(inbound)

    reply_text: str
    if donor is None:
        reply_text = (
            "Thanks for your message — we couldn't find your number in our donor "
            "registry. A coordinator will reach out."
        )
    else:
        reply_text = _process_donor_reply(db, donor=donor, body=Body, inbound=inbound)

    db.commit()

    twiml = (
        f"<?xml version='1.0' encoding='UTF-8'?>"
        f"<Response><Message>{reply_text}</Message></Response>"
    )
    return PlainTextResponse(content=twiml, media_type="application/xml")


def _process_donor_reply(
    db: Session, *, donor: Donor, body: str, inbound: WhatsAppMessage
) -> str:
    """Classify intent, mutate any PENDING memberships, return the reply text."""
    from app.agent.templates import render_ack
    from app.services.response_feedback import apply_inbound_reply
    from app.utils.intent import Intent, classify

    # ---- Phase C: smart reply classification (Bedrock + side effects) ----
    # Run the classifier on every inbound. If it's confident enough, dispatch
    # the matching side-effect (cooldown / ack / forward to Care Agent).
    # When the classifier returns ACCEPT or DECLINE we still flow through the
    # legacy path so the slot_ref → outreach routing keeps working — the
    # classifier just gives us better diagnostics.
    classified_reply_message = _try_smart_classify(db, donor=donor, body=body, inbound=inbound)
    if classified_reply_message is not None:
        return classified_reply_message

    intent = classify(body)
    donor_first = donor.name.split()[0] if donor.name else "there"

    # G2: every inbound nudges the donor's rolling response_rate / avg_hours
    # upward. Happens regardless of intent — the donor *did* respond.
    # We need the inbound to have a created_at, which db.add hasn't given it yet,
    # so populate explicitly.
    from datetime import datetime as _dt
    if inbound.created_at is None:
        inbound.created_at = _dt.utcnow()
    apply_inbound_reply(db, donor=donor, inbound=inbound, commit=False)

    # Alert Allocator: route YES/NO to an outreach wave when the message
    # carries an explicit slot_ref token. We don't fallthrough to outreach
    # without the ref — that would conflict with the G1 PENDING-membership
    # flow which also accepts YES/NO. The ref is the unambiguous signal.
    from app.outreach.dispatch import (
        parse_slot_ref as _parse_slot_ref,
        confirm_outreach_acceptance as _outreach_accept,
        record_outreach_decline as _outreach_decline,
    )

    outreach_slot_ref = _parse_slot_ref(body)
    if outreach_slot_ref is not None and intent == Intent.ACCEPT:
        wave = _outreach_accept(db, donor_id=donor.id, slot_ref=outreach_slot_ref)
        if wave is not None:
            return (
                f"Thanks {donor_first} — confirmed for the next transfusion. "
                "Our coordinator will share the exact time + hospital details "
                "closer to the date. (ref " + outreach_slot_ref + ")"
            )
    if outreach_slot_ref is not None and intent == Intent.DECLINE:
        ping = _outreach_decline(db, donor_id=donor.id, slot_ref=outreach_slot_ref)
        if ping is not None:
            return (
                f"Got it {donor_first}, thanks for replying — we'll find another "
                "donor for this slot. You'll stay on the bridge for future cycles. "
                "(ref " + outreach_slot_ref + ")"
            )

    # G6: route YES/NO to a swap proposal FIRST (if the donor has one).
    # Falls through if there's no pending swap and no pending membership.
    from app.services import swap_engine as _swap
    from app.utils.swap_parser import parse_swap as _parse_swap

    pending_swap = _swap.latest_pending_swap_for_target(db, donor.id)
    if pending_swap is not None and intent == Intent.ACCEPT:
        out = _swap.accept_swap(db, swap=pending_swap)
        return out.reply_body
    if pending_swap is not None and intent == Intent.DECLINE:
        out = _swap.reject_swap(db, swap=pending_swap)
        return out.reply_body

    # G6: detect swap-initiation from donor A ("swap with X on date").
    parsed = _parse_swap(body)
    if parsed is not None:
        # Find an active bridge the donor is on
        active_bridge_membership = (
            db.execute(
                select(BridgeMembership)
                .where(
                    BridgeMembership.donor_id == donor.id,
                    BridgeMembership.status == MembershipStatus.ACTIVE.value,
                )
                .order_by(BridgeMembership.joined_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if active_bridge_membership is not None:
            target_bridge = db.get(Bridge, active_bridge_membership.bridge_id)
            if target_bridge is not None:
                outcome = _swap.initiate_swap(
                    db,
                    from_donor=donor,
                    bridge=target_bridge,
                    name_fragment=parsed.name_fragment,
                    to_slot_date=parsed.date,
                )
                inbound.bridge_id = target_bridge.id
                return outcome.reply_body

    # Find the most recent PENDING membership for this donor (if any)
    pending = (
        db.execute(
            select(BridgeMembership)
            .where(
                BridgeMembership.donor_id == donor.id,
                BridgeMembership.status == MembershipStatus.PENDING.value,
            )
            .order_by(BridgeMembership.joined_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )

    # Language for the reply: use the invite's language if we have it,
    # else the donor's preferred language, else English.
    lang = (
        (pending.invite_language if pending else None)
        or getattr(donor.preferred_language, "value", str(donor.preferred_language))
        or "en"
    )

    if pending is None:
        # No pending action — used to fall through to a hardcoded "Thanks
        # X, coordinator will be in touch" template. Now Bedrock writes the
        # ack so judges see the LLM in the loop on every inbound (with a
        # safe template fallback baked into compose_inbound_reply itself).
        from app.services.demo_outreach import compose_inbound_reply

        donor_lang = (
            getattr(donor.preferred_language, "value", str(donor.preferred_language))
            or "en"
        )
        composed = compose_inbound_reply(
            donor_name=donor.name or "",
            patient_name="",
            intent=intent.name if hasattr(intent, "name") else str(intent),
            inbound_body=body,
            language=donor_lang,
        )
        logger.info(
            "inbound WA reply composed via %s/%s for donor=%s intent=%s",
            composed.source, composed.model, donor.id,
            intent.name if hasattr(intent, "name") else str(intent),
        )
        return composed.text

    bridge = db.get(Bridge, pending.bridge_id)
    patient_name = (
        bridge.patient.name if bridge and bridge.patient else "the patient"
    )
    inbound.bridge_id = pending.bridge_id

    if intent == Intent.ACCEPT:
        # G3: capture the schedule BEFORE we mutate the cohort so the resolve
        # log has accurate before/after deltas.
        from app.services.schedule_resolve import (
            auto_resolve_schedule,
            capture_baseline,
        )

        before_schedule = capture_baseline(bridge) if bridge is not None else None

        # Flip PENDING -> ACTIVE atomically with any replaced donor's EXIT.
        pending.status = MembershipStatus.ACTIVE
        if pending.replaces_donor_id is not None and bridge is not None:
            for m in bridge.memberships:
                if (
                    m.donor_id == pending.replaces_donor_id
                    and getattr(m.status, "value", str(m.status))
                    == MembershipStatus.ACTIVE.value
                ):
                    m.status = MembershipStatus.EXITED
                    break

        # Re-solve and log the change so /bridges/{id}/schedule-history can
        # tell the coordinator what just shifted.
        if bridge is not None:
            db.flush()  # let SQLAlchemy reflect the membership flips
            db.refresh(bridge)
            auto_resolve_schedule(
                db,
                bridge=bridge,
                triggered_by="webhook_yes",
                before=before_schedule,
                notes=f"Donor {donor.name} accepted invite",
            )

            # G5: notify the patient's caregiver that the cohort just changed.
            # No-ops if caregiver_phone is unset.
            from app.services.caregiver_notifications import send_caregiver_template
            if bridge.patient is not None:
                send_caregiver_template(
                    db,
                    patient=bridge.patient,
                    bridge=bridge,
                    template_key="recruit_success_caregiver",
                    added_donor_name=donor.name,
                    commit=False,
                )

        return render_ack("accept", lang, donor_first, patient_name)

    if intent == Intent.DECLINE:
        pending.status = MembershipStatus.REJECTED
        return render_ack("decline", lang, donor_first, patient_name)

    # OTHER — leave pending intact, ask for YES/NO.
    return render_ack("other", lang, donor_first, patient_name)


def _try_smart_classify(
    db: Session, *, donor: Donor, body: str, inbound: WhatsAppMessage
) -> Optional[str]:
    """Run the Bedrock-powered classifier on the inbound. If actionable,
    dispatch the side effect and return the reply text to send back.
    Otherwise return None so the caller can fall through to the legacy path.

    Persists a ``ReplyClassification`` audit row regardless of the outcome
    — that's how operators can see "the model thought this was OUT_OF_TOWN
    with 0.85 confidence" even when we end up not acting on it.
    """
    from datetime import datetime as _dt

    from app.models import ReplyClassification, ReplyIntent
    from app.outreach.dispatch import parse_slot_ref as _parse_slot_ref
    from app.services.reply_classifier import (
        ACTIONABLE_THRESHOLD as _AT,
        classify_reply as _classify_reply,
    )
    from app.services import reply_side_effects as _side

    text = (body or "").strip()
    if not text:
        return None

    language = getattr(donor.preferred_language, "value", str(donor.preferred_language))
    classified = _classify_reply(text, language=language or "en")

    # Audit log — always persist, even on UNKNOWN
    db.add(
        ReplyClassification(
            message_id=inbound.id if getattr(inbound, "id", None) else None,
            donor_id=donor.id,
            text_excerpt=text[:200],
            language=language,
            intent=classified.intent,
            confidence=classified.confidence,
            extracted_date=classified.extracted_date,
            extracted_reason=classified.extracted_reason,
            model_used=classified.model_used,
            raw_response=classified.raw_response,
            used_fallback=classified.used_fallback,
            classified_at=_dt.utcnow(),
        )
    )

    # Confidence gate
    if classified.intent == ReplyIntent.UNKNOWN or classified.confidence < _AT:
        return None  # fall through to legacy keyword path

    # Phase E4: publish the classified intent onto the event bus so audit
    # subscribers (cooldown, EMA) fan out. This is fire-and-forget — the
    # synchronous webhook response stays fast.
    try:
        from app.events import (
            publish_donor_reply_medical_defer,
            publish_donor_reply_opt_out,
            publish_donor_reply_out_of_town,
        )

        if classified.intent == ReplyIntent.OUT_OF_TOWN:
            publish_donor_reply_out_of_town(donor_id=donor.id)
        elif classified.intent == ReplyIntent.MEDICAL_DEFER:
            publish_donor_reply_medical_defer(
                donor_id=donor.id, reason=classified.extracted_reason
            )
        elif classified.intent == ReplyIntent.STOP:
            publish_donor_reply_opt_out(donor_id=donor.id)
    except Exception:
        # Event-bus publish failure must not break the webhook
        import logging as _log
        _log.getLogger(__name__).exception("SNS publish failed for donor %s", donor.id)

    # ACCEPT / DECLINE: keep delegating to the existing slot_ref → outreach
    # path so wave acceptance state stays consistent. We don't dispatch the
    # new on_accept/on_decline handlers here.
    if classified.intent in (ReplyIntent.ACCEPT, ReplyIntent.DECLINE):
        return None

    slot_ref = _parse_slot_ref(text)
    result = _side.dispatch(
        db,
        intent=classified.intent,
        donor=donor,
        text=text,
        slot_ref=slot_ref,
        preferred_date=classified.extracted_date,
        extracted_reason=classified.extracted_reason,
    )
    if not result.handled:
        return None

    # The side-effect handler already sent the acknowledgement via Twilio
    # (mirrored into WhatsAppMessage). We still echo a short status back in
    # the TwiML response so the donor sees confirmation in their chat.
    return _ACK_STATUS_MESSAGES.get(
        classified.intent.value, "Got it — a coordinator will follow up shortly."
    )


_ACK_STATUS_MESSAGES: dict[str, str] = {
    "reschedule_request": "Got it — we'll check whether we can move your slot and confirm shortly.",
    "out_of_town": "Thanks for letting us know — we won't reach out for the next week. Safe travels!",
    "medical_defer": "Wishing you a quick recovery 🙏 We'll pause requests for the next two weeks.",
    "unrelated_question": "Got your question — a coordinator will follow up shortly.",
    "stop": "You've been opted out. Reply START anytime to opt back in.",
}
