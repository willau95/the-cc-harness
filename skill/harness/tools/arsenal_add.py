#!/usr/bin/env python3
"""arsenal_add — add a knowledge entry with provenance.

Trust is auto-assigned:
  - source_type=web/file with URLs → verified
  - source_type=agent_summary → agent_summary (filtered from default search)
  - source_type=agent_hypothesis → hypothesis (filtered from default search)
  - source_type=human_input → human_verified
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from harness import arsenal, identity
from _common import find_project_root, emit, emit_error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=None)
    ap.add_argument("--title", required=True)
    ap.add_argument("--content", required=True, help="Content text, or @path to read file")
    ap.add_argument("--tags", default="", help="Comma-separated")
    ap.add_argument("--source-type", default="agent_summary",
                    choices=["web", "file", "agent_summary", "agent_hypothesis", "human_input"])
    ap.add_argument("--source-refs", default="", help="Comma-separated URLs or paths")
    ap.add_argument("--derived-from", default="", help="Comma-separated slugs")
    args = ap.parse_args()

    if args.content.startswith("@"):
        args.content = Path(args.content[1:]).read_text()

    root = find_project_root()
    ident = identity.load_identity(root)
    by = ident["agent_id"] if ident else "unknown"

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    source_refs = [r.strip() for r in args.source_refs.split(",") if r.strip()]
    derived = [s.strip() for s in args.derived_from.split(",") if s.strip()]

    # Safety net: if source_type=web but no URL supplied, downgrade
    if args.source_type in ("web", "file") and not source_refs:
        emit_error(f"source_type={args.source_type} requires --source-refs")

    meta = arsenal.add(
        slug=args.slug, title=args.title, content=args.content,
        tags=tags, source_type=args.source_type,
        source_refs=source_refs, produced_by=by, derived_from=derived,
    )
    emit({"ok": True, "slug": meta["slug"], "trust": meta["trust"],
          "verification_status": meta["verification_status"]})


if __name__ == "__main__":
    main()
