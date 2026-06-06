"""Cohort memory = per-entity context assembly.

For each agent turn we look at the optional entity hint (donor/bridge/patient)
and pull together a structured summary the LLM can reason over:

    donor   -> profile + recent WhatsApp + bridge memberships
    bridge  -> patient + active donors + recent stability + recent schedule slots
    patient -> profile + bridge ref

This is the "memory" — it's not a vector store, but for the demo's size
(50 patients / 500 donors) a fresh assemble-per-turn is fast and exact.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    Bridge,
    BridgeMembership,
    Donor,
    MembershipStatus,
    Patient,
    WhatsAppMessage,
)


@dataclass
class AgentContext:
    """All facts the LLM should see for this turn — string-only for prompts."""

    summary: str  # human-readable summary block
    sources: list["ContextSource"] = field(default_factory=list)
    donor_id: Optional[uuid.UUID] = None
    bridge_id: Optional[uuid.UUID] = None
    patient_id: Optional[uuid.UUID] = None


@dataclass
class ContextSource:
    kind: str  # "donor", "bridge", "patient", "messages", "schedule"
    label: str  # e.g. "Donor: Priya Sharma"
    detail: str | None = None


def _bg(obj) -> str:
    return getattr(obj.blood_group, "value", str(obj.blood_group))


def _enum_val(obj) -> str:
    """Read an enum-or-string value from a SQLAlchemy column safely."""
    return getattr(obj, "value", str(obj))


def build_donor_context(db: Session, donor_id: uuid.UUID) -> AgentContext:
    donor = db.get(Donor, donor_id)
    if donor is None:
        return AgentContext(summary=f"(No donor found for id {donor_id})")

    # Recent WhatsApp (last 10)
    msgs = (
        db.execute(
            select(WhatsAppMessage)
            .where(WhatsAppMessage.donor_id == donor.id)
            .order_by(desc(WhatsAppMessage.created_at))
            .limit(10)
        )
        .scalars()
        .all()
    )

    # Active bridge memberships
    memberships = (
        db.execute(
            select(BridgeMembership).where(BridgeMembership.donor_id == donor.id)
        )
        .scalars()
        .all()
    )

    days_since = (
        f"{(donor.last_donation_date and (donor.last_donation_date)).isoformat()}"
        if donor.last_donation_date
        else "never"
    )

    lines = [
        f"DONOR PROFILE",
        f"  Name: {donor.name}",
        f"  Age: {donor.age}",
        f"  Blood group: {_bg(donor)} (Kell-{'neg' if donor.kell_negative else 'pos'})",
        f"  City: {donor.city}, {donor.state}",
        f"  Preferred language: {_enum_val(donor.preferred_language)}",
        f"  Phone: {donor.phone}",
        f"  Last donation: {days_since}",
        f"  Total donations: {donor.total_donations}",
        f"  Response rate: {donor.response_rate:.0%}",
        f"  Avg response time: {donor.avg_response_hours:.0f}h",
        f"  Currently active: {donor.is_active}",
    ]
    sources = [ContextSource(kind="donor", label=f"Donor: {donor.name}")]

    if memberships:
        lines.append("")
        lines.append("BRIDGE MEMBERSHIPS")
        for m in memberships:
            bridge = db.get(Bridge, m.bridge_id)
            if bridge:
                patient = db.get(Patient, bridge.patient_id)
                pname = patient.name if patient else "?"
                lines.append(
                    f"  - {bridge.name} (patient {pname}, role {_enum_val(m.role)}, status {_enum_val(m.status)})"
                )
        sources.append(
            ContextSource(
                kind="bridge",
                label=f"Bridges: {len(memberships)} membership(s)",
            )
        )

    if msgs:
        lines.append("")
        lines.append("RECENT WHATSAPP MESSAGES (most recent first)")
        for m in msgs:
            arrow = "->" if _enum_val(m.direction) == "outbound" else "<-"
            tag = f" [{m.template_key}]" if m.template_key else ""
            lines.append(
                f"  {arrow} {m.created_at.strftime('%Y-%m-%d %H:%M')}{tag}: {m.body[:140]}"
            )
        sources.append(
            ContextSource(kind="messages", label=f"WhatsApp: {len(msgs)} recent message(s)")
        )

    return AgentContext(
        summary="\n".join(lines),
        sources=sources,
        donor_id=donor.id,
    )


def build_bridge_context(db: Session, bridge_id: uuid.UUID) -> AgentContext:
    bridge = db.get(Bridge, bridge_id)
    if bridge is None:
        return AgentContext(summary=f"(No bridge found for id {bridge_id})")
    patient = db.get(Patient, bridge.patient_id)
    active_members = [m for m in bridge.memberships if m.status == MembershipStatus.ACTIVE]

    lines = [
        f"BRIDGE: {bridge.name}",
        f"  Status: {_enum_val(bridge.status)}",
        f"  Active donor count: {len(active_members)} / {len(bridge.memberships)} total",
    ]
    sources = [ContextSource(kind="bridge", label=f"Bridge: {bridge.name}")]

    if patient:
        days_until = patient.days_until_transfusion
        lines.append("")
        lines.append("PATIENT")
        lines.append(f"  Name: {patient.name}")
        lines.append(f"  Age: {patient.age}")
        lines.append(
            f"  Blood group: {_bg(patient)} (Kell-{'neg' if patient.kell_negative else 'pos'})"
        )
        lines.append(f"  Hospital: {patient.hospital}, {patient.city}")
        lines.append(f"  Transfusion cadence: every {patient.transfusion_cadence_days} days")
        lines.append(
            f"  Last transfusion: {patient.last_transfusion_date.isoformat() if patient.last_transfusion_date else 'unknown'}"
        )
        if days_until is not None:
            lines.append(f"  Days until next transfusion: {days_until}")
        sources.append(ContextSource(kind="patient", label=f"Patient: {patient.name}"))

    if active_members:
        lines.append("")
        lines.append("ACTIVE DONORS IN COHORT")
        for m in active_members[:15]:
            donor = db.get(Donor, m.donor_id)
            if donor:
                lines.append(
                    f"  - {donor.name} ({_bg(donor)}, response {donor.response_rate:.0%}, "
                    f"{donor.total_donations} donations, "
                    f"last {donor.last_donation_date.isoformat() if donor.last_donation_date else 'never'})"
                )
        sources.append(
            ContextSource(
                kind="donor",
                label=f"Cohort donors: {len(active_members)}",
            )
        )

    return AgentContext(
        summary="\n".join(lines),
        sources=sources,
        bridge_id=bridge.id,
        patient_id=patient.id if patient else None,
    )


def build_patient_context(db: Session, patient_id: uuid.UUID) -> AgentContext:
    patient = db.get(Patient, patient_id)
    if patient is None:
        return AgentContext(summary=f"(No patient found for id {patient_id})")

    # Patient.bridge is set via relationship (patient.bridge)
    bridge = patient.bridge
    if bridge:
        return build_bridge_context(db, bridge.id)

    # Patient without a bridge
    lines = [
        f"PATIENT: {patient.name}",
        f"  Age: {patient.age}",
        f"  Blood group: {_bg(patient)}",
        f"  Hospital: {patient.hospital}",
        "  (No bridge assembled yet)",
    ]
    return AgentContext(
        summary="\n".join(lines),
        sources=[ContextSource(kind="patient", label=f"Patient: {patient.name}")],
        patient_id=patient.id,
    )
