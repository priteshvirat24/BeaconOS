"""Plan API endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from beacon.db import get_session
from beacon.db.models.plans import ResponsePlan
from sqlalchemy import select

router = APIRouter()


class PlanResponse(BaseModel):
    id: uuid.UUID
    crisis_id: uuid.UUID
    objective: str
    status: str
    version: int

    model_config = {"from_attributes": True}


@router.get("", response_model=list[PlanResponse])
async def list_plans(
    crisis_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, le=200),
) -> list[PlanResponse]:
    """List response plans."""
    async with get_session() as session:
        query = select(ResponsePlan).order_by(ResponsePlan.created_at.desc())
        if crisis_id:
            query = query.where(ResponsePlan.crisis_id == crisis_id)
        result = await session.execute(query.limit(limit))
        items = result.scalars().all()
    return [PlanResponse.model_validate(p) for p in items]
