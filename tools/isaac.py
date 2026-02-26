# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
NVIDIA Isaac Sim process management and log retrieval.
"""

import os
from tools.bash import execute, RequiresApprovalError


# Common Isaac Sim log paths to check
ISAAC_LOG_PATHS = [
    os.path.expanduser("~/.nvidia-omniverse/logs/Kit/Isaac-Sim"),
    os.path.expanduser("~/.local/share/ov/data/Kit/Isaac-Sim"),
    "/var/log/isaac-sim",
    os.path.expanduser("~/Documents/Kit/Isaac-Sim"),
]


def get_status() -> dict:
    """
    Check if Isaac Sim is currently running.

    Returns:
        Dict with keys: running (bool), pid (int or None), uptime (str).
    """
    result = execute("pgrep -a -f 'isaac-sim\\|Isaac\\|omni.kit' | head -1")

    if result["returncode"] != 0 or not result["stdout"].strip():
        return {"running": False, "pid": None, "uptime": ""}

    line = result["stdout"].strip().split("\n")[0]
    parts = line.split(None, 1)
    pid = int(parts[0]) if parts else None

    # Get uptime via ps
    uptime_str = ""
    if pid:
        uptime_result = execute(f"ps -p {pid} -o etime= 2>/dev/null")
        if uptime_result["returncode"] == 0:
            uptime_str = uptime_result["stdout"].strip()

    return {"running": True, "pid": pid, "uptime": uptime_str}


def get_logs(lines: int = 100) -> str:
    """
    Read Isaac Sim log file from the most common log paths.

    Args:
        lines: Number of tail lines to return.

    Returns:
        Log content string, or an error message if no logs found.
    """
    for log_dir in ISAAC_LOG_PATHS:
        if not os.path.isdir(log_dir):
            continue

        # Find the most recent log file
        result = execute(
            f"find {log_dir} -name '*.log' -type f -printf '%T@ %p\\n' "
            f"2>/dev/null | sort -rn | head -1"
        )
        if result["returncode"] == 0 and result["stdout"].strip():
            log_file = result["stdout"].strip().split(None, 1)[-1]
            tail_result = execute(f"tail -n {lines} '{log_file}'")
            if tail_result["returncode"] == 0:
                return tail_result["stdout"]

    return f"No Isaac Sim logs found. Checked paths: {ISAAC_LOG_PATHS}"


def start_sim(scene_path: str) -> bool:
    """
    Launch Isaac Sim with a given scene file.

    Args:
        scene_path: Path to the .usd or .usda scene file.

    Returns:
        True if the launch command was issued successfully.
    """
    # Common Isaac Sim launch script locations
    isaac_paths = [
        os.path.expanduser("~/.local/share/ov/pkg/isaac-sim-latest/isaac-sim.sh"),
        "/opt/nvidia/isaac-sim/isaac-sim.sh",
        os.path.expanduser("~/isaac-sim/isaac-sim.sh"),
    ]

    launcher = None
    for path in isaac_paths:
        check = execute(f"test -x '{path}' && echo found")
        if check["returncode"] == 0 and "found" in check["stdout"]:
            launcher = path
            break

    if launcher is None:
        # Try finding it
        find_result = execute("which isaac-sim 2>/dev/null || find /opt -name 'isaac-sim.sh' -type f 2>/dev/null | head -1")
        found = find_result["stdout"].strip()
        if found:
            launcher = found.split("\n")[0]
        else:
            raise FileNotFoundError("Isaac Sim launcher not found on this system")

    # Launch in background with nohup
    result = execute(f"nohup '{launcher}' --open '{scene_path}' > /dev/null 2>&1 &")
    return result["returncode"] == 0


def stop_sim() -> bool:
    """
    Stop the running Isaac Sim process.
    This is a destructive operation and raises RequiresApprovalError.

    Raises:
        RequiresApprovalError: Always, since stopping a simulation is destructive.
    """
    raise RequiresApprovalError("kill Isaac Sim process (pkill -f isaac-sim)")


def get_running_scenes() -> list:
    """
    Get a list of running Isaac Sim instances and their scene files.

    Returns:
        List of dicts with keys: pid, command, scene.
    """
    result = execute("pgrep -a -f 'isaac-sim\\|Isaac\\|omni.kit'")
    if result["returncode"] != 0 or not result["stdout"].strip():
        return []

    scenes = []
    for line in result["stdout"].strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        pid = int(parts[0])
        command = parts[1] if len(parts) > 1 else ""

        # Try to extract scene path from command line args
        scene = ""
        if "--open" in command:
            idx = command.index("--open")
            rest = command[idx + len("--open"):].strip()
            scene = rest.split()[0] if rest.split() else ""
        elif ".usd" in command:
            # Try to find a .usd/.usda path in the command
            for token in command.split():
                if ".usd" in token:
                    scene = token
                    break

        scenes.append({"pid": pid, "command": command, "scene": scene})

    return scenes
