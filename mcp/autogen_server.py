#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""MCP Server for the Alpha Robotics Agent Stack.

Exposes agent capabilities as MCP tools via stdio transport.
"""

import os
import sys
import json
import asyncio
import logging
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agent-stack"))

from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

LOG_PATH = os.path.expanduser("~/agent-stack/logs/mcp_server.log")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [MCP] %(levelname)s: %(message)s",
)
logger = logging.getLogger("mcp_server")

server = Server("agent-stack")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="agent__develop",
            description="Code generation, debugging, and refactoring for the robotics stack. Uses qwen2.5-coder:32b on DGX Spark (FREE, local inference).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The development task to perform"},
                    "context": {"type": "string", "description": "Additional context or file contents", "default": ""},
                },
                "required": ["task"],
            },
        ),
        types.Tool(
            name="agent__research",
            description="Documentation lookup, compatibility research, dependency resolution. Uses qwen2.5:72b on DGX Spark (FREE, local inference).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The research question or task"},
                    "context": {"type": "string", "description": "Additional context", "default": ""},
                },
                "required": ["task"],
            },
        ),
        types.Tool(
            name="agent__sysadmin",
            description="Fleet management, Docker, systemd, git operations. Destructive actions require approval. Uses qwen2.5:72b on DGX Spark (FREE).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The sysadmin task to perform"},
                    "context": {"type": "string", "description": "Additional context", "default": ""},
                },
                "required": ["task"],
            },
        ),
        types.Tool(
            name="agent__simulate",
            description="Isaac Sim scene management, cuRobo trajectory planning, simulation data collection. Uses qwen2.5:72b on DGX Spark (FREE).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The simulation task"},
                    "context": {"type": "string", "description": "Additional context", "default": ""},
                },
                "required": ["task"],
            },
        ),
        types.Tool(
            name="agent__cosmos",
            description="Cosmos world model inference, synthetic environment generation. Uses qwen2.5:72b on DGX Spark (FREE).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The Cosmos/world model task"},
                    "context": {"type": "string", "description": "Additional context", "default": ""},
                },
                "required": ["task"],
            },
        ),
        types.Tool(
            name="agent__groot",
            description="GR00T N1.6 training, Isaac Lab RL, dataset preparation, policy evaluation. Uses qwen2.5:72b on DGX Spark (FREE).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The training/GR00T task"},
                    "context": {"type": "string", "description": "Additional context", "default": ""},
                },
                "required": ["task"],
            },
        ),
        types.Tool(
            name="agent__monitor",
            description="Check fleet health, GPU utilization, temperatures, disk usage, service status across all machines.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "What to monitor or check"},
                },
                "required": ["task"],
            },
        ),
        types.Tool(
            name="agent__fleet",
            description="Execute commands across the fleet of machines. Specify target machines or 'all'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The fleet operation to perform"},
                    "machines": {"type": "string", "description": "Comma-separated machine names or 'all'", "default": "all"},
                },
                "required": ["task"],
            },
        ),
        types.Tool(
            name="agent__status",
            description="Get full status of the agent stack: machine health, loaded models, active tasks, recent alerts.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
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
        ),
        types.Tool(
            name="orchestrator__status",
            description="Get orchestrator status: event queue, recent events, active agents.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="orchestrator__events",
            description="Get recent orchestrator events and their outcomes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of events to return", "default": 20},
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    logger.info(f"Tool call: {name} with args: {json.dumps(arguments)[:200]}")
    try:
        if name == "agent__develop":
            result = await _run_developer(arguments.get("task", ""), arguments.get("context", ""))
        elif name == "agent__research":
            result = await _run_researcher(arguments.get("task", ""), arguments.get("context", ""))
        elif name == "agent__sysadmin":
            result = await _run_sysadmin(arguments.get("task", ""), arguments.get("context", ""))
        elif name == "agent__simulate":
            result = await _run_simulator(arguments.get("task", ""), arguments.get("context", ""))
        elif name == "agent__cosmos":
            result = await _run_cosmos(arguments.get("task", ""), arguments.get("context", ""))
        elif name == "agent__groot":
            result = await _run_groot(arguments.get("task", ""), arguments.get("context", ""))
        elif name == "agent__monitor":
            result = await _run_monitor(arguments.get("task", ""))
        elif name == "agent__fleet":
            result = await _run_fleet(arguments.get("task", ""), arguments.get("machines", "all"))
        elif name == "agent__status":
            result = await _get_status()
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
    except Exception as e:
        error_msg = f"Error in {name}: {str(e)}"
        logger.error(error_msg)
        return [types.TextContent(type="text", text=error_msg)]


async def _run_in_thread(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


async def _run_developer(task: str, context: str) -> str:
    from agents.developer import DeveloperAgent
    agent = DeveloperAgent()
    knowledge = agent.load_knowledge(agent.task_type)
    prompt = f"Knowledge:\n{knowledge}\n\nContext:\n{context}\n\nTask: {task}\n\nProvide complete, production-quality code."
    result = await _run_in_thread(agent.query_with_retry, prompt)
    agent.log_task(task=task[:200], result=result[:500], model=agent.get_model_info()["model"], success=True)
    return result


async def _run_researcher(task: str, context: str) -> str:
    from agents.researcher import ResearcherAgent
    agent = ResearcherAgent()
    return await _run_in_thread(agent.research, task, context)


async def _run_sysadmin(task: str, context: str) -> str:
    from agents.sysadmin import SysadminAgent
    agent = SysadminAgent()
    knowledge = agent.load_knowledge(agent.task_type)
    prompt = f"Fleet:\n{json.dumps(agent.fleet_config, indent=2)}\n\nKnowledge:\n{knowledge}\n\nContext: {context}\n\nTask: {task}\n\nProvide specific commands. Flag destructive operations."
    result = await _run_in_thread(agent.query_with_retry, prompt)
    agent.log_task(task=task[:200], result=result[:500], model=agent.get_model_info()["model"], success=True)
    return result


async def _run_simulator(task: str, context: str) -> str:
    from agents.simulator import SimulatorAgent
    agent = SimulatorAgent()
    knowledge = agent.load_knowledge(agent.task_type)
    prompt = f"Knowledge:\n{knowledge}\n\nContext: {context}\n\nTask: {task}\n\nProvide Isaac Sim / cuRobo code and configuration."
    result = await _run_in_thread(agent.query_with_retry, prompt)
    agent.log_task(task=task[:200], result=result[:500], model=agent.get_model_info()["model"], success=True)
    return result


async def _run_cosmos(task: str, context: str) -> str:
    from agents.cosmos import CosmosAgent
    agent = CosmosAgent()
    knowledge = agent.load_knowledge(agent.task_type)
    prompt = f"Knowledge:\n{knowledge}\n\nContext: {context}\n\nTask: {task}"
    result = await _run_in_thread(agent.query_with_retry, prompt)
    agent.log_task(task=task[:200], result=result[:500], model=agent.get_model_info()["model"], success=True)
    return result


async def _run_groot(task: str, context: str) -> str:
    from agents.groot import GrootAgent
    agent = GrootAgent()
    knowledge = agent.load_knowledge(agent.task_type)
    prompt = f"Knowledge:\n{knowledge}\n\nContext: {context}\n\nTask: {task}"
    result = await _run_in_thread(agent.query_with_retry, prompt)
    agent.log_task(task=task[:200], result=result[:500], model=agent.get_model_info()["model"], success=True)
    return result


async def _run_monitor(task: str) -> str:
    from agents.monitor import MonitorAgent
    agent = MonitorAgent()
    metrics = await _run_in_thread(agent.check_all_machines)
    agent.write_metrics(metrics)
    alerts = agent.evaluate_alerts(metrics)

    lines = ["# Fleet Health Report", f"Timestamp: {datetime.now().isoformat()}", ""]
    for machine_name, m in metrics.items():
        status = m.get("status", "unknown")
        icon = "OK" if status == "online" else "ALERT"
        lines.append(f"## {machine_name} [{icon}]")
        if m.get("gpu_util") is not None:
            lines.append(f"  GPU: {m['gpu_util']:.0f}% | VRAM: {m.get('gpu_vram_used', 0):.1f}/{m.get('gpu_vram_total', 0):.1f} GB | Temp: {m.get('temp_c', 0):.0f}C")
        if m.get("ram_used") is not None:
            lines.append(f"  RAM: {m['ram_used']:.1f}/{m.get('ram_total', 0):.1f} GB")
        if m.get("disk_used") is not None:
            lines.append(f"  Disk: {m['disk_used']:.1f}/{m.get('disk_total', 0):.1f} GB")
        lines.append(f"  Ollama: {m.get('ollama_status', 'unknown')}")
        lines.append("")
    if alerts:
        lines.append("## Alerts")
        for severity, machine, msg in alerts:
            lines.append(f"  [{severity}] {machine}: {msg}")
    else:
        lines.append("No active alerts.")
    return "\n".join(lines)


async def _run_fleet(task: str, machines: str) -> str:
    from agents.sysadmin import SysadminAgent
    agent = SysadminAgent()
    if machines == "all":
        target_machines = list(agent.fleet_config.keys())
    else:
        target_machines = [m.strip() for m in machines.split(",")]
    knowledge = agent.load_knowledge(agent.task_type)
    prompt = f"Fleet:\n{json.dumps(agent.fleet_config, indent=2)}\nTargets: {target_machines}\n\nTask: {task}\n\nProvide exact commands per machine."
    result = await _run_in_thread(agent.query_with_retry, prompt)
    agent.log_task(task=f"fleet:{task[:150]}", result=result[:500], model=agent.get_model_info()["model"], success=True)
    return result


async def _get_status() -> str:
    from tools.database import DB_PATH
    lines = ["# Alpha Agent Stack Status", f"Timestamp: {datetime.now().isoformat()}", ""]

    try:
        from agents.monitor import MonitorAgent
        monitor = MonitorAgent()
        metrics = await _run_in_thread(monitor.check_all_machines)
        online = sum(1 for m in metrics.values() if m.get("status") == "online")
        lines.append(f"## Fleet: {online}/{len(metrics)} machines online")
        for name, m in metrics.items():
            s = "ONLINE" if m.get("status") == "online" else "OFFLINE"
            lines.append(f"  {name}: {s}")
        lines.append("")
    except Exception as e:
        lines.append(f"## Fleet: Error - {e}\n")

    try:
        from tools.ollama import list_models, check_health
        for host_name, host_addr in [("DGX Spark", "spark-2b53.local"), ("Workstation", "localhost")]:
            healthy = await check_health(host_addr)
            if healthy:
                models = await list_models(host_addr)
                lines.append(f"## Models on {host_name}: {len(models)} loaded")
                for m in models:
                    lines.append(f"  - {m}")
            else:
                lines.append(f"## Models on {host_name}: Ollama not responding")
            lines.append("")
    except Exception as e:
        lines.append(f"## Models: Error - {e}\n")

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT agent, task, model_used, success, completed FROM agent_tasks ORDER BY id DESC LIMIT 10").fetchall()
        conn.close()
        lines.append(f"## Recent Tasks: {len(rows)}")
        for row in rows:
            st = "OK" if row["success"] else "FAIL"
            lines.append(f"  [{st}] {row['agent']}: {row['task'][:60]} ({row['model_used']})")
        lines.append("")
    except Exception as e:
        lines.append(f"## Tasks: Error - {e}\n")

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT timestamp, message, level FROM activity_log WHERE category='alert' ORDER BY id DESC LIMIT 5").fetchall()
        conn.close()
        if rows:
            lines.append(f"## Recent Alerts: {len(rows)}")
            for row in rows:
                lines.append(f"  [{row['level']}] {row['timestamp']}: {row['message'][:80]}")
        else:
            lines.append("## Alerts: None")
    except Exception:
        lines.append("## Alerts: No data")

    return "\n".join(lines)


async def _orchestrator_trigger(task: str, priority: int) -> str:
    """Trigger an orchestrator event via the webhook API."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "http://localhost:8080/api/orchestrator/trigger",
                json={"task": task, "priority": priority},
            )
            if resp.status_code == 200:
                data = resp.json()
                return f"Event queued: {data['event_id']} (status: {data['status']})"
            return f"Error: HTTP {resp.status_code} — {resp.text}"
    except Exception as e:
        return f"Error triggering orchestrator: {e}\n(Is the dashboard running on port 8080?)"


async def _orchestrator_status() -> str:
    """Get orchestrator status from the database."""
    try:
        from orchestrator.persistence import EventStore
        store = EventStore()
        await store.init()
        stats = await store.get_stats()
        await store.close()

        lines = ["# Orchestrator Status", ""]
        lines.append(f"Total events: {stats['total_events']}")
        lines.append(f"Active agents: {stats['active_agents']}")
        lines.append("")
        lines.append("Events by status:")
        for status, count in stats.get("by_status", {}).items():
            lines.append(f"  {status}: {count}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error getting orchestrator status: {e}"


async def _orchestrator_events(limit: int) -> str:
    """Get recent orchestrator events."""
    try:
        from orchestrator.persistence import EventStore
        store = EventStore()
        await store.init()
        events = await store.get_recent_events(limit=limit)
        await store.close()

        if not events:
            return "No orchestrator events found."

        lines = [f"# Recent Orchestrator Events ({len(events)})", ""]
        for evt in events:
            lines.append(f"  [{evt['status']}] {evt['source']}/{evt['event_type']} (priority={evt['priority']})")
            if evt.get('result'):
                lines.append(f"    Result: {evt['result'][:100]}")
            lines.append(f"    Created: {evt['created_at']}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error getting orchestrator events: {e}"


async def main():
    logger.info("Starting Alpha Agent Stack MCP Server")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
