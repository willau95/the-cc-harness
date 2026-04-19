"""T2.d / T2.e — project-layer shared memory.
Fixes v3 gap: multiple agents working on the same project had no shared facts store.

Layout:
  ~/.harness/projects/<project>/state.jsonl     append-only {ts, key, value, by}
  ~/.harness/projects/<project>/members.jsonl   append-only {ts, agent_id, role, kind}

Latest value per key = truth.
"""
from __future__ import annotations
from . import config
from ._util import append_jsonl, read_jsonl, now_iso


def _state_path(project: str):
    return config.project_dir(project) / "state.jsonl"


def _members_path(project: str):
    return config.project_dir(project) / "members.jsonl"


def update_state(project: str, key: str, value, by: str) -> None:
    append_jsonl(_state_path(project), {
        "ts": now_iso(), "key": key, "value": value, "by": by,
    })


def read_state(project: str) -> dict:
    """Fold JSONL: latest value per key."""
    merged: dict = {}
    meta: dict[str, dict] = {}
    for e in read_jsonl(_state_path(project)):
        k = e.get("key")
        if not k:
            continue
        merged[k] = e.get("value")
        meta[k] = {"ts": e.get("ts"), "by": e.get("by")}
    return {"values": merged, "meta": meta}


def add_member(project: str, agent_id: str, role: str) -> None:
    append_jsonl(_members_path(project), {
        "ts": now_iso(), "agent_id": agent_id, "role": role, "kind": "joined",
    })


def remove_member(project: str, agent_id: str) -> None:
    append_jsonl(_members_path(project), {
        "ts": now_iso(), "agent_id": agent_id, "kind": "left",
    })


def active_members(project: str) -> list[dict]:
    """Fold: agents currently `joined` (last entry per agent is joined, not left)."""
    latest: dict[str, dict] = {}
    for e in read_jsonl(_members_path(project)):
        aid = e.get("agent_id")
        if aid:
            latest[aid] = e
    return [e for e in latest.values() if e.get("kind") == "joined"]


def list_projects() -> list[str]:
    base = config.HARNESS_ROOT / "projects"
    if not base.exists():
        return []
    return sorted([p.name for p in base.iterdir() if p.is_dir()])
