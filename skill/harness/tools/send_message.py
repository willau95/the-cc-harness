#!/usr/bin/env python3
"""send_message — send a message to a peer agent.

Usage:
  send_message.py --to <agent_id> --subject <short> --body <text> [--task-id <id>]
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from harness import mailbox, identity, eventlog
from _common import find_project_root, emit, emit_error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", required=True)
    ap.add_argument("--task-id", default=None)
    args = ap.parse_args()

    root = find_project_root()
    ident = identity.load_identity(root)
    if not ident:
        emit_error("no agent initialized in current folder")

    try:
        env = mailbox.send(
            from_id=ident["agent_id"],
            to_id=args.to,
            subject=args.subject,
            body=args.body,
        )
    except Exception as e:
        emit_error(str(e))

    emit({"ok": True, "msg_id": env["msg_id"], "to": args.to})


if __name__ == "__main__":
    main()
