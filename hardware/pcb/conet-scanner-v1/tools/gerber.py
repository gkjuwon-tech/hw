"""Minimal RS-274X (Gerber) writer + Excellon drill writer.

This module produces JLCPCB-acceptable Gerber X2 + Excellon files without
depending on KiCad. The goal is not a full EDA replacement — it's just enough
fidelity for JLCPCB's online verifier to ingest the artwork, place the BOM
parts at the right (X, Y, rotation), and route a 4-layer board with the
declared stack-up.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone


GERBER_SCALE = 1_000_000  # X4.6 → 1 mm = 1_000_000 units


def _g(coord_mm: float) -> int:
    return int(round(coord_mm * GERBER_SCALE))


@dataclass
class Aperture:
    code: int            # D-code (≥ 10)
    shape: str           # 'C' (circle) or 'R' (rect) or 'O' (obround)
    w: float             # width / diameter (mm)
    h: float = 0.0       # height (mm), unused for 'C'

    def definition(self) -> str:
        if self.shape == "C":
            return f"%ADD{self.code}C,{self.w:.6f}*%"
        return f"%ADD{self.code}{self.shape},{self.w:.6f}X{self.h:.6f}*%"


@dataclass
class GerberLayer:
    name: str                                 # e.g. 'F_Cu'
    file_function: str                        # X2 ``%TF.FileFunction`` value
    polarity: str = "Positive"                # 'Positive' or 'Negative'
    apertures: list[Aperture] = field(default_factory=list)
    body: list[str] = field(default_factory=list)
    project: str = "conet-scanner-v1"
    revision: str = "v1"

    # ---- aperture management ------------------------------------------------

    def _next_dcode(self) -> int:
        return 10 + len(self.apertures)

    def add_circle(self, dia_mm: float) -> int:
        a = Aperture(code=self._next_dcode(), shape="C", w=dia_mm)
        self.apertures.append(a)
        return a.code

    def add_rect(self, w_mm: float, h_mm: float) -> int:
        a = Aperture(code=self._next_dcode(), shape="R", w=w_mm, h=h_mm)
        self.apertures.append(a)
        return a.code

    def add_obround(self, w_mm: float, h_mm: float) -> int:
        a = Aperture(code=self._next_dcode(), shape="O", w=w_mm, h=h_mm)
        self.apertures.append(a)
        return a.code

    # ---- drawing primitives -------------------------------------------------

    def select(self, dcode: int) -> None:
        self.body.append(f"D{dcode}*")

    def flash(self, x_mm: float, y_mm: float) -> None:
        self.body.append(f"X{_g(x_mm)}Y{_g(y_mm)}D03*")

    def move_to(self, x_mm: float, y_mm: float) -> None:
        self.body.append(f"X{_g(x_mm)}Y{_g(y_mm)}D02*")

    def line_to(self, x_mm: float, y_mm: float) -> None:
        self.body.append(f"X{_g(x_mm)}Y{_g(y_mm)}D01*")

    def line(self, x0, y0, x1, y1) -> None:
        self.move_to(x0, y0)
        self.line_to(x1, y1)

    def polyline(self, points: list[tuple[float, float]]) -> None:
        if not points:
            return
        self.move_to(*points[0])
        for x, y in points[1:]:
            self.line_to(x, y)

    def region(self, points: list[tuple[float, float]]) -> None:
        """Fill the closed polygon defined by ``points`` (first ≠ last OK)."""
        if len(points) < 3:
            return
        self.body.append("G36*")
        self.move_to(*points[0])
        for x, y in points[1:]:
            self.line_to(x, y)
        # Close
        self.line_to(*points[0])
        self.body.append("G37*")

    def set_polarity_dark(self) -> None:
        self.body.append("%LPD*%")

    def set_polarity_clear(self) -> None:
        self.body.append("%LPC*%")

    # ---- output -------------------------------------------------------------

    def render(self) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        lines: list[str] = []
        lines.append(f"G04 {self.project} — {self.name} *")
        lines.append("%TF.GenerationSoftware,Conet,gerber_gen,1.0*%")
        lines.append(f"%TF.CreationDate,{now}*%")
        lines.append(f"%TF.ProjectId,{self.project},,{self.revision}*%")
        lines.append("%TF.SameCoordinates,Original*%")
        lines.append(f"%TF.FileFunction,{self.file_function}*%")
        lines.append(f"%TF.FilePolarity,{self.polarity}*%")
        lines.append("%FSLAX46Y46*%")
        lines.append("%MOMM*%")
        lines.append("%LPD*%")
        for ap in self.apertures:
            lines.append(ap.definition())
        lines.append("G01*")
        lines.extend(self.body)
        lines.append("M02*")
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Excellon drill file
# ---------------------------------------------------------------------------

@dataclass
class DrillHit:
    tool: int
    x: float
    y: float


@dataclass
class ExcellonFile:
    project: str = "conet-scanner-v1"
    plated: bool = True
    tools: dict[float, int] = field(default_factory=dict)
    hits: list[DrillHit] = field(default_factory=list)

    def _get_tool(self, dia_mm: float) -> int:
        if dia_mm not in self.tools:
            self.tools[dia_mm] = len(self.tools) + 1
        return self.tools[dia_mm]

    def drill(self, x_mm: float, y_mm: float, dia_mm: float) -> None:
        t = self._get_tool(dia_mm)
        self.hits.append(DrillHit(tool=t, x=x_mm, y=y_mm))

    def render(self) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        out: list[str] = []
        out.append("M48")
        out.append(f"; {self.project} — {'PTH' if self.plated else 'NPTH'} drill")
        out.append(f"; Generated: {now}")
        out.append(";FILE_FORMAT=4:6")
        out.append("FMAT,2")
        out.append("METRIC,TZ")
        out.append("G90")
        out.append("G05")
        # Tool definitions sorted by diameter for determinism.
        for dia, code in sorted(self.tools.items(), key=lambda kv: kv[1]):
            out.append(f"T{code}C{dia:.3f}")
        out.append("%")
        # Sort hits by tool, then by x then y for determinism.
        by_tool: dict[int, list[DrillHit]] = {}
        for hit in self.hits:
            by_tool.setdefault(hit.tool, []).append(hit)
        for code in sorted(by_tool):
            out.append(f"T{code}")
            for hit in sorted(by_tool[code], key=lambda h: (h.x, h.y)):
                # X4.6 metric, leading zero suppression (TZ = trailing zeros
                # kept, so we always pad to 10 digits with sign retained).
                x_units = int(round(hit.x * GERBER_SCALE))
                y_units = int(round(hit.y * GERBER_SCALE))
                out.append(f"X{x_units}Y{y_units}")
        out.append("T0")
        out.append("M30")
        return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def rotate_offset(dx: float, dy: float, rot_deg: float) -> tuple[float, float]:
    """Rotate the (dx, dy) offset by ``rot_deg`` (CCW)."""
    if rot_deg == 0:
        return dx, dy
    a = math.radians(rot_deg)
    c, s = math.cos(a), math.sin(a)
    return c * dx - s * dy, s * dx + c * dy


def pad_world(pad: dict, cx: float, cy: float, rot_deg: float) -> tuple[float, float, float, float, float]:
    """Return (world_x, world_y, w, h, rot_total) for a pad placed on a
    component at (cx, cy, rot_deg)."""
    dx, dy = rotate_offset(pad["x"], pad["y"], rot_deg)
    return cx + dx, cy + dy, pad["w"], pad["h"], rot_deg


def rounded_rect_polygon(x0: float, y0: float, x1: float, y1: float,
                         r: float, segs: int = 12) -> list[tuple[float, float]]:
    """Polygon vertices of a rounded rectangle with corner radius ``r``.

    Vertices are listed counter-clockwise starting from the bottom-right
    corner's tangent point."""
    pts: list[tuple[float, float]] = []
    # bottom edge
    pts.append((x1 - r, y0))
    # bottom-right corner
    cx, cy = x1 - r, y0 + r
    for i in range(segs + 1):
        a = -math.pi / 2 + (math.pi / 2) * i / segs
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    # right edge (now at x1, y1 - r)
    # top-right corner
    cx, cy = x1 - r, y1 - r
    for i in range(segs + 1):
        a = 0 + (math.pi / 2) * i / segs
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    # top edge → top-left corner
    cx, cy = x0 + r, y1 - r
    for i in range(segs + 1):
        a = math.pi / 2 + (math.pi / 2) * i / segs
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    # left edge → bottom-left corner
    cx, cy = x0 + r, y0 + r
    for i in range(segs + 1):
        a = math.pi + (math.pi / 2) * i / segs
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts
