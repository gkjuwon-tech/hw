"""TacNet — the on-device perception model for tactile void detection.

This is the *product* inspector that replaces the z-score statistic: a compact
CNN that reads each pill's pressure-frame patch and outputs a void probability.
It is deliberately tiny (~75k params, <0.3 MFLOPs/pill) so it runs in real time
on the Jetson Orin Nano edge box (exported to ONNX -> TensorRT). Trained on the
Isaac-Sim synthetic dataset with heavy domain randomization so it transfers to
the noisier physical Velostat mat.

  train  ->  best-val checkpoint (out/tacnet.pt)
  export ->  out/tacnet.onnx  (for TensorRT on the Orin Nano)
  eval   ->  scores + metrics on a held-out split (compared in detect.py)

Run:  python sim/isaac/perception.py sim/dataset/tactile_pills.npz
"""
from __future__ import annotations

import os
import numpy as np

from detect import patchify, _scores_to_metrics

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)
PATCH = 5


def _build(torch_nn):
    nn = torch_nn

    class TacNet(nn.Module):
        """Compact pressure-patch classifier (edge-deployable)."""

        def __init__(self, patch=PATCH):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(1, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(),
                nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
                nn.AdaptiveAvgPool2d(1), nn.Flatten(),
            )
            self.head = nn.Sequential(
                nn.Linear(64, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 2),
            )

        def forward(self, x):
            return self.head(self.features(x))

    return TacNet


def _splits(n, seed=0, val=0.15, test=0.2):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    nt = int(n * test); nv = int(n * val)
    return idx[nt:nt + nv], idx[nt + nv:], idx[:nt]   # val, train, test


def train_and_eval(frames, centers, pill_lab, patch=PATCH, epochs=25,
                   seed=0, device=None, save=True):
    """Train TacNet and return (test_scores, test_labels, metrics, artifacts)."""
    import torch
    import torch.nn as nn

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    X = patchify(frames, centers, patch).reshape(-1, 1, patch, patch).astype(np.float32)
    y = pill_lab.ravel().astype(np.int64)
    val, tr, te = _splits(len(y), seed)

    mu, sd = X[tr].mean(), X[tr].std() + 1e-6
    Xn = (X - mu) / sd
    t = lambda a, d=device: torch.tensor(a, device=d)
    Xtr, ytr = t(Xn[tr]), t(y[tr])
    Xva, yva = t(Xn[val]), y[val]
    Xte = t(Xn[te])

    torch.manual_seed(seed)
    TacNet = _build(nn)
    net = TacNet(patch).to(device)
    opt = torch.optim.Adam(net.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, epochs)
    pos_w = float((y[tr] == 0).sum() / max((y[tr] == 1).sum(), 1))
    lossf = nn.CrossEntropyLoss(weight=t(np.array([1.0, pos_w], np.float32)))

    best_auc, best_state = -1.0, None
    bs = 1024
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(len(tr), device=device)
        for i in range(0, len(tr), bs):
            b = perm[i:i + bs]
            opt.zero_grad(); lossf(net(Xtr[b]), ytr[b]).backward(); opt.step()
        sched.step()
        net.eval()
        with torch.no_grad():
            pv = torch.softmax(net(Xva), 1)[:, 1].cpu().numpy()
        auc = _scores_to_metrics(pv, yva)["auc"]
        if auc > best_auc:
            best_auc = auc
            best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}

    net.load_state_dict(best_state)
    net.eval()
    with torch.no_grad():
        scores = torch.softmax(net(Xte), 1)[:, 1].cpu().numpy()
    M = _scores_to_metrics(scores, y[te])
    M["device"] = device
    M["params"] = int(sum(p.numel() for p in net.parameters()))
    M["val_auc"] = float(best_auc)

    artifacts = {}
    if save:
        ckpt = os.path.join(OUT, "tacnet.pt")
        torch.save({"state_dict": best_state, "mu": float(mu), "sd": float(sd),
                    "patch": patch}, ckpt)
        artifacts["ckpt"] = ckpt
        try:
            artifacts["onnx"] = export_onnx(net, patch, device)
        except Exception as e:
            print(f"[perception] onnx export skipped: {e}")
    return scores, y[te], M, artifacts


def export_onnx(net, patch=PATCH, device="cpu"):
    import torch
    net.eval()
    dummy = torch.zeros(1, 1, patch, patch, device=device)
    path = os.path.join(OUT, "tacnet.onnx")
    torch.onnx.export(net, dummy, path, input_names=["patch"],
                      output_names=["logits"], opset_version=17,
                      dynamic_axes={"patch": {0: "n"}, "logits": {0: "n"}})
    print(f"[perception] exported ONNX -> {path}")
    return path


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "sim/dataset/tactile_pills.npz"
    d = np.load(path)
    s, y, M, art = train_and_eval(d["frames"], d["pill_centers"], d["pill_label"])
    print(f"\nTacNet  AUC {M['auc']*100:.1f}%  acc {M['acc']*100:.1f}%  "
          f"prec {M['prec']*100:.1f}%  rec {M['rec']*100:.1f}%  F1 {M['f1']*100:.1f}%"
          f"  | params {M['params']}  device {M['device']}")
    print(f"artifacts: {art}")
