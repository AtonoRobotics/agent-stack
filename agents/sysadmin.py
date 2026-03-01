#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Sysadmin agent for fleet management, Docker, services, and git operations."""

import os
import sys
import subprocess
import shlex
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
from agents.base_agent import BaseAgent


class SysadminAgent(BaseAgent):
    """Agent for system administration across the fleet."""

    task_type = "sysadmin"

    DESTRUCTIVE_PATTERNS = [
        "rm -rf",
        "apt remove",
        "apt purge",
        "systemctl stop",
        "systemctl disable",
        "docker rm",
        "docker rmi",
        "docker stop",
        "pkill",
        "kill -9",
        "> /dev/",
        "mkfs",
        "dd if=",
        "chmod 000",
        "chown root",
    ]

    def __init__(self):
        super().__init__(self.task_type)
        self._SKILL_REGISTRY = {
            "execute_on_machine": self.execute_on_machine,
            "deploy_to_fleet": self.deploy_to_fleet,
            "manage_docker": self.manage_docker,
            "manage_service": self.manage_service,
            "git_operation": self.git_operation,
        }

    def _is_destructive(self, command: str) -> bool:
        """Check if a command matches any known destructive pattern.

        Args:
            command: The shell command string.

        Returns:
            True if the command contains a destructive pattern.
        """
        return any(pattern in command for pattern in self.DESTRUCTIVE_PATTERNS)

    def _run_on(self, command: str, machine_name: str, timeout: int = 120) -> dict:
        """Execute a command on a machine (local or remote via SSH).

        Args:
            command: Shell command to run.
            machine_name: Machine name from fleet config, or "local".
            timeout: Timeout in seconds.

        Returns:
            Dict with keys: stdout, stderr, returncode.
        """
        if machine_name == "local":
            host = "localhost"
            full_cmd = command
        else:
            machine = self.fleet_config.get(machine_name)
            if not machine:
                return {"stdout": "", "stderr": f"Machine {machine_name} not in fleet config", "returncode": -1}
            host = machine["host"]
            user = machine["user"]
            if host == "localhost":
                full_cmd = command
            else:
                escaped = shlex.quote(command)
                full_cmd = f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no {user}@{host} {escaped}"

        try:
            result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"Command timed out after {timeout}s", "returncode": -1}

    def execute_on_machine(self, command: str, machine: str) -> str:
        """Execute a command on a specific machine.

        If the command matches a destructive pattern, asks for user approval first.
        For local machines, runs via subprocess. For remote, runs via SSH.

        Args:
            command: Shell command to run.
            machine: Machine name from fleet config (e.g., "workstation", "dgx-spark").

        Returns:
            Command stdout as a string.

        Raises:
            PermissionError: If destructive command is denied by user.
            ValueError: If machine is not found in fleet config.
        """
        machine_conf = self.fleet_config.get(machine)
        if not machine_conf:
            raise ValueError(f"Machine '{machine}' not found in fleet config")

        if self._is_destructive(command):
            approved = self.ask_approval(
                action=f"Execute destructive command on {machine}",
                details=command[:80],
                machine=machine,
            )
            if not approved:
                self.logger.warning(f"Destructive command denied: {command}")
                raise PermissionError(f"Command denied by user: {command}")

        self.logger.info(f"Executing on {machine}: {command[:80]}")
        result = self._run_on(command, machine)

        if result["returncode"] != 0:
            self.logger.warning(f"Command failed (rc={result['returncode']}): {result['stderr'][:200]}")
        else:
            self.logger.info(f"Command succeeded on {machine}")

        self.log_activity("command_execution", f"Ran on {machine}: {command[:60]}",
                          machine=machine)
        return result["stdout"]

    def deploy_to_fleet(self, command: str, machines: list = None) -> dict:
        """Deploy a command across multiple machines in the fleet.

        Always asks for user approval before fleet-wide operations.

        Args:
            command: Shell command to run on each machine.
            machines: List of machine names. If None, uses all machines from fleet.yml.

        Returns:
            Dict mapping machine_name to {"stdout": str, "success": bool}.
        """
        if machines is None:
            machines = list(self.fleet_config.keys())

        machines_str = ", ".join(machines)
        approved = self.ask_approval(
            action="Fleet-wide deployment",
            details=f"Command: {command[:60]} on [{machines_str}]",
            machine="fleet",
        )
        if not approved:
            self.logger.warning("Fleet deployment denied")
            raise PermissionError("Fleet deployment denied by user")

        results = {}
        for machine_name in machines:
            self.logger.info(f"Deploying to {machine_name}: {command[:60]}")
            result = self._run_on(command, machine_name)
            results[machine_name] = {
                "stdout": result["stdout"],
                "success": result["returncode"] == 0,
            }
            if not results[machine_name]["success"]:
                self.logger.warning(f"Deployment failed on {machine_name}: {result['stderr'][:200]}")
            else:
                self.logger.info(f"Deployment succeeded on {machine_name}")

        success_count = sum(1 for r in results.values() if r["success"])
        self.log_activity("fleet_deployment",
                          f"Deployed to {success_count}/{len(machines)} machines: {command[:60]}",
                          machine="fleet")
        self.log_task(
            task=f"deploy_fleet:{command[:40]}",
            result=f"{success_count}/{len(machines)} succeeded",
            model="n/a", success=success_count == len(machines),
        )
        return results

    def manage_docker(self, action: str, container: str, machine: str = "local") -> dict:
        """Manage Docker containers on a machine.

        Supported actions: ps, start, stop, restart, rm, rmi, logs, inspect, pull.
        Destructive actions (stop, rm, rmi) require user approval.

        Args:
            action: Docker action to perform.
            container: Container/image name or ID.
            machine: Machine name from fleet config.

        Returns:
            Dict with keys: action, container, machine, stdout, success.
        """
        destructive_actions = ("stop", "rm", "rmi")
        if action in destructive_actions:
            approved = self.ask_approval(
                action=f"Docker {action}",
                details=f"Container: {container}",
                machine=machine,
            )
            if not approved:
                raise PermissionError(f"Docker {action} denied for {container}")

        # Build the docker command
        if action == "ps":
            cmd = "docker ps -a"
        elif action == "logs":
            cmd = f"docker logs --tail 100 {shlex.quote(container)}"
        elif action == "inspect":
            cmd = f"docker inspect {shlex.quote(container)}"
        elif action == "pull":
            cmd = f"docker pull {shlex.quote(container)}"
        elif action in ("start", "stop", "restart", "rm"):
            cmd = f"docker {action} {shlex.quote(container)}"
        elif action == "rmi":
            cmd = f"docker rmi {shlex.quote(container)}"
        else:
            raise ValueError(f"Unsupported docker action: {action}")

        self.logger.info(f"Docker {action} {container} on {machine}")
        result = self._run_on(cmd, machine)

        success = result["returncode"] == 0
        self.log_activity("docker", f"docker {action} {container}", machine=machine)
        self.log_task(
            task=f"docker_{action}:{container}",
            result=result["stdout"][:200] if success else result["stderr"][:200],
            model="n/a", success=success,
        )

        return {
            "action": action,
            "container": container,
            "machine": machine,
            "stdout": result["stdout"],
            "success": success,
        }

    def manage_service(self, action: str, service: str, machine: str = "local") -> dict:
        """Manage systemd services on a machine.

        Supported actions: status, start, stop, restart, enable, disable.
        Destructive actions (stop, disable) require user approval.

        Args:
            action: systemctl action.
            service: Service name (e.g., "ollama", "docker").
            machine: Machine name from fleet config.

        Returns:
            Dict with keys: action, service, machine, stdout, success.
        """
        destructive_actions = ("stop", "disable")
        if action in destructive_actions:
            approved = self.ask_approval(
                action=f"systemctl {action}",
                details=f"Service: {service}",
                machine=machine,
            )
            if not approved:
                raise PermissionError(f"Service {action} denied for {service}")

        cmd = f"systemctl {action} {shlex.quote(service)}"
        self.logger.info(f"Service {action} {service} on {machine}")
        result = self._run_on(cmd, machine)

        success = result["returncode"] == 0
        self.log_activity("service", f"systemctl {action} {service}", machine=machine)
        self.log_task(
            task=f"service_{action}:{service}",
            result=result["stdout"][:200] if success else result["stderr"][:200],
            model="n/a", success=success,
        )

        return {
            "action": action,
            "service": service,
            "machine": machine,
            "stdout": result["stdout"],
            "success": success,
        }

    def git_operation(self, action: str, repo_path: str, args: str = "") -> dict:
        """Execute git operations with safety checks.

        Supported actions: status, log, diff, pull, push, commit, branch, checkout, fetch.
        Push to main/master requires user approval.

        Args:
            action: Git action to perform.
            repo_path: Path to the git repository.
            args: Additional arguments for the git command.

        Returns:
            Dict with keys: action, repo_path, stdout, success.
        """
        if action == "push" and ("main" in args or "master" in args):
            approved = self.ask_approval(
                action=f"git push to protected branch",
                details=f"Repo: {repo_path}, Args: {args}",
                machine="local",
            )
            if not approved:
                raise PermissionError(f"Push to protected branch denied: {args}")

        cmd = f"cd {shlex.quote(repo_path)} && git {action}"
        if args:
            cmd += f" {args}"

        self.logger.info(f"Git {action} in {repo_path}")
        result = self._run_on(cmd, "local")

        success = result["returncode"] == 0
        self.log_activity("git", f"git {action} {args}".strip(), machine="local")
        self.log_task(
            task=f"git_{action}:{repo_path}",
            result=result["stdout"][:200] if success else result["stderr"][:200],
            model="n/a", success=success,
        )

        return {
            "action": action,
            "repo_path": repo_path,
            "stdout": result["stdout"],
            "success": success,
        }
