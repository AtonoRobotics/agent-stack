# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Sim-to-real transfer skill for policy deployment."""
import os
import math
import logging
import json
import subprocess

logger = logging.getLogger("skill.sim_to_real")
BASE_DIR = os.path.expanduser("~/agent-stack")


class SimToRealSkill:
    """Manages sim-to-real transfer: domain randomization, gap analysis, and policy transfer."""

    def configure_domain_randomization(self, config: dict = None) -> dict:
        """Generate comprehensive domain randomization configuration.

        config: {"physics": {...}, "visual": {...}, "dynamics": {...}, "sensor": {...}}
        """
        config = config or {}

        physics_dr = config.get("physics", {
            "gravity_range": [9.71, 9.91],
            "friction_range": [0.3, 1.2],
            "restitution_range": [0.0, 0.5],
            "contact_stiffness_range": [1e4, 1e6],
        })
        visual_dr = config.get("visual", {
            "light_intensity_range": [500, 3000],
            "light_color_temp_range": [3000, 7000],
            "texture_randomize": True,
            "background_randomize": True,
        })
        dynamics_dr = config.get("dynamics", {
            "mass_scale_range": [0.8, 1.2],
            "inertia_scale_range": [0.8, 1.2],
            "joint_damping_scale": [0.5, 2.0],
            "joint_friction_scale": [0.5, 2.0],
            "actuator_delay_range": [0.0, 0.02],
        })
        sensor_dr = config.get("sensor", {
            "camera_noise_std": 0.01,
            "imu_bias_range": [-0.02, 0.02],
            "encoder_noise_std": 0.001,
            "force_torque_noise_std": 0.5,
        })

        code = f'''import numpy as np
import random

class DomainRandomizer:
    """Applies domain randomization for sim-to-real transfer."""

    def __init__(self, seed=None):
        if seed is not None:
            np.random.seed(seed)
            random.seed(seed)

        self.physics = {json.dumps(physics_dr, indent=8)}
        self.visual = {json.dumps(visual_dr, indent=8)}
        self.dynamics = {json.dumps(dynamics_dr, indent=8)}
        self.sensor = {json.dumps(sensor_dr, indent=8)}

    def randomize_physics(self, stage):
        """Randomize physics parameters."""
        gravity = np.random.uniform(*self.physics["gravity_range"])
        friction = np.random.uniform(*self.physics["friction_range"])
        restitution = np.random.uniform(*self.physics["restitution_range"])

        physics_scene = stage.GetPrimAtPath("/physicsScene")
        physics_scene.GetAttribute("physics:gravityMagnitude").Set(gravity)

        return {{"gravity": gravity, "friction": friction, "restitution": restitution}}

    def randomize_dynamics(self, robot):
        """Randomize robot dynamics parameters."""
        mass_scale = np.random.uniform(*self.dynamics["mass_scale_range"])
        inertia_scale = np.random.uniform(*self.dynamics["inertia_scale_range"])
        damping_scale = np.random.uniform(*self.dynamics["joint_damping_scale"])

        # Apply scales to all links
        for link in robot.get_links():
            original_mass = link.get_mass()
            link.set_mass(original_mass * mass_scale)

        # Apply actuator delay
        delay = np.random.uniform(*self.dynamics["actuator_delay_range"])

        return {{
            "mass_scale": mass_scale,
            "inertia_scale": inertia_scale,
            "damping_scale": damping_scale,
            "actuator_delay": delay,
        }}

    def randomize_sensors(self, sensors):
        """Add noise to sensor readings."""
        noisy = {{}}
        for name, reading in sensors.items():
            noise = np.random.normal(0, self.sensor.get(f"{{name}}_noise_std", 0.01),
                                     size=np.array(reading).shape)
            noisy[name] = (np.array(reading) + noise).tolist()
        return noisy

    def randomize_visual(self, stage):
        """Randomize visual properties."""
        intensity = np.random.uniform(*self.visual["light_intensity_range"])
        color_temp = np.random.uniform(*self.visual["light_color_temp_range"])
        return {{"intensity": intensity, "color_temp": color_temp}}

    def apply_all(self, stage, robot, sensors):
        """Apply all randomizations."""
        results = {{}}
        results["physics"] = self.randomize_physics(stage)
        results["dynamics"] = self.randomize_dynamics(robot)
        results["sensors"] = self.randomize_sensors(sensors)
        results["visual"] = self.randomize_visual(stage)
        return results

domain_randomizer = DomainRandomizer()
'''
        full_config = {
            "physics": physics_dr,
            "visual": visual_dr,
            "dynamics": dynamics_dr,
            "sensor": sensor_dr,
        }
        logger.info("Configured domain randomization")
        return {"code": code, "config": full_config}

    def benchmark_reality_gap(self, sim_trajectories: list, real_trajectories: list,
                               metrics: list = None) -> dict:
        """Benchmark the sim-to-real gap across multiple metrics.

        sim_trajectories: list of sim trajectories (each is list of joint angles)
        real_trajectories: list of corresponding real trajectories
        metrics: list of metric names to compute
        """
        metrics = metrics or ["position_error", "velocity_error", "timing_error",
                               "path_length_ratio"]

        n_trajs = min(len(sim_trajectories), len(real_trajectories))
        if n_trajs == 0:
            return {"error": "No trajectories to compare"}

        results_per_metric = {}

        for metric in metrics:
            metric_values = []
            for t in range(n_trajs):
                sim = sim_trajectories[t]
                real = real_trajectories[t]
                n = min(len(sim), len(real))

                if metric == "position_error":
                    errors = []
                    for i in range(n):
                        s = sim[i] if isinstance(sim[i], (list, tuple)) else [sim[i]]
                        r = real[i] if isinstance(real[i], (list, tuple)) else [real[i]]
                        err = math.sqrt(sum((a - b) ** 2 for a, b in zip(s, r)))
                        errors.append(err)
                    metric_values.append({
                        "mean": sum(errors) / len(errors) if errors else 0,
                        "max": max(errors) if errors else 0,
                        "rms": math.sqrt(sum(e ** 2 for e in errors) / len(errors)) if errors else 0,
                    })

                elif metric == "velocity_error":
                    # Compute numerical velocities and compare
                    if n < 2:
                        metric_values.append({"mean": 0, "max": 0, "rms": 0})
                        continue
                    sim_vel = []
                    real_vel = []
                    for i in range(1, n):
                        s_curr = sim[i] if isinstance(sim[i], list) else [sim[i]]
                        s_prev = sim[i - 1] if isinstance(sim[i - 1], list) else [sim[i - 1]]
                        r_curr = real[i] if isinstance(real[i], list) else [real[i]]
                        r_prev = real[i - 1] if isinstance(real[i - 1], list) else [real[i - 1]]
                        sim_vel.append([c - p for c, p in zip(s_curr, s_prev)])
                        real_vel.append([c - p for c, p in zip(r_curr, r_prev)])

                    vel_errors = [
                        math.sqrt(sum((s - r) ** 2 for s, r in zip(sv, rv)))
                        for sv, rv in zip(sim_vel, real_vel)
                    ]
                    metric_values.append({
                        "mean": sum(vel_errors) / len(vel_errors),
                        "max": max(vel_errors),
                        "rms": math.sqrt(sum(e ** 2 for e in vel_errors) / len(vel_errors)),
                    })

                elif metric == "path_length_ratio":
                    def path_length(traj):
                        total = 0.0
                        for i in range(1, len(traj)):
                            curr = traj[i] if isinstance(traj[i], list) else [traj[i]]
                            prev = traj[i - 1] if isinstance(traj[i - 1], list) else [traj[i - 1]]
                            total += math.sqrt(sum((c - p) ** 2 for c, p in zip(curr, prev)))
                        return total

                    sl = path_length(sim[:n])
                    rl = path_length(real[:n])
                    ratio = sl / rl if rl > 0 else float("inf")
                    metric_values.append({"sim_length": sl, "real_length": rl, "ratio": ratio})

                elif metric == "timing_error":
                    length_diff = abs(len(sim) - len(real))
                    ratio = len(sim) / len(real) if len(real) > 0 else float("inf")
                    metric_values.append({"length_diff": length_diff, "ratio": ratio})

            results_per_metric[metric] = metric_values

        # Aggregate
        summary = {}
        for metric, values in results_per_metric.items():
            if values and "mean" in values[0]:
                means = [v["mean"] for v in values]
                summary[metric] = {
                    "avg_mean": sum(means) / len(means),
                    "worst_mean": max(means),
                    "n_trajectories": len(values),
                }
            elif values and "ratio" in values[0]:
                ratios = [v["ratio"] for v in values if v["ratio"] != float("inf")]
                summary[metric] = {
                    "avg_ratio": sum(ratios) / len(ratios) if ratios else 0,
                    "n_trajectories": len(values),
                }

        result = {
            "n_trajectories": n_trajs,
            "metrics": results_per_metric,
            "summary": summary,
        }
        logger.info(f"Reality gap benchmark: {n_trajs} trajectories, {len(metrics)} metrics")
        return result

    def transfer_policy(self, policy_path: str, target_config: dict = None) -> dict:
        """Generate code to transfer a trained policy for real-robot deployment.

        Handles observation/action space normalization and adapter layers.
        """
        target_config = target_config or {}
        obs_scale = target_config.get("observation_scale", 1.0)
        act_scale = target_config.get("action_scale", 1.0)
        control_freq = target_config.get("control_frequency_hz", 30)
        device = target_config.get("device", "cuda:0")

        code = f'''import torch
import numpy as np
import time

class PolicyTransferWrapper:
    """Wraps a sim-trained policy for real-robot deployment."""

    def __init__(self, policy_path, device="{device}"):
        self.device = torch.device(device)
        self.policy = torch.jit.load(policy_path, map_location=self.device)
        self.policy.eval()

        # Normalization parameters (from training)
        self.obs_mean = None
        self.obs_std = None
        self.act_scale = {act_scale}
        self.obs_scale = {obs_scale}
        self.control_dt = 1.0 / {control_freq}

        # Safety limits
        self.max_joint_delta = 0.1  # rad per step
        self.max_velocity = 2.0    # rad/s
        self.prev_action = None

    def load_normalization(self, stats_path):
        """Load observation normalization stats from training."""
        stats = torch.load(stats_path, map_location=self.device)
        self.obs_mean = stats.get("obs_mean", torch.zeros(1))
        self.obs_std = stats.get("obs_std", torch.ones(1))

    def normalize_observation(self, obs):
        """Normalize observation using training statistics."""
        obs_t = torch.tensor(obs, dtype=torch.float32, device=self.device)
        obs_t *= self.obs_scale
        if self.obs_mean is not None and self.obs_std is not None:
            obs_t = (obs_t - self.obs_mean) / (self.obs_std + 1e-8)
        return obs_t.unsqueeze(0)  # add batch dimension

    def denormalize_action(self, action):
        """Convert policy output to joint commands."""
        action_np = action.squeeze(0).cpu().numpy()
        action_np *= self.act_scale
        return action_np

    def safety_filter(self, action, current_pos):
        """Apply safety limits to action before sending to robot."""
        if self.prev_action is not None:
            delta = action - self.prev_action
            delta = np.clip(delta, -self.max_joint_delta, self.max_joint_delta)
            action = self.prev_action + delta

        self.prev_action = action.copy()
        return action

    @torch.no_grad()
    def get_action(self, observation, current_joint_pos):
        """Get safe action from policy given observation."""
        obs_normalized = self.normalize_observation(observation)
        raw_action = self.policy(obs_normalized)
        action = self.denormalize_action(raw_action)
        safe_action = self.safety_filter(action, current_joint_pos)
        return safe_action

    def run_control_loop(self, robot, get_observation_fn, duration=10.0):
        """Run the policy control loop on the real robot."""
        print(f"Starting policy control loop at {{1.0/self.control_dt:.0f}} Hz")
        start_time = time.monotonic()
        step = 0

        while time.monotonic() - start_time < duration:
            loop_start = time.monotonic()

            obs = get_observation_fn()
            current_pos = robot.get_joint_positions()
            action = self.get_action(obs, current_pos)
            robot.set_joint_positions(action)

            step += 1
            elapsed = time.monotonic() - loop_start
            sleep_time = self.control_dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        print(f"Control loop finished: {{step}} steps in {{duration:.1f}}s")
        return step

# Deploy
wrapper = PolicyTransferWrapper("{policy_path}")
'''
        logger.info(f"Generated policy transfer wrapper for {policy_path}")
        return {
            "code": code,
            "policy_path": policy_path,
            "control_frequency_hz": control_freq,
            "target_config": target_config,
        }

    def validate_transfer(self, sim_results: dict, real_results: dict,
                           thresholds: dict = None) -> dict:
        """Validate that transferred policy meets performance thresholds.

        sim_results: {"success_rate": float, "mean_reward": float, ...}
        real_results: {"success_rate": float, "mean_reward": float, ...}
        thresholds: {"success_rate_drop": float, "reward_drop_pct": float}
        """
        thresholds = thresholds or {
            "success_rate_drop": 0.15,  # max 15% drop allowed
            "reward_drop_pct": 25.0,     # max 25% reward drop
            "min_success_rate": 0.70,    # minimum absolute success rate
        }

        sim_sr = sim_results.get("success_rate", 0.0)
        real_sr = real_results.get("success_rate", 0.0)
        sr_drop = sim_sr - real_sr

        sim_reward = sim_results.get("mean_reward", 0.0)
        real_reward = real_results.get("mean_reward", 0.0)
        reward_drop_pct = (
            100.0 * (sim_reward - real_reward) / abs(sim_reward)
            if abs(sim_reward) > 1e-6 else 0.0
        )

        checks = {
            "success_rate_drop": {
                "value": sr_drop,
                "threshold": thresholds["success_rate_drop"],
                "passed": sr_drop <= thresholds["success_rate_drop"],
            },
            "reward_drop_pct": {
                "value": reward_drop_pct,
                "threshold": thresholds["reward_drop_pct"],
                "passed": reward_drop_pct <= thresholds["reward_drop_pct"],
            },
            "min_success_rate": {
                "value": real_sr,
                "threshold": thresholds["min_success_rate"],
                "passed": real_sr >= thresholds["min_success_rate"],
            },
        }

        all_passed = all(c["passed"] for c in checks.values())

        # Additional analysis
        comparison = {}
        for key in set(sim_results.keys()) | set(real_results.keys()):
            if key in sim_results and key in real_results:
                s = sim_results[key]
                r = real_results[key]
                if isinstance(s, (int, float)) and isinstance(r, (int, float)):
                    comparison[key] = {
                        "sim": s, "real": r,
                        "diff": s - r,
                        "pct_change": 100.0 * (r - s) / abs(s) if abs(s) > 1e-6 else 0.0,
                    }

        result = {
            "passed": all_passed,
            "checks": checks,
            "comparison": comparison,
            "recommendation": (
                "Transfer validated - ready for deployment"
                if all_passed else
                "Transfer validation failed - consider additional domain randomization or fine-tuning"
            ),
        }
        logger.info(f"Transfer validation: {'PASS' if all_passed else 'FAIL'} "
                     f"(SR drop={sr_drop:.2f}, reward drop={reward_drop_pct:.1f}%)")
        return result
