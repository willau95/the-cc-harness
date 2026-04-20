"""Shared helper for skill tools: locate agent, emit JSON, auto-heartbeat, respect pause."""
from __future__ import annotations
import json
import sys
from pathlib import Path


def find_project_root() -> Path:
    """Walk up from cwd to find the directory containing .harness/agent.yaml."""
    p = Path.cwd()
    for cand in [p, *p.parents]:
        if (cand / ".harness" / "agent.yaml").exists():
            return cand
    return p  # fallback


def _beat_current_agent() -> None:
    """Best-effort heartbeat on every tool call."""
    try:
        from harness import identity, heartbeat  # type: ignore
        ident = identity.load_identity(find_project_root())
        if ident:
            heartbeat.beat(ident["agent_id"], via="tool_call")
    except Exception:
        pass


def _check_pause() -> bool:
    """Return True if the agent folder has a .harness/paused sentinel.
    Dashboard writes this when human clicks Pause. Tools should short-circuit."""
    try:
        return (find_project_root() / ".harness" / "paused").exists()
    except Exception:
        return False


def _surface_new_inbox() -> list[dict] | None:
    """Check this agent's inbox for messages that arrived since the last tool
    call and weren't yet read. Return a list of compact summaries if any,
    else None. The dashboard / CLI writes an envelope when a human (or peer)
    sends a message; this hook surfaces them on the very next tool call so
    claude sees them without the user having to type 'check inbox'."""
    try:
        from harness import identity, mailbox  # type: ignore
        folder = find_project_root()
        ident = identity.load_identity(folder)
        if not ident:
            return None
        aid = ident["agent_id"]
        # Track which envelopes we've already surfaced so we don't repeat them
        import json as _json
        seen_path = folder / ".harness" / "inbox_seen.json"
        seen: set[str] = set()
        if seen_path.exists():
            try:
                seen = set(_json.loads(seen_path.read_text()) or [])
            except Exception:
                seen = set()
        all_msgs = mailbox.peek(aid, limit=50)
        fresh = [m for m in all_msgs if m.get("msg_id") not in seen]
        if not fresh:
            return None
        # Record as seen so the next tool call doesn't re-show them
        try:
            new_seen = list(seen | {m.get("msg_id") for m in fresh if m.get("msg_id")})
            seen_path.write_text(_json.dumps(new_seen[-500:]))
        except Exception:
            pass
        return [{
            "from": m.get("from"),
            "subject": m.get("subject"),
            "body": (m.get("body") or "")[:2000],
            "created_at": m.get("created_at"),
            "msg_id": m.get("msg_id"),
        } for m in fresh]
    except Exception:
        return None


def emit(obj: dict) -> None:
    _beat_current_agent()
    if _check_pause() and obj.get("ok") is not False:
        obj = {"ok": False, "paused": True,
               "error": "agent is paused (human gate); resume via dashboard or remove .harness/paused"}
    # Piggyback new inbox messages onto every successful tool result so claude
    # reads them on its very next turn. Presented as _notify so role templates
    # can teach claude to check this field.
    if obj.get("ok") is not False:
        new_msgs = _surface_new_inbox()
        if new_msgs:
            obj = {**obj,
                   "_notify": {
                       "type": "new_inbox_messages",
                       "count": len(new_msgs),
                       "messages": new_msgs,
                       "instruction": "You have new inbox messages. Read them and respond appropriately before continuing your current task.",
                   }}
    json.dump(obj, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def emit_error(msg: str, code: int = 1) -> None:
    _beat_current_agent()
    json.dump({"ok": False, "error": msg}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(code)
