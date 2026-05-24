"""One-class tactile anomaly detector.

This is a deliberately small reference implementation. Production swaps it for a
PaDiM-class or PatchCore-class model adapted to pressure-time fields. The
contract (``fit`` / ``score`` / ``serialize`` / ``load``) is what the rest of
the service depends on.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

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

    heatmap: list[list[float]] = field(default_factory=list)
    """Per-cell sigma deviation, optionally downsampled. Shape ``(h', w')``."""


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
            heatmap=_downsample(cell_dev, max_cells=4096).tolist(),
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


def _downsample(arr: np.ndarray, max_cells: int = 4096) -> np.ndarray:
    """Box-average ``arr`` down so the result has at most ``max_cells`` cells.

    Used to keep the per-frame heatmap payload bounded regardless of the
    underlying sensor resolution. We deliberately avoid SciPy so this stays
    a single numpy dependency.
    """
    if arr.size <= max_cells:
        return arr.astype(np.float32)
    h, w = arr.shape
    factor = max(1, int(np.ceil(np.sqrt(arr.size / float(max_cells)))))
    new_h = max(1, h // factor)
    new_w = max(1, w // factor)
    # Trim to multiples and reshape into blocks for vectorized mean.
    trim_h = new_h * factor
    trim_w = new_w * factor
    trimmed = arr[:trim_h, :trim_w]
    return (
        trimmed.reshape(new_h, factor, new_w, factor)
        .mean(axis=(1, 3))
        .astype(np.float32)
    )


@dataclass
class RollingDriftTracker:
    """Online mean/std of recent inspection scores per line, with a z-score.

    The tracker stores the last ``window`` scores in memory and reports the
    standard score (``z``) of the current rolling mean against the calibration
    cohort. Production replaces this with EWMA or CUSUM but the public shape
    is the same.
    """

    window: int = 200
    baseline_mean: float = 0.0
    baseline_std: float = 1.0
    _samples: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if not isinstance(self._samples, deque):  # type: ignore[unreachable]
            self._samples = deque(maxlen=self.window)
        else:
            self._samples = deque(self._samples, maxlen=self.window)

    def calibrate(self, scores: list[float]) -> None:
        if not scores:
            return
        arr = np.asarray(scores, dtype=np.float32)
        self.baseline_mean = float(arr.mean())
        self.baseline_std = max(0.05, float(arr.std()))

    def observe(self, score: float) -> float:
        self._samples.append(float(score))
        return self.z()

    def z(self) -> float:
        if not self._samples:
            return 0.0
        m = float(np.mean(self._samples))
        return float((m - self.baseline_mean) / self.baseline_std)

    def reset(self) -> None:
        self._samples.clear()
