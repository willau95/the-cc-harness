"""Heartbeat + zombie detection. Each agent appends a line each turn.
Zombie sweeper (called by dashboard or CLI) marks stale agents.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from . import config, registry
from ._util import append_jsonl, read_jsonl, now_iso


def beat(agent_id: str, **meta) -> None:
    entry = {"ts": now_iso(), **meta}
    append_jsonl(config.heartbeat_file(agent_id), entry)


def last_beat(agent_id: str) -> str | None:
    last = None
    for e in read_jsonl(config.heartbeat_file(agent_id)):
        last = e.get("ts")
    return last


def stale(agent_id: str, timeout_minutes: int | None = None) -> bool:
    t = timeout_minutes or config.load_config().get("zombie_timeout_minutes", 10)
    ts = last_beat(agent_id)
    if not ts:
        return True
    try:
        last = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return datetime.now(timezone.utc) - last > timedelta(minutes=t)


def sweep() -> list[dict]:
    """Return list of live-registered agents that are stale."""
    out = []
    for ag in registry.live_agents():
        if stale(ag["agent_id"]):
            out.append(ag)
    return out
