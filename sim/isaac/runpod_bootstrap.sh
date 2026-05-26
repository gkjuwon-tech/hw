#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python -m pip install --upgrade pip
python -m pip install -r sim/requirements.txt

python sim/isaac/check_environment.py

cat <<'MSG'

Bootstrap complete.

Next:
  bash sim/isaac/install_isaac_pip.sh
  python sim/isaac/isaac_tactile_pipeline.py --help

MSG
