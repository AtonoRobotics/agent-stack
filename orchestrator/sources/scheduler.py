# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Cron scheduler event source.

Reads schedules.yml and emits events at configured intervals.
Uses a simple tick-based approach (checks every 60s if any schedule is due).
"""

import os
import asyncio
import logging
from datetime import datetime

import yaml

from orchestrator.bus import EventBus
from orchestrator.events import OrchestratorEvent, EventPriority

logger = logging.getLogger("orchestrator.sources.scheduler")

BASE_DIR = os.path.expanduser("~/agent-stack")


def _parse_cron(cron_expr: str) -> dict:
    """Parse a simple cron expression into a dict of constraints.

    Supports: minute hour day_of_month month day_of_week
    Uses * for any value.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {cron_expr}")

    fields = ["minute", "hour", "day", "month", "weekday"]
    result = {}
    for field, val in zip(fields, parts):
        if val == "*":
            result[field] = None
        elif "/" in val:
            # */6 means every 6 units
            _, step = val.split("/")
            result[field] = {"step": int(step)}
        else:
            result[field] = int(val)
    return result


def _cron_matches(cron: dict, now: datetime) -> bool:
    """Check if the current time matches a parsed cron expression."""
    checks = {
        "minute": now.minute,
        "hour": now.hour,
        "day": now.day,
        "month": now.month,
        "weekday": now.weekday(),  # 0=Monday
    }

    for field, constraint in cron.items():
        if constraint is None:
            continue
        current = checks[field]
        if isinstance(constraint, dict) and "step" in constraint:
            if current % constraint["step"] != 0:
                return False
        elif current != constraint:
            return False

    return True


class CronScheduler:
    """Emits events based on cron-like schedules from schedules.yml."""

    def __init__(self, bus: EventBus, config_path: str = "config/schedules.yml"):
        self.bus = bus
        self.config_path = os.path.join(BASE_DIR, config_path)
        self.schedules = self._load_schedules()
        self._last_fired: dict[str, str] = {}  # schedule_name → last fired minute

    def _load_schedules(self) -> dict:
        if not os.path.isfile(self.config_path):
            logger.warning(f"Schedule config not found: {self.config_path}")
            return {}
        with open(self.config_path) as f:
            data = yaml.safe_load(f)
        schedules = data.get("schedules", {})
        # Parse cron expressions
        for name, sched in schedules.items():
            sched["_cron"] = _parse_cron(sched["cron"])
        logger.info(f"Loaded {len(schedules)} schedules from {self.config_path}")
        return schedules

    async def run(self):
        """Check schedules every 60 seconds and emit matching events."""
        logger.info(f"CronScheduler started ({len(self.schedules)} schedules)")

        while True:
            now = datetime.now()
            minute_key = now.strftime("%Y-%m-%d %H:%M")

            for name, sched in self.schedules.items():
                # Skip if already fired this minute
                if self._last_fired.get(name) == minute_key:
                    continue

                if _cron_matches(sched["_cron"], now):
                    self._last_fired[name] = minute_key
                    priority = sched.get("priority", EventPriority.NORMAL)
                    task = sched.get("task", f"Scheduled task: {name}")

                    await self.bus.put(OrchestratorEvent(
                        priority=priority,
                        source="cron",
                        event_type="scheduled_task",
                        payload={
                            "schedule_name": name,
                            "task": task,
                        },
                    ))
                    logger.info(f"Fired schedule: {name}")

            # Sleep until next minute boundary
            now = datetime.now()
            sleep_seconds = 60 - now.second
            await asyncio.sleep(sleep_seconds)
