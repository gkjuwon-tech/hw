"""Tactile inspection — physics digital twin (MuJoCo).

Why this exists: we can't buy enough hardware, so we *simulate* the tactile
sensor in a real physics engine and read the contact forces. The output is
deliberately the SAME shape the physical scanner produces — an R x C frame
of per-cell pressure (see edge_agent / backend `inspect`) — so synthetic and
real data are interchangeable. Swap MuJoCo for Isaac Sim later on an RTX box
without touching the rest of the pipeline.

Model:
  * sensor  = an R x C grid of small *compliant* taxel geoms, tops coplanar
              at z = 0 (soft contact so pressure spreads between cells, like
              a real piezoresistive mat — not a janky point contact).
  * object  = a rigid body on a vertical slide joint, built from an R x C
              field of little "feet" at parametric heights (a height map).
              A heavy top plate presses it straight down under gravity.
  * read    = sum the normal contact force landing on each taxel -> one frame.

Run:  python3 sim/tactile_twin.py
"""

from __future__ import annotations

import numpy as np
import mujoco

PITCH      = 0.010    # cell-to-cell spacing (m) -> 10 mm taxels
CELL_HALF  = 0.0046   # taxel/foot half-width (m)
TAXEL_HZ   = 0.005    # taxel half-height
FOOT_HZ    = 0.004    # foot half-height
START_GAP  = 0.001    # initial gap between nominal feet and taxel tops
PRESS_MASS = 6.0      # top-plate mass (kg) -> the pressing load
SETTLE     = 1400     # physics steps to settle
TAXEL_K    = 400.0    # per-taxel spring stiffness (N/m) — the "compliance"
TAXEL_D    = 4.0      # per-taxel spring damping


def _grid_xy(rows: int, cols: int):
    """Centred (x, y) for cell (r, c)."""
    x0 = -(cols - 1) * PITCH / 2
    y0 = -(rows - 1) * PITCH / 2
    return lambda r, c: (x0 + c * PITCH, y0 + r * PITCH)


def build_model(height_map: np.ndarray) -> mujoco.MjModel:
    """Compile a sensor+object model. `height_map[r,c]` is the foot bottom
    offset (m): 0 = touches, >0 = recessed (cold), <0 = protrudes (hot)."""
    rows, cols = height_map.shape
    xy = _grid_xy(rows, cols)

    taxels, feet = [], []
    for r in range(rows):
        for c in range(cols):
            x, y = xy(r, c)
            # each taxel is its own sprung slider (a bed-of-springs / Winkler
            # foundation) so load spreads across the contact patch like a real
            # compliant pressure mat — not a rigid 3-point balance.
            taxels.append(
                f'<body name="tb_{r}_{c}" pos="{x:.5f} {y:.5f} 0">'
                f'<joint name="j_{r}_{c}" type="slide" axis="0 0 1" '
                f'stiffness="{TAXEL_K}" damping="{TAXEL_D}" springref="0" '
                f'range="-0.05 0.02" limited="true"/>'
                f'<geom name="t_{r}_{c}" type="box" pos="0 0 {-TAXEL_HZ:.5f}" '
                f'size="{CELL_HALF} {CELL_HALF} {TAXEL_HZ}" contype="1" conaffinity="2" '
                f'mass="0.004" rgba="0.2 0.6 0.3 1"/>'
                f'</body>'
            )
            off = float(height_map[r, c])
            # foot local z so its bottom sits at `off` when the body is at START_GAP
            fz = off + FOOT_HZ
            feet.append(
                f'<geom name="f_{r}_{c}" type="box" pos="{x:.5f} {y:.5f} {fz:.5f}" '
                f'size="{CELL_HALF*0.92} {CELL_HALF*0.92} {FOOT_HZ}" contype="2" conaffinity="1" '
                f'mass="0.001" rgba="0.6 0.6 0.7 1"/>'
            )

    plate_z = 0.02
    xml = f"""
<mujoco model="tactile_twin">
  <option timestep="0.002" gravity="0 0 -9.81" cone="elliptic" integrator="implicitfast"/>
  <default>
    <geom friction="0.6 0.01 0.001" solref="0.01 1" solimp="0.9 0.97 0.001"/>
  </default>
  <worldbody>
    {''.join(taxels)}
    <body name="object" pos="0 0 {START_GAP}">
      <joint name="press" type="slide" axis="0 0 1" damping="2"/>
      {''.join(feet)}
      <geom name="plate" type="box" pos="0 0 {plate_z}" size="{cols*PITCH/2} {rows*PITCH/2} 0.01"
            mass="{PRESS_MASS}" contype="0" conaffinity="0" rgba="0.3 0.3 0.35 1"/>
    </body>
  </worldbody>
</mujoco>
"""
    return mujoco.MjModel.from_xml_string(xml)


def read_pressure(m: mujoco.MjModel, d: mujoco.MjData, rows: int, cols: int) -> np.ndarray:
    """Per-taxel spring force (N) = how hard each cell is pressed = pressure."""
    frame = np.zeros((rows, cols), dtype=np.float64)
    for r in range(rows):
        for c in range(cols):
            jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, f"j_{r}_{c}")
            q = d.qpos[m.jnt_qposadr[jid]]   # negative when compressed
            frame[r, c] = max(0.0, -TAXEL_K * q)
    return frame


def press(height_map: np.ndarray) -> np.ndarray:
    """Build, press the object down, settle, and return the pressure frame."""
    rows, cols = height_map.shape
    m = build_model(height_map)
    d = mujoco.MjData(m)
    for _ in range(SETTLE):
        mujoco.mj_step(m, d)
    return read_pressure(m, d, rows, cols)


# ── object / defect generators (height maps; 0 = full contact) ───────────

def nominal(rows=16, cols=16, noise=0.00005):
    return np.abs(np.random.normal(0, noise, (rows, cols)))

def missing_corner(rows=16, cols=16, frac=0.30):
    hm = nominal(rows, cols)
    rr, cc = int(rows * frac), int(cols * frac)
    hm[:rr, :cc] += 0.02            # lift a corner clear of the taxels -> cold
    return hm

def foreign_object(rows=16, cols=16):
    hm = nominal(rows, cols)
    r, c = rows // 2, cols // 2
    hm[r, c] -= 0.0010              # a hard pellet protruding -> hotspot
    return hm

def dent(rows=16, cols=16, rad=2.5):
    hm = nominal(rows, cols)
    cy, cx = rows / 2, cols / 2
    for r in range(rows):
        for c in range(cols):
            if (r - cy) ** 2 + (c - cx) ** 2 <= rad ** 2:
                hm[r, c] += 0.004   # a recessed cavity -> cold patch
    return hm


# ── pretty-print (text only) ─────────────────────────────────────────────

def ascii_map(frame: np.ndarray) -> str:
    glyphs = " .:-=+*#%@"
    mx = frame.max() or 1.0
    out = []
    for row in frame:
        line = "".join(glyphs[min(len(glyphs) - 1, int(v / mx * (len(glyphs) - 1)))] for v in row)
        out.append(line)
    return "\n".join(out)


if __name__ == "__main__":
    np.random.seed(0)
    for name, hm in [
        ("NOMINAL (good part)", nominal()),
        ("MISSING CORNER", missing_corner()),
        ("FOREIGN OBJECT (pellet)", foreign_object()),
        ("DENT (centre cavity)", dent()),
    ]:
        f = press(hm)
        print(f"\n=== {name} ===  total load={f.sum():.1f} N, active cells={int((f>0.05).sum())}/{f.size}")
        print(ascii_map(f))
