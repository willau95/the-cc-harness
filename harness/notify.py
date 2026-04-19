"""notify_human — cross-machine / async human signal.
v4 scope: **only for cross-machine or async cases**. For local blocking prompts,
agent should use Claude Code's native AskUserQuestion tool instead.
"""
from __future__ import annotations
from . import eventlog, config

VALID_URGENCY = {"info", "attention", "blocker"}


def notify(agent_id: str, urgency: str, reason: str, context: str = "",
           suggested_action: str | None = None) -> dict:
    if urgency not in VALID_URGENCY:
        raise ValueError(f"urgency must be one of {VALID_URGENCY}")
    cfg = config.load_config()
    backend = cfg.get("notify_backend", "log")

    payload = {
        "urgency": urgency,
        "reason": reason,
        "context": context,
        "suggested_action": suggested_action or "",
    }
    # Always log to events — dashboard reads from there
    eventlog.log(agent_id, "notify_human", **payload)

    # Backend dispatch (v1: log only; iMessage/Telegram stubs for later)
    if backend == "log":
        # Already logged. Dashboard picks it up.
        pass
    # elif backend == "imessage": ...
    # elif backend == "telegram": ...
    return payload
