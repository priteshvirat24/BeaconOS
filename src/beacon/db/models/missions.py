"""Mission (AgentMission) model."""

from __future__ import annotations

import uuid
from datetime import datetime

from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from beacon.db.base import Base, TimestampMixin, UUIDMixin


class Mission(Base, UUIDMixin, TimestampMixin):
    """AgentMission — a discrete unit of work assigned to an agent."""

    __tablename__ = "missions"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    objective: Mapped[str] = mapped_column(Text, nullable=False)
    mission_type: Mapped[str] = mapped_column(String(100), nullable=False)
    priority: Mapped[float] = mapped_column(Float, default=0.5)

    required_capabilities: Mapped[list | None] = mapped_column(JSONB)
    allowed_tools: Mapped[list | None] = mapped_column(JSONB)
    input_refs: Mapped[dict | None] = mapped_column(JSONB)
    success_criteria: Mapped[list | None] = mapped_column(JSONB)
    termination_conditions: Mapped[list | None] = mapped_column(JSONB)
    budget: Mapped[dict | None] = mapped_column(JSONB)
    dependencies: Mapped[list | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(50), default="created", nullable=False)
    assigned_agent: Mapped[str | None] = mapped_column(String(100))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    parent_mission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True
    )
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(64))

    result: Mapped[dict | None] = mapped_column(JSONB)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)

    crisis: Mapped[Optional["Crisis"]] = relationship("Crisis", back_populates="missions")
