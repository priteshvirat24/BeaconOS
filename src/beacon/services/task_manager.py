"""Beacon Command — Task Manager & Deadline Monitor."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy import select, and_

from beacon.db import get_session
from beacon.db.models.tasks import Task
from beacon.events import event_publisher
from beacon.logging import get_logger

logger = get_logger(__name__)


class TaskManager:
    """Manages operational task lifecycle."""

    async def create_task(
        self,
        crisis_id: uuid.UUID,
        title: str,
        *,
        description: Optional[str] = None,
        plan_id: Optional[uuid.UUID] = None,
        commitment_id: Optional[uuid.UUID] = None,
        assigned_name: Optional[str] = None,
        assigned_slack_user_id: Optional[str] = None,
        deadline: Optional[datetime] = None,
        priority: float = 0.5,
    ) -> uuid.UUID:
        """Create an operational task."""
        async with get_session() as session:
            task = Task(
                crisis_id=crisis_id,
                title=title,
                description=description,
                plan_id=plan_id,
                commitment_id=commitment_id,
                assigned_name=assigned_name,
                assigned_slack_user_id=assigned_slack_user_id,
                deadline=deadline,
                priority=priority,
                status="proposed",
            )
            session.add(task)
            await session.flush()

            await event_publisher.publish(
                "task.created",
                {"task_id": str(task.id), "title": title},
                crisis_id=crisis_id,
            )
            return task.id

    async def update_status(
        self,
        task_id: uuid.UUID,
        new_status: str,
        *,
        actor_type: str = "system",
        actor_id: str = "beacon",
    ) -> bool:
        """Update task status with event publishing."""
        async with get_session() as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return False

            old_status = task.status
            task.status = new_status
            task.version += 1

            if new_status == "in_progress" and not task.started_at:
                task.started_at = datetime.now(timezone.utc)
            elif new_status in ("completed", "verified"):
                task.completed_at = datetime.now(timezone.utc)

            event_type = f"task.{new_status}" if f"task.{new_status}" in (
                "task.assigned", "task.started", "task.blocked",
                "task.at_risk", "task.overdue", "task.completed", "task.verified"
            ) else "task.created"

            await event_publisher.publish(
                event_type,
                {"task_id": str(task_id), "old_status": old_status, "new_status": new_status},
                crisis_id=task.crisis_id,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            return True

    async def get_at_risk_tasks(self, look_ahead_minutes: int = 60) -> list[dict[str, Any]]:
        """Find tasks approaching their deadlines."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(minutes=look_ahead_minutes)

        async with get_session() as session:
            result = await session.execute(
                select(Task).where(
                    and_(
                        Task.deadline.isnot(None),
                        Task.deadline <= cutoff,
                        Task.status.in_(["assigned", "in_progress"]),
                    )
                ).order_by(Task.deadline.asc())
            )
            tasks = result.scalars().all()

        return [
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "deadline": t.deadline.isoformat() if t.deadline else None,
                "assigned_to": t.assigned_name,
                "minutes_remaining": round((t.deadline - now).total_seconds() / 60) if t.deadline else None,
                "crisis_id": str(t.crisis_id) if t.crisis_id else None,
            }
            for t in tasks
        ]

    async def get_overdue_tasks(self) -> list[dict[str, Any]]:
        """Find overdue tasks."""
        now = datetime.now(timezone.utc)

        async with get_session() as session:
            result = await session.execute(
                select(Task).where(
                    and_(
                        Task.deadline.isnot(None),
                        Task.deadline < now,
                        Task.status.in_(["assigned", "in_progress", "at_risk"]),
                    )
                ).order_by(Task.deadline.asc())
            )
            tasks = result.scalars().all()

        at_risk = []
        for t in tasks:
            at_risk.append({
                "id": str(t.id),
                "title": t.title,
                "status": t.status,
                "deadline": t.deadline.isoformat() if t.deadline else None,
                "overdue_minutes": round((now - t.deadline).total_seconds() / 60) if t.deadline else 0,
                "crisis_id": str(t.crisis_id) if t.crisis_id else None,
            })

            # Auto-escalate status
            if t.status != "overdue":
                t.status = "overdue"
                t.version += 1

        return at_risk


task_manager = TaskManager()


class DeadlineMonitor:
    """Periodic monitor for task deadlines."""

    async def check_deadlines(self) -> dict[str, Any]:
        """Run deadline check and return summary."""
        at_risk = await task_manager.get_at_risk_tasks(look_ahead_minutes=30)
        overdue = await task_manager.get_overdue_tasks()

        if overdue:
            logger.warning(
                "deadline_monitor_overdue",
                count=len(overdue),
                tasks=[t["title"] for t in overdue[:5]],
            )

        if at_risk:
            logger.info(
                "deadline_monitor_at_risk",
                count=len(at_risk),
            )

        return {
            "at_risk_count": len(at_risk),
            "overdue_count": len(overdue),
            "at_risk_tasks": at_risk,
            "overdue_tasks": overdue,
        }


deadline_monitor = DeadlineMonitor()
