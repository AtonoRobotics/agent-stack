#!/bin/bash
set -e

echo "Installing systemd user services..."

SVCDIR="$HOME/.config/systemd/user"
mkdir -p "$SVCDIR"
mkdir -p "$HOME/agent-stack/logs"

# Find the correct Python with our packages installed
PYTHON_BIN=$(which python3)
echo "Using Python: $PYTHON_BIN"

# Agent Monitor Service
cat > "$SVCDIR/agent-monitor.service" << EOF
[Unit]
Description=Alpha Agent Stack - Fleet Monitor
After=network.target

[Service]
Type=simple
ExecStart=${PYTHON_BIN} ${HOME}/agent-stack/agents/monitor.py
Restart=always
RestartSec=10
Environment=PATH=/usr/local/bin:/usr/bin:/bin:${HOME}/anaconda3/bin
StandardOutput=append:${HOME}/agent-stack/logs/monitor.log
StandardError=append:${HOME}/agent-stack/logs/monitor.err

[Install]
WantedBy=default.target
EOF

# Metrics Collector Service
cat > "$SVCDIR/agent-metrics.service" << EOF
[Unit]
Description=Alpha Agent Stack - Metrics Collector
After=network.target

[Service]
Type=simple
ExecStart=${PYTHON_BIN} ${HOME}/agent-stack/monitor/metrics_collector.py
Restart=always
RestartSec=30
Environment=PATH=/usr/local/bin:/usr/bin:/bin:${HOME}/anaconda3/bin
StandardOutput=append:${HOME}/agent-stack/logs/metrics.log
StandardError=append:${HOME}/agent-stack/logs/metrics.err

[Install]
WantedBy=default.target
EOF

# MCP Server Service
cat > "$SVCDIR/agent-mcp.service" << EOF
[Unit]
Description=Alpha Agent Stack - MCP Server
After=network.target

[Service]
Type=simple
ExecStart=${PYTHON_BIN} ${HOME}/agent-stack/mcp/autogen_server.py
Restart=always
RestartSec=5
Environment=PATH=/usr/local/bin:/usr/bin:/bin:${HOME}/anaconda3/bin
StandardOutput=append:${HOME}/agent-stack/logs/mcp.log
StandardError=append:${HOME}/agent-stack/logs/mcp.err

[Install]
WantedBy=default.target
EOF

# Dashboard Service
cat > "$SVCDIR/agent-dashboard.service" << EOF
[Unit]
Description=Alpha Agent Stack - Dashboard
After=network.target

[Service]
Type=simple
ExecStart=${PYTHON_BIN} -m uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 8080
WorkingDirectory=${HOME}/agent-stack
Restart=always
RestartSec=5
Environment=PATH=/usr/local/bin:/usr/bin:/bin:${HOME}/anaconda3/bin
StandardOutput=append:${HOME}/agent-stack/logs/dashboard.log
StandardError=append:${HOME}/agent-stack/logs/dashboard.err

[Install]
WantedBy=default.target
EOF

echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

echo "Enabling services..."
systemctl --user enable agent-monitor.service
systemctl --user enable agent-metrics.service
systemctl --user enable agent-mcp.service
systemctl --user enable agent-dashboard.service

echo "Starting dashboard..."
systemctl --user start agent-dashboard.service

echo "Services installed and dashboard started."
echo "  agent-monitor:   systemctl --user start agent-monitor"
echo "  agent-metrics:   systemctl --user start agent-metrics"
echo "  agent-mcp:       systemctl --user start agent-mcp"
echo "  agent-dashboard: http://localhost:8080"
