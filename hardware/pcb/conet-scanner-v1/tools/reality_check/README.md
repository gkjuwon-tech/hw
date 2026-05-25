# `reality_check` — pre-flight gate for the conet-scanner-v1 PCB order

This package answers one question, hard:

> If we send today's `gerbers.zip` + `bom.csv` + `cpl.csv` to JLCPCB,
> what is the realistic probability that the boards come back working
> versus DOA / smoking / measurement-quality-broken — taking into
> account that every silicon part on the BOM will be sourced from
> LCSC's Shenzhen reels, which means some non-trivial fraction will
> be relabelled clones with worse R_on / Vdo / ENOB than the marking
> claims?

The Wokwi test harness (`firmware/tactile_scanner_esp32/wokwi/`) is the
**logic** test: given an idealised hardware model, does the firmware
produce the right wire-format frames? This `reality_check` is the
**hardware** test: given the actual manufacturing artifacts that are
going to JLCPCB, does the board even survive first power-up?

## What it runs

```
$ cd hardware/pcb/conet-scanner-v1
$ python3 -m tools.reality_check
```

The driver does, in order:

| Step | Module | What it checks |
|-----:|:-------|:---------------|
| 1 | `parse_bom.py`     | every BOM row vs `china_parts.PARTS` (counterfeit risk, tolerance widening) and vs the schematic's expected refdes table (missing parts, footprint mismatch, value mismatch). |
| 2 | `parse_cpl.py`     | every placement vs JLCPCB rotation database; out-of-board placements; overlaps; refdeses placed without a BOM row (and vice versa). |
| 3 | `parse_gerber.py`  | unzips `gerbers.zip` and looks at every layer's aperture table + drawn segment count. Flags empty outer copper, missing inner planes, trace widths below the JLCPCB 3.5 mil minimum, drill sizes below 0.20 mm. |
| 4 | `power_budget.py`  | sweeps idle / scan / WiFi-avg / WiFi-peak / WiFi-hot-PA over both a TI-typ-at-25 C case and a worst-case-clone-at-40 C case. Flags steady-state rail collapse, PTC trip, LDO thermal shutdown. Burst transients are NOT counted as PTC trips because the 47 µF bulk and the PTC thermal mass absorb them. |
| 5 | `strapping_check.py`| ESP32-S3 strapping pin requirements (GPIO0, GPIO3, GPIO45, GPIO46) vs the schematic's actual wiring. PSRAM variant + antenna keep-out. |
| 6 | `adc_divider.py`   | recomputes V_ADC across R_cell = 100 kΩ .. 500 Ω for five R_mux models (schematic-ideal, TI-typ, TI-worst, clone-typ, clone-worst). Confirms the 12-bit dynamic range stays usable. |
| 7 | `topology_check.py`| cross-checks `schematic.md` netlist prose against `wokwi/diagram.json` against the `.ino` source. Catches the +3 V source-vs-sink ambiguity in the divider and the missing-INA826-but-firmware-mentions-it discrepancy. |
| 8 | `software_sim.py`  | builds `host_sim/scan_one_frame` and pipes three reality-adjusted ADC matrices through it (no_press / centre_press / edge_press). Confirms CRC + dims + flags phantom-touch and saturation issues. |
| 9 | `wokwi_reality.py` | emits `firmware/.../wokwi/diagram.reality.json` — a 256-cell, R_mux=320 Ω, PSRAM-on, 8 MB-flash version of the diagram, for the optional Wokwi cloud burn-in run. |
| 10 | `report.py`       | aggregates every finding into [`REALITY_CHECK.md`](../../REALITY_CHECK.md) + a JSON sidecar for CI annotations. |

The driver exits non-zero if any finding is `severity >= 4` (CRITICAL or
FIRE). The GitHub Actions wiring (`.github/workflows/ci.yml`, the
`firmware-reality-check` job) reuses this exit code as a release gate.

## Severity levels

| Level | Name | Meaning |
|------:|:-----|:--------|
| 5 | FIRE     | Visible smoke / fire on first power-up, or assembler outright rejects the order. |
| 4 | CRITICAL | Board boots but cannot complete its primary function (no WiFi, brownout loop, measurement saturates). |
| 3 | MAJOR    | Functional with significant degradation. |
| 2 | WARNING  | Works but with caveats; calibration or firmware tweak hides the symptom. |
| 1 | ADVISORY | Cosmetic / good-to-know; first-article inspection should look at it. |
| 0 | INFO     | Documented for traceability; no action. |

## Files in this directory

```
reality_check/
  __init__.py
  __main__.py        # entry point: `python3 -m tools.reality_check`
  README.md          # this file
  findings.py        # the Finding dataclass + SEVERITY_NAMES
  china_parts.py     # per-LCSC-part nominal / worst / notes / severity table
  parse_bom.py       # bom.csv -> Findings
  parse_cpl.py       # cpl.csv -> Findings (incl. JLCPCB rotation DB)
  parse_gerber.py    # gerbers.zip -> Findings (light-weight RS-274X reader)
  power_budget.py    # USB-C -> PTC -> LDO -> +3V3 budget under five load scenarios
  strapping_check.py # ESP32-S3 boot strapping vs schematic
  adc_divider.py     # ADC divider + ADS1115 PGA sanity
  topology_check.py  # schematic vs wokwi vs firmware ADC topology cross-check
  software_sim.py    # drive host_sim/scan_one_frame with reality matrices
  wokwi_reality.py   # emit diagram.reality.json (256 cells + R_mux + PSRAM)
  report.py          # aggregate -> REALITY_CHECK.md + JSON sidecar
```

## Extending

* **New part**: add an entry to `china_parts.PARTS` keyed by LCSC code,
  with `nominal`, `worst`, `notes`, `severity`, and `tags`. The BOM
  parser will pick it up automatically the next time the driver runs.
* **New rotation footprint**: extend `parse_cpl.JLCPCB_ROTATION_OFFSET`.
* **New power scenario**: extend `power_budget.SCENARIOS`.
* **New strapping pin requirement**: extend `strapping_check.STRAPPING_PINS`
  + `SCHEMATIC_BINDING`.

Every module emits `Finding` dataclasses; `report.py` formats them.
Keep the modules independent so future EDA-tool-emitted artifacts can
plug in without touching the runner.
