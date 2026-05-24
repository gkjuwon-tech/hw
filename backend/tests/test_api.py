"""End-to-end API tests covering the calibration → inspection happy path."""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="conet-test-"))
    monkeypatch.setenv("CONET_DATA_DIR", str(tmp))
    monkeypatch.setenv("CONET_DATABASE_URL", f"sqlite+aiosqlite:///{tmp / 'test.db'}")
    # Force re-import so the fresh env is picked up.
    for mod in [m for m in list(os.sys.modules) if m.startswith("app")]:
        del os.sys.modules[mod]


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            yield c


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
    assert r.json()["status"] == "awaiting_calibration"

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

    bad = np.array(_good_frame(rng), dtype=np.float32).reshape(8, 8)
    bad[0:3, 0:3] = 240.0
    r = await client.post(
        f"/v1/lines/{line_id}/inspect",
        json={"data": bad.reshape(-1).tolist()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["score"] > good["score"]


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
