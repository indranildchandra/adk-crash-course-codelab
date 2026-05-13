"""
Central model configuration for all ADK agents.
Edit model.config (in this directory) to switch models — no code changes needed.
"""

import os

# Parse model.config (simple KEY=VALUE, ignores blank lines and comments)
_config = {}
_config_path = os.path.join(os.path.dirname(__file__), "model.config")
with open(_config_path) as _f:
    for _line in _f:
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            _config[_key.strip()] = _val.strip()

_provider = _config.get("MODEL_PROVIDER", "gemini").lower().strip()
_model_name = _config.get("MODEL_NAME", "gemini-2.5-flash").strip()

# Set OLLAMA_API_BASE in env if specified in model.config
if "OLLAMA_API_BASE" in _config:
    os.environ.setdefault("OLLAMA_API_BASE", _config["OLLAMA_API_BASE"])

if _provider == "ollama":
    from google.adk.models.lite_llm import LiteLlm
    MODEL = LiteLlm(model=f"ollama_chat/{_model_name}")
else:
    MODEL = _model_name

# SEARCH_TOOLS — use this in every agent instead of importing google_search directly.
#
# Gemini:  uses google_search (server-side grounding, best quality)
# Ollama:  uses DuckDuckGo (free, no API key, plain Python function tool)
#
# This demonstrates how any Python package can be plugged into ADK as a
# custom tool — just a typed function with a docstring, zero boilerplate.
if _provider == "ollama":
    from tools.duckduckgo_search import ddg_search
    SEARCH_TOOLS = [ddg_search]
else:
    from google.adk.tools import google_search
    SEARCH_TOOLS = [google_search]

IS_GEMINI = _provider != "ollama"

print(f" Model config: provider={_provider}, model={_model_name}")

# Test runner timeout (seconds per test case). Increase for slow local models.
TEST_TIMEOUT_SECONDS = int(_config.get("TEST_TIMEOUT_SECONDS", 300))

# Per-LLM-call cap for Ollama (litellm.request_timeout).
# Ensures timed-out background threads drain Ollama quickly and don't block the next test.
LLM_TIMEOUT_SECONDS = int(_config.get("LLM_TIMEOUT_SECONDS", 180))
