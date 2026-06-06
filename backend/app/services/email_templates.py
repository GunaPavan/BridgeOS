"""Email templates for the SES channel.

Three production templates for Phase E2:

  - caregiver_daily_digest   — 8 AM IST summary of the patient's bridge state
  - caregiver_emergency_alert — same patient + urgent slot, sent when allocator
                                escalates past Tier 2 or WhatsApp delivery fails
  - coordinator_failure_alert — operational alert when a wave hits Tier 3+
                                without acceptance

English only for v1 — we have the i18n machinery in whatsapp_templates for
when we want to ship Hindi/Telugu/etc. Keeping it English-only ships the
demo faster without giving up the architecture.

Each template returns ``(subject, body)`` — plain text body (SES sandbox
accepts HTML too but text is cheaper + more universal).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    body: str
    template_key: str


# ---------------------------------------------------------------------------
# caregiver_daily_digest
# ---------------------------------------------------------------------------


def render_caregiver_daily_digest(
    *,
    caregiver_first: str,
    patient_name: str,
    next_transfusion_date: Optional[date],
    days_until: Optional[int],
    active_donor_count: int,
    bridge_health_label: str,
    pending_donor_count: int = 0,
) -> RenderedEmail:
    subject = f"Bridge OS · today's update for {patient_name}"
    when = (
        f"on {next_transfusion_date.isoformat()}"
        if next_transfusion_date
        else "not yet scheduled"
    )
    countdown = (
        f"({days_until} days from now)"
        if (days_until is not None and days_until >= 0)
        else "(overdue — coordinator notified)"
        if days_until is not None
        else ""
    )
    body = (
        f"Hi {caregiver_first or 'there'},\n\n"
        f"Quick update on {patient_name}'s Blood Bridge:\n\n"
        f"  • Next transfusion: {when} {countdown}\n"
        f"  • Active donors on the bridge: {active_donor_count}\n"
        f"  • Bridge health: {bridge_health_label}\n"
    )
    if pending_donor_count:
        body += f"  • New donor invites in flight: {pending_donor_count}\n"
    body += (
        "\n"
        "You'll continue to receive WhatsApp updates for time-sensitive moments. "
        "This daily email is the calm, single-glance summary.\n\n"
        "— Bridge OS, on behalf of Blood Warriors\n"
    )
    return RenderedEmail(
        subject=subject, body=body, template_key="caregiver_daily_digest"
    )


# ---------------------------------------------------------------------------
# caregiver_emergency_alert
# ---------------------------------------------------------------------------


def render_caregiver_emergency_alert(
    *,
    caregiver_first: str,
    patient_name: str,
    slot_date: date,
    hospital: str,
    tier_label: str,
) -> RenderedEmail:
    subject = f"URGENT · {patient_name} needs donors for {slot_date.isoformat()}"
    body = (
        f"Hi {caregiver_first or 'there'},\n\n"
        f"This is an urgent update on {patient_name}'s upcoming transfusion at "
        f"{hospital} on {slot_date.isoformat()}.\n\n"
        f"The Alert Allocator has escalated to {tier_label} — we're contacting a "
        f"wider donor pool through every available channel. The coordinator is "
        f"on it and will reach you directly within the hour if intervention is "
        f"needed.\n\n"
        f"You don't need to do anything — this is informational. If you have "
        f"a private donor lead in mind, reply to this email and the coordinator "
        f"will follow up.\n\n"
        f"— Bridge OS, on behalf of Blood Warriors\n"
    )
    return RenderedEmail(
        subject=subject, body=body, template_key="caregiver_emergency_alert"
    )


# ---------------------------------------------------------------------------
# coordinator_failure_alert
# ---------------------------------------------------------------------------


def render_coordinator_failure_alert(
    *,
    patient_name: str,
    slot_date: date,
    tier_label: str,
    wave_id: str,
    pings_sent: int,
    pings_accepted: int,
    pings_declined: int,
    pings_no_reply: int,
) -> RenderedEmail:
    subject = f"OPS · escalation past {tier_label} on {patient_name} ({slot_date.isoformat()})"
    body = (
        f"Wave {wave_id} for {patient_name} has escalated through {tier_label} "
        f"without acceptance.\n\n"
        f"Counters:\n"
        f"  sent     : {pings_sent}\n"
        f"  accepted : {pings_accepted}\n"
        f"  declined : {pings_declined}\n"
        f"  no reply : {pings_no_reply}\n\n"
        f"Next system action: Tier 4 external lookup (eRaktKosh + ICMR RDRI). "
        f"Recommend manual coordinator intervention.\n\n"
        f"Open the wave in Bridge OS → /outreach/{wave_id}\n"
    )
    return RenderedEmail(
        subject=subject, body=body, template_key="coordinator_failure_alert"
    )


# ---------------------------------------------------------------------------
# Convenience — listing what's available (for /emails/distribution + tests)
# ---------------------------------------------------------------------------


ALL_TEMPLATE_KEYS: tuple[str, ...] = (
    "caregiver_daily_digest",
    "caregiver_emergency_alert",
    "coordinator_failure_alert",
)
