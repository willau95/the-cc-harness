"""Shared helper for skill tools: locate agent, emit JSON, auto-heartbeat."""
from __future__ import annotations
import json
import sys
from pathlib import Path


def find_project_root() -> Path:
    """Walk up from cwd to find the directory containing .harness/agent.yaml."""
    p = Path.cwd()
    for cand in [p, *p.parents]:
        if (cand / ".harness" / "agent.yaml").exists():
            return cand
    return p  # fallback


def _beat_current_agent() -> None:
    """Best-effort heartbeat. Called automatically on every tool invocation.

    Without this, agents get marked zombie 10 min after init even if they're
    actively using Claude Code, because heartbeats otherwise fire only at
    init and at SessionStart/PreCompact hooks.
    """
    try:
        from harness import identity, heartbeat  # type: ignore
        ident = identity.load_identity(find_project_root())
        if ident:
            heartbeat.beat(ident["agent_id"], via="tool_call")
    except Exception:
        pass  # heartbeat is best-effort; never break the tool


def emit(obj: dict) -> None:
    _beat_current_agent()
    json.dump(obj, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def emit_error(msg: str, code: int = 1) -> None:
    _beat_current_agent()
    json.dump({"ok": False, "error": msg}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(code)
