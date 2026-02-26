# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Safety testing skill for robot validation."""
import os
import math
import logging
import json

logger = logging.getLogger("skill.safety_testing")
BASE_DIR = os.path.expanduser("~/agent-stack")


class SafetyTestingSkill:
    """Runs comprehensive safety tests on robot configurations and trajectories."""

    def workspace_boundary_test(self, robot: dict, limits: dict = None) -> dict:
        """Test positions against workspace limits.

        robot: {"joint_positions": [[q1,...qn], ...], "ee_positions": [[x,y,z], ...]}
        limits: {"x": [min,max], "y": [min,max], "z": [min,max], "radius_max": float}
        """
        limits = limits or {
            "x": [-1.0, 1.0], "y": [-1.0, 1.0], "z": [0.0, 1.5], "radius_max": 1.0
        }
        ee_positions = robot.get("ee_positions", [])
        violations = []

        for i, pos in enumerate(ee_positions):
            x, y, z = pos[0], pos[1], pos[2]
            radius = math.sqrt(x ** 2 + y ** 2)
            issues = []

            if x < limits["x"][0] or x > limits["x"][1]:
                issues.append(f"x={x:.3f} outside [{limits['x'][0]}, {limits['x'][1]}]")
            if y < limits["y"][0] or y > limits["y"][1]:
                issues.append(f"y={y:.3f} outside [{limits['y'][0]}, {limits['y'][1]}]")
            if z < limits["z"][0] or z > limits["z"][1]:
                issues.append(f"z={z:.3f} outside [{limits['z'][0]}, {limits['z'][1]}]")
            if radius > limits["radius_max"]:
                issues.append(f"radius={radius:.3f} exceeds {limits['radius_max']}")

            if issues:
                violations.append({"index": i, "position": pos, "issues": issues})

        passed = len(violations) == 0
        result = {
            "test": "workspace_boundary",
            "passed": passed,
            "total_points": len(ee_positions),
            "violations": violations,
            "violation_count": len(violations),
        }
        logger.info(f"Workspace boundary test: {'PASS' if passed else 'FAIL'} "
                     f"({len(violations)} violations)")
        return result

    def collision_detection_test(self, robot: dict, obstacles: list = None) -> dict:
        """Test collision avoidance against obstacle list.

        robot: {"ee_positions": [[x,y,z], ...], "link_positions": [[[x,y,z], ...], ...]}
        obstacles: [{"position": [x,y,z], "radius": float, "name": str}, ...]
        """
        obstacles = obstacles or []
        ee_positions = robot.get("ee_positions", [])
        link_positions = robot.get("link_positions", [])
        min_clearance = float("inf")
        collisions = []

        for i, ee_pos in enumerate(ee_positions):
            for obs in obstacles:
                obs_pos = obs.get("position", [0, 0, 0])
                obs_radius = obs.get("radius", 0.05)
                safety_margin = obs.get("safety_margin", 0.02)

                dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(ee_pos, obs_pos)))
                clearance = dist - obs_radius
                min_clearance = min(min_clearance, clearance)

                if clearance < safety_margin:
                    collisions.append({
                        "timestep": i,
                        "obstacle": obs.get("name", "unknown"),
                        "clearance": clearance,
                        "ee_position": ee_pos,
                        "obstacle_position": obs_pos,
                        "collision": clearance <= 0,
                    })

            # Check link positions too
            if i < len(link_positions):
                for link_idx, link_pos in enumerate(link_positions[i]):
                    for obs in obstacles:
                        obs_pos = obs.get("position", [0, 0, 0])
                        obs_radius = obs.get("radius", 0.05)
                        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(link_pos, obs_pos)))
                        clearance = dist - obs_radius
                        min_clearance = min(min_clearance, clearance)
                        if clearance <= 0:
                            collisions.append({
                                "timestep": i,
                                "link": link_idx,
                                "obstacle": obs.get("name", "unknown"),
                                "clearance": clearance,
                                "collision": True,
                            })

        actual_collisions = [c for c in collisions if c.get("collision", False)]
        passed = len(actual_collisions) == 0

        result = {
            "test": "collision_detection",
            "passed": passed,
            "min_clearance": min_clearance if min_clearance != float("inf") else None,
            "collision_count": len(actual_collisions),
            "near_miss_count": len(collisions) - len(actual_collisions),
            "collisions": collisions,
        }
        logger.info(f"Collision test: {'PASS' if passed else 'FAIL'} "
                     f"({len(actual_collisions)} collisions, min clearance={min_clearance:.4f})")
        return result

    def emergency_stop_test(self, robot: dict) -> dict:
        """Test emergency stop response time.

        robot: {"velocities_before_stop": [v1,...], "velocities_after_stop": [[v1,...], ...],
                "stop_timestamps": [t0, t1, ...]}
        """
        vel_before = robot.get("velocities_before_stop", [1.0, 0.5, 0.3])
        vel_after = robot.get("velocities_after_stop", [])
        timestamps = robot.get("stop_timestamps", [])

        max_vel_before = max(abs(v) for v in vel_before) if vel_before else 0.0

        # Find time to reach near-zero velocity
        stop_time = None
        threshold = 0.001  # rad/s
        for i, vels in enumerate(vel_after):
            max_v = max(abs(v) for v in vels)
            if max_v < threshold:
                stop_time = timestamps[i] if i < len(timestamps) else i * 0.001
                break

        if stop_time is None and vel_after:
            stop_time = timestamps[-1] if timestamps else len(vel_after) * 0.001

        # Check final velocity
        final_vel = vel_after[-1] if vel_after else vel_before
        max_final_vel = max(abs(v) for v in final_vel) if final_vel else max_vel_before
        fully_stopped = max_final_vel < threshold

        # Response time requirement: < 100ms for collaborative robots
        response_ok = stop_time is not None and stop_time < 0.1

        passed = fully_stopped and response_ok

        result = {
            "test": "emergency_stop",
            "passed": passed,
            "max_velocity_before": max_vel_before,
            "max_velocity_after": max_final_vel,
            "stop_time_seconds": stop_time,
            "fully_stopped": fully_stopped,
            "response_within_limit": response_ok,
            "response_limit_seconds": 0.1,
        }
        logger.info(f"E-stop test: {'PASS' if passed else 'FAIL'} "
                     f"(stop_time={stop_time}s, stopped={fully_stopped})")
        return result

    def payload_limit_test(self, robot: dict, payload_range: list = None) -> dict:
        """Test payload limits across a range of payloads.

        robot: {"max_payload": float, "joint_torque_limits": [t1,...tn]}
        payload_range: list of masses to test [kg]
        """
        payload_range = payload_range or [0.0, 0.5, 1.0, 2.0, 3.0, 5.0]
        max_payload = robot.get("max_payload", 3.0)
        torque_limits = robot.get("joint_torque_limits", [100, 100, 50, 50, 20, 20, 10])

        test_results = []
        for mass in payload_range:
            # Compute worst-case torque at full extension
            # Simplified: torque = mass * gravity * max_reach_per_joint
            gravity = 9.81
            arm_lengths = [0.3, 0.3, 0.2, 0.2, 0.1, 0.1, 0.05]
            cumulative_length = sum(arm_lengths)

            joint_torques_required = []
            for j in range(min(len(torque_limits), len(arm_lengths))):
                # Torque at joint j = mass * g * distance from joint to EE
                dist_to_ee = sum(arm_lengths[j:])
                tau = mass * gravity * dist_to_ee
                joint_torques_required.append(tau)

            # Check each joint
            within_limits = all(
                tau <= limit
                for tau, limit in zip(joint_torques_required, torque_limits)
            )

            utilization = [
                tau / limit if limit > 0 else float("inf")
                for tau, limit in zip(joint_torques_required, torque_limits)
            ]

            test_results.append({
                "payload_kg": mass,
                "within_limits": within_limits,
                "max_utilization": max(utilization) if utilization else 0.0,
                "joint_torques": joint_torques_required,
                "utilization_per_joint": utilization,
            })

        max_safe_payload = max(
            (r["payload_kg"] for r in test_results if r["within_limits"]),
            default=0.0,
        )
        passed = max_safe_payload >= max_payload * 0.9

        result = {
            "test": "payload_limit",
            "passed": passed,
            "rated_payload_kg": max_payload,
            "max_safe_payload_kg": max_safe_payload,
            "test_results": test_results,
        }
        logger.info(f"Payload test: {'PASS' if passed else 'FAIL'} "
                     f"(max_safe={max_safe_payload} kg)")
        return result

    def velocity_limit_test(self, robot: dict, max_velocity: float = None) -> dict:
        """Test velocity limits throughout trajectory.

        robot: {"joint_velocities": [[v1,...vn], ...], "velocity_limits": [v1,...vn]}
        """
        max_velocity = max_velocity or 3.14  # rad/s default
        joint_velocities = robot.get("joint_velocities", [])
        velocity_limits = robot.get("velocity_limits", [max_velocity] * 7)
        violations = []

        peak_velocities = [0.0] * len(velocity_limits)

        for i, vels in enumerate(joint_velocities):
            for j, v in enumerate(vels):
                limit = velocity_limits[j] if j < len(velocity_limits) else max_velocity
                peak_velocities[j] = max(peak_velocities[j], abs(v))
                if abs(v) > limit:
                    violations.append({
                        "timestep": i,
                        "joint": j,
                        "velocity": v,
                        "limit": limit,
                        "ratio": abs(v) / limit,
                    })

        passed = len(violations) == 0

        result = {
            "test": "velocity_limit",
            "passed": passed,
            "violation_count": len(violations),
            "peak_velocities": peak_velocities,
            "velocity_limits": velocity_limits,
            "violations": violations[:20],  # cap detail output
        }
        logger.info(f"Velocity test: {'PASS' if passed else 'FAIL'} "
                     f"({len(violations)} violations)")
        return result

    def human_proximity_test(self, robot: dict, safety_zones: dict = None) -> dict:
        """Test safety zone compliance for human-robot interaction.

        robot: {"ee_positions": [[x,y,z], ...], "velocities": [[v1,...], ...]}
        safety_zones: {"danger": float, "warning": float, "reduced_speed": float}
                      distances in meters from human position.
        """
        safety_zones = safety_zones or {
            "danger": 0.2,      # full stop required
            "warning": 0.5,     # reduced speed
            "reduced_speed": 1.0,  # normal but monitored
        }
        ee_positions = robot.get("ee_positions", [])
        velocities = robot.get("velocities", [])
        human_position = robot.get("human_position", [1.0, 0.0, 0.5])

        zone_entries = {"danger": [], "warning": [], "reduced_speed": []}
        min_distance = float("inf")

        for i, ee_pos in enumerate(ee_positions):
            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(ee_pos, human_position)))
            min_distance = min(min_distance, dist)

            vel_magnitude = 0.0
            if i < len(velocities):
                vel_magnitude = math.sqrt(sum(v ** 2 for v in velocities[i]))

            if dist < safety_zones["danger"]:
                zone_entries["danger"].append({
                    "timestep": i, "distance": dist, "velocity": vel_magnitude,
                    "should_stop": True, "did_stop": vel_magnitude < 0.01,
                })
            elif dist < safety_zones["warning"]:
                max_allowed_vel = 0.25  # m/s in warning zone
                zone_entries["warning"].append({
                    "timestep": i, "distance": dist, "velocity": vel_magnitude,
                    "within_speed_limit": vel_magnitude <= max_allowed_vel,
                })
            elif dist < safety_zones["reduced_speed"]:
                max_allowed_vel = 1.0  # m/s in reduced zone
                zone_entries["reduced_speed"].append({
                    "timestep": i, "distance": dist, "velocity": vel_magnitude,
                    "within_speed_limit": vel_magnitude <= max_allowed_vel,
                })

        # Check compliance
        danger_violations = [e for e in zone_entries["danger"] if not e.get("did_stop", False)]
        warning_violations = [e for e in zone_entries["warning"]
                              if not e.get("within_speed_limit", True)]

        passed = len(danger_violations) == 0 and len(warning_violations) == 0

        result = {
            "test": "human_proximity",
            "passed": passed,
            "min_distance_to_human": min_distance,
            "danger_zone_entries": len(zone_entries["danger"]),
            "danger_violations": len(danger_violations),
            "warning_zone_entries": len(zone_entries["warning"]),
            "warning_violations": len(warning_violations),
            "reduced_speed_entries": len(zone_entries["reduced_speed"]),
            "safety_zones": safety_zones,
        }
        logger.info(f"Human proximity test: {'PASS' if passed else 'FAIL'} "
                     f"(min_dist={min_distance:.3f}m)")
        return result

    def run_full_safety_suite(self, robot: dict, config: dict = None) -> dict:
        """Run all safety tests and aggregate results."""
        config = config or {}

        results = {}
        results["workspace"] = self.workspace_boundary_test(
            robot, config.get("workspace_limits")
        )
        results["collision"] = self.collision_detection_test(
            robot, config.get("obstacles", [])
        )
        results["emergency_stop"] = self.emergency_stop_test(robot)
        results["payload"] = self.payload_limit_test(
            robot, config.get("payload_range")
        )
        results["velocity"] = self.velocity_limit_test(
            robot, config.get("max_velocity")
        )
        results["human_proximity"] = self.human_proximity_test(
            robot, config.get("safety_zones")
        )

        tests_run = len(results)
        passed = sum(1 for r in results.values() if r.get("passed", False))
        failed = tests_run - passed

        summary = {
            "tests_run": tests_run,
            "passed": passed,
            "failed": failed,
            "overall_pass": failed == 0,
            "results": results,
        }
        logger.info(f"Full safety suite: {passed}/{tests_run} passed")
        return summary

    def generate_safety_report(self, results: dict) -> str:
        """Generate markdown safety report from test results."""
        overall = results.get("overall_pass", False)
        tests_run = results.get("tests_run", 0)
        passed = results.get("passed", 0)
        failed = results.get("failed", 0)

        lines = [
            "# Safety Test Report",
            "",
            f"**Overall Status:** {'PASS' if overall else 'FAIL'}",
            f"**Tests Run:** {tests_run}",
            f"**Passed:** {passed}",
            f"**Failed:** {failed}",
            "",
            "---",
            "",
        ]

        test_details = results.get("results", {})
        for test_name, test_result in test_details.items():
            status = "PASS" if test_result.get("passed", False) else "FAIL"
            icon = "[OK]" if status == "PASS" else "[!!]"
            lines.append(f"## {icon} {test_name.replace('_', ' ').title()}")
            lines.append("")
            lines.append(f"**Status:** {status}")
            lines.append("")

            # Test-specific details
            skip_keys = {"test", "passed", "violations", "collisions", "test_results"}
            for key, value in test_result.items():
                if key in skip_keys:
                    continue
                if isinstance(value, float):
                    lines.append(f"- **{key.replace('_', ' ').title()}:** {value:.4f}")
                elif isinstance(value, list) and len(value) > 10:
                    lines.append(f"- **{key.replace('_', ' ').title()}:** [{len(value)} items]")
                else:
                    lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")

            # Show violations if any
            violations = test_result.get("violations",
                                          test_result.get("collisions", []))
            if violations and len(violations) > 0:
                lines.append("")
                lines.append(f"### Violations ({len(violations)})")
                lines.append("")
                for v in violations[:5]:
                    lines.append(f"- {json.dumps(v)}")
                if len(violations) > 5:
                    lines.append(f"- ... and {len(violations) - 5} more")

            lines.append("")
            lines.append("---")
            lines.append("")

        report = "\n".join(lines)
        logger.info(f"Generated safety report: {len(lines)} lines")
        return report
