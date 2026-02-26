# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
ROS 2 node and topic monitoring utilities.
"""

from tools.bash import execute


def list_nodes() -> list:
    """
    List all active ROS 2 nodes.

    Returns:
        List of node name strings.
    """
    result = execute("ros2 node list")
    if result["returncode"] != 0:
        return []

    nodes = []
    for line in result["stdout"].strip().split("\n"):
        line = line.strip()
        if line:
            nodes.append(line)
    return nodes


def list_topics() -> list:
    """
    List all active ROS 2 topics.

    Returns:
        List of topic name strings.
    """
    result = execute("ros2 topic list")
    if result["returncode"] != 0:
        return []

    topics = []
    for line in result["stdout"].strip().split("\n"):
        line = line.strip()
        if line:
            topics.append(line)
    return topics


def get_node_logs(node_name: str, lines: int = 100) -> str:
    """
    Get recent logs for a ROS 2 node from journalctl.

    Args:
        node_name: Name of the node (e.g. "/my_node").
        lines: Number of log lines to retrieve.

    Returns:
        Log output string.
    """
    # Strip leading slash if present for the unit/grep match
    clean_name = node_name.lstrip("/")
    result = execute(f"journalctl -t {clean_name} --no-pager -n {lines}")

    # Fallback: grep journalctl output for the node name
    if result["returncode"] != 0 or not result["stdout"].strip():
        result = execute(f"journalctl --no-pager -n {lines} | grep -i {clean_name}")

    return result["stdout"]


def check_health() -> dict:
    """
    Check the health of the ROS 2 system.

    Returns:
        Dict with keys: daemon_running (bool), nodes_active (int), nodes (list).
    """
    health = {
        "daemon_running": False,
        "nodes_active": 0,
        "nodes": [],
    }

    # Check daemon status
    daemon_result = execute("ros2 daemon status")
    if daemon_result["returncode"] == 0:
        output = daemon_result["stdout"].strip().lower()
        health["daemon_running"] = "running" in output

    # Get active nodes
    nodes = list_nodes()
    health["nodes"] = nodes
    health["nodes_active"] = len(nodes)

    return health


def restart_daemon() -> bool:
    """
    Restart the ROS 2 daemon.

    Returns:
        True if the daemon was restarted successfully.
    """
    result = execute("ros2 daemon stop && ros2 daemon start")
    return result["returncode"] == 0
