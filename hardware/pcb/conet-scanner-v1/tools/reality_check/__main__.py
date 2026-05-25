"""Entry-point. Run from the conet-scanner-v1 directory:

    python3 -m tools.reality_check

It expects bom.csv / cpl.csv / gerbers.zip / schematic.md to live in the
current working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import (
    parse_bom,
    parse_cpl,
    parse_gerber,
    power_budget,
    strapping_check,
    adc_divider,
    topology_check,
    software_sim,
    wokwi_reality,
    report,
)


def main() -> int:
    cwd = Path.cwd()
    bom_p = cwd / "bom.csv"
    cpl_p = cwd / "cpl.csv"
    ger_p = cwd / "gerbers.zip"
    for p in (bom_p, cpl_p, ger_p):
        if not p.exists():
            print(f"missing input: {p}", file=sys.stderr)
            return 2

    print(">> parsing BOM ...")
    bom_rows, bom_f = parse_bom.parse(bom_p)
    bom_refdes = {r["refdes"] for r in bom_rows}

    print(">> parsing CPL ...")
    cpl_rows, cpl_f = parse_cpl.parse(cpl_p, bom_refdes)

    print(">> parsing Gerber ...")
    ger_summary, ger_f = parse_gerber.parse(ger_p)

    print(">> power budget analysis ...")
    # Pull F1 ihold value from the BOM. The format is "<N>A PTC" or "<N>mA PTC".
    ptc_ma = 1000  # safe default = 1 A (matches current BOM)
    for r in bom_rows:
        if r["refdes"] == "F1":
            import re
            m = re.match(r"(\d+(?:\.\d+)?)\s*(m?A)", r["comment"], re.IGNORECASE)
            if m:
                val = float(m.group(1))
                unit = m.group(2).lower()
                ptc_ma = int(val * (1 if unit.startswith("m") else 1000))
            break
    print(f"   F1 ihold = {ptc_ma} mA")
    power_table_typ, power_f_typ = power_budget.analyse(
        v_usb_v=5.0, ihold_ma=ptc_ma, clone_ldo=False, t_amb_c=25.0, rth_ja_c_w=60.0,
    )
    power_table_worst, power_f_worst = power_budget.analyse(
        v_usb_v=4.7, ihold_ma=ptc_ma, clone_ldo=True, t_amb_c=40.0, rth_ja_c_w=80.0,
    )
    # tag rows
    for r in power_table_typ:
        r["case"] = "typ_ti_25C"
    for r in power_table_worst:
        r["case"] = "worst_clone_40C"
    power_table = power_table_typ + power_table_worst
    power_f = power_f_typ + power_f_worst

    print(">> strapping check ...")
    strap_f = strapping_check.analyse()

    print(">> ADC divider analysis ...")
    adc_table, adc_f = adc_divider.analyse()

    print(">> topology cross-check ...")
    # repo root from cwd: cwd is hardware/pcb/conet-scanner-v1
    repo_root = cwd.parent.parent.parent
    topo_f = topology_check.analyse(repo_root)

    print(">> reality-adjusted software simulation ...")
    sim_runs, sim_f = software_sim.analyse(repo_root)

    print(">> emitting reality-adjusted wokwi diagram ...")
    reality_diag = repo_root / "firmware/tactile_scanner_esp32/wokwi/diagram.reality.json"
    try:
        wokwi_reality.build_diagram(reality_diag)
        print(f"   wrote {reality_diag}")
    except Exception as exc:   # noqa: BLE001
        print(f"   wokwi reality diagram failed: {exc}")

    out_md = cwd / "REALITY_CHECK.md"
    out_json = cwd / "reality_check_output" / "reality_check.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)

    print(">> building report ...")
    report.build(
        bom_findings=bom_f,
        cpl_findings=cpl_f,
        gerber_findings=ger_f,
        power_findings=power_f,
        strap_findings=strap_f,
        adc_findings=adc_f,
        topo_findings=topo_f,
        sim_findings=sim_f,
        sim_runs=sim_runs,
        power_table=power_table,
        adc_table=adc_table,
        gerber_summary=ger_summary,
        out_md=out_md,
        out_json=out_json,
    )

    n_total = sum(len(x) for x in (bom_f, cpl_f, ger_f, power_f, strap_f, adc_f, topo_f, sim_f))
    fire_or_critical = sum(1 for f in bom_f + cpl_f + ger_f + power_f + strap_f + adc_f + topo_f + sim_f if f.severity >= 4)
    print(f"DONE. {n_total} findings ({fire_or_critical} CRITICAL+). "
          f"Wrote {out_md.name} and reality_check_output/reality_check.json")
    return 0 if fire_or_critical == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
