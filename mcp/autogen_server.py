#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""MCP Server for the Alpha Robotics Agent Stack.

Exposes agent capabilities as MCP tools via stdio transport.
"""

import os
import sys
import re
import json
import asyncio
import logging
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agent-stack"))


def _extract_path(text: str, extensions: tuple = (".urdf", ".yaml", ".yml", ".py", ".json")) -> str | None:
    """Extract a file path from text, verify it exists."""
    # Match paths like ~/foo/bar.ext or /foo/bar.ext
    for match in re.finditer(r'([~/][\w./_-]+(?:' + '|'.join(re.escape(e) for e in extensions) + r'))', text):
        path = os.path.expanduser(match.group(1))
        if os.path.exists(path):
            return path
    return None


def _extract_paths(text: str, extensions: tuple = (".urdf",)) -> list[str]:
    """Extract multiple file paths from text."""
    paths = []
    for match in re.finditer(r'([~/][\w./_-]+(?:' + '|'.join(re.escape(e) for e in extensions) + r'))', text):
        path = os.path.expanduser(match.group(1))
        if os.path.exists(path):
            paths.append(path)
    return paths


def _format_result(result: dict) -> str:
    """Format a skill result dict as readable text."""
    if isinstance(result, dict):
        return json.dumps(result, indent=2, default=str)
    return str(result)

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
    task_lower = task.lower()

    # Route to skill methods instead of raw LLM
    if any(kw in task_lower for kw in ("fix", "debug", "error")):
        file_path = _extract_path(task + " " + context, (".py", ".js", ".ts", ".yaml", ".yml"))
        if file_path:
            result = await _run_in_thread(agent.fix_error, task, file_path)
            return f"Fix applied to {file_path}:\n{result[:2000]}"

    if "refactor" in task_lower:
        file_path = _extract_path(task + " " + context, (".py", ".js", ".ts"))
        if file_path:
            result = await _run_in_thread(agent.refactor, file_path, task)
            return f"Refactored {file_path}:\n{result[:2000]}"

    # Default: generate_code (still uses LLM but with syntax validation)
    result = await _run_in_thread(agent.generate_code, task, context)
    return result


async def _run_researcher(task: str, context: str) -> str:
    from agents.researcher import ResearcherAgent
    agent = ResearcherAgent()
    return await _run_in_thread(agent.research, task, context)


async def _run_sysadmin(task: str, context: str) -> str:
    from agents.sysadmin import SysadminAgent
    agent = SysadminAgent()
    task_lower = task.lower()
    combined = task + " " + context

    # Route to skill methods instead of raw LLM
    if "git" in task_lower:
        # Extract repo path or default
        repo_path = _extract_path(combined, (".git",))
        if not repo_path:
            # Try common repo paths
            for p in ["~/agent-stack", "~/dobot-cr10-stack", "~/dobot_cr10"]:
                expanded = os.path.expanduser(p)
                if os.path.isdir(os.path.join(expanded, ".git")):
                    repo_path = expanded
                    break
        if repo_path:
            # Determine git action
            action = "status"
            for a in ("pull", "push", "diff", "log", "fetch", "branch", "checkout", "commit"):
                if a in task_lower:
                    action = a
                    break
            result = await _run_in_thread(agent.git_operation, action, repo_path)
            return _format_result(result)

    if "docker" in task_lower:
        # Determine action and container
        action = "ps"
        container = ""
        for a in ("start", "stop", "restart", "rm", "rmi", "logs", "inspect", "pull"):
            if a in task_lower:
                action = a
                break
        # Extract container name (word after action keyword)
        match = re.search(r'(?:container|image)\s+(\S+)', task_lower)
        if match:
            container = match.group(1)
        # Detect machine name
        machine = "local"
        for m in agent.fleet_config:
            if m in task_lower:
                machine = m
                break
        result = await _run_in_thread(agent.manage_docker, action, container, machine)
        return _format_result(result)

    if any(kw in task_lower for kw in ("service", "systemctl")):
        action = "status"
        for a in ("start", "stop", "restart", "enable", "disable"):
            if a in task_lower:
                action = a
                break
        # Extract service name
        match = re.search(r'(?:service|systemctl\s+\w+)\s+(\S+)', task_lower)
        service = match.group(1) if match else ""
        if not service:
            # Try to find a .service name
            match = re.search(r'(\S+\.service)', task_lower)
            service = match.group(1) if match else "unknown"
        machine = "local"
        for m in agent.fleet_config:
            if m in task_lower:
                machine = m
                break
        result = await _run_in_thread(agent.manage_service, action, service, machine)
        return _format_result(result)

    if any(kw in task_lower for kw in ("deploy", "fleet")):
        machines = None
        for m in agent.fleet_config:
            if m in task_lower:
                if machines is None:
                    machines = []
                machines.append(m)
        result = await _run_in_thread(agent.deploy_to_fleet, task, machines)
        return _format_result(result)

    # Check if a specific machine is mentioned -> execute_on_machine
    for machine_name in agent.fleet_config:
        if machine_name in task_lower:
            result = await _run_in_thread(agent.execute_on_machine, task, machine_name)
            return result

    # Fallback: LLM for planning/advice (no file access needed)
    knowledge = agent.load_knowledge(agent.task_type)
    prompt = f"Fleet:\n{json.dumps(agent.fleet_config, indent=2)}\n\nKnowledge:\n{knowledge}\n\nContext: {context}\n\nTask: {task}\n\nProvide specific commands. Flag destructive operations."
    result = await _run_in_thread(agent.query_with_retry, prompt)
    agent.log_task(task=task[:200], result=result[:500], model=agent.get_model_info()["model"], success=True)
    return result


async def _run_simulator(task: str, context: str) -> str:
    from agents.simulator import SimulatorAgent
    agent = SimulatorAgent()
    task_lower = task.lower()
    combined = task + " " + context

    # Route to deterministic skill methods
    if any(kw in task_lower for kw in ("parse urdf", "parse_urdf")):
        path = _extract_path(combined, (".urdf",))
        result = await _run_in_thread(agent.parse_urdf, path)
        return _format_result(result)

    if any(kw in task_lower for kw in ("validate urdf", "validate_urdf", "check urdf")):
        path = _extract_path(combined, (".urdf",))
        result = await _run_in_thread(agent.validate_urdf, path)
        return _format_result(result)

    if any(kw in task_lower for kw in ("compare urdf", "compare_urdf", "diff urdf")):
        paths = _extract_paths(combined, (".urdf",))
        result = await _run_in_thread(agent.compare_urdfs, paths if paths else None)
        return _format_result(result)

    if any(kw in task_lower for kw in ("consolidate", "merge urdf")):
        paths = _extract_paths(combined, (".urdf",))
        result = await _run_in_thread(agent.consolidate_urdfs, paths if paths else None)
        return _format_result(result)

    if any(kw in task_lower for kw in ("collision sphere", "collision_sphere")):
        path = _extract_path(combined, (".urdf",))
        result = await _run_in_thread(agent.generate_collision_spheres, path)
        return _format_result(result)

    if "curobo" in task_lower and any(kw in task_lower for kw in ("validate", "check", "verify")):
        config_path = _extract_path(combined, (".yaml", ".yml"))
        urdf_path = _extract_path(combined, (".urdf",))
        result = await _run_in_thread(agent.validate_curobo_config, config_path, urdf_path)
        return _format_result(result)

    if any(kw in task_lower for kw in ("fix", "error", "debug")):
        result = await _run_in_thread(agent.fix_sim_error, combined)
        return f"Auto-fix result: {result}"

    if "template" in task_lower:
        # Extract template name
        match = re.search(r'template\s+(\S+)', task_lower)
        template_name = match.group(1) if match else "default"
        result = await _run_in_thread(agent.run_template, template_name)
        return _format_result(result)

    # Fallback: LLM for open-ended simulation questions
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
    """Trigger an orchestrator event by writing directly to the event database.

    The running orchestrator watches the data/ directory via FileSystemWatcher
    and will pick up new events. We also write a trigger file to ensure detection.
    """
    import uuid
    import aiosqlite
    DB_PATH = os.path.expanduser("~/agent-stack/data/metrics.db")
    TRIGGER_DIR = os.path.expanduser("~/agent-stack/data")

    try:
        event_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        payload = json.dumps({"task": task, "source": "claude_code"})

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute(
                """INSERT INTO orchestrator_events
                   (id, source, event_type, priority, timestamp, payload, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, "mcp", "manual_trigger", priority, now, payload, "pending", now),
            )
            await db.commit()

        # Touch a trigger file so the orchestrator's FileSystemWatcher detects the change
        trigger_path = os.path.join(TRIGGER_DIR, "mcp_trigger.flag")
        with open(trigger_path, "w") as f:
            f.write(f"{event_id}\n{task}\n{now}\n")

        logger.info(f"Orchestrator event queued: {event_id[:8]} priority={priority} task={task[:100]}")
        return f"Event queued: {event_id}\nPriority: {priority}\nTask: {task}\nStatus: pending\n\nThe orchestrator will pick this up and route it to the appropriate agent team."
    except Exception as e:
        return f"Error triggering orchestrator: {e}"


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
