#!/bin/bash

# ADK Agent Virtual Environment Setup Script

set -e  # Exit on any error

# --- Function for error handling ---
handle_error() {
  echo "Error: $1"
  exit 1
}

# --- Part 1: Set Google Cloud Project ID ---
PROJECT_FILE="$HOME/project_id.txt"
echo "--- Setting Google Cloud Project ID File ---"

read -p "Please enter your Google Cloud project ID: " user_project_id

if [[ -z "$user_project_id" ]]; then
  handle_error "No project ID was entered."
fi

echo "You entered: $user_project_id"
echo "$user_project_id" > "$PROJECT_FILE"

if [[ $? -ne 0 ]]; then
  handle_error "Failed saving your project ID: $user_project_id."
fi
echo "Successfully saved project ID."



echo " Setting up ADK Agent virtual environment..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo " Python 3 is required but not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.8"
recommended_version="3.9"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo " Python $required_version or higher is required. Current version: $python_version"
    exit 1
fi

echo " Python $python_version detected"

# Indicate which google-adk version will be installed
if [ "$(printf '%s\n' "3.10" "$python_version" | sort -V | head -n1)" = "3.10" ]; then
    echo " Python $python_version >= 3.10 → Will install google-adk==1.33.0"
elif [ "$(printf '%s\n' "3.9" "$python_version" | sort -V | head -n1)" = "3.9" ]; then
    echo " Python $python_version >= 3.9  → Will install google-adk==1.15.1"
else
    echo "  Python $python_version < 3.9  → Will install google-adk==0.3.0 (consider upgrading)"
fi

# Create virtual environment
echo " Creating virtual environment..."
python3 -m venv .adk_env

# Activate virtual environment
echo " Activating virtual environment..."
source .adk_env/bin/activate

# Upgrade pip
echo "⬆  Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo " Installing dependencies..."
pip install -r requirements.txt



echo "--- Setting Google Cloud Environment Variables ---"

# --- Authentication Check ---
echo "Checking gcloud authentication status..."

if gcloud auth print-access-token > /dev/null 2>&1; then
  echo "gcloud is authenticated."
else
  echo "Error: gcloud is not authenticated."
  echo "Please log in by running: gcloud auth login"
  exit 1
fi

# Set up Application Default Credentials (required by the Google genai SDK for Vertex AI)
echo "Setting up Application Default Credentials (ADC)..."
if gcloud auth application-default print-access-token > /dev/null 2>&1; then
  echo "ADC already configured."
else
  echo "ADC not found. Running: gcloud auth application-default login"
  gcloud auth application-default login
fi

# --- Get Project ID and Create .env file ---
PROJECT_FILE_PATH=$(eval echo $PROJECT_FILE) # Expand potential ~
if [ ! -f "$PROJECT_FILE_PATH" ]; then
  echo "Error: Project file not found at $PROJECT_FILE_PATH"
  echo "Please run the script again and provide your Google Cloud project ID."
  exit 1
fi

PROJECT_ID_FROM_FILE=$(cat "$PROJECT_FILE_PATH")
echo "Setting gcloud config project to: $PROJECT_ID_FROM_FILE"
gcloud config set project "$PROJECT_ID_FROM_FILE" --quiet

# Re-confirm the project ID from the config
PROJECT_ID=$(gcloud config get project)
REGION="us-central1"

echo " Creating .env file..."
cat > .env << EOL
# Environment variables for ADK Agent, created by setup_venv.sh
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=${PROJECT_ID}
GOOGLE_CLOUD_LOCATION=${REGION}
EOL

# --- MCP Toolbox Binary Download ---
echo "--- Downloading MCP Toolbox binary ---"

TOOLBOX_DIR="$(dirname "$0")/mcp_tool_box"
TOOLBOX_BIN="$TOOLBOX_DIR/toolbox"
TOOLBOX_VERSION="1.2.0"

if [ -f "$TOOLBOX_BIN" ]; then
    echo " MCP Toolbox binary already exists, skipping download."
else
    # Detect OS and arch
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)

    if [ "$ARCH" = "x86_64" ]; then
        ARCH="amd64"
    elif [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then
        ARCH="arm64"
    else
        echo "  Unsupported architecture: $ARCH — skipping toolbox download. g_agents_mcp will be unavailable."
        SKIP_TOOLBOX=1
    fi

    if [ -z "${SKIP_TOOLBOX:-}" ]; then
        TOOLBOX_URL="https://storage.googleapis.com/mcp-toolbox-for-databases/v${TOOLBOX_VERSION}/${OS}/${ARCH}/toolbox"
        echo " Downloading from $TOOLBOX_URL..."
        curl -L -o "$TOOLBOX_BIN" "$TOOLBOX_URL" && chmod +x "$TOOLBOX_BIN"
        echo " MCP Toolbox binary downloaded to $TOOLBOX_BIN"
    fi
fi

echo " Setup complete! A '.env' file has been created with your configuration."
echo ""
echo "To activate the virtual environment, run:"
echo "   source .adk_env/bin/activate"
echo ""
echo "Your agent will automatically load the settings from the .env file."
echo "To deactivate the virtual environment, run:"
echo "   deactivate"
