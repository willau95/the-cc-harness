#!/usr/bin/env python3
"""checkpoint_read — show latest state of all active tasks, or one task."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from harness import checkpoint
from _common import find_project_root, emit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", default=None)
    args = ap.parse_args()
    root = find_project_root()
    if args.task_id:
        t = checkpoint.latest_for_task(root, args.task_id)
        emit({"ok": True, "task": t})
    else:
        tasks = checkpoint.active_tasks(root)
        emit({"ok": True, "active_count": len(tasks), "tasks": tasks})


if __name__ == "__main__":
    main()
