# ADK Multi-Agent Travel Planner

A collection of AI agents built with Google's Agent Development Kit (ADK), ranging from a single agent to complex multi-agent workflows. All agents are exposed through a single master orchestrator that routes requests to the most appropriate specialist.

For a guided walkthrough, refer to the [codelab](https://codelabs.developers.google.com/onramp/instructions#0).

## Demo

### ADK Web UI — Step-by-step agent execution

| | |
|---|---|
| ![User query](../demo/event-1-user-query.png) | ![Master orchestrator thinking](../demo/event-2-master-orchestrator-agent-thinking.png) |
| ![Orchestrator initiates transfer](../demo/event-3-master-orchestrator-agent-initiates-transfer.png) | ![Trip architect output](../demo/event-4-trip-architect-agent-output-1.png) |

![End-to-end trace](../demo/end-to-end-trace.png)

### Automated test report

![Test report](../demo/adk-agent-test-report.png)

A sample self-contained HTML report is included at [`tests/reports/report_20260513_225922.html`](tests/reports/report_20260513_225922.html).

---

## Agent Modules

| Module | Pattern | Description |
|--------|---------|-------------|
| `a_single_agent` | Single agent | Generates creative dating and outing plan suggestions |
| `b1_sequential_agent` | Sequential | Finds a location then provides directions to it |
| `b2_parallel_agent` | Parallel | Searches for multiple items (museum, concert, restaurant) simultaneously |
| `b3_loop_agent` | Loop / iterative | Refines a plan repeatedly until a constraint is satisfied |
| `b4_manual_sequential_flow` | Manual orchestration | Router agent with hand-rolled sequential dispatch logic |
| `c_custom_agent` | Custom `BaseAgent` | Budget-aware planner with Python decision gates |
| `d_routing_agent` | LLM router | Delegates to specialist sub-agents based on request type |
| `e_agent_as_tool` | Agents as tools | Trip architect that calls specialist agents via `AgentTool` |
| `f_agent_with_memory` | Session memory | Personalised planner that saves and recalls user preferences |
| `g_agents_mcp` | MCP toolbox | Database-backed destination search via MCP Toolbox |

### Agent Naming Convention

Agent names follow a deliberate two-tier pattern:

| Style | When used | Examples |
|-------|-----------|---------|
| `snake_case` | Standard ADK agents — instances of `Agent`, `SequentialAgent`, `ParallelAgent`, `LoopAgent` | `planner_agent`, `find_and_navigate_agent` |
| `PascalCase` | Custom-built orchestrators — either a real Python `BaseAgent` subclass, or a hand-crafted agent complex enough to warrant a proper noun | `BudgetAwarePlannerAgent`, `TripArchitectAgent`, `MemoryCoordinatorAgent` |

This is intentional: `snake_case` = standard ADK wiring, `PascalCase` = custom Python orchestration logic inside.

### Master Orchestrator (`agent/`)

`agent/__init__.py` exposes a single `root_agent` that the ADK web UI loads. It imports every module above and registers each as a sub-agent. Modules that fail to load (e.g. `g_agents_mcp` when the toolbox server is not running) are skipped automatically and will not appear in the UI.

## Prerequisites

- Python 3.8 or higher
- **Option A (Gemini API key):** A key from [Google AI Studio](https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com/credentials) — no gcloud, no billing needed
- **Option B (Vertex AI):** A GCP project with billing enabled — higher rate limits, no daily cap, recommended for production

## Quick Setup

> **Important:** All commands must be run from inside this `adk_in_local/` directory.

### Mac / Linux

```bash
chmod +x setup_venv.sh
./setup_venv.sh
```

### Windows

```cmd
setup_venv.bat
```

The script will:
1. Check for Python 3.8+
2. Create a `.adk_env` virtual environment
3. Install dependencies from `requirements.txt`
4. Prompt for your Google Cloud project ID and write a `.env` file
5. Download the MCP Toolbox binary into `mcp_tool_box/` automatically

## Dependencies

`google-adk` is pinned per Python version in `requirements.txt`:

| Python version | `google-adk` version |
|---------------|----------------------|
| `< 3.9` | `0.3.0` |
| `>= 3.9, < 3.10` | `1.15.1` |
| `>= 3.10` | `1.33.0` |

## Environment Setup

A single `.env` file inside `adk_in_local/` is the source of truth for all modules. A template is provided — copy it and fill in your credentials:

```bash
cp .env.example .env
```

Then choose one of the two authentication methods below.

### Option A: Gemini API Key (recommended for local development)

No gcloud, no billing required. Has a free tier (5 RPM on `gemini-2.5-flash`, 30 RPM on `gemini-2.0-flash-lite`).

```env
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=your-gemini-api-key
```

Get a key from the [Google Cloud Console](https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com/credentials) under **Gemini API > Credentials > Create credentials**.

> Do not commit `.env` to version control. A `.env.example` template is provided with both options.

### Option B: Vertex AI (Google Cloud)

Uses your GCP project for inference. No fixed RPM cap — scales with billing quota. Recommended when free-tier limits are a bottleneck.

```env
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
```

**Full setup required — follow these steps in order:**

```bash
# 1. Install gcloud CLI
brew install --cask google-cloud-sdk        # macOS
# For other platforms: https://cloud.google.com/sdk/docs/install

# 2. Authenticate the gcloud CLI
gcloud auth login

# 3. Set your project
gcloud config set project YOUR_PROJECT_ID

# 4. Set up Application Default Credentials (ADC) — required by the SDK
gcloud auth application-default login

# 5. Enable the Vertex AI API
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
```

> **Gotchas:**
> - `gcloud auth login` and `gcloud auth application-default login` are **two separate steps** — the SDK uses ADC, not the gcloud CLI credentials. Missing the second step causes a "default credentials not found" error.
> - **Billing must be enabled** on the GCP project. Vertex AI has no free tier.
> - After enabling the API or billing, wait ~2 minutes before retrying.

## Running the Agent

> **Important:** All commands below must be run from inside this `adk_in_local/` directory. The ADK web UI resolves the `agent/` module relative to the working directory — running from the repo root will fail.

Activate the virtual environment:

**Mac / Linux:**
```bash
source .adk_env/bin/activate
```

**Windows:**
```cmd
.adk_env\Scripts\activate
```

Then start the web UI:

```bash
./run.sh
```

`run.sh` automatically starts the MCP Toolbox server in the background on port 7001 before launching `adk web`, and shuts it down cleanly when you stop the UI. This starts the ADK web interface at [http://localhost:8080](http://localhost:8080) with SQLite-backed session persistence.

To start with a clean slate (wipes all saved session history and user preferences):

```bash
./run.sh --clean
```

Alternatively, clear sessions manually at any time without restarting:

```bash
rm ~/.adk/sessions/adk_web_sessions.db
```

Alternatively, run the standard ADK command directly (MCP Toolbox will not be started):

```bash
adk web
```

## MCP Toolbox (`g_agents_mcp`)

The `g_agents_mcp` module requires the MCP Toolbox server and a local SQLite database. `run.sh` handles the server automatically. The database must be created once:

```bash
python setup_trip_database.py
```

If the toolbox server is not running when `adk web` starts, `g_agents_mcp` is skipped automatically — the other 7 agents load normally.

## Model

The model and provider are configured in `model.config` — the single source of truth. All agents read from it via `config.py`; no agent files need to change when switching providers.

```ini
# model.config
MODEL_PROVIDER=gemini          # or: ollama
MODEL_NAME=gemini-2.5-flash    # or e.g. gemma4:e2b
OLLAMA_API_BASE=http://localhost:11434

JUDGE_PROVIDER=ollama
JUDGE_MODEL=qwen2.5:7b

# TEST_TIMEOUT_SECONDS=300    # per-test wall-clock timeout
# LLM_TIMEOUT_SECONDS=180     # per-LLM-call cap for Ollama
```

### Gemini (cloud)

| Model | Free Tier RPM | Notes |
|-------|--------------|-------|
| `gemini-2.5-flash` | 5 RPM | Default — best quality |
| `gemini-2.0-flash` | 15 RPM | Shared daily quota exhausts quickly |
| `gemini-2.0-flash-lite` | 30 RPM | Best fallback for free-tier rate limits |

> On Vertex AI, there is no fixed RPM cap — rate limits scale with your GCP billing quota.

### Ollama (local, offline)

Set `MODEL_PROVIDER=ollama` in `model.config`. Requires [Ollama](https://ollama.com) installed locally. All agents automatically use `ddg_search` (DuckDuckGo) instead of Google Search. Recommended models with tool-calling support: `gemma4`, `qwen2.5`, `llama3.1`, `mistral`.

## Troubleshooting: 429 RESOURCE_EXHAUSTED

Multi-agent chains make several LLM calls per request (orchestrator + sub-agents + tool-agents), so rate limits are hit faster than with single agents.

**Mitigations** ([official ADK docs](https://google.github.io/adk-docs/agents/models/google-gemini/#error-code-429-resource_exhausted)):

1. **Switch to a higher-quota model** — `gemini-2.0-flash-lite` has 30 RPM free tier vs 5 RPM for `gemini-2.5-flash`. Change the `model=` string in each agent file.

2. **Use Vertex AI** — eliminates RPM limits entirely. See [Option B](#option-b-vertex-ai-google-cloud) above.

3. **Client-side retries** — the master orchestrator has retry config applied:
   ```python
   generate_content_config=types.GenerateContentConfig(
       http_options=types.HttpOptions(
           retry_options=types.HttpRetryOptions(initial_delay=2, attempts=3),
       ),
   )
   ```
   This handles temporary RPM spikes but **cannot recover a fully exhausted daily quota** — you must wait for the quota to reset (midnight US Pacific time) or use a different API key.

4. **Request higher quota** — visit [Google AI Studio rate limits](https://ai.dev/rate-limit) and request a quota increase for your project.

## Running the Test Suite

Automated tests are defined in `tests/test_cases.yaml` (26 test cases across all agents) and evaluated by a local LLM judge — no Gemini API calls, no cost. See [TEST-CASES-EXECUTION.md](TEST-CASES-EXECUTION.md) for the full guide and [TEST-CASES.md](TEST-CASES.md) for all test case prompts and expected behaviours.

A sample HTML report is included at [`tests/reports/report_20260513_225922.html`](tests/reports/report_20260513_225922.html).

### Quick start

```bash
# Run all tests (stack must be running in another terminal)
python tests/run_tests.py

# Run a subset
python tests/run_tests.py --filter TC-M          # Master Orchestrator only
python tests/run_tests.py --filter TC-OL         # Ollama lenient tests only
python tests/run_tests.py --agent planner_agent  # one agent only

# Open the HTML report
open tests/reports/report_*.html
```

### How it works

The runner uses a **two-phase execution** model optimised for local Ollama inference:

- **Phase 1** — all agent calls run back-to-back while the agent model is warm in GPU memory. Per-test timing is printed (`collected (Xms)`).
- **Phase 2** — the judge model is pre-warmed once, then all collected responses are evaluated in batch. Per-test agent and judge timing is printed (`agent Xms / judge Xms`).

This avoids mid-suite model swaps, reducing total runtime by ~40% on Apple Silicon compared to interleaved agent + judge calls.

### Ollama mode

When `MODEL_PROVIDER=ollama` is set in `model.config`, the runner automatically selects only the `TC-OL-*` lenient tests instead of the full Gemini-quality suite. These tests use `tc_ol_planner` — a lightweight no-tools agent created inline — to avoid DDG search loops that make results non-deterministic on small local models.

```
 Ollama mode detected — running lenient TC-OL-* tests only
 (use --filter to override, e.g. --filter TC-A)
```

The judge model (`JUDGE_MODEL` in `model.config`, default `qwen2.5:7b`) is pulled automatically on first run if not already available.

---

## Deactivating the Environment

```bash
deactivate
```
