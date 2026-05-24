"""RollingDriftTracker math."""

from __future__ import annotations

import numpy as np

from app.core.anomaly import RollingDriftTracker


def test_drift_tracker_z_is_zero_at_baseline() -> None:
    rng = np.random.default_rng(0)
    cohort = [float(x) for x in rng.normal(1.0, 0.1, size=50)]
    tracker = RollingDriftTracker(window=200)
    tracker.calibrate(cohort)

    # Observing the same distribution should keep z near zero.
    for _ in range(50):
        tracker.observe(float(rng.normal(1.0, 0.1)))
    assert abs(tracker.z()) < 1.5


def test_drift_tracker_detects_shift() -> None:
    rng = np.random.default_rng(1)
    cohort = [float(x) for x in rng.normal(1.0, 0.1, size=200)]
    tracker = RollingDriftTracker(window=200)
    tracker.calibrate(cohort)

    # Shifted distribution — clearly anomalous.
    for _ in range(200):
        tracker.observe(float(rng.normal(2.5, 0.1)))
    assert tracker.z() > 3.0
