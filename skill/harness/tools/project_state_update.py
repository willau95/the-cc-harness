#!/usr/bin/env python3
"""project_state_update — append a fact to project-layer shared state (T2.d).

Example: project_state_update.py --project my-app --key tech_stack --value '["Python","FastAPI"]'

Use sparingly — project state is shared across ALL agents on this project.
Don't write agent-specific things here (use checkpoint for that).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from harness import project, identity
from _common import find_project_root, emit, emit_error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=None)
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", required=True,
                    help="Value. If starts with '[' or '{' parsed as JSON.")
    args = ap.parse_args()

    ident = identity.load_identity(find_project_root())
    if not ident:
        emit_error("no agent initialized")

    proj = args.project or Path(ident["folder"]).name

    value = args.value
    if value.startswith(("[", "{")):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            pass  # keep as string

    project.update_state(proj, args.key, value, by=ident["agent_id"])
    emit({"ok": True, "project": proj, "key": args.key})


if __name__ == "__main__":
    main()
