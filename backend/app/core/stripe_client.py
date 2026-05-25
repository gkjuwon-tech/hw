"""Thin Stripe Checkout wrapper with a mock-mode fallback.

The store needs to support two deployment shapes:

1.  **Live mode** — ``CONET_STRIPE_SECRET_KEY`` is set and
    ``CONET_STRIPE_MOCK_MODE`` is false. The wrapper talks to the real
    Stripe API over HTTPS to create Checkout Sessions and retrieve their
    status. This is what production uses.

2.  **Mock mode** — the secret key is unset or mock mode is forced. The
    wrapper generates deterministic session ids prefixed ``cs_test_mock_``
    and serves a pretend Stripe-hosted page from ``GET
    /v1/store/mock-checkout/{session_id}``. The marketing site can demo
    the full purchase journey — including shipping-address collection,
    subscription trial, and download delivery — without any external
    credentials. Useful for local development, CI, and recorded walkthroughs.

No external Python SDK is required: live mode calls Stripe's REST API
directly via ``httpx``, which is already a dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("conet.store.stripe")

STRIPE_API_BASE = "https://api.stripe.com/v1"

# Reject webhook events whose signature timestamp is older than this, to
# defeat replay. Matches Stripe's own default tolerance.
STRIPE_SIGNATURE_TOLERANCE_SECONDS = 300


def verify_stripe_signature(
    payload: bytes,
    sig_header: str,
    secret: str,
    *,
    tolerance: int = STRIPE_SIGNATURE_TOLERANCE_SECONDS,
    now: int | None = None,
) -> bool:
    """Verify a ``Stripe-Signature`` header against the raw request body.

    Stripe signs ``"{timestamp}.{payload}"`` with HMAC-SHA256 keyed on the
    endpoint's ``whsec_…`` secret and ships it as
    ``t=<unix>,v1=<hex>[,v1=<hex>…]``. We recompute the MAC and compare in
    constant time against every ``v1`` scheme present, then enforce the
    timestamp tolerance to reject replays. This mirrors
    ``stripe.Webhook.construct_event`` without pulling in the SDK.
    """
    if not sig_header or not secret:
        return False

    timestamp: str | None = None
    signatures: list[str] = []
    for chunk in sig_header.split(","):
        key, _, value = chunk.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)

    if timestamp is None or not signatures:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False

    current = int(now if now is not None else time.time())
    if abs(current - ts) > tolerance:
        return False

    expected = hmac.new(
        secret.encode("utf-8"), f"{ts}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)


@dataclass
class MockSession:
    """A lightweight in-memory record of a pretend Checkout Session."""

    id: str
    mode: str  # "payment" | "subscription"
    url: str
    success_url: str
    cancel_url: str
    customer_email: str | None = None
    line_items: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    payment_status: str = "unpaid"  # "unpaid" | "paid"
    status: str = "open"  # "open" | "complete" | "expired"
    shipping_details: dict[str, Any] | None = None
    customer_details: dict[str, Any] | None = None
    amount_total: int = 0
    currency: str = "usd"
    subscription_id: str | None = None
    created_at: float = field(default_factory=time.time)


_MOCK_SESSIONS: dict[str, MockSession] = {}


def is_mock_mode() -> bool:
    """True when the store should run without calling the Stripe API."""
    return settings.stripe_mock_mode or not settings.stripe_secret_key


def _mock_session_id(prefix: str = "cs_test_mock_") -> str:
    return f"{prefix}{secrets.token_urlsafe(18)}"


def _mock_url_for(session_id: str) -> str:
    base = settings.store_success_url.rsplit("/", 1)[0]
    return f"{base}/mock-checkout.html?session_id={session_id}"


def _form_for_payment(
    *,
    sku_label: str,
    unit_amount_usd: int,
    quantity: int,
    success_url: str,
    cancel_url: str,
    metadata: dict[str, str],
    customer_email: str | None,
) -> list[tuple[str, str]]:
    form: list[tuple[str, str]] = [
        ("mode", "payment"),
        ("success_url", success_url + "?session_id={CHECKOUT_SESSION_ID}"),
        ("cancel_url", cancel_url),
        ("line_items[0][quantity]", str(quantity)),
        ("line_items[0][price_data][currency]", settings.store_default_currency),
        ("line_items[0][price_data][unit_amount]", str(unit_amount_usd * 100)),
        ("line_items[0][price_data][product_data][name]", sku_label),
        ("shipping_address_collection[allowed_countries][]", "US"),
        ("shipping_address_collection[allowed_countries][]", "KR"),
        ("shipping_address_collection[allowed_countries][]", "JP"),
        ("shipping_address_collection[allowed_countries][]", "DE"),
        ("shipping_address_collection[allowed_countries][]", "GB"),
        ("shipping_address_collection[allowed_countries][]", "FR"),
        ("shipping_address_collection[allowed_countries][]", "CA"),
        ("phone_number_collection[enabled]", "true"),
    ]
    for k, v in metadata.items():
        form.append((f"metadata[{k}]", v))
    if customer_email:
        form.append(("customer_email", customer_email))
    return form


def _form_for_subscription(
    *,
    plan_label: str,
    monthly_amount_usd: int,
    trial_days: int,
    success_url: str,
    cancel_url: str,
    metadata: dict[str, str],
    customer_email: str | None,
) -> list[tuple[str, str]]:
    form: list[tuple[str, str]] = [
        ("mode", "subscription"),
        ("success_url", success_url + "?session_id={CHECKOUT_SESSION_ID}"),
        ("cancel_url", cancel_url),
        ("line_items[0][quantity]", "1"),
        ("line_items[0][price_data][currency]", settings.store_default_currency),
        ("line_items[0][price_data][unit_amount]", str(monthly_amount_usd * 100)),
        ("line_items[0][price_data][recurring][interval]", "month"),
        ("line_items[0][price_data][product_data][name]", plan_label),
        ("subscription_data[trial_period_days]", str(trial_days)),
    ]
    for k, v in metadata.items():
        form.append((f"metadata[{k}]", v))
        form.append((f"subscription_data[metadata][{k}]", v))
    if customer_email:
        form.append(("customer_email", customer_email))
    return form


def _shipping_countries() -> list[str]:
    # Centralized so unit tests can assert the allow-list.
    return ["US", "KR", "JP", "DE", "GB", "FR", "CA"]


class StripeClient:
    """Live + mock Stripe client. Single instance lives on the app state."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── public API ────────────────────────────────────────────────

    async def create_hardware_checkout(
        self,
        *,
        sku_label: str,
        unit_amount_usd: int,
        quantity: int,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        customer_email: str | None,
    ) -> dict[str, Any]:
        """Create a one-time-payment Checkout Session with shipping collection."""
        if is_mock_mode():
            sid = _mock_session_id()
            session = MockSession(
                id=sid,
                mode="payment",
                url=_mock_url_for(sid),
                success_url=success_url + f"?session_id={sid}",
                cancel_url=cancel_url,
                line_items=[
                    {
                        "name": sku_label,
                        "quantity": quantity,
                        "unit_amount_usd": unit_amount_usd,
                    }
                ],
                metadata=metadata,
                amount_total=unit_amount_usd * 100 * quantity,
                currency=settings.store_default_currency,
                customer_email=customer_email,
            )
            _MOCK_SESSIONS[sid] = session
            logger.info("mock_checkout_created", extra={"session_id": sid, "mode": "payment"})
            return {"id": sid, "url": session.url, "mode": "payment"}

        form = _form_for_payment(
            sku_label=sku_label,
            unit_amount_usd=unit_amount_usd,
            quantity=quantity,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
            customer_email=customer_email,
        )
        return await self._post_session(form)

    async def create_software_checkout(
        self,
        *,
        plan_label: str,
        monthly_amount_usd: int,
        trial_days: int,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        customer_email: str | None,
    ) -> dict[str, Any]:
        """Create a subscription Checkout Session with a free trial."""
        if is_mock_mode():
            sid = _mock_session_id()
            session = MockSession(
                id=sid,
                mode="subscription",
                url=_mock_url_for(sid),
                success_url=success_url + f"?session_id={sid}",
                cancel_url=cancel_url,
                line_items=[
                    {
                        "name": plan_label,
                        "quantity": 1,
                        "unit_amount_usd": monthly_amount_usd,
                        "interval": "month",
                        "trial_days": trial_days,
                    }
                ],
                metadata=metadata,
                amount_total=0,  # trial is free up front
                currency=settings.store_default_currency,
                customer_email=customer_email,
            )
            _MOCK_SESSIONS[sid] = session
            logger.info(
                "mock_checkout_created",
                extra={"session_id": sid, "mode": "subscription"},
            )
            return {"id": sid, "url": session.url, "mode": "subscription"}

        form = _form_for_subscription(
            plan_label=plan_label,
            monthly_amount_usd=monthly_amount_usd,
            trial_days=trial_days,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
            customer_email=customer_email,
        )
        return await self._post_session(form)

    async def retrieve_session(self, session_id: str) -> dict[str, Any]:
        """Return the canonical session payload, in either mode."""
        if is_mock_mode() or session_id.startswith("cs_test_mock_"):
            session = _MOCK_SESSIONS.get(session_id)
            if session is None:
                raise KeyError(session_id)
            return _serialize_mock(session)

        assert settings.stripe_secret_key is not None
        resp = await self._http.get(
            f"{STRIPE_API_BASE}/checkout/sessions/{session_id}",
            auth=(settings.stripe_secret_key, ""),
            params={"expand[]": "line_items"},
        )
        resp.raise_for_status()
        return _normalize_live_session(resp.json())

    # ── mock-only helpers exposed to the mock-checkout router ──────

    @staticmethod
    def get_mock_session(session_id: str) -> MockSession | None:
        return _MOCK_SESSIONS.get(session_id)

    @staticmethod
    def complete_mock_session(
        session_id: str,
        *,
        customer_email: str,
        shipping: dict[str, Any] | None,
    ) -> MockSession:
        session = _MOCK_SESSIONS[session_id]
        session.status = "complete"
        session.payment_status = "paid"
        session.customer_email = customer_email
        session.customer_details = {"email": customer_email, "name": shipping.get("name") if shipping else None}
        if shipping is not None:
            session.shipping_details = {
                "name": shipping.get("name"),
                "phone": shipping.get("phone"),
                "address": {
                    "line1": shipping.get("line1"),
                    "line2": shipping.get("line2"),
                    "city": shipping.get("city"),
                    "state": shipping.get("state"),
                    "postal_code": shipping.get("postal_code"),
                    "country": shipping.get("country"),
                },
            }
        if session.mode == "subscription":
            session.subscription_id = f"sub_test_mock_{secrets.token_urlsafe(12)}"
        return session

    @staticmethod
    def reset_mock_state() -> None:
        """Test-only — drop all mock sessions."""
        _MOCK_SESSIONS.clear()

    # ── internal ──────────────────────────────────────────────────

    async def _post_session(self, form: list[tuple[str, str]]) -> dict[str, Any]:
        assert settings.stripe_secret_key is not None
        body = urlencode(form)
        resp = await self._http.post(
            f"{STRIPE_API_BASE}/checkout/sessions",
            content=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=(settings.stripe_secret_key, ""),
        )
        resp.raise_for_status()
        data = resp.json()
        return {"id": data["id"], "url": data["url"], "mode": data.get("mode", "payment")}


def _normalize_live_session(data: dict[str, Any]) -> dict[str, Any]:
    """Smooth over Stripe API-version differences for the order endpoint.

    Newer API versions moved the collected shipping address from the
    top-level ``shipping_details`` onto ``collected_information``. The order
    endpoint reads ``shipping_details``, so backfill it when only the newer
    shape is present. Left as-is otherwise.
    """
    if not data.get("shipping_details"):
        collected = data.get("collected_information") or {}
        shipping = collected.get("shipping_details")
        if shipping:
            data["shipping_details"] = shipping
    return data


def _serialize_mock(session: MockSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "mode": session.mode,
        "url": session.url,
        "status": session.status,
        "payment_status": session.payment_status,
        "amount_total": session.amount_total,
        "currency": session.currency,
        "customer_email": session.customer_email,
        "customer_details": session.customer_details,
        "shipping_details": session.shipping_details,
        "metadata": dict(session.metadata),
        "line_items": list(session.line_items),
        "subscription": session.subscription_id,
    }


_singleton: StripeClient | None = None


def get_client() -> StripeClient:
    global _singleton
    if _singleton is None:
        _singleton = StripeClient()
    return _singleton


async def shutdown_client() -> None:
    global _singleton
    if _singleton is not None:
        await _singleton.aclose()
        _singleton = None
