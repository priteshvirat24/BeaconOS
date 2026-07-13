"""Domain event stream endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from beacon.db import get_session
from beacon.db.models.events import DomainEvent
from sqlalchemy import select

router = APIRouter()


class DomainEventResponse(BaseModel):
    id: uuid.UUID
    crisis_id: Optional[uuid.UUID] = None
    event_type: str
    actor_type: str
    actor_id: str
    timestamp: str
    correlation_id: Optional[str] = None
    payload: dict

    model_config = {"from_attributes": True}


@router.get("", response_model=list[DomainEventResponse])
async def list_events(
    crisis_id: Optional[uuid.UUID] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
) -> list[DomainEventResponse]:
    """List domain events with optional filters."""
    async with get_session() as session:
        query = select(DomainEvent).order_by(DomainEvent.timestamp.desc())
        if crisis_id:
            query = query.where(DomainEvent.crisis_id == crisis_id)
        if event_type:
            query = query.where(DomainEvent.event_type == event_type)
        result = await session.execute(query.limit(limit).offset(offset))
        items = result.scalars().all()
    return [DomainEventResponse.model_validate(e) for e in items]
