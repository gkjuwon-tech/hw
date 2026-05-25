"""Direct-purchase storefront endpoints.

Two flows:

*   ``POST /v1/store/checkout/hardware`` — one-time-payment Stripe Checkout
    Session for the Tactile Edge appliance. Shipping address is collected
    by Stripe Checkout itself; the buyer never touches our forms. Returns
    the Stripe-hosted URL the marketing site redirects to.
*   ``POST /v1/store/checkout/software`` — subscription Checkout Session
    for the Tactile Cloud plan, with a configurable free-trial window.

After Stripe completes either session it redirects to a page on the
marketing site, which calls ``GET /v1/store/order/{session_id}`` to
display the receipt + (for software) the download links. A webhook at
``POST /v1/store/webhook`` records ``checkout.session.completed`` events
for accounting / reconciliation.

In **mock mode** (no Stripe key) the same endpoints power a local fake
Checkout page rendered by the marketing site, so the entire customer
journey is exercisable without any external credentials.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.core.store_catalog import (
    HARDWARE_SKUS,
    SOFTWARE_PLANS,
    get_hardware_sku,
    get_software_plan,
)
from app.core.stripe_client import (
    StripeClient,
    get_client,
    is_mock_mode,
    verify_stripe_signature,
)

router = APIRouter(prefix="/v1/store", tags=["store"])
logger = get_logger("conet.store")


# ── schemas ────────────────────────────────────────────────────────


class HardwareCheckoutRequest(BaseModel):
    sku_id: str = Field(default="tactile_edge")
    quantity: int = Field(default=1, ge=1, le=20)
    customer_email: str | None = Field(default=None, max_length=200)
    """Optional — Stripe Checkout asks for it if omitted."""

    success_url: str | None = None
    cancel_url: str | None = None


class SoftwareCheckoutRequest(BaseModel):
    plan_id: str = Field(default="tactile_cloud_pilot")
    hardware_session_id: str | None = None
    """Link the subscription to the hardware order, for cross-reference."""

    customer_email: str | None = Field(default=None, max_length=200)
    success_url: str | None = None
    cancel_url: str | None = None


class CheckoutSessionOut(BaseModel):
    id: str
    url: str
    mode: str
    mock: bool


class MockCompleteRequest(BaseModel):
    session_id: str
    customer_email: str = Field(min_length=3, max_length=200)
    name: str | None = None
    phone: str | None = None
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None


# ── helpers ────────────────────────────────────────────────────────


def _hw_success_url(override: str | None) -> str:
    return override or settings.store_success_url


def _hw_cancel_url(override: str | None) -> str:
    return override or settings.store_cancel_url


def _sw_success_url(override: str | None) -> str:
    return override or settings.store_software_success_url


def _sw_cancel_url(override: str | None) -> str:
    return override or settings.store_software_cancel_url


# ── endpoints ──────────────────────────────────────────────────────


@router.get("/catalog")
async def get_store_catalog() -> dict[str, Any]:
    """Public storefront catalog — consumed by the marketing site."""
    return {
        "mock_mode": is_mock_mode(),
        "currency": settings.store_default_currency,
        "hardware": [
            {
                "id": sku.id,
                "label": sku.label,
                "description": sku.description,
                "unit_amount_usd": sku.unit_amount_usd,
                "image_path": sku.image_path,
            }
            for sku in HARDWARE_SKUS.values()
        ],
        "software": [
            {
                "id": plan.id,
                "label": plan.label,
                "description": plan.description,
                "monthly_amount_usd": plan.monthly_amount_usd,
                "trial_days": plan.trial_days,
            }
            for plan in SOFTWARE_PLANS.values()
        ],
        "shipping_countries": [
            "US",
            "KR",
            "JP",
            "DE",
            "GB",
            "FR",
            "CA",
        ],
        "publishable_key": settings.stripe_publishable_key,
    }


@router.post(
    "/checkout/hardware",
    response_model=CheckoutSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_hardware_checkout(
    payload: HardwareCheckoutRequest,
) -> CheckoutSessionOut:
    try:
        sku = get_hardware_sku(payload.sku_id)
    except KeyError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"unknown sku: {payload.sku_id}"
        ) from exc

    client: StripeClient = get_client()
    metadata = {
        "sku_id": sku.id,
        "quantity": str(payload.quantity),
        "source": "marketing_site",
    }
    session = await client.create_hardware_checkout(
        sku_label=sku.label,
        unit_amount_usd=sku.unit_amount_usd,
        quantity=payload.quantity,
        success_url=_hw_success_url(payload.success_url),
        cancel_url=_hw_cancel_url(payload.cancel_url),
        metadata=metadata,
        customer_email=payload.customer_email,
    )
    logger.info(
        "hardware_checkout_created",
        extra={
            "session_id": session["id"],
            "sku_id": sku.id,
            "quantity": payload.quantity,
            "mock": is_mock_mode(),
        },
    )
    return CheckoutSessionOut(
        id=session["id"],
        url=session["url"],
        mode=session["mode"],
        mock=is_mock_mode(),
    )


@router.post(
    "/checkout/software",
    response_model=CheckoutSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_software_checkout(
    payload: SoftwareCheckoutRequest,
) -> CheckoutSessionOut:
    try:
        plan = get_software_plan(payload.plan_id)
    except KeyError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"unknown plan: {payload.plan_id}"
        ) from exc

    client = get_client()
    metadata: dict[str, str] = {
        "plan_id": plan.id,
        "source": "marketing_site",
    }
    if payload.hardware_session_id:
        metadata["hardware_session_id"] = payload.hardware_session_id

    session = await client.create_software_checkout(
        plan_label=plan.label,
        monthly_amount_usd=plan.monthly_amount_usd,
        trial_days=plan.trial_days,
        success_url=_sw_success_url(payload.success_url),
        cancel_url=_sw_cancel_url(payload.cancel_url),
        metadata=metadata,
        customer_email=payload.customer_email,
    )
    logger.info(
        "software_checkout_created",
        extra={
            "session_id": session["id"],
            "plan_id": plan.id,
            "mock": is_mock_mode(),
        },
    )
    return CheckoutSessionOut(
        id=session["id"],
        url=session["url"],
        mode=session["mode"],
        mock=is_mock_mode(),
    )


@router.get("/order/{session_id}")
async def get_order(session_id: str) -> dict[str, Any]:
    """Return canonical order state for a Checkout Session.

    Used by the marketing-site success pages to render a receipt and, for
    software orders, hand out download URLs.
    """
    client = get_client()
    try:
        data = await client.retrieve_session(session_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc

    paid = data.get("payment_status") == "paid" or data.get("status") == "complete"
    response: dict[str, Any] = {
        "id": data["id"],
        "mode": data["mode"],
        "status": data.get("status"),
        "payment_status": data.get("payment_status"),
        "amount_total": data.get("amount_total"),
        "currency": data.get("currency"),
        "customer_email": data.get("customer_email")
        or (data.get("customer_details") or {}).get("email"),
        "shipping_details": data.get("shipping_details"),
        "metadata": data.get("metadata") or {},
        "subscription": data.get("subscription"),
        "paid": paid,
    }

    if data.get("mode") == "subscription" and paid:
        response["downloads"] = {
            "windows": settings.store_download_url_windows,
            "mac": settings.store_download_url_mac,
            "linux": settings.store_download_url_linux,
        }
        plan_id = (data.get("metadata") or {}).get("plan_id")
        if plan_id and plan_id in SOFTWARE_PLANS:
            response["trial_days"] = SOFTWARE_PLANS[plan_id].trial_days

    return response


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request) -> dict[str, str]:
    """Receive and verify Stripe webhook events.

    In **mock mode** this endpoint is reachable but a no-op — mock sessions
    are completed synchronously by ``/mock/complete``.

    In **live mode**, when ``CONET_STRIPE_WEBHOOK_SECRET`` is set every
    event is authenticated against the ``Stripe-Signature`` header before
    we act on it; a missing or invalid signature is rejected with 400. We
    parse the verified envelope and acknowledge known event types
    (``checkout.session.completed`` is the one the purchase flow cares about).
    """
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    logger.info(
        "stripe_webhook_received",
        extra={"length": len(body), "mock": is_mock_mode(), "has_sig": bool(sig)},
    )

    if is_mock_mode():
        return {"received": "mock", "status": "ignored"}

    if not settings.stripe_webhook_secret:
        # Live mode but no signing secret configured yet — record receipt
        # without trusting the payload. Set CONET_STRIPE_WEBHOOK_SECRET to
        # enable verification.
        logger.warning("stripe_webhook_secret_unset")
        return {"received": "noop", "status": "webhook_secret_unset"}

    if not verify_stripe_signature(body, sig, settings.stripe_webhook_secret):
        logger.warning("stripe_webhook_signature_invalid")
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "invalid Stripe-Signature"
        )

    try:
        event = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed event body") from exc

    event_type = event.get("type", "")
    session_id = ((event.get("data") or {}).get("object") or {}).get("id")
    logger.info(
        "stripe_webhook_verified",
        extra={"event_type": event_type, "session_id": session_id},
    )
    return {"received": "ok", "status": "verified", "type": event_type}


# ── mock-checkout endpoints ────────────────────────────────────────


@router.get("/mock/session/{session_id}")
async def get_mock_session(session_id: str) -> dict[str, Any]:
    """Return the mock session record used by ``mock-checkout.html``."""
    session = StripeClient.get_mock_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mock session not found")
    return {
        "id": session.id,
        "mode": session.mode,
        "amount_total": session.amount_total,
        "currency": session.currency,
        "line_items": list(session.line_items),
        "metadata": dict(session.metadata),
        "success_url": session.success_url,
        "cancel_url": session.cancel_url,
        "status": session.status,
        "customer_email": session.customer_email,
    }


@router.post("/mock/complete")
async def complete_mock_session(payload: MockCompleteRequest) -> dict[str, Any]:
    """Simulate the customer finishing the Stripe-hosted checkout page."""
    try:
        session = StripeClient.complete_mock_session(
            payload.session_id,
            customer_email=payload.customer_email,
            shipping={
                "name": payload.name,
                "phone": payload.phone,
                "line1": payload.line1,
                "line2": payload.line2,
                "city": payload.city,
                "state": payload.state,
                "postal_code": payload.postal_code,
                "country": payload.country,
            }
            if payload.line1
            else None,
        )
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mock session not found") from exc

    logger.info(
        "mock_checkout_completed",
        extra={"session_id": session.id, "mode": session.mode},
    )
    return {
        "id": session.id,
        "status": session.status,
        "redirect_url": session.success_url,
    }
