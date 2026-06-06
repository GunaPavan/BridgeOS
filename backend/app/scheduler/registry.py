"""Declarative job catalogue.

One ``JobSpec`` per code-defined background job. The runtime upserts each
spec into ``ScheduledJob`` at startup so per-job state (pause/resume,
cron_override) persists across restarts.

DEMO MODE: every spec carries a second cron expression. When demo-mode
is toggled on via the API, the runtime re-registers all jobs against
``demo_cron`` instead of ``cron``. Cadences compress from minutes/hours
into seconds so judges see the loop tick visibly.

Job handlers are imported lazily inside ``handler_factory`` callables so
this module stays import-cheap and Phase B can add new specs without
forcing scheduler.py to know about Twilio templates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class JobSpec:
    """Static metadata for one job."""

    name: str
    description: str
    # APScheduler cron (CronTrigger) for normal use. Format mirrors the
    # standard 5/6-field cron: "*/5 * * * *" (every 5 min).
    cron: str
    # Compressed cron used when demo-mode is on. Same syntax.
    demo_cron: str
    # When True, the job is registered enabled the very first time it lands
    # in the DB. Persisted state takes over from then on.
    default_enabled: bool
    # Lazy import: returns the (db, now) -> JobResult callable. We don't
    # import the handler module at module-import time so the scheduler is
    # cheap to load (and lets us avoid cycles with outreach.engine etc.).
    handler_factory: Callable[[], Callable]


def _allocator_handler():
    from app.scheduler.jobs import auto_run_cycle

    return auto_run_cycle


def _expire_handler():
    from app.scheduler.jobs import auto_expire_and_escalate

    return auto_expire_and_escalate


def _pending_nudge_handler():
    from app.scheduler.jobs import auto_pending_nudge

    return auto_pending_nudge


def _pre_reminder_handler():
    from app.scheduler.jobs import auto_pre_donation_reminder

    return auto_pre_donation_reminder


def _thank_you_handler():
    from app.scheduler.jobs import auto_post_donation_thank_you

    return auto_post_donation_thank_you


def _email_digest_handler():
    from app.scheduler.jobs import auto_caregiver_email_digest

    return auto_caregiver_email_digest


REGISTRY: list[JobSpec] = [
    JobSpec(
        name="auto_run_cycle",
        description=(
            "Run the global allocator cycle. Picks open slots, scores donor "
            "candidates, materialises waves + pings, hands them to the "
            "Twilio dispatcher."
        ),
        cron="*/5 * * * *",      # every 5 min
        demo_cron="*/30 * * * * *",  # every 30 seconds (6-field syntax)
        default_enabled=True,
        handler_factory=_allocator_handler,
    ),
    JobSpec(
        name="auto_expire_and_escalate",
        description=(
            "Mark past-due waves EXPIRED, then create the next-tier wave "
            "so the slot keeps trying to fill itself."
        ),
        cron="* * * * *",         # every minute
        demo_cron="*/15 * * * * *",  # every 15 seconds
        default_enabled=True,
        handler_factory=_expire_handler,
    ),
    JobSpec(
        name="auto_pending_nudge",
        description=(
            "Send a softer reminder to donors whose ping is still PENDING "
            "after the configured threshold. Skips during quiet hours."
        ),
        cron="*/30 * * * *",     # every 30 min
        demo_cron="*/45 * * * * *",  # every 45 seconds
        default_enabled=True,
        handler_factory=_pending_nudge_handler,
    ),
    JobSpec(
        name="auto_pre_donation_reminder",
        description=(
            "Day-before reminder for donors who accepted: tomorrow's slot "
            "+ hospital + map link."
        ),
        cron="0 9 * * *",         # daily at 09:00
        demo_cron="0 * * * * *",  # every minute (second 0) in demo mode
        default_enabled=True,
        handler_factory=_pre_reminder_handler,
    ),
    JobSpec(
        name="auto_post_donation_thank_you",
        description=(
            "Confirm-and-thank loop: after a donation is recorded, send "
            "appreciation + next-eligible-date so the donor stays engaged."
        ),
        cron="0 */6 * * *",       # every 6 hours
        demo_cron="*/45 * * * * *",  # every 45 seconds (in demo mode)
        default_enabled=True,
        handler_factory=_thank_you_handler,
    ),
    JobSpec(
        name="auto_caregiver_email_digest",
        description=(
            "Daily 8 AM IST email digest to every patient's caregiver — "
            "next transfusion date, bridge health, active donor count. SES "
            "channel, calm-tone counterpart to the urgent WhatsApp rail."
        ),
        cron="30 2 * * *",        # 08:00 IST = 02:30 UTC
        demo_cron="*/45 * * * * *",
        default_enabled=True,
        handler_factory=_email_digest_handler,
    ),
]


def get_spec(name: str) -> JobSpec | None:
    """Lookup helper."""
    for spec in REGISTRY:
        if spec.name == name:
            return spec
    return None
