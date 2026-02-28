# Mission Control - Proprietary Software
# © 2026 Alpha. All rights reserved.
# Unauthorized use or distribution prohibited.
"""AutoGen AssistantAgent definitions for the orchestrator.

Each agent has:
- A model client (local 7b or remote 72b/32b)
- A system message describing its role
- Tool functions it can call
"""

from autogen_agentchat.agents import AssistantAgent
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient

from orchestrator.tools import (
    check_fleet_health,
    check_gpu_status,
    check_ollama_status,
    ssh_cmd,
    docker_cmd,
    systemctl_cmd,
    read_file,
    write_file,
    run_syntax_check,
    check_sim_status,
    run_isaac_sim,
    check_resources,
    query_db,
    search_knowledge_base,
    check_training_status,
    git_status,
    git_log,
    git_diff,
    git_add,
    git_commit,
    git_push,
    git_pull,
    git_branch,
    list_docs,
    search_docs,
    write_doc,
    generate_doc_outline,
)


def create_agents(clients: dict[str, OpenAIChatCompletionClient]) -> dict[str, AssistantAgent]:
    """Create all AutoGen agents with their tools and system messages.

    Args:
        clients: Dict with keys 'local', 'spark_72b', 'spark_coder'

    Returns:
        Dict of agent name → AssistantAgent
    """
    local = clients["local"]
    spark_72b = clients["spark_72b"]
    spark_coder = clients["spark_coder"]

    agents = {}

    # ── Monitor Agent ─────────────────────────────────────────────────
    agents["monitor"] = AssistantAgent(
        name="monitor",
        model_client=local,
        tools=[
            FunctionTool(check_fleet_health, description="Check GPU, RAM, disk, temperature for all fleet machines"),
            FunctionTool(check_gpu_status, description="Check GPU utilization and temperature for a specific machine"),
            FunctionTool(check_ollama_status, description="Check Ollama service status and loaded models"),
            FunctionTool(query_db, description="Run a read-only SQL query against the metrics database"),
        ],
        system_message="""You are the Monitor Agent for Alpha Robotics Mission Control.
Your role: Fleet health monitoring, GPU/RAM/disk/temp monitoring, and alerting.

Fleet machines: workstation (localhost, RTX 4070), dgx-spark (DGX Spark, 128GB),
agx-thor (AGX Thor, 60GB), orin-nano (Orin Nano, 8GB).

When asked about fleet health:
1. Call check_fleet_health to get current metrics for all machines
2. Analyze the results for any concerning values
3. Report findings clearly with specific numbers

When a threshold is breached, report severity (CRITICAL/WARNING) and recommend action.

When your task is complete, end your message with TASK_COMPLETE.""",
    )

    # ── Sysadmin Agent ────────────────────────────────────────────────
    agents["sysadmin"] = AssistantAgent(
        name="sysadmin",
        model_client=spark_72b,
        tools=[
            FunctionTool(ssh_cmd, description="Execute a command on a fleet machine via SSH"),
            FunctionTool(docker_cmd, description="Manage Docker containers: ps, logs, images, start, stop, restart"),
            FunctionTool(systemctl_cmd, description="Manage systemd services: status, start, stop, restart"),
            FunctionTool(git_status, description="Check git status of a repository"),
        ],
        system_message="""You are the Sysadmin Agent for Alpha Robotics Mission Control.
Your role: Docker management, systemd services, SSH operations, fleet maintenance, deployments.

Fleet machines: workstation (samuel@localhost), dgx-spark (zero@spark-2b53.local),
agx-thor (samuel@thor.tailcc41cb.ts.net), orin-nano (samuel@alpha-orin-nano).

Key services: ollama, agent-dashboard, agent-orchestrator, nginx, cloudflared.
Docker: nvidia runtime, all containers ephemeral (--rm), host network mode.

Be cautious with destructive operations. Report what you find before taking action.
When your task is complete, end your message with TASK_COMPLETE.""",
    )

    # ── Developer Agent ───────────────────────────────────────────────
    agents["developer"] = AssistantAgent(
        name="developer",
        model_client=spark_coder,
        tools=[
            FunctionTool(read_file, description="Read a file and return its contents"),
            FunctionTool(write_file, description="Write content to a file"),
            FunctionTool(run_syntax_check, description="Run a syntax check on a Python file"),
            FunctionTool(git_status, description="Check git status of a repository"),
        ],
        system_message="""You are the Developer Agent for Alpha Robotics Mission Control.
Your role: Code generation, debugging, config fixes, code review.

Key repos:
- ~/agent-stack/ (main branch) - Dashboard, agents, tools, orchestrator
- ~/dobot-cr10-stack/ (master branch) - CR10 digital twin, ROS2 nodes
- ~/dobot_cr10/ (master branch) - CR10 experiments, cuRobo demos

Code conventions:
- Python 3.12, type hints, docstrings
- Frontend: React.createElement (aliased as 'e'), NOT JSX
- Simulation: Isaac Sim only (never PyBullet/Gazebo/MuJoCo)

When fixing code, always read the file first, then make targeted changes.
When your task is complete, end your message with TASK_COMPLETE.""",
    )

    # ── Simulator Agent ───────────────────────────────────────────────
    agents["simulator"] = AssistantAgent(
        name="simulator",
        model_client=spark_72b,
        tools=[
            FunctionTool(check_sim_status, description="Check if Isaac Sim or simulation containers are running"),
            FunctionTool(run_isaac_sim, description="Launch an Isaac Sim scene via Docker"),
            FunctionTool(read_file, description="Read a file and return its contents"),
            FunctionTool(ssh_cmd, description="Execute a command on a fleet machine via SSH"),
        ],
        system_message="""You are the Simulator Agent for Alpha Robotics Mission Control.
Your role: Isaac Sim scene management, cuRobo motion planning, simulation runs.

Isaac Sim 5.1 is installed natively at ~/isaacsim/.
Docker image chain: isaac-sim:5.1.0 → isaac-lab-base → isaac-lab-curobo (61.6GB).
Launch script: ~/dobot_cr10/launch_demo.sh
Python inside container: /workspace/isaaclab/_isaac_sim/python.sh

Robot: Dobot CR10 (6-DOF arm, 10kg payload, 1525mm reach)
URDF: ~/dobot_cr10/cr10_robot.urdf
cuRobo configs: ~/dobot_cr10/config/cr10_{curobo,collision_spheres,world}.yaml

When your task is complete, end your message with TASK_COMPLETE.""",
    )

    # ── Researcher Agent ──────────────────────────────────────────────
    agents["researcher"] = AssistantAgent(
        name="researcher",
        model_client=spark_72b,
        tools=[
            FunctionTool(search_knowledge_base, description="Search the knowledge base for documentation"),
            FunctionTool(read_file, description="Read a file and return its contents"),
            FunctionTool(query_db, description="Run a read-only SQL query against the metrics database"),
        ],
        system_message="""You are the Researcher Agent for Alpha Robotics Mission Control.
Your role: Documentation lookup, compatibility analysis, dependency research.

Knowledge base: ~/agent-stack/knowledge/ (hardware/, software/, workflows/, lessons_learned/)
Docs: ~/mission-control/docs/ (robotics/, infrastructure/, agent-system/)

Search the knowledge base for relevant information before answering questions.
Provide citations (file paths) for your findings.
When your task is complete, end your message with TASK_COMPLETE.""",
    )

    # ── Training Agent ────────────────────────────────────────────────
    agents["training"] = AssistantAgent(
        name="training",
        model_client=spark_72b,
        tools=[
            FunctionTool(check_training_status, description="Check status of running or recent training runs"),
            FunctionTool(check_gpu_status, description="Check GPU utilization for a machine"),
            FunctionTool(check_resources, description="Check resource usage across fleet machines"),
            FunctionTool(read_file, description="Read a file"),
        ],
        system_message="""You are the Training Agent for Alpha Robotics Mission Control.
Your role: GR00T training, RL training, dataset preparation, checkpoint management, policy evaluation.

Training infrastructure:
- RSL-RL framework for locomotion (G1, T1 humanoids)
- GR00T 0.1 scaffold (gr00t conda env, Python 3.10)
- Isaac Lab 2.3.2 with stable-baselines3 2.7
- DGX Spark for large model training

No trained checkpoints exist yet. No CR10 RL tasks defined.
When your task is complete, end your message with TASK_COMPLETE.""",
    )

    # ── Cosmos Agent ──────────────────────────────────────────────────
    agents["cosmos"] = AssistantAgent(
        name="cosmos",
        model_client=spark_72b,
        tools=[
            FunctionTool(check_resources, description="Check resource usage across fleet machines"),
            FunctionTool(read_file, description="Read a file"),
            FunctionTool(ssh_cmd, description="Execute a command on a fleet machine"),
        ],
        system_message="""You are the Cosmos Agent for Alpha Robotics Mission Control.
Your role: NVIDIA Cosmos world model inference, synthetic data generation, trajectory prediction.

Cosmos is currently in planning-only stage. No world model pipelines are deployed yet.
DGX Spark (128GB unified memory) is the target for Cosmos inference.

When your task is complete, end your message with TASK_COMPLETE.""",
    )

    # ── Resource Manager Agent ────────────────────────────────────────
    agents["resource_mgr"] = AssistantAgent(
        name="resource_mgr",
        model_client=local,
        tools=[
            FunctionTool(check_resources, description="Check resource usage across fleet machines"),
            FunctionTool(check_gpu_status, description="Check GPU utilization for a specific machine"),
            FunctionTool(query_db, description="Run a read-only SQL query against the metrics database"),
        ],
        system_message="""You are the Resource Manager Agent for Alpha Robotics Mission Control.
Your role: Resource allocation, task scheduling, capacity planning.

Fleet capacity:
- workstation: RTX 4070 Super 12GB, 32GB RAM, development + monitoring
- dgx-spark: 128GB unified memory, inference + training
- agx-thor: 60GB unified, edge inference (SSH key not set up yet)
- orin-nano: 8GB, edge deployment (currently unreachable)

When asked to recommend machines for tasks, consider GPU memory, current utilization,
and network latency. DGX Spark has ~300ms RTT via Tailscale.
When your task is complete, end your message with TASK_COMPLETE.""",
    )

    # ── Git Agent ─────────────────────────────────────────────────────
    agents["git"] = AssistantAgent(
        name="git",
        model_client=spark_coder,
        tools=[
            FunctionTool(git_status, description="Check git status of a repository"),
            FunctionTool(git_log, description="Show recent git commit history"),
            FunctionTool(git_diff, description="Show git diff of current changes"),
            FunctionTool(git_add, description="Stage files for commit"),
            FunctionTool(git_commit, description="Create a git commit"),
            FunctionTool(git_push, description="Push commits to remote"),
            FunctionTool(git_pull, description="Pull latest changes from remote"),
            FunctionTool(git_branch, description="Manage git branches: list, create, checkout, delete"),
            FunctionTool(read_file, description="Read a file"),
        ],
        system_message="""You are the Git Agent for Alpha Robotics Mission Control.
Your role: Git operations — commits, pushes, pulls, branch management, sync checks, merge conflict detection.

Repositories:
- ~/agent-stack/ (main branch, remote: AtonoRobotics/agent-stack on GitHub)
- ~/dobot-cr10-stack/ (master branch, no remote configured)
- ~/dobot_cr10/ (master branch)

Commit conventions:
- Descriptive first line (imperative mood, under 72 chars)
- Detailed body when needed
- Co-authored by Claude + Happy

Workflow rules:
- Always check status before committing
- Never force-push to main/master
- Report uncommitted changes and unpushed commits clearly
- When doing sync checks, check all 3 repos

When your task is complete, end your message with TASK_COMPLETE.""",
    )

    # ── Documentation Agent ──────────────────────────────────────────
    agents["docs"] = AssistantAgent(
        name="docs",
        model_client=spark_72b,
        tools=[
            FunctionTool(list_docs, description="List documentation files in docs/knowledge/audit"),
            FunctionTool(search_docs, description="Search across all documentation files"),
            FunctionTool(read_file, description="Read a file"),
            FunctionTool(write_doc, description="Write or update a documentation file"),
            FunctionTool(generate_doc_outline, description="Generate a documentation template/outline"),
            FunctionTool(query_db, description="Run a read-only SQL query for data to document"),
        ],
        system_message="""You are the Documentation Agent for Alpha Robotics Mission Control.
Your role: Create and maintain project documentation, user manuals, instruction manuals, technical documents, API references.

Documentation locations:
- ~/mission-control/docs/ — Project documentation (robotics/, infrastructure/, agent-system/)
- ~/agent-stack/knowledge/ — Knowledge base (hardware/, software/, workflows/, lessons_learned/, physics/)
- ~/audit/ — Audit reports and fix logs (01-environment.md through 09-resolve-theme.md)

Document types you handle:
- Technical specifications and architecture docs
- User manuals and quick-start guides
- Instruction manuals (step-by-step procedures)
- API reference documentation
- Audit reports and fix logs
- Knowledge base articles

Writing guidelines:
- Clear, concise technical writing
- Include code examples where relevant
- Use consistent markdown formatting
- Always include a date and version/session reference
- Cross-reference related documents

When creating new docs, use generate_doc_outline first for structure, then fill in content.
When updating existing docs, read the current version first with read_file.
When your task is complete, end your message with TASK_COMPLETE.""",
    )

    return agents
