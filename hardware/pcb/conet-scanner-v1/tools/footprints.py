"""SMD/THT pad geometry for every footprint used on the Scanner v1 PCB.

A footprint is a dictionary with these keys:

    body_w, body_h  : silk outline rectangle size (mm).
    pads            : list of pad dicts.

Each pad has:

    num       : pad number / pin name (string).
    shape     : "rect" | "circle".
    w, h      : pad outer dimensions (mm); for "circle", w == h == diameter.
    x, y      : pad center offset from component origin (mm), measured before
                applying the placement rotation in ``components.py``.
    drill     : drill diameter (mm) if this is a through-hole pad, else None.
    plated    : True for PTH, False for NPTH (only meaningful if ``drill`` set).
    layer     : "top" | "bottom" | "both" (paste/mask handling).

All footprints assume the component reference orientation matches the
``rotation`` field in ``components.py`` — i.e. when a component is placed at
rotation=0 the pad offsets below are applied verbatim.
"""

from __future__ import annotations


def _row_pads(count, pitch, x, y_center, *, w, h, pad_start=1):
    """Helper: emit ``count`` pads along the Y axis at constant X.

    Pad numbering increases with decreasing Y (i.e. top → bottom)."""
    pads = []
    span = (count - 1) * pitch
    y_top = y_center + span / 2.0
    for i in range(count):
        pads.append({
            "num": str(pad_start + i),
            "shape": "rect",
            "w": w, "h": h,
            "x": x, "y": y_top - i * pitch,
            "drill": None, "plated": True, "layer": "top",
        })
    return pads


def _col_pads(count, pitch, y, x_center, *, w, h, pad_start=1, ltr=True):
    """Helper: emit ``count`` pads along the X axis at constant Y."""
    pads = []
    span = (count - 1) * pitch
    x_left = x_center - span / 2.0
    for i in range(count):
        idx = i if ltr else (count - 1 - i)
        pads.append({
            "num": str(pad_start + i),
            "shape": "rect",
            "w": w, "h": h,
            "x": x_left + idx * pitch, "y": y,
            "drill": None, "plated": True, "layer": "top",
        })
    return pads


# ---------------------------------------------------------------------------
# Passive packages
# ---------------------------------------------------------------------------

def _two_pad_smd(pad_w, pad_h, pad_pitch, body_w, body_h):
    return {
        "body_w": body_w, "body_h": body_h,
        "pads": [
            {"num": "1", "shape": "rect", "w": pad_w, "h": pad_h,
             "x": -pad_pitch / 2.0, "y": 0.0,
             "drill": None, "plated": True, "layer": "top"},
            {"num": "2", "shape": "rect", "w": pad_w, "h": pad_h,
             "x": +pad_pitch / 2.0, "y": 0.0,
             "drill": None, "plated": True, "layer": "top"},
        ],
    }


# ---------------------------------------------------------------------------
# IC packages
# ---------------------------------------------------------------------------

def _soic24():
    """SOIC-24, 1.27mm pitch, ~9.9mm lead span, body 15.4 x 7.5 mm.

    Pin 1 is top-left when viewed from above (component origin at body center,
    Y up). Pins 1..12 down the left side, pins 13..24 up the right side."""
    pads = []
    pad_w, pad_h = 0.6, 1.55
    pad_x = 3.7
    pitch = 1.27
    n_per_side = 12
    span = (n_per_side - 1) * pitch
    # Left column, top->bottom = pin 1..12
    for i in range(n_per_side):
        pads.append({
            "num": str(i + 1), "shape": "rect", "w": pad_h, "h": pad_w,
            "x": -pad_x, "y": span / 2.0 - i * pitch,
            "drill": None, "plated": True, "layer": "top",
        })
    # Right column, bottom->top = pin 13..24
    for i in range(n_per_side):
        pads.append({
            "num": str(13 + i), "shape": "rect", "w": pad_h, "h": pad_w,
            "x": +pad_x, "y": -span / 2.0 + i * pitch,
            "drill": None, "plated": True, "layer": "top",
        })
    return {"body_w": 7.5, "body_h": 15.4, "pads": pads}


def _msop10():
    """MSOP-10 (ADS1115). 0.5mm pitch, ~4.9mm lead span, body 3 x 3 mm."""
    pads = []
    pad_w, pad_h = 0.3, 1.05
    pad_x = 1.85
    pitch = 0.5
    n_per_side = 5
    span = (n_per_side - 1) * pitch
    for i in range(n_per_side):
        pads.append({
            "num": str(i + 1), "shape": "rect", "w": pad_h, "h": pad_w,
            "x": -pad_x, "y": span / 2.0 - i * pitch,
            "drill": None, "plated": True, "layer": "top",
        })
    for i in range(n_per_side):
        pads.append({
            "num": str(6 + i), "shape": "rect", "w": pad_h, "h": pad_w,
            "x": +pad_x, "y": -span / 2.0 + i * pitch,
            "drill": None, "plated": True, "layer": "top",
        })
    return {"body_w": 3.0, "body_h": 3.0, "pads": pads}


def _sot23_6():
    """SOT-23-6 (USBLC6). 0.95mm pitch, body 2.9 x 1.6 mm, lead span 2.8mm."""
    pad_w, pad_h = 0.6, 0.95
    pad_x = 1.0
    pitch = 0.95
    pads = []
    # Left side pin 1,2,3 (top to bottom)
    for i in range(3):
        pads.append({
            "num": str(i + 1), "shape": "rect", "w": pad_w, "h": pad_h,
            "x": -pad_x, "y": pitch - i * pitch,
            "drill": None, "plated": True, "layer": "top",
        })
    # Right side pin 6,5,4 (top to bottom) → numbered 4,5,6 bottom→top
    for i in range(3):
        pads.append({
            "num": str(4 + i), "shape": "rect", "w": pad_w, "h": pad_h,
            "x": +pad_x, "y": -pitch + i * pitch,
            "drill": None, "plated": True, "layer": "top",
        })
    return {"body_w": 2.9, "body_h": 2.8, "pads": pads}


def _sot223():
    """SOT-223 (TLV1117). 3 small pins on one side + 1 tab on the other."""
    pads = [
        # 3 small pins on the bottom side (pin 1,2,3 left-to-right)
        {"num": "1", "shape": "rect", "w": 1.0, "h": 1.5,
         "x": -2.3, "y": -2.5, "drill": None, "plated": True, "layer": "top"},
        {"num": "2", "shape": "rect", "w": 1.0, "h": 1.5,
         "x": 0.0, "y": -2.5, "drill": None, "plated": True, "layer": "top"},
        {"num": "3", "shape": "rect", "w": 1.0, "h": 1.5,
         "x": +2.3, "y": -2.5, "drill": None, "plated": True, "layer": "top"},
        # Tab (pin 4) on the top side
        {"num": "4", "shape": "rect", "w": 3.5, "h": 2.0,
         "x": 0.0, "y": +2.5, "drill": None, "plated": True, "layer": "top"},
    ]
    return {"body_w": 6.5, "body_h": 6.7, "pads": pads}


def _esp32_s3_wroom1():
    """ESP32-S3-WROOM-1 castellated SMD module. 25.5 x 18 mm.

    Reference orientation: 25.5mm along X, 18mm along Y, antenna on the +X
    short edge (right). Castellated pads on the +Y (top long edge),
    the -X (left short edge — opposite antenna), the -Y (bottom long edge),
    plus a center thermal/GND pad in the middle. Pad numbering follows the
    Espressif datasheet (pin 1 = GND tab at bottom-left, advancing
    counter-clockwise)."""
    body_w, body_h = 25.5, 18.0
    pads = []

    # Long-edge pads: 18 pads per long edge at 1.27mm pitch
    long_pitch = 1.27
    long_count = 18
    long_span = (long_count - 1) * long_pitch  # 21.59 mm
    pad_size_long = (0.9, 1.4)  # pad width along edge, height into body
    edge_offset_long = body_h / 2.0 - 0.0  # pads sit on the edge of the body

    # Bottom row (pins 2..19), left to right
    for i in range(long_count):
        x = -long_span / 2.0 + i * long_pitch
        pads.append({
            "num": str(2 + i), "shape": "rect",
            "w": pad_size_long[0], "h": pad_size_long[1],
            "x": x, "y": -edge_offset_long,
            "drill": None, "plated": True, "layer": "top",
        })
    # Top row (pins 28..45), right to left
    for i in range(long_count):
        x = long_span / 2.0 - i * long_pitch
        pads.append({
            "num": str(28 + i), "shape": "rect",
            "w": pad_size_long[0], "h": pad_size_long[1],
            "x": x, "y": +edge_offset_long,
            "drill": None, "plated": True, "layer": "top",
        })

    # Short-edge pads (-X side only — antenna is on +X side). 8 pads at
    # 1.5mm pitch.
    short_pitch = 1.5
    short_count = 8
    short_span = (short_count - 1) * short_pitch  # 10.5 mm
    pad_size_short = (1.4, 0.9)
    edge_offset_short = body_w / 2.0
    # Pin 20..27 from bottom to top on the left edge
    for i in range(short_count):
        y = -short_span / 2.0 + i * short_pitch
        pads.append({
            "num": str(20 + i), "shape": "rect",
            "w": pad_size_short[0], "h": pad_size_short[1],
            "x": -edge_offset_short, "y": y,
            "drill": None, "plated": True, "layer": "top",
        })

    # Pin 1 = central thermal/GND pad
    pads.append({
        "num": "1", "shape": "rect", "w": 5.0, "h": 5.0,
        "x": 0.0, "y": 0.0, "drill": None, "plated": True, "layer": "top",
    })

    return {"body_w": body_w, "body_h": body_h, "pads": pads}


def _ffc_16p_1mm():
    """16-pin FFC ZIF, 1.0mm pitch, Hirose FH12-16S-1SH style."""
    pads = []
    pitch = 1.0
    n = 16
    span = (n - 1) * pitch  # 15 mm
    # 16 signal pads in a row along the body, centered on Y=0.
    for i in range(n):
        pads.append({
            "num": str(i + 1), "shape": "rect",
            "w": 0.6, "h": 1.4,
            "x": -span / 2.0 + i * pitch, "y": -1.5,
            "drill": None, "plated": True, "layer": "top",
        })
    # Two mounting tabs (numbered MP1/MP2) at the body ends.
    pads.append({
        "num": "MP1", "shape": "rect", "w": 1.5, "h": 1.7,
        "x": -span / 2.0 - 1.4, "y": +0.6,
        "drill": None, "plated": True, "layer": "top",
    })
    pads.append({
        "num": "MP2", "shape": "rect", "w": 1.5, "h": 1.7,
        "x": +span / 2.0 + 1.4, "y": +0.6,
        "drill": None, "plated": True, "layer": "top",
    })
    return {"body_w": span + 4.6, "body_h": 4.3, "pads": pads}


def _usb_c_16p_smd():
    """USB Type-C SMD receptacle, 16-pin. Inner row of contacts plus 4
    mounting tabs that act as through-hole anchors (plated)."""
    pads = []
    # Signal row of 16 contacts at 0.5mm pitch, centered.
    n = 16
    pitch = 0.5
    span = (n - 1) * pitch  # 7.5 mm
    # Standard USB-C pinout (top row): GND A1, TX1+ A2, TX1- A3, VBUS A4,
    # CC1 A5, D+ A6, D- A7, SBU1 A8, ... etc. We don't differentiate here;
    # JLCPCB places the part by overall outline + center.
    for i in range(n):
        pads.append({
            "num": "A" + str(i + 1) if i < 8 else "B" + str(16 - i + 0),
            "shape": "rect", "w": 0.3, "h": 1.0,
            "x": -span / 2.0 + i * pitch, "y": -0.5,
            "drill": None, "plated": True, "layer": "top",
        })
    # Four mounting tabs (through-hole, plated). 2 at front edge, 2 at back.
    for sign_x, mp_x in ((-1, -4.32), (+1, +4.32)):
        # Front tab (toward receptacle opening)
        pads.append({
            "num": f"MP{1 if sign_x < 0 else 2}",
            "shape": "circle", "w": 1.4, "h": 1.4,
            "x": mp_x, "y": -2.16,
            "drill": 0.8, "plated": True, "layer": "top",
        })
        # Back tab
        pads.append({
            "num": f"MP{3 if sign_x < 0 else 4}",
            "shape": "circle", "w": 1.4, "h": 1.4,
            "x": mp_x, "y": +2.16,
            "drill": 0.8, "plated": True, "layer": "top",
        })
    return {"body_w": 8.94, "body_h": 7.35, "pads": pads}


def _tact_4p():
    """4-pin tactile switch (TS-1187A style), 4.5 x 4.5 mm body."""
    pads = [
        {"num": "1", "shape": "rect", "w": 1.2, "h": 1.0,
         "x": -2.25, "y": +1.6, "drill": None, "plated": True, "layer": "top"},
        {"num": "2", "shape": "rect", "w": 1.2, "h": 1.0,
         "x": +2.25, "y": +1.6, "drill": None, "plated": True, "layer": "top"},
        {"num": "3", "shape": "rect", "w": 1.2, "h": 1.0,
         "x": -2.25, "y": -1.6, "drill": None, "plated": True, "layer": "top"},
        {"num": "4", "shape": "rect", "w": 1.2, "h": 1.0,
         "x": +2.25, "y": -1.6, "drill": None, "plated": True, "layer": "top"},
    ]
    return {"body_w": 4.5, "body_h": 4.5, "pads": pads}


def _solder_jumper_2p():
    pads = [
        {"num": "1", "shape": "rect", "w": 0.8, "h": 1.0,
         "x": -0.55, "y": 0.0, "drill": None, "plated": True, "layer": "top"},
        {"num": "2", "shape": "rect", "w": 0.8, "h": 1.0,
         "x": +0.55, "y": 0.0, "drill": None, "plated": True, "layer": "top"},
    ]
    return {"body_w": 2.2, "body_h": 1.4, "pads": pads}


FOOTPRINTS: dict[str, dict] = {
    # Passives
    "0402": _two_pad_smd(pad_w=0.6, pad_h=0.6, pad_pitch=0.95,
                         body_w=1.0, body_h=0.5),
    "0603": _two_pad_smd(pad_w=0.8, pad_h=0.9, pad_pitch=1.5,
                         body_w=1.6, body_h=0.8),
    "0805": _two_pad_smd(pad_w=1.0, pad_h=1.3, pad_pitch=2.0,
                         body_w=2.0, body_h=1.25),
    "1206": _two_pad_smd(pad_w=1.4, pad_h=1.8, pad_pitch=3.4,
                         body_w=3.2, body_h=1.6),
    "1812": _two_pad_smd(pad_w=1.8, pad_h=3.5, pad_pitch=4.5,
                         body_w=4.6, body_h=3.2),

    # LEDs (same as 0603 outline, but separate so silk can show polarity bar)
    "LED_0603": _two_pad_smd(pad_w=0.8, pad_h=0.9, pad_pitch=1.5,
                             body_w=1.6, body_h=0.8),

    # ICs / modules
    "ESP32_S3_WROOM_1": _esp32_s3_wroom1(),
    "SOIC-24": _soic24(),
    "MSOP-10": _msop10(),
    "SOT-23-6": _sot23_6(),
    "SOT-223": _sot223(),

    # Connectors / switches
    "FFC_16P_1MM": _ffc_16p_1mm(),
    "USB_C_SMD_16P": _usb_c_16p_smd(),
    "TACT_4P_4.5x4.5": _tact_4p(),

    # Jumper
    "SOLDER_JUMPER_2P": _solder_jumper_2p(),
}
