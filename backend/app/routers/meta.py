"""Health, readiness, and Prometheus scrape endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import settings
from app.core.metrics import render
from app.db import get_session

router = APIRouter(tags=["meta"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": __version__,
        "environment": settings.environment,
    }


@router.get("/readyz")
async def readyz(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """Returns 200 only when the database is reachable."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"database not ready: {exc!r}",
        ) from exc
    return {"status": "ready", "database": "ok"}


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    if not settings.metrics_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "metrics disabled")
    payload, content_type = render()
    return Response(content=payload, media_type=content_type)
