"""Fleet registry. Append-only JSONL at ~/.harness/registry.jsonl.
Each line = one lifecycle event (register / unregister / update).
Live state = fold by agent_id, keeping last line.
"""
from __future__ import annotations
from typing import Iterable
from . import config
from ._util import append_jsonl, read_jsonl, now_iso


def register(identity: dict, broadcast: bool = True) -> None:
    """Append a register entry locally. If `broadcast`, also push a copy to
    every peer machine known via mac-fleet-control so every registry is
    eventually consistent and cross-machine routing works both ways.
    """
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
    if broadcast:
        try:
            _broadcast_registry_line(entry)
        except Exception:
            pass  # never break init on broadcast failure


def _broadcast_registry_line(entry: dict) -> None:
    """Best-effort push of a registry line to every known peer machine."""
    import json as _json
    from . import remote
    if not remote.fleet_ssh_available():
        return
    line = _json.dumps(entry, ensure_ascii=False)
    for m in remote.list_machines():
        mname = m["name"]
        if remote.is_local_machine(mname):
            continue  # skip self
        # Also skip the machine where the agent already registered itself
        if entry.get("machine") and entry["machine"].lower().replace("_", "-") == mname.lower().replace("_", "-"):
            continue
        remote.append_remote_jsonl(mname, "~/.harness/registry.jsonl", line)


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
