# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Metrics watcher event source.

Polls fleet machines every interval seconds, writes metrics to DB,
and emits events when thresholds are breached or machines go offline.
Absorbs the functionality of monitor/metrics_collector.py.
"""

import os
import sys
import asyncio
import logging
import subprocess
import sqlite3
from datetime import datetime

import yaml

sys.path.insert(0, os.path.expanduser("~/agent-stack"))

from orchestrator.bus import EventBus
from orchestrator.events import OrchestratorEvent, EventPriority

logger = logging.getLogger("orchestrator.sources.metrics")

BASE_DIR = os.path.expanduser("~/agent-stack")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DB_PATH = os.path.join(BASE_DIR, "data", "metrics.db")


class MetricsWatcher:
    """Collects fleet metrics and emits events on threshold breaches."""

    def __init__(self, bus: EventBus, interval: int = 60):
        self.bus = bus
        self.interval = interval

        with open(os.path.join(CONFIG_DIR, "fleet.yml")) as f:
            self.fleet = yaml.safe_load(f)["machines"]
        with open(os.path.join(CONFIG_DIR, "alerts.yml")) as f:
            self.thresholds = yaml.safe_load(f)["thresholds"]

    def _ssh_cmd(self, user: str, host: str, cmd: str, timeout: int = 10) -> str:
        if host == "localhost":
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        else:
            r = subprocess.run(
                f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes {user}@{host} '{cmd}'",
                shell=True, capture_output=True, text=True, timeout=timeout,
            )
        return r.stdout.strip() if r.returncode == 0 else ""

    def _safe_float(self, v: str) -> float | None:
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    def _collect_machine(self, name: str, config: dict) -> dict:
        host = config["host"]
        user = config["user"]
        metrics = {"machine": name, "timestamp": datetime.now().isoformat(), "status": "online"}

        try:
            gpu_out = self._ssh_cmd(user, host,
                "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits")
            if gpu_out:
                parts = [x.strip() for x in gpu_out.split(",")]
                if len(parts) >= 4:
                    gpu_val = self._safe_float(parts[0])
                    vram_used = self._safe_float(parts[1])
                    vram_total = self._safe_float(parts[2])
                    temp_val = self._safe_float(parts[3])
                    if gpu_val is not None:
                        metrics["gpu_util"] = gpu_val
                    if vram_used is not None:
                        metrics["gpu_vram_used"] = vram_used / 1024
                    if vram_total is not None:
                        metrics["gpu_vram_total"] = vram_total / 1024
                    if temp_val is not None:
                        metrics["temp_c"] = temp_val
                    # Unified memory detection
                    if vram_used is None and vram_total is None:
                        metrics["unified_memory"] = True

            ram_out = self._ssh_cmd(user, host, "free -b | grep Mem")
            if ram_out:
                parts = ram_out.split()
                if len(parts) >= 3:
                    metrics["ram_total"] = float(parts[1]) / (1024**3)
                    metrics["ram_used"] = float(parts[2]) / (1024**3)
                    if metrics.get("unified_memory"):
                        metrics["gpu_vram_total"] = metrics["ram_total"]
                        metrics["gpu_vram_used"] = metrics["ram_used"]

            disk_out = self._ssh_cmd(user, host, "df -B1 / | tail -1")
            if disk_out:
                parts = disk_out.split()
                if len(parts) >= 4:
                    metrics["disk_total"] = float(parts[1]) / (1024**3)
                    metrics["disk_used"] = float(parts[2]) / (1024**3)

            # Ollama status
            ollama_out = self._ssh_cmd(user, host, "systemctl is-active ollama 2>/dev/null || echo inactive")
            metrics["ollama_status"] = ollama_out

        except subprocess.TimeoutExpired:
            metrics["status"] = "timeout"
        except Exception as e:
            metrics["status"] = "error"
            metrics["error"] = str(e)

        return metrics

    def _write_metrics(self, all_metrics: list[dict]):
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

    async def _evaluate_and_emit(self, metrics_list: list[dict]):
        """Check thresholds and emit events for breaches."""
        for m in metrics_list:
            machine = m["machine"]

            # Machine offline
            if m.get("status") not in ("online",):
                await self.bus.put(OrchestratorEvent(
                    priority=EventPriority.HIGH,
                    source="metrics",
                    event_type="machine_offline",
                    payload={
                        "machine": machine,
                        "status": m.get("status"),
                        "task": f"Machine {machine} is {m.get('status', 'offline')}. Investigate connectivity.",
                    },
                ))
                continue

            # GPU temperature
            temp = m.get("temp_c")
            if temp and temp > self.thresholds["gpu_temp_c"]:
                await self.bus.put(OrchestratorEvent(
                    priority=EventPriority.HIGH,
                    source="metrics",
                    event_type="threshold_breach",
                    payload={
                        "machine": machine,
                        "metric": "gpu_temp",
                        "value": temp,
                        "threshold": self.thresholds["gpu_temp_c"],
                        "task": f"GPU temperature on {machine} is {temp}°C (threshold: {self.thresholds['gpu_temp_c']}°C). Check GPU load and cooling.",
                    },
                ))

            # Disk usage
            disk_used = m.get("disk_used", 0)
            disk_total = m.get("disk_total", 1)
            if disk_total > 0:
                disk_pct = (disk_used / disk_total) * 100
                if disk_pct > self.thresholds["disk_pct"]:
                    priority = EventPriority.CRITICAL if disk_pct > 95 else EventPriority.HIGH
                    await self.bus.put(OrchestratorEvent(
                        priority=priority,
                        source="metrics",
                        event_type="threshold_breach",
                        payload={
                            "machine": machine,
                            "metric": "disk",
                            "value": disk_pct,
                            "threshold": self.thresholds["disk_pct"],
                            "task": f"Disk usage on {machine} is {disk_pct:.0f}% ({disk_used:.0f}/{disk_total:.0f}GB). Clean up old files, logs, and Docker images.",
                        },
                    ))

            # RAM usage
            ram_used = m.get("ram_used", 0)
            ram_total = m.get("ram_total", 1)
            if ram_total > 0:
                ram_pct = (ram_used / ram_total) * 100
                if ram_pct > self.thresholds["ram_pct"]:
                    await self.bus.put(OrchestratorEvent(
                        priority=EventPriority.HIGH,
                        source="metrics",
                        event_type="threshold_breach",
                        payload={
                            "machine": machine,
                            "metric": "ram",
                            "value": ram_pct,
                            "threshold": self.thresholds["ram_pct"],
                            "task": f"RAM usage on {machine} is {ram_pct:.0f}%. Identify memory-heavy processes.",
                        },
                    ))

            # Ollama down
            if m.get("ollama_status") not in ("active", "inactive"):
                await self.bus.put(OrchestratorEvent(
                    priority=EventPriority.HIGH,
                    source="metrics",
                    event_type="ollama_down",
                    payload={
                        "machine": machine,
                        "status": m.get("ollama_status"),
                        "task": f"Ollama service on {machine} is '{m.get('ollama_status')}'. Restart the service.",
                    },
                ))

    async def run(self):
        """Main collection loop — runs forever."""
        logger.info(f"MetricsWatcher started (interval={self.interval}s, {len(self.fleet)} machines)")
        while True:
            try:
                metrics_list = []
                for name, config in self.fleet.items():
                    m = await asyncio.get_event_loop().run_in_executor(
                        None, self._collect_machine, name, config
                    )
                    metrics_list.append(m)

                # Write to DB (sync, fast)
                await asyncio.get_event_loop().run_in_executor(
                    None, self._write_metrics, metrics_list
                )

                # Evaluate thresholds and emit events
                await self._evaluate_and_emit(metrics_list)

                online = sum(1 for m in metrics_list if m.get("status") == "online")
                logger.info(f"Metrics collected: {online}/{len(metrics_list)} machines online")

            except Exception as e:
                logger.error(f"MetricsWatcher error: {e}")

            await asyncio.sleep(self.interval)
