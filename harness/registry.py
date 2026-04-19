"""Fleet registry. Append-only JSONL at ~/.harness/registry.jsonl.
Each line = one lifecycle event (register / unregister / update).
Live state = fold by agent_id, keeping last line.
"""
from __future__ import annotations
from typing import Iterable
from . import config
from ._util import append_jsonl, read_jsonl, now_iso


def register(identity: dict) -> None:
    entry = {
        "ts": now_iso(),
        "kind": "register",
        "agent_id": identity["agent_id"],
        "slug": identity.get("slug"),
        "role": identity.get("role"),
        "machine": identity.get("machine"),
        "folder": identity.get("folder"),
    }
    append_jsonl(config.registry_path(), entry)


def unregister(agent_id: str) -> None:
    append_jsonl(config.registry_path(), {
        "ts": now_iso(), "kind": "unregister", "agent_id": agent_id,
    })


def all_entries() -> Iterable[dict]:
    yield from read_jsonl(config.registry_path())


def live_agents() -> list[dict]:
    """Fold registry to current live set: last entry per agent_id, kind=register."""
    state: dict[str, dict] = {}
    for e in all_entries():
        aid = e.get("agent_id")
        if not aid:
            continue
        if e.get("kind") == "unregister":
            state.pop(aid, None)
        else:
            state[aid] = e
    return list(state.values())


def find(agent_id: str) -> dict | None:
    for e in reversed(list(all_entries())):
        if e.get("agent_id") == agent_id and e.get("kind") != "unregister":
            return e
    return None
