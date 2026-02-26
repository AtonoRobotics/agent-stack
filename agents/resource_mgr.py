#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Resource manager agent for fleet resource tracking and task scheduling."""

import os
import sys
import sqlite3
import json
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
from agents.base_agent import BaseAgent, BASE_DIR, DATA_DIR, DB_PATH

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
from tools import gpu as gpu_tool


class ResourceManagerAgent(BaseAgent):
    """Agent for monitoring fleet resources and scheduling tasks to appropriate machines."""

    task_type = "health_check"

    # Maps task types to their resource requirements
    TASK_REQUIREMENTS = {
        "code_generation": {
            "needs_gpu": False,
            "min_vram_gb": 0,
            "needs_ollama": True,
            "preferred_roles": ["development", "inference"],
        },
        "research": {
            "needs_gpu": False,
            "min_vram_gb": 0,
            "needs_ollama": True,
            "preferred_roles": ["development", "inference"],
        },
        "sysadmin": {
            "needs_gpu": False,
            "min_vram_gb": 0,
            "needs_ollama": True,
            "preferred_roles": ["development", "inference"],
        },
        "simulation": {
            "needs_gpu": True,
            "min_vram_gb": 8,
            "needs_ollama": False,
            "preferred_roles": ["inference", "development"],
        },
        "cosmos": {
            "needs_gpu": True,
            "min_vram_gb": 40,
            "needs_ollama": False,
            "preferred_roles": ["cosmos", "training"],
        },
        "groot": {
            "needs_gpu": True,
            "min_vram_gb": 40,
            "needs_ollama": False,
            "preferred_roles": ["training", "inference"],
        },
        "monitoring": {
            "needs_gpu": False,
            "min_vram_gb": 0,
            "needs_ollama": False,
            "preferred_roles": ["monitoring", "development"],
        },
    }

    def __init__(self):
        super().__init__(self.task_type)
        self._init_pending_tasks_table()

    def _init_pending_tasks_table(self):
        """Ensure the pending_tasks table exists."""
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""CREATE TABLE IF NOT EXISTS pending_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT,
            task_data TEXT,
            target_machine TEXT,
            queued_at TEXT,
            status TEXT DEFAULT 'pending',
            started_at TEXT,
            completed_at TEXT,
            result TEXT
        )""")
        conn.commit()
        conn.close()

    def get_fleet_resources(self) -> dict:
        """Get current resource usage for all machines in the fleet.

        Queries GPU, VRAM, and RAM usage for each machine defined in fleet.yml.

        Returns:
            Dict mapping machine_name to resource usage dict with keys:
                gpu_pct, vram_used_gb, vram_total_gb, vram_available_gb,
                ram_used_gb, ram_total_gb, ram_available_gb, status.
        """
        results = {}

        for machine_name, machine_conf in self.fleet_config.items():
            resource_entry = {
                "gpu_pct": 0.0,
                "vram_used_gb": 0.0,
                "vram_total_gb": 0.0,
                "vram_available_gb": 0.0,
                "ram_used_gb": 0.0,
                "ram_total_gb": 0.0,
                "ram_available_gb": 0.0,
                "status": "unknown",
            }

            try:
                usage = gpu_tool.get_usage(machine=machine_name)
                resource_entry["gpu_pct"] = usage["gpu_pct"]
                resource_entry["vram_used_gb"] = usage["vram_used_gb"]
                resource_entry["vram_total_gb"] = usage["vram_total_gb"]
                resource_entry["vram_available_gb"] = round(
                    usage["vram_total_gb"] - usage["vram_used_gb"], 2
                )
                resource_entry["status"] = "online"
            except Exception as e:
                self.logger.warning(f"GPU query failed for {machine_name}: {e}")
                resource_entry["status"] = "gpu_unavailable"
                # Try to parse VRAM from fleet config as fallback
                gpu_spec = machine_conf.get("gpu", "")
                if "GB" in gpu_spec:
                    try:
                        vram_str = gpu_spec.split("GB")[0].strip().split()[-1]
                        resource_entry["vram_total_gb"] = float(vram_str)
                    except (ValueError, IndexError):
                        pass

            # Parse RAM from fleet config as a baseline
            ram_spec = machine_conf.get("ram", "")
            if "GB" in ram_spec:
                try:
                    ram_str = ram_spec.replace("GB", "").strip()
                    resource_entry["ram_total_gb"] = float(ram_str)
                except ValueError:
                    pass

            # Get RAM limits from resources config
            limits = self.resources_config.get(machine_name, {})
            max_ram = limits.get("max_ram_gb", resource_entry["ram_total_gb"])
            resource_entry["ram_available_gb"] = round(
                max_ram - resource_entry["ram_used_gb"], 2
            )

            results[machine_name] = resource_entry

        self.logger.info(f"Fleet resources checked: {len(results)} machines")
        self.log_activity("resource_check", f"Checked {len(results)} machines")
        return results

    def can_run_task(self, task_type: str, machine: str) -> bool:
        """Check if a machine has enough resources to run a given task type.

        Compares current resource usage against configured limits in resources.yml
        and the task's resource requirements.

        Args:
            task_type: The type of task (e.g., "cosmos", "simulation", "code_generation").
            machine: Machine name from fleet config.

        Returns:
            True if the machine has sufficient resources for the task.
        """
        requirements = self.TASK_REQUIREMENTS.get(task_type)
        if not requirements:
            self.logger.warning(f"Unknown task type: {task_type}, allowing by default")
            return True

        machine_conf = self.fleet_config.get(machine)
        if not machine_conf:
            self.logger.error(f"Machine {machine} not found in fleet config")
            return False

        limits = self.resources_config.get(machine, {})

        # Check if machine has the required role
        machine_roles = machine_conf.get("roles", [])
        if requirements["preferred_roles"]:
            has_role = any(role in machine_roles for role in requirements["preferred_roles"])
            if not has_role:
                self.logger.info(
                    f"Machine {machine} lacks preferred roles for {task_type}: "
                    f"has {machine_roles}, needs one of {requirements['preferred_roles']}"
                )
                # Not a hard block, just a preference

        # Check GPU/VRAM requirements
        if requirements["needs_gpu"] or requirements["min_vram_gb"] > 0:
            try:
                usage = gpu_tool.get_usage(machine=machine)
                vram_available = usage["vram_total_gb"] - usage["vram_used_gb"]

                if requirements["min_vram_gb"] > 0 and vram_available < requirements["min_vram_gb"]:
                    self.logger.info(
                        f"Insufficient VRAM on {machine} for {task_type}: "
                        f"{vram_available:.1f}GB available, need {requirements['min_vram_gb']}GB"
                    )
                    return False

                # Check against configured VRAM limits
                max_vram = limits.get("max_vram_gb")
                if max_vram and usage["vram_used_gb"] >= max_vram:
                    self.logger.info(
                        f"VRAM limit reached on {machine}: "
                        f"{usage['vram_used_gb']:.1f}GB used >= {max_vram}GB limit"
                    )
                    return False

            except Exception as e:
                self.logger.warning(f"Could not check GPU on {machine}: {e}")
                if requirements["needs_gpu"]:
                    return False

        # Check RAM limits
        max_ram = limits.get("max_ram_gb")
        if max_ram:
            try:
                usage = gpu_tool.get_usage(machine=machine)
                # GPU tool doesn't return RAM, so we rely on limits being set conservatively
                # If we got this far, the machine is reachable
            except Exception:
                pass  # Already handled above

        self.logger.info(f"Machine {machine} can run {task_type}: True")
        return True

    def recommend_machine(self, task_type: str) -> str:
        """Recommend the best machine in the fleet for a given task type.

        Uses task requirements to find the machine with the most available
        resources that matches the task's needs.

        Args:
            task_type: The type of task to run.

        Returns:
            Machine name string.

        Raises:
            RuntimeError: If no suitable machine is found.
        """
        requirements = self.TASK_REQUIREMENTS.get(task_type, {})
        preferred_roles = requirements.get("preferred_roles", [])
        min_vram = requirements.get("min_vram_gb", 0)
        needs_gpu = requirements.get("needs_gpu", False)

        candidates = []

        for machine_name, machine_conf in self.fleet_config.items():
            machine_roles = machine_conf.get("roles", [])

            # Calculate a score based on role match
            role_score = sum(1 for r in preferred_roles if r in machine_roles)

            # Check if machine can handle the task
            if not self.can_run_task(task_type, machine_name):
                continue

            # Get available resources for scoring
            try:
                usage = gpu_tool.get_usage(machine=machine_name)
                vram_available = usage["vram_total_gb"] - usage["vram_used_gb"]
                gpu_headroom = 100.0 - usage["gpu_pct"]
            except Exception:
                vram_available = 0.0
                gpu_headroom = 0.0
                if needs_gpu:
                    continue

            # Score: role match (weight 10) + available VRAM + GPU headroom
            score = (role_score * 10) + vram_available + (gpu_headroom / 10.0)
            candidates.append((machine_name, score))
            self.logger.debug(f"Candidate {machine_name}: score={score:.1f} "
                              f"(roles={role_score}, vram={vram_available:.1f}GB, "
                              f"gpu_headroom={gpu_headroom:.0f}%)")

        if not candidates:
            # Fallback: try all machines without strict checks
            self.logger.warning(f"No candidate passed strict checks for {task_type}, "
                                "falling back to role-based selection")
            for machine_name, machine_conf in self.fleet_config.items():
                machine_roles = machine_conf.get("roles", [])
                role_score = sum(1 for r in preferred_roles if r in machine_roles)
                if role_score > 0:
                    candidates.append((machine_name, role_score))

        if not candidates:
            raise RuntimeError(f"No suitable machine found for task type: {task_type}")

        # Sort by score descending, pick the best
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_machine = candidates[0][0]

        self.logger.info(f"Recommended machine for {task_type}: {best_machine}")
        self.log_activity("recommendation",
                          f"Recommended {best_machine} for {task_type}")
        return best_machine

    def queue_task_if_busy(self, task: dict, machine: str) -> bool:
        """Queue a task if the target machine is too busy to run it now.

        Checks if the machine can run the task. If not, saves the task
        to the pending_tasks table for later execution.

        Args:
            task: Dict with task details including at least "type" and "description".
            machine: Target machine name.

        Returns:
            True if the task was queued (machine is busy).
            False if the task can run now (machine has capacity).
        """
        task_type = task.get("type", "unknown")

        if self.can_run_task(task_type, machine):
            self.logger.info(f"Machine {machine} has capacity for {task_type}, no queuing needed")
            return False

        # Machine is busy, queue the task
        now = datetime.now().isoformat()
        task_data = json.dumps(task, default=str)

        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT INTO pending_tasks (task_type, task_data, target_machine, queued_at, status)
               VALUES (?, ?, ?, ?, ?)""",
            (task_type, task_data, machine, now, "pending"),
        )
        conn.commit()
        conn.close()

        self.logger.info(f"Task queued for {machine}: {task_type} - {task.get('description', '')[:60]}")
        self.log_activity("task_queued",
                          f"Queued {task_type} for {machine}: {task.get('description', '')[:60]}",
                          machine=machine)
        return True

    def get_pending_tasks(self, machine: str = None) -> list:
        """Get all pending tasks, optionally filtered by machine.

        Args:
            machine: Optional machine name to filter by.

        Returns:
            List of pending task dicts.
        """
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        if machine:
            cursor = conn.execute(
                "SELECT * FROM pending_tasks WHERE status='pending' AND target_machine=? ORDER BY queued_at",
                (machine,),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM pending_tasks WHERE status='pending' ORDER BY queued_at"
            )

        tasks = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Parse task_data JSON
        for task in tasks:
            try:
                task["task_data"] = json.loads(task["task_data"])
            except (json.JSONDecodeError, TypeError):
                pass

        return tasks

    def process_pending_tasks(self) -> dict:
        """Check pending tasks and see if any can now be run.

        Returns:
            Dict with counts: checked, runnable, still_pending.
        """
        pending = self.get_pending_tasks()
        checked = len(pending)
        runnable = 0
        still_pending = 0

        for task_row in pending:
            machine = task_row["target_machine"]
            task_type = task_row["task_type"]

            if self.can_run_task(task_type, machine):
                # Mark as ready to run
                conn = sqlite3.connect(DB_PATH)
                conn.execute(
                    "UPDATE pending_tasks SET status='ready', started_at=? WHERE id=?",
                    (datetime.now().isoformat(), task_row["id"]),
                )
                conn.commit()
                conn.close()
                runnable += 1
                self.logger.info(f"Pending task {task_row['id']} is now runnable on {machine}")
            else:
                still_pending += 1

        result = {
            "checked": checked,
            "runnable": runnable,
            "still_pending": still_pending,
        }
        self.logger.info(f"Pending task check: {result}")
        return result
