#!/bin/bash

# Parse flags
CLEAN=0
for arg in "$@"; do
    case $arg in
        --clean) CLEAN=1 ;;
    esac
done

echo " Starting ADK Web UI with persistent session storage..."

# Cleanup trap — fires on exit, Ctrl+C (SIGINT), and SIGTERM
# Only kills processes that THIS script started (TOOLBOX_PID / OLLAMA_PID)
cleanup() {
    if [ -n "${TOOLBOX_PID:-}" ]; then
        kill "$TOOLBOX_PID" 2>/dev/null && echo " MCP Toolbox stopped"
    fi
    if [ -n "${OLLAMA_PID:-}" ]; then
        kill "$OLLAMA_PID" 2>/dev/null && echo " Ollama stopped"
    fi
}
trap cleanup EXIT SIGINT SIGTERM

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

# Start Ollama in background if model.config specifies ollama provider
MODEL_CONFIG="$(dirname "$0")/model.config"
if [ -f "$MODEL_CONFIG" ]; then
    _provider=$(grep -E "^MODEL_PROVIDER=" "$MODEL_CONFIG" | cut -d= -f2 | tr -d '[:space:]')
    _model_name=$(grep -E "^MODEL_NAME=" "$MODEL_CONFIG" | cut -d= -f2 | tr -d '[:space:]')
    if [ "$_provider" = "ollama" ]; then
        if ! command -v ollama > /dev/null 2>&1; then
            echo "ERROR: MODEL_PROVIDER=ollama but ollama is not installed."
            echo "  Install Ollama:  brew install ollama"
            echo "  Then pull model: ollama pull $_model_name"
            exit 1
        fi
        if curl -s http://localhost:11434 > /dev/null 2>&1; then
            echo " Ollama already running on port 11434"
        else
            ollama serve &
            OLLAMA_PID=$!
            echo " Ollama started (pid $OLLAMA_PID) on port 11434"
            sleep 2  # give it time to bind before agents load
        fi

        # Check if the required model is pulled; pull it if not
        if ! ollama list 2>/dev/null | grep -q "$_model_name"; then
            echo " Model '$_model_name' not found locally — pulling now (this may take a few minutes)..."
            ollama pull "$_model_name"
            echo " Model '$_model_name' ready"
        else
            echo " Model '$_model_name' already available"
        fi
    fi
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

# --clean: wipe session DB before starting
if [ "$CLEAN" = "1" ]; then
    if [ -f "$DB_FILE" ]; then
        rm "$DB_FILE"
        echo " Session database cleared: $DB_FILE"
    else
        echo " No session database found to clear"
    fi
fi

echo " Session database: $DB_FILE"
echo " Session URI: $SESSION_URI"

# Start ADK Web UI with persistent sessions
echo " Starting ADK Web UI on http://localhost:8080..."
echo " Evaluation results and user preferences will now persist across requests!"

adk web \
    --session_service_uri="$SESSION_URI" \
    --host=127.0.0.1 \
    --port=8080 \
    --log_level=warning \
    --reload \
    .

echo " ADK Web UI stopped"