#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Camera, lens, and accessory database for Dobot CR10 payload system.

Provides physics calculations for payload CoM, inertia, and joint torque
margins. Includes preset management for saved configurations.
"""

import json
import math
import os
from pathlib import Path

# ── Camera Bodies ─────────────────────────────────────────

CAMERA_BODIES = {
    "alexa_mini": {
        "name": "Arri Alexa Mini",
        "mass_kg": 2.3,
        "dims_mm": {"l": 130, "w": 114, "h": 58},
        "com_offset_mm": {"x": 45, "y": 0, "z": 22},
        "mount": "PL",
        "sensor": "Super35",
        "manufacturer": "ARRI",
    },
    "alexa_mini_lf": {
        "name": "Arri Alexa Mini LF",
        "mass_kg": 2.6,
        "dims_mm": {"l": 130, "w": 114, "h": 58},
        "com_offset_mm": {"x": 47, "y": 0, "z": 24},
        "mount": "LPL",
        "sensor": "LF",
        "manufacturer": "ARRI",
    },
    "alexa_35": {
        "name": "Arri Alexa 35",
        "mass_kg": 3.5,
        "dims_mm": {"l": 152, "w": 146, "h": 152},
        "com_offset_mm": {"x": 52, "y": 0, "z": 28},
        "mount": "LPL",
        "sensor": "Super35",
        "manufacturer": "ARRI",
    },
    "v_raptor_8k": {
        "name": "RED V-Raptor 8K",
        "mass_kg": 2.45,
        "dims_mm": {"l": 152, "w": 95, "h": 95},
        "com_offset_mm": {"x": 48, "y": 0, "z": 18},
        "mount": "PL",
        "sensor": "VistaVision",
        "manufacturer": "RED",
    },
    "komodo_6k": {
        "name": "RED Komodo 6K",
        "mass_kg": 1.0,
        "dims_mm": {"l": 101, "w": 76, "h": 76},
        "com_offset_mm": {"x": 35, "y": 0, "z": 15},
        "mount": "PL",
        "sensor": "Super35",
        "manufacturer": "RED",
    },
    "monstro_8k": {
        "name": "RED Monstro 8K VV",
        "mass_kg": 2.86,
        "dims_mm": {"l": 165, "w": 95, "h": 95},
        "com_offset_mm": {"x": 55, "y": 0, "z": 20},
        "mount": "PL",
        "sensor": "VistaVision",
        "manufacturer": "RED",
    },
    "venice_2_8k": {
        "name": "Sony Venice 2 8K",
        "mass_kg": 3.89,
        "dims_mm": {"l": 192, "w": 138, "h": 208},
        "com_offset_mm": {"x": 58, "y": 0, "z": 32},
        "mount": "PL",
        "sensor": "Full Frame",
        "manufacturer": "Sony",
    },
    "fx9": {
        "name": "Sony FX9",
        "mass_kg": 1.0,
        "dims_mm": {"l": 152, "w": 168, "h": 190},
        "com_offset_mm": {"x": 42, "y": 0, "z": 28},
        "mount": "E",
        "sensor": "Full Frame",
        "manufacturer": "Sony",
    },
    "fx6": {
        "name": "Sony FX6",
        "mass_kg": 0.89,
        "dims_mm": {"l": 126, "w": 121, "h": 124},
        "com_offset_mm": {"x": 38, "y": 0, "z": 22},
        "mount": "E",
        "sensor": "Full Frame",
        "manufacturer": "Sony",
    },
}

# ── Lenses ────────────────────────────────────────────────

LENSES = {
    "zeiss_mp_18": {
        "name": "Zeiss Master Prime 18mm T1.3",
        "mass_kg": 1.5,
        "length_mm": 112,
        "diameter_mm": 95,
        "com_offset_mm": 45,
        "mount": "PL",
        "manufacturer": "Zeiss",
        "max_aperture": "T1.3",
    },
    "zeiss_mp_25": {
        "name": "Zeiss Master Prime 25mm T1.3",
        "mass_kg": 1.7,
        "length_mm": 121,
        "diameter_mm": 95,
        "com_offset_mm": 52,
        "mount": "PL",
        "manufacturer": "Zeiss",
        "max_aperture": "T1.3",
    },
    "zeiss_mp_35": {
        "name": "Zeiss Master Prime 35mm T1.3",
        "mass_kg": 1.6,
        "length_mm": 128,
        "diameter_mm": 95,
        "com_offset_mm": 55,
        "mount": "PL",
        "manufacturer": "Zeiss",
        "max_aperture": "T1.3",
    },
    "zeiss_mp_50": {
        "name": "Zeiss Master Prime 50mm T1.3",
        "mass_kg": 1.5,
        "length_mm": 136,
        "diameter_mm": 95,
        "com_offset_mm": 58,
        "mount": "PL",
        "manufacturer": "Zeiss",
        "max_aperture": "T1.3",
    },
    "zeiss_mp_85": {
        "name": "Zeiss Master Prime 85mm T1.3",
        "mass_kg": 1.8,
        "length_mm": 152,
        "diameter_mm": 95,
        "com_offset_mm": 65,
        "mount": "PL",
        "manufacturer": "Zeiss",
        "max_aperture": "T1.3",
    },
    "cooke_s4_25": {
        "name": "Cooke S4/i 25mm T2",
        "mass_kg": 1.55,
        "length_mm": 136,
        "diameter_mm": 110,
        "com_offset_mm": 52,
        "mount": "PL",
        "manufacturer": "Cooke",
        "max_aperture": "T2",
    },
    "cooke_s4_32": {
        "name": "Cooke S4/i 32mm T2",
        "mass_kg": 1.6,
        "length_mm": 145,
        "diameter_mm": 110,
        "com_offset_mm": 55,
        "mount": "PL",
        "manufacturer": "Cooke",
        "max_aperture": "T2",
    },
    "cooke_s4_50": {
        "name": "Cooke S4/i 50mm T2",
        "mass_kg": 1.7,
        "length_mm": 152,
        "diameter_mm": 110,
        "com_offset_mm": 60,
        "mount": "PL",
        "manufacturer": "Cooke",
        "max_aperture": "T2",
    },
    "leica_slx_18": {
        "name": "Leica Summilux-C 18mm T1.4",
        "mass_kg": 0.88,
        "length_mm": 98,
        "diameter_mm": 95,
        "com_offset_mm": 42,
        "mount": "PL",
        "manufacturer": "Leica",
        "max_aperture": "T1.4",
    },
    "leica_slx_25": {
        "name": "Leica Summilux-C 25mm T1.4",
        "mass_kg": 0.93,
        "length_mm": 104,
        "diameter_mm": 95,
        "com_offset_mm": 45,
        "mount": "PL",
        "manufacturer": "Leica",
        "max_aperture": "T1.4",
    },
    "leica_slx_35": {
        "name": "Leica Summilux-C 35mm T1.4",
        "mass_kg": 0.95,
        "length_mm": 108,
        "diameter_mm": 95,
        "com_offset_mm": 48,
        "mount": "PL",
        "manufacturer": "Leica",
        "max_aperture": "T1.4",
    },
}

# ── Accessories ───────────────────────────────────────────

ACCESSORIES = {
    "preston_mdr4": {
        "name": "Preston MDR4",
        "mass_kg": 0.4,
        "com_offset_mm": {"x": 0, "y": 35, "z": 0},
    },
    "matte_box_small": {
        "name": "Matte Box (4x5.65)",
        "mass_kg": 0.8,
        "com_offset_mm": {"x": 80, "y": 0, "z": 0},
    },
    "matte_box_large": {
        "name": "Matte Box (6x6)",
        "mass_kg": 1.4,
        "com_offset_mm": {"x": 95, "y": 0, "z": 0},
    },
    "monitor_5in": {
        "name": "On-board Monitor 5 inch",
        "mass_kg": 0.4,
        "com_offset_mm": {"x": 0, "y": 0, "z": 45},
    },
    "wireless_tx": {
        "name": "Wireless Video TX",
        "mass_kg": 0.2,
        "com_offset_mm": {"x": 0, "y": -35, "z": 25},
    },
    "custom": {
        "name": "Custom Accessory",
        "mass_kg": 0.0,
        "com_offset_mm": {"x": 0, "y": 0, "z": 0},
    },
}

# ── Presets ────────────────────────────────────────────────

DEFAULT_PRESETS = {
    "Alpha CR10 - Alexa Mini 35mm": {
        "camera_id": "alexa_mini",
        "lens_id": "zeiss_mp_35",
        "accessory_ids": ["preston_mdr4"],
    },
    "Alpha CR10 - Alexa Mini 50mm": {
        "camera_id": "alexa_mini",
        "lens_id": "zeiss_mp_50",
        "accessory_ids": ["preston_mdr4"],
    },
}

PRESET_PATH = Path.home() / "agent-stack" / "data" / "camera_presets.json"

# CR10 constants
CR10_MAX_PAYLOAD_KG = 10.0
CR10_MAX_COM_OFFSET_MM = 50.0
CR10_RATED_TORQUES = {"J1": 544, "J2": 544, "J3": 180, "J4": 55, "J5": 55, "J6": 28}
CR10_DH = {"d1": 0.1765, "a2": 0.607, "a3": 0.568, "d4": 0.191, "d5": 0.125, "d6": 0.1084}


# ── Accessor functions ────────────────────────────────────

def get_cameras() -> dict:
    """Return the camera bodies database."""
    return CAMERA_BODIES


def get_lenses() -> dict:
    """Return the lens database."""
    return LENSES


def get_accessories() -> dict:
    """Return the accessories database."""
    return ACCESSORIES


# ── Physics calculations ──────────────────────────────────

def calculate_payload(camera_id: str, lens_id: str,
                      accessory_ids: list[str],
                      mount_mass_kg: float = 0.5) -> dict:
    """Calculate total payload physics for a camera/lens/accessory combination.

    Returns mass, CoM, inertia tensor, limit checks, warnings, and torque margins.
    """
    camera = CAMERA_BODIES.get(camera_id)
    lens = LENSES.get(lens_id)
    if not camera:
        raise ValueError(f"Unknown camera: {camera_id}")
    if not lens:
        raise ValueError(f"Unknown lens: {lens_id}")

    accessories = []
    for aid in accessory_ids:
        acc = ACCESSORIES.get(aid)
        if not acc:
            raise ValueError(f"Unknown accessory: {aid}")
        accessories.append(acc)

    # Sum masses
    total_mass = camera["mass_kg"] + lens["mass_kg"] + mount_mass_kg
    total_mass += sum(a["mass_kg"] for a in accessories)

    # Weighted CoM (in mm, relative to J6 flange)
    # Components: (mass, x_mm, y_mm, z_mm)
    components = []
    cam_com = camera["com_offset_mm"]
    components.append((camera["mass_kg"], cam_com["x"], cam_com["y"], cam_com["z"]))
    # Lens com_offset_mm is axial (x-axis) offset
    components.append((lens["mass_kg"], lens["com_offset_mm"], 0, 0))
    # Mount at origin
    components.append((mount_mass_kg, 0, 0, 0))
    for a in accessories:
        ac = a["com_offset_mm"]
        components.append((a["mass_kg"], ac["x"], ac["y"], ac["z"]))

    com_x = sum(m * x for m, x, _, _ in components) / total_mass
    com_y = sum(m * y for m, _, y, _ in components) / total_mass
    com_z = sum(m * z for m, _, _, z in components) / total_mass
    com_offset_mm = {"x": round(com_x, 2), "y": round(com_y, 2), "z": round(com_z, 2)}
    com_dist = math.sqrt(com_x ** 2 + com_y ** 2 + com_z ** 2)

    # Inertia tensor (kg*m^2) via parallel axis theorem
    # Each component as point mass at its CoM offset from flange
    tensor = [[0.0] * 3 for _ in range(3)]
    for m, x_mm, y_mm, z_mm in components:
        x, y, z = x_mm * 1e-3, y_mm * 1e-3, z_mm * 1e-3
        tensor[0][0] += m * (y * y + z * z)
        tensor[1][1] += m * (x * x + z * z)
        tensor[2][2] += m * (x * x + y * y)
        tensor[0][1] -= m * x * y
        tensor[1][0] -= m * x * y
        tensor[0][2] -= m * x * z
        tensor[2][0] -= m * x * z
        tensor[1][2] -= m * y * z
        tensor[2][1] -= m * y * z

    # Round tensor values
    for i in range(3):
        for j in range(3):
            tensor[i][j] = round(tensor[i][j], 6)

    # Warnings
    warnings = []
    within_limits = True
    if total_mass > 8.0:
        warnings.append("Approaching payload limit")
    if total_mass > CR10_MAX_PAYLOAD_KG:
        warnings.append("OVER PAYLOAD LIMIT")
        within_limits = False
    if com_dist > 40.0:
        warnings.append("CoM offset approaching limit")
    if com_dist > CR10_MAX_COM_OFFSET_MM:
        warnings.append("CoM offset OVER LIMIT")
        within_limits = False

    # Joint torque margins
    torque_result = calculate_joint_torques(total_mass, com_offset_mm)
    warnings.extend(torque_result.get("warnings", []))

    return {
        "total_mass_kg": round(total_mass, 3),
        "com_offset_mm": com_offset_mm,
        "inertia_tensor": tensor,
        "within_limits": within_limits,
        "warnings": warnings,
        "joint_torque_margins": torque_result["torques"],
    }


def calculate_joint_torques(total_mass: float, com_offset_mm: dict,
                            joint_angles: list[float] = None) -> dict:
    """Calculate static gravitational torque at each joint as % of rated.

    Uses simplified CR10 FK to find end-effector position, then computes
    torque from payload gravity at each joint.
    """
    if joint_angles is None:
        joint_angles = [0.0] * 6

    g = 9.81
    d1 = CR10_DH["d1"]
    a2 = CR10_DH["a2"]
    a3 = CR10_DH["a3"]
    d4 = CR10_DH["d4"]
    d5 = CR10_DH["d5"]
    d6 = CR10_DH["d6"]

    q = joint_angles
    c1, s1 = math.cos(q[0]), math.sin(q[0])
    c2, s2 = math.cos(q[1]), math.sin(q[1])
    c23 = math.cos(q[1] + q[2])
    s23 = math.sin(q[1] + q[2])

    # EE position (simplified FK)
    ee_x = c1 * (a2 * c2 + a3 * c23) - d5 * s1
    ee_y = s1 * (a2 * c2 + a3 * c23) + d5 * c1
    ee_z = d1 + a2 * s2 + a3 * s23 + d4

    # Add CoM offset (mm -> m)
    payload_x = ee_x + com_offset_mm["x"] * 1e-3
    payload_y = ee_y + com_offset_mm["y"] * 1e-3
    payload_z = ee_z + com_offset_mm["z"] * 1e-3

    # Gravity force vector
    fg = total_mass * g  # downward

    # Joint positions along chain
    j_pos = [
        (0, 0, 0),                                          # J1 base
        (0, 0, d1),                                         # J2
        (c1 * a2 * c2, s1 * a2 * c2, d1 + a2 * s2),       # J3
        (c1 * (a2 * c2 + a3 * c23), s1 * (a2 * c2 + a3 * c23), d1 + a2 * s2 + a3 * s23),  # J4
        (ee_x, ee_y, ee_z - d6),                            # J5
        (ee_x, ee_y, ee_z),                                 # J6
    ]

    # Joint axes (simplified: J1=Z, J2-J6 ~ Y-axis in local frame)
    # For torque estimation, use magnitude of cross product
    torques = {}
    warnings = []

    for i in range(6):
        jx, jy, jz = j_pos[i]
        # Vector from joint to payload CoM
        rx = payload_x - jx
        ry = payload_y - jy
        rz = payload_z - jz
        # Torque magnitude = |r x F| where F = (0, 0, -fg)
        # |r x F| = fg * sqrt(rx^2 + ry^2)
        torque_nm = fg * math.sqrt(rx * rx + ry * ry)
        rated = CR10_RATED_TORQUES[f"J{i + 1}"]
        pct = round(torque_nm / rated * 100, 1)
        torques[f"J{i + 1}"] = pct

        if pct > 95:
            warnings.append(f"J{i + 1} torque CRITICAL ({pct}%)")
        elif pct > 80:
            warnings.append(f"J{i + 1} torque high ({pct}%)")

    return {"torques": torques, "warnings": warnings}


# ── Preset management ─────────────────────────────────────

def _load_presets_file() -> dict:
    """Load presets from disk, initializing with defaults if needed."""
    os.makedirs(PRESET_PATH.parent, exist_ok=True)
    if not PRESET_PATH.exists():
        with open(PRESET_PATH, "w") as f:
            json.dump(DEFAULT_PRESETS, f, indent=2)
        return dict(DEFAULT_PRESETS)
    with open(PRESET_PATH) as f:
        return json.load(f)


def _save_presets_file(presets: dict):
    """Write presets dict to disk."""
    os.makedirs(PRESET_PATH.parent, exist_ok=True)
    with open(PRESET_PATH, "w") as f:
        json.dump(presets, f, indent=2)


def save_preset(name: str, camera_id: str, lens_id: str,
                accessory_ids: list[str]) -> bool:
    """Save a named preset configuration."""
    presets = _load_presets_file()
    presets[name] = {
        "camera_id": camera_id,
        "lens_id": lens_id,
        "accessory_ids": accessory_ids,
    }
    _save_presets_file(presets)
    return True


def load_preset(name: str) -> dict | None:
    """Load a preset by name. Returns None if not found."""
    presets = _load_presets_file()
    return presets.get(name)


def list_presets() -> list[dict]:
    """List all saved presets with their configurations."""
    presets = _load_presets_file()
    return [{"name": k, **v} for k, v in presets.items()]


def delete_preset(name: str) -> bool:
    """Delete a preset by name. Returns False if not found."""
    presets = _load_presets_file()
    if name not in presets:
        return False
    del presets[name]
    _save_presets_file(presets)
    return True
