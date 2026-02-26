# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
Git repository operations with safety gating on main/master push.
"""

import shlex
from tools.bash import execute, execute_approved, RequiresApprovalError


def clone(url: str, path: str) -> bool:
    """
    Clone a git repository.

    Args:
        url: Repository URL.
        path: Local directory to clone into.

    Returns:
        True if successful.
    """
    result = execute(f"git clone {shlex.quote(url)} {shlex.quote(path)}")
    return result["returncode"] == 0


def commit(message: str, path: str) -> bool:
    """
    Stage all changes and commit.

    Args:
        message: Commit message.
        path: Path to the git repository.

    Returns:
        True if successful.
    """
    escaped_msg = shlex.quote(message)
    escaped_path = shlex.quote(path)
    result = execute(f"git -C {escaped_path} add -A && git -C {escaped_path} commit -m {escaped_msg}")
    return result["returncode"] == 0


def push(branch: str, path: str) -> bool:
    """
    Push a branch to the remote. Raises RequiresApprovalError for main/master.

    Args:
        branch: Branch name to push.
        path: Path to the git repository.

    Returns:
        True if successful.
    """
    if branch in ("main", "master"):
        raise RequiresApprovalError(f"git push origin {branch}")

    escaped_path = shlex.quote(path)
    result = execute(f"git -C {escaped_path} push origin {shlex.quote(branch)}")
    return result["returncode"] == 0


def pull(path: str) -> bool:
    """
    Pull latest changes from the remote.

    Args:
        path: Path to the git repository.

    Returns:
        True if successful.
    """
    escaped_path = shlex.quote(path)
    result = execute(f"git -C {escaped_path} pull")
    return result["returncode"] == 0


def status(path: str) -> str:
    """
    Get the git status of a repository.

    Args:
        path: Path to the git repository.

    Returns:
        Status output string.
    """
    escaped_path = shlex.quote(path)
    result = execute(f"git -C {escaped_path} status")
    return result["stdout"]


def create_branch(name: str, path: str) -> bool:
    """
    Create and checkout a new branch.

    Args:
        name: Branch name.
        path: Path to the git repository.

    Returns:
        True if successful.
    """
    escaped_path = shlex.quote(path)
    result = execute(f"git -C {escaped_path} checkout -b {shlex.quote(name)}")
    return result["returncode"] == 0


def get_log(path: str, n: int = 10) -> list:
    """
    Get recent git log entries.

    Args:
        path: Path to the git repository.
        n: Number of log entries to return.

    Returns:
        List of dicts with "hash" and "message" keys.
    """
    escaped_path = shlex.quote(path)
    result = execute(f"git -C {escaped_path} log --oneline -n {n}")
    if result["returncode"] != 0:
        return []

    entries = []
    for line in result["stdout"].strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        commit_hash = parts[0]
        message = parts[1] if len(parts) > 1 else ""
        entries.append({"hash": commit_hash, "message": message})
    return entries
