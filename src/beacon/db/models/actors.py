"""Actor, Volunteer, and Capability models."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from beacon.db.base import Base, TimestampMixin, UUIDMixin


class Actor(Base, UUIDMixin, TimestampMixin):
    """Any person or organization involved in crisis response."""

    __tablename__ = "actors"

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(100), nullable=False)  # person, organization, team
    slack_user_id: Mapped[str | None] = mapped_column(String(50), index=True)
    email: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(255))
    organization_name: Mapped[str | None] = mapped_column(String(500))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    capabilities: Mapped[list | None] = mapped_column(JSONB)
    contact_info: Mapped[dict | None] = mapped_column(JSONB)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class Volunteer(Base, UUIDMixin, TimestampMixin):
    """Volunteer who has opted in through configured channels."""

    __tablename__ = "volunteers"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True
    )
    slack_user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    availability_status: Mapped[str] = mapped_column(String(50), default="available")
    skills: Mapped[list | None] = mapped_column(JSONB)
    location: Mapped[str | None] = mapped_column(String(500))
    opted_in_at: Mapped[str | None] = mapped_column(String(50))  # Slack message ts
    opted_in_channel: Mapped[str | None] = mapped_column(String(50))

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)


class Capability(Base, UUIDMixin, TimestampMixin):
    """Verified capability of an actor or resource."""

    __tablename__ = "capabilities"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True
    )
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resources.id"), nullable=True
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
