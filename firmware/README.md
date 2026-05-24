# Tactile Mesh — reference scanner firmware

This directory contains the reference firmware for the **Tactile Scanner board**
that drives the row/column piezo-resistive mesh and streams frames to the
**Tactile Edge** appliance over USB-CDC.

## Targets

| Board | MCU | Status |
|-------|-----|--------|
| Conet TS-G4 (production) | STM32G474 | reference port (this repo's `tactile_scanner_stm32/`) — coming with the v0.3 PCB |
| Conet TS-Devkit | ESP32-S3-WROOM-1 | development sketch in `tactile_scanner_esp32/` |

This repository ships the ESP32-S3 sketch only; the STM32G4 port is delivered
with the production carrier board.

## Architecture

```
┌────────────────────┐    SPI / parallel    ┌──────────────────┐
│  Tactile Mesh      │  ───────────────►   │  Scanner board   │
│  (piezo-resistive  │   row drive          │  74HC4067 × 2    │
│   textile matrix)  │  ◄───────────────   │  INA826 / ADC    │
└────────────────────┘    column read       └────────┬─────────┘
                                                     │ USB-CDC
                                                     ▼
                                            ┌──────────────────┐
                                            │  Tactile Edge    │
                                            │  Jetson Orin     │
                                            │  Nano 8 GB       │
                                            └──────────────────┘
```

## Frame format on the wire

The scanner sends one frame per scan period as a binary record over USB-CDC:

```
struct frame_t {
  uint32_t magic;        // 0x434F4E54  ('CONT')
  uint16_t rows;
  uint16_t cols;
  uint32_t seq;          // monotonic counter
  uint32_t timestamp_us; // µs since boot
  uint16_t crc;          // CRC-16/CCITT over data
  uint16_t _pad;
  uint8_t  data[rows*cols]; // row-major, 8 bits per cell
};
```

The Edge re-emits these as the `/v1/lines/{line_id}/frames` and
`/v1/lines/{line_id}/inspect` payloads documented in the backend.

## ESP32-S3 development sketch

`tactile_scanner_esp32/tactile_scanner_esp32.ino` is an Arduino-IDE-compatible
sketch that:

- multiplexes two 74HC4067 MUXes for a 16×16 grid;
- samples each cell through an INA826 differential amp;
- packs the frame to 8 bits with simple log compression;
- sends it over USB-CDC at the configured `SCAN_HZ`.

Build with the Arduino IDE (Tools → Board → ESP32S3 Dev Module) or
arduino-cli. No external dependencies.
