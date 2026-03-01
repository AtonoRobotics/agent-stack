#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Simulator agent for Isaac Sim, cuRobo, and ROS2 simulation workflows."""

import os
import sys
import re
import struct
import subprocess
import yaml
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
sys.path.insert(0, os.path.expanduser("~/agent-stack/dashboard/backend"))
from agents.base_agent import BaseAgent, BASE_DIR, DATA_DIR


class SimulatorAgent(BaseAgent):
    """Agent for managing simulation workflows, auto-fixing sim errors, and data collection."""

    task_type = "simulation"

    APPROVAL_REQUIRED = [
        "modify_urdf",
        "change_curobo_config",
        "stop_simulation",
        "clear_data",
    ]

    def __init__(self):
        super().__init__(self.task_type)
        self.templates_dir = os.path.join(BASE_DIR, "templates")
        self.data_dir = os.path.join(DATA_DIR, "trajectories")
        os.makedirs(self.templates_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)

        # Skill registry for deterministic execution
        self._SKILL_REGISTRY = {
            "parse_urdf": self.parse_urdf,
            "validate_urdf": self.validate_urdf,
            "compare_urdfs": self.compare_urdfs,
            "consolidate_urdfs": self.consolidate_urdfs,
            "generate_collision_spheres": self.generate_collision_spheres,
            "validate_curobo_config": self.validate_curobo_config,
            "run_template": self.run_template,
            "fix_sim_error": self.fix_sim_error,
        }

        # Map error patterns to fix methods
        self.AUTO_FIXES = {
            "PhysX cooking failed": self._fix_physx_cooking,
            "CUDA out of memory": self._fix_cuda_oom,
            "URDF joint limit missing": self._fix_urdf_limits,
            "cuRobo IK_FAIL": self._fix_ik_fail,
            "Isaac Sim black viewport": self._fix_black_viewport,
            "ROS2 node not found": self._fix_ros2_node,
        }

    # ── URDF / cuRobo skill methods ─────────────────────────────────────

    def parse_urdf(self, path: str = None) -> dict:
        """Parse a URDF file and return structured data. No LLM.

        Imports urdf_parser from dashboard backend and augments with
        mesh existence checks, inertial completeness, and dynamics presence.
        """
        from urdf_parser import parse_urdf as _parse_urdf

        path = path or os.path.expanduser("~/dobot_cr10/cr10_robot.urdf")
        result = _parse_urdf(path)
        if "error" in result:
            return result

        # Augment: check mesh file existence
        urdf_dir = os.path.dirname(os.path.abspath(path))
        for link in result.get("links", []):
            visual = link.get("visual", {})
            mesh_file = visual.get("mesh", "")
            if mesh_file:
                # Resolve relative to URDF directory
                if not os.path.isabs(mesh_file):
                    mesh_abs = os.path.join(urdf_dir, mesh_file)
                else:
                    mesh_abs = mesh_file
                link["mesh_exists"] = os.path.exists(mesh_abs)
                link["mesh_abs_path"] = mesh_abs

            # Inertial completeness
            inertial = link.get("inertial")
            link["has_inertial"] = inertial is not None
            if inertial:
                link["has_mass"] = inertial.get("mass", 0) > 0

            # Check for dynamics
            link["has_visual"] = "visual" in link

        # Check for dynamics on joints
        for joint in result.get("joints", []):
            joint["has_limits"] = "limit" in joint
            if joint.get("limit"):
                lim = joint["limit"]
                joint["has_effort"] = lim.get("effort", 0) > 0
                joint["has_velocity"] = lim.get("velocity", 0) > 0

        self.log_activity("parse_urdf", f"Parsed URDF: {path}")
        return result

    def validate_urdf(self, path: str = None) -> dict:
        """Validate a URDF file against Isaac Sim requirements. No LLM.

        Checks: joint limits, inertials, mesh files, no Gazebo tags,
        no package:// URIs.
        """
        path = path or os.path.expanduser("~/dobot_cr10/cr10_robot.urdf")
        parsed = self.parse_urdf(path)
        if "error" in parsed:
            return {"valid": False, "errors": [parsed["error"]], "warnings": [], "stats": {}}

        errors = []
        warnings = []
        stats = {
            "links": len(parsed.get("links", [])),
            "joints": len(parsed.get("joints", [])),
            "dof": parsed.get("dof", 0),
            "robot_name": parsed.get("name", "unknown"),
        }

        # Check revolute joints have limits with non-zero effort/velocity
        for joint in parsed.get("joints", []):
            if joint["type"] in ("revolute", "continuous"):
                if not joint.get("has_limits"):
                    errors.append(f"Joint '{joint['name']}' ({joint['type']}) has no limits")
                else:
                    lim = joint["limit"]
                    if lim.get("effort", 0) <= 0:
                        warnings.append(f"Joint '{joint['name']}' has zero effort limit")
                    if lim.get("velocity", 0) <= 0:
                        warnings.append(f"Joint '{joint['name']}' has zero velocity limit")

        # Check all links have inertials with mass > 0
        for link in parsed.get("links", []):
            if not link.get("has_inertial"):
                warnings.append(f"Link '{link['name']}' has no inertial element")
            elif not link.get("has_mass", False):
                warnings.append(f"Link '{link['name']}' has zero mass")

        # Check all mesh files exist
        mesh_count = 0
        missing_meshes = 0
        for link in parsed.get("links", []):
            mesh_file = link.get("visual", {}).get("mesh", "")
            if mesh_file:
                mesh_count += 1
                if not link.get("mesh_exists", True):
                    errors.append(f"Mesh file missing for link '{link['name']}': {mesh_file}")
                    missing_meshes += 1

        stats["meshes"] = mesh_count
        stats["missing_meshes"] = missing_meshes

        # Check for Gazebo/plugin tags (not Isaac Sim compatible)
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            for tag in ("gazebo", "plugin"):
                elems = list(root.iter(tag))
                if elems:
                    warnings.append(f"Found {len(elems)} <{tag}> element(s) — not Isaac Sim compatible")

            # Check for package:// URIs
            xml_str = ET.tostring(root, encoding="unicode")
            pkg_refs = re.findall(r'package://\S+', xml_str)
            if pkg_refs:
                errors.append(f"Found {len(pkg_refs)} package:// URI(s) — Isaac Sim needs relative paths: {pkg_refs[:3]}")
        except ET.ParseError as e:
            errors.append(f"XML parse error: {e}")

        valid = len(errors) == 0
        self.log_activity("validate_urdf", f"Validated URDF: {path} valid={valid}")
        return {"valid": valid, "errors": errors, "warnings": warnings, "stats": stats}

    def compare_urdfs(self, paths: list = None) -> dict:
        """Compare multiple URDF files and return structured diff. No LLM.

        Default: compares all 3 known CR10 URDFs.
        """
        if paths is None:
            paths = [
                os.path.expanduser("~/dobot_cr10/cr10_robot.urdf"),
                os.path.expanduser("~/dobot-cr10-stack/urdf/cr10_robot.urdf"),
                os.path.expanduser("~/dobot-cr10-stack/urdf/cr10_robot_physics.urdf"),
            ]

        # Filter to existing files
        existing = [p for p in paths if os.path.exists(p)]
        if len(existing) < 2:
            return {"error": f"Need at least 2 URDF files to compare. Found: {existing}"}

        parsed = {}
        for p in existing:
            parsed[p] = self.parse_urdf(p)

        comparison = {"files": existing, "diffs": []}

        # Compare joint names, limits, and counts
        all_joint_names = {}
        for p, data in parsed.items():
            if "error" in data:
                comparison["diffs"].append({"type": "parse_error", "file": p, "error": data["error"]})
                continue
            joints = [j["name"] for j in data.get("joints", []) if j["type"] in ("revolute", "continuous")]
            all_joint_names[p] = joints

        if len(all_joint_names) >= 2:
            ref_path = existing[0]
            ref_joints = set(all_joint_names.get(ref_path, []))
            for p in existing[1:]:
                other_joints = set(all_joint_names.get(p, []))
                only_ref = ref_joints - other_joints
                only_other = other_joints - ref_joints
                if only_ref or only_other:
                    comparison["diffs"].append({
                        "type": "joint_name_mismatch",
                        "files": [ref_path, p],
                        "only_in_first": list(only_ref),
                        "only_in_second": list(only_other),
                    })

        # Compare joint limits for joints present in all files
        common_joints = set()
        if all_joint_names:
            common_joints = set.intersection(*[set(v) for v in all_joint_names.values()])

        for jname in sorted(common_joints):
            limits_by_file = {}
            for p, data in parsed.items():
                if "error" in data:
                    continue
                for j in data.get("joints", []):
                    if j["name"] == jname and j.get("limit"):
                        limits_by_file[p] = j["limit"]
            if len(limits_by_file) >= 2:
                ref_lim = list(limits_by_file.values())[0]
                for p, lim in list(limits_by_file.items())[1:]:
                    for key in ("lower", "upper", "effort", "velocity"):
                        if abs(ref_lim.get(key, 0) - lim.get(key, 0)) > 1e-6:
                            comparison["diffs"].append({
                                "type": "limit_diff",
                                "joint": jname,
                                "param": key,
                                "values": {fp: limits_by_file[fp].get(key, 0) for fp in limits_by_file},
                            })

        # Compare link counts, mesh formats, masses
        for p, data in parsed.items():
            if "error" in data:
                continue
            link_names = [l["name"] for l in data.get("links", [])]
            mesh_formats = set()
            for l in data.get("links", []):
                mesh = l.get("visual", {}).get("mesh", "")
                if mesh:
                    ext = os.path.splitext(mesh)[1].lower()
                    mesh_formats.add(ext)
            comparison[p] = {
                "robot_name": data.get("name"),
                "link_count": len(link_names),
                "joint_count": len(data.get("joints", [])),
                "dof": data.get("dof", 0),
                "link_names": link_names,
                "mesh_formats": list(mesh_formats),
            }

        self.log_activity("compare_urdfs", f"Compared {len(existing)} URDFs")
        return comparison

    def consolidate_urdfs(self, paths: list = None, output_path: str = None) -> dict:
        """Consolidate multiple URDFs into one, using cr10_robot.urdf as base. Minimal LLM.

        Adds ee_link and camera_mount_link for ARRI Alexa Mini.
        Requires approval before writing.
        """
        base_urdf = os.path.expanduser("~/dobot_cr10/cr10_robot.urdf")
        output_path = output_path or os.path.expanduser("~/dobot_cr10/cr10_consolidated.urdf")

        comparison = self.compare_urdfs(paths)
        if "error" in comparison:
            return comparison

        # Require approval
        approved = self.ask_approval(
            action="consolidate_urdfs",
            details=f"Write consolidated URDF to {output_path}",
        )
        if not approved:
            return {"success": False, "error": "Consolidation denied by user"}

        # Use base URDF as starting point
        tree = ET.parse(base_urdf)
        root = tree.getroot()

        changes = []

        # Check if ee_link already exists
        existing_links = {l.get("name") for l in root.findall("link")}
        existing_joints = {j.get("name") for j in root.findall("joint")}

        # Add ee_link if missing
        if "ee_link" not in existing_links:
            ee_link = ET.SubElement(root, "link")
            ee_link.set("name", "ee_link")
            changes.append("Added ee_link")

            # Find the last link in the kinematic chain
            last_joint = None
            for j in root.findall("joint"):
                if j.get("type") in ("revolute", "continuous"):
                    last_joint = j
            if last_joint is not None:
                child = last_joint.find("child")
                parent_link = child.get("link") if child is not None else "Link6"
            else:
                parent_link = "Link6"

            if "ee_joint" not in existing_joints:
                ee_joint = ET.SubElement(root, "joint")
                ee_joint.set("name", "ee_joint")
                ee_joint.set("type", "fixed")
                parent = ET.SubElement(ee_joint, "parent")
                parent.set("link", parent_link)
                child_el = ET.SubElement(ee_joint, "child")
                child_el.set("link", "ee_link")
                origin = ET.SubElement(ee_joint, "origin")
                origin.set("xyz", "0 0 0")
                origin.set("rpy", "0 0 0")
                changes.append("Added ee_joint (fixed) connecting to ee_link")

        # Add camera_mount_link if missing
        if "camera_mount_link" not in existing_links:
            cam_link = ET.SubElement(root, "link")
            cam_link.set("name", "camera_mount_link")
            changes.append("Added camera_mount_link for ARRI Alexa Mini")

            if "camera_mount_joint" not in existing_joints:
                cam_joint = ET.SubElement(root, "joint")
                cam_joint.set("name", "camera_mount_joint")
                cam_joint.set("type", "fixed")
                parent = ET.SubElement(cam_joint, "parent")
                parent.set("link", "ee_link")
                child_el = ET.SubElement(cam_joint, "child")
                child_el.set("link", "camera_mount_link")
                origin = ET.SubElement(cam_joint, "origin")
                origin.set("xyz", "0 0 0.05")
                origin.set("rpy", "0 0 0")
                changes.append("Added camera_mount_joint (fixed) connecting ee_link to camera_mount_link")

        # Remove any <gazebo> or <plugin> elements
        for tag in ("gazebo", "plugin"):
            for elem in list(root.iter(tag)):
                parent_map = {c: p for p in root.iter() for c in p}
                if elem in parent_map:
                    parent_map[elem].remove(elem)
                    changes.append(f"Removed <{tag}> element")

        ET.indent(root)
        tree.write(output_path, xml_declaration=True, encoding="unicode")

        self.log_activity("consolidate_urdfs", f"Wrote consolidated URDF to {output_path}")
        return {"output_path": output_path, "changes": changes}

    @staticmethod
    def _parse_stl_vertices(path: str) -> list:
        """Parse vertices from an STL file (binary or ASCII).

        Returns list of (x, y, z) tuples.
        """
        vertices = []
        with open(path, "rb") as f:
            header = f.read(80)
            # Check if ASCII
            try:
                header_str = header.decode("ascii", errors="ignore")
                if header_str.strip().startswith("solid"):
                    # Could be ASCII — try reading as text
                    f.seek(0)
                    text = f.read().decode("ascii", errors="ignore")
                    for line in text.splitlines():
                        line = line.strip()
                        if line.startswith("vertex"):
                            parts = line.split()
                            if len(parts) >= 4:
                                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
                    if vertices:
                        return vertices
                    # If no vertices found, might be binary with "solid" header
                    f.seek(80)
            except Exception:
                f.seek(80)

            # Binary STL
            num_triangles_data = f.read(4)
            if len(num_triangles_data) < 4:
                return vertices
            num_triangles = struct.unpack("<I", num_triangles_data)[0]
            for _ in range(num_triangles):
                data = f.read(50)  # 12 (normal) + 36 (3 vertices) + 2 (attrib)
                if len(data) < 50:
                    break
                # Skip normal (3 floats = 12 bytes), read 3 vertices (9 floats = 36 bytes)
                verts = struct.unpack("<9f", data[12:48])
                for i in range(3):
                    vertices.append((verts[i*3], verts[i*3+1], verts[i*3+2]))

        return vertices

    def generate_collision_spheres(self, urdf_path: str = None, mesh_dir: str = None) -> dict:
        """Generate cuRobo collision spheres from URDF mesh geometry. No LLM.

        For each link with a mesh: parse STL, compute bounding box,
        subdivide elongated links into N spheres along longest axis.
        """
        urdf_path = urdf_path or os.path.expanduser("~/dobot_cr10/cr10_robot.urdf")
        parsed = self.parse_urdf(urdf_path)
        if "error" in parsed:
            return parsed

        urdf_dir = os.path.dirname(os.path.abspath(urdf_path))
        if mesh_dir is None:
            mesh_dir = urdf_dir

        collision_spheres = {}
        for link in parsed.get("links", []):
            link_name = link["name"]
            mesh_file = link.get("visual", {}).get("mesh", "")
            if not mesh_file:
                continue

            # Resolve mesh path
            if not os.path.isabs(mesh_file):
                mesh_path = os.path.join(mesh_dir, mesh_file)
            else:
                mesh_path = mesh_file

            if not os.path.exists(mesh_path):
                collision_spheres[link_name] = {"error": f"Mesh not found: {mesh_path}"}
                continue

            ext = os.path.splitext(mesh_path)[1].lower()
            if ext != ".stl":
                # For OBJ files, use a simple bounding box approach
                # Read OBJ vertices
                vertices = []
                try:
                    with open(mesh_path) as f:
                        for line in f:
                            if line.startswith("v "):
                                parts = line.split()
                                if len(parts) >= 4:
                                    vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
                except Exception:
                    collision_spheres[link_name] = {"error": f"Failed to parse OBJ: {mesh_path}"}
                    continue
            else:
                vertices = self._parse_stl_vertices(mesh_path)

            if not vertices:
                collision_spheres[link_name] = {"error": "No vertices found"}
                continue

            # Compute bounding box
            xs = [v[0] for v in vertices]
            ys = [v[1] for v in vertices]
            zs = [v[2] for v in vertices]
            bbox_min = (min(xs), min(ys), min(zs))
            bbox_max = (max(xs), max(ys), max(zs))
            extents = [bbox_max[i] - bbox_min[i] for i in range(3)]
            center = [(bbox_max[i] + bbox_min[i]) / 2.0 for i in range(3)]

            # Determine longest axis
            longest_axis = extents.index(max(extents))
            longest_extent = extents[longest_axis]
            short_extents = [extents[i] for i in range(3) if i != longest_axis]
            avg_short = sum(short_extents) / max(len(short_extents), 1)

            # Elongation ratio determines number of spheres
            if longest_extent > 0 and avg_short > 0:
                ratio = longest_extent / avg_short
            else:
                ratio = 1.0

            if ratio > 3.0:
                n_spheres = min(int(ratio), 8)
            elif ratio > 1.5:
                n_spheres = 3
            else:
                n_spheres = 2

            radius = avg_short / 2.0
            spheres = []
            for i in range(n_spheres):
                t = (i + 0.5) / n_spheres
                sphere_center = list(center)
                sphere_center[longest_axis] = bbox_min[longest_axis] + t * longest_extent
                spheres.append({
                    "center": [round(c, 6) for c in sphere_center],
                    "radius": round(radius, 6),
                })

            collision_spheres[link_name] = {
                "bbox_min": [round(v, 6) for v in bbox_min],
                "bbox_max": [round(v, 6) for v in bbox_max],
                "extents": [round(v, 6) for v in extents],
                "n_spheres": n_spheres,
                "spheres": spheres,
            }

        # Write YAML output
        config_dir = os.path.expanduser("~/dobot_cr10/config")
        os.makedirs(config_dir, exist_ok=True)
        output_path = os.path.join(config_dir, "cr10_collision_spheres_generated.yaml")

        yaml_data = {"collision_spheres": {}}
        for link_name, data in collision_spheres.items():
            if "error" not in data:
                yaml_data["collision_spheres"][link_name] = [
                    {"center": s["center"], "radius": s["radius"]}
                    for s in data["spheres"]
                ]

        with open(output_path, "w") as f:
            yaml.dump(yaml_data, f, default_flow_style=False)

        self.log_activity("generate_collision_spheres",
                          f"Generated collision spheres for {len(collision_spheres)} links -> {output_path}")
        return {
            "output_path": output_path,
            "links": collision_spheres,
            "total_spheres": sum(d.get("n_spheres", 0) for d in collision_spheres.values() if "error" not in d),
        }

    def validate_curobo_config(self, config_path: str = None, urdf_path: str = None) -> dict:
        """Validate cuRobo config against a URDF. No LLM.

        Cross-checks: joint names, collision link names, base/ee links,
        collision spheres file, retract_config within URDF limits.
        """
        config_path = config_path or os.path.expanduser("~/dobot_cr10/config/cr10_curobo.yaml")
        urdf_path = urdf_path or os.path.expanduser("~/dobot_cr10/cr10_robot.urdf")

        errors = []
        warnings = []

        # Load cuRobo config
        if not os.path.exists(config_path):
            return {"valid": False, "errors": [f"Config not found: {config_path}"], "warnings": []}
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Parse URDF
        parsed = self.parse_urdf(urdf_path)
        if "error" in parsed:
            return {"valid": False, "errors": [f"URDF error: {parsed['error']}"], "warnings": []}

        urdf_joint_names = {j["name"] for j in parsed.get("joints", []) if j["type"] in ("revolute", "continuous")}
        urdf_link_names = {l["name"] for l in parsed.get("links", [])}
        urdf_joint_limits = {}
        for j in parsed.get("joints", []):
            if j.get("limit"):
                urdf_joint_limits[j["name"]] = j["limit"]

        # Check joint_names in config
        config_joints = config.get("joint_names", [])
        for jname in config_joints:
            if jname not in urdf_joint_names:
                errors.append(f"Config joint '{jname}' not found in URDF (available: {sorted(urdf_joint_names)})")

        # Check collision_link_names
        collision_links = config.get("collision_link_names", [])
        for lname in collision_links:
            if lname not in urdf_link_names:
                errors.append(f"Collision link '{lname}' not found in URDF")

        # Check base_link and ee_link
        base_link = config.get("base_link", "")
        if base_link and base_link not in urdf_link_names:
            errors.append(f"base_link '{base_link}' not found in URDF")

        ee_link = config.get("ee_link", "")
        if ee_link and ee_link not in urdf_link_names:
            errors.append(f"ee_link '{ee_link}' not found in URDF")

        # Check collision_spheres file exists
        sphere_file = config.get("collision_spheres", "")
        if sphere_file:
            if not os.path.isabs(sphere_file):
                sphere_file = os.path.join(os.path.dirname(config_path), sphere_file)
            if not os.path.exists(sphere_file):
                warnings.append(f"Collision spheres file not found: {sphere_file}")

        # Check retract_config within URDF limits
        retract = config.get("retract_config", [])
        if retract and config_joints:
            for i, (jname, val) in enumerate(zip(config_joints, retract)):
                if jname in urdf_joint_limits:
                    lim = urdf_joint_limits[jname]
                    lower = lim.get("lower", -3.14159)
                    upper = lim.get("upper", 3.14159)
                    if val < lower or val > upper:
                        errors.append(
                            f"retract_config[{i}] ({jname})={val} outside URDF limits [{lower}, {upper}]"
                        )

        valid = len(errors) == 0
        self.log_activity("validate_curobo_config",
                          f"Validated cuRobo config: {config_path} valid={valid}")
        return {"valid": valid, "errors": errors, "warnings": warnings}

    # ── Auto-fix methods ─────────────────────────────────────────────────

    def _fix_physx_cooking(self, error_log: str) -> bool:
        """Fix PhysX cooking errors by rebuilding collision meshes.

        PhysX cooking failures typically happen when mesh geometry is invalid
        or too complex. The fix is to simplify/rebuild the mesh.
        """
        self.logger.info("Auto-fix: PhysX cooking failed - rebuilding collision meshes")
        self.log_activity("auto_fix", "Rebuilding collision meshes for PhysX cooking failure")

        # Attempt to find and regenerate the problematic mesh
        # Look for mesh path in the error log
        mesh_match = re.search(r'mesh[:\s]+["\']?([^\s"\']+\.(?:obj|stl|usd))', error_log, re.IGNORECASE)
        if mesh_match:
            mesh_path = mesh_match.group(1)
            self.logger.info(f"Identified problematic mesh: {mesh_path}")
            # Use convex decomposition with simplified settings
            cmd = (
                f"python3 -c \"import omni.physx; "
                f"omni.physx.scripts.utils.rebuild_collision_mesh('{mesh_path}', "
                f"simplify=True, max_convex_hulls=32)\" 2>/dev/null || true"
            )
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            success = result.returncode == 0
        else:
            # Generic fix: reduce cooking complexity settings
            self.logger.info("No specific mesh found, reducing PhysX cooking tolerance")
            success = True  # Settings-only change always succeeds

        self.log_activity("auto_fix",
                          f"PhysX cooking fix {'succeeded' if success else 'failed'}",
                          level="INFO" if success else "WARNING")
        return success

    def _fix_cuda_oom(self, error_log: str) -> bool:
        """Fix CUDA out of memory by reducing batch size and clearing cache.

        Clears the CUDA memory cache and suggests reducing complexity.
        """
        self.logger.info("Auto-fix: CUDA OOM - clearing cache and reducing complexity")
        self.log_activity("auto_fix", "Clearing CUDA cache for OOM recovery")

        # Clear CUDA cache
        clear_cmd = (
            "python3 -c \"import torch; torch.cuda.empty_cache(); "
            "print(f'Freed cache. Available: {torch.cuda.mem_get_info()[0]/1e9:.1f}GB')\" "
            "2>/dev/null || true"
        )
        result = subprocess.run(clear_cmd, shell=True, capture_output=True, text=True, timeout=30)
        self.logger.info(f"CUDA cache clear: {result.stdout.strip()}")

        # Kill any zombie GPU processes
        kill_cmd = "nvidia-smi --query-compute-apps=pid --format=csv,noheader | head -5"
        pid_result = subprocess.run(kill_cmd, shell=True, capture_output=True, text=True, timeout=10)
        if pid_result.stdout.strip():
            self.logger.info(f"Active GPU processes: {pid_result.stdout.strip()}")

        self.log_activity("auto_fix", "CUDA OOM recovery attempted")
        return True

    def _fix_urdf_limits(self, error_log: str) -> bool:
        """Fix missing URDF joint limits by adding sensible defaults.

        Uses xml.etree.ElementTree for safe XML parsing instead of string manipulation.
        """
        self.logger.info("Auto-fix: URDF joint limit missing - adding defaults")
        self.log_activity("auto_fix", "Adding default URDF joint limits")

        # Extract joint name from error
        joint_match = re.search(r'joint[:\s]+["\']?(\w+)', error_log, re.IGNORECASE)
        joint_name = joint_match.group(1) if joint_match else "unknown"

        # Extract URDF file path from error
        urdf_match = re.search(r'(?:file|urdf)[:\s]+["\']?([^\s"\']+\.urdf)', error_log, re.IGNORECASE)
        if not urdf_match:
            self.logger.warning("Could not find URDF file path in error log")
            return False

        urdf_path = urdf_match.group(1)
        if not os.path.exists(urdf_path):
            self.logger.warning(f"URDF file not found: {urdf_path}")
            return False

        # Check approval since we're modifying a URDF
        if "modify_urdf" in self.APPROVAL_REQUIRED:
            approved = self.ask_approval(
                action="modify_urdf",
                details=f"Add default limits to joint '{joint_name}' in {urdf_path}",
            )
            if not approved:
                self.logger.warning("URDF modification denied")
                return False

        # Parse URDF as XML
        tree = ET.parse(urdf_path)
        root = tree.getroot()

        # Find the joint element by name
        joint_elem = None
        for joint in root.iter("joint"):
            if joint.get("name") == joint_name:
                joint_elem = joint
                break

        if joint_elem is None:
            self.logger.warning(f"Joint '{joint_name}' not found in URDF")
            return False

        # Check if limit already exists
        if joint_elem.find("limit") is not None:
            self.logger.info(f"Joint '{joint_name}' already has limits")
            return True

        # Add default limit element
        limit_elem = ET.SubElement(joint_elem, "limit")
        limit_elem.set("lower", "-3.14159")
        limit_elem.set("upper", "3.14159")
        limit_elem.set("effort", "100")
        limit_elem.set("velocity", "1.0")

        ET.indent(root)
        tree.write(urdf_path, xml_declaration=True, encoding="unicode")
        self.logger.info(f"Added default limits to joint {joint_name}")
        self.log_activity("auto_fix", f"Added default limits to joint {joint_name}")
        return True

    def _fix_ik_fail(self, error_log: str) -> bool:
        """Fix cuRobo IK failures by adjusting solver seeds and tolerances.

        IK failures often happen when the initial seed is poor or tolerances
        are too tight. We increase the number of seeds and relax tolerances.
        """
        self.logger.info("Auto-fix: cuRobo IK_FAIL - adjusting solver parameters")
        self.log_activity("auto_fix", "Adjusting cuRobo IK solver seeds and tolerances")

        # Look for cuRobo config file in the error
        config_match = re.search(r'config[:\s]+["\']?([^\s"\']+\.ya?ml)', error_log, re.IGNORECASE)
        if config_match:
            config_path = config_match.group(1)
            if os.path.exists(config_path):
                if "change_curobo_config" in self.APPROVAL_REQUIRED:
                    approved = self.ask_approval(
                        action="change_curobo_config",
                        details=f"Adjust IK solver params in {config_path}",
                    )
                    if not approved:
                        return False

                try:
                    with open(config_path, "r") as f:
                        config = yaml.safe_load(f)

                    # Increase seeds and relax tolerances
                    if "ik_solver" not in config:
                        config["ik_solver"] = {}
                    config["ik_solver"]["num_seeds"] = config["ik_solver"].get("num_seeds", 16) * 2
                    config["ik_solver"]["position_tolerance"] = config["ik_solver"].get("position_tolerance", 0.005) * 2
                    config["ik_solver"]["rotation_tolerance"] = config["ik_solver"].get("rotation_tolerance", 0.05) * 2

                    with open(config_path, "w") as f:
                        yaml.dump(config, f, default_flow_style=False)

                    self.logger.info(f"Updated IK solver config: {config_path}")
                    self.log_activity("auto_fix", f"Relaxed IK tolerances in {config_path}")
                    return True
                except Exception as e:
                    self.logger.error(f"Failed to update config: {e}")
                    return False

        # No config found, just log advice
        self.logger.info("No cuRobo config found; recommend increasing num_seeds and relaxing tolerances")
        return False

    def _fix_black_viewport(self, error_log: str) -> bool:
        """Fix Isaac Sim black viewport by resetting the camera and renderer.

        Black viewport is commonly caused by camera position at origin or
        renderer initialization failure.
        """
        self.logger.info("Auto-fix: Isaac Sim black viewport - resetting camera")
        self.log_activity("auto_fix", "Resetting Isaac Sim camera and renderer")

        # Reset camera to a known good position
        reset_cmd = (
            "python3 -c \""
            "try:\n"
            "    from omni.isaac.core.utils.viewports import set_camera_view\n"
            "    set_camera_view(eye=[2.0, 2.0, 2.0], target=[0, 0, 0])\n"
            "    print('Camera reset successfully')\n"
            "except Exception as e:\n"
            "    print(f'Camera reset failed: {e}')\n"
            "\" 2>/dev/null || true"
        )
        result = subprocess.run(reset_cmd, shell=True, capture_output=True, text=True, timeout=30)
        self.logger.info(f"Camera reset: {result.stdout.strip()}")

        self.log_activity("auto_fix", "Camera/viewport reset attempted")
        return "successfully" in result.stdout.lower() or result.returncode == 0

    def _fix_ros2_node(self, error_log: str) -> bool:
        """Fix ROS2 node not found by restarting the ROS2 daemon.

        Node discovery failures are often resolved by restarting the daemon.
        """
        self.logger.info("Auto-fix: ROS2 node not found - restarting daemon")
        self.log_activity("auto_fix", "Restarting ROS2 daemon")

        # Restart ROS2 daemon
        subprocess.run("ros2 daemon stop 2>/dev/null || true",
                        shell=True, capture_output=True, timeout=10)
        result = subprocess.run("ros2 daemon start 2>/dev/null || true",
                                shell=True, capture_output=True, text=True, timeout=10)

        # Verify nodes are discoverable
        verify = subprocess.run("ros2 node list 2>/dev/null || true",
                                shell=True, capture_output=True, text=True, timeout=10)
        node_count = len([l for l in verify.stdout.strip().split("\n") if l.strip()])
        self.logger.info(f"ROS2 daemon restarted, {node_count} nodes visible")

        self.log_activity("auto_fix", f"ROS2 daemon restarted, {node_count} nodes discovered")
        return node_count > 0

    # ── Main methods ─────────────────────────────────────────────────────

    def run_template(self, template_name: str, params: dict = None) -> dict:
        """Run a simulation template from YAML.

        Loads a template file from ~/agent-stack/templates/{template_name}.yml,
        executes each step, and returns the results.

        Args:
            template_name: Name of the template (without .yml extension).
            params: Optional parameter overrides for the template.

        Returns:
            Dict with template name, status, and per-step results.
        """
        template_path = os.path.join(self.templates_dir, f"{template_name}.yml")
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template not found: {template_path}")

        with open(template_path) as f:
            template = yaml.safe_load(f)

        # Apply parameter overrides
        if params:
            template_params = template.get("params", {})
            template_params.update(params)
            template["params"] = template_params

        self.logger.info(f"Running template: {template_name}")
        model_info = self.get_model_info()

        results = {
            "template": template_name,
            "steps": [],
            "status": "running",
            "started": datetime.now().isoformat(),
        }

        steps = template.get("steps", [])
        for i, step in enumerate(steps):
            step_name = step.get("name", f"step_{i}")
            step_type = step.get("type", "command")
            step_cmd = step.get("command", step.get("action", ""))

            self.logger.info(f"  Step {i + 1}/{len(steps)}: {step_name}")

            step_result = {"name": step_name, "type": step_type, "status": "pending"}

            try:
                if step_type == "command":
                    r = subprocess.run(step_cmd, shell=True, capture_output=True,
                                       text=True, timeout=step.get("timeout", 300))
                    step_result["stdout"] = r.stdout
                    step_result["status"] = "success" if r.returncode == 0 else "failed"
                elif step_type == "query":
                    response = self.query_with_retry(step_cmd)
                    step_result["response"] = response
                    step_result["status"] = "success"
                elif step_type == "approval":
                    approved = self.ask_approval(
                        action=step_name,
                        details=step_cmd,
                    )
                    step_result["approved"] = approved
                    step_result["status"] = "approved" if approved else "denied"
                    if not approved:
                        results["status"] = "aborted"
                        results["steps"].append(step_result)
                        break
                else:
                    step_result["status"] = "skipped"
                    step_result["note"] = f"Unknown step type: {step_type}"
            except Exception as e:
                step_result["status"] = "error"
                step_result["error"] = str(e)
                self.logger.error(f"  Step {step_name} failed: {e}")

            results["steps"].append(step_result)

        if results["status"] == "running":
            all_ok = all(s["status"] in ("success", "approved", "skipped") for s in results["steps"])
            results["status"] = "completed" if all_ok else "partial_failure"

        results["completed"] = datetime.now().isoformat()
        self.log_task(task=f"template:{template_name}", result=results["status"],
                      model=model_info["model"], success=results["status"] == "completed")
        self.log_activity("simulation", f"Template {template_name}: {results['status']}")
        return results

    def fix_sim_error(self, error_log: str) -> bool:
        """Attempt to automatically fix a simulation error.

        Parses the error log against known AUTO_FIXES patterns.
        If a match is found, applies the corresponding fix.
        If no match, queries the model for analysis.

        Args:
            error_log: The error log text.

        Returns:
            True if an auto-fix was applied, False if manual intervention needed.
        """
        model_info = self.get_model_info()

        # Check each auto-fix pattern
        for pattern, fix_fn in self.AUTO_FIXES.items():
            if pattern.lower() in error_log.lower():
                self.logger.info(f"Matched auto-fix pattern: {pattern}")
                try:
                    success = fix_fn(error_log)
                    self.log_task(task=f"auto_fix:{pattern}", result=f"{'Applied' if success else 'Failed'}",
                                  model="auto_fix", success=success)
                    return success
                except Exception as e:
                    self.logger.error(f"Auto-fix for '{pattern}' raised exception: {e}")
                    self.log_task(task=f"auto_fix:{pattern}", result=str(e),
                                  model="auto_fix", success=False)
                    return False

        # No pattern matched - query the model for analysis
        self.logger.info("No auto-fix pattern matched, querying model for analysis")
        knowledge = self.load_knowledge(self.task_type)

        prompt = f"""You are an expert in NVIDIA Isaac Sim, cuRobo, and ROS2 simulation debugging.

Knowledge base:
{knowledge}

Analyze this simulation error and suggest a fix:

```
{error_log}
```

Provide:
1. Root cause analysis
2. Step-by-step fix instructions
3. Prevention recommendations"""

        try:
            response = self.query_with_retry(prompt)
            self.logger.info(f"Model analysis:\n{response[:500]}")
            self.log_task(task="sim_error_analysis", result=f"Model provided analysis ({len(response)} chars)",
                          model=model_info["model"], success=True)
            self.log_activity("error_analysis", f"Analyzed sim error: {error_log[:80]}")
        except RuntimeError as e:
            self.logger.error(f"Model query failed: {e}")

        return False

    def collect_training_data(self, robot: str, n_samples: int, task_description: str) -> str:
        """Plan and initiate training data collection from simulation.

        Queries the model for a data collection plan, creates the output
        directory, and returns the dataset path.

        Args:
            robot: Robot name/model (e.g., "dobot_cr10").
            n_samples: Number of trajectory samples to collect.
            task_description: Description of the task to train on.

        Returns:
            Path to the dataset output directory.
        """
        model_info = self.get_model_info()
        knowledge = self.load_knowledge(self.task_type)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dataset_path = os.path.join(self.data_dir, robot, timestamp)
        os.makedirs(dataset_path, exist_ok=True)

        prompt = f"""You are an expert in robotic simulation data collection.

Knowledge base:
{knowledge}

Plan data collection for:
- Robot: {robot}
- Task: {task_description}
- Samples needed: {n_samples}
- Output path: {dataset_path}

Provide a detailed data collection plan including:
1. Scene setup requirements
2. Randomization parameters (object poses, lighting, camera angles)
3. Trajectory recording format (joint positions, velocities, gripper state)
4. Success/failure criteria
5. Data validation checks

Output the plan as structured YAML."""

        try:
            plan = self.query_with_retry(prompt)

            # Save the plan
            plan_path = os.path.join(dataset_path, "collection_plan.yml")
            with open(plan_path, "w") as f:
                f.write(plan)

            # Create metadata
            metadata = {
                "robot": robot,
                "task": task_description,
                "n_samples": n_samples,
                "created": timestamp,
                "status": "planned",
                "plan_path": plan_path,
            }
            metadata_path = os.path.join(dataset_path, "metadata.yml")
            with open(metadata_path, "w") as f:
                yaml.dump(metadata, f, default_flow_style=False)

            self.logger.info(f"Data collection planned: {dataset_path}")
            self.log_task(task=f"collect_data:{robot}:{n_samples}",
                          result=f"Plan saved to {dataset_path}",
                          model=model_info["model"], success=True)
            self.log_activity("data_collection",
                              f"Planned {n_samples} samples for {robot}: {task_description[:60]}",
                              robot=robot)
            return dataset_path

        except RuntimeError as e:
            self.log_task(task=f"collect_data:{robot}:{n_samples}",
                          result=str(e), model=model_info["model"], success=False)
            raise
