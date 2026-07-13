"""Decision, Recommendation, Commitment, and Approval models."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from beacon.db.base import Base, TimestampMixin, UUIDMixin, VersionMixin


class Recommendation(Base, UUIDMixin, TimestampMixin):
    """Evidence-backed recommendation for human approval."""

    __tablename__ = "recommendations"

    crisis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=False
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("response_plans.id"), nullable=True
    )

    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives: Mapped[list | None] = mapped_column(JSONB)
    supporting_claim_ids: Mapped[list | None] = mapped_column(JSONB)
    evidence_citation_ids: Mapped[list | None] = mapped_column(JSONB)
    unresolved_uncertainty: Mapped[list | None] = mapped_column(JSONB)
    risks: Mapped[list | None] = mapped_column(JSONB)
    required_approvals: Mapped[list | None] = mapped_column(JSONB)
    expected_next_state: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_by_agent: Mapped[str | None] = mapped_column(String(100))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class Decision(Base, UUIDMixin, TimestampMixin, VersionMixin):
    """Persistent decision record with evidence citations."""

    __tablename__ = "decisions"

    crisis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=False
    )

    decision: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    alternatives: Mapped[list | None] = mapped_column(JSONB)
    supporting_claim_ids: Mapped[list | None] = mapped_column(JSONB)
    evidence_ids: Mapped[list | None] = mapped_column(JSONB)
    risks: Mapped[list | None] = mapped_column(JSONB)

    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=True
    )
    dependent_plan_ids: Mapped[list | None] = mapped_column(JSONB)
    dependent_task_ids: Mapped[list | None] = mapped_column(JSONB)

    status: Mapped[str] = mapped_column(String(50), default="active")
    outcome: Mapped[str | None] = mapped_column(Text)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)

    crisis: Mapped["Crisis"] = relationship("Crisis", back_populates="decisions")


class Commitment(Base, UUIDMixin, TimestampMixin):
    """Detected operational commitment from Slack content."""

    __tablename__ = "commitments"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )

    statement: Mapped[str] = mapped_column(Text, nullable=False)
    committer_slack_id: Mapped[str | None] = mapped_column(String(50))
    committer_name: Mapped[str | None] = mapped_column(String(255))
    commitment_type: Mapped[str] = mapped_column(String(100), nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(50), default="detected")
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )

    slack_channel_id: Mapped[str | None] = mapped_column(String(50))
    slack_message_ts: Mapped[str | None] = mapped_column(String(50))
    slack_permalink: Mapped[str | None] = mapped_column(String(2000))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class Approval(Base, UUIDMixin, TimestampMixin):
    """Approval record for policy-gated actions."""

    __tablename__ = "approvals"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    state_version: Mapped[int | None] = mapped_column()
    authority_required: Mapped[str] = mapped_column(String(50), nullable=False)

    # Decision
    decision: Mapped[str] = mapped_column(String(50), default="pending")
    approver_slack_id: Mapped[str | None] = mapped_column(String(50))
    approver_name: Mapped[str | None] = mapped_column(String(255))
    comments: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Slack tracking
    slack_message_ts: Mapped[str | None] = mapped_column(String(50))
    slack_channel_id: Mapped[str | None] = mapped_column(String(50))

    # Trace
    trace_id: Mapped[str | None] = mapped_column(String(64))
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
