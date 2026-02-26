# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Trajectory planning skill using cuRobo motion generation."""
import os
import math
import logging

logger = logging.getLogger("skill.trajectory_planning")
BASE_DIR = os.path.expanduser("~/agent-stack")


class TrajectoryPlanningSkill:
    """Plans robot trajectories using cuRobo motion generation and validates them."""

    def plan_cartesian(self, start_pose: dict, goal_pose: dict,
                       plan_config: dict = None) -> dict:
        """Generate cuRobo motion planning code for a Cartesian goal.

        start_pose / goal_pose: {"position": [x,y,z], "quaternion": [w,x,y,z]}
        plan_config: optional overrides for planning parameters.
        """
        plan_config = plan_config or {}
        timeout = plan_config.get("timeout", 10.0)
        num_seeds = plan_config.get("num_seeds", 12)

        sp = start_pose.get("position", [0, 0, 0])
        sq = start_pose.get("quaternion", [1, 0, 0, 0])
        gp = goal_pose.get("position", [0.4, 0.0, 0.3])
        gq = goal_pose.get("quaternion", [1, 0, 0, 0])

        code = f'''import torch
from curobo.types.math import Pose
from curobo.wrap.reacher.motion_gen import MotionGenPlanConfig

# Define start joint state (from current robot state)
start_js = motion_gen.get_retract_config()

# Define goal pose in Cartesian space
goal_pose = Pose(
    position=torch.tensor([[{gp[0]}, {gp[1]}, {gp[2]}]], device="cuda:0"),
    quaternion=torch.tensor([[{gq[0]}, {gq[1]}, {gq[2]}, {gq[3]}]], device="cuda:0"),
)

# Plan motion
plan_cfg = MotionGenPlanConfig(
    enable_graph=True,
    enable_opt=True,
    max_attempts={num_seeds},
    timeout={timeout},
    enable_finetune_trajopt=True,
)

result = motion_gen.plan_single(start_js, goal_pose, plan_cfg)

if result.success[0]:
    trajectory = result.get_interpolated_plan()
    print(f"Planning succeeded! Trajectory has {{trajectory.position.shape[0]}} waypoints")
    print(f"Trajectory duration: {{result.optimized_dt * trajectory.position.shape[0]:.3f}} s")
else:
    print(f"Planning failed: {{result.status}}")
    trajectory = None
'''
        logger.info(f"Generated Cartesian plan: {sp} -> {gp}")
        return {
            "code": code,
            "start_pose": start_pose,
            "goal_pose": goal_pose,
            "timeout": timeout,
        }

    def plan_waypoints(self, pose_list: list, blend_radius: float = 0.01) -> dict:
        """Generate multi-waypoint planning code.

        pose_list: list of {"position": [x,y,z], "quaternion": [w,x,y,z]}
        """
        positions_str = ", ".join(
            f"[{p['position'][0]}, {p['position'][1]}, {p['position'][2]}]"
            for p in pose_list
        )
        quats_str = ", ".join(
            f"[{p['quaternion'][0]}, {p['quaternion'][1]}, {p['quaternion'][2]}, {p['quaternion'][3]}]"
            for p in pose_list
        )

        code = f'''import torch
from curobo.types.math import Pose
from curobo.wrap.reacher.motion_gen import MotionGenPlanConfig

# Define waypoint poses
positions = torch.tensor([{positions_str}], device="cuda:0")
quaternions = torch.tensor([{quats_str}], device="cuda:0")

waypoint_poses = Pose(position=positions, quaternion=quaternions)

# Get current joint state as start
start_js = motion_gen.get_retract_config()

# Plan through all waypoints sequentially
plan_cfg = MotionGenPlanConfig(
    enable_graph=True,
    enable_opt=True,
    max_attempts=12,
    timeout=15.0,
    enable_finetune_trajopt=True,
)

full_trajectory = []
current_js = start_js

for i in range(len(positions)):
    goal = Pose(
        position=positions[i:i+1],
        quaternion=quaternions[i:i+1],
    )
    result = motion_gen.plan_single(current_js, goal, plan_cfg)
    if result.success[0]:
        traj_segment = result.get_interpolated_plan()
        full_trajectory.append(traj_segment)
        current_js = traj_segment[-1]
        print(f"Waypoint {{i+1}}/{len(positions)} planned: {{traj_segment.position.shape[0]}} points")
    else:
        print(f"Failed at waypoint {{i+1}}: {{result.status}}")
        break

if len(full_trajectory) == len(positions):
    import torch
    combined = torch.cat([seg.position for seg in full_trajectory], dim=0)
    print(f"Full trajectory: {{combined.shape[0]}} waypoints across {{len(positions)}} segments")
'''
        logger.info(f"Generated waypoint plan with {len(pose_list)} waypoints")
        return {
            "code": code,
            "waypoint_count": len(pose_list),
            "blend_radius": blend_radius,
            "poses": pose_list,
        }

    def validate_singularity(self, trajectory: list, threshold: float = 0.01) -> dict:
        """Check trajectory for singularity proximity by computing
        condition number of the Jacobian at each waypoint."""
        code = f'''import numpy as np

def compute_jacobian_condition(joint_positions, kin_model):
    """Compute condition number of the Jacobian at each configuration."""
    results = []
    for i, q in enumerate(joint_positions):
        J = kin_model.compute_jacobian(q)  # 6 x n_dof matrix
        J_np = J.cpu().numpy() if hasattr(J, 'cpu') else np.array(J)

        # Condition number: ratio of largest to smallest singular value
        U, S, Vt = np.linalg.svd(J_np)
        cond = S[0] / S[-1] if S[-1] > 1e-12 else float('inf')

        # Manipulability (Yoshikawa): sqrt(det(J * J^T))
        JJt = J_np @ J_np.T
        manip = np.sqrt(max(np.linalg.det(JJt), 0.0))

        results.append({{
            "waypoint": i,
            "condition_number": float(cond),
            "manipulability": float(manip),
            "near_singularity": manip < {threshold},
            "singular_values": S.tolist(),
        }})
    return results

singularity_results = compute_jacobian_condition(trajectory, kin_model)
near_singular = [r for r in singularity_results if r["near_singularity"]]
print(f"Singularity check: {{len(near_singular)}}/{{len(singularity_results)}} points near singularity")
for r in near_singular:
    print(f"  Waypoint {{r['waypoint']}}: cond={{r['condition_number']:.1f}}, manip={{r['manipulability']:.6f}}")
'''
        logger.info(f"Generated singularity validation (threshold={threshold})")
        return {
            "code": code,
            "threshold": threshold,
            "trajectory_length": len(trajectory) if isinstance(trajectory, list) else "dynamic",
        }

    def validate_torque_limits(self, trajectory: list, payload: dict = None) -> dict:
        """Check torque limits along trajectory considering payload."""
        payload = payload or {"mass": 0.0, "com_offset": [0, 0, 0]}
        mass = payload.get("mass", 0.0)
        com = payload.get("com_offset", [0, 0, 0])

        code = f'''import numpy as np

def compute_inverse_dynamics(joint_positions, joint_velocities, joint_accelerations,
                              kin_model, gravity=np.array([0, 0, -9.81]),
                              payload_mass={mass}, payload_com=np.array({com})):
    """Compute required joint torques via recursive Newton-Euler."""
    n_points = len(joint_positions)
    n_dof = len(joint_positions[0]) if n_points > 0 else 0
    torques = np.zeros((n_points, n_dof))

    for i in range(n_points):
        q = np.array(joint_positions[i])
        qd = np.array(joint_velocities[i])
        qdd = np.array(joint_accelerations[i])

        # Mass matrix M(q)
        M = kin_model.compute_mass_matrix(q)
        # Coriolis + centrifugal C(q, qd)
        C = kin_model.compute_coriolis(q, qd)
        # Gravity vector g(q)
        g = kin_model.compute_gravity(q, gravity)

        # tau = M * qdd + C * qd + g
        tau = M @ qdd + C @ qd + g

        # Add payload contribution at end-effector
        if payload_mass > 0:
            J = kin_model.compute_jacobian(q)
            J_np = J.cpu().numpy() if hasattr(J, 'cpu') else np.array(J)
            F_payload = np.zeros(6)
            F_payload[2] = -payload_mass * 9.81  # gravity on payload
            tau += J_np.T @ F_payload

        torques[i] = tau

    return torques

torques = compute_inverse_dynamics(
    joint_positions, joint_velocities, joint_accelerations, kin_model
)

# Check against limits
joint_torque_limits = kin_model.get_torque_limits()  # from URDF
violations = []
for i in range(len(torques)):
    for j in range(torques.shape[1]):
        if abs(torques[i, j]) > joint_torque_limits[j]:
            violations.append({{
                "waypoint": i, "joint": j,
                "required": float(torques[i, j]),
                "limit": float(joint_torque_limits[j]),
                "ratio": float(abs(torques[i, j]) / joint_torque_limits[j]),
            }})

print(f"Torque validation: {{len(violations)}} violations found")
for v in violations[:5]:
    print(f"  Waypoint {{v['waypoint']}}, Joint {{v['joint']}}: "
          f"{{v['required']:.2f}} / {{v['limit']:.2f}} Nm ({{v['ratio']:.1%}})")
'''
        logger.info(f"Generated torque validation with payload mass={mass} kg")
        return {
            "code": code,
            "payload": payload,
        }

    def validate_workspace(self, pose_list: list, workspace_limits: dict = None) -> dict:
        """Validate all poses are within the robot workspace."""
        workspace_limits = workspace_limits or {
            "x": [-1.0, 1.0], "y": [-1.0, 1.0], "z": [0.0, 1.5],
            "radius_min": 0.2, "radius_max": 1.0,
        }

        code = f'''import numpy as np

workspace = {workspace_limits}

def validate_poses_in_workspace(poses, limits):
    """Check each pose against workspace boundaries."""
    results = []
    for i, pose in enumerate(poses):
        pos = np.array(pose["position"])
        x, y, z = pos

        # Cartesian box check
        in_x = limits["x"][0] <= x <= limits["x"][1]
        in_y = limits["y"][0] <= y <= limits["y"][1]
        in_z = limits["z"][0] <= z <= limits["z"][1]

        # Radial distance check (cylindrical workspace)
        r = np.sqrt(x**2 + y**2)
        in_radius = limits["radius_min"] <= r <= limits["radius_max"]

        valid = in_x and in_y and in_z and in_radius
        results.append({{
            "pose_index": i,
            "position": pos.tolist(),
            "valid": valid,
            "radial_distance": float(r),
            "violations": {{
                "x_range": not in_x,
                "y_range": not in_y,
                "z_range": not in_z,
                "radial_range": not in_radius,
            }},
        }})
    return results

results = validate_poses_in_workspace({pose_list}, workspace)
invalid = [r for r in results if not r["valid"]]
print(f"Workspace validation: {{len(results) - len(invalid)}}/{{len(results)}} poses valid")
for r in invalid:
    print(f"  Pose {{r['pose_index']}}: {{r['position']}} - violations: {{r['violations']}}")
'''
        logger.info(f"Generated workspace validation for {len(pose_list)} poses")
        return {
            "code": code,
            "pose_count": len(pose_list),
            "workspace_limits": workspace_limits,
        }

    def compute_manipulability(self, joint_config: list) -> dict:
        """Compute Yoshikawa manipulability index: sqrt(det(J * J^T))."""
        code = f'''import numpy as np
import torch

def yoshikawa_manipulability(q, kin_model):
    """Compute Yoshikawa manipulability index.
    m = sqrt(det(J(q) * J(q)^T))
    Higher values indicate better manipulability (further from singularities).
    """
    q_tensor = torch.tensor([q], dtype=torch.float32, device="cuda:0")
    J = kin_model.compute_jacobian(q_tensor)
    J_np = J.cpu().numpy().squeeze()

    JJt = J_np @ J_np.T
    det_JJt = np.linalg.det(JJt)
    manipulability = np.sqrt(max(det_JJt, 0.0))

    # Also compute directional manipulability (translational + rotational)
    J_trans = J_np[:3, :]  # translational part
    J_rot = J_np[3:, :]    # rotational part

    m_trans = np.sqrt(max(np.linalg.det(J_trans @ J_trans.T), 0.0))
    m_rot = np.sqrt(max(np.linalg.det(J_rot @ J_rot.T), 0.0))

    return {{
        "manipulability": float(manipulability),
        "translational": float(m_trans),
        "rotational": float(m_rot),
        "joint_config": q,
    }}

result = yoshikawa_manipulability({joint_config}, kin_model)
print(f"Manipulability at q={joint_config}:")
print(f"  Total: {{result['manipulability']:.6f}}")
print(f"  Translational: {{result['translational']:.6f}}")
print(f"  Rotational: {{result['rotational']:.6f}}")
'''
        logger.info(f"Generated manipulability computation for config={joint_config}")
        return {
            "code": code,
            "joint_config": joint_config,
        }
