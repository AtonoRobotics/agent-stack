# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
Docker container management with approval gating for destructive operations.
"""

import json
from tools.bash import execute, execute_approved, RequiresApprovalError


AUTO_APPROVED = {"start", "pull", "build", "logs", "ps"}
REQUIRES_APPROVAL = {"stop", "rm", "rmi", "prune"}


def _run(cmd: str, machine: str = "local") -> dict:
    """
    Run a docker command, routing through execute or execute_approved
    based on whether the docker action requires approval.

    Args:
        cmd: The full docker command (e.g. "docker ps -a").
        machine: Machine name or "local".

    Returns:
        Dict with stdout, stderr, returncode.
    """
    # Extract the docker subcommand (first word after "docker")
    parts = cmd.strip().split()
    action = None
    for i, part in enumerate(parts):
        if part == "docker" or part.startswith("docker"):
            if i + 1 < len(parts):
                action = parts[i + 1]
            break

    if action in REQUIRES_APPROVAL:
        return execute_approved(cmd, machine=machine)
    else:
        return execute(cmd, machine=machine)


def list_containers(machine: str = "local") -> list:
    """
    List all containers (running and stopped).

    Args:
        machine: Machine name or "local".

    Returns:
        List of dicts with container info.
    """
    result = _run("docker ps -a --format json", machine=machine)
    if result["returncode"] != 0:
        return []

    containers = []
    for line in result["stdout"].strip().split("\n"):
        line = line.strip()
        if line:
            try:
                containers.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return containers


def start(container: str, machine: str = "local") -> bool:
    """
    Start a stopped container.

    Args:
        container: Container name or ID.
        machine: Machine name or "local".

    Returns:
        True if successful.
    """
    result = execute(f"docker start {container}", machine=machine)
    return result["returncode"] == 0


def stop(container: str, machine: str = "local") -> bool:
    """
    Stop a running container. Raises RequiresApprovalError via bash layer.

    Args:
        container: Container name or ID.
        machine: Machine name or "local".

    Returns:
        True if successful.
    """
    # docker stop is in DESTRUCTIVE_PATTERNS, so execute() will raise RequiresApprovalError.
    # Use execute_approved since _run routes approval-required actions through it.
    result = execute_approved(f"docker stop {container}", machine=machine)
    return result["returncode"] == 0


def build(dockerfile: str, tag: str, machine: str = "local") -> bool:
    """
    Build a Docker image.

    Args:
        dockerfile: Path to the Dockerfile or build context directory.
        tag: Image tag (e.g. "myapp:latest").
        machine: Machine name or "local".

    Returns:
        True if the build succeeds.
    """
    result = execute(f"docker build -t {tag} -f {dockerfile} .", machine=machine)
    return result["returncode"] == 0


def pull(image: str, machine: str = "local") -> bool:
    """
    Pull a Docker image from a registry.

    Args:
        image: Image name (e.g. "nvidia/cuda:12.0-devel-ubuntu22.04").
        machine: Machine name or "local".

    Returns:
        True if successful.
    """
    result = execute(f"docker pull {image}", machine=machine)
    return result["returncode"] == 0


def remove(container: str, machine: str = "local") -> bool:
    """
    Remove a container. Raises RequiresApprovalError via bash layer.

    Args:
        container: Container name or ID.
        machine: Machine name or "local".

    Returns:
        True if successful.
    """
    # docker rm is in DESTRUCTIVE_PATTERNS, so execute() will raise.
    # Use execute_approved since this is an explicitly destructive action.
    result = execute_approved(f"docker rm {container}", machine=machine)
    return result["returncode"] == 0


def logs(container: str, machine: str = "local", tail: int = 100) -> str:
    """
    Get container logs.

    Args:
        container: Container name or ID.
        machine: Machine name or "local".
        tail: Number of lines from the end.

    Returns:
        Log output string.
    """
    result = execute(f"docker logs --tail {tail} {container}", machine=machine)
    return result["stdout"] + result["stderr"]
