"""Beacon Command — Slack Bolt Application.

Initializes the Slack Bolt app with action handlers, event handlers,
and the App Home tab.
"""

from __future__ import annotations

import uuid
from typing import Any

from beacon.logging import get_logger

logger = get_logger(__name__)


def create_slack_app() -> Any:
    """Create and configure the Slack Bolt app.

    Returns None if Slack is not configured.
    """
    try:
        from beacon.config import get_settings

        settings = get_settings()
        if not settings.is_slack_configured:
            logger.info("slack_not_configured", reason="Missing bot token or signing secret")
            return None

        from slack_bolt.async_app import AsyncApp

        app_kwargs: dict[str, Any] = {
            "token": settings.slack_bot_token,
            "signing_secret": settings.slack_signing_secret,
        }

        # Use Socket Mode if app token is available
        if settings.slack_app_token:
            app_kwargs["token"] = settings.slack_bot_token

        bolt_app = AsyncApp(**app_kwargs)

        # --- Event Handlers ---

        @bolt_app.event("app_home_opened")
        async def handle_app_home(event: dict[str, Any], client: Any) -> None:
            """Render the App Home command center."""
            user_id = event.get("user", "")
            try:
                from sqlalchemy import func, select

                from beacon.db import get_session
                from beacon.db.models.crisis import Crisis
                from beacon.db.models.decisions import Approval
                from beacon.db.models.missions import Mission
                from beacon.db.models.tasks import Task
                from beacon.slack.block_kit import app_home_blocks

                async with get_session() as session:
                    # Active crises
                    crises_r = await session.execute(
                        select(Crisis).where(
                            Crisis.status.in_(["detected", "triaging", "active", "monitoring"])
                        ).order_by(Crisis.severity_score.desc()).limit(10)
                    )
                    crises = crises_r.scalars().all()

                    # Pending approvals
                    approvals_count = (await session.execute(
                        select(func.count()).select_from(Approval).where(
                            Approval.decision == "pending"
                        )
                    )).scalar() or 0

                    # At-risk tasks
                    at_risk = (await session.execute(
                        select(func.count()).select_from(Task).where(
                            Task.status == "at_risk"
                        )
                    )).scalar() or 0

                    # Overdue tasks
                    overdue = (await session.execute(
                        select(func.count()).select_from(Task).where(
                            Task.status == "overdue"
                        )
                    )).scalar() or 0

                    # Active missions
                    missions_count = (await session.execute(
                        select(func.count()).select_from(Mission).where(
                            Mission.status.in_(["running", "scheduled"])
                        )
                    )).scalar() or 0

                active_crises = [
                    {
                        "id": str(c.id),
                        "title": c.title,
                        "status": c.status,
                        "severity": c.severity,
                        "severity_score": c.severity_score or 0.0,
                    }
                    for c in crises
                ]

                blocks = app_home_blocks(
                    active_crises=active_crises,
                    pending_approvals=approvals_count,
                    at_risk_tasks=at_risk,
                    overdue_tasks=overdue,
                    active_missions=missions_count,
                )

                await client.views_publish(
                    user_id=user_id,
                    view={"type": "home", "blocks": blocks},
                )

            except Exception as e:
                logger.error("app_home_error", error=str(e), user_id=user_id)

        @bolt_app.event("message")
        async def handle_message(event: dict[str, Any], say: Any) -> None:
            """Handle incoming messages for commitment detection."""
            # Only process in crisis channels
            channel_id = event.get("channel", "")
            text = event.get("text", "")
            user_id = event.get("user", "")

            if not text or event.get("subtype"):
                return

            logger.debug("slack_message_received", channel=channel_id, user=user_id)

        @bolt_app.event("app_mention")
        async def handle_mention(event: dict, say: Any) -> None:
            """Handle mentions of the bot."""
            user_id = event.get("user", "")
            text = event.get("text", "")
            
            await say(
                text=f"Hello <@{user_id}>! 👋 I am BeaconOS, your Crisis Intelligence & Coordination system.\\n\\nRight now I'm monitoring real-time data feeds in the background. To see the active crisis dashboard and pending approvals, please click on my name and visit the **Home** tab!",
                thread_ts=event.get("ts")
            )
            logger.info("app_mention_handled", user=user_id, text=text)

        # --- Action Handlers ---

        @bolt_app.action("investigate_hazard")
        async def handle_investigate(ack: Any, body: dict[str, Any], client: Any) -> None:
            """Launch the full multi-agent pipeline with a live Mission Timeline."""
            await ack()
            crisis_id = body.get("actions", [{}])[0].get("value", "")
            user_id = body.get("user", {}).get("id", "")
            # Post the timeline into the channel the button was clicked in.
            channel = (
                body.get("channel", {}).get("id")
                or body.get("container", {}).get("channel_id", "")
            )

            logger.info("investigate_hazard_requested", crisis_id=crisis_id, user=user_id)

            try:
                import asyncio

                from beacon.agents.pipeline import run_intelligence_pipeline
                from beacon.slack.mission_timeline import MissionTimelinePublisher

                publisher = (
                    MissionTimelinePublisher(client, channel) if channel else None
                )
                asyncio.create_task(run_intelligence_pipeline(
                    objective=f"Investigate hazard event for crisis {crisis_id}",
                    crisis_id=uuid.UUID(crisis_id) if crisis_id else None,
                    on_stage=publisher,
                ))
            except Exception as e:
                logger.error("investigate_launch_error", error=str(e))

        @bolt_app.action("view_mission_timeline")
        async def handle_view_timeline(ack: Any, body: dict[str, Any], client: Any) -> None:
            """Launch the live Mission Timeline for a crisis from App Home."""
            await ack()
            crisis_id = body.get("actions", [{}])[0].get("value", "")
            user_id = body.get("user", {}).get("id", "")

            # App Home clicks have no channel context; post to the operations
            # channel if configured, else DM the requesting coordinator.
            channel = settings.slack_operations_channel or user_id

            try:
                import asyncio

                from beacon.agents.pipeline import run_intelligence_pipeline
                from beacon.slack.mission_timeline import MissionTimelinePublisher

                publisher = MissionTimelinePublisher(client, channel) if channel else None
                asyncio.create_task(run_intelligence_pipeline(
                    objective=f"Assess and coordinate response for crisis {crisis_id}",
                    crisis_id=uuid.UUID(crisis_id) if crisis_id else None,
                    on_stage=publisher,
                ))
                logger.info("mission_timeline_launched", crisis_id=crisis_id, user=user_id)
            except Exception as e:
                logger.error("mission_timeline_launch_error", error=str(e))

        @bolt_app.action("approve_action")
        async def handle_approve(ack: Any, body: dict[str, Any], client: Any) -> None:
            """Handle approval action."""
            await ack()
            approval_id = body.get("actions", [{}])[0].get("value", "")
            user_id = body.get("user", {}).get("id", "")
            user_name = body.get("user", {}).get("username", "")

            try:
                from beacon.services.approval import approval_manager

                success = await approval_manager.grant_approval(
                    approval_id=uuid.UUID(approval_id),
                    approver_slack_id=user_id,
                    approver_name=user_name,
                )
                if success:
                    channel = body.get("channel", {}).get("id")
                    if channel:
                        await client.chat_postMessage(
                            channel=channel,
                            text=f"✅ Approved by <@{user_id}>",
                        )
            except Exception as e:
                logger.error("approval_error", error=str(e))

        @bolt_app.action("reject_action")
        async def handle_reject(ack: Any, body: dict[str, Any], client: Any) -> None:
            """Handle rejection action."""
            await ack()
            approval_id = body.get("actions", [{}])[0].get("value", "")
            user_id = body.get("user", {}).get("id", "")
            user_name = body.get("user", {}).get("username", "")

            try:
                from beacon.services.approval import approval_manager

                success = await approval_manager.reject_approval(
                    approval_id=uuid.UUID(approval_id),
                    approver_slack_id=user_id,
                    approver_name=user_name,
                )
                if success:
                    channel = body.get("channel", {}).get("id")
                    if channel:
                        await client.chat_postMessage(
                            channel=channel,
                            text=f"❌ Rejected by <@{user_id}>",
                        )
            except Exception as e:
                logger.error("rejection_error", error=str(e))

        @bolt_app.action("confirm_commitment")
        async def handle_confirm_commitment(ack: Any, body: dict[str, Any]) -> None:
            """Handle commitment confirmation."""
            await ack()
            commitment_id = body.get("actions", [{}])[0].get("value", "")
            logger.info("commitment_confirmed", commitment_id=commitment_id)

        @bolt_app.action("start_task")
        async def handle_start_task(ack: Any, body: dict[str, Any]) -> None:
            """Handle task start."""
            await ack()
            task_id = body.get("actions", [{}])[0].get("value", "")
            user_id = body.get("user", {}).get("id", "")

            try:
                from beacon.services.task_manager import task_manager

                await task_manager.update_status(
                    uuid.UUID(task_id), "in_progress",
                    actor_type="human", actor_id=user_id,
                )
            except Exception as e:
                logger.error("task_start_error", error=str(e))

        @bolt_app.action("complete_task")
        async def handle_complete_task(ack: Any, body: dict[str, Any]) -> None:
            """Handle task completion."""
            await ack()
            task_id = body.get("actions", [{}])[0].get("value", "")
            user_id = body.get("user", {}).get("id", "")

            try:
                from beacon.services.task_manager import task_manager

                await task_manager.update_status(
                    uuid.UUID(task_id), "completed",
                    actor_type="human", actor_id=user_id,
                )
            except Exception as e:
                logger.error("task_complete_error", error=str(e))

        @bolt_app.action("provide_intel_update")
        async def handle_intel_update(ack: Any, body: dict[str, Any]) -> None:
            """Handle intelligence update from human."""
            await ack()
            request_id = body.get("actions", [{}])[0].get("value", "")
            logger.info("intel_update_requested", request_id=request_id)

        # Catch-all for unregistered actions
        @bolt_app.action({"type": "block_actions"})
        async def handle_block_actions(ack: Any, body: dict[str, Any]) -> None:
            await ack()
            actions = body.get("actions", [])
            for action in actions:
                logger.debug("unhandled_action", action_id=action.get("action_id"))

        logger.info("slack_bolt_app_created")
        return bolt_app

    except ImportError as e:
        logger.warning("slack_bolt_not_available", error=str(e))
        return None
    except Exception as e:
        logger.error("slack_app_creation_error", error=str(e))
        return None
