"""Service configuration.

Settings are read from environment variables. Defaults are tuned for local
development; production overrides come from the platform (Fly.io secrets / env).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_data_dir() -> Path:
    here = Path(__file__).resolve().parent.parent.parent
    return here / "data"


@dataclass(frozen=True)
class Settings:
    """Process-wide settings."""

    database_url: str = os.environ.get(
        "CONET_DATABASE_URL", "sqlite+aiosqlite:///./conet_tactile.db"
    )
    data_dir: Path = Path(os.environ.get("CONET_DATA_DIR", str(_default_data_dir())))
    """Directory for on-disk numpy baselines and recent-frame buffers."""

    min_calibration_samples: int = int(os.environ.get("CONET_MIN_CALIB", "5"))
    """Minimum known-good samples required to finalize a baseline."""

    anomaly_sigma_threshold: float = float(os.environ.get("CONET_SIGMA", "3.0"))
    """Per-cell deviation in standard deviations above which a cell is "hit"."""

    event_buffer_size: int = int(os.environ.get("CONET_EVENT_BUFFER", "256"))
    """Per-line ring buffer of recent inspections served over SSE."""


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
