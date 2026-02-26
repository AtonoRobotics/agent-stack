# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Analysis skill for trajectory and robot performance metrics."""
import os
import math
import logging
import json

logger = logging.getLogger("skill.analysis")
BASE_DIR = os.path.expanduser("~/agent-stack")


class AnalysisSkill:
    """Computes trajectory errors, joint torques, and generates analysis reports."""

    def compute_path_error(self, commanded: list, actual: list) -> dict:
        """Compute Euclidean path error statistics between commanded and actual trajectories.

        commanded: list of [x, y, z, ...] commanded joint/Cartesian positions
        actual: list of [x, y, z, ...] actual joint/Cartesian positions
        Returns dict with mean, max, std, and per-point errors.
        """
        if len(commanded) != len(actual):
            min_len = min(len(commanded), len(actual))
            commanded = commanded[:min_len]
            actual = actual[:min_len]
            logger.warning(f"Trajectory lengths differ, truncated to {min_len}")

        per_point_errors = []
        for cmd, act in zip(commanded, actual):
            squared_sum = sum((c - a) ** 2 for c, a in zip(cmd, act))
            error = math.sqrt(squared_sum)
            per_point_errors.append(error)

        n = len(per_point_errors)
        mean_error = sum(per_point_errors) / n if n > 0 else 0.0
        max_error = max(per_point_errors) if n > 0 else 0.0
        min_error = min(per_point_errors) if n > 0 else 0.0

        variance = sum((e - mean_error) ** 2 for e in per_point_errors) / n if n > 1 else 0.0
        std_error = math.sqrt(variance)

        # Compute per-joint statistics
        n_dims = len(commanded[0]) if commanded else 0
        per_joint = []
        for j in range(n_dims):
            joint_errors = [abs(cmd[j] - act[j]) for cmd, act in zip(commanded, actual)]
            j_mean = sum(joint_errors) / len(joint_errors)
            j_max = max(joint_errors)
            per_joint.append({"joint": j, "mean": j_mean, "max": j_max})

        # RMS error
        rms = math.sqrt(sum(e ** 2 for e in per_point_errors) / n) if n > 0 else 0.0

        result = {
            "mean_error": mean_error,
            "max_error": max_error,
            "min_error": min_error,
            "std_error": std_error,
            "rms_error": rms,
            "n_points": n,
            "per_point_errors": per_point_errors,
            "per_joint_stats": per_joint,
        }

        logger.info(f"Path error: mean={mean_error:.6f}, max={max_error:.6f}, rms={rms:.6f}")
        return result

    def compute_joint_torques(self, trajectory: list, payload: dict = None) -> dict:
        """Compute torque requirements using simplified inverse dynamics.

        trajectory: list of dicts with keys "position", "velocity", "acceleration"
                    each being a list of joint values.
        payload: {"mass": float, "com_offset": [x,y,z]}
        """
        payload = payload or {"mass": 0.0, "com_offset": [0.0, 0.0, 0.0]}
        mass = payload.get("mass", 0.0)
        gravity = 9.81

        torques_per_step = []
        for step in trajectory:
            pos = step.get("position", [])
            vel = step.get("velocity", [0.0] * len(pos))
            acc = step.get("acceleration", [0.0] * len(pos))

            n_dof = len(pos)
            step_torques = []
            for j in range(n_dof):
                # Simplified: tau = I * alpha + friction_coeff * omega + gravity_load
                # Using nominal inertias that decrease along the chain
                inertia = max(0.5 * (1.0 - j / max(n_dof, 1)), 0.05)
                friction_coeff = 0.02
                gravity_load = mass * gravity * math.cos(pos[j]) * (1.0 - j / max(n_dof, 1))

                tau = (inertia * acc[j] +
                       friction_coeff * vel[j] +
                       gravity_load)
                step_torques.append(tau)

            torques_per_step.append(step_torques)

        # Compute statistics per joint
        n_dof = len(torques_per_step[0]) if torques_per_step else 0
        joint_stats = []
        for j in range(n_dof):
            j_torques = [step[j] for step in torques_per_step]
            j_abs = [abs(t) for t in j_torques]
            joint_stats.append({
                "joint": j,
                "mean_torque": sum(j_abs) / len(j_abs),
                "max_torque": max(j_abs),
                "peak_torque": max(j_torques, key=abs),
                "rms_torque": math.sqrt(sum(t ** 2 for t in j_torques) / len(j_torques)),
            })

        result = {
            "torques": torques_per_step,
            "joint_stats": joint_stats,
            "n_steps": len(torques_per_step),
            "n_dof": n_dof,
            "payload": payload,
            "max_torque_overall": max(
                (abs(t) for step in torques_per_step for t in step), default=0.0
            ),
        }

        logger.info(f"Computed torques: {len(torques_per_step)} steps, "
                     f"max={result['max_torque_overall']:.3f} Nm")
        return result

    def generate_analysis_report(self, results: dict) -> str:
        """Generate formatted markdown report from results dict.

        results: dict with keys like "path_error", "torques", "singularity",
                 "workspace", "safety", etc. Each maps to a sub-dict of metrics.
        """
        lines = [
            "# Trajectory Analysis Report",
            "",
            f"**Generated by:** agent-stack analysis skill",
            "",
        ]

        # Path error section
        if "path_error" in results:
            pe = results["path_error"]
            lines.extend([
                "## Path Tracking Error",
                "",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Mean Error | {pe.get('mean_error', 0):.6f} |",
                f"| Max Error | {pe.get('max_error', 0):.6f} |",
                f"| RMS Error | {pe.get('rms_error', 0):.6f} |",
                f"| Std Error | {pe.get('std_error', 0):.6f} |",
                f"| Num Points | {pe.get('n_points', 0)} |",
                "",
            ])
            if "per_joint_stats" in pe:
                lines.append("### Per-Joint Error")
                lines.append("")
                lines.append("| Joint | Mean | Max |")
                lines.append("|-------|------|-----|")
                for js in pe["per_joint_stats"]:
                    lines.append(f"| {js['joint']} | {js['mean']:.6f} | {js['max']:.6f} |")
                lines.append("")

        # Torque section
        if "torques" in results:
            tq = results["torques"]
            lines.extend([
                "## Joint Torque Analysis",
                "",
                f"- **Trajectory Steps:** {tq.get('n_steps', 0)}",
                f"- **DOF:** {tq.get('n_dof', 0)}",
                f"- **Peak Torque:** {tq.get('max_torque_overall', 0):.3f} Nm",
                "",
            ])
            if "joint_stats" in tq:
                lines.append("| Joint | Mean (Nm) | Max (Nm) | RMS (Nm) |")
                lines.append("|-------|-----------|----------|----------|")
                for js in tq["joint_stats"]:
                    lines.append(
                        f"| {js['joint']} | {js['mean_torque']:.3f} | "
                        f"{js['max_torque']:.3f} | {js['rms_torque']:.3f} |"
                    )
                lines.append("")

        # Singularity section
        if "singularity" in results:
            sg = results["singularity"]
            lines.extend([
                "## Singularity Analysis",
                "",
                f"- **Points Checked:** {sg.get('total_points', 0)}",
                f"- **Near Singularity:** {sg.get('near_singular_count', 0)}",
                f"- **Min Manipulability:** {sg.get('min_manipulability', 0):.6f}",
                f"- **Mean Manipulability:** {sg.get('mean_manipulability', 0):.6f}",
                "",
            ])

        # Workspace section
        if "workspace" in results:
            ws = results["workspace"]
            lines.extend([
                "## Workspace Validation",
                "",
                f"- **Poses Checked:** {ws.get('total_poses', 0)}",
                f"- **Valid:** {ws.get('valid_count', 0)}",
                f"- **Invalid:** {ws.get('invalid_count', 0)}",
                "",
            ])

        # Safety section
        if "safety" in results:
            sf = results["safety"]
            lines.extend([
                "## Safety Summary",
                "",
                f"- **Tests Run:** {sf.get('tests_run', 0)}",
                f"- **Passed:** {sf.get('passed', 0)}",
                f"- **Failed:** {sf.get('failed', 0)}",
                f"- **Overall Status:** {'PASS' if sf.get('failed', 1) == 0 else 'FAIL'}",
                "",
            ])

        # Generic key-value fallback for any other sections
        known_keys = {"path_error", "torques", "singularity", "workspace", "safety"}
        for key, value in results.items():
            if key not in known_keys:
                lines.append(f"## {key.replace('_', ' ').title()}")
                lines.append("")
                if isinstance(value, dict):
                    for k, v in value.items():
                        lines.append(f"- **{k}:** {v}")
                else:
                    lines.append(f"{value}")
                lines.append("")

        report = "\n".join(lines)
        logger.info(f"Generated analysis report: {len(lines)} lines")
        return report
