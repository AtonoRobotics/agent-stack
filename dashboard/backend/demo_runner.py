#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Demo execution engine for Isaac Sim demos.

Manages launching, monitoring, and stopping Dobot CR10 demos
(singularity avoidance, velocity profiles, Cartesian path accuracy)
via Docker containers with GPU access.
"""

import os
import re
import json
import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import WebSocket

RESULTS_DIR = os.path.expanduser("~/dobot_cr10/results")
LAUNCH_SCRIPT = os.path.expanduser("~/dobot_cr10/launch_demo.sh")
DEMO_CWD = os.path.expanduser("~/dobot_cr10")
DB_PATH = os.path.expanduser("~/agent-stack/data/metrics.db")
DOCKER_IMAGE = "isaac-lab-curobo:latest"

DEMO_REGISTRY = {
    "singularity": {
        "name": "Singularity Avoidance",
        "description": "cuRobo avoids wrist singularity where standard kinematics fails",
        "launch_mode": "singularity-headless",
        "result_files": ["singularity_comparison.png"],
        "csv_files": [],
    },
    "velocity": {
        "name": "Velocity Profiles",
        "description": "cuRobo smooth bell curves vs kinematic linear ramps",
        "launch_mode": "velocity-headless",
        "result_files": ["velocity_comparison.png"],
        "csv_files": ["curobo_trajectory.csv", "kinematic_trajectory.csv"],
    },
    "cartesian": {
        "name": "Cartesian Path Accuracy",
        "description": "End-effector path deviation from ideal Cartesian trajectory",
        "launch_mode": "comparison-v2-headless",
        "result_files": ["comparison_cartesian.png"],
        "csv_files": [],
    },
}


class DemoRunner:
    """Manages Isaac Sim demo execution lifecycle."""

    def __init__(self):
        self._running = None  # {demo_id, process, log_lines, db_id, started}
        self._lock = asyncio.Lock()
        self._ws_subscribers: list[WebSocket] = []
        self._last_log: dict[str, list[str]] = {}  # demo_id -> log lines from last run

    async def check_prerequisites(self) -> dict:
        """Check Docker image and GPU availability."""
        result = {"docker_available": False, "gpu_available": False, "vram_free_mb": 0}

        # Check Docker image
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "image", "inspect", DOCKER_IMAGE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
            result["docker_available"] = proc.returncode == 0
        except Exception:
            pass

        # Check GPU VRAM
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi", "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode == 0:
                vram = int(stdout.decode().strip().split("\n")[0])
                result["gpu_available"] = True
                result["vram_free_mb"] = vram
        except Exception:
            pass

        return result

    async def launch(self, demo_id: str, user: str) -> dict:
        """Launch a demo. Returns run metadata or raises on error."""
        if demo_id not in DEMO_REGISTRY:
            raise ValueError(f"Unknown demo: {demo_id}")

        async with self._lock:
            if self._running is not None:
                raise RuntimeError(f"Demo '{self._running['demo_id']}' is already running")

            demo = DEMO_REGISTRY[demo_id]
            mode = demo["launch_mode"]
            now = datetime.now().isoformat()

            # Insert DB row
            db_id = self._db_insert(demo_id, now, mode, user)

            # Spawn subprocess
            env = os.environ.copy()
            env["PYTHONPATH"] = DEMO_CWD
            # Auto-confirm VRAM warning prompts
            env["DEBIAN_FRONTEND"] = "noninteractive"

            process = await asyncio.create_subprocess_exec(
                "bash", LAUNCH_SCRIPT, mode,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
                cwd=DEMO_CWD,
                env=env,
            )

            self._running = {
                "demo_id": demo_id,
                "process": process,
                "log_lines": [],
                "db_id": db_id,
                "started": now,
            }

        # Start background output reader
        asyncio.create_task(self._stream_output(demo_id, process, db_id))

        return {
            "run_id": db_id,
            "demo_id": demo_id,
            "status": "running",
            "started": now,
            "mode": mode,
        }

    async def stop(self, demo_id: str) -> dict:
        """Stop a running demo."""
        async with self._lock:
            if self._running is None or self._running["demo_id"] != demo_id:
                raise RuntimeError(f"Demo '{demo_id}' is not running")

            process = self._running["process"]
            db_id = self._running["db_id"]

        # Terminate gracefully, then force
        try:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        except ProcessLookupError:
            pass

        # Kill any orphaned Docker containers
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "kill",
                *[c for c in await self._find_demo_containers()],
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
        except Exception:
            pass

        self._db_update(db_id, "stopped", process.returncode)

        async with self._lock:
            if self._running and self._running["db_id"] == db_id:
                self._last_log[demo_id] = self._running["log_lines"]
                self._running = None

        await self._broadcast({"type": "demo_status", "demo_id": demo_id, "status": "stopped"})
        return {"status": "stopped", "demo_id": demo_id}

    def get_status(self, demo_id: str = None) -> dict:
        """Get current status of running or last demo."""
        if self._running is not None:
            r = self._running
            if demo_id is None or r["demo_id"] == demo_id:
                return {
                    "demo_id": r["demo_id"],
                    "status": "running",
                    "started": r["started"],
                    "log_count": len(r["log_lines"]),
                }
        return {"status": "idle"}

    def get_log(self, demo_id: str, offset: int = 0) -> list[str]:
        """Get log lines for a demo (running or last run)."""
        if self._running and self._running["demo_id"] == demo_id:
            return self._running["log_lines"][offset:]
        return self._last_log.get(demo_id, [])[offset:]

    def get_results(self, demo_id: str) -> dict:
        """Get available result files and last run metrics."""
        if demo_id not in DEMO_REGISTRY:
            return {"error": "Unknown demo"}

        demo = DEMO_REGISTRY[demo_id]
        files = []
        for f in demo["result_files"] + demo["csv_files"]:
            path = os.path.join(RESULTS_DIR, f)
            if os.path.exists(path):
                files.append({
                    "filename": f,
                    "size": os.path.getsize(path),
                    "modified": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
                    "type": "image" if f.endswith(".png") else "csv",
                })

        # Get last run from DB
        last_run = self._db_get_last_run(demo_id)

        return {
            "demo_id": demo_id,
            "files": files,
            "has_results": len(files) > 0,
            "last_run": last_run,
        }

    async def subscribe(self, ws: WebSocket):
        """Add a WebSocket subscriber for demo events."""
        self._ws_subscribers.append(ws)

    async def unsubscribe(self, ws: WebSocket):
        """Remove a WebSocket subscriber."""
        if ws in self._ws_subscribers:
            self._ws_subscribers.remove(ws)

    # ── Internal methods ──────────────────────────────────

    async def _stream_output(self, demo_id: str, process, db_id: int):
        """Read stdout line-by-line, broadcast, and handle completion."""
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if self._running and self._running["db_id"] == db_id:
                    self._running["log_lines"].append(text)
                await self._broadcast({
                    "type": "demo_log",
                    "demo_id": demo_id,
                    "line": text,
                })
        except Exception:
            pass

        # Process finished
        exit_code = await process.wait()
        status = "completed" if exit_code == 0 else "failed"

        # Parse metrics from log output
        log_lines = []
        if self._running and self._running["db_id"] == db_id:
            log_lines = self._running["log_lines"]

        metrics = self._parse_metrics(demo_id, log_lines)
        self._db_update(db_id, status, exit_code, metrics, log_lines)

        async with self._lock:
            if self._running and self._running["db_id"] == db_id:
                self._last_log[demo_id] = self._running["log_lines"]
                self._running = None

        await self._broadcast({
            "type": "demo_status",
            "demo_id": demo_id,
            "status": status,
            "exit_code": exit_code,
            "metrics": metrics,
        })

    async def _broadcast(self, message: dict):
        """Send message to all WebSocket subscribers."""
        dead = []
        for ws in self._ws_subscribers:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_subscribers.remove(ws)

    async def _find_demo_containers(self) -> list[str]:
        """Find running Docker containers from the demo image."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "ps", "-q", "--filter", f"ancestor={DOCKER_IMAGE}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode == 0:
                return [c for c in stdout.decode().strip().split("\n") if c]
        except Exception:
            pass
        return []

    def _parse_metrics(self, demo_id: str, lines: list[str]) -> dict:
        """Extract metrics from demo terminal output."""
        text = "\n".join(lines)
        metrics = {}

        if demo_id == "singularity":
            m = re.search(r"Minimum manipulability:\s+([\d.]+)", text)
            if m:
                metrics["kinematic_min_manip"] = float(m.group(1))
            # Find cuRobo min manip (second occurrence)
            matches = re.findall(r"Minimum manipulability:\s+([\d.]+)", text)
            if len(matches) >= 2:
                metrics["kinematic_min_manip"] = float(matches[0])
                metrics["curobo_min_manip"] = float(matches[1])
            m = re.search(r"Frames in singularity:\s+(\d+)", text)
            if m:
                metrics["singularity_frames"] = int(m.group(1))
            metrics["kinematic_failed"] = "YES" in text and "FAILED" in text

        elif demo_id == "velocity":
            m = re.search(r"Smoothness.*?([\d.]+)\s+([\d.]+)", text)
            if m:
                metrics["curobo_jerk_score"] = float(m.group(1))
                metrics["kinematic_jerk_score"] = float(m.group(2))
            m = re.search(r"Joint path length.*?([\d.]+)\s+([\d.]+)", text)
            if m:
                metrics["curobo_path_length"] = float(m.group(1))
                metrics["kinematic_path_length"] = float(m.group(2))

        elif demo_id == "cartesian":
            m = re.search(r"Max path error.*?([\d.]+)\s+([\d.]+)", text)
            if m:
                metrics["curobo_max_error"] = float(m.group(1))
                metrics["kinematic_max_error"] = float(m.group(2))
            m = re.search(r"Avg path error.*?([\d.]+)\s+([\d.]+)", text)
            if m:
                metrics["curobo_avg_error"] = float(m.group(1))
                metrics["kinematic_avg_error"] = float(m.group(2))

        return metrics

    # ── Database helpers (sync, minimal) ──────────────────

    def _db_insert(self, demo_id: str, started: str, mode: str, user: str) -> int:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute(
            "INSERT INTO demo_runs (demo_id, started, status, mode, launched_by) VALUES (?, ?, 'running', ?, ?)",
            (demo_id, started, mode, user),
        )
        conn.commit()
        row_id = cursor.lastrowid
        conn.close()
        return row_id

    def _db_update(self, db_id: int, status: str, exit_code: int,
                   metrics: dict = None, log_lines: list[str] = None):
        now = datetime.now().isoformat()
        log_tail = "\n".join((log_lines or [])[-200:])
        metrics_json = json.dumps(metrics) if metrics else None
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE demo_runs SET completed=?, status=?, exit_code=?, metrics_json=?, log_tail=? WHERE id=?",
            (now, status, exit_code, metrics_json, log_tail, db_id),
        )
        conn.commit()
        conn.close()

    def _db_get_last_run(self, demo_id: str) -> dict | None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM demo_runs WHERE demo_id=? ORDER BY id DESC LIMIT 1",
            (demo_id,),
        ).fetchone()
        conn.close()
        if row:
            d = dict(row)
            if d.get("metrics_json"):
                try:
                    d["metrics"] = json.loads(d["metrics_json"])
                except Exception:
                    d["metrics"] = {}
            else:
                d["metrics"] = {}
            return d
        return None
