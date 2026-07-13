"""Beacon Command — Domain Event Publisher.

Persists domain events to PostgreSQL append-only log and optionally publishes to Redis.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import insert

from beacon.db import get_session
from beacon.db.models.events import DomainEvent
from beacon.logging import get_logger

logger = get_logger(__name__)


class DomainEventPublisher:
    """Publishes domain events to the append-only event log."""

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        crisis_id: Optional[uuid.UUID] = None,
        actor_type: str = "system",
        actor_id: str = "beacon",
        causation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        state_version_before: Optional[int] = None,
        state_version_after: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> uuid.UUID:
        """Persist a domain event.

        Args:
            event_type: Event type string (e.g., 'crisis.created').
            payload: Typed event payload.
            crisis_id: Associated crisis ID.
            actor_type: Type of actor (system, agent, human).
            actor_id: Identifier of the actor.
            causation_id: ID of the event that caused this one.
            correlation_id: Shared ID for correlated events.
            trace_id: Distributed trace ID.
            state_version_before: World model version before change.
            state_version_after: World model version after change.
            metadata: Additional metadata.

        Returns:
            The event ID.
        """
        event_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        async with get_session() as session:
            await session.execute(
                insert(DomainEvent).values(
                    id=event_id,
                    crisis_id=crisis_id,
                    event_type=event_type,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    timestamp=now,
                    causation_id=causation_id,
                    correlation_id=correlation_id or str(uuid.uuid4()),
                    trace_id=trace_id,
                    state_version_before=state_version_before,
                    state_version_after=state_version_after,
                    payload=payload,
                    metadata_=metadata or {},
                )
            )

        # Optional Redis pub/sub notification
        try:
            from beacon.services.redis import get_redis

            redis = get_redis()
            await redis.publish(
                f"beacon:events:{event_type}",
                str(event_id),
            )
        except Exception:
            pass  # Redis is optional for events

        logger.debug(
            "domain_event_published",
            event_id=str(event_id),
            event_type=event_type,
            crisis_id=str(crisis_id) if crisis_id else None,
        )

        return event_id


# Singleton instance
event_publisher = DomainEventPublisher()
