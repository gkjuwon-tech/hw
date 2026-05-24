"""Outbound webhook dispatcher.

The delivery loop runs as an asyncio background task started by the
FastAPI lifespan. On each tick it:

1. Reads pending ``WebhookDelivery`` rows whose ``next_attempt_at`` has
   elapsed.
2. POSTs the JSON payload with the ``X-Conet-Signature`` HMAC header.
3. Records ``last_response_status`` / ``last_error`` and either marks the
   row as ``succeeded`` (2xx) or schedules an exponential-backoff retry.
4. After ``settings.webhook_max_attempts`` the row is marked ``dead`` and
   left for the operator to replay.

This is deliberately in-process — at the scale we are launching, an
external queue (SQS, Sidekiq, Temporal) is overkill. The escape hatch is
to swap ``_dispatcher_loop`` for a Redis-backed worker without touching
the call sites.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.metrics import webhook_deliveries_total
from app.core.security import webhook_signature
from app.db import WebhookDelivery, WebhookEndpoint, session_factory

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _backoff_at(attempts: int) -> datetime:
    """Exponential backoff with full jitter, capped at the configured ceiling."""
    base = settings.webhook_base_backoff_seconds * (2 ** max(0, attempts - 1))
    ceil = min(settings.webhook_max_backoff_seconds, base)
    jitter = ceil * (0.5 + secrets.SystemRandom().random() * 0.5)
    return _now() + timedelta(seconds=jitter)


async def enqueue(
    org_id: str,
    event: str,
    payload: dict,
    endpoint_id: str | None = None,
) -> int:
    """Enqueue a delivery for every matching endpoint. Returns the count enqueued."""
    body = json.dumps(payload, separators=(",", ":"), default=str)
    factory = session_factory()
    async with factory() as session:
        q = select(WebhookEndpoint).where(
            WebhookEndpoint.org_id == org_id, WebhookEndpoint.active.is_(True)
        )
        if endpoint_id is not None:
            q = q.where(WebhookEndpoint.id == endpoint_id)
        endpoints = list((await session.execute(q)).scalars().all())

        enqueued = 0
        for ep in endpoints:
            wanted = {e.strip() for e in (ep.events or "").split(",") if e.strip()}
            if wanted and event not in wanted:
                continue
            session.add(
                WebhookDelivery(
                    endpoint_id=ep.id,
                    org_id=org_id,
                    event=event,
                    payload=body,
                    status="pending",
                    attempts=0,
                    next_attempt_at=_now(),
                )
            )
            enqueued += 1
        await session.commit()
        return enqueued


async def _deliver_one(client: httpx.AsyncClient, delivery: WebhookDelivery) -> tuple[bool, int | None, str | None]:
    factory = session_factory()
    async with factory() as session:
        endpoint = await session.get(WebhookEndpoint, delivery.endpoint_id)
        if endpoint is None or not endpoint.active:
            return False, None, "endpoint missing or inactive"

        body = delivery.payload.encode("utf-8")
        sig = webhook_signature(endpoint.secret, body)
        headers = {
            "content-type": "application/json",
            settings.webhook_signature_header: sig,
            settings.webhook_id_header: str(uuid.uuid4()),
            settings.webhook_event_header: delivery.event,
        }
        try:
            resp = await client.post(
                endpoint.url,
                content=body,
                headers=headers,
                timeout=settings.webhook_request_timeout_seconds,
            )
            ok = 200 <= resp.status_code < 300
            return ok, resp.status_code, None if ok else resp.text[:500]
        except httpx.HTTPError as exc:  # network, timeout, dns, etc.
            return False, None, repr(exc)[:500]


async def _process_due() -> int:
    """Process a batch of due deliveries. Returns the number attempted."""
    factory = session_factory()
    now = _now()
    async with factory() as session:
        q = (
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status == "pending",
                WebhookDelivery.next_attempt_at <= now,
            )
            .order_by(WebhookDelivery.id.asc())
            .limit(32)
        )
        due = list((await session.execute(q)).scalars().all())

    if not due:
        return 0

    async with httpx.AsyncClient() as client:
        for delivery in due:
            ok, status_code, err = await _deliver_one(client, delivery)
            async with factory() as session:
                # Re-fetch inside this session.
                d = await session.get(WebhookDelivery, delivery.id)
                if d is None:
                    continue
                d.attempts += 1
                d.last_response_status = status_code
                d.last_error = err
                if ok:
                    d.status = "succeeded"
                    d.delivered_at = _now()
                    webhook_deliveries_total.labels(status="succeeded").inc()
                elif d.attempts >= settings.webhook_max_attempts:
                    d.status = "dead"
                    webhook_deliveries_total.labels(status="dead").inc()
                else:
                    d.status = "pending"
                    d.next_attempt_at = _backoff_at(d.attempts)
                    webhook_deliveries_total.labels(status="retry").inc()
                await session.commit()

    return len(due)


class _Dispatcher:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop = asyncio.Event()
            self._task = asyncio.create_task(self._run(), name="webhook-dispatcher")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                processed = await _process_due()
            except Exception:  # noqa: BLE001
                logger.exception("webhook dispatcher tick failed")
                processed = 0
            sleep_for = 0.5 if processed else 2.0
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=sleep_for)
            except TimeoutError:
                pass


dispatcher = _Dispatcher()
