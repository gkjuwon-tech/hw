// Conet Tactile — host-side scan loop simulator.
//
// This binary is the "software mode" core of the Wokwi test harness. It
// reads a 16x16 grid of raw 12-bit ADC samples from stdin (uint16 little
// endian, 512 bytes total per frame) and writes the corresponding wire-
// format frame (20-byte header + 256-byte payload = 276 bytes) to stdout.
//
// Crucially, the per-sample shaping (`compress_sample`) and CRC
// (`crc16_ccitt`) come straight out of `scanner_frame.h` — the same header
// the shipping ESP32-S3 `.ino` pulls in. So the bytes this binary emits
// are byte-identical to what the silicon would emit if it sampled the
// same ADC matrix. The MCU-side delay/MUX-select machinery is intentionally
// out of scope here; that's what Wokwi mode is for.
//
// CLI:
//   scan_one_frame --seq <uint32> --timestamp <uint32>
//
// stdin: 512 bytes (16x16 uint16 LE ADC samples, row-major)
// stdout: 276 bytes (header + payload)
//
// Exit status: 0 on success, 2 on bad arguments, 3 on short stdin read.

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unistd.h>

#include "../../scanner_frame.h"

using conet_scanner::compress_sample;
using conet_scanner::frame_header_t;
using conet_scanner::kCols;
using conet_scanner::kRows;
using conet_scanner::make_frame_header;

namespace {

void usage_and_die() {
  std::fprintf(stderr,
               "usage: scan_one_frame --seq <u32> --timestamp <u32>\n"
               "       (stdin: %zu bytes of uint16-LE ADC samples)\n",
               static_cast<size_t>(kRows * kCols * sizeof(uint16_t)));
  std::exit(2);
}

uint32_t parse_u32(const char* s) {
  char* end = nullptr;
  unsigned long long v = std::strtoull(s, &end, 10);
  if (end == s || *end != '\0' || v > 0xFFFFFFFFULL) usage_and_die();
  return static_cast<uint32_t>(v);
}

}  // namespace

int main(int argc, char** argv) {
  uint32_t seq = 0;
  uint32_t timestamp_us = 0;
  bool seq_set = false;
  bool ts_set = false;

  for (int i = 1; i < argc; ++i) {
    const std::string a = argv[i];
    if ((a == "--seq" || a == "-s") && i + 1 < argc) {
      seq = parse_u32(argv[++i]);
      seq_set = true;
    } else if ((a == "--timestamp" || a == "-t") && i + 1 < argc) {
      timestamp_us = parse_u32(argv[++i]);
      ts_set = true;
    } else {
      usage_and_die();
    }
  }
  if (!seq_set || !ts_set) usage_and_die();

  // Read the ADC matrix.
  constexpr size_t kAdcBytes = static_cast<size_t>(kRows) * kCols * sizeof(uint16_t);
  uint16_t adc[kRows * kCols];
  uint8_t* p = reinterpret_cast<uint8_t*>(adc);
  size_t got = 0;
  while (got < kAdcBytes) {
    ssize_t n = ::read(STDIN_FILENO, p + got, kAdcBytes - got);
    if (n < 0) {
      if (errno == EINTR) continue;
      std::fprintf(stderr, "scan_one_frame: stdin read error\n");
      return 3;
    }
    if (n == 0) {
      std::fprintf(stderr,
                   "scan_one_frame: short stdin read (%zu/%zu bytes)\n",
                   got, kAdcBytes);
      return 3;
    }
    got += static_cast<size_t>(n);
  }

  // Run the per-cell shaping. This mirrors the body of `loop()` in
  // tactile_scanner_esp32.ino, minus the MUX-select / delayMicroseconds /
  // analogRead calls that are pure side-effects on silicon.
  uint8_t payload[kRows * kCols];
  for (uint16_t r = 0; r < kRows; ++r) {
    for (uint16_t c = 0; c < kCols; ++c) {
      payload[r * kCols + c] = compress_sample(adc[r * kCols + c]);
    }
  }

  const frame_header_t hdr =
      make_frame_header(seq, timestamp_us, payload, sizeof(payload));

  if (std::fwrite(&hdr, sizeof(hdr), 1, stdout) != 1) return 4;
  if (std::fwrite(payload, sizeof(payload), 1, stdout) != 1) return 4;
  std::fflush(stdout);
  return 0;
}
