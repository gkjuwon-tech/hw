"""Digital-twin dataset + defect-detection metrics (MuJoCo, CPU, no AI).

The money question: does the tactile mat actually catch a pill with an
internal void — the defect a camera CAN'T see? We answer it with physics,
not vibes.

Model: a tray of pills rests on the 16x16 compliant tactile mesh under its
own weight. A pill with a sealed internal cavity is *lighter* (same outside,
a camera sees nothing), so it presses its patch of the mesh less hard. We
read each pill's integrated pressure and flag the light ones with a plain
statistical detector (z-score vs the good-pill baseline) — the same kind of
anomaly test the backend uses. No neural net; this runs on CPU.

Outputs:
  * sim/dataset/tactile_pills.npz  — labelled frames + per-pill pressures
  * printed metrics                — ROC-AUC, accuracy / precision / recall

Run:  python3 sim/generate_dataset.py [n_frames]
"""

from __future__ import annotations

import os, sys
import numpy as np
import mujoco

from sim.tactile_twin import TAXEL_K, TAXEL_D, CELL_HALF, TAXEL_HZ, PITCH, _grid_xy

ROWS = COLS = 16
PILL_N = 4                 # 4x4 = 16 pills per tray
PILL_R = 0.013             # tablet radius (m)
PILL_H = 0.006             # tablet thickness
SPACING = 0.036            # pill-to-pill spacing
START_Z = 0.012            # pills start just above the mesh, then settle
M0 = 0.08                  # nominal pill mass (kg)
GOOD_JITTER = 0.04         # +/- 4% mass spread on good pills
VOID_RANGE = (0.55, 0.78)  # void pill keeps 55-78% of nominal mass
P_VOID = 0.25              # fraction of pills that are void
CELL_NOISE = 0.012         # per-cell sensor noise (N)
SETTLE = 600


def _pill_centers():
    o = -(PILL_N - 1) * SPACING / 2
    return [(o + i * SPACING, o + j * SPACING) for i in range(PILL_N) for j in range(PILL_N)]


def _build_xml():
    xy = _grid_xy(ROWS, COLS)
    taxels = []
    for r in range(ROWS):
        for c in range(COLS):
            x, y = xy(r, c)
            taxels.append(
                f'<body name="tb_{r}_{c}" pos="{x:.5f} {y:.5f} 0">'
                f'<joint name="j_{r}_{c}" type="slide" axis="0 0 1" stiffness="{TAXEL_K}" '
                f'damping="{TAXEL_D}" springref="0" range="-0.05 0.02" limited="true"/>'
                f'<geom type="box" pos="0 0 {-TAXEL_HZ:.5f}" size="{CELL_HALF} {CELL_HALF} {TAXEL_HZ}" '
                f'contype="1" conaffinity="2" mass="0.004"/></body>'
            )
    pills = []
    for k, (px, py) in enumerate(_pill_centers()):
        pills.append(
            f'<body name="pill_{k}" pos="{px:.5f} {py:.5f} {START_Z}">'
            f'<freejoint/>'
            f'<geom name="pg_{k}" type="cylinder" size="{PILL_R} {PILL_H/2}" '
            f'contype="2" conaffinity="1" mass="{M0}" friction="0.7 0.01 0.001"/></body>'
        )
    return f"""
<mujoco model="pill_tray">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <default><geom solref="0.01 1" solimp="0.9 0.97 0.001"/></default>
  <worldbody>{''.join(taxels)}{''.join(pills)}</worldbody>
</mujoco>
"""


class TrayTwin:
    """Compile once; vary pill masses per sample (no recompile)."""

    def __init__(self):
        self.m = mujoco.MjModel.from_xml_string(_build_xml())
        self.d = mujoco.MjData(self.m)
        nid = lambda t, n: mujoco.mj_name2id(self.m, t, n)
        self.jadr = {(r, c): self.m.jnt_qposadr[nid(mujoco.mjtObj.mjOBJ_JOINT, f"j_{r}_{c}")]
                     for r in range(ROWS) for c in range(COLS)}
        self.pill_bid = [nid(mujoco.mjtObj.mjOBJ_BODY, f"pill_{k}") for k in range(PILL_N * PILL_N)]
        self.base_mass = float(self.m.body_mass[self.pill_bid[0]])
        self.base_inertia = self.m.body_inertia[self.pill_bid[0]].copy()
        # which mesh cells belong to which pill (nearest centre within radius)
        xy = _grid_xy(ROWS, COLS)
        self.centers = _pill_centers()
        self.cell_to_pill = {}
        for r in range(ROWS):
            for c in range(COLS):
                x, y = xy(r, c)
                for k, (px, py) in enumerate(self.centers):
                    if (x - px) ** 2 + (y - py) ** 2 <= (PILL_R * 1.25) ** 2:
                        self.cell_to_pill[(r, c)] = k
                        break

    def sample(self, masses):
        mujoco.mj_resetData(self.m, self.d)
        for bid, mass in zip(self.pill_bid, masses):
            self.m.body_mass[bid] = mass
            self.m.body_inertia[bid] = self.base_inertia * (mass / self.base_mass)
        mujoco.mj_forward(self.m, self.d)
        for _ in range(SETTLE):
            mujoco.mj_step(self.m, self.d)
        frame = np.zeros((ROWS, COLS))
        for (r, c), adr in self.jadr.items():
            frame[r, c] = max(0.0, -TAXEL_K * self.d.qpos[adr])
        frame += np.random.normal(0, CELL_NOISE, frame.shape)
        frame = np.clip(frame, 0, None)
        pill_p = np.zeros(PILL_N * PILL_N)
        for (r, c), k in self.cell_to_pill.items():
            pill_p[k] += frame[r, c]
        return frame, pill_p


def generate(n_frames):
    twin = TrayTwin()
    npill = PILL_N * PILL_N
    frames, pill_press, pill_lab = [], [], []
    for f in range(n_frames):
        masses, labels = [], []
        for _ in range(npill):
            if np.random.random() < P_VOID:
                masses.append(M0 * np.random.uniform(*VOID_RANGE)); labels.append(1)
            else:
                masses.append(M0 * (1 + np.random.uniform(-GOOD_JITTER, GOOD_JITTER))); labels.append(0)
        frame, pp = twin.sample(masses)
        frames.append(frame); pill_press.append(pp); pill_lab.append(labels)
        if (f + 1) % 50 == 0:
            print(f"  ...{f+1}/{n_frames} trays")
    return (np.array(frames, np.float32),
            np.array(pill_press, np.float32),
            np.array(pill_lab, np.int8))


def metrics(pill_press, pill_lab):
    p = pill_press.ravel().astype(float)
    y = pill_lab.ravel().astype(int)
    # calibrate the good-pill baseline on HALF the good pills (held out from scoring)
    good_idx = np.where(y == 0)[0]
    rng = np.random.default_rng(0); rng.shuffle(good_idx)
    cal = good_idx[: len(good_idx) // 2]
    test = np.setdiff1d(np.arange(len(y)), cal)
    mu, sigma = p[cal].mean(), p[cal].std()
    score = (mu - p) / sigma                 # high score = pressure deficit = likely void
    s, yt = score[test], y[test]
    # ROC-AUC (rank-based)
    order = np.argsort(s); ranks = np.empty_like(order, float); ranks[order] = np.arange(len(s))
    npos, nneg = yt.sum(), (yt == 0).sum()
    auc = (ranks[yt == 1].sum() - npos * (npos - 1) / 2) / (npos * nneg)
    # best threshold by Youden's J
    best = None
    for thr in np.linspace(s.min(), s.max(), 200):
        pred = s >= thr
        tp = int((pred & (yt == 1)).sum()); fp = int((pred & (yt == 0)).sum())
        fn = int((~pred & (yt == 1)).sum()); tn = int((~pred & (yt == 0)).sum())
        tpr = tp / max(tp + fn, 1); fpr = fp / max(fp + tn, 1)
        j = tpr - fpr
        if best is None or j > best[0]:
            best = (j, thr, tp, fp, fn, tn)
    _, thr, tp, fp, fn, tn = best
    acc = (tp + tn) / (tp + fp + fn + tn)
    prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    return dict(auc=auc, acc=acc, prec=prec, rec=rec, f1=f1, thr=thr,
                tp=tp, fp=fp, fn=fn, tn=tn, n=len(yt), pos=int(npos), mu=mu, sigma=sigma)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    np.random.seed(7)
    print(f"generating {n} trays x {PILL_N*PILL_N} pills on the tactile twin...")
    frames, pill_press, pill_lab = generate(n)
    npill_total = pill_lab.size
    nvoid = int(pill_lab.sum())
    out = os.path.join(os.path.dirname(__file__), "dataset")
    os.makedirs(out, exist_ok=True)
    np.savez_compressed(os.path.join(out, "tactile_pills.npz"),
                        frames=frames, pill_pressure=pill_press, pill_label=pill_lab,
                        pill_centers=np.array(TrayTwin().centers))
    M = metrics(pill_press, pill_lab)
    gp = pill_press[pill_lab == 0]; vp = pill_press[pill_lab == 1]
    print("\n================ TACTILE VOID-DETECTION (digital twin) ================")
    print(f" dataset: {frames.shape[0]} trays, {npill_total} pills ({nvoid} void / {npill_total-nvoid} good)")
    print(f" good-pill pressure : {gp.mean():.2f} +/- {gp.std():.2f} N")
    print(f" void-pill pressure : {vp.mean():.2f} +/- {vp.std():.2f} N  (lighter -> lower)")
    print(f" ROC-AUC            : {M['auc']*100:.1f}%")
    print(f" accuracy           : {M['acc']*100:.1f}%   precision {M['prec']*100:.1f}%   recall {M['rec']*100:.1f}%   F1 {M['f1']*100:.1f}%")
    print(f" confusion (test n={M['n']}): TP={M['tp']} FP={M['fp']} FN={M['fn']} TN={M['tn']}")
    print(" saved -> sim/dataset/tactile_pills.npz")
    print("=======================================================================")
