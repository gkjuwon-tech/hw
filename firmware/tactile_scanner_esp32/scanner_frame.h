// Conet Tactile — wire protocol + pure sample-shaping logic.
//
// Single header pulled in by both:
//   - tactile_scanner_esp32.ino   (the shipping ESP32-S3 sketch)
//   - wokwi/host_sim/*            (the host-side test harness)
//
// Nothing in here touches Arduino APIs (pinMode/Serial/analogRead/...), so it
// compiles cleanly on any C++17 host toolchain. Keeping the byte-format and
// the sample-shaping math in one place is the only way the host harness can
// honestly claim to exercise the same code that runs on silicon.
//
// License: Proprietary. Conet Studio, 2026.

#ifndef CONET_SCANNER_FRAME_H
#define CONET_SCANNER_FRAME_H

#include <stddef.h>
#include <stdint.h>

// ─── Geometry ────────────────────────────────────────────────────────────────
namespace conet_scanner {

constexpr uint16_t kRows = 16;
constexpr uint16_t kCols = 16;
constexpr uint32_t kScanHz = 200;
constexpr uint32_t kScanPeriodUs = 1000000UL / kScanHz;

constexpr uint16_t kAdcMax = 4095;   // 12-bit ADC full-scale
constexpr uint16_t kAdcDead = 32;    // noise floor subtracted before compression

// ─── Wire format ─────────────────────────────────────────────────────────────
constexpr uint32_t kFrameMagic = 0x434F4E54UL;  // 'CONT'

#pragma pack(push, 1)
struct frame_header_t {
  uint32_t magic;
  uint16_t rows;
  uint16_t cols;
  uint32_t seq;
  uint32_t timestamp_us;
  uint16_t crc;
  uint16_t _pad;
};
#pragma pack(pop)

static_assert(sizeof(frame_header_t) == 20, "frame_header_t must be packed to 20 bytes");

// ─── CRC16-CCITT (poly 0x1021, init 0xFFFF, no reflect, no xor-out) ──────────
// Bit-identical to the on-device implementation; the host harness verifies
// well-known test vectors so any future "optimisation" can't silently drift.
inline uint16_t crc16_ccitt(const uint8_t* data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t b = 0; b < 8; ++b) {
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021)
                           : static_cast<uint16_t>(crc << 1);
    }
  }
  return crc;
}

}  // namespace conet_scanner

// ─── Sample shaping ──────────────────────────────────────────────────────────
// `compress_sample` is the per-cell ADC → uint8 shaper that lives in the hot
// path of the scan loop. It is templated on a "math" provider so the host
// harness can swap in <cmath> while the Arduino build keeps the AVR/ESP libm
// routes. The default specialisation (the one the firmware uses) pulls in
// <cmath> as well — ESP32 ships logf() with the standard libc.
#include <math.h>

namespace conet_scanner {

inline uint8_t compress_sample(uint16_t raw) {
  if (raw <= kAdcDead) return 0;
  const float v = static_cast<float>(raw - kAdcDead) /
                  static_cast<float>(kAdcMax - kAdcDead);
  const float shaped = v < 0.66f
      ? v
      : 0.66f + 0.34f * logf(1.0f + (v - 0.66f) * 4.0f) /
                       logf(1.0f + 4.0f * 0.34f);
  const int v8 = static_cast<int>(shaped * 255.0f + 0.5f);
  if (v8 < 0) return 0;
  if (v8 > 255) return 255;
  return static_cast<uint8_t>(v8);
}

// Pack a frame header for the given payload. The CRC is computed over the
// payload only (not over the header). Timestamp is passed in from the caller
// because the on-device source is `micros()` and the host harness uses a
// deterministic counter — both produce the same byte layout.
inline frame_header_t make_frame_header(uint32_t seq,
                                        uint32_t timestamp_us,
                                        const uint8_t* payload,
                                        size_t payload_len) {
  frame_header_t hdr;
  hdr.magic = kFrameMagic;
  hdr.rows = kRows;
  hdr.cols = kCols;
  hdr.seq = seq;
  hdr.timestamp_us = timestamp_us;
  hdr.crc = crc16_ccitt(payload, payload_len);
  hdr._pad = 0;
  return hdr;
}

}  // namespace conet_scanner

#endif  // CONET_SCANNER_FRAME_H
