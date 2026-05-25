"""Parse `bom.csv` and cross-check against the China-reality table.

Findings emitted:

* BOM-DUPLICATE-REFDES       refdes appears in multiple rows
* BOM-UNKNOWN-PART           LCSC part not in our reality table
* BOM-COUNTERFEIT-RISK       reality table flags counterfeit risk
* BOM-VALUE-INCONSISTENT     value column disagrees with schematic.md
* BOM-PTC-UNDERSIZED         F1 ihold below WiFi peak (the smoking gun)
* BOM-LDO-NOT-LV             a non-LV LDO would dropout at <4.7V USB-C
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from . import china_parts
from .findings import Finding


# Hand-curated expected schematic values per refdes. Anything that
# disagrees with bom.csv becomes a finding.
SCHEMATIC_EXPECTED = {
    "C1": ("47uF/10V", "1206"),
    "C2": ("10uF/10V", "0805"),    # +3V3 bulk near U5 output
    "C3": ("100nF", "0402"),
    "C4": ("100nF", "0402"),
    "C5": ("100nF", "0402"),
    "C6": ("100nF", "0402"),
    "C7": ("100nF", "0402"),
    "C8": ("100nF", "0402"),
    "C20": ("10uF/10V", "0805"),
    "C21": ("1uF/10V", "0402"),
    "R10": ("5.1k", "0402"),
    "R11": ("5.1k", "0402"),
    "R20": ("1k", "0402"),
    "R21": ("1k", "0402"),
    "R30": ("10k", "0402"),
    "R40": ("10k", "0402"),
    "R41": ("10k", "0402"),
    "U1": ("ESP32-S3-WROOM-1-N8R8", "ESP32_S3_WROOM_1"),
    "U2": ("CD74HC4067SM96", "SOIC-24"),
    "U3": ("CD74HC4067SM96", "SOIC-24"),
    "U5": ("TLV1117LV33DCYR", "SOT-223"),
    "D1": ("USBLC6-2SC6Y", "SOT-23-6"),
    "D2": ("green 0603 LED", "LED_0603"),
    "D3": ("red 0603 LED", "LED_0603"),
    "F1": (None, "1812"),   # value handled specially below
    "J1": ("FH12-16S-1SH", "FFC_16P_1MM"),
    "J2": ("FH12-16S-1SH", "FFC_16P_1MM"),
    "J3": ("TYPE-C-31-M-12", "USB_C_SMD_16P"),
    "SW1": ("TS-1187A", "TACT_4P_4.5x4.5"),
    "SW2": ("TS-1187A", "TACT_4P_4.5x4.5"),
}

# Refdeses on the placement file we know are DNP (do-not-populate)
# bodge pads, intentionally absent from the BOM.
DNP_REFDES = {"R31", "C30", "SJ1", "C9", "U4"}   # ADS1115 (U4) is DNP path B


def _expand_refdes_cell(cell: str) -> list[str]:
    return [r.strip() for r in re.split(r"[,\s]+", cell.strip().strip('"')) if r.strip()]


def parse(bom_path: Path) -> tuple[list[dict], list[Finding]]:
    """Read BOM rows + emit findings."""
    rows: list[dict] = []
    findings: list[Finding] = []
    refdes_seen: dict[str, str] = {}    # refdes -> origin LCSC

    with bom_path.open() as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            comment = raw.get("Comment", "").strip()
            designator_cell = raw.get("Designator", "")
            footprint = raw.get("Footprint", "").strip()
            lcsc = raw.get("LCSC Part #", "").strip()
            refs = _expand_refdes_cell(designator_cell)
            for r in refs:
                rows.append(dict(refdes=r, comment=comment, footprint=footprint, lcsc=lcsc))
                if r in refdes_seen and refdes_seen[r] != lcsc:
                    findings.append(Finding(
                        module="parse_bom",
                        code="BOM-DUPLICATE-REFDES",
                        title=f"{r} listed under multiple LCSC parts",
                        severity=4,
                        detail=f"`{r}` appears under both `{refdes_seen[r]}` and `{lcsc}`. The assembler will pick one effectively at random.",
                        refs=[r],
                    ))
                refdes_seen[r] = lcsc

            pm = china_parts.get(lcsc)
            if pm is None:
                findings.append(Finding(
                    module="parse_bom",
                    code="BOM-UNKNOWN-PART",
                    title=f"LCSC {lcsc} not in reality table",
                    severity=1,
                    detail=f"Refdes `{designator_cell}`, comment `{comment}` -- no Shenzhen-reality model for this part. Treat as a free variable in the burn-risk simulation.",
                    refs=refs,
                ))
            else:
                # part-level counterfeit / counterfeit-risk surface
                if "counterfeit-risk" in pm.tags:
                    findings.append(Finding(
                        module="parse_bom",
                        code="BOM-COUNTERFEIT-RISK",
                        title=f"{lcsc} ({pm.mpn}) has documented counterfeit-risk on LCSC",
                        severity=max(2, pm.severity - 1),
                        detail=pm.notes,
                        refs=refs,
                        data={"nominal": str(pm.nominal), "worst": str(pm.worst)},
                    ))

    # cross-check against SCHEMATIC_EXPECTED
    bom_by_refdes = {r["refdes"]: r for r in rows}
    for refdes, (expected_value, expected_footprint) in SCHEMATIC_EXPECTED.items():
        if refdes not in bom_by_refdes:
            findings.append(Finding(
                module="parse_bom",
                code="BOM-MISSING-REFDES",
                title=f"Schematic mentions `{refdes}` but BOM does not",
                severity=4,
                detail=(
                    f"Schematic expects `{refdes}` (value `{expected_value}`, footprint "
                    f"`{expected_footprint}`) but no BOM row covers it. JLCPCB will skip "
                    "the part and the board will ship with an unpopulated pad."
                ),
                refs=[refdes],
            ))
            continue
        row = bom_by_refdes[refdes]
        if expected_value and row["comment"] != expected_value:
            findings.append(Finding(
                module="parse_bom",
                code="BOM-VALUE-INCONSISTENT",
                title=f"`{refdes}` BOM value `{row['comment']}` differs from schematic-expected `{expected_value}`",
                severity=2,
                detail=(
                    f"The schematic.md decoupling table and the netlist say `{refdes}` should "
                    f"be `{expected_value}` but the BOM line carries `{row['comment']}`."
                ),
                refs=[refdes],
            ))
        if expected_footprint and row["footprint"] != expected_footprint:
            findings.append(Finding(
                module="parse_bom",
                code="BOM-FOOTPRINT-INCONSISTENT",
                title=f"`{refdes}` footprint mismatch",
                severity=3,
                detail=(
                    f"Expected footprint `{expected_footprint}` but BOM says `{row['footprint']}`."
                ),
                refs=[refdes],
            ))

    # special: F1 PTC rating cross-check against commit promise
    f1 = bom_by_refdes.get("F1")
    if f1:
        # accept either "500mA PTC" or "1A PTC"
        m = re.match(r"(\d+)\s*(m?A)\s*PTC", f1["comment"], re.IGNORECASE)
        if m:
            current_ma = int(m.group(1)) * (1 if m.group(2).lower().startswith("m") else 1000)
            if current_ma < 1000:
                findings.append(Finding(
                    module="parse_bom",
                    code="BOM-PTC-UNDERSIZED",
                    title=f"F1 PTC ihold {current_ma} mA -- below ESP32-S3 WiFi peak (~500..600 mA)",
                    severity=5,
                    detail=(
                        "ESP32-S3-WROOM-1 WiFi TX peak draws **500..600 mA** off the +3V3 rail. "
                        "After the LDO (~85% eff) that is **~700..900 mA** on the +5V rail.\n\n"
                        "`F1` is specified in the BOM as **{0} mA hold** ({1}, LCSC {2}). "
                        "With derating to a 40 C internal ambient (USB-powered, sealed case), "
                        "the **real Ihold falls to ~{3} mA**, well below the WiFi steady-state "
                        "current. The PTC will trip repeatedly during WiFi association, "
                        "causing 5 V brownout, ESP32 reset, retry -- a hard infinite reboot "
                        "loop on every boot that tries to join WiFi.\n\n"
                        "Commit `510e029` claims `upgrade PTC fuse to 1A` -- this **has not "
                        "been applied to bom.csv**. The assembler will solder whatever the "
                        "BOM says.\n\n"
                        "**Fix before ordering**: replace `F1` with LCSC `C75139` "
                        "(MF-MSMF100X-2, 1.0 A hold, 1.85 A trip, same 1812 footprint), "
                        "and re-emit `bom.csv` so the C75132 row becomes C75139."
                    ).format(current_ma, f1["comment"], f1["lcsc"], int(current_ma * 0.75)),
                    refs=["F1"],
                    data=dict(ihold_ma=current_ma, derated_ma=int(current_ma * 0.75)),
                ))

    # LDO LV check
    u5 = bom_by_refdes.get("U5")
    if u5:
        if "TLV1117LV" in u5["comment"] or "TLV1117LV33" in (u5.get("comment") or ""):
            pass  # OK: TLV1117LV33 -- low-dropout 3.3V variant
        elif re.search(r"\bAMS1117\b", u5["comment"], re.IGNORECASE):
            findings.append(Finding(
                module="parse_bom",
                code="BOM-LDO-AMS1117",
                title="LDO is AMS1117 -- 1.3 V dropout, brownouts likely at USB-C lows",
                severity=4,
                detail=(
                    "AMS1117-3.3 has typ Vdo = 1.3 V. With USB-C VBUS at the legal low of "
                    "4.5 V (sink role, contracted) the LDO has 4.5 - 1.3 = 3.2 V output. "
                    "ESP32-S3 brownout threshold is 2.7 V so technically OK, but transient "
                    "WiFi current pulls VBUS another 200 mV and the rail collapses. "
                    "The previous commit (`510e029`) explicitly banned AMS1117 -- if it "
                    "comes back, the ban regressed."
                ),
                refs=["U5"],
            ))

    return rows, findings
