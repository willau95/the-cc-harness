#!/usr/bin/env bash
# install.sh — one-time setup for a Mac joining the harness fleet.
#
# What it does:
#   1. Check / install Syncthing (via brew)
#   2. pip install -e . (editable install of the harness CLI)
#   3. Run `harness join` to scaffold ~/.harness/
#
# Assumes: macOS with Homebrew. Python 3.11+.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Claude Harness · install ==="
echo "repo: $REPO_ROOT"
echo

# 1. Syncthing
if command -v syncthing >/dev/null 2>&1; then
    echo "✓ syncthing already installed"
else
    if command -v brew >/dev/null 2>&1; then
        echo "→ installing syncthing via brew..."
        brew install syncthing
    else
        echo "[!] brew not found. Install Homebrew first, or install syncthing manually."
        echo "    (continuing without it; you can add it later)"
    fi
fi

# 2. Python package
PYTHON="${PYTHON:-python3}"
echo "→ installing harness Python package (editable)..."
if command -v uv >/dev/null 2>&1; then
    uv pip install -e "$REPO_ROOT"
else
    "$PYTHON" -m pip install -e "$REPO_ROOT"
fi

# Verify
if command -v harness >/dev/null 2>&1; then
    echo "✓ harness CLI installed: $(which harness)"
else
    echo "[!] harness CLI not on PATH. You may need to activate your venv or adjust PATH."
fi

# 3. Bootstrap ~/.harness/
echo "→ scaffolding ~/.harness/..."
harness join || true

echo
echo "=== done ==="
echo
echo "Next:"
echo "  cd ~/projects/<some-project>"
echo "  harness init --role researcher --name kevin"
echo "  claude"
echo
echo "To see the fleet dashboard: harness dashboard → http://localhost:9999"
