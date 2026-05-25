# Bill of Materials — Conet Tactile (prototype + pilot)

All prices are **prototype quantities (1–10 units)** in USD. Pilot quantities (100+) typically drop 30–55 %. Distributors are listed only as representative examples; final sourcing may differ.

---

## 1. Tactile Mesh — sensor sheet (one 200 mm × 500 mm panel)

| # | Part | Spec | Vendor (example) | Qty | Unit | Notes |
|---|------|------|------------------|-----|------|-------|
| 1 | Velostat / Linqstat sheet | 0.1 mm × 280 × 280 mm, 30 kΩ·cm | Adafruit #1361 / Digi-Key | 1 | $4.95 | Prototype-grade pressure-sensitive film. Production switches to Eeonyx EeonTex LTT-SLPA. |
| 2 | Eeonyx EeonTex LTT-SLPA-2k | knit, 2 kΩ/sq, 1 m × 1 m | Eeonyx direct / Less EMF | 0.1 | $32.00 | Production-grade alternative. Order full meter, cut down. |
| 3 | Conductive ripstop fabric | silver-plated nylon, 50 mΩ/sq, 1 m² | Less EMF #A1212 | 0.2 | $14.00 | For row/column buses. |
| 4 | Conductive thread | 234/34 dtex 4-ply, silver | Adafruit #641 | 1 | $6.95 | Bus tie-offs. |
| 5 | Polyimide tape (Kapton) | 25 µm × 25 mm × 33 m | Digi-Key 1928-1004-ND | 0.1 | $12.00 | Inter-layer isolation. |
| 6 | TPU laminating film, food-grade | 0.05 mm, 300 mm wide | TPU Films Ltd | 0.5 | $9.00 | Top + bottom cover. |
| 7 | Double-sided industrial adhesive | 3M VHB 5952, 25 mm × 33 m | 3M / Grainger | 0.05 | $24.00 | Belt attachment. |
| 8 | FFC ribbon, 32-pin, 0.5 mm pitch | 200 mm shielded | Würth 687632200002 | 2 | $3.40 | Mesh → scanner board. |

**Mesh sub-total (prototype):** ≈ **$33** materials per 200 × 500 mm panel.
**At 100-unit pilot quantities:** ≈ **$14** per panel. Sell at $480 → ~97 % gross.

---

## 2. Scanner board (one per mesh panel)

| # | Part | Spec | Vendor (example) | Qty | Unit | Notes |
|---|------|------|------------------|-----|------|-------|
| 1 | STM32G474RET6 | 170 MHz Cortex-M4, 512 KB flash | Digi-Key 497-STM32G474RET6 | 1 | $7.50 | Main MCU. |
| 2 | 74HC4067D (16-ch analog mux) | 16:1, ±5 V | Digi-Key 568-1525-1-ND | 4 | $0.60 | 2× row mux + 2× column mux for 32×32. |
| 3 | INA826 (instrumentation amp) | rail-to-rail, 1 µV/°C drift | Digi-Key 296-37999-1-ND | 2 | $4.20 | Front-end gain. |
| 4 | ADS1115 (16-bit ADC, I²C) | 860 SPS, PGA | Digi-Key 296-24536-1-ND | 1 | $5.40 | Backup ADC; STM32 internal ADC is primary. |
| 5 | TLV70033 LDO (3.3 V) | 200 mA, low noise | Digi-Key 296-25920-1-ND | 1 | $0.45 | Analog rail. |
| 6 | Common-mode choke | 100 Ω @ 100 MHz | Würth 744232101 | 2 | $0.85 | EMC for ribbon. |
| 7 | TVS diode array | SP3010-04UTG | Digi-Key 944-1052-1-ND | 2 | $0.55 | ESD on ribbon pins. |
| 8 | RJ45 jack with magnetics | for PoE-PD path | Würth 7499010121A | 1 | $3.20 | Network in (optional). |
| 9 | USB-C connector + ESD | USB 2.0, 5 V/2 A | Würth 632723300011 | 1 | $1.10 | Primary uplink to Tactile Edge. |
| 10 | PCB | 4-layer, 80 × 60 mm, ENIG, HASL-free | JLCPCB / PCBWay | 1 | $6.00 | At quantity 10. |
| 11 | Assembly (SMT) | turnkey, both sides | JLCPCB SMT | 1 | $14.00 | At quantity 10. |

**Scanner board sub-total (prototype):** ≈ **$50** loaded BOM per board.
**At 1k quantities:** ≈ **$22** per board.

---

## 3. Tactile Edge — inference appliance

| # | Part | Spec | Vendor (example) | Qty | Unit | Notes |
|---|------|------|------------------|-----|------|-------|
| 1 | NVIDIA Jetson Orin Nano 8 GB Developer Kit | 40 TOPS, 7–15 W | NVIDIA / Arrow | 1 | $499.00 | Production switches to bare module + carrier ($249 + $80). |
| 2 | 256 GB NVMe M.2 SSD | industrial-temp variant | Innodisk / Apacer | 1 | $48.00 | Local frame buffer. |
| 3 | DIN-rail enclosure | IP54, 160 × 90 × 60 mm | Phoenix Contact / Hammond | 1 | $42.00 | |
| 4 | PoE+ PD module | IEEE 802.3at, 25 W | Silvertel Ag9805M | 1 | $24.00 | Single-cable install. |
| 5 | M12 X-coded Ethernet jack | industrial | Phoenix Contact 1424246 | 1 | $14.00 | |
| 6 | M12 power + I/O combo jack | 8-pin | TE 1838244-2 | 1 | $12.00 | For PLC integration. |
| 7 | Solid-state relay output | 24 V DC, 1 A, opto-isolated | Omron G3VM-61D1 | 2 | $2.40 | Reject actuator drive. |
| 8 | Status LED + photopipe | tri-color | Bivar / Würth | 1 | $1.80 | |
| 9 | Mounting magnets | rare-earth, 25 mm | K&J Magnetics D8X0 | 4 | $1.50 | Magnetic-base mount option. |
| 10 | Carrier PCB | 4-layer, 100 × 80 mm | JLCPCB | 1 | $12.00 | Connects Orin SOM to I/O. |
| 11 | 7" HDMI capacitive touch display | 1024 × 600 IPS, USB touch | Waveshare 7inch HDMI LCD (H) | 1 | $65.00 | **Integrated kiosk display.** No more .exe / .dmg — operators interact with this directly on the line. 10.1" 1280×800 option is $105 for far-from-line use. |
| 12 | HDMI Micro-to-Standard cable | 30 cm | generic | 1 | $5.00 | Jetson HDMI is full-size; most 7" panels use micro. Match the panel SKU. |
| 13 | Display power adapter | 5 V 3 A USB-A, with micro-B cable | generic | 1 | $9.00 | Powers panel backlight. Sharing Jetson USB causes brightness flicker. |
| 14 | VESA-75 industrial mount arm | with line-side clamp | Ergotron / generic | 1 | $24.00 | First-unit demo can use a desk stand; production lines need the arm. |

**Edge sub-total (prototype):** ≈ **$763** loaded BOM (display + arm bundled — every appliance ships with a kiosk display).
**At 500 quantities with bare Orin Nano module + 7" panel:** ≈ **$490** loaded BOM. Sell at **$1,490** list, software bundled — there is no separate desktop-app SKU. The recurring **Edge Care** plan covers fleet baseline sync, OTA updates, and replacement mesh rolls.

---

## 4. Installation kit (ships in each first-deployment box)

| # | Part | Spec | Vendor | Qty | Unit | Notes |
|---|------|------|--------|-----|------|-------|
| 1 | Rotary cutter | 45 mm, ergonomic | Olfa RTY-2/G | 1 | $14.00 | For trimming mesh to belt width. |
| 2 | Self-healing cutting mat | A3, 3 mm | Olfa CM-A3 | 1 | $22.00 | |
| 3 | Steel rule | 600 mm, anti-slip | Shinwa | 1 | $11.00 | |
| 4 | Mesh-end termination clips | crimp + fold, 32-position | custom | 4 | $0.80 | For row/column bus tie-off after cutting. |
| 5 | Calibration alignment jig | 3D-printed PA12, 200 × 200 mm | in-house SLS | 1 | $8.00 | Holds the five known-good samples at known positions during calibration. |
| 6 | Quick-start card + QR | printed, glossy | local print | 1 | $1.20 | One QR launches the calibration flow. |

**Install kit sub-total:** ≈ **$57.** Ships once per customer site, not per line.

---

## 5. Per-line all-in (prototype)

| Component | Cost |
|-----------|------|
| Tactile Mesh (200 × 500 mm) | $33 |
| Scanner board | $50 |
| Tactile Edge | $660 |
| Install kit (amortized over ~10 lines/site) | $6 |
| **Total hardware** | **~$749** |

Hardware loaded to first pilot customer at break-even; revenue comes from **Tactile Cloud subscription** ($1,200 / line / month).

## 6. Lead-time / sourcing notes

- Eeonyx EeonTex must be ordered ≥ 6 weeks ahead from US distributor; Velostat is in-stock at Adafruit and Digi-Key for prototypes.
- 74HC4067 has had recurring shortages; second-source: ADG1606 (Analog Devices, lower R-on).
- Jetson Orin Nano allocations: maintain a 90-day stock buffer. Backup compute path: Raspberry Pi 5 + Hailo-8L M.2 (15 TOPS, ~$220 total).
- All conductive textiles ship as ITAR-free / EAR99 to KR / JP.
