"""Mesh fabric — edge announce, topology, failover."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _make_edge(client: AsyncClient) -> str:
    edge_id = f"edge-{uuid.uuid4().hex[:8]}"
    r = await client.post(
        "/v1/edges",
        json={
            "id": edge_id,
            "hostname": edge_id,
            "serial": "TEST-1234567890",
        },
    )
    assert r.status_code == 201, r.text
    return edge_id


async def test_mesh_announce_and_topology(client: AsyncClient) -> None:
    e1 = await _make_edge(client)
    e2 = await _make_edge(client)

    r = await client.post(
        "/v1/mesh/announce",
        json={
            "edge_id": e1,
            "ip": "10.0.1.10",
            "port": 9100,
            "peers": [e2],
            "capacity_free_pct": 80.0,
            "latency_to_peers_ms": {e2: 3.2},
        },
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        "/v1/mesh/announce",
        json={
            "edge_id": e2,
            "ip": "10.0.1.11",
            "port": 9100,
            "peers": [e1],
            "capacity_free_pct": 60.0,
            "latency_to_peers_ms": {e1: 3.4},
        },
    )
    assert r.status_code == 200

    r = await client.get("/v1/mesh/topology")
    assert r.status_code == 200
    body = r.json()
    assert body["alive_count"] >= 2
    ids = {n["edge_id"] for n in body["nodes"]}
    assert e1 in ids and e2 in ids


async def test_mesh_peers_of_edge(client: AsyncClient) -> None:
    e1 = await _make_edge(client)
    e2 = await _make_edge(client)

    await client.post(
        "/v1/mesh/announce",
        json={"edge_id": e1, "ip": "10.0.1.10", "peers": [e2]},
    )
    await client.post(
        "/v1/mesh/announce",
        json={"edge_id": e2, "ip": "10.0.1.11", "peers": []},
    )

    r = await client.get(f"/v1/mesh/peers/{e1}")
    assert r.status_code == 200
    peers = r.json()
    assert len(peers) == 1
    assert peers[0]["edge_id"] == e2


async def test_mesh_announce_unknown_edge_404(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/mesh/announce",
        json={"edge_id": "edge-does-not-exist", "ip": "10.0.0.1"},
    )
    assert r.status_code == 404
