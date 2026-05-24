"""Disk storage for baselines and the per-line frame buffer.

Baselines are persisted as `.npz` files under ``settings.data_dir``. The recent
frame ring buffer for ongoing calibration is held in process memory only — it
is rebuilt by re-streaming frames after a restart, which matches how the Edge
behaves anyway.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np

from app.core.anomaly import Baseline
from app.core.config import settings


def _baseline_path(line_id: str) -> Path:
    safe = "".join(c for c in line_id if c.isalnum() or c in "-_")
    return settings.data_dir / "baselines" / f"{safe}.npz"


def save_baseline(line_id: str, baseline: Baseline) -> Path:
    path = _baseline_path(line_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(baseline.to_bytes())
    return path


def load_baseline(line_id: str) -> Baseline | None:
    path = _baseline_path(line_id)
    if not path.exists():
        return None
    return Baseline.from_bytes(path.read_bytes())


def baseline_exists(line_id: str) -> bool:
    return _baseline_path(line_id).exists()


class CalibrationBuffer:
    """In-process ring buffer of calibration samples per line."""

    def __init__(self) -> None:
        self._buf: dict[str, deque[np.ndarray]] = {}

    def append(self, line_id: str, frame: np.ndarray, max_samples: int = 64) -> int:
        dq = self._buf.setdefault(line_id, deque(maxlen=max_samples))
        dq.append(frame.copy())
        return len(dq)

    def take(self, line_id: str, n: int) -> list[np.ndarray]:
        """Pop up to ``n`` most-recent frames (oldest first)."""
        dq = self._buf.get(line_id)
        if not dq:
            return []
        take = list(dq)[-n:]
        dq.clear()
        return take

    def size(self, line_id: str) -> int:
        return len(self._buf.get(line_id, ()))

    def reset(self, line_id: str) -> None:
        self._buf.pop(line_id, None)


calibration_buffer = CalibrationBuffer()
