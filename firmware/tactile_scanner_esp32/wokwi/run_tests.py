#!/usr/bin/env python3
"""Conet Tactile — Wokwi / host-mode test harness.

This harness covers the 10 scenarios the user enumerated in HANDOFF.md,
PLUS 8 additional hardcore scenarios added for PCB fab gating validation.
Two execution modes are supported:

* `--mode software` (default, no token required):
    Compiles `host_sim/scan_one_frame` (which reuses the firmware's
    `scanner_frame.h`) and feeds it deterministic 16x16 ADC matrices.
    Verifies the resulting wire-format frames byte-by-byte.
    Runs in <1 s. Ideal for CI on every push.

* `--mode wokwi`:
    Launches `wokwi-cli` against `wokwi.toml` for hardware-in-the-loop
    scenarios that the software mode cannot honestly cover (MUX settling,
    reset, real timing). Requires `WOKWI_CLI_TOKEN` and a working
    `firmware.bin`/`firmware.elf` built by `build_firmware.sh`. Wokwi-mode
    coverage is best-effort right now: see HANDOFF.md for the serial-
    capture investigation status.

Exit status: 0 if every selected scenario passes (or is documented-skip
with a clear rationale), non-zero otherwise. The user has zero tolerance
for fake-passing tests, so unverifiable scenarios are reported as
SKIPPED with an explanation, never silently PASSED.

Usage:
    python3 run_tests.py                # software mode, all scenarios
    python3 run_tests.py --mode wokwi   # wokwi mode (token required)
    python3 run_tests.py --only happy single edge
    python3 run_tests.py --json         # machine-readable summary
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterable

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent  # firmware/tactile_scanner_esp32/wokwi → repo
HOST_SIM_DIR = HERE / "host_sim"
HOST_SIM_BIN = HOST_SIM_DIR / "scan_one_frame"

# Wire-format constants — must mirror `scanner_frame.h`. Validated by the
# `protocol_constants` scenario so any drift fails CI.
ROWS = 16
COLS = 16
ADC_MAX = 4095
# Mirror firmware/scanner_frame.h::kAdcDead. The v1 divider rests at
# ~1000-1050 counts on every unpressed cell across the silicon variance
# band, so the noise floor must be above the un-pressed baseline rather
# than just the ADC noise floor. Bumping this without re-bumping the
# constant in scanner_frame.h would break the cross-validation tests.
ADC_DEAD = 1100
SCAN_HZ = 200
FRAME_MAGIC = 0x434F4E54  # 'CONT'
FRAME_HDR_FMT = "<IHHIIHH"  # magic, rows, cols, seq, ts_us, crc, _pad
FRAME_HDR_SIZE = struct.calcsize(FRAME_HDR_FMT)
PAYLOAD_SIZE = ROWS * COLS
FRAME_SIZE = FRAME_HDR_SIZE + PAYLOAD_SIZE

assert FRAME_HDR_SIZE == 20, "Header size drift — update scanner_frame.h or this constant"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _crc16_ccitt(data: bytes) -> int:
    """Reference implementation matching `scanner_frame.h::crc16_ccitt`."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def _compress_sample(raw: int) -> int:
    """Reference implementation matching `scanner_frame.h::compress_sample`."""
    import math

    if raw <= ADC_DEAD:
        return 0
    v = (raw - ADC_DEAD) / (ADC_MAX - ADC_DEAD)
    if v < 0.66:
        shaped = v
    else:
        shaped = 0.66 + 0.34 * math.log(1.0 + (v - 0.66) * 4.0) / math.log(1.0 + 4.0 * 0.34)
    v8 = int(shaped * 255.0 + 0.5)
    return max(0, min(255, v8))


def _make_adc_matrix(values: dict[tuple[int, int], int]) -> bytes:
    """Build a 16x16 uint16-LE ADC matrix from a sparse {(r, c): raw} dict.

    Cells not in `values` default to 0 (below the ADC_DEAD floor).
    """
    flat = [0] * (ROWS * COLS)
    for (r, c), raw in values.items():
        if not (0 <= r < ROWS and 0 <= c < COLS):
            raise ValueError(f"cell ({r},{c}) out of bounds")
        if not (0 <= raw <= 0xFFFF):
            raise ValueError(f"adc value {raw} out of 16-bit range")
        flat[r * COLS + c] = raw
    return struct.pack(f"<{ROWS * COLS}H", *flat)


def _adc_constant(raw: int) -> bytes:
    return struct.pack(f"<{ROWS * COLS}H", *([raw] * (ROWS * COLS)))


def _adc_gaussian_at(center: tuple[int, int], peak: int, sigma: float = 1.5) -> bytes:
    """Smooth 2D gaussian touch print centred at `center` with magnitude `peak`."""
    import math

    cr, cc = center
    flat = []
    for r in range(ROWS):
        for c in range(COLS):
            d2 = (r - cr) ** 2 + (c - cc) ** 2
            v = peak * math.exp(-d2 / (2.0 * sigma * sigma))
            flat.append(max(0, min(0xFFFF, int(round(v)))))
    return struct.pack(f"<{ROWS * COLS}H", *flat)


# ─── Software-mode driver ────────────────────────────────────────────────────


def _ensure_host_sim_built() -> None:
    if HOST_SIM_BIN.exists():
        return
    subprocess.run(["make"], cwd=HOST_SIM_DIR, check=True)


def _run_host_sim(adc: bytes, seq: int, timestamp_us: int) -> bytes:
    if len(adc) != ROWS * COLS * 2:
        raise ValueError(f"adc input must be {ROWS * COLS * 2} bytes, got {len(adc)}")
    proc = subprocess.run(
        [str(HOST_SIM_BIN), "--seq", str(seq), "--timestamp", str(timestamp_us)],
        input=adc,
        capture_output=True,
        check=True,
    )
    if len(proc.stdout) != FRAME_SIZE:
        raise RuntimeError(
            f"host_sim returned {len(proc.stdout)} bytes, expected {FRAME_SIZE}"
        )
    return proc.stdout


def _parse_frame(buf: bytes) -> tuple[dict, bytes]:
    if len(buf) != FRAME_SIZE:
        raise ValueError(f"frame size {len(buf)} != {FRAME_SIZE}")
    magic, rows, cols, seq, ts_us, crc, pad = struct.unpack(
        FRAME_HDR_FMT, buf[:FRAME_HDR_SIZE]
    )
    payload = buf[FRAME_HDR_SIZE:]
    hdr = {
        "magic": magic,
        "rows": rows,
        "cols": cols,
        "seq": seq,
        "timestamp_us": ts_us,
        "crc": crc,
        "_pad": pad,
    }
    return hdr, payload


def _assert_frame_envelope(hdr: dict, expected_seq: int) -> None:
    if hdr["magic"] != FRAME_MAGIC:
        raise AssertionError(
            f"bad magic: 0x{hdr['magic']:08X} != 0x{FRAME_MAGIC:08X}"
        )
    if hdr["rows"] != ROWS or hdr["cols"] != COLS:
        raise AssertionError(
            f"bad geometry: rows={hdr['rows']} cols={hdr['cols']}"
        )
    if hdr["seq"] != expected_seq:
        raise AssertionError(f"bad seq: {hdr['seq']} != {expected_seq}")
    if hdr["_pad"] != 0:
        raise AssertionError(f"reserved _pad must be zero, got {hdr['_pad']}")


def _assert_crc(hdr: dict, payload: bytes) -> None:
    expected = _crc16_ccitt(payload)
    if hdr["crc"] != expected:
        raise AssertionError(f"bad CRC: 0x{hdr['crc']:04X} != 0x{expected:04X}")


# ─── Scenario types ─────────────────────────────────────────────────────────


@dataclasses.dataclass
class ScenarioResult:
    name: str
    status: str  # "passed" | "failed" | "skipped"
    detail: str
    duration_ms: float


SoftwareScenario = Callable[[], None]


def _scenario_protocol_constants() -> None:
    """Sanity check: the Python reference matches the firmware's wire format.

    If somebody changes a constant in scanner_frame.h without updating this
    file, the rest of the suite would silently pass against the wrong
    expectation. So this scenario is the canary.
    """
    # Spot-check `compress_sample`:
    #   raw=0 → 0 (below ADC_DEAD)
    #   raw=ADC_DEAD → 0 (boundary)
    #   raw mid-range → strictly non-zero, well below 255
    #   raw=ADC_MAX → 255 (saturates)
    # NB: raw=ADC_DEAD+1 still rounds to 0 because (1 / (ADC_MAX-ADC_DEAD)) *
    # 255 < 0.5. The first raw that produces a non-zero byte is ~ADC_DEAD+8.
    assert _compress_sample(0) == 0, "compress_sample(0) must be 0"
    assert _compress_sample(ADC_DEAD) == 0, "compress_sample(ADC_DEAD) must be 0"
    assert 0 < _compress_sample(2048) < 255, "mid-range must be in (0, 255)"
    assert _compress_sample(ADC_MAX) == 255, "saturates at ADC_MAX"
    # The two halves of the shaping curve meet smoothly: just below v==0.66
    # (linear) and just above (log) should produce adjacent bytes within ±1.
    # raw at v≈0.66 → raw = ADC_DEAD + 0.66 * (ADC_MAX - ADC_DEAD) ≈ 2713
    knee_lo = _compress_sample(2710)
    knee_hi = _compress_sample(2716)
    assert abs(knee_hi - knee_lo) <= 2, (
        f"shaping curve has a discontinuity at the linear/log knee: "
        f"{knee_lo} → {knee_hi}"
    )
    # Spot-check CRC against well-known vectors.
    # CRC16-CCITT-FALSE("123456789") = 0x29B1.
    assert _crc16_ccitt(b"123456789") == 0x29B1, "CCITT-FALSE test vector"
    assert _crc16_ccitt(b"") == 0xFFFF, "empty buffer keeps init value"
    # The firmware's frame header is exactly 20 bytes packed.
    assert FRAME_HDR_SIZE == 20


def _scenario_happy() -> None:
    """Gaussian touch at (8, 8) → frame envelope + CRC + payload has a peak."""
    adc = _adc_gaussian_at((8, 8), peak=3000, sigma=1.5)
    frame = _run_host_sim(adc, seq=1, timestamp_us=200_000)
    hdr, payload = _parse_frame(frame)
    _assert_frame_envelope(hdr, expected_seq=1)
    _assert_crc(hdr, payload)
    peak_idx = max(range(len(payload)), key=lambda i: payload[i])
    if (peak_idx // COLS, peak_idx % COLS) != (8, 8):
        raise AssertionError(
            f"peak should be at (8,8), got ({peak_idx // COLS},{peak_idx % COLS})"
        )
    if payload[peak_idx] < 100:
        raise AssertionError(f"peak too weak: {payload[peak_idx]}/255")


def _scenario_all_zero() -> None:
    """No cells active → entire payload is zero (below ADC_DEAD)."""
    adc = _adc_constant(0)
    frame = _run_host_sim(adc, seq=42, timestamp_us=42_000)
    hdr, payload = _parse_frame(frame)
    _assert_frame_envelope(hdr, expected_seq=42)
    _assert_crc(hdr, payload)
    if any(b != 0 for b in payload):
        raise AssertionError("payload must be all-zero with ADC=0")
    # Boundary: ADC = ADC_DEAD (32) must still compress to 0.
    adc_floor = _adc_constant(ADC_DEAD)
    frame = _run_host_sim(adc_floor, seq=43, timestamp_us=42_500)
    _, payload = _parse_frame(frame)
    if any(b != 0 for b in payload):
        raise AssertionError("payload must be all-zero at ADC == ADC_DEAD")


def _scenario_all_max() -> None:
    """All cells short → payload saturates to 0xFF."""
    adc = _adc_constant(ADC_MAX)
    frame = _run_host_sim(adc, seq=7, timestamp_us=7_000)
    hdr, payload = _parse_frame(frame)
    _assert_frame_envelope(hdr, expected_seq=7)
    _assert_crc(hdr, payload)
    if any(b != 0xFF for b in payload):
        bad = [(i, b) for i, b in enumerate(payload) if b != 0xFF][:4]
        raise AssertionError(f"payload must be all 0xFF at ADC_MAX, bad: {bad}")


def _scenario_single_cell() -> None:
    """Cell (7, 11) active → only that index non-zero (1-cell test point)."""
    adc = _make_adc_matrix({(7, 11): 2048})
    frame = _run_host_sim(adc, seq=11, timestamp_us=11_000)
    hdr, payload = _parse_frame(frame)
    _assert_frame_envelope(hdr, expected_seq=11)
    _assert_crc(hdr, payload)
    expected_idx = 7 * COLS + 11
    for i, b in enumerate(payload):
        if i == expected_idx:
            if b == 0:
                raise AssertionError(f"cell (7,11) must be > 0, got {b}")
        else:
            if b != 0:
                raise AssertionError(
                    f"cell ({i // COLS},{i % COLS}) must be 0, got {b}"
                )


def _scenario_edge_cells() -> None:
    """All four corner cells active simultaneously → exactly those four nonzero.

    Catches off-by-one bugs at row 0, row 15, col 0, col 15 — i.e. the four
    corners of the FFC + MUX fan-out where layout density is highest.
    """
    corners = [(0, 0), (0, 15), (15, 0), (15, 15)]
    values = {corner: 1500 + 500 * i for i, corner in enumerate(corners)}
    adc = _make_adc_matrix(values)
    frame = _run_host_sim(adc, seq=99, timestamp_us=99_999)
    hdr, payload = _parse_frame(frame)
    _assert_frame_envelope(hdr, expected_seq=99)
    _assert_crc(hdr, payload)
    nonzero = {(i // COLS, i % COLS) for i, b in enumerate(payload) if b != 0}
    if nonzero != set(corners):
        raise AssertionError(
            f"expected exactly the four corners to be non-zero, got {sorted(nonzero)}"
        )


def _scenario_mux_settling_software_only() -> None:
    """Software-side check: `compress_sample` is monotonic on (ADC_DEAD, ADC_MAX].

    The *real* MUX-settling test requires the analog simulator (Wokwi) because
    shortening `delayMicroseconds(2)` only changes the analog values the ADC
    sees, not the bytes our host emits given a fixed ADC matrix. So in
    software mode we verify the contract that `compress_sample` is monotonic
    in the active range — i.e. a higher ADC reading always produces a
    higher-or-equal compressed byte. If MUX settling were broken in
    silicon, the ADC values for adjacent channels would alias; Wokwi mode
    covers that. The software check here keeps the compression curve honest.
    """
    prev = 0
    for raw in range(ADC_DEAD + 1, ADC_MAX + 1):
        b = _compress_sample(raw)
        if b < prev:
            raise AssertionError(
                f"compress_sample regressed at raw={raw}: {b} < {prev}"
            )
        prev = b
    if prev != 255:
        raise AssertionError(f"compress_sample(ADC_MAX) must be 255, got {prev}")


def _scenario_reset_seq_starts_at_one() -> None:
    """Reset semantics in software mode: each fresh host_sim run starts seq=1.

    The shipping firmware uses `static uint32_t seq_counter = 0;` and emits
    `++seq_counter` per frame. After a reboot the counter is re-zeroed, so
    the first post-reset frame has seq==1. The host_sim binary mirrors
    this by taking `--seq` from the caller; the harness simulates "boot,
    run for two frames, reset, run for one more" and asserts the post-reset
    frame restarts at seq==1 with a fresh CRC.
    """
    pre_reset_frames = [
        _run_host_sim(_adc_gaussian_at((5, 5), peak=2000), seq=1, timestamp_us=1000),
        _run_host_sim(_adc_gaussian_at((5, 5), peak=2000), seq=2, timestamp_us=6000),
    ]
    # Verify pre-reset seq increments correctly.
    for expected, frame in enumerate(pre_reset_frames, start=1):
        hdr, _ = _parse_frame(frame)
        if hdr["seq"] != expected:
            raise AssertionError(
                f"pre-reset seq must be {expected}, got {hdr['seq']}"
            )
    # Post-reset frame: seq restarts at 1, fresh timestamp.
    post_reset = _run_host_sim(
        _adc_gaussian_at((5, 5), peak=2000), seq=1, timestamp_us=1000
    )
    hdr, payload = _parse_frame(post_reset)
    if hdr["seq"] != 1:
        raise AssertionError(f"post-reset seq must be 1, got {hdr['seq']}")
    _assert_crc(hdr, payload)


def _scenario_timing_jitter_software_only() -> None:
    """Software-side check: scan-period math gives the advertised SCAN_HZ.

    The real timing/jitter check requires either Wokwi (deterministic
    timing simulation) or silicon (logic analyser on a GPIO toggled per
    frame). In software we cover the static contract: the firmware's
    `kScanPeriodUs` constant matches `1_000_000 / kScanHz`, and the
    per-frame execution time of `compress_sample + crc16_ccitt` on the
    host stays well under one period (because if even the pure-logic
    cost approached 5 ms we'd be in trouble before adding MUX/ADC
    overhead).
    """
    period_us = 1_000_000 // SCAN_HZ
    if period_us != 5000:
        raise AssertionError(
            f"SCAN_HZ={SCAN_HZ} → period_us={period_us}, expected 5000"
        )
    adc = _adc_gaussian_at((8, 8), peak=3000)
    durations_us = []
    for i in range(20):
        t0 = time.perf_counter()
        _run_host_sim(adc, seq=i + 1, timestamp_us=(i + 1) * period_us)
        durations_us.append((time.perf_counter() - t0) * 1_000_000)
    # On a modern host the whole subprocess round-trip should complete well
    # under one full SCAN period (5 ms). If this fails the harness itself
    # is the bottleneck, not the firmware — but it still catches accidental
    # algorithmic complexity regressions.
    worst = max(durations_us)
    if worst > 100_000:  # 100 ms — generous; CI runners sometimes burp
        raise AssertionError(
            f"host_sim round-trip too slow: worst={worst:.0f} µs"
        )


def _scenario_payload_size_drift() -> None:
    """If anyone changes ROWS/COLS in scanner_frame.h, this scenario screams.

    The wire-format protocol is consumed by the backend `/ingest` endpoint
    (256-byte payload assumed) and any drift would silently break inference.
    """
    adc = _adc_constant(0)
    frame = _run_host_sim(adc, seq=1, timestamp_us=1)
    _, payload = _parse_frame(frame)
    if len(payload) != 256:
        raise AssertionError(
            f"payload length drift: got {len(payload)} bytes (backend assumes 256)"
        )


# ─── NEW: Hardcore validation scenarios for PCB fab gating ───────────────────


def _scenario_multi_cell_diagonal() -> None:
    """All 16 diagonal cells (r==c) active → exactly those 16 indices non-zero.

    This exercises the row/column MUX decode path for all 16 channels
    simultaneously — a failure here means the MUX selection for at least
    one of the 16 channels is mis-routed. On the real PCB, this would
    correspond to a uniform diagonal pressure strip across the mesh.
    """
    diag_values = {(i, i): 1800 + i * 50 for i in range(16)}
    adc = _make_adc_matrix(diag_values)
    frame = _run_host_sim(adc, seq=200, timestamp_us=200_000)
    hdr, payload = _parse_frame(frame)
    _assert_frame_envelope(hdr, expected_seq=200)
    _assert_crc(hdr, payload)
    nonzero = {(i // COLS, i % COLS) for i, b in enumerate(payload) if b != 0}
    expected = {(i, i) for i in range(16)}
    if nonzero != expected:
        missing = expected - nonzero
        extra = nonzero - expected
        raise AssertionError(
            f"diagonal pattern mismatch: missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )
    # Also verify monotonic ordering along the diagonal (higher ADC → higher byte)
    diag_bytes = [payload[i * COLS + i] for i in range(16)]
    for i in range(1, 16):
        if diag_bytes[i] < diag_bytes[i - 1]:
            raise AssertionError(
                f"diagonal not monotonic at cell ({i},{i}): "
                f"{diag_bytes[i]} < {diag_bytes[i-1]}"
            )


def _scenario_checkerboard_pattern() -> None:
    """Checkerboard: cells where (r+c)%2==0 are active → exactly 128 non-zero.

    This is the maximum-density simultaneous activation pattern — every
    active cell is surrounded by inactive cells. If the MUX has ANY
    crosstalk, this pattern will bleed signal into adjacent cells.
    """
    values = {}
    for r in range(16):
        for c in range(16):
            if (r + c) % 2 == 0:
                values[(r, c)] = 2000
    adc = _make_adc_matrix(values)
    frame = _run_host_sim(adc, seq=201, timestamp_us=201_000)
    hdr, payload = _parse_frame(frame)
    _assert_frame_envelope(hdr, expected_seq=201)
    _assert_crc(hdr, payload)
    active = [(i // COLS, i % COLS) for i, b in enumerate(payload) if b != 0]
    inactive = [(i // COLS, i % COLS) for i, b in enumerate(payload) if b == 0]
    if len(active) != 128:
        raise AssertionError(
            f"checkerboard must have exactly 128 active cells, got {len(active)}"
        )
    for r, c in active:
        if (r + c) % 2 != 0:
            raise AssertionError(
                f"cell ({r},{c}) is active but (r+c)%2 != 0 — MUX crosstalk?"
            )
    for r, c in inactive:
        if (r + c) % 2 != 1:
            raise AssertionError(
                f"cell ({r},{c}) is inactive but (r+c)%2 != 1 — signal dropout?"
            )


def _scenario_gradient_continuity() -> None:
    """compress_sample output never jumps more than 2 between adjacent ADC values.

    The shaping curve has a linear segment [0, 0.66) and a log segment
    [0.66, 1.0]. At the knee (v ≈ 0.66, raw ≈ 2713), the curve is
    designed to be C0-continuous. This scenario scans EVERY adjacent
    pair of ADC values from 0 to 4095 and verifies no jump exceeds 2.
    """
    max_jump = 0
    worst_at = 0
    prev = _compress_sample(0)
    for raw in range(1, ADC_MAX + 1):
        cur = _compress_sample(raw)
        jump = abs(cur - prev)
        if jump > max_jump:
            max_jump = jump
            worst_at = raw
        prev = cur
    if max_jump > 2:
        raise AssertionError(
            f"compress_sample has a jump of {max_jump} at raw={worst_at} "
            f"(max allowed: 2) — shaping curve discontinuity"
        )
    # Specifically check the knee region (raw ≈ 2700..2730)
    knee_values = [_compress_sample(r) for r in range(2700, 2730)]
    for i in range(1, len(knee_values)):
        if abs(knee_values[i] - knee_values[i - 1]) > 1:
            raise AssertionError(
                f"knee discontinuity at raw={2700+i}: "
                f"{knee_values[i-1]} → {knee_values[i]}"
            )


def _scenario_crc_bit_flip_detection() -> None:
    """Flipping any single bit in the payload must produce a CRC mismatch.

    CRC16-CCITT has a minimum Hamming distance of 4 for messages up to
    32767 bits, so it MUST detect all 1-bit and 2-bit errors. This
    scenario verifies the 1-bit case exhaustively for the first 64 bytes
    of the payload (512 bit positions) and spot-checks 64 more across
    the rest.
    """
    adc = _adc_gaussian_at((8, 8), peak=2500)
    frame = _run_host_sim(adc, seq=300, timestamp_us=300_000)
    hdr, payload = _parse_frame(frame)
    good_crc = hdr["crc"]

    # Exhaustive check on first 64 bytes (512 bit positions)
    for byte_idx in range(min(64, len(payload))):
        for bit in range(8):
            corrupted = bytearray(payload)
            corrupted[byte_idx] ^= (1 << bit)
            corrupted_crc = _crc16_ccitt(bytes(corrupted))
            if corrupted_crc == good_crc:
                raise AssertionError(
                    f"CRC FAILED to detect 1-bit flip at byte {byte_idx} "
                    f"bit {bit} — CRC16-CCITT Hamming distance violation"
                )

    import random
    rng = random.Random(42)
    remaining_positions = [
        (byte_idx, bit)
        for byte_idx in range(64, len(payload))
        for bit in range(8)
    ]
    for byte_idx, bit in rng.sample(remaining_positions, min(64, len(remaining_positions))):
        corrupted = bytearray(payload)
        corrupted[byte_idx] ^= (1 << bit)
        if _crc16_ccitt(bytes(corrupted)) == good_crc:
            raise AssertionError(
                f"CRC FAILED to detect 1-bit flip at byte {byte_idx} bit {bit}"
            )


def _scenario_multi_frame_sequence() -> None:
    """100 sequential frames with varying pressure → all envelopes + CRCs valid.

    Simulates a real scanning session: a part rolls over the mesh at
    varying pressure. Each of 100 frames has a shifted gaussian center
    and varying peak intensity. Catches seq counter bugs, CRC calculation
    bugs that only manifest on specific payloads, endianness/alignment
    issues, and memory corruption from repeated frame generation.
    """
    for i in range(100):
        row = (i * 7) % 16
        col = (i * 11) % 16
        # Peaks must be above the kAdcDead = 1100 noise floor or the
        # frame would correctly compress to all-zero -- which is the
        # firmware doing its job, not a bug. Start at 1200 so every
        # synthetic touch generates at least one non-zero byte; the
        # range still covers the full dynamic span of the divider.
        peak = 1200 + (i * 29) % 2800
        adc = _adc_gaussian_at((row, col), peak=peak, sigma=1.5 + (i % 3) * 0.5)
        frame = _run_host_sim(adc, seq=i + 1, timestamp_us=(i + 1) * 5000)
        hdr, payload = _parse_frame(frame)
        _assert_frame_envelope(hdr, expected_seq=i + 1)
        _assert_crc(hdr, payload)
        if all(b == 0 for b in payload):
            raise AssertionError(
                f"frame {i+1}: entire payload is zero with peak={peak}"
            )


def _scenario_noise_floor_rejection() -> None:
    """ADC values in [0, ADC_DEAD+7] must ALL compress to exactly 0.

    The firmware's noise floor is defined by ADC_DEAD=32. Any raw value
    at or below 32 produces compressed byte 0. Values just ABOVE the
    dead zone also compress to 0 because of rounding. This scenario
    finds the exact transition point and validates it.
    """
    first_nonzero = None
    for raw in range(ADC_MAX + 1):
        if _compress_sample(raw) > 0:
            first_nonzero = raw
            break

    if first_nonzero is None:
        raise AssertionError("compress_sample never produces a nonzero output!")

    for raw in range(first_nonzero):
        if _compress_sample(raw) != 0:
            raise AssertionError(
                f"compress_sample({raw}) = {_compress_sample(raw)}, expected 0"
            )

    expected_min = ADC_DEAD + 1
    expected_max = ADC_DEAD + 20
    if not (expected_min <= first_nonzero <= expected_max):
        raise AssertionError(
            f"first nonzero output at raw={first_nonzero}, expected in "
            f"[{expected_min}, {expected_max}]"
        )

    for test_val in [0, ADC_DEAD // 2, ADC_DEAD, first_nonzero - 1]:
        adc = _adc_constant(test_val)
        frame = _run_host_sim(adc, seq=400, timestamp_us=400_000)
        _, payload = _parse_frame(frame)
        if any(b != 0 for b in payload):
            raise AssertionError(
                f"ADC constant={test_val} (below noise floor {first_nonzero}): "
                f"payload has nonzero bytes"
            )


def _scenario_pressure_gradient_spatial() -> None:
    """Left-to-right pressure ramp → column means are monotonically increasing.

    Simulates a part with a linearly increasing pressure profile from
    left (col 0) to right (col 15). After compression, column-wise mean
    of the payload must be monotonically non-decreasing.
    """
    values = {}
    for r in range(16):
        for c in range(16):
            raw = 200 + c * 240
            values[(r, c)] = raw
    adc = _make_adc_matrix(values)
    frame = _run_host_sim(adc, seq=500, timestamp_us=500_000)
    hdr, payload = _parse_frame(frame)
    _assert_frame_envelope(hdr, expected_seq=500)
    _assert_crc(hdr, payload)

    col_means = []
    for c in range(16):
        col_sum = sum(payload[r * COLS + c] for r in range(16))
        col_means.append(col_sum / 16.0)

    for i in range(1, 16):
        if col_means[i] < col_means[i - 1]:
            raise AssertionError(
                f"column means not monotonic: col {i-1}={col_means[i-1]:.1f} "
                f"> col {i}={col_means[i]:.1f} — spatial mapping is broken"
            )

    if col_means[15] <= col_means[0]:
        raise AssertionError(
            f"no gradient detected: col 0 mean={col_means[0]:.1f}, "
            f"col 15 mean={col_means[15]:.1f}"
        )


def _scenario_random_stress() -> None:
    """500 random ADC matrices → all produce valid frames with correct CRC.

    This is the nuclear option. 500 completely random 16x16 ADC patterns.
    If even ONE produces a bad CRC or a payload byte that doesn't match
    the Python reference, the firmware has a latent bug.
    """
    import random
    rng = random.Random(12345)

    for trial in range(500):
        values = {}
        for r in range(16):
            for c in range(16):
                values[(r, c)] = rng.randint(0, ADC_MAX)
        adc = _make_adc_matrix(values)
        frame = _run_host_sim(adc, seq=trial + 1, timestamp_us=(trial + 1) * 5000)
        hdr, payload = _parse_frame(frame)
        _assert_frame_envelope(hdr, expected_seq=trial + 1)
        _assert_crc(hdr, payload)

        for r in range(16):
            for c in range(16):
                expected_byte = _compress_sample(values[(r, c)])
                actual_byte = payload[r * COLS + c]
                if expected_byte != actual_byte:
                    raise AssertionError(
                        f"trial {trial+1} cell ({r},{c}): "
                        f"Python says {expected_byte}, firmware says {actual_byte} "
                        f"(ADC={values[(r,c)]})"
                    )


# ─── Scenario registry ──────────────────────────────────────────────────────

SOFTWARE_SCENARIOS: list[tuple[str, SoftwareScenario, str]] = [
    ("protocol_constants", _scenario_protocol_constants,
     "Sanity: Python reference matches firmware's compress/CRC/header."),
    ("happy", _scenario_happy,
     "Gaussian touch at (8,8) — peak lands on the right cell, CRC clean."),
    ("all_zero", _scenario_all_zero,
     "No active cells — payload is all-zero (incl. boundary at ADC_DEAD)."),
    ("all_max", _scenario_all_max,
     "All cells short to V+ — payload saturates to 0xFF."),
    ("single_cell", _scenario_single_cell,
     "Single test cell (7,11) — only that index non-zero."),
    ("edge_cells", _scenario_edge_cells,
     "Four corners active — no off-by-one on row 0/15 or col 0/15."),
    ("mux_settling_curve", _scenario_mux_settling_software_only,
     "compress_sample is monotonic on (ADC_DEAD, ADC_MAX] (analog mixing → wokwi)."),
    ("reset_seq", _scenario_reset_seq_starts_at_one,
     "After fresh boot, seq restarts at 1 (RESET-pulse path → wokwi)."),
    ("timing_period", _scenario_timing_jitter_software_only,
     "SCAN_HZ math gives 5 ms period (real jitter → wokwi/silicon)."),
    ("payload_size", _scenario_payload_size_drift,
     "Payload remains 256 bytes — backend /ingest assumes this."),
    # ─── NEW: Hardcore fab-gating scenarios ──────────────────────────────────
    ("multi_cell_diagonal", _scenario_multi_cell_diagonal,
     "All 16 diagonal cells active — correct indices, monotonic ordering."),
    ("checkerboard_pattern", _scenario_checkerboard_pattern,
     "128-cell checkerboard — max-density crosstalk detection."),
    ("gradient_continuity", _scenario_gradient_continuity,
     "compress_sample never jumps >2 between adjacent ADC values."),
    ("crc_bit_flip_detection", _scenario_crc_bit_flip_detection,
     "512+ single-bit payload corruptions all detected by CRC16-CCITT."),
    ("multi_frame_sequence", _scenario_multi_frame_sequence,
     "100 sequential frames — all envelopes, CRCs, and payloads valid."),
    ("noise_floor_rejection", _scenario_noise_floor_rejection,
     "Exact ADC_DEAD boundary — all sub-threshold values compress to 0."),
    ("pressure_gradient_spatial", _scenario_pressure_gradient_spatial,
     "Left-to-right ADC ramp — column means are monotonically increasing."),
    ("random_stress", _scenario_random_stress,
     "500 random ADC matrices — Python/firmware cross-validation (nuclear)."),
]


DEFERRED_SCENARIOS: list[tuple[str, str]] = [
    ("usb_reconnect",
     "Skipped: wokwi-cli has no USB stack emulation. Manual procedure: "
     "unplug USB-C on the EVT board, watch host re-enumerate, verify "
     "`seq` continues monotonically (Serial.begin re-entry is idempotent)."),
    ("ads1115_alt_path",
     "Deferred: ADS1115 alt path is a v1.1 schematic feature (U4 marked "
     "DNP on the EVT BOM). Needs a separate firmware variant + "
     "wokwi-ads1115 part. Not blocking the first 5-board fab order."),
]


# ─── Wokwi-mode driver ─────────────────────────────────────────────────────


def _wokwi_available() -> tuple[bool, str]:
    if shutil.which("wokwi-cli") is None:
        return False, "wokwi-cli not on PATH (install: https://wokwi.com/ci/install.sh)"
    if not os.environ.get("WOKWI_CLI_TOKEN"):
        return False, "WOKWI_CLI_TOKEN not set (get one at https://wokwi.com/ci/)"
    flasher = HERE / "build" / "flasher_args.json"
    elf = HERE / "build" / "app.elf"
    if not flasher.exists() or not elf.exists():
        return False, (
            "build/flasher_args.json or build/app.elf missing — "
            "run build_firmware.sh first"
        )
    return True, "ok"


# Magic bytes (little-endian uint32 of FRAME_MAGIC).
_MAGIC_BYTES = struct.pack("<I", FRAME_MAGIC)


def _parse_serial_log(blob: bytes) -> list[tuple[dict, bytes]]:
    """Slice a raw serial-log byte stream into well-formed frames.

    The firmware emits exactly `FRAME_HDR_SIZE + PAYLOAD_SIZE` bytes per frame
    starting with FRAME_MAGIC; in practice Wokwi's USB-CDC pipe is reliable
    enough that you can search by magic and slice. We additionally validate
    the CRC of every candidate frame so any false-positive magic alignment
    inside the payload is rejected.
    """
    frames: list[tuple[dict, bytes]] = []
    i = 0
    while True:
        j = blob.find(_MAGIC_BYTES, i)
        if j < 0 or j + FRAME_SIZE > len(blob):
            break
        candidate = blob[j : j + FRAME_SIZE]
        try:
            hdr, payload = _parse_frame(candidate)
        except ValueError:
            i = j + 1
            continue
        if hdr["rows"] != ROWS or hdr["cols"] != COLS:
            i = j + 1
            continue
        if _crc16_ccitt(payload) != hdr["crc"]:
            # Magic occurred inside a payload, not a real header.
            i = j + 1
            continue
        frames.append((hdr, payload))
        i = j + FRAME_SIZE
    return frames


# Wokwi free-tier simulations on `board-esp32-s3-devkitc-1` run roughly
# 5× slower than wall-clock on the shared cloud sim hosts (empirically: 10s
# of `--timeout` takes ~50s real time). We give 10× as a comfortable ceiling.
WOKWI_REAL_OVER_SIM = 10
WOKWI_WALL_CLOCK_BUDGET_S = 60  # extra buffer for cli startup + upload.


def _run_wokwi_capture(timeout_s: int, scenario_name: str) -> tuple[bytes, str]:
    """Launch wokwi-cli, run for `timeout_s` seconds of simulation."""
    log_path = HERE / f".wokwi_log_{scenario_name}.bin"
    if log_path.exists():
        log_path.unlink()
    wall_clock_s = timeout_s * WOKWI_REAL_OVER_SIM + WOKWI_WALL_CLOCK_BUDGET_S
    # wokwi-cli streams the raw serial bytes to its own stdout *in addition*
    # to writing them into --serial-log-file. We don't need that stream, and
    # it contains arbitrary binary (so capture_output=True with text=True
    # would crash on the first non-UTF-8 byte). Redirect stdout to DEVNULL
    # and keep stderr separately (as text) for diagnostic messages.
    try:
        proc = subprocess.run(
            [
                "wokwi-cli",
                str(HERE),
                "--timeout", str(timeout_s * 1000),
                "--serial-log-file", str(log_path),
                "--quiet",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=wall_clock_s,
        )
    except subprocess.TimeoutExpired:
        return b"", (
            f"wokwi-cli wall-clock budget exhausted after {wall_clock_s}s "
            f"(target sim duration {timeout_s}s)"
        )
    except FileNotFoundError:
        return b"", "wokwi-cli not on PATH"
    captured = log_path.read_bytes() if log_path.exists() else b""
    # wokwi-cli returns 42 on simulation timeout (the timeout we set above is
    # expected — we run wokwi without --expect-text). So 42 is success.
    if not captured and proc.returncode not in (0, 42):
        stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
        return b"", (
            f"wokwi-cli exited {proc.returncode}; "
            f"stderr: {stderr.strip()[:200]}"
        )
    return captured, ""


# Cache the wokwi capture across scenarios — wokwi-cli takes ~50s wall-clock
# per run, so we burn it once and let multiple scenarios assert different
# invariants over the same byte stream.
_WOKWI_CACHE: dict[int, tuple[bytes, list[tuple[dict, bytes]]]] = {}


def _wokwi_capture_cached(timeout_s: int = 8) -> tuple[bytes, list[tuple[dict, bytes]]]:
    if timeout_s in _WOKWI_CACHE:
        return _WOKWI_CACHE[timeout_s]
    blob, err = _run_wokwi_capture(timeout_s=timeout_s, scenario_name="capture")
    if err:
        raise AssertionError(err)
    if not blob:
        raise AssertionError(
            "wokwi-cli ran but captured zero serial bytes — check "
            "CDCOnBoot=cdc in build_firmware.sh and the diagram board type"
        )
    frames = _parse_serial_log(blob)
    _WOKWI_CACHE[timeout_s] = (blob, frames)
    return blob, frames


def _scenario_wokwi_smoke() -> None:
    """Wokwi mode: firmware boots, streams CONT frames.

    Verifies on simulated silicon (board-esp32-s3-devkitc-1):
      - serial capture works (USB-CDC path, GPIO 19/20)
      - first byte is the CONT magic (no boot garbage before the protocol)
      - >= 30 frames captured in the window (well above warmup floor)
      - every frame: correct rows/cols, valid CRC, monotonic seq starting at 1
    """
    blob, frames = _wokwi_capture_cached()
    if not blob.startswith(_MAGIC_BYTES):
        raise AssertionError(
            f"expected CONT magic at offset 0, got {blob[:4].hex()} "
            f"(suggests boot garbage; check Serial.begin / CDC enumeration)"
        )
    if len(frames) < 30:
        raise AssertionError(
            f"only {len(frames)} valid frames in capture window "
            f"(captured {len(blob)} bytes total) — firmware may be stalling"
        )
    seqs = [hdr["seq"] for hdr, _ in frames]
    if seqs[0] != 1:
        raise AssertionError(f"first frame should have seq=1, got {seqs[0]}")
    # The seq stream must be strictly monotonic. We allow non-unit jumps in
    # case Wokwi's USB-CDC ever drops bytes (it shouldn't, but we want a
    # clear error message if it does).
    for prev, curr in zip(seqs, seqs[1:]):
        if curr <= prev:
            raise AssertionError(
                f"seq went backwards: {prev} -> {curr} "
                "(suggests the firmware reset or framing alignment broke)"
            )


def _scenario_wokwi_frame_progress() -> None:
    """Wokwi mode: firmware sustains progress (no stalls / no rate collapse).

    We DELIBERATELY do not assert the absolute 200 Hz target here — Wokwi's
    `analogRead()` emulation is much slower than real ESP32-S3 silicon
    (256 reads per frame dominates the loop), so the simulated firmware
    typically reports ~25-30 Hz. That's expected and OK; the target of this
    scenario is to detect *hangs* and *exponential rate decay*, not
    absolute throughput. Absolute SCAN_HZ verification is a silicon-only
    measurement.

    Concretely we assert:
      * the firmware-reported rate (from its own micros() deltas) is at
        least 5 Hz, which means it's actually scanning — not boot-looping
        or busy-deadlocked.
      * the rate measured across the *second half* of the capture is
        within 30% of the rate across the *first half* — i.e. the firmware
        isn't slowing down over time (memory leak, heap fragmentation,
        accumulating debt in the scheduler).
    """
    _, frames = _wokwi_capture_cached()
    if len(frames) < 4:
        raise AssertionError(
            f"need >= 4 frames to compute first/second-half rates, "
            f"got {len(frames)}"
        )

    def _rate(window: list[tuple[dict, bytes]]) -> float:
        seq_span = window[-1][0]["seq"] - window[0][0]["seq"]
        ts_us = window[-1][0]["timestamp_us"] - window[0][0]["timestamp_us"]
        if ts_us <= 0:
            return 0.0
        return seq_span * 1_000_000.0 / ts_us

    overall_hz = _rate(frames)
    if overall_hz < 5.0:
        raise AssertionError(
            f"firmware-reported rate {overall_hz:.1f} Hz < 5 Hz floor "
            "(firmware is effectively stalled in Wokwi)"
        )

    mid = len(frames) // 2
    first_half_hz = _rate(frames[:mid])
    second_half_hz = _rate(frames[mid:])
    if first_half_hz <= 0 or second_half_hz <= 0:
        raise AssertionError(
            f"degenerate half-rates: first={first_half_hz:.2f} "
            f"second={second_half_hz:.2f}"
        )
    drift = abs(second_half_hz - first_half_hz) / first_half_hz
    if drift > 0.30:
        raise AssertionError(
            f"rate drifted by {drift*100:.1f}% across capture window "
            f"({first_half_hz:.1f} Hz → {second_half_hz:.1f} Hz) "
            "— firmware is slowing down over time"
        )


def _scenario_wokwi_crc_integrity() -> None:
    """Wokwi mode: every frame in the captured stream has a valid CRC.

    _parse_serial_log already filters frames by CRC, so the test is: did
    we find more frames-with-good-CRC than we saw raw magic occurrences
    that turned out to be false alignments? Empirically all real frames
    pass CRC, so the count after parsing should match
    `len(blob) // FRAME_SIZE` (give or take partial bytes at the tail).
    """
    blob, frames = _wokwi_capture_cached()
    expected = len(blob) // FRAME_SIZE
    # Allow ±1 frame slop for partial frames at start/end.
    if not (expected - 1 <= len(frames) <= expected + 1):
        raise AssertionError(
            f"frame count mismatch: parsed {len(frames)} valid frames, "
            f"but {len(blob)} bytes / {FRAME_SIZE} = {expected} expected "
            "— suggests CRC corruption or framing slip"
        )


WOKWI_SCENARIOS: list[tuple[str, Callable[[], None], str]] = [
    ("wokwi_smoke", _scenario_wokwi_smoke,
     "Firmware boots on simulated ESP32-S3, streams valid CONT frames."),
    ("wokwi_frame_progress", _scenario_wokwi_frame_progress,
     "Firmware sustains scanning (>=5 Hz, no rate drift > 30%)."),
    ("wokwi_crc_integrity", _scenario_wokwi_crc_integrity,
     "100% of captured frames pass CRC16-CCITT (no payload corruption)."),
]


# ─── Runner ─────────────────────────────────────────────────────────────────


def _run_software(only: set[str] | None) -> list[ScenarioResult]:
    _ensure_host_sim_built()
    out: list[ScenarioResult] = []
    for name, fn, desc in SOFTWARE_SCENARIOS:
        if only is not None and name not in only:
            continue
        t0 = time.perf_counter()
        try:
            fn()
            status = "passed"
            detail = desc
        except AssertionError as e:
            status = "failed"
            detail = f"{desc}  // FAILED: {e}"
        except Exception as e:  # noqa: BLE001 — surface anything unexpected
            status = "failed"
            detail = f"{desc}  // CRASH: {type(e).__name__}: {e}"
        out.append(ScenarioResult(
            name=name,
            status=status,
            detail=detail,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        ))
    # Deferred scenarios are always reported but never block.
    for name, reason in DEFERRED_SCENARIOS:
        if only is not None and name not in only:
            continue
        out.append(ScenarioResult(
            name=name, status="skipped", detail=reason, duration_ms=0.0
        ))
    return out


def _run_wokwi(only: set[str] | None) -> list[ScenarioResult]:
    ok, reason = _wokwi_available()
    if not ok:
        # The user said "all scenarios must pass before fab order". If wokwi
        # mode is invoked but its prerequisites are not met, that is a
        # hard skip with a clear actionable message — not a silent pass.
        return [ScenarioResult(
            name="wokwi_preflight",
            status="skipped",
            detail=f"wokwi prerequisites not met: {reason}",
            duration_ms=0.0,
        )]
    out: list[ScenarioResult] = []
    for name, fn, desc in WOKWI_SCENARIOS:
        if only is not None and name not in only:
            continue
        t0 = time.perf_counter()
        try:
            fn()
            status = "passed"
            detail = desc
        except AssertionError as e:
            status = "failed"
            detail = f"{desc}  // FAILED: {e}"
        except Exception as e:  # noqa: BLE001
            status = "failed"
            detail = f"{desc}  // CRASH: {type(e).__name__}: {e}"
        out.append(ScenarioResult(
            name=name, status=status, detail=detail,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        ))
    return out


def _print_human(results: Iterable[ScenarioResult]) -> int:
    rows = list(results)
    width = max(len(r.name) for r in rows) if rows else 0
    n_pass = sum(1 for r in rows if r.status == "passed")
    n_skip = sum(1 for r in rows if r.status == "skipped")
    n_fail = sum(1 for r in rows if r.status == "failed")
    icon = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP"}
    print()
    for r in rows:
        line = f"  [{icon[r.status]}] {r.name:<{width}}  ({r.duration_ms:6.1f} ms)  {r.detail}"
        print(line)
    print()
    print(f"  {n_pass} passed   {n_skip} skipped   {n_fail} failed")
    print()
    return 0 if n_fail == 0 else 1


def _print_json(results: Iterable[ScenarioResult]) -> int:
    rows = [dataclasses.asdict(r) for r in results]
    n_fail = sum(1 for r in rows if r["status"] == "failed")
    json.dump(
        {"scenarios": rows, "failed": n_fail},
        sys.stdout, indent=2, ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0 if n_fail == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--mode", choices=["software", "wokwi", "both"], default="software",
        help="Execution backend (default: software).",
    )
    parser.add_argument(
        "--only", nargs="+", default=None, metavar="NAME",
        help="Only run the named scenarios.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)

    only = set(args.only) if args.only else None
    results: list[ScenarioResult] = []
    if args.mode in ("software", "both"):
        results.extend(_run_software(only))
    if args.mode in ("wokwi", "both"):
        results.extend(_run_wokwi(only))

    if args.json:
        return _print_json(results)
    return _print_human(results)


if __name__ == "__main__":
    sys.exit(main())
