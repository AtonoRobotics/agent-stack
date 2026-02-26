# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
Fleet management: SSH execution, file transfer, connectivity checks, and system info.
"""

import subprocess
import yaml
import os
import shlex


FLEET_CONFIG_PATH = os.path.expanduser("~/agent-stack/config/fleet.yml")


def _load_fleet_config() -> dict:
    """Load fleet configuration from fleet.yml."""
    try:
        with open(FLEET_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


# Load config at import time for convenience
_fleet_config = _load_fleet_config()


def _get_machine(machine_name: str) -> dict:
    """
    Return machine config dict from fleet.yml.

    Args:
        machine_name: Name of the machine.

    Returns:
        Machine config dict with keys like user, host, os, gpu, etc.

    Raises:
        ValueError: If the machine is not in fleet config.
    """
    config = _load_fleet_config()
    machines = config.get("machines", {})
    if machine_name not in machines:
        raise ValueError(
            f"Machine '{machine_name}' not found in fleet config. "
            f"Available: {list(machines.keys())}"
        )
    return machines[machine_name]


def ssh_execute(command: str, machine: str, timeout: int = 30) -> dict:
    """
    Execute a command on a remote machine via SSH.

    Args:
        command: Shell command to run remotely.
        machine: Machine name from fleet config.
        timeout: Timeout in seconds.

    Returns:
        Dict with stdout, stderr, returncode.
    """
    m = _get_machine(machine)
    user = m["user"]
    host = m["host"]
    escaped = shlex.quote(command)

    full_cmd = (
        f"ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no "
        f"{user}@{host} {escaped}"
    )

    try:
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"SSH command timed out after {timeout}s",
            "returncode": -1,
        }


def scp_upload(local_path: str, remote_path: str, machine: str) -> bool:
    """
    Upload a local file to a remote machine via SCP.

    Args:
        local_path: Path to the local file.
        remote_path: Destination path on the remote machine.
        machine: Machine name from fleet config.

    Returns:
        True if successful.
    """
    m = _get_machine(machine)
    user = m["user"]
    host = m["host"]

    cmd = (
        f"scp -o ConnectTimeout=5 -o StrictHostKeyChecking=no "
        f"{shlex.quote(local_path)} {user}@{host}:{shlex.quote(remote_path)}"
    )

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
    return result.returncode == 0


def scp_download(remote_path: str, local_path: str, machine: str) -> bool:
    """
    Download a file from a remote machine via SCP.

    Args:
        remote_path: Path on the remote machine.
        local_path: Local destination path.
        machine: Machine name from fleet config.

    Returns:
        True if successful.
    """
    m = _get_machine(machine)
    user = m["user"]
    host = m["host"]

    # Ensure local parent directory exists
    local_dir = os.path.dirname(local_path)
    if local_dir:
        os.makedirs(local_dir, exist_ok=True)

    cmd = (
        f"scp -o ConnectTimeout=5 -o StrictHostKeyChecking=no "
        f"{user}@{host}:{shlex.quote(remote_path)} {shlex.quote(local_path)}"
    )

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
    return result.returncode == 0


def check_connectivity(machine: str) -> bool:
    """
    Check if a remote machine is reachable via SSH.

    Args:
        machine: Machine name from fleet config.

    Returns:
        True if reachable.
    """
    try:
        result = ssh_execute("echo ok", machine, timeout=10)
        return result["returncode"] == 0 and "ok" in result["stdout"]
    except (ValueError, subprocess.TimeoutExpired, Exception):
        return False


def get_system_info(machine: str) -> dict:
    """
    Gather system information from a remote machine.

    Args:
        machine: Machine name from fleet config.

    Returns:
        Dict with os, arch, uptime, load_avg, ip.
    """
    info = {
        "os": "",
        "arch": "",
        "uptime": "",
        "load_avg": "",
        "ip": "",
    }

    # uname -a for OS and arch
    uname_result = ssh_execute("uname -a", machine, timeout=10)
    if uname_result["returncode"] == 0:
        uname_out = uname_result["stdout"].strip()
        info["os"] = uname_out
        # Extract arch from uname output (typically the second-to-last or last field)
        parts = uname_out.split()
        if parts:
            info["arch"] = parts[-2] if len(parts) >= 2 else parts[-1]

    # uptime
    uptime_result = ssh_execute("uptime", machine, timeout=10)
    if uptime_result["returncode"] == 0:
        info["uptime"] = uptime_result["stdout"].strip()

    # load average
    load_result = ssh_execute("cat /proc/loadavg", machine, timeout=10)
    if load_result["returncode"] == 0:
        info["load_avg"] = load_result["stdout"].strip()

    # IP addresses
    ip_result = ssh_execute("hostname -I", machine, timeout=10)
    if ip_result["returncode"] == 0:
        info["ip"] = ip_result["stdout"].strip()

    return info
