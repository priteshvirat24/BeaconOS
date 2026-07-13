"""Memory models: IncidentEpisode, LessonProposal, Procedure, ProcedureVersion."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from beacon.db.base import Base, TimestampMixin, UUIDMixin, VersionMixin


class IncidentEpisode(Base, UUIDMixin, TimestampMixin):
    """Episodic memory of a resolved crisis for similar-incident retrieval."""

    __tablename__ = "incident_episodes"

    crisis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=False, unique=True
    )

    event_summary: Mapped[str] = mapped_column(Text, nullable=False)
    affected_regions: Mapped[list | None] = mapped_column(JSONB)
    hazard_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Key data references
    initial_evidence_ids: Mapped[list | None] = mapped_column(JSONB)
    critical_gap_summaries: Mapped[list | None] = mapped_column(JSONB)
    contradiction_summaries: Mapped[list | None] = mapped_column(JSONB)
    hypothesis_summaries: Mapped[list | None] = mapped_column(JSONB)
    plans_considered: Mapped[list | None] = mapped_column(JSONB)
    selected_plan_summary: Mapped[str | None] = mapped_column(Text)
    decision_summaries: Mapped[list | None] = mapped_column(JSONB)
    task_outcomes: Mapped[list | None] = mapped_column(JSONB)
    material_changes: Mapped[list | None] = mapped_column(JSONB)
    replanning_events: Mapped[list | None] = mapped_column(JSONB)
    bottlenecks: Mapped[list | None] = mapped_column(JSONB)
    successful_interventions: Mapped[list | None] = mapped_column(JSONB)
    failures: Mapped[list | None] = mapped_column(JSONB)
    lessons: Mapped[list | None] = mapped_column(JSONB)

    # Semantic embedding for similarity search
    embedding: Mapped[list | None] = mapped_column(Vector(768), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="draft")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class LessonProposal(Base, UUIDMixin, TimestampMixin):
    """Proposed procedural lesson from after-action analysis."""

    __tablename__ = "lesson_proposals"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_episodes.id"), nullable=True
    )

    lesson: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_ids: Mapped[list | None] = mapped_column(JSONB)
    supporting_data: Mapped[dict | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(50), default="proposed")
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comments: Mapped[str | None] = mapped_column(Text)

    procedure_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procedures.id"), nullable=True
    )

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class Procedure(Base, UUIDMixin, TimestampMixin):
    """Organizational procedure (standard operating procedure)."""

    __tablename__ = "procedures"

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Semantic embedding for retrieval
    embedding: Mapped[list | None] = mapped_column(Vector(768), nullable=True)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class ProcedureVersion(Base, UUIDMixin, TimestampMixin):
    """Versioned procedure content."""

    __tablename__ = "procedure_versions"

    procedure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procedures.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text)

    # Source lesson
    lesson_proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lesson_proposals.id"), nullable=True
    )

    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
