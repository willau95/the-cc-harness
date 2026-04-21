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
    proposals, wakeup, digest, equipment,
)
from ._util import slugify

REPO_ROOT = Path(__file__).resolve().parent.parent  # the-cc-harness repo root


def _rewrite_tool_scripts(skill_dirs: list) -> None:
    """Make copied skill tool .py files executable + shebang them at sys.executable.

    Why: skill tools do `from harness import ...` but the system python3 doesn't
    have our package (it's isolated in a pipx/uv venv). sys.executable (the
    Python running `harness` right now) does have it. So we point each tool's
    shebang at that interpreter at copy-time.

    Also strips obsolete `sys.path.insert(0, ...parents[N]...)` lines from tool
    scripts — they made wrong assumptions about layout and fail silently when
    the package isn't where they guessed.
    """
    import re
    python_exe = sys.executable
    pattern = re.compile(r'^sys\.path\.insert\(\s*0\s*,\s*str\(Path\(__file__\)\.resolve\(\)\.parents\[\d+\]\)\s*\)\s*\n',
                         re.MULTILINE)
    for d in skill_dirs:
        if not d or not d.exists():
            continue
        for py in d.rglob("*.py"):
            try:
                text = py.read_text()
            except Exception:
                continue
            lines = text.splitlines(keepends=True)
            if lines and lines[0].startswith("#!"):
                lines[0] = f"#!{python_exe}\n"
                text = "".join(lines)
            # Remove the obsolete sys.path.insert line
            text = pattern.sub("", text)
            py.write_text(text)
            try:
                py.chmod(0o755)
            except Exception:
                pass


__version__ = "0.2.0"


@click.group()
@click.version_option(__version__, "-V", "--version", prog_name="harness",
                      message="%(prog)s %(version)s")
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
@click.option("--equip", "equip_csv", default=None,
              help="Comma-separated equipment slugs to pre-install (e.g. --equip twitter-client,prediction-market-ref).")
def init(role, name, project_name, equip_csv):
    """Scaffold a new agent in the current folder."""
    folder = Path.cwd()

    # Resolve role template
    role_file = REPO_ROOT / "roles" / f"{role}.md"
    if not role_file.exists():
        click.echo(f"✗ Role template not found: {role_file}", err=True)
        click.echo("  Run `harness roles list` to see available roles.", err=True)
        sys.exit(1)

    # Identity: idempotent — if this folder already has an agent with same slug,
    # keep the existing agent_id. Only generate a fresh one if slug/role differ.
    slug = slugify(name)
    existing = identity.load_identity(folder)
    if existing and existing.get("slug") == slug:
        ident = dict(existing)
        ident["role"] = role  # allow role upgrade
        identity.write_identity(folder, ident)
        click.echo(f"  (reusing existing agent_id {ident['agent_id']})")
    else:
        ident = identity.create_identity(folder, role=role, slug=slug)
    registry.register(ident)

    # Assemble the harness section of CLAUDE.md. If the folder already has
    # its own CLAUDE.md (adopted existing project), we APPEND our section below
    # the user's content, wrapped in markers so future upgrades can find &
    # replace just our block without touching anything the user wrote.
    base_pre = (REPO_ROOT / "roles" / "_base-preamble.md").read_text()
    role_body = role_file.read_text()
    if role_body.startswith("---"):
        parts = role_body.split("---", 2)
        if len(parts) >= 3:
            role_body = parts[2].lstrip()

    HARNESS_BEGIN = "<!-- BEGIN harness agent preamble — auto-generated -->"
    HARNESS_END = "<!-- END harness agent preamble -->"
    harness_block = (
        f"{HARNESS_BEGIN}\n"
        f"# Agent: {ident['agent_id']}\n"
        f"# Role: {role}\n\n"
        + base_pre
        + "\n\n"
        + role_body
        + f"\n{HARNESS_END}\n"
    )

    claude_md_path = folder / "CLAUDE.md"
    if claude_md_path.exists():
        existing = claude_md_path.read_text()
        import re as _re
        # Replace our previous block if present, else append
        pattern = _re.compile(
            _re.escape(HARNESS_BEGIN) + r".*?" + _re.escape(HARNESS_END) + r"\n?",
            _re.DOTALL,
        )
        if pattern.search(existing):
            new_content = pattern.sub(harness_block, existing)
            click.echo("  (updated harness block in existing CLAUDE.md; your content preserved)")
        else:
            sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
            new_content = existing + sep + harness_block
            click.echo("  (appended harness block to existing CLAUDE.md; your content preserved)")
        claude_md_path.write_text(new_content)
    else:
        claude_md_path.write_text(harness_block)

    # Figure out which of our two default skills the caller is overriding via
    # --equip. If they pre-equip `harness` / `harness-core` (same SKILL.md name)
    # or `harness-conventions`, skip our default install to avoid two skill dirs
    # declaring `name: harness` — Claude Code discovers by frontmatter name and
    # duplicates cause one to be ignored unpredictably.
    equip_slugs = {s.strip() for s in (equip_csv or "").split(",") if s.strip()}
    skip_harness_default = bool(equip_slugs & {"harness", "harness-core"})
    skip_conventions_default = "harness-conventions" in equip_slugs
    if skip_harness_default:
        click.echo("  (skipping default `harness` skill install — overridden by --equip)")
    if skip_conventions_default:
        click.echo("  (skipping default `harness-conventions` skill install — overridden by --equip)")

    # Install harness skill into .claude/skills/
    skill_src = REPO_ROOT / "skill" / "harness"
    skill_dst = folder / ".claude" / "skills" / "harness"
    if not skip_harness_default and skill_src.exists():
        if skill_dst.exists():
            shutil.rmtree(skill_dst)
        shutil.copytree(skill_src, skill_dst)

    # Install harness-conventions (detailed guidance, on-demand)
    conv_src = REPO_ROOT / "skill" / "harness-conventions"
    conv_dst = folder / ".claude" / "skills" / "harness-conventions"
    if not skip_conventions_default and conv_src.exists():
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

    # Fix tool scripts: point shebang at THIS Python (the one running harness),
    # which has the harness package importable. Strip obsolete sys.path.insert
    # lines that assumed a specific source-tree layout. Make scripts executable.
    # This is the right moment because sys.executable right now = the interpreter
    # that actually has `harness` on its path.
    _rewrite_tool_scripts([skill_dst, conv_dst, role_skill_dst])

    # Install project-scoped slash commands (/inbox, ...) — Claude Code reads
    # from .claude/commands/<name>.md. These let the user type /<cmd> in the
    # claude terminal instead of "please check your inbox".
    cmds_src = REPO_ROOT / "slash-commands"
    cmds_dst = folder / ".claude" / "commands"
    if cmds_src.exists():
        cmds_dst.mkdir(parents=True, exist_ok=True)
        for f in cmds_src.glob("*.md"):
            (cmds_dst / f.name).write_text(f.read_text())

    # Write settings.local.json — Claude Code's matchers schema
    # Events: SessionStart + PreCompact (PascalCase, no 'on' prefix).
    # Structure: event → array of matcher entries → each with hooks array of {type, command}
    settings_dir = folder / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_path = settings_dir / "settings.local.json"
    hook_root = REPO_ROOT / "hooks"

    # Properly shell-quote paths. Without this, any folder with spaces (very
    # common: `Desktop/testing flow`) breaks hook invocation because bash
    # treats the space as argument separator and the hook receives a truncated
    # path → cd fails → no heartbeat → agent shows stale forever.
    def _sh_quote(p) -> str:
        s = str(p)
        return "'" + s.replace("'", "'\\''") + "'"

    folder_q = _sh_quote(folder)

    our_hooks = {
        "SessionStart": [{
            "matcher": "",
            "hooks": [{
                "type": "command",
                "command": f"bash {_sh_quote(hook_root / 'session_start.sh')} {folder_q}",
            }],
        }],
        "PreCompact": [{
            "matcher": "",
            "hooks": [{
                "type": "command",
                "command": f"bash {_sh_quote(hook_root / 'on_compact.sh')} {folder_q}",
            }],
        }],
        "PreToolUse": [{
            "matcher": "",
            "hooks": [{
                "type": "command",
                "command": f"bash {_sh_quote(hook_root / 'pre_tool_use.sh')} {folder_q}",
            }],
        }],
        "PostToolUse": [{
            "matcher": "",
            "hooks": [{
                "type": "command",
                "command": f"bash {_sh_quote(hook_root / 'post_tool_use.sh')} {folder_q}",
            }],
        }],
    }
    our_allows = [
        "Bash(python -m harness.*:*)",
        "Bash(harness *:*)",
        f"Read({config.HARNESS_ROOT}/**)",
        f"Write({config.HARNESS_ROOT}/**)",
        f"Edit({config.HARNESS_ROOT}/**)",
    ]

    settings: dict = {"hooks": our_hooks,
                      "permissions": {"allow": our_allows}}

    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
            # Merge hooks: our event → replace (avoid stale schema), other events preserved
            existing_hooks = existing.get("hooks") or {}
            # If existing uses obsolete onFoo keys, drop them — they're invalid under current schema
            for obsolete in ("onCompact", "onSessionStart"):
                existing_hooks.pop(obsolete, None)
            for event, entries in our_hooks.items():
                existing_hooks[event] = entries
            existing["hooks"] = existing_hooks
            # Merge permissions.allow (union)
            perms = existing.setdefault("permissions", {})
            allow = perms.setdefault("allow", [])
            for rule in our_allows:
                if rule not in allow:
                    allow.append(rule)
            settings = existing
        except Exception:
            pass  # corrupt → overwrite with fresh
    settings_path.write_text(json.dumps(settings, indent=2))

    # Empty checkpoint
    (folder / ".harness" / "checkpoint.jsonl").touch()

    # Project membership
    proj = project_name or folder.name
    project.add_member(proj, ident["agent_id"], role)

    # First heartbeat
    # Deliberately NOT heartbeating here. `harness init` is scaffold-time,
    # not runtime — claude hasn't started yet. If we beat here, a freshly
    # spawned agent looks "online" (green) in the fleet view even though no
    # claude process exists. Better UX: show "pending" until SessionStart
    # fires its own heartbeat.

    # Pre-equip: install selected equipment items into Claude Code's native
    # slots (skills/, commands/, agents/, settings mcpServers, CLAUDE.md).
    equipped: list[dict] = []
    if equip_csv:
        for slug in [s.strip() for s in equip_csv.split(",") if s.strip()]:
            try:
                r = equipment.equip(slug, folder)
                equipped.append(r)
            except Exception as e:
                click.echo(f"  [warn] failed to equip {slug}: {e}", err=True)

    click.echo(f"✓ Agent {ident['agent_id']} initialized.")
    click.echo(f"  Role:     {role}")
    click.echo(f"  Project:  {proj}")
    click.echo(f"  Folder:   {folder}")
    if equipped:
        click.echo(f"  Equipped: {len(equipped)} item(s)")
        for e in equipped:
            if e.get("ok"):
                click.echo(f"    ✓ {e['slug']} ({e['kind']}) → {e['installed_to'][0]}")

    # Warn about ANTHROPIC_BASE_URL — a common proxy leftover that causes
    # claude to ConnectionRefused against a dead local port.
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
    if base_url:
        click.echo(
            f"\n[!] ANTHROPIC_BASE_URL={base_url} is set — claude will route through "
            "that local proxy, not Anthropic directly."
        )
        click.echo(
            "    If you don't intend to use a proxy, unset it + remove from ~/.zshrc:"
        )
        click.echo("      unset ANTHROPIC_BASE_URL")
        click.echo("      sed -i.bak '/ANTHROPIC_BASE_URL/d' ~/.zshrc")

    # Warn if claude login hasn't been completed — no credentials.json means
    # every `claude` invocation will fail with 'Invalid API key'.
    cred_path = Path.home() / ".claude" / "credentials.json"
    if not cred_path.exists():
        click.echo(
            "\n[!] claude is not logged in on this Mac (~/.claude/credentials.json missing).\n"
            "    Every agent you spawn will fail with 'Invalid API key' until you run:\n"
            "      claude login\n"
            "    Complete the browser OAuth with your Claude subscription account."
        )

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


@cli.command()
@click.option("--agent", default=None, help="Agent id; defaults to agent in cwd.")
@click.option("--limit", default=20)
def receive(agent, limit):
    """Read new messages from the inbox and mark them consumed. Emits JSON
    so the /inbox slash command can hand the result directly to claude."""
    if not agent:
        ident = identity.load_identity(Path.cwd())
        if not ident:
            click.echo(json.dumps({"ok": False, "error": "no agent in cwd"}))
            sys.exit(1)
        agent = ident["agent_id"]
    msgs = mailbox.receive(agent, limit=limit, wrap_untrusted=True)
    click.echo(json.dumps({
        "ok": True,
        "count": len(msgs),
        "messages": [{
            "msg_id": m.get("msg_id"),
            "from": m.get("from"),
            "subject": m.get("subject"),
            "body": m.get("body_wrapped") or m.get("body"),
            "created_at": m.get("created_at"),
        } for m in msgs],
    }, ensure_ascii=False))


@cli.group(name="equipment")
def equipment_cmd():
    """武器库 — shared library of Claude Code skills/commands/subagents/repos."""


@equipment_cmd.command(name="add")
@click.option("--slug", default=None, help="Short identifier. Auto-derived from source if omitted.")
@click.option("--kind", required=True,
              type=click.Choice(sorted(equipment.VALID_KINDS)),
              help="skill | command | subagent | mcp | hook | repo | preamble")
@click.option("--source", required=True,
              help="Local path (dir or file) or git URL to import.")
@click.option("--name", default=None, help="Display name (auto-derived if omitted).")
@click.option("--description", default=None, help="When-to-use description.")
@click.option("--topics", default="", help="Comma-separated topic tags.")
@click.option("--source-url", "source_url", default=None,
              help="Canonical URL if source is a local clone.")
@click.option("--trust", default="experimental",
              type=click.Choice(sorted(equipment.VALID_TRUST)))
def equipment_add(slug, kind, source, name, description, topics, source_url, trust):
    """Import a skill/command/etc into the equipment library."""
    topics_list = [t.strip() for t in topics.split(",") if t.strip()]
    meta = equipment.add(
        slug=slug, kind=kind, source=source,
        name=name, description=description, topics=topics_list,
        source_url=source_url, trust=trust,
    )
    click.echo(f"✓ added equipment `{meta['slug']}` ({meta['kind']})")
    click.echo(f"  name: {meta['name']}")
    if meta.get("description"):
        click.echo(f"  desc: {meta['description'][:120]}")
    click.echo(f"  path: {equipment.item_dir(meta['slug'])}")


@equipment_cmd.command(name="list")
@click.option("--kind", default=None, help="Filter by kind.")
def equipment_list(kind):
    """List all items in the equipment library."""
    items = equipment.list_all(kind=kind)
    if not items:
        click.echo("(empty)")
        return
    for m in items:
        topics = " · " + " ".join(m["topics"]) if m["topics"] else ""
        click.echo(f"  {m['slug']:30s} [{m['kind']:10s}] {m['name']}{topics}")


@equipment_cmd.command(name="get")
@click.argument("slug")
def equipment_get(slug):
    """Show full metadata + analysis.md for one item."""
    m = equipment.get(slug)
    if not m:
        click.echo(f"(not found: {slug})", err=True)
        sys.exit(1)
    click.echo(f"# {m['name']}  ({m['kind']} · trust={m.get('trust')})")
    click.echo(f"slug: {m['slug']}")
    if m.get("source_url"):
        click.echo(f"source_url: {m['source_url']}")
    if m.get("topics"):
        click.echo(f"topics: {', '.join(m['topics'])}")
    click.echo()
    if m.get("description"):
        click.echo(m["description"])
        click.echo()
    if m.get("analysis"):
        click.echo("--- analysis.md ---")
        click.echo(m["analysis"])


@equipment_cmd.command(name="search")
@click.argument("query")
def equipment_search(query):
    """Full-text search across name + description + topics."""
    items = equipment.search(query)
    if not items:
        click.echo("(no matches)")
        return
    for m in items:
        click.echo(f"  {m['slug']:30s} [{m['kind']}] {m['name']}")


@equipment_cmd.command(name="equip")
@click.argument("slugs", nargs=-1, required=True)
@click.option("--folder", default=None,
              help="Target agent folder. Defaults to cwd.")
def equipment_equip(slugs, folder):
    """Install one or more equipment items into an agent folder."""
    target = Path(folder).expanduser().resolve() if folder else Path.cwd()
    if not (target / ".harness" / "agent.yaml").exists():
        click.echo(f"✗ {target} is not a harness agent folder (no .harness/agent.yaml)", err=True)
        sys.exit(1)
    results = equipment.equip_many(list(slugs), target)
    for r in results:
        if r.get("ok"):
            click.echo(f"  ✓ {r['slug']} ({r['kind']}) → {r['installed_to'][0]}")
        else:
            click.echo(f"  ✗ {r['slug']}: {r.get('error')}", err=True)


@equipment_cmd.command(name="reindex")
@click.argument("slug")
def equipment_reindex(slug):
    """Re-populate sqlite from an existing items/<slug>/ dir (no file touching).
    Used by cross-machine rsync — files already rsynced, only need sqlite update."""
    import json as _json
    try:
        r = equipment.reindex(slug)
        click.echo(_json.dumps({"ok": True, "slug": slug}))
    except Exception as e:
        click.echo(_json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)


@equipment_cmd.command(name="set-trust")
@click.argument("slug")
@click.argument("new_trust",
                type=click.Choice(sorted(equipment.VALID_TRUST)))
@click.option("--by", default="human@cli")
def equipment_set_trust(slug, new_trust, by):
    """Update trust tier. Used by dashboard for cross-machine trust routing."""
    import json as _json
    try:
        r = equipment.set_trust(slug, new_trust, by=by)
        click.echo(_json.dumps(r))
    except ValueError as e:
        click.echo(_json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)


@cli.group(name="events")
def events_cmd():
    """Event log inspection."""


@events_cmd.command(name="dump-json")
@click.option("--limit", default=500, help="Max events to emit (most recent first).")
@click.option("--days", default=1, help="How many days back to scan (including today).")
def events_dump_json(limit, days):
    """Emit today's events across every local agent as a JSON array.
    Used by the dashboard to fold a peer's events into the aggregated view."""
    from harness._util import today_str
    import datetime as _dt
    events_root = config.HARNESS_ROOT / "events"
    if not events_root.exists():
        click.echo("[]")
        return
    today = _dt.date.today()
    out = []
    for agent_dir in events_root.iterdir():
        if not agent_dir.is_dir():
            continue
        for i in range(max(1, days)):
            d = (today - _dt.timedelta(days=i)).isoformat()
            f = agent_dir / f"{d}.jsonl"
            if not f.exists():
                continue
            for line in f.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec["agent"] = agent_dir.name
                out.append(rec)
    out.sort(key=lambda e: e.get("ts", ""), reverse=True)
    click.echo(json.dumps(out[:limit], default=str, ensure_ascii=False))


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


@arsenal_cmd.command(name="dump-json")
@click.option("--limit", default=200)
def arsenal_dump_json(limit):
    """Dump full arsenal as a JSON array on stdout. Used by remote aggregation."""
    import sqlite3
    conn = sqlite3.connect(config.arsenal_db_path())
    try:
        rows = conn.execute(
            "SELECT slug, title, trust, produced_by, produced_at, source_refs, tags, chain_depth "
            "FROM items ORDER BY produced_at DESC LIMIT ?", (limit,),
        ).fetchall()
    finally:
        conn.close()
    out = [{
        "slug": r[0], "title": r[1], "trust": r[2], "produced_by": r[3],
        "produced_at": r[4], "source_refs": r[5], "tags": r[6], "chain_depth": r[7],
    } for r in rows]
    click.echo(json.dumps(out, ensure_ascii=False))


@arsenal_cmd.command(name="set-trust")
@click.argument("slug")
@click.argument("new_trust")
@click.option("--by", default="human@dashboard", help="Who's changing the trust")
def arsenal_set_trust(slug, new_trust, by):
    """Update the trust tier of an arsenal item. Used by dashboard
    for cross-machine trust routing (owning peer runs this via fleet-ssh)."""
    from harness import arsenal as arsenal_mod
    # Verify item exists locally before updating
    if not arsenal_mod.get(slug):
        click.echo(json.dumps({"error": "not_found", "slug": slug}))
        sys.exit(1)
    arsenal_mod.set_trust(slug, new_trust, by=by)
    click.echo(json.dumps({"ok": True, "slug": slug, "trust": new_trust}))


@arsenal_cmd.command(name="get")
@click.argument("slug")
@click.option("--json", "as_json", is_flag=True, help="Emit full item as JSON (used by dashboard for cross-machine fetch)")
def arsenal_get(slug, as_json):
    item = arsenal.get(slug)
    if not item:
        if as_json:
            click.echo(json.dumps({"error": "not_found", "slug": slug}))
            sys.exit(1)
        click.echo("(not found)", err=True)
        sys.exit(1)
    if as_json:
        click.echo(json.dumps(item, default=str))
        return
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


# ═══════════════════════════════════════════════════════════════════════════
# Agent-facing subcommands — what SKILL.md used to dispatch via Python scripts
# is now routed through the `harness` CLI binary. Benefits:
#   · no shebang / venv concern (harness is on PATH via pipx)
#   · no path-to-skill-folder hardcoding (was brittle when slug varied)
#   · one canonical surface area; skills just say `harness checkpoint update ...`
# The old Python scripts under skill/harness/tools/ still exist as a fallback
# for any external skill that depends on them, but we don't steer agents there.
# ═══════════════════════════════════════════════════════════════════════════

def _json_emit(obj):
    click.echo(json.dumps(obj, ensure_ascii=False, default=str))


def _load_cwd_agent():
    """Resolve the agent identity in cwd; emit error + exit(1) if missing."""
    ident = identity.load_identity(Path.cwd())
    if not ident:
        _json_emit({"ok": False, "error": "no agent in cwd — run `harness init` first"})
        sys.exit(1)
    return ident


@cli.group(name="checkpoint")
def checkpoint_cmd():
    """Task FSM: create / update / read agent's per-task checkpoint."""


@checkpoint_cmd.command(name="update")
@click.option("--task-id", default=None)
@click.option("--create", is_flag=True)
@click.option("--original-goal", default=None)
@click.option("--deliverable-spec", default="")
@click.option("--budget", type=int, default=None)
@click.option("--state", default=None,
              help="PROPOSED | IN_PROGRESS | BLOCKED | AWAITING_REVIEW | VERIFIED | DONE | ABANDONED")
@click.option("--blocked-on", default=None)
@click.option("--deliverable-ref", default=None)
@click.option("--next-step", default=None)
def checkpoint_update(task_id, create, original_goal, deliverable_spec, budget,
                      state, blocked_on, deliverable_ref, next_step):
    """Append a checkpoint entry (create a new task, or update an existing one)."""
    ident = _load_cwd_agent()
    folder = Path.cwd()
    try:
        if create:
            if not original_goal:
                _json_emit({"ok": False, "error": "--original-goal required with --create"})
                sys.exit(1)
            task_id_new = checkpoint.create_task(folder,
                                                 original_goal=original_goal,
                                                 deliverable_spec=deliverable_spec,
                                                 budget=budget)
            _json_emit({"ok": True, "task_id": task_id_new})
        else:
            if not task_id:
                _json_emit({"ok": False, "error": "--task-id required (unless --create)"})
                sys.exit(1)
            updates = {}
            if state: updates["state"] = state
            if blocked_on: updates["blocked_on"] = blocked_on
            if deliverable_ref: updates["deliverable_ref"] = deliverable_ref
            if next_step: updates["next_step"] = next_step
            t = checkpoint.update(folder, task_id, **updates)
            _json_emit({"ok": True, "task_id": task_id, "task": t})
    except Exception as e:
        _json_emit({"ok": False, "error": str(e)})
        sys.exit(1)


@checkpoint_cmd.command(name="read")
@click.option("--task-id", default=None,
              help="If set, show only this task. Else all active tasks.")
def checkpoint_read(task_id):
    """Read active tasks (FSM state, next_step, blocked_on, budget…)."""
    _load_cwd_agent()
    folder = Path.cwd()
    if task_id:
        t = checkpoint.latest_for_task(folder, task_id)
        _json_emit({"ok": True, "task": t})
    else:
        tasks = checkpoint.active_tasks(folder)
        _json_emit({"ok": True, "active_count": len(tasks), "tasks": tasks})


@cli.group(name="project-state")
def project_state_cmd():
    """Project-shared key-value state (across all agents on a project)."""


@project_state_cmd.command(name="update")
@click.option("--project", "project_slug", default=None)
@click.option("--key", required=True)
@click.option("--value", required=True,
              help="Value string. If starts with '[' or '{' parsed as JSON.")
def project_state_update(project_slug, key, value):
    ident = _load_cwd_agent()
    proj = project_slug or Path(ident["folder"]).name
    try:
        if value.startswith(("[", "{")):
            value = json.loads(value)
    except json.JSONDecodeError:
        pass
    project.update_state(proj, key, value, by=ident["agent_id"])
    _json_emit({"ok": True, "project": proj, "key": key, "value": value})


@project_state_cmd.command(name="read")
@click.option("--project", "project_slug", default=None)
def project_state_read(project_slug):
    ident = identity.load_identity(Path.cwd())
    proj = project_slug or (Path.cwd().name if not ident else Path(ident["folder"]).name)
    state = project.read_state(proj)
    members = project.active_members(proj)
    _json_emit({"ok": True, "project": proj,
                "state": state["values"], "state_meta": state["meta"],
                "members": members})


@cli.group(name="propose")
def propose_cmd():
    """Self-evolution: propose a new skill / role-lesson / budget extension."""


@propose_cmd.command(name="skill")
@click.option("--slug", required=True)
@click.option("--rationale", required=True,
              help="Why this skill? e.g. 'I've done X 3x this week'")
@click.option("--content", required=True,
              help="Skill body (SKILL.md content) or @path to read from a file")
@click.option("--tags", default="")
def propose_skill(slug, rationale, content, tags):
    ident = _load_cwd_agent()
    if content.startswith("@"):
        content = Path(content[1:]).read_text()
    rec = proposals.create("skill", ident["agent_id"], {
        "slug": slug, "rationale": rationale, "content": content,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
    })
    _json_emit({"ok": True, "proposal_id": rec["id"], "status": rec["status"]})


@propose_cmd.command(name="role")
@click.option("--role", required=True)
@click.option("--lesson", required=True)
@click.option("--evidence", default="")
def propose_role(role, lesson, evidence):
    ident = _load_cwd_agent()
    rec = proposals.create("role", ident["agent_id"], {
        "role": role, "lesson": lesson, "evidence": evidence,
    })
    _json_emit({"ok": True, "proposal_id": rec["id"], "status": rec["status"]})


@propose_cmd.command(name="budget")
@click.option("--task-id", required=True)
@click.option("--extra", type=int, required=True)
@click.option("--reason", required=True)
def propose_budget(task_id, extra, reason):
    ident = _load_cwd_agent()
    rec = proposals.create("budget", ident["agent_id"], {
        "task_id": task_id, "extra": extra, "reason": reason,
        "folder": str(Path.cwd().resolve()),
    })
    _json_emit({"ok": True, "proposal_id": rec["id"], "status": rec["status"]})


@cli.command(name="notify-human")
@click.option("--urgency", required=True,
              type=click.Choice(["info", "attention", "blocker"]))
@click.option("--reason", required=True)
@click.option("--context", default="")
@click.option("--suggested-action", default=None)
def notify_human_cli(urgency, reason, context, suggested_action):
    """Cross-machine async signal to the human operator."""
    ident = _load_cwd_agent()
    env = mailbox.send(
        from_id=ident["agent_id"],
        to_id="human@dashboard",
        subject=f"notify[{urgency}]",
        body=f"## {reason}\n\n{context}\n\n**suggested:** {suggested_action or '(none)'}",
    )
    _json_emit({"ok": True, "msg_id": env["msg_id"], "urgency": urgency})


@cli.command(name="request-budget")
@click.option("--task-id", required=True)
@click.option("--extra", type=int, required=True)
@click.option("--reason", required=True)
def request_budget_cli(task_id, extra, reason):
    """Ask for more iterations on a budgeted task. Proposal → critic → human."""
    ident = _load_cwd_agent()
    rec = proposals.create("budget", ident["agent_id"], {
        "task_id": task_id, "extra": extra, "reason": reason,
        "folder": str(Path.cwd().resolve()),
    })
    _json_emit({"ok": True, "proposal_id": rec["id"], "status": rec["status"]})


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
