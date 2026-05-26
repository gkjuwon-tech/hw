// =====================================================================
//  Conet Tactile — Edge appliance enclosure  (parametric, OpenSCAD)
// =====================================================================
//  A line-side "product" shell for the Tactile Edge box: the 7" touch
//  display sits in the front bezel, the Jetson Orin Nano Developer Kit
//  (with its heatsink/fan) tucks in behind it, and the back plate carries
//  a VESA-75 mount, cooling vents, and a cable exit. Prints in 2 parts
//  that screw together with M3 heat-set inserts.
//
//  Units: millimetres.
//
//  ⚠ The dimensions below are NOMINAL. Measure YOUR display module and
//    YOUR dev kit (board mounting-hole pattern especially) and tweak the
//    "measured inputs" block, then test-fit before the final long print.
//
//  Export:
//    openscad -D 'part="body"'  -o edge_body.stl  edge_enclosure.scad
//    openscad -D 'part="bezel"' -o edge_bezel.stl edge_enclosure.scad
//  Preview both assembled:   set part="preview" in the GUI.
//  Print layout (side by side): part="all".
// ---------------------------------------------------------------------

part = "preview";   // "body" | "bezel" | "all" | "preview"

$fn = 48;

// ---- measured inputs (CONFIRM against your hardware) ----------------
// 7" display module (e.g. Waveshare 7" HDMI LCD (H), with case):
disp_w   = 165;   // module outer width
disp_h   = 100;   // module outer height
disp_th  = 16;    // module thickness (panel + touch + PCB)
win_w    = 154;   // visible active-area width  (the window we cut)
win_h    = 86;    // visible active-area height
win_off_y = 0;    // active-area offset from module centre (+ = up)

// Jetson Orin Nano Developer Kit (board + heatsink/fan stack):
jet_w = 103;      // (reference only — used for the fit assertion below)
jet_d = 90.5;
jet_h = 35;       // heatsink/fan stack height above the board
jet_standoff_h = 4;          // lift the board for airflow under it
// 4 board mounting holes as [x, y] from the board centre.
// SET THESE to your measured carrier-board hole pattern:
jet_holes = [[-44, -30], [44, -30], [-44, 30], [44, 30]];

// ---- shell ----------------------------------------------------------
wall      = 2.4;   // side-wall thickness
bezel_th  = 3.0;   // front face thickness (around the window)
back_th   = 2.8;   // back plate thickness
gap       = 3;     // clearance around the display inside the shell
corner_r  = 6;     // outer rounded-corner radius
clearance_z = 3;   // air gap between display back and Jetson heatsink
disp_pocket = 5;   // how deep the display seats into the bezel from behind

// ---- fasteners ------------------------------------------------------
insert_d    = 4.0; // pilot hole for an M3 brass heat-set insert
screw_clear = 3.4; // M3 clearance hole
screw_head  = 6.2; // M3 cap-head / countersink diameter
vesa        = 75;  // VESA mount square on the back plate
vesa_hole   = 4.2; // VESA M4 clearance

// ---- vents ----------------------------------------------------------
vent_w = 2.4; vent_len = 30; vent_pitch = 6; vent_rows = 7;

// ---- derived --------------------------------------------------------
outer_w = disp_w + 2*gap + 2*wall;
outer_h = disp_h + 2*gap + 2*wall;
depth   = bezel_th + disp_th + clearance_z + jet_standoff_h + jet_h + back_th;

edge_inset = wall + 4;
bx = outer_w/2 - edge_inset;
by = outer_h/2 - edge_inset;
boss_pos = [[bx, by], [-bx, by], [bx, -by], [-bx, -by]];

// Sanity: warn if the Jetson stack won't fit behind the display.
assert(jet_w <= disp_w && jet_d <= disp_h,
       "Jetson footprint is larger than the display — grow disp_w/disp_h.");

// =====================================================================
//  primitives
// =====================================================================
module rbox(w, h, d, r) {
  hull() for (sx = [-1, 1], sy = [-1, 1])
    translate([sx*(w/2 - r), sy*(h/2 - r), 0]) cylinder(h = d, r = r);
}

// =====================================================================
//  BODY  (walls + back plate + Jetson standoffs + vents + VESA + bosses)
// =====================================================================
module back_vents() {
  total = (vent_rows - 1) * vent_pitch;
  for (i = [0 : vent_rows - 1])
    translate([0, total/2 - i*vent_pitch, -1])
      rbox(vent_len, vent_w, back_th + 2, vent_w/2);
}

module vesa_holes() {
  for (sx = [-1, 1], sy = [-1, 1])
    translate([sx*vesa/2, sy*vesa/2, -1])
      cylinder(h = back_th + 2, d = vesa_hole);
}

module jet_standoffs() {
  for (p = jet_holes)
    translate([p[0], p[1], 0]) difference() {
      cylinder(h = jet_standoff_h, d = insert_d + 3.5);
      translate([0, 0, -1]) cylinder(h = jet_standoff_h + 2, d = insert_d);
    }
}

module bezel_bosses() {
  h = depth - back_th - bezel_th;
  for (p = boss_pos)
    translate([p[0], p[1], back_th]) difference() {
      cylinder(h = h, d = insert_d + 4);
      // insert pocket opens toward the FRONT (top here)
      translate([0, 0, h - 8]) cylinder(h = 9, d = insert_d);
    }
}

module body() {
  difference() {
    rbox(outer_w, outer_h, depth, corner_r);            // solid outer
    translate([0, 0, back_th])                          // hollow + open front
      rbox(outer_w - 2*wall, outer_h - 2*wall, depth, max(corner_r - wall, 1));
    back_vents();                                        // back-plate vents
    vesa_holes();                                        // VESA-75 pattern
    // cable exit through the bottom wall, just above the back plate
    translate([0, -outer_h/2 + wall/2, back_th + 8])
      rotate([90, 0, 0]) cylinder(h = wall + 4, d = 14, center = true);
  }
  translate([0, 0, back_th]) jet_standoffs();           // board mounts
  bezel_bosses();                                        // bezel screw posts
}

// =====================================================================
//  BEZEL  (front face: display window + retaining pocket + screw holes)
// =====================================================================
module bezel() {
  plate = bezel_th + disp_pocket;
  difference() {
    rbox(outer_w, outer_h, plate, corner_r);
    // see-through window for the active area
    translate([0, win_off_y, -1]) rbox(win_w, win_h, plate + 2, 2);
    // pocket the display seats into, from behind
    translate([0, 0, bezel_th]) rbox(disp_w + 0.6, disp_h + 0.6, disp_pocket + 1, 3);
    // corner screws: clearance through + countersink on the front face
    for (p = boss_pos) translate([p[0], p[1], -1]) {
      cylinder(h = plate + 2, d = screw_clear);
      cylinder(h = 2.6, d = screw_head);
    }
  }
}

// =====================================================================
//  output selector
// =====================================================================
module preview() {
  color("DimGray") body();
  // place the bezel at the front of the body, flipped to face outward
  color("Gainsboro")
    translate([0, 0, depth + (bezel_th + disp_pocket)])
      rotate([180, 0, 0]) bezel();
}

if (part == "body")        body();
else if (part == "bezel")  bezel();
else if (part == "all") {  // flat, side by side for the print bed
  body();
  translate([outer_w + 10, 0, 0]) bezel();
}
else                       preview();
