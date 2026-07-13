"""Beacon Command — Approval Manager.

Manages policy-gated approval workflows for operational actions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy import select, update

from beacon.db import get_session
from beacon.db.models.decisions import Approval
from beacon.events import event_publisher
from beacon.logging import get_logger

logger = get_logger(__name__)


class ApprovalManager:
    """Manages approval workflows for policy-gated actions."""

    async def request_approval(
        self,
        action: str,
        target_object_type: str,
        target_object_id: uuid.UUID,
        authority_required: str,
        *,
        crisis_id: Optional[uuid.UUID] = None,
        state_version: Optional[int] = None,
        expiration_minutes: int = 60,
    ) -> uuid.UUID:
        """Create an approval request."""
        async with get_session() as session:
            approval = Approval(
                crisis_id=crisis_id,
                action=action,
                target_object_type=target_object_type,
                target_object_id=target_object_id,
                state_version=state_version,
                authority_required=authority_required,
                decision="pending",
                expiration=datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes),
            )
            session.add(approval)
            await session.flush()

            await event_publisher.publish(
                "approval.requested",
                {
                    "approval_id": str(approval.id),
                    "action": action,
                    "target_type": target_object_type,
                    "authority_required": authority_required,
                },
                crisis_id=crisis_id,
            )

            return approval.id

    async def grant_approval(
        self,
        approval_id: uuid.UUID,
        approver_slack_id: str,
        approver_name: str,
        comments: str = "",
    ) -> bool:
        """Grant an approval."""
        async with get_session() as session:
            result = await session.execute(
                select(Approval).where(Approval.id == approval_id)
            )
            approval = result.scalar_one_or_none()
            if not approval or approval.decision != "pending":
                return False

            # Check expiration
            if approval.expiration and datetime.now(timezone.utc) > approval.expiration:
                approval.decision = "expired"
                return False

            approval.decision = "approved"
            approval.approver_slack_id = approver_slack_id
            approval.approver_name = approver_name
            approval.comments = comments
            approval.decided_at = datetime.now(timezone.utc)

            await event_publisher.publish(
                "approval.granted",
                {
                    "approval_id": str(approval_id),
                    "approver": approver_name,
                },
                crisis_id=approval.crisis_id,
                actor_type="human",
                actor_id=approver_slack_id,
            )

            return True

    async def reject_approval(
        self,
        approval_id: uuid.UUID,
        approver_slack_id: str,
        approver_name: str,
        comments: str = "",
    ) -> bool:
        """Reject an approval."""
        async with get_session() as session:
            result = await session.execute(
                select(Approval).where(Approval.id == approval_id)
            )
            approval = result.scalar_one_or_none()
            if not approval or approval.decision != "pending":
                return False

            approval.decision = "rejected"
            approval.approver_slack_id = approver_slack_id
            approval.approver_name = approver_name
            approval.comments = comments
            approval.decided_at = datetime.now(timezone.utc)

            await event_publisher.publish(
                "approval.rejected",
                {
                    "approval_id": str(approval_id),
                    "approver": approver_name,
                    "reason": comments,
                },
                crisis_id=approval.crisis_id,
                actor_type="human",
                actor_id=approver_slack_id,
            )

            return True

    async def get_pending_approvals(
        self, crisis_id: Optional[uuid.UUID] = None
    ) -> list[dict[str, Any]]:
        """Get all pending approvals."""
        async with get_session() as session:
            query = select(Approval).where(Approval.decision == "pending")
            if crisis_id:
                query = query.where(Approval.crisis_id == crisis_id)
            result = await session.execute(query.order_by(Approval.created_at.desc()))
            approvals = result.scalars().all()

        return [
            {
                "id": str(a.id),
                "action": a.action,
                "target_type": a.target_object_type,
                "authority_required": a.authority_required,
                "expiration": a.expiration.isoformat() if a.expiration else None,
            }
            for a in approvals
        ]


approval_manager = ApprovalManager()
