"""Admin endpoints: create organizations and mint API keys.

Gated by ``X-Admin-Token``. Disabled entirely unless
``CONET_BOOTSTRAP_ADMIN_TOKEN`` is set.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import get_limiter
from app.core.security import generate_api_key, require_admin
from app.db import ApiKey, Organization, get_session
from app.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    OrganizationCreate,
    OrganizationOut,
)

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/organizations", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    session: AsyncSession = Depends(get_session),
) -> Organization:
    org = Organization(
        id=payload.id,
        name=payload.name,
        contact_email=payload.contact_email,
        rate_limit_per_minute=payload.rate_limit_per_minute,
    )
    session.add(org)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "organization id already exists") from exc
    await session.refresh(org)
    if payload.rate_limit_per_minute:
        get_limiter().set_override(f"key:{org.id}", payload.rate_limit_per_minute)
    return org


@router.get("/organizations", response_model=list[OrganizationOut])
async def list_organizations(
    session: AsyncSession = Depends(get_session),
) -> list[Organization]:
    result = await session.execute(select(Organization).order_by(Organization.created_at.desc()))
    return list(result.scalars().all())


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreated:
    org = await session.get(Organization, payload.org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "organization not found")

    generated = generate_api_key()
    # Avoid an extremely unlikely id collision.
    if await session.get(ApiKey, generated.id) is not None:
        generated = generate_api_key()

    record = ApiKey(
        id=generated.id,
        org_id=org.id,
        label=payload.label,
        scope=payload.scope,
        hashed_secret=generated.hashed_secret,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    return ApiKeyCreated(
        id=record.id,
        raw=generated.raw,
        org_id=org.id,
        label=record.label,
        scope=record.scope,
        created_at=record.created_at,
    )


@router.get("/organizations/{org_id}/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    org_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[ApiKey]:
    result = await session.execute(
        select(ApiKey)
        .where(ApiKey.org_id == org_id)
        .order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyOut)
async def revoke_api_key(
    key_id: str,
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    record = await session.get(ApiKey, key_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
    if record.revoked_at is None:
        record.revoked_at = datetime.now(timezone.utc)
        await session.commit()
    return record
