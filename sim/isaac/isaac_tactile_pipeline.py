"""Isaac Sim entrypoint for the tactile pill twin.

This file is intentionally import-light at module import time so normal repo
checks can run without Isaac installed. The actual Isaac imports happen only
inside `main()`.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trays", type=int, default=3125, help="3125 trays = 50k pills")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("sim/dataset/tactile_pills_isaac.npz"),
        help="Output .npz path matching sim/generate_dataset.py",
    )
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--render-png", type=Path, default=Path("sim/isaac/isaac_twin.png"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        from isaacsim import SimulationApp
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Isaac Sim is not installed. Run `bash sim/isaac/install_isaac_pip.sh` "
            "on the RTX pod first."
        ) from exc

    app = SimulationApp({"headless": args.headless})
    try:
        run_pipeline(args)
    finally:
        app.close()


def run_pipeline(args: argparse.Namespace) -> None:
    """Build scene, simulate trays, save dataset.

    TODO for the Isaac implementation:
      * Build the 350 mm belt + 16x16 spring taxel array from sim.specs.
      * Use PhysX joint drives/contact reports for normal force per taxel.
      * Spawn 4x4 tablet cylinders with reduced mass for void pills.
      * Save frames/pill_pressure/pill_label/pill_centers exactly like MuJoCo.
      * Save an RTX render to args.render_png.
    """

    raise NotImplementedError(
        "Isaac scene construction is the next step; see sim/isaac/README.md."
    )


if __name__ == "__main__":
    main()
