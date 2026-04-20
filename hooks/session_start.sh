#!/usr/bin/env bash
# SessionStart hook — fires at new session / resume / clear / post-compact return.
#
# Input:  JSON on stdin (hook_event_name, session_id, transcript_path, cwd, source, ...)
# Output: JSON on stdout of shape
#   {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"<wake-up md>"}}
# Claude Code appends `additionalContext` into the agent's context.
#
# First arg = agent folder (passed by settings.local.json hook command line).

set -eo pipefail
AGENT_FOLDER="${1:-$PWD}"
cd "$AGENT_FOLDER"

# Claude Code may invoke hooks with a trimmed PATH. Prepend common harness install locations.
export PATH="$HOME/.local/bin:$HOME/.local/pipx/venvs/claude-harness/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# Drain stdin (Claude Code pipes JSON we don't currently consume).
cat > /dev/null || true

# Record the parent process id (= claude itself) so the dashboard can do
# active liveness checks instead of waiting for the 30-min heartbeat timeout.
# When the user closes the terminal, claude dies, this PID goes stale, and
# the dashboard shows the agent offline within seconds.
mkdir -p "$AGENT_FOLDER/.harness"
echo "$PPID" > "$AGENT_FOLDER/.harness/session.pid"

# Heartbeat first — keeps the agent fresh in the fleet registry every time a
# session starts, resumes, or returns from compact. Without this the agent
# shows as zombie after 10 min idle, even if Claude Code is still open.
if command -v harness >/dev/null 2>&1; then
    harness heartbeat >/dev/null 2>&1 || true
else
    python3 -m harness.cli heartbeat >/dev/null 2>&1 || true
fi

# Resolve harness CLI and capture wake-up text.
if command -v harness >/dev/null 2>&1; then
    WAKEUP="$(harness wakeup 2>/dev/null || true)"
else
    WAKEUP="$(python3 -m harness.cli wakeup 2>/dev/null || true)"
fi

# JSON-encode the wake-up string via python (safe across any content).
WAKEUP_TEXT="$WAKEUP" python3 <<'PYEOF'
import json, os, sys
payload = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": os.environ.get("WAKEUP_TEXT", ""),
    }
}
sys.stdout.write(json.dumps(payload))
PYEOF
