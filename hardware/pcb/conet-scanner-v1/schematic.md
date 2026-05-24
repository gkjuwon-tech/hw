# Conet Tactile — Scanner v1 schematic (Markdown rendering)

This is the schematic of the prototype scanner board, expressed as a markdown netlist so it is reviewable in pull requests without an EDA tool. The canonical artwork lives in the KiCad project (separate PR with the Gerbers / BOM / CPL).

Net naming convention: `+5V`, `+3V3`, `GND`, signal nets in UPPER_SNAKE.

---

## Block diagram

```
                ┌──────────────────────────────────────────────────────────┐
                │                ESP32-S3-WROOM-1 (U1)                      │
                │                                                            │
USB-C  ─D±,VBUS─┤ USB native (GPIO 19/20)                                  │
                │                                                            │
                │ GPIO 4..7  ─────────→  ROW_S0..S3  ─→ U2 (CD74HC4067)    │
                │ GPIO 15..18 ────────→  COL_S0..S3  ─→ U3 (CD74HC4067)    │
                │ GPIO 1 (ADC1_CH0) ←────────── ADC_IN (= U2 SIG)          │
                │ GPIO 8/9 (I²C) ⇆ U4 ADS1115 (alternative 16-bit path)   │
                │ GPIO 48 ─────────────→ LED_ACT (D3, red)                 │
                │ GPIO 0 ←─── BOOT (SW1)                                   │
                │ EN     ←─── RESET (SW2)                                  │
                └──────────────────────────────────────────────────────────┘

         +5V ──→ TLV1117LV33 (U5) ──→ +3V3 (to U1/U2/U3/U4 + LEDs)

         J1 (16-pin FFC, ROW)  ─→ U2 Y0..Y15
         J2 (16-pin FFC, COL)  ─→ U3 Y0..Y15
                                  U2 SIG  ──→ ADC_IN
                                  U3 SIG  ──→ GND via 10 kΩ pull-down (R30)
```

---

## Net list

### Power

| Net | Source | Sinks |
|-----|--------|-------|
| `+5V` | J3 USB-C VBUS (after F1 PTC + D1 USBLC6 ESD) | U5 IN, C1 (47 µF bulk) |
| `+3V3` | U5 OUT | U1 (4×0.1 µF + 10 µF), U2 (0.1 µF), U3 (0.1 µF), U4 (0.1 µF), D2 anode via R20 |
| `GND` | J3 USB-C GND | global return |

### USB

| Net | Endpoints | Notes |
|-----|-----------|-------|
| `USB_DM` | J3.A7/B7 ⇆ U1.GPIO19 | through D1.IO1 ESD clamp |
| `USB_DP` | J3.A6/B6 ⇆ U1.GPIO20 | through D1.IO2 ESD clamp |
| `USB_CC1` | J3.A5 → R10 (5.1 kΩ) → GND | CC pull-down (sink role) |
| `USB_CC2` | J3.B5 → R11 (5.1 kΩ) → GND | CC pull-down (sink role) |

### Row mux (U2, CD74HC4067)

| Net | Endpoint(s) |
|-----|-------------|
| `ROW_S0` | U1.GPIO4 → U2.S0 |
| `ROW_S1` | U1.GPIO5 → U2.S1 |
| `ROW_S2` | U1.GPIO6 → U2.S2 |
| `ROW_S3` | U1.GPIO7 → U2.S3 |
| `U2 EN`  | tied to GND |
| `U2 VCC` | `+3V3` |
| `U2 VEE` | `GND` |
| `U2 Y0..Y15` | J1 pin 1..16 (mesh ROW conductors 0..15) |
| `U2 SIG` | `ADC_IN` (= ESP32 GPIO 1) and optionally U4.AIN0 (DNP solder jumper SJ1) |

### Column mux (U3, CD74HC4067)

| Net | Endpoint(s) |
|-----|-------------|
| `COL_S0` | U1.GPIO15 → U3.S0 |
| `COL_S1` | U1.GPIO16 → U3.S1 |
| `COL_S2` | U1.GPIO17 → U3.S2 |
| `COL_S3` | U1.GPIO18 → U3.S3 |
| `U3 EN`  | tied to GND |
| `U3 VCC` | `+3V3` |
| `U3 VEE` | `GND` |
| `U3 Y0..Y15` | J2 pin 1..16 (mesh COL conductors 0..15) |
| `U3 SIG` | `GND` through R30 (10 kΩ pull-down) |

### ADC sampling path

```
ROW(r) ─[Velostat]─ COL(c) ─ U3.Y(c) ─ U3 SIG ─ R30 (10 kΩ) ─ GND
                          └─→ when U3.S = c, the (r,c) cell is the only
                              non-isolated column path.
U2.Y(r) ─ U2 SIG ─→ ADC_IN ─→ U1.GPIO1 (ADC1_CH0)
                  └ DNP R31 (10 kΩ) ─ DNP C30 (100 nF) ─ GND   ; RC filter bodge pads
```

The cell at (r, c) is the resistance `R_cell(r,c)` between U2.Y(r) and U3.Y(c) through the Velostat layer. When U2 selects row r and U3 selects column c, the ADC sees a divider:

```
V_ADC = +3V3 × ( R30 / (R30 + R_cell(r,c) + R_mux_on × 2) )
                                ^^^^^^^^^^^^   ^^^^^^^^^^^^
                                pressure ↓     ~80 Ω each MUX
```

Higher pressure → lower `R_cell` → higher `V_ADC` → higher ADC reading.

### Alternative 16-bit ADC path (DNP by default)

| Net | Endpoint |
|-----|----------|
| `I2C_SDA` | U1.GPIO8 ⇆ U4.SDA |
| `I2C_SCL` | U1.GPIO9 ⇆ U4.SCL |
| `U4.AIN0` | jumper SJ1 → U2 SIG |
| `U4.ADDR` | GND (I²C addr 0x48) |
| `U4.VDD/VSS` | `+3V3` / `GND` |

`SJ1` is a solder-jumper that diverts U2 SIG from ADC_IN to U4.AIN0 when bridged. Default: open (use ESP32 internal ADC).

### LEDs

| Net | Endpoint |
|-----|----------|
| `+3V3` → R20 (1 kΩ) → D2 (green 0603) → GND | power-on indicator |
| `U1.GPIO48` → R21 (1 kΩ) → D3 (red 0603) → GND | firmware activity blink |

### Buttons

| Net | Endpoint |
|-----|----------|
| `U1.GPIO0` → SW1 (BOOT) → GND, also R40 (10 kΩ) pull-up to `+3V3` | enter download mode when pressed |
| `U1.EN`    → SW2 (RESET) → GND, also R41 (10 kΩ) pull-up to `+3V3` | reset chip |

### Mesh interface

| Connector | Pin | Net |
|-----------|----:|-----|
| J1 (ROW, FFC 16-pin 1.0 mm) | 1..16 | U2.Y0..Y15 |
| J2 (COL, FFC 16-pin 1.0 mm) | 1..16 | U3.Y0..Y15 |

Both J1 and J2 are FH12-16S-1SH (Hirose, top contact). Pin 1 marker on PCB silkscreen is the **outer** edge.

---

## Decoupling table

| IC | Caps |
|----|------|
| U1 ESP32-S3 | 4× 100 nF + 1× 10 µF on `+3V3` rail, located ≤5 mm from module pads |
| U2 CD74HC4067 (ROW) | 100 nF + 10 µF on `+3V3` |
| U3 CD74HC4067 (COL) | 100 nF + 10 µF on `+3V3` |
| U4 ADS1115 | 100 nF + 10 µF on `+3V3` |
| U5 TLV1117LV33 | 10 µF input + 22 µF output |
| Bulk | 47 µF on `+5V` rail near USB-C |

---

## DNP / bodge pads

To leave room for in-the-field tuning without spinning a v2:

- **SJ1** — solder jumper to route U2 SIG into ADS1115 instead of ESP32 ADC.
- **R31 / C30** — RC low-pass filter footprint on ADC_IN line. Populate if mesh runs >1 m and we see noise above 1 % of full-scale.
- **TP1..TP4** — test points on `+5V`, `+3V3`, `ADC_IN`, `U3 SIG`. For debugging with a scope.
- **J4** — 4-pin 2.54 mm header for external UART (GPIO 43/44). Useful if native USB ever fights us during bring-up.

---

## Open questions tracked for v2

1. Replace ESP32 internal ADC with always-on ADS1115 once we measure noise in v1 in the field.
2. Consider INA826 instrumentation amp on the row side for very high-impedance mesh designs (>1 MΩ baseline). Adds $4 BOM.
3. Move from FH12 FFC to a Hirose DF40 board-to-board connector for the mesh interface in v2 — cuts assembly time and reduces failure points.
4. Add a small e-fuse (TPS25200 or similar) on the +5V input to survive surges from the customer-side USB-C source.
