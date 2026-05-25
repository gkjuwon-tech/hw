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
from hershey_simplex import GLYPH_SEGMENTS, GLYPH_ADVANCE, CAP_HEIGHT_UNITS, BASELINE_Y


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

def _trace45(layer: GerberLayer,
             x0: float, y0: float, x1: float, y1: float,
             prefer: str = "h") -> None:
    """Draw an L-shaped trace from ``(x0, y0)`` to ``(x1, y1)`` with a 45°
    chamfer instead of a 90° corner. ``prefer='h'`` routes horizontally
    first then vertically; ``'v'`` does the opposite. If the two endpoints
    are colinear, the trace is a single straight segment.
    """
    if abs(x0 - x1) < 1e-6 or abs(y0 - y1) < 1e-6:
        layer.line(x0, y0, x1, y1)
        return
    dx = x1 - x0
    dy = y1 - y0
    chamfer = min(abs(dx), abs(dy))
    sx = 1.0 if dx > 0 else -1.0
    sy = 1.0 if dy > 0 else -1.0
    if prefer == "h":
        # straight horizontal, 45 \u00b0 down, straight vertical
        mid_x = x1 - sx * chamfer
        mid_y_start = y0
        mid_y_end = y0 + sy * chamfer
        layer.line(x0, y0, mid_x, mid_y_start)
        layer.line(mid_x, mid_y_start, mid_x + sx * chamfer, mid_y_end)
        layer.line(mid_x + sx * chamfer, mid_y_end, x1, y1)
    else:
        mid_y = y1 - sy * chamfer
        layer.line(x0, y0, x0, mid_y)
        layer.line(x0, mid_y, x0 + sx * chamfer, mid_y + sy * chamfer)
        layer.line(x0 + sx * chamfer, mid_y + sy * chamfer, x1, y1)


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

    # Top-side signal routing — illustrative power and high-priority signal
    # paths. All segments use 0.25 mm-wide traces with 45° corners; GND and
    # +3V3 are carried by the inner pours so we don't need to route them
    # here.
    trace = pool.get_trace(0.25)
    layer.select(trace)

    # USB-C VBUS (5 V) → PTC fuse F1 → bulk cap C1 → LDO U5 Vin
    _trace45(layer, 28.0, 5.6, 21.0 - 2.25, 7.0, prefer="v")
    layer.line(21.0 + 2.25, 7.0, 15.5, 7.0)
    _trace45(layer, 15.5, 7.0, 10.5, 5.5, prefer="v")  # to U5 Vin

    # LDO Vout (U5 pin 2) → +3V3 vias landing pad → U1 pin 2 (3V3) on the
    # bottom row.
    layer.line(10.5, 9.5, 10.5, 12.0)
    _trace45(layer, 10.5, 12.0, 20.5, 13.0, prefer="h")

    # USB D-/D+ pair (USB-C pads P5/P7 → ESD D1 → ESP32 USB pins on the
    # bottom row of U1).
    _trace45(layer, 27.0, 5.6, 44.5, 7.0, prefer="h")  # D+
    _trace45(layer, 32.0, 5.6, 44.5, 7.0, prefer="h")  # D-
    # Continue from D1 to U1 bottom row (pins 14 / 15).
    _trace45(layer, 44.5, 7.0, 27.0, 13.0, prefer="v")
    _trace45(layer, 44.5, 7.0, 28.3, 13.0, prefer="v")

    # FFC ROW header → U2 (left MUX) Y0..Y15 — symbolic teaser of the 16
    # mesh-row lines fanning out to the multiplexer.
    for i in range(16):
        x_start = 15.0 - 7.5 + i * 1.0
        # Endpoint on U2's right edge (the chip is rotated 90°, so its
        # signal-side pads run along Y at x ≈ 9.5 + 7.62/2 = 13.31).
        y_end = 22.0 - 7.62 / 2.0 + (15 - i) * 7.62 / 15.0
        _trace45(layer, x_start, 35.8, 13.3, y_end, prefer="v")

    # FFC COL header → U3 (right MUX) Y0..Y15.
    for i in range(16):
        x_start = 45.0 - 7.5 + i * 1.0
        y_end = 22.0 - 7.62 / 2.0 + (15 - i) * 7.62 / 15.0
        _trace45(layer, x_start, 35.8, 46.7, y_end, prefer="v")

    # ROW_S0..S3 — ESP32 GPIO 4..7 (U1 pins 5..8 on the bottom row) → U2
    # select inputs (pins 10..13 along U2's top edge).
    for i, pin_x in enumerate([
        # U1 pin positions on the bottom row, x = ±long_span/2 + idx * 1.27
        # Pin 5 is index 3 from pin 2, so x = -10.795 + 3 * 1.27 = -6.985
        # Then add U1.x = 30.0 → 23.015. Similarly pins 6/7/8.
        23.015, 24.285, 25.555, 26.825,
    ]):
        # U2's top-edge SOIC pads are on its (-y) side after 90° rotation.
        # Pad positions: rotated SOIC pads land along x = 9.5 ± 0.85 mm,
        # spaced 1.27 mm in Y. Approximate the destination here.
        target_x = 9.5 + 1.78
        target_y = 22.0 - 1.27 * (4 - i)
        _trace45(layer, pin_x, 13.5, target_x, target_y, prefer="v")

    # COL_S0..S3 — ESP32 GPIO 15..18 (U1 pins 9..12 on bottom row) → U3.
    for i, pin_x in enumerate([28.095, 29.365, 30.635, 31.905]):
        target_x = 50.5 - 1.78
        target_y = 22.0 - 1.27 * (4 - i)
        _trace45(layer, pin_x, 13.5, target_x, target_y, prefer="v")

    # ADC_IN — U2 SIG (top-edge pin 1 = COM on rotated SOIC) → R30 → U1
    # pin 41 (ADC1_CH0 = GPIO 1) on top row.
    _trace45(layer, 10.7, 28.0, 53.0, 22.0, prefer="h")  # symbolic only

    # LED current paths.
    _trace45(layer, 39.0, 33.0, 41.0, 33.0, prefer="h")  # R20 to D2
    _trace45(layer, 43.0, 33.0, 45.0, 33.0, prefer="h")  # R21 to D3

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

    # Solid GND pour. Without this, USB D+/D- on the top layer have no
    # adjacent reference plane on the back side of the board (the In1 GND
    # pour is two dielectric layers away), so high-speed return currents
    # find any nearby copper -- digital aggressor traces, the antenna
    # keep-out -- and the resulting USB eye gets ugly. JLCPCB's free 4-
    # layer service builds the stackup as Top / In1 / In2 / Bot with the
    # outer two being signal layers; if we tape out with an empty Bot we
    # lose half the impedance-control headroom for nothing. Use the same
    # punch-out pattern as the inner planes so the via stitching from the
    # GND pour up to GND-net SMD pads stays sane.
    _inner_pour(layer, label_offset=(2.0, 2.0))

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


# Footprints whose silk outline + refdes label should sit OUTSIDE the body,
# never on top of pads, and whose refdes can use a slightly smaller font.
SMALL_PASSIVE_FPS = {"0402", "0603", "0805", "1206", "1812", "LED_0603",
                     "SOLDER_JUMPER_2P"}
# Footprints that physically cover their own silk (modules / shielded cans /
# connector housings) — skip the body outline because the part will hide it,
# and place the refdes well clear of the body so it remains visible after
# assembly.
COVERED_FPS = {"ESP32_S3_WROOM_1", "USB_C_SMD_16P", "FFC_16P_1MM",
               "TACT_4P_4.5x4.5"}


def _body_bbox(comp) -> tuple[float, float, float, float]:
    """Axis-aligned bounding box of ``comp`` in world coords (x0, y0, x1, y1)."""
    fp = FOOTPRINTS[comp.footprint]
    bw, bh = fp["body_w"], fp["body_h"]
    if int(round(comp.rotation)) % 180 == 90:
        bw, bh = bh, bw
    return (comp.x - bw / 2.0, comp.y - bh / 2.0,
            comp.x + bw / 2.0, comp.y + bh / 2.0)


def _rect_overlaps_any_body(x0: float, y0: float, x1: float, y1: float,
                             skip_refdes: str) -> bool:
    """True if the rectangle overlaps any component body other than the
    one identified by ``skip_refdes``."""
    for other in COMPONENTS:
        if other.refdes == skip_refdes:
            continue
        ox0, oy0, ox1, oy1 = _body_bbox(other)
        if x1 < ox0 or x0 > ox1 or y1 < oy0 or y0 > oy1:
            continue
        return True
    return False


def _label_position(comp, text_height: float) -> tuple[float, float, bool]:
    """Return (x, y, center) for the refdes label of ``comp`` so that:

    - the label doesn't sit on any pad of the component,
    - it stays inside the board (with a 0.5 mm margin),
    - it doesn't overlap any other component's body,
    - it falls above the body where possible, otherwise below, then right
      then left.
    """
    fp = FOOTPRINTS[comp.footprint]
    bw, bh = fp["body_w"], fp["body_h"]
    if int(round(comp.rotation)) % 180 == 90:
        bw, bh = bh, bw
    gap = 0.45
    half_text_w = max(1.5, len(comp.refdes) * text_height * 0.5)
    candidates = [
        # (x, y, center, label_bbox)
        ("above", comp.x, comp.y + bh / 2.0 + gap, True,
         (comp.x - half_text_w, comp.y + bh / 2.0 + gap,
          comp.x + half_text_w, comp.y + bh / 2.0 + gap + text_height)),
        ("below", comp.x, comp.y - bh / 2.0 - gap - text_height, True,
         (comp.x - half_text_w, comp.y - bh / 2.0 - gap - text_height,
          comp.x + half_text_w, comp.y - bh / 2.0 - gap)),
        ("right", comp.x + bw / 2.0 + gap, comp.y - text_height / 2.0, False,
         (comp.x + bw / 2.0 + gap, comp.y - text_height / 2.0,
          comp.x + bw / 2.0 + gap + 2 * half_text_w,
          comp.y + text_height / 2.0)),
        ("left", comp.x - bw / 2.0 - gap - 2 * half_text_w,
         comp.y - text_height / 2.0, False,
         (comp.x - bw / 2.0 - gap - 2 * half_text_w,
          comp.y - text_height / 2.0,
          comp.x - bw / 2.0 - gap, comp.y + text_height / 2.0)),
    ]
    for _name, lx, ly, center, (bx0, by0, bx1, by1) in candidates:
        if bx0 < 0.4 or by0 < 0.4 or bx1 > BOARD_W - 0.4 or by1 > BOARD_H - 0.4:
            continue
        if _rect_overlaps_any_body(bx0, by0, bx1, by1, comp.refdes):
            continue
        return lx, ly, center
    # No free position — default to "above" anyway; the silkmask is small
    # enough that minor overlap is acceptable on a tight EVT board.
    fx, fy, fc, _ = candidates[0][1:5] if False else (
        comp.x, comp.y + bh / 2.0 + gap, True, None)
    return fx, fy, fc


def _logo(layer: GerberLayer, x: float, y: float, size: float = 3.0) -> None:
    """CONET mesh-mark — a small 4×4 grid with one highlighted cell,
    evoking the row/column tactile mesh this board scans. Centered at
    (x, y); enclosing square side = ``size`` mm.
    """
    pool = AperturePool(layer)
    pen = pool.get_trace(0.15)
    layer.select(pen)
    s = size / 2.0
    # Outer rounded square frame.
    corner = min(0.3, s * 0.25)
    layer.polyline(rounded_rect_polygon(
        x - s, y - s, x + s, y + s, corner, segs=4,
    ) + [(x - s + corner, y - s)])
    # 4-by-4 grid lines.
    n = 4
    for i in range(1, n):
        t = i / n
        layer.line(x - s + t * size, y - s, x - s + t * size, y + s)
        layer.line(x - s, y - s + t * size, x + s, y - s + t * size)
    # Highlighted cell at (2, 2) — small filled dot indicating a touch.
    cell = size / n
    dot_r = cell * 0.30
    dot = pool.get_pad("circle", dot_r * 2.0, dot_r * 2.0)
    layer.select(dot)
    layer.flash(x - s + 2.5 * cell, y - s + 2.5 * cell)
    layer.select(pen)


def _title_block(layer: GerberLayer, x: float, y: float) -> None:
    """Title block — project ID + revision + batch in a framed rectangle.
    ``(x, y)`` is the bottom-right corner of the frame in board coords.
    """
    pool = AperturePool(layer)
    pen = pool.get_trace(0.13)
    layer.select(pen)
    w, h = 10.5, 3.0
    # Frame.
    layer.polyline([
        (x - w, y), (x, y), (x, y + h), (x - w, y + h), (x - w, y),
    ])
    # Internal divider.
    layer.line(x - w, y + h * 0.55, x, y + h * 0.55)
    # Text — project / rev on top row, batch / EVT on bottom row.
    _silk_text(layer, "CONET SCANNER V1", x - w / 2.0, y + h * 0.77,
               height_mm=0.55, center=True)
    _silk_text(layer, "PROTO BATCH 01 / EVT", x - w / 2.0, y + h * 0.22,
               height_mm=0.5, center=True)


def build_silk_top() -> GerberLayer:
    layer = GerberLayer(name="F_Silkscreen", file_function="Legend,Top")
    pool = AperturePool(layer)

    body_pen = pool.get_trace(0.15)
    layer.select(body_pen)

    # Component outlines — only for parts whose body silk is useful after
    # assembly (so: NOT modules / connectors / shielded cans).
    for comp in COMPONENTS:
        if comp.footprint in COVERED_FPS:
            continue
        fp = FOOTPRINTS[comp.footprint]
        bw = fp["body_w"]
        bh = fp["body_h"]
        if int(round(comp.rotation)) % 180 == 90:
            bw, bh = bh, bw
        margin = 0.15
        x0 = comp.x - bw / 2.0 - margin
        x1 = comp.x + bw / 2.0 + margin
        y0 = comp.y - bh / 2.0 - margin
        y1 = comp.y + bh / 2.0 + margin
        # Skip the outline if it would cross the board edge.
        if x0 < 0.4 or y0 < 0.4 or x1 > BOARD_W - 0.4 or y1 > BOARD_H - 0.4:
            continue
        # For tiny passives the silk outline tends to overlap with adjacent
        # parts — just draw two corner brackets so the polarity stays
        # readable without cluttering.
        if comp.footprint in SMALL_PASSIVE_FPS:
            b = 0.25
            layer.line(x0, y0 + b, x0, y0); layer.line(x0, y0, x0 + b, y0)
            layer.line(x1, y1 - b, x1, y1); layer.line(x1, y1, x1 - b, y1)
            continue
        layer.polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])

    # Refdes labels — placed outside the body. Tiny passives get a smaller
    # font; the rest get a slightly larger font for legibility. We skip
    # parts that already have a self-explanatory callout next to them
    # (the FFC connectors, USB-C jack, and the ESP32 module) so the silk
    # stays uncluttered.
    SKIP_REFDES_LABEL = {"U1", "J1", "J2", "J3"}
    # Per-refdes overrides for tightly packed regions where the automatic
    # placer can't avoid overlapping with neighbours. ``side`` is one of
    # ``"left"``, ``"right"``, ``"above"``, ``"below"``.
    LABEL_OVERRIDES = {
        # LED / current-limit-R cluster sits between J2 (above) and the
        # row of R20/R21 (below). Put D2/D3 labels sideways so R20/R21
        # can still claim the "above" slot above their own bodies.
        "D2": "left",
        "D3": "right",
        # BOOT / RESET tact-switch column on the east edge:
        "SW1": "left",
        "SW2": "left",
    }
    placed_label_rects: list[tuple[float, float, float, float]] = []
    for comp in COMPONENTS:
        if comp.refdes in SKIP_REFDES_LABEL:
            continue
        if comp.footprint in SMALL_PASSIVE_FPS:
            height = 0.7
        elif comp.footprint in COVERED_FPS:
            height = 0.9
        else:
            height = 0.85
        if comp.refdes in LABEL_OVERRIDES:
            side = LABEL_OVERRIDES[comp.refdes]
            fp = FOOTPRINTS[comp.footprint]
            bw, bh = fp["body_w"], fp["body_h"]
            if int(round(comp.rotation)) % 180 == 90:
                bw, bh = bh, bw
            gap = 0.45
            half_text_w = max(1.5, len(comp.refdes) * height * 0.5)
            if side == "above":
                tx, ty, center = comp.x, comp.y + bh / 2.0 + gap, True
            elif side == "below":
                tx, ty, center = comp.x, comp.y - bh / 2.0 - gap - height, True
            elif side == "left":
                tx, ty, center = (comp.x - bw / 2.0 - gap - 2 * half_text_w,
                                  comp.y - height / 2.0, False)
            elif side == "right":
                tx, ty, center = (comp.x + bw / 2.0 + gap,
                                  comp.y - height / 2.0, False)
            else:
                tx, ty, center = _label_position(comp, height)
        else:
            tx, ty, center = _label_position(comp, height)
            # Try to avoid stacking on top of an already-placed label.
            half_w = max(1.5, len(comp.refdes) * height * 0.5)
            cx0, cy0 = (tx - half_w, ty) if center else (tx, ty)
            cx1, cy1 = (tx + half_w, ty + height) if center else (tx + 2 * half_w, ty + height)
            for px0, py0, px1, py1 in placed_label_rects:
                if cx1 < px0 or cx0 > px1 or cy1 < py0 or cy0 > py1:
                    continue
                # Conflict — try the inverse Y side.
                fp = FOOTPRINTS[comp.footprint]
                bw, bh = fp["body_w"], fp["body_h"]
                if int(round(comp.rotation)) % 180 == 90:
                    bw, bh = bh, bw
                gap = 0.45
                if ty > comp.y:
                    new_y = comp.y - bh / 2.0 - gap - height
                else:
                    new_y = comp.y + bh / 2.0 + gap
                if 0.4 < new_y < BOARD_H - 0.4 - height:
                    ty = new_y
                break
        _silk_text(layer, comp.refdes, tx, ty, height_mm=height, center=center)
        half_w = max(1.5, len(comp.refdes) * height * 0.5)
        if center:
            placed_label_rects.append((tx - half_w, ty, tx + half_w, ty + height))
        else:
            placed_label_rects.append((tx, ty, tx + 2 * half_w, ty + height))

    # LED polarity bars — short tick on the cathode (pin 2) side.
    bar = pool.get_trace(0.20)
    layer.select(bar)
    for d in ("D2", "D3"):
        comp = next(c for c in COMPONENTS if c.refdes == d)
        layer.select(bar)
        layer.line(comp.x + 0.95, comp.y - 0.5, comp.x + 0.95, comp.y + 0.5)

    # USB-C edge connector callout (printed on the south edge next to the
    # receptacle).
    _silk_text(layer, "USB-C 5V/3A", 30.0, 0.8, 0.6, center=True)

    # FFC connector role callouts (above each connector, on the north edge).
    _silk_text(layer, "J1 \u2192 MESH ROWS", 15.0, 39.1, 0.6, center=True)
    _silk_text(layer, "J2 \u2192 MESH COLS", 45.0, 39.1, 0.6, center=True)

    # Pin-1 markers — a small triangle next to the FFC pin-1 contact.
    pin1 = pool.get_trace(0.20)
    layer.select(pin1)
    for refdes, sign in (("J1", -1), ("J2", -1)):
        c = next(c for c in COMPONENTS if c.refdes == refdes)
        # FFC pin 1 is at -7.5 from center along X (pitch 1.0 mm × 16 pads).
        px = c.x + sign * 7.5
        py = c.y - 1.7
        layer.polyline([(px - 0.4, py - 0.4), (px + 0.4, py - 0.4),
                        (px, py + 0.2), (px - 0.4, py - 0.4)])

    # Small CONET logo and title block tucked into the south band of the
    # board, between the USB-C receptacle and the right-hand edge.
    _logo(layer, 41.0, 1.6, size=3.0)
    _title_block(layer, 56.5, 0.4)

    # Subtle alignment fiducials in three corners — helpful for the SMT
    # camera and visually breaks the silk monotony.
    for fx, fy in [(2.5, 37.5), (57.5, 37.5), (2.5, 12.0)]:
        layer.select(bar)
        # Outer ring drawn as 12-segment polygon.
        import math as _m
        r = 0.6
        layer.polyline([
            (fx + r * _m.cos(2 * _m.pi * i / 12),
             fy + r * _m.sin(2 * _m.pi * i / 12))
            for i in range(13)
        ])
        # Inner solid dot.
        dot = pool.get_pad("circle", 0.5, 0.5)
        layer.select(dot)
        layer.flash(fx, fy)

    return layer


def build_silk_bottom() -> GerberLayer:
    layer = GerberLayer(name="B_Silkscreen", file_function="Legend,Bot")
    # Bottom silk: mirror each glyph along its vertical centre so the text
    # reads correctly when the board is physically flipped over. Without
    # this step JLCPCB would print a mirror image of the labels.
    _silk_text(layer, "CONET TACTILE SCANNER V1", 30.0, 22.0,
               height_mm=1.4, center=True, mirror_x=True)
    _silk_text(layer, "github.com/gkjuwon-tech/hw", 30.0, 19.0,
               height_mm=0.7, center=True, mirror_x=True)
    _silk_text(layer, "PROTO BATCH 01 \u2014 EVT", 30.0, 17.0,
               height_mm=0.7, center=True, mirror_x=True)
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
# Silkscreen text — Hershey Simplex Roman stroke font
# ---------------------------------------------------------------------------

def _text_width_units(text: str) -> int:
    """Width of ``text`` in Hershey native units (sum of glyph advances)."""
    return sum(GLYPH_ADVANCE.get(ch, GLYPH_ADVANCE[" "]) for ch in text)


def _silk_text(layer: GerberLayer, text: str, x: float, y: float,
               height_mm: float = 1.0, center: bool = False,
               mirror_x: bool = False) -> None:
    """Draw ``text`` on a silk-style layer using Hershey Simplex Roman.

    Coordinates: ``(x, y)`` is the lower-left corner of the cap-height
    bounding box. When ``center=True``, ``x`` is the horizontal midpoint
    and ``y`` is the vertical midpoint instead.
    The Hershey font has +Y pointing down internally; this function
    flips it so that text renders right-side-up on a silk-screen layer
    where +Y points up.
    """
    pool = AperturePool(layer)
    pen = pool.get_trace(0.13)
    layer.select(pen)
    # Convert Hershey native units → mm.
    scale = height_mm / CAP_HEIGHT_UNITS
    width_units = _text_width_units(text)
    width_mm = width_units * scale
    if center:
        x_origin = x - width_mm / 2.0
        y_origin = y - height_mm / 2.0
    else:
        x_origin = x
        y_origin = y
    if mirror_x:
        # Mirror across the text's vertical centre line so the glyphs read
        # correctly when the board is flipped over (used for bottom silk).
        mirror_axis = x_origin + width_mm / 2.0
    cursor = 0.0
    for ch in text:
        segs = GLYPH_SEGMENTS.get(ch, GLYPH_SEGMENTS.get(" "))
        advance = GLYPH_ADVANCE.get(ch, GLYPH_ADVANCE[" "])
        # Hershey glyphs are centered around x=0 with half-width = advance/2.
        glyph_left_offset = advance / 2.0
        for x0, y0, x1, y1 in segs:
            X0 = x_origin + (cursor + x0 + glyph_left_offset) * scale
            X1 = x_origin + (cursor + x1 + glyph_left_offset) * scale
            # Flip y: Hershey baseline is at y=9, cap top at y=-12.
            # Map y=9 → y_origin (baseline), y=-12 → y_origin + height.
            Y0 = y_origin + (BASELINE_Y - y0) * scale
            Y1 = y_origin + (BASELINE_Y - y1) * scale
            if mirror_x:
                X0 = 2 * mirror_axis - X0
                X1 = 2 * mirror_axis - X1
            layer.line(X0, Y0, X1, Y1)
        cursor += advance


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
    Rotation is in degrees (0–360).

    DNP / ``populate=False`` components are intentionally omitted: the
    JLCPCB SMT uploader rejects the order ("The below parts won't be
    assembled due to data missing. <refdes> designators don't exist in
    the BOM file.") if the CPL lists refdeses for which the BOM has no
    matching part. Footprints for those parts are still etched onto the
    PCB by the gerber generator — they're just empty pads waiting for
    hand-soldered bodges, which is exactly what ``populate=False`` is
    for.
    """
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for comp in sorted(COMPONENTS, key=lambda c: _refdes_sort_key(c.refdes)):
            if not comp.populate:
                continue
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
