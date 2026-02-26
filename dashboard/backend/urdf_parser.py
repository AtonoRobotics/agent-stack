#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""URDF parser for Dobot CR10 robot description."""

import os
import xml.etree.ElementTree as ET
from typing import Optional


URDF_PATH = os.path.expanduser(
    "~/Downloads/TCP-IP-ROS-6AXis-main/dobot_description/urdf/cr10_robot.urdf"
)


def _parse_origin(element) -> dict:
    """Parse an <origin> element into xyz and rpy lists."""
    if element is None:
        return {"xyz": [0.0, 0.0, 0.0], "rpy": [0.0, 0.0, 0.0]}
    xyz = [float(v) for v in element.get("xyz", "0 0 0").split()]
    rpy = [float(v) for v in element.get("rpy", "0 0 0").split()]
    return {"xyz": xyz, "rpy": rpy}


def _parse_axis(element) -> list:
    """Parse an <axis> element into xyz list."""
    if element is None:
        return [0.0, 0.0, 1.0]
    return [float(v) for v in element.get("xyz", "0 0 1").split()]


def _parse_limit(element) -> Optional[dict]:
    """Parse a <limit> element into dict with lower/upper/effort/velocity."""
    if element is None:
        return None
    return {
        "lower": float(element.get("lower", "0")),
        "upper": float(element.get("upper", "0")),
        "effort": float(element.get("effort", "0")),
        "velocity": float(element.get("velocity", "0")),
    }


def _parse_inertial(element) -> Optional[dict]:
    """Parse an <inertial> element."""
    if element is None:
        return None
    origin = _parse_origin(element.find("origin"))
    mass_el = element.find("mass")
    mass = float(mass_el.get("value", "0")) if mass_el is not None else 0.0
    return {"origin": origin, "mass": mass}


def parse_urdf(urdf_path: str = None) -> dict:
    """Parse a URDF file and return structured JSON-serializable dict.

    Returns:
        dict with keys: name, links, joints, kinematic_chain
    """
    path = urdf_path or URDF_PATH
    if not os.path.exists(path):
        return {"error": f"URDF file not found: {path}", "path": path}

    tree = ET.parse(path)
    root = tree.getroot()
    robot_name = root.get("name", "unknown")

    # Parse links
    links = []
    for link_el in root.findall("link"):
        link_name = link_el.get("name", "")
        link_data = {"name": link_name}

        inertial = _parse_inertial(link_el.find("inertial"))
        if inertial:
            link_data["inertial"] = inertial

        visual = link_el.find("visual")
        if visual is not None:
            link_data["visual"] = {
                "origin": _parse_origin(visual.find("origin")),
            }
            geom = visual.find("geometry")
            if geom is not None:
                mesh = geom.find("mesh")
                if mesh is not None:
                    link_data["visual"]["mesh"] = mesh.get("filename", "")

        links.append(link_data)

    # Parse joints
    joints = []
    for joint_el in root.findall("joint"):
        joint_name = joint_el.get("name", "")
        joint_type = joint_el.get("type", "fixed")

        parent_el = joint_el.find("parent")
        child_el = joint_el.find("child")

        joint_data = {
            "name": joint_name,
            "type": joint_type,
            "parent": parent_el.get("link", "") if parent_el is not None else "",
            "child": child_el.get("link", "") if child_el is not None else "",
            "origin": _parse_origin(joint_el.find("origin")),
            "axis": _parse_axis(joint_el.find("axis")),
        }

        limit = _parse_limit(joint_el.find("limit"))
        if limit:
            joint_data["limit"] = limit

        joints.append(joint_data)

    # Build kinematic chain (only revolute/continuous joints in order)
    kinematic_chain = []
    for j in joints:
        if j["type"] in ("revolute", "continuous"):
            kinematic_chain.append({
                "joint": j["name"],
                "parent": j["parent"],
                "child": j["child"],
                "origin": j["origin"],
                "axis": j["axis"],
                "limit": j.get("limit"),
            })

    return {
        "name": robot_name,
        "path": path,
        "links": links,
        "joints": joints,
        "kinematic_chain": kinematic_chain,
        "dof": len(kinematic_chain),
    }


if __name__ == "__main__":
    import json
    result = parse_urdf()
    print(json.dumps(result, indent=2))
