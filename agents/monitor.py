#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Fleet monitoring agent - runs as systemd service."""

import os
import sys
import time
import sqlite3
import subprocess
import yaml
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
from agents.base_agent import BaseAgent, BASE_DIR, CONFIG_DIR, DATA_DIR, DB_PATH

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


SAFE_AUTO_ACTIONS = {"restart_ollama", "clean_tmp"}


class MonitorAgent(BaseAgent):
    task_type = "monitoring"
    CHECK_INTERVAL = 60  # seconds

    def __init__(self, daemon_mode=False):
        super().__init__(self.task_type)
        self.daemon_mode = daemon_mode
        with open(os.path.join(CONFIG_DIR, "alerts.yml")) as f:
            self.thresholds = yaml.safe_load(f)["thresholds"]
        # Ensure fleet_health table
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

    def check_machine(self, machine_name: str) -> dict:
        """SSH into machine and collect all metrics."""
        machine = self.fleet_config.get(machine_name)
        if not machine:
            return {"status": "unknown", "error": f"Machine {machine_name} not in fleet config"}

        host = machine["host"]
        user = machine["user"]
        metrics = {"machine": machine_name, "timestamp": datetime.now().isoformat(), "status": "online"}

        def _ssh(cmd):
            if host == "localhost":
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=8)
            else:
                r = subprocess.run(
                    f"ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no {user}@{host} '{cmd}'",
                    shell=True, capture_output=True, text=True, timeout=8,
                )
            return r.stdout.strip() if r.returncode == 0 else ""

        try:
            # GPU metrics (handles [N/A] for unified memory machines like DGX Spark)
            gpu_out = _ssh("nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits")
            if gpu_out:
                parts = [x.strip().strip("[]") for x in gpu_out.split(",")]
                if len(parts) >= 4:
                    if parts[0].upper() != "N/A":
                        metrics["gpu_util"] = float(parts[0])
                    if parts[1].upper() != "N/A" and parts[2].upper() != "N/A":
                        metrics["gpu_vram_used"] = float(parts[1]) / 1024  # MB to GB
                        metrics["gpu_vram_total"] = float(parts[2]) / 1024
                    else:
                        metrics["unified_memory"] = True
                    if parts[3].upper() != "N/A":
                        metrics["temp_c"] = float(parts[3])

            # RAM metrics
            ram_out = _ssh("free -b | grep Mem")
            if ram_out:
                parts = ram_out.split()
                if len(parts) >= 3:
                    metrics["ram_total"] = float(parts[1]) / (1024**3)  # bytes to GB
                    metrics["ram_used"] = float(parts[2]) / (1024**3)
                    # For unified memory, report RAM as VRAM too
                    if metrics.get("unified_memory"):
                        metrics["gpu_vram_total"] = metrics["ram_total"]
                        metrics["gpu_vram_used"] = metrics["ram_used"]

            # Disk metrics
            disk_out = _ssh("df -B1 / | tail -1")
            if disk_out:
                parts = disk_out.split()
                if len(parts) >= 4:
                    metrics["disk_total"] = float(parts[1]) / (1024**3)
                    metrics["disk_used"] = float(parts[2]) / (1024**3)

            # Docker health
            docker_out = _ssh("docker ps --format '{{.Names}}:{{.Status}}' 2>/dev/null")
            metrics["containers"] = docker_out.split("\n") if docker_out else []

            # Ollama status
            ollama_out = _ssh("systemctl is-active ollama 2>/dev/null || echo inactive")
            metrics["ollama_status"] = ollama_out

        except subprocess.TimeoutExpired:
            metrics["status"] = "timeout"
        except Exception as e:
            metrics["status"] = "error"
            metrics["error"] = str(e)

        return metrics

    def check_all_machines(self) -> dict:
        """Check all machines in fleet config in parallel with 15s total timeout."""
        results = {}
        with ThreadPoolExecutor(max_workers=len(self.fleet_config)) as pool:
            futures = {pool.submit(self.check_machine, name): name for name in self.fleet_config}
            for future in as_completed(futures, timeout=15):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=1)
                    self.logger.info(f"Checked {name}: {results[name].get('status', 'unknown')}")
                except Exception:
                    results[name] = {"machine": name, "status": "timeout", "timestamp": datetime.now().isoformat()}
        # Fill in any machines that didn't complete
        for name in self.fleet_config:
            if name not in results:
                results[name] = {"machine": name, "status": "timeout", "timestamp": datetime.now().isoformat()}
        return results

    def write_metrics(self, metrics_dict: dict):
        """Write fleet metrics to database."""
        conn = sqlite3.connect(DB_PATH)
        for machine_name, metrics in metrics_dict.items():
            conn.execute(
                """INSERT INTO fleet_health (machine, timestamp, gpu_util, gpu_vram_used,
                   gpu_vram_total, ram_used, ram_total, temp_c, disk_used, disk_total, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (machine_name, metrics.get("timestamp", datetime.now().isoformat()),
                 metrics.get("gpu_util"), metrics.get("gpu_vram_used"),
                 metrics.get("gpu_vram_total"), metrics.get("ram_used"),
                 metrics.get("ram_total"), metrics.get("temp_c"),
                 metrics.get("disk_used"), metrics.get("disk_total"),
                 metrics.get("status", "unknown")),
            )
        conn.commit()
        conn.close()

    def evaluate_alerts(self, metrics_dict: dict):
        """Compare metrics against thresholds and trigger alerts."""
        alerts = []
        for machine_name, metrics in metrics_dict.items():
            if metrics.get("status") not in ("online",):
                alerts.append(("CRITICAL", machine_name, f"Machine is {metrics.get('status', 'offline')}"))
                continue

            temp = metrics.get("temp_c")
            if temp and temp > self.thresholds["gpu_temp_c"]:
                alerts.append(("WARNING", machine_name, f"GPU temp {temp}°C > {self.thresholds['gpu_temp_c']}°C"))

            vram_used = metrics.get("gpu_vram_used", 0)
            vram_total = metrics.get("gpu_vram_total", 1)
            if vram_total > 0:
                vram_pct = (vram_used / vram_total) * 100
                if vram_pct > self.thresholds["gpu_vram_pct"]:
                    alerts.append(("WARNING", machine_name, f"VRAM {vram_pct:.0f}% > {self.thresholds['gpu_vram_pct']}%"))

            ram_used = metrics.get("ram_used", 0)
            ram_total = metrics.get("ram_total", 1)
            if ram_total > 0:
                ram_pct = (ram_used / ram_total) * 100
                if ram_pct > self.thresholds["ram_pct"]:
                    alerts.append(("WARNING", machine_name, f"RAM {ram_pct:.0f}% > {self.thresholds['ram_pct']}%"))

            disk_used = metrics.get("disk_used", 0)
            disk_total = metrics.get("disk_total", 1)
            if disk_total > 0:
                disk_pct = (disk_used / disk_total) * 100
                if disk_pct > self.thresholds["disk_pct"]:
                    alerts.append(("CRITICAL", machine_name, f"Disk {disk_pct:.0f}% > {self.thresholds['disk_pct']}%"))
                    # Auto-fix: clean /tmp if disk > 90%
                    if disk_pct > 90:
                        self._auto_clean_tmp(machine_name)

            # Auto-fix: restart crashed ollama
            if metrics.get("ollama_status") not in ("active", "inactive"):
                self._auto_restart_ollama(machine_name)

        # Log alerts
        for severity, machine, message in alerts:
            self.logger.warning(f"[{severity}] {machine}: {message}")
            self._write_alert(severity, machine, message)
            if HAS_RICH:
                color = "red" if severity == "CRITICAL" else "yellow"
                console.print(f"  [{color}][{severity}][/{color}] {machine}: {message}")

        return alerts

    def _write_alert(self, severity: str, machine: str, message: str):
        """Write alert to log file and activity_log table."""
        alert_path = os.path.join(BASE_DIR, "logs", "alerts.log")
        timestamp = datetime.now().isoformat()
        with open(alert_path, "a") as f:
            f.write(f"{timestamp} [{severity}] {machine}: {message}\n")
        self.log_activity("alert", message, machine=machine, level=severity)

    def _auto_clean_tmp(self, machine_name: str):
        """Auto-fix: clean /tmp on a machine. Auto-approved in daemon mode."""
        if self.daemon_mode and "clean_tmp" in SAFE_AUTO_ACTIONS:
            approved = True
            self.logger.info(f"Auto-approved (daemon): clean /tmp on {machine_name}")
        else:
            approved = self.ask_approval(
                action="clean_tmp",
                details=f"Delete /tmp files older than 7 days on {machine_name}",
                machine=machine_name,
            )
        if not approved:
            self.logger.info(f"Auto-fix denied: clean /tmp on {machine_name}")
            self.log_activity("auto_fix_denied", f"Denied /tmp cleanup on {machine_name}", machine=machine_name)
            return

        self.logger.info(f"Auto-fix: cleaning /tmp on {machine_name}")
        machine = self.fleet_config[machine_name]
        host = machine["host"]
        user = machine["user"]
        cmd = "find /tmp -type f -atime +7 -delete 2>/dev/null; echo done"
        if host == "localhost":
            subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
        else:
            subprocess.run(f"ssh {user}@{host} '{cmd}'", shell=True, capture_output=True, timeout=30)
        self.log_activity("auto_fix", f"Cleaned /tmp on {machine_name}", machine=machine_name)

    def _auto_restart_ollama(self, machine_name: str):
        """Auto-fix: restart Ollama service. Auto-approved in daemon mode."""
        if self.daemon_mode and "restart_ollama" in SAFE_AUTO_ACTIONS:
            approved = True
            self.logger.info(f"Auto-approved (daemon): restart Ollama on {machine_name}")
        else:
            approved = self.ask_approval(
                action="restart_ollama",
                details=f"Restart Ollama service on {machine_name}",
                machine=machine_name,
            )
        if not approved:
            self.logger.info(f"Auto-fix denied: restart Ollama on {machine_name}")
            self.log_activity("auto_fix_denied", f"Denied Ollama restart on {machine_name}", machine=machine_name)
            return

        self.logger.info(f"Auto-fix: restarting Ollama on {machine_name}")
        machine = self.fleet_config[machine_name]
        host = machine["host"]
        user = machine["user"]
        cmd = "systemctl restart ollama 2>/dev/null || true"
        if host == "localhost":
            subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
        else:
            subprocess.run(f"ssh {user}@{host} '{cmd}'", shell=True, capture_output=True, timeout=30)
        self.log_activity("auto_fix", f"Restarted Ollama on {machine_name}", machine=machine_name)

    def run_forever(self):
        """Main monitoring loop - runs every CHECK_INTERVAL seconds."""
        self.logger.info("Monitor agent starting continuous monitoring loop")
        if HAS_RICH:
            console.print(Panel("Fleet Monitor Started", style="green"))

        while True:
            try:
                metrics = self.check_all_machines()
                self.write_metrics(metrics)
                alerts = self.evaluate_alerts(metrics)

                if HAS_RICH and not alerts:
                    console.print(f"  [green]✓[/green] All machines healthy at {datetime.now().strftime('%H:%M:%S')}")

            except KeyboardInterrupt:
                self.logger.info("Monitor agent stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Monitor cycle error: {e}")

            time.sleep(self.CHECK_INTERVAL)


if __name__ == "__main__":
    monitor = MonitorAgent(daemon_mode=True)
    monitor.run_forever()
