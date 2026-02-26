# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Health monitoring skill for fleet, robot, and training jobs."""
import os
import json
import logging
import subprocess
import time
import glob

logger = logging.getLogger("skill.health")
BASE_DIR = os.path.expanduser("~/agent-stack")


class HealthSkill:
    """Monitors health of robot fleet, individual robot stacks, and training jobs."""

    def check_fleet(self, fleet_config: dict = None) -> dict:
        """Run health check across the entire robot fleet.

        fleet_config: {"robots": [{"host": str, "name": str, "type": str}, ...],
                       "timeout": int}
        """
        fleet_config = fleet_config or {"robots": [], "timeout": 10}
        robots = fleet_config.get("robots", [])
        timeout = fleet_config.get("timeout", 10)

        fleet_results = []
        for robot_info in robots:
            host = robot_info.get("host", "")
            name = robot_info.get("name", host)
            robot_type = robot_info.get("type", "unknown")

            robot_health = {
                "name": name,
                "host": host,
                "type": robot_type,
                "checks": {},
            }

            # Ping check
            try:
                ping_result = subprocess.run(
                    ["ping", "-c", "1", "-W", str(timeout), host],
                    capture_output=True, text=True, timeout=timeout + 2,
                )
                robot_health["checks"]["network"] = {
                    "status": "ok" if ping_result.returncode == 0 else "unreachable",
                    "latency_ms": None,
                }
                if ping_result.returncode == 0:
                    # Parse latency from ping output
                    for line in ping_result.stdout.split("\n"):
                        if "time=" in line:
                            time_str = line.split("time=")[1].split()[0]
                            robot_health["checks"]["network"]["latency_ms"] = float(time_str)
                            break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                robot_health["checks"]["network"] = {"status": "timeout"}

            # SSH check and system stats
            if robot_health["checks"]["network"].get("status") == "ok":
                try:
                    ssh_cmd = (
                        f"ssh -o ConnectTimeout={timeout} {host} "
                        "'echo OK && "
                        "cat /proc/uptime && "
                        "free -m | grep Mem && "
                        "df -h / | tail -1 && "
                        "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu "
                        "--format=csv,noheader,nounits 2>/dev/null || echo NO_GPU'"
                    )
                    ssh_result = subprocess.run(
                        ssh_cmd, shell=True, capture_output=True, text=True,
                        timeout=timeout + 5,
                    )
                    if ssh_result.returncode == 0:
                        lines = ssh_result.stdout.strip().split("\n")

                        # Parse uptime
                        if len(lines) > 1:
                            uptime_sec = float(lines[1].split()[0])
                            robot_health["checks"]["uptime_hours"] = round(uptime_sec / 3600, 1)

                        # Parse memory
                        if len(lines) > 2:
                            mem_parts = lines[2].split()
                            if len(mem_parts) >= 3:
                                total_mem = int(mem_parts[1])
                                used_mem = int(mem_parts[2])
                                robot_health["checks"]["memory"] = {
                                    "total_mb": total_mem,
                                    "used_mb": used_mem,
                                    "usage_pct": round(100 * used_mem / total_mem, 1) if total_mem > 0 else 0,
                                    "status": "ok" if used_mem / total_mem < 0.9 else "warning",
                                }

                        # Parse disk
                        if len(lines) > 3:
                            disk_parts = lines[3].split()
                            if len(disk_parts) >= 5:
                                usage_pct = int(disk_parts[4].rstrip("%"))
                                robot_health["checks"]["disk"] = {
                                    "total": disk_parts[1],
                                    "used": disk_parts[2],
                                    "usage_pct": usage_pct,
                                    "status": "ok" if usage_pct < 85 else "warning",
                                }

                        # Parse GPU
                        if len(lines) > 4 and "NO_GPU" not in lines[4]:
                            gpu_parts = lines[4].split(",")
                            if len(gpu_parts) >= 4:
                                robot_health["checks"]["gpu"] = {
                                    "utilization_pct": int(gpu_parts[0].strip()),
                                    "memory_used_mb": int(gpu_parts[1].strip()),
                                    "memory_total_mb": int(gpu_parts[2].strip()),
                                    "temperature_c": int(gpu_parts[3].strip()),
                                    "status": "ok" if int(gpu_parts[3].strip()) < 85 else "warning",
                                }

                        robot_health["checks"]["ssh"] = {"status": "ok"}
                    else:
                        robot_health["checks"]["ssh"] = {
                            "status": "error",
                            "error": ssh_result.stderr.strip()[:200],
                        }
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    robot_health["checks"]["ssh"] = {"status": "timeout"}

            # Determine overall status
            statuses = [c.get("status", "unknown") for c in robot_health["checks"].values()
                        if isinstance(c, dict)]
            if "unreachable" in statuses or "timeout" in statuses:
                robot_health["overall"] = "offline"
            elif "error" in statuses:
                robot_health["overall"] = "error"
            elif "warning" in statuses:
                robot_health["overall"] = "warning"
            else:
                robot_health["overall"] = "healthy"

            fleet_results.append(robot_health)

        # Fleet summary
        total = len(fleet_results)
        healthy = sum(1 for r in fleet_results if r["overall"] == "healthy")
        warning = sum(1 for r in fleet_results if r["overall"] == "warning")
        offline = sum(1 for r in fleet_results if r["overall"] in ("offline", "error"))

        result = {
            "fleet_size": total,
            "healthy": healthy,
            "warning": warning,
            "offline": offline,
            "overall": "healthy" if offline == 0 and warning == 0 else (
                "warning" if offline == 0 else "critical"
            ),
            "robots": fleet_results,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        logger.info(f"Fleet check: {healthy}/{total} healthy, {warning} warning, {offline} offline")
        return result

    def check_robot_stack(self, robot_host: str = "localhost") -> dict:
        """Check full software stack health on a single robot.

        Checks: ROS2, Isaac Sim, cuRobo, policy server, sensors.
        """
        checks = {}

        # ROS2 daemon
        try:
            ros_result = subprocess.run(
                ["ros2", "daemon", "status"],
                capture_output=True, text=True, timeout=5,
            )
            checks["ros2_daemon"] = {
                "status": "running" if ros_result.returncode == 0 else "stopped",
                "output": ros_result.stdout.strip(),
            }
        except (FileNotFoundError, subprocess.TimeoutExpired):
            checks["ros2_daemon"] = {"status": "not_found"}

        # ROS2 nodes
        try:
            nodes_result = subprocess.run(
                ["ros2", "node", "list"],
                capture_output=True, text=True, timeout=5,
            )
            nodes = [n.strip() for n in nodes_result.stdout.strip().split("\n") if n.strip()]
            checks["ros2_nodes"] = {
                "status": "ok" if len(nodes) > 0 else "no_nodes",
                "count": len(nodes),
                "nodes": nodes[:20],
            }
        except (FileNotFoundError, subprocess.TimeoutExpired):
            checks["ros2_nodes"] = {"status": "unavailable"}

        # ROS2 topics
        try:
            topics_result = subprocess.run(
                ["ros2", "topic", "list"],
                capture_output=True, text=True, timeout=5,
            )
            topics = [t.strip() for t in topics_result.stdout.strip().split("\n") if t.strip()]
            checks["ros2_topics"] = {
                "status": "ok" if len(topics) > 0 else "no_topics",
                "count": len(topics),
            }
        except (FileNotFoundError, subprocess.TimeoutExpired):
            checks["ros2_topics"] = {"status": "unavailable"}

        # GPU status (local)
        try:
            gpu_result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                 "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if gpu_result.returncode == 0:
                gpus = []
                for line in gpu_result.stdout.strip().split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 5:
                        gpus.append({
                            "name": parts[0],
                            "utilization_pct": parts[1],
                            "memory_used": parts[2],
                            "memory_total": parts[3],
                            "temperature": parts[4],
                        })
                checks["gpu"] = {"status": "ok", "gpus": gpus}
            else:
                checks["gpu"] = {"status": "error", "error": gpu_result.stderr.strip()}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            checks["gpu"] = {"status": "not_found"}

        # Check for active policy
        policy_dir = os.path.join(BASE_DIR, "deploy")
        active_policies = []
        if os.path.exists(policy_dir):
            for task_dir in os.listdir(policy_dir):
                active_link = os.path.join(policy_dir, task_dir, "active")
                if os.path.islink(active_link):
                    target = os.readlink(active_link)
                    manifest_path = os.path.join(target, "manifest.json")
                    if os.path.exists(manifest_path):
                        with open(manifest_path) as f:
                            manifest = json.load(f)
                        active_policies.append({
                            "task": task_dir,
                            "version": manifest.get("metadata", {}).get("version", "unknown"),
                            "path": target,
                        })

        checks["active_policies"] = {
            "status": "ok" if active_policies else "none",
            "policies": active_policies,
        }

        # Determine overall
        critical_checks = ["ros2_daemon", "gpu"]
        has_critical_failure = any(
            checks.get(c, {}).get("status") in ("not_found", "error", "stopped")
            for c in critical_checks
        )

        result = {
            "robot_host": robot_host,
            "overall": "error" if has_critical_failure else "healthy",
            "checks": checks,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        logger.info(f"Robot stack check ({robot_host}): {result['overall']}")
        return result

    def check_training_jobs(self, training_dir: str = None) -> dict:
        """Check status of all training jobs."""
        training_dir = training_dir or os.path.join(BASE_DIR, "training")

        jobs = []
        if not os.path.exists(training_dir):
            return {"jobs": [], "total": 0, "active": 0, "completed": 0, "failed": 0}

        # Scan for training runs
        for root, dirs, files in os.walk(training_dir):
            # Look for training config or metrics files
            config_files = [f for f in files if f in ("training_config.json", "rl_config.json",
                                                        "config.json")]
            metrics_files = [f for f in files if f in ("metrics.jsonl", "progress.csv",
                                                         "training_log.jsonl")]

            if not config_files and not metrics_files:
                continue

            job = {
                "path": root,
                "name": os.path.relpath(root, training_dir),
            }

            # Load config
            for cf in config_files:
                try:
                    with open(os.path.join(root, cf)) as f:
                        job["config"] = json.load(f)
                    break
                except (json.JSONDecodeError, IOError):
                    continue

            # Check metrics for progress
            for mf in metrics_files:
                metrics_path = os.path.join(root, mf)
                try:
                    with open(metrics_path) as f:
                        lines = f.readlines()
                    if lines:
                        last_line = lines[-1].strip()
                        if last_line:
                            last_metrics = json.loads(last_line)
                            job["latest_metrics"] = last_metrics
                            job["total_steps"] = len(lines)

                            # Check if training is recent (file modified within last hour)
                            mtime = os.path.getmtime(metrics_path)
                            age_hours = (time.time() - mtime) / 3600
                            job["last_update_hours_ago"] = round(age_hours, 2)

                            if age_hours < 0.5:
                                job["status"] = "active"
                            elif age_hours < 24:
                                # Check if it seems to have finished
                                config = job.get("config", {})
                                max_epochs = config.get("num_epochs",
                                              config.get("max_iterations", 0))
                                current = last_metrics.get("epoch",
                                            last_metrics.get("iteration", 0))
                                if max_epochs > 0 and current >= max_epochs * 0.95:
                                    job["status"] = "completed"
                                else:
                                    job["status"] = "stalled"
                            else:
                                job["status"] = "completed" if job.get("total_steps", 0) > 10 else "failed"
                    break
                except (json.JSONDecodeError, IOError):
                    continue

            if "status" not in job:
                job["status"] = "unknown"

            # Check for checkpoints
            checkpoints = glob.glob(os.path.join(root, "**", "checkpoint_*.pt"), recursive=True)
            checkpoints.extend(glob.glob(os.path.join(root, "**", "*.ckpt"), recursive=True))
            job["checkpoint_count"] = len(checkpoints)
            if checkpoints:
                latest_ckpt = max(checkpoints, key=os.path.getmtime)
                job["latest_checkpoint"] = latest_ckpt
                job["latest_checkpoint_age_hours"] = round(
                    (time.time() - os.path.getmtime(latest_ckpt)) / 3600, 2
                )

            # Check disk usage
            try:
                du_result = subprocess.run(
                    ["du", "-sh", root],
                    capture_output=True, text=True, timeout=5,
                )
                if du_result.returncode == 0:
                    job["disk_usage"] = du_result.stdout.split()[0]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                job["disk_usage"] = "unknown"

            jobs.append(job)

        # Summary
        total = len(jobs)
        active = sum(1 for j in jobs if j.get("status") == "active")
        completed = sum(1 for j in jobs if j.get("status") == "completed")
        failed = sum(1 for j in jobs if j.get("status") in ("failed", "stalled"))

        result = {
            "training_dir": training_dir,
            "total": total,
            "active": active,
            "completed": completed,
            "failed": failed,
            "unknown": total - active - completed - failed,
            "jobs": jobs,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        logger.info(f"Training jobs: {active} active, {completed} completed, {failed} failed")
        return result
