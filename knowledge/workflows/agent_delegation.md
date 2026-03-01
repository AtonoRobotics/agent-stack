# Agent Delegation Protocol

## Core Principle

Claude Code is an ORCHESTRATOR, not an executor. All work that can be handled by a local Ollama-powered agent MUST be delegated before Claude Code does it directly.

## MCP Tools

The `agent-stack` MCP server exposes 12 tools via stdio transport:

### Agent Tools

| Tool | Model | Host | Use For |
|------|-------|------|---------|
| `agent__develop` | qwen2.5-coder:32b | DGX Spark | Code generation, debugging, refactoring |
| `agent__research` | qwen2.5:72b | DGX Spark | Documentation lookup, dependency resolution |
| `agent__sysadmin` | qwen2.5:72b | DGX Spark | Docker, systemd, fleet management, git ops |
| `agent__simulate` | qwen2.5:72b | DGX Spark | Isaac Sim scenes, cuRobo planning, digital twins |
| `agent__cosmos` | qwen2.5:72b | DGX Spark | Cosmos world model, synthetic environments |
| `agent__groot` | qwen2.5:72b | DGX Spark | GR00T training, Isaac Lab RL, dataset prep |
| `agent__monitor` | qwen2.5:7b | localhost | Fleet health, GPU, Ollama, service status |
| `agent__fleet` | qwen2.5:72b | DGX Spark | Multi-machine command execution |
| `agent__status` | — | — | Stack status snapshot (no LLM needed) |

### Orchestrator Tools

| Tool | Purpose |
|------|---------|
| `orchestrator__trigger` | Queue a task for autonomous agent processing |
| `orchestrator__status` | Check event queue and agent status |
| `orchestrator__events` | View recent event outcomes |

## How It Works

1. Claude Code receives a user request
2. Claude Code calls the appropriate MCP agent tool with a `task` string
3. MCP server creates an AutoGen `AssistantAgent` with relevant tools
4. Agent runs on local Ollama (FREE), calls tool functions, generates response
5. Response returns to Claude Code via MCP
6. Claude Code presents result to user

## Tool Parameters

All agent tools accept:
- `task` (required): What the agent should do
- `context` (optional): Additional context to append

Exception: `agent__monitor` has `task` only (no context).
Exception: `agent__fleet` adds `machines` parameter (default "all").

## When to Delegate vs. Handle Directly

**ALWAYS delegate:**
- Fleet health checks → `agent__monitor`
- Docker/systemd commands → `agent__sysadmin`
- Code generation → `agent__develop`
- Documentation lookup → `agent__research`
- Simulation tasks → `agent__simulate`

**Claude Code handles directly:**
- Multi-file edits requiring user approval
- Interactive debugging with human judgment
- Dashboard frontend (React/CSS)
- Git commits (require user confirmation)
- Governance file updates (CLAUDE.md, .rules/)
- Tasks agents failed at twice

## Orchestrator Events

Use `orchestrator__trigger` for tasks that should run autonomously:
- Writes event to SQLite `orchestrator_events` table
- Touches `data/mcp_trigger.flag` for FileSystemWatcher
- Event processed by AutoGen SelectorGroupChat with supervisor routing
- Priority: 0=critical, 50=normal, 100=low

## Timeouts

- Agent team: 120s timeout (prevents hung agents)
- MCP tool call: 180s timeout (outer safety net)
- Individual SSH commands: 15-30s timeout
