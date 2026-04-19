"""Small shared utilities: atomic JSONL append, safe reads, timestamps."""
from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def append_jsonl(path: Path, obj: dict) -> None:
    """Atomic append of a single JSON line.
    Uses O_APPEND which is atomic for small writes on POSIX.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def read_jsonl(path: Path) -> Iterator[dict]:
    """Yield one dict per line. Skip malformed lines rather than crash."""
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # corrupt line (OS crash?) — skip but don't explode
                continue


def atomic_write_text(path: Path, content: str) -> None:
    """Write via temp file + rename for atomicity."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def slugify(text: str) -> str:
    """Lowercase, replace non-alnum with dash, trim."""
    import re
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:64] or "item"


def short_id(n: int = 8) -> str:
    import secrets
    return secrets.token_hex(n // 2)
