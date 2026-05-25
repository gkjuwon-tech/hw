"""Generate a reality-adjusted Wokwi `diagram.json`.

The existing `firmware/.../wokwi/diagram.json` is a happy-path test bench
that models:

  * an idealised 74HC4067 (R_on=0)
  * 5 of 256 cells
  * `psramType="none"` and `flashSize="4"` (board has N8R8 + 8 MB)

This generator emits `diagram.reality.json` next to the original. It
models the same circuit but with the Shenzhen reality adjustments:

  * series resistance for each MUX channel = R_on_clone_typ = 320 ohm
    (inserted explicitly as a resistor in series with each cell, so a
    stock wokwi-74hc4067 ideal model still behaves like the real part)
  * 256 cells, with a representative pressure distribution
  * board attrs psramType=opi, flashSize=8 to match WROOM-1-N8R8
  * decoupling caps with DC-bias-derated values

The resulting diagram is large (~250 kB of JSON), which is fine for
wokwi-cli but unfriendly for the desktop editor. It is intended for
CI / automated runs, not for interactive editing.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path


# --- pressure distribution model ----------------------------------------
# A real test pad presses the mesh in a Gaussian bump centred somewhere
# on the 16x16 grid. R_cell varies from ~30 kohm un-pressed to ~2 kohm
# fully pressed. We seed the RNG so the diagram is reproducible.

def cell_resistance(row: int, col: int, *, rng: random.Random) -> int:
    centre_r = 7.5
    centre_c = 9.5
    d = math.hypot(row - centre_r, col - centre_c)
    bump = math.exp(-(d ** 2) / 8.0)  # 1 at centre, ~0.05 at the corners
    r_kohm = 30 - 28 * bump   # 30 kohm un-pressed, 2 kohm fully pressed
    # add 5% spread per cell (mesh weave variation)
    r_kohm *= (1 + rng.uniform(-0.05, 0.05))
    return max(500, int(r_kohm * 1000))


def build_diagram(out_path: Path, *, r_mux_each: int = 320, seed: int = 4711) -> dict:
    rng = random.Random(seed)
    parts: list[dict] = []
    connections: list[list] = []

    # Board with the real WROOM-1-N8R8 attrs (within wokwi's vocabulary)
    parts.append({
        "type": "board-esp32-s3-devkitc-1",
        "id": "esp",
        "top": 0, "left": 0,
        "attrs": {"psramType": "opi", "flashSize": "8"},   # match real module
    })
    parts.append({
        "type": "chip-74hc4067",
        "id": "row_mux",
        "top": 300, "left": -800,
        "attrs": {},
    })
    parts.append({
        "type": "chip-74hc4067",
        "id": "col_mux",
        "top": 300, "left": 800,
        "attrs": {},
    })
    # 10k pull-down on col_mux SIG
    parts.append({
        "type": "wokwi-resistor",
        "id": "rpd",
        "top": 500, "left": 1000,
        "attrs": {"value": "10000"},
    })
    # 100 nF decoupling, derated for DC bias (~70 nF effective)
    parts.append({
        "type": "wokwi-capacitor",
        "id": "c_dec_row",
        "top": 200, "left": -800,
        "attrs": {"value": "0.07u"},
    })
    parts.append({
        "type": "wokwi-capacitor",
        "id": "c_dec_col",
        "top": 200, "left": 800,
        "attrs": {"value": "0.07u"},
    })
    # 10 uF bulk, derated to 5 uF effective
    parts.append({
        "type": "wokwi-capacitor",
        "id": "c_bulk",
        "top": 100, "left": 0,
        "attrs": {"value": "5u"},
    })

    # Power + select wiring
    static_conns = [
        ["esp:GND.1", "row_mux:GND", "black", []],
        ["esp:GND.1", "col_mux:GND", "black", []],
        ["esp:3V3.1", "row_mux:VCC", "red", []],
        ["esp:3V3.1", "col_mux:VCC", "red", []],
        ["esp:GND.1", "row_mux:EN", "black", []],
        ["esp:GND.1", "col_mux:EN", "black", []],
        # row mux SIG = +3V3 source (matches schematic divider math)
        ["esp:3V3.1", "row_mux:SIG", "red", []],
        # col mux SIG = ADC + pull-down to GND
        ["esp:1", "col_mux:SIG", "yellow", []],
        ["col_mux:SIG", "rpd:1", "yellow", []],
        ["rpd:2", "esp:GND.1", "black", []],
        # decoupling
        ["esp:3V3.1", "c_dec_row:1", "red", []],
        ["c_dec_row:2", "esp:GND.1", "black", []],
        ["esp:3V3.1", "c_dec_col:1", "red", []],
        ["c_dec_col:2", "esp:GND.1", "black", []],
        ["esp:3V3.1", "c_bulk:1", "red", []],
        ["c_bulk:2", "esp:GND.1", "black", []],
        # row select
        ["esp:4", "row_mux:S0", "green", []],
        ["esp:5", "row_mux:S1", "green", []],
        ["esp:6", "row_mux:S2", "green", []],
        ["esp:7", "row_mux:S3", "green", []],
        # col select
        ["esp:15", "col_mux:S0", "blue", []],
        ["esp:16", "col_mux:S1", "blue", []],
        ["esp:17", "col_mux:S2", "blue", []],
        ["esp:18", "col_mux:S3", "blue", []],
    ]
    connections.extend(static_conns)

    # The 256 mesh cells.
    # Each cell is modelled as: row_mux:CH<r> -- (cell_rxc) -- (rmux_inj_rxc) -- col_mux:CH<c>
    # where rmux_inj_rxc is the R_mux series-injection resistor (one per cell to keep
    # the wokwi schematic graph local). In reality there is only one R_mux per active
    # channel selection at a time, but adding 320 ohm into every branch is
    # behaviourally equivalent for the divider math.
    for r in range(16):
        for c in range(16):
            cell_id = f"cell_{r}_{c}"
            inj_id  = f"inj_{r}_{c}"
            r_cell  = cell_resistance(r, c, rng=rng)
            parts.append({
                "type": "wokwi-resistor",
                "id": cell_id,
                "top": 600 + r * 24,
                "left": -200 + c * 24,
                "rotate": 0,
                "attrs": {"value": str(r_cell)},
            })
            parts.append({
                "type": "wokwi-resistor",
                "id": inj_id,
                "top": 600 + r * 24,
                "left": -100 + c * 24,
                "rotate": 0,
                "attrs": {"value": str(r_mux_each * 2)},  # both MUXes lumped
            })
            connections.append([f"row_mux:CH{r}", f"{cell_id}:1", "orange", []])
            connections.append([f"{cell_id}:2",  f"{inj_id}:1",  "orange", []])
            connections.append([f"{inj_id}:2",   f"col_mux:CH{c}","orange", []])

    diagram = {
        "version": 1,
        "author": "Conet Tactile EVT v1 - reality-adjusted",
        "editor": "wokwi",
        "_generator": "tools/reality_check/wokwi_reality.py",
        "_notes": (
            "256-cell, R_mux=320 ohm clone-typ, PSRAM+8MB flash, DC-bias-derated "
            "decoupling. Use for CI burn-in only; the editor will lag."
        ),
        "parts": parts,
        "connections": connections,
        "dependencies": {},
    }
    out_path.write_text(json.dumps(diagram, indent=2))
    return diagram


def main() -> int:
    import sys
    if len(sys.argv) < 2:
        print("usage: python -m tools.reality_check.wokwi_reality <out_path>")
        return 2
    p = Path(sys.argv[1])
    d = build_diagram(p)
    print(f"wrote {p} : {len(d['parts'])} parts, {len(d['connections'])} connections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
