#!/bin/bash

echo " Starting ADK Web UI with persistent session storage..."

# Load environment variables from root .env into the shell so adk web inherits them
if [ -f "$(dirname "$0")/.env" ]; then
    set -a
    source "$(dirname "$0")/.env"
    set +a
    echo " Loaded .env from project root"
else
    echo "  No .env found at project root"
fi

# Check ADC when using Vertex AI mode
if [ "${GOOGLE_GENAI_USE_VERTEXAI}" = "TRUE" ]; then
    if ! gcloud auth application-default print-access-token > /dev/null 2>&1; then
        echo "ERROR: Vertex AI mode requires Application Default Credentials."
        echo "Run: gcloud auth application-default login"
        exit 1
    fi
    echo "ADC: configured"
fi

# Start MCP Toolbox server in background (required for g_agents_mcp)
TOOLBOX_BIN="$(dirname "$0")/mcp_tool_box/toolbox"
TOOLBOX_CFG="$(dirname "$0")/mcp_tool_box/trip_tools.yaml"
if [ -f "$TOOLBOX_BIN" ] && [ -f "$TOOLBOX_CFG" ]; then
    # Kill any stale instance on port 7001
    lsof -ti tcp:7001 | xargs kill -9 2>/dev/null || true
    "$TOOLBOX_BIN" --config "$TOOLBOX_CFG" --port 7001 &
    TOOLBOX_PID=$!
    echo " MCP Toolbox started (pid $TOOLBOX_PID) on port 7001"
    sleep 1  # give it a moment to bind before adk web loads the agent
else
    echo "  MCP Toolbox binary or config not found — g_agents_mcp will be skipped"
fi

# Create sessions directory if it doesn't exist
SESSIONS_DIR="$HOME/.adk/sessions"
mkdir -p "$SESSIONS_DIR"

# SQLite database file for session persistence
DB_FILE="$SESSIONS_DIR/adk_web_sessions.db"
SESSION_URI="sqlite:///$DB_FILE"

echo " Session database: $DB_FILE"
echo " Session URI: $SESSION_URI"

# Start ADK Web UI with persistent sessions
echo " Starting ADK Web UI on http://localhost:8080..."
echo " Evaluation results and user preferences will now persist across requests!"

adk web \
    --session_service_uri="$SESSION_URI" \
    --host=127.0.0.1 \
    --port=8080 \
    --log_level=info \
    --reload \
    .

echo " ADK Web UI stopped"

# Shut down MCP Toolbox if we started it
if [ -n "${TOOLBOX_PID:-}" ]; then
    kill "$TOOLBOX_PID" 2>/dev/null && echo " MCP Toolbox stopped"
fi