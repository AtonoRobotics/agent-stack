#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""GR00T agent for robot foundation model training, evaluation, and deployment."""

import os
import sys
import ast
import json
import yaml
import sqlite3
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/agent-stack"))
from agents.base_agent import BaseAgent, BASE_DIR, DATA_DIR, DB_PATH


class GrootAgent(BaseAgent):
    """Agent for NVIDIA GR00T foundation model training and deployment pipeline."""

    task_type = "groot"

    def __init__(self):
        super().__init__(self.task_type)
        self.datasets_dir = os.path.join(DATA_DIR, "datasets")
        self.rewards_dir = os.path.join(DATA_DIR, "rewards")
        os.makedirs(self.datasets_dir, exist_ok=True)
        os.makedirs(self.rewards_dir, exist_ok=True)
        self._init_training_db()

    def _init_training_db(self):
        """Ensure the training_runs table exists."""
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""CREATE TABLE IF NOT EXISTS training_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE,
            dataset_path TEXT,
            robot TEXT,
            status TEXT,
            epoch INTEGER DEFAULT 0,
            total_epochs INTEGER DEFAULT 0,
            loss REAL,
            val_loss REAL,
            started TEXT,
            updated TEXT,
            completed TEXT,
            config TEXT,
            notes TEXT
        )""")
        conn.commit()
        conn.close()

    def prepare_dataset(self, raw_data_path: str, robot_config: dict) -> str:
        """Prepare a training dataset from raw simulation/demo data.

        Validates that raw data exists, queries the model for formatting
        instructions, and creates a prepared dataset directory.

        Args:
            raw_data_path: Path to the raw data directory (trajectories, demos).
            robot_config: Dict with robot configuration (name, joints, dof, etc.).

        Returns:
            Path to the prepared dataset directory.

        Raises:
            FileNotFoundError: If raw_data_path does not exist.
        """
        if not os.path.exists(raw_data_path):
            raise FileNotFoundError(f"Raw data path not found: {raw_data_path}")

        model_info = self.get_model_info()
        knowledge = self.load_knowledge(self.task_type)
        robot_name = robot_config.get("name", "unknown_robot")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dataset_path = os.path.join(self.datasets_dir, timestamp)
        os.makedirs(dataset_path, exist_ok=True)

        # Count raw data files
        raw_files = []
        for root, _, files in os.walk(raw_data_path):
            for fname in files:
                raw_files.append(os.path.join(root, fname))

        robot_config_str = yaml.dump(robot_config, default_flow_style=False)

        prompt = f"""You are an expert in preparing training datasets for NVIDIA GR00T robot foundation models.

Knowledge base:
{knowledge}

Prepare a dataset from raw data:
- Raw data path: {raw_data_path}
- Number of raw files: {len(raw_files)}
- Robot: {robot_name}
- Robot configuration:
{robot_config_str}
- Output path: {dataset_path}

Provide a detailed data preparation plan in YAML including:
1. Data format conversion steps (to GR00T-compatible format)
2. Normalization parameters (joint ranges, action spaces)
3. Train/validation/test split ratios
4. Data augmentation techniques
5. Quality filtering criteria
6. Expected output structure"""

        try:
            plan = self.query_with_retry(prompt)

            # Save preparation plan
            plan_path = os.path.join(dataset_path, "preparation_plan.yml")
            with open(plan_path, "w") as f:
                f.write(plan)

            # Create metadata
            metadata = {
                "raw_data_path": raw_data_path,
                "raw_file_count": len(raw_files),
                "robot": robot_name,
                "robot_config": robot_config,
                "created": timestamp,
                "status": "prepared",
            }
            metadata_path = os.path.join(dataset_path, "metadata.yml")
            with open(metadata_path, "w") as f:
                yaml.dump(metadata, f, default_flow_style=False)

            # Create standard subdirectories
            for subdir in ["train", "val", "test"]:
                os.makedirs(os.path.join(dataset_path, subdir), exist_ok=True)

            self.logger.info(f"Dataset prepared: {dataset_path}")
            self.log_task(
                task=f"prepare_dataset:{robot_name}",
                result=f"Dataset at {dataset_path} ({len(raw_files)} raw files)",
                model=model_info["model"], success=True,
            )
            self.log_activity("dataset_preparation",
                              f"Prepared dataset for {robot_name} from {raw_data_path}",
                              robot=robot_name)
            return dataset_path

        except RuntimeError as e:
            self.log_task(task=f"prepare_dataset:{robot_name}",
                          result=str(e), model=model_info["model"], success=False)
            raise

    def start_training(self, dataset_path: str, robot_config: dict,
                       training_config: dict) -> str:
        """Start a GR00T training run.

        Generates a unique job ID, logs the run to the training_runs table,
        and queries the model for training setup instructions.

        Args:
            dataset_path: Path to the prepared dataset.
            robot_config: Dict with robot configuration.
            training_config: Dict with training hyperparameters (epochs, lr, batch_size, etc.).

        Returns:
            The job_id string for tracking the training run.
        """
        model_info = self.get_model_info()
        knowledge = self.load_knowledge(self.task_type)
        robot_name = robot_config.get("name", "unknown_robot")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_id = f"groot_{robot_name}_{timestamp}"

        total_epochs = training_config.get("epochs", 100)
        robot_config_str = yaml.dump(robot_config, default_flow_style=False)
        training_config_str = yaml.dump(training_config, default_flow_style=False)

        # Register the job in the database
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """INSERT INTO training_runs (job_id, dataset_path, robot, status, epoch,
               total_epochs, loss, val_loss, started, updated, config)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, dataset_path, robot_name, "running", 0, total_epochs,
             None, None, timestamp, timestamp,
             json.dumps({"robot": robot_config, "training": training_config})),
        )
        conn.commit()
        conn.close()

        prompt = f"""You are an expert in training NVIDIA GR00T robot foundation models.

Knowledge base:
{knowledge}

Set up training for:
- Job ID: {job_id}
- Dataset: {dataset_path}
- Robot configuration:
{robot_config_str}
- Training configuration:
{training_config_str}

Provide the complete training setup including:
1. Model architecture selection and initialization
2. Data loader configuration
3. Optimizer and scheduler setup
4. Loss function specification
5. Checkpoint strategy
6. Logging and monitoring setup
7. Expected training script or command to launch"""

        try:
            setup = self.query_with_retry(prompt)

            # Save training setup
            job_dir = os.path.join(DATA_DIR, "training_jobs", job_id)
            os.makedirs(job_dir, exist_ok=True)
            setup_path = os.path.join(job_dir, "training_setup.yml")
            with open(setup_path, "w") as f:
                f.write(setup)

            self.logger.info(f"Training started: {job_id}")
            self.log_task(
                task=f"start_training:{job_id}",
                result=f"Job {job_id} started with {total_epochs} epochs",
                model=model_info["model"], success=True,
            )
            self.log_activity("training", f"Started training job {job_id} for {robot_name}",
                              robot=robot_name)
            return job_id

        except RuntimeError as e:
            # Update job status to failed
            conn = sqlite3.connect(DB_PATH)
            conn.execute("UPDATE training_runs SET status='failed', notes=? WHERE job_id=?",
                         (str(e), job_id))
            conn.commit()
            conn.close()
            self.log_task(task=f"start_training:{job_id}", result=str(e),
                          model=model_info["model"], success=False)
            raise

    def monitor_training(self, job_id: str) -> dict:
        """Monitor the status of a training run.

        Queries the training_runs table for the specified job and returns
        current metrics.

        Args:
            job_id: The training job ID returned by start_training.

        Returns:
            Dict with keys: job_id, status, epoch, loss, val_loss, eta.

        Raises:
            ValueError: If job_id is not found.
        """
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM training_runs WHERE job_id = ?", (job_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise ValueError(f"Training job not found: {job_id}")

        row_dict = dict(row)

        # Calculate ETA based on progress
        epoch = row_dict.get("epoch", 0) or 0
        total_epochs = row_dict.get("total_epochs", 0) or 0
        started = row_dict.get("started", "")
        eta = "unknown"

        if epoch > 0 and total_epochs > 0 and started:
            try:
                start_dt = datetime.fromisoformat(started)
                elapsed = (datetime.now() - start_dt).total_seconds()
                time_per_epoch = elapsed / epoch
                remaining_epochs = total_epochs - epoch
                remaining_seconds = time_per_epoch * remaining_epochs
                hours = int(remaining_seconds // 3600)
                minutes = int((remaining_seconds % 3600) // 60)
                eta = f"{hours}h {minutes}m"
            except (ValueError, ZeroDivisionError):
                eta = "unknown"

        result = {
            "job_id": job_id,
            "status": row_dict.get("status", "unknown"),
            "epoch": epoch,
            "total_epochs": total_epochs,
            "loss": row_dict.get("loss"),
            "val_loss": row_dict.get("val_loss"),
            "eta": eta,
            "started": started,
            "updated": row_dict.get("updated", ""),
        }

        self.logger.info(f"Training status for {job_id}: epoch {epoch}/{total_epochs}, "
                         f"status={result['status']}")
        return result

    def evaluate_policy(self, checkpoint_path: str, test_tasks: list) -> dict:
        """Evaluate a trained policy checkpoint on test tasks.

        Queries the model for an evaluation plan and returns structured results.

        Args:
            checkpoint_path: Path to the model checkpoint file.
            test_tasks: List of task description strings to evaluate on.

        Returns:
            Dict with keys: tasks_passed, tasks_total, success_rate, per_task.
        """
        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

        model_info = self.get_model_info()
        knowledge = self.load_knowledge(self.task_type)

        tasks_str = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(test_tasks))

        prompt = f"""You are an expert in evaluating NVIDIA GR00T robot policies.

Knowledge base:
{knowledge}

Evaluate the policy checkpoint:
- Checkpoint: {checkpoint_path}
- Test tasks:
{tasks_str}

For each task, provide an evaluation in JSON format:
{{
    "tasks_passed": number of tasks likely to pass,
    "tasks_total": {len(test_tasks)},
    "success_rate": 0.0 to 1.0,
    "per_task": [
        {{
            "task": "task description",
            "passed": true/false,
            "score": 0.0 to 1.0,
            "notes": "evaluation notes"
        }}
    ]
}}

Respond with ONLY the JSON object, no markdown or explanation."""

        try:
            response = self.query_with_retry(prompt)

            # Parse JSON
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
                import re
                json_match = re.search(r'\{.*\}', response_clean, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    # Construct default result
                    result = {
                        "tasks_passed": 0,
                        "tasks_total": len(test_tasks),
                        "success_rate": 0.0,
                        "per_task": [{"task": t, "passed": False, "score": 0.0, "notes": "Evaluation pending"}
                                     for t in test_tasks],
                    }

            # Ensure required keys
            result.setdefault("tasks_total", len(test_tasks))
            result.setdefault("tasks_passed", 0)
            result.setdefault("success_rate", 0.0)
            result.setdefault("per_task", [])

            # Coerce types
            result["tasks_passed"] = int(result["tasks_passed"])
            result["tasks_total"] = int(result["tasks_total"])
            result["success_rate"] = float(result["success_rate"])

            self.logger.info(
                f"Evaluation: {result['tasks_passed']}/{result['tasks_total']} passed "
                f"({result['success_rate']:.1%} success rate)"
            )
            self.log_task(
                task=f"evaluate_policy:{checkpoint_path}",
                result=f"{result['tasks_passed']}/{result['tasks_total']} passed",
                model=model_info["model"], success=True,
            )
            self.log_activity("evaluation",
                              f"Evaluated checkpoint: {result['success_rate']:.1%} success rate")
            return result

        except RuntimeError as e:
            self.log_task(task=f"evaluate_policy:{checkpoint_path}",
                          result=str(e), model=model_info["model"], success=False)
            raise

    def export_tensorrt(self, checkpoint_path: str, robot_config: dict) -> str:
        """Export a trained model checkpoint to TensorRT format for deployment.

        Queries the model for export instructions and returns the expected
        export path.

        Args:
            checkpoint_path: Path to the source checkpoint.
            robot_config: Dict with robot configuration for target deployment.

        Returns:
            Path to the exported TensorRT model.

        Raises:
            FileNotFoundError: If checkpoint_path does not exist.
        """
        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

        model_info = self.get_model_info()
        knowledge = self.load_knowledge(self.task_type)
        robot_name = robot_config.get("name", "unknown_robot")
        robot_config_str = yaml.dump(robot_config, default_flow_style=False)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = os.path.join(DATA_DIR, "exports", f"{robot_name}_{timestamp}")
        os.makedirs(export_dir, exist_ok=True)
        export_path = os.path.join(export_dir, "model.engine")

        prompt = f"""You are an expert in deploying NVIDIA GR00T models with TensorRT.

Knowledge base:
{knowledge}

Export the model to TensorRT:
- Source checkpoint: {checkpoint_path}
- Target robot:
{robot_config_str}
- Export path: {export_path}

Provide the complete export procedure including:
1. Model graph optimization steps
2. TensorRT conversion parameters (precision, workspace size, batch size)
3. Input/output tensor specifications
4. Calibration data requirements (for INT8)
5. Validation steps for the exported model
6. Deployment configuration for the target platform

Output as structured YAML."""

        try:
            instructions = self.query_with_retry(prompt)

            # Save export instructions
            instructions_path = os.path.join(export_dir, "export_instructions.yml")
            with open(instructions_path, "w") as f:
                f.write(instructions)

            # Create export metadata
            metadata = {
                "source_checkpoint": checkpoint_path,
                "robot": robot_name,
                "robot_config": robot_config,
                "export_path": export_path,
                "created": timestamp,
                "status": "instructions_generated",
            }
            metadata_path = os.path.join(export_dir, "metadata.yml")
            with open(metadata_path, "w") as f:
                yaml.dump(metadata, f, default_flow_style=False)

            self.logger.info(f"TensorRT export planned: {export_dir}")
            self.log_task(
                task=f"export_trt:{robot_name}",
                result=f"Export instructions at {export_dir}",
                model=model_info["model"], success=True,
            )
            self.log_activity("export", f"TensorRT export planned for {robot_name}",
                              robot=robot_name)
            return export_path

        except RuntimeError as e:
            self.log_task(task=f"export_trt:{robot_name}",
                          result=str(e), model=model_info["model"], success=False)
            raise

    def design_reward_function(self, task_description: str, robot_config: dict) -> str:
        """Design a reward function for a specific robot task.

        Queries the model to generate Python code for a reward function,
        validates the syntax, and saves to the rewards directory.

        Args:
            task_description: Description of the task the reward is for.
            robot_config: Dict with robot configuration.

        Returns:
            Path to the saved reward function file.
        """
        model_info = self.get_model_info()
        knowledge = self.load_knowledge(self.task_type)
        robot_name = robot_config.get("name", "unknown_robot")
        robot_config_str = yaml.dump(robot_config, default_flow_style=False)

        prompt = f"""You are an expert in designing reward functions for robot learning.

Knowledge base:
{knowledge}

Design a reward function for:
- Task: {task_description}
- Robot:
{robot_config_str}

Write a complete Python reward function with:
1. Clear docstring explaining the reward components
2. Distance-to-goal reward
3. Smoothness penalty (minimize jerk)
4. Collision penalty
5. Joint limit penalty
6. Task-specific success bonus
7. Proper normalization to [-1, 1] range

Output ONLY Python code, no markdown fences or explanations.
The main function should be named 'compute_reward' and accept (state, action, next_state, info) parameters."""

        try:
            code = self.query_with_retry(prompt)

            # Strip markdown fences
            code = code.strip()
            if code.startswith("```python"):
                code = code[len("```python"):].strip()
            if code.startswith("```"):
                code = code[3:].strip()
            if code.endswith("```"):
                code = code[:-3].strip()

            # Validate Python syntax
            try:
                ast.parse(code)
            except SyntaxError as e:
                self.logger.warning(f"Reward function has syntax error: {e}")
                # Retry once
                retry_prompt = prompt + f"\n\nYour previous code had a syntax error: Line {e.lineno}: {e.msg}\nFix the error."
                code = self.query_with_retry(retry_prompt)
                code = code.strip()
                if code.startswith("```python"):
                    code = code[len("```python"):].strip()
                if code.startswith("```"):
                    code = code[3:].strip()
                if code.endswith("```"):
                    code = code[:-3].strip()
                ast.parse(code)  # Raise if still invalid

            # Save the reward function
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            reward_path = os.path.join(self.rewards_dir, f"{timestamp}.py")

            # Add header comment
            header = (
                f"# Reward function for: {task_description}\n"
                f"# Robot: {robot_name}\n"
                f"# Generated: {timestamp}\n\n"
            )
            with open(reward_path, "w") as f:
                f.write(header + code)

            self.logger.info(f"Reward function saved: {reward_path}")
            self.log_task(
                task=f"design_reward:{task_description[:40]}",
                result=f"Saved to {reward_path}",
                model=model_info["model"], success=True,
            )
            self.log_activity("reward_design",
                              f"Designed reward for {robot_name}: {task_description[:60]}",
                              robot=robot_name)
            return reward_path

        except (RuntimeError, SyntaxError) as e:
            self.log_task(task=f"design_reward:{task_description[:40]}",
                          result=str(e), model=model_info["model"], success=False)
            raise
