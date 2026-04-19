"""Config + well-known paths. Single source of truth for where things live."""
from __future__ import annotations
import os
import socket
from pathlib import Path
import yaml

HARNESS_ROOT = Path(os.environ.get("HARNESS_ROOT", Path.home() / ".harness"))
CONFIG_FILE = HARNESS_ROOT / "config.yaml"

DEFAULT_CONFIG = {
    "machine_id": None,  # filled at first join
    "rate_limits": {"send_message_qpm": 60, "arsenal_add_qpm": 10},
    "task_budget_default": 90,
    "memory_nudge_interval": 30,
    "skill_nudge_interval": 30,
    "zombie_timeout_minutes": 30,
    "notify_backend": "log",  # log | imessage | telegram (later)
}


def machine_short() -> str:
    """Short machine identifier — hostname minus .local and dashes only."""
    host = socket.gethostname().replace(".local", "")
    return host.lower().replace("_", "-").replace(" ", "-")[:32]


def ensure_root() -> Path:
    """Ensure ~/.harness/ and its key subdirs exist. Idempotent."""
    subdirs = [
        "mailboxes", "events", "heartbeats", "digests",
        "arsenal", "arsenal/items",
        "projects", "proposals", "proposals/skill",
        "proposals/role", "proposals/budget",
        "roles-evolved", "wisdom", "reviews", "logs",
    ]
    for d in subdirs:
        (HARNESS_ROOT / d).mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        cfg = dict(DEFAULT_CONFIG)
        cfg["machine_id"] = machine_short()
        CONFIG_FILE.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return HARNESS_ROOT


def load_config() -> dict:
    ensure_root()
    return yaml.safe_load(CONFIG_FILE.read_text()) or {}


def save_config(cfg: dict) -> None:
    CONFIG_FILE.write_text(yaml.safe_dump(cfg, sort_keys=False))


def registry_path() -> Path:
    return HARNESS_ROOT / "registry.jsonl"


def mailbox_dir(agent_id: str) -> Path:
    p = HARNESS_ROOT / "mailboxes" / agent_id
    p.mkdir(parents=True, exist_ok=True)
    (p / "archive").mkdir(exist_ok=True)
    return p


def events_file(agent_id: str, date_str: str) -> Path:
    p = HARNESS_ROOT / "events" / agent_id
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{date_str}.jsonl"


def heartbeat_file(agent_id: str) -> Path:
    return HARNESS_ROOT / "heartbeats" / f"{agent_id}.jsonl"


def digest_file(agent_id: str, session_id: str) -> Path:
    p = HARNESS_ROOT / "digests" / agent_id
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{session_id}.md"


def project_dir(project: str) -> Path:
    p = HARNESS_ROOT / "projects" / project
    p.mkdir(parents=True, exist_ok=True)
    return p


def arsenal_db_path() -> Path:
    return HARNESS_ROOT / "arsenal" / "index.sqlite"


def arsenal_item_dir(slug: str) -> Path:
    p = HARNESS_ROOT / "arsenal" / "items" / slug
    p.mkdir(parents=True, exist_ok=True)
    return p


def proposals_dir(kind: str) -> Path:
    p = HARNESS_ROOT / "proposals" / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


def role_lessons_file(role: str) -> Path:
    p = HARNESS_ROOT / "roles-evolved" / role
    p.mkdir(parents=True, exist_ok=True)
    return p / "lessons.jsonl"
