#!/usr/bin/env bash
# SessionStart hook — runs when Claude Code starts a new session in this folder.
# Emits a Markdown wake-up pack on stdout. Claude Code injects hook stdout as
# an initial user message (behavior depends on Claude Code version; adjust as needed).
#
# Installed by `harness init` in ./.claude/settings.local.json.
# First arg = agent folder.

set -euo pipefail
AGENT_FOLDER="${1:-$PWD}"
cd "$AGENT_FOLDER"

if command -v harness >/dev/null 2>&1; then
    harness wakeup
else
    python3 -m harness.cli wakeup
fi
