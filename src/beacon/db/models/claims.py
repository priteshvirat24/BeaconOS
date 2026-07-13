"""Claim, Contradiction, and Uncertainty models."""

from __future__ import annotations

import uuid
from datetime import datetime

from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from beacon.db.base import Base, TimestampMixin, UUIDMixin, VersionMixin


class Claim(Base, UUIDMixin, TimestampMixin, VersionMixin):
    """A structured assertion derived from evidence.

    Claims have epistemic status tracking and confidence scoring.
    No operational recommendation may cite unsupported prose — it must reference Claims.
    """

    __tablename__ = "claims"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    # Structured claim
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_subject: Mapped[str | None] = mapped_column(String(500))
    predicate: Mapped[str | None] = mapped_column(String(500))
    object_: Mapped[str | None] = mapped_column("object", String(500))

    # Epistemic status
    epistemic_status: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    freshness: Mapped[float] = mapped_column(Float, default=1.0)

    # Temporal validity
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Impact
    decision_criticality: Mapped[float] = mapped_column(Float, default=0.0)

    # Provenance
    created_by_agent: Mapped[str | None] = mapped_column(String(100))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    crisis: Mapped[Optional["Crisis"]] = relationship("Crisis", back_populates="claims")
    evidence_links: Mapped[list] = relationship(
        "ClaimEvidenceLink", back_populates="claim"
    )


class Contradiction(Base, UUIDMixin, TimestampMixin):
    """Detected contradiction between claims or evidence."""

    __tablename__ = "contradictions"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )
    claim_a_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id"), nullable=True
    )
    claim_b_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id"), nullable=True
    )

    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="detected", nullable=False)
    severity: Mapped[float] = mapped_column(Float, default=0.5)
    is_decision_critical: Mapped[bool] = mapped_column(default=False)

    # Resolution
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(100))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class Uncertainty(Base, UUIDMixin, TimestampMixin):
    """Tracked uncertainty about a claim or situation aspect."""

    __tablename__ = "uncertainties"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id"), nullable=True
    )

    description: Mapped[str] = mapped_column(Text, nullable=False)
    uncertainty_score: Mapped[float] = mapped_column(Float, default=0.5)
    impact_if_wrong: Mapped[str | None] = mapped_column(Text)
    acquisition_strategy: Mapped[str | None] = mapped_column(String(100))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
