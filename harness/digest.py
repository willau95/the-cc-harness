"""L5 — onCompact hook writes a Markdown digest from current session state.
Designed to run in the `onCompact` hook context provided by Claude Code.

Claude Code hook env (expected):
  CLAUDE_CODE_SESSION_ID      — current session id (if provided)
  CLAUDE_CODE_TRANSCRIPT      — path to transcript JSONL (may not exist in all versions)
  (we fall back to checkpoint + recent events + active tasks if transcript not available)

The digest is the raw material for L6 wake-up.
"""
from __future__ import annotations
import os
from pathlib import Path
from . import config, identity, checkpoint, eventlog
from ._util import atomic_write_text, now_iso


def _session_id() -> str:
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or now_iso().replace(":", "-")


def write_digest(agent_folder: Path) -> Path | None:
    """Write digest for the current session of this agent.
    Returns path or None if agent not initialized here.
    """
    ident = identity.load_identity(agent_folder)
    if not ident:
        return None
    agent_id = ident["agent_id"]
    session_id = _session_id()

    # Gather material
    active = checkpoint.active_tasks(agent_folder)
    recent_events = eventlog.recent(agent_id, limit=40)

    md_lines = [
        f"# Session digest — {session_id}",
        f"_generated: {now_iso()}_  ",
        f"_agent: {agent_id} · role: {ident.get('role')} · machine: {ident.get('machine')}_",
        "",
        "## Active tasks",
    ]
    if not active:
        md_lines.append("_none_")
    for t in active:
        md_lines.append(
            f"- **{t.get('task_id')}** — state={t.get('state')}"
        )
        md_lines.append(f"  - original_goal: {t.get('original_goal', '?')}")
        if t.get("next_step"):
            md_lines.append(f"  - next_step: {t['next_step']}")
        if t.get("blocked_on"):
            md_lines.append(f"  - blocked_on: {t['blocked_on']}")
        tb = t.get("task_budget") or {}
        if tb:
            md_lines.append(
                f"  - budget: used {tb.get('used', 0)} / {tb.get('max', '?')} "
                f"(remaining {tb.get('remaining', '?')})"
            )

    md_lines.append("")
    md_lines.append("## Recent events (last 40)")
    for e in recent_events:
        md_lines.append(
            f"- `{e.get('ts', '')}` {e.get('type', '?')} "
            f"{' '.join(f'{k}={v}' for k, v in e.items() if k not in ('ts', 'type'))}"
        )

    md_lines.append("")
    md_lines.append("## Notes")
    md_lines.append(
        "This digest is read at SessionStart to rebuild context after /compact or new session."
    )

    path = config.digest_file(agent_id, session_id)
    atomic_write_text(path, "\n".join(md_lines) + "\n")
    eventlog.log(agent_id, "digest_written", path=str(path), session_id=session_id)
    return path
