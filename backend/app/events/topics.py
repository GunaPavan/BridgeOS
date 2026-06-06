"""SNS topic catalogue.

Topic names are stable. New topics get added here (and then subscribers
register against them). The actual SNS topics are auto-provisioned on
first publish via ``app.integrations.sns_client._ensure_topic_exists``.
"""

from __future__ import annotations

from enum import Enum


class TopicName(str, Enum):
    DONOR_REPLY_ACCEPT = "donor-reply-accept"
    DONOR_REPLY_DECLINE = "donor-reply-decline"
    DONOR_REPLY_OPT_OUT = "donor-reply-opt-out"
    DONOR_REPLY_OUT_OF_TOWN = "donor-reply-out-of-town"
    DONOR_REPLY_MEDICAL_DEFER = "donor-reply-medical-defer"
    WAVE_EXPIRED = "wave-expired"
    WAVE_ACCEPTED = "wave-accepted"
    # E7: caregiver email replies. Different from donor replies because the
    # actor is the caregiver (parent / family) replying to a digest email —
    # the side effects are bridge-level (e.g. "we found a donor, cancel
    # other outreach") rather than donor-cooldown.
    CAREGIVER_REPLY_RESOLVED = "caregiver-reply-resolved"  # "we're sorted"
    CAREGIVER_REPLY_URGENT = "caregiver-reply-urgent"      # "need attention now"
    CAREGIVER_REPLY_QUESTION = "caregiver-reply-question"  # forward to Care Agent


ALL_TOPICS: tuple[TopicName, ...] = tuple(TopicName)
