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
from harness import control as fleet_control
from harness._util import read_jsonl

# Pydantic for request bodies
from pydantic import BaseModel


class SpawnRequest(BaseModel):
    role: str
    name: str
    folder: str
    initial_prompt: str | None = None


class BulkRequest(BaseModel):
    action: str
    agent_ids: list[str]

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


@app.get("/api/arsenal/{slug}")
def api_arsenal_get(slug: str) -> dict:
    item = arsenal.get(slug)
    if not item:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return item


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
    return {"project": proj, "state": state, "members": members}


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
    r = fleet_control.spawn(
        role=req.role, name=req.name,
        folder=req.folder, initial_prompt=req.initial_prompt,
    )
    if not r.get("ok"):
        return JSONResponse(r, status_code=400)
    return r


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
