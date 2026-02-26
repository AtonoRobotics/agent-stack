# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""cuRobo setup and configuration skill."""
import os
import json
import logging

logger = logging.getLogger("skill.curobo_setup")
BASE_DIR = os.path.expanduser("~/agent-stack")


class CuRoboSetupSkill:
    """Manages cuRobo robot configuration and initialization."""

    def load_robot_config(self, urdf_path: str, config_yml: str = None) -> dict:
        """Generate cuRobo robot config loading code."""
        config_yml = config_yml or os.path.join(BASE_DIR, "config", "robot.yml")
        code = f'''from curobo.types.robot import RobotConfig
from curobo.util_file import load_yaml, join_path

# Load robot configuration
robot_cfg = RobotConfig.from_dict(
    load_yaml(join_path("{config_yml}"))["robot_cfg"]
)

# Override URDF path if specified
robot_cfg.kinematics.urdf_path = "{urdf_path}"

# Build kinematics model
from curobo.cuda_robot_model.cuda_robot_model import CudaRobotModel
kin_model = CudaRobotModel(robot_cfg.kinematics)

print(f"Loaded robot with {{kin_model.get_dof()}} DOF")
print(f"Joint names: {{kin_model.joint_names}}")
print(f"EE link: {{robot_cfg.kinematics.ee_link}}")
'''
        logger.info(f"Generated robot config load for {urdf_path}")
        return {
            "code": code,
            "urdf_path": urdf_path,
            "config_yml": config_yml,
        }

    def configure_collision_world(self, obstacles: list = None) -> dict:
        """Generate collision world config with obstacle list.

        Each obstacle is a dict: {"type": "cuboid"|"sphere"|"mesh",
            "name": str, "position": [x,y,z], "dims": [x,y,z] or "radius": float}
        """
        obstacles = obstacles or []
        obstacle_defs = []
        for obs in obstacles:
            obs_type = obs.get("type", "cuboid")
            name = obs.get("name", "obstacle")
            pos = obs.get("position", [0.0, 0.0, 0.0])
            if obs_type == "cuboid":
                dims = obs.get("dims", [0.1, 0.1, 0.1])
                obstacle_defs.append(
                    f'    Cuboid(name="{name}", pose={pos + [1, 0, 0, 0]}, dims={dims})'
                )
            elif obs_type == "sphere":
                radius = obs.get("radius", 0.05)
                obstacle_defs.append(
                    f'    Sphere(name="{name}", pose={pos + [1, 0, 0, 0]}, radius={radius})'
                )
            elif obs_type == "mesh":
                mesh_path = obs.get("mesh_path", "")
                obstacle_defs.append(
                    f'    Mesh(name="{name}", pose={pos + [1, 0, 0, 0]}, file_path="{mesh_path}")'
                )

        obstacles_str = ",\n".join(obstacle_defs) if obstacle_defs else "    # No obstacles"
        code = f'''from curobo.geom.types import WorldConfig, Cuboid, Sphere, Mesh

# Configure collision world
world_cfg = WorldConfig(
    cuboid=[],
    sphere=[],
    mesh=[],
)

# Add obstacles
obstacles = [
{obstacles_str}
]

for obs in obstacles:
    if isinstance(obs, Cuboid):
        world_cfg.cuboid.append(obs)
    elif isinstance(obs, Sphere):
        world_cfg.sphere.append(obs)
    elif isinstance(obs, Mesh):
        world_cfg.mesh.append(obs)

print(f"Collision world configured with {{len(obstacles)}} obstacles")
'''
        logger.info(f"Configured collision world with {len(obstacles)} obstacles")
        return {
            "code": code,
            "obstacle_count": len(obstacles),
            "obstacles": obstacles,
        }

    def configure_payload(self, mass: float = 0.0, com_offset: list = None,
                          inertia: list = None) -> dict:
        """Generate payload configuration for end-effector."""
        com_offset = com_offset or [0.0, 0.0, 0.0]
        inertia = inertia or [0.001, 0.001, 0.001]  # Ixx, Iyy, Izz diagonal
        code = f'''from curobo.types.robot import RobotConfig

# Configure end-effector payload
payload_cfg = {{
    "ee_mass": {mass},
    "ee_com": {com_offset},
    "ee_inertia": {{
        "ixx": {inertia[0]}, "iyy": {inertia[1]}, "izz": {inertia[2]},
        "ixy": 0.0, "ixz": 0.0, "iyz": 0.0,
    }},
}}

# Apply to robot config
robot_cfg.kinematics.external_asset_path = None
robot_cfg.kinematics.extra_payload = payload_cfg

print(f"Payload configured: mass={{payload_cfg['ee_mass']}} kg")
print(f"  COM offset: {{payload_cfg['ee_com']}}")
print(f"  Inertia diagonal: [{{payload_cfg['ee_inertia']['ixx']}}, "
      f"{{payload_cfg['ee_inertia']['iyy']}}, {{payload_cfg['ee_inertia']['izz']}}]")
'''
        logger.info(f"Configured payload: mass={mass} kg, com={com_offset}")
        return {
            "code": code,
            "mass": mass,
            "com_offset": com_offset,
            "inertia": inertia,
        }

    def configure_joint_limits(self, position_limits: list = None,
                                velocity_limits: list = None,
                                acceleration_limits: list = None) -> dict:
        """Generate joint limits configuration from URDF or overrides."""
        code_parts = [
            "from curobo.types.robot import JointState",
            "",
            "# Configure joint limits",
        ]
        if position_limits:
            code_parts.append(f"position_limits = {position_limits}")
            code_parts.append("robot_cfg.kinematics.joint_limits.position = position_limits")
        else:
            code_parts.append("# Using position limits from URDF")
            code_parts.append("position_limits = robot_cfg.kinematics.joint_limits.position")

        if velocity_limits:
            code_parts.append(f"velocity_limits = {velocity_limits}")
            code_parts.append("robot_cfg.kinematics.joint_limits.velocity = velocity_limits")
        else:
            code_parts.append("# Using velocity limits from URDF")
            code_parts.append("velocity_limits = robot_cfg.kinematics.joint_limits.velocity")

        if acceleration_limits:
            code_parts.append(f"acceleration_limits = {acceleration_limits}")
            code_parts.append("robot_cfg.kinematics.joint_limits.acceleration = acceleration_limits")
        else:
            code_parts.append("# Setting default acceleration limits (2x velocity limits)")
            code_parts.append("acceleration_limits = [v * 2.0 for v in velocity_limits]")
            code_parts.append("robot_cfg.kinematics.joint_limits.acceleration = acceleration_limits")

        code_parts.extend([
            "",
            "print(f'Position limits: {position_limits}')",
            "print(f'Velocity limits: {velocity_limits}')",
            "print(f'Acceleration limits: {acceleration_limits}')",
        ])

        code = "\n".join(code_parts) + "\n"
        logger.info("Configured joint limits")
        return {
            "code": code,
            "position_limits": position_limits,
            "velocity_limits": velocity_limits,
            "acceleration_limits": acceleration_limits,
        }

    def warmup(self, num_seeds: int = 12, batch_size: int = 1) -> dict:
        """Generate cuRobo warmup code to JIT-compile kernels."""
        code = f'''import torch
from curobo.wrap.reacher.motion_gen import MotionGen, MotionGenConfig

# Build MotionGen from robot and world configs
motion_gen_config = MotionGenConfig.load_from_robot_config(
    robot_cfg,
    world_cfg,
    interpolation_dt=0.01,
    num_ik_seeds={num_seeds},
    num_graph_seeds={num_seeds},
    num_batch_graph_seeds={num_seeds},
    num_batch_ik_seeds={num_seeds},
)
motion_gen = MotionGen(motion_gen_config)

# Warmup: JIT compile CUDA kernels
print("Warming up cuRobo motion generator...")
motion_gen.warmup(
    batch={batch_size},
    warmup_js_trajopt=True,
    parallel_finetune=True,
)
print("Warmup complete. cuRobo is ready for motion planning.")

# Verify warmup by running a simple FK
joint_state = motion_gen.get_retract_config()
ee_pose = motion_gen.compute_kinematics(joint_state)
print(f"Retract config EE pose: position={{ee_pose.position}}, quat={{ee_pose.quaternion}}")
'''
        logger.info(f"Generated warmup code: seeds={num_seeds}, batch={batch_size}")
        return {
            "code": code,
            "num_seeds": num_seeds,
            "batch_size": batch_size,
        }
