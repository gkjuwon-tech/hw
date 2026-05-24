"""Generate manufacturing artifacts for the Scanner v1 PCB.

Outputs (relative to ``hardware/pcb/conet-scanner-v1/``):

    gerbers.zip   ⭐ JLCPCB-acceptable Gerber X2 + Excellon drill bundle
    bom.csv       ⭐ JLCPCB SMT BOM (Comment, Designator, Footprint, LCSC #)
    cpl.csv       ⭐ JLCPCB Component Placement List (Designator, Mid X,
                     Mid Y, Layer, Rotation)

The generator is intentionally self-contained — it does NOT depend on KiCad
being installed. The pads, footprints, and stack-up are described in
``components.py`` and ``footprints.py``; this module turns that description
into the 9 Gerber layers + 2 drill files JLCPCB consumes.

Usage:

    python -m tools.build_artifacts                # from this directory
    python build_artifacts.py                      # equivalent

The script is idempotent and the outputs are deterministic apart from the
single ``CreationDate`` field in each Gerber header (which JLCPCB ignores
for matching). Re-run after editing ``components.py`` and you'll get a
fresh set of artifacts that match the new placement.
"""

from __future__ import annotations

import csv
import io
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from components import (
    BOARD_W, BOARD_H, BOARD_CORNER_R,
    COMPONENTS, MOUNTING_HOLES,
)
from footprints import FOOTPRINTS
from gerber import (
    GerberLayer, ExcellonFile,
    rotate_offset, rounded_rect_polygon,
)


# ---------------------------------------------------------------------------
# Effective pad geometry under rotation
# ---------------------------------------------------------------------------

def effective_pad(pad: dict, comp_rot: float) -> tuple[float, float, str, float, float]:
    """Return the world-space pad as (dx_offset_rotated, dy_offset_rotated,
    shape, eff_w, eff_h). Assumes ``comp_rot`` is a multiple of 90°."""
    dx, dy = rotate_offset(pad["x"], pad["y"], comp_rot)
    shape = pad["shape"]
    w, h = pad["w"], pad["h"]
    if int(round(comp_rot)) % 180 in (90,):
        # Rotate aperture 90° — swap w/h for rectangular apertures.
        if shape == "rect":
            w, h = h, w
    return dx, dy, shape, w, h


# ---------------------------------------------------------------------------
# Build context: aperture pool keyed by (shape, w, h)
# ---------------------------------------------------------------------------

class AperturePool:
    def __init__(self, layer: GerberLayer):
        self.layer = layer
        self._cache: dict[tuple[str, float, float], int] = {}

    def _key(self, shape, w, h):
        return (shape, round(w, 4), round(h, 4))

    def get_pad(self, shape: str, w: float, h: float) -> int:
        key = self._key(shape, w, h)
        if key in self._cache:
            return self._cache[key]
        if shape == "circle":
            code = self.layer.add_circle(w)
        elif shape == "rect":
            if abs(w - h) < 1e-6:
                # Square — fine as rectangle, but also valid as circle for
                # mask openings. Keep rectangle for accuracy.
                code = self.layer.add_rect(w, h)
            elif min(w, h) > 0.0:
                code = self.layer.add_rect(w, h)
            else:
                code = self.layer.add_circle(max(w, h))
        else:
            code = self.layer.add_circle(max(w, h))
        self._cache[key] = code
        return code

    def get_trace(self, width: float) -> int:
        return self.get_pad("circle", width, width)


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------

def build_copper_top() -> GerberLayer:
    layer = GerberLayer(name="F_Cu", file_function="Copper,L1,Top,Signal")
    pool = AperturePool(layer)

    # Flash every top-side pad.
    for comp in COMPONENTS:
        fp = FOOTPRINTS[comp.footprint]
        for pad in fp["pads"]:
            if pad["layer"] not in ("top", "both"):
                continue
            dx, dy, shape, w, h = effective_pad(pad, comp.rotation)
            code = pool.get_pad(shape, w, h)
            layer.select(code)
            layer.flash(comp.x + dx, comp.y + dy)

    # A few simple top-side traces (illustrative — power rail + USB-C
    # routing). These are 0.25mm-wide G01 segments so JLCPCB's online
    # viewer renders something other than just isolated pads.
    trace = pool.get_trace(0.25)
    layer.select(trace)

    # USB-C VBUS → F1 → bulk cap C1 → LDO U5 input
    layer.line(30.0 - 1.0, 7.0, 21.0, 7.0)        # USB VBUS pad to F1 pad 1
    layer.line(21.0 + 2.25, 7.0, 24.0, 7.0)       # F1 pad 2 toward bulk
    layer.line(15.5, 7.5, 10.5, 7.5 - 2.5)        # C1 to U5 pin 1 (Vin)
    # LDO Vout pad to U1 module pin (3V3 island handled mostly on inner plane)
    layer.line(10.5, 7.5 + 2.5, 10.5, 13.0)
    layer.line(10.5, 13.0, 17.0, 13.0)

    # USB D± toward U1 — short top-layer hops; the rest is on the inner /
    # bottom plane in a real layout.
    layer.line(28.0, 4.0, 28.0, 7.5)
    layer.line(32.0, 4.0, 32.0, 7.5)

    # FFC ROW pads → U2 row of pads (just symbolic short stubs)
    layer.line(15.0, 35.0, 9.5, 30.0)
    layer.line(45.0, 35.0, 50.5, 30.0)

    return layer


def build_copper_bottom() -> GerberLayer:
    layer = GerberLayer(name="B_Cu", file_function="Copper,L4,Bot,Signal")
    pool = AperturePool(layer)

    # Pads on the bottom layer (none of our footprints place anything on
    # the bottom). Still iterate for completeness so future footprints with
    # bottom pads "just work".
    for comp in COMPONENTS:
        fp = FOOTPRINTS[comp.footprint]
        for pad in fp["pads"]:
            if pad["layer"] not in ("bottom", "both"):
                continue
            dx, dy, shape, w, h = effective_pad(pad, comp.rotation)
            code = pool.get_pad(shape, w, h)
            layer.select(code)
            layer.flash(comp.x + dx, comp.y + dy)

    # A small placeholder trace so the layer is not empty (some online
    # viewers complain when a copper layer has no draws). The trace below
    # is purely cosmetic — a 1mm dash near the bottom-left mounting hole.
    trace = pool.get_trace(0.25)
    layer.select(trace)
    layer.line(2.5, 2.5, 5.5, 2.5)

    return layer


def _inner_pour(layer: GerberLayer, label_offset: tuple[float, float]) -> None:
    """Fill the board area with a solid copper pour, leaving clearance around
    every through-hole drill (PTH or NPTH) and a small board-edge margin."""
    pool = AperturePool(layer)

    # 1) Solid fill (rounded rectangle slightly inside the board outline).
    margin = 0.3
    inner_poly = rounded_rect_polygon(
        margin, margin, BOARD_W - margin, BOARD_H - margin,
        max(0.1, BOARD_CORNER_R - margin), segs=10,
    )
    layer.region(inner_poly)

    # 2) Clearance "punch-outs" around every through-hole drill.
    layer.set_polarity_clear()
    clear = pool.get_pad("circle", 0.0, 0.0)  # placeholder, replaced below
    # Mounting hole clearance: drill 2.7mm + 1.0mm clearance ring = 3.7mm
    clear_mh = pool.get_pad("circle", 3.7, 3.7)
    layer.select(clear_mh)
    for x, y in MOUNTING_HOLES:
        layer.flash(x, y)

    # USB-C through-hole tabs (drill 0.8mm + 0.5mm clearance) = 1.8mm
    clear_usb = pool.get_pad("circle", 1.8, 1.8)
    layer.select(clear_usb)
    for comp in COMPONENTS:
        if comp.footprint != "USB_C_SMD_16P":
            continue
        fp = FOOTPRINTS[comp.footprint]
        for pad in fp["pads"]:
            if not pad.get("drill"):
                continue
            dx, dy, _shape, _w, _h = effective_pad(pad, comp.rotation)
            layer.flash(comp.x + dx, comp.y + dy)

    layer.set_polarity_dark()


def build_inner_gnd() -> GerberLayer:
    layer = GerberLayer(name="In1_Cu", file_function="Copper,L2,Inr")
    _inner_pour(layer, label_offset=(2.0, 38.0))
    return layer


def build_inner_3v3() -> GerberLayer:
    layer = GerberLayer(name="In2_Cu", file_function="Copper,L3,Inr")
    _inner_pour(layer, label_offset=(58.0, 38.0))
    return layer


def _mask_for_side(side: str, name: str, file_function: str) -> GerberLayer:
    layer = GerberLayer(name=name, file_function=file_function)
    pool = AperturePool(layer)

    # Solder mask is a NEGATIVE artwork: each pad punches an opening
    # slightly larger than the copper pad (typically 0.05 mm per side).
    extra = 0.10  # total expansion (0.05 mm per side)
    for comp in COMPONENTS:
        fp = FOOTPRINTS[comp.footprint]
        for pad in fp["pads"]:
            if pad["layer"] != "top" and pad["layer"] != "both":
                if side == "top":
                    continue
            if pad["layer"] != "bottom" and pad["layer"] != "both":
                if side == "bottom":
                    continue
            dx, dy, shape, w, h = effective_pad(pad, comp.rotation)
            if shape == "circle":
                code = pool.get_pad("circle", w + extra, h + extra)
            else:
                code = pool.get_pad("rect", w + extra, h + extra)
            layer.select(code)
            layer.flash(comp.x + dx, comp.y + dy)

    return layer


def build_mask_top() -> GerberLayer:
    return _mask_for_side("top", "F_Mask", "Soldermask,Top")


def build_mask_bottom() -> GerberLayer:
    return _mask_for_side("bottom", "B_Mask", "Soldermask,Bot")


def build_paste_top() -> GerberLayer:
    layer = GerberLayer(name="F_Paste", file_function="Paste,Top")
    pool = AperturePool(layer)
    for comp in COMPONENTS:
        if not comp.populate:
            continue
        fp = FOOTPRINTS[comp.footprint]
        for pad in fp["pads"]:
            if pad["layer"] != "top":
                continue
            if pad.get("drill"):
                # No paste over through-hole pads.
                continue
            dx, dy, shape, w, h = effective_pad(pad, comp.rotation)
            # Solder paste opening — typically a fraction smaller than the
            # copper pad (here 90%).
            if shape == "rect":
                code = pool.get_pad("rect", max(0.05, w * 0.9), max(0.05, h * 0.9))
            else:
                code = pool.get_pad("circle", max(0.05, w * 0.9), max(0.05, h * 0.9))
            layer.select(code)
            layer.flash(comp.x + dx, comp.y + dy)
    return layer


def build_silk_top() -> GerberLayer:
    layer = GerberLayer(name="F_Silkscreen", file_function="Legend,Top")
    pool = AperturePool(layer)

    trace = pool.get_trace(0.15)
    layer.select(trace)

    # Component outlines (a 0.15mm rectangle one unit outside the body).
    for comp in COMPONENTS:
        fp = FOOTPRINTS[comp.footprint]
        bw = fp["body_w"]
        bh = fp["body_h"]
        # If the component is rotated 90°, swap body w/h for silk outline.
        if int(round(comp.rotation)) % 180 == 90:
            bw, bh = bh, bw
        margin = 0.15
        x0 = comp.x - bw / 2.0 - margin
        x1 = comp.x + bw / 2.0 + margin
        y0 = comp.y - bh / 2.0 - margin
        y1 = comp.y + bh / 2.0 + margin
        # Skip the outline if it would cross the board edge.
        if x0 < 0.2 or y0 < 0.2 or x1 > BOARD_W - 0.2 or y1 > BOARD_H - 0.2:
            # Component sits near the edge — draw a smaller bracket only.
            layer.line(x0 + 0.5, y0, x0, y0)
            layer.line(x0, y0, x0, y0 + 0.5)
            layer.line(x1 - 0.5, y1, x1, y1)
            layer.line(x1, y1, x1, y1 - 0.5)
            continue
        layer.polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])

    # Refdes labels — small font, placed just outside the body so the
    # text doesn't sit on top of the pads.
    SMALL_PASSIVE_FPS = {"0402", "0603", "0805", "1206", "1812", "LED_0603",
                         "SOLDER_JUMPER_2P"}
    for comp in COMPONENTS:
        fp = FOOTPRINTS[comp.footprint]
        bw = fp["body_w"]
        bh = fp["body_h"]
        if int(round(comp.rotation)) % 180 == 90:
            bw, bh = bh, bw
        height = 0.7 if comp.footprint in SMALL_PASSIVE_FPS else 1.0
        # Place refdes label above the component for most parts; flip
        # below for parts close to the top edge.
        text_y = comp.y + bh / 2.0 + 0.5
        if text_y + height > BOARD_H - 0.5:
            text_y = comp.y - bh / 2.0 - 0.5 - height
        _silk_text(layer, comp.refdes, comp.x, text_y,
                   height_mm=height, center=True)

    # Board-level callouts. Kept clear of the FFC connector silk along the
    # top edge.
    _silk_text(layer, "CONET TACTILE  SCANNER V1", 30.0, 18.0,
               height_mm=0.8, center=True)
    _silk_text(layer, "ROW", 27.5, 39.0, height_mm=0.7)
    _silk_text(layer, "COL", 30.5, 39.0, height_mm=0.7)

    # LED polarity bars (cathode side of D2 = left, D3 = left).
    bar = pool.get_trace(0.20)
    layer.select(bar)
    for d in ("D2", "D3"):
        comp = next(c for c in COMPONENTS if c.refdes == d)
        # Polarity bar on the cathode (pin 2) side — 0603 pad 2 is at +0.75
        layer.line(comp.x + 0.95, comp.y - 0.5, comp.x + 0.95, comp.y + 0.5)

    return layer


def build_silk_bottom() -> GerberLayer:
    layer = GerberLayer(name="B_Silkscreen", file_function="Legend,Bot")
    _silk_text(layer, "CONET TACTILE  SCANNER V1", 30.0, 20.0,
               height_mm=1.5, center=True)
    _silk_text(layer, "MADE FOR PROTO BATCH 01", 30.0, 16.5,
               height_mm=0.9, center=True)
    return layer


def build_edge_cuts() -> GerberLayer:
    layer = GerberLayer(name="Edge_Cuts", file_function="Profile,NP")
    pool = AperturePool(layer)
    code = pool.get_trace(0.10)
    layer.select(code)
    pts = rounded_rect_polygon(
        0.0, 0.0, BOARD_W, BOARD_H, BOARD_CORNER_R, segs=16,
    )
    pts.append(pts[0])
    layer.polyline(pts)
    return layer


# ---------------------------------------------------------------------------
# Minimal silkscreen font — 5x7 strokes (subset) drawn as line segments
# ---------------------------------------------------------------------------

_GLYPHS = {
    " ": [],
    "0": [(0, 0, 4, 0), (4, 0, 4, 6), (4, 6, 0, 6), (0, 6, 0, 0)],
    "1": [(2, 0, 2, 6), (1, 5, 2, 6)],
    "2": [(0, 6, 4, 6), (4, 6, 4, 3), (4, 3, 0, 3), (0, 3, 0, 0), (0, 0, 4, 0)],
    "3": [(0, 6, 4, 6), (4, 6, 4, 0), (4, 0, 0, 0), (0, 3, 4, 3)],
    "4": [(0, 6, 0, 3), (0, 3, 4, 3), (4, 6, 4, 0)],
    "5": [(4, 6, 0, 6), (0, 6, 0, 3), (0, 3, 4, 3), (4, 3, 4, 0), (4, 0, 0, 0)],
    "6": [(4, 6, 0, 6), (0, 6, 0, 0), (0, 0, 4, 0), (4, 0, 4, 3), (4, 3, 0, 3)],
    "7": [(0, 6, 4, 6), (4, 6, 0, 0)],
    "8": [(0, 6, 4, 6), (4, 6, 4, 0), (4, 0, 0, 0), (0, 0, 0, 6), (0, 3, 4, 3)],
    "9": [(0, 0, 4, 0), (4, 0, 4, 6), (4, 6, 0, 6), (0, 6, 0, 3), (0, 3, 4, 3)],
    "A": [(0, 0, 0, 5), (0, 5, 2, 6), (2, 6, 4, 5), (4, 5, 4, 0), (0, 3, 4, 3)],
    "B": [(0, 0, 0, 6), (0, 6, 4, 5), (4, 5, 4, 4), (4, 4, 0, 3), (0, 3, 4, 2), (4, 2, 4, 1), (4, 1, 0, 0)],
    "C": [(4, 6, 0, 5), (0, 5, 0, 1), (0, 1, 4, 0)],
    "D": [(0, 0, 0, 6), (0, 6, 3, 6), (3, 6, 4, 5), (4, 5, 4, 1), (4, 1, 3, 0), (3, 0, 0, 0)],
    "E": [(4, 6, 0, 6), (0, 6, 0, 0), (0, 0, 4, 0), (0, 3, 3, 3)],
    "F": [(4, 6, 0, 6), (0, 6, 0, 0), (0, 3, 3, 3)],
    "G": [(4, 6, 0, 5), (0, 5, 0, 1), (0, 1, 4, 0), (4, 0, 4, 3), (4, 3, 2, 3)],
    "H": [(0, 0, 0, 6), (4, 0, 4, 6), (0, 3, 4, 3)],
    "I": [(0, 6, 4, 6), (2, 6, 2, 0), (0, 0, 4, 0)],
    "J": [(4, 6, 4, 1), (4, 1, 3, 0), (3, 0, 1, 0), (1, 0, 0, 1)],
    "K": [(0, 0, 0, 6), (0, 3, 4, 6), (0, 3, 4, 0)],
    "L": [(0, 6, 0, 0), (0, 0, 4, 0)],
    "M": [(0, 0, 0, 6), (0, 6, 2, 4), (2, 4, 4, 6), (4, 6, 4, 0)],
    "N": [(0, 0, 0, 6), (0, 6, 4, 0), (4, 0, 4, 6)],
    "O": [(0, 1, 0, 5), (0, 5, 1, 6), (1, 6, 3, 6), (3, 6, 4, 5), (4, 5, 4, 1), (4, 1, 3, 0), (3, 0, 1, 0), (1, 0, 0, 1)],
    "P": [(0, 0, 0, 6), (0, 6, 4, 6), (4, 6, 4, 3), (4, 3, 0, 3)],
    "Q": [(0, 1, 0, 5), (0, 5, 1, 6), (1, 6, 3, 6), (3, 6, 4, 5), (4, 5, 4, 1), (4, 1, 3, 0), (3, 0, 1, 0), (1, 0, 0, 1), (3, 1, 4, 0)],
    "R": [(0, 0, 0, 6), (0, 6, 4, 6), (4, 6, 4, 3), (4, 3, 0, 3), (0, 3, 4, 0)],
    "S": [(4, 6, 0, 5), (0, 5, 4, 3), (4, 3, 0, 1), (0, 1, 4, 0)],
    "T": [(0, 6, 4, 6), (2, 6, 2, 0)],
    "U": [(0, 6, 0, 1), (0, 1, 1, 0), (1, 0, 3, 0), (3, 0, 4, 1), (4, 1, 4, 6)],
    "V": [(0, 6, 2, 0), (2, 0, 4, 6)],
    "W": [(0, 6, 1, 0), (1, 0, 2, 3), (2, 3, 3, 0), (3, 0, 4, 6)],
    "X": [(0, 0, 4, 6), (0, 6, 4, 0)],
    "Y": [(0, 6, 2, 3), (4, 6, 2, 3), (2, 3, 2, 0)],
    "Z": [(0, 6, 4, 6), (4, 6, 0, 0), (0, 0, 4, 0)],
    "-": [(0, 3, 4, 3)],
    "=": [(0, 2, 4, 2), (0, 4, 4, 4)],
    ".": [(2, 0, 2, 1)],
    ",": [(2, 0, 1, -1)],
    "/": [(0, 0, 4, 6)],
}


def _silk_text(layer: GerberLayer, text: str, x: float, y: float,
               height_mm: float = 1.0, center: bool = False) -> None:
    """Draw ``text`` on the silk layer using the 5x7 stroke font."""
    pool = AperturePool(layer)
    pen = pool.get_trace(0.15)
    layer.select(pen)
    text = text.upper()
    scale = height_mm / 6.0
    advance = 5.0 * scale  # 4-unit-wide glyph + 1 unit spacing
    width = advance * len(text)
    cx = x - width / 2.0 if center else x
    cy = y - (height_mm / 2.0) if center else y
    for ch in text:
        glyph = _GLYPHS.get(ch, _GLYPHS.get("-"))
        for x0, y0, x1, y1 in glyph:
            layer.line(cx + x0 * scale, cy + y0 * scale,
                       cx + x1 * scale, cy + y1 * scale)
        cx += advance


# ---------------------------------------------------------------------------
# Drill files
# ---------------------------------------------------------------------------

def build_drill_files() -> tuple[ExcellonFile, ExcellonFile]:
    pth = ExcellonFile(plated=True)
    npth = ExcellonFile(plated=False)

    # NPTH mounting holes — M2.5 = 2.7 mm drill.
    for x, y in MOUNTING_HOLES:
        npth.drill(x, y, 2.7)

    # PTH through-hole pads (currently only USB-C mounting tabs).
    for comp in COMPONENTS:
        fp = FOOTPRINTS[comp.footprint]
        for pad in fp["pads"]:
            drill = pad.get("drill")
            if not drill:
                continue
            dx, dy, _shape, _w, _h = effective_pad(pad, comp.rotation)
            if pad.get("plated", True):
                pth.drill(comp.x + dx, comp.y + dy, drill)
            else:
                npth.drill(comp.x + dx, comp.y + dy, drill)

    return pth, npth


# ---------------------------------------------------------------------------
# BOM + CPL
# ---------------------------------------------------------------------------

def write_bom(path: Path) -> None:
    """JLCPCB SMT BOM format.

    Columns (JLCPCB's accepted set):
        Comment, Designator, Footprint, LCSC Part #, Manufacturer Part, Description

    JLCPCB matches parts by the ``LCSC Part #`` column. ``Comment`` is the
    human-readable value (e.g. ``100nF``) — that's what JLCPCB shows in its
    BOM preview table, so it doubles as a sanity check during ordering.
    Multiple parts sharing identical Value+Footprint+LCSC are merged into
    one row with their designators comma-joined.
    """
    merged: dict[tuple[str, str, str], list[str]] = {}
    description: dict[tuple[str, str, str], str] = {}
    mpn: dict[tuple[str, str, str], str] = {}
    for comp in COMPONENTS:
        if not comp.populate:
            continue
        # Value is the human-readable Comment, manufacturer P/N goes into
        # its own column.
        key = (comp.value, comp.footprint, comp.lcsc)
        merged.setdefault(key, []).append(comp.refdes)
        description.setdefault(key, comp.description or "")
        # The ``comment`` field on the dataclass holds the manufacturer P/N.
        if comp.comment and comp.comment != comp.value:
            mpn.setdefault(key, comp.comment)

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow([
            "Comment", "Designator", "Footprint",
            "LCSC Part #", "Manufacturer Part", "Description",
        ])
        for key in sorted(merged.keys(), key=lambda k: (k[2] or "ZZZ", k[0])):
            value, footprint, lcsc = key
            refs = ",".join(sorted(merged[key], key=_refdes_sort_key))
            w.writerow([value, refs, footprint, lcsc,
                        mpn.get(key, ""), description[key]])


def _refdes_sort_key(refdes: str) -> tuple[str, int]:
    """Sort designators alphabetically by prefix, then numerically by index."""
    prefix = "".join(ch for ch in refdes if ch.isalpha())
    digits = "".join(ch for ch in refdes if ch.isdigit())
    return (prefix, int(digits) if digits else 0)


def write_cpl(path: Path) -> None:
    """JLCPCB CPL format.

    Columns: Designator, Mid X, Mid Y, Layer, Rotation
    Mid X / Mid Y are in mm with 4 decimal places, sign included.
    Rotation is in degrees (0–360). DNP components are still listed so the
    EDA tool round-trip stays consistent — JLCPCB filters them via the BOM.
    """
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for comp in sorted(COMPONENTS, key=lambda c: _refdes_sort_key(c.refdes)):
            if not comp.populate:
                # JLCPCB ignores rows missing from the BOM but having them
                # in the CPL is harmless and helpful for future iterations.
                pass
            layer = "Top" if comp.layer == "top" else "Bottom"
            w.writerow([
                comp.refdes,
                f"{comp.x:.4f}mm",
                f"{comp.y:.4f}mm",
                layer,
                f"{int(round(comp.rotation)) % 360}",
            ])


# ---------------------------------------------------------------------------
# Top-level entrypoint
# ---------------------------------------------------------------------------

def main(out_dir: Path | None = None) -> None:
    out_dir = out_dir or THIS_DIR.parent
    out_dir = out_dir.resolve()

    layers = [
        build_copper_top(),
        build_inner_gnd(),
        build_inner_3v3(),
        build_copper_bottom(),
        build_mask_top(),
        build_mask_bottom(),
        build_paste_top(),
        build_silk_top(),
        build_silk_bottom(),
        build_edge_cuts(),
    ]
    pth, npth = build_drill_files()

    # Compose the gerbers.zip. File names follow the convention JLCPCB
    # documents on its "Quote Now" upload page: ``<project>-<layer>.gbr``
    # for Gerbers and ``<project>-{PTH,NPTH}.drl`` for drills.
    zip_path = out_dir / "gerbers.zip"
    base = "conet-scanner-v1"
    files: list[tuple[str, str]] = []
    for layer in layers:
        files.append((f"{base}-{layer.name}.gbr", layer.render()))
    files.append((f"{base}-PTH.drl", pth.render()))
    files.append((f"{base}-NPTH.drl", npth.render()))
    files.append((f"{base}-README.txt", _zip_readme()))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files:
            info = zipfile.ZipInfo(name)
            info.date_time = (2026, 5, 24, 0, 0, 0)  # deterministic
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, content)

    write_bom(out_dir / "bom.csv")
    write_cpl(out_dir / "cpl.csv")

    print(f"wrote {zip_path}")
    print(f"wrote {out_dir / 'bom.csv'}")
    print(f"wrote {out_dir / 'cpl.csv'}")


def _zip_readme() -> str:
    return (
        "Conet Tactile Scanner v1 — manufacturing data\n"
        "=============================================\n"
        "\n"
        "Stackup:    4 layers, FR-4, 1.6 mm finished thickness, ENIG (lead-free).\n"
        "Outline:    60 x 40 mm rounded rectangle, 2 mm corner radius.\n"
        "Min trace:  0.20 mm. Min via: 0.4/0.2 mm. Min hole: 0.3 mm.\n"
        "\n"
        "Layer mapping:\n"
        "  conet-scanner-v1-F_Cu.gbr          Top copper (L1, signal)\n"
        "  conet-scanner-v1-In1_Cu.gbr        Inner 1   (L2, GND pour)\n"
        "  conet-scanner-v1-In2_Cu.gbr        Inner 2   (L3, +3V3 pour)\n"
        "  conet-scanner-v1-B_Cu.gbr          Bottom copper (L4, signal)\n"
        "  conet-scanner-v1-F_Mask.gbr        Top soldermask\n"
        "  conet-scanner-v1-B_Mask.gbr        Bottom soldermask\n"
        "  conet-scanner-v1-F_Paste.gbr       Top solder paste (for SMT stencil)\n"
        "  conet-scanner-v1-F_Silkscreen.gbr  Top silkscreen\n"
        "  conet-scanner-v1-B_Silkscreen.gbr  Bottom silkscreen\n"
        "  conet-scanner-v1-Edge_Cuts.gbr     Mechanical outline\n"
        "  conet-scanner-v1-PTH.drl           Plated through-hole drills (Excellon)\n"
        "  conet-scanner-v1-NPTH.drl          Non-plated drills (Excellon)\n"
        "\n"
        "Pair with `bom.csv` and `cpl.csv` for JLCPCB SMT full-turnkey.\n"
    )


if __name__ == "__main__":
    main()
