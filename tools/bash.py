# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
Safe bash command execution with destructive-command gating.
"""

import subprocess
import shlex
import os
import yaml


FLEET_CONFIG_PATH = os.path.expanduser("~/agent-stack/config/fleet.yml")


class RequiresApprovalError(Exception):
    """Raised when a command matches a destructive pattern and needs explicit approval."""

    def __init__(self, command):
        self.command = command
        super().__init__(f"Destructive command requires approval: {command}")


DESTRUCTIVE_PATTERNS = [
    "rm -rf",
    "apt remove",
    "apt purge",
    "systemctl stop",
    "systemctl disable",
    "docker rm",
    "docker rmi",
    "docker stop",
    "pkill",
    "kill -9",
    "> /dev/",
    "mkfs",
    "dd if=",
    "chmod 000",
    "chown root",
]


def _load_fleet_config() -> dict:
    """Load fleet configuration from fleet.yml."""
    try:
        with open(FLEET_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _get_ssh_target(machine: str) -> str:
    """Get user@host string for a given machine name."""
    config = _load_fleet_config()
    machines = config.get("machines", {})
    if machine not in machines:
        raise ValueError(f"Machine '{machine}' not found in fleet config")
    m = machines[machine]
    return f"{m['user']}@{m['host']}"


def is_destructive(command: str) -> bool:
    """
    Check if a command matches any known destructive pattern.

    Args:
        command: The shell command string.

    Returns:
        True if the command contains a destructive pattern.
    """
    return any(pattern in command for pattern in DESTRUCTIVE_PATTERNS)


def execute(command: str, machine: str = "local", timeout: int = 120) -> dict:
    """
    Execute a shell command locally or remotely via SSH.
    Raises RequiresApprovalError if the command is destructive.

    Args:
        command: Shell command to run.
        machine: Machine name from fleet config, or "local".
        timeout: Timeout in seconds.

    Returns:
        Dict with keys: stdout, stderr, returncode.
    """
    if is_destructive(command):
        raise RequiresApprovalError(command)

    return _run_command(command, machine, timeout)


def execute_approved(command: str, machine: str = "local", timeout: int = 120) -> dict:
    """
    Execute a shell command without destructive-command checks.
    Use this only after the user has explicitly approved the action.

    Args:
        command: Shell command to run.
        machine: Machine name from fleet config, or "local".
        timeout: Timeout in seconds.

    Returns:
        Dict with keys: stdout, stderr, returncode.
    """
    return _run_command(command, machine, timeout)


def _run_command(command: str, machine: str, timeout: int) -> dict:
    """Internal: run a command locally or via SSH."""
    if machine != "local":
        ssh_target = _get_ssh_target(machine)
        escaped = shlex.quote(command)
        full_cmd = (
            f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "
            f"{ssh_target} {escaped}"
        )
    else:
        full_cmd = command

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
            "stderr": f"Command timed out after {timeout}s",
            "returncode": -1,
        }
