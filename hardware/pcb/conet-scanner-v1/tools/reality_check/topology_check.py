"""Cross-check schematic vs Wokwi diagram vs firmware source for the
ADC sampling topology. There are three documents that describe the same
analog signal path and they need to be consistent:

  * schematic.md (the design intent, human-readable netlist)
  * firmware/tactile_scanner_esp32/tactile_scanner_esp32.ino (what the CPU
    actually runs)
  * firmware/.../wokwi/diagram.json (what the simulator believes the board
    looks like)

If they disagree, then either:
  (a) the silicon does NOT measure what the schematic claims to measure;
  (b) the simulator passes "all green" but the silicon fails;
  (c) both — the most embarrassing case on first power-up.

Findings emitted:

* TOPO-NO-VPLUS              schematic divider formula cites +3V3 but no
                             netlist row connects +3V3 to either MUX SIG
* TOPO-WOKWI-MIRRORED        wokwi diagram has row_mux:SIG tied to +3V3 and
                             col_mux:SIG to ADC -- opposite of schematic prose
* TOPO-FIRMWARE-INA826       firmware top-of-file comment claims INA826 in
                             the analog path, but neither BOM nor schematic
                             instantiates one
* TOPO-WOKWI-BOARD-MISMATCH  wokwi board variant is devkitc-1 without PSRAM,
                             real board is WROOM-1-N8R8 with octal PSRAM
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .findings import Finding


def analyse(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []

    schem = (repo_root / "hardware/pcb/conet-scanner-v1/schematic.md").read_text()
    ino   = (repo_root / "firmware/tactile_scanner_esp32/tactile_scanner_esp32.ino").read_text()
    diag  = json.loads((repo_root / "firmware/tactile_scanner_esp32/wokwi/diagram.json").read_text())

    # ---- 1. schematic +3V3 sourcing for the divider ---------------------
    # Look for an explicit netlist row that ties +3V3 into either MUX SIG.
    netlist_mentions_vp_on_mux = bool(re.search(
        r"\+3V3.*(U2|U3).*SIG", schem, re.IGNORECASE
    )) or bool(re.search(
        r"(U2|U3).*SIG.*\+3V3", schem, re.IGNORECASE
    ))
    formula_uses_vp = "+3V3 ×" in schem or "+3V3 \\*" in schem or "+3V3 x" in schem
    if formula_uses_vp and not netlist_mentions_vp_on_mux:
        findings.append(Finding(
            module="topology_check",
            code="TOPO-NO-VPLUS",
            title="schematic divider formula cites +3V3 but no netlist row sources it",
            severity=4,
            detail=(
                "`schematic.md` writes the ADC divider as\n\n"
                "```\n"
                "V_ADC = +3V3 × ( R30 / (R30 + R_cell + R_mux_on*2) )\n"
                "```\n\n"
                "but the netlist tables list `U2 SIG = ADC_IN` and `U3 SIG = GND via R30` "
                "with **no explicit row anywhere that connects +3V3 to either MUX SIG**. "
                "If the silicon really is built as the netlist describes, the cell sits "
                "between two MUX Y-pins and there is no current source. ADC reads will "
                "float around ~0 V.\n\n"
                "The Wokwi diagram (`diagram.json`) silently fixes this by tying "
                "`row_mux:SIG` to `+3V3`. If that *is* the intended hardware, the "
                "schematic netlist is incomplete: add a row\n\n"
                "  | `+3V3` | U2.SIG |\n\n"
                "and explain it in the prose, so the PCB layout actually routes copper "
                "from the LDO output to U2.SIG."
            ),
            refs=["schematic.md"],
        ))

    # ---- 2. wokwi vs schematic topology --------------------------------
    conns = diag.get("connections", [])
    wokwi_row_sig_to_v = any(
        (("row_mux:SIG" in a or "row_mux:SIG" in b) and
         (a.endswith("3V3.1") or b.endswith("3V3.1")))
        for entry in conns
        for a, b in [(entry[0], entry[1])]
    )
    wokwi_col_sig_to_adc = any(
        (("col_mux:SIG" in a or "col_mux:SIG" in b) and
         ("esp:1" in a or "esp:1" in b))
        for entry in conns
        for a, b in [(entry[0], entry[1])]
    )
    # Look for a netlist row that points U2.SIG at ADC_IN specifically.
    # The schematic uses lines like ``| U2 SIG | +3V3 |`` and
    # ``| U3 SIG | ADC_IN ... |`` -- those are the rows we want to parse,
    # not just "are the strings present somewhere in the file".
    row_to_adc_re = re.compile(
        r"U2[\s_]*SIG[^\n]{0,80}?(?:ADC_IN|GPIO\s*1\b)",
        re.IGNORECASE,
    )
    col_to_adc_re = re.compile(
        r"U3[\s_]*SIG[^\n]{0,80}?(?:ADC_IN|GPIO\s*1\b)",
        re.IGNORECASE,
    )
    schem_says_row_to_adc = bool(row_to_adc_re.search(schem))
    schem_says_col_to_adc = bool(col_to_adc_re.search(schem))
    # Only flag the mirror if the schematic genuinely points the row MUX at
    # the ADC AND does not also point the col MUX there -- i.e. the prose
    # describes the opposite topology from the Wokwi diagram. If the
    # schematic agrees with Wokwi (col->ADC, row->+3V3) we stay silent.
    if (wokwi_row_sig_to_v and wokwi_col_sig_to_adc
            and schem_says_row_to_adc and not schem_says_col_to_adc):
        findings.append(Finding(
            module="topology_check",
            code="TOPO-WOKWI-MIRRORED",
            title="Wokwi diagram and schematic disagree on which MUX feeds the ADC",
            severity=3,
            detail=(
                "Wokwi `diagram.json`:\n"
                "* `row_mux:SIG` <-> `esp:3V3.1`      (row side = current source)\n"
                "* `col_mux:SIG` <-> `esp:1`           (col side = ADC)\n"
                "* `col_mux:SIG` <-> 10k <-> GND       (pull-down on col side)\n\n"
                "Schematic prose:\n"
                "* `U2 SIG` -> `ADC_IN` -> `GPIO 1`    (row side = ADC, per the netlist)\n"
                "* `U3 SIG` -> R30 10k -> GND          (col side pulled down)\n\n"
                "The two describe **mirror-image** circuits. The math (and the firmware) "
                "doesn't care which side is the source and which side is the ADC -- the "
                "divider produces the same V_ADC either way. But:\n\n"
                "1. The PCB copper has to match *one* of them. If the layout follows the "
                "   schematic, the simulator is testing a circuit that doesn't exist on "
                "   silicon.\n"
                "2. The firmware reads `GPIO 1 (ADC1_CH0) = ADC_IN`. In the schematic "
                "   wiring this is U2.SIG (row side); in the Wokwi wiring it is U3.SIG "
                "   (col side). The MUX row/col select code in `.ino` assumes the **row "
                "   side is the constant +3V3 source** (one MUX always drives, the other "
                "   always samples) -- this matches Wokwi, not schematic prose.\n\n"
                "Conclusion: **the schematic prose is wrong; the Wokwi diagram is right**. "
                "Update `schematic.md` so the netlist matches the silicon. The PCB Gerbers "
                "should be re-inspected to confirm copper actually routes `+3V3` to "
                "`U2.SIG` and not the other way around."
            ),
            refs=["schematic.md", "diagram.json"],
        ))

    # ---- 3. firmware comment references INA826 not in BOM ---------------
    if "INA826" in ino:
        bom = (repo_root / "hardware/pcb/conet-scanner-v1/bom.csv").read_text()
        if "INA826" not in bom:
            findings.append(Finding(
                module="topology_check",
                code="TOPO-FIRMWARE-INA826",
                title="firmware comment claims INA826 differential amp; BOM does not include one",
                severity=2,
                detail=(
                    "`tactile_scanner_esp32.ino` top-of-file comment:\n\n"
                    "> ... samples one piezo-resistive cell at a time through an "
                    "**INA826 differential amplifier** connected to ADC1.\n\n"
                    "The BOM has no INA826. The `analogRead(ADC_PIN)` in the actual loop "
                    "reads the MUX SIG node directly with no front-end amplification.\n\n"
                    "Either:\n"
                    "* The comment is stale and should be removed -- silicon doesn't have "
                    "  an INA826; the divider math runs unbuffered.\n"
                    "* Or path B (ADS1115) was supposed to be the differential path and the "
                    "  INA826 mention is a leftover from an earlier revision.\n\n"
                    "Cosmetic but misleading; flag for whoever brings up the first article."
                ),
                refs=["tactile_scanner_esp32.ino"],
            ))

    # ---- 4. wokwi board variant vs real module --------------------------
    parts = diag.get("parts", [])
    esp_part = next((p for p in parts if p.get("type", "").startswith("board-esp32-s3")), None)
    if esp_part:
        attrs = esp_part.get("attrs", {})
        psram = attrs.get("psramType")
        flash = attrs.get("flashSize")
        notes = []
        if psram in (None, "none"):
            notes.append(f"`psramType` = `{psram}`, but real module is WROOM-1-**N8R8** "
                         "(8 MB octal PSRAM). Any firmware code that uses PSRAM "
                         "(`ESP.getPsramSize() > 0`) passes the wokwi test silently and "
                         "fails on silicon.")
        if flash and str(flash) != "8":
            notes.append(f"`flashSize` = `{flash}` MB, but real module is **N8** (8 MB). "
                         "Partition tables that overflow the simulator's 4 MB image will "
                         "be silently truncated by wokwi and crash on silicon.")
        if notes:
            findings.append(Finding(
                module="topology_check",
                code="TOPO-WOKWI-BOARD-MISMATCH",
                title="Wokwi board attrs do not match the WROOM-1-N8R8 part on the BOM",
                severity=3,
                detail="\n\n".join(notes),
                refs=["diagram.json", "U1"],
            ))

    # ---- 5. wokwi cell coverage ----------------------------------------
    cells = [p for p in parts if p.get("id", "").startswith("cell_")]
    if len(cells) < 256 // 4:   # at least 25% coverage
        findings.append(Finding(
            module="topology_check",
            code="TOPO-WOKWI-CELL-COVERAGE",
            title=f"Wokwi diagram only models {len(cells)} cells out of 256",
            severity=1,
            detail=(
                f"The 16x16 mesh has 256 cells. The Wokwi diagram instantiates only "
                f"**{len(cells)}** of them as wokwi-resistor parts. The remaining 251 "
                "cells appear as open circuits to the simulator. The scan loop will read "
                "those positions as 0 mV (good baseline) but the MUX cross-talk and "
                "leakage through unmodelled cells is invisible to the test. Test coverage "
                "is happy-path only."
            ),
            refs=["diagram.json"],
        ))

    return findings
