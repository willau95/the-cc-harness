#!/usr/bin/env bash
# PostToolUse hook — fires AFTER claude finishes a tool call.
# Mirror of pre_tool_use.sh; we mark the activity slot as idle so dashboard
# distinguishes "currently Editing xxx" vs "last action was Edit xxx".

set -eo pipefail
AGENT_FOLDER="${1:-$PWD}"
cd "$AGENT_FOLDER"
export PATH="$HOME/.local/bin:$HOME/.local/pipx/venvs/claude-harness/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# Drain stdin (PostToolUse also sends tool_result etc., we don't consume)
cat > /dev/null || true

mkdir -p "$AGENT_FOLDER/.harness"
python3 - <<'PYEOF'
import json, os, time
folder = os.path.abspath(os.getcwd())
path = os.path.join(folder, ".harness", "current_activity.json")
record = {}
if os.path.exists(path):
    try:
        with open(path) as fh:
            record = json.load(fh) or {}
    except Exception:
        record = {}
record["status"] = "idle"
record["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
tmp = path + ".tmp"
with open(tmp, "w") as fh:
    json.dump(record, fh)
os.replace(tmp, path)
print('{"hookSpecificOutput":{"hookEventName":"PostToolUse"}}')
PYEOF
