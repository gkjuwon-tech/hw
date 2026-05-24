"""API key authentication and HMAC signing.

API keys
========

Layout: ``ctk_live_<base32-22-chars>``.

- The ``ctk_live_`` portion is the public, low-entropy identifier. It is
  what we store in plain text as the ``api_keys.id`` column.
- The 22-char base32 suffix is the secret. We never store the raw secret
  — only a salted, peppered SHA-256 hash. On creation we return the full
  raw key to the caller exactly once.

This shape gives operators a stable key identifier (for logging,
revocation, and rate limit lookups) without leaking the secret in logs.

HMAC signing
============

Every outbound webhook is signed with ``HMAC-SHA256`` using a per-endpoint
secret. The signature header is ``X-Conet-Signature: t=<unix>,v1=<hex>``.
Receivers should reject anything older than 5 minutes to defeat replay.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import DEFAULT_ORG_ID, ApiKey, Organization, get_session

# ── key generation ───────────────────────────────────────────────────


@dataclass(frozen=True)
class GeneratedApiKey:
    """Result of :func:`generate_api_key`. ``raw`` is shown once and discarded."""

    id: str
    raw: str
    hashed_secret: str


def generate_api_key(prefix: str | None = None) -> GeneratedApiKey:
    """Generate a fresh API key. Returns the raw token, its public id, and the hash to store."""
    pfx = prefix or settings.api_key_prefix
    secret_bytes = secrets.token_bytes(16)
    secret = base64.b32encode(secret_bytes).decode("ascii").rstrip("=").lower()
    raw = f"{pfx}_live_{secret}"
    key_id = raw[: len(pfx) + 6 + 8]  # "<prefix>_live_<first-8-chars>"
    return GeneratedApiKey(
        id=key_id,
        raw=raw,
        hashed_secret=hash_api_key_secret(raw),
    )


def hash_api_key_secret(raw: str) -> str:
    """Salt + pepper + SHA-256 of a raw API key. Stable across processes."""
    h = hashlib.sha256()
    h.update(settings.api_key_secret_pepper.encode("utf-8"))
    h.update(b":")
    h.update(raw.encode("utf-8"))
    return h.hexdigest()


def verify_api_key(raw: str, hashed_secret: str) -> bool:
    """Constant-time comparison of a presented raw key against its stored hash."""
    return hmac.compare_digest(hash_api_key_secret(raw), hashed_secret)


def derive_key_id(raw: str) -> str:
    """Recover the public id from a raw key for lookup."""
    # Length must match :func:`generate_api_key`: ``<prefix>_live_<8>``.
    return raw[: len(settings.api_key_prefix) + 6 + 8]


# ── HMAC for webhooks ────────────────────────────────────────────────


def webhook_signature(secret: str, payload: bytes, timestamp: int | None = None) -> str:
    """Produce ``t=<unix>,v1=<hex>`` for the given payload."""
    ts = int(timestamp if timestamp is not None else time.time())
    mac = hmac.new(secret.encode("utf-8"), f"{ts}.".encode() + payload, hashlib.sha256)
    return f"t={ts},v1={mac.hexdigest()}"


def verify_webhook_signature(
    secret: str,
    payload: bytes,
    header: str,
    *,
    max_skew_seconds: int = 300,
    now: int | None = None,
) -> bool:
    """Verify an ``X-Conet-Signature`` header. Constant-time + replay-protected."""
    parts = {}
    for chunk in header.split(","):
        k, _, v = chunk.strip().partition("=")
        if k and v:
            parts[k] = v
    try:
        ts = int(parts["t"])
        sig = parts["v1"]
    except (KeyError, ValueError):
        return False

    current = int(now if now is not None else time.time())
    if abs(current - ts) > max_skew_seconds:
        return False

    mac = hmac.new(secret.encode("utf-8"), f"{ts}.".encode() + payload, hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), sig)


def generate_webhook_secret() -> str:
    """A 32-byte URL-safe secret for HMAC signing."""
    return secrets.token_urlsafe(32)


# ── request-time authentication ──────────────────────────────────────


@dataclass(frozen=True)
class AuthContext:
    """The authenticated principal for a request."""

    org_id: str
    org: Organization
    api_key_id: str | None
    scope: str  # "anonymous" | "read_only" | "read_write" | "admin"


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, raw = authorization.partition(" ")
    if scheme.lower() != "bearer" or not raw:
        return None
    return raw.strip()


async def require_org(
    authorization: str | None = Header(default=None, include_in_schema=False),
    session: AsyncSession = Depends(get_session),
) -> AuthContext:
    """Resolve the current organization from a bearer API key.

    If ``settings.auth_required`` is ``False`` and no key is presented, the
    default workspace is returned. This keeps local development frictionless
    while letting production lock things down with a single env flag.
    """
    raw = _extract_bearer(authorization)
    if raw is None:
        if settings.auth_required:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "missing API key — set Authorization: Bearer <key>",
                headers={"WWW-Authenticate": "Bearer"},
            )
        org = await session.get(Organization, DEFAULT_ORG_ID)
        if org is None:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "default organization not seeded; restart the service",
            )
        return AuthContext(
            org_id=org.id, org=org, api_key_id=None, scope="read_write"
        )

    key_id = derive_key_id(raw)
    record = await session.get(ApiKey, key_id)
    if record is None or record.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")
    if not verify_api_key(raw, record.hashed_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")

    org = await session.get(Organization, record.org_id)
    if org is None or not org.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "organization disabled")

    # ``last_used_at`` is best-effort; concurrent writes are tolerable.
    from datetime import datetime, timezone

    record.last_used_at = datetime.now(timezone.utc)
    await session.commit()

    return AuthContext(
        org_id=org.id, org=org, api_key_id=record.id, scope=record.scope
    )


async def require_write_scope(auth: AuthContext = Depends(require_org)) -> AuthContext:
    """Reject keys that are only allowed to read."""
    if auth.scope == "read_only":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "read-only API key")
    return auth


async def require_admin(
    x_admin_token: str | None = Header(default=None, include_in_schema=False),
) -> None:
    """Static-token guard for ``/v1/admin/*`` endpoints."""
    expected = settings.bootstrap_admin_token
    if not expected:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "admin endpoints disabled — set CONET_BOOTSTRAP_ADMIN_TOKEN to enable",
        )
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid admin token")
