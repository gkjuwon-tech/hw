"""Webhook registration, delivery, signature, and retry behavior."""

from __future__ import annotations

import asyncio

import httpx
import numpy as np
import respx
from httpx import AsyncClient

from app.core.security import verify_webhook_signature


def _good_frame(rng: np.random.Generator, rows: int = 8, cols: int = 8) -> list[float]:
    frame = np.zeros((rows, cols), dtype=np.float32)
    frame[2:6, 2:6] = 180.0
    frame += rng.normal(0.0, 2.0, frame.shape).astype(np.float32)
    return np.clip(frame, 0, 255).reshape(-1).tolist()


async def test_register_webhook_returns_secret_once(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/webhooks",
        json={
            "url": "https://example.invalid/hook",
            "events": ["inspection.failed"],
            "description": "test",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["secret"]
    assert len(body["secret"]) > 30
    assert body["events"] == ["inspection.failed"]

    # Subsequent listing must not include the secret.
    r = await client.get("/v1/webhooks")
    assert r.status_code == 200
    listed = r.json()
    assert listed[0]["id"] == body["id"]
    assert "secret" not in listed[0]


async def test_webhook_delivered_with_valid_signature(client: AsyncClient) -> None:
    """End-to-end: failing inspection enqueues + dispatcher signs + POSTs."""
    target = "https://example.invalid/hook"
    r = await client.post(
        "/v1/webhooks",
        json={"url": target, "events": ["inspection.failed"]},
    )
    assert r.status_code == 201, r.text
    secret = r.json()["secret"]

    # Calibrate a line.
    rng = np.random.default_rng(7)
    await client.post(
        "/v1/lines",
        json={"id": "wh-line", "customer_tag": "", "rows": 8, "cols": 8},
    )
    for _ in range(7):
        await client.post("/v1/lines/wh-line/frames", json={"data": _good_frame(rng)})
    r = await client.post("/v1/lines/wh-line/calibrate", json={})
    assert r.status_code == 200, r.text

    # Run an inspection that will fail and capture the outbound POST.
    bad = np.array(_good_frame(rng), dtype=np.float32).reshape(8, 8)
    bad[:] = 230.0
    captured: list[httpx.Request] = []

    async def _capture(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text="ok")

    with respx.mock(assert_all_called=False) as mock:
        mock.post(target).mock(side_effect=_capture)
        r = await client.post(
            "/v1/lines/wh-line/inspect",
            json={"data": bad.reshape(-1).tolist()},
        )
        assert r.status_code == 200
        assert r.json()["verdict"] == "fail"

        # The dispatcher polls roughly every 2 seconds; nudge until delivery
        # lands or we hit a generous ceiling.
        deadline = asyncio.get_event_loop().time() + 8.0
        while not captured and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.2)

    assert captured, "webhook was never delivered"
    request = captured[0]
    assert request.headers["x-conet-event"] == "inspection.failed"
    sig = request.headers["x-conet-signature"]
    assert verify_webhook_signature(secret, request.content, sig)

    # Delivery row should be marked succeeded.
    list_resp = await client.get("/v1/webhooks")
    wh_id = list_resp.json()[0]["id"]
    deliveries = await client.get(f"/v1/webhooks/{wh_id}/deliveries")
    assert deliveries.status_code == 200
    assert any(d["status"] == "succeeded" for d in deliveries.json())
