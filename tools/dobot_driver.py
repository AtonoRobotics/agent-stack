#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Async TCP/IP driver for Dobot CR10 robot arm.

Provides direct hardware communication as an alternative to ROS2 subprocess calls.
Manages three TCP connections:
  - Dashboard (29999): Status queries
  - Control (30003): Motion commands
  - Feedback (30004): 100Hz telemetry stream
"""

import asyncio
import json
import logging
import math
from collections import deque
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

# CR10 joint limits in degrees (from URDF/spec)
CR10_JOINT_LIMITS = [
    (-360, 360),   # J1
    (-160, 160),   # J2
    (-160, 160),   # J3
    (-360, 360),   # J4
    (-360, 360),   # J5
    (-360, 360),   # J6
]


class SafetyError(Exception):
    """Raised when a commanded motion would violate joint limits."""
    pass


class DobotConnection:
    """Single async TCP socket with auto-reconnect and exponential backoff."""

    def __init__(self, host: str, port: int, name: str = ""):
        self.host = host
        self.port = port
        self.name = name or f"{host}:{port}"
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._backoff = 1.0
        self._max_backoff = 30.0

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Open TCP connection. Returns True on success."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=5.0
            )
            self._connected = True
            self._backoff = 1.0
            logger.info(f"[{self.name}] Connected to {self.host}:{self.port}")
            return True
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning(f"[{self.name}] Connection failed: {exc}")
            self._connected = False
            return False

    async def disconnect(self):
        """Close connection."""
        self._connected = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        logger.info(f"[{self.name}] Disconnected")

    async def reconnect(self) -> bool:
        """Reconnect with exponential backoff: 1s -> 2s -> 4s -> max 30s."""
        await self.disconnect()
        logger.info(f"[{self.name}] Reconnecting in {self._backoff:.0f}s...")
        await asyncio.sleep(self._backoff)
        self._backoff = min(self._backoff * 2, self._max_backoff)
        return await self.connect()

    async def send_command(self, cmd: str) -> str:
        """Send a command string and read the response line.

        Used for request-response ports (29999 dashboard, 30003 control).
        """
        if not self._connected or not self._writer:
            raise ConnectionError(f"[{self.name}] Not connected")
        try:
            self._writer.write((cmd.strip() + "\n").encode())
            await self._writer.drain()
            data = await asyncio.wait_for(self._reader.readline(), timeout=5.0)
            return data.decode().strip()
        except (OSError, asyncio.TimeoutError, AttributeError) as exc:
            self._connected = False
            raise ConnectionError(f"[{self.name}] Command failed: {exc}")

    async def read_stream(self) -> AsyncGenerator[str, None]:
        """Yield lines continuously from a streaming port (30004 feedback)."""
        if not self._connected or not self._reader:
            raise ConnectionError(f"[{self.name}] Not connected")
        while self._connected:
            try:
                data = await asyncio.wait_for(self._reader.readline(), timeout=2.0)
                if not data:
                    self._connected = False
                    break
                yield data.decode().strip()
            except asyncio.TimeoutError:
                continue
            except (OSError, AttributeError):
                self._connected = False
                break


class DobotCR10Driver:
    """High-level async driver for Dobot CR10 managing 3 TCP connections.

    Ports:
      - dashboard (29999): Robot status, mode queries
      - control (30003): Motion commands (MovJ, MovL, etc.)
      - feedback (30004): 100Hz continuous telemetry stream
    """

    def __init__(self, host: str = "192.168.5.1",
                 dashboard_port: int = 29999,
                 control_port: int = 30003,
                 feedback_port: int = 30004):
        self._dashboard = DobotConnection(host, dashboard_port, "dashboard")
        self._control = DobotConnection(host, control_port, "control")
        self._feedback = DobotConnection(host, feedback_port, "feedback")
        self._feedback_task: Optional[asyncio.Task] = None
        self._feedback_buffer: deque = deque(maxlen=600)
        self._latest_feedback: Optional[dict] = None
        self._streaming = False

    async def connect(self) -> dict:
        """Open all three TCP connections. Returns connection status."""
        results = await asyncio.gather(
            self._dashboard.connect(),
            self._control.connect(),
            self._feedback.connect(),
            return_exceptions=True,
        )
        return {
            "dashboard": results[0] is True,
            "control": results[1] is True,
            "feedback": results[2] is True,
        }

    async def disconnect(self):
        """Close all connections and stop streaming."""
        await self.stop_feedback_stream()
        await asyncio.gather(
            self._dashboard.disconnect(),
            self._control.disconnect(),
            self._feedback.disconnect(),
        )

    @property
    def connection_status(self) -> dict:
        """Current connection state of all three ports."""
        return {
            "dashboard": self._dashboard.connected,
            "control": self._control.connected,
            "feedback": self._feedback.connected,
        }

    async def get_robot_status(self) -> str:
        """Query robot status via dashboard port (29999)."""
        try:
            return await self._dashboard.send_command("get_robot_status")
        except ConnectionError:
            if await self._dashboard.reconnect():
                return await self._dashboard.send_command("get_robot_status")
            raise

    async def get_robot_mode(self) -> str:
        """Query robot mode via dashboard port."""
        try:
            return await self._dashboard.send_command("RobotMode()")
        except ConnectionError:
            if await self._dashboard.reconnect():
                return await self._dashboard.send_command("RobotMode()")
            raise

    def validate_joint_angles(self, angles: list[float]):
        """Validate joint angles against CR10 limits. Raises SafetyError."""
        if len(angles) != 6:
            raise SafetyError(f"Expected 6 joint angles, got {len(angles)}")
        for i, (angle, (lo, hi)) in enumerate(zip(angles, CR10_JOINT_LIMITS)):
            if not (lo <= angle <= hi):
                raise SafetyError(
                    f"J{i+1} angle {angle:.2f}° out of range [{lo}, {hi}]"
                )

    async def set_joint_angles(self, angles: list[float]) -> str:
        """Command joint motion via control port (30003).

        Validates limits first, then sends MovJ command.
        """
        self.validate_joint_angles(angles)
        cmd = "MovJ({})".format(",".join(f"{a:.4f}" for a in angles))
        try:
            return await self._control.send_command(cmd)
        except ConnectionError:
            if await self._control.reconnect():
                return await self._control.send_command(cmd)
            raise

    async def start_feedback_stream(self):
        """Start background task reading 100Hz feedback from port 30004."""
        if self._streaming:
            return
        self._streaming = True
        self._feedback_task = asyncio.create_task(self._feedback_loop())
        logger.info("Feedback stream started")

    async def stop_feedback_stream(self):
        """Stop the feedback streaming task."""
        self._streaming = False
        if self._feedback_task and not self._feedback_task.done():
            self._feedback_task.cancel()
            try:
                await self._feedback_task
            except asyncio.CancelledError:
                pass
        self._feedback_task = None
        logger.info("Feedback stream stopped")

    async def _feedback_loop(self):
        """Internal loop that reads feedback and stores in ring buffer."""
        while self._streaming:
            try:
                if not self._feedback.connected:
                    if not await self._feedback.reconnect():
                        await asyncio.sleep(2)
                        continue

                async for line in self._feedback.read_stream():
                    if not self._streaming:
                        break
                    try:
                        frame = json.loads(line)
                    except json.JSONDecodeError:
                        # Try parsing as comma-separated values
                        frame = self._parse_csv_feedback(line)
                    if frame:
                        self._latest_feedback = frame
                        self._feedback_buffer.append(frame)
            except Exception as exc:
                logger.warning(f"Feedback stream error: {exc}")
                if self._streaming:
                    await asyncio.sleep(1)

    @staticmethod
    def _parse_csv_feedback(line: str) -> Optional[dict]:
        """Parse CSV-format feedback into a dict."""
        parts = line.split(",")
        if len(parts) < 12:
            return None
        try:
            return {
                "joints": [
                    {"position_deg": float(parts[i]), "velocity": float(parts[i+6])}
                    for i in range(6)
                ],
            }
        except (ValueError, IndexError):
            return None

    @property
    def latest_feedback(self) -> Optional[dict]:
        """Most recent feedback frame."""
        return self._latest_feedback

    def get_feedback_history(self, n: int = 300) -> list[dict]:
        """Last N feedback frames from ring buffer."""
        buf = list(self._feedback_buffer)
        return buf[-n:] if len(buf) > n else buf

    async def get_full_status(self) -> dict:
        """Get combined status matching robot_status.get_full_status() shape.

        Returns: {online, status, joints[], mode, pose}
        """
        try:
            raw_status = await self.get_robot_status()
        except ConnectionError:
            return {
                "online": False,
                "status": "offline",
                "joints": [],
                "mode": "unknown",
                "pose": None,
            }

        # Parse status response
        online = "error" not in raw_status.lower()

        # Get mode
        try:
            mode_str = await self.get_robot_mode()
        except ConnectionError:
            mode_str = "unknown"

        # Build joints from latest feedback or empty
        joints = []
        fb = self._latest_feedback
        if fb and "joints" in fb:
            for i, jdata in enumerate(fb["joints"][:6]):
                pos_deg = jdata.get("position_deg", 0.0)
                vel = jdata.get("velocity", 0.0)
                joints.append({
                    "name": f"joint_{i+1}",
                    "position": math.radians(pos_deg),
                    "position_deg": pos_deg,
                    "velocity": vel,
                    "effort": jdata.get("effort", 0.0),
                })

        # Compute pose from joints if available
        pose = None
        if len(joints) >= 6:
            pose = self._compute_pose([j["position"] for j in joints])

        return {
            "online": online,
            "status": "online" if online else "offline",
            "joints": joints,
            "mode": mode_str,
            "pose": pose,
        }

    @staticmethod
    def _compute_pose(q: list[float]) -> dict:
        """Simplified FK using CR10 DH parameters."""
        d1, a2, a3 = 0.1765, 0.607, 0.568
        d4, d5 = 0.191, 0.125

        c1, s1 = math.cos(q[0]), math.sin(q[0])
        c2, s2 = math.cos(q[1]), math.sin(q[1])
        c23 = math.cos(q[1] + q[2])
        s23 = math.sin(q[1] + q[2])

        x = c1 * (a2 * c2 + a3 * c23) - d5 * s1
        y = s1 * (a2 * c2 + a3 * c23) + d5 * c1
        z = d1 + a2 * s2 + a3 * s23 + d4

        return {
            "x": round(x, 4),
            "y": round(y, 4),
            "z": round(z, 4),
            "rx": round(math.degrees(q[3]), 2),
            "ry": round(math.degrees(q[4]), 2),
            "rz": round(math.degrees(q[5]), 2),
        }
