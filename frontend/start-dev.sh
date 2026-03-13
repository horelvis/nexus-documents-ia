#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Frontend Dev Startup — On-Premise (port 3001, HTTP, Turbopack)
# ──────────────────────────────────────────────────────────────
# Prevents common issues:
#   1. Stale next-server / node processes blocking port 3001
#   2. Turbo daemon with corrupted permissions
#   3. nginx pointing to HTTPS instead of HTTP (dev mode)
#
# Usage:
#   ./start-dev.sh          # foreground (Ctrl+C to stop)
#   ./start-dev.sh --bg     # background (logs to /tmp/nextjs-dev.log)
# ──────────────────────────────────────────────────────────────
set -e

PORT=3001
FRONTEND_DIR="/home/nexus/git/nexus-documents-ia/frontend"
APP_DIR="$FRONTEND_DIR/apps/on-premise"
LOG_FILE="/tmp/nextjs-dev.log"
NGINX_CONF="/home/nexus/git/nexus-documents-ia/backend/docker/nginx/tls-proxy.conf"

cd "$APP_DIR"

# ── 1. Kill anything on port 3001 ──────────────────────────────
PID=$(ss -tlnp 2>/dev/null | grep ":${PORT} " | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "$PID" ]; then
    echo "⚠ Port $PORT in use by PID $PID — killing..."
    kill "$PID" 2>/dev/null || true
    sleep 1
    # Force kill if still alive
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null || true
    echo "✓ Port $PORT freed"
fi

# ── 2. Clean Turbo daemon + stale caches ───────────────────────
npx turbo daemon stop 2>/dev/null || true
rm -rf "$FRONTEND_DIR/.turbo/daemon" 2>/dev/null || true

# ── 3. Ensure nginx points to HTTP (dev mode) ─────────────────
if [ -f "$NGINX_CONF" ]; then
    if grep -q 'proxy_pass https://172.18.0.1:3001' "$NGINX_CONF"; then
        echo "⚠ nginx points to HTTPS — switching to HTTP for dev..."
        sed -i 's|proxy_pass https://172.18.0.1:3001|proxy_pass http://172.18.0.1:3001|' "$NGINX_CONF"
        # Reload nginx if container is running
        if docker compose -f /home/nexus/git/nexus-documents-ia/backend/docker/docker-compose.yml \
           -f /home/nexus/git/nexus-documents-ia/backend/docker/docker-compose.onpremise.yml \
           exec -T tls-proxy nginx -s reload 2>/dev/null; then
            echo "✓ nginx reloaded (HTTP mode)"
        else
            echo "  nginx not running — config updated for next start"
        fi
    else
        echo "✓ nginx already in HTTP mode"
    fi
fi

# ── 4. Start Next.js dev server ────────────────────────────────
echo ""
echo "▶ Starting Next.js dev on http://0.0.0.0:$PORT (Turbopack)"
echo ""

if [ "$1" = "--bg" ]; then
    nohup npx next dev --turbo --hostname 0.0.0.0 --port "$PORT" > "$LOG_FILE" 2>&1 &
    DEV_PID=$!
    sleep 3
    if kill -0 "$DEV_PID" 2>/dev/null; then
        echo "✓ Running in background (PID $DEV_PID)"
        echo "  Logs: tail -f $LOG_FILE"
        echo "  Stop: kill $DEV_PID"
    else
        echo "✗ Failed to start — check $LOG_FILE"
        exit 1
    fi
else
    exec npx next dev --turbo --hostname 0.0.0.0 --port "$PORT"
fi
