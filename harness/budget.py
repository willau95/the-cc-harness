"""Iteration budget (v4, Hermes §7).
Each task has task_budget {max, used, remaining}. Tool calls consume.
Delegated peers get sub-budget. Grace call writes a proposal for human.
"""
from __future__ import annotations
from pathlib import Path
from . import checkpoint, eventlog
from ._util import now_iso


def consume(folder: Path, task_id: str, agent_id: str, n: int = 1) -> dict:
    """Decrement used + remaining. Returns updated task state.
    Raises if exhausted.
    """
    t = checkpoint.latest_for_task(folder, task_id)
    if t is None:
        raise ValueError(f"no task {task_id}")
    tb = t.get("task_budget") or {"max": 0, "used": 0, "remaining": 0}
    new_used = tb.get("used", 0) + n
    new_remaining = tb.get("max", 0) - new_used
    if new_remaining < 0:
        eventlog.log(agent_id, "budget_exhausted", task_id=task_id)
        raise BudgetExhausted(task_id, tb)
    tb = {"max": tb["max"], "used": new_used, "remaining": new_remaining}
    checkpoint.update(folder, task_id, task_budget=tb)
    if new_remaining <= tb["max"] * 0.1:
        eventlog.log(agent_id, "budget_low", task_id=task_id, remaining=new_remaining)
    return tb


def delegate(folder: Path, task_id: str, agent_id: str, peer_id: str, share: int) -> int:
    """Parent task carves `share` iterations for a peer. Returns allocated."""
    t = checkpoint.latest_for_task(folder, task_id)
    if t is None:
        raise ValueError(f"no task {task_id}")
    tb = t.get("task_budget") or {"max": 0, "used": 0, "remaining": 0}
    allocated = min(share, tb.get("remaining", 0))
    if allocated <= 0:
        raise BudgetExhausted(task_id, tb)
    # Reduce parent remaining by allocated (allocated is reserved, counted as used)
    new_used = tb.get("used", 0) + allocated
    new_remaining = tb["max"] - new_used
    tb = {"max": tb["max"], "used": new_used, "remaining": new_remaining}

    delegated = dict(t.get("delegated_budget") or {})
    delegated[peer_id] = delegated.get(peer_id, 0) + allocated

    checkpoint.update(folder, task_id,
                      task_budget=tb, delegated_budget=delegated)
    eventlog.log(agent_id, "budget_delegated", task_id=task_id, peer=peer_id, share=allocated)
    return allocated


def request_extension(folder: Path, task_id: str, agent_id: str,
                      extra: int, reason: str) -> dict:
    """Grace call — writes a proposal for human approval via dashboard.
    Does NOT automatically grant; human must approve on /budgets page.
    """
    from . import proposals
    data = {
        "task_id": task_id,
        "requester": agent_id,
        "folder": str(folder.resolve()),
        "extra": extra,
        "reason": reason,
    }
    prop = proposals.create("budget", agent_id, data)
    eventlog.log(agent_id, "budget_extension_requested",
                 task_id=task_id, extra=extra, proposal_id=prop["id"])
    return prop


class BudgetExhausted(RuntimeError):
    def __init__(self, task_id: str, tb: dict):
        super().__init__(f"budget exhausted for task {task_id}: {tb}")
        self.task_id = task_id
        self.tb = tb
