#!/usr/bin/env bash
# install.sh — one-time setup for a Mac joining the harness fleet.
#
# Installs `harness` CLI into its own isolated venv, exposing it globally on PATH.
# No venv activation required afterwards. Uses uv (preferred) or pipx.
#
# What it does:
#   1. Ensure syncthing is installed (via brew)
#   2. Install harness CLI via uv or pipx (isolated, PATH-exposed)
#   3. Run `harness join` to scaffold ~/.harness/
#
# Assumes: macOS with Homebrew. Python 3.11+.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== the-cc-harness · install ==="
echo "repo: $REPO_ROOT"
echo

# ---------- 1. Syncthing (for cross-machine mode; harmless if skipped) ----------
if command -v syncthing >/dev/null 2>&1; then
    echo "✓ syncthing already installed"
else
    if command -v brew >/dev/null 2>&1; then
        echo "→ brew install syncthing"
        brew install syncthing
    else
        echo "[!] brew not found. Install Homebrew + syncthing manually if you want cross-machine."
    fi
fi
echo

# ---------- 2. harness CLI — isolated install, globally on PATH ----------
install_with_uv() {
    echo "→ uv tool install --editable $REPO_ROOT"
    uv tool install --force --editable "$REPO_ROOT"
}

install_with_pipx() {
    echo "→ pipx install --editable $REPO_ROOT"
    pipx install --force --editable "$REPO_ROOT"
}

if command -v uv >/dev/null 2>&1; then
    install_with_uv
elif command -v pipx >/dev/null 2>&1; then
    install_with_pipx
elif command -v brew >/dev/null 2>&1; then
    echo "→ Neither uv nor pipx found. Installing uv via brew..."
    brew install uv
    install_with_uv
else
    cat <<'EOS' >&2

[ERROR] The harness CLI needs either 'uv' or 'pipx' to install cleanly on macOS.

Install one (pick any):
    brew install uv          # recommended — fast, modern (Astral)
    brew install pipx        # traditional alternative

Then re-run:
    ./install.sh

Why? macOS's system Python is PEP 668-locked and a venv-activate-before-every-use
workflow is bad UX for a daily-driver CLI. uv/pipx handle this the right way
(isolated venv, globally-linked binary, no activation needed).
EOS
    exit 1
fi
echo

# ---------- Verify CLI is on PATH ----------
if command -v harness >/dev/null 2>&1; then
    echo "✓ harness CLI: $(command -v harness)"
else
    cat <<'EOS'

[!] 'harness' is installed but not yet on PATH. Try:

    # If you used uv:
    uv tool update-shell

    # Or: open a new shell, or add ~/.local/bin to PATH manually:
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
EOS
    exit 1
fi
echo

# ---------- 3. Scaffold ~/.harness/ ----------
echo "→ scaffolding ~/.harness/ ..."
harness join || true

echo
echo "=== done ==="
echo
echo "Next:"
echo "  cd ~/projects/<any-project>"
echo "  harness init --role researcher --name kevin"
echo "  claude"
echo
echo "Dashboard:  harness dashboard   →   http://localhost:9999"
