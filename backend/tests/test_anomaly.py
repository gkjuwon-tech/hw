"""Unit tests for the one-class anomaly baseline."""

from __future__ import annotations

import numpy as np

from app.core.anomaly import Baseline


def _good_sample(rng: np.random.Generator) -> np.ndarray:
    frame = np.zeros((16, 16), dtype=np.float32)
    frame[5:11, 5:11] = 180.0
    frame += rng.normal(0.0, 2.0, frame.shape).astype(np.float32)
    return np.clip(frame, 0, 255)


def test_fit_and_serialize_roundtrip() -> None:
    rng = np.random.default_rng(0)
    samples = [_good_sample(rng) for _ in range(6)]
    baseline = Baseline.fit(samples)
    blob = baseline.to_bytes()
    restored = Baseline.from_bytes(blob)
    np.testing.assert_allclose(restored.mean, baseline.mean)
    np.testing.assert_allclose(restored.std, baseline.std)
    assert restored.rows == 16 and restored.cols == 16
    assert restored.n_samples == 6


def test_good_sample_scores_low_bad_sample_scores_high() -> None:
    rng = np.random.default_rng(1)
    samples = [_good_sample(rng) for _ in range(8)]
    baseline = Baseline.fit(samples)

    good_score = baseline.score(_good_sample(rng))
    assert good_score.score < 5.0
    assert good_score.hits < 20

    bad = _good_sample(rng)
    bad[2:6, 2:6] = 240.0  # extra hot region — defect
    bad_score = baseline.score(bad)
    assert bad_score.score > good_score.score
    assert bad_score.hits > good_score.hits
