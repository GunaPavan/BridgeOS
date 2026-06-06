"""ScheduleResolveLog — G3 audit row for every auto re-solve.

One row per (bridge, trigger) capturing the before/after solver state so the
bridge detail page can show coordinators what changed and when.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.types import GUID


class ScheduleResolveLog(Base):
    """One auto-resolve event for a bridge's rotation schedule."""

    __tablename__ = "schedule_resolve_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("bridges.id", ondelete="CASCADE"), index=True
    )

    # Solver outcomes as strings (cross-dialect, mirrors SolverStatus enum)
    before_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    after_status: Mapped[str] = mapped_column(String(20))

    before_objective: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    after_objective: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Counts useful for the UI summary
    before_slot_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    after_slot_count: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Why this re-solve fired — "webhook_yes", "webhook_no_change", "recruit",
    # "manual", "membership_exit", etc.
    triggered_by: Mapped[str] = mapped_column(String(32), index=True)

    # Solve time of the *after* solve in ms (the before solve isn't tracked
    # separately because it's the same bridge with one fewer/more donor).
    solve_time_ms: Mapped[Optional[int]] = mapped_column(nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
