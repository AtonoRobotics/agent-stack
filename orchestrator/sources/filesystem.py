# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Filesystem watcher event source using watchdog.

Monitors specified directories for file changes and emits events.
"""

import os
import asyncio
import logging

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

from orchestrator.bus import EventBus
from orchestrator.events import OrchestratorEvent, EventPriority

logger = logging.getLogger("orchestrator.sources.filesystem")

BASE_DIR = os.path.expanduser("~/agent-stack")


class _EventHandler(FileSystemEventHandler):
    """Watchdog handler that queues events into an asyncio-safe list."""

    def __init__(self):
        self.pending: list[dict] = []
        self._lock = asyncio.Lock  # Not used since watchdog is threaded

    # Ignore database files, logs, and temp files
    IGNORE_SUFFIXES = (".db", ".db-wal", ".db-shm", ".log", ".pyc", ".swp", ".tmp")

    def _should_ignore(self, path: str) -> bool:
        return any(path.endswith(s) for s in self.IGNORE_SUFFIXES)

    def on_modified(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self.pending.append({
            "type": "file_modified",
            "path": event.src_path,
        })

    def on_created(self, event):
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self.pending.append({
            "type": "file_created",
            "path": event.src_path,
        })


class FileSystemWatcher:
    """Watches directories for changes and emits orchestrator events."""

    def __init__(self, bus: EventBus, paths: list[str] | None = None):
        self.bus = bus
        self.paths = [os.path.join(BASE_DIR, p) for p in (paths or ["config/"])]
        self._handler = _EventHandler()
        self._observer = Observer()
        # Debounce: ignore rapid-fire events for same file
        self._last_event: dict[str, float] = {}
        self._debounce_seconds = 5.0

    async def run(self):
        """Start watching and periodically drain pending events."""
        for path in self.paths:
            if os.path.isdir(path):
                self._observer.schedule(self._handler, path, recursive=True)
                logger.info(f"Watching directory: {path}")

        self._observer.start()
        logger.info(f"FileSystemWatcher started ({len(self.paths)} paths)")

        try:
            while True:
                await asyncio.sleep(2)  # Check every 2 seconds

                # Drain pending events from the watchdog thread
                if not self._handler.pending:
                    continue

                events = self._handler.pending[:]
                self._handler.pending.clear()

                import time
                now = time.time()

                for evt in events:
                    path = evt["path"]

                    # Debounce
                    if path in self._last_event:
                        if now - self._last_event[path] < self._debounce_seconds:
                            continue
                    self._last_event[path] = now

                    rel_path = os.path.relpath(path, BASE_DIR)
                    event_type = evt["type"]

                    # Determine priority based on file type
                    priority = EventPriority.NORMAL
                    if rel_path.startswith("config/"):
                        priority = EventPriority.HIGH

                    await self.bus.put(OrchestratorEvent(
                        priority=priority,
                        source="filesystem",
                        event_type=event_type,
                        payload={
                            "path": rel_path,
                            "full_path": path,
                            "task": f"File {event_type.replace('file_', '')}: {rel_path}. Review the change and verify it's valid.",
                        },
                    ))
                    logger.info(f"File event: {event_type} {rel_path}")

        finally:
            self._observer.stop()
            self._observer.join()
