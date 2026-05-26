#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export OMNI_KIT_ACCEPT_EULA="${OMNI_KIT_ACCEPT_EULA:-YES}"
python -m pip install --upgrade pip

# Keep this pinned in one place so future agents can update deliberately.
ISAAC_VERSION="${ISAAC_VERSION:-5.1.0.0}"
python -m pip install "isaacsim[all,extscache]==${ISAAC_VERSION}" \
  --extra-index-url https://pypi.nvidia.com

python - <<'PY'
from isaacsim import SimulationApp

app = SimulationApp({"headless": True})
print("Isaac Sim headless boot: ok")
app.close()
PY
