"""China-sourced part reality adjustment table.

For each LCSC part number on the BOM, we encode three columns:

  nominal  -- what the datasheet (or the schematic comment) claims
  worst    -- worst plausible behaviour for a JLCPCB "basic" or "extended"
              part actually shipped from Shenzhen. This is calibrated against
              hobbyist failure reports on EEVblog, Hackaday, and EDAboard,
              plus the LCSC review comments themselves.
  notes    -- short explanation of why the worst-case differs.

The intent is NOT to claim every Chinese part is bad. It is to give a
defensible upper bound on the manufacturing-induced spread so we can answer
the question: "if every part on the BOM rolled snake eyes simultaneously,
would this board still come out of the JLCPCB box working, or would it
smoke?"

Only values that propagate into a numeric model elsewhere in the analysis
need to be filled. The other parts are listed so we have a complete map of
which refdeses we have a story for.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class PartModel:
    lcsc: str
    mpn: str
    # nominal datasheet value. Free-form: float, tuple, or str.
    nominal: Any
    # worst plausible after Shenzhen reality (process + counterfeit risk).
    worst: Any
    # one-line story explaining the worst column.
    notes: str
    # severity if worst-case happens, on a 0..5 scale:
    #   0 = cosmetic, 5 = visible smoke / fire on first power-up.
    severity: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Keyed by LCSC part number so a CSV-driven cross-check is trivial.
PARTS: dict[str, PartModel] = {
    # ----- Resistors (0402 thick-film, 1% marked) ---------------------
    "C11702": PartModel(
        lcsc="C11702",
        mpn="0402WGF1001TCE (UNI-ROYAL)",
        nominal=("1000 ohm", "+/- 1%", "1/16 W"),
        # UNI-ROYAL thick films are honest 1% on the label but the
        # 0402 dies are often the same wafer as their 5% line; pulled
        # measurements from JLCPCB show +/-2.5% 3-sigma in batches.
        worst=("1000 ohm", "+/- 3%", "1/16 W"),
        notes="0402 thick-film tolerance widens to ~3% in real batches; thermal coeff up to +/- 300 ppm/C unspec'd.",
        severity=1,
        tags=["passive", "led-current-limit"],
    ),
    "C25744": PartModel(
        lcsc="C25744",
        mpn="0402WGF1002TCE (UNI-ROYAL)",
        nominal=("10000 ohm", "+/- 1%", "1/16 W"),
        worst=("10000 ohm", "+/- 3%", "1/16 W"),
        notes="Used as ADC pull-down (R30) -- a 3% drift directly skews every cell reading. Calibration absorbs it.",
        severity=2,
        tags=["passive", "adc-divider"],
    ),
    "C25905": PartModel(
        lcsc="C25905",
        mpn="0402WGF5101TCE (UNI-ROYAL)",
        nominal=("5100 ohm", "+/- 1%", "1/16 W"),
        worst=("5100 ohm", "+/- 3%", "1/16 W"),
        notes="USB-C CC pull-down. Spec says 5.1k +/- 20% is the legal window for sink role, so 3% is non-issue.",
        severity=0,
        tags=["passive", "usb-cc"],
    ),

    # ----- Capacitors (MLCC, X5R/X7R, 0402..1206) ---------------------
    "C1525": PartModel(
        lcsc="C1525",
        mpn="CL05B104KO5NNNC (Samsung) -- often substituted with FH or YAGEO equivalent",
        nominal=("100 nF", "X7R", "10 V", "+/- 10%"),
        # MLCC DC bias on 0402/10V X7R at +3V3 typically drops about 25%
        # of nominal capacitance. JLCPCB substitutes with X5R routinely.
        worst=("60..75 nF effective", "X5R", "10 V", "+/- 20%"),
        notes="DC bias of -25% at +3V3 on tiny case sizes. Decoupling effectiveness reduced; ESP32 brownouts during WiFi TX become possible.",
        severity=2,
        tags=["passive", "decoupling", "dc-bias"],
    ),
    "C15849": PartModel(
        lcsc="C15849",
        mpn="CL05A105KP5NNNC (Samsung)",
        nominal=("1 uF", "X5R", "10 V", "+/- 10%"),
        worst=("0.55 uF effective", "X5R", "10 V", "+/- 20%"),
        notes="LDO input cap. Tantalum or correct 6V3 X5R would be safer. A 45% droop here lets the LDO oscillate during USB-C inrush.",
        severity=3,
        tags=["passive", "ldo-input", "dc-bias", "stability"],
    ),
    "C15850": PartModel(
        lcsc="C15850",
        mpn="CL21A106KOQNNNE (Samsung)",
        nominal=("10 uF", "X5R", "10 V", "+/- 10%"),
        worst=("5..7 uF effective", "X5R", "10 V", "+/- 20%"),
        notes="0805 10uF X5R 10V loses ~30..50% at +3V3 due to DC bias. Combined with LDO output requirement this is borderline.",
        severity=3,
        tags=["passive", "ldo-output", "dc-bias"],
    ),
    "C19702": PartModel(
        lcsc="C19702",
        mpn="CL31A476KAHNNNE (Samsung)",
        nominal=("47 uF", "X5R", "10 V", "+/- 10%"),
        worst=("20..28 uF effective", "X5R", "10 V", "+/- 20%"),
        notes="1206 bulk on +5V. DC bias at 5V on 10V part is ~40..55% drop. Still fine for ESP32 WiFi transients but inrush rise time gets faster.",
        severity=1,
        tags=["passive", "bulk", "dc-bias"],
    ),

    # ----- Power components --------------------------------------------
    "C155591": PartModel(
        lcsc="C155591",
        mpn="TLV1117LV33DCYR (TI, SOT-223)",
        # Genuine TI: 1.0 A max, 1.15 V max dropout @ 1 A, thermal RthJA
        # for SOT-223 with 1 oz copper = 60 C/W (no copper pour) down
        # to 30 C/W with a generous pour.
        nominal=("3.3 V +/- 1%", "Iout 1 A", "Vdo 1.15 V @ 1 A", "RthJA 60 C/W"),
        # LCSC C155591 is genuine TI most of the time, but Shenzhen
        # is also flooded with HGSemi HT7333-1 and 3PEAK TP1117 that
        # get relabelled. Watch for:
        #   * dropout climbing to ~1.4 V at 0.5 A on the fake parts;
        #   * thermal shutdown at ~120 C die temp on the clones (vs
        #     150 C on the genuine TLV).
        worst=("3.3 V +/- 3%", "Iout 0.6 A before thermal foldback", "Vdo 1.4 V @ 0.5 A", "RthJA 80 C/W"),
        notes="If the part is a relabelled HT73xx clone, Vdo at 500 mA WiFi peak climbs to ~1.4 V leaving Vout = 5 - 1.4 = 3.6 V minus diode drops; OK on paper but thermal shutdown is the real risk.",
        severity=3,
        tags=["power", "ldo", "thermal", "counterfeit-risk"],
    ),
    "C75132": PartModel(
        lcsc="C75132",
        mpn="MF-MSMF050X-2 (Bourns 1812 PTC, 500 mA hold, 1 A trip)",
        nominal=("Ihold 500 mA", "Itrip 1.0 A @ 25 C", "Vmax 16 V", "trip time 0.1..1 s @ 1 A"),
        worst=("Ihold 380 mA @ 40 C ambient", "Itrip 760 mA", "trip time 60 ms at 1 A inrush"),
        notes=(
            "*** Historical artifact ***. The original BOM specified this 500 mA part. Commit "
            "510e029 replaced it with C150410 (1A PTC). If F1 is ever rolled back to C75132 "
            "for any reason, brownout reboots on WiFi association are essentially guaranteed."
        ),
        severity=4,
        tags=["power", "ptc", "brownout", "historical"],
    ),
    "C150410": PartModel(
        lcsc="C150410",
        mpn="1812 1A PTC (LCSC house brand, polymer 1A hold)",
        # Generic 1812 polymer PTCs at this rating have:
        #   - Ihold 1.0 A @ 23 C
        #   - Ihold ~ 0.85 A @ 40 C (derate 0.85), ~ 0.75 A @ 60 C
        #   - Itrip ~ 2.0 A @ 25 C
        #   - Cold R ~ 0.10 ohm, hot/tripped R > 50 ohm
        #   - trip time at 2 A ~ 200 ms, at 3 A ~ 50 ms
        # Reality: house-brand 1812 PTCs at this LCSC price point sometimes
        # under-perform by ~15% vs the datasheet. Still well above the
        # ESP32-S3 WiFi steady-state current.
        nominal=("Ihold 1.0 A @ 23 C", "Itrip 2.0 A @ 25 C", "R_cold 0.10 ohm", "Vmax 30 V"),
        worst=("Ihold 0.75 A @ 40 C ambient (derate 0.85x AND -15% spec spread)",
               "Itrip 1.6 A", "R_cold 0.15 ohm", "trip time at 1A inrush > 1 s"),
        notes=(
            "Replacement for the original 500 mA PTC. Even at the worst-case derated 750 mA, "
            "this is above the ESP32-S3 WiFi steady-state current (~500 mA peak, but bursty "
            "with ~50% duty during association). PTC trip during WiFi peak is unlikely; the "
            "only failure mode left is the 5 V brownout caused by VBUS sag during inrush, "
            "which is governed by the bulk capacitor C1 (47 uF) and the USB-C source, not "
            "by the PTC."
        ),
        severity=1,
        tags=["power", "ptc"],
    ),

    # ----- Active silicon ---------------------------------------------
    "C5183": PartModel(
        lcsc="C5183",
        mpn="CD74HC4067SM96 (TI marking; LCSC often ships HGSemi or 3PEAK clone)",
        # Genuine TI: R_on typ 70 ohm @ Vcc=4.5V, 180 ohm @ Vcc=3V.
        # Spread up to 270 ohm worst over temperature.
        nominal=("R_on typ 180 ohm @ Vcc=3.3V", "R_on max 270 ohm", "Ileak <1 uA", "tpd 30 ns"),
        # The white-label parts at C5183 price point ($0.30/each) are
        # routinely R_on 250..420 ohm with the same 4067 die topology.
        # Mux leakage rises to ~5 uA.
        worst=("R_on typ 320 ohm @ Vcc=3.3V", "R_on max 450 ohm", "Ileak 5 uA at 70 C", "tpd 50 ns"),
        notes=(
            "*** Top measurement-quality risk ***. The ADC divider math assumes R_mux_on = 80 "
            "ohm in the schematic. Real R_on at 3V3 on a genuine TI is already 180 ohm; on a "
            "clone it can hit 450 ohm worst-case. With 2 muxes in series that is up to 900 ohm "
            "of fixed series resistance in front of R_cell. Below ~5 kohm of pressure the "
            "reading collapses into the mux noise floor."
        ),
        severity=2,
        tags=["mux", "adc-divider", "counterfeit-risk"],
    ),
    "C37593": PartModel(
        lcsc="C37593",
        mpn="ADS1115IDGSR (TI, MSOP-10)",
        # Real TI: INL +/- 2 LSB at FS=4.096V on a 16-bit grid.
        # ENOB ~ 15.5 bits at 8 SPS, drops to ~14 at 860 SPS.
        nominal=("16-bit dSigma", "INL +/-2 LSB", "ENOB 14 @ 860 SPS", "PGA gain 2/3..16"),
        # Counterfeit ADS1115 is one of the most reported fake parts
        # on LCSC. The clones are usually 12-bit dice in a 16-bit
        # wrapper; bottom 4 bits are pure noise. PGA gain 2/3 often
        # missing, locking the part to gain >= 1 (=> max input 4.096 V
        # not 6.144 V, which is fine here).
        worst=("effective 12-bit", "INL +/-8 LSB", "ENOB 11 @ 860 SPS", "PGA only 1..16"),
        notes="Default path is the ESP32 internal ADC (path A) so a fake ADS1115 just disables path B. Bring-up team has to know not to chase '16-bit accuracy' on the bench.",
        severity=2,
        tags=["adc", "counterfeit-risk"],
    ),
    "C2913201": PartModel(
        lcsc="C2913201",
        mpn="ESP32-S3-WROOM-1-N8R8 (Espressif)",
        nominal=(
            "240 MHz dual-core",
            "8 MB QSPI flash",
            "8 MB octal PSRAM",
            "WiFi TX peak 500..600 mA @ +3V3",
            "Boot strap GPIO0/45/46",
        ),
        # Genuine Espressif modules are remarkably consistent. The
        # only "China reality" item is that the antenna keep-out
        # requirement (15 mm) is ignored on most 60x40mm boards.
        worst=(
            "240 MHz dual-core",
            "8 MB QSPI flash",
            "8 MB octal PSRAM (REQUIRES the N8R8 variant; N16R8 and N8 will not run a PSRAM build)",
            "WiFi TX 700 mA peaks if PA hot",
            "antenna gain -6..-9 dBi when ground plane crosses keep-out",
        ),
        notes="Espressif itself is reliable; the failure mode is the surrounding board (PTC trip, antenna keep-out, strapping pins). Listed at severity 0 for the module alone.",
        severity=0,
        tags=["mcu"],
    ),
    "C7519": PartModel(
        lcsc="C7519",
        mpn="USBLC6-2SC6Y (ST, SOT-23-6)",
        nominal=("ESD +/- 15 kV contact", "Cap 3 pF per line", "VRWM 5.25 V"),
        worst=("ESD +/- 10 kV contact", "Cap 5 pF per line", "VRWM 5.25 V"),
        notes="Counterfeit USBLC6 from LCSC sometimes are unbranded SOT-23-6 ESD diodes; capacitance rises and HS USB 480 Mbps eye closes. Full-speed (12 Mbps) like ESP32-S3 native USB is unaffected.",
        severity=0,
        tags=["esd", "usb"],
    ),
    "C165948": PartModel(
        lcsc="C165948",
        mpn="TYPE-C-31-M-12 (KH no-name; 16-pin SMD)",
        nominal=("USB-C receptacle", "3 A current rating", "Mating 10000 cycles"),
        # The TYPE-C-31-M-12 has a notorious failure mode: the
        # mid-mount tabs do not always make solid contact with the
        # board edge, leading to mechanically wobbly USB receptacles
        # that intermittently fail after 50..200 plug cycles. Many
        # LCSC reviews call this out.
        worst=("3 A rating only with all VBUS pins tied", "Mating 200..500 cycles before flake", "CC pins sometimes shorted to shield via flash"),
        notes="Mechanical fragility is the dominant failure mode; specify all four VBUS pads and both GND/shield pads connected in copper. Inspect first-article boards for solder bridges between CC1/CC2 and shield.",
        severity=2,
        tags=["connector", "mechanical"],
    ),
    "C72669": PartModel(
        lcsc="C72669",
        mpn="FH12-16S-1SH (Hirose)",
        nominal=("FFC 16-pin", "1.0 mm pitch", "0.5 A per contact"),
        worst=("often substituted with KH FH12 lookalike if Hirose OOS", "0.3 A per contact on the clone"),
        notes="Mesh ROW/COL conductive thread carries microamps so the per-contact derating is non-issue. Verify it is the Hirose part not a substitute -- the clones have looser ZIF actuation force.",
        severity=0,
        tags=["connector"],
    ),
    "C318884": PartModel(
        lcsc="C318884",
        mpn="TS-1187A-B-A-B (XKB) -- 4-pin tactile",
        nominal=("4-pin tactile", "12 V/50 mA rated", "click force 160 gf"),
        worst=("contact bounce up to 20 ms", "rated 12 V/50 mA"),
        notes="BOOT button bounce can cause spurious download-mode entries; mitigated in firmware by 50 ms debounce in the existing scanner code.",
        severity=0,
        tags=["switch"],
    ),
    "C2287": PartModel(
        lcsc="C2287",
        mpn="0603 red LED (KT-0603R, KENTO)",
        nominal=("Vf 2.0 V @ 20 mA", "If max 30 mA"),
        worst=("Vf 1.8..2.2 V @ 20 mA", "binned dim/bright"),
        notes="With 1k current-limit at 3V3, I_LED = (3.3 - 2.0)/1000 = 1.3 mA. Safely below max. Brightness will vary visibly across boards.",
        severity=0,
        tags=["led"],
    ),
    "C72043": PartModel(
        lcsc="C72043",
        mpn="0603 green LED (ORH-G36G, ORH-OPTOH)",
        nominal=("Vf 3.0 V @ 20 mA"),
        worst=("Vf 2.7..3.3 V @ 20 mA"),
        notes="With 1k limit at 3V3: I_LED = (3.3 - 3.0)/1000 = 0.3 mA -- the LED will barely glow on most boards. Worst-case Vf 3.3 V => LED dark. Recommend 470 ohm.",
        severity=1,
        tags=["led", "brightness"],
    ),
}


def get(lcsc: str) -> PartModel | None:
    return PARTS.get(lcsc)


def all_parts() -> list[PartModel]:
    return list(PARTS.values())


def severity_summary() -> dict[int, list[str]]:
    out: dict[int, list[str]] = {i: [] for i in range(6)}
    for p in PARTS.values():
        out[p.severity].append(f"{p.lcsc} ({p.mpn})")
    return out
