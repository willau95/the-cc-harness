"""Shared helper for skill tools: locate agent, emit JSON, auto-heartbeat, respect pause."""
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
    """Best-effort heartbeat on every tool call."""
    try:
        from harness import identity, heartbeat  # type: ignore
        ident = identity.load_identity(find_project_root())
        if ident:
            heartbeat.beat(ident["agent_id"], via="tool_call")
    except Exception:
        pass


def _check_pause() -> bool:
    """Return True if the agent folder has a .harness/paused sentinel.
    Dashboard writes this when human clicks Pause. Tools should short-circuit."""
    try:
        return (find_project_root() / ".harness" / "paused").exists()
    except Exception:
        return False


def emit(obj: dict) -> None:
    _beat_current_agent()
    if _check_pause() and obj.get("ok") is not False:
        obj = {"ok": False, "paused": True,
               "error": "agent is paused (human gate); resume via dashboard or remove .harness/paused"}
    json.dump(obj, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def emit_error(msg: str, code: int = 1) -> None:
    _beat_current_agent()
    json.dump({"ok": False, "error": msg}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(code)
