# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""Supervisor team using AutoGen SelectorGroupChat.

The supervisor (qwen2.5:72b) routes tasks to specialist agents.
Agents communicate via natural language messages within the group chat.
"""

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_ext.models.openai import OpenAIChatCompletionClient


SELECTOR_PROMPT = """Read the conversation and select the SINGLE BEST agent to handle the next step.
Reply with ONLY the agent name, nothing else.

Agents:
- monitor: Fleet health, GPU/RAM/disk/temp metrics, alerting, Ollama status
- sysadmin: Docker, systemd, SSH, service restarts, fleet maintenance
- developer: Code generation, debugging, config fixes
- simulator: Isaac Sim, cuRobo, simulation runs
- researcher: Documentation lookup, compatibility, dependencies
- training: GR00T, RL training, datasets
- cosmos: World models, synthetic data
- resource_mgr: Resource allocation, capacity planning
- git: Git commits, pushes, pulls, branches, sync checks, repo management
- docs: Documentation writing, user manuals, technical docs, audit reports

IMPORTANT: Respond with ONLY one agent name from the list above. Do not explain your choice."""


def create_team(
    agents: dict[str, AssistantAgent],
    supervisor_client: OpenAIChatCompletionClient,
    max_messages: int = 12,
) -> SelectorGroupChat:
    """Create a SelectorGroupChat with all agents and the supervisor.

    Args:
        agents: Dict of agent name → AssistantAgent
        supervisor_client: Model client for the supervisor (routing decisions)
        max_messages: Maximum messages before forced termination

    Returns:
        A SelectorGroupChat team ready to process tasks
    """
    termination = (
        MaxMessageTermination(max_messages)
        | TextMentionTermination("TASK_COMPLETE")
    )

    participants = [
        agents["monitor"],
        agents["sysadmin"],
        agents["developer"],
        agents["simulator"],
        agents["researcher"],
        agents["training"],
        agents["cosmos"],
        agents["resource_mgr"],
        agents["git"],
        agents["docs"],
    ]

    team = SelectorGroupChat(
        participants=participants,
        model_client=supervisor_client,
        termination_condition=termination,
        selector_prompt=SELECTOR_PROMPT,
    )

    return team
