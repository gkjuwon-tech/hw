"""Void-detection report on a tactile pill dataset — headline model + baseline.

Runs on the SAME `.npz` schema the CPU MuJoCo twin produces (see
`sim/generate_dataset.py`) so Isaac-Sim frames and MuJoCo frames are scored
identically.

  HEADLINE   TacNet (perception.py)  — the real product model: a compact CNN
             that runs on the Jetson Orin Nano edge box. This is what ships.
  REFERENCE  z-score statistic       — the old GPU-poverty fallback (same
             anomaly test the backend `inspect` path used). Kept only so the
             learned model can be compared against it and the CPU baseline.

Both are evaluated on a held-out split and printed against the CPU baseline.

Run:  python detect.py sim/dataset/tactile_pills.npz
"""
from __future__ import annotations

import sys
import numpy as np

CELL_PITCH = 0.010   # m, must match the sensor grid
CPU_BASELINE = dict(auc=0.995, acc=0.970, prec=0.967, rec=0.956, f1=0.962)


# ── shared metric helpers ────────────────────────────────────────────────

def _roc_auc(score: np.ndarray, y: np.ndarray) -> float:
    """Rank-based ROC-AUC (high score = more likely void)."""
    order = np.argsort(score)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(len(score))
    npos, nneg = int(y.sum()), int((y == 0).sum())
    if npos == 0 or nneg == 0:
        return float("nan")
    return (ranks[y == 1].sum() - npos * (npos - 1) / 2) / (npos * nneg)


def _best_threshold(score: np.ndarray, y: np.ndarray):
    """Operating point by Youden's J; returns (thr, confusion dict)."""
    best = None
    for thr in np.linspace(score.min(), score.max(), 300):
        pred = score >= thr
        tp = int((pred & (y == 1)).sum()); fp = int((pred & (y == 0)).sum())
        fn = int((~pred & (y == 1)).sum()); tn = int((~pred & (y == 0)).sum())
        tpr = tp / max(tp + fn, 1); fpr = fp / max(fp + tn, 1)
        j = tpr - fpr
        if best is None or j > best[0]:
            best = (j, thr, tp, fp, fn, tn)
    _, thr, tp, fp, fn, tn = best
    return thr, dict(tp=tp, fp=fp, fn=fn, tn=tn)


def _scores_to_metrics(score: np.ndarray, y: np.ndarray) -> dict:
    auc = _roc_auc(score, y)
    thr, c = _best_threshold(score, y)
    tp, fp, fn, tn = c["tp"], c["fp"], c["fn"], c["tn"]
    acc = (tp + tn) / max(tp + fp + fn + tn, 1)
    prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    return dict(auc=auc, acc=acc, prec=prec, rec=rec, f1=f1, **c, n=len(y), pos=int(y.sum()))


# ── (a) statistical z-score detector ─────────────────────────────────────

def zscore_detector(pill_press: np.ndarray, pill_lab: np.ndarray, seed=0) -> dict:
    """Calibrate the good-pill baseline on half the good pills, score the rest."""
    p = pill_press.ravel().astype(float)
    y = pill_lab.ravel().astype(int)
    good_idx = np.where(y == 0)[0]
    rng = np.random.default_rng(seed); rng.shuffle(good_idx)
    cal = good_idx[: len(good_idx) // 2]
    test = np.setdiff1d(np.arange(len(y)), cal)
    mu, sigma = p[cal].mean(), p[cal].std()
    score = (mu - p) / max(sigma, 1e-9)          # high = pressure deficit = void
    M = _scores_to_metrics(score[test], y[test])
    M.update(mu=float(mu), sigma=float(sigma))
    return M


# ── per-pill patch extraction (shared by the CNN) ────────────────────────

def patchify(frames: np.ndarray, centers: np.ndarray, patch=5) -> np.ndarray:
    """Crop a `patch`x`patch` window of the pressure frame around each pill.
    Returns (n_frames, n_pills, patch, patch)."""
    n, R, C = frames.shape
    half = patch // 2
    padded = np.pad(frames, ((0, 0), (half, half), (half, half)))
    x0 = -(C - 1) * CELL_PITCH / 2
    y0 = -(R - 1) * CELL_PITCH / 2
    out = np.zeros((n, len(centers), patch, patch), dtype=np.float32)
    for k, (px, py) in enumerate(centers):
        col = int(round((px - x0) / CELL_PITCH)) + half
        row = int(round((py - y0) / CELL_PITCH)) + half
        out[:, k] = padded[:, row - half:row + half + 1, col - half:col + half + 1]
    return out


# ── report ────────────────────────────────────────────────────────────────

def _row(name, M):
    if M is None:
        return f" {name:<22}  (skipped)"
    return (f" {name:<22}  AUC {M['auc']*100:5.1f}%  acc {M['acc']*100:5.1f}%  "
            f"prec {M['prec']*100:5.1f}%  rec {M['rec']*100:5.1f}%  F1 {M['f1']*100:5.1f}%"
            f"   [TP{M['tp']} FP{M['fp']} FN{M['fn']} TN{M['tn']}]")


def report(path: str, patch=5, epochs=25):
    d = np.load(path)
    frames = d["frames"]; pill_press = d["pill_pressure"]
    pill_lab = d["pill_label"]; centers = d["pill_centers"]
    n_pill = int(pill_lab.size); n_void = int(pill_lab.sum())
    gp = pill_press[pill_lab == 0]; vp = pill_press[pill_lab == 1]

    z = zscore_detector(pill_press, pill_lab)
    try:
        import perception
        _, _, tac, _ = perception.train_and_eval(frames, centers, pill_lab,
                                                 patch=patch, epochs=epochs)
    except Exception as e:
        print(f"[report] TacNet unavailable ({e}); reporting baseline only")
        tac = None

    print("\n========== ISAAC-SIM TACTILE VOID DETECTION ==========")
    print(f" dataset : {frames.shape[0]} trays, {n_pill} pills "
          f"({n_void} void / {n_pill - n_void} good), frame {frames.shape[1]}x{frames.shape[2]}")
    print(f" good-pill pressure : {gp.mean():.3f} +/- {gp.std():.3f}")
    print(f" void-pill pressure : {vp.mean():.3f} +/- {vp.std():.3f}  (lighter -> lower)")
    print(" " + "-" * 80)
    print(_row("HEADLINE  TacNet (edge)", tac)
          + (f"   {tac['params']/1000:.0f}k params" if tac else ""))
    print(_row("REFERENCE z-score", z))
    print(_row("          CPU baseline", dict(**CPU_BASELINE, tp="-", fp="-", fn="-", tn="-"))
          .replace("[TP- FP- FN- TN-]", "[MuJoCo]"))
    print("======================================================\n")
    return dict(tacnet=tac, zscore=z)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "sim/dataset/tactile_pills.npz"
    report(path)
