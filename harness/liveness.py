"""Active process liveness check.

Multi-signal so it works even when the SessionStart hook hasn't (yet) written
<folder>/.harness/session.pid — for example on agents created before we
added PID tracking, or after a manual terminal close+reopen where the old
PID entry is stale:

  1. .harness/session.pid → kill -0 that PID (primary)
  2. pgrep for a claude process whose cwd matches the folder (local only)
  3. Claude Code's own session jsonl mtime for this folder — if the file
     was touched in the last 2 minutes, claude is actively running
"""
from __future__ import annotations
import os
import subprocess
import time
from pathlib import Path


CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
FRESH_ACTIVITY_SECONDS = 120  # 2 minutes


def session_pid(folder: Path | str) -> int | None:
    p = Path(folder) / ".harness" / "session.pid"
    if not p.exists():
        return None
    try:
        return int(p.read_text().strip())
    except (ValueError, OSError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _folder_to_project_dir(folder: Path) -> Path:
    slug = str(folder.resolve()).replace("/", "-")
    return CLAUDE_PROJECTS / slug


def _recent_session_activity(folder: Path) -> bool:
    """True if any session jsonl under Claude Code's project dir for this
    folder was modified in the last FRESH_ACTIVITY_SECONDS — a strong
    positive signal that claude is currently running here."""
    d = _folder_to_project_dir(folder)
    if not d.exists():
        return False
    cutoff = time.time() - FRESH_ACTIVITY_SECONDS
    try:
        for f in d.glob("*.jsonl"):
            if f.stat().st_mtime > cutoff:
                return True
    except OSError:
        pass
    return False


def _pgrep_claude_in_folder(folder: Path) -> bool | None:
    """Scan running claude processes to see if any has cwd == folder.
    Returns True/False/None (None if pgrep not available / couldn't check)."""
    try:
        r = subprocess.run(["pgrep", "-f", "claude"], capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            return False
        target = str(folder.resolve())
        for pid in r.stdout.split():
            # lsof -p <pid> shows cwd; grep only the cwd line
            try:
                lr = subprocess.run(
                    ["lsof", "-a", "-d", "cwd", "-p", pid],
                    capture_output=True, text=True, timeout=2,
                )
                if target in lr.stdout:
                    return True
            except Exception:
                continue
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def is_alive(folder: Path | str) -> bool | None:
    """True/False/None — best-effort liveness across three signals."""
    folder = Path(folder)

    # Signal 1: session.pid
    pid = session_pid(folder)
    if pid is not None:
        if _pid_alive(pid):
            return True
        # PID file exists but process is gone → definite False
        return False

    # Signal 2: recent Claude Code session jsonl activity (last 2 min)
    if _recent_session_activity(folder):
        return True

    # Signal 3: slower but definitive — pgrep+lsof for claude with this cwd
    pg = _pgrep_claude_in_folder(folder)
    if pg is True:
        return True
    if pg is False:
        # We actively looked and found nothing; but return None (not False)
        # because a new session could start any moment, and lsof requires
        # the process still be reading something from this folder.
        return None

    return None
