"""T3.e — self-evolution proposals queue.
Agents propose → critic reviews → human approves → promote.

Kinds: skill | role | budget | arsenal-retract
"""
from __future__ import annotations
import yaml
from pathlib import Path
from . import config, eventlog
from ._util import short_id, now_iso, atomic_write_text, slugify

VALID_KINDS = {"skill", "role", "budget", "arsenal-retract"}
VALID_STATUS = {"pending", "critic_approved", "needs_revision", "rejected", "human_approved", "promoted"}


def _path(kind: str, pid: str) -> Path:
    return config.proposals_dir(kind) / f"{pid}.yaml"


def create(kind: str, proposer: str, data: dict) -> dict:
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {VALID_KINDS}")
    pid = short_id(10)
    record = {
        "id": pid,
        "kind": kind,
        "proposer": proposer,
        "created_at": now_iso(),
        "status": "pending",
        "data": data,
        "critic_verdict": None,
        "human_verdict": None,
    }
    atomic_write_text(_path(kind, pid), yaml.safe_dump(record, sort_keys=False))
    eventlog.log(proposer, "proposal_created", id=pid, kind=kind)
    return record


def load(kind: str, pid: str) -> dict | None:
    p = _path(kind, pid)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text())


def _save(record: dict) -> None:
    atomic_write_text(_path(record["kind"], record["id"]),
                      yaml.safe_dump(record, sort_keys=False))


def list_all(kind: str | None = None, status: str | None = None) -> list[dict]:
    out: list[dict] = []
    kinds = [kind] if kind else list(VALID_KINDS)
    for k in kinds:
        d = config.proposals_dir(k)
        for f in sorted(d.glob("*.yaml")):
            rec = yaml.safe_load(f.read_text())
            if not rec:
                continue
            if status and rec.get("status") != status:
                continue
            out.append(rec)
    return out


def set_critic_verdict(kind: str, pid: str, verdict: str,
                       notes: str = "", by: str = "critic") -> dict:
    """verdict ∈ {approve, needs_revision, reject}."""
    rec = load(kind, pid)
    if rec is None:
        raise ValueError(f"no proposal {pid}")
    rec["critic_verdict"] = {"verdict": verdict, "notes": notes, "by": by, "at": now_iso()}
    if verdict == "approve":
        rec["status"] = "critic_approved"
    elif verdict == "reject":
        rec["status"] = "rejected"
    else:
        rec["status"] = "needs_revision"
    _save(rec)
    return rec


def human_approve(kind: str, pid: str) -> dict:
    rec = load(kind, pid)
    if rec is None:
        raise ValueError(f"no proposal {pid}")
    rec["human_verdict"] = {"verdict": "approve", "at": now_iso()}
    rec["status"] = "human_approved"
    _save(rec)
    _promote(rec)
    return rec


def human_reject(kind: str, pid: str) -> dict:
    rec = load(kind, pid)
    if rec is None:
        raise ValueError(f"no proposal {pid}")
    rec["human_verdict"] = {"verdict": "reject", "at": now_iso()}
    rec["status"] = "rejected"
    _save(rec)
    return rec


def _promote(rec: dict) -> None:
    kind = rec["kind"]
    if kind == "skill":
        _promote_skill(rec)
    elif kind == "role":
        _promote_role_lesson(rec)
    elif kind == "budget":
        _promote_budget(rec)
    # arsenal-retract: handled by set_trust elsewhere
    rec["status"] = "promoted"
    _save(rec)


def _promote_skill(rec: dict) -> None:
    """Write the skill into ~/.harness/skills/global/<slug>/SKILL.md."""
    data = rec["data"]
    slug = slugify(data.get("slug") or rec["id"])
    global_skills = config.HARNESS_ROOT / "skills" / "global" / slug
    global_skills.mkdir(parents=True, exist_ok=True)
    content = data.get("content", "")
    frontmatter = (
        f"---\n"
        f"name: {slug}\n"
        f"description: {data.get('rationale', '')[:200]}\n"
        f"source_proposal: {rec['id']}\n"
        f"promoted_at: {now_iso()}\n"
        f"---\n\n"
    )
    (global_skills / "SKILL.md").write_text(frontmatter + content)


def _promote_role_lesson(rec: dict) -> None:
    """Append the lesson to ~/.harness/roles-evolved/<role>/lessons.jsonl."""
    from ._util import append_jsonl
    data = rec["data"]
    role = data.get("role", "generic")
    append_jsonl(config.role_lessons_file(role), {
        "ts": now_iso(),
        "lesson": data.get("lesson", ""),
        "proposer": rec["proposer"],
        "proposal_id": rec["id"],
    })


def _promote_budget(rec: dict) -> None:
    """Apply grace — find the task in the requester's folder and extend."""
    from pathlib import Path
    from . import checkpoint
    data = rec["data"]
    folder = Path(data.get("folder", "."))
    task_id = data.get("task_id")
    extra = int(data.get("extra", 0))
    if not task_id or extra <= 0:
        return
    t = checkpoint.latest_for_task(folder, task_id)
    if t is None:
        return
    tb = t.get("task_budget") or {"max": 0, "used": 0, "remaining": 0}
    tb = {"max": tb["max"] + extra, "used": tb["used"], "remaining": tb["remaining"] + extra}
    checkpoint.update(folder, task_id, task_budget=tb)
