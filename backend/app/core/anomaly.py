"""One-class tactile anomaly detector.

This is a deliberately small reference implementation. Production swaps it for a
PaDiM-class or PatchCore-class model adapted to pressure-time fields. The
contract (``fit`` / ``score`` / ``serialize`` / ``load``) is what the rest of
the service depends on.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Score:
    """Result of scoring a single tactile frame."""

    score: float
    """Aggregate anomaly score. Higher = more anomalous."""

    hits: int
    """Number of cells whose deviation exceeded the sigma threshold."""

    cell_score_max: float
    """Maximum per-cell deviation, in standard deviations."""

    frame_features: dict[str, float]
    """Aggregate scalar features for downstream analytics."""


@dataclass
class Baseline:
    """Calibration artifact for a single line."""

    mean: np.ndarray
    """Per-cell mean, shape ``(H, W)``."""

    std: np.ndarray
    """Per-cell standard deviation, shape ``(H, W)``. Floored to avoid div-by-zero."""

    feature_mean: np.ndarray
    """Mean of the global feature vector, shape ``(F,)``."""

    feature_std: np.ndarray
    """Std of the global feature vector, shape ``(F,)``. Floored."""

    n_samples: int
    """Number of known-good samples used."""

    rows: int
    cols: int

    @classmethod
    def fit(cls, samples: list[np.ndarray]) -> Baseline:
        """Compute per-cell statistics from ``samples`` (each shape ``(H, W)``)."""
        if not samples:
            raise ValueError("at least one sample is required")
        arr = np.stack(samples).astype(np.float32)  # (N, H, W)
        if arr.ndim != 3:
            raise ValueError(f"expected (N, H, W), got shape {arr.shape}")

        mean = arr.mean(axis=0)
        std = arr.std(axis=0)
        # Floor std relative to the dynamic range of the calibration set so that
        # quiet background cells don't blow up the per-cell deviation when a
        # later frame has small natural noise.
        dyn = float(arr.max() - arr.min())
        std_floor = max(1.0, 0.02 * dyn)
        std = np.maximum(std, std_floor)

        feats = np.stack([_features(s) for s in arr], axis=0)  # (N, F)
        f_mean = feats.mean(axis=0)
        f_std = np.maximum(feats.std(axis=0), max(1.0, 0.02 * dyn))

        return cls(
            mean=mean,
            std=std,
            feature_mean=f_mean,
            feature_std=f_std,
            n_samples=arr.shape[0],
            rows=int(arr.shape[1]),
            cols=int(arr.shape[2]),
        )

    def score(self, frame: np.ndarray, sigma_threshold: float = 3.0) -> Score:
        """Score ``frame`` against this baseline."""
        if frame.shape != self.mean.shape:
            raise ValueError(
                f"frame shape {frame.shape} != baseline shape {self.mean.shape}"
            )

        frame = frame.astype(np.float32)
        cell_dev = np.abs(frame - self.mean) / self.std  # (H, W) in units of sigma

        feats = _features(frame)
        f_dev = np.abs(feats - self.feature_mean) / self.feature_std  # (F,)

        # Aggregate: top-K cell deviations plus the feature deviation.
        flat = cell_dev.reshape(-1)
        k = max(1, flat.size // 200)  # robust to outliers, ignores top 0.5%
        top_k = np.partition(flat, -k)[-k:]
        cell_term = float(top_k.mean())
        feat_term = float(f_dev.mean())
        score = 0.7 * cell_term + 0.3 * feat_term

        hits = int((cell_dev > sigma_threshold).sum())
        cell_max = float(cell_dev.max())

        return Score(
            score=score,
            hits=hits,
            cell_score_max=cell_max,
            frame_features={
                "sum": float(feats[0]),
                "max": float(feats[1]),
                "area": float(feats[2]),
                "centroid_row": float(feats[3]),
                "centroid_col": float(feats[4]),
                "peak_gradient": float(feats[5]),
            },
        )

    def to_bytes(self) -> bytes:
        """Serialize the baseline to a single ``.npz`` blob."""
        import io

        buf = io.BytesIO()
        np.savez_compressed(
            buf,
            mean=self.mean,
            std=self.std,
            feature_mean=self.feature_mean,
            feature_std=self.feature_std,
            n_samples=np.array(self.n_samples),
            rows=np.array(self.rows),
            cols=np.array(self.cols),
        )
        return buf.getvalue()

    @classmethod
    def from_bytes(cls, blob: bytes) -> Baseline:
        import io

        with np.load(io.BytesIO(blob)) as data:
            return cls(
                mean=data["mean"],
                std=data["std"],
                feature_mean=data["feature_mean"],
                feature_std=data["feature_std"],
                n_samples=int(data["n_samples"]),
                rows=int(data["rows"]),
                cols=int(data["cols"]),
            )


def _features(frame: np.ndarray) -> np.ndarray:
    """Cheap scalar features for the calibration distribution.

    Designed so that two frames of identical good product are close in this
    space, and frames with the wrong fill / position / softness are far.
    """
    h, w = frame.shape
    s = float(frame.sum())
    mx = float(frame.max())
    area = float((frame > 0.5 * mx).sum() if mx > 0 else 0.0)

    if s > 0:
        rs = np.arange(h, dtype=np.float32)[:, None]
        cs = np.arange(w, dtype=np.float32)[None, :]
        cr = float((frame * rs).sum() / s)
        cc = float((frame * cs).sum() / s)
    else:
        cr = cc = 0.0

    gy, gx = np.gradient(frame.astype(np.float32))
    peak_grad = float(np.sqrt(gx * gx + gy * gy).max())

    return np.array([s, mx, area, cr, cc, peak_grad], dtype=np.float32)
