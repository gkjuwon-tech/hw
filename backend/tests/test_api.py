"""End-to-end API tests covering the calibration → inspection happy path."""

from __future__ import annotations

import uuid

import numpy as np
from httpx import AsyncClient


def _good_frame(rng: np.random.Generator, rows: int = 8, cols: int = 8) -> list[float]:
    frame = np.zeros((rows, cols), dtype=np.float32)
    frame[2:6, 2:6] = 180.0
    frame += rng.normal(0.0, 2.0, frame.shape).astype(np.float32)
    return np.clip(frame, 0, 255).reshape(-1).tolist()


async def test_full_loop(client: AsyncClient) -> None:
    rng = np.random.default_rng(42)
    line_id = f"line-{uuid.uuid4().hex[:8]}"

    r = await client.get("/healthz")
    assert r.status_code == 200

    r = await client.post(
        "/v1/lines",
        json={"id": line_id, "customer_tag": "test-bakery", "rows": 8, "cols": 8},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "awaiting_calibration"
    assert body["org_id"] == "org_default"
    assert body["threshold_score"] == 3.0

    for _ in range(7):
        r = await client.post(
            f"/v1/lines/{line_id}/frames", json={"data": _good_frame(rng)}
        )
        assert r.status_code == 202, r.text

    r = await client.post(f"/v1/lines/{line_id}/calibrate", json={})
    assert r.status_code == 200, r.text
    assert r.json()["n_samples"] == 7

    r = await client.post(
        f"/v1/lines/{line_id}/inspect", json={"data": _good_frame(rng)}
    )
    assert r.status_code == 200, r.text
    good = r.json()
    assert good["verdict"] == "pass"
    assert "drift_z" in good

    bad = np.array(_good_frame(rng), dtype=np.float32).reshape(8, 8)
    bad[0:3, 0:3] = 240.0
    r = await client.post(
        f"/v1/lines/{line_id}/inspect?include_heatmap=true",
        json={"data": bad.reshape(-1).tolist()},
    )
    assert r.status_code == 200, r.text
    bad_body = r.json()
    assert bad_body["score"] > good["score"]
    assert bad_body["heatmap"] is not None
    assert len(bad_body["heatmap"]) > 0


async def test_calibrate_requires_min_samples(client: AsyncClient) -> None:
    rng = np.random.default_rng(7)
    line_id = f"line-{uuid.uuid4().hex[:8]}"
    await client.post(
        "/v1/lines",
        json={"id": line_id, "customer_tag": "", "rows": 8, "cols": 8},
    )
    await client.post(
        f"/v1/lines/{line_id}/frames", json={"data": _good_frame(rng)}
    )
    r = await client.post(f"/v1/lines/{line_id}/calibrate", json={})
    assert r.status_code == 400


async def test_inspect_requires_calibration(client: AsyncClient) -> None:
    rng = np.random.default_rng(99)
    line_id = f"line-{uuid.uuid4().hex[:8]}"
    await client.post(
        "/v1/lines",
        json={"id": line_id, "customer_tag": "", "rows": 8, "cols": 8},
    )
    r = await client.post(
        f"/v1/lines/{line_id}/inspect", json={"data": _good_frame(rng)}
    )
    assert r.status_code == 409


async def test_line_patch_thresholds(client: AsyncClient) -> None:
    line_id = f"line-{uuid.uuid4().hex[:8]}"
    await client.post(
        "/v1/lines",
        json={"id": line_id, "customer_tag": "", "rows": 8, "cols": 8},
    )
    r = await client.patch(
        f"/v1/lines/{line_id}",
        json={"threshold_score": 4.5, "threshold_hits": 12},
    )
    assert r.status_code == 200, r.text
    assert r.json()["threshold_score"] == 4.5
    assert r.json()["threshold_hits"] == 12
