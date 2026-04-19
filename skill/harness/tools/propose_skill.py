#!/usr/bin/env python3
"""propose_skill — propose a new reusable skill for the whole fleet.

Triggered by skill nudge (after N tool iterations) or agent's own judgment.
The proposal goes to ~/.harness/proposals/skill/. Critic reviews. Human approves.
Upon human approval the skill gets written to ~/.harness/skills/global/<slug>/.
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
    ap.add_argument("--slug", required=True)
    ap.add_argument("--rationale", required=True,
                    help="Why this skill? E.g. 'I've done this pattern 3x this week'")
    ap.add_argument("--content", required=True,
                    help="Skill body (SKILL.md content) or @path to file")
    ap.add_argument("--tags", default="")
    args = ap.parse_args()

    if args.content.startswith("@"):
        args.content = Path(args.content[1:]).read_text()

    ident = identity.load_identity(find_project_root())
    if not ident:
        emit_error("no agent initialized")

    rec = proposals.create("skill", ident["agent_id"], {
        "slug": args.slug,
        "rationale": args.rationale,
        "content": args.content,
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
    })
    emit({"ok": True, "proposal_id": rec["id"], "status": rec["status"]})


if __name__ == "__main__":
    main()
