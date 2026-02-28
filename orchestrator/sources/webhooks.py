# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Webhook event source.

Provides FastAPI routes that can be mounted on the dashboard to receive
external triggers (GitHub webhooks, manual triggers from UI, etc.).
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from orchestrator.bus import EventBus
from orchestrator.events import OrchestratorEvent, EventPriority

logger = logging.getLogger("orchestrator.sources.webhooks")

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])

# Module-level bus reference (set during init)
_bus: EventBus | None = None


def init_webhook_routes(bus: EventBus) -> APIRouter:
    """Initialize webhook routes with event bus reference."""
    global _bus
    _bus = bus
    return router


class TriggerRequest(BaseModel):
    task: str
    priority: int = EventPriority.NORMAL
    source: str = "webhook"


class EventResponse(BaseModel):
    event_id: str
    status: str


@router.post("/trigger", response_model=EventResponse)
async def trigger_event(req: TriggerRequest):
    """Trigger an orchestrator event from the dashboard or external source."""
    if _bus is None:
        raise HTTPException(status_code=503, detail="Orchestrator not running")

    event = OrchestratorEvent(
        priority=req.priority,
        source=req.source,
        event_type="user_trigger",
        payload={"task": req.task},
    )
    await _bus.put(event)
    logger.info(f"Webhook trigger: {event.id[:8]} — {req.task[:100]}")

    return EventResponse(event_id=event.id, status="queued")


@router.get("/events")
async def get_events(limit: int = 50):
    """Get recent orchestrator events."""
    from orchestrator.persistence import EventStore
    store = EventStore()
    await store.init()
    events = await store.get_recent_events(limit=limit)
    await store.close()
    return events


@router.get("/events/{event_id}/conversation")
async def get_conversation(event_id: str):
    """Get the agent conversation for a specific event."""
    from orchestrator.persistence import EventStore
    store = EventStore()
    await store.init()
    messages = await store.get_event_conversations(event_id)
    await store.close()
    return messages


@router.get("/stats")
async def get_stats():
    """Get orchestrator statistics."""
    from orchestrator.persistence import EventStore
    store = EventStore()
    await store.init()
    stats = await store.get_stats()
    await store.close()

    if _bus:
        stats["bus"] = _bus.stats

    return stats


@router.get("/status")
async def get_status():
    """Get orchestrator running status."""
    return {
        "running": _bus is not None,
        "bus_stats": _bus.stats if _bus else None,
    }
