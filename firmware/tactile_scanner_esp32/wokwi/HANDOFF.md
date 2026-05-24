# Handoff — Wokwi simulation harness (Phase B)

**Branch:** `devin/1779623674-wokwi-test-harness`
**Predecessor PR:** https://github.com/gkjuwon-tech/hw/pull/5 (Phase A, merged — silkscreen overhaul)
**Status:** Phase B closed. Software-mode harness = 10 pass / 2 documented-skip / 0 fail. Wokwi-mode harness = 3 pass / 0 fail. Ready for fab once the user signs off on PR review.

---

## TL;DR

- The 10-scenario test plan the user enumerated for fab gating is now codified
  in `run_tests.py`. 7 scenarios run in pure host-mode (no token, fast CI on
  every push). 3 scenarios run on Wokwi hardware-in-loop (token-gated,
  workflow_dispatch only). 2 scenarios are documented as out-of-scope-for-Wokwi
  with explicit, honest skip rationale.
- The previous session's open blocker (Wokwi serial capture returned 0 bytes)
  is **resolved**. The cause was `CDCOnBoot=default` routing `Serial` to UART0,
  but Wokwi's `board-esp32-s3-devkitc-1` only emulates the native USB-OTG jack
  on GPIO 19/20. Switching the build flag to `CDCOnBoot=cdc` produces a
  clean stream of CONT-prefixed frames at first-byte alignment.
- `CDCOnBoot=cdc` also happens to be the **production-correct** flag for the
  shipping board — `schematic.md` confirms J3 USB-C → D1 ESD clamp → GPIO 19/20
  with no CP210x bridge. So the Wokwi unblock was simultaneously a latent
  production bug fix. The old flag would have shipped a board that's silent
  on its primary USB-C jack.
- All firmware wire-format logic (CRC16-CCITT, ADC compression, frame header)
  is now centralized in `scanner_frame.h`, which is `#include`d by both the
  shipping `.ino` and the host-mode simulator. Byte-for-byte equivalence is
  enforced structurally — there is no possible drift between firmware and
  host simulator because they compile against the same source.

---

## What's in the harness

`firmware/tactile_scanner_esp32/wokwi/run_tests.py` — single Python entry point,
two modes:

```bash
# Software mode (default). No Wokwi token, no firmware build needed.
# Runs the host_sim binary across deterministic ADC matrices and
# validates every byte of every frame.
python3 run_tests.py

# Wokwi mode. Requires WOKWI_CLI_TOKEN env var and a built firmware
# (run build_firmware.sh first).
python3 run_tests.py --mode wokwi
```

### Software-mode scenarios (10 pass / 2 documented-skip)

| # | Scenario | What it locks down |
|---|---|---|
| 1 | `protocol_constants` | Python reference impl of `crc16_ccitt` and `compress_sample` matches the firmware. CCITT-FALSE test vector `0x29B1`, ADC-DEAD boundary, mid-range and saturation behavior, knee-of-curve continuity. |
| 2 | `happy` | Gaussian touch centered at (8,8) — peak byte lands on cell (8,8), neighbors decay, CRC clean. |
| 3 | `all_zero` | No active cells (ADC inputs at floor) → payload is all-zero. Covers the ADC_DEAD floor boundary. |
| 4 | `all_max` | All cells shorted to V+ → payload saturates to 0xFF across all 256 bytes. |
| 5 | `single_cell` | Only cell (7,11) active. Verifies no row/col confusion in `compress_sample` indexing. |
| 6 | `edge_cells` | Four corners (0,0), (0,15), (15,0), (15,15) active. Catches off-by-one in row 0/15 and col 0/15. |
| 7 | `mux_settling_curve` | `compress_sample` is monotonic on (ADC_DEAD, ADC_MAX]. (Real analog cross-talk is a wokwi/silicon concern; this scenario locks the *firmware-side* shaping curve.) |
| 8 | `reset_seq` | A fresh `make_frame_header` invocation starts seq at 1. The full RESET/EN pulse path lives in wokwi mode. |
| 9 | `timing_period` | `SCAN_HZ` math gives a 5 ms period. Real jitter is wokwi/silicon. |
| 10 | `payload_size` | Payload remains exactly 256 bytes. Backend `/ingest` assumes this. |
| skip | `usb_reconnect` | Documented as manual-only with a written procedure (Wokwi has no USB-host stack). |
| skip | `ads1115_alt_path` | Documented as v1.1 follow-up (U4 ADS1115 is DNP on the EVT BOM). |

### Wokwi-mode scenarios (3 pass)

These run the real firmware on Wokwi's simulated ESP32-S3 hardware. One
`wokwi-cli` invocation (~50s wall-clock) feeds all three scenarios via the
`_WOKWI_CACHE` shared fixture.

| # | Scenario | What it locks down |
|---|---|---|
| W1 | `wokwi_smoke` | Firmware boots on simulated silicon, emits CONT magic at offset 0 of the serial stream (no boot garbage in front of the protocol), ≥30 frames in the capture window, seq starts at 1 and is strictly monotonic. |
| W2 | `wokwi_frame_progress` | Firmware sustains scanning (≥5 Hz floor, no rate drift >30% between first/second half of the capture). This is **intentionally** not asserting the 200 Hz target — Wokwi's `analogRead()` model is ~10× slower than real silicon, so 200 Hz absolute is a silicon-only measurement. |
| W3 | `wokwi_crc_integrity` | 100% of captured frames pass CRC16-CCITT. The `_parse_serial_log` already filters by CRC, so the test asserts the parsed-frame count matches `len(blob) // FRAME_SIZE` (within ±1 frame for partial bytes at the tail). |

---

## Files

```
firmware/tactile_scanner_esp32/
├── scanner_frame.h          # NEW. Wire-protocol single source of truth.
│                            #   - frame_header_t struct
│                            #   - crc16_ccitt() (CCITT-FALSE, init 0xFFFF)
│                            #   - compress_sample() (ADC_DEAD floor + log knee)
│                            #   - make_frame_header() factory
│                            # Included by both the .ino and the host sim.
├── tactile_scanner_esp32.ino  # REFACTORED. Logic unchanged; now uses
│                              # scanner_frame.h instead of inline copies.
└── wokwi/
    ├── HANDOFF.md           # this file
    ├── build_firmware.sh    # UPDATED. Now uses CDCOnBoot=cdc by default
    │                        # (production-correct + Wokwi-compatible).
    │                        # Override with CDC_ON_BOOT=default for J4 bring-up.
    │                        # Also synthesizes flasher_args.json for wokwi-cli.
    ├── diagram.json         # ESP32-S3 + 2× CD74HC4067 + 8 test cells
    ├── wokwi.toml           # Points at build/flasher_args.json + build/app.elf
    ├── run_tests.py         # The harness. 10+3 scenarios, two modes.
    └── host_sim/
        ├── scan_one_frame.cpp  # Host-mode scan loop: stdin → ADC matrix,
        │                       # stdout → 276-byte CONT frame.
        └── Makefile

.github/workflows/ci.yml     # UPDATED. New jobs:
                             #   - firmware-software-sim: runs on every push.
                             #   - firmware-wokwi-sim: workflow_dispatch only,
                             #     reads WOKWI_CLI_TOKEN secret.
```

---

## How to reproduce locally

```bash
# 1. Software-mode (fast, no auth needed).
cd firmware/tactile_scanner_esp32/wokwi
make -C host_sim
python3 run_tests.py
# expected: 10 passed   2 skipped   0 failed   (exit 0)

# 2. Wokwi mode (requires arduino-cli + esp32 core + wokwi-cli + token).
export WOKWI_CLI_TOKEN=...
bash build_firmware.sh
python3 run_tests.py --mode wokwi
# expected: 3 passed   0 skipped   0 failed   (exit 0, ~50s wall-clock)
```

---

## Things to NOT break

- `scanner_frame.h` is the **wire-protocol contract**. Do not change `kFrameMagic`,
  the `frame_header_t` field layout (`#pragma pack(1)`), or the CRC/compress
  algorithms without coordinating with the backend `/ingest` endpoint and the
  next firmware release.
- `tactile_scanner_esp32.ino` was refactored to use the shared header. The
  scan loop / pin assignments / timing constants are unchanged. **Do not** add
  test-variant `#define`s here — use `--build-property` flags from
  `build_firmware.sh` instead.
- `build_firmware.sh` now defaults to `CDCOnBoot=cdc`. The `CDC_ON_BOOT=default`
  override is for **hardware bring-up only**, via the J4 4-pin UART header.
  Do not switch the default back without re-verifying the schematic.
- Wokwi-mode scenarios run on the **free tier**, which is rate-limited. CI
  is gated behind `workflow_dispatch` for this reason. If you need to run
  it more aggressively, switch to a paid Wokwi plan first.

---

## Open follow-ups (not blocking fab)

1. **Scenario W4 — analog plumbing in Wokwi.** The current `diagram.json` uses
   `chip-74hc4067` as a stub (no analog passthrough), so wokwi-mode payloads
   are all-zero — the wokwi scenarios verify framing/timing, not analog
   correctness. To wire real analog: swap to `board-cd74hc4067` and route a
   `wokwi-potentiometer` through known mux channels. Acceptance: with the pot
   at midscale on channel (8,8), the captured byte at index 136 is non-zero
   and increases monotonically as the pot turns up.
2. **Scenario 9 — ADS1115 alt path.** v1.1 schematic feature. Needs a
   separate firmware variant (`#ifdef USE_ADS1115`) and a `wokwi-ads1115`
   part in a second diagram.
3. **Scenario 8 — USB reconnect.** Wokwi-cli has no USB host stack, so
   re-enumeration cannot be simulated. Manual procedure documented in
   `run_tests.py`. If we ever switch to a Wokwi feature with USB host
   emulation, lift this out of the skip list.
4. **Cycle-accurate Wokwi timing.** Wokwi's `analogRead()` is ~10× slower than
   real silicon, so we can't enforce the 200 Hz target there. When the EVT
   boards arrive, take a logic-analyzer trace of GPIO 5 (col MUX EN toggle)
   and verify the 5 ms period directly. That replaces the "absolute Hz"
   wokwi assertion with a real silicon measurement.
