"""G6 — swap state machine service.

Three entry points consumed by the WhatsApp webhook:

    1. `initiate_swap()` — donor A inbound "swap with X on date". Fuzzy-matches
        the target donor by name within the same bridge, computes A's current
        slot, INSERTs a PROPOSED SlotSwapRequest, fires the
        `swap_request_inbound` template at B. Returns a `SwapInitiated` enum +
        rendered acknowledgement body for A.

    2. `accept_swap()` / `reject_swap()` — donor B inbound on a PROPOSED swap.
        Flips status, notifies both donors, and (on accept) triggers a
        schedule auto-resolve.

    3. `expire_stale_swaps()` — lazy sweep called on /swap-requests reads.
        Flips PROPOSED rows older than 48h to EXPIRED.

Note: the OR-Tools scheduler doesn't pin individual swaps in this v0. The
SlotSwapRequest row IS the source of truth for "what swap was agreed" — the
UI overlays it on the schedule. A future iteration can add hard-pin
constraints to the solver.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.integrations import twilio_client
from app.ml.scheduler import compute_schedule_for_bridge
from app.models import (
    Bridge,
    BridgeMembership,
    Donor,
    MembershipStatus,
    MessageDirection,
    MessageStatus,
    Patient,
    SlotSwapRequest,
    SwapStatus,
    WhatsAppMessage,
)
from app.services import whatsapp_templates as _tmpl


SWAP_EXPIRY = timedelta(hours=48)


class InitiateResult(str, Enum):
    PROPOSED = "proposed"
    NO_TARGET_FOUND = "no_target_found"
    AMBIGUOUS_TARGET = "ambiguous_target"
    TARGET_HAS_NO_SLOT = "target_has_no_slot"
    REQUESTER_HAS_NO_SLOT = "requester_has_no_slot"
    NOT_A_MEMBER = "not_a_member"


@dataclass
class InitiateOutcome:
    result: InitiateResult
    swap: Optional[SlotSwapRequest]
    reply_body: str
    reply_language: str


# ----- helpers -----


def _first_word(name: str) -> str:
    return name.split()[0] if name else ""


def _active_members(bridge: Bridge) -> list[BridgeMembership]:
    return [
        m for m in bridge.memberships
        if getattr(m.status, "value", str(m.status)) == MembershipStatus.ACTIVE.value
    ]


def _send_template_to(
    db: Session,
    *,
    donor: Donor,
    template_key: str,
    language: str,
    bridge: Optional[Bridge] = None,
    commit: bool = False,
    **vars,
) -> WhatsAppMessage:
    """Fire a template to a donor + persist the outbound row. Returns the row."""
    rendered = _tmpl.render(template_key, language=language, **vars)
    send_result = twilio_client.send_whatsapp(
        to_number=donor.phone, body=rendered.body
    )
    row = WhatsAppMessage(
        donor_id=donor.id,
        bridge_id=bridge.id if bridge else None,
        direction=MessageDirection.OUTBOUND,
        from_number=twilio_client.whatsapp_from(),
        to_number=donor.phone,
        body=rendered.body,
        status=(
            MessageStatus(send_result.status)
            if send_result.status in {s.value for s in MessageStatus}
            else MessageStatus.QUEUED
        ),
        twilio_sid=send_result.sid,
        template_key=template_key,
        language=rendered.language_used,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def _next_scheduled_date_for(
    db: Session, donor: Donor, bridge: Bridge, *, on_or_after: Optional[date] = None
) -> Optional[date]:
    """The donor's next assigned transfusion slot in this bridge.

    Reads the solver output via `compute_schedule_for_bridge` rather than
    persisting a per-donor schedule. For G6's needs this is fine — we run the
    solver once per inbound, picking the donor's first slot at-or-after
    `on_or_after` (defaults to today).
    """
    on_or_after = on_or_after or date.today()
    result = compute_schedule_for_bridge(
        bridge=bridge, today=date.today(), horizon_days=365, time_limit_seconds=2.0
    )
    for slot in result.slots:
        if slot.donor_id == donor.id and slot.transfusion_date >= on_or_after:
            return slot.transfusion_date
    return None


def _fuzzy_match_member(
    bridge: Bridge, name_fragment: str
) -> tuple[list[Donor], list[str]]:
    """Return (matching_donors, all_member_names) for the given fragment.

    Match strategy: case-insensitive substring on the donor's full name.
    """
    members = [m.donor for m in _active_members(bridge)]
    frag = name_fragment.lower().strip()
    if not frag:
        return [], [d.name for d in members]
    matches = [d for d in members if frag in (d.name or "").lower()]
    return matches, [d.name for d in members]


# ----- 1. initiate_swap -----


def initiate_swap(
    db: Session,
    *,
    from_donor: Donor,
    bridge: Bridge,
    name_fragment: str,
    to_slot_date: date,
    commit: bool = False,
) -> InitiateOutcome:
    """Donor A asked to swap. Returns InitiateOutcome describing what happened.

    On PROPOSED, also fires the swap_request_inbound template to donor B.
    """
    patient: Patient = bridge.patient
    patient_bg = getattr(patient.blood_group, "value", str(patient.blood_group))
    a_lang = (
        getattr(from_donor.preferred_language, "value", str(from_donor.preferred_language))
        or "en"
    )

    # A must be an active member of this bridge
    member_ids = {m.donor_id for m in _active_members(bridge)}
    if from_donor.id not in member_ids:
        return InitiateOutcome(
            result=InitiateResult.NOT_A_MEMBER,
            swap=None,
            reply_body=(
                f"Hi {_first_word(from_donor.name)}, you're not an active member "
                f"of {patient.name}'s bridge — we can't swap a slot you don't have."
            ),
            reply_language="en",
        )

    matches, all_names = _fuzzy_match_member(bridge, name_fragment)

    if len(matches) == 0:
        rendered = _tmpl.render(
            "swap_unknown_donor",
            language=a_lang,
            from_donor_first=_first_word(from_donor.name),
            patient_name=patient.name,
            requested_name=name_fragment,
        )
        return InitiateOutcome(
            result=InitiateResult.NO_TARGET_FOUND,
            swap=None,
            reply_body=rendered.body,
            reply_language=rendered.language_used,
        )

    if len(matches) > 1:
        rendered = _tmpl.render(
            "swap_ambiguous",
            language=a_lang,
            from_donor_first=_first_word(from_donor.name),
            patient_name=patient.name,
            requested_name=name_fragment,
            ambiguous_options=", ".join(d.name for d in matches[:5]),
        )
        return InitiateOutcome(
            result=InitiateResult.AMBIGUOUS_TARGET,
            swap=None,
            reply_body=rendered.body,
            reply_language=rendered.language_used,
        )

    to_donor: Donor = matches[0]

    if to_donor.id == from_donor.id:
        return InitiateOutcome(
            result=InitiateResult.AMBIGUOUS_TARGET,
            swap=None,
            reply_body=(
                f"Hi {_first_word(from_donor.name)}, you can't swap with yourself. "
                "Reply: swap with <full name> on <date>."
            ),
            reply_language="en",
        )

    # Find A's next slot. If the OR-Tools solver hasn't (or can't) assign
    # one (e.g. INFEASIBLE because half the cohort is mid-deferral), fall
    # back to "one transfusion cadence before the target date" — close enough
    # for swap-machine semantics; the schedule re-solves on accept.
    from_slot = _next_scheduled_date_for(db, from_donor, bridge)
    if from_slot is None:
        cadence = patient.transfusion_cadence_days or 18
        from_slot = to_slot_date - timedelta(days=cadence)
        if from_slot < date.today():
            from_slot = date.today() + timedelta(days=max(1, cadence // 2))

    # --- Create PROPOSED row ---
    now = datetime.utcnow()
    swap = SlotSwapRequest(
        bridge_id=bridge.id,
        from_donor_id=from_donor.id,
        to_donor_id=to_donor.id,
        from_slot_date=from_slot,
        to_slot_date=to_slot_date,
        status=SwapStatus.PROPOSED,
        expires_at=now + SWAP_EXPIRY,
        created_at=now,
    )
    db.add(swap)
    db.flush()

    # --- Notify B ---
    b_lang = (
        getattr(to_donor.preferred_language, "value", str(to_donor.preferred_language))
        or "en"
    )
    notify_row = _send_template_to(
        db,
        donor=to_donor,
        template_key="swap_request_inbound",
        language=b_lang,
        bridge=bridge,
        from_donor_first=_first_word(from_donor.name),
        from_donor_name=from_donor.name,
        to_donor_first=_first_word(to_donor.name),
        to_donor_name=to_donor.name,
        patient_name=patient.name,
        patient_age=patient.age,
        patient_blood_group=patient_bg,
        from_slot_date=from_slot.isoformat(),
        to_slot_date=to_slot_date.isoformat(),
    )
    swap.notify_message_sid = notify_row.twilio_sid

    # Ack to A in their language
    ack = (
        f"Sent your swap request to {to_donor.name}. "
        f"They'll get back to you within 48 hours."
    )

    if commit:
        db.commit()

    return InitiateOutcome(
        result=InitiateResult.PROPOSED,
        swap=swap,
        reply_body=ack,
        reply_language=a_lang,
    )


# ----- 2. accept / reject -----


def latest_pending_swap_for_target(
    db: Session, to_donor_id: uuid.UUID
) -> Optional[SlotSwapRequest]:
    """Most-recent PROPOSED swap awaiting a YES/NO from this donor."""
    return (
        db.execute(
            select(SlotSwapRequest)
            .where(
                SlotSwapRequest.to_donor_id == to_donor_id,
                SlotSwapRequest.status == SwapStatus.PROPOSED.value,
            )
            .order_by(desc(SlotSwapRequest.created_at))
            .limit(1)
        )
        .scalars()
        .first()
    )


@dataclass
class AcceptOutcome:
    swap: SlotSwapRequest
    reply_body: str
    reply_language: str


def accept_swap(
    db: Session, *, swap: SlotSwapRequest, commit: bool = False
) -> AcceptOutcome:
    """Donor B said YES. Flip ACCEPTED, notify A + B, trigger schedule auto-resolve."""
    bridge = db.get(Bridge, swap.bridge_id)
    from_donor = db.get(Donor, swap.from_donor_id)
    to_donor = db.get(Donor, swap.to_donor_id)
    assert bridge and from_donor and to_donor

    swap.status = SwapStatus.ACCEPTED
    swap.accepted_at = datetime.utcnow()
    db.flush()

    patient_name = bridge.patient.name if bridge.patient else "the patient"
    patient_age = bridge.patient.age if bridge.patient else 0
    patient_bg = (
        getattr(bridge.patient.blood_group, "value", str(bridge.patient.blood_group))
        if bridge.patient
        else ""
    )
    a_lang = getattr(from_donor.preferred_language, "value", str(from_donor.preferred_language)) or "en"
    b_lang = getattr(to_donor.preferred_language, "value", str(to_donor.preferred_language)) or "en"

    common = dict(
        from_donor_first=_first_word(from_donor.name),
        from_donor_name=from_donor.name,
        to_donor_first=_first_word(to_donor.name),
        to_donor_name=to_donor.name,
        patient_name=patient_name,
        patient_age=patient_age,
        patient_blood_group=patient_bg,
        from_slot_date=swap.from_slot_date.isoformat(),
        to_slot_date=swap.to_slot_date.isoformat(),
    )

    # Notify A
    _send_template_to(
        db, donor=from_donor, template_key="swap_confirmed",
        language=a_lang, bridge=bridge, **common,
    )
    # Notify B — both persist a row AND render the body for TwiML
    _send_template_to(
        db, donor=to_donor, template_key="swap_confirmed",
        language=b_lang, bridge=bridge, **common,
    )
    rendered_b = _tmpl.render(
        "swap_confirmed", language=b_lang, **common,
    )

    # Auto-resolve the schedule + log it (G3 reuse). Best-effort.
    try:
        from app.services.schedule_resolve import (
            auto_resolve_schedule,
            capture_baseline,
        )
        before = capture_baseline(bridge)
        db.refresh(bridge)
        auto_resolve_schedule(
            db,
            bridge=bridge,
            triggered_by="swap_accepted",
            before=before,
            notes=f"Swap {from_donor.name} ({swap.from_slot_date.isoformat()}) ↔ "
                  f"{to_donor.name} ({swap.to_slot_date.isoformat()})",
        )
    except Exception:
        db.rollback()  # don't fail the whole accept if scheduling errors

    if commit:
        db.commit()

    return AcceptOutcome(
        swap=swap,
        reply_body=rendered_b.body,
        reply_language=rendered_b.language_used,
    )


@dataclass
class RejectOutcome:
    swap: SlotSwapRequest
    reply_body: str
    reply_language: str


def reject_swap(
    db: Session, *, swap: SlotSwapRequest, commit: bool = False
) -> RejectOutcome:
    """Donor B said NO. Flip REJECTED, notify A."""
    bridge = db.get(Bridge, swap.bridge_id)
    from_donor = db.get(Donor, swap.from_donor_id)
    to_donor = db.get(Donor, swap.to_donor_id)
    assert bridge and from_donor and to_donor

    swap.status = SwapStatus.REJECTED
    swap.rejected_at = datetime.utcnow()
    db.flush()

    a_lang = getattr(from_donor.preferred_language, "value", str(from_donor.preferred_language)) or "en"
    b_lang = getattr(to_donor.preferred_language, "value", str(to_donor.preferred_language)) or "en"
    patient_name = bridge.patient.name if bridge.patient else "the patient"

    _send_template_to(
        db,
        donor=from_donor,
        template_key="swap_rejected_to_requester",
        language=a_lang,
        bridge=bridge,
        from_donor_first=_first_word(from_donor.name),
        from_donor_name=from_donor.name,
        to_donor_first=_first_word(to_donor.name),
        to_donor_name=to_donor.name,
        patient_name=patient_name,
        from_slot_date=swap.from_slot_date.isoformat(),
        to_slot_date=swap.to_slot_date.isoformat(),
    )

    # Brief ack back to B in B's language
    reply = (
        f"Thanks {_first_word(to_donor.name)} — declined. Your current slot stays."
    )

    if commit:
        db.commit()

    return RejectOutcome(
        swap=swap, reply_body=reply, reply_language=b_lang,
    )


# ----- 3. lazy expiry -----


def expire_stale_swaps(
    db: Session, *, bridge_id: Optional[uuid.UUID] = None, now: Optional[datetime] = None
) -> int:
    """Flip PROPOSED swaps older than 48h to EXPIRED. Returns count expired."""
    now = now or datetime.utcnow()
    stmt = select(SlotSwapRequest).where(
        SlotSwapRequest.status == SwapStatus.PROPOSED.value,
        SlotSwapRequest.expires_at <= now,
    )
    if bridge_id is not None:
        stmt = stmt.where(SlotSwapRequest.bridge_id == bridge_id)
    rows = list(db.execute(stmt).scalars())
    for r in rows:
        r.status = SwapStatus.EXPIRED
    return len(rows)


def list_swaps_for_bridge(
    db: Session, bridge_id: uuid.UUID, *, limit: int = 20
) -> list[SlotSwapRequest]:
    """Most-recent-first, includes all statuses (UI filters as needed)."""
    expire_stale_swaps(db, bridge_id=bridge_id)
    return list(
        db.execute(
            select(SlotSwapRequest)
            .where(SlotSwapRequest.bridge_id == bridge_id)
            .order_by(desc(SlotSwapRequest.created_at))
            .limit(max(1, min(limit, 100)))
        ).scalars()
    )
