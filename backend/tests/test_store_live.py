"""Live-mode store behavior: Stripe webhook signature verification.

These tests stand up the app with a TEST Stripe secret + webhook secret so
``is_mock_mode()`` is False. They never reach out to api.stripe.com — the
checkout-creation endpoints are deliberately not exercised here; only the
webhook verification path, which is pure local HMAC, is tested.
"""

from __future__ import annotations

import hashlib
import hmac
import sys
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

WEBHOOK_SECRET = "whsec_test_dummy_secret"  # noqa: S105 — test fixture


def _sign(payload: bytes, secret: str = WEBHOOK_SECRET, ts: int | None = None) -> str:
    ts = int(ts if ts is not None else time.time())
    mac = hmac.new(secret.encode("utf-8"), f"{ts}.".encode() + payload, hashlib.sha256)
    return f"t={ts},v1={mac.hexdigest()}"


@pytest.fixture
async def live_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    tmp = Path(tempfile.mkdtemp(prefix="conet-test-live-"))
    monkeypatch.setenv("CONET_DATA_DIR", str(tmp))
    monkeypatch.setenv("CONET_DATABASE_URL", f"sqlite+aiosqlite:///{tmp / 'test.db'}")
    monkeypatch.setenv("CONET_LOG_JSON", "false")
    monkeypatch.setenv("CONET_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("CONET_STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("CONET_STRIPE_PUBLISHABLE_KEY", "pk_test_dummy")
    monkeypatch.setenv("CONET_STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("CONET_STRIPE_MOCK_MODE", "false")
    for mod in [m for m in list(sys.modules) if m.startswith("app")]:
        del sys.modules[mod]

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            yield c


def test_verify_stripe_signature_unit() -> None:
    from app.core.stripe_client import verify_stripe_signature

    payload = b'{"id":"evt_1","type":"checkout.session.completed"}'
    header = _sign(payload)

    assert verify_stripe_signature(payload, header, WEBHOOK_SECRET) is True
    # Wrong secret, tampered body, and stale timestamp all fail.
    assert verify_stripe_signature(payload, header, "whsec_other") is False
    assert verify_stripe_signature(payload + b" ", header, WEBHOOK_SECRET) is False
    stale = _sign(payload, ts=int(time.time()) - 10_000)
    assert verify_stripe_signature(payload, stale, WEBHOOK_SECRET) is False
    assert verify_stripe_signature(payload, "garbage", WEBHOOK_SECRET) is False


async def test_catalog_reports_live_mode(live_client: AsyncClient) -> None:
    resp = await live_client.get("/v1/store/catalog")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mock_mode"] is False
    assert body["publishable_key"] == "pk_test_dummy"


async def test_webhook_accepts_valid_signature(live_client: AsyncClient) -> None:
    payload = (
        b'{"id":"evt_test_1","type":"checkout.session.completed",'
        b'"data":{"object":{"id":"cs_test_123"}}}'
    )
    resp = await live_client.post(
        "/v1/store/webhook",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _sign(payload),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "verified"
    assert body["type"] == "checkout.session.completed"


async def test_webhook_rejects_bad_signature(live_client: AsyncClient) -> None:
    payload = b'{"id":"evt_test_2","type":"checkout.session.completed"}'
    resp = await live_client.post(
        "/v1/store/webhook",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": "t=1,v1=deadbeef",
        },
    )
    assert resp.status_code == 400, resp.text


async def test_webhook_rejects_missing_signature(live_client: AsyncClient) -> None:
    payload = b'{"id":"evt_test_3","type":"checkout.session.completed"}'
    resp = await live_client.post(
        "/v1/store/webhook",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400, resp.text
