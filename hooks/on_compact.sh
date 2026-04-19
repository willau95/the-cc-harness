#!/usr/bin/env bash
# onCompact hook — runs BEFORE Claude Code compacts context.
# Writes a Markdown digest to ~/.harness/digests/<agent>/<session>.md so the agent
# can recover state on the next session via the wake-up pack.
#
# Installed by `harness init` in ./.claude/settings.local.json.
# First arg = agent folder (where .harness/agent.yaml lives).

set -euo pipefail
AGENT_FOLDER="${1:-$PWD}"
cd "$AGENT_FOLDER"

# Use whichever python exposed `harness`
if command -v harness >/dev/null 2>&1; then
    harness digest >&2 || true
else
    python3 -m harness.cli digest >&2 || true
fi
