"""Full-fidelity digital-twin scene in Isaac Sim — the real Conet Tactile line.

Reproduces the physical inspection station to scale from `sim/specs.py` (the
single source of truth) and imports the *actual* 3D-printed Edge enclosure CAD
(`hardware/edge_enclosure/edge_enclosure.scad`, exported to STL via OpenSCAD):

  - 350 mm conveyor: belt + end rollers + side guide-rails + legs
  - 16x16 Velostat tactile mesh at the inspection station (top at z=0)
  - tablets/pills riding the belt onto the mesh
  - the Tactile Edge appliance on a VESA stand beside the belt: the real
    enclosure body + chamfered bezel, an emissive kiosk screen, the Jetson
    Orin Nano dev kit tucked inside
  - the scanner PCB at the mesh edge

Renders a hero RTX shot headless to sim/isaac/out/twin_scene.png.

Run (inside the isaac venv on the GPU pod):
  python sim/isaac/scene.py
"""
from __future__ import annotations

import os
import struct

# Boot Kit headless with the ray-traced renderer BEFORE any omni/* import.
from isaacsim import SimulationApp

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
ASSETS = os.path.join(HERE, "assets")
os.makedirs(OUT, exist_ok=True)
os.makedirs(ASSETS, exist_ok=True)

_W, _H = 1600, 1000
sim_app = SimulationApp({"headless": True, "renderer": "RayTracedLighting",
                         "width": _W, "height": _H})

import sys
sys.path.insert(0, REPO)
import numpy as np
import omni.replicator.core as rep
from pxr import Usd, UsdGeom, UsdShade, UsdLux, Gf, Sdf
from PIL import Image

import sim.specs as S

BELT_TOP    = -S.MESH_THICK
BELT_CZ     = BELT_TOP - S.BELT_THICK / 2
BELT_BOTTOM = BELT_CZ - S.BELT_THICK / 2
FLOOR_Z     = -0.36


# ── enclosure STL (export from the .scad if missing) ─────────────────────

def _ensure_enclosure_stl():
    body = os.path.join(ASSETS, "edge_body.stl")
    bezel = os.path.join(ASSETS, "edge_bezel.stl")
    scad = os.path.join(REPO, "hardware", "edge_enclosure", "edge_enclosure.scad")
    osc = os.environ.get("OPENSCAD") or "openscad"
    import shutil, subprocess
    if not shutil.which(osc):
        return (None, None)
    for part, dst in (("body", body), ("bezel", bezel)):
        if not os.path.exists(dst):
            subprocess.run([osc, "-o", dst, "-D", f'part="{part}"', scad], check=True)
    return (body, bezel)


def _read_stl(path):
    """Return (points Nx3, faceVertexIndices flat) for an ASCII or binary STL."""
    with open(path, "rb") as f:
        head = f.read(5)
    if head == b"solid":
        verts = []
        with open(path, "r", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("vertex"):
                    _, x, y, z = line.split()
                    verts.append((float(x), float(y), float(z)))
        pts = np.array(verts, dtype=np.float32)
    else:
        with open(path, "rb") as f:
            f.read(80)
            (n,) = struct.unpack("<I", f.read(4))
            pts = np.empty((n * 3, 3), dtype=np.float32)
            for i in range(n):
                f.read(12)                       # normal
                for j in range(3):
                    pts[i * 3 + j] = struct.unpack("<3f", f.read(12))
                f.read(2)                         # attr byte count
    idx = np.arange(len(pts), dtype=np.int32)
    return pts, idx


# ── material + primitive helpers ─────────────────────────────────────────

def _mat(stage, path, diffuse, metallic=0.0, rough=0.5, emissive=None):
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/PBR")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*diffuse))
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    if emissive is not None:
        sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emissive))
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def _bind(prim, mat):
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat)


def _box(stage, path, dims, pos, mat, euler=None):
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    xf = UsdGeom.Xformable(cube)
    xf.AddTranslateOp().Set(Gf.Vec3d(*pos))
    if euler is not None:
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*euler))
    xf.AddScaleOp().Set(Gf.Vec3f(*dims))
    _bind(cube.GetPrim(), mat)
    return cube


def _cyl(stage, path, radius, height, pos, mat, axis="Z", euler=None):
    cyl = UsdGeom.Cylinder.Define(stage, path)
    cyl.CreateRadiusAttr(radius)
    cyl.CreateHeightAttr(height)
    cyl.CreateAxisAttr(axis)
    xf = UsdGeom.Xformable(cyl)
    xf.AddTranslateOp().Set(Gf.Vec3d(*pos))
    if euler is not None:
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*euler))
    _bind(cyl.GetPrim(), mat)
    return cyl


def _mesh(stage, path, pts, idx, pos, scale, mat, euler=None):
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr([Gf.Vec3f(*p) for p in pts])
    m.CreateFaceVertexIndicesAttr(idx.tolist())
    m.CreateFaceVertexCountsAttr([3] * (len(idx) // 3))
    m.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    xf = UsdGeom.Xformable(m)
    xf.AddTranslateOp().Set(Gf.Vec3d(*pos))
    if euler is not None:
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*euler))
    xf.AddScaleOp().Set(Gf.Vec3f(scale, scale, scale))
    _bind(m.GetPrim(), mat)
    return m


# ── scene construction ───────────────────────────────────────────────────

def build(stage):
    root = "/World"
    UsdGeom.Xform.Define(stage, root)

    M = dict(
        floor=_mat(stage, root + "/M/floor", (0.10, 0.11, 0.13), 0.0, 0.6),
        belt=_mat(stage, root + "/M/belt", (0.05, 0.05, 0.06), 0.0, 0.7),
        metal=_mat(stage, root + "/M/metal", (0.55, 0.57, 0.60), 0.9, 0.35),
        mesh=_mat(stage, root + "/M/mesh", (0.08, 0.34, 0.24), 0.0, 0.55),
        pill=_mat(stage, root + "/M/pill", (0.88, 0.84, 0.74), 0.0, 0.45),
        graphite=_mat(stage, root + "/M/graphite", (0.03, 0.032, 0.038), 0.1, 0.45),
        alu=_mat(stage, root + "/M/alu", (0.66, 0.685, 0.71), 1.0, 0.24),
        screen=_mat(stage, root + "/M/screen", (0.02, 0.06, 0.04), 0.0, 0.1,
                    emissive=(0.05, 0.55, 0.30)),
        pcb=_mat(stage, root + "/M/pcb", (0.07, 0.30, 0.16), 0.2, 0.5),
    )

    # floor
    plane = UsdGeom.Mesh.Define(stage, root + "/floor")
    s = 3.0
    plane.CreatePointsAttr([Gf.Vec3f(-s, -s, FLOOR_Z), Gf.Vec3f(s, -s, FLOOR_Z),
                            Gf.Vec3f(s, s, FLOOR_Z), Gf.Vec3f(-s, s, FLOOR_Z)])
    plane.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    plane.CreateFaceVertexCountsAttr([4])
    _bind(plane.GetPrim(), M["floor"])

    hx, hy = S.BELT_LENGTH / 2, S.BELT_WIDTH / 2

    # conveyor belt + rollers + rails + legs
    _box(stage, root + "/belt", (S.BELT_LENGTH, S.BELT_WIDTH, S.BELT_THICK),
         (0, 0, BELT_CZ), M["belt"])
    for sx in (-1, 1):
        _cyl(stage, f"{root}/roller_{sx}", S.ROLLER_DIA / 2, S.BELT_WIDTH + 0.02,
             (sx * hx, 0, BELT_TOP - S.ROLLER_DIA / 2), M["metal"], axis="Y")
    for sy in (-1, 1):
        _box(stage, f"{root}/rail_{sy}", (S.BELT_LENGTH, 0.012, S.RAIL_H),
             (0, sy * (hy + 0.006), BELT_TOP + S.RAIL_H / 2), M["metal"])
    legh = BELT_BOTTOM - FLOOR_Z
    for lx in (-hx + 0.05, hx - 0.05):
        for ly in (-hy + 0.02, hy - 0.02):
            _box(stage, f"{root}/leg_{lx:.2f}_{ly:.2f}".replace("-", "n").replace(".", "_"),
                 (0.024, 0.024, legh), (lx, ly, FLOOR_Z + legh / 2), M["metal"])

    # tactile mesh pad + 16x16 cell grid (the sensor face, top at z=0)
    _box(stage, root + "/mesh_pad", (S.MESH_W, S.MESH_H, S.MESH_THICK),
         (0, 0, -S.MESH_THICK / 2), M["mesh"])
    cell = S.CELL_PITCH
    for r in range(S.MESH_ROWS):
        for c in range(S.MESH_COLS):
            x = -(S.MESH_COLS - 1) * cell / 2 + c * cell
            y = -(S.MESH_ROWS - 1) * cell / 2 + r * cell
            _box(stage, f"{root}/cell_{r}_{c}", (cell * 0.82, cell * 0.82, 0.0006),
                 (x, y, 0.0002), M["mesh"])

    # scanner PCB at the mesh edge
    _box(stage, root + "/scanner_pcb", (0.080, 0.060, 0.0016),
         (0.0, hy - 0.05, BELT_TOP + 0.001), M["pcb"])

    # pills: a tray on the mesh + a few approaching on the belt
    centers = [(-0.054 + 0.036 * i, -0.054 + 0.036 * j) for i in range(4) for j in range(4)]
    for k, (px, py) in enumerate(centers):
        _cyl(stage, f"{root}/pill_{k}", S.__dict__.get("PILL_R", 0.013), 0.006,
             (px, py, 0.003), M["pill"])
    for k, bx in enumerate((-0.30, -0.24, -0.18)):
        _cyl(stage, f"{root}/feed_pill_{k}", 0.013, 0.006, (bx, 0.0, 0.003), M["pill"])

    # Edge appliance on a VESA stand, front-right of the belt
    bx, by = hx - 0.18, -(hy + 0.16)
    post_h = -FLOOR_Z + BELT_TOP
    _box(stage, root + "/edge_post", (0.06, 0.06, post_h),
         (bx, by, FLOOR_Z + post_h / 2), M["metal"])
    body_stl, bezel_stl = _ensure_enclosure_stl()
    app_z = BELT_TOP + 0.02
    recline = (-70.0, 0.0, 0.0)
    if body_stl:
        bp, bi = _read_stl(body_stl)
        zp, zi = _read_stl(bezel_stl)
        # center xy at origin (model is centred; depth runs 0..64 mm in +z)
        _mesh(stage, root + "/edge_body", bp, bi, (bx, by, app_z), 0.001,
              M["graphite"], euler=recline)
        _mesh(stage, root + "/edge_bezel", zp, zi, (bx, by, app_z), 0.001,
              M["alu"], euler=recline)
    else:
        _box(stage, root + "/edge_body", (S.ENCL_W, S.ENCL_D, S.ENCL_H),
             (bx, by, app_z + S.ENCL_H / 2), M["graphite"], euler=recline)
    # emissive kiosk screen proud of the bezel (the 7" active area)
    _box(stage, root + "/edge_screen", (S.DISP_ACT_W, S.DISP_ACT_H, 0.002),
         (bx, by + 0.02, app_z + 0.066), M["screen"], euler=recline)

    # Jetson Orin Nano dev kit (visible behind/below the bezel)
    _box(stage, root + "/jetson", (S.JETSON_W, S.JETSON_D, S.JETSON_H),
         (bx, by - 0.02, app_z + 0.02), M["graphite"], euler=recline)


def setup_lighting(stage):
    key = UsdLux.DistantLight.Define(stage, "/World/Lights/key")
    key.CreateIntensityAttr(2200.0)
    key.CreateAngleAttr(1.5)
    UsdGeom.Xformable(key).AddRotateXYZOp().Set(Gf.Vec3f(-50, 20, 30))
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/dome")
    dome.CreateIntensityAttr(550.0)
    dome.CreateColorAttr(Gf.Vec3f(0.55, 0.6, 0.75))
    rim = UsdLux.SphereLight.Define(stage, "/World/Lights/rim")
    rim.CreateIntensityAttr(35000.0)
    rim.CreateRadiusAttr(0.1)
    UsdGeom.Xformable(rim).AddTranslateOp().Set(Gf.Vec3d(-0.6, 0.6, 0.7))


def render(path=None):
    from isaacsim.core.api import World
    world = World(stage_units_in_meters=1.0)
    stage = world.stage
    build(stage)
    setup_lighting(stage)
    world.reset()

    cam = rep.create.camera(position=(0.85, -0.85, 0.55), look_at=(0.0, 0.0, -0.02))
    rp = rep.create.render_product(cam, (_W, _H))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach(rp)
    for _ in range(120):
        world.step(render=True)
    img = np.asarray(rgb.get_data())[..., :3].astype(np.uint8)
    path = path or os.path.join(OUT, "twin_scene.png")
    Image.fromarray(img).save(path)
    print(f"[scene] rendered -> {path}  shape={img.shape}  mean={img.mean():.1f}")
    return path


if __name__ == "__main__":
    render()
    sim_app.close()
    print("[scene] OK")
