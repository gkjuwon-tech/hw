// =====================================================================
//  Conet Tactile — Edge appliance enclosure  (parametric, OpenSCAD)
// =====================================================================
//  A line-side vision-sensor "product" shell (Cognex/Keyence register):
//  the 7" touch display sits behind a crisp chamfered bezel that stands
//  slightly proud of the body; the Jetson Orin Nano Developer Kit tucks
//  into the body behind it; the back plate carries a VESA-75 mount and a
//  cable exit; the sides carry a machined vent grille.
//
//  Styling is all *subtractive* (chamfers, fillets, slots) — no thin
//  protruding decoration that would snap. Chamfered edges are stronger
//  than sharp ones and print cleanly.
//
//  Units: millimetres. Prints in 2 parts (body + bezel), M3 inserts.
//
//  ⚠ Dimensions are NOMINAL. Measure your display + your dev-kit board
//    hole pattern (`jet_holes`), then test-fit before the final print.
//
//  Export:
//    openscad -D 'part="body"'  -o edge_body.stl  edge_enclosure.scad
//    openscad -D 'part="bezel"' -o edge_bezel.stl edge_enclosure.scad
//  Preview both assembled:   part="preview".   Print layout: part="all".
// ---------------------------------------------------------------------

part = "preview";   // "body" | "bezel" | "all" | "preview"

$fn = 64;

// ---- measured inputs (CONFIRM against your hardware) ----------------
disp_w   = 165;   // 7" display module outer width
disp_h   = 100;   // module outer height
disp_th  = 16;    // module thickness (panel + touch + PCB)
win_w    = 154;   // visible active-area width  (the window we cut)
win_h    = 86;    // visible active-area height
win_off_y = 0;    // active-area offset from module centre (+ = up)

jet_w = 103;      // Jetson Orin Nano dev kit (board) — fit reference
jet_d = 90.5;
jet_h = 35;       // heatsink/fan stack height above the board
jet_standoff_h = 4;
jet_holes = [[-44, -30], [44, -30], [-44, 30], [44, 30]];  // SET to your board

// ---- shell ----------------------------------------------------------
wall        = 2.6;
bezel_th    = 3.0;   // bezel face thickness around the window
back_th     = 3.0;   // back plate thickness
gap         = 3;     // clearance around the display inside the bezel
corner_r    = 7;     // outer rounded-corner radius
clearance_z = 3;     // gap between display back and Jetson heatsink
disp_pocket = 6;     // depth the display seats into the bezel from behind

// ---- styling (all subtractive — strong, no fragile bits) ------------
front_cham  = 6;     // 45° chamfer on the bezel's front face edge
back_cham   = 4;     // 45° chamfer on the body's back edge ("floating" look)
bezel_proud = 1.6;   // how far the bezel stands beyond the body sides
bezel_step  = 1.2;   // depth of the shadow-line step under the bezel

// ---- vents (side grille) --------------------------------------------
vent_h = 2.4; vent_len = 46; vent_pitch = 6.5; vent_rows = 6;

// ---- fasteners ------------------------------------------------------
insert_d    = 4.0;   // M3 brass heat-set insert pilot hole
screw_clear = 3.4;   // M3 clearance
screw_head  = 6.2;   // M3 countersink diameter
vesa        = 75;
vesa_hole   = 4.2;

// ---- derived --------------------------------------------------------
outer_w = disp_w + 2*gap + 2*wall;
outer_h = disp_h + 2*gap + 2*wall;
depth   = bezel_th + disp_th + clearance_z + jet_standoff_h + jet_h + back_th;
bezel_w = outer_w + 2*bezel_proud;
bezel_h = outer_h + 2*bezel_proud;

edge_inset = wall + 6;                       // bezel-boss inset (clears inner wall)
bx = outer_w/2 - edge_inset;
by = outer_h/2 - edge_inset;
boss_pos = [[bx, by], [-bx, by], [bx, -by], [-bx, -by]];
embed = 0.8;                                 // sink posts into the back plate

assert(jet_w <= disp_w && jet_d <= disp_h,
       "Jetson footprint is larger than the display — grow disp_w/disp_h.");

// =====================================================================
//  primitives
// =====================================================================
module rbox(w, h, d, r) {
  hull() for (sx = [-1, 1], sy = [-1, 1])
    translate([sx*(w/2 - r), sy*(h/2 - r), 0]) cylinder(h = d, r = r);
}

// material to remove for a 45° chamfer along the BOTTOM (z=0) outer edge
module cham_bottom(w, h, r, ch) {
  difference() {
    translate([0, 0, -0.1]) rbox(w + 8, h + 8, ch + 0.2, r + 4);
    hull() {
      translate([0, 0, -0.2]) rbox(w - 2*ch, h - 2*ch, 0.1, max(r - ch, 0.8));
      translate([0, 0, ch + 0.1]) rbox(w, h, 0.1, r);
    }
  }
}

// material to remove for a 45° chamfer along the TOP (z=d) outer edge
module cham_top(w, h, r, ch, d) {
  difference() {
    translate([0, 0, d - ch - 0.1]) rbox(w + 8, h + 8, ch + 0.2, r + 4);
    hull() {
      translate([0, 0, d - ch - 0.2]) rbox(w, h, 0.1, r);
      translate([0, 0, d + 0.1]) rbox(w - 2*ch, h - 2*ch, 0.1, max(r - ch, 0.8));
    }
  }
}

// =====================================================================
//  BODY
// =====================================================================
module side_vents() {
  total = (vent_rows - 1) * vent_pitch;
  for (side = [-1, 1])
    for (i = [0 : vent_rows - 1])
      translate([side*outer_w/2, 0, back_th + 9 + total/2 - i*vent_pitch])
        cube([wall + 8, vent_len, vent_h], center = true);
}

module vesa_holes() {
  for (sx = [-1, 1], sy = [-1, 1])
    translate([sx*vesa/2, sy*vesa/2, -1]) cylinder(h = back_th + 2, d = vesa_hole);
}

module jet_standoffs() {
  for (p = jet_holes)
    translate([p[0], p[1], -embed]) difference() {
      cylinder(h = jet_standoff_h + embed, d = insert_d + 3.5);
      translate([0, 0, 1]) cylinder(h = jet_standoff_h + embed, d = insert_d);
    }
}

module bezel_bosses() {
  h = depth - back_th - bezel_step;
  for (p = boss_pos)
    translate([p[0], p[1], back_th - embed]) difference() {
      cylinder(h = h + embed, d = insert_d + 4);
      translate([0, 0, h + embed - 8]) cylinder(h = 9, d = insert_d);
    }
}

module body() {
  difference() {
    rbox(outer_w, outer_h, depth, corner_r);
    translate([0, 0, back_th])
      rbox(outer_w - 2*wall, outer_h - 2*wall, depth, max(corner_r - wall, 1));
    cham_bottom(outer_w, outer_h, corner_r, back_cham);   // floating back edge
    // a shallow step at the very front so the bezel reads as a proud frame
    translate([0, 0, depth - bezel_step])
      rbox(outer_w - 2*wall + 0.4, outer_h - 2*wall + 0.4, bezel_step + 1, corner_r - 1);
    side_vents();
    vesa_holes();
    translate([0, -outer_h/2 + wall/2, back_th + 9])
      rotate([90, 0, 0]) cylinder(h = wall + 4, d = 14, center = true);
  }
  translate([0, 0, back_th]) jet_standoffs();
  bezel_bosses();
}

// =====================================================================
//  BEZEL  (proud chamfered frame + display window + pocket + screws)
// =====================================================================
module bezel() {
  plate = bezel_th + disp_pocket;
  difference() {
    rbox(bezel_w, bezel_h, plate, corner_r + bezel_proud);
    cham_top(bezel_w, bezel_h, corner_r + bezel_proud, front_cham, plate);  // sleek front edge
    translate([0, win_off_y, -1]) rbox(win_w, win_h, plate + 2, 3);          // window
    translate([0, 0, bezel_th]) rbox(disp_w + 0.6, disp_h + 0.6, disp_pocket + 1, 3); // display pocket
    for (p = boss_pos) translate([p[0], p[1], -1]) {                          // corner screws
      cylinder(h = plate + 2, d = screw_clear);
      cylinder(h = 2.8, d = screw_head);
    }
  }
}

// =====================================================================
//  render-only mock-ups (NOT exported — only body/bezel are printed)
// =====================================================================
module mock_jetson() {
  color("#0b3d1f") translate([0, 0, back_th + jet_standoff_h]) rbox(jet_w, jet_d, jet_h, 3);
}
module mock_screen() {
  color("#0d2a18") translate([0, win_off_y, depth - 1]) rbox(win_w - 1, win_h - 1, 2, 2);
}

module preview() {
  mock_jetson();
  mock_screen();
  color("#23262b") body();
  color("#dfe2e6")
    translate([0, 0, depth + (bezel_th + disp_pocket)]) rotate([180, 0, 0]) bezel();
}

if (part == "body")        body();
else if (part == "bezel")  bezel();
else if (part == "all") { body(); translate([bezel_w + 12, 0, 0]) bezel(); }
else                       preview();
