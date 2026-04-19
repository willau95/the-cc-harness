"""L0 — agent identity. Stored in ./.harness/agent.yaml inside each agent folder."""
from __future__ import annotations
from pathlib import Path
import yaml
from . import config
from ._util import short_id, now_iso


def agent_folder_dot(folder: Path) -> Path:
    return folder / ".harness"


def identity_file(folder: Path) -> Path:
    return agent_folder_dot(folder) / "agent.yaml"


def make_agent_id(slug: str, machine: str | None = None) -> str:
    """<machine>-<slug>-<uuid8> — globally unique, human-readable."""
    m = machine or config.machine_short()
    return f"{m}-{slug}-{short_id(8)}"


def write_identity(folder: Path, identity: dict) -> None:
    d = agent_folder_dot(folder)
    d.mkdir(parents=True, exist_ok=True)
    identity_file(folder).write_text(yaml.safe_dump(identity, sort_keys=False))


def load_identity(folder: Path) -> dict | None:
    f = identity_file(folder)
    if not f.exists():
        return None
    return yaml.safe_load(f.read_text()) or {}


def create_identity(folder: Path, role: str, slug: str) -> dict:
    ident = {
        "agent_id": make_agent_id(slug),
        "slug": slug,
        "role": role,
        "machine": config.machine_short(),
        "folder": str(folder.resolve()),
        "created_at": now_iso(),
        "capabilities": [],
    }
    write_identity(folder, ident)
    return ident
