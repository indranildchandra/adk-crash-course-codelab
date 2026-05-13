# GEMINI.md — ADK Multi-Agent Travel Planner

Working directory for all commands: `adk_in_local/`
Virtual environment: `.adk_env/` — activate with `source .adk_env/bin/activate`

---

## Repo Structure

```
adk_in_local/
├── config.py                    # Central config — MODEL, SEARCH_TOOLS, IS_GEMINI, TEST_TIMEOUT_SECONDS, LLM_TIMEOUT_SECONDS
├── model.config                 # Single source of truth for model/provider/judge/timeout settings
├── requirements.txt             # Pinned deps — update here, then pip install -r requirements.txt
├── run.sh                       # Start stack: Ollama (if needed) + MCP Toolbox + adk web
├── tools/
│   └── duckduckgo_search.py     # Custom DDG search tool (Ollama path) — ddg_search()
├── agent/
│   └── __init__.py              # Master orchestrator — dynamically loads all sub-agents
├── a_single_agent/
│   └── day_trip.py              # Single LlmAgent — dating/outing planner (root_agent = planner_agent)
├── b1_sequential_agent/
│   └── agents.py                # SequentialAgent — find location → navigate (find_and_navigate_agent)
├── b2_parallel_agent/
│   └── agents.py                # ParallelAgent — museum + concert + restaurant in parallel (parallel_planner_agent)
├── b3_loop_agent/
│   └── agents.py                # LoopAgent — iterative constraint refinement (iterative_planner_agent)
├── b4_manual_sequential_flow/
│   └── agent.py                 # Manual orchestration — router + hand-rolled dispatch (router_agent)
├── c_custom_agent/
│   └── agents.py                # BaseAgent subclass — BudgetAwarePlannerAgent with Python decision gates
├── d_routing_agent/
│   └── agents.py                # LLM router — delegates to foodie_agent or transportation_agent (root_agent = routing_agent)
├── e_agent_as_tool/
│   └── agents.py                # AgentTool pattern — TripArchitectAgent calls LocationScoutAgent + LogisticsValidatorAgent as tools
├── f_agent_with_memory/
│   └── agents.py                # Session memory — MemoryCoordinatorAgent with save/recall tools via tool_context.state
├── g_agents_mcp/
│   └── trip_agent.py            # MCP Toolbox — trip_planner_agent via ToolboxSyncClient on port 7001
├── mcp_tool_box/
│   └── trip_tools.yaml          # MCP tool definitions (find_destinations_by_type, find_top_rated_in_city, find_affordable_options)
├── tests/
│   ├── test_cases.yaml          # 26 test cases across all agents (+ 5 TC-OL-* lenient Ollama tests)
│   ├── run_tests.py             # Two-phase test runner — ADK Runner + LLM judge + HTML report
│   └── reports/                 # HTML reports (gitignored except sample)
├── TEST-CASES.md                # All test case prompts and expected behaviours (human-readable)
├── TEST-CASES-EXECUTION.md      # How to run the test suite, report format, judge config
├── test-cases.txt               # Compact test case index (ID | agent | name | prompt)
└── setup_trip_database.py       # One-time SQLite DB setup for g_agents_mcp
```

---

## Central Config Pattern — the most important thing to understand

### `model.config` — edit this to change models globally

```ini
MODEL_PROVIDER=ollama          # or: gemini
MODEL_NAME=gemma4:e2b          # or: gemini-2.5-flash
OLLAMA_API_BASE=http://localhost:11434

JUDGE_PROVIDER=ollama
JUDGE_MODEL=qwen2.5:7b

# TEST_TIMEOUT_SECONDS=300     # per-test wall-clock timeout (default 300s)
# LLM_TIMEOUT_SECONDS=180      # per-LLM-call cap for Ollama (default 180s)
```

### `config.py` — exports consumed by every agent

| Export | Type | Gemini value | Ollama value |
|--------|------|-------------|--------------|
| `MODEL` | `str` or `LiteLlm` | `"gemini-2.5-flash"` | `LiteLlm(model="ollama_chat/gemma4:e2b")` |
| `SEARCH_TOOLS` | `list` | `[google_search]` | `[ddg_search]` |
| `IS_GEMINI` | `bool` | `True` | `False` |
| `TEST_TIMEOUT_SECONDS` | `int` | 300 | 300 |
| `LLM_TIMEOUT_SECONDS` | `int` | 180 | 180 |

### Rules — always follow these

1. **Every agent imports from config**: `from config import MODEL, SEARCH_TOOLS`
2. **Never import `google_search` directly in agent files** — always use `SEARCH_TOOLS`. The only place `google_search` is imported is inside `config.py`'s `else` branch.
3. **Use `IS_GEMINI`** for any Gemini-specific branching (retry config, grounding, etc.) — not `if SEARCH_TOOLS:` (SEARCH_TOOLS is non-empty for both providers).
4. **Never import `google.genai.types` unconditionally** — guard with `if IS_GEMINI:`.

---

## Search Tool Architecture

`google_search` (Gemini built-in) is **server-side grounding** — it runs on Google's infrastructure, not in Python. It cannot work with Ollama/LiteLLM regardless of naming tricks.

`ddg_search` (DuckDuckGo via `ddgs` package) is a **plain Python function** in `tools/duckduckgo_search.py`. ADK auto-generates the tool schema from its type hints and docstring. Hardcoded to 10 results. No API key required.

Switching provider in `model.config` automatically routes all agents to the right search tool — no agent code changes needed.

---

## Agent Naming Convention

Agent names follow a deliberate two-tier pattern — do not "fix" this:

- **`snake_case`** — configured ADK agents (`Agent`, `SequentialAgent`, `ParallelAgent`, `LoopAgent`). These are instances, named like variables.
- **`PascalCase`** — custom-built orchestrators. Either a real Python class (`class BudgetAwarePlannerAgent(BaseAgent)`) or a hand-crafted orchestrator important enough to read like a proper noun (`TripArchitectAgent`, `MemoryCoordinatorAgent`).

The naming is a visual cue: snake_case = standard ADK wiring, PascalCase = custom Python logic inside.

---

## Agent Patterns Quick Reference

| Module | ADK Class | Key Pattern |
|--------|-----------|-------------|
| `a_single_agent` | `Agent` | Single LLM with search tool |
| `b1_sequential_agent` | `SequentialAgent` | Output of agent 1 feeds agent 2 |
| `b2_parallel_agent` | `ParallelAgent` | Three sub-agents run concurrently, results merged |
| `b3_loop_agent` | `LoopAgent` + `SequentialAgent` | Runs until `exit_loop()` sets `tool_context.actions.escalate = True` |
| `b4_manual_sequential_flow` | `Agent` (hand-rolled) | `router_agent` returns a name string, Python dispatches manually via `worker_agents` dict |
| `c_custom_agent` | `BaseAgent` subclass | `@override _run_async_impl` — Python controls full execution flow; uses `output_key` to pass state between LlmAgents |
| `d_routing_agent` | `Agent` with `sub_agents` | LLM-driven routing via `transfer_to_agent`; imports and re-exposes agents from b2, b3, c |
| `e_agent_as_tool` | `Agent` + `AgentTool` | Specialist agents wrapped in `AgentTool(agent=...)` and passed as `tools=[]` |
| `f_agent_with_memory` | `BaseAgent` + `ToolContext` | Preferences stored/recalled via `tool_context.state` (ADK session persistence) |
| `g_agents_mcp` | `Agent` + `ToolboxSyncClient` | Tools loaded from MCP Toolbox server at runtime — requires server on port 7001 |

---

## Master Orchestrator (`agent/__init__.py`)

- Dynamically imports each module inside `_try_load()` — failed imports are skipped silently
- Builds `sub_agents` list only from what loaded successfully
- Generates routing instruction dynamically from available agents
- `generate_content_config` (Gemini retry) applied only when `IS_GEMINI` is True
- `d_routing_agent` is NOT included as a sub-agent — it's standalone module D

---

## Memory Agent (`f_agent_with_memory`)

Session state is stored via `tool_context.state` — a dict persisted by ADK's session service.

```python
# Write
tool_context.state['user_preferences'] = {...}

# Read
prefs = tool_context.state.get('user_preferences') or {}
```

`adk web` uses SQLite-backed sessions (`~/.adk/sessions/adk_web_sessions.db`). Clear with `./run.sh --clean`.
Test runner uses `InMemorySessionService` — state is fresh per test case.

---

## MCP Toolbox (`g_agents_mcp`)

Requires two things to be running before `adk web`:
1. SQLite DB (one-time): `python setup_trip_database.py`
2. Toolbox server: `./mcp_tool_box/toolbox --config mcp_tool_box/trip_tools.yaml --port 7001`

`run.sh` handles the server automatically. If toolbox isn't running, `g_agents_mcp` is skipped — other agents load normally.

Available tools: `find_destinations_by_type(city, type)`, `find_top_rated_in_city(city)`, `find_affordable_options(city, max_cost)`.

---

## Test Runner (`tests/run_tests.py`)

- Test cases defined in `tests/test_cases.yaml` — 26 Gemini-quality tests + 5 TC-OL-* lenient Ollama tests
- Each test runs via ADK `Runner` + `InMemorySessionService` (multi-turn tests share a session)
- LLM judge: local Ollama model (`JUDGE_MODEL` in `model.config`) — zero API cost, auto-pulled on first run
- Output: `tests/reports/report_<timestamp>.html` (gitignored except the sample report)

**Two-phase execution** (Ollama / Apple Silicon optimised):
- Phase 1 — all agent calls run back-to-back while the agent model is warm (`collected (Xms)` per test)
- Phase 2 — judge model pre-warmed once, then all responses evaluated in batch (`agent Xms / judge Xms`)

**Ollama auto-selection**: when `MODEL_PROVIDER=ollama`, only `TC-OL-*` tests run automatically. Override with `--filter`.

**`tc_ol_planner`**: a no-tools agent created inline for TC-OL-* tests — prevents DDG search loops that make small local models non-deterministic.

Timeouts (both configurable in `model.config`):
- `TEST_TIMEOUT_SECONDS` (default 300s) — per-test wall-clock limit
- `LLM_TIMEOUT_SECONDS` (default 180s) — per-LLM-call cap for Ollama (`litellm.request_timeout`)

```bash
python tests/run_tests.py                    # all tests (TC-OL-* only if Ollama)
python tests/run_tests.py --filter TC-A      # single agent only
python tests/run_tests.py --filter TC-OL     # Ollama lenient tests only
python tests/run_tests.py --agent planner_agent
```

---

## Adding a New Agent Module

1. Create `x_new_module/agents.py` with `from config import MODEL, SEARCH_TOOLS`
2. Define `root_agent = Agent(name="my_agent", model=MODEL, tools=SEARCH_TOOLS, ...)`
3. Add an entry to `agent/__init__.py` via `_try_load()`
4. Add test cases to `tests/test_cases.yaml`
5. Register agent ID in `AGENT_REGISTRY` in `tests/run_tests.py`

## Adding a New Custom Tool

1. Create `tools/my_tool.py` — a plain Python function with type hints + docstring
2. Import and add to `SEARCH_TOOLS` (or a separate `tools` list) in `config.py`
3. No decorators, no subclassing — ADK auto-generates the schema

---

## Known Gotchas

- **`google_search` is Gemini-only**: It's server-side grounding on Google's infra, not a Python function. Cannot be spoofed or redirected to Ollama.
- **`generate_content_config` is Gemini-only**: Passing it to an Ollama-backed agent causes a runtime error. Always guard with `IS_GEMINI`.
- **`b3_loop_agent` exit condition**: `exit_loop()` sets `tool_context.actions.escalate = True` — the loop won't terminate unless this function is actually called by the model.
- **`c_custom_agent` Pydantic**: `BudgetAwarePlannerAgent` requires `model_config = {"arbitrary_types_allowed": True}` because ADK agent instances are stored as class attributes.
- **`d_routing_agent` cross-imports**: Imports `iterative_planner_agent`, `parallel_planner_agent`, and `custom_agent` from sibling modules — loading it triggers those modules too.
- **MCP Toolbox port conflict**: Kill stale processes with `lsof -ti tcp:7001 | xargs kill -9` before restarting.
- **Ollama tool calling**: `gemma3` does NOT support tool calling. Use `gemma4`, `qwen2.5`, `llama3.1/3.2`, or `mistral`.
- **Graph builder 500 errors**: Pydantic serialization warnings from `GoogleSearchTool` and `LiteLLMClient` appear in `adk web` logs — cosmetic only, non-blocking.
- **Test runner imports all agents at startup**: Changing `model.config` and rerunning tests without restarting will use cached module state. Restart the test runner process after changing config.
