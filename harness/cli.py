"""`harness` CLI — the single entrypoint a developer uses.

Commands:
  harness join <fleet-id>                     — first-time machine setup
  harness init --role <role> --name <slug>    — scaffold a new agent in cwd
  harness status                              — show fleet status
  harness send <to> <subject> <body>          — send a test message
  harness inbox                               — show this agent's inbox
  harness roles list                          — available role templates
  harness arsenal add/search/get              — manage shared knowledge
  harness proposals list/approve/reject       — human decision queue
  harness dashboard                           — launch the dashboard
  harness digest                              — manually run digest (test onCompact)
  harness wakeup                              — emit wake-up pack to stdout
  harness heartbeat                           — beat (useful for scripts)
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import click
import yaml

from . import (
    config, identity, registry, checkpoint, eventlog,
    arsenal, mailbox, heartbeat, notify, project,
    proposals, wakeup, digest,
)
from ._util import slugify

REPO_ROOT = Path(__file__).resolve().parent.parent  # the-cc-harness repo root


@click.group()
def cli():
    """Claude Harness — fleet layer on top of Claude Code."""
    pass


@cli.command()
@click.argument("fleet_id", required=False)
def join(fleet_id):
    """First-time setup on this machine. Creates ~/.harness/ scaffold.

    (Syncthing pairing step is manual for now — print instructions.)
    """
    root = config.ensure_root()
    click.echo(f"✓ ~/.harness/ ready at {root}")
    cfg = config.load_config()
    click.echo(f"  machine_id: {cfg.get('machine_id')}")

    sync = shutil.which("syncthing")
    if sync:
        click.echo("\nSyncthing is installed. To share ~/.harness/ across your fleet:")
        click.echo("  1. Run:  syncthing  (keep it running; it ships a web UI on localhost:8384)")
        click.echo(f"  2. In the UI: add folder with path {root}")
        click.echo("  3. Share it with your other machines (exchange device IDs)")
    else:
        click.echo("\n[!] Syncthing not found. Install with:  brew install syncthing")

    if fleet_id:
        cfg["fleet_id"] = fleet_id
        config.save_config(cfg)
        click.echo(f"  fleet_id: {fleet_id}")


@cli.command()
@click.option("--role", required=True, help="Role template slug (see `harness roles list`).")
@click.option("--name", required=True, help="Short slug (e.g. kevin, seo1).")
@click.option("--project", "project_name", default=None,
              help="Project slug this agent belongs to. Defaults to folder name.")
def init(role, name, project_name):
    """Scaffold a new agent in the current folder."""
    folder = Path.cwd()

    # Resolve role template
    role_file = REPO_ROOT / "roles" / f"{role}.md"
    if not role_file.exists():
        click.echo(f"✗ Role template not found: {role_file}", err=True)
        click.echo("  Run `harness roles list` to see available roles.", err=True)
        sys.exit(1)

    # Create identity
    slug = slugify(name)
    ident = identity.create_identity(folder, role=role, slug=slug)
    registry.register(ident)

    # Assemble CLAUDE.md: role template + hint pointer
    base_pre = (REPO_ROOT / "roles" / "_base-preamble.md").read_text()
    role_body = role_file.read_text()
    # Strip frontmatter from role template
    if role_body.startswith("---"):
        parts = role_body.split("---", 2)
        if len(parts) >= 3:
            role_body = parts[2].lstrip()
    claude_md = (
        f"# Agent: {ident['agent_id']}\n"
        f"# Role: {role}\n\n"
        + base_pre
        + "\n\n"
        + role_body
    )
    (folder / "CLAUDE.md").write_text(claude_md)

    # Install harness skill into .claude/skills/
    skill_src = REPO_ROOT / "skill" / "harness"
    skill_dst = folder / ".claude" / "skills" / "harness"
    if skill_src.exists():
        if skill_dst.exists():
            shutil.rmtree(skill_dst)
        shutil.copytree(skill_src, skill_dst)

    # Install harness-conventions (detailed guidance, on-demand)
    conv_src = REPO_ROOT / "skill" / "harness-conventions"
    conv_dst = folder / ".claude" / "skills" / "harness-conventions"
    if conv_src.exists():
        if conv_dst.exists():
            shutil.rmtree(conv_dst)
        shutil.copytree(conv_src, conv_dst)

    # Install role-specific skill (if exists)
    role_skill_src = REPO_ROOT / "skill" / f"role-{role}"
    role_skill_dst = folder / ".claude" / "skills" / f"role-{role}"
    if role_skill_src.exists():
        if role_skill_dst.exists():
            shutil.rmtree(role_skill_dst)
        shutil.copytree(role_skill_src, role_skill_dst)

    # Write settings.local.json (hooks + permission allowances for ~/.harness/)
    settings_dir = folder / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / "settings.local.json"
    hook_root = REPO_ROOT / "hooks"
    settings = {
        "hooks": {
            "onCompact": f"bash {hook_root / 'on_compact.sh'} {folder}",
            "onSessionStart": f"bash {hook_root / 'session_start.sh'} {folder}",
        },
        "permissions": {
            "allow": [
                f"Bash(python -m harness.*:*)",
                f"Read({config.HARNESS_ROOT}/**)",
                f"Write({config.HARNESS_ROOT}/**)",
                f"Edit({config.HARNESS_ROOT}/**)",
            ],
        },
    }
    if settings_path.exists():
        # Merge rather than overwrite
        try:
            existing = json.loads(settings_path.read_text())
            existing.setdefault("hooks", {}).update(settings["hooks"])
            existing.setdefault("permissions", {}).setdefault("allow", [])
            for rule in settings["permissions"]["allow"]:
                if rule not in existing["permissions"]["allow"]:
                    existing["permissions"]["allow"].append(rule)
            settings = existing
        except Exception:
            pass  # overwrite if corrupt
    settings_path.write_text(json.dumps(settings, indent=2))

    # Empty checkpoint
    (folder / ".harness" / "checkpoint.jsonl").touch()

    # Project membership
    proj = project_name or folder.name
    project.add_member(proj, ident["agent_id"], role)

    # First heartbeat
    heartbeat.beat(ident["agent_id"], kind="init")

    click.echo(f"✓ Agent {ident['agent_id']} initialized.")
    click.echo(f"  Role:     {role}")
    click.echo(f"  Project:  {proj}")
    click.echo(f"  Folder:   {folder}")
    click.echo(f"\nNext: run `claude` to start.")


@cli.command()
def status():
    """Show fleet status."""
    config.ensure_root()
    agents = registry.live_agents()
    if not agents:
        click.echo("No agents registered.")
        return
    click.echo(f"Fleet: {len(agents)} agent(s)")
    click.echo("-" * 70)
    for ag in agents:
        aid = ag["agent_id"]
        last = heartbeat.last_beat(aid) or "never"
        status_mark = "✓" if not heartbeat.stale(aid) else "!"
        click.echo(f"  {status_mark} {aid:40s} role={ag.get('role', '?'):15s} last_beat={last}")
    # zombies
    zombies = heartbeat.sweep()
    if zombies:
        click.echo(f"\n[!] Zombie agents (stale beats): {len(zombies)}")
        for z in zombies:
            click.echo(f"    ✗ {z['agent_id']}")


@cli.command()
@click.argument("to")
@click.argument("subject")
@click.argument("body")
@click.option("--from", "from_id", default="human@dashboard",
              help="Sender id; defaults to human@dashboard.")
def send(to, subject, body, from_id):
    """Send a message. (Testing tool — normally agents do this via skill.)"""
    env = mailbox.send(from_id, to, subject, body)
    click.echo(f"✓ sent {env['msg_id']} to {to}")


@cli.command()
@click.option("--agent", default=None, help="Agent id; defaults to agent in cwd.")
@click.option("--limit", default=20)
def inbox(agent, limit):
    """Peek at an agent's inbox without consuming."""
    if not agent:
        ident = identity.load_identity(Path.cwd())
        if not ident:
            click.echo("No agent in cwd. Use --agent to specify.", err=True)
            sys.exit(1)
        agent = ident["agent_id"]
    msgs = mailbox.peek(agent, limit=limit)
    if not msgs:
        click.echo("(empty)")
        return
    for m in msgs:
        click.echo(f"- {m['msg_id']}  from {m['from']}  {m['subject']}")


@cli.group()
def roles():
    """Role templates."""


@roles.command(name="list")
def roles_list():
    d = REPO_ROOT / "roles"
    if not d.exists():
        click.echo("(no roles dir)")
        return
    for f in sorted(d.glob("*.md")):
        if f.name.startswith("_"):
            continue
        # try to extract description from frontmatter
        body = f.read_text()
        desc = ""
        if body.startswith("---"):
            parts = body.split("---", 2)
            try:
                fm = yaml.safe_load(parts[1])
                desc = fm.get("description", "") if fm else ""
            except Exception:
                pass
        click.echo(f"  {f.stem:25s} {desc}")


@cli.group(name="arsenal")
def arsenal_cmd():
    """Shared knowledge base."""


@arsenal_cmd.command(name="add")
@click.option("--slug", default=None)
@click.option("--title", required=True)
@click.option("--content", required=True, help="Content text (or @path to read file).")
@click.option("--tags", default="", help="Comma-separated.")
@click.option("--source-url", "source_url", default=None)
@click.option("--by", default=None)
def arsenal_add(slug, title, content, tags, source_url, by):
    if content.startswith("@"):
        content = Path(content[1:]).read_text()
    ident = identity.load_identity(Path.cwd())
    by = by or (ident["agent_id"] if ident else "human@cli")
    source_type = "web" if source_url else "human_input"
    source_refs = [source_url] if source_url else []
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    meta = arsenal.add(slug, title, content, tag_list, source_type, source_refs, by)
    click.echo(f"✓ added {meta['slug']} (trust={meta['trust']})")


@arsenal_cmd.command(name="search")
@click.argument("query")
@click.option("--limit", default=10)
@click.option("--all", "include_unverified", is_flag=True)
def arsenal_search(query, limit, include_unverified):
    results = arsenal.search(query, limit=limit, include_unverified=include_unverified)
    if not results:
        click.echo("(no matches)")
        return
    for r in results:
        click.echo(f"  [{r['trust']:16s}] {r['slug']:30s} — {r['title']}")


@arsenal_cmd.command(name="get")
@click.argument("slug")
def arsenal_get(slug):
    item = arsenal.get(slug)
    if not item:
        click.echo("(not found)", err=True)
        sys.exit(1)
    click.echo(f"# {item['title']}")
    click.echo(f"_trust: {item['trust']} · produced_by: {item['produced_by']}_\n")
    click.echo(item["content"])


@cli.group(name="proposals")
def proposals_cmd():
    """Self-evolution proposals queue."""


@proposals_cmd.command(name="list")
@click.option("--kind", default=None)
@click.option("--status", default=None)
def proposals_list(kind, status):
    recs = proposals.list_all(kind=kind, status=status)
    if not recs:
        click.echo("(no proposals)")
        return
    for r in recs:
        click.echo(f"  {r['kind']:10s} {r['id']}  [{r['status']}]  by {r['proposer']}")


@proposals_cmd.command(name="approve")
@click.argument("kind")
@click.argument("pid")
def proposals_approve(kind, pid):
    rec = proposals.human_approve(kind, pid)
    click.echo(f"✓ approved + promoted: {rec['id']}")


@proposals_cmd.command(name="reject")
@click.argument("kind")
@click.argument("pid")
def proposals_reject(kind, pid):
    rec = proposals.human_reject(kind, pid)
    click.echo(f"✗ rejected: {rec['id']}")


@cli.command()
def dashboard():
    """Launch the dashboard (FastAPI + static frontend) on http://localhost:9999"""
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        click.echo("uvicorn not installed. Run: pip install 'claude-harness[dashboard]' "
                   "or just: pip install uvicorn fastapi watchfiles", err=True)
        sys.exit(1)
    # Run as module so imports resolve
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "dashboard.backend.main:app",
         "--host", "127.0.0.1", "--port", "9999", "--reload"],
        cwd=REPO_ROOT, env=env,
    )


@cli.command(name="digest")
def digest_cmd():
    """Manually run digest for current folder (tests onCompact path)."""
    path = digest.write_digest(Path.cwd())
    if path:
        click.echo(f"✓ digest: {path}")
    else:
        click.echo("(no agent in cwd)", err=True)
        sys.exit(1)


@cli.command(name="wakeup")
def wakeup_cmd():
    """Emit the wake-up pack to stdout. (Used by session_start hook.)"""
    text = wakeup.build(Path.cwd())
    sys.stdout.write(text)


@cli.command(name="heartbeat")
@click.option("--agent", default=None)
def heartbeat_cmd(agent):
    if not agent:
        ident = identity.load_identity(Path.cwd())
        if not ident:
            click.echo("No agent in cwd.", err=True)
            sys.exit(1)
        agent = ident["agent_id"]
    heartbeat.beat(agent)
    click.echo(f"✓ beat {agent}")


if __name__ == "__main__":
    cli()
