# Isaac Sim tactile twin

This directory is the RTX/Isaac continuation of the MuJoCo tactile twin in
`sim/`.  The CPU twin already proves the core physics: a sealed internal void
does not change the pill outline, but it reduces pill mass, so the same external
tablet presses the 16×16 mesh less hard.

The important rule: **GitHub is the durable handoff. RunPod is disposable.**
Everything needed to resume the A6000 work should live here instead of only on a
pod volume.

## Current verified RunPod target

- Pod name: `extended_orange_stoat`
- GPU: NVIDIA RTX A6000, 49,140 MiB
- Driver: 570.195.03
- CUDA reported by driver: 12.8
- Python: 3.11.10
- Durable pod workspace: `/workspace`
- Isaac pip note: Python 3.11 cannot install Isaac Sim 4.5 from NVIDIA's pip
  index. This pod should use Isaac Sim 5.1.0.0 unless you intentionally rebuild
  a Python 3.10 environment for Isaac 4.5.
- Isaac's pip boot asks for the NVIDIA Omniverse EULA. The non-interactive
  install script sets `OMNI_KIT_ACCEPT_EULA=YES`; only run it if you accept
  NVIDIA's terms for the pod.
- Verified blocker after install: the RunPod template exposes CUDA/NVML, but
  Vulkan only sees `llvmpipe`. Isaac installs and starts, then cannot create an
  NVIDIA Vulkan GPU device. `apt install libnvidia-gl-570-server` is not safe on
  this template: it attempts to pull 580 userspace libraries and causes an
  NVML driver/library mismatch until removed.
- Direct SSH/SCP:

```bash
ssh root@38.147.83.19 -p 21678 -i ~/.ssh/devin_runpod_isaac_sim
```

The public key used for this session is:

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFFvlAkUhp9wnaKPMLCjndYQNDOZoyihuujh4ZvAOR/t devin-isaac-sim-2026-05-26
```

## One-command bootstrap on the pod

From a fresh pod:

```bash
mkdir -p /workspace && cd /workspace
git clone https://github.com/gkjuwon-tech/hw.git
cd hw
bash sim/isaac/runpod_bootstrap.sh
```

Then install Isaac Sim with the selected route:

```bash
bash sim/isaac/install_isaac_pip.sh
```

If the pip package route fights the pod image/CUDA stack, switch to NVIDIA's
Isaac Sim container and keep the same files in this directory as the mounted
workspace.

Before spending time on scene code, verify RTX/Vulkan:

```bash
VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json vulkaninfo --summary
```

Expected: NVIDIA RTX A6000. Bad state observed on the first pod: only
`llvmpipe`/CPU Vulkan was visible, so Isaac could not render with RTX.

## Acceptance target

The Isaac pipeline must produce the same dataset contract as
`sim/generate_dataset.py`:

```python
np.savez_compressed(
    "tactile_pills_isaac.npz",
    frames=(N, 16, 16) float32,
    pill_pressure=(N, 16) float32,
    pill_label=(N, 16) int8,
    pill_centers=(16, 2) float32,
)
```

That lets the existing statistical detector and backend calibration/inspection
logic run unchanged.

## Physics parity checklist

Use the existing files as source of truth:

- `sim/specs.py`: belt, mesh, Jetson/display/enclosure dimensions.
- `sim/tactile_twin.py`: taxel stiffness/damping intuition.
- `sim/generate_dataset.py`: pill geometry, void mass range, dataset layout,
  metrics baseline.

Isaac implementation order:

1. Build a scaled USD scene: 350 mm belt, 1.2 m section, 16×16 mesh at 10 mm
   pitch, side rails, Edge enclosure.
2. Implement the tactile mesh as a 16×16 spring taxel array. Each taxel should
   provide a normal-force value that becomes one frame cell.
3. Spawn 4×4 pills over the active mesh. A void pill has the same visible
   geometry but lower mass and optional off-centre CoM.
4. Write frames and pill-level labels/pressures on every tray.
5. Run `sim/isaac/evaluate_dataset.py` on the output and compare against the
   MuJoCo baseline:
   - ROC-AUC: 99.5 %
   - accuracy: 97.0 %
   - precision: 96.7 %
   - recall: 95.6 %
   - F1: 96.2 %
6. Only after matching the baseline, scale to at least 50k labelled pills with
   domain randomization.

## Local sanity checks without Isaac

These commands do not require Isaac Sim. They validate that the handoff tools
still understand the existing dataset contract:

```bash
python3 sim/isaac/evaluate_dataset.py sim/dataset/tactile_pills.npz
python3 sim/isaac/check_environment.py
```

When running repo scripts directly from the repository root, set:

```bash
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
```
