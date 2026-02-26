# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Isaac Sim setup and configuration skill."""
import os
import json
import logging

logger = logging.getLogger("skill.isaac_setup")
BASE_DIR = os.path.expanduser("~/agent-stack")


class IsaacSetupSkill:
    """Manages Isaac Sim scene setup and configuration."""

    def load_urdf(self, urdf_path: str, position: list = None, orientation: list = None) -> dict:
        """Generate Isaac Sim code to load a URDF robot model."""
        position = position or [0.0, 0.0, 0.0]
        orientation = orientation or [1.0, 0.0, 0.0, 0.0]  # wxyz quaternion

        code = f'''import isaacsim.asset.importer as importer
from pxr import UsdPhysics, Gf

# Load URDF
robot_prim = importer.import_urdf(
    urdf_path="{urdf_path}",
    import_config=importer.ImportConfig(
        merge_fixed_joints=False,
        fix_base=True,
        default_drive_type="position",
    ),
)

# Set position and orientation
robot_prim.GetAttribute("xformOp:translate").Set(
    Gf.Vec3d({position[0]}, {position[1]}, {position[2]})
)
robot_prim.GetAttribute("xformOp:orient").Set(
    Gf.Quatd({orientation[0]}, {orientation[1]}, {orientation[2]}, {orientation[3]})
)
'''
        logger.info(f"Generated URDF load code for {urdf_path}")
        return {"code": code, "urdf_path": urdf_path, "position": position, "orientation": orientation}

    def configure_physics(self, dt: float = 1.0 / 240.0, gravity: float = -9.81) -> dict:
        """Generate physics configuration for Isaac Sim scene."""
        code = f'''from pxr import UsdPhysics, PhysxSchema

# Configure physics scene
physics_scene = UsdPhysics.Scene.Define(stage, "/physicsScene")
physics_scene.CreateGravityDirectionAttr().Set(Gf.Vec3f(0.0, 0.0, 1.0))
physics_scene.CreateGravityMagnitudeAttr().Set({abs(gravity)})

# Set physics timestep
physx_scene = PhysxSchema.PhysxSceneAPI.Apply(physics_scene.GetPrim())
physx_scene.CreateTimeStepsPerSecondAttr().Set({int(1.0 / dt)})
physx_scene.CreateEnableCCDAttr().Set(True)
physx_scene.CreateEnableStabilizationAttr().Set(True)
'''
        logger.info(f"Configured physics: dt={dt}, gravity={gravity}")
        return {"code": code, "dt": dt, "gravity": gravity, "hz": int(1.0 / dt)}

    def setup_camera(self, position: list, target: list, fov: float = 60.0) -> dict:
        """Generate camera setup code."""
        code = f'''from pxr import UsdGeom, Gf

camera = UsdGeom.Camera.Define(stage, "/World/Camera")
camera.GetFocalLengthAttr().Set({fov})

# Set camera transform
xform = UsdGeom.Xformable(camera.GetPrim())
xform.ClearXformOpOrder()
translate = xform.AddTranslateOp()
translate.Set(Gf.Vec3d({position[0]}, {position[1]}, {position[2]}))

# Set camera to look at target
from omni.kit.viewport.utility import get_active_viewport
viewport = get_active_viewport()
viewport.set_camera_position("{position[0]}", "{position[1]}", "{position[2]}", True)
viewport.set_camera_target("{target[0]}", "{target[1]}", "{target[2]}", True)
'''
        logger.info(f"Setup camera at {position} looking at {target}")
        return {"code": code, "position": position, "target": target, "fov": fov}

    def setup_ground_plane(self) -> dict:
        """Generate ground plane setup code."""
        code = '''from pxr import UsdGeom, UsdPhysics, Gf, PhysxSchema

# Create ground plane
ground = UsdGeom.Mesh.Define(stage, "/World/GroundPlane")
ground.CreatePointsAttr().Set([
    Gf.Vec3f(-50, -50, 0), Gf.Vec3f(50, -50, 0),
    Gf.Vec3f(50, 50, 0), Gf.Vec3f(-50, 50, 0),
])
ground.CreateFaceVertexCountsAttr().Set([4])
ground.CreateFaceVertexIndicesAttr().Set([0, 1, 2, 3])
ground.CreateNormalsAttr().Set([Gf.Vec3f(0, 0, 1)] * 4)

# Add collision
UsdPhysics.CollisionAPI.Apply(ground.GetPrim())
PhysxSchema.PhysxCollisionAPI.Apply(ground.GetPrim())
'''
        logger.info("Setup ground plane")
        return {"code": code}

    def setup_lighting(self, light_type: str = "dome") -> dict:
        """Generate lighting setup code."""
        if light_type == "dome":
            code = '''from pxr import UsdLux

dome_light = UsdLux.DomeLight.Define(stage, "/World/DomeLight")
dome_light.CreateIntensityAttr().Set(1000.0)
dome_light.CreateTextureFormatAttr().Set("latlong")
'''
        elif light_type == "distant":
            code = '''from pxr import UsdLux, Gf

distant_light = UsdLux.DistantLight.Define(stage, "/World/DistantLight")
distant_light.CreateIntensityAttr().Set(3000.0)
distant_light.CreateAngleAttr().Set(0.53)
xform = UsdGeom.Xformable(distant_light.GetPrim())
xform.AddRotateXYZOp().Set(Gf.Vec3f(-45, 30, 0))
'''
        else:
            code = f'# Unknown light type: {light_type}\n'

        logger.info(f"Setup {light_type} lighting")
        return {"code": code, "type": light_type}
