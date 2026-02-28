# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""SQLite persistence for orchestrator events and agent conversations.

Uses aiosqlite for async writes. Tables are created via migration 003.
"""

import os
import json
import logging
from datetime import datetime

import aiosqlite

from orchestrator.events import OrchestratorEvent

logger = logging.getLogger("orchestrator.persistence")

DB_PATH = os.path.expanduser("~/agent-stack/data/metrics.db")


class EventStore:
    """Async persistence layer for orchestrator events."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        """Open database connection and ensure tables exist."""
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")

        # Create tables if migration hasn't run yet
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS orchestrator_events (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                event_type TEXT NOT NULL,
                priority INTEGER DEFAULT 50,
                timestamp TEXT NOT NULL,
                payload TEXT,
                status TEXT DEFAULT 'pending',
                assigned_agents TEXT,
                messages TEXT,
                result TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS agent_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                message TEXT NOT NULL,
                tool_calls TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES orchestrator_events(id)
            )
        """)
        await self._db.commit()
        logger.info("EventStore initialized")

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def log_event(
        self,
        event: OrchestratorEvent,
        status: str = "pending",
        assigned_agents: list[str] | None = None,
        messages: list[dict] | None = None,
        result: str | None = None,
    ):
        """Log or update an orchestrator event."""
        now = datetime.now().isoformat()

        # Check if event already exists (update vs insert)
        cursor = await self._db.execute(
            "SELECT id FROM orchestrator_events WHERE id = ?", (event.id,)
        )
        existing = await cursor.fetchone()

        if existing:
            # Update existing event
            updates = ["status = ?"]
            params = [status]

            if assigned_agents is not None:
                updates.append("assigned_agents = ?")
                params.append(json.dumps(assigned_agents))
            if messages is not None:
                updates.append("messages = ?")
                params.append(json.dumps(messages))
            if result is not None:
                updates.append("result = ?")
                params.append(result)
            if status in ("completed", "failed", "timeout"):
                updates.append("completed_at = ?")
                params.append(now)

            params.append(event.id)
            await self._db.execute(
                f"UPDATE orchestrator_events SET {', '.join(updates)} WHERE id = ?",
                params,
            )
        else:
            # Insert new event
            await self._db.execute(
                """INSERT INTO orchestrator_events
                   (id, source, event_type, priority, timestamp, payload, status,
                    assigned_agents, messages, result, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.source,
                    event.event_type,
                    event.priority,
                    event.timestamp.isoformat(),
                    json.dumps(event.payload),
                    status,
                    json.dumps(assigned_agents) if assigned_agents else None,
                    json.dumps(messages) if messages else None,
                    result,
                    now,
                ),
            )

        await self._db.commit()

    async def log_conversation(
        self,
        event_id: str,
        agent_name: str,
        message: str,
        tool_calls: list[dict] | None = None,
    ):
        """Log an individual agent message in a conversation."""
        await self._db.execute(
            """INSERT INTO agent_conversations (event_id, agent_name, message, tool_calls)
               VALUES (?, ?, ?, ?)""",
            (event_id, agent_name, message[:5000], json.dumps(tool_calls) if tool_calls else None),
        )
        await self._db.commit()

    async def get_recent_events(self, limit: int = 50) -> list[dict]:
        """Get recent orchestrator events."""
        cursor = await self._db.execute(
            """SELECT id, source, event_type, priority, timestamp, status,
                      assigned_agents, result, created_at, completed_at
               FROM orchestrator_events
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    async def get_event_conversations(self, event_id: str) -> list[dict]:
        """Get all conversation messages for an event."""
        cursor = await self._db.execute(
            """SELECT agent_name, message, tool_calls, timestamp
               FROM agent_conversations
               WHERE event_id = ?
               ORDER BY id ASC""",
            (event_id,),
        )
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    async def get_stats(self) -> dict:
        """Get orchestrator statistics."""
        cursor = await self._db.execute(
            "SELECT status, COUNT(*) FROM orchestrator_events GROUP BY status"
        )
        status_counts = dict(await cursor.fetchall())

        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM orchestrator_events"
        )
        total = (await cursor.fetchone())[0]

        cursor = await self._db.execute(
            """SELECT COUNT(DISTINCT agent_name) FROM agent_conversations"""
        )
        active_agents = (await cursor.fetchone())[0]

        return {
            "total_events": total,
            "by_status": status_counts,
            "active_agents": active_agents,
        }
