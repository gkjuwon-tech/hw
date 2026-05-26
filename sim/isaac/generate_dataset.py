"""Isaac-Sim tactile dataset generator — one GPU pipeline -> dataset + metrics.

Builds one inspection env (a 16x16 sprung-taxel mesh + a 4x4 pill tray), clones
it across many GPU envs, then runs domain-randomized batches: each tray gets
random good/void pill masses, settles under gravity on the bed of springs, and
we read every taxel's compression -> per-cell contact force = a 16x16 pressure
frame (relu(k * (rest_z - z))), exactly the MuJoCo readout but with real PhysX
contact mechanics on the GPU.

Every simulated pill contributes (a) a labelled frame to the dataset AND (b) a
sample to the metric. Output is drop-in compatible with the CPU twin:
  frames (N,16,16) f32, pill_pressure (N,16) f32, pill_label (N,16) i8,
  pill_centers (16,2).

Run (isaac venv on the GPU pod):
  python sim/isaac/generate_dataset.py --pills 50000 --envs 256
"""
from __future__ import annotations

import argparse
import os
import sys

from isaacsim import SimulationApp

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pills", type=int, default=50000, help="target labelled pills")
    ap.add_argument("--envs", type=int, default=256, help="parallel cloned trays")
    ap.add_argument("--settle", type=int, default=120, help="physics steps per batch")
    ap.add_argument("--out", default=os.path.join(REPO, "sim", "dataset", "tactile_pills.npz"))
    ap.add_argument("--report", action="store_true", help="run detect.report at the end")
    a = ap.parse_args()

    sim_app = SimulationApp({"headless": True})

    import numpy as np
    from pxr import UsdGeom, Gf
    sys.path.insert(0, REPO)
    sys.path.insert(0, HERE)
    import sim.isaac.tactile_sensor as TS

    from isaacsim.core.api import World
    from isaacsim.core.prims import RigidPrim
    try:
        from isaacsim.core.cloner import GridCloner
    except Exception:
        from omni.isaac.cloner import GridCloner

    ROWS = COLS = TS.ROWS
    NPILL = TS.PILL_N * TS.PILL_N
    N = a.envs

    world = World(stage_units_in_meters=1.0, backend="torch", device="cuda")
    stage = world.stage

    # ground so stray dynamics rest
    world.scene.add_default_ground_plane(z_position=-0.30)

    # build the prototype env, then clone on a grid
    base_env = "/World/envs/env_0"
    UsdGeom.Xform.Define(stage, "/World/envs")
    UsdGeom.Xform.Define(stage, base_env)
    TS.build_sensor(stage, base_env, ROWS, COLS)
    TS.add_pill_tray(stage, base_env)

    cloner = GridCloner(spacing=0.6)
    target_paths = cloner.generate_paths("/World/envs/env", N)
    cloner.clone(source_prim_path=base_env, prim_paths=target_paths,
                 replicate_physics=True, base_env_path="/World/envs")

    # ordered views: taxels row-major per env, pills per env
    taxel_paths = [f"/World/envs/env_{e}/taxel_{r}_{c}"
                   for e in range(N) for r in range(ROWS) for c in range(COLS)]
    pill_paths = [f"/World/envs/env_{e}/pill_{k}"
                  for e in range(N) for k in range(NPILL)]
    taxels = RigidPrim(prim_paths_expr=taxel_paths, name="taxels")
    pills = RigidPrim(prim_paths_expr=pill_paths, name="pills")

    world.reset()

    import torch
    base_masses = pills.get_masses().clone()                     # (N*NPILL,)
    rest_z = None

    # cell -> pill map (same geometry as the CPU twin)
    centers = TS.pill_centers()
    cell_to_pill = {}
    for r in range(ROWS):
        for c in range(COLS):
            x, y = TS.grid_xy(r, c)
            for k, (px, py) in enumerate(centers):
                if (x - px) ** 2 + (y - py) ** 2 <= (TS.PILL_R * 1.25) ** 2:
                    cell_to_pill[(r, c)] = k
                    break

    def read_frames():
        pos, _ = taxels.get_world_poses()
        z = pos[:, 2].reshape(N, ROWS, COLS)
        comp = torch.clamp((rest_z - z) * TS.TAXEL_K, min=0.0)
        return comp.cpu().numpy()

    # zero-load baseline (no pills touching): lift pills away, settle, record rest_z
    far = pills.get_world_poses()[0].clone()
    far[:, 2] += 0.5
    pills.set_world_poses(positions=far)
    for _ in range(60):
        world.step(render=False)
    pos, _ = taxels.get_world_poses()
    rest_z = pos[:, 2].reshape(N, ROWS, COLS)

    rng = np.random.default_rng(7)
    GOOD_J, VOID_R, P_VOID, NOISE = 0.04, (0.55, 0.78), 0.25, 0.012
    frames_all, press_all, lab_all = [], [], []
    done = 0
    batch = 0
    init_pos = pills.get_world_poses()[0].clone()
    init_pos[:, 2] = TS.M0 * 0 + 0.012   # drop height above the mesh

    while done < a.pills:
        # domain-randomized masses + labels per pill per env
        u = rng.random((N, NPILL))
        is_void = u < P_VOID
        good_m = TS.M0 * (1 + rng.uniform(-GOOD_J, GOOD_J, (N, NPILL)))
        void_m = TS.M0 * rng.uniform(*VOID_R, (N, NPILL))
        masses = np.where(is_void, void_m, good_m).astype(np.float32)
        labels = is_void.astype(np.int8)

        pills.set_masses(torch.tensor(masses.ravel(), device="cuda"))
        # reset pill poses to drop height with small xy jitter (DR)
        jit = init_pos.clone()
        jit[:, 0] += torch.tensor(rng.normal(0, 0.001, N * NPILL), device="cuda", dtype=jit.dtype)
        jit[:, 1] += torch.tensor(rng.normal(0, 0.001, N * NPILL), device="cuda", dtype=jit.dtype)
        pills.set_world_poses(positions=jit)
        pills.set_velocities(torch.zeros((N * NPILL, 6), device="cuda"))

        for _ in range(a.settle):
            world.step(render=False)

        frame = read_frames()                                   # (N,16,16) N
        frame = frame + rng.normal(0, NOISE, frame.shape)
        frame = np.clip(frame, 0, None).astype(np.float32)
        # integrate per-pill pressure
        pp = np.zeros((N, NPILL), np.float32)
        for (r, c), k in cell_to_pill.items():
            pp[:, k] += frame[:, r, c]

        frames_all.append(frame); press_all.append(pp); lab_all.append(labels)
        done += N * NPILL
        batch += 1
        print(f"  batch {batch}: {done}/{a.pills} pills "
              f"(good~{frame[labels==0].mean() if (labels==0).any() else 0:.2f})")

    frames = np.concatenate(frames_all)[: a.pills // NPILL + 1]
    press = np.concatenate(press_all)[: len(frames)]
    lab = np.concatenate(lab_all)[: len(frames)]

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    np.savez_compressed(a.out, frames=frames, pill_pressure=press, pill_label=lab,
                        pill_centers=np.array(centers, np.float32))
    gp = press[lab == 0]; vp = press[lab == 1]
    print(f"[dataset] {frames.shape[0]} trays, {lab.size} pills "
          f"({int(lab.sum())} void) -> {a.out}")
    print(f"[dataset] good {gp.mean():.3f}+/-{gp.std():.3f}  void {vp.mean():.3f}+/-{vp.std():.3f}")

    sim_app.close()

    if a.report:
        import importlib
        sys.path.insert(0, HERE)
        detect = importlib.import_module("detect")
        detect.report(a.out)


if __name__ == "__main__":
    main()
