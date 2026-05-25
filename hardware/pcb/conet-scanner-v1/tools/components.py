"""Component table for the Conet Tactile Scanner v1 PCB.

Single source of truth for:
 - Bill of materials (BOM) entries (designator, value, footprint, LCSC #, populate flag).
 - Component placement (mid X, mid Y in mm, rotation in degrees, layer).
 - Footprint pad geometry (so the Gerber/drill generator can stamp the pads
   and pours without referring to an external EDA database).

The board origin is the bottom-left corner. +X is right, +Y is up. All
coordinates are in millimetres. Rotation is counter-clockwise from 0
(component reference orientation as drawn in ``footprints.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Component:
    refdes: str
    value: str
    footprint: str       # key into ``footprints.FOOTPRINTS``
    lcsc: str            # LCSC part number ("" for jumpers / DNP)
    x: float             # mid X (mm)
    y: float             # mid Y (mm)
    rotation: float = 0  # degrees, CCW
    layer: str = "top"   # "top" or "bottom"
    populate: bool = True
    comment: str = ""    # JLCPCB "Comment" column (human-readable value)
    description: str = ""  # extra description for BOM ``Description`` column


# Outline of the board. Edge_Cuts layer draws this rectangle. Mounting holes
# are added separately as NPTH 2.7mm.
BOARD_W = 60.0
BOARD_H = 40.0
BOARD_CORNER_R = 2.0     # rounded corner radius (mm)

MOUNTING_HOLES = [
    (4.0, 4.0),
    (BOARD_W - 4.0, 4.0),
    (4.0, BOARD_H - 4.0),
    (BOARD_W - 4.0, BOARD_H - 4.0),
]


COMPONENTS: list[Component] = [
    # ---- main ICs ----------------------------------------------------------
    Component(
        refdes="U1", value="ESP32-S3-WROOM-1-N8R8",
        footprint="ESP32_S3_WROOM_1", lcsc="C2913201",
        x=30.0, y=22.0, rotation=0,
        comment="ESP32-S3-WROOM-1-N8R8",
        description="WiFi/BT module, 8MB flash + 8MB PSRAM, native USB",
    ),
    Component(
        refdes="U2", value="CD74HC4067SM96",
        footprint="SOIC-24", lcsc="C5183",
        x=9.5, y=22.0, rotation=90,
        comment="CD74HC4067SM96",
        description="16:1 analog mux (row select)",
    ),
    Component(
        refdes="U3", value="CD74HC4067SM96",
        footprint="SOIC-24", lcsc="C5183",
        x=50.5, y=22.0, rotation=90,
        comment="CD74HC4067SM96",
        description="16:1 analog mux (column select)",
    ),
    Component(
        refdes="U4", value="ADS1115IDGSR",
        footprint="MSOP-10", lcsc="C37593",
        x=30.0, y=8.5, rotation=0, populate=False,
        comment="ADS1115IDGSR",
        description="16-bit Sigma-Delta ADC, I2C (DNP — alt sampling path)",
    ),
    Component(
        refdes="U5", value="TLV1117LV33DCYR",
        footprint="SOT-223", lcsc="C155591",
        x=10.5, y=7.5, rotation=0,
        comment="TLV1117LV33DCYR",
        description="3.3V LDO, 1A, SOT-223",
    ),

    # ---- USB-C / ESD / fuse ------------------------------------------------
    Component(
        refdes="J3", value="TYPE-C-31-M-12",
        footprint="USB_C_SMD_16P", lcsc="C165948",
        x=30.0, y=3.6, rotation=0,
        comment="TYPE-C-31-M-12", description="USB Type-C receptacle, SMD, 16-pin",
    ),
    Component(
        refdes="D1", value="USBLC6-2SC6Y",
        footprint="SOT-23-6", lcsc="C7519",
        x=44.5, y=7.0, rotation=0,
        comment="USBLC6-2SC6Y", description="USB-C ESD protection",
    ),
    Component(
        refdes="F1", value="1A PTC",
        footprint="1812", lcsc="C150410",
        x=21.0, y=7.0, rotation=0,
        comment="1812 1A PTC", description="Resettable PTC fuse, 1A hold, 1812",
    ),

    # ---- Mesh interface (FFC) ---------------------------------------------
    Component(
        refdes="J1", value="FH12-16S-1SH",
        footprint="FFC_16P_1MM", lcsc="C72669",
        x=15.0, y=36.5, rotation=0,
        comment="FH12-16S-1SH(55)", description="Hirose FFC ZIF, 16-pin, 1.0mm pitch — ROW",
    ),
    Component(
        refdes="J2", value="FH12-16S-1SH",
        footprint="FFC_16P_1MM", lcsc="C72669",
        x=45.0, y=36.5, rotation=0,
        comment="FH12-16S-1SH(55)", description="Hirose FFC ZIF, 16-pin, 1.0mm pitch — COL",
    ),

    # ---- buttons -----------------------------------------------------------
    Component(
        refdes="SW1", value="TS-1187A",
        footprint="TACT_4P_4.5x4.5", lcsc="C318884",
        x=53.0, y=33.0, rotation=0,
        comment="TS-1187A-B-A-B", description="Tactile switch, 4-pin, BOOT",
    ),
    Component(
        refdes="SW2", value="TS-1187A",
        footprint="TACT_4P_4.5x4.5", lcsc="C318884",
        x=53.0, y=27.0, rotation=0,
        comment="TS-1187A-B-A-B", description="Tactile switch, 4-pin, RESET",
    ),

    # ---- LEDs --------------------------------------------------------------
    Component(
        refdes="D2", value="green 0603 LED",
        footprint="LED_0603", lcsc="C72043",
        x=40.0, y=33.0, rotation=0,
        comment="ORH-G36G", description="Green 0603 LED — +3V3 rail status",
    ),
    Component(
        refdes="D3", value="red 0603 LED",
        footprint="LED_0603", lcsc="C2287",
        x=44.0, y=33.0, rotation=0,
        comment="KT-0603R", description="Red 0603 LED — firmware activity",
    ),

    # ---- bulk / decoupling caps -------------------------------------------
    Component(
        refdes="C1", value="47uF/10V",
        footprint="1206", lcsc="C19702",
        x=15.5, y=7.5, rotation=0,
        comment="CL31A476KAHNNNE", description="MLCC 47uF 10V X5R 1206 — +5V bulk",
    ),
    Component(
        refdes="C2", value="10uF/10V",
        footprint="0805", lcsc="C15850",
        x=22.0, y=33.5, rotation=0,
        comment="CL21A106KOQNNNE", description="MLCC 10uF 10V X5R 0805 — +3V3 bulk",
    ),
    Component(
        refdes="C20", value="10uF/10V",
        footprint="0805", lcsc="C15850",
        x=6.5, y=7.5, rotation=0,
        comment="CL21A106KOQNNNE", description="MLCC 10uF 10V X5R 0805 — LDO out",
    ),
    Component(
        refdes="C21", value="1uF/10V",
        footprint="0402", lcsc="C15849",
        x=15.5, y=11.0, rotation=0,
        comment="CL05A105KP5NNNC", description="MLCC 1uF 10V 0402 — LDO in",
    ),
    Component(
        refdes="C3", value="100nF",
        footprint="0402", lcsc="C1525",
        x=22.0, y=13.5, rotation=0,
        comment="CL05B104KO5NNNC", description="MLCC 100nF 0402 — U1 decouple",
    ),
    Component(
        refdes="C4", value="100nF",
        footprint="0402", lcsc="C1525",
        x=38.0, y=13.5, rotation=0,
        comment="CL05B104KO5NNNC", description="MLCC 100nF 0402 — U1 decouple",
    ),
    Component(
        refdes="C5", value="100nF",
        footprint="0402", lcsc="C1525",
        x=26.5, y=33.5, rotation=0,
        comment="CL05B104KO5NNNC", description="MLCC 100nF 0402 — U1 decouple",
    ),
    Component(
        refdes="C6", value="100nF",
        footprint="0402", lcsc="C1525",
        x=33.5, y=33.5, rotation=0,
        comment="CL05B104KO5NNNC", description="MLCC 100nF 0402 — U1 decouple",
    ),
    Component(
        refdes="C7", value="100nF",
        footprint="0402", lcsc="C1525",
        x=9.5, y=30.0, rotation=0,
        comment="CL05B104KO5NNNC", description="MLCC 100nF 0402 — U2 decouple",
    ),
    Component(
        refdes="C8", value="100nF",
        footprint="0402", lcsc="C1525",
        x=46.0, y=37.5, rotation=0,
        comment="CL05B104KO5NNNC", description="MLCC 100nF 0402 — U3 decouple",
    ),
    Component(
        refdes="C9", value="100nF",
        footprint="0402", lcsc="C1525",
        x=30.0, y=11.5, rotation=0, populate=False,
        comment="CL05B104KO5NNNC", description="MLCC 100nF 0402 — U4 decouple (DNP)",
    ),
    Component(
        refdes="C30", value="100nF",
        footprint="0402", lcsc="C1525",
        x=37.0, y=15.5, rotation=0, populate=False,
        comment="CL05B104KO5NNNC", description="MLCC 100nF 0402 — DNP RC filter",
    ),

    # ---- pull-ups / pull-downs / current limit ----------------------------
    Component(
        refdes="R10", value="5.1k",
        footprint="0402", lcsc="C25905",
        x=27.0, y=8.0, rotation=0,
        comment="0402WGF5101TCE", description="Thick-film 5.1k 1% 0402 — USB CC1 PD",
    ),
    Component(
        refdes="R11", value="5.1k",
        footprint="0402", lcsc="C25905",
        x=33.0, y=8.0, rotation=0,
        comment="0402WGF5101TCE", description="Thick-film 5.1k 1% 0402 — USB CC2 PD",
    ),
    Component(
        refdes="R20", value="1k",
        footprint="0402", lcsc="C11702",
        x=40.0, y=30.5, rotation=0,
        comment="0402WGF1001TCE", description="Thick-film 1k 1% 0402 — D2 limit",
    ),
    Component(
        refdes="R21", value="1k",
        footprint="0402", lcsc="C11702",
        x=44.0, y=30.5, rotation=0,
        comment="0402WGF1001TCE", description="Thick-film 1k 1% 0402 — D3 limit",
    ),
    Component(
        refdes="R30", value="10k",
        footprint="0402", lcsc="C25744",
        x=54.0, y=22.0, rotation=90,
        comment="0402WGF1002TCE", description="Thick-film 10k 1% 0402 — ADC pull-down",
    ),
    Component(
        refdes="R31", value="10k",
        footprint="0402", lcsc="C25744",
        x=35.0, y=15.5, rotation=0, populate=False,
        comment="0402WGF1002TCE", description="Thick-film 10k 1% 0402 — DNP RC filter",
    ),
    Component(
        refdes="R40", value="10k",
        footprint="0402", lcsc="C25744",
        x=49.0, y=37.5, rotation=0,
        comment="0402WGF1002TCE", description="Thick-film 10k 1% 0402 — BOOT pull-up",
    ),
    Component(
        refdes="R41", value="10k",
        footprint="0402", lcsc="C25744",
        x=57.0, y=22.0, rotation=0,
        comment="0402WGF1002TCE", description="Thick-film 10k 1% 0402 — RESET pull-up",
    ),

    # ---- solder jumper -----------------------------------------------------
    Component(
        refdes="SJ1", value="jumper",
        footprint="SOLDER_JUMPER_2P", lcsc="",
        x=40.5, y=15.5, rotation=0, populate=False,
        comment="solder jumper", description="2-pad solder jumper — ADS1115 alt path enable",
    ),
]


def by_refdes() -> dict[str, Component]:
    return {c.refdes: c for c in COMPONENTS}
