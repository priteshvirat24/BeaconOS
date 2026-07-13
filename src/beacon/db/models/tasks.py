"""Task and TaskDependency models."""

from __future__ import annotations

import uuid
from datetime import datetime

from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from beacon.db.base import Base, TimestampMixin, UUIDMixin, VersionMixin


class Task(Base, UUIDMixin, TimestampMixin, VersionMixin):
    """Operational task derived from commitments or plans."""

    __tablename__ = "tasks"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("response_plans.id"), nullable=True
    )
    plan_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plan_tasks.id"), nullable=True
    )
    commitment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commitments.id"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="proposed", nullable=False)

    # Assignment
    assigned_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True
    )
    assigned_slack_user_id: Mapped[str | None] = mapped_column(String(50))
    assigned_name: Mapped[str | None] = mapped_column(String(255))

    # Timing
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer)

    # Verification
    requires_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Slack tracking
    slack_channel_id: Mapped[str | None] = mapped_column(String(50))
    slack_message_ts: Mapped[str | None] = mapped_column(String(50))

    # Priority
    priority: Mapped[float] = mapped_column(Float, default=0.5)
    is_blocked_reason: Mapped[str | None] = mapped_column(Text)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)

    crisis: Mapped[Optional["Crisis"]] = relationship("Crisis", back_populates="tasks")
    dependencies: Mapped[list[TaskDependency]] = relationship(
        back_populates="dependent_task",
        foreign_keys="TaskDependency.dependent_task_id",
    )


class TaskDependency(Base, UUIDMixin, TimestampMixin):
    """Dependency between operational tasks."""

    __tablename__ = "task_dependencies"

    dependent_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    dependency_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    dependency_type: Mapped[str] = mapped_column(String(50), default="finish_to_start")

    dependent_task: Mapped[Task] = relationship(
        foreign_keys=[dependent_task_id], back_populates="dependencies"
    )
