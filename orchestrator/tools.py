# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Tool functions for AutoGen agents.

Each function is registered to specific agents via FunctionTool.
Tools wrap existing code from ~/agent-stack/tools/ and ~/agent-stack/agents/.
All tools return strings (never raise) so agents can handle errors gracefully.
"""

import os
import sys
import json
import subprocess
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agent-stack"))

BASE_DIR = os.path.expanduser("~/agent-stack")
DB_PATH = os.path.join(BASE_DIR, "data", "metrics.db")
CONFIG_DIR = os.path.join(BASE_DIR, "config")

import yaml

def _load_fleet():
    with open(os.path.join(CONFIG_DIR, "fleet.yml")) as f:
        return yaml.safe_load(f)["machines"]


# ── Monitor Tools ─────────────────────────────────────────────────────────

def check_fleet_health() -> str:
    """Check GPU, RAM, disk, temperature for all fleet machines. Returns a formatted report."""
    try:
        from agents.monitor import MonitorAgent
        agent = MonitorAgent(daemon_mode=True)
        metrics = agent.check_all_machines()
        agent.write_metrics(metrics)
        alerts = agent.evaluate_alerts(metrics)

        lines = ["Fleet Health Report", "=" * 40]
        for name, m in metrics.items():
            status = m.get("status", "unknown")
            gpu = f"{m.get('gpu_util', 0):.0f}%" if m.get("gpu_util") is not None else "N/A"
            ram_used = m.get("ram_used", 0)
            ram_total = m.get("ram_total", 1)
            ram_pct = (ram_used / ram_total * 100) if ram_total > 0 else 0
            disk_used = m.get("disk_used", 0)
            disk_total = m.get("disk_total", 1)
            disk_pct = (disk_used / disk_total * 100) if disk_total > 0 else 0
            temp = f"{m.get('temp_c', 0):.0f}°C" if m.get("temp_c") is not None else "N/A"
            lines.append(f"{name}: {status} | GPU={gpu} RAM={ram_pct:.0f}% Disk={disk_pct:.0f}% Temp={temp}")

        if alerts:
            lines.append("")
            lines.append("ALERTS:")
            for severity, machine, msg in alerts:
                lines.append(f"  [{severity}] {machine}: {msg}")
        else:
            lines.append("\nAll machines healthy.")

        agent.close()
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR checking fleet health: {e}"


def check_gpu_status(machine: str = "workstation") -> str:
    """Check GPU utilization, VRAM, and temperature for a specific machine."""
    try:
        fleet = _load_fleet()
        config = fleet.get(machine)
        if not config:
            return f"ERROR: Machine '{machine}' not in fleet config"

        host = config["host"]
        user = config["user"]
        cmd = "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name --format=csv,noheader,nounits"

        if host == "localhost":
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        else:
            r = subprocess.run(
                f"ssh -o ConnectTimeout=5 -o BatchMode=yes {user}@{host} '{cmd}'",
                shell=True, capture_output=True, text=True, timeout=10,
            )

        if r.returncode != 0:
            return f"ERROR: nvidia-smi failed on {machine}: {r.stderr.strip()}"

        parts = [x.strip() for x in r.stdout.strip().split(",")]
        return f"GPU on {machine}: util={parts[0]}% VRAM={parts[1]}/{parts[2]}MB temp={parts[3]}°C model={parts[4]}"
    except Exception as e:
        return f"ERROR checking GPU on {machine}: {e}"


def check_ollama_status(machine: str = "localhost") -> str:
    """Check if Ollama is running and what models are loaded on a machine."""
    try:
        fleet = _load_fleet()
        config = fleet.get(machine, {"host": "localhost", "user": "samuel"})
        host = config["host"]
        user = config["user"]

        # Check service status
        if host == "localhost":
            r = subprocess.run("systemctl is-active ollama", shell=True, capture_output=True, text=True, timeout=5)
            status = r.stdout.strip()
            r2 = subprocess.run("curl -sf http://localhost:11434/api/tags", shell=True, capture_output=True, text=True, timeout=5)
        else:
            r = subprocess.run(
                f"ssh -o ConnectTimeout=5 -o BatchMode=yes {user}@{host} 'systemctl is-active ollama'",
                shell=True, capture_output=True, text=True, timeout=10,
            )
            status = r.stdout.strip()
            port = config.get("port", 11434)
            r2 = subprocess.run(
                f"curl -sf http://{host}:{port}/api/tags",
                shell=True, capture_output=True, text=True, timeout=5,
            )

        models = []
        if r2.returncode == 0:
            try:
                data = json.loads(r2.stdout)
                models = [m["name"] for m in data.get("models", [])]
            except (json.JSONDecodeError, KeyError):
                pass

        return f"Ollama on {machine}: {status} | Models: {', '.join(models) if models else 'none loaded'}"
    except Exception as e:
        return f"ERROR checking Ollama on {machine}: {e}"


# ── Sysadmin Tools ────────────────────────────────────────────────────────

def ssh_cmd(machine: str, command: str) -> str:
    """Execute a command on a fleet machine via SSH. Returns stdout or error."""
    try:
        fleet = _load_fleet()
        config = fleet.get(machine)
        if not config:
            return f"ERROR: Machine '{machine}' not in fleet config"

        host = config["host"]
        user = config["user"]

        if host == "localhost":
            r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        else:
            r = subprocess.run(
                f"ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no {user}@{host} '{command}'",
                shell=True, capture_output=True, text=True, timeout=15,
            )

        if r.returncode == 0:
            return r.stdout.strip() if r.stdout.strip() else "(no output)"
        else:
            return f"ERROR (exit {r.returncode}): {r.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return f"ERROR: Command timed out on {machine}"
    except Exception as e:
        return f"ERROR: {e}"


def docker_cmd(action: str, target: str = "", machine: str = "workstation") -> str:
    """Manage Docker containers: ps, logs, images, start, stop, restart.

    Args:
        action: One of 'ps', 'logs', 'images', 'start', 'stop', 'restart'
        target: Container name (required for logs/start/stop/restart)
        machine: Fleet machine name (default: workstation)
    """
    ALLOWED_ACTIONS = {"ps", "logs", "images", "start", "stop", "restart"}
    if action not in ALLOWED_ACTIONS:
        return f"ERROR: action must be one of {ALLOWED_ACTIONS}"

    if action in ("logs", "start", "stop", "restart") and not target:
        return f"ERROR: '{action}' requires a target container name"

    cmd_map = {
        "ps": "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'",
        "logs": f"docker logs --tail 50 {target}",
        "images": "docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}'",
        "start": f"docker start {target}",
        "stop": f"docker stop {target}",
        "restart": f"docker restart {target}",
    }

    return ssh_cmd(machine, cmd_map[action])


def systemctl_cmd(action: str, service: str, machine: str = "workstation") -> str:
    """Manage systemd services: status, start, stop, restart, is-active.

    Args:
        action: One of 'status', 'start', 'stop', 'restart', 'is-active'
        service: Service name (e.g., 'ollama', 'agent-dashboard')
        machine: Fleet machine name
    """
    ALLOWED = {"status", "start", "stop", "restart", "is-active"}
    if action not in ALLOWED:
        return f"ERROR: action must be one of {ALLOWED}"

    # Use --user for agent-* services
    user_flag = "--user" if service.startswith("agent-") else ""
    return ssh_cmd(machine, f"systemctl {user_flag} {action} {service}")


# ── Developer Tools ───────────────────────────────────────────────────────

def read_file(path: str) -> str:
    """Read a file and return its contents (max 500 lines)."""
    try:
        expanded = os.path.expanduser(path)
        if not os.path.isfile(expanded):
            return f"ERROR: File not found: {path}"
        with open(expanded) as f:
            lines = f.readlines()
        if len(lines) > 500:
            return "".join(lines[:500]) + f"\n... ({len(lines) - 500} more lines truncated)"
        return "".join(lines)
    except Exception as e:
        return f"ERROR reading {path}: {e}"


def write_file(path: str, content: str) -> str:
    """Write content to a file. Creates parent directories if needed."""
    try:
        expanded = os.path.expanduser(path)
        os.makedirs(os.path.dirname(expanded), exist_ok=True)
        with open(expanded, "w") as f:
            f.write(content)
        return f"OK: Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"ERROR writing {path}: {e}"


def run_syntax_check(path: str) -> str:
    """Run a syntax check on a Python file."""
    try:
        expanded = os.path.expanduser(path)
        r = subprocess.run(
            f"python -c \"import py_compile; py_compile.compile('{expanded}', doraise=True)\"",
            shell=True, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return f"OK: {path} syntax is valid"
        return f"SYNTAX ERROR in {path}: {r.stderr.strip()}"
    except Exception as e:
        return f"ERROR: {e}"


# ── Simulator Tools ───────────────────────────────────────────────────────

def check_sim_status() -> str:
    """Check if Isaac Sim or any simulation containers are running."""
    try:
        # Check for Isaac Sim processes
        r = subprocess.run(
            "ps aux | grep -E '(isaac|omni)' | grep -v grep | head -10",
            shell=True, capture_output=True, text=True, timeout=5,
        )
        procs = r.stdout.strip()

        # Check for simulation docker containers
        r2 = subprocess.run(
            "docker ps --format '{{.Names}} {{.Status}}' | grep -i -E '(isaac|sim|curobo)'",
            shell=True, capture_output=True, text=True, timeout=5,
        )
        containers = r2.stdout.strip()

        parts = ["Simulation Status:"]
        if procs:
            parts.append(f"Processes:\n{procs}")
        else:
            parts.append("No Isaac Sim processes running")
        if containers:
            parts.append(f"Containers:\n{containers}")
        else:
            parts.append("No simulation containers running")

        return "\n".join(parts)
    except Exception as e:
        return f"ERROR checking sim status: {e}"


def run_isaac_sim(scene: str, mode: str = "headless") -> str:
    """Launch an Isaac Sim scene via Docker.

    Args:
        scene: Scene name or path (e.g., 'basic_cube', 'cr10_pick_place')
        mode: 'headless' or 'gui'
    """
    try:
        script = os.path.expanduser("~/dobot_cr10/launch_demo.sh")
        if not os.path.isfile(script):
            return "ERROR: launch_demo.sh not found at ~/dobot_cr10/launch_demo.sh"

        cmd = f"bash {script} {scene}"
        if mode == "headless":
            cmd += " --headless"

        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300,
        )
        if r.returncode == 0:
            return f"OK: Simulation '{scene}' completed.\n{r.stdout[-1000:]}"
        return f"ERROR (exit {r.returncode}): {r.stderr[-500:]}"
    except subprocess.TimeoutExpired:
        return f"ERROR: Simulation '{scene}' timed out after 5 minutes"
    except Exception as e:
        return f"ERROR launching sim: {e}"


# ── Resource Manager Tools ────────────────────────────────────────────────

def check_resources() -> str:
    """Check resource usage across all fleet machines (summary view)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute("""
            SELECT machine, gpu_util, gpu_vram_used, gpu_vram_total,
                   ram_used, ram_total, disk_used, disk_total, status
            FROM fleet_health
            WHERE id IN (SELECT MAX(id) FROM fleet_health GROUP BY machine)
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No fleet health data available. Run check_fleet_health first."

        lines = ["Resource Summary (latest metrics):", "-" * 50]
        for row in rows:
            machine, gpu, vram_u, vram_t, ram_u, ram_t, disk_u, disk_t, status = row
            gpu_s = f"{gpu:.0f}%" if gpu is not None else "N/A"
            vram_s = f"{vram_u:.1f}/{vram_t:.1f}GB" if vram_u and vram_t else "N/A"
            ram_s = f"{ram_u:.1f}/{ram_t:.1f}GB" if ram_u and ram_t else "N/A"
            disk_s = f"{disk_u:.0f}/{disk_t:.0f}GB" if disk_u and disk_t else "N/A"
            lines.append(f"{machine}: {status} | GPU={gpu_s} VRAM={vram_s} RAM={ram_s} Disk={disk_s}")

        return "\n".join(lines)
    except Exception as e:
        return f"ERROR checking resources: {e}"


def query_db(sql: str) -> str:
    """Run a read-only SQL query against the metrics database. Returns results as text.

    Only SELECT queries are allowed.
    """
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        return "ERROR: Only SELECT queries are allowed"

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No results."

        # Format as table
        keys = rows[0].keys()
        lines = [" | ".join(keys)]
        lines.append("-" * len(lines[0]))
        for row in rows[:50]:  # Limit to 50 rows
            lines.append(" | ".join(str(row[k]) for k in keys))

        if len(rows) > 50:
            lines.append(f"... ({len(rows) - 50} more rows)")

        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"


# ── Research Tools ────────────────────────────────────────────────────────

def search_knowledge_base(query: str) -> str:
    """Search the agent-stack knowledge base for relevant documentation.

    Args:
        query: Search terms (e.g., 'dobot cr10 urdf', 'isaac sim scene')
    """
    try:
        knowledge_dir = os.path.join(BASE_DIR, "knowledge")
        if not os.path.isdir(knowledge_dir):
            return "ERROR: Knowledge base not found"

        results = []
        query_lower = query.lower()
        terms = query_lower.split()

        for root, _, files in os.walk(knowledge_dir):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath) as f:
                        content = f.read()
                    # Score by number of matching terms
                    content_lower = content.lower()
                    score = sum(1 for t in terms if t in content_lower)
                    if score > 0:
                        rel_path = os.path.relpath(fpath, knowledge_dir)
                        # Extract first paragraph as summary
                        summary = content[:200].replace("\n", " ").strip()
                        results.append((score, rel_path, summary))
                except Exception:
                    pass

        results.sort(key=lambda x: -x[0])
        if not results:
            return f"No knowledge base entries match: {query}"

        lines = [f"Knowledge base results for '{query}':", ""]
        for score, path, summary in results[:10]:
            lines.append(f"  [{score} matches] {path}")
            lines.append(f"    {summary}...")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"ERROR searching knowledge base: {e}"


# ── Training Tools ────────────────────────────────────────────────────────

def check_training_status() -> str:
    """Check status of any running or recent training runs."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT robot, policy_name, started, completed, epochs,
                   final_loss, val_loss, status
            FROM training_runs
            ORDER BY id DESC LIMIT 5
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No training runs found in database."

        lines = ["Recent Training Runs:", "-" * 50]
        for row in rows:
            status = row["status"] or "unknown"
            loss = f"loss={row['final_loss']:.4f}" if row["final_loss"] else "no loss"
            lines.append(
                f"  {row['policy_name']} ({row['robot']}): {status} | "
                f"epochs={row['epochs'] or 0} {loss}"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"ERROR checking training status: {e}"


# ── Git Tools ────────────────────────────────────────────────────────────

def git_status(repo_path: str = "~/agent-stack") -> str:
    """Check git status of a repository (branch, uncommitted changes, unpushed commits)."""
    try:
        expanded = os.path.expanduser(repo_path)
        if not os.path.isdir(os.path.join(expanded, ".git")):
            return f"ERROR: {repo_path} is not a git repository"

        parts = []
        # Branch
        r = subprocess.run("git branch --show-current", shell=True, capture_output=True,
                          text=True, cwd=expanded, timeout=5)
        parts.append(f"Branch: {r.stdout.strip()}")

        # Status
        r = subprocess.run("git status --short", shell=True, capture_output=True,
                          text=True, cwd=expanded, timeout=5)
        changes = r.stdout.strip()
        parts.append(f"Changes: {changes if changes else 'clean'}")

        # Unpushed
        r = subprocess.run("git log --oneline @{u}..HEAD 2>/dev/null", shell=True,
                          capture_output=True, text=True, cwd=expanded, timeout=5)
        unpushed = r.stdout.strip()
        parts.append(f"Unpushed: {unpushed if unpushed else 'none'}")

        return "\n".join(parts)
    except Exception as e:
        return f"ERROR: {e}"


def git_log(repo_path: str = "~/agent-stack", count: int = 10) -> str:
    """Show recent git commit history.

    Args:
        repo_path: Path to git repository
        count: Number of commits to show (max 50)
    """
    try:
        expanded = os.path.expanduser(repo_path)
        count = min(count, 50)
        r = subprocess.run(
            f"git log --oneline --decorate -n {count}",
            shell=True, capture_output=True, text=True, cwd=expanded, timeout=10,
        )
        if r.returncode != 0:
            return f"ERROR: {r.stderr.strip()}"
        return r.stdout.strip() or "No commits."
    except Exception as e:
        return f"ERROR: {e}"


def git_diff(repo_path: str = "~/agent-stack", staged: bool = False) -> str:
    """Show git diff of current changes.

    Args:
        repo_path: Path to git repository
        staged: If True, show staged changes only
    """
    try:
        expanded = os.path.expanduser(repo_path)
        flag = "--cached" if staged else ""
        r = subprocess.run(
            f"git diff {flag} --stat",
            shell=True, capture_output=True, text=True, cwd=expanded, timeout=10,
        )
        if r.returncode != 0:
            return f"ERROR: {r.stderr.strip()}"
        return r.stdout.strip() or "No changes."
    except Exception as e:
        return f"ERROR: {e}"


def git_add(repo_path: str = "~/agent-stack", files: str = ".") -> str:
    """Stage files for commit.

    Args:
        repo_path: Path to git repository
        files: Files to stage (space-separated, or '.' for all)
    """
    try:
        expanded = os.path.expanduser(repo_path)
        r = subprocess.run(
            f"git add {files}",
            shell=True, capture_output=True, text=True, cwd=expanded, timeout=10,
        )
        if r.returncode != 0:
            return f"ERROR: {r.stderr.strip()}"
        return f"OK: Staged '{files}' in {repo_path}"
    except Exception as e:
        return f"ERROR: {e}"


def git_commit(repo_path: str = "~/agent-stack", message: str = "") -> str:
    """Create a git commit with the given message.

    Args:
        repo_path: Path to git repository
        message: Commit message (required)
    """
    if not message:
        return "ERROR: Commit message is required"
    try:
        expanded = os.path.expanduser(repo_path)
        r = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True, text=True, cwd=expanded, timeout=15,
        )
        if r.returncode != 0:
            return f"ERROR: {r.stderr.strip()}"
        return r.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def git_push(repo_path: str = "~/agent-stack", remote: str = "origin", branch: str = "") -> str:
    """Push commits to remote.

    Args:
        repo_path: Path to git repository
        remote: Remote name (default: origin)
        branch: Branch to push (default: current branch)
    """
    try:
        expanded = os.path.expanduser(repo_path)
        cmd = f"git push {remote}"
        if branch:
            cmd += f" {branch}"
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=expanded, timeout=30,
        )
        if r.returncode != 0:
            return f"ERROR: {r.stderr.strip()}"
        output = r.stdout.strip() or r.stderr.strip()
        return f"OK: Pushed to {remote}. {output}"
    except Exception as e:
        return f"ERROR: {e}"


def git_pull(repo_path: str = "~/agent-stack") -> str:
    """Pull latest changes from remote."""
    try:
        expanded = os.path.expanduser(repo_path)
        r = subprocess.run(
            "git pull", shell=True, capture_output=True, text=True, cwd=expanded, timeout=30,
        )
        if r.returncode != 0:
            return f"ERROR: {r.stderr.strip()}"
        return r.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def git_branch(repo_path: str = "~/agent-stack", action: str = "list", name: str = "") -> str:
    """Manage git branches.

    Args:
        repo_path: Path to git repository
        action: 'list', 'create', 'checkout', or 'delete'
        name: Branch name (required for create/checkout/delete)
    """
    ALLOWED = {"list", "create", "checkout", "delete"}
    if action not in ALLOWED:
        return f"ERROR: action must be one of {ALLOWED}"
    if action != "list" and not name:
        return f"ERROR: '{action}' requires a branch name"

    try:
        expanded = os.path.expanduser(repo_path)
        cmd_map = {
            "list": "git branch -a",
            "create": f"git checkout -b {name}",
            "checkout": f"git checkout {name}",
            "delete": f"git branch -d {name}",
        }
        r = subprocess.run(
            cmd_map[action], shell=True, capture_output=True, text=True, cwd=expanded, timeout=10,
        )
        if r.returncode != 0:
            return f"ERROR: {r.stderr.strip()}"
        return r.stdout.strip() or f"OK: {action} {name}"
    except Exception as e:
        return f"ERROR: {e}"


# ── Documentation Tools ──────────────────────────────────────────────────

DOCS_DIRS = [
    os.path.expanduser("~/mission-control/docs"),
    os.path.expanduser("~/agent-stack/knowledge"),
    os.path.expanduser("~/audit"),
]


def list_docs(directory: str = "") -> str:
    """List documentation files in the docs/knowledge/audit directories.

    Args:
        directory: Subdirectory to list (e.g., 'robotics', 'agent-system'). Empty for all.
    """
    try:
        results = []
        for base in DOCS_DIRS:
            search_dir = os.path.join(base, directory) if directory else base
            if not os.path.isdir(search_dir):
                continue
            for root, dirs, files in os.walk(search_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in sorted(files):
                    if f.endswith((".md", ".yml", ".yaml", ".txt")):
                        rel = os.path.relpath(os.path.join(root, f), os.path.expanduser("~"))
                        size = os.path.getsize(os.path.join(root, f))
                        results.append(f"  ~/{rel} ({size:,} bytes)")

        if not results:
            return f"No documentation files found{' in ' + directory if directory else ''}."
        return f"Documentation files ({len(results)}):\n" + "\n".join(results[:100])
    except Exception as e:
        return f"ERROR: {e}"


def search_docs(query: str) -> str:
    """Search across all documentation files for matching content.

    Args:
        query: Search terms (case-insensitive)
    """
    try:
        terms = query.lower().split()
        matches = []
        for base in DOCS_DIRS:
            if not os.path.isdir(base):
                continue
            for root, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in files:
                    if not f.endswith((".md", ".yml", ".yaml", ".txt")):
                        continue
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath) as fh:
                            content = fh.read()
                        content_lower = content.lower()
                        score = sum(1 for t in terms if t in content_lower)
                        if score > 0:
                            rel = os.path.relpath(fpath, os.path.expanduser("~"))
                            # Extract matching line context
                            context = ""
                            for line in content.split("\n"):
                                if any(t in line.lower() for t in terms):
                                    context = line.strip()[:120]
                                    break
                            matches.append((score, rel, context))
                    except Exception:
                        pass

        matches.sort(key=lambda x: -x[0])
        if not matches:
            return f"No documentation matches for: {query}"

        lines = [f"Search results for '{query}' ({len(matches)} matches):", ""]
        for score, path, ctx in matches[:20]:
            lines.append(f"  [{score}] ~/{path}")
            if ctx:
                lines.append(f"       {ctx}")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"


def write_doc(path: str, content: str) -> str:
    """Write or update a documentation file (markdown).

    Args:
        path: File path relative to ~ (e.g., 'mission-control/docs/agent-system/git-agent.md')
        content: Markdown content to write
    """
    try:
        expanded = os.path.expanduser(f"~/{path}" if not path.startswith("/") else path)
        # Safety: only allow writing to docs/knowledge/audit dirs
        allowed_prefixes = [os.path.expanduser(p) for p in ["~/mission-control/docs", "~/agent-stack/knowledge", "~/audit"]]
        if not any(expanded.startswith(p) for p in allowed_prefixes):
            return f"ERROR: Can only write to docs, knowledge, or audit directories"
        if not expanded.endswith((".md", ".yml", ".yaml", ".txt")):
            return f"ERROR: Only .md, .yml, .yaml, .txt files allowed"

        os.makedirs(os.path.dirname(expanded), exist_ok=True)
        with open(expanded, "w") as f:
            f.write(content)
        return f"OK: Wrote {len(content)} bytes to ~/{path}"
    except Exception as e:
        return f"ERROR: {e}"


def generate_doc_outline(topic: str, doc_type: str = "technical") -> str:
    """Generate a documentation outline/template for a given topic.

    Args:
        topic: Subject to document (e.g., 'orchestrator', 'dobot cr10 setup')
        doc_type: Type of document: 'technical', 'user_manual', 'instruction', 'api'
    """
    templates = {
        "technical": f"""# {topic}

## Overview
[Brief description of {topic}]

## Architecture
[System design, components, data flow]

## Components
### Component 1
[Description, configuration, dependencies]

## Configuration
[Config files, environment variables, settings]

## API Reference
[Endpoints, functions, parameters]

## Troubleshooting
[Common issues and solutions]

## Changelog
[Version history]
""",
        "user_manual": f"""# {topic} — User Manual

## Getting Started
[Prerequisites and initial setup]

## Quick Start
[Step-by-step to get running in 5 minutes]

## Features
### Feature 1
[What it does, how to use it]

## Configuration
[User-facing settings and preferences]

## FAQ
[Frequently asked questions]

## Support
[How to get help]
""",
        "instruction": f"""# {topic} — Instructions

## Prerequisites
[Required hardware, software, access]

## Step 1: [First step]
[Detailed instructions with commands/screenshots]

## Step 2: [Second step]
[Detailed instructions]

## Verification
[How to confirm everything works]

## Troubleshooting
[What to do if something goes wrong]
""",
        "api": f"""# {topic} — API Reference

## Base URL
[API base URL and authentication]

## Endpoints

### GET /endpoint
**Description:** [What it does]
**Parameters:** [Query params, headers]
**Response:** [JSON schema]
**Example:**
```
curl -X GET /endpoint
```

## Error Codes
[HTTP status codes and meanings]

## Rate Limits
[Rate limiting policies]
""",
    }
    return templates.get(doc_type, templates["technical"])
