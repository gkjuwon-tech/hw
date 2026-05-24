"""Webhook endpoint registration and delivery audit."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    AuthContext,
    generate_webhook_secret,
    require_org,
    require_write_scope,
)
from app.db import WebhookDelivery, WebhookEndpoint, get_session
from app.schemas import (
    WebhookCreate,
    WebhookCreated,
    WebhookDeliveryOut,
    WebhookOut,
)

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


def _to_out(record: WebhookEndpoint) -> WebhookOut:
    return WebhookOut(
        id=record.id,
        url=record.url,
        events=[e.strip() for e in record.events.split(",") if e.strip()],
        active=record.active,
        description=record.description,
        created_at=record.created_at,
    )


@router.post("", response_model=WebhookCreated, status_code=status.HTTP_201_CREATED)
async def register_webhook(
    payload: WebhookCreate,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> WebhookCreated:
    record = WebhookEndpoint(
        id=str(uuid.uuid4()),
        org_id=auth.org_id,
        url=str(payload.url),
        secret=generate_webhook_secret(),
        events=",".join(sorted({e.strip() for e in payload.events if e.strip()})) or "*",
        description=payload.description,
    )
    session.add(record)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "webhook already registered for this URL") from exc
    await session.refresh(record)

    return WebhookCreated(
        id=record.id,
        url=record.url,
        events=[e.strip() for e in record.events.split(",") if e.strip()],
        active=record.active,
        description=record.description,
        created_at=record.created_at,
        secret=record.secret,
    )


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[WebhookOut]:
    result = await session.execute(
        select(WebhookEndpoint)
        .where(WebhookEndpoint.org_id == auth.org_id)
        .order_by(WebhookEndpoint.created_at.desc())
    )
    return [_to_out(record) for record in result.scalars().all()]


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> None:
    record = await session.get(WebhookEndpoint, webhook_id)
    if record is None or record.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    await session.delete(record)
    await session.commit()


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(
    webhook_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[WebhookDelivery]:
    endpoint = await session.get(WebhookEndpoint, webhook_id)
    if endpoint is None or endpoint.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook not found")
    result = await session.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.endpoint_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())
