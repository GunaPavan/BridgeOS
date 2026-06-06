"""Event bus — SNS-backed pub/sub for inbound webhooks.

A donor reply is interesting to many independent subscribers (cooldown,
EMA, allocator re-fire, caregiver notify). Instead of running them
synchronously inside the webhook handler, we publish ONE event and let
each subscriber consume it.

Live mode: SNS topics in the hackathon AWS account. Subscribers can be
Lambda functions, SQS queues, or in-process callbacks.

Mock mode: the same publish() writes to an in-memory history; the
in-process EventDispatcher subscriber list runs each callback.

Phase E4 only ships the in-process subscriber loop — Lambda subscribers
follow once we deploy.
"""

from app.events.topics import TopicName
from app.events.publishers import (
    publish_caregiver_reply_question,
    publish_caregiver_reply_resolved,
    publish_caregiver_reply_urgent,
    publish_donor_reply_accept,
    publish_donor_reply_decline,
    publish_donor_reply_medical_defer,
    publish_donor_reply_opt_out,
    publish_donor_reply_out_of_town,
    publish_wave_accepted,
    publish_wave_expired,
)
from app.events.dispatcher import (
    EventDispatcher,
    get_dispatcher,
    start_dispatcher,
    stop_dispatcher,
)

__all__ = [
    "TopicName",
    "publish_caregiver_reply_question",
    "publish_caregiver_reply_resolved",
    "publish_caregiver_reply_urgent",
    "publish_donor_reply_accept",
    "publish_donor_reply_decline",
    "publish_donor_reply_medical_defer",
    "publish_donor_reply_opt_out",
    "publish_donor_reply_out_of_town",
    "publish_wave_accepted",
    "publish_wave_expired",
    "EventDispatcher",
    "get_dispatcher",
    "start_dispatcher",
    "stop_dispatcher",
]
