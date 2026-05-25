"""ADC divider reality model.

Schematic claim:
    V_ADC = +3V3 * R30 / (R30 + R_cell + 2*R_mux_on)
with R30=10k, R_mux_on=80 ohm.

Reality:
    R_mux_on at Vcc=3V3 on genuine TI is ~180 ohm typ, 270 ohm max,
    and on a Shenzhen clone is up to 450 ohm. Two mux channels in
    series therefore contribute 360..900 ohm of fixed series R that
    is NOT calibratable per-cell because it shifts with temperature.

We sweep R_cell over the practical mesh range and compare ADC counts
(ESP32-S3 12-bit, VREF ~3.3 V) under nominal vs. worst conditions.
"""

from __future__ import annotations

from .findings import Finding


def v_adc(r_cell_ohm: float, r30_ohm: float, r_mux_each: float, v3v3: float) -> float:
    series = r_cell_ohm + 2.0 * r_mux_each
    return v3v3 * r30_ohm / (r30_ohm + series)


def adc_counts(v: float, v_ref: float = 3.3, bits: int = 12) -> int:
    return int(round((v / v_ref) * ((1 << bits) - 1)))


def analyse() -> tuple[list[dict], list[Finding]]:
    table: list[dict] = []
    findings: list[Finding] = []

    # Mesh cell resistance: ~30 kohm un-pressed, drops to ~2 kohm fully pressed
    r_cells = [100_000, 30_000, 15_000, 8_000, 4_000, 2_000, 1_000, 500]

    cases = [
        ("schematic", 10_000, 80),       # what the schematic claims
        ("ti_typ",    10_000, 180),      # genuine TI CD74HC4067 at +3V3
        ("ti_worst",  10_000, 270),      # genuine TI worst over temperature
        ("clone_typ", 10_000, 320),      # LCSC C5183 clone typical
        ("clone_worst", 10_000, 450),    # clone worst
    ]

    for r in r_cells:
        row = {"r_cell_ohm": r}
        for label, r30, r_mux in cases:
            v = v_adc(r, r30, r_mux, 3.3)
            row[f"v_{label}"] = round(v, 4)
            row[f"adc_{label}"] = adc_counts(v)
        table.append(row)

    # Dynamic range: count distinct ADC steps between un-pressed (30k) and fully pressed (2k)
    def dynamic_range(label: str) -> tuple[int, int, int]:
        r30 = next(c[1] for c in cases if c[0] == label)
        r_mux = next(c[2] for c in cases if c[0] == label)
        v_low  = v_adc(30_000, r30, r_mux, 3.3)
        v_high = v_adc(2_000,  r30, r_mux, 3.3)
        return adc_counts(v_low), adc_counts(v_high), adc_counts(v_high) - adc_counts(v_low)

    dyn = {label: dynamic_range(label) for label, _, _ in cases}

    findings.append(Finding(
        module="adc_divider",
        code="ADC-DYNAMIC-RANGE",
        title="Real ADC dynamic range with MUX R_on reality is " +
              f"{dyn['clone_typ'][2]} counts (12-bit) -- {dyn['schematic'][2]} per schematic",
        severity=2,
        detail=(
            "The schematic divider math is optimistic. Computed counts between un-pressed "
            "(R_cell=30 kohm) and fully pressed (R_cell=2 kohm):\n\n"
            f"* Schematic (R_mux=80 ohm):     low={dyn['schematic'][0]} hi={dyn['schematic'][1]} span={dyn['schematic'][2]}\n"
            f"* Genuine TI typ (R_mux=180):   low={dyn['ti_typ'][0]} hi={dyn['ti_typ'][1]} span={dyn['ti_typ'][2]}\n"
            f"* Genuine TI worst (R_mux=270): low={dyn['ti_worst'][0]} hi={dyn['ti_worst'][1]} span={dyn['ti_worst'][2]}\n"
            f"* Clone typ (R_mux=320):        low={dyn['clone_typ'][0]} hi={dyn['clone_typ'][1]} span={dyn['clone_typ'][2]}\n"
            f"* Clone worst (R_mux=450):      low={dyn['clone_worst'][0]} hi={dyn['clone_worst'][1]} span={dyn['clone_worst'][2]}\n\n"
            "Numbers stay healthy (~2000 counts out of 4095) even on a clone, but the "
            "calibration is no longer linear in pressure -- a per-cell baseline subtraction "
            "remains mandatory. Reality model passes."
        ),
        refs=["U2", "U3", "R30"],
        data=dict(table=table, dyn=dyn),
    ))

    # PGA on ADS1115 path B
    findings.append(Finding(
        module="adc_divider",
        code="ADC-ADS-PGA-CAUTION",
        title="ADS1115 path B requires PGA gain = 1 (FS = +/-4.096V)",
        severity=2,
        detail=(
            "When jumper SJ1 routes U2 SIG to ADS1115 AIN0, the input swings 0..3.3 V "
            "single-ended. The ADS PGA defaults to gain 2 (FS = +/-2.048 V) on hardware "
            "reset; that saturates at 2.048 V => values above ~62% of full pressure "
            "clip. Firmware must explicitly set PGA = 001 (FS = +/-4.096 V) before "
            "the first read. README claims `PGA up to +/-0.256 V` which is the "
            "opposite end of the gain table -- the README text is wrong and will mislead "
            "anyone bringing up path B."
        ),
        refs=["U4", "SJ1"],
    ))

    return table, findings
