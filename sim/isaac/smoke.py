"""Isaac Sim smoke test — boot headless, confirm GPU/RTX, save a render PNG.

Acceptance criterion #1 of docs/HANDOFF_ISAAC_SIM.md: prove Isaac Sim is
installed and the RTX renderer produces an image headless. Also probes which
import namespace this build exposes (4.5 renamed `omni.isaac.*` -> `isaacsim.*`)
so the rest of the pipeline can rely on it.

Run (inside the isaac venv, on the GPU pod):
  python sim/isaac/smoke.py
"""
from __future__ import annotations

import os

# Boot Kit headless with the ray-traced renderer BEFORE importing any omni/* .
from isaacsim import SimulationApp

OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

sim_app = SimulationApp({
    "headless": True,
    "renderer": "RayTracedLighting",
    "width": 1280,
    "height": 720,
})

# --- core API (4.5 namespace first, fall back to legacy) ---
try:
    from isaacsim.core.api import World
    from isaacsim.core.api.objects import DynamicCuboid
    NS = "isaacsim.core.api"
except Exception:
    from omni.isaac.core import World
    from omni.isaac.core.objects import DynamicCuboid
    NS = "omni.isaac.core (legacy)"

import numpy as np
import omni.replicator.core as rep
from PIL import Image

print(f"[smoke] core namespace = {NS}")

world = World(stage_units_in_meters=1.0)
world.scene.add_default_ground_plane()
world.scene.add(DynamicCuboid(prim_path="/World/cube", name="cube",
                              position=np.array([0.0, 0.0, 0.5]),
                              scale=np.array([0.3, 0.3, 0.3]),
                              color=np.array([0.2, 0.6, 0.3])))
world.reset()

# camera + render product via replicator (most reliable headless capture)
cam = rep.create.camera(position=(2.2, 2.2, 1.6), look_at=(0, 0, 0.2))
rp = rep.create.render_product(cam, (1280, 720))
rgb = rep.AnnotatorRegistry.get_annotator("rgb")
rgb.attach(rp)

for _ in range(80):                 # let the RTX renderer converge
    world.step(render=True)

data = rgb.get_data()
img = np.asarray(data)[..., :3].astype(np.uint8)
path = os.path.join(OUT, "smoke.png")
Image.fromarray(img).save(path)
print(f"[smoke] saved render -> {path}  shape={img.shape}  mean={img.mean():.1f}")

sim_app.close()
print("[smoke] OK")
