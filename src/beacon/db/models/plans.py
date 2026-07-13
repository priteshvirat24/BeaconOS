"""Response plan, plan task, and plan dependency models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from beacon.db.base import Base, TimestampMixin, UUIDMixin, VersionMixin


class ResponsePlan(Base, UUIDMixin, TimestampMixin, VersionMixin):
    """Structured response plan represented as a DAG of tasks."""

    __tablename__ = "response_plans"

    crisis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=False
    )

    objective: Mapped[str] = mapped_column(Text, nullable=False)
    strategy: Mapped[str | None] = mapped_column(Text)
    assumptions: Mapped[list | None] = mapped_column(JSONB)
    required_claim_ids: Mapped[list | None] = mapped_column(JSONB)
    required_resource_ids: Mapped[list | None] = mapped_column(JSONB)
    constraints: Mapped[list | None] = mapped_column(JSONB)
    fallbacks: Mapped[list | None] = mapped_column(JSONB)
    success_criteria: Mapped[list | None] = mapped_column(JSONB)
    failure_conditions: Mapped[list | None] = mapped_column(JSONB)
    risk_summary: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    created_by_agent: Mapped[str | None] = mapped_column(String(100))
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)

    crisis: Mapped["Crisis"] = relationship("Crisis", back_populates="plans")
    plan_tasks: Mapped[list[PlanTask]] = relationship(back_populates="plan")


class PlanTask(Base, UUIDMixin, TimestampMixin):
    """Individual task within a response plan DAG."""

    __tablename__ = "plan_tasks"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("response_plans.id"), nullable=False
    )

    objective: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True
    )
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    required_resource_ids: Mapped[list | None] = mapped_column(JSONB)
    required_claim_ids: Mapped[list | None] = mapped_column(JSONB)
    success_criteria: Mapped[list | None] = mapped_column(JSONB)
    failure_conditions: Mapped[list | None] = mapped_column(JSONB)
    fallback_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    reversibility: Mapped[str | None] = mapped_column(String(50))
    authority_required: Mapped[str | None] = mapped_column(String(50))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)

    plan: Mapped[ResponsePlan] = relationship(back_populates="plan_tasks")
    dependencies: Mapped[list[PlanDependency]] = relationship(
        back_populates="dependent_task",
        foreign_keys="PlanDependency.dependent_task_id",
    )


class PlanDependency(Base, UUIDMixin, TimestampMixin):
    """Dependency edge between plan tasks."""

    __tablename__ = "plan_dependencies"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("response_plans.id"), nullable=False
    )
    dependent_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plan_tasks.id"), nullable=False
    )
    dependency_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plan_tasks.id"), nullable=False
    )
    dependency_type: Mapped[str] = mapped_column(String(50), default="finish_to_start")

    dependent_task: Mapped[PlanTask] = relationship(
        foreign_keys=[dependent_task_id], back_populates="dependencies"
    )


class PlanResourceRequirement(Base, UUIDMixin, TimestampMixin):
    """Resource requirement for a plan task."""

    __tablename__ = "plan_resource_requirements"

    plan_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plan_tasks.id"), nullable=False
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resources.id"), nullable=True
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity_needed: Mapped[int] = mapped_column(Integer, default=1)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)


class PlanClaimDependency(Base, UUIDMixin, TimestampMixin):
    """Claim dependency for a plan — plan validity depends on claim status."""

    __tablename__ = "plan_claim_dependencies"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("response_plans.id"), nullable=False
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id"), nullable=False
    )
    is_critical: Mapped[bool] = mapped_column(Boolean, default=True)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.5)
