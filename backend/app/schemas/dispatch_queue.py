"""Pydantic schemas for the /system/dispatch-queue/* API."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DispatchQueueStatus(BaseModel):
    primary_depth: int
    in_flight: int
    dlq_depth: int
    mode: str  # "live" | "mock"
    error: Optional[str] = None
    # Worker stats
    worker_running: bool
    worker_received: int
    worker_sent: int
    worker_duplicates_skipped: int
    worker_failed: int
    worker_last_drained_at: Optional[datetime] = None
    worker_started_at: Optional[datetime] = None


class DispatchMessageOut(BaseModel):
    message_id: str
    body: dict
    is_mock: bool
    queue_name: str
    approximate_receive_count: int


class ReplayResult(BaseModel):
    replayed: int
    failed: int


class DeleteMessageResult(BaseModel):
    message_id: str
    removed: bool
