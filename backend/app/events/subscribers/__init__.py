"""Subscribers register themselves on import.

Each module under this package calls ``@register_subscriber(...)`` at import
time. Importing the package once loads all of them.
"""

from app.events.subscribers import (  # noqa: F401
    allocator_refire,
    caregiver_email_actions,
    caregiver_notify,
    cooldown_handler,
    ema_feedback,
    sibling_cancel,
)
