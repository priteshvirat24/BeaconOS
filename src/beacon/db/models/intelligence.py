"""Intelligence gap, request, human report, and hypothesis models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from beacon.db.base import Base, TimestampMixin, UUIDMixin


class IntelligenceGap(Base, UUIDMixin, TimestampMixin):
    """Identified gap in operational knowledge with prioritization."""

    __tablename__ = "intelligence_gaps"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    question: Mapped[str] = mapped_column(Text, nullable=False)
    related_claim_ids: Mapped[list | None] = mapped_column(JSONB)
    affected_decision_ids: Mapped[list | None] = mapped_column(JSONB)
    affected_plan_ids: Mapped[list | None] = mapped_column(JSONB)
    affected_task_ids: Mapped[list | None] = mapped_column(JSONB)

    # Scoring
    uncertainty_score: Mapped[float] = mapped_column(Float, default=0.5)
    decision_impact: Mapped[float] = mapped_column(Float, default=0.5)
    urgency: Mapped[float] = mapped_column(Float, default=0.5)
    resolvability: Mapped[float] = mapped_column(Float, default=0.5)
    acquisition_cost: Mapped[float] = mapped_column(Float, default=0.5)
    priority: Mapped[float] = mapped_column(Float, default=0.0)

    # Strategy
    candidate_strategies: Mapped[list | None] = mapped_column(JSONB)
    selected_strategy: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="identified", nullable=False)

    # Lifecycle
    expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fallback_action: Mapped[str | None] = mapped_column(Text)
    resolved_by_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class IntelligenceRequest(Base, UUIDMixin, TimestampMixin):
    """Request for human intelligence via Slack."""

    __tablename__ = "intelligence_requests"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )
    gap_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intelligence_gaps.id"), nullable=True
    )

    question: Mapped[str] = mapped_column(Text, nullable=False)
    why_needed: Mapped[str] = mapped_column(Text, nullable=False)
    related_plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    related_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Targeting
    requested_channel_id: Mapped[str | None] = mapped_column(String(50))
    requested_user_ids: Mapped[list | None] = mapped_column(JSONB)
    response_fields: Mapped[dict | None] = mapped_column(JSONB)

    # Urgency
    urgency: Mapped[str] = mapped_column(String(50), default="normal")
    expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fallback_action: Mapped[str | None] = mapped_column(Text)

    # Slack tracking
    slack_message_ts: Mapped[str | None] = mapped_column(String(50))
    slack_channel_id: Mapped[str | None] = mapped_column(String(50))

    # Status
    status: Mapped[str] = mapped_column(String(50), default="pending")
    response_evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class HumanReport(Base, UUIDMixin, TimestampMixin):
    """Human-submitted report that becomes evidence."""

    __tablename__ = "human_reports"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )

    reporter_slack_id: Mapped[str] = mapped_column(String(50), nullable=False)
    reporter_name: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    report_type: Mapped[str] = mapped_column(String(100), default="observation")

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class Hypothesis(Base, UUIDMixin, TimestampMixin):
    """Competing explanation maintained when evidence is incomplete."""

    __tablename__ = "hypotheses"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    statement: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_claim_ids: Mapped[list | None] = mapped_column(JSONB)
    contradicting_claim_ids: Mapped[list | None] = mapped_column(JSONB)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)

    discriminating_evidence_needed: Mapped[str | None] = mapped_column(Text)
    consequences_if_true: Mapped[str | None] = mapped_column(Text)
    consequences_if_false: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    created_by_agent: Mapped[str | None] = mapped_column(String(100))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
