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

# ---------- 0. Auth env sanity check ----------
# harness uses whatever `claude` uses — default is subscription OAuth after
# `claude login`. If the user has a local-proxy env var set (cc-switch /
# claude-code-router / vibeproxy), claude tries to hit that proxy instead of
# Anthropic. When the proxy isn't running, claude errors with
# "Unable to connect to API (ConnectionRefused)" — a confusing symptom that
# looks like a harness bug but isn't.
_anthropic_url_in_rc=""
for _rc in "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.bashrc" "$HOME/.bash_profile"; do
    if [ -f "$_rc" ] && grep -q "^export ANTHROPIC_BASE_URL" "$_rc" 2>/dev/null; then
        _anthropic_url_in_rc="$_rc"
        break
    fi
done
if [ -n "${ANTHROPIC_BASE_URL:-}" ] || [ -n "$_anthropic_url_in_rc" ]; then
    cat <<EOS
[!] Heads-up — ANTHROPIC_BASE_URL is set in your shell env.

    Current value: ${ANTHROPIC_BASE_URL:-<in $_anthropic_url_in_rc>}

This means \`claude\` will route through a local proxy (e.g. cc-switch /
claude-code-router / vibeproxy), NOT Anthropic directly. If that proxy's
daemon is not running, every agent you spawn will hang on
"Unable to connect to API (ConnectionRefused)".

    · If you use that proxy → make sure its daemon is running BEFORE \`claude\`
    · If you don't → unset it: \`unset ANTHROPIC_BASE_URL\` + remove the
      \`export ANTHROPIC_BASE_URL=...\` line from ${_anthropic_url_in_rc:-your shell rc}

harness itself doesn't set this variable and uses your \`claude login\`
subscription by default.
EOS
    echo
fi

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

# ---------- 4. Dashboard frontend (Node + Vite build) ----------
# The dashboard UI is a Vite + React app that must be built once before
# `harness dashboard` can serve it. If Node is missing, we install via brew.
FRONTEND_DIR="$REPO_ROOT/dashboard/frontend"
if [ -f "$FRONTEND_DIR/package.json" ]; then
    echo "→ Installing dashboard UI dependencies..."
    if ! command -v node >/dev/null 2>&1; then
        if command -v brew >/dev/null 2>&1; then
            echo "  Node not found; brew install node..."
            brew install node
        else
            echo "[!] Node.js not found, no brew. Install Node manually, then re-run."
            echo "    (The CLI works without the UI — skipping UI build.)"
        fi
    fi
    if command -v node >/dev/null 2>&1; then
        (
            cd "$FRONTEND_DIR"
            if command -v pnpm >/dev/null 2>&1; then
                pnpm install && pnpm run build
            elif command -v npm >/dev/null 2>&1; then
                npm install && npm run build
            else
                echo "[!] No npm/pnpm found — skipping UI build."
            fi
        )
        if [ -d "$FRONTEND_DIR/dist" ]; then
            echo "  ✓ Dashboard UI built at $FRONTEND_DIR/dist"
        fi
    fi
fi
echo

echo "=== done ==="
echo
echo "Next:"
echo "  cd ~/projects/<any-project>"
echo "  harness init --role researcher --name kevin"
echo "  claude"
echo
echo "Dashboard:  harness dashboard   →   http://localhost:9999"
