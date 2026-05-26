# Tactile inspection — physics digital twin (MuJoCo)

> "사람은 돈이 없으면 뇌를 굴려야 된다." — 하드웨어를 못 사니, 물리엔진 안에
> 똑같은 센서를 만들어 **불량 데이터를 공짜로 찍어낸다.**

A digital twin of the Tactile Edge sensor, built in **MuJoCo** (the physics
engine DeepMind uses — not a game engine). It presses parts onto a simulated
compliant pressure mat and reads the contact forces. The output frame has the
**same shape as the physical scanner** (an `R x C` pressure field, see
`edge_agent` / the backend `inspect` API), so synthetic and real data are
interchangeable.

## Why not Isaac Sim?

Isaac Sim is the dream, but it needs an **RTX GPU** and multi-GB NVIDIA
downloads — neither of which exists in a CPU-only, locked-down sandbox. So we
keep the **same data contract** and run the twin in MuJoCo (CPU, headless,
`pip install mujoco`). When an RTX box is available, swap the engine in behind
the same frame interface — nothing downstream changes.

## The model (why it's not janky)

A rigid part on a rigid grid only touches at ~3 points (statically
determinate) — useless for a pressure image. Real pressure mats are
**compliant**, so we model each taxel as its own **sprung slider** — a
*bed of springs* / **Winkler elastic foundation**. Load then spreads across
the whole contact patch, exactly like a piezoresistive mat:

| defect | signature in the pressure map |
|---|---|
| nominal | full, near-uniform field |
| missing corner | a cold (zero-pressure) block in one corner |
| foreign object (pellet) | a hot spot + the rest of the footprint unloads |
| dent / cavity | a cold patch in an otherwise uniform field |

Each taxel reading is its spring force `F = k·δ` (compression × stiffness).

## Run

```bash
pip install -r sim/requirements.txt
python3 sim/tactile_twin.py          # prints nominal vs defect pressure maps
```

## Roadmap

1. ✅ **Twin + defect signatures** (this file) — physics works, defects show.
2. ⏭ **Synthetic dataset** — randomise defect type/size/position/load and dump
   thousands of labelled frames (`.npz`), matching the scanner frame format.
3. ⏭ **Prove it catches defects** — run the dataset through the backend's
   anomaly detector and report precision / recall / ROC. (Investor metrics.)
4. ⏭ **Fine-tune** — feed the labelled corpus to the model later, in one go.
5. ⏭ **Isaac Sim** — drop-in higher-fidelity engine on a real RTX box.
