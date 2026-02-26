# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Deployment skill for robot policy rollout."""
import os
import json
import hashlib
import logging
import subprocess
import time

logger = logging.getLogger("skill.deploy")
BASE_DIR = os.path.expanduser("~/agent-stack")


class DeploySkill:
    """Deploys, rolls back, and monitors robot policy deployments."""

    def deploy_to_robot(self, package_dir: str, robot_host: str,
                         deploy_path: str = "/opt/robot/policies",
                         approved: bool = False) -> dict:
        """Deploy policy package to robot.

        REQUIRES approved=True to execute. Without approval, returns
        a dry-run preview of what would happen.
        """
        # Load manifest
        manifest_path = os.path.join(package_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            return {"success": False, "error": "Missing manifest.json in package"}

        with open(manifest_path) as f:
            manifest = json.load(f)

        version = manifest.get("metadata", {}).get("version", "unknown")
        task = manifest.get("metadata", {}).get("task", "unknown")
        target_dir = f"{deploy_path}/{task}/v{version}"

        # Verify package integrity before deployment
        checksum_path = os.path.join(package_dir, "checksums.sha256")
        integrity_ok = True
        if os.path.exists(checksum_path):
            with open(checksum_path) as f:
                for line in f:
                    parts = line.strip().split("  ")
                    if len(parts) == 2:
                        expected, filename = parts
                        filepath = os.path.join(package_dir, filename)
                        if os.path.exists(filepath):
                            actual = hashlib.sha256(
                                open(filepath, "rb").read()
                            ).hexdigest()
                            if actual != expected:
                                integrity_ok = False
                                break

        if not integrity_ok:
            return {"success": False, "error": "Package integrity check failed"}

        files_to_deploy = [f for f in os.listdir(package_dir) if os.path.isfile(
            os.path.join(package_dir, f))]

        deploy_plan = {
            "robot_host": robot_host,
            "target_dir": target_dir,
            "version": version,
            "task": task,
            "files": files_to_deploy,
            "integrity_verified": integrity_ok,
        }

        if not approved:
            logger.info(f"Deploy dry-run: {task} v{version} -> {robot_host}:{target_dir}")
            return {
                "success": False,
                "dry_run": True,
                "plan": deploy_plan,
                "message": "Deployment requires approved=True. Review the plan above.",
            }

        # Execute deployment
        commands = [
            f"ssh {robot_host} 'mkdir -p {target_dir}'",
            f"scp -r {package_dir}/* {robot_host}:{target_dir}/",
            f"ssh {robot_host} 'chmod +x {target_dir}/deploy.sh'",
        ]

        results = []
        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=60,
                )
                results.append({
                    "command": cmd,
                    "returncode": result.returncode,
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                })
                if result.returncode != 0:
                    logger.error(f"Deploy command failed: {cmd}")
                    return {
                        "success": False,
                        "error": f"Command failed: {cmd}",
                        "stderr": result.stderr.strip(),
                        "completed_steps": results,
                    }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": f"Command timed out: {cmd}",
                    "completed_steps": results,
                }

        # Record deployment
        deploy_record = {
            "version": version,
            "task": task,
            "robot_host": robot_host,
            "target_dir": target_dir,
            "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files": files_to_deploy,
            "status": "deployed",
        }

        records_dir = os.path.join(BASE_DIR, "deploy", "records")
        os.makedirs(records_dir, exist_ok=True)
        record_file = os.path.join(records_dir, f"{task}_v{version}.json")
        with open(record_file, "w") as f:
            json.dump(deploy_record, f, indent=2)

        logger.info(f"Deployed {task} v{version} to {robot_host}:{target_dir}")
        return {
            "success": True,
            "plan": deploy_plan,
            "record": deploy_record,
            "record_file": record_file,
        }

    def rollback(self, robot_host: str, task: str,
                  target_version: str = None, approved: bool = False) -> dict:
        """Rollback to a previous policy version.

        REQUIRES approved=True to execute. If target_version is None,
        rolls back to the most recent previous version.
        """
        # Find deployment records
        records_dir = os.path.join(BASE_DIR, "deploy", "records")
        if not os.path.exists(records_dir):
            return {"success": False, "error": "No deployment records found"}

        # Load all records for this task
        records = []
        for fname in sorted(os.listdir(records_dir)):
            if fname.startswith(f"{task}_v") and fname.endswith(".json"):
                with open(os.path.join(records_dir, fname)) as f:
                    records.append(json.load(f))

        if len(records) < 2 and target_version is None:
            return {
                "success": False,
                "error": "No previous version to rollback to",
                "available_versions": [r.get("version") for r in records],
            }

        # Determine target version
        if target_version is None:
            # Get second-to-last deployment
            target_record = records[-2]
            target_version = target_record.get("version")
        else:
            target_record = next(
                (r for r in records if r.get("version") == target_version), None
            )
            if target_record is None:
                return {
                    "success": False,
                    "error": f"Version {target_version} not found in records",
                    "available_versions": [r.get("version") for r in records],
                }

        current_version = records[-1].get("version") if records else "unknown"
        deploy_path = target_record.get("target_dir", f"/opt/robot/policies/{task}/v{target_version}")

        rollback_plan = {
            "current_version": current_version,
            "target_version": target_version,
            "robot_host": robot_host,
            "deploy_path": deploy_path,
        }

        if not approved:
            logger.info(f"Rollback dry-run: {task} {current_version} -> {target_version}")
            return {
                "success": False,
                "dry_run": True,
                "plan": rollback_plan,
                "message": "Rollback requires approved=True. Review the plan above.",
            }

        # Execute rollback: symlink or copy the target version as active
        active_link = f"/opt/robot/policies/{task}/active"
        commands = [
            f"ssh {robot_host} 'rm -f {active_link}'",
            f"ssh {robot_host} 'ln -s {deploy_path} {active_link}'",
            f"ssh {robot_host} 'ls -la {active_link}'",
        ]

        results = []
        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30,
                )
                results.append({
                    "command": cmd,
                    "returncode": result.returncode,
                    "stdout": result.stdout.strip(),
                })
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": f"Rollback command timed out: {cmd}",
                    "completed_steps": results,
                }

        # Record rollback
        rollback_record = {
            "action": "rollback",
            "from_version": current_version,
            "to_version": target_version,
            "robot_host": robot_host,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "completed",
        }

        record_file = os.path.join(
            records_dir, f"{task}_rollback_{int(time.time())}.json"
        )
        with open(record_file, "w") as f:
            json.dump(rollback_record, f, indent=2)

        logger.info(f"Rolled back {task}: {current_version} -> {target_version}")
        return {
            "success": True,
            "plan": rollback_plan,
            "record": rollback_record,
        }

    def check_status(self, robot_host: str, task: str = None) -> dict:
        """Check deployment status on robot."""
        try:
            # Check what's deployed
            if task:
                cmd = f"ssh {robot_host} 'ls -la /opt/robot/policies/{task}/active 2>/dev/null && cat /opt/robot/policies/{task}/active/manifest.json 2>/dev/null'"
            else:
                cmd = f"ssh {robot_host} 'ls /opt/robot/policies/ 2>/dev/null'"

            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=15,
            )

            if result.returncode == 0:
                output = result.stdout.strip()

                # Try to parse manifest
                try:
                    manifest = json.loads(output.split("\n", 1)[-1])
                except (json.JSONDecodeError, IndexError):
                    manifest = None

                status = {
                    "reachable": True,
                    "robot_host": robot_host,
                    "raw_output": output,
                    "manifest": manifest,
                    "version": manifest.get("metadata", {}).get("version") if manifest else None,
                    "task": task,
                }
            else:
                status = {
                    "reachable": True,
                    "robot_host": robot_host,
                    "error": result.stderr.strip() or "No deployment found",
                    "task": task,
                }

        except subprocess.TimeoutExpired:
            status = {
                "reachable": False,
                "robot_host": robot_host,
                "error": "Connection timed out",
            }
        except FileNotFoundError:
            status = {
                "reachable": False,
                "robot_host": robot_host,
                "error": "SSH not available",
            }

        # Also check local records
        records_dir = os.path.join(BASE_DIR, "deploy", "records")
        local_records = []
        if os.path.exists(records_dir):
            prefix = f"{task}_v" if task else ""
            for fname in sorted(os.listdir(records_dir)):
                if fname.startswith(prefix) and fname.endswith(".json"):
                    with open(os.path.join(records_dir, fname)) as f:
                        local_records.append(json.load(f))

        status["local_records"] = local_records
        status["local_record_count"] = len(local_records)

        logger.info(f"Status check: {robot_host}, task={task}")
        return status

    def record_update(self, task: str, version: str, status: str = "deployed",
                       notes: str = "", metrics: dict = None) -> dict:
        """Record a deployment event for audit trail."""
        records_dir = os.path.join(BASE_DIR, "deploy", "records")
        os.makedirs(records_dir, exist_ok=True)

        record = {
            "task": task,
            "version": version,
            "status": status,
            "notes": notes,
            "metrics": metrics or {},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "recorded_by": "agent-stack",
        }

        # Append to deployment log
        log_file = os.path.join(records_dir, f"{task}_deploy_log.jsonl")
        with open(log_file, "a") as f:
            f.write(json.dumps(record) + "\n")

        # Also save individual record
        record_file = os.path.join(records_dir, f"{task}_v{version}_{status}.json")
        with open(record_file, "w") as f:
            json.dump(record, f, indent=2)

        logger.info(f"Recorded: {task} v{version} status={status}")
        return {
            "record": record,
            "log_file": log_file,
            "record_file": record_file,
        }
