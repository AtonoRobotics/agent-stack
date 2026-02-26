#!/bin/bash
# Mission Control - Security Setup
# © 2026 Alpha. All rights reserved.
set -euo pipefail

STACK_DIR="$HOME/agent-stack"
SSL_DIR="/etc/nginx/ssl"
PYTHON_BIN=$(which python3)

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Mission Control - Security Setup           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# 1. Install nginx
echo "[1/7] Checking nginx..."
if ! command -v nginx &>/dev/null; then
    echo "  Installing nginx..."
    sudo apt-get update -qq && sudo apt-get install -y -qq nginx
else
    echo "  nginx already installed"
fi

# 2. Generate self-signed SSL certificate
echo "[2/7] Generating SSL certificate..."
sudo mkdir -p "$SSL_DIR"
if [ ! -f "$SSL_DIR/mission-control.crt" ]; then
    sudo openssl req -x509 -nodes -days 3650 \
        -newkey rsa:2048 \
        -keyout "$SSL_DIR/mission-control.key" \
        -out "$SSL_DIR/mission-control.crt" \
        -subj "/C=US/O=Alpha/CN=mission-control" 2>/dev/null
    echo "  Certificate generated (10-year self-signed)"
else
    echo "  Certificate already exists"
fi

# 3. Deploy nginx config
echo "[3/7] Deploying nginx configuration..."
sudo cp "$STACK_DIR/dashboard/nginx/mission-control" /etc/nginx/sites-available/mission-control
sudo ln -sf /etc/nginx/sites-available/mission-control /etc/nginx/sites-enabled/mission-control
sudo rm -f /etc/nginx/sites-enabled/default
if sudo nginx -t 2>/dev/null; then
    echo "  nginx config valid"
else
    echo "  ERROR: nginx config invalid!"
    sudo nginx -t
    exit 1
fi

# 4. Generate secrets
echo "[4/7] Generating secrets..."
$PYTHON_BIN -c "
import sys; sys.path.insert(0, '$STACK_DIR')
from dashboard.backend.auth import AuthManager
am = AuthManager()
print('  Secrets generated')
"

# 5. Create default admin user
echo "[5/7] Creating default admin user..."
CREDS=$($PYTHON_BIN << 'PYEOF'
import sys, secrets
sys.path.insert(0, "$HOME/agent-stack".replace("$HOME", __import__("os").path.expanduser("~")))
sys.path.insert(0, __import__("os").path.expanduser("~/agent-stack"))
from dashboard.backend.auth import AuthManager
am = AuthManager()
password = secrets.token_urlsafe(16)
try:
    am.create_user("admin", password, "admin", created_by="system")
    print(f"ADMIN_PASS={password}")
except ValueError:
    print("ADMIN_PASS=EXISTING")
PYEOF
)
ADMIN_PASS=$(echo "$CREDS" | grep ADMIN_PASS | cut -d= -f2)
if [ "$ADMIN_PASS" = "EXISTING" ]; then
    echo "  Admin user already exists"
else
    echo "  Admin user created"
fi

# 6. Generate agent API key
echo "[6/7] Generating agent API key..."
AGENT_KEY=$($PYTHON_BIN << 'PYEOF'
import sys
sys.path.insert(0, __import__("os").path.expanduser("~/agent-stack"))
from dashboard.backend.auth import AuthManager
am = AuthManager()
key = am.create_api_key("agent-cli", "operator", created_by="system")
print(key)
PYEOF
)

# 7. Restart services
echo "[7/7] Restarting services..."
sudo systemctl enable nginx
sudo systemctl restart nginx
systemctl --user restart agent-dashboard 2>/dev/null || true

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         MISSION CONTROL - CREDENTIALS                   ║"
echo "║         Save these - shown only once!                    ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "  URL:       https://localhost"
echo "  Username:  admin"
echo "  Password:  $ADMIN_PASS"
echo "  API Key:   $AGENT_KEY"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
