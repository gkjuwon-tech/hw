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
// License: Proprietary. Conet Studio, 2026.

#include <Arduino.h>

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

// ─── Geometry ────────────────────────────────────────────────────────────────
constexpr uint16_t ROWS = 16;
constexpr uint16_t COLS = 16;
constexpr uint32_t SCAN_HZ = 200;
constexpr uint32_t SCAN_PERIOD_US = 1000000UL / SCAN_HZ;

constexpr uint16_t ADC_MAX = 4095;  // 12-bit
constexpr uint16_t ADC_DEAD = 32;   // noise floor we subtract before compression

// ─── Wire format ─────────────────────────────────────────────────────────────
constexpr uint32_t FRAME_MAGIC = 0x434F4E54UL;  // 'CONT'

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

static uint8_t frame_buf[ROWS * COLS];
static uint32_t seq_counter = 0;

// ─── Helpers ─────────────────────────────────────────────────────────────────
static inline void selectMux(uint8_t value, uint8_t s0, uint8_t s1, uint8_t s2, uint8_t s3) {
  digitalWrite(s0, value & 0x01);
  digitalWrite(s1, (value >> 1) & 0x01);
  digitalWrite(s2, (value >> 2) & 0x01);
  digitalWrite(s3, (value >> 3) & 0x01);
}

static uint16_t crc16_ccitt(const uint8_t* data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t b = 0; b < 8; ++b) {
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021) : static_cast<uint16_t>(crc << 1);
    }
  }
  return crc;
}

static uint8_t compress_sample(uint16_t raw) {
  if (raw <= ADC_DEAD) return 0;
  // Linear remap with mild log shaping for the upper third of the range.
  const float v = static_cast<float>(raw - ADC_DEAD) / static_cast<float>(ADC_MAX - ADC_DEAD);
  const float shaped = v < 0.66f ? v : 0.66f + 0.34f * logf(1.0f + (v - 0.66f) * 4.0f) / logf(1.0f + 4.0f * 0.34f);
  const int v8 = static_cast<int>(shaped * 255.0f + 0.5f);
  return v8 < 0 ? 0 : (v8 > 255 ? 255 : static_cast<uint8_t>(v8));
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

  for (uint16_t r = 0; r < ROWS; ++r) {
    selectMux(static_cast<uint8_t>(r), ROW_S0, ROW_S1, ROW_S2, ROW_S3);
    delayMicroseconds(2);
    for (uint16_t c = 0; c < COLS; ++c) {
      selectMux(static_cast<uint8_t>(c), COL_S0, COL_S1, COL_S2, COL_S3);
      delayMicroseconds(2);
      const uint16_t raw = analogRead(ADC_PIN);
      frame_buf[r * COLS + c] = compress_sample(raw);
    }
  }

  frame_header_t hdr;
  hdr.magic = FRAME_MAGIC;
  hdr.rows = ROWS;
  hdr.cols = COLS;
  hdr.seq = ++seq_counter;
  hdr.timestamp_us = micros();
  hdr.crc = crc16_ccitt(frame_buf, sizeof(frame_buf));
  hdr._pad = 0;

  Serial.write(reinterpret_cast<const uint8_t*>(&hdr), sizeof(hdr));
  Serial.write(frame_buf, sizeof(frame_buf));

  const uint32_t elapsed = micros() - scan_start_us;
  if (elapsed < SCAN_PERIOD_US) {
    delayMicroseconds(SCAN_PERIOD_US - elapsed);
  }
}
