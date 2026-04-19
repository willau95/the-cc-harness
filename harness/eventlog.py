"""L4 — per-agent per-day event log. JSONL append-only.
Every harness tool writes events here for observability + critic review.
"""
from __future__ import annotations
from pathlib import Path
from . import config
from ._util import append_jsonl, read_jsonl, now_iso, today_str


def log(agent_id: str, event_type: str, **data) -> None:
    entry = {"ts": now_iso(), "type": event_type, **data}
    append_jsonl(config.events_file(agent_id, today_str()), entry)


def for_agent_today(agent_id: str) -> list[dict]:
    return list(read_jsonl(config.events_file(agent_id, today_str())))


def for_agent_date(agent_id: str, date_str: str) -> list[dict]:
    return list(read_jsonl(config.events_file(agent_id, date_str)))


def recent(agent_id: str, limit: int = 50) -> list[dict]:
    """Last N events across available date files (today only, keep it simple for v1)."""
    events = for_agent_today(agent_id)
    return events[-limit:]


def count_since(agent_id: str, event_type: str, since_ts: str) -> int:
    """How many events of type since timestamp. Used for rate limits."""
    count = 0
    for e in for_agent_today(agent_id):
        if e.get("type") == event_type and e.get("ts", "") >= since_ts:
            count += 1
    return count
