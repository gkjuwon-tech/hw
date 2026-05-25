"""+5V -> F1 PTC -> U5 LDO -> +3V3 power budget under worst-case Shenzhen reality.

We sweep three operating states:

* IDLE   -- CPU 240 MHz, WiFi off, no scan.    Iout @ +3V3 ~  30 mA
* SCAN   -- WiFi off, 200 Hz scan, MUX active. Iout @ +3V3 ~  60 mA
* WIFI   -- WiFi TX peak in association burst. Iout @ +3V3 ~ 500 mA (700 mA worst)

Then we compute, for every state:

  I_in_5V   = I_out_3V3 / eta_ldo
  V_PTC     = I_in_5V * R_PTC                       (typ 0.15 ohm cold, 0.7 ohm hot)
  V_LDO_in  = V_USB - V_PTC
  V_LDO_out = V_LDO_in - Vdo(I_in_5V)
  P_LDO     = I_out_3V3 * (V_LDO_in - V_LDO_out)
  T_die     = T_amb + P_LDO * RthJA

and surface findings if anything goes out of safe range.
"""

from __future__ import annotations

from dataclasses import dataclass

from .findings import Finding


@dataclass
class Scenario:
    name: str
    i_out_3v3_a: float
    description: str
    duration_class: str  # "steady" or "burst" -- PTC only trips on steady


# Reality:
#   - "burst" currents (us..few-ms WiFi TX bursts) are absorbed by the
#     47 uF bulk cap on +5V and the 10 uF on +3V3. PTCs are thermal devices
#     and do not trip on sub-100 ms pulses; the relevant integral is
#     i^2 * t. 500 mA for 1 ms == 0.00025 A^2*s -- nowhere near the trip
#     I^2*t of a 1A PTC.
#   - "steady" currents (>100 ms continuous) do heat the PTC and matter.
#     ESP32-S3 average current with WiFi associated is ~150..250 mA on the
#     3V3 rail, not 500 mA. The 500 mA figure is the peak amplitude inside
#     the TX burst, not the time average.
SCENARIOS = [
    Scenario("IDLE",         0.030, "CPU 240 MHz, WiFi off, no scan",                "steady"),
    Scenario("SCAN",         0.060, "200 Hz scan loop, MUX active, WiFi off",         "steady"),
    Scenario("WIFI_AVG",     0.200, "WiFi connected, average current",               "steady"),
    Scenario("WIFI_PEAK",    0.500, "WiFi TX peak inside a burst (us..ms duration)", "burst"),
    Scenario("WIFI_HOTPA",   0.700, "WiFi peak with hot PA (degraded silicon)",      "burst"),
]


# Datasheet TLV1117LV33: Vdo ~= 0.16 V + 0.95 V/A * Iout (linear approx for 0..1A)
# Clone HT73xx: Vdo ~= 0.30 V + 1.5 V/A * Iout (worse slope, worse intercept)
def ldo_vdo_v(i_a: float, clone: bool) -> float:
    if clone:
        return 0.30 + 1.5 * i_a
    return 0.16 + 0.95 * i_a


def ldo_eta(v_in: float, v_out: float) -> float:
    # ideal series-pass efficiency = v_out / v_in
    if v_in <= 0:
        return 0.0
    return max(0.0, v_out / v_in)


def ptc_resistance_ohm(ihold_ma: int, tripped: bool) -> float:
    """Steady-state resistance of the PTC. Cold ~ 0.15 ohm, hot/tripped >> 50 ohm."""
    if tripped:
        return 100.0
    # Approx linear scaling with inverse Ihold (smaller PTC = higher Rcold).
    return 0.15 * (500.0 / max(ihold_ma, 50))


def ptc_trips(i_a: float, ihold_ma: int, duration_class: str, derate: float = 0.85) -> bool:
    """Trip predicate.

    `duration_class`:
       - "steady": continuous current > derated Ihold => trip after seconds.
       - "burst":  short pulse (<100 ms) -- PTC has thermal mass, does not
                   trip from amplitude alone. The bulk cap absorbs the peak.
    Derate default 0.85 = ihold at ~40C ambient for a typical 1812 PTC.
    """
    if duration_class == "burst":
        return False
    return i_a > (ihold_ma * derate / 1000.0)


def analyse(
    v_usb_v: float = 5.0,
    ihold_ma: int = 1000,
    clone_ldo: bool = False,
    t_amb_c: float = 40.0,
    rth_ja_c_w: float = 60.0,
) -> tuple[list[dict], list[Finding]]:
    findings: list[Finding] = []
    table: list[dict] = []

    for sc in SCENARIOS:
        i_3v3 = sc.i_out_3v3_a
        # Iterate Vdo since I_in depends on V_LDO_out
        v_3v3 = 3.30
        for _ in range(5):
            eta = ldo_eta(v_usb_v, v_3v3) or 0.8
            i_5v = i_3v3 / max(eta, 0.5)
            r_ptc = ptc_resistance_ohm(ihold_ma, ptc_trips(i_5v, ihold_ma, sc.duration_class))
            v_ptc = i_5v * r_ptc
            v_ldo_in = v_usb_v - v_ptc
            vdo = ldo_vdo_v(i_5v, clone_ldo)
            v_3v3_new = min(3.30, max(0.0, v_ldo_in - vdo))
            if abs(v_3v3_new - v_3v3) < 0.005:
                v_3v3 = v_3v3_new
                break
            v_3v3 = v_3v3_new
        p_ldo = i_3v3 * max(v_ldo_in - v_3v3, 0)
        t_die = t_amb_c + p_ldo * rth_ja_c_w
        tripped = ptc_trips(i_5v, ihold_ma, sc.duration_class)
        row = dict(
            scenario=sc.name,
            description=sc.description,
            duration_class=sc.duration_class,
            i_out_3v3_ma=round(i_3v3 * 1000, 1),
            i_in_5v_ma=round(i_5v * 1000, 1),
            v_ptc_v=round(v_ptc, 3),
            v_ldo_in_v=round(v_ldo_in, 3),
            v_3v3_v=round(v_3v3, 3),
            ldo_dropout_v=round(vdo, 3),
            ldo_dissipation_w=round(p_ldo, 3),
            ldo_die_temp_c=round(t_die, 1),
            ptc_tripped=tripped,
        )
        table.append(row)

        # Findings -- only flag *steady* low rails. A burst that the cap
        # absorbs is by definition transient and the LDO model doesn't
        # represent the cap, so do not double-count.
        if v_3v3 < 3.0 and sc.duration_class == "steady":
            findings.append(Finding(
                module="power_budget",
                code="PWR-RAIL-COLLAPSE",
                title=f"+3V3 rail collapses to {v_3v3:.2f} V in {sc.name}",
                severity=4 if v_3v3 < 2.7 else 3,
                detail=(
                    f"Scenario `{sc.name}` ({sc.description}): "
                    f"with V_USB={v_usb_v:.2f} V, F1 PTC ihold={ihold_ma} mA "
                    f"({'CLONE LDO' if clone_ldo else 'TI LDO'}), "
                    f"the +3V3 rail sags to **{v_3v3:.2f} V**. ESP32-S3 brownout "
                    f"threshold is configurable but defaults to 2.7 V. Below 3.0 V the WiFi "
                    f"PLL stops locking and BLE coexistence fails."
                ),
                refs=["F1", "U5"],
                data=row,
            ))
        if tripped:
            findings.append(Finding(
                module="power_budget",
                code="PWR-PTC-TRIPS",
                title=f"F1 PTC trips during {sc.name} (I_in = {i_5v*1000:.0f} mA, Ihold derated = {ihold_ma*0.75:.0f} mA)",
                severity=5 if sc.name in {"SCAN", "IDLE"} else 4,
                detail=(
                    f"In scenario `{sc.name}` the steady-state 5 V current draws "
                    f"**{i_5v*1000:.0f} mA**, which exceeds the derated Ihold of "
                    f"{ihold_ma*0.75:.0f} mA. The PTC enters its high-resistance state "
                    "and the LDO input collapses; the ESP32 browns out and resets. After "
                    "reset the PTC is still hot, so it re-trips immediately -- the board "
                    "is stuck in a reset loop until power-cycled."
                ),
                refs=["F1"],
                data=row,
            ))
        # Thermal model. Steady currents matter for sustained die temp; bursts
        # only matter if their *repetition rate* is high enough to integrate
        # to a high average. WiFi association bursts are ~10% duty for ~200 ms,
        # so a 174 C burst die temp averaged 10% lands at ~55 C steady. Still
        # we surface it because the *first burst* runs above thermal shutdown
        # on a clone LDO.
        if t_die > 125 and sc.duration_class == "steady":
            findings.append(Finding(
                module="power_budget",
                code="PWR-LDO-HOT",
                title=f"U5 steady-state die temp {t_die:.0f} C in {sc.name}",
                severity=4 if t_die > 150 else 3,
                detail=(
                    f"Scenario `{sc.name}`: LDO dissipates {p_ldo*1000:.0f} mW steady, "
                    f"RthJA={rth_ja_c_w} C/W at {t_amb_c} C ambient => die "
                    f"**{t_die:.0f} C**. TLV1117LV thermal shutdown ~150 C; clone parts ~120 C. "
                    "Recommend more copper pour around U5 tab."
                ),
                refs=["U5"],
                data=row,
            ))
        elif t_die > 150 and sc.duration_class == "burst":
            findings.append(Finding(
                module="power_budget",
                code="PWR-LDO-BURST-TSD",
                title=f"U5 burst die temp {t_die:.0f} C in {sc.name} exceeds thermal shutdown",
                severity=3,
                detail=(
                    f"WiFi burst peak in scenario `{sc.name}` ({sc.description}) would, "
                    f"on a worst-case clone LDO at {t_amb_c} C ambient, push the die to "
                    f"**{t_die:.0f} C**. Clone TLV1117LV33 substitutes (HT7333, TP1117) "
                    "trigger thermal shutdown around 120-140 C. The first burst on a "
                    "clone part may foldback for tens of ms causing a brief +3V3 sag.\n\n"
                    "Mitigation:\n"
                    "* Use larger copper pour around U5 tab (target RthJA <= 35 C/W).\n"
                    "* Or replace U5 with an AP2112K-3.3 (LDO with native foldback + better RthJA).\n"
                    "* Or push WiFi power down via `WiFi.setTxPower(WIFI_POWER_11dBm)` in firmware."
                ),
                refs=["U5"],
                data=row,
            ))

    return table, findings
