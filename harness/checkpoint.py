"""L1 — Task FSM checkpoint. Append-only JSONL at ./.harness/checkpoint.jsonl.
Latest entry per task_id = truth. `original_goal` is immutable once set.
"""
from __future__ import annotations
from pathlib import Path
from ._util import append_jsonl, read_jsonl, now_iso, short_id
from . import config

VALID_STATES = {
    "PROPOSED", "IN_PROGRESS", "BLOCKED",
    "AWAITING_REVIEW", "VERIFIED", "DONE", "ABANDONED",
}

# Allowed state transitions (outbound edges)
TRANSITIONS = {
    "PROPOSED": {"IN_PROGRESS", "ABANDONED"},
    "IN_PROGRESS": {"BLOCKED", "AWAITING_REVIEW", "ABANDONED"},
    "BLOCKED": {"IN_PROGRESS", "ABANDONED"},
    "AWAITING_REVIEW": {"VERIFIED", "IN_PROGRESS", "ABANDONED"},  # IN_PROGRESS = needs_revision
    "VERIFIED": {"DONE"},
    "DONE": set(),
    "ABANDONED": set(),
}


def checkpoint_file(folder: Path) -> Path:
    d = folder / ".harness"
    d.mkdir(parents=True, exist_ok=True)
    return d / "checkpoint.jsonl"


def create_task(folder: Path, original_goal: str, deliverable_spec: str = "",
                budget: int | None = None) -> str:
    """Create a new task. Returns task_id."""
    task_id = short_id(10)
    if budget is None:
        budget = config.load_config().get("task_budget_default", 90)
    entry = {
        "ts": now_iso(),
        "task_id": task_id,
        "state": "PROPOSED",
        "original_goal": original_goal,
        "deliverable_spec": deliverable_spec,
        "task_budget": {"max": budget, "used": 0, "remaining": budget},
        "delegated_budget": {},
        "subtasks": [],
    }
    append_jsonl(checkpoint_file(folder), entry)
    return task_id


def transition(folder: Path, task_id: str, new_state: str, **kwargs) -> dict:
    """Append a state transition entry. Validates FSM."""
    if new_state not in VALID_STATES:
        raise ValueError(f"unknown state {new_state}")
    current = latest_for_task(folder, task_id)
    if current is None:
        raise ValueError(f"no task {task_id}")
    cur_state = current.get("state")
    if new_state != cur_state and new_state not in TRANSITIONS.get(cur_state, set()):
        raise ValueError(f"illegal transition {cur_state} → {new_state}")
    if new_state == "BLOCKED" and "blocked_on" not in kwargs:
        raise ValueError("BLOCKED requires blocked_on={kind, detail}")
    if new_state == "AWAITING_REVIEW" and "deliverable_ref" not in kwargs:
        raise ValueError("AWAITING_REVIEW requires deliverable_ref")
    entry = {"ts": now_iso(), "task_id": task_id, "state": new_state, **kwargs}
    append_jsonl(checkpoint_file(folder), entry)
    return entry


def update(folder: Path, task_id: str, **fields) -> dict:
    """Append a non-state update (e.g., subtask_added, pending, next_step)."""
    current = latest_for_task(folder, task_id)
    if current is None:
        raise ValueError(f"no task {task_id}")
    entry = {"ts": now_iso(), "task_id": task_id, "state": current["state"], **fields}
    append_jsonl(checkpoint_file(folder), entry)
    return entry


def all_entries(folder: Path) -> list[dict]:
    return list(read_jsonl(checkpoint_file(folder)))


def latest_for_task(folder: Path, task_id: str) -> dict | None:
    """Fold the JSONL to get current state of one task."""
    merged: dict = {}
    found = False
    for e in read_jsonl(checkpoint_file(folder)):
        if e.get("task_id") == task_id:
            # original_goal is write-once: don't overwrite after first entry
            for k, v in e.items():
                if k == "original_goal" and "original_goal" in merged:
                    continue
                merged[k] = v
            found = True
    return merged if found else None


def active_tasks(folder: Path) -> list[dict]:
    """Tasks not in terminal state (DONE / ABANDONED)."""
    seen: dict[str, dict] = {}
    for e in read_jsonl(checkpoint_file(folder)):
        tid = e.get("task_id")
        if not tid:
            continue
        merged = seen.get(tid, {})
        for k, v in e.items():
            if k == "original_goal" and "original_goal" in merged:
                continue
            merged[k] = v
        seen[tid] = merged
    return [t for t in seen.values() if t.get("state") not in ("DONE", "ABANDONED")]
