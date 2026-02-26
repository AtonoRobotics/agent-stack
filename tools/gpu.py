# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""
GPU monitoring for local and remote machines via nvidia-smi.
"""

import subprocess
import json
import yaml
import os
import shlex


FLEET_CONFIG_PATH = os.path.expanduser("~/agent-stack/config/fleet.yml")


def _load_fleet_config() -> dict:
    """Load fleet configuration from fleet.yml."""
    try:
        with open(FLEET_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _get_ssh_target(machine: str) -> str:
    """Get user@host string for a given machine name."""
    config = _load_fleet_config()
    machines = config.get("machines", {})
    if machine not in machines:
        raise ValueError(f"Machine '{machine}' not found in fleet config")
    m = machines[machine]
    return f"{m['user']}@{m['host']}"


def _run(command: str, machine: str = "local", timeout: int = 15) -> subprocess.CompletedProcess:
    """Run a command locally or remotely."""
    if machine != "local":
        ssh_target = _get_ssh_target(machine)
        escaped = shlex.quote(command)
        full_cmd = (
            f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "
            f"{ssh_target} {escaped}"
        )
    else:
        full_cmd = command

    return subprocess.run(
        full_cmd,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def get_usage(machine: str = "local") -> dict:
    """
    Get GPU utilization, VRAM usage, temperature, and power draw.

    Args:
        machine: Machine name from fleet config, or "local".

    Returns:
        Dict with keys: gpu_pct, vram_used_gb, vram_total_gb, vram_pct, temp_c, power_w
    """
    cmd = (
        "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,"
        "temperature.gpu,power.draw --format=csv,noheader,nounits"
    )
    result = _run(cmd, machine=machine)

    if result.returncode != 0:
        raise RuntimeError(f"nvidia-smi failed on {machine}: {result.stderr.strip()}")

    # Parse the first line (first GPU)
    line = result.stdout.strip().split("\n")[0]
    values = [v.strip().strip("[]") for v in line.split(",")]

    def _parse_float(val):
        """Parse a float value, returning None for N/A."""
        if val.upper() == "N/A" or val == "":
            return None
        return float(val)

    gpu_pct = _parse_float(values[0])
    vram_used_mb = _parse_float(values[1])
    vram_total_mb = _parse_float(values[2])
    temp_c = _parse_float(values[3])
    power_w = _parse_float(values[4]) if len(values) > 4 else None

    # For unified memory machines (DGX Spark), VRAM reports N/A
    # Fall back to system RAM via free -m
    unified_memory = vram_used_mb is None and vram_total_mb is None
    if unified_memory:
        ram_cmd = "free -m | grep Mem"
        ram_result = _run(ram_cmd, machine=machine)
        if ram_result.returncode == 0 and ram_result.stdout.strip():
            parts = ram_result.stdout.strip().split()
            if len(parts) >= 3:
                vram_total_mb = float(parts[1])  # already in MB
                vram_used_mb = float(parts[2])

    vram_used_gb = round(vram_used_mb / 1024.0, 2) if vram_used_mb is not None else None
    vram_total_gb = round(vram_total_mb / 1024.0, 2) if vram_total_mb is not None else None
    vram_pct = round((vram_used_mb / vram_total_mb) * 100.0, 1) if vram_used_mb and vram_total_mb and vram_total_mb > 0 else None

    return {
        "gpu_pct": gpu_pct,
        "vram_used_gb": vram_used_gb,
        "vram_total_gb": vram_total_gb,
        "vram_pct": vram_pct,
        "temp_c": temp_c,
        "power_w": power_w,
        "unified_memory": unified_memory,
    }


def get_all_machines() -> dict:
    """
    Get GPU usage for all machines defined in fleet.yml.

    Returns:
        Dict mapping machine_name -> usage dict or {"status": "offline", "error": str}.
    """
    config = _load_fleet_config()
    machines = config.get("machines", {})
    results = {}

    for name in machines:
        try:
            usage = get_usage(machine=name)
            usage["status"] = "online"
            results[name] = usage
        except Exception as exc:
            results[name] = {"status": "offline", "error": str(exc)}

    return results


def get_processes(machine: str = "local") -> list:
    """
    Get list of processes currently using the GPU.

    Args:
        machine: Machine name from fleet config, or "local".

    Returns:
        List of dicts with keys: pid, name, memory_mb.
    """
    cmd = (
        "nvidia-smi --query-compute-apps=pid,name,used_memory "
        "--format=csv,noheader,nounits"
    )
    result = _run(cmd, machine=machine)

    if result.returncode != 0:
        return []

    processes = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        values = [v.strip() for v in line.split(",")]
        if len(values) >= 3:
            processes.append({
                "pid": int(values[0]),
                "name": values[1],
                "memory_mb": float(values[2]),
            })
    return processes
