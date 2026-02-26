# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Trajectory execution skill for Isaac Sim."""
import os
import json
import logging
import time

logger = logging.getLogger("skill.trajectory_execution")
BASE_DIR = os.path.expanduser("~/agent-stack")


class TrajectoryExecutionSkill:
    """Executes planned trajectories in Isaac Sim with logging and comparison."""

    def execute(self, trajectory: str = "trajectory", robot: str = "robot",
                control_dt: float = 0.01) -> dict:
        """Generate trajectory execution code for Isaac Sim.

        trajectory: variable name of the planned trajectory (JointState tensor)
        robot: variable name of the robot articulation
        """
        code = f'''import numpy as np
from omni.isaac.core.utils.types import ArticulationAction

# Execute trajectory on robot
trajectory_np = {trajectory}.position.cpu().numpy()
velocity_np = {trajectory}.velocity.cpu().numpy() if {trajectory}.velocity is not None else None
n_waypoints = trajectory_np.shape[0]
control_dt = {control_dt}

print(f"Executing trajectory: {{n_waypoints}} waypoints at {{1.0/control_dt:.0f}} Hz")

executed_positions = []
executed_timestamps = []

for i in range(n_waypoints):
    target_positions = trajectory_np[i]
    target_velocities = velocity_np[i] if velocity_np is not None else None

    action = ArticulationAction(
        joint_positions=target_positions,
        joint_velocities=target_velocities,
    )
    {robot}.apply_action(action)

    # Step simulation
    world.step(render=True)

    # Record actual state
    actual_positions = {robot}.get_joint_positions()
    executed_positions.append(actual_positions.tolist())
    executed_timestamps.append(i * control_dt)

    if i % max(1, n_waypoints // 10) == 0:
        print(f"  Step {{i}}/{{n_waypoints}} - position error: "
              f"{{np.linalg.norm(target_positions - actual_positions):.6f}} rad")

executed_positions = np.array(executed_positions)
print(f"Execution complete. Final position error: "
      f"{{np.linalg.norm(trajectory_np[-1] - executed_positions[-1]):.6f}} rad")
'''
        logger.info(f"Generated execution code: {trajectory} on {robot}")
        return {
            "code": code,
            "trajectory_var": trajectory,
            "robot_var": robot,
            "control_dt": control_dt,
        }

    def execute_with_logging(self, trajectory: str = "trajectory",
                             robot: str = "robot",
                             log_path: str = None,
                             control_dt: float = 0.01) -> dict:
        """Execute trajectory with full data logging to file."""
        log_path = log_path or os.path.join(BASE_DIR, "logs", "trajectory_log.json")
        log_dir = os.path.dirname(log_path)

        code = f'''import numpy as np
import json
import os
import time
from omni.isaac.core.utils.types import ArticulationAction

# Ensure log directory exists
os.makedirs("{log_dir}", exist_ok=True)

trajectory_np = {trajectory}.position.cpu().numpy()
velocity_np = {trajectory}.velocity.cpu().numpy() if {trajectory}.velocity is not None else None
n_waypoints = trajectory_np.shape[0]
control_dt = {control_dt}

print(f"Executing trajectory with logging: {{n_waypoints}} waypoints")
print(f"Log file: {log_path}")

log_data = {{
    "metadata": {{
        "n_waypoints": int(n_waypoints),
        "control_dt": control_dt,
        "start_time": time.time(),
        "n_dof": int(trajectory_np.shape[1]),
    }},
    "commanded": [],
    "actual": [],
    "errors": [],
    "timestamps": [],
    "velocities": [],
    "torques": [],
}}

for i in range(n_waypoints):
    target_pos = trajectory_np[i]
    target_vel = velocity_np[i] if velocity_np is not None else np.zeros_like(target_pos)

    action = ArticulationAction(
        joint_positions=target_pos,
        joint_velocities=target_vel,
    )
    {robot}.apply_action(action)
    world.step(render=True)

    # Record all telemetry
    actual_pos = {robot}.get_joint_positions()
    actual_vel = {robot}.get_joint_velocities()
    actual_torques = {robot}.get_applied_joint_efforts()

    error = target_pos - actual_pos
    log_data["commanded"].append(target_pos.tolist())
    log_data["actual"].append(actual_pos.tolist())
    log_data["errors"].append(error.tolist())
    log_data["timestamps"].append(i * control_dt)
    log_data["velocities"].append(actual_vel.tolist())
    log_data["torques"].append(actual_torques.tolist())

log_data["metadata"]["end_time"] = time.time()
log_data["metadata"]["duration"] = log_data["metadata"]["end_time"] - log_data["metadata"]["start_time"]

# Compute summary statistics
errors_np = np.array(log_data["errors"])
log_data["summary"] = {{
    "mean_error": float(np.mean(np.linalg.norm(errors_np, axis=1))),
    "max_error": float(np.max(np.linalg.norm(errors_np, axis=1))),
    "std_error": float(np.std(np.linalg.norm(errors_np, axis=1))),
    "max_torque": float(np.max(np.abs(np.array(log_data["torques"])))),
    "max_velocity": float(np.max(np.abs(np.array(log_data["velocities"])))),
}}

# Save log
with open("{log_path}", "w") as f:
    json.dump(log_data, f, indent=2)

print(f"Execution complete. Log saved to {log_path}")
print(f"  Mean error: {{log_data['summary']['mean_error']:.6f}} rad")
print(f"  Max error: {{log_data['summary']['max_error']:.6f}} rad")
print(f"  Duration: {{log_data['metadata']['duration']:.2f}} s")
'''
        logger.info(f"Generated logged execution to {log_path}")
        return {
            "code": code,
            "trajectory_var": trajectory,
            "robot_var": robot,
            "log_path": log_path,
            "control_dt": control_dt,
        }

    def execute_comparison(self, traj_a: str = "traj_a", traj_b: str = "traj_b",
                           robots: list = None) -> dict:
        """Side-by-side execution of two trajectories for comparison."""
        robots = robots or ["robot_a", "robot_b"]
        code = f'''import numpy as np
from omni.isaac.core.utils.types import ArticulationAction

# Execute two trajectories side-by-side
traj_a_np = {traj_a}.position.cpu().numpy()
traj_b_np = {traj_b}.position.cpu().numpy()

# Pad shorter trajectory to match length
max_len = max(len(traj_a_np), len(traj_b_np))
if len(traj_a_np) < max_len:
    pad = np.tile(traj_a_np[-1:], (max_len - len(traj_a_np), 1))
    traj_a_np = np.vstack([traj_a_np, pad])
if len(traj_b_np) < max_len:
    pad = np.tile(traj_b_np[-1:], (max_len - len(traj_b_np), 1))
    traj_b_np = np.vstack([traj_b_np, pad])

print(f"Comparing trajectories: {{max_len}} steps")

results_a = []
results_b = []
ee_positions_a = []
ee_positions_b = []

for i in range(max_len):
    # Execute on robot A
    action_a = ArticulationAction(joint_positions=traj_a_np[i])
    {robots[0]}.apply_action(action_a)

    # Execute on robot B
    action_b = ArticulationAction(joint_positions=traj_b_np[i])
    {robots[1]}.apply_action(action_b)

    world.step(render=True)

    # Record end-effector positions for comparison
    pos_a = {robots[0]}.get_joint_positions()
    pos_b = {robots[1]}.get_joint_positions()
    results_a.append(pos_a.tolist())
    results_b.append(pos_b.tolist())

    # Get EE world positions if available
    ee_a = {robots[0]}.get_world_pose()
    ee_b = {robots[1]}.get_world_pose()
    ee_positions_a.append(ee_a[0].tolist())
    ee_positions_b.append(ee_b[0].tolist())

# Compute comparison metrics
results_a = np.array(results_a)
results_b = np.array(results_b)
ee_a = np.array(ee_positions_a)
ee_b = np.array(ee_positions_b)

joint_diff = np.linalg.norm(results_a - results_b, axis=1)
ee_diff = np.linalg.norm(ee_a - ee_b, axis=1)

comparison = {{
    "joint_space_diff": {{
        "mean": float(np.mean(joint_diff)),
        "max": float(np.max(joint_diff)),
        "std": float(np.std(joint_diff)),
    }},
    "cartesian_diff": {{
        "mean": float(np.mean(ee_diff)),
        "max": float(np.max(ee_diff)),
        "std": float(np.std(ee_diff)),
    }},
    "trajectory_lengths": {{
        "a": len(traj_a_np),
        "b": len(traj_b_np),
    }},
}}

print(f"Comparison results:")
print(f"  Joint space - mean diff: {{comparison['joint_space_diff']['mean']:.6f}} rad")
print(f"  Cartesian   - mean diff: {{comparison['cartesian_diff']['mean']:.4f}} m")
'''
        logger.info(f"Generated comparison execution: {traj_a} vs {traj_b}")
        return {
            "code": code,
            "traj_a_var": traj_a,
            "traj_b_var": traj_b,
            "robots": robots,
        }

    def emergency_stop(self, robot: str = "robot") -> dict:
        """Generate emergency stop code - zero velocity command on all joints."""
        code = f'''import numpy as np
from omni.isaac.core.utils.types import ArticulationAction

# EMERGENCY STOP - Zero all joint velocities immediately
n_dof = {robot}.num_dof

# Send zero velocity command
zero_vel = np.zeros(n_dof)
zero_effort = np.zeros(n_dof)
current_pos = {robot}.get_joint_positions()

stop_action = ArticulationAction(
    joint_positions=current_pos,  # hold current position
    joint_velocities=zero_vel,
    joint_efforts=zero_effort,
)
{robot}.apply_action(stop_action)

# Apply for several steps to ensure stop
for _ in range(10):
    {robot}.apply_action(stop_action)
    world.step(render=False)

# Verify stop
final_vel = {robot}.get_joint_velocities()
max_residual_vel = float(np.max(np.abs(final_vel)))
stopped = max_residual_vel < 0.001

print(f"EMERGENCY STOP executed on {robot}")
print(f"  Held position: {{current_pos.tolist()}}")
print(f"  Residual velocity: {{max_residual_vel:.6f}} rad/s")
print(f"  Fully stopped: {{stopped}}")
'''
        logger.info(f"Generated emergency stop for {robot}")
        return {
            "code": code,
            "robot_var": robot,
            "action": "emergency_stop",
        }
