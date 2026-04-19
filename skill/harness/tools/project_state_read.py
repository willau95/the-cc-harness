#!/usr/bin/env python3
"""project_state_read — read project-layer shared state (T2.d)."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from harness import project, identity
from _common import find_project_root, emit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=None,
                    help="Project slug. Defaults to folder name.")
    args = ap.parse_args()

    ident = identity.load_identity(find_project_root())
    proj = args.project or (Path.cwd().name if not ident else Path(ident["folder"]).name)
    state = project.read_state(proj)
    members = project.active_members(proj)
    emit({"ok": True, "project": proj, "state": state["values"],
          "state_meta": state["meta"], "members": members})


if __name__ == "__main__":
    main()
