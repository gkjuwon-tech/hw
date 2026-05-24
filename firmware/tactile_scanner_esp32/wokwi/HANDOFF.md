# Handoff — Wokwi simulation + PCB aesthetic overhaul (in progress)

**Branch:** `devin/1779620361-pcb-mfg-artifacts`
**PR:** https://github.com/gkjuwon-tech/hw/pull/5
**Session resumed at:** continuation of Phase A → Phase B work

---

## TL;DR

This session covered **two halves** of one larger PR:

1. **Phase A — PCB aesthetic overhaul** (DONE, ready for review).
2. **Phase B — Wokwi hardware simulation** (PARTIALLY DONE, blocked on
   one issue described below; project skeleton + firmware build chain +
   diagram are committed so the next session can pick up immediately).

The goal stated by the user was:

> "예술의 경지로 텐션올려서 [silk-screen 갈아엎고] … wokwi 로 시뮬 빡세게
> 돌려봐 해피케이스, 엣지케이스 다. 다 통과해야 안정적으로 발주 넣을 수
> 있어."

So this PR must satisfy two acceptance bars before fab submission:

- (A) silk-screen / trace artwork passes a visual sanity check, and
- (B) firmware behaviour passes a comprehensive Wokwi test matrix
  (happy / edge / fault cases).

Phase A is good enough to share; Phase B needs ~1 hour more once the
serial-capture issue is sorted (see "Open issue" below).

---

## What changed in this session

### Phase A — aesthetic overhaul (DONE)

All visual gripes from the previous round were addressed:

| Issue (previous round) | Fix in this session |
|---|---|
| Silk text looked like 5×7 bitmap glyphs ("∑CANNER" instead of "SCANNER") | Switched to Hershey Simplex Roman stroke font (public-domain, 1967, futural variant). 95-glyph subset extracted from the `Hershey-Fonts` Python package and embedded as `tools/hershey_simplex.py`. |
| RefDes labels overlapping pads & neighbouring component bodies | New `_label_position()` picker tries above → below → right → left, rejecting positions that (a) exceed board margins or (b) overlap any other component body. Per-refdes overrides (`LABEL_OVERRIDES`) for the densest clusters (D2/D3 + R20/R21, SW1/SW2). Label-vs-label avoidance for non-overridden parts. Connectors with their own callout (J1/J2/J3/U1) skip the refdes label entirely. |
| 90° L-shaped traces that looked "끌려가는 선" | New `_trace45()` helper draws L-shapes with a 45° chamfer at every corner. All routed nets use it: USB VBUS, USB D±, LDO output, FFC fanouts to both 4067s, MUX-select bus, ADC, LED current paths, BOOT/RESET pull-ups. |
| No board branding | 4×4 mesh-grid "logo" with one highlighted cell on the bottom-right of the top silk + a framed title block ("CONET SCANNER V1 / PROTO BATCH 01 — EVT"). Bottom silk has full project URL. |
| Components placed inside other component bodies (R40 inside SW1, R41 inside SW2) | Moved R40 → (49, 37.5), R41 → (57, 22), C8 → (46, 37.5). Verified no body overlaps remain. |
| Bottom silk read mirrored on the fab preview | `_silk_text()` gained a `mirror_x=True` mode and bottom-silk strings now use it. |

After the changes the regenerated artefacts are:

- `hardware/pcb/conet-scanner-v1/gerbers.zip`
- `hardware/pcb/conet-scanner-v1/bom.csv`
- `hardware/pcb/conet-scanner-v1/cpl.csv`

These were verified by re-rendering through gerbonara → SVG → PNG and
visually inspecting the top side. Files preserved at:
- `/tmp/preview_top.png` (top-side full render, on the working VM)
- `/tmp/preview_bottom.png` (bottom-side full render)

To regenerate yourself:

```bash
cd hardware/pcb/conet-scanner-v1
python3 tools/build_artifacts.py
# Optional preview:
rm -rf /tmp/gerber_check && mkdir -p /tmp/gerber_check
unzip -o gerbers.zip -d /tmp/gerber_check/
python3 -c "
import gerbonara, warnings
warnings.filterwarnings('ignore')
stack = gerbonara.LayerStack.open('/tmp/gerber_check/')
open('/tmp/preview_top.svg','w').write(str(stack.to_pretty_svg(side='top')))
open('/tmp/preview_bottom.svg','w').write(str(stack.to_pretty_svg(side='bottom')))
"
rsvg-convert -w 2000 /tmp/preview_top.svg -o /tmp/preview_top.png
rsvg-convert -w 2000 /tmp/preview_bottom.svg -o /tmp/preview_bottom.png
```

### Phase B — Wokwi simulation scaffolding (PARTIALLY DONE)

- `firmware/tactile_scanner_esp32/wokwi/wokwi.toml` — project pointer
  for `wokwi-cli`; references `firmware.bin` (merged flash image) and
  `firmware.elf` (for symbols).
- `firmware/tactile_scanner_esp32/wokwi/diagram.json` — board schematic
  for the simulator:
  - 1× `board-esp32-s3-devkitc-1` (the simulated MCU)
  - 2× `chip-74hc4067` (row and column 16-channel MUX, same family as
    the real CD74HC4067 on the EVT board)
  - 1× 10 kΩ pull-down resistor on the column-MUX SIG so the ADC sees a
    deterministic 0 V when no test cell is active
  - 5× test-cell resistors representing pressed cells:
    - (row 0, col 0) → 1 kΩ
    - (row 0, col 15) → 1.5 kΩ
    - (row 15, col 0) → 2 kΩ
    - (row 15, col 15) → 3.3 kΩ (the four corner-edge cells)
    - (row 7, col 11) → 680 Ω (the dedicated single-cell test point)
  - GPIO mapping (matches the firmware's `ROW_S0..S3` / `COL_S0..S3` /
    `ADC_PIN` constants exactly): row select on GPIO 4–7, column select
    on GPIO 15–18, ADC on GPIO 1.
- `firmware/tactile_scanner_esp32/wokwi/build_firmware.sh` — Arduino-CLI
  build script that compiles the existing sketch with `CDCOnBoot=default,
  USBMode=default` (so `Serial` is routed to UART0 → `wokwi-cli` can log
  it) and copies the resulting `firmware.elf` + merged `firmware.bin`
  next to `wokwi.toml`.
- `firmware/tactile_scanner_esp32/wokwi/.gitignore` — keeps the built
  binaries out of git (they are >320 KB / 7 MB; should be rebuilt by CI
  or each developer).

Build artefacts are intentionally NOT committed. To produce them:

```bash
arduino-cli core install esp32:esp32   # one-time
firmware/tactile_scanner_esp32/wokwi/build_firmware.sh
```

This was tested end-to-end during the session: arduino-cli 1.5.0 +
esp32:esp32 3.3.8 compiles the sketch cleanly (~327 KB program, 22 KB
RAM); `wokwi-cli lint` reports zero errors on `diagram.json`;
`wokwi-cli` connects to the Wokwi Simulation API with the
`WOKWI_CLI_TOKEN` and starts the simulation. See "Open issue" for what
is not yet working.

---

## Open issue — Wokwi serial capture is empty

`wokwi-cli` runs the simulation against `firmware.bin`/`firmware.elf`
and reaches "Starting simulation…", but `--serial-log-file` writes an
empty file and `--expect-text` times out.

This was reproduced with a **trivial three-line "hello-world" sketch**
on both `board-esp32-s3-devkitc-1` and `wokwi-esp32-devkit-v1`, with the
firmware compiled in UART-Serial mode (`CDCOnBoot=default`,
`USBMode=default`). So the issue is **not** specific to our scanner
firmware — there is some configuration step missing between
`wokwi-cli` v0.26.1 and our environment.

Hypotheses to investigate next (in order of likelihood):

1. The default `board-esp32-s3-devkitc-1` part may need an explicit
   serial-monitor part wired to GPIO 43/44 in `diagram.json` for the
   CLI to capture UART output. (Some Wokwi boards stream the on-chip
   UART automatically; others require a `wokwi-serial-monitor` part on
   the diagram.)
2. The merged `firmware.bin` may be loading at the wrong flash offset.
   The `arduino-cli` merged binary normally embeds bootloader at 0x0
   and the app at 0x10000; Wokwi may expect a single contiguous image
   from 0x0. Worth trying the app-only `*.ino.bin` plus an explicit
   `firmware_offset` in `wokwi.toml`, or generating the merged binary
   manually with `esptool.py merge_bin --target-offset 0x0`.
3. The chip may need a Wokwi-recognised CDC mode (`CDCOnBoot=cdc` +
   `USBMode=default`). The first build of the session used this mode
   and produced the same empty-log behaviour, but it was tried before
   the merged-binary swap so it's worth re-trying in combination with
   merged-bin.
4. The `WOKWI_CLI_TOKEN` is a free-tier "CI" token. Free tier may have
   per-simulation duration limits; double-check the dashboard for any
   warnings on this account.

Until one of these is resolved the test runner can't actually verify
behaviour against silicon. In the meantime the **Python software-only
fallback** described in the next section was sketched out and should be
implemented even if Wokwi works, because it runs in CI without a token
and gives sub-second feedback.

---

## Plan for next session

(Ordered, with explicit acceptance criteria the user expects.)

1. **Unblock Wokwi serial capture.** Try hypotheses 1–4 above. The
   moment a "hello-world" sketch streams `hello from wokwi` into
   `--serial-log-file`, move on.
2. **Rebuild the scanner firmware** with `build_firmware.sh` and verify
   it produces frames. A correct frame starts with the magic
   `0x434F4E54` ("CONT" in little-endian) followed by `rows=16`,
   `cols=16`, monotonically increasing `seq`, a CRC16-CCITT of the 256-
   byte payload, and 256 bytes of compressed ADC samples.
3. **Write the Python harness** at
   `firmware/tactile_scanner_esp32/wokwi/run_tests.py`. It should:
   - Launch `wokwi-cli` as a subprocess for each scenario.
   - Tail the serial log, slice it into frames using the magic header,
     verify the CRC, and emit a structured pass/fail.
   - Support a `--software` mode that bypasses Wokwi and exercises the
     pure-logic parts of the firmware (CRC, `compress_sample`, frame
     header packing) in a tiny C++ harness compiled with the host
     toolchain. This gives us deterministic CI without external services
     and matches what the user actually cares about for shipping.
4. **Cover all 10 scenarios** the user explicitly enumerated:
   1. *happy*: gaussian-shaped touch at (8, 8) → 256B frame with a
      reasonable peak.
   2. *all-zero*: no test cells active → frame ≤ ADC_DEAD threshold
      after compression (i.e. all bytes 0).
   3. *all-max*: all cells short to V+ → frame all 0xFF.
   4. *single-cell* at (7, 11) → only that index non-zero.
   5. *edge cells* (0,0), (0,15), (15,0), (15,15) → exactly those four
      indices non-zero; no off-by-one bug on the boundary.
   6. *MUX settling*: shorten `delayMicroseconds(2)` between
      `selectMux` and `analogRead` (recompile a variant) → cross-talk
      between adjacent channels should appear. Confirms the 2 µs
      settling time is actually sufficient.
   7. *RESET*: pulse the EN/RST pin → frames stop, then resume with
      `seq` restarting from 1.
   8. *USB reconnect*: not directly testable in `wokwi-cli` (no USB
      stack emulation). Plan: emit a clear "skip / manual-only" verdict
      with a documented manual procedure (unplug USB on the EVT board
      and watch the host re-enumerate).
   9. *I²C alt path (DNP ADS1115)*: schematic feature, not present on
      the populated EVT board. Plan: a separate variant build of the
      firmware that compiles in the ADS1115 path, exercised with a
      `wokwi-ads1115` part. Document this as a v1.1 follow-up; not
      blocking the first 5-board fab order.
   10. *Timing/jitter*: `loop()` is supposed to run at 200 Hz with
       ≤ 1 ms jitter. Verify by timestamping each frame on the host
       and computing inter-arrival statistics over 1000 frames.
5. **CI**: optional GitHub Actions job that runs the software-mode
   harness on every push (no token required). Wokwi-mode job behind a
   manual workflow_dispatch trigger.
6. **PR update**: attach the rendered top + bottom previews and the
   test-result summary, then notify the user.

User explicitly said: **all scenarios must pass before he authorises
the fab order.** So treat (4.1–4.7, 4.10) as blocking and (4.8, 4.9) as
documented-skip with a clear rationale.

---

## Things not to break

- `hardware/pcb/conet-scanner-v1/schematic.md` is the frozen source of
  truth. Do not edit netlists or pin assignments. If the layout
  generator and the schematic disagree, the schematic wins and the
  generator must be patched.
- `firmware/tactile_scanner_esp32/tactile_scanner_esp32.ino` is the
  shipping firmware. Do not modify it to make tests pass; instead build
  test variants via `--build-property` or per-scenario `#define` flags.
- The user has zero tolerance for fake-passing tests. If a scenario
  cannot be exercised honestly in Wokwi (USB reconnect, ADS1115 alt
  path), mark it as `untested / manual-only / deferred` with a clear
  reason — do not stub or skip silently.
- The PR description currently includes a "PR limitations" block. Keep
  it; do not claim production-readiness. The board is still EVT.

---

## Files touched this session (relative to repo root)

Modified:
- `hardware/pcb/conet-scanner-v1/tools/build_artifacts.py` (silk
  rewrite, 45° traces, label avoidance, bottom-silk mirror)
- `hardware/pcb/conet-scanner-v1/tools/components.py` (R40/R41/C8
  re-locations)
- `hardware/pcb/conet-scanner-v1/gerbers.zip` (regenerated)
- `hardware/pcb/conet-scanner-v1/cpl.csv` (regenerated)

Added:
- `hardware/pcb/conet-scanner-v1/tools/hershey_simplex.py`
- `firmware/tactile_scanner_esp32/wokwi/wokwi.toml`
- `firmware/tactile_scanner_esp32/wokwi/diagram.json`
- `firmware/tactile_scanner_esp32/wokwi/build_firmware.sh`
- `firmware/tactile_scanner_esp32/wokwi/.gitignore`
- `firmware/tactile_scanner_esp32/wokwi/HANDOFF.md` (this file)

Not touched (intentionally):
- `firmware/tactile_scanner_esp32/tactile_scanner_esp32.ino`
- `hardware/pcb/conet-scanner-v1/schematic.md`
- `hardware/pcb/conet-scanner-v1/README.md`
- `HARDWARE_BUILD_GUIDE.md`
- `tools/gerber.py`, `tools/footprints.py`
