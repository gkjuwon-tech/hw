"""Presentation render of the digital-twin conveyor (Blender Cycles).

MuJoCo runs the physics (numbers); this is the *pretty* view for humans.
A conveyor with the tactile mesh laid along the WHOLE belt, a tray of
colourful tablets riding it (externally identical good/void pills), two
enlarged cut-aways showing the internal void a camera can't see, and our
Tactile Edge enclosure on a stand beside the line.

Run:  OPENSCAD=/path/to/openscad python3 sim/render_blender.py
"""

import bpy, os, math, random
from mathutils import Vector

OUT = os.environ.get("SCENE_OUT", "/tmp/svgprev/twin_blender.png")
ENCL_BODY = os.environ.get("EDGE_BODY_STL", "/tmp/edge_body.stl")
ENCL_BEZEL = os.environ.get("EDGE_BEZEL_STL", "/tmp/edge_bezel.stl")

# ── real specs (m) ──
BELT_LEN, BELT_W, BELT_TH = 1.20, 0.350, 0.022
ROLLER_R, RAIL_H = 0.032, 0.045
PITCH, MESH_TH = 0.010, 0.004
BELT_TOP = BELT_TH / 2
MAT_TOP = BELT_TOP + MESH_TH


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
    if material: o.data.materials.append(material)
    return o

def cyl(name, r, depth, loc, rot, material):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object; o.name = name
    o.data.materials.append(material); bpy.ops.object.shade_smooth()
    return o

def import_stl(path):
    before = set(bpy.data.objects)
    try: bpy.ops.wm.stl_import(filepath=path)
    except Exception: bpy.ops.import_mesh.stl(filepath=path)
    return (set(bpy.data.objects) - before).pop()


bpy.ops.wm.read_factory_settings(use_empty=True)

# ── materials (with actual colour) ──
M_FLOOR = mat("floor", (0.05, 0.055, 0.07), rough=0.35)
M_BELT  = mat("belt", (0.04, 0.05, 0.07), rough=0.6)
M_METAL = mat("metal", (0.50, 0.52, 0.56), metallic=1.0, rough=0.28)
M_GRAPH = mat("graphite", (0.03, 0.033, 0.04), rough=0.5, coat=0.15)
M_ALU   = mat("alu", (0.62, 0.64, 0.68), metallic=1.0, rough=0.22)
M_SCREEN = mat("screen", (0.02, 0.05, 0.04), rough=0.1, emit=(0.05, 0.55, 0.32), emit_s=3.0)
PILL_COLORS = [
    mat("pill_red",  (0.80, 0.12, 0.12), rough=0.3, coat=0.4),
    mat("pill_blue", (0.12, 0.28, 0.85), rough=0.3, coat=0.4),
    mat("pill_amber",(0.92, 0.72, 0.10), rough=0.3, coat=0.4),
    mat("pill_white",(0.90, 0.90, 0.93), rough=0.3, coat=0.4),
    mat("pill_teal", (0.05, 0.62, 0.52), rough=0.3, coat=0.4),
]
M_VOID = mat("void", (0.02, 0.02, 0.025), rough=0.95)   # dark hollow interior

# ── floor + conveyor ──
box("floor", (4, 4, 0.04), (0, 0, -0.30 - 0.02), M_FLOOR)
box("belt", (BELT_LEN, BELT_W, BELT_TH), (0, 0, 0), M_BELT)
for sx in (-1, 1):
    cyl("roller", ROLLER_R, BELT_W + 0.02, (sx*BELT_LEN/2, 0, 0), (math.radians(90), 0, 0), M_METAL)
for sy in (-1, 1):
    box("rail", (BELT_LEN, 0.012, RAIL_H), (0, sy*(BELT_W/2 + 0.006), BELT_TOP + RAIL_H/2 - 0.01), M_METAL)
legh = (0.30 - BELT_TH/2)
for sx in (-1, 1):
    for sy in (-1, 1):
        box("leg", (0.026, 0.026, legh), (sx*(BELT_LEN/2 - 0.07), sy*(BELT_W/2 - 0.03), -BELT_TH/2 - legh/2), M_METAL)

# ── tactile mesh over the whole belt (green cell grid) ──
mat_obj = box("tactile_mesh", (BELT_LEN - 0.02, BELT_W - 0.02, MESH_TH), (0, 0, BELT_TOP + MESH_TH/2), None)
gm = bpy.data.materials.new("mesh_grid"); gm.use_nodes = True
nt = gm.node_tree; bsdf = nt.nodes["Principled BSDF"]; bsdf.inputs["Roughness"].default_value = 0.5
chk = nt.nodes.new("ShaderNodeTexChecker")
chk.inputs["Color1"].default_value = (0.04, 0.32, 0.20, 1)
chk.inputs["Color2"].default_value = (0.08, 0.46, 0.30, 1)
mp = nt.nodes.new("ShaderNodeMapping"); tc = nt.nodes.new("ShaderNodeTexCoord")
mp.inputs["Scale"].default_value = (BELT_LEN/PITCH, BELT_W/PITCH, 1)
nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
nt.links.new(mp.outputs["Vector"], chk.inputs["Vector"])
nt.links.new(chk.outputs["Color"], bsdf.inputs["Base Color"])
mat_obj.data.materials.append(gm)

# ── pills: colourful tablets riding the belt ──
random.seed(3)
TAB_R, TAB_H = 0.012, 0.007

def tablet(name, loc, r=TAB_R, h=TAB_H, material=None, hollow=False, cutaway=False):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, location=loc)
    o = bpy.context.active_object; o.name = name
    tools = []
    if hollow:
        bpy.ops.mesh.primitive_cylinder_add(radius=r*0.6, depth=h*0.62, location=loc)
        tools.append(bpy.context.active_object)
    if cutaway:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], loc[1]-r, loc[2]))
        cb = bpy.context.active_object; cb.scale = (r*1.6, r, h*2)
        bpy.ops.object.transform_apply(scale=True); tools.append(cb)
    for t in tools:
        md = o.modifiers.new("b", 'BOOLEAN'); md.operation = 'DIFFERENCE'; md.object = t; md.solver = 'FLOAT'
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier="b")
        bpy.data.objects.remove(t, do_unlink=True)
    o.data.materials.append(material or PILL_COLORS[0])
    bpy.ops.object.shade_smooth()
    return o

pz = MAT_TOP + TAB_H/2
i = 0
for x in [-0.30, -0.18, -0.06, 0.10, 0.22, 0.34, 0.46]:
    for y in [0.02, 0.10]:
        tablet(f"pill_{i}", (x, y, pz), material=PILL_COLORS[i % len(PILL_COLORS)]); i += 1

# featured cut-aways (enlarged): solid (good) vs hollow (void) — front, facing camera
FR, FH = 0.020, 0.011
tablet("cut_solid",  (-0.07, -0.07, MAT_TOP + FH/2), r=FR, h=FH, material=PILL_COLORS[0], cutaway=True)
tablet("cut_void", (0.05, -0.07, MAT_TOP + FH/2), r=FR, h=FH, material=PILL_COLORS[1], hollow=True, cutaway=True)
cyl("void_fill", FR*0.55, FH*0.55, (0.05, -0.07, MAT_TOP + FH/2), (0, 0, 0), M_VOID)

# ── Edge box on a stand beside the belt ──
if os.path.exists(ENCL_BODY) and os.path.exists(ENCL_BEZEL):
    bx, by = 0.42, -(BELT_W/2 + 0.13)
    box("post", (0.05, 0.05, 0.30), (bx, by, -0.15), M_METAL)
    body = import_stl(ENCL_BODY); bezel = import_stl(ENCL_BEZEL)
    for o in (body, bezel): o.scale = (0.001, 0.001, 0.001)
    bezel.location = (0, 0, 0.064); bpy.context.view_layer.update()
    body.data.materials.append(M_GRAPH); bezel.data.materials.append(M_ALU)
    scr = box("edge_screen", (0.15, 0.085, 0.002), (0, 0, 0), M_SCREEN)
    scr.parent = body; scr.location = (0, 0, 0.067); bezel.parent = body
    body.rotation_euler = (math.radians(-60), 0, math.radians(180))
    body.location = (bx, by, 0.03)

# ── world: dim studio gradient ──
w = bpy.data.worlds.new("studio"); bpy.context.scene.world = w; w.use_nodes = True
wn = w.node_tree; wn.nodes.clear()
bg = wn.nodes.new("ShaderNodeBackground"); out = wn.nodes.new("ShaderNodeOutputWorld")
gr = wn.nodes.new("ShaderNodeTexGradient"); rm = wn.nodes.new("ShaderNodeValToRGB")
tcw = wn.nodes.new("ShaderNodeTexCoord"); mpw = wn.nodes.new("ShaderNodeMapping")
mpw.inputs["Rotation"].default_value = (math.radians(90), 0, 0)
rm.color_ramp.elements[0].color = (0.015, 0.017, 0.022, 1)
rm.color_ramp.elements[1].color = (0.05, 0.06, 0.08, 1)
wn.links.new(tcw.outputs["Generated"], mpw.inputs["Vector"])
wn.links.new(mpw.outputs["Vector"], gr.inputs["Vector"])
wn.links.new(gr.outputs["Color"], rm.inputs["Fac"])
wn.links.new(rm.outputs["Color"], bg.inputs["Color"])
wn.links.new(bg.outputs["Background"], out.inputs["Surface"])
bg.inputs["Strength"].default_value = 0.5

# ── lights (conservative — overexposure was the bug) ──
def area(name, loc, energy, size):
    l = bpy.data.lights.new(name, 'AREA'); l.energy = energy; l.size = size
    o = bpy.data.objects.new(name, l); bpy.context.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector((0, 0, 0.02)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return o
area("key", (0.45, -0.55, 0.85), 90, 0.9)
area("fill", (-0.7, -0.25, 0.5), 28, 1.1)
area("rim", (-0.3, 0.7, 0.7), 55, 0.7)

# ── camera (close, low 3/4 so pills clearly SIT on the belt) ──
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 50
cam = bpy.data.objects.new("cam", cam_d); bpy.context.collection.objects.link(cam)
cam.location = (0.42, -0.50, 0.24)
cam.rotation_euler = (Vector((-0.02, 0.0, 0.03)) - Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = cam

# ── render ──
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
sc.cycles.samples = 96; sc.cycles.use_denoising = True
sc.render.resolution_x = 1280; sc.render.resolution_y = 860
sc.view_settings.view_transform = 'AgX'
sc.view_settings.exposure = 0.0
sc.render.filepath = OUT
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.render.render(write_still=True)
print("RENDER_DONE", OUT)
