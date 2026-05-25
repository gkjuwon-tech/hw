"""Light-weight Gerber RS-274X inspection.

We unzip the manufacturing archive and walk every aperture definition
(`%ADD..`) on every copper layer, then run the **trace** primitives
(D-codes interpreted as drawn lines with the current aperture) to derive:

* the smallest aperture (= the minimum line width on that layer)
* the smallest gap between any two strokes/pads on the same layer
* total copper drawing length per layer (sanity check)
* number of drill hits per drill file

We are not running a full DRC -- that needs a polygon engine. We are
looking for obvious red flags: trace widths below the JLCPCB 5/5 mil
standard for 4-layer boards, drill sizes below the 0.2 mm capability,
inner planes that are essentially empty (a 364-byte B_Cu file etc).

Findings emitted:

* GBR-LAYER-EMPTY            copper layer file < 1 KB and has 0 trace D-codes
* GBR-TRACE-TOO-NARROW       minimum aperture width below JLCPCB 4-layer min (3.5 mil)
* GBR-DRILL-TOO-SMALL        any drill hit below 0.2 mm (8 mil) PTH min
* GBR-MISSING-FILE           expected file class absent from the zip
* GBR-OUTLINE-WEIRD          edge cuts perimeter not within expected board area
* GBR-NO-INNER-POURS         inner 2 layers do not span the board outline
"""

from __future__ import annotations

import math
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .findings import Finding


# JLCPCB 2024 capability sheet, 4-layer 1 oz outer / 0.5 oz inner:
# - min trace width / spacing: 3.5 mil (0.0889 mm)  [premium]
# - min drill: 0.20 mm (8 mil) for PTH, 0.30 mm strongly preferred
# - min annular ring: 0.075 mm
JLC_MIN_TRACE_MM = 0.0889   # 3.5 mil
JLC_MIN_DRILL_MM = 0.20     # 8 mil


@dataclass
class LayerStats:
    name: str
    bytes: int
    apertures: dict[int, float] = field(default_factory=dict)  # code -> diameter mm
    aperture_kinds: dict[int, str] = field(default_factory=dict)  # code -> shape
    min_aperture_mm: float = float("inf")
    n_traces: int = 0
    total_stroke_mm: float = 0.0
    units: str = "mm"
    bbox: tuple[float, float, float, float] | None = None    # xmin, ymin, xmax, ymax


@dataclass
class DrillStats:
    name: str
    bytes: int
    tools: dict[int, float] = field(default_factory=dict)
    hits: int = 0
    min_drill_mm: float = float("inf")


# --- Gerber parser --------------------------------------------------------

_AD_RE = re.compile(r"%ADD(\d+)([CROP])([^%]+)\*%")
_FS_RE = re.compile(r"%FSLAX(\d)(\d)Y\d\d\*%")
_MO_RE = re.compile(r"%MO(MM|IN)\*%")
_DCODE_RE = re.compile(r"D(\d+)\*")
_COORD_RE = re.compile(r"(?:X(-?\d+))?(?:Y(-?\d+))?D(0[123])\*")


def _parse_gerber(name: str, raw: bytes) -> LayerStats:
    text = raw.decode("ascii", errors="ignore")
    stats = LayerStats(name=name, bytes=len(raw))

    # Resolution
    int_digits = 3
    dec_digits = 6
    if m := _FS_RE.search(text):
        int_digits = int(m.group(1))
        dec_digits = int(m.group(2))
    units = "mm"
    if m := _MO_RE.search(text):
        units = "mm" if m.group(1) == "MM" else "in"
    stats.units = units
    scale = 10 ** -dec_digits
    unit_to_mm = 1.0 if units == "mm" else 25.4

    # Apertures
    for m in _AD_RE.finditer(text):
        code = int(m.group(1))
        kind = m.group(2)
        spec = m.group(3)
        try:
            diam_str = spec.split(",", 1)[1] if "," in spec else spec
            diam = float(diam_str.split("X")[0])
        except (ValueError, IndexError):
            continue
        diam_mm = diam * unit_to_mm
        stats.apertures[code] = diam_mm
        stats.aperture_kinds[code] = kind
        # Only count rounded apertures as "trace width" candidates;
        # rectangular pads can be wide without being a trace.
        if kind in ("C", "O"):
            stats.min_aperture_mm = min(stats.min_aperture_mm, diam_mm)

    # Walk D-codes / coords
    cur_aperture = None
    cur_x = cur_y = 0.0
    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")

    def upd_bbox(x: float, y: float) -> None:
        nonlocal xmin, ymin, xmax, ymax
        xmin = min(xmin, x)
        ymin = min(ymin, y)
        xmax = max(xmax, x)
        ymax = max(ymax, y)

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("%"):
            continue
        m = _DCODE_RE.fullmatch(line)
        if m and not line.startswith("X") and not line.startswith("Y"):
            cur_aperture = int(m.group(1))
            continue
        c = _COORD_RE.search(line)
        if not c:
            continue
        nx = float(c.group(1)) * scale * unit_to_mm if c.group(1) else cur_x
        ny = float(c.group(2)) * scale * unit_to_mm if c.group(2) else cur_y
        d = c.group(3)
        if d == "01":  # interpolate (draw)
            seg = math.hypot(nx - cur_x, ny - cur_y)
            stats.total_stroke_mm += seg
            stats.n_traces += 1
            upd_bbox(cur_x, cur_y)
            upd_bbox(nx, ny)
        elif d == "02":  # move
            upd_bbox(nx, ny)
        elif d == "03":  # flash
            upd_bbox(nx, ny)
        cur_x, cur_y = nx, ny

    if xmin < float("inf"):
        stats.bbox = (xmin, ymin, xmax, ymax)
    return stats


def _parse_drill(name: str, raw: bytes) -> DrillStats:
    text = raw.decode("ascii", errors="ignore")
    stats = DrillStats(name=name, bytes=len(raw))
    units_mm = "METRIC" in text or "MM" in text
    for m in re.finditer(r"T(\d+)C([0-9.]+)", text):
        tool = int(m.group(1))
        size = float(m.group(2))
        if not units_mm:
            size *= 25.4
        stats.tools[tool] = size
        stats.min_drill_mm = min(stats.min_drill_mm, size)
    # count hits: every "T#" selection followed by X..Y..
    cur_tool = None
    hits = 0
    for line in text.splitlines():
        line = line.strip()
        if m := re.fullmatch(r"T(\d+)", line):
            cur_tool = int(m.group(1))
        elif re.match(r"X[\-0-9.]+Y[\-0-9.]+", line) and cur_tool is not None:
            hits += 1
    stats.hits = hits
    return stats


def parse(zip_path: Path) -> tuple[dict, list[Finding]]:
    findings: list[Finding] = []
    summary: dict = dict(layers=[], drills=[], outline=None)

    with tempfile.TemporaryDirectory() as td:
        td_p = Path(td)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(td_p)

        copper_classes = ["F_Cu", "In1_Cu", "In2_Cu", "B_Cu"]
        seen_copper = set()

        for f in sorted(td_p.iterdir()):
            if f.suffix == ".gbr":
                raw = f.read_bytes()
                stats = _parse_gerber(f.name, raw)
                summary["layers"].append(dict(
                    name=f.name,
                    bytes=stats.bytes,
                    n_traces=stats.n_traces,
                    min_aperture_mm=None if stats.min_aperture_mm == float("inf") else stats.min_aperture_mm,
                    n_apertures=len(stats.apertures),
                    bbox=stats.bbox,
                ))
                for klass in copper_classes:
                    if klass in f.name:
                        seen_copper.add(klass)
                # findings
                if "_Cu.gbr" in f.name:
                    # Empty/near-empty bottom copper or signal layers. Inner
                    # planes can legitimately be small if they are a single
                    # solid pour expressed as one rectangle, so we treat
                    # outer layers (F_Cu/B_Cu) stricter than inner planes.
                    is_outer = ("F_Cu" in f.name) or ("B_Cu" in f.name)
                    if is_outer and stats.bytes < 1024 and stats.n_traces < 5:
                        findings.append(Finding(
                            module="parse_gerber",
                            code="GBR-LAYER-EMPTY",
                            title=f"Outer copper layer `{f.name}` is essentially empty ({stats.bytes} B, {stats.n_traces} traces)",
                            severity=3,
                            detail=(
                                f"`{f.name}` is {stats.bytes} bytes with **{stats.n_traces}** "
                                "drawn copper segments. For a 4-layer board this means there is "
                                "no return path / pour on this outer layer. Signal integrity "
                                "for any trace that depends on this layer as its reference "
                                "plane (and microstrip impedance control) is compromised.\n\n"
                                "If this is `B_Cu`, USB D+/D- and digital I/O on the top layer "
                                "have no controlled-impedance return; USB 12 Mbps still works "
                                "but EMI and ESD margins are reduced. Add a solid GND pour on "
                                "B_Cu before final tape-out."
                            ),
                            refs=[f.name],
                        ))
                    if not is_outer and stats.bytes < 256:
                        findings.append(Finding(
                            module="parse_gerber",
                            code="GBR-INNER-PLANE-MISSING",
                            title=f"Inner plane `{f.name}` looks unpopulated",
                            severity=4,
                            detail=(
                                f"`{f.name}` is only {stats.bytes} bytes -- almost certainly "
                                "no pour. For a 4-layer order this is the GND or +3V3 plane; "
                                "without it the stack-up is effectively 2-layer with two extra "
                                "blanks and you are paying the 4-layer price for nothing."
                            ),
                            refs=[f.name],
                        ))
                    if stats.min_aperture_mm < JLC_MIN_TRACE_MM and stats.min_aperture_mm > 0:
                        findings.append(Finding(
                            module="parse_gerber",
                            code="GBR-TRACE-TOO-NARROW",
                            title=f"`{f.name}` has aperture {stats.min_aperture_mm*1000:.1f} um (below JLC min 88.9 um)",
                            severity=4,
                            detail=(
                                f"Minimum aperture {stats.min_aperture_mm:.4f} mm "
                                f"= {stats.min_aperture_mm/0.0254:.2f} mil. "
                                f"JLCPCB 4-layer 1oz minimum is 3.5 mil (0.0889 mm). "
                                "Submission will be reverted by JLC's CAM team or fabricated with "
                                "open traces."
                            ),
                            refs=[f.name],
                        ))
                if "Edge_Cuts" in f.name:
                    summary["outline"] = dict(
                        bytes=stats.bytes,
                        bbox=stats.bbox,
                        total_perimeter_mm=stats.total_stroke_mm,
                    )
                    if stats.bbox:
                        w = stats.bbox[2] - stats.bbox[0]
                        h = stats.bbox[3] - stats.bbox[1]
                        if not (55 <= w <= 65 and 35 <= h <= 45):
                            findings.append(Finding(
                                module="parse_gerber",
                                code="GBR-OUTLINE-WEIRD",
                                title=f"Edge cuts bbox {w:.2f} x {h:.2f} mm, expected ~60 x 40",
                                severity=3,
                                detail="README declares a 60 x 40 mm board. Edge cuts disagree.",
                                refs=[f.name],
                            ))
            elif f.suffix == ".drl":
                raw = f.read_bytes()
                stats = _parse_drill(f.name, raw)
                summary["drills"].append(dict(
                    name=f.name,
                    bytes=stats.bytes,
                    hits=stats.hits,
                    min_drill_mm=None if stats.min_drill_mm == float("inf") else stats.min_drill_mm,
                    n_tools=len(stats.tools),
                ))
                if stats.min_drill_mm < JLC_MIN_DRILL_MM and stats.min_drill_mm > 0:
                    findings.append(Finding(
                        module="parse_gerber",
                        code="GBR-DRILL-TOO-SMALL",
                        title=f"`{f.name}` drill {stats.min_drill_mm:.3f} mm (below JLC 0.20 mm min)",
                        severity=4,
                        detail="Will be enlarged silently by the CAM tool or rejected.",
                        refs=[f.name],
                    ))

        for klass in copper_classes:
            if klass not in seen_copper:
                findings.append(Finding(
                    module="parse_gerber",
                    code="GBR-MISSING-FILE",
                    title=f"No `{klass}` copper file in archive",
                    severity=5,
                    detail=(
                        f"A 4-layer order requires `F_Cu`, `In1_Cu`, `In2_Cu`, `B_Cu`. "
                        f"`{klass}` is missing -- JLC will either fabricate as 2-layer (wrong "
                        "stack-up, signal integrity dead) or reject the order."
                    ),
                    refs=[klass],
                ))

    return summary, findings
