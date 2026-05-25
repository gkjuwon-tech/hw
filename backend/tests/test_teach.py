"""Teach wizard: 5-sample capture + auto-fit + arm-line flow."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _make_line(client: AsyncClient, rows: int = 8, cols: int = 8) -> str:
    line_id = f"line-{uuid.uuid4().hex[:8]}"
    r = await client.post(
        "/v1/lines",
        json={
            "id": line_id,
            "customer_tag": "teach-line",
            "rows": rows,
            "cols": cols,
        },
    )
    assert r.status_code == 201, r.text
    return line_id


async def _make_edge(client: AsyncClient) -> str:
    edge_id = f"edge-{uuid.uuid4().hex[:8]}"
    r = await client.post(
        "/v1/edges",
        json={
            "id": edge_id,
            "hostname": edge_id,
            "serial": "TEST-1234567890",
            "model": "jetson-orin-nano-8gb",
        },
    )
    assert r.status_code == 201, r.text
    return edge_id


async def test_teach_full_happy_path(client: AsyncClient) -> None:
    line_id = await _make_line(client, rows=8, cols=8)
    edge_id = await _make_edge(client)

    r = await client.post(
        f"/v1/edges/{edge_id}/teach/start",
        json={"line_id": line_id},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["required_samples"] == 5
    assert body["status"] == "in_progress"

    sample = [1.0] * 64  # 8x8
    for i in range(5):
        r = await client.post(
            f"/v1/edges/{edge_id}/teach/capture",
            json={"data": [v + i * 0.01 for v in sample]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["captured"] == i + 1

    r = await client.get(f"/v1/edges/{edge_id}/teach/status")
    assert r.status_code == 200
    assert r.json()["captured"] == 5
    assert r.json()["remaining"] == 0

    r = await client.post(f"/v1/edges/{edge_id}/teach/finish")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_samples"] == 5
    assert body["line_status"] == "live"

    r = await client.get(f"/v1/lines/{line_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "live"


async def test_teach_rejects_finish_before_5_samples(client: AsyncClient) -> None:
    line_id = await _make_line(client)
    edge_id = await _make_edge(client)

    r = await client.post(
        f"/v1/edges/{edge_id}/teach/start",
        json={"line_id": line_id},
    )
    assert r.status_code == 201

    for _ in range(2):
        r = await client.post(
            f"/v1/edges/{edge_id}/teach/capture",
            json={"data": [1.0] * 64},
        )
        assert r.status_code == 200

    r = await client.post(f"/v1/edges/{edge_id}/teach/finish")
    assert r.status_code == 400


async def test_teach_rejects_wrong_frame_size(client: AsyncClient) -> None:
    line_id = await _make_line(client, rows=8, cols=8)
    edge_id = await _make_edge(client)
    await client.post(
        f"/v1/edges/{edge_id}/teach/start",
        json={"line_id": line_id},
    )

    r = await client.post(
        f"/v1/edges/{edge_id}/teach/capture",
        json={"data": [1.0] * 32},
    )
    assert r.status_code == 422


async def test_teach_abort(client: AsyncClient) -> None:
    line_id = await _make_line(client)
    edge_id = await _make_edge(client)
    await client.post(
        f"/v1/edges/{edge_id}/teach/start",
        json={"line_id": line_id},
    )

    r = await client.delete(f"/v1/edges/{edge_id}/teach")
    assert r.status_code == 204

    r = await client.get(f"/v1/edges/{edge_id}/teach/status")
    assert r.status_code == 200
    assert r.json()["status"] == "idle"
