"""Dashboard backend — FastAPI, reads ~/.harness/, serves frontend static files.
Run: `harness dashboard` → uvicorn dashboard.backend.main:app --port 9999
"""
from __future__ import annotations
import asyncio
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Ensure our harness package is importable when run via uvicorn module
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from harness import config, registry, heartbeat, arsenal, mailbox, eventlog
from harness import project, proposals, checkpoint, identity as ident_mod
from harness import control as fleet_control, remote as fleet_remote
from harness import liveness, transcript
from harness._util import read_jsonl, now_iso

# Pydantic for request bodies
from pydantic import BaseModel


class SpawnRequest(BaseModel):
    role: str
    name: str
    folder: str
    initial_prompt: str | None = None
    machine: str | None = None  # None = local; else fleet-ssh target name


class BulkRequest(BaseModel):
    action: str
    agent_ids: list[str]


class ChatSendRequest(BaseModel):
    body: str
    subject: str | None = None
    from_id: str | None = None  # defaults to "human@dashboard"


class ArsenalAddRequest(BaseModel):
    slug: str | None = None
    title: str
    content: str
    tags: list[str] = []
    source_type: str = "human_input"
    source_refs: list[str] = []


class ArsenalTrustRequest(BaseModel):
    trust: str  # human_verified | retracted | peer_verified | ...

app = FastAPI(title="Claude Harness Dashboard", version="0.1.0")

FRONTEND_DIR = REPO_ROOT / "dashboard" / "frontend"

# --- Remote aggregation helpers --------------------------------------------
# Shared thread pool for parallel fleet-ssh calls (each call is ~1s of latency).
_REMOTE_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="remote-agg")

# Short-TTL cache for expensive cross-machine aggregations so rapid refreshes
# (user clicking around) don't refire N fleet-ssh calls per second.
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 5.0  # seconds

# Machines that recently failed — skipped for this TTL window.
_OFFLINE: dict[str, float] = {}
_OFFLINE_TTL = 15.0


def _cache_get(key: str) -> Any | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_put(key: str, value: Any) -> None:
    _CACHE[key] = (time.time(), value)


def _is_offline(machine: str) -> bool:
    ts = _OFFLINE.get(machine)
    if ts is None:
        return False
    if time.time() - ts > _OFFLINE_TTL:
        _OFFLINE.pop(machine, None)
        return False
    return True


def _mark_offline(machine: str) -> None:
    _OFFLINE[machine] = time.time()


def _parallel_remote(machines: list[dict], fn: Callable[[dict], Any]) -> list[Any]:
    """Run fn(machine) in parallel across peers; collect non-None results.
    Machines marked offline in the last _OFFLINE_TTL window are skipped.
    """
    targets = [m for m in machines
               if not m.get("is_local") and not m.get("synthetic")
               and not _is_offline(m["name"])]
    if not targets:
        return []
    results: list[Any] = []
    futures = {_REMOTE_POOL.submit(fn, m): m for m in targets}
    for fut in as_completed(futures, timeout=15):
        m = futures[fut]
        try:
            out = fut.result()
            if out is not None:
                results.append(out)
        except Exception:
            _mark_offline(m["name"])
    return results


# ===== REST =====

def _paused_for(ag: dict) -> bool:
    """Check the .harness/paused sentinel for any agent whose folder we can reach.
    Remote agents (different machine) resolve to False here — AgentDetail only
    ever renders for agents whose folder is local-readable anyway.
    """
    folder = ag.get("folder")
    if not folder:
        return False
    try:
        return fleet_control.is_paused(Path(folder))
    except Exception:
        return False


def _alive_for(ag: dict) -> bool | None:
    """Active process check — is the claude process for this agent still up?
    True/False if we have a PID to probe, None if unknown (remote agent or
    pre-PID-tracking agent)."""
    folder = ag.get("folder")
    if not folder:
        return None
    # Only valid for local agents — can't signal-check a remote PID cheaply.
    # Use the "am I on this machine" heuristic: folder must exist locally.
    try:
        if not Path(folder).exists():
            return None
        return liveness.is_alive(Path(folder))
    except Exception:
        return None


@app.get("/api/fleet")
def api_fleet() -> dict:
    agents = registry.live_agents()
    enriched = []
    for ag in agents:
        aid = ag["agent_id"]
        last = heartbeat.last_beat(aid)
        stale = heartbeat.stale(aid)
        alive = _alive_for(ag)
        # If the process is demonstrably dead, override stale to True regardless
        # of the heartbeat window — user closed the terminal, they want to see
        # it immediately, not in 30 minutes.
        if alive is False:
            stale = True
        enriched.append({**ag, "last_beat": last, "stale": stale,
                         "paused": _paused_for(ag),
                         "process_alive": alive})
    return {"count": len(enriched), "agents": enriched}


@app.get("/api/agents/{agent_id}/transcript")
def api_agent_transcript(agent_id: str, limit: int = 300) -> dict:
    """Return a normalized timeline from Claude Code's per-session JSONL.
    Lets the dashboard show what the agent is actually thinking / doing /
    editing, without the user having to switch to the terminal. Local only
    for v1 — remote transcripts require fleet-ssh tail."""
    ag = registry.find(agent_id)
    if not ag:
        return JSONResponse({"error": "not_found"}, status_code=404)
    folder = ag.get("folder")
    if not folder or not Path(folder).exists():
        return {"agent_id": agent_id, "available": False,
                "reason": "folder not local to this machine", "timeline": []}
    meta = transcript.session_metadata(folder)
    if not meta:
        return {"agent_id": agent_id, "available": False,
                "reason": "no claude session found for this folder", "timeline": []}
    tl = transcript.read_timeline(folder, limit=limit)
    return {"agent_id": agent_id, "available": True,
            "session": meta, "count": len(tl), "timeline": tl}


@app.get("/api/agents/{agent_id}/activity")
def api_agent_activity(agent_id: str) -> dict:
    """Read the PreToolUse/PostToolUse-written current_activity.json."""
    ag = registry.find(agent_id)
    if not ag:
        return JSONResponse({"error": "not_found"}, status_code=404)
    folder = ag.get("folder")
    if not folder:
        return {"activity": None}
    path = Path(folder) / ".harness" / "current_activity.json"
    if not path.exists():
        return {"activity": None}
    try:
        return {"activity": json.loads(path.read_text())}
    except Exception:
        return {"activity": None}


@app.get("/api/agents/{agent_id}/changes")
def api_agent_changes(agent_id: str) -> dict:
    """Show filesystem changes in an agent's folder. Tries git diff first;
    falls back to mtime-based recent-files list if the folder is not a repo."""
    import subprocess as _sp
    ag = registry.find(agent_id)
    if not ag:
        return JSONResponse({"error": "not_found"}, status_code=404)
    folder = ag.get("folder")
    if not folder or not Path(folder).exists():
        return {"agent_id": agent_id, "available": False,
                "reason": "folder not local to this machine"}
    cwd = Path(folder)
    # git path
    try:
        git_status = _sp.run(["git", "-C", str(cwd), "status", "--porcelain"],
                             capture_output=True, text=True, timeout=5)
        if git_status.returncode == 0:
            files = []
            for line in git_status.stdout.splitlines():
                if not line.strip():
                    continue
                mark = line[:2]
                path = line[3:].strip()
                # Per-file stat
                diff_stat = _sp.run(
                    ["git", "-C", str(cwd), "diff", "--numstat", "--", path],
                    capture_output=True, text=True, timeout=5,
                )
                added = deleted = 0
                if diff_stat.returncode == 0 and diff_stat.stdout.strip():
                    parts = diff_stat.stdout.strip().split("\t")
                    try:
                        added = int(parts[0]) if parts[0] != "-" else 0
                        deleted = int(parts[1]) if parts[1] != "-" else 0
                    except (ValueError, IndexError):
                        pass
                files.append({"path": path, "status": mark.strip() or "?",
                              "added": added, "deleted": deleted})
            return {"agent_id": agent_id, "available": True, "kind": "git",
                    "files": files, "count": len(files)}
    except Exception:
        pass
    # Fallback: recent mtime
    try:
        recent = sorted(
            (p for p in cwd.rglob("*") if p.is_file()
             and not any(part.startswith(".") for part in p.parts)),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )[:50]
        cutoff = time.time() - 24 * 3600
        files = [{"path": str(p.relative_to(cwd)),
                  "mtime": p.stat().st_mtime,
                  "size": p.stat().st_size,
                  "recent": p.stat().st_mtime > cutoff}
                 for p in recent]
        return {"agent_id": agent_id, "available": True, "kind": "mtime",
                "files": files, "count": len(files)}
    except Exception as e:
        return {"agent_id": agent_id, "available": False, "reason": str(e)}


@app.get("/api/agents/{agent_id}/file-diff")
def api_agent_file_diff(agent_id: str, path: str) -> dict:
    """Return the git diff for one file within the agent's folder."""
    import subprocess as _sp
    ag = registry.find(agent_id)
    if not ag:
        return JSONResponse({"error": "not_found"}, status_code=404)
    folder = ag.get("folder")
    if not folder or not Path(folder).exists():
        return JSONResponse({"error": "folder not local"}, status_code=404)
    # Guard against path escape
    full = (Path(folder) / path).resolve()
    if not str(full).startswith(str(Path(folder).resolve())):
        return JSONResponse({"error": "invalid path"}, status_code=400)
    try:
        r = _sp.run(["git", "-C", str(folder), "diff", "--", path],
                    capture_output=True, text=True, timeout=8)
        if r.returncode != 0:
            # Maybe untracked — show the full file instead
            if full.exists() and full.is_file():
                return {"path": path, "kind": "untracked",
                        "content": full.read_text(errors="replace")[:100_000]}
            return JSONResponse({"error": r.stderr.strip() or "git diff failed"}, status_code=500)
        return {"path": path, "kind": "diff", "diff": r.stdout}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/agents/{agent_id}")
def api_agent(agent_id: str) -> dict:
    ag = registry.find(agent_id)
    if not ag:
        return JSONResponse({"error": "not_found"}, status_code=404)
    alive = _alive_for(ag)
    ag = {**ag, "paused": _paused_for(ag), "process_alive": alive}
    last = heartbeat.last_beat(agent_id)
    stale = heartbeat.stale(agent_id)
    if alive is False:
        stale = True
    # checkpoint for agents whose folder is accessible from this machine
    tasks = []
    folder = Path(ag.get("folder", ""))
    if folder.exists():
        tasks = checkpoint.active_tasks(folder)
    events = eventlog.recent(agent_id, limit=50)
    inbox = mailbox.peek(agent_id, limit=20)
    return {
        "agent": ag,
        "last_beat": last,
        "stale": stale,
        "tasks": tasks,
        "recent_events": events,
        "inbox_pending": inbox,
    }


@app.get("/api/events")
def api_events(limit: int = 200) -> dict:
    """Merged events across every agent on every peer (today only for v1)."""
    out: list[dict] = []
    events_root = config.HARNESS_ROOT / "events"
    if events_root.exists():
        from harness._util import today_str
        today = today_str()
        for agent_dir in events_root.iterdir():
            f = agent_dir / f"{today}.jsonl"
            for e in read_jsonl(f):
                out.append({"agent": agent_dir.name, "machine": None, **e})

    # Fold in peer events (5s TTL cached — aggressive because events stream fast)
    if fleet_remote.fleet_ssh_available():
        cache_key = f"events-remote::{limit}"
        cached = _cache_get(cache_key)
        if cached is not None:
            out.extend(cached)
        else:
            import re as _re
            import json as _json

            def _fetch(m: dict) -> list[dict] | None:
                r = fleet_remote.exec_remote(
                    m["name"],
                    f"~/.local/bin/harness events dump-json --limit {limit} --days 2",
                    timeout=8,
                )
                if not (r.get("ok") and r.get("stdout")):
                    return None
                s = _re.sub(r"\x1b\[[0-9;]*m", "", r["stdout"])
                s = _re.sub(r"\A\[[^\]\n]+\]\s*\n?", "", s)
                jstart = s.find("[")
                jend = s.rfind("]") + 1
                if jstart < 0 or jend <= jstart:
                    return None
                try:
                    remote_events = _json.loads(s[jstart:jend])
                except _json.JSONDecodeError:
                    return None
                return [{**e, "machine": m["name"]} for e in remote_events]

            merged: list[dict] = []
            for chunk in _parallel_remote(fleet_remote.all_machines_including_local(), _fetch):
                merged.extend(chunk)
            _cache_put(cache_key, merged)
            out.extend(merged)

    out.sort(key=lambda e: e.get("ts", ""), reverse=True)
    # Dedupe in case broadcast registry causes duplicate events across peers
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for e in out:
        k = (e.get("agent"), e.get("ts"), e.get("type"), (e.get("msg_id") or e.get("id") or ""))
        if k in seen:
            continue
        seen.add(k)
        deduped.append(e)
    return {"count": len(deduped[:limit]), "events": deduped[:limit]}


@app.get("/api/arsenal")
def api_arsenal(q: str = "", limit: int = 30) -> dict:
    dist = arsenal.trust_distribution()
    results = []
    if q:
        results = arsenal.search(q, limit=limit, include_unverified=True)
    return {"trust_distribution": dist, "results": results}


# Static paths MUST come before /{slug} so FastAPI doesn't capture them as slug.
@app.get("/api/arsenal/list")
def api_arsenal_list(trust: str | None = None, limit: int = 100) -> dict:
    """Full listing (not just search). Used by /arsenal page."""
    import sqlite3
    conn = sqlite3.connect(config.arsenal_db_path())
    try:
        if trust:
            rows = conn.execute(
                "SELECT slug, title, trust, produced_by, produced_at, source_refs, tags, chain_depth "
                "FROM items WHERE trust = ? ORDER BY produced_at DESC LIMIT ?",
                (trust, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT slug, title, trust, produced_by, produced_at, source_refs, tags, chain_depth "
                "FROM items ORDER BY produced_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()
    items = [{
        "slug": r[0], "title": r[1], "trust": r[2], "produced_by": r[3],
        "produced_at": r[4], "source_refs": r[5], "tags": r[6],
        "chain_depth": r[7], "machine": None,
    } for r in rows]

    # v0.2: fold remote arsenals. Each peer has its own arsenal/index.sqlite;
    # we query via `harness arsenal dump-json` (no brittle inline Python).
    # Parallelized + short-TTL cached to keep /arsenal page snappy.
    if fleet_remote.fleet_ssh_available():
        cache_key = f"arsenal-remote::{trust or ''}::{limit}"
        cached = _cache_get(cache_key)
        if cached is not None:
            items.extend(cached)
        else:
            import re as _re
            import json as _json

            def _fetch(m: dict) -> list[dict] | None:
                r = fleet_remote.exec_remote(
                    m["name"],
                    "~/.local/bin/harness arsenal dump-json --limit 200",
                    timeout=8,
                )
                if not (r.get("ok") and r.get("stdout")):
                    return None
                s = _re.sub(r"\x1b\[[0-9;]*m", "", r["stdout"])
                s = _re.sub(r"\A\[[^\]\n]+\]\s*\n?", "", s)
                jstart = s.find("[")
                jend = s.rfind("]") + 1
                if jstart < 0 or jend <= jstart:
                    return None
                try:
                    remote_items = _json.loads(s[jstart:jend])
                except _json.JSONDecodeError:
                    return None
                out = []
                for item in remote_items:
                    if trust and item.get("trust") != trust:
                        continue
                    item["machine"] = m["name"]
                    out.append(item)
                return out

            merged: list[dict] = []
            for chunk in _parallel_remote(fleet_remote.all_machines_including_local(), _fetch):
                merged.extend(chunk)
            _cache_put(cache_key, merged)
            items.extend(merged)

    # Re-sort merged list by produced_at
    items.sort(key=lambda i: i.get("produced_at") or "", reverse=True)
    items = items[:limit]
    return {"count": len(items), "items": items,
            "trust_distribution": arsenal.trust_distribution()}


@app.post("/api/arsenal/add")
def api_arsenal_add(req: ArsenalAddRequest) -> dict:
    meta = arsenal.add(
        slug=req.slug, title=req.title, content=req.content, tags=req.tags,
        source_type=req.source_type, source_refs=req.source_refs,
        produced_by="human@dashboard",
    )
    return {"ok": True, "meta": meta}


@app.get("/api/arsenal/{slug}")
def api_arsenal_get(slug: str) -> dict:
    item = arsenal.get(slug)
    if item:
        return {**item, "machine": None}
    # Fall back to remote peers — an item in the listing might live elsewhere.
    if fleet_remote.fleet_ssh_available():
        import re as _re
        import json as _json
        for m in fleet_remote.all_machines_including_local():
            if m.get("is_local") or m.get("synthetic") or _is_offline(m["name"]):
                continue
            try:
                # Try --json first; fall back to markdown if the peer's CLI
                # is older (no --json flag).
                r = fleet_remote.exec_remote(
                    m["name"],
                    f"~/.local/bin/harness arsenal get {slug} --json 2>/dev/null || "
                    f"~/.local/bin/harness arsenal get {slug}",
                    timeout=8,
                )
                if not (r.get("ok") and r.get("stdout")):
                    continue
                s = _re.sub(r"\x1b\[[0-9;]*m", "", r["stdout"])
                s = _re.sub(r"\A\[[^\]\n]+\]\s*\n?", "", s)
                # JSON path
                jstart = s.find("{")
                jend = s.rfind("}") + 1
                if jstart == 0 and jend > jstart:
                    try:
                        remote_item = _json.loads(s[jstart:jend])
                        if remote_item.get("error") != "not_found":
                            return {**remote_item, "machine": m["name"]}
                    except _json.JSONDecodeError:
                        pass
                # Markdown fallback:
                #   # Title
                #   _trust: X · produced_by: Y_
                #
                #   <content...>
                if "(not found)" in s:
                    continue
                lines = s.splitlines()
                if not lines or not lines[0].startswith("# "):
                    continue
                title = lines[0][2:].strip()
                meta_match = _re.search(r"_trust:\s*(\S+)\s*·\s*produced_by:\s*(\S+)_", s)
                trust_val = meta_match.group(1) if meta_match else "agent_summary"
                produced_by = meta_match.group(2) if meta_match else "unknown"
                # content = everything after first blank line past the meta line
                body_start = 2
                for i, ln in enumerate(lines[1:], 1):
                    if meta_match and meta_match.group(0) in ln:
                        body_start = i + 1
                        break
                content_txt = "\n".join(lines[body_start:]).strip()
                return {
                    "slug": slug, "title": title, "trust": trust_val,
                    "produced_by": produced_by, "content": content_txt,
                    "tags": "", "source_refs": "", "machine": m["name"],
                }
            except Exception:
                _mark_offline(m["name"])
                continue
    return JSONResponse({"error": "not_found"}, status_code=404)


@app.post("/api/arsenal/{slug}/trust")
def api_arsenal_set_trust(slug: str, req: ArsenalTrustRequest) -> dict:
    # Local path: item lives on this machine
    if arsenal.get(slug):
        arsenal.set_trust(slug, req.trust, by="human@dashboard")
        # Bust caches so the UI re-fetches fresh data
        _CACHE.pop("arsenal-remote::::100", None)
        for k in list(_CACHE.keys()):
            if k.startswith("arsenal-"):
                _CACHE.pop(k, None)
        return {"ok": True, "slug": slug, "trust": req.trust, "machine": None}
    # Remote path: route to the owning peer via fleet-ssh
    if fleet_remote.fleet_ssh_available():
        import re as _re
        for m in fleet_remote.all_machines_including_local():
            if m.get("is_local") or m.get("synthetic") or _is_offline(m["name"]):
                continue
            try:
                # First check whether this peer owns the slug (cheap existence check)
                probe = fleet_remote.exec_remote(
                    m["name"],
                    f"~/.local/bin/harness arsenal get {slug} --json 2>/dev/null | head -c 1",
                    timeout=6,
                )
                if not (probe.get("ok") and probe.get("stdout", "").strip().startswith(("{", "[Seas", "["))):
                    # Second-level probe: try markdown form (old CLI)
                    probe2 = fleet_remote.exec_remote(
                        m["name"],
                        f"~/.local/bin/harness arsenal get {slug} 2>&1 | head -2",
                        timeout=6,
                    )
                    body = _re.sub(r"\x1b\[[0-9;]*m", "", probe2.get("stdout", ""))
                    body = _re.sub(r"\A\[[^\]\n]+\]\s*\n?", "", body)
                    if "(not found)" in body or not body.strip().startswith("# "):
                        continue
                # Owner found — issue the update
                r = fleet_remote.exec_remote(
                    m["name"],
                    f"~/.local/bin/harness arsenal set-trust {slug} {req.trust} --by human@dashboard",
                    timeout=8,
                )
                if not (r.get("ok") and r.get("stdout")):
                    continue
                # Bust caches so next /api/arsenal/{slug} sees the new trust
                for k in list(_CACHE.keys()):
                    if k.startswith("arsenal-"):
                        _CACHE.pop(k, None)
                return {"ok": True, "slug": slug, "trust": req.trust, "machine": m["name"]}
            except Exception:
                _mark_offline(m["name"])
                continue
    return JSONResponse({"error": "not_found_on_any_peer", "slug": slug}, status_code=404)


@app.get("/api/projects")
def api_projects() -> dict:
    projs = project.list_projects()
    out = []
    for p in projs:
        state = project.read_state(p)
        members = project.active_members(p)
        out.append({"project": p, "state": state["values"],
                    "member_count": len(members), "members": members})
    return {"count": len(out), "projects": out}


@app.get("/api/projects/{proj}")
def api_project(proj: str) -> dict:
    state = project.read_state(proj)
    members = project.active_members(proj)
    # Flatten state to {key: value} so frontend shapes match /api/projects list.
    # Raw meta is available via /api/projects/{proj}/state-meta if needed later.
    return {"project": proj, "state": state.get("values", {}), "members": members}


@app.get("/api/proposals")
def api_proposals(status: str | None = None, kind: str | None = None) -> dict:
    recs = proposals.list_all(kind=kind, status=status)
    return {"count": len(recs), "proposals": recs}


@app.post("/api/proposals/{kind}/{pid}/approve")
def api_approve(kind: str, pid: str) -> dict:
    try:
        rec = proposals.human_approve(kind, pid)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "record": rec}


@app.post("/api/proposals/{kind}/{pid}/reject")
def api_reject(kind: str, pid: str) -> dict:
    try:
        rec = proposals.human_reject(kind, pid)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "record": rec}


@app.get("/api/stats")
def api_stats() -> dict:
    agents = registry.live_agents()
    online = sum(1 for a in agents if not heartbeat.stale(a["agent_id"]))
    zombies = sum(1 for a in agents if heartbeat.stale(a["agent_id"]))
    pending_proposals = len(proposals.list_all(status="critic_approved"))
    pending_budgets = len(proposals.list_all(kind="budget", status="pending"))
    projs = project.list_projects()
    trust = arsenal.trust_distribution()
    return {
        "online": online, "zombies": zombies, "total_agents": len(agents),
        "pending_proposals": pending_proposals,
        "pending_budgets": pending_budgets,
        "projects": len(projs),
        "trust_distribution": trust,
    }


# ===== Fleet control (v1 soft controls) =====

@app.post("/api/agents/{agent_id}/pause")
def api_pause(agent_id: str) -> dict:
    r = fleet_control.pause(agent_id)
    if not r.get("ok"):
        return JSONResponse(r, status_code=400)
    return r


@app.post("/api/agents/{agent_id}/resume")
def api_resume(agent_id: str) -> dict:
    r = fleet_control.resume(agent_id)
    if not r.get("ok"):
        return JSONResponse(r, status_code=400)
    return r


@app.post("/api/agents/{agent_id}/kill")
def api_kill(agent_id: str) -> dict:
    r = fleet_control.kill(agent_id)
    if not r.get("ok"):
        return JSONResponse(r, status_code=400)
    return r


@app.post("/api/fleet/spawn")
def api_spawn(req: SpawnRequest) -> dict:
    if req.machine and not fleet_remote.is_local_machine(req.machine):
        # Remote spawn via fleet-ssh
        r = fleet_remote.spawn_remote_agent(
            machine=req.machine, role=req.role, name=req.name,
            folder=req.folder, initial_prompt=req.initial_prompt,
        )
    else:
        r = fleet_control.spawn(
            role=req.role, name=req.name,
            folder=req.folder, initial_prompt=req.initial_prompt,
        )
    if not r.get("ok"):
        return JSONResponse(r, status_code=400)
    return r


@app.get("/api/machines")
def api_machines() -> dict:
    """List machines known in the fleet, enriched with reachability +
    harness version + agent count. Expensive probes run in parallel."""
    cached = _cache_get("machines-enriched")
    if cached is not None:
        return cached

    machines = fleet_remote.all_machines_including_local()

    # Count agents per machine from both local + aggregated remote registries
    local_agents = registry.live_agents()
    local_count = len(local_agents)
    remote_agents: list[dict] = []
    if fleet_remote.fleet_ssh_available():
        remote_cached = _cache_get("fleet-all-remote")
        if remote_cached is not None:
            remote_agents = remote_cached

    # Dedupe by agent_id — broadcast means the same agent appears in many peers' registries
    seen: set[str] = set()
    deduped_remote: list[dict] = []
    for a in remote_agents:
        aid = a.get("agent_id")
        if aid and aid not in seen:
            seen.add(aid)
            deduped_remote.append(a)

    def _agent_count_for(m: dict) -> int:
        if m.get("is_local"):
            return local_count
        name = (m.get("name") or "").lower()
        return sum(1 for a in deduped_remote
                   if (a.get("machine") or "").lower() == name)

    def _probe(m: dict) -> dict:
        """One SSH hop that checks reachability + harness presence in one shot.
        Uses file-existence (not --version) so old harness binaries also count."""
        start = time.time()
        r = fleet_remote.exec_remote(
            m["name"],
            "test -x $HOME/.local/bin/harness && "
            "($HOME/.local/bin/harness --version 2>/dev/null || echo 'harness installed') "
            "|| echo 'harness missing'",
            timeout=6,
        )
        latency_ms = int((time.time() - start) * 1000)
        online = bool(r.get("ok"))
        out = (r.get("stdout") or "").strip()
        import re as _re
        out = _re.sub(r"\x1b\[[0-9;]*m", "", out)
        out = _re.sub(r"\A\[[^\]\n]+\]\s*\n?", "", out).strip()
        harness_ok = online and "missing" not in out and bool(out)
        version = out if harness_ok else None
        return {"online": online, "latency_ms": latency_ms,
                "harness_installed": harness_ok, "harness_version": version}

    enriched: list[dict] = []
    probes: dict[str, dict] = {}
    if fleet_remote.fleet_ssh_available():
        # Fan out SSH probes in parallel
        targets = [m for m in machines if not m.get("is_local") and not m.get("synthetic") and not _is_offline(m["name"])]
        futures = {_REMOTE_POOL.submit(_probe, m): m for m in targets}
        for fut in as_completed(futures, timeout=12):
            m = futures[fut]
            try:
                probes[m["name"]] = fut.result()
            except Exception:
                probes[m["name"]] = {"online": False, "latency_ms": None,
                                     "harness_installed": False, "harness_version": None}
                _mark_offline(m["name"])

    for m in machines:
        info = {
            **m,
            "agent_count": _agent_count_for(m),
            "online": True if m.get("is_local") else False,
            "latency_ms": 0 if m.get("is_local") else None,
            "harness_installed": True if m.get("is_local") else False,
            "harness_version": "local" if m.get("is_local") else None,
        }
        if m.get("name") in probes:
            info.update(probes[m["name"]])
        if _is_offline(m.get("name") or ""):
            info["online"] = False
            info["offline_reason"] = "marked offline by recent failure"
        enriched.append(info)

    result = {
        "count": len(enriched),
        "machines": enriched,
        "fleet_ssh_available": fleet_remote.fleet_ssh_available(),
    }
    _cache_put("machines-enriched", result)
    return result


@app.post("/api/machines/{machine}/ping")
def api_machine_ping(machine: str) -> dict:
    """Force a fresh connectivity test for one machine (bypasses cache)."""
    if not fleet_remote.fleet_ssh_available():
        return JSONResponse({"ok": False, "error": "fleet-ssh not available"}, status_code=400)
    start = time.time()
    r = fleet_remote.exec_remote(machine, "echo harness-ping-ok", timeout=6)
    latency_ms = int((time.time() - start) * 1000)
    _CACHE.pop("machines-enriched", None)
    ok = bool(r.get("ok")) and "harness-ping-ok" in (r.get("stdout") or "")
    if not ok:
        _mark_offline(machine)
    else:
        _OFFLINE.pop(machine, None)
    return {"ok": ok, "machine": machine, "latency_ms": latency_ms,
            "stdout": r.get("stdout", "")[:200], "stderr": r.get("stderr", "")[:200]}


@app.post("/api/machines/{machine}/install-harness")
def api_machine_install_harness(machine: str) -> dict:
    """Clone and install harness on a remote peer via fleet-ssh.
    Idempotent: if already installed, updates to latest main.
    Long-running — up to 5 minutes. Output captured for debugging."""
    if not fleet_remote.fleet_ssh_available():
        return JSONResponse({"ok": False, "error": "fleet-ssh not available"}, status_code=400)

    # Probe first — if already installed, pull + reinstall; else fresh clone.
    probe = fleet_remote.exec_remote(
        machine,
        "test -d $HOME/the-cc-harness/.git && echo UPDATE || echo CLONE",
        timeout=8,
    )
    path_exists = "UPDATE" in (probe.get("stdout") or "")

    if path_exists:
        cmd = (
            "cd $HOME/the-cc-harness && "
            "git fetch origin main --quiet && "
            "git reset --hard origin/main && "
            "./install.sh 2>&1 | tail -40"
        )
    else:
        cmd = (
            "cd $HOME && "
            "git clone --quiet https://github.com/willau95/the-cc-harness && "
            "cd the-cc-harness && ./install.sh 2>&1 | tail -40"
        )

    r = fleet_remote.exec_remote(machine, cmd, timeout=300)  # up to 5 min
    _CACHE.pop("machines-enriched", None)  # bust so UI picks up new harness state
    ok = bool(r.get("ok"))
    out = (r.get("stdout") or "")
    err = (r.get("stderr") or "")[:1000]
    return {
        "ok": ok,
        "action": "update" if path_exists else "clone",
        "machine": machine,
        "tail": out[-2000:],
        "stderr": err,
    }


@app.get("/api/fs/parent-dirs")
def api_fs_parent_dirs(machine: str | None = None) -> dict:
    """Suggest candidate parent directories where an agent folder can live.
    Used by the Spawn dialog to build a dropdown instead of free-text paths
    (typos in absolute paths caused confusion).

    Returns existing dirs only — no promise to create. The folder name
    (project name) the user types becomes a subdirectory under the parent."""
    cache_key = f"fs-parents::{machine or '__local__'}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    candidates = [
        "$HOME/harness-test",
        "$HOME/Desktop",
        "$HOME/Documents",
        "$HOME/projects",
        "$HOME/workspace",
        "$HOME/work",
        "$HOME/dev",
        "$HOME",  # always last-resort
    ]
    probe = "; ".join(
        f'd={c}; if [ -d "$d" ]; then echo "EXISTS:$d"; fi' for c in candidates
    )
    # We also want to know the resolved home path for display ("~/…")
    probe = f'echo "HOME:$HOME"; {probe}'

    is_local = not machine or machine == "__local__"
    if is_local:
        import subprocess
        try:
            r = subprocess.run(["bash", "-lc", probe], capture_output=True, text=True, timeout=4)
            out = r.stdout
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    else:
        if not fleet_remote.fleet_ssh_available():
            return JSONResponse({"error": "fleet-ssh not available"}, status_code=400)
        r = fleet_remote.exec_remote(machine, probe, timeout=6)
        if not r.get("ok"):
            return JSONResponse({"error": r.get("stderr") or r.get("error")}, status_code=502)
        import re as _re
        out = _re.sub(r"\A\[[^\]\n]+\]\s*\n?", "",
                      _re.sub(r"\x1b\[[0-9;]*m", "", r.get("stdout", "")))

    home = ""
    parents: list[dict] = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("HOME:"):
            home = line[5:]
        elif line.startswith("EXISTS:"):
            full = line[7:]
            display = full
            if home and full.startswith(home):
                display = "~" + full[len(home):]
            parents.append({"path": full, "display": display})

    result = {
        "machine": machine or "__local__",
        "home": home,
        "parents": parents,
    }
    _cache_put(cache_key, result)
    return result


@app.post("/api/machines/{machine}/bootstrap")
def api_machine_bootstrap(machine: str) -> dict:
    """Write peers.yaml + fleet-machines.json onto the peer so its mailbox
    can reach the rest of the fleet. Safe to call repeatedly."""
    if not fleet_remote.fleet_ssh_available():
        return JSONResponse({"ok": False, "error": "fleet-ssh not available"}, status_code=400)
    result = fleet_remote.bootstrap_peer_machine(machine)
    _CACHE.pop("machines-enriched", None)
    return result


@app.get("/api/fleet-all")
def api_fleet_all() -> dict:
    """Local fleet + peers on remote machines (best-effort aggregation)."""
    local = registry.live_agents()
    local_enriched = []
    for ag in local:
        aid = ag["agent_id"]
        local_enriched.append({
            **ag, "last_beat": heartbeat.last_beat(aid),
            "stale": heartbeat.stale(aid), "remote_machine": None,
        })
    remote_all: list[dict] = []
    errors: list[dict] = []
    if fleet_remote.fleet_ssh_available():
        cached = _cache_get("fleet-all-remote")
        if cached is not None:
            remote_all = cached
        else:
            def _fetch_peers(m: dict) -> list[dict] | None:
                try:
                    return fleet_remote.list_remote_fleet(m["name"])
                except Exception as e:
                    errors.append({"machine": m["name"], "error": str(e)})
                    raise

            for chunk in _parallel_remote(fleet_remote.all_machines_including_local(), _fetch_peers):
                remote_all.extend(chunk)
            _cache_put("fleet-all-remote", remote_all)
    return {
        "local": local_enriched,
        "remote": remote_all,
        "errors": errors,
        "total": len(local_enriched) + len(remote_all),
    }


# ===== Chat gateway (dashboard ↔ agent mailbox) =====

@app.get("/api/chat/{agent_id}")
def api_chat_thread(agent_id: str, limit: int = 50) -> dict:
    """Return the conversation thread with this agent: inbox + outbox union,
    ordered by created_at ascending. Dashboard renders as a chat."""
    # Inbox to this agent (messages TO it)
    inbox_lines = list(read_jsonl(mailbox.inbox_path(agent_id)))
    # Outbox from this agent — reconstruct by reading other agents' inboxes
    # where this agent is the sender. For v1 we approximate via events.
    events = eventlog.for_agent_today(agent_id)
    outbox: list[dict] = []
    for e in events:
        if e.get("type") in ("sent_message", "sent_message_remote_fallback"):
            outbox.append({
                "msg_id": e.get("msg_id"),
                "from": agent_id,
                "to": e.get("to"),
                "subject": e.get("subject"),
                "body": "(outbound — stored in recipient's inbox)",
                "created_at": e.get("ts"),
                "direction": "outbound",
            })
    # read/unread state: "consumed" msg_ids were seen by the agent (via
    # receive_messages tool call or inbox_peek surfacing). Everything else is
    # still unread.
    consumed = mailbox._load_consumed(agent_id)
    inbound = [
        {**m, "direction": "inbound",
         "read": m.get("msg_id") in consumed}
        for m in inbox_lines
    ]
    # Outbound is always "sent" — agent wrote them, nothing to "read"
    outbox_with_read = [{**o, "read": True} for o in outbox]
    thread = sorted(inbound + outbox_with_read, key=lambda x: x.get("created_at") or "")
    unread_count = sum(1 for m in thread if m.get("direction") == "inbound" and not m.get("read"))
    return {
        "agent_id": agent_id,
        "count": len(thread),
        "unread_count": unread_count,
        "thread": thread[-limit:],
    }


@app.post("/api/chat/{agent_id}/send")
def api_chat_send(agent_id: str, req: ChatSendRequest) -> dict:
    """Human sends a message to an agent via the dashboard."""
    env = mailbox.send(
        from_id=req.from_id or "human@dashboard",
        to_id=agent_id,
        subject=req.subject or "user_message",
        body=req.body,
    )
    return {"ok": True, "msg_id": env["msg_id"], "envelope": env}


# ===== Tasks aggregator (cross-agent active tasks) =====

@app.get("/api/tasks")
def api_tasks() -> dict:
    """Aggregate active tasks across all local agents (paginated/filterable)."""
    out: list[dict] = []
    for ag in registry.live_agents():
        folder = Path(ag.get("folder", ""))
        if not folder.exists():
            continue
        try:
            tasks = checkpoint.active_tasks(folder)
            for t in tasks:
                out.append({
                    **t,
                    "agent_id": ag["agent_id"],
                    "role": ag.get("role"),
                    "folder": str(folder),
                    "project": folder.name,
                })
        except Exception:
            continue
    out.sort(key=lambda t: t.get("ts", ""), reverse=True)
    return {"count": len(out), "tasks": out}


# (arsenal endpoints defined above, in route-order-safe block)


@app.post("/api/fleet/bulk")
def api_bulk(req: BulkRequest) -> dict:
    r = fleet_control.bulk(req.action, req.agent_ids)
    if not r.get("ok"):
        return JSONResponse(r, status_code=400)
    return r


@app.get("/api/roles")
def api_roles() -> dict:
    """List available role templates so the dashboard spawn dialog can populate a select."""
    roles_dir = Path(__file__).resolve().parents[2] / "roles"
    if not roles_dir.exists():
        return {"roles": []}
    out = []
    for f in sorted(roles_dir.glob("*.md")):
        if f.name.startswith("_"):
            continue
        body = f.read_text()
        desc = ""
        if body.startswith("---"):
            try:
                import yaml
                fm = yaml.safe_load(body.split("---", 2)[1])
                desc = fm.get("description", "") if fm else ""
            except Exception:
                pass
        out.append({"slug": f.stem, "description": desc})
    return {"roles": out}


# ===== WebSocket (file watcher) =====

@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket):
    """Push {type: 'changed', path: ...} whenever ~/.harness/ content changes."""
    await ws.accept()
    from watchfiles import awatch
    try:
        async for changes in awatch(str(config.HARNESS_ROOT)):
            payload = [{"change": str(c[0]), "path": str(c[1])} for c in changes]
            await ws.send_text(json.dumps({"type": "batch", "changes": payload}))
    except WebSocketDisconnect:
        pass


# ===== Frontend (static) =====
# Vite builds into dashboard/frontend/dist/. Serve that. If not built, fall
# back to a friendly "run install.sh or npm run build" message.

DIST_DIR = FRONTEND_DIR / "dist"


@app.get("/")
def root() -> Any:
    idx = DIST_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return JSONResponse({
        "note": "dashboard UI not built. Run: cd dashboard/frontend && npm install && npm run build "
                "(or re-run ./install.sh)",
    }, status_code=503)


# Serve built Vite assets at /assets/* (that's where Vite puts them)
if DIST_DIR.exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    # Catch-all for SPA routes (so / reloading works)
    from fastapi import Request

    @app.get("/{spa_path:path}")
    def spa_catchall(spa_path: str, request: Request) -> Any:
        # Let /api and /ws pass through to their handlers
        if spa_path.startswith(("api/", "ws/")):
            return JSONResponse({"error": "not_found"}, status_code=404)
        idx = DIST_DIR / "index.html"
        if idx.exists():
            return FileResponse(idx)
        return JSONResponse({"error": "ui_not_built"}, status_code=503)
