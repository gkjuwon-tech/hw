"""Full digital-twin scene + offscreen render (MuJoCo, headless OSMesa).

A to-scale conveyor line: belt + end rollers + guide rails + legs, a 16x16
compliant tactile-mesh sensor at the inspection station, a real-spec part
resting on it, and our actual 3D-printed Tactile Edge enclosure (imported
from edge_enclosure.scad) on a stand beside the belt. Dimensions come from
sim/specs.py (repo + datasheets), not eyeballing.

Run:
  OPENSCAD=/path/to/openscad MUJOCO_GL=osmesa python3 sim/scene.py
  (OPENSCAD optional — without it the Edge box is omitted from the picture.)
"""

from __future__ import annotations

import os, subprocess, tempfile
import numpy as np
import mujoco
from PIL import Image

import sim.specs as S
from sim import tactile_twin as tw

OUT = os.environ.get("SCENE_OUT", "/tmp/svgprev/twin_scene.png")
BODY_STL  = os.environ.get("EDGE_BODY_STL",  "/tmp/edge_body.stl")
BEZEL_STL = os.environ.get("EDGE_BEZEL_STL", "/tmp/edge_bezel.stl")

BELT_TOP    = -S.MESH_THICK
BELT_CZ     = BELT_TOP - S.BELT_THICK / 2
BELT_BOTTOM = BELT_CZ - S.BELT_THICK / 2
FLOOR_Z     = -0.36


def _ensure_binary_stl(path):
    """MuJoCo only reads binary STL; OpenSCAD writes ASCII. Convert in place."""
    import re, struct
    with open(path, "rb") as f:
        if f.read(5) != b"solid":
            return                       # already binary
    txt = open(path, "r", errors="ignore").read()
    if "facet normal" not in txt:
        return
    vs = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", txt)
    ns = re.findall(r"facet normal\s+(\S+)\s+(\S+)\s+(\S+)", txt)
    nfac = len(vs) // 3
    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", nfac))
        for k in range(nfac):
            nx, ny, nz = ns[k] if k < len(ns) else ("0", "0", "0")
            f.write(struct.pack("<3f", float(nx), float(ny), float(nz)))
            for j in range(3):
                x, y, z = vs[3 * k + j]
                f.write(struct.pack("<3f", float(x), float(y), float(z)))
            f.write(struct.pack("<H", 0))


def _maybe_export_enclosure():
    """Export body/bezel STL from the .scad if OPENSCAD is available."""
    osc = os.environ.get("OPENSCAD")
    scad = os.path.join(os.path.dirname(__file__), "..", "hardware", "edge_enclosure", "edge_enclosure.scad")
    scad = os.path.abspath(scad)
    if osc and os.path.exists(scad):
        for part, dst in (("body", BODY_STL), ("bezel", BEZEL_STL)):
            if not os.path.exists(dst):
                subprocess.run([osc, "-o", dst, "-D", f'part="{part}"', scad], check=True)
    ok = os.path.exists(BODY_STL) and os.path.exists(BEZEL_STL)
    if ok:
        _ensure_binary_stl(BODY_STL); _ensure_binary_stl(BEZEL_STL)
    return ok


def build_scene(height_map: np.ndarray) -> mujoco.MjModel:
    rows, cols = height_map.shape
    xy = tw._grid_xy(rows, cols)
    have_box = _maybe_export_enclosure()

    taxels, feet = [], []
    for r in range(rows):
        for c in range(cols):
            x, y = xy(r, c)
            taxels.append(
                f'<body name="tb_{r}_{c}" pos="{x:.5f} {y:.5f} 0">'
                f'<joint name="j_{r}_{c}" type="slide" axis="0 0 1" stiffness="{tw.TAXEL_K}" '
                f'damping="{tw.TAXEL_D}" springref="0" range="-0.05 0.02" limited="true"/>'
                f'<geom name="t_{r}_{c}" type="box" pos="0 0 {-tw.TAXEL_HZ:.5f}" '
                f'size="{tw.CELL_HALF} {tw.CELL_HALF} {tw.TAXEL_HZ}" contype="1" conaffinity="2" '
                f'mass="0.004" material="mesh"/></body>'
            )
            off = float(height_map[r, c]); fz = off + tw.FOOT_HZ
            feet.append(
                f'<geom name="f_{r}_{c}" type="box" pos="{x:.5f} {y:.5f} {fz:.5f}" '
                f'size="{tw.CELL_HALF*0.92} {tw.CELL_HALF*0.92} {tw.FOOT_HZ}" '
                f'contype="2" conaffinity="1" mass="0.001" group="3"/>'
            )

    # the inspected part rides on the object body (the feet height-map), with a
    # visible "loaf" shell on top so the render reads as a real part.
    part_shell = (
        f'<geom name="part" type="box" pos="0 0 {2*tw.FOOT_HZ + S.PART_H/2:.4f}" '
        f'size="{S.PART_W/2} {S.PART_D/2} {S.PART_H/2}" mass="{S.PART_MASS}" '
        f'contype="0" conaffinity="0" material="part"/>'
    )

    # ── conveyor decor (visual only) ──
    hx, hy = S.BELT_LENGTH/2, S.BELT_WIDTH/2
    decor = [
        f'<geom type="box" pos="0 0 {BELT_CZ:.4f}" size="{hx} {hy} {S.BELT_THICK/2}" material="belt" contype="0" conaffinity="0"/>',
        f'<geom type="cylinder" fromto="{-hx:.3f} {-hy-0.005:.3f} {BELT_TOP-S.ROLLER_DIA/2:.4f} {-hx:.3f} {hy+0.005:.3f} {BELT_TOP-S.ROLLER_DIA/2:.4f}" size="{S.ROLLER_DIA/2}" material="metal" contype="0" conaffinity="0"/>',
        f'<geom type="cylinder" fromto="{hx:.3f} {-hy-0.005:.3f} {BELT_TOP-S.ROLLER_DIA/2:.4f} {hx:.3f} {hy+0.005:.3f} {BELT_TOP-S.ROLLER_DIA/2:.4f}" size="{S.ROLLER_DIA/2}" material="metal" contype="0" conaffinity="0"/>',
        f'<geom type="box" pos="0 {hy+0.006:.3f} {BELT_TOP+S.RAIL_H/2:.4f}" size="{hx} 0.006 {S.RAIL_H/2}" material="metal" contype="0" conaffinity="0"/>',
        f'<geom type="box" pos="0 {-(hy+0.006):.3f} {BELT_TOP+S.RAIL_H/2:.4f}" size="{hx} 0.006 {S.RAIL_H/2}" material="metal" contype="0" conaffinity="0"/>',
    ]
    legh = BELT_BOTTOM - FLOOR_Z
    for lx in (-hx+0.05, hx-0.05):
        for ly in (-hy+0.02, hy-0.02):
            decor.append(f'<geom type="box" pos="{lx:.3f} {ly:.3f} {FLOOR_Z+legh/2:.4f}" size="0.012 0.012 {legh/2:.4f}" material="metal" contype="0" conaffinity="0"/>')

    # ── Edge box on a stand beside the belt (our enclosure STL) ──
    box_assets, box_geoms = "", ""
    if have_box:
        bx, by = hx - 0.18, -(hy + 0.16)          # front-right of the belt
        post_h = -FLOOR_Z + BELT_TOP
        box_assets = (
            f'<mesh name="edge_body" file="{BODY_STL}" scale="0.001 0.001 0.001"/>'
            f'<mesh name="edge_bezel" file="{BEZEL_STL}" scale="0.001 0.001 0.001"/>'
        )
        # reclined ~20deg, screen (+z of the enclosure) facing up/back toward camera
        box_geoms = (
            f'<geom type="box" pos="{bx:.3f} {by:.3f} {FLOOR_Z+post_h/2:.4f}" size="0.03 0.03 {post_h/2:.4f}" material="metal" contype="0" conaffinity="0"/>'
            f'<body name="edgebox" pos="{bx:.3f} {by:.3f} {BELT_TOP+0.02:.4f}" euler="-70 0 0">'
            f'<geom type="mesh" mesh="edge_body" material="graphite" contype="0" conaffinity="0"/>'
            f'<geom type="mesh" mesh="edge_bezel" pos="0 0 0.064" material="alu" contype="0" conaffinity="0"/>'
            f'<geom type="box" pos="0 0 0.067" size="{S.DISP_ACT_W/2} {S.DISP_ACT_H/2} 0.001" material="screen" contype="0" conaffinity="0"/>'
            f'</body>'
        )

    xml = f"""
<mujoco model="twin_scene">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <visual>
    <global offwidth="1280" offheight="960"/>
    <quality shadowsize="4096"/>
    <headlight ambient="0.35 0.35 0.38" diffuse="0.5 0.5 0.5" specular="0.2 0.2 0.2"/>
    <map fogstart="3" fogend="6"/>
  </visual>
  <asset>
    <texture type="skybox" builtin="gradient" rgb1="0.13 0.15 0.2" rgb2="0.02 0.02 0.03" width="64" height="64"/>
    <material name="floor"    rgba="0.10 0.11 0.13 1" reflectance="0.05"/>
    <material name="belt"     rgba="0.07 0.07 0.08 1" reflectance="0.02"/>
    <material name="metal"    rgba="0.55 0.57 0.60 1" reflectance="0.3" specular="0.6" shininess="0.6"/>
    <material name="mesh"     rgba="0.10 0.40 0.28 1" reflectance="0.05"/>
    <material name="part"     rgba="0.82 0.66 0.42 1" reflectance="0.02"/>
    <material name="graphite" rgba="0.10 0.11 0.13 1" reflectance="0.05" specular="0.3"/>
    <material name="alu"      rgba="0.62 0.64 0.67 1" reflectance="0.4" specular="0.7" shininess="0.7"/>
    <material name="screen"   rgba="0.05 0.5 0.3 1" emission="0.6"/>
    {box_assets}
  </asset>
  <worldbody>
    <light directional="true" diffuse="0.7 0.7 0.7" specular="0.3 0.3 0.3" pos="0.6 -0.6 1.2" dir="-0.5 0.5 -1"/>
    <light directional="true" diffuse="0.3 0.3 0.35" pos="-0.8 0.4 0.8" dir="0.6 -0.3 -1"/>
    <geom name="floor" type="plane" pos="0 0 {FLOOR_Z:.3f}" size="3 3 0.1" material="floor"/>
    {''.join(decor)}
    {box_geoms}
    {''.join(taxels)}
    <body name="object" pos="0 0 {tw.START_GAP}">
      <joint name="press" type="slide" axis="0 0 1" damping="2"/>
      {''.join(feet)}
      {part_shell}
    </body>
  </worldbody>
</mujoco>
"""
    return mujoco.MjModel.from_xml_string(xml)


def part_base(rows=S.MESH_ROWS, cols=S.MESH_COLS, w=S.PART_W, d=S.PART_D,
              cx=0.0, cy=0.0, recess=0.02, noise=0.00005):
    """Height map for a part of footprint w x d centred at (cx, cy): cells under
    the part contact (≈0), cells outside are recessed so only the real footprint
    presses the mesh."""
    hm = np.full((rows, cols), recess)
    xy = tw._grid_xy(rows, cols)
    for r in range(rows):
        for c in range(cols):
            x, y = xy(r, c)
            if abs(x - cx) <= w / 2 and abs(y - cy) <= d / 2:
                hm[r, c] = abs(np.random.normal(0, noise))
    return hm


def render(height_map: np.ndarray, az=48, el=-22, dist=0.95, lookat=(0.0, 0.0, -0.02)):
    m = build_scene(height_map)
    d = mujoco.MjData(m)
    for _ in range(tw.SETTLE):
        mujoco.mj_step(m, d)
    cam = mujoco.MjvCamera()
    cam.lookat[:] = lookat
    cam.distance, cam.azimuth, cam.elevation = dist, az, el
    opt = mujoco.MjvOption()
    opt.geomgroup[3] = 0          # hide the contact "feet" (group 3)
    r = mujoco.Renderer(m, 960, 1280)
    r.update_scene(d, cam, scene_option=opt)
    img = r.render()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    Image.fromarray(img).save(OUT)
    pressure = tw.read_pressure(m, d, *height_map.shape)
    return img, pressure


if __name__ == "__main__":
    np.random.seed(1)
    img, pressure = render(part_base())
    print("scene rendered ->", OUT, img.shape)
    print(f"part on mesh: total load={pressure.sum():.1f} N, active cells={int((pressure>0.05).sum())}/{pressure.size}")
