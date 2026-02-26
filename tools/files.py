# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
File operations (read, write, append, search, exists, list) for local and remote machines.
"""

import os
import subprocess
import glob as globmod
import shlex
import yaml


FLEET_CONFIG_PATH = os.path.expanduser("~/agent-stack/config/fleet.yml")


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


def _ssh_run(command: str, machine: str, input_data: str = None, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a command on a remote machine via SSH."""
    ssh_target = _get_ssh_target(machine)
    escaped = shlex.quote(command)
    full_cmd = (
        f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "
        f"{ssh_target} {escaped}"
    )
    return subprocess.run(
        full_cmd,
        shell=True,
        capture_output=True,
        text=True,
        input=input_data,
        timeout=timeout,
    )


def read(path: str, machine: str = "local") -> str:
    """
    Read file contents.

    Args:
        path: Absolute path to the file.
        machine: Machine name from fleet config, or "local".

    Returns:
        File contents as a string.
    """
    if machine == "local":
        with open(path, "r") as f:
            return f.read()
    else:
        result = _ssh_run(f"cat {shlex.quote(path)}", machine)
        if result.returncode != 0:
            raise FileNotFoundError(f"Remote file not found or unreadable: {path} on {machine}: {result.stderr}")
        return result.stdout


def write(path: str, content: str, machine: str = "local") -> bool:
    """
    Write content to a file, creating parent directories if needed.

    Args:
        path: Absolute path to the file.
        content: Content to write.
        machine: Machine name from fleet config, or "local".

    Returns:
        True on success.
    """
    if machine == "local":
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return True
    else:
        ssh_target = _get_ssh_target(machine)
        escaped_path = shlex.quote(path)
        escaped_dir = shlex.quote(os.path.dirname(path))
        # Create parent directory, then write via stdin
        mkdir_cmd = (
            f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "
            f"{ssh_target} 'mkdir -p {escaped_dir}'"
        )
        subprocess.run(mkdir_cmd, shell=True, capture_output=True, text=True)

        write_cmd = (
            f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "
            f"{ssh_target} 'cat > {escaped_path}'"
        )
        result = subprocess.run(
            write_cmd,
            shell=True,
            capture_output=True,
            text=True,
            input=content,
        )
        return result.returncode == 0


def append(path: str, content: str, machine: str = "local") -> bool:
    """
    Append content to a file.

    Args:
        path: Absolute path to the file.
        content: Content to append.
        machine: Machine name from fleet config, or "local".

    Returns:
        True on success.
    """
    if machine == "local":
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "a") as f:
            f.write(content)
        return True
    else:
        ssh_target = _get_ssh_target(machine)
        escaped_path = shlex.quote(path)
        append_cmd = (
            f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "
            f"{ssh_target} 'cat >> {escaped_path}'"
        )
        result = subprocess.run(
            append_cmd,
            shell=True,
            capture_output=True,
            text=True,
            input=content,
        )
        return result.returncode == 0


def search(pattern: str, directory: str, machine: str = "local") -> list:
    """
    Search for files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g. "*.py", "**/*.yml").
        directory: Directory to search in.
        machine: Machine name from fleet config, or "local".

    Returns:
        List of matching file paths.
    """
    if machine == "local":
        full_pattern = os.path.join(directory, pattern)
        return sorted(globmod.glob(full_pattern, recursive=True))
    else:
        escaped_dir = shlex.quote(directory)
        escaped_pattern = shlex.quote(pattern)
        result = _ssh_run(f"find {escaped_dir} -name {escaped_pattern} -type f", machine)
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().split("\n")
        return sorted([l for l in lines if l])


def exists(path: str, machine: str = "local") -> bool:
    """
    Check if a file or directory exists.

    Args:
        path: Absolute path.
        machine: Machine name from fleet config, or "local".

    Returns:
        True if the path exists.
    """
    if machine == "local":
        return os.path.exists(path)
    else:
        result = _ssh_run(f"test -e {shlex.quote(path)} && echo yes || echo no", machine)
        return result.stdout.strip() == "yes"


def list_dir(path: str, machine: str = "local") -> list:
    """
    List directory contents.

    Args:
        path: Absolute path to a directory.
        machine: Machine name from fleet config, or "local".

    Returns:
        List of filenames in the directory.
    """
    if machine == "local":
        return sorted(os.listdir(path))
    else:
        result = _ssh_run(f"ls -1 {shlex.quote(path)}", machine)
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().split("\n")
        return sorted([l for l in lines if l])
