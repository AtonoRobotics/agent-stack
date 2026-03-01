#!/usr/bin/env python3
"""MCP Server for the Alpha Robotics Agent Stack.

Exposes AutoGen agent teams as MCP tools via stdio transport.
"""

import os
import sys
import json
import asyncio
import logging
import sqlite3
import uuid
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agent-stack"))

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from agents.teams import run_team

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_PATH = os.path.expanduser("~/agent-stack/logs/mcp_server.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [MCP] %(levelname)s: %(message)s",
)
logger = logging.getLogger("mcp_server")

DB_PATH = os.path.expanduser("~/agent-stack/data/metrics.db")

server = Server("agent-stack")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

AGENT_TOOLS = [
    ("agent__develop", "Code generation, debugging, and refactoring for the robotics stack. Uses qwen2.5-coder:32b on DGX Spark (FREE, local inference)."),
    ("agent__research", "Documentation lookup, compatibility research, dependency resolution. Uses qwen2.5:72b on DGX Spark (FREE, local inference)."),
    ("agent__sysadmin", "Fleet management, Docker, systemd, git operations. Destructive actions require approval. Uses qwen2.5:72b on DGX Spark (FREE)."),
    ("agent__simulate", "Isaac Sim scene management, cuRobo trajectory planning, simulation data collection. Uses qwen2.5:72b on DGX Spark (FREE)."),
    ("agent__cosmos", "Cosmos world model inference, synthetic environment generation. Uses qwen2.5:72b on DGX Spark (FREE)."),
    ("agent__groot", "GR00T N1.6 training, Isaac Lab RL, dataset preparation, policy evaluation. Uses qwen2.5:72b on DGX Spark (FREE)."),
    ("agent__monitor", "Check fleet health, GPU utilization, temperatures, disk usage, service status across all machines."),
    ("agent__fleet", "Execute commands across the fleet of machines. Specify target machines or 'all'."),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    tool_list = []

    # Agent tools
    for name, description in AGENT_TOOLS:
        schema = {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The task to perform"},
            },
            "required": ["task"],
        }
        if name != "agent__monitor":
            schema["properties"]["context"] = {
                "type": "string",
                "description": "Additional context",
                "default": "",
            }
        if name == "agent__fleet":
            schema["properties"]["machines"] = {
                "type": "string",
                "description": "Comma-separated machine names or 'all'",
                "default": "all",
            }
        tool_list.append(types.Tool(name=name, description=description, inputSchema=schema))

    # Status tool
    tool_list.append(types.Tool(
        name="agent__status",
        description="Get full status of the agent stack: machine health, loaded models, active tasks, recent alerts.",
        inputSchema={"type": "object", "properties": {}},
    ))

    # Orchestrator tools
    tool_list.append(types.Tool(
        name="orchestrator__trigger",
        description="Trigger an orchestrator event — sends a task to the autonomous agent team for processing.",
        inputSchema={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The task to process"},
                "priority": {"type": "integer", "description": "Priority (0=critical, 50=normal, 100=low)", "default": 50},
            },
            "required": ["task"],
        },
    ))
    tool_list.append(types.Tool(
        name="orchestrator__status",
        description="Get orchestrator status: event queue, recent events, active agents.",
        inputSchema={"type": "object", "properties": {}},
    ))
    tool_list.append(types.Tool(
        name="orchestrator__events",
        description="Get recent orchestrator events and their outcomes.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of events to return", "default": 20},
            },
        },
    ))

    return tool_list


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    logger.info(f"Tool call: {name} args={json.dumps(arguments)[:200]}")
    try:
        if name.startswith("agent__"):
            result = await asyncio.wait_for(_handle_agent(name, arguments), timeout=180)
        elif name == "orchestrator__trigger":
            result = await _orchestrator_trigger(arguments.get("task", ""), arguments.get("priority", 50))
        elif name == "orchestrator__status":
            result = await _orchestrator_status()
        elif name == "orchestrator__events":
            result = await _orchestrator_events(arguments.get("limit", 20))
        else:
            result = f"Unknown tool: {name}"
        logger.info(f"Tool {name} completed successfully")
        return [types.TextContent(type="text", text=result)]
    except asyncio.TimeoutError:
        error_msg = f"Tool {name} timed out after 180s"
        logger.error(error_msg)
        return [types.TextContent(type="text", text=error_msg)]
    except Exception as e:
        error_msg = f"Error in {name}: {e}"
        logger.error(error_msg)
        return [types.TextContent(type="text", text=error_msg)]


async def _handle_agent(name: str, arguments: dict) -> str:
    """Route agent__ tools to AutoGen teams."""
    if name == "agent__status":
        return await _get_status()

    agent_type = name.replace("agent__", "")
    task = arguments.get("task", "")
    context = arguments.get("context", "")

    if not task:
        return "Error: 'task' parameter is required."

    # For fleet agent, prepend machine targets
    if agent_type == "fleet":
        machines = arguments.get("machines", "all")
        task = f"Target machines: {machines}\n\n{task}"

    prompt = f"{task}\n\nContext: {context}" if context else task
    return await run_team(agent_type, prompt)


async def _get_status() -> str:
    """Get agent stack status from local checks + database."""
    from agents.tools import check_fleet_health, check_ollama_status

    lines = ["# Alpha Agent Stack Status", f"Timestamp: {datetime.now().isoformat()}", ""]

    # Fleet health (quick local check)
    try:
        health = check_fleet_health()
        lines.append(health)
    except Exception as e:
        lines.append(f"## Fleet: Error - {e}")
    lines.append("")

    # Ollama models
    for label, machine in [("Workstation", "workstation"), ("DGX Spark", "dgx-spark")]:
        try:
            status = check_ollama_status(machine)
            lines.append(f"## {label}: {status}")
        except Exception as e:
            lines.append(f"## {label}: Error - {e}")
    lines.append("")

    # Recent tasks from DB
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT agent, task, model_used, success, completed FROM agent_tasks ORDER BY id DESC LIMIT 10"
        ).fetchall()
        conn.close()
        lines.append(f"## Recent Tasks ({len(rows)})")
        for row in rows:
            st = "OK" if row["success"] else "FAIL"
            lines.append(f"  [{st}] {row['agent']}: {row['task'][:60]} ({row['model_used']})")
    except Exception as e:
        lines.append(f"## Tasks: {e}")
    lines.append("")

    # Recent alerts
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT timestamp, message, level FROM activity_log WHERE category='alert' ORDER BY id DESC LIMIT 5"
        ).fetchall()
        conn.close()
        if rows:
            lines.append(f"## Alerts ({len(rows)})")
            for row in rows:
                lines.append(f"  [{row['level']}] {row['timestamp']}: {row['message'][:80]}")
        else:
            lines.append("## Alerts: None")
    except Exception:
        lines.append("## Alerts: No data")

    return "\n".join(lines)


async def _orchestrator_trigger(task: str, priority: int) -> str:
    """Queue an orchestrator event in the database."""
    try:
        event_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        payload = json.dumps({"task": task, "source": "claude_code"})

        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """INSERT INTO orchestrator_events
               (id, source, event_type, priority, timestamp, payload, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, "mcp", "manual_trigger", priority, now, payload, "pending", now),
        )
        conn.commit()
        conn.close()

        # Touch trigger file for FileSystemWatcher
        trigger_path = os.path.expanduser("~/agent-stack/data/mcp_trigger.flag")
        with open(trigger_path, "w") as f:
            f.write(f"{event_id}\n{task}\n{now}\n")

        return f"Event queued: {event_id}\nPriority: {priority}\nTask: {task}\nStatus: pending"
    except Exception as e:
        return f"Error triggering orchestrator: {e}"


async def _orchestrator_status() -> str:
    """Get orchestrator status from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        total = conn.execute("SELECT COUNT(*) as c FROM orchestrator_events").fetchone()["c"]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as c FROM orchestrator_events GROUP BY status"
        ).fetchall()
        conn.close()

        lines = ["# Orchestrator Status", "", f"Total events: {total}", "", "By status:"]
        for row in by_status:
            lines.append(f"  {row['status']}: {row['c']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


async def _orchestrator_events(limit: int) -> str:
    """Get recent orchestrator events."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM orchestrator_events ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()

        if not rows:
            return "No orchestrator events found."

        lines = [f"# Recent Events ({len(rows)})", ""]
        for row in rows:
            lines.append(f"  [{row['status']}] {row['source']}/{row['event_type']} (p={row['priority']})")
            if row.get("result"):
                lines.append(f"    Result: {str(row['result'])[:100]}")
            lines.append(f"    Created: {row['created_at']}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    logger.info("Starting Alpha Agent Stack MCP Server (AutoGen v0.4)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
