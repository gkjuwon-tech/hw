// Conet Tactile — reference scanner sketch (ESP32-S3, 16x16 grid).
//
// Drives two 74HC4067 multiplexers (rows and columns) and samples one
// piezo-resistive cell at a time through an INA826 differential amplifier
// connected to ADC1. Frames are emitted over USB-CDC at SCAN_HZ.
//
// This is a reference for the development kit. Production boards use STM32G4
// with parallel mux drive and a dedicated 24-bit delta-sigma ADC; the wire
// protocol is identical.
//
// The wire-format / CRC / sample-shaping logic lives in `scanner_frame.h`
// so the host-side Wokwi test harness can exercise the exact same code that
// runs on silicon (see firmware/tactile_scanner_esp32/wokwi/host_sim/).
//
// License: Proprietary. Conet Studio, 2026.

#include <Arduino.h>

#include "scanner_frame.h"

using conet_scanner::compress_sample;
using conet_scanner::frame_header_t;
using conet_scanner::kCols;
using conet_scanner::kRows;
using conet_scanner::kScanPeriodUs;
using conet_scanner::make_frame_header;

// ─── Pinout ──────────────────────────────────────────────────────────────────
constexpr uint8_t ROW_S0 = 4;
constexpr uint8_t ROW_S1 = 5;
constexpr uint8_t ROW_S2 = 6;
constexpr uint8_t ROW_S3 = 7;

constexpr uint8_t COL_S0 = 15;
constexpr uint8_t COL_S1 = 16;
constexpr uint8_t COL_S2 = 17;
constexpr uint8_t COL_S3 = 18;

constexpr uint8_t ADC_PIN = 1;  // GPIO1 == ADC1_CH0

// ─── Frame buffer ────────────────────────────────────────────────────────────
static uint8_t frame_buf[kRows * kCols];
static uint32_t seq_counter = 0;

// ─── Helpers ─────────────────────────────────────────────────────────────────
static inline void selectMux(uint8_t value, uint8_t s0, uint8_t s1, uint8_t s2, uint8_t s3) {
  digitalWrite(s0, value & 0x01);
  digitalWrite(s1, (value >> 1) & 0x01);
  digitalWrite(s2, (value >> 2) & 0x01);
  digitalWrite(s3, (value >> 3) & 0x01);
}

// ─── Setup / Loop ────────────────────────────────────────────────────────────
void setup() {
  for (uint8_t pin : {ROW_S0, ROW_S1, ROW_S2, ROW_S3, COL_S0, COL_S1, COL_S2, COL_S3}) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  analogReadResolution(12);
  analogSetPinAttenuation(ADC_PIN, ADC_11db);

  Serial.begin(2000000);
  while (!Serial && millis() < 2000) { /* wait for host */ }
}

void loop() {
  const uint32_t scan_start_us = micros();

  for (uint16_t r = 0; r < kRows; ++r) {
    selectMux(static_cast<uint8_t>(r), ROW_S0, ROW_S1, ROW_S2, ROW_S3);
    delayMicroseconds(2);
    for (uint16_t c = 0; c < kCols; ++c) {
      selectMux(static_cast<uint8_t>(c), COL_S0, COL_S1, COL_S2, COL_S3);
      delayMicroseconds(2);
      const uint16_t raw = analogRead(ADC_PIN);
      frame_buf[r * kCols + c] = compress_sample(raw);
    }
  }

  const frame_header_t hdr =
      make_frame_header(++seq_counter, micros(), frame_buf, sizeof(frame_buf));

  Serial.write(reinterpret_cast<const uint8_t*>(&hdr), sizeof(hdr));
  Serial.write(frame_buf, sizeof(frame_buf));

  const uint32_t elapsed = micros() - scan_start_us;
  if (elapsed < kScanPeriodUs) {
    delayMicroseconds(kScanPeriodUs - elapsed);
  }
}
