"""Print the host facts that matter for the Isaac Sim handoff."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path


def _run(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"unavailable: {exc}"


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    print(f"repo: {root}")
    print(f"python: {sys.version.split()[0]} ({sys.executable})")
    print(f"platform: {platform.platform()}")
    print(f"nvidia-smi: {shutil.which('nvidia-smi') or 'not found'}")
    if shutil.which("nvidia-smi"):
        print(
            _run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader",
                ]
            )
        )

    try:
        from sim import specs

        print(
            "mesh: "
            f"{specs.MESH_ROWS}x{specs.MESH_COLS} @ {specs.CELL_PITCH * 1000:.1f} mm"
        )
        print(
            "belt: "
            f"{specs.BELT_WIDTH * 1000:.0f} mm x {specs.BELT_LENGTH:.2f} m "
            f"@ {specs.BELT_SPEED:.2f} m/s"
        )
    except Exception as exc:
        print(f"spec import: unavailable: {exc}")


if __name__ == "__main__":
    main()
