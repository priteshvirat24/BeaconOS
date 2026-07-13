"""Decision API endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from beacon.db import get_session
from beacon.db.models.decisions import Decision
from sqlalchemy import select

router = APIRouter()


class DecisionResponse(BaseModel):
    id: uuid.UUID
    crisis_id: uuid.UUID
    decision: str
    rationale: str
    status: str
    approved_by: Optional[str] = None

    model_config = {"from_attributes": True}


@router.get("", response_model=list[DecisionResponse])
async def list_decisions(
    crisis_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, le=200),
) -> list[DecisionResponse]:
    """List decisions."""
    async with get_session() as session:
        query = select(Decision).order_by(Decision.created_at.desc())
        if crisis_id:
            query = query.where(Decision.crisis_id == crisis_id)
        result = await session.execute(query.limit(limit))
        items = result.scalars().all()
    return [DecisionResponse.model_validate(d) for d in items]
