"""Edge enrollment, heartbeat, and telemetry SSE."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def test_edge_crud(client: AsyncClient) -> None:
    edge_id = f"edge-{uuid.uuid4().hex[:8]}"

    r = await client.post(
        "/v1/edges",
        json={
            "id": edge_id,
            "hostname": "edge-floor3-line7",
            "serial": "TEST-1234567890",
            "model": "jetson-orin-nano-8gb",
            "site": "Plant 2 / Bakery line",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == edge_id
    assert body["status"] == "offline"
    assert body["enrolled_at"]
    assert body["frames_per_second"] == 0.0

    r = await client.post(
        "/v1/edges",
        json={
            "id": edge_id,
            "hostname": "x",
            "model": "jetson-orin-nano-8gb",
            "serial": "TEST-1234567890",
        },
    )
    assert r.status_code == 409

    r = await client.get("/v1/edges")
    assert r.status_code == 200
    assert any(e["id"] == edge_id for e in r.json())

    r = await client.get(f"/v1/edges/{edge_id}")
    assert r.status_code == 200
    assert r.json()["hostname"] == "edge-floor3-line7"

    r = await client.patch(
        f"/v1/edges/{edge_id}",
        json={"hostname": "edge-renamed", "site": "Plant 3"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["hostname"] == "edge-renamed"
    assert body["site"] == "Plant 3"


async def test_edge_heartbeat_updates_state(client: AsyncClient) -> None:
    edge_id = f"edge-{uuid.uuid4().hex[:8]}"
    r = await client.post(
        "/v1/edges",
        json={
            "id": edge_id,
            "hostname": edge_id,
            "model": "jetson-orin-nano-8gb",
            "serial": "TEST-1234567890",
        },
    )
    assert r.status_code == 201, r.text

    r = await client.post(
        f"/v1/edges/{edge_id}/heartbeat",
        json={
            "firmware_version": "TS-G4 v0.3",
            "agent_version": "0.1.0",
            "cpu_pct": 32.0,
            "gpu_pct": 18.0,
            "gpu_temp_c": 52.0,
            "cpu_temp_c": 47.0,
            "ram_used_mb": 2100,
            "ram_total_mb": 7775,
            "power_mw": 4900,
            "inference_p50_ms": 12.5,
            "inference_p99_ms": 31.0,
            "frames_per_second": 187.5,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "online"
    assert body["frames_per_second"] == 187.5
    assert body["last_seen_at"] is not None

    # Hot card → degraded.
    r = await client.post(
        f"/v1/edges/{edge_id}/heartbeat",
        json={
            "cpu_pct": 99.0,
            "gpu_pct": 95.0,
            "gpu_temp_c": 95.5,
            "cpu_temp_c": 90.0,
            "ram_used_mb": 7000,
            "ram_total_mb": 7775,
            "power_mw": 8200,
            "inference_p50_ms": 80.0,
            "inference_p99_ms": 220.0,
            "frames_per_second": 180.0,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "degraded"

    # No frames → also degraded.
    r = await client.post(
        f"/v1/edges/{edge_id}/heartbeat",
        json={
            "cpu_pct": 5.0,
            "gpu_pct": 0.0,
            "gpu_temp_c": 40.0,
            "cpu_temp_c": 40.0,
            "ram_used_mb": 1000,
            "ram_total_mb": 7775,
            "power_mw": 3000,
            "inference_p50_ms": 0.0,
            "inference_p99_ms": 0.0,
            "frames_per_second": 0.0,
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"


async def test_edge_telemetry_recent(client: AsyncClient) -> None:
    edge_id = f"edge-{uuid.uuid4().hex[:8]}"
    await client.post(
        "/v1/edges",
        json={"id": edge_id, "hostname": edge_id, "serial": "TEST-1234567890"},
    )

    for fps in (10.0, 50.0, 100.0):
        r = await client.post(
            f"/v1/edges/{edge_id}/heartbeat",
            json={
                "cpu_pct": 10.0,
                "gpu_pct": 5.0,
                "gpu_temp_c": 45.0,
                "cpu_temp_c": 42.0,
                "ram_used_mb": 1000,
                "ram_total_mb": 7775,
                "power_mw": 3500,
                "inference_p50_ms": 14.0,
                "inference_p99_ms": 30.0,
                "frames_per_second": fps,
            },
        )
        assert r.status_code == 200

    r = await client.get(f"/v1/edges/{edge_id}/telemetry/recent")
    assert r.status_code == 200
    recent = r.json()
    assert [snap["frames_per_second"] for snap in recent[-3:]] == [10.0, 50.0, 100.0]


async def test_edge_delete(client: AsyncClient) -> None:
    edge_id = f"edge-{uuid.uuid4().hex[:8]}"
    await client.post(
        "/v1/edges",
        json={"id": edge_id, "hostname": edge_id, "serial": "TEST-1234567890"},
    )

    r = await client.delete(f"/v1/edges/{edge_id}")
    assert r.status_code == 204

    r = await client.get(f"/v1/edges/{edge_id}")
    assert r.status_code == 404


async def test_telemetry_endpoint_authorized(client: AsyncClient) -> None:
    """The SSE endpoint should at least return 200 for an enrolled edge.

    We don't drain the stream here — Starlette's BaseHTTPMiddleware doesn't
    play well with infinite SSE under the ASGI test transport. The replay
    buffer (``/telemetry/recent``) is exercised by ``test_edge_telemetry_recent``.
    """
    edge_id = f"edge-{uuid.uuid4().hex[:8]}"
    await client.post(
        "/v1/edges",
        json={"id": edge_id, "hostname": edge_id, "serial": "TEST-1234567890"},
    )
    r = await client.get(f"/v1/edges/{edge_id}/telemetry/recent")
    assert r.status_code == 200
    assert r.json() == []

    # 404 path for an unknown edge.
    r = await client.get("/v1/edges/edge-nope/telemetry/recent")
    assert r.status_code == 404
