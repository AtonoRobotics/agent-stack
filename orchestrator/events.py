# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Event models for the orchestrator."""

from datetime import datetime
from uuid import uuid4
from pydantic import BaseModel, Field


class EventPriority:
    """Priority levels for orchestrator events (lower = higher priority)."""
    CRITICAL = 0    # Safety, e-stop, hardware failure
    HIGH = 10       # Threshold breaches, service down
    NORMAL = 50     # Scheduled tasks, file changes
    LOW = 100       # Cleanup, informational


class OrchestratorEvent(BaseModel):
    """An event that triggers agent processing."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    priority: int = EventPriority.NORMAL
    source: str          # metrics, cron, webhook, filesystem, ros2, dashboard
    event_type: str      # threshold_breach, scheduled_task, file_changed, etc.
    timestamp: datetime = Field(default_factory=datetime.now)
    payload: dict = {}
    requires_approval: bool = False

    def __lt__(self, other: "OrchestratorEvent") -> bool:
        """For PriorityQueue ordering — lower priority number = higher priority."""
        return self.priority < other.priority

    def __le__(self, other: "OrchestratorEvent") -> bool:
        return self.priority <= other.priority

    def to_task_text(self) -> str:
        """Format this event as a task description for the agent team."""
        parts = [f"[{self.source}/{self.event_type}]"]

        if self.payload.get("task"):
            parts.append(self.payload["task"])
        elif self.payload.get("message"):
            parts.append(self.payload["message"])
        else:
            parts.append(f"Handle {self.event_type} event from {self.source}")

        if self.payload.get("machine"):
            parts.append(f"(machine: {self.payload['machine']})")

        if self.payload.get("details"):
            parts.append(f"\nDetails: {self.payload['details']}")

        return " ".join(parts)
