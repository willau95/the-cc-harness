#!/usr/bin/env python3
"""arsenal_get — full content + meta of one item by slug."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from harness import arsenal
from _common import emit, emit_error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    args = ap.parse_args()
    item = arsenal.get(args.slug)
    if not item:
        emit_error(f"not found: {args.slug}")
    emit({"ok": True, "item": item})


if __name__ == "__main__":
    main()
