# AutoGen v0.4 Patterns

## Package

- `autogen-agentchat==0.7.5` (AutoGen v0.4 series)
- `autogen-ext` for model client extensions

## Architecture Used

### Model Client

```python
from autogen_ext.models.openai import OpenAIChatCompletionClient

client = OpenAIChatCompletionClient(
    model="qwen2.5:7b",
    api_key="ollama",          # Ollama ignores this but field is required
    base_url="http://localhost:11434/v1",
    model_info={
        "vision": False,
        "function_calling": True,
        "json_output": True,
        "structured_output": False,
        "family": "unknown",
    },
)
```

The `model_info` dict is required — AutoGen uses it to determine capability routing.

### Agent

```python
from autogen_agentchat.agents import AssistantAgent

agent = AssistantAgent(
    name="monitor",
    model_client=client,
    tools=[check_fleet_health, check_gpu_status],  # plain Python functions
    system_message="You are a monitoring agent. When done, say TASK_COMPLETE.",
)
```

Tools are plain Python functions with type hints and docstrings. AutoGen extracts the docstring as the tool description and uses type hints for parameter schemas.

### Team

```python
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination

termination = MaxMessageTermination(20) | TextMentionTermination("TASK_COMPLETE")
team = RoundRobinGroupChat([agent], termination_condition=termination)
result = await team.run(task="Check GPU status on workstation")
```

We use single-agent RoundRobinGroupChat (the simplest team pattern). The agent calls tools as needed and terminates when it says "TASK_COMPLETE" or hits 20 messages.

### Timeout Watchdog

```python
import asyncio

result = await asyncio.wait_for(team.run(task=task), timeout=120)
```

Always wrap `team.run()` in `asyncio.wait_for()` to prevent hung agents from blocking the MCP server.

## Important Notes

### TASK_COMPLETE Gotcha

The `TextMentionTermination("TASK_COMPLETE")` matches on ANY message in the chat, including the initial task message. Never include "TASK_COMPLETE" in the task prompt itself — it will terminate the team immediately.

### Tool Function Requirements

- Must take typed parameters
- Must return a string
- Should never raise exceptions (catch and return error strings)
- Must have a docstring (used as tool description by AutoGen)

### Client Cleanup

Always close the client after use:

```python
try:
    result = await team.run(task=task)
finally:
    await client.close()
```

### Message Types

The result contains these message types:
- `TextMessage` — user task or agent text response
- `ToolCallRequestEvent` — agent requesting a tool call
- `ToolCallExecutionEvent` — tool execution result
- `ToolCallSummaryMessage` — summarized tool output

### Ollama Specifics

- `api_key="ollama"` — required by the client but ignored by Ollama
- `base_url` must point to `/v1` endpoint (OpenAI-compatible API)
- Local model (qwen2.5:7b) on port 11434
- DGX Spark models (qwen2.5:72b, qwen2.5-coder:32b) on spark-2b53.local:11434
- ~300ms RTT to DGX Spark via Tailscale

## Files

- `agents/clients.py` — Client factory (`create_clients()`)
- `agents/tools.py` — All tool functions
- `agents/teams.py` — Agent configs and `run_team()`
- `config/models.yml` — Model host/port configuration
