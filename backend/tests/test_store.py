"""Store / Stripe Checkout endpoints — mock-mode end-to-end."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def _reset_mock_state() -> None:
    from app.core.stripe_client import StripeClient

    StripeClient.reset_mock_state()


async def test_catalog_lists_hardware_and_software(client: AsyncClient) -> None:
    resp = await client.get("/v1/store/catalog")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["mock_mode"] is True
    assert body["currency"] == "usd"

    hardware = {sku["id"]: sku for sku in body["hardware"]}
    assert "tactile_edge" in hardware
    assert hardware["tactile_edge"]["unit_amount_usd"] == 1_290

    software = {plan["id"]: plan for plan in body["software"]}
    assert "tactile_cloud_pilot" in software
    assert software["tactile_cloud_pilot"]["trial_days"] == 30

    assert "US" in body["shipping_countries"]
    assert "KR" in body["shipping_countries"]


async def test_create_hardware_checkout_returns_mock_url(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/store/checkout/hardware",
        json={"sku_id": "tactile_edge", "quantity": 1},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("cs_test_mock_")
    assert body["mock"] is True
    assert body["mode"] == "payment"
    assert body["url"].startswith("http")
    assert "session_id=" in body["url"]


async def test_create_hardware_checkout_rejects_unknown_sku(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/store/checkout/hardware",
        json={"sku_id": "doesnotexist"},
    )
    assert resp.status_code == 404, resp.text


async def test_create_software_checkout_returns_subscription_url(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/store/checkout/software",
        json={
            "plan_id": "tactile_cloud_pilot",
            "hardware_session_id": "cs_test_mock_abc",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("cs_test_mock_")
    assert body["mode"] == "subscription"
    assert body["mock"] is True


async def test_full_mock_checkout_journey(client: AsyncClient) -> None:
    # 1. Create the hardware session and walk the mock-complete endpoint
    resp = await client.post("/v1/store/checkout/hardware", json={})
    hw_session_id = resp.json()["id"]

    resp = await client.post(
        "/v1/store/mock/complete",
        json={
            "session_id": hw_session_id,
            "customer_email": "buyer@example.com",
            "name": "Test Buyer",
            "phone": "+82-10-1234-5678",
            "line1": "1 Teheran-ro",
            "city": "Seoul",
            "postal_code": "06234",
            "country": "KR",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "complete"

    # 2. Fetch the order — hardware order should be paid + carry shipping
    resp = await client.get(f"/v1/store/order/{hw_session_id}")
    assert resp.status_code == 200, resp.text
    hw_order = resp.json()
    assert hw_order["mode"] == "payment"
    assert hw_order["paid"] is True
    assert hw_order["customer_email"] == "buyer@example.com"
    assert hw_order["shipping_details"]["address"]["country"] == "KR"
    assert "downloads" not in hw_order  # hardware order, no downloads yet

    # 3. Create the software subscription, complete it (no shipping)
    resp = await client.post(
        "/v1/store/checkout/software",
        json={
            "plan_id": "tactile_cloud_pilot",
            "hardware_session_id": hw_session_id,
            "customer_email": "buyer@example.com",
        },
    )
    sw_session_id = resp.json()["id"]
    resp = await client.post(
        "/v1/store/mock/complete",
        json={
            "session_id": sw_session_id,
            "customer_email": "buyer@example.com",
        },
    )
    assert resp.status_code == 200

    # 4. Fetch the software order — should be paid + carry download URLs
    resp = await client.get(f"/v1/store/order/{sw_session_id}")
    assert resp.status_code == 200, resp.text
    sw_order = resp.json()
    assert sw_order["mode"] == "subscription"
    assert sw_order["paid"] is True
    assert sw_order["trial_days"] == 30
    assert sw_order["subscription"] is not None
    assert sw_order["subscription"].startswith("sub_test_mock_")
    assert "downloads" in sw_order
    assert "windows" in sw_order["downloads"]
    assert "mac" in sw_order["downloads"]
    assert "linux" in sw_order["downloads"]
    assert sw_order["metadata"]["plan_id"] == "tactile_cloud_pilot"
    assert sw_order["metadata"]["hardware_session_id"] == hw_session_id


async def test_get_order_404_for_unknown_session(client: AsyncClient) -> None:
    resp = await client.get("/v1/store/order/cs_test_mock_unknown")
    assert resp.status_code == 404


async def test_get_mock_session_round_trip(client: AsyncClient) -> None:
    resp = await client.post("/v1/store/checkout/hardware", json={"quantity": 2})
    sid = resp.json()["id"]

    resp = await client.get(f"/v1/store/mock/session/{sid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == sid
    assert body["mode"] == "payment"
    assert body["line_items"][0]["quantity"] == 2
    assert body["amount_total"] == 1_290 * 100 * 2
    assert body["metadata"]["sku_id"] == "tactile_edge"


async def test_webhook_returns_ok_in_mock_mode(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/store/webhook",
        content=b'{"type":"checkout.session.completed"}',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["received"] == "mock"
