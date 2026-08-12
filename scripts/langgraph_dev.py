"""
Launch LangGraph Studio dev server.

Workaround for pathspec 1.1.1 Windows bug (re2 backend missing).
Usage: uv run python scripts/langgraph_dev.py
Then open: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
"""
import multiprocessing
import os
import sys
import types

# Required on Windows before any multiprocessing forks
multiprocessing.freeze_support()

# Patch pathspec re2 backend (broken on Windows in pathspec 1.1.1)
_re2_mod = types.ModuleType("pathspec._backends.re2.base")
_re2_mod.re2_error = Exception  # type: ignore[attr-defined]
sys.modules["pathspec._backends.re2.base"] = _re2_mod

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

if __name__ == "__main__":
    from langgraph_cli.cli import cli
    sys.argv = ["langgraph", "dev", "--no-browser"]
    cli()
