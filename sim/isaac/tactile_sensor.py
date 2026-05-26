"""Tactile mesh sensor for Isaac Sim — a 16x16 sprung-taxel array (bed of springs).

This is the 1:1 Isaac analogue of the MuJoCo twin in `sim/tactile_twin.py`:
each cell is a small rigid taxel on a prismatic joint with a linear spring
drive (a Winkler elastic foundation), tops coplanar at z=0. Under a resting
load the taxels compress and load spreads across the contact patch, exactly
like a compliant piezoresistive mat. We read each taxel's **net contact force**
(z), which is "how hard the cell is pressed" — the same per-cell pressure the
physical Velostat scanner reports. Resampled to 16x16 + 8-bit, synthetic and
real frames stay interchangeable.

Built with the raw USD/pxr API so it is independent of the (4.5-renamed)
`isaacsim.*` python namespace. `add_pill_tray` adds the 4x4 rigid tablets.
"""
from __future__ import annotations

from pxr import Usd, UsdGeom, UsdPhysics, Gf, Sdf, PhysxSchema

# Geometry / physics — mirror sim/tactile_twin.py and sim/specs.py.
PITCH      = 0.010      # 10 mm cell-to-cell  (specs.CELL_PITCH)
ROWS = COLS = 16
CELL_HALF  = 0.0046     # taxel half-width (m)
TAXEL_HZ   = 0.005      # taxel half-height
TAXEL_K    = 400.0      # per-taxel spring stiffness (N/m) — the compliance
TAXEL_D    = 4.0        # per-taxel spring damping
TAXEL_MASS = 0.004
TRAVEL     = 0.02       # max taxel travel each way (m)

# Pills (tablets) — mirror sim/generate_dataset.py.
PILL_N     = 4          # 4x4 = 16 pills per tray
PILL_R     = 0.013      # tablet radius (m)
PILL_H     = 0.006      # tablet thickness (m)
SPACING    = 0.036      # pill-to-pill spacing (m)
M0         = 0.08       # nominal pill mass (kg)


def grid_xy(r: int, c: int, rows=ROWS, cols=COLS, pitch=PITCH):
    """Centred (x, y) of cell (r, c) — matches tactile_twin._grid_xy."""
    x0 = -(cols - 1) * pitch / 2
    y0 = -(rows - 1) * pitch / 2
    return x0 + c * pitch, y0 + r * pitch


def pill_centers(n=PILL_N, spacing=SPACING):
    o = -(n - 1) * spacing / 2
    return [(o + i * spacing, o + j * spacing) for i in range(n) for j in range(n)]


def _mass(prim, kg, density=0.0):
    m = UsdPhysics.MassAPI.Apply(prim)
    if density > 0:
        m.CreateDensityAttr(density)
    else:
        m.CreateMassAttr(kg)
    return m


def build_sensor(stage: Usd.Stage, env_path: str,
                 rows=ROWS, cols=COLS, k=TAXEL_K, d=TAXEL_D):
    """Create the static base + a rows*cols grid of sprung taxels under
    `env_path`. Returns the list of taxel prim paths (row-major)."""
    base_path = f"{env_path}/sensor_base"
    base = UsdGeom.Xform.Define(stage, base_path)        # static anchor for joints

    taxel_paths = []
    for r in range(rows):
        for c in range(cols):
            x, y = grid_xy(r, c, rows, cols)
            tp = f"{env_path}/taxel_{r}_{c}"
            cube = UsdGeom.Cube.Define(stage, tp)
            cube.CreateSizeAttr(1.0)
            # scale a unit cube to the taxel box; top face at z=0
            xf = UsdGeom.Xformable(cube)
            xf.AddTranslateOp().Set(Gf.Vec3d(x, y, -TAXEL_HZ))
            xf.AddScaleOp().Set(Gf.Vec3f(CELL_HALF, CELL_HALF, TAXEL_HZ))
            prim = cube.GetPrim()
            UsdPhysics.CollisionAPI.Apply(prim)
            rb = UsdPhysics.RigidBodyAPI.Apply(prim)
            _mass(prim, TAXEL_MASS)
            # enable contact reporting so net contact force is readable
            cr = PhysxSchema.PhysxContactReportAPI.Apply(prim)
            cr.CreateThresholdAttr(0.0)

            # prismatic spring joint: base -> taxel, axis Z, target 0 (springref)
            jp = f"{env_path}/joint_{r}_{c}"
            joint = UsdPhysics.PrismaticJoint.Define(stage, jp)
            joint.CreateAxisAttr("Z")
            joint.CreateBody0Rel().SetTargets([base_path])
            joint.CreateBody1Rel().SetTargets([tp])
            joint.CreateLocalPos0Attr(Gf.Vec3f(x, y, -TAXEL_HZ))
            joint.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0))
            joint.CreateLowerLimitAttr(-TRAVEL)
            joint.CreateUpperLimitAttr(TRAVEL)
            drive = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "linear")
            drive.CreateTypeAttr("force")
            drive.CreateStiffnessAttr(k)        # spring: F = k * (target - pos)
            drive.CreateDampingAttr(d)
            drive.CreateTargetPositionAttr(0.0)
            taxel_paths.append(tp)
    return taxel_paths


def add_pill_tray(stage: Usd.Stage, env_path: str, drop_z=0.012,
                  radius=PILL_R, height=PILL_H, mass=M0):
    """Add the 4x4 tray of rigid tablets above the mesh. Returns pill paths."""
    paths = []
    for kpos, (px, py) in enumerate(pill_centers()):
        pp = f"{env_path}/pill_{kpos}"
        cyl = UsdGeom.Cylinder.Define(stage, pp)
        cyl.CreateRadiusAttr(radius)
        cyl.CreateHeightAttr(height)
        cyl.CreateAxisAttr("Z")
        UsdGeom.Xformable(cyl).AddTranslateOp().Set(Gf.Vec3d(px, py, drop_z))
        prim = cyl.GetPrim()
        UsdPhysics.CollisionAPI.Apply(prim)
        UsdPhysics.RigidBodyAPI.Apply(prim)
        _mass(prim, mass)
        PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr(0.0)
        paths.append(pp)
    return paths
