#!/usr/bin/env bash
# One-command reproduce of the Isaac-Sim tactile digital twin on a RunPod RTX box.
# Builds the venv (Python 3.10), installs Isaac Sim 4.5.0.0, runs the smoke
# render, generates the labelled dataset at scale, and prints the metrics report.
#
# Usage:  bash sim/isaac/run.sh [N_PILLS]      (default 50000)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
VENV="${ISAAC_VENV:-/workspace/isaacenv}"
N_PILLS="${1:-50000}"

export TMPDIR="${TMPDIR:-/workspace/tmp}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/workspace/pipcache}"
mkdir -p "$TMPDIR" "$PIP_CACHE_DIR"

if [ ! -d "$VENV" ]; then
  echo "== creating Python 3.10 venv at $VENV =="
  python3.10 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install -q --upgrade pip wheel

if ! python -c "import isaacsim" 2>/dev/null; then
  echo "== installing Isaac Sim 4.5.0.0 (large download) =="
  pip install --progress-bar off "isaacsim[all,extscache]==4.5.0.0" \
      --extra-index-url https://pypi.nvidia.com
fi

cd "$REPO"
echo "== smoke render =="
python sim/isaac/smoke.py

echo "== generate dataset + metrics ($N_PILLS pills) =="
python sim/isaac/generate_dataset.py --pills "$N_PILLS"

echo "== done.  artifacts in sim/isaac/out/ and sim/dataset/ =="
