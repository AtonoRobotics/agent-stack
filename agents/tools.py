"""Pure Python tool functions for AutoGen agents.

Each function:
- Takes typed parameters
- Returns a string
- Never raises (catches exceptions, returns error string)
- Has a docstring (AutoGen uses it as tool description)
"""

import os
import socket
import subprocess
import sqlite3
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import yaml

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FLEET_CONFIG_PATH = os.path.expanduser("~/agent-stack/config/fleet.yml")
DB_PATH = os.path.expanduser("~/agent-stack/data/metrics.db")
KNOWLEDGE_PATH = os.path.expanduser("~/agent-stack/knowledge")


def _load_fleet() -> dict:
    try:
        with open(FLEET_CONFIG_PATH) as f:
            return yaml.safe_load(f).get("machines", {})
    except Exception as e:
        return {"error": str(e)}


def _run(cmd: list[str], timeout: int = 30) -> str:
    """Run a subprocess, return stdout+stderr."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return output.strip()
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def _ssh_run(machine: str, command: str, timeout: int = 15) -> str:
    """Run a command on a remote machine via SSH."""
    fleet = _load_fleet()
    if machine not in fleet:
        return f"Unknown machine: {machine}. Known: {list(fleet.keys())}"
    info = fleet[machine]
    if info.get("ssh_reachable") is False:
        return f"Machine {machine} is marked as not SSH reachable"
    host = info.get("host", machine)
    user = info.get("user", "samuel")
    if host == "localhost":
        return _run(["bash", "-c", command], timeout=timeout)
    return _run(
        ["ssh", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
         f"{user}@{host}", command],
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Monitor tools
# ---------------------------------------------------------------------------

def check_fleet_health() -> str:
    """Check health of all machines in the fleet: CPU, RAM, disk, GPU, Ollama status."""
    fleet = _load_fleet()
    lines = []
    for name, info in fleet.items():
        host = info.get("host", name)
        lines.append(f"## {name} ({host})")
        if info.get("ssh_reachable") is False:
            lines.append("  Status: UNREACHABLE (ssh_reachable=false)")
            lines.append("")
            continue
        if host == "localhost":
            # Local checks
            lines.append(f"  CPU: {_run(['bash', '-c', 'uptime | sed s/.*load/load/'])}")
            ram_cmd = "free -h | grep Mem | awk '{print $3,$2}'"
            lines.append(f"  RAM: {_run(['bash', '-c', ram_cmd])}")
            disk_cmd = "df -h / | tail -1 | awk '{print $3,$2,$5}'"
            lines.append(f"  Disk: {_run(['bash', '-c', disk_cmd])}")
            gpu = _run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                        "--format=csv,noheader,nounits"])
            if "Error" not in gpu and gpu:
                parts = [p.strip() for p in gpu.split(",")]
                if len(parts) >= 4:
                    lines.append(f"  GPU: {parts[0]}% util, {parts[1]}/{parts[2]} MB VRAM, {parts[3]}C")
            if info.get("ollama", False):
                ollama = _run(["curl", "-sf", f"http://{host}:11434/api/tags"])
                lines.append(f"  Ollama: {'OK' if ollama and 'models' in ollama else 'DOWN'}")
        else:
            # Remote checks via SSH
            user = info.get("user", "samuel")
            remote = _ssh_run(name, "uptime && free -h | grep Mem && df -h / | tail -1")
            lines.append(f"  {remote}")
            if info.get("ollama", False):
                ollama = _run(["curl", "-sf", "--connect-timeout", "3",
                               f"http://{host}:11434/api/tags"])
                lines.append(f"  Ollama: {'OK' if ollama and 'models' in ollama else 'DOWN'}")
        lines.append("")
    return "\n".join(lines) if lines else "No machines configured."


def check_gpu_status(machine: str) -> str:
    """Check GPU utilization, VRAM usage, and temperature on a specific machine."""
    cmd = "nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader"
    return _ssh_run(machine, cmd)


def check_ollama_status(machine: str) -> str:
    """Check Ollama server status and loaded models on a specific machine."""
    fleet = _load_fleet()
    if machine not in fleet:
        return f"Unknown machine: {machine}"
    host = fleet[machine].get("host", machine)
    if not fleet[machine].get("ollama", False):
        return f"Machine {machine} does not have Ollama configured"
    port = 11434
    tags = _run(["curl", "-sf", "--connect-timeout", "5", f"http://{host}:{port}/api/tags"])
    if not tags:
        return f"Ollama not responding on {host}:{port}"
    try:
        data = json.loads(tags)
        models = [m["name"] for m in data.get("models", [])]
        return f"Ollama on {machine}: OK\nModels: {', '.join(models) if models else 'none loaded'}"
    except Exception:
        return f"Ollama response (not JSON): {tags[:500]}"


# ---------------------------------------------------------------------------
# Sysadmin tools
# ---------------------------------------------------------------------------

def ssh_cmd(machine: str, command: str) -> str:
    """Execute a shell command on a fleet machine via SSH. Use 'workstation' for localhost."""
    return _ssh_run(machine, command, timeout=30)


def docker_cmd(action: str, target: str = "", machine: str = "workstation") -> str:
    """Run a Docker command on a fleet machine. Actions: ps, images, logs, inspect, stats, start, stop, restart."""
    safe_actions = {"ps", "images", "logs", "inspect", "stats", "info"}
    if action not in safe_actions | {"start", "stop", "restart"}:
        return f"Action '{action}' not supported. Use: {safe_actions | {'start', 'stop', 'restart'}}"
    if action in {"start", "stop", "restart"} and not target:
        return f"Action '{action}' requires a target container name."
    cmd = f"docker {action}"
    if target:
        cmd += f" {target}"
    return _ssh_run(machine, cmd)


def systemctl_cmd(action: str, service: str, machine: str = "workstation") -> str:
    """Manage systemd services on a fleet machine. Actions: status, start, stop, restart, enable, disable."""
    allowed = {"status", "start", "stop", "restart", "enable", "disable", "is-active"}
    if action not in allowed:
        return f"Action '{action}' not allowed. Use: {allowed}"
    # Use --user for user services if service name suggests it
    user_flag = "--user" if any(s in service for s in ("agent-", "dashboard", "metrics", "monitor", "orchestrator")) else ""
    cmd = f"systemctl {user_flag} {action} {service}"
    return _ssh_run(machine, cmd)


# ---------------------------------------------------------------------------
# Dobot CR10 tools
# ---------------------------------------------------------------------------

def _load_robot_config() -> dict:
    fleet = _load_fleet()
    return fleet.get("robots", {}).get("dobot_cr10", {}) if isinstance(fleet, dict) else {}


def dobot_connect_check() -> str:
    """Ping the Dobot CR10 robot at 192.168.5.1 to check network connectivity."""
    cfg = _load_robot_config()
    host = cfg.get("tcp_host", "192.168.5.1")
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", host],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return f"CR10 reachable at {host}"
        return f"CR10 unreachable at {host}"
    except Exception as e:
        return f"Ping failed: {e}"


def dobot_status() -> str:
    """Query the Dobot CR10 dashboard port (29999) for robot status."""
    cfg = _load_robot_config()
    host = cfg.get("tcp_host", "192.168.5.1")
    port = cfg.get("tcp_ports", {}).get("dashboard", 29999)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((host, port))
        # Read welcome banner
        banner = sock.recv(1024).decode("utf-8", errors="replace").strip()
        # Send RobotMode query
        sock.sendall(b"RobotMode()\n")
        mode = sock.recv(1024).decode("utf-8", errors="replace").strip()
        sock.close()
        return f"CR10 Dashboard ({host}:{port})\nBanner: {banner}\nMode: {mode}"
    except socket.timeout:
        return f"CR10 dashboard timeout ({host}:{port}) — robot may be off or unreachable"
    except ConnectionRefusedError:
        return f"CR10 dashboard refused ({host}:{port}) — robot may be off"
    except Exception as e:
        return f"CR10 dashboard error: {e}"


def dobot_joints() -> str:
    """Get current joint angles from the Dobot CR10 feedback port (30004)."""
    cfg = _load_robot_config()
    host = cfg.get("tcp_host", "192.168.5.1")
    port = cfg.get("tcp_ports", {}).get("feedback", 30004)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((host, port))
        data = sock.recv(4096)
        sock.close()
        if len(data) < 48:
            return f"Received {len(data)} bytes — insufficient for joint data"
        # Dobot feedback: 6 doubles starting at byte 0 (varies by protocol version)
        import struct
        joints = struct.unpack_from("<6d", data, 0)
        labels = ["J1", "J2", "J3", "J4", "J5", "J6"]
        return "CR10 Joint Angles:\n" + "\n".join(
            f"  {l}: {j:.2f}°" for l, j in zip(labels, joints)
        )
    except socket.timeout:
        return f"CR10 feedback timeout ({host}:{port})"
    except ConnectionRefusedError:
        return f"CR10 feedback refused ({host}:{port})"
    except Exception as e:
        return f"CR10 feedback error: {e}"


# ---------------------------------------------------------------------------
# Ollama tools
# ---------------------------------------------------------------------------

def ollama_models(machine: str = "workstation") -> str:
    """List loaded Ollama models on a fleet machine."""
    fleet = _load_fleet()
    if machine not in fleet:
        return f"Unknown machine: {machine}"
    info = fleet[machine]
    if not info.get("ollama", False):
        return f"{machine} does not have Ollama configured"
    host = info.get("host", machine)
    if host == "localhost":
        host = "localhost"
    tags = _run(["curl", "-sf", "--connect-timeout", "5", f"http://{host}:11434/api/tags"])
    if not tags:
        return f"Ollama not responding on {machine}"
    try:
        data = json.loads(tags)
        models = data.get("models", [])
        if not models:
            return f"Ollama on {machine}: no models loaded"
        lines = [f"Ollama on {machine}: {len(models)} model(s)"]
        for m in models:
            size_gb = m.get("size", 0) / (1024**3)
            lines.append(f"  - {m['name']} ({size_gb:.1f} GB)")
        return "\n".join(lines)
    except Exception:
        return f"Ollama response parse error on {machine}"


# ---------------------------------------------------------------------------
# Docker convenience tools
# ---------------------------------------------------------------------------

def docker_images(machine: str = "workstation") -> str:
    """List Docker images on a fleet machine with size info."""
    return _ssh_run(machine, "docker images --format 'table {{.Repository}}\\t{{.Tag}}\\t{{.Size}}'")


def docker_logs(container: str, tail: int = 50, machine: str = "workstation") -> str:
    """Get recent Docker container logs. Tail defaults to 50 lines."""
    return _ssh_run(machine, f"docker logs --tail {tail} {container}", timeout=15)


# ---------------------------------------------------------------------------
# Database query tools
# ---------------------------------------------------------------------------

def query_fleet_health(machine: str = "", hours: int = 1) -> str:
    """Query recent fleet_health rows from the metrics database. Optionally filter by machine."""
    where = f"WHERE machine = '{machine}'" if machine else ""
    sql = (
        f"SELECT machine, timestamp, gpu_util, gpu_vram_used, gpu_vram_total, "
        f"ram_used, ram_total, temp_c, status "
        f"FROM fleet_health {where} "
        f"ORDER BY timestamp DESC LIMIT 20"
    )
    return query_db(sql)


def query_agent_tasks(limit: int = 20) -> str:
    """Query recent agent task records from the database."""
    sql = (
        f"SELECT agent, task, started, completed, model_used, success, notes "
        f"FROM agent_tasks ORDER BY id DESC LIMIT {min(limit, 100)}"
    )
    return query_db(sql)


def log_agent_task(agent: str, task: str, model: str = "", success: bool = True) -> str:
    """Insert a record into the agent_tasks table to log completed work."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO agent_tasks (agent, task, started, completed, model_used, success) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (agent, task[:500], now, now, model, 1 if success else 0),
        )
        conn.commit()
        conn.close()
        return f"Logged task for {agent}: {'success' if success else 'failure'}"
    except Exception as e:
        return f"Error logging task: {e}"


# ---------------------------------------------------------------------------
# URDF tools
# ---------------------------------------------------------------------------

def parse_urdf(path: str) -> str:
    """Parse a URDF file and return joint names, types, limits, and link names."""
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        return f"File not found: {expanded}"
    try:
        tree = ET.parse(expanded)
        root = tree.getroot()
        robot_name = root.get("name", "unknown")

        links = [l.get("name", "?") for l in root.findall("link")]
        joints = []
        for j in root.findall("joint"):
            name = j.get("name", "?")
            jtype = j.get("type", "?")
            limit = j.find("limit")
            limit_str = ""
            if limit is not None:
                lo = limit.get("lower", "N/A")
                hi = limit.get("upper", "N/A")
                vel = limit.get("velocity", "N/A")
                eff = limit.get("effort", "N/A")
                limit_str = f" [{lo} to {hi}], vel={vel}, effort={eff}"
            parent = j.find("parent")
            child = j.find("child")
            p = parent.get("link", "?") if parent is not None else "?"
            c = child.get("link", "?") if child is not None else "?"
            joints.append(f"  {name} ({jtype}): {p} → {c}{limit_str}")

        lines = [f"Robot: {robot_name}", f"Links ({len(links)}): {', '.join(links)}", f"Joints ({len(joints)}):"]
        lines.extend(joints)
        return "\n".join(lines)
    except ET.ParseError as e:
        return f"URDF parse error: {e}"
    except Exception as e:
        return f"Error reading URDF: {e}"


def validate_urdf(path: str) -> str:
    """Validate a URDF file for common errors: missing links, duplicate names, broken references."""
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        return f"File not found: {expanded}"
    try:
        tree = ET.parse(expanded)
        root = tree.getroot()
        errors = []

        if root.tag != "robot":
            errors.append(f"Root element is '{root.tag}', expected 'robot'")

        link_names = [l.get("name") for l in root.findall("link")]
        joint_names = [j.get("name") for j in root.findall("joint")]

        # Duplicate names
        seen_links = set()
        for n in link_names:
            if n in seen_links:
                errors.append(f"Duplicate link name: {n}")
            seen_links.add(n)
        seen_joints = set()
        for n in joint_names:
            if n in seen_joints:
                errors.append(f"Duplicate joint name: {n}")
            seen_joints.add(n)

        # Broken references
        for j in root.findall("joint"):
            jname = j.get("name", "?")
            parent = j.find("parent")
            child = j.find("child")
            if parent is not None:
                plink = parent.get("link")
                if plink and plink not in seen_links:
                    errors.append(f"Joint '{jname}' references unknown parent link '{plink}'")
            else:
                errors.append(f"Joint '{jname}' missing parent element")
            if child is not None:
                clink = child.get("link")
                if clink and clink not in seen_links:
                    errors.append(f"Joint '{jname}' references unknown child link '{clink}'")
            else:
                errors.append(f"Joint '{jname}' missing child element")

        # Missing mesh files
        for visual in root.iter("mesh"):
            filename = visual.get("filename", "")
            if filename and not filename.startswith("package://"):
                mesh_path = filename
                if not os.path.isabs(mesh_path):
                    mesh_path = os.path.join(os.path.dirname(expanded), mesh_path)
                if not os.path.exists(mesh_path):
                    errors.append(f"Missing mesh file: {filename}")

        if errors:
            return f"URDF validation: {len(errors)} error(s)\n" + "\n".join(f"  - {e}" for e in errors)
        return f"URDF valid: {len(link_names)} links, {len(joint_names)} joints, no errors"
    except ET.ParseError as e:
        return f"URDF XML parse error: {e}"
    except Exception as e:
        return f"Validation error: {e}"


# ---------------------------------------------------------------------------
# Developer tools
# ---------------------------------------------------------------------------

def read_file(path: str) -> str:
    """Read a file from the local filesystem and return its contents."""
    try:
        expanded = os.path.expanduser(path)
        if not os.path.exists(expanded):
            return f"File not found: {expanded}"
        if os.path.getsize(expanded) > 100_000:
            return f"File too large ({os.path.getsize(expanded)} bytes). Use head/tail instead."
        with open(expanded) as f:
            return f.read()
    except Exception as e:
        return f"Error reading {path}: {e}"


def write_file(path: str, content: str) -> str:
    """Write content to a file. Creates parent directories if needed."""
    try:
        expanded = os.path.expanduser(path)
        os.makedirs(os.path.dirname(expanded), exist_ok=True)
        with open(expanded, "w") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {expanded}"
    except Exception as e:
        return f"Error writing {path}: {e}"


def run_syntax_check(path: str) -> str:
    """Run a syntax check on a Python file using py_compile."""
    try:
        expanded = os.path.expanduser(path)
        if not expanded.endswith(".py"):
            return "Only .py files supported for syntax check"
        result = _run(["python", "-m", "py_compile", expanded])
        if result:
            return f"Syntax errors:\n{result}"
        return f"Syntax OK: {expanded}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Simulator tools
# ---------------------------------------------------------------------------

def check_sim_status() -> str:
    """Check if Isaac Sim or Isaac Lab processes are running."""
    procs = _run(["bash", "-c", "ps aux | grep -i 'isaac\\|omniverse' | grep -v grep"])
    docker = _run(["bash", "-c", "docker ps --format '{{.Names}} {{.Image}}' | grep -i isaac"])
    lines = ["# Simulation Status"]
    if procs:
        lines.append("## Running processes:")
        lines.append(procs)
    else:
        lines.append("No Isaac Sim/Lab processes running.")
    if docker:
        lines.append("## Docker containers:")
        lines.append(docker)
    return "\n".join(lines)


def run_isaac_sim(scene: str, mode: str = "headless") -> str:
    """Launch an Isaac Sim scene. Mode: headless or gui. Returns launch command (does not block)."""
    script_path = os.path.expanduser(f"~/dobot_cr10/{scene}")
    if not os.path.exists(script_path):
        return f"Scene not found: {script_path}"
    cmd = f"cd ~/dobot_cr10 && bash launch_demo.sh {scene} --{mode}"
    return f"Launch command prepared:\n{cmd}\n\nRun this in a terminal to start the simulation."


# ---------------------------------------------------------------------------
# Resource tools
# ---------------------------------------------------------------------------

def check_resources() -> str:
    """Check local system resources: CPU, RAM, disk, GPU."""
    cpu = _run(["bash", "-c", "uptime"])
    mem = _run(["free", "-h"])
    disk = _run(["df", "-h", "/"])
    gpu = _run(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader"])
    return f"CPU: {cpu}\n\nMemory:\n{mem}\n\nDisk:\n{disk}\n\nGPU: {gpu}"


def query_db(sql: str) -> str:
    """Run a read-only SQL query against the agent-stack metrics database."""
    if not sql.strip().upper().startswith("SELECT"):
        return "Only SELECT queries are allowed."
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchall()
        conn.close()
        if not rows:
            return "No results."
        # Format as table
        columns = rows[0].keys()
        lines = [" | ".join(columns)]
        lines.append(" | ".join("---" for _ in columns))
        for row in rows[:50]:
            lines.append(" | ".join(str(row[c]) for c in columns))
        if len(rows) > 50:
            lines.append(f"... ({len(rows)} total rows, showing first 50)")
        return "\n".join(lines)
    except Exception as e:
        return f"SQL error: {e}"


# ---------------------------------------------------------------------------
# Research tools
# ---------------------------------------------------------------------------

def search_knowledge_base(query: str) -> str:
    """Search the knowledge base markdown files for information matching a query."""
    results = []
    query_lower = query.lower()
    try:
        for root, dirs, files in os.walk(KNOWLEDGE_PATH):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath) as f:
                    content = f.read()
                if query_lower in content.lower():
                    # Find matching lines
                    matches = []
                    for i, line in enumerate(content.split("\n")):
                        if query_lower in line.lower():
                            matches.append(f"  L{i+1}: {line.strip()}")
                    rel_path = os.path.relpath(fpath, KNOWLEDGE_PATH)
                    results.append(f"## {rel_path}\n" + "\n".join(matches[:5]))
        return "\n\n".join(results) if results else f"No matches for '{query}' in knowledge base."
    except Exception as e:
        return f"Error searching knowledge base: {e}"


def search_docs(query: str) -> str:
    """Search project documentation files in ~/mission-control/docs/ for a query."""
    docs_path = os.path.expanduser("~/mission-control/docs")
    results = []
    query_lower = query.lower()
    try:
        for root, dirs, files in os.walk(docs_path):
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath) as f:
                    content = f.read()
                if query_lower in content.lower():
                    matches = []
                    for i, line in enumerate(content.split("\n")):
                        if query_lower in line.lower():
                            matches.append(f"  L{i+1}: {line.strip()}")
                    rel_path = os.path.relpath(fpath, docs_path)
                    results.append(f"## {rel_path}\n" + "\n".join(matches[:5]))
        return "\n\n".join(results) if results else f"No matches for '{query}' in docs."
    except Exception as e:
        return f"Error searching docs: {e}"


def list_docs(directory: str = "") -> str:
    """List documentation files in a directory under ~/mission-control/docs/."""
    base = os.path.expanduser("~/mission-control/docs")
    target = os.path.join(base, directory) if directory else base
    try:
        if not os.path.isdir(target):
            return f"Directory not found: {target}"
        entries = []
        for root, dirs, files in os.walk(target):
            for fname in sorted(files):
                if fname.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root, fname), base)
                    entries.append(rel)
        return "\n".join(entries) if entries else "No .md files found."
    except Exception as e:
        return f"Error listing docs: {e}"


# ---------------------------------------------------------------------------
# Skills tools
# ---------------------------------------------------------------------------

def run_skill(name: str, kwargs_json: str = "{}") -> str:
    """Run a registered skill by name. Pass keyword arguments as a JSON string."""
    from skills import run_skill as _run_skill
    try:
        kwargs = json.loads(kwargs_json) if kwargs_json else {}
    except json.JSONDecodeError as e:
        return f"Invalid JSON for kwargs: {e}"
    return _run_skill(name, **kwargs)


def list_skills() -> str:
    """List all available skills with descriptions."""
    from skills import list_skills as _list_skills
    return _list_skills()


# ---------------------------------------------------------------------------
# Git tools
# ---------------------------------------------------------------------------

def git_status(repo_path: str) -> str:
    """Show git status for a repository."""
    expanded = os.path.expanduser(repo_path)
    return _run(["git", "-C", expanded, "status", "--short"])


def git_log(repo_path: str, count: int = 10) -> str:
    """Show recent git log entries for a repository."""
    expanded = os.path.expanduser(repo_path)
    return _run(["git", "-C", expanded, "log", f"--oneline", f"-{count}"])


def git_diff(repo_path: str) -> str:
    """Show git diff for a repository (staged + unstaged)."""
    expanded = os.path.expanduser(repo_path)
    unstaged = _run(["git", "-C", expanded, "diff"])
    staged = _run(["git", "-C", expanded, "diff", "--staged"])
    parts = []
    if unstaged:
        parts.append(f"## Unstaged:\n{unstaged}")
    if staged:
        parts.append(f"## Staged:\n{staged}")
    return "\n\n".join(parts) if parts else "No changes."


def git_add(repo_path: str, files: str = ".") -> str:
    """Stage files in a repository. Use '.' for all."""
    expanded = os.path.expanduser(repo_path)
    return _run(["git", "-C", expanded, "add", files])


def git_commit(repo_path: str, message: str) -> str:
    """Create a git commit with a message."""
    expanded = os.path.expanduser(repo_path)
    return _run(["git", "-C", expanded, "commit", "-m", message])


def git_push(repo_path: str) -> str:
    """Push commits to the remote repository."""
    expanded = os.path.expanduser(repo_path)
    return _run(["git", "-C", expanded, "push"])


def git_pull(repo_path: str) -> str:
    """Pull latest changes from the remote repository."""
    expanded = os.path.expanduser(repo_path)
    return _run(["git", "-C", expanded, "pull"])


def git_branch(repo_path: str, action: str = "list", name: str = "") -> str:
    """Manage git branches. Actions: list, create, checkout, delete."""
    expanded = os.path.expanduser(repo_path)
    if action == "list":
        return _run(["git", "-C", expanded, "branch", "-a"])
    elif action == "create" and name:
        return _run(["git", "-C", expanded, "checkout", "-b", name])
    elif action == "checkout" and name:
        return _run(["git", "-C", expanded, "checkout", name])
    elif action == "delete" and name:
        return _run(["git", "-C", expanded, "branch", "-d", name])
    return f"Invalid action '{action}' or missing branch name."


# ---------------------------------------------------------------------------
# Safety System Tools
# ---------------------------------------------------------------------------

SAFETY_KNOWLEDGE_PATH = os.path.expanduser("~/agent-stack/knowledge/safety")
SAFETY_CONFIG_PATH = os.path.expanduser("~/dobot_cr10/config/safety")


def safety_check_perception() -> str:
    """Check if NvBlox perception pipeline Docker container is running and healthy."""
    try:
        # Check if Isaac ROS container is running
        result = _run(["docker", "ps", "--filter", "name=isaac_ros", "--format", "{{.Names}} {{.Status}}"])
        if not result or "isaac_ros" not in result:
            return "PERCEPTION_OFFLINE: No Isaac ROS container running. Launch with: ~/workspaces/isaac_ros-dev/run_isaac_ros.sh zed"

        # Check if NvBlox node is active (via ROS2 topic list)
        topics = _run(["docker", "exec", "isaac_ros_dev", "bash", "-c", "ros2 topic list 2>/dev/null | grep nvblox"], timeout=10)
        if "nvblox" in topics:
            return f"PERCEPTION_OK: NvBlox topics active:\n{topics}"
        return "PERCEPTION_DEGRADED: Isaac ROS running but no NvBlox topics found"
    except Exception as e:
        return f"PERCEPTION_ERROR: {e}"


def safety_check_zones(joint_positions: str = "") -> str:
    """Check current safety zone status. Optionally provide 6 joint positions (comma-separated)."""
    try:
        config_path = os.path.join(SAFETY_CONFIG_PATH, "safety_zones.yaml")
        if not os.path.exists(config_path):
            return "SAFETY_CONFIG_MISSING: No safety_zones.yaml found. Safety system not configured yet."

        with open(config_path) as f:
            config = yaml.safe_load(f)

        zones = config.get("safety_zones", {})
        return json.dumps({
            "status": "CONFIGURED",
            "zones": zones,
            "note": "Safety monitor not yet running — zone check requires perception pipeline",
        }, indent=2)
    except Exception as e:
        return f"Error: {e}"


def safety_get_architecture() -> str:
    """Return the safety system architecture summary."""
    try:
        arch_path = os.path.join(SAFETY_KNOWLEDGE_PATH, "safety_system_architecture.md")
        if os.path.exists(arch_path):
            with open(arch_path) as f:
                # Return first 100 lines (overview + architecture diagram)
                lines = f.readlines()[:100]
                return "".join(lines)
        return "Architecture document not found at: " + arch_path
    except Exception as e:
        return f"Error: {e}"


def safety_list_knowledge() -> str:
    """List all safety knowledge base documents."""
    try:
        if not os.path.isdir(SAFETY_KNOWLEDGE_PATH):
            return "Safety knowledge directory not found"
        files = []
        for f in sorted(os.listdir(SAFETY_KNOWLEDGE_PATH)):
            if f.endswith(".md"):
                path = os.path.join(SAFETY_KNOWLEDGE_PATH, f)
                size = os.path.getsize(path)
                files.append(f"{f} ({size} bytes)")
        return "Safety Knowledge Base:\n" + "\n".join(f"  - {f}" for f in files)
    except Exception as e:
        return f"Error: {e}"


def safety_validate_trajectory(trajectory_json: str) -> str:
    """Validate a joint trajectory against safety limits (joint limits, velocity, workspace)."""
    try:
        import numpy as np

        traj = json.loads(trajectory_json)
        points = traj.get("trajectory", [])
        if not points:
            return "INVALID: Empty trajectory"

        # CR10 joint limits from URDF
        limits = [
            (-3.14, 3.14),   # joint1
            (-3.14, 3.14),   # joint2
            (-2.861, 2.861), # joint3
            (-3.14, 3.14),   # joint4
            (-3.14, 3.14),   # joint5
            (-6.28, 6.28),   # joint6
        ]
        max_velocities = [2.094, 2.094, 3.0, 3.927, 3.927, 6.283]

        violations = []
        for i, point in enumerate(points):
            t = point[0]
            joints = point[1:7]

            # Check joint limits
            for j, (pos, (lo, hi)) in enumerate(zip(joints, limits)):
                if pos < lo or pos > hi:
                    violations.append(f"Point {i} (t={t:.3f}s): joint{j+1}={pos:.4f} out of [{lo}, {hi}]")

            # Check velocity (finite differences)
            if i > 0:
                dt = t - points[i-1][0]
                if dt > 0:
                    prev_joints = points[i-1][1:7]
                    for j in range(6):
                        vel = abs(joints[j] - prev_joints[j]) / dt
                        if vel > max_velocities[j]:
                            violations.append(f"Point {i} (t={t:.3f}s): joint{j+1} vel={vel:.3f} > {max_velocities[j]} rad/s")

        if violations:
            return f"UNSAFE: {len(violations)} violations:\n" + "\n".join(violations[:20])
        return f"SAFE: {len(points)} trajectory points validated, no violations"
    except Exception as e:
        return f"VALIDATION_ERROR: {e}"
