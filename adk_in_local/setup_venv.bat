@echo off
REM ADK Agent Virtual Environment Setup Script for Windows

setlocal enabledelayedexpansion

REM --- Part 1: Set Google Cloud Project ID ---
set "PROJECT_FILE=%USERPROFILE%\project_id.txt"
echo --- Setting Google Cloud Project ID File ---

set /p user_project_id="Please enter your Google Cloud project ID: "

if not defined user_project_id (
    echo Error: No project ID was entered.
    exit /b 1
)

echo You entered: !user_project_id!
echo !user_project_id! > "%PROJECT_FILE%"

if !errorlevel! neq 0 (
    echo Error: Failed saving your project ID: !user_project_id!.
    exit /b 1
)
echo Successfully saved project ID.

echo Setting up ADK Agent virtual environment...

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is required but not installed. Please install Python 3.8 or higher.
    pause
    exit /b 1
)

REM Get Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set python_version=%%i
echo Python %python_version% detected

REM Check which version of google-adk will be installed
python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if %errorlevel% equ 0 (
    echo Python %python_version% ^>= 3.10 -- Will install google-adk==1.33.0
) else (
    python -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
    if !errorlevel! equ 0 (
        echo Python %python_version% ^>= 3.9 -- Will install google-adk==1.15.1
    ) else (
        echo Python %python_version% ^< 3.9 -- Will install google-adk==0.3.0 (consider upgrading^)
    )
)

REM Create virtual environment
echo Creating virtual environment...
python -m venv .adk_env

REM Activate virtual environment
echo Activating virtual environment...
call .adk_env\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
pip install --upgrade pip

REM Install requirements
echo Installing dependencies...
pip install -r requirements.txt

echo --- Setting Google Cloud Environment Variables ---

REM --- Authentication Check ---
echo Checking gcloud authentication status...

gcloud auth print-access-token >nul 2>&1
if !errorlevel! neq 0 (
    echo Error: gcloud is not authenticated.
    echo Please log in by running: gcloud auth login
    exit /b 1
)
echo gcloud is authenticated.

REM --- Set up Application Default Credentials ---
echo Checking Application Default Credentials (ADC^)...
gcloud auth application-default print-access-token >nul 2>&1
if !errorlevel! neq 0 (
    echo ADC not found. Running: gcloud auth application-default login
    gcloud auth application-default login
) else (
    echo ADC already configured.
)

REM --- Get Project ID and Create .env file ---
if not exist "%PROJECT_FILE%" (
    echo Error: Project file not found at "%PROJECT_FILE%"
    echo Please run the script again and provide your Google Cloud project ID.
    exit /b 1
)

for /f "delims=" %%i in (%PROJECT_FILE%) do set PROJECT_ID_FROM_FILE=%%i
echo Setting gcloud config project to: !PROJECT_ID_FROM_FILE!
gcloud config set project "!PROJECT_ID_FROM_FILE!" --quiet

REM Re-confirm the project ID from the config
for /f "delims=" %%j in ('gcloud config get project') do set PROJECT_ID=%%j
set "REGION=us-central1"

echo Creating .env file...
(
    echo # Environment variables for ADK Agent, created by setup_venv.bat
    echo GOOGLE_GENAI_USE_VERTEXAI=TRUE
    echo GOOGLE_CLOUD_PROJECT=!PROJECT_ID!
    echo GOOGLE_CLOUD_LOCATION=!REGION!
) > .env

REM --- MCP Toolbox Binary Download ---
echo --- Downloading MCP Toolbox binary ---

set "TOOLBOX_DIR=%~dp0mcp_tool_box"
set "TOOLBOX_BIN=%TOOLBOX_DIR%\toolbox.exe"
set "TOOLBOX_VERSION=1.2.0"
set "TOOLBOX_URL=https://storage.googleapis.com/mcp-toolbox-for-databases/v%TOOLBOX_VERSION%/windows/amd64/toolbox.exe"

if exist "%TOOLBOX_BIN%" (
    echo MCP Toolbox binary already exists, skipping download.
) else (
    echo Downloading from %TOOLBOX_URL%...
    powershell -Command "Invoke-WebRequest -Uri '%TOOLBOX_URL%' -OutFile '%TOOLBOX_BIN%'"
    if !errorlevel! neq 0 (
        echo Warning: Failed to download MCP Toolbox binary. g_agents_mcp will be unavailable.
    ) else (
        echo MCP Toolbox binary downloaded to %TOOLBOX_BIN%
    )
)

echo Setup complete! A '.env' file has been created with your configuration.
echo.
echo To activate the virtual environment, run:
echo    .adk_env\Scripts\activate
echo.
echo Your agent will automatically load the settings from the .env file.
echo To deactivate the virtual environment, run:
echo    deactivate
echo.
pause
