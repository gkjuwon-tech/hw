"""Parse `cpl.csv` and check placement sanity vs the BOM.

Findings emitted:

* CPL-REFDES-NOT-IN-BOM       refdes placed on the board but BOM is silent
* CPL-OUT-OF-BOARD            xy outside the 60x40 mm outline
* CPL-ROTATION-SUSPECT        rotation likely wrong vs LCSC zero-orientation
* CPL-OVERLAP-RISK            two refdeses placed within <0.5 mm centre distance
* CPL-MISSING-REFDES          placed in BOM but missing in cpl.csv
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

from .findings import Finding


BOARD_W_MM = 60.0
BOARD_H_MM = 40.0

# JLCPCB rotation convention is the "EDA-tool zero" orientation. For many
# polarised LCSC parts the rotation differs from KiCad/Altium. We encode
# the documented JLCPCB rotation offset (added to the EDA rotation to get
# the LCSC mounting rotation) for the parts on this BOM.
#
# Source: JLCPCB SMT rotation guide + community-maintained
# https://github.com/matthewlai/JlcKicadTools rotation database (Aug 2024).
JLCPCB_ROTATION_OFFSET = {
    "U1":  0,     # ESP32-S3-WROOM-1 (large module, well-defined pin 1)
    "U2":  0,     # SOIC-24 -- KiCad zero is pin 1 upper-left, same as JLCPCB
    "U3":  0,     # same as U2
    "U4":  0,     # MSOP-10
    "U5": 180,    # SOT-223 TLV1117LV33 has the tab usually at the top in
                  # KiCad but pin 1 at the bottom in LCSC photos. The
                  # rotation offset for SOT-223 LDOs on JLCPCB is +180.
    "D1": 0,
    "D2": 270,    # 0603 LEDs on JLCPCB need +270 (cathode bar orientation)
    "D3": 270,
    "F1": 0,
    "J1": 90,     # FH12-16S-1SH ZIF: LCSC photo shows latch on the bottom;
                  # KiCad library typically lays it horizontal => +90 needed.
    "J2": 90,
    "J3": 0,
    "SW1": 0,
    "SW2": 0,
}


def parse(cpl_path: Path, bom_refdes: set[str]) -> tuple[list[dict], list[Finding]]:
    rows: list[dict] = []
    findings: list[Finding] = []

    with cpl_path.open() as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            refdes = raw["Designator"].strip()
            mid_x = float(raw["Mid X"].replace("mm", "").strip())
            mid_y = float(raw["Mid Y"].replace("mm", "").strip())
            rotation = int(float(raw["Rotation"].strip()))
            layer = raw["Layer"].strip()
            rows.append(dict(refdes=refdes, x=mid_x, y=mid_y, rotation=rotation, layer=layer))

            if refdes not in bom_refdes:
                findings.append(Finding(
                    module="parse_cpl",
                    code="CPL-REFDES-NOT-IN-BOM",
                    title=f"`{refdes}` placed on the PCB but absent from the BOM",
                    severity=5,
                    detail=(
                        f"The pick-and-place file places `{refdes}` at "
                        f"({mid_x:.2f}, {mid_y:.2f}) mm but no BOM row supplies a part for it. "
                        "JLCPCB's SMT uploader **rejects the order outright** with: "
                        f"*'The below parts won't be assembled due to data missing. "
                        f"{refdes} designators don't exist in the BOM file.'* "
                        "If the part is intentionally DNP, drop the refdes from `cpl.csv` too — "
                        "the footprint still gets etched onto the PCB by the gerber generator, "
                        "the SMT line just won't try to pick anything for it. The "
                        "`populate=False` flag on `tools/components.py` is the source-of-truth "
                        "knob; `tools/build_artifacts.py::write_cpl` skips DNP rows automatically."
                    ),
                    refs=[refdes],
                ))

            if not (0 <= mid_x <= BOARD_W_MM and 0 <= mid_y <= BOARD_H_MM):
                findings.append(Finding(
                    module="parse_cpl",
                    code="CPL-OUT-OF-BOARD",
                    title=f"`{refdes}` placed outside {BOARD_W_MM}x{BOARD_H_MM} mm outline",
                    severity=4,
                    detail=(
                        f"Mid X = {mid_x:.2f}, Mid Y = {mid_y:.2f}. Outside [0..{BOARD_W_MM}] x "
                        f"[0..{BOARD_H_MM}] mm. Either the outline is wrong or the placement is."
                    ),
                    refs=[refdes],
                ))

            # rotation offset hint
            if refdes in JLCPCB_ROTATION_OFFSET:
                expected_offset = JLCPCB_ROTATION_OFFSET[refdes]
                if expected_offset != 0 and rotation % 360 == 0:
                    findings.append(Finding(
                        module="parse_cpl",
                        code="CPL-ROTATION-SUSPECT",
                        title=f"`{refdes}` rotation 0 -- JLCPCB usually needs +{expected_offset} for this footprint",
                        severity=3,
                        detail=(
                            f"`{refdes}` ({raw.get('Layer','Top')}) is placed at rotation **0** "
                            f"but the JLCPCB rotation database recommends **+{expected_offset}** "
                            "for this LCSC footprint relative to the EDA-tool zero orientation. "
                            "If the EDA-tool zero matches the LCSC photo, this is fine; if not, "
                            "the part will be soldered rotated and may either short pins or fail "
                            "to make contact. **Verify against the LCSC product page photo before "
                            "ordering.**"
                        ),
                        refs=[refdes],
                        data=dict(rotation=rotation, jlcpcb_offset=expected_offset),
                    ))

    # overlap detection (centres < 0.5 mm)
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a["layer"] != b["layer"]:
                continue
            d = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
            if d < 0.5:
                findings.append(Finding(
                    module="parse_cpl",
                    code="CPL-OVERLAP-RISK",
                    title=f"`{a['refdes']}` and `{b['refdes']}` centres are {d:.2f} mm apart on {a['layer']}",
                    severity=4,
                    detail="Parts almost overlap; pick-and-place will fail or bridge solder.",
                    refs=[a["refdes"], b["refdes"]],
                ))

    placed = {r["refdes"] for r in rows}
    for refdes in bom_refdes:
        if refdes not in placed:
            findings.append(Finding(
                module="parse_cpl",
                code="CPL-MISSING-REFDES",
                title=f"`{refdes}` in BOM but missing from cpl.csv",
                severity=4,
                detail=(
                    f"`{refdes}` is on the BOM but not in the placement file. The part will "
                    "be reeled but never placed -- JLCPCB will pause the line and request a fix."
                ),
                refs=[refdes],
            ))

    return rows, findings
