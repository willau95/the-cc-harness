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
from harness import liveness, transcript, equipment
from harness._util import read_jsonl, now_iso

# Pydantic for request bodies
from pydantic import BaseModel


class SpawnRequest(BaseModel):
    role: str
    name: str
    folder: str
    initial_prompt: str | None = None
    machine: str | None = None  # None = local; else fleet-ssh target name
    equip: list[str] = []  # equipment slugs to pre-install


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


class EquipmentAddRequest(BaseModel):
    slug: str | None = None
    kind: str
    source: str
    name: str | None = None
    description: str | None = None
    topics: list[str] = []
    source_url: str | None = None
    trust: str = "experimental"

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

    # For cross-machine agents, the heartbeat file lives on the peer's disk.
    # Batch-fetch those so we don't per-agent-per-request SSH. One call per
    # peer, 5s TTL cache.
    remote_beats: dict[str, str | None] = {}
    remote_pids: dict[str, bool] = {}  # agent_id -> process_alive
    if fleet_remote.fleet_ssh_available():
        by_machine: dict[str, list[dict]] = {}
        for ag in agents:
            m = ag.get("machine")
            if m and not fleet_remote.is_local_machine(m):
                by_machine.setdefault(m, []).append(ag)

        cache_key = "fleet-remote-beats"
        cached = _cache_get(cache_key)
        if cached is not None:
            remote_beats, remote_pids = cached
        else:
            def _probe_peer(machine: str, peer_agents: list[dict]) -> tuple[dict, dict]:
                """One SSH hop: for each agent, emit a marker + raw last JSONL line
                + session.pid status. We parse on this side to avoid ssh-quoting hell."""
                parts = []
                for ag in peer_agents:
                    aid = ag["agent_id"]
                    folder = ag.get("folder") or ""
                    # BEAT:<aid>:<raw-jsonl-line>   (line is one JSON with 'ts')
                    parts.append(
                        f'echo "BEAT:{aid}:$(tail -1 $HOME/.harness/heartbeats/{aid}.jsonl 2>/dev/null)"'
                    )
                    if folder:
                        parts.append(
                            f'echo PID:{aid}:$(if [ -f "{folder}/.harness/session.pid" ]; then '
                            f'p=$(cat "{folder}/.harness/session.pid"); '
                            f'if kill -0 "$p" 2>/dev/null; then echo alive; else echo dead; fi; '
                            f"else echo unknown; fi)"
                        )
                cmd = "; ".join(parts)
                r = fleet_remote.exec_remote(machine, cmd, timeout=8)
                beats: dict[str, str | None] = {}
                pids: dict[str, bool] = {}
                if not r.get("ok"):
                    return beats, pids
                import re as _re
                import json as _json
                text = _re.sub(r"\x1b\[[0-9;]*m", "", r.get("stdout") or "")
                text = _re.sub(r"^\[[^\]\n]+\]\s*\n?", "", text, flags=_re.MULTILINE)
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("BEAT:"):
                        rest = line[5:]
                        colon = rest.find(":")
                        if colon < 0:
                            continue
                        aid = rest[:colon]
                        raw = rest[colon+1:].strip()
                        if not raw:
                            beats[aid] = None
                            continue
                        try:
                            rec = _json.loads(raw)
                            beats[aid] = rec.get("ts")
                        except _json.JSONDecodeError:
                            beats[aid] = None
                    elif line.startswith("PID:"):
                        rest = line[4:]
                        colon = rest.find(":")
                        if colon < 0:
                            continue
                        aid = rest[:colon]
                        state = rest[colon+1:].strip()
                        if state == "alive":
                            pids[aid] = True
                        elif state == "dead":
                            pids[aid] = False
                return beats, pids

            merged_beats: dict[str, str | None] = {}
            merged_pids: dict[str, bool] = {}
            futures = {_REMOTE_POOL.submit(_probe_peer, m, pa): m for m, pa in by_machine.items()}
            for fut in as_completed(futures, timeout=12):
                try:
                    b, p = fut.result()
                    merged_beats.update(b)
                    merged_pids.update(p)
                except Exception:
                    pass
            remote_beats = merged_beats
            remote_pids = merged_pids
            _cache_put(cache_key, (remote_beats, remote_pids))

    enriched = []
    for ag in agents:
        aid = ag["agent_id"]
        # Heartbeat: local first, fall back to remote probe
        last = heartbeat.last_beat(aid) or remote_beats.get(aid)
        # Staleness: if we have a last_beat, derive; else defer to fallback
        if last:
            try:
                from datetime import datetime, timezone, timedelta
                dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                stale_raw = (datetime.now(timezone.utc) - dt) > timedelta(
                    minutes=config.load_config().get("zombie_timeout_minutes", 30))
            except Exception:
                stale_raw = heartbeat.stale(aid)
        else:
            stale_raw = heartbeat.stale(aid)

        # Liveness: local PID first, then remote PID, else None
        alive = _alive_for(ag)
        if alive is None and aid in remote_pids:
            alive = remote_pids[aid]

        if alive is False:
            stale = True
        elif alive is True:
            stale = stale_raw
        else:
            stale = stale_raw

        enriched.append({**ag, "last_beat": last, "stale": stale,
                         "paused": _paused_for(ag),
                         "process_alive": alive})
    return {"count": len(enriched), "agents": enriched}


def _remote_transcript(machine: str, folder: str, limit: int) -> dict:
    """Pull Claude Code's session jsonl from a peer via fleet-ssh, parse
    on Mac-A side. Cache 5s so 3s UI poll doesn't re-SSH aggressively."""
    cache_key = f"transcript-remote::{machine}::{folder}::{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    # Compute Claude Code's project dir slug on the peer (path → dashes)
    slug = str(Path(folder).resolve()).replace("/", "-")
    cmd = (
        f'D="$HOME/.claude/projects/{slug}"; '
        f'if [ -d "$D" ]; then '
        f'  F=$(ls -t "$D"/*.jsonl 2>/dev/null | head -1); '
        f'  if [ -n "$F" ]; then '
        f'    echo "SESSION_FILE:$F"; '
        f'    stat -f "SESSION_MTIME:%m" "$F" 2>/dev/null || stat -c "SESSION_MTIME:%Y" "$F" 2>/dev/null; '
        f'    stat -f "SESSION_SIZE:%z" "$F" 2>/dev/null || stat -c "SESSION_SIZE:%s" "$F" 2>/dev/null; '
        f'    echo TRANSCRIPT_BEGIN; '
        f'    tail -n {max(limit * 4, 400)} "$F"; '
        f'    echo TRANSCRIPT_END; '
        f'  else echo NO_SESSION_FILE; fi; '
        f'else echo NO_PROJECT_DIR; fi'
    )
    r = fleet_remote.exec_remote(machine, cmd, timeout=10)
    if not r.get("ok"):
        return {"available": False, "reason": "fleet-ssh failed", "timeline": []}
    out = r.get("stdout") or ""
    import re as _re
    out = _re.sub(r"\x1b\[[0-9;]*m", "", out)
    out = _re.sub(r"^\[[^\]\n]+\]\s*\n?", "", out, flags=_re.MULTILINE)
    if "NO_PROJECT_DIR" in out:
        return {"available": False, "reason": "no claude session ever started on this peer for this folder",
                "timeline": []}
    if "NO_SESSION_FILE" in out:
        return {"available": False, "reason": "claude project dir exists but no session jsonl",
                "timeline": []}
    session_file = mtime = size = None
    for line in out.splitlines():
        if line.startswith("SESSION_FILE:"):
            session_file = line[len("SESSION_FILE:"):].strip()
        elif line.startswith("SESSION_MTIME:"):
            try:
                mtime = float(line[len("SESSION_MTIME:"):].strip())
            except ValueError:
                pass
        elif line.startswith("SESSION_SIZE:"):
            try:
                size = int(line[len("SESSION_SIZE:"):].strip())
            except ValueError:
                pass
    # Extract the raw jsonl chunk between markers
    if "TRANSCRIPT_BEGIN" not in out or "TRANSCRIPT_END" not in out:
        return {"available": False, "reason": "could not extract transcript from peer", "timeline": []}
    chunk = out.split("TRANSCRIPT_BEGIN", 1)[1].split("TRANSCRIPT_END", 1)[0]
    # Write to a temp file + parse via our local transcript module's parser
    # logic — but transcript.read_timeline reads from a filename. Inline the
    # parser instead to avoid tmp-file overhead:
    import json as _json
    entries: list[dict] = []
    for line in chunk.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = _json.loads(line)
        except _json.JSONDecodeError:
            continue
        # Reuse the same shape transcript.read_timeline produces by calling
        # its helper functions directly.
        t = rec.get("type")
        ts = rec.get("timestamp")
        if t == "user":
            msg = rec.get("message") or {}
            content = msg.get("content")
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        result_text = transcript._extract_text([b])
                        entries.append({
                            "ts": ts, "role": "tool", "kind": "tool_result",
                            "tool_id": b.get("tool_use_id"),
                            "text": result_text[:4000],
                            "truncated": len(result_text) > 4000,
                            "is_error": bool(b.get("is_error")),
                        })
                text = transcript._extract_text([x for x in content if isinstance(x, dict) and x.get("type") == "text"])
                if text:
                    entries.append({"ts": ts, "role": "user", "kind": "prompt", "text": text[:4000]})
            elif isinstance(content, str) and content.strip():
                entries.append({"ts": ts, "role": "user", "kind": "prompt", "text": content[:4000]})
        elif t == "assistant":
            msg = rec.get("message") or {}
            for b in msg.get("content") or []:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text":
                    txt = b.get("text", "")
                    if txt.strip():
                        entries.append({"ts": ts, "role": "assistant", "kind": "text", "text": txt[:8000]})
                elif bt == "thinking":
                    txt = b.get("thinking", "")
                    if txt.strip():
                        entries.append({"ts": ts, "role": "assistant", "kind": "thinking", "text": txt[:4000]})
                elif bt == "tool_use":
                    entries.append({
                        "ts": ts, "role": "assistant", "kind": "tool_use",
                        "tool_name": b.get("name"),
                        "tool_id": b.get("id"),
                        "tool_input_summary": transcript._summarize_tool_input(b.get("name", ""), b.get("input") or {}),
                        "tool_input": b.get("input") or {},
                    })
        elif t == "attachment":
            att = rec.get("attachment") or {}
            hook = att.get("hookName")
            if hook:
                entries.append({
                    "ts": ts, "role": "system", "kind": "hook",
                    "hook_name": hook,
                    "text": (att.get("stdout") or "")[:1000],
                })
    result = {
        "available": True,
        "session": {"session_id": Path(session_file or "").stem, "file_path": session_file,
                    "mtime": mtime, "size_bytes": size},
        "count": len(entries),
        "timeline": entries[-limit:],
    }
    _cache_put(cache_key, result)
    return result


@app.get("/api/agents/{agent_id}/transcript")
def api_agent_transcript(agent_id: str, limit: int = 300) -> dict:
    """Return a normalized timeline from Claude Code's per-session JSONL.
    Works for local AND remote agents (remote via fleet-ssh tail)."""
    ag = registry.find(agent_id)
    if not ag:
        return JSONResponse({"error": "not_found"}, status_code=404)
    folder = ag.get("folder")
    if not folder:
        return {"agent_id": agent_id, "available": False,
                "reason": "no folder in registry", "timeline": []}
    # Local path
    if Path(folder).exists():
        meta = transcript.session_metadata(folder)
        if not meta:
            return {"agent_id": agent_id, "available": False,
                    "reason": "no claude session found for this folder", "timeline": []}
        tl = transcript.read_timeline(folder, limit=limit)
        return {"agent_id": agent_id, "available": True,
                "session": meta, "count": len(tl), "timeline": tl}
    # Remote path — pull via fleet-ssh
    machine = ag.get("machine")
    if machine and not fleet_remote.is_local_machine(machine) and fleet_remote.fleet_ssh_available():
        r = _remote_transcript(machine, folder, limit)
        return {"agent_id": agent_id, **r}
    return {"agent_id": agent_id, "available": False,
            "reason": f"folder not local and no fleet-ssh for machine={machine}",
            "timeline": []}


@app.get("/api/agents/{agent_id}/activity")
def api_agent_activity(agent_id: str) -> dict:
    """Read the PreToolUse/PostToolUse-written current_activity.json.
    Local: direct file read. Remote: fleet-ssh cat."""
    ag = registry.find(agent_id)
    if not ag:
        return JSONResponse({"error": "not_found"}, status_code=404)
    folder = ag.get("folder")
    if not folder:
        return {"activity": None}
    # Local
    if Path(folder).exists():
        path = Path(folder) / ".harness" / "current_activity.json"
        if not path.exists():
            return {"activity": None}
        try:
            return {"activity": json.loads(path.read_text())}
        except Exception:
            return {"activity": None}
    # Remote
    machine = ag.get("machine")
    if machine and not fleet_remote.is_local_machine(machine) and fleet_remote.fleet_ssh_available():
        r = fleet_remote.read_remote_file(machine, f"{folder}/.harness/current_activity.json")
        if r.get("ok") and r.get("content"):
            import re as _re
            content = _re.sub(r"\x1b\[[0-9;]*m", "", r["content"])
            content = _re.sub(r"^\[[^\]\n]+\]\s*\n?", "", content, flags=_re.MULTILINE).strip()
            try:
                return {"activity": json.loads(content)}
            except Exception:
                return {"activity": None}
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

    # Cross-machine heartbeat + PID probe — if the agent lives on a peer,
    # its heartbeat file is on the peer's disk. Same logic as /api/fleet.
    last = heartbeat.last_beat(agent_id)
    alive = _alive_for(ag)
    if (last is None or alive is None) and ag.get("machine") and not fleet_remote.is_local_machine(ag.get("machine")):
        if fleet_remote.fleet_ssh_available():
            machine = ag["machine"]
            folder = ag.get("folder") or ""
            cmd = (
                f'echo "BEAT:$(tail -1 $HOME/.harness/heartbeats/{agent_id}.jsonl 2>/dev/null)"; '
                f'echo PID:$(if [ -f "{folder}/.harness/session.pid" ]; then '
                f'p=$(cat "{folder}/.harness/session.pid"); '
                f'if kill -0 "$p" 2>/dev/null; then echo alive; else echo dead; fi; '
                f'else echo unknown; fi)'
            )
            r = fleet_remote.exec_remote(machine, cmd, timeout=6)
            if r.get("ok"):
                import re as _re
                import json as _json
                text = _re.sub(r"\x1b\[[0-9;]*m", "", r.get("stdout") or "")
                text = _re.sub(r"^\[[^\]\n]+\]\s*\n?", "", text, flags=_re.MULTILINE)
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("BEAT:"):
                        raw = line[5:].strip()
                        if raw:
                            try:
                                last = _json.loads(raw).get("ts") or last
                            except _json.JSONDecodeError:
                                pass
                    elif line.startswith("PID:"):
                        state = line[4:].strip()
                        if state == "alive":
                            alive = True
                        elif state == "dead":
                            alive = False

    # Re-compute staleness from the final last_beat
    if last:
        try:
            from datetime import datetime, timezone, timedelta
            dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            stale = (datetime.now(timezone.utc) - dt) > timedelta(
                minutes=config.load_config().get("zombie_timeout_minutes", 30))
        except Exception:
            stale = heartbeat.stale(agent_id)
    else:
        stale = heartbeat.stale(agent_id)

    ag = {**ag, "paused": _paused_for(ag), "process_alive": alive}
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
    equip_csv = ",".join(req.equip) if req.equip else None
    if req.machine and not fleet_remote.is_local_machine(req.machine):
        r = fleet_remote.spawn_remote_agent(
            machine=req.machine, role=req.role, name=req.name,
            folder=req.folder, initial_prompt=req.initial_prompt,
            equip_csv=equip_csv,
        )
    else:
        r = fleet_control.spawn(
            role=req.role, name=req.name,
            folder=req.folder, initial_prompt=req.initial_prompt,
            equip_csv=equip_csv,
        )
    if not r.get("ok"):
        return JSONResponse(r, status_code=400)
    return r


# ===== Equipment (武器库) — shared Claude-Code-native artifact library =====

@app.get("/api/equipment")
def api_equipment_list(kind: str | None = None) -> dict:
    items = equipment.list_all(kind=kind)
    return {"count": len(items), "items": items}


@app.get("/api/equipment/{slug}")
def api_equipment_get(slug: str) -> dict:
    m = equipment.get(slug)
    if not m:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return m


@app.post("/api/equipment/add")
def api_equipment_add(req: EquipmentAddRequest) -> dict:
    try:
        meta = equipment.add(
            slug=req.slug, kind=req.kind, source=req.source,
            name=req.name, description=req.description, topics=req.topics,
            source_url=req.source_url, trust=req.trust,
            added_by="human@dashboard",
        )
        return {"ok": True, "meta": meta}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


@app.get("/api/equipment/search/{query}")
def api_equipment_search(query: str) -> dict:
    items = equipment.search(query)
    return {"count": len(items), "items": items}


# Max size for file content streaming — skills rarely have files > this, but
# some do (PDFs / long reference.md). Cap to prevent accidental OOM.
MAX_EQUIPMENT_FILE_BYTES = 512 * 1024  # 512 KB

# Extensions we'll render as text; everything else is returned as "binary"
TEXT_EXTS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".bash",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".html",
    ".css", ".scss", ".sql", ".rs", ".go", ".java", ".rb", ".php", ".c",
    ".cpp", ".h", ".hpp", ".swift", ".kt", ".r", ".lua", ".vim", ".zsh",
    ".fish", ".env", ".gitignore", ".dockerfile", ".makefile",
}


def _is_text_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTS:
        return True
    # Files without extension, check if content looks like text
    if not suffix and path.stat().st_size < 100_000:
        try:
            path.read_text()
            return True
        except UnicodeDecodeError:
            return False
    return False


@app.get("/api/equipment/{slug}/tree")
def api_equipment_tree(slug: str) -> dict:
    """List every file under an equipment item's content/ dir as a flat
    tree. Used by the dashboard detail page to show the full skill
    structure — SKILL.md, references, scripts/, themes/, etc."""
    meta = equipment.get(slug)
    if not meta:
        return JSONResponse({"error": "not_found"}, status_code=404)
    content = Path(meta["path"]) / "content"
    if not content.exists():
        return {"slug": slug, "files": []}
    root_str = str(content)
    files: list[dict] = []
    for f in sorted(content.rglob("*")):
        if f.is_dir():
            continue
        # Skip anything inside .git/
        if ".git" in f.parts:
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        rel = str(f.relative_to(content))
        files.append({
            "path": rel,
            "size": st.st_size,
            "is_text": _is_text_file(f),
            "ext": f.suffix.lower(),
        })
    return {"slug": slug, "content_root": root_str, "count": len(files),
            "files": files}


@app.get("/api/equipment/{slug}/file")
def api_equipment_file(slug: str, path: str) -> dict:
    """Return the content of one file inside an equipment item's content/
    dir. Text files are returned inline; binary files return size + type
    only. Hard-capped at MAX_EQUIPMENT_FILE_BYTES."""
    meta = equipment.get(slug)
    if not meta:
        return JSONResponse({"error": "not_found"}, status_code=404)
    content_root = (Path(meta["path"]) / "content").resolve()
    # Guard against path-escape (e.g. '../../../etc/passwd')
    full = (content_root / path).resolve()
    try:
        full.relative_to(content_root)
    except ValueError:
        return JSONResponse({"error": "path escapes equipment root"}, status_code=400)
    if not full.exists() or not full.is_file():
        return JSONResponse({"error": "file not found"}, status_code=404)
    size = full.stat().st_size
    if size > MAX_EQUIPMENT_FILE_BYTES:
        return {
            "path": path, "size": size, "truncated": True,
            "reason": f"file larger than {MAX_EQUIPMENT_FILE_BYTES} bytes — open locally",
            "content": None, "is_text": False,
        }
    if _is_text_file(full):
        try:
            text = full.read_text(errors="replace")
            return {"path": path, "size": size, "is_text": True,
                    "content": text, "ext": full.suffix.lower()}
        except OSError as e:
            return JSONResponse({"error": str(e)}, status_code=500)
    return {"path": path, "size": size, "is_text": False,
            "ext": full.suffix.lower(), "content": None,
            "reason": "binary file — not rendered inline"}


class EquipmentTrustRequest(BaseModel):
    trust: str


@app.post("/api/equipment/{slug}/trust")
def api_equipment_set_trust(slug: str, req: EquipmentTrustRequest) -> dict:
    try:
        r = equipment.set_trust(slug, req.trust, by="human@dashboard")
        return r
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)


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
        """One SSH hop checking: reachability, harness presence, and common
        setup problems (ANTHROPIC_BASE_URL leftover from cc-switch/openclaw;
        missing claude OAuth credentials so user never completed `claude login`)."""
        start = time.time()
        r = fleet_remote.exec_remote(
            m["name"],
            # Compound probe — do it all in one round trip
            "echo HARNESS_$(test -x $HOME/.local/bin/harness && "
            "  ($HOME/.local/bin/harness --version 2>/dev/null || echo installed) "
            "  || echo missing); "
            # Check zshrc / bashrc for a set ANTHROPIC_BASE_URL (the cc-switch /
            # claude-code-router leftover that silently breaks claude)
            "echo BASE_URL_$(grep -h '^export ANTHROPIC_BASE_URL' "
            "  $HOME/.zshrc $HOME/.zprofile $HOME/.bashrc $HOME/.bash_profile "
            "  2>/dev/null | head -1 || echo clean); "
            # Check claude is logged in — v2.1.40+ stores credentials in
            # macOS Keychain (security find-generic-password -s 'Claude Code-credentials')
            # not ~/.claude/credentials.json. We probe by checking BOTH:
            # file credentials OR a working keychain entry.
            # Claude login probe is TWO-STAGE to avoid the false positive
            # where a stale keychain entry exists but claude CLI still fails
            # with 'Not logged in'. First: check credentials.json or keychain
            # (fast). Second: check for a known-good claude binary path.
            # Result values: yes (confirmed), stale (keychain present but claude
            # v2.1.40+ doesn't consider it valid), missing (neither).
            "echo CLAUDE_LOGIN_$(if test -f $HOME/.claude/credentials.json; then "
            "  echo yes; "
            "elif security find-generic-password -s 'Claude Code-credentials' >/dev/null 2>&1; then "
            "  if test -x $HOME/.local/bin/claude && test -L $HOME/.local/bin/claude; then "
            "    echo yes; "
            "  else "
            "    echo stale; "  # keychain entry but no modern claude to use it
            "  fi; "
            "else echo missing; fi); "
            # Also check for the 'stale binary' case: if /usr/local/bin/claude
            # exists AND differs from ~/.local/bin/claude target, warn —
            # the npm-global v2.1.19 leftover interferes with v2.1.40+
            # keychain logins (issue we actually hit in the wild).
            "echo STALE_BINARY_$(test -f /usr/local/bin/claude "
            "  && test -L $HOME/.local/bin/claude "
            "  && ! test /usr/local/bin/claude -ef $(readlink -f $HOME/.local/bin/claude 2>/dev/null) "
            "  && echo yes || echo no)",
            timeout=6,
        )
        latency_ms = int((time.time() - start) * 1000)
        online = bool(r.get("ok"))
        out = (r.get("stdout") or "")
        import re as _re
        out = _re.sub(r"\x1b\[[0-9;]*m", "", out)
        out = _re.sub(r"\A\[[^\]\n]+\]\s*\n?", "", out).strip()
        # Parse each marker line
        harness_version = None
        harness_ok = False
        base_url_issue = None
        claude_logged_in: bool | None = None
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("HARNESS_"):
                payload = line[len("HARNESS_"):]
                if payload == "missing" or not payload:
                    harness_ok = False
                else:
                    harness_ok = True
                    harness_version = payload
            elif line.startswith("BASE_URL_"):
                payload = line[len("BASE_URL_"):]
                if payload and payload != "clean":
                    base_url_issue = payload  # the offending export line
            elif line.startswith("CLAUDE_LOGIN_"):
                payload = line[len("CLAUDE_LOGIN_"):]
                # yes = confirmed login / stale = keychain exists but likely
                # broken (v2.1.19 shim case) / missing = no credentials at all.
                # For UI we treat stale as "not really logged in" so the card's
                # warning fires correctly instead of lying.
                claude_logged_in = (payload == "yes")
            elif line.startswith("STALE_BINARY_"):
                payload = line[len("STALE_BINARY_"):]
                stale_binary = (payload == "yes")
                # attach below
        return {"online": online, "latency_ms": latency_ms,
                "harness_installed": harness_ok and online,
                "harness_version": harness_version if harness_ok else None,
                "anthropic_base_url_issue": base_url_issue,
                "claude_logged_in": claude_logged_in,
                "stale_claude_binary": locals().get("stale_binary", False)}

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


@app.post("/api/machines/{machine}/fix-base-url")
def api_machine_fix_base_url(machine: str) -> dict:
    """Remove `export ANTHROPIC_BASE_URL=...` lines from the peer's shell
    rc files. This is the cc-switch / claude-code-router leftover that makes
    `claude` fail with 'Unable to connect to API (ConnectionRefused)'.

    Safe — creates a .bak of each rc before editing."""
    if not fleet_remote.fleet_ssh_available() and machine != "__local__":
        return JSONResponse({"ok": False, "error": "fleet-ssh not available"}, status_code=400)
    cmd = (
        "for rc in $HOME/.zshrc $HOME/.zprofile $HOME/.bashrc $HOME/.bash_profile; do "
        "  [ -f $rc ] && sed -i.bak '/^export ANTHROPIC_BASE_URL/d' $rc && "
        "  echo patched:$rc; "
        "done; "
        "echo DONE"
    )
    if machine == "__local__":
        import subprocess
        try:
            r = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=10)
            ok = r.returncode == 0
            out = r.stdout
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    else:
        r = fleet_remote.exec_remote(machine, cmd, timeout=10)
        ok = bool(r.get("ok"))
        out = r.get("stdout", "")
    _CACHE.pop("machines-enriched", None)
    return {"ok": ok, "machine": machine, "output": out[:2000]}


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
    # Inbox to this agent (messages TO it). For agents living on a peer, the
    # inbox file sits on that peer's disk — fetch it via fleet-ssh.
    ag = registry.find(agent_id)
    machine = (ag or {}).get("machine")
    consumed: set[str] = set()
    if ag and machine and not fleet_remote.is_local_machine(machine) and fleet_remote.fleet_ssh_available():
        # Plural "mailboxes" — matches config.mailbox_dir() on receiving side.
        inbox_lines = fleet_remote.read_remote_jsonl(
            machine, f"~/.harness/mailboxes/{agent_id}/inbox.jsonl"
        )
        consumed_result = fleet_remote.read_remote_file(
            machine, f"~/.harness/mailboxes/{agent_id}/inbox.consumed"
        )
        if consumed_result.get("ok") and consumed_result.get("content"):
            consumed = {line.strip() for line in consumed_result["content"].splitlines() if line.strip()}
    else:
        inbox_lines = list(read_jsonl(mailbox.inbox_path(agent_id)))
        consumed = mailbox._load_consumed(agent_id)
    # Outbox from this agent — reconstruct via events (metadata only) +
    # for cross-machine agents, fetch peer-local human@dashboard inbox which
    # is where the agent's replies land (they call send_message --to human@dashboard).
    if ag and machine and not fleet_remote.is_local_machine(machine) and fleet_remote.fleet_ssh_available():
        # Pull events from peer for this agent
        import re as _re2
        import json as _json2
        r = fleet_remote.exec_remote(
            machine,
            f"~/.local/bin/harness events dump-json --limit 200 --days 2 2>/dev/null",
            timeout=8,
        )
        peer_events = []
        if r.get("ok") and r.get("stdout"):
            s = _re2.sub(r"\x1b\[[0-9;]*m", "", r["stdout"])
            s = _re2.sub(r"\A\[[^\]\n]+\]\s*\n?", "", s)
            jstart = s.find("[")
            jend = s.rfind("]") + 1
            if jstart >= 0 and jend > jstart:
                try:
                    peer_events = _json2.loads(s[jstart:jend])
                except _json2.JSONDecodeError:
                    pass
        events = [e for e in peer_events if e.get("agent") == agent_id]
        # Also pull human@dashboard inbox from peer (contains bodies of outbound)
        human_inbox = fleet_remote.read_remote_jsonl(
            machine, "~/.harness/mailboxes/human@dashboard/inbox.jsonl"
        )
    else:
        events = eventlog.for_agent_today(agent_id)
        human_inbox = list(read_jsonl(mailbox.inbox_path("human@dashboard")))
    outbox: list[dict] = []
    # Events provide the full list of sends, even if body is elsewhere
    for e in events:
        if e.get("type") in ("sent_message", "sent_message_remote_fallback"):
            outbox.append({
                "msg_id": e.get("msg_id"),
                "from": agent_id,
                "to": e.get("to"),
                "subject": e.get("subject"),
                "body": None,  # fill in below from human_inbox if match
                "created_at": e.get("ts"),
                "direction": "outbound",
            })
    # For messages the agent sent TO human@dashboard, the body lives in the
    # peer's mailboxes/human@dashboard/inbox.jsonl — match by msg_id.
    by_id = {m.get("msg_id"): m for m in human_inbox if m.get("from") == agent_id}
    for o in outbox:
        if o.get("to") == "human@dashboard" and o.get("msg_id") in by_id:
            o["body"] = by_id[o["msg_id"]].get("body")
    # Also handle the case where events are missing but human_inbox has entries
    # (shouldn't normally happen, but defensive)
    seen_ids = {o["msg_id"] for o in outbox}
    for m in human_inbox:
        if m.get("from") == agent_id and m.get("msg_id") not in seen_ids:
            outbox.append({
                "msg_id": m.get("msg_id"),
                "from": agent_id,
                "to": "human@dashboard",
                "subject": m.get("subject"),
                "body": m.get("body"),
                "created_at": m.get("created_at"),
                "direction": "outbound",
            })
    # read/unread state: "consumed" msg_ids were seen by the agent (via
    # receive_messages tool call or inbox_peek surfacing). Everything else is
    # still unread. 'consumed' is already populated above (local or remote).
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
