"""Mission API endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from beacon.db import get_session
from beacon.db.models.missions import Mission
from sqlalchemy import select

router = APIRouter()


class MissionResponse(BaseModel):
    id: uuid.UUID
    crisis_id: Optional[uuid.UUID] = None
    objective: str
    mission_type: str
    status: str
    priority: float
    assigned_agent: Optional[str] = None
    attempt_count: int

    model_config = {"from_attributes": True}


@router.get("", response_model=list[MissionResponse])
async def list_missions(
    crisis_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
) -> list[MissionResponse]:
    """List missions."""
    async with get_session() as session:
        query = select(Mission).order_by(Mission.created_at.desc())
        if crisis_id:
            query = query.where(Mission.crisis_id == crisis_id)
        if status:
            query = query.where(Mission.status == status)
        result = await session.execute(query.limit(limit))
        items = result.scalars().all()
    return [MissionResponse.model_validate(m) for m in items]
