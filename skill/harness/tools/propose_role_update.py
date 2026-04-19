#!/usr/bin/env python3
"""propose_role_update — propose a lesson to add to a role's evolved preamble.

Example:
  propose_role_update.py --role researcher \
    --lesson "When WebFetch fails, try curl with -L -v for connectivity first."
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from harness import proposals, identity
from _common import find_project_root, emit, emit_error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--lesson", required=True)
    ap.add_argument("--evidence", default="",
                    help="Primary source supporting the lesson (URL / event log ts)")
    args = ap.parse_args()

    ident = identity.load_identity(find_project_root())
    if not ident:
        emit_error("no agent initialized")

    rec = proposals.create("role", ident["agent_id"], {
        "role": args.role,
        "lesson": args.lesson,
        "evidence": args.evidence,
    })
    emit({"ok": True, "proposal_id": rec["id"], "status": rec["status"]})


if __name__ == "__main__":
    main()
