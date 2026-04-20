"""L-eq — the fleet-wide 武器库 (equipment library).

WHY separate from `arsenal` — arsenal is a knowledge base (text findings,
trust-tiered summaries, citations). equipment is a library of Claude Code
native artifacts that agents *equip* at spawn time: skills, slash commands,
subagent definitions, MCP servers, hooks, and reference repos.

INSTALLATION MECHANICS — we never invent a harness-proprietary loader.
equipment items map 1:1 to Claude Code's native discovery slots:

    kind: skill     → <agent>/.claude/skills/<slug>/SKILL.md + files
    kind: command   → <agent>/.claude/commands/<slug>.md
    kind: subagent  → <agent>/.claude/agents/<slug>.md
    kind: mcp       → merged into settings.local.json mcpServers block
    kind: hook      → merged into settings.local.json hooks block
    kind: repo      → <agent>/.harness/equipment/<slug>/source/ (reference-only)
    kind: preamble  → appended to CLAUDE.md between harness markers

This means an equipped skill is **indistinguishable from a hand-installed
skill** as far as Claude Code is concerned. No custom loader, no runtime
translation — we just pre-populate the right paths.

STORAGE (per host):

    ~/.harness/equipment/
    ├── index.sqlite                     # FTS5 over name + description + topics
    └── items/<slug>/
        ├── meta.yaml                    # kind, source_url, topics, trust, etc.
        ├── analysis.md                  # "武器说明书" — readable by agents
        │                                # BEFORE committing to equip. Generated
        │                                # by the (future) equipment-manager agent.
        └── content/                     # What actually gets copied to the agent
            # For kind=skill:
            ├── SKILL.md                 # copied to .claude/skills/<slug>/SKILL.md
            └── <supporting files>
            # For kind=command:
            ├── command.md               # copied to .claude/commands/<slug>.md
            # For kind=subagent:
            ├── agent.md                 # copied to .claude/agents/<slug>.md
            # For kind=mcp:
            ├── mcp.json                 # merged into settings.local.json
            # For kind=hook:
            ├── hook.json                # merged into settings.local.json
            # For kind=repo:
            └── source/...               # symlinked into .harness/equipment/<slug>/
"""
from __future__ import annotations
import shutil
import sqlite3
import subprocess
import yaml
from pathlib import Path
from . import config
from ._util import now_iso, slugify, atomic_write_text


VALID_KINDS = {"skill", "command", "subagent", "mcp", "hook", "repo", "preamble"}
VALID_TRUST = {"analyst_reviewed", "human_verified", "experimental", "retracted"}


def equipment_root() -> Path:
    p = config.HARNESS_ROOT / "equipment"
    p.mkdir(parents=True, exist_ok=True)
    return p


def items_root() -> Path:
    p = equipment_root() / "items"
    p.mkdir(parents=True, exist_ok=True)
    return p


def item_dir(slug: str) -> Path:
    return items_root() / slug


def db_path() -> Path:
    return equipment_root() / "index.sqlite"


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    slug TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    source_url TEXT,
    topics TEXT,                    -- CSV of topic tags
    trust TEXT DEFAULT 'experimental',
    added_by TEXT,
    added_at TEXT,
    updated_at TEXT
);

-- Standalone FTS5 (no content='items' linkage — keep it simple, write to
-- both tables explicitly. Avoids 'disk image malformed' on shared-rowid
-- corruption.)
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    slug UNINDEXED, name, description, topics
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(db_path())
    c.executescript(SCHEMA)
    return c


# ---------- core operations ----------

def _parse_skill_frontmatter(skill_md_path: Path) -> dict:
    """Extract name + description from a SKILL.md YAML frontmatter block."""
    text = skill_md_path.read_text()
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


def _infer_command_meta(md_path: Path) -> dict:
    """Slash-command .md frontmatter has `description: ...`."""
    text = md_path.read_text()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                return yaml.safe_load(parts[1]) or {}
            except Exception:
                return {}
    return {}


def add(slug: str | None, kind: str, source: str | Path,
        name: str | None = None, description: str | None = None,
        topics: list[str] | None = None, source_url: str | None = None,
        added_by: str = "human@cli",
        trust: str = "experimental") -> dict:
    """Add an equipment item to the library.

    `source` can be:
      - A local path to a directory (for skill / repo) or file (for command / subagent / mcp / hook)
      - A git URL (https://...) — we git clone it
      - A local path to a single .md file (for command / subagent / preamble)
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"kind must be one of {sorted(VALID_KINDS)}; got {kind!r}")
    if trust not in VALID_TRUST:
        raise ValueError(f"trust must be one of {sorted(VALID_TRUST)}; got {trust!r}")

    # 1. Resolve source → staged dir
    source_str = str(source)
    is_git = source_str.startswith(("http://", "https://", "git@"))
    if is_git:
        source_url = source_url or source_str
        inferred_slug = slugify(slug or Path(source_str.rstrip("/").split("/")[-1]).stem)
        d = item_dir(inferred_slug)
        if (d / "content").exists():
            shutil.rmtree(d / "content")
        d.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth=1", "--quiet", source_str, str(d / "content")],
            check=True, timeout=180,
        )
        slug = inferred_slug
    else:
        src_path = Path(source).expanduser().resolve()
        if not src_path.exists():
            raise FileNotFoundError(f"source not found: {src_path}")
        # Derive slug
        inferred_slug = slugify(slug or src_path.stem)
        slug = inferred_slug
        d = item_dir(slug)
        content = d / "content"
        if content.exists():
            shutil.rmtree(content)
        d.mkdir(parents=True, exist_ok=True)
        if src_path.is_dir():
            shutil.copytree(src_path, content)
        else:
            content.mkdir()
            shutil.copy2(src_path, content / src_path.name)

    # 2. Auto-derive name + description if caller didn't supply
    content = d / "content"
    if kind == "skill":
        skill_md = content / "SKILL.md"
        if skill_md.exists():
            fm = _parse_skill_frontmatter(skill_md)
            name = name or fm.get("name")
            description = description or fm.get("description")
    elif kind in ("command", "subagent", "preamble"):
        # Single-file kinds: look in content/ for a .md
        mds = list(content.glob("*.md"))
        if mds:
            fm = _infer_command_meta(mds[0])
            name = name or fm.get("name") or mds[0].stem
            description = description or fm.get("description")

    name = name or slug
    description = description or ""
    topics_csv = ",".join(topics or [])

    # 3. Write meta.yaml
    meta = {
        "slug": slug,
        "kind": kind,
        "name": name,
        "description": description,
        "topics": topics or [],
        "source_url": source_url,
        "trust": trust,
        "added_by": added_by,
        "added_at": now_iso(),
    }
    atomic_write_text(d / "meta.yaml", yaml.safe_dump(meta, sort_keys=False))

    # 4. Write placeholder analysis.md if not present (the "武器说明书")
    analysis_path = d / "analysis.md"
    if not analysis_path.exists():
        placeholder = (
            f"# {name} · 武器说明书\n\n"
            f"*This report is a placeholder. When the equipment-manager agent "
            f"runs, it will replace this with a real analysis: tech stack, key "
            f"modules, integration points, limitations, usage patterns.*\n\n"
            f"## Quick facts\n\n"
            f"- **kind**: `{kind}`\n"
            f"- **source**: {source_url or f'(local) {source}'}\n"
            f"- **topics**: {', '.join(topics or []) or '(none)'}\n"
            f"- **added**: {now_iso()} by {added_by}\n\n"
            f"## Description\n\n{description or '_no description_'}\n"
        )
        atomic_write_text(analysis_path, placeholder)

    # 5. Index in sqlite
    with _conn() as c:
        c.execute("DELETE FROM items WHERE slug=?", (slug,))
        c.execute(
            "INSERT INTO items(slug, kind, name, description, source_url, topics, trust, added_by, added_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (slug, kind, name, description, source_url, topics_csv, trust, added_by, meta["added_at"], meta["added_at"]),
        )
        c.execute("DELETE FROM items_fts WHERE slug=?", (slug,))
        c.execute(
            "INSERT INTO items_fts(slug, name, description, topics) VALUES (?,?,?,?)",
            (slug, name, description, topics_csv),
        )
        c.commit()

    return meta


def list_all(kind: str | None = None) -> list[dict]:
    with _conn() as c:
        if kind:
            rows = c.execute(
                "SELECT slug, kind, name, description, source_url, topics, trust, added_by, added_at "
                "FROM items WHERE kind=? ORDER BY added_at DESC", (kind,),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT slug, kind, name, description, source_url, topics, trust, added_by, added_at "
                "FROM items ORDER BY added_at DESC",
            ).fetchall()
    return [
        {"slug": r[0], "kind": r[1], "name": r[2], "description": r[3],
         "source_url": r[4], "topics": r[5].split(",") if r[5] else [],
         "trust": r[6], "added_by": r[7], "added_at": r[8]}
        for r in rows
    ]


def get(slug: str) -> dict | None:
    d = item_dir(slug)
    meta_path = d / "meta.yaml"
    if not meta_path.exists():
        return None
    meta = yaml.safe_load(meta_path.read_text()) or {}
    analysis_path = d / "analysis.md"
    if analysis_path.exists():
        meta["analysis"] = analysis_path.read_text()
    meta["path"] = str(d)
    return meta


def search(query: str, limit: int = 20) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT i.slug, i.kind, i.name, i.description, i.topics "
            "FROM items_fts JOIN items i ON i.slug = items_fts.slug "
            "WHERE items_fts MATCH ? LIMIT ?",
            (query, limit),
        ).fetchall()
    return [
        {"slug": r[0], "kind": r[1], "name": r[2], "description": r[3],
         "topics": r[4].split(",") if r[4] else []}
        for r in rows
    ]


def equip(slug: str, agent_folder: Path | str) -> dict:
    """Install this equipment's content into an agent folder, using
    Claude Code's native discovery slots so `claude` finds it automatically."""
    folder = Path(agent_folder).expanduser().resolve()
    meta = get(slug)
    if not meta:
        raise ValueError(f"equipment {slug!r} not in library")
    content = item_dir(slug) / "content"
    if not content.exists():
        raise RuntimeError(f"equipment {slug!r} has no content/ dir")

    kind = meta["kind"]
    installed_to: list[str] = []

    if kind == "skill":
        # Content must contain SKILL.md at its root (standard Claude Code layout)
        if not (content / "SKILL.md").exists():
            raise RuntimeError(f"skill {slug!r} missing SKILL.md")
        dst = folder / ".claude" / "skills" / slug
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(content, dst)
        installed_to.append(str(dst))

    elif kind == "command":
        # Single .md copied into .claude/commands/<slug>.md
        mds = list(content.glob("*.md"))
        if not mds:
            raise RuntimeError(f"command {slug!r} has no .md file")
        dst_dir = folder / ".claude" / "commands"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"{slug}.md"
        shutil.copy2(mds[0], dst)
        installed_to.append(str(dst))

    elif kind == "subagent":
        mds = list(content.glob("*.md"))
        if not mds:
            raise RuntimeError(f"subagent {slug!r} has no .md file")
        dst_dir = folder / ".claude" / "agents"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"{slug}.md"
        shutil.copy2(mds[0], dst)
        installed_to.append(str(dst))

    elif kind == "repo":
        # Reference-only code: symlink into .harness/equipment/<slug>/ so agent
        # can Read it but not pollute the real project. symlink = free updates
        # when library gets a new version.
        dst_dir = folder / ".harness" / "equipment"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / slug
        if dst.exists() or dst.is_symlink():
            dst.unlink() if dst.is_symlink() else shutil.rmtree(dst)
        dst.symlink_to(content)
        installed_to.append(str(dst))

    elif kind in ("mcp", "hook"):
        # Merge into settings.local.json
        import json as _json
        src_file = content / (f"{kind}.json")
        if not src_file.exists():
            # fall back to any json file in content
            jsons = list(content.glob("*.json"))
            if not jsons:
                raise RuntimeError(f"{kind} {slug!r} has no json file")
            src_file = jsons[0]
        src = _json.loads(src_file.read_text())
        settings_path = folder / ".claude" / "settings.local.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if settings_path.exists():
            try:
                existing = _json.loads(settings_path.read_text()) or {}
            except Exception:
                pass
        merge_key = "mcpServers" if kind == "mcp" else "hooks"
        existing.setdefault(merge_key, {} if kind == "mcp" else {})
        if kind == "mcp":
            # src should be {"mcpServers": {...}} or just {...}
            block = src.get("mcpServers", src) if isinstance(src, dict) else {}
            existing[merge_key].update(block)
        else:
            block = src.get("hooks", src) if isinstance(src, dict) else {}
            if isinstance(existing[merge_key], dict):
                existing[merge_key].update(block if isinstance(block, dict) else {})
        settings_path.write_text(_json.dumps(existing, indent=2))
        installed_to.append(str(settings_path))

    elif kind == "preamble":
        # Append to CLAUDE.md between dedicated equipment markers (distinct
        # from the harness preamble markers so re-init doesn't clobber them)
        mds = list(content.glob("*.md"))
        if not mds:
            raise RuntimeError(f"preamble {slug!r} has no .md file")
        snippet = mds[0].read_text()
        begin = f"<!-- BEGIN equipment:{slug} -->"
        end = f"<!-- END equipment:{slug} -->"
        block = f"{begin}\n{snippet}\n{end}\n"
        claude_md = folder / "CLAUDE.md"
        import re as _re
        if claude_md.exists():
            existing = claude_md.read_text()
            pattern = _re.compile(
                _re.escape(begin) + r".*?" + _re.escape(end) + r"\n?",
                _re.DOTALL,
            )
            if pattern.search(existing):
                new = pattern.sub(block, existing)
            else:
                sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
                new = existing + sep + block
            claude_md.write_text(new)
        else:
            claude_md.write_text(block)
        installed_to.append(str(claude_md))

    return {"ok": True, "slug": slug, "kind": kind, "installed_to": installed_to}


def equip_many(slugs: list[str], agent_folder: Path | str) -> list[dict]:
    results = []
    for s in slugs:
        try:
            results.append(equip(s, agent_folder))
        except Exception as e:
            results.append({"ok": False, "slug": s, "error": str(e)})
    return results


def set_trust(slug: str, new_trust: str, by: str = "human@dashboard") -> dict:
    """Update trust tier (experimental / analyst_reviewed / human_verified /
    retracted). Writes to both the meta.yaml AND the sqlite index so search +
    dashboard both reflect the change."""
    if new_trust not in VALID_TRUST:
        raise ValueError(f"trust must be one of {sorted(VALID_TRUST)}")
    d = item_dir(slug)
    meta_path = d / "meta.yaml"
    if not meta_path.exists():
        raise ValueError(f"equipment {slug!r} not found")
    meta = yaml.safe_load(meta_path.read_text()) or {}
    meta["trust"] = new_trust
    meta["trust_updated_at"] = now_iso()
    meta["trust_updated_by"] = by
    atomic_write_text(meta_path, yaml.safe_dump(meta, sort_keys=False))
    with _conn() as c:
        c.execute(
            "UPDATE items SET trust=?, updated_at=? WHERE slug=?",
            (new_trust, meta["trust_updated_at"], slug),
        )
        c.commit()
    return {"ok": True, "slug": slug, "trust": new_trust}
