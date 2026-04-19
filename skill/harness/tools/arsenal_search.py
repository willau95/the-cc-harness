#!/usr/bin/env python3
"""arsenal_search — FTS5 search of shared knowledge base.
Default: returns only trust>=verified items. Use --all to include unverified.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from harness import arsenal
from _common import emit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--all", action="store_true", dest="include_unverified")
    args = ap.parse_args()
    results = arsenal.search(args.query, limit=args.limit,
                             include_unverified=args.include_unverified)
    emit({"ok": True, "count": len(results), "results": results})


if __name__ == "__main__":
    main()
