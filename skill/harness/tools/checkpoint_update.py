#!/usr/bin/env python3
"""checkpoint_update — append a state/field update to the task checkpoint.

Common uses:
  checkpoint_update.py --task-id t1 --state IN_PROGRESS
  checkpoint_update.py --task-id t1 --state BLOCKED --blocked-on 'permission: push'
  checkpoint_update.py --task-id t1 --state AWAITING_REVIEW --deliverable-ref arsenal:xxx
  checkpoint_update.py --task-id t1 --next-step 'fetch remaining 2 candidates'
  checkpoint_update.py --create --original-goal 'find latest hooks tutorial'
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from harness import checkpoint
from _common import find_project_root, emit, emit_error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", default=None)
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--original-goal", default=None)
    ap.add_argument("--deliverable-spec", default="")
    ap.add_argument("--budget", type=int, default=None)
    ap.add_argument("--state", default=None)
    ap.add_argument("--blocked-on", default=None)
    ap.add_argument("--deliverable-ref", default=None)
    ap.add_argument("--next-step", default=None)
    args = ap.parse_args()

    root = find_project_root()

    try:
        if args.create:
            if not args.original_goal:
                emit_error("--create requires --original-goal")
            tid = checkpoint.create_task(root, args.original_goal,
                                         args.deliverable_spec, args.budget)
            emit({"ok": True, "created": True, "task_id": tid})
            return

        if not args.task_id:
            emit_error("--task-id required (or use --create)")

        kwargs = {}
        if args.blocked_on:
            kwargs["blocked_on"] = {"kind": "info", "detail": args.blocked_on}
        if args.deliverable_ref:
            kwargs["deliverable_ref"] = args.deliverable_ref
        if args.next_step:
            kwargs["next_step"] = args.next_step

        if args.state:
            entry = checkpoint.transition(root, args.task_id, args.state, **kwargs)
        elif kwargs:
            entry = checkpoint.update(root, args.task_id, **kwargs)
        else:
            emit_error("nothing to update")
        emit({"ok": True, "entry": entry})
    except ValueError as e:
        emit_error(str(e))


if __name__ == "__main__":
    main()
