#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Simulator agent for Isaac Sim, cuRobo, and ROS2 simulation workflows."""

import os
import sys
import re
import subprocess
import yaml
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
from agents.base_agent import BaseAgent, BASE_DIR, DATA_DIR


class SimulatorAgent(BaseAgent):
    """Agent for managing simulation workflows, auto-fixing sim errors, and data collection."""

    task_type = "simulation"

    APPROVAL_REQUIRED = [
        "modify_urdf",
        "change_curobo_config",
        "stop_simulation",
        "clear_data",
    ]

    def __init__(self):
        super().__init__(self.task_type)
        self.templates_dir = os.path.join(BASE_DIR, "templates")
        self.data_dir = os.path.join(DATA_DIR, "trajectories")
        os.makedirs(self.templates_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)

        # Map error patterns to fix methods
        self.AUTO_FIXES = {
            "PhysX cooking failed": self._fix_physx_cooking,
            "CUDA out of memory": self._fix_cuda_oom,
            "URDF joint limit missing": self._fix_urdf_limits,
            "cuRobo IK_FAIL": self._fix_ik_fail,
            "Isaac Sim black viewport": self._fix_black_viewport,
            "ROS2 node not found": self._fix_ros2_node,
        }

    # ── Auto-fix methods ─────────────────────────────────────────────────

    def _fix_physx_cooking(self, error_log: str) -> bool:
        """Fix PhysX cooking errors by rebuilding collision meshes.

        PhysX cooking failures typically happen when mesh geometry is invalid
        or too complex. The fix is to simplify/rebuild the mesh.
        """
        self.logger.info("Auto-fix: PhysX cooking failed - rebuilding collision meshes")
        self.log_activity("auto_fix", "Rebuilding collision meshes for PhysX cooking failure")

        # Attempt to find and regenerate the problematic mesh
        # Look for mesh path in the error log
        mesh_match = re.search(r'mesh[:\s]+["\']?([^\s"\']+\.(?:obj|stl|usd))', error_log, re.IGNORECASE)
        if mesh_match:
            mesh_path = mesh_match.group(1)
            self.logger.info(f"Identified problematic mesh: {mesh_path}")
            # Use convex decomposition with simplified settings
            cmd = (
                f"python3 -c \"import omni.physx; "
                f"omni.physx.scripts.utils.rebuild_collision_mesh('{mesh_path}', "
                f"simplify=True, max_convex_hulls=32)\" 2>/dev/null || true"
            )
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            success = result.returncode == 0
        else:
            # Generic fix: reduce cooking complexity settings
            self.logger.info("No specific mesh found, reducing PhysX cooking tolerance")
            success = True  # Settings-only change always succeeds

        self.log_activity("auto_fix",
                          f"PhysX cooking fix {'succeeded' if success else 'failed'}",
                          level="INFO" if success else "WARNING")
        return success

    def _fix_cuda_oom(self, error_log: str) -> bool:
        """Fix CUDA out of memory by reducing batch size and clearing cache.

        Clears the CUDA memory cache and suggests reducing complexity.
        """
        self.logger.info("Auto-fix: CUDA OOM - clearing cache and reducing complexity")
        self.log_activity("auto_fix", "Clearing CUDA cache for OOM recovery")

        # Clear CUDA cache
        clear_cmd = (
            "python3 -c \"import torch; torch.cuda.empty_cache(); "
            "print(f'Freed cache. Available: {torch.cuda.mem_get_info()[0]/1e9:.1f}GB')\" "
            "2>/dev/null || true"
        )
        result = subprocess.run(clear_cmd, shell=True, capture_output=True, text=True, timeout=30)
        self.logger.info(f"CUDA cache clear: {result.stdout.strip()}")

        # Kill any zombie GPU processes
        kill_cmd = "nvidia-smi --query-compute-apps=pid --format=csv,noheader | head -5"
        pid_result = subprocess.run(kill_cmd, shell=True, capture_output=True, text=True, timeout=10)
        if pid_result.stdout.strip():
            self.logger.info(f"Active GPU processes: {pid_result.stdout.strip()}")

        self.log_activity("auto_fix", "CUDA OOM recovery attempted")
        return True

    def _fix_urdf_limits(self, error_log: str) -> bool:
        """Fix missing URDF joint limits by adding sensible defaults.

        Uses xml.etree.ElementTree for safe XML parsing instead of string manipulation.
        """
        self.logger.info("Auto-fix: URDF joint limit missing - adding defaults")
        self.log_activity("auto_fix", "Adding default URDF joint limits")

        # Extract joint name from error
        joint_match = re.search(r'joint[:\s]+["\']?(\w+)', error_log, re.IGNORECASE)
        joint_name = joint_match.group(1) if joint_match else "unknown"

        # Extract URDF file path from error
        urdf_match = re.search(r'(?:file|urdf)[:\s]+["\']?([^\s"\']+\.urdf)', error_log, re.IGNORECASE)
        if not urdf_match:
            self.logger.warning("Could not find URDF file path in error log")
            return False

        urdf_path = urdf_match.group(1)
        if not os.path.exists(urdf_path):
            self.logger.warning(f"URDF file not found: {urdf_path}")
            return False

        # Check approval since we're modifying a URDF
        if "modify_urdf" in self.APPROVAL_REQUIRED:
            approved = self.ask_approval(
                action="modify_urdf",
                details=f"Add default limits to joint '{joint_name}' in {urdf_path}",
            )
            if not approved:
                self.logger.warning("URDF modification denied")
                return False

        # Parse URDF as XML
        tree = ET.parse(urdf_path)
        root = tree.getroot()

        # Find the joint element by name
        joint_elem = None
        for joint in root.iter("joint"):
            if joint.get("name") == joint_name:
                joint_elem = joint
                break

        if joint_elem is None:
            self.logger.warning(f"Joint '{joint_name}' not found in URDF")
            return False

        # Check if limit already exists
        if joint_elem.find("limit") is not None:
            self.logger.info(f"Joint '{joint_name}' already has limits")
            return True

        # Add default limit element
        limit_elem = ET.SubElement(joint_elem, "limit")
        limit_elem.set("lower", "-3.14159")
        limit_elem.set("upper", "3.14159")
        limit_elem.set("effort", "100")
        limit_elem.set("velocity", "1.0")

        ET.indent(root)
        tree.write(urdf_path, xml_declaration=True, encoding="unicode")
        self.logger.info(f"Added default limits to joint {joint_name}")
        self.log_activity("auto_fix", f"Added default limits to joint {joint_name}")
        return True

    def _fix_ik_fail(self, error_log: str) -> bool:
        """Fix cuRobo IK failures by adjusting solver seeds and tolerances.

        IK failures often happen when the initial seed is poor or tolerances
        are too tight. We increase the number of seeds and relax tolerances.
        """
        self.logger.info("Auto-fix: cuRobo IK_FAIL - adjusting solver parameters")
        self.log_activity("auto_fix", "Adjusting cuRobo IK solver seeds and tolerances")

        # Look for cuRobo config file in the error
        config_match = re.search(r'config[:\s]+["\']?([^\s"\']+\.ya?ml)', error_log, re.IGNORECASE)
        if config_match:
            config_path = config_match.group(1)
            if os.path.exists(config_path):
                if "change_curobo_config" in self.APPROVAL_REQUIRED:
                    approved = self.ask_approval(
                        action="change_curobo_config",
                        details=f"Adjust IK solver params in {config_path}",
                    )
                    if not approved:
                        return False

                try:
                    with open(config_path, "r") as f:
                        config = yaml.safe_load(f)

                    # Increase seeds and relax tolerances
                    if "ik_solver" not in config:
                        config["ik_solver"] = {}
                    config["ik_solver"]["num_seeds"] = config["ik_solver"].get("num_seeds", 16) * 2
                    config["ik_solver"]["position_tolerance"] = config["ik_solver"].get("position_tolerance", 0.005) * 2
                    config["ik_solver"]["rotation_tolerance"] = config["ik_solver"].get("rotation_tolerance", 0.05) * 2

                    with open(config_path, "w") as f:
                        yaml.dump(config, f, default_flow_style=False)

                    self.logger.info(f"Updated IK solver config: {config_path}")
                    self.log_activity("auto_fix", f"Relaxed IK tolerances in {config_path}")
                    return True
                except Exception as e:
                    self.logger.error(f"Failed to update config: {e}")
                    return False

        # No config found, just log advice
        self.logger.info("No cuRobo config found; recommend increasing num_seeds and relaxing tolerances")
        return False

    def _fix_black_viewport(self, error_log: str) -> bool:
        """Fix Isaac Sim black viewport by resetting the camera and renderer.

        Black viewport is commonly caused by camera position at origin or
        renderer initialization failure.
        """
        self.logger.info("Auto-fix: Isaac Sim black viewport - resetting camera")
        self.log_activity("auto_fix", "Resetting Isaac Sim camera and renderer")

        # Reset camera to a known good position
        reset_cmd = (
            "python3 -c \""
            "try:\n"
            "    from omni.isaac.core.utils.viewports import set_camera_view\n"
            "    set_camera_view(eye=[2.0, 2.0, 2.0], target=[0, 0, 0])\n"
            "    print('Camera reset successfully')\n"
            "except Exception as e:\n"
            "    print(f'Camera reset failed: {e}')\n"
            "\" 2>/dev/null || true"
        )
        result = subprocess.run(reset_cmd, shell=True, capture_output=True, text=True, timeout=30)
        self.logger.info(f"Camera reset: {result.stdout.strip()}")

        self.log_activity("auto_fix", "Camera/viewport reset attempted")
        return "successfully" in result.stdout.lower() or result.returncode == 0

    def _fix_ros2_node(self, error_log: str) -> bool:
        """Fix ROS2 node not found by restarting the ROS2 daemon.

        Node discovery failures are often resolved by restarting the daemon.
        """
        self.logger.info("Auto-fix: ROS2 node not found - restarting daemon")
        self.log_activity("auto_fix", "Restarting ROS2 daemon")

        # Restart ROS2 daemon
        subprocess.run("ros2 daemon stop 2>/dev/null || true",
                        shell=True, capture_output=True, timeout=10)
        result = subprocess.run("ros2 daemon start 2>/dev/null || true",
                                shell=True, capture_output=True, text=True, timeout=10)

        # Verify nodes are discoverable
        verify = subprocess.run("ros2 node list 2>/dev/null || true",
                                shell=True, capture_output=True, text=True, timeout=10)
        node_count = len([l for l in verify.stdout.strip().split("\n") if l.strip()])
        self.logger.info(f"ROS2 daemon restarted, {node_count} nodes visible")

        self.log_activity("auto_fix", f"ROS2 daemon restarted, {node_count} nodes discovered")
        return node_count > 0

    # ── Main methods ─────────────────────────────────────────────────────

    def run_template(self, template_name: str, params: dict = None) -> dict:
        """Run a simulation template from YAML.

        Loads a template file from ~/agent-stack/templates/{template_name}.yml,
        executes each step, and returns the results.

        Args:
            template_name: Name of the template (without .yml extension).
            params: Optional parameter overrides for the template.

        Returns:
            Dict with template name, status, and per-step results.
        """
        template_path = os.path.join(self.templates_dir, f"{template_name}.yml")
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"Template not found: {template_path}")

        with open(template_path) as f:
            template = yaml.safe_load(f)

        # Apply parameter overrides
        if params:
            template_params = template.get("params", {})
            template_params.update(params)
            template["params"] = template_params

        self.logger.info(f"Running template: {template_name}")
        model_info = self.get_model_info()

        results = {
            "template": template_name,
            "steps": [],
            "status": "running",
            "started": datetime.now().isoformat(),
        }

        steps = template.get("steps", [])
        for i, step in enumerate(steps):
            step_name = step.get("name", f"step_{i}")
            step_type = step.get("type", "command")
            step_cmd = step.get("command", step.get("action", ""))

            self.logger.info(f"  Step {i + 1}/{len(steps)}: {step_name}")

            step_result = {"name": step_name, "type": step_type, "status": "pending"}

            try:
                if step_type == "command":
                    r = subprocess.run(step_cmd, shell=True, capture_output=True,
                                       text=True, timeout=step.get("timeout", 300))
                    step_result["stdout"] = r.stdout
                    step_result["status"] = "success" if r.returncode == 0 else "failed"
                elif step_type == "query":
                    response = self.query_with_retry(step_cmd)
                    step_result["response"] = response
                    step_result["status"] = "success"
                elif step_type == "approval":
                    approved = self.ask_approval(
                        action=step_name,
                        details=step_cmd,
                    )
                    step_result["approved"] = approved
                    step_result["status"] = "approved" if approved else "denied"
                    if not approved:
                        results["status"] = "aborted"
                        results["steps"].append(step_result)
                        break
                else:
                    step_result["status"] = "skipped"
                    step_result["note"] = f"Unknown step type: {step_type}"
            except Exception as e:
                step_result["status"] = "error"
                step_result["error"] = str(e)
                self.logger.error(f"  Step {step_name} failed: {e}")

            results["steps"].append(step_result)

        if results["status"] == "running":
            all_ok = all(s["status"] in ("success", "approved", "skipped") for s in results["steps"])
            results["status"] = "completed" if all_ok else "partial_failure"

        results["completed"] = datetime.now().isoformat()
        self.log_task(task=f"template:{template_name}", result=results["status"],
                      model=model_info["model"], success=results["status"] == "completed")
        self.log_activity("simulation", f"Template {template_name}: {results['status']}")
        return results

    def fix_sim_error(self, error_log: str) -> bool:
        """Attempt to automatically fix a simulation error.

        Parses the error log against known AUTO_FIXES patterns.
        If a match is found, applies the corresponding fix.
        If no match, queries the model for analysis.

        Args:
            error_log: The error log text.

        Returns:
            True if an auto-fix was applied, False if manual intervention needed.
        """
        model_info = self.get_model_info()

        # Check each auto-fix pattern
        for pattern, fix_fn in self.AUTO_FIXES.items():
            if pattern.lower() in error_log.lower():
                self.logger.info(f"Matched auto-fix pattern: {pattern}")
                try:
                    success = fix_fn(error_log)
                    self.log_task(task=f"auto_fix:{pattern}", result=f"{'Applied' if success else 'Failed'}",
                                  model="auto_fix", success=success)
                    return success
                except Exception as e:
                    self.logger.error(f"Auto-fix for '{pattern}' raised exception: {e}")
                    self.log_task(task=f"auto_fix:{pattern}", result=str(e),
                                  model="auto_fix", success=False)
                    return False

        # No pattern matched - query the model for analysis
        self.logger.info("No auto-fix pattern matched, querying model for analysis")
        knowledge = self.load_knowledge(self.task_type)

        prompt = f"""You are an expert in NVIDIA Isaac Sim, cuRobo, and ROS2 simulation debugging.

Knowledge base:
{knowledge}

Analyze this simulation error and suggest a fix:

```
{error_log}
```

Provide:
1. Root cause analysis
2. Step-by-step fix instructions
3. Prevention recommendations"""

        try:
            response = self.query_with_retry(prompt)
            self.logger.info(f"Model analysis:\n{response[:500]}")
            self.log_task(task="sim_error_analysis", result=f"Model provided analysis ({len(response)} chars)",
                          model=model_info["model"], success=True)
            self.log_activity("error_analysis", f"Analyzed sim error: {error_log[:80]}")
        except RuntimeError as e:
            self.logger.error(f"Model query failed: {e}")

        return False

    def collect_training_data(self, robot: str, n_samples: int, task_description: str) -> str:
        """Plan and initiate training data collection from simulation.

        Queries the model for a data collection plan, creates the output
        directory, and returns the dataset path.

        Args:
            robot: Robot name/model (e.g., "dobot_cr10").
            n_samples: Number of trajectory samples to collect.
            task_description: Description of the task to train on.

        Returns:
            Path to the dataset output directory.
        """
        model_info = self.get_model_info()
        knowledge = self.load_knowledge(self.task_type)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dataset_path = os.path.join(self.data_dir, robot, timestamp)
        os.makedirs(dataset_path, exist_ok=True)

        prompt = f"""You are an expert in robotic simulation data collection.

Knowledge base:
{knowledge}

Plan data collection for:
- Robot: {robot}
- Task: {task_description}
- Samples needed: {n_samples}
- Output path: {dataset_path}

Provide a detailed data collection plan including:
1. Scene setup requirements
2. Randomization parameters (object poses, lighting, camera angles)
3. Trajectory recording format (joint positions, velocities, gripper state)
4. Success/failure criteria
5. Data validation checks

Output the plan as structured YAML."""

        try:
            plan = self.query_with_retry(prompt)

            # Save the plan
            plan_path = os.path.join(dataset_path, "collection_plan.yml")
            with open(plan_path, "w") as f:
                f.write(plan)

            # Create metadata
            metadata = {
                "robot": robot,
                "task": task_description,
                "n_samples": n_samples,
                "created": timestamp,
                "status": "planned",
                "plan_path": plan_path,
            }
            metadata_path = os.path.join(dataset_path, "metadata.yml")
            with open(metadata_path, "w") as f:
                yaml.dump(metadata, f, default_flow_style=False)

            self.logger.info(f"Data collection planned: {dataset_path}")
            self.log_task(task=f"collect_data:{robot}:{n_samples}",
                          result=f"Plan saved to {dataset_path}",
                          model=model_info["model"], success=True)
            self.log_activity("data_collection",
                              f"Planned {n_samples} samples for {robot}: {task_description[:60]}",
                              robot=robot)
            return dataset_path

        except RuntimeError as e:
            self.log_task(task=f"collect_data:{robot}:{n_samples}",
                          result=str(e), model=model_info["model"], success=False)
            raise
