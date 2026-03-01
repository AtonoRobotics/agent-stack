#!/usr/bin/env bash
# Pre-session hook — validates governance files before Claude Code starts work.
# Run: bash ~/agent-stack/hooks/pre_session.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Pre-Session Validation ==="

# Run validate_session.py from mission-control (where symlinks live)
VALIDATE_SCRIPT="$HOME/mission-control/scripts/validate_session.py"
if [ -f "$VALIDATE_SCRIPT" ]; then
    cd "$HOME/mission-control"
    python "$VALIDATE_SCRIPT"
    echo ""
    echo "Session validation: PASSED"
else
    echo "WARNING: validate_session.py not found at $VALIDATE_SCRIPT"
    echo "Governance validation skipped."
fi

# Show current project state
STATE_FILE="$HOME/mission-control/state/project_state.json"
if [ -f "$STATE_FILE" ]; then
    echo ""
    echo "=== Current Project State ==="
    python -c "import json; d=json.load(open('$STATE_FILE')); print(json.dumps(d, indent=2))" 2>/dev/null || cat "$STATE_FILE"
fi

# Show current sprint
SPRINT_FILE="$HOME/mission-control/objectives/current_sprint.yaml"
if [ -f "$SPRINT_FILE" ]; then
    echo ""
    echo "=== Current Sprint ==="
    cat "$SPRINT_FILE"
fi

echo ""
echo "Pre-session check complete."
