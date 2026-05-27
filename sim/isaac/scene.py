"""Full-fidelity digital-twin scene in Isaac Sim — the real Conet Tactile line.

To-scale from `sim/specs.py` (single source of truth) and built from proper
geometry, not placeholder boxes:

  * a conveyor with an extruded-aluminium frame, two end rollers, a drive motor,
    guide rails, and legs — belt top at z = -MESH_THICK
  * the 16x16 Velostat tactile mesh at the inspection station (top at z=0) with
    a visible sensor-cell grid and an FFC ribbon to the scanner PCB
  * the scanner PCB populated with its real ICs (STM32, 4x mux, connectors)
  * biconvex tablets / capsules resting ON the mesh (z aligned to the surface)
  * the Tactile Edge appliance on a VESA stand: the *actual* 3D-printed enclosure
    body + chamfered bezel (imported from edge_enclosure.scad via OpenSCAD), an
    emissive kiosk screen, and a detailed Jetson Orin Nano (board + finned
    heatsink + fan)

Renders a hero RTX shot headless to sim/isaac/out/twin_scene.png.

Run (isaac venv on the GPU pod):
  OMNI_KIT_ACCEPT_EULA=YES python sim/isaac/scene.py
"""
from __future__ import annotations

import os
import struct

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
HX, HY      = S.BELT_LENGTH / 2, S.BELT_WIDTH / 2


# ── enclosure STL (export from the .scad if missing) ─────────────────────

def _ensure_enclosure_stl():
    body = os.path.join(ASSETS, "edge_body.stl")
    bezel = os.path.join(ASSETS, "edge_bezel.stl")
    scad = os.path.join(REPO, "hardware", "edge_enclosure", "edge_enclosure.scad")
    import shutil, subprocess
    osc = os.environ.get("OPENSCAD") or shutil.which("openscad")
    if not osc:
        return (None, None)
    for part, dst in (("body", body), ("bezel", bezel)):
        if not os.path.exists(dst):
            subprocess.run([osc, "-o", dst, "-D", f'part="{part}"', scad], check=True)
    return (body, bezel)


def _read_stl(path):
    with open(path, "rb") as f:
        head = f.read(5)
    if head == b"solid":
        verts = []
        with open(path, "r", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if s.startswith("vertex"):
                    _, x, y, z = s.split()
                    verts.append((float(x), float(y), float(z)))
        pts = np.array(verts, dtype=np.float32)
    else:
        with open(path, "rb") as f:
            f.read(80)
            (n,) = struct.unpack("<I", f.read(4))
            pts = np.empty((n * 3, 3), dtype=np.float32)
            for i in range(n):
                f.read(12)
                for j in range(3):
                    pts[i * 3 + j] = struct.unpack("<3f", f.read(12))
                f.read(2)
    return pts, np.arange(len(pts), dtype=np.int32)


# ── material + primitive helpers ─────────────────────────────────────────

def _mat(stage, path, diffuse, metallic=0.0, rough=0.5, emissive=None, opacity=1.0):
    mat = UsdShade.Material.Define(stage, path)
    sh = UsdShade.Shader.Define(stage, path + "/s")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*diffuse))
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    if emissive is not None:
        sh.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emissive))
    if opacity < 1.0:
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def _bind(prim, mat):
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(mat)


def _xform(prim, pos=None, euler=None, scale=None):
    xf = UsdGeom.Xformable(prim)
    if pos is not None:
        xf.AddTranslateOp().Set(Gf.Vec3d(*pos))
    if euler is not None:
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*euler))
    if scale is not None:
        xf.AddScaleOp().Set(Gf.Vec3f(*scale))


def _box(stage, path, dims, pos, mat, euler=None):
    c = UsdGeom.Cube.Define(stage, path); c.CreateSizeAttr(1.0)
    _xform(c.GetPrim(), pos, euler, tuple(d for d in dims))
    _bind(c.GetPrim(), mat); return c


def _cyl(stage, path, radius, height, pos, mat, axis="Z", euler=None):
    c = UsdGeom.Cylinder.Define(stage, path)
    c.CreateRadiusAttr(radius); c.CreateHeightAttr(height); c.CreateAxisAttr(axis)
    _xform(c.GetPrim(), pos, euler)
    _bind(c.GetPrim(), mat); return c


def _capsule(stage, path, radius, height, pos, mat, axis="Z", euler=None, scale=None):
    c = UsdGeom.Capsule.Define(stage, path)
    c.CreateRadiusAttr(radius); c.CreateHeightAttr(height); c.CreateAxisAttr(axis)
    _xform(c.GetPrim(), pos, euler, scale)
    _bind(c.GetPrim(), mat); return c


def _sphere(stage, path, radius, pos, mat, scale=None):
    s = UsdGeom.Sphere.Define(stage, path); s.CreateRadiusAttr(radius)
    _xform(s.GetPrim(), pos, None, scale)
    _bind(s.GetPrim(), mat); return s


def _mesh(stage, path, pts, idx, pos, scale, mat, euler=None):
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr([Gf.Vec3f(*p) for p in pts])
    m.CreateFaceVertexIndicesAttr(idx.tolist())
    m.CreateFaceVertexCountsAttr([3] * (len(idx) // 3))
    m.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    _xform(m.GetPrim(), pos, euler, (scale, scale, scale))
    _bind(m.GetPrim(), mat); return m


# ── sub-assemblies ───────────────────────────────────────────────────────

def build_conveyor(stage, root, M):
    # belt top run + bottom return run (suggests the loop around the rollers)
    _box(stage, f"{root}/belt_top", (S.BELT_LENGTH, S.BELT_WIDTH, S.BELT_THICK),
         (0, 0, BELT_CZ), M["belt"])
    _box(stage, f"{root}/belt_bot", (S.BELT_LENGTH, S.BELT_WIDTH, S.BELT_THICK),
         (0, 0, BELT_TOP - S.ROLLER_DIA - S.BELT_THICK / 2), M["belt"])
    sgn = lambda v: "p" if v > 0 else "n"
    # end rollers (axis Y) with the belt tangent to their tops
    for sx in (-1, 1):
        _cyl(stage, f"{root}/roller_{sgn(sx)}", S.ROLLER_DIA / 2, S.BELT_WIDTH + 0.03,
             (sx * HX, 0, BELT_TOP - S.ROLLER_DIA / 2), M["metal"], axis="Y")
    # drive motor at the head roller
    _cyl(stage, f"{root}/motor", 0.035, 0.09, (HX + 0.02, HY + 0.06, BELT_TOP - S.ROLLER_DIA / 2),
         M["motor"], axis="Y")
    # extruded-aluminium side frame beams under the belt edges
    for sy in (-1, 1):
        _box(stage, f"{root}/frame_{sgn(sy)}", (S.BELT_LENGTH + 0.04, 0.03, 0.05),
             (0, sy * (HY + 0.02), BELT_TOP - 0.05), M["frame"])
    # guide rails
    for sy in (-1, 1):
        _box(stage, f"{root}/rail_{sgn(sy)}", (S.BELT_LENGTH, 0.008, S.RAIL_H),
             (0, sy * (HY + 0.004), BELT_TOP + S.RAIL_H / 2), M["frame"])
    # legs + feet
    legh = (BELT_TOP - 0.07) - FLOOR_Z
    for lx in (-HX + 0.06, HX - 0.06):
        for ly in (-HY + 0.0, HY - 0.0):
            n = f"{lx:.2f}_{ly:.2f}".replace("-", "n").replace(".", "_")
            _box(stage, f"{root}/leg_{n}", (0.03, 0.03, legh),
                 (lx, ly, FLOOR_Z + legh / 2), M["frame"])
            _cyl(stage, f"{root}/foot_{n}", 0.022, 0.012, (lx, ly, FLOOR_Z + 0.006), M["metal"])


def build_mesh_sensor(stage, root, M):
    # laminated Velostat sheet, top at z=0
    _box(stage, f"{root}/mesh_pad", (S.MESH_W + 0.012, S.MESH_H + 0.012, S.MESH_THICK),
         (0, 0, -S.MESH_THICK / 2), M["velostat"])
    cell = S.CELL_PITCH
    grid = UsdGeom.Xform.Define(stage, f"{root}/cells")
    for r in range(S.MESH_ROWS):
        for c in range(S.MESH_COLS):
            x = -(S.MESH_COLS - 1) * cell / 2 + c * cell
            y = -(S.MESH_ROWS - 1) * cell / 2 + r * cell
            _box(stage, f"{root}/cells/c_{r}_{c}", (cell * 0.8, cell * 0.8, 0.0008),
                 (x, y, 0.0003), M["cell"])
    # FFC ribbon from the mesh edge to the scanner PCB (a few flat segments)
    ry0 = S.MESH_H / 2
    seg = [(0.0, ry0 + 0.01, 0.0006, 0.03, 0.02),
           (0.0, ry0 + 0.03, -0.002, 0.03, 0.02),
           (0.0, ry0 + 0.05, -0.006, 0.03, 0.02)]
    for i, (x, y, z, w, l) in enumerate(seg):
        _box(stage, f"{root}/ffc_{i}", (w, l, 0.0006), (x, y, z), M["ffc"],
             euler=(20 * i, 0, 0))


def build_scanner_pcb(stage, root, M):
    px, py, pz = 0.0, HY - 0.045, BELT_TOP + 0.0009
    _box(stage, f"{root}/pcb", (0.080, 0.060, 0.0016), (px, py, pz), M["pcb"])
    # STM32 main MCU (QFP)
    _box(stage, f"{root}/ic_mcu", (0.012, 0.012, 0.0018), (px - 0.018, py, pz + 0.0017), M["chip"])
    # 4x analog mux ICs
    for i, dx in enumerate((-0.005, 0.008, 0.021, 0.034)):
        _box(stage, f"{root}/ic_mux_{i}", (0.006, 0.010, 0.0015),
             (px + dx, py - 0.016, pz + 0.0016), M["chip"])
    # FFC connector + USB-C
    _box(stage, f"{root}/conn_ffc", (0.034, 0.006, 0.003), (px, py + 0.026, pz + 0.0016), M["conn"])
    _box(stage, f"{root}/conn_usb", (0.009, 0.007, 0.0035), (px - 0.036, py, pz + 0.0017), M["metal"])


def build_pills(stage, root, M):
    """4x4 tray of biconvex tablets / capsules resting on the mesh top (z=0)."""
    spacing = 0.036
    o = -(4 - 1) * spacing / 2
    rng = np.random.default_rng(3)
    for i in range(4):
        for k in range(4):
            x, y = o + i * spacing, o + k * spacing
            idx = i * 4 + k
            col = M["pill"] if rng.random() < 0.7 else M[rng.choice(["pillR", "pillB"])]
            if rng.random() < 0.45:  # capsule
                _capsule(stage, f"{root}/pill_{idx}", 0.005, 0.012, (x, y, 0.005),
                         col, axis="X")
            else:                    # biconvex tablet (flattened sphere)
                _sphere(stage, f"{root}/pill_{idx}", 0.013, (x, y, 0.0035), col,
                        scale=(1.0, 1.0, 0.28))
    # a few tablets riding in on the belt toward the station
    for k, bx in enumerate((-0.34, -0.27, -0.20)):
        _sphere(stage, f"{root}/feed_{k}", 0.013, (bx, 0.0, 0.0035 + BELT_TOP),
                M["pill"], scale=(1.0, 1.0, 0.28))


def build_jetson(stage, base, M):
    """Build a detailed Jetson Orin Nano dev kit under Xform path `base`
    (local coords; the caller orients `base`)."""
    UsdGeom.Xform.Define(stage, base)
    _box(stage, f"{base}/carrier", (S.JETSON_W, S.JETSON_D, 0.0016), (0, 0, 0), M["pcb"])
    # iconic square finned heatsink
    hs_w = 0.072
    _box(stage, f"{base}/hs_base", (hs_w, hs_w, 0.006), (0, 0, 0.004), M["heatsink"])
    nfin = 11
    for i in range(nfin):
        fy = -hs_w / 2 + (i + 0.5) * hs_w / nfin
        _box(stage, f"{base}/fin_{i}", (hs_w, hs_w / nfin * 0.5, 0.018),
             (0, fy, 0.016), M["heatsink"])
    # fan on top
    _cyl(stage, f"{base}/fan", hs_w / 2 * 0.85, 0.008, (0, 0, 0.028), M["chip"])
    # GPIO header
    _box(stage, f"{base}/gpio", (0.0025, 0.05, 0.006), (S.JETSON_W / 2 - 0.006, 0, 0.003), M["chip"])


def build_edge_appliance(stage, root, M):
    # kiosk on a VESA stand beside the belt, downstream of the inspection station
    bx, by = 0.34, -(HY + 0.14)
    cz = BELT_TOP + 0.20                       # device CENTRE height above floor
    _box(stage, f"{root}/stand_base", (0.18, 0.14, 0.012), (bx, by, FLOOR_Z + 0.006), M["frame"])
    post_h = cz - FLOOR_Z
    _box(stage, f"{root}/stand_post", (0.045, 0.045, post_h), (bx, by + 0.03, FLOOR_Z + post_h / 2),
         M["frame"])

    # parent Xform = kiosk pose. The .scad model is xy-centred with depth 0..64mm
    # in +z; we centre z too (local -0.032) so the device rotates about its centre.
    # euler X=78deg stands the screen (+z face) up to face the operator (-Y), tilted back.
    app = UsdGeom.Xform.Define(stage, f"{root}/appliance")
    _xform(app.GetPrim(), pos=(bx, by, cz), euler=(78.0, 0.0, 0.0))
    base = f"{root}/appliance"
    half_d = 0.032                              # half the 64mm device depth (m)
    body_stl, bezel_stl = _ensure_enclosure_stl()
    if body_stl:
        bp, bi = _read_stl(body_stl)
        zp, zi = _read_stl(bezel_stl)
        _mesh(stage, f"{base}/body", bp, bi, (0, 0, -half_d), 0.001, M["graphite"])
        _mesh(stage, f"{base}/bezel", zp, zi, (0, 0, half_d - 0.009), 0.001, M["alu"])
        build_jetson(stage, f"{base}/jetson", M)
        _xform(stage.GetPrimAtPath(f"{base}/jetson"), pos=(0, 0, -half_d + 0.012))
        scr_z = half_d + 0.0015
    else:
        _box(stage, f"{base}/body", (S.ENCL_W, S.ENCL_D, 2 * half_d), (0, 0, 0), M["graphite"])
        scr_z = half_d + 0.0015
    # emissive kiosk screen (7" active area), just proud of the bezel front face
    _box(stage, f"{base}/screen", (S.DISP_ACT_W, S.DISP_ACT_H, 0.002), (0, 0, scr_z), M["screen"])


# ── scene assembly ─────────────────────────────────────────────────────────

def build(stage):
    root = "/World"
    UsdGeom.Xform.Define(stage, root)
    UsdGeom.Xform.Define(stage, root + "/M")
    M = dict(
        belt=_mat(stage, root + "/M/belt", (0.04, 0.04, 0.05), 0.0, 0.85),
        metal=_mat(stage, root + "/M/metal", (0.62, 0.64, 0.67), 0.95, 0.3),
        frame=_mat(stage, root + "/M/frame", (0.70, 0.72, 0.75), 0.85, 0.38),
        motor=_mat(stage, root + "/M/motor", (0.20, 0.21, 0.24), 0.6, 0.4),
        velostat=_mat(stage, root + "/M/velostat", (0.06, 0.20, 0.15), 0.0, 0.6),
        cell=_mat(stage, root + "/M/cell", (0.10, 0.42, 0.30), 0.1, 0.45),
        ffc=_mat(stage, root + "/M/ffc", (0.55, 0.42, 0.12), 0.3, 0.4),
        pcb=_mat(stage, root + "/M/pcb", (0.06, 0.32, 0.18), 0.15, 0.5),
        chip=_mat(stage, root + "/M/chip", (0.06, 0.06, 0.07), 0.2, 0.45),
        conn=_mat(stage, root + "/M/conn", (0.85, 0.85, 0.88), 0.7, 0.35),
        pill=_mat(stage, root + "/M/pill", (0.92, 0.90, 0.84), 0.0, 0.40),
        pillR=_mat(stage, root + "/M/pillR", (0.80, 0.28, 0.24), 0.0, 0.4),
        pillB=_mat(stage, root + "/M/pillB", (0.30, 0.45, 0.80), 0.0, 0.4),
        graphite=_mat(stage, root + "/M/graphite", (0.04, 0.045, 0.05), 0.1, 0.5),
        alu=_mat(stage, root + "/M/alu", (0.68, 0.70, 0.73), 1.0, 0.22),
        heatsink=_mat(stage, root + "/M/heatsink", (0.74, 0.76, 0.79), 1.0, 0.28),
        screen=_mat(stage, root + "/M/screen", (0.02, 0.07, 0.05), 0.0, 0.1,
                    emissive=(0.05, 0.55, 0.32)),
        floor=_mat(stage, root + "/M/floor", (0.14, 0.15, 0.17), 0.0, 0.55),
    )

    # factory floor
    fl = UsdGeom.Mesh.Define(stage, root + "/floor")
    s = 3.0
    fl.CreatePointsAttr([Gf.Vec3f(-s, -s, FLOOR_Z), Gf.Vec3f(s, -s, FLOOR_Z),
                         Gf.Vec3f(s, s, FLOOR_Z), Gf.Vec3f(-s, s, FLOOR_Z)])
    fl.CreateFaceVertexIndicesAttr([0, 1, 2, 3]); fl.CreateFaceVertexCountsAttr([4])
    _bind(fl.GetPrim(), M["floor"])

    build_conveyor(stage, root, M)
    build_mesh_sensor(stage, root, M)
    build_scanner_pcb(stage, root, M)
    build_pills(stage, root, M)
    build_edge_appliance(stage, root, M)


def setup_lighting(stage):
    UsdGeom.Xform.Define(stage, "/World/Lights")
    dome = UsdLux.DomeLight.Define(stage, "/World/Lights/dome")
    dome.CreateIntensityAttr(700.0); dome.CreateColorAttr(Gf.Vec3f(0.6, 0.65, 0.78))
    key = UsdLux.DistantLight.Define(stage, "/World/Lights/key")
    key.CreateIntensityAttr(2400.0); key.CreateColorAttr(Gf.Vec3f(1.0, 0.97, 0.92))
    key.CreateAngleAttr(1.2)
    _xform(key.GetPrim(), euler=(-48, 18, 25))
    rect = UsdLux.RectLight.Define(stage, "/World/Lights/overhead")
    rect.CreateIntensityAttr(9000.0); rect.CreateWidthAttr(1.2); rect.CreateHeightAttr(0.5)
    _xform(rect.GetPrim(), pos=(0, 0, 0.9), euler=(0, 0, 0))
    rim = UsdLux.SphereLight.Define(stage, "/World/Lights/rim")
    rim.CreateIntensityAttr(28000.0); rim.CreateRadiusAttr(0.08)
    _xform(rim.GetPrim(), pos=(-0.6, 0.7, 0.6))


VIEWS = {
    # name: (camera position, look_at, focal_length)
    "twin_overview": ((1.05, -1.05, 0.70), (0.00, 0.00, -0.02), 20.0),   # whole line (known-good)
    "hero_a":        ((0.50, -0.50, 0.40), (0.0, 0.0, 0.0), 30.0),       # diagonal, like overview but close
    "hero_b":        ((0.40, -0.45, 0.55), (0.0, 0.0, 0.0), 30.0),       # higher look-down
    "hero_c":        ((0.05, -0.55, 0.48), (0.0, 0.0, 0.0), 28.0),       # front, elevated
}


def render(steps=140):
    from isaacsim.core.api import World
    world = World(stage_units_in_meters=1.0)
    stage = world.stage
    build(stage)
    setup_lighting(stage)
    world.reset()

    products = {}
    for name, (pos, look, fl) in VIEWS.items():
        cam = rep.create.camera(position=pos, look_at=look, focal_length=fl)
        rp = rep.create.render_product(cam, (_W, _H))
        ann = rep.AnnotatorRegistry.get_annotator("rgb")
        ann.attach(rp)
        products[name] = ann

    for _ in range(steps):
        world.step(render=True)

    for name, ann in products.items():
        img = np.asarray(ann.get_data())[..., :3].astype(np.uint8)
        path = os.path.join(OUT, f"{name}.png")
        Image.fromarray(img).save(path)
        print(f"[scene] rendered -> {path}  shape={img.shape}  mean={img.mean():.1f}")


if __name__ == "__main__":
    render()
    sim_app.close()
    print("[scene] OK")
