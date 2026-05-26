#!/usr/bin/env bash
#
# Build the Conet Tactile operator UI (desktop/) and install it as the
# bundle the on-device kiosk server serves.
#
# The kiosk server (edge_agent/edge_agent/kiosk.py) serves whatever static
# files live in CONET_EDGE_KIOSK_STATIC_DIR (default
# /opt/conet/edge_agent/kiosk). This script produces that bundle from the
# React app that PR #24 had deleted, so Chromium --kiosk renders the real
# operator UI instead of an "appliance starting…" splash.
#
# Usage:
#   edge_agent/scripts/install-kiosk-ui.sh [TARGET_DIR]
#
# TARGET_DIR defaults to /opt/conet/edge_agent/kiosk. Override it (and
# CONET_EDGE_KIOSK_STATIC_DIR to match) when developing against a source
# tree, e.g.:
#   CONET_EDGE_KIOSK_STATIC_DIR=$PWD/.kiosk-bundle \
#       edge_agent/scripts/install-kiosk-ui.sh "$PWD/.kiosk-bundle"
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UI_DIR="$REPO_ROOT/desktop"
TARGET_DIR="${1:-/opt/conet/edge_agent/kiosk}"

if [[ ! -d "$UI_DIR" ]]; then
    echo "error: operator UI source not found at $UI_DIR" >&2
    exit 1
fi

echo "==> Building operator UI in $UI_DIR"
cd "$UI_DIR"
# `npm ci` needs a lockfile; we ship without one (Electron was removed),
# so use `npm install` which resolves + writes node_modules.
npm install
npm run build

if [[ ! -f "$UI_DIR/dist/index.html" ]]; then
    echo "error: build did not produce dist/index.html" >&2
    exit 1
fi

echo "==> Installing bundle into $TARGET_DIR"
# Use sudo only when the target isn't writable by the current user.
SUDO=""
if [[ ! -w "$(dirname "$TARGET_DIR")" && "$(id -u)" -ne 0 ]]; then
    SUDO="sudo"
fi
$SUDO mkdir -p "$TARGET_DIR"
# Replace the bundle atomically-ish: clear old assets, copy fresh ones.
$SUDO rm -rf "${TARGET_DIR:?}/assets" "$TARGET_DIR/index.html"
$SUDO cp -r "$UI_DIR/dist/." "$TARGET_DIR/"

echo "==> Done. The kiosk server will serve the operator UI from $TARGET_DIR"
echo "    Restart it to pick up the new bundle:"
echo "      sudo systemctl restart conet-edge-agent.service conet-edge-kiosk.service"
