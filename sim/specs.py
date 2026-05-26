"""Real-world dimensions for the digital twin — no made-up numbers.

Sources are noted per value:
  [repo]  = our own source of truth (pricing / build guide) — authoritative
            for *our* parts.
  [ds]    = vendor datasheet / wiki value for an off-the-shelf part. These are
            nominal; re-verify against the exact revision you buy before you
            cut metal. (Network here is locked down, so these are from the
            published datasheets, not a live fetch.)

All lengths in metres unless the name says _mm.
"""

# ── conveyor belt ────────────────────────────────────────────────────
# Belt width is one of our catalog SKUs. [repo] backend/app/core/pricing.py
# BELT_WIDTHS includes BeltWidth(mm=350, ...). We model the 350 mm line.
BELT_WIDTH   = 0.350        # [repo] 350 mm SKU
BELT_LENGTH  = 1.20         # [typical] short bench/QC conveyor section
BELT_THICK   = 0.003        # [typical] 3 mm PU/PVC food belt
BELT_SPEED   = 0.15         # m/s  [typical] food QC line speed
ROLLER_DIA   = 0.050        # [typical] 50 mm end roller
RAIL_H       = 0.040        # side guide-rail height

# ── tactile mesh (our sensor) ────────────────────────────────────────
# 16 x 16 cell grid. [repo] HARDWARE_BUILD_GUIDE.md builds a 16x16 Velostat
# mesh; we space cells at 10 mm so the active patch is 160 x 160 mm and fits
# inside the 350 mm belt with margin.
MESH_ROWS    = 16
MESH_COLS    = 16
CELL_PITCH   = 0.010        # [repo/derived] 10 mm cell-to-cell
MESH_W       = MESH_COLS * CELL_PITCH   # 0.160 m
MESH_H       = MESH_ROWS * CELL_PITCH   # 0.160 m
MESH_THICK   = 0.004        # laminated Velostat stack ~4 mm

# ── Tactile Edge appliance (Jetson Orin Nano dev kit) ────────────────
# [ds] NVIDIA Jetson Orin Nano Developer Kit mechanical: 103 x 90.5 x 34.77 mm.
JETSON_W     = 0.103
JETSON_D     = 0.0905
JETSON_H     = 0.03477
# [ds] Waveshare 7" HDMI LCD (H): module ~165 x 100 mm; active 154.21 x 85.92
# mm at 1024 x 600. ([repo] guide part D1 = "7" HDMI 1024x600 capacitive".)
DISP_W       = 0.165
DISP_H       = 0.100
DISP_ACT_W   = 0.15421
DISP_ACT_H   = 0.08592
# Our 3D-printed enclosure (hardware/edge_enclosure/edge_enclosure.scad).
# Outer footprint ≈ display + clearance + walls.
ENCL_W       = 0.1758
ENCL_H       = 0.1108
ENCL_D       = 0.064

# ── inspected part (configurable; representative defaults) ───────────
# A small bar/loaf-class part — sized to sit well within the 160 mm mesh.
PART_W       = 0.120
PART_D       = 0.080
PART_H       = 0.040
PART_MASS    = 0.6          # kg
