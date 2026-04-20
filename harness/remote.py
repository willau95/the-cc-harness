"""Cross-machine operations for the fleet.

Strategy (v1):
- **Primary:** `fleet-ssh <machine> "<cmd>"` from mac-fleet-control. Reads the
  machine list from `~/.fleet-machines.json` (mac-fleet-control's registry).
- **Fallback:** plain `ssh user@host <cmd>` if fleet-ssh isn't on PATH but the
  user's ~/.ssh/config has hosts set up.

What this module does:
- Discover peer machines (reads mac-fleet-control's registry if present).
- `exec_remote(machine, cmd)` — run a shell command on a peer.
- `write_remote_file(machine, path, content)` — append JSONL line remotely.
- `push_message(envelope)` — delivers a mailbox envelope to a remote agent's
  inbox.jsonl by writing directly via SSH. Called by `mailbox.send` when the
  target agent's machine != current machine.
- `read_remote_events(machine, agent_id, date)` — fetch a remote agent's
  events JSONL for dashboard aggregation.

Principle: no daemon, no new protocol. Just SSH.
"""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path
from typing import Iterable
import yaml

from . import config

FLEET_MACHINES_JSON = Path.home() / ".fleet-machines.json"


def fleet_ssh_available() -> bool:
    return shutil.which("fleet-ssh") is not None


def list_machines() -> list[dict]:
    """Return machines known via mac-fleet-control registry, if any.
    Format: [{name, user, ip, added}]."""
    if not FLEET_MACHINES_JSON.exists():
        return []
    try:
        data = json.loads(FLEET_MACHINES_JSON.read_text())
        return data.get("machines", [])
    except Exception:
        return []


def find_machine(name_or_ip: str) -> dict | None:
    want = (name_or_ip or "").lower()
    for m in list_machines():
        if m["name"].lower() == want or m["ip"] == name_or_ip:
            return m
    return None


def _current_machine_id() -> str:
    return config.load_config().get("machine_id", config.machine_short())


def is_local_machine(name: str | None) -> bool:
    """True if this machine == the named one (best-effort string match)."""
    if not name:
        return True
    me = _current_machine_id().lower()
    # Normalize common forms
    n = name.lower().replace(" ", "").replace("_", "-")
    return me == n or me in n or n in me


def exec_remote(machine: str, cmd: str, timeout: int = 30) -> dict:
    """Run cmd on machine via fleet-ssh. Returns {ok, exit_code, stdout, stderr}."""
    if fleet_ssh_available():
        full = ["fleet-ssh", machine, cmd]
    else:
        m = find_machine(machine)
        if not m:
            return {"ok": False, "error": f"no machine '{machine}' in registry and no fleet-ssh"}
        target = f"{m['user']}@{m['ip']}"
        full = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes", target, cmd]
    try:
        p = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
        return {
            "ok": p.returncode == 0,
            "exit_code": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "exit_code": -1}
    except FileNotFoundError as e:
        return {"ok": False, "error": f"transport not found: {e}"}


def _normalize_remote_path(p: str) -> str:
    """Leading `~/` is not expanded when it sits inside single quotes on the
    remote shell. Rewrite to `$HOME/...` so we can keep the rest quote-safe."""
    if p.startswith("~/"):
        return "$HOME/" + p[2:]
    if p == "~":
        return "$HOME"
    return p


def append_remote_jsonl(machine: str, remote_path: str, line: str) -> dict:
    """Atomically-ish append a JSONL line to a file on a remote machine."""
    if "\n" in line:
        line = line.replace("\n", " ")
    safe_line = line.replace("'", "'\"'\"'")
    rp = _normalize_remote_path(remote_path)
    # Put the path in a shell variable (double-quoted so $HOME expands); write
    # the line with single quotes so its content is taken literally.
    cmd = (
        f'F={rp}; mkdir -p "$(dirname "$F")" && '
        f"printf '%s\\n' '{safe_line}' >> \"$F\""
    )
    return exec_remote(machine, cmd, timeout=15)


def read_remote_file(machine: str, remote_path: str, max_bytes: int = 200_000) -> dict:
    """Cat a remote file. Returns {ok, content}."""
    rp = _normalize_remote_path(remote_path)
    r = exec_remote(machine, f'F={rp}; head -c {max_bytes} "$F" 2>/dev/null || true')
    return {"ok": r.get("ok", False), "content": r.get("stdout", "")}


def read_remote_jsonl(machine: str, remote_path: str) -> list[dict]:
    """Fetch remote JSONL as a list of dicts."""
    r = read_remote_file(machine, remote_path)
    out: list[dict] = []
    if not r.get("ok"):
        return out
    for line in r.get("content", "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def push_message(machine: str, agent_id: str, envelope: dict) -> dict:
    """Deliver an envelope to a remote agent's inbox.

    Path must match `mailbox.inbox_path` on the receiving side: singular
    `mailbox` — historical typo had plural `mailboxes` here and every
    cross-machine message silently orphaned for ages before we noticed.
    """
    line = json.dumps(envelope, ensure_ascii=False)
    remote_path = f"~/.harness/mailbox/{agent_id}/inbox.jsonl"
    return append_remote_jsonl(machine, remote_path, line)


def bootstrap_peer_machine(machine: str) -> dict:
    """Teach a peer machine who else is in the fleet by writing
    ~/.harness/peers.yaml and ~/.fleet-machines.json on it. This lets the
    remote machine's mailbox.send reach back to other peers (incl. us).
    """
    import yaml as _yaml
    import os as _os
    machines = list_machines()
    me_name = config.machine_short()
    me_user = _os.environ.get("USER", "unknown")
    me_ip = "127.0.0.1"
    # tailscale binary paths to try (macOS often only has the App bundle path)
    TAILSCALE_BINS = [
        "tailscale",
        "/opt/homebrew/bin/tailscale",
        "/usr/local/bin/tailscale",
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
    ]
    import subprocess as _sp
    for bin_ in TAILSCALE_BINS:
        try:
            out = _sp.run([bin_, "ip", "-4"], capture_output=True, text=True, timeout=3)
            if out.returncode == 0 and out.stdout.strip():
                me_ip = out.stdout.strip().splitlines()[0]
                break
        except (FileNotFoundError, Exception):
            continue
    master_entry = {"name": me_name, "user": me_user, "ip": me_ip}
    all_peers = [m for m in machines if m["name"].lower() != machine.lower()]
    all_peers.append(master_entry)
    # Write peers.yaml
    peers_yaml = _yaml.safe_dump({"machines": all_peers}, sort_keys=False)
    safe_y = peers_yaml.replace("'", "'\"'\"'")
    r1 = exec_remote(machine, f"mkdir -p \"$HOME/.harness\" && printf '%s' '{safe_y}' > \"$HOME/.harness/peers.yaml\"", timeout=15)
    # Mirror fleet-machines.json for mac-fleet-control tooling + our remote.list_machines fallback
    fm_json = json.dumps({"machines": all_peers}, indent=2).replace("'", "'\"'\"'")
    r2 = exec_remote(machine, f"printf '%s' '{fm_json}' > \"$HOME/.fleet-machines.json\"", timeout=15)
    return {"ok": r1.get("ok", False) and r2.get("ok", False),
            "peers_count": len(all_peers)}


def spawn_remote_agent(machine: str, role: str, name: str, folder: str,
                        initial_prompt: str | None = None) -> dict:
    """Scaffold a new agent on a remote machine (runs `harness init` there).
    Does NOT start `claude` — that requires a TTY the caller doesn't own.
    Returns {ok, agent_id, folder, machine}.
    """
    folder_esc = folder.replace("'", "'\"'\"'")
    cmd = (
        f"mkdir -p '{folder_esc}' && cd '{folder_esc}' && "
        f"~/.local/bin/harness init --role {role} --name {name}"
    )
    # 1. bootstrap peer machine with our peers table so it can reach back
    bootstrap_peer_machine(machine)

    # 2. run harness init on remote
    r = exec_remote(machine, cmd, timeout=60)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("stderr") or r.get("error"),
                "stdout": r.get("stdout")}
    import re
    match = re.search(r"Agent (\S+) initialized", r.get("stdout", ""))
    agent_id = match.group(1) if match else None

    # 3. register locally (broadcast=True will push to other peers)
    if agent_id:
        from . import registry
        registry.register({
            "agent_id": agent_id,
            "slug": name,
            "role": role,
            "machine": machine,
            "folder": folder,
            "remote": True,
        })
    return {"ok": True, "agent_id": agent_id, "folder": folder, "machine": machine,
            "raw_output": r.get("stdout", "")}


def list_remote_fleet(machine: str) -> list[dict]:
    """Read a remote machine's registry + heartbeats and return
    enriched agent list (for dashboard aggregation across the fleet)."""
    # Read the remote registry
    reg = read_remote_jsonl(machine, "~/.harness/registry.jsonl")
    # Fold by agent_id (last entry wins; skip unregisters)
    state: dict[str, dict] = {}
    for e in reg:
        aid = e.get("agent_id")
        if not aid:
            continue
        if e.get("kind") == "unregister":
            state.pop(aid, None)
        else:
            state[aid] = e
    # Enrich with heartbeat freshness + active process liveness.
    # Batch the PID probes into ONE SSH roundtrip: for each agent folder,
    # read .harness/session.pid and kill -0 it on the remote host.
    folders = [(aid, entry.get("folder")) for aid, entry in state.items() if entry.get("folder")]
    alive_map: dict[str, bool] = {}
    if folders:
        probe_lines = [
            f'f={f!r}; if [ -f "$f/.harness/session.pid" ]; then '
            f'p=$(cat "$f/.harness/session.pid"); '
            f'if kill -0 "$p" 2>/dev/null; then echo "{aid}=alive"; else echo "{aid}=dead"; fi; '
            f'else echo "{aid}=unknown"; fi'
            for aid, f in folders
        ]
        probe = " ; ".join(probe_lines)
        r = exec_remote(machine, probe, timeout=6)
        if r.get("ok"):
            import re as _re
            text = _re.sub(r"\x1b\[[0-9;]*m", "", r.get("stdout") or "")
            text = _re.sub(r"^\[[^\]\n]+\]\s*\n?", "", text, flags=_re.MULTILINE)
            for line in text.splitlines():
                line = line.strip()
                if "=alive" in line:
                    alive_map[line.split("=", 1)[0]] = True
                elif "=dead" in line:
                    alive_map[line.split("=", 1)[0]] = False

    out = []
    for aid, entry in state.items():
        hb = read_remote_jsonl(machine, f"~/.harness/heartbeats/{aid}.jsonl")
        last_ts = hb[-1]["ts"] if hb else None
        out.append({
            **entry,
            "last_beat": last_ts,
            "remote_machine": machine,
            "process_alive": alive_map.get(aid),  # None if no PID file yet
        })
    return out


def all_machines_including_local() -> list[dict]:
    """Return list of {name, user, ip, is_local}. Local is synthesized from config."""
    machines = list_machines()
    result = [{**m, "is_local": False} for m in machines]
    # Try to detect which one is local
    me = _current_machine_id().lower()
    for m in result:
        if m["name"].lower().replace(" ", "").replace("_", "-") == me or m["name"].lower() == me:
            m["is_local"] = True
            break
    else:
        # Not in registry — add synthetic local entry
        result.insert(0, {"name": me, "user": "$USER", "ip": "127.0.0.1",
                         "is_local": True, "synthetic": True})
    return result
