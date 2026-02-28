# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""ROS2 bridge event source.

Since ROS2 is not installed natively on the host, this bridge uses
docker exec to query ROS2 topics and diagnostics from running containers.
Emits events when joint limits are approached or diagnostics report warnings.
"""

import asyncio
import logging
import subprocess

from orchestrator.bus import EventBus
from orchestrator.events import OrchestratorEvent, EventPriority

logger = logging.getLogger("orchestrator.sources.ros2_bridge")


class ROS2Bridge:
    """Monitors ROS2 topics via Docker exec and emits orchestrator events."""

    def __init__(self, bus: EventBus, interval: int = 10,
                 container_name: str = "isaac-ros-dev"):
        self.bus = bus
        self.interval = interval
        self.container = container_name

    def _docker_exec(self, cmd: str, timeout: int = 5) -> str:
        """Run a command inside the ROS2 container."""
        try:
            r = subprocess.run(
                f"docker exec {self.container} bash -c '{cmd}'",
                shell=True, capture_output=True, text=True, timeout=timeout,
            )
            return r.stdout.strip() if r.returncode == 0 else ""
        except (subprocess.TimeoutExpired, Exception):
            return ""

    def _container_running(self) -> bool:
        """Check if the ROS2 container is running."""
        try:
            r = subprocess.run(
                f"docker ps --filter name={self.container} --format '{{{{.Names}}}}'",
                shell=True, capture_output=True, text=True, timeout=5,
            )
            return self.container in r.stdout
        except Exception:
            return False

    async def run(self):
        """Main monitoring loop."""
        logger.info(f"ROS2Bridge started (container={self.container}, interval={self.interval}s)")

        while True:
            try:
                # Check if container is running
                running = await asyncio.get_event_loop().run_in_executor(
                    None, self._container_running
                )

                if not running:
                    logger.debug(f"ROS2 container '{self.container}' not running, skipping")
                    await asyncio.sleep(self.interval)
                    continue

                # Check diagnostics
                diag_output = await asyncio.get_event_loop().run_in_executor(
                    None, self._docker_exec,
                    "ros2 topic echo /diagnostics --once --no-daemon 2>/dev/null | head -50",
                )

                if diag_output:
                    # Parse for warnings/errors
                    if "ERROR" in diag_output.upper() or "WARN" in diag_output.upper():
                        await self.bus.put(OrchestratorEvent(
                            priority=EventPriority.HIGH,
                            source="ros2",
                            event_type="diagnostic_warning",
                            payload={
                                "container": self.container,
                                "diagnostics": diag_output[:1000],
                                "task": f"ROS2 diagnostic warning detected in {self.container}. Review and address: {diag_output[:200]}",
                            },
                        ))

                # Check joint states for limit warnings
                joint_output = await asyncio.get_event_loop().run_in_executor(
                    None, self._docker_exec,
                    "ros2 topic echo /joint_states --once --no-daemon 2>/dev/null | head -20",
                )

                if joint_output and "position:" in joint_output:
                    # Parse joint positions and check against limits
                    # CR10 joint limits (radians): ±2π for most joints
                    import re
                    positions = re.findall(r"[-+]?\d*\.?\d+", joint_output.split("position:")[1].split("velocity:")[0])
                    for i, pos_str in enumerate(positions):
                        pos = float(pos_str)
                        if abs(pos) > 5.5:  # ~315 degrees, approaching ±2π limit
                            await self.bus.put(OrchestratorEvent(
                                priority=EventPriority.CRITICAL,
                                source="ros2",
                                event_type="joint_limit",
                                payload={
                                    "joint_index": i,
                                    "position_rad": pos,
                                    "task": f"Joint {i} approaching limit at {pos:.2f} rad. Trigger safety stop if needed.",
                                },
                            ))

            except Exception as e:
                logger.error(f"ROS2Bridge error: {e}")

            await asyncio.sleep(self.interval)
