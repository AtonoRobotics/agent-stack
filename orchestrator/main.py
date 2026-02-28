#!/usr/bin/env python3
# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Main entry point for the autonomous agent orchestrator.

Usage:
    # Test mode — process a single task
    python -m orchestrator.main --test "Check fleet health"

    # Autonomous mode — start event loop (Phase 2+)
    python -m orchestrator.main
"""

import os
import sys
import asyncio
import argparse
import logging
import signal
from datetime import datetime

sys.path.insert(0, os.path.expanduser("~/agent-stack"))

from orchestrator.clients import create_clients
from orchestrator.agents import create_agents
from orchestrator.team import create_team

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.expanduser("~/agent-stack/logs/orchestrator.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("orchestrator")


async def run_test(task_text: str):
    """Run a single task through the agent team (test mode)."""
    logger.info(f"Test mode: processing task: {task_text}")
    print(f"\n{'='*60}")
    print(f"ORCHESTRATOR TEST MODE")
    print(f"Task: {task_text}")
    print(f"{'='*60}\n")

    # Create clients and agents
    print("Creating model clients...")
    clients = create_clients()
    print("Creating agents...")
    agents = create_agents(clients)
    print("Creating supervisor team...")
    team = create_team(agents, clients["spark_72b"])

    print(f"\nProcessing task...\n{'-'*60}")

    try:
        result = await asyncio.wait_for(
            team.run(task=task_text),
            timeout=300,  # 5 minute max
        )

        print(f"\n{'-'*60}")
        print("CONVERSATION LOG:")
        print(f"{'-'*60}")
        for msg in result.messages:
            source = getattr(msg, "source", "system")
            content = msg.content if hasattr(msg, "content") else str(msg)
            # Truncate long tool results
            if isinstance(content, list):
                content = "\n".join(
                    str(item.content) if hasattr(item, "content") else str(item)
                    for item in content
                )
            if isinstance(content, str) and len(content) > 1000:
                content = content[:1000] + "... (truncated)"
            print(f"\n[{source}]: {content}")

        print(f"\n{'='*60}")
        print(f"Task completed. {len(result.messages)} messages exchanged.")
        print(f"Stop reason: {result.stop_reason}")
        print(f"{'='*60}")

    except asyncio.TimeoutError:
        print("\nERROR: Task timed out after 5 minutes")
    except Exception as e:
        logger.error(f"Error processing task: {e}", exc_info=True)
        print(f"\nERROR: {e}")


async def run_autonomous():
    """Run the autonomous event-driven orchestrator (Phase 2+)."""
    logger.info("Starting autonomous orchestrator...")
    print(f"\n{'='*60}")
    print("MISSION CONTROL ORCHESTRATOR")
    print(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Create clients (shared across all team instances)
    clients = create_clients()

    def make_team():
        """Create a fresh agent team for each event (AutoGen teams are single-use)."""
        agents = create_agents(clients)
        return create_team(agents, clients["spark_72b"])

    # Import event system (Phase 2)
    try:
        from orchestrator.bus import EventBus
        from orchestrator.persistence import EventStore
        from orchestrator.events import OrchestratorEvent
    except ImportError:
        logger.error("Event system not available. Run with --test for test mode.")
        print("ERROR: Event system (Phase 2) not yet implemented.")
        print("Use --test mode: python -m orchestrator.main --test \"your task\"")
        return

    # Initialize event bus and persistence
    bus = EventBus(max_size=500)
    store = EventStore()
    await store.init()

    # Load and start event sources
    sources = []
    try:
        from orchestrator.sources.metrics import MetricsWatcher
        sources.append(MetricsWatcher(bus, interval=60))
    except ImportError:
        logger.warning("MetricsWatcher not available")

    try:
        from orchestrator.sources.scheduler import CronScheduler
        sources.append(CronScheduler(bus, config_path="config/schedules.yml"))
    except ImportError:
        logger.warning("CronScheduler not available")

    try:
        from orchestrator.sources.filesystem import FileSystemWatcher
        sources.append(FileSystemWatcher(bus, paths=["config/", "data/"]))
    except ImportError:
        logger.warning("FileSystemWatcher not available")

    for source in sources:
        asyncio.create_task(source.run())

    logger.info(f"Started {len(sources)} event sources")
    print(f"Event sources active: {len(sources)}")

    # Process events
    semaphore = asyncio.Semaphore(3)  # Max 3 concurrent team runs
    shutdown = asyncio.Event()

    def handle_signal(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    async def process_event(event: OrchestratorEvent):
        async with semaphore:
            task_text = event.to_task_text()
            logger.info(f"Processing event {event.id[:8]}: {task_text[:100]}")
            await store.log_event(event, status="processing")

            try:
                team = make_team()  # Fresh team per event (AutoGen teams are single-use)
                result = await asyncio.wait_for(
                    team.run(task=task_text),
                    timeout=300,
                )
                # Extract conversation for logging
                messages = []
                agents_involved = set()
                for msg in result.messages:
                    source = getattr(msg, "source", "system")
                    content = msg.content if hasattr(msg, "content") else str(msg)
                    if isinstance(content, list):
                        content = "\n".join(str(c) for c in content)
                    messages.append({"agent": source, "content": str(content)[:2000]})
                    agents_involved.add(source)

                await store.log_event(
                    event,
                    status="completed",
                    assigned_agents=list(agents_involved),
                    messages=messages,
                    result=str(result.messages[-1].content)[:500] if result.messages else "",
                )
                logger.info(f"Event {event.id[:8]} completed ({len(result.messages)} messages)")

            except asyncio.TimeoutError:
                await store.log_event(event, status="timeout")
                logger.warning(f"Event {event.id[:8]} timed out")
            except Exception as e:
                await store.log_event(event, status="failed", result=str(e)[:500])
                logger.error(f"Event {event.id[:8]} failed: {e}")

    # Main event loop
    while not shutdown.is_set():
        try:
            event = await asyncio.wait_for(bus.get(), timeout=1.0)
            asyncio.create_task(process_event(event))
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.error(f"Event loop error: {e}")
            await asyncio.sleep(1)

    logger.info("Orchestrator shutdown complete")


def main():
    parser = argparse.ArgumentParser(description="Mission Control Agent Orchestrator")
    parser.add_argument("--test", type=str, help="Run a single test task")
    args = parser.parse_args()

    os.makedirs(os.path.expanduser("~/agent-stack/logs"), exist_ok=True)

    if args.test:
        asyncio.run(run_test(args.test))
    else:
        asyncio.run(run_autonomous())


if __name__ == "__main__":
    main()
