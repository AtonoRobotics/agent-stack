#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""ROS2 robot status collection via subprocess for Dobot CR10.

Supports dual data sources: ROS2 (subprocess) and TCP (async driver).
"""

import asyncio
import json
import logging
import math
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

# ── Dual-source state ────────────────────────────────────
_dobot_driver = None  # Optional DobotCR10Driver instance
_data_source: str = "ros2"  # "ros2" or "tcp"
_ros2_executor = ThreadPoolExecutor(max_workers=1)


def _run_ros2_cmd(args: list, timeout: float = 5.0) -> Optional[str]:
    """Run a ROS2 CLI command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _offline_response(extra: dict = None) -> dict:
    """Return a standard offline response."""
    resp = {"status": "offline", "online": False}
    if extra:
        resp.update(extra)
    return resp


def get_joint_states() -> dict:
    """Get current joint states from /joint_states topic."""
    output = _run_ros2_cmd(
        ["ros2", "topic", "echo", "/joint_states", "--once", "--no-arr"]
    )
    if not output:
        return _offline_response({"joints": []})

    joints = []
    names = []
    positions = []
    velocities = []
    efforts = []

    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("name:"):
            names = _parse_yaml_list(line.split(":", 1)[1])
        elif line.startswith("position:"):
            positions = _parse_float_list(line.split(":", 1)[1])
        elif line.startswith("velocity:"):
            velocities = _parse_float_list(line.split(":", 1)[1])
        elif line.startswith("effort:"):
            efforts = _parse_float_list(line.split(":", 1)[1])

    for i, name in enumerate(names):
        joints.append({
            "name": name,
            "position": positions[i] if i < len(positions) else 0.0,
            "velocity": velocities[i] if i < len(velocities) else 0.0,
            "effort": efforts[i] if i < len(efforts) else 0.0,
            "position_deg": math.degrees(positions[i]) if i < len(positions) else 0.0,
        })

    return {"status": "online", "online": True, "joints": joints}


def _parse_yaml_list(s: str) -> list:
    """Parse a YAML-style list string like '[a, b, c]'."""
    s = s.strip().strip("[]")
    if not s:
        return []
    return [item.strip().strip("'\"") for item in s.split(",")]


def _parse_float_list(s: str) -> list:
    """Parse a YAML-style float list string."""
    s = s.strip().strip("[]")
    if not s:
        return []
    result = []
    for item in s.split(","):
        try:
            result.append(float(item.strip()))
        except ValueError:
            result.append(0.0)
    return result


def get_robot_mode() -> dict:
    """Get robot operating mode from /robot_mode topic."""
    output = _run_ros2_cmd(
        ["ros2", "topic", "echo", "/robot_mode", "--once"]
    )
    if not output:
        return _offline_response({"mode": "unknown"})

    mode = "unknown"
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("data:") or line.startswith("mode:"):
            mode = line.split(":", 1)[1].strip().strip("'\"")
            break

    return {"status": "online", "online": True, "mode": mode}


def get_end_effector_pose() -> dict:
    """Compute end-effector pose via forward kinematics from joint states.

    Uses simplified CR10 DH parameters for FK calculation.
    """
    joints_data = get_joint_states()
    if not joints_data.get("online"):
        return _offline_response({"pose": None})

    joints = joints_data.get("joints", [])
    if len(joints) < 6:
        return _offline_response({"pose": None, "reason": "insufficient_joints"})

    q = [j["position"] for j in joints[:6]]

    # Simplified FK using CR10 link lengths
    # d1=0.1765, a2=0.607, a3=0.568, d4=0.191, d5=0.125, d6=0.1084
    d1 = 0.1765
    a2 = 0.607
    a3 = 0.568
    d4 = 0.191
    d5 = 0.125
    d6 = 0.1084

    c1, s1 = math.cos(q[0]), math.sin(q[0])
    c2, s2 = math.cos(q[1]), math.sin(q[1])
    c23 = math.cos(q[1] + q[2])
    s23 = math.sin(q[1] + q[2])

    # Approximate wrist center position
    x = c1 * (a2 * c2 + a3 * c23) - d5 * s1
    y = s1 * (a2 * c2 + a3 * c23) + d5 * c1
    z = d1 + a2 * s2 + a3 * s23 + d4

    return {
        "status": "online",
        "online": True,
        "pose": {
            "x": round(x, 4),
            "y": round(y, 4),
            "z": round(z, 4),
            "rx": round(math.degrees(q[3]), 2),
            "ry": round(math.degrees(q[4]), 2),
            "rz": round(math.degrees(q[5]), 2),
        },
    }


def get_controller_state() -> dict:
    """Get active controllers from ros2_control."""
    output = _run_ros2_cmd(
        ["ros2", "control", "list_controllers"], timeout=5.0
    )
    if not output:
        return _offline_response({"controllers": []})

    controllers = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            controllers.append({
                "name": parts[0],
                "state": parts[1] if len(parts) > 1 else "unknown",
                "type": parts[2] if len(parts) > 2 else "",
            })

    return {"status": "online", "online": True, "controllers": controllers}


def get_robot_diagnostics() -> dict:
    """Get robot diagnostics from /diagnostics topic."""
    output = _run_ros2_cmd(
        ["ros2", "topic", "echo", "/diagnostics", "--once"], timeout=5.0
    )
    if not output:
        return _offline_response({"diagnostics": []})

    diags = []
    current = {}
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("name:"):
            if current:
                diags.append(current)
            current = {"name": line.split(":", 1)[1].strip().strip("'\""), "level": 0, "message": ""}
        elif line.startswith("level:"):
            try:
                current["level"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("message:"):
            current["message"] = line.split(":", 1)[1].strip().strip("'\"")

    if current:
        diags.append(current)

    return {"status": "online", "online": True, "diagnostics": diags}


def get_all_topics_data() -> dict:
    """List all active ROS2 topics with their types."""
    output = _run_ros2_cmd(["ros2", "topic", "list", "-t"])
    if not output:
        return _offline_response({"topics": []})

    topics = []
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Format: /topic_name [msg_type]
        if " [" in line:
            name, msg_type = line.rsplit(" [", 1)
            msg_type = msg_type.rstrip("]")
        else:
            name = line
            msg_type = ""
        topics.append({"name": name.strip(), "type": msg_type})

    return {"status": "online", "online": True, "topics": topics}


def get_topic_value(topic_name: str) -> dict:
    """Echo a single message from a topic."""
    if not topic_name.startswith("/"):
        topic_name = "/" + topic_name

    output = _run_ros2_cmd(
        ["ros2", "topic", "echo", topic_name, "--once"], timeout=5.0
    )
    if not output:
        return _offline_response({"topic": topic_name, "value": None})

    return {
        "status": "online",
        "online": True,
        "topic": topic_name,
        "value": output,
    }


def get_full_status() -> dict:
    """Get combined robot status for the cockpit."""
    joints = get_joint_states()
    mode = get_robot_mode()

    online = joints.get("online", False)

    result = {
        "online": online,
        "status": "online" if online else "offline",
        "joints": joints.get("joints", []),
        "mode": mode.get("mode", "unknown"),
    }

    if online:
        pose = get_end_effector_pose()
        result["pose"] = pose.get("pose")

    return result


# ── Dual-source abstraction ──────────────────────────────

async def init_tcp_driver(host: str = "192.168.5.1",
                          dashboard_port: int = 29999,
                          control_port: int = 30003,
                          feedback_port: int = 30004) -> dict:
    """Create and connect the TCP driver. Returns connection status."""
    global _dobot_driver
    from tools.dobot_driver import DobotCR10Driver
    _dobot_driver = DobotCR10Driver(host, dashboard_port, control_port, feedback_port)
    status = await _dobot_driver.connect()
    if status.get("feedback"):
        await _dobot_driver.start_feedback_stream()
    logger.info(f"TCP driver initialized: {status}")
    return status


async def disconnect_tcp_driver():
    """Disconnect and tear down the TCP driver."""
    global _dobot_driver
    if _dobot_driver:
        await _dobot_driver.disconnect()
        _dobot_driver = None
    logger.info("TCP driver disconnected")


def get_data_source() -> str:
    """Return current data source: 'ros2' or 'tcp'."""
    return _data_source


def set_data_source(source: str):
    """Switch data source. Must be 'ros2' or 'tcp'."""
    global _data_source
    if source not in ("ros2", "tcp"):
        raise ValueError(f"Invalid data source: {source}")
    _data_source = source
    logger.info(f"Data source set to: {source}")


async def get_full_status_async() -> dict:
    """Get full robot status from the active data source.

    If tcp: uses the async driver directly.
    If ros2: runs the sync get_full_status() in a thread executor.
    """
    if _data_source == "tcp" and _dobot_driver:
        return await _dobot_driver.get_full_status()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_ros2_executor, get_full_status)


def get_tcp_connection_status() -> dict:
    """Return TCP driver connection status, or all-disconnected if no driver."""
    if _dobot_driver:
        return _dobot_driver.connection_status
    return {"dashboard": False, "control": False, "feedback": False}


def get_tcp_driver():
    """Return the TCP driver instance (or None)."""
    return _dobot_driver
