"""L2 — shared knowledge base. SQLite FTS5 + file tree.
Items carry provenance + trust fields (v3/v4). Search defaults to trusted-only.
"""
from __future__ import annotations
import sqlite3
import yaml
from pathlib import Path
from . import config
from ._util import now_iso, slugify, atomic_write_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    tags TEXT,                            -- comma-separated
    source_type TEXT NOT NULL,            -- web | file | agent_summary | agent_hypothesis | human_input
    source_refs TEXT,                     -- JSON array as text
    produced_by TEXT NOT NULL,
    produced_at TEXT NOT NULL,
    verification_status TEXT NOT NULL,    -- unverified | self_verified | peer_verified | human_verified
    chain_depth INTEGER NOT NULL DEFAULT 0,
    trust TEXT NOT NULL,                  -- verified | peer_verified | human_verified | agent_summary | hypothesis | retracted
    derived_from TEXT                     -- JSON array of slugs
);
CREATE INDEX IF NOT EXISTS idx_trust ON items(trust);
CREATE INDEX IF NOT EXISTS idx_produced_at ON items(produced_at DESC);
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    slug UNINDEXED, title, content, tags,
    tokenize = 'porter unicode61'
);
"""

DEFAULT_TRUST_FILTER = ("verified", "peer_verified", "human_verified")


def _conn() -> sqlite3.Connection:
    config.ensure_root()
    conn = sqlite3.connect(config.arsenal_db_path())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def add(slug: str | None, title: str, content: str, tags: list[str],
        source_type: str, source_refs: list[str], produced_by: str,
        derived_from: list[str] | None = None) -> dict:
    """Add an item. Trust is auto-assigned from source_type + refs presence."""
    import json
    slug = slugify(slug or title)
    derived_from = derived_from or []
    chain_depth = 0
    if derived_from:
        chain_depth = 1 + max((_chain_depth_of(s) for s in derived_from), default=0)

    # Trust assignment rule (auto; can be upgraded by critic later):
    if source_type == "human_input":
        trust = "human_verified"
        verification = "human_verified"
    elif source_type in ("web", "file") and source_refs:
        trust = "verified"
        verification = "self_verified"
    elif source_type == "agent_summary":
        trust = "agent_summary"
        verification = "unverified"
    elif source_type == "agent_hypothesis":
        trust = "hypothesis"
        verification = "unverified"
    else:
        trust = "agent_summary"
        verification = "unverified"

    # Write files
    d = config.arsenal_item_dir(slug)
    atomic_write_text(d / "content.md", content)
    meta = {
        "slug": slug, "title": title, "tags": tags,
        "source_type": source_type, "source_refs": source_refs,
        "produced_by": produced_by, "produced_at": now_iso(),
        "verification_status": verification, "chain_depth": chain_depth,
        "trust": trust, "derived_from": derived_from,
    }
    atomic_write_text(d / "meta.yaml", yaml.safe_dump(meta, sort_keys=False))

    # Index
    with _conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO items
            (slug, title, tags, source_type, source_refs, produced_by, produced_at,
             verification_status, chain_depth, trust, derived_from)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (slug, title, ",".join(tags), source_type,
              json.dumps(source_refs), produced_by, meta["produced_at"],
              verification, chain_depth, trust, json.dumps(derived_from)))
        conn.execute("DELETE FROM items_fts WHERE slug = ?", (slug,))
        conn.execute(
            "INSERT INTO items_fts(slug, title, content, tags) VALUES (?,?,?,?)",
            (slug, title, content, " ".join(tags)),
        )
        conn.commit()
    return meta


def _chain_depth_of(slug: str) -> int:
    with _conn() as conn:
        row = conn.execute("SELECT chain_depth FROM items WHERE slug = ?", (slug,)).fetchone()
        return row[0] if row else 0


def search(query: str, limit: int = 10,
           trust_filter: tuple[str, ...] = DEFAULT_TRUST_FILTER,
           include_unverified: bool = False) -> list[dict]:
    """FTS5 search with trust filter."""
    with _conn() as conn:
        # FTS5 needs quoted terms for partial; escape naively.
        q = query.replace('"', '""')
        if include_unverified:
            sql = """
                SELECT i.slug, i.title, i.trust, snippet(items_fts, 2, '[', ']', '…', 16) AS snippet,
                       i.produced_by, i.source_refs
                FROM items_fts JOIN items i ON i.slug = items_fts.slug
                WHERE items_fts MATCH ?
                ORDER BY rank LIMIT ?
            """
            rows = conn.execute(sql, (q, limit)).fetchall()
        else:
            placeholders = ",".join("?" for _ in trust_filter)
            sql = f"""
                SELECT i.slug, i.title, i.trust, snippet(items_fts, 2, '[', ']', '…', 16) AS snippet,
                       i.produced_by, i.source_refs
                FROM items_fts JOIN items i ON i.slug = items_fts.slug
                WHERE items_fts MATCH ? AND i.trust IN ({placeholders})
                ORDER BY rank LIMIT ?
            """
            rows = conn.execute(sql, (q, *trust_filter, limit)).fetchall()
    return [
        {"slug": r[0], "title": r[1], "trust": r[2], "snippet": r[3],
         "produced_by": r[4], "source_refs": r[5]}
        for r in rows
    ]


def get(slug: str) -> dict | None:
    """Full content + meta by slug."""
    d = config.arsenal_item_dir(slug) if slug else None
    if not d or not (d / "content.md").exists():
        return None
    meta = yaml.safe_load((d / "meta.yaml").read_text())
    content = (d / "content.md").read_text()
    return {**meta, "content": content}


def set_trust(slug: str, new_trust: str, by: str) -> None:
    """Used by critic (→peer_verified) or human (→human_verified)."""
    with _conn() as conn:
        conn.execute("UPDATE items SET trust = ? WHERE slug = ?", (new_trust, slug))
        conn.commit()
    d = config.arsenal_item_dir(slug)
    if (d / "meta.yaml").exists():
        meta = yaml.safe_load((d / "meta.yaml").read_text())
        meta["trust"] = new_trust
        meta["verification_status"] = new_trust
        atomic_write_text(d / "meta.yaml", yaml.safe_dump(meta, sort_keys=False))


def trust_distribution() -> dict[str, int]:
    with _conn() as conn:
        rows = conn.execute("SELECT trust, COUNT(*) FROM items GROUP BY trust").fetchall()
    return {r[0]: r[1] for r in rows}
