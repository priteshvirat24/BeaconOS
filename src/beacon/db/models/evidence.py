"""Evidence model — immutable evidence items with source provenance."""

from __future__ import annotations

import uuid
from datetime import datetime

from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from beacon.db.base import Base, TimestampMixin, UUIDMixin


class Evidence(Base, UUIDMixin, TimestampMixin):
    """Immutable evidence item. Content must never be mutated after creation.

    Corrections create new evidence and contest/invalidate related claims.
    """

    __tablename__ = "evidence"

    crisis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crises.id"), nullable=True
    )

    # Source identification
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    source_external_id: Mapped[str | None] = mapped_column(String(500), index=True)
    source_uri: Mapped[str | None] = mapped_column(String(2000))
    slack_permalink: Mapped[str | None] = mapped_column(String(2000))
    slack_channel_id: Mapped[str | None] = mapped_column(String(50))
    slack_message_ts: Mapped[str | None] = mapped_column(String(50))
    slack_thread_ts: Mapped[str | None] = mapped_column(String(50))

    # Content
    raw_content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    normalized_content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_artifact_ref: Mapped[str | None] = mapped_column(String(2000))

    # Attribution
    author: Mapped[str | None] = mapped_column(String(255))
    author_type: Mapped[str | None] = mapped_column(String(50))

    # Temporal
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Geographic scope
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geographic_scope: Mapped[str | None] = mapped_column(String(500))

    # Scoring
    reliability_score: Mapped[float] = mapped_column(Float, default=0.5)
    freshness_score: Mapped[float] = mapped_column(Float, default=1.0)

    # Access scope
    access_scope: Mapped[str | None] = mapped_column(String(255))
    is_redacted: Mapped[bool] = mapped_column(Boolean, default=False)

    # Ingestion trace
    ingestion_trace_id: Mapped[str | None] = mapped_column(String(64))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    crisis: Mapped[Optional["Crisis"]] = relationship("Crisis", back_populates="evidence_items")
    claim_links: Mapped[list[ClaimEvidenceLink]] = relationship(back_populates="evidence")


class ClaimEvidenceLink(Base, UUIDMixin, TimestampMixin):
    """Links claims to their supporting or contradicting evidence."""

    __tablename__ = "claim_evidence_links"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id"), nullable=False
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(
        String(50), nullable=False  # "supports" | "contradicts" | "weakens"
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_by_agent: Mapped[str | None] = mapped_column(String(100))

    evidence: Mapped[Evidence] = relationship(back_populates="claim_links")
    claim: Mapped["Claim"] = relationship("Claim", back_populates="evidence_links")
