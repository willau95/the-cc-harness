"""Dashboard backend — FastAPI, reads ~/.harness/, serves frontend static files.
Run: `harness dashboard` → uvicorn dashboard.backend.main:app --port 9999
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

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


# ===== REST =====

@app.get("/api/fleet")
def api_fleet() -> dict:
    agents = registry.live_agents()
    enriched = []
    for ag in agents:
        aid = ag["agent_id"]
        last = heartbeat.last_beat(aid)
        stale = heartbeat.stale(aid)
        enriched.append({**ag, "last_beat": last, "stale": stale})
    return {"count": len(enriched), "agents": enriched}


@app.get("/api/agents/{agent_id}")
def api_agent(agent_id: str) -> dict:
    ag = registry.find(agent_id)
    if not ag:
        return JSONResponse({"error": "not_found"}, status_code=404)
    last = heartbeat.last_beat(agent_id)
    stale = heartbeat.stale(agent_id)
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
    """Merged events across all agents (today only for v1)."""
    out: list[dict] = []
    events_root = config.HARNESS_ROOT / "events"
    if events_root.exists():
        from harness._util import today_str
        today = today_str()
        for agent_dir in events_root.iterdir():
            f = agent_dir / f"{today}.jsonl"
            for e in read_jsonl(f):
                out.append({"agent": agent_dir.name, **e})
    out.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return {"count": len(out[:limit]), "events": out[:limit]}


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
        "chain_depth": r[7],
    } for r in rows]
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
    if not item:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return item


@app.post("/api/arsenal/{slug}/trust")
def api_arsenal_set_trust(slug: str, req: ArsenalTrustRequest) -> dict:
    arsenal.set_trust(slug, req.trust, by="human@dashboard")
    return {"ok": True, "slug": slug, "trust": req.trust}


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
    """List machines known in the fleet (from mac-fleet-control registry)."""
    machines = fleet_remote.all_machines_including_local()
    return {"count": len(machines), "machines": machines,
            "fleet_ssh_available": fleet_remote.fleet_ssh_available()}


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
        for m in fleet_remote.all_machines_including_local():
            if m.get("is_local") or m.get("synthetic"):
                continue
            try:
                peers = fleet_remote.list_remote_fleet(m["name"])
                remote_all.extend(peers)
            except Exception as e:
                errors.append({"machine": m["name"], "error": str(e)})
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
    inbound = [{**m, "direction": "inbound"} for m in inbox_lines]
    thread = sorted(inbound + outbox, key=lambda x: x.get("created_at") or "")
    return {"agent_id": agent_id, "count": len(thread), "thread": thread[-limit:]}


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
