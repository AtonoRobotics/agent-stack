#!/bin/bash
set -e

echo "============================================="
echo "  Installing Alpha Robotics Agent Stack"
echo "============================================="
echo ""

# Create directory structure
echo "[1/7] Creating directory structure..."
mkdir -p ~/agent-stack/{config,agents,tools,skills,mcp,knowledge,templates,data,logs,dashboard,monitor}
mkdir -p ~/agent-stack/skills/{robotics,ai,deployment,monitoring,devops}
mkdir -p ~/agent-stack/knowledge/{hardware,software,lessons_learned,physics,workflows}
mkdir -p ~/agent-stack/dashboard/{frontend,backend}

# Install Python dependencies
echo "[2/7] Installing Python dependencies..."
pip install pyautogen "mcp[cli]" fastapi "uvicorn[standard]" \
    httpx rich textual python-dotenv pyyaml \
    aiohttp websockets aiosqlite \
    --break-system-packages --quiet 2>/dev/null || \
pip install pyautogen "mcp[cli]" fastapi "uvicorn[standard]" \
    httpx rich textual python-dotenv pyyaml \
    aiohttp websockets aiosqlite --quiet

# Initialize SQLite database
echo "[3/7] Initializing database..."
python3 ~/agent-stack/tools/database.py

# Make agent CLI executable
echo "[4/7] Setting up CLI..."
chmod +x ~/agent-stack/agent.py
if ! grep -q 'agent-stack' ~/.bashrc 2>/dev/null; then
    echo 'export PATH="$HOME/agent-stack:$PATH"' >> ~/.bashrc
fi

# Install systemd services
echo "[5/7] Installing systemd services..."
bash ~/agent-stack/install_services.sh

# Register MCP server with Claude Code
echo "[6/7] Registering MCP server..."
if command -v claude &>/dev/null; then
    claude mcp remove agent-stack 2>/dev/null || true
    claude mcp add agent-stack -- python3 ~/agent-stack/mcp/autogen_server.py
    echo "  MCP server registered with Claude Code"
else
    echo "  Claude Code CLI not found - skipping MCP registration"
    echo "  Run manually: claude mcp add agent-stack -- python3 ~/agent-stack/mcp/autogen_server.py"
fi

# Health check
echo "[7/7] Running health check..."
python3 -c "
import sys
sys.path.insert(0, '$HOME/agent-stack')
checks = []
try:
    from tools.database import DB_PATH
    import os
    checks.append(('Database', os.path.exists(DB_PATH)))
except Exception as e:
    checks.append(('Database', False))

try:
    from agents.base_agent import BaseAgent
    checks.append(('BaseAgent', True))
except Exception as e:
    checks.append(('BaseAgent', False))

try:
    import fastapi
    checks.append(('FastAPI', True))
except:
    checks.append(('FastAPI', False))

try:
    import mcp
    checks.append(('MCP SDK', True))
except:
    checks.append(('MCP SDK', False))

try:
    import rich
    checks.append(('Rich', True))
except:
    checks.append(('Rich', False))

for name, ok in checks:
    status = 'OK' if ok else 'FAIL'
    print(f'  {name}: {status}')
"

echo ""
echo "============================================="
echo "  ALPHA AGENT STACK INSTALLED"
echo "============================================="
echo "  Dashboard: http://localhost:8080"
echo "  CLI:       agent 'your task'"
echo "  Status:    agent --status"
echo "  MCP:       registered with Claude Code"
echo "============================================="
echo ""
echo "Run: source ~/.bashrc"
