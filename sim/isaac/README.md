# Isaac-Sim digital twin — Conet Tactile inspection line

The full-fidelity twin of the real line in **NVIDIA Isaac Sim** (RTX, on a
RunPod GPU pod), taking over from the CPU MuJoCo prototype in `sim/`. It matches
the real setup part-for-part — same dimensions, same enclosure CAD, same 16×16
tactile contract — and from **one GPU pipeline** produces both a labelled
synthetic dataset and defect-detection metrics, then runs the **real on-device
product AI** (not the old statistical fallback).

> See `docs/HANDOFF_ISAAC_SIM.md` for the mission and acceptance criteria.

## What it builds

| File | Role |
|---|---|
| `smoke.py` | Boot Isaac headless, confirm RTX, save a render PNG (acceptance #1). |
| `scene.py` | To-scale USD scene: conveyor + rollers + rails, the 16×16 Velostat mesh, pills, and the **real Edge enclosure** (imported from `hardware/edge_enclosure/edge_enclosure.scad` via OpenSCAD) on a VESA stand with a kiosk screen + Jetson. Hero RTX render. |
| `tactile_sensor.py` | The sensor: a 16×16 **sprung-taxel array** (bed of springs / Winkler foundation) — the 1:1 Isaac analogue of `sim/tactile_twin.py`. Per-cell contact force = pressure. |
| `generate_dataset.py` | One GPU pipeline → dataset + metrics. Clones the tray across many GPU envs, domain-randomizes mass/position/void-fraction/noise, settles on real PhysX contacts, reads a 16×16 frame per tray. Drop-in `.npz` schema. |
| `perception.py` | **TacNet** — the product perception model (~23k-param CNN). Per-pill void detection from pressure patches; exports ONNX → TensorRT for the Orin Nano. **This replaces the z-score.** |
| `detect.py` | Report harness: TacNet (headline) vs z-score (reference) vs the CPU baseline. |
| `sllm/` | The on-device **QC reporting sLLM** (Qwen2.5-0.5B + LoRA): turns an inspection record into the operator report shown on the kiosk. Quantized INT4 for the edge. |

## The product AI (runs on the Jetson Orin Nano edge box)

Two stages, both edge-sized:

1. **Perception — TacNet (CNN).** Real-time per-pill void detection on every
   tray. ONNX → TensorRT (FP16). ~23k params.
2. **Reporting — QC sLLM (Qwen2.5-0.5B, LoRA, INT4).** On a flagged tray it
   writes the operator QC report (verdict, flagged pills + grid position +
   pressure deficit, the internal-void physics, recommended action). GGUF
   Q4_K_M via llama.cpp; fits in <0.6 GB, well inside the per-tray time budget.

```
sim/isaac/sllm/build_corpus.py   # detection records -> QC report pairs (LoRA data)
sim/isaac/sllm/train_lora.py     # LoRA fine-tune the sLLM on our domain
sim/isaac/sllm/infer.py          # generate reports (as the kiosk would)
sim/isaac/sllm/export_edge.py    # merge + INT4 GGUF + edge manifest
```

## Reproduce (on the RunPod RTX pod)

```bash
bash sim/isaac/run.sh 50000          # venv + Isaac Sim + smoke + dataset + metrics
# then the product AI:
python sim/isaac/perception.py sim/dataset/tactile_pills.npz       # train TacNet
python sim/isaac/sllm/build_corpus.py sim/dataset/tactile_pills.npz
python sim/isaac/sllm/train_lora.py                                # LoRA fine-tune
python sim/isaac/sllm/infer.py --demo sim/dataset/tactile_pills.npz
python sim/isaac/sllm/export_edge.py                               # INT4 for Orin
```

## Environment (pinned)

- Pod: NVIDIA RTX 2000 Ada (16 GB), CUDA 12.4, driver 550.x, Ubuntu 22.04.
- Isaac Sim **4.5.0.0** (pip) in a Python **3.10** venv at `/workspace/isaacenv`.
- AI training uses the system PyTorch (2.4.1+cu124, Python 3.11) so Isaac's
  pinned deps stay isolated from `transformers`/`peft`.

Metrics from the latest run are printed by `detect.py`; the CPU MuJoCo baseline
to beat is ROC-AUC 99.5%.
