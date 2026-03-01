#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Base agent class for the Alpha Robotics Agent Stack."""

import os
import sys
import time
import yaml
import json
import atexit
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.expanduser("~/agent-stack"))

import httpx


BASE_DIR = os.path.expanduser("~/agent-stack")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
DB_PATH = os.path.join(DATA_DIR, "metrics.db")

# ── Module-level caches ──────────────────────────────────────────────────

_config_cache: dict = {}
_knowledge_cache: dict = {}
_http_client: httpx.Client | None = None


def _load_config(filename: str) -> dict:
    """Load a YAML config file, caching the result."""
    if filename not in _config_cache:
        path = os.path.join(CONFIG_DIR, filename)
        with open(path) as f:
            _config_cache[filename] = yaml.safe_load(f)
    return _config_cache[filename]


def _get_http_client() -> httpx.Client:
    """Return a shared httpx client (lazy init, 180s read timeout)."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=httpx.Timeout(
            connect=10.0, read=300.0, write=10.0, pool=10.0
        ))
        atexit.register(_http_client.close)
    return _http_client


class BaseAgent:
    """Base class for all agents in the stack."""

    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        self.start_time = datetime.now()

        # Load configs (cached at module level)
        _full_config = _load_config("models.yml")
        self.models_config = _full_config["models"]
        self.policy = _full_config.get("policy", {})
        self.fleet_config = _load_config("fleet.yml")["machines"]
        self.alerts_config = _load_config("alerts.yml")["thresholds"]
        self.resources_config = _load_config("resources.yml")["limits"]

        # Setup logging
        os.makedirs(LOGS_DIR, exist_ok=True)
        self.logger = logging.getLogger(f"agent.{agent_type}")
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            fh = logging.FileHandler(os.path.join(LOGS_DIR, f"{agent_type}.log"))
            fh.setLevel(logging.DEBUG)
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
            fh.setFormatter(fmt)
            ch.setFormatter(fmt)
            self.logger.addHandler(fh)
            self.logger.addHandler(ch)

        # Persistent DB connection (WAL mode allows concurrent readers)
        os.makedirs(DATA_DIR, exist_ok=True)
        self._db = sqlite3.connect(DB_PATH)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._init_db()

        self.logger.info(f"{agent_type} agent initialized")

    def _init_db(self):
        """Ensure database and tables exist."""
        self._db.execute("""CREATE TABLE IF NOT EXISTS agent_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT, task TEXT, started TEXT, completed TEXT,
            model_used TEXT, success INTEGER, tokens_saved INTEGER,
            retries INTEGER, notes TEXT
        )""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS performance_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            robot_serial TEXT, timestamp TEXT, metric_name TEXT,
            value REAL, units TEXT, source TEXT
        )""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, category TEXT, machine TEXT, robot TEXT,
            agent TEXT, message TEXT, level TEXT
        )""")
        self._db.commit()

    def close(self):
        """Close the persistent DB connection."""
        if self._db:
            self._db.close()
            self._db = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def load_knowledge(self, task_type: str) -> str:
        """Load relevant knowledge base files for a task type (cached)."""
        if task_type in _knowledge_cache:
            return _knowledge_cache[task_type]

        knowledge_map = {
            "code_generation": ["software/", "lessons_learned/"],
            "research": ["hardware/", "software/", "workflows/"],
            "sysadmin": ["hardware/", "workflows/", "lessons_learned/docker_issues.md"],
            "simulation": ["software/isaac_sim_51.md", "software/curobo_077.md",
                           "lessons_learned/simulation.md", "hardware/dobot_cr10.md"],
            "cosmos": ["software/", "hardware/dgx_spark.md"],
            "groot": ["software/", "hardware/", "lessons_learned/"],
            "monitoring": ["hardware/", "workflows/fleet_management.md"],
            "health_check": ["hardware/", "workflows/"],
        }

        paths = knowledge_map.get(task_type, ["lessons_learned/"])
        combined = []

        for rel_path in paths:
            full_path = os.path.join(KNOWLEDGE_DIR, rel_path)
            if os.path.isdir(full_path):
                for root, _, files in os.walk(full_path):
                    for fname in sorted(files):
                        if fname.endswith(".md"):
                            fpath = os.path.join(root, fname)
                            try:
                                with open(fpath) as f:
                                    content = f.read()
                                combined.append(f"--- {fname} ---\n{content}")
                            except Exception:
                                pass
            elif os.path.isfile(full_path):
                try:
                    with open(full_path) as f:
                        content = f.read()
                    combined.append(f"--- {os.path.basename(full_path)} ---\n{content}")
                except Exception:
                    pass

        result = "\n\n".join(combined) if combined else ""
        _knowledge_cache[task_type] = result
        return result

    def query_ollama(self, prompt: str, model: str, host: str, port: int) -> str:
        """Send a query to an Ollama instance and return the response.

        Uses a shared httpx client with 300s read timeout (72b models ~4.4 tok/s).
        POST to http://host:port/api/generate with stream=false.
        """
        url = f"http://{host}:{port}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 1024},
        }
        self.logger.debug(f"Querying {model} @ {host}:{port}")

        client = _get_http_client()
        response = client.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "")

    def query_with_retry(self, prompt: str, task_type: str = None) -> str:
        """Query the appropriate model with retry logic and exponential backoff.

        Gets model config for the task_type (or self.agent_type).
        Tries up to 3 times with 1s, 2s, 4s backoff.
        On 3 failures, logs and raises exception.
        Never falls back to Claude API automatically.
        """
        task_type = task_type or self.agent_type
        model_conf = self.models_config.get(task_type)
        if not model_conf:
            raise ValueError(f"No model config for task type: {task_type}")

        model = model_conf["model"]
        host = model_conf["host"]
        port = model_conf["port"]

        last_error = None
        for attempt in range(1, 4):
            try:
                self.logger.info(f"Attempt {attempt}/3: {model} @ {host}")
                result = self.query_ollama(prompt, model, host, port)
                if result.strip():
                    self.logger.info(f"Success on attempt {attempt}")
                    return result
                else:
                    last_error = "Empty response from model"
                    self.logger.warning(f"Attempt {attempt}: empty response")
            except httpx.ConnectError as e:
                last_error = f"Connection error: {e}"
                self.logger.warning(f"Attempt {attempt}: {last_error}")
            except httpx.TimeoutException as e:
                last_error = f"Timeout: {e}"
                self.logger.warning(f"Attempt {attempt}: {last_error}")
            except Exception as e:
                last_error = f"Error: {e}"
                self.logger.warning(f"Attempt {attempt}: {last_error}")

            # Exponential backoff: 1s, 2s, 4s (skip after last attempt)
            if attempt < 3:
                delay = 2 ** (attempt - 1)
                self.logger.debug(f"Backing off {delay}s before retry")
                time.sleep(delay)

        error_msg = f"All 3 attempts failed for {model} @ {host}. Last error: {last_error}"
        self.logger.error(error_msg)
        self.log_task(
            task=f"query_{task_type}",
            result=error_msg,
            model=model,
            success=False,
            retries=3,
        )

        # Local-first policy: prompt for API escalation instead of raising immediately
        if self.policy.get("local_first") and self.policy.get("require_explicit_approval_for_api"):
            fallback_conf = self.models_config.get("fallback", {})
            fallback_model = fallback_conf.get("model", "claude-sonnet-4-20250514")
            print()
            print("┌─ API ESCALATION ────────────────────────────────┐")
            print(f"│  Local inference failed after 3 attempts         │")
            print(f"│  Model:  {model:<40s}│")
            print(f"│  Host:   {host:<40s}│")
            print(f"│  Error:  {str(last_error)[:40]:<40s}│")
            print("│                                                  │")
            print(f"│  Fallback: {fallback_model:<38s}│")
            print(f"│  Cost:     PAID API CALL                        │")
            print("└──────────────────────────────────────────────────┘")
            try:
                response = input("  Escalate to API? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                response = "n"

            if response in ("y", "yes"):
                self.log_activity(
                    category="api_escalation",
                    message=f"User approved API fallback to {fallback_model} after local failure: {task_type}",
                    level="WARNING",
                )
                self.logger.warning(f"API escalation approved for {task_type} -> {fallback_model}")
                raise RuntimeError(f"API_ESCALATION_APPROVED:{fallback_model}:{error_msg}")
            else:
                self.log_activity(
                    category="api_escalation",
                    message=f"User denied API fallback for {task_type}. Task aborted.",
                    level="INFO",
                )
                raise RuntimeError(error_msg)

        raise RuntimeError(error_msg)

    def ask_approval(self, action: str, details: str, machine: str = "local") -> bool:
        """Ask the user for approval before executing a destructive action.

        Prints a formatted approval request to the terminal.
        Returns True if user types 'y' or 'yes', False otherwise.
        In daemon mode (no terminal), EOFError returns False.
        """
        print()
        print("┌─ APPROVAL REQUIRED ─────────────────────────┐")
        print(f"│ Action:  {action:<36s}│")
        print(f"│ Details: {details:<36s}│")
        print(f"│ Machine: {machine:<36s}│")
        print("└─────────────────────────────────────────────┘")

        try:
            response = input("  Approve? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Denied (no input)")
            return False

        approved = response in ("y", "yes")
        self.logger.info(f"Approval {'GRANTED' if approved else 'DENIED'} for: {action}")
        self.log_activity(
            category="approval",
            message=f"{'APPROVED' if approved else 'DENIED'}: {action} - {details}",
            machine=machine,
            level="WARNING" if not approved else "INFO",
        )
        return approved

    def log_task(self, task: str, result: str, model: str, success: bool,
                 tokens_saved: bool = True, retries: int = 0):
        """Log a task execution to the agent_tasks table."""
        now = datetime.now().isoformat()
        self._db.execute(
            """INSERT INTO agent_tasks (agent, task, started, completed, model_used,
               success, tokens_saved, retries, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.agent_type, task, self.start_time.isoformat(), now, model,
             1 if success else 0, 1 if tokens_saved else 0, retries,
             result[:500] if result else ""),
        )
        self._db.commit()

    def save_metric(self, robot_serial: str, metric_name: str, value: float, units: str):
        """Save a performance metric to the database."""
        now = datetime.now().isoformat()
        self._db.execute(
            """INSERT INTO performance_metrics (robot_serial, timestamp, metric_name,
               value, units, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (robot_serial, now, metric_name, value, units, self.agent_type),
        )
        self._db.commit()

    def log_activity(self, category: str, message: str, machine: str = "",
                     robot: str = "", level: str = "INFO"):
        """Log an activity to the activity_log table."""
        now = datetime.now().isoformat()
        self._db.execute(
            """INSERT INTO activity_log (timestamp, category, machine, robot,
               agent, message, level)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now, category, machine, robot, self.agent_type, message, level),
        )
        self._db.commit()

    def get_model_info(self, task_type: str = None) -> dict:
        """Get model configuration for a task type."""
        task_type = task_type or self.agent_type
        conf = self.models_config.get(task_type, {})
        return {
            "model": conf.get("model", "unknown"),
            "host": conf.get("host", "unknown"),
            "port": conf.get("port", 11434),
            "is_local": conf.get("provider", "ollama") != "anthropic",
        }

    def execute_skill(self, skill_name: str, **kwargs) -> dict:
        """Execute a registered skill method by name.

        Looks up skill_name in the agent's _SKILL_REGISTRY dict and calls it.
        Returns a standardized result dict with success/result/error keys.
        """
        registry = getattr(self, "_SKILL_REGISTRY", {})
        if skill_name not in registry:
            return {"success": False, "result": None,
                    "error": f"Unknown skill '{skill_name}'. Available: {list(registry.keys())}"}
        try:
            result = registry[skill_name](**kwargs)
            self.log_activity("skill_execution", f"Executed: {skill_name}")
            return {"success": True, "result": result, "error": None}
        except Exception as e:
            self.logger.error(f"Skill '{skill_name}' failed: {e}")
            return {"success": False, "result": None, "error": str(e)}
