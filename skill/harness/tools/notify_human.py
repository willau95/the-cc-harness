#!/usr/bin/env python3
"""notify_human — cross-machine / async human signal.

NOTE: For LOCAL (same machine) blocking questions, use Claude Code's native
AskUserQuestion tool. This tool is for:
  - cross-machine: agent on Machine B wants to ping human watching Machine A
  - async: info/attention without blocking this turn
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from harness import notify as notify_mod, identity
from _common import find_project_root, emit, emit_error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urgency", required=True, choices=["info", "attention", "blocker"])
    ap.add_argument("--reason", required=True)
    ap.add_argument("--context", default="")
    ap.add_argument("--suggested-action", default=None)
    args = ap.parse_args()

    root = find_project_root()
    ident = identity.load_identity(root)
    if not ident:
        emit_error("no agent initialized")
    res = notify_mod.notify(ident["agent_id"], args.urgency, args.reason,
                            args.context, args.suggested_action)
    emit({"ok": True, **res})


if __name__ == "__main__":
    main()
