#!/usr/bin/env python3
"""request_budget_extension — Hermes grace call.
Use when task_budget.remaining < 10% but the task genuinely needs more iterations.
Writes a proposal; human approves via Dashboard /budgets page.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from harness import budget, identity
from _common import find_project_root, emit, emit_error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--extra", type=int, required=True, help="Extra iterations needed.")
    ap.add_argument("--reason", required=True)
    args = ap.parse_args()

    root = find_project_root()
    ident = identity.load_identity(root)
    if not ident:
        emit_error("no agent initialized")
    try:
        rec = budget.request_extension(root, args.task_id, ident["agent_id"],
                                       args.extra, args.reason)
    except Exception as e:
        emit_error(str(e))
    emit({"ok": True, "proposal_id": rec["id"], "status": rec["status"]})


if __name__ == "__main__":
    main()
