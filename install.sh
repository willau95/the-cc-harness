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
    # Ensure ~/.local/bin is on PATH (uv edits shell rc idempotently)
    uv tool update-shell || true
}

install_with_pipx() {
    echo "→ pipx install --editable $REPO_ROOT"
    pipx install --force --editable "$REPO_ROOT"
    # Ensure ~/.local/bin is on PATH (pipx edits shell rc idempotently)
    pipx ensurepath || true
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
# uv/pipx just updated the shell rc, but THIS shell wasn't reloaded yet.
# Test with an explicit ~/.local/bin check so we don't false-fail.
export PATH="$HOME/.local/bin:$PATH"

if command -v harness >/dev/null 2>&1; then
    echo "✓ harness CLI: $(command -v harness)"
else
    cat <<'EOS'

[!] 'harness' was installed but is not on PATH in this shell.

The shell config (~/.zshrc or ~/.bashrc) was updated by uv/pipx so new shells
will have it. To make THIS shell see it, run one of:

    exec zsh                    # or bash — reloads this shell
    source ~/.zshrc             # reload rc in place
    open a new terminal window

Then re-run:  harness join
EOS
    exit 0
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
