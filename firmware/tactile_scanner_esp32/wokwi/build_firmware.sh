#!/usr/bin/env bash
# Build the Tactile Scanner firmware for Wokwi simulation.
#
# Produces firmware.elf and firmware.bin next to this script, ready for
# `wokwi-cli` to pick up via wokwi.toml.
#
# Requirements:
#   - arduino-cli (>= 1.5)
#   - esp32 board package installed
#       arduino-cli core install esp32:esp32
#
# Notes on FQBN flags:
#   - CDCOnBoot=cdc + USBMode=default routes `Serial` to USB-CDC over the
#     ESP32-S3 native USB-OTG peripheral (GPIO 19/20). This is the SAME
#     routing the EVT board uses in production: the board's USB-C jack J3
#     goes through D1 (USBLC6-2SC6Y ESD clamp) directly to GPIO 19/20 — there
#     is no CP210x / CH340 UART bridge on the board. So building with
#     CDCOnBoot=cdc is the production-correct flag, AND it matches what
#     Wokwi's `board-esp32-s3-devkitc-1` emulates over its USB jack.
#
#     Building with the (Arduino-default) CDCOnBoot=default would route
#     `Serial` to UART0 (GPIO 43/44) — that's the J4 4-pin debug header
#     ("useful if native USB ever fights us during bring-up"), NOT the
#     primary USB-C jack. The shipping image therefore needs CDCOnBoot=cdc;
#     a UART0 build is only useful for hardware bring-up via J4.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKETCH_DIR="$(cd "${HERE}/.." && pwd)"
BUILD_DIR="${HERE}/.build"

mkdir -p "${BUILD_DIR}"

# CDCOnBoot=cdc is the production-correct routing (see header comment above).
# Allow override via $CDC_ON_BOOT for hardware bring-up via the J4 UART header.
CDC_ON_BOOT="${CDC_ON_BOOT:-cdc}"

arduino-cli compile \
  --fqbn "esp32:esp32:esp32s3:CDCOnBoot=${CDC_ON_BOOT},USBMode=default" \
  --output-dir "${BUILD_DIR}" \
  "${SKETCH_DIR}"

# wokwi-cli supports two firmware shapes:
#   1. A single merged flash image at `firmware = "...bin"`.
#   2. A `flasher_args.json` describing per-offset binaries (the ESP-IDF
#      convention; arduino-cli doesn't produce one, so we synthesize it).
# Shape #2 has been more reliable in practice on `board-esp32-s3-devkitc-1`,
# so this is what we ship and what wokwi.toml points at.
FLASH_DIR="${HERE}/build"
mkdir -p "${FLASH_DIR}"
cp "${BUILD_DIR}/tactile_scanner_esp32.ino.bootloader.bin" "${FLASH_DIR}/bootloader.bin"
cp "${BUILD_DIR}/tactile_scanner_esp32.ino.partitions.bin" "${FLASH_DIR}/partitions.bin"
cp "${BUILD_DIR}/tactile_scanner_esp32.ino.bin"            "${FLASH_DIR}/app.bin"
cp "${BUILD_DIR}/tactile_scanner_esp32.ino.elf"            "${FLASH_DIR}/app.elf"
cat > "${FLASH_DIR}/flasher_args.json" <<'JSON'
{
  "flash_settings": { "flash_mode": "qio", "flash_size": "4MB", "flash_freq": "80m" },
  "flash_files": {
    "0x0":     "bootloader.bin",
    "0x8000":  "partitions.bin",
    "0x10000": "app.bin"
  }
}
JSON

# Convenience legacy aliases — keep the single merged image around in case
# somebody points wokwi.toml at a flat `firmware.bin` instead of build/.
cp "${BUILD_DIR}/tactile_scanner_esp32.ino.elf"        "${HERE}/firmware.elf"
cp "${BUILD_DIR}/tactile_scanner_esp32.ino.merged.bin" "${HERE}/firmware.bin"

echo "build/{bootloader,partitions,app}.bin + flasher_args.json written to ${FLASH_DIR}"
echo "firmware.elf / firmware.bin (merged) also written to ${HERE} for compatibility"
