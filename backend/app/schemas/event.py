"""Pydantic schemas for /system/events/*."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TopicWithSubscribers(BaseModel):
    topic: str
    subscribers: list[str]


class EventOut(BaseModel):
    message_id: str
    topic_name: str
    body: dict
    published_at: datetime
    is_mock: bool


class DispatcherStatus(BaseModel):
    running: bool
    delivered: int
    failed: int
    last_tick_at: Optional[datetime] = None
    topics: list[TopicWithSubscribers]


class RepublishResult(BaseModel):
    original_message_id: str
    new_message_id: str
    topic_name: str
    is_mock: bool
