"""Claim-redeem flow for edge enrollment with serial + firmware validation."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def test_claim_create_and_redeem(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/claims",
        json={
            "label": "floor3-line7",
            "site": "Plant 2",
            "expected_model": "jetson-orin-nano-8gb",
            "ttl_hours": 24,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"].startswith("ec_")
    assert body["id"].startswith("clm_")
    token = body["token"]

    edge_id = f"edge-{uuid.uuid4().hex[:8]}"
    r = await client.post(
        "/v1/claims/redeem",
        json={
            "token": token,
            "edge_id": edge_id,
            "hostname": edge_id,
            "serial": "1234567890ABCD",
            "model": "jetson-orin-nano-8gb",
            "firmware_version": "TS-G4 v0.3",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == edge_id
    assert body["serial"] == "1234567890ABCD"
    assert body["firmware_version"] == "TS-G4 v0.3"

    # Second redemption with same token must fail.
    r = await client.post(
        "/v1/claims/redeem",
        json={
            "token": token,
            "edge_id": f"edge-{uuid.uuid4().hex[:8]}",
            "serial": "OTHER-12345",
            "firmware_version": "TS-G4 v0.3",
        },
    )
    assert r.status_code == 409


async def test_redeem_rejects_unknown_firmware(client: AsyncClient) -> None:
    r = await client.post("/v1/claims", json={"label": "x"})
    token = r.json()["token"]

    r = await client.post(
        "/v1/claims/redeem",
        json={
            "token": token,
            "edge_id": f"edge-{uuid.uuid4().hex[:8]}",
            "serial": "1234567890ABCD",
            "firmware_version": "RANDOM-STRING",
        },
    )
    assert r.status_code == 422


async def test_redeem_rejects_bad_token(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/claims/redeem",
        json={
            "token": "ec_completely-bogus-token",
            "edge_id": f"edge-{uuid.uuid4().hex[:8]}",
            "serial": "1234567890ABCD",
            "firmware_version": "TS-G4 v0.3",
        },
    )
    assert r.status_code == 401


async def test_claim_revoke_blocks_redeem(client: AsyncClient) -> None:
    r = await client.post("/v1/claims", json={"label": "rev-test"})
    body = r.json()
    token = body["token"]
    claim_id = body["id"]

    r = await client.post(f"/v1/claims/{claim_id}/revoke")
    assert r.status_code == 204

    r = await client.post(
        "/v1/claims/redeem",
        json={
            "token": token,
            "edge_id": f"edge-{uuid.uuid4().hex[:8]}",
            "serial": "1234567890ABCD",
            "firmware_version": "TS-G4 v0.3",
        },
    )
    assert r.status_code == 403


async def test_claim_expected_serial_mismatch(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/claims",
        json={"label": "pinned", "expected_serial": "PINNED-SERIAL-001"},
    )
    token = r.json()["token"]

    r = await client.post(
        "/v1/claims/redeem",
        json={
            "token": token,
            "edge_id": f"edge-{uuid.uuid4().hex[:8]}",
            "serial": "DIFFERENT-SERIAL",
            "firmware_version": "TS-G4 v0.3",
        },
    )
    assert r.status_code == 422
