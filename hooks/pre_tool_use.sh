#!/usr/bin/env bash
# PreToolUse hook — fires BEFORE claude invokes any tool.
#
# Input:  JSON on stdin  {"tool_name": "...", "tool_input": {...}, ...}
# Output: JSON on stdout (empty hookSpecificOutput — we just observe)
#
# Side effect: write <folder>/.harness/current_activity.json so the dashboard
# can show "this agent is currently calling <tool>..." in real time.
#
# First arg = agent folder (passed by settings.local.json hook command line).

set -eo pipefail
AGENT_FOLDER="${1:-$PWD}"
cd "$AGENT_FOLDER"

export PATH="$HOME/.local/bin:$HOME/.local/pipx/venvs/claude-harness/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# Heartbeat on every tool call — keeps the agent from drifting to stale
# when it's using non-harness tools (Read/Edit/Bash/Grep/...) and hasn't
# invoked any of our skill tools in the last 30 min.
if command -v harness >/dev/null 2>&1; then
    harness heartbeat >/dev/null 2>&1 || true
else
    python3 -m harness.cli heartbeat >/dev/null 2>&1 || true
fi

# Read stdin JSON and pull out tool_name + a short input summary
mkdir -p "$AGENT_FOLDER/.harness"
INPUT_JSON="$(cat || true)"
FOLDER="$AGENT_FOLDER" INPUT_JSON="$INPUT_JSON" python3 - <<'PYEOF'
import json, os, time
folder = os.environ.get("FOLDER", "")
raw = os.environ.get("INPUT_JSON", "").strip()
try:
    payload = json.loads(raw) if raw else {}
except json.JSONDecodeError:
    payload = {}
tool_name = payload.get("tool_name") or payload.get("name") or "?"
tool_input = payload.get("tool_input") or payload.get("input") or {}

def summary(name, args):
    if not isinstance(args, dict):
        return ""
    if name in {"Read", "Edit", "Write", "NotebookEdit"}:
        return str(args.get("file_path") or args.get("notebook_path") or "")[:200]
    if name == "Bash":
        return str(args.get("command", ""))[:200]
    if name == "Grep":
        return str(args.get("pattern", ""))[:120]
    if name == "Glob":
        return str(args.get("pattern", ""))[:160]
    if name == "WebFetch":
        return str(args.get("url", ""))[:200]
    if name == "WebSearch":
        return str(args.get("query", ""))[:160]
    if name == "TodoWrite":
        todos = args.get("todos") or []
        return f"{len(todos)} todos"
    keys = list(args.keys())[:3]
    return "{" + ", ".join(keys) + ("..." if len(args) > 3 else "") + "}"

record = {
    "tool_name": tool_name,
    "tool_input_summary": summary(tool_name, tool_input),
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "status": "running",
}

out_path = os.path.join(folder, ".harness", "current_activity.json")
# Atomic write
tmp = out_path + ".tmp"
with open(tmp, "w") as fh:
    json.dump(record, fh)
os.replace(tmp, out_path)

# Claude Code expects a JSON response; empty hookSpecificOutput is fine
print('{"hookSpecificOutput":{"hookEventName":"PreToolUse"}}')
PYEOF
