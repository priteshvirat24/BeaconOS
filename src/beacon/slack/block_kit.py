"""Beacon Command — Block Kit Builder.

Composable Block Kit surface builders for all 20 required Slack surfaces.
Avoids giant raw JSON dictionaries throughout handlers.
"""

from __future__ import annotations

from typing import Any

# --- Unified severity visual system -----------------------------------------
# Single source of truth for severity color-coding, applied uniformly across
# hazard alerts, situation briefs, the Mission Timeline, and App Home.
SEVERITY_EMOJI: dict[str, str] = {
    "extreme": "🔴",
    "severe": "🟠",
    "high": "🟡",
    "moderate": "🟢",
    "low": "⚪",
}


def severity_emoji(severity: str) -> str:
    """Return the uniform color chip for a severity label."""
    return SEVERITY_EMOJI.get((severity or "").lower(), "⚪")


def severity_label_for_score(score: float | None) -> str:
    """Map a 0-10 severity score to a severity label (matches ingestion bands)."""
    if score is None:
        return "moderate"
    if score >= 8:
        return "extreme"
    if score >= 6:
        return "severe"
    if score >= 4:
        return "high"
    if score >= 2:
        return "moderate"
    return "low"


class BlockBuilder:
    """Fluent builder for Slack Block Kit blocks."""

    def __init__(self) -> None:
        self._blocks: list[dict[str, Any]] = []

    def header(self, text: str) -> BlockBuilder:
        self._blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": text[:150], "emoji": True},
        })
        return self

    def section(self, text: str, *, accessory: dict[str, Any] | None = None) -> BlockBuilder:
        block: dict[str, Any] = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": text[:3000]},
        }
        if accessory:
            block["accessory"] = accessory
        self._blocks.append(block)
        return self

    def fields(self, field_pairs: list[tuple[str, str]]) -> BlockBuilder:
        fields = []
        for label, value in field_pairs[:10]:
            fields.append({"type": "mrkdwn", "text": f"*{label}*\n{value}"})
        self._blocks.append({"type": "section", "fields": fields})
        return self

    def divider(self) -> BlockBuilder:
        self._blocks.append({"type": "divider"})
        return self

    def context(self, text: str) -> BlockBuilder:
        self._blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": text[:3000]}],
        })
        return self

    def _create_card(
        self,
        title: str,
        body: str,
        *,
        subtitle: str | None = None,
        actions: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        blocks = []
        
        # Build premium callout layout using unicode borders & blockquotes
        mrkdwn_text = f"> 📍 *{title[:150]}*\n"
        if subtitle:
            mrkdwn_text += f"> _Subtitle: {subtitle}_\n"
        mrkdwn_text += f"> ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        body_lines = body.split("\n")
        for line in body_lines:
            mrkdwn_text += f"> {line}\n"
            
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": mrkdwn_text}
        })
        
        if actions:
            blocks.append({
                "type": "actions",
                "elements": actions
            })
        return blocks

    def card(
        self,
        title: str,
        body: str,
        *,
        subtitle: str | None = None,
        actions: list[dict[str, Any]] | None = None,
    ) -> BlockBuilder:
        self._blocks.extend(self._create_card(title, body, subtitle=subtitle, actions=actions))
        self._blocks.append({"type": "divider"})
        return self

    def carousel(self, cards: list[list[dict[str, Any]]]) -> BlockBuilder:
        for idx, card_blocks in enumerate(cards):
            if idx > 0:
                self._blocks.append({"type": "divider"})
            self._blocks.extend(card_blocks)
        return self

    def alert(self, text: str, level: str = "warning") -> BlockBuilder:
        emoji_map = {
            "error": "🚨 *CRITICAL ALERT*",
            "warning": "⚠️ *WARNING ALERT*",
            "success": "✅ *SUCCESS REPORT*",
            "info": "ℹ️ *SYSTEM UPDATE*",
            "default": "📢 *NOTICE BRIEF*"
        }
        prefix = emoji_map.get(level.lower(), "📢 *NOTICE BRIEF*")
        
        # Build premium callout layout for alert
        mrkdwn_text = f"> {prefix}\n> ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        body_lines = text.split("\n")
        for line in body_lines:
            mrkdwn_text += f"> {line}\n"
            
        self._blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": mrkdwn_text}
        })
        self._blocks.append({"type": "divider"})
        return self

    def actions(self, buttons: list[dict[str, Any]]) -> BlockBuilder:
        self._blocks.append({"type": "actions", "elements": buttons})
        return self

    def button(
        self,
        text: str,
        action_id: str,
        *,
        value: str = "",
        style: str | None = None,
        confirm: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        btn: dict[str, Any] = {
            "type": "button",
            "text": {"type": "plain_text", "text": text[:75], "emoji": True},
            "action_id": action_id,
            "value": value,
        }
        if style in ("primary", "danger"):
            btn["style"] = style
        if confirm:
            btn["confirm"] = confirm
        return btn

    def build(self) -> list[dict[str, Any]]:
        return self._blocks


# --- Pre-built Surface Builders ---

def hazard_alert_blocks(
    title: str,
    hazard_type: str,
    severity: str,
    magnitude: float | None,
    location: str,
    event_time: str,
    source: str,
    crisis_id: str,
) -> list[dict[str, Any]]:
    """Build hazard alert Block Kit surface."""
    chip = severity_emoji(severity)
    
    # Map severity to alert level
    alert_level = "info"
    if severity.lower() == "extreme":
        alert_level = "error"
    elif severity.lower() in ("severe", "high"):
        alert_level = "warning"

    b = BlockBuilder()
    b.alert(
        text=f"🚨 *{severity.upper()} Hazard Alert:* {title[:100]}",
        level=alert_level
    )
    
    body = (
        f"*Magnitude:* {magnitude if magnitude else 'N/A'}\n"
        f"*Location:* {location}\n"
        f"*Time:* {event_time}\n"
        f"*Source:* {source}"
    )
    
    b.card(
        title=f"{chip} {hazard_type.replace('_', ' ').title()}",
        subtitle=f"Crisis ID: {crisis_id}",
        body=body,
        actions=[
            b.button("🔍 Investigate", "investigate_hazard", value=crisis_id, style="primary"),
            b.button("📋 Create Crisis", "create_crisis", value=crisis_id),
            b.button("🔕 Dismiss", "dismiss_hazard", value=crisis_id),
        ]
    )
    return b.build()


def situation_brief_blocks(
    crisis_title: str,
    status: str,
    summary: str,
    evidence_count: int,
    verified_claims: int,
    contested_claims: int,
    critical_gaps: int,
    active_tasks: int,
    crisis_id: str,
) -> list[dict[str, Any]]:
    """Build situation brief Block Kit surface."""
    status_emoji = {
        "active": "🔴", "monitoring": "🟡", "stabilizing": "🟢",
        "resolved": "✅", "detected": "⚠️",
    }.get(status.lower(), "⚪")

    alert_level = "info"
    if status.lower() in ("active", "detected"):
        alert_level = "warning"
    elif status.lower() == "resolved":
        alert_level = "success"

    b = BlockBuilder()
    b.alert(
        text=f"📊 *Crisis Briefing Updated* · Status: {status.upper()}",
        level=alert_level
    )

    body = (
        f"{summary[:1500]}\n\n"
        f"*Current Metrics:*\n"
        f"· *Evidence collected:* {evidence_count}\n"
        f"· *Verified Claims:* {verified_claims} · *Contested Claims:* {contested_claims}\n"
        f"· *Critical Gaps:* {critical_gaps} identified\n"
        f"· *Active Tasks:* {active_tasks} in progress"
    )

    b.card(
        title=f"{status_emoji} {crisis_title[:100]}",
        subtitle="Mission Situation Brief",
        body=body,
        actions=[
            b.button("📊 Full Situation", "view_situation", value=crisis_id, style="primary"),
            b.button("🔍 Evidence", "view_evidence", value=crisis_id),
            b.button("📋 Tasks", "view_tasks", value=crisis_id),
            b.button("⚠️ Gaps", "view_gaps", value=crisis_id),
        ]
    )
    return b.build()


def intelligence_request_blocks(
    question: str,
    why_needed: str,
    crisis_title: str,
    urgency: str,
    request_id: str,
) -> list[dict[str, Any]]:
    """Build intelligence request Block Kit surface."""
    urgency_emoji = {"critical": "🔴", "high": "🟠", "normal": "🟡", "low": "🟢"}.get(
        urgency.lower(), "🟡"
    )

    alert_level = "info"
    if urgency.lower() == "critical":
        alert_level = "error"
    elif urgency.lower() == "high":
        alert_level = "warning"

    b = BlockBuilder()
    b.alert(
        text=f"🤔 *New Intelligence Request* · Urgency: {urgency.upper()}",
        level=alert_level
    )

    body = (
        f"*Question:*\n{question}\n\n"
        f"*Why Needed:*\n{why_needed}"
    )

    b.card(
        title=f"{urgency_emoji} Info Required",
        subtitle=f"Crisis: {crisis_title}",
        body=body,
        actions=[
            b.button("✅ Provide Update", "provide_intel_update", value=request_id, style="primary"),
            b.button("👤 Assign", "assign_intel_request", value=request_id),
            b.button("❌ Unable to Verify", "unable_to_verify", value=request_id),
            b.button("⬆️ Escalate", "escalate_intel_request", value=request_id),
        ]
    )
    return b.build()


def approval_request_blocks(
    action_description: str,
    rationale: str,
    risks: str,
    authority_required: str,
    approval_id: str,
) -> list[dict[str, Any]]:
    """Build approval request Block Kit surface."""
    b = BlockBuilder()
    b.alert(
        text="🔐 *Authorization Required* · Action needs human verification",
        level="warning"
    )

    body = (
        f"*Action to Authorize:*\n{action_description}\n\n"
        f"*Rationale:*\n{rationale}"
    )
    if risks:
        body += f"\n\n*Identified Risks:*\n{risks}"

    b.card(
        title="Approve Operational Write",
        subtitle=f"Required Authority: {authority_required}",
        body=body,
        actions=[
            b.button("✅ Approve", "approve_action", value=approval_id, style="primary"),
            b.button("❌ Reject", "reject_action", value=approval_id, style="danger"),
            b.button("✏️ Modify", "modify_action", value=approval_id),
        ]
    )
    return b.build()


def task_card_blocks(
    title: str,
    status: str,
    assigned_to: str,
    deadline: str | None,
    priority: str,
    task_id: str,
) -> list[dict[str, Any]]:
    """Build task card Block Kit surface."""
    status_emoji = {
        "in_progress": "🔵", "completed": "✅", "blocked": "🔴",
        "at_risk": "🟠", "overdue": "⚠️", "assigned": "🟡",
    }.get(status.lower(), "⚪")

    b = BlockBuilder()
    body_text = f"Assigned: {assigned_to}\nDeadline: {deadline or 'None'} | Priority: {priority}"
    
    b.card(
        title=f"{status_emoji} {title}",
        subtitle=f"Status: {status.upper()}",
        body=body_text,
        actions=[
            b.button("▶️ Start", "start_task", value=task_id),
            b.button("✅ Complete", "complete_task", value=task_id, style="primary"),
            b.button("🔴 Block", "block_task", value=task_id, style="danger"),
        ]
    )
    return b.build()


def error_blocks(
    error_title: str,
    error_detail: str,
    degraded_mode: bool = False,
 ) -> list[dict[str, Any]]:
    """Build error/degraded mode Block Kit surface."""
    b = BlockBuilder()
    
    b.alert(
        text=f"*{error_title[:100]}*\n{error_detail[:2000]}",
        level="warning" if degraded_mode else "error"
    )
    
    if degraded_mode:
        b.context("Beacon is operating in degraded mode. Some features may be unavailable.")
    return b.build()


def commitment_confirmation_blocks(
    statement: str,
    committer: str,
    source_link: str,
    commitment_id: str,
) -> list[dict[str, Any]]:
    """Build commitment confirmation Block Kit surface."""
    b = BlockBuilder()
    b.alert(
        text="📌 *Commitment Detected in Chat*",
        level="info"
    )

    b.card(
        title="Commitment Confirmation",
        subtitle=f"By: {committer}",
        body=f"_{statement}_\n\n<{source_link}|View Source Message>",
        actions=[
            b.button("✅ Confirm", "confirm_commitment", value=commitment_id, style="primary"),
            b.button("✏️ Edit", "edit_commitment", value=commitment_id),
            b.button("🚫 Ignore", "ignore_commitment", value=commitment_id),
        ]
    )
    return b.build()


def app_home_blocks(
    active_crises: list[dict[str, Any]],
    pending_approvals: int,
    at_risk_tasks: int,
    overdue_tasks: int,
    active_missions: int,
) -> list[dict[str, Any]]:
    """Build App Home command center Block Kit surface."""
    b = BlockBuilder()
    b.header("🛡️ Beacon Command Center")
    b.divider()

    # Summary stats
    b.fields([
        ("Active Crises", str(len(active_crises))),
        ("Pending Approvals", str(pending_approvals)),
        ("At-Risk Tasks", str(at_risk_tasks)),
        ("Overdue Tasks", str(overdue_tasks)),
        ("Active Missions", str(active_missions)),
        ("System Status", "🟢 Operational"),
    ])
    b.divider()

    if active_crises:
        b.section("*Active Crises* — swipe to explore")
        ordered = sorted(
            active_crises[:10],
            key=lambda c: c.get("severity_score", 0.0),
            reverse=True,
        )
        
        cards = []
        for crisis in ordered:
            chip = severity_emoji(crisis.get("severity", ""))
            score = crisis.get("severity_score", 0.0)
            
            body = (
                f"Status: {crisis['status'].upper()}\n"
                f"Severity: {chip} {crisis.get('severity', '').upper()} ({score:.1f})\n"
                f"Evidence Items: {crisis.get('evidence_count', 0)} · Tasks: {crisis.get('task_count', 0)}"
            )
            
            card = b._create_card(
                title=f"{chip} {crisis['title'][:60]}",
                subtitle="Active Crisis Details",
                body=body,
                actions=[
                    b.button("📊 Open", f"open_crisis_{crisis['id']}", value=str(crisis["id"])),
                    b.button(
                        "🛰️ Mission Timeline",
                        "view_mission_timeline",
                        value=str(crisis["id"]),
                        style="primary",
                    ),
                ]
            )
            cards.append(card)
            
        b.carousel(cards)
    else:
        b.section("_No active crises. Beacon is monitoring hazard feeds._")

    return b.build()
