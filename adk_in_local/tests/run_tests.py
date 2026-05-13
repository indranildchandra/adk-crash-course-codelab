"""
ADK Agent Test Runner
=====================
Runs all test cases from test_cases.yaml against live ADK agents,
evaluates each response with an LLM judge, and produces an HTML report.

Usage (from adk_in_local/):
    python tests/run_tests.py                    # run all tests
    python tests/run_tests.py --filter TC-M      # run only TC-M-* tests
    python tests/run_tests.py --agent planner_agent  # run tests for one agent

Output: tests/reports/report_<timestamp>.html
"""

import asyncio
import concurrent.futures
import sys
import logging
import warnings
import json
import yaml
import argparse
import traceback
import importlib
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Suppress the MCP protocol version warning emitted via the root logger by toolbox_core
logging.getLogger().addFilter(
    type("_MCPFilter", (logging.Filter,), {
        "filter": lambda self, r: "newer version of MCP" not in r.getMessage()
    })()
)

# Suppress litellm LoggingWorker RuntimeWarnings ("coroutine was never awaited",
# "async_success_handler was never awaited") that appear when the thread's event
# loop closes while litellm's background worker still has pending log tasks.
# These are harmless cleanup-ordering artefacts, not real errors.
warnings.filterwarnings(
    "ignore",
    message="coroutine '.*' was never awaited",
    category=RuntimeWarning,
)
warnings.filterwarnings(
    "ignore",
    message="Enable tracemalloc",
    category=RuntimeWarning,
)

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
import litellm

litellm.set_verbose = False  # suppress litellm debug noise

# ── Agent registry ────────────────────────────────────────────────────────────
# Maps test_cases.yaml agent id → (module_path, attribute_name)
AGENT_REGISTRY = {
    "master_orchestrator":    ("agent",                       "root_agent"),
    "planner_agent":          ("a_single_agent.day_trip",     "root_agent"),
    "find_and_navigate_agent":("b1_sequential_agent.agents",  "find_and_navigate_agent"),
    "parallel_planner_agent": ("b2_parallel_agent.agents",    "parallel_planner_agent"),
    "iterative_planner_agent":("b3_loop_agent.agents",        "iterative_planner_agent"),
    "BudgetAwarePlannerAgent":("c_custom_agent.agents",       "root_agent"),
    "routing_agent":          ("d_routing_agent.agents",      "root_agent"),
    "TripArchitectAgent":     ("e_agent_as_tool.agents",      "root_agent"),
    "MemoryCoordinatorAgent": ("f_agent_with_memory.agents",  "root_agent"),
    "trip_planner_agent":     ("g_agents_mcp.trip_agent",     "root_agent"),
}

from config import TEST_TIMEOUT_SECONDS, LLM_TIMEOUT_SECONDS, IS_GEMINI
TIMEOUT_SECONDS = TEST_TIMEOUT_SECONDS

# For Ollama, cap each individual LLM HTTP request so that when a test times
# out, the background thread's Ollama HTTP connection is dropped quickly,
# freeing the server for the next test.  Not needed for Gemini (fast network).
# Configurable via LLM_TIMEOUT_SECONDS in model.config (default 180s).
if not IS_GEMINI:
    litellm.request_timeout = LLM_TIMEOUT_SECONDS

# ── Data classes ──────────────────────────────────────────────────────────────
@dataclass
class TurnResult:
    prompt: str
    response: str

@dataclass
class TestResult:
    id: str
    agent_id: str
    name: str
    status: str = ""     # PASS | FAIL | SKIP | ERROR
    turns: list[TurnResult] = field(default_factory=list)
    expected: str = ""
    score: int = 0       # 0-10
    verdict: str = ""
    error: str = ""
    duration_ms: int = 0

# ── Agent loader ──────────────────────────────────────────────────────────────
def load_agent(agent_id: str):
    # Special lightweight agent for TC-OL-* tests in Ollama mode.
    # Has NO tools — prevents DDG search loops that make tests non-deterministic.
    # One LLM call per query, ~50-80s, reliable under the 300s timeout.
    if agent_id == "tc_ol_planner":
        from google.adk.agents import Agent
        from config import MODEL
        return Agent(
            name="tc_ol_planner",
            model=MODEL,
            instruction=(
                "You are a concise Bay Area travel assistant. "
                "Answer questions briefly from general knowledge only. "
                "Give short, direct responses with specific place names. "
                "Keep responses to 2-3 sentences."
            ),
            tools=[],
        )
    if agent_id not in AGENT_REGISTRY:
        raise ValueError(f"Unknown agent id: {agent_id}")
    module_path, attr = AGENT_REGISTRY[agent_id]
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)

# ── ADK runner ────────────────────────────────────────────────────────────────
async def run_turns(agent, turns: list[str]) -> list[TurnResult]:
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=agent.name,
        user_id="test_runner",
        session_id=f"test_{datetime.now().timestamp()}",
    )
    runner = Runner(
        agent=agent,
        app_name=agent.name,
        session_service=session_service,
    )

    results = []
    for prompt in turns:
        response_parts = []
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=Content(parts=[Part(text=prompt)], role="user"),
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        response_parts.append(part.text)
        results.append(TurnResult(prompt=prompt, response="\n".join(response_parts).strip()))
    return results

# ── Judge config (read from model.config) ─────────────────────────────────────
def _load_judge_config() -> tuple[str, str, str]:
    """Returns (provider, model_name, api_base)."""
    config_path = ROOT / "model.config"
    cfg = {}
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    provider  = cfg.get("JUDGE_PROVIDER", "ollama").lower()
    model     = cfg.get("JUDGE_MODEL", "qwen2.5:7b")
    api_base  = cfg.get("OLLAMA_API_BASE", "http://localhost:11434")
    return provider, model, api_base

JUDGE_PROVIDER, JUDGE_MODEL_NAME, JUDGE_API_BASE = _load_judge_config()

# ── Ollama model pre-warmer ────────────────────────────────────────────────────
async def _prewarm_ollama_models() -> None:
    """Pre-load agent and judge models into GPU memory before tests begin.

    On Apple Silicon, Ollama uses the Metal GPU but must load model weights from
    disk on the first request (cold start, ~10–30 s per model).  Sending a short
    "hi" prompt before the test loop pays that cost once rather than charging it
    against the first test's timer.

    keep_alive=30m ensures both models stay resident in GPU memory across the
    entire test run, so Ollama never needs to swap between them mid-suite.
    """
    import httpx

    # Read the agent model name from model.config
    config_path = ROOT / "model.config"
    cfg: dict = {}
    with open(config_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    agent_model = cfg.get("MODEL_NAME", "")

    # Only pre-warm the agent model, not the judge.
    # On 16 GB unified memory (M1 Pro/Max), loading both models simultaneously
    # (e.g. gemma4:e2b 7.2 GB + qwen2.5:7b 4.7 GB = 11.9 GB) leaves the OS
    # starved of RAM and slows inference by 40-50%.  Keeping only the agent
    # model resident means Ollama has breathing room; the judge loads lazily
    # (once per test, negligible overhead compared to inference time).
    models = [agent_model] if agent_model else []
    # Exception: if agent and judge are the same model, one pre-warm covers both.
    if JUDGE_MODEL_NAME and JUDGE_MODEL_NAME == agent_model:
        models = [agent_model]
    api_base = JUDGE_API_BASE.rstrip("/")

    async with httpx.AsyncClient() as client:
        for model in models:
            try:
                print(f" Pre-warming '{model}' ...", end=" ", flush=True)
                await client.post(
                    f"{api_base}/api/chat",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "keep_alive": "30m",
                        "stream": False,
                    },
                    timeout=120.0,
                )
                print("ready")
            except Exception as e:
                print(f"skipped ({e})")

# ── LLM judge ─────────────────────────────────────────────────────────────────
async def judge(turns: list[TurnResult], expected: str) -> tuple[str, int, str]:
    """Returns (status, score, verdict). Uses local Ollama model — no API cost."""
    conversation = "\n\n".join(
        f"[Turn {i+1}]\nUser: {t.prompt}\nAgent: {t.response}"
        for i, t in enumerate(turns)
    )
    prompt = f"""You are a QA evaluator for an AI travel planning assistant.

CONVERSATION:
{conversation}

EXPECTED BEHAVIOUR:
{expected}

Evaluate whether the agent's final response meets the expected behaviour.
Return ONLY valid JSON — no markdown fences, no explanation outside the JSON:
{{"pass": true_or_false, "score": 0_to_10, "reason": "one or two sentence explanation"}}

Score guide: 0=completely wrong, 5=partially correct, 10=fully correct."""

    try:
        response = await litellm.acompletion(
            model=f"ollama_chat/{JUDGE_MODEL_NAME}",
            messages=[{"role": "user", "content": prompt}],
            api_base=JUDGE_API_BASE,
            timeout=300,
        )
        raw = response.choices[0].message.content.strip()
        # Strip accidental markdown fences
        raw = raw.strip("```json").strip("```").strip()
        data = json.loads(raw)
        status = "PASS" if data.get("pass") else "FAIL"
        return status, int(data.get("score", 0)), data.get("reason", "")
    except Exception as e:
        return "FAIL", 0, f"Judge error: {e}"

# ── Thread-isolated runner ────────────────────────────────────────────────────
def _run_turns_in_thread(agent, turns: list[str]) -> list[TurnResult]:
    """Run async run_turns() in a fresh event loop inside a thread.

    asyncio.wait_for() cannot cancel blocking Ollama HTTP requests — the
    litellm/httpx layer holds the GIL in a run_in_executor thread that ignores
    asyncio cancellation.  By running the whole coroutine in its own thread we
    can use concurrent.futures.Future.result(timeout=N) which is a true OS-level
    wall-clock timeout: when it expires the caller gets TimeoutError immediately
    while the background thread drains naturally (daemon-style).
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Suppress "Task was destroyed" / "Event loop is closed" noise from litellm's
    # LoggingWorker background tasks when the thread's loop shuts down.
    loop.set_exception_handler(lambda _loop, _ctx: None)
    try:
        return loop.run_until_complete(run_turns(agent, turns))
    finally:
        # Cancel and drain any lingering tasks (e.g. litellm LoggingWorker)
        # so they don't emit RuntimeError spam when the loop closes.
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        loop.close()

# ── Two-phase test runner ─────────────────────────────────────────────────────
# Phase 1 — collect agent responses (agent model stays hot, no judge calls)
# Phase 2 — batch-judge all collected responses (judge model stays hot, no swaps)
#
# On Apple Silicon / Ollama, keeping only one model loaded at a time prevents
# memory pressure from simultaneous model residency, cutting inference time by
# ~40% compared to interleaving agent and judge calls per test.

async def collect_agent_response(tc: dict, *, agent) -> tuple["TestResult", list[TurnResult] | None]:
    """Run the agent turns and return raw responses. Does NOT call the judge."""
    start = datetime.now()
    result = TestResult(
        id=tc["id"],
        agent_id=tc["agent"],
        name=tc["name"],
        expected=tc.get("expected", ""),
    )

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    thread_future = executor.submit(_run_turns_in_thread, agent, tc["turns"])
    executor.shutdown(wait=False)

    try:
        loop = asyncio.get_event_loop()
        turns = await loop.run_in_executor(
            None,
            lambda: thread_future.result(timeout=TIMEOUT_SECONDS),
        )
        result.turns = turns
        result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
        return result, turns

    except concurrent.futures.TimeoutError:
        result.status = "ERROR"
        result.error = f"Timed out after {TIMEOUT_SECONDS}s"
    except Exception:
        result.status = "ERROR"
        result.error = traceback.format_exc()

    result.duration_ms = int((datetime.now() - start).total_seconds() * 1000)
    return result, None


async def evaluate_with_judge(result: "TestResult", turns: list[TurnResult]) -> None:
    """Judge a pre-collected response and write status/score/verdict into result."""
    if not turns or not turns[-1].response:
        result.status = "FAIL"
        result.verdict = "Agent returned no response."
        return
    try:
        status, score, verdict = await judge(turns, result.expected)
        result.status = status
        result.score = score
        result.verdict = verdict
    except Exception:
        result.status = "ERROR"
        result.error = traceback.format_exc()

# ── HTML report ───────────────────────────────────────────────────────────────
STATUS_COLOR = {"PASS": "#22c55e", "FAIL": "#ef4444", "SKIP": "#f59e0b", "ERROR": "#8b5cf6"}
STATUS_BG    = {"PASS": "#f0fdf4", "FAIL": "#fef2f2", "SKIP": "#fffbeb", "ERROR": "#f5f3ff"}

def render_html(results: list[TestResult], run_at: str) -> str:
    total  = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped= sum(1 for r in results if r.status == "SKIP")
    errors = sum(1 for r in results if r.status == "ERROR")
    pct    = int(passed / total * 100) if total else 0

    cards = ""
    for r in results:
        color  = STATUS_COLOR.get(r.status, "#6b7280")
        bg     = STATUS_BG.get(r.status, "#f9fafb")
        turns_html = ""
        for i, t in enumerate(r.turns):
            turns_html += f"""
            <div class="turn">
              <div class="label">Turn {i+1} — Prompt</div>
              <div class="prompt-box">{_esc(t.prompt)}</div>
              <div class="label">Response</div>
              <div class="response-box">{_esc(t.response) if t.response else '<em>No response</em>'}</div>
            </div>"""

        error_html = f'<div class="error-box">{_esc(r.error)}</div>' if r.error else ""
        score_html = f'<span class="score">Score: {r.score}/10</span>' if r.score else ""

        cards += f"""
        <details class="card" data-status="{r.status}" style="border-left:4px solid {color}; background:{bg}">
          <summary class="card-header">
            <span class="tc-id">{_esc(r.id)}</span>
            <span class="tc-name">{_esc(r.name)}</span>
            <span class="tc-agent">agent: {_esc(r.agent_id)}</span>
            <span class="badge" style="background:{color}">{r.status}</span>
            <span class="duration">{r.duration_ms}ms</span>
          </summary>
          <div class="card-body">
            <div class="section">
              <div class="label">Expected behaviour</div>
              <div class="expected-box">{_esc(r.expected)}</div>
            </div>
            {turns_html}
            {error_html}
            <div class="verdict-box">
              <strong>Judge verdict:</strong> {score_html} — {_esc(r.verdict)}
            </div>
          </div>
        </details>"""

    filter_btns = "".join(
        f'<button class="filter-btn" data-filter="{s}" onclick="filterCards(\'{s}\')">'
        f'<span style="color:{STATUS_COLOR[s]}">●</span> {s} ({cnt})</button>'
        for s, cnt in [("PASS", passed), ("FAIL", failed), ("SKIP", skipped), ("ERROR", errors)]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ADK Test Report — {run_at}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f8fafc; color: #1e293b; padding: 24px; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
  .meta {{ color: #64748b; font-size: 0.85rem; margin-bottom: 24px; }}
  .summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }}
  .stat {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
           padding: 12px 20px; text-align: center; min-width: 90px; }}
  .stat-num {{ font-size: 1.8rem; font-weight: 700; }}
  .stat-lbl {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }}
  .progress-bar {{ background: #e2e8f0; border-radius: 999px; height: 10px;
                   margin-bottom: 20px; overflow: hidden; }}
  .progress-fill {{ height: 100%; background: #22c55e; border-radius: 999px;
                    transition: width .3s; width: {pct}%; }}
  .filters {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
  .filter-btn {{ border: 1px solid #e2e8f0; background: #fff; border-radius: 6px;
                 padding: 6px 14px; cursor: pointer; font-size: 0.85rem; }}
  .filter-btn:hover {{ background: #f1f5f9; }}
  .filter-btn.active {{ background: #1e293b; color: #fff; border-color: #1e293b; }}
  .card {{ border-radius: 8px; margin-bottom: 12px; overflow: hidden; }}
  .card-header {{ display: flex; align-items: center; gap: 10px; padding: 12px 16px;
                  cursor: pointer; list-style: none; flex-wrap: wrap; }}
  .card-header::-webkit-details-marker {{ display: none; }}
  .tc-id {{ font-weight: 700; font-size: 0.85rem; min-width: 80px; }}
  .tc-name {{ flex: 1; font-size: 0.9rem; }}
  .tc-agent {{ font-size: 0.78rem; color: #64748b; font-family: monospace; }}
  .badge {{ font-size: 0.75rem; font-weight: 700; color: #fff; border-radius: 4px;
            padding: 2px 8px; letter-spacing: .05em; }}
  .duration {{ font-size: 0.75rem; color: #94a3b8; }}
  .score {{ font-weight: 600; }}
  .card-body {{ padding: 16px; border-top: 1px solid rgba(0,0,0,.06); display: flex;
                flex-direction: column; gap: 12px; }}
  .section {{ display: flex; flex-direction: column; gap: 6px; }}
  .label {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
            letter-spacing: .06em; color: #64748b; }}
  .turn {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px;
           display: flex; flex-direction: column; gap: 8px; }}
  .prompt-box {{ font-style: italic; color: #475569; white-space: pre-wrap; }}
  .response-box {{ white-space: pre-wrap; font-size: 0.9rem; max-height: 300px;
                   overflow-y: auto; background: #fff; border: 1px solid #e2e8f0;
                   border-radius: 4px; padding: 8px; }}
  .expected-box {{ color: #475569; font-size: 0.88rem; white-space: pre-wrap; }}
  .verdict-box {{ background: #f1f5f9; border-radius: 6px; padding: 10px 14px; font-size: 0.88rem; }}
  .error-box {{ background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px;
                padding: 10px; font-family: monospace; font-size: 0.8rem; white-space: pre-wrap;
                color: #b91c1c; max-height: 200px; overflow-y: auto; }}
  .hidden {{ display: none; }}
</style>
</head>
<body>
<h1>ADK Agent Test Report</h1>
<div class="meta">Run at: {run_at} &nbsp;·&nbsp; {total} test cases</div>

<div class="summary">
  <div class="stat"><div class="stat-num">{total}</div><div class="stat-lbl">Total</div></div>
  <div class="stat"><div class="stat-num" style="color:#22c55e">{passed}</div><div class="stat-lbl">Passed</div></div>
  <div class="stat"><div class="stat-num" style="color:#ef4444">{failed}</div><div class="stat-lbl">Failed</div></div>
  <div class="stat"><div class="stat-num" style="color:#f59e0b">{skipped}</div><div class="stat-lbl">Skipped</div></div>
  <div class="stat"><div class="stat-num" style="color:#8b5cf6">{errors}</div><div class="stat-lbl">Errors</div></div>
  <div class="stat"><div class="stat-num">{pct}%</div><div class="stat-lbl">Pass rate</div></div>
</div>

<div class="progress-bar"><div class="progress-fill"></div></div>

<div class="filters">
  <button class="filter-btn active" data-filter="ALL" onclick="filterCards('ALL')">All ({total})</button>
  {filter_btns}
</div>

{cards}

<script>
  function filterCards(status) {{
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`[data-filter="${{status}}"]`).classList.add('active');
    document.querySelectorAll('.card').forEach(c => {{
      c.classList.toggle('hidden', status !== 'ALL' && c.dataset.status !== status);
    }});
  }}
</script>
</body>
</html>"""

def _esc(text: str) -> str:
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="ADK Test Runner")
    parser.add_argument("--filter", help="Only run test IDs matching this prefix (e.g. TC-M)")
    parser.add_argument("--agent", help="Only run tests for this agent id")
    args = parser.parse_args()

    # Load .env
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv())

    # Ensure judge model is available locally
    import subprocess
    pulled = subprocess.run(
        ["ollama", "list"], capture_output=True, text=True
    )
    if JUDGE_MODEL_NAME not in pulled.stdout:
        print(f" Judge model '{JUDGE_MODEL_NAME}' not found — pulling now...")
        subprocess.run(["ollama", "pull", JUDGE_MODEL_NAME], check=True)
        print(f" Judge model '{JUDGE_MODEL_NAME}' ready\n")
    else:
        print(f" Judge model '{JUDGE_MODEL_NAME}' already available")

    # Pre-warm models into GPU memory (Ollama / Apple Silicon only).
    # Skipped for Gemini — no local GPU involved.
    if not IS_GEMINI:
        await _prewarm_ollama_models()

    # Load test cases
    yaml_path = Path(__file__).parent / "test_cases.yaml"
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    test_cases = data["test_cases"]

    # Auto-select test suite based on provider unless --filter is explicitly given.
    # TC-OL-* = lenient Ollama tests  |  all others = Gemini-quality tests
    if args.filter:
        test_cases = [tc for tc in test_cases if tc["id"].startswith(args.filter)]
    elif not IS_GEMINI:
        test_cases = [tc for tc in test_cases if tc["id"].startswith("TC-OL-")]
        print(f" Ollama mode detected — running lenient TC-OL-* tests only")
        print(f" (use --filter to override, e.g. --filter TC-A)\n")
    else:
        test_cases = [tc for tc in test_cases if not tc["id"].startswith("TC-OL-")]
    if args.agent:
        test_cases = [tc for tc in test_cases if tc["agent"] == args.agent]

    # Pre-load all agents needed for the filtered test cases.
    # This separates import time from test execution time so agent loading
    # messages appear cleanly before any test runs, and do not consume
    # the per-test timeout budget.
    print(f"\n Loading agents ...", end=" ", flush=True)
    agent_cache: dict = {}
    skip_agents: set = set()
    needed = {tc["agent"] for tc in test_cases}
    for agent_id in needed:
        try:
            agent_cache[agent_id] = load_agent(agent_id)
        except Exception as e:
            skip_agents.add(agent_id)
            print(f"\n  Skipping '{agent_id}': {e}", end="", flush=True)
    print(f" done ({len(agent_cache)} loaded, {len(skip_agents)} skipped)\n")

    print(f" ADK Test Runner — {len(test_cases)} test(s) to run\n{'─'*50}")

    # ── Phase 1: collect all agent responses ──────────────────────────────────
    # The agent model is already warm from pre-warming. Running all agent calls
    # back-to-back keeps it resident with no model swaps.
    print(f"\n Phase 1 — collecting agent responses\n{'─'*50}")
    results: list[TestResult] = []
    pending_judge: list[tuple[TestResult, list[TurnResult]]] = []

    for tc in test_cases:
        print(f"  {tc['id']} [{tc['agent']}] {tc['name']} ...", end=" ", flush=True)
        if tc["agent"] in skip_agents:
            result = TestResult(
                id=tc["id"], agent_id=tc["agent"], name=tc["name"],
                status="SKIP", verdict="Agent failed to load",
                expected=tc.get("expected", ""),
            )
            results.append(result)
            print("– SKIP")
            continue

        result, turns = await collect_agent_response(tc, agent=agent_cache[tc["agent"]])
        results.append(result)
        if turns is not None:
            pending_judge.append((result, turns))
            print(f"collected ({result.duration_ms}ms)")
        else:
            first_line = result.error.strip().splitlines()[-1] if result.error else ""
            print(f"! ERROR ({result.duration_ms}ms)  {first_line}")

    # ── Phase 2: warm judge, then batch-evaluate all collected responses ───────
    if pending_judge:
        if not IS_GEMINI:
            print(f"\n Phase 2 — pre-warming judge '{JUDGE_MODEL_NAME}' ...", end=" ", flush=True)
            import httpx
            api_base = JUDGE_API_BASE.rstrip("/")
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{api_base}/api/chat",
                        json={"model": JUDGE_MODEL_NAME,
                              "messages": [{"role": "user", "content": "hi"}],
                              "keep_alive": "30m", "stream": False},
                        timeout=120.0,
                    )
                print("ready")
            except Exception as e:
                print(f"skipped ({e})")

        print(f"\n Phase 2 — judging {len(pending_judge)} response(s)\n{'─'*50}")
        for result, turns in pending_judge:
            print(f"  {result.id} [{result.agent_id}] {result.name} ...", end=" ", flush=True)
            judge_start = datetime.now()
            await evaluate_with_judge(result, turns)
            judge_ms = int((datetime.now() - judge_start).total_seconds() * 1000)
            status_icon = {"PASS": "✓", "FAIL": "✗", "ERROR": "!"}.get(result.status, "?")
            print(f"{status_icon} {result.status}  agent {result.duration_ms}ms / judge {judge_ms}ms")
            if result.verdict:
                print(f"    {result.verdict}")
            if result.error:
                print(f"    ERROR: {result.error.strip().splitlines()[-1]}")

    # Summary
    passed = sum(1 for r in results if r.status == "PASS")
    total  = len(results)
    print(f"\n{'─'*50}")
    print(f"  Results: {passed}/{total} passed ({int(passed/total*100) if total else 0}%)\n")

    # Write HTML report
    run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_dir = Path(__file__).parent / "reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

    html = render_html(results, run_at)
    report_path.write_text(html)
    print(f"  Report saved: {report_path}")
    print(f"  Open with:   open {report_path}\n")

if __name__ == "__main__":
    asyncio.run(main())
