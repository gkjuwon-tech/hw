# Scanner v1 — manufacturing artifact generator

This subdirectory contains the Python source that emits the three files
JLCPCB needs to fabricate + populate the Scanner v1 PCB:

```
hardware/pcb/conet-scanner-v1/
├── gerbers.zip      ← generated
├── bom.csv          ← generated
├── cpl.csv          ← generated
└── tools/
    ├── components.py        ← placement + BOM source-of-truth
    ├── footprints.py        ← SMD/THT pad geometry per package
    ├── gerber.py            ← minimal RS-274X + Excellon writer
    ├── build_artifacts.py   ← top-level entrypoint
    └── README.md            ← this file
```

## Why a Python generator instead of KiCad / Altium?

This board is small (60 × 40 mm, ~35 unique parts) and the
[`schematic.md`](../schematic.md) netlist is already structured. Re-deriving
the manufacturing files from a single declarative source — instead of
keeping a separate `.kicad_pcb` in sync with the schematic — gives us:

- **No EDA-tool licensing dependency** in CI. The generator runs on stock
  Python 3 with the standard library only.
- **Diff-friendly artifacts.** When R30 moves 1 mm, the diff is a 1-line
  change in `components.py`, not a binary repack of the `.kicad_pcb`.
- **Deterministic output.** Running `python3 build_artifacts.py` twice on
  the same inputs produces byte-identical Gerber/BOM/CPL files (modulo the
  ISO-8601 `CreationDate` field in each Gerber header, which JLCPCB
  ignores for matching).

We will still graduate to a full KiCad project for v2 once the routing
needs more nuance than this generator supports — at which point this
folder's job is done and the canonical artwork moves into the KiCad
sources.

## Regenerating the artifacts

From this directory's parent (`hardware/pcb/conet-scanner-v1/`):

```bash
python3 tools/build_artifacts.py
```

This rewrites `gerbers.zip`, `bom.csv`, and `cpl.csv` in place. The
generator has zero non-stdlib dependencies — Python 3.10+ is enough.

## Sanity-checking the generated Gerbers

If you want to visualise the output without uploading to JLCPCB:

```bash
pip install gerbonara          # local-only, dev dependency
python3 -c "
import gerbonara
stack = gerbonara.LayerStack.open('gerbers/')   # after unzipping
open('top.svg','w').write(str(stack.to_pretty_svg(side='top')))
"
```

JLCPCB's own "Order Now" page also gives a free in-browser viewer — paste
the zip in there before paying and you'll see exactly what the
fabricator will see.

## Editing the placement

Open [`components.py`](components.py). Each `Component` row is

```python
Component(
    refdes="R30", value="10k",
    footprint="0402", lcsc="C25744",
    x=54.0, y=22.0, rotation=90,
    comment="0402WGF1002TCE",
    description="...",
)
```

- `refdes` must match the netlist in [`../schematic.md`](../schematic.md).
- `footprint` must match a key in [`footprints.py`](footprints.py).
- `lcsc` is what JLCPCB matches against — leave empty for jumpers / DNP.
- `x`, `y` are in millimetres, board origin = bottom-left.
- `rotation` is in degrees, CCW. Use multiples of 90° (the generator's
  rectangular-aperture rotation path handles those exactly; other angles
  fall through to a polygon region and the resulting Gerber is still
  correct but harder to read in the JLCPCB viewer).
- `populate=False` keeps the footprint on the PCB and in the CPL but drops
  it from the BOM (the JLCPCB SMT line then skips the part).

After editing, re-run `python3 tools/build_artifacts.py`, commit the
changed `components.py` **plus** the regenerated `gerbers.zip` / `bom.csv`
/ `cpl.csv`, and open a PR.

## Adding a new footprint

If you need a package that isn't already in
[`footprints.py`](footprints.py):

1. Find the LCSC part page and copy the recommended land-pattern
   dimensions from the datasheet.
2. Add an entry to the `FOOTPRINTS` dict mapping pad positions to a
   `{shape, w, h, x, y}` dict. Pad coordinates are relative to the
   component's centre at rotation = 0.
3. Reference the new footprint from a `Component(...)` row in
   [`components.py`](components.py).
4. Re-run the generator and double-check the output in the JLCPCB viewer
   (or in `gerbonara`'s SVG export).
