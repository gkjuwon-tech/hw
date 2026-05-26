"""Studio product render of the Edge enclosure (Blender Cycles).

Produces `preview.png` next to this script: matte-graphite body, anodized
aluminium bezel, an emissive screen, a soft studio light rig (key/fill/rim
softboxes + a vertical-gradient world for ambient + reflections) and a
dark sweep floor. No HDRI file required — the lighting is built in-scene.

Run (Blender as a Python module — `pip install bpy`):

    OPENSCAD=/path/to/openscad python3 render.py

It exports the two printable parts from `edge_enclosure.scad` via OpenSCAD
(set $OPENSCAD or have `openscad` on PATH), then renders. CPU Cycles, so
it takes a few minutes.
"""

import bpy, math, os, shutil, subprocess, tempfile
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
SCAD = os.path.join(HERE, "edge_enclosure.scad")
OUT  = os.path.join(HERE, "preview.png")

S = 0.01                 # mm -> Blender units
DEPTH = 64.0 * S         # body front-face z (matches edge_enclosure.scad depth)
WIN_W, WIN_H = 154*S, 86*S

# ---- export the printable parts from the .scad via OpenSCAD ----
osc = os.environ.get("OPENSCAD") or shutil.which("openscad") or shutil.which("openscad-nightly")
tmp = tempfile.mkdtemp()
body_stl  = os.path.join(tmp, "body.stl")
bezel_stl = os.path.join(tmp, "bezel.stl")
if osc:
    for part, dst in (("body", body_stl), ("bezel", bezel_stl)):
        subprocess.run([osc, "-o", dst, "-D", 'part="%s"' % part, SCAD], check=True)
else:
    # fall back to pre-exported STLs sitting next to this script
    body_stl  = os.path.join(HERE, "edge_body.stl")
    bezel_stl = os.path.join(HERE, "edge_bezel.stl")
    if not (os.path.exists(body_stl) and os.path.exists(bezel_stl)):
        raise SystemExit("OpenSCAD not found and no edge_body.stl/edge_bezel.stl present")

# ---- scene ----
bpy.ops.wm.read_factory_settings(use_empty=True)

def import_stl(path):
    before = set(bpy.data.objects)
    try:
        bpy.ops.wm.stl_import(filepath=path)
    except Exception:
        bpy.ops.import_mesh.stl(filepath=path)
    return (set(bpy.data.objects) - before).pop()

body  = import_stl(body_stl)
bezel = import_stl(bezel_stl)
for o in (body, bezel):
    o.scale = (S, S, S)
bpy.context.view_layer.update()
bezel.location.z = DEPTH          # bezel caps the front (back face on body top)

# ---- recenter to origin, drop onto z=0 ----
def world_bbox(objs):
    mn = Vector((1e9,)*3); mx = Vector((-1e9,)*3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i]); mx[i] = max(mx[i], w[i])
    return mn, mx
mn, mx = world_bbox([body, bezel])
center = (mn + mx) / 2
for o in (body, bezel):
    o.location.x -= center.x; o.location.y -= center.y; o.location.z -= mn.z
mn, mx = world_bbox([body, bezel])
size = mx - mn; cz = (mn.z + mx.z) / 2; diag = max(size)

# ---- screen (emissive glass) ----
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, mx.z - 0.05))
screen = bpy.context.active_object
screen.scale = (WIN_W*0.985, WIN_H*0.985, 1)

# ---- materials ----
def mat(name):
    m = bpy.data.materials.new(name); m.use_nodes = True
    return m, m.node_tree.nodes["Principled BSDF"]
def setin(b, key, val):
    if key in b.inputs: b.inputs[key].default_value = val

m_body, b = mat("graphite")
setin(b,"Base Color",(0.028,0.03,0.035,1)); setin(b,"Metallic",0.0); setin(b,"Roughness",0.5)
setin(b,"Coat Weight",0.18); setin(b,"Coat Roughness",0.35)
body.data.materials.clear(); body.data.materials.append(m_body)
for p in body.data.polygons: p.material_index = 0

m_bez, b = mat("anodized_alu")
setin(b,"Base Color",(0.66,0.685,0.71,1)); setin(b,"Metallic",1.0); setin(b,"Roughness",0.24)
setin(b,"Coat Weight",0.15)
bezel.data.materials.append(m_bez)

m_scr, b = mat("screen")
setin(b,"Base Color",(0.01,0.02,0.015,1)); setin(b,"Roughness",0.08); setin(b,"Coat Weight",1.0)
setin(b,"Emission Color",(0.03,0.42,0.22,1)); setin(b,"Emission Strength",2.2)
screen.data.materials.append(m_scr)

bpy.ops.mesh.primitive_plane_add(size=24*diag, location=(0,0,0))
floor = bpy.context.active_object
m_fl, b = mat("sweep"); setin(b,"Base Color",(0.05,0.055,0.065,1)); setin(b,"Roughness",0.28)
floor.data.materials.append(m_fl)

# ---- world: soft vertical gradient (ambient + reflections) ----
w = bpy.data.worlds.new("studio"); bpy.context.scene.world = w; w.use_nodes = True
nt = w.node_tree; nt.nodes.clear()
bg   = nt.nodes.new("ShaderNodeBackground")
out  = nt.nodes.new("ShaderNodeOutputWorld")
grad = nt.nodes.new("ShaderNodeTexGradient")
ramp = nt.nodes.new("ShaderNodeValToRGB")
texc = nt.nodes.new("ShaderNodeTexCoord")
mapp = nt.nodes.new("ShaderNodeMapping")
mapp.inputs["Rotation"].default_value = (math.radians(90),0,0)
ramp.color_ramp.elements[0].color=(0.008,0.009,0.012,1)
ramp.color_ramp.elements[1].color=(0.05,0.055,0.07,1)
nt.links.new(texc.outputs["Generated"], mapp.inputs["Vector"])
nt.links.new(mapp.outputs["Vector"], grad.inputs["Vector"])
nt.links.new(grad.outputs["Color"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
bg.inputs["Strength"].default_value = 0.35

# ---- softbox studio lights ----
def area(name, loc, energy, sz):
    l = bpy.data.lights.new(name,'AREA'); l.energy=energy; l.size=sz; l.shape='RECTANGLE'; l.size_y=sz*0.7
    o = bpy.data.objects.new(name,l); bpy.context.collection.objects.link(o); o.location=loc
    o.rotation_euler = (Vector((0,0,cz))-Vector(loc)).to_track_quat('-Z','Y').to_euler()
    return o
area("key",  ( 1.2*diag,-1.2*diag, 1.5*diag), 340, 1.1*diag)
area("fill", (-1.7*diag,-0.5*diag, 0.7*diag),  90, 1.5*diag)
area("rim",  (-0.5*diag, 1.6*diag, 1.2*diag), 300, 1.0*diag)

# ---- camera ----
cam_data = bpy.data.cameras.new("cam"); cam_data.lens = 85
cam = bpy.data.objects.new("cam", cam_data); bpy.context.collection.objects.link(cam)
cam.location = (1.55*diag, -1.7*diag, 0.92*diag)
cam.rotation_euler = (Vector((0,0,cz+0.05))-Vector(cam.location)).to_track_quat('-Z','Y').to_euler()
bpy.context.scene.camera = cam

# ---- render ----
sc = bpy.context.scene
sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'
sc.cycles.samples = 220; sc.cycles.use_denoising = True
sc.render.resolution_x = 1600; sc.render.resolution_y = 1200
sc.view_settings.exposure = -0.6
sc.view_settings.view_transform = 'AgX'
if any(e.identifier=='AgX - Punchy' for e in sc.view_settings.bl_rna.properties['look'].enum_items):
    sc.view_settings.look = 'AgX - Punchy'
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("RENDER_DONE", OUT)
