"""Presentation render of the digital-twin conveyor (Blender Cycles).

MuJoCo runs the physics (numbers); this is the *pretty* view for humans.
A full conveyor with the tactile mesh laid along the WHOLE belt (so every
part that rides past is inspected, not just one spot), several parts —
good and defective — on the mat, and our actual Tactile Edge enclosure on
a stand beside the line.

Run:
    OPENSCAD=/path/to/openscad python3 sim/render_blender.py
(OPENSCAD optional — exports the enclosure STL; without it the box is omitted.)
"""

import bpy, os, math, shutil, subprocess, tempfile
from mathutils import Vector

OUT = os.environ.get("SCENE_OUT", "/tmp/svgprev/twin_blender.png")

# ── real specs (m) — mirrors sim/specs.py (repo + datasheets) ──
BELT_LEN, BELT_W, BELT_TH = 1.20, 0.350, 0.020
ROLLER_R, RAIL_H = 0.030, 0.040
PITCH = 0.010                     # mesh cell pitch -> grid density
MESH_TH = 0.004
PART = (0.120, 0.080, 0.040)      # loaf-class part
ENCL_BODY = os.environ.get("EDGE_BODY_STL", "/tmp/edge_body.stl")
ENCL_BEZEL = os.environ.get("EDGE_BEZEL_STL", "/tmp/edge_bezel.stl")

BELT_TOP = BELT_TH / 2
MAT_TOP = BELT_TOP + MESH_TH


# ── helpers ──
def mat(name, base, metallic=0.0, rough=0.5, coat=0.0, emit=None, emit_s=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    if "Coat Weight" in b.inputs: b.inputs["Coat Weight"].default_value = coat
    if emit is not None:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = emit_s
    return m

def box(name, size, loc, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object; o.name = name
    o.scale = (size[0]/2, size[1]/2, size[2]/2)
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(material)
    return o

def cyl(name, r, depth, loc, rot, material):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object; o.name = name
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o

def import_stl(path):
    before = set(bpy.data.objects)
    try: bpy.ops.wm.stl_import(filepath=path)
    except Exception: bpy.ops.import_mesh.stl(filepath=path)
    return (set(bpy.data.objects) - before).pop()


# ── scene ──
bpy.ops.wm.read_factory_settings(use_empty=True)

M_FLOOR  = mat("floor", (0.10, 0.11, 0.13), rough=0.5)
M_BELT   = mat("belt", (0.05, 0.05, 0.06), rough=0.7)
M_METAL  = mat("metal", (0.55, 0.57, 0.60), metallic=1.0, rough=0.3)
M_PART   = mat("part", (0.80, 0.64, 0.40), rough=0.55, coat=0.1)
M_PELLET = mat("pellet", (0.10, 0.10, 0.11), metallic=0.6, rough=0.4)
M_GRAPH  = mat("graphite", (0.03, 0.033, 0.038), rough=0.5, coat=0.18)
M_ALU    = mat("alu", (0.66, 0.685, 0.71), metallic=1.0, rough=0.24)
M_SCREEN = mat("screen", (0.01, 0.02, 0.015), rough=0.08, coat=1.0, emit=(0.03, 0.42, 0.22), emit_s=2.2)

# floor
box("floor", (6, 6, 0.02), (0, 0, -0.36 - 0.01), M_FLOOR)

# conveyor
box("belt", (BELT_LEN, BELT_W, BELT_TH), (0, 0, 0), M_BELT)
for sx in (-1, 1):
    cyl("roller", ROLLER_R, BELT_W + 0.02, (sx*BELT_LEN/2, 0, 0), (math.radians(90), 0, 0), M_METAL)
for sy in (-1, 1):
    box("rail", (BELT_LEN, 0.012, RAIL_H), (0, sy*(BELT_W/2 + 0.006), BELT_TOP + RAIL_H/2), M_METAL)
for sx in (-1, 1):
    for sy in (-1, 1):
        legh = 0.36 + (-BELT_TH/2)
        box("leg", (0.024, 0.024, legh), (sx*(BELT_LEN/2 - 0.06), sy*(BELT_W/2 - 0.03), -BELT_TH/2 - legh/2), M_METAL)

# ── tactile mesh: a mat over the WHOLE belt, with a cell grid ──
mat_obj = box("tactile_mesh", (BELT_LEN - 0.02, BELT_W - 0.02, MESH_TH), (0, 0, BELT_TOP + MESH_TH/2), None)
gm = bpy.data.materials.new("mesh_grid"); gm.use_nodes = True
nt = gm.node_tree
bsdf = nt.nodes["Principled BSDF"]; bsdf.inputs["Roughness"].default_value = 0.55
chk = nt.nodes.new("ShaderNodeTexChecker")
chk.inputs["Color1"].default_value = (0.07, 0.30, 0.20, 1)
chk.inputs["Color2"].default_value = (0.10, 0.42, 0.28, 1)
mp = nt.nodes.new("ShaderNodeMapping")
tc = nt.nodes.new("ShaderNodeTexCoord")
mp.inputs["Scale"].default_value = ((BELT_LEN)/PITCH, (BELT_W)/PITCH, 1)  # ~118 x 33 cells
nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
nt.links.new(mp.outputs["Vector"], chk.inputs["Vector"])
nt.links.new(chk.outputs["Color"], bsdf.inputs["Base Color"])
mat_obj.data.materials.append(gm)

# ── parts riding the belt: good + defective ──
pw, pd, ph = PART
pz = MAT_TOP + ph/2
xs = [-0.46, -0.16, 0.16, 0.44]

# 0: nominal
box("part_ok_0", PART, (xs[0], 0, pz), M_PART)
# 1: chipped corner (boolean difference)
p1 = box("part_chip", PART, (xs[1], 0, pz), M_PART)
cutter = box("cutter", (0.05, 0.05, 0.05), (xs[1] + pw/2, pd/2, pz + ph/2), M_PART)
mod = p1.modifiers.new("chip", 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = cutter
bpy.context.view_layer.objects.active = p1
bpy.ops.object.modifier_apply(modifier="chip")
bpy.data.objects.remove(cutter, do_unlink=True)
# 2: nominal
box("part_ok_2", PART, (xs[2], 0, pz), M_PART)
# 3: foreign object (a dark pellet sitting on the part)
box("part_foreign", PART, (xs[3], 0, pz), M_PART)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.010, location=(xs[3], 0.0, pz + ph/2 + 0.006))
pel = bpy.context.active_object; pel.name = "pellet"; pel.data.materials.append(M_PELLET); bpy.ops.object.shade_smooth()

# ── Edge box on a stand beside the belt ──
if os.path.exists(ENCL_BODY) and os.path.exists(ENCL_BEZEL):
    bx, by = 0.50, -(BELT_W/2 + 0.16)
    box("post", (0.06, 0.06, 0.36), (bx, by, -0.18), M_METAL)
    body = import_stl(ENCL_BODY); bezel = import_stl(ENCL_BEZEL)
    for o in (body, bezel):
        o.scale = (0.001, 0.001, 0.001)
    bezel.location = (0, 0, 0.064)
    bpy.context.view_layer.update()
    # group into an empty, recline ~20deg, place on post, screen facing the belt
    body.data.materials.append(M_GRAPH); bezel.data.materials.append(M_ALU)
    scr = box("edge_screen", (0.15, 0.085, 0.002), (0, 0, 0), M_SCREEN)
    scr.parent = body; scr.location = (0, 0, 0.067)
    bezel.parent = body
    body.rotation_euler = (math.radians(-65), 0, math.radians(180))
    body.location = (bx, by, 0.02)

# ── world: soft studio gradient ──
w = bpy.data.worlds.new("studio"); bpy.context.scene.world = w; w.use_nodes = True
wn = w.node_tree; wn.nodes.clear()
bg = wn.nodes.new("ShaderNodeBackground"); out = wn.nodes.new("ShaderNodeOutputWorld")
gr = wn.nodes.new("ShaderNodeTexGradient"); rm = wn.nodes.new("ShaderNodeValToRGB")
tcw = wn.nodes.new("ShaderNodeTexCoord"); mpw = wn.nodes.new("ShaderNodeMapping")
mpw.inputs["Rotation"].default_value = (math.radians(90), 0, 0)
rm.color_ramp.elements[0].color = (0.02, 0.022, 0.03, 1)
rm.color_ramp.elements[1].color = (0.10, 0.11, 0.14, 1)
wn.links.new(tcw.outputs["Generated"], mpw.inputs["Vector"])
wn.links.new(mpw.outputs["Vector"], gr.inputs["Vector"])
wn.links.new(gr.outputs["Color"], rm.inputs["Fac"])
wn.links.new(rm.outputs["Color"], bg.inputs["Color"])
wn.links.new(bg.outputs["Background"], out.inputs["Surface"])
bg.inputs["Strength"].default_value = 0.5

# ── lights ──
def area(name, loc, energy, size):
    l = bpy.data.lights.new(name, 'AREA'); l.energy = energy; l.size = size
    o = bpy.data.objects.new(name, l); bpy.context.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return o
area("key", (0.8, -1.0, 1.3), 500, 1.6)
area("fill", (-1.2, -0.4, 0.8), 150, 1.8)
area("rim", (-0.6, 1.2, 1.0), 260, 1.2)

# ── camera ──
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 40
cam = bpy.data.objects.new("cam", cam_d); bpy.context.collection.objects.link(cam)
cam.location = (1.15, -0.95, 0.62)
cam.rotation_euler = (Vector((-0.1, 0.0, 0.02)) - Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

# ── render ──
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
sc.cycles.samples = 160; sc.cycles.use_denoising = True
sc.render.resolution_x = 1600; sc.render.resolution_y = 1000
sc.view_settings.view_transform = 'AgX'
sc.render.filepath = OUT
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.render.render(write_still=True)
print("RENDER_DONE", OUT)
