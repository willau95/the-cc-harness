"""Fleet control primitives: pause, resume, kill, spawn.

We don't manage Claude Code processes directly (they're long-lived interactive
CLIs the user opened). Control here is *soft* — flags on disk that skill tools
respect at invocation time, plus registry mutations.

- **Pause:** writes a sentinel `.harness/paused` file. skill tool _common.py
  checks this and short-circuits with a standard "paused" response.
- **Resume:** removes the sentinel.
- **Kill:** unregisters agent + removes heartbeat. Next `harness status` shows
  it gone. Any future skill-tool call from the agent folder will auto-register
  on its next heartbeat (soft). For hard-kill of the Claude Code process itself
  the user still Ctrl-C's their terminal — we don't reach across.
- **Spawn:** runs the init logic programmatically + returns the new agent_id.
  Does NOT launch `claude` (that needs a TTY the server doesn't have); returns
  the folder + instruction for the user.
"""
from __future__ import annotations
from pathlib import Path
from . import identity, registry, heartbeat, eventlog
from ._util import now_iso


def pause_sentinel(folder: Path) -> Path:
    return folder / ".harness" / "paused"


def is_paused(folder: Path) -> bool:
    return pause_sentinel(folder).exists()


def pause(agent_id: str) -> dict:
    """Mark the agent paused. Requires we know its folder (from registry)."""
    entry = registry.find(agent_id)
    if not entry:
        return {"ok": False, "error": f"unknown agent {agent_id}"}
    folder = Path(entry.get("folder", ""))
    if not folder.exists():
        return {"ok": False, "error": f"folder missing: {folder}"}
    sentinel = pause_sentinel(folder)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(now_iso())
    eventlog.log(agent_id, "paused")
    return {"ok": True, "agent_id": agent_id, "folder": str(folder)}


def resume(agent_id: str) -> dict:
    entry = registry.find(agent_id)
    if not entry:
        return {"ok": False, "error": f"unknown agent {agent_id}"}
    folder = Path(entry.get("folder", ""))
    sentinel = pause_sentinel(folder)
    if sentinel.exists():
        sentinel.unlink()
    eventlog.log(agent_id, "resumed")
    return {"ok": True, "agent_id": agent_id}


def kill(agent_id: str) -> dict:
    """Soft-kill: unregister + purge heartbeat. The Claude Code process, if
    open, keeps running (the user closes it). But the fleet no longer sees this
    agent until it auto-re-registers via a future tool call."""
    entry = registry.find(agent_id)
    if not entry:
        return {"ok": False, "error": f"unknown agent {agent_id}"}
    registry.unregister(agent_id)
    from . import config
    hb = config.heartbeat_file(agent_id)
    if hb.exists():
        hb.unlink()
    eventlog.log(agent_id, "killed")
    return {"ok": True, "agent_id": agent_id}


def spawn(role: str, name: str, folder: str | Path,
          initial_prompt: str | None = None) -> dict:
    """Programmatic init: scaffold a new agent folder. Does NOT launch Claude Code."""
    from .cli import REPO_ROOT  # avoid circular at module load
    import json, shutil
    from ._util import slugify

    folder = Path(folder).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)

    # Duplicate minimal logic from cli.init() — we can't call click-wrapped
    # function directly from non-CLI context cleanly, so we replicate.
    role_file = REPO_ROOT / "roles" / f"{role}.md"
    if not role_file.exists():
        return {"ok": False, "error": f"role not found: {role}"}

    slug = slugify(name)
    existing = identity.load_identity(folder)
    if existing and existing.get("slug") == slug:
        ident = dict(existing)
        ident["role"] = role
        identity.write_identity(folder, ident)
    else:
        ident = identity.create_identity(folder, role=role, slug=slug)
    registry.register(ident)

    base_pre = (REPO_ROOT / "roles" / "_base-preamble.md").read_text()
    role_body = role_file.read_text()
    if role_body.startswith("---"):
        parts = role_body.split("---", 2)
        if len(parts) >= 3:
            role_body = parts[2].lstrip()
    claude_md = (
        f"# Agent: {ident['agent_id']}\n"
        f"# Role: {role}\n\n"
        + base_pre + "\n\n" + role_body
    )
    if initial_prompt:
        claude_md += f"\n\n## Initial prompt (from spawner)\n\n{initial_prompt}\n"
    (folder / "CLAUDE.md").write_text(claude_md)

    for skill_name in ("harness", "harness-conventions", f"role-{role}"):
        src = REPO_ROOT / "skill" / skill_name
        dst = folder / ".claude" / "skills" / skill_name
        if src.exists():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    # Shebang rewrite (same as cli._rewrite_tool_scripts)
    from .cli import _rewrite_tool_scripts
    skills_dir = folder / ".claude" / "skills"
    _rewrite_tool_scripts(list(skills_dir.iterdir()) if skills_dir.exists() else [])

    # Settings
    from . import config
    settings_dir = folder / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    hook_root = REPO_ROOT / "hooks"
    settings = {
        "hooks": {
            "SessionStart": [{"matcher": "", "hooks": [{
                "type": "command",
                "command": f"bash {hook_root / 'session_start.sh'} {folder}",
            }]}],
            "PreCompact": [{"matcher": "", "hooks": [{
                "type": "command",
                "command": f"bash {hook_root / 'on_compact.sh'} {folder}",
            }]}],
        },
        "permissions": {"allow": [
            "Bash(python -m harness.*:*)",
            "Bash(harness *:*)",
            f"Read({config.HARNESS_ROOT}/**)",
            f"Write({config.HARNESS_ROOT}/**)",
            f"Edit({config.HARNESS_ROOT}/**)",
        ]},
    }
    (settings_dir / "settings.local.json").write_text(json.dumps(settings, indent=2))
    (folder / ".harness" / "checkpoint.jsonl").touch()

    # Project membership + first heartbeat
    from . import project
    project.add_member(folder.name, ident["agent_id"], role)
    heartbeat.beat(ident["agent_id"], via="spawn")

    eventlog.log("human@dashboard", "spawned",
                 new_agent_id=ident["agent_id"], role=role, folder=str(folder))
    return {"ok": True, "agent_id": ident["agent_id"],
            "folder": str(folder), "role": role}


def bulk(action: str, agent_ids: list[str]) -> dict:
    """Fan-out a pause/resume/kill across multiple agents."""
    if action not in ("pause", "resume", "kill"):
        return {"ok": False, "error": f"unknown action {action}"}
    handler = {"pause": pause, "resume": resume, "kill": kill}[action]
    results = [handler(aid) for aid in agent_ids]
    return {"ok": True, "action": action, "results": results}
