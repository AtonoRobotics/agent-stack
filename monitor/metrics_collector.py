#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Lightweight metrics collector - runs as systemd service.

Collects fleet health metrics every 60 seconds and writes to SQLite.
Lighter weight than the full MonitorAgent - just data collection.
"""

import os
import sys
import time
import sqlite3
import subprocess
import yaml
from datetime import datetime

BASE_DIR = os.path.expanduser("~/agent-stack")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DB_PATH = os.path.join(BASE_DIR, "data", "metrics.db")

os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS fleet_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        machine TEXT, timestamp TEXT,
        gpu_util REAL, gpu_vram_used REAL, gpu_vram_total REAL,
        ram_used REAL, ram_total REAL, temp_c REAL,
        disk_used REAL, disk_total REAL, status TEXT
    )""")
    conn.commit()
    conn.close()


def load_fleet():
    with open(os.path.join(CONFIG_DIR, "fleet.yml")) as f:
        return yaml.safe_load(f)["machines"]


def ssh_cmd(user, host, cmd, timeout=10):
    if host == "localhost":
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    else:
        r = subprocess.run(
            f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no {user}@{host} '{cmd}'",
            shell=True, capture_output=True, text=True, timeout=timeout,
        )
    return r.stdout.strip() if r.returncode == 0 else ""


def collect_machine(name, config):
    host = config["host"]
    user = config["user"]
    metrics = {"machine": name, "timestamp": datetime.now().isoformat(), "status": "online"}

    try:
        gpu_out = ssh_cmd(user, host, "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits")
        if gpu_out:
            parts = [x.strip() for x in gpu_out.split(",")]
            if len(parts) >= 4:
                metrics["gpu_util"] = float(parts[0])
                metrics["gpu_vram_used"] = float(parts[1]) / 1024
                metrics["gpu_vram_total"] = float(parts[2]) / 1024
                metrics["temp_c"] = float(parts[3])

        ram_out = ssh_cmd(user, host, "free -b | grep Mem")
        if ram_out:
            parts = ram_out.split()
            if len(parts) >= 3:
                metrics["ram_total"] = float(parts[1]) / (1024**3)
                metrics["ram_used"] = float(parts[2]) / (1024**3)

        disk_out = ssh_cmd(user, host, "df -B1 / | tail -1")
        if disk_out:
            parts = disk_out.split()
            if len(parts) >= 4:
                metrics["disk_total"] = float(parts[1]) / (1024**3)
                metrics["disk_used"] = float(parts[2]) / (1024**3)

    except subprocess.TimeoutExpired:
        metrics["status"] = "timeout"
    except Exception as e:
        metrics["status"] = "error"

    return metrics


def write_metrics(all_metrics):
    conn = sqlite3.connect(DB_PATH)
    for m in all_metrics:
        conn.execute(
            """INSERT INTO fleet_health (machine, timestamp, gpu_util, gpu_vram_used,
               gpu_vram_total, ram_used, ram_total, temp_c, disk_used, disk_total, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (m.get("machine"), m.get("timestamp"), m.get("gpu_util"), m.get("gpu_vram_used"),
             m.get("gpu_vram_total"), m.get("ram_used"), m.get("ram_total"), m.get("temp_c"),
             m.get("disk_used"), m.get("disk_total"), m.get("status", "unknown")),
        )
    conn.commit()
    conn.close()


def main():
    init_db()
    fleet = load_fleet()
    print(f"Metrics collector started. Monitoring {len(fleet)} machines every 60s.")

    while True:
        try:
            results = []
            for name, config in fleet.items():
                metrics = collect_machine(name, config)
                results.append(metrics)
                status = metrics.get("status", "unknown")
                gpu = f"{metrics.get('gpu_util', 0):.0f}%" if metrics.get("gpu_util") is not None else "N/A"
                print(f"  {name}: {status} GPU={gpu}")

            write_metrics(results)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Collected metrics for {len(results)} machines")

        except KeyboardInterrupt:
            print("Metrics collector stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")

        time.sleep(60)


if __name__ == "__main__":
    main()
