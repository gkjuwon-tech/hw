"""On-device telemetry: CPU/GPU load, board temps, memory, power draw.

On a real Jetson Orin Nano the canonical source is ``tegrastats``, a userland
sampler shipped by NVIDIA L4T. We shell out to it (one-shot mode) and parse
its single line of output. On non-Jetson hosts the parser still works against
the synthesized output produced by :func:`stub_tegrastats_line`, which lets us
run the agent on a dev laptop for end-to-end validation.

This module is intentionally small and dependency-free so it can be imported
inside a tight loop without dragging in numpy / scipy / nvidia-ml-py.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Sample tegrastats output (Orin Nano, JetPack 5.1):
#
#   RAM 2123/7775MB (lfb 4x4MB) SWAP 0/3887MB (cached 0MB) CPU [16%@1190,...]
#   GR3D_FREQ 12%@624 cpu@52.5C soc0@49.0C soc1@49.5C soc2@49.5C tj@52.5C VDD_IN 5310mW/5310mW

_RAM_RE = re.compile(r"RAM\s+(\d+)/(\d+)MB")
_CPU_RE = re.compile(r"CPU\s*\[(?P<inner>[^\]]+)\]")
_GPU_RE = re.compile(r"GR3D_FREQ\s+(\d+)%")
_TEMP_RE = re.compile(r"(?P<name>[A-Za-z0-9_]+)@(?P<v>-?\d+(?:\.\d+)?)C")
_POWER_RE = re.compile(r"VDD_IN\s+(\d+)mW")


@dataclass(frozen=True)
class TegraSnapshot:
    """One parsed tegrastats line."""

    cpu_pct: float
    gpu_pct: float
    cpu_temp_c: float
    gpu_temp_c: float
    ram_used_mb: int
    ram_total_mb: int
    power_mw: int

    @classmethod
    def empty(cls) -> TegraSnapshot:
        return cls(0.0, 0.0, 0.0, 0.0, 0, 0, 0)


def parse_tegrastats(line: str) -> TegraSnapshot:
    """Parse one tegrastats line. Missing fields default to 0 — never raises."""
    ram_used = 0
    ram_total = 0
    cpu_pct = 0.0
    gpu_pct = 0.0
    cpu_temp = 0.0
    gpu_temp = 0.0
    power = 0

    if m := _RAM_RE.search(line):
        ram_used = int(m.group(1))
        ram_total = int(m.group(2))

    if m := _CPU_RE.search(line):
        # The inner format is e.g. "16%@1190,12%@1190,8%@1190,4%@1190" — one
        # entry per core. We average the percentages.
        percents: list[float] = []
        for chunk in m.group("inner").split(","):
            chunk = chunk.strip()
            if not chunk or chunk in {"off", "OFF"}:
                continue
            mm = re.match(r"(\d+)%", chunk)
            if mm is not None:
                percents.append(float(mm.group(1)))
        if percents:
            cpu_pct = sum(percents) / len(percents)

    if m := _GPU_RE.search(line):
        gpu_pct = float(m.group(1))

    for m in _TEMP_RE.finditer(line):
        name = m.group("name").lower()
        v = float(m.group("v"))
        if name in {"cpu", "cpu0"}:
            cpu_temp = v
        elif name in {"gpu", "tj"}:
            gpu_temp = max(gpu_temp, v)
        elif name.startswith("soc"):
            # SoC zones are a reasonable proxy when no explicit gpu zone exists.
            gpu_temp = max(gpu_temp, v)

    if m := _POWER_RE.search(line):
        power = int(m.group(1))

    return TegraSnapshot(
        cpu_pct=cpu_pct,
        gpu_pct=gpu_pct,
        cpu_temp_c=cpu_temp,
        gpu_temp_c=gpu_temp,
        ram_used_mb=ram_used,
        ram_total_mb=ram_total,
        power_mw=power,
    )


def sample_tegrastats(timeout_s: float = 1.5) -> TegraSnapshot:
    """Run ``tegrastats --interval 100`` for one shot and parse the first line.

    Returns :meth:`TegraSnapshot.empty` if tegrastats isn't on PATH (i.e. we
    are running on a developer laptop). Callers should treat the empty
    snapshot as "no hardware metrics available" and the heartbeat will
    fall back to zero-valued fields, which the cloud renders as "—".
    """
    if shutil.which("tegrastats") is None:
        return _fallback_metrics()
    try:
        proc = subprocess.run(  # noqa: S603
            ["tegrastats", "--interval", "100", "--count", "1"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return _fallback_metrics()
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        return _fallback_metrics()
    return parse_tegrastats(line[0])


def _fallback_metrics() -> TegraSnapshot:
    """Best-effort host metrics on non-Jetson Linux/macOS dev hosts."""
    cpu_pct = _read_loadavg_pct()
    ram_used, ram_total = _read_meminfo_mb()
    cpu_temp = _read_thermal_zone_c()
    return TegraSnapshot(
        cpu_pct=cpu_pct,
        gpu_pct=0.0,
        cpu_temp_c=cpu_temp,
        gpu_temp_c=cpu_temp,
        ram_used_mb=ram_used,
        ram_total_mb=ram_total,
        power_mw=0,
    )


def _read_loadavg_pct() -> float:
    p = Path("/proc/loadavg")
    if not p.exists():
        return 0.0
    try:
        first = p.read_text().split()[0]
        return min(100.0, float(first) * 100.0 / max(1, _cpu_count()))
    except (OSError, ValueError):
        return 0.0


def _cpu_count() -> int:
    try:
        import os

        return os.cpu_count() or 1
    except Exception:  # noqa: BLE001
        return 1


def _read_meminfo_mb() -> tuple[int, int]:
    p = Path("/proc/meminfo")
    if not p.exists():
        return (0, 0)
    try:
        total_kb = 0
        avail_kb = 0
        for line in p.read_text().splitlines():
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail_kb = int(line.split()[1])
        if total_kb <= 0:
            return (0, 0)
        used_kb = max(0, total_kb - avail_kb)
        return (used_kb // 1024, total_kb // 1024)
    except (OSError, ValueError):
        return (0, 0)


def _read_thermal_zone_c() -> float:
    for i in range(8):
        p = Path(f"/sys/class/thermal/thermal_zone{i}/temp")
        if p.exists():
            try:
                return int(p.read_text().strip()) / 1000.0
            except (OSError, ValueError):
                continue
    return 0.0


def stub_tegrastats_line(
    *,
    cpu_pct: float = 12.0,
    gpu_pct: float = 8.0,
    cpu_temp_c: float = 48.5,
    gpu_temp_c: float = 51.0,
    ram_used_mb: int = 2100,
    ram_total_mb: int = 7775,
    power_mw: int = 4_900,
) -> str:
    """Build a tegrastats-shaped line for tests / dev simulation."""
    return (
        f"RAM {ram_used_mb}/{ram_total_mb}MB (lfb 4x4MB) "
        f"SWAP 0/3887MB (cached 0MB) "
        f"CPU [{int(cpu_pct)}%@1190,{int(cpu_pct)}%@1190,{int(cpu_pct)}%@1190,{int(cpu_pct)}%@1190] "
        f"GR3D_FREQ {int(gpu_pct)}%@624 "
        f"cpu@{cpu_temp_c}C tj@{gpu_temp_c}C "
        f"VDD_IN {power_mw}mW/{power_mw}mW"
    )


def read_serial_number() -> str:
    """Read the NVIDIA module serial from device-tree, or empty if absent."""
    p = Path("/proc/device-tree/serial-number")
    if not p.exists():
        return ""
    try:
        return p.read_bytes().rstrip(b"\x00").decode("ascii", errors="replace")
    except OSError:
        return ""
