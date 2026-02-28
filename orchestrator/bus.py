# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Event bus using asyncio.PriorityQueue.

Events are prioritized: lower priority number = higher urgency.
The bus provides backpressure via max_size.
"""

import asyncio
import logging
from orchestrator.events import OrchestratorEvent

logger = logging.getLogger("orchestrator.bus")


class EventBus:
    """Priority queue-based event bus for the orchestrator."""

    def __init__(self, max_size: int = 500):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        self._total_events = 0
        self._dropped_events = 0

    async def put(self, event: OrchestratorEvent):
        """Add an event to the bus. Drops event if queue is full."""
        try:
            self._queue.put_nowait(event)
            self._total_events += 1
            logger.debug(f"Event queued: {event.id[:8]} [{event.source}/{event.event_type}] priority={event.priority}")
        except asyncio.QueueFull:
            self._dropped_events += 1
            logger.warning(f"Event dropped (queue full): {event.id[:8]} [{event.source}/{event.event_type}]")

    async def get(self) -> OrchestratorEvent:
        """Get the highest-priority event from the bus (blocks until available)."""
        return await self._queue.get()

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def stats(self) -> dict:
        return {
            "queue_size": self.size,
            "total_events": self._total_events,
            "dropped_events": self._dropped_events,
        }
