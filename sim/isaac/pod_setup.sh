#!/usr/bin/env bash
# Prepare a fresh RunPod container to run Isaac Sim headless.
#
# The pod's root overlay is ephemeral (wiped on stop/start) while /workspace
# persists — so the Isaac venv survives a restart but the system libraries the
# RTX/Kit runtime links against do NOT. Re-run this after every pod (re)start.
# It (1) installs those libs, (2) writes /workspace/isaac_env.sh with the env
# (LD_LIBRARY_PATH over the bundled kit libs, EULA accept, headless X paths)
# that every Isaac entrypoint should `source` before launching.
set -euo pipefail

VENV="${ISAAC_VENV:-/workspace/isaacenv}"
SP="$VENV/lib/python3.10/site-packages"

echo "== system libraries the Kit/RTX runtime needs (ephemeral overlay) =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  libsm6 libice6 libxt6 libxmu6 libglu1-mesa libgl1 libegl1 \
  libvulkan1 vulkan-tools libxrandr2 libxinerama1 libxcursor1 libxi6 \
  libxext6 libx11-6 libxrender1 libgomp1 libglib2.0-0 libfontconfig1 \
  libxkbcommon0 openscad

echo "== writing /workspace/isaac_env.sh =="
LD="$(find "$SP/isaacsim" -type d -name bin 2>/dev/null | tr '\n' ':')$SP/omni"
cat > /workspace/isaac_env.sh <<EOF
# source this before launching any Isaac Sim entrypoint
source "$VENV/bin/activate"
export OMNI_KIT_ACCEPT_EULA=YES
export OMNI_KIT_ALLOW_ROOT=1
export XDG_RUNTIME_DIR=/tmp/xdg
mkdir -p /tmp/xdg
export LD_LIBRARY_PATH="$LD:\${LD_LIBRARY_PATH:-}"
EOF
echo "== done. before Isaac runs:  source /workspace/isaac_env.sh =="
