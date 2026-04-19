"""Helper used by all skill tools: resolve current agent from cwd."""
from __future__ import annotations
import json
import sys
from pathlib import Path


def find_project_root() -> Path:
    """Walk up from cwd to find the directory with .harness/ subdir."""
    p = Path.cwd()
    for cand in [p, *p.parents]:
        if (cand / ".harness" / "agent.yaml").exists():
            return cand
    return p  # fallback


def emit(obj: dict) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def emit_error(msg: str, code: int = 1) -> None:
    emit({"ok": False, "error": msg})
    sys.exit(code)
