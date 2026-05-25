"""Drive the existing host_sim/scan_one_frame binary with reality-adjusted
ADC matrices and verify the wire-format frames are well-formed.

Three scenarios:

  A. "no_press"  -- every cell un-pressed (R_cell=30 kohm) => ADC near 1000
                    after the divider with R_mux=320 ohm clone-typ.
                    Payload should be mostly zeros after `compress_sample`
                    (because raw ~1000 minus kAdcDead=1024 returns 0).

  B. "centre_press" -- Gaussian bump centred at (7, 9) with peak R_cell=2k.
                       Should produce a high-amplitude blob in the payload
                       and CRC must validate.

  C. "edge_press"   -- only one corner cell at R_cell=500 ohm (worst pressure).
                       Tests that the saturation handling in compress_sample
                       clamps to 255.

We rebuild the host_sim/scan_one_frame binary first, then pipe matrices
through it and parse the resulting bytes.
"""

from __future__ import annotations

import math
import random
import struct
import subprocess
from pathlib import Path

from .findings import Finding


ROWS = COLS = 16
HEADER_LEN = 20
PAYLOAD_LEN = ROWS * COLS
FRAME_LEN = HEADER_LEN + PAYLOAD_LEN
MAGIC = 0x434F4E54   # 'CONT'


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def v_adc(r_cell: float, r30: float = 10_000, r_mux_each: float = 320, vcc: float = 3.3) -> float:
    return vcc * r30 / (r30 + r_cell + 2 * r_mux_each)


def adc_counts(v: float, v_ref: float = 3.3, bits: int = 12) -> int:
    counts = int(round((v / v_ref) * ((1 << bits) - 1)))
    return max(0, min((1 << bits) - 1, counts))


def make_matrix_no_press(rng: random.Random) -> bytes:
    out = bytearray()
    for r in range(ROWS):
        for c in range(COLS):
            r_cell = 30_000 * (1 + rng.uniform(-0.05, 0.05))
            v = v_adc(r_cell) + rng.gauss(0, 0.001)
            out += struct.pack("<H", adc_counts(v))
    return bytes(out)


def make_matrix_centre_press(rng: random.Random) -> bytes:
    out = bytearray()
    for r in range(ROWS):
        for c in range(COLS):
            d = math.hypot(r - 7, c - 9)
            bump = math.exp(-(d ** 2) / 6.0)
            r_cell = 30_000 - 28_000 * bump
            r_cell *= (1 + rng.uniform(-0.05, 0.05))
            v = v_adc(r_cell) + rng.gauss(0, 0.001)
            out += struct.pack("<H", adc_counts(v))
    return bytes(out)


def make_matrix_edge_press(rng: random.Random) -> bytes:
    out = bytearray()
    for r in range(ROWS):
        for c in range(COLS):
            if (r, c) == (15, 15):
                r_cell = 500.0
            else:
                r_cell = 30_000.0
            v = v_adc(r_cell)
            out += struct.pack("<H", adc_counts(v))
    return bytes(out)


def run_scan(binary: Path, matrix: bytes, seq: int = 1, ts_us: int = 42) -> bytes:
    proc = subprocess.run(
        [str(binary), "--seq", str(seq), "--timestamp", str(ts_us)],
        input=matrix, capture_output=True, check=True, timeout=10,
    )
    return proc.stdout


def parse_frame(buf: bytes) -> dict:
    if len(buf) != FRAME_LEN:
        raise ValueError(f"frame length {len(buf)} != expected {FRAME_LEN}")
    hdr = struct.unpack("<IHHIIHH", buf[:HEADER_LEN])
    magic, rows, cols, seq, ts, crc, pad = hdr
    payload = buf[HEADER_LEN:]
    return dict(
        magic=magic, rows=rows, cols=cols, seq=seq, ts=ts,
        crc=crc, pad=pad, payload=payload, computed_crc=crc16_ccitt(payload),
    )


def analyse(repo_root: Path) -> tuple[list[dict], list[Finding]]:
    findings: list[Finding] = []
    runs: list[dict] = []

    host_sim_dir = repo_root / "firmware/tactile_scanner_esp32/wokwi/host_sim"
    binary = host_sim_dir / "scan_one_frame"

    # Build it (idempotent)
    try:
        subprocess.run(
            ["make", "-C", str(host_sim_dir)],
            capture_output=True, check=True, timeout=60,
        )
    except subprocess.CalledProcessError as e:
        findings.append(Finding(
            module="software_sim",
            code="SIM-BUILD-FAIL",
            title="Could not build host_sim/scan_one_frame",
            severity=4,
            detail=(
                "Building the host-mode scanner simulator failed. The CI workflow "
                "depends on this binary, so the existing software-mode pre-flight "
                "is also broken. stderr:\n\n```\n" + e.stderr.decode("utf-8", "ignore") + "\n```"
            ),
            refs=["firmware/.../host_sim/Makefile"],
        ))
        return runs, findings

    if not binary.exists():
        findings.append(Finding(
            module="software_sim",
            code="SIM-BINARY-MISSING",
            title="host_sim/scan_one_frame not present after make",
            severity=4,
            detail="`make` finished without producing the binary.",
            refs=["firmware/.../host_sim"],
        ))
        return runs, findings

    rng = random.Random(2026)
    scenarios = [
        ("no_press", make_matrix_no_press(rng)),
        ("centre_press", make_matrix_centre_press(rng)),
        ("edge_press", make_matrix_edge_press(rng)),
    ]

    for name, matrix in scenarios:
        try:
            out = run_scan(binary, matrix, seq=1, ts_us=42)
        except subprocess.CalledProcessError as e:
            findings.append(Finding(
                module="software_sim",
                code="SIM-RUN-FAIL",
                title=f"scan_one_frame failed on `{name}`",
                severity=4,
                detail=(
                    f"scan_one_frame exited non-zero on reality-adjusted matrix "
                    f"`{name}`. stderr:\n\n```\n"
                    + e.stderr.decode("utf-8", "ignore") + "\n```"
                ),
                refs=[name],
            ))
            continue

        frame = parse_frame(out)
        ok_magic = frame["magic"] == MAGIC
        ok_dim = (frame["rows"], frame["cols"]) == (16, 16)
        ok_crc = frame["crc"] == frame["computed_crc"]
        max_payload = max(frame["payload"])
        nonzero = sum(1 for b in frame["payload"] if b != 0)
        runs.append(dict(
            scenario=name, magic_ok=ok_magic, dim_ok=ok_dim, crc_ok=ok_crc,
            max_payload=max_payload, nonzero_cells=nonzero,
        ))

        if not (ok_magic and ok_dim and ok_crc):
            findings.append(Finding(
                module="software_sim",
                code="SIM-FRAME-INVALID",
                title=f"Reality matrix `{name}` produced invalid frame",
                severity=4,
                detail=(
                    f"magic_ok={ok_magic}, dim_ok={ok_dim}, crc_ok={ok_crc}. "
                    f"Header bytes: {out[:20].hex()}"
                ),
                refs=[name],
            ))

        # Expectations
        if name == "no_press" and nonzero > 5:
            findings.append(Finding(
                module="software_sim",
                code="SIM-FALSE-POSITIVE",
                title=f"`no_press` matrix yielded {nonzero} non-zero cells",
                severity=2,
                detail=(
                    "With every cell at the un-pressed value (~R_cell=30 kohm), the "
                    "compressed payload should be near-zero everywhere. Seeing "
                    f"{nonzero} non-zero cells means the noise floor / kAdcDead "
                    "threshold is too low for the real divider output "
                    "(~1000 counts with R_mux=320 ohm). The firmware will report "
                    "phantom touches on an unloaded mesh. **Recommend raising "
                    "kAdcDead to ~1024 counts (which fully zeroes out the "
                    "no-press baseline) or, for v2, switching to a runtime "
                    "per-cell baseline subtracted on the first scan.**"
                ),
                refs=["scanner_frame.h"],
            ))
        if name == "edge_press" and max_payload < 200:
            findings.append(Finding(
                module="software_sim",
                code="SIM-WEAK-SATURATION",
                title=f"`edge_press` peak payload only {max_payload}/255",
                severity=2,
                detail=(
                    "Hardest pressure (R_cell=500 ohm, one corner cell) produced "
                    f"peak payload {max_payload} out of 255. With R_mux=320 ohm "
                    "the ADC saturation point shifts up; the dynamic-range loss is "
                    "real but not fatal. Calibration must compensate."
                ),
                refs=["scanner_frame.h"],
            ))

    return runs, findings
