# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Environment builder skill for Isaac Sim scenes."""
import os
import json
import logging

logger = logging.getLogger("skill.environment_builder")
BASE_DIR = os.path.expanduser("~/agent-stack")


class EnvironmentBuilderSkill:
    """Builds and manages Isaac Sim environments with obstacles, lighting, and randomization."""

    def create_environment(self, config: dict = None) -> str:
        """Generate Isaac Sim environment creation code.

        config: {"name": str, "size": [x,y,z], "ground": bool, "lighting": str}
        """
        config = config or {}
        name = config.get("name", "TrainingEnv")
        size = config.get("size", [10.0, 10.0, 5.0])
        ground = config.get("ground", True)
        lighting = config.get("lighting", "dome")

        code_parts = [
            "from pxr import Usd, UsdGeom, UsdPhysics, Gf, PhysxSchema, UsdLux",
            "",
            f'# Create environment: {name}',
            f'stage = omni.usd.get_context().get_stage()',
            f'env_prim = stage.DefinePrim("/World/{name}", "Xform")',
            "",
        ]

        if ground:
            code_parts.extend([
                "# Ground plane",
                f'ground = UsdGeom.Mesh.Define(stage, "/World/{name}/Ground")',
                f"ground.CreatePointsAttr().Set([",
                f"    Gf.Vec3f(-{size[0]/2}, -{size[1]/2}, 0),",
                f"    Gf.Vec3f({size[0]/2}, -{size[1]/2}, 0),",
                f"    Gf.Vec3f({size[0]/2}, {size[1]/2}, 0),",
                f"    Gf.Vec3f(-{size[0]/2}, {size[1]/2}, 0),",
                "])",
                "ground.CreateFaceVertexCountsAttr().Set([4])",
                "ground.CreateFaceVertexIndicesAttr().Set([0, 1, 2, 3])",
                "UsdPhysics.CollisionAPI.Apply(ground.GetPrim())",
                "",
            ])

        if lighting == "dome":
            code_parts.extend([
                "# Dome lighting",
                f'dome = UsdLux.DomeLight.Define(stage, "/World/{name}/DomeLight")',
                "dome.CreateIntensityAttr().Set(1000.0)",
                "",
            ])
        elif lighting == "studio":
            code_parts.extend([
                "# Studio lighting (key + fill + rim)",
                f'key = UsdLux.DistantLight.Define(stage, "/World/{name}/KeyLight")',
                "key.CreateIntensityAttr().Set(3000.0)",
                "UsdGeom.Xformable(key.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-45, 30, 0))",
                "",
                f'fill = UsdLux.DistantLight.Define(stage, "/World/{name}/FillLight")',
                "fill.CreateIntensityAttr().Set(1500.0)",
                "UsdGeom.Xformable(fill.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-30, -60, 0))",
                "",
                f'rim = UsdLux.DistantLight.Define(stage, "/World/{name}/RimLight")',
                "rim.CreateIntensityAttr().Set(2000.0)",
                "UsdGeom.Xformable(rim.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-60, 150, 0))",
                "",
            ])

        code_parts.extend([
            "# Physics scene",
            f'physics = UsdPhysics.Scene.Define(stage, "/World/{name}/PhysicsScene")',
            "physics.CreateGravityDirectionAttr().Set(Gf.Vec3f(0, 0, -1))",
            "physics.CreateGravityMagnitudeAttr().Set(9.81)",
            "",
            f'print("Environment \\"{name}\\" created")',
        ])

        code = "\n".join(code_parts) + "\n"
        logger.info(f"Created environment: {name}")
        return code

    def add_static_obstacle(self, mesh: str = "cube", pose: list = None,
                            physics: bool = True) -> dict:
        """Generate code to add a static obstacle.

        mesh: "cube", "sphere", "cylinder", or USD file path.
        pose: [x, y, z, qw, qx, qy, qz]
        """
        pose = pose or [0.0, 0.0, 0.5, 1.0, 0.0, 0.0, 0.0]
        pos = pose[:3]
        quat = pose[3:7] if len(pose) >= 7 else [1, 0, 0, 0]

        if mesh == "cube":
            shape_code = f'''obstacle = UsdGeom.Cube.Define(stage, prim_path)
obstacle.CreateSizeAttr().Set(0.1)'''
        elif mesh == "sphere":
            shape_code = f'''obstacle = UsdGeom.Sphere.Define(stage, prim_path)
obstacle.CreateRadiusAttr().Set(0.05)'''
        elif mesh == "cylinder":
            shape_code = f'''obstacle = UsdGeom.Cylinder.Define(stage, prim_path)
obstacle.CreateRadiusAttr().Set(0.05)
obstacle.CreateHeightAttr().Set(0.2)'''
        else:
            shape_code = f'''from omni.isaac.core.utils.stage import add_reference_to_stage
obstacle = add_reference_to_stage(usd_path="{mesh}", prim_path=prim_path)'''

        physics_code = ""
        if physics:
            physics_code = """
# Add physics
UsdPhysics.CollisionAPI.Apply(obstacle.GetPrim())
UsdPhysics.RigidBodyAPI.Apply(obstacle.GetPrim())
rigid = UsdPhysics.RigidBodyAPI(obstacle.GetPrim())
rigid.CreateKinematicEnabledAttr().Set(True)  # Static"""

        code = f'''from pxr import UsdGeom, UsdPhysics, Gf
import random
import string

# Add static obstacle
obs_id = "".join(random.choices(string.ascii_lowercase, k=6))
prim_path = f"/World/Obstacles/static_{{obs_id}}"

{shape_code}

# Set pose
xform = UsdGeom.Xformable(obstacle.GetPrim())
xform.ClearXformOpOrder()
xform.AddTranslateOp().Set(Gf.Vec3d({pos[0]}, {pos[1]}, {pos[2]}))
xform.AddOrientOp().Set(Gf.Quatd({quat[0]}, {quat[1]}, {quat[2]}, {quat[3]}))
{physics_code}

print(f"Added static {{'{mesh}'}} obstacle at {pos}")
'''
        logger.info(f"Added static {mesh} at {pos}")
        return {"code": code, "mesh": mesh, "pose": pose}

    def add_dynamic_obstacle(self, mesh: str = "sphere", pose: list = None,
                             velocity: list = None) -> dict:
        """Generate code to add a dynamic (moving) obstacle."""
        pose = pose or [1.0, 0.0, 0.5, 1.0, 0.0, 0.0, 0.0]
        velocity = velocity or [0.0, 0.1, 0.0]
        pos = pose[:3]
        quat = pose[3:7] if len(pose) >= 7 else [1, 0, 0, 0]

        if mesh == "sphere":
            shape_code = '''obstacle = UsdGeom.Sphere.Define(stage, prim_path)
obstacle.CreateRadiusAttr().Set(0.05)'''
        elif mesh == "cube":
            shape_code = '''obstacle = UsdGeom.Cube.Define(stage, prim_path)
obstacle.CreateSizeAttr().Set(0.1)'''
        else:
            shape_code = f'''from omni.isaac.core.utils.stage import add_reference_to_stage
obstacle = add_reference_to_stage(usd_path="{mesh}", prim_path=prim_path)'''

        code = f'''from pxr import UsdGeom, UsdPhysics, PhysxSchema, Gf
import random
import string

# Add dynamic obstacle
obs_id = "".join(random.choices(string.ascii_lowercase, k=6))
prim_path = f"/World/Obstacles/dynamic_{{obs_id}}"

{shape_code}

# Set initial pose
xform = UsdGeom.Xformable(obstacle.GetPrim())
xform.ClearXformOpOrder()
xform.AddTranslateOp().Set(Gf.Vec3d({pos[0]}, {pos[1]}, {pos[2]}))
xform.AddOrientOp().Set(Gf.Quatd({quat[0]}, {quat[1]}, {quat[2]}, {quat[3]}))

# Add dynamic physics
UsdPhysics.CollisionAPI.Apply(obstacle.GetPrim())
UsdPhysics.RigidBodyAPI.Apply(obstacle.GetPrim())
rigid = UsdPhysics.RigidBodyAPI(obstacle.GetPrim())
rigid.CreateVelocityAttr().Set(Gf.Vec3f({velocity[0]}, {velocity[1]}, {velocity[2]}))

# Set mass properties
mass_api = UsdPhysics.MassAPI.Apply(obstacle.GetPrim())
mass_api.CreateMassAttr().Set(0.5)

print(f"Added dynamic {{'{mesh}'}} obstacle at {pos} with velocity {velocity}")
'''
        logger.info(f"Added dynamic {mesh} at {pos} vel={velocity}")
        return {"code": code, "mesh": mesh, "pose": pose, "velocity": velocity}

    def add_lighting(self, light_type: str = "point", position: list = None,
                     intensity: float = 1000.0) -> dict:
        """Generate code to add a light source."""
        position = position or [0.0, 0.0, 3.0]

        light_map = {
            "point": ("SphereLight", f'''light = UsdLux.SphereLight.Define(stage, prim_path)
light.CreateRadiusAttr().Set(0.1)'''),
            "distant": ("DistantLight", '''light = UsdLux.DistantLight.Define(stage, prim_path)
light.CreateAngleAttr().Set(0.53)'''),
            "dome": ("DomeLight", '''light = UsdLux.DomeLight.Define(stage, prim_path)
light.CreateTextureFormatAttr().Set("latlong")'''),
            "rect": ("RectLight", '''light = UsdLux.RectLight.Define(stage, prim_path)
light.CreateWidthAttr().Set(1.0)
light.CreateHeightAttr().Set(1.0)'''),
        }

        light_name, shape_code = light_map.get(light_type, light_map["point"])

        code = f'''from pxr import UsdLux, UsdGeom, Gf

prim_path = "/World/Lights/{light_name}"

{shape_code}
light.CreateIntensityAttr().Set({intensity})
light.CreateColorAttr().Set(Gf.Vec3f(1.0, 1.0, 1.0))

xform = UsdGeom.Xformable(light.GetPrim())
xform.AddTranslateOp().Set(Gf.Vec3d({position[0]}, {position[1]}, {position[2]}))

print(f"Added {light_type} light at {position}, intensity={intensity}")
'''
        logger.info(f"Added {light_type} light at {position}")
        return {"code": code, "light_type": light_type, "position": position, "intensity": intensity}

    def randomize_environment(self, seed: int = 42) -> str:
        """Generate domain randomization code for sim-to-real transfer."""
        code = f'''import random
import numpy as np
from pxr import UsdGeom, UsdShade, Gf

random.seed({seed})
np.random.seed({seed})

# Domain randomization parameters
DR_CONFIG = {{
    "lighting_intensity_range": (500, 3000),
    "lighting_color_temp_range": (3000, 7000),  # Kelvin
    "ground_friction_range": (0.3, 1.0),
    "object_scale_range": (0.8, 1.2),
    "camera_position_noise": 0.05,  # meters
    "texture_randomization": True,
    "gravity_noise": 0.02,  # fraction of 9.81
}}

def kelvin_to_rgb(temp):
    """Convert color temperature to RGB."""
    temp = temp / 100.0
    if temp <= 66:
        r = 255
        g = 99.4708025861 * np.log(temp) - 161.1195681661
        b = 138.5177312231 * np.log(temp - 10) - 305.0447927307 if temp > 19 else 0
    else:
        r = 329.698727446 * ((temp - 60) ** -0.1332047592)
        g = 288.1221695283 * ((temp - 60) ** -0.0755148492)
        b = 255
    return [max(0, min(255, v)) / 255.0 for v in [r, g, b]]

def randomize_scene(stage):
    """Apply domain randomization to entire scene."""
    results = {{}}

    # Randomize lighting
    for prim in stage.Traverse():
        if prim.IsA(UsdLux.Light):
            intensity = random.uniform(*DR_CONFIG["lighting_intensity_range"])
            prim.GetAttribute("inputs:intensity").Set(intensity)
            temp = random.uniform(*DR_CONFIG["lighting_color_temp_range"])
            rgb = kelvin_to_rgb(temp)
            prim.GetAttribute("inputs:color").Set(Gf.Vec3f(*rgb))
            results["lighting"] = {{"intensity": intensity, "color_temp": temp}}

    # Randomize ground friction
    for prim in stage.Traverse():
        if "Ground" in prim.GetPath().pathString:
            friction = random.uniform(*DR_CONFIG["ground_friction_range"])
            mat = UsdShade.Material.Define(stage, prim.GetPath().AppendPath("PhysMat"))
            # Apply physics material
            results["friction"] = friction

    # Randomize object scales
    for prim in stage.Traverse():
        if "Obstacles" in prim.GetPath().pathString and prim.IsA(UsdGeom.Gprim):
            scale = random.uniform(*DR_CONFIG["object_scale_range"])
            xform = UsdGeom.Xformable(prim)
            xform.AddScaleOp().Set(Gf.Vec3d(scale, scale, scale))

    # Randomize gravity
    gravity_noise = random.uniform(-DR_CONFIG["gravity_noise"], DR_CONFIG["gravity_noise"])
    gravity = 9.81 * (1.0 + gravity_noise)
    results["gravity"] = gravity

    print(f"Domain randomization applied (seed={seed})")
    for k, v in results.items():
        print(f"  {{k}}: {{v}}")
    return results

dr_results = randomize_scene(stage)
'''
        logger.info(f"Generated domain randomization code (seed={seed})")
        return code

    def save_environment(self, path: str = None) -> str:
        """Generate USD scene save code."""
        path = path or os.path.join(BASE_DIR, "environments", "scene.usd")
        dir_path = os.path.dirname(path)

        code = f'''import os
from pxr import Usd

os.makedirs("{dir_path}", exist_ok=True)

# Save current stage as USD
stage = omni.usd.get_context().get_stage()
stage.GetRootLayer().Export("{path}")

# Also save as USDA (text format) for version control
usda_path = "{path}".replace(".usd", ".usda")
stage.GetRootLayer().Export(usda_path)

print(f"Environment saved to {path}")
print(f"Text format saved to {{usda_path}}")
'''
        logger.info(f"Generated save code for {path}")
        return code

    def load_environment(self, path: str = None) -> str:
        """Generate USD scene load code."""
        path = path or os.path.join(BASE_DIR, "environments", "scene.usd")

        code = f'''import os

if not os.path.exists("{path}"):
    raise FileNotFoundError(f"Environment file not found: {path}")

# Open USD stage
success, msg = omni.usd.get_context().open_stage("{path}")
if success:
    stage = omni.usd.get_context().get_stage()
    print(f"Environment loaded from {path}")

    # List top-level prims
    root = stage.GetPseudoRoot()
    for child in root.GetChildren():
        print(f"  Prim: {{child.GetPath()}}")
else:
    print(f"Failed to load environment: {{msg}}")
'''
        logger.info(f"Generated load code for {path}")
        return code
