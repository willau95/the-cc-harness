#!/usr/bin/env bash
# PreCompact hook — fires BEFORE Claude Code compacts context.
# Writes a Markdown digest to ~/.harness/digests/<agent>/<session>.md so the
# agent can rebuild state at the next SessionStart via the wake-up pack.
#
# Input:  JSON on stdin (hook_event_name=PreCompact, trigger, custom_instructions)
# Output: not used by Claude Code for PreCompact — we simply return 0.
#
# First arg = agent folder (passed by settings.local.json hook command line).

set -eo pipefail
AGENT_FOLDER="${1:-$PWD}"
cd "$AGENT_FOLDER"

# Drain stdin
cat > /dev/null || true

# Run digest. Swallow stderr to avoid disrupting compaction.
if command -v harness >/dev/null 2>&1; then
    harness digest >/dev/null 2>&1 || true
else
    python3 -m harness.cli digest >/dev/null 2>&1 || true
fi

exit 0
