"""Edge claim system — real validation for enrollment.

Two-step enrollment replaces "type any string and it works":

  1. Operator generates a *claim token* via the fleet-management console
     or the on-device kiosk: ``POST /v1/claims`` returns a one-time
     token + expiry.
  2. The edge appliance is physically attached. On first boot the agent
     calls ``POST /v1/claims/redeem`` with the token + its hardware serial
     + firmware hash. The server validates and creates the Edge row.

The plaintext claim token is shown once and never persisted; only a
SHA-256 hash is stored. Tokens expire after 24 hours and can be revoked.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.security import AuthContext, require_write_scope
from app.db import Base, Edge, get_session
from app.schemas import EdgeOut

router = APIRouter(prefix="/v1/claims", tags=["claims"])

# Allow-list of firmware hashes that are accepted at enrollment.
# In production this would be loaded from a signed manifest; for now we
# accept any sha256 (validation is structural rather than content-based).
ACCEPTED_FIRMWARE_PREFIXES = ("TS-G4", "TS-G5", "TS-DEV")


# ── ORM model ────────────────────────────────────────────────────────


class EdgeClaim(Base):
    """A pending-or-redeemed claim token for enrolling an edge appliance."""

    __tablename__ = "edge_claims"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    site: Mapped[str] = mapped_column(String(120), default="")
    expected_serial: Mapped[str] = mapped_column(String(64), default="")
    """Optional pre-bound serial. If set, the redeeming edge must match."""

    expected_model: Mapped[str] = mapped_column(String(80), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redeemed_edge_id: Mapped[str | None] = mapped_column(String(64), default=None)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


# ── schemas ──────────────────────────────────────────────────────────


class ClaimCreate(BaseModel):
    label: str = Field(default="", max_length=120)
    site: str = Field(default="", max_length=120)
    expected_serial: str = Field(default="", max_length=64)
    expected_model: str = Field(default="jetson-orin-nano-8gb", max_length=80)
    ttl_hours: int = Field(default=24, ge=1, le=720)


class ClaimCreated(BaseModel):
    id: str
    token: str  # plaintext, shown once
    label: str
    site: str
    expires_at: datetime


class ClaimOut(BaseModel):
    id: str
    label: str
    site: str
    expected_serial: str
    expected_model: str
    expires_at: datetime
    created_at: datetime
    redeemed_at: datetime | None
    redeemed_edge_id: str | None
    revoked: bool


class ClaimRedeem(BaseModel):
    token: str = Field(min_length=8, max_length=128)
    edge_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    hostname: str = Field(default="", max_length=120)
    serial: str = Field(min_length=4, max_length=64)
    """NVIDIA module serial. Required for claim redemption."""

    model: str = Field(default="jetson-orin-nano-8gb", max_length=80)
    firmware_version: str = Field(min_length=3, max_length=40)
    """Scanner firmware version. Must start with an accepted prefix."""


# ── helpers ──────────────────────────────────────────────────────────


def _hash_token(raw: str) -> str:
    h = hashlib.sha256()
    h.update(b"edge-claim:")
    h.update(raw.encode("utf-8"))
    return h.hexdigest()


def _gen_token() -> tuple[str, str, str]:
    raw = "ec_" + secrets.token_urlsafe(24)
    claim_id = "clm_" + secrets.token_urlsafe(8).replace("_", "").replace("-", "")[:16]
    return claim_id, raw, _hash_token(raw)


# ── routes ───────────────────────────────────────────────────────────


@router.post("", response_model=ClaimCreated, status_code=status.HTTP_201_CREATED)
async def create_claim(
    payload: ClaimCreate,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> ClaimCreated:
    """Generate a one-time enrollment token. Returns the plaintext exactly once."""
    claim_id, raw, hashed = _gen_token()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=payload.ttl_hours)

    claim = EdgeClaim(
        id=claim_id,
        org_id=auth.org_id,
        token_hash=hashed,
        label=payload.label,
        site=payload.site,
        expected_serial=payload.expected_serial,
        expected_model=payload.expected_model,
        expires_at=expires,
        created_at=now,
    )
    session.add(claim)
    await session.commit()

    return ClaimCreated(
        id=claim_id,
        token=raw,
        label=payload.label,
        site=payload.site,
        expires_at=expires,
    )


@router.get("", response_model=list[ClaimOut])
async def list_claims(
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> list[ClaimOut]:
    """List all claims for this org."""
    result = await session.execute(
        select(EdgeClaim)
        .where(EdgeClaim.org_id == auth.org_id)
        .order_by(EdgeClaim.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        ClaimOut(
            id=c.id,
            label=c.label,
            site=c.site,
            expected_serial=c.expected_serial,
            expected_model=c.expected_model,
            expires_at=c.expires_at,
            created_at=c.created_at,
            redeemed_at=c.redeemed_at,
            redeemed_edge_id=c.redeemed_edge_id,
            revoked=c.revoked,
        )
        for c in rows
    ]


@router.post("/{claim_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_claim(
    claim_id: str,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Mark a claim as revoked so it cannot be redeemed."""
    claim = await session.get(EdgeClaim, claim_id)
    if claim is None or claim.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "claim not found")
    claim.revoked = True
    await session.commit()


@router.post("/redeem", response_model=EdgeOut, status_code=status.HTTP_201_CREATED)
async def redeem_claim(
    payload: ClaimRedeem,
    session: AsyncSession = Depends(get_session),
) -> Edge:
    """Atomic edge enrollment via claim token.

    This is the *only* path that creates an Edge row in production. The
    legacy POST /v1/edges remains for back-compat but is gated behind a
    settings flag.

    Validation:
      - token hashes to a known, unredeemed, unrevoked, unexpired claim
      - firmware version has an accepted prefix (rejects rando strings)
      - if the claim pre-bound a serial, the presented serial must match
      - edge_id must be globally unique (not already enrolled)
    """
    hashed = _hash_token(payload.token)
    result = await session.execute(
        select(EdgeClaim).where(EdgeClaim.token_hash == hashed)
    )
    claim = result.scalars().first()
    if claim is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid claim token")
    if claim.revoked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "claim token revoked")
    if claim.redeemed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "claim already redeemed")

    now = datetime.now(timezone.utc)
    expires_at = claim.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(status.HTTP_410_GONE, "claim token expired")

    if not any(payload.firmware_version.startswith(p) for p in ACCEPTED_FIRMWARE_PREFIXES):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"firmware version '{payload.firmware_version}' not in accepted prefixes",
        )

    if claim.expected_serial and claim.expected_serial != payload.serial:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "presented serial does not match claim's expected serial",
        )

    existing = await session.get(Edge, payload.edge_id)
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "edge_id already enrolled")

    edge = Edge(
        id=payload.edge_id,
        org_id=claim.org_id,
        hostname=payload.hostname or payload.edge_id,
        serial=payload.serial,
        model=payload.model or claim.expected_model,
        site=claim.site,
        firmware_version=payload.firmware_version,
        status="online",
        last_seen_at=now,
    )
    session.add(edge)
    claim.redeemed_at = now
    claim.redeemed_edge_id = payload.edge_id

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "enrollment race") from exc

    await session.refresh(edge)
    return edge
