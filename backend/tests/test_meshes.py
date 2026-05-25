"""Mesh segment installation, lookup, lifetime/health updates."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _make_line(client: AsyncClient, rows: int = 8, cols: int = 8) -> str:
    line_id = f"line-{uuid.uuid4().hex[:8]}"
    r = await client.post(
        "/v1/lines",
        json={"id": line_id, "customer_tag": "test", "rows": rows, "cols": cols},
    )
    assert r.status_code == 201, r.text
    return line_id


async def test_install_and_list_mesh(client: AsyncClient) -> None:
    line_id = await _make_line(client)
    mesh_id = f"mesh-{uuid.uuid4().hex[:8]}"

    r = await client.post(
        "/v1/meshes",
        json={
            "id": mesh_id,
            "line_id": line_id,
            "roll_lot": "TM350-2026W21-A",
            "belt_width_mm": 350,
            "length_mm": 1500,
            "rows": 8,
            "cols": 8,
            "expected_lifetime_days": 180,
            "notes": "first install",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == mesh_id
    assert body["line_id"] == line_id
    assert body["health_pct"] == 100.0

    r = await client.get(f"/v1/meshes?line_id={line_id}")
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()]
    assert ids == [mesh_id]


async def test_mesh_requires_existing_line(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/meshes",
        json={
            "id": f"mesh-{uuid.uuid4().hex[:8]}",
            "line_id": "no-such-line",
            "roll_lot": "TM-X",
            "rows": 8,
            "cols": 8,
        },
    )
    assert r.status_code == 404


async def test_mesh_update_health(client: AsyncClient) -> None:
    line_id = await _make_line(client)
    mesh_id = f"mesh-{uuid.uuid4().hex[:8]}"
    r = await client.post(
        "/v1/meshes",
        json={
            "id": mesh_id,
            "line_id": line_id,
            "roll_lot": "TM-1",
            "rows": 8,
            "cols": 8,
        },
    )
    assert r.status_code == 201

    r = await client.patch(
        f"/v1/meshes/{mesh_id}",
        json={"health_pct": 87.5, "dead_cells": 4, "notes": "drift on row 3"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["health_pct"] == 87.5
    assert body["dead_cells"] == 4
    assert "drift" in body["notes"]


async def test_mesh_link_to_edge(client: AsyncClient) -> None:
    line_id = await _make_line(client)
    edge_id = f"edge-{uuid.uuid4().hex[:8]}"
    mesh_id = f"mesh-{uuid.uuid4().hex[:8]}"

    r = await client.post(
        "/v1/edges",
        json={
            "id": edge_id,
            "hostname": edge_id,
            "model": "jetson-orin-nano-8gb",
            "serial": "TEST-1234567890",
        },
    )
    assert r.status_code == 201

    r = await client.post(
        "/v1/meshes",
        json={
            "id": mesh_id,
            "line_id": line_id,
            "edge_id": edge_id,
            "roll_lot": "TM-2",
            "rows": 8,
            "cols": 8,
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["edge_id"] == edge_id

    r = await client.get(f"/v1/meshes?edge_id={edge_id}")
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [mesh_id]


async def test_mesh_delete(client: AsyncClient) -> None:
    line_id = await _make_line(client)
    mesh_id = f"mesh-{uuid.uuid4().hex[:8]}"
    await client.post(
        "/v1/meshes",
        json={
            "id": mesh_id,
            "line_id": line_id,
            "roll_lot": "TM-3",
            "rows": 8,
            "cols": 8,
        },
    )
    r = await client.delete(f"/v1/meshes/{mesh_id}")
    assert r.status_code == 204
    r = await client.get(f"/v1/meshes/{mesh_id}")
    assert r.status_code == 404
