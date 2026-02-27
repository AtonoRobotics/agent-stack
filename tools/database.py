# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
Async & sync database layer for the agent-stack metrics store.

Uses aiosqlite for async operations and sqlite3 for synchronous
initialization and sync wrapper helpers.  All tables are created
automatically on import.
"""

import os
import sqlite3
import asyncio
from datetime import datetime, timedelta, timezone

import aiosqlite

DB_PATH = os.path.expanduser("/home/samuel/agent-stack/data/metrics.db")

_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS simulation_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        robot TEXT, timestamp TEXT, scene TEXT,
        result TEXT, path_error REAL,
        manipulability REAL, cycle_time REAL,
        safety_pass INTEGER, notes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS training_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        robot TEXT, policy_name TEXT,
        started TEXT, completed TEXT,
        epochs INTEGER, final_loss REAL,
        val_loss REAL, dataset_size INTEGER,
        status TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS deployment_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        robot_serial TEXT, policy_version TEXT,
        deployed_at TEXT, deployed_by TEXT,
        machine TEXT, status TEXT,
        rollback_available INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS performance_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        robot_serial TEXT, timestamp TEXT,
        metric_name TEXT, value REAL,
        units TEXT, source TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fleet_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        machine TEXT, timestamp TEXT,
        gpu_util REAL, gpu_vram_used REAL,
        gpu_vram_total REAL, ram_used REAL,
        ram_total REAL, temp_c REAL,
        disk_used REAL, disk_total REAL,
        status TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent TEXT, task TEXT,
        started TEXT, completed TEXT,
        model_used TEXT, success INTEGER,
        tokens_saved INTEGER, retries INTEGER,
        notes TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS incidents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        robot_serial TEXT, timestamp TEXT,
        severity TEXT, description TEXT,
        resolved INTEGER, resolution TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, category TEXT,
        machine TEXT, robot TEXT,
        agent TEXT, message TEXT, level TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS demo_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        demo_id TEXT NOT NULL,
        started TEXT NOT NULL,
        completed TEXT,
        status TEXT DEFAULT 'running',
        mode TEXT DEFAULT 'headless',
        exit_code INTEGER,
        metrics_json TEXT,
        log_tail TEXT,
        launched_by TEXT
    )
    """,
]


def init_db():
    """Synchronous initialization -- creates the data directory, DB file, and all tables."""
    db_dir = os.path.dirname(DB_PATH)
    os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    try:
        for ddl in _TABLES_SQL:
            conn.execute(ddl)
        conn.commit()
    finally:
        conn.close()


async def insert(table: str, data: dict) -> int:
    """Insert a single row into *table* from *data* and return the new row id."""
    columns = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
    values = tuple(data.values())

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(sql, values)
        await db.commit()
        return cursor.lastrowid


async def query(sql: str, params: tuple = ()) -> list:
    """Execute arbitrary SQL and return a list of dicts (one per row)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_recent(table: str, n: int = 100) -> list:
    """Return the most recent *n* rows from *table*, ordered by id DESC."""
    sql = f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?"
    return await query(sql, (n,))


async def get_time_series(
    table: str, metric: str, robot: str, hours: int = 24
) -> list:
    """
    Retrieve time-series data from the performance_metrics table.

    Filters by *metric_name* and *robot_serial* for rows whose timestamp
    falls within the last *hours* hours.  Results are ordered oldest-first
    so they are ready for plotting.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    sql = (
        f"SELECT * FROM {table} "
        "WHERE metric_name = ? AND robot_serial = ? AND timestamp >= ? "
        "ORDER BY timestamp ASC"
    )
    return await query(sql, (metric, robot, cutoff))


# ── Sync wrappers for non-async contexts ─────────────────────────────────

def _run_async(coro):
    """Run an async coroutine from synchronous code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        return asyncio.run(coro)
    else:
        # Already inside an event loop -- spin up a thread so we don't block.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()


def insert_sync(table: str, data: dict) -> int:
    """Synchronous wrapper around :func:`insert`."""
    return _run_async(insert(table, data))


def query_sync(sql: str, params: tuple = ()) -> list:
    """Synchronous wrapper around :func:`query`."""
    return _run_async(query(sql, params))


# ── Auto-initialise on first import ──────────────────────────────────────
init_db()

if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)
