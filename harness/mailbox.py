"""L3 — inter-agent messaging. JSONL append-only, Syncthing-replicated.
v3 envelope: idempotency_key, hop_count (≤6), provenance_chain, ttl, reply_to.
v4: body wrapped <untrusted-content> only on receive.
"""
from __future__ import annotations
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from . import config, eventlog
from ._util import append_jsonl, read_jsonl, now_iso, short_id

MAX_HOP = 6
DEFAULT_TTL_HOURS = 24 * 7
DEDUP_LRU_SIZE = 10000  # per-agent in-memory set not persisted; acceptable for now


def _idempotency_key(from_id: str, to_id: str, subject: str, body: str) -> str:
    """Rounded-minute hash → same message within a minute dedups."""
    minute = now_iso()[:16]  # YYYY-MM-DDTHH:MM
    h = hashlib.sha256(f"{from_id}|{to_id}|{subject}|{body}|{minute}".encode()).hexdigest()
    return h[:16]


def inbox_path(agent_id: str) -> Path:
    return config.mailbox_dir(agent_id) / "inbox.jsonl"


def consumed_path(agent_id: str) -> Path:
    return config.mailbox_dir(agent_id) / "inbox.consumed"


def send(from_id: str, to_id: str, subject: str, body: str,
         reply_to_msg_id: str | None = None,
         provenance_chain: list[str] | None = None,
         hop_count: int = 0,
         ttl_hours: int = DEFAULT_TTL_HOURS) -> dict:
    """Append a message to `to_id` inbox. Returns envelope."""
    if hop_count > MAX_HOP:
        raise ValueError(f"hop_count {hop_count} exceeds MAX_HOP={MAX_HOP}")
    ttl_dt = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    envelope = {
        "msg_id": short_id(12),
        "idempotency_key": _idempotency_key(from_id, to_id, subject, body),
        "from": from_id,
        "to": to_id,
        "subject": subject,
        "body": body,
        "created_at": now_iso(),
        "ttl": ttl_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hop_count": hop_count,
        "provenance_chain": (provenance_chain or []) + [from_id],
        "reply_to_msg_id": reply_to_msg_id,
    }
    # Route: if the target agent lives on a remote machine per the registry,
    # push to the remote inbox via SSH / fleet-ssh. Otherwise local append.
    from . import registry, remote
    target_entry = registry.find(to_id)
    target_machine = (target_entry or {}).get("machine")
    if target_machine and not remote.is_local_machine(target_machine):
        r = remote.push_message(target_machine, to_id, envelope)
        if not r.get("ok"):
            # Fallback: local append (at least the sender's fleet view has it)
            append_jsonl(inbox_path(to_id), envelope)
            eventlog.log(from_id, "sent_message_remote_fallback",
                         to=to_id, subject=subject, msg_id=envelope["msg_id"],
                         error=str(r.get("error") or r.get("stderr")))
        else:
            eventlog.log(from_id, "sent_message", to=to_id, subject=subject,
                         msg_id=envelope["msg_id"], via="remote",
                         machine=target_machine)
    else:
        append_jsonl(inbox_path(to_id), envelope)
        eventlog.log(from_id, "sent_message", to=to_id, subject=subject,
                     msg_id=envelope["msg_id"])
    return envelope


def _load_consumed(agent_id: str) -> set[str]:
    s: set[str] = set()
    path = consumed_path(agent_id)
    if not path.exists():
        return s
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                s.add(line)
    return s


def _mark_consumed(agent_id: str, msg_ids: Iterable[str]) -> None:
    path = consumed_path(agent_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for m in msg_ids:
            f.write(m + "\n")


def receive(agent_id: str, limit: int = 20,
            wrap_untrusted: bool = True) -> list[dict]:
    """Read new messages. Apply 4 gates (dedup/hop/ttl/wrap)."""
    consumed = _load_consumed(agent_id)
    idempotency_seen: set[str] = set()
    result: list[dict] = []
    to_mark: list[str] = []
    now = datetime.now(timezone.utc)

    for env in read_jsonl(inbox_path(agent_id)):
        msg_id = env.get("msg_id")
        if not msg_id or msg_id in consumed:
            continue
        # 1. dedup by idempotency_key (LRU-esque, bounded to this pass)
        ik = env.get("idempotency_key")
        if ik and ik in idempotency_seen:
            to_mark.append(msg_id)
            eventlog.log(agent_id, "dropped_message", reason="dup", msg_id=msg_id)
            continue
        if ik:
            idempotency_seen.add(ik)
        # 2. hop gate
        if env.get("hop_count", 0) > MAX_HOP:
            to_mark.append(msg_id)
            eventlog.log(agent_id, "dropped_message", reason="hop_max", msg_id=msg_id)
            continue
        # 3. ttl gate
        ttl = env.get("ttl")
        if ttl:
            try:
                ttl_dt = datetime.strptime(ttl, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if now > ttl_dt:
                    to_mark.append(msg_id)
                    eventlog.log(agent_id, "dropped_message", reason="ttl", msg_id=msg_id)
                    continue
            except ValueError:
                pass
        # 4. untrusted wrap
        if wrap_untrusted:
            original = env.get("body", "")
            env = dict(env)
            env["body_wrapped"] = (
                f'<untrusted-content from="{env.get("from")}">\n'
                f'{original}\n</untrusted-content>'
            )
        result.append(env)
        to_mark.append(msg_id)
        if len(result) >= limit:
            break

    if to_mark:
        _mark_consumed(agent_id, to_mark)
        for env in result:
            eventlog.log(agent_id, "received_message",
                         msg_id=env["msg_id"], peer=env.get("from"),
                         subject=env.get("subject"))
    return result


def peek(agent_id: str, limit: int = 20) -> list[dict]:
    """List messages without consuming (dashboard view)."""
    consumed = _load_consumed(agent_id)
    out: list[dict] = []
    for env in read_jsonl(inbox_path(agent_id)):
        if env.get("msg_id") not in consumed:
            out.append(env)
            if len(out) >= limit:
                break
    return out
