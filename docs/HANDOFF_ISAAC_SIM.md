# Handoff — Full digital twin in NVIDIA Isaac Sim (RunPod RTX)

> **For the next agent (e.g. Devin) picking this up on an open-network GPU VM.**
> Mission: rebuild the Conet Tactile inspection line as a **full-fidelity
> digital twin in NVIDIA Isaac Sim**, matching the real setup as closely as
> possible, and from that **single pipeline produce BOTH (a) defect-detection
> metrics and (b) a labelled synthetic dataset** — at scale, with domain
> randomization, ready to fine-tune an AI later.

---

## 0. Why this handoff exists (the blocker)

A working physics twin + dataset + metrics **already exist** (in MuJoCo, on
CPU — see §2). The reason we did not go straight to Isaac Sim:

- This work was prototyped inside **Claude Code on the web**, whose container
  has a **locked-down egress** (allowlist: github + pypi + a few mirrors). It
  **cannot SSH out** to RunPod (both direct TCP and the `ssh.runpod.io` proxy
  time out), and it has **no GPU**. So Isaac Sim was impossible there.
- An agent running in an **open-network VM with a GPU** (Devin, or Claude Code
  with a permissive network policy) **can** do this directly: SSH into the
  RunPod pod, install Isaac Sim, render with RTX, and run the twin.

Nothing is lost — the CPU twin is the **ground-truth prototype**. Isaac Sim
should reproduce its qualitative result, then add fidelity + scale.

---

## 1. The real system to replicate (ground truth)

```
   parts on conveyor  ──►  tactile mesh (16×16 piezoresistive cells)  ──►  pressure frame
                                     │
                                     ▼
                         Jetson Orin Nano (edge_agent) ── HTTPS ──►  Tactile Cloud (backend)
```

- **Conveyor belt**: 350 mm wide (one of our catalog SKUs), ~1.2 m section,
  ~0.15 m/s. The **tactile mesh is laid along the WHOLE belt** — every part
  that rides past is inspected, not one spot.
- **Tactile mesh**: a Velostat-based **piezoresistive mat**, **16×16 cells at
  10 mm pitch** (160×160 mm active). It behaves like a **compliant
  bed-of-springs** (Winkler foundation): contact load spreads across cells; a
  cell's reading ≈ local pressure.
- **Per part → one frame**: an `R×C` (16×16) pressure image, row-major, 8-bit
  (0..255). This is the **data contract** the scanner MCU, `edge_agent`, and
  the backend `inspect` API all speak (see `edge_agent` `frame_t`, and
  `POST /v1/lines/{line_id}/inspect {"data": [...]}`).
- **Defect of record = pill with an internal void.** A tablet/capsule with a
  sealed internal cavity is **externally identical** (a camera / Cognex sees
  nothing) but **lighter**, so it presses its patch of the mat **less hard**.
  This is the entire reason a tactile sensor beats vision here — Isaac Sim must
  preserve this physics.

---

## 2. What already exists in this repo (reuse — do NOT reinvent)

Repo: `gkjuwon-tech/hw` (everything below is on `main`).

| Path | What it is | Reuse for Isaac |
|---|---|---|
| `sim/specs.py` | **Real dimensions** (belt 350 mm, mesh 16×16@10 mm, Jetson Orin Nano dev kit 103×90.5×34.77, Waveshare 7", enclosure). Sources cited. | Single source of truth for the USD scene scale. |
| `sim/tactile_twin.py` | MuJoCo **compliant taxel** sensor (bed-of-springs), defect generators, `TwinSim` fast presser. | The physics model to match; copy the spring stiffness / contact intuition. |
| `sim/generate_dataset.py` | **Pill-tray twin + dataset + metrics**. Statistical (z-score vs good baseline) detector, **no AI**. | The dataset schema + detector + the metric target to beat. |
| `sim/scene.py` | MuJoCo scene (headless OSMesa render). | Layout reference (belt/rollers/rails/mesh/edge box). |
| `sim/render_blender.py` | Blender presentation render. | Material/lighting reference if you render hero shots. |
| `sim/dataset/tactile_pills.npz` | Sample labelled dataset (gitignored output). | **Match this format exactly** (see §4). |
| `hardware/edge_enclosure/edge_enclosure.scad` | Parametric Edge box (manifold-verified). | Drop into the Isaac scene beside the belt for realism. |
| `backend/` | FastAPI cloud; the anomaly detector lives in the `inspect` path (sigma threshold + `threshold_hits`). | Feed Isaac frames through the SAME logic to compare. |
| `edge_agent/` | On-device agent + scanner frame format. | The frame contract (`frame_t`, row-major 8-bit). |

### Current CPU-twin results (the baseline to match/beat)

From `sim/generate_dataset.py`, **400 trays × 16 pills = 6,400 pills**:

```
good-pill pressure : 1.05 ± 0.07 N
void-pill pressure : 0.80 ± 0.07 N   (lighter → lower)
ROC-AUC  99.5%  |  accuracy 97.0%  |  precision 96.7%  |  recall 95.6%  |  F1 96.2%
```

Void detection works in physics. Isaac Sim should **confirm and harden** this
with real contact mechanics + RTX + domain randomization.

---

## 3. Target environment (RunPod)

- Pod: **RTX 2000 Ada (16 GB)**, 8 vCPU (EPYC), 31 GB RAM, image
  `runpod-torch-v240` (Ubuntu + CUDA + PyTorch), **/workspace = 100 GB
  persistent volume** (clone the repo there — survives pod restarts).
- Has a **display path** (RTX) — Isaac Sim runs with the RTX renderer, headless
  or via livestream. ~$0.26/hr — **stop the pod when idle**.
- SSH: account-level public key → pod `authorized_keys`; direct TCP
  (`root@<ip> -p <port>`) supports SCP. Pod has full internet (NVIDIA/NGC,
  github) for installs.

---

## 4. Deliverables / acceptance criteria

1. **Isaac Sim installed + verified** on the pod (`nvidia-smi` + a headless
   RTX render of the twin saved to a PNG). Pin versions; document them.
2. **USD scene to scale** from `sim/specs.py`: conveyor (kinematic belt at
   0.15 m/s) + full-length tactile mesh + the Edge enclosure beside it.
3. **Tactile sensor model** producing a **16×16 pressure frame per pill**,
   physically grounded (contact forces / pressure field), matching the
   bed-of-springs behaviour of `sim/tactile_twin.py`.
4. **Pills with internal void**: rigid tablets with **real mass**; void =
   same geometry, reduced mass (sealed cavity → lower density) + optional
   off-centre CoM. Document the mass/scale choice (real tablets are ~0.3–0.6 g;
   either model sensor sensitivity to match, or use representative scaled
   pills — state which).
5. **One pipeline → dataset + metrics simultaneously**: every simulated pill
   contributes (a) a labelled frame to the dataset AND (b) a sample to the
   metric. Target **≥ 50k labelled pills** with **domain randomization**
   (pill colour/size/position, belt speed, void fraction, sensor noise,
   lighting if rendering).
6. **Dataset format = drop-in compatible** with the existing one:
   `np.savez_compressed(... frames=(N,16,16) float32, pill_pressure=(N,16) float32,
   pill_label=(N,16) int8, pill_centers=...)` — so `sim/generate_dataset.metrics()`
   and the backend detector run unchanged.
7. **Metrics report**: run BOTH (a) the existing **statistical z-score detector**
   and (b) — now that there's a GPU — a small **CNN** trained on the dataset.
   Report ROC-AUC / accuracy / precision / recall + confusion, and **compare to
   the CPU baseline** (AUC 99.5%). Both detectors on a held-out split.
8. **Everything committed** under `sim/isaac/` with a one-command reproduce
   script, pinned deps, and a short README.

---

## 5. Suggested approach (not prescriptive)

- **Install**: try Isaac Sim **pip packages** first (`pip install "isaacsim[all,extscache]==<ver>" --extra-index-url https://pypi.nvidia.com`) on the torch image; fall back to the **Isaac Sim container** if the pip route fights the pod's CUDA/driver. Verify `from isaacsim import SimulationApp` boots headless.
- **Tactile sensor in Isaac** — pick one, in order of parity:
  1. **Contact-report taxel array** (recommended for 1:1 parity): a 16×16 grid
     of small rigid taxels on prismatic joints with a spring (PhysX joint
     drive), read each taxel's contact normal force → frame. This mirrors
     `tactile_twin.py` exactly.
  2. **PhysX deformable / soft-body mat** + contact pressure sampling →
     higher fidelity, more setup.
  3. Isaac's contact sensor API per cell region.
- **Pills**: rigid `Cylinder`/capsule prims with `mass` + `centerOfMass`;
  void = lower mass (and/or CoM offset). Drop onto the mat, settle, read.
- **Throughput**: use Isaac's **cloning / vectorized envs** (many trays in
  parallel on the GPU) to hit 50k+ samples fast — this is the whole point of
  moving to a GPU.
- **Keep the contract**: whatever the native sensor resolution, **resample to
  16×16** before saving, and quantize like the real 8-bit scanner so synthetic
  ↔ real frames stay interchangeable.

---

## 6. Gotchas / parity notes

- The detection signal is a **pressure/weight deficit** — make sure sim
  sensitivity resolves the void's mass deficit **above the sensor noise** you
  inject (the CPU twin used ±4 % good-mass jitter, 0.55–0.78× void mass,
  ~1.2 % per-cell noise — start there).
- **Domain randomization is the deliverable**, not a nicety: vary aggressively
  so a model trained on this transfers to the real Velostat mat (which is
  noisier and non-linear).
- The MuJoCo twin is the **sanity check**: if Isaac's good-vs-void separation
  is *worse* than AUC ~0.99 at comparable settings, something's wrong with the
  contact model — debug before scaling.
- **Pill ≠ part**: the current twin also has a generic "part footprint" path
  (`sim/scene.py`) — the pharma/void story is the headline; keep both if easy.

---

## 7. Connect (from an open-network agent)

The Claude env couldn't reach these; an open-net VM can:

```bash
# RunPod gives one of these on the pod's "Connect" tab:
ssh root@<POD_IP> -p <PORT> -i ~/.ssh/<your_key>          # direct TCP (SCP works)
ssh <podid>@ssh.runpod.io -i ~/.ssh/<your_key>            # proxy

# on the pod:
cd /workspace && git clone https://github.com/gkjuwon-tech/hw.git && cd hw
nvidia-smi   # confirm RTX 2000 Ada + driver/CUDA
# then install Isaac Sim and build sim/isaac/ per §4–§5
```

> If using Claude Code instead of Devin: recreate the web environment with a
> **permissive network policy** (see code.claude.com/docs → network policies) —
> then SSH to RunPod works and this whole handoff can be executed in-session.

---

## 8. One-line status

A physics-correct tactile twin + a 6,400-pill labelled dataset + a 97 %
void-detection result already exist on CPU (MuJoCo). **Take it to Isaac Sim on
the RTX pod, match the real line exactly, and scale the dataset + metrics on
the GPU.** Everything you need to match is in `sim/`.
