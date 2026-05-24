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
#   - CDCOnBoot=default + USBMode=default keeps Serial bound to UART0
#     (GPIO 43/44) which is what wokwi-cli's --serial-log-file captures.
#     The production board uses USB-CDC (the firmware code is identical;
#     only the build option changes the routing of `Serial`).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKETCH_DIR="$(cd "${HERE}/.." && pwd)"
BUILD_DIR="${HERE}/.build"

mkdir -p "${BUILD_DIR}"

arduino-cli compile \
  --fqbn "esp32:esp32:esp32s3:CDCOnBoot=default,USBMode=default" \
  --output-dir "${BUILD_DIR}" \
  "${SKETCH_DIR}"

cp "${BUILD_DIR}/tactile_scanner_esp32.ino.elf"        "${HERE}/firmware.elf"
cp "${BUILD_DIR}/tactile_scanner_esp32.ino.merged.bin" "${HERE}/firmware.bin"

echo "firmware.elf and firmware.bin written to ${HERE}"
