"""AutoGen v0.4 agent teams.

Each agent type gets an AssistantAgent with tools and a RoundRobinGroupChat.
"""

import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination

from agents.clients import create_clients
from agents import tools


# ---------------------------------------------------------------------------
# Agent configurations
# ---------------------------------------------------------------------------

AGENT_CONFIGS = {
    "develop": {
        "client": "spark_coder",
        "tools": [tools.read_file, tools.write_file, tools.run_syntax_check, tools.git_status, tools.parse_urdf, tools.validate_urdf, tools.run_skill, tools.list_skills],
        "system_message": (
            "You are a senior robotics software developer. You write clean, correct Python code "
            "for the Alpha Robotics platform (Isaac Sim, ROS2, cuRobo). "
            "Use tools to read existing code before modifying. Validate syntax after writing. "
            "Use run_skill to generate domain-specific code (cuRobo configs, Isaac Sim scenes, etc.). "
            "When done, say TASK_COMPLETE."
        ),
    },
    "research": {
        "client": "spark_72b",
        "tools": [tools.search_knowledge_base, tools.search_docs, tools.list_docs, tools.read_file, tools.query_db, tools.query_agent_tasks],
        "system_message": (
            "You are a technical researcher for a robotics AI platform. "
            "Search the knowledge base and documentation to answer questions. "
            "Provide specific file paths and references. "
            "When done, say TASK_COMPLETE."
        ),
    },
    "sysadmin": {
        "client": "spark_72b",
        "tools": [tools.ssh_cmd, tools.docker_cmd, tools.systemctl_cmd, tools.git_status, tools.docker_images, tools.docker_logs, tools.ollama_models],
        "system_message": (
            "You are a Linux sysadmin managing a fleet of machines for a robotics company. "
            "Use tools to check status and manage services. Be cautious with destructive operations. "
            "The fleet includes: workstation (localhost), dgx-spark, agx-thor, orin-nano. "
            "When done, say TASK_COMPLETE."
        ),
    },
    "simulate": {
        "client": "spark_72b",
        "tools": [tools.check_sim_status, tools.run_isaac_sim, tools.read_file, tools.ssh_cmd, tools.parse_urdf, tools.validate_urdf, tools.dobot_connect_check, tools.run_skill, tools.list_skills],
        "system_message": (
            "You are an Isaac Sim and cuRobo simulation specialist. "
            "You manage simulation scenes, trajectory planning, and digital twins for the Dobot CR10 robot. "
            "Use run_skill to generate cuRobo configs, collision spheres, Isaac Sim scenes, and safety tests. "
            "When done, say TASK_COMPLETE."
        ),
    },
    "monitor": {
        "client": "local",
        "tools": [tools.check_fleet_health, tools.check_gpu_status, tools.check_ollama_status, tools.query_db, tools.query_fleet_health, tools.ollama_models, tools.dobot_connect_check, tools.log_agent_task],
        "system_message": (
            "You are a fleet monitoring agent. Check machine health, GPU status, and Ollama availability. "
            "Report issues clearly with severity. "
            "When done, say TASK_COMPLETE."
        ),
    },
    "cosmos": {
        "client": "spark_72b",
        "tools": [tools.check_resources, tools.read_file, tools.ssh_cmd],
        "system_message": (
            "You are a Cosmos world model specialist. You help with synthetic environment generation "
            "and world model inference on NVIDIA hardware. "
            "When done, say TASK_COMPLETE."
        ),
    },
    "groot": {
        "client": "spark_72b",
        "tools": [tools.check_resources, tools.read_file, tools.query_db],
        "system_message": (
            "You are a GR00T N1.6 training specialist. You help with Isaac Lab RL, dataset preparation, "
            "and policy evaluation for humanoid and robotic arm training. "
            "When done, say TASK_COMPLETE."
        ),
    },
    "fleet": {
        "client": "spark_72b",
        "tools": [tools.ssh_cmd, tools.docker_cmd, tools.systemctl_cmd, tools.check_fleet_health, tools.docker_images, tools.docker_logs, tools.ollama_models, tools.dobot_connect_check, tools.dobot_status],
        "system_message": (
            "You are a fleet operations agent. Execute commands across multiple machines. "
            "Report results per machine. Be cautious with destructive operations. "
            "When done, say TASK_COMPLETE."
        ),
    },
}


AGENT_TIMEOUT = 120  # seconds — kill hung agents after this


async def run_team(agent_type: str, task: str) -> str:
    """Run an AutoGen team for the given agent type and task.

    Creates a single-agent RoundRobinGroupChat with tools, runs the task,
    and returns the last text message from the agent. Enforces a timeout
    to prevent hung agents from blocking the MCP server.
    """
    if agent_type not in AGENT_CONFIGS:
        return f"Unknown agent type: {agent_type}. Available: {list(AGENT_CONFIGS.keys())}"

    config = AGENT_CONFIGS[agent_type]
    clients = create_clients()
    client = clients[config["client"]]

    try:
        agent = AssistantAgent(
            name=agent_type,
            model_client=client,
            tools=config["tools"],
            system_message=config["system_message"],
        )

        termination = MaxMessageTermination(20) | TextMentionTermination("TASK_COMPLETE")
        team = RoundRobinGroupChat([agent], termination_condition=termination)

        try:
            result = await asyncio.wait_for(
                team.run(task=task), timeout=AGENT_TIMEOUT
            )
        except asyncio.TimeoutError:
            return f"Agent '{agent_type}' timed out after {AGENT_TIMEOUT}s. Task: {task[:100]}"

        # Extract the last text message
        for msg in reversed(result.messages):
            if hasattr(msg, "content") and isinstance(msg.content, str):
                # Strip the TASK_COMPLETE marker from the response
                text = msg.content.replace("TASK_COMPLETE", "").strip()
                if text:
                    return text

        return "Agent completed but produced no text response."
    except Exception as e:
        return f"Agent error ({agent_type}): {e}"
    finally:
        await client.close()
