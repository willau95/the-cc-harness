"""Mirror Claude Code's per-session JSONL transcripts into the dashboard.

Claude Code writes every user/assistant turn + tool_use/tool_result to
~/.claude/projects/<slash-to-dash path>/<session-uuid>.jsonl.

We parse those files and expose a cleaned-up timeline so the dashboard can
show what the agent is actually doing (prompts, thinking, tool calls,
results) without the user having to switch to the terminal.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Iterable


CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


def folder_to_project_dir(folder: str | Path) -> Path:
    """Translate an agent folder to the Claude Code projects dir. The
    convention is slashes replaced by dashes, with a leading dash."""
    p = str(Path(folder).resolve())
    slug = p.replace("/", "-")
    return CLAUDE_PROJECTS / slug


def latest_session_file(folder: str | Path) -> Path | None:
    """Find the most recent .jsonl for this agent folder, or None if no
    claude session has ever been started in it."""
    d = folder_to_project_dir(folder)
    if not d.exists():
        return None
    candidates = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _summarize_tool_input(name: str, args: dict) -> str:
    """Return a short human-readable summary of a tool_use input."""
    if not isinstance(args, dict):
        return ""
    if name in {"Read", "Edit", "Write", "NotebookEdit"}:
        return str(args.get("file_path") or args.get("notebook_path") or "")[:200]
    if name == "Bash":
        return str(args.get("command", ""))[:240]
    if name == "Grep":
        return (str(args.get("pattern", ""))[:80] +
                (f" · path={args.get('path')}" if args.get("path") else ""))[:200]
    if name == "Glob":
        return str(args.get("pattern", ""))[:160]
    if name == "WebFetch":
        return str(args.get("url", ""))[:240]
    if name == "WebSearch":
        return str(args.get("query", ""))[:240]
    if name == "TodoWrite":
        todos = args.get("todos") or []
        return f"{len(todos)} todo{'s' if len(todos) != 1 else ''}"
    if name == "Task":
        return str(args.get("description", ""))[:160]
    # Generic fallback — short repr of keys
    keys = list(args.keys())[:3]
    return f"{{{', '.join(keys)}{'...' if len(args) > 3 else ''}}}"


def _extract_text(content: Any) -> str:
    """Pull readable text out of a user/assistant message content, which
    can be a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                chunks.append(block.get("text", ""))
            elif t == "tool_result":
                tr = block.get("content")
                if isinstance(tr, str):
                    chunks.append(tr)
                elif isinstance(tr, list):
                    for b in tr:
                        if isinstance(b, dict) and b.get("type") == "text":
                            chunks.append(b.get("text", ""))
        return "\n".join(chunks).strip()
    return ""


def read_timeline(folder: str | Path, limit: int = 500) -> list[dict]:
    """Return a normalized timeline for this agent's most recent session.
    Each entry: {ts, role, kind, text?, tool_name?, tool_input?, tool_id?}."""
    f = latest_session_file(folder)
    if not f:
        return []

    entries: list[dict] = []
    try:
        with f.open("r") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = rec.get("type")
                ts = rec.get("timestamp")
                if t == "user":
                    msg = rec.get("message") or {}
                    content = msg.get("content")
                    # User content may be a tool_result response (model just
                    # provided a tool's output back to claude). Break those
                    # out as tool_result entries; free-form text = user turn.
                    if isinstance(content, list):
                        for b in content:
                            if isinstance(b, dict) and b.get("type") == "tool_result":
                                # Summarize — tool_results can be enormous
                                result_text = _extract_text([b])
                                entries.append({
                                    "ts": ts,
                                    "role": "tool",
                                    "kind": "tool_result",
                                    "tool_id": b.get("tool_use_id"),
                                    "text": result_text[:4000],
                                    "truncated": len(result_text) > 4000,
                                    "is_error": bool(b.get("is_error")),
                                })
                        # Any text-block in the same user msg = actual user prompt
                        text = _extract_text([x for x in content if
                                              isinstance(x, dict) and x.get("type") == "text"])
                        if text:
                            entries.append({"ts": ts, "role": "user",
                                            "kind": "prompt", "text": text[:4000]})
                    elif isinstance(content, str) and content.strip():
                        entries.append({"ts": ts, "role": "user",
                                        "kind": "prompt", "text": content[:4000]})
                elif t == "assistant":
                    msg = rec.get("message") or {}
                    content = msg.get("content") or []
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        bt = b.get("type")
                        if bt == "text":
                            txt = b.get("text", "")
                            if txt.strip():
                                entries.append({"ts": ts, "role": "assistant",
                                                "kind": "text", "text": txt[:8000]})
                        elif bt == "thinking":
                            txt = b.get("thinking", "")
                            if txt.strip():
                                entries.append({"ts": ts, "role": "assistant",
                                                "kind": "thinking", "text": txt[:4000]})
                        elif bt == "tool_use":
                            entries.append({
                                "ts": ts, "role": "assistant", "kind": "tool_use",
                                "tool_name": b.get("name"),
                                "tool_id": b.get("id"),
                                "tool_input_summary": _summarize_tool_input(
                                    b.get("name", ""), b.get("input") or {}),
                                "tool_input": b.get("input") or {},
                            })
                elif t == "attachment":
                    # Hook firings — keep hook events, skip the rest
                    att = rec.get("attachment") or {}
                    hook = att.get("hookName")
                    if hook:
                        entries.append({
                            "ts": ts, "role": "system", "kind": "hook",
                            "hook_name": hook,
                            "text": (att.get("stdout") or "")[:1000],
                        })
    except OSError:
        return []

    return entries[-limit:]


def session_metadata(folder: str | Path) -> dict | None:
    """Return {session_id, file_path, mtime, size_bytes} or None."""
    f = latest_session_file(folder)
    if not f:
        return None
    try:
        st = f.stat()
        return {
            "session_id": f.stem,
            "file_path": str(f),
            "mtime": st.st_mtime,
            "size_bytes": st.st_size,
        }
    except OSError:
        return None
