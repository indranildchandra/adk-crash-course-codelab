# Test Cases — Execution Guide

Automated test runner for the ADK Multi-Agent Travel Planner.
Runs all test cases from `tests/test_cases.yaml`, evaluates responses with a local LLM judge (no API costs), and produces a self-contained HTML report.

---

## Prerequisites

All commands must be run from inside `adk_in_local/`.

### 1. Start the stack

The agents must be reachable. Start everything with:

```bash
cd adk_in_local
source .adk_env/bin/activate
./run.sh
```

Leave this running in a separate terminal.

### 2. Judge model (auto-pulled)

The test runner uses a local Ollama model as the LLM judge — no Gemini API calls, no cost. The judge model is configured in `model.config`:

```ini
JUDGE_PROVIDER=ollama
JUDGE_MODEL=qwen2.5:7b
```

Change `JUDGE_MODEL` to any Ollama model you prefer. `qwen2.5:7b` is recommended for its strong reasoning ability. **The runner pulls the configured model automatically on first run** — no manual `ollama pull` needed.

---

## Running the Tests

Open a second terminal (stack must be running in the first):

```bash
cd adk_in_local
source .adk_env/bin/activate
```

### Run all test cases

```bash
python tests/run_tests.py
```

### Run a subset by test ID prefix

```bash
python tests/run_tests.py --filter TC-M    # Master Orchestrator only
python tests/run_tests.py --filter TC-A    # Single Agent only
python tests/run_tests.py --filter TC-B1   # Sequential Agent only
python tests/run_tests.py --filter TC-B2   # Parallel Agent only
python tests/run_tests.py --filter TC-B3   # Loop Agent only
python tests/run_tests.py --filter TC-C    # Budget-Aware Planner only
python tests/run_tests.py --filter TC-D    # Routing Agent only
python tests/run_tests.py --filter TC-E    # Trip Architect only
python tests/run_tests.py --filter TC-F    # Memory Agent only
python tests/run_tests.py --filter TC-G    # MCP Trip Planner only
```

### Run tests for a specific agent

```bash
python tests/run_tests.py --agent planner_agent
python tests/run_tests.py --agent master_orchestrator
python tests/run_tests.py --agent MemoryCoordinatorAgent
python tests/run_tests.py --agent trip_planner_agent
```

### Open the HTML report

```bash
open tests/reports/report_*.html
```

Or open the latest report specifically:

```bash
ls -t tests/reports/ | head -1 | xargs -I{} open tests/reports/{}
```

---

## Report Overview

The HTML report is self-contained (no external dependencies) and includes:

| Section | Description |
|---------|-------------|
| **Summary bar** | Total / Passed / Failed / Skipped / Errors + pass rate % |
| **Progress bar** | Visual pass rate indicator |
| **Filter buttons** | Click to show only PASS / FAIL / SKIP / ERROR results |
| **Test cards** | One collapsible card per test case |
| **Card details** | Prompt(s), full agent response, expected behaviour, judge score (0–10) + verdict |

### Status definitions

| Status | Meaning |
|--------|---------|
| `PASS` | Agent response met expected behaviour (judge score ≥ threshold) |
| `FAIL` | Agent response did not meet expected behaviour |
| `SKIP` | Agent failed to load (e.g. `g_agents_mcp` when MCP Toolbox is not running) |
| `ERROR` | Test timed out or threw an unexpected exception |

---

## How the LLM Judge Works

Each agent response is evaluated by a local Ollama model (`qwen2.5:7b` by default):

1. The judge receives the full conversation (all turns), the expected behaviour description, and the actual agent response
2. It returns a JSON verdict: `{"pass": true/false, "score": 0-10, "reason": "..."}`
3. The score and reason are displayed in the HTML report card

**No Gemini or external API calls are made during evaluation** — the judge runs entirely offline.

---

## Two-Phase Execution

The runner uses a two-phase model to minimise Ollama model-swap overhead on Apple Silicon:

- **Phase 1 — collect**: All agent calls run back-to-back while the agent model is warm in GPU memory. Per-test collection time is printed inline (`collected (Xms)`).
- **Phase 2 — judge**: The judge model is pre-warmed once via the Ollama API (`keep_alive=30m`), then all collected responses are evaluated in batch. Per-test agent and judge timings are printed (`agent Xms / judge Xms`).

This keeps each model resident for its entire phase, eliminating mid-suite GPU memory swaps and cutting total runtime by ~40% compared to interleaved execution.

---

## Ollama Mode — Automatic Test Selection

When `MODEL_PROVIDER=ollama` is set in `model.config`, the runner automatically selects only the `TC-OL-*` lenient tests instead of the full suite. This avoids running multi-agent Gemini-quality tests against a local model that would time out.

```
 Ollama mode detected — running lenient TC-OL-* tests only
 (use --filter to override, e.g. --filter TC-A)
```

### TC-OL-* design notes

- All TC-OL tests use `tc_ol_planner` — a lightweight agent created inline by the test runner with **no search tools** and a concise instruction. This prevents DDG search loops that make results non-deterministic on small local models.
- Each test requires a single LLM call. With two-phase execution and model pre-warming, 5 tests complete in ~1 minute on Apple Silicon.
- The judge model (`qwen2.5:7b`) evaluates responses with lenient criteria — any named place, food, or activity passes.

### Running TC-OL tests manually (even with Gemini configured)

```bash
python tests/run_tests.py --filter TC-OL
```

---

## Test Timeout

Both timeouts are configurable in `model.config`:

```ini
TEST_TIMEOUT_SECONDS=300   # per-test wall-clock timeout (default 300s)
LLM_TIMEOUT_SECONDS=180    # per-LLM-call cap for Ollama (default 180s)
```

`TEST_TIMEOUT_SECONDS` is the hard wall-clock limit per test case. `LLM_TIMEOUT_SECONDS` caps each individual Ollama HTTP call so that timed-out background threads drain quickly and do not block subsequent tests. Neither key is needed for Gemini.

---

## Adding New Test Cases

Edit `tests/test_cases.yaml` and add an entry following this structure:

```yaml
- id: TC-X-01
  agent: agent_id_here         # must match a key in AGENT_REGISTRY in run_tests.py
  name: Short description
  turns:
    - "First user message"
    - "Optional second turn for multi-turn tests"
  expected: >
    What a correct response should contain or do.
    Be specific — the judge uses this to evaluate.
```

For multi-turn tests (e.g. memory agents), add multiple entries under `turns`. Each turn uses the same session so the agent retains context across turns.
