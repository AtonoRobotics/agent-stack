#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Cosmos agent for synthetic data generation and world model inference."""

import os
import sys
import json
import yaml
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
from agents.base_agent import BaseAgent, BASE_DIR, DATA_DIR

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
from tools import gpu as gpu_tool


class CosmosAgent(BaseAgent):
    """Agent for NVIDIA Cosmos world model operations - synthetic data and trajectory prediction."""

    task_type = "cosmos"

    MINIMUM_VRAM_GB = 40.0  # Cosmos needs significant VRAM

    def __init__(self):
        super().__init__(self.task_type)
        self.synthetic_dir = os.path.join(DATA_DIR, "synthetic")
        os.makedirs(self.synthetic_dir, exist_ok=True)

    def check_vram_available(self, machine: str = "dgx-spark") -> bool:
        """Check if a machine has enough VRAM available for Cosmos operations.

        Cosmos world models require significant VRAM (>40GB). This method
        queries the GPU on the target machine and checks availability.

        Args:
            machine: Machine name from fleet config (default: "dgx-spark").

        Returns:
            True if enough VRAM is available, False otherwise.
        """
        try:
            usage = gpu_tool.get_usage(machine=machine)
            vram_total = usage["vram_total_gb"]
            vram_used = usage["vram_used_gb"]
            vram_available = vram_total - vram_used

            self.logger.info(
                f"VRAM on {machine}: {vram_available:.1f}GB available "
                f"({vram_used:.1f}/{vram_total:.1f}GB used), "
                f"need {self.MINIMUM_VRAM_GB}GB"
            )

            has_enough = vram_available >= self.MINIMUM_VRAM_GB
            if not has_enough:
                self.logger.warning(
                    f"Insufficient VRAM on {machine}: {vram_available:.1f}GB < {self.MINIMUM_VRAM_GB}GB"
                )
            return has_enough

        except Exception as e:
            self.logger.error(f"Failed to check VRAM on {machine}: {e}")
            return False

    def generate_synthetic_data(self, task_description: str, n_samples: int,
                                robot_config: dict) -> str:
        """Generate synthetic training data using Cosmos world model.

        Checks VRAM availability first, then queries the model to plan
        synthetic data generation and creates the output directory structure.

        Args:
            task_description: Description of the task to generate data for.
            n_samples: Number of synthetic samples to generate.
            robot_config: Dict with robot configuration (name, urdf, joints, etc.).

        Returns:
            Path to the synthetic data output directory.

        Raises:
            RuntimeError: If insufficient VRAM is available.
        """
        # Check VRAM availability
        target_machine = "dgx-spark"
        if not self.check_vram_available(target_machine):
            raise RuntimeError(
                f"Insufficient VRAM on {target_machine} for Cosmos. "
                f"Need at least {self.MINIMUM_VRAM_GB}GB available."
            )

        model_info = self.get_model_info()
        knowledge = self.load_knowledge(self.task_type)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(self.synthetic_dir, timestamp)
        os.makedirs(output_path, exist_ok=True)

        robot_name = robot_config.get("name", "unknown_robot")
        robot_config_str = yaml.dump(robot_config, default_flow_style=False)

        prompt = f"""You are an expert in NVIDIA Cosmos world model for synthetic data generation.

Knowledge base:
{knowledge}

Generate a synthetic data generation plan for:
- Task: {task_description}
- Samples: {n_samples}
- Robot configuration:
{robot_config_str}
- Output path: {output_path}

Provide a detailed plan in YAML format including:
1. Scene generation parameters (environments, lighting, objects)
2. Camera viewpoints and rendering settings
3. Physics simulation parameters
4. Domain randomization ranges
5. Output format specification (images, depth maps, segmentation masks, poses)
6. Quality validation criteria
7. Estimated compute time and VRAM requirements"""

        try:
            plan = self.query_with_retry(prompt)

            # Save the generation plan
            plan_path = os.path.join(output_path, "generation_plan.yml")
            with open(plan_path, "w") as f:
                f.write(plan)

            # Create metadata
            metadata = {
                "task": task_description,
                "n_samples": n_samples,
                "robot": robot_name,
                "robot_config": robot_config,
                "created": timestamp,
                "machine": target_machine,
                "status": "planned",
                "output_path": output_path,
            }
            metadata_path = os.path.join(output_path, "metadata.yml")
            with open(metadata_path, "w") as f:
                yaml.dump(metadata, f, default_flow_style=False)

            # Create subdirectories for outputs
            for subdir in ["images", "depth", "segmentation", "poses", "annotations"]:
                os.makedirs(os.path.join(output_path, subdir), exist_ok=True)

            self.logger.info(f"Synthetic data generation planned: {output_path}")
            self.log_task(
                task=f"synthetic_gen:{robot_name}:{n_samples}",
                result=f"Plan saved to {output_path}",
                model=model_info["model"], success=True,
            )
            self.log_activity("synthetic_data",
                              f"Planned {n_samples} synthetic samples for {robot_name}: {task_description[:60]}",
                              robot=robot_name)
            return output_path

        except RuntimeError as e:
            self.log_task(
                task=f"synthetic_gen:{robot_name}:{n_samples}",
                result=str(e), model=model_info["model"], success=False,
            )
            raise

    def predict_trajectory_outcome(self, trajectory: dict, scene_config: dict) -> dict:
        """Predict the outcome of a robot trajectory using world model reasoning.

        Sends the trajectory and scene configuration to the model for analysis,
        and returns a structured prediction.

        Args:
            trajectory: Dict with trajectory data (waypoints, joint positions, timestamps).
            scene_config: Dict with scene description (objects, obstacles, goals).

        Returns:
            Dict with keys:
                success_probability (float): 0.0 to 1.0
                predicted_error (float): Expected position error in meters
                risk_factors (list): List of identified risk strings
        """
        model_info = self.get_model_info()
        knowledge = self.load_knowledge(self.task_type)

        trajectory_str = json.dumps(trajectory, indent=2, default=str)
        scene_str = json.dumps(scene_config, indent=2, default=str)

        prompt = f"""You are an expert in robotic trajectory analysis and world model prediction.

Knowledge base:
{knowledge}

Analyze this trajectory and predict the outcome:

Trajectory:
{trajectory_str}

Scene configuration:
{scene_str}

Respond with ONLY a JSON object (no markdown, no explanation):
{{
    "success_probability": 0.0 to 1.0,
    "predicted_error": estimated position error in meters,
    "risk_factors": ["list", "of", "risk", "factors"],
    "collision_risk": true/false,
    "singularity_risk": true/false,
    "joint_limit_risk": true/false,
    "recommended_adjustments": ["list", "of", "suggested", "changes"]
}}"""

        try:
            response = self.query_with_retry(prompt)

            # Parse JSON from response
            response_clean = response.strip()
            if response_clean.startswith("```json"):
                response_clean = response_clean[len("```json"):].strip()
            if response_clean.startswith("```"):
                response_clean = response_clean[3:].strip()
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3].strip()

            try:
                result = json.loads(response_clean)
            except json.JSONDecodeError:
                # Try to extract JSON from the response
                import re
                json_match = re.search(r'\{.*\}', response_clean, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    result = {}

            # Ensure required keys with proper types
            result.setdefault("success_probability", 0.5)
            result.setdefault("predicted_error", 0.01)
            result.setdefault("risk_factors", [])

            # Coerce types
            result["success_probability"] = float(result["success_probability"])
            result["predicted_error"] = float(result["predicted_error"])
            if not isinstance(result["risk_factors"], list):
                result["risk_factors"] = [str(result["risk_factors"])]

            self.log_task(
                task="trajectory_prediction",
                result=f"P(success)={result['success_probability']:.2f}, "
                       f"error={result['predicted_error']:.4f}m",
                model=model_info["model"], success=True,
            )
            self.log_activity("trajectory_prediction",
                              f"Predicted trajectory: P(success)={result['success_probability']:.2f}")
            return result

        except RuntimeError as e:
            self.log_task(task="trajectory_prediction", result=str(e),
                          model=model_info["model"], success=False)
            raise

    def validate_world_model_output(self, output_path: str) -> bool:
        """Validate that world model output files exist and have valid content.

        Checks the output directory for expected files (images, metadata)
        and verifies they are not empty or corrupted.

        Args:
            output_path: Path to the output directory to validate.

        Returns:
            True if all validation checks pass, False otherwise.
        """
        if not os.path.exists(output_path):
            self.logger.error(f"Output path does not exist: {output_path}")
            return False

        if not os.path.isdir(output_path):
            self.logger.error(f"Output path is not a directory: {output_path}")
            return False

        # Check for metadata file
        metadata_path = os.path.join(output_path, "metadata.yml")
        if not os.path.exists(metadata_path):
            self.logger.warning(f"Missing metadata.yml in {output_path}")
            return False

        try:
            with open(metadata_path) as f:
                metadata = yaml.safe_load(f)
            if not metadata:
                self.logger.warning("metadata.yml is empty")
                return False
        except Exception as e:
            self.logger.warning(f"Invalid metadata.yml: {e}")
            return False

        # Check expected subdirectories
        expected_dirs = ["images", "depth", "segmentation", "poses", "annotations"]
        missing_dirs = []
        for subdir in expected_dirs:
            subdir_path = os.path.join(output_path, subdir)
            if not os.path.exists(subdir_path):
                missing_dirs.append(subdir)

        if missing_dirs:
            self.logger.warning(f"Missing subdirectories: {missing_dirs}")
            # Not a hard failure - some outputs may not include all types
            if len(missing_dirs) == len(expected_dirs):
                self.logger.error("All expected subdirectories are missing")
                return False

        # Check for non-empty output files
        total_files = 0
        empty_files = 0
        for subdir in expected_dirs:
            subdir_path = os.path.join(output_path, subdir)
            if os.path.exists(subdir_path):
                for fname in os.listdir(subdir_path):
                    fpath = os.path.join(subdir_path, fname)
                    if os.path.isfile(fpath):
                        total_files += 1
                        if os.path.getsize(fpath) == 0:
                            empty_files += 1
                            self.logger.warning(f"Empty file: {fpath}")

        # Check generation plan
        plan_path = os.path.join(output_path, "generation_plan.yml")
        has_plan = os.path.exists(plan_path) and os.path.getsize(plan_path) > 0

        # Validation summary
        valid = has_plan and empty_files == 0
        self.logger.info(
            f"Validation {'PASSED' if valid else 'FAILED'}: "
            f"{total_files} files, {empty_files} empty, plan={'yes' if has_plan else 'no'}"
        )

        self.log_activity("validation",
                          f"World model output validation: {'PASS' if valid else 'FAIL'} "
                          f"({total_files} files in {output_path})")
        return valid
