# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Sensor setup skill for Isaac Sim."""
import os
import logging

logger = logging.getLogger("skill.sensor_setup")
BASE_DIR = os.path.expanduser("~/agent-stack")


class SensorSetupSkill:
    """Sets up various sensors in Isaac Sim: cameras, IMU, lidar, force-torque, encoders, ZED X."""

    def add_camera(self, name: str = "front_camera", position: list = None,
                   orientation: list = None, resolution: list = None,
                   fov: float = 60.0, clipping: list = None) -> dict:
        """Generate code to add a camera sensor."""
        position = position or [0.5, 0.0, 0.5]
        orientation = orientation or [1.0, 0.0, 0.0, 0.0]
        resolution = resolution or [640, 480]
        clipping = clipping or [0.01, 100.0]

        code = f'''from pxr import UsdGeom, Gf
from omni.isaac.sensor import Camera

# Add camera: {name}
camera = Camera(
    prim_path="/World/Sensors/{name}",
    position=np.array({position}),
    frequency=30,
    resolution=({resolution[0]}, {resolution[1]}),
)
camera.initialize()

# Configure camera properties
camera.set_focal_length({fov})
camera.set_clipping_range({clipping[0]}, {clipping[1]})

# Set orientation
camera_prim = stage.GetPrimAtPath("/World/Sensors/{name}")
xform = UsdGeom.Xformable(camera_prim)
xform.AddOrientOp().Set(Gf.Quatd({orientation[0]}, {orientation[1]}, {orientation[2]}, {orientation[3]}))

# Enable render products
camera.add_motion_vectors_to_frame()
camera.add_distance_to_camera_to_frame()
camera.add_normals_to_frame()

print(f"Camera '{name}' added at {position}, resolution={resolution}")
'''
        logger.info(f"Added camera {name} at {position}")
        return {"code": code, "name": name, "position": position, "resolution": resolution}

    def add_imu(self, name: str = "base_imu", parent_prim: str = "/World/Robot/base_link",
                update_rate: float = 200.0) -> dict:
        """Generate code to add an IMU sensor."""
        code = f'''from omni.isaac.sensor import IMUSensor

# Add IMU sensor: {name}
imu = IMUSensor(
    prim_path="{parent_prim}/{name}",
    name="{name}",
    frequency={update_rate},
    translation=np.array([0.0, 0.0, 0.0]),
)
imu.initialize()

# IMU will output:
# - Linear acceleration (m/s^2)
# - Angular velocity (rad/s)
# - Orientation quaternion (w, x, y, z)

def read_imu():
    frame = imu.get_current_frame()
    return {{
        "linear_acceleration": frame["lin_acc"].tolist(),
        "angular_velocity": frame["ang_vel"].tolist(),
        "orientation": frame["orientation"].tolist(),
    }}

print(f"IMU '{name}' attached to {parent_prim} at {update_rate} Hz")
'''
        logger.info(f"Added IMU {name} on {parent_prim}")
        return {"code": code, "name": name, "parent_prim": parent_prim, "update_rate": update_rate}

    def add_lidar(self, name: str = "lidar", position: list = None,
                  num_channels: int = 16, range_max: float = 100.0,
                  horizontal_fov: float = 360.0, rotation_rate: float = 10.0) -> dict:
        """Generate code to add a lidar sensor."""
        position = position or [0.0, 0.0, 1.0]

        code = f'''from omni.isaac.range_sensor import LidarRtx

# Add Lidar sensor: {name}
lidar = LidarRtx(
    prim_path="/World/Sensors/{name}",
    position=np.array({position}),
    frequency=1.0 / {rotation_rate},
)

# Configure lidar
lidar_prim = stage.GetPrimAtPath("/World/Sensors/{name}")
lidar_prim.GetAttribute("maxRange").Set({range_max})
lidar_prim.GetAttribute("horizontalFov").Set({horizontal_fov})
lidar_prim.GetAttribute("numChannels").Set({num_channels})
lidar_prim.GetAttribute("rotationRate").Set({rotation_rate})

# Set beam properties
vertical_fov = 30.0  # degrees
lidar_prim.GetAttribute("verticalFov").Set(vertical_fov)

lidar.initialize()

def read_lidar():
    point_cloud = lidar.get_point_cloud()
    ranges = lidar.get_range_data()
    intensities = lidar.get_intensity_data()
    return {{
        "point_cloud_shape": point_cloud.shape,
        "num_points": len(point_cloud),
        "min_range": float(np.min(ranges)) if len(ranges) > 0 else None,
        "max_range": float(np.max(ranges)) if len(ranges) > 0 else None,
    }}

print(f"Lidar '{name}' added: {{num_channels}} channels, range={range_max}m")
'''
        logger.info(f"Added lidar {name} at {position}")
        return {"code": code, "name": name, "num_channels": num_channels, "range_max": range_max}

    def add_force_torque(self, name: str = "wrist_ft", joint_prim: str = "",
                         update_rate: float = 1000.0) -> dict:
        """Generate code to add a force-torque sensor at a joint."""
        joint_prim = joint_prim or "/World/Robot/wrist_3_joint"

        code = f'''from pxr import PhysxSchema

# Add Force-Torque sensor: {name}
joint_prim = stage.GetPrimAtPath("{joint_prim}")

# Apply force sensor API to the joint
ft_sensor = PhysxSchema.PhysxJointForceSensorAPI.Apply(joint_prim)
ft_sensor.CreateForceEnabledAttr().Set(True)
ft_sensor.CreateTorqueEnabledAttr().Set(True)
ft_sensor.CreateReportPairsAttr().Set(True)

# Configure update rate
sensor_period = 1.0 / {update_rate}

def read_force_torque():
    """Read force-torque sensor data."""
    forces = joint_prim.GetAttribute("physics:force").Get()
    torques = joint_prim.GetAttribute("physics:torque").Get()
    return {{
        "force": [float(f) for f in forces] if forces else [0, 0, 0],
        "torque": [float(t) for t in torques] if torques else [0, 0, 0],
        "force_magnitude": float(np.linalg.norm(forces)) if forces else 0.0,
        "torque_magnitude": float(np.linalg.norm(torques)) if torques else 0.0,
    }}

print(f"Force-torque sensor '{name}' at {joint_prim}, {update_rate} Hz")
'''
        logger.info(f"Added FT sensor {name} at {joint_prim}")
        return {"code": code, "name": name, "joint_prim": joint_prim, "update_rate": update_rate}

    def add_joint_encoders(self, robot_prim: str = "/World/Robot",
                           joints: list = None, resolution: float = 0.001) -> dict:
        """Generate code to set up joint encoder readings."""
        joints = joints or ["joint_1", "joint_2", "joint_3", "joint_4",
                            "joint_5", "joint_6", "joint_7"]

        joint_paths = [f'"{robot_prim}/{j}"' for j in joints]
        joint_paths_str = ", ".join(joint_paths)

        code = f'''from omni.isaac.core.articulations import Articulation

# Setup joint encoders for {robot_prim}
robot = Articulation(prim_path="{robot_prim}")
robot.initialize()

joint_names = {joints}
encoder_resolution = {resolution}  # radians

def read_encoders():
    """Read all joint encoder values with simulated quantization."""
    raw_positions = robot.get_joint_positions()
    raw_velocities = robot.get_joint_velocities()

    # Apply encoder quantization (simulate real encoder resolution)
    quantized_positions = np.round(raw_positions / encoder_resolution) * encoder_resolution

    return {{
        "positions": quantized_positions.tolist(),
        "velocities": raw_velocities.tolist(),
        "raw_positions": raw_positions.tolist(),
        "quantization_error": (raw_positions - quantized_positions).tolist(),
        "joint_names": joint_names,
    }}

def read_single_encoder(joint_index):
    """Read a single joint encoder."""
    data = read_encoders()
    return {{
        "joint": joint_names[joint_index],
        "position": data["positions"][joint_index],
        "velocity": data["velocities"][joint_index],
    }}

print(f"Joint encoders configured for {{len(joint_names)}} joints, resolution={resolution} rad")
'''
        logger.info(f"Added joint encoders for {robot_prim}")
        return {"code": code, "robot_prim": robot_prim, "joints": joints, "resolution": resolution}

    def add_zed_x_stereo(self, name: str = "zed_x", position: list = None,
                          baseline: float = 0.12, resolution: list = None,
                          fps: float = 30.0) -> dict:
        """Generate code to add a ZED X stereo camera setup."""
        position = position or [0.3, 0.0, 0.5]
        resolution = resolution or [1920, 1080]

        code = f'''from pxr import UsdGeom, Gf
from omni.isaac.sensor import Camera
import numpy as np

# Add ZED X Stereo Camera: {name}
baseline = {baseline}  # meters between left and right cameras

# Left camera
left_cam = Camera(
    prim_path="/World/Sensors/{name}/left",
    position=np.array([{position[0]}, {position[1]} - baseline/2, {position[2]}]),
    frequency={fps},
    resolution=({resolution[0]}, {resolution[1]}),
)
left_cam.initialize()
left_cam.set_focal_length(2.12)  # ZED X focal length in mm
left_cam.set_horizontal_aperture(5.6)

# Right camera
right_cam = Camera(
    prim_path="/World/Sensors/{name}/right",
    position=np.array([{position[0]}, {position[1]} + baseline/2, {position[2]}]),
    frequency={fps},
    resolution=({resolution[0]}, {resolution[1]}),
)
right_cam.initialize()
right_cam.set_focal_length(2.12)
right_cam.set_horizontal_aperture(5.6)

# Enable depth and other render products
for cam in [left_cam, right_cam]:
    cam.add_distance_to_camera_to_frame()
    cam.add_normals_to_frame()
    cam.add_motion_vectors_to_frame()

def read_stereo():
    """Read stereo pair images and compute disparity."""
    left_rgb = left_cam.get_rgba()[:, :, :3]
    right_rgb = right_cam.get_rgba()[:, :, :3]
    left_depth = left_cam.get_depth()
    right_depth = right_cam.get_depth()

    return {{
        "left_rgb_shape": left_rgb.shape,
        "right_rgb_shape": right_rgb.shape,
        "left_depth_range": [float(np.min(left_depth)), float(np.max(left_depth))],
        "baseline": baseline,
    }}

print(f"ZED X stereo '{name}' added at {position}, baseline={baseline}m, {resolution[0]}x{resolution[1]}@{fps}fps")
'''
        logger.info(f"Added ZED X stereo {name} at {position}")
        return {
            "code": code,
            "name": name,
            "position": position,
            "baseline": baseline,
            "resolution": resolution,
            "fps": fps,
        }
