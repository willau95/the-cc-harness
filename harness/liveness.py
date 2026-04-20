"""Active process liveness check.

SessionStart hook writes the claude PID to <folder>/.harness/session.pid.
This module exposes a cheap `is_alive(folder)` that `kill -0`s that PID so
the dashboard can tell an agent is dead within seconds of terminal close,
instead of waiting for the 30-minute heartbeat timeout.
"""
from __future__ import annotations
import os
from pathlib import Path


def session_pid(folder: Path | str) -> int | None:
    """Read the recorded claude PID for an agent folder, or None if absent."""
    p = Path(folder) / ".harness" / "session.pid"
    if not p.exists():
        return None
    try:
        return int(p.read_text().strip())
    except (ValueError, OSError):
        return None


def is_alive(folder: Path | str) -> bool | None:
    """True if claude is still running for this agent, False if it exited,
    None if we never recorded a PID (old agent, or SessionStart hook didn't
    fire yet — don't assume either way)."""
    pid = session_pid(folder)
    if pid is None:
        return None
    try:
        os.kill(pid, 0)  # signal 0 = existence check, doesn't actually signal
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't own it — should be impossible for a
        # claude we spawned. Treat as alive so we don't false-kill.
        return True
    except OSError:
        return False
