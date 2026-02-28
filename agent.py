#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Mission Control by Alpha - CLI Interface.

Usage:
    agent "your task here"
    agent --agent developer "write code for X"
    agent --status
    agent --dashboard
"""

import os
import sys
import time
import argparse
import webbrowser
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agent-stack"))

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

AGENT_ROUTES = {
    "developer": ["code", "write", "fix", "debug", "refactor", "implement", "function", "class", "test", "script"],
    "researcher": ["research", "find", "docs", "documentation", "compatible", "dependency", "api", "spec", "lookup"],
    "sysadmin": ["docker", "service", "install", "fleet", "git", "ssh", "deploy", "systemd", "apt", "package"],
    "simulator": ["simulate", "simulation", "isaac", "curobo", "trajectory", "urdf", "scene", "physics"],
    "cosmos": ["cosmos", "world model", "synthetic", "wfm", "tokenizer"],
    "groot": ["train", "training", "groot", "policy", "reward", "rl", "reinforcement", "checkpoint", "dataset"],
    "monitor": ["health", "check", "monitor", "status", "temperature", "gpu", "ram", "disk", "alert"],
}


AGENT_DESCRIPTIONS = {
    "developer": "Code generation, debugging, refactoring, writing functions/classes/tests/scripts",
    "researcher": "Documentation lookup, API research, dependency analysis, hardware specs, compatibility checks",
    "sysadmin": "Docker, systemd, SSH, fleet management, package installation, git, deployment",
    "simulator": "Isaac Sim scenes, URDF editing, cuRobo trajectories, physics simulation, digital twin",
    "cosmos": "NVIDIA Cosmos world models, synthetic data generation, tokenizers",
    "groot": "Robot training, RL policies, GR00T, datasets, checkpoints, reward functions",
    "monitor": "Fleet health checks, GPU/RAM/disk monitoring, temperature alerts, machine status",
}


def _route_task_llm(task: str) -> str | None:
    """Use local Ollama (qwen2.5:7b) to classify the task to an agent type."""
    agent_list = "\n".join(f"- {name}: {desc}" for name, desc in AGENT_DESCRIPTIONS.items())
    prompt = (
        f"You are a task router. Given a user task, respond with ONLY the agent name "
        f"that should handle it. Available agents:\n{agent_list}\n\n"
        f"Task: {task}\n\nAgent name:"
    )
    try:
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={"model": "qwen2.5:7b", "prompt": prompt, "stream": False},
            timeout=httpx.Timeout(5.0),
        )
        response.raise_for_status()
        result = response.json().get("response", "").strip().lower()
        # Try exact match first
        if result in AGENT_DESCRIPTIONS:
            return result
        # Try to extract agent name from response
        for name in AGENT_DESCRIPTIONS:
            if name in result:
                return name
        return None
    except Exception:
        return None


def _route_task_keywords(task: str) -> str:
    """Fallback: keyword-based routing."""
    task_lower = task.lower()
    scores = {}
    for agent_name, keywords in AGENT_ROUTES.items():
        score = sum(1 for kw in keywords if kw in task_lower)
        if score > 0:
            scores[agent_name] = score
    if scores:
        return max(scores, key=scores.get)
    return "researcher"


def route_task(task: str) -> str:
    """Route a task to the best agent. Tries LLM first, falls back to keywords."""
    llm_result = _route_task_llm(task)
    if llm_result:
        return llm_result
    return _route_task_keywords(task)


def get_agent(agent_type: str):
    if agent_type == "developer":
        from agents.developer import DeveloperAgent
        return DeveloperAgent()
    elif agent_type == "researcher":
        from agents.researcher import ResearcherAgent
        return ResearcherAgent()
    elif agent_type == "sysadmin":
        from agents.sysadmin import SysadminAgent
        return SysadminAgent()
    elif agent_type == "simulator":
        from agents.simulator import SimulatorAgent
        return SimulatorAgent()
    elif agent_type == "cosmos":
        from agents.cosmos import CosmosAgent
        return CosmosAgent()
    elif agent_type == "groot":
        from agents.groot import GrootAgent
        return GrootAgent()
    elif agent_type == "monitor":
        from agents.monitor import MonitorAgent
        return MonitorAgent()
    else:
        from agents.researcher import ResearcherAgent
        return ResearcherAgent()


def run_task(task: str, agent_type: str = None):
    if not agent_type:
        agent_type = route_task(task)

    agent = get_agent(agent_type)
    model_info = agent.get_model_info()
    cost_label = "FREE" if model_info["is_local"] else "PAID"

    console.print()
    header = Table(show_header=False, box=None, padding=(0, 1))
    header.add_column(style="bold")
    header.add_column()
    # Load policy from models.yml
    import yaml as _yaml
    _policy_conf = {}
    _config_path = os.path.expanduser("~/agent-stack/config/models.yml")
    if os.path.exists(_config_path):
        with open(_config_path) as _f:
            _policy_conf = _yaml.safe_load(_f).get("policy", {})
    _local_first = _policy_conf.get("local_first", False)
    _api_fallback = "requires approval" if _policy_conf.get("require_explicit_approval_for_api") else "auto"
    _policy_str = f"[bold green]LOCAL FIRST[/bold green] | API fallback: {_api_fallback}" if _local_first else "standard"

    header.add_row("Task:", task)
    header.add_row("Agent:", f"[bold cyan]{agent_type}[/bold cyan]")
    header.add_row("Model:", f"{model_info['model']} @ {model_info['host']} ([{'green' if cost_label == 'FREE' else 'red'}]{cost_label}[/])")
    header.add_row("Policy:", _policy_str)
    console.print(Panel(header, title="[bold yellow]AGENT STACK[/bold yellow]", border_style="yellow"))
    console.print()

    start_time = time.time()

    try:
        with console.status(f"[yellow]Running {agent_type} agent...[/yellow]", spinner="dots"):
            if agent_type == "developer":
                knowledge = agent.load_knowledge(agent.task_type)
                prompt = f"Knowledge:\n{knowledge}\n\nTask: {task}\n\nProvide complete, production-quality code."
                result = agent.query_with_retry(prompt)
            elif agent_type == "monitor":
                metrics = agent.check_all_machines()
                agent.write_metrics(metrics)
                alerts = agent.evaluate_alerts(metrics)
                result = _format_monitor(metrics, alerts)
            elif agent_type == "researcher":
                result = agent.research(task)
            elif agent_type == "sysadmin":
                knowledge = agent.load_knowledge(agent.task_type)
                prompt = f"Fleet:\n{agent.fleet_config}\n\nKnowledge:\n{knowledge}\n\nTask: {task}"
                result = agent.query_with_retry(prompt)
            else:
                knowledge = agent.load_knowledge(agent.task_type)
                prompt = f"Knowledge:\n{knowledge}\n\nTask: {task}"
                result = agent.query_with_retry(prompt)

        duration = time.time() - start_time
        console.print(result)
        console.print()

        footer = Table(show_header=False, box=None, padding=(0, 1))
        footer.add_column(style="bold")
        footer.add_column()
        footer.add_row("Duration:", f"{duration:.1f}s")
        footer.add_row("Success:", "[green]OK[/green]")
        footer.add_row("Model:", f"{model_info['model']} ({cost_label})")
        console.print(Panel(footer, title="[bold green]COMPLETE[/bold green]", border_style="green"))

        agent.log_task(task=task[:200], result=result[:500] if result else "", model=model_info["model"], success=True)

    except Exception as e:
        duration = time.time() - start_time
        console.print(f"\n[red]Error: {e}[/red]")

        footer = Table(show_header=False, box=None, padding=(0, 1))
        footer.add_column(style="bold")
        footer.add_column()
        footer.add_row("Duration:", f"{duration:.1f}s")
        footer.add_row("Success:", "[red]FAILED[/red]")
        footer.add_row("Error:", str(e)[:100])
        console.print(Panel(footer, title="[bold red]FAILED[/bold red]", border_style="red"))
        sys.exit(1)


def _format_monitor(metrics: dict, alerts: list) -> str:
    lines = []
    for machine_name, m in metrics.items():
        status = m.get("status", "unknown")
        icon = "[green]OK[/green]" if status == "online" else f"[red]{status.upper()}[/red]"
        lines.append(f"\n[bold]{machine_name}[/bold] {icon}")
        if m.get("gpu_util") is not None:
            lines.append(f"  GPU: {m['gpu_util']:.0f}% | VRAM: {m.get('gpu_vram_used', 0):.1f}/{m.get('gpu_vram_total', 0):.1f} GB | Temp: {m.get('temp_c', 0):.0f}C")
        if m.get("ram_used") is not None:
            pct = (m["ram_used"] / max(m.get("ram_total", 1), 0.01)) * 100
            lines.append(f"  RAM: {m['ram_used']:.1f}/{m.get('ram_total', 0):.1f} GB ({pct:.0f}%)")
        if m.get("disk_used") is not None:
            pct = (m["disk_used"] / max(m.get("disk_total", 1), 0.01)) * 100
            lines.append(f"  Disk: {m['disk_used']:.1f}/{m.get('disk_total', 0):.1f} GB ({pct:.0f}%)")
        lines.append(f"  Ollama: {m.get('ollama_status', 'N/A')}")
    if alerts:
        lines.append("\n[bold red]ALERTS:[/bold red]")
        for severity, machine, msg in alerts:
            color = "red" if severity == "CRITICAL" else "yellow"
            lines.append(f"  [{color}][{severity}][/{color}] {machine}: {msg}")
    return "\n".join(lines)


def show_status():
    from concurrent.futures import ThreadPoolExecutor, as_completed

    console.print(Panel("[bold yellow]\u03B1 MISSION CONTROL[/bold yellow]\n[dim]Robotics Fleet Intelligence \u2022 by Alpha[/dim]", border_style="yellow"))
    try:
        from agents.monitor import MonitorAgent
        monitor = MonitorAgent()

        table = Table(title="Fleet Health")
        table.add_column("Machine", style="bold")
        table.add_column("Status")
        table.add_column("GPU %")
        table.add_column("VRAM")
        table.add_column("RAM")
        table.add_column("Temp")
        table.add_column("Ollama")

        results = {}
        with console.status("[yellow]Checking fleet...[/yellow]"):
            with ThreadPoolExecutor(max_workers=len(monitor.fleet_config)) as pool:
                futures = {pool.submit(monitor.check_machine, name): name for name in monitor.fleet_config}
                for future in as_completed(futures, timeout=15):
                    name = futures[future]
                    try:
                        results[name] = future.result(timeout=1)
                    except Exception:
                        results[name] = {"status": "timeout"}

        # Fill in timed-out machines
        for name in monitor.fleet_config:
            if name not in results:
                results[name] = {"status": "timeout"}

        for name in monitor.fleet_config:
            m = results[name]
            status = m.get("status", "unknown")
            status_str = "[green]ONLINE[/green]" if status == "online" else f"[red]{status.upper()}[/red]"
            gpu = f"{m.get('gpu_util', 0):.0f}%" if m.get("gpu_util") is not None else "N/A"
            if m.get("unified_memory"):
                vram = f"unified ({m.get('gpu_vram_total', 0):.0f}GB)" if m.get("gpu_vram_total") else "unified"
            else:
                vram = f"{m.get('gpu_vram_used', 0):.1f}/{m.get('gpu_vram_total', 0):.1f}G" if m.get("gpu_vram_used") is not None else "N/A"
            ram = f"{m.get('ram_used', 0):.1f}/{m.get('ram_total', 0):.1f}G" if m.get("ram_used") is not None else "N/A"
            temp = f"{m.get('temp_c', 0):.0f}C" if m.get("temp_c") is not None else "N/A"
            ollama = m.get("ollama_status", "N/A")
            table.add_row(name, status_str, gpu, vram, ram, temp, ollama)

        console.print(table)

        # Write metrics to DB
        monitor.write_metrics(results)

    except Exception as e:
        console.print(f"[red]Fleet check failed: {e}[/red]")

    console.print()
    import yaml
    config_path = os.path.expanduser("~/agent-stack/config/models.yml")
    if os.path.exists(config_path):
        with open(config_path) as f:
            _full = yaml.safe_load(f)
            models = _full["models"]
            _pol = _full.get("policy", {})
        if _pol.get("local_first"):
            _fb = "requires approval" if _pol.get("require_explicit_approval_for_api") else "auto"
            console.print(Panel(
                f"[bold green]LOCAL FIRST[/bold green] | API fallback: {_fb} | Max retries: {_pol.get('max_local_retries', 3)} | Log API calls: {_pol.get('log_all_api_calls', True)}",
                title="[bold]Policy[/bold]", border_style="green"
            ))
            console.print()
        table = Table(title="Model Routes")
        table.add_column("Agent", style="bold")
        table.add_column("Model")
        table.add_column("Host")
        table.add_column("Cost", style="green")
        for task_type, conf in models.items():
            if task_type == "fallback":
                table.add_row(task_type, conf.get("model", ""), conf.get("provider", ""), "[red]PAID[/red]")
            else:
                table.add_row(task_type, conf.get("model", ""), conf.get("host", ""), "[green]FREE[/green]")
        console.print(table)

    console.print()
    try:
        import sqlite3
        db_path = os.path.expanduser("~/agent-stack/data/metrics.db")
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM agent_tasks ORDER BY id DESC LIMIT 5").fetchall()
            conn.close()
            if rows:
                table = Table(title="Recent Tasks")
                table.add_column("Agent")
                table.add_column("Task")
                table.add_column("Model")
                table.add_column("Status")
                for row in rows:
                    status = "[green]OK[/green]" if row["success"] else "[red]FAIL[/red]"
                    table.add_row(row["agent"], (row["task"] or "")[:50], row["model_used"] or "", status)
                console.print(table)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Mission Control by Alpha - Robotics Fleet Intelligence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  agent "check fleet health"
  agent "write a Python function to compute manipulability"
  agent --agent developer "refactor trajectory planner"
  agent --status
  agent --dashboard
        """,
    )
    parser.add_argument("task", nargs="?", help="Task to execute")
    parser.add_argument("--agent", "-a", choices=[
        "developer", "researcher", "sysadmin", "simulator",
        "cosmos", "groot", "monitor"
    ], help="Force a specific agent")
    parser.add_argument("--status", "-s", action="store_true", help="Show agent stack status")
    parser.add_argument("--dashboard", "-d", action="store_true", help="Open dashboard in browser")

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.dashboard:
        url = "http://localhost:8080"
        console.print(f"Opening dashboard at {url}")
        webbrowser.open(url)
    elif args.task:
        run_task(args.task, args.agent)
    else:
        parser.print_help()
        console.print("\n[yellow]Quick start:[/yellow] agent \"check fleet health\"")


if __name__ == "__main__":
    main()
