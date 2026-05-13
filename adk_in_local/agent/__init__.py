from config import MODEL, SEARCH_TOOLS, IS_GEMINI
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.adk.agents import Agent
from dotenv import load_dotenv

# Retry config is Gemini-specific — only applied when not using Ollama/LiteLLM.
# See: https://google.github.io/adk-docs/agents/models/google-gemini/#error-code-429-resource_exhausted
_retry_config = None
if IS_GEMINI:
    try:
        from google.genai import types
        _retry_config = types.GenerateContentConfig(
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(initial_delay=2, attempts=3),
            ),
        )
    except Exception:
        pass

# Single source of truth: project root .env covers all modules
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# ---------------------------------------------------------------------------
# Conditionally import each agent module. If a module's dependencies are
# missing (e.g. toolbox_core for g_agents_mcp), it is skipped silently and
# the agent simply won't appear as a sub-agent in the UI.
# ---------------------------------------------------------------------------

_available_agents = []
_routing_lines = []
_example_lines = []


def _try_load(label, import_fn):
    """Attempt to import an agent; log a warning and skip on failure."""
    try:
        agent = import_fn()
        _available_agents.append(agent)
        return agent
    except Exception as e:
        print(f"  Skipping '{label}': {e}")
        return None


# a — Dating / outing planner
_a = _try_load(
    "a_single_agent (dating planner)",
    lambda: __import__("a_single_agent.day_trip", fromlist=["root_agent"]).root_agent,
)

# b1 — Find location + navigate
_b1 = _try_load(
    "b1_sequential_agent (find & navigate)",
    lambda: __import__("b1_sequential_agent.agents", fromlist=["find_and_navigate_agent"]).find_and_navigate_agent,
)

# b2 — Parallel multi-item search
_b2 = _try_load(
    "b2_parallel_agent (parallel planner)",
    lambda: __import__("b2_parallel_agent.agents", fromlist=["parallel_planner_agent"]).parallel_planner_agent,
)

# b3 — Iterative / constraint-based planner
_b3 = _try_load(
    "b3_loop_agent (iterative planner)",
    lambda: __import__("b3_loop_agent.agents", fromlist=["iterative_planner_agent"]).iterative_planner_agent,
)

# c — Budget-aware custom agent
_c = _try_load(
    "c_custom_agent (budget planner)",
    lambda: __import__("c_custom_agent.agents", fromlist=["root_agent"]).root_agent,
)

# e — Trip architect (agents-as-tools)
_e = _try_load(
    "e_agent_as_tool (trip architect)",
    lambda: __import__("e_agent_as_tool.agents", fromlist=["root_agent"]).root_agent,
)

# f — Memory-aware coordinator
_f = _try_load(
    "f_agent_with_memory (memory coordinator)",
    lambda: __import__("f_agent_with_memory.agents", fromlist=["root_agent"]).root_agent,
)

# g — MCP toolbox agent (requires external toolbox server)
_g = _try_load(
    "g_agents_mcp (MCP trip planner)",
    lambda: __import__("g_agents_mcp.trip_agent", fromlist=["root_agent"]).root_agent,
)

# ---------------------------------------------------------------------------
# Build routing instruction dynamically from whatever loaded successfully
# ---------------------------------------------------------------------------

_routing_guide = []
_examples = []

if _c:
    _routing_guide.append("- **Budget mentioned** (e.g. \"$75\", \"cheap\", \"under 100\") → `BudgetAwarePlannerAgent`")
    _examples.append("- \"Plan a day in SF for under $50\" → `BudgetAwarePlannerAgent`")

if _b2:
    _routing_guide.append("- **Multiple diverse items at once** (e.g. museum + concert + restaurant) → `parallel_planner_agent`")
    _examples.append("- \"Find me a museum, a jazz concert, and a taco spot\" → `parallel_planner_agent`")

if _b3:
    _routing_guide.append("- **Optimization / iteration needed** (e.g. \"minimize travel time\") → `iterative_planner_agent`")
    _examples.append("- \"Plan activities close together to avoid long drives\" → `iterative_planner_agent`")

if _b1:
    _routing_guide.append("- **Find a specific place + get directions** → `find_and_navigate_agent`")
    _examples.append("- \"Find the best ramen in Sunnyvale and get me directions from San Jose\" → `find_and_navigate_agent`")

if _e:
    _routing_guide.append("- **Full logistical trip with self-correction** → `TripArchitectAgent`")
    _examples.append("- \"Plan a museum visit and lunch nearby\" → `TripArchitectAgent`")

if _f:
    _routing_guide.append("- **Personalized planning / returning user** → `MemoryCoordinatorAgent`")
    _examples.append("- \"Plan my weekend, I love hiking and coffee\" → `MemoryCoordinatorAgent`")

if _a:
    _routing_guide.append("- **Dating / outing / weekend plan** (creative, fun) → `planner_agent`")
    _examples.append("- \"Plan a date night — we like art and good food\" → `planner_agent`")

if _g:
    _routing_guide.append("- **Database-backed destination search** → `trip_planner_agent`")
    _examples.append("- \"Find top-rated things to do in Seattle\" → `trip_planner_agent`")

_fallback = (
    f"- **General / anything else** → `{_e.name}`"
    if _e
    else ("- **General / anything else** → `{}`".format(_available_agents[0].name) if _available_agents else "")
)

_instruction = f"""
You are a master travel and activity coordinator. Analyze the user's request and delegate
to the single most appropriate specialist agent. Return the specialist's full response.

--- Routing Guide ---
{chr(10).join(_routing_guide)}
{_fallback}

--- Examples ---
{chr(10).join(_examples)}
""".strip()

# ---------------------------------------------------------------------------
# Root agent
# ---------------------------------------------------------------------------

_agent_kwargs = dict(
    name="master_orchestrator",
    model=MODEL,
    description="Master coordinator — routes requests to the best available specialist agent.",
    instruction=_instruction,
    sub_agents=_available_agents,
)
if _retry_config is not None:
    _agent_kwargs["generate_content_config"] = _retry_config

root_agent = Agent(**_agent_kwargs)

print(f" Master Orchestrator ready — {len(_available_agents)} agent(s) loaded: "
      f"{[a.name for a in _available_agents]}")
