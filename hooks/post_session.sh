#!/usr/bin/env bash
# Post-session hook — runs tests and updates state after Claude Code session.
# Run: bash ~/agent-stack/hooks/post_session.sh

set -e

echo "=== Post-Session Validation ==="

# Run sprint tests
SPRINT_TESTS="$HOME/mission-control/scripts/run_sprint_tests.py"
if [ -f "$SPRINT_TESTS" ]; then
    cd "$HOME/mission-control"
    echo "Running sprint tests..."
    python "$SPRINT_TESTS" || {
        echo "WARNING: Sprint tests had failures"
    }
else
    echo "No sprint test runner found — skipping."
fi

# Verify agent-stack imports
echo ""
echo "=== Agent Stack Health ==="
cd "$HOME/agent-stack"
python -c "
from agents.tools import check_fleet_health
from agents.teams import run_team, AGENT_CONFIGS
from skills import list_skills, SKILL_REGISTRY
print(f'Agents: {len(AGENT_CONFIGS)} configs OK')
print(f'Skills: {len(SKILL_REGISTRY)} skills OK')
print('All imports: OK')
" || echo "WARNING: Agent stack import errors"

# Dashboard health
echo ""
HEALTH=$(curl -sf http://localhost:8080/api/health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "Dashboard: OK"
else
    echo "Dashboard: NOT RESPONDING"
fi

echo ""
echo "Post-session check complete."
echo "Remember to:"
echo "  1. Update state/project_state.json with changes"
echo "  2. Append session summary to state/decisions_log.md"
echo "  3. Commit if needed: git add -A && git commit"
